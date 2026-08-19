# PK-140 — QQ bridge、定时推送与业务私聊菜单

- 状态：待集成
- 优先级：P1
- 所属模块：`qq_bridge`
- 依赖任务：PK-001、PK-010、PK-011、PK-020、PK-100、PK-110、PK-150、PK-170、PK-180、PK-190、PK-200
- 负责路径：`server/qq_bridge/src/**`、`server/qq_bridge/tests/**`、`server/qq_bridge/package_source/**`、`server/qq_bridge/release/**`、`server/qq_bridge/module_adapter.py`、`server/qq_bridge/control_facade.py`、`server/qq_bridge/package_builder.py`、`server/features/qq_control/**`（既有兼容边界）、`server/services/qq_bridge_control.py` 兼容接缝、本任务定向测试和任务文件；共享 `api.py`、ModuleManager composition、Catalog、根控制台和公共 README 由 PK-000 串行装配。明确排除 `server/qq_bridge/.env`、`server/qq_bridge/data/**`、`server/qq_bridge/node_modules/**`、真实 focus 状态与真实日程文件内容
- 当前对话：2026-07-30 PK-011 可安装化增量：交付确定性 QQ sidecar 包、独立依赖部署 marker 校验、固定 adapter、adapter-backed qq-control facade、动态面板和 release 元数据；不修改共享生产 composition，不运行 npm 或真实 sidecar

## 目标

在保持 QQ bridge 为独立 Node sidecar 的前提下，明确 Gateway 私聊转发、主 API 本机 `qq_control`、定时情报、生命维持提醒、发送幂等状态与控制台显式启动之间的契约。版本化与 legacy 控制接口共用同一 service；所有实现和自动验证均不得接触真实凭证、真实日程/发送状态或真实外部服务。

## 不在本任务内

- 不把 bridge 合并进 FastAPI 进程，不新增常驻进程、端口或自动开机启动；本次只按 PK-010/011 冻结契约提供 QQ 专属模块包与受信 sidecar adapter，不另造模块生命周期。
- 不修改 PK-110 Collector/缓存/Kei 改写契约、PK-200 conversation/LLM 契约、QQ 平台后台配置、Bot 权限、正式白名单或任何模型/情报业务规则。
- 不创建、补全、读取、输出、复制、格式化或修改 `server/qq_bridge/.env`；不把 AppID、Secret、Token、allowed user、Gateway URL 或消息内容写入响应、日志、任务文档或测试产物。
- 不运行 `src/index.mjs`、真实 Gateway、Token 获取、真实 QQ API、真实 `/chat`、LLM、情报生成/采集、提醒生成或发送；不得用真实消息证明功能。
- 不读取、迁移、清空、覆盖或修改真实日程配置与发送状态；不以当前真实文件内容作为测试 fixture。
- 不安装、更新或删除 Node 依赖，不运行 `npm install`，不修改 `node_modules`。控制台缺少配置或依赖时只返回有限状态和人工操作提示。

## 接口契约

- 当前控制接口：`GET /dashboard/qq-bridge/status`、`POST /dashboard/qq-bridge/start`。
- 当前日程接口：`GET/PUT /dashboard/briefing/schedule`、`GET/PUT /dashboard/life-support/schedule`；bridge 消费 `/chat/text-only`、当天情报缓存接口与 `POST /life-support/reminder` 等现有公开接缝。
- 目标控制接口：`GET /api/v1/qq-control/status`、`POST /api/v1/qq-control/start`。
- 目标日程接口：`GET/PUT /api/v1/qq-control/schedules/daily-briefing`、`GET/PUT /api/v1/qq-control/schedules/life-support`。legacy dashboard 路径必须委托同一个 qq-control service/repository，不能维护两套验证或文件写入规则。
- status 只能返回 `running/state/message/launcher_exists/env_configured/dependencies_ready` 等有限布尔/枚举信息，不返回路径、进程命令行、PID 之外的进程详情、环境名称/值或文件内容。
- start 是明确用户点击后的本机控制操作，必须同时校验本机 client 与受信控制台 Origin；未配置、依赖缺失或已有 bridge 时不启动。重复、并发点击最多产生一个受控进程，不能依赖前端按钮禁用作为唯一防线。
- 控制台保留现有启动图片、状态、日程表单、元素 ID 和折叠行为；不得静默创建 `.env`、打开编辑器、执行安装命令、修改配置、启用日程或启动第二个 bridge。
- bridge 私聊继续通过既有公开 conversation API；定时情报只消费 PK-110 当天缓存/受控生成接口，正常发送阶段不得自行实现 Collector 或绕过缓存反复采集。任何需要改变 PK-110 或 conversation 契约的需求先停止并交回 PK-000。

## 数据所有权

- 受保护秘密：`server/qq_bridge/.env`。本任务不读取其内容，也不确认/输出其中的变量；产品 status 最多检查文件是否存在。`.env.example` 仅可维护字段名和非秘密占位说明，不得写真实值。
- 主 API 日程配置：`server/data/daily_briefing_schedule.json`、`server/data/life_support_schedule.json`。
- bridge 发送状态：`server/qq_bridge/data/daily_briefing_schedule_state.json`、`server/qq_bridge/data/life_support_schedule_state.json`。
- 2026-07-22 入场仅根据源码常量，对上述四个日程/状态路径执行 `Test-Path` 与定向 Git 状态检查：四者均存在且属于忽略范围；未读取内容、大小、时间戳或摘要。`.env` 未执行存在性或 Git 状态探测。
- 日程配置属于用户设置，发送状态包含按日期/时隙和接收者的投递事实；不得进入 Git、浏览器存储、公开 API 的非必要字段或其他模块状态。两类状态不得与 PK-110 情报缓存、conversation history 或来源配置合并。
- 测试必须向 schedule repository、scheduler `statePath`、launcher/env/dependency path 显式注入 `TemporaryDirectory`，并使用 fake process checker/Popen、fake clock/timers、fake fetch、fake conversation/briefing/reminder 和 fake sender。
- 日程和发送状态写入必须原子化；失败时保留旧字节。损坏状态应安全降级且不得导致发送或用空状态覆盖；投递成功后才能记录已发送，部分失败只重试未成功接收者。

## Sidecar 与调度语义

- Node sidecar 独占 QQ Token/Gateway/C2C 协议与消息发送适配；主 API 不读取 QQ 凭证、不持有 Gateway session，也不直接向 QQ 平台发送。
- 只处理明确白名单私聊；未知发送者不进入 conversation/情报/发送链路，日志不得输出完整 user openid 或消息正文。
- 每日情报预构建与发送时间必须合法且预构建早于发送；关闭日程时不设置发送 timer。当天缓存存在时复用，缺失时按既有有限策略提示，不在发送阶段反复联网补采。
- 每日情报按日期和接收者幂等；生命维持按时隙和接收者幂等。成功接收者不重发，失败接收者可在受控重试中继续；状态保存失败不得假装已发送。
- 生命维持关闭、时间窗非法、间隔非法或白名单为空时零生成、零发送；LLM/reminder 不可用时只使用既有本地安全文本降级，不改变 PK-200。
- scheduler start/stop、刷新和重连必须可取消且不累计 timer/listener；重复初始化不能造成重复推送。

## 实施清单

- [x] 检查实际 Node bridge、Python control、日程 API、控制台、catalog 和测试，不读取受保护内容、不运行 sidecar。
- [x] 建立 `server/features/qq_control/` 的 models/repository/service/router 清晰边界，让版本化与 legacy 控制/日程接口共用规则。
- [x] 加固显式启动、并发重复启动、本机/Origin、有限状态和缺失配置/依赖的零副作用行为。
- [x] 用可注入状态、时钟、timer、fetch、sender 验证私聊白名单、缓存优先、日程校验、部分失败、发送幂等、重启恢复和 stop 清理。
- [x] 保持控制台组件兼容并切到版本化 qq-control 接口；不新增自动配置、安装、发送或重复启动能力。
- [x] 更新 catalog、README、架构说明和本任务实际工作记录，执行 Node/Python/控制台、文档门禁与 `git diff --check`。

## 验收标准

- bridge 仍是独立 Node sidecar；主 API 与控制台不读取凭证、不建立 Gateway、不直接发送 QQ。
- 新旧 qq-control/status/start 与两类日程 API 共用 service/repository；非法或损坏输入明确失败，原子保存失败保留旧配置。
- 缺少 `.env`、launcher 或依赖时零创建、零安装、零编辑器、零进程；已运行及并发 start 最多启动一次，恶意 Origin/远端 client 零副作用。
- 白名单外消息不调用 conversation、briefing 或 sender；白名单内文字/情报调用只经公开接口，错误体和日志不泄露 Token、完整 user ID、消息正文或上游错误体。
- 每日情报缓存优先、按日/用户幂等；生命维持按时隙/用户幂等。部分失败、状态保存失败、进程重启和重复 scheduler start 不产生已成功用户的重复发送。
- 关闭/非法日程、空白名单、缺失缓存、fake LLM/提醒失败均有确定性降级和零意外发送证据。
- 控制台保留现有组件且只执行显式状态查询、配置保存和单次启动；不保存秘密、日程或发送状态到 browser storage。
- 所有自动测试只使用 fake/Mock、虚构标记和临时文件；没有真实网络、Gateway、Token、LLM、Collector、QQ 消息、提醒或生产进程副作用。

## 工作记录

- 2026-07-22：独立 PK-140 功能对话确认任务总板与本文件均已为“进行中”。完整阅读根/本机 README、AGENTS、TASKS、PK-140/110/200、模块化/可安装/每日情报架构、控制台和 bridge 手册；检查实际 Git 分支与混合工作区。仅对 `.env`、两份真实 schedule 与两份真实 sidecar state 做存在性和定向 Git 状态检查：五者存在、状态为空；未读取内容/大小/时间戳/摘要或详细 diff。未启动 BAT/Node、未安装依赖、未连接 QQ、未请求 token、未调用真实 LLM/情报/发送。
- 2026-07-22：建立 `server/features/qq_control/`：models 严格拒绝额外字段；repository 独占两份 schedule 的缺失默认、损坏失败、同目录唯一临时文件、`flush/fsync/os.replace` 和失败保留旧字节；service 独占固定 launcher/env/Node/dependency readiness、有限 status、单锁并发 start 和两类日程校验；router 同时注册四组版本化接口与全部 legacy 路径。`server/services/qq_bridge_control.py` 只保留固定生产 composition/兼容 facade，`api.py` 移除旧日程/启动规则并只装配同一 service/router。
- 2026-07-22：控制写保护固定为实际 socket loopback client 加受信 `127.0.0.1|localhost|[::1]:8000` Origin；不信任 Host、Forwarded 或自定义 header。qq-control middleware 在全局 CORS 前拒绝恶意实际写/OPTIONS，并把 Pydantic 422 统一为不回显输入的 `invalid_request`；router 再次校验。无 Origin 的 loopback Node sidecar只可读日程。status/readiness 零写入、零网络、零 bridge 启动；响应不含路径、命令行、环境或凭证。并发 start 只使用固定 BAT/cwd，最多一次 fake/实际 Popen，不接受用户命令/BAT/cwd/env，也未新增 stop/kill。
- 2026-07-22：`start_qq_bridge.bat` 删除自动复制 `.env.example`、打开 Notepad 和 `npm.cmd install`；缺 Node、`.env` 或 `node_modules/ws` 时失败并提示人工步骤。控制台保留最前面的 `qq-launch.png` 图片按钮、DOM ID、折叠和状态展示；status/start/两类 schedule 读写改用 `/api/v1/qq-control`，legacy 后端继续兼容；浏览器仍不保存 QQ 状态、白名单、日程或凭证。
- 2026-07-22：Node sidecar 拆出 `bridge_core/gateway_client/state_store`。C2C 固定为事件/ID/发送者/长度 → allowlist → 上限 1000 的 message-ID 去重 → `POST /api/v1/conversation` → 同一用户回复；空白名单、未授权和重复事件零 Kei/QQ。按钮也先鉴权再 ack；只处理 C2C 文本/批准按钮。输入 4000、回复/Markdown 分片与总长、每类条目/warning/URL 有界；URL 拒绝 userinfo 并删除敏感 query。QQ 401 只强刷/重试一次，上游正文不进入异常、日志或用户响应，日志不记录消息/OpenID/AppID/Token。
- 2026-07-22：Gateway 只有单 socket/heartbeat/reconnect timer，指数退避最多 60 秒；重复 connect 不累积，shutdown 进入终态并取消 timers。普通 bridge 主路径不再使用 `/chat/text-only` 或带 fetch query 的 legacy 情报入口；预生成显式 `POST /api/v1/briefing/generate`，私聊/发送只读 `GET /api/v1/briefing/today`，缓存缺失零采集。生命维持继续使用现有 `/life-support/reminder` 受控生成接缝且不写 history，失败使用按槽位确定的本地文本。
- 2026-07-22：两类 scheduler 以注入 clock/timer/fetch/sender 运行。关闭、改期和重复 start 清理旧 timer；每日预生成按本机日期只进入一次，投递按日期/用户隔离；生命维持只在启用、合法时间窗、正间隔、非空 allowlist 时调度并按槽位/用户隔离。对外发送前先原子记录 `sending` reservation，成功后 `success`，明确失败 `failed/error_code`；因此成功用户不因其他用户重收，崩溃后的 `sending` at-most-once 失败关闭，代价是可能需要人工确认一次不确定投递。
- 2026-07-22：Node 状态 Schema 只含日期/槽位、`sha256(OpenID)` 截断去重键、有限状态/错误码；每日最多 14 天，生命维持最多 96 槽，不保存完整 OpenID、消息、情报、模型回复、token 或内部路径。状态写使用唯一临时文件、`fsync`、原子 rename；损坏/旧版/未知 Schema 关闭调度且不自动覆盖。自动测试全部指向系统临时目录；现存真实状态未读取或迁移。
- 2026-07-22：新增 `server/tests/test_qq_control.py` 6 项和 Node 12 项，覆盖 status 零副作用、缺前置条件、并发 start、原子失败/损坏状态、loopback/Origin、新旧路由共用、allowlist 顺序、空/未授权/重复零调用、401 单次重试、秘密清洗、输入限长、显式预生成/缓存只读、逐用户失败隔离/跨重启去重、生命维持 fallback/槽位、改期/关闭/stop、原子 state 与 Gateway timer 单例。首次 Python 路由测试主动发现默认 Pydantic 422 会回显虚构 `FAKE_SECRET_TOKEN`，随后加入固定错误响应并重跑通过。
- 数据/网络/生命周期：主 API 只在明确 schedule PUT 时原子写两份 schedule，status/GET 不写；start 仅明确浏览器操作时打开固定 BAT。Node 仅在实际启动后访问 QQ token/Gateway/send 和 loopback Project Kei API；本轮验证未执行这些真实副作用。部署 Python/control/dashboard/catalog 需重启 API，部署 `qq_bridge/src`/BAT 后需人工重启 sidecar；没有新增端口、进程类型、安装包、远程 stop 或自动启动。
- 遗留风险：QQ 外发与本地状态文件之间没有平台事务，当前以发送前 reservation 保证跨崩溃 at-most-once；崩溃窗口可能造成“状态为 sending、实际是否送达未知”，不会自动重发，需要人工确认。旧/损坏 sidecar state 按要求不自动迁移/覆盖，会关闭对应调度，操作者需在 sidecar 停止后先备份再明确处理。真实 QQ/Gateway/Token/发送端到端未测试且不得在本任务自动验证。
- 最终验证：`test_qq_control.py` 7 项、Node `node --test tests/*.test.mjs` 14 项、`test_daily_briefing_module.py`、`test_daily_briefing_summary_cache.py`、`test_conversation_consumers.py`、`test_feature_catalog.py`、`test_dashboard_shell.py` 均退出 0；dashboard 回归包含内联 JavaScript 语法检查。`src/` 与 `tests/` 全部 `.mjs` 逐文件 `node --check` 通过；`features/qq_control`、兼容 service、`api.py` 与定向测试 `compileall` 通过。`test_conversation_consumers.py` 仅记录既有 focus runtime 只读 `PermissionError` 并按既有隔离逻辑跳过，测试结论仍通过。文档门禁和 `git diff --check` 通过（仅既有 LF/CRLF 提示）；受保护五路径最终定向 Git 状态为空。
- 2026-07-22：PK-000 确认 PK-001、PK-110 已完成，PK-140 依赖满足并从“待开始”登记为“进行中”。本轮没有登记或启动新的 PK-900 批次。
- 现状审计确认 `server/qq_bridge/src/index.mjs` 装配 daily briefing 与 life-support scheduler，`server/services/qq_bridge_control.py` 提供本机 readiness/start，`server/api.py` 仍持有 legacy qq/status/start 与两类日程接口，控制台已有显式图片启动和日程表单。独立任务仅在上述批准 hunk 内收口，不整理其他模块。
- 入场审计时，手工 `start_qq_bridge.bat` 在直接运行且缺少前置条件时含创建 `.env` 模板、打开编辑器和执行 `npm.cmd install` 的交互分支；当时的 Python 控制服务会在缺少 `.env` 或依赖时拒绝启动。该入场风险已在本轮移除并用静态 BAT/缺前置条件测试固定；任何后续改动仍不得读取真实 `.env` 或自动安装依赖。
- 当前工作区为既有混合状态，含多项已完成任务、个人状态与未跟踪模块。PK-140 必须逐路径保留；禁止执行真实启动、安装、发送、日程写入、Git 发布或工作区清理。

## PK-900 独立验收退回（2026-07-22）

- 结论：不通过，PK-140 退回“进行中”。现有 7 项 Python、14 项 Node 和五组相关回归全部通过，但 PK-900 新增的两类临时逆向夹具发现数据完整性覆盖缺口；不得以既有自测通过替代整改。
- 阻断一：两份 Python schedule 的更新路径直接调用 repository save，没有在同一锁域内先读取并验证已有文件。临时 daily schedule 写入损坏 JSON 后，直接 service update、versioned PUT 与 legacy PUT 均未失败关闭；实际结果为 `direct_corrupt_write_blocked=False`，两组 HTTP 均 `status=200 old_bytes_preserved=False`。同类风险适用于 life-support schedule。最小整改应让所有 schedule 保存路径在 mutation 前验证已有状态，并避免 read/validate/save 之间的并发窗口；损坏/错误结构必须返回固定脱敏错误、保留旧字节且不留临时文件。
- 阻断二：Node scheduler 对 runtime state 只验证 `schema_version` 与顶层容器类型。带完整 OpenID 形态键、秘密/消息字段或非法 delivery 记录的 `schema_version=1` 状态仍被视为健康；daily 与 life-support 两条临时夹具都进入 fake 发送并改写文件，实际结果为 `daily_semantic_corruption_blocked=false sends=1`、`life_semantic_corruption_blocked=false sends=1`。最小整改应为 daily prebuild/deliveries 和 life slots 建立严格语义校验：只接受规定日期/槽位、24 位小写十六进制用户哈希、有限状态/错误码和规定字段；未知字段、完整 OpenID、Token/Secret/Authorization/消息正文或超界结构必须令 scheduler 失败关闭、零 timer/生成/发送/写入并保留原字节。
- 必补正式回归：corrupt/错误结构 schedule → service + versioned/legacy PUT；四类以上 Node delivery state 语义篡改 → daily/life scheduler start/send/deliver。每项断言固定脱敏错误或 `stateHealthy=false`、零进程/网络/timer/生成/发送、旧字节完全不变且无临时文件。只允许修改 `features/qq_control/**`、`qq_bridge/src/state_store.mjs`/两类 scheduler 的必要校验接缝及定向测试，不改变 API、日程、缓存、发送 reservation、控制台、PK-110 或 PK-200 契约。
- 已通过项：白名单先于去重/转发，重复消息零额外调用，401 仅重试一次，错误/Markdown/URL 脱敏；8 路并发 start 仅一次 fake Popen，缺 launcher/env/Node/依赖零创建；新旧 API 共用 service，同源/远端/恶意预检与 422 脱敏；预生成与缓存发送分离，每用户每日与生命维持槽位跨重启幂等，改期/关闭/stop 和异步 shutdown 清除 timer 且零后续发送；原子替换失败保留旧字节；控制台、catalog 与文档一致。
- 数据隔离：PK-900 未探测 bridge `.env`；只对四个冻结 schedule/runtime state 路径执行 `Test-Path`，未读取内容、大小、时间戳或摘要。全部写入、损坏、HTTP、WebSocket、进程、时钟、timer、fetch、sender 夹具使用系统临时目录和 fake；未启动 BAT/sidecar、安装依赖、连接 QQ、发送消息或调用真实 Collector/LLM。用户禁止 Git，本轮没有执行任何 Git 命令。

## PK-900 退回整改（2026-07-23）

- 只处理两项阻断。Python repository 新增两类 `replace_*` mutation：在同一 schedule 路径锁内先读取现有文件、调用 service 的完整语义校验，再创建唯一临时文件并 `flush/fsync/os.replace`；旧的无校验公开 save 入口已移除。损坏 JSON、错误根结构、未知字段、非法布尔/时间/间隔/更新时间都在临时文件创建前失败。直接 service 抛出有限 `ScheduleStateError`；版本化与 legacy PUT 统一返回固定 `409 {"detail":"schedule_state_invalid"}`，不回显文件内容、路径、凭证形态字段或异常正文。
- Node 增加严格 state Schema：顶层、daily prebuild/deliveries、life slots 和每个投递记录都使用字段白名单；日期/槽位必须是真实值，接收者键只能是 24 位小写十六进制哈希，状态只能是 `sending/success/failed`，`failed` 必须带有限小写错误码且其他状态禁止错误码，并继续固定 14 天/96 槽上限。完整 OpenID 形态键、Authorization/Token/Secret、消息字段、未知字段、非法日期/槽位/状态/错误码或超界容器都会令 `stateHealthy=false`。
- 两类 scheduler 在 state 不健康时于任何日程读取前返回；不会创建 refresh/业务 timer，也不会进入 prebuild、缓存读取、提醒生成、发送或状态写入。异常原字节与目录内容保持不变，只输出固定 `daily_state_corrupt` / `life_support_state_corrupt`，不自动迁移、清空或修复。
- 接口、合法日程 payload、控制台、PK-110 显式预生成/只读缓存、PK-200 conversation/受控生成、QQ reservation 和 at-most-once 策略均未改变。正常网络副作用仍只可能发生在 sidecar 实际运行后的既有 QQ/Project Kei 调用；本次全部验证使用临时目录、fake 进程/HTTP/时钟/timer/sender，没有启动 BAT/sidecar、请求 Gateway/Token、发送 QQ、调用真实 Collector/LLM/TTS 或安装依赖。
- 新增正式回归覆盖：daily/life 损坏或错误结构经 direct service、版本化 PUT、legacy PUT 均失败且旧字节/临时目录保持；daily 7 类与 life 6 类语义篡改覆盖完整 OpenID 形态键、Authorization、消息/秘密字段、非法日期/槽位、状态/错误码及 14/96 上限，逐项断言 `stateHealthy=false`、零 schedule network、零 timer/生成/缓存/发送/写入、旧字节不变和固定安全 warning。
- 实际验证：`test_qq_control.py` 8 项、Node `node --test tests/*.test.mjs` 29 项，以及 `test_daily_briefing_module.py`、`test_daily_briefing_summary_cache.py`、`test_conversation_consumers.py`、`test_feature_catalog.py`、`test_dashboard_shell.py` 全部退出 0；相关 Python `compileall` 和全部 bridge `src/tests` JavaScript `node --check` 通过。`test_conversation_consumers.py` 仍只记录既有 focus runtime 的只读 `PermissionError` 并按既有隔离逻辑跳过。状态恢复“待集成”后，文档门禁通过 22 项，`git diff --check` 退出 0（仅混合工作区既有 LF/CRLF 提示）。
- 受保护数据：本轮只检查 bridge `.env` 与四个真实 schedule/runtime 文件的存在性、路径和定向 Git 状态，未读取内容、大小、时间戳、摘要或详细 diff，未修改、格式化、迁移或用作测试夹具。工作区仍为多任务混合状态；未暂存、提交、推送、建 PR 或清理，PK-900 保持“进行中”等待独立复验。

## 历史完成文档门禁（2026-07-23 基线）

任务进入“待集成”前必须全部勾选；不适用项也必须写明原因。

- [x] TASK_RECORD — 已记录实际 sidecar/control/scheduler 行为、版本化/legacy 接口、数据/网络副作用、验证、重启要求和 at-most-once 遗留风险。
- [x] TASKS_BOARD — 两项退回阻断完成限定整改并通过 PK-900、PK-000 双重复核后，`TASKS.md` 已把 PK-140 登记为“已完成”；名称、P1 和 PK-001/PK-110 依赖不变，本批 PK-900 同步关闭。
- [x] PUBLIC_README — `README.md` 已补充损坏现有日程禁止 PUT 覆盖、严格 sidecar state Schema 和失败关闭零副作用，并保留既有控制/日程接口、启动/重启和限制。
- [x] MODULE_CATALOG — QQ 条目已登记完整 endpoint、`sidecar:qq-bridge` 进程边界、数据所有权、网络副作用、失败模式和 `modular` 状态。
- [x] ARCHITECTURE_DOCS — `docs/architecture/qq-bridge.md` 与 bridge README 已补充同锁域 schedule mutation、固定 409 和 Node 深层 state 语义/失败关闭；模块化、PK-110/PK-200 边界不变。
- [x] LOCAL_README — 不适用：本机路径、启动器位置、解释器、端口和环境位置均未变化；忽略的 `README.local.md` 未修改。
- [x] AGENT_RULES — 不适用：本轮遵守既有工作流、安全、验证、文档和 Git 规则，没有改变长期 agent 政策；`AGENTS.md` 未修改。
- [x] VALIDATION — 退回整改后 8 项 Python qq-control、29 项 Node、五组指定回归、全部 bridge `src/tests` MJS 语法、相关 Python compileall 和 dashboard JavaScript 均通过；最终文档门禁通过 22 项，`git diff --check` 退出 0（仅既有 LF/CRLF 提示）。全部为 fake/临时路径，未执行真实外部副作用。

## 独立对话启动提示

```text
继续 Project Kei 的 PK-140 QQ bridge 与定时推送任务。先完整阅读根 README.md、
AGENTS.md、README.local.md（如存在）、TASKS.md 和 tasks/PK-140-qq-bridge.md，
再检查 git status 与 Node sidecar、qq_control、日程 API、控制台和 catalog 接缝。
不得读取/输出/修改 server/qq_bridge/.env 或真实日程/发送状态，不运行 Node
sidecar、Gateway、Token、真实 QQ、LLM、情报生成或提醒。全部测试使用临时路径、
fake process/timer/fetch/sender。只处理本任务批准边界；跨模块契约变化先交回 PK-000。
```

## PK-000 最终独立复核（2026-07-23）

- 结论：通过。PK-900 初验发现的损坏 schedule 覆盖与 Node delivery state 浅校验两项阻断均已关闭；总控审查实际 repository/service/router、sidecar handler、gateway、state store 和两类 scheduler 后，未发现新的集成阻断。
- 总控专项回归：`tests/test_qq_control.py` 8 项通过；Node `bridge_core`、scheduler 与 state/gateway 共 29 项通过；daily briefing module/summary cache、conversation consumers、catalog、dashboard shell 五组回归均退出 0；相关 Python 编译和全部 bridge `src/tests` MJS 语法检查通过。
- 独立故障注入：32 路并发 start 仅执行一次 fake Popen；无 Origin、恶意 Origin 与远端伪造 Origin 写入均被拒；固定 422/上游错误不回显虚构秘密；缓存 Promise 未完成时 shutdown 后零发送；跨重启只发送一次且发送路径零 briefing generation；模拟原子 rename 失败保留旧字节并清理临时文件。
- 隔离审计：全部写入、HTTP、进程、timer、cache 和 sender 场景使用临时路径/fake；未读取或修改真实 QQ 配置、日程或 runtime 内容，未启动 sidecar/BAT/Gateway、未发送 QQ、未联网或调用真实 LLM/Collector。两份真实 schedule 与 sidecar runtime 仍在 Git 忽略范围，bridge 私密配置的忽略规则存在；公开相关路径扫描仅命中空占位和测试假秘密。
- 差异边界：工作区仍为进入本批前既有混合状态，包含其他任务和个人状态修改；总控未整理或覆盖这些变更。`git diff --check` 退出 0，仅有既有 LF/CRLF 提示。原有 `sending` 预约导致的 at-most-once 崩溃窗口继续作为已记录限制，不影响本批验收结论。
## 发布前回归补充（2026-07-23）

- GitHub 发布前的全量离线回归发现 `server/services/qq_bridge_control.py` 的 legacy facade 在迁入 `QQControlService` 后未继续接受既有的 `launcher`、`env_path`、`dependency_path`、`process_checker` 与 `popen_factory` 注入参数，导致旧 `test_intel_source_config.py` 兼容夹具失败。
- facade 已恢复上述只用于兼容和隔离测试的关键字接缝；生产无参数调用仍复用唯一的版本化 `qq_control_service`，不会建立第二套日程、进程或业务规则。注入式启动继续保持旧命令形状、PID 返回和重复启动保护，且只使用临时 BAT、占位 `.env`、临时依赖目录及 fake Popen。
- `test_intel_source_config.py` 与 `test_qq_control.py` 已重新通过；随后完成其余 25 组离线 Python 回归、29 项 Node bridge 测试、控制台 JavaScript 语法检查、任务文档门禁和 `git diff --check`。未启动 BAT、QQ Gateway、真实 Project Kei 服务、采集、LLM、TTS 或任何个人状态命令。

## 业务私聊菜单增量边界（2026-07-24）

### 总控登记结论

- PK-150、PK-170、PK-180、PK-190 均已完成，PK-140 本轮新增对四者的形式依赖，依赖已满足。PK-140 由“已完成”重新打开为“进行中”，交独立功能对话实施；此前 QQ bridge、qq-control、定时情报、生命维持、白名单、秘密清洗、原子状态和 at-most-once 行为全部作为累计回归基线。
- 本轮只扩展白名单 QQ 私聊中的主菜单、四个业务子菜单、有限只读摘要和经二次确认的有限写操作。不得借机修改四个业务模块的 router、service、repository、数据 Schema 或业务规则；如果现有版本化 API 无法支持冻结交互，必须把精确接口缺口记录到本任务并停止扩张，交 PK-000 决策。
- 本轮不修改正在进行的 PK-900 批次。独立实现完成后只把 PK-140 交回“待集成”，由 PK-900 另行独立验收。

### 进程、网络与所有权冻结

- QQ bridge 继续是现有独立 Node sidecar；主 API 仍监听 `8000`，bridge 不新增监听端口、进程类型、环境变量、凭证、QQ 权限、Gateway 能力、后台循环、定时任务或自动启动行为。
- bridge 只能经固定 Project Kei base URL 调用下表列出的现有 `/api/v1/*` HTTP API。禁止导入 Python 模块、访问 `server/features/*/repository.py`、打开个人状态 JSON、调用 legacy 路径、构造任意路径代理或在 Node 中复制打卡、积分、奖励、计时、日期、重复事件和修炼累计规则。
- 四个模块继续独占各自个人状态。bridge 只可把当前白名单用户明确请求得到的有限字段格式化后回复给同一用户；不得把完整 API JSON、备注、日历正文、历史记录、状态文件路径或用户输入写入日志、scheduler state、浏览器存储或新的持久化文件。
- 菜单不建立长期多轮输入或磁盘确认状态。主菜单只进入子菜单；写操作只能由子菜单中的独立明确按钮或两条严格单消息命令触发。斩妖动态 goal_id 只在一次 `status` 响应后保存为有界、短时、用户绑定的进程内校验缓存，不写 scheduler state 或新文件，不包含目标正文以外的 API 快照，也不新增 timer。
- 现有 allowlist 必须先于菜单构造、状态查询、确认登记和业务 API 调用。消息/interaction 去重、输出限长、URL/秘密清洗、固定错误码、401 单次重试及 shutdown 行为继续适用。

### 冻结的版本化 API 矩阵

| 子菜单 | 允许的只读动作 | 允许的明确写动作 | 明确不开放 |
|---|---|---|---|
| PK-150 斩妖除魔 | `GET /api/v1/demon-slayer/status`；只展示有限今日目标、完成状态和积分。`GET /api/v1/demon-slayer/reviews/daily` 只在用户单独点击“生成今日复盘”后调用 | `POST /api/v1/demon-slayer/checkins`；只接受刚由 status 返回并通过格式/长度/用户缓存校验的 goal_id，完成与未完成使用不同固定 action | 目标/奖励创建、编辑或删除、奖励兑换、非 daily 复盘、legacy plan/wish/redeem、`/demon/reset` |
| PK-170 健身打卡 | `GET /api/v1/fitness/status` | 独立“确认今日健身打卡”按钮调用一次 `POST /api/v1/fitness/checkins`，body 只有空备注 | `/fitness/*` 全部 legacy 路径，尤其 `/fitness/reset` |
| PK-180 专注计时 | `GET /api/v1/focus/status` | 独立按钮调用 `POST /api/v1/focus/start` 或 `/stop`；start 固定 `pomodoro`、25 分钟、空 task、`force=false`、`with_audio=false` | `/focus/*` legacy、`/api/v1/focus/reset`、`force=true`、模块安装/启停/卸载和生命周期控制 |
| PK-190 日历与修炼 | `GET /api/v1/calendar/today`、`GET /api/v1/calendar/status` | 严格单消息命令 `添加备忘 YYYY-MM-DD 标题` 调用 `POST /api/v1/calendar/events`；`记录修炼 技能 小时数` 调用 `POST /api/v1/calendar/practice` | `/calendar/*` legacy、`/api/v1/calendar/reset`、编辑、删除、导入、同步、提醒、LLM 猜测和长期输入状态 |

- 主菜单中的四个模块按钮只能打开相应子菜单，或至多执行一次上表允许的状态查询；主菜单点击本身不得发送任何 POST/PATCH/PUT/DELETE。
- “二次明确”指主菜单第一次点击只打开子菜单；随后独立写按钮或严格命令才可调用固定 POST。状态查看与子菜单展示始终零写。重复 interaction 由既有 message-ID 去重阻断；写请求失败或响应不确定时不自动重试，用户若要再次执行必须重新发起。
- 子菜单只允许固定 action ID 到固定 method/path/body builder 的白名单映射；用户文本、目标 ID、奖励 ID或日期只能作为经过长度/格式约束的参数，不能进入 URL host、任意 path、HTTP method 或 header。
- 不接受用户输入 focus task/minutes 或打卡备注。calendar 两条命令按固定、确定性语法解析并限制合法日期、标题/技能长度与正小时数范围；不得交给 conversation/LLM 猜测动作或请求体。解析失败只返回格式提示、不调用业务 API。
- focus 未安装、停用或 API 返回 404，以及任一模块返回损坏状态/保存失败时，只向用户给出有限“功能不可用/保存失败”提示；不得读取文件、切换模块生命周期、改走 legacy 路径或回显上游错误体。

### 允许修改路径

- `server/qq_bridge/src/bridge_core.mjs` 与职责单一的 `server/qq_bridge/src/business_menu.mjs`：只实现固定菜单路由、有限格式化、短时 goal_id 校验缓存和版本化 API client 接缝。
- `server/qq_bridge/src/index.mjs`：仅在需要时注入既有 Project Kei base URL、clock 或确认状态依赖；不得改变 Token、Gateway、scheduler、sender 或进程生命周期 composition。
- `server/qq_bridge/tests/**`：新增菜单、确认、API 调用、失败隔离和安全回归；所有 QQ、HTTP、时钟和用户均为 fake。
- `tasks/PK-140-qq-bridge.md`：记录实际接口、数据/网络副作用、测试和遗留问题。实现完成后按门禁最小同步 `README.md`、`docs/architecture/qq-bridge.md`、QQ catalog 条目和 `TASKS.md`；`AGENTS.md`、`README.local.md`、四个业务模块及其他共享文件默认不修改。

### 禁止事项

- 不读取、输出、修改或探测 `server/qq_bridge/.env` 内容，不运行 sidecar/BAT、Gateway、Token、真实 QQ 发送、真实 Project Kei API、LLM、Collector、TTS 或 scheduler。
- 不读取、打印、diff、迁移、reset、覆盖、暂存或提交斩妖、健身、focus、calendar 的真实个人状态，也不得以真实状态完成菜单测试。
- 不暴露任何 reset、`force=true`、目标删除、批量删除、数据清理、模块卸载、任意 API 转发或配置修改入口；禁止通过自由文本绕过固定菜单与二次确认。
- 不扩展到 QQ 群聊、频道、好友等消息域，不申请新的 Markdown 模板或平台权限；只复用现有 C2C 文本、Markdown 与 keyboard 能力。不修改白名单来源、Token 流程、定时投递、conversation/briefing 语义或四个业务模块的公共契约。
- 不安装依赖、不修改 `node_modules`、不整理混合工作区、不执行 Git 暂存、提交、推送或清理。

### 累计验收标准

- 既有普通对话、每日情报按钮、白名单前置、消息去重、QQ 401 一次重试、scheduler、qq-control、秘密清洗和跨重启 at-most-once 回归全部继续通过。
- 主菜单完整展示每日情报与四个业务子菜单；每个只读按钮只调用上表对应 GET，响应只显示允许的有界摘要，模块之间的失败互不影响。
- 主菜单/子菜单展示、非法/过期 goal_id、格式错误命令、重复 interaction、白名单外用户和未知 action 都是零写调用；每个独立明确写按钮或合法严格命令恰好调用一次固定版本化 POST。
- 自动测试明确断言从未请求任何 legacy、reset、DELETE、PATCH、`force=true`、模块生命周期、非固定 host/path 或未列入矩阵的 endpoint。
- 断网、404、422、409、500、超时、无效 JSON、超长/含秘密响应都固定降级，不回显上游正文、个人内容、内部路径、凭证、OpenID 或堆栈，也不自动重试写操作。
- 全部验证使用 fake `qqRequest`、fake `fetch`、fake clock 和虚构用户/业务数据；不访问网络、真实 QQ、真实 API、真实状态、LLM、TTS、Collector、scheduler 或付费服务。
- Node 定向测试、全部既有 bridge 测试、相关 Python 模块/API 回归、逐文件 `node --check`、文档门禁和 `git diff --check` 通过后，PK-140 才可进入“待集成”。

### PK-000 登记记录

- 2026-07-24：只读审计确认四项新增依赖均为“已完成”；实际版本化 API 已具备斩妖 status/goals/checkins/redeem、健身 status/checkins、focus status/start/stop 和 calendar today/status/events/practice。危险 reset、focus force、目标删除及 legacy 接口仍然存在于各模块兼容面，因此在 QQ 菜单契约中显式排除。
- 2026-07-24：审计确认现有 `bridge_core.mjs` 只有每日情报主菜单按钮，业务菜单尚未实现；bridge 已有 allowlist、interaction 去重、固定 Project Kei API client、输出限长和秘密清洗基础。本轮只登记并冻结增量边界，未修改业务代码、未调用任何 API 或真实外部服务。
- 2026-07-24：工作区为既有混合状态，包含 PK-120、个人状态与未跟踪 `vendor/` 等非 PK-140 差异。本轮只修改 `TASKS.md` 和本任务文件，不整理、覆盖、暂存或发布其他路径。

### 独立实现记录（2026-07-24）

- 入场完整阅读根 README、AGENTS、忽略的本机 README、TASKS、本任务、PK-150/170/180/190、模块化架构与 bridge README，并补读 QQ bridge 专项架构；检查实际分支、混合 Git 状态、bridge 与四个版本化 router/model。真实 bridge `.env` 未读取或探测；真实日程、sidecar runtime 与四个业务个人状态只遵守既有路径/Git 边界，没有读取内容、详细 diff、格式化、迁移、覆盖或作为 fixture。没有启动 BAT/sidecar/Gateway/主 API、请求 Token、发送 QQ、调用真实 LLM/TTS/Collector 或安装依赖。
- 新增 `src/business_menu.mjs`，以集中 action 表和固定 operation 表实现五项主菜单、四个业务子菜单、有限格式化与严格命令。operation 同时冻结 method/path；未知按钮、任意 URL/path/method、legacy、reset、reward/redeem、目标管理、DELETE/PATCH 与 `force=true` 均不在可达表中。`bridge_core.mjs` 保持 allowlist → 去重 → interaction ACK → API → sender 的顺序，并在普通 conversation 之前路由菜单、功能名与两条日历命令。
- 实际业务 API：斩妖 `GET status`、显式 `GET reviews/daily`、`POST checkins`；健身 `GET status`、明确按钮 `POST checkins`；专注 `GET status`、明确 `POST start|stop`，start 固定 `pomodoro/25/空 task/force=false/with_audio=false`；日历 `GET today|status`、严格 `添加备忘 YYYY-MM-DD 标题` → `POST events`、严格 `记录修炼 技能 小时数` → `POST practice`。每日情报继续只读 `GET /api/v1/briefing/today`，未知普通聊天继续 `POST /api/v1/conversation`。
- 斩妖 status 只展示前 4 个目标，其他业务列表最多 5 项；keyboard 最多 5 行、每行 5 按钮。动态 goal_id 限 64 位安全字符，必须来自最近一次同用户 status 的可见目标；进程内缓存最多 200 用户、10 分钟惰性过期，重启即丢失，不写文件或 timer。目标、备忘、技能、Markdown 与错误均清洗/转义/限长/分段；超时、focus 404、通用 404、422、500、无效 JSON/根类型和发送失败只返回有限固定提示，上游正文、异常、路径、OpenID、凭证或个人状态不进入普通日志/错误回复。
- 生命周期/数据/网络：仍只有现有 Node QQ sidecar，无新端口、进程、后台循环、环境变量、QQ 权限或自动启动。bridge 不访问四个 Python repository、个人 JSON 或缓存；业务持久化仍完全由主 API 各模块在明确 POST 时拥有。运行时网络只增加白名单用户明确交互产生的固定 loopback 版本化 HTTP；主/子菜单展示零 HTTP，状态查询只有 GET，写失败不自动重试。部署菜单需人工重启 sidecar；Catalog 展示更新需随主 API 正常重启，不改变业务 router。
- 新增 16 项业务菜单 Node 用例，连同既有 core/Gateway/scheduler/每日情报/生命维持/状态安全共 45 项通过，覆盖五项主菜单、全部子菜单/读写 action、严格命令、完成/未完成、daily 复盘、白名单/重复事件、ACK 顺序、goal_id 注入/超量/过期、输出边界、timeout/404/422/500/非法 JSON、发送失败脱敏、conversation fallback 以及无 reset/force/任意 URL/method/直接文件入口。11 组 Python 回归通过：qq-control（8 项）、daily briefing module/summary cache、conversation consumers、Catalog、dashboard shell、demon module/review、fitness、focus、calendar；相关测试全部为 fake/临时数据。
- 验证还包括 bridge `src/tests` 共 11 个 MJS 逐文件 `node --check`、`features/catalog` compileall 和待集成状态下的文档门禁 22 项；`git diff --check` 退出 0，仅报告混合工作区既有 LF/CRLF 提示。两项 API import 型回归按既有隔离逻辑报告 focus runtime package 只读 `PermissionError` 并继续通过，没有读取 focus 个人状态。遗留风险是未执行真实 QQ keyboard/Gateway/主 API 端到端；QQ 平台渲染差异仍需人工集成验收，写请求在网络不确定窗口坚持不自动重试，过期/重启后的目标按钮要求重新查看今日目标。

## 完成文档门禁

本轮重新开放后，以下门禁必须由独立 PK-140 实施对话按实际交付重新完成；历史勾选只代表 2026-07-23 基线。

- [x] TASK_RECORD — 已记录实际菜单、固定 action/API、goal_id 缓存、数据/网络/生命周期、副作用、验证与遗留风险。
- [x] TASKS_BOARD — 独立实施完成时曾改为“待集成”；2026-07-25 PK-000 首轮复核发现文本路由优先级阻断后退回“进行中”，整改重新进入“待集成”并通过总控复核后已同步为“已完成”。冻结依赖保持不变，PK-900 当前批次未修改。
- [x] PUBLIC_README — 根 README 与 bridge README 已同步五项菜单、明确写操作、严格命令、安全限制、重启要求和验证命令。
- [x] MODULE_CATALOG — QQ 条目已补充固定业务消费 API、sidecar/业务数据所有权、网络副作用与失败模式；公共 Schema 不变。
- [x] ARCHITECTURE_DOCS — QQ 专项架构与模块化单体架构已记录 action/HTTP 边界、所有权、ACK 顺序、输出和失败语义。
- [x] LOCAL_README — 不适用：没有新增本机路径、端口、启动器、解释器或环境位置；`README.local.md` 未修改。
- [x] AGENT_RULES — 不适用：没有改变长期 agent 工作流、安全、验证、文档或 Git 规则；`AGENTS.md` 未修改。
- [x] VALIDATION — 实施自测的 45 项 Node、11 组相关 Python、11 个 MJS 语法、Catalog compileall 和 22 项文档门禁通过；全部使用 fake/临时数据，`git diff --check` 退出 0（仅既有 LF/CRLF 提示）。PK-000 独立逆向场景另发现一项路由优先级失败，已在下方如实记录，当前不得以本勾选项宣称最终验收通过。

## 本轮独立对话启动提示

```text
继续 Project Kei 的 PK-140 QQ bridge、定时推送与业务私聊菜单增量。先完整
阅读 README.md、AGENTS.md、README.local.md（如存在）、TASKS.md、
tasks/PK-140-qq-bridge.md，以及 PK-150、PK-170、PK-180、PK-190 任务记录
和 docs/architecture/qq-bridge.md；检查 git status 与实际 bridge/API。
只在 PK-140 冻结的版本化 API 矩阵内实现四个子菜单、有限只读摘要、独立
明确写按钮与严格命令。bridge 不得访问 repository 或个人状态，不复制业务规则，不调用
legacy/reset/DELETE/PATCH/force=true，不新增端口、进程、凭证、定时任务或
QQ 权限。所有测试使用 fake QQ/fetch/clock 和虚构数据，不启动 sidecar、BAT、
真实 API、Gateway、Token、LLM、Collector、TTS 或发送。若现有版本化 API
不足，记录精确缺口并停止跨模块修改，交 PK-000 决策。完成后只进入“待集成”，
不得自行标记“已完成”，不得执行 Git 暂存、提交、推送或工作区清理。
```

## PK-000 增量最终复核退回（2026-07-25）

- 结论：暂不通过。既有 45 项 Node 累计测试、16 项业务菜单专项、8 项 qq-control、十组业务/共享 Python 回归、全部 bridge MJS `node --check` 均通过；固定版本化 operation 表、白名单前置、ACK 顺序、危险接口不可达、goal ID 临时隔离及秘密清洗没有发现新阻断。
- 独立逆向场景发现文本路由优先级缺口：合法严格命令 `添加备忘 2030-01-01 每日情报` 先命中 `bridge_core.mjs` 既有 `isBriefing(content)` 的包含匹配，实际只请求 `GET /api/v1/briefing/today`，未调用 `POST /api/v1/calendar/events`。同类冲突可影响标题或技能名包含“每日情报/今日情报/今天情报/今日简报”等关键词的两条合法日历命令。
- 该缺口没有触发危险写入、legacy、reset、真实网络或个人数据访问，但违反本轮“合法严格命令恰好调用一次固定版本化 POST”及日历命令确定性契约，因此 PK-140 从“待集成”退回“进行中”，PK-020 继续保持“待开始”。
- 最小整改归属仅为 PK-140：在 `server/qq_bridge/src/bridge_core.mjs` 调整 C2C 文本分类顺序或建立单一可测试分类接缝，使合法严格业务命令优先于宽泛情报关键词，普通“每日情报”查询和普通 conversation fallback 保持原行为；不得修改四个业务模块、API 矩阵、briefing 业务规则或个人状态。
- 必补正式回归：合法添加备忘标题包含每个情报关键词、合法修炼技能名包含情报关键词时，各自只调用一次 calendar POST；普通“每日情报/今日情报”仍只读 briefing cache；格式错误命令继续零业务 API/零 conversation；白名单外与重复消息继续零额外调用。整改后重跑业务菜单专项、全部 Node、相关 Python 回归、MJS 语法、文档门禁和 `git diff --check`，再交 PK-000 复核。
- 数据隔离：本次复核全部 HTTP/QQ/时间/用户为 fake，Python 业务测试使用临时 store；未探测或读取 bridge `.env`、真实日程/runtime、斩妖/健身/focus/calendar 个人状态、模型、缓存或 `vendor/`，未启动 BAT/sidecar/API/Gateway/LLM/Collector/TTS，未暂存、提交、推送或清理。

## 关键词碰撞整改交回（2026-07-25）

- 只调整 `bridge_core.mjs` 的 C2C 分类顺序：allowlist 与 message-ID 去重后仍先处理精确菜单；其他文字先交给 `businessMenu.handleText()` 做严格功能命令判断，仅在未处理时才执行宽泛 briefing 关键词匹配，最后才进入 conversation。版本化 endpoint、四个业务模块、scheduler、Gateway、QQ token 和 API 契约均未修改。
- 新增正式碰撞回归，覆盖备忘标题和修炼技能名分别包含 `每日情报`、`今日情报`、`今天情报`、`今日简报`、`dailybriefing`：每条合法命令恰好调用一次固定 calendar POST，零 briefing、零 conversation；同时覆盖含关键词的非法日期零 API、重复命令零额外写入、白名单外零调用，以及普通“每日情报/今日情报”仍各自只读一次 briefing cache。
- 整改后业务菜单专项 17 项、全部 Node 46 项、bridge `src/tests` 11 个 MJS 语法均通过；qq-control 8 项及 daily briefing、conversation consumers、Catalog、dashboard、demon module/review/statistics、fitness、focus、calendar 共 12 组 Python 回归通过。待集成状态下文档门禁通过 23 项，`git diff --check` 退出 0（仅混合工作区既有 LF/CRLF 提示）。全部测试使用 fake QQ/fetch/clock、虚构用户/业务响应和临时 store；未访问真实秘密、日程、runtime、个人状态或网络，未启动任何真实进程。
- PK-140 重新置为“待集成”并交回 PK-000 复核，不标记完成；PK-020 及其工作记录保持现状，本整改不放行 PK-020。混合工作区其他任务与个人状态差异未整理、覆盖、暂存或发布。

## PK-000 关键词碰撞整改最终复核（2026-07-25）

- 结论：通过。PK-000 未直接接受整改自测数字；使用独立 fake handler 重放原命令及修炼同类场景，实际调用顺序为 `POST /api/v1/calendar/events`、`POST /api/v1/calendar/practice`、普通情报 `GET /api/v1/briefing/today`，没有额外 briefing、conversation 或写请求。
- 正式业务菜单专项 17/17、全部 Node 46/46、qq-control 8/8，以及 daily briefing、conversation consumers、Catalog、dashboard、demon module/review/statistics、fitness、focus、calendar 共 12 组 Python 回归全部通过；11 个 bridge MJS `node --check` 通过。
- 代码复核确认严格业务命令只在 allowlist 与 message-ID 去重后、情报关键词与 conversation 之前分类；菜单/业务 operation 表、固定版本化路径、危险接口不可达、ACK、goal ID 缓存、scheduler 和秘密清洗边界未发生扩张。
- 文档门禁在最终状态切换前通过 23 项，定向 `git diff --check` 退出 0，仅有混合工作区既有 LF/CRLF 提示。真实 `.env`、日程/runtime、四个业务个人状态、模型、缓存和 `vendor/` 均未探测或读取；未启动真实服务，也未暂存、提交、推送或清理。
- PK-140 本次业务私聊菜单增量正式关闭并改为“已完成”。PK-020 对 PK-140 的依赖已经满足，可由原独立对话重新领取；总控不替其提前实现安装任务。

## 专注到点鼓励增量交回（2026-07-27）

- 契约冻结与依赖：首轮审计确认 focus 内部虽有 session UUID，但公开响应没有稳定会话身份；PK-200 `TextGenerator` 只有 Python 进程内门面，公开 conversation 会写普通 history；sidecar 原契约也只有两份投递状态。用户随后批准最小扩展：PK-140 新增对已完成 PK-200 的形式依赖，focus composition 暴露固定目的受控生成，Node 获得第三份有界原子状态所有权。没有把 QQ 凭证交给主 API，也没有让 Node 读取 focus/conversation repository 或个人 JSON。
- 主 API 与 focus 1.1.0：`TimerResult` 新增有界不透明 `session_id`；新增仅版本化、真实 loopback 的 `POST /api/v1/focus/encouragement`，请求严格只接受 `session_id/start_at`。focus service 重新读取同一 repository，要求当前会话仍 `active` 且 identity 完全匹配，自行计算 mode、elapsed、remaining，再通过应用注入的 PK-200 `TextGenerator` 做一次固定 purpose 生成。请求不接受 OpenID、task、prompt、URL 或聊天 history，受控生成不写普通 history；inactive/replaced/stopped/completed 返回固定 409 且零生成，模型失败返回 `generated=false` 交 Node fallback。focus 状态损坏现在明确 `focus_state_invalid`，不再由一次 status 静默覆盖为空文件。
- 安装与生命周期：跟踪的 focus 本地包版本从 1.0.0 提升为 1.1.0，manifest namespace 不变且不新增 legacy encouragement；已有 1.0.0 runtime 不会被代码自动替换，必须由操作者显式构建 1.1.0 ZIP、校验摘要、调用既有模块 update 并重启 API。bridge 不安装、升级、启用或重启 focus。未运行任何真实模块生命周期写操作。
- QQ 交互：原 `kei:focus:start25` 保持 25 分钟、空 task、`force=false`、`with_audio=false` 且无模型调用；新增固定 `kei:focus:start25:encourage10`，并新增严格单消息 `专注 25 鼓励 10`。自定义专注只接受整数 2–240 分钟，鼓励为正整数且严格早于结束；非法或附加任意文本只返回用法，零 API、零 conversation。成功 start 响应必须提供 `session_id/start_at` 才能登记；普通 status/start/stop 与菜单展示不调用生成，QQ stop 和新的成功 session 会取消该用户旧提醒。
- 调度与幂等：新增 `focus_encouragement_scheduler.mjs` 与忽略的运行路径 `data/focus_encouragement_state.json`。每个用户/会话只有一个 timer；到期先 GET focus status，精确核对 active/session/start/mode/elapsed/remaining，再原子保存 `sending`，然后仅一次 POST encouragement 并向登记用户发送。重复事件、重复登记、重连、重启恢复、`sending/sent/failed/cancelled` 均保持 at-most-once；白名单移除、status 404/超时/无效、会话完成/替换、生成 404/409/500、取消与 shutdown 均零发送。模型 `generated=false` 或生成超时使用有限确定性文案；QQ 失败不重复模型或自动发送。发送成功后才写 `sent`，最终保存失败时磁盘保持 `sending` 并在重启后失败关闭。
- 状态与秘密：focus encouragement 状态最多 256 项，只允许 24 位用户哈希、不透明 session、`start_at/due_at`、有限状态和错误码；不保存完整 OpenID、task、消息、模型文本、Authorization、Token、Secret 或路径。读取执行精确字段/时间/状态语义校验；损坏 schema、完整身份形态键、秘密或消息字段在任何 timer/API/生成/发送/写入前关闭 scheduler，并保留旧字节。写入复用同目录唯一临时文件、`fsync` 和原子替换；测试只使用系统临时目录和 fake fs。
- 网络副作用：只有 sidecar 明确运行、白名单用户显式启用鼓励且到期 identity 复核成功时，新增一次本机 GET focus status、一次本机 POST focus encouragement、最多一次既有 PK-200 OpenAI-compatible generation 和一次 QQ C2C send。主 API 不接触 QQ 身份/sender；Node 不接触 LLM 凭证/persona/history。外部控制台 stop/reset/disable 没有反向推送协议，物理 timer 会在到期 status 复核时逻辑取消，零模型、零发送。
- 验证：全部 bridge Node 测试 72/72，通过五项菜单、显式按钮/严格命令、非法边界、白名单/重复事件、active identity、一次生成/一次发送、fallback、404/409/500、status 超时/损坏、新会话/取消、跨重启、QQ 失败、最终状态保存失败、秘密扫描和异步 shutdown；全部 bridge MJS `node --check` 通过。Python 通过 focus timer/module/dashboard、conversation consumers/module、qq-control 8 项、Catalog、dashboard shell、daily briefing module/summary cache，相关 compileall 通过；PK-200 consumer 测试确认 focus 受控生成使用热切换后的同一稳定 runtime 且 history 不变。首次并行命令中的 `scripts/python.ps1` 被本机 PowerShell 执行策略拒绝，随后使用既有 `.venv-asr` 解释器重跑通过，不是代码失败。
- 隔离：未读取、打印或修改真实 bridge `.env`、三份 sidecar runtime、真实 focus/conversation 状态或模型配置；未启动 BAT、sidecar、Gateway、主 API、真实 LLM/TTS/Collector，未请求 Token 或发送 QQ，未安装依赖。工作区中 PK-150、`vendor/` 与两份个人状态的既有修改均保留且未整理、覆盖、暂存或发布。PK-140 仅置为“待集成”，交 PK-900 独立验收，不自行标记完成。

### 本增量八项文档门禁

- [x] TASK_RECORD — 已记录冻结缺口、实际 API/session、Node 调度、数据、网络、失败、安装升级、验证与遗留外部取消语义。
- [x] TASKS_BOARD — PK-140 已新增 PK-200 依赖并置为“待集成”；名称、P1 与其他已完成依赖不变。
- [x] PUBLIC_README — 已同步显式命令/按钮、受控生成、状态、focus 1.1.0 update/restart 和版本化接口。
- [x] MODULE_CATALOG — QQ 与 focus 条目已同步 encouragement endpoint、数据所有权、网络副作用和失败模式，公共 Schema 不变。
- [x] ARCHITECTURE_DOCS — QQ 专项与模块化单体说明已记录双重 active identity 校验、PK-200 门面、at-most-once 状态及无反向推送限制。
- [x] LOCAL_README — 不适用：未新增端口、解释器、真实环境变量或启动器位置，忽略的本机 README 未修改。
- [x] AGENT_RULES — 不适用：未改变长期 agent 工作流、安全、Git 或验证规则，AGENTS 未修改。
- [x] VALIDATION — 72 项 Node、10 组 Python 回归、全部 bridge MJS、相关 compileall 已通过；文档门禁与 `git diff --check` 在最终状态切换后复跑。

## PK-900 scheduler 竞态整改交回（2026-07-28）

- 只修改 `server/qq_bridge/src/focus_encouragement_scheduler.mjs` 及其定向 Node
  测试。没有修改 focus/PK-180、conversation/PK-200、API、持久化 Schema、菜单、
  Gateway 或其他 scheduler。
- `deliver(key)` 现在会在首个异步调用前取得进程内唯一 in-flight claim；同一 key
  的第二个并发 delivery 会在 status、生成和发送之前退出。claim 不持久化，不改变
  runtime state 的字段、容量或重启语义。
- status 成功或异常返回后，旧流程都必须重新确认 scheduler 未停止、状态仍健康、当前
  entry 仍是相同 `user_key/session_id/start_at/due_at` 的 `scheduled` 记录，并且哈希
  映射出的用户仍在实时白名单中。取消或新 session 替换已经改变 entry 时，旧 delivery
  只释放 claim，不得写回 `sending/failed`、调用模型或发送；等待期间移除白名单会把仍
  匹配的记录持久化为 `cancelled`，随后零模型、零发送。
- 生成与发送 await 后也继续使用相同 identity/status 检查，避免异步返回用旧 entry
  覆盖已取消状态。错误码、fallback、发送前 reservation、最终保存失败 fail-closed 和
  日志脱敏契约保持不变。
- 新增四类永久回归：同 key 并发双 deliver 实际为
  `status/generation/send=1/1/1`；status await 中 `cancelUser`、新 session replacement
  和白名单移除均为 `generation/send=0/0`，旧 entry 最终保持 `cancelled`，替换后的新
  entry 保持 `scheduled`。
- 验证使用系统临时目录、fake status/generator/send、虚构用户和可控 Promise；
  `node --test tests/focus_encouragement.test.mjs` 28/28、全部 bridge Node 76/76、
  `src/tests` 13 个 MJS 逐文件 `node --check` 通过。未读取或探测真实 `.env`、sidecar
  runtime、focus/conversation 个人状态，未启动 BAT、sidecar、Gateway、API、模型或
  QQ，未安装依赖。`scripts/check_task_docs.py` 通过 24 项文档门禁；
  `git diff --check` 退出 0，仅报告混合工作区既有 LF→CRLF 提示。
- 文档门禁：TASK_RECORD 已补本记录；TASKS_BOARD 不适用（PK-140 已是“待集成”且状态/
  依赖未变）；PUBLIC_README、MODULE_CATALOG、ARCHITECTURE_DOCS 不适用（本轮只修正已
  文档化的 at-most-once/取消语义，没有新增用户能力、接口、数据或网络副作用）；
  LOCAL_README、AGENT_RULES 不适用（路径、运行时和协作规则未变）。整改完成后仍只交
  PK-900 独立验收，不自行标记“已完成”。

## PK-000 scheduler 竞态整改最终复核（2026-07-28）

- 结论：通过。PK-000 独立核对 `deliver()` 的首个 await 前唯一 in-flight claim，
  以及 status 成功/异常、生成和发送返回后的 identity、状态、白名单与 shutdown
  重验；没有发现 API、持久化 Schema、PK-180 或 PK-200 所有权扩大。
- 独立重跑 `node --test tests/focus_encouragement.test.mjs` 为 28/28，
  `node --test tests/*.test.mjs` 为 76/76。原并发双 deliver、status-await
  cancel、白名单移除和新 session 替换回归全部通过；旧流程不会复活 entry、
  重复生成或重复发送。
- 独立补跑 focus module、conversation consumers、qq-control 与 feature Catalog
  四组关键 Python 接缝，全部退出 0；qq-control 为 8/8。conversation consumer
  只出现既有 focus runtime 权限隔离提示，没有读取个人状态。
- 任务文档门禁与 `git diff --check` 在状态切换前通过；全部验证使用 fake、系统
  临时目录和受控 Promise，未启动真实 QQ、Gateway、API、LLM 或其他外部服务，
  未读取 `.env`、sidecar runtime、focus 状态或其他个人数据。
- PK-140 正式恢复“已完成”。本轮 PK-900 同步关闭；PK-213 仍独立保持“待集成”，
  不因本批状态更新而被视为通过。

## 斩妖完成反馈联动（2026-07-28）

- 仍只调用固定 `POST /api/v1/demon-slayer/checkins`。完成 action 的 body 为已验证 `goal_id`、`done=true`、空 note 和 `with_encouragement=true`；未完成固定传 `false`。Node 不调用 conversation、不持有 prompt、不访问斩妖 repository/JSON，也不新增 action、timer、文件或网络目标。
- 完成回复直接展示 PK-150 返回的启用时长、当前连续、历史最长、`day/week/month/year` 对应的天/周/月/年单位和 `encouragement`。`once` 显示不累计启用时长；null/零值稳定显示，不出现 `undefined`/`NaN`。Node 只做字段清洗和单位标签映射，不根据日期、check-in 或 cadence 重算统计。
- 新增两项永久菜单回归：daily 完成只产生一次 status GET 和一次 check-in POST，显示启用 2 天、当前 2 天、历史 4 天与 Kei 文案且零 conversation；weekly 与 once fake 响应验证周/月单位、null/零值和无前端推导。累计 business-menu 为 21/21，全部 bridge 为 78/78，均使用 fake QQ/fetch/clock/业务响应。
- 网络与数据副作用保持原边界：实际运行时只有白名单用户明确点击完成后的一次 loopback check-in 和既有 QQ 回复；可选 PK-200 生成完全位于 PK-150 service，失败由同一响应本地降级。部署本轮需要重启 API 与 QQ sidecar。
- 本增量恢复为“待集成”，交回 PK-000/新的 PK-900 验收；按既有串行要求不直接改 `TASKS.md`，不自行标记“已完成”。
- 最终验证补充：11 组相关 Python 文件、business-menu 21/21、全量 bridge 78/78、13 个 bridge MJS 语法、PK-150 compileall 和 dashboard inline module 均通过；任务文档门禁通过 25 项，`git diff --check` 退出 0且仅有既有 LF→CRLF 提示。全部业务/QQ/时间/模型响应为 fake 或临时路径；未读取 `.env`、真实 sidecar state、斩妖/focus 个人状态，未启动或连接任何真实服务。

### 本联动增量八项文档门禁

- [x] TASK_RECORD — 已记录固定 check-in body、字段展示、零前端算法、网络/数据副作用、重启和回归。
- [x] TASKS_BOARD — 建议 PK-140 与 PK-150 均为“待集成”；按 PK-000 总板串行要求不直接修改 `TASKS.md`，由总控同步且不得覆盖 PK-213。
- [x] PUBLIC_README — 已同步 QQ 完成后的启用/连续统计、正确单位、同请求 Kei 鼓励和零额外 conversation。
- [x] MODULE_CATALOG — 已同步 QQ 对 demon check-in 可选受控鼓励的消费及失败边界；没有新增 endpoint、进程或数据所有权。
- [x] ARCHITECTURE_DOCS — 已更新 QQ 专项和模块化单体协议；`server/qq_bridge/README.md` 同步实际按钮 body 与显示规则。
- [x] LOCAL_README — 不适用：没有新增或改变端口、启动器、解释器、环境变量或本机路径。
- [x] AGENT_RULES — 不适用：没有改变长期协作、安全、验证、文档或 Git 规则。
- [x] VALIDATION — business-menu 21/21、全部 bridge 78/78、13 个 MJS 语法和 11 组 Python 接缝回归通过；文档门禁与 `git diff --check` 在最终更新后复跑。

## 斩妖常驻目标添加联动（2026-07-28）

- 斩妖子菜单新增“添加常驻目标”。白名单用户发送精确“添加斩妖任务”或不带标题的“添加日/周/月/年任务（目标）”会弹出日/周/月/年按钮；点击 cadence 只显示严格单消息格式，菜单与说明均零 Project Kei API。
- 严格 `添加日任务 目标名称`、`添加周任务 目标名称`、`添加月任务 目标名称`、`添加年任务 目标名称` 先建立待确认卡。标题最多 80 字，只存在 Node 进程内的用户绑定单次缓存，最多 200 个用户、10 分钟惰性过期；action 只含不透明 pending ID，不含标题、URL、method、payload 或 prompt。每用户新命令替换旧待确认项。
- 只有同一用户点击“确认添加”才调用一次固定 `POST /api/v1/demon-slayer/goals`，body 只含 `title`、明确 cadence、`category=auto`、`repeat_mode=recurring`、`target_date=null`。pending 在调用前即消费，不自动重试写请求；取消、过期、跨用户、重复 interaction/确认和非法格式均零业务写入、零 conversation。标题含“每日情报”等宽泛关键词时仍由严格斩妖命令优先处理。
- Node 不判断妖怪种类、积分、目标 ID、周期归属或重复语义，全部由 PK-150 service 负责；不开放 once/指定日期、目标编辑/删除、奖励、reset、legacy、任意路径或模块生命周期。没有新增状态文件、timer、端口、进程或依赖；sidecar 重启会安全丢弃未确认项。
- 专项新增 5 项，business-menu 累计 26/26、全部 bridge 83/83、`src/tests` 13 个 MJS 语法均通过。相关 12 组 Python demon/consumer/catalog/dashboard/qq-control 回归与 compileall 通过；全部 QQ/API/时钟/业务响应为 fake，Python 使用临时 store/fake provider。
- 未读取或探测真实 `.env`、sidecar runtime、斩妖/focus 个人状态、模型或缓存；未启动 BAT、sidecar、Gateway、API、LLM、TTS、Collector 或网络。混合工作区 PK-133、PK-213、focus、PK-150 既有实现、PK-900、`vendor/` 和个人状态差异均保留，未整理、覆盖、暂存或发布。
- 本增量将 PK-140 与 PK-150 都保持“待集成”，交回 PK-000 安排新的 PK-900；按总板串行约定不直接修改 `TASKS.md`，不自行标记“已完成”。

### 本添加联动八项文档门禁

- [x] TASK_RECORD — 已记录菜单、严格命令、pending 生命周期、固定 payload、失败/排除语义、重启和回归。
- [x] TASKS_BOARD — 建议 PK-140/PK-150 保持“待集成”；不直接修改共享 `TASKS.md`，由 PK-000 统一同步。
- [x] PUBLIC_README — 已同步用户可见按钮/命令、二次确认、内存过期和不开放范围。
- [x] MODULE_CATALOG — 已登记 QQ 消费既有 goals endpoint、短时确认缓存、网络副作用和失败关闭。
- [x] ARCHITECTURE_DOCS — 已同步模块化单体与 QQ 专项的固定 operation、用户绑定确认和零业务算法边界。
- [x] LOCAL_README — 不适用：没有新增端口、解释器、启动器、环境变量或本机路径。
- [x] AGENT_RULES — 不适用：没有改变长期协作、安全、Git、文档或验证规则。
- [x] VALIDATION — business-menu 26/26、全部 bridge 83/83、13 个 MJS 语法、12 组相关 Python 与 compileall 通过；文档门禁和 `git diff --check` 在最终更新后复跑。

## PK-011 可安装化增量交回（2026-07-30）

### 冻结契约与实际文件

- 新增 `package_source/manifest.json`、`config.schema.json`、动态
  `dashboard/index.js` 和包内 README；新增确定性 `package_builder.py`、
  `release/official-release-fragment.json` 与 release README。包精确包含根
  manifest/schema/README/dashboard、`sidecar/package.json`、既有 lockfile 及
  8 个 bridge MJS；不包含 `node_modules`、`.env`、data、凭证、白名单、用户 ID、
  日程/发送状态、缓存、日志、测试、vendor 或个人数据。构建器拒绝输出到 QQ 源码树、
  已存在目标和与 Node package/lock 不一致的版本。
- 新增 `module_adapter.py`：`register_qq_bridge_sidecar(manager, ...)` 只向受信
  ModuleManager 登记固定 `qq_bridge` adapter。adapter 只消费当前版本
  `SidecarDeploymentDescriptor`，不接受 manifest/API/浏览器提供的 path、command、
  cwd 或 env；legacy `start/stop` 明确返回 `deployment_required`，不存在源码树回退。
- dependency root 只允许
  `.project-kei-deployment.json`、`package.json`、`package-lock.json`、`src/`、
  `node_modules/` 五个顶层项。marker 严格拒绝未知/重复字段，只接受 schema 1、
  当前 `qq_bridge` ID/SemVer、当前不可变包摘要、package/lock 摘要和非空 Node/npm
  版本。package、lock 和全部 8 个 MJS 必须与不可变安装包逐字节摘要一致；
  `node_modules/ws/package.json` 必须存在。部署缺失返回 `deployment_missing`，
  尚缺 npm 依赖返回 `dependencies_missing`，结构/schema/版本异常返回
  `deployment_invalid`，package/lock/src 摘要不匹配返回 `integrity_mismatch`。
- 启动命令只能是受信 Node 路径加
  `<dependency-root>/src/index.mjs`；cwd 固定为既有 `server/qq_bridge`（测试中为
  注入 `.env` 的父目录），子进程环境只继承有限系统变量并传入固定 `.env`/data
  内部定位。adapter 不读取 `.env` 内容，不创建配置/data，不运行 shell/npm，不返回
  命令、路径、进程环境或秘密；并发启动只创建一个 fake 进程，shutdown 只经固定
  stdin `shutdown\n` 停止自己拥有的进程。probe 发现但 adapter 不拥有句柄的既有
  进程只报告 running；stop 固定返回 `shutdown_channel_unavailable`，不按探测结果
  终止进程。没有公共远程 stop 或任意终止能力。
- 新增 `control_facade.py`：模块生命周期与 versioned/legacy qq-control status/start
  共用同一 manager、deployment descriptor 和 adapter 实例；status 零启动/零写入，
  start 并发串行且只启用/重启当前安装版本。每日情报和生命维持日程方法原样委托既有
  schedule service/repository，没有第二套验证或数据规则。共享 `api.py` 与生产
  composition 未修改，待 PK-000 串行创建一次 adapter、登记到进程级 manager，并把
  同一实例注入 facade/router。

### 生命周期、副作用与失败模式

- 模块安装/网页点击/普通启动不执行 npm。PK-020 独占显式
  `setup.bat --profile qq`：从不可变安装包的 `sidecar/` allowlist 复制到同父 staging，
  在 staging 执行锁定 `npm ci`，校验后最后写 marker 并原子发布到
  `server/runtime/module-dependencies/qq_bridge/<version>/`。本任务没有修改或执行
  PK-020 安装器。
- 更新/卸载程序包不得删除既有 `server/qq_bridge/.env` 与
  `server/qq_bridge/data/`。依赖 deployment 是可再生成数据且不进入安装包
  `installed_tree_sha256`；不可变包全树摘要仍不排除任何子树。缺配置/缺 deployment/
  缺依赖进入可修复 readiness，完整性/结构异常进入 unavailable 并零启动。
- 实际网络副作用没有扩大：只有 adapter 被明确启用并通过全部 readiness 后，Node
  sidecar 才按既有规则连接 QQ Gateway、调用固定 loopback 版本化 API 和向白名单 C2C
  发送。安装、readiness、动态面板展示和本轮测试均零 QQ、零 Core HTTP、零 LLM/
  Collector/TTS/ASR 网络。

### 验证与隔离

- `python -m unittest qq_bridge.tests.test_installable_package`：10/10。覆盖确定性
  allowlist、release manifest、秘密扫描、错误输出、marker 正/反 schema、重复/未知
  字段、旧版本、大小写/摘要篡改、package/lock/src/node_modules/顶层边界、无源码树
  fallback、缺配置/Node/deployment/依赖、并发单启动、固定 shutdown、外部进程不终止、
  ModuleManager 安装/启用/禁用/卸载/重装、外部 `.env`/runtime 保留，以及 versioned/
  legacy router 与生命周期共用同一 adapter。
- 全部 bridge Node 测试 83/83；8 个 `src/*.mjs` 与动态面板 `node --check` 通过。
  `test_installable_modules.py` 通过，既有 qq-control 8/8；本增量 Python 文件
  `py_compile` 通过。确定性 ZIP 经官方 Catalog builder 校验：
  `qq_bridge-0.1.0.zip` 为 104151 bytes，SHA-256
  `ced1193729d752ee2ea06453cb20831f20da5128f6bf607279ff25e041408136`，
  manifest SHA-256
  `f29ac8578d041e632881a203d8c091d552248bb79ca3c3d3cb0d83de52c0003a`。
- 所有动态验证只使用系统临时目录、fake Popen/process probe、虚构 Secret、临时
  module registry/data/deployment 和 ASGITransport。未读取、探测、diff、复制或修改
  真实 QQ `.env`、`data/**`、node_modules、日程/发送状态、白名单、Token、个人状态、
  缓存、模型或 vendor；未运行 npm、BAT、sidecar、Gateway、真实 API/QQ/LLM/TTS/
  Collector，未执行 Git 暂存、提交、推送或清理。

### 本增量八项文档门禁

- [x] TASK_RECORD — 本节已记录包、adapter、marker、facade、数据/网络副作用、失败语义、验证和共享装配请求。
- [x] TASKS_BOARD — 按 PK-000 冻结不修改共享 `TASKS.md`；本任务文件保持“待集成”，由总控串行同步。
- [x] PUBLIC_README — 共享 README 冻结且本轮未修改；用户可见安装/运行边界已写入 QQ 专属 README 与包内 README，公共汇总由 PK-000 装配。
- [x] MODULE_CATALOG — 已提供 release fragment 与可复现摘要，但未修改/发布共享官方 Catalog；由 PK-000 合并条目和 Release 资产。
- [x] ARCHITECTURE_DOCS — 共享架构冻结且未修改；QQ 专属 README 已记录不可变包、独立 dependency deployment、marker、同 adapter facade 与失败模式，PK-000 负责公共架构汇总。
- [x] LOCAL_README — 不适用：未新增端口、用户环境变量、解释器位置或机器配置；真实 `README.local.md` 未修改。
- [x] AGENT_RULES — 不适用：未改变长期协作、安全、文档、Git 或验证规则；混合工作区其他任务修改均保留。
- [x] VALIDATION — 专项 10/10、bridge Node 83/83、Core lifecycle、qq-control 8/8、Catalog/dashboard/feature catalog、全部 bridge MJS/动态面板语法、Python 编译与官方 Catalog builder 已通过；`git diff --check` 退出 0，仅有混合工作区既有 LF→CRLF 提示，文档门禁在本记录后复跑。

本增量保持“待集成”。共享装配只请求 PK-000：在生产 composition 对进程级 manager
调用一次 `register_qq_bridge_sidecar()`，注入只匹配当前 dependency-root
`src/index.mjs` 的固定非秘密 process probe（helper 不允许省略，避免 Core 重启后
重复 sidecar），再以返回的同一 adapter 构造
`QQControlAdapterFacade` 并装配既有 router；同时由 PK-020 接入冻结的 staging/npm/
marker 发布流程。PK-140 不自行修改 `api.py`、模块管理 service、共享 Catalog/dashboard/
README/架构，不发布 Release。

## PK-000 串行装配与 0.1.1 候选（2026-07-30）

- PK-000 已在 `server/module_composition.py` 对进程级 ModuleManager 调用
  `register_qq_bridge_sidecar()`，process probe 只匹配固定 dependency root 的
  `src/index.mjs`；同一 adapter 实例被注入 `QQControlAdapterFacade`。生产装配不再
  以源码树 BAT、任意命令或宽泛 Node 进程判断作为生命周期主路径。
- facade 新增固定 `POST /api/v1/qq-control/life-support/reminder` 接缝，只接受有限
  reminder kind，通过已安装 conversation 的受控文本生成能力返回文本；不写普通
  chat history。conversation 缺失、生成失败或返回异常时使用确定性本地提醒，不影响
  sidecar/Core。没有新增远程路径、凭证、timer、QQ 权限或个人状态所有权。
- 因上述包内公开接缝变化，候选模块版本提升为 `qq_bridge@0.1.1`；Node sidecar 自身
  `package.json` 的内部依赖包版本仍为 `0.1.0`，它不是 Project Kei 模块 SemVer，
  lockfile 与安装包逐字节校验规则未改变。
- 两轮独立临时构建字节一致。最终候选
  `qq_bridge-0.1.1.zip` 为 104181 bytes，SHA-256
  `f67b87f936ac5041a0ce1bfab68984ac53ec36b6be21bf17510435ee9d929bdf`，
  manifest SHA-256
  `9ad2d97e35715e840f2943267dd92889297126b009effe1d9a9e14e9853a2638`。
  包路径扫描对 `.env`、`node_modules`、`vendor`、`data` 和已知个人状态文件为
  0 命中。
- 累计离线证据：可安装包 11/11、qq-control 8/8、全部 Node 83/83、19 模块官方
  release-set 生命周期通过。全部使用临时目录、fake process/HTTP/文本生成；没有
  启动真实 QQ、Gateway、API、LLM、Collector 或读取真实 `.env`/runtime/data。

PK-140 继续保持“待集成”，上述 0.1.1 候选取代本文件早先 0.1.0 的发布摘要，但
保留早期记录作为历史证据；只有最终 PK-900 可以确认完成。

## 控制台功能恢复与 0.1.2 候选（2026-08-01）

- `needs_configuration` 的 QQ sidecar 现在可在未启用、未启动状态装载受信动态面板；
  面板把“QQ 功能启动”“每日情报定时推送”“生命维持系统”恢复为三个独立折叠区。
  状态查询、显式 start 和两类 schedule API 保持原契约，没有新增 stop、自动安装、
  自动启动、自动生成或自动发送。
- 候选模块提升为 `qq_bridge@0.1.2`。确定性 ZIP 为 104963 bytes，SHA-256
  `d8b4ea9eab69cfbe1908e75990634fee509c8af7c3ca48a56f3901b2fc70e3ce`，
  manifest SHA-256 为
  `30db7b7d80472afc357222ba9f3c7eec2a00f784e5d3f11ca1d1a89c8d2d12cb`。
- 专项可安装包 12/12、dashboard shell、ModuleManager 生命周期、Node 语法检查均
  通过；全部使用临时 registry/runtime/data 和 fake 边界，未读取 `.env`、真实
  schedule/runtime、白名单或凭证，未启动 sidecar、Gateway 或发送 QQ。

PK-140 仍保持“待集成”，等待 PK-900 累计复核，不提前标记完成。

## QQ 独立功能卡与 0.1.4 包修复（2026-08-01）

- 控制台把同一 `qq_bridge` sidecar 安装单元拆成三个独立视觉卡：QQ 功能启动、每日
  情报定时推送、生命维持系统。三卡分别使用 `qq-launch.png`、
  `briefing-schedule.png`、`life-support.png`，各自独立折叠；底层仍共用一套固定
  adapter、凭证和进程，不复制业务规则或新增安装包。
- 配置面板增加 `https://q.qq.com/` 官方入口。已有 `.env` 时只显示“检测到既有本机
  配置”并继续复用，不读取或回显字段值；缺配置时只提示 `.env.example` 的字段名与
  本机填写位置。安装和页面加载均不启动 sidecar、不运行 npm、不发送 QQ。
- `needs_configuration` 状态可装配固定本机 qq-control facade，以便读取非秘密状态与
  配置两类 schedule；仍不可自动启用或启动。显式 start 继续要求 readiness 全部通过。
- 修复构建器遗漏：manifest 升版时同步重写包内 `package.json`、`package-lock.json`
  及 lock 根包版本。候选为 `qq_bridge@0.1.4`，ZIP 105805 bytes，SHA-256
  `26a08d586bf5ad218135e06efcd9c9b992022772d6ef0b526835eb78808df445`；manifest
  SHA-256 `e7c81a8e9deec897bee3619766cea733ebe8fba0eb81694778c0455e436212c3`。
- 本机以官方目录精确 SHA 登记 0.1.4，并通过受控 resolver、公开 lock 与
  `npm ci --ignore-scripts` 原子生成依赖 marker；`inspect` 返回 `ready`。只检查既有
  `.env` 是否存在，未读取内容，未启动 Gateway/sidecar 或发送消息。

PK-140 继续保持“待集成”，等待 PK-900 累计复核。
## QQ 三卡与 0.1.5 本机运行修复（2026-08-01）

- 控制台明确显示三个独立视觉卡：`module-qq_bridge`（QQ 功能启动）、`module-qq-daily-push`（每日情报定时推送）、`module-qq-life-support`（生命维持系统），分别使用 `qq-launch.png`、`briefing-schedule.png`、`life-support.png`。底层仍共享一个受控 sidecar，不复制进程、凭证或调度规则。
- 面板始终提供 `https://q.qq.com/` 官方配置入口；检测到既有 `.env` 时仅显示可复用状态，不读取或输出值。缺配置时只提示 `.env.example` 的本机填写位置。
- 旧 0.1.4 本机运行目录存在前端资源 ACL 不可读问题。本轮以当前 Windows 用户通过本机 Core 原子更新为 `qq_bridge@0.1.5`，动态入口实测 HTTP 200；Node 依赖部署经固定 allowlist、公开 lock、`npm ci --ignore-scripts` 和 marker 校验后为 `ready`。
- 0.1.5 确定性 ZIP 为 105805 bytes，SHA-256 `d9f1a26edb784df0e963ad41a10cc4e6b7e7fb91762adc62ab80f871ca87f319`；manifest SHA-256 `c2a246d962573621335459fdb7d258e3cd879ab49b60753f1b21097d6ceec357`。
- 验证：可安装包 13/13、qq-control 8/8、dashboard shell、官方 Catalog、四个相关 JS 语法检查均通过。未启动真实 QQ/Gateway、未发送消息、未读取 `.env` 内容。当前旧 Core 进程必须重启后才会装配新 qq-control 路由；任务状态保持“待集成”。

## QQ 启动视觉兼容修正（2026-08-01）

- 不变更当前运行中的 `qq_bridge@0.1.5`、sidecar 或 qq-control 行为；公共外壳把 QQ 卡的原图恢复为受 Core 固定提供的 `/dashboard/assets/qq-launch.png`。
- 图片成为既有显式启动按钮的视觉代理；旧文字启动按钮仅从布局隐藏，实际请求、readiness、并发和运行中禁用规则保持同一实现。
- QQ 开放平台入口改为明显的链接按钮。它不会在加载时访问外部站点，也不会读取、创建或覆盖 `.env`。
- 本机 Browser 验收观察到 `状态：running`，因此图片按钮按契约禁用以防重复启动；没有点击启动、没有重启 sidecar、没有发送 QQ 消息。

## QQ 凭证受控配置面板与 0.1.6 候选（2026-08-08）

- PK-140 新增自有 `QQBridgeConfigurationStore`。它只拥有受信 adapter 已冻结的
  `server/qq_bridge/.env` 路径，只解释 `QQBOT_APPID`/`QQBOT_SECRET`，不让 Core、
  manifest、浏览器或请求提供 path/command/cwd/env。状态只返回 configured/missing、
  两字段是否已设置和 AppID 尾号掩码；Secret 与完整 AppID 不进入响应、异常或日志。
- 动态 QQ 面板新增固定 `https://q.qq.com/` 入口、AppID 文本框、Secret 密码框和
  “保存/替换”动作。页面加载只 GET 且零写入；输入不写 localStorage/sessionStorage，
  Secret 保存成功或失败后都会清空且永不回显。空 Secret 保留已有值，缺失字段时固定
  422，不调用 LLM、不启动 sidecar、不运行 npm。
- 新增 `GET/POST /api/v1/qq-control/configuration`。GET 只允许真实 loopback（带
  Origin 时必须精确受信）；POST 在读取 body 前同时要求真实 loopback 和精确受信
  Origin，只接收有限 JSON `appid/secret`，拒绝未知/重复字段、非字符串、非 JSON 和
  超长 body。所有失败只返回有限错误码，不回显请求值。
- 保存保留 `.env` 的其他键和值，使用进程内串行锁、同目录唯一临时文件、文件
  `flush/fsync` 和原子替换；替换失败清理临时文件并保留旧字节。响应明确
  配置实际变化时 `restart_required=true`，全空/未变化保存保持零写入；若 sidecar
  已运行，操作者需先在本机停止旧进程，再通过
  同一 adapter facade 显式 start，没有新增远程 stop、强杀、BAT fallback 或第二套
  bridge。
- 生命维持兼容 `POST /life-support/reminder` 已在本轮开始前存在于同一
  facade/router：固定 kind allowlist、动态 PK-200 Provider、零 history、失败确定性
  fallback，Node 行为和接口边界未再次修改。
- 候选模块提升为 `qq_bridge@0.1.6`。两次临时目录确定性构建逐字节一致：ZIP
  `109140` bytes，SHA-256
  `9b9fde6ecf4585c437ddb8de6c29b947d028fc160c3390695210cf919bc4c967`；manifest
  SHA-256 `bfebe6f01d3f889e69e27547cf9b853c55fcb583e83456f5b1d48a1789f36215`。
  包仍不含 `.env`、data、node_modules、凭证、白名单、个人状态、缓存或日志。
- 专项与既有可安装包/qq-control 共 27/27、全部 bridge Node 83/83、四组
  installable/Catalog/dashboard/conversation consumer 回归、8 个 bridge MJS 与动态面板
  `node --check`、相关 Python compileall、25 项任务文档门禁和 `git diff --check` 均通过；
  全部使用 TemporaryDirectory、虚构 AppID/Secret、fake adapter/process/provider 与
  ASGITransport。未读取、打印或修改真实 QQ `.env`/data/runtime，未启动 BAT、Node
  sidecar、Gateway、API、LLM/Collector/TTS，未发送 QQ，也未执行 Git 发布或清理。

PK-140 保持“待集成”，交 PK-900 独立复核；按 PK-000 冻结不修改 `TASKS.md`、
共享 `api.py`、ModuleManager、公共 dashboard/Catalog/README 或生产 composition。

### 本增量八项文档门禁

- [x] TASK_RECORD — 本节记录配置接口、秘密边界、原子写入、重启语义、包摘要、测试与隔离。
- [x] TASKS_BOARD — 不修改冻结的 `TASKS.md`；PK-140 继续待集成，由 PK-000/PK-900 串行处理。
- [x] PUBLIC_README — 共享 README 冻结；用户可见说明已同步 QQ 专属 README 与包内 README。
- [x] MODULE_CATALOG — release fragment 已升至 0.1.6；共享 Catalog 由 PK-000 合并，本任务不发布。
- [x] ARCHITECTURE_DOCS — 公共架构冻结；QQ 专属 README 已记录所有权、API、防护、写入和生命周期边界。
- [x] LOCAL_README — 不适用：固定路径、端口、解释器与本机启动方式均未变化。
- [x] AGENT_RULES — 不适用：长期协作、安全、Git 和验证规则未变化。
- [x] VALIDATION — 专项/可安装包/qq-control 27/27、全部 Node 83/83、四组公共回归、全部 MJS/面板语法、compileall、25 项文档门禁、双构建摘要与 `git diff --check` 均通过。

## QQ 0.1.7 运行时声明与本地 ZIP 依赖修复（2026-08-09）

- QQ manifest、包内 `package.json`/lock 与公开安装器统一声明 Node.js
  20/22/24/26 x64；推荐 Node 24 LTS。包提升为 `qq_bridge@0.1.7`，避免覆盖既有
  0.1.6 不可变资产。
- 本地 ZIP 与官方包使用相同的显式 dependency deployment；`node_modules` 仍不进入
  ZIP，也不写入只读安装程序树。缺 Node、lock 部署、`.env` 或 adapter readiness
  时只显示有限状态并阻止启动，不读取或回显凭证。
- 确定性候选：`qq_bridge-0.1.7.zip`，109341 bytes，SHA-256
  `abba8d1bddf8304525011d4d34c543d299896df71f578e0e232444101434350f`；根
  manifest SHA-256
  `e8799558d97a738b3d38595b76459da752bcb1b442c93ce3d4e9673166f2429d`。
- 验证：QQ 包 13/13、全部 Node 83/83、Windows local ZIP/Node26/幂等 3/3、官方
  19 模块集合和控制台显示通过。没有启动 Gateway、发送 QQ、读取 `.env` 或运行
  真实业务；候选 ZIP 只生成在系统临时目录，尚未上传 Release。

### 本增量八项文档门禁

- [x] TASK_RECORD — 已记录运行时声明、依赖部署、包摘要与隔离证据。
- [x] TASKS_BOARD — 已由 PK-000 将 PK-140 重新登记为“待集成”。
- [x] PUBLIC_README — 已同步 Node 支持和显式 QQ setup 说明。
- [x] MODULE_CATALOG — 0.1.7 候选条目与 fragment 已同步，未发布。
- [x] ARCHITECTURE_DOCS — 安装与模块包契约已同步。
- [x] LOCAL_README — 不适用：未读取或修改本机 QQ 配置。
- [x] AGENT_RULES — 不适用：秘密、进程和网络边界未改变。
- [x] VALIDATION — 包、Node、Windows、Catalog、控制台和静态门禁已执行。

## QQ 回复附带语音：PK-210 公共契约阻断（2026-08-10）

### 只读审计结论

- 当前 PK-210 公开版本化接口只有 `/api/v1/voice/health`、上传用户音频后执行
  ASR→conversation→TTS 的 `/api/v1/voice/chat` 与流式变体，以及受控临时音频读取。
  它没有“对已经生成的 Kei 文字回复仅执行一次 TTS”的 sidecar 可消费接口。
- QQ bridge 当前普通聊天已通过 `/api/v1/conversation` 获得最终文字。复用
  `/api/v1/voice/chat` 会要求伪造用户音频、再次执行 ASR/conversation/LLM 并写入普通对话
  历史；直接导入 PK-210 的 `TextToSpeechProvider`、Voice Pack、模型或音频路径则越过模块边界。
  两种方式均被本需求禁止。因此在 PK-210/PK-000 冻结下述最小公共契约前，PK-140
  不实现配置开关、TTS 调用或 QQ 音频上传，也不提升候选包版本。
- QQ 官方单聊富媒体流程要求先取得 `file_info`，再以 `msg_type=7` 和
  `media.file_info` 发送；本机音频不能依赖 QQ 平台回连 `127.0.0.1`，也不能使用用户
  提供的 URL。后续 bridge 应只对 PK-210 返回的有界内存字节执行 QQ 官方预上传、分片
  PUT、分片确认与合并流程，预签名地址只能来自 QQ 上传响应。首期采用语音 `file_type=3`
  且必须由 PK-210 返回 QQ 已验证支持的固定音频格式；不得把不受控扩展名当作格式判断。

### 请求 PK-210/PK-000 冻结的最小接口

- 新增单一版本化入口 `POST /api/v1/voice/synthesize`，仅由已安装 voice 模块装配，沿用
  Core 的真实 loopback/受信调用边界；不新增端口、进程、legacy 路由或 QQ 权限。
- 请求必须是严格 JSON object，未知/重复字段拒绝：
  `{"purpose":"qq_reply","text":"..."}`。`purpose` 只允许固定值 `qq_reply`；
  `text` 是 PK-200 已生成且经过 bridge 边界检查的最终回复，最多 1500 个 Unicode 字符，
  空白、超长或控制字符异常固定 422。接口不得接受 prompt、OpenID、用户路径、模型、
  Voice Pack ID、任意 URL、任意音色或任意生成参数。
- 接口只调用 PK-210 已有 active Voice Pack 与 `TextToSpeechProvider` 一次，零 ASR、零
  conversation/LLM、零 history 写入。建议直接返回有界二进制响应，不返回 JSON base64、
  本机路径或可由请求者选择的下载地址：成功 200，`Content-Type` 必须是冻结的
  QQ 可发送音频类型，并提供可信 `Content-Length`；最大 20 MiB，同时 PK-210 应设更保守的
  产品级时长/大小上限并在契约中固定。空音频、格式/容器不匹配、长度不符或超限必须拒绝。
- 失败只返回稳定脱敏 code：`voice_unavailable`、`voice_pack_unavailable`、
  `tts_timeout`、`tts_failed`、`audio_invalid`、`audio_too_large`；不得返回 Provider 正文、
  prompt、模型/Voice Pack 路径、异常或堆栈。单次请求不得自动重试付费生成。
- `/api/v1/voice/health` 继续只提供非秘密 availability/readiness，供 QQ 面板显示
  `voice unavailable`；健康检查不得合成、读出 Voice Pack 注册表内容或写状态。
- PK-210/Core 对响应完成、客户端断开、超时与取消负责释放其临时资源；QQ bridge 只持有
  有界内存字节，不持久化音频、文字、OpenID 或文件路径。

### PK-140 在契约落地后的冻结实现范围

- 本机配置键建议固定为 `QQBOT_REPLY_WITH_VOICE=true|false`，默认关闭。它是非秘密布尔
  设置，仍由 `QQBridgeConfigurationStore` 在固定 `.env` 中原子保存并保留其他键；GET
  仅返回 `reply_with_voice` 与有限 availability，Secret 永不回显。页面加载、展开、状态刷新
  均零写入、零 TTS、零 QQ；变更后明确显示 sidecar 是否需要重启。
- 首期只为白名单用户经 `/api/v1/conversation` 获得的普通、实质性、完整且不超过 1500
  字符的回复，在文本成功发送后尝试一次语音。菜单、子菜单、按钮 ACK、状态查询、确认、
  拒绝、错误、非法命令、斩妖/健身/专注/日历业务结果、生命维持与专注鼓励均保持纯文本。
  每日情报明确不纳入首期：其内容长、分片多且属于主动定时发送；开启 QQ 语音不能触发
  Collector、新 LLM 或额外 TTS 成本。任何扩展须另经 PK-000 冻结。
- QQ 侧使用单聊富媒体 `file_type=3`，先执行官方受控上传取得短期 `file_info`，再以
  `msg_type=7` 发送；不使用公网临时文件 URL。20 MiB 是官方语音软限制，首期实现仍须采用
  更小的固定内存上限，并以 PK-210 冻结的格式/时长为准。文本是可靠基线；TTS、上传或
  语音发送失败只记录稳定 code，不撤销、不重复发送文本，也不回显上游内容。
- 白名单检查继续先于 conversation、TTS 和 QQ 上传；同一消息去重与 in-flight claim 覆盖
  文本和语音整个事务。重复事件、并发、shutdown/cancel 后均零新增合成/上传/发送；成功
  文本最多附带一次语音，不把音频结果写入 sidecar runtime 状态。

### 本次边界与交接

- 本次仅完成代码/协议审计和精确公共契约请求；未修改产品代码、manifest、配置 schema、
  dashboard、release 或 PK-210，也未新增测试，因为在缺少合成接口时编写可运行接线会制造
  第二套语音契约。PK-140 状态保持“待集成”。
- 交 PK-000：裁决并把上述合成接口交 PK-210 实现/验收；接口冻结后再将本增量退回 PK-140，
  由 PK-140 完成配置开关、受控 QQ 分片上传、文本优先降级、幂等与全部 fake 永久回归。
- 隔离证明：未读取、输出或修改真实 `server/qq_bridge/.env`、QQ data/runtime、凭据、
  用户标识、Voice Pack 注册表、模型、参考音频、个人状态或 vendor；未启动 BAT、sidecar、
  Gateway、Core、LLM/TTS/ASR，未发送 QQ，未执行 npm 或 Git 发布/清理。

### 补充审计：分段合成不是可发送的完整媒体（2026-08-10）

#### 现有实现

- PK-210 的 `split_text_for_tts()` 默认可按标点和约 42 字边界拆分文本；
  `VoiceService._synthesize_all()` 按原顺序逐段调用 Provider，每段得到独立
  `AudioResult`，当前 GPT-SoVITS Provider 只接受并返回 WAV。
- 非流式接口把每段 WAV 分别发布为独立临时音频；`include_audio_base64` 只编码第一段，
  并不代表完整回复。流式接口逐个发布 `audio_part`，其中只有 index/total/text/临时文件名，
  没有统一 PCM 参数、逻辑 `utterance_id`、连续压缩帧或最终单容器产物。
- 当前实现没有把多个 WAV 字节直接拼成一个文件，但也没有“解码到统一 PCM→有界处理→
  顺序合并→一次目标编码”的公共能力。QQ bridge 因此不能把现有多个 URL/WAV 当成一条完整
  QQ 语音，也不能只取第一段后伪装成功。

#### 建议由 PK-210 冻结的逻辑 utterance 契约

- 保留 Provider 内部短句分段，但每个结果必须绑定受控 `utterance_id`、连续 `segment_id`
  和输入顺序；所有段必须解码为一致的采样率、声道与位深 PCM。不匹配、缺段、重复段、
  越界段或乱序完成只能使整个 utterance 失败，不能丢段后返回成功。
- PCM 合并前可执行有界首尾静音裁剪、响度/峰值归一和必要淡入淡出；这些算法、阈值和固定
  参数归 PK-210 媒体层所有。QQ/Pi 不导入实现，也不提交 ffmpeg 命令、codec 参数、路径、
  Voice Pack 或模型信息。
- 面向完整消息的输出只在所有段成功并按序合并后编码一次。独立 WAV、MP3、AAC、Opus、
  Ogg 或 Silk 容器/码流不得用字节连接模拟合并；任何部分成功都不能产出可发送的 final。
- 面向树莓派的低延迟输出应由 PK-210/受控传输层从同一逻辑 PCM 产生连续帧；每帧至少包含
  有界 `utterance_id`、`segment_id`/`sequence`、`final`、固定 `codec`、`sample_rate`、
  `channels`。Pi 端只按序缓冲；缺帧、重复冲突、断线、取消或超时立即废弃当前 utterance，
  不续播旧帧。此流式协议属于 PK-210 与 PK-220/传输层共同决策，不由 PK-140 实现。
- 建议将上一节的 `POST /api/v1/voice/synthesize` 请求补充为严格固定 profile：
  `{"purpose":"qq_reply","output_profile":"qq_c2c_voice_v1","text":"..."}`。
  `output_profile` 是代码内 allowlist 枚举，不是 codec 参数；返回必须是一个完整 final
  utterance 的二进制及有限元数据（opaque `utterance_id`、格式、字节数、时长），不得返回
  segment 文本、临时路径或中间 WAV。相同受控 request/idempotency key 的并发请求应合并为
  一次 TTS；QQ 与 Pi 同时消费同一回复时应复用同一逻辑 utterance 或从同一 PCM 派生，不能
  各自再次调用付费 TTS。跨消费者的 key、内存寿命与取消所有权需由 PK-000/PK-210 冻结。
- 中间 PCM/WAV 只能位于有界内存或 PK-210 受控临时目录；成功响应结束、失败、客户端断开、
  取消、超时和 shutdown 都必须清理。不得进入日志、长期缓存、个人状态、模块包、Git 或
  sidecar runtime。清理失败只记录稳定 code，不记录路径。

#### QQ 官方边界与固定适配策略

- QQ 官方富媒体概述当前列出语音展示支持 silk/mp3/wav/ogg，但正式单聊上传请求 schema
  对 `file_type=3` 明确写为 silk，二者存在文档口径差异。PK-140 采取 fail-closed 策略：
  `qq_c2c_voice_v1` 仅接受 PK-210 最终返回的 `audio/silk`，不在 Node 中把 WAV 改扩展名或
  自行转码；若 PK-210 尚无受控 Silk 编码器，则面板显示 `voice unavailable` 并保持纯文本。
  是否由 PK-210 新增固定媒体编码 Provider/随模块安装的受控编码依赖，须由 PK-000 裁决。
- QQ 官方单聊语音上传的软限制为 20 MiB、硬限制为 200 MiB。首期建议采用更严格的项目上限：
  完整 Silk 不超过 8 MiB、时长不超过 60 秒、只允许一个 final utterance；任一元数据缺失、
  容器/魔数不匹配、长度不符或超限均零上传并保留文本。该 8 MiB/60 秒产品上限需随
  `qq_c2c_voice_v1` 一并由 PK-000/PK-210 最终冻结。
- Node 只负责：校验固定 profile/Content-Type/长度/时长，按 QQ 返回的 block size 和 part
  列表上传原始 final 字节，逐片完成后用 `upload_id` 合并取得 `file_info`，再发送一次
  `msg_type=7`。预签名 URL 只来自当前 QQ API 响应并须 HTTPS、数量/大小/总量有界；不接受
  浏览器、manifest、用户文本或 Project Kei 响应提供上传 URL/文件名。
- 腾讯官方来源（审计日期 2026-08-10）：
  [富媒体消息概述](https://bot.q.qq.com/wiki/develop/api-v2/server-inter/message/rich-media.html)、
  [单聊富媒体上传](https://bot.q.qq.com/wiki/develop/api-v2/autogen/api/v2_users_user_openid_files.post.html)、
  [单聊富媒体预上传](https://bot.q.qq.com/wiki/develop/api-v2/autogen/api/v2_users_user_id_upload_prepare.post.html)、
  [发送单聊消息](https://bot.q.qq.com/wiki/develop/api-v2/autogen/api/v2_users_user_openid_messages.post.html)。

#### 需要 PK-000/PK-210 决策与永久回归

- 决策项：逻辑 utterance/PCM 标准化所有权、固定 `qq_c2c_voice_v1` 编码实现与依赖、
  `utterance_id`/idempotency/cancel 生命周期、Pi 连续帧协议，以及 QQ 8 MiB/60 秒产品上限。
  在这些契约冻结前，PK-140 继续零产品接线，不在 Node sidecar 复制分段、PCM、编码或模型逻辑。
- PK-210 契约测试需全部使用短小 fake PCM/fake encoder，覆盖顺序、统一 PCM 参数、缺段、
  重复段、乱序完成、取消、编码失败、格式/时长/大小超限、临时文件清理、并发同 key 单次
  TTS 与每 profile 单次编码；不得调用真实模型、下载/执行真实 ffmpeg、连接 QQ 或 Pi。
- 契约落地后，PK-140 再用 fake final Silk/fake QQ 分片接口覆盖严格格式、大小、时长、
  part 边界、上传失败、`file_info` 发送、重复事件、并发、取消与 shutdown；证明 Node 零文本
  分段、零 PCM 拼接、零转码、零二次 TTS。本补充未修改 PK-210、QQ 产品代码或候选包。

### PK-210 合成契约已落地，退回 PK-140（2026-08-10）

- PK-210 已实现仅版本化的 `POST /api/v1/voice/synthesize`：严格请求保持
  `{"purpose":"qq_reply","text":"..."}`，profile 不由客户端选择；最终固定为
  `qq_c2c_voice_v1`、`audio/silk`、`final=true`、最多 60 秒/8 MiB。链路只调用一次
  TTS 和一次 encoder，零 ASR/conversation/LLM/history；分段统一 PCM、顺序校验、
  取消/断开/关闭清理与同 key 并发去重均由 voice 所有。
- 当前仓库没有随 voice 包交付生产 Silk encoder；未注入或未就绪时稳定返回
  `encoding_unavailable`，PK-140 必须保留纯文字，不能接受 WAV 或自行转码。PK-210
  health 只报告本地 engine、Voice Pack、encoder readiness，不读取 QQ Secret、推断
  App 权限或发送真实消息探测。
- 请 PK-140 继续实现默认关闭的开关、受控 C2C `file_info` 上传/`msg_type=7` 发送、
  文本优先降级和端到端幂等。整体 voice readiness 还须加入非秘密
  `qq_media_upload_capability=unknown|available|unavailable|denied`；`unknown` 默认
  fail closed。只有本地 `audio/silk` profile ready 且能力明确 `available` 时 UI 才能
  开启，其他状态一律显示 voice unavailable，文字发送不受影响。

## QQ 普通聊天语音后半链路与 0.1.8 候选（2026-08-10）

### 已实现接口与用户行为

- PK-140 自有 `QQBridgeConfigurationStore` 新增非秘密
  `QQBOT_REPLY_WITH_VOICE=true|false`，缺失时确定性默认 false。动态 QQ 面板显示
  “QQ 回复同时发送语音”开关与 `available/encoding_unavailable/qq_media_*` 有限状态；
  页面加载、展开和刷新只读，只有操作者改变开关并提交时才写固定 `.env`。保存继续保留
  其他键、空 Secret 不覆盖、唯一临时文件+`fsync`+原子替换，失败保留旧字节；响应不含
  Secret、完整 AppID、白名单或其他 `.env` 值。
- `QQControlAdapterFacade` 构造签名新增可选
  `voice_health_provider=None, qq_media_capability_provider=None`；两者支持同步值/函数或
  async 函数。facade 只接受 PK-210 health 中严格的 `qq_c2c_voice_v1`、
  `audio/silk`、`final=true`、`max_bytes<=8 MiB`、`max_duration_seconds<=60`，并将 QQ
  capability 严格归一为 `unknown|available|unavailable|denied`。只有 profile ready 且
  capability 精确 available，`voice_reply_available` 才为 true；未知/异常均 fail closed。
  `GET/POST /api/v1/qq-control/configuration` 仍沿用真实 loopback/精确同源防护，POST 新增
  严格 boolean `reply_with_voice`；不可用时启用固定 409 `voice_unavailable`，关闭仍允许。
- 生产共享 composition 未由 PK-140 修改。交 PK-000 串行注入同一 facade：
  `voice_health_provider=lambda: app.state.voice_service.health()`（模块缺失/异常返回不可用）及
  一个受信、无发送副作用的 QQ media capability snapshot provider。不得以 AppID/Secret
  存在推断 available，也不得用真实消息探测；当前虽已有 PK-210 encoder 适配器候选，但其
  hash-locked 依赖安装和生产 composition 注入尚未完成，因此 readiness 仍按设计保持
  `encoding_unavailable/unknown`，面板不能开启。

### Node 生命周期、媒体上传与失败隔离

- 新增 `src/voice_reply.mjs`。只有普通 `/api/v1/conversation` 已成功发送全部文本后才进入；
  菜单/子菜单、按钮 ACK、状态、确认、错误、非法命令、四个业务模块结果、每日情报、生命
  维持和专注鼓励均零 TTS、零语音上传。sidecar 启动时只把严格 `true` 视为 opt-in，并在
  每次候选回复前读取本机 qq-control 综合 readiness；白名单在 conversation 前以及合成、
  每片上传、合并和最终发送后续边界反复复核。
- 合成固定调用一次 `POST /api/v1/voice/synthesize`，body 只有
  `{"purpose":"qq_reply","text":"..."}`；Idempotency-Key 是当前白名单用户与 msg_id
  的 SHA-256 截断，不含原始标识。只接受 200、精确 `audio/silk`、
  `X-Kei-Audio-Final=true`、固定 profile、16–80 字符 opaque utterance、可信
  Content-Length 1..8 MiB、严格纯十进制 `X-Kei-Audio-Duration-Ms` 1..60000 和合法
  Silk 头；缺失、重复合并值、0、越界、WAV、长度不符或恶意响应均不读取错误正文并保持文本。
- QQ 固定调用单聊 `/upload_prepare`，校验 upload_id、1..32 个连续 part、每片/总长度和
  唯一预签名 URL；只向 HTTPS 443、无 userinfo/hash、host 为 `*.myqcloud.com` 且禁止
  redirect 的 QQ 返回地址 PUT 原始 final Silk。每片成功后固定调用
  `/upload_part_finish`（上传 ID、part index、实际 block size、该片 MD5），再调用 `/files`
  合并；仅接受有界 `file_info` 和 TTL 0..3600，最后发送一次 `msg_type=7`。所有 path、method、
  file_type=3、文件名和 payload 字段均为代码常量；用户、浏览器、manifest 和 Kei 响应不能
  提交 URL/path/command/codec 参数。若 QQ sandbox 返回新的官方域名，须先由 PK-000 冻结
  精确 suffix，不能泛化成任意 HTTPS。
- 新增 `data/voice_reply_delivery_state.json`，只保存 schema 1、最多 1000 个 32 位哈希键及
  `claimed/sent`；不保存音频、文字、完整 OpenID、URL、file_info、Token、上游错误或路径。
  claim 在付费合成前原子持久化；重复事件、并发和重启看到 claimed/sent 均零二次 TTS/上传/
  发送。损坏状态零网络且不覆盖旧字节；最终 sent 保存失败时磁盘仍保留 claimed，保持
  at-most-once。shutdown abort 本机合成 HTTP 并阻止后续 part/合并/发送；已进入 QQ 请求的
  网络不确定窗口不自动重试，文字仍是可靠基线。

### 包、网络/数据副作用与验证

- 候选提升为 `qq_bridge@0.1.8`，manifest 新增可选依赖 `voice`，包 allowlist 增加
  `sidecar/src/voice_reply.mjs`；配置 schema 增加默认 false 的非秘密开关。包仍不含
  `.env`、data、node_modules、音频、文字、凭据、白名单、个人状态、模型、Voice Pack、
  encoder、日志或 vendor。确定性临时候选 `qq_bridge-0.1.8.zip` 为 124163 bytes，
  SHA-256 `c01b03cfc0a479eac4383b75dfaddc5d77117b088c4b0bd40c6b6b1e03249f7e`；manifest
  SHA-256 `1b22b34f1c11b6e465efb07449d669d6f4a1b431e643327474767e46e8eb1d0d`，未发布。
- 新增网络只在四重条件同时满足后发生：白名单、显式本机开关、PK-210 profile ready、
  QQ capability available。顺序为本机 readiness GET→一次本机 synthesize→QQ
  upload_prepare→受控 COS PUT/part_finish→files→一次 media message。未新增端口、进程、
  QQ 凭据/权限字段或自动安装；不会让 Core 读取 QQ Secret，也不会让 Node 读取 Voice Pack、
  repository、PCM/WAV 或模型路径。
- 新增 14 项 Node fake 专项，覆盖默认关闭、成功单次及多分片合成/上传/发送、unknown/profile/
  allowlist fail-closed、格式/头/时长/长度/Silk 校验、恶意预签名目标、并发、跨重启、损坏
  状态、错误脱敏、QQ 发送失败、合成/最终发送窗口 shutdown 和仅普通 conversation 路由；
  配置面板 Python 增至 9 项，
  覆盖原子启停/刷新、unknown 禁用、available 启用、async provider、同源与秘密隔离。
  全部使用 fake voice/QQ/conversation、虚构用户、系统临时状态和 ASGITransport。
- 实际回归：全部 bridge Node 97 项、QQ 配置+可安装包
  22 项、PK-210 voice module/installable、PK-200 conversation consumers、qq-control、
  feature Catalog、dashboard shell 与 official catalog 均通过；全部 MJS/动态面板语法通过。
  未读取或修改真实 `.env`、QQ data/runtime、个人/Voice Pack/模型/vendor；未启动 BAT、
  Gateway、Core、LLM/TTS/ASR/encoder，未连接 QQ/COS/Pi 或发送消息，未运行 npm。

### 本增量八项文档门禁

- [x] TASK_RECORD — 本节记录开关、综合 readiness、固定合成/上传接口、状态、网络与失败模式。
- [x] TASKS_BOARD — 按总控冻结不修改 `TASKS.md`；PK-140 保持“待集成”。
- [x] PUBLIC_README — 共享根 README 由其他任务占用且本轮不改；QQ 专属和包内 README 已更新。
- [x] MODULE_CATALOG — 0.1.8 manifest/release fragment 已更新，公共 Catalog 由 PK-000 串行合并。
- [x] ARCHITECTURE_DOCS — 公共架构冻结；QQ 专属 README 已记录媒体、所有权和 fail-closed 边界。
- [x] LOCAL_README — 不适用：未改变端口、解释器或机器路径，真实本机配置未读取/修改。
- [x] AGENT_RULES — 不适用：长期协作、安全、Git、测试和文档规则未改变。
- [x] VALIDATION — 全部 Node 97/97、QQ 配置+可安装包 22/22、qq-control 8/8、
  PK-210 synthesize/installer/Silk encoder、PK-200 consumer、Catalog/dashboard 回归、全部
  MJS/面板语法、相关 compileall、29 项文档门禁和 `git diff --check` 均通过；所有外部能力
  均为 fake。

PK-140 继续保持“待集成”，交 PK-900 独立验收；当前真实遗留是生产 Silk encoder 的
hash-locked 依赖安装/composition 注入未完成、QQ Bot media capability 尚未由无副作用
provider 明确为 available，以及 PK-000 尚需完成上述 facade 生产注入。任一项未解决时
语音开关不可开启且文本功能不受影响。

## PK-900 语音流与能力声明最小整改（2026-08-10）

- 阻断 A 已在 `src/voice_reply.mjs` 收口：`POST /api/v1/voice/synthesize` 从建立请求、等待
  响应头、按块读取正文到 Silk/长度/时长最终校验共用同一 deadline 和 AbortController。
  不再调用 `arrayBuffer()` 后才限长；实际累计超过 8 MiB 会立即 cancel reader、abort 请求并
  丢弃部分字节。挂流、欺骗 Content-Length、reader error、timeout/shutdown 竞态均清理
  in-flight，零 QQ 上传、零 `msg_type=7`，状态沿用既有 claimed fail-closed 语义。
- 阻断 B 已在 PK-140 配置边界新增非秘密
  `QQBOT_MEDIA_UPLOAD_CAPABILITY=unknown|available|unavailable|denied`，默认 unknown。
  `GET/POST /api/v1/qq-control/configuration` 和动态面板可读写该枚举；面板明确它是管理员
  声明而非自动验证。保存声明零网络、零 voice、零 QQ；降为非 available 会在同一原子写入
  中关闭 `QQBOT_REPLY_WITH_VOICE`。非法枚举拒绝，原子替换失败保留旧字节。
- 提供共享装配 helper：
  `from qq_bridge.configuration import create_qq_media_capability_provider`；准确签名为
  `create_qq_media_capability_provider(configuration_store: QQBridgeConfigurationStore) -> Callable[[], str]`。
  PK-000 应以该 helper 返回值替换生产 composition 中固定 `lambda: "unknown"`，并继续把
  PK-210 health provider 注入同一 facade；Core 无需也不得读取 Secret。
- 候选提升为 `qq_bridge@0.1.9` / `qq_bridge-0.1.9.zip`。两次临时目录构建均为
  `129027` bytes，SHA-256
  `c77d98549d600ad39d890aa332bb6b5cfa31b87aec4fd64021b50e2e9b3e878b`；manifest SHA-256
  `183e584cd762de55b32cdb891d4dda3a42478a1581f841b09930d6a5ff7fee58`。未发布。

### 本轮八项文档门禁

- [x] TASK_RECORD — 本节记录两个阻断、接口、失败语义、包摘要及共享装配请求。
- [x] TASKS_BOARD — 按总控冻结不修改 `TASKS.md`；PK-140 保持“待集成”。
- [x] PUBLIC_README — 公共 README 由 PK-000 串行处理，本轮只更新 QQ 专属 README。
- [x] MODULE_CATALOG — 专属 manifest/release 更新为 0.1.9；公共 Catalog 由 PK-000 串行处理。
- [x] ARCHITECTURE_DOCS — 公共架构冻结，本轮边界已写入 QQ 专属 README 与任务记录。
- [x] LOCAL_README — 不适用；未改变端口、解释器或本机路径，未读取真实配置。
- [x] AGENT_RULES — 不适用；长期工作、安全、测试和 Git 规则未改变。
- [x] VALIDATION — Node 流式专项、配置/安装包、qq-control、全量 bridge、语法、Python
  回归、compileall、文档门禁及 `git diff --check` 的最终结果记录在本节交付尾注。

- 最终验证：全部 bridge Node `101/101`；QQ 安装包+配置 `25/25`；qq-control `8/8`；
  PK-210 voice module/installable/Silk encoder、PK-200 conversation consumers、Catalog、
  dashboard、official catalog 均通过；全部 bridge MJS 与动态面板语法、相关 compileall、
  文档门禁和 `git diff --check` 通过。流与网络测试均使用 fake。

PK-140 保持“待集成”，整改完成后交 PK-900 独立复验；未启动真实 QQ/Core/Voice，未读取
真实 `.env`/data/runtime，未执行 npm、Git 暂存、提交、推送或发布。

## PK-000 共享装配收口（2026-08-10）

- PK-000 已在生产 `InstalledModuleHost` 中向同一 QQ facade 注入只读 voice health provider
  和有限 media capability provider。前者只在配置状态请求时读取当前
  `app.state.voice_service.health()`；缺模块、异常或非字典结果均 fail closed，绝不启动 TTS。
- capability 默认固定为 `unknown`，并只接受 `unknown|available|unavailable|denied`；没有
  根据 AppID/Secret 推断权限，也没有真实发送探测。因而当前真实面板继续禁止开启语音是预期
  安全状态，普通文字回复与全部既有 QQ 功能不受影响。
- PK-020 已补齐独立 hash-locked voice-media 安装层；共享生产 encoder 也已固定注入。
  本地累计回归为配置 9/9、安装包 13/13、语音专项 14/14、全部 Node 97/97、qq-control
  8/8、module host assembly 通过。PK-140 仍为“待集成”，等待 PK-900 独立复验。

## QQ 0.1.9 真实本机面板与安全降级验证（2026-08-10）

- 经用户明确授权，使用 PK-010 正式生命周期把本机候选更新并启用为
  `qq_bridge@0.1.9`；没有直接编辑 runtime/registry，也没有读取或输出真实 `.env`。
  模块状态为 `enabled`，`configuration_ready=true`，sidecar readiness 为
  `ready/ready`，动态入口 `/api/v1/modules/qq_bridge/assets/dashboard/index.js`
  返回 200（15477 bytes）。
- 实际控制台页面已确认动态面板成功挂载，显示“QQ 语音上传能力”下拉框和
  “QQ 回复同时发送语音”开关。下拉框只含
  `unknown|available|unavailable|denied`；当前真实值为 `unknown`，开关默认 false 且
  disabled，页面同时显示管理员声明而非自动探测的安全说明。
- 只读 API 证据：QQ control 为 `running`，Node、依赖和既有本机配置均 ready；
  `qq_media_upload_capability=unknown`、`reply_with_voice=false`、
  `voice_profile_ready=false`、`voice_reply_available=false`。这证明未满足媒体权限和
  本地 Silk/TTS profile 时会保持纯文字，不会把 AppID/Secret 存在误判为可发送语音。
- 本轮没有调用 conversation、synthesize、QQ upload_prepare/files/messages、真实
  TTS/LLM/ASR、Collector 或定时发送接口，没有产生真实 QQ 消息。系统可见 3 个 Node
  进程，但当前权限无法读取命令行以安全分类；没有强杀或替换任何进程，正式 facade
  只报告一个 running sidecar。若后续需要真实权限验收，必须另行授权并先确认
  capability，再使用受控测试账号；不属于本轮。
- PK-140 保持“待集成”，本节只记录候选安装后的真实界面与 fail-closed 证据；不构成
  GitHub 发布或最终完成确认。

## QQ 语音开关真实 readiness 解锁复核（2026-08-10）

- 本机 `qq_bridge@0.1.9` 动态面板资产继续返回 200，正式 facade 状态为 `running`。
  文字回复恢复后未由总控发送任何真实测试消息；用户自行截图确认普通 QQ 文字回复可用。
- `voice@1.0.5` 经 ModuleManager 正式更新并重启 Core 后，QQ 配置只读接口实际返回：
  `qq_media_upload_capability=available`、`voice_profile_ready=true`、
  `voice_reply_available=true`。对应 voice health 的 TTS、Voice Pack、Silk encoder 均为
  available，固定 profile 为 `qq_c2c_voice_v1`/`audio/silk`。
- `reply_with_voice` 仍保持 false；总控没有替用户自动开启真实消息行为，也没有调用
  synthesize、QQ upload_prepare/files/messages 或发送语音。用户需刷新控制台、显式勾选
  “QQ 回复同时发送语音”并保存；运行中的 sidecar 需在配置保存后正常重启才会取得新环境值。
- PK-140 继续保持“待集成”。真实 Bot 媒体权限及最终语音发送仍由用户受控测试后交
  PK-900 复验，本节不构成 GitHub 发布或最终完成确认。

## QQ Gateway READY 健康与 C2C 重投整改（2026-08-10）

- 根因收口：旧实现把“存在 Node 进程/已创建 WebSocket”当成运行健康，Identify 同时
  请求了不属于本轮的额外 intent，且没有 READY、心跳 ACK、Hello/READY 阶段超时和
  可供控制面的脱敏连接状态。`src/gateway_client.mjs` 现只请求官方
  `GROUP_AND_C2C_EVENT (1 << 25)`，状态机固定为
  `connecting/identified_or_ready/reconnect_wait/failed/stopped`；只有 READY 与心跳 ACK
  同时成立才允许 dispatch 并报告连接成功。op7、op9、socket close/error、Hello/READY
  超时和心跳超时均进入单一有上限重连路径，重复 Hello/close/connect 不累计 socket、
  heartbeat、phase 或 reconnect timer。
- OpenAPI 默认地址从旧的 `https://api.sgroup.qq.com` 迁移到官方
  `https://api.bot.qq.com`；旧地址只保留为精确、显式兼容值。Token base、OpenAPI base
  和 Gateway URL 均使用代码内固定 allowlist，拒绝任意 host、userinfo、非 TLS、非固定
  `/websocket` 路径、query/hash 和非标准端口。依据为 QQ 开放平台 2026-07 标注的 API
  调用、C2C 事件、消息概览与富媒体文档；本轮没有联网调用这些接口。
- Node 在固定 data root 原子写入 `gateway_status.json`：严格 schema 只含随机 session
  generation、PID、有限状态、READY/心跳布尔、稳定错误码/close code、重连次数、最近
  READY 与更新时间。它不含 token、URL、OpenID、事件或消息正文。Python adapter 仅在
  自己持有的子进程 PID 匹配、schema/语义完整且快照未过期时消费；损坏、未知字段、恶意
  error code、过期、PID 不匹配和仅由外部 probe 发现的进程均 fail closed。
- `QQControlAdapterFacade.status()` 继续保留兼容 `running`，但其语义明确为
  `process_running`；新增 `gateway_ready/gateway_state` 和有限诊断字段。动态面板分别显示
  Bridge 进程与 QQ Gateway，只有 READY+ACK 显示“QQ Gateway：已连接”；进程存在但没有
  新鲜快照会显示连接状态不可用，不再误报已连接。start 的并发/重复保护继续按进程事实
  工作，不会因尚未 READY 启动第二个实例。
- 正式 adapter 仍只关闭自己持有的实例。Node 收到固定 stdin `shutdown` 后立即停止
  scheduler/voice/Gateway，取消 timer，关闭并 terminate 自己的 WebSocket，销毁控制输入，
  因而 adapter 的有界 wait 可完成；重复 stop 幂等，随后可重新 start。外部旧实例仍返回
  `shutdown_channel_unavailable`，没有新增按 `node.exe`、文件名或 substring 杀进程能力。
  启动阶段任一 scheduler fatal 会清理已创建资源并退出，不再由提前 resume 的 stdin 或
  残留 timer 伪装运行。
- C2C 复合去重身份升级为 `msg_id + msg_seq + message_scene.ext.msg_idx`（以实际存在字段
  为准）；真正重投零二次 conversation/QQ，合法不同序号不会被误杀。白名单仍先于去重与
  任何 Project Kei/QQ 副作用；只接受 `message_type=0|103` 的有界字符串正文，引用内容不
  替换当前正文，其他消息类型保持不处理。普通 conversation 仍先发送文字；既有可选语音
  失败只降级文字，本轮没有改写 PK-210 合成或 QQ 富媒体上传链路。
- 候选提升为 `qq_bridge@0.1.10` / `qq_bridge-0.1.10.zip`。两次系统临时目录构建均为
  `142652` bytes、SHA-256
  `58057cf09203aece182279f52dc8fe54f648372bea10a0f11b6f3c22de95bcf5`；manifest SHA-256
  `be179ef7e223c79764d07de1c2d903df19b5e3d0584971c7348b82a9958d5a08`，未发布。
- 验证全部使用 fake WebSocket/token/gateway/fetch/QQ/conversation/voice、虚构用户与系统
  临时目录：全部 bridge Node 110/110；QQ 可安装包/配置 26/26；qq-control 8/8；模块
  lifecycle/host assembly、dashboard shell、feature catalog、conversation consumers、
  daily briefing module/cache、voice module/installable 均通过；全部 bridge MJS 语法通过。
  相关 compileall、动态面板语法、28 项任务文档门禁与 `git diff --check` 全部通过；
  diff check 仅报告混合工作区既有 LF→CRLF 提示。
  未读取或修改真实 `.env`、QQ data/runtime、openid、聊天、个人状态或 server/runtime，
  未启动 sidecar/Core/BAT，未连接 QQ、Token、Gateway、LLM/TTS/Collector，未发送消息。

### 本轮八项文档门禁

- [x] TASK_RECORD — 本节记录 READY/心跳状态机、官方 endpoint、复合去重、控制面语义、
  生命周期、包摘要、测试与遗留风险。
- [x] TASKS_BOARD — 按总控冻结不修改 `TASKS.md`；PK-140 原状态继续为“待集成”。
- [x] PUBLIC_README — 公共 README 由 PK-000 串行处理；本轮更新 QQ 专属与包内 README。
- [x] MODULE_CATALOG — 专属 manifest/release fragment 提升为 0.1.10；公共 Catalog 由
  PK-000 串行处理。
- [x] ARCHITECTURE_DOCS — `docs/architecture/qq-bridge.md` 已记录 process/Gateway 双层
  健康、状态快照与 C2C 复合去重。
- [x] LOCAL_README — 不适用：未改变端口、解释器或机器路径，且未读取/修改真实本机配置。
- [x] AGENT_RULES — 不适用：长期协作、安全、测试、文档及 Git 规则未改变。
- [x] VALIDATION — Node/Python/语法/compileall/文档门禁、确定性双构建与
  `git diff --check` 在本节完成后复跑；全部外部能力保持 fake。

PK-140 保持“待集成”，交 PK-000 后再由 PK-900 独立复验。生产仍需由 PK-010/020 安装
0.1.10 dependency deployment 并正常重启 sidecar；真实 QQ 联网不属于本实现验收。

## PK-900 启动期 shutdown 竞态整改（0.1.11，2026-08-10）

- 阻断复现成立：0.1.10 的 stdin listener 位于三个 startup await 之后，且 Gateway stop
  只能递增 generation、不能使 pending token/Gateway provider 的调用方 Promise 及时结算；
  默认请求超时 45 秒确实可能超过 adapter owned-process wait 的 10 秒。本轮仅在 PK-140
  专属 Node 生命周期、测试、包与文档内整改，未处理公共 README/Catalog/voice 冲突。
- 新增通用 `settleWithSignal(factory, signal)`：abort 会立即 reject 调用方等待，同时为原
  provider 的晚到 resolve/reject 保留受控 handler，避免 unhandled rejection；真实 fetch 的
  timeout controller 还会消费外部 AbortSignal。因此不是只在 await 之后丢弃晚到值，而是
  startup Promise 本身在远小于 10 秒的窗口内完成结算。
- `index.mjs` 在任何 scheduler/Gateway await 前安装唯一 stdin `shutdown` listener 和三个
  process signal handler。shutdown 首先 abort process-wide lifecycle，再幂等停止 Gateway、
  voice、daily/life/focus scheduler，移除 listener，pause/destroy stdin；任一 startup await
  返回后都会检查 stopped，禁止在中途关闭后继续启动下一个组件。fatal startup 复用同一
  cleanup，再由顶层设置失败退出码。
- daily/life scheduler 各自拥有内部 AbortController，并可绑定 index 的共享 signal。首次
  schedule refresh、预生成/缓存读取/提醒生成及发送等待都通过可取消 settle；stop 会 abort、
  递增 epoch、清 timer/interval 并移除外部 listener。startup refresh 永不返回时，start()
  仍立即结算；晚到 schedule 不会重新规划 timer 或写状态。
- Gateway token 与 URL provider 均接收内部 lifecycle signal 并通过可取消 settle。stop 会
  abort bootstrap、关闭/terminate 自有 CONNECTING/OPEN socket、清 phase/heartbeat/reconnect
  timer并发布一次 stopped；catch 在 stopped/旧 generation 下不再发布 failed 或重连。旧代
  provider resolve/reject 以及 socket open/READY/ACK/C2C 全部零状态复活、零 dispatch。
  重复 stop 保持幂等，外部进程仍没有宽泛 kill 回退。
- 永久 fake 回归新增 7 项：pending token stop、pending Gateway URL 后 late resolve/reject、
  CONNECTING socket stop 与晚到事件、stdin listener startup 顺序/唯一性、真实 token fetch
  AbortSignal、pending daily refresh stop、共享 signal 取消 pending life refresh。测试 deadline
  固定 100ms，显著小于 adapter 10 秒；全部断言零 socket/timer/dispatch/status revival。
- 候选提升为 `qq_bridge@0.1.11` / `qq_bridge-0.1.11.zip`。双系统临时目录构建均为
  `147675` bytes、SHA-256
  `c264e4effeb48c387a7413b712eb44fa425c51ca8b1a376c8e45ee8a2b3ade54`；manifest SHA-256
  `025a46896463719848de81f30421a606f2624d62d551042c82007ad41a57e235`，未发布。
- 定向生命周期/调度/bridge core 44/44、全部 bridge Node 117/117 与全部 MJS/动态面板语法
  已通过。
- QQ installable/config 26/26、qq-control 8/8、九组跨模块 Python 回归、相关
  `compileall`、28 项文档门禁和 `git diff --check` 均已通过；差异检查仅报告混合工作区既有
  LF/CRLF 提示，无 whitespace error。
  全部 provider、WebSocket、QQ、Core、conversation/voice 均为 fake；未读取真实 `.env`、
  data/runtime、消息或个人状态，未启动服务、联网、发送、安装依赖或执行 Git 发布。

### 本轮八项文档门禁

- [x] TASK_RECORD — 本节记录阻断、取消语义、生命周期顺序、永久回归、包摘要和边界。
- [x] TASKS_BOARD — 按要求不修改 `TASKS.md`；PK-140 保持“待集成”。
- [x] PUBLIC_README — 按要求不处理根 README 的旧版本冲突，留 PK-000 串行收口。
- [x] MODULE_CATALOG — 仅更新 PK-140 专属 manifest/release 为 0.1.11；公共 Catalog 留 PK-000。
- [x] ARCHITECTURE_DOCS — QQ 架构补充 startup control channel、共享取消与旧代隔离。
- [x] LOCAL_README — 不适用：端口、解释器和本机路径未改变，真实配置未读取/修改。
- [x] AGENT_RULES — 不适用：协作、安全、验证、文档和 Git 长期规则未改变。
- [x] VALIDATION — 全量 Node/Python/语法/compileall、确定性构建、文档门禁和 diff check
  在本记录后完成；全部外部副作用保持 fake。

PK-140 继续“待集成”，交回 PK-000 并由同一 PK-900 独立复验；不得以本轮 fake 验证代替
生产安装或真实 QQ 验收。

## PK-900 HTTP JSON body shutdown 竞态整改（0.1.12，2026-08-10）

- 0.1.11 的 startup listener 前置、pending provider 快速结算、generation 隔离与 CONNECTING
  socket terminate 已由 PK-900 确认关闭，本轮没有重做。新 P1 根因是 `fetchWithTimeout()` 在
  fetch 返回 Response 后立即清除 deadline/lifecycle listener，而 `readSafeJson()` 随后才无界
  `response.text()`；因此外层虽 settle，底层 response body 仍可能悬挂。
- 受控 HTTP context 现在把同一个内部 AbortController、请求 deadline 与调用方 lifecycle
  signal 保留至 JSON body 完整消费/解析结束。Token、Gateway URL、QQ OpenAPI、conversation、
  业务 API 与 daily/life schedule 都走同一接缝；主消息 handler 也继承进程 lifecycle signal，
  shutdown 后不会再尝试固定错误回复或 interaction action。
- Node/Web Stream 使用 reader 逐块解码并按实际字节累计固定 4 MiB 上限；`Content-Length`
  缺失或虚报较小值不能绕过。超限会在继续读取/分配前 abort request、取消 reader 并丢弃部分
  body；reader failure 同样 abort/cancel，映射为稳定 `response_read_failed`。timeout 与显式
  shutdown 映射为稳定 `request_timeout/request_cancelled`，上游 URL、正文、Token、OpenID、
  Authorization 与异常文本均不进入日志、状态或用户响应。只提供 `text()` 的既有 fake
  Response 仍兼容，生产 Node fetch 优先使用 Web Stream。
- 401 分支现在先完整结束并清理首个有界响应，再执行唯一一次强制 token refresh；不会留下
  未消费的旧响应体。取消 listener、deadline、reader lock 与 cancel 均幂等；late chunk、late
  resolve/reject 已有受控 handler，不产生 unhandled rejection 或状态/发送复活。
- 永久 fake 逆向新增：token 头后 body 永久 pending、Gateway URL/OpenAPI body pending、
  daily/life schedule body pending、reader.read timeout、reader error、无/虚假 Content-Length
  下实际字节超限、late resolve/reject、重复 abort/stop，以及 conversation body shutdown 后
  零 QQ 回复。能力存在时均断言 request signal `aborted=true`、abort event 恰好一次、reader
  cancel 恰好一次，并在 100ms 窗口内结算。
- 候选提升为 `qq_bridge@0.1.12` / `qq_bridge-0.1.12.zip`。两次系统临时目录构建均为
  `153307` bytes、SHA-256
  `1644c806556008217078bf32f85a7b254555cbfd8ce11aeec2d4e7b07b10103f`；manifest SHA-256
  `ebafe938beec261b705feaf99a1b842c1582b07bcbe7ef6bab8cfc59d78c1d36`，未发布。
- 定向 bridge core/scheduler/Gateway 54/54、全部 bridge Node 127/127、QQ configuration/installable
  26/26、qq-control 8/8、九组跨模块 Python、dashboard Node 1/1、相关 compileall 与 16 个
  MJS/动态面板语法检查均通过。当前项目 venv 与本机 Python 均未安装 Ruff；按禁止安装依赖
  的边界未执行联网安装，Ruff 留同一 PK-900 使用其既有隔离工具复验。28 项文档门禁和
  `git diff --check` 均已通过；差异检查仅报告混合工作区既有 LF/CRLF 提示。
- 全部新增测试使用 fake fetch/ReadableStream/QQ/Core、虚构身份和系统临时目录；未读取或修改
  真实 `.env`、QQ data/runtime、个人状态、`server/runtime` 或 vendor，未启动 BAT/Core/
  sidecar/Gateway、未联网、未发送消息，也未执行 Git 写入或发布。

### 本轮八项文档门禁

- [x] TASK_RECORD — 本节记录响应体竞态、完整请求生命周期、流式上限、逆向证据与包摘要。
- [x] TASKS_BOARD — 按总控冻结不修改 `TASKS.md`；PK-140 继续“待集成”。
- [x] PUBLIC_README — 按要求不修改公共 README，留 PK-000 串行收口。
- [x] MODULE_CATALOG — 仅更新 PK-140 专属 manifest/release 为 0.1.12；公共 Catalog 留 PK-000。
- [x] ARCHITECTURE_DOCS — QQ 架构补充跨响应体的 deadline/lifecycle 与实际字节上限。
- [x] LOCAL_README — 不适用：未改变本机路径、端口或解释器，且未读取本机私有配置。
- [x] AGENT_RULES — 不适用：长期协作、安全、测试和 Git 规则未改变。
- [x] VALIDATION — Node/Python/语法/compileall/双构建、28 项文档门禁与 diff check 已通过；
  Ruff 环境缺失如实记录并交独立验收复跑，全部业务副作用保持 fake。

PK-140 保持“待集成”，交回 PK-000 后由同一 PK-900 使用永久逆向和其既有 Ruff 环境复验；
公共 README/Catalog/voice release-set 不在本轮修改范围。

## PK-900 原生流取消优先级与 401 refresh 整改（0.1.13，2026-08-10）

- 0.1.12 的底层 request abort、stream cancel 与 4 MiB 实际字节上限已由 PK-900 确认有效，
  本轮未重写。新增阻断一是原生 `ReadableStream.cancel()` 可使后续 `reader.read()` 结算为
  `{done:true}`，旧实现没有在建 reader、read settle 和返回前重验 signal，导致取消态可能被
  解释为成功 `{}` 或 `invalid_response`；阻断二是 401 catch 仅看 status，取消 body 后仍会
  启动 token refresh。
- 新实现把 request signal 置于 body `done`、空正文、decoder、JSON parse、HTTP status 与返回值
  之上：读取前、reader 建立后、每次 `read()` 结算后、decoder flush、JSON parse 前后和最终
  返回前均检查同一 internal signal。只要已 abort，空 body、半段 JSON、已排队完整 JSON、
  reader error 或 cancel-to-done 都统一优先为 `request_cancelled`；若 deadline 先触发则保持
  `request_timeout`。真正未取消的 200 空响应继续按既有契约返回 `{}`。
- `fetchWithTimeout`、`token()` 与 `request()` 入口在 provider/fetch 前拒绝已取消 signal；取得
  token 后和 refresh 后也再次检查。401 仅当 `readSafeJson()` 已完整、有界、合法消费并抛出
  精确 `http_401`，且 lifecycle 仍 active 时，才允许唯一 refresh 与唯一 retry。取消、timeout、
  reader failure、oversize、invalid JSON 均不 refresh；refresh 期间 abort 不会发起第二次 API。
- 永久回归使用 Node 原生 `Response + ReadableStream` 覆盖：headers→getReader 间取消的空流、
  半段 JSON 与完整 JSON 排队；正常未取消 200 空 body；401 pending body 后 abort；完整合法 401
  唯一 refresh/retry；初始 signal 已 abort 时 token/API fetch=0；refresh body 中 abort 时第二 API=0；
  invalid/read-error/oversize/timeout 401 的 refresh=0。场景断言稳定错误码、request abort event=1、
  stream cancel=1（能力存在）、body lock 释放、零额外网络与零 unhandled rejection。
- 候选提升为 `qq_bridge@0.1.13` / `qq_bridge-0.1.13.zip`。两次系统临时目录构建均为
  `154813` bytes、SHA-256
  `7a131eea277a979af267df0f21066b7a80996a0118e1ed631340d6b4de2dce00`；源 manifest SHA-256
  `10651336969c6335fb5af4870504218ff0572f68b5e6cf9e6c9cf820fc3306c9`，未发布。
- 聚焦 bridge core/scheduler/Gateway 67/67、全部 bridge Node 140/140、QQ configuration/installable
  26/26、qq-control 8/8、九组跨模块 Python、相关 compileall、16 个 MJS/动态面板语法与
  dashboard Node 1/1、28 项文档门禁与 `git diff --check` 已通过；diff 仅报告混合工作区既有
  LF/CRLF 提示。Ruff 继续由 PK-900 使用其报告中已验证可用的隔离环境执行，本任务不安装依赖。
- 所有流、HTTP、QQ、Core 与身份均为纯内存 fake/虚构值，构建使用系统临时目录；未读取或修改
  真实 `.env`、data/runtime、个人状态、`server/runtime`、vendor 或 voice，未启动服务、联网、
  发送、暂存、提交、推送、发布或清理混合工作区。

### 本轮八项文档门禁

- [x] TASK_RECORD — 本节记录原生流取消优先级、401 refresh 门槛、永久逆向与候选摘要。
- [x] TASKS_BOARD — 按冻结不修改 `TASKS.md`，PK-140 继续“待集成”。
- [x] PUBLIC_README — 按要求不修改公共 README，留 PK-000 串行收口。
- [x] MODULE_CATALOG — 仅更新 PK-140 专属 manifest/release 为 0.1.13；公共 Catalog 留 PK-000。
- [x] ARCHITECTURE_DOCS — QQ 架构记录 cancel 高于 done/status 与安全 401 retry 门槛。
- [x] LOCAL_README — 不适用：未变更机器路径、解释器或本机私有配置。
- [x] AGENT_RULES — 不适用：长期协作、安全、测试与 Git 规则未改变。
- [x] VALIDATION — Node/Python/compileall/语法/dashboard/双构建、文档与 diff 已通过；隔离 Ruff
  分工如上。

PK-140 保持“待集成”，交回 PK-000 并由同一 PK-900 聚焦复验；公共发布收口不在本轮范围。

## 正式安装后 Gateway 阶段诊断整改（0.1.14，2026-08-11）

- 运行态证据显示已正式安装并启用的 0.1.13 sidecar 为 `process_running=true`，但
  `gateway_ready=false`、`gateway_state=reconnect_wait`、`last_ready_at=null`，原实现把 token、
  Gateway discovery 与 WebSocket constructor 的非 allowlist 异常统一压成 `connect_failed`，
  无法在不暴露上游细节的前提下定位阶段。本轮只整改 PK-140 专属 Gateway/status/control/dashboard、
  永久 fake、候选包与本记录；未执行真实 QQ 请求。
- `src/gateway_client.mjs` 现在在三个 bootstrap 边界分别包装固定错误：token 的
  `token_request_failed/token_rejected/token_response_invalid`；Gateway discovery 的
  `gateway_request_failed/gateway_rejected/gateway_response_invalid` 及既有
  `gateway_url_missing/gateway_url_invalid/gateway_url_rejected`；WebSocket 的
  `websocket_constructor_failed/websocket_error/websocket_closed`。Hello、READY 继续分别为
  `gateway_hello_timeout/gateway_ready_timeout`。分类只读取有限 `error.code`，绝不拼接异常文本、
  URL、响应正文、Token、AppID/Secret 或用户数据。
- 0.1.13 已通过的请求契约保持不变：同一 lifecycle signal 仍覆盖 token/Gateway provider、fetch、
  有界 body 与 401 refresh；已取消请求在 provider/fetch 前结束，取消/timeout/reader error/oversize/
  invalid JSON 不会错误 refresh 或 retry，refresh 后仍重验 signal。stop 仍先 abort，再清 socket、
  phase/heartbeat/reconnect timer 并递增 generation；每项失败只建立一个有界 reconnect，旧 timer、
  provider 或 socket event 不得复活。
- `module_adapter.py` 与 `control_facade.py` 只接受同一有限错误 allowlist。facade 只返回有限 code、
  固定英文安全提示及现有有界 close/reconnect/ready 时间字段；未知 code 变为 `null`。动态 dashboard
  只把有限 code 映射为固定中文提示。`process_running` 继续只表示 owned sidecar 存活，只有 READY 与
  健康 heartbeat ACK 同时成立才有 `gateway_ready=true`。
- 永久 fake 新增 token 网络/401/invalid body、Gateway 网络/401/invalid body/invalid URL、WebSocket
  constructor/error/close、Hello timeout 与 READY timeout。每个场景断言唯一稳定 code、状态/日志不含
  虚构秘密、URL、路径或 body、只有一个 reconnect timer，stop 后手工触发旧 timer 仍零 provider、
  零 socket、零状态复活。控制 facade 另断言进程运行不等于 Gateway ready，且只返回固定安全提示。
- 候选提升为 `qq_bridge@0.1.14` / `qq_bridge-0.1.14.zip`。两个独立系统临时目录构建字节一致，
  均为 `158283` bytes，SHA-256
  `90767a065e7bbf4d8cf4ae91de1a399a0d9807b02439858010546389d7b57eee`；源 manifest SHA-256
  `fcc956e6bb1a1eb1c84046f33ddc7446ec409114c20c557100bcb455ee99e03f`。ZIP 共 15 项，禁止路径 0，
  未发布。
- 验证：聚焦 core/scheduler/Gateway 68/68、全部 bridge Node 141/141、QQ configuration/installable
  26/26、qq-control 8/8、九组跨模块 Python 脚本、dashboard Node 1/1、15 个 src/tests MJS 加动态
  dashboard `node --check`、相关 Python `compileall` 均通过。首次从 bridge 目录运行 Python unittest
  因未加入 server 导入根得到两个 `ModuleNotFoundError`，未执行产品测试；设置既有 server
  `PYTHONPATH` 后 14/14 与 12/12 均通过。文档门禁与 `git diff --check` 在本记录后复跑。
- 全部外部能力均为内存 fake/虚构值或系统临时目录。未读取、打印或修改真实 `.env`、QQ
  data/runtime、个人状态、`server/runtime`、vendor 或 voice；未启动 BAT/Core/sidecar、未联网、
  发送、安装依赖、暂存、提交、推送、发布或清理混合工作区。

### 本轮八项文档门禁

- [x] TASK_RECORD — 本节记录运行态根因、阶段码、控制面、永久 fake、候选摘要和隔离边界。
- [x] TASKS_BOARD — 按总控冻结不修改 `TASKS.md`；PK-140 继续“待集成”。
- [x] PUBLIC_README — 按范围不修改公共 README，继续留 PK-000 串行收口。
- [x] MODULE_CATALOG — 仅更新 PK-140 专属 manifest/release 为 0.1.14；公共 Catalog 留 PK-000。
- [x] ARCHITECTURE_DOCS — PK-140 专属与包内 README 已记录阶段码、双层健康和 shutdown 边界；
  公共架构文档未越权修改。
- [x] LOCAL_README — 不适用：未改变机器路径、端口、解释器或本机私有配置。
- [x] AGENT_RULES — 不适用：长期协作、安全、验证与 Git 规则未改变。
- [x] VALIDATION — Node/Python/compileall/语法/dashboard/双构建已通过；文档与 diff 在本节后复跑。

PK-140 保持“待集成”，交同一 PK-900 聚焦独立复验；真实 QQ 权限运行态与公共发布收口仍由
PK-000 串行处理。

## READY 后首次心跳时序整改（0.1.15，2026-08-11）

- 经用户明确授权的受控真实 Gateway 探测，两轮均完成 Token、Gateway URL、WebSocket open、
  Hello、Identify 与 READY 各一次且 dispatch=0；旧时序在 Hello 后立即心跳，25 秒内 ACK=0。
  仅把首次心跳延后至 READY 后立即发送时 ACK=1，由此定位为 PK-140 Gateway handshake 时序问题。
  本实现阶段不再联网或读取真实配置，只根据该固定计数证据做最小源码整改。
- `src/gateway_client.mjs` 收到首个 Hello 后仅发送一次 Identify、记录有界 heartbeat interval 并
  启动 READY timeout，不发送心跳也不建立 heartbeat interval。收到首个合法 READY 后清 READY
  timeout、立即发送唯一首次 heartbeat，并从此时才建立周期 timer；该 heartbeat 的 ACK 到达后才
  设置 heartbeat healthy/`gateway_ready=true` 并允许业务 dispatch。
- READY 前或没有 pending heartbeat 的 op11 ACK 明确记录固定 `gateway_heartbeat_ack_unexpected`
  并忽略，不改变 ready/healthy；READY 早于 Hello 同样固定记录并忽略。重复 Hello 不重复 Identify，
  重复 READY 不重复首次 heartbeat 或 interval。首次 ACK 前 dispatch 保持拒绝；后续 heartbeat 未获
  ACK 时仍固定 `heartbeat_timeout` 并进入唯一有界重连。
- stop/generation/socket 身份检查仍位于所有事件入口；shutdown 清 phase/heartbeat/reconnect timer，
  旧 Hello/READY/ACK/dispatch 和手工触发的旧 timer 均不能复活。0.1.13 的请求取消/timeout/body bound/
  401 门槛与 0.1.14 的有限阶段错误码、状态/facade/dashboard 脱敏契约均未改动。
- 永久 fake 明确断言：Hello 后 heartbeat=0；READY 前伪 ACK 后 ready/healthy=false；首个 READY 后
  heartbeat=1；重复 READY 后仍为 1；首次有效 ACK 前零 dispatch，ACK 后才放行；重复 Hello、
  READY timeout、heartbeat timeout、stop 与晚到事件继续失败关闭。
- 候选提升为 `qq_bridge@0.1.15` / `qq_bridge-0.1.15.zip`。两个独立系统临时目录构建逐字节一致，
  均为 `159275` bytes，SHA-256
  `ac169241acdc362cc908db758c75022cd0c7e622baeca9d9b70fc5db4617c976`；源 manifest SHA-256
  `f82dfd37440ee3699e59c3e9d446770eac0edca3da6a5e8230abf23b88fe6692`。ZIP 共 15 项、禁止路径 0，
  未发布。
- 验证：聚焦 core/scheduler/Gateway 68/68、全部 bridge Node 141/141、QQ configuration/installable
  26/26、qq-control 8/8、九组跨模块 Python、dashboard Node 1/1、15 个 src/tests MJS 加动态面板
  `node --check`、相关 Python `compileall` 均通过；文档门禁与 `git diff --check` 在本节后复跑。
- 全部本轮回归只使用 fake/虚构值和系统临时目录。未读取或修改真实 `.env`、QQ data/runtime、
  个人状态、`server/runtime`、vendor 或 voice；未启动 BAT/Core/sidecar，未联网、发送、安装依赖、
  暂存、提交、推送、发布或清理混合工作区。

### 本轮八项文档门禁

- [x] TASK_RECORD — 本节记录真实诊断输入、最小时序整改、永久 fake、候选摘要与隔离边界。
- [x] TASKS_BOARD — 按总控冻结不修改 `TASKS.md`；PK-140 继续“待集成”。
- [x] PUBLIC_README — 按范围不修改公共 README，继续留 PK-000 串行收口。
- [x] MODULE_CATALOG — 仅更新 PK-140 专属 manifest/release 为 0.1.15；公共 Catalog 留 PK-000。
- [x] ARCHITECTURE_DOCS — PK-140 专属与包内 README 已同步 READY 后首次心跳契约；公共架构不改。
- [x] LOCAL_README — 不适用：未改变机器路径、端口、解释器或本机私有配置。
- [x] AGENT_RULES — 不适用：长期协作、安全、验证与 Git 规则未改变。
- [x] VALIDATION — Node/Python/compileall/语法/dashboard/双构建已通过；文档与 diff 在本节后复跑。

PK-140 保持“待集成”，交同一 PK-900 聚焦独立复验；真实 QQ 权限运行态与公共发布收口仍由
PK-000 串行处理。

## Gateway 已接受序号整改（0.1.16，2026-08-11）

- PK-900 在 0.1.15 独立逆向发现：消息入口在分支判断前无条件复制 `payload.s`，导致已明确忽略的
  READY-before-Hello、重复 READY 和有效 ACK 前 dispatch 仍推进 heartbeat `d`。原夹具分别观察到
  后续 heartbeat 确认 `90`、`99`、`77`，存在确认并丢失从未放行业务事件的风险。
- `src/gateway_client.mjs` 现在只在状态机接受事件后调用有限 `acceptSequence()`：Hello 后的首个合法
  READY 可确认其非负安全整数 `s`；仅当 READY 与有效 heartbeat ACK 均成立、实际交给 dispatch 的
  op0 业务事件才可继续推进。合法 ACK 只清 pending heartbeat/建立健康状态，即使非标准携带 `s`
  也不更新事件序号。
- READY-before-Hello、重复 Hello/READY、unexpected ACK、ACK 前 dispatch、op7/op9、非法 JSON、
  不合法或超界 `s` 均不改变 `lastSequence`。保留 0.1.15 的 Hello 后零 heartbeat、READY 后唯一首次
  heartbeat、有效 ACK 后才 ready/dispatch；保留 0.1.13/0.1.14 的取消、401/body bound、阶段码、
  脱敏、有界重连与 stop/generation 隔离。
- 永久 fake 直接检查 heartbeat payload：READY-before-Hello 的 `s=90` 不进入首个 heartbeat；重复
  READY `s=99` 与 ACK 前 dispatch `s=77` 后的下一 heartbeat 仍为合法 READY 序号 `1`；有效 ACK
  即使带 `s=123` 也不推进；真正放行的 dispatch `s=88` 才使再下一 heartbeat 为 `88`。既有重复
  Hello/READY、timeout、stop 和晚到事件断言继续通过。
- 候选提升为 `qq_bridge@0.1.16` / `qq_bridge-0.1.16.zip`。两个独立系统临时目录构建逐字节一致，
  均为 `159784` bytes，SHA-256
  `c2c45555bf01efa673279eab1b99e1799422a57fd8f49600bd663d633826f68a`；源 manifest SHA-256
  `1bc524aa162e3d676d35235c7dbe4a2e17b5f239a8612d8390feb1c59031fd5f`。ZIP 共 15 项、禁止路径 0，
  未发布。
- 验证：聚焦 core/scheduler/Gateway 68/68、全部 bridge Node 141/141、QQ configuration/installable
  26/26、qq-control 8/8、九组跨模块 Python、dashboard Node 1/1、15 个 src/tests MJS 加动态面板
  `node --check`、相关 Python `compileall` 均通过；文档门禁与 `git diff --check` 在本节后复跑。
- 所有本轮事件、序号、身份和上游均为内存 fake/虚构值，构建只写系统临时目录。未读取或修改
  真实 `.env`、QQ data/runtime、个人状态、`server/runtime`、vendor 或 voice；未启动真实服务，
  未联网、发送、安装依赖、暂存、提交、推送、发布或清理混合工作区。

### 本轮八项文档门禁

- [x] TASK_RECORD — 本节记录序号 P1、接受边界、永久 heartbeat payload 证据与候选摘要。
- [x] TASKS_BOARD — 按总控冻结不修改 `TASKS.md`；PK-140 继续“待集成”。
- [x] PUBLIC_README — 按范围不修改公共 README，继续留 PK-000 串行收口。
- [x] MODULE_CATALOG — 仅更新 PK-140 专属 manifest/release 为 0.1.16；公共 Catalog 留 PK-000。
- [x] ARCHITECTURE_DOCS — PK-140 专属与包内 README 已同步已接受序号契约；公共架构不改。
- [x] LOCAL_README — 不适用：未改变机器路径、端口、解释器或本机私有配置。
- [x] AGENT_RULES — 不适用：长期协作、安全、验证与 Git 规则未改变。
- [x] VALIDATION — Node/Python/compileall/语法/dashboard/双构建已通过；文档与 diff 在本节后复跑。

PK-140 保持“待集成”，交同一 PK-900 聚焦独立复验；真实 QQ 权限运行态与公共发布收口仍由
PK-000 串行处理。

## Gateway 健康状态 null 错误码整改（0.1.17，2026-08-11）

- 受控真实运行态显示 0.1.16 已达到 `process_running=true`、`gateway_ready=true`、
  `state=identified_or_ready`，但控制接口仍返回 `gateway_last_error_code=gateway_failed`。根因是状态
  文件 writer 对合法 `errorCode=null` 使用 truthy 判断，错误落入 fallback。
- `createGatewayStatusFile.write()` 现在对三类输入显式分支：`null` 原样保留；非 null 且通过现有有限
  allowlist/安全格式的 code 原样保留；未知、越界或疑似泄漏值继续归一为 `gateway_failed`。没有
  扩展状态字段、错误词汇或控制接口输入面。
- Node 永久回归断言 READY+有效 ACK 后内存 status 的 `gateway_ready=true` 且
  `last_error_code=null`，原子状态文件健康快照同样保存 null；既有恶意
  `authorization_fictional_secret` 仍归一 `gateway_failed`，文件不含原始秘密。Python
  adapter/facade 回归断言健康状态的 `gateway_last_error_code` 与固定 `gateway_message` 均为 null，
  因而动态 UI 不会显示失败提示。
- 0.1.15 的 READY 后首次 heartbeat、0.1.16 的已接受序号，以及 0.1.13/0.1.14 的取消、401/body
  bound、有限阶段码、脱敏、有界重连与 stop/generation 隔离均未改变。
- 候选提升为 `qq_bridge@0.1.17` / `qq_bridge-0.1.17.zip`。两个独立系统临时目录构建逐字节一致，
  均为 `160086` bytes，SHA-256
  `71753a8697aa3f80e9f2f732ab5f0f383fc57335eacaca3a76a9236cd1ecc68b`；源 manifest SHA-256
  `dbcea3234681fa13aaeb30a10c7627577a74844d2cae275bb9e0e6fd9e57cb1c`。ZIP 共 15 项、禁止路径 0，
  未发布。
- 验证：聚焦 core/scheduler/Gateway 68/68、全部 bridge Node 141/141、QQ configuration/installable
  26/26、qq-control 8/8、九组跨模块 Python、dashboard Node 1/1、15 个 src/tests MJS 加动态面板
  `node --check`、相关 Python `compileall` 均通过；文档门禁与 `git diff --check` 在本节后复跑。
- 所有测试状态、凭据与身份均为 fake/虚构值，构建只写系统临时目录。未读取或修改真实 `.env`、
  QQ data/runtime、个人状态、`server/runtime`、vendor 或 voice；未启动真实服务，未联网、发送、
  安装依赖、暂存、提交、推送、发布或清理混合工作区。

### 本轮八项文档门禁

- [x] TASK_RECORD — 本节记录 null 根因、三分支状态契约、Node/Python 回归和候选摘要。
- [x] TASKS_BOARD — 按总控冻结不修改 `TASKS.md`；PK-140 继续“待集成”。
- [x] PUBLIC_README — 按范围不修改公共 README，继续留 PK-000 串行收口。
- [x] MODULE_CATALOG — 仅更新 PK-140 专属 manifest/release 为 0.1.17；公共 Catalog 留 PK-000。
- [x] ARCHITECTURE_DOCS — PK-140 专属与包内 README 已同步健康状态 null 契约；公共架构不改。
- [x] LOCAL_README — 不适用：未改变机器路径、端口、解释器或本机私有配置。
- [x] AGENT_RULES — 不适用：长期协作、安全、验证与 Git 规则未改变。
- [x] VALIDATION — Node/Python/compileall/语法/dashboard/双构建已通过；文档与 diff 在本节后复跑。

PK-140 保持“待集成”，交同一 PK-900 聚焦独立复验；真实 QQ 权限运行态与公共发布收口仍由
PK-000 串行处理。
## PK-000 受控本机 Gateway 入场验证（2026-08-11）

- 经用户逐项授权后，仅执行无凭据 HTTP、QQ Token 认证与 Gateway 认证探测；未主动发送 QQ 消息，未读取、打印或回显 `.env`、Token、OpenID、消息正文或个人状态。
- `qq_bridge@0.1.17` 候选经同一 PK-900 聚焦独立复验通过后，使用正式 ModuleManager update 流程安装；候选为 `160086` bytes，SHA-256 `71753a8697aa3f80e9f2f732ab5f0f383fc57335eacaca3a76a9236cd1ecc68b`。随后 `setup.bat --profile qq` 成功完成锁定的 Node 依赖部署，没有直接修改 runtime/registry。
- 运行态首次启用后再重启 Core，旧 Core 创建的 sidecar 成为无法由新 Core 接管的外部实例，正式 disable 按安全契约返回失败。总控按固定 `0.1.17/src/index.mjs` 精确匹配并确认唯一进程后，只清理该次受控测试创建的孤立进程；没有匹配或终止其他 Node/Core 进程。之后按 `disable -> enable` 正式流程由当前 Core 持有 sidecar。
- 最终真实状态连续三次为 `process_running=true`、`gateway_ready=true`、`gateway_state=identified_or_ready`、`gateway_last_error_code=null`；这证明 Token、Gateway URL、WebSocket、READY 与首个心跳 ACK 已完成。动态面板资源 `/api/v1/modules/qq_bridge/assets/dashboard/index.js` 返回 `200`。
- 本轮没有验证真实消息 dispatch 或语音上传。当前 QQ 配置仍为 `qq_media_upload_capability=available`、`reply_with_voice=true`，但 `voice_profile_ready=false`；模块总表同时显示 `voice@1.0.5` 为 `broken` 且 `/api/v1/voice/*` 未装载。因此现阶段只能确认 QQ Gateway 连通，不能声称 QQ 语音可用，必须先由 PK-210/共享装配恢复 voice 模块并重新做显式、受控的消息验收。
- 临时 `__pk000/module-binding` 诊断路由及为排查 ACL 加入的 manager 重绑定试验已完整撤除；装配专项、`py_compile` 与 `git diff --check` 通过（仅既有换行提示）。未执行 Git 暂存、提交、推送或工作区清理。

## QQ 普通语音上传协议整改（进行中，2026-08-11）

- 用户真实消息已触发 `POST /api/v1/voice/synthesize` 与 GPT-SoVITS 合成，但 QQ 最终只显示文字。公开状态同时确认 Gateway ready、语音开关开启、媒体权限管理员声明为 available、voice profile ready，因此故障边界位于合成后的 QQ 媒体上传。
- 根因是现实现对几 KiB 的普通 Silk 语音强制调用大文件 `upload_prepare`、预签名分片 PUT 与 `upload_part_finish`，且旧实现使用从 0 开始的分片序号；腾讯官方 `@tencent-connect/qqbot-nodejs@1.0.4` 的普通语音路径直接向 `/v2/users/{openid}/files` 提交 `file_type=3`、`srv_send_msg=false` 与 `file_data` base64，再使用返回的 `file_info` 发送 `msg_type=7`。本轮不再把小语音送入分片流程。
- `src/voice_reply.mjs` 已改为固定单次 `/files` 上传；浏览器、用户文本或配置不能提供 path、URL、filename、hash、upload_id 或分片控制字段。仍只接受 PK-210 返回的最终 `audio/silk`、固定 profile、1..60000 ms 与不超过 8 MiB 的有界字节；`file_info` 与 TTL 继续严格校验，失败保持文字优先并按既有幂等标记禁止重复付费合成。
- 永久 fake 回归断言 `/files -> messages` 是唯一 QQ 调用顺序，base64 解码逐字节等于已验证 Silk，上传体只有三个固定字段；无预签名 PUT、无大文件控制字段，非法/越界 `file_info` 在 `msg_type=7` 前关闭。QQ Node 全量 141/141、QQ configuration/installable 26/26、qq-control 8/8 已通过。
- 源码与累计回归通过后才提升为本机候选 `qq_bridge@0.1.18`。两个独立系统临时目录构建逐字节一致：`156820` bytes，SHA-256 `499167d4a106c946b4179e5c0a20a2d9b834b13ff105b9c3aa715a89c39dce26`；源 manifest SHA-256 `85c908e11691bb7ee07e71e71b2b697656d75f8a231b356ee9e392d0d58d1d67`，ZIP 15 项、禁止路径 0。该候选仅供本机正式 update 与真实用户显式验收，尚未上传或发布；不得因 GPT 日志成功而提前宣称 QQ 语音成功。

## QQ 仅显式点击启动整改（0.1.22，2026-08-12）

- 根因有三处：Core lifespan 会调用 `start_enabled_sidecars()`；ModuleManager 的 sidecar
  `enable`、已启用版本切换与 activation coordinator 默认立即启动；根 `start.ps1 --profile
  qq|all` 仍会另开 QQ Node 窗口。因此仅隐藏按钮不能满足“页面和 Core 零自动启动”。
- `QQBridgeSidecarAdapter.start_automatically = False` 现在把 QQ 声明为手动生命周期。
  ModuleManager 对未声明该属性的既有 sidecar 保持历史默认；对 QQ，install/update/enable、
  Core `start_enabled_sidecars()` 与 activation coordinator 均不创建进程。已运行 QQ 在 update
  时仍会受控关闭，但新版本等待下一次用户点击，不自动复活。`enabled` 只表示功能可用。
- `QQControlAdapterFacade.start()` 是唯一生产创建入口：未启用时先完成 readiness enable，再由
  同一 adapter 和当前可信 deployment 显式启动；失败保持可重试，并发/重复请求仍由 facade
  与 adapter 双层锁收敛为一次 `Popen`。停止后状态回到“已启用，等待手动启动”，下一次点击
  才重启。status GET 始终零启动、零写入、零网络。
- 动态面板继续保留现有 QQ 图片。共享 dashboard shell 已有的 `enhanceQQLaunchVisual()` 把图片
  包装为带 `aria-label` 的原生 button，并调用同一个隐藏文字按钮的 `click()`；文字按钮唯一调用
  固定 `POST /api/v1/qq-control/start`。页面加载、展开、配置/日程读取及状态刷新都只有 GET，
  不会触发该动作。未运行提示明确为“已启用，等待手动启动”，运行后分别展示
  `process_running` 与 `gateway_ready`。
- 根 `start.ps1` 删除 `--only qq` Node 入口和 `qq/all` 自动开窗分支；profile 仍可选择 QQ 的
  Core/setup 诊断语义，但只提示去控制台明确点击。历史 `start_qq_bridge.bat` 仅给出本机控制台
  地址并以固定非零码退出，保留统一 pause/退出码外壳，不再调用根启动器或 Node。没有新增
  第二套 start、stop、kill、路径、命令、环境、端口、安装或网络能力。
- 0.1.21 已有的 `file_info/ttl/content` 语音修复、语音 capability/readiness、配置原子保存、
  daily/life/focus 调度、业务菜单、Gateway READY/heartbeat、取消/重连、C2C 去重及文字降级均未
  改写；全量 Node fake 回归 143/143 通过。
- 新增/更新永久 fake 回归覆盖：安装/enable/Core sidecar startup 零 `Popen`；首次 facade start
  一次；失败后八路并发重试仅一次成功和一次进程；已运行重复 start 零新增；disable 后保持
  stopped/ready，下一次显式 start 才创建第二个进程；dashboard 唯一 POST、按钮禁用、头像
  ARIA 与同动作代理；根 profile 和旧 BAT 零 Node 启动。
- 候选提升为 `qq_bridge@0.1.22` / `qq_bridge-0.1.22.zip`，release tag
  `modules-2026.08.12`。两个独立系统临时目录构建逐字节一致，均为 `160616` bytes，SHA-256
  `cf951c8b92510d102b4fc959b2e6a3b7a32458c147fe50e2a6b97c5088a0180d`；源 manifest SHA-256
  `021355e2ca6286e5d42609e709addfe2893fa465dd2f6be74afeca9ecd4fb576`。ZIP 未复制到仓库、未安装、
  未上传或发布。
- 验证：QQ installable 15/15、configuration 12/12、qq-control 8/8、ModuleManager lifecycle、
  module host assembly、dashboard shell、feature catalog 均通过；Windows 安装/启动全套 27 项
  通过（1 项因本机 8000 端口占用按既有条件跳过）；全部 bridge Node 143/143，9 个 bridge MJS
  与动态面板 `node --check`、相关 Python `compileall`、28 项任务文档门禁及
  `git diff --check` 通过。第一次 Windows 全套准确发现旧 BAT pause 外壳断言，修正为“只提示、
  不启动”同时保留统一退出行为后，全套复跑转绿。
- 全部进程、HTTP、Gateway、QQ、配置、状态和身份均为 fake/虚构值或系统临时目录。未读取、
  输出或修改真实 `.env`、QQ data/runtime、个人状态、`server/runtime`、vendor 或 voice；未启动
  BAT/Core/sidecar、未联网、未发送 QQ、未调用 LLM/TTS/Collector、未安装依赖，也未执行 Git
  暂存、提交、推送、发布或工作区清理。混合工作区其他任务修改原样保留。

### 本轮八项文档门禁

- [x] TASK_RECORD — 本节记录自动启动根因、手动生命周期、显式接口、副作用、测试和候选摘要。
- [x] TASKS_BOARD — 按总控冻结不修改 `TASKS.md`；PK-140 继续“待集成”。
- [x] PUBLIC_README — 按范围不修改公共 README，留 PK-000 串行收口。
- [x] MODULE_CATALOG — 仅更新 PK-140 专属 manifest/release；公共 Catalog 留 PK-000 更新 0.1.22。
- [x] ARCHITECTURE_DOCS — QQ 专项架构与 bridge/package README 已同步显式点击生命周期。
- [x] LOCAL_README — 不适用：未改变本机路径、端口、解释器或私有配置。
- [x] AGENT_RULES — 不适用：长期协作、安全、测试与 Git 规则未改变。
- [x] VALIDATION — Node/Python/Windows/语法/compileall/双构建/文档与 diff 检查如上均已执行。

PK-140 保持“待集成”，交 PK-000 后由 PK-900 独立复验；PK-000 仍需在共享串行窗口同步公共
Catalog/README 的 0.1.22 发布信息，本轮不安装真实 runtime、不发布。

## PK-000 本机 0.1.22 手动启动运行态验证（2026-08-12）

- 在 PK-900 源码候选聚焦验收通过后，经用户明确授权执行本机安装。总控从当前源码在两个系统
  临时目录重新构建 `qq_bridge-0.1.22.zip`，两份均为 `160616` bytes，SHA-256 均为
  `cf951c8b92510d102b4fc959b2e6a3b7a32458c147fe50e2a6b97c5088a0180d`；源 manifest
  SHA-256 为 `021355e2ca6286e5d42609e709addfe2893fa465dd2f6be74afeca9ecd4fb576`，与独立验收记录一致。
- 启动中的旧 `qq_bridge@0.1.21` 由旧 Core 自动创建，正式 disable 因已失去可用 shutdown channel
  返回 `sidecar stop failed`。总控仅在命令行精确匹配固定
  `module-dependencies/qq_bridge/0.1.21/src/index.mjs` 且确认唯一 PID 后关闭该旧实例，再通过正式
  ModuleManager `disable -> update` 流程安装 0.1.22；未直接编辑 runtime 或 registry。
- `setup.bat --profile qq` 成功建立与 0.1.22 immutable package/lock 匹配的 Node dependency
  deployment，未创建或覆盖 `.env`、凭据、服务、模型或 Voice Pack。configuration check 随后为
  `ready`。
- 正式 enable 后，运行态为 `installed_version=0.1.22`、`enabled=true`、
  `install_status=enabled`，同时 `process_running=false`、`gateway_ready=false`，固定提示为
  `QQ bridge is enabled and waiting for manual start.`；证明安装、enable 与现有 Core 均未自动创建
  QQ sidecar。
- 使用与控制台按钮相同的唯一 `POST /api/v1/qq-control/start` 连续调用两次：调用前 Project Kei
  QQ Node 数量为 0，调用后为 1，最终 `process_running=true`、`gateway_ready=true`、错误码 null；
  没有创建重复实例。动态模块资源返回 HTTP 200。
- 为把环境交给用户亲自验证，总控最后只关闭本次显式测试创建且精确匹配 0.1.22 固定入口的唯一
  Node PID，未改变模块启用状态。最终仍为 0.1.22/enabled、进程未运行、等待用户从控制台点击头像
  或“启动 QQ Bridge”。Core 保持运行；ASR/GPT-SoVITS 当时未监听，因此语音 readiness 可暂时随
  外部语音服务状态降级，不属于手动启动失败。
- 全程未读取、打印或修改真实 QQ `.env`、AppID/Secret、QQ data、个人状态、模型、Voice Pack、
  `vendor/` 或其他任务内容；未发送真实 QQ 消息，未暂存、提交、推送、发布或清理混合工作区。

PK-140 继续保持“待集成”；本节只记录本机安装和手动启动运行态证据，不提前关闭任务或 PK-900。

## QQ Bridge 显式安全关闭增量（0.1.23，2026-08-12）

- 新增固定 `POST /api/v1/qq-control/stop` 与 legacy 同源接缝；仅接受可信本机
  Origin 和空 body，拒绝 PID、路径、命令等客户端控制输入。
- readiness/facade 新增 `can_stop`，仅当前 adapter 持有的进程可通过既有 stdin
  `shutdown` 通道关闭。外部 probe 检测到的进程返回
  `shutdown_channel_unavailable`，不会强杀或按端口猜测。
- 动态面板新增“关闭 QQ Bridge”，浏览器二次确认后才 POST；顶部配置卡同步提供
  同一能力。重复关闭无副作用，启动、Gateway、语音、定时任务契约未改变。
- 候选 `qq_bridge@0.1.23` 双构建均为 `161683` bytes，SHA-256
  `2a760c6303fa353bcaf8882333b263ad5ca30839b3a07de9aa195cfa48eaaf67`；manifest
  SHA-256 `1535258b9c1307eb50241d1969704aa0d7ba170a0c5957f9f94e67cb73aa30e1`。

## QQ 跨 Core 重启的显式安全关闭（0.1.24，2026-08-12）

- 根因：0.1.23 的关闭通道只存在于当前 Core 持有的 `Popen.stdin`。Core 正常重启后，QQ Node
  仍在运行，但新 Core 只能识别它为外部进程，因此 `can_stop=false`；控制台不能安全显示可用的
  “关闭服务”，也不能用端口或宽泛 `node.exe` 终止代替。
- `gateway_status.json` 新增固定布尔字段 `shutdown_control_ready=true`，并继续只保存随机 32 位
  generation、PID、有限状态与时间；不保存凭据、URL、OpenID 或消息。新 Core 只有同时验证状态新鲜、
  PID 对应当前 dependency deployment 的固定 `src/index.mjs`、generation 合法时才令 `can_stop=true`。
- 关闭请求固定写入现有受控 QQ data root 的 `shutdown_request.json`，严格只有
  `schema_version/generation/requested_at/expires_at` 四个字段，5 秒有效。sidecar 只接受与自身
  generation 一致的常规小文件；过期、重放、额外字段、错误 generation、超限文件和符号链接均拒绝。
  成功请求只走现有幂等 shutdown/AbortController，绝不接受浏览器 PID/path/command，也不按端口或进程名
  杀进程。
- 永久 fake 回归覆盖同一 Core stdin stop、Core 重启后精确 identity+generation stop、错误 PID/入口零写请求、
  过期/重放/符号链接/超限请求零 shutdown。QQ Node 全量 145/145；QQ configuration/installable/qq-control
  Python 37/37；Core module host assembly 通过；相关语法与编译通过。
- 候选提升为 `qq_bridge@0.1.24` / `qq_bridge-0.1.24.zip`。两个独立系统临时目标构建逐字节一致，
  均为 `165310` bytes；SHA-256
  `4bf3b0a0f74eb19d13ab2a864f3f4ab741dfe9e94ed021d52451829a280c7de5`；源 manifest SHA-256
  `2857094e048c7030804c9675bf0e620baeb6f548aae02b2d098e1076eab0359c`。构建只写系统临时目录，未安装、
  上传或发布。
- 当前本机仍运行的 0.1.22 实例不认识该协议，因此不会被伪装成可关闭；必须先正常结束旧实例，再经正式
  ModuleManager 更新与 QQ dependency deployment 安装 0.1.24。此迁移门禁完成后，新版启动的实例才能在
  Core 重启前后持续显示并执行“关闭服务”。
- 未读取、打印或修改真实 `.env`、QQ data/runtime、个人状态、`server/runtime`、模型、Voice Pack 或
  `vendor/`；未联网、发送 QQ、安装依赖、暂存、提交、推送、发布或清理混合工作区。

### 本轮八项文档门禁

- [x] TASK_RECORD — 记录旧实例为何不可关闭、跨重启协议、安全校验、回归与候选摘要。
- [x] TASKS_BOARD — 不修改 `TASKS.md`，PK-140 继续“待集成”。
- [x] PUBLIC_README — 不修改公共 README，留 PK-000 串行收口。
- [x] MODULE_CATALOG — 只更新 PK-140 专属 manifest/release 为 0.1.24，公共 Catalog 留 PK-000。
- [x] ARCHITECTURE_DOCS — QQ 包内 README 已同步跨 Core 重启关闭边界。
- [x] LOCAL_README — 不适用；未改变本机路径、端口、解释器或秘密配置。
- [x] AGENT_RULES — 不适用；协作、安全、验证和 Git 规则未改变。
- [x] VALIDATION — Node/Python/Core 装配/语法/双构建及下述文档、diff 门禁已执行。

PK-140 保持“待集成”，交 PK-900 独立复验；本轮不把当前 0.1.22 实例冒充为 0.1.24，也不提前发布。

## PK-000 本机 0.1.24 安装与无黑框启停验证（2026-08-12）

- 在 PK-900 通过 0.1.24 源码候选后，经正式 ModuleManager 流程把本机模块从 0.1.22 更新至
  0.1.24；依赖部署 allowlist 漏项由 PK-020 最小修复后，正式 setup/configuration check/enable
  全部通过。最终为 `installed_version=0.1.24`、`enabled=true`、配置 ready，且启用不自动启动。
- 实际控制台页面验证：未运行时顶部 QQ 卡固定显示“未启动”且没有伪造关闭按钮；显式点击
  “启动 QQ Bridge”后进程进入 connecting，刷新顶部状态后固定显示“启动”和唯一“关闭服务”按钮；
  动态 QQ 面板同时显示“关闭 QQ Bridge”。点击顶部按钮会先触发二次确认，确认后通过既有安全
  stop 契约关闭，最终只读状态为 `process_running=false/gateway_ready=false/can_stop=false`，回到
  “等待手动启动”。没有按端口、进程名或宽泛 Node kill。
- 动态面板 asset 实际返回 HTTP 200。页面验证没有发送 QQ 消息、没有改配置，也没有读取或打印
  `.env`、凭据或 QQ 数据。最终将 QQ 留为“已启用、未启动”，供用户自行点击头像启动。

## PK-000 发布时规范化重建（2026-08-12）

- 保留上述 PK-900 对 `165310` bytes / `4bf3b0a0...c7de5` 候选包的历史验收事实，不覆盖或弱化。
- 精确 Git 发布范围在提交前由 `git diff --check` 发现并移除了
  `sidecar/src/shutdown_control.mjs` 文件末尾多余空行；业务逻辑、manifest、依赖和包内文件集合未变。
- 从最终提交候选源码在两个独立系统临时目录重新构建，`qq_bridge-0.1.24.zip` 均为 `165308` bytes，
  SHA-256 均为 `52767f2d81f92cf0d474ea5e0f9f7f4f4985caffb687ffa6c759e24114a936a8`；
  Catalog 所用规范 manifest SHA-256 为
  `7c6768a2128ceedb1128969d629d12e55055c3fe54b6cb629d9b8c03835f63ed`。
- 最终 ZIP 仍为 16 项，`.env`、凭据、QQ data/runtime、`server/runtime`、个人状态、模型、Voice Pack、
  `node_modules`、`vendor`、绝对用户路径和私钥头命中均为 0。
