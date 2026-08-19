# PK-150 — 斩妖除魔

- 状态：待集成
- 优先级：P1
- 所属模块：`demon_slayer`
- 依赖任务：PK-001、PK-010、PK-100、PK-200
- 负责路径：`server/features/demon_slayer/**`、斩妖专属测试、本任务文件；PK-011 本地业务批期间 `TASKS.md`、`server/api.py`、Catalog、PK-100 dashboard、`server/core/modules/**`、README 与架构文档全部冻结，由 PK-000 串行装配
- 当前对话：2026-07-30 由 PK-000 重新打开 PK-150 的 PK-011 可安装化增量；本轮只交付自包含 `in_process` 包、可选 conversation Provider 接缝、动态面板、确定性构建器、Release 元数据与临时生命周期回归，完成后保持“待集成”

## 目标

把既有斩妖除魔能力收敛为可按需安装的普通 `in_process` 业务模块，独立管理目标、打卡、积分、奖励，以及基于真实完成事实的 Kei 日/周/月/年复盘；安装包复用同一份 models/repository/service/router 源码，保留个人状态、版本化/legacy 接口和确定性降级，不扩张其他模块或模型基础设施的所有权。

## 不在本任务内

- 不实现或迁移 PK-160 好感度/长期记忆、PK-170 健身、PK-190 日历修炼，也不读写这些模块的状态。
- 不修改 PK-200 的 Provider/Profile、模型切换、对话历史、system prompt 所有权或长期记忆 Provider；需要公共契约变化时先记录需求并交回 PK-000。
- 不迁移 voice/ASR/TTS，不扩展语音意图；既有斩妖语音行为只做兼容回归。
- 不修改 PK-010 的 manifest Schema、ModuleManager、loader、官方 Catalog 或生命周期语义；公共装配需求交回 PK-000。
- 不把历史斩妖状态迁入新 namespace，不在包内携带状态、配置、缓存、模型、LLM 输出、vendor 或执行脚本。
- 不在本轮删除共享 legacy 控制台 DOM；动态入口已独立交付，最终切换由 PK-000/PK-100 串行完成。
- 不新增批量导入、同步、提醒推送、多人账户或新的奖励经济规则。既有 reminder 只保留兼容，不扩张为通知系统。
- 不删除或重定义 legacy `POST /demon/reset`；它是危险兼容入口，本轮不增加版本化 reset、不在控制台暴露，也不得用于自动测试。

## 接口契约

- 当前兼容接口：`GET /demon/status`、`POST /demon/plan`、`DELETE /demon/goals/{goal_id}`、`POST /demon/checkin`、`GET /demon/reminder`、`GET /demon/review/{daily|weekly|monthly|yearly}`、`POST /demon/wish`、`POST /demon/redeem`、`POST /demon/reset`。
- 目标版本化接口：`GET /api/v1/demon-slayer/status`、`GET/POST /api/v1/demon-slayer/goals`、`PATCH/DELETE /api/v1/demon-slayer/goals/{goal_id}`、`POST /api/v1/demon-slayer/checkins`、`GET /api/v1/demon-slayer/reviews/{period}`、`POST /api/v1/demon-slayer/rewards`、`POST /api/v1/demon-slayer/rewards/{reward_id}/redeem`。
- 新旧接口必须委托同一 service/repository，不能维护两套目标、积分、奖励或复盘规则；legacy 请求/响应保持兼容，版本化接口使用明确模型和有限错误文案。
- Kei 复盘只通过 PK-200 的受控 `ConversationService.generate_text()` 类公开能力注入，输入仅包含复盘所需的结构化事实；不直接依赖原始 LLM client/`LLMEngine`，不写普通对话历史。模型不可用、拒绝或超时时保留确定性的本地兜底并明确 `kei_generated=false`。
- 被调用方：既有控制台和 voice 兼容链路可以消费本模块公开 service/API；不得直接访问斩妖状态文件。
- 安装包 manifest 固定 `id=demon_slayer`、`type=in_process`、`entrypoint=backend.register`、版本化 namespace `/api/v1/demon-slayer`、既有 `/demon/*` legacy 前缀、动态入口 `dashboard/index.js`、`data_namespace=demon_slayer`、`local_state`、`requires_restart=true`；强依赖为空，`conversation` 仅为 optional dependency。

## 数据所有权

- `server/systems/data/demon_slayer.json` 是用户个人状态，包含目标、打卡、积分、愿望/奖励和复盘奖励账本。当前工作区已存在该文件的既有修改，独立任务不得读取或打印内容、查看详细 diff、移动、格式化、迁移、重置、覆盖、暂存或提交。
- 所有自动测试必须显式注入系统临时目录下的 `DemonSlayerStore`，并注入 fake conversation；不得调用默认 store、真实/付费模型、真实 voice 或外部网络。
- 模块只拥有斩妖状态；不得合并到 affection、memory、fitness、calendar、focus 或 conversation 状态文件。删除目标继续保留历史打卡和既得积分。
- 持久化失败不得留下截断 JSON 或半发放积分/奖励；同一目标/周期重复打卡、同一复盘奖励重复请求必须保持幂等。
- 安装、启停、升级、回滚和卸载只改变可再生成程序/注册状态。卸载默认保留历史文件并在重装后继续关联；PK-010 的 purge 只允许清理 `server/data/modules/demon_slayer/`，不得越权删除既有 `server/systems/data/demon_slayer.json`。

## 实施清单

- [x] 先审阅 `server/systems/demon_slayer.py`、`server/api.py` 斩妖路由、既有控制台、voice 兼容和三组斩妖测试；保留工作区既有实现修改，不读取真实状态。
- [x] 建立 `models/repository/service/router` 边界或等价清晰分层，让默认 store 路径只在 composition root 注入。
- [x] 装配 `/api/v1/demon-slayer/*`，并让 `/demon/*` 委托同一 service；危险 legacy reset 只保留兼容。
- [x] 保持日/周/月/年、recurring/once、指定日期、稳定目标 ID、选妖、删除保留历史、积分/奖励幂等规则。
- [x] 把 Kei 复盘接到 PK-200 受控生成门面，验证事实约束、失败兜底和不写聊天历史。
- [x] 更新本模块 catalog、README/架构说明和完成文档门禁；共享文件只改斩妖相关 hunk。
- [x] 使用临时 store/fake conversation 运行定向、legacy、API、控制台和消费者回归，再执行 `git diff --check` 与受保护路径状态检查。
- [x] 交付 `backend.register`、manifest、动态 dashboard、确定性 directory/ZIP builder 和官方 Release fragment；包内后端从同一 feature 源文件 allowlist 生成，不复制第二套规则。
- [x] 使用临时 ModuleManager/runtime/registry/data、临时历史状态、fake clock 与 fake generator 覆盖安装启停、升级回滚、卸载重装、purge 隔离、重复路由、原子失败和可选依赖降级。

## 验收标准

- 旧状态 Schema 和旧目标可由同一 repository/service 兼容读取；实现不得靠真实个人文件验证。旧 `/demon/*` 与新 `/api/v1/demon-slayer/*` 对同一临时状态产生一致结果。
- 日/周/月/年目标、recurring/once、指定日期临时目标、稳定 ID、自动/显式妖怪分类和单条删除均保持；删除保留历史打卡、积分和奖励账本。
- 同一目标同一周期重复打卡不重复积分；完成状态修改、复盘奖励和 reward redeem 不出现双发、负余额或半状态。
- 日/周/月/年复盘只统计对应周期已到期事实；当前月/年不惩罚未来日期，完成/未完成、notes、breakdown 和积分数据可复核。
- Kei 文本不能编造完成事项、改变事实、发放积分或修改状态；生成失败时本地规则结果仍完整可用，PK-200 profile/历史保持不变。
- 真实个人状态路径未被读取、修改或纳入任务差异；测试全部使用临时 store，敏感模型/上游错误不进入响应、日志或状态。
- 控制台每个当前目标卡片直接展示 service/API 返回的启用起点、启用天数、当前连续完成数、历史最长连续完成数和正确 cadence 单位；空值、零值与一次性目标均有确定性文案，不出现 `undefined`/`NaN`，浏览器不复制统计算法。
- 既有控制台与 voice 兼容回归通过；PK-160、PK-170、PK-190、PK-200 的文件与数据所有权没有扩张。
- 同一输入两次构建得到完全相同的 ZIP 字节与摘要；包内只有 manifest、允许的 backend 源码与 dashboard 入口，不含状态、`.env`、缓存、模型、vendor、测试或执行脚本。
- 没有 conversation 时 goals/check-ins/points/rewards 和确定性复盘正常；显式注入 fake generator 时只走既有受控 token 裁决，不写普通 conversation history。
- 安装后默认停用；启用并重启后新旧 API 与动态入口可发现，停用/卸载后新进程不装配。卸载、错误 purge 确认和正确 purge 都不删除临时注入的历史斩妖文件。

## 工作区入场记录

- 依赖确认：PK-001、PK-200 在任务总板和各自任务文件中均为“已完成”，PK-150 可以进入独立功能开发。
- 入场时工作区为混合状态；`server/systems/demon_slayer.py` 和受保护的 `server/systems/data/demon_slayer.json` 已有既存修改，另有 conversation、voice、calendar、focus、来源批次及其他用户修改。独立任务必须逐 hunk 保留，不得整理或覆盖。
- 允许实现路径以本文件“负责路径”为准。`server/services/voice_pipeline.py`、PK-200 实现、PK-160/170/190 路径和其他模块状态默认只读；跨模块公共契约需求必须停止并交回 PK-000。
- 本轮只把 PK-150 登记为“进行中”；PK-900 保持上一批“已完成”，不登记新批次。

## 实施记录（2026-07-22）

- 新增 `server/features/demon_slayer/models.py`、`repository.py`、`service.py`、`router.py` 与公开 `__init__.py`。`server/systems/demon_slayer.py` 改为兼容门面；主应用显式注入既有默认路径、PK-200 `TextGenerator` provider 和 legacy 可选音频函数。
- 版本化接口实际落地：`GET /status`、`GET/POST /goals`、`PATCH/DELETE /goals/{goal_id}`、`POST /checkins`、`GET /reviews/{period}`、`POST /rewards`、`POST /rewards/{reward_id}/redeem`，统一前缀 `/api/v1/demon-slayer`。全部既有 `/demon/*` 路由由同一 router/service 提供；仅 legacy 保留危险 reset。
- 目标编辑保持稳定 ID；删除与重复删除为软停用，`reset_existing` 兼容字段也改为软停用旧目标后登记新目标，不清空 check-in。新 check-in 固化 cadence、周期键、标题和妖怪快照，编辑后旧完成事实仍可复盘。旧目标缺失 `repeat_mode` 时按 `recurring` 读取。
- 日/周/月/年分别对应小妖/大妖/大大妖/妖王；周期和妖怪支持自动或显式选择，`once` 只在指定日期所属周期生效。控制台保留原面板并增加编辑/取消编辑、周期自动判断，目标与复盘操作改用版本化 API；没有新增 localStorage/sessionStorage 业务状态。
- 同一目标同一周期的相同打卡只返回一次正积分，重复请求返回 `duplicate=true/points_awarded=0`；未来、停用和周期外目标拒绝打卡。撤销完成若积分已经花掉会拒绝，余额不会变负。奖励兑换用可选 `request_id` 幂等；无 request ID 的 legacy 重试按同一奖励幂等。
- repository 对损坏 JSON/错误结构显式失败，不再回空覆盖；写入使用同路径锁、唯一临时文件、`flush/fsync` 与 `os.replace`，替换失败清理临时文件并保留旧字节。没有移动或自动迁移真实 `server/systems/data/demon_slayer.json`。
- 复盘 facts 只来自 repository 中的目标、check-in、notes、breakdown、积分和幂等奖励账本，并截止本机今日。PK-200 只返回受限 `praise/criticize/mixed` 裁决，最终文字由事实确定性组装；失败、超时、无效或与全成/全败冲突的裁决回退本地规则且 `kei_generated=false`。`generate_text()` 不写普通聊天 history。
- 数据副作用：正常写操作只原子更新斩妖状态；删除不删历史，复盘仅在已闭合完整周期首次全清时写入 bonus，重复复盘不重复发放。复盘模型调用不写 conversation、好感度、记忆、健身、专注、日历、语音、QQ、情报或模型配置状态。
- 遗留风险：默认个人状态仍是既有单文件、单用户模型，未提供多人/同步/批量导入；legacy `POST /demon/reset` 仍可清空斩妖状态，只因兼容保留且控制台不暴露；正式集成前仍需 PK-000/PK-900 对混合工作区整体路由与发布边界复核。

## 验证记录（2026-07-22）

- 所有斩妖写入/损坏/并发/API 测试均使用 `TemporaryDirectory`、虚构目标与 fake `TextGenerator`；未调用真实 LLM、TTS、QQ、网络或默认 store。
- 基线实现检查时七项重点测试均通过；实现后新增 `test_demon_slayer_module.py` 覆盖新旧 API 同 service、旧 Schema、目标编辑、软删除、重复打卡/兑换、损坏文件、原子替换失败和并发重复请求。
- 最终重点测试全部通过：`test_demon_slayer.py`、`test_demon_slayer_hierarchy.py`、`test_demon_slayer_module.py`、`test_demon_review_kei.py`、`test_voice_demon_intents.py`、`test_conversation_consumers.py`、`test_feature_catalog.py`、`test_dashboard_shell.py`。导入主 API 的两项测试仅出现已知 focus runtime 目录 `PermissionError` 装载跳过提示，不影响通过，也未触碰 focus 数据。
- `server/.venv-asr/Scripts/python.exe -m compileall -q features/demon_slayer systems/demon_slayer.py api.py` 及本任务相关测试文件通过；从 `dashboard.html` 提取 module script 后执行 `node --input-type=module --check -` 通过。
- `server/.venv-asr/Scripts/python.exe scripts/check_task_docs.py` 通过，输出 `task documentation gate passed: 20 gated task(s)`。
- `git diff --check` 退出码 0；仅报告混合工作区已有文件的 LF→CRLF 提示，无空白错误。受保护路径状态仍显示入场前已有的 `M server/systems/data/demon_slayer.json`；本任务未读取、diff、写入、reset、暂存或清理该文件。

## 常驻目标统计增量（2026-07-24）

- 版本化契约保持原路径和原请求不变：`GET /api/v1/demon-slayer/status?date=YYYY-MM-DD`、`GET/POST /api/v1/demon-slayer/goals`、`POST /api/v1/demon-slayer/checkins`、`GET /api/v1/demon-slayer/reviews/{period}`。`POST /goals` 继续接受 `title`、`cadence=daily|weekly|monthly|yearly`、`category=auto`、`repeat_mode=recurring|once` 与可空 `target_date`；legacy `/demon/*` 继续委托同一个 service。
- `status` 继续稳定返回 `daily_goals`、`weekly_goals`、`monthly_goals`、`yearly_goals`，且每个返回目标在既有字段上非破坏性增加以下冻结字段：
  - `active_since: string|null`：常驻目标截至事实日所属的最新连续启用区间起始日，格式 `YYYY-MM-DD`；创建日或最近重新启用日计入。旧目标没有任何可信时间证据时为 `null`；临时 `once` 目标固定为 `null`。
  - `active_days: integer|null`：常驻目标从已知 `active_since` 到事实日的自然日数量，首日为 `1`；停用后重新启用会从新启用日重新计数。未知历史起点和 `once` 均固定为 `null`，不是执行天数。
  - `current_streak: integer`：当前连续启用区间内，按目标 cadence 连续完成的周期数。查询日所在自然周期已完成时计入；尚未结束且未完成/`done=false` 时不提前中断上一段，只有更早已闭合的有效周期缺少成功打卡才重置。重新启用开启新的 current streak 区间。
  - `longest_streak: integer`：截至查询日，在全部合法连续启用区间内曾达到的最长连续完成周期数；停用区间、创建前周期、未来打卡和非法历史不进入计算，重新启用不清除历史最长值。
  - `streak_unit: day|week|month|year`：依次对应 daily、周一开始的 weekly、自然 monthly、自然 yearly。
  - `completed: boolean`：保持既有语义，表示查询日所属目标周期是否已有成功 check-in。
- streak 只由 `DemonSlayerService` 的自然周期/启停纯规则计算。每个周期最多形成一个结果，乱序记录按周期归位，重复记录不重复增加；同周期最新合法 `done=false` 视为未完成。旧 cadence 快照不会被改写或伪装成当前 cadence 的连续记录，仍保留给既有历史复盘。停用区间会切开连续段；历史段中在停用前尚未自然闭合的末周期若未完成，不作为失败周期。
- 旧目标缺少 `repeat_mode` 时继续按 `recurring`；缺少目标级 `created_at` 时，只读地使用可解释的全局创建日、最早合法打卡日或明确重新启用日。若三类证据都不存在，`active_since/active_days` 稳定返回 `null` 且 streak 为 `0`，不使用查询日、进程缓存、ID 哈希或磁盘迁移虚构历史。损坏生命周期容器、缺失/非法区间起点、倒置区间和非法显式生命周期时间明确失败关闭；普通 status 零写入。
- `test_demon_slayer_statistics.py` 全部使用 `TemporaryDirectory`、临时 `DemonSlayerStore` 与 fake clock，覆盖四类常驻目标和分组、创建首日、daily 三连/断档、weekly/monthly/yearly 未闭合与闭合断档、`done=false`、重复与乱序、未来记录/未来查询、once、停用/重新启用、创建前查询、无锚点旧目标的跨查询稳定/零写、只读重新启用证据、损坏生命周期、新旧 HTTP 同值，以及 `0001-01-01` 至 `9999-12-31` 极端跨度。既有损坏 JSON、原子替换失败、积分/奖励/复盘与并发幂等继续由原 PK-150 测试覆盖。
- 数据与边界：未新增状态字段或迁移任务，不读取、diff、覆盖或重置真实 `server/systems/data/demon_slayer.json`；未修改 `server/qq_bridge/**`、PK-140、PK-900、积分、奖励、复盘、目标 ID、软删除、check-in 或 LLM 契约。PK-140 可直接读取 `status` 四个 cadence 分组中上述六个字段，不需复制时间或连续规则。
- 增量遗留风险：当前仍是单用户 JSON store；对完全无时间证据的旧目标无法可靠恢复真实历史启用日，因此 API 明确返回未知值而不猜测，后续若需要精确补史必须由 PK-000 另行冻结显式迁移/用户确认契约。正式 QQ 展示与平台渲染不属于 PK-150，本次不做真实 sidecar/API 端到端。
- 增量验证：`test_demon_slayer.py`、`test_demon_slayer_hierarchy.py`、`test_demon_slayer_module.py`、新增 `test_demon_slayer_statistics.py`、`test_demon_review_kei.py`、`test_voice_demon_intents.py`、`test_conversation_consumers.py`、`test_feature_catalog.py`、`test_dashboard_shell.py` 均退出 0；两项主 API 导入型测试只出现既有 focus runtime `PermissionError` 隔离提示并继续通过。相关 Python `compileall`、dashboard module script 的 `node --input-type=module --check -`、23 项任务文档门禁和 `git diff --check` 均退出 0；后者仅报告混合工作区既有 LF→CRLF 提示。全部斩妖写入使用系统临时目录/fake clock，未调用真实 LLM、TTS、QQ、网络或默认 store。

## 常驻统计稳定性收口（2026-07-26）

- 根因：此前 `_goal_created_on()` 在目标级/全局创建日和历史 check-in 均不存在时返回本次 `as_of`，把查询参数错误地当成持久化事实；同一旧目标分别查询不同日期会产生不同 `active_since`，且没有任何数据证据支持其中任一日期。最终兼容语义复用已冻结的 nullable 响应类型：无可信时间证据的 recurring 目标返回 `active_since=null`、`active_days=null`、`current_streak=0`、`longest_streak=0`，`streak_unit` 与 `completed` 保持 cadence/查询周期语义。该结果跨重复查询和进程重启稳定，不写盘、不缓存、不用目标 ID 推导日期；如果未来要求恢复精确历史，只能由 PK-000 另行冻结显式迁移或用户确认契约。
- 可信锚点优先级保持兼容且只读：目标自身 `created_at` 是权威起点；缺失时可使用不晚于事实日的全局 `state.created_at`、该目标不落在停用区间内的最早合法 check-in，或明确闭区间的重新启用日。查询日晚于本机今日时，`completed` 不接受未来记录，派生统计以本机今日为事实截止日；查询日期和四个 cadence 分组本身不变。
- 生命周期采用 `[start, end)` 停用区间：`start` 当日已停用，`end` 当日重新启用；创建/重新启用日计为 `active_days=1`。删除日进入停用区间，重新启用切开 `current_streak`，合法历史段仍参与 `longest_streak`。生命周期容器非列表、条目非对象、缺失/非法起点、非法显式结束时间、结束早于起点，以及非法显式创建/删除时间都失败关闭；status 在这些失败路径同样不保存或修复状态。
- streak 复杂度从“按创建日至查询日枚举每个自然周期”改为“按实际 check-in 归并结果、按启停段分组并检查相邻完成周期”。运行量只随持久化生命周期/check-in 数量增长，不随空白日期跨度增长；daily/weekly/monthly/yearly 的前后周期和边界计算对 `0001-01-01`、`9999-12-31` 做了溢出保护。
- 永久回归补充无锚点旧目标跨日期重复查询与写路径哨兵、重新启用证据、四 cadence 未闭合/闭合断档、未来查询、极端跨度、倒置/缺起点/非法时间生命周期，以及 versioned/legacy status 全响应同值。所有构造数据仍位于 `TemporaryDirectory`，通过临时 `DemonSlayerStore` 和 fake clock 注入。
- 实际验证：九项累计 Python 测试（`test_demon_slayer.py`、`test_demon_slayer_hierarchy.py`、`test_demon_slayer_module.py`、`test_demon_slayer_statistics.py`、`test_demon_review_kei.py`、`test_voice_demon_intents.py`、`test_conversation_consumers.py`、`test_feature_catalog.py`、`test_dashboard_shell.py`）均退出 0；两项导入主 API 的测试仅打印既有 focus runtime `PermissionError` 隔离提示。`compileall -q features/demon_slayer systems/demon_slayer.py api.py tests/test_demon_slayer_statistics.py` 使用定向系统临时 `PYTHONPYCACHEPREFIX` 后退出 0，dashboard 内联 module 经标准输入执行 `node --input-type=module --check -` 退出 0，任务文档门禁通过 23 项；`git diff --check` 退出 0，仅报告混合工作区已有 LF→CRLF 提示。
- 解释器环境说明：当前工作区没有 PK-020 目标根 `.venv`，仓库 `scripts/python.ps1` 因策略需用 `-ExecutionPolicy Bypass`，随后选择到缺少 FastAPI 的 PATH Anaconda，首次统计测试在导入前退出 1；为不修改 PK-020/环境，本轮 Python 功能测试与 compileall 使用现存 `server/.venv-asr`，文档门禁仍通过仓库脚本执行。该环境缺口不属于 PK-150 源码。
- 真实数据零访问证据：入场和验证后 `git status --short` 的受保护项始终只是预存的 `M server/systems/data/demon_slayer.json` 与 `M server/systems/data/focus_timer.json`；本轮命令没有读取、diff、打印、迁移、覆盖、reset 或暂存二者。斩妖测试源码检索确认所有 store 写入均显式指向 `TemporaryDirectory`；未调用真实 LLM、TTS、QQ、网络、模型配置或默认 store。
- 混合工作区排除项：未修改 `server/qq_bridge/**`、PK-140、PK-900、Draft PR #3、PK-020/PK-120 已发布实现、`vendor/`、两份受保护 JSON、`.env`、个人业务缓存或模型文件；未执行暂存、提交、推送、工作区清理。2026-07-26 经总控验收后，PK-150 已标记“已完成”；本次验收不修改或启动 PK-900。

## 控制台常驻统计展示整改（2026-07-28）

- 实机问题根因不是后端字段或 router 装配缺失：`DemonSlayerService.get_status()` 已为 `/api/v1/demon-slayer/status` 与 legacy `/demon/status` 的同一 handler 返回 `active_since`、`active_days`、`current_streak`、`longest_streak`、`streak_unit` 和 `completed`；缺口是 `dashboard.html` 的 `renderDemon()` 只渲染层级、妖怪、周期、积分和打卡日期，未消费五个常驻统计字段。
- 控制台目标卡片新增第二行纯展示事实：`启用起点 <日期|未知> · 已启用 <N 天|未知> · 当前连续 <N 天|周|月|年> · 历史最长 <N 天|周|月|年>`。`streak_unit` 只负责映射显示单位，不在浏览器推导 cadence；未知单位保守显示“周期”。空值不会进入数值运算，合法零值明确显示 `0`；临时 `once` 显示“临时目标不累计启用天数”，并继续展示 API 给出的零 streak。
- 软删除/停用目标继续遵守既有 status 语义：不出现在当前目标列表，不在前端伪造当前启用统计；历史 check-in、积分、奖励和复盘依据仍由 repository/service 保留。本轮没有增加 inactive 查询、目标恢复或第二套业务规则。
- 新增 `test_demon_slayer_dashboard.py`：使用 `TemporaryDirectory`、临时 `DemonSlayerStore` 和 fake clock 复核 status 字段且读取零写；再以 fake API 目标覆盖 daily/weekly/monthly/yearly、`once`、空值和零值，通过 Node 执行实际 `renderDemon()`，断言目标卡片出现正确中文单位、没有 `undefined`/`NaN`，渲染前后临时状态字节不变。测试不启动浏览器、API、LLM、TTS、QQ 或网络。
- 共享文件范围仅为 `dashboard.html` 中现有 `renderDemon` 相邻 hunk和 README 的斩妖说明/测试命令；保留同文件 PK-133 今日论文、PK-140/PK-213 及其他任务修改。后端统计、router、catalog、积分、奖励、复盘、check-in 与数据格式均未改变。
- 实际验证：`test_demon_slayer.py`、`test_demon_slayer_hierarchy.py`、`test_demon_slayer_module.py`、`test_demon_slayer_statistics.py`、新增 `test_demon_slayer_dashboard.py`、`test_demon_review_kei.py`、`test_voice_demon_intents.py`、`test_conversation_consumers.py`、`test_feature_catalog.py`、`test_dashboard_shell.py` 均退出 0；两项主 API 导入测试只打印既有 focus runtime `PermissionError` 隔离提示。`compileall -q features/demon_slayer tests/test_demon_slayer_statistics.py tests/test_demon_slayer_dashboard.py` 使用系统临时 `PYTHONPYCACHEPREFIX` 后退出 0；去除 import 行的 dashboard inline module 经 `new Function(...)` 编译退出 0；任务文档门禁通过 25 项，`git diff --check` 退出 0且仅报告混合工作区既有 LF→CRLF 提示。
- 本轮建议状态为“待集成”，交回 PK-000 安排新的 PK-900/总板同步；按照总控串行要求，本对话不直接修改 `TASKS.md`，也不自行标记“已完成”。

## QQ 完成反馈联动增量（2026-07-28）

- 继续使用 `POST /api/v1/demon-slayer/checkins` 与 legacy `/demon/checkin` 的同一 service。请求非破坏性增加 `with_encouragement: boolean=false`；QQ“完成”固定提交 `true`，“未完成”固定提交 `false`，网页控制台和旧调用方默认零模型。没有新增 QQ 专用 endpoint、repository、状态或连续算法。
- check-in 响应在原字段上增加 `repeat_mode`、`active_since`、`active_days`、`current_streak`、`longest_streak`、`streak_unit`、`encouragement`、`kei_generated`。统计在持久化锁内由 `_goal_statistics()` 针对提交后的同一状态计算，因此积分、重复、启停、once 和 cadence 单位与 status 完全同源；重复请求不写状态、不发积分且不再次调用生成器。
- 只有 `done=true`、非重复且显式要求鼓励时，service 才通过 PK-200 `TextGenerator.generate_text()` 请求一个 `warm|strict|playful` 语气 token。模型看见的只有目标 ID、日期、完成、启用/连续、积分等结构化事实，不返回最终正文；最终 Kei 文案由 service 根据事实确定性组装，不能虚构目标或经历。Provider 缺失、异常、`generated=false` 或无效 token 时返回本地鼓励并保持 `kei_generated=false`；打卡已经原子提交，不因生成失败回滚或重复。
- 新增 `test_demon_checkin_feedback.py`，全部使用 `TemporaryDirectory`、临时 `DemonSlayerStore`、fake clock 和 fake `TextGenerator`，覆盖 daily 三连、weekly 单位、once 空值/零值、versioned/legacy 字段、显式/默认生成开关、失败降级、重复零写与零额外生成。未读取默认 store、真实模型或网络。
- 数据边界未变：只在明确 check-in 时原子写既有斩妖状态；受控鼓励不写 conversation history、QQ 状态或其他个人系统。部署 Python 变更需重启 API；QQ 展示变更需重启 sidecar。
- 最终验证：11 组 Python 文件（累计 demon、统计、dashboard、新 feedback、Kei review、voice、conversation、catalog 与 shell）全部退出 0；business-menu 21/21、全量 bridge 78/78、13 个 bridge MJS `node --check` 通过；`compileall -q features/demon_slayer tests/test_demon_checkin_feedback.py` 与 dashboard inline module 标准输入语法检查通过。首次尝试的 dashboard `node -e` 命令仅因 PowerShell 引号截断退出 1，随后等价标准输入检查通过。任务文档门禁输出 `25 gated task(s)`，`git diff --check` 退出 0，仅有混合工作区已有 LF→CRLF 提示。
- 隔离证据：最终 status 中真实 `server/systems/data/demon_slayer.json` 与 `focus_timer.json` 仍只是入场前的 `M`；本轮没有读取、diff、打印、迁移、reset、覆盖或暂存这些文件，也未探测 `.env`、sidecar runtime、模型或缓存。未启动 API、QQ sidecar、Gateway、LLM、TTS、Collector 或外部网络。PK-133、PK-213、focus 鼓励既有实现、PK-900、`vendor/` 和其他混合差异均保留，未整理或覆盖。

## QQ 常驻目标添加联动增量（2026-07-28）

- PK-150 公共契约没有变化：QQ 只新增消费既有 `POST /api/v1/demon-slayer/goals`，固定提交 `title`、明确 `cadence=daily|weekly|monthly|yearly`、`category=auto`、`repeat_mode=recurring`、`target_date=null`。创建、妖怪分类、稳定目标 ID、积分和后续周期归属仍全部由同一个 `DemonSlayerService` 决定；没有新增 QQ 专用 endpoint、repository 或业务规则。
- 用户说“添加斩妖任务”或不带标题的“添加日/周/月/年任务”时只展示四个 cadence 按钮，零 PK-150 写入；点击周期只显示严格格式。发送 `添加日任务 目标名称` 等严格单消息后，标题只进入 Node 进程内最多 10 分钟的用户绑定单次待确认缓存，按钮 action 只携带不透明 ID。只有同一用户点击“确认添加”才执行一次固定 POST；取消、过期、跨用户、重复确认和非法格式均零写入、零 conversation。
- QQ 本轮只开放 recurring 常驻目标创建；不开放 once/指定日期、自动 cadence、目标编辑/删除、奖励兑换、reset 或其他复盘。若要创建临时目标或调整已有目标，继续使用 Project Kei 控制台。原 status/check-in/鼓励/复盘、legacy 接缝和个人状态格式不变。
- 永久回归新增五类业务菜单场景：十种精确“任务/目标”口令弹出周期按钮且零 API、四个 cadence 按钮只给格式、含“每日情报”的合法标题仍进入确认、确认恰好一次固定 payload、取消/跨用户/过期/重复/非法输入零写入。累计 business-menu 26/26、全部 bridge 83/83、13 个 MJS 语法通过；12 组 demon/consumer/catalog/dashboard/qq-control Python 文件与相关 compileall 通过。
- 隔离证据：所有 QQ、用户、API、时钟和业务响应均为 fake；Python 业务回归继续使用临时 store/fake provider。未读取、diff、打印、迁移、reset、覆盖或暂存真实 `demon_slayer.json`、`focus_timer.json`，未探测 `.env` 或 sidecar runtime，未启动 API、QQ、Gateway、LLM、TTS、Collector 或外部网络。PK-133、PK-213、focus、PK-900、`vendor/` 和其他混合差异均保留。
- 本增量建议 PK-150 与 PK-140 继续保持“待集成”，交回 PK-000 安排新的 PK-900；按共享总板串行要求不直接修改 `TASKS.md`，也不自行标记“已完成”。

## PK-011 可安装化增量（2026-07-30）

- 新增正式包源 `package_source/manifest.json` 和 `package_source/dashboard/index.js`。
  manifest 固定 `demon_slayer@1.0.0`、`in_process`、`backend.register`、
  `/api/v1/demon-slayer`、完整 `/demon/*` 兼容前缀、`local_state` 和
  `requires_restart=true`；没有强依赖，`conversation` 只列为可选增强。安装器在
  conversation 未安装时仍允许启用。
- 新增 `module.py`。注册入口只接收 PK-010 已冻结的 FastAPI `app`，从
  `app.state.demon_slayer_state_path`、`demon_slayer_text_generator_provider`、
  fake clock/timestamp 和可选 legacy audio seam 取得显式组合依赖。没有 Provider
  时注入空 provider，目标、打卡、积分、奖励、确定性鼓励和本地复盘不受影响。
  service 的 generator 类型改为本地 Protocol，包运行时不反向导入
  `features.conversation` 或任何其他 feature。
- 默认数据路径不迁移。开发源码继续解析到
  `server/systems/data/demon_slayer.json`；安装到
  `server/runtime/modules/demon_slayer/<version>/backend/` 后只根据包路径定位同一
  server 根下的历史路径。构造 service/router 和普通模块装载不会读取或创建文件；
  自动测试始终覆盖为临时路径。
- 注册前比较所有候选 route 的 path/method/name。相同完整版本化/legacy router
  已由迁移期 composition 装配时，包标记 `preexisting_compatible_routes` 并零重复
  注册；只有部分 path/method 冲突或名称不一致时整体失败，不能留下半套路由。重复
  loader/重复 register 同样不增加路由。
- 新动态面板只操作 `context.root`，只经 `context.request` 调用版本化 namespace，
  不使用 `fetch`、legacy endpoint、localStorage 或业务文件。面板保留日/周/月/年、
  自动/显式妖怪、recurring/once/指定日期、批量新增、编辑、软删除、打卡、四类
  复盘和奖励兑换，并直接渲染 API 的启用日、启用天数、当前/最长连续、单位、
  completed、积分和本地降级标志；零值、空值和 once 有确定性文案。
- 新增 `package_builder.py`，只 allowlist 复制当前 feature 的
  `__init__/models/module/repository/router/service` 与 package_source 的 manifest/
  dashboard。所有文本规范为 UTF-8 LF；ZIP 使用固定时间、stored 压缩和固定 Unix
  文件元数据。同一输入双构建字节完全一致。包中不存在状态、`.env`、registry、
  cache、测试、模型、LLM 输出、vendor、BAT/PowerShell/shell 或安装脚本。
- `release/official-release-fragment.json` 冻结 tag
  `module-demon-slayer-v1.0.0`、asset `demon_slayer-1.0.0.zip`、Core 范围、
  optional conversation、权限、卸载保留数据和重启语义。专属测试在系统临时目录
  调用共享 Catalog builder，核对 ZIP 大小、ZIP/manifest SHA-256 和生成条目；
  本轮不修改共享 Catalog，也不创建或上传 Release。
- 卸载/重装回归使用临时历史路径：卸载只删除 runtime 程序并返回
  `data_preserved=true`，重装继续读取同一临时目标/check-in/积分/奖励记录。
  `purge-data` 的错误确认被拒绝，精确确认也只删除临时
  `data/modules/demon_slayer/` sentinel，历史文件始终保留。

### 专属回归与隔离

- 新增 `test_demon_slayer_installable.py`，全程使用 `TemporaryDirectory`、临时
  ModuleManager/registry/runtime/data、临时 `DemonSlayerStore`、fake clock 和
  fake generator。覆盖确定性 package/Release、安装/启用/停用、升级/回滚、卸载/
  重装、默认历史路径解析、optional dependency 降级、fake Provider 增强、动态
  统计四单位/空值/零值、legacy/versioned、旧 schema 零写、once 周期、软删除保留
  历史、重复打卡/兑换、未来日期、确定性复盘、损坏 JSON、原子替换失败、重复/
  兼容/冲突路由和 purge 隔离。
- 最终 Python 3.12 累计回归 14 个脚本全部退出 0：
  `test_demon_slayer.py`、`test_demon_slayer_hierarchy.py`、
  `test_demon_slayer_module.py`、`test_demon_slayer_statistics.py`、
  `test_demon_slayer_dashboard.py`、`test_demon_slayer_installable.py`、
  `test_demon_review_kei.py`、`test_demon_checkin_feedback.py`、
  `test_voice_demon_intents.py`、`test_conversation_consumers.py`、
  `test_feature_catalog.py`、`test_dashboard_shell.py`、
  `test_installable_modules.py` 和 `test_official_module_catalog.py`。
  当前根 `.venv` launcher 指向已移动的 Python 3.12，可用依赖仍在根 `.venv`
  site-packages；最终命令使用当前 Python 3.12 显式加入该只读依赖目录。首次用本机
  登记的 `.venv-asr`（实际 Python 3.8）复跑时，四项主 API 导入测试被其他任务
  已采用的 Python 3.10+ union type 阻断；两项旧斩妖演示还使用硬编码前一日。演示
  日期已改为本机当日，随后全部在项目目标解释器组合下通过；未改环境或其他模块。
- `compileall` 对 `features/demon_slayer` 和三项本轮测试使用系统临时
  `sys.pycache_prefix` 后退出 0；动态 `dashboard/index.js` 的 `node --check`
  退出 0；`git diff --check` 退出 0，输出仅为混合工作区既有 LF→CRLF 提示。
- 入场和最终状态中真实 `server/systems/data/demon_slayer.json` 与
  `focus_timer.json` 均保持预存 `M`。本轮没有读取、打印、diff、迁移、覆盖、
  reset、打包或暂存二者；未读取 `.env`、模型、缓存或 vendor，未启动或调用真实
  LLM、TTS、QQ、API、Gateway、Collector、GitHub 或其他网络。

### 待 PK-000 串行装配

- 共享 `server/api.py` 当前仍静态 include 旧 demon router；本包会识别完整兼容
  路由并避免双装配，但在 PK-000 移除静态装配、设置历史数据/可选 Provider seam
  并交给 PK-010 loader 前，停用/卸载后的新进程仍会被旧 composition 重新装配。
- 共享 Catalog 当前仍把 demon_slayer 描述为内置模块，PK-100 仍保留 legacy demon
  DOM；PK-000 需用本模块 Release fragment 生成/合并正式 Catalog 条目，并在动态
  入口生效后移除单一 legacy UI 接缝，不能长期保留两套面板。
- 冻结的 `docs/architecture/modular-monolith.md` 与
  `installable-modules.md` 仍含“demon_slayer 内置且无 manifest”的旧说明。该公共
  契约与本轮授权不一致，本任务未越权修改；PK-000/PK-011 集成必须同步纠正后再跑
  PK-900。`TASKS.md` 当前由总控保持 PK-150“进行中”，本任务建议同步为“待集成”。

## PK-011 生命周期整改（2026-07-31）

- `demon_slayer@1.0.1` 为正式包新增实例绑定与幂等 `unregister(app)`；只移除本实例
  新增路由/service。兼容复用宿主完整路由时不取得路由所有权，注册异常回滚部分路由。

## 完成文档门禁

以下八项以 2026-07-30 PK-011 可安装化增量为当前交接基线。

- [x] TASK_RECORD — 已记录 manifest、注册/Provider 接缝、动态面板、确定性包、
  Release、数据副作用、生命周期、隔离证据、验证和公共装配遗留。
- [x] TASKS_BOARD — 按 PK-000 明确冻结，本轮未修改 `TASKS.md`；交回总控把
  PK-150 从“进行中”串行同步为“待集成”，不得覆盖 PK-213 或其他任务 hunk。
- [x] PUBLIC_README — 本批冻结且未修改；正式 Catalog/API/dashboard 装配后由
  PK-000 统一把“内置”说明更新为可安装模块、optional conversation 和卸载保留数据。
- [x] MODULE_CATALOG — 本批冻结且未修改；已提供通过共享 builder 校验的 Release
  fragment，最终 Catalog 条目、下载摘要和动态入口合并交 PK-000。
- [x] ARCHITECTURE_DOCS — 本批冻结且未修改；现存“内置且无 manifest”冲突已明确
  登记为 PK-000/PK-011 串行修订项。
- [x] LOCAL_README — 不适用：没有改变本机路径、端口、启动器、解释器或环境；
  只记录并绕开现有根 venv launcher 失效，未修复或安装环境。
- [x] AGENT_RULES — 不适用：没有改变协作、安全、验证、文档或 Git 规则。
- [x] VALIDATION — 14 项累计 Python、compileall、动态 JavaScript、确定性
  Release/Catalog、任务文档门禁和 `git diff --check` 已执行；全部功能写入仅位于
  系统临时目录，未调用真实外部服务。

## 独立对话启动提示

```text
继续 Project Kei 的 PK-150 斩妖除魔可安装化任务。完整阅读 PK-011/010/100/150/
200、模块包契约和实际 feature/package/test；只修改 demon_slayer 专属包源、
构建器、Release 元数据、测试和任务记录。包必须复用同一 service/repository，
conversation 只为 optional dependency，缺少时确定性功能继续可用。全部生命周期
和业务测试使用临时 ModuleManager/store/fake clock/fake generator；禁止读取真实
demon_slayer.json，禁止修改共享 API、Catalog、dashboard、Core、TASKS 或架构文档。
完成后保持“待集成”并把串行装配项交回 PK-000，不做 Git 发布。
```

## 历史 PK-000 复核（2026-07-22）

PK-000 已独立复核 PK-900 报告、实际分层与混合工作区，并以临时 `DemonSlayerStore` 和 fake conversation 重放旧 schema、软删除历史、一次性周期边界、重复积分、未来复盘、事实 prompt、矛盾 verdict 与异常降级。八项斩妖/消费者/catalog/dashboard 回归通过，未发现新的 PK-150 阻断；PK-150 置为“已完成”。

真实 `server/systems/data/demon_slayer.json` 继续保留入场前的修改状态，本次只核对路径状态，未读取内容、查看详细 diff、迁移、重置、覆盖、暂存或提交。

该结论只对应 2026-07-22 的内置模块收口。2026-07-30 PK-000 已按 PK-011 重新打开
可安装化增量，当前顶部“待集成”和本轮交接记录优先；不得把这条历史结论用于跳过
新的 Catalog/API/dashboard/架构串行装配与 PK-900 验收。
