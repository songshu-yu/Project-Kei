# Project Kei

Project Kei 是一个以《碧蓝档案》天童 Kei 为人格的 Windows 本地 AI 陪伴终端。当前可运行版本以 FastAPI 为核心，提供角色对话、GPT-SoVITS 语音、faster-whisper ASR、每日情报、QQ 官方机器人私聊和网页控制台。

> **公开测试说明**：本仓库以已验收源码提交 `31ab22ad4f3e16ae094a1ff885ec465d2a081d4b` 为基线，并包含公开前的隐私清理与安装兼容修正；公开仓库使用无历史快照，供测试人员进行干净安装、模块安装和兼容性验证。公开快照不包含开发者个人状态、缓存、密钥、Cookie、Token、模型权重或本机路径。发现问题时请提交可复现步骤和脱敏日志，切勿在 Issue、截图或日志中上传 `.env`、QQ Secret、LLM Key、B 站 Cookie 或个人数据。

本 README 是项目的公开、可移植运行手册：不包含机器绝对路径、密钥、Cookie、Token 或个人关注名单。实际工作目录和本机启动路径请见未提交的 `README.local.md`。

## 给接手 agent 的必读顺序

任何 agent 在检查、修改或执行 Git 操作前，必须依次阅读：

1. 本文件 `README.md`；
2. 根目录 [AGENTS.md](AGENTS.md)；
3. 若存在，根目录 `README.local.md`（本机路径和服务位置，已被 Git 忽略）；
4. 根目录 [TASKS.md](TASKS.md)；若请求属于其中某项，再读取对应 `tasks/PK-xxx-*.md`；
5. `git status --short` 与相关源码的实际内容。

不要根据旧对话、README 或文件名猜测当前状态。`AGENTS.md` 规定了变更、测试、密钥和 Git/README 同步规则。

## 当前实现状态

| 模块 | 当前状态 | 主要入口 |
|---|---|---|
| 主服务与控制台公共外壳 | 已实现；公共样式、请求、通知、折叠、功能中心和模块入口加载已从业务脚本中拆出 | `server/api.py`、`server/static/dashboard/`、`/dashboard` |
| 模块目录与项目任务体系 | 已实现；采用模块化单体、项目内任务总板和独立功能任务 | `TASKS.md`、`tasks/`、`GET /api/v1/modules` |
| 可安装模块生命周期 | 本地可信包、固定官方 GitHub/Gitee 双镜像目录、摘要校验、原子注册表、生命周期 API、重启装载与控制台模块中心已实现；20 个业务项已有确定性安装包候选，等待最终 PK-900 与 Release 发布 | `server/core/modules/`、`server/core/modules/official-catalog.json`、`GET /api/v1/modules`、`PK-010`、`PK-011`、`PK-100` |
| LLM 角色对话 | 已迁入可安装 conversation 模块；新旧文字与 history 接口共用同一 service | `server/features/conversation/`、`POST /api/v1/conversation`、`/chat/text-only` |
| 热切换模型方案 | 已迁入 conversation 模块；候选测试、非秘密 profile 原子保存和活动 client 切换共用同一流程 | `GET/PUT /api/v1/llm-profile`、控制台 legacy LLM 面板 |
| 语音公共契约与编排 | 已迁入可安装 voice 模块；新旧同步/流式接口共用 ASR → PK-200 → TTS service，TTS 缺失时明确文字降级 | `server/features/voice/`、`/api/v1/voice/*`、`/voice/*` |
| GPT-SoVITS TTS | PK-211 Engine Provider、官方固定来源描述、本机登记与显式受控获取已实现；共享实例以单一引擎会话串行完成 Pack 确认、权重切换和合成 | `server/features/voice/providers/gpt_sovits/` |
| Voice Pack | PK-212 已实现版本化 Schema、本机原子注册表与切换；PK-213 已实现可信 catalog、受限 HTTPS 获取、安全 ZIP、离线导入、确定性构建及根 CLI；经授权的 `kei@1.0.0` 由公共模块分发仓库提供规范 ZIP、摘要和 release manifest | `voice-pack.bat`、`voice-pack-build.bat`、`server/features/voice/voice_packs/`、`/api/v1/voice-packs/*` |
| faster-whisper ASR | 保留 8010 兼容适配 | `server/features/voice/providers/asr_http.py` |
| 每日情报 | 已迁入可安装 daily_briefing 模块；生产 composition 按已启用来源模块注册 Collector 1.0，并可在默认关闭的本机总/逐项开关下只读投影当天生活预报，不改写简报缓存 | `server/features/daily_briefing/`、`/api/v1/briefing/*`、兼容 `/briefing/today*` |
| 每日生活预报 | PK-240 已提供独立可安装候选；默认禁用联网，显式刷新后按本地日期缓存天气事实/生活建议，可选本地娱乐运势 | `server/features/life_forecast/`、`/api/v1/life-forecast/*` |
| 每日情报来源管理 | 已迁入 `intel_sources` registry；版本化增改删、原子本机配置和只读 Collector 快照共用同一 service，控制台使用版本化 API | `/api/v1/intel-sources`、兼容 `/dashboard/intel-sources` |
| QQ 官方机器人 bridge | 已收口为独立 Node sidecar；生活预报默认关闭，启用后固定菜单按钮显式刷新一次，四个完整关键词只读当天缓存，不增加定时推送或自动天气刷新 | `server/qq_bridge/`、`/api/v1/qq-control/*` |
| QQ 定时情报推送 | 缓存优先；版本化显式预生成、只读发送、逐用户/跨重启 at-most-once 状态 | `server/qq_bridge/src/daily_briefing_scheduler.mjs` |
| 生命维持提醒 | 合法时间窗/正间隔调度、逐槽位去重、受控生成失败的本地确定性兜底 | `server/qq_bridge/src/life_support_scheduler.mjs` |
| 好感度、长期记忆、斩妖除魔、健身、专注、日历 | 均已形成可安装 `in_process` 包候选；只有安装、启用并重启后才装配新旧 API 和动态面板，卸载保留各自既有个人状态 | `server/features/fitness/`、`server/features/affection_memory/`、`server/features/focus/`、`server/features/calendar/`、`server/features/demon_slayer/` |
| 树莓派实体、移动机器人、3D 外壳 | 规划中/独立推进 | `hardware/`、`pi_client/`、`client/` |

## 架构与服务端口

```text
浏览器控制台 ─┐
QQ 官方机器人 ─┼─> Project Kei API :8000
语音输入/输出 ─┘        ├─ faster-whisper ASR :8010
                           ├─ GPT-SoVITS TTS :9880
                           ├─ LLM API（当前可在控制台切换）
                           ├─ 每日情报采集、缓存、改写
                           └─ 个人系统与长期记忆

QQ bridge（独立 Node 进程）
  ├─ QQ Gateway / access token
  ├─ 白名单私聊转发至 API
  ├─ QQ Markdown 每日情报
  └─ 定时情报与生命维持提醒
```

| 服务 | 默认地址/端口 | 启动方式 |
|---|---|---|
| Project Kei API 与控制台 | `http://127.0.0.1:8000` | 根目录 `start.bat`（默认 Core） |
| 控制台 | `http://127.0.0.1:8000/dashboard` | 主服务启动后访问 |
| ASR | `http://127.0.0.1:8010` | 由主启动器管理 |
| GPT-SoVITS | `http://127.0.0.1:9880` | 由主启动器管理 |
| QQ bridge | 独立 Node 进程 | `server/qq_bridge/start_qq_bridge.bat` |

## 目录说明

```text
project-kei/
├── README.md                    # 本公开运行/交接手册
├── README.local.md              # 本机绝对路径（忽略，不提交）
├── AGENTS.md                    # 后续 agent 的强制协作规范
├── TASKS.md                     # 项目任务总板与状态入口
├── tasks/                       # 各功能的独立任务、接口与验收记录
├── docs/architecture/           # 模块边界和兼容迁移规范
├── server/
│   ├── api.py                   # FastAPI 主入口与控制台 API
│   ├── features/                # 模块化边界；conversation、affection_memory、voice、daily_briefing 等内置/可安装功能
│   ├── static/dashboard.html    # 网页控制台
│   ├── static/dashboard/        # 控制台公共 CSS、请求/通知、折叠、注册表与模块加载器
│   ├── core/                    # 公共兼容入口、模块管理与环境加载
│   ├── services/                # ASR、TTS、每日情报、来源配置
│   ├── systems/                 # 好感度、任务、健身、专注、日历
│   ├── intel/                   # 情报配置、采集器与汇总
│   ├── qq_bridge/               # 独立 QQ 官方机器人 Node bridge
│   ├── data/                    # 本地状态/缓存（多数忽略）
│   ├── tests/                   # 可直接运行的定向自检
│   └── start_all_services.bat   # 兼容入口，委托根启动器
├── pi_client/                   # 树莓派客户端相关代码
├── client/                      # 早期客户端/显示相关代码
├── hardware/                    # 硬件与外壳资料
└── vendor/                      # 外部参考资源；默认不提交、不重构
```

## Windows 安装与启动

下面是新电脑上的完整流程。支持 Windows 10/11 x64、Windows PowerShell 5.1
或 PowerShell 7.4+、Python `>=3.10,<3.14`；支持 3.10、3.11、3.12、3.13
x64，推荐 Python 3.11 x64。只有需要
QQ bridge 时才需要 Node.js 20、22、24 或 26 x64；推荐 Node 24 LTS。Node 20
仅保留旧环境兼容，新的 Windows 验证矩阵覆盖仍在支持期内的 22、24、26。

### 0. 先安装系统运行时

`.venv` 不能凭空安装 Python。它必须由电脑上已经存在的 Python 创建：

```text
系统 Python 3.10/3.11/3.12/3.13 x64
        ↓ setup.bat 自动创建
项目根目录 .venv
        ↓ setup.bat 自动安装
Project Kei 锁定的 Python 依赖
```

首次使用前：

1. 从 [Python 官方 Windows 下载页](https://www.python.org/downloads/windows/)
   安装 **Python 3.10、3.11、3.12 或 3.13 的 64 位版本**，推荐 3.11。
   Python 3.14 及更高版本当前不受支持。使用传统安装器时建议勾选
   `Add python.exe to PATH`，安装后关闭并重新打开 PowerShell。
2. 如果只使用 Core、控制台和文字对话，不需要安装 Node.js。如果要使用 QQ，
   从 [Node.js 官方下载页](https://nodejs.org/en/download)安装
   **Node 24 LTS x64**。
3. Git 只用于下载和更新仓库；通过 ZIP 得到完整项目时，普通安装不依赖 Git。
   Windows PowerShell 5.1 已随 Windows 提供，不要求另外安装 PowerShell 7。

打开一个新的 PowerShell，检查运行时：

```powershell
python --version
python -c "import struct; print(struct.calcsize('P') * 8)"

# 仅 QQ 用户需要
node --version
npm --version
```

Python 应显示 3.10、3.11、3.12 或 3.13，第二条命令应显示 `64`。如果
`python` 命令不存在，请重新打开 PowerShell，或重新安装 Python 并启用 PATH；
不要先手工创建 `.venv`。

### 1. 下载项目并打开根目录

下载 ZIP 后解压，或通过 Git clone 项目。进入能看到 `setup.bat`、`doctor.bat`
和 `start.bat` 的 `project-kei` 根目录。项目可以放在其他磁盘，路径可以包含
空格或中文。

在文件夹空白处按住 Shift 点击鼠标右键，选择“在此处打开 PowerShell 窗口”；
也可以在资源管理器地址栏输入 `powershell` 后回车。

### 2. 自动创建虚拟环境并安装 Core

可以在 PowerShell 中运行，也可以直接双击。所有面向用户的 BAT 都会在成功、
失败或长驻进程退出后显示结果并等待按键，因此错误信息不会一闪而过：

```powershell
.\setup.bat
```

默认 `core` 安装会自动完成：

1. 查找受支持的 x64 Python；
2. 在项目根目录创建 `.venv`；
3. 校验项目锁文件；
4. 在 `.venv` 中安装固定版本的 Core 依赖；
5. 检查必要包能否导入。

用户不需要运行 `python -m venv`、`pip install` 或激活 `.venv`。安装器不会
安装或替换系统 Python、Node、Git 或 PowerShell，也不会创建 `.env`、下载模型、
启动服务或读取个人状态。网络中断后修复网络并重新运行同一条命令即可；健康的
`.venv` 会被复用，不会被删除重建。

安装结束后执行只读诊断：

```powershell
.\doctor.bat
```

看到 Core 的 Python、lock、imports 等项目为 `[ok]` 后即可启动。

### 3. 启动 Core 和控制台

```powershell
.\start.bat
```

根启动器会作为本机 supervisor 持有 Core 子进程；Core 通过本地就绪检查后，
启动器会自动使用默认浏览器打开控制台。控制台的浏览器地址是：

```text
http://127.0.0.1:8000/dashboard
```

Core 固定只监听 `127.0.0.1:8000`，ASR 固定只监听 `127.0.0.1:8010`，不会
静默开放到局域网。如果浏览器没有自动打开，可手动使用上面的本机地址。CI、测试、
后台运行或不希望弹出浏览器时使用 `.\start.bat --no-browser`，也可设置
`PROJECT_KEI_NO_BROWSER=1`。

主 API 的全部 HTTP、静态控制台和 WebSocket 路由都先验证底层连接客户端：
只接受 IPv4 `127.0.0.0/8` 或 IPv6 `::1`，不信任 `Host`、`Origin`、
`X-Forwarded-For` 或 `Forwarded` 来判断客户端身份。浏览器跨域只允许
`http://127.0.0.1:8000`、`http://localhost:8000` 和
`http://[::1]:8000`；无 `Origin` 的本机 CLI、QQ sidecar 与 Provider 调用保持
兼容。本版本不提供 LAN 监听模式。

按启动窗口中的 `Ctrl+C` 停止 Core。再次使用时不需要重跑 setup，直接运行
`start.bat`；只有依赖或安装 profile 变化时才需要再次运行 setup。

控制台的“配置就绪情况”会显示 QQ、ASR 和 GPT-SoVITS 的进程状态。只有由当前
Project Kei 控制器显式启动并仍持有句柄的进程才显示可用的“关闭服务”按钮；点击后
还需二次确认。外部手工启动或来自旧 Core 的实例只显示“外部启动”，不会按 PID、
端口、路径或进程名强制终止。Core 本身仍通过启动窗口 `Ctrl+C` 停止，控制台只提供
下述受控重启，因为停止 Core 后当前网页也会立即失联。

控制台的服务重启接缝只在由根 `start.bat`/`scripts/start.ps1` 建立的 supervisor
下可用。它固定重启 Core runtime，不接受浏览器提供命令、路径、PID、host 或
port，也不会在重启时新增启动 `voice`、`qq` 或 `all` profile 的外部进程。
已启用的 in-process 模块和由 Core 生命周期管理的已启用模块 sidecar 会随 Core
按既有模块契约重新装配；由用户显式 profile 启动的 ASR、GPT-SoVITS 和兼容 QQ
窗口不在重启范围内。直接运行兼容 `--only api` 入口时没有 supervisor，控制台必须
显示“重启不可用”，不能假报成功。

供控制台接入的固定接口为
`POST /api/v1/dashboard/service/restart` 和
`GET /api/v1/dashboard/service/restart/status`。两者都只接受真实 loopback 客户端；
浏览器式 status GET 不携带 Origin 时可读，若携带则只能是上面三种精确同源
Origin。POST 始终必须携带精确可信 Origin，请求体只能是
`{"confirmation":"restart-project-kei-core"}`。首次请求返回 HTTP 202 与
`accepted`，并发或重复点击复用同一 `request_id`；随后可能短暂断线，控制台按
`retry_after_ms`（当前 500 ms）重连并轮询，直到相同 request id 变为 `running`
或 `failed`。无 supervisor 固定返回 HTTP 503/`unavailable`。错误状态不包含
进程号、本机路径、配置、秘密或上游响应。

启动 profile 与进程范围如下；安装 profile 和启动 profile 名称相近，但安装命令
只安装依赖，启动命令才创建进程：

| 启动命令 | 启动范围 |
|---|---|
| `.\start.bat` | 默认只启动 Core API 与控制台 |
| `.\start.bat --profile voice` | Core + 已配置的 ASR + 已登记的 GPT-SoVITS |
| `.\start.bat --profile qq` | Core + 已配置的 QQ bridge |
| `.\start.bat --profile all` | Core + ASR + GPT-SoVITS + QQ bridge |
| `server\start_all_services.bat` | `--profile all` 的兼容一键入口 |

Core 已单独启动时，控制台会在未运行的 ASR 与 GPT-SoVITS 状态卡下显示“启动服务”，
以隐藏窗口的后台模式启动日常服务；启动后，同一位置变为“关闭服务”。语音模块内
另保留“调试启动……（打开窗口）”，供需要查看 ASR/GPT-SoVITS 实时日志的维护者使用。
两类语音按钮只调用本机同源的固定启动器；不会接受路径或命令参数，不会安装依赖、
下载模型、写入配置或启动重复进程。顶部只能关闭由当前 Core 启动并持有句柄的实例；
从模块调试窗口或旧 Core 启动的外部实例只读显示，用户在其窗口按 `Ctrl+C` 关闭。
缺少 ASR 模型或 GPT-SoVITS 本机登记时，按钮保持禁用并显示需要完成的准备事项。
QQ 继续使用独立的模块启动按钮，不随 Core 自动启动。

“配置就绪情况”和已启用的语音模块提供两个受控本机目录入口：ASR 的“选择模型
目录”只打开操作系统目录选择器并校验用户明确选中的模型目录；GPT-SoVITS 的
“选择已有引擎目录”只校验已有安装的固定入口并登记脱敏状态。浏览器不会提交路径、
URL 或命令，响应最多显示清洗后的末级目录名称，不显示绝对路径；取消选择不写配置，
验证失败保留原配置。这两个入口不会自动扫描磁盘、下载模型/引擎、安装依赖或执行
所选目录中的脚本。GPT-SoVITS 目录登记接口由 Core 固定装配，即使尚未登记引擎也
不会返回 404；`gpt_sovits_engine_provider` 模块仍独立负责 Provider/sidecar 生命周期，
安装模块不等于安装或登记外部引擎。

### 4. 按需安装可选功能

| profile | 命令 | 安装内容 |
|---|---|---|
| `core` | `.\setup.bat` | 默认；Core Python 锁 |
| `voice` | `.\setup.bat --profile voice` | Core + 公共 ASR 锁 + hash-locked Windows Silk 媒体 wheel；不下载模型、GPT-SoVITS 或 Voice Pack |
| `qq` | `.\setup.bat --profile qq` | Core + Node lock 对应的 `npm ci` |
| `full` | `.\setup.bat --profile full` | Core + voice + qq 的公开依赖 |
| `dev` | `.\setup.bat --profile dev` | Core + 开发/测试锁；不隐式包含 voice 或 qq |

例如，QQ 用户先安装 Node 22，再运行：

```powershell
.\setup.bat --profile qq
.\doctor.bat --profile qq
```

语音用户安装公开 ASR 与语音媒体依赖：

```powershell
.\setup.bat --profile voice
.\doctor.bat --profile voice
```

`voice`/`full` 只接受 `silk-python==0.2.8`、`cffi==1.17.1` 和
`pycparser==2.22` 对应 Python 3.10–3.13 CPython x64 Windows wheel 的项目冻结
SHA-256，不会回退源码包、其他平台 wheel 或未锁版本。
doctor 只核对版本、导入和 encoder capability，不编码音频。缺少该依赖时语音媒体
明确 unavailable，但 Core 仍可安装和启动。`voice` 也不会下载 ASR 模型、
GPT-SoVITS 或 Voice Pack；这些资产仍需按后文对应说明显式准备。`qq` 不会创建或读取 QQ `.env`。锁和重现方式见
[Windows 安装、依赖锁与启动架构](docs/architecture/windows-install.md)。

ASR 模型不会随 `full` 安装下载。voice/all 启动器优先使用当前 PowerShell 或
本机 `server\.env` 中的 `ASR_MODEL_PATH`；未配置时，为兼容既有安装，只检查
项目内固定的 `server\models\asr\medium`，其次检查
`server\models\asr\small`。该检查不递归扫描磁盘、不下载模型、不输出实际
路径。`ASR_DEVICE`、`ASR_COMPUTE_TYPE` 仍可按需设置；启动器只从 `.env`
导入这三个非秘密字段，其他 Key、Cookie、Token 不会由启动器导入。

PK-213 已提供根目录 `voice-pack.bat`。权利持有人已明确授权 `kei@1.0.0` 的完整
Voice Pack 按包内非商用许可公开下载和原样再分发；规范 ZIP、SHA-256 sidecar 与
release manifest 发布在公共 `songshu-yu/Project-Kei-Modules` 仓库的固定 Release。
ZIP 为 303635280 字节，SHA-256 为
`bc679c8ab97d5be44d959506c841e642cda19f8215ba3aede07e18d91807c83a`。
用户可通过受信目录在线安装，也可先用 GitHub 网页或 `gh` 下载 ZIP，再执行离线导入：

```powershell
.\voice-pack.bat list
.\voice-pack.bat import <明确的本机ZIP或目录> --confirm <id@version> --sha256 <ZIP摘要>
.\voice-pack.bat verify kei@1.0.0
.\voice-pack.bat select kei@1.0.0
```

`list/status/verify` 不联网；只有 catalog 已收录版本的显式 `install` 可以访问其
固定 HTTPS 来源，并要求再次精确确认 `id@version`。本机目录导入标记为
`local_unpublished`；本机 ZIP 必须匹配 catalog，或由用户同时提供精确
`id@version` 与预期 SHA-256。源 ZIP/目录不会被删除或移动。Pack 安装与
GPT-SoVITS Engine 可用性分开报告，工具不会自动获取约 8 GB Engine、CUDA、
驱动或解包器。

重复安装同一 `id@version` 只有在 PK-212 锁内重新验证已安装 Pack，并证明其
规范化 manifest 与全部声明资产摘要和可信 Release 完全一致时才返回幂等成功；
内容不同或无法证明等价会稳定报告冲突，且不会改 Registry、runtime、缓存或旧
活动 Pack。经授权使用 `voice-pack-build.bat` 构建时，输出 ZIP 及 sidecar 必须
位于显式 source root 外；source/输出父链中的 symlink、hardlink、Windows
junction 或 reparse point 都会在读取资产内容前被拒绝。

### 5. 常见安装问题

| 现象 | 处理方式 |
|---|---|
| 提示找不到受支持的 Python | 从 python.org 安装 Python 3.10、3.11、3.12 或 3.13 x64（推荐 3.11），重新打开 PowerShell，再运行 `python --version` |
| Python 显示 32 位 | 卸载 32 位版本并安装 Windows x64 版本 |
| `dependency_install_failed` | 检查网络和公开 Python 包索引，随后重新运行同一 setup 命令 |
| `voice_media_install_failed` | 只重跑 `setup.bat --profile voice`；检查公开索引/网络与 Python x64 版本，不要改用源码包或未锁版本 |
| QQ 提示找不到 Node/npm | 安装 Node 24 LTS x64，重新打开 PowerShell，再运行 `node --version` |
| `npm_ci_failed` | 检查网络；不要改用 `npm install` 或删除 lockfile |
| `lock_checksum_mismatch` | 项目锁文件损坏或被修改，应从可信项目副本恢复 |
| 8000 端口已占用 | 回到原 Project Kei 窗口按 `Ctrl+C`；不要强制结束不明进程 |
| `.venv` 已存在但损坏或版本不兼容 | 安装器会失败关闭而不会擅自删除；先确认它不是用户仍需保留的环境，再手工移走后重跑 setup |

`doctor.bat` 严格只读，不安装、不写配置、不下载、不启动业务进程，也不连接业务
服务。遇到问题时可把它输出的固定错误类别提供给维护者，但不要发送 `.env`、
Token、Cookie、个人状态或本机模型路径。

所有 9 个受跟踪用户 BAT 默认在结束时保留窗口。CI、测试、计划任务或
BAT→BAT 内部委托必须显式设置 `PROJECT_KEI_NO_PAUSE=1`；该变量只关闭末尾等待，
不改变参数、退出码、安装、诊断或启动语义。普通用户无需设置它。

### 6. 配置本地环境

不要提交本地配置。主服务读取 `server/.env`，QQ bridge 读取 `server/qq_bridge/.env`。首次部署时，分别参考同目录的 `.env.example`。

QQ 公开依赖只能由 `setup.bat --profile qq` 或 `setup.bat --profile full` 使用现有 `package-lock.json` 和 `npm ci` 安装。QQ App Secret、LLM API Key、B 站 Cookie、QQ access token 都只能保留在本地 `.env`，绝不能写入 Git、README、Issue、日志或聊天内容。

### 7. 启动与停止

双击或在 PowerShell 中运行：

```powershell
.\start.bat
```

默认只启动 Core API 8000。语音、QQ 或所有已安装可选组件必须显式请求：

```powershell
.\start.bat --profile voice
.\start.bat --profile qq
.\start.bat --profile all
```

完成一次 `.\setup.bat --profile full` 后，也可以直接双击兼容入口
`server\start_all_services.bat`，它等价于 `start.bat --profile all`。启动器会先
确认 Core 的 Python 依赖和 8000 端口可用，再分别启动已配置的 GPT-SoVITS、
ASR 和 QQ，最后在当前窗口启动 Core 并打开控制台。Core 预检失败时不会先留下
GPT-SoVITS、ASR 或 QQ 子进程；依赖不完整时会提示重新运行 `setup.bat --profile
full`。各组件仍使用各自的端口、进程和停止窗口。

`start` 只做有限只读 preflight，不运行 pip/npm、不修改 `.env`、不下载资产。若
选中的 `.venv` 已创建但缺少 FastAPI/uvicorn，启动器会在创建服务进程前返回
`dependencies are incomplete`，明确要求重新运行 setup 和 doctor，不再直接
显示裸 `No module named uvicorn`。可选组件缺失或启动失败只产生分项警告，
Core 仍继续启动；8000 已被其他进程占用时会明确失败且不会替换或终止端口所有者。
按对应控制台窗口中的 `Ctrl+C` 停止本次前台进程。既有 `server/start_*.bat`
和 QQ bridge BAT 名称继续可用，均委托同一运行时解析逻辑。

GPT-SoVITS 启动器不再包含某个角色的权重、参考音频或公开绝对安装路径。它只读取项目固定的 `engine.json` 和被忽略的 `server/data/gpt_sovits_engine.local.json`，检查固定 `runtime/python.exe`、`api.py` 后在用户显式启动时监听 `127.0.0.1:9880`；缺少登记、入口文件或路径越界时会明确失败，不会下载、装依赖、扫描源码或伪装成功。已有安装可直接登记，不必重新下载；实际路径与状态只见 `README.local.md` 和本机配置。

角色权重、参考音频、提示文本和语言不再从主业务代码或 `TTS_DEFAULT_*` 环境变量选择。主 API 只解析被忽略的 `server/data/voice_pack_registry.local.json` 中的活动 Voice Pack ID，并把其已校验的不透明句柄交给 9880 Provider；修改 Voice Pack 代码或注册表装配后需要重启 API，使用选择接口切换已登记 Pack 则立即生效。

若修改了 `server/api.py`、`server/features/conversation/`、`server/features/affection_memory/`、`server/features/fitness/`、`server/features/voice/`、`server/services/`、`server/intel/`、`server/static/dashboard.html` 或 `server/static/dashboard/`，必须重启 API 才能加载新代码。由根启动器运行时可使用上述受控 supervisor 接缝；其他启动方式应关闭原 API 窗口后重新启动。首次启动发现 `8000` 已被占用时仍会明确失败，不会按端口或进程名终止所有者。通过控制台或 `PUT /api/v1/llm-profile` 成功切换模型方案本身立即生效，不需要重启。

### 8. 兼容 QQ bridge 入口

另开一个 PowerShell 窗口：

```powershell
cd server\qq_bridge
.\start_qq_bridge.bat
```

仅修改 API、控制台或每日情报采集代码时通常不需要重启 bridge；修改 `server/qq_bridge/src/`、bridge `.env` 或其依赖后才需要重启它。

API 已运行时，控制台最前面的“QQ 功能启动”卡片会使用 `server/static/assets/qq-launch.png` 作为大图按钮，点击图片即可启动 QQ bridge。该按钮只在真实 loopback 与受信同源 Origin 下可用，会先确认固定 `start_qq_bridge.bat`、bridge `.env`、Node 和 `node_modules/ws` 已存在，并检查对应 Node 子进程；并发或重复点击不会启动多个 bridge。就绪后它会打开一个新的 QQ bridge 控制台窗口。BAT 与网页都不会运行包管理器、创建/覆盖 `.env`、打开编辑器或读取密钥；缺失条件只显示 `setup.bat --profile qq` 和人工配置提示。

QQ 模块卡提供本机 AppID/Secret 配置表单。状态读取只返回是否已配置和脱敏后的
AppID；Secret 永不回显，也不会写入浏览器存储。只有点击“保存配置”才把本次填写值
发送给本机 Core；留空字段会按界面提示保留既有值。保存结果若提示需要重启，且
bridge 已在运行，请先在它自己的本机窗口中正常关闭，再回到控制台点击现有“启动”
按钮；控制台没有 stop API，不会伪装远程停止或静默重启 QQ。

## 控制台使用

所有功能区都支持点击标题展开/收起；浏览器使用
`project-kei.dashboard.panel-open.v1` 保存面板的布尔展开状态，并使用
`project-kei.dashboard.theme.v1` 保存 `cloud/sakura/moon` 三档纯界面主题。
“云朵白”为首次访问默认值，另可选择“樱花粉”和“月夜蓝”；主题初始化、
切换和刷新恢复都只操作当前页面与 `localStorage`，不会调用 API、采集网络、
模块生命周期或业务写接口。浏览器不会保存密钥、来源名单、模块配置或业务缓存。
首次访问时各功能以三列小组件网格排列；收起卡只显示小图与标题，点击标题后该
组件占满整行；展开卡采用真正的左右详情布局，角色图最大为 280×350（4:5），
右侧依次显示标题、状态/刷新/设置操作坞、设置面板和完整原有功能，不再把正文排在
图片下方留下大片空白。图片统一使用
`object-fit: contain`，不裁切、不放大位移；窄屏自动改为单列，角色图缩为最大
260×325 并居中，标题与完整详情移到下方。已有布尔折叠记录继续恢复；浏览器存储不可用时会安全
回退到云朵白与默认收起状态，无 JavaScript 时页面骨架和全部内容仍可读。
静态 legacy 面板与 `#dashboard-module-mounts` 中后加载的可安装模块使用同一折叠
状态机；收起卡明确显示“展开详情”，展开卡显示“收起详情”。QQ 与通用主组件
统一使用圆角矩形小图，桌面为 64px、窄屏为 56px；B 站次级参数头像仍保持自己的
独立圆形样式。
控制台 HTML 与 `/dashboard/static/*` 公共资源返回 `Cache-Control: no-store`；
HTML 引用和公共 ES module 内部依赖使用同一版本标记，避免普通刷新继续复用旧版
折叠脚本或样式。更新到包含该缓存策略的版本后需重启一次主 API，此后直接刷新
`/dashboard` 即可加载当前公共外壳。

“配置就绪情况”本身也是可独立展开/收起的公共面板。动态区域通常只装载已启用
模块；唯一例外是已经受信安装、处于 `needs_configuration` 的 `sidecar`，它可以
装载自己的配置/显式启动面板，方便用户补齐本机条件，但这不会启用或自动启动
sidecar，也不会放开其业务后端。QQ 面板内部把“QQ 功能启动”“每日情报定时推送”
和“生命维持系统”分为三个独立功能卡；好感度系统与长期记忆也显示为两张独立功能卡，
分别保留自己的图片、设置和折叠入口。
保存定时设置不等于立即生成或发送，QQ、模型、Collector 和语音服务均不会因打开、
折叠或刷新控制台而自动运行。

公共控制台卡头采用可选的角色头像、模块名称、单行说明、状态胶囊、现有主动作和
折叠入口。尚无素材的模块显示“添加图片”空槽，可选择 8MB 内 PNG/JPG/WebP；图片
先在本页预览，再上传到本机 Project Kei 的 Git 忽略 UI 素材目录，刷新、换浏览器
或重启 API 后仍保留。“恢复默认”会删除上传素材并回到仓库默认图/空槽。上传接口
校验组件 ID、Content-Type、文件签名、大小、本机客户端与可信控制台 Origin，不
返回服务端绝对路径。UI 素材目录和图片响应均使用 `Cache-Control: no-store`，
前端目录请求同样禁用 HTTP 缓存，并以素材更新时间区分图片 URL，确保上传后刷新
不会退回旧目录。升级到包含该修复的版本后需重启一次主 API，使目录响应头生效。
仓库默认素材仍可通过公共卡头的
`data-panel-avatar`/`data-panel-summary` 注入，不需要复制折叠逻辑。标题按钮只
控制本地展开状态，展开后显示原有完整说明与功能内容。QQ 启动卡
继续把本地 `qq-launch.png` 作为 64px（窄屏 56px）单向启动按钮，并在标题中注明
“单击头像可以启动 QQ”；状态只展示 `running/ready/failed` 等已有值。后端没有
stop API，因此控制台
不会伪装成双向启停开关。B 站参数区继续使用 42px（窄屏 36px）本地思考头像、
原独立 `<details>` 和 PK-130 状态/操作，公共样式不会改变凭据、候选验证或显式
采集契约。
每个主功能卡和后加载的动态模块卡都会获得独立“设置”按钮。点击设置只会展开
当前卡片并汇总其中已有的带标签表单项；点击设置项只把焦点定位到原控件，不复制
字段、不改变值、不自动保存，也不调用 API。当前示例包括 LLM 方案、生命维持
时间、每日推送时间、关注对象管理和专注启动参数。没有独立设置的卡显示占位说明；
QQ 只说明现有头像启动和状态刷新，并明确没有 stop 接口。未来模块可使用标准
`<label>` 自动接入，也可通过 `data-setting-label` 或模块根
`data-panel-settings` 补充设置描述。每张卡的设置面板都包含“设置本机图片”和
“恢复默认”；前者保存当前安装实例的自定义覆盖，不会把普通用户上传提升为项目
发行默认素材，后者删除覆盖并回到仓库默认图/空槽。它们只调用 PK-100 自有的
`/api/v1/dashboard/ui-assets`，不写
localStorage/IndexedDB，也不调用业务接口。QQ 只替换按钮内图片，单击头像启动 QQ
的原行为不变。

PK-100 同时是控制台组件的统一 UI 注册层。每个 legacy 或可安装组件使用稳定且
唯一的 `panel_id`，并声明标题、单行说明、仓库默认图片和可选设置入口；组件更新
时同步这份展示元数据与模块目录即可。用户图片统一由 PK-100 通用 UI 素材接口按
`panel_id` 保存，不需要、也不允许为每个业务模块再增加头像 API。业务功能、状态
和操作仍由各模块自己的接口与任务所有。

仓库随附的 16 张已确认组件/状态 PNG 与 QQ 启动图均作为只读默认素材使用；情报
来源聚合卡默认使用 `intel-sources.png`，语音聚合卡默认使用
`voice-pack.png`，配置就绪情况使用 `configuration.png`；好感度、长期记忆、定时推送和生命维持继续各用自己的图片。
这些默认映射只影响展示，不把聚合卡变成新的业务模块。用户仍可在任一卡的“设置”
中显式上传本机图片或点击“恢复默认”；本机覆盖保存在 Git 忽略目录，不进入模块
ZIP、GitHub Release 或其他用户的安装。

顶部服务状态卡另外共享两类 PK-100 状态视觉槽：`service-status-normal` 对应
“正常”，`service-status-attention` 对应“需要处理”。卡片仍只消费
`GET /dashboard/status` 的既有布尔结果，图片不会参与或改变健康判断。点击 56px
圆角状态图可展开“设置本机图片/恢复默认”；同一状态的服务共用一张图片，上传仍
复用 UI 素材接口并只写本机外观目录。没有自定义或项目默认图时显示高对比的
勾号/感叹号占位，窄屏缩为 50px，菜单和卡片不得产生水平滚动。

页面会通过只读 `GET /api/v1/modules` 显示功能中心，并且只加载 `enabled === true` 且声明了 `dashboard_entrypoint` 的同源模块入口。入口采用 ES module，必须导出 `mount(context)`，可选导出 `unmount()`；公共外壳只向模块提供自己的 DOM 根节点、只读目录快照、受 API 命名空间约束的请求函数和统一通知。单个入口 404、超时或挂载异常只会显示在该模块区域，不阻止其他模块继续工作。模块中心提供显式刷新官方目录、安装、启用、停用、更新、回滚与卸载操作；所有写操作都必须由用户点击触发，启停或卸载后按返回的 `restart_required` 提示重启。清除模块数据仍是独立危险操作，要求精确模块名二次确认，不与卸载合并。

功能中心的最近操作读取生命周期目录统一返回的 `last_operation.action/status`；模块加载错误中的长 URL 会在窄屏内换行，避免单个失败入口撑破移动端布局。

## 项目任务与模块协作

项目采用“总控任务 + 独立功能任务”的协作方式。根目录 [TASKS.md](TASKS.md) 是唯一任务总板，`tasks/` 中每个 `PK-xxx` 文件负责一个功能边界。新建 Codex 对话时，应在对话名称和首条消息中写明任务 ID，并只推进该任务；跨模块接口变化先交给 `PK-000` 总控确认。

任务状态依次为“待开始 → 进行中 → 待集成 → 已完成”。功能对话负责实现和定向测试，总控负责接口决策，`PK-900` 负责跨模块集成与发布门禁。完整代码边界见 [模块化单体规范](docs/architecture/modular-monolith.md)；按需安装的 manifest、状态、依赖、启停、升级、回滚和卸载规则见 [可安装模块生命周期规范](docs/architecture/installable-modules.md)。

每个任务进入“待集成”或“已完成”前，都必须完成任务文件中的八项文档门禁：任务记录、任务总板、公开 README、模块目录、架构/专项说明、本机 README、agent 规则和验证记录。适用项更新对应文件，不适用项写明理由；不要求把同一功能全文复制到所有文件。可在根目录运行 `.\scripts\python.ps1 ..\scripts\check_task_docs.py` 自动检查。

当前不把所有功能拆成独立进程。Project Kei API 保持模块化单体，QQ bridge、ASR 和 GPT-SoVITS 继续作为已有独立进程。新业务接口优先使用 `/api/v1/<module>`；现有 `/dashboard/*`、`/demon/*` 等接口在逐模块迁移期间保持兼容。

Core 固定只保留模块管理、官方目录和控制台公共外壳。conversation、个人工具、
情报来源与聚合、语音、Voice Pack 工具和 QQ bridge 共 20 项已经形成确定性安装包。
官方分发以 GitHub `songshu-yu/Project-Kei-Modules` 为主仓库，并可将同一批不可变 ZIP
同步到 Gitee `songshuyu957/Project-Kei-Modules` 镜像。源码仓库继续维护模块实现和构建器；
GitHub 以批次 Release 承载附件，Gitee 以固定 `packages/<release_tag>/<asset_name>` 路径
保存逐字节相同的附件。两端共用同一 Catalog、精确大小、ZIP SHA-256 和 manifest
SHA-256，不允许镜像自行重打包。旧 Release 暂时保留为兼容入口。

当前目录中的每个附件都保留模块 ID、SemVer、精确大小和 SHA-256。公共目录支持匿名
固定 URL；控制台只在用户显式刷新或确认安装时联网。下载来源可选择“自动（推荐）”、
“仅 GitHub”或“仅 Gitee”。自动模式先尝试 GitHub，只在连接失败、超时或明确可重试的
服务端故障时切换 Gitee；摘要、大小、manifest、重定向或其他安全校验失败时立即停止，
不会借镜像绕过校验。来源选择只保存在浏览器 `localStorage`，不写业务配置。

测试人员也可在项目根目录把 20 个模块包下载到系统临时目录；脚本会按照当前受版本
控制的 Catalog 逐项核对 SHA-256。公开仓库无需 GitHub Token：

```powershell
$downloadRoot = Join-Path $env:TEMP "project-kei-private-module-releases"
New-Item -ItemType Directory -Force -Path $downloadRoot | Out-Null
$catalog = Get-Content .\server\core\modules\official-catalog.json -Raw | ConvertFrom-Json
foreach ($module in $catalog.modules) {
  gh release download $module.release_tag --repo songshu-yu/Project-Kei-Modules `
    --pattern $module.asset_name --dir $downloadRoot --clobber
  $asset = Join-Path $downloadRoot $module.asset_name
  $actual = (Get-FileHash -LiteralPath $asset -Algorithm SHA256).Hash.ToLowerInvariant()
  if ($actual -ne $module.package_sha256) { throw "摘要不匹配：$($module.asset_name)" }
}
```

启动 Core 后，测试人员可以直接打开控制台的“模块管理 → 高级 / 离线安装”，
选择已下载的 ZIP，再点击“上传并安装”。模块 ID 默认由 Core 从已验证的包内
manifest 自动识别；“预期模块 ID”只是可选的高级核对项，不是安装必填项，也不会
从文件名推断。连续选择新 ZIP 会清除旧的自动 ID；若当前 ID 是用户手工填写，页面
会明确询问保留手工 ID、改用新包 manifest 自动识别或取消换包。选择文件只在浏览器
本机计算 SHA-256，不联网、不安装；显式点击后才把 ZIP 发送给本机 Core。Core
限制包为 64 MiB，重新计算摘要、读取包内 manifest 的实际模块 ID，并复用正式
ModuleManager 的路径穿越、依赖、冲突和原子安装校验。页面不接受服务器路径、任意
网址、GitHub Token 或 Cookie。

维护者自动化仍可使用旧的本机路径接口；例如安装 focus：

```powershell
$asset = Join-Path $downloadRoot "focus-1.1.1.zip"
$body = @{
  package_path = (Resolve-Path -LiteralPath $asset).Path
  expected_sha256 = (Get-FileHash -LiteralPath $asset -Algorithm SHA256).Hash.ToLowerInvariant()
} | ConvertTo-Json
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/api/v1/modules/focus/install `
  -ContentType "application/json" -Body $body
```

安装结果默认为停用；再从控制台显式启用并按提示重启。测试不要求把 ZIP
复制进仓库，也不要提交临时下载目录、`.env`、个人状态或任何 GitHub 凭证。

Voice Pack 同样可先用 `gh` 下载，再离线导入：

```powershell
gh release download voice-pack-kei-v1.0.0 --pattern "kei-voice-pack-1.0.0.zip" `
  --dir $downloadRoot --clobber
$voiceZip = Join-Path $downloadRoot "kei-voice-pack-1.0.0.zip"
$voiceSha = (Get-FileHash -LiteralPath $voiceZip -Algorithm SHA256).Hash.ToLowerInvariant()
.\voice-pack.bat import $voiceZip --confirm kei@1.0.0 --sha256 $voiceSha
```

普通用户和测试人员的流程是：

1. clone 仓库并运行 `setup.bat`，随后运行 `start.bat`；
2. 打开 `http://127.0.0.1:8000/dashboard` 的模块中心；
3. 可选择自动/GitHub/Gitee 后显式点击“刷新官方目录”并确认在线安装；也可用 `gh release download` 下载
   ZIP，再在“高级 / 离线安装”中选择本地 ZIP；
4. 安装后显式启用；页面提示需要重启时，关闭并重新运行 `start.bat`；
5. 停用或卸载后同样重启。卸载默认只移除程序包，保留个人状态。

页面加载、查看本地目录、展开卡片、切换主题和切换下载来源都不联网。只有显式刷新
官方目录或确认安装/更新时只访问固定 GitHub `songshu-yu/Project-Kei-Modules` 或
Gitee `songshuyu957/Project-Kei-Modules` 镜像；浏览器不能提交任意仓库、URL、
Token、Cookie、代理或远程脚本。模块与本地
程序的完整交互标准见
[模块包交互与发布契约](docs/architecture/module-package-contract.md)。

### 本地可安装模块基础

- 开发者仍可导入当前电脑上的可信目录或 ZIP，并同时提供预先计算的 SHA-256。
  普通用户使用固定官方目录；管理器只在显式动作中从固定 GitHub Release 或 Gitee
  镜像路径下载目录声明的同一不可变资产，并始终按 Catalog 的大小与摘要复核。
- 控制台离线导入不暴露服务器文件路径：浏览器计算 SHA-256 后，以
  `application/zip` 原始请求体上传到仅本机接口；Core 流式写入自动清理的系统临时
  目录，摘要和 manifest ID 通过后才进入既有原子安装流程。安装后仍为停用状态。
- 正式 manifest Schema 位于 `server/core/modules/manifest.schema.json`。包内入口、控制台资源、依赖、冲突、Core 版本、权限和命名空间会在写入正式版本目录前校验。
- Core 保留身份和 namespace 由 `server/core/modules/contracts.py` 统一定义。本地可选包不能使用 `catalog`、`module_manager`、`dashboard`，也不能声明 `/api/v1/modules`、`/api/v1/dashboard` 或其子 namespace；拒绝不会创建正式版本目录或注册表记录。
- 安装产物位于忽略的 `server/runtime/modules/<module_id>/<version>/`，注册表位于忽略的 `server/data/module_registry.json`，新模块数据位于 `server/data/modules/<data_namespace>/`；三者彼此分离。
- `in_process` 模块在 API 重启时调用包内公开的 `module.register(app)`；启用、停用、升级或回滚可能返回需要重启。第一版不承诺运行时移除已经注册的 FastAPI 路由。
- `sidecar` manifest 只能引用 Core 代码显式注册的适配器，不能携带任意 PowerShell、BAT 或 Python 安装命令；适配器负责启动、停止和本地健康检查。
- 卸载只移除程序版本并保留模块数据。清除数据是独立接口，确认文字必须与模块 ID 完全一致。

### Focus 可安装模块

focus 包源码和构建器位于 `server/features/focus/`。在根目录生成一个新的本地 ZIP（输出路径不能已存在）：

```powershell
.\scripts\python.ps1 -m features.focus.package_builder "<output-directory>\focus-1.1.1.zip"
```

构建器会输出包路径和 SHA-256。开发者可以将两者作为 `POST /api/v1/modules/focus/install` 的 `package_path`、`expected_sha256` 提交；普通用户则在模块中心刷新固定官方目录后点击安装。安装结果为 `installed_disabled`，随后显式启用并重启 API，才会装配 `/api/v1/focus/*`、兼容 `/focus/*` 和控制台动态面板。已有旧版本安装需要用 1.1.1 ZIP 显式更新并重启 API，才会同时获得受控鼓励接口与完整卸载清理；系统不会自动升级、启用或重启模块。

停用使用 `POST /api/v1/modules/focus/disable`，卸载使用 `DELETE /api/v1/modules/focus`；两者之后都要重启 API，新的进程才不再装配路由和面板。升级使用新版本 ZIP 调用 `POST /api/v1/modules/focus/update`，也需要重启。第一版不会从已经运行的 FastAPI 进程热移除路由。

卸载只删除 `server/runtime/modules/focus/` 下的程序版本，保留历史计时状态，重新安装并启用后继续关联。PK-180 不移动或合并既有 `server/systems/data/focus_timer.json`、`server/data/focus_timer.json`；模块管理器的 `purge-data` 只处理新的 `server/data/modules/focus/` namespace，不删除这些历史文件。用户明确需要清空当前专注记录时，使用 focus 面板的二次确认重置或 `POST /api/v1/focus/reset`，不要把卸载当作清数据。

focus 面板的重置必须连续两次点击确认；成功后按钮会恢复可用，重置不会停用或卸载模块，也不会调用模块管理器的 `purge-data`。

### Calendar 可安装模块

日历备忘与修炼记录位于 `server/features/calendar/` 的 models、repository、service、router 分层，并以可安装 `in_process` 包装配。安装、启用并重启后，版本化接口位于 `/api/v1/calendar/*`，原 `/calendar/*` 路径和动态面板继续兼容；语音只通过公开 calendar summary Provider 读取摘要，模块缺失时稳定降级。

版本化 `POST /api/v1/calendar/reset` 必须提交 `{"confirmation":"calendar"}`。旧 `POST /calendar/reset` 暂时保留兼容，但控制台不提供 reset 控件；两者都会清除全部事件、技能累计和练习日志，只能在用户明确操作或显式临时测试状态上调用。当前 legacy 面板只支持添加事件、记录练习和查询，不提供编辑、单条删除、同步或提醒。

### Demon Slayer 可安装模块

斩妖除魔位于 `server/features/demon_slayer/` 的 models、repository、service、router 分层，并以可安装 `in_process` 包装配。安装、启用并重启后，版本化接口位于 `/api/v1/demon-slayer/*`，原 `/demon/*` 路径继续兼容并调用同一 service；`server/systems/demon_slayer.py` 只保留旧 Python 导入门面。

目标周期与层级固定为日目标/小妖、周目标/大妖、月目标/大大妖、年目标/妖王。周期和妖怪种类都可自动判断或显式选择；`recurring` 在每个对应周期重复，`once` 只在 `target_date` 所属周期出现。目标可新增、查看、编辑和单条软删除，编辑保持 ID，删除与重复删除只停止之后的追踪，不删除历史打卡、积分、奖励、兑换或复盘依据。旧目标缺少 `repeat_mode` 时按周期重复兼容。

`GET /api/v1/demon-slayer/status?date=YYYY-MM-DD` 与兼容 `/demon/status` 继续稳定返回 `daily_goals/weekly_goals/monthly_goals/yearly_goals`。每个目标新增 `active_since`、`active_days`、`current_streak`、`longest_streak`、`streak_unit`，并保留 `completed`：常驻目标有可信创建/重新启用证据时从该日按自然日计数；旧目标若没有目标/全局创建日、合法历史打卡或重新启用日，则两个启用字段稳定返回 `null`，不会把查询日伪装成历史起点。临时目标的启用天数为 `null`、连续值为 `0`；连续记录分别按自然日、周一自然周、自然月和自然年计算。当前尚未结束且未完成的周期不会提前打断上一段，只有已闭合周期缺少成功打卡才重置；停用区间、创建前周期和未来记录不进入统计，未来查询也只使用截至本机今日的事实，重新启用重开当前连续段但保留历史最长值。上述规则全部由 PK-150 service 计算，QQ 等消费者只读取字段，不复制周期规则；普通 status 仍零写入且不迁移个人文件。

控制台的每个当前目标卡片会直接展示 API 返回的启用起点、已启用天数、当前连续完成数和历史最长连续完成数；连续单位按目标事实显示为天、周、月或年。未知起点/天数显示“未知”，零值明确显示 `0`，临时目标明确说明不累计启用天数；浏览器不重新计算周期或连续记录。软删除目标仍按既有语义退出当前目标列表，历史打卡、积分、奖励和复盘依据继续保留。

打卡只接受当前有效且属于目标周期的目标，拒绝未来日期；同一目标同一周期的重复请求不重复发积分。打卡响应会直接返回该目标的 `active_since/active_days/current_streak/longest_streak/streak_unit` 和确定性 `encouragement`。只有调用方显式提交 `with_encouragement=true` 且本次为非重复成功完成时，service 才通过 PK-200 受控生成选择 `warm/strict/playful` 语气；最终鼓励正文仍由打卡事实组装，失败时返回本地文案并标记 `kei_generated=false`，不影响已经原子提交的打卡。奖励兑换支持可选 `request_id`，相同请求不重复扣分。日/周/月/年复盘只统计截至今天的实际事实，不把当前周期中的未来日期算作未完成；完整周期奖励按持久化 key 幂等发放。

Kei 复盘只通过 PK-200 的稳定 `TextGenerator.generate_text()` 调用，不直接创建或持有原始 LLM client，也不写普通聊天 history。模型只选择表扬、批评或褒贬并存的受限裁决，最终文本由实际完成/未完成/积分事实确定性组装；模型不可用、超时、失败或返回无效裁决时标记 `kei_generated=false` 并返回本地规则复盘。真实状态继续位于 `server/systems/data/demon_slayer.json`，不会自动迁移；损坏文件明确失败，原子保存失败保留旧文件。自动测试只使用临时 store 与 fake TextGenerator。

### 好感度与长期记忆可安装模块

好感度与长期记忆位于 `server/features/affection_memory/` 的 models、repository、service、context、router 和 compatibility 分层，并以可安装 `in_process` 包装配，不新增进程。安装、启用并重启后，版本化接口位于 `/api/v1/relationship/*` 与 `/api/v1/memories*`；原 `/affection/*`、`/memories*`、旧 Python 导入和显式文字/语音命令继续委托同一 service，动态面板只通过公共请求上下文访问 API。

好感度保留原等级、范围、事件、选项、回复和 legacy reset。事件选择在同一文件锁内结算，同一活动事件的重复或并发选择最多生效一次；无活动事件、错误事件和错误选项安全失败。长期记忆支持列表、新增、稳定 ID 删除、按序号命令删除和显式 legacy clear；空/超长内容、非法标签/来源被确定性拒绝，相同内容或 `request_id` 重试不会重复新增。危险的 `/affection/reset` 与 `/memories/clear` 只为旧客户端保留，不在版本化接口或控制台新增暴露。

控制台同机读取关系状态和记忆列表使用只读本机守卫；事件、选择、新增、删除及 legacy reset/clear 继续要求可信控制台 Origin。非本机访问仍由 Core 全局 Loopback 边界先行拒绝。

两个 repository 分别独占现有 `server/data/affection_state.json` 与 `server/data/memories.json`，不会创建、合并或搬迁 `server/systems/data` 同名文件。所有写入使用同路径进程锁、唯一临时文件、`flush/fsync` 和原子替换；损坏状态明确失败，保存失败保留旧字节。好感度 reset 不清长期记忆，记忆操作不改好感度，清 conversation history 也不触碰两者。

全部版本化及 legacy relationship/memories HTTP 接口同时要求本机客户端，并在请求带浏览器 `Origin` 时只接受 `http://127.0.0.1:8000`、`http://localhost:8000` 或等价 IPv6 本机控制台；无 `Origin` 的本机 CLI 与测试客户端保持兼容。全局本机边界先于精确 Origin CORS 和 PK-160 模块 guard，对读取、写入及 OPTIONS 预检统一拒绝非本机客户端或恶意 Origin，路由再执行同一控制检查。迁移前由冻结事件目录生成、但缺少 `instance_id`/`created_at` 的合法活动事件会在内存中获得确定性的稳定身份；status、choice 与只读 relationship context 可继续使用，普通读取不自动改写个人文件，未知或被篡改的事件仍明确失败。

正式 `AffectionMemoryContextProvider.get_context()` 每次只读最新状态，只输出关系概览和经过筛选、限量、逐条限长及总长限制的记忆资料；不含内部 ID、时间戳、完整事件历史或写能力。上下文明确标记用户记忆是资料而非系统指令，不写聊天 history。数据缺失时返回空字符串，状态损坏或 Provider 异常由 PK-200 既有安全降级处理，conversation 本身不反向导入 PK-160。

### Fitness 可安装模块

健身打卡位于 `server/features/fitness/` 的 models、repository、service、router、compatibility 分层，并以可安装 `in_process` 包装配，不新增进程或端口。安装、启用并重启后，版本化接口为 `GET /api/v1/fitness/status` 和 `POST /api/v1/fitness/checkins`；原 `GET /fitness/status`、`POST /fitness/checkin`、`POST /fitness/reset` 与 `server/systems/fitness_checkin.py` 继续委托同一 service。危险的 legacy reset 不提供版本化对应接口，也不在控制台暴露。

生产 composition 显式把唯一 repository 指向已有个人状态 `server/data/fitness_checkins.json`，不创建、猜测、合并或迁移旧的 `server/systems/data/fitness_checkins.json`。同日打卡幂等，连续天数按唯一合法自然日计算，断档后重算；每连续 6 天按既有 Kei 文本发放一次奖励，6 天、12 天等里程碑分别持久化且不可重复发放。状态返回累计打卡、最近 14 个日期、最近 10 条奖励和距离下次奖励天数；旧文件中的重复日期和非法日期不重复计数或导致崩溃。

repository 对同一路径的读改写加锁，使用同目录唯一临时文件、`flush/fsync` 与原子替换。损坏 JSON、错误根结构、篡改奖励或保存失败明确失败，不能回空后覆盖；普通 status、控制台加载与模块 catalog 均零写入、零外网。版本化接口不拥有 TTS，只有明确请求 `with_audio=true` 且刚解锁奖励的 legacy check-in 才在应用接缝尝试本机语音。所有 fitness HTTP 读取和写入仅接受本机客户端及可信 8000 控制台 Origin，浏览器不保存健身业务数据。

### 每日生活预报可安装模块

`life_forecast@1.0.0` 是 PK-240 的独立 `in_process` 模块候选。安装、启用并重启
Core 后，控制台以“天气事实 / 生活建议 / 娱乐运势”三个清晰区块显示今天内容；
继续复用公共三主题、响应式折叠、键盘/ARIA 和本机头像配置，不在浏览器保存位置或
业务缓存。

模块默认 Provider 为 `disabled`。用户在控制台明确填写城市显示名与经纬度、选择
`open_meteo` 并保存时只写 Git 忽略的本机配置，不联网；只有再次点击“显式刷新”
才把经纬度发送到固定 Open-Meteo 天气/空气质量 HTTPS API。页面加载、展开、主题或
Provider 选择、配置/今天缓存读取都不访问上游。城市标签、生日、星座和娱乐内容
不会发给第三方；模块不自动定位，也不读取系统定位。

今天缓存位于 `server/data/modules/life_forecast/cache/YYYY-MM-DD.json`，配置位于
同一模块数据根的 `config.json`。正常读取只看用户本地今天文件；旧日期、损坏缓存或
位置配置变化都不会冒充今天。获取、解析或原子保存失败保留旧缓存。缓存不保存明文
城市/坐标，只保存配置指纹；卸载默认保留该模块数据，重装后继续关联。

天气事实包括本地 allowlist 条件、当前/体感/最高/最低温、最大降水概率、最大风速、
UV、美国 AQI 和必要预警可用性。第一版 Open-Meteo 没有模块可消费的官方灾害预警，
因此预警明确为 `unavailable`；UV/AQI 上游缺失也照实显示 unavailable，不编造。
生活建议只按规范化数值做确定性穿衣、出行/带伞、UV 和空气质量提示，不替代当地
官方、医疗或应急指引。

可选“今日运势”完全在本机生成，不使用星座、生日、位置或第三方 API。公开规则为
`local-date-sha256-v1`：对规则版本和用户本地日期做 SHA-256，从固定提示/颜色/小行动
表中选取；同日稳定、可关闭，始终标注“娱乐内容、非事实预测”，与天气事实严格
分区。

Open-Meteo API 数据按 CC BY 4.0 使用，控制台保留 Open-Meteo 署名链接；空气质量
数据同时署名 CAMS。免费公共服务适合非商业低频使用，商业/高量部署应按
[Open-Meteo 当前许可](https://open-meteo.com/en/license)与服务条款选择合适端点。
Project Kei 不内置或回显天气 API Key。完整 Provider、缓存、隐私和未来集成边界见
[每日生活预报模块契约](docs/architecture/daily-life-forecast.md)。

PK-240 本身不拥有每日情报或 QQ 调度。PK-241 只通过当天只读摘要契约完成消费端
联动：每日情报使用默认关闭的总开关和逐项投影；QQ 使用默认关闭的总开关，固定
“生活预报”按钮会显式刷新一次，四个完整关键词仅查询当天缓存。两端都不复制
PK-240 的 Provider、缓存或生活规则，也不新增定时推送。

### 每日情报来源管理

控制台可维护以下个人关注目标：

- X/Nitter 用户名；
- GitHub 用户与 `owner/repository` 仓库；
- B 站 UID（正整数）；
- YouTube Channel ID（不是频道昵称或 `@handle`）；
- 论文优先/常规/AI 作者；
- 信息差 X 用户。

首次保存会创建 `server/data/intel_sources.json`。它会覆盖代码中的默认关注名单，但只保留在本机且已被 Git 忽略。采集器在**每次新的采集**开始时重新读取该文件，因此保存后不需要重启 API 或 QQ bridge。

保存名单不会自动重新采集当天缓存，以避免 B 站等来源被重复请求。若确实需要立即验证，请使用面板中的“按新名单重新生成今日情报”，确认后它会使用 `refresh=true` 覆盖当天缓存。

来源配置的版本化接口为 `GET/PUT /api/v1/intel-sources`、`POST /api/v1/intel-sources/{field}` 与 `PUT/DELETE /api/v1/intel-sources/{field}/{index}`。写操作只更新本机注册表，不级联资料查询或情报刷新；旧 `/dashboard/intel-sources` 继续委托同一个 registry，并采用与版本化接口一致的本机客户端和浏览器 Origin 限制。X 资料与今日言论使用 `/api/v1/x/*`，B 站资料使用 `/api/v1/bilibili/profiles*`，原 dashboard profile/posts 路径仍兼容。

当前可视化管理的是“人/ID/仓库”类目标；arXiv 主题分类和关键词、Nitter 实例、信息差 RSS 地址等高级搜索规则仍保留在 `server/intel/intel_config.py`，除非明确扩展，不应擅自改写。

X/Nitter 目标仍以账号名作为稳定配置。控制台把普通 X 用户与“信息差 X 用户”的显示资料共同缓存在本机 `server/data/x_profiles.json`。打开控制台、增改删关注项和 `GET /api/v1/x/profiles` 都只读缓存；未缓存项显示刷新提示，不会隐式访问 Nitter。只有用户点击单条“刷新资料”时，`POST /api/v1/x/profiles/resolve` 才查询显示名称和头像；失败查询会冷却 6 小时。资料查询不会触发推文采集或重新生成每日情报。

每个 X/Nitter 条目提供标签为“查询日期”的日期选择器，以及“获取该日言论”“获取该日至今”两个显式按钮。前者查询所选日期在 `Asia/Shanghai` 的自然日半开区间 `[00:00, 次日 00:00)`；后者查询 `[所选日期 00:00, 请求处理时刻]`。最多回溯包含今天在内的 30 个自然日，未来日期、非法日期和超限日期都在联网前拒绝。两种查询结果只在当前页面内按用户、模式独立保留，同一用户同一时刻只显示一种；不写浏览器存储、不落盘，也不覆盖今日兼容缓存。页面加载、选择日期、切换已有结果、展开/收起、读取缓存或保存来源配置都不会访问 Nitter。

兼容 `POST /api/v1/x/posts/fetch?username=...` 现在明确表示 `Asia/Shanghai` 今天 00:00 至请求时刻，成功后仍把普通 `/<handle>/rss` 实际提供的原创帖、引用帖和回复统一保存到唯一的 `server/data/x_daily_posts.json`；刷新一个账号不会覆盖其他账号。`GET /api/v1/x/posts` 只读该本地自然日缓存。新 `POST /api/v1/x/posts/query` 只返回本次日期窗口结果，不持久化。单用户控制台日期窗口与 daily briefing 的滚动 lookback（通常 24 小时）是两套明确语义，后者未改变。

Nitter RSS 条目仍按明确结构区分原创帖、回复、纯转发、引用帖和 unknown，以便过滤纯转发、冲突标记和 unknown，并避免把引用正文混入当前用户文字。Nitter 是显式单用户采集的首选来源；只有本次 Nitter 请求失败时，服务才会使用固定的 `https://api.fxtwitter.com` FxEmbed/FxTwitter API v2 作为无 Token 后备。普通页面加载、缓存读取、展开、日期切换、发帖/回复栏目切换和来源保存均不会请求 Nitter 或 FxEmbed。

FxEmbed 后备只把受关注用户自己的原创帖、引用帖和回复归一到现有单一言论结果及 `x_daily_posts.json` 今日兼容缓存。对于结构中带合法直接父帖 ID 的回复，最多补抓一层父帖，并且只有父帖作者与被回复用户名匹配时才显示有限的用户名、正文、时间和链接；不会调用 conversation 接口，不分页追踪祖先、后代或其他用户的完整线程，也不会补抓引用帖正文。每个用户卡片固定提供“发帖 / 回复”本地栏目，切换只过滤已取得结果，不新增 replies API、第二份缓存或网络请求。缺少合法 aware 发布时间的条目不会被猜测进窗口；每次最多返回 30 条，外部文本和链接会在响应及今日缓存写盘前净化。

B 站目标仍以 UID 作为稳定配置，但控制台会额外显示对应昵称和头像。打开控制台、增改删关注项和 `GET /api/v1/bilibili/profiles` 都只读本机 `server/data/bilibili_profiles.json`；未缓存项不会自动联网。只有用户点击单条“刷新资料”时才显式查询，失败会进入 6 小时冷却。资料请求先从 B 站公开 nav 数据取得并在当前 client 内缓存 WBI key，再为 `/x/space/wbi/acc/info` 动态生成 `wts/w_rid`；签名、Cookie 和上游正文都不会进入缓存或日志。上游昵称和头像 URL 在进入 API 响应及原子缓存前统一做凭证形态文本与敏感 URL 参数净化，控制台仍进行 HTML 转义。资料查询只更新控制台展示，不会重新生成每日情报。

控制台的 B 站栏目另有独立参数维护区。当前 Collector 的最小 allowlist 只有本人会话的 `SESSDATA`、`bili_jct`、`buvid3` 三项 Cookie，均为必填密码式输入；不接受整段 Cookie Header、任意 Header、脚本或 JSON。`GET /api/v1/bilibili/credentials/status` 只返回缺失/已配置/已失效、脱敏尾部和时间戳；`PUT /api/v1/bilibili/credentials` 只把完整候选值原子保存到 Git 忽略的本机双槽文件，不联网、不改 `.env`、不替换旧 active。只有显式 `POST /api/v1/bilibili/credentials/validate-and-collect` 才使用候选参数查询当前名单的资料和空间动态；二者成功后才原子切换 active，失败时旧 active、资料缓存和 PK-110 今日情报缓存保持不变。`anti_bot/rate_limited/timeout/upstream_*` 和 WBI key 不可用属于共享会话或网络失败，验证会在首个 UID 的有限重试后立即终止并记录安全错误码，不会对名单中的每个 UID 重复等待；单个 UID 的 `not_found/invalid_profile` 仍与其他 UID 隔离。legacy dashboard 路径委托同一 service。

### 每日情报与 B 站稳定性

- 当日规范化缓存位于 `server/data/briefing_cache/YYYY-MM-DD.json`，Kei 播报稿单独位于 `kei_summary_today.json`；两者有明确 Schema 并原子替换，正常读取不会联网、调用 LLM 或 TTS。
- 点击生成或强制刷新后，控制台通过只读 `GET /api/v1/briefing/generation-status` 展示采集、Kei 改写、保存阶段，以及本轮实际工作来源的完成进度；缺失来源补采只计入实际补采集合，不把其他来源长期显示为“等待”。失败来源还会显示本轮实际产生的白名单有限诊断码，例如 `timeout（请求超时）`；它与旧缓存中的 coverage/warning 分开展示，因此失败刷新保留旧缓存时也不会把旧原因冒充成本次结果。状态只在 API 进程内存中有界保留，重启后回到 idle，不保存或返回条目正文、标题、URL、prompt、路径、warning 正文、异常正文或凭证。轮询最长 36 分钟，完成、失败或页面卸载即停止。
- 控制台“今日情报”把“来源状态与错误详情”“今日论文”“Kei 今日播报总结”分别放入默认收起的详情区。来源详情只读当天 coverage、warning 与 retry_after；有上游有限诊断码时照实显示，没有时明确标记“来源未提供”，不猜测原因。论文详情通过只读 `GET /api/v1/briefing/today` 展示当天缓存中 `category="papers"` 的标题、已有摘要、作者与安全 HTTP(S) 来源链接；缺少摘要时显示“摘要暂缺”。打开、刷新或展开这些详情不会调用 Collector、LLM、voice 或写缓存，跨 arXiv/Crossref/Semantic Scholar 的同一论文只显示一次。
- 来源详情中的每个公共来源都有“强制刷新此来源”按钮。确认后只向版本化 `POST /api/v1/briefing/refresh` 发送该 `source_id`，跳过该来源补采冷却但不采集其他来源，也不调用 Kei 改写；成功时在旧当天文档上事务替换该来源，其他来源条目和 coverage 保持不变，失败时保留提交前缓存。PK-110 不再用固定 120 秒总时限取消 X、B 站等串行多目标 Collector；各来源仍保留自身的单次请求超时、有限重试和冷却。浏览器单来源操作最长等待 35 分钟，执行期间所有单来源按钮禁用。需要在原生 PowerShell 窗口观察时，只轮询 `GET /api/v1/briefing/generation-status` 的阶段、耗时、来源状态和有限错误码，不恢复可能泄露上游正文或凭据的逐项日志。
- `twitter/github/bilibili/youtube/money/arxiv/crossref/semantic` 都有独立 coverage。`failed`、`not_configured`、成功但 `empty` 是不同状态；warning 与 `retry_after` 会随缓存返回并显示在控制台。
- X、B 站和 RSS 不再把已知异常统一压成“不可用”：Collector 会以脱敏 warning 附带有限诊断码及受影响目标数量，控制台同时显示英文码和中文解释。典型码包括 `timeout`、`network_error`、`rate_limited`、`parse_error`、`anti_bot`、`access_denied` 和 `upstream_unavailable`；不会包含账号、请求 URL、响应正文、Cookie 或 Token。多个原因会分别展示，仍未知时才显示“来源未提供”。
- 主 API 已直接注册八类 Collector 1.0；X、GitHub、B 站、YouTube 和固定 RSS 并发隔离，论文按 arXiv → Crossref → Semantic Scholar 协调，Semantic fallback 只查询尚未覆盖的作者。旧 `intel/briefing.py` 仅保留脚本和 Python 兼容，不再是主 API 的生产注册入口。
- arXiv、Crossref、Semantic Scholar 的 Collector 公开实现与进程级 HTTP 协调统一由 `server/features/papers/` 拥有；同一上游的新旧入口共享一个可注入 runtime、client 与 limiter（并发、最小间隔、429 冷却），`server/intel/collectors/arxiv.py` 和 `papers.py` 仅为 deprecated 兼容 facade。
- YouTube 只接受 `UC` Channel ID 并读取公开 Atom Feed；GitHub 采集公开用户事件和仓库 Release，可选 Token 只来自环境；RSS 只访问应用固定的 HTTPS 公网 Feed，不接受浏览器临时 URL。
- 有失败/partial 来源时，系统只在补采冷却到期后按来源补采，不重采完整来源集合；失败补采保留旧条目并更新覆盖状态。
- 强制刷新会先保留旧版本作为事务保底。gateway/Collector 全部失败时不覆盖旧主缓存或播报稿，响应以 `failed_using_cache` 明确说明继续使用旧缓存；主缓存与播报稿共同暂存并提交，任一替换失败会恢复两份提交前字节。
- Collector 的 warning、coverage detail、标题/摘要/作者、metadata 字符串和 URL 都在公共模型边界统一做有限凭证脱敏；敏感 URL query 参数会被移除。legacy 失败日志只保留来源和异常类型，不输出异常正文或关注作者。
- items、coverage、warning 或原始摘要变化都会使旧 Kei 播报稿失效；显式 rewrite 重新生成，否则持久化明确 fallback，生成响应与立即重读缓存保持一致。
- 去重使用稳定 ID、规范 URL、平台 ID、标题规则和论文 DOI；论文跨 arXiv/Crossref/Semantic Scholar 合并时保留全部真实发现来源。未来时间和 lookback 外条目不会进入当天展示，缺失发布时间的条目保留并稳定后排。
- 同一天已经生成或已回退的 Kei 播报稿默认复用；只有显式 `rewrite_refresh=true` 才重新调用当前 PK-200 模型。模型失败、超时或空回复返回明确 `generated=false/fallback=true` 的原始摘要兜底。
- B 站 UID 之间有节流；遇到反爬会等待后只重试一次。
- 控制台昵称/头像查询与视频采集相互独立；成功资料长期复用本机缓存，失败查询也有冷却。
- 即使配置了 Cookie，部分 UID 仍可能因平台风控返回 `412`、`-352` 或其他失败；Cookie 不是永久解决方案。
- 情报中“本次未采到信息”不等价于“今天没有发表/没有动态”；应结合数据覆盖和错误警告判断。
- Collector `1.0` 已于 2026-07-22 经 PK-900/PK-000 最终复核正式冻结；下游来源配置、X、B 站、YouTube、GitHub、论文与 RSS 任务可以按冻结协议分别独立领取和并行实施，破坏性协议修改仍须交回 PK-000 决策并提升 major。

### 模型方案

控制台继续使用 legacy LLM 面板测试并应用 DeepSeek Flash、DeepSeek Pro 或兼容 OpenAI 的本机自定义方案。面板保留原元素 ID 和“测试并应用”操作，不显示、编辑或存储 API Key，也不把 profile 写入 `localStorage`；服务端只使用 `server/.env` 中已有的凭证。profile 只保存/返回 `provider`、`base_url`、`model`、`thinking_mode`、`updated_at`，custom provider 会自动关闭不支持的 thinking 参数。

版本化文字接口是 `POST /api/v1/conversation`，只返回 `text`、白名单 `emotion` 和 `timestamp`，不触发音频；`/chat`、`/chat/text-only`、`/history*` 和 `/ws/chat` 继续兼容并调用同一 service。情绪标签会从用户可见文本中去除，未知标签回退为 `calm`。当前 history 仍是单用户、单 API 进程内状态，最多保留 20 轮/40 条消息；超限截断最旧消息，切换模型保留 history，重启 API 会清空。清 history 不会清长期记忆、好感度或 profile。

模型更新会先规范化并用现有环境 Key 测试独立候选 client，测试成功后才在同一串行化流程中原子保存 profile、切换活动 runtime，并最后关闭旧 client。失败会维持旧方案和 history。文字、voice 的文字阶段、每日情报改写、生命维持提醒和斩妖复盘都持有稳定 conversation 门面，下一次调用会共同看到新模型；受控生成失败会明确返回/使用 `generated=false` 的业务兜底，不伪装成成功生成。

API shutdown 会把 conversation runtime 置为不可逆关闭状态：已进入的模型调用先安全结束，活动 client 只关闭一次；关闭后不会再调用 client、追加 fallback history、保存 profile 或提交候选模型。关闭后的内部受控生成只返回 `generated=false` 的本地兜底，chat/profile 写入则明确拒绝。

profile 控制接口只接受本机请求；带浏览器 Origin 时还必须来自 `http://127.0.0.1:8000`、`http://localhost:8000` 或等价 IPv6 本机控制台。Base URL 允许明确配置本机 OpenAI-compatible HTTP 服务，但必须是绝对 HTTP(S) URL且不能含用户名、密码、query 或 fragment。候选测试会产生一次外部 `/chat/completions` 请求；普通 GET、损坏 profile 回退和打开控制台不会测试模型。超时、连接/鉴权/限流/5xx、无效 JSON、缺少结果或空回复只返回有限脱敏状态，不返回上游正文、Authorization、系统提示、长期上下文或调用栈。

### 语音公共层

版本化语音入口为 `POST /api/v1/voice/chat` 与 `POST /api/v1/voice/chat/stream`，原 `/voice/chat`、`/voice/chat/stream` 和 `/voice/audio/*` 继续兼容。两组路径共用 `server/features/voice/` 中的同一个 service，文字阶段只调用 PK-200 的公开 conversation service；ASR 仍使用 8010，TTS 仍使用 9880，不新增进程或端口。

同步响应保留原有识别、回复、情绪、音频、时间和耗时字段，并用 `audio_available`、`mode`、`degraded`、`errors` 明确表示降级。音频字段只返回 `/api/v1/voice/audio/*` 或 `/voice/audio/*` URL，不返回本机路径。流式响应是 NDJSON：先发 `reply`，完整合成成功后发零到多个 `audio_part`，最后只发一个 `done`；ASR/对话失败则以一个已清洗的 `error` 终止。没有 TTS、Voice Pack 解析失败或合成失败时仍返回已取得的文字，明确标记 `text_only`，不会伪造音频。

上传只接受常见音频 MIME 与 `.wav/.mp3/.m4a/.flac/.ogg/.webm`，默认最大 16 MiB，并按受限分块读取。ASR 缺失、超时、失败、空结果或超长结果不会向 PK-200 提交空/无效文字。请求暂存目录在成功、失败、取消和流式中断后都清理；流式中断还会删除该请求尚未完整交付的音频，不影响并发请求。正常完成的受控输出继续位于忽略的 `server/output/voice_replies/` 并由现有保留策略清理。

PK-210 只定义 `SpeechToTextProvider`、`TextToSpeechProvider`、`ConversationProvider`、`VoicePackResolver` 和最小 `VoicePackRef`。GPT-SoVITS 上游来源/版本/安装逻辑归 PK-211，Kei 权重、参考音频和具体 Voice Pack 内容归 PK-212；主 API 不再内置 Kei 资产路径或参考文本。模块导入和 API 启动不会主动探测这些 Provider，只有显式语音请求或 voice health 才访问已有本机服务。完整协议见 [语音公共契约与编排](docs/architecture/voice.md)。部署本次代码后需要重启 API；8010/9880 与现有启动器不变。

`POST /api/v1/voice/synthesize` 是给受控 sidecar 使用的最终文字合成入口，只接受
`{"purpose":"qq_reply","text":"..."}`，不再调用 ASR、conversation、LLM 或 history。
它把分段 WAV 统一为有界 PCM 后只编码一次，固定输出
`qq_c2c_voice_v1`/`audio/silk`，上限 60 秒、8 MiB；缺少受控 Silk encoder 时明确
`encoding_unavailable`，绝不把 WAV 冒充为 QQ 语音。voice health 只报告本地 engine、
Voice Pack 与 encoder readiness，不读取 QQ Secret 或推断 Bot 权限。QQ Node sidecar
已实现有界 C2C 媒体上传，但只有本地 profile ready 且 PK-140 的非秘密
`qq_media_upload_capability` 明确 `available` 时才可开启；`unknown` 默认关闭，纯文字不受影响。

PK-211 现提供 `GPTSoVITSProvider`：默认连接本机 9880，`auto` 风格先尝试现有 `api.py` 的 `POST /`，仅在 404 时回退 legacy `/tts`；也可固定为 `api_py` 或 `legacy_v2`。Provider 接收 PK-210 的合成请求和不透明 Voice Pack handle，不发现或拥有角色资产；同一 9880 实例上的活动 Pack 确认、必要权重切换和完整合成请求由唯一共享引擎会话串行化，正在合成时不能切换到其他 Pack。权重切换优先使用当前 GPT-SoVITS 的组合 `/set_model` 接口，仅当该接口明确返回 404/405 时兼容旧版 `/set_gpt_weights` 与 `/set_sovits_weights`；其他上游故障不会触发第二套写入。health、超时、连接失败、非音频响应与上游错误都只返回有限脱敏状态。

PK-212 的正式 Schema 位于 `server/features/voice/voice_packs/voice-pack.schema.json`。可移植包根必须包含 `voice-pack.json`，所有权重和参考音频引用必须是包内 POSIX 相对路径并带精确字节数与 SHA-256；绝对路径、`..`、目录逃逸、符号链接、未知引擎、摘要不符以及 BAT/PowerShell/Python/可执行安装内容都会被拒绝。导入只接受用户显式指定的本机目录或 ZIP，不联网；目录包原地登记，ZIP 解到忽略的运行目录。注销只删除注册记录，不删除源资产或运行副本。

本机 Voice Pack 管理接口为 `GET /api/v1/voice-packs`、`POST /api/v1/voice-packs/import`、`POST /api/v1/voice-packs/{id}/{version}/enable|select|disable` 和 `DELETE /api/v1/voice-packs/{id}/{version}`。所有写操作必须同时来自本机客户端，并且浏览器 `Origin` 只能是 8000 端口的本机控制台；没有 `Origin` 的本机脚本、测试客户端和 CLI 保持兼容。全局本机边界和精确 Origin CORS 先执行，Voice Pack 专用中间件继续对恶意 POST/PUT/PATCH/DELETE 预检作纵深拒绝，实际写路由再次执行同一控制检查；只读 GET 仍受全局本机边界保护。响应只返回 ID、名称、版本、引擎、语言、完整性模式和状态，不返回包根、权重或参考音频的绝对路径。选择会在共享引擎会话内完成候选校验、两阶段权重切换和活动 ID 原子提交；任一步失败或取消都先恢复旧 GPT/SoVITS 权重再传播失败/取消。若回滚本身失败，Provider 和 Registry 都公开 `unknown/unavailable`，列表不再把旧 Pack 标为活动，必须通过一次成功选择恢复，不能继续假装旧 Pack 可用。现有 Kei Pack 以 `kei@1.0.0` 本机登记，使用 `existence_only` 明确表示只做了必要文件存在性检查，未读取权重/音频、未计算大型摘要、未复制或重新训练，且不可据此声称资产可再分发。完整协议见 [Voice Pack Schema、注册表与切换](docs/architecture/voice-packs.md)。

PK-213 在不改变上述 Schema/Registry 所有权的前提下增加受版本控制的远程
catalog、确定性发布构建器和 `voice-pack.bat`。第一版只接受 catalog 内固定的
HTTPS 来源、版本、字节数和 SHA-256，不接受任意用户 URL；下载、校验和安全解包
后仍委托 PK-212 导入/启用/选择；同 key 的可信重复安装还必须经 PK-212 只读
内容比较证明完全等价。当前没有获得或记录真实 Kei 权重与参考音频的
公开分发授权，也没有可用的真实 catalog 条目、URL 或摘要，因此不得创建真实
Release 或把 `kei@1.0.0` 描述为可远程安装。

外部引擎描述位于 `server/features/voice/providers/gpt_sovits/engine.json`。当前固定上游 release 为 `20250606v2pro`、完整 commit 为 `d7c2210da8c013e81a94bfc7b811a477c99fd506`；上游发布页确认的 NVIDIA 50 系 Windows 包固定到分发 revision `fb387b7a65a5441e5e3985f4ab9b721a9d455363`，大小 `8,835,144,925` 字节，SHA-256 为 `97b4edcd451c42357db7e26e6c1c877ca5d85144fe97beaff6d7005d35bee008`。公开描述还记录 API 风格、health、能力、许可证、归档限制和本机状态来源，不记录实际安装根。

在根目录查看无路径本机状态：

```powershell
.\scripts\python.ps1 -m features.voice.providers.gpt_sovits.cli status
```

已有安装只需由用户显式登记：

```powershell
.\scripts\python.ps1 -m features.voice.providers.gpt_sovits.cli register --install-root <项目外绝对目录> --api-style auto
```

受控获取也只能由用户显式运行，并要求精确确认 `gpt-sovits-v2pro-nvidia50`；CLI 不接受任意 URL、Git URL、安装命令、PowerShell/BAT 或脚本参数。它先在隔离临时目录下载固定 HTTPS 归档，核对精确字节数和 SHA-256，再拒绝路径穿越/链接/超限归档并原子安装到不存在或空的项目外目录；重复固定安装和离线登记可以复用。归档脚本永不执行。真实 7z Python 解包依赖缺失时会明确返回 `extractor_dependency_missing`，必须由用户另行显式处理，系统不会自动 `pip`、安装 CUDA/依赖或假报成功。完整协议见 [GPT-SoVITS 外部引擎 Provider 与受控获取](docs/architecture/gpt-sovits-engine.md)。

### QQ bridge

- 仅处理 `QQBOT_ALLOW_FROM` 白名单内的 C2C 私聊。
- 白名单校验发生在消息去重、菜单、按钮、conversation、情报与发送之前；空白名单零转发、零回复，普通日志不输出完整消息或 OpenID。
- 普通消息调用 `POST /api/v1/conversation`；legacy `/chat/text-only` 只保留兼容。
- “每日情报”等关键词与按钮只读 `GET /api/v1/briefing/today`；不会为单次查询或定时发送自动采集。
- QQ 主菜单固定展示每日情报、斩妖除魔、健身打卡、专注计时、日历与修炼；主/子菜单展示零业务写入，明确功能文字和严格日历命令在宽泛情报关键词及普通 conversation 之前路由。
- 业务菜单只调用固定版本化 `/api/v1/demon-slayer/*`、`/api/v1/fitness/*`、`/api/v1/focus/*`、`/api/v1/calendar/*`：斩妖支持今日目标打卡、显式 daily 复盘，以及经用户绑定确认后创建日/周/月/年常驻目标；说“添加斩妖任务”或不带标题的“添加日/周/月/年任务”会弹出周期按钮，严格 `添加日任务 目标名称` 等命令再弹出单次确认，只有确认才调用一次 `/api/v1/demon-slayer/goals`。待确认标题只在 Node 内存保留 10 分钟，不进入按钮 action、磁盘或 conversation。点击“完成”会在同一次 check-in 请求中显式要求受控鼓励，并展示 API 返回的启用天数、当前/历史连续周期及正确天/周/月/年单位，Node 不重复计算规则，也不额外调用 conversation。健身限明确 check-in；专注保留 25 分钟无鼓励按钮，并提供显式“25 分钟、10 分钟后鼓励”及严格 `专注 25 鼓励 10`，始终 `force=false`；日历新增只接受两条确定性单消息命令。不开放 legacy、reset、奖励兑换、目标编辑/删除、临时目标、任意 URL/prompt 或模块生命周期。
- 专注鼓励只在 sidecar 到期重新读取 focus status 并精确匹配 `active + session_id + start_at` 后调用一次本机 `POST /api/v1/focus/encouragement`；该接口由 focus composition 使用 PK-200 `TextGenerator`，不写普通聊天 history。停止、完成、会话替换、白名单移除、模块不可用、状态损坏或 shutdown 都不会发送；模型失败/超时使用有界本地文案。
- 动态斩妖 goal_id 必须来自最近一次同用户 status 的有界短时缓存；所有业务列表、keyboard、Markdown 和错误均限量/限长/脱敏。API 404、422/500、超时或损坏个人状态只给固定提示，bridge 不读取业务 repository、个人 JSON 或缓存。
- 每日预生成显式调用 `POST /api/v1/briefing/generate`；发送按日期/哈希用户去重，生命维持按槽位/哈希用户去重，状态分别最多保留 14 天/96 槽。
- 两类日程 PUT 会在同一 repository 锁域先读取并语义校验现有文件；现有文件损坏或结构异常时固定返回 `schedule_state_invalid`，不覆盖旧字节。
- sidecar state 只接受规定字段、合法日期/槽位、24 位小写十六进制用户哈希和有限状态/错误码；完整 OpenID 形态键、Authorization、Token、消息字段或非法记录会在读取后立即关闭对应 scheduler，且不读取日程、不建 timer、不生成、不发送、不改写原文件。
- QQ 401 最多刷新 Token 并重试一次；Gateway 使用有上限的单 socket/heartbeat/reconnect 退避，shutdown 取消未来工作。
- QQ Markdown 卡片、机器人头像和客户端展示由 QQ 开放平台与 QQ 客户端控制，bridge 不能强制改变移动端头像布局。
- 每日预生成、QQ 推送和生命维持提醒都需要 API 与 QQ bridge 同时持续运行。
- 完整进程、API、状态和 at-most-once 失败语义见 [QQ bridge 契约](docs/architecture/qq-bridge.md)。

## 本地状态、缓存与安全边界

下列内容属于本机状态；除表中另有说明的历史状态文件外，均应保持在 Git 之外：

| 内容 | 位置 | 说明 |
|---|---|---|
| 服务密钥与凭证 | `server/.env`、`server/qq_bridge/.env` | 永不输出或提交 |
| 模型方案 | `server/data/llm_profile.json` | 控制台本地设置 |
| GPT-SoVITS 本机登记 | `server/data/gpt_sovits_engine.local.json` | 忽略；只保存实际外部根、API 风格与明确的安装/完整性状态，不保存角色资产 |
| Voice Pack 本机注册表 | `server/data/voice_pack_registry.local.json` | 忽略；保存活动 Pack ID、脱敏 manifest 和本机资产绑定，API 不返回绑定路径 |
| Voice Pack 导入运行目录 | `server/runtime/voice_packs/` | 忽略；仅存显式导入 ZIP 的受控展开结果，注销默认不删除 |
| 控制台自定义头像 | `server/data/dashboard_ui/avatars/` | Git 忽略；PK-100 只保存用户明确上传的 PNG/JPG/WebP UI 素材，不保存业务状态或凭据 |
| 每日推送计划 | `server/data/daily_briefing_schedule.json` | bridge 轮询读取 |
| 生命维持计划 | `server/data/life_support_schedule.json` | bridge 轮询读取 |
| 情报来源名单 | `server/data/intel_sources.json` | 个人偏好，本地覆盖 |
| X/Nitter 显示资料 | `server/data/x_profiles.json` | 普通与信息差 X 用户共用；成功后缓存，手动刷新时才更新 |
| X/Nitter 今日兼容言论 | `server/data/x_daily_posts.json` | 普通 RSS 实际提供的原创帖、引用帖和回复统一按 `Asia/Shanghai` 自然日、账号缓存；日期/区间查询不落盘 |
| B 站昵称/头像资料 | `server/data/bilibili_profiles.json` | 仅用于控制台识别 UID；成功后缓存，手动刷新时才更新 |
| B 站本机采集参数 | `server/data/bilibili_credentials.local.json` | Git 忽略；active/candidate 双槽原子保存三项 allowlist Cookie，状态 API 只返回脱敏元数据 |
| 情报缓存 | `server/data/briefing_cache/` | 每日采集结果；`kei_summary_today.json` 只保留当天供 Kei 播报的总结，跨天启动或更新时自动删除旧内容 |
| 每日生活预报配置/缓存 | `server/data/modules/life_forecast/` | Git 忽略；配置保存城市标签、经纬度、Provider 与娱乐开关，按日本地缓存不保存明文位置；只有显式刷新访问上游 |
| QQ bridge 状态 | `server/qq_bridge/data/` | 忽略；每日/生命维持状态保存日期或槽位及哈希投递标记；专注鼓励状态只保存用户哈希、不透明 focus session、起止时间和有限投递状态。三者均原子替换且有数量上限，不保存完整 OpenID、任务、消息、情报、模型回复或凭证 |
| 依赖/模型/输出 | `node_modules/`、`server/models/`、`server/output/` | 可再生成或体积大；voice 请求暂存位于 `output/.voice_tmp/`，完整输出位于 `output/voice_replies/`，均不得提交 |
| 历史个人状态（已跟踪） | `server/data/affection_state.json`、`focus_timer.json`、`memories.json`，以及 `server/systems/data/focus_timer.json` | 仓库历史目前已跟踪；它们仍是用户数据，未经明确授权不得重置、输出，或把无关改动一并提交。focus 模块继续关联既有 `systems/data` 路径且不自动合并同名文件；若要迁移为仅本地文件，必须单独确认。 |
| 健身打卡状态（已跟踪） | `server/data/fitness_checkins.json` | 用户个人数据；fitness repository 独占读写，生产显式使用此路径，不创建或迁移 `server/systems/data` 候选。不得用真实文件做测试、reset、损坏复现、迁移、输出或 diff。 |
| 日历与修炼状态 | `server/systems/data/calendar_memo.json` | 用户个人数据；calendar repository 独占读写，迁移不改变路径。不得用真实文件做测试、reset、损坏复现、迁移或 diff 展示。 |
| 斩妖除魔状态 | `server/systems/data/demon_slayer.json` | 用户个人数据；demon_slayer repository 独占读写，迁移不改变路径。删除目标保留历史；不得读取、输出、reset、损坏测试、迁移或 diff 真实文件。 |

如果出现未知的 `.env`、Cookie、Token、缓存或大型 vendor 文件，默认不要读取、打印、暂存或上传。

## 常用 API

| 目的 | 路由 |
|---|---|
| 服务状态 | `GET /dashboard/status` |
| 受控重启 Core | `GET /api/v1/dashboard/service/restart/status`（loopback 只读；无 Origin 可用）、`POST /api/v1/dashboard/service/restart`（精确同源 Origin + 二次确认） |
| 模块目录与任务映射 | `GET /api/v1/modules`（只读，不访问外网或个人状态） |
| 官方模块目录 | `GET /api/v1/modules/official-catalog`（只读本地缓存）、`POST /api/v1/modules/official-catalog/refresh`（显式联网刷新；可选固定 `download_source=auto\|github\|gitee`） |
| 安装/更新/回滚官方模块 | `POST /api/v1/modules/{module_id}/install-official`、`/update-official`、`/rollback-official`（精确版本确认；安装/更新可选固定下载来源；回滚只用已验证本地版本） |
| 安装本地模块包 | `POST /api/v1/modules/install-upload`（正式控制台入口；从已验证 manifest 自动识别 ID，可选 `expected_module_id` 额外核对；原始 `application/zip` + `X-Project-Kei-Package-SHA256`）、`POST /api/v1/modules/{module_id}/install-upload`（legacy 兼容路径）、`POST /api/v1/modules/{module_id}/install`（维护者本机路径接口） |
| 启用/停用模块 | `POST /api/v1/modules/{module_id}/enable`、`/disable`（仅本机） |
| 升级/回滚模块 | `POST /api/v1/modules/{module_id}/update`、`/rollback`（仅本机） |
| 检查模块配置 | `POST /api/v1/modules/{module_id}/configuration/check`（仅本机，只返回缺少字段，不返回配置值） |
| 卸载/清除模块数据 | `DELETE /api/v1/modules/{module_id}`、`POST /api/v1/modules/{module_id}/purge-data`（仅本机；后者需精确确认） |
| QQ 本机配置 | `GET /api/v1/qq-control/configuration`（只返回配置状态和脱敏 AppID）、`POST /api/v1/qq-control/configuration`（显式保存；Secret 不回显） |
| QQ 进程控制 | `GET /api/v1/qq-control/status`、`POST /api/v1/qq-control/start`、`POST /api/v1/qq-control/stop`（stop 仅关闭当前 adapter 持有的进程） |
| ASR 模型目录选择 | `GET /api/v1/voice-control/asr/model-directory/status`、`POST /api/v1/voice-control/asr/model-directory/select`（空 body；路径由本机选择器处理） |
| ASR/TTS 进程控制 | `GET /api/v1/voice-control/status`、`POST /api/v1/voice-control/asr/start|stop`、`POST /api/v1/voice-control/gpt-sovits/start|stop`（stop 仅关闭当前 Core 持有的进程组） |
| GPT-SoVITS 引擎目录选择 | `GET /api/v1/gpt-sovits-engine/status`、`POST /api/v1/gpt-sovits-engine/select-existing`（空 body；路径由本机选择器处理） |
| 专注计时（版本化） | `GET /api/v1/focus/status`、`POST /api/v1/focus/start`、`/stop`、`/reset`、`/encouragement`（鼓励仅真实 loopback、固定目的、精确 active session 校验且不写 conversation history；仅在 focus 1.1.1 已安装、启用并重启 API 后装配） |
| 专注计时（兼容） | `GET /focus/status`、`POST /focus/start`、`/stop`、`/reset`（与版本化接口调用同一 service） |
| 日历与修炼（版本化） | `GET /api/v1/calendar/today`、`/status`，`POST /api/v1/calendar/events`、`/practice`、`/reset`（reset 精确确认 `calendar`） |
| 日历与修炼（兼容） | `GET /calendar/today`、`/status`，`POST /calendar/event`、`/practice`、`/reset`（与版本化接口调用同一 service；旧 reset 未在控制台暴露） |
| 健身打卡（版本化） | `GET /api/v1/fitness/status`、`POST /api/v1/fitness/checkins`（纯业务 JSON，不触发 TTS） |
| 健身打卡（兼容） | `GET /fitness/status`、`POST /fitness/checkin`、`POST /fitness/reset`（共用版本化 service；reset 为危险 legacy 接口，奖励音频仅在 `with_audio=true` 时显式尝试） |
| QQ bridge 状态/启动（版本化） | `GET /api/v1/qq-control/status`、`POST /api/v1/qq-control/start`（共用已安装模块的受信 sidecar adapter；不接受任意命令/路径，start 要求真实 loopback + 受信 Origin） |
| QQ bridge 状态/启动（兼容） | `GET /dashboard/qq-bridge/status`、`POST /dashboard/qq-bridge/start`（委托同一 service） |
| 每日情报（版本化只读） | `GET /api/v1/briefing/today`、`GET /api/v1/briefing/today/script`、`GET /api/v1/briefing/generation-status`（不采集、不改写、不合成、不写缓存） |
| 每日情报（版本化生成） | `POST /api/v1/briefing/generate`、`POST /api/v1/briefing/refresh`（仅本机；后者明确强制覆盖） |
| 每日生活预报 | `GET /api/v1/life-forecast/today`、`GET/PUT /api/v1/life-forecast/config`、`POST /api/v1/life-forecast/refresh`（仅 refresh 访问固定上游；需安装、启用并重启） |
| 每日情报（兼容） | `GET /briefing/today`、`POST /briefing/today/voice`；默认 `fetch=false`，定时预生成须显式 `fetch=true` |
| 控制台情报状态/生成 | `GET /dashboard/briefing/status`、`POST /dashboard/briefing/generate`；强制重建使用确认后的 `refresh=true` |
| 情报来源名单（版本化） | `GET` / `PUT /api/v1/intel-sources`，以及单条 `POST /{field}`、`PUT` / `DELETE /{field}/{index}`（仅本机控制台） |
| 情报来源名单（兼容） | `GET` / `PUT /dashboard/intel-sources`（委托同一 registry） |
| 读取/刷新 X 显示资料 | `GET /api/v1/x/profiles`（只读缓存）、`POST /api/v1/x/profiles/resolve`（显式查询）；兼容 `/dashboard/intel-sources/x-profiles/resolve` |
| 读取/获取/查询 X 言论 | `GET /api/v1/x/posts`、`POST /api/v1/x/posts/fetch?username=...`、`POST /api/v1/x/posts/query`；query JSON 使用 `mode=day|since` 与 `date=YYYY-MM-DD`，保留 dashboard posts 兼容路径，不提供独立 replies API |
| 查询/刷新 B 站昵称头像 | `GET /api/v1/bilibili/profiles`、`POST /api/v1/bilibili/profiles/resolve`；保留 dashboard 兼容路径 |
| 维护/验证 B 站采集参数 | `GET /api/v1/bilibili/credentials/status`、`PUT /api/v1/bilibili/credentials`、`POST /api/v1/bilibili/credentials/validate-and-collect`；dashboard legacy 路径委托同一 service |
| 定时情报设置（版本化） | `GET/PUT /api/v1/qq-control/schedules/daily-briefing`（PUT 要求真实 loopback + 受信 Origin） |
| 生命维持设置（版本化） | `GET/PUT /api/v1/qq-control/schedules/life-support`（PUT 要求真实 loopback + 受信 Origin） |
| QQ 日程设置（兼容） | `GET/PUT /dashboard/briefing/schedule`、`GET/PUT /dashboard/life-support/schedule`（委托同一 repository/service） |
| LLM 方案 | `GET` / `PUT /dashboard/llm/profile`（仅本机） |
| 文字对话（版本化） | `POST /api/v1/conversation`（仅文字，不触发 TTS） |
| 对话 history（版本化） | `GET` / `DELETE /api/v1/conversation/history`（只影响当前进程内 history） |
| LLM 方案（版本化） | `GET` / `PUT /api/v1/llm-profile`（仅本机；PUT 会测试候选并原子应用） |
| 好感度（版本化） | `GET /api/v1/relationship/status`、`POST /api/v1/relationship/events`、`POST /api/v1/relationship/choices` |
| 长期记忆（版本化） | `GET/POST /api/v1/memories`、`DELETE /api/v1/memories/{memory_id}` |
| 好感度与记忆（兼容） | `/affection/status|event|choose|reset`、`GET/POST /memories`、`DELETE /memories/{memory_id}`、`POST /memories/clear`（共用版本化 service；reset/clear 为危险 legacy 接口） |
| 语音健康与能力 | `GET /api/v1/voice/health`、兼容 `GET /voice/health` |
| 语音对话（版本化） | `POST /api/v1/voice/chat`、`POST /api/v1/voice/chat/stream`、`GET /api/v1/voice/audio/{filename}` |
| 已生成文字的单次语音合成 | `POST /api/v1/voice/synthesize`（固定 `qq_reply` → `qq_c2c_voice_v1`/`audio/silk`；无 legacy 别名） |
| 语音对话（兼容） | `POST /voice/chat`、`POST /voice/chat/stream`、`GET /voice/audio/{filename}`（与版本化入口共用 service） |
| Voice Pack 列表/导入 | `GET /api/v1/voice-packs`、`POST /api/v1/voice-packs/import`（导入仅本机，响应脱敏） |
| Voice Pack 启用/选择/停用/注销 | `POST /api/v1/voice-packs/{id}/{version}/enable`、`/select`、`/disable`，`DELETE /api/v1/voice-packs/{id}/{version}`（写操作仅本机；注销不删源资产） |
| 斩妖目标（版本化） | `GET /api/v1/demon-slayer/status`、`GET/POST /api/v1/demon-slayer/goals`、`PATCH/DELETE /api/v1/demon-slayer/goals/{goal_id}`、`POST /api/v1/demon-slayer/checkins` |
| 斩妖奖励与复盘（版本化） | `POST /api/v1/demon-slayer/rewards`、`POST /api/v1/demon-slayer/rewards/{reward_id}/redeem`、`GET /api/v1/demon-slayer/reviews/{daily|weekly|monthly|yearly}` |
| 斩妖除魔（兼容） | `GET /demon/status`、`POST /demon/plan`、`DELETE /demon/goals/{goal_id}`、`POST /demon/checkin`、`GET /demon/reminder`、`GET /demon/review/*`、`POST /demon/wish`、`/redeem`、`/reset`（全部委托同一 service；危险 reset 不在控制台暴露） |
| QQ 文字消费 | bridge 主路径为 `POST /api/v1/conversation`；`POST /chat/text-only` 仅兼容 |

除非任务明确要求，不要在调试时调用会触发真实采集、TTS、QQ 发信或模型付费请求的接口。

## 验证与测试

先用 `setup.bat --profile dev` 安装锁定的开发依赖。以下命令均从仓库根目录执行；
默认 pytest 会完整发现已分类的离线回归，不访问外部网络、真实本机服务、模型、
凭据或个人状态。机器清单与 pytest 收集前门禁还会拒绝任何必需参数既不是合法
fixture、也未由 literal `parametrize` 提供的新增 `check_*`：

```powershell
.\scripts\python.ps1 ..\scripts\check_python_test_inventory.py
.\scripts\python.ps1 -m pytest tests --collect-only -q
.\scripts\python.ps1 -m pytest tests
.\scripts\python.ps1 -m ruff check tests ..\scripts\check_python_test_inventory.py
```

真实网络、模型、硬件和运行中服务诊断不会进入默认 pytest；逐项隔离理由与显式
运行边界见 [Python 测试与质量基线](docs/architecture/python-test-quality.md)。
迁移期仍保留安全测试脚本的历史单文件 `main()` 入口。需要定向复验时，在
`server/` 目录下通过统一解析器选择根 `.venv` 或受支持的迁移期解释器：

```powershell
# 新的情报来源管理
..\scripts\python.ps1 tests\test_intel_source_config.py
..\scripts\python.ps1 tests\test_intel_sources_registry.py
..\scripts\python.ps1 tests\test_x_monitor.py
..\scripts\python.ps1 tests\test_bilibili_collector.py
..\scripts\python.ps1 tests\test_bilibili_feature.py
..\scripts\python.ps1 tests\test_bilibili_credentials.py
..\scripts\python.ps1 tests\test_youtube_collector.py
..\scripts\python.ps1 tests\test_github_intel_collector.py
..\scripts\python.ps1 tests\test_papers_collectors.py
..\scripts\python.ps1 tests\test_rss_intel_collector.py
..\scripts\python.ps1 tests\test_intel_sources_integration.py

# PK-110 Collector/汇总/去重/缓存/补采/改写/语音/API（全 fake、固定时钟、临时目录）
..\scripts\python.ps1 tests\test_daily_briefing_module.py

# PK-110 进程内生成阶段、来源进度、失败/取消与只读状态 API（全 fake、临时目录）
..\scripts\python.ps1 tests\test_daily_briefing_generation_status.py
node tests\test_dashboard_briefing_progress.mjs

# PK-240 天气 Provider、跨日/DST、原子缓存、并发、隐私、动态包（全 fake/MockTransport/临时目录）
..\scripts\python.ps1 -m pytest tests\test_life_forecast_module.py -q

# 当天 Kei 播报稿分离缓存与旧 Schema 只读兼容（临时目录）
..\scripts\python.ps1 tests\test_daily_briefing_summary_cache.py

# 模块目录与项目任务映射
..\scripts\python.ps1 tests\test_feature_catalog.py

# conversation、profile 原子热切换与现有文本消费者（全 fake/MockTransport/临时 profile）
..\scripts\python.ps1 tests\test_conversation_module.py
..\scripts\python.ps1 tests\test_llm_profile.py
..\scripts\python.ps1 tests\test_conversation_consumers.py

# voice Provider、同步/流式、降级、上传限制、并发与临时文件生命周期（全 fake/临时目录）
..\scripts\python.ps1 tests\test_voice_module.py

# GPT-SoVITS 固定描述、Provider、假 9880、假下载/摘要/归档、回滚和不执行脚本
..\scripts\python.ps1 tests\test_gpt_sovits_provider.py

# GPT-SoVITS 单实例共享引擎会话、两阶段取消/失败回滚、并发合成/选择与 close 竞态
..\scripts\python.ps1 tests\test_gpt_sovits_engine_sessions.py

# Voice Pack Schema、假资产导入、路径/链接/摘要拒绝、原子注册、切换回滚和 API 脱敏
..\scripts\python.ps1 tests\test_voice_pack_registry.py

# Voice Pack 本机/Origin 双重写保护、恶意 Origin、无 Origin 兼容和 CORS 预检阻断
..\scripts\python.ps1 tests\test_voice_pack_origin_guard.py

# PK-213 可信 catalog、fake HTTPS、ZIP 安全、PK-212 接缝和确定性构建
..\scripts\python.ps1 tests\test_voice_pack_distribution.py

# 控制台公共外壳、同源请求、模块过滤、失败隔离与静态资源边界
..\scripts\python.ps1 tests\test_dashboard_shell.py

# 本地模块 manifest、安装、升级、回滚、启停、卸载与安全边界
..\scripts\python.ps1 tests\test_installable_modules.py

# 已完成/待集成任务的文档门禁
..\scripts\python.ps1 ..\scripts\check_task_docs.py

# 既有个人系统示例
..\scripts\python.ps1 tests\test_affection_system.py
..\scripts\python.ps1 tests\test_memory_system.py
..\scripts\python.ps1 tests\test_affection_memory_module.py
..\scripts\python.ps1 tests\test_demon_slayer.py
..\scripts\python.ps1 tests\test_demon_slayer_hierarchy.py
..\scripts\python.ps1 tests\test_demon_slayer_module.py
..\scripts\python.ps1 tests\test_demon_slayer_statistics.py
..\scripts\python.ps1 tests\test_demon_slayer_dashboard.py
..\scripts\python.ps1 tests\test_demon_checkin_feedback.py
..\scripts\python.ps1 tests\test_demon_review_kei.py
..\scripts\python.ps1 tests\test_fitness_checkin.py
..\scripts\python.ps1 tests\test_fitness_module.py
..\scripts\python.ps1 tests\test_focus_timer.py
..\scripts\python.ps1 tests\test_focus_module.py
..\scripts\python.ps1 tests\test_focus_dashboard.py
..\scripts\python.ps1 tests\test_calendar_memo.py
..\scripts\python.ps1 tests\test_calendar_module.py
..\scripts\python.ps1 tests\test_voice_calendar_intents.py

# Python 语法检查
..\scripts\python.ps1 -m compileall -q core\modules features\module_manager features\catalog api.py

# QQ control 与 sidecar（fake process/HTTP/WebSocket/clock/timer、临时目录）
..\scripts\python.ps1 tests\test_qq_control.py
Set-Location qq_bridge
node --test tests/*.test.mjs
Get-ChildItem -LiteralPath src -Filter *.mjs | ForEach-Object { node --check $_.FullName }
```

页面脚本变更后，至少做 JavaScript 语法检查；Python/Node 变更后，至少做对应编译或定向测试。不要宣称未执行过的验证。

## Git、文档与交接规则

本仓库可能是脏工作区，`vendor/` 是外部参考资源，默认不纳入功能提交。禁止用 `git reset --hard`、`git checkout --` 或 blanket `git add -A` 清除/覆盖用户改动。

每次准备 `git add`、`git commit`、`git push` 或创建 PR 之前，执行以下文档门禁：

1. 对照实际 diff 列出本次新增、修改和删除的用户可见功能；
2. **主动更新本 README**：功能状态、入口、启动/重启方式、配置、数据副作用、验证命令或已知限制发生变化时必须同步，不等待用户提醒；
3. 如果本机绝对路径、环境位置或服务启动点变化，更新 `README.local.md`，但绝不提交它；
4. 如果协作流程/安全规则变化，更新 `AGENTS.md`；
5. 运行与改动相称的验证和 `git diff --check`；
6. 只显式暂存经确认的相关路径，二次确认没有 `.env`、缓存、`node_modules`、模型、运行状态或 `vendor/` 混入。

这不是可选的文档建议，而是后续 agent 的提交前完成条件。完整操作规范见 [AGENTS.md](AGENTS.md)。

## 当前后续方向

- 按 `TASKS.md` 逐项把 `server/api.py` 中的业务路由迁入 `server/features/<module>/`，每次保留旧接口兼容并单独验收；
- 由 `PK-900`/总控集成验收 PK-180 的 focus 端到端安装试点，再按独立任务复用机制迁移其他业务；
- 将 arXiv 主题/关键词、RSS 地址等高级情报搜索规则做成第二层可视化配置；
- 继续提高每日情报源的可靠性和失败可见性；
- 在不破坏现有本地服务的前提下推进树莓派、移动机器人和实体外壳；
- 任何扩展都应先检查实际文件、最小化改动、保留既有功能，并在完成后更新本文档。

## 控制台聚合卡与 QQ 配置说明

- 情报来源、语音与 Voice Pack 等聚合模块在收起时与普通模块一样显示为小方块；
  只有展开后才占据整行。聚合关系仅属于控制台展示，不合并各模块的安装、启停、
  卸载、接口或数据所有权。
- QQ bridge 是一个 sidecar 安装单元，但控制台分别展示“QQ 功能启动”“每日情报
  定时推送”和“生命维持系统”三个小模块卡，分别使用既有图片并独立展开/收起。
- 若尚未配置 QQ，面板会引导用户前往 [QQ 开放平台](https://q.qq.com/) 创建机器人，
  再按 `server/qq_bridge/.env.example` 的字段名填写本机
  `server/qq_bridge/.env`。页面只显示配置是否存在，绝不回显秘密。
- 若本机已有 `server/qq_bridge/.env`，更新或重装模块会继续复用它，不要求重新填写。
  QQ 依赖需在项目根目录显式执行 `setup.bat --profile qq`；安装模块或打开页面不会
  静默运行 npm、启动 sidecar 或发送消息。
## 控制台紧凑模块卡与 QQ 本机配置（2026-08-01）

- 已安装模块默认以三列小卡片显示；点击“展开详情”后，该卡片才占满整行。升级后浏览器会执行一次仅限 `localStorage` 的布局迁移，把旧版本遗留的展开状态收起，不调用任何业务 API。
- `qq_bridge` 是一个安装/进程单元，但控制台按用途显示为三个独立卡片：QQ 功能启动、每日情报定时推送、生命维持系统；三项分别保留独立图片、折叠状态和操作区。
- QQ 配置入口指向 [QQ 开放平台](https://q.qq.com/)。已有 `server/qq_bridge/.env` 会继续原地复用；控制台只显示非秘密的“已配置/未配置”状态，不显示凭证值。新用户按 `server/qq_bridge/.env.example` 在本机填写字段。
- 本地候选包已修复为 `qq_bridge@0.1.5`。更新后必须关闭旧 Core 窗口并重新运行根目录 `start.bat`，再在浏览器按 `Ctrl+F5`，使新动态入口和 `/api/v1/qq-control/*` 装配生效。
