# PK-110 — 每日情报核心、缓存与 Kei 播报

- 状态：待集成
- 优先级：P1
- 所属模块：`daily_briefing`
- 依赖任务：PK-001、PK-010、PK-100、PK-200
- 负责路径：`server/core/intel_contracts/`、`server/features/daily_briefing/`、`server/services/daily_briefing.py` 兼容接缝、`server/intel/briefing.py` 的 legacy gateway、情报汇总/缓存/播报稿接口及隔离测试
- 当前对话：2026-07-30，PK-011 可安装化增量已完成并置“待集成”；`core/intel_contracts` 与 Collector `1.0` 已冻结，等待 PK-000/PK-900 合并共享装配和官方 Catalog

## 入场授权（2026-07-22）

- 依赖确认：PK-001、PK-200 已完成，PK-110 的实现依赖已满足，可以进入独立功能开发。
- 授权范围仅限 Collector 公共契约、规范化、汇总、去重、缓存、缺失来源补采、Kei 改写和当天播报稿；不得借本任务重构任何具体来源 Collector 或来源配置。
- `LegacyCollectorGateway` 是现有采集实现进入新核心的唯一兼容接缝；后续来源任务只需实现本任务冻结的 Collector 协议，不得反向依赖 PK-110 内部实现。
- PK-110 必须交付带明确版本与兼容规则的 `CollectorResult`、`IntelItem` 冻结契约；`CollectRequest` 作为调用输入契约一并稳定，供后续来源任务并行实现。
- Kei 改写只调用 PK-200 的受控生成接口，不直接构造或依赖 `LLMEngine`。语音合成只调用已完成的 PK-210 公共接口；PK-110 只拥有情报文本和当天播报稿，不拥有音频、Voice Pack 或 TTS 生命周期。
- 本轮不创建、领取或实施 PK-115、PK-120、PK-130、PK-131、PK-132、PK-133、PK-134 等来源任务。

## 阶段约束

- 本任务先于各来源模块实施，并负责冻结后续任务共同依赖的 `CollectRequest`、`CollectorResult` 与 `IntelItem` 契约。
- PK-115、PK-120、PK-130、PK-131、PK-132、PK-133、PK-134 已于 2026-07-22 获得并行实施授权；各任务仍保持“待开始”，由各自独立功能对话领取后再改为“进行中”。
- 当前 X、GitHub、B 站、YouTube、RSS、arXiv、Crossref 和 Semantic Scholar 继续通过 `LegacyCollectorGateway` 适配；PK-110 不重写这些来源的采集、节流、鉴权、资料缓存或配置规则。

## Collector 1.0 正式冻结（2026-07-22）

- `CollectRequest`、`CollectorResult`、`IntelItem`、`SourceCoverage` 及公共 source ID `twitter/github/bilibili/youtube/money/arxiv/crossref/semantic` 按 `docs/architecture/daily-briefing.md` 正式冻结。
- 同一 major 内允许增加可忽略的未知字段；缺少必填字段或破坏字段语义属于不兼容变更。任何破坏性修改必须交回 PK-000 决策并提升 major，来源任务不得自行改变公共协议。
- 正式授权 PK-115、PK-120、PK-130、PK-131、PK-132、PK-133、PK-134 分别在自己的路径和数据边界内并行实施；它们只实现冻结后的 Collector 协议，不反向依赖 PK-110 的 service/repository/router 内部实现。

## 目标

让采集结果规范化、汇总、去重、缓存、缺失来源补采、Kei 改写和当天播报稿形成独立的 models/contracts/gateway/service/repository/router 边界。后续来源模块只实现冻结后的 Collector 契约，不需要读取 PK-110 内部实现。

## 模块边界

- 拥有：Collector 公共协议、规范化条目、多来源失败隔离、覆盖状态、去重排序、当天缓存、补采冷却、显式刷新、Kei 总结及当天播报稿。
- 不拥有：关注对象配置、X/B 站资料缓存、各平台鉴权与限流、YouTube/GitHub/论文/RSS 解析、QQ 定时器、LLM client 或具体 TTS client。
- Kei 改写必须通过 PK-200 的受控文本生成接口；普通缓存读取不得触发 LLM。
- 语音播报兼容入口只把当天播报稿交给 PK-210 公共语音契约；音频文件、Voice Pack、TTS Provider 和临时文件清理由 PK-210 所有。PK-210 是已冻结的外部公共契约，不扩大 PK-110 的代码所有权。
- PK-140 只能通过 PK-110 的公开 service/API 复用当天缓存，不直接解析缓存 JSON。

## Collector 契约基线

- `CollectRequest` 至少表达本机日期、时区、source IDs、刷新意图、lookback 与只读来源配置快照。
- `CollectorResult` 至少表达 `source_id`、规范化条目、warnings、coverage、fetched_at、retry_after 与 cache_status。
- `IntelItem` 至少表达稳定 ID、source ID、分类、标题、摘要、URL、作者、发布时间、采集时间与可 JSON 序列化的脱敏 metadata。
- 冻结交付必须明确 Schema/协议版本、必填与可选字段、未知字段兼容策略、时间与 URL 表示、稳定 ID 生成规则以及序列化示例；冻结后如需破坏性修改，必须返回 PK-000 重新决策。
- 公共 source ID 至少覆盖 `twitter`、`github`、`bilibili`、`youtube`、`money`、`arxiv`、`crossref`、`semantic`。
- “来源失败”“来源未配置”“成功但当天无内容”必须是不同状态；单来源失败不能阻断其他来源。
- 论文可统一进入展示层的 `papers` 区，但不得丢失 arXiv、Crossref、Semantic Scholar 的真实 source ID、coverage 或 warning。
- 外部条目一律视为不可信文本；进入 PK-200 前必须限制长度，并避免将其中的指令当作系统指令。

## 接口契约

- 当前接口：`/briefing/today`、`/briefing/today/voice`、`/dashboard/briefing/*`
- 目标命名空间：`/api/v1/briefing`
- 消费所有来源的规范化 `CollectorResult`，不直接拥有其配置或平台客户端。
- 版本化接口需覆盖当天结果读取、显式生成/刷新和当天 Kei 播报稿；精确路径在实现前写入工作记录并保持 legacy 接口兼容。
- 普通读取、打开控制台或 QQ 缓存查询不得触发 Collector、PK-200 或 PK-210；外部副作用只能来自显式生成、刷新、缺失来源补采或播报请求。

## 数据所有权

- `server/data/briefing_cache/` 与当天 Kei 播报稿缓存。
- 现有真实缓存属于本机运行状态，开发和自动测试不得读取、打印、删除、迁移或覆盖；测试必须注入临时 root 和固定时钟。
- 缓存不得保存 Cookie、Token、API Key、Authorization header、完整上游错误体或个人来源配置快照。

## 验收标准

- 正常读取当天缓存不触发 Collector、LLM 或 TTS；来源配置保存不隐式采集。
- 刷新、缺失来源补采、跨天清理和 QQ 缓存复用保持现有语义；QQ 消费者只通过 PK-110 公开 service/API 读取当天结果。
- 显式 `refresh`、按来源补采、失败冷却、补采合并与去重保持可观察且不会重复已有数据。
- 主缓存和 `kei_summary_today.json` 使用明确日期/Schema 与原子写入；损坏、跨天和写入失败均安全降级，不破坏旧缓存。
- 同一天 Kei 总结默认复用，只有显式 rewrite refresh 才重新调用 PK-200；失败或空回复明确回退原始摘要而不伪装生成成功。
- 新旧 API、控制台、QQ 缓存消费者和语音兼容入口保持一致；TTS 缺失时明确返回文字降级。
- 所有自动测试使用 fake Collector、fake conversation、fake voice、临时缓存和固定时间，不访问真实来源、真实 LLM、TTS、QQ 或个人配置。
- 最终架构文档给出足以让后续来源任务独立实施的冻结契约、版本和兼容策略。
- 冻结契约至少可由 `twitter`、`github`、`bilibili`、`youtube`、`money`、`arxiv`、`crossref`、`semantic` 八类 source ID 的假 Collector 独立验证。

## 不在本任务内

- 修改 `server/intel/collectors/twitter.py`、`bilibili.py`、`youtube.py`、`github.py`、`arxiv.py`、`papers.py`、`money_tips.py` 的平台规则。
- 修改个人关注名单的增删改、资料头像缓存或来源配置 UI；这些归 PK-115 和对应来源任务。
- 调用真实采集、付费 LLM、真实 TTS、QQ 消息，或读取真实缓存与个人来源配置。
- 提前实施、领取或完成 PK-115、PK-120、PK-130、PK-131、PK-132、PK-133、PK-134。

## 工作记录

- 2026-07-30：完成 PK-011 生产装配审计退回：`PK210BriefingVoiceProvider` 已重构为 PK-110 自有的纯 structural adapter 并纳入安装包，不再静态 import `features.voice` 的 contracts/models/storage。宿主精确接缝为：优先的高层 `app.state.daily_briefing_voice_provider`（实例或同步 factory）；否则从当前 `app.state.voice_service` 结构化读取 `tts/voice_packs/artifacts`，并允许显式覆盖 `app.state.voice_tts_provider`、`voice_pack_resolver_binding`、`voice_artifact_store`、`voice_synthesis_request_factory`。Core 不 import daily briefing，PK-110 也不读取 PK-210/PK-212 状态文件或实现类型。
- 2026-07-30：结构化适配器在每次显式播报开始时一次性捕获 TTS、VoicePack resolver、Artifact store 和可选 request factory；voice 后加载/替换在下一请求生效，卸载移除 `voice_service` 后稳定返回 `voice_unavailable + text_only`，请求中途替换不跨能力集混用。合成、解析 Pack、发布或 factory 异常统一为有限 `voice_failed`，不返回异常正文；普通缓存读取仍不解析 voice seam。永久 fake 测试覆盖缺失、后加载、卸载、异常脱敏、高层 Provider 后注入/解除及并发替换，全程未调用真实 TTS 或写入真实音频。
- 2026-07-30：daily briefing release 提升为 patch 版本 `1.0.1`，tag `module-daily-briefing-v1.0.1`、asset `daily-briefing-1.0.1.zip`；确定性构建包含 `backend/voice_adapter.py`，大小 `123725` 字节，package SHA-256 `7dfce6cad4d2bbfac7cbf38d5499ad3f28303b82619b4311287e115947e439e1`，manifest SHA-256 `80621a452885aaf3793e98d4cea869da7935a78952cbc92348132103739af9da`。ZIP 仅在系统临时目录重建校验后删除，未进入仓库。
- 2026-07-30：本轮最终验证通过 `test_daily_briefing_installable.py`、PK-110 core/cache/generation tests、voice adapter 既有 fake、官方 release 重建校验、PK-140 全部 83 项 fake sidecar、compileall、动态面板语法、文档门禁及 `git diff --check`。共享 `test_conversation_consumers.py` 与 `test_feature_catalog.py` 在当前并行装配状态分别因冻结 `api.py` 已无 `conversation_service` 属性、尚无 `/api/v1/calendar/today` 路由而失败，均位于 PK-000/其他模块共享 composition，不是本次 PK-110 适配器行为；未越界修改。
- 2026-07-30：修复 PK-000 全量拓扑审计发现的 optional voice 注册时序问题。`daily_briefing.module.register()` 不再把注册瞬间的 Provider/`None` 固化进 service，而是注入 app-scoped lazy resolver；只有显式播报请求才读取当前 `app.state.daily_briefing_voice_provider`，同步 factory 的异常、无效 Provider 和畸形返回均映射为固定 `voice_unavailable/voice_failed + text_only`，不返回异常或 Provider 错误正文。每个请求只捕获一次 Provider，后装、替换、解除在下一请求生效，并发中的旧请求继续使用自身已捕获实例。未 import PK-210/PK-212 内部实现，未改变普通缓存读取、文本生成、Collector `1.0` 或 HTTP 字段。
- 2026-07-30：永久 fake 回归覆盖 briefing 先注册且无 voice、同一 service 后注入 fake voice、解除后降级、factory 抛错、畸形结果脱敏及两个并发请求跨 Provider 替换隔离；PK-110 installable/core/cache/generation、PK-200 consumers、Catalog 和 PK-140 全部 83 项 fake sidecar 测试通过。`test_daily_briefing_voice.py` 是面向运行中 API 的手工脚本，本轮按隔离规则未执行；没有生成真实音频。
- 2026-07-30：完成 PK-011 可安装化增量。Collector `1.0` 的稳定类型、协议、时间与净化契约已迁入 `server/core/intel_contracts/`，并以专项目录 README 冻结依赖方向、兼容策略和导出面；`features.daily_briefing.models/collector_contracts/time_utils` 保留对象身份相同的兼容 re-export。X、B 站、YouTube、GitHub、论文、RSS、来源配置及 legacy collectors 的生产 import 已切换为只依赖 Core，依赖防护确认来源模块不再反向 import daily briefing 内部实现。
- 2026-07-30：冻结导出包括 `CollectRequest`、`CollectorResult`、`IntelItem`、`SourceCoverage`、`CacheStatus`、`CoverageStatus`、`Collector`、`CollectorGateway`、`ObservableCollectorGateway`、`CollectorProgressCallback`、`CollectorRegistry`、八个 public source ID 常量，以及 `normalize_source_ids/normalize_url/sanitize_external_text/json_safe_mapping/stable_item_id/aware_timestamp/rfc3339/get_timezone/localize/ensure_compatible_contract/is_valid_source_id`。契约版本仍为 `1.0`，同 major 忽略未知对象字段，不兼容 major 或缺少必填字段安全拒绝；已明确通知 PK-115 可依赖该冻结面，其他来源任务沿用同一边界。
- 2026-07-30：新增 `daily_briefing@1.0.0` 确定性安装包。manifest 使用 `backend.register`，数据命名空间为 `daily_briefing`，保留 `/api/v1/briefing` 与四个 legacy endpoint；来源包 `intel_sources/x_monitor/bilibili/youtube/github_intel/papers/rss_intel` 及 `conversation/voice` 均为 optional dependencies。安装包仅含每日情报 backend allowlist、manifest 和动态面板，不含来源实现、名单、真实缓存、凭据、模型、音频、虚拟环境或 vendor。
- 2026-07-30：安装 composition 使用进程内 `CollectorRegistry` 的逐次快照，缺少来源稳定返回 `not_configured`，单来源异常隔离，其他来源继续生成；缺少 conversation 时返回真实 `fallback` 的确定性播报文本，缺少 voice 时返回文本降级。可选能力只从 `app.state.daily_briefing_text_generator_provider`、`daily_briefing_voice_provider`、`intel_collector_registry` 和受控 clock/root/config/loopback seam 注入；daily briefing 不创建定时器、不拥有来源 Provider，也不复制 PK-140 规则。
- 2026-07-30：动态面板仅调用当天只读、生成、刷新和 generation-status 公共接口；普通加载零 Collector/PK-200/PK-210/写入，轮询有界且在完成、失败或 unmount 后停止，不使用 localStorage/sessionStorage。安装后须显式启用并重启；停用/卸载后重启不注册路由、Provider 或定时器，卸载保留模块数据，重装可读取原缓存且不触发 Collector。
- 2026-07-30：初版 `1.0.0` release 输入已由后续 `1.0.1` structural voice adapter 补丁取代；测试继续从源码重建并逐项核对，仓库不保存 ZIP。
- 2026-07-30：PK-011 隔离验证通过 Core 类型身份与生产依赖扫描、确定性双构建/release 哈希、ModuleManager 安装/启用/停用/卸载/重装、缺失来源、单源异常脱敏、缓存 GET 零网络、conversation/voice 降级、缓存保留，以及 PK-110 核心事务/summary/生成进度、PK-115 registry、PK-119 composition、X/B 站/YouTube/GitHub/论文/RSS consumers、PK-010 installable lifecycle、Catalog、PK-200 consumers、Python compileall 和动态面板 `node --check`。全部使用 fake Collector、固定时钟、临时目录及 ASGITransport；未读取或打包真实缓存、来源名单、`.env`、凭据、个人状态，未调用真实采集、LLM、TTS 或 QQ。额外的 PK-120 installable 回归因其专属 release 固定值与当前产物不一致而失败，已作为外部并行任务问题保留，未越界修改。
- 2026-07-30：修复来源总时限生效后“顶部显示本轮失败、来源详情仍只有旧缓存原因”的可观测性缺口。`BriefingGenerationTracker` 新增八个固定 source ID 的 `source_error_codes`，只从 Collector 规范化 warning 中提取白名单括号码，未知码和虚构秘密丢弃；不保存 warning/detail/异常正文。控制台将其显示为“本次运行”，并把原 coverage/warning/retry_after 明确改标为“缓存说明/缓存诊断码/缓存记录的可再次尝试”。因此失败 refresh 可以继续保持旧缓存字节不变，同时照实显示本次 `timeout（请求超时）`。Python/Node 定向回归覆盖有限码、未知码脱敏、partial-success 文案和轮询；隔离浏览器预览实测 X 卡片同时显示本次 timeout 与缓存诊断。PK-110 核心/summary、dashboard/catalog、PK-200/PK-210 consumers 和 PK-140 全部 83 项 sidecar 回归通过；未调用真实来源、LLM、TTS 或 QQ。
- 2026-07-30：根据真实控制台脱敏状态定位单来源刷新长期停在 `0/1`：X Collector 会按目标串行执行 30 秒请求及有限重试，而 PK-110 gateway 原先没有来源级总时限，实际运行超过 22 分钟仍为 `running/collecting`。整改后 `ContractCollectorGateway` 对每个独立平台来源施加 120 秒总时限，`ProjectCollectorGateway` 对论文选择集也施加同样有界等待；到期取消 Collector，规范化为 `failed + collector timed out + timeout`，其他来源不受阻断。父调用取消时 gateway 同时取消尚未结束的子任务，避免脱离请求继续运行。控制台单来源请求等待改为 180 秒并明确提示最长约 2 分钟。临时目录/fake 回归验证平台与论文超时、取消、完成顺序、单源失败隔离，以及超时刷新返回 `failed_using_cache` 且旧主缓存字节不变；PK-110 核心/summary、PK-119 composition、PK-200/PK-210 consumers、dashboard/catalog、PK-140 全部 83 项 sidecar 回归均通过。未读取当天缓存正文、来源名单或凭证，未发起真实采集、LLM、TTS 或 QQ。
- 2026-07-30：用户实机复核证明上一条 120 秒来源总时限会误杀串行多目标来源：B 站 12 个 UID 在约 119.995 秒被 gateway 取消，只能得到通用 `timeout`，X 的 17 个目标也无法在单实例慢响应时完成。现撤销 `ContractCollectorGateway` 与论文 composition 的固定总时限，保留父调用取消传播、来源异常隔离，以及具体 Collector 自有的单次请求超时、有限重试、节流和冷却；fake 慢来源回归确认超过旧阈值概念后任务仍在运行，释放后正常返回。单来源浏览器等待调整为 35 分钟并取消“最长约 2 分钟”的错误承诺。按用户要求不在 dashboard 增加黑框、不恢复逐项 stdout；原生 PowerShell 只读轮询现有 generation-status 即可观察阶段、耗时、来源状态和有限错误码，且不输出账号、正文、URL 或凭据。
- 2026-07-30：撤销总时限后的隔离验证通过 `test_daily_briefing_generation_status.py`、`test_intel_sources_integration.py`、`test_daily_briefing_module.py`、`test_daily_briefing_summary_cache.py`、`test_conversation_consumers.py`、`test_dashboard_briefing_progress.mjs`、`test_dashboard_shell.py` 与 `test_feature_catalog.py`；相关 Python 编译和 23 项文档门禁通过。测试只使用 fake Collector、固定时钟、临时缓存、ASGI/MockTransport；未触发真实来源、LLM、TTS 或 QQ，也未读取真实 briefing cache、来源名单或凭据。
- 2026-07-30：逐来源强制刷新增量完成隔离验收。`test_daily_briefing_module.py` 验证单来源成功只替换自身、其他来源条目与 coverage 保留，单来源失败返回 `failed_using_cache` 且主缓存旧字节不变；版本化 ASGI 契约验证请求只含一个 source ID。控制台预览 fixture 展开来源详情后实测八个 public source ID 均显示“强制刷新此来源”，未点击按钮、未访问真实上游。相关 PK-110/来源/PK-200/PK-210/dashboard/catalog 回归、PK-140 全部 83 项 sidecar 测试、Python 编译、11 项 dashboard JavaScript 语法、23 项文档门禁和 `git diff --check` 均通过。未读取或改写真实缓存、来源名单、`.env`、profile、QQ/runtime 状态，未调用真实采集、LLM、TTS 或 QQ。
- 2026-07-30：新增来源详情逐项“强制刷新此来源”。按钮对八个 public source ID 使用同一版本化 `POST /api/v1/briefing/refresh`，请求只含单个 `source_id` 且 `rewrite/rewrite_refresh/patch_missing=false`；操作前明确确认会立即访问对应上游，执行期间禁用全部单来源按钮并复用 generation-status，20 分钟有界超时，完成后重新只读加载缓存。未新增 sidecar 规则或外部持久状态。
- 2026-07-30：修复通用 refresh 的子集事务语义。此前 `refresh=true + source_ids=[one]` 会跳过旧缓存并用单来源结果重建主文档，存在删除其他来源的风险；现在有当天缓存时统一在旧文档上按来源合并，单来源成功只替换自身，失败返回 `failed_using_cache` 并保持主缓存旧字节，其他来源 items/coverage/warnings 不变。B 站旧 warning 清理同时识别 `Bilibili ` 与 `Bilibili:` 前缀，避免单来源刷新后遗留重复诊断。新增 service 与 ASGI 回归验证单来源请求、其他来源保留、失败旧字节保留和 HTTP 响应仍含未请求来源。
- 2026-07-30：用户授权补齐来源详细错误。保持 Collector `1.0` 字段不变，在既有脱敏 `warnings` 上增加兼容的有限码约定：X/Nitter 将 HTTP、超时、传输、XML/响应异常映射为有限码；B 站 Collector 保留 `BilibiliClientError.code` 并跨失败冷却保留该码；RSS Collector 保留 `FeedFetchError.code`，并把 401/403、404、429、5xx 分别映射为 `access_denied/not_found/rate_limited/upstream_unavailable`。所有来源只按码返回受影响数量，不返回账号、UID、Feed URL、异常正文或响应体，未知码降级为通用有限码；重试、冷却、coverage、条目与缓存规则未改变。
- 2026-07-30：控制台来源详情支持同一来源多个诊断码，并显示有限中文解释，例如 `anti_bot（触发平台风控）`、`rate_limited（请求过于频繁）`、`timeout（请求超时）`；现有当天旧缓存不会凭空补码，必须等对应来源下一次显式采集/补采后才会写入新 warning。定向 fake/MockTransport 回归覆盖 X 的 timeout/rate_limited/parse_error/upstream_unavailable、B 站 anti_bot/upstream_unavailable 及冷却保码、RSS parse_error/timeout/redirect_rejected/rate_limited，并验证虚构响应正文不进入结果。
- 2026-07-30：诊断码增量通过 X/B 站/RSS 三项来源测试、PK-119 source composition、两项既有 PK-110 缓存/模块测试、generation-status、dashboard、catalog、PK-200/PK-210 consumers、PK-140 全部 83 项 sidecar 测试、Python 编译、JavaScript 语法、23 项文档门禁和 `git diff --check`。全部使用 MockTransport、fake service 或临时目录；未触发真实采集、LLM、TTS 或 QQ，未读取真实缓存正文、来源名单、环境文件或凭证。
- 2026-07-30：根据控制台实测修正缺失来源补采的进度工作集。原 tracker 在整批 `start()` 后虽然 service 只采集 `patch_ids`，但 `collecting()` 未替换八来源选择集，导致只补采 `money/semantic` 时结束仍显示 `2/8`、其余来源“等待”。现在 collector 调用前以实际工作集重置计数和来源状态，补采完成显示 `2/2`，未参与来源为 `not_requested` 且不展示；总体成功但本轮有 failed/partial 时显示“处理完成（部分来源失败）”，不再写“生成成功”。
- 2026-07-30：只读复查当次当天响应的净化诊断字段：Semantic Scholar 提供了有限码 `rate_limited`；X、B 站和 RSS 仅提供通用失败说明、warning/retry_after，没有来源诊断码。未读取条目正文、真实来源名单、环境文件或凭证，也未启动采集。控制台新增默认收起的“来源状态与错误详情”“今日论文”“Kei 今日播报总结”；详情照实展示现有净化字段，没有诊断码时明确写“来源未提供（仅有通用失败）”，不修改具体 Collector 规则。
- 2026-07-30：新增 patch workset 与 dashboard partial-success 文案回归，并扩展 dashboard shell 契约检查三组 native details、安全 `textContent` 渲染及缺码提示；本机视觉复核使用只读 preview fixture，确认三组默认收起且来源/论文可独立展开，未触发真实 Collector、PK-200、PK-210 或 QQ。
- 2026-07-30：完成“每日情报生成进度可观测性”增量并交 PK-900 复验。Collector `1.0` 的 `CollectRequest/CollectorResult/IntelItem/Collector` 字段和语义保持冻结不变；新增的 `ObservableCollectorGateway.collect_with_progress` 只是 PK-110 gateway 可选能力，旧 gateway/fake 继续只实现 `collect()`。生产平台 Collector 按并发完成顺序回报，论文 coordinator 返回后仍以 `arxiv/crossref/semantic` 三个真实来源回报。
- 2026-07-30：新增进程内 `BriefingGenerationTracker`。公开状态只含 `idle/running/succeeded/failed`、`idle/collecting/rewriting/saving/finished`、aware 时间/有界 elapsed、八个固定 public source ID 的有限状态、完成计数和 `cancelled/cache_save_failed/generation_failed` 有限错误码；不新增持久文件，不保存或返回条目正文、标题、摘要、URL、账号、来源配置、warning/detail、异常正文、prompt、路径、headers 或凭证。mutation lock 保持原串行语义，线程锁与单调 token 阻止旧 run 覆盖新 run。
- 2026-07-30：新增本机只读 `GET /api/v1/briefing/generation-status`；legacy `/dashboard/briefing/status` 的 `generation` 字段委托同一 tracker。两者均零 Collector、零 PK-200、零 PK-210、零缓存写入。控制台今日情报区显示采集/改写/保存和来源进度；撤销误杀多目标来源的 120 秒总时限后，1 秒轮询上限同步调整为 2160 次，完成/失败/页面卸载即停止；刷新页面若发现 `running` 会恢复显示，不使用 localStorage/sessionStorage 保存业务状态。
- 2026-07-30：隔离验证使用 fixed clock、fake/observable Collector、fake PK-200、临时 repository 与 ASGITransport，覆盖并发来源完成顺序、单源失败隔离、collect/rewrite/save、保存总体失败、取消、旧 run 防覆盖、缓存复用零采集、状态 GET 零副作用与脱敏，以及本轮 patch workset `2/2`。通过 `test_daily_briefing_generation_status.py`、`test_dashboard_briefing_progress.mjs`、两项既有 PK-110 测试、PK-119 source composition、PK-200/PK-210 consumers、PK-140 全部 83 项 sidecar 测试、dashboard、catalog、Python 编译、全部 11 项 dashboard JavaScript 语法、23 项文档门禁和 `git diff --check`。未读取/改写真实缓存、来源名单、`.env`、profile、QQ/runtime 状态，未调用真实采集、LLM、TTS 或 QQ。
- 2026-07-22：PK-000 完成整改后的最终独立复验。重新审查 refresh 旧缓存保底、repository 两文件暂存/提交/回滚与 router 的条件化持久化错误承诺；重放 gateway 全失败、主缓存替换失败、summary 替换失败三项固定时钟/临时 root/fake 场景，旧 items/text/script 与两份文件字节均保持，旧播报稿继续可见且无临时文件残留。两项 PK-110 定向测试和五项共享回归全部退出 0；受保护真实缓存、来源名单、环境文件和 profile 的定向 Git 状态为空。结论为通过，PK-110 与本轮 PK-900 改为“已完成”，Collector `1.0` 正式冻结并授权下游来源任务独立领取。
- 2026-07-22：领取 PK-000 最终复核退回整改。本轮仅处理 refresh 的旧缓存保底、主缓存/播报稿共同提交或可靠回滚、HTTP 持久化承诺及三项临时目录回归；Collector `1.0` 暂不冻结，下游来源任务不启动。
- 2026-07-22：刷新事务整改完成。refresh 现在始终先加载旧版本作为保底；gateway 异常或全部请求结果均无成功 empty/带条目 complete|partial 状态时，直接返回旧 items/text/script，不改两份缓存、不调用 PK-200，并公开 `refresh_status=failed_using_cache` 与“刷新失败，继续使用旧缓存”。成功刷新先在内存完成规范化和播报稿，再由 repository 同时暂存主缓存/summary；任一替换失败按提交前字节恢复两份文件并通过 `cache_state_preserved` 告知 router 回滚结果。
- 2026-07-22：HTTP 不再无条件声明“旧缓存保持不变”。确认回滚成功时返回“已恢复提交前缓存”；若回滚也失败则明确“缓存状态无法确认，请先执行只读检查”。新增临时目录回归覆盖 gateway 刷新异常、主缓存替换失败、summary 替换失败，逐项断言旧 items/text/script、两份旧字节、可见旧播报稿与无遗留临时文件。
- 2026-07-22：PK-000 最终独立复核未接受本轮 PK-900“通过”结论。临时缓存夹具证明：已有 `old-item` 可用缓存时，显式 `refresh=true` 遇到 gateway/Collector 异常会写入 `failed/0 items` 并覆盖旧主缓存；主缓存替换成功后若 `kei_summary_today.json` 原子替换失败，会留下新主缓存、旧 summary 字节和不可见播报稿的半提交状态。单个主缓存 `os.replace` 失败仍能保留旧字节并清理临时文件。整改归 PK-110 service/repository/router，不能扩大到具体 Collector。
- 2026-07-22：PK-900 首轮验收退回三项阻断，PK-110 暂时恢复“进行中”：失败补采改变 coverage/warning 后旧播报稿未同步失效；公共 Collector warning、coverage detail 与 URL query 缺少统一凭证脱敏；legacy 论文异常在 gateway 清洗前输出原始异常正文。本轮仅修复上述 PK-110 边界并补充临时缓存/虚构秘密回归，不扩大到具体 Collector 或下游任务。
- 2026-07-22：首轮整改完成。播报稿 `source_digest` 现在覆盖 items、原始 text、coverage 与 warnings；补采后任一事实状态变化都会清空内存旧稿，显式 rewrite 重新调用 fake/受控 PK-200，不请求 rewrite 时也会把明确 fallback 写入独立 summary cache，因此成功响应与立即重读的 script/status 一致。旧摘要算法生成的同日播报稿只会安全失效，不改写历史主缓存。
- 2026-07-22：Collector `1.0` 候选模型新增并公开统一 `sanitize_external_text/normalize_url/json_safe_mapping`。stable ID、title/summary/author、warning、coverage detail、metadata 字符串值和旧 summary 文本都在公共边界有限脱敏；秘密键/headers 删除，异常或未知对象仅保留类型名；URL 删除敏感 query 参数并清洗保留参数值。该规则同时覆盖缓存、HTTP 响应与 PK-200 prompt，不要求未来 Collector 依赖 legacy 私有清洗。
- 2026-07-22：`server/intel/briefing.py` legacy gather 的来源异常日志/警告不再拼接异常正文，Semantic Scholar 失败不再输出或缓存关注作者；只保留来源、有限失败状态、数量和异常类型。未修改 `server/intel/collectors/*`。新增主动夹具分别验证失败补采响应/重读一致、虚构 warning/coverage/metadata/title/summary/URL query 凭证不进入临时缓存/响应/prompt，以及虚构论文异常正文不进入 stdout/warning。
- 2026-07-22：独立 PK-110 对话完成领取并将任务置为“进行中”。本对话只建立 `daily_briefing` 的 Collector 公共契约、legacy gateway、条目规范化、多来源失败隔离、覆盖状态、去重排序与数量限制、当天缓存、缺失来源补采冷却、强制刷新、PK-200 Kei 改写、当天播报稿缓存、版本化/legacy 稳定读取接口及隔离测试。明确不修改 `server/intel/collectors/*`、来源配置所有权、QQ 定时器、PK-200/PK-210 内部实现、真实缓存或个人来源配置；不调用真实采集、LLM、TTS 或 QQ。当前工作区包含 conversation、voice、calendar、focus、dashboard、来源配置、Collector 与用户状态等既有混合修改，全部视为用户所有；本任务不清理、不覆盖、不暂存。
- 2026-07-22：实现 Collector `1.0` 候选契约。`CollectRequest` 固定 `local_date/timezone/source_ids/refresh/lookback/source_config_snapshot`；`IntelItem` 固定 stable/source/category/title/summary/url/author/published/fetched/metadata；`CollectorResult` 固定 items/warnings/coverage/fetched/retry/cache。时间一律为带时区 RFC 3339，metadata 只允许有界 JSON 并移除 secrets/headers；同 major 忽略未知字段，未知但格式合法的 source ID 形成单源 `not_configured`，不能阻断汇总。公共 ID 为 `twitter/github/bilibili/youtube/money/arxiv/crossref/semantic`，其中普通和信息差 X 共属 twitter；论文合并到 papers 时以 `discovery_sources` 保留真实发现来源。该候选仅在 PK-900/PK-000 最终复核后正式冻结。
- 2026-07-22：建立 `models/collector_contracts/collector_gateway/repository/prompt_builder/service/router/legacy_adapter/voice_adapter` 分层。当前八类来源全部经 `LegacyCollectorGateway` 按 source ID 隔离调用 `gather_all_intel`；来源配置只在显式生成/刷新/到期补采开始时读取一次快照，`server/intel/collectors/*` 未修改。非论文来源可并发，三个论文 legacy 适配因现有全局 arXiv failure tracker 串行；单来源异常转换为有限 warning、coverage 和 retry_after。
- 2026-07-22：版本化接口冻结为只读 `GET /api/v1/briefing/today`、显式 `POST /api/v1/briefing/generate`、强制 `POST /api/v1/briefing/refresh`、只读 `GET /api/v1/briefing/today/script`。保留 `GET /briefing/today`、`POST /briefing/today/voice`、`GET /dashboard/briefing/status`、`POST /dashboard/briefing/generate`；所有入口委托同一 core/facade。legacy GET 默认改为 `fetch=false`，定时预生成仍显式传 `fetch=true`；控制台状态、普通 GET 和 QQ `fetch=false&rewrite=true` 都只读缓存。
- 2026-07-22：主缓存 `schema_version=1` 只保存规范化条目、原始摘要、coverage/warnings/retry/patch attempts；当天 Kei 播报稿独立保存到 `kei_summary_today.json` 并带内容摘要、generated/fallback。两类文件使用唯一临时文件、`flush/fsync/os.replace`；写入失败保留旧文件。损坏、未知 Schema、日期错误安全 miss，旧无 Schema 缓存只读适配、不就地迁移；所有测试仅写系统临时目录，未读取或改写真实缓存。
- 2026-07-22：去重覆盖 stable ID、相同 URL、平台 ID、同来源标题大小写/空白、缺 URL 与论文 DOI/标题跨来源；不同来源仅内容相似不会误删。论文合并 stable ID 与 Collector 顺序无关；未来时间和 lookback 外条目排除，缺发布时间稳定后排，最后按 section limit 截断。补采只选择 failed/partial 且已过 retry_after/冷却的来源；成功按来源替换/合并再去重，失败保留旧内容并更新 warning/coverage。
- 2026-07-22：Kei 改写只调用 PK-200 `TextGenerator`。prompt 将有限字段放入 `UNTRUSTED_DAILY_BRIEFING_DATA` 并明确忽略外部文本中的指令/角色扮演/系统提示；metadata、秘密、headers、内部路径和完整错误体不进入 prompt。成功/异常/超时/空回复分别记录真实 generated/fallback；同日普通读取不重复调用，只有 `rewrite_refresh=true` 重写。
- 2026-07-22：legacy voice 通过 `PK210BriefingVoiceProvider` 只依赖 PK-210 的 `TextToSpeechProvider`、`VoicePackResolver`、`VoiceArtifactStore`，不引用具体 `TTSClient`。音频只发布到 PK-210 受控输出并返回同源 URL，不进入 briefing 缓存；Provider 缺失/失败保留文本并返回 `text_only/degraded/errors`。PK-140 代码和消息格式未修改，现有 bridge 继续只经 legacy API 读当天缓存。
- 数据/外部副作用：主缓存和播报稿仅在显式生成/刷新/到期补采或改写时写入；来源配置快照不落盘到 briefing cache。Collector 网络只在显式生成/刷新/到期补采，PK-200 只在显式 rewrite，PK-210 只在 voice POST；普通读为零外部副作用。自动测试没有访问真实来源、LLM、TTS、QQ、个人来源名单、真实缓存、`.env` 值或音频资产。
- 2026-07-22：隔离验证通过：`test_daily_briefing_module.py`、`test_daily_briefing_summary_cache.py`、`test_intel_source_config.py`、`test_conversation_consumers.py`、`test_voice_module.py`、`test_feature_catalog.py`、`test_dashboard_shell.py`；后者同时执行控制台内联 JavaScript/Node 语法检查。新增模块、兼容接缝、API、catalog 与测试文件通过 `py_compile`，`git diff --check` 无空白错误，新增文件尾随空白扫描无匹配。按安全约束未运行可能真实联网的 `test_intel.py` 与 `test_daily_briefing_voice.py`。
- 2026-07-22：首轮整改后再次完整运行上述两项 PK-110 定向测试及五项共享回归，全部通过；`test_daily_briefing_module.py` 已内含 PK-900 三项阻断的固定时钟、临时 root、fake Collector/PK-200 与虚构秘密复现。Python 编译复验通过；文档门禁与最终差异检查在恢复“待集成”后重跑。
- 2026-07-22：刷新事务整改后完整重跑两项 PK-110 定向测试及五项共享回归，全部通过；新增固定时钟/临时 root 回归分别证明 gateway 全失败时两份旧缓存字节不变且零重复 PK-200、主缓存替换失败回滚两份旧字节并清理临时文件、summary 替换失败回滚新主缓存且旧播报稿仍可见。相关模块与测试再次通过 `py_compile`；Collector `1.0` 保持候选，等待 PK-900/PK-000 原夹具复验。
- 遗留/后续项：服务进程需在部署时重启才会加载新 router/catalog。PK-115/120/130/131/132/133/134 已获准由独立功能对话并行领取，PK-140 仍按自身任务边界后续推进；本任务未实现或领取这些下游来源/QQ 任务，也未执行真实来源、真实模型、真实语音或端到端 QQ 验证。

## PK-011 生命周期整改（2026-07-31）

- `daily_briefing@1.0.2` 现公开幂等 `unregister(app)`，按身份清理本实例路由/service；
  仅当模块自建且 registry 仍为空、仍绑定原对象时删除 registry。注册中途失败不会
  留下路由、service 或 registry 半状态。

## 完成文档门禁

- [x] TASK_RECORD — 已记录实际模块边界、Collector `1.0` 契约、API、缓存/外部副作用、验证与遗留集成项。
- [x] TASKS_BOARD — `TASKS.md` 中 PK-110 已按本轮增量恢复为“待集成”，等待 PK-900 复验；PK-900 保持“进行中”，名称、优先级与依赖不变。
- [x] PUBLIC_README — `README.md` 已记录用户可见能力、新旧接口、只读/刷新语义、缓存影响、重启要求、测试和安全限制。
- [x] MODULE_CATALOG — `server/features/catalog/service.py` 已登记模块映射、接口、进程边界、网络条件、失败策略和迁移状态。
- [x] ARCHITECTURE_DOCS — `docs/architecture/daily-briefing.md` 已记录正式冻结的 Collector `1.0` 契约、兼容规则和下游授权，并已更新模块化单体架构索引。
- [x] LOCAL_README — 不适用；本任务未新增仅本机路径、启动器、解释器、端口或环境位置。
- [x] AGENT_RULES — 不适用；本任务遵循既有工作流、安全、验证、文档和 Git 规则，未改变 agent 规则。
- [x] VALIDATION — 本轮增量测试、两项既有 PK-110 测试、PK-119/PK-200/PK-210 consumers、PK-140 83 项 sidecar 回归、dashboard、catalog、Python 编译、全部 dashboard JavaScript 语法、21 项文档门禁与 `git diff --check` 均通过；未运行被明确禁止的真实集成测试。

## PK-011 可安装化文档门禁（2026-07-30）

- [x] TASK_RECORD — 已记录 Core 冻结导出、依赖方向、manifest、Provider 接缝、包内容、数据/网络副作用、生命周期、release 输入、验证与外部阻断。
- [x] TASKS_BOARD — 总控已在共享 `TASKS.md` 将 PK-110 置“进行中”；本轮明确禁止修改该共享文件，专属任务记录完成后置“待集成”，由 PK-000/PK-900 执行共享状态合并。
- [x] PUBLIC_README — 共享 `README.md` 冻结，本轮没有修改；面向集成方的安装、启停、数据和降级语义记录在本任务与专属 release README。
- [x] MODULE_CATALOG — 官方 Catalog 与 Catalog service 冻结，本轮没有修改；已生成可由 PK-000/PK-010 合并的 `official-release-fragment.json` 和逐字节校验的 `official-catalog-entry.json`。
- [x] ARCHITECTURE_DOCS — 共享架构文档冻结，本轮没有修改；新增 `server/core/intel_contracts/README.md` 作为 Collector `1.0` 专项只读架构边界。
- [x] LOCAL_README — 专属 `release/README.md` 已记录确定性构建命令、Release 参数、数据保留、可选依赖及禁止打包内容；没有新增本机端口、解释器或秘密配置。
- [x] AGENT_RULES — 不适用；未改变 agent 工作流、安全、验证或 Git 规则。
- [x] VALIDATION — PK-011 专属测试、PK-110 核心测试、来源 consumer/安装包回归、PK-010 lifecycle、Catalog/PK-200 consumer、compileall、JavaScript 语法与 `git diff --check` 均按最终记录执行；真实来源、模型、语音、QQ 和个人状态始终隔离。

## 独立对话启动提示

```text
领取 PK-110 每日情报核心、缓存与 Kei 播报任务。读取本任务、PK-200、PK-210
和架构规范，只处理 Collector 公共契约、legacy gateway、规范化、汇总、缓存、
补采冷却、Kei 改写和播报稿。所有测试使用 fake provider 与临时缓存；不得修改
任何具体来源 Collector、个人来源配置、真实缓存或外部服务。完成后提交“待集成”
并等待 PK-900/PK-000 决定是否冻结契约；不得提前启动下游来源任务或执行 Git 发布。
```
