# PK-134 — RSS 与信息差来源

- 状态：待集成
- 优先级：P2
- 所属模块：`rss_intel`
- 依赖任务：PK-001、PK-010、PK-100、PK-110、PK-115
- 负责路径：`server/intel/collectors/money_tips.py`、`server/features/rss_intel/**`、新建 `server/tests/test_rss_intel_*.py`、本任务文件
- 当前对话：2026-07-30 由 PK-000 重新打开 PK-011 情报批可安装化增量；Core
  Collector 1.0 公共契约落地后，完成专属包、Provider、动态面板、发布元数据与
  隔离测试，不修改 `TASKS.md` 或共享冻结文件
- 并行阶段交接状态：共享集成待排队（2026-07-22）；专属实现与隔离验证已完成，等待 PK-000 分配串行窗口，不自行修改 `TASKS.md`

## 并行批次授权（2026-07-22）

- 共同依赖为 `docs/architecture/daily-briefing.md` 已冻结的 Collector `1.0`；需要改变契约时立即停止并交回 PK-000。
- 并行阶段只修改上述负责路径。`server/intel/intel_config.py`、API、legacy briefing、旧控制台、catalog、README、架构文档和来源注册表均留到总控串行窗口或 PK-115。
- 现有联网 debug 脚本、真实 Feed、真实 URL 和内部地址不用于自动测试；PK-140 不属于本批。

## 阶段约束

- PK-110 已通过最终复核，Collector `1.0` 已冻结，本任务已由 PK-000 统一领取。
- 通用 RSS 规则与“信息差 X 用户”必须分开；后者始终归 PK-120。

## 目标

独立管理通用 RSS/Atom 抓取、关键词过滤、规范化、稳定 ID、限流和失败状态，并向 PK-110 提供 `money` 或后续总控确认的公共 source ID。

## 数据所有权

- 当前 RSS URL 与高级关键词仍在 `intel_config.py`；如果以后开放用户输入 URL，必须由 PK-000 另行定义本机请求、SSRF 和重定向安全边界。
- 本任务不拥有 X 用户配置，也不直接写 PK-110 当天缓存。

## 验收标准

- RSS/Atom、空 Feed、损坏 XML、重复条目、关键词、发布时间、超时和重定向使用假 HTTP 测试。
- 自动测试不得请求真实 Feed；不得把完整 Feed 内容、内部地址或错误响应写入公开日志。
- 不修改 X/Nitter Collector、PK-110 汇总或 PK-115 注册表。

## 并行阶段工作记录（2026-07-22）

### 实际导出

- `features.rss_intel.RSSIntelCollector`：公共 `source_id="money"`，实现冻结的 `Collector.collect(CollectRequest) -> CollectorResult`；只导入 PK-110 的 `collector_contracts`、`models` 与无副作用时区帮助，不导入 gateway、service、repository 或 router。
- `features.rss_intel.RSSFeedEntry`、`parse_feed()`、`parse_published()`：解析有界 RSS 2.x/RDF 与 Atom 1.0，规范标题、摘要、作者、链接和带时区发布时间；缺失/无效时间保持空，不伪造时间。
- `features.rss_intel.FeedURLPolicy`、`normalize_feed_url()`、`normalize_entry_url()`：Feed 抓取只接受应用组装时传入的 HTTPS 公网 DNS 主机；拒绝 userinfo、IP literal、localhost/本地域、非 443 端口，逐跳校验有限重定向，条目展示 URL 不作为抓取目标。
- `intel.collectors.money_tips.MoneyTip` 与 `fetch_money_tips()`：保留 legacy 调用与返回类型，内部委托 `RSSIntelCollector`；新增可选 fake client/clock 仅用于隔离测试，不增加 HTTP/API 用户 URL 输入面。

### 行为、失败状态与副作用

- 关键词在标题和摘要上大小写无关匹配；ASCII 词/短语使用词边界，中文使用子串匹配。重复关键词被折叠，最多 100 个关键词。
- 单 Feed 最多解析 30 条（构造参数上限 100），默认最多返回 15 条；最多 32 个应用所有 Feed，单响应默认最多 1 MiB（硬上限 4 MiB），顺序请求且不自动重试。
- 发布时间支持 RFC 822/2822 与带时区 ISO 8601；naive 时间按请求 IANA timezone 明确本地化。超出 `lookback` 或晚于当前时刻 5 分钟的条目排除，缺时间条目保留并标记 `published_status`。
- stable ID 使用冻结的 `stable_item_id()`；存在 GUID/Atom ID 时组合 Feed host 作为上游身份，无上游 ID 时依次回退规范 URL及标题/作者/时间。结果按 stable ID/规范 URL 去重，按关键词分数、发布时间和 stable ID 确定性排序。
- 全成功有条目为 `complete`，全成功无匹配为 `empty`，有条目但部分 Feed 失败为 `partial`，无可用条目且存在 Feed 失败为 `failed`，无应用所有 Feed 或请求不含 `money` 为 `not_configured`。失败 warning 不包含 URL、异常正文或响应体；429/503 等有限读取 `Retry-After`，其余失败默认 30 分钟后可重试。
- 网络只发生在显式 `collect()`/legacy `fetch_money_tips()`；自建 client 固定 `trust_env=false`、`follow_redirects=false`，响应流式限长。Collector 完全忽略 `source_config_snapshot` 中的 `rss_feeds` 等 URL，因此本地来源注册表或调用请求不能临时增加抓取目标。模块不读写缓存、关注名单、Cookie、Token、API Key 或 `.env`，不打印 Feed URL、异常正文或响应体。

### 专属修改路径

- `server/intel/collectors/money_tips.py`
- `server/features/rss_intel/__init__.py`
- `server/features/rss_intel/models.py`
- `server/features/rss_intel/parser.py`
- `server/features/rss_intel/http_client.py`
- `server/features/rss_intel/collector.py`
- `server/tests/test_rss_intel_collector.py`
- `tasks/PK-134-rss.md`

### 验证记录

- `server/.venv-asr/Scripts/python.exe tests/test_rss_intel_collector.py`：通过；全部 HTTP 使用 `httpx.MockTransport`，覆盖 RSS、Atom、空 Feed、损坏 XML、重复条目、关键词、发布时间/窗口、超时、429、允许/拒绝重定向、任意 URL 注入拒绝、legacy 映射与禁止依赖边。
- `server/.venv-asr/Scripts/python.exe tests/test_daily_briefing_module.py`：通过；PK-110 Collector/汇总/缓存主回归无回退。
- `server/.venv-asr/Scripts/python.exe tests/test_daily_briefing_summary_cache.py`：通过；当天播报缓存回归无回退。
- `server/.venv-asr/Scripts/python.exe -m py_compile features/rss_intel/__init__.py features/rss_intel/models.py features/rss_intel/parser.py features/rss_intel/http_client.py features/rss_intel/collector.py intel/collectors/money_tips.py tests/test_rss_intel_collector.py`：通过。
- `server/.venv-asr/Scripts/python.exe ../scripts/check_task_docs.py`：通过，11 个既有门禁任务均通过；PK-134 仍保持“进行中/共享集成待排队”，未越权改为“待集成”。
- `git diff --check`：退出 0，无空白错误；仅报告工作树既有 LF/CRLF 提示。PK-134 新建未跟踪文件另做行尾空白扫描，无匹配。
- 按批次禁令未运行真实 Feed、真实 URL、真实缓存或联网 debug 脚本。

### 共享集成待排队内容

- `server/intel/intel_config.py`：无需改变现有高级 RSS URL/关键词字段，也不新增用户可编辑 URL；串行组装可把既有受信 `MONEY_CONFIG["rss_feeds"]` / `MONEY_CONFIG["keywords"]` 注入 `RSSIntelCollector`。
- `server/intel/briefing.py`：现有 `fetch_money_tips` 导入签名保持兼容，legacy 路径无需为 PK-134 改字段；串行窗口只需确认 `money_tips -> money` 映射继续成立。
- `server/api.py` / PK-110 组合根：与本批其他来源一起，把 `"money": RSSIntelCollector(...)` 注册进统一 `ContractCollectorGateway` 并传给 `DailyBriefingService`；不得让 router/API 接收任意 Feed URL。
- `server/features/catalog/service.py`：登记 `rss_intel` / PK-134 为 main-api 内的 Collector source adapter，无独立用户 URL 管理端点；网络只在显式生成/刷新/到期补采时发生。
- `docs/architecture/daily-briefing.md`：只追加 Collector 1.0 的非破坏性 RSS/Atom 实现说明、`money` 映射与封闭 Feed/重定向边界，不修改冻结字段语义或版本。
- `docs/architecture/modular-monolith.md` 与 `README.md`：在串行窗口记录 `rss_intel` 模块边界、受信固定 Feed、失败覆盖、假 HTTP 测试命令和 API 重启要求；`AGENTS.md`、`README.local.md` 无需变更。
- `TASKS.md`：仅由 PK-000 在共享文档门禁与串行集成完成后更新状态；本对话保持不修改。

### 公共契约问题

- 无。现有冻结的 `source_id="money"`、`CollectRequest`、`IntelItem`、`SourceCoverage` 与 `CollectorResult` 足以表达本实现；未请求新增字段、改变状态语义或提升 major。

## 独立对话启动提示

```text
仅在 PK-110 Collector 契约冻结后领取 PK-134。只处理通用 RSS/Atom、关键词
和规范化 Collector；信息差 X 用户仍归 PK-120。所有测试使用假 Feed，不访问
真实 URL，不修改 PK-110 汇总、来源注册表或其他平台采集器。
```

## PK-119 事后复核与共享收口（2026-07-22）

- 复核确认 `RSSIntelCollector` 只使用应用装配的受信 HTTPS Feed/关键词，拒绝用户 URL、内网/本地主机、危险重定向和超限响应；没有独立 router、缓存或来源配置所有权。
- 已通过统一 `ProjectCollectorGateway` 注册到公共 `money` source，legacy `fetch_money_tips()` 继续委托同一实现。普通当天缓存读取仍不调用 RSS；仅 PK-110 显式生成、刷新或缺失补采触发网络。
- catalog、README 与架构文档已登记 RSS/Atom adapter 和 SSRF/重定向边界。`test_rss_intel_collector.py`、PK-119 集成及 PK-110 两项核心回归通过，全部使用 MockTransport 与固定配置。
- 没有读取真实 Feed、来源名单、凭证或缓存，也未发起真实网络请求。遗留仅为 PK-900 独立验收、部署后重启与受信上游运行可用性。

## 完成文档门禁

- [x] TASK_RECORD — 已按实际代码补记接口、网络/安全副作用、生产装配、验证与遗留。
- [x] TASKS_BOARD — PK-134 已由 PK-000 统一登记为“待集成”。
- [x] PUBLIC_README — 已登记 RSS/Atom、受信 Feed 与失败边界。
- [x] MODULE_CATALOG — 已登记 `rss_intel` Collector adapter。
- [x] ARCHITECTURE_DOCS — 已登记 `money` 生产装配与 SSRF/重定向边界。
- [x] LOCAL_README — 不适用；未改变本机路径、端口或解释器约定。
- [x] AGENT_RULES — 不适用；未改变长期 agent 规则。
- [x] VALIDATION — 专属、PK-119 集成及 PK-110 共享回归通过；最终差异检查由 PK-119 记录。

## PK-000 最终复核（2026-07-22）

PK-900 报告及实际固定受信 Feed、私网/危险重定向拒绝、Retry-After 和零真实网络回归经独立复核通过；PK-134 置为“已完成”。

## PK-011 可安装化增量（2026-07-30）

### 实际导出与动态接缝

- `features.rss_intel.RSSIntelCollector` 现直接依赖
  `core.intel_contracts` 的 Collector 1.0 models/protocols/time helpers，不再
  导入 `features.daily_briefing` 的 gateway、service、repository、router 或兼容
  转发层；`source_id="money"`、稳定 ID、发布时间、关键词和结果覆盖语义不变。
- `RSSIntelSourceConfig` 与 `RSSIntelCollectorProvider.create_collector()` 是
  应用组装专用的受信配置接缝。包内默认没有 Feed/关键词；缺失 Provider 时仍向
  Core `CollectorRegistry` 注册一个空配置 `money` Collector，显式 collect 返回
  `not_configured`，不会 DNS、HTTP 或读取本地文件。
- `backend.register` / `backend.unregister` 使用
  `app.state.intel_collector_registry` 与
  `app.state.rss_intel_collector_provider`。重复装配同一 app 幂等；已有不同
  `money` Collector 时拒绝覆盖，其他 source 保持不变。模块不注册 HTTP 路由，
  因而不会形成开发源码/运行包重复路由。
- `build_rss_intel_package()` 与 `file_sha256()` 只复制明确 allowlist：
  `__init__.py`、Collector、HTTP、模型、parser、Provider、module 和动态面板。
  ZIP 固定时间、权限、存储方式、排序与 LF，重复构建字节和 SHA-256 一致。
- 动态 `dashboard/index.js` 只展示 `money`、受信 HTTPS Feed 和显式采集边界；
  不调用 `context.request`/`fetch`，不提供 Feed URL 输入、清数据或生命周期旁路。

### 安全、数据与失败隔离

- `FeedURLPolicy` 新增可注入 DNS resolver；正式 collect 在每次请求和每一跳重定向
  前解析目标，任一结果不是全局公网地址即以有限 `dns_rejected` 失败。IP literal、
  localhost/本地域、非默认 HTTPS 端口、未批准重定向 host 和危险 Location 仍拒绝。
- 测试 DNS 全为 fake；HTTP 全为 `httpx.MockTransport`。私网直连在零 HTTP 请求时
  失败，允许 host 重定向到链路本地/回环解析时只完成前一跳，失败 warning 不含
  URL、响应体或异常正文。
- 包、manifest 和 release 元数据不含真实 RSS 规则、关键词、来源名单、缓存、
  凭据、`.env`、模型、vendor、脚本、测试夹具或本机绝对路径。安装、启停、面板
  mount 和缺配置 collect 均零网络。
- `rss_intel` 本身不拥有配置或缓存。ModuleManager 卸载只删除可再生成程序版本并
  返回 `data_preserved=true`；外部受信来源配置/缓存保持原所有权，重装后由
  Provider 重新关联。
- manifest 强依赖 `intel_sources`，不声明 API namespace/legacy endpoint，
  权限为空，`requires_restart=true`；启停和卸载后的进程内 Collector 变化在重启
  装配后生效。

### 专属修改路径

- `server/intel/collectors/money_tips.py`
- `server/features/rss_intel/__init__.py`
- `server/features/rss_intel/collector.py`
- `server/features/rss_intel/http_client.py`
- `server/features/rss_intel/module.py`
- `server/features/rss_intel/package_builder.py`
- `server/features/rss_intel/provider.py`
- `server/features/rss_intel/package_source/**`
- `server/features/rss_intel/release/**`
- `server/tests/test_rss_intel_collector.py`
- `server/tests/test_rss_intel_module.py`
- `tasks/PK-134-rss.md`

### 验证结果

- `scripts/python.ps1 -m py_compile ...`：通过全部 PK-134 Python 文件；本机需以
  `-ExecutionPolicy Bypass` 调用项目包装器。
- `scripts/python.ps1 tests/test_rss_intel_collector.py`：通过。覆盖 RSS/Atom、
  关键词、发布时间、稳定 ID、损坏/空 Feed、超时、限流、重定向、fake DNS 私网
  和 snapshot URL 注入拒绝。
- `server/.venv-asr/Scripts/python.exe tests/test_rss_intel_module.py`：通过。
  项目包装器当前选择的解释器缺 FastAPI，因此生命周期专项按项目既有服务端虚拟
  环境复跑；覆盖确定性 ZIP/摘要、release 元数据、零网络缺配置、安装/启用/停用/
  卸载保留数据/重装、稳定条目 ID、单 source 失败隔离、重复 Collector/零重复路由。
- `node --check server/features/rss_intel/package_source/dashboard/index.js`：
  通过。
- 全程未读取真实 Feed/关键词、来源名单、缓存、Cookie、Token、API Key、`.env`、
  vendor、模型或个人状态，未执行真实采集、真实 DNS/HTTP、Git 暂存/提交/推送或
  发布。

### 共享串行窗口需要写入

- PK-000/PK-010：用
  `server/features/rss_intel/release/official-release-fragment.json` 和临时构建
  ZIP 生成正式 Catalog 条目；本任务不修改共享 Catalog 或执行 Release。
- PK-000/PK-110：应用启动时复用同一 Core `CollectorRegistry`，将它放入
  `app.state.intel_collector_registry`；从既有应用所有、受信且不可由浏览器修改的
  RSS 配置构造 `RSSIntelCollectorProvider`。不得把
  `CollectRequest.source_config_snapshot`、PK-115 CRUD 或任意用户 URL 变成 Feed。
- PK-000/PK-100：Catalog/控制台登记 `rss_intel` 的依赖、空权限、重启语义、
  动态入口和卸载保留数据；面板不增加业务 API。
- PK-000 文档窗口：README 与模块/每日情报架构说明补记安装顺序、`money` Provider、
  显式采集网络、逐跳 DNS/重定向 SSRF 边界、缺来源降级和卸载保留配置/缓存。
- `TASKS.md` 状态只由 PK-000 串行回写，本任务未修改。

### 公共契约结论

Core 已冻结并导出 Collector 1.0 models/protocols、时间帮助与
`CollectorRegistry`，现有契约足以完成本增量；没有请求新增 manifest 字段、
Collector 字段、source ID、状态或 major 版本。共享装配只需消费上述公开对象和
Provider 接缝，不需要修改冻结契约。

### Python 3.8 导入修复与 PK-200 共享回归

- PK-200 报告的阻断已在项目 Python `3.8.20` 下复现：Provider 返回类型别名若用
  `RSSIntelSourceConfig | Mapping[...]`，即使文件启用 postponed annotations，
  类型别名赋值仍会在 import 时求值并抛出 `TypeError`。
- `provider.py` 已做最小兼容修复：显式导入 `typing.Union`，将运行时类型别名改为
  `Callable[[], Union[RSSIntelSourceConfig, Mapping[str, object]]]`；未改变配置、
  Collector、网络或模块生命周期行为。
- Python 3.8 直接 import、PK-134 Collector/安装包专项，以及 PK-200
  `test_conversation_package.py`、`test_conversation_module.py`、
  `test_conversation_consumers.py` 全部通过。后两项仍输出混合工作区既有的
  focus runtime `PermissionError` 降级提示，但退出码为 0，且不再出现 RSS
  Provider 导入阻断。

### app.state 配置接缝收口

- 共享装配审计指出 Core 若为复用既有 `MONEY_CONFIG` 而直接 import
  `features.rss_intel.provider`，会破坏安装包独立性。PK-134 因此新增纯字符串
  app.state 接缝：
  `rss_intel_source_config_provider: Callable[[], Mapping[str, object]]`。
- 映射只接受 `rss_feeds`、`keywords` 和可选 `allowed_redirect_hosts`；RSS 动态
  `backend.register` 在包内将其转换为 `RSSIntelCollectorProvider`。Core 只需设置
  callable，不导入 RSS 模型、Provider、Collector 或其他内部实现。
- 注册优先级固定为：完整 `rss_intel_collector_provider`（测试或受控高级装配）→
  `rss_intel_source_config_provider` 只读映射 → 安全空配置。无任一接缝时仍注册
  `money` 的 `not_configured` Collector。
- source-config callable 在注册时只读取一次映射；构造 Collector 不解析 DNS、
  不发 HTTP、不读缓存。卸载/`unregister` 只移除 Collector 和模块自行创建的完整
  Provider，保留外部 source-config callable，符合卸载保留配置语义。
- 非 callable 接缝抛有限 `TypeError`；返回非 Mapping 或未知字段抛有限
  `ValueError`。失败不注册/覆盖 `money`，也不残留模块自行创建的 Provider。
- 临时映射、空配置、错误类型、未知字段、零 DNS/HTTP 注册、幂等注册、卸载清理
  与配置保留已加入 `test_rss_intel_module.py`。PK-134 两项专项以及 PK-200
  module/consumer 回归通过。PK-200 package 回归曾在本轮第一次复跑通过，但并行
  工作区随后变化，最终复跑发现其受跟踪 Catalog entry 的 manifest 摘要
  `8f5dd55b672fd9f67bfab88b29d02c8bebe1b934bce1dd182a70f70840c11411`
  与当前临时重建值
  `fd560a74496c46c9b745cbd25d85b3edf0983a7632630fc5912ff60074ec06ce`
  不一致。该失败不涉及 RSS import/Provider，已交 PK-000/PK-200 串行处理；
  PK-134 未修改 PK-200 路径。

确定性临时重建结果（两份 ZIP 字节完全相同）：

- Asset：`rss_intel-1.0.0.zip`
- Size：`36153`
- Package SHA-256：
  `9af0bb51fe50b2a709386ed656aed95eb7fbe6cc8dadcb3f3dc36b55d46c6307`
- Manifest SHA-256：
  `0928d9decb6c4797994a776f96663a0a079c0a2a80b50108f2fa9598ced4a466`
- Release fragment SHA-256：
  `e5969b55bf6017e95e907f4a049d77a6ccd992a5c84e706a563ce4bd678ef8df`
- Release fragment 仍为 `module-rss-intel-v1.0.0` /
  `rss_intel-1.0.0.zip`，依赖 `intel_sources`，空权限，
  `preserve_on_uninstall`，`requires_restart=true`。

本任务停在“待集成”，等待 PK-000 安排共享串行窗口；不发布。
