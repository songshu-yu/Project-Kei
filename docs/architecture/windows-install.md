# Windows 安装、依赖锁与启动架构

## 边界

PK-020 提供 Windows 10/11 x64 的项目级安装、只读诊断和启动编排，不改变业务 API、模块生命周期或 Provider 契约。Core 是默认且唯一必装/必启集合；QQ、ASR、GPT-SoVITS 和 Voice Pack 始终是显式可选能力。

外部资产所有权不变：

- QQ 凭证、Gateway 和业务规则归 PK-140；PK-020 只使用既有 Node lock 和启动 preflight。
- GPT-SoVITS 来源、获取、校验和登记归 PK-211；PK-020 只调用其登记式启动器。
- Voice Pack 导入、注册和切换归 PK-212；PK-020 只报告脱敏的“注册表是否存在”。
- Voice Pack 发布、可信远程获取和一键安装归 PK-213；PK-020 只提供受支持
  Python 环境和可选语音安装提示，不复制下载器、catalog 或包校验规则。
- ASR 锁只包含公共 Python 依赖，不包含模型、CUDA/GPU 偶然依赖或外部引擎。
- `pi_client` 是独立设备部署，不属于任一 Windows profile。

## 公开入口

| 入口 | 默认 | 可选值 | 写入/进程语义 |
|---|---|---|---|
| `setup.bat` → `scripts/setup.ps1` | `core` | `core|voice|qq|full|dev` | 可创建根 `.venv`、安装锁定公开依赖；不写配置、不下载资产、不启动服务 |
| `doctor.bat` → `scripts/doctor.ps1` | `core` | 同 setup | 严格只读；只做版本、摘要、导入、端口和非秘密存在性检查 |
| `start.bat` → `scripts/start.ps1` | `core` | `core|voice|qq|all`，可加 `--no-browser` | 只做 preflight 后启动；Core 就绪后默认打开本地控制台；不运行 pip/npm、不写配置、不下载 |
| `scripts/python.ps1` | 无 | Python 参数 | 用同一解析器在 `server/` 工作目录运行维护/测试命令 |

BAT 只从 `%~dp0` 计算位置、完整转发参数和退出码。9 个面向用户的 BAT 在普通
直接运行时都通过 `scripts/project-kei.pause.cmd` 显示最终结果并等待按键；
pause 前保存的原退出码在等待后保持不变。CI、测试、计划任务及 BAT→BAT 内部
委托显式设置 `PROJECT_KEI_NO_PAUSE=1`，所以不会挂起或重复 pause；最外层兼容
入口恢复调用方设置后只暂停一次。该变量不参与业务参数解析，也不会被传给
PowerShell 或业务进程。既有 `server/start_*.bat`、`server/scripts/start_*.ps1`、
`server/qq_bridge/start_qq_bridge.bat` 和每日情报预构建 BAT 仍是兼容薄层，
不保存另一套路径或安装规则。

## 运行时解析

PowerShell 公共层为 `scripts/project-kei.common.ps1`。Python 候选按以下顺序逐个验证版本和 x64 架构：

1. 根 `.venv\Scripts\python.exe`；
2. 迁移期 `server\.venv-asr\Scripts\python.exe`；
3. Windows `py` launcher 的 3.11、3.13、3.12、3.10 x64；
4. PATH 中的 `python`；
5. 全部失败时返回从 python.org 安装 Python 3.10、3.11、3.12 或 3.13 x64
   （推荐 3.11）的明确提示。

新安装只创建根 `.venv`。已有 `server/.venv-asr` 既不删除、重建，也不作为新安装目标。已有根 `.venv` 若不完整、版本不受支持或不是 x64，setup 会失败关闭并要求用户手工移开；不会自动清理。

Node 只接受 20.x、22.x、24.x、26.x x64，推荐 Node 24 LTS；20.x 只保留旧环境
兼容。只有 `qq|full` setup 和 `qq|full` doctor 将 Node/npm 缺失视为 profile
阻断。`package.json`、lockfile 与 QQ 模块 manifest 表达相同边界。

## 依赖分层

`requirements/` 是唯一 Python 版本事实：

- `core.in` / `core-win.lock.txt`：Core 直接依赖与完整解析锁。
- `asr.in` / `asr-win.lock.txt`：相对 Core 的 ASR 附加层。
- `voice-media.in` / `voice-media-win.lock.txt`：仅用于 `voice|full` 的 Windows
  CPython x64 媒体层；固定 `silk-python==0.2.8`、其二进制依赖
  `cffi==1.17.1` 和纯 Python 依赖 `pycparser==2.22`，逐 Python 3.10–3.13 wheel
  SHA-256，并以 `--require-hashes --only-binary=:all:` 安装。
- `dev.in` / `dev-win.lock.txt`：相对 Core 的测试、静态检查和锁工具。
- `lock-manifest.json`：四份锁文件内容的 SHA-256；setup/doctor 在 pip 前校验。

每个非注释锁行都是精确版本（Python marker 除外），不含 editable、本机路径、`file://`、私有源、凭证、本机 wheel、引擎、模型或 GPU 专用包。`server/requirements*.txt` 只是指向根权威锁的兼容入口。

Node 依赖只由受版本控制的 `package-lock.json` 固定。源码树兼容安装和已安装的
QQ 模块都由显式 `setup.bat --profile qq` 执行 `npm ci --ignore-scripts`；本地 ZIP
与官方 Release 使用同一受控依赖部署根和摘要校验。模块上传、普通 start 和控制台
启动接缝永不调用 npm。

锁更新只能在显式 dev 工作流中进行：从干净的 Python 3.11 x64 环境安装 `dev`
工具，分别由 `.in` 重新解析 Windows 锁，审阅无本机/私有来源后更新
`lock-manifest.json`，再在 Python 3.10/3.11/3.12/3.13 x64 无缓存 Windows CI
中验证 Core、ASR、dev 三层的真实安装和导入。不得用 `pip freeze`、当前
`.venv-asr` 或开发机 `node_modules` 生成正式锁。

## Profile

| profile | Python 层 | Node | 资产 |
|---|---|---|---|
| `core` | Core | 无 | 无 |
| `voice` | Core + ASR + voice-media | 无 | 仅 preflight，不获取模型/引擎/Pack |
| `qq` | Core | `npm ci` | 不创建/读取 `.env` |
| `full` | Core + ASR + voice-media | `npm ci` | 仍不获取资产 |
| `dev` | Core + dev | 无 | 不隐式包含 voice/qq |

安装顺序固定为平台/工具检查 → 根 `.venv` 创建或复用 → 锁摘要校验 → pip 锁安装 →（按需）Node/npm 校验和 `npm ci` → 包导入检查。任何失败都保留已有环境和用户文件。

PK-213 已增加独立 `voice-pack.bat` / `voice-pack-build.bat`，继续使用本节的
Python 解析器和 BAT 暂留约定。`voice`/`full` setup 仍只安装公开依赖，不调用
Voice Pack CLI、不代替用户确认，也不把资产下载混入 Python 安装。当前内置
catalog 没有真实 Kei Release，公开安装器不得声称真实 Pack 已可远程获取。

start 的有限 preflight 除版本外还检查所选环境的 Core `fastapi/uvicorn`，ASR
显式启动还检查 `faster_whisper`。`.venv` 目录存在但依赖不完整时，以退出码 21
在启动进程前停止并指向对应 setup/doctor；`all` 映射到安装/诊断 profile
`full`。Core 的依赖与 8000 端口 preflight 必须先于任何 GPT-SoVITS、ASR 或
QQ 子进程创建，失败时保持所有可选服务未启动。start 不自行运行 pip。

Core 固定绑定 `127.0.0.1:8000`，ASR 固定绑定 `127.0.0.1:8010`；统一启动器、
兼容 BAT/PowerShell 与 Python 直接入口都没有 `0.0.0.0` 或局域网静默回退。
普通交互启动会在 Core 的 `http://127.0.0.1:8000/dashboard` 通过最多 30 秒的
本地、禁代理只读就绪检查后，用系统默认浏览器打开控制台；浏览器调度失败不影响
Core。`--no-browser` 或 `PROJECT_KEI_NO_BROWSER=1` 可显式关闭该行为，供 CI、
测试、计划任务和后台运行使用。legacy `server/start_all_services.bat` 继续只
委托统一 `start.bat --profile all`，不维护第二套浏览器或服务启动规则。

## 失败语义

| 退出码 | 类别 | 语义 |
|---|---|---|
| `2` | arguments | 未知参数/profile |
| `10` | platform | Windows/PowerShell 不受支持 |
| `11` | python | Python 缺失、不兼容或 `.venv` 创建/验证失败 |
| `12` | lock | 锁或 manifest 缺失、损坏、摘要不匹配 |
| `13` | pip | 锁定 Python 依赖安装失败 |
| `14` | node/npm | Node/npm 不受支持或 `npm ci` 失败 |
| `15` | health | 安装后包导入失败 |
| `20` | start runtime | 启动时无受支持 Python |
| `21` | optional preflight | 显式单组件启动缺配置/依赖 |
| `22` | port | 目标端口被占用 |

doctor 对选中 profile 的必需项返回 `error` 并以 1 退出；可选资产缺失和端口占用为 `warn`，Core doctor 不因可选能力缺失失败。输出统一使用 `[ok]`、`[warn]`、`[error]`。

`voice|full` 的 voice-media 检查严格只读：校验 lock manifest 后，只在已解析的
CPython x64 运行时核对 distribution version 为 `0.2.8`、导入 `pysilk`，并确认
`encode` capability 可调用；不会调用 encoder、写配置/缓存、下载或启动服务。
缺失、错版或 capability 不完整会把所选语音 profile 判为 unavailable，但不影响
`core|qq` 的安装、doctor 或 Core 启动。安装失败统一保留既有环境，并明确区分为
锁/平台门禁或 `voice_media_install_failed`，绝不回退源码包和未锁 wheel。

## 启动进程

Core API 在当前窗口前台运行，8000 被占用时拒绝启动且不终止所有者。`voice|all` 仅在固定端口空闲且公开 preflight 通过时为 ASR/GPT-SoVITS 打开独立窗口；任一缺失不会阻止 Core。ASR 先使用显式 `ASR_MODEL_PATH`；未配置时只按顺序检查项目内固定的 `server/models/asr/medium` 与 `server/models/asr/small`。启动器不显示解析后的路径、不递归扫描磁盘，并强制 `ASR_LOCAL_FILES_ONLY=true`。GPT-SoVITS 仍使用 PK-211 登记的仓库外运行时。

主 API 在路由和业务 I/O 之前安装最外层 `LoopbackAccessMiddleware`。HTTP、
静态控制台和 WebSocket 都只接受底层 ASGI `client` 提供的 IPv4
`127.0.0.0/8` 或 IPv6 `::1`；缺失或无法解析的客户端地址失败关闭。
`Host`、`Origin`、`X-Forwarded-For` 和 `Forwarded` 都不能替代连接对端身份。
HTTP 以 403 和固定“仅允许本机访问”拒绝，WebSocket 在接受握手前以 1008
关闭。模块已有 guard 保留作纵深防御。

CORS 仅允许 `http://127.0.0.1:8000`、`http://localhost:8000` 和
`http://[::1]:8000`，`allow_credentials=false`；不允许通配、`null`、LAN
Origin 或任意 HTTPS Origin。无 Origin 的 loopback CLI、QQ sidecar 与 Provider
保持可用；带恶意 Origin 的 loopback 请求不会获得跨域授权。非 loopback 的
OPTIONS 预检同样先被全局边界拒绝。本版本没有 LAN 模式；未来若需要，必须另立
显式高风险契约，不能改变默认安装和启动行为。

`qq|all` 仅在受支持 Node、`node_modules/ws` 和 `.env` 存在时打开 sidecar 窗口；preflight 只检查 `.env` 是否存在，不读取或回显内容。真正由用户显式启动 sidecar 后，QQ 自有代码才按 PK-140 规则读取配置。

完成一次 `setup.bat --profile full` 后，`server/start_all_services.bat` 可作为
一键兼容入口；它仍只委托 `start.bat --profile all`。GPT-SoVITS、ASR、QQ
继续在独立窗口运行，Core 在主窗口前台运行，缺失的可选组件只产生分项警告，
不会形成第二套安装、路径或进程规则。

Core-only 启动后，控制台可通过本机同源的
`POST /api/v1/voice-control/asr/start` 与
`POST /api/v1/voice-control/gpt-sovits/start` 分别调用固定的
`server/start_asr.bat`、`server/start_gptsovits.bat`。对应只读状态入口为
`GET /api/v1/voice-control/status`。接口不接收路径、参数或环境变量；非空请求
体、非 loopback 或非可信控制台 Origin 均拒绝。服务以锁和固定端口/已创建进程
防止并发重复启动，且绝不在请求中执行安装、下载或配置写入。

`voice|all` 和显式 ASR 启动会从 `server/.env` 仅导入
`ASR_MODEL_PATH`、`ASR_DEVICE`、`ASR_COMPUTE_TYPE` 三个非秘密字段，且已有进程
环境变量优先。解析器不输出字段值，不导入 LLM/QQ Key、Cookie、Token 或其他
配置；Core-only、QQ-only 和 GPT-SoVITS-only 启动不读取该 ASR 接缝。doctor
继续不读取 `.env` 内容，但会执行相同的两个固定项目目录存在性检查；它不读取
目录内容、不递归枚举、不联网，也不显示实际路径。

## 验证边界

`server/tests/test_windows_install.py` 在临时副本中创建新 `.venv`，通过 fake pip/npm 和临时盘符验证空格、中文、非系统盘、幂等、profile、锁损坏、版本/安装失败、doctor 只读、start 不安装/不写配置及端口占用。测试不使用项目现有环境、配置、模型或 `node_modules`。

Windows CI 使用 Python 3.10、3.11、3.12、3.13 x64 矩阵，并在主版本 3.11
验证 Windows PowerShell 5.1 和 PowerShell 7.4+。独立 QQ 运行时矩阵在 Node
22、24、26 x64 上从空缓存执行锁定安装、测试和语法检查；Node 20 仅作为旧环境
兼容声明，不再作为新的 CI 基线。
`scripts/windows_ci_copy.py` 只读取 `git ls-tree` 返回的相对
路径和对象元数据，先用纯字符串规则拒绝秘密、本机说明、个人状态、缓存、
profile、模型/音频、Voice Pack、QQ runtime、外部引擎、虚拟环境、
`node_modules`、`vendor`、绝对路径与 traversal；只有明确的安装、Core/API、
测试和活动文档表面才能在逐层 `lstat` 证明不是 symlink/reparse 后进入复制。
永久合成 tripwire 证明保护候选不会到达工作树 `lstat`、目标创建或复制 I/O，
链接候选不会到达目标创建或复制 I/O。

隔离副本位于含空格和中文的临时非系统盘。pip 使用 `PIP_NO_CACHE_DIR=1` 与全新
空 cache，npm 使用全新空 cache，`actions/setup-node` 不启用 npm cache。CI
每个 Python 版本执行无缓存 Core/voice（含逐 wheel hash 的 voice-media）/dev 锁安装、doctor、真实导入和
ASGITransport 健康检查；主版本执行首次/二次 Core setup、两种 PowerShell 的
setup/doctor/AST、公开 `setup.bat --profile qq`（其内部执行锁定
`npm ci --ignore-scripts`）、安装专项、Node 测试/语法、兼容回归、路径扫描、
文档门禁和 `git diff --check`。CI 不配置 Secret、不下载模型或外部引擎、不
启动 API 监听或真实 QQ、Collector、LLM、ASR、TTS 及其他业务服务。
## Core 本机 supervisor 与控制台重启契约

根 `start.bat` 委托 `scripts/start.ps1` 完成 runtime 与端口 preflight 后，由
`scripts/supervise_core.py` 持有固定 Core 子进程。supervisor 从自身文件位置解析
项目根，子进程命令固定为当前已验证 Python 的
`-B -m uvicorn api:app --host 127.0.0.1 --port 8000`；它不接受命令行参数，
浏览器也不能提供 command、path、PID、host 或 port。兼容 `--only api` 是前台
直启入口，不创建 supervisor，因此其重启状态必须为 `unavailable`。

每次根启动生成一个 32 位小写 hex session，仅通过子进程环境传递 session id。
控制文件只能位于固定的 `server/runtime/supervisor/<session>/`，公开响应不返回该
目录、解释器路径或 PID。Core 只写固定 `restart_core` 请求；launcher owner 在
响应已返回后才处理请求。重启前先用同一解释器执行固定 import preflight；若失败，
保留当前 Core。停止操作只针对本 supervisor 直接持有的 Core process group，不按
端口、名称或浏览器输入寻找进程；端口未释放时不终止占用者，也不启动替代进程。
replacement 未启动或未通过 loopback 就绪检查时进入 `failed`，不得伪报成功。

重启 scope 固定为 `core`：不会新增启动 root profile 的 ASR、GPT-SoVITS、兼容
QQ、Collector 或模型进程。已启用的 in-process 模块，以及由 Core lifespan 管理的
已启用 module sidecar，属于 Core runtime 组合，会按既有模块生命周期重新装配；
用户显式 profile 创建的独立窗口/进程不在重启 owner 集合中。此边界只披露既有
生命周期，不新增或复制模块启动规则。

控制台接口固定为：

- `POST /api/v1/dashboard/service/restart`：只允许底层 loopback peer、精确受信
  dashboard Origin 和 `Content-Type: application/json`；请求对象必须且只能含
  `{"confirmation":"restart-project-kei-core"}`。返回 202；首次状态为
  `accepted`，并发/重复请求在 `accepted|restarting` 期间返回同一 request id。
- `GET /api/v1/dashboard/service/restart/status`：要求真实 loopback peer；普通同源
  浏览器 GET 缺少 Origin 时允许，若携带 Origin 则必须属于三种精确可信值。
  返回 `available,state,scope,request_id,generation,retry_after_ms,message`。
  无 supervisor 为 200/`unavailable`；POST 无 supervisor 为 503/`unavailable`。
- 状态枚举为 `unavailable|starting|running|accepted|restarting|failed`；确认错误为
  HTTP 400/`confirmation_required`。响应不包含命令、PID、端口所有者、绝对路径、
  环境变量、秘密、个人状态或上游错误体。

只读 GET 不使用 Referer、Host、X-Forwarded-For 或 Forwarded 补充身份；POST
仍同时要求真实 loopback peer 与精确可信 Origin，缺失、`null`、LAN、恶意或重复
Origin 都在 supervisor I/O 前拒绝。PK-100 的交互顺序固定为二次确认、单次 POST、立即禁用重复按钮、按返回的
`retry_after_ms` 轮询；Core 退出期间的连接错误是预期过渡，页面应继续重连 GET。
只有相同 `request_id` 在新 generation 返回 `running` 才显示完成；`failed` 或
`unavailable` 为终态并显示固定本机提示。UI 不得降级为拼接命令、调用兼容 BAT、
传入 PID/路径/端口，或在网络断开时自行启动任何服务。
