# Project Kei 任务总板

本文件是项目内的任务入口。总控对话只维护架构、优先级和集成；具体功能应在独立 Codex 对话中，按对应任务文件推进。

## 使用方式

1. 新建一个以任务 ID 开头的对话，例如 `PK-120 X 用户监控模块`。
2. 在第一条消息中要求 agent 先读取 `README.md`、`AGENTS.md`、`README.local.md`（如存在）和对应的 `tasks/PK-xxx-*.md`。
3. 一个对话默认只领取一个任务；跨模块改动先在 `PK-000` 总控任务确认接口。
4. 开始工作时把任务状态改成“进行中”，完成验证后改成“待集成”；只有总控验收后才改成“已完成”。
5. 任务实现必须记录实际接口、数据副作用、测试结果和未解决问题，不能只在聊天里交接。

## 完成文档门禁

任务进入“待集成”或“已完成”前，任务文件必须增加 `## 完成文档门禁`，并勾选以下八项。适用时更新对应文件；不适用时也要勾选并写明理由，不能留空。

| 检查键 | 负责内容 |
|---|---|
| `TASK_RECORD` | 对应任务文件的功能、接口、副作用、验证和遗留问题 |
| `TASKS_BOARD` | 本总板中的状态、名称、优先级和依赖 |
| `PUBLIC_README` | 用户可见功能、接口、配置、重启要求、数据影响、测试和限制 |
| `MODULE_CATALOG` | `/api/v1/modules` 中的模块映射、接口、进程边界和迁移状态 |
| `ARCHITECTURE_DOCS` | 模块边界、依赖、manifest、生命周期或专项协议 |
| `LOCAL_README` | 仅本机路径、启动器、解释器、端口和环境位置；不提交 |
| `AGENT_RULES` | agent 工作流、安全、验证、文档或 Git 规则 |
| `VALIDATION` | 实际运行的测试和 `git diff --check` 结果 |

不得把同一功能全文复制到所有说明文件；各文件只维护表中属于自己的信息。运行 `server/.venv-asr/Scripts/python.exe scripts/check_task_docs.py` 可检查所有“待集成/已完成”任务是否满足门禁。

## 状态定义

| 状态 | 含义 |
|---|---|
| 待开始 | 已规划，尚未领取 |
| 进行中 | 正在独立对话中设计或实现 |
| 待集成 | 功能已完成，等待总控兼容性验收 |
| 已完成 | 已通过集成验收 |
| 暂停 | 有明确阻塞或暂不推进 |

## 当前任务

| ID | 功能边界 | 状态 | 优先级 | 依赖任务 | 任务文件 |
|---|---|---|---|---|---|
| PK-000 | 架构总控与集成 | 进行中 | 持续 | 无 | [任务说明](tasks/PK-000-project-control.md) |
| PK-001 | 模块化基础与任务体系 | 已完成 | P0 | PK-000 | [任务说明](tasks/PK-001-modular-foundation.md) |
| PK-010 | 可安装模块生命周期与加载基础 | 待集成 | P0 | PK-001 | [任务说明](tasks/PK-010-installable-modules.md) |
| PK-011 | 全量业务模块可安装化与官方发布 | 已完成 | P0 | PK-010、PK-100、PK-180 | [任务说明](tasks/PK-011-installable-module-rollout.md) |
| PK-020 | Windows 安装、环境锁定与可移植启动 | 待集成 | P0 | PK-001、PK-010、PK-100、PK-140、PK-200、PK-210、PK-211、PK-212 | [任务说明](tasks/PK-020-windows-install.md) |
| PK-030 | Python 测试发现、质量基线与 CI 收编 | 已完成 | P0 | PK-001、PK-020 | [任务说明](tasks/PK-030-python-test-quality.md) |
| PK-100 | 控制台公共外壳 | 已完成 | P1 | PK-001、PK-010 | [任务说明](tasks/PK-100-dashboard-shell.md) |
| PK-110 | 每日情报核心、缓存与 Kei 播报 | 待集成 | P1 | PK-001、PK-010、PK-100、PK-200 | [任务说明](tasks/PK-110-daily-briefing.md) |
| PK-115 | 每日情报来源注册表与配置 | 已完成 | P1 | PK-001、PK-010、PK-100、PK-110 | [任务说明](tasks/PK-115-intel-source-registry.md) |
| PK-119 | 情报来源事后收口、共享装配与冲突审计 | 已完成 | P0 | PK-110、PK-115、PK-120、PK-130、PK-131、PK-132、PK-133、PK-134 | [任务说明](tasks/PK-119-intel-sources-closeout.md) |
| PK-120 | X/Nitter 用户资料与今日言论 | 已完成 | P1 | PK-001、PK-010、PK-100、PK-110、PK-115 | [任务说明](tasks/PK-120-x-monitor.md) |
| PK-130 | B 站资料与动态采集 | 待集成 | P1 | PK-001、PK-010、PK-100、PK-110、PK-115 | [任务说明](tasks/PK-130-bilibili.md) |
| PK-131 | YouTube 频道采集 | 待集成 | P2 | PK-001、PK-010、PK-100、PK-110、PK-115 | [任务说明](tasks/PK-131-youtube.md) |
| PK-132 | GitHub 用户与仓库采集 | 待集成 | P2 | PK-001、PK-010、PK-100、PK-110、PK-115 | [任务说明](tasks/PK-132-github.md) |
| PK-133 | 论文来源、作者追踪与今日论文展示 | 待集成 | P0 | PK-001、PK-010、PK-100、PK-110、PK-115 | [任务说明](tasks/PK-133-papers.md) |
| PK-134 | RSS 与信息差来源 | 待集成 | P2 | PK-001、PK-010、PK-100、PK-110、PK-115 | [任务说明](tasks/PK-134-rss.md) |
| PK-140 | QQ bridge、定时推送与业务私聊菜单 | 待集成 | P1 | PK-001、PK-010、PK-100、PK-110、PK-150、PK-170、PK-180、PK-190、PK-200 | [任务说明](tasks/PK-140-qq-bridge.md) |
| PK-150 | 斩妖除魔 | 待集成 | P1 | PK-001、PK-010、PK-100、PK-200 | [任务说明](tasks/PK-150-demon-slayer.md) |
| PK-160 | 好感度与长期记忆 | 待集成 | P2 | PK-001、PK-010、PK-100、PK-200 | [任务说明](tasks/PK-160-affection-memory.md) |
| PK-170 | 健身打卡 | 已完成 | P2 | PK-001、PK-010、PK-100 | [任务说明](tasks/PK-170-fitness.md) |
| PK-180 | 专注计时与首个可安装模块试点 | 待集成 | P1 | PK-001、PK-010、PK-100 | [任务说明](tasks/PK-180-focus.md) |
| PK-190 | 日历备忘与修炼记录 | 待集成 | P2 | PK-001、PK-010、PK-100 | [任务说明](tasks/PK-190-calendar.md) |
| PK-200 | LLM 对话与模型方案 | 待集成 | P1 | PK-001、PK-010、PK-100 | [任务说明](tasks/PK-200-conversation-llm.md) |
| PK-210 | 语音公共契约与编排 | 已完成 | P1 | PK-001、PK-010、PK-100、PK-200 | [任务说明](tasks/PK-210-voice.md) |
| PK-211 | GPT-SoVITS Engine Provider 与受控获取 | 已完成 | P1 | PK-010、PK-100、PK-210 | [任务说明](tasks/PK-211-gpt-sovits-engine-provider.md) |
| PK-212 | Voice Pack 注册表与 Kei 模型包 | 待集成 | P1 | PK-010、PK-100、PK-210 | [任务说明](tasks/PK-212-voice-pack.md) |
| PK-213 | Voice Pack 发布、远程获取与一键安装 | 待集成 | P1 | PK-010、PK-020、PK-100、PK-211、PK-212 | [任务说明](tasks/PK-213-voice-pack-distribution.md) |
| PK-900 | 版本集成与发布验收 | 已完成 | P0 | PK-010、PK-020、PK-030、PK-100、PK-115、PK-140、PK-170、PK-210、PK-211（本批次） | [任务说明](tasks/PK-900-integration-release.md) |

## 并行情报来源批次（2026-07-22）

- 批次任务：`PK-115 + PK-120 + PK-130 + PK-131 + PK-132 + PK-133 + PK-134`；PK-140 不属于本批，待来源批次完成集成后再独立推进。
- 共同依赖：Collector 1.0 已冻结，所有任务必须实现 [Collector 1.0 冻结契约](docs/architecture/daily-briefing.md)。PK-110 当前“待集成”仅为生成进度可观测性增量复验，不改变下游契约；若需要改变公共模型、字段语义、source ID、兼容或版本规则，立即停止实现并交回 PK-000。
- 并行状态：总控已一次性把七项登记为“进行中”。各对话完成专属代码、定向测试和任务记录后，只在自己的任务文件中把“并行阶段交接状态”记为“共享集成待排队”；不得自行修改本总板或进入“待集成”。
- 并行期间冻结：`TASKS.md`、`README.md`、`AGENTS.md`、`server/api.py`、`server/static/dashboard.html`、`server/features/catalog/service.py`、`server/intel/briefing.py`、`server/intel/intel_config.py`、`docs/architecture/daily-briefing.md`、`docs/architecture/modular-monolith.md`。未在下表明确分配的跨来源文件同样视为共享路径，必须先交回 PK-000。

### 专属路径所有权

| 任务 | 并行阶段唯一可修改的实现路径 | 专属测试 | 任务记录 |
|---|---|---|---|
| PK-115 | `server/services/intel_source_config.py`、`server/features/intel_sources/**` | `server/tests/test_intel_source_config.py`、新建 `server/tests/test_intel_sources_*.py` | `tasks/PK-115-intel-source-registry.md` |
| PK-120 | `server/services/x_profile_cache.py`、`server/services/x_daily_posts.py`、`server/intel/collectors/twitter.py`、`server/features/x_monitor/**` | 新建 `server/tests/test_x_*.py` | `tasks/PK-120-x-monitor.md` |
| PK-130 | `server/services/bilibili_profile_cache.py`、`server/intel/collectors/bilibili.py`、`server/features/bilibili/**` | 新建 `server/tests/test_bilibili_*.py` | `tasks/PK-130-bilibili.md` |
| PK-131 | `server/intel/collectors/youtube.py`、`server/features/youtube/**` | 新建 `server/tests/test_youtube_collector.py` 或 `test_youtube_feature_*.py` | `tasks/PK-131-youtube.md` |
| PK-132 | `server/intel/collectors/github.py`、`server/features/github_intel/**` | 新建 `server/tests/test_github_intel_*.py` | `tasks/PK-132-github.md` |
| PK-133 | `server/intel/collectors/arxiv.py`、`server/intel/collectors/papers.py`、`server/features/papers/**` | 新建 `server/tests/test_papers_*.py` | `tasks/PK-133-papers.md` |
| PK-134 | `server/intel/collectors/money_tips.py`、`server/features/rss_intel/**` | 新建 `server/tests/test_rss_intel_*.py` | `tasks/PK-134-rss.md` |

真实 `server/data/intel_sources.json`、来源缓存、Cookie、Token、API Key、`.env` 和现有联网 debug 脚本不属于任何任务的可修改/验收数据。所有测试必须使用假 HTTP、假 Collector、临时目录和虚构配置。

### 共享文件串行窗口顺序

1. PK-000 汇总七项“共享集成待排队”记录，确认专属测试全部通过，并指定唯一串行集成所有者。
2. 如确有已批准的高级来源配置接线，先处理 `server/intel/intel_config.py`；否则保持不变。
3. 处理 `server/intel/briefing.py` 的 legacy gateway/聚合接线，不改变 Collector 1.0。
4. 处理 `server/api.py` 的 router/service 装配，再更新 `server/features/catalog/service.py` 的目录映射。
5. 最后处理 `server/static/dashboard.html` 的兼容控制台接线；各任务新增的独立静态资源必须先已在专属路径内完成。
6. 共享集成测试通过后，按实际变化依次更新 `docs/architecture/modular-monolith.md`、`README.md`；`docs/architecture/daily-briefing.md` 只允许记录非破坏性实现说明，任何契约变化仍须另行决策；`AGENTS.md` 仅在协作/安全规则确有变化时更新。
7. 完成各任务八项文档门禁后，由 PK-000 最后一次串行更新 `TASKS.md`，把具备条件的任务登记为“待集成”，再安排 PK-900 批次。

### PK-119 事后收口结果（2026-07-22）

- PK-119 已依据实际源码、测试和任务记录完成事后审计，无需原七个对话补发消息；共享 API、八源 Collector composition、legacy 兼容、控制台、catalog、README 与架构文档已串行收口。
- Collector `1.0` 保持冻结。确认通过的 `PK-115 + PK-119 + PK-120 + PK-130 + PK-131 + PK-132 + PK-133 + PK-134` 已统一进入“待集成”，交由新一轮 PK-900 独立验收；此处不提前标记“已完成”。

### 来源批次最终关闭（2026-07-22）

- PK-900 完成整改复验后，PK-000 独立抽查原子配置、零网络读取/保存、单源失败隔离、敏感信息清洗、RSS 重定向防护、路由唯一性和混合工作区边界，结论通过。
- `PK-115 + PK-119 + PK-120 + PK-130 + PK-131 + PK-132 + PK-133 + PK-134 + PK-900` 已统一标记“已完成”；Collector 契约继续冻结为 `1.0`。
- PK-140 的 PK-001、PK-110 依赖已满足，可以另行入场；当前仍保持“待开始”，不在本次关闭动作中提前领取。

## 共同约束

- 目标架构是模块化单体；除 QQ bridge、ASR、GPT-SoVITS 外，不擅自增加常驻进程或端口。
- 新模块优先使用 `/api/v1/<module>` 命名空间；迁移期间保留现有接口作为兼容入口。
- 模块只能通过公开 service/API 契约协作，不直接修改其他模块的本地状态文件。
- `server/api.py` 最终只负责应用装配、公共中间件和兼容入口，业务路由逐项迁出。
- 按需安装遵守 `docs/architecture/installable-modules.md`；可安装不等于微服务化，普通业务默认仍是进程内模块。
- 所有密钥、Cookie、缓存和个人状态继续遵守 `AGENTS.md` 的安全边界。
