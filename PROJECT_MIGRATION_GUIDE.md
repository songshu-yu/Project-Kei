# Project Kei Windows 迁移指南

本指南用于把 Project Kei 的受版本控制代码迁移到另一台 Windows 10/11 x64 电脑、另一 Windows 账户或不同盘符。所有公开入口都从脚本自身位置解析项目根，不要求固定用户名、桌面目录、盘符或调用时的当前目录。

## 1. 先迁移代码，不迁移环境

在新电脑上重新 clone 或复制干净的仓库内容。不要复制或发布以下机器相关产物：

- 根 `.venv`、迁移期 `server/.venv-asr`；
- `server/qq_bridge/node_modules`；
- `.env`、Token、Cookie、QQ Secret、LLM Key、白名单和用户 ID；
- 个人状态、缓存、来源名单和 LLM profile；
- ASR/GPT-SoVITS 模型、参考音频、Voice Pack 注册表；
- 外部 GPT-SoVITS 源码或运行时。

如果确实要保留个人配置或数据，应在所有相关进程停止后，由用户在私有介质上按各功能自己的备份规则处理。不要把它们混进 Git、安装锁或公开迁移包。

## 2. 安装受支持的运行时

- Windows PowerShell 5.1 或 PowerShell 7.4+；
- Python `>=3.10,<3.14` x64（3.10、3.11、3.12、3.13），建议 Python 3.11；
- 只有 QQ profile 需要 Node.js 20.x、22.x 或 24.x x64，建议 Node 22 LTS；
- Git 用于 clone 和后续维护；已有完整 checkout 时，setup 只会提示 Git 缺失。

安装器不会自动下载或替换 Git、PowerShell、Python、Node、CUDA、驱动、引擎或模型。

## 3. 在任意目录完成 Core 安装

路径可位于非系统盘，并可包含空格或中文。从项目根目录运行：

```powershell
.\setup.bat
.\doctor.bat
```

默认 `core` profile 会创建根 `.venv`，校验权威锁并安装 Core。没有 `.env`、QQ、ASR、GPT-SoVITS、Voice Pack 或模型时，这一步仍应成功。

可按需显式安装：

```powershell
.\setup.bat --profile voice
.\setup.bat --profile qq
.\setup.bat --profile full
.\setup.bat --profile dev
```

重复运行同一命令会复用健康的根 `.venv`。安装器不会删除或重建已有环境，不会覆盖配置，不会启动服务。QQ 依赖只通过 `server/qq_bridge/package-lock.json` 和 `npm ci` 安装。

## 4. 人工恢复本机配置

根据需要，从受版本控制的示例人工创建本机文件：

- 主 API：参考 `server/.env.example` 创建 `server/.env`；
- QQ bridge：参考 `server/qq_bridge/.env.example` 创建 `server/qq_bridge/.env`。

setup、doctor 和普通 start 不会创建、复制、迁移、覆盖、打印或验证这些秘密。缺少秘密只会让对应可选能力保持未配置；Core 不受影响。

## 5. 外部语音资产

GPT-SoVITS 获取和已有安装登记只归 PK-211。Voice Pack 导入、注册和切换只归 PK-212。PK-020 不下载、不复制、不扫描这些资产，也不会猜测旧电脑上的目录。

ASR 公开依赖由 `voice` profile 安装；模型由用户另行准备并通过 `ASR_MODEL_PATH` 显式指定。详细说明见 [ASR 部署说明](docs/asr-setup.md)。

## 6. 启动

```powershell
.\start.bat
```

默认只启动 Core API 8000。可选组合必须显式选择：

```powershell
.\start.bat --profile voice
.\start.bat --profile qq
.\start.bat --profile all
```

`start` 不安装依赖、不写 `.env`、不下载资产。可选组件缺失或失败不会终止 Core；端口已被占用时不会替换或结束已有进程。按每个控制台窗口中的 `Ctrl+C` 停止相应进程。

旧名称 `server/start_api.bat`、`server/start_asr.bat`、`server/start_gptsovits.bat`、`server/start_all_services.bat` 和 `server/qq_bridge/start_qq_bridge.bat` 仍保留，但都委托统一解析逻辑。

## 7. 故障诊断

```powershell
.\doctor.bat
.\doctor.bat --profile voice
.\doctor.bat --profile qq
```

doctor 是只读检查：不会安装、写配置、下载、启动业务进程或连接业务网络。常见稳定错误包括：

- `python`：未找到 Python 3.10–3.13 x64；从 python.org 安装任一受支持的
  x64 版本（建议 Python 3.11）后重试。
- `lock_checksum_mismatch`：受跟踪锁被修改或损坏；从可信仓库恢复锁。
- `dependency_install_failed`：公开索引、网络或 pip 失败；修复后重跑同一 profile。
- `node`：QQ profile 缺少受支持 Node/npm。
- `npm_ci_failed`：检查公开 registry 和 `package-lock.json`，不要改用无锁安装。
- `port-8000/8010/9880`：已有监听者；先确认并正常停止原进程。
- 可选配置缺失：按公开示例或 PK-211/PK-212 工作流人工处理，Core 可继续使用。

## 8. 验证迁移

从项目根运行安装专项测试和文档门禁：

```powershell
.\scripts\python.ps1 tests\test_windows_install.py
.\scripts\python.ps1 ..\scripts\check_task_docs.py
```

专项测试只使用临时副本、fake pip/npm/进程/端口和 tripwire，不以开发机现有 `.venv-asr`、`node_modules`、配置或模型作为干净安装证据。

普通双击任一受跟踪 BAT 时，窗口会在命令成功、失败或长驻进程退出后保留。
自动化、CI、计划任务和 BAT 内部委托使用 `PROJECT_KEI_NO_PAUSE=1` 防止等待；
脚本仍返回原始退出码。
