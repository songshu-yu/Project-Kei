# PK-132 — GitHub 用户与仓库采集

- 状态：待集成
- 优先级：P2
- 所属模块：`github_intel`
- 依赖任务：PK-001、PK-010、PK-100、PK-110、PK-115
- 负责路径：`server/intel/collectors/github.py`、`server/features/github_intel/**`、新建 `server/tests/test_github_intel_*.py`、本任务文件
- 当前对话：2026-07-30 由 PK-000 重新打开 PK-011 情报来源可安装化增量
- 并行阶段交接状态：共享集成待排队；不得自行修改 `TASKS.md`

## 并行批次授权（2026-07-22）

- 共同依赖为 `docs/architecture/daily-briefing.md` 已冻结的 Collector `1.0`；需要改变契约时立即停止并交回 PK-000。
- 并行阶段只修改上述负责路径。API、legacy briefing、旧控制台、catalog、README、架构文档和来源配置均留到总控串行窗口或 PK-115。
- 真实 GitHub Token、个人名单与网络不用于自动测试；PK-140 不属于本批。

## 阶段约束

- PK-110 已通过最终复核，Collector `1.0` 已冻结，本任务已由 PK-000 统一领取。
- 用户/仓库配置归 PK-115；本任务只消费只读配置快照，不保存个人名单。

## 目标

独立管理 GitHub 用户公开事件、仓库 Release、可选认证、限流、稳定 ID 和失败表达，并向 PK-110 返回规范化条目。

## 数据所有权

- GitHub 用户和 `owner/repository` 列表归 PK-115。
- GitHub Token 只能来自本机环境，不得进入配置、响应、缓存、日志、测试夹具或任务文档。

## 验收标准

- 用户事件和仓库 Release 分别保留来源类型、时间、URL 与稳定 ID。
- 无 Token、401/403、404、限流、超时、分页边界和错误体脱敏使用假 HTTP 测试。
- 不执行真实 GitHub 采集，不修改 PK-110、PK-115 或其他来源。

## 并行阶段工作记录（2026-07-22）

- 实际导出：`features.github_intel.GitHubCollector` 实现冻结的 `Collector` 协议，固定 `source_id="github"`，公开 `collect(CollectRequest) -> CollectorResult`；`GitHubCollectorSettings` 只承载非秘密超时、分页和信任环境参数。`intel.collectors.github` 同步兼容导出这两个类型，既有 `GithubEvent`、`fetch_github_user_events`、`fetch_github_repo_releases` 接口保持不变。
- 采集范围：从 `source_config_snapshot.github_users/github_repos` 只读消费目标；用户端点为 `/users/{user}/events/public`，仓库端点为 `/repos/{owner}/{repo}/releases`。用户事件和 Release 分别写入 `metadata.record_type=user_event/release`，公共 source/category 固定为 `github/development`，上游 event/release ID 带类型前缀后经冻结 `stable_item_id` 生成稳定 ID。
- 分页与时间窗：每页最多 100 条、默认最多 3 页（运行时非秘密环境参数可收紧/放宽至 1～20 页）；只根据响应 Link 是否含 `rel=next` 决定递增同一端点的页码，不跟随 Link 中的 URL。条目按 `CollectRequest.local_date/timezone/lookback` 过滤；已整页越过时间窗时提前停止，达到页上限且仍有下一页时返回 `partial` 与脱敏 warning。
- 失败与限流：401、普通 403、404、429/限流 403、超时/传输失败、5xx、无效 JSON 和分页上限均转换为有限 warning，不读取或传播上游错误体。单目标失败不阻断其余用户/仓库；有条目同时有失败时为 `partial`，全部失败为 `failed`，成功无内容为 `empty`，无有效配置为 `not_configured`。`Retry-After` 或 `X-RateLimit-Reset` 转换为 Collector/coverage 一致的 RFC 3339 `retry_after`，限流后停止继续请求剩余目标。
- 可选认证：只在请求发出时读取运行环境 `GITHUB_TOKEN`，只允许随 HTTPS `api.github.com` 请求发送；不从配置快照、构造参数或文件读取，不进入 item/metadata/warning/coverage、缓存、响应、日志或测试。重定向关闭，避免认证头跨主机传播。
- 数据与副作用：本模块不保存关注名单、响应、ETag 或缓存，不创建 router/repository/service 持久化边界；只有显式调用 `collect` 才发起 HTTP。自动测试全部使用 `httpx.MockTransport`、固定 aware 时钟和虚构公开数据，认证读取在测试 settings 中关闭；未读取真实名单、缓存、环境凭证，也未执行真实采集。

## 共享集成待排队

- 串行窗口需要把 `GitHubCollector` 注册到生产 Collector dispatch 的 `github` source；其余来源继续走既有 legacy 适配，不能因只注册 GitHub 而把其他 source 误报为 `not_configured`。具体组合位置由 PK-000 在 `server/api.py` / PK-110 共享接缝中统一决定。
- `server/features/catalog/service.py` 需登记 `github_intel` 与 PK-132、`main-api` 进程边界、无独立 HTTP endpoint、显式 briefing 生成/刷新时才联网、单目标失败隔离和限流退避语义。
- `README.md` 需补充 GitHub 用户公开事件/仓库 Release、可选环境认证、分页/限流、重启 API 要求及 `tests/test_github_intel_collector.py` 验证命令；`docs/architecture/daily-briefing.md` 只需记录非破坏性的 GitHub Collector 1.0 实现/装配说明。
- 当前不需要修改 `server/intel/intel_config.py`、`server/static/dashboard.html` 或来源配置模型；目标字段继续由 PK-115 提供。`TASKS.md` 状态仅由 PK-000 在串行窗口更新。
- 公共契约问题：无。实现能够完整表达事件、Release、分页截断、目标级失败、限流 `retry_after` 和可选认证边界，不要求改变 Collector `1.0` 的模型、字段语义、source ID 或兼容规则。

## 专属验证记录

- `server/.venv-asr/Scripts/python.exe tests/test_github_intel_collector.py`：通过。覆盖用户事件、Release、稳定 ID、时间窗、同端点分页、恶意 Link 不跟随、页上限、无认证头、401/403/404、目标失败隔离、429、`Retry-After`、超时、错误体脱敏、无/无效配置。
- `server/.venv-asr/Scripts/python.exe -m py_compile intel/collectors/github.py features/github_intel/__init__.py features/github_intel/collector.py tests/test_github_intel_collector.py`：通过。
- 专属 tracked diff 执行 `git diff --check`，新增专属文件执行尾随空白扫描：均无错误。
- PK-110 共享回归曾尝试启动，但在导入其他并行任务的 `features/papers/domain.py` 时因当前解释器缺少 `zoneinfo` 终止；未进入 PK-110 测试体。该阻断路径不属于 PK-132，未越权修改。

## 独立对话启动提示

```text
仅在 PK-110 Collector 契约冻结后领取 PK-132。只处理 GitHub 用户事件、仓库
Release、限流与规范化 Collector；不得读取或输出真实 Token/关注名单，所有网络
测试使用假 HTTP，不修改 PK-110 汇总或 PK-115 注册表。
```

## PK-119 事后复核与共享收口（2026-07-22）

- 复核确认 `GitHubCollector` 从 PK-115 只读快照消费用户/仓库目标，按公开事件与 Release 输出冻结模型；没有独立 router、缓存或目标所有权，Token 仍只在发请求时从环境读取。
- 已通过统一 `ProjectCollectorGateway` 注册到 `github`，其余七个 source 同时保留，未出现只注册单源导致的覆盖。分页、限流和目标级失败仍由 Collector 自身隔离。
- catalog、README 与架构文档已按实际模块登记。`test_github_intel_collector.py`、PK-119 集成及 PK-110/catalog/dashboard 共享回归通过；没有读取真实 Token/名单或发起真实 GitHub 请求。
- 原并行记录中的 papers `zoneinfo` 导入阻断已由实际代码兼容处理。遗留仅为 PK-900 独立验收与部署后重启。

## 完成文档门禁

- [x] TASK_RECORD — 已按实际代码补记接口、认证/网络副作用、生产装配、验证与遗留。
- [x] TASKS_BOARD — PK-132 已由 PK-000 统一登记为“待集成”。
- [x] PUBLIC_README — 已登记 GitHub 事件/Release、分页与可选认证边界。
- [x] MODULE_CATALOG — 已登记 `github_intel` Collector adapter。
- [x] ARCHITECTURE_DOCS — 已登记 `github` 生产装配与失败隔离。
- [x] LOCAL_README — 不适用；未改变本机路径、端口或解释器约定。
- [x] AGENT_RULES — 不适用；未改变长期 agent 规则。
- [x] VALIDATION — 专属、PK-119 集成及共享回归通过；最终差异检查由 PK-119 记录。

## PK-000 最终复核（2026-07-22）

PK-900 报告及实际目标级失败隔离、环境 Token 边界、跨源脱敏与八源装配经独立复核通过；PK-132 置为“已完成”。

## PK-011 可安装化增量入场与契约阻塞（2026-07-30）

- PK-000 已重新打开 PK-132，并把 PK-010、PK-100、PK-110、PK-115 补入当前
  增量依赖；`TASKS.md` 由总控持有，本任务没有修改。
- 本轮目标是在 `server/features/github_intel/` 专属路径交付确定性安装包：
  manifest、`backend.register(app)`、package builder、必要时的动态来源面板、固定
  官方 Release 元数据，以及使用 MockTransport、临时路径和 ModuleManager 的隔离
  生命周期测试。原 Collector 1.0 的用户公开事件、仓库 Release、分页、限流、
  可选环境认证、去重和单目标失败隔离语义必须原样保留。
- 入场只读核查确认 Collector 1.0 目前仍由
  `features.daily_briefing.collector_contracts`、`features.daily_briefing.models`
  和 `features.daily_briefing.time_utils` 暴露；`server/core/` 尚无 intelligence
  contract 模块。现有 `features.github_intel.collector` 因而仍直接导入
  `features.daily_briefing`。
- 入场只读核查同时确认 ModuleManager 的 in-process loader 只调用
  `backend.register(app)`，当前 Core 没有公开的 Collector registry/discovery
  接口。若现在生成安装包，backend 只能反向导入 PK-110 的
  `source_composition`、gateway 或 service 才能进入生产采集，这违反本批
  “只依赖 Core 契约与 intel_sources 公开 API”的冻结边界。

### 交回 PK-000 / PK-110 的精确公共契约需求

1. 冻结一个稳定的 Core intelligence import path（例如
   `core.intel_contracts`，精确名称由 PK-000/PK-110 决定），公开与 Collector
   1.0 对象身份和序列化语义兼容的 `Collector`、`CollectRequest`、
   `CollectorResult`、`IntelItem`、`SourceCoverage`、`CacheStatus`、
   `CoverageStatus`，以及来源实现必需的 `rfc3339`、`stable_item_id`、时区
   本地化和公共脱敏 helper。迁移必须保持 `contract_version="1.0"`、八个
   public source ID、字段指纹和未知字段兼容规则不变，不能要求安装包复制模型。
2. 冻结一个可由 `backend.register(app)` 使用的 Core Collector 注册/发现接口，
   使安装包能以 `source_id="github"` 注册 Collector factory/instance，而不导入
   PK-110 gateway、service、repository、router 或 `source_composition`。接口需
   明确：生产 composition 何时消费注册项、相同 source ID 的重复注册行为、
   同一 backend 重复调用的幂等/冲突语义、单模块加载失败隔离，以及启用/停用/
   卸载在“重启后生效”模型下如何移除注册项。
3. Collector 仍应只从 Core `CollectRequest.source_config_snapshot` 消费
   `github_users/github_repos`；安装包 manifest 只声明对 `intel_sources` 的模块
   依赖，不得读取其 repository、真实名单或文件。若 PK-115 还要求额外的公开
   Python/HTTP 接缝，需先冻结精确接口，不能让 PK-132 反向导入其私有
   service/repository。

以上不是要求改变 Collector 1.0 的业务字段，而是安装包缺少稳定 Core 导入与
注册接缝。依照批次规则，本任务在此停止实施：尚未创建 manifest、backend、
builder、面板、Release 元数据或生命周期测试，也未读取真实来源名单、缓存、
`.env`、Token、vendor、脚本，未发起任何网络请求或执行 Git 发布。待 PK-000
确认上述契约已经冻结并落入工作区后，再继续专属实现；当前不能进入“共享集成
待排队”。

## PK-011 可安装化增量交付（2026-07-30）

### 契约阻塞解除

- 中断恢复后确认 `core.intel_contracts` 已冻结并公开 Collector 1.0 模型、协议、
  时间/脱敏 helper 与 `CollectorRegistry`；PK-110 的 legacy facade 保持同一对象
  身份，`RegistryCollectorGateway` 在每次采集时读取 registry snapshot。
- GitHub Collector 已改为只导入 `core.intel_contracts`。实现、包内 backend 与
  测试均不导入 PK-110 gateway、service、repository、router 或
  `source_composition`，也不导入 PK-115 私有实现。
- Core registry 使用同批已落地的 `app.state.intel_collector_registry` Provider
  接缝：不存在时建立 Core `CollectorRegistry`，存在时复用；同一 backend 重复
  注册返回原实例，其他实现已占用 `source_id="github"` 时按 Core 冲突规则失败，
  不覆盖已有来源。

### 1. 实际导出的 Collector / 接口

- `features.github_intel.GitHubCollector`、`GitHubCollectorSettings`：原 Collector
  1.0 用户公开事件/仓库 Release、分页、限流、可选环境认证、稳定 ID、去重和
  单目标失败隔离语义保持不变。
- `features.github_intel.register(app)`：安装包 `backend.register` 的同一 Provider
  接缝；只向 Core `CollectorRegistry` 注册一个 `github` Collector，不新增 HTTP
  路由、后台循环、缓存或目标配置所有权。
- `features.github_intel.package_builder.build_github_intel_package()` 与
  `file_sha256()`：生成可审阅目录或 byte-for-byte 确定性 ZIP；固定版本
  `1.0.0`、tag `module-github-intel-v1.0.0`、asset
  `github-intel-1.0.0.zip`。
- 动态入口导出 `mount(context)` / `unmount()`。面板只显示能力和数据边界，不调用
  API、不触发采集、不读取浏览器存储；用户/仓库目标继续由 `intel_sources`
  公共面统一管理。
- manifest：`id=github_intel`、`in_process`、硬依赖 `intel_sources`、无自有 API
  namespace、无配置 Schema、无权限、`data_namespace=github_intel`、
  `requires_restart=true`。启用前 ModuleManager 会要求 `intel_sources` 已安装且
  启用。

### 2. 专属修改路径

- `server/features/github_intel/__init__.py`
- `server/features/github_intel/collector.py`
- `server/features/github_intel/provider.py`
- `server/features/github_intel/package_builder.py`
- `server/features/github_intel/package_source/manifest.json`
- `server/features/github_intel/package_source/backend/__init__.py`
- `server/features/github_intel/package_source/dashboard/index.js`
- `server/features/github_intel/release/official-release-fragment.json`
- `server/features/github_intel/release/official-catalog-entry.json`
- `server/tests/test_github_intel_collector.py`
- `server/tests/test_github_intel_package.py`
- `tasks/PK-132-github.md`

未修改 `TASKS.md`、共享 API/catalog/dashboard、PK-110、PK-115、Core module
manager、架构文档或其他来源；未暂存、提交、推送、发布或清理混合工作区。

### 3. 测试结果

- `server/.venv-asr/Scripts/python.exe tests/test_github_intel_collector.py`：
  通过。全部上游请求为 MockTransport；原事件/Release、同端点分页、时间窗、
  401/403/404、429、retry-after、超时、脱敏、分页上限与目标失败隔离保持通过。
- `server/.venv-asr/Scripts/python.exe tests/test_github_intel_package.py`：
  通过。覆盖确定性 ZIP/manifest/release 摘要、包内容 allowlist、Core Provider
  自动建立与幂等、冲突来源失败隔离、零路由重复、安装/启用/停用/卸载/重装、
  临时 config/cache 保留、已安装 Collector 的 MockTransport 采集、动态入口
  Node 语法，以及固定官方 Release 的匿名 MockTransport 安装。
- `server/.venv-asr/Scripts/python.exe tests/test_daily_briefing_installable.py`：
  通过，确认 Core registry 与 daily_briefing 可安装消费者兼容。
- `server/.venv-asr/Scripts/python.exe tests/test_installable_modules.py`：
  通过。
- `server/.venv-asr/Scripts/python.exe tests/test_official_module_catalog.py`：
  通过。
- 专属 Python `py_compile`：通过；动态入口 `node --check` 已由专属包测试通过。
- 专属路径尾随空白扫描无匹配。所有测试仅使用临时目录、fake/MockTransport；
  未读取真实来源名单、缓存、`.env`、Cookie、凭据、模型、vendor 或运行脚本，
  未发起真实 GitHub/Release 请求。

### 4. 共享串行窗口需写入的内容

- 官方 catalog 合入
  `server/features/github_intel/release/official-catalog-entry.json`，发布时对串行窗口
  重新构建相同 ZIP 并复核 manifest/package SHA-256 与字节数；模块获取继续只走
  Core 固定 `songshu-yu/Cyber-Girlfriend` 匿名 Release 来源，不复用 GitHub 情报
  采集认证。
- `server/api.py` / PK-110 生产装配应在加载可选情报模块时共享同一个
  `app.state.intel_collector_registry`，并由 daily_briefing 的 registry gateway
  消费；移除旧生产 composition 对 `GitHubCollector` 的无条件内置注册，确保停用
  或卸载后重启确实不再采集 GitHub。legacy 直接脚本兼容出口可保留。
- `server/features/catalog/service.py` 登记 `github_intel@1.0.0` 为 installable
  in-process Provider，依赖 `intel_sources`、无自有 API、显式 briefing 生成/刷新
  才联网、卸载保留数据、启停需重启。
- README 与安装/每日情报架构文档记录：目标配置归 `intel_sources`，Collector
  只消费只读快照；官方模块下载匿名固定来源，情报认证仅请求时从运行环境读取，
  两者完全分离；普通 catalog/面板/缓存读取零网络。
- PK-100 动态外壳无需增加共享按钮或专属 API，只需按现有 manifest 自动发现
  `dashboard/index.js`；面板不能越权请求 `intel_sources` namespace。

### 5. 公共契约问题

- 无。此前缺少 Core import/registry 的阻塞已由 PK-110 的
  `core.intel_contracts`、`CollectorRegistry` 与 registry gateway 解决；本任务
  未要求改变 Collector `1.0` 字段、source ID、模型身份、兼容规则、ModuleManager
  manifest/lifecycle 或 `intel_sources` 公共 API。
- 剩余事项是共享生产 composition、catalog 与公开文档的串行接线，不是公共契约
  缺口。本任务停在“共享集成待排队”，等待 PK-000 分配串行窗口。

## PK-011 可安装化增量完成文档门禁

- [x] TASK_RECORD — 已记录导出、包契约、Provider、网络/数据副作用、测试与共享接线。
- [x] TASKS_BOARD — 由 PK-000 统一持有；本任务未修改 `TASKS.md`，当前在任务记录中待集成。
- [x] PUBLIC_README — 共享文件冻结；已在上节给出串行窗口的精确写入内容。
- [x] MODULE_CATALOG — 共享文件冻结；专属官方 catalog entry 已生成，待串行合入。
- [x] ARCHITECTURE_DOCS — 共享文件冻结；已列出 registry/数据/认证分离说明，待串行合入。
- [x] LOCAL_README — 不适用；未改变本机路径、端口、解释器或启动约定。
- [x] AGENT_RULES — 不适用；未改变长期 agent 规则。
- [x] VALIDATION — 专属与相关 Core/PK-110/官方 catalog 回归均通过，网络全为 fake。
