# RSS intelligence official release handoff

本目录冻结 `rss_intel@1.0.0` 的公开发布输入。确定性 ZIP 不进入仓库，由
`features.rss_intel.package_builder` 在系统临时目录重建；正式 Catalog 合并与
Release 发布由 PK-000 串行执行。

发布边界：

- Release tag：`modules-2026.08.02`
- Asset：`rss_intel-1.0.0.zip`
- 强依赖：`intel_sources`
- Collector：Core Collector 1.0，`source_id="money"`
- 包内不含 Feed、关键词、来源名单、缓存、凭据、环境文件、用户数据、vendor、
  脚本或测试夹具
- 打开动态面板、安装、启用和普通读取均不触发采集；只有显式 Collector 调用联网
- Feed 只能由应用组装时注入受信 HTTPS 配置，不提供浏览器或任意用户 URL 入口
- Core 只需设置
  `app.state.rss_intel_source_config_provider: Callable[[], Mapping]`；动态入口自行
  构造 RSS Provider，不要求 Core import `features.rss_intel.provider`。映射只接受
  既有 `rss_feeds`、`keywords` 和可选 `allowed_redirect_hosts`
- 每一跳重定向与 DNS 解析均拒绝私网、本机、链路本地、保留和非全局地址
- 卸载保留外部来源配置与缓存；重装后由应用 Provider 重新关联

本目录不修改官方 Catalog，不创建 Release，也不执行 Git 操作。
