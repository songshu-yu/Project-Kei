# Project Kei ASR 部署说明

ASR 是显式可选组件。Core 不依赖 ASR、模型、CUDA、GPT-SoVITS 或 Voice Pack；没有这些组件时仍可安装并启动。

## 安装公开依赖

在项目根目录运行：

```powershell
.\setup.bat --profile voice
.\doctor.bat --profile voice
```

`voice` profile 在根 `.venv` 中安装 Core 和 `requirements/asr-win.lock.txt` 的公共依赖。它不会创建或重建 `server/.venv-asr`，不会下载模型、引擎或参考音频，也不会扫描磁盘寻找这些资产。

支持 Python `>=3.10,<3.14` x64，即 3.10、3.11、3.12、3.13；推荐和主回归
版本为 Python 3.11。迁移期已有的 `server/.venv-asr` 只有在真实版本和架构
探针通过时才会成为解释器候选；新安装始终以根 `.venv` 为目标。

## 配置和启动

为了让双击 `server/start_all_services.bat` 也能启动 ASR，启动器按以下顺序
解析已有本机模型：

1. 当前 PowerShell 中显式设置的 `ASR_MODEL_PATH`；
2. 本机 `server/.env` 中的 `ASR_MODEL_PATH`；
3. 项目内固定目录 `server/models/asr/medium`；
4. 项目内固定目录 `server/models/asr/small`。

后两项用于兼容旧版 Project Kei 的本地模型布局，只检查目录是否存在，不递归
枚举内容、不扫描其他磁盘、不下载模型，也不输出解析后的实际路径。模型位于其他
目录时，推荐只在本机 `server/.env` 中填写以下三个字段；启动器只导入这三个
非秘密 ASR 字段：

```dotenv
ASR_MODEL_PATH=<existing-local-model>
ASR_DEVICE=cpu
ASR_COMPUTE_TYPE=int8
```

当前 PowerShell 中已经显式设置的同名变量优先于 `.env`。临时测试也可以只在
当前窗口设置 `$env:ASR_MODEL_PATH` 后运行 `.\start.bat --profile voice`。
`.env` 中的 LLM Key、Cookie、Token 和其他字段不会由启动器导入或输出。

如已由用户自行准备兼容的 CUDA 环境，可以显式调整 `ASR_DEVICE` 和 `ASR_COMPUTE_TYPE`；CUDA、驱动及 GPU 专用依赖不属于 PK-020 的安装锁。启动器固定设置 `ASR_LOCAL_FILES_ONLY=true`，因此不会在启动时下载模型。

语音 profile 会逐项尝试：

- ASR：`127.0.0.1:8010`，仅在显式路径或上述项目标准目录可用且端口空闲时启动。
- GPT-SoVITS：`127.0.0.1:9880`，仅使用 PK-211 的本机登记和受控启动器。
- Core：`127.0.0.1:8000`，始终是主进程；可选组件缺失不阻止 Core。

Core 与 ASR 都只绑定 loopback，不提供静默的局域网监听回退。本机 dashboard、
QQ sidecar 和语音 Provider 继续使用 `127.0.0.1`。

按对应控制台窗口中的 `Ctrl+C` 停止进程。`start` 不运行 pip、不下载模型、不修改 `.env`。

## 只读诊断

```powershell
.\doctor.bat --profile voice
```

doctor 只报告依赖导入、端口、当前 PowerShell 的 `ASR_MODEL_PATH` 是否设置、
两个固定项目模型目录是否存在，以及 GPT-SoVITS/Voice Pack 的脱敏登记状态。
为保持 doctor 不读取 `.env` 内容，它不会验证 `.env` 中的模型字段；该字段由
实际 voice/all 启动器按上述白名单加载。doctor 不读取模型目录内容、路径值或
注册表内容，不递归枚举、不连接 8010/9880，也不触发 ASR/TTS。

## 隔离上传测试

只有在用户已显式启动测试 ASR、且使用测试音频时，才从项目根运行：

```powershell
.\scripts\python.ps1 tests\test_asr_upload.py --file "<test-audio>"
```

树莓派客户端是独立部署面；其依赖不由 Windows `core|voice|qq|full|dev` profile 安装。
