# PK-020 — Windows 安装、环境锁定与可移植启动

- 状态：待集成
- 优先级：P0
- 所属模块：`project_tooling`
- 依赖任务：PK-001、PK-010、PK-100、PK-140、PK-200、PK-210、PK-211、PK-212
- 负责路径：根目录安装/诊断/启动入口，`scripts/` 中对应 PowerShell 编排与公共路径解析，受版本控制的 Python/Node 依赖声明和锁文件，现有 `server/start_*.bat`、`server/scripts/start_*.ps1`、`server/qq_bridge/start_qq_bridge.bat` 的可移植兼容接缝，安装专项测试、Windows CI、安装与迁移文档
- 当前对话：2026-08-10 Windows voice-media hash lock 增量，待新的 PK-900/PK-000 验收

## 总控定位

PK-020 是项目级 Windows 交付与运行工具任务。它统一负责 Project Kei 的环境版本、依赖分层、安装入口、环境诊断和可移植启动，不归属于 QQ、语音、情报或其他业务模块，也不允许各业务模块另建一套安装逻辑。

本任务的正式依赖关系如下：

- PK-001、PK-010、PK-100：提供当前模块化单体、可安装模块和控制台入口的稳定基线；PK-020 只让这些能力可安装、可启动，不改变模块生命周期或公共外壳契约。
- PK-200：提供 Core 对话/LLM 的现行可选配置与无秘密启动边界；PK-020 不管理 LLM Provider/Profile，不读取 API Key。
- PK-210：提供语音编排和 Core 在语音缺失时的降级契约；PK-020 不改变 ASR/TTS API。
- PK-211：是 GPT-SoVITS 外部引擎受控获取和本机登记的唯一所有者；PK-020 只调用其公开状态/显式获取说明，不复制下载器或引擎元数据。
- PK-212：是 Voice Pack 导入、注册和切换的唯一所有者；PK-020 只检查是否已配置，不扫描、移动或打包模型。
- PK-213：是后续 Voice Pack 发布、可信远程获取和一键安装的唯一所有者；它依赖
  PK-020 的可移植 Python/Windows 入口。PK-020 不反向依赖 PK-213，不复制其
  catalog、下载器、归档校验或发布工具，只允许在可选语音 profile 完成后显示
  用户下一步可显式执行的命令。
- PK-140：是 QQ sidecar、凭证和运行控制的唯一所有者；PK-020 只用现有 lockfile 安装公开 Node 依赖并提供可移植启动接缝，不读取 QQ `.env`。PK-140 已由 PK-000 最终复核并标记“已完成”，PK-020 未复制其凭证、Gateway、菜单或业务路由规则。

## 入场审计基线

2026-07-25 的总控审计只检查受 Git 跟踪的脚本、配置、依赖清单和公开文档，没有读取 `.env`、个人状态、缓存、模型、Voice Pack、外部 GPT-SoVITS 源码、现有虚拟环境或 `node_modules` 内容。已确认：

- 根目录不存在 `setup.bat`、`doctor.bat`、`start.bat` 及对应 `scripts/setup.ps1`、`scripts/doctor.ps1`、`scripts/start.ps1`。
- `server/scripts/start_asr.ps1` 含开发机 `E:` 盘 GPT-SoVITS 绝对路径，并固定使用 `server/.venv-asr/Scripts/python.exe`；`server/scripts/start_api.ps1` 和 `server/prebuild_daily_briefing.bat` 也固定依赖该解释器位置。
- `docs/asr-setup.md` 含开发者电脑上的 `C:\Users\<user>\...` 路径；`PROJECT_MIGRATION_GUIDE.md` 仍要求用户替换固定用户目录示例。任务历史中的旧命令可作为历史证据保留，但不得被运行时、测试或安装器消费。
- `server/requirements.txt`、`server/requirements-asr.txt` 和 `pi_client/requirements.txt` 只有直接依赖或宽范围约束，没有可复现的 Windows 锁；Core 与 ASR 清单还有重复依赖。
- `server/qq_bridge/package-lock.json` 已存在且为 lockfile v3，但公开安装说明仍要求无锁语义的 `npm install`。PK-020 必须统一改为 `npm ci`；不得修改 QQ 业务规则。
- 当前没有 `.github/workflows/` 下的 Windows 干净安装验证。
- 当前代码已使用 Python 3.10 的联合类型语法，不能继续把 Python 3.8 当作受支持运行时。

上述是整改输入，不是完成证据。独立任务仍须在不读取受保护路径内容的前提下重跑受跟踪文件扫描，并把完整分类结果记录到本文件。

## 目标

- 消除生产运行代码、启动器、安装器、活动配置和用户文档对开发者用户名、盘符、桌面目录、固定外部引擎目录、固定解释器绝对路径和调用方当前工作目录的依赖。
- 提供 clone 后可从项目根目录双击或命令行执行的一键 Core 安装、只读 doctor 和统一启动入口。
- 形成可审计、可重复生成的 Core、ASR/voice、开发测试和 QQ Node 依赖分层；新用户不需要猜测应安装哪个清单。
- 在没有 `.env`、QQ、ASR、GPT-SoVITS、Voice Pack 或模型时仍可完成 Core 安装并启动健康检查，明确报告可选组件状态。
- 建立不借用开发机现有环境、模型和个人配置的干净 clone 式测试与 Windows CI。

## 冻结的支持平台与运行时

- 第一阶段支持 Windows 10/11 x64；其他操作系统可继续人工运行现有 Python 服务，但不属于本任务的一键入口验收。
- Windows PowerShell 5.1 和 PowerShell 7.4+ 均须可运行安装、doctor 和启动编排；批处理入口不得假设 `pwsh` 已安装。
- 9 个受跟踪用户 BAT 在普通直接运行、失败或长驻进程退出后必须显示结果并等待
  按键；统一自动化免暂停契约为 `PROJECT_KEI_NO_PAUSE=1`。CI、测试、计划任务
  和 BAT→BAT 内部委托必须显式启用，内部委托只允许最外层暂停一次；等待前保存
  的退出码必须原样返回，且该机制不得改变参数转发或产品副作用。
- Python 支持范围冻结为 `>=3.10,<3.14` x64，即 3.10、3.11、3.12、3.13；
  推荐与主回归版本为 Python 3.11。安装器必须以真实版本/架构 probe 接受四个
  版本，拒绝 Python 3.8/3.9、3.14+ 和 32 位，并给出 python.org 官方安装提示
  及重新运行命令；不得自行下载或静默替换系统 Python。
- Node 支持范围冻结为 20.x、22.x、24.x，主验证版本为 Node 22 LTS；奇数主版本或范围外版本必须由 doctor 明确报告为不受支持。`package.json`、安装器和文档必须表达相同边界。
- 本任务不得把当前开发机的 Python 3.12、Node 24、既有 `.venv-asr` 或 `node_modules` 当作唯一验证环境。

如实际依赖证明上述范围无法成立，独立任务不得悄悄收窄或扩大；必须记录具体包、版本和最小变更建议并交回 PK-000。

## 冻结的环境与依赖分层

### 本地环境

- 安装器创建并拥有项目根目录下的 `.venv/`，它是 Core、可公开安装的可选 Python 依赖和开发测试工具的统一本地环境。
- 现有 `server/.venv-asr/` 只作为迁移期兼容候选：启动解析器可在根 `.venv` 不存在时验证并临时复用，但安装器不得创建、复制、删除或重装它，也不得把它写成新用户前提。
- Python 解析顺序固定为：有效的 `<项目根>/.venv/Scripts/python.exe`；有效的迁移期 `server/.venv-asr/Scripts/python.exe`；Windows `py` launcher 中受支持的 Python；PATH 中受支持的 `python`。每个候选都必须实际核对版本和架构；全部失败时输出明确安装提示。
- GPT-SoVITS 继续使用 PK-211 登记的仓库外引擎运行时，不进入 `.venv`。Voice Pack 继续使用 PK-212 注册表，不进入任何 requirements。
- 已安装官方 QQ sidecar 的 Node 依赖位于
  `server/runtime/module-dependencies/qq_bridge/<current-version>/`，不写入不可变
  package root；尚未安装模块时才兼容使用 `server/qq_bridge/node_modules/`。
  两者都只由对应 `package-lock.json` 通过显式 QQ/full profile 的 `npm ci`
  生成。
- `pi_client` 属于独立设备客户端，不由 Windows 主机默认、voice、qq 或 full profile 安装；PK-020 只在组件清单中说明其独立入口和依赖，不顺带改写树莓派部署。

### 依赖清单

独立任务须建立单一权威依赖目录，建议冻结为：

- `requirements/core.in` 与 `requirements/core-win.lock.txt`：Core/main API 必需依赖。
- `requirements/asr.in` 与 `requirements/asr-win.lock.txt`：ASR 可选依赖；只列相对 Core 的附加/约束，不包含 GPT-SoVITS 或模型。
- `requirements/dev.in` 与 `requirements/dev-win.lock.txt`：测试、锁生成和静态验证工具。
- 现有 `server/requirements.txt`、`server/requirements-asr.txt` 只能成为指向权威清单的兼容入口或明确弃用说明，不得继续形成第二套版本事实。
- 锁文件必须由直接依赖清单可重复生成，固定解析后的版本和完整性信息；不得含 editable、本机目录、私有索引、凭证、`file://`、本机 wheel、开发工具污染或未经说明的 CUDA/GPU 专用包。

安装 profile 冻结为：

- `core`：默认；只建立 `.venv` 并安装 Core 锁定依赖。
- `voice`：`core` 加公共 ASR 依赖与语音目录/preflight；不下载 GPT-SoVITS、ASR 模型、Voice Pack 或大型音频。
- `qq`：`core` 加 `server/qq_bridge/package-lock.json` 对应的 `npm ci`；不创建或读取 QQ `.env`，不启动 sidecar。
- `full`：`core + voice + qq` 的公开可安装部分；仍不下载大型引擎/模型、不创建秘密、不启动联网业务。
- `dev`：`core` 加开发/测试锁；不隐式包含 voice、qq 或真实服务。

## 接口契约

本任务不新增业务 HTTP API；公开接口以以下根目录 CLI/双击入口及其退出码、
只读/写入副作用和进程语义为主。2026-08-08 经 PK-000 明确授权增加的固定本机
Core supervisor 控制端点是启动器基础设施接口，不接受业务参数或任意执行输入；
精确契约见本文件末尾的 supervisor 增量记录。

### 冻结的脚本入口

- `setup.bat` → `scripts/setup.ps1`：默认 `--profile core`；从自身位置解析项目根，完整转发参数和退出码。允许 `core|voice|qq|full|dev`，未知 profile 必须失败。
- `doctor.bat` → `scripts/doctor.ps1`：默认检查 Core，可指定同一 profile；严格只读，不创建目录、安装依赖、写配置、下载、启动进程或联网探测业务服务。
- `start.bat` → `scripts/start.ps1`：默认只启动 Core API 8000；可由用户显式选择 `voice`、`qq` 或 `all`。启动前只执行有限只读 preflight，不运行 pip/npm，不修改配置。
- `server/start_api.bat`、`server/start_asr.bat`、`server/start_gptsovits.bat`、`server/start_all_services.bat` 和 `server/qq_bridge/start_qq_bridge.bat` 保持兼容名称，但应委托统一路径/运行时解析或共享 helper，不得复制第二套安装规则。
- 所有脚本使用脚本自身目录计算项目根，对路径逐层加引号；不得依赖调用者先 `cd server`，必须在空格、中文和非系统盘路径中工作。

进程语义冻结为：

- Core 是默认且唯一必启进程。无语音、QQ、LLM Key、模型或来源配置时，Core 仍应启动，相关能力显示未配置/降级。
- voice 是显式可选组合：ASR 8010、GPT-SoVITS 9880 仅在对应 profile 和配置通过时启动；某个可选进程失败不得终止已可用的 Core，并须逐项报告。
- qq 是显式可选 sidecar；只有现有 PK-140 preflight 通过后才可启动，不能读取或回显秘密，不能启动第二个 bridge。
- `all` 只表示显式请求所有已安装组件，不表示自动安装、自动下载、自动创建 `.env`、自动获取 Token、自动采集、自动调用 LLM/TTS 或自动发送消息。
- 启动器必须显示每个由它启动的进程、端口、解释器/运行时和停止办法。若实现 PID 管理，只能停止本次启动器明确拥有的进程，不得按端口或进程名批量终止其他程序。

## 安装与 doctor 契约

安装器必须：

1. 检查 Windows、PowerShell、Git、Python、Node/npm 的版本；只有所选 profile 需要 Node 时才把 Node 缺失视为阻断。
2. 在项目内创建/验证 `.venv`，只用受版本控制的锁安装；QQ 只执行 `npm ci`。
3. 可重复执行且幂等：健康环境直接复用或验证，不删除环境重装，不覆盖用户配置。
4. 对每个阶段返回稳定的组件名、错误类别、建议修复命令和非零退出码；不得只透传 pip/npm 堆栈。
5. 完成后运行有限健康检查，输出下一步 `doctor.bat`/`start.bat` 命令和未配置的可选组件。
6. 安装失败时保留既有健康环境和用户文件；本次新建的临时产物只能清理到精确目标。

doctor 必须：

- 只检查版本、入口/锁文件存在性、已选 profile 的包导入、端口占用、非秘密配置是否存在以及 PK-211/212 的脱敏状态。
- 缺少秘密时只显示字段名与公开文档位置；不得读取、打印、哈希、上传或验证真实值。
- 不连接真实 API、QQ Gateway、Nitter、LLM、ASR、TTS 或其他外部服务，不触发 Collector、定时器、下载器或业务写入。
- 输出稳定的 `ok/warn/error` 项和最终退出码，供安装器、用户和 CI 共用；不得因为可选组件缺失而把 Core 诊断判为失败。

## 数据所有权

PK-020 只拥有受版本控制的依赖声明/锁、安装与启动脚本、无秘密示例、安装验证代码，以及由安装器在精确目标中新建或验证的 `.venv`/`node_modules` 安装产物；不得据此清理既有环境。业务状态、用户配置、秘密、外部引擎和模型仍归原任务或用户所有。

### 配置、秘密与资产边界

- 可更新 `.env.example` 和各组件示例配置的字段名/非秘密占位说明；不得读取、复制、打印、覆盖或提交任何真实 `.env`、Token、QQ Secret、LLM Key、Cookie、白名单、用户 ID 或私有源。
- 已存在配置时 setup/doctor/start 一律不覆盖。缺失时只给出人工复制模板和编辑说明，不自动创建带值配置。
- 不把 GPT-SoVITS 源码、Kei/其他角色权重、参考音频、ASR 模型或大型资产放入 Git、`vendor/`、Python lock 或 Node 包。
- 需要引擎时只引导用户显式调用 PK-211 的受控流程，并在执行前显示来源、固定版本、大小、摘要、目标和确认；PK-020 自身不实现第二个下载器。
- 需要声音模型时只引导用户显式调用 PK-212 的导入/注册流程；不得扫描磁盘寻找模型或复制开发者本机路径。
- 安装结束不得自动启动 QQ、真实采集、LLM、ASR、TTS、Gateway、定时推送或提醒。

## 允许修改的边界

- 新建根入口：`setup.bat`、`doctor.bat`、`start.bat`。
- 新建/修改安装工具：`scripts/setup.ps1`、`scripts/doctor.ps1`、`scripts/start.ps1` 及其小型公共 helper。
- 新建权威 `requirements/` 分层和锁；窄范围维护现有 `server/requirements*.txt`、`server/qq_bridge/package.json`/`package-lock.json`、`.gitignore` 与示例配置。
- 窄范围修正现有 `server/start_*.bat`、`server/scripts/start_*.ps1`、`server/prebuild_daily_briefing.bat`、`server/qq_bridge/start_qq_bridge.bat` 及必要的安装提示接缝。
- 新建安装专项测试和 `.github/workflows/` 下无 Secret、无大型资产、无真实服务的 Windows 验证。
- 更新 `README.md`、`PROJECT_MIGRATION_GUIDE.md`、`docs/asr-setup.md`、新建安装专项架构文档和本任务记录；`README.local.md` 只在确有本机入口变化时维护且不得提交。

## 不在本任务内

- 不重构任何业务模块、业务 API、数据模型、Collector、控制台业务面板、QQ 菜单、对话、语音编排、模型注册或模块生命周期。
- 不修改 `server/api.py` 的业务装配、`server/static/dashboard.html` 的产品行为或 `server/features/catalog/service.py` 的模块契约；如健康检查确需公共接缝，先记录需求交 PK-000。
- 不为 QQ、语音、情报或任一业务模块新增独立 setup，不把安装逻辑复制进模块。
- 不用 `pip freeze` 全量覆盖依赖，不提交本机路径依赖、editable、私有源、CUDA/GPU 偶然版本或开发机无关包。
- 不删除、移动或重建当前真实 `.venv-asr`、`.venv`、`node_modules`、GPT-SoVITS、模型、Voice Pack、缓存、个人状态或配置。
- 不自动安装 Git、Python、Node、PowerShell、CUDA、驱动、GPT-SoVITS 或模型；缺失时给出官方下载/项目文档指引，由用户明确操作。
- 不执行真实外部下载、QQ/LLM/TTS/Collector 调用或 Git 暂存、提交、推送、发布和工作区清理。

## 验收标准

- 受跟踪的生产 `.py/.ps1/.bat/.cmd/.mjs/JSON`、活动配置和用户运行文档中不含开发者用户名、桌面目录、固定磁盘上的 GPT-SoVITS/模型路径或固定解释器绝对路径；扫描对任务历史采用明确 allowlist，历史证据不被运行时消费。
- 从非系统盘、含空格且含中文的隔离副本运行根 `setup.bat --profile core`，在没有现成虚拟环境、`node_modules`、`.env` 和模型时成功建立锁定 Core 环境。
- 同一隔离副本第二次运行 setup 不删除/重建健康环境、不覆盖配置，结果稳定且明确报告复用。
- `doctor.bat` 在文件系统与进程 tripwire 下保持只读、零安装、零配置写入、零服务启动、零业务网络。
- 新建 `.venv` 能导入主 API，并通过 ASGI/假进程方式完成最小健康检查；不以当前开发机已有环境冒充证据。
- `voice`、`qq`、`full` 对缺失可选组件给出分项提示；没有 GPT-SoVITS/Voice Pack/QQ `.env` 时 Core 仍可用。
- Python/Node 缺失、版本不兼容、端口占用、模拟网络失败、pip/npm 失败和锁损坏都有可测试的稳定错误与修复建议。
- QQ 依赖只通过现有 lockfile 的 `npm ci`；Python 各 profile 只通过权威锁安装，锁中无本机路径、秘密、editable 或未说明的大型资产。
- 所有启动器从自身位置解析根目录，在不同当前目录和带空格/中文路径下正确传参、引用解释器并报告进程状态；启动过程不静默安装或修改配置。
- 安装/测试使用临时目录、fake 下载器、fake 进程、fake 端口和隔离环境；真实个人状态、缓存、来源名单、模型、QQ 配置、秘密和现有运行环境保持未访问、未修改、未纳入差异。
- Windows CI 完成 checkout、只读 doctor、Core 测试环境建立、锁定依赖安装、最小导入/健康检查、专项测试和运行时绝对路径扫描；不使用 Secret、不下载模型、不启动外部服务。
- 相关 PowerShell AST、Batch 路径/引号、Python 测试、Node lock/语法、文档门禁和 `git diff --check` 全部通过，实际命令与结果写入本文件。

## PK-900 后续验收范围

PK-020 进入“待集成”后，应单独登记 `PK-900 = PK-020`，至少独立复核：

1. 用新建的隔离副本和隔离运行时完成非系统盘、空格、中文路径的首次 Core 安装、二次幂等和启动健康检查。
2. 复现 Python/Node 缺失与版本不兼容、模拟 pip/npm 网络/安装失败、端口占用和配置缺失的失败语义。
3. 对 doctor 和普通 start 设置文件写入、进程、网络 tripwire，证明 doctor 只读且启动器不安装、不改配置、不触发业务联网。
4. 验证 `core|voice|qq|full|dev` 分层与锁文件，特别是 QQ `npm ci`、语音缺失不阻塞 Core、PK-211/212 资产边界未被复制。
5. 扫描受跟踪运行时代码、配置、启动器和活动文档中的开发者绝对路径；核对历史任务 allowlist 不会被产品消费。
6. 核对差异中没有真实 `.env`、个人状态、缓存、来源名单、模型、参考音频、外部引擎源码、`vendor/`、虚拟环境或 `node_modules`。
7. 重跑 API/Core、PK-010/100、PK-140、PK-200、PK-210/211/212 的最小兼容回归及 Windows CI 等价命令。

PK-900 提交报告前，PK-020 保持“待集成”；只有 PK-000 独立确认后才可改为“已完成”。

## 工作记录

- 2026-07-25：PK-000 完成受跟踪文件的只读入场审计，确认根安装入口、可复现 Python 锁和 Windows CI 缺失；定位 `start_asr.ps1` 的开发机外部引擎绝对路径、多个脚本对 `server/.venv-asr` 的固定依赖、公开 ASR 文档的开发者路径，以及 QQ 文档的 `npm install` 漂移风险。
- 2026-07-25：冻结 Windows/Python/Node 支持范围、根 `.venv`、依赖/profile 分层、setup/doctor/start 入口、Core 默认启动、语音/QQ 显式可选、PK-211/212 资产边界和干净 clone 验收。未实现脚本、未安装依赖、未运行服务、未读取受保护数据，也未执行 Git 暂存、提交、推送或清理。
- 依赖阻断：PK-140 当前“待集成”；PK-020 尚未领取。PK-140 最终完成后，独立任务才可把本文件和总板改为“进行中”并开始实现。
- 2026-07-25：PK-020 独立实施对话完成必读文档、架构文档、分支与混合工作区只读预检；`TASKS.md` 和 PK-140 任务记录仍将 2026-07-24 业务私聊菜单增量标为“待集成”，未找到 PK-000 对该增量的最终“已完成”确认。按冻结依赖保持 PK-020“待开始”，交回 PK-000 先完成 PK-140 验收；本轮未修改 QQ 启动器、QQ 依赖说明、控制接缝或其他实现/活动文档，未运行安装、服务、网络或业务测试，也未读取受保护数据。
- 2026-07-25：PK-000 对 PK-140 增量独立复核发现合法日历命令会被宽泛情报关键词抢先路由的阻断，已将 PK-140 退回“进行中”。PK-020 继续保持“待开始”，不得在该阻断关闭前修改 QQ 启动器、依赖说明或控制接缝。
- 2026-07-25：PK-140 完成关键词碰撞整改并通过 PK-000 独立最终复核，已正式改为“已完成”。PK-020 的全部登记依赖现已满足，获准由原独立对话重新领取；本文件和总板仍保持“待开始”，领取时再按项目规则改为“进行中”。
- 2026-07-25：原 PK-020 独立对话重新核对最新总板与任务记录，确认 PK-140 及其余登记依赖全部为“已完成”，正式将本任务和 `TASKS.md` 改为“进行中”。实施范围仍严格限定为安装/诊断/启动入口、依赖锁、兼容启动器接缝、隔离测试、Windows CI 和安装文档；混合工作区其他修改继续全部排除。

## 实施结果（2026-07-25）

### 入口、运行时与 profile

- 新增根 `setup.bat`、`doctor.bat`、`start.bat`，分别委托 `scripts/setup.ps1`、`doctor.ps1`、`start.ps1`；BAT 使用 `%~dp0`、引号和退出码透传，不依赖调用者当前目录。公共解析位于 `scripts/project-kei.common.ps1`。
- Python 逐项验证版本和 x64 架构，顺序为根 `.venv` → 迁移期
  `server/.venv-asr` → `py` 的 3.11/3.13/3.12/3.10 x64 → PATH python。
  setup 只创建/复用根 `.venv`；已存在但损坏/不受支持时失败关闭，不删除、
  重建或清理任何环境。
- Node 只接受 20.x、22.x、24.x x64；`package.json` 与 `package-lock.json` 已同步该范围。只有 `qq|full` setup 和 `qq|full` doctor 把 Node/npm 作为必需项。
- setup profile 已实现 `core`（默认）、`voice`、`qq`、`full`、`dev`；dev 是 Core + dev，不隐式包含 voice/qq。start profile 已实现 `core`（默认）、`voice`、`qq`、`all`。
- `scripts/python.ps1` 让维护/测试命令使用同一解释器顺序；`scripts/run-server-tool.ps1` 为每日情报预构建提供窄入口。
- `server/start_api.bat`、`start_asr.bat`、`start_gptsovits.bat`、`start_all_services.bat`、对应 API/ASR/all PowerShell 和 QQ BAT 均成为统一入口的兼容薄层。PK-211 的 `start_gptsovits.ps1` 保持登记式外部运行时实现，没有复制或改写引擎规则。

### 实际依赖锁

- 权威目录为 `requirements/`：`core.in`、`asr.in`、`dev.in` 分别对应 40、20、13 个精确 Windows lock 行。Core 直接版本为 FastAPI 0.115.4、HTTPX 0.27.2、Pydantic 2.9.2、Uvicorn 0.32.1、python-multipart 0.0.12、tzdata 2024.2、bilibili-api-python 17.4.2；ASR 固定 faster-whisper 1.0.3、huggingface-hub 0.25.2、tokenizers 0.20.3 及完整传递层；dev 固定 pytest 8.3.3、pytest-asyncio 0.24.0、ruff 0.7.1、pip-tools 7.4.1 及传递层。
- `lock-manifest.json` 以 SHA-256 固定锁文件内容：Core `00aa31206aad7bf242eae3633fbf74446317b4d8700114a3ecb2099c2fce37f1`，ASR `1f36a3fcc15355fbf4e72fc557c5ce39d7f39ea69d241e6a2a9c6513c4ce9631`，dev `2aea2269d9ca2f9c8d1b85677e9c179e054ebbd351591831713565f8c8516ca1`。setup/doctor 在安装/导入前验证摘要。
- 锁不含 editable、本机目录、`file://`、私有源、凭证、本机 wheel、GPT-SoVITS、模型、Voice Pack 或 GPU/CUDA 专用包。`server/requirements*.txt` 只保留指向根权威锁的兼容入口。
- QQ 继续使用原 lockfile v3；`ws` 为 8.21.0，保留 registry URL 和 `sha512-Vsp28b7DRcimFQvrqu2Wek3z1iYxDCWqHYB8Qsnk/S4RfaCQzPGPyBNuVjJV3cd6UiKtUtp6sNM77gWvzcCH+g==` 完整性。setup 只执行 `npm ci --ignore-scripts`，start/doctor/控制接缝不运行 npm。

### 副作用与失败语义

- setup 唯一允许写入是精确目标根 `.venv` 和选中 QQ profile 的 `server/qq_bridge/node_modules`。它不读取/创建/覆盖 `.env`，不下载引擎、模型、Voice Pack 或远程脚本，不启动任何服务。
- doctor 只读取版本、锁/摘要、包导入、监听端口、公开入口及非秘密配置“是否存在”。它不读取 `.env` 内容、模型路径值、引擎登记内容或 Voice Pack 注册表内容，不连接业务网络，不运行 pip/npm，不启动服务。
- start 不运行安装器、不写配置、不下载。Core 在当前窗口前台运行；语音/QQ 仅显式请求并通过有限 preflight 后打开独立窗口。可选项缺失只警告且不阻止 Core；端口占用不会替换或停止所有者。
- setup 稳定退出码：2 参数、10 平台/PowerShell、11 Python/venv、12 lock、13 pip、14 Node/npm、15 包导入；start 为 2 参数、20 Python、21 显式单组件 preflight、22 端口。doctor 以稳定 `ok/warn/error` 输出，选中 profile 的必需项错误时退出 1。

### 验证与结果

- `python server/tests/test_windows_install.py`：12 项通过，110.764 秒。全部使用系统临时根、隔离副本、新建临时 `.venv`、fake pip/npm/uvicorn、临时非系统盘符、fake 端口与保护 sentinel；覆盖中文/空格/非系统盘、无 venv/node_modules/.env/模型、二次幂等、五个 profile、doctor 文件快照零变化、默认 Core fake 启动、start 零安装/零配置写、Python/Node 缺失或不兼容、锁/pip/npm 失败、端口占用、活动文档/运行时代码路径扫描和锁摘要。
- QQ Node 最小兼容回归：`node --test tests/*.test.mjs` 46/46 通过；随后对 `src/*.mjs` 全部 `node --check` 通过。未运行 `src/index.mjs`，未连接 Gateway/Token/QQ/业务网络。
- PowerShell AST 对根 `scripts/*.ps1` 与 `server/scripts/*.ps1` 通过；专项测试同时验证 BAT `%~dp0`/引号/绝对路径门禁、Python lock 精确行和活动文档命令。
- `python -m py_compile server/tests/test_windows_install.py` 使用系统临时 pycache 通过；Node manifest/lock 的 engines/dependencies 一致性检查通过；新增的未知 profile、活动文档、运行时绝对路径和锁摘要 4 项聚焦重跑通过。
- `python scripts/check_task_docs.py`：通过，共检查 23 个处于“待集成/已完成”的任务。因本机安全边界未通过 `scripts/python.ps1` 探测真实迁移期环境，本次文档脚本使用 PATH Python 直接运行且禁止 bytecode 写入。
- `git diff --check` 在实现差异上退出 0，仅输出仓库既有 LF→CRLF 提示。
- 尝试以 PATH Python 运行 PK-010 最小回归时在导入阶段因该系统 Python 未安装 FastAPI 而以 `ModuleNotFoundError` 退出；没有进入应用装配、业务 I/O 或网络。按冻结限制未借用真实 `.venv-asr`、未真实下载依赖。`.github/workflows/windows-install.yml` 已配置 Python 3.11/Node 22 的非系统盘干净安装、二次幂等、doctor、真实锁安装、ASGITransport Core 健康检查、PK-010/100/140/200/210/211/212 最小回归、Node/AST/文档/diff 门禁；本对话没有 Git 提交/推送，故远端 CI 尚未运行，必须由独立 PK-900 执行。

### 遗留与独立验收

- 独立 PK-900 必须实际运行新增 Windows workflow 或其等价 Python 3.11/Node 22 干净环境，确认公开依赖可由当前锁解析并完成真实 Core import/ASGI 健康检查；不得把本轮 fake pip 或开发机环境冒充该证据。
- 已通过 Codex 应用创建独立 PK-900 任务 `019f9a15-c1c2-7cb1-8957-3f8638f078ba` 并发送完整验收提示；应用初始化及一次 follow-up 均立即返回 `systemError`，未进入文档读取/验收且未修改工作区。任务记录和 PK-900 入场清单已完整保留，需由用户在该任务中重试或手工新开任务继续。
- 独立 PK-900 还须重跑 workflow 登记的 PK-010、PK-100、PK-140、PK-200、PK-210、PK-211、PK-212 Python 回归，并复核 `qrcode-terminal` 的公开 sdist 安装和全部 Windows wheel 可得性。若真实锁解析失败，退回 PK-020，不得无审阅放宽版本。
- 未执行真实 setup 下载、真实服务/浏览器、QQ、Gateway、Collector、LLM、ASR、TTS、提醒或定时任务；未读取/打印/迁移/删除真实配置、个人状态、缓存、来源名单、模型、参考音频、Voice Pack 或外部引擎源码。
- `README.local.md` 未修改：本轮没有验证或改变任何本机绝对路径、真实配置、引擎/模型位置；公开入口变化已写入受跟踪文档。

## 完成文档门禁

任务进入“待集成”或“已完成”前必须全部勾选；不适用项也必须写明原因。

- [x] TASK_RECORD — 已记录实际脚本、锁摘要/profile、运行时顺序、失败语义、副作用、验证、未运行项和 PK-900 遗留。
- [x] TASKS_BOARD — 已同步 `TASKS.md` 的名称、P0、依赖和“待集成”状态。
- [x] PUBLIC_README — 已说明支持版本、首次安装、profile、启动/停止、可选组件、配置与安全限制。
- [x] MODULE_CATALOG — 不适用：未新增/迁移业务模块或 API；仅窄改 QQ 缺依赖提示，现有 catalog 进程边界不变。
- [x] ARCHITECTURE_DOCS — 已新增 Windows 安装架构，并窄更新 voice/QQ 启动与依赖接缝。
- [x] LOCAL_README — 不适用：未验证或改变本机绝对路径/真实运行时；`README.local.md` 保持忽略且未修改。
- [x] AGENT_RULES — 已把标准 Python/文档门禁命令切到 `scripts/python.ps1`，保留秘密、个人数据和外部引擎隔离规则。
- [x] VALIDATION — 已记录 12 项安装专项、46 项 Node 回归、AST/Batch/路径/锁/diff 门禁、Python 回归的本机依赖阻断和未执行远端 CI。

## 独立对话启动提示

```text
继续 Project Kei 的 PK-020「Windows 安装、环境锁定与可移植启动」。

先完整阅读 README.md、AGENTS.md、README.local.md（如存在）、TASKS.md、
tasks/PK-020-windows-install.md，以及 PK-010、PK-100、PK-140、PK-200、
PK-210、PK-211、PK-212 的任务说明和相关架构文档。先检查 PK-140 是否已经
由 PK-000 最终改为“已完成”；若仍为“待集成”，不要修改与其重叠的 QQ
启动器/说明，记录阻断并交回总控。依赖满足后，才把 PK-020 改为“进行中”。

严格按 PK-020 已冻结的 Windows/Python/Node、根 .venv、依赖锁、profile、
setup/doctor/start 和进程边界实施。先重新扫描所有受跟踪运行时脚本、配置和
用户文档；任务历史中的旧路径只可作为历史 allowlist，不得被产品消费。

只修改 PK-020 允许路径。不得重构业务模块或公共 API，不得复制 PK-211 下载器、
PK-212 Voice Pack 逻辑或 PK-140 QQ 规则。不得读取或输出真实 .env、个人状态、
缓存、模型、参考音频、外部引擎源码、现有虚拟环境或 node_modules 内容。
不得删除/重建开发机环境，不得启动真实 QQ、Collector、LLM、ASR、TTS，
不得执行 Git 暂存、提交、推送或清理。

所有安装与启动测试使用临时隔离副本、fake 下载器/进程/端口和路径/网络/写入
tripwire；必须覆盖非系统盘、空格、中文、无 venv、无 node_modules、无配置、
二次幂等、失败诊断与 Core 健康检查。完成后更新任务记录和八项文档门禁，
将 PK-020 置为“待集成”，等待独立 PK-900 = PK-020，不要自行标记“已完成”。
```

## PK-900 独立验收退回（2026-07-26）

- 结论：**不通过**。PK-020 与总板状态已从“待集成”退回“进行中”；PK-900 同批保持“进行中”。本节只记录独立验收证据，没有修改安装器、启动器、业务模块或测试实现。
- 阻断一：隔离副本中运行 `tests/test_qq_control.py` 得到 `Ran 8 tests`、`FAILED (failures=1)`。失败用例 `test_project_launcher_never_configures_or_installs` 仍要求 `server/qq_bridge/start_qq_bridge.bat` 包含 `node src\index.mjs`，当前兼容启动器按 PK-020 新契约委托根 `start.bat --only qq --current-window`。`.github/workflows/windows-install.yml` 第 97 行会运行同一回归，因此当前 Windows CI 等价流程确定失败。最小整改只应对齐这条兼容测试与已经冻结的统一启动器契约，同时继续断言零配置、零安装、参数/退出码透传和可移植路径。
- 阻断二：`server/tests/test_windows_install.py::_copy_install_surface()` 使用 `shutil.copytree()` 递归复制真实 `server/qq_bridge`，忽略项只有 `.env` 与 `node_modules`；但 `.gitignore` 明确把 `server/qq_bridge/data/` 定义为本机 QQ runtime，AGENTS 也禁止读取或复制该状态。故从共享工作区直接执行任务记录中的必跑命令，可能在测试夹具创建前读取并复制真实运行状态，不能满足本批零读取门禁。最小整改应让测试安装表面使用显式白名单，或至少完整排除 QQ data、缓存和其他本机运行产物，并增加受保护路径 tripwire。
- 强制环境证据未闭合：本机 PATH 仅有 Python 3.12.7 x64、Node 24.18.0 和 Windows PowerShell 5.1，`py.exe` 与 PowerShell 7 均不可用；未安装或下载新运行时，也未提交/推送触发远端 CI。因此没有产生清单要求的 Python 3.11 x64、Node 22、PowerShell 7.4+ 无缓存实际安装证据。补充性的 Python 3.12 / Node 24 结果不得替代目标矩阵。
- 已通过的补充证据：严格白名单临时副本中的专项测试 12/12；公开 Core lock 首次安装、二次复用、doctor dev、Core import 与 ASGITransport `/` 200/`online`；三份 manifest SHA-256；PK-010、PK-100、PK-200、PK-210、PK-211、PK-212 Python 最小回归；QQ `npm ci --ignore-scripts` 与 Node 46/46；QQ/dashboard JavaScript 语法；Windows PowerShell 5.1 AST；Python compileall。上述均不能抵消两个阻断或缺失的强制版本矩阵。
- 数据隔离：所有动态安装、npm、ASGI、失败注入和回归只在系统临时目录的白名单副本、新建 `.venv`、临时 npm cache 与 fake/ASGITransport 中进行。没有使用共享项目 `.venv`、`.venv-asr` 或 `node_modules`；没有读取、打印、复制、迁移或修改真实 `.env`、秘密、个人状态、缓存、来源名单、profile、模型、参考音频、Voice Pack 注册表或外部 GPT-SoVITS 源码；没有启动真实业务服务或执行 Git 发布操作。

## PK-900 退回整改（2026-07-26）

### 两项阻断的最小修改

- QQ 兼容入口的生产实现保持不变，继续由 `server/qq_bridge/start_qq_bridge.bat` 通过 `%~dp0..\..` 委托根 `start.bat --only qq --current-window %*` 并以 `exit /b %ERRORLEVEL%` 透传结果。只更新共享测试 `test_project_launcher_never_configures_or_installs`：正向验证可移植根、统一薄委托、固定 `--only qq --current-window`、参数和退出码透传；反向验证无直接 `node src\index.mjs`、无 npm、无配置复制和无编辑器。未修改 PK-140 的 Gateway、凭证、菜单、路由或进程控制业务。
- `_copy_install_surface()` 不再递归 `copytree()` 真实 `scripts/`、`requirements/` 或 `server/qq_bridge/`。测试夹具只复制 16 个明确文件：三个根 BAT、四个安装 PowerShell、七个 Python 输入/锁/manifest 文件和 QQ 的 `package.json`/`package-lock.json`。
- 新增 `InstallSurfaceTripwire`，以词法根边界、精确 allowlist 和受保护前缀在 `shutil.copy2` 原始 I/O 前拒绝越界或非安装表面来源。每个专项 setUp 都证明实际复制集合等于 allowlist 且拒绝记录为空。
- 原 12 项专项中的 doctor 用例额外创建纯临时合成 sentinel，逐项验证 QQ data、主/QQ `.env`、缓存、个人状态、来源名单、LLM profile、模型、参考音频、Voice Pack 注册表及合成外部 GPT-SoVITS 源路径均在底层复制函数被调用前抛出 `PermissionError`；另有源根外 sentinel 验证不能越界。测试不以存在性探测或读取真实受保护路径作为证据。

### 隔离方式与验证结果

- `python server/tests/test_windows_install.py`：原有 12 项全部通过，`Ran 12 tests in 112.037s`。执行只使用专项自己创建的系统临时目录、非系统盘映射、fake pip/npm/uvicorn/端口和合成 sentinel；共享项目的现有虚拟环境、QQ `node_modules` 及受保护目录均未使用。
- 系统 PATH Python 缺少 FastAPI，因此没有借用共享 `.venv`/`.venv-asr`。在 `%TEMP%` 新建一次性 Python 3.12.7 x64 venv，以 `--no-cache-dir` 从现有 Core/dev 公共锁安装依赖；再用 `git ls-files --cached --others --exclude-standard` 产生的明确源码清单构造名为 `project-kei` 的临时副本，同时排除 `.env`、`README.local.md`、data、models、runtime、output、cache、profiles、参考音频、Voice Pack、vendor、现有 venv 和 `node_modules`。
- 在该隔离副本中，`test_qq_control.py` 为 8/8 通过，直接证明 Windows workflow 登记的共享 QQ 回归已对齐统一启动器契约。PK-010 `test_installable_modules.py`、PK-100 `test_dashboard_shell.py`、PK-200 `test_conversation_module.py`、PK-210 `test_voice_module.py`、PK-211 `test_gpt_sovits_provider.py`、PK-212 `test_voice_pack_registry.py` 最小回归全部通过。
- QQ 临时副本使用现有 `package-lock.json` 执行 `npm ci --ignore-scripts`，随后 `npm test` 为 46/46 通过；7 个 `src/*.mjs` 均通过 `node --check`。dashboard 的 6 个 JavaScript 文件均通过 `node --check`。没有运行真实 QQ bridge、Gateway 或业务网络。
- 一次 Node 语法门禁命令把参数顺序误写为 `node <file> --check`，在无 `.env`、无 Token、无本机状态的隔离副本中短暂执行了 `index.mjs`；它立即以 `bridge_start_required_configuration_missing` 失败关闭，没有网络连接、外部进程或共享工作区副作用。随后用正确的 `node --check <file>` 重跑 7/7 通过。
- 隔离副本 `python -m compileall -q server` 通过；Windows PowerShell 5.1 对根 `scripts/*.ps1` 和 `server/scripts/*.ps1` AST 解析通过；三份 Python lock 的 SHA-256 与 `lock-manifest.json` 一致；QQ package/lock 的 Node engines 与 `ws` 版本一致。
- `python -B scripts/check_task_docs.py`：退出 0，`task documentation gate passed: 23 gated task(s)`。`git diff --check`：退出 0，仅输出混合工作区既有 LF→CRLF 提示，没有空白错误。

### 遗留矩阵与复验要求

- 当前机器仍只有 Python 3.12.7 x64、Node 24.18.0、Windows PowerShell 5.1，且没有 `py.exe` 或 PowerShell 7。未安装新运行时，也不把本轮 3.12/24 补充回归冒充 Python 3.11 x64、Node 22、PowerShell 7.4+ 的强制矩阵。
- PK-900 必须按原两个失败点复验：先确认共享 QQ 回归 8/8 和安装表面 tripwire，再在 Python 3.11 x64、Node 22、PowerShell 5.1/7.4+ 无缓存隔离环境运行真实公开锁安装、首次/二次 Core setup、doctor、Core import 与 ASGITransport `/` 健康检查。PK-020 保持“待集成”，不得由本对话改为“已完成”。
- 本轮没有改动公开契约、模块 catalog、架构、运行时锁或本机路径，因此 PUBLIC_README、MODULE_CATALOG、ARCHITECTURE_DOCS、LOCAL_README 和 AGENT_RULES 无需内容修改；TASK_RECORD、TASKS_BOARD 和 VALIDATION 已按实际整改同步。

## PK-900 二次复验退回（2026-07-26）

- 结论：**仍不通过**。原 QQ 兼容回归阻断已独立关闭；安装表面 16 文件 allowlist
  和其合成 tripwire 也按设计生效。但整份安装专项仍有另一条真实个人状态读取路径，
  因此 PK-020 与总板再次退回“进行中”，PK-900 继续保持“进行中”。
- 已关闭证据：在 PK-900 事先排除所有 data、配置、模型和运行目录的严格白名单
  副本中，更新后的 `test_windows_install.py -v` 为 12/12 通过（118.131 秒）；
  `test_qq_control.py` 为 8/8 通过。生产 QQ 启动器没有修改，统一薄委托契约正确。
- 剩余阻断：`test_runtime_scripts_have_no_developer_absolute_paths` 先通过
  `git ls-files -z` 收集所有受跟踪路径，再对 `.py/.ps1/.bat/.cmd/.mjs/.json`
  调用 `Path.is_file()` 和 `read_text()`。它只排除 `.git/.venv/.venv-asr/
  node_modules/vendor/tasks`，没有在任何文件系统调用前排除 `server/data` 和
  `server/systems/data`。
- PK-900 只查询 Git index 路径名即确认扫描集合包含
  `server/data/affection_state.json`、`fitness_checkins.json`、
  `focus_timer.json`、`memories.json`，以及
  `server/systems/data/calendar_memo.json`、`demon_slayer.json`、
  `focus_timer.json`。没有读取或打印这些文件内容，也没有从共享仓库直接运行该
  不安全测试入口。
- 最小整改限于 `server/tests/test_windows_install.py`：运行时/活动路径扫描应在
  构造真实 `Path`、`is_file/stat/open/read_text` 前，基于相对路径明确排除全部
  个人状态、缓存、来源名单、profile、模型、参考音频、Voice Pack、QQ runtime
  和外部引擎前缀；优先改为受跟踪生产代码/活动配置的显式 allowlist。补充纯合成
  tripwire，断言上述前缀不会到达任何底层文件 I/O。不得通过检查真实文件存在性
  或读取真实内容来证明修复。
- 新 `InstallSurfaceTripwire` 目前使用词法绝对路径而不解析链接目标；本机无创建
  符号链接权限，PK-900 的纯临时 symlink 逆向夹具输出
  `symlink_probe_available=false error_type=OSError`，未形成动态失败证据。
  整改时宜同时拒绝 allowlist 源文件为 symlink/reparse point，避免允许文件名指向
  根外内容；该项记为应覆盖的防御性测试，不扩展产品功能。
- 强制 Python 3.11 x64、Node 22、PowerShell 7.4+ 矩阵仍未执行，且即使上述
  测试隔离修复后也必须由 PK-900 补齐才能通过。Python 3.12/Node 24 结果继续只作
  补充证据。

## PK-900 二次退回整改（2026-07-26）

### 运行时扫描的预 I/O 隔离

- 修改范围继续仅限 `server/tests/test_windows_install.py`。运行时路径扫描不再把
  `git ls-files` 结果先转换成真实 `Path`，也不再在 Git 不可用时对仓库
  `rglob()`。候选始终先保持为 Git index 返回的相对字符串；无 Git 的隔离副本只
  补充既有 16 文件安装表面。
- 新增 `RuntimePathScanTripwire`。它先以纯字符串规范化并拒绝绝对路径、路径穿越、
  `.env`、`README.local.md`、个人状态文件名、模型/音频后缀，以及 data、systems
  data、QQ runtime、cache、profiles、runtime、models、output、Voice Pack、
  vendor、external、现有虚拟环境和 `node_modules` 等保护前缀。只有明确的根启动器、
  安装脚本/锁、server 顶层入口、core/features/intel/services/scripts/static/
  systems、QQ `src`、client 和 pi_client 生产表面才会在过滤后构造 `Path` 并调用
  `is_file/read_text`。
- 同一既有测试内加入 17 类纯合成 runtime sentinel。注入的 fake `is_file` 与
  `read_text` 证明全部保护候选的底层 I/O 调用数为 0；允许的合成 Core Python
  候选才产生一次 `is_file` 和一次 `read_text`。没有用真实保护路径的存在性、
  stat 或内容验证安全性。
- 从共享仓库直接聚焦运行运行时扫描得到
  `protected_rejected=32 allowed_io_calls=410`，用例通过。32 个保护候选只由
  Git index 相对名称分类，在构造真实 `Path` 之前拒绝；输出没有路径名或内容。

### symlink/reparse 防御

- `InstallSurfaceTripwire` 在保护前缀和 16 文件 allowlist 检查后、`copy2` 前，对
  源根以下每个相对路径组件执行不跟随目标的 `lstat`。任一组件是 symlink 或带
  Windows `FILE_ATTRIBUTE_REPARSE_POINT` 即失败关闭，避免允许文件名或中间目录
  指向根外内容。
- 覆盖不依赖本机创建链接权限：合成 `lstat` 分别把允许的 `setup.bat` 标记为
  symlink、把 `scripts` 中间目录标记为 reparse point。两种情况均在一次
  `lstat` 后抛出 `PermissionError`，底层 copy 调用合计为 0；因此本机无法创建
  symlink 不再造成覆盖缺口。

### 验证、隔离与遗留

- `python -B -c "...compile(...)"`：更新后的专项文件静态编译通过。
- 从共享仓库直接运行
  `python -B server/tests/test_windows_install.py WindowsInstallTest.test_runtime_scripts_have_no_developer_absolute_paths -v`：
  1/1 通过，0.110 秒；tripwire 计数为保护拒绝 32、允许 I/O 410。
- 从共享仓库直接运行
  `python -B server/tests/test_windows_install.py WindowsInstallTest.test_doctor_is_read_only_and_does_not_invoke_installers -v`：
  1/1 通过，13.679 秒；同时覆盖 protected copy、根外、symlink 与 reparse 的
  合成拒绝。
- 从共享仓库直接运行 `python -B server/tests/test_windows_install.py -v`：
  12/12 通过，112.373 秒；输出同样为保护拒绝 32、允许 I/O 410。专项没有
  stat/open/read 真实个人状态、缓存、来源、profile、模型、参考音频、
  Voice Pack、QQ runtime 或外部引擎。
- 使用上一轮已创建、位于系统临时目录且不含共享项目数据的隔离 Python 依赖环境
  和严格白名单 `project-kei` 副本重跑 `test_qq_control.py`：8/8 通过，
  0.115 秒。没有借用共享项目 `.venv`、`.venv-asr` 或 `node_modules`。
- `python -B scripts/check_task_docs.py`：退出 0，
  `task documentation gate passed: 23 gated task(s)`；因安全边界禁止标准包装器
  探测共享现有环境，本轮继续显式使用 PATH Python 且禁止 bytecode。
  `git diff --check`：退出 0，仅有混合工作区既有 LF→CRLF 提示；任务文件和专项
  的行尾空白扫描无命中。
- 本轮未改变安装器、启动器、锁、QQ/语音业务、公开契约、catalog、架构或本机
  路径；PUBLIC_README、MODULE_CATALOG、ARCHITECTURE_DOCS、LOCAL_README 和
  AGENT_RULES 继续为已验证不适用。未运行真实服务、业务网络或 Git 发布操作。
- Python 3.11 x64、Node 22、PowerShell 7.4+ 无缓存真实锁安装矩阵仍只归 PK-900
  补齐；本轮没有安装运行时，也没有把 Python 3.12/Node 24 冒充强制矩阵证据。
  PK-020 现恢复“待集成”，不得由本对话标记为“已完成”。

## PK-900 第三次数据隔离复验（2026-07-26）

- 原两项整改及二次退回的数据扫描遗漏现均已独立关闭。PK-900 从共享根安全运行
  聚焦 runtime scan、链接/doctor 和完整专项，未发现新的 PK-020 实现阻断。
- 静态复核确认 Git index 候选保持为纯相对字符串；保护前缀、敏感 basename 和
  资产后缀在 `joinpath`、`is_file/stat/open/read_text` 前拒绝。无 Git 时不再
  `rglob` 仓库；只补充 16 个安装表面。Git index 中的个人状态均归入已拒绝的
  `server/data` 或 `server/systems/data`。
- `RuntimePathScanTripwire` 的 17 类合成 sentinel 在底层 I/O 前全部拒绝，只有
  允许的合成 Core 文件产生一次 `is_file` 和一次 `read_text`。共享根聚焦用例
  1/1 通过，0.114 秒，输出
  `protected_rejected=32 allowed_io_calls=410`。
- `InstallSurfaceTripwire` 对每层组件使用不跟随链接目标的 `lstat`；合成文件
  symlink 和中间目录 reparse 均在 copy 前拒绝。共享根 doctor 聚焦用例
  1/1 通过，13.762 秒；完整 `test_windows_install.py -v` 为 12/12 通过，
  113.455 秒，计数仍为 32/410。
- 原 QQ 兼容入口复验 8/8 继续有效；本次改动未触及 QQ 测试、生产启动器或
  PK-140 业务。PK-020 保持“待集成”，等待 PK-900 补齐 Python 3.11 x64、
  Node 22、PowerShell 7.4+ 强制矩阵；在此之前不标记“已完成”。
- 本轮没有读取、stat、open、打印、迁移或修改真实个人状态、秘密、配置、缓存、
  来源、profile、模型、音频、Voice Pack、QQ runtime 或外部 GPT-SoVITS 源码；
  未借用共享项目现有环境，未运行真实服务或 Git 发布操作。

## 公开安装说明补充（2026-07-26）

- 根据用户反馈扩充根 `README.md` 的 Windows 首次安装教程，明确 `.venv` 不能安装
  Python 本身：用户先安装受支持的系统 Python，`setup.bat` 再自动创建根 `.venv`
  并安装锁定依赖。Core 不需要 Node，只有 QQ 用户需要受支持的 Node。
- 新说明覆盖官方运行时入口、版本/64 位检查、打开项目根目录、首次 setup、只读
  doctor、启动控制台、重复使用、五个 profile、常见错误与安全交接。明确用户无需
  手工运行 venv/pip，也不应把当前不支持的 Python 3.13/3.14 当作可用版本。
- 本次只修改公开文档和任务记录，不改变安装器、锁、profile、端口或产品行为；
  PK-020 继续保持“待集成”，等待目标版本矩阵。

## PK-000 最终复核退回（2026-07-26）

**结论：不通过。** 已关闭的运行时扫描、安装表面 tripwire、链接防御与 QQ
兼容回归继续有效，但 Windows CI 自身仍会把受跟踪个人状态带入所谓“干净安装”
副本，且强制 Python 3.11 x64、Node 22、PowerShell 7.4+ 无缓存矩阵没有形成
可接受证据。PK-020 已由总控退回“进行中”；本批 PK-900 保持“进行中”。

### 新阻断：Windows CI 副本边界

- `.github/workflows/windows-install.yml` 的隔离步骤执行
  `git archive --format=zip ... HEAD` 后完整解压，没有路径 allowlist 或受保护前缀
  排除。总控只读取 Git tree 路径名，确认 HEAD 中包含 7 个已跟踪个人状态：
  `server/data/` 下 4 个 JSON，以及 `server/systems/data/` 下 3 个 JSON；未读取、
  stat、diff、归档或输出其内容。
- 因此该 workflow 一旦运行，就会把这些状态复制到临时 ZIP 和 R: 副本。现有
  `InstallSurfaceTripwire` 与 `RuntimePathScanTripwire` 只保护 Python 专项测试，
  不覆盖 workflow 在测试启动前执行的全仓 `git archive`。
- 最小整改归 PK-020：把 CI 副本构造改为受版本控制的明确 allowlist，或在任何
  归档/复制 I/O 前按纯 Git 相对路径拒绝 `.env`、`README.local.md`、个人状态、
  cache、profile、model/audio、Voice Pack、QQ runtime、外部引擎、venv、
  `node_modules` 与 `vendor/`；增加纯合成 workflow/helper tripwire。不得通过
  读取真实文件内容或存在性证明排除有效。

### 仍未闭合的目标矩阵

- 当前机器实际只有 Python 3.12.7 x64、Node 24.18.0、Windows PowerShell
  5.1.26100.8875；`py.exe`、Python 3.11、Node 22 与 `pwsh.exe` 不可用。
- 当前 workflow 只使用 `shell: powershell`，没有 PowerShell 7.4+ 执行步骤；
  `actions/setup-node` 还显式启用 npm cache，安装步骤也没有冻结一个全新空
  pip cache。因此它不能作为“Python 3.11 / Node 22 / PowerShell 7.4+ 无缓存”
  的完整证据。
- GitHub CLI 当前认证失效，远端默认分支也没有可查询的 `windows-install.yml`
  workflow；总控没有提交、推送或触发远端 CI。最小整改后应在严格白名单副本中，
  分别以 Windows PowerShell 5.1 与 `pwsh` 7.4+ 执行入口/AST，使用 Python 3.11
  x64 和 Node 22 的全新空缓存完成 Core 首装、二次幂等、doctor、Core
  ASGITransport health、`setup --profile qq`/`npm ci` 及既定兼容回归。

### 本轮实际验证与隔离

- `python -B server/tests/test_windows_install.py -v`：12/12 通过，114.503 秒；
  `protected_rejected=33 allowed_io_calls=418`。测试使用 fake pip/npm/进程/端口
  和系统临时目录。
- `python -B scripts/check_task_docs.py`：退回前通过 23 个 gated task；同步把
  PK-020 改为“进行中”后复跑通过 22 个 gated task。
- Windows PowerShell 5.1 对根 `scripts/` 与 `server/scripts/` 共 11 个 `.ps1`
  做 AST 解析：0 失败。
- `git diff --check`：退出 0，仅有既有 LF→CRLF 提示。
- `python -B server/tests/test_qq_control.py` 未执行到测试：系统 Python 缺少
  FastAPI，导入阶段返回 `ModuleNotFoundError`。总控没有借用或检查共享
  `.venv`/`.venv-asr`，也没有把该环境缺失记作产品失败；上一轮严格隔离副本的
  8/8 证据继续保留，但目标矩阵仍须重跑。
- 本轮未读取、stat、diff、复制或修改任何真实秘密、个人状态、缓存、来源名单、
  profile、模型、音频、Voice Pack、QQ runtime 或外部引擎源码；未安装运行时、
  下载依赖、启动服务、暂存、提交、推送或清理混合工作区。

## PK-000 最终复核最小整改（2026-07-26）

### CI 隔离副本与永久 tripwire

- `.github/workflows/windows-install.yml` 不再执行无排除的 `git archive HEAD` 或
  `Expand-Archive`。新增 `scripts/windows_ci_copy.py`，只从 `git ls-tree -rz
  --full-tree HEAD` 接收相对路径、mode、object type 和 object id；每个候选先以
  纯字符串规范化并分类，保护候选不会构造对应工作树 `Path`，也不会到达
  `lstat`、`stat`、`open`、`read_text`、目标创建或 `copy2`。
- 允许表面只包括根安装/诊断/启动入口和活动项目文档、`requirements/`、
  `scripts/`、`tasks/`，以及 Core/API 和既定回归需要的 `server` 顶层文件与
  `core/features/intel/prompts/qq_bridge/scripts/services/static/systems/tests/tools`
  子树。保护规则先于 allowlist，明确拒绝 `.env`、`README.local.md`、
  `server/data`、`server/systems/data`、QQ data/runtime、cache、来源名单、
  profile、model/audio、Voice Pack、外部/本机 GPT-SoVITS、`.venv`、
  `.venv-asr`、`node_modules`、`vendor`、绝对路径、盘符和 traversal。
- Git mode `120000` 在工作树 I/O 前失败；允许文件在复制前对源根以下每个组件
  执行不跟随目标的 `lstat`，任一 symlink 或 Windows
  `FILE_ATTRIBUTE_REPARSE_POINT` 都在目标目录创建和 `copy2` 前失败。目标必须
  位于源仓库外且不存在或为空。
- 新增 `server/tests/test_windows_ci_copy.py` 作为永久门禁。22 个合成保护/
  绝对/traversal 候选全部在 fake `lstat/mkdir/copy` 调用数仍为 0 时失败；
  tracked symlink mode 同样为 0 I/O；合成源 symlink 与中间 reparse 只到
  `lstat`，均未到 `mkdir/copy`；允许的 `scripts/setup.ps1` 必须先完成两个
  组件 `lstat` 才到目标创建和 copy。测试另以 Git tree 元数据确认当前保护拒绝
  数至少覆盖已知 7 个个人状态，并静态冻结 workflow 的 allowlist helper、
  无缓存和双 PowerShell 矩阵。
- 从共享根实际执行 helper，得到
  `allowed=326 protected_rejected=18 ignored=8 copied=326`，目标是系统临时目录
  下的新建副本。输出只含计数，不含任何保护路径名或内容；没有归档、探测或复制
  保护文件。

### 目标矩阵与无缓存语义

- workflow 明确设置 Python `3.11` `x64`、Node `22`，运行时门禁同时断言
  Python 主次版本/64 位、Node 主版本/`x64`、Windows PowerShell 5.1 和
  `pwsh` 7.4+。pre-install doctor、Core setup/doctor 和 AST 在
  `powershell` 与 `pwsh` 下分别执行相称入口。
- 已移除 `actions/setup-node` 的 npm cache。每次 job 新建并验证空的 pip/npm
  cache，设置 `PIP_NO_CACHE_DIR=1`、独立 `PIP_CACHE_DIR` 和独立
  `npm_config_cache`，不借用 runner 的 pip/npm 预热缓存。
- Windows PowerShell 5.1 在含空格/中文的 `R:` 隔离副本执行公开
  `setup.bat --profile core` 首装、第二次幂等和 doctor；PowerShell 7.4+
  直接复用 `scripts/setup.ps1` 并运行 `scripts/doctor.ps1`。随后安装 dev
  profile，完成 Core import 与 ASGITransport `/` 健康检查。
- Node 22 的 QQ 锁安装只通过公开 `setup.bat --profile qq` 进入，由冻结产品
  入口调用 `npm ci --ignore-scripts`；后续步骤只运行 46 项 Node 测试、
  7 个 `src/*.mjs` 和 6 个 dashboard JavaScript 的 `node --check`，没有第二套
  直接安装规则。workflow 继续登记 PK-010/100/140/200/210/211/212 最小回归。
- CI 不读取 Secret，不下载模型、GPT-SoVITS 或 Voice Pack，不启动 API 监听、
  QQ、Gateway、Collector、LLM、ASR、TTS 或外部服务。本轮没有修改 setup/start
  产品行为、业务模块、公共 API、Provider 或 PK-140/211/212 业务规则。

### 本地验证、隔离与遗留矩阵

- `python -B server/tests/test_windows_ci_copy.py`：6/6 通过，约 0.06 秒；
  `python -B -m py_compile scripts/windows_ci_copy.py
  server/tests/test_windows_ci_copy.py`：通过；PyYAML 只做 workflow 语法解析：
  通过。
- 把尚未提交因而不在 `HEAD` 的 helper/专项文件补入上述过滤临时副本后，从该
  无 `.git`、无 `.github` 的副本直接运行专项：6 项中 4 项合成 I/O tripwire
  通过，2 项只依赖源 checkout Git/workflow 元数据的静态门禁按设计 skip；没有
  访问副本外路径或业务数据。
- `python -B server/tests/test_windows_install.py`：12/12 通过，113.166 秒；
  `protected_rejected=33 allowed_io_calls=418`。全部动态安装/进程/端口/网络继续
  使用 fake、tripwire 和临时目录。
- Windows PowerShell 5.1 对 `scripts/` 与 `server/scripts/` 共 11 个
  PowerShell 文件做 AST 解析：0 失败。当前 Node 24 只补充执行 7 个 QQ MJS 与
  6 个 dashboard JavaScript 的静态 `node --check`：0 失败；此结果不替代
  Node 22 矩阵。
- `python -B server/tests/test_qq_control.py` 在测试收集前因系统 Python 缺少
  FastAPI 返回 `ModuleNotFoundError`；没有下载依赖或借用共享 `.venv`、
  `.venv-asr`。此前严格隔离副本的 QQ 8/8 证据保留，但本次 workflow 目标矩阵
  必须重跑该回归。
- 当前机器仍没有 Python 3.11、Node 22 和 `pwsh` 7.4+，GitHub CLI 认证仍不可
  用。本轮没有自动安装系统运行时、提交、推送或触发远端 CI，也没有把 Python
  3.12、Node 24 或单独 Windows PowerShell 5.1 冒充完整矩阵。新的独立 PK-900
  或远端 Windows runner 仍须实际运行更新后的 workflow，核验无缓存公开锁
  安装、Core 首装/二次幂等、双壳 doctor/AST、Core import/ASGITransport health、
  QQ profile/npm ci、Node 测试和全部既定 Python 回归。
- 本轮未读取、diff、stat、open、复制、迁移或修改真实 `.env`、秘密、个人状态、
  缓存、来源名单、profile、模型、参考音频、Voice Pack 注册表、QQ runtime、
  外部 GPT-SoVITS 源码、共享虚拟环境、`node_modules` 或 `vendor`。实际文件修改
  严格限定为 workflow、CI copy helper、对应安装专项、Windows 安装架构和本任务
  记录；PK-213、PK-150、业务代码、个人状态及其他混合修改全部保留并排除。

### 八项文档门禁

- [x] TASK_RECORD — 已记录 helper/allowlist、I/O 失败语义、矩阵、无缓存行为、
  本地命令/结果和必须由 PK-900 补齐的证据。
- [x] TASKS_BOARD — PK-020 最小整改验证完成后只恢复“待集成”；名称、P0、依赖
  与 PK-900 状态不变。
- [x] PUBLIC_README — 不适用：公开安装、迁移、profile 和产品行为没有变化，
  现有 README 说明继续有效。
- [x] MODULE_CATALOG — 不适用：未新增、迁移或改变业务模块、API 与 catalog。
- [x] ARCHITECTURE_DOCS — 已补充纯 Git 路径 allowlist、链接防御、无缓存及
  Python/Node/双 PowerShell CI 边界。
- [x] LOCAL_README — 不适用：未读取、验证或改变任何本机配置、路径、模型或
  运行时；`README.local.md` 未修改。
- [x] AGENT_RULES — 不适用：现有秘密/个人数据/混合工作区与验证规则未改变。
- [x] VALIDATION — 已记录 6 项 CI copy tripwire、12 项安装专项、YAML/Python/
  PowerShell/Node 静态门禁、QQ 本机依赖阻断和未执行的真实目标矩阵。

## Python 3.13 与 BAT 窗口暂留增量整改（2026-07-26）

本节取代此前活动文档中把 Python 3.13 视为不支持版本的结论；旧段落仅保留为
历史复核证据，不再被安装器、测试、CI 或公开文档消费。本轮没有改变业务 API、
QQ 菜单、语音/情报业务规则、模块生命周期或 Provider 公共契约。

### Python 探针、依赖锁与 CI

- 正式支持范围改为 Python `>=3.10,<3.14` x64。公共 probe 对根 `.venv`、
  迁移候选 `server/.venv-asr`、`py` launcher 与 PATH 候选都执行真实
  `sys.version_info`、指针位数和机器架构探测；接受 3.10、3.11、3.12、3.13
  x64，拒绝 3.9、3.14 与 32 位。`py` 候选已包含 `-3.13-64`，setup/doctor
  错误信息列出四个受支持版本并指向 python.org，推荐版本仍为 3.11。
- 依赖审计确认旧 ASR 组合的 `numpy==1.26.4`、`ctranslate2==4.5.0` 与
  `faster-whisper==1.0.3`/`av<13` 无法形成完整 cp313 Windows wheel 表面。
  ASR 锁最小升级为 `faster-whisper==1.1.1`、`av==14.0.0`、
  `ctranslate2==4.6.0`、`numpy==2.1.3`、`onnxruntime==1.20.1`，并补入
  Windows 间接依赖 `pyreadline3==3.5.6`。
- 首次真实 voice profile 安装进一步发现未锁定的最新 setuptools 已不再提供
  `pkg_resources`，导致 `ctranslate2` import 失败。最终 ASR 锁固定
  `setuptools==75.2.0`，与 dev 锁一致；随后公开 voice setup、doctor、
  `pip check` 及 `av/ctranslate2/faster_whisper/numpy/onnxruntime`
  导入全部通过。
- 最终锁摘要为：Core
  `8280e23581206b7ef21ef001c4de580cb732eeb01607d5855fa6424216d99fe5`；
  ASR `67c44d7d715f37bf789640b7c2f5b76dc98f081656902ad73db987f544ef5c16`；
  dev `4cbd205c84455140cdd5c276224a60bdd97a61cf9adba364175df52b5afa38c0`。
  `lock-manifest.json` 已同步，锁中没有 editable、本机 wheel、`file://`、
  私有源、凭证或 CUDA 偶然依赖。
- 使用全新空 pip 下载目录和 `--platform win_amd64`/对应 CPython ABI 做公开
  artifact 审计：3.10 为 Core 40、ASR 22、dev 13；3.11/3.12/3.13 均为
  Core 40、ASR 22、dev 11。差异来自 dev 锁中仅 3.10 生效的
  `exceptiongroup`/`tomli` marker。每组仅 `qrcode-terminal==0.8`
  没有 wheel、使用公开纯 Python sdist；其余选择均为 wheel。该 sdist 已在
  全新 Python 3.12 Core setup 中构建并导入成功，3.13 的实际构建仍由目标
  runner 复验。
- Windows workflow 现为 Python 3.10/3.11/3.12/3.13 x64 矩阵；每个版本均
  以空 pip cache 和 `PIP_NO_CACHE_DIR=1` 经公开入口安装 Core、运行 doctor、
  Core import/ASGI health，并安装/导入 voice 与 dev 锁。主 3.11 job 继续
  验证首次/第二次 Core setup、Node 22 QQ profile/npm ci、兼容回归、
  Windows PowerShell 5.1 与 pwsh 7.4+ 的入口和 AST。

### 九个 BAT 的统一暂留契约

- 新增 `scripts/project-kei.pause.cmd` 作为唯一结果/暂留 helper。根
  `setup.bat`、`doctor.bat`、`start.bat`，`server/start_api.bat`、
  `start_asr.bat`、`start_gptsovits.bat`、`start_all_services.bat`、
  `prebuild_daily_briefing.bat` 与
  `server/qq_bridge/start_qq_bridge.bat` 共 9 个受跟踪 BAT 均在普通
  成功、失败或长驻进程退出后显示结果并等待按键。
- helper 在等待前保存调用方退出码，等待后原样 `exit /b`；统一自动化免暂停
  开关为 `PROJECT_KEI_NO_PAUSE=1`。CI、专项测试和每日情报计划任务显式设置
  该变量；BAT→BAT 兼容入口只在内部委托期间临时设置，恢复调用方环境后由
  最外层入口暂停一次。参数使用 `%*` 原样透传，QQ 入口仍只委托
  `start.bat --only qq --current-window`，没有恢复第二套 Node 启动规则。
- 永久测试实际执行 helper 的免暂停成功/失败与默认等待路径，验证退出码
  0/37 保持；同时静态覆盖 9 个 BAT 的单一 helper、参数透传、内部免暂停、
  零双重 pause，以及计划任务动作的显式免暂停。

### CI copy 边界与本地验证

- 既有纯 Git 相对路径 allowlist、保护前缀、绝对/traversal 和
  symlink/reparse 预 I/O tripwire 继续生效。新增精确例外只允许
  `server/features/voice/voice_packs/` 的受跟踪生产源码进入 Core/API
  副本；`server/voice_packs/` 用户注册表、参考音频、模型和敏感 basename/
  后缀仍优先拒绝。最终 helper 计数为
  `allowed=336 protected_rejected=8 ignored=8 copied=336`，输出没有保护路径
  名或内容。
- 在 allowlist 临时副本和全新 Python 3.12.7 x64 `.venv` 中，经公开
  `setup.bat --profile core` 完成首次无缓存安装、doctor、第二次幂等；
  Core import 与 ASGITransport `/` 返回 200。公开 voice/dev setup 与 doctor、
  `pip check` 和对应 imports 全部通过；没有 `.env`、模型、Voice Pack 或
  外部引擎，也没有启动监听或业务服务。
- `test_windows_install.py` 最终 14/14（139.782 秒），输出
  `protected_rejected=33 allowed_io_calls=420`；`test_windows_ci_copy.py`
  7/7（0.067 秒）；过滤副本中的 QQ 兼容回归 8/8，PK-010/100/200/210/211/212
  最小回归全部通过。
- 过滤副本使用本机 Node 24 仅作补充静态验证：QQ Node 46/46、全部
  `src/*.mjs` 与 6 个 dashboard JavaScript `node --check` 通过。Python
  compileall 通过；Windows PowerShell 5.1.26100.8875 对 11 个脚本 AST
  解析零错误。Node 24 结果不冒充 Node 22。
- `python -B scripts/check_task_docs.py` 通过 23 个 gated task；workflow YAML
  解析通过；`git diff --check` 返回 0，仅报告混合工作区既有 LF→CRLF 提示。
  最后新增的 BAT 顺序/参数断言聚焦重跑 1/1（0.149 秒）。
- 本机没有 Python 3.10、3.11、3.13、Node 22 或 pwsh 7.4+，也没有触发远端
  CI；因此这三个 Python 版本的真实无缓存 setup/import（以及 3.13 的
  `qrcode-terminal` sdist 构建）、Node 22 QQ profile 与 PowerShell 7.4+
  必须由 PK-000 安排新的独立 Windows runner/PK-900 矩阵复验。本任务只恢复
  为“待集成”，不得据此标记“已完成”。
- 本轮没有读取、stat、diff、复制或输出真实 `.env`、个人状态、缓存、来源名单、
  profile、模型、参考音频、Voice Pack 注册表、QQ runtime、共享项目
  `.venv`/`.venv-asr`/`node_modules` 或 `vendor`。PK-150、PK-213、个人状态、
  业务代码和其他混合工作区修改均原样保留并排除；没有暂存、提交、推送或清理。

### 本轮八项文档门禁

- [x] TASK_RECORD — 已记录四版本契约、真实/交叉依赖证据、锁摘要、BAT 副作用、
  CI、失败语义、命令结果和未执行矩阵。
- [x] TASKS_BOARD — PK-020 仅恢复“待集成”；名称、P0、依赖及 PK-900 状态
  未改变。
- [x] PUBLIC_README — README 与迁移指南已更新四版本支持、推荐版本、官方安装
  提示、双击暂留和自动化免暂停。
- [x] MODULE_CATALOG — 不适用：未新增、迁移或改变业务模块、API 与 catalog。
- [x] ARCHITECTURE_DOCS — Windows 安装架构与 ASR 安装说明已更新运行时、
  依赖证据、9 BAT 契约和四版本 CI。
- [x] LOCAL_README — 不适用：`README.local.md` 未读取或修改，本机配置不属于
  本轮事实源。
- [x] AGENT_RULES — 不适用：现有秘密、个人数据、混合工作区和验证规则未改变。
- [x] VALIDATION — 已记录专项、tripwire、公开 setup、依赖 artifact/import、
  兼容回归、Node/Python/PowerShell 静态门禁及待独立执行的目标矩阵。

## 远端矩阵首轮编排整改（2026-07-26）

- Draft PR #4 的首轮 Windows Actions run `30191638508` 已真实启动
  Python 3.10/3.11/3.12/3.13 x64 四个 job；四者均在安装前的
  `Create fresh empty package caches` 步骤失败，尚未执行依赖安装或业务回归。
- 失败日志证明 Windows PowerShell 5.1 的 `New-Item` 不接受
  `-LiteralPath`。workflow 已最小改为 `New-Item -Path`；同时让始终执行的
  `subst R: /D` 清理在映射尚未创建时保持成功，避免掩盖原始失败。
- `test_windows_ci_copy.py` 已永久断言 workflow 不再使用该不兼容参数，并冻结
  cache 创建与容错清理文本。PK-020 继续保持“待集成”，须等待新 run 完整通过。
- 第二轮 run `30191726833` 已通过 cache、Python/PowerShell、Node 22 和 copy
  policy 步骤，但生成 runner 脚本时把双引号形式的 `PK020_ROOT=R:\` 判为缺少
  字符串终止符。该环境行已改为单引号字面量，并增加正反断言后重新排队。
- 第三轮 run `30191812474` 证明环境行整改有效，但 runner 又在内联双引号
  `$env:GITHUB_WORKSPACE\scripts\windows_ci_copy.py` 路径处报同类解析错误。
  workflow 已改为先用 `Join-Path` 和单引号片段生成变量，再以 `& python` 传参；
  测试冻结该无内联双引号路径的调用形式。
- 第四轮 run `30191903483` 最终定位为 Windows PowerShell 5.1 对 runner 生成的
  无 BOM UTF-8 step 脚本按本地代码页解析，中文路径字面量乱码并破坏字符串。
  为继续真实覆盖中文目录而不降低验收，workflow 改用纯 ASCII Unicode 码点构造
  “中文路径”；永久测试禁止该 step 恢复非 ASCII 中文字面量。
- 第五轮 run `30191975922` 已成功创建隔离副本。pre-install doctor 按预期发现
  未安装 Core，但步骤因保留外部命令退出码而失败；同时 Windows checkout 的
  CRLF 转换触发锁摘要不匹配。新增 `.gitattributes` 仅对
  `requirements/*.lock.txt` 冻结 `eol=lf`，并让两种 shell 的预期失败检查显式
  `exit 0`；摘要算法与锁内容均未放宽。
- 第六轮 run `30192124764` 的四个版本均通过双 shell pre-install doctor，并
  成功完成 Core 锁安装、摘要校验和安装后 doctor。失败仅来自验收夹具把多行
  ASGI Python 代码作为 PowerShell 5.1 原生 `-c` 参数传递时丢失内部双引号。
  现改为 runner 临时 `.py` 文件，经同一 `scripts/python.ps1` 执行后删除；
  产品代码、API 和锁均未修改。
- 第七轮 run `30192224339` 中 Python 3.10、3.12、3.13 全部通过；3.11 已通过
  Core 幂等、双 PowerShell、voice/dev 和 QQ profile，兼容回归随后发现
  `test_dashboard_shell.py` 把项目根目录名硬编码为 `project-kei`。已删除该无效
  测试假设并增加永久断言；dashboard 产品代码与契约未改变。
- 第八轮 run `30192381985` 的 3.10/3.12/3.13 继续全绿；3.11 的 dashboard
  测试把含中文的脚本通过 `subprocess.run(text=True)` 发送给 Node 时使用默认
  cp1252，触发 `UnicodeEncodeError`。测试现显式使用 UTF-8，并由 PK-020
  tripwire 冻结；生产 dashboard 未修改。

## PK-000 最终通过结论（2026-07-26）

- Draft PR #4 的第九轮 Windows Actions run `30192550638` 四个 job 全部成功：
  Python 3.10、3.11、3.12、3.13 均为 x64，并在全新空 pip/npm cache、受保护
  allowlist 副本和含空格/中文的非系统盘路径中完成 Core、voice、dev 安装。
- 四版本均通过 pre-install doctor、Core setup/doctor、真实 import、ASGI
  `GET /`=200 和语音/dev 锁导入；3.11 额外通过 Core 二次幂等、PowerShell 7.4
  复用、Node 22 x64、公开 QQ profile `npm ci`、全部既定兼容回归、Node 语法/
  测试、Windows PowerShell 5.1 与 PowerShell 7.4+ AST、文档门禁和 diff 检查。
- 前八轮失败均保留为历史证据并已形成永久回归门禁；最终 run 未使用 Secret，
  未下载模型/外部引擎，未启动真实 QQ、Gateway、Collector、LLM、ASR 或 TTS。
- PK-000 独立确认 PK-020 验收通过，状态更新为“已完成”；本批 PK-900 同步关闭。

## 完成后现场反馈：不完整 `.venv` 启动诊断（2026-07-26）

- 用户在另一份 clone 中运行 `start.bat` 时，启动器选中已存在的根 `.venv`，
  随后 Python 裸报 `No module named uvicorn`。源码审计确认 Core 锁一直包含
  `uvicorn==0.32.1`，setup 成功门禁也会实际导入 `fastapi/httpx/pydantic/uvicorn`；
  因此该现象表示 `.venv` 已创建但 setup 未完整成功或曾被中断，不表示锁遗漏。
- 最小防回归只修改公共启动 preflight：新增只读 `Test-KeiPythonImports`，
  Core 在占端口/创建进程前检查 `fastapi,uvicorn`，ASR 显式启动检查
  `fastapi,uvicorn,faster_whisper`。缺失时固定退出 21，指向对应 setup/doctor；
  start 仍不安装依赖、不删除/重建环境、不读取配置。
- `test_windows_install.py` 新增“不完整 `.venv` 在进程前拒绝”用例；Core 正常
  启动、不完整环境拒绝、端口占用三个定向用例 3/3 通过，BAT/PowerShell 静态
  两项 2/2 通过。当前迁移期解释器实际为旧于支持范围的 Python，完整专项中
  使用 `str.removesuffix` 的既有测试辅助代码无法运行，因此没有用该环境冒充
  Python 3.10–3.13 完整矩阵；此增量交给 PK-213 的独立 PK-900 在支持版本复验。

## 完成后现场反馈：控制台浏览器地址与自动打开（2026-07-26）

- 用户在另一份干净 clone 中已成功启动 Uvicorn，但浏览器打开了监听地址
  `http://0.0.0.0:8000`，Edge 返回 `ERR_ADDRESS_INVALID`。`0.0.0.0` 只表示
  服务监听所有本机网络接口，不是浏览器导航地址；控制台的固定本地地址仍为
  `http://127.0.0.1:8000/dashboard`。
- 根 `start.bat` 继续是唯一主入口；legacy `server/start_all_services.bat`
  只委托 `start.bat --profile all`，不另建启动或浏览器规则。Core preflight
  通过后，启动器会创建隐藏的本地就绪等待进程；该进程最多等待 30 秒，以禁代理
  只读 GET 检查 `127.0.0.1` 控制台，成功后才调用系统默认浏览器。浏览器调度
  失败或超时不影响 Core，终端始终明确打印可手工访问的本地 URL。
- 新增 `--no-browser` 与 `PROJECT_KEI_NO_BROWSER=1`。前者供用户显式禁用，
  后者供 CI、测试、计划任务和后台编排禁用；两者不改变 bind host、端口、
  服务 profile、退出码或依赖安装语义。`start` 仍不运行 pip/npm、不写配置、
  不下载资产。
- 定向验证实际执行：`scripts/start.ps1` PowerShell AST 解析 0 错误；
  `test_start_does_not_install_or_create_configuration`、
  `test_start_rejects_incomplete_venv_before_starting_process`、
  `test_port_occupied_prevents_core_process_start` 与
  `test_powershell_ast_and_batch_delegation` 合计 4/4 通过（52.124 秒）。
  自动测试显式设置 `PROJECT_KEI_NO_BROWSER=1`，未启动浏览器、真实 API 或外部
  服务。真实默认浏览器打开行为仍应由下一轮 PK-900 在干净 Windows 交互环境复验。

### 本增量完成文档门禁

- [x] TASK_RECORD — 已记录现场现象、根因、统一入口、自动打开/禁用契约、测试和待复验项。
- [x] TASKS_BOARD — PK-020 因完成后增量重新置为“待集成”，未提前恢复“已完成”。
- [x] PUBLIC_README — 已明确监听地址与浏览器地址、默认自动打开及 `--no-browser`。
- [x] MODULE_CATALOG — 不适用：未修改模块映射、API namespace、进程边界或迁移状态。
- [x] ARCHITECTURE_DOCS — 已更新 Windows 启动架构的就绪等待和自动化免弹窗边界。
- [x] LOCAL_README — 已把经确认存在的根 `start.bat` 记为本机主启动器；未记录新绝对路径。
- [x] AGENT_RULES — 不适用：安全、数据、测试、Git 和协作规则没有变化。
- [x] VALIDATION — 已记录 4/4 启动专项与 AST；文档门禁和 diff 检查在交付前执行。

## 控制台自动打开增量最终复核（2026-07-26）

- 本轮联合批次登记为 `PK-020 + PK-213`。PK-020 增量只改变统一启动器的
  浏览器提示与调度：Core 仍监听 `0.0.0.0:8000`，本机浏览器地址固定为
  `http://127.0.0.1:8000/dashboard`；根 `start.bat` 和 legacy
  `server/start_all_services.bat` 继续共用同一实现。
- 独立累计运行 `test_windows_install.py -v` 为 15/15 通过（216.050 秒），
  `test_windows_ci_copy.py -v` 为 7/7 通过（0.066 秒）。覆盖含空格/中文/
  非系统盘、Python 3.10–3.13 x64 探针、setup 幂等、doctor 只读、残缺
  `.venv`、端口占用、15 个安装/启动契约及 copy tripwire；测试显式设置
  `PROJECT_KEI_NO_BROWSER=1`，没有弹出浏览器或启动真实 API。
- PowerShell AST、公开文档一致性、任务文档门禁和 `git diff --check` 通过。
  结合此前已通过的 GitHub 四版本无缓存 Windows 矩阵，本增量未发现阻断；
  PK-020 由 PK-000 恢复为“已完成”。PK-213 的独立阻断不归属于 PK-020，
  不反向改变已经冻结的安装、锁或启动契约。

## `start_all_services.bat` Core-first 一键编排增量（2026-07-28）

### 现场现象与根因

- 用户在另一份安装中双击 `server/start_all_services.bat`。统一启动器先创建了
  GPT-SoVITS 和 QQ 独立窗口，随后才发现根 `.venv` 缺少
  `fastapi/uvicorn`，Core 以退出码 21 停止；因此留下两个可选进程，但控制台
  无法使用。QQ 窗口中的日程状态 warning 与本次 Core 依赖失败相互独立。
- 根因是 `scripts/start.ps1` 的 `voice|all`、`qq|all` 分支位于
  `Invoke-CoreApi` 的 Core preflight 之前。既有“不完整 `.venv` 在进程前拒绝”
  只覆盖单独 Core 启动，没有冻结组合启动的跨进程顺序。

### 最小整改

- 抽出只读 `Test-CorePreflight`，统一检查 Core 的 `fastapi/uvicorn` 与 8000
  端口。普通 `core|voice|qq|all` 均在创建任何 GPT-SoVITS、ASR 或 QQ 子进程
  前执行一次；失败立即原样返回 21/22，保持全部可选服务未启动。
- 依赖提示跟随用户选择的组合：`core` 指向 core、`voice` 指向 voice、`qq`
  指向 qq、`all` 指向 `setup.bat --profile full` 及对应 doctor。成功预检后，
  Core 启动阶段复用该结果，不重复检查或改变端口、浏览器、解释器与退出码语义。
- `server/start_all_services.bat` 继续只委托根 `start.bat --profile all`。
  完成一次 `setup.bat --profile full` 后仍可直接双击一键启动；GPT-SoVITS、
  ASR、QQ 继续使用各自独立窗口，Core 继续在主窗口前台运行。
- start 仍不运行 pip/npm、不创建/修改 `.env`、不下载模型/引擎/Voice Pack，
  也不读取个人状态。没有修改业务 API、Provider、QQ、语音或控制台业务代码。

### ASR 一键启动配置接缝

- Core-first 整改后，用户控制台继续显示 ASR `ConnectError`；只读端口检查确认
  8010 没有监听。源码审计发现 voice/all 启动器只检查当前 PowerShell 的
  `$env:ASR_MODEL_PATH`，而双击 BAT 会创建新进程，无法继承用户在另一个终端
  临时设置的变量；主 API 虽会读取 `server/.env`，启动器此前不会。
- 公共 helper 新增严格 allowlist 导入，只在 `voice|all` 或显式 ASR 启动时从
  `server/.env` 导入 `ASR_MODEL_PATH`、`ASR_DEVICE`、`ASR_COMPUTE_TYPE`；
  当前进程已有非空变量优先。它不输出值、不导入任何 LLM/QQ Key、Cookie、
  Token 或其他字段。Core-only、QQ-only、GPT-SoVITS-only 均不经过该接缝。
- `.env.example` 和 ASR/公开安装文档已增加空的非秘密字段及人工配置说明。
  setup/full 仍不下载或寻找模型；用户必须拥有并明确填写本机模型位置。
- doctor 继续保持原严格边界，不读取 `.env` 内容；它只报告当前 PowerShell
  环境的 ASR 设置。实际 voice/all 启动才按白名单加载本机配置。

### 验证与隔离

- PowerShell AST：`scripts/start.ps1` 解析零错误。
- 新增
  `WindowsInstallTest.test_start_all_preflights_core_before_optional_services`：
  在临时项目、fake pip/npm/进程和被刻意移除的 fake uvicorn 下，组合启动稳定
  返回 21、提示 `setup.bat --profile full`，不打印任何可选进程启动消息且
  fake 进程日志不存在；同时静态冻结 Core preflight 位于两个可选启动分支之前。
- 新增 `test_voice_start_imports_only_allowlisted_asr_settings`：在临时 `.env`
  放入三个虚构 ASR 字段和一个虚构 secret，证明只导入三个白名单名、secret
  不进入启动器环境，且输出不含模型路径或 secret。PowerShell 5.1 的中文临时
  路径探针使用 UTF-8 BOM；聚焦用例 1/1 通过。
- Core-first 第一轮 `test_windows_install.py -v`：16/16 通过，159.023 秒。
  加入 ASR 白名单后最终累计重跑 17 项，16 项通过、1 项因当前 8000 已由用户
  Core 占用而按设计跳过 fake Core 启动，151.662 秒；端口占用、Core-first、
  ASR allowlist 三项另行聚焦 3/3 通过。覆盖非系统盘、空格/中文路径、setup
  幂等、五个安装 profile、端口、锁、BAT 委托、doctor 只读、零静默安装和
  运行时路径隔离；输出 `protected_rejected=34 allowed_io_calls=452`。
- 测试只使用系统临时目录与 fake 组件，没有启动真实 API、QQ、ASR、TTS、
  Collector、LLM 或浏览器；没有读取或修改真实 `.env`、日程/runtime、个人
  状态、缓存、模型、Voice Pack、外部引擎、现有虚拟环境或 `vendor/`。

### 本增量完成文档门禁

- [x] TASK_RECORD — 已记录现场根因、Core-first 编排、profile 提示、进程语义、
  验证和隔离边界。
- [x] TASKS_BOARD — 本增量实现与定向验证完成后，PK-020 置为“待集成”，未提前
  恢复“已完成”。
- [x] PUBLIC_README — 已明确 full 首次安装、legacy 一键入口、Core-first
  preflight、独立进程和失败不留子进程。
- [x] MODULE_CATALOG — 不适用：未改变模块、API、namespace 或进程所有权。
- [x] ARCHITECTURE_DOCS — Windows 安装架构已冻结组合启动顺序和 all/full 映射。
- [x] LOCAL_README — 不适用：本机路径、端口、解释器和入口位置均未改变。
- [x] AGENT_RULES — 不适用：安装、秘密、个人数据、测试和 Git 规则未改变。
- [x] VALIDATION — 已记录 AST、新增隔离用例、累计 17 项专项及聚焦 3/3；
  CI 安全副本 7/7、任务文档门禁 25 项及 `git diff --check` 退出 0，只有既有
  行尾转换提示。

## ASR 项目标准目录兼容回归整改（2026-07-28）

- 用户现场再次确认 `start_all_services.bat` 只出现 Core、GPT-SoVITS、QQ 三个
  进程，控制台 ASR 报 8010 连接失败。受版本控制历史审计确认，初始可用启动器
  会按顺序使用项目内 `server/models/asr/medium`、`server/models/asr/small`；
  PK-020 可移植改造移除硬编码时同时删除了这段项目相对目录兼容发现，只保留
  `ASR_MODEL_PATH`，导致已有模型仍在标准目录时 ASR 被跳过。
- 公共 helper 新增受限解析：当前进程/`.env` 的显式 `ASR_MODEL_PATH` 仍最高
  优先；未配置时只检查上述两个固定项目目录，medium 优先于 small。找到后仅向
  当前启动进程写入规范化路径，不修改 `.env`、不打印路径、不递归枚举模型、
  不扫描其他磁盘、不联网或下载。两处均不存在时继续安全跳过 ASR，Core 与其他
  可用组件不受影响。
- voice/all、显式 ASR 和 doctor 共用同一解析规则；doctor 仍不读取 `.env`
  内容，只报告显式配置或固定项目目录来源，不读取模型内容或显示路径。旧版项目
  内模型布局因此恢复一键启动，新用户和任意安装目录仍不依赖开发者绝对路径。
- 本增量只修改 PK-020 启动 helper、start/doctor、临时目录回归测试与公开文档；
  没有修改模型、个人配置、业务 API、语音 Provider、Voice Pack、QQ 或其他任务
  代码。TASKS 中 PK-020 保持“待集成”，等待独立累计验收。
- 实际验证：三个 PowerShell 文件 AST 零错误；新增解析与 allowlist 聚焦测试
  2/2 通过；当前工作区脱敏探针返回 `project-medium`，未输出路径；完整
  `python server/tests/test_windows_install.py -v` 为 18 项通过、1 项因用户
  进程占用 8000 而按既有规则跳过，tripwire 为
  `protected_rejected=34 allowed_io_calls=452`；任务文档门禁 25 项通过，
  `git diff --check` 退出 0（仅既有行尾转换提示）。

## 控制台启动范围说明与语音显式启动接缝（2026-07-28）

- 公开 README 已明确根 `start.bat` 默认 Core-only，以及
  `--profile voice|qq|all`、`server/start_all_services.bat` 的进程范围，避免
  把“未选择可选 profile”误判为服务启动失败。
- PK-210 增量控制接口只调用 PK-020 保留的固定 ASR/GPT-SoVITS 兼容 BAT，不复制
  安装或启动规则。控制台操作不运行 setup/pip/npm，不下载资产、不写配置；
  启动器自身继续执行既有运行时、模型/登记和端口 preflight。
- PK-020 Windows 专项累计 18/18 通过，确认 README 命令可移植、启动 BAT 委托、
  路径隔离、无静默安装和固定模型目录回归保持不变。PK-020 继续为“待集成”，
  与本次 PK-210 控制增量一并交独立验收。

## 本机 API/ASR 默认暴露边界 P0 安全增量（2026-07-29）

### 威胁模型与冻结边界

- Project Kei 当前是本机桌面服务，不是反向代理后的 LAN/Web 公共服务。风险包括
  同网段客户端直接访问 8000/8010、浏览器跨站请求，以及使用 `Host`、
  `Origin`、`X-Forwarded-For`、`Forwarded` 伪造本机身份。
- 客户端身份只取 ASGI server 提供的底层 `scope["client"]` /
  `request.client.host`：IPv4 `127.0.0.0/8` 与 IPv6 `::1` 允许，缺失、
  `localhost` 字符串、IPv4-mapped IPv6、LAN/公网地址或无法解析的值失败关闭。
  Header 从不覆盖 peer 身份。
- 本轮不提供 LAN 模式、token、账户、代理信任或远程管理；未来若需要 LAN
  暴露，必须另立默认关闭、显式高风险确认的独立契约。业务 API 请求/响应、
  端口、QQ/voice/Provider 契约不变。

### 生产 bind、HTTP、WebSocket 与 CORS

- `scripts/start.ps1` 的 Core 8000 与 ASR 8010 命令和日志统一为
  `127.0.0.1`。`server/api.py`、`server/services/asr_server.py` 的直接
  Python 入口也固定为 `127.0.0.1`。根 BAT、兼容 BAT/PowerShell 与控制台
  voice-control 接缝继续委托这些固定入口，没有第二套 host 参数或
  `0.0.0.0` 回退。
- 新增 `server/core/local_access.py`。最外层 `LoopbackAccessMiddleware`
  在 router、静态文件、CORS 和模块 guard 之前统一保护全部 HTTP 与 WebSocket
  scope；lifespan 等非请求 scope 原样通过。HTTP 拒绝固定为 403
  `{"detail":"仅允许本机访问"}`，不含路径、状态、Key 或上游错误。
- 实际装配共枚举 147 个 HTTP 路由，覆盖 `/`、docs、静态 dashboard、
  `/chat*`、`/history*`、calendar、demon、relationship/memory、fitness、
  briefing/intel、module、QQ、voice/Voice Pack 及所有 legacy/危险写入口。
  非 loopback 在 downstream/handler/repository 前统一拒绝；本机 `/` 的
  既有 200 语义在 `127.0.0.1`、其他 `127/8` 与 `::1` 保留。
- 实际 WebSocket 路由为 `/ws/chat`。非 loopback 或恶意 Origin 在
  `websocket.accept` 前收到 1008 close；`127.0.0.1`、其他 `127/8` 与
  `::1` 进入原 handler。WebSocket 不依赖普通 HTTP middleware 的偶然行为。
- CORS 不再通配，精确值为 `http://127.0.0.1:8000`、
  `http://localhost:8000`、`http://[::1]:8000`，
  `allow_credentials=false`。`null`、空白、重复、LAN、HTTPS 或任意其他
  Origin 均不获得授权；非 loopback OPTIONS 预检先被全局边界拒绝。无 Origin
  的本机 CLI、QQ sidecar、ASR/TTS Provider 与 ASGI 调用保持兼容。原模块
  guard 保留为纵深防御。

### 永久回归、实际命令与结果

- 新增 `server/tests/test_local_access_boundary.py` 并登记进 Windows CI。
  测试以显式 ASGI client、合成 scope、fake downstream 和保护路径 I/O
  tripwire 枚举实际装配：4/4 通过，`http_routes=147`、
  `websocket_routes=1`。API 导入阶段
  `protected_rejected=1 protected_resolve_shortcuts=5
  allowed_io_calls=37`；保护路径在底层 `stat/open/read/write` 前拒绝或改用
  纯词法 resolve，没有读取真实状态。
- `python -B server/tests/test_windows_install.py -v`：19 项中 18 通过、
  1 项因本机 8000 已被既有进程占用而按原规则跳过，171.962 秒；独立新增 bind
  与 BAT/AST 聚焦 2/2 通过。累计 tripwire 为
  `protected_rejected=34 allowed_io_calls=456`。永久扫描明确拒绝受控生产
  Core/ASR 脚本中的 `0.0.0.0`，并断言两个 uvicorn host 均为
  `127.0.0.1`。
- `python -B server/tests/test_windows_ci_copy.py -v`：7/7 通过；workflow 的
  ASGI health 显式注入 `client=("127.0.0.1", 53000)`，主 3.11 回归新增
  local-access 专项。安全复制策略、四 Python 版本、Node 22、双 PowerShell
  和全新空 cache 设计均保留。
- 在过滤后的含空格/中文临时副本中，使用全新临时 Core lock 环境运行：
  dashboard、installable modules、QQ 8/8、conversation/history、
  calendar、demon、voice、voice runtime control、feature catalog 全部通过。
  副本计数为 `allowed=360 protected_rejected=8 ignored=8
  allowed_io_calls=1238`。前两次组合回归只因 Git tree 尚不含其他任务的
  dashboard/Bilibili/papers 新源码而在 import 前失败；仅把这些明确产品源码/
  静态资产覆盖到临时副本后重跑通过，不把夹具缺项记为产品失败。
- 临时 QQ 目录使用全新 npm cache 执行
  `npm ci --ignore-scripts --no-audit --no-fund`，随后 Node 测试 55/55、
  QQ `src/*.mjs` 与 dashboard 全部 JavaScript `node --check` 通过。
  本机 Node 24.18.0 结果仅为补充，不冒充 workflow 已冻结的 Node 22。
- 临时副本 `python -B -m compileall -q server scripts` 通过；Windows
  PowerShell 5.1 AST 13/13 通过。当前本机没有 `pwsh`，因此 PowerShell 7.4+
  与目标 Node 22 不在本地重复声明通过，须由新的 PK-900/远端 Windows runner
  按现有 workflow 累计复验。
- `python -B scripts/check_task_docs.py` 通过，输出
  `task documentation gate passed: 24 gated task(s)`；`git diff --check`
  退出 0，仅有混合工作区既有 LF→CRLF 提示，无空白错误。

### 数据隔离、混合工作区与遗留事项

- 所有 API 动态回归使用 ASGITransport/fake WebSocket/fake downstream，
  未监听真实端口，未访问业务网络，未启动 QQ、Collector、LLM、ASR、TTS、
  GPT-SoVITS 或浏览器。公开 PyPI/npm 只用于全新临时锁环境；未借用共享
  `.venv`、`.venv-asr` 或 `node_modules`。
- 未读取、stat、diff、复制、输出或修改真实 `.env`、聊天/记忆、个人状态、
  来源名单、cache/profile、模型、参考音频、Voice Pack 注册表、QQ runtime
  或 `vendor/`。测试只使用过滤副本、合成 sentinel 和系统临时目录。
- 共享工作区中的 PK-030/100/120/130/133/140/150/213、dashboard、Bilibili、
  papers、个人状态及其他混合修改全部保留；本轮只改本机边界、启动 host、
  PK-020 测试/CI 和必要活动文档。未暂存、提交、推送、切分支、清理或修改
  现有 PR。
- PK-020 现交回“待集成”。总板由 PK-000 所有，本轮没有抢写 `TASKS.md`；
  新的 PK-900 必须复验本机 HTTP/WS/CORS 边界、启动器扫描及现有 Windows
  Python 3.10–3.13/Node 22/PowerShell 5.1 与 7.4+ 累计矩阵，PK-020 不自行
  标记“已完成”。

### 本增量八项文档门禁

- [x] TASK_RECORD — 已记录威胁模型、受保护路由、HTTP/WS 差异、精确 CORS、
  启动入口、测试、隔离、失败夹具和遗留矩阵。
- [x] TASKS_BOARD — 按总控要求未修改总板；任务文件置“待集成”，等待 PK-000
  同步总板和创建新的 PK-900 验收。
- [x] PUBLIC_README — 已把 Core/ASR 改为 loopback-only，并公开全局 HTTP/WS、
  peer identity、精确 Origin 与无 LAN 模式边界。
- [x] MODULE_CATALOG — 未改模块映射/生命周期；installable modules 与 feature
  catalog 最小回归通过。
- [x] ARCHITECTURE_DOCS — Windows 安装、ASR、模块化单体、QQ、Voice Pack 中的
  旧 LAN/通配 CORS 陈述已更新为全局本机边界。
- [x] LOCAL_README — 本机路径、解释器、端口号和入口位置未改变，不需修改。
- [x] AGENT_RULES — 全程保护秘密/状态/资产/共享环境，保留混合工作区且无 Git
  发布操作。
- [x] VALIDATION — 本机可安全执行的专项、兼容、Node 补充、compile、AST、
  文档和差异门禁均执行；Node 22/PowerShell 7.4+ 累计矩阵明确交 PK-900。

## 已安装官方 QQ sidecar 依赖 deployment 增量（2026-07-30）

### 入口、解析与不可变边界

- `setup.bat --profile qq|full` 仍是唯一安装入口；start、网页、adapter 和模块
  lifecycle 不运行 npm。未安装 `qq_bridge` 时继续在受跟踪源码树执行兼容
  `npm ci --ignore-scripts`。只有 PK-010 `ModuleManager.get()` 明确返回
  `package_source=official_github_release` 且公开
  `resolve_sidecar_deployment("qq_bridge")` 成功时，才进入已安装模块分支。
- descriptor 固定 current module/version、只读 package root、独立
  `server/runtime/module-dependencies/qq_bridge/<version>/` 和
  `installed_tree_sha256`。PK-020 在任何复制/npm 前重算完整 package tree
  摘要，并核对 package manifest 的 id/version/type/adapter；非 current、
  local import、registry/path 损坏或摘要变化失败关闭，不回退源码树。
- 不在 `runtime/modules/<id>/<version>` 内运行 npm，也不从
  `installed_tree_sha256` 排除任何文件。只把 package 内固定
  `sidecar/package.json`、`package-lock.json` 和 8 个 `src/*.mjs` allowlist
  复制到随机同父 staging；源/目标的 symlink、reparse、hardlink、非普通文件、
  逃逸、非 npm 官方 registry URL或缺 integrity 均在 npm/切换前拒绝。

### 原子 deployment、marker 与失败语义

- npm 只在随机 staging 中运行。成功后最后写
  `.project-kei-deployment.json`，再以同卷 rename 原子切换 current version
  deployment；npm/复制/摘要/marker/切换失败会安全清理 staging，保留旧
  deployment、只读 package root、registry、`server/qq_bridge/.env` 与
  `server/qq_bridge/data/`。版本目录相互隔离，旧版本 deployment 可由模块卸载
  随其可再生成程序目录清理，持久配置/状态不在该根。
- deployment 根顶层只允许 marker、`package.json`、`package-lock.json`、
  `src/`、`node_modules/`，入口固定为 `src/index.mjs`。marker 未知字段拒绝，
  严格字段为 `schema_version=1`、`module_id`、`version`、
  `installed_tree_sha256`、`package_json_sha256`、`lock_sha256`、
  `node_version`、`npm_version`；三个摘要必须是 64 位小写 hex，marker 不含
  path、env、命令、时间或秘密。Node 只接受 20/22/24 x64，npm 冻结为随这些
  Node 线使用的 9/10/11。
- 第二次 setup 在 descriptor、三个摘要、marker、固定复制表面与依赖均匹配时
  不再运行 npm。doctor 只读执行同一 inspect，报告
  `ready/missing/invalid` 类别，不显示 package/deployment/解释器绝对路径，不
  读取 QQ `.env` 内容或 data；源码树兼容 doctor 行为保留。

### 实际验证、隔离与遗留

- `python -B server/tests/test_windows_install.py`：25/25，276.228 秒；
  `protected_rejected=34 allowed_io_calls=460`。其中新增 deployment 聚焦 6/6，
  覆盖官方 current、首次/二次幂等、missing/ready doctor、package 摘要不变、
  npm 原子失败、版本隔离、marker 未知字段、registry/path/lock/摘要攻击、
  reparse/hardlink 在 copy I/O 前拒绝及零业务进程。
- Windows PowerShell 5.1.26100.8875 对 common/setup/doctor AST 3/3；
  Python compile 通过。系统 Python 缺 FastAPI，且本轮禁止借用共享
  `.venv/.venv-asr`，因此 `test_qq_control.py`、`test_installable_modules.py`
  和 QQ installable-package 回归未在本机冒充执行，须由新的隔离 PK-900
  环境连同 Node 22、PowerShell 7.4+ 累计矩阵复验。本机 Node 24 只被 fake npm
  专项用于受支持范围补充，不冒充 Node 22。
- 当前官方 Catalog 仍无已发布 QQ 条目；本轮只以临时 registry/runtime 和 fake
  npm 合成验证 official installed seam。PK-011/PK-000 负责发布正式资产；
  PK-140 负责 deployment-aware adapter 注册/facade 与固定持久 cwd，PK-020
  未复制其启动、配置或业务规则。
- 全程未读取/输出真实 `.env`、QQ data/runtime、个人状态、缓存、来源名单、
  profile、模型、音频、Voice Pack、共享 venv/node_modules 或 `vendor/`；
  未运行真实 npm、网络或业务服务。TASKS、README、架构、Catalog、dashboard、
  Core/QQ 业务和其他混合修改均保留未覆盖，且无暂存、提交、推送或清理。

### 本增量八项文档门禁

- [x] TASK_RECORD — 已记录 descriptor、摘要、allowlist、marker、原子切换、
  失败语义、doctor、测试与遗留集成。
- [x] TASKS_BOARD — 按总控要求未修改；任务文件保持“待集成”。
- [x] PUBLIC_README — 不适用：PK-011 共享 README 冻结，普通 profile 命令未变。
- [x] MODULE_CATALOG — 不适用：未伪造尚未发布的 QQ Catalog/Release 条目。
- [x] ARCHITECTURE_DOCS — 不适用：PK-010/PK-011 已冻结 deployment 契约，
  本轮只消费，不改共享架构文件。
- [x] LOCAL_README — 不适用：未读取或修改本机路径/配置。
- [x] AGENT_RULES — 不适用：安全、混合工作区和 Git 规则未改变。
- [x] VALIDATION — 已记录 25/25、聚焦 6/6、AST/compile 和未执行矩阵。

## Core supervisor 与控制台受控重启增量（2026-08-08）

### 威胁模型、owner 与 scope

- 浏览器是不可信参数来源：不得提供 command、path、PID、host、port、profile 或
  其他执行参数；Core 也不得在正在处理 POST 时同步终止自己。唯一 owner 是由根
  `start.bat` → `scripts/start.ps1` 创建的 `scripts/supervise_core.py`，它从自身
  文件位置解析项目根，并只持有固定 `127.0.0.1:8000` Core 子进程。
- supervisor 不接受任何命令行参数。session 是 launcher 随机生成的 32 位小写
  hex，仅用于选择固定 `server/runtime/supervisor/<session>/`；公开响应不暴露
  session、控制目录、解释器路径或 PID。首次 8000 preflight 仍在任何可选组件前
  完成，不会按端口/名称替换或终止未知进程。
- restart scope 固定为 `core`，不会新增启动 `voice|qq|all` profile 的 ASR、
  GPT-SoVITS、兼容 QQ、Collector 或模型进程。已启用 in-process 模块和由 Core
  lifespan 管理的 enabled module sidecar 属于 Core runtime 组合，会按 PK-010
  既有生命周期重新装配；用户显式 profile 打开的独立进程/窗口不在 supervisor
  owner 集合。本轮没有复制或改变模块业务生命周期。
- restart 前以同一已验证 Python 执行固定 Core import preflight；失败则写入
  `failed` 并保留当前可用 Core。只向直接持有的 child process group 发出停止，
  不接受外部 PID；端口未释放时不终止端口所有者，也不启动 replacement。新进程
  启动失败或未通过禁代理 loopback readiness 时诚实返回 `failed`。

### PK-100 精确接口与重连契约

- `POST /api/v1/dashboard/service/restart`：必须是底层 loopback peer、精确受信
  dashboard Origin、显式 POST；JSON 对象必须且只能含
  `{"confirmation":"restart-project-kei-core"}`。首次请求返回 202/
  `accepted`；并发或重复请求在 `accepted|restarting` 期间复用同一
  `request_id`，不生成第二次动作。确认缺失/错误返回 400。
- `GET /api/v1/dashboard/service/restart/status`：要求真实 loopback peer；同源浏览器
  GET 缺少 Origin 时允许，若携带则必须为精确可信 Origin，不以 Referer/Host/
  XFF/Forwarded 补充身份。字段固定为 `available,state,scope,request_id,generation,
  retry_after_ms,message`；状态枚举为
  `unavailable|starting|running|accepted|restarting|failed`。无 supervisor 时
  GET 为 200/`unavailable`，POST 为 503/`unavailable`，不得假报 accepted。
- PK-100 必须先做人机二次确认；POST 后立即禁用重复按钮，按服务返回的
  `retry_after_ms`（当前过渡态 500 ms）轮询。旧 Core 退出期间连接失败是正常
  过渡，页面继续重连 GET；只有同一 request id 在更高 generation 返回
  `running` 才显示成功，`failed|unavailable` 为终态。UI 不得降级为执行 BAT、
  拼接命令或传递路径/PID/host/port。
- 两个端点复用全局 loopback middleware；status GET 使用 `_is_local_request`，
  POST 使用 `_is_local_control_request`。POST 以及携带 Origin 的 GET 仅接受
  `http://127.0.0.1:8000`、`http://localhost:8000`、`http://[::1]:8000`；
  伪造 Host/X-Forwarded-For/Forwarded 不参与身份判断。错误只返回固定本机提示，
  不含配置、秘密、个人状态、路径、进程信息或上游错误体。

### 实际修改与验证

- 新增 `server/core/restart_supervisor.py`（严格 session/status/request 协议与
  原子 JSON）、`scripts/supervise_core.py`（固定 Core owner）和
  `server/features/dashboard/restart_router.py`；`server/api.py` 只增加 router
  装配，业务请求/响应未改。`scripts/start.ps1` 的普通 profile Core 改由
  supervisor 持有；`--only api` 兼容直启保留并诚实显示 unavailable。
- 新增 `server/tests/test_restart_supervisor.py` 并登记默认离线 inventory；覆盖
  loopback/IPv6、GET 无 Origin/好 Origin/坏 Origin、POST 缺失/好/恶意/重复
  Origin、伪造转发头、二次确认、拒绝浏览器执行字段、并发去重、无 supervisor、
  固定 child、preflight 保留旧 Core、端口占用、replacement 启动失败与脚本相对
  路径。拒绝 tripwire 在 status/process I/O 前触发；Core-only 断言解析受控命令
  token 与固定 `uvicorn api:app` 目标，不再对可能含 `.venv-asr` 的解释器绝对路径
  做裸 substring。全部使用 ASGITransport、fake process/fake port 和临时 runtime；
  不启动真实 Core/QQ/voice/collector。
- 纯标准库 fake supervisor 聚焦通过：重复请求归并为 1 个 request id，固定 child
  仅为旧/新两代 Core 共 2 个，generation 从 0 到 1，终态 `running`。随后在全新
  临时 `--no-cache-dir` 目标安装公开 core/dev 锁并执行真实 FastAPI/
  ASGITransport：接口语义 6 项通过、symlink 夹具因本机权限跳过，唯一失败为静态
  测试字符串误含补丁符号；修正后以锁中相同 FastAPI/httpx/pytest/
  pytest-asyncio 直接版本在全新临时目标最终重跑（含真实 `api.py` 隔离子进程
  装配）8 通过、1 symlink skip，3.16 秒。
  两个临时依赖目录均已精确清理，未借用或修改共享 `.venv/.venv-asr`。PK-900 仍须
  在完整锁环境复跑修正后的 9 项，不能用本机 Python 3.12 补充结果代替目标矩阵。
- `server/tests/test_windows_install.py -v` 首轮 25 项中 24 通过，暴露 supervisor
  函数误放入 PowerShell here-string；修复后相关聚焦 1/1（18.268 秒），最终完整
  重跑 25/25（267.042 秒）通过，tripwire 为
  `protected_rejected=36 allowed_io_calls=732`。安装副本 allowlist 增加 supervisor
  与固定协议模块，fake uvicorn 只在临时 127.0.0.1:8000 响应一次 readiness，
  不访问业务网络或默认状态路径。
- `server/tests/test_windows_ci_copy.py` 8/8，测试 inventory 89 文件完整、默认
  offline 75 文件、参数契约零缺口；新文件继续受既有纯 Git 相对路径 copy policy
  与保护前缀 tripwire 约束。Python compile、PowerShell 5.1 AST 和
  `git diff --check` 在最终门禁再次执行。

### 数据、混合工作区与遗留验收

- 未读取、stat、diff、复制、输出或修改真实 `.env`、个人状态、聊天/记忆、来源
  名单、cache/profile、模型、参考音频、Voice Pack、QQ runtime、共享 venv/
  node_modules 或 `vendor/`。没有停止当前真实服务、监听生产端口、调用业务网络或
  运行 QQ/LLM/ASR/TTS/Collector。
- 共享工作区已有 PK-010/030/100/140/150/211/213、dashboard、voice、QQ 与个人
  状态修改均保留。本轮只修改 supervisor、最小 API 装配、PK-020 测试/inventory、
  Windows copy/install allowlist 及必要 README/架构/任务 hunk；未暂存、提交、
  推送、切分支或清理，`TASKS.md` 未抢写。
- 本机缺完整隔离 dev runtime；PK-900 必须在过滤副本中运行新专项与既定兼容回归，
  并复核 Windows Python 3.10–3.13 x64、Node 22、PowerShell 5.1/7.4+ 矩阵。
  PK-020 保持“待集成”，不得自行标记完成。

### 本增量八项文档门禁

- [x] TASK_RECORD — 已记录威胁模型、owner/scope、接口、状态机、失败语义、测试与
  遗留矩阵。
- [x] TASKS_BOARD — 总板归 PK-000，本轮未修改；任务文件保持“待集成”。
- [x] PUBLIC_README — 已公开根 supervisor、Core scope、unavailable、确认/去重和
  轮询重连契约。
- [x] MODULE_CATALOG — 未改 Catalog、manifest 或模块业务生命周期；仅披露 Core
  既有 enabled composition 会随 runtime 重装配。
- [x] ARCHITECTURE_DOCS — Windows 安装架构已记录固定命令、owner、控制文件、
  HTTP 状态与 PK-100 交互顺序。
- [x] LOCAL_README — 未改变用户本机路径或配置，不读取/修改该文件。
- [x] AGENT_RULES — 保护数据与混合工作区，无真实进程/网络和 Git 发布操作。
- [x] VALIDATION — 本地可执行的 fake/安装/copy/inventory/AST/compile/diff 门禁已
  执行；缺 FastAPI 的完整 ASGI 与目标 Windows 矩阵明确交 PK-900。

## Node 运行时扩展与已安装模块依赖部署增量（2026-08-09）

- Windows 公共解析器、setup、doctor 和 start 统一接受 Node.js 20/22/24/26 x64，
  推荐 Node 24 LTS；20 只作为旧环境兼容。奇数/EOL 主版本及非 x64 继续拒绝。
- `setup.bat --profile qq` 现在对官方 Release 与浏览器本地 ZIP 安装的 QQ 模块使用
  同一个当前版本 descriptor、包树摘要、公开 registry lock、固定文件 allowlist 和
  独立 `module-dependencies` 根。它不再因 `source=local_import` 误判为不可信。
- npm 仍只在用户显式 setup 时以 `npm ci --ignore-scripts` 执行；上传、普通启动、
  doctor 和控制台按钮都不会安装依赖。staging/marker 原子切换失败时保留旧部署，
  包目录、注册表、`.env` 和 QQ 数据不变。
- Windows CI 保留 Python 3.10–3.13 矩阵，并新增 Node 22/24/26 x64 独立矩阵；每项
  从 Git 过滤副本和空缓存调用公开 QQ setup/doctor，再运行 Node 测试和语法检查。
- 本机可执行证据：Windows 安装专项 27/27（Python 3.12，
  `protected_rejected=36`、`allowed_io_calls=744`）；local ZIP/Node26/幂等专项 3/3；
  CI copy 8/8。旧 `server/.venv-asr` 的 Python 3.8 不在支持范围，未为通过测试而
  修改或安装其环境。

### 本增量八项文档门禁

- [x] TASK_RECORD — 已记录版本、依赖部署、原子性、测试和遗留远端矩阵。
- [x] TASKS_BOARD — 已由 PK-000 将 PK-020 重新登记为“待集成”。
- [x] PUBLIC_README — 已同步 Node 20/22/24/26 与 Node 24 推荐值。
- [x] MODULE_CATALOG — QQ 候选 runtime 声明已同步。
- [x] ARCHITECTURE_DOCS — Windows 安装与模块包契约已同步。
- [x] LOCAL_README — 不适用：未读取或修改本机私有说明。
- [x] AGENT_RULES — 不适用：保护数据和 Git 边界未改变。
- [x] VALIDATION — 本地 Windows/fake npm/copy/静态测试已执行；远端 Node 三版本
  真实矩阵留给 PK-900，不用本机 Node 24 冒充。

## 首轮远端矩阵结果（2026-08-10）

- GitHub Actions run `31326237028` 已真实通过 QQ Node 22/24/26 x64 三项，关闭本轮
  Node 扩展的远端证据门禁。
- Python 3.10–3.13 四项的安装、doctor、Core/voice/dev locks、QQ profile、inventory
  和 collect 均先通过，随后完整 pytest 因 PK-010 Catalog 空可选字段兼容问题各自失败；
  四项不是安装器或 Python 版本故障。PK-010 已作最小兼容修复，须由新提交重新取得
  四版本完整绿色结果后才能关闭 PK-020/PK-900。

## Windows voice-media hash lock 增量（2026-08-10）

### 依赖事实与安装契约

- 新增独立 `requirements/voice-media.in` 与
  `requirements/voice-media-win.lock.txt`，只固定 `silk-python==0.2.8`。锁只包含
  PyPI 发布页列出的 Windows x64 CPython wheels：cp310
  `6f4533e320239c0599ef272654f230020442d94273be457f136ce8c48b4aa808`、cp311
  `3afcebce1dd18130d352a2d669a8b16977c36b789d5f708c379959a08b05a3f5`、cp312
  `b9bb030589150e0d91f8148971eebf6f9211e6839af64dd39b26b9802be242b0`、cp313
  `450dc26c71e9fd3cbdc694319d5fb24aae50d20321c9e29982d358aafbee628c`。
  文件名、平台 tag 与摘要已逐项对照 PyPI `silk-python/0.2.8` release files，且与
  PK-210 冻结常量一致；没有下载或提交 wheel、源码或二进制，也没有使用本机
  `pip freeze`。
- `lock-manifest.json` 新增 voice-media lock 内容摘要
  `166796e43e39633382ae66dd11eb83a81c36c1578213dbc1cd86b2c8219fab1d`。
  `voice|full` 在 Core 与 ASR 后单独以 `--require-hashes --only-binary=:all:` 安装
  该锁；先验证 Windows x64 和 CPython 3.10–3.13。网络、hash、平台或解释器不匹配
  均稳定失败，不回退 sdist、其他 wheel 或未锁版本。重复运行沿用 pip 的已满足
  语义，不重建 `.venv`。`core|qq|dev` 不消费该锁，媒体依赖缺失不阻断 Core。
- setup 安装后与 doctor 使用同一个只读 capability probe：distribution version 必须
  精确为 `0.2.8`，`pysilk` 必须可导入，`encode` 必须 callable。探针不调用 encoder、
  不写配置/缓存、不下载、不启动业务服务。voice/full 缺失时 doctor 返回
  `voice media unavailable (<category>)` 并令所选 profile 失败，同时明确 Core 可用；
  Core doctor 不执行媒体探针。
- Windows CI 继续以全新空 pip cache 和 `PIP_NO_CACHE_DIR=1` 覆盖 Python
  3.10/3.11/3.12/3.13 x64；每项公开运行 voice setup/doctor 后显式核对
  `silk-python==0.2.8`、`pysilk` import 与 callable encoder。CI copy required surface
  同步包含 input/lock；不使用 Secret、模型、QQ 状态或业务网络服务。

### 本地验证与遗留矩阵

- `python -B server/tests/test_windows_install.py -v`：27/27，通过，308.453 秒；
  `protected_rejected=36 allowed_io_calls=744`。fake pip 只在临时 venv 写合成
  `pysilk`/distribution metadata，fake `encode` 若被调用即抛错，因此 doctor 成功
  同时证明零编码。另覆盖两次 voice/full hash 参数、媒体锁定安装失败无回退、移除
  合成依赖后 voice doctor 失败/Core doctor 成功，以及 doctor 前后临时文件树一致。
- 聚焦 profile/failure/lock 3/3 通过；`server/tests/test_windows_ci_copy.py -v`
  8/8 通过。变更 Python 文件 `py_compile`、Windows PowerShell 5.1 AST、四份 lock
  manifest 摘要复算、29 项任务文档门禁和 `git diff --check` 均退出 0（仅既有
  LF→CRLF 提示）。所有安装测试只使用白名单临时副本、fake pip/npm/进程与合成 metadata，
  未访问真实 venv、node_modules、配置、个人状态、模型、音频、Voice Pack 或 QQ runtime。
- `server/tests/test_voice_silk_encoder.py` 在系统 Python 导入阶段因没有 FastAPI 而未
  运行；本轮没有借用共享 venv 或联网安装依赖。该测试仍由 Windows runner 的 voice/dev
  锁环境执行；本地 PK-020 专项已用“调用即抛错”的 fake `encode` 证明 doctor 不编码。
- 本机只有 Python 3.12 x64，且没有执行公开 wheel 安装或业务编码；所以本轮不把本地
  fake 证据冒充四版本真实安装。新的 Python 3.10–3.13 x64 无缓存 wheel 下载、hash
  校验、doctor/import 绿色矩阵必须由提交后的 Windows runner 和新 PK-900 完成。
  未暂存、提交、推送、触发远端 CI 或清理混合工作区。

### 本增量八项文档门禁

- [x] TASK_RECORD — 本节记录四 wheel 摘要、profile、失败语义、doctor 与验证。
- [x] TASKS_BOARD — 总板由 PK-000 管理，本轮未抢写；PK-020 保持“待集成”。
- [x] PUBLIC_README — 已说明 voice-media 锁、缺失降级与故障处理。
- [x] MODULE_CATALOG — 不适用：未修改 PK-210/PK-140 模块、manifest 或业务实现。
- [x] ARCHITECTURE_DOCS — Windows 安装架构已同步独立层、profile、doctor 与 CI。
- [x] LOCAL_README — 不适用：未读取或修改任何本机说明/配置。
- [x] AGENT_RULES — 不适用：任务边界、数据保护和 Git 规则未改变。
- [x] VALIDATION — 临时副本 fake 专项、copy tripwire、AST/compile/文档/diff 门禁；
  四版本真实公开安装矩阵明确留给 PK-900。

## QQ 0.1.9 本机候选安装整改与真实部署验证（2026-08-10）

- 通过 PK-010 正式 disable/update/enable 流程把本机 `qq_bridge` 从 0.1.5 更新到
  0.1.9；没有直接编辑 `server/runtime` 或 registry。候选 ZIP 在系统临时目录生成，
  SHA-256 为 `871cd5043a73dca5c486319c45e8ef2af14b4aaecf21d32c90e15ebcf8a7eb7f`，
  15 个条目，未包含 `.env`、data、node_modules、个人状态、模型或 Voice Pack。
- 真实部署暴露 `scripts/resolve_qq_module_runtime.py` 的固定 sidecar allowlist 漏掉
  `src/voice_reply.mjs`。已把该文件加入受控复制集合，并在
  `server/tests/test_windows_install.py` 的合成安装包与目标部署树断言中永久固定；没有
  扩大为通配复制，也没有接受浏览器/manifest 提交命令或路径。
- 定向永久回归：
  `python -m unittest server.tests.test_windows_install.WindowsInstallTest.test_installed_qq_module_uses_current_lock_idempotently_and_doctor_is_read_only`
  为 1/1 通过（23.748 秒）。随后用正式 `setup.bat --profile qq` 接缝执行固定
  `npm ci --ignore-scripts`，Node 24.18.0 / npm 11.16.0，新增 1 个公开依赖、审计 0
  vulnerability，dependency marker 原子切换为 ready。
- 项目旧 `.venv` 引用已移除的 Python 3.12，按用户明确授权仅移动为
  `.venv.broken-20260810-194409` 备份，没有删除。首次 Core 重建因系统 pip cache 权限
  失败；以 `PIP_NO_CACHE_DIR=1` 重跑公开 hash-lock 后成功，`doctor.bat --profile core`
  全绿，Core 在 127.0.0.1:8000 恢复。安装器未读取或覆盖 `.env`、QQ 数据、个人状态、
  模型、缓存或 Voice Pack。
- 本轮只是本机候选安装验证；PK-020 继续保持“待集成”。破损 venv 备份属于本机恢复
  资产，不得暂存或打包；最终是否删除由用户另行决定。

## voice-media 传递依赖锁整改（2026-08-10）

- 真实 `setup.bat --profile voice` 证明首版锁只固定 `silk-python==0.2.8`，却漏掉其
  `cffi>=1.0.0` 传递依赖；pip 在 `--require-hashes` 下正确拒绝未精确固定的依赖，
  因而没有进行不受控安装。该失败与用户操作、ASR 模型、GPT-SoVITS 或 Voice Pack
  无关。
- 继续保持顶层 `voice-media.in` 只声明 `silk-python==0.2.8`；解析锁新增
  `cffi==1.17.1` 的 CPython 3.10/3.11/3.12/3.13 Windows x64 wheel 摘要，以及
  `pycparser==2.22` 通用 wheel 摘要。所有 wheel 都从官方 PyPI 下载到系统临时目录
  复算 SHA-256；不提交 wheel、源码或二进制，不回退 sdist/无锁版本。
- 新锁摘要为
  `8ce59b21ae0e2345595abbee3dd5222f53d5663bf0cf4e3f65d8243f574ed00a`；
  `lock-manifest.json`、公开 README、Windows 安装架构和永久测试同步更新。PK-020
  仍保持“待集成”，须在本机安装/doctor 与远端四 Python 版本矩阵通过后关闭。

## QQ 0.1.24 依赖部署 allowlist 接缝整改（2026-08-12）

- 本机正式更新暴露：`qq_bridge@0.1.24` 新增受控关闭入口
  `sidecar/src/shutdown_control.mjs`，但 Windows QQ dependency resolver 的固定复制集合仍停留在
  0.1.22，导致 `setup.bat --profile qq` 生成的可再生部署缺少该文件，ModuleManager 稳定返回
  `deployment_invalid`。该问题不涉及 `.env`、凭据、QQ 状态或包摘要。
- 已把该精确文件加入 `scripts/resolve_qq_module_runtime.py` 的 `SIDECAR_FILES`；未扩大为目录通配，
  也未允许 manifest、浏览器或用户提交路径/命令。合成安装夹具同步生成并断言该文件，目标部署树
  的精确文件集合也永久包含它。
- 定向 `unittest` 1/1 通过。随后只删除并重建精确的可再生成目录
  `server/runtime/module-dependencies/qq_bridge/0.1.24`；正式 setup 使用 Node 24.18.0 x64、
  npm 11.16.0 执行 `npm ci --ignore-scripts`，安装 1 个锁定公开依赖、审计 0 vulnerability。
  配置复核为 `configuration_ready=true`、`sidecar_readiness=ready`，模块正式启用但保持手动启动。
- 全程未读取或覆盖 QQ `.env`、AppID/Secret、消息、个人状态、模型、Voice Pack；未修改模块
  registry 的内容、未直接编辑不可变包，也未执行 Git 暂存、提交、推送或发布。
