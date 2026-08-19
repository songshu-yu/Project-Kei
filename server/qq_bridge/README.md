# Project Kei QQ Bridge

## Gateway 连接健康（0.1.10）

OpenAPI 默认固定为官方 `https://api.bot.qq.com`；历史
`https://api.sgroup.qq.com` 只作为精确配置的兼容值，其他地址会被拒绝。
Gateway Identify 只声明 `GROUP_AND_C2C_EVENT (1 << 25)`。进程存在不再等同于
QQ 已连接：只有收到 `READY` 且心跳已经获得 ACK，控制台才显示
`gateway_ready=true`。`connecting/identified_or_ready/reconnect_wait/failed/stopped`
以及有限错误码、close code、重连次数和最近 READY 时间写入固定
`data/gateway_status.json`；快照使用原子替换，不含 token、Gateway URL、OpenID、
消息正文或事件内容。Python facade 校验 PID、会话 generation、严格字段和新鲜度，
损坏、过期或外部未跟踪进程均 fail closed。

C2C 去重身份为官方 `msg_id` 加可用的 `msg_seq`/`message_scene.ext.msg_idx`；
真正重投不会再次调用 conversation 或 sender，而同一 `msg_id` 下合法的不同序号不会
被误杀。仅 `message_type=0|103` 的有界字符串正文进入既有白名单后路由。

契约依据：QQ 开放平台的 [API 调用指南](https://bot.q.qq.com/wiki/develop/api-v2/dev-prepare/api-call-guide.html)、
[C2C_MESSAGE_CREATE](https://bot.q.qq.com/wiki/develop/api-v2/autogen/event/c2c_message_create.html)、
[消息概览](https://bot.q.qq.com/wiki/develop/api-v2/server-inter/message/overview.html) 与
[富媒体](https://bot.q.qq.com/wiki/develop/api-v2/server-inter/message/rich-media.html)。

## 启动期可取消关闭（0.1.11）

固定 stdin `shutdown` listener 会在任何 scheduler/Gateway startup await 之前安装。
daily/life 首次 schedule refresh、QQ token 获取、Gateway URL 获取与 WebSocket bootstrap
共享一个生命周期取消信号；stop 会先 abort，再幂等清理 scheduler、socket、timer、listener
和 stdin。即使 provider 永不返回，调用方 startup Promise 也会立即 settle；provider 的晚到
resolve/reject、旧 socket 的 open/READY/ACK/C2C 都不能复活状态、建立 timer 或 dispatch。
真实本机 HTTP fetch 同时消费 AbortSignal，因此关闭不依赖默认 45 秒请求超时，能够落在 adapter
的 10 秒 owned-process 等待窗口内。外部进程仍没有 kill-by-name 回退。

## 有界 HTTP 响应生命周期（0.1.12）

Token、Gateway URL、QQ OpenAPI、Project Kei API 与 daily/life schedule 的 JSON 请求在响应头到达后仍继续受同一个 deadline 和 lifecycle AbortSignal 约束。JSON body 使用 4 MiB 流式上限；缺失或虚报较小的 `Content-Length` 不能绕过实际字节计数。shutdown、调用方取消、超时、reader 错误或超限会 abort 底层请求并在能力存在时只取消一次 reader；晚到 chunk、resolve/reject 不会恢复发送、调度或状态。错误只暴露稳定代码，不包含 URL、响应正文、凭证或用户标识。

### 取消优先级与 401 门槛（0.1.13）

读取正文前、每次 Web Stream `read()` 结算后以及 JSON 解析/返回前都会重新检查 request signal。只要请求已经取消，原生流因 `cancel()` 返回 `done=true`、空 body、半段 JSON 或已排队完整 JSON 都统一优先返回 `request_cancelled`（deadline 先发生则为 `request_timeout`）；真正未取消的 200 空响应仍保持 `{}` 契约。QQ 401 只有在正文完整、有界、合法并精确结算为 `http_401`，且 lifecycle 仍 active 时才允许唯一 token refresh；取消、timeout、reader error、超限或 invalid JSON 均零 refresh/零 retry。进入 fetch/token/request 时 signal 已取消则在 provider 前拒绝，零网络。

### Gateway 阶段诊断（0.1.14）

Gateway 状态只记录固定、有限、脱敏的阶段错误码。Token 获取区分请求失败、凭据被拒绝和响应格式无效；Gateway 地址获取区分请求失败、平台拒绝、响应格式无效以及缺失/无效/不在白名单的地址；WebSocket 区分构造失败、传输错误、就绪前关闭、Hello 超时和 READY 超时。原始异常、响应正文、URL、Token 与应用凭据均不会进入状态文件、控制接口或日志。Bridge 进程运行只表示 sidecar 存活，只有 READY 与健康心跳同时成立时 `gateway_ready=true`；每个失败仍走唯一有界重连，shutdown 会取消 pending provider、socket 与 timer，旧回调不得复活。

### READY 后首次心跳（0.1.15）

收到 Hello 后 bridge 只发送 Identify、记录服务端给出的心跳间隔并继续等待 READY，不再提前发送心跳。收到首个合法 READY 后才立即发送唯一首次心跳并启动周期 timer；只有该心跳获得 ACK 后才设置 `gateway_ready=true` 并允许业务 dispatch。READY 前或没有 pending heartbeat 的 ACK、READY 早于 Hello、重复 Hello 与重复 READY 均只记录固定安全事件并忽略，不会放行业务、重复 Identify/首次心跳或绕过 READY timeout。shutdown 与旧 generation 的晚到事件仍不能复活连接。

### 已接受事件序号（0.1.16）

Gateway heartbeat 的 `d` 只确认状态机已经接受的序号：Hello 后首个合法 READY 可推进序号，READY 与有效 heartbeat ACK 同时成立后实际放行的 op0 dispatch 才可继续推进。READY-before-Hello、重复 READY/Hello、unexpected ACK、ACK 前 dispatch、op7/op9、非法 JSON 或不合法序号均不改变已确认序号；ACK 即使携带非标准 `s` 也只完成 pending heartbeat，不推进事件序号。因此 bridge 不会通过后续 heartbeat 确认一个从未放行的业务事件。

### 健康状态无错误码（0.1.17）

Gateway 状态快照在没有当前错误时严格保留 `last_error_code=null`。READY 与有效 ACK 后的健康连接不会被控制接口或动态面板误显示为 `gateway_failed`；合法非空有限码继续保留，未知、越界或疑似泄漏值仍统一收敛为 `gateway_failed`，不会回显原值。

QQ bridge 是独立 Node sidecar。它独占 QQ access token、Gateway session、C2C 协议与 QQ 发送；Project Kei 主 API 不读取 QQ 凭证、不连接 Gateway，也不直接向 QQ 发消息。

```text
QQ C2C text / approved button
  -> allowlist
  -> bounded message-ID dedupe
  -> Project Kei versioned API
  -> bounded QQ text/Markdown reply
  -> optional, explicitly enabled final Silk attachment for ordinary chat only
```

群聊、图片、文件和语音输入不属于当前边界。QQ 语音回复默认关闭，只覆盖符合下述
readiness 的普通 conversation 回复。

## 配置与启动

1. 在动态 QQ 面板打开 QQ 开放平台，填写 AppID 与 Secret 并显式保存；也可继续按
   `.env.example` 人工维护固定的 `.env`。面板永不回显 Secret，空 Secret 会保留
   已有值，且不会把凭证写入浏览器存储。白名单等其余字段仍由本机 `.env` 维护。
2. 在项目根目录运行 `setup.bat --profile qq`，由现有 `package-lock.json` 通过 `npm ci` 准备依赖；启动器不会代替用户安装。
3. 启动 Project Kei API 后，在本机控制台明确点击 QQ 头像或“启动 QQ Bridge”。两者复用同一个受控 `POST /api/v1/qq-control/start` 动作。

Core 启动、`start.bat`/`start_all_services.bat`、模块安装/更新/启用、页面加载/展开和状态刷新都不会创建 QQ Node sidecar；`enabled` 只表示功能可用。未运行时控制台显示“已启用，等待手动启动”。启动检查只验证当前受信部署、Node、`.env` 与依赖，缺失时明确失败；不会创建/覆盖 `.env`、打开编辑器或运行 npm。状态接口只返回有限 readiness、`process_running` 与 `gateway_ready`，不返回配置内容、命令行或进程环境。

配置状态使用 `GET /api/v1/qq-control/configuration`，保存使用显式
`POST /api/v1/qq-control/configuration`。保存只接受真实 loopback 客户端和精确受信
Origin，并由 PK-140 自有组件在固定 `server/qq_bridge/.env` 上执行唯一临时文件、
`fsync` 与原子替换；它保留其他键和值，不接受路径、命令、cwd 或环境变量。保存失败
或并发异常时旧文件不被半写覆盖。响应只包含 configured/missing、AppID 掩码和是否
需要重启；若 bridge 已在运行，需先在本机停止旧进程，再通过同一 adapter facade
重新启动，本项目不提供远程强杀或第二套 bridge。

同一表单提供“QQ 回复同时发送语音”显式开关，对应固定非秘密配置
`QQBOT_REPLY_WITH_VOICE=true|false`，默认 false。只有 PK-210 报告固定
`qq_c2c_voice_v1`/`audio/silk` profile ready，且独立非秘密
`qq_media_upload_capability=available` 时才能开启；unknown、denied、unavailable、
生产 encoder 缺失或异常均显示 voice unavailable。Secret 存在不能推断媒体权限，状态
读取也不会真实发送探测消息。

白名单为空时 bridge 可以保持连接，但不会转发、回复、显示菜单、确认按钮或主动发送。普通未授权消息只产生不含消息正文和个人标识的固定安全日志。当前 bridge 不提供持续打印 `user_openid` 的“发现模式”；首次绑定标识应通过操作者明确授权的 QQ 开放平台调试/事件工具取得，再人工写入本机 `.env`。不得把标识、白名单或凭证复制到文档、测试或浏览器存储。

## 私聊与网络边界

- 只接受明确的 `C2C_MESSAGE_CREATE` 文本和白名单内 `INTERACTION_CREATE` 按钮。
- 普通文字调用 `POST /api/v1/conversation`；`/chat/text-only` 只保留服务端兼容，不是 bridge 主路径。
- “每日情报”和按钮只调用 `GET /api/v1/briefing/today`，缓存缺失时提示失败，不触发采集。
- 明确菜单、四个业务功能名、斩妖添加命令和两条严格日历命令先于宽泛的每日情报关键词及 conversation 路由；因此目标、备忘标题或修炼技能名包含“每日情报”等词时仍确定性执行严格命令。未知普通文字继续进入 `/api/v1/conversation`。
- QQ 401 最多强制刷新 Token 并重试一次；其他 QQ/Kei 错误只记录有限错误码，不拼接上游正文。
- 输入、回复、Markdown 字段、各类条目、warnings、URL 和总输出均有限长；URL 只接受无 userinfo 的 HTTP(S)，敏感 query 参数会被移除。
- Gateway reconnect 使用最大 60 秒的指数退避；socket、heartbeat 与 reconnect timer 都是单实例。shutdown 会取消未来调度并阻止新的连接、发送和状态写入。

### 可选普通聊天语音

开关开启且综合 readiness 可用时，普通 `/api/v1/conversation` 回复仍先完成文本发送，
随后至多调用一次 `POST /api/v1/voice/synthesize`。请求只有固定 purpose、最终有界文字和
由消息身份哈希形成的受控 Idempotency-Key；仅接受 HTTP 200、`audio/silk`、
`final=true`、`qq_c2c_voice_v1`、严格 `X-Kei-Audio-Duration-Ms` 1–60000、完整长度不超过
8 MiB 及合法 Silk 头。缺头、重复/非法时长、WAV、超限、encoder/Pack 不可用、超时或恶意
错误体全部保留纯文本，不在 Node 估算时长或转码。

合格音频按腾讯官方 Node SDK 的普通媒体契约直接调用 QQ 单聊 `/files`：固定
`file_type=3`、`srv_send_msg=false`，并把已验证且不超过 8 MiB 的 Silk 字节作为
`file_data` base64 提交；取得有界 `file_info` 后再发送一次 `msg_type=7`。不调用大文件
`upload_prepare`/分片接口，不跟随重定向，不接受
用户、浏览器、manifest 或 Project Kei 返回的任意上传 URL、路径、文件名、codec 参数或
命令。文本发送成功是可靠基线，任何 TTS/上传/语音发送失败都不补发第二份文本。

只有普通 conversation 进入上述链路；菜单、按钮 ACK、状态、确认、错误、非法命令、
斩妖/健身/专注/日历结果、每日情报、生命维持和专注鼓励始终纯文本。语音投递状态只保存
有界哈希键与 claimed/sent 标记，不保存音频、文字、完整 OpenID、URL、file_info 或错误体；
claimed 采用 at-most-once 失败关闭，重复事件、并发与重启不会再次付费生成或发送。shutdown
会取消进行中的本机合成请求并阻止后续上传/发送。

## 业务私聊菜单

主菜单固定为“每日情报、斩妖除魔、健身打卡、专注计时、日历与修炼”。主菜单和子菜单展示不产生业务写请求；interaction 在 allowlist 与事件去重后先安全 ACK，再访问 Project Kei 本机版本化 API。按钮 action 只能命中 bridge 内的固定枚举/分发表，不能作为 URL、HTTP method、命令或文件路径执行。

- 斩妖只读 `/api/v1/demon-slayer/status`，只展示前 4 个今日目标；完成/未完成按钮仅接受刚由该响应返回、格式合法且仍在 10 分钟用户绑定缓存中的 goal_id，并写 `/api/v1/demon-slayer/checkins`。完成固定提交 `with_encouragement=true`，同一次响应直接展示 PK-150 service 返回的启用天数、当前/历史连续周期、正确单位和 Kei 鼓励；未完成固定为 `false`。Node 不重算连续规则，也不额外调用 conversation。
- 斩妖子菜单新增“添加常驻目标”。发送精确的“添加斩妖任务”或不带标题的“添加日/周/月/年任务”会弹出四个周期按钮且零业务写入；点击周期只显示固定格式。严格单消息 `添加日任务 目标名称`、`添加周任务 目标名称`、`添加月任务 目标名称`、`添加年任务 目标名称` 会生成用户绑定、单次使用、10 分钟过期的确认按钮，只有点击“确认添加”才调用一次 `POST /api/v1/demon-slayer/goals`，固定提交 `category=auto`、`repeat_mode=recurring`、`target_date=null`。标题只存在短时内存缓存，不进入 action、磁盘或 conversation；取消、过期、跨用户和重复确认均零写入。单独“生成今日复盘”只读 `/api/v1/demon-slayer/reviews/daily`。不开放目标编辑、删除、临时目标、奖励兑换、reset 或其他复盘。
- 健身只读 `/api/v1/fitness/status`；独立“确认今日健身打卡”调用一次 `/api/v1/fitness/checkins`。不开放 reset。
- 专注只读 `/api/v1/focus/status`；原“开始 25 分钟专注”保持无模型副作用，仍使用 pomodoro、空 task、`force=false`、`with_audio=false`。另有显式“25 分钟，10 分钟后鼓励”按钮和严格单消息 `专注 25 鼓励 10`；专注时长只接受整数 2–240，鼓励时间必须为正整数且早于结束。格式错误只返回用法，不进入 conversation。停止只调用 `/api/v1/focus/stop` 并取消该用户尚未发送的鼓励。404 时只提示模块不可用，不安装、升级、启用或重启模块。
- 日历分别只读 `/api/v1/calendar/today` 与 `/api/v1/calendar/status`。新增只接受 `添加备忘 YYYY-MM-DD 标题` 和 `记录修炼 技能 小时数` 两条严格单消息命令；日期、长度和大于 0 且不超过 24 小时的范围在 Node 本地确定性校验，格式错误只返回用法，不进入 LLM 或长期多轮状态。

所有业务响应只提取有界字段；目标、备忘、技能、鼓励和 Markdown 会清洗、转义、限长，列表只展示前 4–5 项。斩妖 `active_days=null` 显示未知，`once` 显示不累计，连续零值保持为零，`streak_unit` 只映射为天/周/月/年标签。超时、404、422/500、损坏个人状态和上游错误体统一为有限提示，不回显响应正文、异常、路径、凭证或个人状态。bridge 不读取四个模块的 repository、JSON 状态或缓存，也不调用 legacy、reset、reward/redeem、DELETE/PATCH、临时目标创建、`force=true` 或任意 URL。

## 每日情报调度

bridge 每 30 秒从真实 loopback 主 API 读取 `/api/v1/qq-control/schedules/daily-briefing`。生成时间必须早于发送时间；关闭或改期会立即取消旧 timer。

- 预生成每天最多进入一次，显式调用 `POST /api/v1/briefing/generate`。
- 发送阶段只读 `GET /api/v1/briefing/today`，不传模糊 query，也不会在缓存缺失时偷偷采集。
- 按本机日期和白名单用户的哈希去重标记发送；成功用户不会因其他用户失败而重收。
- 发送前先原子保存 `sending` 预留，再发 QQ，成功后保存 `success`。进程在两步之间异常时采用 at-most-once 的失败关闭策略：该用户不会自动重发，但可能需要人工确认本次是否实际送达。
- 状态最多保留 14 天，只包含日期、哈希去重标记、有限状态/错误码，不保存完整 OpenID、情报或消息。

## 生命维持提醒

bridge 从 `/api/v1/qq-control/schedules/life-support` 读取时间窗和正间隔，只在启用、合法时间窗、非空白名单时建立 timer。关闭或改期会取消旧 timer。

每个时间槽/用户采用同样的原子 `sending -> success|failed` 去重；最多保留 96 个槽位。文案只通过本机 `/life-support/reminder` 受控生成接缝取得，不写 conversation history。生成失败时使用由槽位确定的本地提醒，不影响下一个槽位。

## 专注到点鼓励

只有白名单用户明确选择鼓励按钮或发送合法严格命令，bridge 才会登记一次提醒。开始响应必须包含有界 `session_id/start_at`；登记先写入 `data/focus_encouragement_state.json`，成功后才建立 timer。每个用户/会话只有一个 entry/timer，重复事件、重复登记与重启恢复不会累计。

到期固定执行 `GET /api/v1/focus/status`，确认 `active=true` 且 `session_id/start_at` 与登记完全一致；随后先原子保存 `sending` reservation，再且仅再调用一次 `POST /api/v1/focus/encouragement`。主 API 会再次校验同一 active session，并通过 PK-200 受控生成门面使用 mode、已专注分钟和剩余分钟生成短文案，不接受 QQ 标识、任意 prompt/URL 或聊天历史，也不写 conversation history。`generated=false` 或模型超时使用 Node 本地确定性鼓励；生成接口的 404/409/500、无效响应不发送。

focus status 404/超时/损坏、会话停止/完成/重置/替换、白名单移除、用户从 QQ 停止或启动新会话、状态损坏和 shutdown 都会失败关闭，零后续模型、零发送；外部控制台变化没有推送协议，会在到期 status 复核时逻辑取消。QQ 发送失败不重新调用模型或自动重发。发送成功后才把状态改为 `sent`；最终保存失败时磁盘仍保留 `sending`，重启后不会再次生成或发送。

## 状态安全

运行状态位于 `data/daily_briefing_schedule_state.json`、`data/life_support_schedule_state.json`、`data/focus_encouragement_state.json` 和 `data/voice_reply_delivery_state.json`。写入使用同目录唯一临时文件、`fsync` 与原子替换；失败清理临时文件并保留旧字节。前两份严格校验日期/槽位、用户哈希与投递状态；focus 文件最多 256 项，只接受 24 位用户哈希、有界不透明 session、合法 `start_at/due_at`、`scheduled/sending/sent/failed/cancelled` 和有限错误码；voice 文件最多 1000 项，只接受 32 位哈希键和 `claimed/sent`。未知字段、完整 OpenID 形态键、Authorization/Token/Secret、任务/消息字段或非法记录均视为损坏，并在 timer、状态读取、生成和发送之前失败关闭。bridge 不会用空状态自动覆盖损坏、旧版或未知 Schema；需要操作者在 bridge 停止后先备份并明确处理旧文件。

## 隔离验证

```powershell
node --test tests/*.test.mjs
Get-ChildItem -LiteralPath src -Filter *.mjs | ForEach-Object { node --check $_.FullName }
```

## QQ 语音能力声明与流式边界（0.1.9）

`QQBOT_MEDIA_UPLOAD_CAPABILITY` 是非秘密的管理员声明，只接受
`unknown|available|unavailable|denied`，默认 `unknown`。它不是自动权限验证：保存不会联网、
上传或发送消息，也不会根据 AppID、Secret 或白名单推断能力。只有该声明为 `available` 且
PK-210 的 `qq_c2c_voice_v1` profile ready 时，才允许开启 `QQBOT_REPLY_WITH_VOICE`；降为其他
状态时会在同一次原子配置写入中关闭语音开关。

合成响应从建立请求、等待响应头、流式读取完整正文到最终格式校验共用同一个 deadline。
Node 按块累计实际字节，超过 8 MiB 会立即取消 reader 和请求；伪造较小 Content-Length、
挂起流、reader 异常、超时或 shutdown 均零上传、零语音发送，并保留已发送的文字回复。

## 可安装 sidecar 部署

QQ 模块包只包含受审查的 `package.json`、`package-lock.json`、`src/`、动态面板与
模块说明，不包含 `.env`、`data/`、`node_modules`、凭证、白名单、日程、发送
状态、缓存或日志。已安装版本目录保持只读，完整
`installed_tree_sha256` 不排除任何子树。

只有显式 `setup.bat --profile qq` 可以在 Core 推导的
`server/runtime/module-dependencies/qq_bridge/<version>/` 临时 staging 中复制
固定 sidecar allowlist、执行锁定的 `npm ci` 并原子发布。可用部署的顶层只能有
`.project-kei-deployment.json`、`package.json`、`package-lock.json`、`src/`
和 `node_modules/`。marker 必须严格匹配当前模块 ID、版本、不可变包摘要以及
package/lock 摘要；缺失、旧版本、未知字段、内容篡改或半部署均返回有限的
`dependencies_missing`/`deployment_invalid` 状态，零启动且不回退源码树。

Core 登记的同一个 `qq_bridge` adapter 同时服务模块生命周期和 qq-control
status/start facade。它只启动 dependency deployment 中固定的
`src/index.mjs`，工作目录固定为现有 `server/qq_bridge`，继续使用且在卸载/
更新时保留该处 `.env` 与 `data/`。模块安装、网页点击和普通 start 不运行 npm，
也不接受用户提供的 path、command、cwd 或环境变量。当前公共生命周期没有远程
stop 接口。

测试只使用虚构凭证、假 HTTP/WebSocket、假时钟/timer 和系统临时目录；不得运行 `src/index.mjs`、真实 Gateway、Token、QQ 发送、真实 LLM/情报采集或真实 npm 安装。

### QQ 语音阶段诊断（0.1.20）

普通聊天的语音附带流程只记录最近一次有限结果码与时间：合成不可用、音频校验失败、
QQ `/files` 上传失败、`file_info` 无效、`msg_type=7` 发送失败或发送成功。状态不会保存
或返回消息正文、OpenID、QQ 原始错误体、URL、Token、Secret 或音频内容；未知错误统一
收敛为 `voice_delivery_failed`。控制台可据此判断为什么保留了文字降级。
