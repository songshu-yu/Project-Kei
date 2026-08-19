# GPT-SoVITS Provider official release handoff

本目录只描述 `gpt_sovits_engine_provider@1.0.2` 的 Project Kei sidecar adapter
模块包。Release ZIP 不进入仓库，由 PK-000 在临时目录用
`features.voice.providers.gpt_sovits.package_builder` 确定性构建并统一发布。
本次新资产固定为 tag `modules-2026.08.12`、文件
`gpt_sovits_engine_provider-1.0.2.zip`；已发布过的 `1.0.0`、`1.0.1` 与旧 tag/asset
保持不可变，不得用新字节覆盖。

包内只有 manifest、路径无关配置 Schema、动态状态面板、Project Kei Provider/
受控获取/adapter、本机目录选择接缝源码和固定 `engine.json`。它不包含 GPT-SoVITS 上游源码、
runtime、Python/CUDA 依赖、模型、权重、参考音频、本机登记、绝对路径、`.env`、
BAT、PowerShell、远程脚本或 `vendor/`。

安装本模块不等于安装外部引擎。安装后仍为停用；启用只允许 Core 已登记的
`gpt_sovits_provider` adapter 读取忽略的本机登记，复用已运行的 9880，或使用
固定 `runtime/python.exe api.py -a 127.0.0.1 -p 9880` 启动已登记引擎。缺少
引擎登记时 deployment readiness 返回 `configuration_missing`，模块保持
`needs_configuration` 且不会尝试启动进程；登记损坏、包描述异常或固定入口缺失
返回 Core 规范化的 unavailable。Core 和 voice 保持正常文字降级。adapter
完整实现冻结的 DeploymentSidecarAdapter，只消费 Core 验证后的 deployment；
只停止自己创建的进程，不停止外部既有进程，也不删除外部资产。

受控获取仍是 PK-211 的独立、用户显式操作：必须精确确认固定 engine id，下载
固定官方版本并在解包前核对大小和 SHA-256；不会由安装/启用模块隐式触发，也
不会执行归档中的安装脚本或安装 Python/CUDA/依赖。

## PK-100 本机目录按钮接缝

动态面板在“尚未登记”或登记无效时显示“选择已有引擎目录”，已登记时显示
“重新选择已有引擎目录”。它只调用下列固定接口，不提供文本框、文件系统枚举、
路径、URL、命令、PowerShell/BAT 或启动参数：

- `GET /api/v1/gpt-sovits-engine/status`：只读、真实 loopback；浏览器必须同源。
- `POST /api/v1/gpt-sovits-engine/select-existing`：真实 loopback、精确受信控制台
  Origin、无 query、空请求体；后端仅在这次显式点击中打开 Windows 目录选择器。

状态响应固定为 `engine_id`、`registration_state`、`integrity_status`、
`entrypoints_ready`、`display_name`、`selection_in_progress`、
`can_select_existing`，操作响应另加 `action=cancelled|registered`。`display_name`
只允许最多 80 字符的末级安全名称，绝不返回绝对路径。已有安装没有匹配固定
Project Kei marker 时必须返回 `registered_existing` +
`unverified_existing_install`，不能宣称归档已验证。取消零写入；恶意结构、
重解析点、并发选择或保存失败均不替换旧登记。

Core 串行装配只需构造 `LocalEngineSelectionService` 并挂载
`create_gpt_sovits_engine_router(service)`；不得让浏览器或 module manifest 构造
service 的 picker、Registry 路径或 descriptor。该 API 不启动 9880，也不执行、
复制、移动或递归扫描所选目录。

共享 Core 登记装配、官方 Catalog 合并和 GitHub Release 发布均由 PK-000 串行
完成；本目录不修改共享 Catalog，不上传资产。
