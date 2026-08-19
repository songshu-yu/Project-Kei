# GPT-SoVITS 外部引擎 Provider 与受控获取

## 不变引擎边界

PK-211 只拥有 GPT-SoVITS 的引擎描述、PK-210 `TextToSpeechProvider` 适配、外部安装登记、显式受控获取和 9880 启动定位。Kei 或其他角色的权重、参考音频、提示文本和 Voice Pack 注册/切换全部属于 PK-212；PK-211 不读取、移动、修改或发现这些资产。

```text
PK-210 SynthesisRequest + PK-212 opaque VoicePackRef.handle
  -> GPTSoVITSProvider
  -> local HTTP 127.0.0.1:9880
       ├─ api.py style: POST /
       └─ legacy v2 style: POST /tts
```

`GPTSoVITSProvider` 默认采用 `auto`：先调用现有 `api.py` 风格，只有固定的 404 才回退 legacy `/tts`。也可显式选择 `api_py` 或 `legacy_v2`。健康检查只访问 `/docs`，能力固定报告 WAV、合成、取消、关闭和默认超时；超时、连接失败、非音频响应与其他上游错误只映射为 PK-210 的有限错误，不复制响应正文、异常文本或本机路径。

Provider 不扫描磁盘。角色引用只能来自 PK-210 传入的只读不透明 handle；兼容环境字段仍可为既有调用提供通用参考参数，但没有内置角色路径、角色名或模型发现逻辑。

Voice Pack 权重切换兼容两种固定的本机 9880 契约。Provider 优先以单次
`GET /set_model?gpt_model_path=...&sovits_model_path=...` 同时提交两项 checkpoint；
只有该接口明确返回 404 或 405 时，才回退旧版 `/set_gpt_weights` 与
`/set_sovits_weights`。超时、取消、5xx 或其他响应不会触发第二套写入。成功风格在
当前 Provider 实例内缓存；接口、参数和异常正文均不会进入公开 health、日志或状态。

## 单实例共享引擎会话

GPT-SoVITS 的 GPT 与 SoVITS checkpoint 是 9880 进程级共享状态，不属于单个 HTTP 请求。`GPTSoVITSProvider` 因此只维护一套客户端和一把共享引擎会话锁，不创建第二套引擎规避并发。以下操作都以这把锁为线性化点：

```text
synthesis: acquire -> re-read Registry active Pack -> switch if needed -> POST synthesis -> release
selection: acquire -> switch both weights -> atomic Registry active save -> release
close: mark closing -> cancel queued/active sessions -> wait rollback/exit -> close client
```

合成不会只在切换阶段持锁，而是把完整上游音频响应纳入会话；因此 Pack A 的合成结束前，Pack B 的选择或合成不能改写共享权重。合成取得锁后会重新解析 Registry 的活动 Pack，不信任锁外取得的旧引用。选择则通过 `activate_voice_pack_transaction()` 把 Registry 的 `os.replace` 提交放进同一会话，避免“引擎已切到 B、Registry 仍为 A”的可插入窗口。重复选择已经就绪的同一 Pack 不重复调用权重端点。

权重切换以两项为一个原子单元。第一项或第二项失败、以及任务在任一阶段被取消时，Provider 都在释放会话前用独立受保护任务重新应用旧 GPT 与旧 SoVITS 权重；清理完成后继续传播原异常或 `CancelledError`。Registry 提交失败也在同一会话内触发相同回滚。若旧权重恢复失败，Provider 清除活动身份并进入 `unknown`，health 返回 `tts_engine_state_unknown`；Registry 同步把活动视图隐藏并拒绝解析，直到一次完整成功选择恢复为 `ready`。未知状态绝不回退为“旧 Pack 仍可用”的假成功。

## 固定描述与来源链

项目描述位于 `server/features/voice/providers/gpt_sovits/engine.json`，包含 engine id、Provider 协议版本、上游仓库、固定 release/完整 commit、版本、许可证、固定分发 revision、归档名称/字节数/SHA-256、API 风格、健康检查、能力、归档限制和本机登记策略。

当前确认链为：

- 上游：`RVC-Boss/GPT-SoVITS` release `20250606v2pro`，commit `d7c2210da8c013e81a94bfc7b811a477c99fd506`；
- 分发：上游 release 明确链接的 `lj1995/GPT-SoVITS-windows-package`，固定 revision `fb387b7a65a5441e5e3985f4ab9b721a9d455363`；
- NVIDIA 50 系包：`GPT-SoVITS-v2pro-20250604-nvidia50.7z`，`8,835,144,925` 字节，SHA-256 `97b4edcd451c42357db7e26e6c1c877ca5d85144fe97beaff6d7005d35bee008`。

生产加载器会拒绝非上述官方仓库、非完整 commit/revision、非 HTTPS 固定路径、非 SHA-256、错误大小和不受支持的 API 风格。CLI 不接受 URL、Git URL、安装命令、PowerShell/BAT、额外启动参数或脚本。

## 本机登记与状态

实际安装根只写入忽略的 `server/data/gpt_sovits_engine.local.json`，公开描述与 README 不包含绝对路径。本机状态区分：

- `unregistered`：没有本机登记；
- `registered_existing` / `unverified_existing_install`：入口已窄范围核对，可离线复用，但没有用原始归档 SHA-256 证明整个既有安装；
- `installed_verified` / `sha256_verified`：由受控获取校验固定归档并原子安装。

登记只检查用户明确给出的根目录及描述中的 `api.py`、`runtime/python.exe`，不递归列目录、不读取源码、不接触权重或参考音频。普通 agent 只需阅读 Provider、`engine.json` 和无路径状态输出。

## 受控获取事务

获取只能由用户显式运行独立 CLI，并精确提交 descriptor 中的 engine id 作为确认。应用导入、API 启动、控制台、health、`start_all_services` 和 `start_gptsovits` 均不会下载或安装。

```text
fixed descriptor
  -> exact HTTPS source
  -> isolated download temp
  -> exact byte count + SHA-256
  -> bounded archive validation
  -> sibling staging directory
  -> fixed archive root + fixed entry files
  -> marker (scripts_executed=false)
  -> atomic move to empty/nonexistent external target
  -> atomic ignored local registration
```

ZIP 与可选 7z 解包都拒绝绝对路径、`..`、盘符、目标逃逸、链接/重解析点、过多文件、过大解压体积和异常压缩比。归档中的 Python、PowerShell、BAT 或其他脚本只是文件，永不自动执行。真实 7z 需要 Python 解包依赖；依赖缺失会返回 `extractor_dependency_missing`，必须由用户另行显式处理，系统不执行 `pip`、CUDA 或环境安装。

非空未标记目标拒绝覆盖；同一固定 marker 可重复获取并直接复用。离线模式只复用本机登记或匹配 marker 的显式目录，不扩大扫描范围。下载、摘要、解包、布局、移动或本机配置提交失败都会清理本次临时产物；配置提交失败时还会移除本次新安装，旧安装与旧配置保持不变。

## 启动兼容

`server/start_gptsovits.bat` 继续进入 `scripts/start_gptsovits.ps1`，端口仍为 9880。PowerShell 启动器只读取项目描述与忽略的本机登记，解析固定 `runtime/python.exe` 和 `api.py`，然后在用户显式启动时执行 `api.py -a 127.0.0.1 -p 9880`。本机配置不能提供命令、脚本、权重、参考音频或任意参数；缺配置、入口缺失、路径落入项目、engine id 不匹配都会明确失败，不伪装启动成功。

## PK-213 的单向依赖

PK-213 只发布和获取角色 Voice Pack。它可以读取 PK-211 的脱敏 Engine ID、
兼容版本和无路径登记状态，以便在 Pack 安装后说明仍缺少哪个 Engine；不得修改
`engine.json`、本机 Engine 登记、9880 Provider 或受控获取事务，也不得把
GPT-SoVITS 归档重复装入角色包。

`voice-pack.bat install <pack@version>` 不得隐式调用 PK-211 下载器。若 Engine
未登记，应分别报告“Pack 已安装/未安装”和“语音可用/不可用”，给出 PK-211
已有的精确获取或登记命令后停止。未来若提供明确的组合命令，也必须对 Engine 与
Pack 分别展示固定来源、体积、目标和确认；任一阶段都不能静默安装 CUDA、驱动、
解包器或执行远程脚本。

PK-213 预发布 CLI 已遵守这一方向：它只读取 `LocalEngineRegistry.status()` 的
无路径字段。Engine 未登记时仍可完成经过 PK-212 校验的 Pack 导入和启用，但
跳过选择并返回固定的 `voice_pack_engine_unavailable` 与 PK-211 状态命令；
不会调用 `acquire`、修改 Engine 登记或访问 9880。当前内置 Voice Pack catalog
没有真实 Release，因此不存在生产下载副作用。
