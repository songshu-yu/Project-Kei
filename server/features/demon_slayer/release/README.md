# Demon Slayer official release handoff

本目录冻结 `demon_slayer@1.0.1` 的官方发布输入。确定性 ZIP 不进入仓库，
必须由 `features.demon_slayer.package_builder` 写入调用者新建的系统临时目录。
`official-release-fragment.json` 是 PK-000 合并 Catalog v1 时的输入；本任务不
修改共享 Catalog、不创建 GitHub Release，也不上传资产。

发布契约：

- Release tag：`modules-2026.08.02`
- Asset：`demon_slayer-1.0.1.zip`
- 固定来源：`songshu-yu/Project-Kei-Modules`
- 强依赖：无
- 可选增强：`conversation`；缺失时目标、打卡、积分、奖励和确定性本地复盘仍可用
- 权限：仅 `local_state`
- 数据策略：卸载程序默认保留历史目标、打卡、积分和奖励；重装继续使用原状态路径
- purge 边界：只允许 PK-010 清理 `server/data/modules/demon_slayer/`，不得删除
  历史 `server/systems/data/demon_slayer.json`
- 重启语义：安装后仍为停用；启用、停用、升级、回滚和卸载对进程内路由/面板的
  变化均在重启 API 后生效

PK-000 发布前应在系统临时目录构建两次，确认 ZIP 字节、大小、ZIP SHA-256 和根
manifest SHA-256 完全相同，再用共享 Catalog builder 生成最终 Catalog 条目。
