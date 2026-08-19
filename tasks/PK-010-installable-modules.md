# PK-010 — 可安装模块生命周期与加载基础

- 状态：待集成
- 优先级：P0
- 所属模块：`module_manager`
- 依赖任务：PK-001
- 负责路径：`docs/architecture/installable-modules.md`、未来 `server/core/modules/`、模块 manifest Schema、模块注册表与生命周期 API
- 当前对话：2026-08-08 PK-000 重新打开浏览器本地 ZIP 身份推导增量；本对话只补
  PK-010 上传契约、Core 路由和临时目录回归，不修改 PK-100 UI、README、TASKS、
  业务模块或真实 registry/runtime/data

## 目标

实现 Project Kei 可安装模块的最小基础设施，使 Core 能发现本地模块包、验证 manifest、解析依赖并管理安装、配置、启用、停用、升级、回滚和卸载状态；不把普通业务拆成微服务。

## 第一阶段范围

- 固化并验证 manifest JSON Schema。
- 建立本机模块注册表和明确的状态模型。
- 将 `GET /api/v1/modules` 从静态目录兼容扩展为安装/启用状态目录。
- 实现只接受本地可信模块包的生命周期骨架。
- 为 `in_process` 和 `sidecar` 提供不同的装配/健康检查协议。
- 为 `PK-100` 提供已启用模块的控制台入口目录。
- 使用 `PK-180` 专注计时作为首个业务试点，但不在本任务内重写专注业务规则。

## 不在第一阶段内

- 远程模块商店、自动更新、发布者签名或付费模块。
- 把所有现有模块一次性迁移。
- 静默安装 Node.js、模型、QQ 凭证或其他大型外部依赖。
- 无重启卸载 FastAPI 路由。
- 清除现有个人状态或迁移历史跟踪数据文件。

## 接口契约

- `GET /api/v1/modules` 保持现有字段兼容，只新增可选生命周期字段。
- 写操作使用 `/api/v1/modules/{module_id}/...`，第一版仅本机可用。
- 查看模块目录不触发下载、安装、联网、服务启动或付费调用。
- 卸载默认保留用户数据；清除数据使用独立、二次确认的破坏性操作。

## 依赖任务与协作

- `PK-000`：确认新增权限、模块类型和跨模块生命周期契约。
- `PK-100`：消费已启用模块的前端入口，不自行维护安装状态。
- `PK-180`：提供专注模块 manifest、公开 service、兼容接口和数据所有权。
- `PK-900`：验收空模块启动、生命周期、回滚、数据保留和安全边界。

## 验收标准

- 空可选模块状态下 Core 可启动，原有兼容接口不因管理器存在而失效。
- 非法 manifest、重复 ID、循环依赖、版本不兼容和路径穿越会在写入运行目录前失败。
- 安装失败不产生半安装记录，升级失败保留旧版本。
- 启用、停用和卸载结果可查询，sidecar 停用后不再运行自己的后台任务。
- 默认卸载不删除模块数据，清除数据必须显式确认准确目标。
- 定向测试、API 导入检查和 `git diff --check` 通过。

## 工作记录

- 2026-07-21：领取任务，通读项目第一方 Markdown、架构说明、任务边界、环境示例与运行说明；确认不触碰 `vendor/`、个人状态和其他功能任务。
- 2026-07-21：固化 `server/core/modules/manifest.schema.json` 与对应运行时校验，限制 ID、SemVer、Core 兼容范围、包内路径、命名空间、依赖/冲突、第一阶段权限和 sidecar adapter 声明。
- 2026-07-21：实现目录/ZIP 的 SHA-256 校验、安全展开、符号链接和路径穿越拒绝、正式版本目录原子切换，以及 `server/data/module_registry.json` 原子注册表。
- 2026-07-21：实现安装、配置检查、启用、停用、升级、回滚、卸载保留数据和精确确认清数据；依赖环、缺失依赖、已启用冲突、重复 ID 和 API 命名空间冲突均会阻断操作。
- 2026-07-21：实现 API 重启时的 `in_process` `register(app)` 装载和 Core 注册式 sidecar 启停/健康协议；manifest 不能执行任意 shell 命令。
- 2026-07-21：`GET /api/v1/modules` 保留原字段并增加可选生命周期字段；已启用模块的前端静态资源只允许从包内 `dashboard/` 读取。
- 2026-07-21：新增隔离测试 `server/tests/test_installable_modules.py`，不读取或修改真实模块注册表、运行目录和个人数据。
- 2026-07-21 终验整改：新增 `server/core/modules/contracts.py` 作为 Core 保留身份与 namespace 的唯一来源；ModuleManager、catalog 和测试共同消费，不再各自维护 `catalog/module_manager/dashboard` 常量集合。
- 2026-07-21 终验整改：安装/升级会在正式版本目录和注册表写入前拒绝 Core 保留 ID、`/api/v1/modules`、`/api/v1/dashboard` 以及相互包含的斜杠子/父 namespace；可选包也不能声明与必需 Core 模块冲突。
- 2026-07-21 终验整改：ModuleManager 快照、重启装载和 sidecar 启停会忽略历史或伪造的 Core ID 记录；catalog 对 Core 项执行不可覆盖合并，即使注入恶意生命周期快照也保持必需属性和 namespace。
- 2026-07-21 PK-000 二次复验：独立重放 Core ID、Core namespace、子 namespace 和父级 namespace 四类拒绝并确认无状态残留；完整批次测试、编译、JavaScript 和文档门禁通过，PK-010 验收完成。
- 2026-07-30 增量审计：现有 `POST /api/v1/modules/{module_id}/install` 仅接受 JSON `package_path + expected_sha256`，适用于本机 CLI，但浏览器不能安全、可移植地提交服务器文件路径。PK-000 随后紧急更正产品方向：普通入口必须从项目固定官方 GitHub 仓库的 Catalog/Release asset 获取模块，本地路径/ZIP 只保留为高级备用；因此本轮没有新增把本地 ZIP 当作唯一入口的上传 API。
- 2026-07-30 官方目录增量：新增 Catalog v1 受版本控制空基线、正式 Schema、Release fragment Schema 和确定性合成/校验工具。官方身份固定为匿名公开 `songshu-yu/Cyber-Girlfriend`，客户端不能提交 owner、repo、URL、Token 或代理；首批只接收 PK-180 生成并由 PK-000 发布的 focus 正式条目，当前不伪造不存在的 Release asset，也不把内置模块列为 downloadable。
- 2026-07-30 官方获取增量：新增只读本机目录、显式刷新和 install/update/rollback-official 接缝。普通目录与已安装模块列表零网络；刷新失败保留原子缓存/last-good，下载使用关闭环境代理继承的匿名 HTTPS、逐跳 GitHub asset allowlist、超时、64 MiB 上限、精确字节数、流式 ZIP SHA-256、根 manifest SHA-256 和随机临时目录，随后只委托既有 ModuleManager。
- 2026-07-30 生命周期响应增量：目录和成功操作返回 `available_actions`、包来源与官方 Release 摘要；官方操作另返回 `official_operation` 进度摘要。已启用或仍有待重启装配的 `in_process` 模块卸载明确返回 `restart_required=true`，不伪造热卸载。卸载继续保留数据，purge-data 路径和精确确认语义不变。
- 2026-07-30 模块作者交接：新增 `docs/architecture/module-package-contract.md`，冻结真实 manifest、`register(app)`、dashboard `mount(context)/unmount()`、namespace、配置/秘密、数据 namespace、in-process/sidecar、确定性包、Catalog/Release 和临时目录测试契约；README 共享段落按 PK-000 要求暂不修改。
- 2026-07-30 sidecar 增量：新增 Core 归一化
  `SidecarReadiness(status/code/message/missing_requirements)` 与不可静默覆盖的
  `SidecarAdapterRegistry`。生产 composition 通过
  `register_core_sidecar_adapter(name, adapter)` 注册受审查 adapter；manifest
  仍只能引用 adapter 名，不能声明 path/command/cwd/env。
- 2026-07-30 sidecar 状态机：安装、配置检查、启用和 API 重启恢复均先消费
  readiness。缺配置或尚未部署的依赖返回/记录 `needs_configuration`；运行时、
  平台、入口、部署完整性或 adapter 异常返回/记录 `unavailable`。两者均携带脱敏
  详情且不调用 `start()`、不写成 `broken`；
  readiness 就绪后的真实启动/健康失败才保持原有 `broken` 语义。旧
  `start/stop/is_healthy` adapter 使用 `legacy_healthcheck` 兼容路径。
- 2026-07-30 sidecar 依赖部署根：冻结安装包程序树
  `runtime/modules/<id>/<version>/` 为不可变内容，`installed_tree_sha256` 继续覆盖
  全树；新增 Core 内部默认 `runtime/module-dependencies/<id>/<version>/` 作为
  可再生成依赖部署根。dependency root 不进入包摘要、官方 rollback 信任或公开
  lifecycle 响应，PK-010 不创建 deployment、不运行 npm。
- 2026-07-30 deployment descriptor：新增冻结
  `SidecarDeploymentDescriptor(module_id/version/package_root/
  dependency_deployment_root/installed_tree_sha256)` 和内部
  `resolve_sidecar_deployment()`。只解析已安装 current sidecar，核对 ID、SemVer、
  注册表精确路径、两类 root containment 与 symlink/reparse；descriptor-aware
  adapter 使用 `deployment_readiness/start_deployment/stop_deployment/
  is_deployment_healthy`，版本切换由 manager 重新解析，旧 adapter 保持兼容。
- 2026-07-30 deployment marker 对齐：固定文件名
  `.project-kei-deployment.json`，位置为当前版本
  `dependency_deployment_root` 根；PK-010 只提供共享常量和安全 descriptor，不读取
  marker，不冻结或解释其字段，布局与内容由 PK-020/PK-140 负责。

- 2026-07-30 依赖装配门禁：新增完整已启用图的无副作用预检和确定性分层拓扑排序。
  强依赖必须已安装、current SemVer/manifest 一致、已启用且可用；已安装并启用的
  optional dependency 参与排序，缺失 optional 不失败。同层按 module ID 字典序，
  `backend.register` 与 sidecar start 使用同一序列，shutdown/失败回滚严格逆序。
- 2026-07-30 原子装配接缝：生产 `api.lifespan` 改由
  `features.module_manager.service.activate_enabled_modules(app)` 统一装配，不再在
  `api` import 阶段先注册 in-process 再独立启动 sidecar。Core 内部
  `ModuleActivationCoordinator` 在完整 preflight 后执行，注册失败会调用失败模块
  的可选 `unregister(app)`、恢复路由快照并逆序撤销已成功步骤；公开 HTTP API 未变。
- 2026-07-30 readiness 最终裁决：`dependencies_missing/configuration_missing/
  deployment_missing` 映射 `needs_configuration`；
  `deployment_invalid/integrity_mismatch/package_tampered/runtime_missing/
  platform_unsupported` 映射 `unavailable`。未知 adapter code fail closed 为
  `adapter_unavailable/unavailable`，不透传文本、路径、命令或秘密。
- 2026-07-30 PK-011 权限增量：PK-000 批准 manifest 权限闭集加入
  `network_download`。它只允许用户显式触发/确认后从代码或受版本控制 Catalog
  固定 HTTPS allowlist 做有界、逐跳重验、精确长度与 SHA-256 校验的非执行下载；
  浏览器/manifest/普通配置不能提供 URL、header、cookie、token、proxy、shell，
  页面加载、启动、普通 GET 和后台任务不能自动联网。本轮只扩 Schema、validator
  与声明展示，没有新增网络执行能力或公开 API。

## 实际接口与副作用

- 只读目录：`GET /api/v1/modules`；无联网、安装、启动或本地写入。
- 本机写接口：`install`、`enable`、`disable`、`update`、`rollback`、`configuration/check`、`DELETE` 卸载与 `purge-data`。
- 本机状态：`server/data/module_registry.json`；安装产物：`server/runtime/modules/`；新模块数据：`server/data/modules/`。三者均已加入 `.gitignore`。
- 卸载默认保留数据；清数据确认必须精确匹配模块 ID。第一阶段没有远程商店、自动下载、签名发布者或控制台一键安装。
- 接口路径和请求体保持不变；保留 ID/namespace 的安装或升级请求返回生命周期冲突（HTTP 409），且不会产生正式运行目录、注册表记录或模块数据目录。
- 官方目录读取：`GET /api/v1/modules/official-catalog`，只读本机 cache/last-good/内置
  空基线，不联网。响应包含固定 `source`、`generated_at`、`cache_source`、
  `refresh_status`、`network_accessed` 和 `modules[]`；每个版本包含名称、版本、
  Core 范围、Release 来源、字节数、ZIP/manifest SHA-256、依赖、权限、数据策略、
  重启字段、安装/配置/启用状态、最近操作和 `available_actions`。
- 显式刷新：`POST /api/v1/modules/official-catalog/refresh`，无请求体；只允许
  loopback 与受信 8000 控制台 Origin。成功原子保存公开元数据，失败不覆盖最后
  有效目录。
- 官方安装/更新/回滚：
  `POST /api/v1/modules/{module_id}/install-official`、
  `POST /api/v1/modules/{module_id}/update-official`、
  `POST /api/v1/modules/{module_id}/rollback-official`，请求体统一为
  `{"version":"<semver>","confirmation":"<module_id>@<semver>"}`。成功返回正常
  ModuleManager 快照及 `official_operation.action/status/phase/received_bytes/
  total_bytes/sha256/source`；rollback 不联网并要求前一版本仍匹配 catalog、
  registry provenance、manifest 与已安装 tree 摘要。
- `available_actions` 使用稳定动作名：
  `install_official/install_local/enable/disable/configuration_check/
  update_official/update_local/rollback/rollback_official/uninstall/purge_data`；
  实际列表按当前状态裁剪，Core 必需项为空。
- 官方结构化错误位于 FastAPI `detail`：
  `code/message/stage/retryable/received_bytes/retry_after`。稳定 code 包含
  `official_catalog_refresh_failed`、`official_github_rate_limited`、
  `official_module_not_found`、`official_module_confirmation_required`、
  `official_module_redirect_rejected`、`official_module_download_failed`、
  `official_module_download_timeout`、`official_module_size_mismatch`、
  `official_module_integrity_mismatch`、`official_module_archive_invalid`、
  `official_module_manifest_mismatch`、`official_catalog_source_untrusted` 和
  `official_module_conflict/not_installed/package_rejected/install_failed` 以及
  cache/catalog invalid/unavailable 类别。
- sidecar 配置检查与模块快照新增可选 `sidecar_readiness`：
  `status/code/message/missing_requirements`。固定状态为 `ready`、
  `needs_configuration`、`unavailable`；固定 code 为 `ready`、
  `legacy_healthcheck`、`qq_env_missing`、`configuration_missing`、
  `dependencies_missing`、`deployment_missing`、`node_missing`、
  `runtime_missing`、`platform_unsupported`、`deployment_invalid`、
  `integrity_mismatch`、`package_tampered`、`entrypoint_missing`、
  `adapter_unavailable`。
  message 由 Core 生成，requirement 名仅允许小写安全标识符。启用前未就绪返回
  HTTP 409 `detail.code=sidecar_needs_configuration`，附同一脱敏 readiness；
  API 启动恢复结果使用 `status=needs_configuration`，不回显 adapter 异常。
- Core 内部 helper：
  `features.module_manager.service.resolve_sidecar_deployment(module_id,
  version=None) -> SidecarDeploymentDescriptor`。`version` 省略时解析 current；显式
  提供也必须与 current 完全一致。descriptor 含内部绝对 Path，仅供 PK-020 和受审查
  adapter 使用，不是 HTTP/Pydantic 响应；manifest、浏览器和生命周期请求均不能
  提供或覆盖 dependency root。

- Core 内部装配 helper：
  `ModuleManager.enabled_activation_descriptors()` 返回已完整预检的跨类型拓扑序；
  `ModuleActivationCoordinator(manager, loader).activate(app)/deactivate(app)` 是生产
  composition 调用点。manifest v1 没有 dependency version range，本轮未扩公开
  Schema；版本门禁核对 current SemVer、当前版本 manifest/record 和 Core
  compatibility。

## 剩余集成事项

- `PK-100` 已完成第一阶段只读功能中心、动态面板装载和错误隔离；生命周期写控件继续属于后续阶段，不是本次 PK-010 整改内容。
- `PK-180` 仍需提供第一个真实 focus 包与兼容 service/router；本任务没有迁移现有 `/focus/*` 规则或真实计时状态。
- QQ、ASR、GPT-SoVITS 尚未注册具体 sidecar adapter；Core readiness 与生产注册
  接缝已冻结，但不会接管现有独立启动器。QQ adapter、配置/状态根和 qq-control
  facade 仍由 PK-140 实现，ModuleManager 不解析 QQ `.env`。PK-020 负责在已验证
  descriptor 的 `dependency_deployment_root` 生成锁定依赖；PK-140 只消费
  descriptor，不拼接 package/dependency path。
- PK-000 首轮终验发现的 Core ID/namespace 隔离缺口已修复并通过二次独立复验；PK-010 + PK-100 基础设施批次已完成。
- 本轮增量停在“共享集成待排队”：PK-100 正在按上述冻结矩阵实现网页模块中心，
  PK-180 负责唯一首批 focus 正式 ZIP/Release fragment，PK-000 负责最终 GitHub
  Release 上传、Catalog focus 条目和 README 串行收口。最终批次为
  `PK-010 + PK-100 + PK-180（官方 focus 包）`；PK-010 不自行发布。
- 当前 `server/core/modules/official-catalog.json` 是合法离线空基线。没有 PK-180
  的可审计 ZIP、精确字节数和摘要前，不得添加或声称真实 focus 可下载。

## README 串行更新草案（交 PK-000）

网页控制台的“模块中心”显示官方可安装模块和本机已安装状态；普通打开页面及读取
已安装列表不会联网。用户可显式点击“刷新可安装模块”匿名读取 Project Kei 固定
GitHub 官方目录，选择版本后先查看来源、体积、SHA-256、权限、依赖、数据保留和
重启要求，再以精确 `module_id@version` 确认下载并安装。安装后需显式启用；
`in_process` 的启用、停用、更新、回滚或卸载若返回 `restart_required=true`，
必须重启主 API 才完成路由装配/移除。离线时 Core、已安装模块和最后有效官方目录
继续可用，但不能刷新或下载。本地目录/ZIP 加摘要的旧接口只作为维护者高级入口。
卸载默认保留模块数据；“清除数据”是独立危险操作，必须再次精确输入 module ID，
不得与卸载合并。

## 验证记录

- `server/.venv-asr/Scripts/python.exe tests/test_installable_modules.py`：通过。
- `server/.venv-asr/Scripts/python.exe tests/test_feature_catalog.py`：通过。
- `server/.venv-asr/Scripts/python.exe -m compileall -q core/modules features/module_manager features/catalog tests/test_installable_modules.py tests/test_feature_catalog.py api.py`：通过。
- API 导入及 OpenAPI 路由检查：通过，确认目录与安装接口进入 Schema。
- `git diff --check`：通过；仅输出 Windows 工作区已有的 LF→CRLF 提示，无空白错误。
- `server/.venv-asr/Scripts/python.exe scripts/check_task_docs.py`：初次实现阶段通过；当时共检查 2 个门禁任务。
- 2026-07-21 PK-000 独立复核：原有三项定向测试与 compileall 均通过，但新增隔离审计复现两个漏测缺陷：`dashboard` 可选包安装/启用后目录返回 `required=False`、`managed=True`、`source=local_package`；声明 `/api/v1/modules` namespace 的本地包也被接受。当前测试通过不足以支持完成结论。
- 2026-07-21 整改验证：`server/.venv-asr/Scripts/python.exe server/tests/test_installable_modules.py` 通过；覆盖三个 Core ID、全部当前 Core namespace、Core 子 namespace、拒绝后无注册表/正式运行目录/模块数据目录，以及普通可选模块继续安装和启用。
- 2026-07-21 整改验证：`server/.venv-asr/Scripts/python.exe server/tests/test_feature_catalog.py` 通过；向 catalog 注入伪造的 Core 生命周期快照后，三个 Core 项仍保持统一契约中的 `required`、`managed`、`source`、namespace 和内置安装状态。
- 2026-07-21 整改验证：`server/.venv-asr/Scripts/python.exe server/tests/test_dashboard_shell.py` 通过；PK-100 既有只读功能中心、临时正常模块安装/启用、目录合并和资产边界未回归。
- 2026-07-21 整改验证：PK-900 规定的 `compileall` 通过；测试中的 API 装配改用临时 ModuleManager，不读取或修改真实模块注册表、运行目录或模块数据目录。
- 2026-07-21 整改验证：状态切换前后 `scripts/check_task_docs.py` 均通过（切换后 3 个门禁任务），`git diff --check` 均为退出码 0，仅有既存 LF→CRLF 提示；本轮明确路径行尾空白检查无匹配。
- 2026-07-21 PK-000 二次复验：三项定向测试、规定 compileall、六个公共 JavaScript `node --check` 全部通过；隔离脚本确认四类保留边界均拒绝且无 registry/runtime/data 残留，最终文档门禁与 `git diff --check` 通过。
- 2026-07-30 增量验证：`server/tests/test_official_module_catalog.py` 通过；使用
  TemporaryDirectory、ASGITransport 和 MockTransport 覆盖离线 GET、显式刷新、
  固定 Release redirect、install/update/rollback、并发重复安装、卸载重启提示、
  确认/Origin、任意 URL、错误摘要、截断、超限、manifest 不一致、traversal、
  symlink、Windows reparse、重复 manifest、缓存刷新失败/last-good 和 catalog
  确定性合成；未访问真实 GitHub 或真实本机状态。
- 2026-07-30 增量验证：`server/tests/test_installable_modules.py` 与
  `server/tests/test_feature_catalog.py` 通过；
  `scripts/build_official_module_catalog.py --validate-catalog` 通过空基线。
- 2026-07-30 增量验证：PK-900 范围 compileall（含 official catalog/service、
  router、Catalog、三项 PK-010 测试和构建工具）通过；PK-180 并行交付的
  `focus@1.1.0` 完整 Catalog 条目通过同一 `validate_official_catalog()`，字段、
  固定 owner/repo/URL 和摘要形态与冻结契约一致，未访问 GitHub 或读取 ZIP 内容。
- 2026-07-30 最终门禁：`scripts/check_task_docs.py` 通过 21 个门禁任务；
  `git diff --check` 退出码 0，仅输出混合工作区既有 LF→CRLF 提示；真实
  `server/data`/`server/runtime` 中没有 `official_module_catalog` 测试状态。
- 2026-07-30 环境说明：迁移期 `server/.venv-asr` 未安装 pytest，故
  `python -m pytest server/tests/test_official_module_catalog.py -q` 不能启动；
  `check_python_test_inventory.py` 在该解释器缺少 `tomllib/tomli`。同一新测试的
  历史单文件入口及全部定向脚本已实际通过，完整 dev-profile pytest/quality gate
  留给 PK-030/PK-900 环境，不伪称执行成功。
- 2026-07-30 共享验证状态：`server/tests/test_dashboard_shell.py` 在 PK-100
  当前并行工作树因公共脚本清单断言失败；PK-010 未修改任何 dashboard HTML/CSS/JS
  或该测试，等待 PK-100 完成其独占共享路径后由三任务批次复跑。
- 2026-07-30 sidecar 定向验证：
  `server/.venv-asr/Scripts/python.exe server/tests/test_installable_modules.py`
  通过；TemporaryDirectory fake adapter 覆盖 QQ 配置缺失、依赖缺失、ready、
  readiness 异常、恶意返回脱敏、启用前阻断、启动恢复、旧 adapter 兼容、固定注册
  防覆盖及无 enabled/registry 半状态，未读取 `.env` 或真实 runtime/data。
- 2026-07-30 sidecar 增量门禁：`test_official_module_catalog.py`、PK-900 范围
  `compileall`、`scripts/check_task_docs.py`（最终复跑 19 个门禁任务）和
  `git diff --check` 通过。`test_feature_catalog.py` 与
  `test_dashboard_shell.py` 当前均在导入共享 `api` 时被 PK-134 并行文件
  `features/rss_intel/provider.py` 的 Python 3.8 运行期类型别名
  `RSSIntelSourceConfig | Mapping[...]` 阻断，尚未进入 PK-010/PK-100 断言；
  本任务未越界修改该共享业务文件，交 PK-134 修复后由集成批次重跑。
- 2026-07-30 sidecar dependency 定向验证：
  `test_installable_modules.py` 与 `test_official_module_catalog.py` 通过；临时目录
  覆盖 dependency root 写入不改变安装树摘要或官方 rollback、启用升级切换到新版本
  descriptor、非 current 旧根不可解析、rollback 切回受信旧包、未安装/恶意
  ID/version/registry path/重叠 root/reparse 拒绝，以及 lifecycle JSON 不含 package
  或 dependency 绝对路径；adapter start/health/stop 异常也折叠为 Core 固定文案，
  不传播路径或上游正文。测试未运行 npm、未创建真实 deployment。
- 2026-07-30 sidecar dependency 最终共享复跑：PK-134 已消除上述 Python 3.8
  导入阻断；`test_feature_catalog.py`、`test_dashboard_shell.py` 均通过。PK-900
  范围 `compileall`、`scripts/check_task_docs.py`（23 个门禁任务）与
  `git diff --check` 同步通过，后者仅输出混合工作区既存 LF→CRLF 提示。

- 2026-07-30 依赖装配定向验证：`test_installable_modules.py` 通过，临时包/fake
  adapter 覆盖 `affection_memory→conversation`、`voice→conversation`、启用的可选
  calendar provider、缺失依赖、current/manifest 版本不一致、cycle、确定性同层
  tie-break、register 中途异常及 `unregister/stop` 逆序回滚、sidecar 正序启动/
  逆序 shutdown、卸载被依赖模块拒绝；所有失败均在临时 registry/runtime/data 下，
  未触碰真实状态。
- 2026-07-30 readiness 映射验证：同一测试逐项断言三个可操作 code 为
  `needs_configuration`、五个安全/完整性/平台 code 为 `unavailable`，未知恶意 code
  折叠为 `adapter_unavailable` 且序列化不含路径或秘密；QQ installable package 的
  10 项 unittest 同步通过。
- 2026-07-30 `network_download` 权限验证：`test_installable_modules.py` 断言
  Python validator、manifest Schema、official Catalog Schema 与 release fragment
  Schema 共享精确闭集；`local_state+network_download` 可安装并在生命周期快照中
  展示，未知权限、重复项和大小写变体均拒绝，既有 `local_state` 包保持兼容。

## 完成文档门禁

- [x] TASK_RECORD — 已记录统一 Core 契约、官方 Catalog/Release、接口矩阵、结构化
  错误、安装前拒绝、无状态残留、README 草案、隔离测试和三任务重验遗留事项。
- [x] TASKS_BOARD — 本轮按 PK-000 指令不修改共享 `TASKS.md`；任务文件在增量实现和
  定向验证通过后恢复“待集成”，等待 PK-010/PK-140/PK-020 共享集成。
- [x] PUBLIC_README — 本轮按 PK-000 串行窗口要求不直接改共享 README；准确最终用户
  草案已写入本任务记录，交 PK-000 在 PK-010 + PK-100 + PK-180 收口时落地。
- [x] MODULE_CATALOG — catalog 与 ModuleManager 共同消费 Core 契约；恶意快照不能覆盖 Core 必需属性或 namespace，并有回归测试。
- [x] ARCHITECTURE_DOCS — 已更新生命周期规范，并新增正式模块作者/Release 契约；
  Schema、包摘要、入口/sidecar、官方目录、下载与静态资源边界均与实际实现一致。
- [x] LOCAL_README — 不适用：本机路径、启动器、解释器、端口和环境位置均未变化。
- [x] AGENT_RULES — 不适用：本任务没有改变 agent 工作流、安全、文档或 Git 规则。
- [x] VALIDATION — 已补充官方目录/下载/缓存/原子性回归并重跑 PK-010、catalog、
  Catalog 构建/焦点条目校验、compileall、文档门禁和 `git diff --check`；
  sidecar readiness/deployment descriptor、版本隔离、官方 rollback 与路径脱敏均已
  纳入 TemporaryDirectory 回归；依赖拓扑、原子逆序回滚及最终 readiness 映射也已
  覆盖。最终 installable/official catalog/feature catalog/dashboard、PK-900
  compileall、23 项任务文档门禁和 `git diff --check` 全部通过。

## 独立对话启动提示

```text
领取 Project Kei 的 PK-010 可安装模块生命周期与加载基础任务。先读取
README.md、AGENTS.md、README.local.md、TASKS.md、
docs/architecture/modular-monolith.md、docs/architecture/installable-modules.md
和本任务文件。第一阶段只实现本地可信包、manifest、注册表和生命周期骨架，
保持 GET /api/v1/modules 与现有业务接口兼容，不迁移具体业务规则。
```

## PK-011 动态导入树清理接缝（2026-07-31）

- 独立 PK-900 复现正式包卸载后仅移除顶层动态 import，`sys.modules` 仍保留
  `<generated_package>.*` 子模块；8 个包分别残留 8/13/5/6/5/5/9/2 项。
- Loader 现通过一个固定 helper 同时删除生成的顶层包名及 `包名 + "."` 前缀的全部
  子模块，并覆盖 import 失败、入口 callable 缺失、register 失败、正常同步/异步
  unload 与 coordinator rollback。它不会匹配或删除其他模块及普通项目 import。
- 永久累计测试使用正式 builder 与临时 Loader/Coordinator 验证正常卸载和注册失败
  后动态 import 树为零。该修复只完善 PK-010 既有进程内卸载原子契约，不改变
  manifest、API、业务规则或个人数据所有权；仍等待 PK-900 再次独立复验。

## PK-100 配置型 sidecar 面板接缝（2026-08-01）

- `ModuleManager.asset_path()` 继续默认拒绝未启用模块的静态资源；唯一受控例外是
  manifest 类型为 `sidecar`、registry 状态为 `needs_configuration` 且明确声明
  dashboard entrypoint 的受信安装模块。该例外只提供包内 dashboard 静态文件，
  不注册业务路由、不启用或启动 sidecar，也不读取其秘密。
- 普通 disabled `in_process`、状态不是 `needs_configuration` 的 sidecar 和越界资源
  仍返回拒绝。临时 ModuleManager 回归已覆盖正常 disabled 拒绝与 QQ 配置面板可读。

## 配置型 sidecar 固定控制接缝（2026-08-01）

- `needs_configuration` sidecar 可装配其固定、同源、非秘密 control facade，使配置
  面板读取 readiness 并保存既有业务 schedule；该接缝不等于启用模块，也不得启动
  进程或接受用户提供的命令、路径、cwd、环境变量。
- QQ 0.1.4 永久回归锁定 manifest、Node package 与 lock 根版本一致，避免安装包可被
  Core 接受但被 PK-020 依赖部署门禁拒绝。

## 浏览器本地 ZIP 导入接缝（2026-08-02）

- 新增仅本机 `POST /api/v1/modules/{module_id}/install-upload`。请求体必须是原始
  `application/zip`，并携带浏览器计算的 `X-Project-Kei-Package-SHA256`；接口不
  接受服务器路径、文件名、URL、owner/repo、Token、Cookie 或 multipart 字段。
- Core 在读取请求体前校验 loopback/Origin、模块 ID、Content-Type、摘要格式和
  已知 Content-Length；随后以 64 MiB 为硬上限流式写入随机系统临时目录并同步计算
  摘要。摘要不符、空包、超限和中断均在调用 ModuleManager 前拒绝，临时目录退出
  自动清理。
- 摘要通过后只调用既有 `ModuleManager.install(..., expected_module_id=...)`；包内
  manifest ID、路径穿越、符号链接/reparse、依赖、冲突、Core 保留边界及原子写入
  沿用同一规则，不维护第二套安装逻辑。响应只增加有限的 received bytes 和摘要，
  不返回临时绝对路径；安装结果仍为停用且不会自动启用或重启。
- 临时 ASGITransport 回归覆盖成功 ZIP、摘要不符、manifest ID 不符、错误媒体类型、
  声明/实际超限、远端客户端拒绝和上传目录零残留；真实 registry/runtime/data、
  个人状态、凭据、缓存和 vendor 均未读取或修改。
- 实际验证：`test_installable_modules.py`、`test_official_module_catalog.py`、
  `test_feature_catalog.py`、相关 `py_compile`、26 项任务文档门禁和
  `git diff --check` 均通过；后者仅有既存 LF→CRLF 提示。

### 本增量完成文档门禁

- [x] TASK_RECORD — 已记录上传接口、大小/摘要/ID 校验、临时文件生命周期、副作用和测试。
- [x] TASKS_BOARD — PK-010 继续保持“待集成”，与 PK-100 一并交 PK-900 累计验收。
- [x] PUBLIC_README — 已增加授权协作者的本地 ZIP 控制台流程和 API 矩阵。
- [x] MODULE_CATALOG — 不适用：未改变 Catalog 条目、manifest 或生命周期字段。
- [x] ARCHITECTURE_DOCS — 已在安装规范冻结原始 ZIP、摘要头、64 MiB 与零路径契约。
- [x] LOCAL_README — 不适用：未改变本机端口、解释器、启动器或私人路径。
- [x] AGENT_RULES — 不适用：未改变 agent 协作、安全或 Git 规则。
- [x] VALIDATION — installable/dashboard 专项、JS 语法、编译、文档和 diff 门禁已记录。

## 浏览器本地 ZIP manifest 身份推导（2026-08-08）

- 保留兼容接口 `POST /api/v1/modules/{module_id}/install-upload`；新增正式入口
  `POST /api/v1/modules/install-upload`。两者继续只接受 loopback + 受信 Origin、原始
  `application/zip` 和 `X-Project-Kei-Package-SHA256`，共享同一个 64 MiB 流式临时
  文件处理函数和同一个 `ModuleManager.install()`，没有复制包校验或生命周期规则。
- 新入口默认不接受安装身份输入，而是以完整 ZIP/manifest 校验后的 `manifest.id`
  为准。查询参数 `expected_module_id` 仅是可选显式核对值；缺省、空字符串或仅空白
  等价于不提供，非空时必须符合模块 ID 闭集并与 manifest 完全一致。兼容路由的路径
  ID 继续作为必填核对值，因此旧调用方行为不变。
- 成功响应继续返回实际 `module_id` 与 `installed_version`，并保留有限的
  `local_upload.status/received_bytes/sha256`。Core 不读取客户端文件名，不接受服务器
  路径、URL、Token、Cookie 或 multipart；选择文件和本机摘要计算不会触发请求，
  只有用户显式点击上传安装才发送 ZIP。
- ID 不匹配仍由 ModuleManager 在临时展开并验证 manifest 后、创建正式版本目录和
  写注册表前拒绝。新增 ASGITransport 临时目录回归连续上传 `qq_bridge` 后再上传另一
  manifest，证明空预期 ID 不会沿用旧 QQ ID；另覆盖残留旧 ID 显式核对时拒绝、兼容
  路由继续核对、误导性文件名不参与身份、失败后 registry 快照不变、正式运行目录和
  上传临时目录均无残留。未读取或修改真实 registry/runtime/data、个人状态或 vendor。
- PK-100 对齐项：本地 ZIP 普通表单改用无路径正式入口，不再要求或从文件名建议模块
  ID；若保留“预期 ID”高级核对框，应在每次重新选文件时清空，空值不得拼入旧路径。
  文件选择仍只做本地摘要，上传按钮才发请求。PK-100 完成后交 PK-900 做累计集成验收。
- 验证：`test_installable_modules.py` 与 `test_official_module_catalog.py` 通过；对
  `server/core/modules`、`server/features/module_manager` 和本专项测试的隔离
  `compileall -q` 通过；`scripts/check_task_docs.py` 通过 25 个 gated tasks；本轮四个
  明确文件的 `git diff --check` 退出 0，仅有既存 LF→CRLF 提示。
- 共享集成待复验：`test_feature_catalog.py` 在导入 PK-140 现有
  `features/qq_control/models.py` 时因当前 Python 无法求值 `str | None` 注解而失败；
  `test_dashboard_shell.py` 因共享 HTML 缺少其既有断言标记
  `pk100-20260802-localzip1` 而失败。两处均不在 PK-010 本轮改动路径，未越界修改，
  交 PK-100/PK-900 在累计集成中处理。任务状态保持“待集成”。

### 本增量完成文档门禁

- [x] TASK_RECORD — 已记录双入口、可选预期 ID、实际响应身份、零残留和 PK-100 交接。
- [x] TASKS_BOARD — `TASKS.md` 已由 PK-000 保持 PK-010“待集成”；本轮按冻结边界未改。
- [x] PUBLIC_README — 不适用：PK-000 冻结 README 共享交接，本轮准确契约已记录于此。
- [x] MODULE_CATALOG — 不适用：未改变模块目录字段、manifest 或生命周期状态。
- [x] ARCHITECTURE_DOCS — 已更新安装规范的无路径入口、可选核对值和兼容语义。
- [x] LOCAL_README — 不适用：未改变端口、解释器、启动器或私人路径。
- [x] AGENT_RULES — 不适用：未改变协作、安全、验证或 Git 规则。
- [x] VALIDATION — 临时 ZIP/registry/runtime/data 的 PK-010 与官方 Catalog 专项、
  隔离编译、文档和范围内 diff 门禁通过；Catalog/QQ 注解与 Dashboard 共享标记两项
  既存集成失败已准确记录并交 PK-100/PK-900，未冒充全绿。

## 官方 Catalog 2026-08-08 不可变资产串行收口

- PK-211 完成最终不可变版本闭环后，独立读取并核对 QQ、voice 与 GPT-SoVITS
  Provider 的 `package_source/manifest.json`、确定性 builder、release fragment、
  catalog entry/README；没有只采信对话摘要，也没有访问真实 runtime、registry、
  模块数据或个人状态。
- 在两个独立系统临时目录分别重建三份 ZIP，两个批次逐字节一致。最终证据为：
  `qq_bridge@0.1.6` / `modules-2026.08.08` / `qq_bridge-0.1.6.zip` / 109140 bytes /
  package SHA-256 `9b9fde6ecf4585c437ddb8de6c29b947d028fc160c3390695210cf919bc4c967` /
  manifest SHA-256 `bfebe6f01d3f889e69e27547cf9b853c55fcb583e83456f5b1d48a1789f36215`；
  `voice@1.0.3` / `voice-1.0.3.zip` / 67448 bytes /
  `7c5bd049b74def7dadeebb91b0a48f1fc8a851528af38b7bb0e6c5b334a27702` /
  `3872e12a006b5f9c3d5e136567ae1e652e1617ab1aebb558cbb07d35d7b9c82f`；
  `gpt_sovits_engine_provider@1.0.1` / `gpt_sovits_engine_provider-1.0.1.zip` /
  93850 bytes / `27a39f7ec930562a152c949d059260ae9ecb428589856f618c6b8d67a36bc5f6` /
  `5a50239a19b552e798079addaf507db5bd878ccfc1a81369cc9cb356b3c45a79`。
- 确定性 Catalog builder 从实际 ZIP 根 manifest 生成三条候选，再与共享
  `server/core/modules/official-catalog.json` 中三条记录做完整字典比较，version、
  tag、asset、size、package/manifest SHA、URL、dependencies、optional dependencies、
  permissions、data policy 与 restart 字段逐字一致。Catalog `generated_at` 同步为
  `2026-08-08T00:00:00Z`；其他模块条目与 owner/repository/publisher 不变。
- 旧 `qq_bridge@0.1.5`、`voice@1.0.2`、`gpt_sovits_engine_provider@1.0.0` Release
  tag/asset 只从“当前推荐目录条目”中被新版本替代；没有创建、写入、上传或覆盖任何
  旧/新 Release ZIP。manifest 自动识别上传入口与 legacy 路由均未修改。
- 验证通过：官方 Catalog schema/字段精确比较、`test_official_module_catalog.py`、
  `test_installable_modules.py`、QQ 13 项安装包测试、voice 安装包测试、GPT-SoVITS
  Provider 安装包测试。所有构建和安装测试使用系统临时目录/fake 状态，无真实网络、
  下载、sidecar、QQ、模型或个人数据副作用。任务保持“待集成”，交 PK-000/PK-900
  累计验收；未改 `TASKS.md`，未暂存、提交、推送或发布。

### 本增量完成文档门禁

- [x] TASK_RECORD — 已记录三条不可变候选、双构建证据、逐字段合并和验证结果。
- [x] TASKS_BOARD — 不适用：PK-010 已为“待集成”，按冻结要求未改共享 `TASKS.md`。
- [x] PUBLIC_README — 不适用：本轮只更新机器可读官方目录，不改变用户操作契约。
- [x] MODULE_CATALOG — 已以实际确定性 ZIP/manifest 更新三条当前官方推荐版本。
- [x] ARCHITECTURE_DOCS — 不适用：上传、生命周期、sidecar 与不可变发布协议未改变。
- [x] LOCAL_README — 不适用：未改变端口、解释器、启动器或本机私人路径。
- [x] AGENT_RULES — 不适用：未改变协作、安全、验证或 Git 规则。
- [x] VALIDATION — Catalog、生命周期、三安装包、文档与范围内 diff 门禁均已执行；
  builder/测试只使用系统临时目录，未读取真实 runtime/registry/个人状态。

## 生产 ModuleHost 重复装配幂等整改（2026-08-08）

- PK-900 完整默认套件稳定复现顺序依赖：`test_module_host_assembly` 留下同一进程级
  ModuleManager 后，后续 production dashboard/local-access reload `api` 会再次构造
  `InstalledModuleHost`；原实现每次新建并注册固定 `gpt_sovits_provider`，Core registry
  因同名重复而在请求/测试前抛 `ValueError`。QQ 注册位于其后，修复不能只绕过首个
  GPT-SoVITS 名称。
- 最小整改放在生产 `module_composition.py`，而不是放宽 `SidecarAdapterRegistry`：
  ModuleManager 只新增无副作用的 Core 内部 `resolve_sidecar_adapter(name)` 查询；host
  仅当现存对象的 `type` 与该固定名称对应的精确官方 adapter 类完全相同时复用原实例。
  不使用 `isinstance`，因此子类、代理或其他实现不能冒充；注册竞态也只吞掉 registry
  唯一稳定的 `sidecar adapter is already registered`，其他 `ValueError` 原样抛出。
- registry 的 `register_sidecar_adapter` 行为保持严格：即使再次提交同一个对象仍拒绝，
  不会静默覆盖。若 `gpt_sovits_provider` 已被 legacy fake/不同实现占用，生产 host
  fail closed，并保留原注册对象不变。没有清空/替换全局 manager、停止 sidecar、
  读取 registry/runtime/个人状态，也没有改变 PK-140/PK-211 adapter、picker、QQ
  配置、Catalog、README 或 `TASKS.md`。
- 永久回归扩展 `test_module_host_assembly.py`：同一临时 manager 连续构造两个 host，
  断言 GPT-SoVITS 与 QQ 均复用首个官方实例；直接重复 registry 注册仍拒绝；不同
  fake adapter 分别预占 GPT-SoVITS 或 QQ 官方名称时仍拒绝且原对象不被覆盖；同一临时
  manager 上导入并 reload `api` 成功，两个官方 sidecar 均解析为首次注册实例，
  installed in-process 模块仍按启动/关闭契约装配与卸载。
- 现有 `server/.venv-asr` 只作为本机已有离线脚本解释器使用，不是目标验收矩阵；
  未安装、升级或修复依赖，未读取/修改环境内部内容，也未启动 ASR、模型、sidecar、
  picker 或外部服务。该解释器通过 module host、PK-010 lifecycle 与 Dashboard shell；
  同一进程逆序夹具 `module_host_assembly -> dashboard production -> local-access api reload`
  通过 local-access 4 项，保护路径 rejected=0、resolve shortcuts=0。
- 环境限制如实保留：项目解释器没有 pytest；本机 base pytest 解释器没有 FastAPI 且
  不接受项目的 asyncio 配置，因此没有混装环境或声称完成默认 pytest。单独运行
  `test_local_access_boundary.py` 仍命中其既有 protected-resolve shortcut，而上述
  PK-900 精确同进程顺序夹具通过。PK-900 必须在其已有、可证明隔离的完整验收解释器
  重跑受影响默认 pytest，确认原 `403 passed + 1 expected skip + 4 setup errors` 中的
  4 个 adapter setup errors 归零。PK-010 保持“待集成”。
- 最终门禁：上述三个改动文件的隔离 `compileall -q` 通过；
  `scripts/check_task_docs.py` 通过 26 个 gated tasks；PK-010 四个相关路径的
  `git diff --check` 退出 0，仅有既存 LF→CRLF 提示。未执行 Git 暂存、提交、推送、
  发布或工作区清理。

### 本增量完成文档门禁

- [x] TASK_RECORD — 已记录根因、最窄修复边界、严格冲突语义、顺序回归和环境限制。
- [x] TASKS_BOARD — 不适用：按 PK-000 冻结要求保持 PK-010“待集成”，未改 `TASKS.md`。
- [x] PUBLIC_README — 不适用：没有用户可见接口、配置、操作或重启语义变化。
- [x] MODULE_CATALOG — 不适用：没有改变模块 manifest、目录字段或发布元数据。
- [x] ARCHITECTURE_DOCS — 不适用：registry 严格契约未改变，只修复生产 composition 幂等。
- [x] LOCAL_README — 不适用：没有改变本机路径、端口、启动器或解释器登记。
- [x] AGENT_RULES — 不适用：没有改变协作、安全、验证或 Git 规则。
- [x] VALIDATION — fake/temp 的 host/reload/冲突/lifecycle/dashboard/同进程 local-access
  以及编译、26 项文档和范围内 diff 门禁已通过。完整默认 pytest 明确交 PK-900
  在既有隔离验收解释器执行，未把当前环境缺失依赖冒充产品通过。

## Manifest 运行时依赖与安装检查增量（2026-08-09）

- manifest v1 新增向后兼容的可选 `runtime_requirements`。当前只接受 Core 冻结的
  Node.js 声明、排序去重的主版本闭集和 `x64`；命令、路径、URL、未知运行时、
  重复项和非 x64 均在安装写入前拒绝。旧包省略该字段时等同空数组。
- 安装、详情和目录响应新增 `dependency_readiness`，逐项返回必需 Project Kei
  模块的 `ready/missing/disabled`；`runtime_readiness` 返回 Node 的
  `ready/missing/version_unsupported/architecture_unsupported`。这些字段只含有限
  枚举和版本/架构，不返回可执行文件路径或命令。
- 缺少电脑运行时的包安全安装为 `needs_configuration`，启用会在 sidecar/业务入口
  前阻断；缺少或未启用的 Project Kei 强依赖仍允许先安装，但启用前再次强制验证。
  模块上传从不执行 manifest 脚本、npm、pip 或下载器。
- 官方 Catalog/fragment schema、解析器、包内 manifest 精确核对与控制台展示已同步；
  QQ 候选以真实确定性 ZIP/manifest 摘要更新，其他旧 manifest 与 Catalog 条目保持
  兼容。临时构建和安装均未触碰真实 registry/runtime/个人状态。
- 回归证据：PK-010 生命周期脚本通过；官方 Catalog 脚本通过；19 模块确定性重建、
  Catalog 摘要与临时安装/卸载/重装通过；Dashboard shell 通过；JS 语法通过。

### 本增量完成文档门禁

- [x] TASK_RECORD — 已记录字段、状态、失败语义、数据副作用和测试。
- [x] TASKS_BOARD — 已由 PK-000 将 PK-010 重新登记为“待集成”。
- [x] PUBLIC_README — 已同步用户可见 Node 支持和显式依赖安装说明。
- [x] MODULE_CATALOG — QQ 0.1.7 候选及 runtime 声明已同步；未发布。
- [x] ARCHITECTURE_DOCS — 生命周期与模块包交互规范已同步。
- [x] LOCAL_README — 不适用：未改变任何本机私有路径或配置。
- [x] AGENT_RULES — 不适用：安全和协作规则未改变。
- [x] VALIDATION — 生命周期、Catalog、19 模块、控制台和静态门禁已执行。

## 远端矩阵空运行时字段兼容修复（2026-08-10）

- 合并提交 `d537e5a` 的 Windows 矩阵确认 Node 22/24/26 全部通过；Python
  3.10/3.11/3.12/3.13 均在同一组 7 个旧模块发布元数据断言失败。失败不是解释器兼容
  问题，而是 Catalog builder 把省略的可选 `runtime_requirements` 强制物化为 `[]`。
- 冻结兼容规则为：无运行时依赖时，官方 Catalog 文件、缓存 wire payload 和公开模块
  字典继续省略该可选字段；存在声明时必须完整输出。QQ 的 Node 20/22/24/26 x64 声明
  因此保留，旧模块的 release fragment、Catalog entry、ZIP 和摘要无需改动。
- 永久回归同时覆盖旧模块省略字段和 QQ 非空字段保留；原远端失败的 7 个包测试及官方
  Catalog 专项均在本地逐项通过。任务仍为“待集成”，等待修复提交后的完整远端矩阵。
