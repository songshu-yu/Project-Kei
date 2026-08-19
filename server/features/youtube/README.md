# YouTube Collector module

`youtube` 是只读取 YouTube 公开 Atom Feed 的进程内 Collector 1.0 模块。它严格
区分 Channel ID、频道名称与 handle：只有 `UC` 加 22 个 URL-safe 字符的
Channel ID 能进入固定的 `https://www.youtube.com/feeds/videos.xml` 请求。

安装包通过 `backend.register(app)` 向 Core `CollectorRegistry` 注册
`source_id="youtube"`。应用可以在加载前注入
`app.state.youtube_collector_provider`，以无参数 callable 返回 Collector 1.0
实例；自动测试据此使用 MockTransport。注册过程不读取来源配置、不调用
Collector，也不产生网络请求。

本模块没有独立 API 或动态面板。Channel ID 配置属于 `intel_sources`，Collector
只消费 `CollectRequest.source_config_snapshot["youtube_channel_ids"]` 的只读
快照。缺失配置返回 `not_configured`；非法值零请求；单频道失败不阻断其他频道。

从项目根目录构建本地包：

```powershell
.\scripts\python.ps1 -m features.youtube.package_builder "<临时目录>\youtube-1.0.1.zip"
```

输出只含 `manifest.json` 和 `backend/__init__.py`、`backend/collector.py`、
`backend/module.py`，不包含真实 Channel ID、配置、缓存、凭证、`.env`、vendor
或脚本。卸载只移除程序包，来源配置与缓存由各自所有者保留。
