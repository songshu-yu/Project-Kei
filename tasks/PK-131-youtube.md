# PK-131 — YouTube 频道采集

- 状态：待集成
- 优先级：P2
- 所属模块：`youtube`
- 依赖任务：PK-001、PK-010、PK-100、PK-110、PK-115
- 负责路径：`server/intel/collectors/youtube.py`、`server/features/youtube/**`、新建 `server/tests/test_youtube_collector.py` 或 `test_youtube_feature_*.py`、本任务文件
- 当前对话：2026-07-30，PK-011 可安装化增量已完成专属实现与隔离验证，等待共享集成
- 并行阶段交接状态：共享集成待排队；未修改 `TASKS.md`，等待 PK-000 分配串行窗口

## 并行批次授权（2026-07-22）

- 共同依赖为 `docs/architecture/daily-briefing.md` 已冻结的 Collector `1.0`；需要改变契约时立即停止并交回 PK-000。
- 并行阶段只修改上述负责路径。API、legacy briefing、旧控制台、catalog、README、架构文档和来源配置均留到总控串行窗口或 PK-115。
- 现有联网 debug 脚本、真实频道和真实网络不用于自动测试；PK-140 不属于本批。

## 阶段约束

- PK-110 已通过最终复核，Collector `1.0` 已冻结，本任务已由 PK-000 统一领取。
- 来源配置归 PK-115；本任务只消费只读 Channel ID 快照并返回规范化结果。

## 目标

独立管理 YouTube Channel ID 的公开 Atom/RSS 采集、条目解析、时间规范化、稳定 ID、节流和失败表达，并实现 PK-110 Collector 契约。

## 数据所有权

- Channel ID 列表归 PK-115；当前采集结果只作为 PK-110 输入。
- 若未来增加来源缓存，必须保持模块本地、Git 忽略并经 PK-000 确认，不能复用其他来源状态文件。

## 验收标准

- 严格区分 Channel ID、频道昵称与 handle；无效 ID 不触发任意 URL 请求。
- Feed 解析、发布时间、重复条目、空 Feed、超时和错误状态全部用假 HTTP 测试。
- 不以真实 YouTube 请求作为自动验收，不修改 PK-110 汇总或其他来源。

## 并行阶段工作记录（2026-07-22）

### 实际导出

- `features.youtube.YouTubeCollector`：结构化实现冻结的 `Collector 1.0`，`source_id="youtube"`；只读取 `CollectRequest.source_config_snapshot["youtube_channel_ids"]`，返回 `CollectorResult`、`IntelItem` 与 `SourceCoverage`。
- `features.youtube.create_collector(**kwargs) -> Collector`：以冻结的 `collector_contracts.Collector` 类型导出构造入口。
- `validate_channel_id` / `is_channel_id`：只接受 `UC` 加 22 位 `[A-Za-z0-9_-]`；频道名称、`@handle`、频道 URL、长度或大小写错误均在 HTTP 前拒绝。
- `parse_youtube_timestamp`：把带显式时区的 Atom 时间规范为 UTC RFC 3339；naive/无效时间不伪造时区。
- `youtube_video_stable_id`：只接受 11 位 YouTube video ID，并通过冻结的 `stable_item_id()` 生成 `youtube:<sha256-prefix>`；标题、频道显示名或 Feed 顺序变化不改变同一视频 ID。
- `fetch_youtube`、`YouTubeVideo`、`YouTubeResult`、`NS`：由 `server/intel/collectors/youtube.py` 继续兼容导出；legacy facade 内部委托同一 Collector，不复制第二套 Feed 解析。

### 已交付行为与边界

- 所有请求固定为 `https://www.youtube.com/feeds/videos.xml?channel_id=<validated-id>`；Channel ID 只作为 query 参数，不接受调用者 URL。默认 `trust_env=False`，公开 Feed 不读取 Cookie、Token、API Key 或代理环境凭据。
- Atom Feed 必须声明与请求一致的 `yt:channelId`；entry 的 `yt:channelId` 也不得串台。解析 `yt:videoId`、title、author、published/updated、alternate link、description 与 thumbnail，输出 `video` 分类的规范化条目。
- 按 `CollectRequest.lookback` 过滤过旧和超过当前时间五分钟的条目；缺失发布时间保持为空，不伪造。相同 video ID 跨 Feed/重复 entry 以稳定 ID 去重，每频道执行上限。
- 多频道串行请求并保留可注入节流；`complete/empty/partial/failed/not_configured` 与 `fetched/refreshed` 按冻结语义返回。warning 不包含 HTTP 响应正文、异常正文或失败频道 ID。
- 没有新增缓存、状态文件、路由、配置写入、常驻进程或端口。自动测试未读取真实来源名单、缓存、`.env`、Cookie、Token 或 API Key，也未访问真实 YouTube。

### 专属修改路径

- `server/features/youtube/__init__.py`
- `server/features/youtube/collector.py`
- `server/intel/collectors/youtube.py`
- `server/tests/test_youtube_collector.py`
- `tasks/PK-131-youtube.md`

### 验证

- 通过（工作目录 `server/`）：`.\.venv-asr\Scripts\python.exe tests\test_youtube_collector.py`；全程使用 `httpx.MockTransport`，覆盖非法 ID 零请求、固定 Feed URL、Atom 解析、Feed/entry Channel ID 一致性、时区归一、lookback、重复条目、稳定 ID、空 Feed、超时、HTTP 错误、部分/失败 coverage、节流与 legacy facade。
- 通过（工作目录 `server/`）：`.\.venv-asr\Scripts\python.exe -m py_compile features\youtube\__init__.py features\youtube\collector.py intel\collectors\youtube.py tests\test_youtube_collector.py`；实际解释器为 Python 3.8.20。
- 通过：全工作区 `git diff --check` 退出 0（仅报告既有 LF→CRLF 警告）；专属路径尾随空白扫描无匹配，禁止的 PK-110 gateway/service/repository/router 反向导入扫描无匹配。
- 未完成的旁路回归：`test_intel_source_config.py` 在导入另一并行任务的 `server/features/bilibili/__init__.py` 时即因 Python 3.8 不支持运行时求值的 `list[str]` 报 `TypeError`，尚未进入 YouTube 路径；PK-131 未越权修改该路径，需由 PK-130/PK-000 在共享集成前处理后重跑。

### 共享串行窗口待写入/接线

- `server/intel/briefing.py`：现有 `fetch_youtube(channel_ids, max_per_channel=...)` 导入可继续工作；串行集成时可选择把 PK-110 gateway 注册切到 `create_collector`/`YouTubeCollector`，但不得改变 Collector 1.0。
- PK-115 来源注册表：当前并行实现中的 YouTube 校验仍允许泛 `[A-Za-z0-9_-]{3,128}`；为避免控制台保存“像名称但不是 Channel ID”的值，串行协调时应与本任务相同，收紧为 `UC[A-Za-z0-9_-]{22}`。这不是 Collector 公共契约变更。
- `server/features/catalog/service.py`：如总控把 YouTube 登记为独立内置来源模块，补充模块/任务映射、当前 legacy 入口与 `Collector 1.0` 进程内边界。
- `README.md`：记录只接受 Channel ID（非名称/handle/URL）、使用公开 Atom Feed、无凭据、失败/空 Feed 语义，以及 fake 测试命令。
- `docs/architecture/daily-briefing.md`：仅补充非破坏性实现说明和 YouTube 导出入口；冻结字段、source ID、兼容/版本规则不变。`AGENTS.md`、`README.local.md` 和旧控制台当前无内容需要改动。

### 公共契约与遗留问题

- Collector `1.0` 公共契约问题：无。实现只导入冻结的 `collector_contracts.py` 与 `models.py`，未导入 PK-110 gateway、service、repository 或 router，也未要求增加或改变公共字段。
- 共享集成前遗留：协调 PK-115 的 Channel ID 校验、处理上述 PK-130 Python 3.8 导入阻断并重跑来源配置回归；由 PK-000 决定 legacy gateway/catalog/README/架构文档的串行接线。

## 独立对话启动提示

```text
仅在 PK-110 Collector 契约冻结后领取 PK-131。只处理 YouTube Channel ID、
公开 Feed 和规范化 Collector；使用假 HTTP 测试，不访问真实频道，不修改来源
注册表、PK-110 汇总或其他平台采集器。
```

## PK-119 事后复核与共享收口（2026-07-22）

- 复核确认 `YouTubeCollector` 是无独立 HTTP 路由/缓存的 Collector adapter，只在 PK-110 显式采集时读取只读 Channel ID 快照并访问公开 Atom Feed；legacy facade 继续委托同一实现。
- 已通过统一 `ProjectCollectorGateway` 注册到 `youtube`。PK-115 的宽松校验已按本任务公开契约收紧为 `UC[A-Za-z0-9_-]{22}`，避免保存后才在 Collector 层失败；这是局部配置一致性修复，不改变 Collector `1.0`。
- catalog、README 和架构文档已登记实际能力。`test_youtube_collector.py`、来源注册表测试、PK-119 集成及共享回归通过；没有读取真实频道名单、环境凭证或发起真实 YouTube 请求。
- 原并行记录中的 Bilibili Python 3.8 导入阻断已关闭。遗留仅为 PK-900 独立验收与部署后重启。

## PK-011 生命周期整改（2026-07-31）

- `youtube@1.0.1` 现公开身份绑定、幂等 `unregister(app)`；Collector 仅按对象身份
  从 Core registry 解除，模块自建 registry 仅在仍为空且仍由本实例持有时删除。
  注册失败会回滚 Collector/state；正式包 loader/coordinator load→unload 无残留。

## 完成文档门禁

- [x] TASK_RECORD — 已按实际代码补记导出、网络副作用、生产注册、局部契约修复、验证与遗留。
- [x] TASKS_BOARD — PK-131 已由 PK-000 统一登记为“待集成”。
- [x] PUBLIC_README — 已登记 Channel ID/公开 Feed/无凭据边界。
- [x] MODULE_CATALOG — 已登记 `youtube` Collector adapter。
- [x] ARCHITECTURE_DOCS — 已登记 `youtube` 生产装配与校验边界。
- [x] LOCAL_README — 不适用；未改变本机路径、端口或解释器约定。
- [x] AGENT_RULES — 不适用；未改变长期 agent 规则。
- [x] VALIDATION — 专属、registry、PK-119 集成及共享回归通过；最终差异检查由 PK-119 记录。

## PK-000 最终复核（2026-07-22）

PK-900 报告及实际严格 Channel ID、假 Feed、八源 dispatch 与失败隔离回归经独立复核通过；PK-131 置为“已完成”。

## PK-011 可安装化增量（2026-07-30）

### 实际导出与包边界

- `features.youtube.register(app)` 是 `backend.register(app)` 的源码入口。它只依赖
  `core.intel_contracts.CollectorRegistry`，在
  `app.state.collector_registry` 注册一个 `source_id="youtube"` 的 Collector；
  同一应用重复注册保持幂等，已有不同 Collector 的同 source ID 冲突继续由 Core
  registry 拒绝。
- `app.state.youtube_collector_provider` 是无参数 Provider 接缝，供应用装配或测试
  注入 Collector 1.0 实例。缺失时构造 `YouTubeCollector`；构造和注册均不读取
  Channel ID、来源配置或缓存，也不发起 HTTP。已注册实例公开在
  `app.state.youtube_collector`，装配标记为
  `app.state.youtube_module_registered`。
- `features.youtube.package_builder.build_youtube_package(destination,
  version="1.0.0")` 构建可审阅目录或确定性 ZIP，并导出官方版本、tag、asset 与
  SHA-256 helper。同一输入两次构建字节和摘要完全一致。
- 包只含 `manifest.json`、`backend/__init__.py`、`backend/collector.py`、
  `backend/module.py`。manifest 为 `youtube@1.0.0`、`in_process`、依赖
  `intel_sources`、安装后默认停用、生命周期变更需重启；不声明 API namespace、
  legacy endpoint、动态面板或权限。
- 不提供独立动态面板是有意边界：Channel ID 的管理面和版本化 HTTP API 属于
  `intel_sources`。YouTube 包若声明该 namespace 或直接从面板调用它会形成跨模块
  所有权冲突；本模块只消费 Core `CollectRequest.source_config_snapshot` 中的
  `youtube_channel_ids` 只读快照。

### Release 元数据与数据策略

- 官方输入冻结为 tag `module-youtube-v1.0.0`、asset
  `youtube-1.0.0.zip`。确定性包 SHA-256 为
  `929222b5084b17b122d5f01ec8f51f3938a94666bf6487abc35c59f9e7ea0eee`，
  manifest SHA-256 为
  `ba92e29d349a28b3de38d91333c69dca918c1c6987c9473c6ccf4f4b7a3f4737`，
  大小 19837 字节；release fragment 与完整 Catalog v1 条目位于本任务专属
  `release/`。
- 构建输入不包含真实 Channel ID 列表、来源配置、缓存、Cookie、Token、API Key、
  `.env`、vendor、脚本、测试或安装钩子。自动验证也只使用虚构 Channel ID、
  MockTransport、临时 registry/runtime/data。
- 卸载只移除程序包。临时生命周期测试证明 `data/modules/youtube` 下的隔离缓存
  和独立的临时 `intel_sources.json` 字节均保持不变；重装启用后重新关联同一
  数据，未执行 purge。

### 专属验证

- `python -m py_compile`：通过
  `features/youtube/{__init__,collector,module,package_builder}.py` 与两项
  YouTube 测试。
- `tests/test_youtube_collector.py`：通过。继续覆盖严格 Channel ID、名称/handle/
  URL 拒绝且零请求、Atom 时间解析、稳定 ID、去重、lookback、空/partial/failed、
  节流、Feed 身份和 legacy facade；所有 HTTP 均为 MockTransport。
- `tests/test_youtube_feature_package.py`：通过。覆盖确定性目录/ZIP 与 release
  摘要、包内容 allowlist、Provider 零网络注册、重复加载无重复注册或路由、临时
  ModuleManager 安装/依赖/启用/停用/卸载/重装、配置与缓存保留、缺失配置零请求，
  以及两个虚构频道中一个失败时另一个结果继续返回。
- 扩展回归 `tests/test_intel_sources_registry.py`：通过。随后
  `tests/test_intel_sources_integration.py` 在导入 PK-134 专属
  `features/rss_intel.provider` 时因 Python 3.8 运行时求值
  `RSSIntelSourceConfig | Mapping[...]` 报 `TypeError`，尚未进入 YouTube 断言；
  PK-131 未越权修改该路径，需由 PK-134/串行窗口修复后复跑整批来源集成。

### 共享串行窗口接入清单

- 主 API 的 Core 启动装配需要让 PK-110 production composition 消费同一个
  `app.state.collector_registry`，优先使用已启用安装包注册的来源，不再静态导入
  YouTube 可选实现；停用/卸载后重启时 registry 中自然不存在该来源。
- PK-010/PK-100 串行合并官方 Catalog、模块展示、依赖与重启提示；README、
  catalog、共享 dashboard、架构文档与 `TASKS.md` 均保持冻结，本任务未修改。
- 本模块没有 Collector `1.0` 字段、source ID、时间、稳定 ID 或序列化契约问题。
  新增的 Core `CollectorRegistry` 已足够完成专属包；剩余事项是共享 composition
  接线，不要求改变冻结契约。

当前状态：待集成（共享集成待排队）。本任务未暂存、提交、推送、发布或清理任何
工作区内容。
