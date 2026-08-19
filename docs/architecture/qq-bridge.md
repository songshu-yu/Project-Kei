# QQ bridge、主 API 控制与定时推送契约

## 进程与所有权

PK-140 保持两个边界：

```text
FastAPI main process :8000
  qq_control router -> service -> schedule repository
  PK-200 conversation / PK-110 briefing / life-support controlled generation
  focus 1.1 composition -> active session validation -> PK-200 controlled generation

Node QQ sidecar
  QQ token + Gateway + C2C protocol + outbound sender
  message dedupe + schedule/focus timers + bounded delivery state
```

sidecar 不新增监听端口。主 API 不读取 `server/qq_bridge/.env`、不持有 QQ token/Gateway session、不发送 QQ；Node 不复制 conversation、Collector、缓存、记忆或 LLM 实现。

## 主 API

版本化入口：

| 方法与路径 | 语义 |
|---|---|
| `GET /api/v1/qq-control/status` | 非秘密 launcher/config/Node/dependency/running readiness；零写入、零网络、零启动 |
| `POST /api/v1/qq-control/start` | 显式启动固定 `start_qq_bridge.bat`；并发最多一次 |
| `GET/PUT /api/v1/qq-control/schedules/daily-briefing` | 读取或原子更新生成/发送时间 |
| `GET/PUT /api/v1/qq-control/schedules/life-support` | 读取或原子更新时间窗/间隔 |

兼容的 `/dashboard/qq-bridge/status|start`、`/dashboard/briefing/schedule` 与 `/dashboard/life-support/schedule` 注册在同一个 router 并调用同一 service/repository，不保留第二套规则。`/life-support/reminder` 是现有受控生成兼容接缝：只调用 PK-200 `TextGenerator`，不写 conversation history，失败由 Node 使用本地确定性文本。

所有读取必须来自实际 socket client 的 loopback 地址；带浏览器 Origin 时只能是 `http://127.0.0.1:8000`、`http://localhost:8000` 或 `[::1]:8000`。所有 qq-control PUT/POST 和 start 还必须携带受信 Origin，不能用 Host、Forwarded 或自定义 header 代替。全局 loopback middleware 在精确 Origin CORS 前保护全部路由，QQ 专用 middleware 与 router 再次校验控制操作。无 Origin 的 loopback sidecar 只能读取日程，不能写日程或启动进程。

schedule repository 独占 `server/data/daily_briefing_schedule.json` 与 `server/data/life_support_schedule.json`。缺失文件返回关闭默认值；损坏/错误结构明确失败且不改写。每次 PUT 都在同一个 repository 路径锁内完成现有文件读取、完整语义校验和新值原子替换；既有状态无法解释时，service、版本化接口与 legacy 接口统一失败为固定的 `schedule_state_invalid`，不创建临时文件。保存使用同目录唯一临时文件、`flush/fsync/os.replace`，替换失败保留旧字节。API 不接受 BAT、命令、cwd 或环境变量输入。

## 启动生命周期

sidecar 在任何异步 scheduler/Gateway startup 之前安装唯一 stdin shutdown 控制通道。
daily/life 首次 refresh、token、Gateway URL 与 WebSocket bootstrap 共享生命周期 AbortSignal；
stop 先 abort 并使调用方 startup Promise 在 adapter 10 秒等待窗口内结算，再幂等清理
listener、scheduler、socket 与 timer。旧代 provider/socket 的晚到结果不能写状态或 dispatch，
且不得以按进程名终止作为取消失败的回退。

HTTP 生命周期不会在响应头到达时提前结束。Token、Gateway URL、QQ OpenAPI、Project Kei API 和 daily/life schedule 的 JSON body 继续使用同一个 request AbortController、deadline 与进程 lifecycle signal，并以 4 MiB 实际流式字节为上限。shutdown、timeout、reader failure 或超限会取消 reader/底层请求；虚报 `Content-Length`、晚到 chunk 或晚到 Promise 结果不能绕过上限或复活 dispatch、timer 与状态。公开错误仅为稳定脱敏 code。

取消状态高于 Web Stream 的 `done`、空正文、JSON 解析和 HTTP status：reader 建立前、每次 read 结算后与返回前均重新验证同一 signal，因此原生流 cancel-to-done 不会变成成功 `{}` 或 `invalid_response`。QQ 401 只有在有界正文完整安全结算为精确 `http_401` 且 lifecycle 未取消时才能触发一次 token refresh/retry；其他 body failure 或入口 signal 已取消均在网络调用前失败关闭。

生产 control facade 只消费 ModuleManager 已验证的当前 deployment、固定 `.env` 位置、Node 与依赖 readiness。缺失条件返回有限非秘密状态；不创建配置、不打开编辑器、不运行 npm。进程检查只接受精确 installed entrypoint，响应不包含命令行、环境或路径。锁内重复/并发 start 最多调用一次 `Popen`，只使用固定 deployment entrypoint 与 cwd；不提供远程强杀或任意进程终止。

QQ sidecar 只允许由本机控制台头像或“启动 QQ Bridge”按钮明确触发；两者复用同一个受控 `POST /api/v1/qq-control/start`。Core lifespan、根启动脚本的 `qq/all` profile、模块 install/update/enable、页面加载/展开与 status GET 均只检查或展示状态，不创建 Node 进程。`enabled` 表示功能可用而非进程已运行；旧 `start_qq_bridge.bat` 只提示改用控制台，不再执行 Node。依赖仍只由根 `setup.bat --profile qq` 使用现有 lockfile 和 `npm ci` 安装。

## C2C 流程

QQ OpenAPI 默认使用 `https://api.bot.qq.com`。Gateway Identify 仅请求
`GROUP_AND_C2C_EVENT (1 << 25)`；连接必须先收到 READY 并确认心跳 ACK，才允许
dispatch C2C 并对外报告 `gateway_ready=true`。进程存活仅由 `process_running` 表示，
不能替代 Gateway 健康。Node 在固定 data root 原子写入严格、有限、短期有效的连接
快照，Python adapter 校验 PID、generation、schema 与新鲜度后才展示；凭证、URL、
OpenID 和事件正文均不进入快照。C2C 重投使用
`msg_id + msg_seq/message_scene.ext.msg_idx` 的有界复合身份去重。

固定顺序为：事件类型/消息 ID/发送者/长度校验 → allowlist → 有界消息 ID 去重 → 版本化 Project Kei API → 同一 allowlist 用户回复。allowlist 为空或发送者未授权时，conversation、briefing、菜单、按钮确认和 sender 全部不调用；日志只记录固定码，不记录正文或完整 OpenID。

普通文字调用 `POST /api/v1/conversation`；缓存情报调用 `GET /api/v1/briefing/today`。legacy `/chat/text-only` 仍由主 API 保留，但不是 Node 主路径。只处理 C2C 文本与批准按钮；其他 dispatch 类型忽略。输入最大 4000 字符，输出/Markdown 总长、分片数、字段、URL 和每类条目均有限。QQ 401 最多刷新 token 并重试一次；上游正文不进入异常、日志或用户回复。

### 业务菜单消费边界

主菜单固定为每日情报加斩妖、健身、专注、日历四个子菜单。主菜单/子菜单 action 是集中登记的固定枚举；斩妖打卡 action 可携带动态 goal_id，且该 ID 必须匹配 `/api/v1/demon-slayer/status` 最近返回给同一用户的前 4 个合法短 ID。斩妖添加确认 action 只携带不透明待确认 ID，不携带标题、cadence 之外的业务参数或 API 信息。两类用户绑定缓存都只存在 Node 进程内、最多 200 个用户、10 分钟惰性过期，不写 scheduler state 或业务文件；添加缓存每用户只保留最后一个待确认项，确认/取消后立即消费。keyboard 最多 5 行、每行最多 5 个按钮；业务列表最多显示 4–5 项。

interaction 顺序固定为 allowlist → interaction ID 去重 → `PUT /interactions/{id}` 安全 ACK → 固定 API dispatch → 同一用户回复。主/子菜单展示零 Project Kei 写调用；明确写按钮或严格命令一次只调用一个固定版本化 endpoint，不自动重试写请求。

| 菜单 | 固定读取 | 明确写入 |
|---|---|---|
| 斩妖 | `GET /api/v1/demon-slayer/status`；显式 `GET /api/v1/demon-slayer/reviews/daily` | 用户绑定单次确认后的 `POST /api/v1/demon-slayer/goals`，body 固定为已验证标题、明确 cadence、`category=auto`、`repeat_mode=recurring`、`target_date=null`；`POST /api/v1/demon-slayer/checkins` 的 body 仅含已验证 goal_id、done、空 note 与布尔 `with_encouragement`，完成固定为 `true`，未完成固定为 `false` |
| 健身 | `GET /api/v1/fitness/status` | 独立确认按钮 `POST /api/v1/fitness/checkins` |
| 专注 | `GET /api/v1/focus/status` | `POST /api/v1/focus/start|stop`；兼容按钮固定 25 分钟且无鼓励；显式鼓励按钮/严格命令仍用 `force=false`，到期才调用固定 `POST /api/v1/focus/encouragement` |
| 日历 | `GET /api/v1/calendar/today`、`GET /api/v1/calendar/status` | 严格 `添加备忘 YYYY-MM-DD 标题` → `POST /api/v1/calendar/events`；严格 `记录修炼 技能 小时数` → `POST /api/v1/calendar/practice` |

bridge 不导入 Python 模块，不读取 demon/fitness/focus/calendar repository、个人 JSON 或缓存，不复制积分、妖怪分类、周期重复、连续天数、计时、重复事件或修炼累计规则。dispatch 表没有 legacy、reset、reward/redeem、目标编辑/删除、临时目标、DELETE/PATCH、`force=true`、任意 host/path/method/prompt 或模块生命周期操作；未知 action 零 ACK、零 API、零发送。精确“添加斩妖任务”及不带标题的“添加日/周/月/年任务”只展示 cadence 按钮；点击 cadence 只给固定格式；严格 `添加日任务 目标名称` 等单消息命令才建立短时待确认项，最终确认恰好调用一次固定 goals POST。取消、过期、跨用户、重复确认和格式错误均零写入、零 conversation。明确菜单/功能命令/严格斩妖、日历及专注命令先于宽泛情报关键词和 conversation；合法命令参数即使包含“每日情报”等关键词也不会被改路由，格式错误命令只返回固定用法，不交给 LLM 猜测，也不建立长期多轮输入状态。

斩妖完成响应只显示 PK-150 返回的 `active_days/current_streak/longest_streak/streak_unit/encouragement`：单位仅做 `day/week/month/year` 的中文展示映射，缺失启用天数显示未知，`once` 明确不累计，零值保持为零。Node 不根据 status/check-in 历史推导连续记录，不额外请求 conversation；PK-150 在同一次明确 check-in 内完成可选受控生成和本地降级。其他业务响应同样只提取允许字段，目标名、备忘、技能与 Markdown 先清洗/转义/限长再分片。超时、404、422/500、损坏个人状态或无效响应只映射为有限固定提示；上游正文、请求体、异常、内部路径、凭证、OpenID 和个人状态不进入日志或错误回复。focus 404 不触发安装、启用、重启或 legacy 回退。

Gateway client 只有一个 socket、heartbeat 和 reconnect timer。断线采用上限 60 秒指数退避；重复 connect 不新建 socket。shutdown 先进入终态，再取消 timers/重连和关闭 socket；Node scheduler 同样以 epoch 阻止 await 后的发送/写状态。

## 每日情报

日程要求生成早于发送。预生成每天只进入一次并调用 `POST /api/v1/briefing/generate`；发送只调用 `GET /api/v1/briefing/today`。缓存缺失时结束发送，不触发 Collector。按日期和 `sha256(OpenID)` 截断标记逐用户隔离；成功用户不因失败用户重收。关闭/改期会清理旧 generate/send timer，重复 start 不累计 timer。

为保证“最多一次”，每次外发前先原子记录 `sending`，成功后记录 `success`，明确失败记录有限 `failed/error_code` 供下一轮受控重试。若进程在 reservation 与外发完成之间异常，重启后对 `sending` 失败关闭，不自动重发；这避免重复，但可能需要人工确认实际投递结果。

## 生命维持

只有启用、`start < end`、正间隔和非空 allowlist 才创建 timer。每个本机时间槽/用户使用相同 reservation 状态机。文案生成失败使用由槽位稳定选择的本地提醒；不保存模型回复，也不影响下一时间槽。关闭、改期和 shutdown 清理旧 timer。

## 专注鼓励

普通 status/start/stop 和兼容 25 分钟按钮不触发模型。白名单用户必须显式选择 `kei:focus:start25:encourage10`，或发送严格 `专注 <2-240 整数分钟> 鼓励 <正整数且小于专注时长>`，才会在成功 start 响应的 `session_id/start_at` 上登记提醒。action 与命令都不能提供 prompt、URL、endpoint、HTTP method、`force` 或 task。

sidecar 以 `sha256(user hash + session + start_at)` 截断键登记一个 timer。到期先调用 `GET /api/v1/focus/status`，仅在 `active=true`、mode/elapsed/remaining 合法且 `session_id/start_at` 完全一致时，原子保存 `sending` reservation，然后调用一次 `POST /api/v1/focus/encouragement`。该 loopback-only endpoint 由 focus service 再次读取同一 repository 并验证 active identity，自行计算 mode/elapsed/remaining，再通过注入的 PK-200 `TextGenerator` 使用固定 purpose prompt；它不接收 QQ 身份、聊天历史或用户 prompt，也不写普通 conversation history。

模型 `generated=false` 或明确生成超时由 Node 使用有界确定性文本；focus status 404/超时/损坏/身份不匹配，以及生成接口 404/409/500/无效响应均不发送。QQ stop、新成功会话、白名单移除和 shutdown 会取消未完成 entry/timer；外部 reset/stop/disable 没有反向推送契约，因此保留的物理 timer 会在到期 status 复核时逻辑取消，零模型、零发送。QQ 发送失败不重复模型调用或自动发送；只有发送成功后才保存 `sent`，最终状态写失败保留磁盘 `sending`，跨重启继续 at-most-once 失败关闭。

## Node 状态

每日与生命维持两份状态只保存 `schema_version`、日期/槽位、24 位用户哈希、`sending/success/failed` 与有限错误码，分别最多 14 天/96 槽。第三份 `focus_encouragement_state.json` 最多 256 项，只保存用户哈希、不透明 `session_id`、`start_at/due_at`、`scheduled/sending/sent/failed/cancelled` 和有限错误码。三者都不保存 token、Authorization、完整 OpenID、task、消息、情报、模型响应或内部路径。读取对所有顶层、bucket/entry、身份哈希、时间、状态和错误码执行字段白名单与语义校验；未知字段、完整 OpenID 形态键、秘密/任务/消息字段或非法记录都令对应 scheduler 在任何 timer、API、生成、发送或写入之前失败关闭。

写入使用唯一临时文件、文件 `fsync` 和原子 rename。损坏、旧版或未知 Schema 会关闭调度且不覆盖原文件。自动测试向 `statePath` 注入系统临时目录，并只使用 fake fetch/WebSocket/clock/timer/sender。

## 网络和失败

- QQ 网络：仅 Node 明确启动后请求 token、Gateway 和 C2C API。
- Project Kei 网络：Node 只访问配置的主 API；对话、业务菜单、预生成、缓存读取和提醒边界如上。
- schedule/status GET 不产生外部网络；schedule PUT 只原子写本机文件；start 只在显式控制台动作后调用同一 adapter facade。
- 任一 QQ 用户发送失败不阻断其他用户；模型提醒失败使用本地文本；状态损坏/保存失败关闭对应调度；上游正文和身份信息不进入普通日志。

QQ 已接入 PK-010 的可安装 sidecar lifecycle/manifest，并通过同一 adapter facade 提供有限 status 与显式 start。它不提供远程强杀或自动启动；受控 shutdown 只关闭当前 Core 所拥有的实例。

控制台显式关闭固定使用 `POST /api/v1/qq-control/stop`，只接受可信 loopback Origin
和空 body。当前 Core 持有进程句柄时沿用 stdin `shutdown`；Core 重启后，只有固定
dependency entrypoint 的 PID 身份、严格新鲜 gateway 状态、同 generation 与
`shutdown_control_ready=true` 同时成立时，才允许写入固定四字段、短期有效的
`shutdown_request.json`。外部 probe 本身不能授权关闭；浏览器不能提交 PID、端口、路径、
命令或 generation，也不使用宽泛 kill。
