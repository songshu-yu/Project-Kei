# Project Kei Voice Pack Schema、注册表与切换

## 边界

PK-212 只拥有可变化的角色声音资产描述、本机登记和选择。它不拥有 GPT-SoVITS 上游源码/安装、ASR、语音 HTTP 编排、LLM Profile、system prompt、Persona Pack、长期记忆或角色业务状态。

依赖方向固定为：

```text
VoicePackRegistryService
  -> PK-210 VoicePackRef（ID、版本、engine、进程内不透明 handle）
  -> PK-211 GPTSoVITSProvider.activate_voice_pack()/synthesize()

PK-210 VoiceService -> VoicePackRegistryService.resolve_active_pack()
```

PK-210 不读取注册表，PK-211 不拥有注册表。主应用只负责注入同一个 resolver/activator；新增角色或版本不修改语音编排与 Engine Provider。

LLM 模型、system prompt 和 Persona Pack 永远不是 Voice Pack 内容。未来如需关联，只能在另立契约后使用稳定 ID，不能嵌入路径、提示正文、凭证或执行逻辑。

## Schema v1

正式 JSON Schema 是 `server/features/voice/voice_packs/voice-pack.schema.json`，包根 manifest 固定为 `voice-pack.json`。v1 必填：

- `schema_version=1`、`id`、`name`、语义化 `version`；
- `engine.provider=gpt-sovits` 与 `engine.protocol_version`；
- `supported_languages`；
- GPT checkpoint、SoVITS checkpoint、参考音频；
- 参考文本、参考语言、默认文本语言；
- 可选的白名单生成参数；
- 每项文件的完整性声明；
- 可选来源、作者、许可证和再分发状态。

可移植包的三个文件引用只能使用包根内的 POSIX 相对路径，且完整性模式必须为精确 `size_bytes + sha256`。解析和导入拒绝绝对路径、盘符、反斜杠、空段、`.`、`..`、根目录逃逸、符号链接、未知字段/引擎/版本、缺失文件、大小/摘要不符及可执行/安装器文件。

现有本机资产允许使用 `existence_only`，但只能通过显式本机登记写入忽略的注册表。此模式只验证必要文件存在、是普通文件且不是符号链接，不打开文件、不计算摘要，也不表示来源、许可证或可再分发性已验证。可移植导入不能使用该模式。

Voice Pack 没有命令、hook、依赖安装、URL 下载或任意脚本字段。目录/ZIP 中出现 BAT、CMD、PowerShell、Python、Shell、可执行程序或动态库会被拒绝；导入不会联网、启动引擎或执行包内内容。

## 本机注册表

`VoicePackRegistry` 使用版本化 JSON 状态，内容为 `registry_version`、活动 `id@version` 和各版本记录。记录包含 manifest、启用状态、来源类型、本机资产绑定和登记时间。文件通过同目录临时文件、flush/fsync 与 `os.replace` 原子替换；失败保留旧文件且清理临时文件。

实际绝对路径只存在于被忽略的本机注册表，不进入 Schema 示例、公开 README、模块目录或 HTTP 响应。公开列表只包含 ID、名称、版本、engine、语言、完整性模式、启用/活动状态和登记时间。

可移植目录包原地登记，不移动或删除源文件。ZIP 只在用户显式导入时安全展开到忽略的 `server/runtime/voice_packs/<id>/<version>/`；归档条目同样拒绝路径逃逸、链接、执行文件和数量/展开大小超限。注销只删除注册记录并把 `source_assets_deleted=false` 写入结果，默认不删除目录源、ZIP 源、外部模型或已展开运行副本。真正清除大型资产必须另立明确操作和确认，本轮没有该接口。

## 生命周期与失败语义

```text
import: validate tree -> parse schema -> validate every asset -> atomic registry save
enable: resolve record -> revalidate assets -> atomic enabled=true
select: revalidate candidate -> Provider activate/probe -> atomic active ID save
disable: atomic enabled=false; active candidate becomes none
unregister: atomic record removal; assets remain
```

导入失败不产生注册记录；ZIP 在注册表提交前失败会清理本次新建的受控临时/运行目录，不触碰源归档。重复 `id@version` 被拒绝，允许同一 ID 的不同版本并存。

Registry 操作仍由自己的串行锁保护；生产选择另外进入 GPT-SoVITS Provider 的唯一共享引擎会话，并把“两项权重切换 + Registry 活动 ID 原子保存”作为同一个事务。Provider 激活候选失败、任务取消或注册表保存失败时都在释放共享会话前恢复旧 GPT/SoVITS 两项权重；只有候选激活与原子保存都成功，新的活动 ID 才对 PK-210 消费者可见。合成也持有同一共享会话直至音频响应完成，并在锁内重新确认 Registry 当前活动 Pack，因此锁外旧引用不会造成声音回切或身份漂移。

切换中间态公开为 `switching` 且不被视为可用。回滚成功后 Provider、Registry 活动 ID 与假/真实引擎两项权重共同恢复旧 Pack，再传播原失败或 `CancelledError`。回滚自身失败时 Provider 清除内存活动身份并进入 `unknown`；Registry 的 list/health/resolve 同步返回无活动 Pack 和 `voice_pack_engine_state_unknown`，即使磁盘上的原子注册表仍保留最后一次已提交 ID，也不会把它冒充为当前可用声音。后续一次完整成功选择可以从未知状态恢复。

Provider 从不透明 handle 取得 GPT/SoVITS checkpoint、参考音频、参考文本、参考/文本语言和白名单生成参数。它通过已有 9880 服务的固定权重切换端点应用 checkpoint，不扫描目录、不猜测角色、不读取权重内容；随后合成请求只使用该 Pack 配置。

## 管理 API 与本机 Kei 适配

管理命名空间是 `/api/v1/voice-packs`：列表只读；导入、启用、选择、停用和注销必须同时通过本机客户端地址与 Origin 控制。浏览器 Origin 只允许 `http://127.0.0.1:8000`、`http://localhost:8000` 和等价 IPv6 本机控制台；缺失 Origin 的本机非浏览器调用继续允许，非本机客户端即使没有 Origin 也拒绝。

主应用先以全局 loopback 边界和三个精确本机 Origin 的 CORS 保护全部 HTTP/WS 路由，再保留 Voice Pack 专用安全中间件作纵深防御。该中间件只处理 `/api/v1/voice-packs` 的写方法及声明写方法的 OPTIONS：恶意 Origin 的预检在 CORS 返回允许头之前以 403 终止，实际写请求也在进入路由前拒绝；路由随后通过注入的统一 `local_control_guard` 再检查一次。GET 和声明 GET 的只读预检不受这项模块写保护影响，但仍受全局本机边界保护。错误返回稳定 code 与有限说明，不回显包路径、绑定路径、权重名、音频名或异常链。

现有 Kei 三项资产保持原位。本机登记内嵌一个 `kei@1.0.0` manifest，并把三个逻辑相对路径映射到已有绝对路径；登记过程只做存在性检查，未移动、复制、训练、读取或摘要大型文件。该注册表和所有真实路径/资产均由 Git 忽略。

## 验证边界

自动测试只在系统临时目录创建微小假 checkpoint、假 WAV、假 ZIP、假注册表和假 Provider，并用 `httpx.MockTransport` 模拟 9880。除导入、Schema、路径、摘要、注册表和 API 覆盖外，独立共享引擎测试还覆盖两阶段中途取消、第二阶段失败并成功回滚、回滚自身失败、Pack A 合成阻塞期间选择 Pack B、两个 Pack 并发合成、重复选择、Provider close 与切换/合成并发，以及失败后旧 Pack 继续合成。独立 Origin 夹具覆盖恶意/合法/缺失 Origin、非本机客户端、五类写接口和 POST/DELETE CORS 预检，并逐次断言临时注册表状态不变。测试不访问网络、8000/9880、真实模型或真实参考音频。

## PK-213 发布与远程获取边界

PK-213 是 PK-212 之上的分发层，不是第二套 Voice Pack Schema 或 Registry。
依赖方向冻结为：

```text
tracked trusted catalog
  -> PK-213 bounded HTTPS acquisition / release-package validation
  -> PK-212 VoicePackRegistryService import / enable / select
  -> PK-211 registered GPT-SoVITS Engine
```

PK-213 可拥有版本化远程 catalog、发布构建器、下载缓存、Windows CLI/BAT 和
分发专项测试；不得修改 PK-212 对 manifest、逐文件摘要、本机注册表和原子选择
的最终解释权。远程包必须继续使用 `voice-pack.json` Schema v1，并只包含声明的
角色 checkpoint、必要参考音频、README、LICENSE 和 NOTICE。包内不得包含
GPT-SoVITS Engine、训练集、训练缓存、未使用 checkpoint、秘密、个人状态、
安装脚本、可执行文件、动态库或符号链接。

发布构建器在任何 manifest/资产内容 I/O 前，以不跟随链接的元数据检查验证
source root、其父链、逐层目录和每个文件；普通文件必须 `st_nlink == 1`，Windows
路径不得带 `FILE_ATTRIBUTE_REPARSE_POINT`。输出 ZIP、`.sha256` 和
`.release.json` 必须位于 source root 外，所有目标必须未使用，输出父链也不得
包含 symlink、junction 或其他 reparse point。

第一版 catalog 只接受仓库内置条目。每个可安装版本必须固定 HTTPS 来源、允许
主机、不可变 release/tag/commit 或 revision、精确归档大小、ZIP SHA-256、
最大文件数、单文件/总解压大小、压缩比、许可证和兼容范围。远程 `.sha256`
文件只供人工核对；真正信任锚是已经合并到 Git 的 catalog SHA-256。禁止
`latest`、`main`、可变重定向、任意 URL、Git URL、镜像、shell 命令和包内 hook。

安装分为两个原子边界：获取/校验/PK-212 导入成功后，Pack 可作为已安装记录存在；
启用/选择继续使用 PK-212 与 PK-211 的既有事务。Engine 缺失或选择失败时，新
Pack 可以明确保持“已安装但不可用”，旧活动 Pack、旧 Engine 权重和旧活动 ID
不变。安装工具必须分别报告 Pack 安装状态与 Engine 可用状态，不得自动获取约
8 GB Engine、CUDA、驱动、7-Zip 或其他系统依赖。

预发布实现位于 `voice_packs/catalog/` 与 `voice_packs/distribution/`。内置
catalog 只有严格 JSON Schema/加载器，没有生产条目；CLI 因此不会把规划中的
`kei@1.0.0` 冒充为可下载。只有显式 `install` 会使用 catalog 固定 HTTPS，
下载器逐跳检查允许主机、限制重定向/超时/字节数并在解压前核对精确大小和
SHA-256。`download-only` 只原子保存完整验证的忽略缓存。

外层 ZIP 先拒绝穿越、绝对/盘符路径、链接、重复/冲突路径、未声明文件、
可执行内容、文件数/单文件/总大小和压缩比异常，再在系统临时目录展开。
分发层只检查固定 Release 外壳与包级信任；manifest 和三个资产的最终解释仍由
PK-212 完成。PK-212 提供只读 `verify(id, version)` 与
`compare_content(id, version, candidate_root)` service 接缝：二者都在 PK-212
自身锁内复用既有 manifest/资产校验，不写 Registry/Engine、不新增 HTTP API，
比较结果只返回 ID、版本和内容是否等价，不暴露路径。同 key 的可信安装只有在
候选 Release 与已安装规范化 manifest（含全部声明资产大小/SHA）完全一致时才
幂等；校验失败、无法证明或内容不同均由分发层稳定转为 conflict，旧 Registry、
runtime、缓存和活动 Pack 保持不变。

真实 Kei 权重、参考音频、许可证和再分发权尚未由 PK-000 确认；在此之前不得
生成生产 `kei.json`、真实 ZIP、URL、大小或摘要，也不得创建 GitHub Release。
自动测试只能使用系统临时目录、`httpx.MockTransport` 和微型虚构
checkpoint/WAV/ZIP。
