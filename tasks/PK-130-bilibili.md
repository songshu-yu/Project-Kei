# PK-130 — B 站资料与动态采集

- 状态：待集成
- 优先级：P1
- 所属模块：`bilibili`
- 依赖任务：PK-001、PK-010、PK-100、PK-110、PK-115
- 负责路径：`server/services/bilibili_profile_cache.py`、`server/intel/collectors/bilibili.py`、`server/features/bilibili/**`、新建 `server/tests/test_bilibili_*.py`、本任务文件
- 当前对话：2026-07-22 由 PK-000 批量登记并授权并行情报来源批次
- 累计增量：2026-07-28 用户实机确认上游参数会失效；新增本机参数维护、候选验证与显式恢复采集，完成后交回 PK-000/新一轮 PK-900
- 并行阶段交接状态：共享集成待排队；不得自行修改 `TASKS.md`

## 并行批次授权（2026-07-22）

- 共同依赖为 `docs/architecture/daily-briefing.md` 已冻结的 Collector `1.0`；需要改变契约时立即停止并交回 PK-000。
- 并行阶段只修改上述负责路径。API、legacy briefing、旧控制台、catalog、README、架构文档及来源注册表均留到总控串行窗口或 PK-115。
- 真实 B 站资料缓存、UID 名单、Cookie 与网络不用于自动测试；PK-140 不属于本批。

## 目标

独立管理 UID 资料缓存、公开动态采集、节流和反爬失败表达。

## 阶段约束

- PK-110 已通过最终复核，Collector `1.0` 已冻结，本任务已由 PK-000 统一领取。
- 与 PK-115、PK-120、PK-131～PK-134 是同一后续并行批次；只实现 B 站适配，不修改 PK-110 内部汇总或其他来源。

## 接口契约

- 当前接口：`/dashboard/intel-sources/bilibili-profiles/resolve`
- 目标命名空间：`/api/v1/bilibili`
- 向每日情报模块提供规范化动态及明确的缺失来源状态。

## 数据所有权

- `server/data/bilibili_profiles.json`

## 验收标准

- 不把 Cookie 当作永久方案；保留节流、有限重试和失败冷却。
- 昵称头像查询不隐式触发视频采集。

## 并行阶段工作记录（2026-07-22）

### 实际导出与行为

- `server/intel/collectors/bilibili.py` 导出 `BilibiliCollector`：固定 `source_id="bilibili"`，直接实现冻结的 `Collector.collect(CollectRequest) -> CollectorResult`，仅导入 PK-110 的 `collector_contracts/models`，未导入 gateway、service、repository 或 router。配置只读 `source_config_snapshot.bilibili_uids`；未请求或无 UID 返回 `not_configured`，成功有条目/成功无条目/部分失败/全部失败分别返回 `complete/empty/partial/failed`。
- Collector 将空间动态规范化为 `IntelItem(category="video")`，稳定 ID 优先使用 dynamic ID，保留 `uid/dynamic_id/dynamic_type` 脱敏 metadata、昵称、带时区发布时间和规范 URL。AV、opus、article、common、直播推荐及纯文字/图片动态使用同一有界解析，不调用视频列表接口。
- `BilibiliPublicClient.fetch_profile(uid)` 与 `fetch_space_dynamics(uid)` 是两个独立 HTTP 操作；UID 间请求通过实例锁串行节流，反爬 `HTTP 412`、API `-352/-412`、429、5xx、超时和传输失败最多总计两次尝试，上游正文不进入异常、warning 或 CollectorResult。默认真实调用可使用现有已配置 Cookie，但 Cookie 不是成功保证，也不进入配置快照、缓存、返回或日志。
- `BilibiliCollector` 对失败 UID 记录实例内 6 小时冷却；冷却期间即使 `refresh=true` 也不再次请求。单 UID 失败不丢弃其他 UID 的可用动态，`retry_after` 同步写入 result 与 coverage。`fetch_bilibili()` 保留 legacy Python 入口但已改为动态 Collector 适配，不再调用 `get_videos`；`fetch_bilibili_profile()` 保留单资料兼容入口。
- `server/services/bilibili_profile_cache.py` 保留 `resolve_bilibili_profiles()` 并新增零网络只读 `get_bilibili_profiles()`。成功资料默认复用，显式刷新只刷新成功项；失败项把 6 小时 `retry_after` 原子保存到 `server/data/bilibili_profiles.json`，冷却内显式刷新也不重试。写入使用同目录唯一临时文件、flush/fsync 与 `os.replace`；日志不包含 UID、上游正文或凭证。
- `server/features/bilibili/` 新增无导入期网络副作用的 client/models/service/router。`BilibiliService` 通过注入 `uid_provider` 消费 PK-115 所有的名单，不导入或写来源注册表；`GET /api/v1/bilibili/profiles` 只读缓存，`POST /api/v1/bilibili/profiles/resolve` 只处理当前配置 UID。router 工厂强制由装配层注入本机请求 guard，当前并行阶段未修改 `server/api.py`，因此新路由尚未装配。

### 数据与外部副作用

- 生产数据所有权仍只有 `server/data/bilibili_profiles.json`；Collector 的动态失败冷却仅在其进程内实例中，不新增第二个磁盘状态或常驻进程。
- 只有显式资料 resolve 会查询单个/当前 UID 并可能更新资料缓存；只读 profile 接口零网络零写入。只有显式 Collector/legacy gather 调用会查询空间动态；资料解析不查询动态或视频，动态解析也不查询资料或视频。
- 自动测试只使用 `httpx.MockTransport`、fake profile fetcher、固定 UTC aware 时钟、虚构 UID/响应和系统临时目录。未读取真实 UID 名单、资料缓存、Cookie、Token、API Key、`.env` 或个人状态，未发起真实 B 站请求或批量采集。

### 专属验证结果

- `server/.venv-asr/Scripts/python.exe server/tests/test_bilibili_collector.py`：通过，输出 `bilibili collector tests passed`。覆盖资料/动态路径隔离、零隐式视频请求、Cookie 缺省不发送、节流、反爬/5xx 最多两次、异常正文净化、Collector 1.0 字段与 stable ID、legacy 动态适配、未配置、部分失败隔离、6 小时冷却、profile 成功缓存/刷新/失败冷却与唯一临时文件清理。
- `server/.venv-asr/Scripts/python.exe server/tests/test_bilibili_feature.py`：通过，输出 `bilibili feature tests passed`。覆盖版本化只读/resolve、当前名单约束、本机 guard、缓存读取零网络及未配置 UID 拒绝。
- 九个 PK-130 实现/测试文件执行 `py_compile`：通过。
- `server/.venv-asr/Scripts/python.exe scripts/check_task_docs.py`：通过，输出 `task documentation gate passed: 11 gated task(s)`；PK-130 仍按并行规则保持总板“进行中”且只在本文件记录排队状态。
- `git diff --check`：退出 0；仅输出混合工作区既有 LF→CRLF 提示。PK-130 专属文本路径尾随空白扫描无匹配，Collector/feature/cache 未发现对 PK-110 gateway/service/repository/router 的禁用导入。
- 尝试运行共享 `test_intel_source_config.py` 与 `test_daily_briefing_module.py`，两者均在收集/导入阶段被同批次 PK-133 的 `server/features/papers/domain.py` 阻断：项目指定 Python 3.8 环境缺少其直接导入的标准库 `zoneinfo`；尚未执行到 PK-130 代码。PK-130 未越权修改该路径，需总控在共享集成前先恢复共享回归可运行性。

### 共享串行窗口待办

- `server/api.py`：构造单例 `BilibiliService(uid_provider=lambda: load_intel_sources()["bilibili_uids"])`，注入现有本机请求 guard 并挂载 `create_bilibili_router()`；旧 `/dashboard/intel-sources/bilibili-profiles/resolve` 改为委托同一 service，保持原 query/响应兼容。Collector 应复用单例，以便进程内失败冷却跨采集请求生效。
- `server/intel/briefing.py`：现有 `fetch_bilibili(...)` 导入不需要字段改动，其实现已返回空间动态 legacy shape；串行验收需确认 gather 的 warning/coverage 仍由 PK-110 legacy gateway 隔离。若总控选择直接注册 `BilibiliCollector`，只在共享装配处引用公开 class，不改变 Collector 1.0。
- `server/features/catalog/service.py`：登记 `bilibili`、`/api/v1/bilibili/profiles`、`/api/v1/bilibili/profiles/resolve`、legacy profile endpoint、主 API in-process、本地资料缓存所有权、显式网络副作用、partial/failed/cooldown 失败语义及模块化状态。
- `server/static/dashboard.html`：现有 legacy 资料按钮可继续工作，本任务不要求并行修改 DOM；串行窗口若切到版本化 endpoint，必须保持现有元素 ID、单 UID 刷新和“不生成情报”语义。
- `README.md`/架构说明：记录 B 站来源现在采集空间动态而非只采视频列表、资料/动态操作分离、默认节流、最多一次重试、6 小时失败冷却、Cookie 非永久方案、新版本化资料接口、部署后重启 API，以及测试全部使用 fake HTTP/临时目录。`docs/architecture/daily-briefing.md` 只能追加非破坏性实现说明，不能改冻结字段或语义。
- 串行集成前先解决上述 PK-133/Python 3.8 共享回归导入阻断，再运行 PK-130 两项专属测试、PK-115/PK-110 共享回归、catalog/dashboard 检查、文档门禁与 `git diff --check`。

### 公共契约结论

- 不存在 Collector 1.0 公共契约变更需求。当前 `CollectRequest.source_config_snapshot.bilibili_uids`、公共 source ID `bilibili`、`IntelItem`、`CollectorResult`、coverage、cache status 与 retry_after 已足够表达本实现。
- 当前唯一跨任务阻断是 PK-133 新代码与项目 Python 3.8 的导入兼容性，不是 Collector 契约问题；PK-130 保持“共享集成待排队”，不修改 `TASKS.md`，等待 PK-000 指定串行窗口。

## 独立对话启动提示

```text
仅在 PK-110 已完成且 Collector 契约冻结后领取 PK-130。遵守 AGENTS.md 的
Cookie 安全规则，只处理 B 站资料缓存、动态 Collector、节流和失败表达；不做
真实批量采集，不修改 PK-110 汇总或 PK-115 来源注册表。
```

## PK-119 事后复核与共享收口（2026-07-22）

- 复核确认资料 resolve 与空间动态采集保持分离，`BilibiliService`/router 和 `BilibiliCollector` 共用既有公开边界；生产 API 已装配 `/api/v1/bilibili/profiles*`，legacy 资料入口委托同一 service。
- 控制台资料按钮已切到版本化 resolve；`BilibiliCollector` 已注册到统一生产 gateway 的 `bilibili` source。打开面板或读取缓存不采集动态，Cookie 仍只来自既有运行环境且不进入结果、日志或配置。
- 原记录中的 `list[str]` Python 3.8 阻断在实际代码中已修复；`test_bilibili_collector.py`、`test_bilibili_feature.py`、PK-119 集成及共享回归均通过。
- catalog、README 与架构文档已同步。真实 UID、资料缓存、Cookie 和上游正文未读取或纳入差异；遗留仅为 PK-900 独立验收、部署重启及上游反爬可用性。

## 完成文档门禁

- [x] TASK_RECORD — 已按实际代码补记接口、缓存/网络副作用、生产装配、验证与遗留。
- [x] TASKS_BOARD — PK-130 已由 PK-000 统一登记为“待集成”。
- [x] PUBLIC_README — 已登记 B 站资料与空间动态能力。
- [x] MODULE_CATALOG — 已登记 `bilibili` 的版本化/legacy 接口和失败边界。
- [x] ARCHITECTURE_DOCS — 已登记 `bilibili` 生产 Collector 与资料服务边界。
- [x] LOCAL_README — 不适用；未改变本机路径、端口或解释器约定。
- [x] AGENT_RULES — 不适用；未改变长期 agent 规则。
- [x] VALIDATION — 两项专属测试、PK-119 集成及共享回归通过；最终差异检查由 PK-119 记录。

## PK-000 最终复核（2026-07-22）

PK-900 报告及实际单目标失败隔离、profile 响应/cache 脱敏、只读零网络与 Origin 回归经独立复核通过；PK-130 置为“已完成”。

## PK-900 逆向退回整改（2026-07-22）

- Bilibili profile 的 `name` 在公开响应与原子 cache 前使用公共 `sanitize_external_text()`，`avatar_url` 先补全协议相对 URL，再使用公共 `normalize_url()` 移除 userinfo、fragment、敏感 query 及 query 值中的凭证形态内容。
- 既有 cache 每次读取也经过同一 normalization，因此无需读取、迁移或原地扫描真实 cache；后续成功写入仅保存净化后的公开字段。dashboard 显示层继续对 nickname/avatar URL 做 HTML 转义。
- `test_bilibili_collector.py` 使用临时 cache、虚构 Authorization/Bearer 名称和 token query，验证 API 结果与磁盘 JSON 均不含虚构秘密，同时保留无害 query；没有读取真实 UID、cache、Cookie 或上游响应。
- dashboard 打开和 UID 增改删只读 B profile cache，只有显式“刷新资料”联网。PK-130 保持“待集成”，等待 PK-900 独立复验。

## 2026-07-28 累计增量：参数维护与失效恢复

### 目标与最小 allowlist

本轮不创建新任务编号。根据当前 `BilibiliPublicClient`、`BilibiliCollector` 和既有 dashboard 就绪判断重建实际输入边界，只接受以下三项本人浏览器会话 Cookie；三项均为必填敏感字段：

| API 字段 | 浏览器 Cookie 名 | 用途 | 必填 |
|---|---|---|---|
| `sessdata` | `SESSDATA` | 本人登录会话标识，随资料与空间动态 GET 请求发送 | 是 |
| `bili_jct` | `bili_jct` | 与同一会话配套的 CSRF Cookie | 是 |
| `buvid3` | `buvid3` | 本人浏览器设备 Cookie，降低上游拒绝概率 | 是 |

不接受整段 Cookie/Header、任意 Header 名、Authorization、脚本、JSON、浏览器文件路径或自动登录输入。控制台只指导用户从本人已登录的 B 站页面打开浏览器开发者工具，在 Application/Storage → Cookies → `https://www.bilibili.com` 中逐项复制；不自动读取浏览器、磁盘或其他用户会话。

### 接口矩阵

版本化与 legacy 路径均委托同一个 `BilibiliService`、`BilibiliCredentialRepository` 和 Collector 规则：

| 版本化接口 | legacy 兼容接口 | 网络 | 行为 |
|---|---|---|---|
| `GET /api/v1/bilibili/credentials/status` | `GET /dashboard/intel-sources/bilibili-credentials/status` | 零 | 只返回 `missing/configured/invalid`、active/candidate 状态、脱敏尾部和时间戳 |
| `PUT /api/v1/bilibili/credentials` | `PUT /dashboard/intel-sources/bilibili-credentials` | 零 | 校验 allowlist 后仅原子保存 candidate，不激活、不改 `.env` |
| `POST /api/v1/bilibili/credentials/validate-and-collect` | `POST /dashboard/intel-sources/bilibili-credentials/validate-and-collect` | 显式 | 用 candidate（无 candidate 时用 active）查询当前 UID 的资料并调用现有 `BilibiliCollector` 采集空间动态；成功才切换 active |
| `GET /api/v1/bilibili/profiles` | 既有只读入口 | 零 | 只读公开资料缓存 |
| `POST /api/v1/bilibili/profiles/resolve` | `POST /dashboard/intel-sources/bilibili-profiles/resolve` | 显式 | 保留单资料刷新，不隐式采集动态或视频 |

所有路由继续要求本机客户端与受信同源 Origin。请求模型拒绝 allowlist 外字段。上游正文、异常正文和输入值不进入 HTTP detail、warning、日志或 CollectorResult。

### 数据所有权与秘密边界

- `server/data/bilibili_credentials.local.json`：PK-130 新增的最小本机 secret store，已在 `.gitignore` 精确登记；Schema 只含 `active/candidate/environment_status`。写入使用同目录唯一临时文件、flush、fsync、尽力限制文件权限和 `os.replace`，失败清理临时文件并保留原字节。
- `active` 是 Collector 实际使用值；`candidate` 是尚未验证的新值。保存 candidate 不破坏 active。候选资料和动态均成功后才原子提升；失败只更新固定安全错误码。旧环境变量仍作为未建立本机 active 时的兼容只读来源，控制台不会读取或回填完整值，也不会改写 `.env`。
- `server/data/bilibili_profiles.json` 仍只保存净化后的昵称、头像和安全元数据。验证阶段先把资料保留在内存；动态 Collector 成功后才原子合并成功资料，失败 UID 不覆盖旧资料。
- B 站动态没有 PK-130 独立磁盘缓存；显式操作返回本次 Collector coverage/count，并使之后的 PK-110 正常 generate/refresh 立即使用新 active。PK-110 的当天主缓存、播报稿及失败事务仍由 PK-110 独占，本接口不导入其 gateway/service/repository/router，也不直接覆写今日缓存；因此验证失败时旧动态/今日情报字节天然保持不变。
- 完整敏感值不进入关注名单、资料缓存、daily briefing、README、catalog、DOM 状态、console 或错误提示。状态字段只显示是否配置、最多四位脱敏尾部、更新时间、验证时间和固定错误码。

### 控制台交互

- B 站 UP 主折叠栏目内新增独立“B 站采集参数维护”，明确三项参数、必填性、用途和本人浏览器合法获取路径。
- 参数维护区使用本轮用户提供的“托着下巴思考” Kei 图片作为 42px 本地静态头像，采用紧凑列表式标题层级：主标题、单行辅助文案、右侧安全状态胶囊与折叠箭头；该区域自身使用嵌套 `<details>`，可在 B 站 UP 主栏目内单独展开或收起，不影响 UID 列表及其他来源栏目。图片另有 HTML 固定尺寸并为 `shell.css` 增加版本参数，避免浏览器旧 CSS 缓存把 300px 原图直接展示。
- 三项均为 `type=password`、`autocomplete=off`；页面刷新和状态 GET 不回填完整值。保存请求发出前即清空输入，失败也不在 DOM 保留候选。
- 页面加载、展开栏目、读取资料/动态缓存、读取参数状态和“仅保存候选参数”均不访问 B 站。只有用户点击“验证并重新采集”或既有单 UID“刷新资料”才联网。
- UI 稳定覆盖未配置、已配置、已失效、验证中、采集成功、采集失败；失败提示只使用本地固定正文，并允许重新填写、保存后再次验证。

### 原子性、并发与失败恢复

- `BilibiliService` 使用单一 async mutation lock 串行候选保存和验证采集；repository 另用进程内锁保护同一文件的读改写。并发“采集 + 保存”会先完成一个完整事务，再留下明确 active/candidate，不出现半 JSON。
- 验证失败不提升 candidate；旧 active 和资料缓存不变。active 失败只把安全状态标记为 `invalid`，不删除原值或覆盖缓存，用户保存新 candidate 后可恢复。
- secret store 替换失败时旧文件字节不变且无临时文件残留。资料 cache 写失败依靠既有原子替换保留旧缓存；凭据验证结果与 cache 更新状态分别公开，不伪装缓存已写成功。
- Collector 继续保持请求节流、总计最多两次尝试、单 UID 六小时冷却、partial/failed 隔离和脱敏 warning。资料解析仍只访问 profile endpoint，不触发动态或视频采集。

### 累计验收记录

- `server/.venv-asr/Scripts/python.exe tests/test_bilibili_collector.py`：通过。
- `server/.venv-asr/Scripts/python.exe tests/test_bilibili_feature.py`：通过。
- `server/.venv-asr/Scripts/python.exe tests/test_bilibili_credentials.py`：通过；覆盖 status/页面/候选保存零上游请求、显式按钮才访问 MockTransport、三字段 allowlist、完整值不回显、legacy/versioned 同 service、本机/Origin guard、失败候选保留旧 active/旧 profile、失效后更新恢复、原子 replace 失败、并发保存/采集、临时根外零写入，以及思考头像 PNG 和参数区独立 `<details>` 标记。
- 2026-07-28 紧凑布局复验：头像在 HTML/CSS 双重固定为桌面 42px、窄屏 36px；标题、辅助说明、安全状态胶囊和折叠箭头均有静态契约断言。`tests/test_bilibili_credentials.py`、`tests/test_dashboard_shell.py`、dashboard 内联 module 语法、25 项任务文档门禁及 `git diff --check` 均通过。尝试用内置浏览器打开无服务的 `data:` 静态预览时被 URL 安全策略拒绝，已关闭标签页且未改用绕行方案；未启动 API 或发生 B 站请求。
- `server/.venv-asr/Scripts/python.exe tests/test_intel_sources_integration.py`、`tests/test_daily_briefing_module.py`、`tests/test_intel_source_config.py`、`tests/test_feature_catalog.py`、`tests/test_dashboard_shell.py`：全部通过；确认生产 Collector 注册、来源失败隔离、版本化/legacy guard、PK-110 缓存事务、catalog 与混合 dashboard 未回归。
- `server/.venv-asr/Scripts/python.exe -m py_compile ...`：PK-130 实现与三项测试通过；`scripts/check_task_docs.py` 通过，输出 `task documentation gate passed: 25 gated task(s)`。
- 根 `scripts/python.ps1` 的 `py_compile` 通过。运行 FastAPI 测试时该脚本当前优先选择缺少 FastAPI 的根 `.venv`，因此按 `README.local.md` 指定的 `server/.venv-asr/Scripts/python.exe` 执行正式测试；该解释器选择偏差不改本轮业务结论。
- 自动测试只使用临时 secret/profile 路径、虚构 Cookie、固定时钟和 `httpx.MockTransport`。未读取、输出、diff 或修改真实 `.env`、B 站参数、UID 名单、profile、briefing cache、Cookie、Token 或个人状态，未执行真实 B 站请求。

### 公共契约与交回状态

- 不存在 Collector `1.0` 公共契约问题。`CollectRequest.source_config_snapshot.bilibili_uids`、`CollectorResult`、coverage、warning、retry/cache status 已足够；本轮只改变 PK-130 私有凭据提供器、service/router 和共享装配/UI，不引入对 PK-110 gateway/service/repository/router 的依赖。
- PK-130 保持“待集成”，交回 PK-000 安排新一轮 PK-900 对共享 API/dashboard/catalog/README、启动后凭据热切换、legacy parity 和受保护路径隔离进行独立验收；本对话不执行 Git 暂存、提交、推送、分支或 PR 操作。

### 用户后续视觉需求（待 PK-000 分配共享串行窗口）

- 用户希望把 B 站参数区的“角色头像 + 标题/副标题 + 安全状态 + 独立展开”结构推广到 QQ 启动及其他功能卡片，并把 QQ 等主功能头像提高到约 56–64px；这属于共享 dashboard 组件化与 PK-140 控制台接缝，不在 PK-130 专属路径所有权内。
- 建议全局提供 `云朵白 / 月夜蓝 / 樱花粉` 三档主题选择，主题值只写浏览器 `localStorage`，页面加载时零 API、零业务网络；颜色全部由语义 CSS 变量驱动，保留足够文字对比度、键盘焦点、减少动画偏好和移动端响应式。
- 推荐模块卡片头部统一为：角色头像、模块名称、单行用途说明、安全状态胶囊、主要动作、折叠箭头。QQ 当前公共接口只有显式“启动”而没有“停止”，因此在公共契约扩展前继续使用动作按钮，不得以双向开关误导用户；已有生命维持和每日推送 `enabled` 字段才可使用真正的开关。
- 视觉方向参考通用 dashboard 的紧凑卡片、清晰信息层级和亮暗主题机制，并以低饱和粉紫、天蓝、奶白色和有限角色插图加入二次元气质；避免整页高亮霓虹、过大人物图或用装饰抢占主要操作。
- 当前混合工作区的 `server/static/dashboard.html`、`server/static/dashboard/shell.css` 与 PK-140 路径均已有其他任务修改。PK-000 应先指定共享 UI 所有者和串行窗口，再实施全局主题、通用模块头部、QQ 卡片迁移及对应 dashboard/QQ 回归；本轮未修改这些新增范围。

## 2026-07-30 实机故障整改：WBI 与快速失败

- 只读复查确认旧 client 直接调用 `/x/space/wbi/acc/info?mid=...`，没有按 B 站当前资料接口要求取得公开 WBI key 并生成 `wts/w_rid`。匿名 nav 仍能提供 `data.wbi_img`，但无签名资料请求返回有限拒绝码；使用标准 WBI 签名后，当前本机会话仍被上游拒绝，说明“调用迁移缺签名”和“本机会话已失效/被风控”是两个同时存在的问题。
- `BilibiliPublicClient` 现在从 `/x/web-interface/nav` 取得公开 key，接受匿名 nav 的 `-101 + data` 形态，在 client 内有界缓存 mixin key，并为 profile 请求动态生成签名。签名参数不持久化、不回显、不记录；nav/profile 的响应正文仍只映射为有限错误码。
- `BilibiliService.validate_and_collect()` 把 `anti_bot`、`rate_limited`、`timeout`、`upstream_failed/rejected/unavailable` 和 `wbi_key_unavailable` 识别为共享会话/网络失败。首个 UID 完成 client 自身最多两次尝试后立即停止，不再对全部 UID 重复相同等待；`not_found`、非法/缺失资料等单目标问题仍隔离统计。
- MockTransport 回归覆盖匿名 nav key、固定时钟签名字段、WBI key 复用、Cookie provider 热切换、三 UID 遇全局反爬时只执行一次 profile 的有限重试且不进入动态采集、旧 active/profile 保持，以及上游秘密正文不进入异常或状态。
- 验证：`test_bilibili_collector.py`、`test_bilibili_credentials.py`、`test_bilibili_feature.py` 与相关集成回归通过；Python 编译、任务文档门禁和 `git diff --check` 通过。测试未读取真实 UID、Cookie、profile/briefing cache 或 `.env`，未调用真实上游。
- 当前实机会话需要用户从本人已登录浏览器重新保存三项候选参数后显式验证；代码修复不能把已过期或被风控的会话恢复为有效。PK-130 保持“待集成”，交 PK-900 复验。

## 2026-07-30 PK-011 可安装化累计增量

### 确定性包与导出

- `server/features/bilibili/package_source/manifest.json` 声明非必装
  `in_process` 模块 `bilibili@1.0.0`，只要求 `intel_sources`，把
  `daily_briefing` 列为可选依赖；版本化命名空间仅为
  `/api/v1/bilibili`，并精确声明已有四个 legacy 兼容路径。
- 包入口导出 `backend.register(app)`；动态面板导出
  `dashboard/index.js` 的 `mount(context)` / `unmount()`。面板只使用
  manifest 已声明的 B 站版本化接口，不直接读取来源名单或其他模块状态。
- `server/features/bilibili/package_builder.py` 只从显式 allowlist 物化
  `manifest.json`、`dashboard/index.js` 和八个 `backend/*.py`，固定文件顺序、
  ZIP 时间戳、权限位与 UTF-8/LF。相同输入连续构建字节与 SHA-256 一致。
- 包内 Collector、模型与净化函数直接依赖冻结的
  `core.intel_contracts`；构建时只把 PK-130 自有 client、凭据仓库、service、
  router、Collector 和 profile cache 转为包内相对导入，不导入
  PK-110 gateway/service/repository/router，也不导入开发树的
  `intel.collectors` 或 `services.bilibili_profile_cache`。
- `server/features/bilibili/release/official-release-fragment.json` 是串行
  official catalog 的 release 输入，资产名为 `bilibili-1.0.0.zip`，
  `data_policy=preserve_on_uninstall`；本轮不修改共享 catalog 或发布工作流。

### 动态面板、秘密边界与联网边界

- 动态面板紧凑展示本机 profile cache 和凭据安全状态，并提供独立可收起的
  参数维护区。缓存资料只用本地文字头像，不把远程 avatar URL 赋给图片元素，
  因此普通挂载不会由浏览器额外访问 B 站 CDN。三个公开字段仍严格为
  `sessdata`、`bili_jct`、`buvid3`，
  全部使用 password 输入，不写 DOM 持久状态、`localStorage`、
  `sessionStorage` 或 console，提交结束后立即清空。
- `mount()` 只请求本机 credentials status 与 profile cache；保存 candidate
  只执行本机原子写入。只有用户明确点击“验证并重新采集”才调用
  `POST /api/v1/bilibili/credentials/validate-and-collect` 并使用 B 站网络。
- 面板只渲染安全状态、最多四位脱敏尾部和时间戳；失败提示为本地固定文字，
  不展示请求值、上游错误正文或异常对象。包、release、测试夹具和任务记录均
  不含真实凭据、UID 名单、profile/cache、briefing cache 或个人状态。
- 凭据与 profile 继续位于宿主提供的固定 `server/data` 根，并精确使用历史
  文件名 `bilibili_credentials.local.json` 与 `bilibili_profiles.json`；
  卸载只移除程序并保留两个文件，重装后从原 store 恢复。包不包含 `.env`、
  state/data、脚本、模型、vendor 或 `node_modules`。

### Provider 接缝与失败原子性

- 冻结 Core 已提供 `CollectorRegistry`，但共享装配尚未提供正式的
  `app.state` Provider。包入口当前明确要求宿主串行接线以下四项：
  `intel_source_registry_provider()`、`intel_collector_registry_provider()`、
  `bilibili_data_root_provider()` 和 `bilibili_local_request_guard`。
  测试专用的 `bilibili_client_factory_provider` 与
  `bilibili_now_provider` 仅用于 fake client / 固定时钟注入。
- `register(app)` 在修改 app 前验证全部必需 Provider、公开方法、Core
  registry 类型和全部目标路由冲突；路由挂载中途失败时撤销新增路由并注销
  Collector。重复调用同一已加载入口幂等，缺 Provider、重复路由或注入失败
  均不留下半注册状态，也不创建数据目录。
- 共享 `server/api.py` 仍持有当前 `intel_source_registry` 单例但没有暴露上述
  Provider。此项是明确的串行集成接线需求；本轮按冻结规则不修改 API/Core，
  也没有回退导入共享 singleton。
- 为兼容 Python 3.8 同步加载及测试/重启使用多个 event loop，
  `BilibiliService`、`BilibiliPublicClient` 和 `BilibiliCollector` 的 async
  lock 改为首次异步操作时按当前 running loop 懒创建，不在模块注册阶段隐式
  创建或绑定已关闭 loop。

### 专属验证

- `test_bilibili_installable_module.py`：通过（最近一次 3.00 秒）。覆盖两次确定性构建、
  精确 10 文件 allowlist、release 元数据、危险路径/秘密/开发树导入扫描、
  Provider 缺失、既有重复路由拒绝、路由挂载失败回滚、
  安装→启用→停用→卸载→重装、数据保留、重复 register、普通 GET/保存零
  fake 网络、显式 fake 资料与动态采集、响应不回显三项虚构秘密。
- `test_bilibili_collector.py`、`test_bilibili_credentials.py`、
  `test_bilibili_feature.py`：均通过。全部使用临时目录、fake client /
  MockTransport、虚构 UID/凭据和固定时钟，没有读取或请求真实 B 站状态。
- 项目根 `.venv` 已失效，`server/.venv-asr` 启动 shim 在本机挂起；最终回归
  使用其 Python 3.8 基础解释器并显式加载现有 `.venv-asr` site-packages。
  未终止无法确认归属的既有 Python 进程，也未为测试安装或下载依赖。
- PK-130 专属路径 `git diff --check` 退出 0（仅既有 LF→CRLF 提示）；
  本轮未修改 TASKS、README、API、Catalog、Core、共享 dashboard、架构文档或
  发布工作流，未执行 Git 暂存、提交、推送、清理或 PR 操作。

### 交回结论

- Collector `1.0` 模型与协议本身无需变更；包可以仅靠冻结
  `core.intel_contracts` 完成 Collector 注册与采集。
- 仍需 PK-000 在共享串行窗口确认并提供上述四个宿主 Provider，再由新一轮
  PK-900 验收生产装配、动态面板挂载、legacy parity、重复路由与卸载重装。
  PK-130 保持“待集成 / 共享集成待排队”。

## 2026-07-30 PK-000 串行审计整改：历史数据路径兼容

- 审计确认安装包入口曾把 `bilibili_data_root_provider()` 返回目录与
  `profiles.json`、`credentials.local.json` 拼接，生产传入 `server/data`
  时会形成第二套静默数据所有权。本轮已删除这两个短文件名。
- `bilibili_data_root_provider()` 的冻结语义保持为可信宿主提供的绝对、
  规范化 `server/data` 路径；包内只拼接
  `bilibili_profiles.json` 和 `bilibili_credentials.local.json`。不扫描、
  复制、改名、迁移或回退查找其他文件，浏览器和 manifest 均不能传入路径。
- 注册前逐级检查数据根：拒绝相对路径、含 `..` 等未规范化路径、非目录、
  symbolic link 与 Windows reparse point。路径检查发生在 Collector/路由注册
  之前，失败不写文件、不创建短文件名、不留下半注册状态。
- 永久回归在临时 `server/data` 等价目录预置历史凭据和 profile，验证普通
  GET 可立即看到旧状态且零 fake 网络；保存、显式采集、卸载和重装后两个
  历史文件仍保留，并始终断言 `profiles.json` /
  `credentials.local.json` 不存在。相对路径与模拟 reparse 分支也验证为
  原子拒绝。
- 临时重建 `bilibili-1.0.0.zip` 两次，字节完全一致，共 10 项：
  - 完整大小：`91043` bytes
  - ZIP SHA-256：
    `99855bf0eb0b2480d1f687b59b96d0ccb7aaa4b3df14b9e0d27129726cf963df`
  - 包内 `manifest.json` SHA-256：
    `2ad0a3a276da917b0b44c885863407f4938d2f2dcd02be5853bb8050551a232f`
- 本轮回归：installable 通过（3.00 秒）、profile feature 通过、Collector
  通过、凭据 service/原子性/并发子集通过。完整
  `test_bilibili_credentials.py` 目前只在共享 dashboard 静态契约处失败：
  混合工作区的共享页面已不含旧
  `<details class="... bilibili-credential-panel ...">` 标记；失败未进入本次
  包数据路径逻辑。该共享文件冻结，本轮未越权修复，交 PK-000 串行 UI 所有者
  处理。
- 未读取、diff、打印或修改真实 `server/data` 文件、Cookie、Token、来源名单
  或缓存；所有新增数据均位于系统临时目录。未修改 API、Core、TASKS、
  dashboard、Catalog 或 release 工作流，未执行 Git 暂存、提交、推送或清理。
- Collector 1.0 无公共契约变更；生产仍只待 PK-000 接入已记录的可信宿主
  Provider。PK-130 保持“待集成 / 共享集成待排队”。

## 2026-08-01 可安装包依赖环修复

- 实机恢复全部官方包时，Core 激活预检稳定发现 `bilibili,daily_briefing` 循环：daily_briefing 合理地把各 Collector 作为可选依赖，而 Bilibili 包又反向把 daily_briefing 声明为可选依赖。
- 复核 Bilibili 安装包 `backend.register()` 确认它只消费 `intel_sources` 与公共 `CollectorRegistry`，不导入或调用 daily_briefing；因此移除无效反向可选依赖，不放宽 PK-010 的循环检测。
- 修复包版本提升为 `bilibili@1.0.1`，资产 `bilibili-1.0.1.zip` 为 91,687 bytes，SHA-256 `dc85eeae3787720d32edee11fd393d2720671b47de156773d389bdddf5e9637e`；release fragment 与 19 项官方 Catalog 已从同一 ZIP 重建。
- 本机通过生命周期 API 更新并启用后，17 个 in-process 模块激活图通过；Bilibili installable、官方 Catalog 与控制台专项均通过。未读取真实 Cookie、UID、资料/动态缓存或网络来源。

## 2026-08-01 控制台只读资料恢复

- 实机确认 `server/data/bilibili_profiles.json` 仍存在且未被迁移、覆盖或清空；资料面板为空的根因是 `GET /api/v1/bilibili/profiles` 和凭据状态 GET 错用了写操作 Origin/CSRF guard，控制台普通同源读取收到 403。
- Bilibili router 现拆分 `local_read_guard` 与原 `local_request_guard`：profiles/credentials status 的版本化与 legacy GET 仅要求可信 loopback peer；resolve、保存参数、验证并采集继续使用严格写 guard。没有放宽采集、Cookie 保存或网络副作用边界。
- 修复包提升为 `bilibili@1.0.2`：`bilibili-1.0.2.zip` 为 92,316 bytes，SHA-256 `623748d83a5ef0803f1bf9d4f8ff5557d3e7f4f8f9e3de26c75d4c5cc7a59349`，manifest SHA-256 `c737126beab65c3785cbfec6aa4b23bd67b59e1fbe8e4ca753361d9282a93b90`。
- 本机生命周期更新并重启 Core 后，仅按数量确认 12 个历史 profile 卡重新显示；未打印资料内容，未读取 Cookie 值，未调用 B 站网络。feature、installable、来源集成和控制台专项通过。
