# Daily life forecast official release handoff

本目录冻结 `life_forecast@1.0.0` 的官方发布输入。ZIP 只能在系统临时目录通过
`features.life_forecast.package_builder` 确定性重建，不进入 Git。

- Release tag：`modules-2026.08.19`
- Asset：`life_forecast-1.0.0.zip`
- 卸载保留 `server/data/modules/life_forecast/` 中的本机配置和每日缓存
- 包内只有 allowlist Python、manifest 与同源动态面板；没有位置、缓存、`.env`、
  API Key、生日、星座、个人状态、模型、脚本或 vendor
- 普通页面加载和读取不访问上游；只有显式 refresh 使用固定 Open-Meteo HTTPS API
- 发布前由 PK-000/PK-900 核对 ZIP/manifest 摘要并决定是否合入共享官方 Catalog；
  本任务不上传、不发布、不替换现有 Release
