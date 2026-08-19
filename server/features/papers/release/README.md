# Papers official release handoff

本目录冻结 `papers@1.0.0` 的官方发布输入。确定性 ZIP 不进入仓库，只能在系统
临时目录构建。发布、Catalog 合并、上传与 Git 操作均由 PK-000 在累计验收后执行。

包内包含 arXiv、Crossref、Semantic Scholar 的 Collector 1.0 正式实现、唯一共享
HTTP runtime 接缝、只读今日论文投影和显式刷新面板。它依赖 `intel_sources`，但不
打包或读取作者名单、查询规则、缓存、凭据、`.env`、vendor 或脚本。

包可以在空宿主 state 下自举 Core `CollectorRegistry` 与唯一
`PaperHttpRuntime`，并把二者写回 `app.state`。如果迁移期仍有 legacy 论文入口，
宿主可以注入同一个 duck-typed runtime，安装包会消费它而不会创建或关闭第二实例。

宿主串行集成可注入：

- `app.state.intel_collector_registry`：已有 Core `CollectorRegistry`；缺失时包内创建。
- `app.state.papers_http_runtime`：迁移期与 legacy 共用的唯一论文 runtime；缺失时包内创建。
- `app.state.papers_today_provider`：只读当天 briefing 公共投影。
- `app.state.papers_refresh_provider`：显式刷新三个论文 source ID。
- 可选 arXiv 查询、期刊、Semantic Scholar Key、固定时钟及本机请求 guard provider。

`app.state.papers_module_close` 是幂等 async 解注册/关闭接缝，并同时注册为 shutdown
handler：它总会从 registry 移除本包三个 Collector，只关闭包内自有 runtime，不关闭
宿主注入 runtime。Core 不需要也不得导入 `features.papers.http`。

普通面板加载只调用 `GET /api/v1/papers/today`，不得联网或写缓存。刷新必须在面板
二次确认后调用 `POST /api/v1/papers/refresh`。卸载保留 `papers` 数据命名空间和现有
arXiv 缓存；启用、停用、卸载和重装后的运行态变化均须重启 API。
