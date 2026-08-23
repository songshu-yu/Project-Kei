# PK-900 — 版本集成与发布验收

- 状态：进行中
- 优先级：P0
- 所属模块：`integration`
- 当前批次：`PK-020 + PK-140 + PK-210` QQ 普通回复语音、受控 Silk 编码与 Windows voice-media 安装累计验收
- 依赖任务：PK-020、PK-140、PK-210（均保持待集成）；其登记依赖以 `TASKS.md` 最新状态为准
- 负责路径：`tasks/PK-900-integration-release.md`、跨模块测试、批次验收报告、必要的 README/架构一致性修正；不拥有业务代码
- 当前对话：2026-08-10 已授权独立复验 QQ 文字优先语音附件、固定 Silk profile、能力 fail-closed、hash-locked 安装和共享生产装配；不得真实发送 QQ

## PK-020 + PK-140 + PK-210 QQ 语音附件批次入场（2026-08-10）

- 批次精确登记为 `PK-020 + PK-140 + PK-210`。三项继续保持“待集成”，PK-900
  重新进入“进行中”；旧批次的完成记录和远端证据全部保留，不得改写为本批证据。
- PK-210 验收范围：`POST /api/v1/voice/synthesize` 只能对 PK-200 已生成的普通回复执行
  一次 TTS；多段必须统一为 24 kHz mono s16le PCM 后合并并只编码一次。最终输出固定
  `qq_c2c_voice_v1`、`audio/silk`、`final=true`、不超过 8 MiB/60 秒，并提供有界
  `X-Kei-Audio-Duration-Ms`。不得重新调用 ASR、conversation、LLM 或写聊天历史。
- PK-140 验收范围：开关默认关闭；只有本机 profile ready 且非秘密
  `qq_media_upload_capability=available` 才可开启。普通 conversation 必须先成功发送文字，
  随后最多一次合成与一次 C2C media 发送；菜单、业务命令、每日情报、生命维持、专注鼓励、
  错误与确认保持纯文字。上传只接受 QQ 返回的 HTTPS `*.myqcloud.com:443` 预签名分片，
  禁止重定向、用户 URL、本机路径和 Node 侧转码。
- PK-020 验收范围：`silk-python==0.2.8` 只能由 `voice/full` profile 通过独立
  `voice-media-win.lock.txt`、`--require-hashes` 与 binary-only 安装；四个 Windows x64
  CPython 3.10–3.13 wheel 摘要必须和 PK-210 常量一致。core/qq profile 不因缺少该可选层
  失败，doctor 只检查 version/import/capability，不编码、不写入、不下载、不启动服务。
- 共享装配验收：进程级 `SilkPythonUtteranceEncoder` 固定注入
  `app.state.voice_utterance_encoder`；QQ facade 只读当前 `voice_service.health()`。媒体权限
  默认 provider 固定为 `unknown`，不能从 AppID/Secret 推断，也不能用真实消息探测。因而
  未获得可信 capability 时，真实 UI 保持语音不可开启而文字功能正常，这是预期，不是缺陷。
- 必须独立复现：默认关闭零 TTS/上传；依赖缺失、profile 不可用、capability unknown、恶意
  合成头、非 Silk、超时/超限、恶意预签名 URL、并发、重复消息、重启、损坏状态与 shutdown
  全部 fail closed；文本已发送后语音失败不重发文字；成功 fake 链路严格一次合成、顺序分片、
  一次 `msg_type=7`，且不泄露 OpenID、文字、Secret、URL、file_info、路径或上游错误体。
- 必跑：PK-020 Windows 安装专项与 CI copy；PK-210 voice/module/installable/Silk；PK-140
  配置/安装包/qq-control/全部 Node；module host assembly、Catalog、文档门禁、Python 编译、
  MJS 语法和 `git diff --check`。发布后的真实 Windows runner 还必须覆盖 Python
  3.10/3.11/3.12/3.13 x64、Node 22、Windows PowerShell 5.1 与 PowerShell 7.4+。
- 禁止真实 QQ/Gateway、LLM、ASR/TTS、模型、Voice Pack 或外部网络测试；禁止读取真实
  `.env`、QQ data/runtime、个人状态、缓存、`server/runtime/` 或 `vendor/`。不得暂存、
  提交、推送、发布或清理混合工作区。PK-900 只报告缺陷并退回所属任务，不顺带扩张业务。

## 情报来源批次入场待验收（2026-07-22）

- 批次：`PK-115 + PK-119 + PK-120 + PK-130 + PK-131 + PK-132 + PK-133 + PK-134`。八项均保持“待集成”；PK-900 当前仅登记为“待开始”。
- 验收范围：来源 registry、X/B 资料与缓存、八个 Collector source 的生产 composition、论文 coordinator、版本化/legacy API、控制台来源面板、catalog、README、架构文档和 Collector `1.0` 不变性。
- 必跑：七项来源专属共八个测试、`test_intel_sources_integration.py`、`test_intel_source_config.py`、`test_daily_briefing_module.py`、`test_daily_briefing_summary_cache.py`、`test_feature_catalog.py`、`test_dashboard_shell.py`、`test_conversation_consumers.py`、文档门禁、Python 编译和 `git diff --check`。
- 主动复核：当天缓存读取零 Collector；八 source dispatch/顺序/单源失败隔离；registry 原子失败保留旧配置；X/B 版本化与 legacy 委托一致；YouTube 严格 Channel ID；GitHub 凭证、论文 Key、B 站 Cookie、上游错误体和真实来源名单不泄漏；RSS 任意 URL/内网/危险重定向拒绝。
- 禁止：真实联网、真实来源名单/缓存/凭证读取或 diff、修改 Collector `1.0`、顺带实施 PK-140、整理混合工作区或执行 Git 暂存/提交/推送。若发现重大来源能力缺失，退回所属 PK；只允许 PK-900 记录验收，不重写来源业务。
- 2026-07-22：PK-900 已完整读取根 README、AGENTS、本机 README、任务总板、PK-115/119/120/130/131/132/133/134/900 任务记录及 daily briefing、模块化单体和可安装模块架构说明；检查当前分支与混合工作区后正式领取。本轮只写 PK-900 报告和状态，不覆盖此前批次记录，不修改八个来源任务状态。

## 目标

对当前登记批次执行独立的跨模块兼容、安全、装配、控制台和文档验收，形成可复核的通过/不通过报告。PK-900 默认只验证并记录；发现属于上游实现的缺陷时退回对应任务，不在集成任务中顺带重写业务功能。

## 入场确认

- 2026-07-21：PK-010 与 PK-100 在任务总板及各自任务文件中均为“待集成”；PK-900 入场前为“待开始”。
- `scripts/check_task_docs.py` 入场检查通过，共核对 3 个门禁任务；PK-010、PK-100 的 `TASK_RECORD`、`TASKS_BOARD`、`PUBLIC_README`、`MODULE_CATALOG`、`ARCHITECTURE_DOCS`、`LOCAL_README`、`AGENT_RULES`、`VALIDATION` 均已勾选并有说明。
- 依赖链成立：PK-001 已完成，PK-010 依赖 PK-001；PK-100 依赖 PK-001、PK-010，并已按 PK-010 的目录和模块资产契约实现公共外壳。
- 已授权 PK-900 开始本批验收。入场授权不代表验收通过，PK-010、PK-100 继续保持“待集成”。

## 本批验收范围

- PK-010：本地可信模块包、manifest Schema/校验、包摘要与安全展开、原子注册表、依赖/冲突、安装/配置检查/启停/升级/回滚/卸载/清数据、重启装载和 sidecar 适配协议。
- PK-100：控制台公共 CSS 与 ES modules、同源请求和命名空间限制、通知/折叠/启动、只读功能中心、模块入口过滤与失败隔离、legacy 业务接缝和静态资源路径边界。
- 共享装配：`server/api.py` 中 catalog、dashboard shell、module lifecycle router 的装配顺序与 OpenAPI/实际路由可发现性。
- 共享目录/API：`GET /api/v1/modules` 的旧字段兼容、生命周期字段、dashboard 必需模块映射、启用状态与 `dashboard_entrypoint`/模块资产 URL 一致性。
- 静态入口：`GET /dashboard`、`GET /dashboard/static/{asset_path}`、`GET /api/v1/modules/{module_id}/assets/{asset_path}` 的正常读取、404、同源和路径逃逸边界。
- 文档与任务：`README.md`、`AGENTS.md`、`TASKS.md`、PK-010/PK-100/PK-900 任务记录以及两份架构文档的一致性。
- 测试：现有三个定向测试、编译/语法检查、文档门禁、工作区空白检查，以及不接触真实个人数据的跨层临时模块夹具。

## PK-180 非阻塞决策

- 结论：PK-100 尚未完成的“与 PK-180 真实模块入口联调”不阻塞本批基础设施验收。
- 理由：架构顺序明确把 PK-180 定义为 PK-010、PK-100 之后的独立真实业务试点；PK-010 不拥有 `/focus/*` 业务迁移，PK-100 第一阶段只拥有公共装载契约、过滤和失败隔离。
- 本批替代证据：必须使用临时目录中的合成模块包或去标识化只读夹具验证 manifest → 安装状态 → catalog → `dashboard_entrypoint` → 模块资产边界 → `mount(context)` 的共享接缝，不得读写真实模块注册表、运行目录或个人数据。
- 限制：即使本批通过，也只能说明“安装生命周期与控制台装载基础设施通过集成验收”；不得宣称 focus 或其他真实业务模块已完成安装、启停、数据恢复或控制台端到端联调。
- 后续：PK-180 继续独立负责 focus manifest、公开 service/router、旧 `/focus/*` 兼容、真实数据所有权和端到端试点；PK-900 不得顺带实现。

## 验收范围

- 新旧接口及 Pydantic 目录模型兼容，生命周期错误码和只读/本机写边界符合任务记录。
- 空注册表不产生文件；所有安装测试使用临时目录，失败包不进入运行目录，升级失败保留旧版本。
- 卸载保留模块数据，清数据要求精确确认；验收不得操作真实 `server/data/module_registry.json`、`server/runtime/modules/` 或 `server/data/modules/`。
- API 导入后目录、生命周期、dashboard 静态资源和模块资产路由同时存在；查看目录或打开控制台不触发写入、联网下载、服务启动或付费调用。
- 控制台保留关键 DOM ID、唯一 UI 存储键和 legacy 启动接缝；只加载已启用且有可信入口的模块，单模块错误不阻断其他区域。
- README、架构文档、模块目录映射、任务状态、测试命令和已知限制与实际代码一致。
- 验收报告显式区分本批路径和既有无关修改，不包含 `.env`、缓存、个人状态、运行产物、模型、`node_modules` 或 `vendor/`。

## 必跑测试与检查

在项目根目录使用本机已记录的 ASR 虚拟环境；所有生命周期测试必须保持临时目录隔离。

1. `server/.venv-asr/Scripts/python.exe server/tests/test_installable_modules.py`
2. `server/.venv-asr/Scripts/python.exe server/tests/test_feature_catalog.py`
3. `server/.venv-asr/Scripts/python.exe server/tests/test_dashboard_shell.py`
4. `server/.venv-asr/Scripts/python.exe -m compileall -q server/core/modules server/features/module_manager server/features/catalog server/features/dashboard server/tests/test_installable_modules.py server/tests/test_feature_catalog.py server/tests/test_dashboard_shell.py server/api.py`
5. 对 `server/static/dashboard/` 下 `request.js`、`notifications.js`、`panels.js`、`registry.js`、`module-loader.js`、`app.js` 分别运行 `node --check`；同时确认 `test_dashboard_shell.py` 的内联 legacy `new Function(...)` 检查通过。
6. 运行跨层临时模块夹具，验证生命周期目录输出可被公共外壳按可信 URL 装载；夹具不得成为 PK-180 或任何真实业务模块实现。
7. 使用 `server/tests/test_dashboard_shell.py --preview <临时端口>` 做去标识化只读浏览器冒烟：功能中心、折叠/键盘、单入口 404 隔离、移动端布局。若自动浏览器仍受本机 URL 策略阻止，必须如实记录，禁止绕过；人工补验须明确操作者、夹具和未连接真实 API。
8. `server/.venv-asr/Scripts/python.exe scripts/check_task_docs.py`
9. `git diff --check`，并单独确认本批路径无行尾空白。

## 风险点与必须报告的限制

- 当前工作区包含大量既有修改和未跟踪路径，PK-900 必须按明确路径审阅，不能把整棵工作区当成本批交付，也不能清理或覆盖用户改动。
- PK-010 的既有测试以临时 `ModuleManager` 为主；PK-900 需特别核对 router 本机限制、应用装配和 catalog 合并，不得用真实注册表补足覆盖。
- PK-100 的 Browser 自动控制曾受本机 URL 安全策略限制；已有用户人工只读补验不能替代对当前批次代码的自动定向测试，新的人工证据也必须明确其限制。
- 尚无 PK-180 真实业务包，真实 focus API、数据恢复和面板联调不在本批证据中。
- sidecar 目前只有协议和测试适配器，QQ、ASR、GPT-SoVITS 尚未接入实际 adapter；不得宣称现有独立启动器已由模块管理器接管。
- 第一阶段功能中心为只读，没有安装、启停、升级、回滚、卸载、配置或清数据按钮；后端 API 存在不等于控制台已提供一键生命周期操作。
- `in_process` 模块的启停和切换可能要求重启 API，第一版不承诺运行时移除已注册路由。

## 不在本批范围内

- 实现 PK-180、创建真实 focus 安装包、迁移 `/focus/*` 业务规则或触碰真实专注数据。
- 把其他现有业务模块改造成可安装包，或迁移其控制台面板、service、router、repository。
- 为 QQ、ASR、GPT-SoVITS 实现或启用真实 sidecar adapter。
- 开发生命周期控制台按钮、配置对话框、远程模块商店、自动下载、发布者签名、自动更新或第三方 SDK。
- 调用真实采集、付费 LLM、TTS、QQ 消息、打卡、删除、配置保存，或读写任何个人状态、密钥和缓存。
- 修复与本批契约无关的业务缺陷、重构 `server/api.py` 或清理/格式化无关文件。
- Git 暂存、提交、推送、PR、工作区清理或发布；这些需要用户后续明确授权。

## 完成条件

- 独立 PK-900 任务提交逐项验收报告，列出实际命令、结果、接口矩阵、数据副作用、未覆盖项和明确的通过/不通过建议。
- 必跑测试全部通过；无法执行的浏览器项有合规、可复核的限制说明，且没有绕过工具安全策略。
- 临时跨层模块夹具证明 PK-010 与 PK-100 的共享目录、入口和资产边界可协作，但没有引入真实业务实现或真实状态写入。
- `scripts/check_task_docs.py` 与 `git diff --check` 通过，批次文档与任务总板一致。
- 发现的上游缺陷已明确归属 PK-010 或 PK-100；未在 PK-900 中越界重写业务功能。
- PK-010、PK-100 在验收报告提交前保持“待集成”。只有 PK-000 阅读并确认报告后，才可决定是否将二者和 PK-900 改为“已完成”或退回整改。

## 工作记录

- 2026-07-21：PK-000 完成入场确认。确认批次为 `PK-010 + PK-100`，两项上游任务状态、依赖、八项文档门禁、测试记录、接口和遗留事项具备进入独立集成验收的条件。
- 2026-07-21：PK-000 判定 PK-180 真实模块联调为后续独立任务，不阻塞本批基础设施验收；同时将“无真实业务包端到端证据”列为必须写入最终报告的限制。
- 2026-07-21：独立 PK-900 验收开始。已按顺序完整读取根 README、AGENTS、本机 README、任务总板、PK-010/PK-100/PK-900 任务记录及两份架构规范；确认 PK-900 已由入场流程置为“进行中”，本批仍严格限定为 `PK-010 + PK-100`。
- 2026-07-21：检查分支与工作区，当前分支为 `agent/intel-sources-dashboard`，存在多个任务和用户修改以及大量未跟踪文件。本次仅审阅/修改本批明确路径，不重置、删除、覆盖、暂存或整理 `vendor/`、个人状态及其他任务变更。
- 2026-07-21：逐项核对 manifest、目录/ZIP 摘要、安全展开、原子注册表、依赖/冲突、配置检查、启停、升级、回滚、卸载保留数据、精确确认清数据、重启装载、sidecar 协议、本机写接口限制及模块资产边界；未读取或修改真实注册表、运行目录和个人状态。
- 2026-07-21：逐项核对 `GET /dashboard`、公共静态资源、路径穿越 404、目录字段脱敏、启用且有入口过滤、同源资产前缀、请求命名空间、`mount(context)`/`unmount()`、10 秒超时和单模块失败隔离；确认第一阶段功能中心没有生命周期写按钮。
- 2026-07-21：修复两项本批缺陷：PK-100 原读取不存在的 `last_operation.operation`，现与 PK-010 的 `action/status` 一致；失败入口长 URL 在 390px 视口造成横向溢出，现为 `.module-error` 增加 `overflow-wrap:anywhere`。
- 2026-07-21：新增临时跨层夹具，完整验证本地包安装为 `installed_disabled`、启用后 `enabled/restart_required`、catalog 合并、Pydantic 响应兼容、可信 `dashboard_entrypoint` 和只限 `dashboard/` 的资产读取；夹具位于系统临时目录并自动清理，不是 PK-180 实现。
- 2026-07-21：PK-010 完成 Core 保留 ID/namespace 整改后，PK-000 二次独立复核实际代码与写入顺序，重放四类保留边界攻击并确认全部拒绝、无状态残留。
- 2026-07-21：PK-000 重跑本批全部必跑测试、编译、六个公共 JavaScript 语法检查和文档门禁，确认 PK-010 与 PK-100 通过；本批最终状态为“已完成”。

## 验收报告

### 结论

**有条件通过。** PK-010 与 PK-100 的基础设施契约、共享目录和动态入口协议通过集成验收；条件/限制是 PK-180 真实 focus 包尚未实施，故不能宣称任何真实业务模块已完成端到端安装、启停、数据恢复或面板联调。该限制按既定架构顺序属于基础设施验收后的已知限制，不是本批阻塞项。

## PK-000 独立复核

### 复核结论

**不接受当前“有条件通过”结论，批次退回进行中。** PK-180 仍不是本批阻断项，但 PK-010 存在 Core 身份和 API namespace 隔离缺口，违反必需模块不可被可选包覆盖以及模块 namespace 不得与 Core 冲突的基础契约。PK-010、PK-100、PK-900 均不得据此进入“已完成”。

### 阻断证据

- PK-000 在当前工作区独立重跑 `test_installable_modules.py`、`test_feature_catalog.py`、`test_dashboard_shell.py` 和约定 compileall，均通过；说明原报告的自动测试结果可复现，但现有测试覆盖不足。
- 使用系统临时目录构造 `required: false`、ID 为 `dashboard` 的本地包，安装与启用均成功；将该临时 manager 合并到目录后，dashboard 项变为 `required=False`、`managed=True`、`source=local_package`，且 namespace 被本地声明覆盖。临时目录随后自动清理，未接触真实注册表、运行目录或个人数据。
- 使用另一个系统临时目录构造 ID 为 `shadow`、`api_namespaces=["/api/v1/modules"]` 的本地包，安装成功并进入 `installed_disabled`；证明 namespace 冲突检查只覆盖本地注册表，没有保护 Core 自有路由。

### 退回要求

- PK-010 必须拒绝至少 `catalog`、`module_manager`、`dashboard` 等 Core 保留 ID；拒绝发生在创建正式版本目录或写入注册表之前。
- PK-010 必须拒绝 `/api/v1/modules` 等 Core 自有 namespace，并明确保留集合的唯一来源，避免 manager、catalog 与文档各自维护漂移的副本。
- 增加隔离回归，至少覆盖 Core ID 伪装、Core namespace 占用、失败后无运行目录/注册表残留，以及正常非保留模块仍可安装。
- 修复后重跑本批全部必跑项并更新 PK-010、PK-900 工作记录；PK-000 再次独立复核前，PK-100 保持“待集成”，PK-010 与 PK-900 保持“进行中”。

## PK-000 二次复验与最终结论

### 最终结论

**通过。** PK-010 已关闭首轮复核发现的 Core 身份与 API namespace 隔离缺口；PK-100 在依赖整改后无回归。PK-000 据此接受 `PK-010 + PK-100` 基础设施批次，并将 PK-010、PK-100、PK-900 置为“已完成”。

### 二次复验证据

- `server/core/modules/contracts.py` 是 Core ID、namespace、必需属性和目录来源的唯一契约；ModuleManager 与 catalog 共同消费该契约。
- PK-000 使用系统临时目录独立重放 `dashboard` Core ID、`/api/v1/modules`、其子 namespace 和父级 `/api/v1` 四类输入。前三类返回 `ModuleConflictError`，父级因 manifest 结构约束更早返回 `ManifestValidationError`；四类均未生成 registry、正式 runtime 版本目录或模块数据目录。
- 恶意生命周期快照不能覆盖 `catalog`、`module_manager`、`dashboard` 的 `required=True`、`managed=False`、`source=core_builtin` 和 Core namespace；占用 Core namespace 的额外目录项会被忽略。
- `test_installable_modules.py`、`test_feature_catalog.py`、`test_dashboard_shell.py`、规定 compileall 和六个公共 JavaScript `node --check` 全部通过；跨层夹具仍证明正常可选模块可安装、启用、合并目录并读取受限 dashboard 资产。
- 所有复验使用临时隔离 manager/目录；未读取或写入真实模块注册表、运行目录、个人状态、密钥或缓存，也未执行 Git 暂存、提交、推送或清理。

### 最终限制

- PK-180 真实 focus manifest、service/router、旧接口兼容、真实数据迁移/恢复和 `mount(context)` 联调仍是独立后续任务，不是本批阻断项。
- 本次通过只代表可安装模块生命周期、目录契约与控制台公共外壳基础设施通过；不代表任何真实业务模块、实际 sidecar adapter 或控制台生命周期写操作已经完成。

### 接口与语义矩阵

- PK-010：manifest Schema 与运行时校验一致；仅接受本地目录/ZIP 和调用方 SHA-256，拒绝绝对路径、`..`、反斜杠、符号链接、`.env`、超限包和未批准权限。
- 生命周期：安装失败不写正式记录；升级使用新版本目录并保留旧版本；启停、回滚和装载结果持久化；`in_process` 正确报告重启要求；sidecar 仅允许 Core 注册 adapter；卸载保留数据，清数据独立且要求精确模块 ID。
- 目录兼容：`GET /api/v1/modules` 保留既有必需字段，生命周期字段均为带默认值的扩展；目录读取无安装、联网、启动或付费副作用，Pydantic 响应不会输出包摘要等未声明内部字段。
- PK-100：`GET /dashboard`、`/dashboard/static/{asset_path}` 和既有 QQ 图片入口保持可用；公共与模块静态路由均限制在各自根目录，路径逃逸返回 404/错误而不泄露文件。
- 功能中心：只读展示目录声明的状态、依赖、配置、权限、重启和数据策略，不展示配置值；只加载 `enabled === true` 且具有可信入口的模块，不提供安装、启停、卸载或清数据写控件。
- 动态入口：只接受同源 `/api/v1/modules/<module_id>/assets/`，模块获得独立 DOM 根、冻结目录快照、限定 API 前缀的请求和统一通知；缺入口、404、超时、缺少 `mount()` 或挂载异常均隔离到单模块。

### 修复

- `server/static/dashboard/module-loader.js`：最近操作字段从错误的 `operation` 改为 PK-010 实际契约 `action`。
- `server/static/dashboard/shell.css`：失败入口长 URL 允许窄屏断行，避免模块错误撑破移动端布局。
- `server/tests/test_dashboard_shell.py`：新增上述字段/样式回归和临时模块生命周期到控制台资产的跨层夹具。

### 浏览器只读回归

- 本次 Browser 自动控制成功打开 `http://127.0.0.1:8765/dashboard` 的去标识化预览；确认功能中心无生命周期按钮、禁用/无入口模块不加载、故意 404 的入口只在自身容器报错、其余 legacy 页面继续存在，并通过键盘操作功能中心折叠按钮。
- 390×844 视口首次检查发现失败信息长 URL 造成页面横向宽度 586px，已据此修复。修复后的浏览器新标签仍命中旧 CSS 缓存（计算样式为旧值），因此不把自动视觉复验宣称为通过；落盘 CSS、静态资源路由和定向测试已确认修复存在。PK-100 既有人工只读预览结果仍作为其他布局/折叠验证证据。
- 预览未连接真实 API，不存在业务写路由；未调用采集、QQ、付费接口、TTS、删除、保存、打卡或个人状态操作。

### 风险与遗留

- PK-180 仍须独立提供真实 focus manifest、service/router、旧 `/focus/*` 兼容、数据迁移/恢复和真实 `mount(context)` 联调；PK-900 未实现或修改 PK-180。
- sidecar 当前只有协议与测试 adapter，QQ、ASR、GPT-SoVITS 未由模块管理器接管。
- 第一阶段控制台明确只读；后端生命周期 API 存在不等于已提供控制台一键操作。
- `in_process` 启停、升级或回滚可能要求重启 API，第一版不保证运行时卸载已注册路由。
- 工作区包含大量不属于本批的用户修改和未跟踪内容；本报告只覆盖列明的 PK-010、PK-100 与必要共享路径。

### 实际验证

- `server/.venv-asr/Scripts/python.exe server/tests/test_installable_modules.py`：通过。
- `server/.venv-asr/Scripts/python.exe server/tests/test_dashboard_shell.py`：通过（含跨层临时模块夹具、内联 legacy `new Function(...)` 和公共 JS `node --check`）。
- `server/.venv-asr/Scripts/python.exe server/tests/test_feature_catalog.py`：通过。
- `server/.venv-asr/Scripts/python.exe -m compileall -q server/core/modules server/features/module_manager server/features/catalog server/features/dashboard server/tests/test_installable_modules.py server/tests/test_feature_catalog.py server/tests/test_dashboard_shell.py server/api.py`：通过。
- `node --check`：`request.js`、`notifications.js`、`panels.js`、`registry.js`、`module-loader.js`、`app.js` 全部通过。
- `server/.venv-asr/Scripts/python.exe scripts/check_task_docs.py`：通过，输出 `task documentation gate passed: 4 gated task(s)`。
- `git diff --check`：通过，退出码 0；仅有工作区既存的 LF→CRLF 提示，无空白错误。
- `Select-String -Path <本批修改路径> -Pattern '[ \t]+$'`：无匹配。本批未执行 Git 暂存、提交或推送。

## 完成文档门禁

PK-010 整改完成后，PK-000 已执行二次独立复验并接受本批最终结论；以下八项均已完成。

- [x] TASK_RECORD — 已记录 PK-010 整改后的统一 Core 契约、隔离重放、完整测试、副作用、风险、限制和最终结论。
- [x] TASKS_BOARD — 已将 PK-010、PK-100、PK-900 同步为“已完成”；名称、优先级和批次依赖不变。
- [x] PUBLIC_README — 已同步最近操作字段契约和窄屏失败信息换行；既有生命周期、只读控制台、重启与 PK-180 限制说明核对一致。
- [x] MODULE_CATALOG — 已验证 Core 必需模块映射不可被恶意生命周期快照覆盖，占用 Core namespace 的额外目录项会被隔离。
- [x] ARCHITECTURE_DOCS — 已同步并核对 Core 保留身份/namespace、manifest、生命周期、资产边界和控制台装载协议与代码一致。
- [x] LOCAL_README — 不适用：无本机路径、端口、启动器、解释器或环境位置变化；8765 仅为已停止的临时只读预览。
- [x] AGENT_RULES — 不适用：未改变 agent 工作流、安全、验证、文档或 Git 规则。
- [x] VALIDATION — 已在 PK-010 整改后重跑完整批次测试、编译、JavaScript、文档门禁、隔离审计、明确路径行尾检查和 `git diff --check`。

## 独立对话启动提示

```text
领取 Project Kei 的 PK-900 集成验收批次：PK-010 + PK-100。先完整阅读
README.md、AGENTS.md、README.local.md（如存在）、TASKS.md、
tasks/PK-010-installable-modules.md、tasks/PK-100-dashboard-shell.md、
tasks/PK-900-integration-release.md、docs/architecture/modular-monolith.md 和
docs/architecture/installable-modules.md，检查 git status 和本批明确路径。
严格按 PK-900 文件中的必跑测试、风险和非目标执行；只做独立验收与报告，
不实现 PK-180，不顺带重写业务模块，不触碰真实个人数据，不执行 Git 发布。
```

## PK-180 集成验收批次

### 批次登记

- 2026-07-21：上一批 `PK-010 + PK-100` 的入场、退回整改、二次复验和 PK-000 最终“通过”结论继续完整有效；上文历史不覆盖、不改写。本节是独立第二批次。
- 2026-07-21：本轮只验收 PK-180“专注计时与首个可安装模块试点”，不顺带验收或实现健身、日历、斩妖、语音、QQ、情报或其他业务模块。
- 2026-07-21：入场核对确认 PK-180 为“待集成”且八项文档门禁已完成；`scripts/check_task_docs.py` 通过并检查 5 个门禁任务。PK-010、PK-100 保持“已完成”，仅作为本轮生命周期和控制台公共契约基线，不重新打开。
- 2026-07-21：PK-900 已从上一批“已完成”重新置为“进行中”，总板本批依赖更新为 `PK-180（本批次）`。
- 2026-07-21：当前分支仍为 `agent/intel-sources-dashboard`，工作区包含多个任务、用户修改和未跟踪内容。已确认 `server/systems/data/focus_timer.json` 显示为修改，但本轮不会读取、打印、查看详细 diff、重置、覆盖、格式化、暂存、提交或用于测试；其他同名历史状态同样保护。

### 当前进度

- 已重新完整读取当前 README、AGENTS、本机 README、任务总板、PK-180/PK-900/PK-010/PK-100 任务文件和两份架构规范。
- 所有 focus 状态、registry、runtime、module data 和 ZIP 写入验证均显式使用系统临时目录；未读取或修改真实 `focus_timer.json`。

### 验收范围与实际审阅路径

- 审阅 `server/features/focus/` 的 models、repository、service、router、module 注册、package builder、manifest 和 dashboard 入口；审阅 `server/systems/focus_timer.py` 兼容接缝。
- 定向核对 `server/api.py` 的 focus 状态路径/TTS 注入与动态装配，`server/features/catalog/` 的未安装/生命周期覆盖语义，以及 `server/static/dashboard.html` 是否残留旧 focus DOM、函数、请求或事件。
- 审阅并实际运行 `test_focus_timer.py`、`test_focus_module.py`、`test_focus_dashboard.py` 及 PK-010/PK-100/catalog 回归；新增覆盖只放在 PK-180 测试路径。
- 排除其他业务模块、真实个人状态、真实 registry/runtime/module data、外部服务、`vendor/` 和工作区其他用户修改。

### 代码边界结论

- `models -> router -> service -> repository` 边界清晰；计时规则只在 `service.py`，JSON 读写只在 `repository.py`，HTTP 与新旧路由只在 `router.py`。
- `server/systems/focus_timer.py` 仅重新导出同一实现，没有第二套状态机；`server/api.py` 不再静态声明 focus 路由，只注入历史状态路径和可选 TTS 回调。
- `dashboard.html` 中不存在旧 focus 面板 ID、`/focus/*` 请求、渲染或事件；动态面板只由安装包入口挂载，因此不会出现静态/动态双面板。
- focus 未安装、停用、卸载或新进程装载失败时，不影响 Core、catalog 或公共控制台；新进程不会装配 focus 路由。

### 新旧接口兼容矩阵

| 行为 | `/api/v1/focus/*` | `/focus/*` | 结果 |
|---|---|---|---|
| `GET status` | 同一 handler/service | 同一 handler/service | 字段、状态码、进行中/完成/空闲及重启恢复一致 |
| `POST start` | `mode/minutes/task/force/with_audio` | 相同模型 | 默认 pomodoro 25 分钟、focus 50 分钟、自定义分钟、重复启动与 force 语义一致 |
| `POST stop` | 同一 service | 同一 service | 停止、自然完成和空闲停止语义一致 |
| `POST reset` | 独立显式操作 | 独立显式操作 | 返回 `status/cleared_sessions`，不等于卸载或 purge-data |

TTS 仅通过隔离假异步回调验证 `with_audio`；未调用真实 TTS。两组接口完整响应在独立临时 store 场景中逐项相等。

### 实际包与 manifest 审计

- 使用实际 `server/features/focus/package_builder.py` 在系统临时目录构建 1.0.0/1.1.0 ZIP。两次 1.0.0 构建字节完全相同且 SHA-256 相同，ModuleManager 计算摘要与构建器一致。
- manifest 经正式运行时校验，实际声明 `focus`、`in_process`、`required=false`、`backend.register`、`/api/v1/focus`、四个 `/focus/*`、`dashboard/index.js`、`data_namespace=focus`、`local_state`、`requires_restart=true`。
- ZIP 仅含 `manifest.json`、`backend/{__init__,models,module,repository,router,service}.py` 和 `dashboard/index.js`；条目无绝对路径、`..` 或大小写重复，不含 `focus_timer.json`、data/runtime/registry/cache、`.env`、BAT/CMD/PowerShell/shell 或测试状态。
- 错误摘要、未知 manifest 字段、缺失已声明 dashboard 入口、Core namespace 和模块 namespace 冲突均在正式记录前失败，无 registry、正式版本目录或 module data 残留。

### 生命周期与重启矩阵

- 安装：`installed_disabled`，未启用时无路由装配且目录无 dashboard URL。
- 启用：返回 `enabled=true/restart_required=true`；新 app 装配八个新旧路由，资产可读，catalog 返回可信 `/api/v1/modules/focus/assets/dashboard/index.js`。
- 运行恢复：临时进行中状态在新 app 恢复；自然完成状态在重启后报告 completed；重复启动受保护。
- 升级：1.1.0 成功切换并要求重启；缺失声明入口的实际 1.1.0 升级失败后仍为已启用 1.0.0，无半安装目录，旧版本新 app 仍可装配。
- 停用：旧 app 保留已注册路由；新 app 无 focus 路由，资产不可读，符合第一版非热卸载语义。
- 卸载/重装：程序版本与资产消失，临时历史状态文件保留；重装、启用和新 app 重新关联同一进行中状态。
- purge-data：错误确认拒绝；精确确认只删除临时 `data/modules/focus` sentinel，历史临时 focus store 保留。focus reset、卸载和 purge-data 为三个独立操作。

### 动态面板结果

- 实际入口导出 `mount(context)` 与 `unmount()`，只查询 `context.root`，所有请求均限定 `/api/v1/focus/*`，不访问其他模块 DOM 或浏览器存储。
- 启动、停止、状态刷新、自定义分钟、task、`with_audio=false` 和 reset 二次确认由 Node 假 DOM 自动验证；`unmount()` 清理 interval 并清空自身根节点。
- 发现并修复：reset 成功后按钮原保持 disabled。现成功后恢复可用，并有回归断言。
- 公共加载器的未启用/无入口/不可信入口过滤、资产穿越拒绝和单模块错误隔离由 PK-100 回归继续覆盖。

### 数据副作用与主动安全审计

- `DEFAULT_STORE` 指向受保护历史路径，但模块/兼容层全局 import 只构造 repository/service，不执行 `load/save`；所有自动请求均显式注入临时 `focus_state_path`。
- 重装不会创建空文件覆盖保留状态；启用新 app 的 status 会从同一临时历史 store 恢复。卸载和 module purge 均不会触碰包外历史状态。
- catalog 未安装 focus 明确为 `available/enabled=false/installable`，不会误报 enabled；生命周期 snapshot 仅在实际安装后覆盖。
- 包 manifest/实际入口由构建器取同一受审阅源码，包安装阶段再次验证声明文件；摘要不匹配、非法包和失败升级均无半安装状态。

### 浏览器结果与限制

- 新增 `test_focus_dashboard.py --preview 8766`：启动时在系统临时目录构建、安装、启用实际 focus 包，并只关联临时计时状态。
- Browser 对 `http://127.0.0.1:8766/dashboard` 两次均返回连接拒绝；没有尝试变体 URL、其他浏览器或绕过方式。因此本轮未完成真实浏览器的动态加载、键盘焦点和窄屏视觉检查，也不宣称视觉通过。
- 自动替代证据包括真实包生命周期/资产/catalog、新旧 ASGI API、Node 假 DOM mount/unmount、公共外壳过滤/隔离和 JavaScript 语法检查。仍建议 PK-000 最终复核前由用户在该去标识化临时预览做一次人工只读视觉补验；不得连接真实状态后点击开始、停止或 reset。

### 缺陷与修复

- PK-180 缺陷：reset 成功后按钮没有恢复可用。已最小修复 `dashboard/index.js` 并在 `test_focus_dashboard.py` 增加回归。
- 覆盖缺口：增加实际 ZIP 确定性与实际 focus 失败升级保留旧版本/无半安装回归。未发现需要重开 PK-010 或 PK-100 的公共契约缺陷。

### 工作区排除项与遗留风险

- `server/systems/data/focus_timer.json` 当前显示已修改，但内容和 diff 从未读取；`server/data/focus_timer.json` 及其他同名文件同样未接触。
- 真实 Windows 浏览器视觉仍待人工只读补验；第一阶段功能中心仍无生命周期写按钮；两处历史 focus 状态不会自动合并。
- 本轮未暂存、提交、推送、创建 PR 或清理工作区。

### 最终结论

**有条件通过。** 实际 focus 包已完成 SHA-256、安装、启用、重启装配、新旧 API、catalog、可信 dashboard 入口、自动 mount/unmount、停用、重启隔离、卸载保留与重装恢复闭环；唯一条件是当前 Browser 无法连接临时本地预览，真实视觉/键盘/窄屏需人工只读补验。该条件不掩盖任何已知生命周期或数据安全缺陷。

### PK-000 最终复核

- 2026-07-21：PK-000 复核第二批报告、PK-180 代码边界、实际包/lifecycle 证据、动态面板修复和全量门禁，确认没有未关闭的生命周期、接口兼容、数据安全或 PK-010/PK-100 公共契约缺陷。
- PK-000 接受“有条件通过”。Browser 无法连接临时本地预览属于当前自动控制环境限制；人工去标识化只读视觉补验继续保留为非阻塞后续项，不宣称已经执行。
- PK-180 与本轮 PK-900 据此进入“已完成”；PK-010、PK-100 继续保持“已完成”。本结论不扩大为其他业务模块已可安装，也不取消第一阶段功能中心只读、历史 focus 文件不自动合并等既有限制。
- 状态同步后最终门禁通过：focus timer/module/dashboard、catalog、公共 dashboard、Python 编译、focus JavaScript、`task documentation gate passed: 5 gated task(s)`、`git diff --check` 和本批行尾检查均成功。

### 本批实际验证

- `server/.venv-asr/Scripts/python.exe server/tests/test_focus_timer.py`：通过。
- `server/.venv-asr/Scripts/python.exe server/tests/test_focus_module.py`：通过，含新增确定性 ZIP 和失败升级回归。
- `server/.venv-asr/Scripts/python.exe server/tests/test_focus_dashboard.py`：通过，含 reset 按钮恢复回归。
- `server/.venv-asr/Scripts/python.exe server/tests/test_installable_modules.py`：通过。
- `server/.venv-asr/Scripts/python.exe server/tests/test_feature_catalog.py`：通过。
- `server/.venv-asr/Scripts/python.exe server/tests/test_dashboard_shell.py`：通过。
- `server/.venv-asr/Scripts/python.exe -m py_compile ...`：通过，覆盖 `server/api.py`、focus 全部 Python、catalog 和六个相关测试。
- `node --check`：实际 focus 入口与六个公共 dashboard JavaScript 全部通过。
- 状态切换前 `server/.venv-asr/Scripts/python.exe scripts/check_task_docs.py`：通过，输出 `task documentation gate passed: 4 gated task(s)`；PK-900 尚为“进行中”所以未计入。
- PK-900 切换为“待集成”后复跑文档门禁：通过，输出 `task documentation gate passed: 5 gated task(s)`。
- `git diff --check`：通过，退出码 0；仅输出混合工作区既有 LF→CRLF 提示，无空白错误。
- 本批文本路径 `Select-String -Pattern '[ \t]+$'`：无匹配；首次扫描误包含 `__pycache__/*.pyc` 后已修正为仅扫描 `.py/.js/.md/.json` 源文件，不构成功能失败。

### 本批完成文档门禁

- [x] TASK_RECORD — 本节已记录范围、路径、接口、包、生命周期、重启、面板、数据、副作用、Browser 限制、修复、验证和结论；PK-180 工作记录同步修复。
- [x] TASKS_BOARD — 已登记 PK-900 的 PK-180 批次；PK-000 接受报告后，PK-180 与 PK-900 均同步为“已完成”。
- [x] PUBLIC_README — 已同步 focus reset 二次确认成功后的按钮恢复语义；现有安装、重启、数据保留和限制说明核对一致。
- [x] MODULE_CATALOG — 已核对未安装、安装、启用、停用/卸载的 focus 映射、八个接口、namespace、入口和迁移状态；无需新增字段。
- [x] ARCHITECTURE_DOCS — 已核对 focus 模块边界、manifest、重启、动态入口和历史数据例外；本次修复未改变架构协议，无需修改。
- [x] LOCAL_README — 不适用：无本机路径、服务端口、启动器、解释器或环境位置变化；8766 仅为已停止的临时测试预览。
- [x] AGENT_RULES — 不适用：未改变协作、安全、验证、文档或 Git 规则。
- [x] VALIDATION — 已记录实际测试；最终状态切换前重跑文档门禁、完整测试、编译、JS、行尾和 `git diff --check`。

## PK-190 集成验收批次

### 批次登记与入场结论

- 2026-07-21：上一批 `PK-180` 及更早的 `PK-010 + PK-100` 验收历史和最终结论继续有效；本节登记独立第三批次 `PK-190`，不覆盖既有报告。
- PK-190 当前为“待集成”，八项完成文档门禁已勾选；PK-001、PK-010、PK-100、PK-180 均为“已完成”。PK-900 已从上一批“已完成”重新置为“进行中”，总板本批依赖同步为 `PK-190（本批次）`。
- PK-000 已独立核对任务记录、实际分层、新旧路由、voice provider、legacy 控制台、目录项、README、架构说明和隔离测试；未发现阻止进入集成验收的问题。
- 复查前后 `server/systems/data/calendar_memo.json` 均未出现在 `git status --short -- <该路径>` 输出中；未读取其内容或详细 diff。当前混合工作区的其他任务、个人状态和 `vendor/` 继续排除，不整理、不覆盖。

### 本批验收边界与重点

- 只验收 PK-190 的普通内置 `calendar` 模块化：`models -> router -> service -> repository`、`server/systems/calendar_memo.py` 兼容导出及 `server/api.py` 装配；不按可安装模块验收。
- 核对 `/api/v1/calendar/*` 与 `/calendar/*` 由同一 router/handler/service/repository 提供，legacy 成功响应、控制台日历/修炼面板和语音查询保持兼容。
- 核对 voice 只通过可注入的公开 calendar summary provider/service，不导入 repository、默认路径或直接打开状态文件。
- 以显式临时 `CalendarMemoStore` 验证一次性/yearly、闰年 2 月 29 日、跨年未来七天、`days=0`/负数、确定性 ID/重复保护、标签备注、修炼累计、最近记录、全部境界阶段、损坏结构、并发锁和原子替换失败保护。
- 核对版本化 reset 只接受精确 `{"confirmation":"calendar"}`；legacy reset 继续兼容但其全量删除风险必须保留在报告中，控制台不得出现 reset 入口。
- 核对目录仍为 `in_process`/`modular`、10 个新旧 endpoint、`local_state` 权限、calendar 单独数据所有权和 `legacy` 控制台表面；README、架构文档、任务总板与实际代码一致。

### 必跑测试与检查

```powershell
cd server
.\.venv-asr\Scripts\python.exe tests\test_calendar_memo.py
.\.venv-asr\Scripts\python.exe tests\test_calendar_module.py
.\.venv-asr\Scripts\python.exe tests\test_voice_calendar_intents.py
.\.venv-asr\Scripts\python.exe tests\test_feature_catalog.py
.\.venv-asr\Scripts\python.exe tests\test_dashboard_shell.py
.\.venv-asr\Scripts\python.exe ..\scripts\check_task_docs.py
cd ..
git diff --check
git status --short -- server/systems/data/calendar_memo.json
```

运行前必须先确认每项会写状态的测试都显式注入系统临时 store；不得通过启动真实 API、调用 legacy reset 或 monkeypatch 默认路径补证。若增加测试，仍只能使用去标识化临时数据。

### 风险、遗留与非目标

- legacy `POST /calendar/reset` 仍无需确认并会全量删除 events、skills、practice_logs；这是已接受的兼容风险，不得误报为已消除，也不得在 PK-900 中自行收紧旧接口。
- 出于个人数据边界，真实历史文件内容兼容只按既有 Schema 和临时夹具验证；不得为提高证据强度读取、迁移、修复、reset 或打印真实文件。
- 进程内共享路径锁和原子替换不等于跨进程文件锁；PK-900 应记录这一边界，但除非现有运行架构出现实际多进程写者证据，不自动扩大为新基础设施实现。
- 编辑、单条删除、批量删除、导入导出、外部同步、提醒推送、manifest、ZIP、安装/启停/卸载/重装、动态 `mount(context)`/`unmount()` 面板均不在本批范围。
- 不迁移健身、专注、斩妖、好感度、长期记忆或其他业务，不重开已完成的 PK-010、PK-100、PK-180；若发现公共契约缺陷，只记录证据和归属并交回 PK-000。

### 状态控制与交付

- 本登记仅授权独立 PK-900 开始验收，不代表 PK-190 已通过；PK-190 必须保持“待集成”。
- 独立任务应提交可复核的通过/不通过报告，列出实际命令、结果、数据隔离方式、风险、限制和工作区排除项；不得顺带实现业务修复。
- 只有 PK-000 阅读实际差异和 PK-900 报告并独立确认后，才能决定将 PK-190 与本轮 PK-900 改为“已完成”或退回整改。

### 本轮入场复查证据

- `test_calendar_memo.py`、`test_calendar_module.py`、`test_voice_calendar_intents.py`、`test_feature_catalog.py`、`test_dashboard_shell.py`：全部通过。
- 入场状态切换前 `scripts/check_task_docs.py`：通过，输出 `task documentation gate passed: 6 gated task(s)`；登记 PK-900 为“进行中”后复跑仍通过，输出 `5 gated task(s)`，因为进行中的 PK-900 不计入完成门禁。
- `git diff --check`：退出码 0，仅有混合工作区既有 LF→CRLF 提示；真实 calendar 状态路径在复查前后均无状态输出。

### 独立任务启动提示

```text
领取 Project Kei 的 PK-900 集成验收批次：PK-190。完整阅读根 README、AGENTS、
README.local（如存在）、TASKS、PK-190/PK-900 任务文件及两份架构文档，检查
本批实际差异。严格按“PK-190 集成验收批次”的边界和必跑项独立复核；所有
状态写入只能使用显式临时 CalendarMemoStore。不要读取真实 calendar_memo.json，
不要实现可安装包、动态面板、编辑删除或同步提醒，不要重写上游功能，也不要
执行 Git 暂存、提交、推送或工作区清理。完成后提交报告，保持 PK-190 待集成，
等待 PK-000 最终确认。
```

### 独立验收报告

#### 结论

**通过。** PK-190 的内置 calendar 分层、新旧 API、voice 只读接缝、legacy 控制台、模块目录、数据隔离和文档契约在当前工作区通过独立复核。未发现需要退回 PK-190 的集成缺陷；本轮未修改任何业务代码，PK-190 继续保持“待集成”，由 PK-000 决定最终状态。

#### 实际审阅与契约结果

- `server/features/calendar/` 符合 `models -> router -> service -> repository` 边界：router 不读写 JSON，service 拥有日期、重复事件、未来七天、确定性 ID、修炼累计和摘要规则，repository 独占校验、同路径进程锁、唯一临时文件与原子替换。
- `server/systems/calendar_memo.py` 仅重导出同一实现；`server/api.py` 只装配 `create_calendar_router(get_calendar_service())`，不存在旧 calendar handler 副本。
- `/api/v1/calendar/*` 与 `/calendar/*` 共用同一组 handler/service/repository；版本化 reset 只接受精确 `calendar`，legacy reset 继续兼容且控制台无 reset 控件。
- voice pipeline 只导入公开 calendar service 函数，并支持注入只读摘要 provider；测试未加载真实状态。legacy 控制台仍只有一个 calendar 面板，页面加载只执行状态查询，写入只由用户显式添加事件或练习触发。
- catalog 中 calendar 为 `main-api`、`in_process`、`modular`、`local_state`，列出 5 条版本化和 5 条 legacy endpoint，数据所有权仍指向 calendar 独立状态，控制台表面为 `legacy`。它没有 manifest、安装包、生命周期状态或动态入口。
- README、任务总板和模块化架构说明与当前实现一致；可安装模块规范中的 calendar 分类是后续计划，不代表 PK-190 已把 calendar 制作为可安装模块。

#### 数据隔离与副作用

- 执行前逐项审计测试：事件、练习、损坏 JSON、错误结构、并发、原子替换失败和两类 reset 均在 `TemporaryDirectory` 中显式构造 `CalendarMemoStore(Path(temp_dir) / "calendar_memo.json")` 或等价临时路径；没有通过 monkeypatch 替换默认 calendar 路径。
- API 等价测试使用临时 FastAPI app 和显式临时 `CalendarService(CalendarMemoStore(path))`；voice 测试注入去标识化摘要 provider；catalog/dashboard 测试只构造临时 ModuleManager，应用导入不会读取 calendar store。
- `git status --short -- server/systems/data/calendar_memo.json` 在测试前后均无输出。未读取、打印、diff、迁移、格式化、reset、修改、暂存或提交真实 calendar 状态，也未启动真实 API 或调用任何真实写路由。
- 未调用外部采集、LLM、TTS、ASR、QQ、付费接口或生产写操作；未创建 calendar manifest、ZIP、动态面板、编辑删除、同步或提醒功能。

#### 实际命令与结果

- `cd server; .\.venv-asr\Scripts\python.exe tests\test_calendar_memo.py`：通过，输出 `calendar memo tests passed`。
- `cd server; .\.venv-asr\Scripts\python.exe tests\test_calendar_module.py`：通过，输出 `calendar module tests passed`。
- `cd server; .\.venv-asr\Scripts\python.exe tests\test_voice_calendar_intents.py`：通过，7 个意图判断与注入 provider 检查均成功。
- `cd server; .\.venv-asr\Scripts\python.exe tests\test_feature_catalog.py`：通过，输出 `feature catalog tests passed`。
- `cd server; .\.venv-asr\Scripts\python.exe tests\test_dashboard_shell.py`：通过，输出 `dashboard shell tests passed`；包含 legacy 内联脚本 `new Function(...)` 和公共 JavaScript 检查。
- `cd server; .\.venv-asr\Scripts\python.exe -m py_compile api.py features\calendar\__init__.py features\calendar\models.py features\calendar\repository.py features\calendar\router.py features\calendar\service.py systems\calendar_memo.py services\voice_pipeline.py features\catalog\models.py features\catalog\service.py tests\test_calendar_memo.py tests\test_calendar_module.py tests\test_voice_calendar_intents.py tests\test_feature_catalog.py tests\test_dashboard_shell.py`：通过。
- `cd server; node --check static\dashboard\{request,notifications,panels,registry,module-loader,app}.js`：六个文件分别通过。
- `cd server; .\.venv-asr\Scripts\python.exe ..\scripts\check_task_docs.py`：报告写入前通过，输出 `task documentation gate passed: 5 gated task(s)`；状态切换后的最终结果见下方门禁记录。
- `git diff --check`：报告写入前退出码 0；仅输出混合工作区既有 LF→CRLF 提示，无空白错误。
- `Select-String -Path <本批明确源文件和文档> -Pattern '[ \t]+$'`：无匹配。
- `git status --short -- server/systems/data/calendar_memo.json`：测试前后无输出。

#### 风险、限制与工作区排除项

- legacy `POST /calendar/reset` 仍无需确认且会清除 events、skills、practice_logs；这是既定兼容风险，本批没有收紧、移除或在控制台暴露它。
- 真实历史内容兼容仅依据现有 Schema 和去标识化临时夹具验证。因为禁止读取真实文件，本报告不声明其内容已被逐项检查；若真实文件已损坏，新实现会显式报错而不会静默覆盖。
- repository 的共享路径锁只覆盖当前进程；原子替换保护单次写入，但不是跨进程文件锁。当前主 API 单进程架构没有发现实际多进程写者证据，因此不扩大实现范围。
- 未运行真实浏览器人工视觉回归：本批没有修改 dashboard HTML 或前端资产，自动 dashboard shell 回归已覆盖 calendar 关键 DOM、单一 legacy 面板、静态边界和脚本语法；未连接真实 API 或真实 calendar 状态。
- 当前分支为 `agent/intel-sources-dashboard`，混合工作区包含情报、斩妖、focus、dashboard/模块基础设施、个人状态、`vendor/` 和其他用户修改。本报告只覆盖列明的 PK-190 路径；这些排除项均未整理、覆盖、删除、暂存或提交。

### 本批完成文档门禁

- [x] TASK_RECORD — 本节已记录审阅范围、接口、数据隔离、副作用、命令、结果、风险、限制、工作区排除项和“通过”结论。
- [x] TASKS_BOARD — 独立报告提交时 PK-190、PK-900 均保持“待集成”；PK-000 最终接受后，两项已同步为“已完成”，依赖保持 `PK-190（本批次）`。
- [x] PUBLIC_README — 不适用：独立验收未改变用户可见行为、接口、配置、重启要求、数据副作用或限制；已核对现有 calendar 说明与代码一致。
- [x] MODULE_CATALOG — 已核对 calendar 的 10 条 endpoint、namespace、进程、权限、数据所有权、legacy 控制台表面和 `modular` 状态，无需修改目录字段。
- [x] ARCHITECTURE_DOCS — 已核对内置分层、兼容导出、voice provider、原子持久化与非安装边界；本轮未改变架构协议。
- [x] LOCAL_README — 不适用：本机路径、启动器、解释器、端口和环境位置均未变化。
- [x] AGENT_RULES — 不适用：未改变 agent 工作流、安全、验证、文档或 Git 规则。
- [x] VALIDATION — 已记录全部必跑测试、编译、JavaScript、文档门禁、空白检查、真实状态路径复查及未执行的浏览器视觉项；状态切换后最终复跑门禁。

### PK-000 最终复核

- 2026-07-21：PK-000 独立读取 PK-900 报告并对照当前源码、测试、目录、README、架构和任务状态；确认本轮仍是普通内置 calendar 模块化，没有 manifest、安装包、生命周期或动态面板交付。
- 新旧五组 HTTP 接口继续由同一 router/handler/service/repository 提供；voice 只使用公开、可注入的摘要 provider；legacy 控制台只有单一 calendar 面板且没有 reset 入口。版本化 reset 的精确确认和 legacy reset 的已知危险兼容均与报告一致。
- PK-000 重新运行 calendar memo/module、voice intent、feature catalog、dashboard shell 和六个公共 JavaScript 语法检查，全部通过；状态切换前文档门禁通过并输出 `task documentation gate passed: 6 gated task(s)`，`git diff --check` 与本批文档行尾检查无错误。
- 真实 `server/systems/data/calendar_memo.json` 在复核前、测试后均无状态输出；未读取、打印、diff、迁移、reset、修改、暂存或提交。所有写入证据继续限定在显式临时 store。
- PK-000 接受独立报告的“通过”结论。PK-190 与本轮 PK-900 均置为“已完成”；legacy reset 无确认、真实历史内容未逐项读取验证、进程内锁不覆盖多进程等限制继续保留，不影响当前单进程内置模块验收结论。

## PK-200 集成验收批次

### 批次登记与入场状态

- 2026-07-21：保留 `PK-010 + PK-100`、PK-180、PK-190 的完整验收和 PK-000 最终结论；本节追加独立 PK-200 批次，不覆盖或重写此前记录。
- 入场时 PK-200 为“待集成”且八项文档门禁已完成；PK-160 为“待开始”并依赖 PK-200，PK-200 自身只依赖已完成的 PK-001，循环依赖已按总控决定解除。
- PK-900 已从上一轮“已完成”重新置为“进行中”，任务总板本批依赖同步为 `PK-200（本批次）`；PK-200 保持“待集成”。
- 入场文档门禁通过，输出 `task documentation gate passed: 7 gated task(s)`。真实 `server/data/llm_profile.json`、`server/data/memories.json`、`server/data/affection_state.json` 均无 Git 状态输出；未读取内容或详细 diff。
- 当前分支仍为 `agent/intel-sources-dashboard`，工作区包含多个任务、用户状态和未跟踪内容。本批只审阅 PK-200 及必要消费者接缝，不整理、覆盖、删除、暂存或提交其他改动。

### 本批验收边界

- 独立核验 `server/features/conversation/` 的 models/context/client/repository/runtime/service/router/composition 边界，以及 `core/llm_engine.py`、`core/dialogue_manager.py`、`server/api.py` 的兼容与装配接缝；不得形成第二套 LLM 或 history 实现。
- 核验空/故障上下文 Provider、版本化 conversation/profile、新旧 chat/history/profile、legacy 控制台、catalog 和主应用装配兼容；PK-200 不得读取或拥有 PK-160 状态。
- 核验 profile 严格白名单、环境 Key 所有权、安全 URL、本机/同源写边界、上游错误净化、候选测试和原子保存/切换，以及旧 client 关闭与并发 history 竞态。
- 核验 QQ 文字转发、voice 文字阶段、每日情报、生命维持和斩妖复盘只持有同一稳定 `ConversationService`/`TextGenerator` 门面，热切换后下一次调用共同使用新活动配置。
- 所有 profile 写入只使用系统临时目录；所有 LLM 网络测试只允许 fake client、`httpx.MockTransport` 或等价完全内存传输。不得读取 `.env` 值、真实 profile、长期记忆或好感度数据，不得运行真实/付费 LLM 诊断。

### 计划执行的定向回归与门禁

- `server/.venv-asr/Scripts/python.exe server/tests/test_conversation_module.py`
- `server/.venv-asr/Scripts/python.exe server/tests/test_llm_profile.py`
- `server/.venv-asr/Scripts/python.exe server/tests/test_conversation_consumers.py`
- `server/.venv-asr/Scripts/python.exe server/tests/test_feature_catalog.py`
- `server/.venv-asr/Scripts/python.exe server/tests/test_dashboard_shell.py`
- `server/.venv-asr/Scripts/python.exe server/tests/test_demon_review_kei.py`
- `server/.venv-asr/Scripts/python.exe server/tests/test_voice_demon_intents.py`
- `server/.venv-asr/Scripts/python.exe server/tests/test_voice_calendar_intents.py`
- `server/.venv-asr/Scripts/python.exe server/tests/test_daily_briefing_summary_cache.py`
- 相关 conversation、兼容层、消费者、API 和测试的 Python 编译检查；dashboard 公共 JavaScript 的 `node --check` 与 legacy 内联脚本语法检查。
- `server/.venv-asr/Scripts/python.exe scripts/check_task_docs.py`、`git diff --check`、本批明确路径行尾空白检查，以及三条受保护状态路径的前后状态复查。

### 主动安全审阅重点与非目标

- 现有测试之外主动检查：错误体/日志是否回显 Key、Authorization、上游正文或完整 URL；URL userinfo/query/fragment；跨站 profile 写入；profile 文件与 runtime 半切换；关闭后的 client 复用；并发聊天、受控生成、清 history 和切换的共享 history 竞态。
- 不实现 PK-160、PK-210、安装包、动态面板、会话持久化、多用户、跨进程 history 或新的消费者业务；若发现上游缺陷，只在 PK-200 明确边界内判断是否阻断并记录归属，不扩大任务。
- 不启动真实 API 进行外部诊断，不调用真实 LLM、ASR、TTS、QQ 或采集服务，不执行 Git 暂存、提交、推送、PR 或工作区清理。

### 独立验收报告

#### 结论

**不通过。** 规定的九组自动测试、编译、JavaScript、目录/控制台和文档门禁均通过，依赖、接口、秘密、Provider、消费者和常规 profile 热切换契约未发现其他回归；但主动并发审阅稳定复现 `ConversationRuntime.close()` 与 chat/profile update 的客户端关闭竞态。该缺陷违反本批明确要求的“客户端关闭竞态有独立覆盖”和“已关闭客户端不得继续使用”，必须退回 PK-200 整改后复验。

PK-200 继续保持“待集成”；PK-900 因存在阻断项保持“进行中”，不进入“待集成”，等待 PK-200/PK-000 处理。

#### 阻断缺陷：关闭后的 runtime 仍接受工作

- 根因位于 `server/features/conversation/runtime.py` 的 `close()`：只在 `_operation_lock` 内取得当前 client，随后释放锁再执行 `await client.close()`；runtime 没有 `closing/closed` 状态，`ConversationService.close()` 也不与 `_update_lock` 协调。
- 纯内存 fake client 复现一：启动 `runtime.close()`，在 fake client 已进入关闭状态但 close 尚未返回时调用 `runtime.chat()`。结果为 `{"chat_calls_after_close": 1, "reply_was_fallback": true}`，进程退出 1；说明 chat 实际调用了已关闭 client，异常又被通用 fallback 吞掉并写入一对 history。
- 临时 profile + fake client 复现二：让候选 `test()` 阻塞，期间完成 `service.close()`，再释放候选测试。结果为 `{"old_closed": true, "profile_after_close": "new", "candidate_closed_after_service_close": false}`，进程退出 1；说明 service 已关闭后仍能提交新 profile，并留下一个未关闭的活动 candidate。
- 影响：关闭边界不是终态；并发请求可能静默得到网络 fallback 并污染 history，并发 profile PUT 可能在 shutdown 后落盘并复活新的 client。虽然 FastAPI 正常 shutdown 通常会等待请求，但 PK-200 的 runtime/service 公共契约本身没有保证这一点，且任务明确要求覆盖该竞态，不能据部署时序豁免。

#### 退回整改要求

- 在 runtime/service 中增加由锁保护的明确生命周期状态，使 close 与 chat、generate、probe、commit/profile update 形成同一个一致性边界；close 开始后不得再取得或提交活动 client。
- close 必须等待已进入的活动操作安全结束，再关闭恰好一次；后续 chat/generate/profile update 应确定性拒绝或使用不接触 client、且不写 history/profile 的安全结果。
- profile candidate 在 close 与候选测试并发时必须被关闭且不得 commit/落盘；service close 完成后不得留下新的活动 client。
- 增加独立回归，至少覆盖 close 与 chat、close 与受控生成、close 与阻塞候选 profile update、重复 close，以及失败路径不写 history/profile、不复用 closed client。
- 修复后重跑本节全部测试和两条主动竞态夹具，再由 PK-900 复验；PK-900 不在集成任务中代写该业务修复。

#### 其余验收结果

- 循环依赖已解除：TASKS 与 PK-160/PK-200 任务文件一致为 `PK-001 -> PK-200 -> PK-160`；conversation 默认 `EmptyConversationContextProvider` 可独立启动，模块本身不导入 MemoryStore/affection repository。
- `POST /api/v1/conversation`、版本化 history、`GET/PUT /api/v1/llm-profile` 与 `/chat`、`/chat/text-only`、`/history*`、`/ws/chat`、`/dashboard/llm/profile` 共用同一 service/runtime；版本化文字响应不包含音频。
- conversation 的 client/repository/runtime/service/router/composition 职责分离；`core/llm_engine.py` 仅兼容重导出，`core/dialogue_manager.py` 只保留 voice/旧记忆命令应用接缝，没有第二套 client 或 history。
- profile 只允许五个非秘密字段；额外字段、userinfo、query、fragment、非法 provider/thinking/URL/model 被拒绝。Key 仅由测试进程环境以虚构值注入；错误体、上游正文、日志和 profile 未发现 Key/Authorization 回显。
- 常规候选失败、上游错误、损坏 JSON、原子替换失败、候选测试期间旧模型可用、串行双切换、成功切换保留 history 和旧 client 关闭失败警告均通过；阻断仅在尚无现有覆盖的 shutdown 竞态。
- QQ legacy 文字接口、voice 的 DialogueManager、DailyBriefingService、生命维持和斩妖复盘均持有同一个稳定 service/TextGenerator；成功切换后消费者使用新模型，受控生成不写普通 chat history。
- 空、静态和故障 Context Provider 均通过；故障只输出固定安全日志并降级为空上下文。PK-200 代码未读取或拥有 PK-160 状态。
- legacy LLM 面板保持单一 DOM，请求仅发送公开 profile 字段；页面源码不访问 local/session storage，公共外壳的 localStorage 只保存 panel 布尔折叠状态。失败 PUT 不调用 `renderLlmProfile()`，不会改变当前展示方案。

#### 实际命令与结果

- `test_conversation_module.py`、`test_llm_profile.py`、`test_conversation_consumers.py`：全部通过。
- `test_feature_catalog.py`、`test_dashboard_shell.py`、`test_demon_review_kei.py`、`test_voice_demon_intents.py`、`test_voice_calendar_intents.py`、`test_daily_briefing_summary_cache.py`：全部通过。
- 上述测试进程均显式设置 `PROJECT_KEI_ENV_FILE=<不存在的临时路径>`、`PROJECT_KEI_LLM_PROFILE_PATH=<不存在的临时路径>` 和虚构 `LLM_API_KEY`。HTTP 只使用 ASGITransport、MockTransport 或 fake client；未建立真实 LLM 连接。
- 相关 conversation、API、兼容层、消费者和测试执行 `python -m py_compile`：通过。
- `node --check static/dashboard/{request,notifications,panels,registry,module-loader,app}.js`：六个文件分别通过；`test_dashboard_shell.py` 的 legacy 内联 `new Function(...)` 检查通过。
- 纯内存 close/chat 竞态脚本：按预期复现缺陷并退出 1；临时 profile close/update 竞态脚本：按预期复现缺陷并退出 1。前两次尝试用 `python -c` 传递第一段脚本时因 PowerShell 引号拆分产生 `SyntaxError`，未执行测试代码；改用标准输入后稳定复现，不影响产品结论。
- 报告写入前 `scripts/check_task_docs.py`：通过，输出 `task documentation gate passed: 6 gated task(s)`；PK-900 为“进行中”因此不计入完成门禁。
- `git diff --check`：退出码 0，仅有混合工作区既有 LF→CRLF 提示；本批明确源文件/文档行尾空白检查无匹配。
- 测试前后 `git status --short -- server/data/llm_profile.json server/data/memories.json server/data/affection_state.json` 均无输出。

#### 数据隔离、限制和工作区排除项

- 未读取或打印真实 `.env` 值、`llm_profile.json`、`memories.json`、`affection_state.json`，未查看这些文件的详细 diff；未启动应用 lifespan，因此未构造真实 MemoryStore 或加载真实 profile。
- profile repository 测试与第二条竞态复现只写系统临时目录并自动清理。LLM HTTP 错误测试只使用 `httpx.MockTransport` 和虚构 Key；未调用真实/付费 LLM、ASR、TTS、QQ、外部采集或生产写操作。
- API-import 回归记录到既有 focus runtime 目录的只读 `PermissionError`，由应用现有模块隔离逻辑跳过；不属于 PK-200 阻断，也未修改该目录。
- 当前混合工作区中的情报、calendar、focus、斩妖、个人状态、`vendor/` 及其他用户修改全部排除。未执行 Git 暂存、提交、推送、PR 或清理。

### PK-200 阻断整改复验

#### 复验结论

**通过。** 上一轮报告中的两条客户端关闭竞态已按原始时序独立复验通过，新增回归也覆盖关闭等待、重复关闭、阻塞候选、关闭后拒绝与失败不落盘。规定的九组测试、消费者回归、Python 编译、六个 dashboard JavaScript 语法检查、文档门禁和 `git diff --check` 全部通过；未发现新的 PK-200 集成阻断项。

PK-200 保持“待集成”，本轮 PK-900 改为“待集成”，交由 PK-000 最终复核；不自行把任一任务改为“已完成”。

#### 原阻断项复验结果

- `ConversationRuntime` 现在以 `_operation_lock` 保护不可逆 `_closed` 状态和唯一 `_close_task`。close 开始后 chat 被 `ConversationClosedError` 明确拒绝，不触达已关闭 client、不新增 history；并发及重复 close 只调用一次 client close。
- `ConversationService` 现在以生命周期锁协调 chat、受控生成、probe、profile update 与 close，并跟踪正在测试的候选 client。阻塞候选在 service close 时即关闭；候选测试随后返回时以 `stage=lifecycle`、`code=service_closed` 失败，不保存 profile、不切换 runtime、不遗留活动 client。
- 原 close/chat 纯内存夹具输出：`{'calls_after_close': 0, 'rejected_after_close': True, 'history_count': 0, 'close_calls': 1}`，退出码 0。
- 原 close/profile-update 临时目录夹具输出：`old_closed=True`、`profile_after_close='old'`、`candidate_closed_before_release=True`、`candidate_close_calls=1`、`profile_exists=False`、`update_error=('lifecycle', 'service_closed')`、`history_count=0`，退出码 0。
- `tests/test_llm_profile.py` 新增的 shutdown 竞态回归同时覆盖 runtime 双 close、关闭期间活动 chat 的完成顺序、关闭后 chat/generate、阻塞候选、关闭后 profile update 以及关闭失败不污染状态；本轮完整执行通过。

#### 其余契约复核

- 上一轮已通过的依赖解除、空/故障 Context Provider、版本化与 legacy API、单一 conversation/profile repository/Provider 装配、环境 Key 所有权、URL/跨站限制、错误净化、原子热切换、共享 history 和消费者统一活动配置结论继续有效；本轮整改仅收紧生命周期边界，没有引入第二套 LLM 实现或 PK-160 数据所有权。
- QQ、voice、每日情报、生命维持、复盘、提醒、catalog 和 dashboard 回归全部通过。legacy 控制台仍不保存 API Key、不把 profile 写入浏览器存储，失败切换不更新当前显示方案。
- 所有网络相关测试继续只使用 fake client、ASGITransport 或 `httpx.MockTransport`；未运行真实 LLM 诊断、付费请求或外部服务。

#### 实际命令与结果

- 两条独立竞态脚本均通过 `server/.venv-asr/Scripts/python.exe -` 从标准输入执行，并显式设置隔离环境变量；结果见上文。首次复用旧夹具时分别因已变化的构造参数和 history 方法名产生 `TypeError`、`AttributeError`，校正为当前公开契约后按相同时序通过；这些属于验收脚本适配错误，不是产品失败。
- `cd server; .\.venv-asr\Scripts\python.exe tests\test_conversation_module.py`、`test_llm_profile.py`、`test_conversation_consumers.py`、`test_feature_catalog.py`、`test_dashboard_shell.py`、`test_demon_review_kei.py`、`test_voice_demon_intents.py`、`test_voice_calendar_intents.py`、`test_daily_briefing_summary_cache.py`：九组全部退出码 0。
- `cd server; .\.venv-asr\Scripts\python.exe -m py_compile <conversation/API/兼容层/消费者/测试文件>`：通过。
- `cd server; node --check static\dashboard\request.js`、`notifications.js`、`panels.js`、`registry.js`、`module-loader.js`、`app.js`：六项通过。首次沿用错误的 `server/dashboard/*.js` 路径得到 `MODULE_NOT_FOUND`，定位实际 `server/static/dashboard/` 后全部通过；不是脚本语法失败。
- 状态切换前 `cd server; .\.venv-asr\Scripts\python.exe ..\scripts\check_task_docs.py`：通过，输出 `task documentation gate passed: 6 gated task(s)`。
- 状态切换前 `git diff --check`：退出码 0，仅输出混合工作区既有 LF→CRLF 提示，无空白错误。
- `git status --short -- server/data/llm_profile.json server/data/memories.json server/data/affection_state.json server/.env`：无输出。

#### 数据隔离、风险、限制与工作区排除项

- 所有命令显式设置 `PROJECT_KEI_ENV_FILE=<TEMP>\project-kei-pk200-integration\missing.env`、`PROJECT_KEI_LLM_PROFILE_PATH=<TEMP>\project-kei-pk200-integration\missing-profile.json` 和虚构 `LLM_API_KEY=integration-fake-key`。profile 写入夹具只使用自动清理的 `TemporaryDirectory`。
- 未读取、打印、diff、迁移、重置或修改真实 `.env`、profile、长期记忆或好感度数据；未启动真实应用 lifespan，未调用真实 LLM、QQ、voice、采集、付费接口或生产写操作。
- API-import 测试仍记录既有 focus runtime 目录只读 `PermissionError` 并由模块隔离逻辑跳过；测试断言全部通过，该现象不属于 PK-200，本轮未触碰该目录。
- 本轮未进行连接真实本地 API 的浏览器回归，以避免加载真实 profile/MemoryStore；dashboard shell 自动回归已覆盖 legacy DOM、请求净化、失败切换和 JavaScript 语法。真实上游可用性、跨进程 history、会话持久化与多用户仍为既定非目标。
- 混合工作区中的情报、calendar、focus、斩妖、个人状态、`vendor/` 和其他用户改动全部排除；未重置、覆盖、删除、整理、暂存、提交、推送或发布。

### 本批完成文档门禁

- [x] TASK_RECORD — 已保留初验“不通过”证据并追加整改复验范围、代码结论、夹具输出、命令、结果、数据隔离、风险、限制和最终“通过”结论。
- [x] TASKS_BOARD — 独立复验提交时 PK-200、PK-900 均保持“待集成”；PK-000 最终接受后两项已同步为“已完成”，依赖继续为 `PK-200（本批次）`。
- [x] PUBLIC_README — 不适用：整改只收紧既有内部生命周期并发语义，未改变用户安装、启动、配置、公开 API 或数据行为；已复核现有说明无需更新。
- [x] MODULE_CATALOG — catalog 与 conversation 的版本化/legacy endpoint、进程模型、权限和非秘密 profile 所有权回归通过，无目录字段变更。
- [x] ARCHITECTURE_DOCS — 整改未改变 modular monolith、内置 conversation、只读 Context Provider 或 installable module 边界；现有架构文档仍一致。
- [x] LOCAL_README — 不适用：未改变本机路径、解释器、端口、环境变量位置或启动器。
- [x] AGENT_RULES — 不适用：未改变 agent 工作流、安全、验证、文档或 Git 规则。
- [x] VALIDATION — 已复跑原两条阻断夹具、九组规定测试、Python 编译、六项 JavaScript、文档门禁、受保护路径状态和 `git diff --check`；最终状态切换后再执行文档门禁与差异检查。

### PK-000 最终独立复核

#### 最终结论

**通过。** PK-000 独立对照 PK-900 报告、实际源码、测试、任务依赖、README、模块目录和架构说明，确认首轮 shutdown 阻断已关闭，未发现新的接口兼容、原子切换、并发、秘密泄露或数据隔离阻断。PK-200 与本轮 PK-900 均置为“已完成”。

#### 独立代码与契约复核

- 依赖保持 `PK-001 -> PK-200 -> PK-160`；conversation 模块只认识 `ConversationContextProvider`，默认空实现可独立启动，主应用的临时 MemoryStore 适配只位于装配/compatibility 接缝。PK-160 后续无需形成反向依赖。
- `POST /api/v1/conversation`、版本化 history/profile 与 `/chat*`、`/history*`、`/ws/chat`、`/dashboard/llm/profile` 共用同一 service/runtime。QQ 继续调用 `/chat/text-only`；voice、daily briefing、生命维持提醒和斩妖复盘持有稳定 conversation/TextGenerator 门面，不缓存原始 client。
- profile repository 在活动指针替换前完成唯一临时文件、`flush/fsync/os.replace`；runtime 的操作锁覆盖 chat/generate/commit，service 的 update/lifecycle 锁覆盖候选、commit 和 close。close 进入终态后不再接受 client 工作或 profile commit。
- profile/API 只允许非秘密字段；client 将上游失败转换为固定错误码/安全短句，不返回响应正文。静态审计未发现 API Key、Authorization、角色系统提示、Provider 上下文或长期记忆进入 profile、HTTP 错误、日志或浏览器存储的路径。

#### PK-000 主动隔离复现

- 候选测试成功、profile 原子替换失败：使用真实 `LLMProfileRepository` 和注入失败的 `replace`，输出确认 `active_model=old`、`history_unchanged_at_failure=true`、`profile_file_unchanged=true`、`candidate_closed_once=true`、`old_client_still_served=true`。
- 并发切换/对话：候选测试阻塞期间并发两次 chat 均返回旧模型，profile 仍为 old 且未落盘；释放候选后提交为 new，下一次 chat 使用 new，三组 history 保持 user/assistant 成对，旧 client 只关闭一次。
- 额外取消场景：阻塞候选测试任务被取消后，候选只关闭一次，活动模型仍为 old，history 不变且 profile 文件不存在。
- 上述夹具全部只使用 fake client、虚构 Key 和 `TemporaryDirectory`，没有 socket、真实模型或外部副作用。

#### 最终验证与数据边界

- 九组规定测试全部通过：conversation module、LLM profile、conversation consumers、feature catalog、dashboard shell、demon review、voice demon/calendar intents、daily briefing summary cache。
- 23 个 conversation/API/兼容层/消费者/测试 Python 文件以内存 `compile()` 通过；六个公共 dashboard JavaScript 分别通过 `node --check`。
- 状态切换前文档门禁通过，输出 `task documentation gate passed: 7 gated task(s)`；`git diff --check` 和本批文档行尾检查无错误。
- 规定测试的 HTTP 仅使用 fake client、`httpx.MockTransport` 或 `ASGITransport`。未运行 `test_llm_debug.py`、真实 voice/chat、真实 briefing rewrite、真实/付费 LLM、ASR、TTS、QQ 或采集。
- 真实 `.env`、`llm_profile.json`、`memories.json`、`affection_state.json` 在复核前后均无状态输出，未读取内容或详细 diff，未修改、暂存或提交；混合工作区的缓存、个人状态、其他任务改动和 `vendor/` 继续排除。
- 实施早期旧 `_path_setup.py` 曾在一次测试导入时读取真实环境变量值，但没有打印、序列化、落盘或联网；该历史偏差已如实保留。修复后 PK-900 全部测试及本次 PK-000 复核均强制使用不存在的 env/profile 路径与虚构 Key。

#### 保留限制

- 未连接真实上游验证供应商可用性或计费行为；profile PUT 本身按契约会进行一次显式候选请求。
- history 仍是单用户、单 API 进程内、重启清空；跨进程 history、持久会话和多用户不在范围。
- PK-160 仍需后续提供正式只读 Context Provider；PK-210 继续拥有 ASR/TTS/音频传输。legacy 控制台保持单一面板，本批没有安装包或动态入口。

## PK-210 + PK-211 + PK-212 语音解耦集成验收批次

### 批次登记与入场状态

- 2026-07-22：保留 `PK-010 + PK-100`、PK-180、PK-190、PK-200 的全部初验、整改与 PK-000 最终结论；本节追加独立 `PK-210 + PK-211 + PK-212` 批次，不覆盖或重写此前记录。
- 入场时 PK-210、PK-211、PK-212 均为“待集成”且八项文档门禁已完成；PK-200 已完成。依赖方向为 `PK-001 + PK-200 -> PK-210 -> PK-211/PK-212`，PK-211 与 PK-212 彼此不依赖，只通过 PK-210 公共契约联调。
- PK-900 已从上一批“已完成”重新置为“进行中”，任务总板本批依赖同步为 `PK-210、PK-211、PK-212（本批次）`；三个功能任务保持“待集成”。
- 入场文档门禁通过，输出 `task documentation gate passed: 10 gated task(s)`。`server/.env`、GPT-SoVITS 本机登记、Voice Pack 本机注册表、Voice Pack runtime、模型与语音输出路径均无 Git 状态输出；未读取内容或详细 diff。
- 当前分支为 `agent/intel-sources-dashboard`，混合工作区包含多个任务、个人状态、外部参考与未跟踪内容。本批只审阅项目自有 voice/Provider/Voice Pack、必要 PK-200/API/catalog/dashboard 接缝及对应文档测试；不整理、覆盖、删除、暂存或提交其他改动。
- 已完整读取根 README、AGENTS、本机 README、TASKS、PK-210/211/212/900 任务文件、模块化单体、可安装模块、voice、Voice Pack 与 GPT-SoVITS 专项架构文档。依照 AGENTS 规则，不递归枚举、搜索、读取、索引或 diff 项目外 GPT-SoVITS 安装树，也不展开 `vendor/`。

### 本批验收边界与闭环

- 独立验证去标识化完整闭环：`假音频 -> PK-210 SpeechToTextProvider -> PK-200 ConversationService adapter -> PK-212 VoicePackRegistryService -> PK-211 GPTSoVITSProvider -> 假音频结果`。所有环节必须使用 fake、MockTransport 和系统临时目录，不启动 8000/8010/9880，不执行真实 ASR、LLM、TTS 或 GPU 推理。
- 核验 GPT-SoVITS 外部引擎、可变化 Voice Pack 与 Project Kei 语音编排三个所有权边界；Core 在引擎/Pack 未安装或未登记时仍可导入和启动，并通过 health/降级结果明确报告缺失。
- 核验 PK-211 固定官方 HTTPS 来源、release/commit/revision、精确大小和 SHA-256；受控获取只由显式 CLI 触发，失败无半安装/半登记，不接受任意 URL/命令且永不执行归档脚本。
- 核验 PK-212 多假 Pack 导入、启停/选择/注销、Provider 激活与注册表原子提交；绝对路径、穿越、链接、未知 engine、执行内容、秘密/未知字段、错误大小/摘要必须在发布前拒绝，切换失败恢复旧 Pack。
- 核验 PK-210 新旧 health/chat/stream/audio 路由共用同一 service，文字阶段只调用 PK-200，ASR/对话失败终止，TTS/Pack 失败明确文字降级；流式取消、请求临时目录和未完整发布音频按请求隔离清理。
- 主动补查恶意包、错误摘要、下载中断、安装/登记提交失败、Provider/注册表切换失败、并发导入/切换/语音请求、流生成器提前关闭和 cancellation，不仅接受三项功能任务既有报告。

### 数据、安全与非目标

- 不真实下载、clone、安装、启动或升级 GPT-SoVITS，不访问 GPU，不调用真实 9880；不执行任何归档、远程、本机安装脚本或依赖安装。
- 不读取、打开、摘要、移动、复制、上传、重命名、打包、暂存或记录真实 Kei 权重与参考音频。允许的证据仅限项目自有 descriptor/Provider/无路径状态契约、Git 状态排除和临时微型假资产。
- 不读取或打印 `.env`、LLM profile、长期记忆、好感度、真实 Voice Pack 注册表、本机引擎登记或生成音频；不启动真实应用 lifespan，不调用 QQ、采集、付费接口或生产写操作。
- GPT-SoVITS 上游源码不得进入项目、`vendor/`、任务 diff 或普通 agent 阅读范围；本批不会为了证明“不存在源码”而递归扫描 `vendor/` 或外部引擎，只审计项目自有文件清单、Git 顶层状态、忽略规则和 descriptor 边界。
- 不把 PK-210/211/212 改造成 PK-010 生命周期安装包，不新增控制台安装/下载/资产管理面板，不实现 Persona Pack、云市场、真实模型导出、自动依赖安装或新的业务语音意图。
- 不执行 Git 暂存、提交、推送、PR、发布或工作区清理。发现缺陷只判断 PK-210/211/212 或必要共享契约归属并记录；不在 PK-900 中越界重写上游业务。

### 计划执行的测试与门禁

- 定向测试：`test_voice_module.py`、`test_gpt_sovits_provider.py`、`test_voice_pack_registry.py`。
- PK-200/共享回归：`test_conversation_module.py`、`test_llm_profile.py`、`test_conversation_consumers.py`、`test_feature_catalog.py`、`test_dashboard_shell.py`，并按实际接缝补跑 voice calendar/demon intents 等必要兼容测试。
- 独立临时闭环与恶意/竞态夹具：使用 fake ASR、fake conversation 或真实 PK-200 service 的 fake client、两个以上假 Voice Pack、MockTransport GPT-SoVITS 和临时 storage/registry/acquisition 目标；严禁真实 socket 与资产。
- 对本批 Python 文件和测试运行 `py_compile`/`compileall`；对六个 dashboard 公共 JavaScript 分别运行 `node --check`，并依赖 dashboard shell 测试检查 legacy 内联脚本。
- 运行 `scripts/check_task_docs.py`、`git diff --check`、本批明确文本路径行尾检查和受保护状态路径前后复查。通过后将 PK-900 改为“待集成”，PK-210/211/212 保持“待集成”，提交 PK-000 最终复核。

### 独立验收报告

#### 结论

**不通过。** 去标识化 `假音频 -> PK-210 ASR -> PK-200 conversation -> PK-212 Voice Pack -> PK-211 GPT-SoVITS -> 假音频` 完整闭环、三项定向测试、PK-200/模块/API/catalog/dashboard 回归、编译和文档门禁均通过；正常导入、失败回滚、下载中断、摘要错误、恶意包、流式取消和请求临时清理也可复现通过。但主动安全/并发审阅稳定复现两项未被现有测试覆盖的阻断：

1. Voice Pack 本机写路由接受恶意浏览器 Origin，并在主应用 `CORS *` 下实际修改注册表状态；
2. GPT-SoVITS 两阶段权重切换在取消时不回滚，且合成没有持有共享权重租约，另一 Pack 可在前一请求合成期间改写引擎权重。

这两项分别违反“本机显式写操作”以及“Voice Pack 原子切换、失败回滚、所有消费者保持旧 Pack 完整可用”的批次契约。PK-210、PK-211、PK-212 继续保持“待集成”；PK-900 保持“进行中”，不进入“待集成”，等待上游整改和原夹具复验。

#### 阻断一：Voice Pack 写接口可被跨站网页调用

- 根因：`server/features/voice/voice_packs/router.py` 的 `_require_local()` 只检查 `request.client.host`，没有复用 `server/api.py` 已存在的本机 Origin 控制；主应用同时配置 `CORSMiddleware(allow_origins=["*"], allow_methods=["*"])`，因此浏览器跨站请求不仅会发送，响应也明确允许任意 Origin。
- 纯 ASGI 临时注册表夹具先导入、启用并选择 `origin-pack@1.0.0`，随后从本机 client 地址携带 `Origin: https://evil.example` 调用无请求体的 `POST /api/v1/voice-packs/origin-pack/1.0.0/disable`。结果为 `status_code=200`、`access-control-allow-origin=*`、Pack 变为 `enabled=false`、活动 ID 变为 `null`；断言应返回 403，因此夹具退出 1。
- 影响：任意网页可在用户浏览时对可猜测的本机 Pack ID 发起 enable/select/disable 等状态写入；CORS 还允许读取结果。导入需要 JSON body，但其余无 body 的 POST 已足以改变活动声音。仅限制远端 TCP client 不能构成本机控制写的浏览器安全边界。
- 归属：PK-212 路由与主应用装配接缝。整改应像 conversation profile 一样注入统一 `local_control_guard`，校验本机 client 与允许的 8000 同源 Origin，并增加恶意 Origin 回归；不能只依赖浏览器预检或全局 CORS 偶然行为。

#### 阻断二：共享 GPT-SoVITS 权重不是原子切换边界

- 根因一：`GPTSoVITSProvider.activate_voice_pack()` 只在两个权重设置请求期间持有 `_pack_switch_lock`，但 `except asyncio.CancelledError` 直接重新抛出，不执行旧 Pack 回滚。若取消发生在 GPT checkpoint 成功、SoVITS checkpoint 尚未完成时，外部引擎进入混合权重状态，而 Provider 的 `_active_voice_pack` 仍指向旧 Pack。
- 纯 MockTransport 夹具先激活 `old`，让 `new` 的 GPT 权重请求成功并阻塞 SoVITS 权重请求，再取消切换。结果为 `provider_identity=old`、假引擎 `gpt=new.ckpt`、`sovits=old.pth`，且取消后没有旧权重恢复请求；断言旧两项权重应完整保留，因此夹具退出 1。
- 根因二：`_synthesize_provider()` 只在调用 `activate_voice_pack()` 时短暂取得切换锁，随后释放锁再发送合成 POST。Pack A 的合成 POST 阻塞期间，Pack B 能完成两项权重切换；夹具输出 `a_request_done=false`、`active_while_a_inflight=b`、引擎权重为 `b.ckpt/b.pth`。
- 影响：取消、并发 Pack 选择或不同 Pack 的合成请求可能让注册表活动 ID、Provider 内存身份与外部引擎实际权重不一致；正在合成的请求可能使用另一 Pack 的部分或全部权重。PK-212 的 registry 保存回滚无法恢复一个已经半切换或正在被并发改写的 PK-211 引擎。
- 归属：PK-211 Provider 的共享引擎并发/取消边界，及 PK-212 select 与 activator 的事务集成。整改至少需要让“确认/切换 Pack + 完整合成”共享同一权重使用租约或等价串行化边界；取消也必须在受保护的唯一任务中恢复旧 GPT/SoVITS 两项权重并报告恢复失败。PK-212 应为 select cancellation 和合成并发增加集成回归，不能只覆盖普通 `Exception`。

#### 通过的闭环与契约

- 完整假闭环使用真实 `ConversationRuntime/ConversationService`、fake LLM client、fake ASR、临时 `VoicePackRegistryService`、两个微型假 Pack、真实 `GPTSoVITSProvider` 与 `httpx.MockTransport`。结果为 `mode=audio`、假 WAV 成功发布、PK-200 调用一次、活动 Pack 为 `fake-kei-a@1.0.0`、临时 profile 未写入；Provider 请求顺序为 `/set_gpt_weights`、`/set_sovits_weights`、`/`。
- GPT-SoVITS 引擎、Voice Pack 与 voice 编排代码所有权清晰：PK-210 只消费协议，PK-211 不拥有注册表，PK-212 不拥有引擎来源/安装，voice 文字阶段只调用 `ConversationServiceProvider -> PK-200 ConversationService.chat()`；未发现第二套 LLM client/profile/history。
- 在 TTS Provider 缺失、注册表文件不存在的夹具中，health 明确返回 `tts_unavailable` 与 `voice_pack_unconfigured`，整体仍可提供 ASR+conversation，chat 返回 `mode=text_only/degraded=true`，未创建空注册表。模块导入和 app 路由回归没有 Provider 网络或安装副作用。
- PK-211 的生产 CLI 不接受 URL、Git URL、命令、脚本或额外启动参数；descriptor 固定官方 HTTPS repository、release/commit/revision、精确大小和 SHA-256。错误摘要、下载中断、不安全归档、非空目标、解包失败和本机配置提交失败均不留下目标或登记；归档中的假 `install.ps1` 只作为普通文件展开，sentinel 未创建且 marker 为 `scripts_executed=false`。
- PK-212 正常路径可导入多个假 Pack、启用和选择；Provider 普通异常与注册表 `os.replace` 失败会恢复旧活动 ID。绝对/盘符/反斜杠/`..` 路径、符号链接、未知 engine/schema、错误大小/摘要、重复 ID、执行文件和 `install_command` 未知字段均被拒绝，失败不注册；API 列表不返回绑定或根路径。
- PK-210 新旧同步/流式/audio/health 路由共用一个 `VoiceService`。ASR/对话失败终止，TTS/Pack 缺失或失败明确文字降级；流式顺序、唯一终止、生成器提前关闭、合成取消、分段半失败、上传类型/大小、有界读取、并发请求文件隔离和临时清理均通过。
- README、AGENTS、TASKS、模块目录、模块化单体、可安装模块、voice、Voice Pack 和 GPT-SoVITS 专项文档与除上述阻断外的实现一致。AGENTS 明确外部引擎默认不扫描；项目自有 descriptor/Provider/task diff 中没有上游源码。本轮只列出 `vendor/` 一级目录名 `openclaw-qqbot`，未进入或读取其源码；`vendor/` 是既有未跟踪排除项，不属于本批 diff。

#### 实际命令与结果

- `cd server; .\.venv-asr\Scripts\python.exe tests\test_voice_module.py`、`test_gpt_sovits_provider.py`、`test_voice_pack_registry.py`：三项全部通过。
- `test_conversation_module.py`、`test_llm_profile.py`、`test_conversation_consumers.py`、`test_installable_modules.py`、`test_feature_catalog.py`、`test_dashboard_shell.py`、`test_voice_calendar_intents.py`、`test_voice_demon_intents.py`、`test_daily_briefing_summary_cache.py`：九项全部通过。API import 测试仍只记录既有 focus runtime 目录的受限 `PermissionError` 并由模块隔离逻辑跳过，不影响断言。
- 完整假音频闭环脚本：退出码 0，使用临时 profile/registry/runtime/output、fake ASR/fake LLM/MockTransport TTS；未建立 socket。
- 缺引擎/缺 Pack 状态与降级脚本：退出码 0，返回 `tts_unavailable`、`voice_pack_unconfigured` 和 `text_only`，不存在的 registry 保持未创建。
- 恶意 Origin 脚本：按预期复现阻断并退出 1；两阶段取消/并发共享权重脚本：按预期同时复现半切换与合成期间切换并退出 1。两者仅使用临时微型 Pack、内存状态和 ASGI/MockTransport。
- `cd server; .\.venv-asr\Scripts\python.exe -m py_compile <features/voice 全部 Python + api/兼容导出/12 个相关测试>`：通过。
- `node --check static\dashboard\request.js`、`notifications.js`、`panels.js`、`registry.js`、`module-loader.js`、`app.js`：六项通过；dashboard shell 内联 legacy 脚本检查也通过。
- PowerShell AST 解析 `server/scripts/start_gptsovits.ps1`：通过；未执行该启动器。
- 报告写入前 `server/.venv-asr/Scripts/python.exe scripts/check_task_docs.py`：通过，输出 `task documentation gate passed: 9 gated task(s)`；PK-900 为“进行中”所以不计入完成门禁。
- 报告写入前 `git diff --check`：退出码 0，仅有混合工作区既有 LF→CRLF 提示；本批明确 `.py/.js/.json/.md` 路径行尾检查无匹配。

#### 数据隔离、风险、限制与工作区排除项

- 全部测试进程显式使用不存在的临时 env/profile/Voice Pack registry 路径与虚构 `LLM_API_KEY`；所有写入限定在 `TemporaryDirectory` 或系统临时测试目录并自动清理。
- 未读取、打印、diff、迁移、摘要、移动、复制、上传、打包、重置或修改真实 `.env`、LLM profile、长期记忆、好感度、GPT-SoVITS 本机登记、Voice Pack 本机注册表、runtime Pack、模型、权重、参考音频或生成音频。上述受保护路径测试前后均无 Git 状态输出。
- 未递归枚举、搜索、读取、索引或 diff 项目外 GPT-SoVITS 安装树；未执行真实下载、clone、7z、依赖安装、启动器、GPU、8000/8010/9880、真实/付费 LLM、ASR、TTS、QQ、采集或生产写操作。
- 真实 7z 获取、真实 9880 权重切换兼容和真实 Kei `existence_only` 资产仍未执行；这些既有现实集成限制不能替代本轮已由 MockTransport 证明的并发阻断。自动测试通过也不能豁免跨站写和半切换状态。
- 混合工作区中的情报、calendar、focus、斩妖、个人状态、`vendor/` 及其他用户改动全部排除；未重置、覆盖、删除、整理、暂存、提交、推送、PR 或发布。

#### 退回整改与复验要求

- PK-212：所有 `/api/v1/voice-packs/*` 写操作必须同时验证本机 client 和允许的本机控制台 Origin；新增恶意 Origin 对 import/enable/select/disable/unregister 的独立回归，并核对主应用 CORS 下仍不能跨站写。
- PK-211：权重切换的 cancellation 必须回滚到完整旧 Pack，且回滚过程本身不可被同一取消打断；记录/报告恢复失败但不得声称旧 Pack 可用。Pack 激活与使用共享权重进行合成必须形成一致的租约/锁边界，禁止其他 Pack 在请求结束前切换。
- PK-212/PK-211 集成：增加 select 与并发 synthesize、select cancellation、两阶段第二步失败/取消、旧 Pack 恢复失败、并发两个不同 Pack 请求的确定性覆盖；注册表活动 ID、Provider 内存身份和假引擎两项权重必须始终一致或明确进入不可用状态。
- 整改后由 PK-900 复跑本节两条原始失败夹具、完整假闭环、三项定向测试、全部共享回归、编译/JS/文档门禁和受保护路径检查。阻断关闭前 PK-900 不得改为“待集成”。

### PK-211/PK-212 共享引擎整改交接（待 PK-900 独立复验）

- 2026-07-22：上游功能对话已针对本报告“阻断二”完成整改；本节只登记待复验交接，不构成 PK-900 通过结论。PK-210、PK-211、PK-212 继续保持“待集成”，PK-900 继续保持“进行中”。跨站 Origin 阻断不属于本次共享引擎整改结论，仍按本报告原要求单独跟踪。
- 2026-07-22：PK-212 已通知“阻断一”跨站 Origin 整改就绪：全部 Voice Pack 写路由复用本机+受信 Origin guard，并在通配 CORS 外层拦截恶意写预检；独立临时 Registry/假包测试覆盖五类写接口、合法/恶意/缺失 Origin、远端客户端及 POST/DELETE OPTIONS。PK-212 保持“待集成”，请 PK-900 重跑原 ASGI 恶意 Origin 夹具后独立给出复验结论。
- 线性化边界：唯一 `GPTSoVITSProvider` 的共享引擎会话现在覆盖“锁内重新确认 Registry 活动 Pack -> 必要的 GPT/SoVITS 两阶段切换 -> 完整合成 POST”；Registry `select()` 把活动 ID 原子保存作为同一 Provider 会话的 commit。没有增加第二套 GPT-SoVITS、client、进程或端口。
- 回滚边界：权重请求、Registry commit 的失败或 `asyncio.CancelledError` 都在会话释放前执行不可由同一次取消打断的旧 GPT/SoVITS 恢复，再传播原失败/取消。回滚失败清除 Provider 活动身份并公开 `tts_engine_state_unknown`；Registry list/health/resolve 同步隐藏旧活动 ID并返回 `voice_pack_engine_state_unknown`，不得继续合成，直至完整成功选择恢复。
- 关闭边界：Provider close 先进入 closing，取消排队/活动切换与合成，等待切换回滚或合成任务退出，取得共享会话后才关闭唯一 HTTP client；重复 close 复用同一 close task。
- 上游新增 `tests/test_gpt_sovits_engine_sessions.py`，仅使用 `httpx.MockTransport`、临时 Registry、微型假 checkpoint/假 WAV 和假路径，覆盖原两阶段取消与合成中切换时序，以及第二阶段失败回滚、回滚失败、双 Pack 并发合成、重复选择、close 竞态和失败后旧 Pack 合成。上游完整 13 组测试、54 文件 Python 编译、六项 JavaScript 与 PowerShell AST 已通过；PK-900 仍须使用本报告原始竞态夹具独立重放，不得只接受上游新测试。

### PK-211/PK-212 阻断整改独立复验（2026-07-22）

#### 结论

**通过。** PK-900 没有只接受上游任务记录：已重新审阅 Voice Pack 路由、中间件、主应用装配、Registry/Provider 事务边界和新增夹具，并使用临时假 Pack、临时 Registry、真实项目 Provider/Service、ASGITransport 与 `httpx.MockTransport` 独立重放原两条失败时序。恶意 Origin 无法再修改 Voice Pack；两阶段取消能够恢复完整旧权重；完整合成持有共享引擎会话，其他 Pack 选择和合成必须等待；Registry ID、Provider 身份和假引擎权重保持一致，或在回滚失败时共同进入明确的 unknown/unavailable 状态。原两个阻断均已关闭。

PK-210、PK-211、PK-212 继续保持“待集成”，未由 PK-900 改成“已完成”；PK-900 本轮改为“待集成”，提交 PK-000 最终复核。

#### 阻断一复验：Voice Pack 跨站写入

- `VoicePackOriginGuardMiddleware` 位于通配 CORS 外层，覆盖 `/api/v1/voice-packs` 的 POST/PUT/PATCH/DELETE 以及声明这些写方法的 OPTIONS；路由内五类写接口又复用同一个本机 client + 受信 Origin guard，形成装配层与业务路由双重检查。
- 独立临时 ASGI 夹具对 import/enable/select/disable/unregister 逐项发送 `Origin: https://evil.example`，全部返回 403，临时 Registry 原始字节逐次保持不变；恶意 POST/DELETE 预检同样返回 403 且没有 `access-control-allow-origin`。
- `http://127.0.0.1:8000`、`http://localhost:8000` 的本机控制台 Origin 可正常写入；本机无 Origin 的脚本/CLI 调用保持兼容；非本机 client 即使无 Origin 仍为 403；跨站只读 GET 与 GET 预检保持兼容。
- 原失败条件“本机 client + 恶意 Origin + 无 body disable”已被上述夹具覆盖，不再返回 200，也不会改变 enabled/active 状态。

#### 阻断二复验：共享权重原子切换与合成租约

- 两阶段切换在新 GPT 成功、新 SoVITS 阻塞时取消，Provider 会在释放共享会话前用受保护 rollback task 恢复旧 GPT 与旧 SoVITS，再传播 `CancelledError`；复验得到假引擎 `pack-a.ckpt/pack-a.pth`、Registry `pack-a@1.0.0`、Provider `ready/pack-a@1.0.0`。
- 第二阶段普通失败会恢复旧 Pack，随后旧 Pack 仍能合成；若回滚自身失败，Provider 清除活动身份并返回 `tts_engine_state_unknown`，Registry list/health/resolve 同步隐藏旧活动 ID并返回 `voice_pack_engine_state_unknown`，没有半切换假成功。
- Pack A 的完整合成 POST 阻塞时，选择 Pack B 保持等待且引擎仍为 A；A 完成后才允许切换到 B。两个不同 Pack 的并发合成按共享会话串行执行，各自输出对应 checkpoint；重复选择同一 Pack不重复请求权重端点。
- Provider close 与正在切换/合成的任务竞态通过：切换先完成必要回滚，合成任务被取消，唯一 client 在共享会话退出后关闭，最终状态为 closed。
- 另加锁顺序探针，在 Provider 合成会话重新确认活动 Registry 的同时并发发起 Registry select；夹具输出 `lock_order_deadlock=false`，未发现整改引入的 Provider/Registry 锁互相等待。

#### 完整闭环与回归

- 独立完整闭环使用 `FakeASR`、真实 `ConversationRuntime/ConversationService` 与 fake LLM client、临时 `VoicePackRegistryService`、两个微型假 Pack、真实 `GPTSoVITSProvider` 和 `MockTransport` 假 9880。`假音频 -> 假识别文本 -> PK-200 -> 活动 pack-a -> GPT/SoVITS 两项假权重 -> 假 WAV` 通过，输出 `fake_full_voice_chain=passed`；所有 profile、Registry、runtime、临时音频均位于 `TemporaryDirectory`。
- 定向复验：`test_voice_pack_origin_guard.py`、`test_gpt_sovits_engine_sessions.py`、`test_gpt_sovits_provider.py`、`test_voice_pack_registry.py`、`test_voice_module.py` 全部退出 0。
- 共享回归：`test_conversation_module.py`、`test_llm_profile.py`、`test_conversation_consumers.py`、`test_installable_modules.py`、`test_feature_catalog.py`、`test_dashboard_shell.py`、`test_voice_calendar_intents.py`、`test_voice_demon_intents.py`、`test_daily_briefing_summary_cache.py` 全部退出 0。conversation/API 装配测试仍只输出既有 focus runtime 权限隔离提示，不影响断言。
- `features/voice` 全部 Python、`api.py` 和五个相关语音测试执行 `py_compile`：通过。六个 dashboard 公共 JavaScript 分别执行 `node --check`：通过。`start_gptsovits.ps1` 只执行 PowerShell AST 解析：通过，未运行启动器。
- 批量回归时曾误把既有真实诊断脚本 `tests/test_tts_gptsovits.py` 纳入命令；它立即输出 `GPT-SoVITS service is not available.` 并退出，未获得真实音频、未启动引擎、未执行权重切换或产生状态写入。该脚本违反本批 fake-only 测试边界，已明确排除且未再次运行；正式结论只依据上述 MockTransport/临时夹具和规定回归。

#### 数据隔离、风险与工作区排除项

- 全部成功验收夹具只使用系统临时目录、微型假 checkpoint/假 WAV、临时 Registry、fake LLM client 与 MockTransport；未读取或修改真实 `.env`、LLM profile、长期记忆、好感度、GPT-SoVITS 本机登记、Voice Pack 本机注册表、runtime Pack、权重、参考音频或生成音频。
- 受保护路径 `server/.env`、`server/data/gpt_sovits_engine.local.json`、`server/data/voice_pack_registry.local.json`、`server/runtime/voice_packs`、`server/output`、`server/models` 的定向 Git 状态为空。
- 未递归进入外部 GPT-SoVITS 或 `vendor/`，未下载、安装、执行脚本、启动 8000/8010/9880、调用付费 LLM、真实 ASR/TTS、QQ、采集或生产写操作。真实 9880 与真实 Kei 权重兼容仍属于未执行的本机人工限制，不影响本轮用项目契约和 MockTransport 关闭原竞态阻断。
- 当前分支为 `agent/intel-sources-dashboard`，工作区包含大量既有任务和用户修改；本轮只改 PK-900 任务记录与 `TASKS.md` 状态，不重置、覆盖、删除、整理、暂存、提交或推送任何内容。

### PK-000 最终独立复核（2026-07-22）

**通过。** PK-000 独立复现并审阅当前源码、测试与实际差异后，接受本轮 PK-900 报告。PK-210、PK-211、PK-212 与本轮 PK-900 均置为“已完成”。

- 无引擎、无 Voice Pack、错误摘要和离线状态下 Core 可启动并提供明确文字降级；完整 fake 链路仅经 ASR、PK-200 Conversation、Voice Pack 与 TTS Provider 契约协作，使用 `MockTransport`，未访问真实服务或上游内部代码。
- 路径穿越、绝对/盘符/反斜杠路径、符号链接和脚本文件均被拒绝；错误引擎摘要不会安装、登记或执行归档内容；Voice Pack 两阶段切换失败会恢复旧 Pack。
- 5 个语音专项测试和 9 个共享回归测试全部通过；测试使用 fake 与临时目录，不读取真实权重、参考音频、注册表或个人状态。
- 语音模块差异中没有上游源码、权重、参考音频、归档或秘密，`vendor/` 未出现 GPT-SoVITS；公开 README 与语音架构文档未包含真实本机引擎/资产路径。本机注册表、运行时 Pack、缓存及其他任务数据未纳入本批。
- PK-200 的 LLM Provider/Profile 与 Voice Pack Schema、注册表和切换保持独立；AGENTS.md 已明确普通任务默认不扫描外部引擎源码。
- 状态同步后 `scripts/check_task_docs.py` 通过并输出 `task documentation gate passed: 10 gated task(s)`；`git diff --check` 退出码 0，仅有混合工作区既有换行提示；受保护状态路径复查无输出。
- 未连接真实 9880、未加载真实 Kei Voice Pack、未执行真实下载；这些均按批次契约使用 fake/模拟下载覆盖，不构成基础设施验收阻断。

#### 本批八项文档门禁

- [x] TASK_RECORD — 保留初验“不通过”及原始失败证据，并追加本节独立复验范围、代码结论、夹具、命令、结果、隔离、限制和最终“通过”结论。
- [x] TASKS_BOARD — PK-000 最终复核通过后，PK-210/211/212 与本轮 PK-900 已同步为“已完成”；标题、优先级和依赖不变。
- [x] PUBLIC_README — 已核对 Voice Pack Origin 双重写保护、共享引擎会话、取消/失败回滚和 unknown 语义与实现一致；本轮验收未产生新的用户行为变更，无需再改 README。
- [x] MODULE_CATALOG — 模块身份、endpoint、进程边界和迁移状态未变；相关 catalog 回归通过，无目录修改。
- [x] ARCHITECTURE_DOCS — 已核对 `voice-packs.md`、`gpt-sovits-engine.md` 与 `voice.md` 的同源写保护、事务提交、共享合成租约、回滚和 unknown 状态与实现一致。
- [x] LOCAL_README — 不适用：没有更改或确认新的本机路径、端口、启动器、解释器或环境位置；未读取真实本机登记内容。
- [x] AGENT_RULES — 不适用：未改变工作流、安全、验证、文档或 Git 规则。
- [x] VALIDATION — 已记录两条原阻断复验、完整假闭环、定向/共享回归、Python/JavaScript/PowerShell 检查和受保护路径状态；状态切换后 `scripts/check_task_docs.py` 通过 10 个 gated tasks，`git diff --check` 退出 0（仅既有 LF→CRLF 提示），本批明确路径行尾检查无匹配。

## PK-110 集成验收批次（2026-07-22）

### 批次登记与边界

- 验收对象仅为 PK-110 的 Collector `1.0` 公共契约、LegacyCollectorGateway、规范化/汇总/去重、来源覆盖、当天缓存与补采冷却、PK-200 Kei 改写、PK-210 播报委托、新旧 briefing/dashboard 接口和 PK-140 只读缓存接缝。
- 本批不实施 PK-115/120/130/131/132/133/134/140，不修改具体 Collector 平台规则、来源配置 UI、QQ 定时器、PK-200/PK-210 内部实现，也不读取或迁移真实缓存、来源名单或凭证。
- 独立验收必须只使用 fake Collector、fake conversation、fake voice、固定 aware 时钟和系统临时目录；普通缓存读取、控制台状态和 QQ `fetch=false` 必须证明零 Collector、零 LLM、零 TTS。
- 主动夹具必须覆盖缓存原子写失败、并发刷新、跨天播报稿、缺失来源补采冷却和 prompt injection；论文合并必须保留 arXiv/Crossref/Semantic Scholar 来源身份与 coverage/warning。
- 入场时 PK-110 为“待集成”，PK-900 已由上一批“已完成”重新置为“进行中”。当前分支 `agent/intel-sources-dashboard` 含大量既有任务和用户修改；本批只按明确路径审阅，不清理、覆盖、暂存、提交或推送。

### 计划测试与门禁

- 定向：`test_daily_briefing_module.py`、`test_daily_briefing_summary_cache.py`。
- 共享：`test_intel_source_config.py`、`test_conversation_consumers.py`、`test_voice_module.py`、`test_feature_catalog.py`、`test_dashboard_shell.py`；按实际 QQ 缓存接缝补充只读代码/语法检查。
- 对 PK-110 模块、兼容接缝、API/catalog 和相关测试运行 Python 编译检查；对 dashboard/QQ 相关 JavaScript 运行 `node --check`。
- 最终运行 `scripts/check_task_docs.py`、`git diff --check`、本批明确文本路径行尾检查和受保护缓存/来源配置路径 Git 状态复查。通过后 PK-900 改为“待集成”，PK-110 保持“待集成”等待 PK-000；不通过则 PK-900 保持“进行中”并记录退回项。

### 独立验收报告

#### 结论

**不通过。** Collector `1.0` 基础模型、LegacyCollectorGateway 八类映射、论文来源身份、普通只读零外部调用、强制刷新、缓存原子替换、刷新串行化、补采冷却、跨天清理、PK-200/PK-210 委托、新旧 API、QQ 缓存接缝以及规定回归均通过。但是主动夹具稳定复现三项现有测试没有覆盖的 PK-110 阻断：

1. 到期补采再次失败后，coverage/warning 和主缓存内容摘要已经变化，但同一次响应仍返回旧 Kei 播报稿；紧接着重读缓存又因 digest 不匹配而没有播报稿，响应与持久化状态不一致。
2. Collector `1.0` 公共边界没有统一清洗 `warnings` 和 URL query 中的凭证形态；未来 Collector 返回虚构 Authorization/Cookie/token 时，值会进入缓存、HTTP 响应和 PK-200 prompt。
3. Legacy `gather_all_intel` 在 LegacyCollectorGateway 有机会清洗 warning 前，直接把论文来源原始异常正文写到 stdout；虚构秘密稳定进入日志。

三项分别违反“总结复用/补采后的缓存一致性”“外部内容按不可信输入处理”“缓存、响应、prompt、日志不含 Token/Cookie/完整错误体”的 PK-110 契约。PK-110 继续保持“待集成”；PK-900 保持“进行中”，等待上游整改和原夹具复验。

#### 阻断一：失败补采后旧播报稿与新主缓存不一致

- 根因位于 `features/daily_briefing/service.py`：`_merge_patch()` 只有结果替换了条目、`changed=True` 时才清空 `document.script`；补采再次失败时虽然会更新 `patch_attempts`、coverage、warning、`updated_at` 和 plain text，但保留从旧 summary cache 加载的 script。随后 `_rewrite()` 遇到 `document.script and not refresh` 直接复用旧稿。
- 固定时钟临时夹具先生成 `github: first failure` 主缓存和一次 fake PK-200 播报稿；31 分钟后令到期补采返回 `github: second failure`，再以 `rewrite=true` 生成。结果为 `generator_calls=1`、本次响应 `patched_has_script=true`；随后 `service.read()` 因新主缓存 digest 与旧 summary digest 不同得到 `reread_has_script=false`，输出 `same_response_and_cache=false` 并退出 1。
- 影响：同一个补采请求的返回值不可由随后只读缓存复现；控制台/QQ 可能在一次请求看到过期稿，下一次又突然没有稿。失败状态虽写入 coverage，但播报稿没有同步反映新的来源失败，违反“来源失败不能丢失或被描述为无内容”的播报一致性。
- 归属：PK-110 service/repository summary 契约。整改应在条目、coverage、warning 或 plain text 的摘要发生变化时统一失效旧 script/summary，并根据 `rewrite` 明确重写或回退；写入成功后的响应必须与立即重读的 document/script 一致。

#### 阻断二：Collector warning 与 URL query 凭证穿过冻结公共边界

- `models.py` 的 `CollectorResult.__post_init__()` 目前只规范空白并截断 warning；`IntelItem.normalize_url()` 拒绝 userinfo 但原样保留 query。Legacy gateway 的 `_warning_text()` 会清洗自己的 warning，但未来 `ContractCollectorGateway` 返回的标准 `CollectorResult` 不经过同一清洗。
- 独立 fake Collector warning 为 `Authorization=Bearer warning-secret-123; Cookie=warning-secret-123`。生成后夹具输出 `warning_secret_leak={'cache': True, 'prompt': True, 'response': True, 'system': False}`：虚构秘密同时进入临时主缓存、`public_result()` 和 `UNTRUSTED_DAILY_BRIEFING_DATA`，夹具退出 1。
- 另一 fake item URL 为 `https://example.test/doc?token=url-secret-123&view=1`，输出 `url_query_secret_leak={'cache': True, 'prompt': True, 'response': True}`。metadata 的现有键清洗不能覆盖 warning 和 URL query。
- 影响：冻结契约把秘密清洗责任留给每个未来来源实现，与“后续来源只实现公共契约、不需要了解 PK-110 内部”“PK-110 将外部内容视为不可信”“缓存、响应和 prompt 不保存凭证”不一致。仅在 system prompt 声明不执行外部指令，不能阻止凭证文本被持久化或发给模型。
- 归属：PK-110 models/contract normalization 与 prompt/public/cache 出口。整改需要冻结、复用统一的有限文本/URL/query 脱敏规则，并对 warning、URL、coverage detail 等所有公开外部文本入口建立独立回归；不能要求后续 Collector 了解 Legacy gateway 的私有 `_warning_text()`。

#### 阻断三：Legacy gateway 清洗前日志泄露原始异常

- `server/intel/briefing.py` 的 arXiv、Crossref 和 Semantic Scholar 异常分支直接将 `Exception` 正文插入 `print()` 和 `_warnings`。PK-110 的 LegacyCollectorGateway 只能在 `gather_all_intel()` 返回后清洗 `_warnings`，无法撤回已经写出的 stdout。
- 纯内存夹具临时替换 arXiv fetch 为抛出 `RuntimeError('collector-log-secret-123')` 的 fake 函数，并传入不含个人数据的空来源快照。输出为 `legacy_log_secret_leak=true warning_contains_secret=true`，夹具退出 1；未调用任何网络或真实 Collector。
- 影响：即使 API 响应和缓存最终经过 `_warning_text()`，上游错误体中的 Token、Cookie、URL query 或个人标识仍可能先进入 API 日志。该问题位于 PK-110 明确负责的 `server/intel/briefing.py` legacy gateway 接缝，不需要修改任何具体 Collector。
- 归属：PK-110 LegacyCollectorGateway/legacy gather 接缝。整改应让 legacy gather 日志只包含来源 ID、有限错误码/异常类型等非秘密状态；原始异常对象不得进入 stdout 或持久化 warning。

#### 已通过的契约与主动夹具

- `features.daily_briefing.__init__` 公开导出 Collector/CollectorGateway、CollectRequest/CollectorResult/IntelItem、coverage/cache 枚举和 `1.0` 版本；同 major 忽略未知字段，缺必填/不兼容 major 拒绝单源，future source ID 可形成 `not_configured`。未来来源无需导入 gateway/service/repository。
- 当前 twitter/github/bilibili/youtube/money/arxiv/crossref/semantic 均由 LegacyCollectorGateway 按 source ID 隔离映射；论文 legacy 调用因既有全局 tracker 串行，其他来源并发。PK-110 没有修改 `server/intel/collectors/*`；工作区中 twitter/bilibili Collector 的既有修改明确排除。
- arXiv/Crossref/Semantic Scholar 假论文汇入 `papers` 后按 DOI/标题去重，`metadata.discovery_sources` 保留全部发现来源，coverage/warning 仍按三个真实 source ID 独立存在，合并 stable ID 不依赖返回顺序。
- 普通 `GET /api/v1/briefing/today`、legacy `GET /briefing/today`、`GET /dashboard/briefing/status` 和 QQ `fetch=false&rewrite=true` 均在 fake gateway/generator/voice 计数器下保持零 Collector、零 PK-200、零 PK-210；QQ bridge 文本意图、按钮和定时 send 都调用缓存读取，只有 scheduler prebuild 显式 `fetch=true`。
- 独立主动夹具通过：两个并发 `refresh=true` 被唯一 mutation lock 串行，`calls=2/max_active=1`，最终 JSON 完整且缓存与最后响应一致；`os.replace` 失败保留旧目标字节并清理临时文件；跨天 read 删除旧 summary 且不调用 fake PK-200；失败来源在 30 分钟前不补采，到期后只补该来源。输出 `atomic_concurrent_crossday_cooldown=passed`。
- 正常/异常/超时/空 fake PK-200 生成分别得到 generated 或明确 fallback；普通同日读取不重复生成，`rewrite_refresh=true` 才重写。title/summary prompt injection 被放在 `UNTRUSTED_DAILY_BRIEFING_DATA` user 区而不进入 system，字段与总 prompt 有界；除上述 warning/URL 凭证缺口外，metadata 秘密键不会进入 prompt。
- legacy voice 和 `PK210BriefingVoiceProvider` 只依赖 PK-210 TTS/Resolver/ArtifactStore 契约；fake TTS 成功返回同源 URL，缺失/失败返回 `audio_available=false/mode=text_only/degraded=true`，音频路径不写入 briefing cache。
- 版本化 GET/generate/refresh/script、legacy today/voice 和 dashboard status/generate 共用同一 core/facade；catalog 登记与架构文档一致。PK-140 尚未迁移，但现有 QQ bridge 只通过公开 HTTP API 读取当天缓存，不解析 JSON。

#### 实际命令与结果

- `cd server; .\.venv-asr\Scripts\python.exe tests\test_daily_briefing_module.py`、`test_daily_briefing_summary_cache.py`：通过。
- `test_intel_source_config.py`、`test_conversation_consumers.py`、`test_voice_module.py`、`test_feature_catalog.py`、`test_dashboard_shell.py`：通过；API/consumer 测试仅输出既有 focus runtime 权限隔离提示，不影响断言。
- 独立失败补采/摘要一致性夹具：按预期稳定失败并退出 1；fake warning 凭证夹具、fake URL query 凭证夹具、fake legacy 异常日志夹具均按预期稳定失败并退出 1。所有秘密字符串均为本轮硬编码虚构值。
- 独立缓存原子写、并发强刷、跨天 summary 和补采冷却组合夹具：退出 0，输出 `atomic_concurrent_crossday_cooldown=passed`。
- `features/daily_briefing` 全部 Python、`services/daily_briefing.py`、`intel/briefing.py`、`api.py`、catalog 和七个相关测试执行 `py_compile`：通过。
- `node --check`：dashboard 的 `request.js`、`notifications.js`、`panels.js`、`registry.js`、`module-loader.js`、`app.js`，以及 QQ `index.mjs`、`daily_briefing_scheduler.mjs` 共八项通过；`test_dashboard_shell.py` 的内联 legacy JavaScript 检查也通过。
- 报告写入前 `server/.venv-asr/Scripts/python.exe scripts/check_task_docs.py`：通过，输出 `task documentation gate passed: 10 gated task(s)`；`git diff --check` 退出 0，仅有混合工作区既有 LF→CRLF 提示；本批明确路径尾随空白检查无匹配。

#### 数据隔离、限制与工作区排除项

- 所有成功/失败夹具都使用 `TemporaryDirectory`、固定 aware 时钟、fake Collector/gateway、fake PK-200、fake PK-210 和虚构秘密；未打开主应用 lifespan，未建立外部 socket。
- 未读取、打印、diff、迁移、删除或修改真实 `server/data/briefing_cache/`、`server/data/intel_sources.json`、`.env`、QQ `.env`、Cookie、Token、LLM profile、个人状态或 QQ runtime。上述受保护路径定向 Git 状态复查为空。
- 未运行可能真实联网的 `test_intel.py`、`test_daily_briefing_voice.py`，未启动 8000/8010/9880，未调用真实采集、付费 LLM、TTS 或 QQ，也未修改/领取 PK-115/120/130/131/132/133/134/140。
- 当前分支和混合工作区中的来源配置、twitter/bilibili Collector、dashboard、calendar、focus、斩妖、个人数据、`vendor/` 及其他用户改动全部排除；本轮未重置、删除、整理、暂存、提交、推送、PR 或发布。

#### 退回整改与复验要求

- PK-110 service/repository：失败或成功补采导致 document digest（至少 items/text/coverage/warnings）变化时，旧 summary 必须一致失效；根据 rewrite 意图生成新稿或明确 fallback，并断言返回 document 与立即 repository reload 一致。
- PK-110 models/contracts：对 Collector warning、coverage detail、URL query 等所有外部公开文本建立统一、有界、可复用的秘密清洗；新增 fake Authorization/Cookie/API key/signed URL 回归，断言缓存、响应、prompt 和日志均不出现虚构秘密。
- PK-110 legacy 接缝：`gather_all_intel` 不得打印或保留原始异常正文；日志只记录来源和有限状态。不得借整改修改具体 Collector 行为或来源配置所有权。
- 整改后由 PK-900 重跑本节三条原始失败夹具、主动通过夹具、两项定向测试、五项共享回归、Python/JavaScript、文档门禁和受保护路径检查。阻断关闭前 PK-900 不得改为“待集成”。

### PK-110 阻断整改独立复验（2026-07-22）

#### 复验结论

**通过。** PK-900 没有只接受上游工作记录：已重新审阅 Collector 公共模型、补采/改写事务、legacy gather 异常分支和新增测试，并按初验原时序独立重放三类失败夹具。补采内容变化后返回稿与立即重读一致；warning、coverage detail、标题、摘要、metadata 和 URL query 中的虚构凭证不再进入缓存、响应或 PK-200 prompt；legacy 采集异常只记录来源与异常类型。原三项阻断均已关闭，未发现新的 PK-110 集成阻断。

PK-110 保持“待集成”；本轮 PK-900 置为“待集成”，提交 PK-000 最终复核。此前初验“不通过”的证据继续保留，不改写为当时已通过，也不把 PK-110 自行标记为“已完成”。

#### 原阻断项复验结果

- 摘要一致性：固定时钟下先生成 `github` 失败状态和 fake 播报稿，31 分钟后再次失败并改变 warning/coverage/text。`document_digest()` 识别内容变化，旧 script 被失效并按当前 `rewrite=true` 重写；返回 document 与 `service.read()` 立即重读的 `script`、`rewrite_status` 和新失败文本一致。原夹具输出 `original_patch_summary_fixture=passed`。
- 公共边界脱敏：只使用硬编码虚构值，对 `Authorization`、`Cookie`、token、API key 和 URL query 做缓存、公开响应及 fake PK-200 prompt 联合断言。所有秘密均不可见，敏感 query 被移除，安全 query `view=1` 保留，普通 metadata 保留，受控位置出现 `<redacted>`。原夹具输出 `original_public_secret_fixture=passed`。
- legacy 日志脱敏：临时替换 arXiv fetch 为抛出含虚构秘密的 `RuntimeError`，传入空作者/假来源快照并捕获 stdout。stdout 和 `_warnings` 均不含异常正文，只保留 `RuntimeError` 类型；原夹具输出 `original_legacy_log_fixture=passed`。
- 代码边界：统一 `sanitize_external_text()` 位于冻结模型边界，`normalize_url()` 丢弃敏感 query key；`CollectorResult`、`SourceCoverage`、`IntelItem` 与 `BriefingDocument` 的公共文本在落盘/公开前收敛到同一规则。补采 digest 覆盖 items/text/coverage/warnings，内容变化统一失效旧稿；legacy gather 未修改具体 Collector 或来源配置所有权。

#### 回归与主动场景

- `test_daily_briefing_module.py` 继续覆盖缓存原子替换失败、并发 refresh 串行、补采冷却、跨天 summary 清理、prompt injection、论文来源合并、只读零调用和本轮三条阻断回归；退出 0，输出 `daily briefing module tests passed`。
- `test_daily_briefing_summary_cache.py` 退出 0；同日总结复用、摘要失配、跨天失效和 fallback 行为无回归。
- `test_intel_source_config.py`、`test_conversation_consumers.py`、`test_voice_module.py`、`test_feature_catalog.py`、`test_dashboard_shell.py` 全部退出 0。conversation 消费者测试仅记录沙箱拒绝就地加载既有 focus runtime 的隔离提示，应用按现有模块隔离逻辑跳过且全部断言通过，不属于 PK-110 缺陷。
- 普通缓存读取、dashboard 状态和 QQ `fetch=false` 的零 Collector/零 PK-200/零 PK-210 结论继续由定向测试覆盖；强制刷新、缺失来源补采、冷却、跨天清理、原子写和并发刷新没有回归。

#### 实际命令与结果

- 原三类失败时序使用 `.\.venv-asr\Scripts\python.exe -c ...` 调用测试中的独立函数，统一使用 `TemporaryDirectory(prefix='kei-pk900-pk110-recheck-')`、固定 UTC aware 时钟、fake gateway/collector/generator：三项均通过。首次命令因未把 `tests/` 加入 `sys.path`，在导入阶段得到 `ModuleNotFoundError: _path_setup`，未执行产品代码；按测试脚本正常导入路径修正后通过。
- `.\.venv-asr\Scripts\python.exe tests\test_daily_briefing_module.py`、`test_daily_briefing_summary_cache.py`、`test_intel_source_config.py`、`test_conversation_consumers.py`、`test_voice_module.py`、`test_feature_catalog.py`、`test_dashboard_shell.py`：七项全部退出 0。
- `features/daily_briefing`、`features/catalog`、`services/daily_briefing.py`、`intel/briefing.py`、`api.py` 和七个相关测试共 25 个 Python 文件执行 `py_compile`：通过。第一次编译清单误写不存在的 `features/catalog.py`，在读取源码前得到 `FileNotFoundError`；改用实际 `features/catalog/*.py` 后完整通过。
- dashboard 的 `panels.js`、`notifications.js`、`module-loader.js`、`app.js`、`request.js`、`registry.js`，以及 QQ `index.mjs`、`daily_briefing_scheduler.mjs` 分别执行 `node --check`：八项全部退出 0。
- 状态和报告写入后执行 `server/.venv-asr/Scripts/python.exe scripts/check_task_docs.py`、`git diff --check`、本批明确文本路径尾随空白检查和受保护路径 Git 状态复查；结果记录在下方文档门禁。

#### 数据隔离、风险、限制与工作区排除项

- 所有写入测试只使用系统临时目录、fake Collector/gateway、fake PK-200、fake PK-210、固定时钟和硬编码虚构秘密；未读取、打印、迁移、重置或修改真实 briefing cache、来源名单、Cookie、Token、`.env`、LLM profile、个人状态或 QQ runtime。
- 未运行 `test_intel.py`、`test_daily_briefing_voice.py`，未启动本地服务，未建立外部 socket，未调用真实采集、付费 LLM、TTS 或 QQ；未实施 PK-115/120/130/131/132/133/134/140。
- 脱敏采用有限的 credential-shaped 名称/赋值模式；它降低标准 Token/Cookie/URL 凭证进入公共链路的风险，但不承诺识别任意自然语言中的未知秘密。后续来源仍不得主动把凭证放入业务内容，此限制不阻塞当前冻结契约。
- legacy gather 继续属于兼容接缝，内部仍有既有全局来源状态；本轮只验证 PK-110 单进程调用和错误净化，没有把其改造成新 Collector 或跨进程协调器。
- 当前混合工作区包含来源配置、Collector、dashboard、calendar、focus、语音、个人数据、`vendor/` 及其他任务/用户修改；本轮只编辑本任务记录与 `TASKS.md` 的 PK-900 状态，不重置、删除、覆盖、整理、暂存、提交、推送或发布。

#### 本轮八项文档门禁

- [x] TASK_RECORD — 保留初验“不通过”与原始失败证据，并追加整改代码结论、原夹具输出、回归、实际命令、隔离、风险、限制及最终“通过”结论。
- [x] TASKS_BOARD — PK-110 保持“待集成”；本轮 PK-900 已改为“待集成”，依赖仍为 `PK-110（本批次）`，等待 PK-000。
- [x] PUBLIC_README — 整改只收紧既有缓存一致性和不可信文本净化，没有改变用户安装、启动、配置、公开接口形状或操作流程；现有 README 无需更新。
- [x] MODULE_CATALOG — 模块 ID、版本、endpoint、状态与迁移信息未变；catalog/dashboard 回归通过，不需要修改目录。
- [x] ARCHITECTURE_DOCS — Collector 契约、legacy gateway、PK-200/PK-210 委托、缓存和模块边界未改变；现有模块化单体与可安装模块文档仍一致。
- [x] LOCAL_README — 不适用：没有读取或确认新的本机路径、端口、解释器、秘密或真实来源配置，也没有改变本机运行约定。
- [x] AGENT_RULES — 不适用：没有改变安全边界、工作流、验证、文档或 Git 规则；验收过程继续遵守 fake/临时目录与不发布约束。
- [x] VALIDATION — 已重放原三条阻断夹具、两项定向和五项共享回归、25 文件 Python 编译及八项 JavaScript 检查；最终文档门禁、差异/行尾和受保护路径检查在状态同步后执行并记录。

### PK-000 最终独立复核（2026-07-22）

#### 结论

**不通过。** PK-000 独立重跑两项 PK-110 定向测试与五项共享回归，均退出 0；只读零调用、缺失来源单独补采与冷却、跨天播报稿清理、prompt 注入隔离、LegacyCollectorGateway 八类映射、冻结文档和受保护数据隔离也通过。但是额外的刷新失败与跨文件保存失败夹具稳定复现一个新的事务阻断，因此不宣布 Collector `1.0` 正式冻结，不授权下游来源任务开始。

#### 阻断证据

- Collector/gateway 刷新失败：先在临时 root 写入包含 `old-item` 和有效播报稿的当天缓存，再令 gateway 在 `refresh=true` 时抛出异常。`BriefingService._collect()` 将异常转换为 `failed` 结果，`generate()` 因 refresh 跳过旧缓存并把 `failed/0 items` document 原子覆盖到同一路径。夹具输出 `collector_failure_refresh_old_cache_preserved=false`、`main_bytes_unchanged_after_collector_failure=false`。
- 主缓存单文件替换失败：注入失败的 `os.replace` 后，旧主缓存字节保持不变且临时文件被清理，输出 `main_atomic_replace_failure_old_cache_preserved=true`；说明单文件原子写本身有效。
- 播报稿替换失败：允许新主缓存替换成功、只令 `kei_summary_today.json` 替换失败。请求抛出 `BriefingCachePersistenceError`，但主缓存已经变成 `new-item`，旧 summary 字节仍在且因 digest 不匹配不再展示。夹具输出 `summary_replace_failure_main_cache_unchanged=false`、`summary_replace_failure_old_summary_bytes_preserved=true`、`summary_replace_failure_visible_script=false`。
- 路由对任意 `BriefingCachePersistenceError` 返回“旧缓存保持不变”，但上述 summary 失败路径中该承诺不成立。当前顺序是先保存主缓存，再生成/保存 summary，两个文件没有共同 commit/rollback 边界。

#### 最小整改与归属

- 归属 PK-110 `service.py`/`repository.py`/`router.py`。显式刷新遇到 gateway 异常或不可接受的全来源失败时，必须保留旧可用主缓存和播报稿；响应应明确刷新失败/沿用旧缓存，不能把失败快照覆盖为当天唯一事实。
- 主缓存与当天播报稿必须形成可恢复的统一提交边界。summary 保存失败时应回滚主缓存或使用 generation/commit pointer 等等价事务方案，保证调用失败后只读结果仍是完整旧版本；同时修正 HTTP 错误文案，使其只声明实际成立的保证。
- 新增三个全假临时回归：Collector/gateway 刷新异常保留旧 items/text/script 与文件字节；主缓存替换失败保留旧版本且无临时文件；summary 替换失败不出现新主缓存+旧/不可见播报稿的半状态。整改不得修改具体 Collector、真实缓存或来源配置。
- 整改后由 PK-900 重跑本轮全部定向/共享测试和上述原始夹具，再提交 PK-000。PK-110 继续保持“待集成”，PK-900 恢复“进行中”；Collector 契约冻结与下游并行授权均暂缓。

### PK-110 刷新事务整改最终复验（2026-07-22）

#### 最终结论

**通过。** PK-000 独立审查整改后的 `service.py`、`repository.py`、`router.py` 与新增事务回归，并重新执行原阻断时序。显式刷新遇到 gateway 全失败时沿用完整旧缓存且不重复调用 PK-200；主缓存或当天播报稿任一替换失败时，两份文件都恢复为提交前字节，只读结果继续显示旧条目与旧播报稿。此前阻断已关闭，未发现新的 PK-110 集成阻断。

PK-110 与本轮 PK-900 均改为“已完成”。Collector `1.0` 正式冻结；PK-115、PK-120、PK-130、PK-131、PK-132、PK-133、PK-134 获准由各自独立功能对话领取并并行推进，授权本身不改变其当前“待开始”状态。

#### 独立复现与回归证据

- gateway 全失败：临时 root 中先生成 `old-item` 和 fake 播报稿，再令 fake gateway 在 `refresh=true` 时抛错。返回 `refresh_status=failed_using_cache`，旧 items/text/script、主缓存字节和 summary 字节均不变，fake PK-200 调用次数不增加；dashboard 兼容入口返回同一降级状态。
- 主缓存替换失败：向 repository 注入只拒绝主缓存目标的 fake replace；请求明确抛出 `BriefingCachePersistenceError(cache_state_preserved=True)`，两份旧字节和旧可见播报稿保持，无 `*.tmp`/restore 临时文件残留。
- summary 替换失败：允许主缓存先替换、仅拒绝 `kei_summary_today.json` 目标；repository 回滚主缓存与 summary，异常继续报告 `cache_state_preserved=True`，立即重读仍为 `old-item` 与原播报稿，无半提交状态。
- `test_daily_briefing_module.py`、`test_daily_briefing_summary_cache.py`、`test_intel_source_config.py`、`test_conversation_consumers.py`、`test_voice_module.py`、`test_feature_catalog.py`、`test_dashboard_shell.py` 共七项均退出 0。conversation consumer 测试的 focus runtime 权限提示属于既有隔离降级，全部断言通过。
- 最终状态写入后，`scripts/check_task_docs.py` 与 `git diff --check` 通过；明确受保护路径的定向 Git 状态除既有、与本批无关的未跟踪 `vendor/` 外为空。`vendor/` 只做顶层状态确认，依照 agent 规则未扫描其中外部源码。

#### 安全、数据与工作区边界

- 所有主动写入只发生在系统临时目录，使用 fake gateway/Collector、fake PK-200、fake PK-210 与固定时钟；未运行真实采集、LLM、TTS、QQ 或可能联网的集成测试。
- 未读取、打印、diff、迁移、重置或修改真实 `server/data/briefing_cache/`、`server/data/intel_sources.json`、`.env`、QQ runtime、LLM profile 或个人状态。
- 当前混合工作区中的来源配置、具体 Collector、dashboard、calendar、focus、语音、个人数据、`vendor/` 及其他用户修改均不属于本批；本轮未清理、覆盖、暂存、提交、推送或发布。

#### 最终文档门禁

- [x] TASK_RECORD — 保留两轮退回证据并追加本次整改最终通过结论、独立场景、风险与限制。
- [x] TASKS_BOARD — PK-110 与本轮 PK-900 已同步为“已完成”；下游来源任务继续保持“待开始”等待独立领取。
- [x] PUBLIC_README — 已宣布 Collector `1.0` 正式冻结和下游并行授权。
- [x] MODULE_CATALOG — 模块 ID、接口和迁移状态未变；catalog/dashboard 回归通过，无需修改目录。
- [x] ARCHITECTURE_DOCS — daily briefing 专项文档已由候选改为正式冻结，并记录兼容与变更规则。
- [x] LOCAL_README — 不适用；未改变本机路径、端口、解释器、秘密或运行约定。
- [x] AGENT_RULES — 不适用；未改变 agent 安全、工作流、验证、文档或 Git 规则。
- [x] VALIDATION — 三项事务失败时序、两项定向测试、五项共享回归、文档门禁、差异/空白及受保护路径检查均通过。

## PK-115 + PK-119 + PK-120 + PK-130 + PK-131 + PK-132 + PK-133 + PK-134 情报来源模块集成验收批次（2026-07-22）

### 批次范围、状态与独立性

- 本节只追加本批独立验收，不覆盖 PK-900 之前任何初验、整改、复验或 PK-000 结论。验收对象为 PK-115、PK-119、PK-120、PK-130、PK-131、PK-132、PK-133、PK-134；八项功能任务继续保持“待集成”。
- 入场时已完整读取根 `README.md`、`AGENTS.md`、`README.local.md`、`TASKS.md`、八项来源任务、PK-900 任务文件，以及 daily briefing、模块化单体、可安装模块架构文档；随后检查 `git status --short --branch` 和共享文件实际差异。PK-900 与任务总板本批均登记为“进行中”。
- 当前分支为 `agent/intel-sources-dashboard`，工作区包含 conversation、voice、calendar、demon、focus、QQ、个人状态、外部参考和其他任务的混合修改。本批只审计来源 registry、八来源 Collector/编排、资料/帖子缓存、daily briefing 接缝、来源 API、catalog 与 dashboard 对应 hunks；其余修改全部排除，未清理、覆盖、暂存、提交或推送。

### 验收结论

**不通过。** Collector `1.0` 指纹、八来源装配、普通来源并发、三论文来源串行与独立 coverage、Semantic fallback/去重、单来源采集失败隔离、RSS 固定受信 HTTPS Feed/重定向限制、YouTube Channel ID、GitHub 环境 Token、路由唯一性、十五项规定回归、Python/JavaScript/文档/差异门禁均通过；但独立逆向测试稳定复现四项当前集成阻断：

1. dashboard 初次打开及 X/B 关注项新增、编辑成功后会调用资料解析 POST；缓存缺失时该路径实际调用 profile fetcher，违反“打开控制台零联网”及“只有显式按钮或生成流程才能联网”。
2. Bilibili 资料规范化未复用 Collector `1.0` 的公共文本/URL 净化规则，凭证形态的上游昵称及头像 query 会原样进入 API 响应和临时 cache。
3. versioned 来源写入/联网端点拒绝恶意 Origin，但同功能 legacy `/dashboard/intel-sources*` 端点接受该 Origin并执行写入或 fake 网络动作，兼容边界不一致。
4. `ProjectCollectorGateway.aclose()` 遇到第一个 collector 关闭异常即退出，后续普通来源和论文来源均未执行关闭。

因此 PK-900 保持“进行中”，不把整批提前交给 PK-000 终审。八项来源任务均不改成“已完成”或其他状态。

### 通过的契约与装配审计

- Collector 公共指纹保持 `contract_version=1.0`；公共 source ID 顺序为 `twitter/github/bilibili/youtube/money/arxiv/crossref/semantic`。`CollectRequest`、`IntelItem`、`SourceCoverage`、`CollectorResult` 的 dataclass 字段与正式冻结文档逐项一致，没有发现来源任务修改公共契约。
- `create_project_collector_gateway()` 注册 twitter/Nitter、GitHub、Bilibili、YouTube、money/RSS 以及 arXiv、Crossref、Semantic Scholar；构造只装配 client/配置，不发送请求。普通来源由 `ContractCollectorGateway` 并发执行；论文 coordinator 按请求顺序逐个 await，且 platform 与 paper coordinator 可以并行。
- 单来源 collect 异常被收敛为有限 warning/coverage，不阻断其他来源。论文三来源保留真实 source ID/coverage；Semantic fallback 只补未覆盖作者，跨来源规范化与去重回归通过。
- YouTube registry/collector 只接受 `UC` 加 22 字符标准 Channel ID。GitHub 授权仅在请求时从 `GITHUB_TOKEN` 环境读取，代码未把 Token 写入来源配置。RSS 拒绝用户 URL、非 HTTPS、userinfo、IP literal、本机/私网式 hostname、非 443 端口和危险跨站重定向，并禁用 `trust_env`/自动重定向。
- `GET/PUT/POST/DELETE /api/v1/intel-sources*`、X/B versioned API、legacy API、dashboard 和 feature catalog 均已登记；主应用路由表逆向枚举没有重复 method/path。

### 阻断证据与最小整改归属

#### 阻断一：控制台只读打开和来源 CRUD 存在隐式资料联网

- `loadIntelSources()` 在读取 `/api/v1/intel-sources` 后自动执行 `loadBilibiliProfiles()` 与 `loadXProfiles()`；两者调用 `/api/v1/bilibili/profiles/resolve`、`/api/v1/x/profiles/resolve` 的 POST。使用空临时 cache 与计数 fake fetcher 调用 service 的同等路径，得到 `x=1`、`b=1`。
- dashboard 的 `addIntelSource()`、`updateIntelSource()` 在保存成功后还会分别 `await loadBilibiliProfiles(false, uid)` 或 `await loadXProfiles(false, value)`，所以新增/编辑来源本身会触发资料联网；删除未发现相同调用，briefing 生成也未被触发。
- 归属：PK-119 共享 dashboard/API 收口，PK-120/PK-130 资料读取契约。最小修复为控制台初次展示只走只读 cache API（B 已有 GET；X 需补等价只读入口或公开只读 service），移除来源 CRUD 成功后的隐式 resolve；只有用户点击明确的“刷新资料”按钮或显式生成流程才调用 resolve/fetch。新增 dashboard 启动、增改删三类零 fake-network 计数回归。

#### 阻断二：Bilibili profile 响应和 cache 未净化凭证形态字段

- 临时 B profile fetcher 返回凭证形态 nickname 和带敏感 query 的 HTTPS avatar。`resolve_profiles(refresh=false)` 的公开结果与临时 `b_profiles.json` 均保留 nickname 内容及敏感 query；测试只输出真假布尔值，没有打印真实秘密或真实 cache。
- X profile cache 已使用公共 `sanitize_external_text()`/`normalize_url()`，Bilibili profile normalization 尚未保持同一规则；Collector 公共结果本身的净化测试通过，但 profile API/cache 是另一条公开链路。
- 归属：PK-130。最小修复为在 B profile 进入响应和原子 cache 之前，对 name 使用公共外部文本净化、对 avatar URL 使用公共 URL 净化，并补充响应、cache、dashboard 三处虚构 Cookie/Token/Authorization/query 回归；不得读取或迁移真实 B profile cache。

#### 阻断三：versioned 与 legacy 本机控制边界不一致

- ASGI fake side-effect 夹具使用本机 client 地址并携带 `Origin: https://evil.example`。结果：versioned registry PUT、B profile resolve、X profile resolve、X posts fetch 均返回 403；对应 legacy 路径返回 200，并分别执行 fake registry 写入或 fake profile/posts 调用。
- 原因是 versioned registry/B 使用统一 local-control guard、versioned X 自行校验本机 Origin，而 legacy 来源路由仅检查 client host。路由 method/path 枚举没有重复，问题是同功能接口的调用边界分叉。
- 归属：PK-119 的 `server/api.py` legacy 接缝。最小修复为 legacy 来源读取、写入及联网动作复用同一 local-control Origin 规则，并增加 versioned/legacy 参数化恶意 Origin 回归；正常无 Origin 的本机工具与 `http://127.0.0.1:8000`、`http://localhost:8000` 控制台兼容性仍需保留。

#### 阻断四：关闭失败会跳过剩余资源

- 向 `ProjectCollectorGateway` 注入三个全假 closer，第一个抛出 `RuntimeError`。输出为 `first_calls=1`、`second_calls=0`、`paper_calls=0`，证明一个来源关闭失败会阻止后续来源释放。
- 归属：PK-119 的 `features/daily_briefing/source_composition.py`。最小修复为仍按唯一对象去重，但无论单个 closer 成功或失败都尝试关闭全部普通/论文 collector；完成全部清理后再按明确契约报告失败，并补充首/中/末 closer 失败与重复对象回归。

### 规定测试、主动逆向测试与静态门禁

- 在 `server/` 下统一设置不存在的 `PROJECT_KEI_ENV_FILE`、`PROJECT_KEI_LLM_PROFILE_PATH`、`PROJECT_KEI_VOICE_PACK_REGISTRY`，设置虚构 `GITHUB_TOKEN`、`SEMANTIC_SCHOLAR_API_KEY`，并清空 `BILI_COOKIE`；随后逐项执行 `.\.venv-asr\Scripts\python.exe`：
  - `tests\test_intel_sources_registry.py`
  - `tests\test_x_monitor.py`
  - `tests\test_bilibili_collector.py`
  - `tests\test_bilibili_feature.py`
  - `tests\test_youtube_collector.py`
  - `tests\test_github_intel_collector.py`
  - `tests\test_papers_collectors.py`
  - `tests\test_rss_intel_collector.py`
  - `tests\test_intel_sources_integration.py`
  - `tests\test_intel_source_config.py`
  - `tests\test_daily_briefing_module.py`
  - `tests\test_daily_briefing_summary_cache.py`
  - `tests\test_feature_catalog.py`
  - `tests\test_dashboard_shell.py`
  - `tests\test_conversation_consumers.py`
- 上述十五项均退出 0。B/X lookup failure 日志来自固定 fake 异常；conversation consumer 的 focus runtime `PermissionError` 是既有模块隔离提示，断言仍全部通过。
- 主动逆向夹具全部只用 `TemporaryDirectory`、计数 fake、`httpx.ASGITransport` 和虚构凭证：Collector 指纹夹具退出 0；profile/dashboard、legacy Origin、关闭失败夹具按预期退出 1并输出上述阻断事实。初版逆向脚本曾两次在测试夹具导入/构造阶段失败（错误的模块路径、过期的 service kwargs），均未进入产品断言或外部副作用；改为实际公开构造契约后得到正式结果。
- Python：`.\.venv-asr\Scripts\python.exe -m compileall -q` 覆盖八来源 features、daily briefing、catalog、相关 collectors/services、`api.py` 和十五项测试，退出 0。
- JavaScript：对 `static/dashboard/app.js`、`module-loader.js`、`notifications.js`、`panels.js`、`registry.js`、`request.js` 分别执行 `node --check`，六项均通过。内联 dashboard JavaScript 同时由 `test_dashboard_shell.py` 检查并通过。
- 文档：`server\.venv-asr\Scripts\python.exe scripts\check_task_docs.py` 输出 `task documentation gate passed: 18 gated task(s)`。
- 差异：`git diff --check` 退出 0；只出现既有 LF/CRLF 提示，无空白错误。

### 数据隔离、限制与工作区排除项

- 所有会写状态的测试只使用系统临时目录或测试自身临时路径；网络只用 fake/MockTransport/ASGITransport。未运行 `test_intel.py`、`test_daily_briefing_voice.py` 或任何真实来源采集；未调用 LLM、TTS、QQ、付费接口或生产写操作。
- 未读取、打印、diff、迁移、重置或修改真实 `server/data/intel_sources.json`、briefing/X/B/论文 cache、`.env`、QQ runtime、LLM profile、voice registry 或个人状态内容。来源配置及这些 cache/env/QQ 路径的定向 Git 状态为空。
- `server/systems/data/demon_slayer.json`、`server/systems/data/focus_timer.json` 在本批开始前已经是修改状态，本批只核对顶层状态，没有读取内容；它们与 calendar、conversation、voice、focus、demon、QQ 代码 hunks 一并排除。
- 本批未启动真实本地服务或浏览器，因此没有进行真人页面点击回归；dashboard shell、内联 JavaScript、ASGI 路由和 fake side-effect 已覆盖本次阻断判定所需的可自动复现边界。

### 本批文档门禁

- [x] TASK_RECORD — 已保留所有历史并追加本批范围、通过项、四项阻断、命令、隔离、风险、限制及最小整改归属。
- [x] TASKS_BOARD — PK-900 保持“进行中”；PK-115/119/120/130/131/132/133/134 均保持“待集成”。
- [x] PUBLIC_README — 已核对现有来源能力、显式联网语义和 Collector `1.0` 说明；本轮只报告缺陷，不改公开能力声明。
- [x] MODULE_CATALOG — 已核对来源模块 task ID、endpoint、data owner、network condition 和迁移状态；catalog 回归通过。
- [x] ARCHITECTURE_DOCS — 已核对八来源映射、论文串行/fallback、API、数据所有权和安全限制；四项阻断是实现偏离，不改写架构约定。
- [x] LOCAL_README — 不适用；本批未改变本机解释器、端口、路径、环境位置或运行说明。
- [x] AGENT_RULES — 不适用；未改变 agent 规则，验收按既有数据、外部服务、共享工作区和 Git 边界执行。
- [ ] VALIDATION — 十五项规定回归、compileall、六项 `node --check`、文档门禁和 `git diff --check` 均通过，但四项独立逆向场景失败；待责任任务最小整改后由 PK-900 原夹具复验。

### 责任任务整改交接（2026-07-22）

- PK-119/120/130 已按上列最小范围完成代码、回归与公开文档整改：dashboard/CRUD 资料读取改为 cache-only，新增 X profile 只读 GET；B profile 响应/cache 统一净化；legacy 来源路由复用 versioned Origin 控制；Collector close 全尝试后有界报错。
- 责任任务新增的回归使用临时目录、fake 和 ASGITransport，已分别覆盖零隐式网络、虚构凭证不进入响应/cache、legacy/versioned 恶意 Origin 零副作用，以及首/中/末 closer 失败与重复对象。
- 本条仅是整改交接，不修改上方独立验收结论或 `[ ] VALIDATION`。PK-900 继续保持“进行中”，八个来源任务继续保持“待集成”，等待 PK-900 用原逆向夹具复验。

### 四项阻断整改独立复验（2026-07-22）

#### 复验结论

**通过。** PK-900 没有直接采用责任任务的自测结论，而是重新审查实际实现并按初验同等时序重放四项原始失败夹具。只读 dashboard/profile 链路不再调用外部 fetcher；Bilibili 资料的凭证形态文本和敏感 URL query 不再进入响应或 cache；versioned/legacy 来源端点对恶意 Origin 一致拒绝且零副作用；单个 closer 失败后其余唯一 collector 仍全部关闭。十五项规定回归、Collector `1.0` 指纹、路由唯一性、Python/JavaScript、文档门禁和差异检查均通过，未发现新的本批集成阻断。

本轮 PK-900 改为“待集成”，提交 PK-000 最终复核。PK-115、PK-119、PK-120、PK-130、PK-131、PK-132、PK-133、PK-134 继续保持“待集成”，本轮不自行将任何任务改为“已完成”。上方初验“不通过”和四项原始失败证据继续作为历史保留，不回写为当时已通过。

#### 原四项失败夹具复验结果

- 控制台与 CRUD 零隐式外部网络：临时 X/B profile cache 为空，向两项 service 注入计数 fake fetcher；调用 `read_profiles()` 后计数保持 `x=0`、`b=0`。dashboard 非刷新路径分别使用 `GET /api/v1/x/profiles`、`GET /api/v1/bilibili/profiles`；新增和编辑函数不再调用 resolve，删除继续只保存 registry。显式“刷新资料”按钮仍调用 POST resolve，功能边界保持。
- Bilibili 资料净化：临时 fetcher 返回含虚构 Authorization 形态 nickname、`token` query 和安全 `view=1` query 的头像 URL。公开结果和临时 `b.json` 均不含两项虚构秘密，安全 query 在两处保留；响应/cache 共同经过 `sanitize_external_text()` 与 `normalize_url()`。
- versioned/legacy Origin 一致性：以本机 ASGI client 携带 `Origin: https://evil.example` 请求 registry PUT、B profile resolve、X profile resolve、X posts fetch 的新旧八个入口，全部返回 403；fake registry/B/X profile/X posts 副作用计数全部为 0。正常本机控制规则未改，相关 API 回归通过。
- 关闭失败隔离：向 `ProjectCollectorGateway` 注入 first/second/paper 三个唯一 closer，并让 first 抛出包含虚构正文的 `RuntimeError`，同时在论文映射中重复引用 second。结果三个唯一 closer 调用次数均为 1；最终抛出有界 `CollectorCloseError`，不含原始异常正文。证明失败后继续清理且对象去重仍有效。

#### 完整回归与实际命令

- 在 `server/` 下强制使用不存在的 `PROJECT_KEI_ENV_FILE`、`PROJECT_KEI_LLM_PROFILE_PATH`、`PROJECT_KEI_VOICE_PACK_REGISTRY`，注入虚构 `GITHUB_TOKEN`、`SEMANTIC_SCHOLAR_API_KEY` 并清空 `BILI_COOKIE`。随后用 `.\.venv-asr\Scripts\python.exe` 逐项执行：
  - `tests\test_intel_sources_registry.py`
  - `tests\test_x_monitor.py`
  - `tests\test_bilibili_collector.py`
  - `tests\test_bilibili_feature.py`
  - `tests\test_youtube_collector.py`
  - `tests\test_github_intel_collector.py`
  - `tests\test_papers_collectors.py`
  - `tests\test_rss_intel_collector.py`
  - `tests\test_intel_sources_integration.py`
  - `tests\test_intel_source_config.py`
  - `tests\test_daily_briefing_module.py`
  - `tests\test_daily_briefing_summary_cache.py`
  - `tests\test_feature_catalog.py`
  - `tests\test_dashboard_shell.py`
  - `tests\test_conversation_consumers.py`
- 十五项全部退出 0。B/X lookup failure 是预期 fake 异常日志；conversation consumer 的 focus runtime `PermissionError` 是既有模块隔离提示，断言全部通过。
- 对八来源 features、daily briefing、catalog、相关 collectors/services、`api.py` 和十五项测试执行 `.\.venv-asr\Scripts\python.exe -m compileall -q ...`，退出 0。
- 对 dashboard 的 `app.js`、`module-loader.js`、`notifications.js`、`panels.js`、`registry.js`、`request.js` 分别执行 `node --check`，六项退出 0；内联脚本由 dashboard shell 测试再次验证。
- 独立指纹/路由夹具确认 Collector `1.0` 的四个 dataclass 字段列表和八个公共 source ID 与冻结文档一致，主应用没有重复 method/path。
- 最终状态和本节写入后执行 `server\.venv-asr\Scripts\python.exe scripts\check_task_docs.py`、`git diff --check` 及受保护路径定向状态检查；结果见下方最终门禁。

#### 数据隔离、风险与限制

- 原夹具和回归仅使用 `TemporaryDirectory`、fake、MockTransport/ASGITransport 与虚构凭证；未调用真实来源、LLM、TTS、QQ、付费接口或生产写操作，未启动真实本地服务。
- 未读取、打印、diff、迁移、重置或修改真实来源名单、briefing/X/B/论文 cache、`.env`、QQ runtime、LLM profile、voice registry 或个人状态内容。来源/cache/env/QQ 受保护路径定向 Git 状态为空。
- `server/systems/data/demon_slayer.json` 与 `server/systems/data/focus_timer.json` 仍是入场前既有修改，本轮只确认顶层状态，不读取内容；calendar、conversation、voice、focus、demon、QQ、`vendor/` 和其他用户修改继续排除。
- 本轮未启动服务或进行真人浏览器点击；控制台语义由 dashboard shell、内联 JavaScript 静态断言、公开 service 计数 fake 和 ASGI 路由时序复验。真实上游可用性、限流和供应商行为不在自动验收范围。
- 未执行 Git 暂存、提交、推送、发布或工作区清理。

#### 最终八项文档门禁

- [x] TASK_RECORD — 保留初验不通过和原始证据，并追加本次独立通过结论、原夹具输出、完整回归、隔离、风险与限制。
- [x] TASKS_BOARD — 本轮 PK-900 同步为“待集成”；八项来源任务继续保持“待集成”等待 PK-000。
- [x] PUBLIC_README — 已记录 dashboard/CRUD cache-only、X profile 只读 GET、B profile 净化和显式联网语义，与实现一致。
- [x] MODULE_CATALOG — 已登记 X profile 只读/resolve、B profile 只读/resolve、数据所有权和显式网络条件；catalog 回归通过。
- [x] ARCHITECTURE_DOCS — 已记录八来源、论文串行/fallback、只读 profile、legacy Origin 一致性及数据边界，与实现一致。
- [x] LOCAL_README — 不适用；没有改变本机解释器、路径、端口、环境文件位置或启动方式。
- [x] AGENT_RULES — 不适用；没有改变 agent 工作流、安全、文档、验证或 Git 规则。
- [x] VALIDATION — 四项原失败时序、十五项规定回归、Collector 指纹、路由唯一性、compileall、六项 JavaScript、文档门禁、差异和受保护路径检查全部通过。

### PK-000 最终独立复核（2026-07-22）

#### 最终结论

**通过。** PK-000 已复核最新 PK-900 报告、实际整改代码和当前混合工作区，并独立重放本批关键边界。原子来源配置替换失败保留旧字节且不残留临时文件，并发写入保持有效单一文档；来源配置保存、当天 briefing 读取及 X/B profile cache-only 读取均不调用 Collector、文本生成器或外部 fetcher；单来源采集/关闭失败不阻断其他来源；跨源 warning、coverage、item 与 B profile 响应/cache 的虚构凭证均被清洗；RSS 私网重定向在首跳后拒绝；主应用 114 个 method/path 均唯一。

Collector 公共版本仍为 `1.0`，四个 dataclass 字段指纹和八个公共 source ID 未改变。PK-115、PK-119、PK-120、PK-130、PK-131、PK-132、PK-133、PK-134 与本轮 PK-900 一并置为“已完成”。

#### 独立证据与边界

- 独立执行 `test_intel_sources_registry.py`、`test_x_monitor.py`、`test_bilibili_collector.py`、`test_rss_intel_collector.py`、`test_intel_sources_integration.py`，全部退出 0；只使用 fake、MockTransport/ASGITransport、虚构凭证和临时目录。
- 独立指纹/路由夹具输出 `collector_contract=1.0`、`public_source_ids=8`、`unique_method_paths=114`，无重复 method/path。
- `scripts/check_task_docs.py` 在状态变更前通过 19 个门禁任务；`git diff --check` 退出 0，仅有既有 LF/CRLF 提示。来源名单、briefing/X/B/论文 cache、`.env` 和 QQ runtime 的定向 Git 状态为空，未读取其内容或详细差异。
- 工作区中既有 calendar、conversation、voice、focus、demon、QQ、个人状态及 `vendor/` 修改继续排除；未清理、覆盖、暂存、提交、推送或发布。

#### PK-140 后续资格

可以进入 PK-140。其依赖 PK-001、PK-110 已完成，本来源批次也已关闭；Collector `1.0` 可继续作为 QQ 定时情报的冻结上游契约。PK-140 当前仍保持“待开始”，需由独立任务入场登记后再改为“进行中”，且不得读取 bridge `.env`、发送真实 QQ 测试消息或把缓存优先语义改为隐式联网刷新。

## PK-150 斩妖除魔集成验收批次（2026-07-22）

### 入场登记

- 本节追加在全部既有批次、整改和 PK-000 结论之后，不覆盖或改写任何历史记录。本轮对象仅为 PK-150 及其必要的 PK-200、API、catalog、dashboard 兼容接缝。
- PK-150 入场状态为“待集成”；PK-900 已从上一批“已完成”临时改为“进行中”，任务总板依赖同步为 `PK-150（本批次）`。入场授权不代表通过，PK-150 不由本任务改成“已完成”。
- 当前分支和混合工作区包含来源、conversation、voice、calendar、focus、QQ、个人状态及其他任务修改；本批只按明确路径检查 demon-slayer 实现、测试、API/catalog/dashboard hunks 和文档，不清理、覆盖、暂存、提交或推送其他改动。
- 验收只使用临时 DemonSlayerStore/临时文件、固定时钟和 fake TextGenerator。不得读取、打印、diff、迁移、重置或修改真实 `demon_slayer.json` 及其他个人状态，不调用真实 LLM、TTS 或 QQ。

### 独立验收结论

**通过。** PK-150 的旧数据兼容、versioned/legacy 共用 service、目标层级与周期边界、软删除历史保留、并发与重复奖励幂等、未来日期处理、PK-200 `TextGenerator` 复盘接缝、控制台和模块目录均符合本批约定。规定回归和独立逆向夹具全部通过，没有发现需要退回 PK-150 的当前集成阻断。

本轮 PK-900 改为“待集成”，提交 PK-000 最终复核。PK-150 继续保持“待集成”，本任务不自行将其改为“已完成”。

### 契约、装配与控制台审计

- `DemonSlayerStore` 对旧版仅含 `goals/checkins/points` 的文档补齐缺省字段并保持稳定目标 ID；所有状态写入通过同一路径锁和临时文件替换完成。默认真实路径只在实际读取或写入时访问，本批没有对其调用状态操作。
- 主应用只构造一个 `demon_slayer_service`，再把同一对象注入 versioned `/api/v1/demon-slayer/*` 与 legacy `/demon/*` 路由。ASGI 临时仓库夹具从 legacy 创建后可由 versioned 查询、从 versioned 创建后可由 legacy 查询；跨接口重复打卡首次发 10 分、第二次发 0 分且标记重复。主应用 method/path 枚举无重复项。
- recurring 与 once 目标边界保持；日、周、月、年层级分别按公开 cadence/rank 元数据计算。当前月、年复盘的结束日被截断到固定“今天”，不会把未来日期计为未完成；未来打卡与未来周期复盘均明确拒绝。
- 删除采用软删除，已有打卡和积分仍保留。历史月份夹具保持实际 completed/total；删除后临时存储中的既有 check-in 和 points 未消失。
- Kei 复盘只经 PK-200 公共 `TextGenerator.generate_text()` 获取受限 verdict，prompt 只包含结构化事实。假模型对 `0/1` 事实返回表扬或夹带编造文本时结果被拒绝并本地降级；生成器抛错同样降级；合法受限 verdict 被接受，但最终文案仍由本地事实模板生成。复盘前后状态字节不变，不写 conversation history。
- 控制台提供目标新增、编辑、删除、打卡、周期复盘和奖励兑换，并调用 versioned API；公共 dashboard shell、catalog 和动态面板回归通过。PK-150 业务代码没有使用 `localStorage` 或 `sessionStorage`；公共 `panels.js` 只保存面板展开/收起布尔值，不存目标、积分、复盘、奖励或任何个人业务数据。
- legacy `POST /demon/reset` 仅为旧客户端兼容保留，versioned API 和控制台不暴露该操作。本批未调用它；这仍是明确的兼容风险，不是本批新阻断。

### 独立逆向测试

- 新旧 API 同 service：在 `TemporaryDirectory` 中替换唯一 service 的 repository，并在 `finally` 恢复；使用 `httpx.ASGITransport` 验证双向可见、跨接口重复打卡幂等和路由唯一性，全部通过。
- 旧数据、层级和未来日期：构造最小旧 schema、固定时钟 `2026-07-22`，覆盖 daily/weekly/monthly/yearly、recurring/once、历史月份、当前月/年截断、未来一次性目标、未来打卡/复盘拒绝及软删除历史保留，全部通过。
- 并发与重复奖励：两个 service 实例共用同一临时路径，40 个并发打卡合计只发 10 分且仅一项非重复；30 个并发日复盘合计只发一次 5 分奖励；30 个同 request ID 的兑换只成功一次。最终临时状态为一条 check-in、一条 bonus、一条 redemption，积分为 `10 + 5 - 1 = 14`。
- Kei 事实边界：使用记录 prompt 的 fake generator 分别返回矛盾 verdict、异常和合法受限 verdict，验证矛盾/异常均本地降级、合法结果只影响当次响应、不改变事实或历史，全部通过。
- 第一版层级逆向夹具因 PowerShell stdin 中中文 literal 被本地代码页改写而在测试夹具自身断言失败；改用实现公开的 `CADENCE_META` 比较后正式夹具通过。内联 dashboard 初次 `node --check` 同样因 PowerShell 5.1 默认错误解码 UTF-8 HTML产生语法误报；显式 `-Encoding UTF8` 后退出 0。两项均未触发产品写入、网络或个人数据访问，不属于产品缺陷。

### 规定回归与静态门禁

- 在 `server/` 下设置不存在的 `PROJECT_KEI_ENV_FILE`、`PROJECT_KEI_LLM_PROFILE_PATH`、`PROJECT_KEI_VOICE_PACK_REGISTRY` 和虚构 `LLM_API_KEY`，逐项执行 `.\.venv-asr\Scripts\python.exe`：
  - `tests\test_demon_slayer.py`
  - `tests\test_demon_slayer_hierarchy.py`
  - `tests\test_demon_slayer_module.py`
  - `tests\test_demon_review_kei.py`
  - `tests\test_voice_demon_intents.py`
  - `tests\test_conversation_consumers.py`
  - `tests\test_feature_catalog.py`
  - `tests\test_dashboard_shell.py`
- 八项均退出 0。conversation consumer 期间出现的 focus runtime `PermissionError` 为既有模块隔离提示，测试断言仍全部通过；没有触发真实 LLM、TTS、QQ 或个人状态操作。
- `.\.venv-asr\Scripts\python.exe -m compileall -q features\demon_slayer systems\demon_slayer.py api.py ...` 覆盖实现和上述八项测试，退出 0。
- 从 `dashboard.html` 以显式 UTF-8 提取内联 module script，执行 `node --input-type=module --check -`，退出 0；对 `server/static/dashboard/*.js` 逐项执行 `node --check`，全部退出 0。
- `server\.venv-asr\Scripts\python.exe scripts\check_task_docs.py` 在最终状态写入前输出 `task documentation gate passed: 19 gated task(s)`；PK-900 改为“待集成”并写入本节后复跑，输出 `task documentation gate passed: 20 gated task(s)`。
- `git diff --check` 退出 0，仅输出混合工作区既有 LF/CRLF 提示，没有空白错误。只执行只读状态/差异检查，未执行暂存、提交、推送、发布或清理。

### 数据隔离、风险、限制与工作区排除

- 所有会写状态的规定测试和逆向夹具均使用 `TemporaryDirectory`、临时 `DemonSlayerStore`、固定时钟、fake generator 或 ASGITransport。未启动真实服务，未调用真实 LLM、TTS、QQ 或付费接口。
- 未读取、打印、diff、迁移、重置或修改真实 `server/systems/data/demon_slayer.json` 及其他个人状态内容。该文件与 `focus_timer.json` 的修改状态在入场前已经存在，本批只核对顶层路径状态，不检查其内容；测试前后仍由用户工作区持有。
- 当前分支的来源、conversation、voice、calendar、focus、QQ、个人状态、`vendor/` 及其他任务改动均排除。本批只审查 demon-slayer implementation/test、必要 API/catalog/dashboard hunks和文档一致性，没有整理或吸收无关差异。
- 仓库锁为同一 Python 进程内的路径级锁；本轮以两个 service 实例验证线程并发，不宣称跨多进程事务能力。legacy reset 的破坏性仍由旧接口兼容承担，控制台和 versioned API 不提供入口。
- 未进行真人浏览器点击；控制台由 dashboard shell、内联/外部 JavaScript 语法、公开 API 的 ASGI 时序和静态业务存储检查覆盖。真实浏览器视觉布局不是本批阻断项。

### 本批八项文档门禁

- [x] TASK_RECORD — 保留全部旧批次记录，追加 PK-150 范围、独立结论、逆向证据、命令、隔离、风险和限制。
- [x] TASKS_BOARD — PK-900 同步为“待集成”；PK-150 继续保持“待集成”，等待 PK-000。
- [x] PUBLIC_README — 已核对斩妖除魔能力、versioned/legacy 入口、事实复盘和数据边界，与当前实现一致；本批无需改公开说明。
- [x] MODULE_CATALOG — 已核对 PK-150 模块 ID、endpoint、data owner、dashboard 入口和生命周期状态，catalog 回归通过。
- [x] ARCHITECTURE_DOCS — 已核对模块化单体、公共 conversation 契约、模块目录和共享 API 装配，没有第二套 LLM 或越界数据所有权。
- [x] LOCAL_README — 不适用；未改变解释器、路径、端口、环境文件位置或本机运行方式。
- [x] AGENT_RULES — 不适用；未改变 agent 工作流、安全、数据隔离、文档或 Git 规则。
- [x] VALIDATION — 八项规定回归、四组独立逆向场景、compileall、内联及外部 JavaScript、文档门禁和差异检查全部通过。

### 交给 PK-000 的终审摘要

- 建议结论：**通过**。PK-150 可由 PK-000 依据本报告做最终抽查；在总控明确确认前，PK-150 和本轮 PK-900 均保持“待集成”。
- 建议抽查最小集合：旧 schema 归一化；legacy/versioned 双向可见与跨接口重复打卡；40 并发打卡、30 并发复盘和同 request ID 兑换；当前周期未来日期截断；矛盾 fake verdict 本地降级；真实个人状态路径仅核对状态而不读取内容。

### PK-000 最终独立复核（2026-07-22）

#### 最终结论

**通过。** PK-000 没有只接受 PK-900 的验收结论：已审阅当前 repository/service/router、兼容门面、主应用装配和定向测试，并使用系统临时目录、固定 `2026-07-22` 时钟与 fake `TextGenerator` 独立重放要求的核心边界。未发现旧数据兼容、历史保留、周期、积分、复盘事实、降级或个人状态隔离方面的新阻断。

PK-150 与本轮 PK-900 一并置为“已完成”。

#### 独立抽查证据

- 旧数据：临时最小 `goals/checkins/points` schema 可补齐稳定 goal ID、`repeat_mode=recurring`、rank 和奖励/幂等账本缺省值；未用真实文件验证。
- 历史与周期：完成后的目标软删除，既有 check-in 与积分保持；一次性 weekly 目标在创建后、目标日期所属周内可见，在下一周不可见。最初夹具错误地要求目标在创建前的周一出现，实现按创建时间正确拒绝；改为目标日期检查后通过，不属于产品缺陷。
- 积分与未来：同一目标/周期第二次打卡返回 `duplicate=true` 且积分增量为 0；当前月复盘截止 `2026-07-22`，`2026-07-23` 的未来日复盘被拒绝。
- Kei 边界：事实 prompt 明确包含 `completed=0/total=1`；fake 模型为全未完成事实返回 `praise` 时被拒绝并 `kei_generated=false`，生成异常同样使用本地规则。两种降级前后临时状态字节一致。
- 回归：`test_demon_slayer.py`、`test_demon_slayer_hierarchy.py`、`test_demon_slayer_module.py`、`test_demon_review_kei.py`、`test_voice_demon_intents.py`、`test_conversation_consumers.py`、`test_feature_catalog.py`、`test_dashboard_shell.py` 全部退出 0；只使用临时 store/fake，focus runtime 权限提示属于既有隔离降级且断言通过。
- 数据隔离：真实 `server/systems/data/demon_slayer.json` 仍显示入场前的 `M`，与 `focus_timer.json` 一并只核对顶层路径状态；没有读取内容、查看详细 diff、迁移、重置、覆盖或执行 legacy reset。测试路径扫描确认自动执行分支均显式注入临时 store；`test_demon_slayer.py --reset` 的手工 CLI 兼容分支未执行。
- 最终门禁：状态收口前 `scripts/check_task_docs.py` 通过 20 个 gated tasks，`git diff --check` 退出 0，仅有混合工作区既有 LF/CRLF 提示。未暂存、提交、推送、发布或清理工作区。

## PK-160 好感度与长期记忆集成验收批次（2026-07-22）

### 入场登记

- 本节追加于此前全部批次、整改及 PK-000 最终结论之后，不覆盖、改写或折叠历史记录。本轮只验收 PK-160 及其必要的 PK-200 conversation context、API、catalog、dashboard 和 legacy 命令接缝。
- PK-160 入场状态为“待集成”；PK-900 已从上一批“已完成”临时改为“进行中”，任务总板依赖同步为 `PK-160（本批次）`。入场授权不代表通过，PK-160 不由本任务改成“已完成”。
- 本批重点独立验证：真实好感度/记忆文件零读取零迁移；新旧 relationship/memories API 同 service；事件选择与记忆写入并发幂等；原子替换失败保留旧状态；history、memory、relationship、profile 四个所有权隔离；正式 Context Provider 只读、限量、限长；PK-200 无反向依赖且空 Provider 可独立运行；上下文/错误/日志脱敏；catalog/dashboard 与实际代码一致。
- 所有写入、损坏、并发和 API 验证必须显式使用 `TemporaryDirectory` 中的 relationship/memory repository 与虚构数据；模型和 HTTP 使用 fake client/ASGITransport。不得调用真实 LLM、TTS、QQ、采集或生产写操作。
- 用户明确要求不执行 Git 操作，本轮不运行 `git status`、`git diff`、`git diff --check`、暂存、提交、推送或清理。与 AGENTS.md 常规只读 Git 门禁的差异作为本批限制记录；改用明确路径源码审计、文本尾随空白检查和 `scripts/check_task_docs.py`，不读取真实个人文件内容或元数据。

### 独立验收结论

**不通过。** 七项规定回归、Python/JavaScript 检查、文档门禁以及并发事件结算、并发记忆写入、原子替换失败、四类状态隔离、正式 Context Provider、PK-200 空 Provider/单向依赖、错误与日志脱敏、catalog/dashboard 一致性均通过；但主动逆向测试稳定复现两项当前集成阻断：

1. 主应用通配 CORS 与 PK-160 无本机/Origin guard 组合，使恶意网页能够读取 relationship 状态和完整长期记忆，并通过预检后写入长期记忆；
2. 迁移前已持久化、尚无 PK-160 新增 `instance_id` 的活动事件会被 repository 判为损坏，旧客户端状态无法只读或继续结算。

因此 PK-900 保持“进行中”，PK-160 继续保持“待集成”，不提交 PK-000 最终通过复核。本批未修改任何业务代码。

### 阻断一：跨站网页可读取和写入个人 relationship/memory 状态

- 实现证据：`server/api.py` 使用 `CORSMiddleware(allow_origins=["*"], allow_methods=["*"])`；`create_affection_memory_router()` 的新旧 relationship/memories handler 不接收 `Request`，也没有注入现有 `_is_local_control_request` 或等价 guard。catalog 同时把该模块声明为 `local_state`。
- 独立夹具把主应用的两项 service repository 临时替换到 `TemporaryDirectory`，写入硬编码虚构标记，再以本机 ASGI client 携带 `Origin: https://evil.example` 请求。输出：`memory_read_status=200`、`memory_read_cors=*`、`memory_marker_readable=true`、POST 预检 `200/CORS=*`、实际写入 `200` 且 `cross_origin_write_committed=true`；relationship status 同样 `200/CORS=*`。夹具按安全期望退出 1。
- 该问题不仅是通用网络加固：长期记忆正文和关系状态是本批明确保护的个人信息，向任意浏览器 Origin 暴露属于非必要泄漏；恶意网页还能改变后续 conversation 上下文。
- 最小整改归属：PK-160 router 与必要的 `server/api.py` 装配接缝。新旧 relationship/memories 的个人数据读取与写入应复用统一的本机 client + 受信本机控制台 Origin 契约；无 Origin 的明确本机测试/CLI 保持兼容。由于通配 CORS 会在路由前处理 OPTIONS，写方法还需在 CORS 外层拒绝恶意预检，或由 PK-000 批准等价的统一 CORS 收口；不得只在 POST handler 内检查。
- 必补回归：versioned/legacy 的 relationship status/event/choice、memory list/add/delete，以及危险 legacy reset/clear；覆盖恶意 Origin、受信 `127.0.0.1:8000`/`localhost:8000` Origin、本机无 Origin、远端 client 和 POST/DELETE OPTIONS，并断言拒绝时临时文件字节完全不变。

### 阻断二：迁移前活动事件缺少 `instance_id` 时旧状态不兼容

- `RelationshipRepository.validate()` 目前要求非空 `active_event` 同时含字符串 `id` 与 `instance_id`。`instance_id` 是 PK-160 为并发结算新增的身份字段，但既有 frozen event catalog 事件本身不含该字段。
- 独立临时旧 schema 夹具使用合法 legacy stats、空 history 和从现有 `EVENTS` 复制的活动事件，不添加 `instance_id`/`created_at`。`RelationshipService.get_status()` 抛出安全错误 `relationship active event identity is invalid`，输出 `legacy_active_event_loaded=false` 并退出 1；旧文件字节保持不变。
- 影响限定于迁移时恰有待回应活动事件的旧状态：普通空活动状态与新事件均通过，但这类旧文件会让新旧 status、choice 和 Context Provider 的 relationship 读取全部失败。真实个人文件禁止读取，不能以“当前真实文件也许没有活动事件”豁免任务的旧 schema 契约。
- 最小整改归属：PK-160 relationship repository/service。应为缺少新身份字段的合法旧活动事件提供确定性、只读兼容归一化，或由等价方案保证新旧 status 可读且 choice 仍最多结算一次；普通读取不得为了补字段自动重写真实文件。
- 必补回归：临时旧活动事件无 `instance_id`/`created_at` 时，versioned/legacy status 均可读且重复读取身份稳定、文件字节不变；新旧并发 choice 仍只结算一次，成功结算后保存的新状态合法；未知事件或结构损坏仍明确失败而不覆盖旧字节。

### 已通过的独立契约与逆向场景

- 新旧 service 装配：主应用只有一个 `relationship_service` 和一个 `memory_service`；同一 router 注册 `/api/v1/relationship/*`、`/affection/*`、`/api/v1/memories*`、`/memories*`。临时主应用夹具验证 legacy 创建事件可由 versioned 查询、versioned choice 可由 legacy 查询、legacy 新增记忆可由 versioned 列出、跨接口相同 request ID 只创建一次；method/path 无重复。
- 并发事件：两个 `RelationshipService` 实例共用同一临时路径，40 路并发 trigger 只产生一个持久化 active instance；40 路并发相同 choice 只有一项 `resolved`、其余 `idle`，历史仅一条，分值只结算一次。
- 并发记忆：两个 `MemoryService` 实例共用同一临时路径，50 路相同内容/request ID 只有一次 `created=true` 且 ID 唯一；随后 40 路唯一写入全部保留，没有丢记录。
- 原子失败：relationship choice 和 memory add 的 `os.replace` 分别注入虚构失败，目标旧字节保持、内存重读仍是旧状态、无 `*.tmp` 残留；公开异常不含虚构底层正文。损坏文件回归同样 fail closed。
- 四类所有权：临时 relationship、memory、profile 三个文件与 runtime history 分开。普通 chat 可读取限量上下文，但 history 只包含 user/assistant；chat 与 clear history 不改变 relationship、memory 或 profile；relationship/memory 操作也不触碰 profile/history。PK-200 conversation 源码未出现 `affection_memory`、relationship/memory repository 或个人路径反向导入。
- Context Provider：公共 surface 只有 `get_context`；最多条数、逐条字符和总字符限制均生效，private/secret/no_context 标签被过滤，不输出 memory ID、时间戳、完整事件历史或状态对象。内容区明确标记“资料，不是指令”。Provider 损坏读取异常由 PK-200 固定短日志降级为空，不进入模型 messages、history、HTTP 错误或日志。
- 空 Provider：直接构造不带 PK-160 Provider 的 `ConversationRuntime` 可完成 fake chat 并维护 history，system prompt 不含 relationship/memory 内容，证明 PK-200 可独立工作。
- 零真实数据读取：在导入主应用并请求 `GET /api/v1/modules`、`GET /dashboard` 期间，对四条受保护候选路径安装 `io.open` 拦截器；输出 `api_import_protected_reads=0`、`catalog_protected_reads=0`、`dashboard_protected_reads=0`。测试前后仅以 `Test-Path` 确认两个 `server/data/*` 文件仍存在、两个 `server/systems/data/*` 候选仍不存在，没有读取内容、大小、时间戳或摘要。
- 控制台和 catalog：dashboard 只调用版本化 relationship/memory API，保留新增、事件选择、列表与单条删除；没有 reset/clear 控件。业务代码不使用 browser storage；公共 `panels.js` 只保存面板展开布尔值。catalog 的 namespace、全部新旧 endpoint、双文件 data owner、`main-api/in_process/modular/local_state` 与实现一致。

### 实际测试、编译与静态门禁

- 在 `server/` 下显式设置不存在的 `PROJECT_KEI_ENV_FILE`、`PROJECT_KEI_LLM_PROFILE_PATH`、`PROJECT_KEI_VOICE_PACK_REGISTRY` 和虚构 `LLM_API_KEY`，逐项执行 `.\.venv-asr\Scripts\python.exe`：
  - `tests\test_affection_system.py`
  - `tests\test_memory_system.py`
  - `tests\test_affection_memory_module.py`
  - `tests\test_conversation_module.py`
  - `tests\test_conversation_consumers.py`
  - `tests\test_feature_catalog.py`
  - `tests\test_dashboard_shell.py`
- 七项全部退出 0。`test_affection_system.py` 默认 demo 使用 `TemporaryDirectory`，未执行 `--status/--event/--choose/--reset` 等真实默认路径分支。conversation 两项回归的 focus runtime `PermissionError` 是既有模块隔离提示，全部断言通过。
- 独立并发/原子/隔离/Provider 组合夹具退出 0；主应用同 service/空 Provider/反向依赖夹具退出 0；错误体、日志和 Provider 故障脱敏夹具退出 0；受保护路径 open 拦截夹具退出 0。
- 恶意 Origin 夹具和 legacy active event 夹具分别按安全期望稳定退出 1，输出见两项阻断。所有标记和状态均为临时硬编码虚构数据。
- `.\.venv-asr\Scripts\python.exe -m compileall -q features\affection_memory features\conversation core\memory_store.py systems\affection_system.py features\catalog api.py ...` 覆盖实现及七项测试，退出 0。
- 对 `server/static/dashboard/*.js` 全部执行 `node --check`；从 `dashboard.html` 以显式 UTF-8 提取内联 module script 后执行 `node --input-type=module --check -`，全部退出 0。
- `server\.venv-asr\Scripts\python.exe scripts\check_task_docs.py` 在本报告写入前输出 `task documentation gate passed: 20 gated task(s)`。PK-900 为“进行中”，不计入完成门禁。
- 对 affection_memory、conversation、API、catalog、compatibility、dashboard、PK-160/PK-900 任务和总板明确文本路径执行尾随空白检查，无匹配。
- 按用户明确要求，本批没有运行任何 Git 命令，包括只读 `git status` 和 `git diff --check`；这意味着无法提供基于 Git index 的本批 hunk/行尾和受保护文件状态证明，是本次失败报告的已知流程限制，不把未执行项宣称为通过。

### 数据隔离、风险与工作区排除

- 所有状态写入、损坏、并发、新旧 API、CORS、Provider 和 profile/history 隔离夹具只使用 `TemporaryDirectory`、fake client 与 ASGITransport；没有建立外部 socket，没有启动应用 lifespan。
- 未读取、打印、diff、迁移、重置、覆盖、清空或计算真实 `server/data/affection_state.json`、`server/data/memories.json` 的内容/摘要；未创建 `server/systems/data` 同名文件。没有调用危险 legacy reset/clear 的真实路径。
- 未调用真实或付费 LLM、TTS、ASR、QQ、外部采集或生产写操作；没有读取 `.env` 值或真实 profile。所有 Key、个人文本和底层异常均为硬编码虚构标记。
- 没有修改 relationship、memory、conversation、API、catalog 或 dashboard 业务代码。来源、voice、calendar、demon、focus、QQ、个人状态、`vendor/` 和其他混合工作区内容全部排除，也未执行暂存、提交、推送、发布或清理。
- repository 的共享路径锁只覆盖同一 Python 进程；本轮两个 service 实例的线程并发通过，不宣称跨进程锁能力。危险 legacy `/affection/reset`、`/memories/clear` 仍仅为兼容保留且控制台不暴露；整改 Origin guard 时需把它们纳入同一保护。

### 本批文档门禁状态

- [x] TASK_RECORD — 已保留全部历史并追加本批范围、通过项、两项阻断、命令、隔离、风险、流程限制及最小整改范围。
- [x] TASKS_BOARD — PK-900 保持“进行中”；PK-160 保持“待集成”，名称、P2 和 PK-001/PK-200 依赖不变。
- [x] PUBLIC_README — 已核对现有 PK-160 公开说明；当前两项是实现偏离，失败验收不把 README 改写为已具备错误能力。
- [x] MODULE_CATALOG — 已核对 endpoint、namespace、data owner、进程、权限和 dashboard surface；目录回归通过，阻断一发生在实际访问控制边界。
- [x] ARCHITECTURE_DOCS — 已核对双 repository、同 service 兼容、只读 Provider 和单向依赖；阻断二是旧状态兼容实现偏离，不改写架构约定。
- [x] LOCAL_README — 不适用：未改变或确认新的路径、端口、解释器、环境位置或启动器。
- [x] AGENT_RULES — 不适用：未改变 agent 规则；用户本轮明确禁止 Git 命令，已将与常规门禁的差异如实列为限制。
- [ ] VALIDATION — 七项规定回归、正向逆向夹具、编译、JavaScript、文档门禁和明确路径空白检查通过；但两项安全/兼容逆向夹具失败，且用户明确禁止执行 `git diff --check`。待 PK-160 最小整改后由 PK-900 原夹具复验。

### 两项阻断整改独立复验（2026-07-22）

#### 复验结论

**通过。** PK-900 没有直接采用 PK-160 的整改自测结论：已重新审查 `security.py`、router、repository、主应用中间件顺序、README/架构说明和新增回归，并按初验相同条件独立重放恶意 Origin 与旧活动事件两条失败夹具。跨站读取、写入和预检现均在进入 repository 前拒绝；迁移前活动事件可稳定只读且不会自动改写文件，40 路 versioned/legacy 混合选择只结算一次；未知和篡改事件继续失败关闭。原两项阻断均已关闭，未发现新的 PK-160 集成阻断。

本轮 PK-900 改为“待集成”，提交 PK-000 最终复核。PK-160 继续保持“待集成”，本任务不自行把任一任务改为“已完成”。上方初验“不通过”、两项失败输出和当时的 `[ ] VALIDATION` 作为历史证据保留，不回写为初验已经通过。

#### 原阻断一复验：Origin、远端客户端与预检

- 主应用在通配 CORS 之后依次登记 PK-160 与 Voice Pack 中间件；按 Starlette 反向包裹顺序，`AffectionMemoryOriginGuardMiddleware` 位于 CORS 外层。它精确覆盖 `/api/v1/relationship*`、`/api/v1/memories*`、`/affection*`、`/memories*`，非本机 client 或非受信 Origin 在路由与 repository 前收到固定 403。router 的全部 status/event/choice/reset/list/add/delete/clear handler 又调用可注入的同一 guard。
- PK-900 原主应用夹具继续把两个 service repository 临时替换到 `TemporaryDirectory`，以本机 ASGI client 携带 `Origin: https://evil.example` 重放。结果：memory GET 403 且无 CORS 允许头、虚构个人标记不在响应；POST 预检 403 且无 CORS 允许头；实际 memory POST 403；relationship status 403；临时 relationship/memory 状态字节不变。
- 同一夹具确认 `Origin: http://127.0.0.1:8000` 返回 200，本机无 Origin legacy CLI 请求返回 200。独立远端 ASGI client `203.0.113.9` 对新旧 relationship/memory GET/POST/clear 六项均为 403，且没有创建临时状态文件。
- `test_affection_memory_module.py` 的扩展矩阵还覆盖全部新旧 status/event/choice/reset/list/add/delete/clear、POST/DELETE OPTIONS、`localhost:8000`、route-only 二次 guard 和拒绝时旧字节不变；完整测试通过。

#### 原阻断二复验：旧活动事件稳定只读兼容

- repository 对加载结果先做深拷贝，只接受与冻结 `EVENTS` 的 `id/title/scene/text/contexts/weight/voice_cue/choices` 逐字段一致且无未知字段的活动事件。缺少身份时由 event ID、合法 stats 和 history 数量派生 `legacy_` SHA-256 短身份；缺失时间只在加载副本中补空值，普通 load/status/context 不调用 save。
- PK-900 原旧 schema 夹具使用合法 stats、空 history 和没有 `instance_id/created_at` 的冻结活动事件。两次 service status 与 versioned/legacy HTTP status 返回同一稳定派生 ID，原始临时文件字节保持不变。
- 随后并发发送 40 个 versioned/legacy 混合 choice：结果恰好一项 `resolved`、39 项 `idle`，提交后 active event 为空、history 一条、affection 只增加一次到 60。
- 未知 event ID、修改冻结 text 和增加未知字段三类临时状态均抛出 `RelationshipStateError` 且原字节不变。显式非法 identity/时间由正式扩展回归继续覆盖。

#### 完整回归与静态验证

- 在 `server/` 下显式设置不存在的 `PROJECT_KEI_ENV_FILE`、`PROJECT_KEI_LLM_PROFILE_PATH`、`PROJECT_KEI_VOICE_PACK_REGISTRY` 和虚构 `LLM_API_KEY`，逐项执行：
  - `.\.venv-asr\Scripts\python.exe tests\test_affection_system.py`
  - `.\.venv-asr\Scripts\python.exe tests\test_memory_system.py`
  - `.\.venv-asr\Scripts\python.exe tests\test_affection_memory_module.py`
  - `.\.venv-asr\Scripts\python.exe tests\test_conversation_module.py`
  - `.\.venv-asr\Scripts\python.exe tests\test_conversation_consumers.py`
  - `.\.venv-asr\Scripts\python.exe tests\test_feature_catalog.py`
  - `.\.venv-asr\Scripts\python.exe tests\test_dashboard_shell.py`
- 七项全部退出 0。affection 默认 demo 继续只用临时 store；conversation 两项只输出既有 focus runtime 沙箱 `PermissionError` 的模块隔离提示，全部断言通过。
- `.\.venv-asr\Scripts\python.exe -m compileall -q features\affection_memory features\conversation core\memory_store.py systems\affection_system.py features\catalog api.py ...` 覆盖实现及七项测试，退出 0。
- `request.js`、`notifications.js`、`panels.js`、`registry.js`、`module-loader.js`、`app.js` 分别执行 `node --check`，六项退出 0；dashboard shell 内联脚本检查随测试通过。
- 报告写入前 `server\.venv-asr\Scripts\python.exe scripts\check_task_docs.py` 输出 `task documentation gate passed: 20 gated task(s)`；PK-900 改为“待集成”并写入本节后复跑，输出 `task documentation gate passed: 21 gated task(s)`。明确相关 `.py/.js/.html/.md` 路径尾随空白检查无匹配。
- 上游整改记录声明其 `git diff --check` 退出 0且只有既有换行提示；但 PK-900 继续遵守用户本批原始“不要执行 Git 操作”约束，没有独立重跑任何 Git 命令，因此只把该项列为上游证据，不冒充 PK-900 独立命令结果。该授权限制不再对应产品缺陷，不阻塞两条原失败夹具的通过判定。

#### 数据隔离、风险与工作区排除

- 两条原夹具、远端 client 探针、新增正式回归均只使用 `TemporaryDirectory`、虚构标记、fake client 与 ASGITransport；未启动真实 lifespan、外部 socket、LLM、TTS、ASR、QQ、采集或生产写操作。
- 测试前后只以 `Test-Path` 确认 `server/data/affection_state.json`、`server/data/memories.json` 存在而两个 `server/systems/data` 同名候选不存在。未读取、打印、diff、迁移、格式化、摘要、reset、clear、覆盖或写入真实个人文件。
- 单主 API 进程内路径锁仍是既有限制，本轮没有扩展跨进程写协议。危险 legacy reset/clear 仍保留兼容，但已被同一 local client/Origin 边界保护且控制台不暴露。
- conversation、voice、calendar、demon、focus、QQ、来源、其他个人状态、`vendor/` 和混合工作区其他修改继续排除；PK-900 仅编辑本报告与总板状态，没有执行 Git 暂存、提交、推送、PR、发布或清理。

#### 本轮八项文档门禁

- [x] TASK_RECORD — 保留初验失败证据并追加整改代码结论、原夹具输出、完整回归、隔离、风险、限制及最终通过结论。
- [x] TASKS_BOARD — PK-900 同步为“待集成”；PK-160 继续保持“待集成”等待 PK-000。
- [x] PUBLIC_README — 已核对本机/Origin 双重保护、旧活动事件只读兼容和不自动改写语义，与当前实现一致。
- [x] MODULE_CATALOG — namespace、endpoint、data owner、`local_state`、进程与 dashboard surface 未变化；catalog 回归通过。
- [x] ARCHITECTURE_DOCS — 已核对 PK-160 外层中间件、router 二次 guard、冻结事件归一化、单向 Provider 与双 repository 边界一致。
- [x] LOCAL_README — 不适用：未改变本机路径、解释器、端口、环境位置或启动器。
- [x] AGENT_RULES — 不适用：未改变 agent 工作流、安全、验证、文档或 Git 规则。
- [x] VALIDATION — 两条原失败夹具、远端 client 探针、七项规定回归、compileall、六项 JavaScript、文档门禁和明确路径空白检查全部通过；Git 差异检查仅采用上游已记录结果，PK-900 因用户明确禁止 Git 操作未独立重跑，并已如实记录。

### PK-000 最终独立复核（2026-07-22）

**结论：通过。** 总控没有只采信 PK-900 报告：重新读取实现与测试，独立重跑七项规定回归，并使用临时双 repository 主动复现原子替换失败、32 路重复事件结算、relationship/memory 清除隔离和只读 Context Provider。两类保存失败均保留旧字节且无临时文件残留；并发事件只结算一次；两类个人状态互不越界；Provider 不写状态、不暴露内部对象、ID、时间戳或私密标签内容。

总控静态扫描确认 `server/features/conversation/**` 不反向导入 PK-160、其 service/repository 或个人数据路径；应用仅在 composition root 注入既有 `ConversationContextProvider`。恶意 Origin、远端客户端、预检、Provider 故障和错误正文脱敏由通过的正式回归覆盖。七项测试、相关 `compileall`、六项 dashboard JavaScript 检查、任务文档门禁与总控独立 `git diff --check` 均通过。

真实 `server/data/affection_state.json`、`server/data/memories.json` 只做存在性和定向 Git 状态检查：文件存在且状态无输出；未读取、打印、diff、迁移、reset、clear、覆盖或写入内容。两个旧 `server/systems/data/*` 候选不存在。其他个人状态、缓存、环境文件、来源、voice、calendar、demon、focus、QQ、`vendor/` 与混合工作区修改均排除。本次仅更新 PK-160、PK-900 的任务记录和总板状态，未执行暂存、提交、推送、发布或清理。

## PK-170 健身打卡集成验收批次（2026-07-22）

### 入场登记

- 本节追加于此前全部批次、整改与 PK-000 最终结论之后，不覆盖、折叠或改写任何历史。当前验收对象仅为 PK-170 及其必要的 API、catalog、dashboard、legacy Python 和可选奖励音频接缝。
- PK-170 入场状态为“待集成”；PK-900 已从上一批“已完成”临时改为“进行中”，总板依赖同步为 `PK-170（本批次）`。入场不代表通过，PK-170 不由本任务改成“已完成”。
- 验收重点为唯一生产状态路径、真实个人文件零读取/迁移/写入、新旧 API 同 service、同日与并发幂等、6/12 天奖励和断签 streak、原子失败/损坏状态、status/dashboard/catalog 零写零网络、versioned 核心零 TTS、浏览器零业务存储及混合工作区排除。
- 所有状态写入、损坏、并发、API 和奖励验证必须显式使用 `TemporaryDirectory` 中的 `FitnessRepository` 与虚构日期/备注/音频；不得启动真实 lifespan、调用真实 LLM/TTS/QQ/采集或生产写操作。
- 用户明确要求不执行 Git 操作，本轮不运行 `git status`、`git diff`、`git diff --check`、暂存、提交、推送或清理。改用明确路径源码审计、受保护路径 `Test-Path`、open 拦截、文本尾随空白检查与任务文档门禁；不把未执行的 Git 检查宣称为通过。

### 验收结论

**通过。** PK-170 的生产 composition、repository/service/router 分层、新旧兼容入口、控制台和 catalog 与任务契约一致。独立正向、逆向和并发夹具均未发现集成阻断；本轮没有修改 PK-170 产品实现。PK-900 改为“待集成”，PK-170 继续保持“待集成”，等待 PK-000 最终复核，不自行标记“已完成”。

### 实现与契约核验

- 唯一生产路径同时由 `features/fitness/repository.py` 的 `DEFAULT_STORE` 与 `api.py` 的 `FITNESS_STATE_PATH` 固定为 `server/data/fitness_checkins.json`；主应用只构造一个注入该路径的 `FitnessRepository`/`FitnessService`。`systems/fitness_checkin.py` 仅重导出兼容门面，未拥有第二套规则或状态。源码定向扫描没有发现其他生产 `fitness_checkins.json` 所有者；`server/systems/data/fitness_checkins.json` 不存在。
- 入场只使用 `Test-Path` 确认真实文件存在以及旧候选不存在；随后以 `Path.open` 拦截器保护真实路径，在 catalog/dashboard 隔离探针中若发生打开即失败。未读取文件内容、大小、时间戳或摘要，未迁移、复制、reset、覆盖、创建第二份状态，也未把真实文件注入测试。
- `/api/v1/fitness/status` 与 `/fitness/status` 共用同一个 `status_handler`；`/api/v1/fitness/checkins`、`/fitness/checkin` 和仅保留兼容的 `/fitness/reset` 共用同一个注入 service/repository。主应用路由表和 catalog 的五个 endpoint、namespace、data owner、failure mode 与实现一致。
- repository 按规范化路径共享进程内 `RLock`，在一个锁域内执行读改写；保存使用同目录唯一临时文件、`flush/fsync` 和 `os.replace`。替换失败清理临时文件并保留旧字节；损坏 JSON、错误根结构和篡改奖励明确失败，不会回落为空状态再覆盖。
- service 按唯一合法自然日计算累计和连续天数，同日重复不覆盖首次备注。正式测试的 24 路并发和 PK-900 的 40 路并发均只有一次 `checked_in` 与一次 `reward_unlocked`；连续 6 天、12 天分别发奖，断签后 streak 从 1 重新累计，重复请求不重复发放。
- status 对不存在的临时 store 不创建文件，对已有 store 读取前后字节一致。PK-900 在同步 service/catalog/dashboard 段禁止 socket connect，在异步 HTTP 段使用 `ASGITransport` 并拦截高层外连入口；没有网络访问。版本化 check-in 响应不含音频字段且 fake audio 调用次数为 0；只有 legacy 新解锁奖励且 `with_audio=true` 时保留可选 TTS 接缝。
- 控制台保留既有健身 DOM、备注输入与打卡按钮，只调用版本化 status/check-in。内联业务脚本不含 `localStorage`/`sessionStorage`；公共 `panels.js` 只保存 `project-kei.dashboard.panel-open.v1` 下的面板展开布尔值，不保存打卡、备注、streak 或奖励。

### 独立逆向过程与结果

- 首次自建夹具错误地把断签后 11 个连续日断言为 12，命中普通 `AssertionError`；修正为连续 12 天后业务断言通过。第二次为证明零网络而全局拒绝 `socket.connect`，误拦截 Windows `asyncio` 创建本机 socketpair；改为异步段只拦截高层外连并继续使用 `ASGITransport`。第三次业务、并发、原子和 HTTP 段已通过，但 catalog 返回字典而夹具误按对象读取 `.key`；改用 `catalog["modules"]` 后隔离探针通过。这三次均是 PK-900 临时夹具错误，不是产品失败，没有接触生产状态。
- 校正后的独立业务夹具通过：断签后 6 天重新发放里程碑、随后 12 天里程碑正确；40 路跨 service 实例同日请求只提交/发奖一次；status 零写；`os.replace` 失败保留旧字节；损坏状态的读写均失败关闭；新旧 status 完全一致；版本化奖励解锁不调用 fake TTS，随后 legacy 重试也不补发音频。
- 校正后的 path/catalog/dashboard 夹具在真实 fitness 路径 open 即失败、socket connect 即失败的条件下通过：catalog 含 fitness，dashboard 只引用版本化接口且内联脚本无浏览器业务存储，默认路径精确指向冻结文件，旧候选路径不存在。

### 实际命令与验证结果

- `server/.venv-asr/Scripts/python.exe server/tests/test_fitness_checkin.py`：通过，输出 `fitness legacy compatibility tests passed`。
- `server/.venv-asr/Scripts/python.exe server/tests/test_fitness_module.py`：通过，输出 `fitness module tests passed`。
- `server/.venv-asr/Scripts/python.exe server/tests/test_feature_catalog.py`：通过，输出 `feature catalog tests passed`。
- `server/.venv-asr/Scripts/python.exe server/tests/test_dashboard_shell.py`：通过，输出 `dashboard shell tests passed`；同时覆盖控制台内联脚本和静态入口语法检查。
- `server/.venv-asr/Scripts/python.exe server/tests/test_focus_dashboard.py`：相关公共外壳回归通过，输出 `focus dashboard tests passed`。
- 两个经校正的 PK-900 临时 stdin 夹具分别输出 `PK-900 independent streak/race/atomic/API checks passed` 与 `PK-900 catalog/dashboard/path isolation checks passed`；状态只写系统 `TemporaryDirectory`，网络只用进程内 ASGI fake。
- 设置系统临时 `PYTHONPYCACHEPREFIX` 后执行 `python -m compileall -q features\\fitness systems\\fitness_checkin.py api.py`：退出 0；没有把编译缓存写进业务目录。
- `node --check` 分别检查 `request.js`、`registry.js`、`panels.js`、`notifications.js`、`module-loader.js`、`app.js`：六项退出 0；dashboard 内联脚本由 `test_dashboard_shell.py` 的临时模块检查覆盖。
- 报告收口后执行 `server/.venv-asr/Scripts/python.exe scripts/check_task_docs.py`，输出 `task documentation gate passed: 22 gated task(s)`。随后对本批明确相关 `.md/.py/.html/.js` 路径执行尾随空白扫描，无匹配（`rg` 按“无匹配”返回 1）。用户明确禁止 Git 操作，因此未执行 `git diff --check`，也未执行任何其他 Git 命令；该流程限制不冒充通过项。

### 数据隔离、风险与工作区排除

- 所有写入、损坏、并发、原子失败与 API 夹具均显式构造系统临时目录下的 `FitnessRepository`，日期、备注、音频和异常均为虚构值。未启动生产 lifespan，未调用真实 TTS、LLM、ASR、QQ、采集或任何外部/付费服务。
- 真实 `server/data/fitness_checkins.json` 只做存在性判断并被 open 拦截保护；未读、未打印、未 diff、未摘要、未迁移、未 reset、未覆盖。relationship、memories、calendar、demon、focus、conversation、voice、来源、QQ、环境文件和其他个人状态均未纳入本批。
- repository 锁是符合当前单主 API 模块化单体拓扑的同进程路径锁，不宣称支持多个独立进程同时写同一 JSON。legacy reset 和奖励音频仍是既有兼容面，前者不提供版本化入口或控制台按钮，后者不属于版本化核心。
- 因用户禁止全部 Git 操作，本轮不能提供基于 index 的 hunk/未跟踪文件/行尾复核证明。混合工作区排除依据为明确负责路径、源码引用扫描和本轮实际编辑范围；PK-900 只修改本报告与总板状态，没有整理、覆盖或吸收其他模块修改。

### 本批八项文档门禁

- [x] TASK_RECORD — 已保留全部历史并追加范围、实现核验、独立夹具的失败修正过程、命令、隔离、风险、限制和通过结论。
- [x] TASKS_BOARD — PK-900 同步为“待集成”；PK-170 保持“待集成”，P2 与 PK-001 依赖不变。
- [x] PUBLIC_README — 已核对唯一数据路径、新旧接口、幂等/奖励/失败模式、零网络与版本化零 TTS 说明，与实现和结果一致。
- [x] MODULE_CATALOG — 已核对五个 endpoint、namespace、data owner、process、dashboard surface、网络副作用和失败模式；回归及 open/network 拦截探针通过。
- [x] ARCHITECTURE_DOCS — 已核对 fitness 分层、同 service 委托、路径锁/原子替换、数据边界和 legacy TTS 接缝；无 manifest/lifecycle 变更。
- [x] LOCAL_README — 不适用：未改变本机路径、端口、解释器、环境位置或启动器。
- [x] AGENT_RULES — 不适用：未改变长期工作流、安全、验证、文档或 Git 规则；用户本批禁用 Git 已按更严格限制执行并记录。
- [x] VALIDATION — 定向测试、catalog/dashboard/focus 回归、两组独立逆向夹具、隔离编译、六项 JavaScript 和文档门禁均通过；`git diff --check` 因用户明确禁止 Git 操作未执行并如实列为限制。

### PK-000 最终复核退回（2026-07-22）

**结论：不通过。** 总控独立重跑五项规定回归并执行额外临时夹具：路径唯一性、同日/40 路并发幂等、6 天奖励防重复、断签、原子替换失败、新旧 status、status/控制台零写和版本化零 TTS 均通过；但 PK-900 报告所称“损坏状态的读写均失败关闭”并不覆盖奖励语义损坏后的 check-in 写路径。

临时状态包含类型和结构均合法、但 `text` 与既有六日奖励不一致的 reward。`FitnessRepository.validate()` 只检查字段类型，`FitnessService.check_in()` 在 mutation 中直接读取 reward key 并保存新增打卡，没有调用 status/reset 使用的 `_unique_rewards()` 语义校验。实际复现为 `tampered_write_blocked=False`、`old_bytes_preserved=False`；真实个人文件未参与。

责任限定为 PK-170 repository/service 及定向测试：任何保存前必须先验证已有 reward 的 date/streak/key/text 业务不变量；补充 semantic-tamper → versioned/legacy check-in → 固定脱敏错误、旧字节不变、无临时文件回归。不得借机改变接口、奖励规则、日期策略、控制台或其他模块。修复后由 PK-900 只重放该失败夹具与必要回归，再提交总控；当前 PK-170、PK-900 均为“进行中”。

总控仅以 `Test-Path` 和定向 Git 状态确认真实 `server/data/fitness_checkins.json` 存在、旧候选不存在且两者无状态输出；未读取、打印、diff、迁移、reset 或覆盖真实内容。未执行暂存、提交、推送、发布或清理。

### PK-000 整改后最终独立复验（2026-07-22）

**结论：通过。** 总控检查实际修复后确认 `FitnessService.check_in()` 在任何打卡变更前调用 `_unique_rewards()` 验证全部已有奖励，并仅使用验证后的去重快照进行奖励幂等判断；完全重复的合法奖励仍保持只读兼容，不会被静默整理。

上次原样失败夹具现得到 `tampered_write_blocked=True`、`old_bytes_preserved=True`、`temporary_files=0`。独立 ASGI 夹具对 versioned 与 legacy check-in 重放同一篡改奖励状态，两者均返回固定脱敏 500，未泄露虚构奖励、临时路径或堆栈，目标字节保持不变。正式测试还覆盖非法奖励日期、非 6 倍数 streak、key/里程碑不一致和篡改文本四类 service/HTTP 写入失败。

五项规定回归、相关 `compileall`、六项 dashboard JavaScript、任务文档门禁与 `git diff --check` 全部通过；此前已通过的路径唯一性、并发幂等、奖励防重复、断签、原子失败、新旧接口与控制台零副作用没有回归。真实个人状态仍只做存在性和定向 Git 状态检查，未读取或修改。本次仅更新任务记录和状态，未暂存、提交、推送、发布或清理。

## PK-140 QQ bridge 与定时推送集成验收批次（2026-07-22）

### 入场登记

- 本节追加于此前全部批次、退回整改和 PK-000 最终结论之后，不覆盖或改写历史。当前验收对象仅为 PK-140 的 Node QQ sidecar、主 API qq-control、两类 scheduler、控制台、catalog、文档和必要的 PK-110/PK-200 兼容接缝。
- PK-140 入场保持“待集成”；PK-900 已从上一批“已完成”临时改为“进行中”，总板当前批次同步为 PK-140。入场不代表通过，PK-140 不由本任务改成“已完成”。
- 已重新阅读根 README、AGENTS、本机 README、TASKS、PK-140 任务记录、QQ bridge 专项架构、模块化单体相关边界与 PK-110 缓存/HTTP 契约。用户明确禁止 Git 操作，本轮不执行 `git status`、`git diff`、`git diff --check`、暂存、提交、推送或清理；不把未执行的 Git 检查宣称为通过。
- 真实 `server/qq_bridge/.env`、两份生产 schedule 和两份 sidecar runtime state 只允许基于任务冻结路径做存在性判断，不读取内容、大小、时间戳或摘要。所有 API repository、进程、WebSocket、HTTP、clock、timer、sender 和状态写入验证必须显式注入 fake 与系统临时目录。
- 本轮不会启动 `src/index.mjs`、BAT、真实 Gateway/Token/QQ、真实 Project Kei API lifespan、Collector、LLM 或依赖安装；不会访问 `node_modules` 内容、真实白名单、真实消息或其他个人状态。若发现缺陷，只记录 PK-140 的最小修复范围，不扩展其他模块契约。

### 验收结论

**不通过。** 规定回归、控制台/catalog、同源与秘密脱敏、启动并发、缓存发送分离、发送幂等和 timer/shutdown 行为均通过，但独立逆向检查发现两项数据完整性阻断：损坏的 Python schedule 可被更新接口静默覆盖；语义异常的 Node delivery state 会被当作健康状态并继续发送/改写。PK-140 与本批 PK-900 均保持“进行中”，等待限定范围整改后重放原失败夹具。

### 阻断一：损坏 schedule 可被 PUT 静默覆盖

- `QQScheduleRepository._read()` 能拒绝损坏 JSON，`get_daily_schedule()` 的只读测试也会失败关闭；但 `QQControlService.update_daily_schedule()` 与 `update_life_support_schedule()` 直接调用 save，不读取/验证现有文件。repository 的 read/save 还是两个独立锁操作，不能用简单的 service 层先读后写消除并发窗口。
- PK-900 使用临时 launcher、临时 `.env` 占位、临时 dependency 目录、fake process/Popen 和临时 daily/life 路径。将 daily 写为损坏 JSON 后分别调用直接 service、`PUT /api/v1/qq-control/schedules/daily-briefing` 和 legacy `PUT /dashboard/briefing/schedule`。
- 实际输出：`direct_corrupt_write_blocked=False`；versioned 与 legacy 均为 `status=200 old_bytes_preserved=False`。两个 HTTP 入口确实共用 service，但共同继承了同一个缺陷。真实 schedule 未参与。
- 最小整改：为两类 schedule 增加同一锁域内的 read/validate/mutate/save；存在的损坏 JSON、错误根结构、非法字段类型/时间/间隔或不允许的结构必须在任何临时文件创建前失败关闭。versioned/legacy PUT 返回固定脱敏错误，不含原内容、路径或异常；旧字节完全不变且无临时文件。不得改变 endpoint、合法 payload、时间策略或控制台。

### 阻断二：Node delivery state 缺少严格语义校验

- `loadStateFile()` 只确认 JSON 根为对象；scheduler 构造器只确认 `schema_version===1` 和 `prebuild/deliveries/slots` 是对象。它不验证日期/槽位 key、24 位哈希用户 key、delivery status/error_code、字段白名单、数量上限或秘密/正文形态字段。
- PK-900 分别构造临时 daily state 和 life state，保持 `schema_version=1` 与顶层容器类型合法，但加入完整 `FULL_FAKE_OPENID` key 及 `Authorization`/消息正文字段。使用 fake schedule、fake cache/reminder、fake sender、fake timer 和固定时钟启动并显式触发 send/deliver。
- 实际输出：`daily_semantic_corruption_blocked=false sends=1`、`life_semantic_corruption_blocked=false sends=1`。两类 scheduler 均把异常状态视为健康、执行一次 fake 发送并改写状态；这违反“损坏状态失败关闭”和状态只含哈希接收者/有限字段的契约。
- 最小整改：在启动前严格验证 daily 的 prebuild/deliveries 与 life 的 slots，至少固定日期/槽位格式、24 位小写十六进制接收者哈希、`sending|success|failed`、安全 error code、规定字段和 14 天/96 槽上限。任何未知字段、完整 OpenID、Token/Secret/Authorization/消息正文、非法 status/error code 或超界结构都应 `stateHealthy=false`，零 timer、零生成、零缓存读取、零发送、零写入并保留旧字节。不得自动清空、迁移或静默整理异常文件。

### 通过项与独立补充检查

- Python 正式测试确认 status/readiness 零写入且有限响应；缺 launcher、临时 env、Node 或临时 dependency 零创建/零 Popen；8 路并发 start 只有一次 fake Popen；固定 BAT 不复制 `.env.example`、不开编辑器、不执行 npm；正常原子替换失败保留旧字节并清理临时文件。
- versioned/legacy status、start 和两类 schedule 注册到同一 router/service/repository。独立 ASGI 矩阵确认：本机无 Origin 只读兼容，恶意 Origin 读取 403；无 Origin/恶意 Origin 写入、恶意 OPTIONS 预检和远端客户端均 403；额外 `Authorization`、OpenID 与虚构正文的请求固定 422 且不回显；有限 status 不含临时路径或虚构秘密。第一次矩阵因错误禁止合法响应字段名 `message` 而自失败，校正为检查虚构正文值后完整通过，不是产品缺陷。
- Node 正式测试确认 allowlist 在菜单/情报/按钮/conversation/sender 前，空白名单和重复 ID 零额外转发；QQ 401 恰好一次刷新重试；上游错误正文不进入异常；超长输入零调用；warning、URL、Token 和内部路径在 Markdown 中脱敏并限长。
- 每日预生成只调用显式 generate，发送只读缓存；缺缓存不补采。成功用户每日及生命维持每槽位跨 scheduler 重启不重发，失败用户可受控重试；状态只写 fake 测试路径。关闭、改期和重复 start 清理 timer；Gateway socket/heartbeat/reconnect 保持单例且 stop 后归零。
- 独立 in-flight shutdown 夹具在 cache/reminder Promise 尚未返回时调用 stop，随后释放 Promise；daily/life 均零发送、零状态文件、零 timeout/interval，验证 epoch 取消语义通过。
- 控制台保留启动图片、按钮和两类日程 DOM，只调用版本化 qq-control；公共浏览器存储仍仅为面板布尔展开状态。catalog 登记 sidecar 进程、完整新旧 endpoint、schedule/delivery data owner、网络和失败模式，与既有文档一致。

### 实际命令与结果

- `server/.venv-asr/Scripts/python.exe server/tests/test_qq_control.py`：7 项通过。
- `node --test tests/bridge_core.test.mjs tests/schedulers.test.mjs tests/state_gateway.test.mjs`：14 项通过。
- `test_daily_briefing_module.py`、`test_daily_briefing_summary_cache.py`、`test_conversation_consumers.py`、`test_feature_catalog.py`、`test_dashboard_shell.py`：五项全部退出 0；conversation consumer 只输出既有 focus runtime `PermissionError` 隔离提示，断言通过。
- PK-900 临时 Python 损坏 schedule 写入夹具：退出 1，得到阻断一证据；PK-900 临时 Node delivery semantic corruption 夹具：退出 1，得到阻断二证据。
- 校正后的 PK-900 qq-control 同源/脱敏 ASGI 矩阵：通过；scheduler in-flight shutdown Node 夹具：通过。
- 设置系统临时 `PYTHONPYCACHEPREFIX` 后对 `features/qq_control`、兼容 service、`api.py` 和定向测试执行 `compileall -q`：退出 0。`qq_bridge/src` 与 `qq_bridge/tests` 全部 `.mjs`、控制台目录全部 `.js` 分别执行 `node --check`：全部退出 0。
- 报告写入后运行 `server/.venv-asr/Scripts/python.exe scripts/check_task_docs.py`，输出 `task documentation gate passed: 21 gated task(s)`；对本批明确相关 `.md/.py/.mjs/.html` 路径执行尾随空白扫描，无匹配。用户明确禁止 Git 操作，因此未执行 `git diff --check` 或任何其他 Git 命令；该流程限制不冒充通过项。

### 数据隔离、风险与工作区排除

- bridge `.env` 未读取、未修改，也未执行存在性探测。四个冻结真实路径只执行精确 `Test-Path`：两份 schedule 与两份 runtime state 均存在；未读取内容、大小、时间戳、摘要或详细状态。
- 所有写入、损坏、HTTP、WebSocket、进程、clock、timer、fetch、conversation、briefing、reminder 和 sender 验证均使用系统临时目录与 fake。未运行 `src/index.mjs`、BAT、npm、真实 API lifespan、QQ Gateway/Token/发送、Collector、LLM、TTS 或外部网络。
- 未读取 `node_modules` 内容，未安装/更新/删除依赖。PK-110、PK-200、conversation、voice、来源、个人状态和混合工作区其他模块均未修改；本轮只更新 PK-140/PK-900 任务记录与总板状态。
- 既有 at-most-once reservation 的崩溃窗口仍是已记录限制：`sending` 在重启后不自动重发，可能需人工确认。它不是本轮新增阻断；本轮不得借整改改变为 at-least-once 或扩展 QQ 平台事务。
- 因用户禁止全部 Git 操作，本轮无法提供基于 index 的 hunk、未跟踪文件和 `git diff --check` 证明。工作区排除依据为明确负责路径、源码引用与实际编辑范围，不声称完成了 Git 差异审计。

### 本批八项文档门禁

- [x] TASK_RECORD — 保留历史并追加本批范围、两项阻断、原始输出、通过项、命令、隔离、风险和最小整改范围；PK-140 同步退回记录。
- [x] TASKS_BOARD — PK-140 与 PK-900 均保持“进行中”；PK-140 名称、P1 和 PK-001/PK-110 依赖不变。
- [x] PUBLIC_README — 已核对公开 QQ 控制、预生成/缓存发送、幂等、状态和安全说明；当前实现对损坏写保护有偏离，不把 README 改写成允许该缺陷。
- [x] MODULE_CATALOG — endpoint、namespace、sidecar 进程、data owner、网络副作用和失败模式已核对；目录回归通过，阻断发生在实际状态校验。
- [x] ARCHITECTURE_DOCS — 已核对进程边界、同 service、原子 schedule、严格 Node state、at-most-once 和 timer 语义；两项阻断均是实现偏离，不修改架构契约。
- [x] LOCAL_README — 不适用：未改变或确认新的本机路径、端口、解释器、环境位置或启动器。
- [x] AGENT_RULES — 不适用：未改变长期工作流、安全、验证、文档或 Git 规则；用户禁用 Git 已按更严格限制执行。
- [ ] VALIDATION — 正式回归、编译、JavaScript、同源/脱敏和 shutdown 夹具通过，但两项独立数据完整性夹具失败；`git diff --check` 依用户要求未执行。待 PK-140 最小整改后由 PK-900 原夹具复验。

### 两项阻断整改独立复验（2026-07-23）

#### 复验结论

**通过。** PK-900 未直接采用 PK-140 的整改自测结论：已重新审查 repository/service/router、Node state validator、两类 scheduler、正式新增测试和公开文档，并按初验相同数据形态重放损坏 schedule 与语义异常 delivery state 两组失败夹具。两项原阻断均已关闭，未发现新的 PK-140 集成阻断。PK-900 改为“待集成”，PK-140 保持“待集成”，提交 PK-000 最终复核；上方初验“不通过”和 `[ ] VALIDATION` 作为历史证据保留，不回写成初验已经通过。

#### 原阻断一复验：损坏 schedule 写保护

- repository 已移除无校验的公开 save 路径。`replace_daily()`/`replace_life_support()` 在各自同一个 `RLock` 内调用 `_read_unlocked()`，对存在的旧文件执行 service 注入的完整语义 validator，只有验证通过才创建临时文件并原子替换；因此不存在 service 层 read/validate/save 分锁竞态窗口。
- daily validator 固定字段白名单、严格布尔、合法 `HH:MM`、生成早于发送和可选合法更新时间；life validator固定字段白名单、严格布尔/整数、合法时间窗、正间隔和可选合法更新时间。损坏 JSON、错误根结构、未知字段或非法语义在临时文件创建前抛有限 `ScheduleStateError`。
- PK-900 使用与初验相同的临时损坏 daily JSON，以及带虚构 `Authorization` 字段的临时 life JSON，分别重放直接 service、versioned PUT 与 legacy PUT。实际输出：`direct_corrupt_write_blocked=True`、`versioned_legacy_fixed_409=True`、`old_bytes_preserved=True temporary_files=0`。
- 四个 HTTP 写入口均返回固定 `409 {"detail":"schedule_state_invalid"}`，未回显虚构字段、临时路径或底层异常。合法日程更新与原子替换失败保留旧字节的正式回归继续通过。

#### 原阻断二复验：Node delivery state 严格失败关闭

- `state_store.mjs` 现提供 plain-object/精确字段、真实日期/槽位、24 位小写十六进制用户哈希、安全错误码与 delivery record validator。daily 额外严格校验空或合法 prebuild；两类 scheduler 分别限制 14 天与 96 槽，拒绝未知字段、完整 OpenID 形态键、秘密/正文、非法日期/槽位、非法状态/error code 和超界容器。
- scheduler 构造时把 `loadStateFile` 与完整语义 validator 共同决定 `stateHealthy`。`start()` 在任何 `fetchSchedule` 和 refresh timer 前检查该值；`refreshSchedule`、prebuild/send/deliver 和 persist 也各自二次检查。因此异常状态不会建立 timer，也不会进入缓存、生成、发送或写入。
- PK-900 原样构造含 `FULL_FAKE_OPENID`、`Authorization` 或消息字段的临时 daily/life `schema_version=1` 状态，并注入 fake schedule/cache/reminder/sender/timer。实际输出：`daily_semantic_corruption_blocked=true schedule=0 cache=0 generate=0 sends=0`、`life_semantic_corruption_blocked=true schedule=0 generate=0 sends=0`、`old_bytes_preserved=true`；warning 仅为固定 `daily_state_corrupt`/`life_support_state_corrupt`。
- 正式 Node 扩展矩阵进一步覆盖 daily 7 类、life 6 类篡改，包括非法日期/槽位、非法状态/error code、顶层与 prebuild 秘密字段以及 14/96 上限；逐项验证零 schedule 网络、零 timer/生成/缓存/发送/写入和旧目录不变。

#### 完整回归与静态验证

- 在 `server/` 下执行 `tests/test_qq_control.py`：8 项通过。
- 在 `server/qq_bridge/` 下执行 `node --test tests/bridge_core.test.mjs tests/schedulers.test.mjs tests/state_gateway.test.mjs`：29 项通过。
- `test_daily_briefing_module.py`、`test_daily_briefing_summary_cache.py`、`test_conversation_consumers.py`、`test_feature_catalog.py`、`test_dashboard_shell.py` 全部退出 0。conversation consumer 仍只输出既有 focus runtime 的隔离 `PermissionError` 提示，所有断言通过。
- 设置系统临时 `PYTHONPYCACHEPREFIX` 后对 `features/qq_control`、兼容 service、`api.py` 和定向测试执行 `compileall -q`：退出 0。`qq_bridge/src`、`qq_bridge/tests` 全部 `.mjs` 与 dashboard 目录全部 `.js` 逐文件执行 `node --check`：全部退出 0。
- 定向文档核对确认 README、`docs/architecture/qq-bridge.md` 与 bridge README 已准确记录同锁域 mutation、固定 `schedule_state_invalid`、严格 Node state Schema、失败关闭和既有 at-most-once 限制；接口、控制台、PK-110 与 PK-200 契约未变化。
- 报告写入后复跑 `server/.venv-asr/Scripts/python.exe scripts/check_task_docs.py`，输出 `task documentation gate passed: 23 gated task(s)`；对本批明确相关 `.md/.py/.mjs/.html` 路径执行尾随空白扫描，无匹配。用户本批明确禁止 Git 操作，因此 PK-900 未执行 `git status`、`git diff --check` 或任何其他 Git 命令；上游记录的 Git 结果不冒充 PK-900 独立证据。

#### 数据隔离、风险与工作区排除

- 本次复验没有探测、读取或修改 bridge `.env`；没有重新读取四个真实 schedule/runtime state。所有损坏状态、HTTP、timer、cache、generation 和 sender 操作均使用系统临时目录、虚构标记、fake 与 ASGITransport。
- 未运行 `src/index.mjs`、BAT、npm、真实 API lifespan、QQ Gateway/Token/发送、Collector、LLM、TTS 或外部网络；未读取 `node_modules` 内容，也未安装、更新或删除依赖。
- 原有 at-most-once reservation 崩溃窗口继续保留：持久化 `sending` 后进程异常时不会自动重发，可能需人工确认。这是已接受的既有限制，本次修复没有改成 at-least-once 或扩大 QQ 平台事务。
- PK-110、PK-200、conversation、voice、来源、个人状态和混合工作区其他模块继续排除。PK-900 仅更新本报告与总板状态，没有执行暂存、提交、推送、发布或清理；因禁用 Git，仍不提供基于 index 的差异证明。

#### 本轮八项文档门禁

- [x] TASK_RECORD — 保留初验失败证据并追加实际修复审计、两条原夹具输出、完整回归、隔离、风险与通过结论。
- [x] TASKS_BOARD — 独立验收提交时 PK-900 与 PK-140 均保持“待集成”；PK-000 最终接受后两项已同步为“已完成”，PK-140 的 P1 与 PK-001/PK-110 依赖不变。
- [x] PUBLIC_README — 已核对同锁域 PUT、严格 state Schema、失败关闭、控制接口、重启要求和限制，与实际实现一致。
- [x] MODULE_CATALOG — namespace、完整新旧 endpoint、sidecar 进程、data owner、网络副作用和失败模式未变化；catalog 回归通过。
- [x] ARCHITECTURE_DOCS — 已核对 schedule mutation、固定错误、Node 深层语义校验、零副作用失败关闭和 at-most-once 边界一致。
- [x] LOCAL_README — 不适用：未改变本机路径、端口、解释器、环境位置或启动器。
- [x] AGENT_RULES — 不适用：未改变长期工作流、安全、验证、文档或 Git 规则；用户禁用 Git 已按更严格限制执行。
- [x] VALIDATION — 两条原失败夹具、8 项 Python、29 项 Node、五组消费者/目录/控制台回归、隔离编译和全部相关 JavaScript 语法均通过；PK-000 另行完成并发、同源、脱敏、in-flight shutdown、重启幂等和原子失败故障注入，并独立执行文档门禁与 Git 差异检查。

### PK-000 最终独立复核（2026-07-23）

**通过。** 总控没有只接受 PK-900 报告：已复查实际实现，重跑 8 项 Python、29 项 Node 与五组共享回归，并用临时路径/fake 独立复现白名单前置、秘密清洗、32 路并发启动单例、真实 client/Origin 防护、缓存只读发送、跨重启幂等、异步 shutdown 失效和原子 rename 失败保旧。两项返工阻断与本批全部重点均通过，PK-140 和本批 PK-900 正式关闭。

- 状态与文档：`TASKS.md`、PK-140 和 PK-900 均已同步为“已完成”；README、QQ bridge 架构、catalog、控制台和实现接口一致。
- 数据与副作用：未读取/修改真实 bridge `.env`、QQ 日程或 runtime 内容；未运行 sidecar/BAT/npm、Gateway/Token、真实 Project Kei lifespan、Collector、LLM、TTS 或 QQ 发送。受保护 schedule/runtime 仍为 ignored，私密配置 ignore 规则存在。
- 工作区：只更新本批任务记录与总板状态，保留混合工作区中的其他任务和个人修改；未执行 Git 暂存、提交、推送或清理。`git diff --check` 退出 0，仅有既有换行提示。
## 发布前总回归补充（2026-07-23）

- 发布审计排除了 `vendor/`、真实 `.env`/缓存以及 `server/systems/data/demon_slayer.json`、`focus_timer.json` 两份个人状态改动，并把准备提交文档中的本机测试路径改为可移植 `<TEMP>` 占位符。
- 总回归发现并修复 PK-140 legacy `qq_bridge_control` 注入参数兼容缺口；新版 `/api/v1/qq-control` 与生产装配不变，旧 helper 仅恢复测试/兼容调用面。修复后 `test_intel_source_config.py`、`test_qq_control.py` 及本批全部离线回归通过。
- 发布门禁最终包括：23 项任务文档门禁、40 组安全 Python 脚本回归、29 项 Node bridge 测试、Python compileall（本机 focus runtime 目录仅有权限提示、无源码编译错误）、全部 bridge/dashboard JavaScript 语法检查与 `git diff --check`。未运行 debug、麦克风、真实语音聊天、真实 QQ、真实采集或外部付费调用。

## PK-120 累计重新验收（2026-07-23）

### 验收结论

**通过。** 本轮按累计口径同时验收原用户资料、昵称、头像、今日言论及新增
发帖/回复分流，不另保留一份与本结论并列的旧 PK-120 验收结论。PK-120 恢复
“已完成”，本批 PK-900 关闭为“已完成”。

### 独立审计结果与修复

- RSS 分类的 `post/reply/repost/quote/unknown` 互斥；纯转发、冲突和 unknown
  不入缓存。回复只保留当前用户正文、当前回复 ID/链接/时间和可选被回复账号；
  `MockTransport` 对任何非 `/<handle>/rss` 请求立即失败，证明未补抓父帖或线程。
- 两个显式按钮仅调用各自 posts/replies fetch。profiles/posts/replies 普通 GET、
  页面初始化、Tab/折叠和来源 CRUD 只读本机数据；不同用户的 Tab、details open
  与被点击按钮 loading 由用户键/按钮实例隔离，同一时间只渲染一个栏目。
- 发帖/回复文件和 repository 独立；逐用户替换不覆盖其他用户或另一通道。
  当天去重、30 条上限、跨天空视图、损坏只读零写、原子失败保旧均通过。
- 主动审计发现并在 PK-120 内最小修复两项问题：Schema 1 当天发帖缓存原会被
  新 repository 当成空视图，现改为只读归一化且不写回；带 quote/quoted-tweet
  类名的引用块原会被判为 quote 却未完整剥离，现与 `<blockquote>` 一并移除。
  两项均有新增临时 fixture，旧字节与被引用正文隔离断言通过。
- profile 昵称/头像、来源分组、显式刷新、版本化 profile/posts API 与 legacy
  dashboard posts API 均保持；Collector `1.0` 与 `twitter` source ID 不变。
  Catalog replies 映射与实际路由一致，method/path 无重复，其他情报来源无冲突。

### 实际命令与结果

- `server/.venv-asr/Scripts/python.exe server/tests/test_x_monitor.py`：通过。
- 在 `server/` 下逐项运行：
  `test_intel_source_config.py`、`test_intel_sources_registry.py`、
  `test_bilibili_collector.py`、`test_bilibili_feature.py`、
  `test_youtube_collector.py`、`test_github_intel_collector.py`、
  `test_papers_collectors.py`、`test_rss_intel_collector.py`、
  `test_intel_sources_integration.py`、`test_daily_briefing_module.py`、
  `test_daily_briefing_summary_cache.py`、`test_feature_catalog.py`、
  `test_dashboard_shell.py`：全部退出 0。
- 对 `intel/collectors/twitter.py`、三个 X cache/service 文件、
  `features/x_monitor`、Catalog、`api.py` 与相关测试执行
  `python -m py_compile`：退出 0。dashboard 六个 `.js` 分别
  `node --check`：全部退出 0；内联 module 脚本由 dashboard 测试编译通过。
- 报告写入后运行 `server/.venv-asr/Scripts/python.exe scripts/check_task_docs.py`：
  通过；`git diff --check`：退出 0，仅有既有换行转换提示。

### 数据隔离、风险、限制与工作区排除

- X 专项使用 `MockTransport`、fake fetcher、固定 aware 时钟、
  `ASGITransport` 和系统临时目录；其他来源回归也只用 mock/fixture。未运行真实
  Nitter、Collector、LLM、TTS、QQ 或任何付费/生产请求。
- 未读取、打印、迁移、重置或修改真实 X 三份缓存、来源名单、`.env`、凭证或
  个人状态。`vendor/`、`server/systems/data/demon_slayer.json`、
  `server/systems/data/focus_timer.json` 与其他任务修改均未纳入本批。
- 同一通道的文件级并发写仍沿用现有单主 API 进程假设；本次未扩展跨进程锁或
  分布式抓取协议。该限制不影响本轮要求的逐用户/双通道与原子替换语义。
- 未执行 Git 暂存、提交、推送或工作区清理。代码部署后需重启主 API，除此之外
  无新增安装、进程、端口或本机配置要求。

### 本批八项文档门禁

- [x] TASK_RECORD — 已追加累计范围、独立证据、两项修复、命令、隔离、风险和结论。
- [x] TASKS_BOARD — PK-120 与 PK-900 已按累计验收结果同步为“已完成”。
- [x] PUBLIC_README — 双通道、只读行为、父帖限制及 Schema 1 兼容与实现一致。
- [x] MODULE_CATALOG — replies API、namespace、数据所有权和网络副作用核对通过。
- [x] ARCHITECTURE_DOCS — 引用块剥离、双缓存及旧 Schema 只读兼容已同步。
- [x] LOCAL_README — 不适用；本机路径、端口、解释器、环境位置与启动器未改变。
- [x] AGENT_RULES — 不适用；长期工作流、安全、验证、文档和 Git 规则未改变。
- [x] VALIDATION — 专项、八源、daily briefing、Catalog、dashboard、Python、
  JavaScript、文档门禁和 `git diff --check` 均通过。

## PK-120 撤销发帖/回复双通道独立验收（2026-07-24）

### 验收结论

**不通过。** 产品功能与全部正式回归通过，没有发现需要退回 PK-120 代码实现的
阻断；唯一阻断是 PK-900 验收过程未能保持全程真实数据零读取。PK-120 与 PK-900
因此保持“进行中”，不按本轮提前写成最终“已完成”。

### 产品与集成证据

- 控制台每个 X 用户只有一个“获取/刷新今日言论”按钮、一个按用户键维护 open
  状态的 `<details>` 列表；无 Tab、独立回复按钮或第二列表。界面明确声明普通
  RSS 可能不包含全部回复。
- active 代码无 replies service/import/API/dashboard state。专用文件
  `services/x_daily_replies.py` 不存在；replies 路由 404；单 repository 只接受
  `channel=posts`，其允许内容类型为 `post/quote/reply`。
- profiles/posts GET、页面加载、折叠和来源 CRUD 零 fake 网络；仅显式单用户
  posts fetch 调用一次 `/<handle>/rss`。普通 RSS 的三类用户正文统一进入
  `x_daily_posts.json` 语义，纯转发、冲突/unknown、引用正文和父帖关系正文被
  排除，不承诺 RSS 未提供的回复完整性。
- 昵称、头像、普通/信息差来源分组、逐用户折叠、legacy dashboard posts、
  versioned posts 与 Collector `1.0` 保持。使用显式临时 service/repository
  重建 versioned app 后，新旧 GET/fetch 结果一致；Catalog 无 replies endpoint，
  主应用 method/path 无重复。

### 实际命令与结果

- `server/.venv-asr/Scripts/python.exe server/tests/test_x_monitor.py`：通过。
- `test_intel_source_config.py`、`test_intel_sources_registry.py`、
  `test_intel_sources_integration.py`、`test_daily_briefing_module.py`、
  `test_daily_briefing_summary_cache.py`、`test_feature_catalog.py`、
  `test_dashboard_shell.py`：修正验收夹具后完整重跑，全部通过。
- 对 `intel/collectors/twitter.py`、X cache/service/router、Catalog、`api.py`
  和相关测试执行 `python -m py_compile`：通过。dashboard 六个 `.js`
  `node --check`：全部通过。active replies surface 扫描：无匹配。
- `server/.venv-asr/Scripts/python.exe scripts/check_task_docs.py`：通过，
  共检查 21 个当前处于“待集成/已完成”的任务；`git diff --check`：退出 0，
  仅有既有 LF/CRLF 转换提示。

### 数据隔离阻断

- 为增强 legacy/versioned 正向一致性测试，PK-900 首次直接请求已装配的
  `api.app`。实际版本化 router 在装配时闭包绑定默认
  `XMonitorService`/source loader，测试中的 `patch.object` 只替换 legacy
  handler。一次 `GET /api/v1/x/posts` 因而可能读取默认来源注册表和今日缓存；
  响应比较失败后立即停止，未执行 fetch POST。
- 此次只读响应未被打印或写入报告，未发生外部网络、删除、迁移、重置、原子
  替换或其他写操作。随后已把测试改为显式临时 registry/service 构建隔离
  versioned app，并在新进程全量重跑通过。
- 但“可能读取”无法在事后改写为“从未读取”，也不能通过探测默认文件是否存在
  来规避。因此本轮不满足用户第 6 项数据隔离门禁，不冒充通过。

### 风险、限制与工作区排除

- 旧 `x_daily_replies.json` 的 ignore 规则刻意保留，以免可能存在的历史本机
  文件暴露；当前运行时代码不再拥有它，本轮也未探测、读取或删除它。
- 单通道 repository 仍以单主 API 进程为并发边界；本轮不扩展跨进程协议。
- `vendor/`、两份已修改个人状态和其他模块差异均排除。未执行 Git 暂存、提交、
  推送、发布或工作区清理。

### 本批八项文档门禁

- [x] TASK_RECORD — 已记录产品结果、命令、污染过程、影响和未通过结论。
- [x] TASKS_BOARD — PK-120 与 PK-900 保持“进行中”。
- [x] PUBLIC_README — 单按钮/缓存、RSS 回复限制、接口与数据所有权一致。
- [x] MODULE_CATALOG — profiles/posts endpoint 与单缓存/显式网络边界一致。
- [x] ARCHITECTURE_DOCS — 单通道 repository、router 与 Collector 边界一致。
- [x] LOCAL_README — 不适用；本机路径、端口、解释器和启动器未改变。
- [x] AGENT_RULES — 不适用；工作流、安全、验证、文档和 Git 规则未改变。
- [ ] VALIDATION — 功能回归全部通过，但首次验收尝试可能读取默认本机数据，
  故本批数据隔离门禁不通过。

## PK-120 单通道数据隔离整改独立复验（2026-07-24）

### 验收结论

**通过。** 本轮是在上方“不通过”记录之后启动的新一轮独立隔离验收；旧记录与
首次可能只读默认来源/X 缓存的历史事实完整保留。本轮产品代码没有新增改动，
整改范围仅为集成夹具与任务记录。新的正式复验中，受保护路径零触发、系统临时根
之外零写入，PK-120 与本轮 PK-900 可以最终关闭为“已完成”。

### 夹具审计与独立逆向验证

- `check_legacy_and_versioned_origin_parity()` 的主应用请求集合静态禁止
  `/api/v1/*`，只向真实装配的 `api.app` 请求 legacy
  `/dashboard/intel-sources*`；legacy handler 使用临时 registry、临时 X/B
  service。versioned 来源、B 资料和 X 路由则只装配到新建的临时 `FastAPI`，
  X 路由显式绑定 `build_x_monitor_router(temp_service, temp_registry.read)`。
- `ProtectedPathTripwire` 在原始 I/O 前拦截默认来源名单、X profiles/posts、
  历史 replies、B 资料缓存、主 `.env` 与 fitness/calendar/demon/focus 状态，
  并审计 open/stat/lstat、临时文件、mkdir、unlink、rename、replace 及对应
  `os` 操作。正式双应用比对断言保护路径触发数为 0、临时根外写入数为 0；
  独立合成读写夹具均在原始 I/O 前得到预期 `AssertionError`。
- active runtime 逆向扫描没有 replies API、reply service、reply fetch 或第二
  cache channel；`services/x_daily_replies.py` 不存在，单 repository 对
  非 `posts` channel 失败关闭。dashboard 只以条目标签显示普通 RSS 已实际
  返回的 `reply`，没有第二按钮、Tab、列表、loading 状态或完整回复暗示。

### 实际命令与结果

- 单独运行隔离 legacy/versioned 正向比对：通过，输出
  `independent isolated legacy/versioned parity passed`。
- 单独运行 protected-path 合成读写回归：通过，输出
  `independent protected-path read/write tripwire passed`。
- 首次单函数 `runpy` 命令因测试目录未加入 `sys.path`，在导入
  `_path_setup` 前以 `ModuleNotFoundError` 退出；纠正命令后上述两项均通过。
  该失败调用未进入应用装配或业务文件 I/O。
- 在 `server/` 下逐项运行
  `tests/test_x_monitor.py`、`test_intel_source_config.py`、
  `test_intel_sources_registry.py`、`test_intel_sources_integration.py`、
  `test_daily_briefing_module.py`、`test_daily_briefing_summary_cache.py`、
  `test_feature_catalog.py`、`test_dashboard_shell.py`：八项全部退出 0。
- 对 `api.py`、X collector/cache/service/router、Catalog 与相关测试运行
  `python -m py_compile`：通过；`PYTHONPYCACHEPREFIX` 指向系统临时目录。
- 对 dashboard 的 `request.js`、`notifications.js`、`panels.js`、
  `registry.js`、`module-loader.js`、`app.js` 逐项运行 `node --check`：
  六项全部退出 0。
- 报告和状态写入后运行
  `server/.venv-asr/Scripts/python.exe scripts/check_task_docs.py` 与
  `git diff --check`：文档门禁通过 23 个受门禁任务，差异检查退出 0，仅有
  既有 LF→CRLF 转换提示。

### 数据隔离与副作用

- 所有正式动态验证仅使用系统临时目录、固定 aware clock、fake fetcher、
  Mock/ASGITransport；普通 GET 的 fake 网络计数为 0，只有两个显式 fetch
  分别调用同一 fake 一次。
- 本轮未探测受保护文件是否存在，未读取、打印、迁移、删除、覆盖或重置真实
  来源名单、X/B 缓存、`.env`、凭证或个人状态；未调用真实 Nitter、其他来源
  Collector、LLM、TTS、QQ 或付费服务。
- 没有进行浏览器实机回归：生产 dashboard 的普通初始化会读取本机缓存/来源，
  与本轮零真实数据读取门禁冲突；相同 DOM/API 契约已由 dashboard shell、
  临时 ASGI 应用和 fake 网络计数覆盖。

### 风险、限制与工作区排除

- 历史 `x_daily_replies.json` ignore 条目继续防止可能存在的旧本机文件暴露；
  运行时不拥有、不读取、不写入或删除它。单缓存文件仍以单主 API 进程为并发
  边界，未增加跨进程锁。
- `.gitignore`、README/架构、Catalog/API/dashboard/X 产品实现、PK-140、
  QQ bridge、`vendor/`、`server/systems/data/demon_slayer.json`、
  `focus_timer.json` 及其他混合工作区差异均排除。未执行 Git 暂存、提交、
  推送、发布或工作区清理。

### 本轮八项文档门禁

- [x] TASK_RECORD — 已追加新轮次范围、夹具审计、命令、隔离、风险和通过结论。
- [x] TASKS_BOARD — PK-120 与本轮 PK-900 已同步为“已完成”。
- [x] PUBLIC_README — 单按钮、单列表、单缓存、普通 RSS 限制与公开 API 一致。
- [x] MODULE_CATALOG — profiles/posts endpoint、所有权和显式网络条件与实现一致。
- [x] ARCHITECTURE_DOCS — 单通道 repository/router/Collector 边界与实现一致。
- [x] LOCAL_README — 不适用；路径、端口、解释器与启动器未改变。
- [x] AGENT_RULES — 不适用；长期工作流、安全、验证、文档和 Git 规则未改变。
- [x] VALIDATION — 隔离专项、八项 Python 回归、编译、六项 JavaScript、
  文档门禁与 `git diff --check` 均通过。

## PK-020 待独立验收（2026-07-25）

- 入场状态：PK-020 已完成实现方定向验证并标记“待集成”；本批 PK-900 仅登记为“待开始”，必须由新的独立对话领取，不沿用 PK-020 实现对话的判断。
- 核心范围：根 setup/doctor/start、PowerShell 5.1/7.4+、Python 3.10–3.12 x64 解析顺序、Node 20/22/24、根 `.venv`、五个安装 profile、Core 默认启动、旧 BAT/PS 兼容、Python/Node 锁、活动文档和 Windows CI。
- 首要证据：在 Python 3.11 x64、Node 22 的无缓存隔离环境实际执行 `.github/workflows/windows-install.yml` 等价流程；必须完成真实公开锁安装、Core import 和 ASGITransport `/` 健康检查。本批不得把实现方 fake pip/npm 测试、当前开发机 `.venv-asr`、`node_modules`、模型或配置当作该证据。
- 必跑：首次/二次 `setup.bat --profile core`、五 profile/失败注入专项、doctor 只读 tripwire、start fake 进程/端口 tripwire、PK-010/100/140/200/210/211/212 最小 Python 回归、QQ 46 项 Node 回归和 `src/*.mjs` 语法、PowerShell AST、Batch 路径/引号、活动路径/文档扫描、锁/manifest、文档门禁、`git diff --check`。
- 重点逆向：确认 doctor 不读取秘密/个人状态/模型/登记内容且不写入或联网；start 不运行 pip/npm/写 `.env`；Core 无配置/模型仍健康；voice/QQ 失败不终止 Core；setup 不下载大型资产/远程脚本；`server/.venv-asr` 只作验证后的迁移候选且从不被创建、删除或重建。
- 锁审计：核对三层精确版本与 manifest SHA-256、QQ lockfile v3/`npm ci`；在干净 Windows 索引解析中特别确认全部 Python 3.11 wheel/sdist 可用。任何解析漂移、缺包、隐式未固定传递依赖或私有/本机来源都退回 PK-020。
- 数据隔离：不得读取/diff/打印真实 `.env`、Token、Cookie、QQ Secret、LLM Key、白名单/用户 ID、个人状态/缓存/来源名单/profile、模型/参考音频/Voice Pack 注册表或外部 GPT-SoVITS 源码；不得扫描磁盘。所有动态证据只在临时副本、fake 服务/网络/进程与受保护路径 tripwire 下产生。
- 通过后职责：PK-900 才可把 PK-020 与本批 PK-900 标记“已完成”；不通过则写明可复现命令、最小失败证据和所属边界，退回 PK-020，不在集成对话顺带改写安装器或业务模块。

### PK-900 独立验收入场（2026-07-26）

- 已按顺序完整读取根 README、AGENTS、本机 README、任务总板、PK-020/900
  以及 PK-010/100/140/200/210/211/212 任务记录和 Windows 安装、模块化单体、
  可安装模块、QQ、voice、GPT-SoVITS、Voice Pack 架构说明；不继承实现对话的
  “通过”判断。
- 入场确认 PK-020 为“待集成”、PK-900 为“待开始”，登记依赖均为“已完成”；
  现将 PK-900 临时置为“进行中”，PK-020 保持“待集成”。
- 已先执行 `git status --short` 和任务相关差异统计。当前分支为
  `agent/intel-sources-dashboard`，工作区同时包含 PK-020、PK-140、情报、
  dashboard、个人状态和未跟踪 `vendor/` 等修改；本批只审计 PK-020 允许路径
  与必要兼容测试，不读取受保护文件内容，不重置、覆盖、整理、暂存、提交或推送。
- 后续动态证据只允许在临时隔离副本和新建 Python 3.11/Node 22 环境产生；不会
  使用或检查当前真实 `.venv`、`.venv-asr`、`node_modules` 的内容，也不会启动
  真实 API、QQ、ASR、TTS、Collector、LLM 或外部引擎。

### PK-020 独立验收结论（2026-07-26）

**结论：不通过。** 当前代码存在一项确定会让登记 Windows CI 失败的兼容回归，
以及一项会让安装专项测试可能读取真实 QQ runtime 的数据隔离缺口；同时本机不具备
Python 3.11 / Node 22 / PowerShell 7.4+，无法补齐清单要求的首要目标矩阵。
PK-020 已退回“进行中”，本批 PK-900 保持“进行中”，不提交 PK-000 关闭。

#### 阻断一：Windows CI 登记的 PK-140 最小回归确定失败

- 在不含真实数据、根目录名为 `project-kei` 的严格白名单临时副本中，使用本轮
  公开锁新建的 `.venv` 运行 `tests/test_qq_control.py`，实际结果为
  `Ran 8 tests`、`FAILED (failures=1)`。
- 失败用例为 `test_project_launcher_never_configures_or_installs`：测试仍断言
  `server/qq_bridge/start_qq_bridge.bat` 包含 `node src\index.mjs`，而当前文件
  已按 PK-020 文档冻结的统一入口契约委托根
  `start.bat --only qq --current-window`。
- `.github/workflows/windows-install.yml` 在 Python 3.11 / Node 22 流程第 97 行
  运行同一测试并在非零时退出，故这不是“本机没跑 CI”的推测；当前 workflow
  等价回归必然失败。
- 责任与最小范围：PK-020 的 QQ 兼容启动接缝及必要共享回归。只需让该测试验证
  新的薄委托契约、`%~dp0` 可移植根、参数/退出码透传、零 npm、零配置写入；
  不应恢复第二套直接 Node 启动规则，也不得改动 PK-140 业务行为。

#### 阻断二：安装专项夹具没有隔离受保护 QQ runtime

- `server/tests/test_windows_install.py::_copy_install_surface()` 对真实
  `server/qq_bridge` 使用递归 `shutil.copytree()`，忽略项仅为 `.env` 和
  `node_modules`。同仓库 `.gitignore` 明确保护 `server/qq_bridge/data/`，
  AGENTS 也把 QQ runtime state 列为不得读取、复制或输出的数据。
- 因此直接从共享工作区运行任务登记命令时，夹具可能在进入临时项目和 sentinel
  断言之前读取并复制真实 QQ runtime。PK-900 没有执行这个不安全入口；专项测试
  只在事先由验收方严格白名单构造、已排除 QQ data 的副本中运行。
- 责任与最小范围：PK-020 安装专项测试。复制安装表面应采用显式文件白名单，
  或至少完整排除 `data`、本机缓存和其他运行产物，并增加保护路径零触发断言；
  不需要改业务实现。

#### 强制版本矩阵与真实安装

- 本机只发现 `C:\Users\<user>\anaconda3\python.exe` 的 Python 3.12.7 x64、
  Node 24.18.0、npm 11.16.0 和 Windows PowerShell 5.1.26100.8875；
  `py.exe`、Python 3.11、Node 22 与 `pwsh.exe` 均不可用。按任务限制没有自动
  安装运行时，也没有提交/推送来触发远端 workflow。
- 因此清单首要证据——Python 3.11 x64、Node 22、PowerShell 5.1/7.4+ 的无缓存
  Windows 等价流程——未闭合。下面的 Python 3.12 / Node 24 结果仅为补充证据，
  不冒充目标版本通过。
- 在系统临时目录、含中文和空格的严格白名单副本中，设置
  `PIP_NO_CACHE_DIR=1` 后真实执行 `setup.bat --profile core` 成功，从公开索引
  安装 40 项精确依赖，`qrcode-terminal==0.8` sdist 成功构建；第二次执行成功
  且 `.venv/pyvenv.cfg` 时间戳不变。
- 临时新建 `.venv` 从临时 `server/` 导入 `api`，以
  `httpx.ASGITransport(app=api.app)` 请求 `/` 得到 200 与
  `{"status":"online","tts_available":false}`。`doctor.bat --profile dev`
  在临时副本通过，报告 Core 端口可用。
- 首次真实安装尝试因 pip 默认用户 cache 位于沙箱不可写目录而退出 13；重新创建
  全新白名单副本并显式禁用 cache 后成功。该首次失败归因于验收沙箱 cache 权限，
  不记为产品缺陷。

#### 专项、失败注入与锁审计

- 在不含真实运行状态的严格白名单副本运行
  `C:\Users\<user>\anaconda3\python.exe -I -B
  server\tests\test_windows_install.py -v`：12/12 通过，110.472 秒。
  覆盖首次/二次 setup、五个 profile、doctor 只读、start fake 进程、
  Python 缺失/不兼容、Node/npm/pip/lock/端口失败、绝对路径、Batch 引号、
  活动文档和锁门禁。
- 三份实际 SHA-256 与 manifest 完全一致：
  Core `00aa31206aad7bf242eae3633fbf74446317b4d8700114a3ecb2099c2fce37f1`，
  ASR `1f36a3fcc15355fbf4e72fc557c5ce39d7f39ea69d241e6a2a9c6513c4ce9631`，
  dev `2aea2269d9ca2f9c8d1b85677e9c179e054ebbd351591831713565f8c8516ca1`。
  定向扫描没有 editable、`file://`、本机/私有/带凭证来源。
- Windows PowerShell 5.1 对根和 server 共 10 个相关 `.ps1` 的 AST 解析通过；
  PowerShell 7 本机不可用。临时副本 `python -m compileall -q server scripts`
  通过。

#### 跨任务最小回归与 Node 结果

- 临时新建 dev 环境逐项运行：`test_installable_modules.py`、`test_dashboard_shell.py`
  通过；`test_qq_control.py` 8 项中失败 1 项，证据见阻断一；
  `test_conversation_module.py`、`test_voice_module.py`、
  `test_gpt_sovits_provider.py`、`test_voice_pack_registry.py` 均通过。
- 临时 QQ 目录执行 `npm.cmd ci --ignore-scripts --no-audit --no-fund` 成功，
  npm cache 显式位于该临时副本；随后 `npm.cmd test` 为 46/46 通过。
  `server/qq_bridge/src/*.mjs` 全部 `node --check` 通过。
- 控制台六个 JavaScript 文件
  `request/notifications/panels/registry/module-loader/app.js` 均
  `node --check` 通过。没有执行 QQ 入口、真实 API、Collector、LLM、ASR、TTS、
  GPT-SoVITS、提醒或定时发送。

#### 数据隔离、风险和工作区排除

- 验收方第一次构造临时副本时采用的目录排除表不够严格，误带入根目录下一个既有
  ignored `cyber_girlfriend/` 目录；专项测试的绝对路径扫描因此读取到该副本内
  `Scripts/activate.bat` 并以 11/12 退出。没有输出文件内容，也没有使用其中的
  解释器或依赖。该轮证据判为验收夹具错误并废弃，随后从共享根按显式文件/目录
  白名单重建全新副本，正式 12/12、真实安装和全部回归只使用后者。
- 动态安装、npm、ASGI、失败注入和回归只发生在系统临时目录中的严格白名单副本、
  新建 `.venv`、临时 npm cache、fake 进程/端口和 ASGITransport。未使用或检查
  共享项目的 `.venv`、`.venv-asr`、`node_modules` 内容。
- 未读取、打印、diff、复制、迁移、重置或修改真实 `.env`、秘密、个人状态、
  缓存、来源名单、profile、模型、参考音频、Voice Pack 注册表或外部
  GPT-SoVITS 源码。没有探测这些保护文件是否存在。
- 入场已有的 `.gitignore`、README/架构、PK-140、情报、dashboard、个人状态、
  `vendor/` 及其他混合修改继续排除；本轮只编辑 `TASKS.md`、PK-020 记录和本报告。
  未执行暂存、提交、推送、发布或工作区清理。
- 补充限制：真实公开安装发生在系统临时盘，不是 Python 3.11 / Node 22 的
  非系统盘矩阵；非系统盘、中文/空格、五 profile 与失败语义由 fake 专项覆盖。
  在目标矩阵真正运行前，仍不能声称全部 Python 3.11 wheel/sdist 可用或
  PowerShell 7.4 行为已验证。

#### 本批八项文档门禁

- [x] TASK_RECORD — 已在 PK-020 与本报告记录范围、命令、结果、阻断、隔离和最小整改边界。
- [x] TASKS_BOARD — PK-020 与本批 PK-900 均为“进行中”；名称、P0 和依赖不变。
- [x] PUBLIC_README — 已复核公开安装/profile/启动/停止/配置/安全说明；本批没有修改公开契约。
- [x] MODULE_CATALOG — 不适用：PK-020 不新增业务模块；最小 catalog/dashboard 兼容由现有回归覆盖。
- [x] ARCHITECTURE_DOCS — 已核对 Windows 安装、模块化单体、可安装模块、QQ 与语音三层架构；阻断不要求改变架构。
- [x] LOCAL_README — 已读取路径说明但未读取所指环境/数据；本批未改变本机路径、端口或解释器。
- [x] AGENT_RULES — 全程保留混合工作区并遵守秘密、状态、外部引擎、环境和 Git 隔离规则。
- [ ] VALIDATION — 专项和大部分补充回归通过，但 QQ 兼容回归失败、测试夹具隔离不合格，且强制 3.11/22/PowerShell 7 矩阵缺失。

#### 最终门禁命令

- `C:\Users\<user>\anaconda3\python.exe -B scripts\check_task_docs.py`：
  退出 0，输出 `task documentation gate passed: 22 gated task(s)`。为避免标准
  `scripts/python.ps1` 解析并使用共享项目现有环境，本轮显式使用系统 Python，
  且设置 `PYTHONDONTWRITEBYTECODE=1`。
- `git diff --check`：退出 0，仅输出混合工作区既有 LF→CRLF 提示，没有空白错误。
  最终 `git status --short` 仍显示入场时的多任务修改和未跟踪文件；本轮没有清理、
  暂存、提交或推送。

### PK-020 两项整改二次独立复验（2026-07-26）

**结论：仍不通过。** 原 QQ 兼容回归已经关闭，复制阶段的安装表面 allowlist
也已生效；但专项测试的全仓运行时路径扫描仍会读取真实个人状态，故原数据隔离
阻断没有完整关闭。PK-020 再次退回“进行中”，本批 PK-900 保持“进行中”。

#### 原失败点复验

- 静态审阅确认 `test_project_launcher_never_configures_or_installs` 现在正向断言
  `%~dp0`、根 `start.bat --only qq --current-window %*`、参数与退出码透传，
  并反向拒绝 npm、配置复制和 `node src\index.mjs`。生产
  `server/qq_bridge/start_qq_bridge.bat` 与 PK-140 业务未被整改修改。
- 在 PK-900 已知安全、无 data/配置/模型/运行目录的严格白名单副本中，使用隔离
  新建依赖环境运行 `tests/test_qq_control.py`：8/8 通过，0.097 秒。原阻断一关闭。
- `_copy_install_surface()` 已改为 16 个精确安装文件，不再递归复制目录；
  `InstallSurfaceTripwire` 在 `shutil.copy2` 前拒绝受保护、非白名单和根外合成
  路径。严格副本中运行 `test_windows_install.py -v`：12/12 通过，
  118.131 秒，合成 protected sentinel 断言通过。

#### 仍未关闭的数据隔离阻断

- 同一专项的 `test_runtime_scripts_have_no_developer_absolute_paths` 仍通过
  `git ls-files -z` 枚举全部受跟踪文件，并对后缀
  `.py/.ps1/.bat/.cmd/.mjs/.json` 执行 `Path.is_file()` 与 `read_text()`。
  排除集合没有 `server/data`、`server/systems/data` 或其他保护前缀。
- PK-900 只读取 Git index 的路径名，确认该扫描集合包含
  `server/data/affection_state.json`、`fitness_checkins.json`、
  `focus_timer.json`、`memories.json`，以及 calendar/demon/focus 的
  `server/systems/data/*.json`。这些均是 AGENTS 明确禁止读取的真实个人状态。
  PK-900 未读取、stat、diff 或打印其内容，也没有从共享根执行该不安全专项。
- 这说明 16 文件 allowlist 只保护 `setUp()` 的复制阶段，不能保护随后直接以
  `REPO_ROOT` 为源的运行时扫描。PK-020 自测之所以通过，是在预先排除 data 的
  隔离源码副本中运行；它不能证明任务记录所列共享仓库必跑命令安全。
- 最小整改继续限定于 `server/tests/test_windows_install.py`：所有扫描候选必须在
  任何 `Path.is_file/stat/open/read_text` 前按相对路径排除个人状态、缓存、
  来源名单、profile、模型、参考音频、Voice Pack、QQ runtime 和外部引擎；
  优先使用活动生产代码/配置显式 allowlist，并以纯合成 I/O tripwire 证明保护
  前缀零触发。

#### 额外防御性检查与限制

- `InstallSurfaceTripwire` 使用词法 `abspath/relative_to`，未显式拒绝 allowlist
  路径本身是 symlink/reparse point。PK-900 仅在系统临时目录尝试合成 symlink，
  本机返回 `symlink_probe_available=false error_type=OSError`，没有形成可复现
  绕过；建议整改测试层同时加入链接拒绝，防止允许文件名指向根外内容。
- 本机仍无 Python 3.11、Node 22 和 PowerShell 7。目标版本无缓存真实安装矩阵
  未闭合，Python 3.12/Node 24 的既有补充证据不冒充通过。
- 本轮只更新总板、PK-020 退回记录与本报告；混合工作区其他差异继续排除。未读取
  真实秘密、配置、个人状态内容、缓存、来源、profile、模型、音频、Voice Pack
  或外部 GPT-SoVITS 源码，未执行真实服务或 Git 发布操作。

### PK-020 数据隔离第三次独立复验（2026-07-26）

**整改结论：通过；整批仍未完成。** 原 QQ 兼容回归、安装表面复制和全仓路径扫描
三处测试集成问题现均已关闭，未发现新的 PK-020 代码阻断。由于 Python 3.11 x64、
Node 22、PowerShell 7.4+ 无缓存真实安装矩阵仍未执行，PK-020 保持“待集成”，
PK-900 保持“进行中”，不能提前写为“已完成”。

#### 独立代码审阅

- `RuntimePathScanTripwire` 先把 Git index 候选作为纯相对字符串规范化；绝对路径、
  traversal、个人状态 basename、模型/音频后缀及 data、systems data、QQ data、
  cache、runtime、output、profiles、models、Voice Pack、external、vendor、
  venv、node_modules 等保护前缀均在构造真实 `Path` 前拒绝。
- 只有根安装器、安装脚本/锁、server 顶层入口及明确的 core/features/intel/
  services/scripts/static/systems、QQ src、client/pi_client 生产表面可进入
  `is_file/read_text`。`server/systems/data` 的保护判断先于 `server/systems`
  允许判断；Git 不可用时不再执行仓库 `rglob`。
- PK-900 只按 Git index 路径名审阅可疑候选：affection、fitness、memory、
  calendar、demon、focus 状态全部命中保护前缀；允许的 Voice Pack JSON 仅为
  受跟踪 example/schema。没有读取、stat 或打开这些个人状态。
- `InstallSurfaceTripwire` 在 copy 前逐层 `lstat` 相对组件，不跟随目标；
  symlink 与 Windows reparse flag 均失败关闭。合成覆盖不依赖本机实际创建链接
  权限，并断言底层 copy 调用为 0。

#### 共享根实际命令

- `C:\Users\<user>\anaconda3\python.exe -B
  server\tests\test_windows_install.py
  WindowsInstallTest.test_runtime_scripts_have_no_developer_absolute_paths -v`：
  1/1 通过，0.114 秒；输出
  `protected_rejected=32 allowed_io_calls=410`。
- 同文件聚焦
  `WindowsInstallTest.test_doctor_is_read_only_and_does_not_invoke_installers`：
  1/1 通过，13.762 秒；合成 protected、根外、symlink、reparse 均在 copy I/O
  前拒绝。
- `C:\Users\<user>\anaconda3\python.exe -B
  server\tests\test_windows_install.py -v`：12/12 通过，113.455 秒；计数仍为
  32/410。测试只写自身系统临时目录，使用 fake pip/npm/进程/端口。
- 上一轮 PK-900 已在严格隔离副本独立运行 `test_qq_control.py` 8/8；第三次整改
  未修改该测试、QQ 启动器或 PK-140 业务，结果继续有效。

#### 数据隔离与剩余门禁

- 从共享根运行前已确认所有保护候选在任何真实文件 I/O 前拒绝。运行期间未读取、
  stat、open、打印、迁移或修改真实 `.env`、个人状态、缓存、来源名单、profile、
  模型、参考音频、Voice Pack 注册表、QQ runtime 或外部 GPT-SoVITS 源码。
- 未使用共享项目 `.venv`、`.venv-asr` 或 `node_modules`；上述 Python 命令使用
  系统 Python，专项的包/进程均为临时 fake。未启动真实 API、QQ、Collector、
  LLM、ASR、TTS 或外部引擎，未执行 Git 暂存、提交、推送、发布或清理。
- 当前机器仍只有 Python 3.12.7 x64、Node 24.18.0 和 Windows PowerShell 5.1，
  无 `py.exe`、Python 3.11、Node 22 或 `pwsh.exe`。任务禁止自动安装新运行时，
  也没有可用于未提交工作区的远端 CI 证据。因此目标矩阵继续是整批唯一未闭合
  门禁，不归因于新的实现缺陷。

#### 用户安装教程更新

- 用户进一步确认期望“点击安装后自动建立虚拟环境”。PK-900 已据此扩充公开
  README：先安装系统 Python 3.11/3.12 x64，随后 `setup.bat` 自动创建/复用
  `.venv`、校验锁并安装依赖；Core 无需 Node，QQ 用户再安装 Node 22 LTS。
- README 现给出运行时检查、项目根识别、首次 setup、doctor、启动与浏览器地址、
  可选 profile、重跑语义和常见错误表，并明确虚拟环境不能替代系统 Python
  安装。只引用 Python/Node 官方下载入口，不提供第三方安装器。
- 该文档补充不改变已通过的数据隔离结论，也不解除尚未完成的 Python 3.11/
  Node 22/PowerShell 7.4+ 发布矩阵门禁。

### PK-020 最终复核退回：CI 副本与目标矩阵（2026-07-26）

**结论：不通过。** PK-000 复核确认专项测试内的数据隔离整改已经生效，但
`.github/workflows/windows-install.yml` 在测试开始前仍通过无排除的
`git archive HEAD` 构造临时副本。只按 Git tree 路径名核对，HEAD 包含
`server/data/` 下 4 个和 `server/systems/data/` 下 3 个已跟踪个人状态 JSON；
总控未读取、stat、diff、归档或输出其内容。现有两个 Python tripwire 不保护这条
workflow 复制路径，故“干净安装副本不包含个人状态”的发布门禁未满足。

目标运行时矩阵也仍未闭合：本机仅有 Python 3.12.7 x64、Node 24.18.0 和
Windows PowerShell 5.1，无 Python 3.11、Node 22 或 `pwsh`；当前 workflow
没有 PowerShell 7.4+ 步骤，且启用了 npm cache、未冻结全新空 pip cache。
GitHub CLI 认证失效，远端默认分支没有可查询的本 workflow，因此没有远端结果
可以替代本地缺失证据。

PK-020 已退回“进行中”，PK-900 保持“进行中”。最小整改只归 PK-020 的
Windows CI/隔离复制 helper 与专项测试：在任何归档/复制 I/O 前使用明确
allowlist/保护前缀过滤并补充纯合成 tripwire；增加 Windows PowerShell 5.1 与
PowerShell 7.4+、Python 3.11 x64、Node 22 的全新空缓存矩阵，并通过公开 setup
入口验证 Core 首装/幂等、doctor、ASGI health、QQ profile/npm ci 和既定回归。
不得借机改业务模块、个人数据或外部资产。

本轮独立结果：`test_windows_install.py -v` 12/12 通过（114.503 秒，
`protected_rejected=33 allowed_io_calls=418`）；文档门禁在退回前 23 项通过，
同步状态后复跑 22 项通过；
Windows PowerShell 5.1 AST 11 文件、0 失败；`git diff --check` 退出 0。
系统 Python 运行 `test_qq_control.py` 因未安装 FastAPI 在收集前停止；未借用
共享 venv，该结果不记作产品失败。未读取受保护内容，未安装运行时或依赖，未启动
服务，未执行 Git 发布或工作区清理。

### PK-020 新契约变更导致本轮验收暂停（2026-07-26）

**结论：暂停并退回 PK-020，当前验收基线作废。** PK-000 在本轮独立验收进行中
通知 PK-020 产品契约已经扩大：正式 Python 支持范围改为 3.10、3.11、3.12、
3.13 x64；所有受跟踪 BAT 还必须在普通直接运行结束后保留窗口，同时提供明确的
自动化免暂停机制，避免 CI、兼容入口或内部调用挂起。此前冻结的
`>=3.10,<3.13` 范围和当前 BAT 结束行为不能继续作为最终验收依据。

- PK-900 已立即停止本轮源码审计和动态测试，没有把已阅读的 workflow/helper
  或此前 Python 3.11、Node 22、双 PowerShell 矩阵设计写成通过结论，也没有继续
  运行 setup、doctor、兼容回归或远端 CI。
- 本轮停止前只完成必读文档、`git status --short`、受控任务状态查询，以及
  `.github/workflows/windows-install.yml`、`scripts/windows_ci_copy.py` 和相关
  专项测试的只读审阅；未读取、stat、diff、复制或输出任何真实 `.env`、秘密、
  个人状态、缓存、来源名单、profile、模型、参考音频、Voice Pack、QQ runtime
  或外部 GPT-SoVITS 源码。
- PK-020 需要先按新契约更新运行时解析、版本/失败提示、锁与目标矩阵，并统一
  设计 BAT 的交互保留窗口和自动化免暂停协议；这些均属于 PK-020 产品实现，
  PK-900 本轮不代写、不补丁、不提前判断实现方案。
- PK-900 保持“进行中”，不更新任何“待集成/已完成”结论。PK-020 当前任务文件
  和总板仍显示“待集成”，但本记录明确将其退回整改；应由 PK-020/PK-000 在新
  实现入场时同步为“进行中”，完成新契约整改并重新进入“待集成”后，再启动一轮
  累计独立验收。
- 本次暂停未执行 Git 暂存、提交、推送、远端 CI、发布或工作区清理；PK-150、
  PK-213、业务代码、两份真实个人状态和 `vendor/` 等混合工作区差异继续全部
  排除。

### PK-020 新契约累计独立验收（2026-07-26）

**结论：本地实现审计通过，整批验收未通过。** Python 3.10–3.13 x64 契约、
9 个 BAT 的交互暂留/自动化免暂停、CI 安全副本、无缓存矩阵定义及本机可执行
回归均未发现新的实现缺陷；但当前机器只能提供 Python 3.12.7 x64、Node
24.18.0 和 Windows PowerShell 5.1，缺少 Python 3.10/3.11/3.13、Node 22 与
PowerShell 7.4+。未提交工作区也没有可合法触发和查询的远端 runner 结果，因此
强制目标矩阵尚未形成实际证据。PK-020 保持“待集成”，PK-900 保持“进行中”；
不得据本地 3.12/24/PS5.1 结果提前标记“已完成”。

#### 实现与契约复核

- `.github/workflows/windows-install.yml` 不再使用无排除的 `git archive HEAD` 或
  `Expand-Archive`。workflow 先调用受版本控制的
  `scripts/windows_ci_copy.py`，随后所有动态安装与回归只在过滤后的临时副本中
  运行。
- workflow 明确列出 Python 3.10、3.11、3.12、3.13 x64，Node 22 只进入主
  3.11 兼容回归，且分别覆盖 Windows PowerShell 5.1 和 PowerShell 7.4+。
  `setup-node` 未启用 npm cache；pip/npm 使用每轮新建空目录并设置 no-cache/
  非离线语义。3.11 主矩阵包含 Core 首装、二次幂等、doctor、Core import、
  ASGITransport `/` 健康、dev、QQ `npm ci`、Node 测试及 PK-010/100/140/
  200/210/211/212 最小回归。非 3.11 job 会先用矩阵解释器创建 `.venv` 后再走
  公开 `setup.bat`，故其主要证明锁/依赖/doctor/import/ASGI 兼容；解释器自动
  发现与首次创建由主 3.11 job 和专项 fake 矩阵覆盖。
- `scripts/windows_ci_copy.py` 只先读取 Git tree 的相对路径名；绝对路径、
  traversal、`.env`、`README.local.md`、个人状态、cache、来源、profile、
  models/audio、Voice Pack 注册表、QQ data/runtime、external、vendor、
  venv、node_modules 等均在 `Path` 构造和任何 `lstat/stat/open/read/copy`
  前按字符串策略拒绝。允许的 Voice Pack 路径只覆盖项目自有 Python 代码、
  schema/example，资产后缀与本地注册表仍拒绝。
- helper 对 Git symlink mode、源文件 symlink、任一路径组件 reparse point、
  根外候选和目标碰撞均失败关闭。实际复制集合覆盖 setup/doctor/start、锁和
  manifest、Core/API 包代码、静态 dashboard、QQ package/lock/src/tests、
  专项与既定兼容测试；未把受保护数据纳入副本。
- 当前受 Git 跟踪的用户 BAT 共 9 个：
  `setup.bat`、`doctor.bat`、`start.bat`、`server/prebuild_daily_briefing.bat`、
  `server/start_all_services.bat`、`server/start_api.bat`、`server/start_asr.bat`、
  `server/start_gptsovits.bat`、`server/qq_bridge/start_qq_bridge.bat`。
  每个入口使用 `%~dp0`、透传 `%*`、保存原退出码、只调用一次统一 pause helper
  并以原码退出。helper 默认显示结果并等待按键，
  `PROJECT_KEI_NO_PAUSE=1` 时不等待；内部包装器临时设置该变量并恢复调用者值，
  因而只由最外层暂停一次。定时任务显式设置免暂停。
- 独立重算锁摘要与任务冻结值一致：Core
  `8280e23581206b7ef21ef001c4de580cb732eeb01607d5855fa6424216d99fe5`，
  ASR `67c44d7d715f37bf789640b7c2f5b76dc98f081656902ad73db987f544ef5c16`，
  dev `4cbd205c84455140cdd5c276224a60bdd97a61cf9adba364175df52b5afa38c0`。

#### 独立实际命令与结果

- `C:\Users\<user>\anaconda3\python.exe -B
  server\tests\test_windows_ci_copy.py -v`：7/7 通过，0.078 秒。绝对路径、
  traversal、保护前缀、Git symlink、源 symlink/reparse 与目标 I/O
  tripwire 全部通过。
- `C:\Users\<user>\anaconda3\python.exe -B
  server\tests\test_windows_install.py -v`：14/14 通过，142.798 秒，输出
  `protected_rejected=33 allowed_io_calls=420`。覆盖 Unicode/空格/非系统盘
  可移植路径、五 profile、幂等、doctor/start 零隐式安装、锁/pip/npm/版本/
  端口失败、Python 3.10–3.13 x64 探测、绝对路径扫描、PowerShell AST、9 BAT
  暂留和退出码/参数协议。
- 对 workflow 执行 PyYAML 解析：通过；对 copy helper 与两个专项测试使用内存
  `compile()`：通过；Windows PowerShell 5.1 对 11 个 `.ps1` 执行 AST：
  11/11 通过。
- 本机 Node 24.18.0 补充静态检查：QQ `src` 7 个 `.mjs` 与 dashboard 6 个
  `.js` 的 `node --check` 共 13/13 通过。该结果不替代 Node 22。
- 在系统临时目录中用正式 copy helper 建立严格白名单副本，实际输出
  `allowed=336 protected_rejected=8 ignored=8 copied=336`；仅把当前未跟踪但
  属于 PK-020 的 copy helper、copy 测试和 pause helper 三个文件覆盖进副本，
  未复制任何其他未跟踪文件。使用全新 `.venv`、全新空 pip/npm cache、
  `PROJECT_KEI_NO_PAUSE=1`、临时/不存在的 env、LLM profile 与 Voice Pack
  registry 路径和 fake LLM key 完成：
  Python 3.12 x64 Core 首装、二次幂等、Core doctor、`import api`、
  ASGITransport `GET /`=200、dev setup/doctor、`pip check`、QQ profile 的
  `npm ci`、QQ Node 46/46，以及
  `test_qq_control.py`、`test_installable_modules.py`、
  `test_dashboard_shell.py`、`test_conversation_module.py`、
  `test_voice_module.py`、`test_gpt_sovits_provider.py`、
  `test_voice_pack_registry.py`、`test_windows_ci_copy.py`；总流程退出 0，
  输出 `ISOLATED_PK020_MATRIX_LOCAL_OK`。
- 动态验收前两次尝试分别因工具短超时和 PK-900 自编 ASGI 临时命令的 PowerShell
  引号/模块路径错误 fail-closed；公开 Core setup/doctor/import 已成功，失败点
  均在验收夹具。每次 `finally` 均删除对应临时副本。改用副本
  `server` 内固定临时 Python 文件后，第三次完整运行通过；未把前两次夹具错误
  归为产品失败，也未隐藏该过程。
- `C:\Users\<user>\anaconda3\python.exe -B scripts\check_task_docs.py`：
  写报告前通过，`task documentation gate passed: 23 gated task(s)`。
  `git diff --check`：写报告前退出 0，仅有既有 LF→CRLF 提示，无空白错误。

#### 数据隔离、风险与未执行项

- 共享根仅用于读取明确允许的源码、文档、Git 路径元数据和运行带 tripwire 的
  专项；动态安装、pip/npm、ASGI、fake 服务和兼容回归全部位于系统临时白名单
  副本。没有借用共享 `.venv`、`.venv-asr` 或 `node_modules`。
- 未读取、stat、diff、复制、输出、迁移或修改真实 `.env`、秘密、个人状态、
  缓存、来源名单、profile、模型、参考音频、Voice Pack 注册表、QQ runtime
  或外部 GPT-SoVITS 源码；未启动真实 API 监听、QQ、Collector、LLM、ASR、
  TTS 或 GPT-SoVITS。依赖下载仅为公开 PyPI/npm 锁安装，不含业务/付费请求。
- 当前缺少 Python 3.10/3.11/3.13、Node 22 和 `pwsh`；没有安装系统运行时，
  没有触发未经授权的远端 CI。故尚未实际证明四个 Python 版本的 wheel/sdist
  可用性、Node 22 QQ 回归及 PowerShell 7.4+ 行为，这是本轮唯一验收阻断。
- 三个关键新增文件
  `scripts/windows_ci_copy.py`、`server/tests/test_windows_ci_copy.py`、
  `scripts/project-kei.pause.cmd` 当前仍为未跟踪文件；本地副本验收通过显式覆盖
  它们模拟最终受版本控制状态。PK-000 发布时必须把三者与 workflow/BAT 改动
  原子纳入同一提交，否则 CI copy 或 BAT 暂留会缺少依赖。PK-900 不执行暂存。
- 混合工作区中的 PK-150、PK-213、catalog/demon 等业务修改、真实
  `server/systems/data/demon_slayer.json`、`focus_timer.json`、`vendor/` 及
  其他无关差异均排除。本轮未修改 PK-020 产品代码、PK-020 状态或总板，只追加
  本报告；未暂存、提交、推送、发布或清理工作区。

#### 本批八项文档门禁

- [x] TASK_RECORD — 保留全部历史并追加新契约范围、审阅、命令、结果、隔离、
  风险、夹具失败过程和剩余矩阵门禁。
- [x] TASKS_BOARD — PK-020 保持“待集成”，PK-900 保持“进行中”；名称、优先级
  和依赖不变。
- [x] PUBLIC_README — 已核对 Python 3.10–3.13 x64、系统 Python 与自动创建
  `.venv`、Core/QQ 安装和 BAT 暂留说明，未发现与实现不一致。
- [x] MODULE_CATALOG — PK-020 不新增业务模块；catalog/dashboard 最小回归通过。
- [x] ARCHITECTURE_DOCS — `windows-install.md` 的运行时、锁、profile、隔离副本、
  no-pause 与外部引擎边界已和实现核对。
- [x] LOCAL_README — 仅核对本机路径说明；没有读取其指向的真实环境或数据。
- [x] AGENT_RULES — 全程保留混合工作区，保护数据和共享环境，未执行 Git 发布。
- [ ] VALIDATION — 本地所有可安全运行项通过；Python 3.10/3.11/3.13、Node 22、
  PowerShell 7.4+ 的实际无缓存目标矩阵尚未取得，故整批不能通过。

### PK-020 远端矩阵首轮失败与重跑要求（2026-07-26）

- Draft PR #4、run `30191638508` 的 Python 3.10/3.11/3.12/3.13 四个 Windows
  job 均在空 cache 创建步骤失败：Windows PowerShell 5.1 报
  `New-Item` 不存在 `-LiteralPath` 参数。该失败发生在任何安装、复制或回归前。
- 清理步骤随后因 R: 尚未映射而失败，属于同一编排缺陷。最小修复为使用
  `New-Item -Path`，并让 always cleanup 在未映射时成功退出；专项测试须冻结
  两项回归。
- 本 run 不构成目标矩阵证据。PK-020 保持“待集成”、PK-900 保持“进行中”，
  新提交推送后必须重新运行完整四版本、Node 22 与双 PowerShell 矩阵。
- 第二轮 run `30191726833` 已通过上述步骤及 Python/PowerShell、Node 22、copy
  policy 门禁，随后在写入 `PK020_ROOT=R:\` 时由 runner PowerShell 报字符串
  终止符缺失；尚未创建隔离副本。已改用单引号环境行并增加永久断言，仍须重跑。
- 第三轮 run `30191812474` 在同一步继续暴露内联双引号工作区路径的 runner
  解析问题；前置门禁均成功、安装仍未开始。现以 `Join-Path` 变量和调用运算符
  取代该表达，并冻结测试后安排下一轮完整重跑。
- 第四轮 run `30191903483` 证明真正剩余根因是 Windows PowerShell 5.1 对
  runner 无 BOM UTF-8 step 脚本中的中文路径字面量发生代码页误读。现以 ASCII
  Unicode 码点生成同一中文目录名，既消除源码编码歧义又保留中文路径验收。
- 第五轮 run `30191975922` 已通过安全副本创建，随后 pre-install doctor 的预期
  非零未被 workflow 显式归零，且 checkout CRLF 转换导致锁摘要不匹配。修复限定
  为锁文件 `eol=lf` 属性与预期失败步骤 `exit 0`；不得改写摘要或忽略锁失败。
- 第六轮 run `30192124764` 已在四版本上完成 Core 锁安装、摘要与 doctor；
  ASGI 夹具因 PowerShell 5.1 原生 `-c` 多行参数丢失双引号失败。改用临时脚本
  文件经公共 Python 入口执行并清理，属于验收装配修复，不改变产品行为。
- 第七轮 run `30192224339` 的 3.10/3.12/3.13 job 全绿；3.11 已通过安装、
  幂等、双 shell、voice/dev 与 QQ，随后被 dashboard 测试对根目录名
  `project-kei` 的硬编码断言阻断。最小修复仅删除测试假设并冻结防回归。
- 第八轮 run `30192381985` 的三个非主版本全绿；3.11 dashboard 测试向 Node
  stdin 写入中文脚本时使用系统 cp1252 而失败。最小修复为测试 subprocess
  显式 UTF-8，不改变页面、Node 代码或业务行为。

### PK-020 第九轮最终通过（2026-07-26）

- Draft PR #4、run `30192550638` 结论为 `success`；四个
  `clean-install (3.10|3.11|3.12|3.13)` job 均成功。
- 四版本均实际完成无缓存 Core/voice/dev 锁安装、doctor、import、ASGI health、
  空格/中文/非系统盘与受保护副本验证。主 3.11 job 额外完成二次幂等、
  Node 22 QQ profile、兼容回归、Node 测试/语法、双 PowerShell AST 和文档门禁。
- 失败轮次 `30191638508` 至 `30192381985` 的编排、编码与测试可移植性问题均已
  记录并加永久防回归；最终 run 没有 Secret、真实个人状态、模型或业务外部副作用。
- PK-900 独立验收结论：通过。PK-020 与本批 PK-900 由 PK-000 统一标记“已完成”。

## PK-020 + PK-213 联合预发布技术验收（2026-07-26）

### 结论

**本批未通过。** PK-020 的控制台自动打开增量与既有 Windows 安装/启动契约
复核通过，PK-000 已将 PK-020 恢复为“已完成”；PK-213 存在两个可独立复现的
预发布安全/幂等阻断，退回“进行中”。PK-900 保持“进行中”，等待 PK-213
最小整改后重新执行累计验收。

PK-213 当前仍只有空生产 catalog 和 fake Release 技术实现。本轮没有、也不允许
创建真实 Kei ZIP、生产 URL/SHA、tag 或 GitHub Release；即使后续首次技术验收
通过，也只能记录“预发布技术通过”，不能跳过分发权与发布后复核门禁。

### 入场、范围与实现核验

- 入场时 PK-020、PK-213 均为“待集成”，PK-211、PK-212 为“已完成”。联合范围
  是 PK-020 的残缺 `.venv` preflight、监听/浏览器地址、自动打开与免弹窗契约，
  以及 PK-213 的 catalog、固定 HTTPS 下载、安全 ZIP、PK-212 导入/启用/选择、
  本地导入、确定性构建、CLI/BAT 和数据隔离。
- 根 `start.bat` 是唯一主入口；`server/start_all_services.bat` 只委托
  `start.bat --profile all`。Core bind 保持 `0.0.0.0:8000`，浏览器地址固定
  `http://127.0.0.1:8000/dashboard`。`--no-browser` 与
  `PROJECT_KEI_NO_BROWSER=1` 不改变 profile、端口或退出码。
- PK-213 内置 catalog 除严格 Schema 外没有生产 JSON 条目。CLI 没有任意 URL、
  Engine acquire、CUDA/驱动/解包器安装或包内脚本执行入口；远程测试只使用
  `httpx.MockTransport`。分发 service 的 manifest/资产最终验证与 Registry
  写入继续委托 PK-212，PK-211 Engine 状态只以无路径字段读取。
- 相关新增/修改表面未发现真实 checkpoint、权重、音频、ZIP、7z、生产 Release、
  开发者绝对路径或秘密。唯一匹配 `API_KEY` 的文本是专项中专门验证构建器拒绝
  秘密的虚构字符串。

### 阻断一：同 key 的不同内容被误判为可信幂等

- 独立夹具全部位于 `TemporaryDirectory`，使用微型 fake checkpoint/WAV、
  `httpx.MockTransport`、临时 Registry/runtime/cache。步骤为：
  1. 构建并 `download-only` 缓存受信 `fake-kei@1.0.0`；
  2. 另建同一 `id@version`、但 GPT 资产内容与 manifest SHA 均不同的合法
     `local_unpublished` 目录并导入；
  3. 再执行受信 catalog 的 `install fake-kei@1.0.0`。
- 实际输出为
  `{"install_status":"already_installed","local_release_status":"local_unpublished","network_requests":1}`，
  随后验收脚本以 `BLOCKER_REPRODUCED` 终止。根因位于
  `VoicePackDistributionService.install()` 的已安装快速路径：它只验证 catalog
  ZIP cache 自身，再调用 PK-212 `verify(id, version)` 验证已安装记录自身，
  没有比较两者内容身份。
- 责任归 PK-213 的可信 Release 幂等装配。最小整改必须在返回
  `already_installed` 前，通过 PK-212 的公开只读 compare/fingerprint 接缝证明
  manifest 与全部声明资产大小/SHA 一致；不能直接读取 Registry 私有 JSON，
  也不能在 PK-213 复制第二套 manifest 规则。不同内容必须稳定返回 conflict，
  Registry、runtime、cache 和活动 Pack 不变。

### 阻断二：构建器接受源外硬链接资产

- 独立夹具在临时根创建源外微型假模型，以 `os.link()` 把声明的 GPT checkpoint
  变为硬链接，更新 manifest 为该假内容的合法大小/SHA 后调用 `build_release()`。
- 实际输出为
  `{"build_status":"built","hardlink_count":2,"output_created":true}`，
  随后验收脚本以 `BLOCKER_REPRODUCED` 终止。当前 builder 仅用
  `Path.is_symlink()` 检查源路径，未拒绝 `st_nlink != 1`，也未完整检查 Windows
  `FILE_ATTRIBUTE_REPARSE_POINT`。
- 责任归 PK-213 构建输入安全。最小整改需对 root、逐层目录和每个文件使用
  `lstat`/文件属性 fail-closed，拒绝 symlink、hardlink 与 Windows
  reparse/junction；输出 ZIP 与 sidecar 必须在 source root 外，且目标父链同样
  不得含链接/reparse。永久测试应在任何源外文件读取前触发 tripwire。

### 已通过的实际验证

- `test_windows_install.py -v`：15/15，216.050 秒；输出
  `protected_rejected=33 allowed_io_calls=422`。
- `test_windows_ci_copy.py -v`：7/7，0.066 秒。
- `test_voice_pack_distribution.py -v`：9/9，0.651 秒。
- `test_voice_pack_registry.py`、`test_gpt_sovits_engine_sessions.py`、
  `test_voice_pack_origin_guard.py`、`test_gpt_sovits_provider.py`、
  `test_feature_catalog.py`：全部通过。
- `scripts/start.ps1` PowerShell AST、PK-020/213 相关公开路径扫描和 Git ignore
  检查通过。测试没有启动真实 API、浏览器、QQ、Collector、LLM、ASR、TTS、
  9880 或外部引擎。
- PK-213 八个 Python 模块通过 `py_compile`，四个相关 PowerShell 入口 AST
  为 4/4；报告写入后任务文档门禁通过 23 个 gated task，`git diff --check`
  退出 0，仅有混合工作区既有 LF→CRLF 提示。

### 数据隔离、混合工作区与剩余项

- 未读取、diff、stat、复制、摘要、移动或修改真实 `.env`、个人状态、来源名单、
  缓存、LLM profile、Voice Pack Registry/runtime、模型、参考音频、Engine
  登记、外部 GPT-SoVITS 源码、共享 `node_modules` 或 `vendor/`。
- 两个逆向复现只使用系统临时目录和虚构字节，退出后由
  `TemporaryDirectory` 清理；没有真实网络或持久运行副作用。
- 混合工作区中的 PK-150、demon service/test、真实
  `server/systems/data/demon_slayer.json`、`focus_timer.json` 与 `vendor/`
  均保留排除。本轮只修改 TASKS、PK-020/213/900 任务状态和验收记录，不修复
  PK-213 产品代码，不暂存、提交、推送或清理。
- PK-213 整改后必须重跑当前 9 项专项、两个新增永久回归、PK-212 Registry/
  Engine session/Origin/Provider、PK-020 Windows 安装与 BAT/CLI 路径、Python
  编译、PowerShell AST、模块 Catalog、文档门禁和 `git diff --check`。

### 本批八项文档门禁

- [x] TASK_RECORD — 已记录联合范围、独立命令、两个阻断、最小责任边界和剩余门禁。
- [x] TASKS_BOARD — PK-020 通过并恢复“已完成”；PK-213 与 PK-900 为“进行中”。
- [x] PUBLIC_README — 当前仍如实说明空生产 catalog、无真实 Release、启动地址和禁用浏览器开关；无需为失败结论改写产品说明。
- [x] MODULE_CATALOG — 已核对 PK-213 CLI/catalog、网络副作用与无生产条目边界；阻断不允许扩大模块接口。
- [x] ARCHITECTURE_DOCS — 已核对 PK-020/211/212/213 依赖、信任锚、事务和分发权门禁；整改后需补充最终内容身份接缝。
- [x] LOCAL_README — 只核对根启动器和本机 URL；未读取其指向的 Engine、环境或个人数据。
- [x] AGENT_RULES — 遵守混合工作区、外部引擎、秘密、模型、测试和 Git 安全规则。
- [ ] VALIDATION — PK-020 通过；PK-213 两个独立逆向场景失败，本批不能关闭。

## PK-140 QQ 专注到点鼓励增量独立验收（2026-07-28）

### 结论

**不通过。** 既有功能、自测回归、公开 focus 1.1.0 契约、受控 PK-200
生成接缝、状态 Schema 和静态检查均通过，但独立并发夹具复现了一个可达的
交付竞态：`deliver()` 在等待 focus status 时没有先取得进程内唯一交付权，
也没有在等待结束后重新确认当前 entry 和白名单。因此同一提醒可被并发执行两次；
更重要的是，QQ stop/新会话触发的取消可以在 status 请求尚未返回时被旧交付流程
复活，白名单在同一窗口移除后仍会发生一次模型调用。该结果违反本批
“每用户/会话至多一次”以及取消、替换、白名单移除后零模型零发送的冻结契约。

PK-900 保持“进行中”，PK-140 保持“待集成”，退回 PK-140 做最小整改；
本轮没有修改 PK-140、TASKS、产品实现或其他任务状态。

### 入场范围与独立审查

- 已完整读取并按最新内容核对根 `README.md`、`AGENTS.md`、
  `README.local.md`、`TASKS.md`、PK-140、PK-180、PK-200、PK-900
  任务记录及 `docs/architecture/qq-bridge.md`；另核对本批实际改动涉及的
  `docs/architecture/modular-monolith.md`、Catalog、focus package 与 Node
  sidecar 源码。没有继承来源任务的聊天结论。
- PK-020 发布冻结经 PK-000 明确解除：PR #5 已合并，Python 3.10–3.13
  Windows 矩阵通过且暂存区为空。PK-000 同时要求本轮不切分支、不做任何 Git
  写操作或清理，只允许追加本报告。
- 实现边界审查通过：`TimerResult` 暴露稳定且有界的 `session_id`；
  `/api/v1/focus/encouragement` 只接受 `session_id/start_at`，生产装配注入
  loopback guard 与同一 PK-200 `ConversationService` 门面；生成只使用
  mode/elapsed/remaining，不接受 QQ/OpenID、task、任意 prompt、URL，
  不写 conversation history。inactive、替换、停止和损坏 focus 状态在生成前
  固定失败。
- Node 普通 25 分钟 start/status/stop 保持固定版本化 API、`force=false`、
  `with_audio=false` 且零生成；新增固定 action
  `kei:focus:start25:encourage10` 与严格 `专注 N 鼓励 M`，整数及
  2–240/`0 < encourage < duration` 边界正确。非法输入、未知 action 和菜单
  展示均不会形成 API、conversation、任意 method/path/prompt 或模块生命周期操作。
- sidecar 状态 Schema 只允许 24 位用户哈希、受限 session/timestamp/status/
  error code，最多 256 项；原子写使用同目录独占临时文件、file fsync 与 rename，
  错误时删除临时文件并保留旧字节。损坏 Schema、完整身份、秘密或消息字段均
  fail closed。生成接口 404/409/500 和损坏响应不发送；上游空模型文本在 Python
  接缝被规范为 `generated=false`，随后由 Node 使用确定性 fallback，并不伪装
  为生成成功。
- focus 跟踪源码 manifest 与默认构建版本均为 1.1.0；安装包仍复用 PK-010
  install/update/restart 语义，不新增 legacy encouragement，也没有自动安装、
  升级、启用或重启。真实已安装 1.0.0 runtime 仍需要用户显式 build/update/
  restart；本轮没有读取其个人状态，也没有执行真实生命周期操作。

### 阻断：status 等待窗口可绕过唯一交付与取消

- 根因位于
  `server/qq_bridge/src/focus_encouragement_scheduler.mjs:234-263`：
  `deliver()` 先读取一次 `scheduled` entry，随后在没有 in-flight claim 的情况下
  `await getFocusStatus()`；等待返回后直接使用旧的 `entry` 写回 `sending`，
  没有重新确认 `state.entries[key]` 仍为同一条 `scheduled` 记录，也没有在模型
  调用前重新确认 allowlist。
- 独立并发交付夹具使用系统临时目录、fake status、fake generator、fake send
  和门控 Promise，同时调用两次同一 `deliver(key)`。实际输出：
  `{"statusCalls":2,"generationCalls":2,"sendCalls":2,"finalStatus":"sent"}`。
  现有顺序重复测试只能覆盖第一次已经保存 `sent` 后的第二次调用，未覆盖两个
  调用同时停在 status await 的窗口。
- 独立取消竞态夹具在 `getFocusStatus()` 等待期间调用 `cancelUser()`。
  取消当时已经成功持久化为 `cancelled`，但旧交付返回后又覆盖为 `sending`
  并继续生成、发送。实际输出：
  `{"cancelled":true,"statusAfterCancel":"cancelled","generationCalls":1,`
  `"sendCalls":1,"finalStatus":"sent"}`。这也是 QQ stop 或新会话替换可真实触发
  的路径。
- 独立白名单竞态夹具在同一 status 等待窗口删除用户。实际输出：
  `{"generationCalls":1,"sendCalls":0,"finalStatus":"sending"}`。发送前的再次
  检查阻止了 QQ 消息，却没有阻止本应为零的模型调用，并留下 fail-closed
  `sending`。
- 最小整改责任仅属 PK-140 scheduler：在任何 await 前为 entry 建立进程内唯一
  in-flight claim；status 返回后、写 `sending`/调用模型前重新确认 scheduler
  未停止、白名单仍允许、当前 entry 仍是同一 session/start 且仍为
  `scheduled`。取消、新 session 或第二个并发 deliver 必须稳定使旧流程退出，
  不得复活状态、调用模型或发送。生成等待后的既有 `sending`/allowlist/shutdown
  二次检查应继续保留。必须补充永久回归覆盖并发双 deliver、status await 期间
  stop/cancel、新 session 替换和白名单移除；不要扩大 API、状态持久化字段或
  PK-200/PK-180 所有权。

### 实际命令与结果

- `node --test tests/*.test.mjs`（`server/qq_bridge`）：72/72 通过，
  0 fail，约 0.43 秒。该结果证明现有顺序、恢复、fallback、状态损坏和业务菜单
  回归通过，但不覆盖上述并发窗口。
- 依次使用 `server/.venv-asr/Scripts/python.exe` 运行：
  `test_focus_timer.py`、`test_focus_module.py`、`test_focus_dashboard.py`、
  `test_conversation_consumers.py`、`test_conversation_module.py`、
  `test_qq_control.py`、`test_feature_catalog.py`、`test_dashboard_shell.py`、
  `test_daily_briefing_module.py`、`test_daily_briefing_summary_cache.py`：
  十组全部退出 0；qq-control 为 8/8。两个 API import 型测试只记录既有
  focus runtime 目录的 `PermissionError` 并继续通过，没有读取个人状态。
- `node --check` 对 bridge `src/tests` 13 个 MJS 与 dashboard 6 个 JS
  逐文件执行：19/19 通过。
- 使用临时 `PYTHONPYCACHEPREFIX` 对 focus、Catalog、`api.py` 和上述十组测试
  执行 `python -m compileall -q`：通过；临时 pycache 随后删除。
- 上游空文本独立 Python 夹具实际返回
  `{"eligible":true,"generated":false,"text":"","error_code":"generation_failed"}`；
  Node 对不一致的 `generated=true + blank text` 响应稳定保存
  `failed/generation_invalid`，因此空模型输出的正常 fallback 与损坏响应
  fail-closed 边界成立。
- 第一次从仓库根误用 `.\.venv-asr\Scripts\python.exe
  scripts\check_task_docs.py`，因解释器实际位于 `server/.venv-asr` 而在启动前
  失败；修正为 `.\server\.venv-asr\Scripts\python.exe
  scripts\check_task_docs.py` 后通过：`24 gated task(s)`。这不是产品失败。
- `git diff --check`：退出 0，仅输出混合工作区既有 LF→CRLF 提示。
- 报告写入后的文档门禁与 `git diff --check` 在下方最终门禁中再次执行。

### 数据隔离、风险、限制与工作区排除

- 全部新增逆向夹具只使用 `os.tmpdir()`/`TemporaryDirectory`、虚构用户、
  fake clock/timer/status/generator/send 和无网络 ASGI/本地对象；退出后删除
  临时状态。没有启动 BAT、sidecar、Gateway、监听 API、QQ、Collector、
  LLM、ASR、TTS 或 GPT-SoVITS，没有真实发送或付费请求，也没有安装依赖。
- 未读取、打印、diff、迁移、重置或修改真实 `server/qq_bridge/.env`、
  `server/qq_bridge/data/**`、conversation/profile、focus 个人状态或其他个人
  数据。未读取 `server/systems/data/focus_timer.json` 和
  `demon_slayer.json` 内容。
- 混合工作区中的 PK-150 service/task/test、两份已跟踪个人状态、
  `vendor/` 及其他无关修改继续排除。测试后的 `git status --short` 与入场集合
  一致；本轮未整理、覆盖、暂存、提交、推送、切分支或清理。
- 未执行真实 QQ keyboard/Gateway/主 API 端到端，QQ 平台渲染与真实网络时序
  仍属于最终人工限制。focus 1.0.0→1.1.0 的显式部署门禁保持不变，但不是本轮
  代码阻断；当前阻断来自无需真实网络即可稳定复现的 scheduler 并发语义。

### 本批八项文档门禁

- [x] TASK_RECORD — 已追加范围、源码审查、实际命令、三组同根并发证据、
  最小整改、隔离、风险和工作区排除项。
- [x] TASKS_BOARD — PK-140 已为“待集成”，PK-900 已为“进行中”；按 PK-000
  冻结边界未改写总板的当前批次文案或其他状态。
- [x] PUBLIC_README — focus 1.1.0、固定按钮/命令、受控生成、部署和数据边界
  与当前产品实现一致；竞态只记录在验收报告，未把失败实现写成通过。
- [x] MODULE_CATALOG — QQ/focus endpoint、data owner、PK-200 网络副作用和
  failure mode 与实际装配一致；未新增任意调用面。
- [x] ARCHITECTURE_DOCS — 已核对 QQ 与模块化单体中的双重 active identity、
  at-most-once、fallback、取消和部署说明；并发阻断说明现实现尚未满足该文档。
- [x] LOCAL_README — 只读取路径和本机运行说明，没有跟随其路径读取真实配置、
  runtime 或个人状态。
- [x] AGENT_RULES — 遵守数据、外部服务、混合工作区、测试和 Git 边界。
- [ ] VALIDATION — 规定回归与静态门禁通过，但独立并发/取消/白名单竞态失败；
  PK-140 整改并重跑永久回归前，本批不能通过。

## PK-140 scheduler 竞态整改独立复验（2026-07-28）

### 结论

**通过。** 上一节记录的同一根竞态已经按最小范围关闭。PK-900 独立重放原三组
失败夹具并补查新 session 替换与生成中替换后，没有再发现重复模型、重复发送、
取消状态复活或白名单移除后的模型调用。PK-140 继续保持“待集成”，PK-900
不自行将其改为“已完成”，本结论交 PK-000 最终关闭。

### 实际差异与源码复核

- 本轮整改实际只涉及
  `server/qq_bridge/src/focus_encouragement_scheduler.mjs`、
  `server/qq_bridge/tests/focus_encouragement.test.mjs` 和 PK-140 工作记录；
  API、持久化 Schema、focus/PK-180、conversation/PK-200、Catalog、TASKS
  及其他模块没有因整改扩大。
- `deliver(key)` 在第一次 await 前用进程内 `inFlight` 对同 key 唯一 claim；
  claim 固定 `user_key/session_id/start_at/due_at`，第二个并发 delivery 在
  status、生成和发送之前退出，并在 `finally` 释放。
- status 成功或异常返回后，代码在写 `sending/failed` 或调用模型前重新核对
  stopped、state health、实时 allowlist 和当前 entry 的 identity/status；
  cancel、新 session 和白名单变化不能被旧闭包覆盖。生成与发送 await 返回后
  也继续使用同一 identity/status 检查。
- 状态字段、256 项上限、原子写、fallback、错误码、发送前 `sending`
  reservation、最终保存失败和秘密清洗语义均未改变；未引入持久化 claim、
  新 API、任意 endpoint/method/prompt 或第二套 focus/conversation 实现。

### 原失败夹具独立重放

- 同 key 并发双 `deliver`：
  `{"statusCalls":1,"generationCalls":1,"sendCalls":1,"finalStatus":"sent"}`。
- status await 期间 `cancelUser`：
  `{"cancelled":true,"statusAfterCancel":"cancelled","generationCalls":0,`
  `"sendCalls":0,"finalStatus":"cancelled"}`。
- status await 期间移除白名单：
  `{"generationCalls":0,"sendCalls":0,"finalStatus":"cancelled"}`。
- status await 期间登记新 session：
  `{"generationCalls":0,"sendCalls":0,"oldStatus":"cancelled",`
  `"newStatus":"scheduled"}`。
- 补充逆向：模型生成 await 已开始后登记新 session，实际为
  `{"sendCalls":0,"oldStatus":"cancelled","newStatus":"scheduled"}`；
  证明生成返回后不会使用旧 entry 继续发送或覆盖取消。

全部夹具使用系统临时目录、虚构用户、fake status/generator/send、fake timer
和可控 Promise；没有网络、QQ、模型或真实状态副作用。

### 累计回归与门禁

- `node --test tests/focus_encouragement.test.mjs`：28/28 通过。
- `node --test tests/*.test.mjs`：76/76 通过，0 fail。
- 使用 `server/.venv-asr/Scripts/python.exe` 重跑 focus timer/module/dashboard、
  conversation consumers/module、qq-control、Catalog、dashboard shell、daily
  briefing module/summary cache 共十组：全部退出 0，qq-control 为 8/8。
  两个 API import 型回归仅出现既有 focus runtime 目录 `PermissionError` 隔离提示，
  没有读取个人 focus 状态。
- bridge `src/tests` 13 个 MJS 与 dashboard 6 个 JS 逐文件
  `node --check`：19/19 通过。
- 使用临时 `PYTHONPYCACHEPREFIX` 对相关 focus/Catalog/API/测试执行
  `python -m compileall -q`：通过，临时 pycache 已删除。
- 报告写入前 `scripts/check_task_docs.py`：24 个 gated task 通过；
  `git diff --check`：退出 0，仅有混合工作区既有 LF→CRLF 提示。报告写入后
  两项门禁再次执行。

### 数据隔离、限制与工作区排除

- 未读取、stat、diff、打印、迁移或修改真实 `server/qq_bridge/.env`、
  `server/qq_bridge/data/**`、`server/systems/data/focus_timer.json`、
  conversation/profile 或其他个人状态。未启动 BAT、sidecar、Gateway、API、
  QQ、Collector、LLM、ASR、TTS 或 GPT-SoVITS，未安装依赖。
- PK-150 service/task/test、真实 demon/focus 状态、`vendor/` 和其他混合修改
  均继续排除；本轮只追加 PK-900 复验记录，没有修改产品或其他任务状态，
  没有暂存、提交、推送、切分支或清理。
- 真实 QQ 平台/Gateway 网络时序与 focus 1.0.0→1.1.0 显式
  build/update/restart 仍是既有人工部署门禁，不构成本次 scheduler 源码阻断。

### 本轮八项文档门禁

- [x] TASK_RECORD — 保留上一轮失败证据并追加整改差异、独立复现、回归、隔离和结论。
- [x] TASKS_BOARD — PK-140 保持“待集成”，PK-900 保持“进行中”，由 PK-000 决定最终关闭。
- [x] PUBLIC_README — 本轮未改变用户能力；既有受控鼓励、fallback 和部署说明仍与实现一致。
- [x] MODULE_CATALOG — API、数据所有权、网络副作用和失败模式未改变。
- [x] ARCHITECTURE_DOCS — 现实现已满足已记录的 at-most-once、取消和 identity 重验语义。
- [x] LOCAL_README — 未改变本机路径、环境、端口或启动方式，也未跟随路径读取真实状态。
- [x] AGENT_RULES — 全程遵守数据隔离、外部服务、混合工作区和 Git 边界。
- [x] VALIDATION — 原失败夹具、补充异步替换、76 项 Node、十组 Python、
  19 项 JavaScript 语法、compileall、文档门禁和 `git diff --check` 全部通过。

## PK-000 最终关闭确认（2026-07-28）

- PK-000 没有仅接受来源任务的通过数字；独立审查 scheduler claim/identity
  实现，并重跑定向 28 项与全部 76 项 bridge Node 测试，全部通过。
- 独立重跑 focus module、conversation consumers、qq-control 8 项及 feature
  Catalog 四组关键 Python 接缝，全部通过。原 status-await 并发、取消、白名单
  移除和新 session 替换阻断已关闭，生成/发送等待后的旧 entry 也不能覆盖取消。
- 最终状态仅更新 TASKS、PK-140 与本报告。未读取或修改真实 QQ `.env`、
  sidecar runtime、focus/demon 个人状态、模型配置或 `vendor/`，未启动真实服务，
  未执行 Git 暂存、提交、推送、切分支或清理。
- 结论：`PK-140` 与本轮 `PK-900` 标记“已完成”。`PK-213` 继续保持独立
  “待集成”，其预发布/真实发布门禁不属于本批关闭范围。

## PK-030 Python 测试质量集成交接（2026-07-29）

### 待独立复验的交付

- PK-030 保持“待集成”，不在来源任务自行关闭。机器清单当前报告 67 个测试文件：
  53 个默认离线、6 个受控集成、8 个人工诊断；180 个顶层 `check_*` 中 106 个异步。
- 来源任务在全新的系统临时 Python 3.12.7 venv 中按 PK-020 两份锁安装后，
  collect-only 为 260 项，完整默认套件为 259 passed、1 个既有端口占用条件 skip；
  ruff 首期范围和机器清单审计均通过。
- 需要独立核对 `pyproject.toml`、`server/tests/conftest.py`、
  `server/tests/python-test-inventory.json`、`scripts/check_python_test_inventory.py`
  和 Windows workflow；不得只接受来源任务的通过数字。

### PK-900 必跑

```powershell
.\scripts\python.ps1 .\scripts\check_python_test_inventory.py --json
.\scripts\python.ps1 -m pytest --collect-only -q
.\scripts\python.ps1 -m pytest
.\scripts\python.ps1 -m ruff check server\tests scripts\check_python_test_inventory.py
.\scripts\python.ps1 ..\scripts\check_task_docs.py
git diff --check
```

另需独立复验质量门禁中的故意失败后继续报告、async 真执行、外部 DNS 与真实
loopback 阻断、protected-path 拒绝；确认 14 个隔离脚本均有真实网络/服务/硬件/
秘密或破坏性诊断理由，且 workflow 的 Python 3.10–3.13 x64 每项都运行完整离线
集合和 ruff。不得启动真实 API、QQ、ASR、TTS、GPT-SoVITS、collector 或模型，
不得读取个人状态、凭据、来源名单、模型、Voice Pack registry、`vendor/`、现有
venv 或 `node_modules`。共享 PK-020/100/120/130/133/140/150/210/213 修改继续排除。

### 过滤副本阻断整改回传

- 原因确认：copy policy 保护整个 `.github/`，导致 inventory 和默认质量测试无法在
  过滤副本读取其必须审计的同一 workflow。来源任务已加入唯一精确、
  大小写敏感的 `.github/workflows/windows-install.yml` 例外并列入 required files；
  其他 `.github/**` 仍为 protected。
- 根工作树 copy-policy 测试 8/8 通过；候选过滤副本仅含这一个 `.github` 文件，
  副本 inventory 通过，质量门禁 6/6 通过，副本 copy-policy 为 7 passed、
  1 个无 Git metadata 预期 skip。
- PK-900 在精确发布后必须从真实 tracked Git tree 重放 `create_filtered_copy()`，
  再在副本内运行 inventory、质量 pytest 与完整默认套件；远端四版本新矩阵仍需取得。

## PK-020 本机 API/ASR 默认暴露边界独立复验（2026-07-29）

### 结论

**不通过，继续保持 PK-900“进行中”和 PK-020“待集成”。** 本机访问边界产品
实现与本地可执行回归未发现绕过，但最终关闭仍有两个硬门禁：

1. 本轮 P0 文件仍是当前提交 `58b415785d4b19cb2aa0bac7dafc5c1c77700040`
   之外的工作区差异。最新同 SHA 的 Windows workflow
   `30332764812` 于 2026-07-28 成功覆盖 Python 3.10/3.11/3.12/3.13 四个
   clean-install job，但不包含 2026-07-29 新增的 loopback middleware、测试和
   bind 改动，不能作为本轮目标矩阵证据。PK-000 精确发布本轮安全差异后，仍须
   取得 Node 22、Windows PowerShell 5.1、PowerShell 7.4+ 与四个 Python x64
   job 的新成功记录。
2. 当前混合工作区中的 PK-030 CI 增量与过滤副本存在确定冲突：workflow 在
   `PK020_ROOT` 过滤副本内运行 `scripts/check_python_test_inventory.py`，而
   `scripts/windows_ci_copy.py` 明确过滤 `.github/`；inventory 随即读取
   `.github/workflows/windows-install.yml` 并失败。独立复现为退出 2：
   `python-test-inventory: error: [Errno 2] ... .github\workflows\
   windows-install.yml`。同一 inventory 还被默认 pytest 的
   `test_pytest_quality_gate.py` 再次调用，因此仅移动 workflow 中的一条命令
   不足以关闭。该问题归属 PK-030/共享 Windows CI 接缝，不是 PK-020 本机边界
   业务实现；最小整改应让 inventory 的 workflow 审计与过滤副本契约一致，或在
   精确 PK-020 发布分支排除尚未集成的 PK-030 全量 pytest 改动并显式运行
   `test_local_access_boundary.py`。整改后必须在真实过滤副本重跑，不能跳过。

### 独立源码与边界复核

- `LoopbackAccessMiddleware` 是 `api.app.user_middleware[0]`，即实际最外层
  middleware。它只读取 ASGI `scope["client"]`，允许 IPv4 `127.0.0.0/8`
  与 IPv6 `::1`；缺失 peer、`localhost` 字符串、IPv4-mapped IPv6、LAN/
  公网和非法值均失败关闭。重复、空白、`null` 或非白名单 Origin 同样在下游
  前拒绝。
- 远端 peer 即使同时伪造 loopback `Host`、可信 `Origin`、
  `X-Forwarded-For` 和 `Forwarded`，HTTP/静态/legacy/写路由仍统一返回
  403 `{"detail":"仅允许本机访问"}`，且 handler/downstream 与保护路径 I/O
  均未执行。
- 实际枚举 147 条 HTTP 路由和 1 条 WebSocket `/ws/chat`：远端 WebSocket
  在 `accept` 前收到 1008；`127.0.0.1`、其他 `127/8` 与 `::1` 可进入原
  handler；本机恶意 Origin 在握手前拒绝。
- CORS 只含 `http://127.0.0.1:8000`、`http://localhost:8000`、
  `http://[::1]:8000`，`allow_credentials=false`。三种可信 Origin 的
  preflight 均为 200、精确回显该 Origin 且无 credentials 头；`null`、空白、
  重复、LAN、HTTPS 与恶意 Origin 均无 CORS 授权并返回 403，远端 OPTIONS
  先被全局边界拒绝。
- 对生产 Python/BAT/PowerShell 入口作定向扫描：`scripts/start.ps1` 的
  Core/ASR uvicorn 参数及日志、`server/api.py` 和
  `server/services/asr_server.py` 直接入口均固定 `127.0.0.1`；根启动器与
  `server/start_api.bat`、`server/start_asr.bat`、对应 PowerShell 和 all
  入口只委托统一启动器。排除测试/文档和保护目录后，生产启动代码没有
  `0.0.0.0` 或第二套 host 回退。

### 隔离方式与实际结果

- 使用工作区外新建的 Python 3.12.7 venv，按公开
  `requirements/core-win.lock.txt`、`PIP_NO_CACHE_DIR=1` 和
  `--no-cache-dir --no-input` 安装；没有借用共享 `.venv`、`.venv-asr`。
  首次误加逐包 `--require-hashes` 因本项目采用整份锁文件 SHA 而按预期在安装
  前失败，随后按公开 setup 的真实 pip 参数安装成功。
- 独立当前工作树副本先用 `git ls-files -co --exclude-standard -z` 取得纯相对
  字符串，再复用 `CopyPolicy` 分类，只有 allowed 项才构造 Path、逐组件
  `lstat` 和 copy：`allowed=385 protected_rejected=113 ignored=8
  copied=385 lstat_calls=1320`。保护路径未进入底层文件 I/O。
- `fresh-python -B server/tests/test_local_access_boundary.py -v` 在共享根
  tripwire 和过滤副本各运行一次，均 4/4；输出
  `protected_rejected=1 protected_resolve_shortcuts=5 allowed_io_calls=37
  http_routes=147 websocket_routes=1`。
- 独立逆向 ASGI 探针覆盖缺失 peer、IPv4-mapped IPv6、远端四类伪造头、三个
  可信 CORS preflight、credentials 头缺失和 `null` Origin，最终全部符合上述
  固定结果。第一次自编断言误把三个允许用例也纳入“全部应为 403”的集合而失败；
  打印实际响应后修正夹具，确认是验收脚本错误，不是产品失败。
- 过滤副本 `test_windows_install.py -v`：18 passed、1 skipped，跳过项是本机
  8000 已占用时按既有规则不运行 fake Core 启动；共享根仅运行路径扫描与 bind
  两项为 2/2，tripwire 为 `protected_rejected=34 allowed_io_calls=456`。
- 共享根 `test_windows_ci_copy.py -v`：6 passed、1 error。错误是当前 HEAD
  尚不含 `pyproject.toml`、inventory、local access 实现/测试等新文件，
  `build_plan(HEAD)` 报缺少 required files；在无 Git 元数据的当前工作树过滤
  副本中纯 tripwire 为 5 passed、2 skipped。提交后前一错误应自然消失，但必须
  由新远端 run 证明，不能在验收阶段预判为通过。
- 过滤副本依次重跑 installable modules、dashboard shell、QQ 8 项、
  conversation（含 history 读/清除/失败保持）、calendar memo/module、
  demon、voice module/runtime control、GPT-SoVITS provider、Voice Pack
  registry 与 feature catalog：全部退出 0。曾误列不存在的
  `test_conversation_history.py`，命令退出 2；核对实际源码后确认 history
  已由 `test_conversation_module.py` 覆盖，并按真实清单继续完成。
- 过滤副本使用全新空 npm cache 执行
  `npm.cmd ci --ignore-scripts --no-audit --no-fund`，仅安装 1 个公开依赖；
  Node 测试 83/83，QQ 与 dashboard JavaScript `node --check` 17/17。
  首次 `npm` 命令仅因本机 PowerShell 禁止 `npm.ps1` 而退出，改用官方
  `npm.cmd` 后成功。本机 Node 24.18.0 只作补充，不冒充 Node 22。
- 过滤副本 `python -B -m compileall -q server scripts` 通过；Windows
  PowerShell 5.1 AST 13/13；workflow YAML 解析通过；文档门禁为
  `24 gated task(s)`；`git diff --check` 退出 0，只有既有 LF→CRLF 提示。

### 数据隔离、风险和工作区排除

- 未启动真实监听、BAT、QQ、Collector、LLM、ASR、TTS、GPT-SoVITS 或浏览器；
  未连接业务/付费服务。仅为新临时 Python/npm 环境访问公开包索引。
- 未读取、stat、diff、复制、打印、迁移或修改真实 `.env`、聊天/长期记忆、
  个人状态、来源名单、cache/profile、模型、参考音频、Voice Pack registry、
  QQ runtime、共享环境、`node_modules` 或 `vendor/`。过滤副本中的测试写入与
  npm 产物不属于真实项目状态。
- PK-030/100/120/130/133/140/150/213、dashboard、Bilibili、papers、
  demon/focus 个人状态及其他混合工作区差异全部保留且不归入本批。
- 本轮只追加 PK-900 记录；没有修改产品、TASKS 或 PK-020 状态，没有暂存、
  提交、推送、触发 workflow、切分支或清理。

### 本轮八项文档门禁

- [x] TASK_RECORD — 已追加范围、源码判断、实际命令/结果、隔离、风险和阻断。
- [x] TASKS_BOARD — PK-900 保持“进行中”，PK-020 保持“待集成”。
- [x] PUBLIC_README — loopback bind、可信 peer、精确 Origin 和无 LAN 模式与实现一致。
- [x] MODULE_CATALOG — 未改变模块映射；installable modules 与 catalog 回归通过。
- [x] ARCHITECTURE_DOCS — Windows 安装、ASR、QQ、Voice Pack 的本机边界与实现一致。
- [x] LOCAL_README — 未改变本机路径约定，也未跟随路径访问保护数据。
- [x] AGENT_RULES — 遵守数据、外部服务、混合工作区和 Git 边界。
- [ ] VALIDATION — 本机专项与回归通过，但当前过滤副本 CI 接缝确定失败，且
  P0 精确提交后的 Python 3.10–3.13/Node 22/双 PowerShell 新矩阵尚无证据。

## PK-020 + PK-030 过滤副本接缝整改独立复验（2026-07-29）

### 当前结论

**PK-030 对上一节第二个阻断的候选工作树整改已通过本地独立复验；累计批次仍
等待远端矩阵，PK-900 保持“进行中”，PK-020 与 PK-030 均保持“待集成”。**
本节不覆盖上一节的历史失败：原 `.github` 全过滤缺陷确实存在，现已由精确
allowlist 关闭。当前 `HEAD` 仍为
`58b415785d4b19cb2aa0bac7dafc5c1c77700040`，整改和 PK-020 P0 仍是其外的
工作区差异，因此尚不能用候选副本替代发布后的真实 tracked Git tree。

### 精确 allowlist 与逆向审计

- `CopyPolicy.classify()` 先保留原始大小写的 normalized 相对字符串，只对
  `.github/workflows/windows-install.yml` 返回 allowed；随后才进入原有
  case-folded protected/allowed 分类。`REQUIRED_COPY_FILES` 同时要求该精确
  workflow，缺失时 `build_plan()` 失败关闭。
- 根工作树使用新建独立 Python 环境执行
  `python -B server/tests/test_windows_ci_copy.py -v`：8/8 通过。
- PK-900 另写纯合成逆向探针，不调用正式测试断言：
  - 合法精确 workflow 为 allowed；
  - evil workflow、`.github/actions/**`、`.GitHub`、`WORKFLOWS`、
    `WINDOWS-INSTALL.yml` 均 protected；
  - Windows 分隔符、traversal、盘符绝对路径、根绝对路径和根外候选在
    filesystem I/O 前抛 `CopyPolicyError`；
  - required entry 缺失、Git mode `120000`、组件 symlink 与 Windows reparse
    均失败关闭，合成 `mkdir/copy` 调用为 0。
- 结论：例外是大小写敏感的单文件边界，没有把 `.github/` 目录、actions 或其他
  workflow 扩入复制面；symlink/reparse 仍须通过逐组件 `lstat`。

### 使用真实同一 policy 的候选过滤副本

- 因 P0/PK-030 文件尚未进入 Git tree，本轮不能调用只读取 `HEAD` 的正式
  `create_filtered_copy()` 冒充发布证据。PK-900 使用
  `git ls-files -co --exclude-standard -z` 取得当前候选的纯相对路径字符串，
  再逐项调用生产 `CopyPolicy`；只有 classified allowed 后才构造 Path，并继续
  使用生产 `WorkingTreeCopyGuard` 的逐组件 `lstat` 与 copy。
- 结果为 `allowed=387 protected_rejected=112 ignored=8 copied=387
  lstat_calls=1326`。副本 `.github` 实际文件集合严格等于
  `[".github/workflows/windows-install.yml"]`，没有读取或复制其他 `.github`
  内容。
- 副本内 `scripts/check_python_test_inventory.py --json` 成功：
  `test_files=67 default_files=53 isolated_files=14
  controlled_integration_files=6 manual_diagnostic_files=8
  top_level_check_functions=180 async_check_functions=106`。
- 副本内 `pytest -q server/tests/test_pytest_quality_gate.py`：6/6 通过，实际
  覆盖 async 等待、故意失败后继续报告、外部 DNS/真实 loopback 阻断、保护路径
  I/O 前拒绝、固定时钟和 inventory 子进程。
- 副本内 `test_windows_ci_copy.py -v`：7 passed、1 skipped；唯一 skip 是过滤
  副本按设计没有 `.git` metadata，workflow 存在性/内容检查实际执行并通过，
  不再因 workflow 缺失跳过。
- 副本内 `pytest --collect-only -q`：实际收集 260 项。
- 副本内完整 `pytest`：258 passed、2 skipped、0 failed。两个 skip 分别是
  “过滤副本无 Git metadata”及本机 8000 已占用；没有 workflow 缺失、网络、
  保护路径或测试收集跳过。完整套件中的 local-access 4 项同时通过。
- 副本内
  `python -B -m ruff check server/tests scripts/check_python_test_inventory.py`：
  `All checks passed!`。

### 分类数字与隔离理由的独立交叉核对

- PK-900 未使用 inventory 工具自身结果作为唯一证据，另以独立 AST 解析实际
  `server/tests/test_*.py`：实际文件 67，分类集合无重复、无漏项、无 stale；
  默认 53、隔离 14，顶层 `check_*` 为 180，其中 async 为 106，与工具输出一致。
- 6 个 controlled integration 均有真实隔离理由：用户音频与 ASR、每日情报
  生成/LLM/TTS、综合健康真实服务与付费模型、麦克风/音频驱动、GPT-SoVITS/
  Voice Pack runtime、完整 voice chat 服务链。
- 8 个 manual diagnostic 均有真实隔离理由：真实输出清理可删除数据、真实情报
  多来源采集、读取环境并调用付费 LLM、Nitter/RSSHub/YouTube 外部诊断、
  真实论文检索，以及读取模型凭证并执行 DeepSeek 总结。14 项理由均对应脚本
  实际能力，不是空占位；本轮未运行其中任何一项。

### 剩余发布门禁、数据隔离与状态

- 当前尚无包含 PK-020 P0、PK-030 质量门禁和本次精确 workflow allowlist 的新
  commit，也没有基于该 commit 的远端 run。PK-000 必须先对 `PK-020 + PK-030`
  精确范围作逐文件/逐 hunk 审核与发布。
- 发布后必须从真实 tracked Git tree 调用正式 `create_filtered_copy()`，确认
  required files、唯一 workflow 与完整复制面，再在副本内重放 inventory、
  quality gate、260 collect、完整默认 pytest 和 ruff。
- 同一新 commit 的 Windows workflow 必须实际通过 Python
  3.10/3.11/3.12/3.13 x64、Node 22、Windows PowerShell 5.1 和
  PowerShell 7.4+；旧 SHA 的成功 run 继续只作历史基线，不作为本轮证据。
- 本轮只使用 PK-900 自建的工作区外 Python venv、候选过滤副本、公开 Core/dev
  lock 与禁用缓存安装。未借用现有项目环境或 `node_modules`，未启动 API、
  BAT、QQ、Collector、LLM、ASR、TTS、GPT-SoVITS 或浏览器。
- 未读取、stat、diff、复制、输出或修改真实 `.env`、个人状态、缓存、来源名单、
  profile、模型、音频、Voice Pack registry、QQ runtime 或 `vendor/`。
  PK-100/120/130/133/140/150/213 及其他混合差异继续排除。
- 只追加本 PK-900 报告；未修改产品、TASKS、PK-020/PK-030 状态，未暂存、
  提交、推送、触发远端 workflow、切分支或清理。

### 本轮八项文档门禁

- [x] TASK_RECORD — 已保留原失败并追加整改差异、逆向证据、完整副本回归和遗留矩阵。
- [x] TASKS_BOARD — PK-020/PK-030 均保持“待集成”，PK-900 保持“进行中”。
- [x] PUBLIC_README — 本轮只改变 CI 安全复制/质量接缝，不改变用户运行契约。
- [x] MODULE_CATALOG — 未改变模块目录、API、数据所有权或副作用声明。
- [x] ARCHITECTURE_DOCS — Python 测试质量和 Windows 安装的过滤副本边界一致。
- [x] LOCAL_README — 未改变或跟随本机秘密、个人路径与 runtime 说明。
- [x] AGENT_RULES — 遵守过滤副本、保护数据、外部服务、混合工作区和 Git 边界。
- [ ] VALIDATION — 候选工作树本地复验通过；真实 tracked copy 与新远端目标矩阵
  仍未执行，最终关闭门禁尚未满足。

## PK-030 `check_*` 参数契约独立复验（2026-07-29）

### 结论

**不通过，精确退回 PK-030；PK-020 的 loopback/CORS 实现不重复退回。**
当前实际默认测试树的参数可以满足，但新增的“收集前参数契约”存在一个错误放行和
一个错误拒绝，尚不能证明未来默认 `check_*` 的不可满足参数恒为 0。PK-900
继续“进行中”，PK-020/PK-030 继续“待集成”，远端发布矩阵仍暂停。

### 已通过的现有树与受控路径证据

- 使用新的候选过滤副本，按生产 `CopyPolicy` 与 `WorkingTreeCopyGuard` 得到
  `allowed=388 protected=112 ignored=8 lstat=1329`；`.github` 仍只包含
  `.github/workflows/windows-install.yml`，且
  `server/tests/_parameter_contract.py`、conftest、inventory 均进入副本。
- 从 `server` 工作目录按 Windows runner 的真实 cwd 语义运行
  `python ..\scripts\check_python_test_inventory.py --json`，输出：
  `total=183 zero=98 fixture_or_parametrize=85 unsatisfied=0
  async_check=107 legacy=12 legacy_zero_parameter=12`，必需参数名为实际 13 个。
- PK-900 另用独立 AST 重新解析默认文件，不调用 inventory 统计函数，得到同样
  `183/107/98/85/0`，实际树没有 positional-only check，12 个 legacy 入口均无
  必需参数。
- `pytest tests --collect-only -q` 从 `server` cwd 实际收集 263 项，退出 0；
  quality gate 9/9，copy policy 在副本中 7 passed、1 个无 Git metadata 的预期
  skip；Ruff 与四个相关文件的 Python 3.10 grammar 解析通过。
- 为验证受控入口而在过滤副本内创建指向 PK-900 自建临时 venv 的临时 junction，
  通过 Windows PowerShell 5.1、`-ExecutionPolicy Bypass` 实际调用根
  `scripts/python.ps1`。inventory、quality 9/9 和
  `ruff check tests ..\scripts\check_python_test_inventory.py` 均成功，证明
  wrapper 的 `Push-Location server` 与 README/workflow/架构中的 `tests`、
  `..\scripts\...` 路径一致。首次直接调用仅被本机 PowerShell execution
  policy 拒绝，未运行测试；改用公开 BAT 等价的 Bypass 方式后通过。

### 阻断一：positional-only fixture 被错误判为可满足

- 合成 `def check_posonly(tmp_path, /): ...`，调用生产
  `validate_check_parameters(..., fixture_names={"tmp_path"})` 返回
  `fixture_or_parametrize`，没有收集前拒绝。
- 对同一合成模块运行真实 pytest：
  `--collect-only` 退出 0 并收集 1 项；完整执行退出 1。pytest 以关键字注入
  fixture，最终报
  `TypeError: check_posonly() missing 1 required positional argument:
  'tmp_path'`。这不是 fixture-not-found，也不是预期 skip，而是当前 AST 审计
  错误放行后延迟到 call phase 的失败。
- 未知 positional-only、普通 positional 与 keyword-only 参数当前都能被
  `ParameterContractError` 拒绝；普通/keyword-only `tmp_path` 能合法接受。
  缺口精确限定为“名称碰巧匹配 fixture/parametrize 的必需 positional-only”。
- 最小整改：`_parameter_contract.py` 必须把必需 positional-only 单独标记为
  pytest 不可注入并无条件 fail closed，不能与普通 positional 参数一起按
  fixture 名称抵消；补充纯 AST 与真实 collection 子进程永久回归，要求在
  模块导入/fixture 解析前固定 UsageError。

### 阻断二：模块自身声明的合法 fixture 被错误拒绝

- 合成模块：
  `@pytest.fixture def local_value(): return "ok"` 与
  `def check_local_fixture(local_value): ...`。真实 pytest 收集并执行为
  1 passed。
- 生产参数审计只调用
  `fixture_names_from_source(conftest_source)`，未把当前测试模块自身的 fixture
  声明加入 available fixtures；同一模块被
  `validate_check_parameters()` 错误拒绝为
  `check_local_fixture -> local_value`。
- 这违反“合法项目/pytest fixture 可识别”，属于安全门禁误报，不应要求所有
  fixture 都搬到根 conftest。最小整改：每个默认文件审计时，把该文件通过同一
  严格 literal fixture 解析得到的模块级 fixture 与 conftest/builtin 集合合并；
  对 module-local 同步 fixture、async fixture + async check 增加永久成功回归。
  非 literal fixture 名和未知参数仍应 fail closed。

### 未执行项、隔离和后续门禁

- 因独立逆向已经确认参数门禁不完整，本轮未把 263 collect、quality 9/9 或来源
  的 262 passed 总数作为通过依据，也未重复运行三分钟完整默认套件掩盖契约失败。
- 未访问真实 `.env`、个人状态、缓存、来源、profile、模型、音频、Voice Pack、
  QQ runtime、共享 venv/node_modules 或 `vendor/`；合成模块全部位于系统临时
  目录，候选副本与 venv 由 PK-900 独立创建。
- 只追加 PK-900 报告；未修改产品、TASKS、PK-020/PK-030 状态，未暂存、提交、
  推送、触发 workflow、切分支或清理。
- PK-030 关闭上述两项并恢复“待集成”后，PK-900 须重放未知 positional-only/
  positional/keyword-only、fixture-named positional-only、模块内同步/async
  fixture、literal parametrize 和 legacy main 手工传参夹具；确认错误都在
  collection 前固定 UsageError，合法项真实注入/await。
- 随后仍须等待 PK-000 精确发布，从 tracked Git tree 正式
  `create_filtered_copy()`，在副本运行 inventory、263 collect、完整 pytest、
  quality/copy/Ruff，并取得 Python 3.10–3.13 x64、Node 22、PowerShell
  5.1/7.4+ 新远端矩阵。

### 本轮八项文档门禁

- [x] TASK_RECORD — 已记录现有树结果、两个逆向失败、精确责任与后续门禁。
- [x] TASKS_BOARD — PK-020/PK-030 保持“待集成”，PK-900 保持“进行中”。
- [x] PUBLIC_README — 受控命令路径与 wrapper 实际 cwd 一致；参数安全声明暂未满足。
- [x] MODULE_CATALOG — 本轮不改变模块/API/数据所有权。
- [x] ARCHITECTURE_DOCS — 测试质量文档的 collection 前 fail-closed 目标已核对，
  现实现对上述两类签名尚未满足。
- [x] LOCAL_README — 未改变或访问本机秘密和个人 runtime。
- [x] AGENT_RULES — 遵守过滤副本、保护数据、外部服务、混合工作区与 Git 边界。
- [ ] VALIDATION — 现有树总数与正式用例通过，但独立 positional-only 和
  module-local fixture 逆向失败；PK-030 整改前不能进入发布矩阵。

## PK-030 参数契约第二次整改独立复验（2026-07-29）

### 结论

**不通过，继续精确退回 PK-030；PK-020 的 loopback/CORS 实现不重复退回。**

上一轮的两个原始缺陷已得到实质修复：required positional-only 现在会被
`validate_check_parameters()` 拒绝，模块本地同步/参数化/async fixture 与合法
pytest alias、literal `name=`、literal parametrize、keyword-only builtin fixture
也能被同一解析器识别。可是本轮独立逆向又确认两项当前阻断：

1. pytest module alias 只在模块顶层的少数简单语句中检查重绑定；位于模块级
   `for`、`if`、`try`/`except`、`with ... as`、walrus 和 `del` 中的重绑定均被
   错误放行，后续任意对象的 `@pt.fixture` 会被当成可信 pytest fixture。
2. 当前真实过滤副本的默认 collection 完整性检查不接受参数化 node id。
   合法 `check_fixture_parameter_is_injected[pytest-fixture-injected]` 已实际被
   pytest 收集，却仍被误报为未收集；因此 collect-only 和完整默认套件均在
   collection finish 阶段退出 4，来源任务报告的 “265 collected exit 0 /
   264 passed” 在当前同哈希源码上不能复现。

PK-900 保持“进行中”，PK-020/PK-030 均保持“待集成”。本地候选尚未通过，
因此不能进入 tracked filtered copy 和远端 Python/Node/PowerShell 发布矩阵。

### 隔离副本与共享解析器核对

- 使用当前候选工作树的纯相对路径字符串，经生产 `CopyPolicy` 分类后才构造
  `Path`，再由 `WorkingTreeCopyGuard` 逐组件 `lstat`，重新建立
  `source-parameter-fix-recheck` 过滤副本：
  `allowed=388 protected=112 ignored=8 lstat=1329`。
  `.github` 仍只包含精确
  `.github/workflows/windows-install.yml`；本轮没有扩大 copy 例外。
- 对根工作树和过滤副本的 `conftest.py`、`_parameter_contract.py`、
  `test_pytest_quality_gate.py`、inventory 脚本逐文件 SHA-256 比对，四项均完全
  相同，排除“副本落后于整改源码”的解释。
- `conftest.py` 与 `scripts/check_python_test_inventory.py` 均直接导入并调用
  `_parameter_contract.validate_check_parameters`；参数可满足性没有第二套
  parser。legacy main 的必需参数仍由同一文件中的
  `required_parameters_for_function` 计算。
- 从实际副本运行 inventory 得到：
  `test_files=67 default=53 isolated=14 checks=185 async_checks=107
  zero=99 fixture_or_parametrize=86 unsatisfied=0 legacy=12
  legacy_zero=12`。这些是当前树的实际扫描结果，但不能抵消下面的逆向和真实
  collection 失败。

### 原两项整改的独立逆向结果

- 纯 AST 合成矩阵确认以下均按预期拒绝：
  `check_posonly(tmp_path, /)`、被 literal parametrize 同名覆盖的 positional-only、
  dynamic fixture name、任意同名 decorator、直接赋值重绑定的 pytest/fixture
  alias、重复 exposed fixture name、decorator 位置参数、普通 unknown 和
  keyword-only unknown。
- 以下均按预期接受：模块本地同步 fixture、带 `params=` 的参数化 fixture、
  `import pytest as pt`、`from pytest import fixture as fx`、非空 literal
  `name=`、async fixture + async check、keyword-only builtin fixture、
  literal parametrize/mark alias 与模块本地 fixture override。
- 永久质量用例在过滤副本单独运行 11/11，其中包含真实子 pytest 对
  positional-only 的 collection 前拒绝，以及合法同步/async fixture 的真实注入
  和 await。故上一轮精确退回的两项本身可视为已修复。

### 阻断一：模块级控制流中的 pytest alias 重绑定仍可绕过

独立纯 AST 夹具先 `import pytest as pt`，再分别使用下列模块级语句重绑定 `pt`，
随后声明 `@pt.fixture` 和依赖该“fixture”的 `check_*`：

- `for pt in []`
- `if True: pt = object()`
- `try: pt = object()`
- `except Exception as pt`
- `with context as pt`
- `if (pt := object())`
- `del pt`

七类全部被 `validate_check_parameters()` 错误接受；输出为
`REBIND_ACCEPTED ['for', 'if_assign', 'try_assign', 'except_name',
'with_as', 'walrus', 'delete']`，夹具退出 1。

根因位于 `_pytest_import_aliases()`：它只遍历直接 `tree.body`，第二遍只识别直接
Assign/AnnAssign/AugAssign、定义和 import，没有按模块执行作用域检查控制流内的
绑定目标，也没有处理 NamedExpr、Delete、loop/with/except target。最小整改应
增加“模块执行作用域”的绑定收集器：递归模块级控制流但不进入嵌套
function/class/lambda/comprehension，并覆盖解包/星号目标、async loop/with、
except name、named expression、delete 和 match pattern；任何可信 pytest alias
被再次绑定都必须 fail closed。需增加纯 AST 与真实子 pytest 永久逆向，不能只
覆盖直接赋值。

### 阻断二：参数化 check 被 collection 完整性检查误报

在过滤副本的 `server` cwd 使用独立 venv 执行：

- `python ..\scripts\check_python_test_inventory.py --json`：退出 0，输出上述
  185/107/99/86/0 和 legacy 12/12。
- `python -m pytest tests --collect-only -q`：pytest 列出 265 个 node，其中明确
  包含
  `test_pytest_quality_gate.py::check_fixture_parameter_is_injected[pytest-fixture-injected]`，
  但 `pytest_collection_finish` 将期望值硬编码为不带参数后缀的 exact node id，
  最终报
  `ERROR: default Python checks escaped pytest collection:
  server/tests/test_pytest_quality_gate.py::check_fixture_parameter_is_injected`，
  退出 4。
- `python -m pytest tests -q`：同一 collection finish 错误，退出 4，测试体没有
  获得一次完整默认套件执行机会。
- `python -m pytest tests\test_pytest_quality_gate.py -q`：11/11；由于参数化
  节点仍能在单文件选择中运行，这个绿色结果不能替代默认入口失败。
- `python -m pytest tests\test_windows_ci_copy.py -q`：7 passed、1 个“过滤副本
  无 Git metadata”的预期 skip。
- `python -m ruff check tests ..\scripts\check_python_test_inventory.py`：
  `All checks passed!`。

最小整改限定在 PK-030 的 collection 完整性契约：检查顶层 check 时应把
`relative.py::check_name[param-id]` 视为对应 base check 已收集，同时仍要保证
至少一个实际 node、不能以未知 fixture/collection error/skip 冒充成功。应新增
参数化 check 的默认 `pytest tests --collect-only` 与完整套件永久回归，并断言
两个命令退出 0。

### 数据隔离、未执行项与后续门禁

- 全部动态命令位于 PK-900 自建过滤副本和独立 venv；未借用共享 `.venv`、
  `.venv-asr` 或 `node_modules`。
- 未读取、stat、diff、复制或输出真实 `.env`、个人状态、缓存、来源名单、
  profile、模型、音频、Voice Pack、QQ runtime 或 `vendor/`；未启动服务、BAT、
  QQ、Collector、LLM、ASR、TTS 或网络业务调用。
- 保留 PK-100/120/130/133/140/150/213 等混合工作区差异，不纳入本批。
- 因默认受控入口已经确定退出 4，本轮不再用“264 passed”或远端矩阵掩盖
  collection 阻断，也不触发远端 workflow。
- PK-030 修复上述两项后，PK-900 需重新构造候选过滤副本并重放 alias 控制流、
  参数化 check collection、inventory、collect-only、完整 pytest、quality、
  copy 和 Ruff。只有本地候选通过，才可由 PK-000 精确发布，再从 tracked Git
  tree 正式 `create_filtered_copy()` 并取得 Python 3.10–3.13 x64、Node 22、
  PowerShell 5.1/7.4+ 新矩阵。
- 本轮只追加 PK-900 报告；未修改产品、TASKS、PK-020/PK-030 状态，未暂存、
  提交、推送、切分支、触发 workflow 或清理。

### 本轮八项文档门禁

- [x] TASK_RECORD — 已记录原缺陷修复、两项新阻断、精确命令和最小责任范围。
- [x] TASKS_BOARD — PK-020/PK-030 保持“待集成”，PK-900 保持“进行中”。
- [x] PUBLIC_README — server-cwd 命令与公开 wrapper 一致；当前默认 collection
  失败已如实登记。
- [x] MODULE_CATALOG — 本轮不改变模块、API 或数据所有权。
- [x] ARCHITECTURE_DOCS — collection 前 fail-closed 目标已核对；alias 控制流与
  参数化 node 完整性尚未满足。
- [x] LOCAL_README — 未访问本机秘密、个人路径或 runtime。
- [x] AGENT_RULES — 遵守过滤副本、保护数据、混合工作区和 Git 边界。
- [ ] VALIDATION — 默认 collect/full 均退出 4，且七类 alias 重绑定被错误放行；
  PK-030 再整改前不能进入发布矩阵。

## PK-030 参数契约第三次独立复验（2026-07-29）

### 结论

**PK-020 + PK-030 本地候选通过，等待精确发布后的 tracked
`create_filtered_copy()` 与远端 Python 3.10–3.13 x64、Node 22、
PowerShell 5.1/7.4+ 矩阵。**

第二次复验退回的两项均已关闭：

1. pytest module/fixture/mark alias 的模块执行作用域重绑定会 fail closed，且没有
   误伤 function/class/lambda/comprehension 和 async 函数体内的局部同名。
2. collection 完整性不再解析或截断 display node id，而以 resolved
   `item.path`、`item.originalname` 和顶层 `pytest.Module` parent 建立身份；
   参数化实例可以满足原函数身份，类方法、skip/skipif、伪造 bracket 和同名前缀
   均不能满足。

本地候选现阶段没有实现阻断，但当前整改仍未进入精确发布的 tracked Git tree，
也没有基于新 commit 的目标 Windows 矩阵。因此 PK-900 继续“进行中”，PK-020/
PK-030 继续“待集成”，不得提前关闭。

### 独立候选过滤副本

- 没有复用来源任务临时目录或输出。PK-900 在
  `.pk900-pk030-third-review-20260729/candidate-source` 新建候选副本：
  先执行 `git ls-files -co --exclude-standard -z` 只取得纯相对路径名，再由当前
  生产 `CopyPolicy` 在任何 `Path`/`lstat`/copy 前分类；只有 allowed 项才交给
  `WorkingTreeCopyGuard` 做逐组件 `lstat` 和复制。
- 实际结果：
  `allowed=388 protected=112 ignored=8 copied=388 lstat=1329`。
  副本 `.github` 唯一文件仍是
  `.github/workflows/windows-install.yml`，精确例外没有扩大。
- 全部测试使用 PK-900 先前自建的独立 review venv；没有借用共享 `.venv`、
  `.venv-asr` 或 `node_modules`。

### Alias 独立逆向

- PK-900 自建纯 AST 矩阵覆盖：
  `for`、`if`、`try`、`except ... as`、`with ... as`、walrus、`del`、
  tuple/star unpack、`while`、match capture/rest、conditional import、
  function default/annotation/decorator expression 中的 walrus。
  14 类均被 `validate_check_parameters()` 拒绝，没有一项继续进入 fixture
  解析；输出为
  `PK900_ALIAS_OK static_rejected=14 child_rejected=7 nested_accepted=1`。
- 对原七类分别建立真实子 pytest 项目，conftest 在导入候选测试模块前调用共享
  parser。七次 `pytest --collect-only` 均以固定 UsageError、退出 4 在 collection
  前拒绝；输出均没有 fixture-not-found、call-phase TypeError 或假 skip。
- 另构造合法模块 alias，并在 function、class、lambda、comprehension 及 async
  function 内部使用局部同名（含 async for/with）；parser 接受，合法模块 fixture
  参数无 `unsatisfied`。这证明新 visitor 没有越过嵌套词法作用域。
- 源码核对确认 `_ModuleExecutionBindings` 递归模块级控制流和定义时求值的
  decorator/default/annotation/base 表达式，同时不进入 function/class body、
  lambda 或 comprehension；tuple/star、async loop/with、except、NamedExpr、
  Delete 和 match binding 均有显式处理。

### 参数化身份、junction 与伪造路径独立逆向

- PK-900 自建独立 pytest 项目，通过真实 Windows junction 运行 collect/full。
  实际包含双参数、多个含 `[]`、`::`、slash 和 space 的自定义 param id、两个
  模块中的同名 `check_shared`、同名前缀函数、类方法、skip 与 skipif：
  collect 为 8 项、退出 0；full 为 6 passed、2 skipped、退出 0；自建 hook
  输出 `PK900_IDENTITY_HOOK_OK`。
- 该 hook 直接使用候选
  `collected_function_identity()`，按 resolved module path 与 originalname
  比较。两个模块的同名函数保持独立，所有参数实例归属于各自 base identity；
  类方法因 parent 不是 `pytest.Module` 被拒，skip/skipif 不计入，合成
  `check_shared[forged]` 返回 `None`，`check_shared_prefix` 不会满足
  `check_shared`。
- 随后另建指向整个候选副本的真实 Windows junction，从
  `candidate-source-junction/server` 以 lexical 参数
  `.\tests\..\tests` 运行生产 conftest：
  实际收集 267 项、退出 0。故 CLI requested tests 与实际 item path 都经
  `Path.resolve(strict=False)` 汇合，junction 和 `..` 没有绕过完整性 hook。

### Inventory、默认套件与质量门禁

- `python ..\scripts\check_python_test_inventory.py --json`：退出 0；
  `files=67 default=53 isolated=14 controlled=6 manual=8
  checks=187 async_checks=107 zero=99 fixture_or_parametrize=88
  unsatisfied=0 legacy=12 legacy_zero=12`。
- PK-900 另写独立 recount，从副本实际 `test_*.py` 枚举文件、交叉检查 inventory
  分区，再逐文件解析 AST 和调用共享参数 parser；结果为：
  `files=67 default=53 isolated=14 controlled=6 manual=8 checks=187
  async=107 zero=99 fixture_or_parametrize=88 unsatisfied=0
  legacy=12 legacy_nonzero=0`。
- `python -m pytest tests --collect-only -q`：267 collected，退出 0；没有
  escaped check、unknown fixture、collection error 或 call TypeError。
- `python -m pytest tests\test_pytest_quality_gate.py -q`：13/13。
- 过滤副本 `test_windows_ci_copy.py`：7 passed、1 个“副本无 Git metadata”的
  预期 skip；共享根同一用例 8/8，证明 Git-tree 计划项也实际执行。
- `python -m ruff check tests ..\scripts\check_python_test_inventory.py`：
  `All checks passed!`。
- `_parameter_contract.py`、conftest、quality gate 与 inventory 脚本使用
  `ast.parse(..., feature_version=(3, 10))` 复核为 4/4。

### Fitness WinError 5 复现判断

- 在过滤副本内将 `test_fitness_module.py::check_failure_safety` 连续独立运行三次：
  3/3 通过，每次都使用 conftest 新建的 session 临时根。
- 两次完整默认套件分别使用显式、互不复用的
  `pytest-temp-run1`、`pytest-temp-run2`，均为：
  `265 passed, 2 skipped, 0 failed`，退出 0。两个 skip 固定为过滤副本无 Git
  metadata 与本机 8000 已占用；两轮均未出现 WinError 5 或 fitness 失败。
- 两轮均是单 pytest 进程、未启用 xdist；命令完成后两个 basetemp 各保留
  307 个隔离夹具文件供复核，`*.tmp`/临时替换残留均为 0。遵守“不清理工作区”
  要求，没有删除这些验收证据。
- 综合三次定向和两次完整复跑，本轮无法复现来源任务首次报告的单次
  `os.replace` WinError 5；当前没有足够证据把它升级为 fitness 业务阻断，也没有
  修改 fitness 实现或测试。若新远端矩阵再次出现相同失败，应保留 runner 的
  basetemp/进程占用证据并重新归属，不得以重跑绿色直接掩盖。

### 文档、数据隔离与剩余门禁

- `scripts/check_task_docs.py`：`24 gated task(s)`，退出 0。
- `git diff --check`：退出 0；只有混合工作区既有 LF→CRLF 提示。
- 未读取、stat、diff、复制、输出或修改真实 `.env`、个人状态、缓存、来源名单、
  profile、模型、参考音频、Voice Pack、QQ runtime、共享环境或 `vendor/`；
  没有启动服务、BAT、QQ、Collector、LLM、ASR、TTS 或外部业务请求。
- PK-100/120/130/133/140/150/213 等混合差异继续排除。本轮只追加 PK-900
  报告，未修改产品、TASKS、PK-020/PK-030 状态，未暂存、提交、推送、切分支、
  触发 workflow 或清理。
- 下一步仍由 PK-000 对 PK-020 + PK-030 精确文件/hunk 做发布审查并提交。发布
  后 PK-900 必须从真实 tracked Git tree 正式运行 `create_filtered_copy()`，
  在该副本重跑 inventory、collect、完整 pytest、quality、copy、Ruff，并取得
  同一 commit 的 Python 3.10/3.11/3.12/3.13 x64、Node 22、Windows
  PowerShell 5.1 和 PowerShell 7.4+ 全绿证据。

### 本轮八项文档门禁

- [x] TASK_RECORD — 已记录整改差异、独立逆向、两轮完整套件和 fitness 判断。
- [x] TASKS_BOARD — PK-020/PK-030 保持“待集成”，PK-900 保持“进行中”。
- [x] PUBLIC_README — server-cwd、受控入口和过滤副本行为与公开说明一致。
- [x] MODULE_CATALOG — 本轮不改变模块、API、Catalog 或数据所有权。
- [x] ARCHITECTURE_DOCS — Python 测试质量与 Windows filtered-copy 边界一致。
- [x] LOCAL_README — 未访问或改变本机秘密、个人路径或 runtime。
- [x] AGENT_RULES — 遵守保护数据、隔离副本、混合工作区和 Git 边界。
- [ ] VALIDATION — 本地候选通过；精确发布后的 tracked copy 与完整远端目标矩阵
  尚未取得，最终关闭门禁仍未满足。

## PK-011 + PK-020 + PK-030 最终可安装模块发布批次入场（2026-07-31）

### 批次与状态

- 本轮批次明确登记为 `PK-011 + PK-020 + PK-030`。PK-011 已完成共享串行装配、
  19 个业务项的确定性候选包与本地累计验证，现为“待集成”；PK-020、PK-030
  继续保持“待集成”；PK-900 保持“进行中”。
- 本次入场不把任何任务提前标为“已完成”，不发布 ZIP，不暂存、提交或推送。
  最终状态必须等待独立验收报告，以及精确提交后的 tracked filtered copy 和同一
  commit 的远端 Windows 矩阵。

### PK-900 独立验收范围

1. 在没有任何可选模块、外部服务、秘密、模型或配置时，Core 仍只提供健康检查、
   模块生命周期、固定官方目录与 dashboard 外壳，并能正常启动。
2. 对官方 19 项从各自正式 builder 重建两轮，核对 ZIP 字节、大小、SHA-256、
   manifest SHA-256、SemVer、依赖、权限、API namespace、legacy endpoint、数据策略、
   固定 release tag/asset URL 与 `official-catalog.json` 完全一致。
3. 在全临时 registry/runtime/data 中验证依赖图无环、安装默认停用、缺强依赖拒绝、
   配置缺失隔离、依赖序启用、逆序停用、更新/回滚约束、卸载保留数据和重装恢复；
   sidecar 不得执行 manifest 命令或回退开发源码路径。
4. 安装启用并重启后的 versioned/legacy API 与动态面板必须来自同一模块 service；
   停用或卸载并重启后不再装配。不得存在开发源码与 runtime package 双路由、重复
   Collector、重复限流器、残留 Provider 或异步清理泄漏。
5. 独立审计所有包、Catalog、公开文档和实际差异，确认不存在 `.env`、Cookie、
   Token、个人状态、真实缓存/名单、LLM profile、模型、权重、参考音频、Voice Pack
   注册表、本机绝对路径、`.venv`、`node_modules`、上游 GPT-SoVITS 源码或 `vendor/`。
6. 重跑 Python inventory、`pytest --collect-only`、完整默认 pytest、Ruff、compileall、
   全部 JS/MJS `node --check`、Node 测试、Catalog 校验、任务文档门禁与
   `git diff --check`。HTTP/WS、Collector、LLM、voice、QQ 和下载均使用
   ASGITransport/MockTransport/fake provider/fake process/系统临时目录，零真实网络。
7. 精确发布候选后，从真实 tracked Git tree 运行 `create_filtered_copy()`，在该副本
   重放 PK-020/PK-030 安装与测试质量门禁，并取得同一 commit 的 Python
   3.10/3.11/3.12/3.13 x64、Node 22、Windows PowerShell 5.1 与 PowerShell 7.4+
   workflow 全绿证据。旧 commit 或当前开发机单版本结果不能替代该矩阵。

### 入场候选证据（仅供复核，不替代独立结论）

- PK-000 的候选环境收集 382 项并全部通过；Ruff、compileall、44 个 JS/MJS
  `node --check`、Node 83/83、QQ 包 11/11、qq-control 8/8、26 个任务文档门禁和
  `git diff --check` 均通过。
- 19 个候选在两个独立临时目录中重建，19/19 字节与摘要一致；Catalog 以最终资产根
  执行 `--check --validate-catalog` 通过。测试只使用临时路径和 fake/MockTransport，
  未访问受保护数据或真实外部服务。
- 以上是实现方/总控的本地交接证据。PK-900 必须独立检查实际源码与差异，并主动
  构造失败、卸载清理、Provider 解除和 sidecar 配置缺失场景，不得只接受本记录。

### 本轮完成文档门禁

- [x] TASK_RECORD — 已记录批次、候选、独立范围、必跑门禁和剩余发布条件。
- [x] TASKS_BOARD — PK-011/020/030 为“待集成”，PK-900 为“进行中”。
- [x] PUBLIC_README — 普通用户安装流、显式生命周期操作、重启和未发布状态已同步。
- [x] MODULE_CATALOG — 19 项候选与本地最终资产核对通过，正式 URL 等待发布复验。
- [x] ARCHITECTURE_DOCS — Core/包/模块交互、sidecar、数据与发布契约已同步。
- [x] LOCAL_README — 本轮不记录、读取或修改本机路径、秘密或个人状态。
- [x] AGENT_RULES — 沿用现有安全、混合工作区、测试与 Git 规则，无新增规则。
- [ ] VALIDATION — 本地候选门禁通过；独立 PK-900、tracked copy 和远端矩阵待执行。

## PK-011 首轮独立生命周期验收（2026-07-31）

**结论：不通过，已退回 PK-011 最小整改。** PK-900 保持“进行中”；PK-020/
PK-030 的 tracked copy 与远端矩阵门禁尚未进入执行。

### 通过的累计门禁

- inventory 为 87 个文件（73 默认、14 隔离），`pytest --collect-only` 收集 382 项，
  完整默认 pytest 为 `382 passed`；聚焦 package/host/cleanup 回归 34 项通过。
- Ruff 通过；显式枚举并排除 `.venv*`、保护数据和依赖目录后，360 个项目 Python
  文件编译通过；44 个 JS/MJS `node --check`、QQ Node 83/83、dashboard Node 1/1
  通过。
- 独立临时目录重建 19 个资产，19 个 release fragment 与 Catalog 的
  `--check --validate-catalog` 通过；任务文档门禁 26 项通过；排除两份禁止读取的
  真实状态文件后 `git diff --check` 退出 0，仅有行尾提示。

### 阻断证据与最小责任

- 正式 in-process backend 中，`youtube`、`x_monitor`、`fitness`、
  `affection_memory`、`daily_briefing`、`demon_slayer`、`intel_sources`、`focus`
  共 8 个只有 `register()`，没有 `unregister()`。Loader 回退路由和动态 import 后，
  无法自动回退这些模块写入的 app state、Provider、Collector 或 middleware。
- 使用临时包、临时 registry/runtime/data 的独立 `affection_memory` 探针得到：load
  为 `loaded`，unload 为 `unloaded`，路由无残留，但 conversation Provider、模块状态
  和 Origin middleware 均残留。该事实直接违反卸载/失败回滚零残留契约；现有完整
  套件全绿说明永久测试此前没有覆盖同一 app 的真实 loader unload。
- 最小整改归 PK-011 与上述模块：补身份校验且幂等的 `unregister(app)`，只解除本模块
  拥有的 state/provider/collector/middleware；注册中途失败回滚已完成副作用；增加
  正式包 Loader/Coordinator 卸载、失败注入、重复解注册与宿主对象保护回归。不得
  借此重写业务规则、API 或数据所有权。

### 隔离与过程说明

- 测试使用系统临时目录、工作区外验收环境、fake/MockTransport 和假进程；未读取
  真实 `.env`、个人状态、缓存、名单、模型、Voice Pack registry 或 `vendor/`，未
  执行 Git 写操作、真实服务或外部网络。
- 验收曾启动范围过宽的 `python -B -m compileall -q server scripts`，约 11 秒后
  意识到可能遍历 `server/.venv-asr` 并主动终止。该命令没有完成结果，不能声称完全
  未发生目录元数据遍历。之后正式门禁改为显式项目文件清单并通过；没有使用、修改
  或安装既有环境。此过程瑕疵不得从历史记录删除或弱化。

### 本轮文档门禁

- [x] TASK_RECORD — 已记录累计门禁、主动探针、阻断、责任与过程瑕疵。
- [x] TASKS_BOARD — PK-011 整改后恢复“待集成”，PK-020/030 待集成，PK-900 进行中。
- [x] PUBLIC_README — 本轮未发现公开生命周期文案与候选实现的新差异。
- [x] MODULE_CATALOG — 首轮 19 项候选重建与目录一致；仍不是已发布资产。
- [x] ARCHITECTURE_DOCS — 阻断由既有卸载零残留契约直接判定，无需扩大契约。
- [x] LOCAL_README — 未读取或改变本机配置、路径或秘密。
- [x] AGENT_RULES — 如实保留过宽 compile 尝试，后续用显式文件清单纠正。
- [ ] VALIDATION — 累计门禁通过，但首轮 8 个模块同进程卸载残留，整批不通过。

## PK-011 第二轮失败与第三轮独立复验（2026-07-31）

### 第二轮结论（历史失败，保留不覆盖）

**第二轮仍不通过。** 首轮补入的 8 个正式包 `unregister(app)` 已能清除
routes、state、Provider、Collector 与 middleware，且当轮 inventory、两轮 19 包
重建、Catalog、384 项完整 pytest、Ruff、显式 compile、44 项 `node --check`、
Node 83/83、dashboard 1/1、任务文档和差异门禁均为绿色；但主动复验仍发现两类
阻断：

- 正常 unload 后，`youtube/x_monitor/fitness/affection_memory/daily_briefing/
  demon_slayer/intel_sources/focus` 的动态 import 树分别残留
  `8/13/5/6/5/5/9/2` 个 `sys.modules` 项。Loader 当时只删除生成包顶层名，未按
  前缀删除已导入子模块；同一缺陷也影响 import failure、register failure 与
  coordinator rollback。
- `intel_sources` 在发布 `intel_source_snapshot_provider` 时注入中途失败后，先写入的
  `intel_source_registry` 与 `intel_source_config_reader` 仍留在 app state；routes
  已恢复，但 registry/config reader/registered/owner/Provider 全量事务边界没有成立。

因此第二轮没有因其他门禁全绿而判为通过，PK-011、PK-020、PK-030 保持“待集成”，
PK-900 保持“进行中”。最小整改是 Loader 按生成包名前缀清除完整 import 树，以及
`intel_sources.register()` 在任何 provider 发布失败时恢复完整旧 state 和本轮 routes。

### 第三轮结论

**本地候选通过；整批尚不能最终关闭。** 本轮独立重放两项原阻断，并对当前实际
源码、包、Catalog 和完整门禁复验，没有发现新的本地实现阻断。精确发布后的
tracked filtered copy 与同一 commit 远端 Windows 矩阵仍未完成，因此 PK-011、
PK-020、PK-030 继续“待集成”，PK-900 继续“进行中”，不发布、不提前标记完成。

### 原阻断重放与生命周期证据

- 使用工作区外临时 Python 3.12.7 解释器、系统临时 package/registry/runtime/data、
  正式 builder、`InProcessModuleLoader` 与 `ModuleActivationCoordinator` 重放 8 包。
  `youtube/x_monitor/fitness/affection_memory/daily_briefing/demon_slayer/
  intel_sources/focus` 均完成 load→unload；routes、app state、Provider、Collector、
  middleware 与生成包顶层/前缀子模块全部恢复为基线，残留数均为 0。
- 正式回归同时验证重复 `unregister(app)` 幂等，且宿主替换后的
  conversation Provider 不被模块清除。Loader 现以 `_clear_import_tree()` 在正常
  unload、entrypoint import failure、register failure 和 coordinator rollback
  删除完整动态 import 树；另以临时合成包独立重放后三种路径，顶层及子模块均为 0。
- `intel_sources` provider 发布中途失败夹具在写 registry/config reader 后、写
  snapshot provider 时抛错；当前 routes、registry、config reader、snapshot
  provider、registered flag 与 registration owner 全部恢复原对象/原缺失状态。
  正常成功装载后卸载也恢复同一基线。
- 第一次编写临时 Loader 逆向夹具时沿用了错误 manifest 字段 `api_namespace`，在
  `validate_manifest()` 阶段退出；修正为当前公开 `api_namespaces` 及完整 Schema 后，
  import/register/coordinator 三条故障路径全部通过。该首次失败是验收夹具错误，
  未进入产品装载，也不作为产品失败隐藏。

### 19 包、Catalog 与完整门禁

- `test_official_module_release_set.py` 从 19 个正式 builder 在两个独立临时目录重建，
  19/19 ZIP 字节一致，并逐项核对实际 manifest、版本、大小、package SHA-256、
  manifest SHA-256、依赖图、安装、依赖序启用、逆序停用、卸载保留数据与重装；通过。
- `intel_sources@1.1.2` 实际 Catalog/release/manifest 一致：大小 `37495` bytes，
  ZIP SHA-256 `8da2335c3837795cb2587130948e69fe10ece7aa2bd8d17aed86812d59525850`，
  manifest SHA-256 `ba8354949be3de0304797acc6fb92fb049b90d1450550d929cddb9b6c9920362`，
  tag `module-intel-sources-v1.1.2`，asset `intel-sources-1.1.2.zip`。
- inventory：87 个文件（73 默认、14 隔离），274 个顶层 check 参数契约、
  `unsatisfied=0`；默认 collect 为 385 项，完整默认套件为 `385 passed`、53 warnings，
  约 5 分 36 秒。相对第二轮的 384 项，本轮新增的永久故障注入已实际收集执行。
- Ruff：`server/tests` 与 `scripts/check_python_test_inventory.py` 全部通过；显式枚举并
  排除 `.venv*`、`node_modules`、`vendor` 后，360 个项目 Python 文件
  `py_compile` 通过；44 个 JS/MJS `node --check` 通过。
- QQ Node `83/83`、dashboard Node `1/1` 通过；官方 Catalog
  `--check --validate-catalog` 通过；报告写入后任务文档门禁为 26 项通过。
- 排除两份禁止读取的 `server/systems/data` 状态后执行 `git diff --check`，退出 0；
  仅有混合工作区既有 LF→CRLF 提示，无 whitespace error。

### 隔离、差异与剩余发布门禁

- 本轮只使用 fake/MockTransport、临时目录和临时状态；未联网、未启动真实 API、
  QQ、Collector、LLM、ASR、TTS 或 GPT-SoVITS，未执行任何 Git 写操作或发布。
- 未读取、stat 详细内容、diff、复制或修改真实 `.env`、个人状态、缓存、名单、
  profile、模型、参考音频、Voice Pack registry、两份 `server/systems/data` 状态、
  `vendor/` 或 `node_modules/`。实际差异审阅只覆盖 Loader、正式 package source、
  intel_sources 注册事务、永久测试、Catalog/release metadata 与任务记录。
- 当前工作区仍为混合候选树；本轮仅追加本 PK-900 报告，不修改产品、TASKS 或其他
  任务状态。下一步仍需由 PK-000 精确审查并提交；随后从真实 tracked Git tree
  正式运行 `create_filtered_copy()`，并取得同一 commit 的 Python 3.10/3.11/3.12/
  3.13 x64、Node 22、Windows PowerShell 5.1 与 PowerShell 7.4+ 全绿矩阵。

### 本轮八项文档门禁

- [x] TASK_RECORD — 保留首轮和第二轮失败证据，并追加第三轮修复、独立重放、完整门禁、隔离和剩余条件。
- [x] TASKS_BOARD — PK-011/020/030 保持“待集成”，PK-900 保持“进行中”。
- [x] PUBLIC_README — 生命周期、候选未发布、重启与安装说明未发生新的用户可见变更。
- [x] MODULE_CATALOG — 19 项重建与当前候选目录一致；`intel_sources@1.1.2` 精确元数据复核通过。
- [x] ARCHITECTURE_DOCS — 完整 import 树清理与注册事务恢复符合既有零残留契约，无需扩大架构。
- [x] LOCAL_README — 未读取或改变本机路径、配置、秘密或 runtime。
- [x] AGENT_RULES — 使用指定工作区外解释器和显式安全文件清单，未触碰受保护路径或真实服务。
- [ ] VALIDATION — 本地第三轮全部通过；精确发布后的 tracked filtered copy 与同一 commit 远端矩阵仍未完成。

## PK-011 + PK-020 + PK-030 + PK-213 精确远端矩阵与私有预发布（2026-08-01）

- Draft PR `#8` 首次在提交 `a3d1d770c39863898d29cdc421c96b2606531b30`
  触发矩阵 `30647265014`。四版本安装与收集均通过，完整测试共同暴露 Windows
  runner 的 8.3 短路径/长路径差异：Bilibili 安装包误拒绝同一数据目录，Demon
  Slayer 测试直接比较路径字符串。整改保留 `..`、symlink、junction/reparse
  fail-closed，并把合法 8.3 表示规范化；Bilibili ZIP、摘要和官方目录同步重建。
- 第二次提交 `c60e120edd0877a95eac698905991bd249067513` 的矩阵
  `30648069295` 中 Python 3.11/3.12/3.13 全绿；Python 3.10 唯一失败为 pytest
  protected-path tripwire 只拦截新版 pathlib 的 io/os 接缝。整改在每个测试调用期
  同时保护稳定的 `Path.open/stat/lstat`，真实 I/O 前仍抛固定保护异常，不扩大
  测试可访问路径。
- 最终提交 `48e06b09aa5decde3ba34d096b851416b8b4a782` 的矩阵
  `30648742199` 四个 Python 3.10/3.11/3.12/3.13 x64 job 全部成功；包括干净
  Core/voice/dev 安装、385 项完整离线 pytest、Ruff、PS 5.1/7.4，Python 3.11
  另含 Node 22、QQ `npm ci`、Node 测试和脚本检查。
- 19 个官方模块 ZIP 已逐项与 `official-catalog.json` 的大小/SHA-256 对照后上传
  到各自固定 Release；GitHub 服务端 digest 19/19 与 Catalog 一致。Kei Voice
  Pack 三件套也已上传到固定 Release，ZIP 服务端 digest 与本机构建摘要一致。
- 仓库当前明确保持 `PRIVATE` 供一名授权协作者完成全项目测试。匿名下载返回 404，
  Core 下载器也不会接收 GitHub Token，因此本轮属于私有预发布而非普通用户公开
  发布；不写 Voice Pack 生产 Catalog，不把 PK-011/020/030/213 或 PK-900 提前
  标为“已完成”。公开仓库后仍需重验匿名固定 URL、模块中心一键安装和 Voice Pack
  远程安装，方可最终关闭。

## PK-100 + PK-120 累计发布候选独立验收（2026-08-02）

### 结论

**本子批次通过。** PK-100 的每日情报聚合卡公共布局修复、PK-120 的
`x_monitor@1.1.0`、固定 FxEmbed 后备、一层直接父帖、单缓存与动态面板累计候选均
通过独立源码、逆向、生命周期、浏览器和回归验收。未发现需要退回 PK-100 或 PK-120
的集成阻断；建议 PK-000 对本批精确 hunk 做最终复核后关闭并发布两项。PK-900 未修改
`TASKS.md` 或 PK-100/PK-120 状态，也未替其他仍开放批次作最终关闭决定。

### 实际差异与契约复核

- 本轮先读完根 README、AGENTS、本机 README、任务板、PK-100/PK-120/PK-900 最新
  任务记录及完整官方 Catalog；只以显式路径检查当前分支和本批差异。实际产品 hunk
  限于公共 `shell.css`、X feature/package/release 输入、单一 X cache 归一化、相关
  测试、README 和 Catalog；其他任务与受保护数据均未纳入。
- PK-100 删除了三组 intelligence 专用的隐藏图片/强制单列覆盖，仅保留 sticky 导航
  所需的 `overflow:visible`。公共桌面布局仍为
  `minmax(220px,280px) minmax(0,1fr)`，移动端复用公共单列；六个安装单元仍形成六个
  tab/tabpanel，标签点击仅调用本地 `selectGroupPanel()`。
- PK-120 的 Nitter/RSS 仍为首选，只有首选 fetch 抛出受控失败后才调用注入的
  FxEmbed fetcher。正式 fetcher 把 origin 固定为 `https://api.fxtwitter.com`，路径
  allowlist 仅含单用户 statuses 与单 status；默认 client 禁止环境代理和重定向，
  没有 URL、Token、Key、cursor、groupthreads 或 conversation 配置面。
- post/quote 进入发帖视图，reply 进入回复视图，repost、作者不符、冲突标记和 unknown
  被排除。回复正文始终来自当前用户；合法 reply 最多补抓一个作者匹配的直接父帖，
  父帖自身即使含 reply/quote 标记也不会递归。引用帖不补抓正文，最多 8 个不同父帖、
  并发最多 3。
- 唯一运行缓存仍为 `x_daily_posts.json`；没有 replies router/service/API/cache。普通
  profiles/posts GET、页面加载、折叠、日期/结果/发帖回复切换和来源保存不进入外部
  fetcher；只有显式资料刷新或言论获取进入相应网络接缝。动态面板为每个用户和每个
  day/since 模式保存独立内存状态，不写浏览器存储；原文和直接父帖均为
  `noopener noreferrer` 按钮式链接。

### 包、Catalog 与临时生命周期

- 在系统临时目录两次独立运行 `package_builder.py`，两个 ZIP 字节完全一致：大小
  `110315`，SHA-256
  `3ab7d1b0425883e7d0e8ec81ad2323d9cacbfb9af655413307611ceaa7052669`；包内
  `manifest.json` SHA-256 为
  `aa028f6bdf1ac611f211da0c2ce5a6566cf113ac51f908acea8708c299fcd3d5`。
  13 个包条目无 traversal、`.env`、cache、runtime、个人数据、历史 replies、
  `vendor` 或 `node_modules`；内容扫描无私钥、凭证形态值或开发机绝对路径。
- `manifest.json`、release fragment、release Catalog entry、共享
  `official-catalog.json` 与 README 的版本、依赖、权限、重启、数据策略、tag、asset、
  大小和两项摘要一致；官方 Catalog schema 校验通过。
- 独立临时 registry/runtime/data 夹具完成 `intel_sources` 依赖安装启用、
  `x_monitor@1.0.9` 安装启用、错误摘要更新失败隔离、更新到 `1.1.0`、回滚到
  `1.0.9`、停用和卸载。失败更新保留旧版本，成功更新/回滚状态一致，卸载保留临时
  module data；安装后的 `dashboard/index.js` 从 runtime package 的 asset path 读取并
  含正式 `mount()`。

### 独立逆向与浏览器结果

- 临时 FastAPI + fake source snapshot + tripwire 证明普通 profiles/posts GET 与未来
  日期拒绝均为零 profile/Nitter/Fx 调用；Nitter 成功时 Fx 调用为 0。另一夹具给父帖
  注入 reply/quote 关系，实际请求仍严格只有一次 timeline 和一次直接父帖，外部作者
  条目被排除、quote 无 parent context。
- 去标识 fake preview 仅绑定 loopback，验收后已关闭。收起 intelligence 卡实测约
  `343×136`；桌面展开实测 `280px + 726px` 双栏、图片 `280×350` 且可见，六个来源
  tab、六个 panel、始终一个可见。移动端实测单列，图片 `260×325`，document 无横向
  溢出。切到 X 标签只改变 active/visible panel；期间请求增量只有既有 Core 健康轮询，
  无来源或业务 API。

### 实际命令与结果

- 使用任务指定 ASR 测试解释器逐项运行：`test_dashboard_shell.py`、
  `test_intel_sources_dashboard.py`、`test_x_monitor.py`、`test_x_fxembed.py`、
  `test_x_monitor_module.py`、`test_x_monitor_dashboard.py`、`test_installable_modules.py`、
  `test_official_module_catalog.py`、`test_module_host_assembly.py`、
  `test_intel_sources_integration.py`、`test_daily_briefing_module.py`、
  `test_daily_briefing_summary_cache.py`、`test_feature_catalog.py`：全部通过。
- 使用工作区外既有隔离验收解释器执行上述 13 文件的 pytest 汇总：`70 passed`；追加
  `test_intel_source_config.py`、`test_intel_sources_registry.py`、
  `test_daily_briefing_installable.py`、`test_daily_briefing_generation_status.py`：
  `22 passed`。累计 `92 passed`，只有 Pydantic 弃用 warning，无 skip/fail/error。
- 总控随后提供另一份只读既有 Python 3.12.7 隔离解释器；PK-900 未安装或修改其中
  依赖，独立重跑本批精确 16 文件（PK-010 lifecycle/catalog/host、PK-100 dashboard、
  PK-120 X/Fx/module/integration、来源配置/registry、daily briefing 与 feature catalog）：
  `84 passed, 11 warnings in 12.34s`，无 skip/fail/error。warning 仍仅为 Pydantic 2
  对 class-based config 的弃用提示。
- 13 个 dashboard/X JavaScript 文件逐项 `node --check`：通过；
  `node --test server/tests/test_dashboard_briefing_progress.mjs`：`1 passed`。
- 相关 X、cache、dashboard 与测试 Python 文件定向 `py_compile`：通过，pycache 指向
  系统临时目录；`build_official_module_catalog.py --validate-catalog`：通过；
  `scripts/check_task_docs.py`：`26 gated task(s)` 通过。
- 过程记录：公共 `scripts/python.ps1` 首次被本机执行策略拦截；用临时 bypass 调用后，
  其解析环境缺 FastAPI。任务指定 ASR 环境可运行正式 standalone tests，但未安装
  pytest，因此 pytest 汇总改用已有工作区外验收环境，未联网安装依赖。首个 ZIP 扫描
  命令在 PowerShell 引号解析阶段失败，构建器未执行；拆分后两次构建成功。首个独立
  生命周期夹具把卸载状态误写成 `not_installed`，实际公共契约为 `available`；打印临时
  状态确认后修正夹具并完整通过，不属于产品失败。

### 数据隔离、风险与工作区排除

- 所有写入只发生于系统临时 package/registry/runtime/data、临时 UI asset 或浏览器
  fake preview；所有 HTTP 使用 ASGITransport/MockTransport/fake fetcher。未启动真实
  Core、Collector、Nitter、FxEmbed、QQ、LLM、TTS、ASR 或 sidecar，未执行外部业务
  请求。
- 未读取、stat 内容、diff、复制、打印、迁移或修改真实 `.env`、来源名单、X 缓存、
  个人状态、凭据、profile、模型、音频、Voice Pack registry、QQ runtime、受保护
  system 状态、`server/runtime/` 或 `vendor/`。差异和扫描均使用本批显式 allowlist。
- 工作区仍含 PK-150、PK-213 及其他任务的混合修改；这些差异未纳入本批结论。未执行
  Git 暂存、提交、推送、发布、切分支或工作区清理。
- 已知非阻断限制：本轮只验证候选 ZIP、Catalog 元数据和临时生命周期，没有访问固定
  GitHub 下载 URL 或执行真实发布；是否把该候选纳入最终提交/Release 仍由 PK-000
  负责。

### 本轮八项文档门禁

- [x] TASK_RECORD — 已追加独立范围、差异、逆向、浏览器、包、生命周期和命令结果。
- [x] TASKS_BOARD — 未修改；PK-100/PK-120 最终关闭交 PK-000。
- [x] PUBLIC_README — Nitter/FxEmbed、直接父帖、单缓存和零网络普通操作与实现一致。
- [x] MODULE_CATALOG — x_monitor 1.1.0 的版本、URL、大小、包/manifest 摘要一致且合法。
- [x] ARCHITECTURE_DOCS — Collector 1.0、独立安装单元/聚合展示和单 service 边界未改变。
- [x] LOCAL_README — 未改变或输出本机配置、秘密、端口和个人路径契约。
- [x] AGENT_RULES — 遵守显式路径、临时数据、离线 fake、混合工作区和 Git 边界。
- [x] VALIDATION — 定向/累计 pytest、standalone tests、逆向、双构建、生命周期、浏览器、
  Python/JavaScript、Catalog、文档和精确差异门禁均已完成。

## PK-011 集中模块分发独立验收（2026-08-02）

### 结论与范围

- 结论：**通过**。`PK-011` 的 19 个确定性模块包已从主仓库逐模块 Release 迁移到
  私有专用仓库 `songshu-yu/Project-Kei-Modules` 的单一批次 Release
  `modules-2026.08.02`；远端实物、bundled Catalog、19 个 release fragment、
  package builder、Core 固定信任边界、README/架构说明与累计回归均达到本批门禁。
- 本结论只建议 PK-000 对本次集中分发增量做最终关闭；PK-900 未修改 `TASKS.md`，
  未把 `PK-011` 或 `PK-900` 标记为“已完成”。旧逐模块 Release 只作为历史兼容入口
  保留，不属于当前 Catalog 来源。
- 入场后曾独立发现 PK-011 正文、公开 README、可安装模块架构和 7 份模块发布说明仍
  残留旧主仓库固定源。PK-000 按最小范围改为 `Project-Kei-Modules` 后，PK-900 重新
  读取上下文并在当前契约文件、Core、19 个 builder/fragment/release 说明范围重跑
  旧仓库与旧 tag 扫描；当前残留为 0。历史 Git/任务事实未被抹除。

### 私有仓库、Release 与远端实物

- 只读 GitHub API 实测仓库 `private=true`、`visibility=private`、默认分支 `main`，未
  archive/disable。分支 tree 只含根/分类 README、`.gitignore` 与
  `catalog/official-catalog.json`，没有把 ZIP、模块源码、模型或 Voice Pack 大资产
  提交进分发仓库。
- tag `modules-2026.08.02` 对应非 draft、非 prerelease Release，恰有 19 个状态为
  `uploaded` 的 ZIP；无第 20 个附件。PK-900 使用现有 GitHub 登录态经只读 asset API
  把 19 个附件下载到系统临时目录
  `pk900-pk011-assets-7o1y_0e7`，逐项重新计算 size/SHA-256，19/19 与 GitHub asset
  metadata 和 bundled Catalog 一致。
- 19 个本地 builder 再次构建到独立系统临时目录，构建结果与已下载的 19 个远端 ZIP
  逐字节一致；正式 release-set 测试还对每个 builder 连续构建两次并验证字节一致。
  使用远端实物、19 个 fragments 和固定 `generated_at` 执行
  `build_official_module_catalog.py --check` 通过。远端 Catalog 与 bundled Catalog
  JSON 语义完全相同（19/19 字段相等）；文本字节因格式化不同而不相等，Catalog 契约
  不冻结自身文本摘要，此差异不影响解析、Schema 或模块资产摘要。
- 对 19 个实际远端 ZIP 扫描 entry path、symlink mode、`.env`、`data`、cache、
  `vendor`、`node_modules`、本机用户路径、GitHub/OpenAI key 形态及常见模型/音频后缀，
  修正两处仅为 GitHub/QQ `/users/` API 路径的大小写误报后，真实命中为 0。最大 ZIP
  为 `126244` 字节；没有权重、参考音频、模型或其他 Voice Pack 大型资产。

### Core 信任边界与私有阶段降级

- `OFFICIAL_OWNER=songshu-yu`、`OFFICIAL_REPOSITORY=Project-Kei-Modules`、固定 raw
  Catalog URL、Catalog schema repository const、19 个 release URL/tag 彼此一致。
  Catalog 校验拒绝任意 owner/repository/package URL；HTTP client 使用
  `trust_env=false`、不设置 Authorization，也不接受用户 URL 或 Token。
- 对固定 raw Catalog URL 的真实匿名请求返回 `404`。独立 MockTransport 夹具同时证明：
  请求严格等于固定 URL且无 Authorization；404 映射为
  `official_catalog_refresh_failed/catalog_download`，不创建 cache；刷新失败前后普通目录
  均继续从 bundled Catalog 返回 19 个模块。私有阶段因此保留可启动、可浏览的降级，
  但一键远程安装不可用。
- README 已清楚区分当前私有协作者流程（先登录 `gh`、下载到系统临时目录、逐项校验
  摘要、再走本地可信安装）与未来公开用户流程（显式刷新、确认、启用、按提示重启）；
  同时说明匿名 404、旧 Releases 仅兼容保留、页面普通操作零网络及不接受任意 URL、
  Token 或远程脚本。该私有部署限制符合本批冻结契约，不作为阻断。

### 累计测试与质量门禁

- 定向命令：工作区外既有 Python 3.12.7 隔离解释器执行
  `pytest -q tests/test_official_module_release_set.py tests/test_official_module_catalog.py
  tests/test_installable_modules.py tests/test_module_host_assembly.py
  tests/test_dashboard_shell.py tests/test_feature_catalog.py`：`30 passed`。覆盖 19 包双构建、
  拓扑安装、启停、卸载保留数据、重装、注册失败回滚、官方目录防护、dashboard 和
  lifecycle 基础链路。
- 完整命令：同一隔离解释器在 `server/` 执行 `pytest tests -q`：
  `391 passed, 53 warnings in 339.26s`；无 skip/fail/error，warning 仅为既有 Pydantic
  弃用提示。
- 实际 inventory：`88` 个测试文件、`74` 个默认、`14` 个隔离、`280` 个默认
  `check_*`、`125` 个 async check、`0` 个不可满足参数；12/12 legacy entrypoint 无
  必需参数。
- `ruff check tests ..\\scripts\\check_python_test_inventory.py`：通过；相关 21 个 Python
  文件 `py_compile`：通过；29 个 dashboard package JavaScript `node --check`：通过；
  dashboard Node test：`1 passed`。
- `build_official_module_catalog.py --validate-catalog`：通过；26 项任务文档门禁通过；
  本批显式 allowlist 的 `git diff --check` 退出 0，仅有既有 LF→CRLF 提示。

### 数据隔离、限制与工作区排除

- 所有构建、下载、registry/runtime/data 与逆向夹具均位于系统临时目录；网络访问只限
  GitHub 仓库/Release/Catalog 的只读验收和匿名 raw URL 状态核对。未启动 Core、QQ、
  Collector、LLM、ASR、TTS、GPT-SoVITS 或任何真实业务服务，未执行付费请求。
- 未读取、stat 内容、diff、复制、输出、迁移或修改真实 `.env`、个人状态、缓存、来源
  名单、profile、模型、参考音频、Voice Pack registry、`server/runtime/`、受保护
  `demon_slayer.json`/`focus_timer.json` 或 `vendor/`。相关 Git 状态、diff 和扫描均使用
  本批显式路径 allowlist。
- 混合工作区中的 PK-020、PK-030、PK-100、PK-120、PK-150、PK-213 及其他任务修改未
  纳入本批结论。未执行 Git 暂存、提交、推送、发布、分支切换或工作区清理。

### 本轮八项文档门禁

- [x] TASK_RECORD — 已追加远端实物、双构建、信任边界、回归、限制和整改复验记录。
- [x] TASKS_BOARD — 未修改；PK-011/PK-900 最终关闭交 PK-000。
- [x] PUBLIC_README — 私有协作者、未来公开用户、匿名 404 与旧 Release 兼容说明一致。
- [x] MODULE_CATALOG — 19 个 URL/tag/size/package/manifest SHA 与远端和重建结果一致。
- [x] ARCHITECTURE_DOCS — 集中分发仓库、单批 Release、匿名 Core 与安全包契约一致。
- [x] LOCAL_README — 未修改或输出本机秘密、个人数据、模型和真实服务路径。
- [x] AGENT_RULES — 遵守临时目录、保护数据、混合工作区和 Git 写操作边界。
- [x] VALIDATION — 远端只读验证、19 包实物/重建/安全扫描、定向与完整 pytest、ruff、
  Python/JavaScript、Catalog、文档与精确 diff 门禁均已完成。

## PK-010 + PK-020 + PK-100 + PK-140 + PK-210 + PK-211 累计独立验收（2026-08-08）

### 结论

- **不通过**。PK-900 保持“进行中”；六项上游任务保持“待集成”，由 PK-000 决定后续状态。
- 阻断一：生产应用重复装配并不安全。进程内先装配一次 `api` 后再次 reload/import，
  `InstalledModuleHost.__init__()` 会再次注册 `gpt_sovits_provider` sidecar，
  `SidecarAdapterRegistry.register()` 抛出 `ValueError: sidecar adapter is already registered`。
  完整默认套件因此有 4 个 setup error；定向组合也稳定复现 1 个失败。该问题归属
  PK-211 与 PK-010 共享装配接缝。最小整改应保证相同进程内重复应用装配复用唯一适配器、
  不静默替换活动适配器，并同时审计 QQ sidecar 的同类重复注册；增加连续两次装配且两组
  路由仍各唯一的永久回归。
- 阻断二：真实 tracked Git tree 构造的 Windows 过滤副本无法运行测试清单。
  `server/tests/test_gpt_sovits_engine_selection_assembly.py` 与
  `server/tests/test_restart_supervisor.py` 当前未被 Git 跟踪，但受跟踪 inventory 已引用二者。
  过滤副本的 inventory、collect-only、quality/copy pytest 均在 collection 前失败，不能作为
  可发布候选。归属精确发布集合/PK-020 Windows filtered-copy 接缝；必须由 PK-000 在逐文件、
  逐 hunk 审核后把所需源码、测试及清单纳入同一提交，再从该提交重建过滤副本重跑。
- 阻断三：当前变更未形成可引用提交，因此没有覆盖本轮实现的 Python 3.10/3.11/3.12/3.13
  x64、Node 22、Windows PowerShell 5.1 与 PowerShell 7.4+ 同提交远端矩阵。现有成功 run
  `30750911557` 对应旧 HEAD `ceb1660d4b86816a3a9b159a06cb76285d1f9b42`，不能证明
  当前未提交增量。本机仅有 Python 3.12.7、Node 24.18.0 和 Windows PowerShell 5.1，未冒充
  目标矩阵。
- 发布门禁：只读 GitHub API 核对时，旧 `modules-2026.08.02` 的三项旧资产仍存在且摘要未变；
  新 tag `modules-2026.08.08` 返回 404。三份新 ZIP 是确定的本地候选，但 Catalog 指向的远端
  资产在发布前不可用。该项由 PK-000 在代码验收和精确提交完成后发布并复核，不由 PK-900
  执行 Git 或 Release 写操作。

### 已通过的契约复核

- `api.app` 由唯一 `InstalledModuleHost` 固定创建本机 GPT-SoVITS 选择服务，registry 固定为
  `server/data/gpt_sovits_engine.local.json`，并各挂载一组 GPT status/select 与 restart 路由。
  GET 的真实 loopback 请求允许缺 Origin；带 Origin 时必须精确匹配。POST 在 picker、registry、
  supervisor 或请求体处理前执行真实 peer、精确 Origin、无 query 与严格 body/确认词校验。
  fake picker 的取消路径零写入，响应不返回目录；无已选引擎时 Core 仍可构造。
- ZIP 上传的版本化入口支持从 manifest 自动确定模块 ID、可选 `expected_module_id`，legacy
  `/{module_id}/install-upload` 仍委托同一路径；请求长度和流式累计均限制为 64 MiB，校验
  SHA-256，失败清理临时包且不进入 runtime/registry。相关临时目录生命周期回归通过。
- QQ 配置只接受 AppID/Secret 两个冻结字段；响应不含 Secret，AppID 只返回掩码。空 Secret
  保留旧值，唯一临时文件配合 flush/fsync/原子替换，替换失败保留旧字节并清理临时文件。
  独立测试只使用临时 `.env` 和 fake 请求，未读取真实配置。
- ASR/GPT 目录选择均使用 fake picker、临时目录和合成 reparse/错误结构；覆盖取消、并发、
  保存失败保旧与路径脱敏，未扫描或读取真实模型、参考音频或外部 GPT-SoVITS 源码。
- 官方 Catalog 三条候选分别为：`qq_bridge@0.1.6`（109140，ZIP
  `9b9fde6ecf4585c437ddb8de6c29b947d028fc160c3390695210cf919bc4c967`，manifest
  `bfebe6f01d3f889e69e27547cf9b853c55fcb583e83456f5b1d48a1789f36215`）；
  `voice@1.0.3`（67448，ZIP
  `7c5bd049b74def7dadeebb91b0a48f1fc8a851528af38b7bb0e6c5b334a27702`，manifest
  `3872e12a006b5f9c3d5e136567ae1e652e1617ab1aebb558cbb07d35d7b9c82f`）；
  `gpt_sovits_engine_provider@1.0.1`（93850，ZIP
  `27a39f7ec930562a152c949d059260ae9ecb428589856f618c6b8d67a36bc5f6`，manifest
  `5a50239a19b552e798079addaf507db5bd878ccfc1a81369cc9cb356b3c45a79`）。
  三个 builder 在两个独立系统临时目录中的输出逐字节一致，且 version/tag/asset/size/hash 与
  Catalog 一致。
- README 与控制台定向回归覆盖卡片布局、移动端、二次确认、显式点击才写入以及普通加载零业务
  网络；30 个 dashboard/QQ/voice JavaScript 文件通过 `node --check`，dashboard Node 测试通过。

### 实际命令与结果

- 定向累计 pytest（12 个文件）：`79 passed, 1 skipped, 1 failed`；失败为上述 reload 后
  `gpt_sovits_provider` 重复注册。
- 默认 `pytest tests -q`：`403 passed, 1 skipped, 4 errors in 381.69s`；4 个错误均在
  `test_local_access_boundary.py` 的真实 `api` reload fixture，根因同上。
- `pytest -q tests/test_windows_ci_copy.py tests/test_windows_install.py`：`33 passed in 298.70s`。
- `windows_ci_copy.py --source . --target <系统临时目录>`：`allowed=607 protected_rejected=7
  ignored=8 copied=607`。副本 inventory 报 stale 两文件；collect-only 与 pytest 在 conftest
  因缺文件失败；副本 ruff 通过。
- 根目录 inventory：90 个测试文件、76 default、14 isolated、282 个 default `check_*`、
  `unsatisfied=0`、12/12 legacy entrypoint 无必需参数、125 个 async check。
- QQ Node：`83 passed, 0 failed`；dashboard Node：`1 passed`；30 个 JS `node --check` 全通过。
- 根测试/清单 ruff：通过；相关 Python `py_compile`：通过；7 个 PowerShell 文件 PS5.1 AST：
  通过；Catalog 校验：通过；文档门禁：`26 gated task(s)` 通过。
- 三包独立双构建：三组均 `byte_equal=true`、`catalog_match=true`。
- 精确相关路径 `git diff --check`：退出 0；仅有既有 LF→CRLF 提示。

### 数据隔离、风险与排除

- 使用工作区外既有隔离 Python 3.12.7，只执行、不安装依赖；没有借用或修改项目
  `.venv`、`.venv-asr`、`node_modules`。所有包、registry、picker、模型树、过滤副本和写入
  夹具均位于系统临时目录；HTTP 使用 ASGITransport/fake，未启动监听服务。
- 未读取、stat 内容、diff、复制、输出、迁移或修改真实 `.env`、个人状态、缓存、来源名单、
  profile、模型、参考音频、Voice Pack registry、QQ runtime、`server/runtime/`、受保护系统
  状态或 `vendor/`；未启动 QQ、Collector、LLM、ASR、TTS、GPT-SoVITS，未执行真实业务请求。
- 工作区中的 PK-030、PK-120、PK-150、PK-213 及其他无关改动均排除。未执行暂存、提交、
  推送、发布、分支切换或清理。

### 本轮八项文档门禁

- [x] TASK_RECORD — 本节已记录范围、契约、命令、失败证据、责任归属和最小整改。
- [x] TASKS_BOARD — 未修改；六项保持“待集成”，PK-900 保持“进行中”。
- [x] PUBLIC_README — 安装、控制台、确认词、目录选择和本机访问说明已核对。
- [x] MODULE_CATALOG — 三条候选元数据与独立双构建一致；远端新 Release 缺失已明确列为门禁。
- [x] ARCHITECTURE_DOCS — 模块宿主、sidecar、Windows 安装和本地 Provider 所有权与实现已核对。
- [x] LOCAL_README — 未输出或探测本机外部引擎、模型、秘密和个人数据路径。
- [x] AGENT_RULES — 遵守临时目录、保护数据、混合工作区和 Git 只读边界。
- [x] VALIDATION — 已运行定向、默认、Windows copy/install、Node、编译、ruff、Catalog、文档和
  diff 门禁；失败项及尚缺同提交远端矩阵未被隐藏或降级为通过。

## 同批次 sidecar 幂等整改后独立复验（2026-08-08）

### 本地结论与状态

- **本地候选通过，可进入 PK-000 精确提交准备；本批最终仍未通过。** 上轮生产应用重复装配
  阻断已经消除：原失败顺序和完整默认套件均不再出现 `sidecar adapter is already registered`，
  GPT-SoVITS 与 QQ 两类官方 adapter 在重复、reload 和并发装配中均保持唯一实例。
- PK-900 继续“进行中”；PK-010、PK-020、PK-100、PK-140、PK-210、PK-211 继续“待集成”。
  本地通过不替代 tracked filtered-copy、新 Release 实物和同提交 Windows 目标矩阵。
- 可以交 PK-000 逐文件、逐 hunk 精确纳入候选提交，但在提交后过滤副本与远端矩阵成功前
  **不可直接发布或关闭**。PK-900 未修改产品、`TASKS.md` 或六项上游状态。

### sidecar 整改独立证据

- `ModuleManager.resolve_sidecar_adapter(name)` 是只读查询；底层严格 register 冲突规则未放宽，
  对已经登记的同一对象再次 register 仍抛稳定冲突。
- `InstalledModuleHost` 只复用固定名称下 `type(existing) is OfficialAdapterClass` 的对象，未使用
  `isinstance`。独立构造 GPT 与 QQ 官方类的子类对象预占名称，两者均在 host 构造时固定失败，
  原对象没有被覆盖；既有 fake/不同实现冲突回归也通过。
- 重放原顺序
  `test_module_host_assembly.py -> test_dashboard_shell.py -> test_local_access_boundary.py`：
  `13 passed`。这直接覆盖上轮 4 个 setup error 的触发顺序。
- 独立在同一 manager 上连续 import/reload `api` 三次：GPT status/select 与 restart status/write
  四条路径各恰有一条，manager 中 GPT/QQ 均为精确官方类。
- 独立用 12 个 worker 并发构造 40 个 host：无异常，40 个 host 只共享一个 GPT adapter 和
  一个 QQ adapter，且分别与 manager 解析结果为同一对象。

### 累计回归与质量门禁

- 完整默认入口：`python -m pytest tests -q` 得到
  `408 passed, 1 skipped, 53 warnings in 456.93s`；零 fail/error。唯一 skip 为当前 Windows
  主机无法创建 symlink 的 restart supervisor 条件夹具，未把失败伪装为 skip。
- 上轮 12 文件累计定向入口重新运行：`81 passed, 1 skipped`；唯一 skip 同上。覆盖真实
  `api.app` 路由唯一、本机/Origin 前置拒绝、restart、ZIP upload 自动/预期 ID 与 legacy、
  64 MiB/摘要/清理、QQ Secret/AppID/原子保存、ASR/GPT fake picker、错误结构/reparse、
  Catalog、dashboard/README 和安装包。
- QQ bridge Node：`83 passed, 0 failed`；dashboard Node：`1 passed`；实际枚举 dashboard、QQ
  src/tests、voice 与 GPT provider dashboard 的 29 个 JavaScript 文件全部 `node --check`。
- 根测试与 inventory ruff：通过；相关 11 个 Python 文件 `py_compile`：通过；官方 Catalog
  校验：通过。
- 独立 inventory：90 个测试文件、76 default、14 isolated、283 个 default `check_*`、
  `unsatisfied=0`、12/12 legacy entrypoint 无必需参数、125 个 async check。7 个 PowerShell
  文件的 Windows PowerShell 5.1 AST 通过；文档门禁通过 26 项；本批显式 allowlist 的
  `git diff --check` 退出 0，仅有既有 LF→CRLF 提示。
- QQ、voice、GPT provider 在两组独立系统临时目录再次双构建，三组字节均一致，并逐项匹配
  Catalog：`qq_bridge@0.1.6` 为 109140 bytes / package
  `9b9fde6ecf4585c437ddb8de6c29b947d028fc160c3390695210cf919bc4c967` / manifest
  `bfebe6f01d3f889e69e27547cf9b853c55fcb583e83456f5b1d48a1789f36215`；
  `voice@1.0.3` 为 67448 / `7c5bd049b74def7dadeebb91b0a48f1fc8a851528af38b7bb0e6c5b334a27702` /
  `3872e12a006b5f9c3d5e136567ae1e652e1617ab1aebb558cbb07d35d7b9c82f`；
  `gpt_sovits_engine_provider@1.0.1` 为 93850 /
  `27a39f7ec930562a152c949d059260ae9ecb428589856f618c6b8d67a36bc5f6` /
  `5a50239a19b552e798079addaf507db5bd878ccfc1a81369cc9cb356b3c45a79`。
- 过程记录：首个独立摘要脚本误把 Catalog 主键写为 `id`，在任何构建/比较前以 `KeyError`
  停止；改为实际冻结字段 `module_id` 后完整双构建和逐字段断言通过。该次为验收夹具错误，
  没有修改产品或状态。

### 仍待 PK-000 完成的发布门禁

- `git ls-files --error-unmatch` 再次确认
  `server/tests/test_gpt_sovits_engine_selection_assembly.py` 与
  `server/tests/test_restart_supervisor.py` 尚未被跟踪，而受跟踪 inventory 已引用它们。
  当前完整工作树可以验证且已全绿，但从当前 HEAD 构造的真实 tracked filtered-copy 必然缺少
  两文件。本轮按 PK-000 指示不把它误判为本次产品整改失败，也不重复冒充过滤副本通过；
  精确提交必须包含两文件及其必要实现，然后从新 tracked tree 重跑 inventory、collect-only、
  完整 pytest、quality、copy policy 和 ruff。
- 当前 HEAD 仍为 `ceb1660d4b86816a3a9b159a06cb76285d1f9b42`，而本轮产品与测试增量
  尚在工作树。最近 Windows workflow 成功 runs 的 head 分别为 `8554bfb...`、`ceb1660...`
  等旧提交，均不能标识当前内容；仍缺 Python 3.10/3.11/3.12/3.13 x64、Node 22、Windows
  PowerShell 5.1 与 PowerShell 7.4+ 的新同提交证据。
- 只读 GitHub API 对 `songshu-yu/Project-Kei-Modules` 的 `modules-2026.08.08` 仍返回 404。
  三包本地候选摘要正确，但远端资产尚不存在；须由 PK-000 在精确提交和矩阵通过后发布、
  再核对远端 asset size/digest 与 Catalog。PK-900 未触发 Release 或 workflow。

### 数据隔离、工作区排除与文档门禁

- 使用工作区外既有隔离 Python 3.12.7 和本机 Node 24，只执行、不安装；未借用或修改项目
  `.venv`、`.venv-asr`、`node_modules`。所有构建、manager、registry、runtime、picker、
  模型树与并发夹具均位于系统临时目录；未启动真实监听、sidecar、picker 或业务网络。
- 未读取、stat 内容、diff、复制、输出、迁移或修改真实 `.env`、个人状态、缓存、来源名单、
  profile、模型、参考音频、Voice Pack registry、QQ runtime、`server/runtime/`、受保护系统
  状态或 `vendor/`。PK-030、PK-120、PK-150、PK-213 等混合改动继续排除。
- [x] TASK_RECORD — 本节记录整改复现、逆向、完整回归、隔离和剩余门禁。
- [x] TASKS_BOARD — 未修改；PK-900“进行中”，六项上游“待集成”。
- [x] PUBLIC_README — 用户操作、确认、目录选择和零网络普通加载契约无回归。
- [x] MODULE_CATALOG — 三包双构建与当前条目一致；远端 404 明确保留为发布门禁。
- [x] ARCHITECTURE_DOCS — 严格 adapter registry 与唯一生产 composition 边界未放宽。
- [x] LOCAL_README — 未探测或输出本机秘密、模型、外部引擎或个人数据路径。
- [x] AGENT_RULES — 遵守临时目录、保护数据、混合工作区与 Git 只读边界。
- [x] VALIDATION — 默认/定向/逆向、Node、编译、ruff、Catalog、双构建、文档和精确 diff
  均重跑；tracked copy、新 Release 与远端矩阵如实保持未完成。

## 精确待提交 Git index 树只读门禁（2026-08-08）

### 结论

- **精确待提交树本地通过，可由 PK-000 提交并触发远端矩阵；本批仍不能最终关闭。**
  本节只验证当前 index 中的 71 个精确候选文件，没有修改 index、产品、`TASKS.md` 或任务
  状态。PK-900 继续“进行中”，六项上游继续“待集成”。
- `scripts/windows_ci_copy.py` 的公开 CLI 固定枚举 `HEAD`，尚未提交时直接调用会误验旧树。
  本轮因此使用同一受版本控制模块的 `GitTreeEntry` 与 `build_plan()`：先通过
  `git ls-files --stage -z` 只读取 index 的纯相对路径、mode 与 blob ID；所有路径先经过原
  allowlist/保护前缀/symlink mode 策略，只有 `plan.allowed` 项才通过 `git cat-file blob <id>`
  写入新建系统临时目录。没有从工作区 protected path 构造、stat、open 或复制内容。

### index filtered-copy 实际证据

- 新副本：系统临时目录 `pk900-index-filtered-2c913b5e09f44b719286112beeb3b531`；策略结果
  `allowed=620 protected_rejected=7 ignored=8`。副本明确包含
  `server/tests/test_gpt_sovits_engine_selection_assembly.py` 与
  `server/tests/test_restart_supervisor.py`。
- 副本 inventory `--json` 通过：90 个测试文件、76 default、14 isolated、283 个 default
  `check_*`、`unsatisfied=0`、12/12 legacy entrypoint 无必需参数、125 个 async check；无
  missing/stale。
- 副本 `python -m pytest tests --collect-only -q`：`409 tests collected`，退出 0，无
  collection error、unknown fixture 或 call-phase TypeError。
- 副本 `test_pytest_quality_gate.py -q`：`13 passed`；
  `test_windows_ci_copy.py -q`：`7 passed, 1 skipped`，唯一 skip 明确是 filtered-copy 不携带
  Git metadata，其他 policy 断言实际执行；副本 ruff `tests ..\\scripts\\check_python_test_inventory.py`
  通过。
- 没有在副本再次耗时运行完整默认 suite。引用紧邻本门禁、同一候选内容的独立结果
  `408 passed, 1 skipped, 0 failed/error`；在追加本报告前又以纯路径核对确认工作树对 71 个
  staged 候选没有 unstaged 内容漂移，唯一 unstaged tracked 项仍是两份明确排除的个人状态文件。
  因而该完整结果与当前 index 候选内容一致，不引用更早实现方数字。

### 暂存清单与剩余外部门禁

- 只读检查得到 `STAGED_COUNT=71`、`FORBIDDEN_STAGED=0`、`REQUIRED_TESTS=2`、
  `UNSTAGED_CANDIDATE_DRIFT=0`；路径规则排除 `.env`/`README.local.md`、`server/data`、
  `server/systems/data`、`server/runtime`、`vendor`、venv、node_modules、cache、profile、model、
  audio 与 Voice Pack 用户资产。`git diff --cached --check` 退出 0。
- 本报告按授权仅追加在工作树，未执行 `git add`，因此上述 71 项 index 结论保持为验证时快照；
  PK-000 可在提交前决定是否把本报告作为单独复核记录精确纳入，不得顺带纳入保护路径。
- 当前仍未产生新提交；`modules-2026.08.08` Release 尚未发布；覆盖该新提交的 Python
  3.10/3.11/3.12/3.13 x64、Node 22、Windows PowerShell 5.1/PowerShell 7.4+ 矩阵尚未运行。
  PK-000 必须在提交后从真实 tracked tree 再调用公开 `create_filtered_copy`/workflow，并取得
  全部远端 jobs 成功，再发布并核验三份资产；这些是最终关闭门禁，不由本轮提前判定通过。

### 数据隔离与文档门禁

- 只读取 index 的路径/mode/blob ID 和策略允许的 Git blob；没有读取工作区真实 `.env`、
  个人状态、缓存、来源名单、profile、模型、音频、Voice Pack registry、QQ runtime、
  `server/runtime/` 或 `vendor/` 内容。所有副本与测试写入位于系统临时目录，未启动真实服务、
  sidecar、picker、QQ、LLM、ASR、TTS 或业务网络。
- [x] TASK_RECORD — 已记录 index 构造方法、命令结果、完整 suite 引用依据与剩余门禁。
- [x] TASKS_BOARD — 未修改；状态保持不变。
- [x] PUBLIC_README — 候选 README 已进入过滤副本，相关默认/定向回归无回归。
- [x] MODULE_CATALOG — 候选 Catalog 已进入过滤副本，前轮精确双构建结果继续适用。
- [x] ARCHITECTURE_DOCS — Windows copy 与模块/voice 架构候选均经过同一 index policy。
- [x] LOCAL_README — 未纳入 index、副本或输出。
- [x] AGENT_RULES — 遵守保护数据、系统临时目录、混合工作区和 Git 只读边界。
- [x] VALIDATION — index inventory/collect/quality/copy/ruff 与 staged name/diff 门禁均实际通过；
  完整 suite 的同内容依据和未执行的远端门禁均已明确区分。

## PK-000 最终远端矩阵、Release 回读与关闭确认（2026-08-08）

### 最终结论

- **通过。** PK-000 已独立核对提交、远端 Windows 矩阵和实际 Release 附件，前述未完成门禁均已关闭。
- 主批 `PK-010 + PK-020 + PK-100 + PK-140 + PK-210 + PK-211` 通过；同一矩阵实际覆盖并关闭
  `PK-030` 的测试发现/过滤副本门禁，以及本轮为 Windows 原子写入稳定性修复并重新发布的
  `PK-115`、`PK-170`。上述九项与本轮 PK-900 统一登记为“已完成”。
- Draft PR #12 保持 Draft；本轮没有合并 PR，也没有清理混合工作区。

### 同提交远端证据

- 最终代码提交：`69f3ff748ca6c1a0002200e76901338a4cafc0ea`；GitHub Actions run
  `31265955157`（`windows-install`）结论为 `success`。
- 四个真实 Windows clean-install jobs 全部成功：Python 3.10、3.11、3.12、3.13。
  workflow 同时执行 Node 22、Windows PowerShell 5.1、PowerShell 7.4+、过滤副本、完整默认
  Python suite、Ruff、Node 测试/语法和文档门禁，因此不再以本机解释器冒充目标矩阵。
- 历史失败保留：首轮暴露 ASR 对 runner TEMP 祖先 reparse 的误判，以及 fitness/intel_sources
  的 Windows `os.replace` 短暂占用；第二轮关闭原子写入问题后，暴露 Windows 8.3 短路径与
  canonical 长路径别名差异。第三轮在固定入口双拼写检查和 `Path.samefile()` 身份断言后全绿。

### 官方模块 Release 与回读校验

- 已在 `songshu-yu/Project-Kei-Modules` 创建并发布 `modules-2026.08.08`：
  `https://github.com/songshu-yu/Project-Kei-Modules/releases/tag/modules-2026.08.08`。
- 发布前从当前源码在新系统临时目录确定性重建，发布后又通过私有 GitHub API 下载到另一新
  临时目录并重新计算 SHA-256；五个附件数量、大小与摘要全部匹配当前官方 Catalog：
  - `fitness-1.0.3.zip`：34369 bytes，
    `603dd45be66ab1e88f4d80ccaba99529abf4c9dbcf4520b9e781dff4895daad5`；
  - `intel-sources-1.1.6.zip`：41312 bytes，
    `db96595b58347959ca3506453700373362c6e237a5da6c5edda09eb649f28bda`；
  - `qq_bridge-0.1.6.zip`：109140 bytes，
    `9b9fde6ecf4585c437ddb8de6c29b947d028fc160c3390695210cf919bc4c967`；
  - `voice-1.0.3.zip`：67448 bytes，
    `7c5bd049b74def7dadeebb91b0a48f1fc8a851528af38b7bb0e6c5b334a27702`；
  - `gpt_sovits_engine_provider-1.0.1.zip`：93850 bytes，
    `27a39f7ec930562a152c949d059260ae9ecb428589856f618c6b8d67a36bc5f6`。

### 隔离与发布边界

- 精确提交只包含已复核的产品、测试、公开文档、Catalog 与任务记录；最终 ASR 修复提交仅含
  `asr_model_directory.py`、对应永久回归和 PK-210 记录。
- 未暂存、提交、上传、读取内容或清理两份真实个人状态、`server/runtime/`、`vendor/`、`.env`、
  QQ/LLM 凭据、来源名单、缓存、profile、模型、参考音频、Voice Pack 用户注册表或其他混合任务修改。
- Release ZIP 只含公开模块程序和 manifest；不含模型权重、秘密、个人状态、缓存、`node_modules`
  或外部引擎源码。发布后的回读摘要是最终实物证据。

### 本轮完成文档门禁

- [x] TASK_RECORD — 本节记录同提交矩阵、历史失败、Release 实物和最终状态。
- [x] TASKS_BOARD — 九项上游与 PK-900 已同步为“已完成”。
- [x] PUBLIC_README — 当前安装、离线 ZIP、受控重启、QQ/ASR/GPT 目录选择说明已进入通过矩阵的提交。
- [x] MODULE_CATALOG — 五个新附件已按 Catalog 文件名、大小和 SHA-256 回读验证。
- [x] ARCHITECTURE_DOCS — 模块、Windows 安装、语音与 sidecar 公共契约未扩大。
- [x] LOCAL_README — 未读取、输出或提交本机私有配置。
- [x] AGENT_RULES — 精确暂存/发布并保留混合工作区，未执行清理或真实业务副作用。
- [x] VALIDATION — 本地定向回归、文档/diff 门禁、四版本远端矩阵和 Release 回读均通过。

## PK-020 + PK-140 + PK-210 QQ 语音附件累计独立验收（2026-08-10）

### 结论与状态

- **不通过。** 本轮本地候选的核心语音合成、固定 Silk 编码、文字优先、fake QQ 分片上传、
  Windows voice-media 锁和大部分失败关闭回归均通过，但仍有一个可复现的 PK-140 运行时阻断、
  一个真实部署功能不可达阻断、官方 Catalog/公开文档不一致，以及尚未形成精确 tracked commit
  的发布门禁。不能用 fake 成功链路或旧提交的远端矩阵替代。
- PK-900 保持“进行中”；PK-020、PK-140、PK-210 均保持“待集成”。本轮只追加本报告，未修改
  产品、`TASKS.md`、三项上游状态或其他历史验收记录。

### 阻断证据、责任与最小整改

1. **PK-140 P1：合成响应体不受 timeout/shutdown/流式 8 MiB 上限保护。**
   `createVoiceReplyController()` 的 `boundedFetch()` 在 `fetch()` 返回响应头后立即清理 timer 并从
   `activeControllers` 移除 controller；`synthesize()` 随后才用 `response.arrayBuffer()` 读取完整
   body。因此慢或不结束的 body 已脱离 45 秒 deadline，`stop()` 也无法 abort；8 MiB 只信任
   头部并在完整分配后比较实际长度，没有边读边限额。独立 fake `ReadableStream` 只返回合法
   头和 10 字节前缀、永不结束：等待超过自定义 30 ms 后调用 `stop()`，120 ms 再观察仍得到
   `HUNG_AFTER_TIMEOUT_AND_STOP`，`synthCalls=1`、`qqCalls=0`、`inFlight=1`。这直接违反本批
   “超时/超限/shutdown fail closed”契约。最小整改仅在 PK-140：让同一 AbortController/deadline
   覆盖响应体消费；用 reader 累计最多 8 MiB，超过立即 abort；readiness JSON 也必须在同一
   deadline 内有界读取；新增 headers 已到达但 body 卡住/超量及 stop 的永久回归。
2. **PK-140/共享装配 P1：真实部署没有把 capability 从 `unknown` 变成 `available` 的受控路径。**
   生产 `module_composition.py` 唯一设置是
   `app.state.qq_media_upload_capability_provider = lambda: "unknown"`；限定源码检索未找到生产
   声明或快照来源，只有测试替身能改成 `available`。facade 又正确拒绝 capability 非 available
   的开关，所以当前真实 UI 永远不能开启 QQ 语音。裁决分两层：默认 unknown、不得由
   AppID/Secret 推断、不得真实发消息探测，作为安全失败关闭是正确的；但 PK-140 若以“用户可在
   真实部署中显式启用普通聊天语音”为完成标准，则功能目前不可达，属于产品阻断，不能只凭 fake
   链路关闭。最小整改按总控冻结归 PK-140/共享装配：提供非秘密、显式、可审计且默认 unknown
   的 capability 声明/快照来源；控制台明确说明这是用户对 Bot 权限的声明而非探测结果；仍禁止
   从凭据推断或发送测试消息。
3. **发布目录接缝阻断：候选版本未进入官方 Catalog。** 两次系统临时目录构建字节一致：
   `voice-1.0.5.zip` 为 104572 bytes / SHA-256
   `bb4d80cf5f036608e771f9230b406ec70164e389b5a221d3c6d1d3435faf80ac`；
   `qq_bridge-0.1.8.zip` 为 124163 bytes /
   `c01b03cfc0a479eac4383b75dfaddc5d77117b088c4b0bd40c6b6b1e03249f7e`。
   但 `server/core/modules/official-catalog.json` 实际仍登记 `voice@1.0.3` /
   `voice-1.0.3.zip` 和 `qq_bridge@0.1.7` / `qq_bridge-0.1.7.zip`；独立逐字段断言固定失败。
   现有 official-catalog 测试只证明旧目录内部自洽，不能证明本轮包可安装。最小范围：PK-140、
   PK-210 保持已冻结 fragment/摘要，由 Catalog 所有者在精确发布候选中合并两条新 entry，随后
   双构建、安装生命周期、远端资产回读共同复验。
4. **公开文档不一致。** `README.md` 仍写“当前 QQ Node sidecar 尚未实现完整媒体上传”，与实际
   `voice_reply.mjs` 完整 fake 链相反；`docs/architecture/qq-bridge.md` 末尾仍写 QQ 尚未接入
   PK-010 installable sidecar，并未记录本批 readiness/合成/COS 上传/状态契约；voice 架构仍有
   “PK-020/composition 需要完成”的未来时表述。最小范围是 PK-140 更新 QQ 架构和 README 当前
   能力边界，PK-210/PK-020 把 voice-media 锁与生产 encoder 注入改成已实现，同时如实保留
   capability 默认 unknown 和真实启用门禁。
5. **精确发布与远端矩阵尚未成立。** 当前 HEAD 为
   `aa40b14af0898d2d1fe6235241cd79cf751ddba1`，虽然 GitHub Actions run `31327206715`
   对该提交成功，但本轮 lock、encoder、Node controller 和测试仍有大量工作树修改及未跟踪文件，
   不能继承该 run。用当前公开 `windows_ci_copy.py` 从 tracked HEAD 构造新系统临时副本时直接
   `COPY_EXIT=2 / reviewed CI surface is missing one or more required files`，证明尚未形成可复验的
   tracked 候选。整改完成并由 PK-000 精确提交后，必须从同一 commit 重新构造 filtered-copy，
   再取得 Python 3.10/3.11/3.12/3.13 x64、Node 22、Windows PowerShell 5.1 与 PowerShell
   7.4+ 全部成功；本机 Python 3.12/Node 24/PS5.1 不可替代。

### 已通过的独立契约与实际命令结果

- 隔离 Python 3.12.7 定向执行 voice module/installable/Silk、module host、installable lifecycle、
  feature/official Catalog、qq-control、QQ configuration/installable package：`75 passed`。确认
  synthesize 只消费既有文字，一次 TTS、统一 24 kHz mono s16le PCM 后一次编码；不调用
  ASR/conversation/LLM/history；固定 `qq_c2c_voice_v1`、`audio/silk`、final、1..60000 ms，
  60 秒/8 MiB 上限和 idempotency/cancel/close 基础回归通过。
- `test_windows_install.py + test_windows_ci_copy.py`：`35 passed in 332.56s`。四个 CPython
  3.10–3.13 win_amd64 wheel SHA 与 `SilkPythonUtteranceEncoder.WINDOWS_X64_WHEEL_SHA256`
  完全一致；`voice/full` 才加入独立 `voice-media-win.lock.txt`，使用 `--require-hashes` 和
  `--only-binary=:all:`；core/qq 不要求可选 codec；doctor 只查 version/import/callable，零编码。
- QQ bridge 全部 Node：`97 passed, 0 failed`。另定向逆向 7 项通过：默认关闭零 readiness/TTS/
  上传/写状态；成功链一次 synthesize，严格 upload_prepare→HTTPS `*.myqcloud.com:443` PUT
  （redirect error）→part_finish→files→一次 `msg_type=7`；恶意头/非 Silk/危险 URL、并发与
  shutdown 基础夹具失败关闭。普通 conversation 先发文字，语音失败不重发；菜单、业务、每日
  情报、生命维持和专注鼓励不调用 voice controller。
- 两份候选 ZIP 双构建字节一致，包名清单无 `.env`、data/runtime/cache、model、node_modules、
  vendor，内容扫描无用户绝对路径。由于官方 Catalog 仍旧，本项只证明候选包确定性，不表示可发布。
- Python compile（pycache 指向系统临时目录）退出 0；相关 Ruff 通过；QQ src/tests 15 个 MJS
  与 dashboard/两模块入口 16 个 JS 全部 `node --check`；dashboard Node `1 passed`；8 个实际
  PowerShell 脚本的 Windows PowerShell 5.1 AST 为 0 error；文档门禁
  `28 gated task(s)`；`git diff --check` 退出 0，仅有既有 LF→CRLF 提示。
- 过程记录：一次 Node 定向命令从 `server` cwd 使用了错误相对路径，随后在 `server/qq_bridge`
  正确重跑 7/7；一次 AST 清单误写两个不存在的脚本名，随后枚举实际 8 个 `.ps1` 重跑 0 error；
  一次复合 compile/ruff/node-check 命令仅最终 PowerShell 三参数 `Math.Max` 包装出错，三个实际
  检查均已输出通过并分别用正确命令再次重跑。上述均为验收夹具/命令错误，没有修改产品。

### 数据隔离、工作区排除与八项文档门禁

- 只使用工作区外既有隔离 Python、系统临时构建/状态/filtered-copy、fake HTTP/QQ/stream；未
  借用或修改项目 `.venv`、`.venv-asr`、`node_modules`，未安装依赖，未启动监听、BAT、QQ、
  Gateway、LLM、ASR、TTS、encoder、Collector、模型或 Voice Pack，未发送真实消息或业务请求。
  唯一外部只读查询为 GitHub Actions run 元数据，没有触发 workflow 或 Release。
- 未读取、stat 内容、diff、复制、输出、迁移或修改真实 `.env`、QQ data/runtime、个人状态、
  缓存、来源名单、profile、模型、参考音频、Voice Pack registry、`server/runtime/`、`vendor/`、
  `demon_slayer.json` 或 `focus_timer.json`。混合工作区其他任务继续排除；未暂存、提交、推送、
  发布、切分支或清理。
- [x] TASK_RECORD — 本节记录范围、实际命令、通过项、阻断、归属、隔离和剩余门禁。
- [x] TASKS_BOARD — 未修改；PK-900“进行中”，三项上游“待集成”。
- [ ] PUBLIC_README — 当前 QQ 媒体上传状态陈述与实现冲突，需 PK-140 收口。
- [ ] MODULE_CATALOG — voice 1.0.5 与 qq_bridge 0.1.8 尚未进入官方 Catalog。
- [ ] ARCHITECTURE_DOCS — QQ installable/媒体链及 voice-media 完成时态与实现不一致。
- [x] LOCAL_README — 只读取项目要求的说明，未输出其中本机私有路径或配置。
- [x] AGENT_RULES — 遵守系统临时目录、保护数据、混合工作区和 Git 只读边界。
- [ ] VALIDATION — 本地回归已充分重放，但响应体 P1、生产 capability、tracked filtered-copy 与
  同提交 Windows 目标矩阵尚未关闭。

## PK-020 + PK-140 + PK-210 整改后仅源码功能复验（2026-08-10）

### 本轮结论与边界

- **源码功能复验不通过。** PK-140 已修复 synthesize 音频 body 的流式 deadline/8 MiB 限额，
  非秘密 capability 声明及同根生产组合也已可达；但独立逆向仍复现 readiness JSON body 脱离
  deadline，以及跨 `server_root` 复用旧 QQ adapter 路径两个阻断。本轮没有构建 ZIP，也没有
  检查或修改 Catalog、README、Release 元数据、远端矩阵或发布资产；这些继续作为后续门禁，
  不计入本节源码功能判断。
- PK-900 保持“进行中”；PK-020、PK-140、PK-210 保持“待集成”。只追加本报告，没有修改
  产品、`TASKS.md` 或上游任务状态。

### 仍未通过的两项源码阻断

1. **PK-140：readiness 响应体仍不受同一 deadline/shutdown 控制。**
   `readiness()` 仍先调用 `boundedFetch()`；该 helper 只把 `fetchImpl()` 包在 `withDeadline()`
   中，响应头返回后即清 timer/remove active。随后 `safeJsonResponse()` 在 deadline 外执行
   `response.text()`。独立 fake configuration `ReadableStream` 只写入半段 JSON 后永不结束；
   `timeoutMs=25`，等待 60 ms 后调用 `stop()`，再等 120 ms 仍得到
   `HUNG_READINESS_AFTER_TIMEOUT_AND_STOP`，且 `cancelled=0`、synthesize/QQ 调用均为 0。
   这违反本轮“fetch、响应头与整个 ReadableStream 使用同一 deadline”要求，也说明现有 101
   项 Node 只覆盖了 synthesize body，没有覆盖 readiness body。最小整改：让 readiness 的
   fetch 与有界 JSON body 读取处于同一个 `withDeadline(active => ...)`；设置小型 JSON 字节
   上限，并增加挂流、reader error、超限和 shutdown 后 active 归零的永久回归。
2. **PK-140/共享装配：不同 `server_root` 会静默复用旧 adapter 的配置路径。**
   `_reuse_or_register_official_sidecar()` 目前只比较 adapter 精确类型。独立使用同一临时
   `ModuleManager`，先以临时根 `a`、再以临时根 `b` 构造两个 `InstalledModuleHost`：第二个
   `qq_adapter.configuration_path` 实际仍为 `a/qq_bridge/.env`，而不是要求的
   `b/qq_bridge/.env`，且 `same_adapter=true`。本夹具只访问系统临时目录，但证明已有 manager
   状态可能让新测试根/新 composition 读取旧根配置，未完全满足“显式使用当前 server_root，
   测试根只访问自己的临时目录”。最小整改：官方 QQ adapter 的幂等复用除精确类外，还必须
   核对固定 env/data 路径与当前 server_root 完全一致；同根 reload 继续复用，不同根必须在
   构造 configuration store 前固定失败，不能静默沿用旧路径；为 data root 增加只读精确匹配
   接缝并补同根/异根永久回归。

### 已通过的整改功能

- `voice_reply.mjs` 的 synthesize 路径现以同一个 `withDeadline` 覆盖 fetch、响应头和
  `ReadableStream`；reader 累计实际字节，超过 8 MiB 即 abort/cancel，伪造较小
  `Content-Length` 不能绕过。正式 Node 回归覆盖挂流到期、超量、shutdown/deadline 竞态和
  reader error，均零上传、零 media send；普通成功链仍严格一次 synthesize、顺序分片和一次
  `msg_type=7`，语音失败不重发已成功文字，菜单/业务/每日情报/生命维持/专注保持零 TTS。
- `QQBOT_MEDIA_UPLOAD_CAPABILITY` 更新接口只接受
  `unknown|available|unavailable|denied`，缺失为 unknown；非法值、replace 失败保留旧字节，
  临时文件清理；同一 store 的并发更新留下单个完整枚举值。写 available 是本机原子配置写入，
  代码没有网络或探测；写 denied/unavailable/unknown 会同时把 reply-with-voice 关闭。
- 同一个临时 `server_root` 下，`InstalledModuleHost` 把 adapter、
  `QQBridgeConfigurationStore`、app.state capability provider 和 facade 连接到同一临时
  `.env`。独立真实组合结果：默认 `('unknown', false)`；写 available 后 facade 为
  `('available', reply_with_voice=true)` 且 app.state provider 同步返回 available；降为 denied
  后为 `('denied', false)`。fake voice profile ready 只影响本机 readiness，不从 AppID/Secret
  推断权限，也没有真实 QQ 探测。
- PK-210 既有 synthesize/Silk fake 回归继续通过：只对既有文字一次 TTS/一次 encode，固定
  PCM/Silk profile、时长/大小边界，无 ASR/conversation/history。

### 实际运行与隔离证据

- 隔离 Python 3.12.7：
  `qq_bridge/tests/test_configuration_panel.py`、`test_qq_control.py`、
  `test_module_host_assembly.py`、`test_voice_module.py`、`test_voice_silk_encoder.py` 合计
  `34 passed`。
- `node --test tests/*.test.mjs`：`101 passed, 0 failed`。上述 readiness 挂流是另加的独立
  逆向夹具，固定复现失败；它没有被现有全绿结果掩盖。
- 相关 Python compile 退出 0，pycache 写入系统临时目录；QQ src/tests 共 15 个 MJS 全部
  `node --check`；文档门禁 `28 gated task(s)`；`git diff --check` 退出 0，仅有既有
  LF→CRLF 提示。
- 本轮明确没有调用 package builder、生成或读取候选 ZIP、修改 Catalog/README/Release、
  运行 Windows filtered-copy/远端矩阵或执行 Git 写操作。真实 QQ 权限是否确实具备 media
  upload、真实 Windows `silk-python==0.2.8` 是否可编码，仍需后续部署/目标矩阵验证，本轮不
  以 fake 结果冒充。
- 所有配置、manager、runtime 和 stream 夹具都位于系统临时目录或纯内存；未读取、打印、
  diff、迁移或修改真实 `.env`、QQ data/runtime、个人状态、缓存、`server/runtime/`、
  `vendor/`、模型或 Voice Pack；未启动 Core/QQ/LLM/TTS/ASR，未联网或发送消息。

## 仅源码阻断最小修复与复验通过（2026-08-10）

### 修复

- PK-140 `voice_reply.mjs` 新增 64 KiB 配置响应体上限，并把 readiness 的 fetch、响应头、
  `ReadableStream` 消费和 JSON 解析放入同一个 `withDeadline`。音频和配置统一复用有界 reader；
  timeout/shutdown 会 abort controller 并 cancel reader，实际累计字节超限立即停止，不在完整读取
  后才判断。
- QQ adapter 新增只读 `data_root`；共享 composition 的官方 adapter 幂等复用除精确类型外，
  还必须同时匹配当前 `server_root/qq_bridge/.env` 与 `server_root/qq_bridge/data`。同根 reload
  继续复用；异根在构造 configuration store、读取旧配置或产生写入前以固定错误拒绝。
- 新增永久逆向：readiness JSON 响应头已到但 body 永不完成；同 manager 同根复用及异根拒绝。
  未改变 QQ API、普通聊天顺序、capability 枚举、Voice profile、上传协议或发布元数据。

### 独立复验结论

- **本轮仅源码功能通过。** 原 readiness 复现已由
  `HUNG_READINESS_AFTER_TIMEOUT_AND_STOP` 反转为
  `settled:voice_unavailable`，`cancelled=1`、`inFlight=0`；零 synthesize、零 QQ 上传/发送。
- 原异根复现现在固定返回 `sidecar adapter is bound to a different production root`；第一个
  adapter 保持自己的临时 A 根，临时 B 根没有静默继承 A 的 `.env`/data。正式同根重复 host
  仍共享唯一 adapter。
- capability 同根生产组合继续通过：默认 unknown 不可开启；临时 available 后 app.state
  provider 与 facade 同时 available 并可开启；denied 后自动关闭。未从 AppID/Secret 推断，
  未执行网络探测。

### 验证与剩余门禁

- 定向 `voice_reply.test.mjs`：`19 passed`；全部 QQ Node：`102 passed, 0 failed`。
- configuration、qq-control、module host、PK-210 synthesize/Silk fake：`34 passed`。
- 相关 Python compile、Ruff、15 个 QQ MJS `node --check` 全部通过；文档门禁
  `28 gated task(s)`；`git diff --check` 退出 0，仅有既有 LF→CRLF 提示。
- 本节只关闭前一节两个源码阻断。真实 QQ Bot 是否确有媒体上传权限、真实 Windows
  `silk-python==0.2.8` 编码，以及 Catalog/README/Release ZIP/tracked filtered-copy/同提交
  远端矩阵仍是后续发布门禁，未被本地 fake 结果替代。
- 未调用 package builder、未生成 ZIP、未修改 Catalog/README/Release 元数据，未执行 Git
  暂存、提交、推送、发布或清理；所有新增夹具只使用系统临时目录/纯内存，保护数据和真实服务
  均未访问或启动。PK-900 继续“进行中”，PK-020、PK-140、PK-210 继续“待集成”。

## PK-140 QQ Gateway 连接状态、C2C 去重与生命周期独立验收（2026-08-10）

### 结论与状态

- **不通过。** READY/心跳 ACK、进程/Gateway 双层状态、复合 C2C 去重、固定 endpoint、
  原子脱敏快照和 `qq_bridge@0.1.10` 确定性包均通过独立复核；但启动阶段的 owned stdin
  shutdown 仍有可复现生命周期阻断。当前官方 Catalog 与两处公开文档也尚未收口到候选版本。
- PK-900 保持“进行中”，PK-140 保持“待集成”。本轮只追加本报告，没有修改产品、
  `TASKS.md`、PK-140 状态、Catalog 或其他历史验收记录。

### 阻断证据、责任与最小整改

1. **PK-140 P1：启动中的 owned sidecar 无法在 adapter 等待窗口内确定性关闭。**
   `server/qq_bridge/src/index.mjs` 在第 204–207 行依次等待 daily scheduler、life scheduler 和
   `gateway.connect()`，直到第 219–225 行才安装 stdin `shutdown` listener。与此同时，
   `server/qq_bridge/src/gateway_client.mjs` 第 206–207 行直接等待 token/Gateway provider，
   第 347 行的 `stop()` 不能取消或结算这些未返回的 Promise；Python adapter 在
   `module_adapter.py` 第 680–682 行写入 `shutdown\n` 后只等待至多 10 秒。
   独立纯 fake 夹具令 `getAccessToken()` 保持 pending，调用 `connect()` 后立即 `stop()`；
   50 ms 竞态结果固定为
   `{"bootstrap_stop_result":"still_pending_after_stop","state":"stopped","sockets_created":0}`。
   这证明内部状态虽然停止，主 `await gateway.connect()` 仍不结算；默认 45 秒请求超时可超过
   adapter 的 10 秒 wait，导致启动后立即停用/卸载返回 `shutdown_failed`。最小整改仅归 PK-140：
   在任何可挂起启动 await 前建立固定 stdin shutdown；让 scheduler 首次刷新和 Gateway
   token/URL bootstrap 接受同一关闭信号，或采用等价的有界可取消启动任务；`stop()` 后相关
   Promise 必须及时结算、零 socket/重连/dispatch，并补 token pending、schedule pending、
   gateway URL pending 与重复 stop 的永久进程生命周期回归。不得增加 kill-by-name 或宽泛终止。
2. **PK-140/共享文档：当前架构与公开 README 仍陈述旧事实。**
   `docs/architecture/qq-bridge.md:107` 仍写“QQ 尚未接入 PK-010 可安装 sidecar”，与实际
   manifest/adapter/lifecycle 及本轮 0.1.10 包冲突；`README.md:1113` 仍把本地候选写为
   `qq_bridge@0.1.5`。最小范围是由 PK-140/共享文档所有者改成当前 installable lifecycle、
   process/Gateway 双层健康与 0.1.10 部署要求，同时保留“无远程 stop API、无自动安装/启动”的
   真实限制；不得抹除任务文件中的历史版本记录。
3. **PK-000 发布接缝：官方 Catalog 尚未合并本批候选。**
   当前 `official-catalog.json` 仍登记 `qq_bridge@0.1.7`、旧摘要/大小/tag，且可选依赖缺少
   `voice`；候选 fragment/manifest 已是 0.1.10。`test_official_module_release_set.py` 实际为
   `1 failed, 7 passed`，首个失败先暴露同一混合发布批次中 `voice@1.0.5` 与 Catalog
   `voice@1.0.3` 不一致；独立逐字段读取同时确认 QQ 条目也未合并。本项不要求 PK-140 越权
   修改共享 Catalog，但在 PK-000 串行合并并重跑 19 包 release-set 前不能发布或关闭。

### 已通过的独立功能与逆向结果

- 全部 bridge Node 测试：`110 passed, 0 failed`。确认固定 Intent `1 << 25`，只有 READY 与
  heartbeat ACK 同时出现才 `gateway_ready/dispatch`；Hello/READY/heartbeat timeout、op7、
  op9、close/error、重连和 shutdown 的现有 fake 回归通过。
- 自建“进程存活但零 READY”临时夹具得到
  `process_running=true, gateway_ready=false, gateway_state=gateway_unavailable`，没有创建状态文件。
  自建“旧连接晚到 READY/ACK/C2C”夹具证明旧代事件全部丢弃，当前连接 READY+ACK 后仅分发一次，
  stop 后 socket/heartbeat/reconnect/phase timers 全清理。
- 自建状态逆向接受一个合法快照，并在不覆盖旧字节的前提下拒绝损坏 JSON、过期、PID 错、
  generation 非法、READY 无 ACK、未知错误码和额外消息字段。快照响应不返回 generation、PID、
  URL、凭证、OpenID 或正文。
- 自建 endpoint/C2C 夹具在网络前拒绝 14 类非 allowlist scheme/host/userinfo/path/query/hash/
  port；默认使用 `https://api.bot.qq.com`，旧 base 仅精确显式值可用。当前正文进入 conversation，
  引用正文零使用；真重复一次，同 msg_id 的三个合法不同 seq/idx 均未误杀，非 0/103 类型零调用。
- 0.1.10 在两个系统临时目录独立构建字节一致：`142652` bytes，SHA-256
  `58057cf09203aece182279f52dc8fe54f648372bea10a0f11b6f3c22de95bcf5`；包内 manifest SHA-256
  `be179ef7e223c79764d07de1c2d903df19b5e3d0584971c7348b82a9958d5a08`，共 15 个精确文件。
  ZIP 无 `.env`、data/runtime/cache、node_modules、vendor、凭据、本机绝对路径或个人状态。
- Python QQ configuration/installable/qq-control：`34 passed`；模块 lifecycle/host assembly、
  dashboard、feature catalog、conversation consumers、daily briefing module/cache、voice
  module/installable：`62 passed`。并发 start、owned fake stdin stop、外部实例拒绝终止、配置与
  runtime 保留、文字优先和语音失败降级等既有回归通过；上述启动期 pending provider 是这些
  fake process 用例未覆盖的新失败。
- 相关 Python `compileall` 与 Ruff 通过；QQ src/tests 及动态面板全部 `node --check`，dashboard
  Node `1 passed`。release 专属 README、fragment、manifest、package builder 与 PK-140 最新记录
  的 0.1.10 版本/tag/asset/size/hash 彼此一致。

### 数据隔离、命令与剩余门禁

- 使用工作区外既有 Python 3.12.7、本机 Node 24、纯内存 fake、系统临时 package/status/config
  目录；没有借用或修改项目 venv/node_modules，没有启动 BAT/Core/sidecar/Gateway，没有真实
  QQ/LLM/TTS/Collector/发送或业务网络。Node 24 只作为本地补充，不冒充目标 Node 22。
- 未读取、打印、diff、迁移或修改真实 `.env`、AppID/Secret/Token/OpenID、QQ data/runtime、
  聊天正文、个人状态、缓存、模型、Voice Pack、`server/runtime/` 或 `vendor/`；混合工作区的
  demon/focus、robot、intel 等差异全部排除。未执行 Git 暂存、提交、推送、发布或清理。
- 实际运行：全部 `server/qq_bridge/tests/*.test.mjs`；QQ 两组 Python 专项与
  `test_qq_control.py`；九组 lifecycle/dashboard/catalog/consumer/briefing/voice 回归；
  official catalog/release-set；两组独立 Gateway 夹具、endpoint/C2C 与状态逆向；0.1.10
  双构建；Python compile/Ruff、MJS/dashboard 语法及 dashboard Node。文档门禁与
  `git diff --check` 在追加本报告后重跑：文档门禁通过 `28 gated task(s)`；全工作区与本报告
  定向 `git diff --check` 均退出 0，仅有混合工作区既有 LF→CRLF 提示。
- [x] TASK_RECORD — 本节记录通过项、阻断、精确责任、测试与隔离。
- [x] TASKS_BOARD — 未修改；PK-900“进行中”，PK-140“待集成”。
- [ ] PUBLIC_README — 根 README 仍保留 0.1.5 当前候选陈述，待共享所有者收口。
- [ ] MODULE_CATALOG — 0.1.10 尚未进入官方 Catalog，release-set 当前失败。
- [ ] ARCHITECTURE_DOCS — QQ 架构末句仍否认已存在的 installable lifecycle。
- [x] LOCAL_README — 按要求读取但未输出、修改或提交本机私有内容。
- [x] AGENT_RULES — 遵守混合工作区、保护数据、临时夹具和 Git 只读边界。
- [ ] VALIDATION — 本地功能/逆向大部分通过，但启动期 shutdown 阻断和发布接缝未关闭。

## PK-140 0.1.11 启动期 shutdown 整改独立复验（2026-08-10）

### 结论与状态

- **不通过。** 0.1.10 的 startup/stop 阻断已经关闭：pending token、pending Gateway URL、
  pending daily/life refresh 和 CONNECTING WebSocket 均能在 stop 后明显早于 adapter 10 秒窗口
  结算；旧代晚到事件、重复 stop 和 late provider resolve/reject 均未复活 socket、timer、状态或
  dispatch。但独立逆向发现同一生命周期仍没有覆盖 OpenAPI JSON 响应体：响应头返回后，
  shutdown 只让外层调用结算，底层请求 signal 与 ReadableStream 没有被取消，仍可能留下挂起连接。
- PK-900 保持“进行中”，PK-140 保持“待集成”。本轮仅追加本报告，没有修改产品、`TASKS.md`、
  PK-140 状态、Catalog、公共 README 或其他历史记录。

### 已关闭的原阻断与独立逆向证据

- 自建纯内存 fake 覆盖 pending token provider、pending Gateway URL provider（stop 后再 resolve 与
  reject）及 CONNECTING WebSocket；所有调用方均在 100 ms 内结算，pending provider 没有创建
  socket，CONNECTING socket 得到 close/terminate，重复 stop 幂等。随后注入 late
  open/Hello/READY/heartbeat ACK/C2C/op7/op9/close，结果为零新状态、零 dispatch、零 timer、
  零 unhandled rejection：
  `pending_token_settled=true`、`pending_url_resolve_reject_settled=true`、
  `connecting_terminated=true`、`late_events_blocked=true`、`unhandled_rejections=0`。
- 自建系统临时目录 scheduler 夹具让 daily/life 首次 provider 永久 pending，start 后立即 stop；
  两个 start promise 均在 100 ms 内结算，两个 provider 的 signal 均已 aborted，timer 数为 0；
  stop 后再让 daily resolve、life reject，没有未处理 rejection 或 late state。
- 源码确认 `index.mjs` 在任何 startup await 前安装唯一 stdin/signal shutdown；shutdown 先 abort，
  再停止 gateway、voice、daily/life/focus scheduler 并移除监听。`settleWithSignal()` 消费 late
  resolve/reject；Gateway generation/socket identity/stopped 检查阻止旧代事件复活。

### 新阻断证据、责任与最小整改

1. **PK-140 P1：JSON 响应体不在 request deadline/lifecycle signal 的有效期内。**
   `server/qq_bridge/src/bridge_core.mjs:84-95` 的 `fetchWithTimeout()` 仅等待 fetch 返回响应头，随后
   在 `finally` 中立即清 timer 并移除外部 abort listener；`readSafeJson()` 到第 103 行才另行
   `await response.text()`。独立 fake fetch 返回已到达的 200 响应头，并让 body 只写入半段 JSON
   后永久挂起。Gateway connect 后立即 stop，外层 connect 确实结算，但底层结果固定为
   `request_signal_aborted=false`、`request_abort_events=0`、`stream_cancelled=0`。这说明 lifecycle
   只忽略了结果，没有真正清除正在读取的连接；token、OpenAPI、daily/life 等共用 JSON 路径均受
   影响，不能满足本批“AbortSignal 真实传入并在 abort 时清 timer/连接”的完成标准。
2. 最小整改限于 PK-140 公共 HTTP helper：让同一 controller、deadline 和外部 lifecycle signal
   覆盖 fetch、响应头和完整的有界 JSON body 读取；abort/timeout/shutdown 必须取消 reader/body
   并让底层 request signal 进入 aborted。补永久 fake 回归覆盖 token、Gateway URL、QQ OpenAPI、
   daily/life JSON 在“响应头已到但 body 永久挂起/reader error/超限”时及时结算、流被取消、
   零 late state、零 timer、零 unhandled rejection。不得通过只 race 外层 Promise 来伪装底层关闭。

### 其余实际结果

- 全部 QQ Node：`117 passed, 0 failed`。上一轮官方 `api.bot.qq.com` 默认、精确 legacy base、
  Gateway READY+ACK、快照校验、C2C `msg_id+msg_seq+msg_idx` 去重、文字先发和语音失败降级回归
  未出现失败。
- QQ configuration/installable/qq-control：`34 passed`；九组 lifecycle、host assembly、dashboard、
  feature catalog、conversation consumer、daily briefing 与 voice 回归：`62 passed`。
- 0.1.11 在两个系统临时目录重建字节一致：`147675` bytes，SHA-256
  `c264e4effeb48c387a7413b712eb44fa425c51ca8b1a376c8e45ee8a2b3ade54`；manifest SHA-256
  `025a46896463719848de81f30421a606f2624d62d551042c82007ad41a57e235`，15 个文件，包内无
  `.env`、data/runtime/cache、node_modules、vendor、凭据、本机绝对路径或个人数据。
- 相关 Python `compileall`、Ruff、QQ src/tests 与 dashboard `node --check` 全部通过；dashboard
  Node 测试 `1 passed`。官方 catalog/release-set 为 `1 failed, 7 passed`，首个失败来自共享批次
  `voice@1.0.5` 与 Catalog `voice@1.0.3`；QQ 0.1.11 也尚未串行进入 Catalog。按本轮边界，这些是
  PK-000 的共享发布门禁，不归责 PK-140，也不掩盖上述源码阻断。

### 数据隔离与门禁

- 所有新增夹具均为纯内存 fake 或系统临时目录；没有启动 BAT、Core、sidecar、Gateway、QQ、
  LLM、TTS 或业务网络，没有安装依赖或发送消息。使用工作区外既有 Python 3.12.7 和本机 Node
  24，仅作本地复验，不冒充发布矩阵。
- 未读取、打印、diff、复制或修改真实 `.env`、AppID/Secret/Token/OpenID、QQ data/runtime、
  聊天正文、个人状态、缓存、模型、Voice Pack、`server/runtime/` 或 `vendor/`；demon/focus 等
  混合工作区差异继续排除。未执行 Git 暂存、提交、推送、发布或清理。
- [x] TASK_RECORD — 已记录原阻断关闭、新阻断复现、责任、最小整改、测试与隔离。
- [x] TASKS_BOARD — 未修改；PK-900“进行中”，PK-140“待集成”。
- [ ] PUBLIC_README — 由 PK-000 在共享版本收齐后串行更新，不作为本轮 PK-140 越权整改。
- [ ] MODULE_CATALOG — 0.1.11 与共享 voice release-set 尚未合并，留作 PK-000 发布门禁。
- [ ] ARCHITECTURE_DOCS — 共享 QQ 架构收口留给 PK-000，不归责本轮 startup 修复。
- [x] LOCAL_README — 未输出、修改或提交本机私有内容。
- [x] AGENT_RULES — 遵守临时目录、保护数据、混合工作区与 Git 只读边界。
- [ ] VALIDATION — 原 startup/stop 竞态已通过，但 JSON body 底层取消阻断尚未关闭。

## PK-140 0.1.12 HTTP JSON body 整改聚焦独立复验（2026-08-10）

### 结论与状态

- **不通过。** 0.1.12 已经修复上一轮“外层 settle、底层请求/流不取消”的主体缺陷：在 token、
  Gateway URL、普通 OpenAPI、daily/life schedule 与 conversation 的自建原生 Web Stream 挂流
  夹具中，调用方均在 100 ms 窗口内结算，内部 request signal 均 `aborted=true`、abort event
  恰好 1、reader cancel 恰好 1、body lock 已释放；conversation 为零 fallback send、零
  interaction、零 voice。但“响应头到达后、reader 建立前”的取消仍可能被解释为空 JSON 成功，
  并且 401 响应体取消后会错误执行一次 token refresh，违反本批明确的“abort 后不得刷新或重试”。
- PK-900 保持“进行中”，PK-140 保持“待集成”。本轮仅追加报告，没有修改产品、`TASKS.md`、
  PK-140 状态、Catalog、README 或发布元数据。

### 独立逆向与阻断证据

1. **PK-140 P1：原生 Web Stream 的 headers→reader 取消竞态没有稳定 fail closed。**
   独立使用 Node 原生 `Response`/`ReadableStream`，fetch 已返回 200 响应头但尚未调用
   `readSafeJson()` 时触发 lifecycle abort，再开始读取。底层行为正确地得到
   `request.signal.aborted=true`、abort event 1、stream cancel 1、`body.locked=false`，但
   `readSafeJson()` 可能解析为成功的空对象，而不是稳定 `request_cancelled`。原因是
   `server/qq_bridge/src/bridge_core.mjs:198` 在 reader cancel 使 pending read 返回 `done=true` 后
   立即退出循环，第 211 行返回空字符串；其间没有再次检查 signal，随后空 body 被解释成 `{}`。
   同一原生流若先进入半段 JSON，则返回稳定但错误语义的 `invalid_response`。现有永久测试使用
   自定义 reader，其 cancel 不会像原生 Web Stream 一样把 read 结算为 done，因此没有覆盖此竞态。
2. **PK-140 P1：401 body 读取中 abort 后仍刷新 token。** 独立链路为：初始 token 成功 →
   OpenAPI 返回 401 响应头与永久 pending body → lifecycle abort。底层 request/cancel/lock 均正确
   清理且 caller 在 1 ms 内结算，但 fetch 总调用数为 3：初始 token、401 API、以及不应发生的
   token refresh，`refresh_or_retry_calls=1`。根因是
   `server/qq_bridge/src/bridge_core.mjs:282` 只判断 `response.status === 401 && allowRetry`，没有要求
   读取已完整结束为 `http_401`，也没有在 refresh 前拒绝 aborted signal。相比之下，未取消且完整
   消费的 401 正常路径独立验证为 token 2 次、API 2 次、只刷新/重试一次，所有 body lock 均释放。
3. 最小整改仍只归 PK-140 公共 HTTP helper：在 reader 建立后、每次 read settle 后及返回 body 前
   重检 internal signal，cancel 导致的 `done=true` 也必须映射为 `request_cancelled/request_timeout`；
   401 只允许在 `readSafeJson()` 已完整消费并抛出精确 `http_401`、调用方 signal 未 aborted 时刷新，
   且 `fetchWithTimeout()` 对进入时已 aborted 的 signal 应在调用 fetch provider 前固定拒绝。补原生
   `Response/ReadableStream` 永久回归，不得只用 cancel 后仍保持 read pending 的自定义 reader。

### 已通过的修复与防回归确认

- 无或虚报很小 `Content-Length` 的原生流按实际字节逐块累计；超过 4 MiB 时 1 ms 内返回
  `response_too_large`，request signal aborted、abort event 1、cancel 1、lock 释放，未继续接受正文。
- token、Gateway URL、普通 OpenAPI、daily 与 life schedule 的 headers 后 body pending 均在 stop 后
  小于 100 ms 结算并真正取消底层流；daily/life 最终 stopped 且无残留 timer。conversation body
  pending 后 shutdown 为零 QQ 发送、零 voice，晚到结果未复活状态。
- 上游 500 JSON 中放入虚构 Token/OpenID/Authorization/URL，外部只得到
  `qq_api_http_500` / `http_500`，没有上游正文、URL 或身份泄漏。
- 最小防回归确认上一轮 provider settle、CONNECTING terminate、generation 隔离继续由完整 Node
  套件覆盖通过；没有重新扩大已经关闭的 0.1.10/0.1.11 生命周期审计范围。

### 实际测试、包与隔离

- 全部 QQ Node：`127 passed, 0 failed`；QQ configuration/installable/qq-control：`34 passed`；
  九组 lifecycle、host assembly、dashboard、feature catalog、conversation consumer、daily
  briefing 与 voice：`62 passed`；dashboard Node：`1 passed`。
- 相关 Python `compileall` 与隔离 Ruff 环境检查通过；QQ src/tests 共 15 个 MJS、动态面板均
  `node --check` 通过。
- 两个系统临时目录构建的 `qq_bridge-0.1.12.zip` 字节一致：`153307` bytes，SHA-256
  `1644c806556008217078bf32f85a7b254555cbfd8ce11aeec2d4e7b07b10103f`；源
  `package_source/manifest.json` 原始字节 SHA-256 为
  `ebafe938beec261b705feaf99a1b842c1582b07bcbe7ef6bab8cfc59d78c1d36`，与交接口径一致。包内
  manifest 经 builder 规范化后摘要为
  `6ed2042afd2b324d732a3db5a82ec55b2434000b6f54de26ca8f93fb45dcad07`；这是确定性规范化字节口径，
  不是候选源 manifest 摘要冲突。ZIP 共 15 项，禁止路径、秘密标记和本机绝对路径均为 0。
- 所有独立夹具使用纯内存 fake、虚构身份和系统临时目录；没有启动 BAT/Core/sidecar/Gateway、
  没有真实 QQ/LLM/TTS/网络或发送，没有安装依赖。未读取、打印、diff、复制或修改真实 `.env`、
  QQ data/runtime、个人状态、缓存、模型、Voice Pack、`server/runtime/` 或 `vendor/`；混合工作区
  中 demon/focus/robot 等差异继续排除。未执行 Git 暂存、提交、推送、发布或清理。
- [x] TASK_RECORD — 已记录主体修复通过、原生流竞态、401 abort 刷新、最小整改与实际证据。
- [x] TASKS_BOARD — 未修改；PK-900“进行中”，PK-140“待集成”。
- [ ] PUBLIC_README — 留 PK-000 在共享版本收齐后串行处理，不归责本轮聚焦修复。
- [ ] MODULE_CATALOG — 0.1.12、voice release-set 与本机正式安装仍是 PK-000 后续门禁。
- [x] ARCHITECTURE_DOCS — 本轮源码契约已核对；公共发布陈述留 PK-000 收口。
- [x] LOCAL_README — 未输出、修改或提交本机私有配置。
- [x] AGENT_RULES — 遵守保护数据、临时目录、混合工作区和 Git 只读边界。
- [ ] VALIDATION — 主体底层取消和全部回归通过，但原生 gap 与 401 abort retry 阻断尚未关闭。

## PK-140 0.1.13 原生流取消与 401 门槛聚焦独立复验（2026-08-10）

### 结论与状态

- **通过（源码候选聚焦验收）。** 0.1.12 剩余的两个阻断均已关闭：原生 Node
  `Response/ReadableStream` 在 headers 与 reader 建立之间取消时，无论空 body、半段 JSON 或完整
  JSON 已排队，均稳定返回 `request_cancelled`；401 只有在响应体完整、有界、合法消费并得到精确
  `http_401` 且 lifecycle 仍 active 时，才执行唯一 token refresh 与唯一 API retry。
- 本结论不等同于最终发布关闭。PK-140 继续“待集成”，PK-900 继续“进行中”；真实本机安装、
  Gateway/QQ 权限运行态验证以及公共 README、Catalog、voice release-set 串行收口仍由 PK-000
  后续处理。本轮仅追加报告，未修改产品、`TASKS.md`、上游状态或发布元数据。

### 独立原生流与取消优先级证据

- 自建三类 Node 原生流：空 body cancel-to-done、半段 JSON、完整 `{"ok":true}` 已排队但流未关闭。
  fetch 返回 headers 后、调用 `readSafeJson()` 前触发 lifecycle abort；三者均在 1 ms 内 rejected，
  `code=request_cancelled`、内部 request signal aborted、abort event 恰好 1、stream cancel 恰好 1、
  `body.locked=false`，外部 lifecycle listener add/remove 均为 1。
- 自建 decoder 非法字节、HTTP 500 完整 JSON、半段非法 JSON 三种排队正文，并重复调用 abort；
  cancel 状态均优先于 decoder、JSON、status 与 return，固定 `request_cancelled`，event/cancel 各 1、
  reader lock 释放。deadline 先于随后 lifecycle abort 时固定 `request_timeout`，没有被后到取消覆盖。
- 正常未取消的 200 真空 body 仍返回 `{}`；等待超过原 timeout 后内部 request signal 仍未 aborted，
  且外部 listener add/remove 各 1，证明正常完成时 timer 与 listener 已清理。
- 全程监听 `unhandledRejection` 得到空集合；late cancel/reader settle 没有产生未处理 rejection。

### 独立 401 门槛证据

- 初始 lifecycle 已 aborted 时，分别调用 token 与 API，二者均固定 `request_cancelled`，fake fetch
  总调用为 0，证明在 provider/fetch 前拒绝。
- 401 响应体分别设置为 lifecycle abort、deadline timeout、reader error、实际超过 4 MiB、invalid
  JSON；对应错误为 `request_cancelled`、`request_timeout`、`response_read_failed`、
  `response_too_large`、`invalid_response`，五种场景均为初始 token 1、API 1、refresh 0。
- 合法、完整、有界 401 的成功重试链固定为总调用 4：初始 token 1、首个 API 401、refresh token 1、
  第二 API 200；最终取得固定 Gateway URL，没有第二次 refresh 或第三次 API。
- refresh token 的原生响应体 pending 时触发 lifecycle abort：总调用 3、token 2、API 1，第二 API
  为 0；refresh request signal aborted、abort event 1、cancel 1、lock 释放，最终
  `request_cancelled`。

### 防回归、包与门禁

- 全部 QQ Node：`140 passed, 0 failed`，覆盖 0.1.12 已通过的 body 取消、4 MiB 实际字节上限，
  以及 startup/provider settle、CONNECTING terminate、Gateway generation/READY+ACK、C2C 去重、
  文字优先与 QQ 语音失败降级。
- QQ configuration/installable/qq-control：`34 passed`；九组 lifecycle、host assembly、dashboard、
  feature catalog、conversation consumer、daily briefing 与 voice：`62 passed`；dashboard Node
  `1 passed`。相关 Python `compileall`、隔离 Ruff、15 个 QQ src/tests MJS 与动态面板
  `node --check` 均通过。
- 两个系统临时目录独立构建的 `qq_bridge-0.1.13.zip` 字节一致：`154813` bytes，SHA-256
  `7a131eea277a979af267df0f21066b7a80996a0118e1ed631340d6b4de2dce00`；源 manifest SHA-256
  `10651336969c6335fb5af4870504218ff0572f68b5e6cf9e6c9cf820fc3306c9`。ZIP 共 15 项，`.env`、
  data/runtime/cache、node_modules、vendor、秘密标记、本机绝对路径和个人数据命中均为 0。

### 数据隔离与后续门禁

- 所有新增夹具使用纯内存 fake、虚构凭据/身份和系统临时目录；未启动 BAT、Core、sidecar、
  Gateway、QQ、LLM、TTS，没有联网、发送或安装运行时。未读取、打印、diff、复制或修改真实
  `.env`、QQ data/runtime、个人状态、缓存、模型、Voice Pack、`server/runtime/` 或 `vendor/`；
  demon/focus/robot 等混合工作区差异继续排除。未执行 Git 暂存、提交、推送、发布或清理。
- [x] TASK_RECORD — 已记录原生流、取消优先级、401 门槛、防回归、包摘要与隔离证据。
- [x] TASKS_BOARD — 未修改；PK-900“进行中”，PK-140“待集成”。
- [ ] PUBLIC_README — 留 PK-000 与正式运行态、版本集串行收口。
- [ ] MODULE_CATALOG — 0.1.13、voice release-set 与正式安装仍是 PK-000 后续门禁。
- [x] ARCHITECTURE_DOCS — 聚焦源码契约与当前 QQ 架构记录一致。
- [x] LOCAL_README — 未输出、修改或提交本机私有配置。
- [x] AGENT_RULES — 遵守保护数据、临时目录、混合工作区和 Git 只读边界。
- [x] VALIDATION — 独立逆向、全量 Node、相关 Python、静态检查、双构建均通过；最终发布门禁另列。

## PK-140 0.1.14 Gateway 分阶段诊断聚焦独立复验（2026-08-11）

### 结论与状态

- **通过（仅源码候选聚焦验收）。** 0.1.14 把正式安装后原先统一的 `connect_failed` 收窄为
  token、Gateway discovery、Gateway URL、WebSocket 与 Hello/READY 五组固定阶段码；独立 fake
  未发现原始异常、URL、响应正文或虚构 AppID/Token/Secret 进入状态、日志、facade 或动态面板。
- `process_running=true` 仍只表示 owned sidecar 存活；没有新鲜且结构合法的 READY + heartbeat ACK
  快照时 `gateway_ready=false`，不会把 `reconnect_wait` 或单纯进程存活冒充已连接。每个失败只保留
  一个有界重连；`stop()` 的 abort、timer/socket 清理和 generation 隔离可阻止旧 provider、timer、
  socket event 复活。
- 本结论不替代真实运行态关门。PK-140 保持“待集成”，PK-900 保持“进行中”；0.1.14 真实重新安装、
  有凭据的 Gateway/QQ 权限运行态、公共 Catalog/README 与批次发布仍由 PK-000 串行处理。

### 独立阶段码、泄漏与生命周期证据

- 自建一次性纯内存 Node fake 覆盖 14 个分支：token 网络/401/invalid body，Gateway 网络/401/invalid
  body，Gateway URL missing/invalid/rejected，WebSocket constructor/error/close，以及 Hello/READY
  timeout。14/14 均得到各自唯一固定码：`token_request_failed`、`token_rejected`、
  `token_response_invalid`、`gateway_request_failed`、`gateway_rejected`、
  `gateway_response_invalid`、三种 `gateway_url_*`、三种 `websocket_*` 与两种 timeout；没有回退成
  原始异常或不受控字符串。
- 每个 fake 均断言状态与日志不含虚构秘密、恶意 URL、Token 或 query；命中为 0。每次失败只存在
  一个 reconnect timer；停止后手工调用已捕获的旧 timer，provider/socket 计数和最终状态均不再变化，
  `stale_revival=0`。
- Python adapter/facade 回归实际验证：进程存在但没有合法新鲜 Gateway 快照时为
  `gateway_unavailable` / `gateway_ready=false`；合法 READY + heartbeat ACK 才为 connected；
  reconnect 快照只返回 allowlist code 与固定安全提示，未知字段、PID、generation、URL 和秘密不向
  control facade 泄漏。

### 取消优先级、防回归与静态门禁

- QQ Node 全量 `141 passed, 0 failed`；其中 0.1.13 的 headers→reader 取消优先级、已取消零
  provider/fetch、401 仅在完整合法 body 后唯一 refresh/retry、4 MiB 实际字节上限，以及 startup
  shutdown、CONNECTING terminate、C2C、文字优先和语音失败降级均继续通过。
- QQ configuration/installable/qq-control 共 `34 passed`；module host、dashboard、feature catalog、
  conversation consumer、daily briefing 等相关脚本退出 0；dashboard Node `1 passed`。QQ src/tests
  15 个 MJS 与动态 dashboard 共 16 个文件 `node --check` 通过；12 个相关 Python 文件以内存
  `compile()` 通过，未生成编译产物。
- 当前项目 `.venv-asr` 与系统 Python 均未安装 Ruff，且本轮按隔离要求未联网、未安装依赖，因此
  **本代理无法独立复跑 Ruff**。这是验收环境能力限制，不是 Ruff 失败；Python 定向测试、内存编译、
  Node 全量/静态检查与相关 `git diff --check` 均已通过。后续 PK-000 发布前仍应在具备锁定 Ruff 的
  隔离环境复跑该质量门禁。
- 文档门禁实际通过 `28 gated task(s)`；相关 `git diff --check` 退出 0，仅有既有 LF/CRLF 提示。

### 双构建、包扫描与隔离

- 本代理与根验收代理分别从当前源码触发双构建；根代理补齐完整只读结果：A/B 均为 `158283`
  bytes，SHA-256 均为
  `90767a065e7bbf4d8cf4ae91de1a399a0d9807b02439858010546389d7b57eee`，字节完全一致；源
  `package_source/manifest.json` SHA-256 由本代理独立复算为
  `fcc956e6bb1a1eb1c84046f33ddc7446ec409114c20c557100bcb455ee99e03f`。
- ZIP 恰好 15 项；`.env`、`node_modules`、data/runtime/vendor、绝对路径、PEM/key/token/secret
  与既定虚构秘密标记命中均为 0，expected size/hash 均为 true。候选仍未发布。
- 未启动 BAT、Core、sidecar 或真实 Gateway，未联网、发送消息、调用 QQ/LLM/TTS 或安装依赖；
  未读取或输出真实 QQ `.env`、凭据、个人正文、QQ runtime、`server/runtime/` 或 `vendor/` 内容，
  未执行 Git 暂存、提交、推送、发布或清理混合工作区。一次跨模块 daily briefing 脚本只报告固定
  缓存路径下“缓存未生成”，未输出缓存正文且未写入；后续检查未再触碰该路径。双构建产物留在
  Codex 专用验收工作区，不在项目仓库中。

### 本轮文档门禁

- [x] TASK_RECORD — 本节记录阶段码、独立 fake、双层健康、生命周期、回归、包与限制。
- [x] TASKS_BOARD — 未修改；PK-900“进行中”，PK-140“待集成”。
- [ ] PUBLIC_README — 真实重新安装与公共发布说明留 PK-000 串行收口。
- [ ] MODULE_CATALOG — 0.1.14 正式 Catalog、资产发布与真实安装仍是 PK-000 后续门禁。
- [x] ARCHITECTURE_DOCS — 当前 QQ 架构与有限阶段码、双层健康及 shutdown 契约一致。
- [x] LOCAL_README — 未修改、输出或提交本机私有配置。
- [x] AGENT_RULES — 保留混合工作区、Git 只读与外部能力隔离；未触碰真实凭据和运行态。
- [x] VALIDATION — 独立逆向、14 项 fake、Node/Python 回归、静态检查、双构建、文档与 diff 已通过；
  Ruff 因当前离线环境未安装而明确留作 PK-000 发布前补跑，不冒充已执行。

## PK-140 0.1.15 READY 后首次心跳时序聚焦独立复验（2026-08-11）

### 结论与状态

- **不通过。** 0.1.15 的主体时序整改有效：Hello 后只有一个 Identify、READY 前 heartbeat 为 0、
  首个合法 READY 后 heartbeat 恰好为 1，首次 pending heartbeat 的 ACK 前业务 dispatch 为 0，ACK
  后才放行；重复 Hello/READY、伪 ACK、READY timeout、heartbeat timeout、stop 和晚到事件的表面
  状态门槛均失败关闭。
- 但独立逆序夹具发现一个未被永久测试覆盖的 P1 阻断：消息入口在确认该帧是否应被忽略之前就
  无条件用 `payload.s` 推进 `lastSequence`。因此 READY-before-Hello、重复 READY，以及有效 ACK 前
  被拒绝的业务 dispatch 虽然没有触发业务 callback，却仍会让后续 heartbeat 确认该未接受序号，
  存在跳过并丢失未放行业务事件的风险；这不满足交接中“忽略”与 ACK 前 dispatch=0 的完整语义。
- PK-140 保持“待集成”，PK-900 保持“进行中”。本轮只追加独立报告，不修改产品、上游任务状态、
  `TASKS.md`、Catalog 或发布元数据。

### 阻断证据、归属与最小整改

- 根因位于 `server/qq_bridge/src/gateway_client.mjs` 的 message handler：当前先执行
  `if (payload.s !== null && payload.s !== undefined) lastSequence = payload.s`，然后才判断
  `helloSeen`、`readySeen`、`awaitingHeartbeatAck` 与 dispatch gate。被明确拒绝/忽略的帧仍产生协议
  序号副作用。
- 独立纯内存 fake 的实际 heartbeat `d` 序列：
  - READY-before-Hello 携带 `s=90`，随后 Hello 与无 `s` 的合法 READY：首次 heartbeat 为 `[90]`；
  - 合法 READY `s=1` 后重复 READY `s=99`，ACK 后触发周期 heartbeat：序列为 `[1, 99]`；
  - 合法 READY `s=1` 后、ACK 前被拒绝的 C2C dispatch `s=77`，ACK 后触发周期 heartbeat：序列为
    `[1, 77]`，虽然对应业务 dispatch 计数仍为 0。
- 责任归属 PK-140 Gateway 协议状态机。最小整改不需要改外部契约：把 `lastSequence` 更新移入各帧
  已通过顺序/重复/ready/ACK 门槛之后；READY-before-Hello、重复 Hello/READY、unexpected ACK、
  ACK 前被拒绝的 dispatch 均不得改变它。新增永久回归应同时断言 callback 计数与后续 heartbeat
  `d`，不能只断言 `gatewayReady`/dispatch 数量。

### 已通过的主体时序与历史回归

- 自建顺序/逆序/重复/伪 ACK/timeout/stop/late-event 矩阵确认：Identify=1、Hello 后 heartbeat=0、
  READY 后 heartbeat=1、有效 ACK 前 dispatch=0、ACK 后 dispatch=1；重复 READY 不新增 heartbeat/
  interval；READY 与 heartbeat timeout 各进入唯一有界重连；stop 后旧 phase/interval callback 与旧
  socket Hello/READY/ACK/dispatch 均不能复活状态。
- QQ Node 全量 `141 passed, 0 failed`，包括 0.1.13 cancellation/timeout、已取消零 provider/fetch、
  401 完整合法 body 后唯一 refresh/retry、4 MiB 实际字节上限，以及 0.1.14 阶段码、状态/日志/
  facade/dashboard 脱敏。全量通过同时说明现有永久测试没有检查被忽略帧对 heartbeat sequence 的
  隐蔽副作用，不能覆盖上述独立阻断。
- QQ configuration/installable/qq-control 共 `34 passed`；dashboard Node `1 passed`；QQ src/tests
  15 个 MJS 与动态面板共 16 个文件 `node --check` 通过；12 个相关 Python 文件以内存 `compile()`
  通过。当前项目与系统 Python 仍没有 Ruff，本轮未联网安装，故不冒充独立 Ruff 结果。
- 文档门禁通过 `28 gated task(s)`；相关 `git diff --check` 退出 0，仅有既有 LF/CRLF 提示。

### 双构建、包扫描与隔离

- 两个 Codex 专用验收目录独立构建的 `qq_bridge-0.1.15.zip` 均为 `159275` bytes，SHA-256 均为
  `ac169241acdc362cc908db758c75022cd0c7e622baeca9d9b70fc5db4617c976`，摘要一致；源 manifest
  SHA-256 为 `f82dfd37440ee3699e59c3e9d446770eac0edca3da6a5e8230abf23b88fe6692`。
- ZIP 恰好 15 项；`.env`、data/runtime/cache、node_modules、vendor、绝对用户路径、私钥头与既定
  虚构秘密标记命中均为 0。包确定性与安全扫描通过，但不能消除 Gateway 序号阻断。
- 全部外部能力为纯内存 fake/虚构值或专用验收构建目录；未读取真实 `.env`、QQ data/runtime、
  个人数据、`server/runtime/` 或 `vendor/`，未启动 BAT/Core/sidecar、未联网、发送、安装依赖或
  执行 Git 暂存、提交、推送、发布、清理。

### 本轮文档门禁

- [x] TASK_RECORD — 本节记录主体通过项、独立序号阻断、证据、归属、最小整改、回归与包摘要。
- [x] TASKS_BOARD — 未修改；PK-900“进行中”，PK-140“待集成”。
- [ ] PUBLIC_README — 候选未通过，不进入公共发布收口。
- [ ] MODULE_CATALOG — 0.1.15 不得提升至正式 Catalog/Release。
- [x] ARCHITECTURE_DOCS — 已按当前契约核对；阻断属于实现未完整满足“忽略”语义。
- [x] LOCAL_README — 未读取、修改或提交本机私有配置。
- [x] AGENT_RULES — 保留混合工作区、Git 只读和真实运行态隔离。
- [ ] VALIDATION — 主体回归、静态检查、双构建与文档/diff 通过，但 heartbeat sequence 阻断未关闭；
  Ruff 当前环境不可用亦已明确记录。

## PK-140 0.1.16 Gateway 已接受序号聚焦独立复验（2026-08-11）

### 结论与状态

- **通过（仅源码候选聚焦验收）。** 0.1.15 的 P1 序号阻断已关闭：message handler 不再在入口
  无条件复制 `payload.s`；只有 Hello 后首个合法 READY 与 READY + 有效 heartbeat ACK 后实际放行的
  op0 dispatch，才可通过 `acceptSequence()` 接受非负安全整数序号。
- 被忽略的 READY-before-Hello、重复 Hello/READY、unexpected ACK、ACK 前 dispatch、非法 JSON、
  非法/负数/超界序号均不再影响后续 heartbeat `d`。合法 ACK 即使非标准携带 `s` 也只结算 pending
  heartbeat 和健康状态，不推进事件序号。
- 本结论仅关闭源码候选聚焦门禁，不等同于真实 QQ 发布关闭。PK-140 保持“待集成”，PK-900 保持
  “进行中”；真实重新安装、有凭据 Gateway/QQ 运行态及公共 Catalog/README/Release 仍由 PK-000
  串行处理。

### 独立序号、逆序与停止证据

- 自建纯内存事件矩阵得到 heartbeat payload 链 `[1, 1, 1, 88]`：
  - READY-before-Hello `s=90`、Hello/重复 Hello 携带 `s=55/66`、unexpected ACK `s=50` 后，首个
    合法 READY `s=1` 产生的首次 heartbeat 为 `d=1`；
  - 重复 READY `s=99`、ACK 前被拒绝的 C2C dispatch `s=77`、合法 ACK `s=123` 后，下一 heartbeat
    仍为 `d=1`；
  - 后续 ACK `s=124`、非法 JSON，以及 string、负数、小数、超过 `Number.MAX_SAFE_INTEGER`、布尔
    五类非法 `s` 后，heartbeat 仍为 `d=1`；
  - 只有 READY + 有效 ACK 后实际放行的 C2C dispatch `s=88`，才使再下一 heartbeat 为 `d=88`。
- 同一夹具确认 Identify 恰好 1、READY 前 heartbeat 0、首个 READY 后 heartbeat 1、有效 ACK 前业务
  dispatch 0、ACK 后才放行；重复 READY 不新增 heartbeat/interval。停止后手工调用旧 interval 并
  注入晚到业务事件，socket send、dispatch 和最终 stopped 状态均不复活。
- 源码反向核对确认 `acceptSequence()` 只出现在首个合法 READY 分支和已满足
  `readySeen && heartbeatAcknowledged` 的 op0 dispatch 分支；op11、op7、op9、parse failure 与所有
  early/duplicate return 路径均没有序号更新。

### 历史回归与质量门禁

- QQ Node 全量 `141 passed, 0 failed`：0.1.13 的 lifecycle cancellation/timeout、已取消零
  provider/fetch、401 完整合法 body 后唯一 refresh/retry、4 MiB 实际字节上限；0.1.14 的有限阶段码
  与状态/日志/facade/dashboard 脱敏；0.1.15 的 READY 后首次 heartbeat、有效 ACK 后 ready/dispatch、
  timeout、有界唯一重连与 stop/generation 隔离均继续通过。
- QQ configuration/installable/qq-control 共 `34 passed`；dashboard Node `1 passed`；QQ src/tests
  15 个 MJS 与动态 dashboard 共 16 个文件 `node --check` 通过；12 个相关 Python 文件以内存
  `compile()` 通过。当前本机 Python 环境仍未安装 Ruff，本轮未联网安装，故不冒充 Ruff 结果；
  0.1.16 的实际产品逻辑增量为 MJS 序号门槛。
- 文档门禁通过 `28 gated task(s)`；相关 `git diff --check` 退出 0，仅报告混合工作区既有 LF/CRLF
  提示。

### 双构建、包扫描与隔离

- 两个 Codex 专用验收目录独立构建的 `qq_bridge-0.1.16.zip` 均为 `159784` bytes，SHA-256 均为
  `c2c45555bf01efa673279eab1b99e1799422a57fd8f49600bd663d633826f68a`，摘要一致；源 manifest
  SHA-256 为 `1bc524aa162e3d676d35235c7dbe4a2e17b5f239a8612d8390feb1c59031fd5f`。
- ZIP 恰好 15 项；`.env`、data/runtime/cache、node_modules、vendor、绝对用户路径、私钥头及既定
  虚构秘密标记命中均为 0。候选未发布。
- 全部网络、Gateway、身份、消息和序号均为纯内存 fake/虚构值，构建仅写 Codex 专用验收目录；
  未读取真实 `.env`、QQ data/runtime、个人数据、`server/runtime/` 或 `vendor/`，未启动 BAT/Core/
  sidecar、未联网、发送、安装依赖或执行 Git 暂存、提交、推送、发布、清理。

### 本轮文档门禁

- [x] TASK_RECORD — 本节记录原 P1 关闭、独立 heartbeat payload、逆序/非法序号、回归与包摘要。
- [x] TASKS_BOARD — 未修改；PK-900“进行中”，PK-140“待集成”。
- [ ] PUBLIC_README — 真实运行态与公共发布说明留 PK-000 串行收口。
- [ ] MODULE_CATALOG — 0.1.16 正式 Catalog、资产发布与真实安装仍是 PK-000 后续门禁。
- [x] ARCHITECTURE_DOCS — 当前已接受序号契约与 QQ 架构说明一致。
- [x] LOCAL_README — 未读取、修改或提交本机私有配置。
- [x] AGENT_RULES — 保留混合工作区、Git 只读和真实外部能力隔离。
- [x] VALIDATION — 独立序号逆向、Node/Python 回归、静态检查、双构建、文档与 diff 均通过；
  Ruff 当前环境不可用已明确记录，最终发布门禁另列。

## PK-140 0.1.17 Gateway 健康 null 状态聚焦独立复验（2026-08-11）

### 结论与状态

- **通过（仅源码候选聚焦验收）。** READY + 有效 heartbeat ACK 后，Gateway 内存状态与原子状态
  文件均为 `gateway_ready=true`、`last_error_code=null`；经 adapter/facade 后
  `gateway_last_error_code=null`、`gateway_message=null`，不再把健康连接伪报为
  `gateway_failed`。
- 未知或疑似泄漏的非 null code 继续固定归一为 `gateway_failed`，原始值不进入状态文件、facade
  或动态面板；已知有限 code 仍原样保留并映射到固定安全提示。健康与失败两条展示路径没有互相
  矛盾。
- 本结论仅关闭 0.1.17 源码候选聚焦门禁。PK-140 保持“待集成”，PK-900 保持“进行中”；真实
  重新安装、有凭据 Gateway/QQ 运行态及公共 Catalog/README/Release 仍由 PK-000 串行处理。

### 独立 null、恶意值与展示证据

- 自建纯内存文件系统和 fake WebSocket，实际经过 Hello → READY → pending heartbeat ACK，而非直接
  调用实现方断言：最终 status writer snapshot 为 `gateway_ready=true`、
  `last_error_code=null`，内存中的原子 JSON 同样保存 JSON `null`；虚构 access token 未进入状态。
- 对同一 writer 注入未知非 null 字符串 `authorization_fictional_secret`：输出稳定为
  `gateway_failed`，原始字符串落盘命中为 0；再注入 allowlist code `token_request_failed`，该 code
  正确保留，证明 null、合法 code、未知 code 三个分支互不混淆。
- 独立 Python facade fake：健康连接返回 `gateway_ready=true` 且 code/message 均为 null；失败快照
  返回 `token_request_failed` 与固定英文安全提示；未知恶意值对外 code/message 均为 null，原值命中
  为 0。动态 dashboard 源码核对确认 `gateway_ready===true` 优先显示“已连接”，非健康状态才按有限
  code 映射固定中文提示或回退有限 gateway state，不会在健康路径显示失败提示。

### 必要回归与质量门禁

- QQ Node 全量 `141 passed, 0 failed`，覆盖 0.1.13 cancellation/401/body bound、0.1.14 有限阶段码与
  脱敏、0.1.15 READY 后首次 heartbeat、0.1.16 已接受序号以及有界重连、stop/generation 隔离。
- QQ configuration/installable/qq-control 共 `34 passed`；QQ src/tests 15 个 MJS 与动态 dashboard
  共 16 个文件 `node --check` 通过；12 个相关 Python 文件以内存 `compile()` 通过。动态面板健康/
  失败分支的必要固定条件与提示映射静态核对通过。
- 文档门禁通过 `28 gated task(s)`；相关 `git diff --check` 退出 0，仅报告混合工作区既有 LF/CRLF
  提示。

### 双构建、包扫描与隔离

- 两个 Codex 专用验收目录独立构建的 `qq_bridge-0.1.17.zip` 均为 `160086` bytes，SHA-256 均为
  `71753a8697aa3f80e9f2f732ab5f0f383fc57335eacaca3a76a9236cd1ecc68b`，摘要一致；源 manifest
  SHA-256 为 `dbcea3234681fa13aaeb30a10c7627577a74844d2cae275bb9e0e6fd9e57cb1c`。
- ZIP 恰好 15 项；`.env`、data/runtime/cache、node_modules、vendor、绝对用户路径、私钥头及既定
  虚构秘密标记命中均为 0。候选未发布。
- 全部 Gateway、状态、凭据与身份为纯内存 fake/虚构值，构建仅写 Codex 专用验收目录；未读取
  真实 `.env`、QQ data/runtime、个人数据、`server/runtime/` 或 `vendor/`，未启动真实服务、联网、
  发送、安装依赖或执行 Git 暂存、提交、推送、发布、清理。

### 本轮文档门禁

- [x] TASK_RECORD — 本节记录 null 修复、三分支逆向、facade/UI 一致性、回归与包摘要。
- [x] TASKS_BOARD — 未修改；PK-900“进行中”，PK-140“待集成”。
- [ ] PUBLIC_README — 真实运行态与公共发布说明留 PK-000 串行收口。
- [ ] MODULE_CATALOG — 0.1.17 正式 Catalog、资产发布与真实安装仍是 PK-000 后续门禁。
- [x] ARCHITECTURE_DOCS — 健康 null 与有限失败码契约同当前 QQ 架构一致。
- [x] LOCAL_README — 未读取、修改或提交本机私有配置。
- [x] AGENT_RULES — 保留混合工作区、Git 只读和真实外部能力隔离。
- [x] VALIDATION — 独立 null/恶意值/facade/UI 逆向、必要 Node/Python、静态检查、双构建、文档与
  diff 均通过；最终发布门禁另列。

## PK-140 0.1.22 QQ 仅手动启动增量聚焦独立复验（2026-08-12）

### 结论与状态

- **通过（仅源码候选聚焦验收）。** `qq_bridge@0.1.22` 已把 QQ sidecar 的创建入口收敛到
  `QQControlAdapterFacade.start()`：安装、启用、更新、Core lifespan、模块激活、状态 GET 和页面挂载
  均不会创建 QQ/Node 进程；已启用模块明确返回 `waiting_manual_start`，只有本机控制台中的显式启动
  操作才会进入固定 `POST /api/v1/qq-control/start`。
- PK-140 继续保持“待集成”，PK-900 继续保持“进行中”。本结论不等同于真实运行态安装或公共发布
  关闭；公共 Catalog/README、正式安装和有凭据 QQ/Gateway 验证继续由 PK-000 串行处理。
- 本轮没有修改产品、`TASKS.md`、PK-140 状态、Catalog、README 或 Release；唯一写入是追加本验收记录。

### 独立生命周期、并发与 UI 证据

- 自建系统临时目录、虚构 env、fake Node resolver、fake `Popen` 和 fake schedule service，直接经过
  正式 `ModuleManager`、`ModuleActivationCoordinator`、`QQBridgeSidecarAdapter` 与
  `QQControlAdapterFacade`，15 项独立断言全部通过：
  - install、enable、`start_enabled_sidecars()`、activation、status 均为零进程；activation 固定返回
    `waiting_manual_start`；
  - 首次 12 路并发 `start()` 恰好产生一个进程，全部调用方看到 `process_running=true`，同时
    `gateway_ready=false`；已运行后的重复调用不新增进程；
  - disable 后重新 enable 不复活，模拟新 Core 进程重新读取同一临时 registry 后仍不自动启动，下一次
    显式点击才恰好启动一个；
  - 首次 fake `Popen` 失败得到 `start_failed`，随后 10 路并发重试只再尝试一次且仅一个调用报告
    `started=true`；
  - 独立构造默认 adapter，确认未声明 `start_automatically=False` 的既有 sidecar 在 enable 时仍自动启动；
    另以 1.0.0→1.0.1 临时 sidecar 更新证明手动 adapter 更新期间启动次数保持 0。
- 自建最小 DOM 挂载正式 `package_source/dashboard/index.js`：页面初始化只产生 status、configuration、
  daily schedule、life schedule 四个 GET；未出现 POST。原生文字 `<button>` 的一次显式 click 恰好产生
  一个固定 start POST。源码交叉核对显示公共 `panels.js` 用原生 `<button type="button">` 和明确
  `aria-label` 构造 QQ 头像启动控件，并仅转发到上述文字按钮；候选 dashboard 范围内 start endpoint
  只有这一处，展开、刷新和主题切换没有第二条启动路径。
- `scripts/start.ps1` 的 core/qq/all 正常分支只提示“等待控制台显式点击”，没有 QQ Node/独立窗口分支；
  `server/qq_bridge/start_qq_bridge.bat` 在 `PROJECT_KEI_NO_PAUSE=1` 下实际执行后只输出控制台指引并以
  2 退出，未启动 Node。根 start/BAT 的 PowerShell AST 与委托定向测试为 `2 passed`。

### 富媒体防回归、包与质量门禁

- QQ Node 全量：`143 passed, 0 failed`。另聚焦重跑 `file_info` 严格边界与 TTL 兼容两项：`2 passed`；
  明确覆盖缺失/0/86400 TTL 可接受、越界 `file_info` 拒绝，以及最终 `msg_type=7`、`content=" "`、
  `media.file_info` 固定结构。语音 capability/readiness、凭据脱敏、菜单/定时推送、Gateway
  READY/heartbeat、并发取消/重连和文字优先降级随全量 Node 套件通过。
- Python 回归：QQ installable/configuration/qq-control `35 passed`；installable lifecycle、module host、
  dashboard、feature catalog `28 passed`；conversation consumers、daily briefing、voice、QQ 合并回归
  `72 passed`。所有请求、网络、进程、时钟和持久化均为 fake 或系统临时目录。
- 两个独立系统临时目录连续构建 `qq_bridge-0.1.22.zip`，字节完全一致：`160616` bytes，SHA-256
  `cf951c8b92510d102b4fc959b2e6a3b7a32458c147fe50e2a6b97c5088a0180d`；源
  `package_source/manifest.json` SHA-256 为
  `021355e2ca6286e5d42609e709addfe2893fa465dd2f6be74afeca9ecd4fb576`。ZIP 恰好 15 项，`.env`、
  data/runtime/cache、node_modules、vendor、models、绝对路径命中均为 0。
- QQ src/tests、公共 dashboard 与模块 dashboard 共 30 个 JS/MJS 文件 `node --check` 通过；相关
  Python `compileall` 通过；隔离 Python 3.12.7 环境的 Ruff 通过；文档门禁通过 `28 gated task(s)`；
  本批显式路径的 staged/unstaged `git diff --check` 均退出 0，仅有既有 LF→CRLF 提示。
- `test_windows_install.py` 与本增量直接相关的 PowerShell AST/BAT 两项为 `2 passed, 25 deselected`。
  同一文件全量运行在 302 秒执行上限到达时仍未返回最终汇总，因此没有把其进度输出冒充全量成功；
  该限制不覆盖本轮已经单独通过的启动脚本门禁，完整 Windows 发布矩阵仍留给 PK-000。

### 数据隔离、限制与工作区排除

- 未启动真实 Core、sidecar、QQ、Gateway、LLM、ASR/TTS，未联网、发送消息、安装依赖或操作真实
  runtime。未读取、打印、diff、复制或修改真实 `.env`、QQ data/runtime、个人状态、模型、
  `vendor/`、`demon_slayer.json` 或 `focus_timer.json`；所有写状态测试都在系统临时目录。
- 一次广域文件发现命令碰到受保护 `server/runtime/` 后由操作系统直接拒绝访问；未读取任何文件内容，
  后续全部检查改用显式允许目录。该事件未产生写入或运行态副作用，亦未被用作验收证据。
- 混合工作区中的 PK-150、PK-213、robot、个人状态、`server/runtime/`、`vendor/` 及其他无关差异继续
  排除；未执行 Git 暂存、提交、推送、发布、分支切换或清理。

### 本轮文档门禁

- [x] TASK_RECORD — 已记录范围、独立夹具、实际命令结果、包摘要、隔离、限制与结论。
- [x] TASKS_BOARD — 未修改；PK-900“进行中”，PK-140“待集成”。
- [ ] PUBLIC_README — 按本轮边界不更新，留给 PK-000 正式发布串行收口。
- [ ] MODULE_CATALOG — 0.1.22 尚未安装或发布，留给 PK-000。
- [x] ARCHITECTURE_DOCS — 已核对 QQ 手动启动生命周期与当前实现一致，未发现新增冲突。
- [x] LOCAL_README — 未输出、修改或提交任何本机私有配置。
- [x] AGENT_RULES — 保留混合工作区并遵守 fake/临时目录、外部能力和 Git 写入边界。
- [x] VALIDATION — 独立生命周期/UI 逆向、Node/Python/Windows 定向、静态检查、双构建、Ruff、
  文档和 scoped diff 均通过；全量 Windows 运行超时和正式运行态/发布门禁已单列，未冒充完成。

## PK-140 0.1.24 跨 Core 重启安全关闭候选聚焦独立复验（2026-08-12）

### 结论与状态

- **通过（仅源码候选聚焦验收）**。未发现阻断项：新 Core 只有在固定 QQ dependency entry 的 Node
  PID 身份核验通过、`gateway_status.json` 严格字段集合与新鲜度通过、
  `shutdown_control_ready=true` 且 generation 合法时才得到 `can_stop=true`；跨 Core 停止只写固定四字段、
  短时有效且绑定同一 generation 的请求，不按端口发现进程，也不执行宽泛 Node kill。
- Node watcher 对错误 generation、过期/未来/超长有效期、重放、超限、符号链接、额外字段、错误 schema、
  非法时间类型及非法 JSON 均拒绝；有效请求只消费一次。当前 Core 自己持有的子进程继续走既有 stdin
  `shutdown\n` 路径，未退化为跨进程 kill 或请求文件路径。
- 本结论只关闭 0.1.24 源码候选的跨 Core 安全关闭门槛。PK-140 保持“待集成”，PK-900 保持“进行中”；
  未安装运行态、未启动真实 Core/sidecar/Gateway/QQ，正式安装、真实重启关闭与发布仍由 PK-000 串行收口。

### 独立身份、状态与请求逆向证据

- 自建隔离 Python 临时目录、fake process probe、fake identity probe 与 fake `Popen`，直接经过正式 adapter：
  严格新鲜状态、PID `4242`、精确解析后的固定 dependency root、合法 generation 与
  `shutdown_control_ready=true` 同时满足时，外部进程状态为 `process_running` 且 `can_stop=true`；独立断言
  identity probe 收到的路径和 PID 与上述固定值精确相等。分别把 control-ready 改为 false、状态改为过期、
  generation 改为非法、PID 改为 bool、增加额外字段时，5/5 均得到 `can_stop=false`；固定身份 probe
  返回 false 时同样不可停止。
- 对外部进程实际调用正式 `_request_external_shutdown()`，写出的 JSON 键恰好为
  `schema_version/generation/requested_at/expires_at`，没有 command、PID、路径或其他自由字段，
  `expires_at-requested_at` 恰好 5000 ms。源码反向核对确认请求 generation 直接来自本次重新读取并再次通过
  严格状态、身份与新鲜度检查的 snapshot；等待路径只观察目标停止，不调用 terminate/kill。
- 对当前 Core 跟踪的 fake 子进程调用正式 stop，唯一控制写入为 stdin `shutdown\n`，flush 与 wait 各一次，
  未生成跨 Core 请求；聚焦生产路径静态搜索未发现 `taskkill`、`Stop-Process`、端口枚举或宽泛 Node
  kill。`module_composition.py` 的 Windows 身份探针只查询给定 PID 的 `node.exe`，并以完整解析路径匹配固定
  `<dependency_root>/src/index.mjs`。
- 自建 Node watcher 临时目录逆向得到：10 类非法请求全部拒绝，513-byte 超限文件拒绝；一个合法四字段请求
  被删除并恰好触发一次 shutdown，同 generation 重放不再触发。当前 Windows sandbox 不允许本代理创建真实
  symlink，因此未把创建失败冒充产品结果；另以注入式文件系统令 `lstat().isSymbolicLink()` 返回 true，确认
  watcher 在读取正文前拒绝，read 次数 0、shutdown 次数 0。正式 Node 全量套件中的 symlink/oversize
  watcher 用例亦通过。
- 源码交叉核对 `shutdown_control.mjs`：只接受 32 位小写十六进制 generation、精确四字段、整数时间、
  当前时刻前后窄窗口及最长 10 秒请求寿命；先校验普通文件/非 symlink/1..512 bytes，再解析和校验，
  generation 一经消费即拒绝重放。`index.mjs` watcher 固定观察 QQ data root 下的
  `shutdown_request.json`，并绑定进程启动时生成且写入 gateway status 的同一 generation。

### 回归、静态与文档证据

- `node --test tests\\*.test.mjs`：`145 passed, 0 failed`。除本轮 watcher/lifecycle 外，既有
  cancellation、401/body bound、阶段码脱敏、READY/heartbeat/ACK、序号、重连、stop/generation、C2C、
  定时推送与文本/语音降级门槛继续通过。
- QQ configuration/installable/qq-control Python 聚焦套件：`37 passed`；`test_module_host_assembly.py`
  通过。全部进程、状态、时钟和文件写入均为 fake 或验收临时目录。
- QQ `src`/`tests` 加模块 dashboard 共 17 个 JS/MJS 文件 `node --check` 通过；7 个相关 Python 文件以
  内存 `compile()` 通过。`scripts/check_task_docs.py` 输出
  `task documentation gate passed: 28 gated task(s)`；工作树 `git diff --check` 退出 0，仅报告混合工作区
  既有 LF→CRLF 提示。
- 实际 diff 与 0.1.23/0.1.24 任务记录、manifest、package README、release fragment 和本地 README
  交叉核对一致；本轮未更改 TASKS、PK-140、公共 README、Catalog、产品源码或状态。

### 双构建、包扫描与隔离

- 在两个 Codex 专用验收目录独立构建 `qq_bridge-0.1.24.zip`：A/B 均为 `165310` bytes，SHA-256 均为
  `4bf3b0a0f74eb19d13ab2a864f3f4ab741dfe9e94ed021d52451829a280c7de5`，字节完全一致；源
  `package_source/manifest.json` SHA-256 为
  `2857094e048c7030804c9675bf0e620baeb6f548aae02b2d098e1076eab0359c`，三项均精确匹配候选声明。
- ZIP 恰好 16 项，包含新增 `sidecar/src/shutdown_control.mjs`；精确项名扫描中 `.env`、data、runtime、
  cache、node_modules、vendor、models 与绝对路径命中均为 0；内容扫描中 Windows 用户绝对路径、
  `/home/` 路径和常见 PEM/OpenSSH 私钥头命中均为 0。
- 未联网、发送、安装依赖、读取真实 `.env`/QQ data/runtime/个人数据、启动服务或执行 Git 暂存、提交、
  推送、发布、切换、清理。一次广域文件名发现触及受保护 `server/runtime/` 后被操作系统拒绝，未读到文件
  内容；另一次目录枚举仅暴露受保护目录下的文件名而未读取内容，两者均未作为验收证据，后续检查均收敛到
  显式允许路径。混合工作区其他改动完整保留。

### 本轮文档门禁

- [x] TASK_RECORD — 已记录严格身份/状态、四字段请求、watcher 逆向、同 Core 回归、构建摘要与限制。
- [x] TASKS_BOARD — 未修改；PK-900“进行中”，PK-140“待集成”。
- [ ] PUBLIC_README — 按本轮边界不更新，留给 PK-000 正式发布串行收口。
- [ ] MODULE_CATALOG — 0.1.24 尚未安装或发布，留给 PK-000。
- [x] ARCHITECTURE_DOCS — 已核对跨 Core 停止控制与当前 QQ 架构、手动生命周期约束一致。
- [x] LOCAL_README — 未输出、修改或提交任何本机私有配置。
- [x] AGENT_RULES — 保留混合工作区并遵守 fake/临时目录、外部能力、真实数据与 Git 写入边界。
- [x] VALIDATION — 独立状态/身份/请求/watcher 逆向、Node/Python 回归、静态检查、双构建、包扫描、
  文档与 diff 均通过；真实运行态与发布门槛明确留给 PK-000。

## PK-000 发布时规范化重建补充（2026-08-12）

- 本节不改变上方 `165310` bytes / `4bf3b0a0...c7de5` 的独立验收历史。总控精确暂存前运行
  `git diff --check`，只移除了 `sidecar/src/shutdown_control.mjs` 末尾多余空行，未改变已验收逻辑。
- 最终提交候选经两个系统临时目录重建均为 `165308` bytes，SHA-256
  `52767f2d81f92cf0d474ea5e0f9f7f4f4985caffb687ffa6c759e24114a936a8`；Catalog 规范 manifest
  SHA-256 为 `7c6768a2128ceedb1128969d629d12e55055c3fe54b6cb629d9b8c03835f63ed`。
- 16 项包清单与安全扫描范围不变，禁止内容命中仍为 0；后续远端 Release 与 Catalog 必须使用本节最终摘要。

## PK-241 每日生活预报消费端联动独立验收（2026-08-20）

### 结论与状态

- **不通过。** PK-110 的只读投影、默认关闭与十一项严格字段，PK-140 的默认关闭、固定 action、四个
  精确关键词及零 scheduler 主体均已成立；但 QQ 生活预报的结构化文本清洗存在一处可独立复现的凭证
  残留，违反本批“秘密不得扩散”的明确完成标准。
- PK-241 保持“待集成”，PK-900 保持“进行中”。本轮只追加验收报告，未修改产品、`TASKS.md`、
  PK-241 状态、Catalog 或其他任务文件；由 PK-000 将下述最小整改退回 PK-241 后再复验。

### 阻断证据、归属与最小整改

1. **PK-241 / PK-140 消费端 P1：`Authorization: Bearer <secret>` 会残留 Bearer 值。**
   独立直接调用正式 `createBusinessMenuController()`，让唯一固定 today Provider 返回
   `forecast.condition="Authorization: Bearer PK241_FICTIONAL_BEARER_MARKER"`，再通过固定
   `kei:life-forecast` action 格式化；实际结果为
   `天气：Authorization=[redacted] PK241_FICTIONAL_BEARER_MARKER`，断言
   `marker_leaked=true`。该虚构 marker 已进入最终 QQ markdown。
2. 根因位于 `server/qq_bridge/src/business_menu.mjs:75-83`：`safeVisible()` 先执行通用
   `authorization ... [^\s,;]+` 替换，只消费了单词 `Bearer`，随后 Bearer 专用正则已看不到
   `Bearer <secret>` 组合，因而秘密值留在输出。`safeMultiline()` 的同序替换也有相同结构风险，
   但本次确定阻断由生活预报的 `safeVisible()` 路径直接触发。
3. 最小整改归 PK-241 的 QQ 消费格式化接缝：调整清洗顺序或让 assignment 规则完整消费可选 Bearer
   scheme 与后续值，保证 `Authorization: Bearer value`、`Authorization=value`、`Token=value` 等均不
   残留；在 `server/qq_bridge/tests/business_menu.test.mjs` 增加生活预报正式 action/关键词输出的永久
   marker 逆向，断言原值、scheme 组合、城市、Provider、attribution、路径均不出现。无需修改 PK-240、
   action、关键词、API、scheduler、包边界或配置 schema。

### 已通过的独立契约与逆向检查

- PK-110：总开关关闭时 Provider 调用为 0；配置不存在时总开关及 11 项全部 false；严格 Pydantic
  模型拒绝缺字段、额外字段和整数冒充 bool。开启后每次 today 请求只捕获一次 fake Provider，按选中
  字段投影，跨天、missing/corrupted、异常 Provider 和结构异常均返回空/不可用；briefing 原缓存字节
  不变，没有 Collector、generate、refresh、conversation 或 voice 调用。
- PK-110 输出只接受 `cache_status/forecast/life_advice/fortune` 四个顶层业务字段；独立恶意快照中的
  city、Provider、attribution、时区、坐标与路径不进入投影。fortune 仅在 PK-240 `enabled=true`、日期为
  当天、免责声明精确为“娱乐内容、非事实预测”且 PK-110 `fortune=true` 时出现。
- 投影配置保存使用临时目录、唯一临时文件、flush/fsync 与原子替换；replace 失败（包括目标替换后再
  抛错）恢复旧字节，损坏/未知 schema 的 GET 全关且不改旧文件，同一正式 repository 的 8 路并发保存
  留下完整 schema 且无临时残留。额外构造两个独立 repository 实例并发写同一 Windows 路径时，部分
  调用会以有限 `life_forecast_projection_save_failed` 失败，但最终文件保持完整合法且无残留；生产装配
  每个 app 只有一个受锁 repository/service，因此此额外压力不作为本批阻断，也未掩盖结果。
- PK-140：菜单 action 固定为 `kei:life-forecast`，四个完整关键词为“每日生活预报 / 今日生活预报 /
  生活预报 / 今日天气预报”；关闭时 action 与关键词均零 API。开启时每次只调用一次固定
  `GET /api/v1/life-forecast/today`；“天气”“天气不错”“聊聊天气”“明日天气预报”“生活预报一下”均不
  被消费端截获。action 与四关键词进入同一 handler，跨日、missing 和非法结构固定降级，调用路径中无
  refresh、任意 URL/method 或 scheduler。
- QQ 配置沿用既有原子 `.env` store，只新增非秘密 `QQBOT_LIFE_FORECAST_ENABLED`，缺失默认 false；
  路由只接受真实 bool 并转发同一 facade。保存失败保持旧字节；测试全部使用临时 env，未读取真实值。

### 实际回归、构建与质量门禁

- 根 `scripts/python.ps1` 解析到当前 `.venv`，但该环境没有 pytest，故第一次正式命令以
  `No module named pytest` 退出；随后使用既有隔离 Python 3.12.7/pytest 8.3.3，不安装或修改环境：
  - PK-241、daily module/generation-status/summary-cache/installable、qq-control 合并：`36 passed`；
  - PK-240 life forecast 与 feature catalog：`18 passed`；
  - QQ configuration/installable `unittest`：`30 passed`。
- QQ Node 全量：`148 passed, 0 failed`；其中默认关闭、固定 action/关键词、宽泛天气旁路、无效快照、
  Gateway/白名单/去重/scheduler/语音等既有回归均通过。现有测试未覆盖上述
  `Authorization: Bearer <marker>` 作为生活预报结构化字段的组合，因此全绿不能覆盖独立阻断。
- 两个系统临时目录分别双构建：
  - `daily-briefing-1.0.3.zip` 两份字节一致，`145148` bytes，SHA-256
    `25335e3c51d8d7cf690a3aaf620164de6f7a11d6ca50c17a2f9ff26689636d9f`，16 项；
  - `qq_bridge-0.1.25.zip` 两份字节一致，`172002` bytes，SHA-256
    `86af63306b924ef752d6511a511b55cc5facb96c9c18c5bd86e9002a8363eb7d`，16 项；
  - 二者版本/release tag 均与 `modules-2026.08.19` 元数据一致；包内 `.env`、data/runtime、cache、
    node_modules、vendor、models、绝对路径命中均为 0。包确定性通过不消除运行时文本泄漏阻断。
- 10 个相关 Python 文件 `py_compile` 通过；daily/QQ 两个动态面板及三个相关 MJS `node --check` 通过；
  文档门禁通过 `30 gated task(s)`；范围 `git diff --check` 退出 0，仅有既有 LF→CRLF 提示。
- `test_dashboard_shell.py` 为 `5 passed, 2 failed`：一项是混合工作区未集成 learning manifest 令实际
  21 对冻结预期 20；另一项是默认测试保护钩在 import production app 时拒绝访问受保护
  `server/runtime/module-dependencies`。Python inventory 只报告另一任务未登记的
  `test_learning_module.py`。这些属于 PK-100/PK-230/共享测试隔离接缝，按用户要求不纳入 PK-241
  整改，也不用于覆盖本批确定的 QQ 脱敏阻断。

### 数据隔离与工作区排除

- 所有新增验证只使用纯内存 fake、ASGITransport、固定时钟和系统临时目录；未启动真实 QQ、Gateway、
  Core、天气、Collector、LLM、TTS 或外部服务，未联网或发送消息。
- 未读取、打印、diff、复制或修改真实生活预报缓存、daily briefing 缓存、`.env`、QQ data/runtime、
  `server/runtime` 内容、个人状态、模型或 `vendor/`；未触碰 PK-100 正在进行的模块中心实现。
- 混合工作区中的 learning、robot、PK-100、个人 `demon_slayer.json`/`focus_timer.json`、runtime、vendor
  及其他无关差异全部保留。未执行 Git 暂存、提交、推送、发布、分支切换或清理。

### 本轮文档门禁

- [x] TASK_RECORD — 本节记录范围、确定阻断、最小整改、通过项、命令结果、构建与隔离。
- [x] TASKS_BOARD — 未修改；PK-241“待集成”，PK-900“进行中”。
- [x] PUBLIC_README — 已核对当前用户可见默认关闭/只读行为；候选不通过，不做额外发布文档修改。
- [x] MODULE_CATALOG — 已核对两个候选版本与 release 元数据；共享 Catalog/发布不在本轮执行。
- [x] ARCHITECTURE_DOCS — 已核对只读 Provider、字段投影、关键词/action 与零 refresh/scheduler 边界。
- [x] LOCAL_README — 未修改或输出本机私有配置；无本机路径/端口变化。
- [x] AGENT_RULES — 遵守保护数据、混合工作区、临时目录、外部能力及 Git 边界。
- [ ] VALIDATION — 主体回归、构建和静态门禁已执行，但 QQ Bearer 值泄漏永久回归尚未关闭，故本批
  不得通过。

## PK-241 Bearer 脱敏整改后独立复验（2026-08-20）

### 结论与状态

- **通过（整改后源码与本地安装包候选）**。上一轮唯一确定阻断已关闭：生活预报最终 QQ markdown 中
  `Authorization: Bearer <value>` 不再残留 Bearer 值；固定 action 与四个精确关键词走同一只读路径，宽泛
  天气聊天继续旁路到 conversation。
- PK-241 继续保持“待集成”，PK-900 继续保持“进行中”。本轮只追加本报告，未修改产品、`TASKS.md`、
  PK-241 状态、公共 Catalog 或发布元数据；最终状态与发布仍交由 PK-000 串行决定。

### 独立逆向与差异复核

- 实际 diff 与交回范围一致：`business_menu.mjs` 的 `safeVisible()`、`safeMultiline()` 仅把 assignment
  规则收紧为完整消费可选 Bearer scheme 及其值；正式测试新增最终 QQ markdown marker 逆向；PK-241
  任务记录追加整改事实。未发现 action、关键词、PK-240 Provider、配置 schema、scheduler、Gateway、
  语音或其他业务被顺带改写。
- 不使用实现方夹具，直接构造正式 `createBusinessMenuController()`：在 condition、warning、四类 advice
  字段中分别注入虚构 Authorization Bearer、token、API key、cookie、secret 及 Windows/Unix 路径；固定
  `kei:life-forecast` 与“每日生活预报 / 今日生活预报 / 生活预报 / 今日天气预报”五条路径输出逐字一致，
  Provider 恰好调用 5 次，所有秘密及路径 marker 均消失并出现固定 `[redacted]` / `[internal-path]`。
  “天气不错”“聊聊天气”均 `handled=false`，额外 Provider 调用为 0。
- 正式永久回归 `node --test tests/business_menu.test.mjs` 为 `30 passed`，其中新增测试覆盖固定 action、四个
  关键词、Bearer、token/API key/cookie/secret、city/provider/attribution 及两类本机路径；跨天、缺失、
  损坏与结构非法快照仍 fail closed。

### 实际回归与质量门禁

- `node --test tests/*.test.mjs`：`149 passed, 0 failed`；QQ 配置/安装包
  `python -m unittest qq_bridge.tests.test_configuration_panel qq_bridge.tests.test_installable_package`：
  `30 passed`；`pytest tests/test_qq_control.py -q`：`8 passed`。
- `pytest tests/test_life_forecast_consumers.py -q`：`2 passed`；合并重跑 PK-241、daily
  module/generation-status/summary-cache/installable 与 feature catalog：`29 passed`。所有配置、Provider、
  HTTP 与时钟均为 fake/临时路径。
- `business_menu.mjs`、`bridge_core.mjs`、`index.mjs` 的 `node --check` 通过；13 个相关 Python 文件以隔离
  Python 3.12.7 和系统临时 pycache 执行 `py_compile` 通过；`scripts/check_task_docs.py` 输出
  `task documentation gate passed: 30 gated task(s)`；三处整改文件的 scoped `git diff --check` 退出 0，
  仅报告既有 LF→CRLF 提示。
- 首次误按 pytest 文件名执行 QQ configuration/installable 时，两个文件不存在并以“no tests ran”退出；
  未计入通过证据。随后依据任务登记改用上述真实 `unittest` 入口并取得 30/30，避免用错误入口冒充结果。

### 安装包候选、风险与隔离

- 因 `business_menu.mjs` 属于 QQ 包源码，未沿用修复前摘要；在两个系统临时目录重新构建
  `qq_bridge-0.1.25.zip`，两份字节一致，均为 `172030` bytes，SHA-256
  `6212581c830c5f650db6fa0c02323bde4e035e3cb289ac4fb55ed48a29cb3f11`；源 manifest SHA-256
  `84bc677cb965ce12009bba1158e5821cf54fa8f6db6269a5ca2802e41da69a27`，恰好 16 项，`.env`、data/runtime、
  cache、node_modules、vendor、models 与绝对项名命中为 0。上一轮修复前的 `172002` bytes / `86af6330…`
  只保留为历史证据，不得用于发布修复后的候选；PK-000 发布时应采用本节新摘要并完成 Catalog 串行收口。
- 未读取、打印、diff、复制或修改真实生活预报缓存、daily briefing 缓存、`.env`、QQ data/runtime、
  `server/runtime`、个人状态、模型或 `vendor/`；未启动真实 Core、QQ、Gateway、天气、Collector、LLM、
  TTS，未联网或发送消息。混合工作区的 PK-100、learning、robot、个人状态及其他任务差异均排除并保留；
  未执行 Git 暂存、提交、推送、发布、切换或清理。

### 本轮文档门禁

- [x] TASK_RECORD — 已记录整改差异、独立逆向、实际命令、回归、新包摘要、风险与隔离。
- [x] TASKS_BOARD — 未修改；PK-241“待集成”，PK-900“进行中”。
- [x] PUBLIC_README — 本轮没有新增用户契约；既有默认关闭与只读说明未被改写。
- [ ] MODULE_CATALOG — 本轮不修改共享 Catalog；修复后 QQ ZIP 新摘要交由 PK-000 发布时串行收口。
- [x] ARCHITECTURE_DOCS — 只读 Provider、精确 action/关键词、零 refresh/scheduler 边界未变。
- [x] LOCAL_README — 未读取、修改或输出本机私有配置。
- [x] AGENT_RULES — 遵守临时目录、保护数据、混合工作区、外部能力与 Git 写入边界。
- [x] VALIDATION — 原阻断独立复现已转为通过，正式 Node/Python、静态、文档、diff 与双构建门禁均有实证。

## PK-100 官方目录与本机 registry 版本归并独立验收（2026-08-20）

### 结论与状态

- **不通过。** 普通 SemVer、状态矩阵、唯一 update 路由、二次确认、批量 install 隔离、操作后双 GET
  恢复、ARIA 与移动端主体均成立；但实际源码存在两个可稳定复现的 PK-100 阻断：registry 归并没有
  严格使用 `module_id`，以及合法大整数 SemVer 与 Core 比较结果不一致。
- PK-100 保持“待集成”，PK-900 保持“进行中”。本轮只追加验收记录，未修改产品、`TASKS.md`、
  PK-100 状态、PK-230 清单、Catalog 或其他任务文件；下述最小整改应退回 PK-100。

### 阻断证据、责任与最小整改

1. **P1 — registry 关联错误地优先使用 `key`，违反以 `module_id` 精确归并。**
   `server/static/dashboard/module-management.js:193-195` 的 `moduleId()` 返回
   `key || module_id`，`reconcileOfficialModules()` 又在约第 330 行用该结果建立 `installedById`。
   独立构造官方 `module_id=alpha` 与本机记录 `key=wrong,module_id=alpha`，正式归并结果为
   `install`，错误展示“下载并安装”；反向构造 `key=alpha,module_id=beta`，结果为 `installed`，把另一个
   module_id 误当作已安装。两例均不涉及名称、label、文件名或真实 registry。
2. **P1 — JavaScript `Number` 破坏 Core 支持的任意精度版本顺序。**
   `parseControlledSemver()` 在约第 162 行把三段主版本转为 `Number`，数值 prerelease 也在约第 187 行
   用 `Number()` 比较；Core `server/core/modules/manifest.py:195-224` 使用 Python 任意精度整数。
   对合法输入 `9007199254740992.0.0` 与 `9007199254740993.0.0`，Core 返回 `-1`、前端返回 `0`；对
   `1.0.0-9007199254740992` 与 `1.0.0-9007199254740993`，Core 返回 `-1`、前端返回 `1`。因此本机旧版
   可能被误判为同版或较新，导致合法 update 按钮缺失，不能声称与 Core `compare_semver()` 一致。
3. 最小整改仅限 PK-100 的前端归并和永久测试：`reconcileOfficialModules()` 建表时只接受 registry
   记录的精确、非空 `module_id`，不得用 `key`/name/label 回退；同 ID 的冲突记录应 fail closed。
   数字段使用 `BigInt` 或十进制字符串长度/字典序实现 Core 同序比较，数值 prerelease 同样不得经过
   `Number`。增加上述四个正反夹具，并保留普通 `1.0.0`、prerelease、build metadata 与非法版本用例。
   不需修改 PK-010 API、Core SemVer、Catalog、PK-230 或生命周期后端。

### 已通过的独立契约与逆向

- 普通版本矩阵独立通过：`1.0.0 == 1.0.0`、`alpha < release`、数值 prerelease `2 < 10`、数字标识符
  小于字符串标识符、字符串字典序、build metadata 不改变优先级；`1.0`、前导零主版本、空 build、`v`
  前缀均抛错。普通状态矩阵中未安装/install、同版/installed、本机旧版/update、本机新版/local_newer、
  不兼容/incompatible、local_import/source_conflict、多官方版本唯一最高 update 和“更高版本不兼容但
  较低兼容版本可更新”均得到预期结果。
- 更新请求独立确认唯一为
  `POST /api/v1/modules/old/update-official`，body 精确为
  `{"version":"1.1.0","confirmation":"old@1.1.0"}`；未走 install-official。批量计划只包含真正
  未安装项，同版项被排除；普通页面、版本比较、选择和确认弹窗前均未产生 POST。
- 源码核对 `runOfficialOperation()`：成功后按顺序先 GET `/api/v1/modules`，再 GET
  `/api/v1/modules/official-catalog`；两个失败分支均经 `finally/recoverOfficialModuleState()` 离开 busy
  状态。HTML/JS 正式专项覆盖成功收敛与二次 GET 失败恢复并通过。

### Browser fake、回归与共享门禁

- 按 Browser 技能启动纯 fake FastAPI 预览（首次 8765 已被其他本机进程占用，未探测或终止该进程；
  改用 18765/18766），未连接真实 Core/registry/GitHub。模块中心展开后，同版卡为禁用“已安装”，未安装
  卡为“下载并安装”；批量依赖缺失明确显示“未发送任何安装请求”。选择合法单项后确认按钮自动聚焦，
  dialog 具有 `aria-labelledby/aria-describedby`，Escape 关闭；375px viewport 下
  `window.innerWidth=375`、`clientWidth=scrollWidth=360`，无横向溢出。fake audit 中 POST 为 0。
- 批量切换与确认控件均为原生 button/checkbox，ARIA 状态和焦点可见。in-app Browser 的 locator 与
  DOM 键盘注入在 `activeElement` 已为 toggle 时仍未触发浏览器原生 Enter/Space 默认动作，因此本环境
  只确认了原生语义、焦点、ARIA 与 Escape，未把该输入注入限制冒充完整键盘激活实证；现有正式 JS
  契约测试通过。该限制不覆盖上方两个确定产品阻断。
- `check_html_contract()` 与 `check_javascript_contract()` 通过；完整
  `test_dashboard_shell.py` 在 `check_manifest_inventory()` 精确停止。独立重算为实际 21、冻结
  `INSTALLABLE_MODULE_IDS` 20，唯一额外项 `learning`、缺失 0，确认归属 PK-230/共享清单；未越权修改。
- `pytest tests/test_official_module_catalog.py tests/test_installable_modules.py -q`：`22 passed`；
  `module-management.js` `node --check` 通过；Dashboard/Core 三个 Python 文件以系统临时 pycache
  `py_compile` 通过；`scripts/check_task_docs.py` 输出 `30 gated task(s)`；PK-100 五文件 scoped
  `git diff --check` 退出 0，仅有 LF→CRLF 提示。
- 两次以 `importlib` 单独调用 Dashboard 检查时，首次因未把 `server/tests` 加入 `sys.path` 而在导入
  `_path_setup` 前失败，未计作产品结果；修正为测试脚本真实搜索路径后 HTML/JS 通过、manifest 按上述
  PK-230 差异失败，证据未被掩盖。

### 数据隔离与文档门禁

- 未读取、打印、diff、复制或修改真实 registry、`server/runtime`、个人状态、缓存、`.env`、秘密、模型
  或 `vendor/`；未安装/更新真实模块，未访问 GitHub，未启动真实 Core 或业务服务。fake 预览已正常停止，
  临时浏览器 viewport 已恢复、测试页已关闭；未执行 Git 暂存、提交、推送、发布、切换或清理。
- [x] TASK_RECORD — 本节记录两个阻断、通过项、Browser 限制、共享门禁、命令与隔离。
- [x] TASKS_BOARD — 未修改；PK-100“待集成”，PK-900“进行中”。
- [x] PUBLIC_README — 本轮只验收现有契约，未修改用户行为或公开文档。
- [x] MODULE_CATALOG — 未读取远端或修改 Catalog；只使用内存 fake 条目。
- [x] ARCHITECTURE_DOCS — 已对照 PK-010/Core SemVer 与官方生命周期边界，未改变架构。
- [x] LOCAL_README — 未修改或输出本机私有配置。
- [x] AGENT_RULES — 遵守保护数据、混合工作区、Browser、本地 fake 与 Git 边界。
- [ ] VALIDATION — 普通矩阵与门禁已执行，但 module_id 精确关联和任意精度 SemVer 两项未通过。

## PK-100 两项 P1 整改后聚焦独立复验（2026-08-20）

### 结论与状态

- **不通过。** 上轮两个直接错误已关闭：官方归并已严格使用 registry `module_id`，大整数 SemVer 已与
  Core 正反序一致且 BigInt 缺失时 fail closed；但同一 module_id 的冲突结果仍保留“第一条”记录，产生
  明确输入顺序依赖。此外 PK-100 Browser preview 未同步 `module_id`，本轮实际页面无法复现任务记录
  声称的同版“已安装”卡。
- PK-100 保持“待集成”，PK-900 保持“进行中”。本轮未修改产品、`TASKS.md`、PK-100、PK-230 或
  Catalog；以下两项最小整改继续归 PK-100。

### 已关闭的原始阻断

- 独立正式归并得到：官方 alpha + `key=wrong,module_id=alpha` 为 `installed`；
  `key=alpha,module_id=beta` 不误关联，官方 alpha 为 `install`。空值、`Alpha`、`alpha/evil`、null 和
  缺失 module_id 均不借助 key/name/label 回退，alpha 保持 `install`；单条合法 alpha 为 `installed`。
  旧生命周期 `allowedLifecycleActions()` 仍可使用 legacy key，兼容路径未被严格归并改写。
- SemVer 独立交叉结果与 Core 完全一致：大整数主版本正反序 `-1/1`，大整数数值 prerelease 正反序
  `-1/1`，不同 build metadata 为 `0`；普通 prerelease、数字/字符串标识符规则继续通过。主版本任一段
  前导零、缺段、`v` 前缀与空 build 均抛错；临时把 `globalThis.BigInt` 设为 undefined 时比较直接抛错，
  未回退 `Number/parseInt`。

### 剩余阻断、证据与最小整改

1. **P1 — duplicate registry conflict 的完整结果仍依赖输入顺序。**
   `indexInstalledRegistry()` 在 `server/static/dashboard/module-management.js:332-345` 标记 conflict，
   但仍把第一条合法记录保存到 `records`；`reconcileOfficialModules()` 最终在约第 445 行把该记录作为
   `local_module` 返回。用同 ID 的 `first@1.0.0` 与 `second@0.9.0` 正反排列，两边状态均为
   `registry_conflict` 且 batch 均以 `batch_selection_stale` 拒绝，零 install/update；但正序返回并展示
   `local_module=first@1.0.0`，反序返回 `second@0.9.0`，`full_equal=false`。这违反本轮“正反输入结果应
   一致”，并让冲突卡的“本机版本”随 registry 顺序变化。
   **最小修复：** conflict ID 不得向归并结果暴露任一候选记录；冲突时 `local_module` 固定为 null（或固定
   的无候选冲突摘要），并在计算版本/来源/action 前短路。永久测试必须使用不同 key/版本的两条记录，
   对完整公开结果做正反序等价断言，而不是继续使用两条完全相同的 fixture。
2. **P1 验收夹具 — Browser preview 不符合严格 registry 契约。**
   `server/tests/test_dashboard_shell.py:810` 的 `_module_record()` 只返回 `key`，不返回 `module_id`。
   严格归并正确忽略这些记录，故本轮真实 Browser fake 中 `sameDisabled=false`：没有任何禁用“已安装”官方
   卡，尽管任务记录声称同版卡已验证；仍有未安装按钮，但无法验收“普通合法单条不会误判”。生产
   ModuleManager `_describe()` 确实返回 `module_id`，所以不得回退产品到 key。
   **最小修复：** 仅让 preview 的 managed registry fixture 返回与生产 API 一致的精确 `module_id`，并
   增加 Browser/DOM 断言同版卡禁用、批量排除；不修改 PK-010 API、生产归并或 PK-230 清单。

### 其余矩阵、Browser 与质量门禁

- 未安装/同版/可更新/本机较新/不兼容/非官方来源/多版本唯一目标/更高不兼容且较低兼容矩阵全部通过；
  update 唯一调用 `/api/v1/modules/older/update-official`，确认体精确；批量只包含 fresh install，冲突项
  无法进入计划；恢复状态机通过。`check_html_contract()` 与 `check_javascript_contract()` 通过。
- Browser 技能仅连接 18768 fake preview：375px 下 `clientWidth=scrollWidth=360`，零横向溢出；批量
  dialog 正确 `aria-labelledby/aria-describedby`、确认按钮自动聚焦、Escape 关闭；页面加载、展开、选择、
  打开/取消确认后 fake audit `post_count=0`，未访问 GitHub。上述同版卡缺失证据来自实际 DOM，不接受
  实现方旧结论。fake 服务已停止，viewport 已恢复，临时 tab 已关闭。
- Core/API 回归 `22 passed`；`module-management.js` `node --check`、三个相关 Python 文件临时 pycache
  `py_compile`、30 项文档门禁、三文件 scoped `git diff --check` 均通过。
- 完整 `test_dashboard_shell.py` 仍精确停止在 manifest inventory；独立重算 actual 21 / expected 20，
  unexpected 仅 `learning`、missing 0，继续归属 PK-230/共享清单，未让 PK-100 越权修改。

### 隔离与文档门禁

- 所有归并、版本、API 和 Browser 检查使用内存 fake、隔离解释器或本机临时预览；未读取/打印/diff
  真实 GitHub、registry、`server/runtime`、个人状态、缓存、秘密、模型或 vendor，未安装/更新真实模块，
  未执行 Git 暂存、提交、推送、发布、切换或清理。
- [x] TASK_RECORD — 本节记录原阻断关闭证据、两项剩余阻断、Browser、命令与隔离。
- [x] TASKS_BOARD — 未修改；PK-100“待集成”，PK-900“进行中”。
- [x] PUBLIC_README — 本轮未改变用户契约或文档。
- [x] MODULE_CATALOG — 未访问远端或修改 Catalog。
- [x] ARCHITECTURE_DOCS — 未改变 PK-010/Core 生命周期或数据所有权。
- [x] LOCAL_README — 未修改或输出本机私有配置。
- [x] AGENT_RULES — 遵守混合工作区、保护数据、Browser、本地 fake 与 Git 边界。
- [ ] VALIDATION — 原两项直接夹具通过，但 duplicate 顺序独立性和生产等价 Browser fixture 尚未关闭。

## PK-100 第二次最小收口后聚焦独立复验（2026-08-20）

### 结论与状态

- **通过（本次 PK-100 累计候选的第二次最小收口）。** 上轮两个剩余 P1 均已关闭：重复
  `module_id` 的冲突结果不再暴露任一候选记录且与输入顺序无关；Dashboard preview 的 managed
  registry 记录已显式提供生产契约 `module_id`，实际 Browser fake 中同版卡正确收敛为“已安装”。
- PK-100 继续保持“待集成”，PK-900 继续保持“进行中”，交由 PK-000 做最终关闭。本轮未修改
  `TASKS.md`、PK-100、PK-230、产品代码、Catalog 或公开文档。

### 冲突确定性、身份与版本逆向

- 使用与正式夹具不同的两条 alpha 记录独立重放：两条均为 `module_id=alpha`，但 key 分别为
  `first-key`/`second-key`、版本为 `8.8.8`/`7.7.7`、label 与 package source 也各不相同。正反顺序的
  `reconcileOfficialModules()` 完整公开结果 `deepEqual`；两边均为 `registry_conflict`、
  `local_module=null`，序列化结果不含任一候选 key/version/label/source。两个顺序的 batch plan 均以
  `batch_selection_stale` 拒绝，零 install/update、零批量候选。单条合法 alpha（即使 key 不同）仍为
  `installed`，未被误判冲突。
- `key=wrong,module_id=alpha` 正确关联；`key=alpha,module_id=beta` 不误关联；空、大小写错误及 traversal
  形式的 module_id 均被忽略且不回退 key/name/label。正式 preview `_module_record()` 已显式返回
  `module_id`，产品未恢复 key fallback，旧生命周期卡仍可继续使用自己的 key。
- 任意精度 SemVer 独立复验通过：超大主版本与超大数值 prerelease 正反序均为 `-1/1`，build metadata
  相等，主版本三段前导零、缺段和 `v` 前缀 fail closed；移除 `BigInt` 后直接拒绝，未回退
  `Number/parseInt`。`1.0.0-01` 由冻结 Core `compare_semver` 本身接受，Dashboard 与 Core 行为一致；本批
  没有让 PK-100 单方面改写共享版本规则。
- 未安装/同版/可更新/本机较新/更高不兼容/非官方来源/同 ID 多官方版本唯一目标矩阵通过；update
  只发 `/api/v1/modules/{id}/update-official`。源码中的成功路径依次重新 GET `/api/v1/modules` 和本机
  `/api/v1/modules/official-catalog`，两次读取任一失败均由 `finally`/恢复状态机解除 blocking phase，
  `check_javascript_contract()` 的累计状态、请求和恢复夹具通过。

### Browser fake 与零副作用

- 仅在临时 fake preview `127.0.0.1:18779`、375×812 viewport 复验。Bilibili 1.0.0 显示“已安装”且
  按钮 disabled，批量模式中对应 checkbox 数为 0；Conversation 1.0.0 显示“下载并安装”且恰有一个
  checkbox。页面 `innerWidth=375`、document scroll width=360，无横向溢出。
- 页面加载、展开模块中心、进入批量、选择 Conversation、打开确认框及 Escape 取消期间，audit 中
  POST 为 0；模块中心业务状态仅读取 `/api/v1/modules` 与 `/api/v1/modules/official-catalog`，未访问
  GitHub。确认框具有精确 `aria-labelledby=official-module-batch-confirmation-heading` 和
  `aria-describedby=official-module-batch-summary`，确认按钮自动聚焦；Escape 关闭后焦点恢复到“安装已选”。
  fake 服务已停止、临时 tab 已关闭、viewport 已 reset。

### 实际命令与结果

- 独立内存 Node 逆向脚本：冲突正反深度相等、候选字段不泄漏、单条关联、identity 交叉、SemVer、
  状态矩阵、batch 拒绝与唯一 update route 全部通过。
- 隔离 Python 调用 `check_html_contract()`、`check_javascript_contract()`：通过；
  `node --check server/static/dashboard/module-management.js`：通过；相关 `py_compile`：通过。
- `python -m pytest server/tests/test_official_module_catalog.py server/tests/test_installable_modules.py -q`：
  **22 passed**。
- 完整 `server/tests/test_dashboard_shell.py` 仍只停止在共享 manifest inventory。独立重算为 actual 21 /
  expected 20，unexpected 仅 `learning`、missing 0，精确归属 PK-230/共享清单；未让 PK-100 越权修改。
- `scripts/check_task_docs.py`：`30 gated task(s)` 通过；三文件 scoped `git diff --check`：退出 0，仅
  LF→CRLF 提示。

### 隔离与八项门禁

- 全部验证使用内存 fake、临时 preview 与既有隔离解释器；未读取、打印、diff、复制或修改真实 GitHub、
  registry、`server/runtime`、个人状态、缓存、秘密、模型或 `vendor/`，未安装/更新真实模块，未执行 Git
  暂存、提交、推送、发布、切换或清理。
- [x] TASK_RECORD — 本节追加本轮结论、逆向、Browser、命令、共享门禁与隔离证据。
- [x] TASKS_BOARD — 未修改；PK-100“待集成”，PK-900“进行中”。
- [x] PUBLIC_README — 本轮未改变用户契约或公开说明。
- [x] MODULE_CATALOG — 未访问远端或修改 Catalog。
- [x] ARCHITECTURE_DOCS — 保持 PK-010/Core 身份、SemVer 与生命周期边界。
- [x] LOCAL_README — 未修改或输出本机私有配置。
- [x] AGENT_RULES — 遵守保护数据、混合工作区、Browser、fake 与 Git 边界。
- [x] VALIDATION — 本批要求的冲突、身份、版本、状态矩阵、Browser、静态、回归、文档和 diff 门禁已完成；
  PK-230 的 21/20 共享 inventory 冲突单独记录，不作为 PK-100 阻断。

## PK-240 每日生活预报源码候选独立验收（2026-08-20）

### 结论与状态

- **通过（源码候选范围）。** 独立源码审计与 17 项离线专项未发现 PK-240 产品阻断：普通 config/today
  读取不调用 Provider，只有显式 refresh 进入固定 Open-Meteo Provider；跨日、损坏缓存、并发合并、上游失败
  及原子替换失败均 fail closed 并保留旧数据。PK-240 继续保持“待集成”，PK-900 继续“进行中”，交由
  PK-000 做共享 Catalog、真实安装运行态与最终状态收口。

### 独立证据

- 完整阅读 PK-240 任务、每日生活预报架构、manifest、repository/service/provider/router/module、确定性 builder、
  dashboard entrypoint、release fragment/entry 与实际差异。Provider 只接收清空 city/fortune 的坐标视图，固定
  `api.open-meteo.com` 与 `air-quality-api.open-meteo.com`，关闭重定向及环境代理；响应只保留经范围、单位、
  日期、时区和天气码校验的规范化数值，有限错误码不携带上游正文。
- `python -m pytest -c NUL server/tests/test_life_forecast_module.py -q` 使用系统临时 cache/basetemp：
  **17 passed in 0.73s**。覆盖普通读取零网络、显式 refresh、跨日不复用、损坏缓存不修写、Provider/缓存不含
  city/坐标、MockTransport 单位规范化、超时/429/5xx/恶意时区、AQI 降级、非法坐标、原子保存失败保旧、
  并发 refresh 单次采集、DST、本地确定性娱乐提示、dashboard 无直接 fetch，以及双次确定性 ZIP。
- 包测试在两个系统临时目录逐字节构建，并用受跟踪 release entry 反向断言最终 ZIP 大小 **43495 bytes**、
  SHA-256 `b1f981a23e6fca2dcb4cd056c47ef25c9aa3d03a61111fe4a3a498b45eeb3a99`、manifest SHA-256
  `ef3673c9f973c9b231c41ed03649e7e046a0c07f67dc61c7431860c07336986c`；manifest 为可选 in-process、
  固定 backend/dashboard entrypoint、独立 `life_forecast` 数据命名空间，包扫描排除 config/cache/runtime/
  vendor/`.env`。动态面板只经 `context.request` 读取 config/today，保存与 refresh 均为显式按钮动作。

### 限制、隔离与门禁

- 根项目 `.venv` 缺 pytest，故未冒充正式锁环境；改用已存在且具备 pytest/httpx 的系统 Python 运行同一离线
  专项。收到停止长耗时测试指示后，没有继续执行完整全仓 pytest/ruff，也没有再次独立跑临时 ModuleManager
  安装/启用/重启装载/停用/卸载 smoke；本轮对生命周期的结论来自 manifest/module/loader 接缝静态复核及
  专项中的包内容验证，真实本机安装运行态仍保留给 PK-000 后续串行窗口，不据此提前标记“已完成”。
- 未读取、打印、diff 或修改真实生活预报数据、`.env`、位置、缓存、个人状态、`server/runtime`、模型或
  `vendor/`；未联网、未安装真实模块、未执行 Git 暂存/提交/推送/发布/切换/清理。被中断的额外临时构建
  未产出文件，也未写入仓库。
- [x] TASK_RECORD — 本节记录结论、独立测试、包摘要、限制和隔离。
- [x] TASKS_BOARD — 未修改；PK-240“待集成”，PK-900“进行中”。
- [x] PUBLIC_README — 本轮只读核对，未修改。
- [x] MODULE_CATALOG — 仅核对 PK-240 release entry，未合并或发布。
- [x] ARCHITECTURE_DOCS — 已核对 WeatherProvider、缓存和显式联网边界。
- [x] LOCAL_README — 未修改或输出本机私有配置。
- [x] AGENT_RULES — 遵守临时目录、保护数据、混合工作区与 Git 边界。
- [x] VALIDATION — 17 项专项及源码/包契约通过；完整锁环境与真实安装运行态限制已透明保留给总控。

## PK-240 每日生活预报最终运行态复核（2026-08-20）

### 结论与状态

- **通过。** PK-000 已补齐源码候选报告保留的正式本机生命周期和浏览器装载门禁：通过 ModuleManager
  安装并启用 `life_forecast@1.0.0`，由受控 supervisor 重启 Core，未直接编辑 registry/runtime。
- `GET /api/v1/modules` 返回 `life_forecast` 的 `installed_version=1.0.0`、`enabled=true`、
  `install_status=enabled`；模块 dashboard asset 与只读 today API 均返回 200。
- 真实 dashboard 中“每日生活预报”卡片可见且可展开，配置控件、三个结果分区和显式刷新入口完整装载；
  初始 provider disabled、cache missing，不会因页面加载或展开联网。
- PK-240 由 PK-000 最终标记“已完成”。PK-900 仍保持“进行中”，因为其总任务文件还承载其他未关闭批次；
  本节只关闭 PK-240 子批次，不改变其他任务状态。

### 隔离与发布边界

- 本轮没有保存位置配置、点击刷新或访问天气上游；没有读取/输出 `.env`、位置、缓存、个人状态、模型、
  `vendor/` 或其他混合工作区内容。
- 官方不可变 Release asset 和远程 Catalog 尚未发布；本地正式安装通过不等同于远程一键安装已上线。
- 未执行 Git 暂存、提交、推送、发布、切分支或工作区清理。

## PK-241 QQ 生活预报显式刷新独立聚焦验收（2026-08-20）

### 结论与状态

- **通过（源码候选聚焦验收）。** 未发现阻断。PK-241 继续保持“待集成”，PK-900 继续“进行中”；本节不修改
  `TASKS.md` 或任务状态。
- 固定菜单 action `kei:life-forecast` 在总开关开启时只调用一次
  `POST /api/v1/life-forecast/refresh`，并直接格式化本次响应；不先读 today、不二次刷新、不回退旧缓存。
- 四个精确关键词“每日生活预报”“今日生活预报”“生活预报”“今日天气预报”仍各只调用一次
  `GET /api/v1/life-forecast/today`，不会调用 refresh。
- 页面/菜单加载、总开关关闭以及“天气”等宽泛普通聊天均为零 refresh；同一个 interaction 的重复投递至多产生一次
  refresh 和一次回复。
- refresh 失败时只返回固定、脱敏的失败提示，零重试、零 today fallback、零旧缓存展示。

### 独立反向验证

- 独立执行 `node --test tests/business_menu.test.mjs`：**32/32 通过**。覆盖菜单 action 单次 POST、四关键词
  单次 GET、开关关闭零 API、宽泛天气旁路、refresh 失败不回退、重复 interaction 去重和结果格式化。
- 注入 Bearer/token/API key/Cookie/Secret、城市、Provider、attribution、Windows/Unix 路径等虚构 marker；最终
  QQ markdown 均未出现原值，上游错误正文亦未透出。
- 独立执行全部 bridge Node 测试：**151/151 通过**；执行
  `python -m unittest -q qq_bridge.tests.test_installable_package qq_bridge.tests.test_configuration_panel`：
  **30/30 通过**。
- 所有 HTTP/QQ/天气调用均为 fake；没有启动 Gateway、真实 QQ、天气 Provider 或外部网络。

### 候选包与隔离

- 两个系统临时目录确定性构建 `qq_bridge-0.1.26.zip` 字节一致：**172429 bytes**，SHA-256
  `9ab9c65ab25e7c357338f4654f3d46f383bb5f34d8179aa19c703ae89c5f8ae0`。
- 源 manifest SHA-256 为
  `2d5e4ff59cd2684efb4c1a82c157a74c731e89b1ccddfe7f01c999814e13de2f`；包内文件严格为预期 **16 项**，
  禁止路径分段命中 **0**，真实秘密 marker 命中 **0**。README/schema/lockfile 中对 `.env` 或
  `node_modules` 的说明文字不属于打包路径或秘密值，未误报为发布资产。
- 未读取或修改真实 `.env`、QQ data、生活预报缓存、`server/runtime`、个人状态或 `vendor/`；未安装真实模块，
  未执行 Git 暂存、提交、推送、发布或清理。

### 完成文档门禁

- [x] TASK_RECORD — 本节记录结论、次数边界、失败行为、脱敏、包摘要和隔离证据。
- [x] TASKS_BOARD — 未修改；PK-241“待集成”，PK-900“进行中”。
- [x] PUBLIC_README — 本轮未修改。
- [x] MODULE_CATALOG — 仅核对候选包和 release 元数据，未合并或发布。
- [x] ARCHITECTURE_DOCS — 未改变 PK-240/PK-110/PK-140 已冻结契约。
- [x] LOCAL_README — 未读取或输出本机私有配置。
- [x] AGENT_RULES — 遵守受保护数据、临时目录、混合工作区和 Git 边界。
- [x] VALIDATION — 聚焦 32/32、Node 151/151、Python 30/30 与确定性包检查通过。
