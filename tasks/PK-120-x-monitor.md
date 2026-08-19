# PK-120 — X/Nitter 用户资料与今日言论

- 状态：已完成
- 优先级：P1
- 所属模块：`x_monitor`
- 依赖任务：PK-001、PK-010、PK-100、PK-110、PK-115
- 负责路径：`server/services/x_profile_cache.py`、`server/services/x_daily_posts.py`、`server/services/x_daily_cache.py`、`server/intel/collectors/twitter.py`、`server/features/x_monitor/**`、`server/tests/test_x_*.py`、本任务文件；实现阶段可对 `server/api.py`、`server/static/dashboard.html`、`server/static/dashboard/**`、`server/features/catalog/service.py`、`README.md` 和相关架构文档做本任务所需的最小兼容修改
- 当前对话：2026-08-01 PK-000 授权的 FxEmbed API v2 后备与一层直接父帖上下文增量
- 最终关闭：2026-08-02 PK-900 对 PK-100 + PK-120 累计候选完成独立验收；固定 FxEmbed 后备、最多一层直接父帖、单缓存、发帖/回复本地分栏、确定性 `x_monitor@1.1.0` 包及 Catalog 一致性全部通过。PK-000 复核后将本任务置为“已完成”。
- 并行阶段交接状态：历史来源批次已经完成；本轮为 PK-120 单任务增量，不再受当时“共享集成待排队”限制

## 并行批次授权（2026-07-22）

- 共同依赖为 `docs/architecture/daily-briefing.md` 已冻结的 Collector `1.0`；需要改变契约时立即停止并交回 PK-000。
- 并行阶段只修改上述负责路径。API、legacy briefing、旧控制台、catalog、README、架构文档及来源注册表均留到总控串行窗口或 PK-115。
- 真实 X 资料/今日言论缓存、用户名单与 Nitter 网络不用于自动测试；PK-140 不属于本批。

## 目标

独立管理 X 用户资料缓存、单用户今日言论缓存和 Nitter 采集适配。

## 阶段约束

- PK-110 已通过最终复核，Collector `1.0` 已冻结，本任务已由 PK-000 统一领取。
- 与 PK-115、PK-130～PK-134 是同一后续并行批次；只实现 X/Nitter 适配，不修改 PK-110 内部汇总或其他来源。

## 接口契约

- 当前接口：`/dashboard/intel-sources/x-profiles/resolve`、`/dashboard/intel-sources/x-posts*`
- 目标命名空间：`/api/v1/x`
- 向每日情报模块提供规范化帖子，不直接生成总播报。

## 数据所有权

- `server/data/x_profiles.json`
- `server/data/x_daily_posts.json`

## 验收标准

- 只按单个账号显式获取，跨天自动清空，成功资料默认复用。
- 控制台逐用户折叠和展开行为保持兼容。

## 并行实施交接（共享集成待排队）

### 1. 实际导出的 Collector / 接口

- `server/intel/collectors/twitter.py` 导出 `NitterCollector`，固定
  `source_id="twitter"`，直接实现冻结的 `Collector.collect(CollectRequest) ->
  CollectorResult`。只导入 PK-110 的 `collector_contracts.py`、`models.py` 与公共时区
  工具，不导入 gateway、service、repository 或 router。
- Collector 从只读快照读取 `twitter_users` 与 `money_twitter_users`，账号按大小写
  去重；同一账号可以同时属于两个配置组，规范化 `IntelItem.metadata.x_config_groups`
  保留全部真实组名。条目使用 `social` 分类、`twitter` source ID、上游 status ID/
  规范 URL 生成稳定 ID，并按 `lookback` 排除过旧和超过当前时间 5 分钟的条目。
- Collector 区分 `complete/partial/empty/failed/not_configured`，失败只公开有限计数、
  脱敏 detail 与 `retry_after`；不返回响应正文、异常正文、Header 或凭证。
- 保留并强化 legacy `fetch_twitter`，另导出 `fetch_x_profile`、
  `fetch_x_daily_posts`；三者均支持注入 `httpx.AsyncClient`，专属测试使用
  `httpx.MockTransport`。
- `server/features/x_monitor/` 导出 `XMonitorService`、`XTarget`、
  `classify_x_targets` 与 `build_router`。service 只消费调用方传入的非秘密来源快照，
  不读取或拥有 PK-115 注册表。
- 路由工厂提供 `POST /api/v1/x/profiles/resolve`、`GET /api/v1/x/posts`、
  `POST /api/v1/x/posts/fetch`，带本机与浏览器 Origin 边界。并行阶段只定义路由，
  未在共享 `server/api.py` 装配，因此当前运行中 API 仍只有既有 legacy 路径。

### 2. 专属修改路径

- `server/intel/collectors/twitter.py`
- `server/services/x_profile_cache.py`
- `server/services/x_daily_posts.py`
- `server/features/x_monitor/__init__.py`
- `server/features/x_monitor/models.py`
- `server/features/x_monitor/service.py`
- `server/features/x_monitor/router.py`
- `server/tests/test_x_monitor.py`
- `tasks/PK-120-x-monitor.md`

未修改 `TASKS.md`、README、AGENTS、API 装配、dashboard、catalog、PK-110 内部实现或
任何共享架构文档；未读取或写入真实 `x_profiles.json`、`x_daily_posts.json`、来源名单、
Cookie、Token、API Key 或其他本机缓存。

### 3. 测试结果

- `server/.venv-asr/Scripts/python.exe -m py_compile` 对上述专属 Python 代码与测试通过。
- `server/.venv-asr/Scripts/python.exe tests/test_x_monitor.py` 通过：覆盖 MockTransport
  资料/帖子解析、URL 凭证 query 清洗、单用户抓取、成功资料复用、失败 6 小时冷却、
  普通/信息差双分类、Collector partial/not_configured 与序列化、跨天清空、版本化路由、
  非本机 Origin 阻断；全部缓存位于系统临时目录。
- 尝试运行 `test_intel_source_config.py` 与 `test_daily_briefing_module.py`，两者在导入
  本批并行的未跟踪 `server/features/bilibili/__init__.py` 时因 Python 3.8 不支持其运行时
  `list[str]` 注解而提前失败，尚未进入 X/PK-110 测试代码。该文件不属 PK-120，未越权
  修改；PK-120 自身 legacy X helper 已由专属测试覆盖。
- 已跟踪的 `server/intel/collectors/twitter.py` 执行 `git diff --check` 未报告空白错误；
  专属新增文件尾随空白扫描无匹配。

### 4. 串行窗口需要写入共享文件的内容

- `server/api.py`：装配 `build_router(XMonitorService(...), source_config_loader)`；让三个
  legacy `/dashboard/intel-sources/x-*` 路由委托同一个 service，保持当前响应和本机保护。
- `server/static/dashboard.html`：把 X 资料/今日言论请求迁到 `/api/v1/x/*` 或确认继续走
  legacy 委托；必须保持普通 X/信息差 X 分组、逐账号详情折叠、只展开刚刷新账号、打开
  控制台不批量采集。并行阶段禁止修改，故只记录需求。
- `server/features/catalog/service.py`：登记 `x_monitor` 的实际版本化和 legacy endpoint、
  `main-api/in_process` 边界、本地资料/今日缓存所有权、显式 Nitter 网络副作用和降级语义。
- `README.md`：补充 `/api/v1/x/*`、`NitterCollector` 已按 Collector 1.0 实现及
  `tests/test_x_monitor.py` 验证命令；现有资料/今日言论说明可保留。
- `docs/architecture/daily-briefing.md` 与 `docs/architecture/modular-monolith.md`：记录
  PK-120 只依赖冻结 models/contracts、`twitter` source ID 下保留
  `x_config_groups`，以及 x_monitor cache/service/router 边界。无需改变 Collector 1.0。
- Collector 装配：在总控选择的共享 composition root 中注册 `NitterCollector`；其他来源
  尚未全部迁出 legacy 时，可暂时继续使用已兼容的 `fetch_twitter`，不得让 PK-120 反向
  导入 `LegacyCollectorGateway` 或 PK-110 内部 service/repository/router。
- `TASKS.md`：仅由总控在串行窗口同步状态；本对话按明确禁令不修改。

### 5. 公共契约结论

不存在 Collector 1.0 公共契约问题，也不需要新增/修改冻结字段。普通 X 与信息差 X 的
分类通过允许的 `IntelItem.metadata.x_config_groups` 表达；共享集成只涉及 composition、
路由/catalog/UI/文档装配。当前状态不是“待集成”，而是**共享集成待排队**。

## 独立对话启动提示

```text
仅在 PK-110 已完成且 Collector 契约冻结后领取 PK-120。只处理 X 资料、今日
言论和 Nitter Collector；每日情报汇总交给 PK-110，来源配置注册表交给 PK-115，
公共契约变化先交 PK-000。
```

## PK-119 事后复核与共享收口（2026-07-22）

- 复核确认 `NitterCollector`、资料缓存、今日言论缓存、`XMonitorService` 与版本化 router 均按上文接口工作；生产 API 已装配 `/api/v1/x/profiles*`、`/api/v1/x/posts*`，旧 `/dashboard/intel-sources/x-*` 路径委托同一 service。
- 控制台已切换到版本化接口，普通 X 与信息差 X 仍由只读配置分组区分。网络只在显式 resolve/fetch 或 PK-110 采集时发生；真实用户名、资料/帖子缓存和凭证未读取或纳入差异。
- `NitterCollector` 已通过统一 `ProjectCollectorGateway` 注册到 `twitter`，单源失败仍由 Collector `1.0` 隔离；catalog、README 和架构文档已同步。`test_x_monitor.py`、`test_intel_sources_integration.py` 及共享回归通过。
- 原并行记录中的 Bilibili Python 3.8 导入阻断已关闭。遗留事项仅为 PK-900 独立验收、真实部署重启及运行环境自身的 Nitter 可用性。

## PK-011 生命周期整改（2026-07-31）

- `x_monitor@1.0.1` 为本次实际新增路由、service 与 twitter Collector 记录实例身份，
  `unregister(app)` 只移除本实例对象；注册中途失败同步回滚部分路由和 Collector。
  正式包 loader/coordinator 回归覆盖重复 unregister 与零残留。

## 完成文档门禁

- [x] TASK_RECORD — 已按实际代码补记版本化/legacy 接口、缓存副作用、装配、验证与遗留。
- [x] TASKS_BOARD — PK-120 已由 PK-000 统一登记为“待集成”。
- [x] PUBLIC_README — 已登记 X 资料、今日言论和 Collector 能力。
- [x] MODULE_CATALOG — 已登记 `x_monitor` 的接口、缓存、网络与降级边界。
- [x] ARCHITECTURE_DOCS — 已登记 `twitter` 生产装配与模块边界。
- [x] LOCAL_README — 不适用；未改变本机路径、端口或解释器约定。
- [x] AGENT_RULES — 不适用；未改变长期 agent 规则。
- [x] VALIDATION — `test_x_monitor.py`、PK-119 集成及共享回归通过；最终差异检查由 PK-119 记录。

## PK-000 最终复核（2026-07-22）

PK-900 报告及实际只读 profile/posts 零网络、显式刷新、Origin 和临时缓存回归经独立复核通过；PK-120 置为“已完成”。

## PK-900 逆向退回整改（2026-07-22）

- 新增 `get_x_profiles()`、`XMonitorService.read_profiles()` 和 `GET /api/v1/x/profiles`：只读取并净化现有缓存，`fetched=0`，不调用 Nitter、不写缓存。
- dashboard 打开和来源增改删改走上述只读入口；只有用户显式点击单条“刷新资料”才调用 resolve。未缓存资料不再自动查询。
- `test_x_monitor.py` 用临时 cache 和计数 fake 验证 resolve 前后只读请求均零新增网络调用；`test_dashboard_shell.py` 验证打开/CRUD 不包含隐式 X/B resolve。
- PK-120 保持“待集成”，等待 PK-900 原逆向夹具复验，不在本任务中宣告批次通过。

## 2026-07-23 发帖/回复分流增量

### 任务定位与兼容基线

- 本轮继续使用 PK-120，不创建 PK-121，也不拆成另一个独立功能任务。此前已通过验收的用户资料、头像、昵称、来源分组、逐用户折叠、只读页面加载、显式单用户采集、Origin 防护、敏感信息清洗、Collector `1.0` 和新旧 API 是累计回归基线，不因重新打开任务而作废。
- 本轮只扩展 X/Nitter 今日内容的分类、独立缓存、显式操作和控制台展示；不修改 PK-110 的 Collector `1.0` 公共模型、来源注册表所有权、每日情报缓存或其他来源模块。
- 在 `x_monitor` 页面和配置链路中，只有用户点击某个账号的“获取今日发帖”或“获取今日回复”才允许调用对应的 Nitter fetcher。PK-110 自身已有的显式情报生成/刷新流程仍按冻结 Collector 契约运行，不由普通 X 面板读取或配置保存暗中触发。

### 内容分类规则

采集适配必须先根据当前 Nitter 条目的明确结构和标记判型，再决定进入哪个缓存；不得仅凭正文以 `@` 开头、中文文案或猜测进行分类。

| 类型 | 判定与归属 |
|---|---|
| 原创帖 `post` | 由受关注用户发布，且没有 reply、repost/retweet 或 quote 的明确结构标记；进入“发帖”缓存。 |
| 回复 `reply` | 由受关注用户自己写出，并具有明确的回复关系标记；只把该用户写出的回复正文放入“回复”缓存。可以保存被回复者的规范化 `@username`、回复时间和当前回复自身的链接。 |
| 转发 `repost` | 具有 repost/retweet 明确标记且没有受关注用户独立撰写正文；不进入“发帖”或“回复”缓存，不在两个栏目展示。 |
| 引用帖 `quote` | 受关注用户写有独立正文并引用另一条状态；作为“发帖”的子类型进入发帖缓存，标记 `kind=quote`。不得为补全引用内容额外请求被引用帖、作者资料或线程；缓存不保存引用帖完整正文。 |
| 无法判断 `unknown` | 缺少可靠类型标记、结构互相冲突或解析器无法确定；不进入发帖/回复展示缓存。只允许在本次采集结果中增加有限的跳过计数或固定 warning，不返回原始 HTML、猜测类型或敏感上游内容。 |

- 判定优先级为明确 reply 关系、明确 repost/retweet、明确 quote、原创帖；互相冲突时按 `unknown` 失败关闭，不得让同一条内容同时进入发帖和回复。
- 回复采集不得额外获取父帖正文、父帖完整对象、引用内容、祖先状态、上下文会话或整条线程；也不得把父帖正文混入摘要、缓存、API 响应或控制台。
- 回复允许公开的关系字段仅限当前回复自身的稳定 ID/链接、受关注用户自己的回复正文、回复时间和被回复者的规范化用户名。缺少被回复者用户名不应触发补抓；该字段可为空。

### 版本化与兼容接口

- 保留并继续使用：
  - `GET /api/v1/x/profiles`：只读资料缓存，零网络、零写入。
  - `POST /api/v1/x/profiles/resolve`：既有显式资料获取。
  - `GET /api/v1/x/posts`：只读当天发帖缓存，零网络、零写入。
  - `POST /api/v1/x/posts/fetch?username=<handle>`：只显式采集该用户当天发帖。
- 新增目标接口：
  - `GET /api/v1/x/replies`：只读当天回复缓存，零网络、零写入。
  - `POST /api/v1/x/replies/fetch?username=<handle>`：只显式采集该用户当天回复。
- 现有 `/dashboard/intel-sources/x-profiles*`、`/dashboard/intel-sources/x-posts*` 的路径、方法、主要响应字段和错误语义必须兼容，并继续委托同一 `XMonitorService`。legacy posts 接口只映射发帖通道，不得因兼容入口而隐式抓取回复；新回复功能优先使用版本化 `/api/v1/x/replies*`，不要求复制第二套业务规则。
- 发帖和回复响应必须能让控制台区分 `post`、`quote` 与 `reply`，但不得暴露 Nitter 原始 HTML、上游错误体、Cookie、Token、内部绝对路径或完整父帖/线程对象。

### 缓存与数据所有权

- 既有 `server/data/x_profiles.json` 继续只保存用户资料；`server/data/x_daily_posts.json` 明确只拥有当天发帖。
- 回复使用独立 repository 和独立本地状态路径，目标为 `server/data/x_daily_replies.json`。该文件与现有 X 缓存一样属于本机运行数据，不进入 Git，不用于真实数据测试。
- 两类缓存必须分别按日期和用户管理、分别原子写入。获取/刷新发帖只能替换目标用户的当天发帖，获取/刷新回复只能替换目标用户的当天回复；任一类成功、空结果、解析失败、网络失败或保存失败都不得覆盖另一类。
- 同一类的单用户刷新不得覆盖其他用户。原子保存失败保留该类旧字节；跨天读取不展示昨日内容，但普通读取不得以“清理旧数据”为由产生写入或联网。
- 不读取、打印、迁移、格式化或用测试修改真实 `x_profiles.json`、`x_daily_posts.json`、`x_daily_replies.json`、来源名单或任何凭证。所有测试显式注入临时 profile/posts/replies 路径与 MockTransport/fake fetcher。

### 控制台契约

- 每个用户保留昵称、头像、来源分组和原有折叠行为，并提供两个相互独立的显式按钮：“获取今日发帖”和“获取今日回复”。
- 用户内容区域提供“发帖 / 回复”切换按钮；同一时间只展示一个栏目。切换栏目、展开/折叠用户、普通页面初始化和刷新视图都只能读取已经加载或通过只读 GET 返回的缓存，不得调用任何 fetch/resolve 接口。
- 保存、添加、编辑或删除 X 来源配置不得解析资料、抓取发帖或抓取回复；资料仍只由既有显式“刷新资料”操作获取。
- 点击某类获取按钮时只禁用/更新该用户对应按钮和栏目，不得批量采集其他用户，不得自动切换或清空另一栏目。失败时保留两个栏目既有缓存并显示有限错误。
- 浏览器存储仍只允许保存折叠/栏目选择等 UI 布尔或枚举状态，不得保存用户名单、资料、帖子、回复、缓存正文或凭证。

### 累计验收标准

- 原有 PK-120 专项测试和来源集成/控制台回归继续全部通过；旧版本化与 legacy profile/posts API、用户昵称、头像、来源分组、折叠和显式资料刷新保持兼容。
- MockTransport fixture 同时覆盖原创帖、明确回复、纯转发、引用帖、冲突标记和 unknown；断言分类互斥、纯转发/unknown 被排除、引用帖进入发帖并且回复只包含受关注用户自己的文字。
- 使用请求计数器证明：读取 profiles/posts/replies 缓存、普通 dashboard load、栏目切换、展开用户以及来源配置增改删均为零 Nitter/外部网络；两个显式获取操作各自只调用一次对应 fetcher。
- 使用会在父帖、线程或额外 URL 请求时立即失败的 fake transport，证明回复采集不会补抓父帖正文、引用状态或会话线程；响应和缓存只含允许的回复关系元数据。
- 使用两个独立临时缓存验证 posts 刷新不改变 replies 字节、replies 刷新不改变 posts 字节、单用户不覆盖其他用户、跨天不展示旧内容，以及任一原子保存失败保留两类原有状态。
- 同一用户同一内容的稳定 ID、当天重复获取去重、时间边界、空正文、缺失链接/被回复者、恶意 URL query、超长正文、损坏缓存和 Nitter 失败均有确定性回归；错误信息不泄露上游正文、Header、凭证或本机路径。
- Collector `1.0` 指纹与 `twitter` source ID 保持不变；如实现需要改变冻结契约或 PK-110 公共语义，必须停止并交回 PK-000，不得在 PK-120 内自行扩张。
- 完成后重新运行包含新旧行为的完整 PK-120 专项测试、来源集成、daily briefing、feature catalog、dashboard shell、相关 Python/JavaScript 检查、文档门禁和 `git diff --check`，再将任务交回“待集成”；不得依据 2026-07-22 的旧验收直接恢复“已完成”。

### 本轮非目标

- 不新增 PK-121，不制作安装包或新增常驻进程/端口。
- 不增加父帖/线程抓取、转发详情、引用帖全文补全、全历史同步、搜索、通知推送或浏览器端业务缓存。
- 不改变来源注册表、PK-110 缓存/汇总/Kei 改写、QQ 推送或其他 Collector 的所有权和公共契约。
- 本轮登记阶段不实现代码、不读取真实缓存、不联网、不运行真实 Nitter，也不执行 Git 暂存、提交或推送。

### 本轮实施记录（2026-07-23）

#### 实际导出与接口

- `server/intel/collectors/twitter.py` 保留 `NitterCollector`、`Tweet`、
  `fetch_twitter()`、`fetch_x_profile()` 和 `fetch_x_daily_posts()`，新增
  `fetch_x_daily_replies()`。Collector 仍直接实现冻结的 Collector `1.0`，
  `source_id=twitter` 不变；`post`、`quote`、`reply` 只通过既有
  `IntelItem.metadata` 表达分类。
- `XMonitorService` 新增 `get_daily_replies()` 与 `fetch_daily_replies()`；
  router 新增 `GET /api/v1/x/replies` 和
  `POST /api/v1/x/replies/fetch?username=...`。既有 profile/posts 版本化和
  dashboard legacy 接口未删除，legacy posts 仍只映射发帖。
- `services/x_daily_cache.py` 提供发帖/回复共用但按 channel 严格隔离的原子
  repository；`services/x_daily_posts.py` 保留旧 Python 门面，
  `services/x_daily_replies.py` 提供独立回复门面。回复运行数据固定为忽略的
  `server/data/x_daily_replies.json`。

#### 分类、缓存与控制台结果

- 发帖与回复 RSS 都访问 `<instance>/<handle>/rss`，再按分类分别筛选。
  标题的明确 `R to @...:` /
  `RT by @...:` 和描述的 quote block 用于互斥判型；冲突或不完整 marker
  归入 `unknown`。纯转发和 unknown 不进入两个缓存，引用块在形成
  `quote` 正文前移除，回复关系块在形成 `reply` 正文前移除。
- 发帖和回复 repository 拥有独立日期、顶层更新时间、逐用户获取时间和原子
  文件。普通读取遇到缺失、损坏或跨天缓存只返回当天空视图，零网络且零写入；
  显式刷新只替换目标用户/目标 channel，失败保留两份旧缓存字节。
- 控制台为每个用户提供“获取今日发帖”“获取今日回复”及“发帖 / 回复”
  segmented control。同一用户只渲染当前栏目；用户键控的 Map/Set 分别维护
  Tab 和折叠状态，按钮 loading 只作用于被点击元素。切换、折叠、初始化、
  只读缓存、来源 CRUD 都不调用 fetch/resolve。

#### 专属与共享修改路径

- 专属实现/测试：
  `server/intel/collectors/twitter.py`、`server/services/x_daily_cache.py`、
  `server/services/x_daily_posts.py`、`server/services/x_daily_replies.py`、
  `server/features/x_monitor/service.py`、`server/features/x_monitor/router.py`、
  `server/tests/test_x_monitor.py`。
- 兼容接线/回归：
  `.gitignore`、`server/static/dashboard.html`、
  `server/static/dashboard/shell.css`、`server/features/catalog/service.py`、
  `server/tests/test_dashboard_shell.py`、
  `server/tests/test_intel_sources_integration.py`。
- 用户与架构文档：
  `README.md`、`docs/architecture/daily-briefing.md`、
  `docs/architecture/modular-monolith.md`、`TASKS.md`、本任务文件。
- 未读取、迁移或修改真实 X 资料/发帖/回复缓存、关注名单或凭证；未执行真实
  X/Nitter 采集，也未修改 PK-110 冻结 models/contracts。

#### 验证结果

- `tests/test_x_monitor.py` 通过：MockTransport 同时覆盖 post/reply/repost/
  quote/conflict/unknown、正文隔离、禁止父帖/线程请求、query 清理、日期边界、
  缺链接/目标、空描述、超长正文、稳定 ID/去重、损坏/跨天零写入、双缓存字节
  隔离、原子失败和单用户失败。
- `tests/test_intel_source_config.py`、
  `tests/test_intel_sources_integration.py`、
  `tests/test_daily_briefing_module.py`、
  `tests/test_daily_briefing_summary_cache.py`、
  `tests/test_feature_catalog.py`、`tests/test_dashboard_shell.py` 全部通过。
  dashboard shell 同时执行内联 JavaScript 语法检查，并静态证明 Tab 切换零 API、
  两个按钮只引用各自 fetch endpoint、获取后不自动切换另一栏目。
- 本地只读 preview 使用完全离线的 Alice/Gap fixture 完成浏览器交互检查：两个获取
  按钮同时可见，Alice 展开后默认只显示发帖；切换“回复”后只显示 Alice 自己的回复
  和 `@Bob` 关系元数据，Alice 保持展开而 Gap 保持收起，验证逐用户状态隔离。
- 相关 Python 文件 `py_compile` 通过；`scripts/check_task_docs.py` 通过；
  `git diff --check` 通过。所有 cache 测试显式使用系统临时目录和 fake fetcher。
- 公共契约问题：无。Collector `1.0` 指纹、`twitter` source ID、PK-110 API 与
  缓存所有权均不需要改变。

### 本轮重新打开后的完成文档门禁

- [x] TASK_RECORD — 已记录实际分类、接口、缓存副作用、路径、测试与契约结论。
- [x] TASKS_BOARD — 已同步为“待集成”，未标记最终完成。
- [x] PUBLIC_README — 已同步双按钮、双缓存、零网络读取和父帖/线程限制。
- [x] MODULE_CATALOG — 已同步 replies endpoint、独立缓存与网络副作用。
- [x] ARCHITECTURE_DOCS — 已记录分类、缓存和 Collector `1.0` 不变边界。
- [x] LOCAL_README — 不适用；本机路径、端口、解释器和启动位置均未改变。
- [x] AGENT_RULES — 不适用；长期工作流、安全和验证规则均未改变。
- [x] VALIDATION — 新旧专项、来源集成、daily briefing、catalog、dashboard、
  Python/JavaScript、文档门禁和差异检查均已通过。

本任务停在“待集成”，由 PK-900 执行独立验收；本轮不宣告最终完成。

### PK-900 累计重新验收（2026-07-23）

**结论：通过。** 本节是 PK-120 当前唯一有效的累计验收结论，覆盖原用户资料、
昵称、头像、今日言论及新增发帖/回复分流，并取代上方实施交接时的“待集成”
结论；不把原能力和新增能力拆成两份独立验收。

- 独立源码审计确认 `post`、`reply`、`repost`、`quote`、`unknown` 互斥；
  回复仅保留当前用户正文和有限关系字段，适配器只请求用户 RSS，不补抓父帖、
  引用状态或完整线程。两个控制台按钮分别只调用 posts/replies fetch，普通
  profiles/posts/replies GET、页面加载、Tab/折叠和来源配置保存均不触发采集。
- 发帖与回复使用不同文件和 repository；逐用户替换、当天去重、跨天空视图、
  损坏状态只读失败和原子替换失败保留旧字节均通过临时目录回归。控制台每次
  只渲染一个栏目，Tab、折叠和按钮 loading 均按用户键隔离；昵称、头像、来源
  分组、显式资料刷新和 legacy dashboard posts API 保持兼容。
- 验收主动发现并在 PK-120 最小范围修复两项兼容缺口：同一天的旧 Schema 1
  发帖缓存现可只读归一化为 `post` 且不改写原文件；显式
  `class="quote"`/`class="quoted-tweet"` 引用块会与 `<blockquote>` 一样在
  缓存前剥离，避免被引用正文混入当前用户文字。相应 fixture 已加入
  `test_x_monitor.py`。
- Collector `1.0`、`source_id=twitter`、PK-110 公共模型和其他来源所有权均未
  修改。Catalog 已登记版本化 replies API，主应用 method/path 无重复；其他
  七类来源和 daily briefing 回归均通过。

实际验证命令与结果：

- `server/.venv-asr/Scripts/python.exe server/tests/test_x_monitor.py`：通过。
- `test_intel_source_config.py`、`test_intel_sources_registry.py`、
  `test_bilibili_collector.py`、`test_bilibili_feature.py`、
  `test_youtube_collector.py`、`test_github_intel_collector.py`、
  `test_papers_collectors.py`、`test_rss_intel_collector.py`、
  `test_intel_sources_integration.py`：全部通过。
- `test_daily_briefing_module.py`、`test_daily_briefing_summary_cache.py`、
  `test_feature_catalog.py`、`test_dashboard_shell.py`：全部通过；后两项覆盖
  route 唯一性、Catalog、双按钮/双 GET、Tab 零 fetch 与内联脚本语法。
- 对 PK-120、Catalog、`api.py` 和相关测试执行 `python -m py_compile`：通过。
  `server/static/dashboard/` 六个 `.js` 逐文件 `node --check`：全部通过。
- `server/.venv-asr/Scripts/python.exe scripts/check_task_docs.py` 与
  `git diff --check`：报告收口后通过。

数据隔离与排除：

- 所有 HTTP 使用 `MockTransport`/`ASGITransport`，所有 cache 写入、损坏、
  Schema 1 兼容和原子失败均使用系统临时目录与 fake fetcher；没有运行真实
  X/Nitter 或其他来源采集。
- 未读取、打印、迁移或修改真实 `x_profiles.json`、`x_daily_posts.json`、
  `x_daily_replies.json`、`intel_sources.json`、`.env`、Cookie、Token 或个人
  状态。工作区中的 `vendor/`、`demon_slayer.json`、`focus_timer.json` 及其他
  非 PK-120 修改均排除，未清理或覆盖。
- 未执行 Git 暂存、提交或推送。部署本批代码后需重启主 API；不需要新增进程、
  端口或本机路径配置。

### 累计验收完成文档门禁

- [x] TASK_RECORD — 已写入累计范围、两项最小修复、命令、结果、隔离、风险和结论。
- [x] TASKS_BOARD — PK-120 已按用户授权恢复为“已完成”，名称、P1 与依赖不变。
- [x] PUBLIC_README — 已核对并补充双通道、零网络读取和 Schema 1 只读兼容。
- [x] MODULE_CATALOG — replies endpoint、namespace、数据所有权和网络副作用一致。
- [x] ARCHITECTURE_DOCS — 已补充两种引用块剥离与 Schema 1 只读兼容边界。
- [x] LOCAL_README — 不适用；本机路径、启动器、解释器和端口均未改变。
- [x] AGENT_RULES — 不适用；工作流、安全、验证、文档和 Git 规则均未改变。
- [x] VALIDATION — 专项、八源、daily briefing、Catalog、dashboard、Python、
  JavaScript、文档门禁和差异检查均通过，且全部使用 fake/临时数据。

## 2026-07-24 公共回复源诊断与回退

用户授权对公开账号 `@thsottiaux` 的 RSS 做只读诊断。未保存正文、未写入真实缓存，
也未跟随任何帖子链接。实际结果表明：

- `nitter.net/<handle>/rss` 返回 200 和 20 条记录，其中存在历史回复标记，但最新
  条目停在北京时间 2026-07-23，缺少用户已确认存在的 2026-07-24 回复。
- `nitter.net/<handle>/with_replies/rss` 返回 403。
- Nitter 官方清单中的五个公共实例对相同两个 feed 的抽查均返回 403、502 或
  1971 年占位数据，没有可用的当日回复源。
- 官方 X API 已改为按读取资源收费；零 API 费用的自建 Nitter/Twikit 都要求真实
  X 账号会话，属于非官方接口，并有风控、失效与封号风险。

按用户授权，撤销专用 `with_replies/rss` 路由尝试并恢复原降级实现：发帖和回复
按钮都只请求普通 `/<handle>/rss`，随后按 `post/quote/reply` 分类分别写入独立
缓存。该版本不会因为公共实例禁用回复 RSS 而直接 403，但只能识别普通 RSS
实际提供的回复；空结果不代表 X 上确实没有回复。

回退没有改变双按钮、双缓存、按用户折叠、发帖/回复切换、版本化 API、零网络
普通读取、父帖/线程禁止抓取或 Collector `1.0`。PK-120 保持累计“已完成”。

验证结果：

- `server/.venv-asr/Scripts/python.exe server/tests/test_x_monitor.py`：通过。
- `python -m py_compile server/intel/collectors/twitter.py server/tests/test_x_monitor.py`：通过。
- `server/tests/test_intel_sources_integration.py`：通过。
- `server/tests/test_daily_briefing_module.py`：通过。
- 文档门禁与 `git diff --check`：通过。

### 公共回复源诊断文档门禁

- [x] TASK_RECORD — 已记录公开源诊断、限制、回退行为和剩余风险。
- [x] TASKS_BOARD — PK-120 保持“已完成”；接口、优先级和依赖不变。
- [x] PUBLIC_README — 已写明普通 RSS 降级和“空结果不等于没有回复”的限制。
- [x] MODULE_CATALOG — 不适用；模块 ID、API、namespace、数据所有权和进程边界不变。
- [x] ARCHITECTURE_DOCS — 已同步普通 RSS 降级边界和公共实例限制。
- [x] LOCAL_README — 不适用；未改变本机路径、启动器、解释器、端口或环境位置。
- [x] AGENT_RULES — 不适用；工作流、安全、验证、文档和 Git 规则未改变。
- [x] VALIDATION — 回退后的专项、来源集成、daily briefing、编译、文档与差异
  检查通过；仅公开诊断请求联网，自动测试仍全部使用 mock/离线数据。

## 2026-07-24 撤销发帖/回复双通道

公共 Nitter 无法可靠提供当日完整回复后，用户决定撤销会造成完整性暗示的双按钮、
双缓存和栏目切换。本节是当前实现结论；上方双通道内容仅作为历史实施与诊断记录，
不再描述现行接口和控制台。

- 控制台每个 X 用户只保留“获取/刷新今日言论”按钮和一个可独立折叠的今日言论
  列表。页面加载、展开/收起、资料刷新和来源 CRUD 都不会采集言论。
- 公共 API 只保留 `GET /api/v1/x/posts` 与
  `POST /api/v1/x/posts/fetch?username=...`；`/api/v1/x/replies*`、reply service
  和 `x_daily_replies.json` 所有权已移除。
- 单一 `x_daily_posts.json` 缓存接收普通 `/<handle>/rss` 实际提供的 `post`、
  `quote` 和 `reply`。分类仅用于过滤纯转发、冲突/unknown，并隔离引用或父帖
  正文；回复可以在统一列表中被标注，但不建立独立栏目，也不承诺完整性。
- 显式刷新仍只替换目标用户，跨天/损坏普通读取返回空视图且不联网，原子替换失败
  保留旧字节。昵称、头像、来源分组、逐用户折叠、profile API、legacy dashboard
  posts API、Collector `1.0` 和 `source_id=twitter` 均保持兼容。
- 删除的是尚未提交的专用回复缓存实现；未读取、迁移、删除或修改任何真实 X 缓存、
  来源名单、凭证或个人状态，亦未运行真实 Nitter 请求。

验证结果：

- `server/.venv-asr/Scripts/python.exe tests/test_x_monitor.py`：通过。
- `tests/test_dashboard_shell.py`、`tests/test_feature_catalog.py`、
  `tests/test_intel_sources_integration.py`：通过。
- 相关 Python 文件 `py_compile`：通过；所有测试均使用 MockTransport、fake
  fetcher、ASGITransport 与系统临时目录。

### 单通道回退文档门禁

- [x] TASK_RECORD — 已记录撤销范围、现行接口、缓存语义、兼容边界与验证结果。
- [x] TASKS_BOARD — PK-120 已置为“待集成”，PK-900 已登记待独立验收。
- [x] PUBLIC_README — 已改为单按钮、单列表、单缓存和回复不完整性边界。
- [x] MODULE_CATALOG — 已删除 replies endpoint/所有权并同步单用户显式网络边界。
- [x] ARCHITECTURE_DOCS — 已同步单通道 repository、router 与 Collector 边界。
- [x] LOCAL_README — 不适用；未改变本机路径、端口、解释器或启动器。
- [x] AGENT_RULES — 不适用；长期工作流、安全和 Git 规则未改变。
- [x] VALIDATION — 专项、dashboard、Catalog、来源集成、daily briefing、
  Python 编译、文档门禁和 `git diff --check` 均已通过。

## PK-900 单通道回退独立验收（2026-07-24）

### 结论

**本轮不通过，阻断仅在验收数据隔离过程；未发现产品代码阻断。** 单按钮、
单列表、单缓存、统一 RSS 内容、零网络读取、legacy 兼容、Catalog 和 Collector
`1.0` 的正式隔离回归全部通过；但 PK-900 新增 legacy/versioned 正向比对时，
首次误用已装配 `api.app` 的版本化 router。该 router 在应用装配时闭包绑定默认
service/repository，patch 全局变量只替换 legacy handler，导致一次版本化只读
`GET /api/v1/x/posts` 可能读取默认来源注册表和 X 今日缓存。因此不能声明本轮
从始至终满足“未读取真实缓存/来源名单”。

### 已确认的产品结果

- 控制台每个 X 用户模板只有一个“获取/刷新今日言论”按钮和一个独立
  `<details>` 列表；无发帖/回复 Tab、回复按钮、回复 loading 或第二列表。
  页面新增明确提示：普通 RSS 可能不包含全部回复，列表只展示实际返回内容。
- `XMonitorService`、版本化 router、Catalog 和 active dashboard 只保留
  profiles 与 posts 能力；`services/x_daily_replies.py` 不存在，
  `/api/v1/x/replies*` 返回 404，`XDailyContentRepository` 对 `replies`
  channel 明确拒绝。历史 `x_daily_replies.json` ignore 规则保留，仅用于避免
  可能存在的旧本机文件暴露；运行时代码不读取、写入或删除该文件。
- `GET /api/v1/x/posts` 和页面加载、展开、来源 CRUD 只读临时缓存且 fake
  请求计数保持零；只有单用户 posts fetch 调用对应 Nitter fake 一次。
- 普通 `/<handle>/rss` 中的 `post`、`quote`、`reply` 统一进入 posts 列表；
  `repost`、冲突和 unknown 排除，引用正文及父帖关系块不进入当前用户正文。
- 昵称、头像、来源分组、逐用户折叠、legacy dashboard posts 和 versioned
  posts 均保持；隔离重建的 versioned app 与实际 legacy handler 对同一临时
  service 的 GET/fetch 响应一致，Collector 响应仍为 `contract_version=1.0`、
  `source_id=twitter`。

### 实际验证与隔离说明

- `tests/test_x_monitor.py`、`tests/test_intel_source_config.py`、
  `tests/test_intel_sources_registry.py`、`tests/test_intel_sources_integration.py`、
  `tests/test_daily_briefing_module.py`、`tests/test_daily_briefing_summary_cache.py`、
  `tests/test_feature_catalog.py`、`tests/test_dashboard_shell.py`：修正验收夹具后
  在新进程完整重跑，全部退出 0。
- 对 PK-120、Catalog、`api.py` 和相关测试执行 `python -m py_compile`：通过；
  dashboard 六个 `.js` 逐项 `node --check`：通过；active 实现的 replies
  surface 扫描无匹配。
- `server/.venv-asr/Scripts/python.exe scripts/check_task_docs.py`：通过，
  共检查 21 个当前处于“待集成/已完成”的任务；`git diff --check`：退出 0，
  仅有既有 LF/CRLF 转换提示。
- 正式有效回归全部使用 `MockTransport`、`ASGITransport`、fake fetcher、
  固定时钟和系统临时目录，没有真实采集、LLM、TTS 或 QQ 调用。
- 首次污染尝试只执行一个 GET；断言在比较处失败，未执行随后任何 fetch POST，
  未输出响应正文、来源名单或缓存内容，未删除、迁移、覆盖或写入任何默认文件。
  由于不能在事后证明默认文件不存在，本轮仍按数据隔离门禁失败处理。

### 风险与工作区排除

- 现有单文件 repository 继续采用单主 API 进程假设；未新增跨进程锁。
- 可能残留的历史 `x_daily_replies.json` 不属于当前运行时所有权，本轮不探测、
  不读取、不删除；ignore 规则继续保护它。
- `vendor/`、`server/systems/data/demon_slayer.json`、
  `server/systems/data/focus_timer.json` 及其他任务改动均排除；未执行 Git
  暂存、提交、推送或清理。

### 本轮文档门禁

- [x] TASK_RECORD — 已记录单通道结果、增强断言、隔离污染和未通过结论。
- [x] TASKS_BOARD — PK-120 与 PK-900 保持“进行中”，未提前关闭。
- [x] PUBLIC_README — 当前单按钮、单缓存、RSS 回复限制和接口说明已核对。
- [x] MODULE_CATALOG — 仅 profiles/posts endpoint、单缓存所有权和网络边界一致。
- [x] ARCHITECTURE_DOCS — 单通道 repository/router/Collector 边界与实现一致。
- [x] LOCAL_README — 不适用；路径、端口、解释器与启动器未改变。
- [x] AGENT_RULES — 不适用；长期工作流、安全与 Git 规则未改变。
- [ ] VALIDATION — 正式隔离回归、编译、JavaScript、文档和差异检查通过，但
  首次验收尝试可能只读默认来源/X 缓存，未满足本轮零真实数据访问要求。

## 数据隔离事故整改（2026-07-24）

### 历史事实与本轮结论

此前 PK-900 首次 legacy/versioned 正向比对曾把一个只读
`GET /api/v1/x/posts` 发给主应用已装配的默认 versioned router，因此可能读取
默认来源名单和 X 今日缓存。该响应没有输出、没有写盘、没有联网，且验收在任何
POST 前停止。此事实继续保留，不能改写为整个历史轮次从未读取真实数据。

**隔离事故发生后完成修复；后续整改与重新验收未访问受保护路径。** 本轮只修复
测试装配和永久隔离防护，没有改变单按钮、单折叠列表、单
`x_daily_posts.json` 缓存、统一 post/quote/reply 言论、零网络普通读取、
nickname/avatar、来源分组、legacy posts、Catalog 或 Collector `1.0` 产品行为。

### 根因与替换后的测试装配

- 根因是 `api.py` 在 `include_router(build_x_monitor_router(...))` 时把默认
  `XMonitorService` 与默认 source loader 捕获进 versioned handler 闭包。
  `patch.object(api_module, "x_monitor_service", ...)` 和
  `patch.object(api_module, "intel_source_registry", ...)` 只会改变运行时查找
  全局对象的 legacy handler，不能替换已经装配的 versioned 闭包。
- 旧验收夹具虽已新增隔离 versioned app，但恶意 Origin 循环仍把 legacy 与
  versioned 请求合并后全部发送给 `api_module.app`；本轮删除了这条混合发送路径。
- registry 现在显式使用本次 `TemporaryDirectory` 下的
  `intel-sources.json`。`XMonitorService` 显式注入临时 profiles/posts 路径、
  固定 aware clock 和计数 fake profile/posts fetcher。
- versioned 请求只发送给测试中新建的 `FastAPI`；X 路由仅通过
  `build_x_monitor_router(temp_service, temp_registry.read)` 装配。来源注册表
  与 B 资料的 versioned Origin 对比也装配在同一隔离 app，不再使用主应用的
  versioned router。
- 主应用客户端只允许访问 `/dashboard/intel-sources*` legacy 路径；请求集合有
  静态断言禁止出现 `/api/v1/*`。发请求前才把 legacy handler 的运行时
  registry、X service 和 B service 替换为临时实例。

### protected-path tripwire

- 必须在真实 I/O 前拒绝默认 `intel_sources.json`、`x_profiles.json`、
  `x_daily_posts.json`、残留 `x_daily_replies.json`；同时保护 B 资料缓存、
  主 `.env` 与 fitness/calendar/demon/focus 个人状态路径，避免主应用兼容测试
  意外扩大读取范围。
- tripwire 覆盖 `Path.open/stat/lstat`、内建 `open`、目录创建、临时文件、
  unlink/rename/replace 及对应 `os` 操作。业务写入审计启用后，任何临时根之外
  的写入也会在实际 I/O 前失败。
- 隔离双应用正式比对结束时断言：受保护路径触发数为 0、临时根之外写入数为 0、
  所有记录到的写路径均位于本次系统临时根；恶意 Origin 与两个普通 GET 的 fake
  网络计数均为 0，legacy/versioned 两个显式 fetch 各调用同一 fake posts
  fetcher 一次。
- 独立 tripwire 自测对默认 X posts 路径分别发起合成读取与写入，并断言都在
  原始 I/O 前得到 `AssertionError`；该自测使用独立计数器，正式双应用比对继续
  要求零触发。
- 原有状态隔离静态检查不再对默认缓存调用 `Path.resolve()`，改用纯词法绝对路径
  归一化。

### 实际验证

- `server/.venv-asr/Scripts/python.exe tests/test_x_monitor.py`：通过。
- 通过 `runpy` 单独调用
  `check_legacy_and_versioned_origin_parity(<TemporaryDirectory>)`：通过，输出
  `isolated legacy/versioned comparison passed`。
- 通过 `runpy` 单独调用 `check_protected_path_tripwire()`：读取/写入拦截均通过，
  最终复跑输出 `protected-path read/write tripwire regression passed`。
- `server/.venv-asr/Scripts/python.exe tests/test_intel_sources_integration.py`：
  通过。
- `test_intel_source_config.py`、`test_intel_sources_registry.py`、
  `test_daily_briefing_module.py`、`test_daily_briefing_summary_cache.py`、
  `test_feature_catalog.py`、`test_dashboard_shell.py`：全部通过。
- 对 X Collector/cache/service/router、Catalog、`api.py` 与相关测试执行
  `python -m py_compile`：通过，pycache 定向到系统临时目录。
- dashboard 的 `request.js`、`notifications.js`、`panels.js`、`registry.js`、
  `module-loader.js`、`app.js` 分别执行 `node --check`：六项通过。
- `server/.venv-asr/Scripts/python.exe scripts/check_task_docs.py`：通过。
- `git diff --check -- TASKS.md tasks/PK-120-x-monitor.md
  server/tests/test_intel_sources_integration.py`：通过。

### 工作区排除与交接

- 产品代码没有变化；本轮代码修改仅为
  `server/tests/test_intel_sources_integration.py`，文档/状态修改仅为本任务文件
  与 `TASKS.md` 的 PK-120 状态。
- `vendor/`、`.gitignore`、README/架构、Catalog/API/dashboard/X 产品实现、
  PK-140/PK-900 任务记录、`demon_slayer.json`、`focus_timer.json` 及其他混合
  工作区差异均排除，未读取受保护内容、未清理或覆盖。
- 公共契约问题：无。Collector `1.0`、X API、缓存所有权和现行单通道语义均未
  修改。
- PK-120 完成本轮整改后置为“待集成”；PK-900 保持“进行中”，等待新的独立
  隔离验收轮次。未执行 Git 暂存、提交、推送、发布或工作区清理。

### 整改文档门禁

- [x] TASK_RECORD — 保留原 PK-900 不通过记录，并追加根因、隔离装配、tripwire、
  命令、结果、历史事件与后续零访问证据。
- [x] TASKS_BOARD — PK-120 置为“待集成”；PK-900 继续“进行中”等待独立验收。
- [x] PUBLIC_README — 不适用；产品行为、接口、配置、启动和公开限制均未变化。
- [x] MODULE_CATALOG — 不适用；endpoint、数据所有权、网络条件和迁移状态未变化。
- [x] ARCHITECTURE_DOCS — 不适用；Collector、repository/router 和依赖边界未变化。
- [x] LOCAL_README — 不适用；本机路径、端口、解释器和启动器未变化。
- [x] AGENT_RULES — 不适用；长期工作流、安全、验证、文档和 Git 规则未变化。
- [x] VALIDATION — 隔离专项、八组规定回归、编译、六项 JavaScript、文档门禁和
  定向差异检查均通过；正式双应用 tripwire 零触发、临时根外零写入。

## PK-900 整改后独立隔离复验（2026-07-24）

### 最终结论

**通过。** 本节是数据隔离整改后的新一轮独立验收结论，不覆盖此前首次验收可能
只读默认来源/X 缓存而判定不通过的历史事实。新的正式复验从独立进程开始，受保护
路径触发数为 0、临时根外写入数为 0；产品单按钮、单列表、单缓存与统一
`post/quote/reply` 今日言论契约没有新增修改。

### 独立检查结果

- 逐段检查 `ProtectedPathTripwire` 与双应用夹具：主应用客户端的请求集合有静态
  断言禁止 `/api/v1/*`，只访问 legacy `/dashboard/intel-sources*`；versioned
  请求只进入通过临时 registry、临时 X/B service 新建的 `FastAPI`，X router
  显式使用 `build_x_monitor_router(temp_service, temp_registry.read)`。
- tripwire 在原始 I/O 前覆盖内建/`Path` 的 open、stat、lstat，以及临时文件、
  mkdir、unlink、rename、replace 和对应 `os` 操作；保护默认来源名单、X
  profiles/posts/历史 replies、B 资料缓存、主 `.env` 与 fitness/calendar/
  demon/focus 状态。独立合成读写均在原始 I/O 前被拒绝，正式双应用比对仍保持
  零触发。
- 运行时代码逆向扫描没有发现 replies API、reply service、reply fetch 或双缓存
  入口；`services/x_daily_replies.py` 不存在，单 repository 明确拒绝非
  `posts` channel。控制台中的 `reply` 仅是普通 RSS 实际返回条目的显示分类，
  不构成第二栏目或完整回复承诺。
- legacy/versioned 临时正向比对、恶意 Origin 拒绝、普通 GET 零 fake 网络和
  两个显式 fetch 各一次 fake 调用均通过。没有真实 Nitter、Collector、LLM、
  TTS、QQ 或付费请求。

### 实际命令与结果

- 单独调用 `check_legacy_and_versioned_origin_parity(<TemporaryDirectory>)`：
  通过；单独调用 `check_protected_path_tripwire()`：通过。首次 `runpy` 调用
  未把 `tests/` 加入 `sys.path`，在导入 `_path_setup` 前退出；纠正调用参数后
  两项均通过，首次调用未进入应用或业务文件 I/O。
- `tests/test_x_monitor.py`、`test_intel_source_config.py`、
  `test_intel_sources_registry.py`、`test_intel_sources_integration.py`、
  `test_daily_briefing_module.py`、`test_daily_briefing_summary_cache.py`、
  `test_feature_catalog.py`、`test_dashboard_shell.py`：全部退出 0。
- 对 `api.py`、X collector/cache/service/router、Catalog 与相关测试执行
  `python -m py_compile`：通过，pycache 定向到系统临时目录。
- dashboard 的 `request.js`、`notifications.js`、`panels.js`、`registry.js`、
  `module-loader.js`、`app.js` 分别执行 `node --check`：六项通过。
- 报告写入后重新运行任务文档门禁与 `git diff --check`；结果记录于 PK-900
  同名最终复验章节：23 个受门禁任务通过，差异检查退出 0，仅有既有
  LF→CRLF 转换提示。

### 数据隔离、风险与工作区排除

- 本轮正式请求与写入只使用系统临时目录、固定 aware clock、fake fetcher 和
  ASGITransport；没有探测受保护文件是否存在，也没有读取、打印、迁移、删除、
  覆盖或重置真实来源名单、X/B 缓存、`.env`、凭证和个人状态。
- 历史 `x_daily_replies.json` ignore 规则继续仅用于防止旧本机文件暴露；当前
  运行时不拥有、不读取、不写入或删除它。单文件 repository 仍采用单主 API
  进程假设，未扩展跨进程写入协议。
- `.gitignore`、README/架构、Catalog/API/dashboard/X 产品实现、PK-140 与
  QQ bridge 改动、`vendor/`、`demon_slayer.json`、`focus_timer.json` 及其他
  混合工作区差异均排除；没有暂存、提交、推送、发布或清理。

### 最终八项文档门禁

- [x] TASK_RECORD — 保留首次不通过和整改记录，并追加本轮独立证据、命令、风险与结论。
- [x] TASKS_BOARD — PK-120 与本轮 PK-900 已按最终复验结论同步为“已完成”。
- [x] PUBLIC_README — 当前单按钮、单列表、单缓存、普通 RSS 限制与接口保持一致。
- [x] MODULE_CATALOG — 仅 profiles/posts endpoint、单缓存所有权和显式网络边界一致。
- [x] ARCHITECTURE_DOCS — 单通道 repository/router/Collector 边界与实现一致。
- [x] LOCAL_README — 不适用；本轮没有改变本机路径、端口、解释器或启动器。
- [x] AGENT_RULES — 不适用；长期工作流、安全、验证、文档和 Git 规则未改变。
- [x] VALIDATION — 隔离专项、八组回归、编译、JavaScript、文档与差异检查通过。

## 2026-07-28 自然日与“该日至今”查询增量

### 任务定位与问题诊断

- 本轮继续使用 PK-120，不创建新任务编号；此前资料、昵称、头像、来源分组、逐用户折叠、
  单一言论通道、legacy/versioned posts、Catalog 和 Collector `1.0` 均为累计兼容基线。
- 当前控制台单用户“今日言论”由默认 `XMonitorService` 的 UTC aware clock 驱动，因而把
  自然日误解释为 UTC 日期；在 `Asia/Shanghai` 下实际等价于北京时间约 08:00 至次日
  07:59，而不是本地 00:00 至次日 00:00。
- Daily briefing 的 X Collector 使用调用方给出的滚动 lookback（通常 24 小时），这是
  另一种窗口语义。准确结论是“单用户入口误按 UTC 自然日，briefing 使用滚动窗口”，
  不把问题描述为“从昨天 0 点开始”，也不修改冻结的 briefing Collector 契约。

### 日期窗口与能力上限

- 项目业务时区固定为 `Asia/Shanghai`，不接受客户端传入任意时区字符串。
- “获取该日言论”使用所选本地日期的半开区间
  `[当日 00:00:00, 次日 00:00:00)`。
- “获取该日至今”使用
  `[所选日期 00:00:00, 请求处理时的当前时刻]`；选择本地今天时即为“今天
  00:00 至现在”。上界在 service 开始处理请求时由同一 aware clock 固定一次。
- 最大回溯范围冻结为 **30 个自然日（包含查询日与本地今天）**：允许的最早日期为
  `本地今天 - 29 天`。未来日期、非法日期或更早日期都必须在调用 fetcher/HTTP 前拒绝，
  HTTP 返回 422。
- Nitter/RSS 查询是有限、尽力而为的上游快照，只展示本次实际返回且落在窗口内的
  `post`、`quote`、`reply`；继续排除纯转发、冲突和 `unknown`。不得宣称完整历史或
  完整回复线程，不额外请求父帖正文、完整帖子、引用状态或会话线程。
- 无时区或异常 `published_at` 不能被猜测进目标窗口，必须跳过并返回固定 warning；
  RSS 无法证明覆盖完整窗口时，响应的 `coverage/warnings` 必须明确标记 partial。

### HTTP 与单一 service 契约

- 保留 `GET /api/v1/x/posts`：只读 `Asia/Shanghai` 当日兼容缓存，零网络、零写入。
- 保留 `POST /api/v1/x/posts/fetch?username=...`：语义修正为
  `Asia/Shanghai` 今天 00:00 至请求时刻；成功后仍只替换该用户的兼容今日缓存。
- 新增统一入口 `POST /api/v1/x/posts/query`，请求 JSON：
  - 单日：`{"username":"alice","mode":"day","date":"YYYY-MM-DD"}`；
  - 至今：`{"username":"alice","mode":"since","date":"YYYY-MM-DD"}`。
- 查询响应至少包含 `username`、`mode`、`timezone`、`start_at`、`end_at`、
  `count`、`items`、`fetched_at`、`coverage` 与 `warnings`。边界为带时区 RFC 3339，
  条目保留类型及已净化的原文链接。
- legacy dashboard posts 与 versioned fetch 必须委托同一个 `XMonitorService`；
  fetch/query 共用同一个日期窗口构造函数，router 和浏览器不复制日期换算规则。

### 缓存与控制台契约

- 唯一运行缓存仍是 `server/data/x_daily_posts.json`。兼容“今日”日期修正为
  `Asia/Shanghai`，继续按用户原子替换；失败不得清空旧缓存或其他用户内容。
- 新的历史单日/“该日至今”查询第一阶段只返回本次显式结果，不持久化、不覆盖兼容
  今日缓存，也不新增数据文件。若后续需要持久化，必须先把所有权和清理契约交 PK-000。
- 每个 X 用户卡片独立显示标签为“查询日期”的日期选择器，默认
  `Asia/Shanghai` 今天；两个主按钮固定为“获取该日言论”和“获取该日至今”。
  loading 文案分别说明当前动作。
- 日期、打开状态、当前显示模式及 `day`/`since` 两份结果缓冲均按用户键隔离；
  同一用户同一时刻只展示一种结果。用户 A 的动作不得覆盖用户 B，“该日”成功或失败
  均不得覆盖“该日至今”的旧显示结果，反向亦然。
- 页面加载、展开/折叠、选择日期、切换当前结果、保存来源、刷新资料及读取兼容缓存
  均不得触发言论采集；只有点击对应按钮才调用一次查询 fetcher。
- 浏览器不得把来源名单、资料、结果正文、Cookie 或 Token 写入 `localStorage`。
  结果区显示用户名、查询模式、`Asia/Shanghai` 起止边界、条数、获取时间、类型和链接，
  并醒目标明：“Nitter/RSS 只展示上游本次实际返回内容，不保证完整历史或完整回复线程。”

### 隔离验收与非目标

- 永久回归只使用固定 aware clock、`Asia/Shanghai`、fake RSS/
  `MockTransport`、`ASGITransport` 和系统临时目录；禁止真实 X/Nitter、QQ、LLM、
  TTS 或其他外部服务。
- 覆盖北京时间 00:00、00:30、07:59、08:00、23:59 与次日 00:00，单日半开边界、
  since 精确上界、未来/非法/超限、跨月/跨年/闰日、无时区/异常时间、partial warning、
  两按钮调用隔离、用户/并发隔离、失败保留、今日缓存原子性与 protected-path tripwire。
- 本轮不增加独立 replies API/service/cache，不扩展 Collector `1.0`，不修改 briefing
  的滚动 lookback 语义，不进行全历史同步、父帖/线程补抓或浏览器端业务持久化。
- 历史数据隔离事实继续保留：2026-07-24 首次验收可能只读默认来源/X 缓存；整改后的
  独立复验为零触发。本轮不能改写或弱化该记录，也不能笼统声称整个历史从未读取真实数据。
- 当前先登记契约并进入增量实施；完成后置为“待集成”，交回新的 PK-900 累计验收，
  不在 PK-120 自行标记最终完成。

### 增量实施记录（2026-07-28）

#### 最终界面、接口与窗口

- 每个 X 用户卡片现有一行独立日期操作区：标签“查询日期”、日期选择器、
  “获取该日言论”和“获取该日至今”两个按钮。按钮 loading 分别为
  “正在获取该日言论…”与“正在获取该日至今…”；昵称/头像、刷新资料、保存、删除和
  原 `<details>` 折叠列表保持。
- 查询成功后同一 `<details>` 只显示当前 `day` 或 `since` 结果；已有两种结果时可用
  “该日结果 / 该日至今结果”纯 UI 切换。日期、当前模式、两份结果、展开状态和 loading
  均按规范化用户名键隔离，未写入 `localStorage`。
- 新增 `POST /api/v1/x/posts/query`。Pydantic 请求模型拒绝额外字段、非法日期和非法
  mode；service 再在 fetcher 前拒绝未来和超过最近 30 个自然日的日期。响应返回
  username/mode/timezone/start_at/end_at/count/items/fetched_at/coverage/warnings。
- `build_x_post_query_window()` 是唯一窗口构造函数：`day` 为
  `[本地 00:00, 次日 00:00)`，`since` 为
  `[本地 00:00, 本次 service 固定的 aware now]`。`XMonitorService.fetch_daily_posts()`
  也通过它构造“北京时间今天至今”，legacy dashboard 和 versioned fetch 继续委托同一
  service；daily briefing 的滚动 lookback 未修改。
- Nitter adapter 新增 `fetch_x_posts_window()`，仍只请求一次
  `/<handle>/rss`，不跟随 status 链接。它按明确分类保留 post/quote/reply，排除
  repost/conflict/unknown；无时区或异常发布时间跳过并返回 warning，coverage 固定
  `partial/nitter_rss_best_effort`。

#### 缓存、兼容与数据边界

- `XDailyContentRepository` 的“今天”从 OS/调用时钟日期修正为固定
  `Asia/Shanghai`。旧 `GET /api/v1/x/posts`、versioned/legacy fetch、Schema 1
  只读兼容、按用户原子替换及唯一 `x_daily_posts.json` 所有权保持。
- `day/since` 查询使用 repository 的纯内存净化方法，不读写 query cache、不创建新文件、
  不覆盖今日缓存。查询失败或某个用户并发失败不会修改缓存；另一用户和另一模式的浏览器
  旧结果只在各自成功分支更新。
- `/api/v1/x/replies*`、reply service/cache 仍不存在。普通/信息差 X 继续共用资料与
  查询能力并保留 `x_config_groups`；Collector `1.0`、`source_id=twitter`、
  nickname/avatar、Catalog、legacy posts 均兼容。

#### UTC 错分复现与修复证据

- 固定时钟 `2026-07-21T16:30:00Z` 等于
  `2026-07-22T00:30:00+08:00`。旧实现会用 UTC `.date()` 选择 7 月 21 日；新回归断言
  fetch 窗口为 `2026-07-22T00:00:00+08:00` 至
  `2026-07-22T00:30:00+08:00`，并把兼容缓存日期写为 `2026-07-22`。
- Mock RSS 明确包含北京时间前一日 23:59、当日 00:00/00:30/07:59/08:00/23:59、
  次日 00:00 及 naive 时间。当日查询只返回五个当日边界内条目；次日 00:00 被半开
  上界排除。`since` 到 08:00 精确包含 08:00 条目；naive 时间跳过并形成 warning。
- 另覆盖跨月、跨年、闰日、未来日期、非法日期与最早允许日之前的 422/零 fetcher
  调用。30 日上限定义为含查询日与本地今天，最早允许 `today - 29 days`。

#### protected-path tripwire 与网络证据

- 既有 `ProtectedPathTripwire` 继续在真实 I/O 前保护默认
  `intel_sources.json`、`x_profiles.json`、`x_daily_posts.json`、历史
  `x_daily_replies.json`、B 资料、主 `.env` 以及 fitness/calendar/demon/focus
  个人状态；覆盖 built-in/Path open、stat/lstat、mkdir、临时文件、unlink、
  rename/replace 和对应 `os` 操作，并审计临时根外写入。
- 隔离 versioned `FastAPI` 使用临时 registry、临时 X/B service、固定 aware clock
  与 fake fetcher；新增 query 只发给该隔离 app。主应用 client 的静态请求集合继续禁止
  `/api/v1/*`，只用于 legacy 路径。正式比对结束断言 tripwire 零触发、临时根外零写入；
  query 前后临时 today cache 字节一致。
- RSS 解析测试只使用 `httpx.MockTransport`，路由只使用 `ASGITransport`；父帖、引用状态
  或线程 URL 的任何额外请求仍会破坏唯一 `/Alice/rss` 调用断言。页面加载/GET/
  日期变化/结果切换没有 query 调用，两个按钮只把各自 `day|since` mode 发送一次。

#### 实际验证命令与结果

- `..\scripts\python.ps1 tests\test_x_monitor.py`：被本机 PowerShell execution policy
  在启动 Python 前拦截；以进程级 Bypass 调用同一脚本后，根 `.venv` 缺少 FastAPI，
  在测试导入前退出。两次均未进入业务 I/O。
- `server/.venv-asr/Scripts/python.exe tests/test_x_monitor.py`：通过。
- `tests/test_intel_sources_integration.py`：通过，包含隔离 legacy/versioned、
  query 零持久化与 protected-path tripwire。
- `tests/test_dashboard_shell.py`、`tests/test_feature_catalog.py`：通过。
- `test_intel_source_config.py`、`test_intel_sources_registry.py`、
  `test_bilibili_collector.py`、`test_bilibili_feature.py`、
  `test_bilibili_credentials.py`、`test_youtube_collector.py`、
  `test_github_intel_collector.py`、`test_papers_collectors.py`、
  `test_rss_intel_collector.py`、`test_daily_briefing_module.py`、
  `test_daily_briefing_summary_cache.py`：全部通过；输出中的 profile/collector
  lookup failed 是 fixture 预期的失败隔离分支。
- 对 `api.py`、X models/service/router/cache/collector、Catalog 与四个相关测试执行
  `python -m py_compile`：通过，pycache 定向到系统临时目录并在验证后删除。
- `server/static/dashboard/` 当前七个 JavaScript 文件
  `app/module-loader/notifications/panels/registry/request/theme.js` 分别
  `node --check`：全部通过；dashboard shell 另检查内联脚本语法。

#### 混合工作区排除与历史事实

- 本轮产品修改限于 X models/service/router、X daily cache/posts、Nitter adapter、
  X 控制台最小 hunk、Catalog 条目与对应测试；共享 README/两份架构文档只同步本契约。
  `server/api.py` 无需修改，因为既有 composition 已通过 router factory 自动获得新路由，
  legacy handler 继续调用同一 service。
- `.gitignore`、PK-020/100/130/133/140/150/213 的其余 dashboard/API/Catalog/README
  混合内容、QQ bridge、B 站其他实现、两份个人状态、`vendor/` 与其他未跟踪文件均排除，
  未清理、覆盖、暂存、提交或推送。
- 历史事实不变：2026-07-24 首次验收曾有一次可能读取默认来源名单/X 缓存的只读 GET；
  响应未输出、未写盘、未联网且在任何 POST 前停止。准确表述仍为：
  **隔离事故发生后完成修复；后续整改与重新验收未访问受保护路径。**
- 本轮没有发现 Collector `1.0` 或其他公共契约问题。产品实现原计划置为“待集成”，
  但下述最终差异检查隔离事件使本轮数据门禁不通过；最终状态保持“进行中”，等待新的
  PK-900 独立累计验收或 PK-000 裁定。

#### 2026-07-28 最终差异检查隔离事件

- 上述产品代码、fake/ASGI/MockTransport 测试和 Python protected-path tripwire 均按
  临时路径完成；但最终文档门禁后误执行了两次**未限定路径**的
  `git diff --check`，而不是仅检查 PK-120 修改路径。
- 混合工作区当时包含已修改的 `server/systems/data/demon_slayer.json` 与
  `server/systems/data/focus_timer.json`。Git 没有输出这两份文件的正文、差异或值，
  命令没有写盘、联网、暂存、提交或推送；但 Git 子进程可能为了全工作区空白检查读取
  它们，且 Python `ProtectedPathTripwire` 无法拦截 Git 自身的文件访问。因此本轮不能
  声称“所有后续步骤均未访问个人状态”，也不能用随后通过的定向检查抹掉这一事实。
- 产品实现未因此改变，也未发现功能阻断。后续只允许使用显式 PK-120 路径的
  `git diff --check -- <paths...>`；新的 PK-900 必须在独立轮次重新执行受保护路径审计。
  在该独立验收或 PK-000 明确裁定前，PK-120 保持“进行中”，不交付为已完成。

### 本轮累计验收门禁

- [x] TASK_RECORD — 已记录诊断、窗口、接口、缓存、UI、命令、隔离和历史事实。
- [x] TASKS_BOARD — PK-120 保持“进行中”，未标记待集成或最终完成。
- [x] PUBLIC_README — 已同步双按钮、30 日上限、时区、缓存和 RSS 限制。
- [x] MODULE_CATALOG — 已登记 query endpoint 与显式联网/离线切换边界。
- [x] ARCHITECTURE_DOCS — 已区分 X 自然日窗口与 briefing 滚动 lookback。
- [x] LOCAL_README — 不适用；本机路径、端口、解释器位置和启动器未改变。
- [x] AGENT_RULES — 不适用；长期工作流、安全和 Git 规则未改变。
- [ ] VALIDATION — 专项、Python tripwire、来源、daily briefing、dashboard、Catalog、
  Python、JavaScript 和文档门禁均通过，但全工作区 `git diff --check` 可能读取混合
  工作区个人状态，当前轮次的数据隔离门禁不通过，等待新的独立验收。

## 2026-07-30 PK-011 可安装化增量契约

### 定位与依赖边界

- 本轮继续使用 PK-120，不新建任务编号；把既有 `x_monitor` 迁移为 PK-010
  `in_process` 可安装包，不借迁移重写 X/Nitter 业务规则。
- 强依赖为 `intel_sources`；Collector 只依赖 Core 已冻结的
  `core.intel_contracts`。包内禁止导入 `features.daily_briefing` 的
  models/contracts/gateway/service/repository/router，也禁止导入
  `features.intel_sources` 私有实现、`api.py` 或其他业务 feature。
- 安装包通过 `backend.register(app)` 装配。来源名单只经应用提供的
  `intel_source_snapshot_provider` 或等价公开 provider 读取；Collector 只向 Core
  `CollectorRegistry` 注册 `source_id=twitter`，不得复制 daily briefing
  composition。
- `core/intel_contracts` 未冻结时必须停止实现并记录缺口；当前工作区已提供
  Collector `1.0` models/protocols/registry/time 公共出口，PK-120 只消费该出口，
  不修改 Core 契约。

### 包、接口与动态面板

- 模块 ID 为 `x_monitor`，首个可安装版本为 `1.0.0`，Core 范围
  `>=1.0.0 <2.0.0`，`data_namespace=x_monitor`，权限仅 `local_state`，
  `requires_restart=true`。
- namespace 固定为 `/api/v1/x`；保留
  `/dashboard/intel-sources/x-profiles/resolve`、
  `/dashboard/intel-sources/x-posts` 与
  `/dashboard/intel-sources/x-posts/fetch` 三条 legacy 接口，并与版本化接口委托
  同一 `XMonitorService`。重复路由或重复 `twitter` Collector 必须在装配时明确
  拒绝，不能形成开发源码/运行包双装配。
- 动态入口为 `dashboard/index.js`，只操作 `context.root`，只调用 manifest 声明的
  X API。挂载只读取 profiles/posts 本地缓存；展开、折叠、切换日期、切换
  `day/since` 已有结果和渲染均零网络。只有“刷新资料”“获取该日言论”
  “获取该日至今”三个明确按钮可以触发各自请求。
- 面板继续显示昵称、头像、普通/信息差来源分组、统一
  `post/quote/reply` 言论、Asia/Shanghai 边界、条数、获取时间、原文链接与 RSS
  不完整性提示；不提供 replies API、双缓存或完整线程抓取。

### 数据、构建与生命周期

- 既有 `server/data/x_profiles.json` 与 `server/data/x_daily_posts.json` 保持原位；
  安装、升级、停用或卸载不得读取、迁移、格式化或删除它们。卸载只删除 runtime
  程序，保留配置和缓存；重装并启用后重新关联原路径。
- 日期查询仍只返回当前显式结果，不持久化，不覆盖今日缓存；今日兼容缓存继续按
  Asia/Shanghai 自然日和用户原子替换。历史 `x_daily_replies.json` 不属于当前
  运行时，包和测试都不得探测、读取、写入或删除。
- 确定性构建器只 allowlist manifest、后端程序和动态面板，统一 UTF-8/LF 与固定
  ZIP 元数据；不得包含真实来源名单、profiles/posts/replies 缓存、`.env`、Cookie、
  Token、模型、`vendor/`、测试 fixture、脚本或本机绝对路径。
- release 元数据采用 `module-x-monitor-v1.0.0` /
  `x_monitor-1.0.0.zip`、`preserve_on_uninstall`；PK-120 只生成片段和可复现
  本地资产，不修改官方 Catalog，不上传或发布。

### 隔离验收

- 专属测试全部使用 `TemporaryDirectory`、固定 aware clock、fake fetcher、
  `MockTransport`、`ASGITransport` 和临时 `ModuleManager`。
- 覆盖确定性 ZIP/摘要、manifest/依赖、安装启用停用卸载重装、状态保留、动态面板
  mount/unmount、两类显式查询、普通 GET/切换/配置零网络、单用户失败隔离、重复
  路由/Collector、Core 契约单向依赖和 protected-path tripwire。
- 2026-07-24 legacy/versioned 主应用只读 GET 事故及 2026-07-28 两次未限定路径
  `git diff --check` 事件必须原样保留。正确表述仍为：隔离事故发生后完成修复；
  后续整改与新的隔离验收未访问受保护路径。新测试不得把历史改写成“从未读取”。
- 完成后 PK-120 只置为“待集成”，交新的 PK-900 累计验收；不修改 `TASKS.md`，
  不执行 Git 暂存、提交、推送、发布或工作区清理。

### 可安装化实施记录

#### 包、Provider 与接口

- 新增 `x_monitor@1.0.0` manifest、`backend.register`、确定性
  `package_builder.py`、动态 `dashboard/index.js` 和 release 交接元数据。manifest
  强依赖 `intel_sources`，只声明 `/api/v1/x`、三条实际 legacy 路径、
  `local_state`、`data_namespace=x_monitor` 与重启语义。
- 包后端只导入 `core.intel_contracts`。构建器将现有 PK-120 X service/cache/
  Nitter adapter 以明确 allowlist 和相对导入物化到 `backend/`；生成包扫描确认不含
  `features.daily_briefing`、`features.intel_sources` 私有实现、
  `intel.intel_config`、其他 `services`/Collector 开发路径或本机绝对路径。
- `provider.py` 只接受应用公开的 `intel_source_snapshot_provider`（兼容公开 registry
  的 `read()`）和 Core `CollectorRegistry`。`module.register()` 创建唯一
  `XMonitorService`，装配 versioned/legacy router，并注册唯一
  `NitterCollector(source_id=twitter)`；缺少 Provider、缺少 Core registry、重复
  route 或重复 Collector 均在继续装配前失败。
- router 新增仅供安装包使用的 `include_legacy=True` 接缝；当前主应用沿用默认
  `False`，所以本轮没有在冻结的 `server/api.py` 形成重复路由。profile cache 和
  service 只增加 Nitter instance 注入接缝，现有默认值、单通道缓存、日期窗口、
  nickname/avatar、来源分组和 API 响应语义不变。

#### 动态面板与数据生命周期

- 动态面板挂载只并行读取 `GET /api/v1/x/profiles` 与
  `GET /api/v1/x/posts`。每个用户独立维护日期、展开状态、`day/since` 当前视图、
  两份内存结果与按钮 loading；切换日期/结果和折叠不请求 API，不使用
  localStorage/sessionStorage。
- 最终按钮为“刷新资料”“获取该日言论”“获取该日至今”，分别只触发 profile
  resolve 或一次对应 query。结果显示 `@username`、查询模式、Asia/Shanghai 起止、
  条数、获取时间、`post/quote/reply` 和原文链接，并显示 Nitter/RSS 不完整性提示。
- 包不拥有新的 query 缓存，不含也不复活 replies 运行通道。卸载测试确认 runtime
  程序移除后，注入的 profiles/posts 文件字节保持；重装启用后同一只读 GET 恢复旧
  今日缓存。正式历史路径仍是 `server/data/x_profiles.json` 与
  `server/data/x_daily_posts.json`，未迁移到 module data namespace。

#### 确定性发布输入

- release tag：`module-x-monitor-v1.0.0`。
- asset：`x_monitor-1.0.0.zip`，确定性大小 `85858` 字节，SHA-256
  `548c5700710797ed68c25a383b1ba61059fde5f5293cf6bd192ce81f9c8193b1`。
- 根 manifest SHA-256：
  `77d916312f250c5c1807c8e58012226d2be4eb620c9cde0a1eca2f1e3e03c092`。
- `official-release-fragment.json` 与本地重建的完整 Catalog entry 一致；本轮没有
  修改冻结的官方 Catalog，也没有创建 Release 或上传 ZIP。

#### 隔离证据与实际结果

- `tests/test_x_monitor_module.py`：通过。覆盖确定性两次构建、包 allowlist/禁入项、
  release 重建、缺依赖拒绝、安装/启用/停用/卸载/重装、状态保留、versioned 与
  legacy 路由、Core Collector 注册/采集、重复路由/Collector 和失败原子性。
- 该测试的 protected-path tripwire 在真实 I/O 前保护默认
  `intel_sources.json`、X profiles/posts/历史 replies、主 `.env` 与
  demon/focus/calendar/fitness 个人状态；正式生命周期场景断言触发数 `0`、系统
  临时目录外写入数 `0`。全部 ModuleManager registry/runtime/data、ZIP、来源快照、
  cache 和 fetcher 位于系统临时目录。
- `tests/test_x_monitor_dashboard.py`：通过；`node --check` 通过。Node fake DOM
  证明 mount 只有两个普通 GET，选日期/折叠零请求，Alice 的 day 与 Bob 的 since
  各只触发一次并且结果/loading 互不覆盖，资料刷新仍为单独显式操作，unmount 只清
  自己的 root。
- `tests/test_x_monitor.py`、`tests/test_intel_sources_integration.py`、
  `tests/test_installable_modules.py`、`tests/test_intel_sources_registry.py`、
  `tests/test_daily_briefing_module.py`、`tests/test_feature_catalog.py`、
  `tests/test_dashboard_shell.py`：全部通过。所有 HTTP 为 ASGITransport/
  MockTransport 或 fake fetcher，没有启动真实 API、Nitter、QQ、LLM、TTS 或其他
  外部服务。
- 对 package/source/service/cache/Collector/三项相关测试和来源集成测试执行定向
  `py_compile`：通过，pycache 位于系统临时目录。

#### 历史事实、共享集成与排除

- 历史记录不变：2026-07-24 首次 legacy/versioned 比对曾有一次可能读取默认来源
  名单/X 缓存的只读 GET；2026-07-28 两次未限定路径的 `git diff --check` 可能读取
  混合工作区个人状态。两者均未输出内容、未写盘、未联网，但不能改写为“历史上从未
  读取”。
- 本次可安装化整改使用新的临时 ModuleManager、Provider、Core registry 和 tripwire；
  **隔离事故发生后完成修复；本次整改与重新验收未访问受保护路径。**
- 冻结共享文件 `TASKS.md`、README、AGENTS、API、Catalog、Core、dashboard 与两份
  架构文档均未修改。后续串行窗口需要：PK-115 暴露来源快照 Provider，Core
  composition 暴露 CollectorRegistry，移除开发态 X 双装配，Catalog/官方目录登记
  release entry，并让公共 dashboard 只加载安装包动态面板。
- 混合工作区中的 PK-010/100/110/115 及其他任务实现、`vendor/`、两份个人状态和
  所有真实来源/缓存/凭据均排除；未暂存、提交、推送、发布或清理。
- 公共契约问题：无。现有 `core.intel_contracts` 已满足 Collector `1.0` 所需
  models/protocols/registry/time；PK-120 没有请求字段或版本变化。
- PK-120 现在停在“待集成”，交新的 PK-900 做累计独立验收；`TASKS.md` 按 PK-000
  冻结要求保持原状。

## 2026-08-01 FxEmbed API v2 后备与直接父帖增量契约

### 定位与联网边界

- 本轮继续使用 PK-120，不新建任务编号。Nitter/RSS 仍是单用户言论显式采集的首选；
  FxEmbed/FxTwitter API v2 只在 Nitter 本次请求失败后作为可选后备，不替换
  `NitterCollector`，也不进入 daily briefing 的 Collector 路径。
- FxEmbed origin 固定为 `https://api.fxtwitter.com`，不接受浏览器、manifest、来源
  配置或环境提交 base URL，不新增 Token/API Key。只有“获取该日言论”“获取该日至今”
  和兼容“获取/刷新今日言论”这些明确单用户操作可以进入后备；页面加载、普通 GET、
  折叠、选日期、切换结果、保存来源与刷新资料继续零 FxEmbed 请求。
- 时间线只使用 `GET /2/profile/{handle}/statuses`，固定 `count=30`、
  `with_replies=1` 和由服务端窗口换算的 Unix `since`；不发送 cursor、
  `groupthreads`、语言或任意用户参数。单次响应上限 1 MiB、超时 10 秒。
- 同时校验 HTTP 状态与 JSON `code`；204 作为成功空页处理。429、4xx/5xx、超时、
  非法 JSON、结构异常与过大响应只形成有限内部错误码；`Retry-After` 仅接受 0～3600
  秒十进制值，不返回上游正文、Header、URL、异常正文或秘密。

### 分类、去重与一层父帖

- API v2 `status` 按明确结构映射：`replying_to` 为回复，非空 `quote` 为引用，普通
  status 为原创；`reposted_by` 为转发并排除。reply/quote/repost 标记冲突、作者不属于
  目标用户或无法证明类型的条目按 unknown 排除。仍只把 post/quote/reply 写入现有统一
  言论列表，不恢复 replies API、service、按钮、栏目或缓存。
- 先按合法 snowflake status ID、再按去 query/fragment 的规范 status URL 稳定去重；
  首个条目获胜。引用帖不补抓 quote 正文或完整对象。
- 对受关注用户自己写出的 reply，只有 `replying_to.status` 是 2～20 位十进制
  snowflake 且被回复者用户名合法时，才允许一次
  `GET /2/status/{parent_id}`。只有返回父帖的 `author.screen_name` 与
  `replying_to.screen_name` 大小写无关一致，才附加
  `parent_context={username,content,published_at,url}`；其中 username 规范为带 `@`
  的 handle，正文、aware 时间和无 query/fragment 的当前链接均有限净化。
- 每条 reply 最多一次父帖请求；单次时间线最多补抓前 8 个不同父帖，父帖并发最多 3。
  无 ID、非法 ID、作者不匹配、父帖失败或超过上限都保留关注用户自己的回复，不附加
  context。严禁 `/2/conversation/{id}`、线程分页、祖先/后代或其他完整会话抓取。

### 缓存、失败与发布输入

- 唯一持久化运行缓存仍为 `x_daily_posts.json`；FxEmbed 后备成功时沿用同一
  `XMonitorService`、Asia/Shanghai 窗口和按用户原子替换。Nitter 与 FxEmbed 双失败、
  或原子保存失败时保留旧缓存字节；日期 query 仍不持久化。
- 本轮功能性增加将可安装包版本提升为 `x_monitor@1.1.0`；确定性包继续只 allowlist
  后端、manifest 与动态面板，不包含来源名单、真实缓存、历史 replies、秘密、模型、
  vendor、fixture 或脚本。卸载保留配置和缓存，重装恢复。
- 冻结共享 `TASKS.md`、README、API、Catalog、Core、公共 dashboard 与架构文档不在
  本轮修改。完成后在本任务记录共享 README/Catalog 的串行同步内容并置“待集成”，交
  新一轮 PK-900 累计验收，不自行标记完成或发布。

### 永久隔离回归

- HTTP 仅用 `MockTransport`，路由仅用 `ASGITransport`，时钟固定且所有状态位于
  `TemporaryDirectory`。回归覆盖 post/quote/reply/repost/unknown、父帖一次、作者
  不匹配、无 ID、8 次/3 并发上限、conversation 永久禁用、200/code 错误、204、429、
  timeout、invalid JSON、oversize、Nitter 成功零 Fx、Nitter 失败后备成功、双失败和
  保存失败保留旧缓存，以及普通读取/页面状态零网络。
- protected-path tripwire 必须在真实 I/O 前保护默认来源名单、X profiles/posts/历史
  replies、`.env` 与既有个人状态，并断言临时根外零写入。
- 历史事实保持不变：2026-07-24 首次 legacy/versioned 比对可能执行过一次默认来源/X
  缓存只读 GET；2026-07-28 两次未限定路径的 `git diff --check` 可能读取混合工作区
  个人状态。两者均未输出内容、未写盘、未联网，但不得改写成“历史上从未读取”。

### FxEmbed 增量实施记录

#### 实际导出、装配与接口

- `features.x_monitor.fxembed` 新增并公开 `FxEmbedFetchError` 与
  `fetch_fxembed_posts_window()`；固定 base 为 `https://api.fxtwitter.com`，请求
  allowlist 只有 profile statuses 与单 status 两种 v2 路径。`XMonitorService` 新增
  `fxembed_query_fetcher` 注入接缝和受控 429 cooldown；`module.register()` 默认装配
  固定 FxEmbed 后备，可由 composition 的布尔开关整体停用，但没有 base URL、Token、
  Key 或浏览器配置面。
- 现有 `GET /api/v1/x/posts`、`POST /api/v1/x/posts/fetch`、
  `POST /api/v1/x/posts/query` 及三条 legacy 路径均保持，未新增 Fx/replies endpoint。
  安装包 `x_monitor@1.1.0` 继续注册原 `NitterCollector(source_id=twitter)`；Collector
  代码和 daily briefing 采集路径没有导入或调用 FxEmbed。
- `XDailyContentRepository` 只为 reply 保存经过 allowlist 归一化的
  `parent_context`，并把稳定去重加强为 status ID 或规范 URL 首项获胜；顶层仍是唯一
  `posts` channel。动态面板只在该字段存在时显示“查看直接父帖”，没有字段时保持旧
  展示；按钮、日期模式、逐用户状态与零网络普通操作均未改变。

#### 请求次数、失败与缓存证据

- 分类 fixture 的一次 timeline 含 post/quote/reply/repost/conflict/thread/duplicate，
  最终只保留 post/quote/reply；其中一条合法 reply 只产生一次父帖请求，回复正文仍为
  Alice 自己的正文，父帖只进入独立 context。作者不匹配、非法/缺失 parent ID 和父帖
  503 均不附加 context，但保留 reply。
- 11 条不同 parent 的 reply fixture 只发 8 次父帖请求，实测最高并发不超过 3；未发送
  cursor、groupthreads 或会话路径。Nitter 成功的 service fixture 断言 Fx 请求为 0；
  Nitter 失败的安装包 fixture 只发 1 次 Fx timeline 请求。429 的合法
  `Retry-After: 60` 只形成 60 秒进程内 cooldown，第二次显式操作不再次请求 Fx；非法或
  超过 3600 秒的值不保留。
- Fx timeline 成功才进入既有今日按用户原子替换。Nitter/Fx 双失败、Fx 429 cooldown、
  以及原子 `_write_atomic` 失败后，临时旧 cache 字节均保持。query 仍不落盘；没有创建
  replies 或历史查询缓存。
- 204 返回成功空页；HTTP 与 JSON code 分别覆盖 429、403、503，另覆盖 timeout、
  invalid JSON、结构异常和超过 1 MiB。异常只公开有限 code，测试上游正文/Header 中的
  `SECRET` 不出现在异常、响应或缓存。

#### 安装包与发布输入

- 确定性包版本：`x_monitor@1.1.0`；tag
  `module-x-monitor-v1.1.0`；asset `x_monitor-1.1.0.zip`。
- 最终本地确定性 asset 为 `110315` 字节，SHA-256
  `3ab7d1b0425883e7d0e8ec81ad2323d9cacbfb9af655413307611ceaa7052669`；manifest
  SHA-256 为 `aa028f6bdf1ac611f211da0c2ce5a6566cf113ac51f908acea8708c299fcd3d5`。
  两次构建字节一致，release fragment 与重建 Catalog entry 一致；未把 ZIP 写入仓库，
  未修改共享 official Catalog，未创建或上传 Release。

#### 实际验证命令与结果

- `server/.venv-asr/Scripts/python.exe tests/test_x_fxembed.py`：通过；覆盖上述协议、
  分类、父帖、并发、错误、cooldown、缓存保留、URL 去重及 tripwire。
- `tests/test_x_monitor.py`、`tests/test_x_monitor_module.py`、
  `tests/test_x_monitor_dashboard.py`：通过；module 测试额外证明安装包内 Nitter fake
  失败后只访问固定 Fx timeline，Collector fake client 保持零调用。
- `tests/test_intel_sources_integration.py`、`tests/test_intel_sources_registry.py`、
  `tests/test_intel_source_config.py`、`tests/test_installable_modules.py`、
  `tests/test_daily_briefing_module.py`、`tests/test_daily_briefing_summary_cache.py`、
  `tests/test_feature_catalog.py`、`tests/test_dashboard_shell.py`：全部通过。
- 对 X feature/service/Collector 与相关测试定向 `py_compile`：通过，pycache 指向系统
  临时目录。动态面板及公共 dashboard 当前 JavaScript 逐项 `node --check`：通过。
- protected-path tripwire 在真实 I/O 前保护默认 `intel_sources.json`、X
  profiles/posts/历史 replies、主 `.env` 及 demon/focus/calendar/fitness 状态；正式
  fallback/lifecycle 场景断言触发 `0`、系统临时目录外写入 `0`。所有业务 HTTP 为
  MockTransport/ASGITransport 或 fake fetcher，没有启动真实 API、Nitter、FxEmbed、
  QQ、LLM、TTS 或其他外部服务。

#### 历史事实、共享同步与混合工作区

- 历史只读事件与本轮证据严格区分：2026-07-24 的主应用 versioned GET 仍可能读取过
  默认来源/X cache；2026-07-28 两次未限定 diff 仍可能读取过个人状态。两条记录均保留。
  **隔离事故发生后完成修复；本次 FxEmbed 整改与重新验收未访问受保护路径。** 本轮不
  声称整个项目历史“从未读取真实数据”。
- 本轮专属修改为 `features/x_monitor/**`、`services/x_daily_cache.py`、
  `tests/test_x_fxembed.py`、`tests/test_x_monitor_module.py`、
  `tests/test_x_monitor_dashboard.py` 与本任务文件；`intel/collectors/twitter.py`、
  `services/x_profile_cache.py`、`services/x_daily_posts.py` 只做回归读取，产品字节未变。
- 共享串行窗口需要把 README 现有“不会请求父帖”的文字改为“FxEmbed 后备可为回复补
  一层经作者匹配的直接父帖，但不抓线程”，并合并本任务 release Catalog entry。若公共
  legacy dashboard 在迁移完成前仍继续展示 X，则可在 PK-100 串行窗口复用动态面板的
  `parent_context` allowlist 展示；API 路由和 Core Collector 契约不需要变化。
- `TASKS.md`、README、AGENTS、`server/api.py`、共享 dashboard、Catalog、Core 与架构
  文档按冻结要求未修改。工作区既有 `server/systems/data/demon_slayer.json`、
  `server/systems/data/focus_timer.json`、`server/runtime/`、`vendor/` 及其他任务差异未
  读取、diff、清理或覆盖；未暂存、提交、推送、切分支或发布。
- 公共契约问题：无。当前状态为“待集成”，交新的 PK-900 做累计独立验收，不自行标记
  完成。

### 本轮文档门禁

- [x] TASK_RECORD — 已记录接口、固定 origin、父帖边界、缓存、发布输入、命令和结果。
- [x] TASKS_BOARD — 按 PK-000 冻结要求不修改；本任务文件置“待集成”。
- [x] PUBLIC_README — 共享文件冻结；需串行替换的父帖限制文字已精确记录。
- [x] MODULE_CATALOG — 专属 release entry 已生成；共享 official Catalog 待串行合并。
- [x] ARCHITECTURE_DOCS — Collector 1.0 与模块边界不变，无公共契约修改。
- [x] LOCAL_README — 不适用；未改变本机路径、端口、解释器或秘密配置。
- [x] AGENT_RULES — 不适用；未改变长期协作、安全或 Git 规则。
- [x] VALIDATION — 专项、生命周期、来源集成、briefing、Catalog、dashboard、编译、
  JavaScript、tripwire、文档和定向差异门禁均按上文执行。

## 2026-08-01 控制台发帖/回复视图与原文按钮优化

- 按用户反馈，在动态 X 面板的每份 `day`/`since` 查询结果内新增“发帖（n）”与
  “回复（n）”分段按钮；`post` 与 `quote` 进入发帖视图，`reply` 进入回复视图。
  同一时刻只渲染一个视图，默认发帖；按钮只过滤已经取得的同一统一结果，不新增
  replies API/service/cache，不再次请求 Nitter/FxEmbed，也不改变唯一 posts 缓存。
- `contentView` 按用户且按 `day/since` 模式保存于当前页面内存。Bob 切换回复不会改变
  Alice 的发帖视图；页面加载、折叠、切日期、日期结果切换和发帖/回复切换继续不写
  localStorage、不中断其他用户 loading、零业务网络。
- 查询边界摘要显示当前视图条数及本次统一结果总数。空发帖或空回复视图显示明确空态，
  不把“未获取到”表述成上游账号确定没有对应内容。
- “查看原文”和“查看直接父帖”统一使用带边框、圆角、背景、内边距和焦点语义的链接
  按钮；仍以新标签页打开已净化 URL，并保留 `noopener noreferrer`。
- `tests/test_x_monitor_dashboard.py` 的 fake DOM 回归新增样式属性、ARIA 状态、默认发帖、
  回复切换零请求、跨用户隔离、父帖按钮和原文按钮断言；专项测试及 `node --check`
  通过。
- UI 变化后的确定性 `x_monitor@1.1.0` asset 更新为 `110315` 字节，SHA-256
  `3ab7d1b0425883e7d0e8ec81ad2323d9cacbfb9af655413307611ceaa7052669`；manifest
  SHA-256 仍为 `aa028f6bdf1ac611f211da0c2ce5a6566cf113ac51f908acea8708c299fcd3d5`。
  未创建 ZIP、Release、暂存、提交或推送；PK-120 继续保持“待集成”。

### 固定子栏目布局修正

- 根据最终视觉反馈，“发帖 / 回复”不再放在结果正文内部，也不等查询成功后才出现；
  现在每个用户卡片固定拥有自己的 `<nav>` 子栏目行，位置在“该日结果 / 该日至今结果”
  之后、正文之前。两项采用与来源导航一致的紧凑胶囊样式、完整圆角和明确选中态。
- 子栏目文字固定为“发帖”“回复”，数量通过各按钮的 `aria-label` 提供，不把长计数文字
  挤入胶囊。没有查询结果时栏目仍可见且为 0 条；切换日期结果时同一行同步显示对应结果
  的数量和选中态。
- fake DOM 断言 Alice/Bob 各自拥有独立固定 nav、标签顺序为“发帖/回复”、Bob 切换
  回复为零请求且不改变 Alice 当前发帖视图。视觉修正后的确定性包摘要以上述最终值为准。
