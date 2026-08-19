# YouTube Collector official release handoff

本目录冻结 `youtube@1.0.1` 的官方发布输入。确定性 ZIP 不进入仓库，必须在系统
临时目录构建。包只包含 manifest 与 Collector 后端源码，不包含 Channel ID
列表、配置、缓存、Cookie、Token、`.env`、vendor、脚本或安装钩子。

固定发布输入：

- Release tag：`modules-2026.08.02`
- Asset：`youtube-1.0.1.zip`
- 依赖：`intel_sources`
- 数据策略：卸载只删除程序包，保留来源配置与缓存
- 重启语义：安装后默认停用；启用、停用和卸载均在重启 API 后改变注册状态

本模块没有独立 HTTP 管理面或动态面板。Channel ID 的增删改继续由
`intel_sources` 所有；YouTube 包只在进程启动时向 Core `CollectorRegistry`
注册 `source_id="youtube"`。读取面板、安装、启用或加载模块均不访问 YouTube；
只有 PK-110 的显式生成/刷新流程调用 Collector 时才允许请求固定公开 Atom Feed。

本目录不创建 GitHub Release、不上传资产，也不修改官方 Catalog；发布与共享
Catalog 合并由 PK-000/PK-900 在串行窗口统一执行。
