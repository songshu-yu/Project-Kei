# PK-241 — 每日生活预报消费端联动

- 状态：已完成
- 优先级：P1
- 所属模块：`daily_briefing`、`qq_bridge`（只读消费端联动，不新增业务模块）
- 依赖任务：PK-110、PK-140、PK-240
- 负责路径：`server/features/daily_briefing/**` 中本任务新增的投影配置/只读呈现接缝、`server/qq_bridge/**` 中本任务新增的配置/菜单/只读查询接缝、`server/features/qq_control/router.py` 中仅限 `life_forecast_enabled` 的既有配置请求白名单与 facade 参数转发、`server/module_composition.py` 的最小只读 Provider 注入、对应 fake/临时目录测试、本任务记录及必要公开说明
- 当前对话：由 PK-000 创建并独占的 PK-241 串行实施任务；不得与 PK-110、PK-140、PK-240 的其他增量并行抢写相同文件

## 目标

在不改变 PK-240 数据、刷新和 Provider 规则的前提下，让两个既有消费端使用当天生活预报：每日情报可按本地开关选择只读展示字段；QQ 私聊的固定菜单按钮是显式刷新入口，四个精确关键词保持只读查询。两端升级后的默认状态均为关闭，不会静默改变现有每日情报或 QQ 行为。

## 不在本任务内

- 不修改 PK-240 的天气 Provider、位置配置、缓存格式、刷新流程、娱乐规则或动态面板；如现有只读契约不足，必须记录需求并交回 PK-000，不能自行扩大 PK-240。
- 不让每日情报或 QQ 读取 `server/data/modules/life_forecast/**`，也不复制天气、生活建议或运势规则。
- 不在读取、页面加载、卡片展开、菜单显示或关键词查询时触发 `POST /api/v1/life-forecast/refresh`、上游天气网络或 PK-240 缓存写入；唯一例外是用户明确点击固定 QQ“生活预报”按钮。
- 不把生活预报拼入 PK-110 已缓存的 `text/script`，不触发简报重新生成、Kei 改写、TTS、Collector 或来源补采。
- QQ 第一版不增加生活预报定时推送，不修改 daily/life/focus scheduler、at-most-once 状态、语音回复、Gateway、白名单或消息上传协议。
- 不使用“天气”等宽泛子串拦截普通对话，不增加任意 URL、城市/坐标输入、Provider 选择或危险操作；QQ 只允许固定 action 调用固定本机 refresh。
- 不修改 PK-190 日历、PK-160 记忆、个人状态、`.env` 秘密、模型、Voice Pack、`server/runtime` 或 `vendor/`。

## 串行路径所有权

本任务是本轮唯一跨模块实施所有者。允许的最小范围如下；实际不需要的文件不得顺带改动：

- PK-110：`server/features/daily_briefing/models.py`、`repository.py`、`service.py`、`router.py`、`module.py`、`package_source/dashboard/index.js`、manifest/package builder/release/README，以及相应 `server/tests/test_daily_briefing_*.py`。
- PK-140：`server/qq_bridge/configuration.py`、`.env.example`、`package_source/config.schema.json`、`src/business_menu.mjs`、必要的固定启动装配文件、动态面板、manifest/package builder/release/README，以及现有 bridge fake 测试。
- QQ control HTTP 接缝：独占授权 `server/features/qq_control/router.py`，仅允许把 `life_forecast_enabled: bool` 加入既有 `POST /api/v1/qq-control/configuration` 的严格字段校验，并原样转发给同一个现有 facade；不得新增路由、复制配置规则或修改 `server/features/qq_control/**` 的其他文件。
- 共享装配：仅在确有需要时最小修改 `server/module_composition.py`，注入只读、结构化的 today Provider；不得把 PK-240 repository、配置路径或 refresh 能力注入消费端。
- 集成回归：可新增 `server/tests/test_life_forecast_consumers.py`，并更新受版本控制的 Python 测试清单。
- 文档：本任务文件、`docs/architecture/daily-life-forecast.md` 和用户可见行为确有变化时的 `README.md`。

`TASKS.md` 继续只由 PK-000 修改。`server/api.py`、PK-240 实现路径、真实数据与运行时目录默认冻结；若实现确实需要这些路径，必须先停止并交回 PK-000。

## 接口契约

### 共同输入与显式刷新

- 每日情报和 QQ 关键词的业务输入为 `GET /api/v1/life-forecast/today` 或等价的进程内结构化只读 Provider；QQ 固定菜单按钮唯一使用 `POST /api/v1/life-forecast/refresh`。
- 消费适配器只接受 `cache_status`、`forecast`、`life_advice`、`fortune` 四个顶层字段；即使现有响应还含 `city/provider`，也必须忽略且不得转发、记录或写入消费端状态。
- 不新增专用摘要 API。若真实实现证明必须新增，只能在 `/api/v1/life-forecast` 下做向后兼容增量，并先交 PK-000 冻结。
- 当天数据缺失、跨天、损坏、结构异常或 unavailable 时必须返回稳定的空/不可用投影，不得回退旧日预报。

### 每日情报投影

- 新增本机配置接口：
  - `GET /api/v1/briefing/life-forecast-projection`：只读当前开关；无网络、无业务缓存写入。
  - `PUT /api/v1/briefing/life-forecast-projection`：只保存严格配置；沿用本机写保护，不触发 refresh 或简报生成。
- 严格请求模型为 `enabled: bool` 和 `fields: object`，`fields` 必须且只能包含以下稳定 ID，值均为布尔：
  - `weather_condition`
  - `temperature_range`
  - `apparent_temperature`
  - `precipitation_probability`
  - `wind`
  - `alerts`
  - `clothing`
  - `travel_umbrella`
  - `uv`
  - `air_quality`
  - `fortune`
- 配置文件不存在时，`enabled=false` 且十一项全部为 `false`。升级不得根据已有缓存自动开启。
- `GET /api/v1/briefing/today` 可增加一个向后兼容、仅运行时计算的 `life_forecast` 投影字段；不得修改或重写已缓存的 `text/script/items/coverage`。
- 总开关关闭时不读取 PK-240 Provider；开启时每次只捕获一次 Provider 结果，再按字段开关投影。`fortune` 只有 PK-240 返回 `fortune.enabled=true` 且每日情报 `fortune=true` 时显示，并原样保留“娱乐内容、非事实预测”。

### QQ 私聊查询

- 在既有 `GET/POST /api/v1/qq-control/configuration` 中增加非秘密布尔字段 `life_forecast_enabled`；本机 `.env` 键固定为 `QQBOT_LIFE_FORECAST_ENABLED`，缺失时为 `false`。保存继续原子写入且不得回显其他秘密。
- 私聊菜单按钮固定显示“生活预报”，action 固定为 `kei:life-forecast`。
- 只匹配四个完整关键词：`每日生活预报`、`今日生活预报`、`生活预报`、`今日天气预报`。不得用“天气”或其他宽泛包含关系命中。
- 菜单 action 与精确关键词必须共用同一格式化与脱敏边界。关闭时返回固定“生活预报尚未开启”提示且零 API；开启时 action 至多一次固定本机 refresh POST，关键词至多一次 today GET。
- refresh 响应直接格式化，不追加 today GET；失败不重试、不回退缓存，返回固定脱敏提示。同一 interaction 由既有去重器保证至多刷新一次。
- QQ 展示当天所有可用天气事实和生活建议，不复用每日情报逐项开关。娱乐内容仅在 PK-240 返回 `fortune.enabled=true` 时附加，并保留免责声明。
- QQ 只格式化、限长和清洗结构化结果；不持有位置、坐标、Provider 配置，不执行天气推导规则，不写 scheduler 或投递状态。

## 数据所有权

- 每日情报投影配置由 PK-110 消费端拥有，固定保存到 Git 忽略的 `server/data/modules/daily_briefing/life_forecast_projection.json`；只含 schema、总开关和十一项布尔值。
- 配置写入必须使用同目录唯一临时文件、flush/fsync 与原子替换；失败保留旧字节。损坏或未知 schema 必须 fail closed 为全部关闭，且普通读取不得覆盖原文件。
- QQ 总开关由 PK-140 既有配置服务拥有，保存到现有本机 `server/qq_bridge/.env` 的 `QQBOT_LIFE_FORECAST_ENABLED`；`.env.example` 只提供字段名和默认 false，不包含真实值。
- PK-240 独占 `server/data/modules/life_forecast/**`。PK-241 不得直接读取、diff、打印、迁移、清空或覆盖其中配置与缓存。
- 两个消费端不得保存城市、坐标、天气响应、运势正文或上游 attribution 的副本；只保存开关。

## 实施清单

- [x] 复核 PK-110、PK-140、PK-240 当前源码、包版本、测试和混合工作区差异。
- [x] 实现 PK-110 原子投影配置、版本化配置接口和只读 today 投影。
- [x] 实现 PK-110 控制台总开关/逐项开关，页面加载和切换零上游网络。
- [x] 实现 PK-140 默认关闭的总开关、固定 action、精确关键词和统一只读 handler。
- [x] 保持 daily briefing cache/text/script、QQ scheduler/语音/Gateway 与 PK-240 缓存契约不变。
- [x] 更新两个既有可安装包的 manifest/release 元数据并做确定性双构建；不发布。
- [x] 更新 README、专项架构和本任务实际交付记录。
- [x] 运行 fake/临时目录累计回归、文档门禁与 `git diff --check`。

## 验收标准

- 新安装或升级后，每日情报十一项和 QQ 总开关全部关闭；没有静默新增内容或网络活动。
- 每日情报逐项组合准确，字段 ID 与中文 UI 解耦；总开关关闭时 Provider 调用为零。
- 每日情报投影不改 briefing 缓存字节，不调用 generate/refresh/conversation/voice/Collector，不写 PK-240。
- QQ 菜单 action 与四个精确关键词结果等价；普通“天气不错”“聊聊天气”等进入原 conversation，零生活预报 API。
- QQ 按钮开启后只调用一次 refresh POST，四个关键词各只调用一次 today GET；关闭、跨日、损坏、unavailable 和结构异常都安全降级，刷新失败不回退缓存。
- `fortune` 在每日情报满足双开关，在 QQ 满足 PK-240 娱乐开关；两处均保留完整免责声明且不混入天气事实标签。
- 所有输出不包含城市、坐标、Provider 私有配置、秘密、路径、上游错误正文或旧日缓存。
- 原子配置保存失败保持旧状态；并发保存不产生半文件；损坏配置不会被普通 GET 自动覆盖。
- 所有自动测试只用 fake today Provider、ASGITransport/MockTransport、固定时钟和系统临时目录；不启动真实 QQ、天气、LLM、TTS、Collector 或外部服务。
- PK-110、PK-140 原有接口、控制台、QQ 白名单/去重/菜单优先级、scheduler 和安装生命周期累计回归通过。

## 工作记录

- 2026-08-19：PK-000 扫描 `TASKS.md`、全部 `tasks/` 文件及 README/架构中的 `PK-xxx` 引用。确认 PK-230、PK-240 已占用，PK-121 有历史记录；PK-241 在全仓任务/文档编号中未使用，因此正式登记本任务。
- 2026-08-19：确认 PK-240 保持“待集成”，现有 `GET /api/v1/life-forecast/today` 足以作为只读输入；当前不需要扩展 PK-240 公共接口。
- 2026-08-19：本轮总控仅登记任务、冻结边界并分配唯一串行负责人；未实现业务代码，未读取真实天气缓存、QQ `.env`、个人状态、`server/runtime` 或 `vendor/`，未执行 Git 暂存、提交、推送或清理。
- 2026-08-19：串行实施入场完成全部指定文档、当前分支、混合 Git 状态及冻结源码接缝复核。确认 PK-240 的现有 today 只读契约足够，PK-110 可在已授权路径内完成；但 QQ 配置写接口的严格字段白名单和 facade 参数装配实际位于未授予本任务所有权的 `server/features/qq_control/router.py`。该路由目前只接受并传递 `appid`、`secret`、`reply_with_voice`、`qq_media_upload_capability`，若不修改它，冻结的 `life_forecast_enabled` 无法通过既有 `POST /api/v1/qq-control/configuration` 保存；仅修改 `server/qq_bridge/configuration.py` 会形成不可验收的半接线。依照“跨出冻结路径立即停止并交回 PK-000”，本轮未修改任何业务代码、包、测试、README 或架构文件，任务保持“进行中”，八项门禁保持未完成；未读取真实天气缓存、QQ `.env`、个人状态、`server/runtime` 或 `vendor/`，未暂存、提交、推送、发布或清理。
- 2026-08-19：PK-000 独立复核 `server/features/qq_control/router.py`，确认既有 `POST /api/v1/qq-control/configuration` 在该文件中同时维护严格字段白名单与传给现有 facade 的关键字参数；不修改此接缝会使 `life_forecast_enabled` 无法保存。现正式将该单一文件授予 PK-241 串行负责人，范围严格限于新增布尔字段校验与原样转发；不授权新路由、其他 `features/qq_control` 文件或任何 PK-240 契约变更。PK-241 可继续实施，状态仍为“进行中”。
- 2026-08-19：完成 PK-110 消费投影。新增严格 `GET/PUT /api/v1/briefing/life-forecast-projection`、schema 1 原子配置与十一项稳定字段；配置缺失/损坏/未知 schema 均只读失败关闭。`GET /api/v1/briefing/today` 仅在运行时附加 `life_forecast`，总开关关闭时 Provider 调用为零，开启时每请求只捕获一次 `get_today()`，只接受 `cache_status/forecast/life_advice/fortune` 并验证本地当天；不写入 `text/script/items/coverage` 或 PK-240。
- 2026-08-19：完成 PK-140 消费查询。`QQBOT_LIFE_FORECAST_ENABLED` 缺失默认 false，沿用既有 `.env` 原子存储；经 PK-000 单文件授权，QQ control 路由仅新增布尔白名单校验与同一 facade 参数透传。主菜单新增固定“生活预报”/`kei:life-forecast`；四个完整关键词与 action 共用一个 handler，关闭零 API，开启至多一次固定本机 today GET。没有修改 scheduler、Gateway、语音、上传、刷新或 PK-240。
- 2026-08-19：数据副作用复核完成。PK-110 只保存 `server/data/modules/daily_briefing/life_forecast_projection.json` 的 schema/总开关/十一项布尔；PK-140 只保存既有 `.env` 的非秘密布尔键。读取、面板加载、菜单、action 和关键词均不触发天气上游网络、PK-240 写入、简报生成、Collector、conversation（精确命中时）、LLM、TTS 或 QQ 定时投递；输出忽略城市、坐标、Provider、署名、路径、秘密和上游错误正文。
- 2026-08-19：安装包候选更新为 `daily_briefing@1.0.3` 与 `qq_bridge@0.1.25`，release tag 均为 `modules-2026.08.19`，只更新各自候选 manifest/release 元数据，未修改共享生产 Catalog、未发布。系统临时目录双构建逐字节一致：daily 两份均 `145148` bytes / SHA-256 `25335e3c51d8d7cf690a3aaf620164de6f7a11d6ca50c17a2f9ff26689636d9f`；QQ 两份均 `172002` bytes / SHA-256 `86af63306b924ef752d6511a511b55cc5facb96c9c18c5bd86e9002a8363eb7d`。
- 2026-08-19：专属验证通过：`tests/test_life_forecast_consumers.py`、`tests/test_daily_briefing_module.py`、`tests/test_daily_briefing_generation_status.py`、`tests/test_daily_briefing_installable.py`、`tests/test_qq_control.py`；`npm test` 148/148；`unittest qq_bridge.tests.test_configuration_panel qq_bridge.tests.test_installable_package` 30/30。所有新增测试只使用 fake Provider、固定时钟、ASGITransport/本地 fake fetch 和系统临时目录。
- 2026-08-19：混合工作区累计门禁如实记录：`test_dashboard_shell.py` 在 `check_manifest_inventory` 因入场时另一个未集成 `learning` manifest 使数量超出其当前 `INSTALLABLE_MODULE_IDS` 而失败；`check_python_test_inventory.py` 仅报告另一个任务的 `test_learning_module.py` 未登记。两者不涉及 PK-241 代码，且修复需跨出冻结路径/抢写 PK-230，故留给 PK-000 集成排序；PK-241 自有新增测试已登记。未读取真实天气缓存、QQ `.env`、个人状态、`server/runtime` 内容或 `vendor`，未暂存、提交、推送、发布或清理。
- 2026-08-20：PK-900 独立验收退回一项 P1 输出清洗缺陷：`safeVisible()` 的通用 assignment 正则先把 `Authorization: Bearer value` 中的 `Bearer` 当成完整值替换，后续 Bearer 规则因 scheme 已消失而无法清除真正的 value，导致虚构 marker 残留在最终 QQ markdown；同结构 `safeMultiline()` 具有相同风险。整改严格限定在两个正则：通用 assignment 规则现在完整消费可选的 `Bearer` 前缀及其值，未重写 sanitizer、action、关键词、API、配置、scheduler、Gateway、语音或缓存契约。任务继续保持“待集成”，交回同一 PK-900 重新独立复验。
- 2026-08-20：新增永久逆向回归 `life forecast action and exact keywords redact credentials, metadata, and local paths`。测试以固定 fake today 响应分别通过 `kei:life-forecast` 和四个完整关键词产生五份最终 QQ markdown，覆盖 `Authorization: Bearer`、token、API key、cookie、secret、city、provider、attribution、Windows 路径与 Unix 路径 marker；断言五条路径等价、各自只调用一次固定 today GET，所有 marker/本机路径均不进入输出。同时原有“天气不错”“聊聊天气”继续断言进入 conversation。
- 2026-08-20：整改门禁全部通过：`node --test tests/business_menu.test.mjs` 30/30；`npm test` 149/149；`tests/test_life_forecast_consumers.py` 通过；`unittest qq_bridge.tests.test_configuration_panel qq_bridge.tests.test_installable_package` 30/30；`tests/test_qq_control.py` 8/8；`node --check` 对 `business_menu.mjs`、`bridge_core.mjs`、`index.mjs` 均通过；`py_compile` 对 PK-241 相关 Python 实现/测试均通过；`python scripts/check_task_docs.py` 通过 30 个 gated tasks；三文件 scoped `git diff --check` 通过（仅 Git 的 CRLF 提示）。测试仅使用 fake/临时数据，未读取真实 `.env`、QQ data、生活预报缓存、位置、凭据、个人状态或网络，未发送消息，未暂存、提交、推送、发布或清理。
- 2026-08-20：PK-900 完成 Bearer 脱敏整改后的独立复验并判定通过；PK-241 继续保持“待集成”。独立正式 controller 夹具确认固定 action 与四个关键词输出等价，凭据/元数据/本机路径 marker 均未进入最终 QQ markdown，宽泛天气聊天仍未被截获。复验累计结果为 business menu 30/30、Node 149/149、PK-241 2/2、daily/feature 29/29、QQ configuration/installable 30/30、qq-control 8/8，语法、编译、文档和 scoped diff 门禁均通过。因 `business_menu.mjs` 属于包源码，2026-08-19 记录的 QQ `172002` bytes / `86af...` 仅为整改前历史摘要，最终收口不得沿用；PK-900 在两个系统临时目录重建的 `qq_bridge-0.1.25.zip` 均为 `172030` bytes，SHA-256 `6212581c830c5f650db6fa0c02323bde4e035e3cb289ac4fb55ed48a29cb3f11`，manifest SHA-256 `84bc677cb965ce12009bba1158e5821cf54fa8f6db6269a5ca2802e41da69a27`，16 项且禁止项命中 0。最终 Catalog/发布记录由 PK-000 使用该新摘要收口。

- 2026-08-20：PK-000 最终独立复核通过。总控重新核对 PK-900 正式报告、两个清洗函数与永久 marker 回归，并实际重跑 `node --test tests/business_menu.test.mjs`，结果 30/30；固定 action、四个精确关键词、Bearer/token/API key/cookie/secret、位置元数据和本机路径均未泄漏，宽泛天气聊天继续进入 conversation。PK-241 正式关闭为“已完成”；PK-900 因后续 PK-100 批次仍保持“进行中”。最终 QQ 包摘要固定采用 `172030` bytes / `6212581c830c5f650db6fa0c02323bde4e035e3cb289ac4fb55ed48a29cb3f11`，不得回退到整改前摘要。

- 2026-08-20：按用户追加需求重新开启 PK-241 增量并恢复“待集成”。固定 QQ 私聊菜单 action `kei:life-forecast` 现在是唯一显式刷新入口：总开关开启后，每次有效点击只调用一次固定本机 `POST /api/v1/life-forecast/refresh`，直接格式化该响应，不追加 today GET；刷新失败不重试、不读取旧缓存，返回固定脱敏提示。同一 interaction 继续由既有去重器保证至多刷新一次。四个完整文字关键词保持原只读语义，各自只调用一次 `GET /api/v1/life-forecast/today`；菜单展示、普通聊天和宽泛“天气”文字仍不触发刷新。
- 2026-08-20：新增 fake 永久回归覆盖 action=一次 POST、四关键词=四次 GET、POST body 固定为空对象、刷新失败零 fallback，以及相同 interaction 重放仅一次 POST/一次回复。实际结果：`node --test server/qq_bridge/tests/business_menu.test.mjs` 32/32，全部 bridge `npm test` 151/151，`.venv` 下 `unittest server.tests.test_qq_control` 8/8，`server/tests/test_life_forecast_consumers.py` 通过，`node --check server/qq_bridge/src/business_menu.mjs` 通过。系统 Python 因缺 FastAPI、项目 `.venv` 因未安装 pytest 均未伪称 pytest 成功；没有安装依赖或联网补装。
- 2026-08-20：QQ 候选提升为 `qq_bridge@0.1.26` / tag `modules-2026.08.20`。两个独立系统临时目录确定性构建逐字节一致：`172429` bytes，SHA-256 `9ab9c65ab25e7c357338f4654f3d46f383bb5f34d8179aa19c703ae89c5f8ae0`，源 manifest SHA-256 `2d5e4ff59cd2684efb4c1a82c157a74c731e89b1ccddfe7f01c999814e13de2f`；ZIP 共 16 项，`.env`、`node_modules`、runtime、vendor、绝对路径命中 0。候选仅生成于系统临时目录并已清理，未安装、暂存、提交、推送或发布。
- 2026-08-20：PK-900 对本轮 QQ 显式刷新增量完成独立聚焦验收并判定通过。独立结果为 business menu 32/32、全部 Node 151/151、QQ configuration/installable 30/30；固定 action 单次 POST refresh、四个关键词单次 GET today、宽泛聊天与菜单加载零 refresh、失败零重试/零旧缓存回退、interaction 去重和敏感字段清洗均符合冻结契约；独立双构建、16 项白名单与禁止项扫描也与上述摘要一致。PK-000 据此完成最终复核并将 PK-241 标记为“已完成”；PK-900 因其他批次继续保持“进行中”。

## 完成文档门禁

任务进入“待集成”或“已完成”前必须全部勾选；不适用项也必须写明原因。

- [x] TASK_RECORD — 已记录最终接口、数据副作用、验证和遗留问题。
- [x] TASKS_BOARD — 不适用：依授权未修改 `TASKS.md`，由 PK-000 集成时同步状态。
- [x] PUBLIC_README — 已同步用户可见开关、QQ 查询、默认关闭和限制。
- [x] MODULE_CATALOG — 已核对并更新 PK-110/PK-140 候选包版本、可选依赖与 release 元数据；共享生产 Catalog 依边界留给 PK-000。
- [x] ARCHITECTURE_DOCS — 已同步消费投影、只读 Provider 和零网络边界。
- [x] LOCAL_README — 不适用：无本机路径、端口或私密配置值变化。
- [x] AGENT_RULES — 不适用：协作与安全规则无变化。
- [x] VALIDATION — 已记录实际命令、通过结果、混合工作区既有阻断和 `git diff --check`。

## 独立对话启动提示

```text
继续 Project Kei 的 PK-241 每日生活预报消费端联动任务。先完整阅读项目根目录
README.md、AGENTS.md、README.local.md（如存在）、TASKS.md、
tasks/PK-241-life-forecast-consumers.md，以及 PK-110、PK-140、PK-240 任务记录和
docs/architecture/daily-life-forecast.md。检查 git status 与相关实际差异。

你是本轮唯一串行实施所有者。只实现每日情报只读字段投影和 QQ 显式生活预报查询；
不得修改 PK-240 Provider/缓存/refresh，不得增加 QQ 定时推送，不得读取真实缓存、
.env、个人状态、server/runtime 或 vendor。所有测试使用 fake Provider、固定时钟和
系统临时目录。跨出已冻结路径或需要改变 PK-240 公共契约时立即停止并交回 PK-000。
完成专属实现、累计回归和八项文档门禁后，把本任务置为“待集成”，不要自行改
TASKS.md，不执行 Git 暂存、提交、推送、发布或工作区清理。
```
