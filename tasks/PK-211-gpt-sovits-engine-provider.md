# PK-211 — GPT-SoVITS Engine Provider 与受控获取

- 状态：待集成
- 优先级：P1
- 所属模块：`voice_engine_provider`
- 依赖任务：PK-010、PK-100、PK-210
- 负责路径：`server/features/voice/providers/gpt_sovits/`、项目内 GPT-SoVITS 来源/版本/完整性元数据、显式受控获取工具、对应测试与文档
- 当前对话：2026-08-08 PK-000 最终复核退回并授权唯一共享串行窗口；本对话除 PK-211 专属路径外，只最小修改生产装配与永久回归，不修改官方 Catalog、TASKS 或其他业务

## 目标

为不纳入仓库的 GPT-SoVITS 外部引擎提供一个符合 PK-210 `TTSProvider` 契约的适配层，并建立可审计、需用户显式触发的受控获取流程。项目只保存官方来源、固定 release/commit、完整性信息、预期安装位置和兼容能力，不保存上游源码。

## 不在本任务内

- 不把 GPT-SoVITS 上游源码复制到 Project Kei 或 `vendor/`，不要求普通 agent 阅读或索引外部源码树。
- 不定义、导入、切换或移动 Kei/其他角色的权重、参考音频和 Voice Pack 配置；这些归 PK-212。
- 不实现 ASR、LLM、对话历史、Persona Pack 或业务语音意图。
- 不修改 PK-210 的请求/响应或 Provider 契约；发现缺口时先记录接口需求并交回 PK-000。
- 不提供“启动时自动安装”“缺失时自动下载”或远程脚本执行能力。

## 接口契约

- 实现 PK-210 定义的 `TTSProvider`/Engine Provider 适配契约，默认连接既有本机 `127.0.0.1:9880`，不得新增端口。
- 适配器接收 PK-210 的合成请求和 PK-212 已解析的只读 Voice Pack 句柄；不得自行搜索硬盘、猜测权重或扫描安装树。
- Provider 健康/能力结果只报告可用性、受支持协议版本和已清洗的错误类别，不返回上游完整错误体、命令行、绝对模型路径或响应正文。
- 保持现有 GPT-SoVITS API 风格与 legacy `/tts` 兼容策略，但重试、超时、取消和错误分类由公开适配契约约束。

## 受控获取契约

- 项目内的来源描述必须包含：官方 HTTPS 来源、固定 release 或完整 commit、归档文件名、字节大小、强完整性算法与摘要、支持的 Provider 协议版本、许可证/上游说明和预期安装根标识。
- 获取只能由用户显式运行独立命令触发；应用导入、API 启动、控制台打开、Provider 健康检查和普通启动器均不得触发下载。
- 禁止 `curl | shell`、PowerShell 远程脚本管道、安装后自动执行未知脚本或绕过 TLS/完整性校验。
- 下载先进入独立临时目录，完整性通过后再安全解包；必须拒绝绝对路径、`..` 穿越、逃逸目标根的链接和超出限制的归档。
- 安装目标必须是用户确认的仓库外目录。已有非空目标默认拒绝覆盖；失败时移除本次临时产物并保留旧安装不变。
- 离线环境可仅校验已存在的显式安装目录和项目元数据，不得以失败为由扩大扫描范围。

## 数据所有权

- 项目可提交：Provider 代码、脱敏来源清单、固定版本/commit、归档摘要、Schema、示例配置和测试夹具。
- 仅本机保存且不得提交：真实安装绝对路径、下载缓存、解包目录、运行日志与本机覆盖配置。
- GPT-SoVITS 上游源码及安装目录属于外部引擎资产；项目任务默认不得递归读取、diff 或索引。
- 权重、参考音频和角色配置属于 PK-212 Voice Pack，不得写入 Engine Provider 元数据或安装包。

## 依赖与集成

- 依赖 PK-210 已稳定的 TTS/Engine Provider 契约；不依赖 PK-212 实现。
- 定向测试使用 PK-210 的假请求和 PK-212 契约形状的假 Pack 句柄。
- PK-211 与 PK-212 均进入“待集成”后，与 PK-210 一并登记同一轮 PK-900；不得单独宣布整体语音架构完成。

## 实施清单

- [x] 领取任务后同步状态并确认 PK-210 契约已可用。
- [x] 登记经核验的官方来源、固定版本/commit、强摘要和许可证信息。
- [x] 实现只通过明确配置定位外部安装的 Provider；不扫描源码树或磁盘。
- [x] 实现显式、可审计、校验优先、失败不覆盖的获取流程。
- [x] 为协议兼容、超时、重试、取消、错误清洗和安装回滚建立测试。
- [x] 更新 README、模块目录/架构说明、任务工作记录和完成文档门禁。

## 验收标准

- 仓库及 `vendor/` 中没有 GPT-SoVITS 上游源码副本，项目模块导入和普通启动无隐式网络或安装副作用。
- 来源元数据能唯一定位官方固定版本，下载产物必须在解包前通过强摘要校验。
- 模拟下载覆盖成功、网络失败、摘要不符、归档穿越、目标已存在、解包/安装失败；均不执行真实网络和远程脚本。
- 假 HTTP 引擎覆盖 9880 可用、不可用、超时、取消、legacy fallback 和恶意上游错误体，响应与日志不泄露正文或本机路径。
- 旧安装在任何获取失败下保持不变；临时目录只清理由本次操作创建的文件。
- 测试不读取外部 GPT-SoVITS 源码、真实权重、真实参考音频或本机 Voice Pack。

## 工作记录

- 2026-07-21：PK-000 完成任务登记；未获取引擎、未扫描外部源码、未实现 Provider。
- 2026-07-21：独立 PK-211 对话完成领取并改为“进行中”。已确认 PK-210 为“待集成”，`TextToSpeechProvider`、`SynthesisRequest`、`VoicePackRef`、健康/能力、取消与关闭契约可用。本对话只负责不变的 GPT-SoVITS 引擎层：9880 HTTP Provider、官方固定来源与完整性描述、显式受控获取、本机安装登记和启动定位；不负责 Kei 或其他角色的权重、参考音频、Voice Pack，不读取、移动或修改这些资产，不扫描外部引擎源码，不执行真实下载、安装、GPU 服务或远程脚本。混合工作区中的既有修改均视为用户所有，不清理、不暂存、不发布。
- 2026-07-21：新增 `server/features/voice/providers/gpt_sovits/engine.json` 与强校验加载器。上游固定为官方 `RVC-Boss/GPT-SoVITS` release `20250606v2pro` / commit `d7c2210da8c013e81a94bfc7b811a477c99fd506`；分发源是该 release 明确链接的 `lj1995/GPT-SoVITS-windows-package`，固定 revision `fb387b7a65a5441e5e3985f4ab9b721a9d455363`，NVIDIA 50 系归档大小 `8,835,144,925` 字节、SHA-256 `97b4edcd451c42357db7e26e6c1c877ca5d85144fe97beaff6d7005d35bee008`。元数据查询只读取 GitHub/Hugging Face 官方 release/file API，没有下载归档本体。
- 2026-07-21：实现 `GPTSoVITSProvider` 并保留 `TTSClient`/`TTSConfig` 兼容导出。Provider 满足 PK-210 health/capabilities/synthesize/cancel/close，默认只连接 `127.0.0.1:9880`；`auto` 先调用 `api.py` 风格 `POST /`，只对 404 回退 legacy `POST /tts`，也支持固定 `api_py` / `legacy_v2`。Voice Pack 只作为不透明 handle 提供通用参考字段，Provider 不发现、读取或拥有角色资产；超时、连接、非音频和其他上游失败统一转换为有限 `tts_*` 错误，不返回正文、异常文本或路径。
- 2026-07-21：实现固定来源受控获取与本机登记 CLI。生产命令只提供 `status/register/acquire`，不接受 Git URL、下载 URL、命令、BAT/PowerShell、脚本或任意启动参数；获取要求精确确认 engine id。下载进入系统临时目录，先核对精确大小与 SHA-256，再对 zip/可选 7z 执行路径、盘符、穿越、链接/重解析点、文件数、解压大小和压缩比校验，随后在目标同级暂存并原子移动。非空未标记目标拒绝覆盖，匹配 marker 可重复复用，离线只复用显式登记；任何下载、摘要、解包、布局、移动或本机配置提交失败都只清理本次产物，配置提交失败会回滚本次新安装。归档脚本从不执行，marker 固定记录 `scripts_executed=false`。
- 2026-07-21：真实 7z 依赖缺失时明确返回 `extractor_dependency_missing`，不自动运行 `pip`、CUDA/环境安装或外部命令，不伪装获取成功。已有本机 GPT-SoVITS 仅窄范围核对明确根目录、`api.py` 与 `runtime/python.exe` 后登记到忽略的 `server/data/gpt_sovits_engine.local.json`；当前状态为 `registered_existing` / `unverified_existing_install`，表示入口可复用但没有读取源码或用原始 8.8GB 归档验证整个既有目录。
- 2026-07-21：`start_gptsovits.bat` 的用途、9880 端口和总启动顺序不变；PowerShell 启动器改为只读项目 descriptor 与忽略的本机登记，固定解析 `runtime/python.exe` / `api.py` 并执行 `-a 127.0.0.1 -p 9880`。已移除公开绝对安装根、Kei 权重、参考音频和参考文本；缺配置、路径位于项目内、engine id 不匹配或入口缺失均明确失败，启动器不下载、不装依赖、不扫描模型。
- 数据与副作用审计：项目只新增 Provider、固定描述、获取/登记代码、架构说明与假测试；真实绝对根只进入忽略的本机配置和 `README.local.md`。自动测试只在系统临时目录创建微型假 ZIP、假入口、假摘要与假本机配置，HTTP 只用 `httpx.MockTransport`/阻塞测试 transport；没有 clone、真实下载、外网获取、依赖安装、GPU 服务、9880 真实请求、模型加载、权重/参考音频读取、归档脚本执行、Git 暂存、提交、推送或发布。
- 验证记录：通过 `tests/test_gpt_sovits_provider.py`（固定版本、错误来源、摘要不符、中断、非空目录、重复获取、离线复用、不安全归档、解包失败、本机配置提交失败回滚、脚本不执行、health 可用/不可用、API 风格/404 回退、超时/非音频脱敏、取消）、`tests/test_voice_module.py` 与 `tests/test_feature_catalog.py`；相关 Provider/catalog/兼容导出完成 `compileall`。CLI `status` 返回 `registered_existing`、`entrypoints_ready=true`、`unverified_existing_install` 且不暴露路径；`start_gptsovits.ps1` PowerShell AST 语法检查通过。最终“待集成”状态下 `scripts/check_task_docs.py` 通过 9 个门禁任务，`git diff --check` 通过，仅有工作区既有 LF→CRLF 提示。
- 遗留/集成关注：没有执行真实 7z 获取或真实 9880 合成；当前虚拟环境没有可选 `py7zr`，实际受控解包必须由用户显式准备后再运行。现有安装完整性明确未验证；PK-212 仍需提供真实只读 Voice Pack handle。只有 PK-212 也进入“待集成”后，才由 PK-000 将 PK-210/211/212 登记为同一轮 PK-900，当前不得宣称整体语音架构已完成。
- 2026-07-22 根因整改：PK-900 证明旧 `_pack_switch_lock` 只覆盖两项权重请求，合成 POST 在锁外；`activate_voice_pack()` 又在 `CancelledError` 分支直接退出，导致 GPT 已切换、SoVITS 仍旧且 Provider 身份仍指向旧 Pack。根因不是 Registry 文件替换，而是共享 9880 进程状态缺少覆盖“身份确认、两阶段切换、完整合成、选择提交”的统一线性化边界。
- 2026-07-22 并发模型：保留唯一 `GPTSoVITSProvider`/`httpx.AsyncClient` 和唯一共享引擎会话锁，不创建第二套 GPT-SoVITS。合成取得锁后重新读取 Registry 活动 Pack，在锁内完成必要切换与完整音频 POST；选择通过 `activate_voice_pack_transaction()` 在同一锁内完成两项权重和 Registry commit；close 先进入不可逆 closing，取消排队/活动会话，再等待切换回滚或合成退出后关闭 client。重复选择 ready 的同一 Pack 不请求权重端点。
- 2026-07-22 回滚语义：任何权重阶段、Registry commit 的普通失败或任务取消都会在释放会话前用受保护 rollback task 重新设置旧 GPT 与旧 SoVITS；清理完成后原异常或 `asyncio.CancelledError` 继续传播。回滚成功恢复旧 Provider 身份和 `ready`；回滚失败清除身份并进入 `unknown`，health 固定返回 `tts_engine_state_unknown`，不把旧 Pack 假报为可用。一次完整成功选择可从 unknown 恢复。
- 2026-07-22 隔离测试：新增 `tests/test_gpt_sovits_engine_sessions.py`，只用 `httpx.MockTransport`、临时 Registry、微型假 checkpoint/假 WAV 和假路径，确定性覆盖两阶段中途取消、第二阶段失败并成功回滚、回滚自身失败、A 合成阻塞时选择 B、两个 Pack 并发合成、重复选择、Provider close 与切换/合成并发、失败后旧 Pack 合成。首次定向执行与既有 Provider/Registry 测试均通过；完整回归和门禁结果见本任务最终验证记录。
- 2026-07-22 最终验证：在显式不存在的 env/profile/Voice Pack Registry 路径和虚构 Key 下，从头运行共享引擎新测试、`test_gpt_sovits_provider.py`、`test_voice_pack_registry.py`、PK-210 `test_voice_module.py`、PK-200 conversation/profile/consumers、installable modules、feature catalog、dashboard shell、voice calendar/demon intents、daily briefing summary cache 共 13 组，全部退出码 0。首次整组运行在 catalog 既有精确短语断言处停止，保留兼容短语并追加 unknown 说明后，从第一项完整重跑通过。voice/conversation/API/兼容层/相关测试共 54 个 Python 文件 `py_compile` 通过，六个 dashboard JavaScript `node --check` 与 GPT-SoVITS 启动脚本 PowerShell AST 通过。未运行真实 `test_tts_gptsovits.py`、真实 9880、下载、模型、GPU 或参考音频。
- 2026-07-22 最终门禁：`scripts/check_task_docs.py` 通过并输出 `task documentation gate passed: 9 gated task(s)`；`git diff --check` 退出码 0，仅有混合工作区既有 LF→CRLF 提示；本次 11 个明确源码/测试/文档路径行尾空白检查无匹配。真实 `.env`、LLM profile、记忆、好感度、GPT-SoVITS 本机登记、Voice Pack 本机注册表/runtime 和输出路径的 Git 状态复查均无输出。未暂存、提交、推送或发布。
- 2026-07-22 PK-000 最终复核：错误来源/摘要不会留下半安装或半登记状态，归档内容未执行；共享引擎会话、切换失败回滚和离线状态均独立复现通过。

## 完成文档门禁

任务进入“待集成”或“已完成”前必须全部勾选；不适用项也必须写明原因。

- [x] TASK_RECORD — 已记录固定来源、Provider/获取/启动接口、副作用、验证、未验证既有安装与 PK-212 集成遗留。
- [x] TASKS_BOARD — PK-000 最终复核通过后已同步为“已完成”，名称、P1 与 `PK-210` 依赖不变。
- [x] PUBLIC_README — 已更新 Provider/API 风格、固定来源/摘要、本机登记、显式获取、启动兼容、安全边界、测试与限制。
- [x] MODULE_CATALOG — 已登记 PK-211 `tts-sidecar`、9880 风格、外部数据所有权、显式网络副作用和失败模式。
- [x] ARCHITECTURE_DOCS — 已新增 `gpt-sovits-engine.md` 并同步 voice/模块化单体的 Provider、来源、事务、启动与角色资产边界。
- [x] LOCAL_README — 已窄范围核实现有安装根和固定入口并登记；绝对路径只写入忽略文件，未扫描源码或读取模型。
- [x] AGENT_RULES — 已强化“普通 agent 只读 Provider/descriptor/无路径状态，外部引擎默认不扫描”及禁止任意来源/命令/脚本规则。
- [x] VALIDATION — 已记录全假源/假 HTTP/临时目录测试、共享引擎竞态回归、编译、CLI 状态、PowerShell 语法和 `git diff --check` 结果。

## 2026-08-11 现有引擎权重切换兼容整改

- 真实运行故障表现为：`voice@1.0.5` 已恢复装载，但首次 QQ 语音请求在选择
  `kei@1.0.0` 时把 Provider 置为 `unknown`，随后
  `voice_profile_ready=false`、`voice_reply_state=encoding_unavailable`，QQ 按契约只发
  文字。只读取本机 9880 的公开 OpenAPI 后确认，当前已登记引擎提供组合
  `/set_model`，而 Provider 仍固定调用两个旧版权重接口；未读取外部引擎源码、模型、
  权重、参考音频或本机绝对路径。
- `GPTSoVITSProvider` 现优先调用一次组合 `/set_model`；仅在精确 404/405 时回退旧版
  `/set_gpt_weights` 与 `/set_sovits_weights`。5xx、超时、取消和其他故障继续 fail
  closed，不会尝试第二套写入；成功风格只在当前实例内缓存，不进入响应或持久状态。
- 永久 fake HTTP 回归覆盖组合接口成功、404 后旧接口兼容、组合接口 500 时零回退；
  `test_gpt_sovits_provider.py`、共享引擎 session、Voice Pack Registry、voice module 与
  installable voice module 均退出 0。
- 通过正式 supervisor 将 Core generation 从 12 重启至 13，再经现有 Voice Pack
  选择 API 恢复 `kei@1.0.0`。只读 QQ readiness 随后为
  `reply_with_voice=true`、capability `available`、`voice_profile_ready=true`、
  `voice_reply_available=true`、state `available`。本次没有调用 synthesize、没有发送
  QQ 消息，也没有读取或打印秘密及模型路径；真实语音发送仍由用户显式消息验证。
- 本轮属于已完成 PK-211 的回归修复，任务与总板重新置为“待集成”；在真实 QQ
  语音验证和新的独立累计验收前，不生成或发布新安装包，不提前恢复“已完成”。

## 2026-08-11 QQ 文字成功但真实语音未产生的运行态复查

- 用户在 QQ 私聊中确认普通文字回复正常，但启用“QQ 回复同时发送语音”后仍没有语音消息。只读运行态复查确认 QQ 配置、管理员声明的媒体能力、`qq_c2c_voice_v1`、Silk encoder 与开关均为 ready；失败发生在 QQ 上传之前。
- 本机受控调用 `POST /api/v1/voice/synthesize` 实际返回 `502 {"code":"audio_invalid"}`，另一次调用在上游推理等待中超时。直接检查 9880 响应的安全元数据时，曾得到只有 `44` 字节 WAV 头、`0` 音频帧的空结果；同一参考音频经 `/change_refer` 加载返回 `200`，但中文和日文的最小推理请求均由上游提前断流（`RemoteProtocolError`）。没有保存、播放或发送测试音频。
- 对照固定官方 commit `d7c2210da8c013e81a94bfc7b811a477c99fd506` 的 `api.py` 后确认，该引擎同时正式支持 `POST /` JSON、`GET /` query 以及标准语言码 `ja`/`zh`；因此没有保留基于 OpenAPI request-body 展示不完整而产生的 GET/本地化语言猜测改动。Provider 继续使用冻结的 `POST /` 契约。
- Provider 保留本轮已验证的 `/set_model` 优先、仅 404/405 回退旧拆分权重端点；同时仅允许固定的 api.py 生成参数，并把 Voice Pack 的 `speed_factor` 映射为上游 `speed`，防止生成参数覆盖正文、语言、参考音频等核心字段。`test_gpt_sovits_provider.py`、共享 engine session、Voice Pack Registry、voice module、installable voice module 与 conversation consumer 定向回归均通过。
- 当前阻断位于外部 GPT-SoVITS `StreamingResponse` 的模型推理生成器。上游没有日志 API，当前 Windows Terminal 使用 ConPTY，进程与父 PowerShell 均无法通过只读 Console API 获取缓冲区；必须取得 GPT-SoVITS 启动窗口中本次推理后的末尾异常堆栈，才能区分 CUDA/模型版本/权重配对/张量形状等真实原因。未取得该证据前不得生成或发布新包，也不得声称 QQ 语音已修复。

## 独立对话启动提示

```text
领取 PK-211“GPT-SoVITS Engine Provider 与受控获取”。先完整阅读项目启动文件、
PK-210/PK-211 任务说明和相关架构文档，检查混合工作区。只实现符合 PK-210
契约的 GPT-SoVITS Provider、官方固定来源元数据和显式受控获取。不要递归扫描
GPT-SoVITS 源码，不要放入 vendor，不要执行远程脚本，不要下载真实资源进行
自动测试，不要读取或移动真实权重/参考音频。所有获取测试使用本地模拟归档和
模拟下载；如需改变 PK-210 契约，先记录并交回 PK-000。
```

## 2026-07-30 PK-011 sidecar 可安装化增量

### 边界与产物

- 新增 `package_source/manifest.json`，模块身份固定为
  `gpt_sovits_engine_provider@1.0.0`、类型为 `sidecar`，依赖 PK-210 的
  `voice` 模块，adapter 固定为 `gpt_sovits_provider`。manifest 不提供命令、
  可执行文件路径、URL、环境覆盖或 shell，面板不声明/冒领任何业务 API namespace。
- 新增路径无关 `config.schema.json`。只声明固定 engine id、`auto/api_py/legacy_v2`
  API 风格、loopback `127.0.0.1:9880` 和“不随包安装”的引擎状态枚举；没有本机
  登记、绝对安装根、角色模型、权重、参考音频、`.env` 或秘密。
- 新增动态面板 `dashboard/index.js`。它只消费 PK-100 提供的只读
  `context.module`，显示 Provider 包版本、生命周期、最近 adapter 检查/操作和
  “模块安装不等于引擎安装”的边界；不发网络请求、不下载、不启动进程。
- 新增确定性 `package_builder.py`。ZIP 使用固定时间、权限、顺序、无压缩存储和
  UTF-8 LF，只允许 manifest、Schema、面板、Project Kei 的
  Provider/descriptor/受控获取/adapter 源码与固定 `engine.json`。包不包含
  GPT-SoVITS 上游源码、runtime、CUDA/Python 依赖、模型、权重、参考音频、本机
  登记、绝对路径、远程脚本、BAT/PowerShell、`.env`、状态、缓存或 `vendor/`。
- 新增 trusted `GPTSoVITSSidecarAdapter` 与
  `register_gpt_sovits_sidecar(manager)` 入口，直接消费 PK-010 已冻结的
  `ModuleManager.register_sidecar_adapter()`，无需扩展公共 sidecar 契约。
  adapter 完整实现 `deployment_readiness/start_deployment/stop_deployment/
  is_deployment_healthy`，只消费 Core 构造的 `SidecarDeploymentDescriptor`；
  不从 manifest、包内 descriptor 或前端输入读取命令、cwd、env、启动参数或任意
  引擎路径。
  adapter 先精确比对包内与 Core 固定 descriptor，只读取忽略的本机登记并窄范围
  检查 `runtime/python.exe`、`api.py`；既有 9880 健康时只附着，不取得进程所有权。
  需要启动时只用参数数组和 `shell=False` 执行固定入口，不接受包或用户传入命令。
  stop 只终止本 adapter 创建的进程，不终止既有外部服务，不删除本机登记、外部
  引擎目录、模型、权重或参考音频。
- 安装/启用不调用 `acquire`。无登记、固定入口缺失、进程失败或 health 超时时，
  adapter 只返回脱敏稳定错误，ModuleManager 将模块标记为失败；Core、PK-210
  voice 与文字降级继续可用。归档获取仍必须由用户独立、精确确认固定 engine id
  与 SHA-256，且永不执行下载内容中的安装脚本或自动安装 Python/CUDA/依赖。

### Release 交接

- Release fragment：`release/official-release-fragment.json`。
- 固定 tag：`module-gpt-sovits-engine-provider-v1.0.0`。
- 固定 asset：`gpt_sovits_engine_provider-1.0.0.zip`。
- 确定性 Catalog 交接条目：`release/official-catalog-entry.json`；最终 ZIP
  `77,042` 字节，SHA-256
  `c376b8c849f1ee8877f3ce5228601e833dafd30697aa8e0987d854bd8939981f`，
  根 manifest SHA-256
  `77108411294339b6a66e7377123aff05313543368782cdd70c92ee69be1f18a4`。
- 本对话不修改共享 `server/core/modules/**` 或官方 Catalog，不创建 Release、
  不上传资产。PK-000 串行装配时只需在进程级 ModuleManager 上调用已导出的
  `register_gpt_sovits_sidecar()`，再合并上述 fragment/entry；生产登记调用未在
  本并行工作窗口越权写入共享 service/API。

### 测试与回归

- 新增 Provider 专属
  `tests/test_installable_package.py`，全部使用 `TemporaryDirectory`、临时
  ModuleManager/registry/runtime/data、fake engine 入口、fake process、fake
  health、fake downloader、微型 fake ZIP 和 `httpx.MockTransport`。覆盖两次构建
  字节/摘要一致、精确包内容、无引擎安装后启用清晰失败、模块摘要错误无半状态、
  引擎摘要错误/下载中断无半安装或半登记、Provider fake 9880 会话、安装/启用/
  重复 start/停用/卸载/重装、重复安装拒绝、既有 9880 不被停止，以及外部模型/
  参考音频哨兵和本机登记不删除。
- PK-000 串行装配复核发现 legacy adapter 会先被 Core 归为
  `legacy_healthcheck/ready`，随后因缺登记在 start 阶段失败并误记 `broken`。
  deployment 整改后，缺登记在安装/配置检查阶段即返回
  `configuration_missing(engine_registration)`；enable 在启动进程前抛
  `SidecarReadinessError`，状态稳定为 `needs_configuration`。登记 JSON 损坏映射
  `deployment_invalid`，包内固定 descriptor 异常映射 `package_tampered`，固定
  `runtime/python.exe`/`api.py` 缺失映射 `entrypoint_missing`；三者均为冻结的
  `unavailable`，不返回绝对路径、登记正文或异常文本。
- 专属测试、原 `tests/test_gpt_sovits_provider.py`、PK-010
  `tests/test_installable_modules.py`、PK-210 `tests/test_voice_module.py` 和
  `tests/test_voice_calendar_intents.py` 均通过；面板 `node --check` 和新增 Python
  文件 `py_compile` 通过。没有真实 clone、下载、GitHub、9880、GPU、模型、权重、
  参考音频、依赖安装、远程脚本或付费调用。
- PK-190 共享回归暴露 adapter 模块级
  `Callable[[list[str], Path], ...]` 在项目旧解释器导入时立即求值。已在 PK-211
  专属路径最小改为 `typing.List[str]`；项目 Python 3.8.20 实际 import/py_compile
  与 calendar 回归通过，全局 Python 3.12.7 `py_compile` 通过。该全局解释器缺
  FastAPI/Pydantic 对应依赖，未伪称完成 3.12 全包 import；本机未安装可调用的
  3.10/3.11/3.13。已通知 PK-210 与 PK-000 在共享环境重跑矩阵。
- 最终复跑：专属包测试、既有 Provider/共享引擎会话、PK-010 生命周期、PK-210
  voice 与 calendar 六组脚本均退出 0；新增 Python 文件 `py_compile` 与面板
  `node --check` 退出 0；本次 deployment 整改最终
  `scripts/check_task_docs.py` 通过 24 项门禁，
  `git diff --check` 退出 0，仅输出混合 Windows 工作区既有 LF→CRLF 提示。
  当前两个可用解释器均未安装 Ruff，因此未伪称 Ruff 通过，也未为测试静默安装
  dev 依赖。

### 本增量完成文档门禁

- [x] TASK_RECORD — 已记录包内容、adapter 所有权、无引擎降级、外部数据保留、
  Release 摘要、验证和共享装配交接。
- [x] TASKS_BOARD — PK-000 已把 PK-211 置为“进行中”并补
  PK-010/PK-100/PK-210 依赖；本对话按授权不修改冻结的 `TASKS.md`，仅将本任务
  文件置为“待集成”。
- [x] PUBLIC_README — 本并行批不适用：`README.md` 由 PK-011/PK-000 串行装配，
  本任务没有写入共享文件；准确用户边界已写入本记录与 `release/README.md`。
- [x] MODULE_CATALOG — 本并行批不直接改共享 Catalog；已交付通过固定官方
  owner/repository/tag/asset 形态的 fragment 和含实际摘要/字节数的条目。
- [x] ARCHITECTURE_DOCS — 本并行批不适用：共享模块架构文档冻结；实现只消费
  PK-010 已冻结 sidecar adapter 契约，无公共契约扩展。
- [x] LOCAL_README — 不适用：没有改变或读取真实本机路径、登记、引擎、模型、
  权重或参考音频。
- [x] AGENT_RULES — 不适用：共享 `AGENTS.md` 冻结，且既有“外部引擎默认不扫描”
  和任意来源/命令/脚本禁令没有变化。
- [x] VALIDATION — 已记录全 fake/临时测试、确定性 Release、导入回归、编译、
  JavaScript 语法、共享契约回归和环境限制；最终门禁在交付前重跑。

## 2026-08-08 本机已有引擎目录选择增量

### 后端边界与精确 API

- 新增 `local_selection.py`：只有显式选择动作才调用项目固定的 Windows 原生目录
  对话框。浏览器不能枚举文件系统，也不能提交 path、URL、command、cwd、env、
  PowerShell/BAT 或脚本；取消返回 `action=cancelled` 且零写入。
- 选择后只检查用户明确给出的目录、固定 `api.py`、`runtime/python.exe` 和可选
  `.project-kei-engine.json`，不递归列目录、不读取/执行源码与安装脚本，不触碰
  模型、权重、参考音频或 Voice Pack。所选根、根的祖先链和固定入口链出现
  symlink/junction/reparse point 时拒绝。缺少 marker 的合法现有安装只登记为
  `registered_existing` / `unverified_existing_install`；只有完全匹配固定来源、
  release/revision、SHA-256 且 `scripts_executed=false` 的 marker 才显示
  `installed_verified` / `sha256_verified`。
- 同一进程内选择使用非阻塞锁；并发点击在打开第二个选择器前返回
  `selection_in_progress`。完整校验完成后才复用 `LocalEngineRegistry.save()` 的
  临时文件、fsync、`os.replace` 原子提交；校验或保存失败保留旧登记和所选目录。
- PK-100 精确接缝：`GET /api/v1/gpt-sovits-engine/status` 只返回
  `engine_id/registration_state/integrity_status/entrypoints_ready/display_name/
  selection_in_progress/can_select_existing`；`POST
  /api/v1/gpt-sovits-engine/select-existing` 只接受真实 loopback、精确受信控制台
  Origin、无 query 和空请求体，响应另含 `action=cancelled|registered`。
  `display_name` 仅为清洗、截断后的末级目录名，不返回绝对路径或异常正文。
- 新增 `selection_router.py` 与公开工厂 `create_gpt_sovits_engine_router(service)`；
  最终共享窗口已由 `InstalledModuleHost` 使用固定 descriptor、固定本机 Registry
  路径和项目内置 picker 创建唯一 `LocalEngineSelectionService`，并由 `api.py`
  在公共路由装配阶段挂载 router。浏览器和 manifest 均不能构造 picker、Registry
  路径或 descriptor。PK-210 的 voice runtime start 契约、ASR 与 PK-212 资产
  所有权不变。

### 面板、包与验证

- Provider 动态面板新增“选择/重新选择已有引擎目录”按钮和脱敏状态；只调用上述
  两个自有 API。manifest 仅新增 `/api/v1/gpt-sovits-engine` namespace；模块仍
  不包含外部引擎、runtime、CUDA、模型、权重、参考音频、本机登记、绝对路径、
  远程脚本、`.env` 或 `vendor`，安装模块仍不等于安装引擎。
- 首次交接误沿用了已发布的 `1.0.0` 身份，PK-000 复核后已按不可变发布规则整改：
  新包固定为 `gpt_sovits_engine_provider@1.0.1`、tag `modules-2026.08.08`、asset
  `gpt_sovits_engine_provider-1.0.1.zip`；旧 `1.0.0`/旧 tag/旧 asset 不覆盖。
  最终确定性 ZIP 为 `93,850` 字节，SHA-256
  `27a39f7ec930562a152c949d059260ae9ecb428589856f618c6b8d67a36bc5f6`；manifest
  SHA-256 为 `5a50239a19b552e798079addaf507db5bd878ccfc1a81369cc9cb356b3c45a79`。
  release fragment/entry 已同步，但本任务不修改官方 Catalog，不创建、上传或发布
  Release；由 PK-010 串行合并最终条目。

## PK-000 本机目录选择功能不可变版本收口（2026-08-12）

- 本机引擎目录选择新增 `provider/local_selection.py`、`provider/selection_router.py` 和对应 dashboard
  接缝后，确定性包内容已不同于已发布的 `1.0.1`；按不可变发布规则提升为 `1.0.2`，不覆盖旧资产。
- 两个独立系统临时目录构建 `gpt_sovits_engine_provider-1.0.2.zip` 均为 `98648` bytes，SHA-256
  `3971228df9f098582076dc551d5c22d4be610a059102878f35e3465e33391c6e`；规范 manifest SHA-256
  `1e1eafae166ac03adf1dfc06d66ccbfb94ea72c5baa00fb578630ca4baf0584e`。
- ZIP 共 11 项，不含 GPT-SoVITS 上游源码、模型、权重、参考音频、`.env`、runtime、vendor、
  `node_modules`、绝对用户路径或私钥。
- 新增 `tests/test_local_selection.py`，仅用 fake picker、临时微型引擎树、临时
  Registry、ASGITransport 与注入失败，覆盖取消零写入、未验证/固定标记状态、
  恶意结构、重解析点、并发选择、保存失败保留旧登记、loopback/Origin、空 POST、
  path/query/command/URL 拒绝与响应路径脱敏。没有打开真实选择器、读取真实引擎、
  访问网络、启动 9880/GPU、执行脚本或触碰 Voice Pack。
- 新增生产装配永久回归 `tests/test_gpt_sovits_engine_selection_assembly.py` 并登记
  默认离线测试清单。它导入真实 `api.app`，断言两个路径存在且唯一；用禁止 I/O
  哨兵证明远端、恶意/缺失 Origin、query 和 body 均在 picker/Registry 前拒绝；
  再用临时 Registry 与取消 picker 证明 GET 无 Origin 可用、取消零写、响应无绝对
  路径，并证明没有引擎登记时 Core 根路由仍正常启动。
- 实际验证：新目录选择脚本、生产装配永久回归、原 sidecar 包脚本、
  `test_gpt_sovits_provider.py`、`test_gpt_sovits_engine_sessions.py`、最新
  `test_voice_runtime_control.py`、`test_dashboard_shell.py` 与
  `test_module_host_assembly.py` 均退出 0；90 个测试文件 inventory 门禁通过。
  项目旧解释器与 Python 3.12.7 `py_compile`、面板 `node --check`、26 项任务文档
  门禁和精确范围 `git diff --check` 通过。项目旧环境未安装 pytest、Python
  3.12 环境未安装 Ruff，均明确记录且未静默安装。最终共享挂载与不可变版本整改
  完成后状态保持“待集成”，交 PK-900 复核；未暂存、提交、推送、创建 Release
  或清理混合工作区。

## 可安装 voice 请求类型身份接缝整改（2026-08-11）

- 真实运行复现中，GPT-SoVITS 的 `/set_model` 与 `POST /` 均返回 200，直接 Unicode
  请求能得到有效单声道 WAV；但 Core 的 `POST /api/v1/voice/synthesize` 稳定返回
  `502 audio_invalid`。根因不是 9880、模型或 Silk encoder，而是可安装 `voice`
  backend 在隔离命名空间中拥有一套字段相同但类身份不同的 `SynthesisRequest` /
  `VoicePackRef`。Provider 原先用宿主类做 nominal `isinstance`，误落入 legacy 字符串
  兼容路径并返回原始 `bytes`，安装版 VoiceService 因期望 `AudioResult` 而拒绝结果。
- `GPTSoVITSProvider` 现只对固定公开字段执行严格结构校验，并重建宿主侧受信
  `SynthesisRequest`、`SynthesisTextSegment` 与 `VoicePackRef`；不接受任意映射、命令、
  路径、URL 或额外字段，legacy 字符串入口保持兼容。永久回归使用名义类型不同的隔离
  fixture，证明 Provider 返回 `AudioResult` 而不是原始字节。
- 本机通过 ModuleManager 正式 update 流程装入未发布候选 `voice@1.0.7`，没有直接修改
  runtime/registry；受控重启到 Core generation 17 后，真实本机调用
  `/api/v1/voice/synthesize` 返回 200、`audio/silk`、2375 bytes、duration 786 ms、
  `X-Kei-Audio-Final=true`、profile `qq_c2c_voice_v1`。QQ 配置只读快照同时为
  `reply_with_voice=true`、`qq_media_upload_capability=available`、
  `voice_profile_ready=true`、`voice_reply_available=true`。
- 定向脚本 `test_gpt_sovits_provider.py`、`test_voice_module.py`、
  `test_voice_installable_module.py` 与相关 `py_compile` 通过。本轮未发送真实 QQ 消息，
  未读取或输出秘密、模型、Voice Pack、参考音频、个人状态或 runtime 内容；未提交、
  推送或发布。PK-211 保持“待集成”，真实 QQ 上传/发送需由一条新的用户消息另行验收。
