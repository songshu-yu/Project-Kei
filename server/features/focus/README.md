# Focus module

`focus` 是 Project Kei 的首个可安装业务模块，也是首个冻结官方 GitHub Release
输入的业务模块。源码遵守 `router -> service -> repository`：

- `models.py`：启动请求和计时响应模型；
- `repository.py`：JSON 状态读写及可注入路径；
- `service.py`：番茄钟、专注模式、重复启动保护、停止、完成和恢复规则；
- `router.py`：同时提供 `/api/v1/focus/*` 与 `/focus/*`，两组路由调用同一 `FocusService`；
- `module.py`：安装包的 `register(app)` 入口；
- `package_source/`：正式 manifest 和动态控制台入口；
- `package_builder.py`：把同一套 Python 源码规范化为 UTF-8/LF 后复制到包内
  `backend/`，生成可审阅目录或完全确定性的无压缩 ZIP；
- `release/`：冻结官方 release fragment、完整 Catalog v1 条目和 PK-010/PK-100
  发布交接。

从项目根目录构建本地 ZIP（输出路径必须尚不存在）：

```powershell
.\scripts\python.ps1 -m features.focus.package_builder "<output-directory>\focus-1.1.1.zip"
```

构建器会同时输出 ZIP 的 SHA-256，可作为 `POST /api/v1/modules/focus/install` 的 `expected_sha256`。包只包含 `manifest.json`、`backend/*.py` 和 `dashboard/index.js`，不包含状态、配置、凭证或安装脚本。

当前候选冻结为 `focus@1.1.1`、tag `modules-2026.08.02`、asset
`focus-1.1.1.zip`，固定来源为 `songshu-yu/Project-Kei-Modules`。发布 ZIP 必须在
系统临时目录生成，不进入仓库；PK-010 可用
`release/official-release-fragment.json` 和实际 ZIP 生成/校验官方 catalog。
完整摘要、大小、固定 URL、构建命令和 PK-100 展示提示见
[`release/README.md`](release/README.md)。PK-180 不创建 Release 或上传资产，
该动作留给 PK-000/PK-900 的统一发布流程。

1.1.x 在既有 status/start/stop/reset 之外提供本机版本化 `POST /api/v1/focus/encouragement`，并在计时响应中返回不透明 `session_id`。鼓励请求只接受 `session_id` 与 `start_at`；service 必须重新确认同一会话仍 active，再通过应用注入的 PK-200 `TextGenerator` 用有限 mode/elapsed/remaining 事实生成一次短文案。它不接受任意 prompt、QQ 标识或 URL，不写 conversation history；会话停止、完成、替换或状态损坏时在模型调用前失败。模型失败返回 `generated=false`，由 QQ sidecar 决定确定性 fallback。已有旧安装需要显式 update 到 1.1.1 并重启 API，不会自动升级。

当前兼容默认状态路径仍是既有 `server/systems/data/focus_timer.json`。`server/data/focus_timer.json` 及其他同名历史文件同样视为用户数据；PK-180 不读取、不移动或合并它们。测试和生命周期验收必须给应用注入临时 `focus_state_path`。

安装后默认为停用。安装、升级、启用、停用和卸载均遵守 `in_process` 重启语义：启用后重启 API 才会装配新旧路由和动态面板；停用或卸载后也要重启，旧进程中已经注册的路由不会热移除。卸载只移除程序包，保留既有状态；重新安装和启用后继续关联原路径。
