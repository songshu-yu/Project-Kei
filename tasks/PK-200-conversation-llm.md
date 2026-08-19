# PK-200 — LLM 对话与模型方案

- 状态：待集成
- 优先级：P1
- 所属模块：`conversation`
- 依赖任务：PK-001、PK-010、PK-100
- 负责路径：`server/features/conversation/`、`server/core/llm_engine.py`、`server/core/dialogue_manager.py` 兼容层、`server/prompts/kei_system.txt`、`server/api.py` 的 conversation/profile 装配与 legacy 接缝、`server/features/catalog/service.py` 的 conversation 目录项、必要的受控文本生成消费者接缝、隔离测试及完成门禁文档
- 当前对话：2026-07-30 由 PK-000 重新打开 PK-011 本地业务批可安装化增量；只修改 conversation 专属包源、构建器、动态面板、Release 元数据、专属测试与本任务记录，共享装配文件保持冻结

## 2026-07-30 可安装化增量入场登记

- 对话目的：在不重写既有对话、history、profile 与热切换规则的前提下，为
  `conversation` 生成符合 PK-010 冻结契约的确定性 `in_process` 安装包、动态
  LLM 面板和官方 Release 元数据，并以临时 ModuleManager 验证完整生命周期。
- 允许路径：`server/features/conversation/**`、
  `server/tests/test_conversation_package.py` 与本任务文件。`TASKS.md` 已由
  PK-000 更新，本对话不再修改；`server/api.py`、Catalog、dashboard 公共文件、
  README、`server/core/modules/**` 和架构文档全部冻结。
- 非目标：不改变 manifest/loader/Catalog/Core Provider 公共契约，不迁移 ASR、
  TTS、音频文件或语音流，不并入 PK-160 状态，不发布 Release，不执行 Git
  暂存、提交、推送或工作区清理。
- 数据边界：包只含 allowlist 程序、声明、Kei 角色提示与面板；API Key 只从环境
  或测试注入取得。测试只使用虚构 Key、fake client、MockTransport、临时 profile、
  registry/runtime/data；不读取或打包真实 `.env`、`llm_profile.json`、长期记忆、
  好感度、缓存、模型、vendor 或个人状态。
- 共享装配现状：当前冻结的 `server/api.py` 仍直接导入并内置装配
  `features.conversation`，现有消费者也尚未全部改为“模块缺失时返回空实现”的
  Core Provider。因此本任务可以交付并隔离验证包本身，但真实 Core 的无包启动、
  legacy 内置路由移除及消费者空 Provider 接线必须由 PK-000 串行装配；PK-200
  不越界修改共享文件或伪称该接缝已经落地。

## 总控定位决策

- 解除循环依赖：PK-200 只依赖已完成的 PK-001；PK-160 继续依赖 PK-200。依赖方向固定为 `PK-001 -> PK-200 -> PK-160`，PK-200 不等待、导入或读取 PK-160 的状态实现。
- PK-200 先定义只读 `ConversationContextProvider` 协议和返回空文本的模块默认实现。为保留现有行为，应用装配层可暂时把既有 `MemoryStore.prompt_context` 包装成可选兼容 Provider，但 `server/features/conversation/` 不得导入 `MemoryStore`；PK-160 后续提供正式实现。Provider 不暴露 repository、状态对象或写方法。
- 本轮是随主 API 启动的必需内置 `in_process` conversation 模块化，不制作 manifest、本地包、ZIP、安装/启停/卸载/重装流程或动态面板。
- 控制台模型方案面板第一阶段保留 `server/static/dashboard.html` 中的 legacy DOM、元素 ID 和交互，不迁入 PK-100 动态入口，不新增 `mount(context)`/`unmount()`。
- PK-200 负责文字对话、Kei 角色提示、非秘密模型 profile、候选测试、原子热切换和供其他模块调用的受控文本生成。ASR、TTS、音频上传/下载、流式音频和语音临时文件归 PK-210；好感度与长期记忆状态、命令和写入归 PK-160。
- 默认保留单用户、单主进程、内存对话历史语义。不得自行增加账户、鉴权租户、会话 ID、数据库历史、跨重启恢复、多人隔离或多进程会话同步。

## 目标

把现有 LLM 引擎、对话编排、模型 profile 和热切换迁入明确的 conversation 模块边界。版本化接口与 legacy 接口必须委托同一稳定 service/runtime；模型切换成功后，文字对话、语音对话的文字阶段、每日情报改写、生命维持文案和斩妖复盘等现有消费者在下一次调用时共同使用新配置，同时不泄露凭证、不丢失现有进程内历史。

## 不在本任务内

- 不制作可安装包、manifest、生命周期 API、模块 ZIP 或动态控制台入口；不修改 PK-010/PK-100 公共契约。
- 不实现或重构 ASR、TTS、音频 base64、音频文件、语音流、麦克风测试、8010/9880 服务或 PK-210 路由。
- 不读取、迁移、打印、重置或修改好感度与长期记忆状态；不实现 PK-160 的 relationship/memory API、存储、摘要规则或写命令。
- 不新增账户、多用户、会话持久化、数据库、Redis、跨进程 history、向量库、RAG、工具调用、联网搜索、模型路由、自动重试风暴或后台常驻进程。
- 不改变每日情报、生命维持、斩妖复盘等调用方的业务 prompt 或兜底规则；只允许把它们对原始 `LLMEngine` 的依赖替换为 PK-200 的公开受控生成契约。
- 不调用真实/付费模型，不运行 `test_llm_debug.py`、真实 `/voice/chat`、真实每日情报改写或任何会访问外部 LLM 的手工探测。
- 不执行 Git 暂存、提交、推送、PR 或工作区清理，不整理 `vendor/` 或其他任务/用户修改。

## 允许修改的边界

- `server/features/conversation/`：建立 `models.py`、`context.py`（或同等公开协议文件）、`repository.py`、`runtime.py`/`service.py`、`router.py` 和 `__init__.py`；HTTP、profile 持久化、运行时切换和对话用例职责分离。
- `server/core/llm_engine.py`：保留底层 OpenAI-compatible HTTP 客户端、角色 prompt、情绪解析和内存 history；不得在此直接读写 profile 或其他模块状态。
- `server/core/dialogue_manager.py`：作为 compatibility/application 接缝委托 conversation service。版本化 conversation 核心不得直接依赖 `MemoryStore`；既有记忆命令行为在 PK-160 接管前只能保留为外部兼容接缝，不得扩写其状态逻辑或用真实记忆测试。
- `server/api.py`：只允许移出 conversation/profile 业务规则、装配统一 router/service，并为 `/chat`、`/chat/text-only`、`/history*`、`/ws/chat`、voice/daily briefing/life-support/demon 等现有调用点注入稳定 conversation/text-generation 门面；不得借机重构这些业务。
- `server/services/daily_briefing.py`、`server/services/voice_pipeline.py`：仅允许必要的类型/构造注入接缝，使其不持有会在热切换后失效的原始 engine；不得改变采集、缓存、ASR、TTS、音频或意图规则。
- `server/static/dashboard.html`：只允许把 legacy 模型面板请求切到同一版本化 service 的兼容 handler，并保持现有 DOM、预设、按钮和成功/失败语义；本轮不是视觉重设计。
- `server/features/catalog/service.py`、README、架构说明和测试：实现完成时把 conversation 的 `api_namespaces` 明确登记为 `/api/v1/conversation` 与 `/api/v1/llm-profile`，同步全部 legacy endpoint、迁移状态、数据/秘密边界和验证结果，不改其他模块目录项。

## 接口契约

### 版本化 conversation

- `POST /api/v1/conversation`：请求至少包含非空 `message`；只返回文字阶段的 `text`、`emotion`、`timestamp`，不得返回或触发音频。
- `GET /api/v1/conversation/history`：返回当前单进程 history 的 `count` 与最近消息；字段与既有 `/history` 兼容，不增加跨重启承诺。
- `DELETE /api/v1/conversation/history`：只清除当前进程内 conversation history，并返回确定的清除数量/状态；不得清除长期记忆、好感度、profile 或任何文件。
- 非空校验、情绪白名单、角色 prompt、历史截断和失败兜底由同一 conversation service/runtime 管理；旧接口不能保留第二套规则。

### 版本化 profile

- `GET /api/v1/llm-profile`：仅本机可用，只返回 `provider`、`base_url`、`model`、`thinking_mode`、`updated_at` 等公开字段。
- `PUT /api/v1/llm-profile`：仅本机可用；校验并测试候选 profile，只有完整成功后才原子应用和持久化。请求与响应都禁止 `api_key`、Authorization、headers、Cookie、Token 或任意额外秘密字段。
- `provider` 第一阶段只接受当前明确支持的值（`deepseek`、`custom`）；`thinking_mode` 只接受 `enabled`/`disabled`。`base_url` 必须是绝对 HTTP(S) URL，禁止 userinfo、fragment、query 中嵌入凭证；`model` 非空且有长度上限。
- 未知请求字段应拒绝，不能静默落盘；错误响应只能包含安全错误码、阶段和简短说明，不回显远端响应正文、请求 headers、API Key、完整异常链或可能含凭证的 URL。

### 兼容接口

- 保留 `POST /chat`、`POST /chat/text-only`、`GET /history`、`POST /history/clear` 和 `WebSocket /ws/chat`。其中音频合成/传输仍是 PK-210 兼容层职责，文字回复必须委托同一 conversation service。
- 保留 `GET /dashboard/llm/profile`、`PUT /dashboard/llm/profile` 及 legacy 控制台面板；它们与 `/api/v1/llm-profile` 共用请求模型、profile repository、候选测试和原子切换 service。
- 不为本轮新增版本化语音或 WebSocket 协议；PK-210 后续通过 PK-200 的公开文字 service 接入。

## 跨模块公开协议

### 只读上下文 Provider

```python
class ConversationContextProvider(Protocol):
    def get_context(self) -> str: ...

class EmptyConversationContextProvider:
    def get_context(self) -> str:
        return ""
```

- conversation 模块默认使用空实现，因此在没有 PK-160 或任何个人状态时仍可独立启动。过渡期主应用可注入既有只读 `prompt_context` 兼容适配器以避免回归，但该适配器不是 PK-200 的数据所有权或前置依赖。
- PK-160 后续提供正式只读实现；它负责决定哪些好感度/记忆信息可进入 prompt。PK-200 只消费返回文本，不得导入 PK-160 repository、枚举状态或调用写方法。
- Provider 返回空文本时行为正常；Provider 异常时应安全降级为空上下文并输出不含个人内容的简短日志，不把上下文写入响应或错误。

### 受控文本生成

- PK-200 暴露稳定的 `TextGenerator`/conversation service 门面，支持调用方传入受控的 system instruction、user input、`max_tokens`、`temperature` 并返回纯文本。
- 受控生成不得写入普通聊天 history，也不得自动读取长期记忆；参数必须有确定上限。调用方继续拥有自己的业务事实、prompt 和 fallback。
- voice、daily briefing、life-support、demon review 等消费者只能持有稳定门面，不能缓存当前原始 `LLMEngine`。热切换后它们的下一次调用必须看到同一个新 runtime。

## profile 测试与原子应用语义

1. 在不修改活动状态的前提下规范化候选 profile，并用当前环境变量中的 API Key 创建候选 engine；API Key 不进入候选 profile。
2. 候选测试只调用候选 engine，不能追加、清空或复制回活动 history，不能提前更新全局配置、文件或消费者引用。
3. 候选测试成功后，在 reconfigure 锁下重新确认活动 runtime，复制当前内存 history，先把非秘密 profile 完整写入同目录唯一临时文件并 `flush/fsync`。
4. commit 由同一稳定 runtime/service 协调：profile 原子替换和活动 engine 指针切换对所有通过门面调用的消费者表现为一个提交点；并发请求要么完整使用旧 engine，要么完整使用新 engine，不允许看到半更新消费者集合或丢失 history。
5. 旧 engine 只在提交成功后关闭；关闭失败只能记安全警告，不回滚已经成功的提交，也不能泄露连接或凭证信息。
6. 在校验失败、候选 HTTP 4xx/5xx、超时、格式错误、取消、临时文件写入失败或原子替换失败时：关闭候选并清理候选临时文件；旧 engine、旧 history、旧 profile 文件、内存 profile、模型配置和所有消费者必须逐项保持不变。
7. profile 文件缺失时使用环境变量派生的非秘密默认值；文件损坏或结构异常时安全回退但不得静默覆盖原文件。修复/覆盖只能来自一次成功的显式 PUT。

## 数据与秘密所有权

- PK-200 只拥有 `server/data/llm_profile.json` 的非秘密模型偏好；该文件是本机状态，本轮不得读取真实内容、打印、查看详细 diff、格式化、迁移、覆盖、暂存或提交。
- API Key 和其他凭证只来自进程环境/`server/.env`；`.env` 只允许检查存在性或变量名是否配置，禁止读取或输出值。任何 profile repository、模型、响应、日志、异常和测试夹具都不得接收或序列化 API Key。
- `server/data/memories.json`、`server/data/affection_state.json` 及其他同名历史文件属于 PK-160/用户个人数据；PK-200 不得读取内容或详细 diff，也不得写入、清理、迁移、暂存或用作测试。
- conversation history 默认只在内存中，由 PK-200 runtime 所有；清历史不等于清长期记忆。角色 prompt 文件是代码资产，不得包含真实用户状态或密钥。
- 所有 profile 写测试必须显式注入系统临时目录；所有 LLM HTTP 测试必须使用 `httpx.MockTransport` 或等价假客户端，使用虚构 Key 和去标识化 payload。

## 实施清单

- [x] 固定现有 `/chat*`、history、profile、角色 prompt、情绪、fallback、控制台和消费者兼容基线。
- [x] 建立 conversation models/context/repository/runtime/service/router 边界，并保留 core 兼容导出/适配。
- [x] 新增版本化 conversation/profile 接口，让新旧路由共用同一 handler/service。
- [x] 引入稳定受控生成门面，把现有消费者从原始 engine 引用切换为公开契约且不改业务 prompt。
- [x] 实现候选测试、锁、唯一临时文件、原子 profile 保存、单点 runtime 切换和失败回滚/清理。
- [x] 保留 legacy 控制台面板，不制作动态入口或安装资产。
- [x] 补齐 MockTransport、临时 profile、假 context provider、新旧 API、并发切换、失败注入、秘密扫描和消费者一致性回归。
- [x] 更新目录、README、架构说明、任务记录和完成文档门禁；运行定向测试、语法检查、文档门禁及 `git diff --check`。

## 验收标准

- PK-200 只依赖 PK-001；PK-160 可在之后通过公开 `ConversationContextProvider` 接入。PK-200 在空 Provider 下可独立启动和完成文字对话，过渡期兼容 Provider 继续保留现有只读上下文行为且不形成反向任务依赖。
- conversation 分层清晰，router 不创建客户端或读写文件，profile repository 不管理 runtime，底层 engine 不读取 profile/长期记忆；`api.py` 只装配和保留兼容接缝。
- 新旧文字对话、history 和 profile 接口共享同一 service，成功响应兼容；`/chat` 的音频部分与 `/ws/chat` 仍可由 PK-210 兼容层调用同一文字 service。
- profile 只保存/返回批准的非秘密字段；额外秘密字段、带 userinfo/query/fragment 的危险 URL 和非法枚举被拒绝。错误、日志、历史、profile 和目录响应中没有 API Key 或远端响应正文。
- 候选测试成功才提交；对测试失败、超时、取消、响应异常、临时写失败、`os.replace` 失败和旧 engine 关闭失败均有隔离回归。所有提交前失败都证明旧 engine、history、profile 文件、内存 profile及全部消费者不变。
- 热切换成功保留既有进程内 history，所有消费者下一次调用一致使用新模型；受控生成不污染聊天 history。并发聊天/生成/切换没有半更新、丢历史或使用已关闭 client。
- 所有自动测试仅用假 LLM/MockTransport、临时 profile 和假 Provider；真实 `.env` 值、真实 `llm_profile.json`、长期记忆/好感度内容、外部模型、ASR、TTS、QQ 和采集均未触及。
- legacy LLM 面板保持单一且可用，不出现动态副本；catalog、README、架构和任务记录与实际代码一致，八项文档门禁和 `git diff --check` 通过。

## 工作记录

- 2026-07-21：PK-000 完成入场登记。只读核对现有 `LLMEngine`、`DialogueManager`、API profile/chat/history/ws 装配、legacy 控制台、catalog 和消费者接缝；仅检查真实 `.env`、`llm_profile.json`、memory/affection 文件是否存在及 Git 状态，未读取其内容或详细 diff。
- 2026-07-21：PK-000 解除 PK-160/PK-200 循环依赖，固定 `PK-001 -> PK-200 -> PK-160`；决定本轮为普通内置模块化、legacy 控制台不动态化，并登记空上下文 Provider、稳定受控生成门面及 profile 原子切换/失败不变契约。PK-200 保持“待开始”，等待独立功能对话领取。
- 2026-07-21：独立 PK-200 对话完成领取并改为“进行中”。本对话目的为建立内置 `conversation` 分层、统一新旧文字/history/profile 接口、稳定受控文本生成门面与非秘密 profile 原子热切换。允许路径限定为本任务“负责路径”和“允许修改的边界”；非目标包括 PK-160 状态/写命令、PK-210 的 ASR/TTS/音频、PK-010/PK-100 契约、manifest/ZIP/生命周期及任何真实外部模型调用。数据边界固定为只拥有进程内聊天 history 与注入的临时 profile 测试文件；不读取或修改真实 `.env`、`server/data/llm_profile.json`、记忆/好感度及其他个人状态，保留混合工作区全部既有修改且不暂存、不清理。
- 2026-07-21：建立 `server/features/conversation/`：`models/context` 定义公开模型和空/只读 Provider，`repository` 负责严格非秘密 profile 与唯一临时文件 `flush/fsync/os.replace`，`client/provider` 是唯一 OpenAI-compatible HTTP 实现，`runtime` 独占活动 client、20 轮/40 条 history 和操作锁，`service` 提供 chat、history、稳定 `TextGenerator` 及串行 profile 更新，`router` 提供版本化 HTTP。`core/llm_engine.py` 仅兼容导出，`core/dialogue_manager.py` 只保留 voice/既有记忆命令接缝且不导入 `MemoryStore`。
- 2026-07-21：新增 `POST /api/v1/conversation`、`GET/DELETE /api/v1/conversation/history`、`GET/PUT /api/v1/llm-profile`。保留 `/chat`、`/chat/text-only`、`/history`、`/history/clear`、`/ws/chat`、`GET/PUT /dashboard/llm/profile`；新旧文字/profile 均委托同一 service。`/chat` 与 WebSocket 仍只在兼容层装配 TTS，versioned conversation 不触发音频；QQ 的 `message + with_audio=false` 契约保持。
- 2026-07-21：角色 prompt 继续从 `server/prompts/kei_system.txt` 加载并保留内置兜底。回复只接受既有六种情绪，未知标签清理后回退 `calm`；用户可见文本和 history 中不保留情绪标签。chat 在一次锁内生成并追加完整 user/assistant 对，失败返回既有可理解兜底；清 history 只清内存。Provider 空值/异常安全降级，不泄露上下文；应用装配层可选包装既有 `MemoryStore.prompt_context`，conversation 本身不导入或写 PK-160 数据。
- 2026-07-21：profile 只接受/保存/返回 `provider/base_url/model/thinking_mode/updated_at`；严格拒绝未知字段、非 `deepseek/custom`、非 HTTP(S)、userinfo、query/fragment、空/超长模型及损坏时间，custom 自动禁用 thinking。浏览器 profile 控制只接受本机 `8000` 同源 Origin；额外秘密字段用固定 422 拒绝且不回显输入。文件缺失使用环境默认，损坏只回退不覆盖；API Key 只在 composition 内交给 client，未进入 profile、响应、目录或错误。
- 2026-07-21：热切换先在串行 update 锁中建立并测试候选；候选测试期间普通 chat 可完整使用旧 client。提交时在 runtime 操作锁内先原子保存 profile、再替换活动指针，最后关闭旧 client；history 由稳定 runtime 所有，因此无需复制且切换保留。测试/取消/保存/提交失败关闭候选并保持旧 runtime、history、内存 profile 和文件；旧 client 关闭失败只记录无异常详情警告。普通 chat/受控生成在同一操作锁内用完 client，不会取得已关闭实例。
- 2026-07-21：PK-900 首轮集成退回一个 shutdown 阻断：旧 `runtime.close()` 释放操作锁后才关闭且无终态，使并发 chat 可触碰 closed client 并写 fallback history，阻塞候选也可在 service close 后提交。整改为 runtime 在操作锁内标记 closed、创建唯一 close task并让重复 close 等待同一任务；service 增加 lifecycle lock/closed 状态，与 chat、生成、probe、commit、close 共享提交边界。已进入操作会完整结束，新操作在接触 client 前拒绝；关闭后受控生成返回 `service_closed` fallback，chat/profile update 不写 history/profile。service 登记当前候选并在 close 时立即启动其唯一关闭任务；候选测试之后的成功、失败或取消路径只复用该任务且不得 commit。
- 2026-07-21：`DailyBriefingService`、voice 的 `DialogueManager`、生命维持提醒和斩妖复盘均改为持有同一个稳定 conversation/TextGenerator 门面，不缓存原始 engine；受控生成不写 chat history，返回 `generated/fallback/model/error_code`。timeout、连接/DNS、401/403、429、5xx、非 JSON、缺 choices、空回复均转为有限错误码；chat 使用 Kei 兜底，其他消费者保留各自业务 fallback，不返回上游正文、Authorization、系统提示、长期上下文或调用栈。
- 2026-07-21：网络副作用仅发生在显式 chat、内部受控生成、显式 `check_llm=true` 健康探测或 profile PUT 候选测试时，目标为所选 OpenAI-compatible `/chat/completions`；profile GET、打开控制台、history 操作和损坏 profile 回退不联网。代码部署后需重启 API；一次成功 profile PUT 热切换无需重启。限制保持为单用户、单主进程、history 不跨重启；PK-160 后续接正式 Provider，PK-210 继续拥有 ASR/TTS/音频。
- 2026-07-21：新增 `test_conversation_module.py`、`test_llm_profile.py`、`test_conversation_consumers.py`；共同覆盖新旧/QQ API、情绪、history、空/假/故障 Provider、MockTransport 上游失败、profile 规范化/损坏/原子保存、测试失败、保存回滚、旧关闭失败、成功切换、消费者一致性、并发更新/chat 和秘密不回显。测试入口显式覆盖到不存在的临时 env/profile；`tests/_path_setup.py` 改为尊重 `PROJECT_KEI_ENV_FILE`，后续隔离测试不再无条件加载真实 `.env`。
- 2026-07-21：实际通过 `test_conversation_module.py`、`test_llm_profile.py`、`test_conversation_consumers.py`、`test_feature_catalog.py`、`test_dashboard_shell.py`、`test_demon_review_kei.py`、`test_voice_demon_intents.py`、`test_voice_calendar_intents.py`、`test_daily_briefing_summary_cache.py`，以及相关文件 `compileall` 和 `git diff --check`。API-import 测试在受限沙箱中记录了既有 focus runtime 目录的只读 `PermissionError` 并由应用既有隔离逻辑跳过，不影响测试结论。未运行会真实联网/付费/生成音频的 `test_llm_debug.py`、`test_voice_chat.py`、`test_mic_voice_chat.py` 或带 fetch/rewrite/voice 的手工脚本。
- 2026-07-21：shutdown 整改后完整重跑上述九组测试并全部通过；`test_llm_profile.py` 新增 close/chat、close/受控生成、已进入操作等待、阻塞候选 update、重复 close 和关闭后无 history/profile/client 副作用回归。相关 Python `py_compile` 与六个 dashboard JavaScript `node --check` 均通过；全部测试继续显式使用不存在的 env/profile 与虚构 Key，无真实网络调用。
- 数据副作用与隔离审计：只在系统临时目录创建并自动清理 fake profile/cache。首轮新增测试导入时发现既有 `tests/_path_setup.py` 会无条件加载真实 `server/.env`，该次测试进程因此读取了环境变量值，但未打印、序列化、写入 profile 或发起任何网络请求；随后立即改为尊重 `PROJECT_KEI_ENV_FILE`，最终全部记录测试均以不存在的测试 env/profile 重跑通过。全程未读取或修改真实 `server/data/llm_profile.json`、memories/affection、音频、缓存或其他用户状态，未调用真实 LLM/ASR/TTS/QQ/采集，未暂存、提交、推送或清理工作区。
- 遗留/集成关注：请 PK-900 按报告第 508 行后的两条 shutdown 竞态夹具复验；总控仍应复核版本化主入口按最新授权为 `POST /api/v1/conversation`（不是另建 `/api/v1/conversation/chat`）、legacy 面板单一性、PK-160 正式 Provider 后续接入和 PK-210 音频所有权。功能对话不自行改为“已完成”。
- 2026-07-21：PK-900 完成首轮阻断整改复验并提交最终“通过”报告后，PK-000 独立审阅 runtime/service 生命周期锁、profile repository、client 错误净化、新旧路由、Provider、QQ/voice/briefing/提醒/复盘消费者、legacy 控制台、catalog、README 和架构文档。PK-000 重跑九组 fake/MockTransport 回归，并主动复现“候选测试成功但 `os.replace` 保存失败”与“候选测试并发期间对话”场景：前者确认旧模型/history/profile 文件不变、候选只关闭一次且旧 client 继续服务；后者确认提交前对话完整使用旧模型、提交后切到新模型、history 成对保留且旧 client 只关闭一次。另补验候选测试取消无切换、无落盘。受保护路径前后无状态输出，最终接受报告并将 PK-200 置为“已完成”。
- 2026-07-30 可安装化增量：新增 `package_source/manifest.json`、
  `config.schema.json` 和动态 `dashboard/index.js`。manifest 固定
  `conversation@1.0.0`、`in_process`、`backend.register`、两个版本化 namespace、
  全部现有 chat/history/WebSocket/profile legacy 路径、`local_state`、卸载保留
  数据与重启语义；配置只声明 `LLM_API_KEY` 环境变量名，不保存值。
- 2026-07-30 可安装化增量：新增 `module.py`，在装配前拒绝同 method/path 的
  既有 conversation 路由，成功后一次性注册版本化与 legacy router，并在
  `app.state` 暴露稳定 service、生成 Provider 和 close 接缝。legacy
  `/chat`/`/ws/chat` 只接受可选音频 synthesizer，conversation 包不拥有 TTS；
  可选命令处理与上下文只通过注入协议取得，不导入 PK-160 实现。
- 2026-07-30 可安装化增量：`router.py` 的 `include_legacy` 接缝让新旧 chat、
  history 与 profile 使用同一 `ConversationService`；现有内置调用默认仍只注册
  versioned router，因此共享 `api.py` 未完成串行迁移前不会产生第二套路由。
  Kei 提示优先读取包内 `backend/kei_system.txt`，开发树继续回退
  `server/prompts/kei_system.txt` 和既有内置提示。
- 2026-07-30 可安装化增量：PK-010 在无事件循环的应用装配阶段调用
  `register(app)`。为兼容本机 Python 3.8/3.10 迁移环境，conversation 三把
  `asyncio.Lock` 改为首次异步请求时绑定主循环的 `LazyAsyncLock`；锁的数量、
  关闭终态、chat/history 原子性和 profile 串行提交语义不变。WebSocket、并发
  profile/close 与重启装载测试均覆盖该接缝。
- 2026-07-30 可安装化增量：新增确定性 `package_builder.py`。构建器只复制
  明确 `BACKEND_FILES`、Kei 提示、manifest、配置声明和面板，统一 UTF-8 LF，
  使用固定 ZIP 时间/权限元数据和 `ZIP_STORED`；两次构建字节与 SHA-256 完全
  一致。包扫描确认不含 `.env`、API Key、profile、history、长期记忆、好感度、
  缓存、模型、runtime 状态、vendor、安装脚本或本机绝对路径。
- 2026-07-30 Release 交接：fragment 为
  `module-conversation-v1.0.0` / `conversation-1.0.0.zip`；最终确定性 ZIP
  `package_size=69032`、`package_sha256=62006de611b1413e48266648f7e4f8f73c449488c72f64fedb20e466372aac0a`，
  根 manifest SHA-256 为
  `8f5dd55b672fd9f67bfab88b29d02c8bebe1b934bce1dd182a70f70840c11411`。
  `official-catalog-entry.json` 已由共享 Catalog 构建器从临时 ZIP 精确重建并
  匹配；本任务未修改共享 Catalog、未创建 Release 或上传资产。
- 2026-07-30 生命周期与数据：临时 ModuleManager 已覆盖安装→配置检查→启用→
  重启装配→profile 热切换→再次重启→停用→卸载保留 profile→重装恢复，以及
  精确 purge 只删除临时 `data/modules/conversation`、不删除外部 profile。
  普通 history 仍只在单用户主进程内，模型切换保留，重启不持久化。包的网络
  副作用仍仅来自显式 chat、受控生成、probe 或 profile 候选测试。
- 2026-07-30 动态面板：保留 `llm-preset`、`llm-base-url`、`llm-model`、
  `llm-thinking`、`apply-llm`、`llm-status` ID 与“测试并应用”语义；只使用
  `/api/v1/llm-profile`，失败后重新读取活动方案，不写 localStorage、
  sessionStorage 或 IndexedDB，不显示/编辑 API Key。
- 2026-07-30 共享串行阻断：冻结的 `server/api.py` 当前仍顶层导入
  `features.conversation`、内置注册 conversation 路由并让 voice、briefing、
  提醒、复盘直接持有该 service。PK-000 必须在共享窗口删除内置装配，改为从
  Core 稳定 Provider 读取 `app.state.conversation_service` 或空实现，并在
  lifespan 调用 `conversation_service_close`；否则“未安装 conversation 时真实
  Core 可启动”和“消费者统一降级”尚未在生产 composition 成立。本任务没有反向
  import Core/其他包或越界修改共享文件。
- 2026-07-30 验证：`test_conversation_package.py` 通过，覆盖确定性包/Catalog、
  配置缺失、安装生命周期、新旧 HTTP、QQ text-only、WebSocket、动态音频接缝、
  history/profile、上下文、生成 Provider、停用/卸载/重装、purge 隔离、错误
  原子性、重复注册和预存路由冲突；全部使用 fake client、虚构 Key 和临时目录。
  `test_llm_profile.py` 通过；`test_conversation_module.py` 的 runtime/HTTP
  子集通过；`test_installable_modules.py`、`test_focus_module.py` 通过。
  完整 `test_conversation_module.py`、`test_conversation_consumers.py`、
  `test_feature_catalog.py` 和 `test_dashboard_shell.py` 当前在导入共享
  `api.py` 时被并行 PK-134 `features/rss_intel/provider.py:50` 在本机
  Python 3.8 下的类型别名 `TypeError` 阻断，异常发生在 PK-200 用例前；本任务
  未修改该路径，交 PK-000/PK-134 在共享批次修复后复跑。
- 2026-07-30 晚装配整改：PK-000 全量串行审计确认 `affection_memory` 强依赖
  `conversation`，拓扑会先注册 conversation；旧 `_create_service()` 会把该时刻
  尚不存在的 `app.state.conversation_context_provider` 固化为空 Provider。
  `AppStateConversationContextProvider` 现改为每次 `get_context()` 才解析当前
  app-scoped Provider；缺失、指向自身、无同步 `get_context`、异常、awaitable 或
  非字符串结果均静默返回空字符串。conversation 不导入 PK-160，也不读取其
  repository、文件或可变状态；注册前显式注入的结构 Provider仍通过相同代理兼容。
- 2026-07-30 晚装配永久回归：conversation 先完成一次空上下文请求，随后注入
  fake affection Provider 的下一次请求立即只读新文本；解除 Provider 后恢复空，
  故障/非结构/非字符串/self Provider 均降级。阻塞 fake LLM 固定并发时序后，
  Provider A 请求只包含 A，运行时替换后的 Provider B 请求只包含 B，未跨请求
  泄漏。回归位于 `test_conversation_package.py`，全程使用虚构 Key、临时 profile
  与 fake client。
- 2026-07-30 晚装配 Release：从同一 allowlist 构建器连续构建并由共享 Catalog
  构建器核对；最终 `conversation-1.0.0.zip` 为 `69032` bytes，SHA-256
  `62006de611b1413e48266648f7e4f8f73c449488c72f64fedb20e466372aac0a`；
  manifest 未变，SHA-256
  `8f5dd55b672fd9f67bfab88b29d02c8bebe1b934bce1dd182a70f70840c11411`。
  只更新 conversation 专属 Catalog 条目，未修改共享 Catalog 或发布资产。
- 2026-07-30 晚装配验证：通过 `test_conversation_package.py`、
  `test_conversation_module.py`、`test_llm_profile.py`、
  `test_conversation_consumers.py`、`test_affection_memory_module.py`、
  `test_voice_module.py`、`test_voice_installable_module.py`、
  `test_daily_briefing_module.py`、`test_daily_briefing_installable.py` 和
  `test_daily_briefing_summary_cache.py`。`test_affection_memory_installable.py`
  的真实 loader 结果为 conversation、affection_memory 依次 `loaded`，但该
  PK-160 冻结测试仍断言旧的反向结果顺序，交 PK-000/PK-160 更新断言后复跑；
  `test_daily_briefing_voice.py` 是直连运行中本机 8000 API 的手工检查而非 fake
  测试，因服务未启动收到连接拒绝，不纳入本轮离线验收。未读取真实 `.env`、
  profile、长期记忆或好感度文件，未调用真实/付费 LLM。
- 2026-07-30 生命周期回收整改：conversation 包根现公开幂等异步
  `unregister(app)`。`register` 为本次创建的 service、受控生成 Provider、
  close callback 和注册标记保存私有 ownership；卸载始终关闭该 owned service，
  但仅在 `app.state` 当前值仍与本模块原值身份相同时删除引用。后装配或外部替换的
  state 值保持不变，`conversation_context_provider`、affection_memory Provider、
  repository 和数据均不在清理范围。close 异常完成 state 清理后只抛固定
  `conversation service cleanup failed`，不回显异常正文、profile 路径或 Key；
  重复调用不重复关闭。
- 2026-07-30 生命周期回归：临时 ModuleManager 使用实际 conversation ZIP
  完成 register→`unload_one_async`，验证 client 只关闭一次、路由恢复、五个
  module-owned state 引用清除、affection Provider 保留；再次 loader unload 和
  直接重复 unregister 均安全。另验证外部替换的 service/close 引用不被删除，以及
  close 抛出含虚构 Key/路径的异常时只返回固定脱敏错误。
- 2026-07-30 未发布资产按不可复用原则从 `1.0.0` 提升到 `1.0.1`：
  Release tag `module-conversation-v1.0.1`，asset
  `conversation-1.0.1.zip`，最终大小 `70860` bytes，ZIP SHA-256
  `3e39953da6f83d83d54d13ad023e7c779179fb6fdc6d03084b57d8c7b9105e16`，
  manifest SHA-256
  `fd560a74496c46c9b745cbd25d85b3edf0983a7632630fc5912ff60074ec06ce`。
  两次 allowlist 构建保持字节稳定，专属 release fragment/Catalog 条目已同步；
  未修改共享 Catalog 或创建/上传 Release。
- 2026-07-30 生命周期验证：`test_conversation_package.py`、定向 async
  unregister、`test_llm_profile.py`、`test_affection_memory_module.py`、
  `test_voice_installable_module.py` 和 `test_daily_briefing_module.py` 通过。
  当前混合工作区的共享 `api.py` 已移除旧 `api.conversation_service`，使冻结的
  `test_conversation_consumers.py` 旧全局断言失败；同文件另新增 Python 3.9+
  `dict[str, Any]` 注解，导致本机 Python 3.8 在完整
  `test_conversation_module.py` 导入阶段失败，均发生在 PK-200 用例前。
  `test_daily_briefing_installable.py` 还因其并行任务 Release 条目与当前构建摘要
  不一致失败。PK-200 未越界修改这些共享/其他模块路径。完整 package 测试的预存
  路由失败夹具还揭示共享 loader 的同步失败回滚会直接调用 async unregister 而
  不 await，产生 RuntimeWarning；成功装载后的通用异步 shutdown
  `unload_one_async` 已由本轮回归证明可完整回收，失败回滚接缝交 PK-000/PK-010
  统一修正。

## 完成文档门禁

任务进入“待集成”或“已完成”前必须全部勾选；不适用项也必须写明原因。

- [x] TASK_RECORD — 已追加可安装包结构、接口、Provider/legacy 接缝、确定性
  Release、profile/history/网络副作用、生命周期、重启、验证和共享装配遗留。
- [x] TASKS_BOARD — PK-000 已把 PK-200 重新置为进行中并补 PK-010/PK-100
  依赖；本对话按明确冻结不修改 `TASKS.md`，待集成状态由 PK-000 串行回写。
- [x] PUBLIC_README — 本增量不适用：PK-011 冻结共享 README，由 PK-000 在
  本地业务批装配后统一写入真实安装/启停/卸载和无包降级说明。
- [x] MODULE_CATALOG — 本增量不直接修改冻结 Catalog；已交付通过共享构建器精确
  重建的 `release/official-catalog-entry.json`，等待 PK-000 合并。
- [x] ARCHITECTURE_DOCS — 本增量不直接修改冻结架构文档；conversation 自有
  README 已记录 package、register、Provider、数据和 PK-000 串行接缝。
- [x] LOCAL_README — 不适用：没有改变本机路径、启动器、解释器、端口或环境位置。
- [x] AGENT_RULES — 不适用：没有改变 agent 工作流、安全、验证、文档或 Git 政策。
- [x] VALIDATION — 已记录通过项、被 PK-134 并行导入错误阻断的共享 API 测试、
  Python compileall、动态面板 `node --check`、文档门禁与 `git diff --check`；
  全程未读取真实秘密/profile/个人状态，未联网调用 LLM 或执行 Git 发布。

## 独立对话启动提示

```text
继续 PK-011 本地业务批的 PK-200 共享装配与复验。读取本任务 2026-07-30
可安装化记录、PK-011、PK-010/PK-100 和模块包契约。conversation 专属包已交付；
由 PK-000 在冻结共享窗口移除 api.py 内置 import/router/lifespan，接入 Core
generation/context Provider 的空实现和 package app.state 接缝，合并官方 Catalog
与 README，再复跑任务记录中被 PK-134 并行导入错误阻断的四组共享 API 测试。
不得读取真实 Key/profile/记忆，不得把 legacy 与包路由同时装配，不得直接导入
runtime 包内部动态名称。
```
