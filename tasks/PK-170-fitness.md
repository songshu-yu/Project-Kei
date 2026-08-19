# PK-170 — 健身打卡

- 状态：已完成
- 优先级：P2
- 所属模块：`fitness`
- 依赖任务：PK-001、PK-010、PK-100
- 负责路径：`server/features/fitness/**`、`server/tests/test_fitness_module.py` 和本任务文件；`TASKS.md`、共享 API/Catalog/dashboard/README/core modules/架构文档及其他模块全部冻结
- 当前对话：2026-07-30 由 PK-000 重新打开 PK-170 的 PK-011 本地业务可安装化增量；只交付 fitness 专属包源、构建器、动态面板、release 元数据、隔离测试和任务记录，不修改共享装配或任务板

## 目标

在已经完成的 models、repository、service、router 分层之上，把 fitness 交付为
普通可选 `in_process` 安装包；包内版本化 API、legacy 接缝和动态控制台面板继续
委托同一个 service/repository，保留同日幂等、连续天数、六日奖励与既有个人状态
兼容。该增量复用 PK-010/PK-100 的冻结生命周期和面板协议，不引入 sidecar、
新端口或第二套业务实现。

## 不在本任务内

- 不修改 `TASKS.md`、`server/api.py`、Catalog、公共 dashboard、README、
  `server/core/modules/` 或架构文档；正式 composition/Catalog 合并由 PK-000
  在集成窗口串行处理。
- 不制作 sidecar、新端口、安装脚本、开放商店、第三方 URL、远程下载器或依赖
  安装逻辑；只产生 PK-010 已支持的声明式本地/官方 `in_process` 包输入。
- 不迁移、合并或修改好感度、长期记忆、斩妖、专注、日历、情报、QQ、conversation 或 voice 的业务规则与状态文件。
- 不新增训练计划、动作库、卡路里、体重、健康建议、云同步、多用户、提醒推送、编辑历史或单条删除。
- 不改变 PK-210 公共契约；legacy 打卡的可选奖励语音仍由应用 composition 使用现有 TTS 接缝完成，fitness service 只返回确定性的奖励事实和文本。
- 不未经总控决定扩大日期策略。既有显式日期兼容需保留；未来日期是否禁止如需改变，必须先记录需求并交回 PK-000。
- 不读取、打印、移动、迁移或打包真实 `server/data/fitness_checkins.json`；
  也不重新启用不存在的 `server/systems/data/fitness_checkins.json`。

## 接口契约

- 当前兼容接口：`GET /fitness/status`、`POST /fitness/checkin`、`POST /fitness/reset`。
- 目标接口：`GET /api/v1/fitness/status`、`POST /api/v1/fitness/checkins`。
- 安装包：`fitness@1.0.0`、`type=in_process`、`entrypoint=backend.register`、
  `dashboard/index.js`、`data_namespace=fitness`、权限仅 `local_state`，生命周期
  操作按冻结契约要求重启 API。
- 新旧 status/check-in 必须委托同一个 `FitnessService` 与同一个 repository，不能维护两套连续天数、奖励或重复打卡规则。
- `POST /fitness/reset` 是清除全部打卡与奖励的危险 legacy 入口：本轮只为旧客户端保留，不新增版本化 reset，不在控制台暴露；必须纳入与其他个人状态接口一致的本机 client/受信控制台 Origin 保护。若要增加版本化 reset，须先由 PK-000 决定精确确认契约。
- 动态面板只操作 `context.root`，挂载时只读
  `GET /api/v1/fitness/status`，用户明确点击后才调用
  `POST /api/v1/fitness/checkins`；继续显示今日状态、连续天数、累计打卡、
  下次奖励、备注和打卡按钮，不暴露 reset，不使用浏览器业务存储。
- `date`、`note` 与 legacy `with_audio` 保持兼容。note 不进入日志或错误正文；版本化核心响应不获得 TTS/Voice Pack 所有权。
- 调用其他模块：无业务依赖；主应用可以对明确解锁的奖励文本执行现有可选本机 TTS 兼容适配。
- 被调用方：控制台和旧客户端只通过公开 API；其他模块不得直接访问 fitness 状态文件。
- `backend.register` 在新 composition 中要求显式 `app.state.fitness_state_path`；
  未配置时失败关闭，绝不从 runtime 位置推导生产状态。迁移期若共享 API 已装配
  完整且名称匹配的五条 fitness 路由，register 只复用它们并设置登记标记；部分
  路由或重复/异名冲突会失败，不形成重复路由。

## 数据所有权

- 冻结所有权：`server/data/fitness_checkins.json`，属于用户个人状态。2026-07-22 入场只用 `Test-Path` 与定向 `git status --short --ignored` 确认该文件存在且状态无输出，未读取内容。
- 旧实现默认候选 `server/systems/data/fitness_checkins.json` 当前不存在。独立任务必须由 composition root 显式注入冻结路径，不得自动创建旧候选，也不得在两个位置之间猜测、复制、移动、合并或迁移。
- 未经用户明确授权，不得读取、打印、diff、摘要、格式化、清空、重置、覆盖、暂存或提交真实打卡日期、备注与奖励记录。
- 自动测试必须显式注入 `TemporaryDirectory` 下的 repository 和虚构数据；不得使用默认 store、`--today`、`--status`、`--reset` 或真实 API 生命周期进行验证。
- repository 写入必须原子化并序列化同一路径的读改写；损坏/结构异常状态应明确失败而不是回退空状态后覆盖，保存失败必须保留旧字节且不留下半状态。
- fitness 只拥有打卡条目和已发放奖励。不得读写 relationship、memory、demon、focus、calendar、profile、voice 或其他个人状态。
- manifest 的 `data_namespace=fitness` 只声明新的
  `server/data/modules/fitness/` 生命周期 namespace。卸载默认保留数据；
  `purge-data` 只能在精确确认 `fitness` 后删除这个新 namespace，不能删除、
  清空或迁移受保护的历史文件。重装由 composition root 继续显式关联原历史路径。

## 业务兼容基线

- 同一日期只记录一次打卡，重复请求不增加累计数、不重复写备注、不重复发奖励。
- 连续天数按目标日期向前计算，断档后重新计数；累计打卡按唯一合法日期计算。
- 每连续 6 天解锁一次既有 Kei 奖励，已发奖励键保持幂等；`next_reward_in`、最近 14 个打卡日期和最近 10 条奖励语义保持兼容。
- 合法 `YYYY-MM-DD` 显式日期、空备注与既有响应字段保持兼容；非法日期、空白/过长备注、重复/损坏条目、异常奖励结构和原子写入失败必须有临时夹具覆盖。
- 并发同日打卡只能提交一条记录并至多解锁一次奖励；不能通过读取或修改真实状态证明。

## 实施清单

- [x] 检查实际 fitness、API、控制台、catalog 和既有测试，只确认真实数据存在性/状态。
- [x] 建立 `server/features/fitness/` 的 models、repository、service、router 分层，由主应用显式注入冻结数据路径。
- [x] 装配版本化 status/check-in，让全部 legacy 接口委托同一 service；危险 reset 仅保留受保护兼容。
- [x] 保留控制台元素和交互，将请求切到版本化接口，不新增动态入口或清除控件。
- [x] 使用临时 repository 验证旧 schema、同日/并发幂等、连续天数、六日奖励、损坏文件与原子失败。
- [x] 更新 catalog、README、架构说明和本任务实际工作记录，并执行完成文档门禁与 `git diff --check`。

## 验收标准

- 冻结的真实文件及旧候选路径没有被读取、创建、迁移或修改；所有自动测试只使用临时 store。
- 新旧 status/check-in 共用同一 service/repository，返回和副作用兼容；legacy reset 保留但不出现在版本化 API 或控制台。
- 同日及并发重复打卡最多提交一次；累计、连续天数、六日奖励、奖励幂等、最近记录与下次奖励计算具有实际回归证据。
- 损坏或异常旧状态明确失败且不被空状态覆盖；临时写/替换失败保留旧字节，无临时文件和进程内半状态残留。
- note、日期、奖励文本和个人历史不进入日志、固定错误体、浏览器存储或其他模块；跨站/远端读取与写入在 repository 前被拒绝。
- 现有控制台面板、元素 ID、折叠和可选奖励语音兼容；不新增业务能力、进程、端口、安装包或其他状态所有权。

## 工作记录

- 2026-08-08：远端 Windows Actions 的 Python 3.11 在 `check_concurrent_checkin` 中偶发 `os.replace` `PermissionError`。独立审计确认同路径 repository 已由规范化路径的进程级 `RLock` 串行化，临时文件也在替换前关闭；阻断属于 Windows 文件系统/安全扫描器短暂占用目标或临时文件，不是同日幂等规则或测试夹具绕锁。repository 现只对 `PermissionError` 执行 10/25/50ms 三次有界重试；其他 `OSError` 仍立即失败，重试耗尽仍抛 `FitnessPersistenceError`、清理临时文件并保留旧状态。永久回归用临时 store 模拟两次共享拒绝后成功，并固定普通保存错误只尝试一次；未读取或修改真实 `server/data/fitness_checkins.json`。
- 2026-08-08 验证：项目受控 `scripts/python.ps1` 被本机执行策略拦截，临时 `-ExecutionPolicy Bypass` 后又因它选中的 Anaconda 缺 `fastapi`/有效 pytest asyncio 配置而未进入测试；未安装或改动环境。使用已有隔离 `server/.venv-asr` 直接运行临时 store 专项：并发与失败安全 1/1，通过 50 轮、每轮 24 个同日并发的压力回归 50/50；新增的瞬时 `PermissionError` 两次后成功、持续 `PermissionError` 四次后失败保旧、普通 `OSError` 一次即失败保旧均通过。完整脚本继续执行到官方 Catalog 元数据断言时因当前共享 Catalog 混合版本不一致停止，该阻断不在 PK-170 专属路径内，未越权修改；本次 repository、测试与任务文件的 `py_compile`/`git diff --check` 结果见交接记录。
- 该 repository 是 fitness 安装包的后端输入，不能用改变后的字节冒充已发布 `fitness@1.0.2`；PK-170 专属发布元数据因此升为 `fitness@1.0.3`、资产 `fitness-1.0.3.zip`、批次 `modules-2026.08.08`。总控串行窗口仍须把新条目合入共享官方 Catalog 并决定是否纳入本轮 Release；本任务不抢写共享 Catalog/README/TASKS，也不自行上传。
- 最终专属验证：`server/.venv-asr/Scripts/python.exe server/tests/test_fitness_module.py` 全部通过；50 轮并发压力 50/50；两次独立构建均为 34,369 bytes、SHA-256 `603dd45be66ab1e88f4d80ccaba99529abf4c9dbcf4520b9e781dff4895daad5`，manifest SHA-256 `2e742cb2734fed67a91b9fafe2baed5026f15ffc77662f7a88917d43fd054868`；相关 Python 编译、26 项任务文档门禁与范围内 `git diff --check` 通过。此前共享 Catalog 断言阻断已通过升级专属 release 元数据关闭；仍未修改共享 Catalog 本体。
- 2026-07-22：PK-000 确认 PK-001 已完成，PK-170 依赖满足并从“待开始”登记为“进行中”。当前分支与工作区包含大量其他已完成/进行中任务及个人状态修改，独立任务必须逐 hunk 保留，不得整理或吸收。
- 数据入场仅检查存在性和定向 Git 状态：冻结文件存在且状态无输出，旧 `systems/data` 候选不存在；未读取内容、大小、时间戳或摘要。当前旧实现默认路径与冻结所有权不一致，修正只能通过显式 composition，不得迁移真实文件。
- 本轮仅完成任务授权和边界登记，没有实现 fitness 业务代码，没有登记或启动新的 PK-900 批次。
- 2026-07-22：新增 `server/features/fitness/` 的 models、repository、service、router、compatibility、security 分层。repository 以规范化路径共享进程锁，在同一临界区完成读改写，保存使用同目录唯一临时文件、`flush/fsync` 和 `os.replace`；损坏 JSON、错误根/列表结构、异常字段和被篡改奖励均明确失败。替换失败清理临时文件并保留旧字节，service 不缓存可变状态。
- 主应用通过 `FITNESS_STATE_PATH = server/data/fitness_checkins.json` 显式构造唯一 `FitnessRepository`/`FitnessService`，没有读取、创建、迁移或合并不存在的 `server/systems/data/fitness_checkins.json`。`server/systems/fitness_checkin.py` 只保留旧 Python 导入门面，默认 store 也统一到冻结所有权。
- 实际接口：`GET /api/v1/fitness/status`、`POST /api/v1/fitness/checkins`；兼容 `GET /fitness/status`、`POST /fitness/checkin`、`POST /fitness/reset`。全部读取/写入均先经过本机客户端与可信 8000 控制台 Origin 防护，外层 middleware 覆盖 OPTIONS；危险 reset 仍只存在于 legacy。版本化响应不含音频字段且不触发 TTS，只有 legacy `with_audio=true` 且本次新解锁奖励时由 `api.py` 的兼容回调尝试本机 TTS，失败不回传异常。
- 业务兼容：同一合法自然日只计一次且重复请求返回 `already_checked_in`，不覆盖首次备注；乱序、重复和非法旧日期只读归一化为唯一合法日期集合。连续天数从目标日向前计算，断档重置；6 天、12 天及后续每 6 天使用既有奖励文本与 key 规则分别发放一次。status 保留累计打卡、最近 14 日、最近 10 个唯一奖励和 `next_reward_in`。
- 控制台保留原 fitness DOM、元素 ID、折叠、备注输入与按钮，只把 status/check-in 切换到版本化接口；未增加动态入口、reset 控件或浏览器业务存储。catalog 已登记完整新旧接口、冻结数据所有权、本机/TTS副作用、原子失败模式和 `modular` 迁移状态。
- 测试全部使用 `TemporaryDirectory` 与虚构日期/备注/音频，未调用默认 store、真实 API lifespan、真实 TTS、QQ、LLM 或网络。`test_fitness_checkin.py` 已移除可直接操作真实状态的 `--today/--status/--reset` 命令，只验证 legacy Python 门面；新增 `test_fitness_module.py` 覆盖新旧 API 共用状态、同日/并发幂等、6/12 天奖励、断档、乱序/重复/非法日期、损坏/篡改、替换失败、零写读取、Origin/远端拒绝和版本化零 TTS。
- 遗留风险：这是进程内路径锁，不提供多个独立 API 进程同时写同一 JSON 的跨进程协调；当前项目生产拓扑为单主 API 进程，符合模块化单体约束。legacy reset 与显式奖励音频仍为兼容面，后续若要新增版本化 reset、改变日期/补打卡语义或部署多 worker，必须交回 PK-000 决策。
- 完成实现、隔离验证和八项门禁后，PK-170 已按协议登记为“待集成”；没有提前标记“已完成”，也没有启动或修改 PK-900。

## PK-011 生命周期整改（2026-07-31）

- `fitness@1.0.1` 记录本实例新增的路由、service 与精确 middleware 描述符；幂等
  `unregister(app)` 不清空宿主 middleware，注册失败会回滚已添加副作用。复用宿主
  既有完整路由时不主张路由/middleware 所有权。

## 完成文档门禁

任务进入“待集成”前必须全部勾选；不适用项也必须写明原因。

- [x] TASK_RECORD — 已记录实际分层、接口、数据/TTS副作用、兼容行为、测试和多 worker 遗留风险。
- [x] TASKS_BOARD — 已同步 `TASKS.md`：PK-170 保持 P2、依赖 PK-001，状态改为“待集成”。
- [x] PUBLIC_README — 已更新 fitness 功能状态、新旧接口、生产数据路径、失败边界、重启要求、测试和限制。
- [x] MODULE_CATALOG — 已登记完整 endpoint、`server/data/fitness_checkins.json` 所有权、main-api 进程、legacy 面板、零网络/版本化零 TTS、失败模式和 `modular` 状态。
- [x] ARCHITECTURE_DOCS — 已在 `docs/architecture/modular-monolith.md` 增加内置 fitness 分层、依赖、兼容、锁/原子提交和数据边界；无 manifest/lifecycle 变化。
- [x] LOCAL_README — 不适用：本机路径、启动器、解释器、端口和环境位置均未变化，未修改忽略的 `README.local.md`。
- [x] AGENT_RULES — 不适用：没有改变长期工作流、安全、验证、文档或 Git 规则，未修改 `AGENTS.md`。
- [x] VALIDATION — 2026-07-22 首轮及退回整改后实际通过：`test_fitness_checkin.py`、`test_fitness_module.py`、`test_feature_catalog.py`、`test_dashboard_shell.py`；`compileall -q features\\fitness systems\\fitness_checkin.py api.py`；控制台内联脚本 `node --check -`；任务文档门禁；`git diff --check` 零退出，仅报告混合工作区既有 LF/CRLF warning。全部 fitness 测试只使用系统临时目录和虚构数据/音频。

## 独立对话启动提示

```text
继续 Project Kei 的 PK-170 健身打卡任务。先完整阅读根 README.md、
AGENTS.md、README.local.md（如存在）、TASKS.md 和 tasks/PK-170-fitness.md，
再检查 git status 与 fitness、API、控制台、catalog 的实际接缝。真实
server/data/fitness_checkins.json 只能检查存在性和 Git 状态，不得读取、diff、
迁移、重置或覆盖；所有测试注入临时 repository。只实现内置 fitness 分层、
版本化 API、legacy 委托和既有控制台面板；跨模块契约变化先停止并交回 PK-000。
```

## PK-000 最终复核退回（2026-07-22）

- 结论：不通过，责任归属 PK-170 repository/service 的损坏状态写保护。PK-170 与本批 PK-900 均退回“进行中”，不得标记“已完成”。
- 独立临时夹具写入结构合法但奖励 `text` 与冻结六日里程碑不一致的状态。`get_status()` 已能通过 `_unique_rewards()` 拒绝该状态，但随后直接调用 `check_in("2026-05-07", ...)` 没有先执行奖励 key/date/streak/text 语义校验，结果未抛 `FitnessStateError` 并把新打卡写回异常文件。实际输出：`tampered_write_blocked=False`、`old_bytes_preserved=False`，夹具按安全期望退出 1。
- 最小整改：在任何会保存 fitness 状态的 mutation 修改数据前，统一验证已持久化奖励的完整业务不变量；至少让 `check_in()` 对非法奖励日期、非 6 倍数 streak、key 与里程碑不一致、奖励文本被篡改等状态失败关闭。不得以清空或静默修复覆盖异常文件，也不得破坏对完全重复合法奖励的既有只读去重兼容。
- 必补回归：对上述每类语义损坏分别调用 `check_in()`，断言抛出 `FitnessStateError`、目标字节完全不变、无临时文件；HTTP versioned/legacy check-in 应返回固定脱敏 500 且不含奖励正文、路径或异常细节。修复限定在 `server/features/fitness/**` 及其定向测试；无需改变 API、控制台、catalog 或其他模块契约。
- 已通过项：真实路径唯一性与定向状态、40 路同日并发仅一次打卡/发奖、六日奖励防重复、断签后 streak=1、`os.replace` 失败旧字节不变、新旧 status 一致、status 零写、版本化零 TTS、控制台只使用版本化接口且无业务 browser storage。五项规定回归与总控独立正向夹具均通过。
- 真实 `server/data/fitness_checkins.json` 仍只检查存在性和 Git 状态，未读取、打印、diff、迁移、reset 或覆盖；旧 `server/systems/data/fitness_checkins.json` 不存在。未暂存、提交、推送或清理工作区。

## PK-170 退回整改（2026-07-22）

- 已在 `FitnessService.check_in()` 的 repository mutation 第一步调用统一 `_unique_rewards()`，在计算/追加打卡和创建临时文件之前验证全部既有奖励的日期、6 日倍数、key/日期/里程碑一致性及冻结文本。后续奖励幂等判断只使用该已验证、按 key 去重的快照。
- 对非法奖励日期、streak 非 6 的倍数、key 与日期/里程碑不一致、冻结奖励文本被篡改四类临时夹具，分别直接调用 service check-in，并重放 `POST /api/v1/fitness/checkins` 与 `POST /fitness/checkin`。全部 service 调用抛出 `FitnessStateError`，两组 HTTP 均固定返回 `500 {"detail":"fitness state is invalid"}`，不含路径、奖励正文、异常或堆栈；每次断言旧文件字节完全不变且无同目录临时文件。
- 补充完全重复合法奖励兼容回归：status 仍只读去重为一条且字节不变，随后正常日期 check-in 可成功，持久状态不会静默整理或删除原有合法重复奖励。
- 退回整改后重新通过 `test_fitness_checkin.py`、`test_fitness_module.py`、`test_feature_catalog.py`、`test_dashboard_shell.py` 和 fitness/api `compileall`。修复未改变 API、日期、奖励文本/周期、控制台、catalog、README 或其他模块；PK-900 保持“进行中”等待复验，PK-170 重新交回“待集成”。

## PK-000 整改后最终复验（2026-07-22）

- 结论：通过。总控原样重放上次失败夹具，现输出 `tampered_write_blocked=True`、`old_bytes_preserved=True`、`temporary_files=0`；原奖励语义损坏写回阻断已关闭。
- 总控另以独立 ASGI 临时夹具重放 versioned `/api/v1/fitness/checkins` 与 legacy `/fitness/checkin`：两者对篡改奖励均固定返回 `500 {"detail":"fitness state is invalid"}`，不含奖励正文、路径或堆栈，旧字节保持且无临时文件。
- 重新通过 `test_fitness_checkin.py`、`test_fitness_module.py`、`test_feature_catalog.py`、`test_dashboard_shell.py`、`test_focus_dashboard.py`。同日/并发幂等、6/12 天奖励、断签、原子失败、新旧接口、Origin、版本化零 TTS 和控制台零业务存储继续通过。
- 生产路径扫描仍只有 repository 默认路径与 API composition 指向 `server/data/fitness_checkins.json`，catalog 只声明该所有权；旧 `server/systems/data/fitness_checkins.json` 不存在。真实文件只检查存在性和定向 Git 状态，未读取、打印、diff、迁移、reset 或覆盖。
- 相关 `compileall`、六项 dashboard JavaScript `node --check`、任务文档门禁与 `git diff --check` 通过。未暂存、提交、推送、发布或清理工作区。

## 2026-07-30 PK-011 可安装化增量

### 实施结果

- 新增 `package_source/manifest.json`，冻结 `fitness@1.0.0`、
  `backend.register`、`/api/v1/fitness`、三条 `/fitness/*` legacy 接缝、
  `dashboard/index.js`、`data_namespace=fitness`、唯一 `local_state` 权限和
  `requires_restart=true`。包没有配置 Schema、sidecar、命令、安装脚本或新端口。
- 新增 `module.py` 作为安装包 composition 接缝。新装配必须显式提供
  `fitness_state_path`，可选注入 `fitness_audio_synthesizer` 和
  `fitness_local_control_guard`；同一个 `FitnessService/FitnessRepository`
  同时承载 versioned 与 legacy 路由。完整既有五路由装配只复用一次，重复 register
  幂等；部分、重复或异名路由失败关闭。
- 新增确定性 `package_builder.py`。ZIP allowlist 固定为根 manifest、
  `dashboard/index.js`、生成的 `backend/__init__.py` 与
  `models/module/repository/router/security/service.py`，共 9 个 UTF-8/LF 文件；
  使用稳定排序、固定时间、固定 Unix 普通文件 mode 和 `ZIP_STORED`。不扫描功能
  目录，不会把状态、`.env`、缓存、模型资产、vendor、测试或脚本带入包。
- 新增动态面板，只使用 `context.root/request/notify`，挂载仅调用一次版本化
  status GET；点击打卡才发送只含 note 的版本化 check-in，随后刷新状态。
  面板保留今日状态、连续天数、累计打卡、下次奖励、备注和按钮，不提供 reset，
  不访问其他 DOM/API，也不使用 `localStorage/sessionStorage`。
- 新增 release fragment、完整 Catalog entry 和发布交接说明。确定性
  `fitness-1.0.0.zip` 为 30494 字节，SHA-256
  `7efa416e1b5e9d6c9d83c8fa63ebb3a16700d7b662ea1b64a2d05e0bd8c87a4f`；
  根 manifest SHA-256
  `c75d781def193b232d6389bc3e450033d1dfcf0c663d2602ff544024d642162e`。
  本轮没有修改官方 Catalog 或创建/上传 GitHub Release。
- 扩展 `test_fitness_module.py` 的专属隔离回归：真实构建两份逐字节相同 ZIP，
  通过 ModuleManager 安装/启用/停用/卸载/重装，验证动态资产启停、受保护历史
  重关联、精确 purge 只删除临时 `data/modules/fitness/`、完整既有路由复用和
  部分冲突失败。已安装包实际代码继续覆盖同日/并发幂等、6/12 天奖励、断签、
  原子替换失败、损坏状态、四类奖励篡改、新旧 API、版本化零 TTS、legacy 可选
  音频 Provider 和控制台挂载零写入；全部状态、registry、runtime、data 和 ZIP
  均在系统临时目录。

### 共享冻结与集成交接

- `TASKS.md`、`server/api.py`、Catalog、公共 dashboard、README、
  `server/core/modules/` 和架构文档均未修改；真实
  `server/data/fitness_checkins.json` 仍只检查存在性和 Git 状态，旧 systems
  候选仍不存在，二者都没有被测试、读取、diff、迁移、打包或写入。
- 当前共享 `api.py` 仍保留内置 fitness composition，公共 dashboard 仍保留
  legacy fitness DOM，Catalog 仍登记旧 `modular` 状态。这是冻结共享窗口下的
  预期集成接缝：启用包时 `backend.register` 可复用完整既有路由而不重复；
  PK-000 后续串行集成时需设置显式 `app.state.fitness_state_path`/Provider，
  移除静态业务装配与 legacy 面板并合并 release/Catalog。完成该共享切换前，
  当前主应用的静态路由不会随包停用而消失，且动态面板可能与 legacy 面板并存；
  专属临时 app 已验证切换后的完整启停语义。
- 没有发现需要增加 manifest 字段、权限、生命周期状态、API、日期或奖励规则的
  公共契约变化。多 worker 对同一 JSON 的跨进程锁仍是原有遗留风险，不在本增量
  扩张。

### PK-011 增量文档门禁

- [x] TASK_RECORD — 已记录包身份、allowlist、Provider/路由接缝、动态面板、
  release 摘要、数据/purge 边界、测试和共享集成交接。
- [x] TASKS_BOARD — PK-000 已在共享任务板把 PK-170 置“进行中”并补充
  PK-010/PK-100 依赖；按本轮明确冻结要求未修改 `TASKS.md`，本任务文件置
  “待集成”，任务板由 PK-000 串行回写。
- [x] PUBLIC_README — 不适用：README 属于本批共享冻结窗口；fitness 专属
  `release/README.md` 已提供准确构建、数据保留、重启和发布交接。
- [x] MODULE_CATALOG — 不适用：共享 Catalog 冻结；已交付通过冻结 Schema 的
  manifest、release fragment 和完整 Catalog entry，等待 PK-000 合并。
- [x] ARCHITECTURE_DOCS — 不适用：没有改变 PK-010/PK-100 公共契约；实现严格
  消费 `module-package-contract.md`、`installable-modules.md` 与模块化单体边界。
- [x] LOCAL_README — 不适用：没有改变本机路径、端口、启动器、解释器或环境；
  构建和生命周期状态全部位于系统临时目录。
- [x] AGENT_RULES — 不适用：没有改变 agent 工作流、安全、验证、文档或 Git
  规则，未修改 `AGENTS.md`。
- [x] VALIDATION — 通过项目 Python 3.12 运行时与项目依赖路径实际复跑
  `test_fitness_checkin.py`、`test_fitness_module.py`、
  `test_feature_catalog.py`、`test_dashboard_shell.py`、
  `test_installable_modules.py`、`test_official_module_catalog.py`；全部通过。
  `compileall -q features\fitness tests\test_fitness_module.py
  tests\test_fitness_checkin.py`、动态 `dashboard/index.js` 的 `node --check`、
  `scripts/check_task_docs.py`（最终运行时 21 项）均通过。`ruff` 基线已尝试，但当前项目、
  migration venv 与 PATH 都没有 ruff/uv，固定失败为
  `No module named ruff`；未联网或静默安装依赖。最终 `git diff --check`
  零退出，仅输出混合工作区既存 LF→CRLF 提示；所有测试只使用临时
  data/registry/runtime/ZIP 和虚构内容。
