# PK-160 — 好感度与长期记忆

- 状态：待集成
- 优先级：P2
- 所属模块：`affection_memory`
- 依赖任务：PK-001、PK-010、PK-100、PK-200
- 负责路径：`server/features/affection_memory/**`（等价统一模块目录，内部保持 relationship/memory 两个数据所有权）、`server/systems/affection_system.py` 与 `server/core/memory_store.py` 兼容门面、本任务定向测试和任务文件；共享文件仅允许修改 `server/api.py` 的 relationship/memory/provider 装配与 legacy 委托、`server/core/dialogue_manager.py` 的既有记忆命令接缝、catalog/既有控制台对应 hunk 及 README/架构说明
- 当前对话：2026-07-22 由 PK-000 完成数据路径审计、边界登记并授权独立实施；不启动 PK-900

## 目标

把既有好感互动状态与长期记忆收敛为两个数据所有权独立、可组合的内置模块边界，保留旧数据和 legacy 接口，并实现 PK-200 已冻结 `ConversationContextProvider` 协议的正式只读适配器。conversation 只消费经过筛选、长度有界的文本，不获得状态对象、repository 或写能力。

## 不在本任务内

- 不修改 PK-200 的 `ConversationContextProvider.get_context() -> str`、ConversationService、Provider/Profile、模型热切换、system prompt、history 或受控生成契约；如现有协议不足，立即停止并交回 PK-000。
- 不让 `server/features/conversation/**`、LLM client/runtime/repository 反向导入 relationship 或 memory；依赖仍为 `PK-001 -> PK-200 -> PK-160`，只由主应用 composition 注入 Provider。
- 不合并 relationship 与 memory 状态文件，不与斩妖、健身、专注、日历、QQ、情报或 voice 状态合并，也不扩张这些任务的所有权。
- 不制作安装包、manifest、启停生命周期或动态面板；现有 legacy 控制台保持兼容。
- 不新增账户、多用户、向量数据库、embedding、云同步、自动遗忘、批量导入或聊天历史持久化。
- 不把普通聊天自动写成长记忆，不改变既有显式记忆命令语义；任何新增写入都必须来自明确的 memory API/命令。
- legacy `POST /affection/reset` 与 `POST /memories/clear` 作为危险兼容入口保留，本轮默认不增加版本化全量清除、不在控制台新增入口，也不得用于真实状态或自动测试。

## 接口契约

- 当前兼容接口：`GET /affection/status`、`POST /affection/event`、`POST /affection/choose`、`POST /affection/reset`；`GET/POST /memories`、`DELETE /memories/{memory_id}`、`POST /memories/clear`；既有显式记忆命令接缝保持兼容。
- 目标 relationship API：`GET /api/v1/relationship/status`、`POST /api/v1/relationship/events`、`POST /api/v1/relationship/choices`。
- 目标 memory API：`GET /api/v1/memories`、`POST /api/v1/memories`、`DELETE /api/v1/memories/{memory_id}`。默认不新增版本化全量 clear；若确需增加，必须先由 PK-000 决定精确确认契约。
- 新旧接口必须委托各自同一 service/repository，不能维护两套好感、事件、选择或记忆规则。relationship 和 memory 可以由一个公开 facade 组合读取，但不得互相写对方文件。
- 正式 `RelationshipMemoryContextProvider`（名称可等价）实现 PK-200 已有 `ConversationContextProvider`。`get_context()` 每次只读获取最新数据，返回已筛选、确定性、长度有界的字符串；不得返回 raw JSON、内部 ID、完整事件历史、repository、写函数或异常正文，不得记录上下文内容。
- Provider 只向 conversation 提供批准的 relationship 概览与记忆文本；Provider 失败由 PK-200 既有空上下文降级处理。PK-160 不改写该降级，不缓存 conversation client，也不写 conversation history。
- 被调用方：conversation 通过只读 Provider 消费上下文；legacy 控制台/记忆命令通过公开 service/API 消费，不得直接访问状态文件。

## 数据所有权

- 2026-07-22 仅做存在性/Git 状态审计：`server/data/affection_state.json` 存在且定向 Git 状态无输出；`server/data/memories.json` 存在且定向 Git 状态无输出。未读取、打印或 diff 内容。
- 当前代码差异：`server/systems/affection_system.py` 的默认候选为不存在的 `server/systems/data/affection_state.json`；主应用 memory 明确使用现存 `server/data/memories.json`。`server/systems/data/memories.json` 也不存在。
- 本任务把现存 `server/data/affection_state.json` 与 `server/data/memories.json` 视为受保护个人数据和 composition root 应显式注入的兼容路径；不得自动创建 `systems/data` 同名文件，不得在两个位置之间猜测、合并、复制、移动或迁移。
- 未经用户明确授权，不得读取或打印真实好感、事件、选择、记忆内容、标签、来源、时间或上下文文本；不得查看详细 diff、格式化、重置、覆盖、暂存或提交这两个文件。
- 自动测试必须向 relationship/memory repository 显式注入系统临时路径和虚构数据；Provider 测试使用 fake consumer，不启动真实/付费模型，不调用网络、voice、QQ 或其他个人系统。
- relationship 只拥有好感分数/阶段、事件/选择及必要幂等状态；memory 只拥有显式长期记忆条目。持久化应原子化，损坏文件显式失败，写入失败不得留下半状态或覆盖旧字节。

## 实施清单

- [x] 审阅 affection、memory、API、控制台、显式记忆命令和现有测试；保持真实数据完全不读。
- [x] 建立 relationship 与 memory 各自的 models/repository/service/router 边界或等价清晰分层，并由主应用显式注入现存 `server/data/*` 路径。
- [x] 装配 `/api/v1/relationship/*` 与 `/api/v1/memories*`，让 legacy 接口委托相同 service；危险 legacy reset/clear 只保留兼容。
- [x] 实现正式只读 `ConversationContextProvider`，替换主应用当前 `CallableConversationContextProvider(memory_store.prompt_context)` 过渡装配，不修改 PK-200 公共代码或契约。
- [x] 保持既有好感事件/选择与显式记忆增删/命令兼容；验证 relationship 与 memory 写入互不影响。
- [x] 更新 catalog、README、模块架构和本任务记录；共享文件只改本任务相关 hunk。
- [x] 使用临时 repositories、fake context consumer 运行新旧 API、provider、conversation、控制台和数据隔离回归，再执行文档门禁、`git diff --check` 与受保护路径状态检查。

## 验收标准

- 两个现存用户文件不被读取、打印、diff、迁移、重置或覆盖；不存在的 `systems/data` 同名文件不会因导入、只读状态、Provider 调用或自动测试而创建。
- 旧好感/记忆 schema 可用临时夹具兼容验证；损坏结构和原子保存失败明确报错并保留旧字节，不能用空状态静默覆盖。
- relationship 新旧 API 共用一套规则，memory 新旧 API/显式命令共用一套规则；写 relationship 不改变 memory，写 memory 不改变 relationship。
- 正式 Provider 满足既有 `ConversationContextProvider`，仅返回批准、确定性、长度有界的只读文本；无 raw 状态、内部对象、写方法、完整事件历史或异常正文泄露。
- conversation 在 Provider 存在、返回空、抛错或数据不可用时均保持 PK-200 既有启动、history、profile 和降级语义；PK-200 文件和公共契约无修改。
- 正常 chat 可以读取最新批准上下文，但不自动新增/删除记忆、不改变好感，也不把上下文写入 history、日志或错误响应。
- legacy reset/clear 保持旧客户端兼容但不在 versioned API/控制台新增暴露，自动测试不调用默认 store 或真实路径。
- PK-150、PK-170、PK-190、voice、QQ、情报和其他用户状态没有所有权扩张；混合工作区无关修改保持不动。

## 工作区入场记录

- PK-001、PK-200 在总板和任务文件中均为“已完成”，PK-160 依赖满足。
- 当前工作区为混合状态，含 conversation、voice、calendar、focus、demon、情报来源、QQ、个人状态和其他用户修改。独立任务必须逐 hunk 保留，不得整理、覆盖或吸收无关差异。
- 真实路径审计只调用 `Test-Path` 与定向 `git status --short --ignored`；两个现存 `server/data/*` 文件未显示修改、未跟踪或忽略状态，两个 `server/systems/data/*` 候选不存在。未读取文件内容、大小、时间戳或详细差异。
- 本轮只把 PK-160 登记为“进行中”；PK-900 保持上一批“已完成”，不登记或启动新批次。

## 工作记录

- 2026-07-22：完成 `server/features/affection_memory/` 内置分层。`event_catalog.py` 固定迁移前全部等级、数值上下限、八类事件、选项、影响和回复；`models.py` 定义公开请求/领域结果；`repository.py` 分别实现 relationship/memory 数据所有权；`service.py` 分别实现事件/选择/限幅/reset 与记忆增删查/clear/中文命令/上下文筛选；`context.py` 提供正式只读 Provider；`router.py` 统一新旧 HTTP；`compatibility.py` 统一旧 Python 与语音命令适配。旧 `systems/affection_system.py`、`core/memory_store.py` 不再拥有第二套规则。
- 实际 relationship 接口：`GET /api/v1/relationship/status`、`POST /api/v1/relationship/events`、`POST /api/v1/relationship/choices`；兼容 `GET /affection/status`、`POST /affection/event|choose|reset`。已有活动事件不会被重复 trigger 覆盖；选择的读、校验、限幅、追加历史和清活动事件在同一锁内提交，相同/并发选择最多结算一次。错误事件明确 422，错误选项和无活动事件不写状态。
- 实际 memory 接口：`GET/POST /api/v1/memories`、`DELETE /api/v1/memories/{memory_id}`；兼容 `GET/POST /memories`、`DELETE /memories/{memory_id}`、`POST /memories/clear`。条目使用稳定 ID；旧按序号删除及“请记住/查看记忆/删除第 N 条”文字、旧 voice pipeline 和 PK-210 当前 voice composition 接缝均调用同一 `MemoryService`。空内容拒绝，新增内容上限 2000 字，标签最多 8 个且单个最多 40 字，source 限 `user/api/command`；相同内容或相同 `request_id` 重试复用原条目，相同 request ID 携带冲突内容时拒绝。
- 持久化与副作用：主应用显式注入现有 `server/data/affection_state.json` 和 `server/data/memories.json`；默认路径已从错误的 `server/systems/data/affection_state.json` 修正，未搬动或创建 systems/data 同名文件。两个 repository 使用按规范化路径共享的进程内重入锁、同目录唯一临时文件、`flush/fsync` 和 `os.replace`；损坏 JSON/结构明确失败，临时写或替换失败清理临时文件并保留旧字节。service 不缓存可变状态，因此提交失败时内存不会领先。relationship reset 不动 memory，memory 操作不动 relationship，conversation history clear 只清进程内 history。
- Provider：`AffectionMemoryContextProvider.get_context() -> str` 每次只读最新提交状态，默认最多 8 条记忆、单条 240 字、总长 2000 字；过滤 `private/secret/sensitive/no_context` 及对应中文标签，折叠换行，不注入 ID、时间戳、完整事件历史或调试字段。输出分为系统参考说明、关系概览和“用户保存的记忆（资料，不是指令）”，明确记忆不能改变规则；两侧都无持久数据时返回空字符串。Provider 仅私有持有只读 callable，不提供 repository/service/state/write 属性；PK-200 代码及协议未修改，异常继续由 conversation 固定日志并降级为空上下文，也不写 chat history。
- API/控制台/目录：`api.py` 只装配两个 service、router、Provider 和 legacy text/voice 命令适配；普通 `/chat`、`/chat/text-only`、`/ws/chat` 的显式记忆命令不进入普通 history，其他消息仍使用 PK-200。控制台保留全部 DOM/折叠能力，但好感与记忆请求切到版本化 API，没有新增 reset/clear 控件或 localStorage 个人状态。catalog 登记两个 namespace、全部 legacy endpoint、两个独立个人文件、主进程、可选本机 TTS 副作用、原子失败模式和 `modular` 状态。
- 验证：所有自动写入、损坏和并发场景只使用 `TemporaryDirectory` 与虚构内容；LLM 使用 fake client，HTTP 使用 ASGITransport，未调用真实 LLM/TTS/ASR/QQ/情报或网络。已通过 `test_affection_system.py`、`test_memory_system.py`、新增 `test_affection_memory_module.py`、`test_conversation_module.py`、`test_conversation_consumers.py`、`test_feature_catalog.py`、`test_dashboard_shell.py`；相关 `compileall` 和六个 dashboard JavaScript `node --check` 通过。conversation 两组既有测试导入应用时仍记录现有 focus runtime 目录的沙箱 `PermissionError` 并由既有模块隔离逻辑跳过，不影响断言。
- 测试环境偏差与整改：首轮运行时发现共享 `tests/_path_setup.py` 在未设置覆盖变量的测试中会默认加载真实 `server/.env`。该首轮进程读取了环境变量值，但没有打印、序列化、写入状态或发起网络/外部服务调用；发现后立即在本任务涉及的 affection、memory、新增模块、catalog、dashboard 测试入口中于导入 helper 前设置指向不存在文件的 `PROJECT_KEI_ENV_FILE`，conversation/consumer 原本已有相同隔离。最终记录矩阵已全部在不存在的测试 env 下重跑。未读取或输出任何具体 `.env` 值。
- 真实状态隔离：入场与交接均仅以 `Test-Path` 和定向 `git status --short -- <四个候选路径>` 检查存在性/状态；最终仍确认两个 `server/data/*` 文件存在、两个 `server/systems/data/*` 候选不存在，定向 Git 状态无输出。全程未读取内容、大小、时间戳或详细 diff，未格式化、迁移、reset、覆盖、暂存或提交真实好感度/记忆数据。
- 遗留/集成关注：危险全量操作继续只保留 legacy `/affection/reset`、`/memories/clear`，按冻结任务契约未新增版本化 clear。锁覆盖单主 API 进程内并发；如果未来允许独立多进程脚本与 API 同时写同一文件，应由总控另行决定跨进程锁协议。部署代码/控制台后需重启 API；本任务未启动服务或执行真实手工请求。

### PK-900 阻断项整改记录（2026-07-22）

- HTTP 安全边界：为 `/api/v1/relationship*`、`/api/v1/memories*`、`/affection*` 与 `/memories*` 增加统一的本机客户端与可信 Origin 保护。`AffectionMemoryOriginGuardMiddleware` 装配在通配 CORS 外层，覆盖全部实际读写和 OPTIONS 预检；恶意 Origin 或非本机客户端在进入路由/repository 前返回固定 403 且不获得 CORS 允许头。router 对 status/event/choice/reset/list/add/delete/clear 再执行可注入的同一控制检查。`http://127.0.0.1:8000`、`http://localhost:8000`、等价 IPv6 本机控制台以及无 Origin 的本机 CLI 保持兼容。未扩大到其他任务接口或改变全局 CORS。
- 迁移前活动事件兼容：relationship repository 现在接受与冻结 `EVENTS` 逐字段一致、但缺少 `instance_id` 和/或 `created_at` 的旧活动事件。缺失 identity 由事件 ID、规范 stats 与历史长度确定性派生，缺失时间只在加载后的内存副本中表示为空；重复 status、legacy/versioned status 和 relationship context 均不保存、不改写文件。成功 choice 继续在共享路径锁内清除活动事件并原子提交，40 路 versioned/legacy 混合并发只结算一次；未知事件、冻结字段篡改、非法显式 identity/时间仍失败关闭。
- 整改验证：所有新增场景均在 `TemporaryDirectory` 中使用虚构 marker、fake/ASGITransport 和显式临时 repository。恶意 Origin 覆盖新旧 status/event/choice/reset、memory list/add/delete/clear 以及 POST/DELETE 预检，并断言 403 响应不含虚构个人内容、无 CORS 允许头且旧字节不变；另覆盖可信 `127.0.0.1:8000`/`localhost:8000`、无 Origin 本机 CLI、非本机客户端、缺失中间件时的 router 二次校验、旧事件稳定 identity/只读不改写/上下文可用/结算后合法状态、未知及篡改事件不覆盖。七项规定回归 `test_affection_system.py`、`test_memory_system.py`、`test_affection_memory_module.py`、`test_conversation_module.py`、`test_conversation_consumers.py`、`test_feature_catalog.py`、`test_dashboard_shell.py` 全部通过；相关 Python `compileall` 与六个 dashboard JavaScript `node --check` 通过。conversation 两项仍只出现既有 focus runtime 沙箱 `PermissionError` 的模块隔离提示，不影响断言。
- 状态与范围：PK-160 保持“待集成”，PK-900 保持“进行中”；未改动 PK-200 公共协议、conversation 依赖方向、控制台 DOM/localStorage、安装包/manifest/进程或其他任务业务。未读取、打印、diff、迁移、格式化、清空或覆盖真实 `server/data/affection_state.json` 与 `server/data/memories.json`；整改写入只发生在系统临时目录。

## PK-011 生命周期整改（2026-07-31）

- `affection_memory@1.0.1` 现按实例清理路由、context Provider、module state 与精确
  Origin middleware 描述符；若宿主后来替换 `conversation_context_provider`，卸载
  保留替换对象。注入 middleware 后失败会回滚路由/state/middleware，重复
  `unregister` 幂等。

## 完成文档门禁

任务进入“待集成”前必须全部勾选；不适用项也必须写明原因。

- [x] TASK_RECORD — 已记录实际 relationship/memory/provider 功能、接口、数据副作用、验证、重启和遗留问题。
- [x] TASKS_BOARD — 已同步总板为“待集成”，名称/P2/PK-001、PK-200 依赖不变；未标记“已完成”。
- [x] PUBLIC_README — 已更新实际新旧接口、Provider、真实数据路径/不迁移边界、原子失败、重启、测试和限制。
- [x] MODULE_CATALOG — 已登记 relationship/memory 双 namespace、全部 endpoint、数据所有权、进程边界、TTS 副作用、失败模式和 `modular` 状态。
- [x] ARCHITECTURE_DOCS — 已在模块化单体规范记录双 repository、同 service 兼容、只读 Provider、composition 和单向依赖。
- [x] LOCAL_README — 不适用：没有新增或改变本机路径、启动器、解释器、端口或环境/秘密位置，未修改忽略的 `README.local.md`。
- [x] AGENT_RULES — 不适用：没有改变长期 agent 安全、验证、文档或 Git 规则，未修改 `AGENTS.md`。
- [x] VALIDATION — 最终在不存在的测试 env、临时 repository、虚构数据和 fake consumer 下通过上述七组测试、新增并发/原子/Provider/隔离及 PK-900 的 Origin/预检/旧活动事件兼容覆盖、相关 `compileall`、六个 dashboard JavaScript `node --check`、任务文档门禁和 `git diff --check`；受保护四路径最终存在性/状态复核符合入场记录。

## 独立对话启动提示

```text
继续 Project Kei 的 PK-160 好感度与长期记忆任务。先完整阅读根 README.md、
AGENTS.md、README.local.md（如存在）、TASKS.md、tasks/PK-160-affection-memory.md，
再检查 relationship、memory、conversation context 接缝和 git status。禁止读取或 diff
真实 affection_state.json、memories.json；所有测试注入临时 repository 与虚构数据。
只实现 relationship、memory、新旧 API 和正式只读 ConversationContextProvider；不得
修改 PK-200 公共契约或反向依赖。跨模块需求先停止并交回 PK-000。
```

## PK-000 最终复核（2026-07-22）

- 结论：通过。PK-160 与本批 PK-900 已由总控统一收口为“已完成”。
- 独立重跑七项规定回归，全部退出 0；另用 `TemporaryDirectory` 主动注入 relationship/memory 两类 `os.replace` 失败，旧字节与已提交状态均保持不变，临时文件无残留。
- 32 路并发选择同一活动事件时恰好一次 `resolved`、31 次 `idle`，历史只增加一条；清空临时 memory 不改变 relationship，重置临时 relationship 不改变 memory。
- 正式 Provider 满足 PK-200 `ConversationContextProvider`，读取不改写文件，不暴露 repository/service/write surface；私密标签内容、内部 ID 与时间戳不进入上下文。`server/features/conversation/**` 静态扫描未发现 PK-160、repository 或真实个人路径的反向导入。
- 新旧 API 的恶意 Origin、远端 client、预检、错误正文和 Provider 故障脱敏由正式回归覆盖；所有测试使用 fake/ASGITransport、临时状态和不存在的 env/profile/Voice Pack 路径，没有外部调用。
- 真实 `server/data/affection_state.json` 与 `server/data/memories.json` 仅检查存在性和定向 Git 状态；两者存在且状态无输出，两个 `server/systems/data/*` 同名候选不存在。未读取、打印、diff、迁移、清空、重置或覆盖真实内容。
- 相关 Python `compileall`、六项 dashboard JavaScript `node --check`、任务文档门禁和 `git diff --check` 通过。工作区其他任务、个人状态、缓存、环境文件和 `vendor/` 均保持原状；未暂存、提交、推送或清理。

## PK-011 可安装化增量（2026-07-30）

本节是 PK-000 重新打开的 PK-011 本地业务批增量，只覆盖
`affection_memory` 专属可安装化交付。此前“不制作安装包/manifest/动态面板”的
旧范围说明仅是 2026-07-22 内置模块阶段的历史记录，不再约束本增量。总任务板由
PK-000 维护，本轮未修改 `TASKS.md`。

### 实际交付

- `package_source/manifest.json` 声明模块 ID `affection_memory`、入口
  `backend.register`、依赖 `conversation`、两个版本化 namespace、全部 legacy
  endpoint、动态面板入口、`local_state` 权限、新 namespace
  `affection_memory`、卸载保留数据和重启生效语义。
- `package_builder.py` 只按显式 allowlist 收集 10 个后端文本文件、manifest 和
  `dashboard/index.js`，统一 UTF-8/LF、固定 ZIP 时间和元数据并使用
  `ZIP_STORED`，同一输入字节级确定。包内不含 relationship/memory 状态、
  profile、`.env`、缓存、模型资产、vendor、测试夹具或安装脚本。
- `module.register(app)` 只组装一套 `RelationshipService` /
  `MemoryService` 和同一新旧 router，拒绝外来重复路由并对自身重复注册幂等；
  Origin guard 随模块注册。默认仍指向历史
  `server/data/affection_state.json` 与 `server/data/memories.json`，也允许
  composition root 显式注入路径。构造和导入不会读取或创建数据文件。
- Provider 继续结构化实现 PK-200 的
  `ConversationContextProvider.get_context() -> str`，安装包运行时不导入
  conversation 内部实现。启用时仅把只读 Provider 放入 app-scoped
  `conversation_context_provider` 与包自有
  `affection_memory_context_provider` 接缝；未安装、停用或卸载并重启后的新 app
  不存在这些引用，conversation 使用自己的 Empty Provider。Provider 不暴露
  repository/service/state/write surface。
- 动态面板只通过挂载上下文提供的受限 `context.request` 调用
  `/api/v1/relationship` 与 `/api/v1/memories`，不使用 `fetch` 绕过外壳，不写
  localStorage，也不保存个人状态。该 `global fetch -> context.request` hunk
  最初由 PK-100 只读审计提出并受控修正，现由 PK-160 独立复核、认领并纳入
  专属回归；未修改或覆盖其他 PK-100 UI。
- `release/official-release-fragment.json`、
  `official-catalog-entry.json` 和 release README 记录 1.0.0 官方资产契约、
  SHA-256、大小、依赖、权限、重启与保留数据策略；未生成或保留实际 ZIP。

### 数据副作用与隔离

- 卸载只移除程序文件并保留历史 relationship/memory 文件；显式 purge 只允许
  ModuleManager 声明的新 `data/modules/affection_memory` namespace，不能触及
  两个历史路径。卸载重装测试确认临时历史数据仍可由新 Provider 读取。
- relationship reset 与 memory clear 继续委托各自 service：重置临时
  relationship 不改变临时 memory，清空临时 memory 不改变 relationship。
  相同事件选择经 versioned/legacy 混合重复提交只结算一次。
- 原子替换失败测试确认旧字节不变、无同目录临时文件残留；损坏临时文件的 API
  错误不包含虚构个人 marker、路径或异常堆栈。
- 真实 `server/data/affection_state.json` 与 `server/data/memories.json` 本轮只
  检查存在性和定向 Git 状态，两个文件存在且定向状态无输出；两个
  `server/systems/data/*` 候选不存在。未读取、打印、diff、迁移、打包、清空、
  格式化或覆盖真实内容。

### 验证

- 专属 `test_affection_memory_installable.py` 通过：确定性包、正式 release
  catalog 生成、allowlist/路径泄漏、动态入口、空 Provider、安装/启停/卸载重启、
  Provider 注册/解除、重复路由、重复事件、两类清除隔离、卸载重装保留、
  namespace purge、原子失败和错误脱敏均使用 `TemporaryDirectory`、
  fake conversation contract 与 `ASGITransport`。
- 既有七项回归通过：`test_affection_system.py`、`test_memory_system.py`、
  `test_affection_memory_module.py`、`test_conversation_module.py`、
  `test_conversation_consumers.py`、`test_feature_catalog.py`、
  `test_dashboard_shell.py`。conversation 两项仍只报告混合工作区既有 focus
  runtime 沙箱 `PermissionError` 隔离提示，不影响断言。
- 专属 Python `compileall`、动态面板 `node --check` 和全工作区
  `git diff --check` 退出 0；后者只有混合工作区既有 LF/CRLF 提示。
- 首轮专属测试入口在导入共享 `_path_setup` 前遗漏设置缺失 env 路径，因此该
  子进程可能按 helper 默认规则加载了 `server/.env`；没有打印、序列化、写入
  状态或发起网络/外部服务调用。发现后已在专属测试文件最前固定
  `PROJECT_KEI_ENV_FILE` 为系统临时目录中的不存在文件，并在该隔离下重跑全部
  专属与既有回归。任何具体秘密值均未被检查或输出。

### 交回 PK-000 的公共集成关注

- 当前共享 `server/api.py` 仍内置装配 PK-160 路由和 Provider；要让真实运行时
  的停用/卸载语义生效，PK-000 串行窗口需要移除该内置装配并由
  ModuleManager 唯一装载，PK-160 本轮按冻结规则未修改共享 API。
- 当前共享 catalog/dashboard/README/架构文件按 PK-011 批次冻结；PK-000
  串行窗口需要登记本 release fragment、切换动态面板发现入口并删除重复的内置
  控制台所有权，本轮未修改这些共享文件。
- `ModuleManager.enabled_in_process_descriptors()` 当前按 registry 键顺序返回，
  没有按 manifest dependencies 做拓扑排序。本轮临时 registry 的确定顺序使
  `affection_memory` 先设置 Provider、`conversation` 后消费且测试通过，但依赖
  顺序保证属于 PK-010 公共契约，需由 PK-000 决定是否在串行窗口补强；PK-160
  未反向修改 PK-200 或 `core/modules/**`。

## PK-011 增量完成文档门禁

- [x] TASK_RECORD — 已记录包、接口、Provider 生命周期、数据副作用、验证、真实数据隔离与公共集成关注。
- [x] TASKS_BOARD — 由 PK-000 维护且本轮禁止修改；本任务文件已置“待集成”，未标记“已完成”。
- [x] PUBLIC_README — 批次冻结；实际接口未改变，安装/release 增量交由 PK-000 串行窗口统一登记。
- [x] MODULE_CATALOG — 批次冻结；专属 release fragment/catalog entry 已就绪，正式 catalog 合并交 PK-000。
- [x] ARCHITECTURE_DOCS — 批次冻结；未改变现有 module package 或 Provider 公共契约，依赖排序关注已交 PK-000。
- [x] LOCAL_README — 不适用：未改变本机路径、端口、解释器、秘密位置或启动方式。
- [x] AGENT_RULES — 不适用：未改变长期 agent 工作、安全、验证、文档或 Git 规则。
- [x] VALIDATION — 临时数据专属测试、七项既有回归、compileall、node check、任务文档门禁与 git diff check 均已覆盖；未调用真实外部服务。

## 控制台长期记忆入口恢复与 1.0.2 候选（2026-08-01）

- 动态面板不再把两类能力压成一块：恢复“好感度系统”和“长期记忆”两个独立
  `<details>`。既有关系状态、事件选择、记忆列表/新增/删除 API 与 Provider 契约
  均未改变，危险 reset/clear 仍不在动态面板暴露。
- 候选模块提升为 `affection_memory@1.0.2`。确定性 ZIP 为 73897 bytes，SHA-256
  `e31fb56b9273f2f041eecf6c2a3b8260c65789adafdbffb0b86db56d50611941`，
  manifest SHA-256 为
  `f4891af77e64b3478ed3d96d9a612efa9f4acfe16286e18a8c0ac883aab29e09`。
- 专属安装/生命周期、dashboard 静态契约和 Node 语法检查通过；未读取、迁移、
  打印或覆盖真实 `affection_state.json`、`memories.json` 或 conversation history。

PK-160 仍保持“待集成”，等待 PK-900 累计复核，不提前标记完成。

## 好感度/长期记忆双卡与本机加载修复（2026-08-01）

- 实机复查纠正上一节的不足：两个 `<details>` 仍属于同一张父卡，不能满足独立模块卡展示。本轮改为 `.module-owned-panels` 下的 `module-affection` 与 `module-long-term-memory` 两张独立卡，分别使用 `affection.png` 和 `memory.png`，各自保留公共图片、设置与折叠能力。
- 旧 `affection_memory@1.0.2` 加载失败的实际原因是 Core 读取运行目录 `backend/__init__.py` 时出现 `PermissionError: WinError 5`。通过正式本地更新生命周期安装 `1.0.3` 后，受控前端入口返回 HTTP 200，并确认包含两卡契约；未直接改写 registry 或运行目录。
- `affection_memory@1.0.3` 确定性 ZIP 为 74579 bytes，SHA-256 `13092656fab42c518f9a70e3377dd94f031d033fb618da9aa1a0a57df4198030`，manifest SHA-256 `9ece0b2661aa414bff52f63d39257cd44032da4b54f4776e09bd146a56a2f4af`。
- 当前 registry 已安装并启用 1.0.3，`restart_required=true`。前端双卡已可加载；关系/记忆后端需在用户正常重启 Core 后按新版本装配。未读取、迁移、打印或覆盖真实关系、记忆或对话历史。

PK-160 继续保持“待集成”，等待重启后的 PK-900 累计复核。

## 控制台同源读取守卫修复（2026-08-01）

- 1.0.3 重启后前端入口与双卡均正常装配，但生产 composition 错把 `local_write_guard` 同时用于 GET，导致浏览器同源 GET 未携带 `Origin` 时返回 `relationship and memory access is local-only`。
- 1.0.4 将接口守卫明确分为 `local_read_guard` 与 `local_control_guard`：关系状态和记忆列表 GET 使用前者；事件、选择、新增、删除、reset/clear 等写操作继续使用后者。全局 Loopback 中间件仍先行拒绝非本机客户端，未放宽局域网访问。
- 永久临时数据回归覆盖：同机无 Origin 的两个 GET 均为 200；无 Origin 的 POST 为 403；可信 `http://127.0.0.1:8000` Origin 的 POST 为 200。没有使用真实关系或记忆文件。
- `affection_memory@1.0.4` 确定性 ZIP 为 74871 bytes，SHA-256 `7e74beb9a07509829edf5b6e3504a4e930ae546c0f6ea3c1a79a12486a279d21`，manifest SHA-256 `6e45f315af8a013dc5797c7b77f1ca0a1a1d6b334c941c1ab978243af5deb751`。本机已通过正式 update 生命周期安装并启用，等待一次 Core 重启装配。

PK-160 仍为“待集成”，不得在重启实机复验前提前关闭。
