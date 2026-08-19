# PK-115 — 每日情报来源注册表与配置

- 状态：已完成
- 优先级：P1
- 所属模块：`intel_sources`
- 依赖任务：PK-001、PK-010、PK-100、PK-110
- 负责路径：`server/services/intel_source_config.py`、`server/features/intel_sources/**`、`server/tests/test_intel_source_config.py`、新建 `server/tests/test_intel_sources_*.py`、本任务文件
- 当前对话：2026-07-22 由 PK-000 批量登记并授权并行情报来源批次
- 并行阶段交接状态：共享集成待排队；不得自行修改 `TASKS.md` 或冻结共享文件

## 并行批次授权（2026-07-22）

- 共同依赖为 `docs/architecture/daily-briefing.md` 已冻结的 Collector `1.0`；需要改变契约时立即停止并交回 PK-000。
- 并行阶段只修改上述负责路径。旧 `/dashboard/intel-sources*` 接线、`server/api.py`、legacy dashboard、catalog、README 和架构文档属于冻结共享文件，留到总控串行窗口。
- 不得读取或使用真实 `server/data/intel_sources.json`；所有配置测试使用显式临时路径。PK-140 不属于本批。

## 阶段约束

- PK-110 已通过最终复核，Collector `1.0` 已冻结，本任务已由 PK-000 统一领取。
- 与各来源任务并行开发，只提供原子、脱敏、只读的配置快照；不得调用 Collector 或重新生成情报。

## 目标

独立管理 X、GitHub、B 站、YouTube、论文作者和信息差目标的本机注册表、格式校验、增删改与控制台展示，并向各 Collector 提供符合 PK-110 契约的只读配置快照。

## 数据所有权

- `server/data/intel_sources.json`，属于用户个人关注配置，必须保持本机和 Git 忽略。
- 保存、读取或列出配置不得泄露环境凭证，也不得隐式触发资料查询、采集、补采或当天缓存刷新。
- arXiv 分类/关键词、Nitter 实例和通用 RSS URL 等高级规则继续留在 `intel_config.py`，除非 PK-000 另行扩展本任务。

## 验收标准

- 新旧来源配置接口兼容，写入原子化，错误输入不会损坏旧配置。
- 各类型校验、重复处理、单条增删改和控制台行为使用临时配置测试。
- 返回 Collector 的快照符合 PK-110 冻结契约，不包含 Token、Cookie、API Key 或内部对象。
- 保存配置不重采当天情报；需要刷新必须由用户另行显式操作 PK-110。

## 并行阶段交付（2026-07-22）

### 实际导出

- `features.intel_sources.IntelSourceConfigRepository(path, replace=os.replace)`：对注入路径提供共享路径锁、唯一同目录临时文件、`flush/fsync/os.replace` 原子持久化；公开 `load()`、`save(payload)`、`mutate(callback)`，失败收敛为 `IntelSourceStateError`/`IntelSourcePersistenceError`。
- `features.intel_sources.IntelSourceRegistry(repository, defaults_provider, clock)`：公开 `read()`、`replace(payload)`、`add(field, value)`、`update(field, index, value)`、`remove(field, index)`、`snapshot(source_ids=None)`。所有写操作仅访问注入的配置 repository，不导入或调用资料查询、Collector、PK-110 gateway/service/repository/router，也不生成、补采或刷新当天缓存。
- `snapshot()` 直接复用冻结的 PK-110 `models.json_safe_mapping()` 与 `normalize_source_ids()`，返回 `MappingProxyType[str, tuple]` 的只读脱敏快照，可直接传给冻结的 `CollectRequest.source_config_snapshot`。损坏本地文件不会静默形成 Collector 快照。
- `services.intel_source_config` 保留兼容导出 `LIST_FIELDS`、`default_intel_sources()`、`normalize_intel_sources()`、`load_intel_sources()`、`save_intel_sources()`，新增 `get_intel_source_snapshot()`。
- 配置 Schema 固定为 `schema_version=1`；九个字段为 `twitter_users`、`money_twitter_users`、`github_users`、`github_repos`、`bilibili_uids`、`youtube_channel_ids`、`paper_priority_authors`、`paper_secondary_authors`、`paper_ai_authors`。未知字段、秘密形态字段、错误 Schema、非法格式和单组超过 500 项均在写入前拒绝；大小写去重保留首次顺序。

### 数据与副作用

- 正式数据所有权仍是忽略的 `server/data/intel_sources.json`；本阶段未读取或写入该生产路径。全部持久化验证只使用系统临时目录中的同名文件与虚构目标。
- 存储仅包含九组目标、`schema_version` 和带时区 `updated_at`。响应另含 `using_local_override`，按需含 `changed`/有限 `load_warning`；不落盘凭证、headers、Collector 快照、资料缓存或 PK-110 缓存。
- 损坏文件的普通管理读取返回代码默认值和有限 `load_warning`，不打印异常正文且不覆盖原文件；Collector 快照读取明确失败，由调用方按单源失败隔离。
- 保存配置没有刷新语义；PK-110 generate/refresh 只能由用户另行显式操作。

### 共享串行窗口接入清单

以下内容尚未修改共享文件，等待 PK-000 分配串行窗口：

- API：在共享装配中增加本机限定 `GET /api/v1/intel-sources`（`read`）、`PUT /api/v1/intel-sources`（`replace`）、`POST /api/v1/intel-sources/{field}`（`add`）、`PUT /api/v1/intel-sources/{field}/{index}`（`update`）、`DELETE /api/v1/intel-sources/{field}/{index}`（`remove`）；legacy `GET/PUT /dashboard/intel-sources` 委托同一 registry。只读 Collector 快照仅为进程内 Python 接口，不增加浏览器端点。
- API 错误：格式、重复和索引错误映射 422；原子持久化失败映射 500 且只返回固定有限文案。任何写接口都不得串接资料 resolve、PK-110 generate/refresh 或缓存删除。
- 控制台字段：消费九个列表字段、`schema_version`、`using_local_override`、`updated_at`，并显示可选 `changed`/`load_warning`；不显示或存储 Cookie、Token、API Key、headers、完整错误体或内部对象。
- 控制台事件：面板挂载只触发只读 `intel-sources:load`；单条成功操作触发 `intel-sources:changed`，detail 仅含 `field/operation/index/changed`，用于重读和渲染，不触发资料查询或情报生成。“重新生成今日情报”继续是独立、显式确认后的 PK-110 事件，不能由保存事件级联。
- 控制台兼容：保留现有 `intel-sources` panel ID 与独立展开/收起。资料头像和 X 今日言论 resolve/fetch 按钮仍属对应来源任务，不并入 PK-115 保存事件。
- catalog/文档：串行更新 `server/features/catalog/service.py`、`README.md`、每日情报/模块架构说明与完成文档门禁；`TASKS.md` 只由总控同步。

### 专属验证记录

- `server/.venv-asr/Scripts/python.exe tests/test_intel_sources_registry.py`：通过。覆盖九组格式/Schema/未知字段、去重、单条增改删、重复与越界保护、冻结 `CollectRequest` 快照兼容和不可变性、替换失败保留旧字节且清理临时文件、损坏文件不覆盖、12 线程同路径原子写，以及禁止导入 PK-110 gateway/service/repository/router/具体 Collector。
- `server/.venv-asr/Scripts/python.exe tests/test_intel_source_config.py`：本任务实现后首次运行通过，配置位于临时目录且资料/采集函数均为 fake；最终并行复跑被本任务范围外新建的 `features/bilibili/__init__.py` 在项目 Python 3.8 下导入失败阻断（`__all__: list[str]`），尚未进入 PK-115 断言。
- `server/.venv-asr/Scripts/python.exe tests/test_daily_briefing_module.py`：本任务实现后首次运行通过（固定时钟、临时 cache、fake gateway/PK-200）；最终并行复跑同样在导入上述 Bilibili 包时提前失败。PK-115 未越权修改该并行任务路径，需其所有者修复 Python 3.8 兼容后由串行窗口重跑。
- `server/.venv-asr/Scripts/python.exe -m py_compile features/intel_sources/__init__.py features/intel_sources/models.py features/intel_sources/repository.py features/intel_sources/service.py services/intel_source_config.py tests/test_intel_sources_registry.py`：通过。
- 专属路径尾随空白检查与全工作区 `git diff --check`：通过；后者仅报告混合工作区既有 LF/CRLF 提示。未运行真实 HTTP、真实 Collector、真实资料查询、真实 LLM/TTS/QQ 或真实配置/缓存测试。

### 公共契约结论

- 没有 Collector `1.0` 公共契约问题；PK-115 只消费冻结的 `models` 清洗/ID 规则与 `CollectRequest.source_config_snapshot`，未要求改变字段、版本或依赖方向。
- 当前缺口仅是共享 API/UI/catalog/文档的串行接入，不构成公共契约变更；本任务停在“共享集成待排队”，不得提前改成“待集成”。

## 独立对话启动提示

```text
仅在 PK-110 已完成并冻结 Collector 契约后领取 PK-115。只处理来源注册表、
格式校验、原子本机配置和控制台管理；不得读取真实关注名单、调用任何 Collector、
刷新当天情报或修改各来源采集规则。
```

## PK-119 事后复核与共享收口（2026-07-22）

- 复核确认 registry/repository 的实际接口、原子写入和只读快照与上文记录一致；生产装配已新增本机受控的 `/api/v1/intel-sources*`，legacy `/dashboard/intel-sources*` 委托同一单例 registry，保存来源不会触发采集或刷新。
- PK-131 指出的 YouTube 契约差异已做最小修复：注册表现在只接受 `UC` 加 22 位合法字符，并同步临时配置测试；这不改变 Collector `1.0`。
- 控制台已改用版本化来源管理接口，catalog、README 与架构文档已按实际能力登记。真实 `server/data/intel_sources.json` 未读取、写入或纳入差异。
- 原记录中的 Bilibili Python 3.8 导入阻断已经由实际代码修复；本次重跑 `test_intel_sources_registry.py`、`test_intel_source_config.py`、`test_intel_sources_integration.py` 及共享回归通过。遗留事项仅为 PK-900 独立验收与部署后重启进程。

## PK-011 生命周期整改（2026-07-31）

- `intel_sources@1.1.1` 现按身份清理本实例路由、registry/read/snapshot Provider 与
  module state；若宿主预先注入 Provider，卸载恢复原对象而非删除。两阶段 router
  注册任一步失败都会移除已经添加的路由。

## 完成文档门禁

- [x] TASK_RECORD — 已按实际代码补记接口、数据副作用、共享装配、验证和遗留事项。
- [x] TASKS_BOARD — PK-115 已由 PK-000 统一登记为“待集成”。
- [x] PUBLIC_README — 已登记版本化来源管理与兼容入口。
- [x] MODULE_CATALOG — 已登记 `intel_sources` 的实际接口和边界。
- [x] ARCHITECTURE_DOCS — 已登记 registry、生产 Collector 组合及兼容关系。
- [x] LOCAL_README — 不适用；未改变本机路径、端口或解释器约定。
- [x] AGENT_RULES — 不适用；未改变长期 agent 规则。
- [x] VALIDATION — 专属、PK-119 集成及 PK-110/catalog/dashboard 共享回归通过；最终差异检查由 PK-119 记录。

## PK-000 最终复核（2026-07-22）

PK-900 报告及实际原子失败/并发写、配置保存零采集、Origin 与共享回归均经独立复核通过；PK-115 置为“已完成”。

## PK-011 可安装化增量（2026-07-30）

### 冻结依赖

- PK-110 已明确冻结 `server/core/intel_contracts/**`。本模块只从
  `core.intel_contracts` 导入 `json_safe_mapping` 和 `normalize_source_ids`；
  不再导入 `features.daily_briefing.models/collector_contracts/time_utils`，也不导入
  PK-110 的 gateway、service、repository 或 router。
- Collector `1.0` 类型身份与兼容 re-export 已由 PK-110 定向回归确认。PK-115
  没有要求改变字段、source ID、快照语义或契约版本；破坏性变更仍须提升 major
  并交回 PK-000。

### 实际导出与包表面

- 本模块实际导出 Collector 数量为 `0`；它只提供来源配置与只读快照，不注册、
  创建或调用任何 Collector。
- Python 公共表面保留 `IntelSourceConfigRepository`、
  `IntelSourceRegistry.read/replace/add/update/remove/snapshot`、
  `create_intel_sources_router()`，并新增
  `create_legacy_intel_sources_router()` 与 `register(app)`。
- `register(app)` 注册 `/api/v1/intel-sources*` 和 legacy
  `GET/PUT /dashboard/intel-sources`，两者使用同一个 registry。重复调用幂等；
  若宿主已经存在相同 method/path，则在加入任何新路由前明确失败，禁止重复路由。
- 进程内 Provider 接缝为 `app.state.intel_source_registry`、
  `app.state.intel_source_config_reader` 和
  `app.state.intel_source_snapshot_provider`。宿主可在加载前注入同一 registry，
  或注入 `intel_source_config_path`、`intel_source_defaults_provider` 和
  `intel_source_local_control_guard`。未注入 guard 时 HTTP 默认拒绝。
- manifest：`intel_sources@1.1.0`、`in_process`、
  `entrypoint=backend.register`、`data_namespace=intel_sources`、
  `permissions=["local_state"]`、`requires_restart=true`；无业务模块依赖，
  只依赖 Core Collector 契约。
- 确定性构建入口：
  `python -m features.intel_sources.package_builder <new-dir-or-zip>`。包为显式白名单：
  `manifest.json`、六个 `backend/*.py` 与 `dashboard/index.js`；固定排序、时间戳、
  权限、LF 和 `ZIP_STORED`，不执行安装/卸载脚本。
- Release 输入冻结为 tag `module-intel-sources-v1.1.0`、asset
  `intel-sources-1.1.0.zip`、package SHA-256
  `ee9ca29def7aad20dbaec4dc15e4c8150f6d29b05d3fac7ca54f597ad82907c3`、
  manifest SHA-256
  `49334bf56f3494e1345e4feb949c313eade541c060d7c54012310ebcb54d750b`、
  size `34920` bytes。只写入本任务 release 片段和候选条目，未修改官方 Catalog、
  未创建 Release、未上传资产。

### 动态来源管理面板

- 动态入口只导出 `mount(context)` / `unmount()`，只在传入的 `context.root`
  内构建 DOM，不使用 `document.querySelector`、`localStorage`、
  `sessionStorage` 或全局 `fetch`。
- 字段固定为九组：
  `twitter_users`、`money_twitter_users`、`github_users`、
  `github_repos`、`bilibili_uids`、`youtube_channel_ids`、
  `paper_priority_authors`、`paper_secondary_authors`、
  `paper_ai_authors`。
- 面板挂载和“重新读取”只调用 `GET /api/v1/intel-sources`；“保存来源配置”
  只调用 `PUT /api/v1/intel-sources`。保存成功明确提示没有触发资料查询、Collector、
  每日情报生成或缓存刷新。资料头像、X 言论、B 站参数与 briefing 刷新不属于本入口。
- 本轮没有修改共享 `dashboard.html`。旧的 `intel-sources:load` /
  `intel-sources:changed` 事件属于 legacy 控制台迁移接缝；动态入口通过自身
  `mount/unmount` 生命周期和受限 `context.request/notify` 完成，不向页面广播名单。

### 数据、安全与生命周期

- 真实 `server/data/intel_sources.json`、真实来源名单、Cookie、Token、API Key、
  `.env`、状态、缓存、模型、vendor 和脚本均未读取、未复制、未打包。
- 所有新增运行测试注入系统临时 `intel_sources.json`。页面加载、配置读取与保存
  仅访问该 repository；网络 tripwire 覆盖 API 测试，动态入口测试使用 fake
  `context.request`。
- 卸载由 Core 只移除程序版本；历史配置路径不进入 ZIP，也不进入模块程序目录。
  测试确认停用/卸载并重启后路由和 Provider 不加载，配置字节保持不变；重装启用
  并重启后重新关联同一配置。
- 原子失败覆盖两层：registry 的 `os.replace` 失败保留旧字节并清理临时文件；
  ModuleManager 摘要错误时不写 registry、不创建 runtime 或 data 目录。

### 专属修改路径

- `server/features/intel_sources/__init__.py`
- `server/features/intel_sources/models.py`（PK-110 授权的 Core import 迁移）
- `server/features/intel_sources/module.py`
- `server/features/intel_sources/package_builder.py`
- `server/features/intel_sources/package_source/**`
- `server/features/intel_sources/release/**`
- `server/features/intel_sources/repository.py`
- `server/features/intel_sources/router.py`
- `server/tests/test_intel_sources_installable.py`
- `server/tests/test_intel_sources_dashboard.py`
- `tasks/PK-115-intel-source-registry.md`

### 验证记录

- `server/.venv-asr/Scripts/python.exe tests/test_intel_sources_registry.py`：通过。
- `server/.venv-asr/Scripts/python.exe tests/test_intel_sources_installable.py`：通过。
- `server/.venv-asr/Scripts/python.exe tests/test_intel_sources_dashboard.py`：通过。
- `server/.venv-asr/Scripts/python.exe tests/test_intel_source_config.py`：通过，
  资料失败分支均为 fake。
- `server/.venv-asr/Scripts/python.exe tests/test_intel_sources_integration.py`：通过，
  使用保护路径 tripwire、fake/MockTransport 和临时状态。
- `server/.venv-asr/Scripts/python.exe tests/test_installable_modules.py`：通过。
- 临时目录执行 `features.intel_sources.package_builder` 与
  `scripts/build_official_module_catalog.py`：通过；release fragment、ZIP 摘要、
  manifest 摘要和体积与本任务候选 Catalog 条目一致。
- Python 3.8 `py_compile` 与 `node --check`：通过。
- 项目 `scripts/python.ps1` 因本机 PowerShell execution policy 无法执行；按项目
  既有兼容方式改用同一 `.venv-asr` 解释器直接运行，不属于代码失败。
- `python scripts/check_python_test_inventory.py`：当前混合并行工作区报告 17 个
  新测试文件尚未进入共享 `python-test-inventory.json`，其中包含本任务两个测试
  和其他 15 个并行模块测试。本任务按冻结要求未修改该共享清单；须由 PK-000
  在串行窗口统一刷新后复跑。Python 3.8 环境另缺少 `tomllib/tomli`，已用本机
  Python 3.12 获得上述确定性清单差异。

### 共享串行窗口待办

- `server/api.py`：移除当前内置的版本化 router 与 legacy
  `GET/PUT /dashboard/intel-sources` 定义；在模块加载前只注入历史
  `INTEL_SOURCES_PATH`、`default_intel_sources` 和本机控制 guard，让启用包创建
  唯一 registry。不得同时保留内置与安装包路由。
- PK-110/daily briefing 组合层和各来源消费者：每次新采集开始时通过
  `app.state.intel_source_snapshot_provider` 获取只读快照；Provider 缺失时使用
  明确的模块缺失/空配置降级，不静态导入 PK-115 内部实现。
- `server/features/catalog/service.py` 与官方 Catalog：串行登记
  `intel_sources@1.1.0` 的 installable 状态和上述 release 条目。
- `server/static/dashboard.html`：不再拥有来源管理业务实现；由模块目录加载
  `dashboard/index.js`。若迁移期保留 legacy 面板，必须避免同时挂载两个可写面板。
- `README.md` 与架构文档：登记安装、启停、卸载保留配置、重装恢复、重启要求、
  Provider 缺失降级和“配置保存零采集”边界。
- `TASKS.md` 仍只由 PK-000 更新；本任务没有修改。

### 公共契约结论与当前状态

- 不存在新的 Core/Collector 公共契约问题；冻结导出足以实现只读快照。
- 需要的剩余工作都是共享装配、Catalog、dashboard 和文档串行接入，不要求改变
  manifest schema、ModuleManager、Core Collector `1.0` 或数据格式。
- 本增量停在“共享集成待排队 / 待集成”，不执行暂存、提交、推送、Release
  或任何清理操作。

## PK-011 注册失败原子回滚补充（2026-07-31）

- 第二轮独立 PK-900 在发布 `intel_source_snapshot_provider` 时注入异常，复现此前
  `intel_source_registry` 与 `intel_source_config_reader` 已写入 `app.state` 却未
  恢复。现 register 在写入前保存 registry、reader、snapshot provider、registered
  标记与 registration owner 的逐项旧值；任一发布失败时移除本轮路由并完整恢复，
  缺失字段则删除。成功 unregister 同样按本实例拥有值恢复，宿主预置值不被清除。
- 永久回归使用正式 `intel_sources` 包、临时 state 和写入故障对象，在真实 Loader
  中验证 provider 中途失败后 routes/state/动态 import 树全部恢复。无真实配置、
  来源名单或网络访问。
- 包内容变化按不可变资产规则提升为 `intel_sources@1.1.2`：候选
  `intel-sources-1.1.2.zip` 为 37495 字节，SHA-256
  `8da2335c3837795cb2587130948e69fe10ece7aa2bd8d17aed86812d59525850`，manifest
  SHA-256 `ba8354949be3de0304797acc6fb92fb049b90d1450550d929cddb9b6c9920362`。
  官方目录已从实际 ZIP 重建；该候选尚未发布，状态保持“待集成”。

## 2026-08-01 控制台只读来源恢复

- 实机发现生产组合把 `GET /api/v1/intel-sources` 与 legacy GET 也绑定到写操作 Origin/CSRF guard；同源控制台普通 GET 因没有写请求 Origin 而收到 403，表现为来源配置文本框全部为空。真实 `server/data/intel_sources.json` 始终存在且未被迁移、覆盖或清空。
- Router 现分别接收 `local_read_guard` 与 `local_control_guard`：两个 GET 仅要求可信 loopback peer；PUT/POST/DELETE 继续要求 loopback 与可信同源 Origin。安装包缺少新 read guard 时仍回退到旧 guard，保持既有测试装配兼容。
- 修复包提升为 `intel_sources@1.1.3`：`intel-sources-1.1.3.zip` 为 38,459 bytes，SHA-256 `33514dffa48257c42b4505be98d4fe0659bd074b2d83590a56aaf6b731f82e24`，manifest SHA-256 `e349a1c09b8f1b3796610bc5cb1d7afac76abe85b227c45a29af74d21ada81d0`。本机生命周期更新后七类已配置来源重新可见；验收只统计每类数量/字段长度，没有打印真实名单。
- 永久回归证明 read guard 可以独立放行 GET，而写 guard 仍独立拒绝恶意 Origin；来源集成、installable 与控制台专项通过。

## 分来源配置界面收口（2026-08-01）

- 保持 `/api/v1/intel-sources` 读写契约、原子保存和零采集语义不变；仅将 X、B 站、GitHub、论文字段分别投放到对应动态子页，来源总览保留 YouTube 字段。
- 配置 DOM 仍由 `intel_sources` 单一模块拥有，公共外壳只按 `data-module-config-target` 移动已挂载节点；卸载或重载所有者时同步清除投放节点，不向消费者复制 repository/service/API 规则。
- 官方候选提升为 `intel_sources@1.1.5`：`intel-sources-1.1.5.zip` 为 40,496 bytes，SHA-256 `34a063a4108ec2ac1a477596ab994e557811a22fe3d45ce4b349b3fbae3ee9dc`，manifest SHA-256 `9d74da0a75d89006c9c0b008919f3baefd9cb83f6b6dee65e03947d8c13585b1`。
- 本轮只读取配置接口并核对字段存在性/数量，不打印名单，不触发 Collector，也不修改来源 API。

## Windows 并发原子写入重试整改（2026-08-08）

### 根因与边界

- 远端 Windows Actions run `31263724750` 仅在 Python 3.10 的
  `check_concurrent_atomic_writes` 中出现一次
  `IntelSourcePersistenceError`。复核确认不同 repository 实例会按规范化目标路径共用同一个
  `RLock`，`NamedTemporaryFile(delete=False)` 也为每次保存创建同目录唯一临时文件；不存在两个
  线程覆盖同一临时文件或绕过 read-modify-write 锁的缺陷。
- 缺口位于替换阶段：Windows 可能在杀毒/索引器短暂持有目标或新临时文件时，让
  `os.replace` 返回 WinError `5`、`32` 或 `33`；旧实现把首次短暂共享冲突直接升级为持久化失败。
- repository 现在只对上述三个 Windows 错误码执行 `10/25/50/100ms` 的四次有界退避，且重试期间
  始终持有同一路径锁。无 `winerror`、其他错误码以及超过重试预算的错误仍立即收敛为
  `IntelSourcePersistenceError`；失败时目标文件字节不变并清理本次临时文件。未加入无限重试、网络、
  Collector 调用或真实配置回退。

### 永久回归与数据隔离

- 新增 fake replace 正向/逆向：WinError `32` 前两次失败、第三次成功；WinError `33` 连续失败时
  精确尝试五次后终止并保留稳定旧值；普通 `OSError` 继续不重试。
- 并发用例以 12 方 barrier 同时起跑，为每个唯一临时文件注入一次 WinError `5`，验证每个写入都只
  尝试两次、最终 JSON 可规范化、同目录无临时文件残留；同一用例额外连续运行 30 轮全部通过。
- 所有配置路径均来自 `TemporaryDirectory`。未读取、diff、打印或修改真实
  `server/data/intel_sources.json`、来源名单、Cookie、Token、缓存或个人状态；配置保存仍为零网络。

### 安装包与串行接缝

- backend 变更按不可变包规则提升为 `intel_sources@1.1.6`，Release tag
  `modules-2026.08.08`，asset `intel-sources-1.1.6.zip`，大小 `41,312` bytes，package
  SHA-256 `db96595b58347959ca3506453700373362c6e237a5da6c5edda09eb649f28bda`，manifest
  SHA-256 `4b4dcb6c503c9fa21720e9ec9c4fa64703d50a3b5c19888822bddb09c821cfcb`。
- PK-115 专属 builder、manifest、release fragment 与 candidate entry 已同步。共享
  `server/core/modules/official-catalog.json` 未由本任务越权修改，须由 PK-000 串行窗口用上述 entry
  更新后重跑 19 包累计确定性校验，再交远端 Python 3.10 矩阵复验。

### 实际验证

- `server/.venv-asr/Scripts/python.exe tests/test_intel_sources_registry.py`：通过。
- `server/.venv-asr/Scripts/python.exe tests/test_intel_sources_installable.py`：通过；两次构建字节一致，
  allowlist、无秘密/真实状态与 release 摘要一致。
- 同一隔离解释器直接连续运行 `check_concurrent_atomic_writes()` 30 轮：`30/30` 通过。
- 当前系统 Python 带 pytest 但缺 FastAPI，项目 `.venv-asr` 带运行依赖但未安装 pytest；因此本任务
  未把本机直接脚本结果冒充 pytest。最终 pytest/远端 Python 3.10 结果由 PK-900 在共享串行同步后复跑。
- 本轮未修改 `TASKS.md`、PK-900、共享 Catalog、README、AGENTS 或本机 README，未执行 Git 暂存、
  提交、推送、清理或真实服务/网络操作。
