# PK-210 — 语音公共契约与编排

- 状态：待集成
- 优先级：P1
- 所属模块：`voice`
- 依赖任务：PK-001、PK-010、PK-100、PK-200
- 负责路径：`server/features/voice/`、`server/services/asr_client.py`、`server/services/tts_client.py`、`server/services/voice_pipeline.py`、`server/api.py` 中语音装配与兼容路由、语音临时输出清理、对应测试与文档
- 当前对话：2026-08-10 PK-000 冻结 QQ 回复专用合成与 readiness 增量；只交付 voice 专属合成/PCM/encoder 公共契约、确定性包、隔离测试和交接，不实现 QQ 上传或权限探测

## 总控定位

PK-210 是 Project Kei 的语音公共契约与编排任务，只负责把音频输入依次交给 ASR Provider、PK-200 对话服务和 TTS Provider，并管理版本化 HTTP 接口、流式事件、降级结果和临时文件生命周期。

GPT-SoVITS 引擎的来源、固定版本、完整性与受控获取归 PK-211；角色权重、参考音频、Voice Pack Schema、注册表与切换归 PK-212。PK-211 与 PK-212 彼此不直接依赖、也不得直接导入对方实现，只通过 PK-210 的公开契约协作。

```text
PK-001 + PK-200 -> PK-210
PK-210 -> PK-211
PK-210 -> PK-212
PK-210 + PK-211 + PK-212 -> 同一轮 PK-900 集成验收
```

本次登记不启动新的 PK-900 批次。三项独立任务均完成并进入“待集成”后，再由 PK-000 将批次明确登记为 `PK-210 + PK-211 + PK-212`。

## 目标

- 在 `server/features/voice/` 建立请求/响应模型、Provider 协议、编排 service 与 router 的明确边界。
- 形成可注入、可替换的 `ASRProvider`、`ConversationProvider` 和 `TTSProvider` 契约；PK-200 是文字对话与 LLM Profile 的唯一所有者。
- 新增 `/api/v1/voice/*`，同时保留现有 `/voice/*` 的请求、响应和音频访问兼容。
- 保留同步语音对话和 NDJSON 流式语音对话，明确 `reply`、`audio_part`、`done`、`error` 终止语义。
- 对 ASR、对话或 TTS 缺失和失败给出稳定、可观察且不泄露上游正文的降级结果。
- 在正常完成、异常、取消和客户端断开时清理由本次请求创建的临时上传与合成文件。

## 不在本任务内

- 不下载、安装、更新、扫描或内嵌 GPT-SoVITS 上游源码；不创建 `vendor/` 副本。
- 不管理 GPT-SoVITS 的固定版本、commit、下载完整性或安装目录；这些归 PK-211。
- 不定义角色模型包格式，不导入、移动、复制、删除或切换 Kei 权重与参考音频；这些归 PK-212。
- 不实现 LLM Provider、模型 Profile、角色提示或对话历史语义；这些继续归 PK-200。
- 不把 Persona Pack/角色人格包混入 Voice Pack；Persona Pack 如需建设，应由 PK-000 另立后续任务。
- 不迁移每日情报、日历、斩妖、复盘、提醒等业务规则。语音兼容入口只能调用其公开 Provider/service，不得读取其私有状态。
- 不新增常驻进程、端口、账户、多用户、会话持久化或可安装业务模块。

## 公共契约

### Provider 边界

- `SpeechToTextProvider.transcribe(request) -> Transcript`：接收受限大小的音频与语言/VAD/超时选项，返回文本、语言、置信信息和只含 `start/end/text` 的规范化分段；不得暴露上游原始错误体。
- `ConversationProvider.chat(message, *, request_id) -> ConversationReply`：适配且只调用 PK-200 公开 `ConversationService.chat()`，返回文字、情绪与时间戳；voice 不复制 LLM Profile、历史或角色提示。
- `TextToSpeechProvider.synthesize(request, voice_pack) -> AudioResult`：接收文本、情绪、超时和已解析的 Voice Pack 引用；不得自行寻找本机模型目录。
- `VoicePackRef` 是 PK-210 定义的最小只读跨任务引用，只包含 pack ID、版本、引擎 Provider key 和经过 PK-212 校验的本地句柄；不得包含模型内容、密钥或可回传的绝对路径。
- Provider/Resolver 均公开 `health`、`capabilities`（含默认超时）、取消和关闭；所有实现都可由测试替身注入。模块导入和应用启动不得主动连接 ASR、TTS、LLM 或网络。

### HTTP 接口矩阵

| 版本化接口 | 兼容接口 | 契约 |
|---|---|---|
| `POST /api/v1/voice/chat` | `POST /voice/chat` | multipart 音频输入；返回识别文本、回复文本、情绪、音频引用、时间戳和阶段耗时 |
| `POST /api/v1/voice/chat/stream` | `POST /voice/chat/stream` | `application/x-ndjson`；顺序发送 `reply`、零到多个 `audio_part`、一个 `done`，失败时以一个已清洗的 `error` 终止 |
| `GET /api/v1/voice/audio/{filename}` | `GET /voice/audio/{filename}` | 只读取 voice 临时输出根目录内的安全 `.wav` 文件名，拒绝路径穿越 |
| `GET /api/v1/voice/health` | `GET /voice/health` | 显式读取 Provider 健康与能力；缺失项结构化报告，不返回路径或上游正文 |

新旧入口必须委托同一编排 service，不得维护两套 ASR、对话、TTS、错误或清理规则。legacy 流中的音频 URL 可继续使用 `/voice/audio/*`；版本化流应返回 `/api/v1/voice/audio/*`，二者引用同一受控文件。

### 错误与降级

- ASR 失败：不调用 PK-200 或 TTS，返回稳定的识别阶段错误。
- PK-200 失败：不调用 TTS，保留 PK-200 已定义的错误类别，不复制上游错误正文。
- TTS 失败：已成功取得的文字回复可以作为明确的文本降级返回，但不得伪造音频成功或留下半成品。
- 流式响应在客户端断开或任务取消时停止后续 Provider 调用并执行清理；每次请求最多产生一个终止事件。
- 日志和 HTTP 响应不得包含 API Key、系统提示、上游完整错误体、绝对模型路径、参考音频内容或用户上传音频字节。

## 进程与启动兼容

- Project Kei API 保持 `8000`，ASR 保持 `8010`，GPT-SoVITS TTS 保持 `9880`；不得为 Provider 或 Voice Pack 新增端口。
- `server/start_all_services.bat`、`server/start_asr.bat`、`server/start_gptsovits.bat` 的既有用途和启动顺序保持兼容。
- 启动器可以依据 PK-211 的公开 Provider 元数据定位外部引擎，但不得在普通启动时下载代码、执行远程脚本或扫描引擎源码。

## 数据所有权

- voice 只拥有单次请求的上传临时文件、合成临时文件和清理元数据；不得把音频内容写入对话 Profile、Voice Pack 注册表或其他业务状态。
- `server/output/`、生成音频和上传临时文件均为本地运行态，不得暂存或提交。
- GPT-SoVITS 源码/安装树归外部引擎，PK-211 只管理项目内的来源与适配元数据。
- Kei 权重、参考音频、模型配置和 Voice Pack 注册表归 PK-212 管理的本机资产边界；PK-210 只接收不透明引用。
- 不得读取、打印、移动、覆盖或打包真实模型、参考音频、`.env`、LLM Profile、长期记忆或其他个人数据。

## 实施清单

- [x] 领取任务后同步 `TASKS.md` 与本文件状态为“进行中”并记录独立对话用途。
- [x] 在 `server/features/voice/` 定义模型、Provider 协议、service 与 router，保持 `server/api.py` 只做装配和兼容入口。
- [x] 将新旧 HTTP 路由委托同一 service，并验证旧字段和 NDJSON 事件兼容。
- [x] 通过 PK-200 的公开 Conversation Provider 调用文字对话，不直接持有或修改 LLM Profile。
- [x] 为错误分类、文本降级、取消/断连和临时文件清理建立确定性规则。
- [x] 保持 8010/9880 与既有启动器兼容，不触碰外部引擎源码或真实 Voice Pack。
- [x] 更新 README、模块目录、架构说明与工作记录，并运行完成文档门禁。

## 验收标准

- 新旧三组接口共用同一编排 service，旧 `/voice/*` 行为和 8010/9880 启动方式有回归证据。
- 单元/接口测试使用假 ASR、PK-200 fake Conversation Provider、假 TTS 和假 Voice Pack；测试期间没有真实网络、真实服务、模型加载或付费 LLM 调用。
- 同步与流式路径覆盖 ASR 失败、PK-200 失败、TTS 失败、保存音频失败、客户端取消/断开和并发请求隔离。
- TTS 失败时文本降级明确；任何失败都不返回伪造音频，不泄露上游错误体或本机敏感路径。
- 测试证明每个请求只清理由它创建的临时文件，不删除并发请求或用户已有文件。
- PK-211 和 PK-212 能分别用假 Engine Provider、假 Voice Pack 接入相同契约，且无需互相导入。
- 实际测试命令、结果、接口副作用和遗留事项写入本文件后，任务才可进入“待集成”。

## 工作记录

- 2026-07-21：PK-000 完成架构登记，将原“ASR、TTS 与语音链路”拆为 PK-210 公共契约与编排、PK-211 Engine Provider、PK-212 Voice Pack；未实现业务代码，未启动集成批次。
- 2026-07-21：独立 PK-210 对话完成领取并改为“进行中”。本对话只迁移 Project Kei 内部语音公共层：Provider/Voice Pack Resolver 契约、ASR → PK-200 conversation → TTS 编排、`/api/v1/voice/*` 与 `/voice/*`、同步/NDJSON、上传限制、结构化降级和请求级临时文件清理。保留 8010、9880 与现有启动器；不修改 PK-200/PK-211/PK-212 内部实现，不扫描外部引擎，不读取或移动真实 Voice Pack/模型资产，不运行真实服务、LLM 或音频合成。混合工作区中的既有修改均视为用户所有，不清理、不暂存、不提交。
- 2026-07-21：建立 `server/features/voice/` 的 `models/contracts/errors/service/router/storage/providers` 边界。四个可注入协议公开健康、能力、默认超时、操作、取消和关闭；`VoicePackRef.handle` 仅为进程内不透明值且不参与公开序列化。8010/9880 HTTP 适配只返回规范化结果或有限 `stage/code/message/retryable`，不返回上游正文、异常链或本机路径。
- 2026-07-21：主应用以 `ConversationServiceProvider` 注入 PK-200 `ConversationService.chat()`；新生产链路不再使用 `DialogueManager`、原始 LLM client、profile 或业务私有状态来取得文字回复。TTS 与 Pack 缺失/超时/失败返回 `mode=text_only`、`degraded=true` 和结构化错误；ASR 缺失/失败/超时/空或超长识别在 PK-200 前终止，conversation 失败在 TTS 前终止。
- 2026-07-21：`router.py` 同时装配版本化和 legacy 的 health/chat/stream/audio 路由。上传要求批准 MIME 与扩展名、默认 16 MiB、64 KiB 有界读取；响应保留旧字段并增加明确降级字段，音频引用统一为对应 namespace 的 URL。NDJSON 为 `reply -> audio_part* -> done` 或一个清洗后的 `error`，终止事件唯一。
- 2026-07-21：`storage.py` 为每个请求创建 UUID 隔离暂存目录，全部分段先完整合成再原子发布。暂存目录在成功、失败、取消和断连后都删除；失败/流式中断还删除当前请求已发布但未完整交付的文件，不触碰并发请求或既有输出。完整成功输出留在忽略的 `server/output/voice_replies/` 并继续受现有保留清理管理。
- 2026-07-21：`server/services/asr_client.py`、`tts_client.py`、`voice_pipeline.py` 已缩为兼容导出，旧 Python `VoicePipeline` 位于 `features/voice/legacy_pipeline.py`，仅保留历史调用和日历/斩妖意图辅助；生产 HTTP 只使用新 `VoiceService`。`api.py` 移除内置 Kei 引擎绝对路径、参考音频和参考文本默认值，只接受显式环境配置；没有修改启动器、PK-200、PK-211 或 PK-212 内部实现。
- 数据与副作用审计：自动测试只在系统临时目录写入微小假 WAV 并自动清理，使用假 ASR、假 TTS、假 conversation service 与假 Pack Resolver；没有读取真实 `.env` 值、LLM profile、模型、权重、参考音频或个人状态，没有访问网络、启动 8000/8010/9880、调用真实 LLM/ASR/TTS、暂存、提交或推送。
- 验证记录：通过 `tests/test_voice_module.py`（fake/MockTransport/临时目录，覆盖正常同步与流式、health/capabilities、ASR/TTS 缺失、ASR/conversation/TTS 超时、异常响应、空识别、文字降级、分段半失败、流中断与取消、上传类型/大小/有界读取、临时清理、并发隔离、新旧 URL/字段兼容、PK-200 adapter 和路径/正文净化）、`test_conversation_consumers.py`、`test_conversation_module.py`、`test_feature_catalog.py`、`test_voice_calendar_intents.py`、`test_voice_demon_intents.py`。相关 `features/voice`、兼容导出、`api.py`、测试完成 `compileall`；任务文档门禁和 `git diff --check` 通过。API route 导入检查使用不存在的临时 env/profile 与虚构 Key，只观察到既有 focus runtime 的受限沙箱 `PermissionError` 被应用隔离逻辑跳过。未运行会连接真实服务的 `test_asr_upload.py`、`test_tts_gptsovits.py`、`test_voice_chat.py`、`test_mic_voice_chat.py` 或任何真实/付费手工请求。
- 遗留/集成关注：PK-211 应以本契约替换 9880 compatibility Provider 并负责上游来源/版本；PK-212 应替换无 I/O 的 `StaticVoicePackResolver` 并提供真实 `VoicePackRef`，两者不得改动 PK-210 编排或互相导入。当前 `legacy_pipeline.py` 只为既有 Python 消费者保留日历/斩妖等历史辅助；生产 `/api/v1/voice/*` 与 `/voice/*` 均严格使用新 `VoiceService` 和 PK-200 conversation adapter。
- 2026-07-22 PK-000 最终复核：无引擎、无 Voice Pack、错误摘要与离线降级下 Core 可启动；完整 fake 链路只经公开 Provider 契约协作，未加载 GPT-SoVITS 上游内部代码。

## 完成文档门禁

任务进入“待集成”或“已完成”前必须全部勾选；不适用项也必须写明原因。

- [x] TASK_RECORD — 已记录实际 Provider/Resolver 契约、编排、接口、降级、上传/音频副作用、清理语义、验证和集成遗留。
- [x] TASKS_BOARD — PK-000 最终复核通过后已同步为“已完成”，名称、P1 和 `PK-001、PK-200` 依赖不变。
- [x] PUBLIC_README — 已更新 voice 模块状态、新旧接口、响应/流协议、上传限制、文字降级、输出生命周期、重启、测试及 PK-211/PK-212 边界。
- [x] MODULE_CATALOG — 已登记 8 个新旧 health/chat/stream/audio endpoint、`modular` 状态、三进程边界、输出所有权、网络与失败模式。
- [x] ARCHITECTURE_DOCS — 已新增 `docs/architecture/voice.md` 并在模块化单体规范登记依赖方向、Provider、临时生命周期和兼容导出。
- [x] LOCAL_README — 不适用：本机路径、启动器、解释器、端口和环境位置均未变化，未修改忽略的 `README.local.md`。
- [x] AGENT_RULES — 不适用：工作流、安全、验证、文档和 Git 规则均未变化，未修改 `AGENTS.md`。
- [x] VALIDATION — 已记录 fake/MockTransport/临时目录测试、既有回归、相关编译、文档检查及 `git diff --check`；最终状态下已重跑通过。

## 独立对话启动提示

```text
领取 PK-210“语音公共契约与编排”。先完整阅读 README.md、AGENTS.md、
README.local.md（如存在）、TASKS.md、tasks/PK-210-voice.md、
tasks/PK-200-conversation-llm.md 及相关架构文档，检查 git status 和现有
/voice/* 实现。只实现 ASR -> PK-200 -> TTS 的公共契约、编排、版本化接口、
流式降级和临时文件清理；保留 /voice/*、8010/9880 与现有启动器。不要扫描
GPT-SoVITS 源码，不要读取或移动真实模型/参考音频，不要实现 PK-211、PK-212
或 Persona Pack。测试必须注入 fake Provider，禁止真实网络、服务和付费调用。
如需改变 PK-200 或其他模块公共契约，先记录需求并交回 PK-000。
```

## 控制台显式语音 sidecar 启动增量（2026-07-28）

- 用户确认根 `start.bat` 的 Core-only 默认语义容易与全服务入口混淆，并要求
  控制台在 ASR/GPT-SoVITS 未运行时提供与 QQ 类似的显式启动操作。公开 README
  已用启动矩阵明确 `core|voice|qq|all` 和 legacy
  `server/start_all_services.bat` 的实际进程范围。
- 新增 `VoiceRuntimeControlService` 与独立 control router。只读
  `GET /api/v1/voice-control/status` 返回 ASR/GPT-SoVITS 的脱敏
  running/ready/state/message；两个写入口分别固定为
  `POST /api/v1/voice-control/asr/start` 和
  `POST /api/v1/voice-control/gpt-sovits/start`。
- 写接口只接受 loopback + 可信控制台 Origin + 空请求体；前端不能传入 BAT、
  路径、参数、环境变量或下载来源。后端只运行项目固定的
  `server/start_asr.bat`、`server/start_gptsovits.bat`，使用锁、已创建进程与
  固定 8010/9880 端口防止并发重复启动。状态和错误不返回本机路径。
- ASR 就绪只认可显式模型设置或项目标准 `models/asr/medium|small`；GPT-SoVITS
  就绪只认可 PK-211 忽略的本机登记文件存在。按钮不安装依赖、不下载/扫描模型、
  不读取引擎源码、不写 `.env`/登记/个人状态，也不改变 PK-210 Provider 编排、
  PK-211 获取或 PK-212 Voice Pack 契约。
- 控制台 ASR/TTS 状态卡在服务未健康时显示对应按钮和脱敏准备信息；只有状态
  `ready` 才允许点击，启动后在 1.5/5/12 秒自动刷新。QQ 控制代码保持原样。
- 隔离验证全部使用系统临时 Core 锁环境、临时 BAT、fake Popen/端口和
  ASGITransport：runtime-control 4 组通过，dashboard shell、feature catalog、
  voice module 通过，QQ control 8/8，PK-020 Windows 专项 18/18；相关 Python
  `py_compile` 通过。没有启动真实 8000/8010/9880、QQ、LLM、采集、ASR/TTS，
  没有读取或修改真实配置、模型、注册表、外部引擎或个人状态。

### 本增量完成文档门禁

- [x] TASK_RECORD — 已记录接口、固定启动目标、安全边界、UI 行为、副作用和验证。
- [x] TASKS_BOARD — PK-210 因新增公开控制接口恢复为“待集成”，未提前完成。
- [x] PUBLIC_README — 已公开安装 profile 与启动 profile 区别、启动矩阵和按钮限制。
- [x] MODULE_CATALOG — voice 已登记 `/api/v1/voice-control` namespace 与三个接口。
- [x] ARCHITECTURE_DOCS — voice/Windows 架构已记录 runtime-control 所有权和安全边界。
- [x] LOCAL_README — 不适用：未改变本机路径、端口、解释器或资产位置。
- [x] AGENT_RULES — 不适用：既有秘密、外部引擎、测试和 Git 规则未改变。
- [x] VALIDATION — 已记录 fake/ASGI、模块、控制台、QQ、Windows 专项和编译结果；
  文档门禁与 `git diff --check` 在交付前重跑。

## 可安装化增量（2026-07-30）

- 新增 `voice@1.0.0` 的 `in_process` manifest，强依赖 `conversation`、可选依赖
  `calendar`，声明 `/api/v1/voice`、四个 `/voice/*` 兼容入口、
  `dashboard/index.js`、`local_state`、卸载保留和重启语义。没有把 ASR/TTS
  runtime 错当成模块强依赖。
- `module.py` 提供 `backend.register(app)`，只从 composition state 取得公开
  conversation/ASR/TTS/Voice Pack Provider。conversation adapter 延迟解析，
  避免 ModuleManager 描述符顺序造成假损坏；manifest 仍阻止缺少或停用
  conversation 时启用。重复装配幂等，已有同名路由会明确拒绝。
- Core 未安装或未启用 voice 时不产生 voice 路由/面板；动态面板只在安装启用后
  请求 `/api/v1/voice/health`，如实显示 ASR、conversation、TTS 与 Voice Pack，
  TTS/Pack 缺失明确说明保留文字，不显示伪音频成功。
- `package_builder.py` 只复制显式 allowlist 的 Project Kei 协议、编排、路由、
  临时音频管理、文字辅助、入口和面板，使用固定 ZIP 时间、权限、顺序、LF 与
  `ZIP_STORED`。两次构建字节完全一致；release fragment 与完整 Catalog 交接条目
  记录固定 tag、asset、字节数、manifest/ZIP SHA-256，但不修改官方 Catalog、
  不创建 Release、不上传资产。
- 包内容审计确认不含 ASR 模型、GPT-SoVITS 上游/安装器、权重、参考音频、
  Voice Pack 内容、生成输出、本机路径、`.env`、`vendor/`、脚本、缓存或个人
  状态。卸载/重装测试确认外部 Provider 登记与用户音频保持不变。
- 新增稳定 Core `core.calendar_contracts`：线程安全 registry 至多保存一个
  `CalendarSummaryProvider`。`legacy_pipeline.py` 移除对
  `features.calendar.service.today_summary` 的静态导入，只查询公共 registry。
  PK-190 包负责 register/unregister；缺失、停用、解除、异常和并发切换返回固定
  empty/unavailable 摘要，不读取 calendar 状态文件、不崩溃。
- 隔离测试全部使用 fake ASR、fake TTS、fake conversation、fake Voice Pack、
  临时 ModuleManager/registry/runtime/data 和临时音频目录。覆盖 conversation
  强依赖、安装/启用/停用/卸载/重装、同步和 legacy API、文字降级、ASR 缺失、
  流式取消、临时清理、并发请求隔离、重复路由、确定性包、内容禁区、动态面板、
  calendar 缺失/注册/解除/异常/并发及静态反向依赖。
- 全程没有启动 8000/8010/9880、访问外网、调用真实 LLM/ASR/TTS、合成真实音频、
  读取模型/Voice Pack/calendar 个人状态或执行 Git 发布。

### 本增量完成文档门禁

- [x] TASK_RECORD — 已记录 manifest、包入口、Provider 注入、动态面板、数据策略、
  calendar registry、确定性发布输入、副作用、测试和共享装配遗留。
- [x] TASKS_BOARD — 共享 `TASKS.md` 按 PK-011 冻结且已由 PK-000 置“进行中”；
  本文件完成后为“待集成”，最终看板切换交 PK-000 串行装配。
- [x] PUBLIC_README — 不适用：`README.md` 属 PK-011 冻结共享文件；已新增
  voice 模块 README，公开 README 串行汇总交 PK-000。
- [x] MODULE_CATALOG — 官方 Catalog 属 PK-000 冻结窗口；本任务只交付通过 schema
  构建复核的 release fragment 与完整 Catalog entry，不直接合并或发布。
- [x] ARCHITECTURE_DOCS — 已更新 voice 专项架构，公共模块包文档保持冻结。
- [x] LOCAL_README — 不适用：未改变本机路径、端口、解释器或资产位置。
- [x] AGENT_RULES — 不适用：未改变 agent 工作流、安全、验证或 Git 规则。
- [x] VALIDATION — 已运行可安装 voice、原 voice、calendar intent、runtime-control、
  PK-211 sidecar 共享回归、编译、JavaScript、文档门禁和 `git diff --check`；
  精确命令与最终结果记录在下方。

### 共享装配遗留

- PK-000 在串行窗口移除 `server/api.py` 的内置 voice/calendar 路由与直接构造，
  把公开 Provider 放入 composition state，并合并官方 Catalog/README；本任务不改
  这些冻结文件。
- PK-190 已交付 calendar 包并负责 provider register/unregister。PK-211/PK-212
  继续分别拥有 sidecar/引擎 Provider 与 Voice Pack 注册表；voice ZIP 不复制它们。

### 可安装化增量验证记录

- 项目 Python 3.8.20 直接运行
  `tests/test_voice_installable_module.py`、`test_voice_module.py`、
  `test_voice_calendar_intents.py`、`test_voice_runtime_control.py`：全部通过。
- 同一解释器运行 `test_calendar_module.py`、`test_conversation_consumers.py`、
  `test_conversation_module.py`：全部通过。后两项只记录既有 focus runtime
  `PermissionError` 被模块隔离跳过，不影响断言，也没有读取该目录。
- 共享语音批回归：
  `features/voice/providers/gpt_sovits/tests/test_installable_package.py`、
  `test_voice_pack_registry.py`、`test_voice_pack_origin_guard.py` 与
  `test_installable_modules.py` 全部通过，确认 PK-211 Python 3.8 import 修复、
  PK-212 registry 及 PK-010 生命周期未回归。
- `python -m compileall -q core/calendar_contracts features/voice ...`、
  全局 Python 3.12 `py_compile` 和
  `node --check server/features/voice/package_source/dashboard/index.js` 通过。
- `scripts/check_task_docs.py` 通过，共检查 21 个门禁任务；
  `git diff --check` 退出码 0，仅有混合 Windows 工作区既有 LF→CRLF 提示。
- `ruff` 在项目 Python 和当前全局 Python 中均未安装，因此没有伪报 lint 通过；
  相关 E9/F63/F7/F82 风险由两个解释器编译、包实际导入和定向测试覆盖。
- 根 `scripts/python.ps1 -m pytest` 能选择运行时，但当前环境的
  pytest/pytest-asyncio 不识别已冻结 `pyproject.toml` 中
  `asyncio_default_fixture_loop_scope`，严格配置在收集前终止；项目 Python 3.8
  本身未安装 pytest。所有上述脚本式门禁均按仓库既有入口直接运行并通过。

## Voice Pack Resolver 后装顺序修复（2026-07-30）

- 全量装配审计确认 `voice_pack_registry -> voice` 是强依赖，PK-010 会先调用
  voice `register()`；原实现把当时通常为空的 `app.state.voice_pack_resolver`
  直接传给 `VoiceService`，PK-212 后装时虽调用 consumer，但 PK-210 没有发布
  consumer，导致该 service 永久停在无 resolver 状态。
- `module.py` 新增 app-scoped `DynamicVoicePackResolver`。同一 `VoiceService`
  始终持有该代理；注册时立即尝试绑定已有 resolver，并发布
  `voice_pack_resolver_consumer` 接收后装候选。候选必须结构化提供
  health/capabilities/resolve_active_pack/resolve_pack/cancel/close；非法对象
  不替换旧值，`None` 明确解绑。
- consumer 保留并安全调用注册前已有链条。unregister 仅在当前 state 仍指向
  PK-210 consumer 时恢复前置 consumer；若 PK-213 等后装 consumer 已包装它，
  则保留后装链并只停用 PK-210 代理，避免删除有效接缝。
- 绑定和候选快照由进程锁保护。并发合成在解析开始时固定 resolver，并把解析出的
  Pack 引用传到 TTS；中途 bind 只影响后续请求，不改变当前请求。PK-211 的共享
  引擎会话锁、TTS/LLM 独立性、HTTP API 和临时音频规则均未修改。
- 新增永久 fake 回归：resolver 缺失文字降级、voice 先加载后 PK-212 包立即绑定、
  已有 resolver 立即绑定、显式解绑回空、非法对象不产生半状态、前后 consumer
  链保留，以及并发 synthesis/bind 分别使用切换前后的单一 Pack。全部使用临时
  ModuleManager/registry/runtime/data，没有真实服务、模型、音频或 registry。
- 重新构建两次 `voice-1.0.0.zip` 字节一致：49,864 bytes，ZIP SHA-256
  `852a8e97ece7bd3e2ba1fa076eb3b15e7b14c08cea630e645a1ed1678c36e1af`，
  manifest SHA-256
  `555eed46b56389f97abcbbdb00f4d86eb24919be8fa997e062527a594a6c4eed`。
- 最新共享回归通过：PK-210 installable/base、PK-212 installable registry、
  registry、distribution，PK-211 provider/shared engine sessions，calendar
  module/voice intents、conversation consumers。PK-211 额外 installable package
  套件在最新 PK-010 下的“未登记引擎”用例因 `enable()` 抛
  `sidecar start failed` 中止；该测试预期差异不属于本次 PK-210 修改，未改
  PK-211 文件。

## 可安装包运行时控制收口（2026-07-30）

- PK-011 装配前审计确认 `voice@1.0.0` 未把既有
  `/api/v1/voice-control` 能力放入包：manifest 只声明 `/api/v1/voice`，
  allowlist 不含 control router，动态面板也只有刷新。若 PK-000 移除
  `api.py` 静态业务路由，ASR/GPT-SoVITS 显式启动按钮会随之丢失。
- 按不可变 Release 规则提升为 `voice@1.0.1`，新增
  `/api/v1/voice-control` namespace，并在 legacy endpoint 清单保留既有
  status、ASR start、GPT-SoVITS start 三个路径。包 allowlist 新增的只有
  `control_router.py`；没有复制 `runtime_control.py`、BAT、命令、路径、
  安装器、下载器、模型、引擎或 Voice Pack 资产。
- `backend.register(app)` 只动态消费
  `app.state.voice_runtime_control_provider` 公共 duck contract：
  `status()` 与 `start("asr"|"gpt-sovits")`。Provider 缺失、结构错误或
  status 异常时，GET/status 仍稳定返回两个脱敏 `unavailable` 项；POST
  明确失败。异常链、未知字段、命令和本机路径不进入公开响应。
- control router 对 GET 要求真实 loopback peer，且浏览器 Origin 必须可信；
  POST 额外强制存在精确可信控制台 Origin和空请求体。target 由两个固定路由
  决定，客户端不能提交命令、路径、参数或环境变量。
- 动态面板为 ASR、GPT-SoVITS 各提供一个显式按钮，只使用
  `context.request`。mount、页面加载、刷新、折叠和 health/status 读取均为
  零启动；仅点击具体按钮才产生一次对应 POST。Provider 缺失时状态仍可读、
  按钮禁用并显示 unavailable，启动异常以通知展示且不会自动换目标重试。
- 永久 fake 回归覆盖：注册零调用、status 零启动、缺失/异常 Provider 降级、
  loopback/Origin/空请求体、固定 target、响应字段隔离、显式单次调用、动态
  panel 零自动启动与无全局 fetch、manifest 接口声明以及包内容禁区。全部使用
  ASGITransport、fake provider、Node fake DOM 和临时 ModuleManager，没有真实
  8000/8010/9880、进程、网络、模型、音频或 registry。
- 重新构建两次 `voice-1.0.1.zip` 字节一致：59,804 bytes，ZIP SHA-256
  `f199654b2935ce5288d339e32a7b0afeeca73b93d9474d157636c8f1973cbedb`；
  manifest SHA-256
  `c74c2ff59eccb51f443cdcb315754366905fb206b275ff064eea529dd1b98b12`。
  release fragment 与交接 Catalog entry 已切换到独立
  `module-voice-v1.0.1/voice-1.0.1.zip`，未覆盖 1.0.0、未修改官方 Catalog、
  未创建或发布 Release。
- 项目解释器定向回归通过：PK-210 installable/base/runtime-control/calendar，
  conversation consumers，PK-212 installable registry/registry/distribution，
  PK-211 provider/shared engine sessions 及 PK-010 installable lifecycle。
  项目与全局解释器 `py_compile`、动态面板 `node --check`、24 项任务文档门禁和
  `git diff --check` 均通过；后者只输出共享 Windows 工作区既有 LF→CRLF 提示。
- 本增量只改 PK-210 专属代码、测试、任务记录与 voice 专属文档；共享
  `api.py`、Core、`TASKS.md`、根 README、官方 Catalog 和 dashboard 保持冻结。
  PK-210 状态继续为“待集成”。

## 可安装包异步关闭门禁（2026-07-30）

- PK-011 关闭审计确认旧 `unregister` 只解除 resolver consumer/binding 与
  app-state 引用，没有 await 本模块创建的 `VoiceService.close()`；通用 loader
  逆序关闭时可能遗留 ASR/TTS 引用和未完成的 Provider 清理。
- `backend.unregister(app)` 已改为幂等 async。register 额外保存自己创建的
  `voice_module_service_owner`；关闭只针对该实例。若后装模块替换
  `app.state.voice_service`，PK-210 仍关闭自己的 owner，但保留替换对象及其
  state，不会误关其他模块 service。
- `VoiceService.close()` 进入 closed 状态后先解除自身 ASR、conversation、TTS、
  Voice Pack 引用，再按快照逐个 await Provider close。单个 Provider close
  异常被安全隔离，不阻断其他 Provider 与后续 app-state 清理；重复 close 或
  unregister 不重复调用 Provider。
- app-state 清理发生在 close await 完成后，只移除 PK-210 自己发布的 service
  owner、close task、resolver binding/consumer、calendar registry seam 与注册
  标记。composition 注入的 ASR/TTS/conversation/Pack Provider state、外部登记、
  用户音频和已发布文件不读取、不删除。
- 永久 fake 回归通过 source 直接重复 unregister 与临时 ModuleManager 的
  `unload_one_async` 验证：阻塞 ASR close 未完成时 loader 不返回且 owner state
  仍在；释放后才清理；异常 TTS close 被归一；Provider 引用从 service 解除；
  注入 state、替换 service 和用户音频保持；重复卸载返回 `not_loaded` 且关闭
  次数不增加。
- 因未发布的 1.0.1 内容再次变化，按不可变 Release 契约提升为
  `voice@1.0.2`，独立 tag/asset 为
  `module-voice-v1.0.2/voice-1.0.2.zip`。两次构建字节一致：60,882 bytes，
  ZIP SHA-256
  `396fe2689fdaccf5fad793ac7a788faf326c2a42838e2606fa0bc1aebbbd9127`；
  manifest SHA-256
  `de0ffcd0716ea88114d7c8b3dc9a8979dcf05c7ab024880e9d04c1904e52f5f0`。
- 最新定向回归通过：PK-210 installable/base/runtime-control/calendar，
  PK-212 installable registry/registry/distribution，PK-211 provider/shared
  engine sessions 与 PK-010 installable lifecycle。共享
  `test_conversation_consumers.py` 在 PK-000 并行装配移除
  `api.conversation_service` 静态属性后于旧测试夹具处中止；该冻结 API/旧夹具
  差异不属于本次 voice 关闭实现，未修改 API 或该共享测试。
- 本增量未修改 Core、API、dashboard、`TASKS.md` 或根 README，未留下 ZIP、
  未发布、暂存、提交或推送。PK-210 继续为“待集成”。

## ASR 本机模型目录选择增量（2026-08-08）

- 控制台新增“选择 ASR 模型目录”显式按钮，以及
  `GET /api/v1/voice-control/asr/model-directory/status` 和
  `POST /api/v1/voice-control/asr/model-directory/select`。页面挂载、刷新、折叠
  和普通状态读取均不会打开选择器；只有 loopback、精确可信 Origin 的空 POST
  才调用一次注入 provider。请求体不能提交 path、URL、command、参数或环境变量。
- `VoiceRuntimeControlService` 的公共 duck contract 增加脱敏
  `asr_model_selection_status()` 与异步 `select_asr_model_directory()`。默认实现
  只在 Windows 本机打开系统目录对话框，不使用浏览器 directory input。取消零
  写入；Core 无 ASR、无模型或选择器不可用时仍能启动并返回稳定状态。
- 目录校验只读取用户选择的单一目录，不扫描磁盘、不下载、移动或复制模型；要求
  非空可读 `model.bin`、有界且为 JSON object 的 `config.json`，以及一个非空
  tokenizer/vocabulary 文件，并拒绝符号链接和 Windows 重解析点。通过后同目录
  临时文件 + `os.replace` 原子保存忽略的非秘密本机配置；错误模型、保存失败或
  取消均保持旧配置并清理临时文件。
- HTTP 响应只允许 available/configured/state/message 与经清洗的目录名，绝不
  返回绝对路径。已验证路径只在用户随后显式启动固定 ASR BAT 时注入该子进程的
  `ASR_MODEL_PATH`；现有显式进程环境仍优先。没有改变 GPT-SoVITS、Voice Pack、
  8010/9880、启动器内容或 Provider/模型资产归属。
- 永久 fake 回归覆盖取消、错误模型、恶意请求体、重解析点、并发选择单对话框、
  原子保存失败、路径脱敏、固定启动注入、provider 缺失和 Core 无 ASR 零副作用；
  动态面板 fake DOM 证明挂载/刷新零 POST、显式点击恰好一次且只用
  `context.request`。全部模型文件均为系统临时目录中的微小假文件。
- 未发布内容按不可变 Release 契约提升为 `voice@1.0.3`，交接 tag/asset 为
  `modules-2026.08.08/voice-1.0.3.zip`。本增量不修改 Core、API、共享 dashboard、
  `TASKS.md`、PK-020/PK-100/PK-211/PK-212 实现，不提交或推送；PK-210 保持
  “待集成”，由 PK-900 统一验收。
- 两次确定性构建由 installable 回归确认字节一致：67,448 bytes；ZIP SHA-256
  `7c5bd049b74def7dadeebb91b0a48f1fc8a851528af38b7bb0e6c5b334a27702`；
  manifest SHA-256
  `3872e12a006b5f9c3d5e136567ae1e652e1617ab1aebb558cbb07d35d7b9c82f`。
  定向回归通过 PK-210 runtime-control/installable/base、calendar voice、conversation
  consumers、PK-212 registry/distribution、PK-211 provider/session/installable/local
  selection、installable lifecycle、PK-210 `py_compile`、动态面板 `node --check`、
  25 项任务文档门禁和 `git diff --check`；没有启动真实服务、访问外网或读取模型资产。

## Windows runner ASR 临时目录重解析误判整改（2026-08-08）

- 远端 `windows-install` 的完整离线套件在四个 Python 版本中均复现：
  `TemporaryDirectory` 下由测试创建的合法微型模型在 `select()` 时返回
  `invalid_model`。根因是目录验证从用户选中的模型目录一路检查到盘符根；GitHub
  Windows runner 的系统临时目录上层可以包含受系统管理的 junction/reparse 接缝，
  该接缝不属于用户选择的模型树，却使合法目录被误拒绝。
- 验证边界现精确限定为用户明确选中的目录本身，以及将被读取的固定
  `model.bin`、`config.json` 和 tokenizer/vocabulary 文件。目录本身或任一必需
  文件为符号链接/重解析点时仍 fail closed；`..`、UNC/非本地路径、缺失/空文件、
  非对象 JSON 与超限配置仍拒绝。所选目录之外的系统祖先不再被当成模型包内容，
  不会触发递归磁盘扫描。
- 永久回归用注入的 reparse checker 模拟 Windows runner：外部 TEMP 祖先被标记时
  合法模型可配置；所选目录或四个固定模型入口分别被标记时均返回
  `invalid_model`；同时保留 traversal 与 UNC 逆向。本轮所有文件均位于系统临时
  目录，未弹真实 picker、未读取真实模型或个人状态。
- 实际验证：项目 ASR 解释器直接运行 `test_voice_runtime_control.py`、
  `test_voice_module.py`、`test_voice_installable_module.py`、
  `test_voice_calendar_intents.py` 全部通过；同解释器 `py_compile` 通过；系统
  Python 3.12 隔离加载 `asr_model_directory.py` 的 runner-style 正反向夹具通过。
  PK-210 继续保持“待集成”，需由 PK-900 在 Python 3.10–3.13 的新远端矩阵复验。

### Windows 8.3 路径别名复验整改

- 第二轮远端矩阵确认原三项 `invalid_model` 已关闭，但 Windows runner 的
  `C:\Users\RUNNER~1\...` 会解析为 `C:\Users\runneradmin\...`。首轮修复对目录使用
  原始拼写、对固定模型文件只使用规范拼写，导致注入到短路径文件入口的 reparse
  tripwire 未命中；同时启动测试错误地要求 `ASR_MODEL_PATH` 字符串与短路径完全一致。
- 验证器现同时检查用户选择拼写和 canonical resolved 拼写下的三个固定模型文件
  入口；任一身份被标记为 symlink/reparse 都在读取内容前拒绝。新增可注入 strict
  resolver，仅用于构造确定性的 `RUNNER~1 -> runneradmin` 回归；生产默认仍调用
  `Path.resolve(strict=True)`，浏览器/API 仍不能提供 resolver 或路径。
- 启动断言改用 `Path.samefile()` 验证模型目录文件身份，不再把 Windows 8.3/长路径
  的等价拼写当成错误。永久回归逐项标明 raw/canonical 的
  `model.bin`、`config.json`、`tokenizer.json`，因此后续失败可直接定位具体入口。
- 第二轮本地验证：ASR 任务解释器直接运行 runtime-control、voice base、installable
  voice 与 calendar intent 全部通过，相关 `py_compile` 通过；未访问真实模型、未弹
  picker、未启动服务，PK-210 继续等待远端 Python 3.10–3.13 累计矩阵。

## QQ 最终文字单次合成与本地 readiness（2026-08-10）

- 新增仅版本化 `POST /api/v1/voice/synthesize`，严格只接受
  `{"purpose":"qq_reply","text":"..."}`。文字去除首尾空白后必须非空、最多
  1500 个 Unicode 字符且不含控制字符；未知/重复字段、非 UTF-8、非 JSON、超限请求体
  和非固定 purpose 均返回脱敏 `invalid_request`。该入口要求真实 loopback peer，浏览器
  Origin 必须精确可信；伪造 Host、Origin、XFF 或 Forwarded 不能放行。
- 合成与 chat 隔离：零 ASR、零 PK-200 conversation/LLM/history/长期记忆/Collector，
  单请求只调用一次 `TextToSpeechProvider.synthesize()`。Provider 可在同一结果返回原文字
  规划的短句段；PK-210 校验连续 `segment_id/sequence`，将每段有界 WAV 统一为
  24 kHz/mono/signed 16-bit PCM，执行静音裁剪、RMS/峰值归一和 5 ms 淡入淡出后顺序
  合并。缺段、重复、乱序、无效音频或超过 60 秒整体失败，不字节拼接 WAV/压缩容器。
- 固定 profile 为 `qq_c2c_voice_v1`，只把统一 PCM 交给注入的公共
  `UtteranceEncoder` 一次。成功为单个 `audio/silk`、`final=true`，最大 8 MiB；只返回
  固定 profile 与随机 opaque utterance ID，不含文字、用户、路径、URL、base64、模型、
  Voice Pack、提示词或临时文件名。没有/未就绪/失败的 encoder 均稳定
  `encoding_unavailable`，绝不退回 WAV；TTS、Pack、格式、超时与超限也只返回有限 code。
- 受控无 Origin sidecar 可提交 16–80 字符有限 `Idempotency-Key`；浏览器不能提交持久
  key。同 key/同文字并发与短 TTL 重放共享一次 TTS、一次最终编码和同一进程内 PCM，
  失败结果不隐藏重试，同 key 换文字固定冲突。最后等待者断开/取消或 shutdown 会取消
  Provider 并释放引用；该入口全程使用有界内存，不创建、发布或持久化临时音频。
- health 新增本地 `synthesis_profiles.qq_c2c_voice_v1`，只依据 TTS engine、活动
  Voice Pack 和 encoder 的 health/capabilities；读取零生成、零写入。它不读取 QQ
  AppID/Secret，不因存在凭据推断 Bot 媒体权限，也不真实发消息探测。QQ 协议支持 C2C
  富媒体、Node sidecar 已实现上传、具体 Bot 已获准媒体能力是三个独立状态；PK-140 完成
  前整体 QQ voice 保持 unavailable。PK-140 后续合并非秘密
  `qq_media_upload_capability=unknown|available|unavailable|denied`，`unknown` 默认
  fail closed；只有本地 Silk profile ready 且能力明确 available 时 UI 才能开启。
- `voice@1.0.4` 保持未发布候选；两次确定性构建由 installable 回归验证字节一致：
  93,874 bytes，ZIP SHA-256
  `e5a44180ad45fe6db7d01160120de2e7d3233364e969db406eeed12b1274f893`，manifest SHA-256
  `da15998dbfd75d9972f404f1218967516398d5b245c383bb7a618c383d88a4d1`。包不含生产
  Silk encoder、QQ 上传、模型、权重、参考音频、生成输出、路径、`.env`、vendor 或脚本。
- 永久 fake 回归通过：PK-210 base/installable/runtime-control/calendar，PK-200 consumer，
  PK-211 provider/shared session/selection，PK-212 registry/origin/distribution/installable，
  PK-010 installable lifecycle 与 feature Catalog；覆盖严格输入、零 ASR/conversation、单次
  TTS/编码、Unicode/分段顺序、缺失/重复/乱序、缺 Provider、超时/恶意错误、编码失败、
  格式/时长/大小、取消/shutdown、清理、并发同 key、失败复用和本地 readiness。
  `compileall`、动态面板 `node --check`、29 项任务文档门禁及 `git diff --check` 通过；
  `test_voice_pack_distribution.py` 直接脚本入口缺少自身 `_path_setup`，改用标准
  `python -m tests.test_voice_pack_distribution` 后其 13 项通过。未启动真实
  8000/8010/9880、LLM、QQ、Pi 或网络，未读取真实模型/Pack/音频/secret/runtime/vendor。

### 八项文档门禁

- [x] TASK_RECORD — 本节记录接口、媒体、幂等、readiness、包摘要与验证。
- [x] TASK_BOARD — `TASKS.md` 将 PK-210 置为“待集成”。
- [x] PUBLIC_README — 根 README 增加 synthesize、固定 Silk profile 与 QQ fail-closed 边界。
- [x] MODULE_README — voice README 增加 encoder 注入、PCM、资源和 readiness 契约。
- [x] ARCHITECTURE — `docs/architecture/voice.md` 冻结合成与三层 capability 边界。
- [x] LOCAL_README — 不适用：未读取或改变本机模型、Provider、Secret 或服务配置。
- [x] AGENT_RULES — 不适用：任务所有权、秘密、网络和进程规则未改变。
- [x] VALIDATION — 全 fake/临时目录回归、编译、Catalog、JS、文档和差异门禁已通过。

PK-210 保持“待集成”，已在 PK-140 任务记录中交回开关、QQ `file_info` 上传、
`msg_type=7` 发送、文本降级与综合 readiness 后续；未暂存、提交、推送或发布。

## 生产 Silk encoder 与 duration header 增量（2026-08-10）

- 总控复核确认此前只有 fake `voice_utterance_encoder`，所以真实 synthesize 必然
  `encoding_unavailable`。本轮在 voice 专属边界新增
  `SilkPythonUtteranceEncoder`：输入固定 24 kHz/mono/s16le PCM，输出固定
  `qq_c2c_voice_v1`/`audio/silk`；以 `sys.executable -I` 启动短生命周期隔离 worker，固定
  参数调用本地依赖，不接受用户 command/path/URL/codec/bitrate，stderr 丢弃，超时、取消、
  close、并发和 8 MiB/60 秒上限均受控。
- 候选审计选择 `silk-python==0.2.8`：PyPI 元数据声明 BSD，项目固定的
  `silk-v3-decoder` revision `507be6bca8ce1fb977a061481f1d79e8c610e309` 为 MIT；
  PyPI 提供 Windows x64 CPython 3.10/3.11/3.12/3.13 wheels。四个 wheel SHA-256 已冻结在
  适配器常量中。风险是 PyPI 页面显示该版本未通过 Trusted Publishing，因此 PK-020 必须
  使用逐 wheel hash lock，不能只锁版本。备选 `pysilk-mod==1.6.4` 的许可证/上游组合更复杂；
  `pilk==0.2.4` 缺 CPython 3.12/3.13 Windows wheel，均未加入项目。
- 包不 vendor 上游源码、wheel、二进制或远程脚本。依赖/版本/平台缺失时 health 返回稳定
  unavailable 且不创建进程，Core 正常启动。所有异常只对 VoiceService 暴露稳定 code。
- 生产闭环仍有共享接缝，未伪报完成：PK-020 应新增 hash-locked voice-media Windows lock，
  在 `voice`/`full` profile 安装上述 wheel，并由 doctor 做零编码、零写、零网络的
  distribution version/import/capability 检查；共享 composition 应固定创建适配器并注入
  `app.state.voice_utterance_encoder`。完成前真实 synthesize/QQ voice 保持 unavailable。
  PK-010 manifest 现有 runtime requirements 只描述 host runtime，不应用来暗装 Python codec；
  本轮未改 PK-020、PK-010 或 composition。
- synthesize 成功响应新增固定 `X-Kei-Audio-Duration-Ms`。值只从已校验
  `SynthesizedUtterance.duration_seconds` 用 `math.ceil(seconds * 1000)` 派生；合法范围
  1..60000。零、负数、NaN、infinity 和大于 60 秒均在发布二进制前返回稳定
  `audio_invalid`/`encoding_unavailable`，不 clamp，不从 encoded bytes 或请求字段估算。
- fake 回归新增适配器健康/能力、固定输出、依赖缺失/错版/错平台、非法输入、恶意输出、
  超时、取消、重复 close 与 wheel hash 覆盖；duration 覆盖亚毫秒、非整数向上取整、精确
  60 秒以及 0/NaN/inf/超限拒绝。全程未安装或导入真实 codec，未编码真实音频，未访问网络。
- 未发布内容按不可变 Release 契约提升为 `voice@1.0.5`；两次确定性构建字节一致：
  104,572 bytes，ZIP SHA-256
  `bb4d80cf5f036608e771f9230b406ec70164e389b5a221d3c6d1d3435faf80ac`，manifest SHA-256
  `c5585ba6cbcb1591f22c465b49727530e0de9d07fb1bb097f3a25ed7464b80bf`。
  PK-210 状态继续为“待集成”。
- 定向验证通过：PK-210 base/installable/Silk/calendar/demon、PK-200 conversation consumer、
  PK-211 GPT-SoVITS provider/shared session、PK-212 registry/distribution 与 feature catalog；
  `py_compile`/`compileall`、29 项任务文档门禁、Python 测试 inventory 和
  `git diff --check` 通过。项目已配置解释器与系统 Python 均未安装 ruff，因此本轮没有
  声称 ruff 通过，也没有为此联网或修改依赖。所有测试均为 fake/临时目录，未启动真实
  8010/9880、TTS、LLM、QQ 或网络，未读取模型、Voice Pack、音频、secret、runtime 或 vendor。

## PK-000 生产 encoder 装配收口（2026-08-10）

- 生产 `InstalledModuleHost` 已固定创建 `SilkPythonUtteranceEncoder` 并注入
  `app.state.voice_utterance_encoder`。构造过程不导入可选 codec、不创建 worker、不联网；
  依赖缺失时 health 明确 unavailable，Core 及不使用语音附件的功能仍可启动。
- PK-020 已新增 `voice-media-win.lock.txt`，仅在 `voice/full` profile 以逐 wheel SHA-256、
  `--require-hashes`、binary-only 安装 `silk-python==0.2.8`；doctor 只读检查版本、import 和
  encoder capability。四个 CPython 3.10–3.13 Windows x64 摘要与本模块常量一致。
- PK-000 的 module host assembly 已验证固定实例、缺 voice service 返回 unavailable、有效
  health 快照和非法 capability 归一为 unknown；PK-210 的 Silk、module、installable 专项均
  通过。PK-210 继续“待集成”，由 PK-900 复验真实 Windows 四版本安装矩阵与跨模块降级。

## voice 1.0.5 本机正式更新与 QQ profile 就绪复核（2026-08-10）

- 运行态只读复核确认本机此前仍启用 `voice@1.0.2`；该旧服务的 health 只有 providers，
  不包含 `synthesis_profiles.qq_c2c_voice_v1`，因此 QQ 面板即使已声明媒体权限，也只能
  显示 `encoding_unavailable`。这不是 ASR/GPT-SoVITS 状态卡误报，也不是 QQ 上传实现失败。
- 在系统临时目录构建 `voice-1.0.5.zip`，大小 104,572 bytes，SHA-256 为
  `bb4d80cf5f036608e771f9230b406ec70164e389b5a221d3c6d1d3435faf80ac`；包内固定 14 个
  manifest/backend/dashboard 文件，无 `.env`、data、runtime、vendor、模型、权重或音频。
  通过 ModuleManager 正式 `update` 把本机版本从 1.0.2 更新到 1.0.5，保留 1.0.2 为
  previous version，未直接编辑 runtime/registry。
- 更新前定向脚本通过：voice base、voice installable，以及 QQ configuration 12/12。
  voice-media lock 安装完成后，真实只读 health 显示 utterance encoder、Voice Pack 与 TTS
  均 available，`qq_c2c_voice_v1` 为 `audio/silk` 且 available；没有调用 synthesize，
  没有读取 Voice Pack/模型内容，也没有生成音频。
- PK-210 继续保持“待集成”；本节只证明本机候选安装与 readiness 闭环，不构成真实 QQ
  发送验收、GitHub 发布或最终完成确认。

## voice 1.0.5 broken 本机恢复与 QQ readiness 闭环（2026-08-11）

- 运行态首先确认 `voice@1.0.5` 为 `enabled=true`、`configuration_ready=true`，但状态为
  `broken`，且 `/api/v1/voice/*` 返回 404。只读图预检得到
  `ModuleConflictError: module dependency unavailable: voice_pack_registry->voice`；这是依赖模块
  对 broken 强依赖的后续阻断，不是最初装载失败原因。
- 同一已安装包在临时 FastAPI、临时 voice data root 中可成功装载并注册 10 条
  voice/voice-control 路由。正式 Core generation 10 的实际 load result 进一步定位到
  `PermissionError: [WinError 5]`，目标仅为
  `runtime/modules/voice/1.0.5/backend/__init__.py`。该目录来自此前隔离进程安装，ACL 只包含
  SYSTEM、Administrators 与 Owner Rights；正式 supervisor Core 无法读取。没有读取模型、
  Voice Pack、用户音频、个人状态或 secret。
- 未直接编辑 registry 或 runtime 文件。尝试只为精确 voice 目录补读取 ACL 时被 Windows 拒绝，
  随即停止权限修改。改用正式 ModuleManager 更新流程：在系统临时目录以普通 Windows 用户
  上下文构建同源码 `voice@1.0.6`，大小 104,572 bytes，SHA-256 为
  `32963c4c76c7a593c8d5235e0e1768843661fbcc0b0d88a2c0a8c927203bd534`；再由运行中的 Core
  调用 `POST /api/v1/modules/voice/update` 创建新版本目录和原子 registry 记录。本机修复版本
  仅用于恢复正式运行态，尚未发布为官方 Catalog/Release。
- 为避免孤儿 sidecar，更新前先通过模块生命周期接口停用 QQ，确认进程退出；受控重启到
  generation 11 后，`voice@1.0.6` 成功装载，`restart_required=false`，
  `/api/v1/voice/health` 返回 200。真实只读 health 显示 TTS、Voice Pack、
  `silk-python/0.2.8` encoder 均 available，`qq_c2c_voice_v1` 为 final `audio/silk`、
  60 秒/8 MiB 上限。ASR 未运行使整体 health 为 degraded，但 QQ 的“既有文字 -> TTS -> Silk”
  链路不依赖 ASR。
- QQ 重新启用后再由受控 supervisor 重启到 generation 12；最终只读状态为
  `process_running=true`、`gateway_ready=true`、`gateway_last_error_code=null`，且配置快照为
  `qq_media_upload_capability=available`、`reply_with_voice=true`、
  `voice_profile_ready=true`、`voice_reply_available=true`。本轮没有向真实 QQ 发送消息，
  没有调用真实 synthesize，也没有输出或读取 AppID/Secret。
- 定向回归使用现有 Core `.venv` 的脚本兼容入口和临时/fake 数据：voice module、installable、
  Silk encoder、module host assembly、Voice Pack registry/distribution 全部通过；QQ 配置面板
  12/12；Node QQ voice fake 链路 19/19。`scripts/python.ps1` 首次因本机 ExecutionPolicy 未进入
  测试；项目 `.venv` 缺 pytest、系统 pytest 环境缺 FastAPI，均未联网补装或改环境，改用
  仓库已有直接脚本入口完成验证。
- PK-210 仍保持“待集成”。本节证明本机 ACL 异常已通过正式更新恢复，以及 QQ voice readiness
  已闭环；真实 QQ 语音上传/发送仍需用户显式触发后的运行验收，不能据此提前标记“已完成”或
  发布 GitHub。

## 安装版 Provider 契约身份修复后的实机合成闭环（2026-08-11）

- 后续真实合成发现 readiness 为 ready 仍不足以证明安装版调用成功：隔离加载的 voice
  backend 与宿主 Provider 的同名 dataclass 不共享 Python 类身份。PK-211 已在 Provider
  边界以严格固定字段重建宿主请求/Pack 契约，消除安装版误走 legacy bytes 返回的问题，
  未改变 PK-210 的公开请求、响应、Silk profile 或资源上限。
- 修复后从真实 Core 调用 `POST /api/v1/voice/synthesize` 已得到 200、final
  `audio/silk`、profile `qq_c2c_voice_v1`、2375 bytes 与 786 ms duration；此前的
  `audio_invalid` 已不再复现。该结果只证明 Core→Provider→GPT-SoVITS→PCM→Silk
  闭环，未代替 QQ file upload / `msg_type=7` 的真实发送验证。
- PK-210 继续“待集成”；本地 `voice@1.0.7` 是未发布验证候选，不更新官方 Catalog 或
  Release。此前失败的 QQ 消息受 at-most-once 约束不会重放，须用新消息验证后半链路。
## ASR / GPT-SoVITS 显式安全关闭增量（voice 1.0.8，2026-08-12）

- `VoiceRuntimeControlService` 为固定 ASR/GPT-SoVITS 启动器保存进程组句柄；公开状态
  增加 `owned/can_stop`。外部端口运行只读可见，不能从控制台关闭。
- 新增 `POST /api/v1/voice-control/asr/stop` 与
  `POST /api/v1/voice-control/gpt-sovits/stop`，仅可信本机 Origin、空 body，拒绝
  PID、端口、路径和命令。停止只向当前 Core 创建的固定进程组发送受控中断并有界等待。
- 语音动态面板和顶部配置卡均增加二次确认后的关闭按钮；重复关闭零副作用。
- `voice@1.0.8` 两次系统临时目录确定性构建逐字节一致：`108683` bytes；ZIP SHA-256
  `d05c0a2a783851d54f5656596ec66d26a34131223b0221437f3bdccb6b6f4f9b`；manifest SHA-256
  `3290021c1c5d1f22f560787c30894ee445d59f2c8c30e076794f884a933f74fb`。不得继续沿用
  早期 1.0.6 候选的摘要。

## 顶部后台启动与模块调试入口分层（voice 1.0.9，2026-08-12）

- 用户要求没有调试黑框时也能从“配置就绪情况”启动和关闭 ASR/GPT-SoVITS，同时
  保留语音模块内适合排障的可见窗口。本轮没有合并两种行为：原固定 `/start` 路由
  继续用 `CREATE_NEW_CONSOLE`，动态模块按钮明确标注“调试启动……（打开窗口）”；
  新增固定空 body 的 `/asr/start-background` 与 `/gpt-sovits/start-background`，仅供
  顶部日常状态卡使用。
- 后台模式仍创建独立 Windows process group，但通过受控 `STARTUPINFO/SW_HIDE` 隐藏
  窗口；同一个 `VoiceRuntimeControlService` 保存句柄，因此后续固定 `/stop` 仍只会
  向本 Core 创建的进程组发送中断。外部端口实例继续 `can_stop=false`，不显示可关闭
  按钮。浏览器不能提交 PID、端口、路径、命令、参数或环境变量。
- 公共顶部状态卡只在对应 target 精确 `state=ready` 时显示“启动服务”，运行后按
  `can_stop` 显示“关闭服务”或只读“外部启动”。页面加载、刷新、折叠和定时轮询均为
  GET，不会自动启动；后台启动失败也只显示脱敏错误并恢复状态。
- 永久回归覆盖：后台/调试 creation flags 分离、八路并发单例、固定路由和 Origin/body
  门禁、恶意 command body 零启动、owned-only stop；fake DOM 进一步验证顶部精确调用
  `start-background`、从不调用调试 `/start`，以及启动后只调用固定 stop。Voice runtime、
  installable module、Dashboard shell 专项均通过。
- 不可变候选提升为 `voice@1.0.9`；本轮只构建和校验系统临时目录候选，不安装本机、
  不上传 Release、不触发真实 ASR/GPT-SoVITS。PK-210 继续保持“待集成”。
