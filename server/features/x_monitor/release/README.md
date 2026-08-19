# X monitor official release handoff

本目录冻结 `x_monitor@1.1.0` 的官方发布输入。确定性 ZIP 不进入仓库，只能在系统
临时目录构建。PK-120 不修改官方 Catalog，也不创建或上传 GitHub Release。

发布身份固定为：

- tag：`modules-2026.08.02`
- asset：`x_monitor-1.1.0.zip`
- 强依赖：`intel_sources`
- 权限：`local_state`
- 数据策略：卸载保留既有 X 来源配置、资料缓存和今日言论缓存
- 重启：启用、停用、更新、回滚和卸载后的路由/Collector/面板变化需重启 API

包只含 allowlist 程序文件、manifest 和动态面板；FxEmbed 后备固定使用
`https://api.fxtwitter.com`，不接受任意 base URL 或秘密配置。包不含来源名单、
`x_profiles.json`、`x_daily_posts.json`、历史 replies 残留、`.env`、Cookie、
Token、模型、`vendor/`、fixture 或安装脚本。PK-000 在 PK-900 通过后使用同一
确定性构建器生成资产和合并官方 Catalog。
