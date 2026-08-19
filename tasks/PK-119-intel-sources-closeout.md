# PK-119 — 情报来源事后收口、共享装配与冲突审计

- 状态：已完成
- 优先级：P0
- 所属模块：`intel_sources_integration`
- 依赖任务：PK-110、PK-115、PK-120、PK-130、PK-131、PK-132、PK-133、PK-134
- 负责路径：七项来源任务的实际代码/测试/任务记录审计；`server/api.py`、`server/intel/briefing.py`、`server/intel/intel_config.py`、`server/features/catalog/service.py`、`server/static/dashboard.html`、`README.md`、`TASKS.md`、相关架构文档及本任务测试/记录
- 当前对话：2026-07-22，由 PK-000 采用事后审计模式直接领取；不要求联系原七个任务对话

## 目标

从工作区实际实现重建 PK-115、PK-120、PK-130、PK-131、PK-132、PK-133、PK-134 的交付事实，审计并解决并行开发造成的共享装配、重复实现、覆盖遗漏和局部契约冲突，完成 API、Collector 注册、控制台、catalog、README、架构文档和任务状态的统一收口，再把完整批次交给 PK-900 独立验收。

## 不在本任务内

- 不凭聊天记录补写不存在的能力，也不要求原七个任务对话补发消息。
- 不重写整个来源业务；明确且局部的装配/兼容缺陷可以最小修复，重大业务缺失必须记录并退回所属任务。
- 不改变 Collector `1.0` 的公共模型、字段语义、source ID、兼容或版本规则；发现需要破坏性变更时立即停止并交回 PK-000。
- 不实施 PK-140，不触发真实来源、真实凭证、付费模型、TTS、QQ 或 Git 发布。

## 接口契约

- 公共 Collector：继续严格遵守 `docs/architecture/daily-briefing.md` 冻结的 Collector `1.0`。
- 版本化来源管理/API：依据七项实际 router/service/Collector 导出完成统一装配；保留现有 `/dashboard/intel-sources*` 与 briefing legacy 路径兼容。
- PK-110 只通过公共 Collector/Gateway 协议消费来源，不反向依赖各来源私有 repository 或状态文件。
- 共享控制台和 catalog 只登记实际已装配、可验证的能力，不预告未接线接口。

## 数据所有权

- 真实 `server/data/intel_sources.json`、briefing cache、X/B 站/论文缓存、`.env`、Cookie、Token、API Key、QQ runtime 和个人状态均为受保护本机数据。
- 审计和自动测试只使用 fake/MockTransport、固定时钟、临时目录和虚构配置；不得读取、打印、迁移、覆盖或 diff 真实内容。
- PK-119 只拥有共享装配与文档状态，不改变各来源既有数据所有权。

## 实施清单

- [x] 逐项读取七个任务的实际代码、测试和任务文件，重建接口、副作用、验证与遗留事项。
- [x] 运行七项专属测试并检查 Python 3.8 导入/编译兼容。
- [x] 审计 Collector `1.0` 实现、注册覆盖、重复 legacy 规则和跨来源失败隔离。
- [x] 完成共享 API、Collector composition、legacy 兼容、控制台和 catalog 装配。
- [x] 更新 README、架构说明、七项任务工作记录和本任务报告。
- [x] 运行 PK-110、来源配置、API/catalog/dashboard 共享回归及 `git diff --check`。
- [x] 全部通过后统一把 PK-115/119/120/130/131/132/133/134 改为“待集成”，登记新的 PK-900 批次。

## 验收标准

- 七项专属测试和共享回归在项目 Python 3.8 环境下通过，且不访问真实网络、真实配置或个人缓存。
- 八个公共 source ID 的生产装配无遗漏、重复调用或错误映射；来源失败继续相互隔离。
- 新旧 API、控制台、catalog、README、架构文档与实际装配一致。
- Collector `1.0` 未发生破坏性变化，秘密、来源名单、完整错误体和内部路径没有新增泄漏通道。
- 七项任务记录均依据实际源码补齐接口、数据副作用、验证和遗留内容，并完成八项文档门禁。
- 若无重大业务阻断，PK-115/119/120/130/131/132/133/134 统一进入“待集成”，PK-900 获得明确批次和验收范围。

## 工作记录

- 2026-07-22：PK-000 创建并领取 PK-119。采用事后审计模式，解除此前“必须由原对话补写交接”的流程依赖；仅以当前源码、测试、任务记录和实际命令为证据。

### 事后审计结论与冲突处理

- 七项来源专属实现均存在且具备 fake/MockTransport 定向测试；PK-115 提供原子来源 registry，PK-120/130 同时提供资料/缓存 service 与 Collector，PK-131/132/134 提供无独立路由的 Collector adapter，PK-133 提供三论文来源及 coordinator。没有发现需要退回的重大业务缺失。
- 共享装配遗漏已关闭：新增 `ProjectCollectorGateway`，按 `twitter/github/bilibili/youtube/money/arxiv/crossref/semantic` 八个冻结 source ID 分派平台 Collector 和论文 coordinator；单源失败、顺序及关闭生命周期有集成测试。`LegacyCollectorGateway` 与 `intel.briefing` 仅保留脚本/Python 兼容，不再是主 API composition root，避免两套生产采集并行。
- API 冲突已收口：来源 registry、新 X 和 B 站 router 在 `server/api.py` 统一装配；legacy `/dashboard/intel-sources*` 委托相同 registry/service。控制台改用版本化接口，catalog 只登记实际存在的公开 endpoint；YouTube 配置校验收紧到与 Collector 一致的标准 Channel ID。
- 文档/目录遗漏已关闭：README、daily briefing、modular monolith、catalog、七项任务记录和总板按实际实现同步。`server/intel/intel_config.py` 无需修改，Collector `1.0` 的模型、字段、source ID、状态和版本规则均未改变。
- 旧交接中记录的 Bilibili `list[str]` 与 papers `zoneinfo` Python 3.8 阻断在当前代码中均已修复，完整回归实际通过；这些历史记录保留，并由各任务的 PK-119 复核章节说明现状。

### 数据副作用与遗留

- 生产进程只有显式 briefing 生成/刷新/缺失补采才调用 Collector；读取当天完整缓存不采集。来源管理写入只更新 registry，X/B 资料/帖子操作只在对应显式 API 下写各自缓存；无新增常驻进程、端口或共享状态文件。
- 自动验证只使用 fake Collector、MockTransport、固定时钟、虚构配置和系统临时目录。未读取、打印、迁移、覆盖或 diff 真实来源名单、briefing/X/B/论文缓存、`.env`、Cookie、Token、API Key、QQ runtime 或个人状态。
- 非阻断遗留：PK-900 仍需独立复核启动/关闭、八源 dispatch、版本化与 legacy API、控制台、缓存零调用和秘密隔离；实际部署需重启主 API。上游站点可用性、限流与反爬属于已记录的运行降级，不在 PK-119 中伪造在线通过。

### 验证记录

- 七项专属共八个测试、`test_intel_sources_integration.py`、`test_intel_source_config.py`、PK-110 两项核心回归、`test_feature_catalog.py`、`test_dashboard_shell.py`、`test_conversation_consumers.py` 全部退出 0；控制台测试显式断言版本化来源/X/B 入口。
- `ProjectCollectorGateway` factory 在不联网条件下可构造并声明全部八个公共 source ID；相关 Python 文件编译检查通过。
- 最终 `scripts/check_task_docs.py` 通过并核对 18 个门禁任务；`git diff --check` 退出 0，仅有混合工作区既有 LF/CRLF 提示。对来源名单、briefing/X/B 缓存、`.env` 与 QQ runtime 的定向 `git status --short` 为空；只检查路径状态，未读取内容或详细差异。全工作区仍含其他任务和个人状态修改，未清理、覆盖、暂存、提交或推送。
- 2026-07-22 事后重建复验：将 `test_intel_sources_integration.py` 从基础 dispatch/CRUD 夹具扩展为直接覆盖生产 factory 的八源类型与受信配置、五个平台并发、三论文严格串行、单源失败与日志脱敏、registry 保存/增改删零采集、普通读取零网络、显式 generate/refresh、warning/URL/metadata/cache/prompt 脱敏、来源状态路径隔离、控制台只持久化折叠布尔值以及版本化/legacy briefing 结果兼容；未访问真实来源、配置、缓存或凭证。
- 本轮重新执行附件要求的 14 项来源/PK-110/catalog/dashboard 测试及 `test_conversation_consumers.py`，15 项均退出 0；扩展后的 API 装配检查同时拒绝重复 method/path 路由并确认新旧 briefing 与来源/X/B 路径。相关 Python `compileall`、六个 dashboard JavaScript 文件的 `node --check` 以及 `test_dashboard_shell.py` 的内联脚本编译均通过。`test_conversation_consumers.py` 在当前沙箱中记录了可选 focus runtime 目录的既有 `PermissionError` 降级提示，但测试断言与来源批次均通过。

## 完成文档门禁

- [x] TASK_RECORD — 已记录事后审计、冲突处理、接口、数据副作用、验证与遗留。
- [x] TASKS_BOARD — 八项任务已统一为“待集成”，PK-900 已登记新批次并保持“待开始”。
- [x] PUBLIC_README — 已按实际八源组合、版本化/legacy 接口和验证方式更新。
- [x] MODULE_CATALOG — 已按实际来源模块、公开端点、网络和数据边界更新。
- [x] ARCHITECTURE_DOCS — 已补充 ProjectCollectorGateway、论文协调、legacy 兼容和模块边界，Collector 1.0 未改变。
- [x] LOCAL_README — 不适用：本任务不改变本机路径、端口、解释器或环境位置。
- [x] AGENT_RULES — 不适用：事后审计为本批授权，不改变长期 agent 安全、验证、文档或 Git 规则。
- [x] VALIDATION — 15 项专属/集成/共享回归通过；扩展跨来源夹具逐项覆盖附件列出的 12 类集成保证，文档门禁、Python/JavaScript 编译、差异空白及受保护路径检查在最终状态同步后完成并记录。

## PK-000 最终复核（2026-07-22）

PK-900 报告及实际八源 composition、单源失败/关闭隔离、路由唯一性、脱敏和混合工作区边界经独立复核通过；PK-119 置为“已完成”。

## 独立对话启动提示

```text
继续 Project Kei 的 PK-119 事后收口任务。先读取项目规则、七个来源任务和实际
代码/测试，只依据工作区证据重建交付。Collector 1.0 保持冻结；局部装配缺陷最小
修复，重大业务缺失记录退回。禁止读取真实来源配置、缓存或凭证，不执行 Git 发布。
```

## PK-900 逆向退回整改（2026-07-22）

- 接受 PK-900 的“不通过”结论；此前“规定回归通过”不能替代逆向副作用、安全和关闭生命周期验收。PK-900 保持“进行中”，本任务及七个来源任务保持“待集成”。
- dashboard 打开时对 X/B 资料仅调用只读 cache GET；来源增改删成功后不再隐式 resolve。新增 `GET /api/v1/x/profiles` 与只读 service，未缓存项只提示用户点击“刷新资料”，只有显式刷新按钮调用联网入口。
- legacy `/dashboard/intel-sources*` 的读、写及 X/B 联网入口统一复用 `_is_local_control_request`，与 versioned API 一致拒绝恶意浏览器 Origin，同时保留无 Origin 的本机工具兼容。
- `ProjectCollectorGateway.aclose()` 按对象身份去重，逐个隔离 closer 异常，尝试全部平台/论文 Collector 后才抛出有界 `CollectorCloseError`；错误不包含异常正文。
- `test_intel_sources_integration.py` 新增首/中/末 closer 失败、重复对象，以及 legacy/versioned 参数化恶意 Origin、临时 registry 零写入和 fake fetcher 零调用回归。整改测试只使用虚构数据、临时目录、ASGITransport 和 fake；未读取或访问真实来源、缓存、凭证或个人状态。
- 整改后重新执行 PK-900 登记的 15 项规定回归，全部退出 0；相关 Python `compileall`、6 项 dashboard JavaScript `node --check`、18 项文档门禁和 `git diff --check` 均通过。差异检查仅有工作区既有 LF/CRLF 提示。
- 本节只登记责任任务完成的最小整改与自测，不宣告 PK-900 通过；须由 PK-900 使用原逆向夹具独立复验后决定批次结论。
