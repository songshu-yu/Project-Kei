# PK-011 — 全量业务模块可安装化与官方发布

- 状态：已完成
- 优先级：P0
- 所属模块：`installable_module_rollout`
- 依赖任务：PK-010、PK-100、PK-180
- 参与任务：PK-110、PK-115、PK-120、PK-130、PK-131、PK-132、PK-133、PK-134、PK-140、PK-150、PK-160、PK-170、PK-190、PK-200、PK-210、PK-211、PK-212、PK-213
- 负责路径：各业务模块的 `package_source/`、`package_builder.py`、公开 release 元数据和专属测试；共享装配窗口中的 `server/api.py`、`server/features/catalog/`、`server/core/modules/official-catalog.json`、`README.md` 与模块架构文档
- 当前对话：2026-07-30 由用户授权 PK-000 启动全部业务模块可安装化、统一验收和 GitHub 发布

## 目标

把 Catalog 中除 Core 必需模块外的现有业务能力迁移为符合 PK-010 契约的
版本化模块包。用户可以在 PK-100 模块中心显式刷新 Project Kei 官方 GitHub
目录，查看来源、版本、大小、权限和摘要，下载、校验、安装、启用、停用、更新、
回滚和卸载模块；默认卸载保留用户数据。所有模块完成累计验收后，由 PK-000
统一更新 README、提交源码、推送官方目录并发布不可变 GitHub Release 资产。

## Core 与可安装模块边界

以下三项属于不可替换的 Core 最小集合，不进入下载、停用或卸载流程：

- `module_manager`
- `catalog`
- `dashboard`

以下 Catalog 项进入可安装化迁移：

| 模块 ID | 任务 | 类型 | 主要依赖 |
|---|---|---|---|
| `conversation` | PK-200 | in_process | Core |
| `affection_memory` | PK-160 | in_process | conversation provider 契约 |
| `demon_slayer` | PK-150 | in_process | conversation 为可选增强 |
| `fitness` | PK-170 | in_process | Core |
| `focus` | PK-180 | in_process | conversation 为可选增强 |
| `calendar` | PK-190 | in_process | Core |
| `intel_sources` | PK-115 | in_process | Core |
| `x_monitor` | PK-120 | in_process | intel_sources、Collector 公共契约 |
| `bilibili` | PK-130 | in_process | intel_sources、Collector 公共契约 |
| `youtube` | PK-131 | in_process | intel_sources、Collector 公共契约 |
| `github_intel` | PK-132 | in_process | intel_sources、Collector 公共契约 |
| `papers` | PK-133 | in_process | intel_sources、Collector 公共契约 |
| `rss_intel` | PK-134 | in_process | intel_sources、Collector 公共契约 |
| `daily_briefing` | PK-110 | in_process | Collector 公共契约；来源模块为可选依赖 |
| `voice` | PK-210 | in_process | conversation |
| `gpt_sovits_engine_provider` | PK-211 | sidecar adapter | voice；不包含上游引擎 |
| `voice_pack_registry` | PK-212 | in_process | voice；不包含权重或参考音频 |
| `voice_pack_distribution` | PK-213 | project tooling | voice_pack_registry；不包含真实资产 |
| `qq_bridge` | PK-140 | sidecar | conversation、daily_briefing 与业务菜单模块 |

依赖是否为强依赖或可选依赖必须以模块在缺失下是否仍可正确降级为准，不能为了
方便把所有模块强行绑成一个安装集合。最终 manifest 依赖图不得成环。

## 不在本任务内

- 不把 Core 必需模块伪装成可卸载包。
- 不把 GPT-SoVITS 上游源码、ASR 模型、Voice Pack 权重、参考音频、Node
  `node_modules`、Python 虚拟环境或 `vendor/` 打入模块包。
- 不自动迁移、重置、打印、提交或上传任何真实个人状态、缓存、来源名单、
  `.env`、Cookie、Token、LLM profile、QQ runtime 或模型登记。
- 不开放第三方模块商店、任意 GitHub 仓库、任意 URL、远程脚本、静默安装、
  启动时自动下载或未经确认的自动更新。
- 不借可安装化迁移重写各模块业务规则、删除 legacy API 或合并数据所有权。

## 统一模块包契约

- 每个模块拥有稳定 `module_id`、SemVer、Core 兼容范围、明确依赖/冲突、
  API namespace、legacy endpoints、权限、数据 namespace 和重启语义。
- 开发源码仍由 `server/features/<module_id>/` 维护。确定性构建器只把明确
  allowlist 的程序文件复制进临时包，不从 runtime 或用户数据目录反向取材。
- `in_process` 包使用受支持的 `backend.register` 入口；`sidecar` 只能引用
  Core 已审查并登记的 adapter，manifest 不得包含可执行命令或 shell。
- 动态面板导出 `mount(context)`，可导出 `unmount()`；只能访问自己的 DOM 和
  manifest 声明的公开 API，不得直接访问其他模块内部代码或数据文件。
- 模块间共享类型必须位于稳定 Core 契约层。情报模块不得继续从
  `features.daily_briefing` 内部实现反向导入 Collector 模型；需要先冻结公共
  `core/intel_contracts` 或等价边界。
- 安装、更新、停用、卸载后的进程内路由变化允许要求重启，但 UI 与 API 必须
  返回真实 `restart_required`，不能伪装热卸载。

## 数据所有权与兼容

- 程序包、模块注册状态和用户数据严格分离。
- 新模块数据默认位于 `server/data/modules/<module_id>/`；已经投入使用的历史
  数据路径继续由原任务拥有。未经独立迁移契约，不移动、不复制、不格式化。
- 卸载只移除可再生成程序文件并保留个人数据；清除数据是独立危险操作，要求
  精确 `module_id` 二次确认。
- 新旧 HTTP 接口必须委托同一 service/repository。安装包不得包含真实状态或以
  测试名义读取真实状态。

## 官方目录与发布契约

- 官方来源固定为 `songshu-yu/Project-Kei-Modules` 的受版本控制 Catalog v1 和
  不可变 GitHub Release ZIP 资产。
- 每个发布版本提供 ZIP SHA-256、manifest SHA-256、精确字节数、release tag、
  asset 名称、权限、数据策略和 Core 兼容范围。
- 页面加载和读取缓存不联网；只有用户显式刷新目录或确认安装/更新才联网。
- 摘要错误、超限、截断、非法重定向、路径穿越、绝对路径、链接/reparse、
  manifest 不一致或安装失败均不得留下半状态。
- 一个 Release tag 下的同名资产不得替换；内容变化必须发布新版本。

## 分批实施与共享文件冻结

### A. 基础批

`PK-010 + PK-100 + PK-180`

- 冻结 Catalog v1、官方获取、生命周期和 dashboard 管理界面。
- 发布 focus 作为第一个真实官方模块包。

### B. 本地业务批

`PK-150 + PK-160 + PK-170 + PK-190 + PK-200`

- 先迁移无外部采集 side effect 的业务模块。
- 保留 legacy API、个人数据路径和受控生成降级。

### C. 情报批

`PK-115 + PK-120 + PK-130 + PK-131 + PK-132 + PK-133 + PK-134 + PK-110`

- 先冻结独立 Collector 公共契约，再打包来源模块，最后打包聚合模块。
- 普通目录、缓存读取和配置保存继续零网络。

### D. 语音与 sidecar 批

`PK-210 + PK-211 + PK-212 + PK-213 + PK-140`

- Provider、Engine adapter、Voice Pack 注册表/分发和 QQ sidecar 保持分离。
- 包内不包含引擎、模型、权重、参考音频、秘密或本机路径。

并行开发期间冻结以下共享文件，只有 PK-000 安排的串行装配窗口可以修改：

- `TASKS.md`
- `README.md`
- `AGENTS.md`
- `server/api.py`
- `server/features/catalog/service.py`
- `server/core/modules/**`
- `server/static/dashboard.html`
- `server/static/dashboard/**`
- `docs/architecture/installable-modules.md`
- `docs/architecture/module-package-contract.md`
- `.github/workflows/**`

各任务只修改自己的 feature、package source/builder、专属测试和任务记录。需要改变
manifest、loader、Catalog 或模块间公共契约时必须停止并交回 PK-000。

## 验收标准

- 没有任何可选包时 Core、模块中心和健康检查可以启动；没有外部服务、秘密、
  模型或配置时失败可理解且不影响 Core。
- 19 个可安装项分别具有可重复构建的程序包和有效 Catalog 条目；同一输入构建
  字节与摘要稳定。
- 每个模块均通过安装、配置检查、启用、停用、升级、回滚、卸载保留数据和重装
  恢复测试；不支持的动作必须明确拒绝。
- 各模块 legacy 与 versioned API 在安装启用后保持兼容，停用/卸载并重启后不再
  装配；没有重复路由或开发源码/运行包双装配。
- 依赖图无环；缺少强依赖时拒绝启用，缺少可选依赖时按文档降级。
- 所有包和 Catalog 不含真实个人数据、缓存、名单、秘密、模型、本机绝对路径、
  `.venv`、`node_modules` 或 `vendor/`。
- 自动测试仅使用临时 registry/runtime/data、fake/MockTransport 和假 sidecar，
  不调用真实 GitHub、采集源、LLM、TTS、QQ 或付费服务。
- PK-900 对每个分批及最终总批独立复核通过；README、模块交互规范、Catalog、
  任务记录和实际 Release 资产完全一致。
- PK-000 仅显式暂存审阅过的发布文件，统一提交、推送并创建/更新发布；混合
  工作区的个人状态和无关任务修改始终排除。

## 工作记录

- 2026-07-30：PK-000 实际盘点 Catalog 共 22 项。`module_manager`、`catalog`、
  `dashboard` 固定为 Core；其余 19 项进入四个分批。当前只有 focus 具备正式
  manifest、确定性包构建器和动态面板，因此先完成基础批，再开放后续批次。
- 2026-07-30：四批专属实现交回后，PK-000 完成共享串行装配。`server/api.py`
  只保留 Core 模块中心、dashboard 外壳和健康入口；已启用 in-process 包在 ASGI
  lifespan 冻结 middleware 前按依赖顺序登记，新旧 API/动态面板随模块启停并在
  重启后生效。异步 unregister、sidecar readiness 隔离、calendar summary Provider、
  conversation/voice/briefing Provider 和 QQ 同 adapter facade 已接入生产 composition。
- 2026-07-30：19 个 release fragment 已生成统一
  `server/core/modules/official-catalog.json`。所有包仅写系统临时目录并连续构建
  两轮，19/19 ZIP 字节与 SHA-256 完全一致；Catalog builder 从实际 ZIP 核对版本、
  manifest 摘要、包摘要、大小、依赖、权限与固定 GitHub Release URL。包内路径
  审计对 `.env`、`node_modules`、`vendor`、`data` 和已知个人状态文件为 0 命中。
- 2026-07-30：新增 `test_official_module_release_set.py`，从每个正式 builder 重建
  两轮包，严格比对官方 Catalog，验证依赖图无环，并在临时 ModuleManager 中完成
  19 项安装、全部 in-process 依赖序启用/逆序停用、逆序卸载保留数据和全量重装。
  该累计专项通过；官方目录、生命周期、dashboard、feature catalog、生产 host、
  本机访问、conversation consumers、情报来源隔离、QQ 包 11/11、qq-control 8/8
  与 Node 83/83 同时通过。
- 2026-07-31：Python 测试清单已刷新为 87 个文件，其中默认 73、隔离 14；默认入口
  共收集 382 项并得到 `382 passed`。Ruff、全量 `compileall`、44 个 JS/MJS
  `node --check`、任务文档门禁和 `git diff --check` 均通过。全部测试使用工作区外临时
  Python 环境、临时 registry/runtime/data、fake/MockTransport 与假 sidecar；未读取
  真实个人状态、来源名单、缓存、秘密、模型、Voice Pack registry 或 `vendor/`。
- 2026-07-31：19 个最终候选重新构建并与
  `server/core/modules/official-catalog.json` 逐项核对，确定性、依赖无环、安装、依赖序
  启用、逆序停用、卸载保留数据与重装全部通过。当前仅登记为“待集成”，ZIP 尚未
  上传，Catalog 中固定 GitHub Release URL 也不得描述为已经可用；最终状态和发布
  必须等待新的独立 PK-900 对同一候选及后续 Git commit/Release 资产复核。
- 2026-07-31：按独立 PK-900 退回证据补齐 8 个正式 in-process 包的最小可逆
  生命周期：`youtube/x_monitor/fitness/affection_memory/daily_briefing/demon_slayer/
  intel_sources/focus` 均公开身份绑定、幂等 `unregister(app)`；Collector 按对象身份
  解除，Provider/state 仅在当前值仍为本实例对象时清理，宿主预置或后来替换对象保留。
  fitness/affection middleware 只删除本次 `add_middleware` 后识别出的精确
  `user_middleware` 描述符，不清空宿主列表、不重建冻结的 `middleware_stack`。
  每个 `register` 对部分路由、Collector、middleware 和自建 registry 做异常回滚。
- 2026-07-31：`test_official_module_release_set.py` 新增从 8 个正式 builder 生成真实包，
  经 `InProcessModuleLoader + ModuleActivationCoordinator` 逐一 load→unload，核对 routes、
  app.state、Provider、Collector、middleware 零残留；另覆盖 affection middleware
  添加后故障注入、重复 unregister 和宿主替换 Provider 不被清除。累计 19 包确定性、
  Catalog、安装/启停/卸载/重装与上述生命周期回归通过。
- 2026-07-31：受影响候选按不可变资产规则提升补丁版本并从实际 ZIP 重建 Catalog：
  `affection_memory@1.0.1` 73285 bytes / `9e11e95b47e01aaa...`，
  `daily_briefing@1.0.2` 126244 / `02d97afa30819210...`，
  `demon_slayer@1.0.1` 105156 / `880d75219bde9c17...`，
  `fitness@1.0.1` 33608 / `a53a28cfa58a6c5c...`，
  `focus@1.1.1` 34284 / `4a455bbd73bad33b...`，
  `intel_sources@1.1.1` 37183 / `fa6212505a8f6969...`，
  `x_monitor@1.0.1` 87781 / `b0932f6ff0ace5e4...`，
  `youtube@1.0.1` 22217 / `692dd56d29904a0d...`。完整 SHA-256、manifest SHA-256、
  tag 与 asset 以各 release entry 和官方 Catalog 为准；仍未发布。
- 2026-07-31：本轮实际验证通过：8 个受影响模块专属历史 `main()` 回归、
  `test_official_module_release_set.py`（19 包确定性/安装集 + 8 包真实
  loader/coordinator 清理）、`test_module_host_assembly.py`、受影响 Python
  `compileall`、19 项 Catalog 从实际 ZIP 内存重建精确相等、Python inventory
  `87 files / 73 default / unsatisfied=0`、44 个 JS/MJS `node --check`、26 项任务
  文档门禁。完整 pytest 与 Ruff 未在当前两个可用解释器中执行：迁移期
  `.venv-asr` 缺 pytest/ruff，根 wrapper 选中的系统环境缺 FastAPI/ruff；未联网或
  修改既有 venv 补装依赖。按本轮明确禁令未执行 Git/diff 命令，交由父级集成
  工作流在完整候选环境继续完成。
- 2026-07-31：第二轮 PK-900 证明上述 8 包的 routes/state/provider/collector/
  middleware 清理已生效，但 Core Loader 仍遗留动态包子模块；同时
  `intel_sources` 在 provider 多字段发布中途失败时遗留两个先写字段。现已统一按
  动态包名前缀清理 import 树，并为 intel_sources 增加完整 state 快照恢复与永久
  故障注入回归。`intel_sources` 因包字节变化提升为 1.1.2（37495 bytes，ZIP
  SHA-256 `8da2335c3837795cb2587130948e69fe10ece7aa2bd8d17aed86812d59525850`，
  manifest SHA-256 `ba8354949be3de0304797acc6fb92fb049b90d1450550d929cddb9b6c9920362`）；
  19 项 Catalog 已从新的实际资产根重建，定向 Loader/安装/Catalog 24 项通过。
- 2026-08-01：在系统临时目录重新生成当前官方目录声明的 19 个确定性 ZIP，总大小
  1,275,129 bytes；`build_official_module_catalog.py --check` 使用全部 release fragment、
  实际 ZIP manifest、大小和 SHA-256 对当前 `official-catalog.json` 精确复现通过。
  `test_official_module_release_set.py` 再次覆盖 19 包双构建字节一致、保护文件名排除、
  依赖排序、安装/启停/卸载保留数据/重装和故障回滚。发布时只上传这些临时构建产物，
  不上传 `runtime/`、个人状态、缓存、`.env`、模型、Voice Pack 本机注册表或 `vendor/`。

## 完成文档门禁

- [x] TASK_RECORD — 已记录各批次接口、产物、数据副作用、验证和遗留问题。
- [x] TASKS_BOARD — 已同步 PK-011 的待集成状态及本轮 PK-900 依赖；参与任务继续保持各自真实状态。
- [x] PUBLIC_README — 已更新普通用户模块中心、安装、启停、卸载、离线和限制说明。
- [x] MODULE_CATALOG — 19 个可安装模块的候选目录、依赖、版本、摘要和资产名一致；正式 URL 等待发布后复验。
- [x] ARCHITECTURE_DOCS — 已完成模块交互、包格式、生命周期和发布规范。
- [x] LOCAL_README — 不适用：本轮不记录或改变本机路径。
- [x] AGENT_RULES — 不适用：沿用现有安全、验证和 Git 规则，没有新增 agent 规则。
- [x] VALIDATION — 已记录本轮生命周期/正式包/Catalog/compile/node/docs/inventory
  结果及当前环境无法执行完整 pytest/Ruff、当前子任务禁止 Git/diff 的限制；独立
  PK-900、tracked copy 和远端矩阵继续保留为集成门禁。

## 独立对话启动提示

```text
继续 Project Kei 的 PK-011 全量业务模块可安装化与官方发布协调任务。先完整阅读
README.md、AGENTS.md、README.local.md（如存在）、TASKS.md、
tasks/PK-011-installable-module-rollout.md、tasks/PK-010-installable-modules.md、
tasks/PK-100-dashboard-shell.md 和模块包架构文档，并检查混合工作区。严格按 A-D
批次推进。业务任务只修改自己的 package source/builder、专属测试和任务记录；
共享装配必须等待 PK-000 串行窗口。不得读取或上传真实状态、秘密、模型、缓存或
vendor，不执行 Git 发布，直至 PK-900 最终通过并由 PK-000 统一提交。
```
- 2026-08-02 集中分发增量：PK-000 决定将 19 个模块从“每模块一个 Release”迁移到独立私有仓库 `songshu-yu/Project-Kei-Modules`。模块源码与确定性 builder 继续留在主仓库；分发仓库按业务/情报/语音/集成分类，只提交 Catalog 与说明，全部 ZIP 作为 `modules-2026.08.02` 的独立附件上传。旧逐模块 Release 保留兼容，不删除、不作为新 Catalog 来源。
- 2026-08-02 最终关闭：PK-900 独立下载并复算 19 个远端附件，确认 size/SHA-256 与 Catalog、本地双构建逐字节一致；包安全扫描、391 项完整测试、Ruff、JavaScript 语法、Catalog、文档和差异门禁全部通过。PK-000 据此将 PK-011 标记为“已完成”；PK-900 仍继续承担 PK-020 + PK-030 批次。
