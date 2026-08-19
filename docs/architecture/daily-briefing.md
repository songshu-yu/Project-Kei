# 每日情报 Collector、缓存与 Kei 播报契约

## 边界与依赖

PK-110 是主 API 内置的 `daily_briefing` 模块，代码位于 `server/features/daily_briefing/`。它拥有 Collector 公共协议、规范化条目、汇总/失败隔离、去重排序、数量限制、当天缓存、来源覆盖、补采冷却、PK-200 改写与当天播报稿。

Collector `1.0` 已于 2026-07-22 经 PK-900 与 PK-000 最终复核正式冻结。PK-115/120/130/131/132/133/134 等下游来源任务可以按本协议独立领取和并行实施；破坏性修改必须交回 PK-000 决策并提升 major。

它不拥有关注对象注册表、平台鉴权/限流、任何具体 Collector、QQ 定时器、LLM client、Voice Pack、TTS Provider 或音频生命周期。依赖方向固定为：

```text
PK-115/120/130/131/132/133/134 Collector -> PK-110 collector_contracts/models
PK-110 -> PK-200 TextGenerator
PK-110 legacy voice adapter -> PK-210 TextToSpeechProvider + VoicePackResolver + VoiceArtifactStore
控制台/QQ/voice consumer -> PK-110 public service or HTTP API
```

`server/services/daily_briefing.py` 只保留旧 Python 导入。主 API 通过 `source_composition.py` 组装七个来源任务交付的 Collector；`server/intel/briefing.py` 与 `LegacyCollectorGateway` 只保留直接脚本、旧 Python 调用和隔离兼容测试，不再是主 API 的生产 composition root。`server/intel/collectors/*` 仍分别属于对应来源任务，不属于 PK-110。

## Collector 契约 1.0

公开入口是：

```python
class Collector(Protocol):
    source_id: str
    async def collect(self, request: CollectRequest) -> CollectorResult: ...

class CollectorGateway(Protocol):
    async def collect(self, request: CollectRequest) -> Sequence[CollectorResult]: ...
```

当前版本为 `1.0`。同一 major 内，读者必须忽略未知对象字段；缺少必填字段或 major 不兼容时拒绝该单源结果，不能击穿其他来源。破坏性字段修改必须返回 PK-000 决策并提升 major。

### CollectRequest

| 字段 | 类型 | 规则 |
|---|---|---|
| `contract_version` | string | 必填，当前 `1.0` |
| `local_date` | `date` / `YYYY-MM-DD` | 必填，本机目标日期 |
| `timezone` | IANA timezone | 必填；当前默认 `Asia/Shanghai` |
| `source_ids` | string list | 必填、去重；未知但格式合法的 ID 允许进入 gateway 并形成单源 `not_configured`，不能导致汇总崩溃 |
| `refresh` | boolean | 必填；只表达调用者明确的强制刷新意图 |
| `lookback` | integer | 必填，单位小时，范围 1～720 |
| `source_config_snapshot` | JSON object | 必填只读快照；不能含 Token、Cookie、API Key、Authorization、响应头或客户端对象 |

`source_config_snapshot` 只传给 Collector，不写入 PK-110 缓存、响应或 prompt。

### IntelItem

| 字段 | 必填 | 规则 |
|---|---|---|
| `contract_version` | 是 | 当前 `1.0` |
| `stable_id` | 是 | 不超过 160 字符；来源模块升级后对同一上游实体保持稳定 |
| `source_id` | 是 | 格式 `[a-z][a-z0-9_.-]{0,63}` |
| `category` | 是 | 展示区，如 `papers/social/development/video/money/general` |
| `title` | 是 | 规范空白，最长 1000 字符 |
| `summary` | 否 | 规范空白，最长 4000 字符 |
| `url` | 否 | 只接受无 userinfo 的绝对 HTTP(S)，最长 2048，去 fragment；Token、Cookie、Authorization、API Key、session、signature 等敏感 query 参数直接移除，其余 query 值再次做凭证形态脱敏 |
| `author` | 否 | 最长 300 字符 |
| `published_at` | 否 | RFC 3339、必须带时区；缺失使用空字符串，不伪造时间 |
| `fetched_at` | 是 | RFC 3339、必须带时区 |
| `metadata` | 否 | 有界 JSON object；不能含 Token、Cookie、secret、Authorization、API Key、密码或请求/响应头 |

Collector 不返回平台 client、HTTP response、异常对象、文件句柄或 repository。公共模型统一对 stable ID、标题、摘要、作者、warning、coverage detail、metadata 字符串值和 URL 做有限脱敏；秘密/headers 键会移除，未批准的 Python 对象只保留类型名，不能依赖每个 Collector 自行清洗。公共函数 `sanitize_external_text`、`normalize_url` 与 `json_safe_mapping` 从模块边界导出，供已授权的来源任务复用。PK-110 不把 metadata 全量发送给 LLM。

### CollectorResult

| 字段 | 规则 |
|---|---|
| `contract_version` | 当前 `1.0` |
| `source_id` | 与本次单源 Collector 和所有 `items[].source_id` 一致 |
| `items` | 规范化 `IntelItem` 列表 |
| `warnings` | 有界、脱敏的可展示字符串；不能放异常对象或完整上游错误体 |
| `coverage` | `SourceCoverage`，见下表 |
| `fetched_at` | 带时区 RFC 3339 |
| `retry_after` | 可空；带时区 RFC 3339 |
| `cache_status` | `hit/fetched/refreshed/bypass/unavailable` |

`coverage` 的状态语义固定为：

| 状态 | 含义 |
|---|---|
| `complete` | 本次成功且取得至少一个规范化条目 |
| `empty` | 本次成功、来源已配置，但目标窗口内没有条目 |
| `partial` | 有可用条目，同时存在来源级 warning/失败；旧内容在补采失败时也使用此状态 |
| `failed` | 已尝试但失败，不能描述为“今天没有内容” |
| `not_configured` | 没有活动配置、没有注册 Collector，或 legacy gateway 不认识该来源 |

`SourceCoverage` 缓存并返回 `status/item_count/detail/retry_after`。`CollectorResult.retry_after` 与 coverage 中的同名值保持一致，方便只读消费者不解析 warning 猜测重试时间。

已知来源失败使用兼容的 warning 诊断约定：`<source>: <bounded count> ... (<finite_code>)`。这不是 Collector `1.0` 的新字段；旧消费者仍可把 warning 当普通展示字符串，新控制台只从已经净化且匹配 `[a-z][a-z0-9_]{1,63}` 的括号值读取诊断码。一个来源可返回多个按码聚合的 warning，禁止写入账号、目标 ID、请求 URL、异常正文、响应体或凭证。当前有限映射为：

- X/Nitter：`timeout/network_error/rate_limited/access_denied/not_found/http_error/upstream_unavailable/parse_error/invalid_response`
- B 站：`anti_bot/rate_limited/timeout/not_found/upstream_rejected/upstream_unavailable/invalid_response/upstream_failed`
- RSS：`timeout/network_error/rate_limited/access_denied/not_found/http_error/upstream_unavailable/parse_error/invalid_response/redirect_missing_location/redirect_rejected/too_many_redirects/response_too_large/upstream_failed`

来源内部出现未知异常标识时必须降级为该来源允许的通用有限码，不得把未知字符串直接穿透。重试、冷却、coverage 判定和条目内容规则不因诊断约定改变。

### 序列化示例

```json
{
  "contract_version": "1.0",
  "source_id": "github",
  "items": [
    {
      "contract_version": "1.0",
      "stable_id": "github:0123456789abcdef0123456789abcdef",
      "source_id": "github",
      "category": "development",
      "title": "example/repository released v1.2.3",
      "summary": "Release notes summary",
      "url": "https://github.com/example/repository/releases/tag/v1.2.3",
      "author": "example/repository",
      "published_at": "2026-07-22T00:30:00Z",
      "fetched_at": "2026-07-22T01:00:00Z",
      "metadata": {"event_type": "release"}
    }
  ],
  "warnings": [],
  "coverage": {"status": "complete", "item_count": 1, "detail": "", "retry_after": null},
  "fetched_at": "2026-07-22T01:00:00Z",
  "retry_after": null,
  "cache_status": "fetched"
}
```

## 公共来源 ID 与 legacy 映射

| source ID | 当前 legacy key / 识别规则 | 展示区 |
|---|---|---|
| `twitter` | `twitter`；普通 X 与信息差 X 均在这里 | `social` |
| `github` | `github_users + github_repos` | `development` |
| `bilibili` | `bilibili` | `video` |
| `youtube` | `youtube` | `video` |
| `money` | `money_tips`，当前普通 RSS 聚合 | `money` |
| `arxiv` | `papers` 且 field/source 不是 Crossref/Semantic Scholar | `papers` |
| `crossref` | `papers` 且 field/source 为 `crossref` | `papers` |
| `semantic` | `papers` 且 field/source 为 `semantic_scholar` | `papers` |

生产 `ProjectCollectorGateway` 注册 `NitterCollector`、`GitHubCollector`、`BilibiliCollector`、`YouTubeCollector`、`RSSIntelCollector`、`ArxivCollector`、`CrossrefCollector` 与 `SemanticScholarCollector`。前五类平台来源经 `ContractCollectorGateway` 并发且逐来源隔离；三类论文来源经 `PaperCollectorCoordinator` 按 arXiv → Crossref → Semantic 顺序协调，使 Semantic fallback 只查询尚未被前两类覆盖的作者，同时保留三份独立 `CollectorResult`。摘要补全和论文跨来源去重在论文模块内部完成，不改变 Collector 1.0 字段。关闭时按对象身份去重并尝试关闭全部平台与论文 Collector；单个 closer 失败不会跳过其余资源，全部尝试结束后才以不含异常正文的有界 `CollectorCloseError` 报告失败来源与异常类型。

论文生产 composition 只从 `features.papers` 公共出口导入三类 Collector。`features.papers.http.PaperHttpRuntime` 是论文上游 HTTP 的进程级唯一协调所有者：每个 arXiv、Crossref、Semantic Scholar 上游各有一个共享 client 和 limiter，统一控制最大并发、最小请求间隔、429 `Retry-After`/退避与幂等关闭；Collector 1.0 和 legacy Python 入口都委托同一默认 runtime，也可在隔离测试中注入同一个 fake runtime。`intel.collectors.arxiv` 与 `intel.collectors.papers` 仅保留 deprecated 导出 facade，不拥有 HTTP client、limiter 或第二套采集规则。runtime 的关闭责任由 `PaperCollectorCoordinator` 持有，gateway 仍按对象身份去重，因此共享 client 恰好关闭一次。

`LegacyCollectorGateway` 继续为兼容测试或直接旧调用按 source ID 调用 `gather_all_intel(...)`。legacy gather 的失败日志和 warning 只记录来源、有限状态和异常类型，不输出异常正文、作者目标或完整错误体。新来源实现只依赖 `collector_contracts.py` 与 `models.py`，不导入 PK-110 gateway/service/repository/router。

### 生成进度可观测性（不改变 Collector 1.0）

`ObservableCollectorGateway.collect_with_progress(request, on_result)` 是 PK-110 gateway 的可选能力，不是 Collector `1.0` 的新增字段或破坏性变更。单个 Collector 仍只实现冻结的 `collect(request) -> CollectorResult`；旧 gateway 与测试 fake 只实现 `collect()` 仍然有效。生产 `ContractCollectorGateway` 在各并发来源完成时回调规范化 `CollectorResult`，`ProjectCollectorGateway` 对平台来源逐个回报、对论文协调结果保留真实 `arxiv/crossref/semantic` 身份后回报。

`BriefingGenerationTracker` 只在主 API 进程内保存当前/最近一次 mutation 的有界脱敏状态，不新增持久文件。公开只读入口为 `GET /api/v1/briefing/generation-status`，legacy `/dashboard/briefing/status` 的 `generation` 字段委托同一 tracker。前者只读取 tracker；legacy 状态中的缓存视图也直接只读 repository，不借状态查询清理跨天 summary。两者均为零 Collector、零 PK-200、零 PK-210、零缓存写入。

状态契约固定为：

- `state`: `idle | running | succeeded | failed`
- `phase`: `idle | collecting | rewriting | saving | finished`
- `started_at/finished_at`: aware RFC 3339 或 `null`；`elapsed_ms` 最多七天
- `completed_sources/total_sources`: 当前 mutation 实际工作集中的有限整数计数；缺失来源补采会在 collector 调用前把工作集收窄为本轮 `patch_ids`，未参与本轮的公共来源保持 `not_requested`（未知扩展 ID 不进入公开进度）
- `sources`: 键始终仅为八个 public source ID，值仅为 `not_requested | pending | running | complete | partial | empty | failed | not_configured`
- `source_error_codes`: 键始终仅为八个 public source ID，值为白名单有限码数组；只从规范化 Collector warning 的括号码中提取，未知值丢弃
- `error_code`: `null | cancelled | cache_save_failed | generation_failed`

状态不包含条目正文、标题、摘要、URL、账号、来源配置、内部路径、prompt、warning/detail、异常正文、headers 或任何凭证。`source_error_codes` 当前白名单只覆盖公开 UI 已知的网络、HTTP、解析、限流、风控与上游可用性有限码；任意虚构码或秘密样式括号内容都不会进入状态。service 的 mutation lock 保持原生成串行语义；tracker 另用线程锁保护快照，并以单调 run token 忽略旧 run 的迟到更新。API 重启后状态自然回到 `idle`，缓存语义不受影响。

控制台的“来源状态与错误详情”同时读取当天 briefing 中已经净化的缓存 `coverage/warnings/retry_after`，以及 generation-status 中最近一次运行的 `source_error_codes`。两者必须分别标为“本次运行”和“缓存”，避免失败刷新保留旧字节时把历史原因冒充为当前诊断；没有有限码时明确显示“来源未提供”，不得从通用失败文本臆测平台内部原因。“今日论文”和“Kei 今日播报总结”同样使用原有只读缓存接口并默认收起，展开动作零 Collector、零 PK-200、零 PK-210、零写入。

逐来源调试复用版本化 `POST /api/v1/briefing/refresh`，请求体固定为 `{"source_ids":["<public_source_id>"],"rewrite":false,"rewrite_refresh":false,"patch_missing":false}`。它是显式联网操作，必须经过本机控制守卫和控制台确认。存在当天缓存时，refresh 不再从所选子集新建主文档，而是在旧文档上用 `_merge_patch` 事务替换所选来源：成功替换该来源 items/coverage/warnings，失败保留该来源旧 items，其他来源始终保持；主缓存与 summary 仍共用原子提交/回滚边界。无当天缓存时才以所选来源建立新文档。公共 gateway 负责来源间异常隔离和父调用取消传播，但不再对整个 Collector 施加固定 120 秒总时限；X、B 站等多目标来源继续由各自 Collector 的单次请求超时、有限重试、节流和冷却约束。单来源按钮执行期间互斥，浏览器请求最长等待 35 分钟，并继续通过 generation-status 显示采集/保存进度。原生终端观察同样只能读取该脱敏状态，不打印账号、条目、URL、响应正文、异常正文或凭据。

## 已装配来源模块

| 任务 | 模块/Collector | 配置与状态所有权 | 关键边界 |
|---|---|---|---|
| PK-115 | `features/intel_sources` | 忽略的 `server/data/intel_sources.json` | 版本化增改删、原子写与只读快照；保存不触发采集 |
| PK-120 | `NitterCollector`、`features/x_monitor` | X 资料与单一 `Asia/Shanghai` 当日兼容缓存；日期查询不持久化 | 普通/信息差 X 共用 `twitter`，组别写入 metadata；仅显式单用户获取联网 |
| PK-130 | `BilibiliCollector`、`features/bilibili` | B 站资料缓存；动态冷却为进程内 | 资料查询与空间动态分离；昵称/头像在响应和缓存前净化；有限重试和每 UID 冷却 |
| PK-131 | `YouTubeCollector` | Channel ID 归 PK-115，无来源缓存 | 只接受 `UC` Channel ID，固定公开 Atom Feed，非法值零请求 |
| PK-132 | `GitHubCollector` | 目标归 PK-115；可选 Token 仅环境 | 用户公开事件与 Release，有限分页、限流和目标级隔离 |
| PK-133 | `features.papers` 三论文 Collector、coordinator 与共享 HTTP runtime | 作者归 PK-115；arXiv 缓存来源私有；Key 仅环境；legacy 文件仅 facade | 三来源独立 coverage、fallback-only Semantic、摘要补全、跨来源去重；同上游共享并发/间隔/429 冷却 |
| PK-134 | `RSSIntelCollector` | 固定 Feed/关键词归 `intel_config.py` | `money` source ID，HTTPS 公网 allowlist、逐跳重定向与响应限长 |

PK-115 的版本化接口为 `GET/PUT /api/v1/intel-sources`、`POST /api/v1/intel-sources/{field}`、`PUT/DELETE /api/v1/intel-sources/{field}/{index}`。PK-120 提供只读缓存 `GET /api/v1/x/profiles|posts`，以及显式的 `/api/v1/x/profiles/resolve`、`/api/v1/x/posts/fetch` 与 `/api/v1/x/posts/query`。兼容 fetch 表示 `Asia/Shanghai` 今天 00:00 至请求时刻并更新单一今日缓存；query 的 `day` 表示本地自然日半开区间，`since` 表示所选日 00:00 至请求时刻，最多回溯包含今天在内的 30 个自然日，响应不落盘。普通 GET 在缺失、损坏或跨天时只返回空视图，不触发外部网络。PK-130 提供只读缓存 `/api/v1/bilibili/profiles` 与显式查询 `/api/v1/bilibili/profiles/resolve`。旧 `/dashboard/intel-sources*` 路径继续委托相同 registry/service，并复用版本化控制接口的本机客户端与浏览器 Origin 限制。控制台使用版本化路径，打开页面、选择日期、切换已有结果、展开账号和来源 CRUD 都不隐式 resolve/fetch；保持逐项操作和“保存不自动刷新情报”语义。

PK-120 在 Nitter RSS 适配层根据明确的 reply、retweet 和 quote 结构互斥分类，但仍只有一个统一言论通道。显式采集只请求公共 `/<handle>/rss`；纯转发、冲突结构和 unknown 关闭失败并跳过。兼容今日 fetch 将窗口内实际存在的 `post`、`quote` 和 `reply` 统一写入 `x_daily_posts.json`，repository 固定以 `Asia/Shanghai` 日期按用户原子替换，失败保留旧字节；同一天的 Schema 1 缓存只读兼容为普通发帖，不自动迁移或改写。显式日期/区间 query 复用同一 service 和日期窗口构造函数，只返回净化后的本次结果、partial coverage 与有限 warning，不读取或写入查询缓存。适配层不跟随当前状态链接，也不补抓父帖、引用状态、祖先或线程，因此不会对公共 RSS 没有提供的历史或回复作完整性承诺。

`NitterCollector` 的 `source_id=twitter` 和 Collector `1.0` 输入/输出指纹不变。可展示的 `post`、`quote`、`reply` 仍直接构造冻结 `IntelItem`，分类和普通/信息差来源组仅写入 metadata；PK-120 不导入 PK-110 gateway、service、repository 或 router。

X 控制台窗口与 Collector 窗口必须区分：此前单用户入口误按 UTC 自然日，现已固定为 `Asia/Shanghai`；daily briefing 的 `NitterCollector` 仍按 `CollectRequest.lookback` 使用滚动窗口（通常 24 小时）。本次没有把 briefing 改成自然日，也不能把两者笼统描述为同一个“今天”。

## stable ID、去重、时间与排序

- legacy 稳定 ID 按 `source_id + 上游 ID` 生成；没有上游 ID 时依次使用规范 URL，最后使用规范化标题、作者和发布时间，SHA-256 截取固定 32 个十六进制字符。
- 同来源按稳定 ID、相同规范 URL、标题大小写/空白归一后去重；缺 URL 时仍能使用稳定 ID/标题。
- 不同非论文来源仅在规范 URL 完全相同等强证据下合并，不能因为内容相似就误删。
- 论文按 DOI、规范 URL、标题归一跨 arXiv/Crossref/Semantic Scholar 去重；合并项的 `metadata.discovery_sources` 保留全部真实 source ID，`alternate_stable_ids` 保留各来源 ID。
- 跨来源合并 stable ID 使用去重键生成，不随 Collector 返回顺序变化。
- 所有输入时间先转 UTC aware datetime；naive datetime 在公共 Schema 中拒绝。legacy 无时区字符串只在 adapter 内按请求 IANA timezone 明确本地化。
- 超过当前时刻 5 分钟的未来条目排除；超出 lookback 排除；缺失发布时间保留并稳定排在有时间条目之后。
- 排序先按发布时间倒序，再按 stable ID；最后按 section limit 截断。默认 `papers=30`，其余展示区各 5 条。

## 缓存与补采

PK-110 只拥有：

```text
server/data/briefing_cache/YYYY-MM-DD.json
server/data/briefing_cache/kei_summary_today.json
```

主缓存 Schema 为 `schema_version=1`，保存规范化 items、coverage、warnings、patch_attempts、原始 briefing text、明确日期/时区和 aware 时间戳；不保存来源配置快照、凭证、headers、异常对象或音频。播报稿单独写入 `kei_summary_today.json`，包含 schema、日期、`generated/fallback`、更新时间和主内容摘要。该摘要覆盖 items、原始 text、coverage 与 warnings；任一播报事实发生变化都会使旧稿失效。主缓存不再重复嵌入新播报稿。

两类文件都在同目录使用唯一临时文件、`flush/fsync` 与 `os.replace`。需要同时更新主缓存和当天播报稿时，repository 先完整暂存两份 payload 并记录提交前字节，再依次替换；任一替换失败都会按提交前快照恢复两个目标并清理普通/恢复临时文件。异常以 `cache_state_preserved` 明确回滚是否成功，HTTP 只有在该值为真时才声明旧缓存已恢复。进程内生成/刷新/补采使用同一 async mutation lock；读取依赖原子替换，不会看见半 JSON。

- 普通读只调用 repository，不触发 Collector、PK-200 或 PK-210。
- 有效当天缓存直接复用；`refresh=true` 才明确覆盖有效主缓存。
- 显式 refresh 仍先读取旧可用版本作为事务保底；gateway 异常，或所有请求结果都没有成功 `empty` 状态/带条目的 `complete|partial` 状态时，不写主缓存、不写播报稿、不调用 PK-200，返回旧 items/text/script，并用 `refresh_status=failed_using_cache` 与“刷新失败，继续使用旧缓存”明确标记。
- 缺失补采只选择 `failed/partial` 且已到 `retry_after`/本地冷却的来源。
- 补采成功按来源合并并再次去重；失败保留旧 items，更新 warning、coverage 与 retry_after。只要 items、coverage、warning 或原始 text 的摘要改变，内存旧稿立即失效；请求了 rewrite 就重新生成，否则写入明确 fallback。成功响应与立即重读缓存的 script/status 必须一致。
- 来源配置保存不调用 PK-110 generate/refresh。
- 跨天 `kei_summary_today.json` 在 service 初始化或当天读取时失效并尽力删除；旧日期绝不展示。
- 同日已经生成或已回退的播报稿默认复用；只有 `rewrite_refresh=true` 重新调用 PK-200。
- 损坏 JSON、未知主缓存 Schema、日期不匹配或不兼容 Collector major 返回 cache miss，不覆盖原文件。旧无 Schema 缓存可只读映射为规范化模型；不会为验证迁移而改写真实历史缓存。

## Kei 改写与语音

PK-110 只持有 PK-200 `TextGenerator`。prompt 把条目序列化到明确的 `UNTRUSTED_DAILY_BRIEFING_DATA` JSON 区，并声明标题、摘要、作者、URL、warning 中的指令/角色扮演/系统提示注入全部不可执行。每字段和总 prompt 都有上限，metadata、凭证、headers、内部路径及完整错误体不进入 prompt。

PK-200 成功时缓存 `generated=true/fallback=false`；异常、超时、空回复或明确 `generated=false` 时使用原始摘要稿，并缓存 `generated=false/fallback=true`，不能伪装成功，也不会在同日普通读取时重复付费。

`POST /briefing/today/voice` 将播报文本交给 `PK210BriefingVoiceProvider`。该 adapter 只依赖 PK-210 的 `TextToSpeechProvider`、`VoicePackResolver` 和 `VoiceArtifactStore`，返回同源 voice audio URL；不导入具体 `TTSClient`，不把音频写入 briefing 缓存。Provider 缺失/失败时保留 text/script，并返回 `audio_available=false`、`mode=text_only`、`degraded=true` 和有限错误。

## HTTP 接口

| 方法与路径 | 副作用与语义 |
|---|---|
| `GET /api/v1/briefing/today` | 只读当天主缓存和播报稿；没有缓存时 `ready=false` |
| `POST /api/v1/briefing/generate` | 仅本机；显式生成，无有效缓存时采集，已有缓存按补采冷却复用 |
| `POST /api/v1/briefing/refresh` | 仅本机；强制全量刷新并覆盖当天主缓存 |
| `GET /api/v1/briefing/today/script` | 只读当天播报稿与 generated/fallback 状态 |
| `GET /briefing/today` | legacy 字段兼容；默认 `fetch=false`，显式 `fetch=true` 才允许生成/补采 |
| `POST /briefing/today/voice` | legacy 字段兼容；默认只读缓存并把文本交给 PK-210 |
| `GET /dashboard/briefing/status` | 仅本机，只读 counts/coverage/warnings/summary |
| `POST /dashboard/briefing/generate` | 仅本机；普通生成或经确认的 `refresh=true` |

情报日程属于 PK-140 的 qq-control 边界。Node sidecar 读取 `GET /api/v1/qq-control/schedules/daily-briefing`，预生成显式调用 `POST /api/v1/briefing/generate`，发送只读 `GET /api/v1/briefing/today`；不得直接解析缓存 JSON，也不得在发送阶段通过 query 参数触发采集。`/dashboard/briefing/schedule` 继续兼容并委托同一 qq-control service/repository。

生成/刷新响应额外返回瞬时 `refresh_status/refresh_message`。持久化事务失败时：回滚成功返回 HTTP 500“已恢复提交前缓存”；回滚本身失败则返回“缓存状态无法确认，请先执行只读检查”，不能无条件承诺旧缓存未变。

## 隔离验证

核心测试是 `server/tests/test_daily_briefing_module.py`：只使用 fake gateway、fake PK-200、fake PK-210、固定 aware 时钟和系统临时目录。`test_daily_briefing_summary_cache.py` 也只使用临时 root。七项来源分别由 `test_intel_sources_registry.py`、`test_x_monitor.py`、`test_bilibili_collector.py`/`test_bilibili_feature.py`、`test_youtube_collector.py`、`test_github_intel_collector.py`、`test_papers_collectors.py`、`test_rss_intel_collector.py` 使用 MockTransport/fake/临时目录验证；`test_papers_http_runtime.py` 额外验证 legacy/Collector 并发共享、最小间隔、429 冷却、取消/失败恢复、单次关闭与单向导入；`test_intel_sources_integration.py` 验证八 source ID 顺序、失败隔离、关闭和版本化 registry API。`test_intel.py` 与 `test_daily_briefing_voice.py` 是真实来源/运行中 API 手工工具，不属于自动回归。
