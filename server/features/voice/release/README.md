# Voice official release handoff

本目录冻结 `voice@1.0.9` 的官方发布输入。确定性 ZIP 不进入仓库，必须在系统
临时目录重建；PK-210 不创建 GitHub Release、不上传资产，也不修改官方 Catalog。

包只包含 Project Kei 的语音编排、Provider 公共接口、版本化/legacy 路由、临时
音频管理和动态状态面板。它不包含 ASR 模型、GPT-SoVITS 上游源码、安装器、权重、
参考音频、Voice Pack 内容、生成输出、`.env`、本机路径、`vendor/` 或脚本。
ASR 目录选择 HTTP 只适配本机 provider：包不包含选择器实现或模型路径，客户端也
不能提交路径。取消、验证失败和保存失败保持旧配置；公开状态只显示安全目录名。

发布输入：

- Release tag：`modules-2026.08.12`
- Asset：`voice-1.0.9.zip`
- Package size：`108683` bytes
- Package SHA-256：`d05c0a2a783851d54f5656596ec66d26a34131223b0221437f3bdccb6b6f4f9b`
- Manifest SHA-256：`3290021c1c5d1f22f560787c30894ee445d59f2c8c30e076794f884a933f74fb`
- 强依赖：`conversation`
- 可选依赖：`calendar`；缺失时 calendar 摘要 registry 返回稳定 unavailable
- 本地合成 profile：固定 `qq_c2c_voice_v1`/`audio/silk`；生产 encoder 由 composition 注入，缺失时 `encoding_unavailable`
- readiness：只报告本地 engine、Voice Pack、encoder，不读取或推断 QQ 凭据/媒体权限
- 成功时长头：`X-Kei-Audio-Duration-Ms`，仅由已验证 utterance duration 向上取整，范围 1..60000
- Silk 适配器：包内仅含固定接口适配代码，不含 wheel/源码/二进制；生产 readiness 仍依赖 PK-020 hash-lock 与 composition 注入
- 数据策略：卸载保留本机 Provider/模型登记、用户音频和外部资产
- 重启语义：启用、停用、更新、回滚或卸载后按 Core 返回值重启 API
- 本机进程控制：ASR/GPT-SoVITS 仅可停止当前 Core 显式启动并持有的进程组；外部实例只读显示

从项目根目录执行：

```powershell
$releaseRoot = Join-Path ([System.IO.Path]::GetTempPath()) ("project-kei-voice-1.0.9-" + [guid]::NewGuid().ToString("N"))
New-Item -ItemType Directory -Path $releaseRoot
.\scripts\python.ps1 -m features.voice.package_builder "$releaseRoot\voice-1.0.9.zip"
.\scripts\python.ps1 ..\scripts\build_official_module_catalog.py `
  --fragment "features\voice\release\official-release-fragment.json" `
  --asset-root $releaseRoot `
  --output "$releaseRoot\official-catalog.json" `
  --generated-at "2026-07-30T00:00:00Z"
```

最终发布和 Catalog 合并由 PK-000 在语音批累计验收后统一完成。
