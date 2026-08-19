# PK-190 — 日历备忘与修炼记录

- 状态：待集成
- 优先级：P2
- 所属模块：`calendar`
- 依赖任务：PK-001、PK-010、PK-100
- 负责路径：`server/features/calendar/`、`server/tests/test_calendar_module.py`、`server/tests/test_calendar_memo.py`、本任务记录
- 当前对话：2026-07-30 由 PK-000 重新打开可安装化增量，属于 PK-011 本地业务批

## 目标

在不改变既有业务规则、状态位置和 HTTP 兼容性的前提下，把 calendar 制作为符合
PK-010 契约的确定性 `in_process` 安装包。包提供独立 manifest、
`backend.register`、动态控制台面板、发布元数据和专属生命周期测试；安装、停用、
卸载和重装不迁移或删除既有事件、标签、备注、技能及练习记录。

## 不在本任务内

- 不修改 `TASKS.md`、`README.md`、`server/api.py`、共享 Catalog、
  `server/core/modules/`、共享 dashboard、voice 或架构文档；共享装配由 PK-000
  串行处理。
- 不发布 Git commit、PR、GitHub Release、官方 Catalog 或 ZIP 资产。
- 不读取、打印、迁移、重置、打包、暂存或提交真实
  `server/systems/data/calendar_memo.json` 及任何历史同名文件。
- 不把用户状态、`.env`、缓存、模型、`vendor/`、脚本、测试夹具或 runtime
  反向复制进模块包。
- 不新增编辑、单条删除、导入、导出、外部日历同步、提醒或后台任务。
- 不在动态面板提供全量 reset。

## 包与接口契约

- 模块 ID：`calendar`；版本：`1.0.0`；类型：`in_process`。
- Core 兼容范围：`>=1.0.0 <2.0.0`；权限：`local_state`；启停和卸载按
  `requires_restart=true` 生效。
- 入口：`backend.register`；开发源码继续位于
  `server/features/calendar/`，构建器只复制固定 allowlist。
- 版本化接口保持：
  `GET /api/v1/calendar/today`、
  `GET /api/v1/calendar/status`、
  `POST /api/v1/calendar/events`、
  `POST /api/v1/calendar/practice`、
  `POST /api/v1/calendar/reset`。
- legacy 接口保持：
  `GET /calendar/today`、
  `GET /calendar/status`、
  `POST /calendar/event`、
  `POST /calendar/practice`、
  `POST /calendar/reset`。
- 新旧接口仍由同一个 router 绑定同一个 `CalendarService` 和
  `CalendarMemoStore`，不复制业务或持久化实现。
- 版本化 reset 只接受精确请求体 `{"confirmation":"calendar"}`。legacy reset
  仍无确认，这是已知兼容风险；动态面板不显示或调用任何 reset。
- 动态面板只通过受限 `context.request` 访问声明的
  `/api/v1/calendar/*` namespace，导出 `mount(context)` 和 `unmount()`，
  不保存业务状态到浏览器。

## Summary Provider 接缝

- `CalendarSummaryProvider` 是 callable 公开边界，只委托
  `CalendarService.today_summary()`，不暴露 repository 或状态路径。
- `backend.register(app)` 将 provider 放入
  `app.state.calendar_summary_provider`。
- 若 Core/voice 提供可选 `app.state.voice_calendar_provider_registry`，calendar
  只调用其公开
  `register_calendar_summary_provider(provider)` /
  `unregister_calendar_summary_provider(provider)`，不导入 voice 内部代码。
- `unregister(app)` 解除 registry/provider 引用；进程内路由仍遵守重启语义。
- 未安装/停用 calendar 时，新进程不加载 package，因此不注册 provider。明确的
  “模块不可用 + 空摘要”由 PK-210 公共 registry 负责；PK-190 用临时 registry
  验证该缺失状态，不修改冻结的 voice/API。
- 2026-07-30 已把现有 voice 兼容层静态导入 calendar service 的问题交给
  PK-000；PK-000 已确认由 PK-210 在共享装配窗口处理。

## 数据所有权

- 默认业务状态仍是历史路径
  `server/systems/data/calendar_memo.json`，只由 calendar repository 拥有。
- 本次包化不读取该文件；构建 allowlist 只包含 manifest、dashboard 和明确列出的
  Python 程序文件。
- `ModuleManager.uninstall("calendar")` 默认只移除程序并保留模块数据 namespace；
  历史状态路径不属于 purge namespace，停用、卸载、purge 与重装测试均确认隔离
  状态字节不变。
- 测试只使用系统临时目录中的显式 `CalendarMemoStore` 和
  `calendar_state_path`，文件名使用去标识化隔离名称。

## 必须保持的业务兼容基线

- 一次性事件与 `yearly` 年度重复事件。
- 闰年 2 月 29 日、跨年排序、未来七天与 `days_left`。
- 基于标题、日期、repeat 的确定性 ID 和重复添加保护。
- 标签、备注、技能练习日志、累计小时和熟练度阶段。
- 原子写入失败保留原状态且清理临时文件。
- 新旧 HTTP 接口成功响应等价。

## 实施清单

- [x] 复核 README、AGENTS、README.local、TASKS、PK-011/190/010/100、模块包
  契约及实际 calendar/voice 接缝。
- [x] 新增 `package_source/manifest.json` 和固定 allowlist 确定性构建器。
- [x] 新增 `backend.register`、重复路由拒绝、公开 Summary Provider 和可选
  registry 注册/解除。
- [x] 新增只调用版本化接口的动态面板，未提供 reset。
- [x] 新增 release fragment、确定性 Catalog 条目和发布交接说明。
- [x] 扩充专属测试，使用临时 store/ModuleManager 覆盖业务、包内容、生命周期、
  provider、重复路由、卸载重装与危险 reset 隔离。
- [x] 向 PK-000 提交共享 voice provider registry 适配需求，未越权修改共享路径。
- [x] 运行专属回归、业务回归、语法检查、发布元数据复算及差异检查。

## 验收标准

- 两次独立构建得到字节完全一致的 ZIP；entry metadata、时间戳、权限位和换行固定。
- ZIP 文件集合精确等于 manifest、动态面板和 backend allowlist，不含状态、
  `.env`、缓存、模型、vendor、脚本、测试或本机绝对路径。
- 安装后默认停用；启用并重启后十条新旧路由各只出现一次，第二次 register 幂等，
  与既有同 namespace 路由冲突时明确失败而不追加重复路由。
- versioned/legacy 路由共享 service/repository；版本化 reset 精确确认，legacy
  风险留档，动态面板无 reset。
- provider 可注册、解除；calendar 缺失时临时 registry 返回明确 unavailable 与
  空事件/技能摘要。
- 停用、卸载和精确/非精确 purge 不触碰外部 calendar 状态；重装恢复事件、标签、
  备注、技能和练习记录。
- yearly、闰年、跨年、未来七天、重复事件、累计小时和原子写失败均通过隔离测试。

## 工作记录

- 2026-07-21：完成第一阶段内置模块化：建立
  `models -> router -> service -> repository`，保留十条新旧接口、严格日期、
  yearly/闰日、事件去重、修炼累计、原子写及 versioned reset 精确确认。该历史
  阶段不含安装包。
- 2026-07-30：PK-000 为 PK-011 重新打开可安装化增量，并冻结共享
  API/Catalog/dashboard/README/Core/架构文件。入场确认工作区存在大量其他任务和
  用户状态修改，PK-190 只改 calendar 专属源码、测试和本任务记录。
- 2026-07-30：新增 `calendar@1.0.0` manifest、`backend.register`、
  `CalendarSummaryProvider`、可选 voice registry 接缝、确定性 ZIP 构建器、
  动态控制台面板和 release 元数据。构建过程只从源码 allowlist 取材，ZIP 仅在
  系统临时目录生成。
- 2026-07-30：专属安装测试首次发现两个测试断言问题（跨年列表顺序假设、版本化
  URL 被误判为 legacy substring），修正测试后通过；实现代码无需为断言让步。
- 2026-07-30：原 calendar memo 业务回归通过。旧
  `test_voice_calendar_intents.py` 在导入共享 voice 的未完成
  `gpt_sovits/sidecar_adapter.py` 时因当前解释器不支持运行时 `list[str]`
  注解而退出；失败发生在 calendar 测试逻辑之前，相关共享文件不属于 PK-190，
  已由 PK-210/PK-000 负责。

## 发布元数据

- Release tag：`module-calendar-v1.0.0`
- Asset：`calendar-1.0.0.zip`
- Manifest SHA-256：
  `8f743dc960022c4a0febe475149d803184c9e715ffd4fa708a30d2c9ee278653`
- Package SHA-256：
  `0d1df169d788574989b616f26d080b0516b449da340c675ae85e9aaed1af24a8`
- Package size：`38764` bytes
- 数据策略：`preserve_on_uninstall`
- 本任务未创建 Release、未上传资产、未修改共享官方 Catalog。

## 验证结果与限制

- 通过：`.venv-asr\Scripts\python.exe -m py_compile` 检查 calendar 新增 Python
  文件及专属测试。
- 通过：`.venv-asr\Scripts\python.exe tests\test_calendar_module.py`，输出
  `calendar installable module tests passed`。
- 通过：`.venv-asr\Scripts\python.exe tests\test_calendar_memo.py`，输出
  `calendar memo tests passed`。
- 通过：在系统临时目录构建 ZIP 和 Catalog，生成值与
  `official-catalog-entry.json` 一致。
- 受共享 PK-210 工作阻断：`tests\test_voice_calendar_intents.py` 尚未进入测试
  主体即在 shared voice import 阶段抛出 `TypeError: 'type' object is not
  subscriptable`；PK-190 未修改该路径。
- 未运行真实 API、真实 voice、真实状态或真实 Git 发布。

## 未解决问题

- PK-210 仍需移除 `features.voice.legacy_pipeline` 对 calendar service 的静态
  导入，并采用公共 registry；calendar 未安装时由该 registry 返回稳定的
  unavailable/空摘要。
- 共享 `server/api.py` 仍直接装配内置 calendar router。PK-000 必须在串行装配
  窗口移除它后再启用安装包；本包会明确拒绝重复路由，避免静默双注册。
- legacy `POST /calendar/reset` 仍无精确确认。为兼容保留，但动态面板没有入口；
  后续若收紧或移除，需要 PK-000 单独兼容决策。
- 真实历史状态只按既有 schema 和临时夹具验证；遵守数据边界，未读取真实内容。

## 完成文档门禁

- [x] TASK_RECORD — 已记录包内容、接口、provider、数据副作用、验证、限制和遗留
  集成问题。
- [x] TASKS_BOARD — PK-000 已预先把 PK-190 置为进行中并补充 PK-010/PK-100
  依赖；本对话按指令未修改 `TASKS.md`。完成后由 PK-000 在共享窗口同步待集成。
- [x] PUBLIC_README — 不适用：README 属于 PK-011 共享冻结路径，由 PK-000 在
  全批模块完成后统一更新。
- [x] MODULE_CATALOG — 不适用：共享 Catalog 冻结；PK-190 已提供专属 release
  fragment 和可复算 Catalog 条目供 PK-000 集成。
- [x] ARCHITECTURE_DOCS — 不适用：共享架构文档冻结；实现严格遵循现有模块包契约，
  公共 voice 缺口已交 PK-000/PK-210。
- [x] LOCAL_README — 不适用：本机路径、端口、解释器和启动方式未变化。
- [x] AGENT_RULES — 不适用：没有改变 agent 工作流或安全规则。
- [x] VALIDATION — 已记录专属/业务测试、共享 voice 阻断、确定性构建复算；
  `git diff --check` 在最终差异后执行。

## 独立对话启动提示

```text
复核 Project Kei 的 PK-190 calendar 可安装化增量。先完整阅读 README.md、
AGENTS.md、README.local.md、TASKS.md、PK-011/190/010/100、模块包契约和实际
calendar/voice 接缝。只检查 server/features/calendar/、calendar 专属测试和
任务记录；不要修改 TASKS、共享 API/Catalog/dashboard/README/Core/架构文件，
不要读取或操作任何真实 calendar_memo.json。用临时 CalendarMemoStore 和
ModuleManager 验证确定性包、十条兼容路由、provider 注册解除、卸载重装数据保留、
重复路由拒绝及 reset 隔离。共享 voice/API 适配交回 PK-000。
```
