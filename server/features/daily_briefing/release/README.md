# Daily briefing official release handoff

本目录冻结 `daily_briefing@1.0.3` 的官方发布输入。确定性 ZIP 不进入仓库，
必须在系统临时目录重新构建。`official-release-fragment.json` 供 PK-000/PK-010
在 PK-900 通过后合并到官方 Catalog；本任务不修改共享 Catalog 或创建 GitHub
Release。

模块只包含每日情报聚合、缓存、播报文本、路由和动态面板代码，不包含来源名单、
真实缓存、Cookie、Token、`.env`、模型输出、音频、虚拟环境或 `vendor/`。来源
Collector、conversation、voice 和 life_forecast 均为可选依赖：缺少来源时显示
`not_configured`，缺少 conversation 时使用确定性播报文本，缺少 voice 时返回
文本降级。

发布参数：

- Release tag：`modules-2026.08.19`
- Asset：`daily-briefing-1.0.3.zip`
- 固定来源：`songshu-yu/Project-Kei-Modules`
- 数据策略：卸载保留历史 `server/data/briefing_cache/`
- 生命周期：安装后需启用并重启；停用/卸载后需重启才移除路由和面板

从项目根目录构建：

```powershell
$releaseRoot = Join-Path ([System.IO.Path]::GetTempPath()) ("project-kei-daily-briefing-1.0.3-" + [guid]::NewGuid().ToString("N"))
New-Item -ItemType Directory -Path $releaseRoot
.\scripts\python.ps1 -m features.daily_briefing.package_builder "$releaseRoot\daily-briefing-1.0.3.zip"
```

## Optional voice binding

The host may set `app.state.daily_briefing_voice_provider` to either a current
`BriefingVoiceProvider` or a synchronous factory returning one. The module
resolves and captures that value once for each explicit voice request, so a
voice module loaded after daily briefing becomes available without rebuilding
the service. Replacing or clearing the host seam affects the next request only.
Missing, throwing or malformed providers deterministically degrade to
`text_only`; ordinary cache reads never resolve the provider.

When that high-level seam is absent, the packaged structural adapter reads the
current `app.state.voice_service` attributes `tts`, `voice_packs` and
`artifacts`. A host may explicitly override them with
`voice_tts_provider`, `voice_pack_resolver_binding` and
`voice_artifact_store`; `voice_synthesis_request_factory` is the optional
factory for a host-native public synthesis request object. All four capabilities
are captured once per request. No PK-210 or PK-212 Python implementation type is
imported by the package.
