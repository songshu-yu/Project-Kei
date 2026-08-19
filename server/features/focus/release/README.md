# Focus official release handoff

本目录冻结 `focus@1.1.1` 的官方发布输入。`official-release-fragment.json`
符合 PK-010 的 release fragment v1；确定性 ZIP 不进入仓库，必须在系统临时目录
重新构建。`official-catalog-entry.json` 是该 ZIP 对应的完整 Catalog v1 条目，
供 PK-010 合并和 PK-900 发布复核。

从项目根目录执行：

```powershell
$releaseRoot = Join-Path ([System.IO.Path]::GetTempPath()) ("project-kei-focus-1.1.1-" + [guid]::NewGuid().ToString("N"))
New-Item -ItemType Directory -Path $releaseRoot
.\scripts\python.ps1 -m features.focus.package_builder "$releaseRoot\focus-1.1.1.zip"
.\scripts\python.ps1 ..\scripts\build_official_module_catalog.py `
  --fragment "features\focus\release\official-release-fragment.json" `
  --asset-root $releaseRoot `
  --output "$releaseRoot\official-catalog.json" `
  --generated-at "2026-07-30T00:00:00Z"
```

输出必须满足：

- Release tag：`modules-2026.08.02`
- Asset：`focus-1.1.1.zip`
- 固定来源：`songshu-yu/Project-Kei-Modules`
- 数据策略：卸载保留状态，重装后继续关联
- 重启提示：安装后仍为停用；启用、停用、升级、回滚和卸载对进程内路由的变化均
  在重启 API 后生效

PK-100 用户展示交接：

- 名称：专注计时
- 说明：番茄钟与专注模式，支持自定义分钟、当前任务、计时恢复、停止和显式重置
- 权限：本机状态（`local_state`）
- 数据提示：卸载模块不会删除专注状态
- 重启提示：安装后需启用并重启 API；停用或卸载后也需重启 API 才移除路由和面板

发布动作不属于 PK-180。本目录不创建 GitHub Release、不上传资产，也不修改官方
catalog；这些步骤由 PK-000 在 PK-010、PK-100、PK-180 通过 PK-900 后统一执行。
