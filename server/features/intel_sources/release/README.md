# Intel Sources official release handoff

本目录冻结 `intel_sources@1.1.6` 的官方发布输入。确定性 ZIP 不进入仓库；
发布窗口必须从当前源码重新构建，再由 PK-010 的官方 Catalog 工具生成目录条目。

从项目根目录执行：

```powershell
$releaseRoot = Join-Path ([System.IO.Path]::GetTempPath()) ("project-kei-intel-sources-1.1.6-" + [guid]::NewGuid().ToString("N"))
New-Item -ItemType Directory -Path $releaseRoot
.\scripts\python.ps1 -m features.intel_sources.package_builder "$releaseRoot\intel-sources-1.1.6.zip"
.\scripts\python.ps1 ..\scripts\build_official_module_catalog.py `
  --fragment "features\intel_sources\release\official-release-fragment.json" `
  --asset-root $releaseRoot `
  --output "$releaseRoot\official-catalog.json" `
  --generated-at "2026-08-08T00:00:00Z"
```

发布输入：

- Release tag：`modules-2026.08.08`
- Asset：`intel-sources-1.1.6.zip`
- 大小：`41,312` bytes
- Package SHA-256：`db96595b58347959ca3506453700373362c6e237a5da6c5edda09eb649f28bda`
- Manifest SHA-256：`4b4dcb6c503c9fa21720e9ec9c4fa64703d50a3b5c19888822bddb09c821cfcb`
- 固定来源：`songshu-yu/Project-Kei-Modules`
- 数据策略：卸载保留历史 `server/data/intel_sources.json`，重装后重新关联
- 权限：本机状态（`local_state`）
- 重启提示：安装后保持停用；启用、停用和卸载后需重启 API

包内只允许 manifest、六个 backend 源文件和动态 dashboard 入口。不得包含真实
`intel_sources.json`、来源名单、Cookie、Token、`.env`、缓存、状态、vendor 或脚本。
本目录不创建 GitHub Release、不上传资产，也不修改官方 Catalog；统一发布由 PK-000
在 PK-900 验收后执行。
