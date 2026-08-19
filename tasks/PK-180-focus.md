# PK-180 — 专注计时与首个可安装模块试点

- 状态：待集成
- 优先级：P1
- 所属模块：`focus`
- 依赖任务：PK-001、PK-010、PK-100
- 负责路径：`server/systems/focus_timer.py` 的兼容接缝、`server/features/focus/`、focus manifest/本地包源码、`/focus/*`、`/api/v1/focus`、focus 动态面板与隔离测试；共享装配/目录/文档只做必要的 focus 接入
- 当前对话：2026-07-30 由 PK-000 重新打开“首个官方可安装模块发布”增量；本对话只冻结 focus 1.1.0 的完全确定性 ZIP、官方 release fragment/Catalog v1 条目、隔离生命周期证据和发布交接，不修改 PK-010 下载器、PK-100 UI、TASKS.md 或 GitHub Release

## 入场授权

- PK-001、PK-010、PK-100 均为“已完成”，上一批 `PK-010 + PK-100` 的 PK-900 也已最终通过；PK-180 的形式依赖全部满足。
- PK-900 是上一批基础设施的验收证据，不新增为 PK-180 的形式依赖。PK-180 当前从“待开始”进入“进行中”，但尚未实现、尚未验收，更不得标记“已完成”。
- 本任务是第一个真实可安装业务模块试点：必须用实际 focus 后端、manifest 和动态面板补齐此前仅由合成夹具覆盖的 manifest → 安装 → 启用 → catalog → 资产 → `mount(context)` → 停用/卸载/重装接缝。

## 目标

把专注模式、番茄钟、状态恢复和结束逻辑迁入独立功能模块，并作为第一个端到端可安装模块验证 manifest、装配、动态面板和数据保留协议。

## 不在本任务内

- 不迁移或重构健身、日历、斩妖、好感度、每日情报、QQ、对话、语音等其他业务模块，也不借机整理它们的控制台代码或数据。
- 不改变 PK-010 的 manifest、注册表、生命周期、Core 保留 ID/namespace、模块资产或本机写接口契约；不改变 PK-100 的公共 `mount(context)`、请求、通知、过滤或失败隔离契约。若现有契约确实不足，先在本任务记录精确接口需求并停止跨模块扩张，交 PK-000 确认后再继续。
- 不开发远程模块商店、自动下载/更新、签名发布、第三方 SDK、通用生命周期控制台按钮、配置对话框或无重启路由卸载。
- 不新增常驻进程或端口；focus 必须保持 `in_process` 模块。
- 不执行 Git 暂存、提交、推送、PR、工作区清理，也不触碰 `vendor/` 或无关用户修改。

## 允许修改的边界

- `server/features/focus/`：新增并拥有 focus 的 `models/router/service/repository`、应用装配入口、manifest/本地包源码和包内 `dashboard/` 资源。跟踪的包源码必须可审阅；安装产物只能写入测试临时目录或被忽略的 runtime，不能把运行产物当源码提交。
- `server/systems/focus_timer.py`：只允许作为渐进迁移的兼容层或复用入口；业务规则最终只能有一份，旧调用与新 router 必须委托同一个 focus service/repository，不能维护两套状态机。
- `server/api.py`：只允许最小化移除旧 focus 业务实现并接入共享装配/兼容入口；不得重构其他路由或公共应用结构。
- `server/static/dashboard.html`：只允许移除或桥接旧 focus 面板逻辑，避免与动态模块面板重复；不得改写其他业务面板。实际 focus UI 必须由包内 ES module `mount(context)` 提供。
- `server/features/catalog/`：只允许把 focus 的实际状态、接口、入口与迁移状态同步到现有目录契约；不得新增公共字段或改变其他模块条目。
- `server/tests/test_focus_timer.py` 及新的 focus 专项/集成测试：只能使用注入的临时状态和临时 ModuleManager 根目录。README、架构文档、`TASKS.md` 和本任务文件仅按完成门禁同步实际结果。

## 接口契约

- 新接口：`GET /api/v1/focus/status`、`POST /api/v1/focus/start`、`POST /api/v1/focus/stop`、`POST /api/v1/focus/reset`。
- 兼容接口：现有 `GET /focus/status`、`POST /focus/start`、`POST /focus/stop`、`POST /focus/reset` 保持请求、响应、错误和恢复语义，并委托同一个 service；不复制第二套业务逻辑。
- manifest：稳定 ID 为 `focus`，类型为可选 `in_process`，`required=false`，声明 `/api/v1/focus`、现有 `/focus/*` legacy endpoints、`dashboard/index.js`、`local_state` 最小权限和实际重启要求；字段必须通过 PK-010 正式 Schema。
- 装配语义：安装默认进入 `installed_disabled`；启用后按 PK-010 契约在 API 重启时装配新旧路由和动态面板。停用或卸载后不得继续装配模块入口；第一版不要求热移除已经注册的 FastAPI 路由，必须以重启后的应用状态验收。
- 控制台：仅当目录返回 `enabled === true` 且存在可信 `dashboard_entrypoint` 时加载 focus 面板；面板只能通过 `context.request` 调用 `/api/v1/focus` 或声明的 `/focus/*`，不能访问文件、注册表或其他模块 DOM。

## 数据所有权

- `server/data/focus_timer.json`，属于用户个人状态。
- 第一阶段继续兼容现有路径；不得为了开发或测试读取后打印、移动、重置、清除、覆盖、格式化、重写或打入安装包。仓库中若存在其他同名历史 focus 状态路径，也按相同敏感等级处理。
- 所有自动测试必须给 repository 显式注入系统临时目录中的独立状态文件；不得以真实 `server/data/focus_timer.json`、真实 `server/data/module_registry.json`、真实 `server/runtime/modules/` 或真实 `server/data/modules/` 补足覆盖。
- 卸载 focus 程序默认保留既有用户状态；重新安装并启用后应在不迁移、不改写真实文件的前提下重新关联。清除数据不在本轮自动验收操作内，禁止为了证明 purge 语义触碰真实状态。

## 生命周期与隔离验证

- 使用实际 focus 包源码而非合成空夹具，在临时 ModuleManager 根目录验证 SHA-256、安装、启用、停用、卸载、重新安装和目录状态。
- 分别构造重启后的应用装配：启用时新旧 API 与模块资产可发现；停用/卸载时 focus dashboard 入口不加载，模块路由不再装配；不得把运行中旧路由仍存在误判为热卸载失败。
- 使用临时 focus 状态验证进行中计时恢复、重复启动保护、停止/重置、卸载保留和重装恢复；测试内容必须去标识化，失败日志不得输出真实用户状态。
- 同时验证无 focus 可选模块时 Core、目录和公共控制台仍可启动，focus 失败不能影响其他模块或公共外壳。

## 验收标准

- API 重启后的计时恢复、重复启动保护和结束状态保持兼容。
- 实际 focus 包通过正式 manifest 校验；安装并启用、再重启装配后，新旧接口和动态控制台面板可用。
- 停用或卸载并按契约重启后，不加载 focus 面板或 focus 路由；无 focus 时 Core 与其他模块继续可用。
- 卸载默认保留隔离状态，重新安装并启用后能够恢复关联；完整过程不访问或覆盖真实计时状态。
- 模块目录、README、架构说明、任务记录和实际接口一致；focus 状态、manifest、包内容、前端 context 与其他模块数据所有权均通过隔离审计。
- focus 专项测试、PK-010 生命周期回归、PK-100/dashboard 回归、catalog/API 装配、Python/JavaScript 语法、文档门禁和 `git diff --check` 全部通过。

## 最终交给 PK-900 的内容

- 可审阅、可重建的真实 focus 本地包及 SHA-256 计算方式；manifest 字段、包内容清单和包内不含个人状态/凭证的证据。
- 新旧 API 矩阵、启用/停用/卸载的重启语义、动态面板 `mount(context)` 接入和 catalog 字段对照。
- 使用临时 registry/runtime/data/focus 状态完成的安装 → 启用 → 重启装配 → 停用 → 重启隔离 → 卸载保留 → 重装恢复报告，含失败路径和无真实数据副作用说明。
- PK-010、PK-100 与 Core 无回归测试结果，以及 README、模块目录、架构文档、任务八项门禁和工作区差异检查。
- 明确列出未覆盖项和任何公共契约需求。PK-180 完成实现后只能进入“待集成”；由 PK-000 另行登记新的 PK-900 批次并在验收报告后决定最终状态。

## 工作记录

- 2026-07-30：PK-000 重新打开 PK-180 官方发布增量。目的为在系统临时目录构建并冻结首个官方 focus 模块资产，向 PK-010 提供可信 GitHub Catalog v1 可合并条目和构建命令，向 PK-100 提供名称、说明、权限、数据保留与重启提示；不创建或上传 GitHub Release，不修改下载器/控制台公共契约，不读取或操作真实 focus 状态。
- 2026-07-30：冻结官方候选为 `focus 1.1.0`、tag `module-focus-v1.1.0`、asset `focus-1.1.0.zip`。本机只读检查确认 Git tag 与 GitHub Releases 均不存在同名 tag/asset；仓库当前唯一已有 release 为无关的 `moudle` 预发布及 `kei-voice-pack-1.0.0.zip`，因此没有覆盖既有发布。
- 2026-07-30：将 ZIP 构建冻结为无压缩 `ZIP_STORED`，统一 UTF-8/LF，固定文件顺序、时间、权限、平台、ZIP 版本、extra/comment，并锁定精确文件白名单；由同一源码在两个隔离目录生成的 ZIP 字节完全一致。发布 ZIP 只生成在系统临时目录，不写入仓库或真实 runtime。
- 2026-07-30：新增 PK-010 Catalog v1 的预发布 fragment 与完整可合并条目。固定官方来源为 `songshu-yu/Cyber-Girlfriend`，完整条目由 PK-010 正式 builder 从 fragment 和临时资产计算，不接受用户任意 owner/repo/URL；未改变 PK-010 manifest 或 Catalog 公共契约。
- 2026-07-30：未把 calendar、fitness、demon 或其他内置 feature 声明为发布包；未修改 PK-010 下载器、PK-100 UI、官方 bundled catalog、TASKS.md、GitHub Release 或 PR，也未执行 Git 暂存、提交、推送或工作区清理。
- 2026-07-21：PK-000 完成入场确认。PK-001、PK-010、PK-100 已完成，上一批 PK-900 已最终通过；授权 PK-180 进入独立功能开发。本轮只登记范围和安全边界，未修改业务代码、未运行生命周期写操作、未读取或改动真实 focus 状态。
- 2026-07-21：本独立 PK-180 对话开始实施。目的为在不读取、打印、移动或改写真实 `focus_timer.json` 的前提下，将现有专注计时迁入明确的 router/service/repository 边界，制作并用临时 registry/runtime/data 完成真实 focus 本地包、重启装载、新旧 API、动态面板、停用/卸载/重装与数据保留的端到端验证；不处理其他业务模块，不执行 Git 暂存或发布。
- 2026-07-21：建立 `server/features/focus/` 的 models/repository/service/router/module 边界；`server/systems/focus_timer.py` 改为兼容导出，旧 Python 调用和安装包 router 均委托同一 service，没有复制第二套计时状态机。repository 路径可注入，API 装配只提供既有路径与可选 TTS 回调。
- 2026-07-21：新增正式 focus manifest、动态 `dashboard/index.js` 和确定性 ZIP 构建器。构建器把同一份 feature 源码物化为包内 `backend/`，实际包只含 manifest、Python 后端和控制台入口，不含 BAT/PowerShell/shell、`.env`、`focus_timer.json`、测试状态或安装命令。
- 2026-07-21：从 `server/api.py` 移除静态 focus 业务路由，从 `dashboard.html` 移除旧 focus DOM、请求、渲染和事件；已启用安装包在 API 重启时一次性注册 `/api/v1/focus/*` 与 `/focus/*`，动态面板只挂载到 `context.root` 并只请求版本化 namespace。
- 2026-07-21：更新 catalog：未安装 focus 显示 `available/disabled/installable`；安装状态由 PK-010 snapshot 覆盖，启用时返回可信 dashboard 入口，停用/卸载后新应用不再装配路由或面板。
- 2026-07-21：PK-900 第二批次主动审计发现动态面板 reset 成功后按钮仍保持禁用；已在 PK-180 边界内最小修复为成功后恢复按钮，并补充假 DOM 回归断言。另补充实际 focus ZIP 双次构建字节/摘要确定性，以及实际 focus 失败升级保留 1.0.0、无 1.1.0 半安装目录且旧路由仍可装配的隔离回归。

## 实际交付与接口

- 版本化接口：`GET /api/v1/focus/status`、`POST /api/v1/focus/start`、`POST /api/v1/focus/stop`、`POST /api/v1/focus/reset`。
- 兼容接口：`GET /focus/status`、`POST /focus/start`、`POST /focus/stop`、`POST /focus/reset`。两组路径绑定同一组 handler 和同一个 `FocusService`；启动请求继续接受 `mode/minutes/task/force/with_audio`，响应字段、重复启动 200 保护、停止/完成和 reset 计数语义保持一致。
- manifest：`focus` / `1.1.0` / `in_process` / `required=false` / `backend.register` / Core `>=1.0.0 <2.0.0` / 无依赖、可选依赖和冲突 / `local_state` / `data_namespace=focus` / `requires_restart=true`，并声明上述新旧接口、鼓励语接口与 `dashboard/index.js`。
- 包结构：`manifest.json`、`backend/{__init__,models,module,repository,router,service}.py`、`dashboard/index.js`。`server/features/focus/package_builder.py` 可生成可审阅目录或确定性 ZIP；测试实际对 ZIP 摘要进行 PK-010 校验、安装和升级。

## 2026-07-30 官方发布候选

- 发布身份：版本 `1.1.0`，tag `module-focus-v1.1.0`，asset `focus-1.1.0.zip`，官方仓库 `songshu-yu/Cyber-Girlfriend`。
- 发布输入：`package_source/manifest.json`、`package_source/dashboard/index.js` 与显式列出的 focus 后端源码；构建器自身、测试、README、release 元数据和任何本机状态都不进入 ZIP。
- ZIP 白名单：`manifest.json`、`backend/__init__.py`、`backend/models.py`、`backend/module.py`、`backend/repository.py`、`backend/router.py`、`backend/service.py`、`dashboard/index.js`。回归拒绝绝对路径、反斜线、`..`、重复大小写路径、脚本、状态、registry/runtime/cache、`.env`、测试、fixture、vendor 和额外文件。
- 冻结摘要：`manifest_sha256=376ad572802ce3028051ea3f11c3013964827777acb843fa2edab2f299f32f7b`；`package_size=32468`；`package_sha256=7e1c39fa68fed9df30c1305208ed5a6c82abcbd795ee43a31054b46b735efbe9`。
- 可合并元数据：`server/features/focus/release/official-release-fragment.json` 是 PK-010 builder 输入；`official-catalog-entry.json` 是完整 Catalog v1 条目，下载 URL 固定为 `https://github.com/songshu-yu/Cyber-Girlfriend/releases/download/module-focus-v1.1.0/focus-1.1.0.zip`。PK-000 应在 PK-010、PK-100、PK-180 通过 PK-900 后再合并目录并发布资产。
- PK-100 展示交接：名称“专注计时”；说明“番茄钟与自由专注计时，支持任务记录、重启恢复和动态控制台面板”；权限提示“仅本机专注状态（local_state）”；数据提示“卸载程序保留计时状态”；操作提示“启用、停用、升级、卸载后需重启 API 生效”。
- 构建与目录生成命令记录在 `server/features/focus/release/README.md`。本轮只在系统临时目录生成候选 ZIP 与临时 catalog，没有创建 GitHub Release、上传资产或写入正式 bundled catalog。

## 数据读写与保留

- 为保持迁移前实际行为，默认继续关联 `server/systems/data/focus_timer.json`；`server/data/focus_timer.json` 与其他同名历史文件同样受保护。本任务未读取、打印、移动、合并、格式化、重置或覆盖任何真实状态。
- 所有 service/router/重启/生命周期测试均显式使用系统临时目录下的 `focus_state_path`、registry、runtime 和 module data。
- 卸载仅移除 runtime 程序版本，历史计时状态在包外保留；重新安装、启用并重启后继续关联同一注入路径，测试已恢复进行中状态。
- PK-010 `purge-data` 只处理新的 `server/data/modules/focus/` namespace：错误确认被拒绝，精确 `focus` 才清除临时 namespace；它不删除历史计时文件。focus 自身 reset 是单独的显式业务操作，自动测试只对临时 store 执行。

## 重启语义

- 安装默认停用；启用、升级、停用和卸载均要求重启 API 才改变 `in_process` 路由与动态面板装配。
- 已运行进程中的路由不会热移除：测试明确确认停用后旧测试 app 仍返回 200，而新建 app 不再有 focus 路由；没有伪造热卸载。
- 启用后的新 app 同时提供新旧 API 与模块资产；停用/卸载后的新 app 返回 404 且 dashboard 资产不可读。QQ bridge、ASR 与 TTS 不需要因本模块生命周期而重启。

## 浏览器验证

- 未连接真实 API 或执行浏览器写操作。动态面板使用 Node 假 DOM 完成 `mount(context)`、受限请求、二次确认 reset 和 `unmount()` 自动验证；focus 面板自身回归通过。公共外壳的单模块失败隔离已有历史覆盖，但本轮完整 `test_dashboard_shell.py` 被混合工作区 PK-100 资产版本号不一致阻断，详见验证记录。
- 本轮未进行真实浏览器人工视觉检查；因此不宣称鼠标/移动端视觉已重新验证。PK-900 若需要，可复用去标识化、只读/临时状态预览进行视觉验收。

## 未解决问题

- 第一阶段功能中心仍只读，用户需调用本机生命周期 API 完成安装、启停、升级或卸载；通用控制台生命周期按钮不属于 PK-180。
- GitHub 官方目录下载与控制台安装尚未发布：PK-180 只交付资产、摘要、Catalog v1 条目和提示文案；PK-000 需在 PK-010 下载器、PK-100 UI 与本任务通过 PK-900 后创建 GitHub Release、上传完全相同的资产并合并官方 catalog。
- 两处历史 `focus_timer.json` 不自动合并；当前保留迁移前实际使用的 `systems/data` 路径。若未来决定统一到 `server/data/modules/focus/`，需要 PK-000 单独确认迁移、备份和回滚契约。
- 当前混合工作区的 `test_dashboard_shell.py` 仍期待 `pk100-20260729-widget11`，而实际 dashboard HTML/app 已引用 `pk100-20260730-modules1`；这属于 PK-100 在途修改，不在本增量授权范围内，交 PK-100/PK-900 对齐。focus 专用 dashboard 测试不受影响并已通过。
- 真实 Windows 控制台视觉和由 PK-900 执行的新批次集成验收尚未完成；本任务只能进入“待集成”，不能自行标记“已完成”。

## 验证记录

- `server/.venv-asr/Scripts/python.exe tests/test_focus_timer.py`：通过；覆盖临时 store 的启动、重复启动、停止、完成、重启恢复、reset 和 `systems.focus_timer` 兼容导出。
- `server/.venv-asr/Scripts/python.exe tests/test_focus_module.py`：通过；覆盖新旧 API 完整响应等价、重复启动、TTS 字段、实际 focus ZIP 内容/摘要、安装、启用、重启装载、进行中与完成状态恢复、资产、catalog、升级、停用后旧进程保留/新进程 404、卸载保留、重装关联、精确 purge 确认，以及错误摘要、非法 manifest、Core namespace 和模块 namespace 冲突无半安装状态。
- 同一 `test_focus_module.py` 的官方发布回归通过：两次独立构建 ZIP 字节/摘要一致，ZIP 路径和元数据固定，包内容严格白名单；PK-010 正式 catalog builder 生成的完整条目与冻结条目逐字段一致。
- `server/.venv-asr/Scripts/python.exe tests/test_focus_dashboard.py`：通过；包含 `node --check`、假 DOM `mount/unmount`、仅访问 `/api/v1/focus/*`、启动/停止和 reset 二次确认。
- `server/.venv-asr/Scripts/python.exe tests/test_installable_modules.py`：通过，PK-010 生命周期回归无退化。
- `server/.venv-asr/Scripts/python.exe tests/test_official_module_catalog.py`：通过；PK-010 固定官方 GitHub 来源、摘要校验、缓存/304、拒绝重定向/非 GitHub/超限资产与禁止覆盖既有 asset 等公共契约无退化。
- `server/.venv-asr/Scripts/python.exe tests/test_feature_catalog.py`：通过，focus 未安装/安装目录映射与 Core 契约无退化。
- `server/.venv-asr/Scripts/python.exe tests/test_dashboard_shell.py`：本轮失败于 `check_html_contract`；测试固定期待 `pk100-20260729-widget11`，实际混合工作区 HTML/app 使用 `pk100-20260730-modules1`。失败发生在 focus 模块加载前，未修改 PK-100 文件；交 PK-100/PK-900 对齐。历史 PK-180 集成轮曾通过该套件。
- `server/.venv-asr/Scripts/python.exe -m py_compile features/focus/... tests/test_focus_*.py`：通过；覆盖 focus 全部 Python、package builder 和三个 focus 定向测试。
- `node --check features/focus/package_source/dashboard/index.js`：通过。
- PK-010 正式 builder 在系统临时目录生成 `official-catalog.json`，随后以 `--check` 复核通过；两份 `focus-1.1.0.zip` 均为 32468 bytes 且 SHA-256 均为 `7e1c39fa68fed9df30c1305208ed5a6c82abcbd795ee43a31054b46b735efbe9`。
- `server/.venv-asr/Scripts/python.exe scripts/check_task_docs.py`：状态切换前通过，输出 `task documentation gate passed: 21 gated task(s)`；切换为“待集成”后复跑通过，输出 `task documentation gate passed: 22 gated task(s)`。
- `git diff --check`：通过，退出码 0；只有混合工作区已有的 LF→CRLF 提示，无空白错误。明确 PK-180 路径的 `rg -n "[ \\t]+$"` 无匹配（`rg` 以 1 表示未找到）。
- 项目标准 `scripts/python.ps1` 在当前 PowerShell 执行策略下被系统阻止；同一仓库迁移环境解释器 `server/.venv-asr/Scripts/python.exe` 可用并完成全部构建和验证。这不是产品运行失败，也未修改本机启动器或 README.local.md。
- 未运行真实浏览器或连接真实 API；不宣称新的人工视觉回归通过。所有写验证均在系统临时目录，不涉及真实计时、模块注册表、runtime、QQ、采集、TTS 或付费 LLM。

## PK-011 生命周期整改（2026-07-31）

- 当前候选提升为 `focus@1.1.1` / `module-focus-v1.1.1` /
  `focus-1.1.1.zip`。正式包公开身份绑定、幂等 `unregister(app)`，只清理本实例
  路由/service/state；注册失败回滚部分路由，不触碰专注个人状态。

## 完成文档门禁

任务进入“待集成”前必须全部勾选；不适用项也必须写明原因。

- [x] TASK_RECORD — 已记录实际模块边界、新旧接口、包结构、数据副作用、重启、验证、浏览器限制和遗留问题。
- [x] TASKS_BOARD — 本轮入场时 PK-000 已将 `TASKS.md` 置为“进行中”，并明确委派本对话不得再修改；任务文件现置“待集成”，由 PK-000 复核后同步总看板。
- [x] PUBLIC_README — 本增量尚未产生可供用户下载的正式 GitHub Release 或已合并目录，公共用户行为未变化，因此不改根 README；已在 focus README 和 release README 记录发布候选、构建、来源、保留与重启交接。正式发布说明由 PK-000/PK-900 随 catalog 与 UI 一并同步。
- [x] MODULE_CATALOG — 未修改 PK-010 bundled catalog；已提供通过正式 Schema/builder 的预发布 fragment 和完整可合并条目，待 PK-000 在 PK-900 通过后合并，避免提前暴露尚不存在的 GitHub asset。
- [x] ARCHITECTURE_DOCS — 不适用：本轮没有改变 manifest、Catalog v1、生命周期或模块边界公共契约；发布特定规则集中记录在 focus release README，避免重复架构文档。
- [x] LOCAL_README — 不适用：本机路径、启动器、解释器、端口和环境位置均未变化。
- [x] AGENT_RULES — 不适用：没有改变 agent 工作流、安全、验证、文档或 Git 规则。
- [x] VALIDATION — 已记录实际通过项、PK-100 混合工作区导致的 dashboard shell 外部失败、临时隔离证据、浏览器未验证限制、解释器限制和 `git diff --check`；状态切换后复跑文档门禁。

## 独立对话启动提示

```text
领取 Project Kei 的 PK-180 专注计时与首个可安装模块试点。先完整阅读
README.md、AGENTS.md、README.local.md（如存在）、TASKS.md、
tasks/PK-180-focus.md、tasks/PK-010-installable-modules.md、
tasks/PK-100-dashboard-shell.md、tasks/PK-900-integration-release.md、
docs/architecture/modular-monolith.md 和 docs/architecture/installable-modules.md，
检查 git status 与实际 focus 代码。只处理 focus 模块、manifest/本地包、
/api/v1/focus、/focus/* 兼容、动态面板和隔离生命周期测试；不得读取、移动、
清除、覆盖、打印或打包真实 focus_timer.json。需要改变 PK-010/PK-100 公共
契约时先在任务文件记录并停止扩张，交 PK-000 确认。完成后只进入“待集成”，
不得自行标记“已完成”，不得执行 Git 提交或推送。
```
