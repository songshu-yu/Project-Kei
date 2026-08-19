# Project Kei 模块化单体规范

## 目标

Project Kei 保持一个主 FastAPI 进程，但把业务拆成可独立讨论、实现、测试和替换的功能模块。QQ bridge、ASR 与 GPT-SoVITS 继续作为已有独立进程；其他功能在没有明确收益前不拆成微服务。

模块化单体同时是按需安装能力的代码基础，但两者不是同一层协议：本文规定模块内部结构、依赖方向和兼容迁移；[可安装模块生命周期规范](installable-modules.md) 另行规定模块包的清单、安装状态、依赖解析、启停、升级、回滚和卸载行为。可安装能力不得破坏本文的单体边界，也不意味着把每个功能改成独立服务。

## 目标目录

```text
server/
├── api.py                         # 过渡期应用装配与旧接口兼容
├── core/                          # 配置、公共协议、错误和共享基础设施
└── features/
    ├── catalog/                   # 模块目录与发现接口
    └── <module>/
        ├── router.py              # HTTP 边界
        ├── models.py              # 请求/响应模型
        ├── service.py             # 用例与业务编排
        └── repository.py          # 该模块自己的持久化
```

控制台采用相同边界：`server/static/dashboard.html` 保留兼容 DOM 和尚未迁移的业务脚本，`server/static/dashboard/` 承载公共样式、同源请求、通知、折叠、启动、模块注册与动态加载。公共资源通过只读 `/dashboard/static/{asset_path}` 提供，并限制在该目录内；各功能脚本只调用自己模块声明的接口。
`GET /dashboard` 与公共静态资源使用 `Cache-Control: no-store`，HTML 入口和公共
ES module 依赖共享同一版本标记。该策略只负责控制台资源失效，不改变模块 API、
目录响应或业务缓存语义；更新后主 API 需要重启一次以应用新的响应头。

公共外壳的前端入口协议为 ES module `mount(context)` 与可选 `unmount()`。`context` 只包含该模块的 DOM 根节点、只读模块目录快照、按 `api_namespaces`/`legacy_endpoints` 限制的同源请求函数和统一通知函数。目录失败、入口 404/超时及挂载异常必须在模块根节点内隔离；尚未迁移的内置业务继续通过 `dashboard.html` 的单一 legacy 启动回调运行，不能复制成第二套实现。

控制台“模块管理”由公共外壳拥有，并固定分成三种视图：`可安装模块` 只消费
PK-010 官方 Catalog 缓存中真实存在且声明 `install_official` 的受信版本；
`已安装模块` 只消费 PK-010 registry 合并到 `GET /api/v1/modules` 的 managed
条目；`内置功能` 只读展示 `required=true`、`installable=false` 或非 managed
的 Core feature。内置功能不得获得下载、停用、卸载或 purge 控件。普通加载和
本机目录刷新不访问 GitHub；只有用户显式刷新官方目录或在展示来源、大小、摘要、
权限及数据策略后再次确认安装/更新/回滚，才调用 PK-010 的固定官方接口。浏览器
不能提交 package URL、服务器路径、Token/Cookie，也不直接下载或解包。卸载默认
保留数据，purge 是要求精确 module ID 的独立危险操作；任何需要重启的响应只显示
说明，公共外壳不得自动重启或结束 Core 进程。

公共视觉层另定义可组合的模块卡头：头像、名称、单行说明、状态胶囊、既有主动作
和折叠入口均为可选插槽，业务模块只注入自己公开 API 已返回的状态和已有动作。
legacy 主面板由公共折叠脚本渐进包装为组件卡：收起时在响应式网格中只显示小图
与标题；标题展开后组件占满整行，媒体槽放大并恢复原有完整说明和业务 DOM。无合法
本地素材时显示显式图片空槽。用户明确选择 PNG/JPG/WebP 后可先用对象 URL 预览，
再经 PK-100 自有同源 UI asset API 原子保存到 Git 忽略的
`server/data/dashboard_ui/avatars/`。该目录只拥有控制台外观图片，不得保存模块
业务状态、配置、凭据或缓存。可安装模块可通过自己的挂载根或
`data-panel-avatar`/`data-panel-summary` 提供合法本地展示元数据，但不得由公共
外壳发现网络图片、业务状态或私有文件。
每个顶层组件必须提供稳定且唯一的 `panel_id`，作为标题、单行说明、仓库默认图片、
设置入口和用户自定义图片之间的 UI 注册键。新增或更新组件只同步其展示元数据和
模块目录；头像读写始终复用 PK-100 的通用 UI asset API，不能在业务 router 中
复制头像接口或借此改变业务契约。
服务健康摘要使用两个 PK-100 保留 UI 注册键 `service-status-normal` 与
`service-status-attention`。它们只根据 `/dashboard/status` 已有的 ready/ok 结果
切换共享图片，不得参与健康判断、启动服务或改写配置。两类图片与组件头像复用同一
受控素材 API、格式/大小限制和默认/本机覆盖分层；无图片时必须保留可读占位。
主组件展开卡统一为“竖版角色图 + 完整详情”的两列布局：图片槽最大 280×350
（4:5），图片使用 `object-fit: contain`，不得使用放大 transform 或 `cover`
裁切；右栏容纳标题/说明、左对齐状态与动作坞、设置和原业务内容，不能把正文放在
媒体下方制造空白。720px 以下改为单列并将图片限制为最大 260×325、水平居中，
动作坞占满可用宽度且不得产生水平滚动。
服务状态卡的状态图桌面为 56px、窄屏为 50px 圆角方形，图片完整显示；点击后只
展开本机图片设置菜单。正常与需要处理分别共享一张状态图，避免按服务复制素材，
菜单必须键盘可达并保留可见焦点。
收起态 QQ 与通用主组件均为 16px 圆角矩形。B 站参数等业务自有次级头像不受该
主组件尺寸契约影响。
公共折叠发现范围同时包含 main 直属 legacy section 与
`#dashboard-module-mounts > section.section`；动态模块完成 `mount(context)` 后由
loader 触发同一渐进包装，不要求模块复制折叠代码。动态模块卸载只移除自己的根，
遗留的纯 UI 布尔折叠项不触发模块安装、启停或业务请求。
公共包装同时为每个顶层组件建立独立设置入口。入口自动发现组件内
`label.field`、`label.switch-row` 和 `data-setting-label`，只生成定位原控件的
本地导航；模块根可用 `data-panel-settings` 以 `|` 分隔补充无控件说明。设置入口
不得克隆字段、读取值或提交业务表单；具体字段
含义、校验、保存按钮与副作用仍完全由业务模块拥有。没有声明设置的模块保留明确
占位，入口加载失败的隔离卡也继续拥有相同公共按钮。所有设置面板共享“设置本机
图片”与“恢复默认”入口；前者只创建当前安装实例的自定义覆盖，不能修改或提升为
版本化项目默认素材，后者删除覆盖并回退到仓库默认图/空槽。API 仅接受受信本机
请求、有限 panel ID、8MB 内且 MIME 与签名匹配
的 PNG/JPG/WebP，采用受控目录原子替换并返回同源 URL，不暴露绝对路径。普通页面
只读一次素材目录；目录和图片响应必须 `no-store`，前端读取目录也必须绕过 HTTP
缓存，图片 URL 使用 `updated_at` 失效标记，避免上传成功后刷新恢复旧目录。只有
显式上传/恢复才写入/删除。QQ 只能替换既有 start 按钮内
的图片节点，不能改变按钮、事件或 start-only 契约。
卡头本身不得导入 repository、读取个人文件或产生网络副作用；QQ 的卡头只能消费
现有 status/start，不能在没有 stop 契约时表现为双向开关。B 站参数卡继续由
PK-130 拥有参数、凭据和采集规则，PK-100 只提供视觉类和响应式约束。

主题所有权完全位于浏览器 UI 层。`project-kei.dashboard.theme.v1` 只允许
`cloud/sakura/moon`，与既有 `project-kei.dashboard.panel-open.v1` 一样不得承载
模块配置、凭据、名单、缓存或个人状态。主题初始化、切换、刷新恢复和面板折叠
不得调用公共请求封装；存储异常回退到默认主题/默认折叠。颜色由语义 CSS 变量
驱动，卡头需要保留键盘可达、ARIA 状态、`prefers-reduced-motion` 和窄屏无横向
溢出；无 JavaScript 时兼容 HTML 仍保持基本可读。

## 依赖方向

```text
router -> service -> repository
                    -> core 基础设施

dashboard/QQ -> HTTP 接口
其他模块      -> 对方公开 service 契约或 HTTP 接口
```

禁止以下依赖：

- router 直接读写 JSON 状态文件；
- 一个模块直接修改另一个模块的数据文件；
- 为方便而从 `api.py` 导入全局业务对象，形成循环依赖；
- 新接口删除或静默改变现有控制台依赖的返回字段。

## 接口策略

- 新接口使用 `/api/v1/<module>` 命名空间。
- 现有 `/dashboard/*`、`/demon/*`、`/fitness/*` 等路径在迁移期间继续可用。
- 旧接口应调用同一个 service，而不是复制两套业务逻辑。
- 模块目录可通过 `GET /api/v1/modules` 发现；`migration_status` 只描述代码边界迁移状态，不代表用户功能不可用。
- 跨模块字段变化必须先写入对应任务的“接口契约”，再由 `PK-000` 总控确认。

## 数据所有权

每个状态或缓存文件只能有一个负责模块。其他模块需要数据时，通过公开查询方法获取。个人状态、凭证和缓存仍按 `AGENTS.md` 处理；模块化不意味着可以扩大读取或提交范围。

## 渐进迁移

1. 先登记模块目录、任务边界和现有接口。
2. 为模块建立 `models/router/service/repository`，把测试先固定下来。
3. 从 `api.py` 抽离路由，但保留旧路径并调用同一 service。
4. 拆分控制台脚本，保持页面元素 ID 和行为兼容。
5. 完成一个模块后进入“待集成”，由 `PK-900` 做跨模块回归。

不进行一次性目录搬迁或大范围格式化；每个模块单独迁移、单独验证、单独交接。

## 与按需安装的实施顺序

1. 新模块先满足本文的 `router -> service -> repository` 边界，并声明自己的数据所有权。
2. 按可安装模块规范补充 manifest、依赖、前端入口、配置和生命周期声明。
3. 控制台公共外壳只加载已启用模块的面板；旧单页元素 ID 在迁移期间保持兼容。
4. 先用依赖较少的专注计时模块完成端到端试点，再复用机制迁移其他模块。
5. 进程内模块启停通过主 API 装配并在必要时重启 API；QQ bridge、ASR、GPT-SoVITS 继续作为 sidecar 管理。

PK-100 第一阶段已经完成第 4 步的公共层拆分和动态挂载边界；PK-180 已完成首个真实 focus 安装模块联调，其他业务面板仍由各自任务渐进迁移。

## QQ sidecar 的业务消费边界

PK-140 的 Node sidecar 仍只拥有 QQ Gateway/Token/C2C/发送适配、事件去重、定时器与有限投递状态；它不是第五套业务实现。QQ 私聊菜单对 PK-150、PK-170、PK-180、PK-190 的消费只经主 API 已有版本化 HTTP：斩妖 status/goals/checkins/daily review、健身 status/checkins、focus status/start/stop/encouragement、calendar today/status/events/practice。sidecar 不导入 Python feature、不读取 repository 或个人 JSON，也不复制积分、目标周期、妖怪分类、连续天数、计时、日历、修炼或 LLM prompt 规则。

Node 的 action-to-operation 表同时固定 method 与 path；用户输入不能形成 URL、method、header、prompt、命令或文件路径。主/子菜单展示只返回有界 keyboard；业务 mutation 只能由独立明确按钮、严格斩妖添加确认、两条严格日历命令或严格专注/鼓励整数命令触发。斩妖添加只允许固定 cadence 的 recurring 目标：标题先进入最多 10 分钟的用户绑定单次内存确认，按钮 action 只携带不透明 ID，确认后才调用同一个 PK-150 `POST /goals`；Node 不判断妖怪、积分或周期。QQ 不暴露 legacy、reset、奖励兑换、目标编辑/删除、临时目标、`force=true` 或模块生命周期。focus 路由未装配时只返回固定不可用提示，不能由 sidecar 安装、升级、启用或重启模块。专注到期由 Node 先核对公开 active session identity，focus 1.1 composition 再核对同一 repository 并通过 PK-200 稳定 `TextGenerator` 生成；Node 不持有 persona/prompt，主 API 不接触 QQ 身份或 sender，受控生成不写 conversation history。详细交互、安全顺序和失败语义见 [QQ bridge 契约](qq-bridge.md)。

## Focus 首个落地边界

PK-180 已将计时规则迁入 `server/features/focus/`：HTTP 仅在 `router.py`，番茄钟/专注模式、重复启动、停止、完成和恢复只在 `service.py`，JSON 读写只在 `repository.py`。`server/systems/focus_timer.py` 仅保留旧 Python 导入兼容，不再拥有第二套状态机；`server/api.py` 只提供历史状态路径和可选 TTS 回调，再由已启用安装包的 `register(app)` 完成装配。

同一个 router 同时注册 `/api/v1/focus/*` 与 `/focus/*`，因此既有 status/start/stop/reset 共享请求模型、service 和错误行为；1.1.0 只新增版本化、真实 loopback 的 `/api/v1/focus/encouragement`，不增加 legacy 入口。计时响应公开不透明 `session_id`；鼓励接口只接受它与 `start_at`，再次验证 active identity 后使用有限 mode/elapsed/remaining 事实调用 PK-200，不接受任意 prompt/task/QQ 身份且不写 history。focus 未安装、已停用或已卸载时，新启动的 API 不装配这些路由；第一版已经运行的进程不会热移除路由。

动态面板源码位于 `server/features/focus/package_source/dashboard/index.js`，旧 `dashboard.html` 不再包含 focus DOM 或业务函数。面板只操作 `context.root`，只通过 `context.request` 访问 `/api/v1/focus`，`unmount()` 会清理计时器和自己的 DOM；公共加载器继续负责单模块失败隔离。

为保持数据连续性，repository 默认继续使用迁移前实际路径 `server/systems/data/focus_timer.json`，同时把 `server/data/focus_timer.json` 等同名历史文件视为受保护用户数据。PK-180 不读取、移动、合并或自动清除这些文件；测试通过显式 `focus_state_path` 使用临时 store。

## Calendar 内置模块落地边界

PK-190 将日历、备忘、年度重复和修炼累计迁入 `server/features/calendar/`。`models.py` 只定义 HTTP/领域模型，`router.py` 统一装配 `/api/v1/calendar/*` 与 `/calendar/*`，`service.py` 拥有严格日期、年度闰日、未来七天、确定性 ID、重复保护、修炼境界和中文摘要规则，`repository.py` 独占结构校验、同路径进程锁和唯一临时文件原子替换。`server/systems/calendar_memo.py` 仅保留旧 Python 导入兼容，`server/api.py` 只装配 router。

calendar 仍是主 API 内置 `in_process` 模块，不声明 manifest、安装包、生命周期或动态面板。`dashboard.html` 的 legacy calendar DOM 与 `/calendar/*` 调用继续保留，voice pipeline 通过可注入的公开摘要 provider 调用同一 service；二者都不能访问 repository 或状态文件。

默认状态继续位于 `server/systems/data/calendar_memo.json`，不迁移到模块数据 namespace。损坏 JSON、缺失/错误列表结构和原子替换失败必须显式失败，不能用空状态覆盖原文件；所有写入、reset、损坏和并发测试只能显式构造临时 `CalendarMemoStore`。版本化 reset 要求精确确认 `calendar`，旧 reset 只为兼容保留且不在控制台暴露。

## Demon Slayer 内置模块落地边界

PK-150 将目标、打卡、积分、奖励和复盘规则迁入 `server/features/demon_slayer/`。`models.py` 定义版本化与 legacy HTTP 输入和公开打卡结果，`repository.py` 独占状态校验、同路径进程锁、唯一临时文件、`fsync` 与原子替换，`service.py` 独占日/周/月/年周期、妖怪层级、目标生命周期、积分/奖励幂等和事实复盘，`router.py` 同时装配版本化与 legacy 路由。`server/systems/demon_slayer.py` 只保留旧 Python 导入门面，`server/api.py` 只注入默认 repository、PK-200 `TextGenerator` provider 和可选 legacy 音频接缝。

demon_slayer 是随主 API 启动的内置 `in_process` 模块，不声明安装包、manifest、生命周期或动态面板。版本化接口位于 `/api/v1/demon-slayer/*`；原 `/demon/*` 全部委托同一 service。危险的 `POST /demon/reset` 只为兼容保留，没有版本化 reset，也不在控制台暴露。legacy 控制台 DOM 继续由 PK-100 公共外壳承载，但目标读取、新增、编辑、删除、打卡和四类复盘均使用版本化接口，浏览器不保存任何斩妖业务状态。

默认状态继续位于 `server/systems/data/demon_slayer.json`，不自动搬迁、覆盖或重写。旧目标缺少 `repeat_mode` 时按 `recurring` 读取；旧日/周目标和既有 check-in/积分/愿望结构由同一 repository/service 兼容。损坏 JSON 或错误顶层结构明确失败，不能回空后覆盖；写入失败保留替换前字节。所有自动测试必须显式注入临时 `DemonSlayerStore`，不得读取、reset、损坏或 diff 真实个人文件。

目标 ID 在编辑时保持不变。删除是幂等软停用，只影响之后的追踪；打卡、既得积分、兑换和复盘依据继续保留。新 check-in 固化当时的 cadence、周期键、标题和妖怪快照；编辑周期后，旧完成事实仍按原快照进入历史复盘。同一目标同一周期的相同请求只保留一条记录并只发一次积分；未来日期、停用目标和临时目标指定周期之外的打卡会被拒绝。奖励兑换接受可选 `request_id`；相同请求不重复扣分，无 request ID 的 legacy 重试按同一奖励幂等。

check-in 响应直接复用同一 service 的统计纯函数，返回目标启用起点/天数、当前与历史最长连续周期、单位和确定性鼓励。请求模型的 `with_encouragement` 默认为 `false`，保持网页控制台、legacy 与既有消费者零模型副作用；QQ“完成”按钮显式传 `true`，且只有非重复的成功完成才调用一次 PK-200 `TextGenerator`。模型只选择 `warm/strict/playful` 语气 token，不生成或改变事实正文；service 根据已提交的打卡事实组装最终 Kei 文本。生成不可用、失败或返回无效 token 时保留本地鼓励并标记 `kei_generated=false`，不回滚打卡、不重复积分，也不写 conversation history。

`status` 的四个 cadence 分组由同一 service 非破坏性补充常驻统计：`active_since/active_days/current_streak/longest_streak/streak_unit`，`completed` 保持查询周期完成语义。daily、weekly、monthly、yearly 分别按自然日、周一开始的自然周、自然月、自然年推进；查询日所在未闭合周期若未完成不会提前截断已有 streak，已完成则可计入，只有此前已闭合且有效的缺失/`done=false` 周期才重置。重复与乱序 check-in 每周期至多形成一个结果，创建前、未来、停用区间和不同 cadence 的冻结历史不被重新解释为当前连续记录。

启停区间和上述统计只在 `DemonSlayerService`/同文件纯函数中解释，repository 仍只负责结构校验、锁与原子持久化，router 仍只负责 HTTP。`recurring` 有可信时间证据时，`active_since` 从创建日或最新重新启用日开始，`active_days` 首日为 1；旧目标没有目标/全局创建日、合法历史打卡或重新启用日时，两个字段返回 `null`，不使用查询日、进程缓存或写盘迁移制造起点。重新启用切开 current streak，但历史合法启用段继续参与 `longest_streak`；`once` 固定返回 `active_since=null`、`active_days=null` 和两个零 streak。统计只遍历持久化 check-in 与启停段，不按日期跨度枚举全部周期；未来查询只使用截至本机今日的事实。QQ、控制台及后续消费者只能读取版本化 status 字段，不得复制周期、启停或连续规则，也不得增加专用 repository。

日/周/月/年复盘只计算截至本机今日的实际周期，不把未来日期记为未完成。完整周期全清奖励使用持久化 bonus key 幂等提交。Kei 复盘只调用 PK-200 的 `TextGenerator.generate_text()`，输入为完成、未完成、notes、breakdown 和积分事实；模型只返回受限的 `praise`、`criticize` 或 `mixed` 裁决，最终用户文本由本模块根据事实确定性组装，因此模型不能增删目标事实、发积分或修改状态。生成不可用、超时、失败、返回无效裁决或与全成/全败事实冲突时，直接返回确定性的本地复盘并标记 `kei_generated=false`；该调用不写普通 conversation history。

## Conversation 内置模块落地边界

PK-200 将文字对话、进程内 history、只读上下文、受控文本生成、非秘密 LLM profile 和活动 provider runtime 迁入 `server/features/conversation/`。`router.py` 只承载 `/api/v1/conversation`、版本化 history 和 `/api/v1/llm-profile`；`service.py` 负责用例、参数上限和候选切换；`runtime.py` 独占活动 client、history 与并发锁；`repository.py` 只负责 profile 校验和原子持久化；`client.py` 是唯一 OpenAI-compatible HTTP 实现。`server/core/llm_engine.py` 只保留兼容导出，`core/dialogue_manager.py` 是 voice 与既有记忆命令的应用接缝，不再拥有第二套模型或 history。

conversation 是随主 API 启动的必需内置 `in_process` 能力，但本轮不声明 manifest、安装包、生命周期或动态控制台入口。legacy `dashboard.html` 模型面板保持单一 DOM，`/chat`、`/chat/text-only`、`/history*`、`/ws/chat` 与 `/dashboard/llm/profile` 继续存在，并与版本化路由调用同一 service。`/chat` 和 WebSocket 的音频装配仍归 voice 边界。

依赖方向固定为 `PK-001 -> PK-200 -> PK-160`。conversation 只认识 `ConversationContextProvider.get_context() -> str`；默认空实现无需 PK-160 即可启动，当前主应用仅在装配层把既有 `MemoryStore.prompt_context` 包成临时只读 Provider。Provider 失败会降级为空上下文，不返回或记录上下文内容。conversation 不导入记忆/好感 repository，也不读写其数据文件。

`ConversationService.generate_text()` 是 voice、daily briefing、生命维持提醒和斩妖复盘等内部消费者的稳定门面。调用方传入受控 instruction/input/上限和自己的 fallback，返回 `TextGenerationResult(text, generated, fallback, model, error_code)`；它不读取长期记忆、不写普通 chat history，也没有允许外部调用者自定义 system prompt 的 HTTP 接口。消费者始终持有 service，不缓存当前原始 client，因此热切换后下一次调用自然看到新 provider。

history 维持单用户、单主进程、非持久化语义，上限为 20 轮（40 条 user/assistant 消息）。chat 在 conversation 锁内一次性完成并追加完整消息对；超过上限从最旧消息对开始截断。清 history 只清内存，模型切换保留现有 history，API 重启会清空；不增加会话 ID、多用户、数据库或跨进程同步。

profile 只含 `provider`、`base_url`、`model`、`thinking_mode`、`updated_at`，API Key 只在进程环境中交给 client。`provider` 限 `deepseek/custom`，URL 限绝对 HTTP(S)、拒绝 userinfo/query/fragment，`model` 非空且限长，custom 自动关闭 thinking。文件缺失使用环境默认，损坏时只回退且不覆盖原文件；成功 PUT 使用同目录唯一临时文件、`flush/fsync` 和 `os.replace`。

候选测试由独立 client 执行，不接触活动 history。profile 更新串行化；测试成功后在 runtime 操作锁内先原子保存非秘密 profile，再替换活动指针，最后关闭旧 client。chat/生成在同一操作锁内取得并用完 client，因此不会使用已关闭实例。测试、保存或提交前失败会关闭候选并保持旧 client、history、内存 profile 和文件不变；旧 client 关闭失败只记录不含异常详情的警告。timeout、连接/鉴权/限流/5xx、非 JSON、缺少 choices 和空回复均转换为有限错误码，不返回上游正文、headers、系统提示、上下文或异常链。

runtime/service 的关闭是由锁保护的终态。runtime 在操作锁内先标记 closed 并创建唯一 close task，随后重复 close 只等待同一任务；已经进入的 chat/生成会完整结束后再关闭，新调用在接触 client 前确定性拒绝，且不写 fallback history。service 生命周期锁与 chat、生成、probe、profile commit 使用同一提交边界；候选测试不长期持锁，service 会登记当前候选并在 shutdown 时立即启动其唯一关闭任务。测试之后无论成功、失败或取消都只复用该关闭任务，不能保存 profile 或替换活动 client。关闭后的受控生成只返回 `generated=false/error_code=service_closed` 的调用方 fallback，关闭后的 chat/profile update 返回服务不可用且不产生状态副作用。

## Affection Memory 内置模块落地边界

PK-160 将好感度、互动事件、选择结算、显式长期记忆和只读对话上下文迁入 `server/features/affection_memory/`。`models.py` 定义公开 HTTP/领域模型，`repository.py` 分别拥有 relationship 与 memory 两个持久化边界，`service.py` 分别拥有互动规则和记忆增删查/命令/筛选规则，`context.py` 只实现 PK-200 的 `ConversationContextProvider.get_context() -> str`，`router.py` 同时装配版本化与 legacy HTTP，`compatibility.py` 支撑旧 Python 与语音命令接缝。`server/systems/affection_system.py` 和 `server/core/memory_store.py` 只再导出兼容门面，`server/api.py` 只注入现有数据路径、正式 Provider、router 和 legacy text/voice 命令适配。

模块随主 API 运行，是内置 `in_process` 能力，不声明 manifest、安装包、生命周期或新进程。版本化 namespace 为 `/api/v1/relationship` 与 `/api/v1/memories`；`/affection/*`、`/memories*` 继续调用同一 service。危险的 legacy reset/clear 保留但不新增版本化入口或控制台按钮。legacy 控制台 DOM 不迁移，业务请求已切换到版本化 API，且不在 localStorage 保存好感度或记忆。

relationship repository 独占现有 `server/data/affection_state.json`，memory repository 独占现有 `server/data/memories.json`；两者不合并，也不创建或自动迁移 `server/systems/data` 同名候选。repository 不依赖 HTTP、conversation 或对方状态；所有读改写由按规范化路径共享的进程锁串行化，保存采用同目录唯一临时文件、`flush/fsync` 和 `os.replace`。损坏 JSON/结构明确失败，不能回退空状态后覆盖；替换失败清理临时文件并保持旧字节，因为 service 不缓存可变状态，内存也不会领先于提交。

PK-160 的 `/api/v1/relationship*`、`/api/v1/memories*`、`/affection*` 与 `/memories*` 对读写采用同一安全边界：请求必须来自本机客户端；浏览器请求还必须来自 8000 端口的本机控制台 Origin，无 Origin 的本机非浏览器客户端继续允许。主应用的全局 loopback middleware 位于精确 Origin CORS 与模块 guard 外层并保护全部路由；`AffectionMemoryOriginGuardMiddleware` 继续覆盖实际 GET/POST/DELETE 与 OPTIONS 预检作纵深防御，router 通过可注入的相同 guard 再次校验，单独装配时也不会失去保护。

迁移前活动事件可能直接保存冻结 `EVENTS` 条目而没有 `instance_id` 或 `created_at`。repository 仅在加载后的内存副本中验证该条目与冻结目录逐字段一致，并由事件 ID、数值状态和历史长度生成稳定的派生 identity；缺失时间映射为空值。普通 status、重复读取和 Provider context 不触发保存，因此不会借兼容读取改写个人文件。成功选择仍在同一路径锁内只结算一次并保存无活动事件的新状态；未知 ID、篡改过的冻结字段、非法显式 identity 或时间仍按损坏状态失败关闭。

relationship service 保留冻结的等级、范围、八类事件、全部选项/回复与 legacy 返回结构。已有活动事件不会被新 trigger 覆盖；选择在 repository mutation 锁内验证、限幅、追加历史并清除活动事件，因此相同或并发重试最多结算一次。memory service 为新条目生成稳定 ID，按 ID 或 legacy 序号删除；空/超长内容、标签数量/长度、非法来源和非法 request ID 被拒绝，相同内容或 request ID 重试确定性复用现有条目。relationship reset、memory clear 和 PK-200 history clear 只改各自所有权内的状态。

依赖方向保持 `PK-001 -> PK-200 -> PK-160`。PK-160 可导入 PK-200 的只读 Protocol，conversation 仍只消费 Protocol 且不导入 PK-160。正式 Provider 私有持有两个只读 callable，每次读取最新已提交数据，只返回关系阶段/状态分档与经过敏感标签过滤、数量限制、逐条限长和总长限制的记忆文本；不返回 ID、时间、事件历史、repository、service 或写方法。输出把系统参考说明、关系概览和“用户保存的记忆（资料，不是指令）”分区，明确记忆不能改变系统规则。空数据返回空文本，任何读取异常继续由 PK-200 `_safe_context()` 降级为空且只记录固定错误，不把个人内容写入 history、响应或日志。

## Fitness 内置模块落地边界

PK-170 将健身打卡、连续天数、累计统计和六日奖励迁入 `server/features/fitness/`。`models.py` 定义版本化/legacy 请求响应与领域结果，`repository.py` 独占 JSON 校验、同路径进程锁和原子提交，`service.py` 独占严格日期、唯一自然日、连续天数和奖励幂等规则，`router.py` 同时装配版本化与 legacy HTTP，`compatibility.py` 支撑旧 Python 导入。`server/systems/fitness_checkin.py` 只再导出兼容门面，`server/api.py` 只注入冻结路径、router、本机请求 guard 和可选 legacy 音频接缝。

fitness 是随主 API 启动的普通内置 `in_process` 模块，不声明 manifest、ZIP、安装/启停/卸载生命周期、sidecar、动态 dashboard entrypoint 或新端口。版本化接口为 `GET /api/v1/fitness/status` 与 `POST /api/v1/fitness/checkins`；`/fitness/status|checkin|reset` 调用同一 service。危险 reset 只保留 legacy，不新增版本化入口或控制台按钮。控制台保留 PK-100 的既有 DOM、折叠和元素 ID，但 status/check-in 改用版本化接口；业务数据不进入浏览器存储。

唯一生产数据所有权固定为现有 `server/data/fitness_checkins.json`，由 composition root 显式注入。模块不会探测、创建、复制、合并或迁移不存在的 `server/systems/data/fitness_checkins.json`。同一路径所有 repository 实例共享进程锁；写操作在锁内完成读取、规则计算和保存，使用同目录唯一临时文件、`flush/fsync` 和 `os.replace`。替换失败会清理临时文件并保留旧字节；service 不缓存可变状态，因此可见状态不会领先于持久提交。损坏 JSON、错误根结构、异常字段或篡改奖励明确失败，不能作为空状态覆盖；重复/乱序打卡日期按合法唯一自然日计算，非法日期只读忽略。

同日首次提交最多追加一条记录；并发重试返回 `already_checked_in` 且不覆盖最初备注。连续天数从目标日逐日向前计算，断档后重置；每个 6 天倍数生成与既有格式一致的里程碑 key 和 Kei 奖励文本，已有 key 不再发放。状态保留累计唯一日期、最近 14 个打卡日、最近 10 个唯一奖励和 `next_reward_in` 语义。版本化接口只返回业务 JSON，不调用 TTS；仅 legacy `with_audio=true` 且新解锁奖励时，应用层可调用现有本机 TTS。全部 fitness 路由在 repository 前执行本机客户端/可信控制台 Origin 防护，外层 middleware 同样覆盖恶意 OPTIONS 预检。

## Voice 内置模块落地边界

PK-210 将 Provider 协议、ASR → PK-200 conversation → TTS 编排、版本化/兼容路由、结构化降级和请求级音频生命周期迁入 `server/features/voice/`。`router.py` 同时注册 `/api/v1/voice/*` 与 `/voice/*`，两组入口共用 `VoiceService`；`server/services/asr_client.py`、`tts_client.py` 和 `voice_pipeline.py` 仅为旧 Python 导入提供兼容导出。完整协议见 [语音公共契约与编排](voice.md)。

voice 只通过 `ConversationServiceProvider` 调用 PK-200 的公开 `chat()`，不持有 LLM client、profile、prompt 或 history。ASR/TTS/Voice Pack 都是可注入协议，模块导入无网络副作用；PK-211 和 PK-212 后续分别替换引擎与 Pack 适配，不能反向修改编排或互相导入。

PK-211 已将 9880 适配替换为 `providers/gpt_sovits/` 中的稳定 Engine Provider。项目只拥有固定来源描述、PK-210 适配、忽略的本机登记和显式获取事务；外部源码/运行时不进入仓库或 `vendor/`，普通 agent 不扫描安装树。角色权重与参考音频仍完全属于 PK-212。受控获取不是模块生命周期安装，也不会由 API、目录、health 或启动器自动触发；专项协议见 [GPT-SoVITS 外部引擎 Provider 与受控获取](gpt-sovits-engine.md)。

请求音频受 MIME、扩展名、16 MiB 和分块读取限制。合成全部成功后才从请求专属暂存目录原子发布到受控输出根；失败、取消和流式中断删除当前请求的暂存与未完成发布，不触碰其他请求。对外音频字段只返回同源 URL。ASR/对话失败终止链路，TTS/Pack 失败返回明确 `text_only`，详细生命周期、流事件和错误语义由专项文档固定。

## Daily Briefing 内置模块落地边界

PK-110 将 Collector 公共协议、legacy gateway、规范化、汇总/去重、来源覆盖、当天缓存、补采冷却、PK-200 改写和播报稿迁入 `server/features/daily_briefing/`。`router.py` 同时承载 `/api/v1/briefing/*` 与 legacy `/briefing/today*`、`/dashboard/briefing/status|generate`；`service.py` 拥有用例和单一 mutation lock；`generation_status.py` 只拥有进程内、有界、线程安全且不含业务正文的生成阶段/来源进度，版本化状态 GET 与 legacy dashboard status 委托同一 tracker；`repository.py` 独占主缓存/当天播报稿的 Schema、旧缓存只读适配与原子写；`server/services/daily_briefing.py` 只保留兼容导出。完整 Collector 1.0、去重、缓存、生成状态和 API 协议见 [每日情报 Collector、缓存与 Kei 播报契约](daily-briefing.md)。

PK-119 已完成来源批次的事后共享装配。主 API 使用 `source_composition.py` 的 `ProjectCollectorGateway`：X、GitHub、B 站、YouTube、RSS 平台 Collector 经冻结的 `ContractCollectorGateway` 并发隔离，arXiv、Crossref、Semantic Scholar 经 `features/papers/PaperCollectorCoordinator` 串行协调 fallback 与摘要补全。`LegacyCollectorGateway` 和 `server/intel/briefing.py` 只保留旧 Python/脚本兼容，不再拥有主 API 的生产 Collector 注册。

PK-115 的 `features/intel_sources/` 遵守 router → service → repository，独占忽略的个人来源注册表并向 Collector 提供不可变快照。PK-120 的 `features/x_monitor/` 拥有资料、单一 `Asia/Shanghai` 当日兼容缓存和无持久化日期查询 use case 与版本化 router：普通读取、日期选择、结果切换和控制台折叠只消费内存/缓存，只有显式单用户 fetch/query 联网；fetch 与 `day|since` query 复用 service 的同一日期窗口构造函数，旧 dashboard profile/posts 路由委托同一 service，不暴露独立 replies 通道。查询最多覆盖包含本地今天在内的 30 个自然日，Nitter/RSS 只声明 partial best-effort，不补抓父帖或线程。PK-130 的 `features/bilibili/` 拥有资料缓存 use case、三字段 B 站凭据 allowlist、Git 忽略的 active/candidate 双槽原子 store 及版本化/legacy 同 service router；状态读取与候选保存零网络，显式验证并采集成功后才切换 active，失败不改 PK-110 今日缓存。PK-131、PK-132、PK-133、PK-134 是无独立 HTTP 管理面的进程内 source adapter，分别拥有 YouTube、GitHub、论文和固定 RSS 的解析、限流、失败与安全边界。所有 Collector 只依赖 `collector_contracts.py`/`models.py`，不能导入 PK-110 service/repository/router。

普通版本化 GET、控制台状态和 QQ `fetch=false` 查询只读 repository，不触发 Collector、PK-200 或 PK-210。显式 generate 在没有有效缓存时采集，显式 refresh 覆盖当天主缓存；失败/partial 来源只在 retry_after 与本地冷却到期后单独补采。Kei 改写只用 PK-200 `TextGenerator`，播报音频只经 PK-210 Provider/Resolver/ArtifactStore 公共契约，音频不进入 briefing 缓存。

## QQ Control 与 Node sidecar 落地边界

PK-140 在主 API 中建立 `server/features/qq_control/` 的 models/repository/service/router 分层。router 同时注册 `/api/v1/qq-control/*` 和既有 dashboard 控制/日程路径；service 独占固定 launcher readiness、并发 start 和两类日程规则；repository 独占两份 schedule JSON 的损坏失败与原子替换。`server/services/qq_bridge_control.py` 只保留生产 composition/兼容 facade，`api.py` 只装配 middleware/router 并在总状态中读取同一 service。

QQ 私聊、token、Gateway、reconnect、消息去重、Markdown、定时器和投递状态仍全部位于独立 `server/qq_bridge/` Node sidecar；不进入 FastAPI，也不新增端口。Node 普通文字调用 PK-200 版本化 conversation，预生成/缓存发送调用 PK-110 版本化接口，生命维持只用既有受控生成接缝。完整协议见 [QQ bridge、主 API 控制与定时推送契约](qq-bridge.md)。
