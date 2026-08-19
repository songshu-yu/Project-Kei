# Calendar official release handoff

本目录冻结 `calendar@1.0.0` 的官方发布输入。确定性 ZIP 不进入仓库，必须在系统
临时目录重新构建；`official-release-fragment.json` 供 PK-000 在共享发布窗口生成
正式 Catalog 条目。

从 `server/` 目录执行：

```powershell
$releaseRoot = Join-Path ([System.IO.Path]::GetTempPath()) ("project-kei-calendar-1.0.0-" + [guid]::NewGuid().ToString("N"))
New-Item -ItemType Directory -Path $releaseRoot
.\scripts\python.ps1 -m features.calendar.package_builder "$releaseRoot\calendar-1.0.0.zip"
```

发布输入必须保持：

- Release tag：`modules-2026.08.02`
- Asset：`calendar-1.0.0.zip`
- 数据策略：卸载保留既有事件、标签、备注、技能和练习记录，重装后继续关联
- 重启语义：启用、停用、更新、回滚和卸载后重启 API 才改变进程内路由/provider
- 包内只含 allowlist 程序文件、manifest 和动态面板；不含任何状态文件、历史同名
  文件、`.env`、缓存、模型、`vendor/`、脚本或测试夹具
- 动态面板不提供全量清空入口

兼容风险：`/calendar/reset` 是已有 legacy 无确认端点，暂时保留；版本化
`/api/v1/calendar/reset` 仍要求精确确认值 `calendar`。该风险不得扩散到动态面板。
真实发布、Catalog 合并和 Git 操作不属于 PK-190。
