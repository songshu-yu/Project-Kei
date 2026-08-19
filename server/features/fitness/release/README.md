# Fitness official release handoff

本目录冻结 `fitness@1.0.3` 的官方发布输入。`official-release-fragment.json`
符合 PK-010 release fragment v1；确定性 ZIP 不进入仓库，必须在系统临时目录重新构建。
`official-catalog-entry.json` 是该 ZIP 对应的完整 Catalog v1 条目，仅供 PK-000 合并和
PK-900 发布复核。

从项目根目录执行：

```powershell
$releaseRoot = Join-Path ([System.IO.Path]::GetTempPath()) ("project-kei-fitness-1.0.3-" + [guid]::NewGuid().ToString("N"))
New-Item -ItemType Directory -Path $releaseRoot
.\scripts\python.ps1 -m features.fitness.package_builder "$releaseRoot\fitness-1.0.3.zip"
.\scripts\python.ps1 ..\scripts\build_official_module_catalog.py `
  --fragment "features\fitness\release\official-release-fragment.json" `
  --asset-root $releaseRoot `
  --output "$releaseRoot\official-catalog.json" `
  --generated-at "2026-08-08T00:00:00Z"
```

输出必须满足：

- Release tag：`modules-2026.08.08`
- Asset：`fitness-1.0.3.zip`
- 固定来源：`songshu-yu/Project-Kei-Modules`
- 数据策略：卸载与新 namespace purge 都不删除 `server/data/fitness_checkins.json`；重装后由 composition root 继续显式关联
- 重启提示：安装后仍为停用；启用、停用、升级、回滚和卸载对进程内路由的变化均在重启 API 后生效

包只包含 manifest、fitness 后端 allowlist 与动态控制台入口，不包含真实打卡状态、
`.env`、缓存、模型、`vendor`、测试、脚本或安装命令。发布、Catalog 合并和共享
composition 改动由 PK-000 串行完成。
