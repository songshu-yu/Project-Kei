# PK-240 — 每日生活预报

- 状态：已完成
- 优先级：P1
- 所属模块：`life_forecast`
- 依赖任务：PK-010、PK-100
- 负责路径：`server/features/life_forecast/**`、`server/tests/test_life_forecast_module.py`、本任务文档与对应公开说明/目录条目
- 当前对话：2026-08-19 独立功能任务；实现天气事实、生活建议和本地娱乐运势，不修改 daily briefing、calendar、QQ 或个人状态契约

## 目标

提供独立可安装的每日生活预报模块：只在用户显式刷新时通过可替换 Provider 获取天气与空气质量，按用户本地日期原子缓存，并在控制台严格分隔天气事实、生活建议和可关闭的本地娱乐运势。

## 不在本任务内

- 不修改 PK-110 每日情报的采集、缓存、改写或调度。
- 不修改 PK-140 QQ bridge 的发送、计划任务或 at-most-once 状态。
- 不修改 PK-190 日历、relationship/memory、个人状态、模型、语音或 server runtime。
- 不自动定位、不读取系统定位，不向第三方发送生日、星座或娱乐运势输入。
- 不增加后台联网、启动联网、页面加载联网或普通缓存读取联网。

## 接口契约

- 目标命名空间：`/api/v1/life-forecast`。
- `GET /api/v1/life-forecast/today`：只读本地今天缓存；跨天旧缓存不作为今天返回。
- `GET /api/v1/life-forecast/config`：只读本机位置/Provider/娱乐开关配置。
- `PUT /api/v1/life-forecast/config`：显式保存经验证的本机配置，不联网。
- `POST /api/v1/life-forecast/refresh`：唯一联网入口；串行刷新，失败保留旧缓存。
- 公共 Python 契约：`WeatherProvider.fetch(location, local_date) -> ForecastResult`；Provider 接收经验证的经纬度与本地日期，输出已规范化事实，不拥有缓存、配置或娱乐规则。
- 供未来 PK-110/PK-140 消费的需求仅登记为只读摘要 Provider/API；本任务不接线，交 PK-000 串行确认。

## 数据所有权

- `server/data/modules/life_forecast/config.json`：本机隐私配置，包含城市显示名、经纬度、Provider 与娱乐开关；Git 忽略。
- `server/data/modules/life_forecast/cache/YYYY-MM-DD.json`：按用户本地日期分文件的规范化缓存；Git 忽略。
- 模块不读取或修改 briefing、calendar、QQ、relationship/memory 或其他个人状态。
- 普通读取无写入、无网络；配置保存仅写配置；刷新成功仅原子替换当天缓存。

## Provider 与许可审计

- 第一版实现 `disabled` 与 `open_meteo`。默认 `disabled`；只有用户明确选择 Open-Meteo 并点击刷新才会把经纬度发送到其固定 HTTPS API，城市显示名始终留在本机。
- Open-Meteo Weather/Air Quality API 数据为 CC BY 4.0；控制台和缓存响应保留 Open-Meteo 与 CAMS 署名链接。免费公共服务只适合非商业、低频使用；商业部署需自行核对并使用其商业端点/许可，本模块不内置 API Key。
- Open-Meteo 不提供本模块可消费的官方灾害预警字段，因此第一版预警明确返回 `unavailable`，不根据普通天气代码伪造官方预警。
- 娱乐运势完全本地生成，不使用第三方 API。公开规则为：对 `规则版本 + 本地日期` 做 SHA-256，从固定文案表选取三项；同一日期稳定、跨日期变化、可关闭，并始终标注“娱乐内容、非事实预测”。

## 验收标准

- 天气事实包含条件、最高/最低温、降水概率、风力、体感温度、预警可用性；空气质量或上游缺字段时明确 unavailable。
- 生活建议至少覆盖穿衣、出行/带伞、紫外线与空气质量，且只基于已规范化事实。
- Provider 超时、429、5xx、恶意文本、单位/时区异常安全降级，不泄露上游正文或位置到错误。
- 当天缓存读取零网络；跨日、DST、损坏缓存、原子失败和并发刷新语义有自动测试。
- 位置、秘密、上游正文不进入日志、安装包、目录或非必要 API 响应。
- manifest、动态面板、确定性 ZIP、官方 Catalog fragment/entry、README 和专项架构说明齐全。

## 实施清单

- [x] 审计实际仓库、混合工作区与未占用 PK 编号
- [x] 冻结 Provider/结果/缓存边界和许可方案
- [x] 实现 models/repository/providers/service/router/module
- [x] 实现三分区动态控制台与零上游网络交互
- [x] 实现 manifest、确定性 builder、Catalog fragment/entry 和 release README
- [x] 补齐 fake/MockTransport/固定时钟/临时路径测试
- [x] 更新公开 README、目录与架构说明
- [x] 运行定向测试、文档门禁和 `git diff --check`

## 工作记录

- 2026-08-19：只读检查 Git 状态，确认工作区已有 README/TASKS/catalog/机器人等未提交改动并全部视为用户所有；未读取 `.env`、真实缓存、个人状态、runtime 或 vendor。
- 2026-08-19：审计 `TASKS.md`、全部 `tasks/PK-*.md` 文件名与仓库相关关键词，确认 PK-240 未被登记或引用；正式领取 PK-240，不复用已有编号。
- 2026-08-19：官方文档审计 Open-Meteo 天气、空气质量、许可与公共服务限制；决定默认禁用、显式选择/刷新才联网，位置标签本地保存，灾害预警 unavailable，本地娱乐规则不接触敏感输入。
- 2026-08-19：实现 `contracts/models/repository/providers/service/router/module` 分层，冻结 WeatherProvider/ForecastResult 1.0；天气响应只使用本地天气代码表和经验证数值，温度/风速统一为 °C/km/h，未知单位、日期、时区、代码、超时、429/5xx 使用有限错误码。
- 2026-08-19：实现本机配置、日期缓存、位置指纹、唯一临时文件 + `fsync/os.replace` 原子提交和并发 refresh 合并。普通读取只看注入时钟的今天文件；旧日、损坏或配置变化返回空事实。AQI 单独失败降级 unavailable；天气/解析/保存失败不覆盖旧缓存。
- 2026-08-19：实现动态紧凑面板，保存城市/经纬度、Provider 与娱乐开关，显式刷新；按“天气事实 / 生活建议 / 娱乐运势”三个 ARIA 区块展示，复用公共三主题/折叠/响应式/头像接缝，不使用 `fetch`、localStorage 或 sessionStorage。
- 2026-08-19：实现 `life_forecast@1.0.0` manifest、确定性 builder、发布 fragment/entry 和 release README。双次 ZIP 构建逐字节一致，最终大小 43495 字节，package SHA-256 `b1f981a23e6fca2dcb4cd056c47ef25c9aa3d03a61111fe4a3a498b45eeb3a99`，manifest SHA-256 `ef3673c9f973c9b231c41ed03649e7e046a0c07f67dc61c7431860c07336986c`；没有 ZIP 写入仓库或发布。
- 2026-08-19：更新 `/api/v1/modules` 静态边界映射、README、专项架构和测试清单；共享生产 official-catalog 未合并，因为目标 Release 尚不存在，fragment/entry 交 PK-000/PK-900 串行核验与发布。
- 2026-08-19：用户确认希望接入每日情报和 QQ。已把“每日情报逐项开关 + QQ 总开关/固定关键词/菜单按钮”收敛为下述串行集成需求；未修改 PK-110/PK-140 的冻结契约、配置、菜单、路由、调度、缓存或发送状态机。

## 实际交付接口

- `GET /api/v1/life-forecast/today`：只读今天缓存，返回 `cache_status/forecast/life_advice/fortune`；无上游网络、无写入。
- `GET /api/v1/life-forecast/config`：为 loopback 控制台返回编辑所需的城市、坐标、Provider、娱乐开关与隐私提示。
- `PUT /api/v1/life-forecast/config`：只做本机验证/原子保存；不触发刷新。
- `POST /api/v1/life-forecast/refresh`：唯一上游联网 API；成功原子提交，失败保留旧缓存，并发请求合并。
- Python Provider 1.0：`WeatherProvider.fetch(LocationConfig, date) -> ForecastResult`；`ForecastResult` 为不可变、Provider 中立的规范化事实。

## 数据副作用

- 配置写入：仅用户显式 PUT 时写 `server/data/modules/life_forecast/config.json`。
- 缓存写入：仅成功显式 refresh 时写 `server/data/modules/life_forecast/cache/YYYY-MM-DD.json`。
- 外部网络：仅 `open_meteo` 已选择且显式 refresh 时访问两个固定 HTTPS host；测试未发真实请求。
- 本次实现/验证未读取或修改真实模块数据、缓存、`.env`、Token、定位、QQ、LLM、TTS、个人状态、server/runtime 或 vendor；未暂存、提交、推送、发布或清理工作区。

## 验证记录

- `python -m pytest -c NUL server/tests/test_life_forecast_module.py -q`：17 passed；使用 fake/MockTransport、固定时钟和临时目录。
- `.venv/Scripts/python.exe` + ASGITransport 临时 smoke：版本化 config/today/refresh API 通过。
- `.venv/Scripts/python.exe` + 临时 ModuleManager/Loader：安装、启用、重启装载、路由、停用、卸载保留数据通过。
- `server/.venv-asr/Scripts/python.exe tests/test_feature_catalog.py`：通过。
- `node --check server/features/life_forecast/package_source/dashboard/index.js`：通过。
- `python -m compileall -q ...`：life_forecast、专项测试、catalog 相关文件通过。
- `scripts/build_official_module_catalog.py` 使用临时 ZIP：fragment schema、计算结果与受跟踪 entry 精确相等。
- `git diff --check`：退出 0，仅有工作区既存 LF→CRLF 提示。
- Ruff：当前 root `.venv`、base Python 与迁移期 `server/.venv-asr` 均未安装 ruff，因此未执行；没有安装或混装依赖。
- `scripts/check_python_test_inventory.py`：共享清单仍因入场前已有未跟踪 `test_learning_module.py` 报 missing；PK-240 自身已登记。
- `test_dashboard_shell.py`：PK-240 候选已纳入预期，但共享工作区另有入场前未跟踪 `learning/package_source/manifest.json`，因此实际 21 与本任务预期 20 不符；未越界吸收或隐藏 PK-230 工作。

## 遗留集成项

- PK-000/PK-900：在独立串行窗口审计并决定是否把 `life_forecast@1.0.0` fragment 合入共享 official-catalog、创建不可变 Release asset；当前不宣称远程安装可用。
- PK-000/PK-230：先收口混合工作区的 learning manifest/测试清单，再复跑完整 dashboard shell 与 Python inventory；这不是 PK-240 数据或接口缺陷。
- PK-000：为下述每日情报/QQ 联动审计新的未占用 PK 编号并指定唯一串行所有者；联动只消费 PK-240 的只读当天摘要，不得在 PK-240 内直接改 PK-110/PK-140，也不得复制其调度、发送或缓存规则。
- PK-900：在项目正式 Python 3.10–3.13 dev 锁环境运行完整 pytest/ruff 和安装生命周期回归；当前可用环境分别缺 pytest/ruff 或是迁移期旧解释器。

## 完成文档门禁

- [x] TASK_RECORD — 已记录最终接口、副作用、验证、环境限制和遗留集成项。
- [x] TASKS_BOARD — 已同步 PK-240 名称、P1、依赖与“待集成”状态。
- [x] PUBLIC_README — 已更新功能、三分区呈现、配置/隐私、接口、缓存、许可、重启和限制。
- [x] MODULE_CATALOG — 已更新 `/api/v1/modules` 边界映射及模块 release fragment/entry；共享官方目录待 PK-000 发布窗口。
- [x] ARCHITECTURE_DOCS — 已新增 `docs/architecture/daily-life-forecast.md` 冻结 Provider、缓存、隐私和集成需求。
- [x] LOCAL_README — 不适用：不改变本机路径、启动器、解释器、端口或环境位置。
- [x] AGENT_RULES — 不适用：不改变 agent 协作、安全、验证或 Git 规则。
- [x] VALIDATION — 已记录 17 项专项、API/lifecycle smoke、catalog、JS、编译、fragment 和 diff 结果；共享/环境限制已如实列出。

## 给 PK-900 的验收重点

- 页面加载、卡片展开、Provider 切换和普通缓存读取均零网络。
- 只有显式 refresh 联网；失败不破坏旧缓存，跨天不冒充今天，并发请求至多执行一次刷新序列。
- 位置不进入日志、错误、模块 ZIP、Catalog 或 today 响应；config 只在 loopback 控制台按必要范围返回。
- Open-Meteo/CAMS 署名可见，预警/AQI 缺失明确 unavailable，娱乐分区与事实分区不可混淆。

## 2026-08-19 新增联动需求（交 PK-000）

此处登记产品需求和最小契约，不代表 PK-110/PK-140 已接线。PK-000 必须先审计未占用
编号、登记独立串行任务，再由对应路径所有者实现；PK-240 继续保持“待集成”。

### 每日情报投影

- 每日情报设置增加生活预报总开关和逐项开关；迁移默认全部关闭，避免升级后静默改变既有简报。
- 稳定字段 ID 为：`weather_condition`、`temperature_range`、`apparent_temperature`、
  `precipitation_probability`、`wind`、`alerts`、`clothing`、`travel_umbrella`、`uv`、
  `air_quality`、`fortune`。UI 可按“天气事实 / 生活建议 / 娱乐运势”分组，但保存值不得依赖中文标签。
- 开关只决定每日情报如何投影今天的只读摘要，不改变或复制 PK-240 缓存，也不触发 refresh、
  简报重新生成或上游网络。缺失、损坏、跨天或 unavailable 字段必须省略或明确不可用，不能拿旧日数据补位。
- `fortune` 采用双重许可：PK-240 本地娱乐开关和每日情报 `fortune` 项都开启才显示；输出必须保留
  “娱乐内容、非事实预测”，且不得混入天气事实段落。

### QQ 查询

- QQ 侧增加独立的生活预报总开关，迁移默认关闭；第一版不新增定时推送，也不修改既有 at-most-once 状态。
- 固定精确关键词建议冻结为：`每日生活预报`、`今日生活预报`、`生活预报`、`今日天气预报`；
  不匹配宽泛子串“天气”，避免截获普通对话。关键词表仍由 PK-140 所有。
- 私聊业务菜单增加固定按钮“生活预报”，action 建议为 `kei:life-forecast`。点击按钮与命中关键词
  走同一只读处理器；关闭时返回固定的未开启提示，开启时展示今天所有可用天气事实和生活建议。
- QQ 不复用每日情报的逐项开关，避免两个消费端配置相互耦合；娱乐运势仅在 PK-240 娱乐开关开启时附加，
  并完整保留免责声明。按钮/关键词读取不得刷新、写缓存或发送坐标、城市、生日、星座给第三方。

### 最小消费契约与验收

- 两个消费端只调用 `GET /api/v1/life-forecast/today` 或等价的进程内只读 Provider；响应只含
  `cache_status/forecast/life_advice/fortune`，不得扩散位置配置、坐标、Provider 秘密或 refresh 能力。
- 若串行实现需要新增专用摘要 API，只能是 `/api/v1/life-forecast` 下的兼容增量，并先由 PK-000
  冻结版本与字段；不得让 PK-110/PK-140 读取 PK-240 私有文件。
- 集成测试使用 fake 摘要和临时配置，覆盖默认关闭、逐项组合、固定关键词、固定 action、点击与关键词
  等价、跨天/损坏/unavailable、娱乐双开关与免责声明、零网络读取、无位置泄漏；禁止真实 QQ 或天气网络。

## 独立对话启动提示

```text
继续 Project Kei 的 PK-240 每日生活预报任务。先完整读取根 README.md、
AGENTS.md、README.local.md（如存在）、TASKS.md、本任务文件，以及 PK-010、
PK-100、PK-110、PK-140、PK-190 和相关架构文档。只修改 life_forecast 专属路径
及已登记的最小目录/文档接缝；不得读取真实个人状态、缓存、.env、runtime 或 vendor。
```

## PK-000 最终运行态复核（2026-08-20）

- PK-900 已独立通过源码候选验收：17 项离线专项通过，确定性包为 43,495 bytes，SHA-256
  `b1f981a23e6fca2dcb4cd056c47ef25c9aa3d03a61111fe4a3a498b45eeb3a99`。
- PK-000 通过正式 ModuleManager 本地 ZIP 流程安装并启用 `life_forecast@1.0.0`，随后经受控
  supervisor 重启 Core；没有直接修改 registry 或 runtime 文件。
- 重启后只读核对：`GET /api/v1/modules` 返回 `install_status=enabled`、`enabled=true`，模块静态入口
  `/api/v1/modules/life_forecast/assets/dashboard/index.js` 返回 200，`GET /api/v1/life-forecast/today`
  返回 200。
- 真实浏览器控制台已出现“每日生活预报”卡片；展开后可见城市显示名、经纬度、Provider、娱乐运势开关、
  “保存本机配置”和“显式刷新”，当前为 provider disabled、缓存 missing 的安全初始状态。
- 本次运行态复核没有点击“保存本机配置”或“显式刷新”，没有读取、打印或写入真实位置/缓存，也没有发起
  Open-Meteo、QQ、LLM、TTS 或其他业务网络请求。
- PK-240 实现、独立验收和正式本机生命周期/控制台装载均通过，状态由 PK-000 收口为“已完成”。官方远程
  Release/Catalog 发布仍是独立发布动作；在不可变 Release asset 存在前，不宣称其他用户可远程一键安装。
