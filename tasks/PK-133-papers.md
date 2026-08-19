# PK-133 — 论文来源、作者追踪与今日论文展示

- 状态：待集成
- 优先级：P0
- 所属模块：`papers`
- 依赖任务：PK-001、PK-010、PK-100、PK-110、PK-115
- 负责路径：`server/intel/collectors/arxiv.py`、`server/intel/collectors/papers.py`、`server/features/papers/**`、论文展示所需的 `server/static/dashboard.html` 最小区块、必要且只读的 briefing 状态投影接缝、新建 `server/tests/test_papers_*.py`、本任务文件
- 当前对话：2026-07-30 由 PK-000 授权 PK-011 可安装化增量
- 当前增量交接状态：待集成；交由新的 PK-900 累计验收

## 并行批次授权（2026-07-22）

- 共同依赖为 `docs/architecture/daily-briefing.md` 已冻结的 Collector `1.0`；需要改变契约时立即停止并交回 PK-000。
- 并行阶段只修改上述负责路径。`server/intel/intel_config.py`、API、legacy briefing、旧控制台、catalog、README、架构文档和作者注册表均留到总控串行窗口或 PK-115。
- 真实作者名单、论文缓存、API Key 与网络不用于自动测试；PK-140 不属于本批。

## 阶段约束

- PK-110 已通过最终复核，Collector `1.0` 已冻结，本任务已由 PK-000 统一领取。
- 作者名单归 PK-115；arXiv 主题/关键词等高级规则暂留 `intel_config.py`，除非 PK-000 另行调整。

## 目标

把 arXiv、Crossref、Semantic Scholar 组织为边界清晰的论文来源适配器，统一作者匹配、时间窗口、摘要补全、fallback 和 DOI/URL/标题去重，同时保留各自 source ID、coverage 与 warning。

## 数据所有权

- 三组论文作者配置归 PK-115；API Key 只来自环境。
- arXiv 本机缓存保持来源模块所有、Git 忽略；自动测试不得读取或覆盖真实缓存。

## 验收标准

- 三来源失败相互隔离，fallback 不重复请求已覆盖作者，也不把失败伪装成无论文。
- 作者规范化、跨来源去重、摘要补全、时间窗口、限流和缓存全部使用假 HTTP/临时目录测试。
- Semantic Scholar Key、完整错误体和个人作者名单不得进入日志或汇总缓存。

## 工作记录（2026-07-22）

### 实际导出

- `intel.collectors.arxiv.ArxivCollector`：`source_id="arxiv"`，实现冻结的 `Collector.collect(CollectRequest) -> CollectorResult`；构造时接收非秘密 `ArxivQuery` 列表、可注入 HTTP transport/时钟/限流 sleep 和可注入缓存目录。主题/关键词仍由未来串行窗口从 `intel_config.py` 组装，不在本任务复制或改写。
- `intel.collectors.papers.CrossrefCollector`：`source_id="crossref"`，按冻结快照中的三组作者键逐作者查询，严格核验返回作者、时间窗口和可选期刊白名单，返回独立 coverage/warning/retry_after。
- `intel.collectors.papers.SemanticScholarCollector`：`source_id="semantic"`，按作者查询并严格核验；Key 只通过可注入 `api_key_provider` 取得，默认运行时才读取 `SEMANTIC_SCHOLAR_API_KEY`，不进入 `CollectRequest`、结果、warning 或日志。
- `features.papers.PaperCollectorCoordinator`：保留三份独立 `CollectorResult`，Semantic fallback 只收到 arXiv/Crossref 尚未覆盖的作者；`collect_batch()` 额外返回跨来源去重后的只读 `deduplicated_items`，`collect()` 返回独立结果序列。
- `features.papers.AbstractResolver` / `AbstractResolution` 与 `SemanticScholarCollector.resolve()`：对缺摘要论文先按 DOI、再按规范标题精确补全；这是论文级查询，不重复已覆盖作者的 author search，成功后以 `metadata.abstract_source="semantic"` 记录来源。
- `features.papers` 纯函数接口：`normalize_author_name`、`author_name_matches`、`authors_from_snapshot`、`covered_authors`、`normalize_doi`、`deduplicate_paper_items`。跨来源去重按 DOI、arXiv ID、规范 URL、规范标题做传递合并，合并项保留 `metadata.discovery_sources` 与 `alternate_stable_ids`，并择优补齐较完整摘要。
- 保留既有 `fetch_arxiv_papers`、`search_by_author_semantic_scholar`、`fetch_recent_crossref_for_authors` 等 legacy Python 入口；本任务仅把其自动日志中的作者目标与异常正文改为有限状态/异常类型，没有修改共享聚合接线。

### 专属修改路径与副作用

- 修改：`server/intel/collectors/arxiv.py`、`server/intel/collectors/papers.py`。
- 新增：`server/features/papers/__init__.py`、`domain.py`、`service.py`、`server/tests/test_papers_collectors.py`。
- 任务记录：`tasks/PK-133-papers.md`。
- 运行时网络只发生在显式调用 Collector 时；普通导入不联网。arXiv Collector 的默认缓存仍位于来源模块既有忽略目录，测试全部注入系统临时目录。Crossref/Semantic 不新增本机持久化。没有读取、打印、迁移或覆盖真实作者名单、真实 arXiv 缓存、`.env` 或真实 Semantic Scholar Key。

### 隔离验证

- `server/.venv-asr/Scripts/python.exe -m py_compile intel/collectors/arxiv.py intel/collectors/papers.py features/papers/__init__.py features/papers/domain.py features/papers/service.py tests/test_papers_collectors.py`：通过。
- `server/.venv-asr/Scripts/python.exe tests/test_papers_collectors.py`：通过。只使用 `httpx.MockTransport`、固定 aware 时钟、虚构作者/Key/错误正文和系统临时目录；覆盖作者规范化/缩写/倒序/误匹配拒绝、arXiv 时间窗/缓存/刷新/429、Crossref 部分失败、Semantic 未覆盖作者 fallback、已覆盖作者不重复 author search 但允许单次 DOI 摘要补全、摘要择优、跨来源传递去重、稳定 shared ID、独立 source_id/coverage/warning 及凭证/错误正文不泄漏。
- `server/.venv-asr/Scripts/python.exe tests/test_daily_briefing_module.py`：通过（PK-110 全 fake 核心回归）。
- `server/.venv-asr/Scripts/python.exe tests/test_daily_briefing_summary_cache.py`：通过（PK-110 临时目录摘要缓存回归）。
- 专属 tracked 路径 `git diff --check`：通过；新建专属文件尾随空白扫描无匹配。仅出现工作区既有 LF→CRLF 提示。

### 共享集成待排队

- `server/intel/intel_config.py`：由串行所有者把既有 `ARXIV_CONFIG` 转为 `ArxivQuery`，并把既有非秘密限流/数量/期刊开关作为 Collector 构造参数；不得把作者名单或 Key 写入构造配置、日志或缓存。
- `server/intel/briefing.py`：由串行所有者用 `PaperCollectorCoordinator` 接线三来源，并把同一 `SemanticScholarCollector` 作为可选 `abstract_resolver`；删除旧聚合中的重复作者 fallback/摘要补全/跨来源去重职责。三份 `CollectorResult` 必须原样保留 source ID、coverage、warning，汇总展示再消费 `deduplicated_items` 或继续交给 PK-110 的同语义去重。
- `server/api.py` / `server/features/catalog/service.py`：若总控决定把 papers 注册为内置模块或公开独立 API，再在各自串行窗口装配；当前专属实现未新增 HTTP 路由，Collector 接入本身不要求新增 endpoint。
- `README.md`：串行窗口记录三来源已经从 legacy 混合采集切换为独立 Collector、Semantic fallback 只查未覆盖作者、arXiv 缓存/显式刷新和失败可见性，以及部署后需重启 API。
- `docs/architecture/daily-briefing.md`：仅补充非破坏性实现说明（实际类名、协调/fallback、缓存位置）；不得改动 Collector 1.0 字段或语义。`docs/architecture/modular-monolith.md` 仅在 catalog/模块边界实际接线后更新 papers 模块映射。
- `TASKS.md` 与八项完成文档门禁：保持由 PK-000 在共享串行窗口统一处理，本任务未修改。

### 公共契约检查

- 未发现需要修改 Collector `1.0` 的问题。三个 Collector 均只导入 `features.daily_briefing.collector_contracts` 与 `models` 公共边界（另使用标准/论文专属纯函数），没有导入 PK-110 gateway、service、repository 或 router。
- 当前待办仅为共享装配与公开文档同步，不是公共契约阻塞；并行阶段停在“共享集成待排队”。

## 独立对话启动提示

```text
仅在 PK-110 Collector 契约冻结后领取 PK-133。只处理 arXiv、Crossref、
Semantic Scholar、作者匹配、fallback、摘要和论文去重；不得读取真实作者名单、
API Key 或缓存，全部使用假 HTTP 与临时目录，不修改 PK-110 汇总。
```

## PK-119 事后复核与共享收口（2026-07-22）

- 复核确认 arXiv、Crossref、Semantic Scholar 保持三个独立 source/result，由 `PaperCollectorCoordinator` 处理未覆盖作者 fallback、摘要补全和跨来源去重；PK-110 不直接访问论文私有状态。
- 统一 `ProjectCollectorGateway` 已从既有非秘密 `intel_config.py` 组装查询/开关，并通过 coordinator 分派 `arxiv/crossref/semantic`；Semantic 只在现有开关/Key 条件允许时启用。legacy 论文函数保留 Python 兼容，但不再是主 API 的生产 composition root。
- 实际代码已有 Python 3.8 的 `zoneinfo`/`pytz` 兼容回退，旧阻断不再成立。`test_papers_collectors.py`、PK-119 集成、PK-110 两项核心回归通过，全部使用假 HTTP、固定时钟和临时缓存。
- catalog、README 与架构文档已同步。真实作者名单、arXiv 缓存和 Semantic Key 未读取或纳入差异；遗留仅为 PK-900 独立验收及部署后重启。

## 完成文档门禁

- [x] TASK_RECORD — 已按实际代码补记三源接口，并在 2026-07-28 增量记录只读展示接口、共享 hunk、验证与遗留。
- [x] TASKS_BOARD — `TASKS.md` 由 PK-000 保持 P0“进行中”；本轮按明确禁令未再次修改，任务文件在交接时记录“待集成”。
- [x] PUBLIC_README — 已登记三源边界及控制台当天缓存论文展示的只读、安全与 fallback 语义。
- [x] MODULE_CATALOG — 不适用；本增量没有新增模块、路由或 catalog 能力。
- [x] ARCHITECTURE_DOCS — 不适用；直接复用已记录的 `GET /api/v1/briefing/today` 与 Collector 1.0，不改变架构边界。
- [x] LOCAL_README — 不适用；未改变本机路径、端口或解释器约定。
- [x] AGENT_RULES — 不适用；未改变长期 agent 规则。
- [x] VALIDATION — 原三来源回归与本轮固定时钟、fake、ASGITransport、临时目录只读展示回归通过；最终累计验收交由新的 PK-900。

## PK-000 最终复核（2026-07-22）

PK-900 报告及实际三论文来源顺序、独立 coverage、fallback、去重与关闭隔离经独立复核通过；PK-133 置为“已完成”。

## 控制台今日论文展示增量（2026-07-28）

### 总控授权与定位

- 保留上述 2026-07-22 已完成事实；本节是同一 PK-133 的新增增量，不新建任务编号。
- 本增量只补齐“今日有受关注作者发布论文时，控制台能看见论文标题和摘要”的用户界面闭环。PK-213 的 Voice Pack 发布/安装工作与本增量并行，但二者不得互相修改任务契约、依赖或实现。
- PK-100 作为公共控制台外壳依赖补入；PK-110 的 Collector `1.0`、缓存、汇总、去重与零网络读取语义继续冻结，不得为展示需求增加或改变公共 Collector 字段。

### 接口与数据契约

- 数据继续来自当天 briefing 缓存中的标准 `IntelItem`：论文以 `category="papers"` 识别，展示 `title` 与 `summary`。现有 `/api/v1/briefing/today` 已公开 `items`，不得从控制台直接调用 arXiv、Crossref、Semantic Scholar Collector。
- 控制台普通加载只读取已有当天缓存；不得触发联网、缺失来源补采、Kei 改写、摘要补全或缓存写入。显式“生成/重新生成今日情报”继续沿用 PK-110 既有行为。
- 如 `/dashboard/status` 需要增加论文展示数据，只允许投影当天缓存中已公开的安全字段，且限于 `stable_id`、`title`、`summary`、`author`、`published_at`、`url`、`source_id`；不得返回缓存路径、原始上游响应、作者配置、Key、Cookie、Token 或隐藏 metadata。
- “今天发布”以 briefing 文档的本地日期和项目时区为准；仅展示该当天缓存内的论文项。跨来源同一论文只展示一次，并沿用既有去重后较完整的摘要。
- 标题必须显示；摘要有值时显示已有 `summary`，没有摘要时明确显示“摘要暂缺”，不得现场联网、调用 LLM 或编造内容。
- 所有外部文本必须以安全文本节点或等价转义方式渲染；论文标题、摘要、作者和 URL 不得形成可执行 HTML/脚本。

### 控制台边界

- 在现有“今日情报”区域增加“今日论文”列表；无论文时显示稳定空状态，不影响来源计数、覆盖状态、warning 和 Kei 今日播报总结。
- 不新增论文管理页、作者编辑规则、收藏、下载、全文抓取、引用导出、翻译、LLM 摘要或通知推送。
- 不新增论文缓存或个人状态文件，不改变三来源采集、fallback、摘要补全和去重规则。
- `server/static/dashboard.html` 与必要的 briefing 状态投影属于共享路径：独立任务修改前必须检查实际 diff，只能提交本增量的最小 hunk；若与 PK-213 或其他进行中任务重叠且无法安全拆分，停止并交回 PK-000，不得覆盖混合工作区。

### 累计验收标准

- 固定时钟与临时 briefing repository 下，今天的去重论文会在控制台逐条显示标题和摘要；同一论文不因 arXiv/Crossref/Semantic 多源发现而重复。
- 摘要缺失时显示“摘要暂缺”；昨天、未来日期或非 `papers` 类别条目不进入“今日论文”列表。
- 恶意标题、摘要、作者与 URL 只能作为文本展示，不能注入 DOM、脚本或危险链接。
- 页面加载、状态刷新、展开论文列表和空状态均为零网络采集、零 LLM/voice 调用、零缓存写入；只有既有显式生成/重新生成操作可沿用原采集语义。
- `/api/v1/briefing/today`、legacy briefing、Collector `1.0`、其他情报类别、来源配置及原 PK-133 三来源回归继续通过。
- 自动测试只使用固定 aware clock、fake gateway/transport、ASGITransport 和系统临时目录；不得访问真实作者名单、论文缓存、API Key、外部网络或付费服务。
- 完成后补记实际接口、共享 hunk、测试命令、零网络/零写入证据和遗留事项，将 PK-133 改为“待集成”并交给新的 PK-900 累计验收；不得自行标记“已完成”。

### 增量实施记录与交接（2026-07-28）

#### 实际接口与展示行为

- 复用既有 `GET /api/v1/briefing/today`；响应中的 `items[]` 已包含冻结 `IntelItem` 的 `stable_id/source_id/category/title/summary/url/author/published_at`，本轮没有新增或修改 HTTP、Collector 1.0、gateway、service、repository、router 接口。
- 控制台在普通 `/dashboard/status` 完成后独立只读上述当天端点，只筛选 `category="papers"`。防御性去重依次使用 stable ID、安全规范 URL 与空白/大小写归一标题，重复项择优保留已有摘要更完整的一项。
- “今日论文”逐条显示标题、已有摘要、作者/发布时间/来源和经绝对 HTTP(S)、无 userinfo 校验的来源链接；空摘要固定显示“摘要暂缺”，无当天论文固定显示“今日暂无论文”。
- 标题、摘要、作者及来源信息均通过 `textContent` 写入；URL 仅在白名单校验后赋给 `<a>`，并设置 `noopener noreferrer`。`javascript:` 等危险 URL 不生成链接。

#### 专属与共享修改路径

- 共享最小 hunk：`server/static/dashboard.html` 的“今日情报”区新增“今日论文”容器、纯前端筛选/去重/安全渲染，以及普通状态加载后的只读当天缓存请求。
- 专属测试：新增 `server/tests/test_papers_dashboard.py`。
- 共享文档：`README.md` 新增一条用户可见展示/副作用说明；`TASKS.md` 仅把 PK-133 当前增量改为“待集成”；本任务文件补记实际交接。
- 未修改 `server/api.py`：检查到该文件已有其他专注任务 hunk，而现有版本化只读接口足够完成展示，因此无需叠加共享 API 差异。PK-213 没有修改 `dashboard.html`；本轮也未修改 PK-110、论文 Collector、catalog、架构文档或任何真实缓存/配置。

#### 零网络与零写入证据

- 专属 ASGI 测试使用固定 aware 时钟、`ForbiddenGateway`、`ForbiddenTextGenerator`、`ForbiddenVoice`、`httpx.ASGITransport` 和系统临时目录；当天端点与 dashboard status 读取前后的缓存文件集合及每个文件字节完全一致，三类 fake 调用次数均为 0。
- 仅有昨天和未来日期缓存时，当天端点稳定返回 `ready=false`；非 `papers` 项不进入前端论文列表。测试不读取真实作者注册表、真实 arXiv 缓存、环境 Key、Cookie 或 Token，也不创建外部 HTTP transport。
- Node 假 DOM 夹具验证三来源同题只保留一项并择优已有摘要，缺摘要 fallback 稳定，恶意标题/摘要/作者只形成文本，危险 URL 不形成链接；渲染与展开没有事件型采集、LLM、voice 或写缓存代码。

#### 验证命令

- `server/.venv-asr/Scripts/python.exe tests/test_papers_dashboard.py`：通过。
- `server/.venv-asr/Scripts/python.exe tests/test_papers_collectors.py`：通过。
- `server/.venv-asr/Scripts/python.exe tests/test_daily_briefing_module.py`：通过。
- `server/.venv-asr/Scripts/python.exe tests/test_daily_briefing_summary_cache.py`：通过。
- `server/.venv-asr/Scripts/python.exe tests/test_intel_sources_integration.py`：通过。
- `server/.venv-asr/Scripts/python.exe tests/test_dashboard_shell.py`：通过。
- `server/.venv-asr/Scripts/python.exe -m py_compile tests/test_papers_dashboard.py`：通过。
- `scripts/python.ps1` 在当前 PowerShell 策略下被系统拦截，且回退到不含 FastAPI 的 PATH Python；以上命令因此直接使用仓库既有 `server/.venv-asr` 解释器，未安装或下载依赖。

#### 公共契约与累计验收

- 未发现公共契约问题。展示只消费既有当天缓存字段，没有导入或调用 PK-110 内部 gateway/service/repository/router，也没有更改三来源独立 `source_id`、coverage、warning、fallback、摘要补全或去重规则。
- PK-133 当前状态为“待集成”。新的 PK-900 需累计复核混合工作区中的最小 dashboard/README/TASKS hunk、完整相关回归与部署后 API 静态资源重载；本任务不自行标记“已完成”，不执行暂存、提交、推送或清理。

## 论文 HTTP 唯一所有者增量（2026-07-29）

### 风险复现与最终所有权图

- 静态调用图确认生产 `features/daily_briefing/source_composition.py` 原先从 `intel.collectors.arxiv` / `papers` 反向导入 Collector；`arxiv.py` 同时存在 Collector 实例锁与 legacy 模块锁，`papers.py` 同时存在 Collector 实例锁与 Semantic legacy 模块锁，各自还会创建独立 `httpx.AsyncClient`。
- 在任何代码修改前，用固定 fake arXiv 响应并发触发 `ArxivCollector.collect()` 与 `fetch_arxiv_papers()`，记录到 `old_dual_limiter_max_concurrency=2`。复现只替换 HTTP client、使用临时 cache 与固定时钟，没有访问真实 arXiv。
- 最终依赖为：`source_composition -> features.papers public exports -> Collector/coordinator -> PaperHttpRuntime -> upstream`；`intel.collectors.arxiv|papers -> features.papers` 仅作 deprecated facade。`features.papers/**` 不导入两个 legacy module。
- 唯一协调边界位于 `server/features/papers/http.py`。默认同进程 runtime 为每个 `arxiv/crossref/semantic` 上游各持有一个 client 与一个 `UpstreamLimiter`，统一最大并发、最小间隔、429 `Retry-After`/指数退避状态。隔离测试可以注入同一 `PaperHttpRuntime`、transport、monotonic clock 与 sleep。
- `PaperCollectorCoordinator` 持有生产共享 runtime 的关闭责任；`ProjectCollectorGateway.aclose()` 先纳入 coordinator 再按对象身份去重，Collector 对外部 runtime 不重复关闭。幂等关闭回归断言底层 fake transport `aclose()` 恰好调用一次。

### 实际导出与兼容 facade

- `features.papers` 新公开 `ArxivCollector`、`ArxivQuery`、`CrossrefCollector`、`SemanticScholarCollector`、`PaperHttpRuntime`、`UpstreamLimiter`、`UpstreamPolicy` 与 `default_paper_http_runtime`；Collector `source_id`、`collect(CollectRequest) -> CollectorResult`、coverage/warning、规范化、作者匹配、fallback、摘要补全和跨来源去重均未改变。
- `intel.collectors.arxiv` 只转出 arXiv 常量、`Paper`、Collector/Query 与 legacy `fetch/clear/get`；`intel.collectors.papers` 只转出旧常量、`PaperItem`、三类 Collector/legacy 函数。两 facade 不再包含 `AsyncClient`、锁、limiter、解析或采集规则。
- legacy `fetch_arxiv_papers` 委托 `ArxivCollector` 并转换回既有 `Paper` 形状；Semantic/Crossref/摘要 legacy helper 通过 runtime client adapter 委托统一 HTTP owner。`intel/briefing.py` 尚未物理迁移，继续通过 facade 调用，属于刻意保留的兼容面。

### 修改路径与共享最小 hunk

- 专属实现：`server/features/papers/arxiv.py`、`collectors.py`、`http.py`、`service.py`、`__init__.py`。
- legacy facade：`server/intel/collectors/arxiv.py`、`server/intel/collectors/papers.py`。
- 专属测试：`server/tests/test_papers_http_runtime.py`；`test_papers_collectors.py` 改从 feature 公共出口验证 Collector。
- 共享最小 hunk：`server/features/daily_briefing/source_composition.py` 只改论文导入、共享 runtime 注入与关闭 owner；`README.md`、`docs/architecture/daily-briefing.md` 只补唯一所有者/兼容 facade 说明。
- 本轮没有修改 `TASKS.md`、`server/api.py`、catalog、dashboard、`intel_config.py`、PK-110 模型/契约/聚合器，也没有碰 X、B 站、GitHub、YouTube、RSS。保留了工作区中 PK-020/030/100/120/130/140/150/213 的已有差异。

### 永久回归与并发证据

- `server/.venv-asr/Scripts/python.exe tests/test_papers_http_runtime.py`：通过。legacy 与 Collector 分别同时进入 arXiv、Crossref、Semantic Scholar 时，各自 fake transport 最大并发均为 `1`；arXiv 5 秒最小间隔的观测时刻为 `[0.0, 5.0]`；首个消费者收到 `Retry-After: 7` 时按 arXiv 45 秒退避下限推迟另一消费者，观测时刻为 `[0.0, 45.0]`。
- 同一专属回归还证明：legacy 消费者取消或 fake `ConnectError` 后 semaphore 会释放，随后 Collector 完成；外部 runtime 的 Collector `aclose()` 不抢占 owner，runtime 重复关闭后 transport close count 仍为 `1`；三个 Collector 的注入 runtime 与各自 limiter 身份一致。
- 静态回归证明 `features.papers` 不含对 `intel.collectors.arxiv/papers` 的依赖，两个 legacy 文件不含 `AsyncClient`/`asyncio.Lock`，生产 composition 只从 `features.papers` 导入论文 Collector。facade 导出的三类 Collector 与 feature 类对象身份一致。
- `server/.venv-asr/Scripts/python.exe tests/test_papers_collectors.py`：通过。
- `server/.venv-asr/Scripts/python.exe tests/test_intel_sources_integration.py`：通过。
- `server/.venv-asr/Scripts/python.exe tests/test_papers_dashboard.py`：通过。
- `server/.venv-asr/Scripts/python.exe tests/test_daily_briefing_module.py`：通过。
- `server/.venv-asr/Scripts/python.exe tests/test_daily_briefing_summary_cache.py`：通过。
- `server/.venv-asr/Scripts/python.exe -m py_compile features/papers/http.py features/papers/arxiv.py features/papers/collectors.py features/papers/service.py features/papers/__init__.py features/daily_briefing/source_composition.py intel/collectors/arxiv.py intel/collectors/papers.py tests/test_papers_http_runtime.py tests/test_papers_collectors.py`：通过。

上述自动验收全部使用固定时钟、fake/MockTransport、虚构作者或空 Key 与系统临时目录；没有外部网络、真实作者名单、真实论文缓存或凭据读取，只有临时 arXiv cache 写入。实施中曾误执行文档已标为“运行中 API 手工工具”的 `test_daily_briefing_voice.py`：它以默认 `fetch=false/rewrite=false/voice=false` 对已运行的 loopback API 做了一次 GET 并读取已有当天响应，没有触发 Collector、LLM、voice 或缓存写入；该命令不计入自动验收，交 PK-900 知悉。

### 未迁移内容、公共契约与交接

- 未物理删除 `intel/briefing.py` 的 legacy 论文调用，也未删除 feature 内为旧脚本保留的 `Paper`/`PaperItem` 形状与 journal/摘要 helper；它们已不拥有独立 client 或 limiter。未来若移除 facade，需单独盘点外部 Python 脚本，不属于本轮。
- 未发现 Collector 1.0 公共契约问题，不需要修改冻结 models/contracts，也未导入 PK-110 gateway、service、repository 或 router。
- PK-030 正在混合工作区新增 `server/tests/python-test-inventory.json`；本轮没有越权修改该共享清单。用系统 Python 运行 `python scripts/check_python_test_inventory.py` 会准确报告 `missing=['test_papers_http_runtime.py']`，需由 PK-030/PK-900 串行窗口把这项专属离线测试登记到 `default_offline`。
- PK-133 置为“待集成”，交新的 PK-900 累计验收。PK-900 应重点复核共享 composition hunk、默认 runtime 生命周期、混合 dashboard 保留情况及上述手工工具误调用记录；本任务不暂存、提交、推送、切分支或清理工作区。

## PK-011 可安装化增量（2026-07-30）

### 包边界与实际导出

- `server/features/papers/package_source/manifest.json` 定义
  `papers@1.0.0`、`type=in_process`、`entrypoint=backend.register`、
  `dependencies=["intel_sources"]`、`api_namespaces=["/api/v1/papers"]`、
  `dashboard/index.js`、`data_namespace=papers`、`local_state` 与重启生效。
- `features.papers.register(app)` 是唯一安装入口。它消费可选的宿主
  `intel_collector_registry`、`papers_http_runtime`、`papers_today_provider`、
  `papers_refresh_provider` 及可选查询/期刊/Key/时钟/本机 guard provider；
  不导入 daily briefing 内部实现，也不读取作者注册表、真实查询规则、缓存或凭据。
- 注册时把 `ArxivCollector`、`CrossrefCollector`、
  `SemanticScholarCollector` 逐一写入 Core `CollectorRegistry`，并公开
  `app.state.papers_collector_coordinator`。重复 source ID 会回滚本轮已注册
  Collector；重复 `/api/v1/papers/*` 路由在任何注册前拒绝。
- 安装入口在宿主提供 duck-typed `papers_http_runtime` 时消费该实例；缺失时从包内
  `default_paper_http_runtime()` 创建唯一实例并写回 `app.state`。两条路径均调用
  `install_default_paper_http_runtime(runtime)`，使 Collector 1.0、coordinator 与包内
  兼容 helper 全部指向同一个 client/limiter owner。缺失 registry 时同样从冻结 Core
  `CollectorRegistry` 自举并写回 state，不要求 Core 反向导入 papers。
- `app.state.papers_module_close` 是幂等 async unregister/close callback，并注册为
  shutdown handler：总是按对象身份解注册三个 Collector，只在
  `papers_http_runtime_owned_by_module=true` 时关闭 runtime；同步 loader 注册阶段不
  建立 client、不访问网络，关闭接缝由 app lifespan 收集。
- `GET /api/v1/papers/today` 只调用只读 provider，并经
  `project_today_payload()` 筛选 `category=papers`、跨来源去重、净化和字段投影；
  `POST /api/v1/papers/refresh` 才调用显式 refresh provider，且固定只请求
  `arxiv/crossref/semantic`。二者都不直接访问 daily briefing repository、
  service、gateway、router 或缓存文件。
- 动态 `dashboard/index.js` 只使用 PK-100 的 `context.request` 请求本包命名空间。
  普通挂载只读 today；联网刷新需要二次点击确认。标题、摘要、作者、source/date
  均用 `textContent`，URL 仅接受无 userinfo 的绝对 HTTP(S)，空摘要显示“摘要暂缺”。
- `features.papers.package_builder.build_papers_package()` 只复制白名单内的正式
  Collector/domain/service/http/module/router/projection、manifest 与 dashboard；
  使用固定 ZIP 时间、权限、顺序、LF 和 stored entries，重复构建字节一致。
- `server/features/papers/release/official-release-fragment.json` 与
  `release/README.md` 记录 tag `module-papers-v1.0.0`、asset
  `papers-1.0.0.zip`、`preserve_on_uninstall`、依赖、权限、重启提示和串行发布边界。

### 生命周期、数据与安全证据

- 新增 `server/tests/test_papers_installable_module.py`，使用临时
  `ModuleManager` 安装/启用 fake `intel_sources` 与正式 papers 包，验证安装后默认
  停用、启用加载、停用、卸载保留 `data/modules/papers`、同包重装、依赖声明、
  确定性 ZIP、dashboard 入口和 release manifest。
- 同一测试使用固定时钟、`httpx.MockTransport`、Core `CollectorRegistry`、
  `ASGITransport`、临时 store 与虚构 provider。普通 today GET 的 transport
  调用增量为 0；显式 refresh 仅命中 fake refresh provider，测试本身不调用任何
  真实论文上游。创建一次 fake client 后重复 shutdown，transport `aclose()` 恰好 1 次。
- 重复 Collector 场景在 Crossref 冲突后断言 arXiv 回滚、Semantic 未注册、路由未加入；
  重复 route 场景在 Collector 注册前失败。安装失败/重复安装由 ModuleManager 的原子
  目录与 registry 契约覆盖，不留下半安装版本。
- 包内容审计不含 `features.daily_briefing`、`features.intel_sources` 内部导入，也不含
  真实作者名单、`intel_sources.json`、briefing cache、`.env`、vendor 或脚本。
  `intel_sources` 只通过 manifest 依赖与宿主提供的冻结 request snapshot 参与采集。
- 空 app state 的 installed backend 可以成功自举 registry/runtime，三 Collector 与
  coordinator 的 runtime/三个 limiter 身份完全一致，普通 GET 返回有限 503 且 client
  集合仍为空；随后仅用 MockTransport 建立一个 fake client，重复 close callback 后
  transport 只关闭一次。注入 duck fake runtime 时三 Collector 继续共享同一身份，
  重复 `register()` 不增加路由/Collector，关闭接缝不会越权关闭宿主 runtime。
- 既有 `test_papers_collectors.py` 继续覆盖作者匹配、fallback、摘要补全/净化和跨来源
  去重；`test_papers_http_runtime.py` 继续覆盖 legacy 与 Collector 1.0 的三上游共享
  最大并发、最小间隔、429 退避、取消/失败释放与唯一 close；
  `test_papers_dashboard.py` 继续覆盖当天缓存标题/摘要、零采集/LLM/voice/写入和 DOM 安全。

### 本轮验证

- `server/.venv-asr/Scripts/python.exe tests/test_papers_collectors.py`：通过。
- `server/.venv-asr/Scripts/python.exe tests/test_papers_http_runtime.py`：通过；
  fake Crossref/Semantic 输出仅为虚构数据。
- `server/.venv-asr/Scripts/python.exe tests/test_papers_dashboard.py`：通过。
- `server/.venv-asr/Scripts/python.exe tests/test_papers_installable_module.py`：通过。
- papers backend、builder 与专属测试 `py_compile`：通过。
- papers 专属路径 `git diff --check`：通过；仅有混合工作区既存 LF/CRLF 提示。

### 共享集成与契约结论

- 本轮只修改 `server/features/papers/**`、新增
  `server/tests/test_papers_installable_module.py` 和本任务记录；没有修改
  `TASKS.md`、API、dashboard、catalog、README、Core、daily briefing 或其他来源。
- Collector `1.0` 公共字段没有问题；papers 已直接导入新冻结的
  `core.intel_contracts`，不再反向依赖 `features.daily_briefing`。
- 共享串行窗口只需提供只读当天 briefing 投影、显式三论文来源 refresh，并决定内置
  papers composition 与安装包的互斥/迁移时点。迁移期若两入口必须短暂共存，宿主应把
  现有 runtime 注入 `app.state.papers_http_runtime`；内置入口移除后安装包可完全自有
  runtime。Core 无需也不得导入 `features.papers.http`；这是装配接缝，不要求改变
  Collector `1.0` 模型。
- 任务状态保持“待集成”，交新的 PK-900 累计复核；本轮未构建仓库内 ZIP、未发布
  release/catalog，未暂存、提交、推送、切分支或清理混合工作区。

## PK-000 串行装配审计退回修复（2026-07-30）

- 已移除 installable `register()` 对宿主 `papers_http_runtime` 的强制要求。空
  `app.state` 下，包内自行创建一个 `PaperHttpRuntime` 和一个 Core
  `CollectorRegistry` 并写回 state；Core 无需且静态回归禁止导入
  `features.papers`。若迁移期宿主注入符合 `get/limiter/aclose` duck contract 的
  runtime，则安装包消费该对象且不创建第二实例。
- 无论自举或注入，arXiv/Crossref/Semantic Collector、coordinator 与包内 legacy
  helper 的 runtime 身份均相同，各上游 limiter 身份也来自同一个 runtime。已存在
  另一未关闭默认 runtime 时拒绝替换，避免两套互不知情的限流状态。
- 新公开 `features.papers.unregister(app)` 与
  `app.state.papers_module_close`。callback 在 runtime 选定后立即挂入 shutdown，
  因此同步 loader 后续注册失败也可由 lifespan 收集；它按对象身份解注册三 Collector，
  只关闭包内 owned runtime，重复调用幂等，宿主注入 runtime 不被关闭。
- 包内默认 arXiv cache 路径在源码布局继续使用既有 `server/data/cache/arxiv`；安装
  布局解析到 ModuleManager 保留的 `data/modules/papers/cache/arxiv`，卸载包代码不会
  删除该 namespace。注册与普通 today GET 均不创建 cache/client 或访问网络。
- 永久测试新增：空 Core state 安装加载、零 client 的只读 503、三个 Collector 与
  coordinator/runtime/limiter 身份、自有 MockTransport client 恰好关闭一次、解注册、
  注入 duck fake runtime 不被越权关闭、重复 register 不增加路由、Core 无反向导入、
  确定性包重建。共享 dashboard 串行装配已移除旧静态论文节点，专属
  `test_papers_dashboard.py` 因此改验动态 package panel；未恢复或修改共享 dashboard。
- 修复后 `test_papers_collectors.py`、`test_papers_http_runtime.py`、
  `test_papers_dashboard.py`、`test_papers_installable_module.py`、
  `test_installable_modules.py` 及专属 `py_compile` 通过。全部网络行为仍为
  MockTransport/fake provider；未读取真实作者、查询规则、缓存、Key、`.env` 或凭据。
- 本次只修改 PK-133 专属包、专属测试和本记录；状态保持“待集成”，未修改
  Core/API/TASKS/共享文档，未执行任何 Git 发布操作。

## PK-000 最终候选摘要同步（2026-07-31）

- 为避免完整 pytest 的执行顺序污染，papers 注册失败或卸载时会解除本模块拥有的
  默认 HTTP runtime；宿主注入的 runtime 仍不被关闭。该清理接缝只影响模块运行时
  所有权，不改变 Collector `1.0`、论文查询规则、缓存或 API。
- 最终确定性候选为 `papers-1.0.0.zip`，大小 `113553` 字节，SHA-256
  `a8039450988d72058a99bbc720144b87928b50ac91802d0818b819a7c3651d9a`；manifest
  SHA-256 为 `ac3cac4aa5585f2217e309b3bd2c0ee05ec34114c54364c6d99a2f50f4b47917`。
  两轮构建字节一致，并已进入 19 模块累计安装/启停/卸载/重装与完整 382 项 pytest。
- 以上仍是待 PK-900 复核的本地候选，并非已发布 GitHub Release；未访问真实作者
  名单、缓存、Key、个人状态或外部网络。
