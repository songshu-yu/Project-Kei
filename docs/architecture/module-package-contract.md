# Project Kei 模块包交互与发布契约

## 文档分工

本文件面向模块作者、维护者和 Release 审核者，说明一个模块如何与已经实现的
PK-010 Core 交互、测试和发布。总体生命周期、Core 首次安装集合和产品边界仍见
[可安装模块生命周期规范](installable-modules.md)；本文件只描述当前代码已经支持
的包级接缝，不预告不存在的远程商店、热卸载或脚本安装能力。

## 包根与 manifest

ZIP 解压后的根必须直接包含 `manifest.json`，不能再套一层目录：

```text
manifest.json
backend.py                 # in_process 的 backend.register
dashboard/index.js         # 可选
config.schema.json         # 可选，只声明配置需求
```

正式 Schema 是 `server/core/modules/manifest.schema.json`，运行时校验器是
`server/core/modules/manifest.py`。当前 `schema_version` 固定为 `1`，未知字段
直接拒绝。最小 `in_process` 示例：

```json
{
  "schema_version": 1,
  "id": "example",
  "name": "示例模块",
  "version": "1.0.0",
  "type": "in_process",
  "required": false,
  "core_compatibility": ">=1.0.0 <2.0.0",
  "entrypoint": "backend.register",
  "dependencies": [],
  "optional_dependencies": [],
  "runtime_requirements": [],
  "conflicts": [],
  "api_namespaces": ["/api/v1/example"],
  "legacy_endpoints": [],
  "dashboard_entrypoint": "dashboard/index.js",
  "data_namespace": "example",
  "config_schema": null,
  "permissions": ["local_state"],
  "requires_restart": true
}
```

ID 和数据 namespace 只能使用小写字母、数字与下划线；版本使用 SemVer。
`core_compatibility` 在正式目录写入前校验。第一版唯一批准权限是
`local_state` 与 `network_download`；增加权限、模块类型或 manifest 字段必须先由
PK-000 修改契约。权限数组是大小写敏感、不可重复的闭集，未知权限 fail closed。

`network_download` 不是通用网络权限。它仅允许模块在用户显式触发并确认后，从模块
代码或受版本控制 Catalog 固定的 HTTPS allowlist 下载已知资产。实现必须逐跳验证
重定向主机，限制连接/读取/总超时，核对精确字节数和 SHA-256，并把下载内容当作
不可执行数据。浏览器、manifest、普通配置均不得提供 URL、header、cookie、token、
proxy、shell 或 allowlist；页面加载、启动、普通 GET 和后台任务不得自动联网。
Catalog 与生命周期 API 只原样展示声明，不因该字段自行联网。
包不能包含 `.env`、凭据、缓存、模型、个人状态、BAT、PowerShell 或要求 Core
执行的安装脚本。

## Core 生命周期状态机

```text
官方目录/本地高级导入
  -> 下载或读取显式包
  -> SHA-256、ZIP 和 manifest 校验
  -> Core ID/namespace、兼容、依赖、冲突校验
  -> 临时展开
  -> 原子移动到 runtime 版本目录
  -> 原子注册
  -> installed_disabled / needs_configuration
  -> enable
  -> enabled（in_process 可能 restart_required）
  -> disable / update / rollback / uninstall
```

- 安装失败不写注册表、不创建正式版本目录或模块数据目录。
- 安装成功响应立即包含 `dependency_readiness` 与 `runtime_readiness`。缺少必需模块、
  模块尚未启用或电脑运行时不匹配会被明确展示；电脑运行时不满足时模块保持
  `needs_configuration`，不会进入启动接缝。
- 启用前重新检查依赖、冲突和必需配置。
- 更新写入新版本目录，成功后保留前一版本用于回滚；失败保持旧版本。
- 卸载默认只删除程序版本，返回 `data_preserved=true`。
- `purge-data` 是独立危险操作，确认值必须与路由中的 module ID 完全一致。
- `last_operation` 使用 `action/status/message/at`；目录与成功操作同时返回
  `available_actions`、`requires_restart` 和 `restart_required`。

## Python 后端接缝

第一版 loader 只支持单层公开 `module.callable`，例如 `backend.register`。Core
在应用重启装配时实际调用：

```python
def register(app):
    @app.get("/api/v1/example/status")
    async def status():
        return {"ready": True}
```

当前唯一传入对象是 FastAPI `app`；没有文件系统、注册表、ModuleManager、凭据或
通用 service container context。模块可以导入自己包内代码，但不得反向 import
`core.*`、其他 `features.*` 的内部实现或直接修改它们的状态。跨模块协作只能通过
已冻结的公开 HTTP/service 契约和 manifest 依赖表达。入口导入或注册失败时该模块
记录为 `broken`，不能阻断其他模块装配。

## HTTP namespace 与兼容接口

每个新 API 必须落在 manifest 的 `api_namespaces` 中。`legacy_endpoints` 只登记该
模块确实拥有、并委托同一 service 的兼容路径；不得用 legacy 列表声明其他模块
接口。安装器拒绝已安装模块之间的 namespace 冲突，也拒绝 Core 保留 ID
`catalog/module_manager/dashboard` 和 `/api/v1/modules`、
`/api/v1/dashboard` 的相同、父级或子级 namespace。

模块面板的公共请求封装只允许该模块声明的 namespace/legacy 路径；声明不等于
绕过后端认证、loopback、Origin 或业务权限检查。

## Dashboard 接缝

`dashboard_entrypoint` 必须位于包根 `dashboard/` 中。启用模块的入口由 Core
映射为同源 `/api/v1/modules/<module_id>/assets/...`，其他包文件不会被静态读取。
ES module 必须导出 `mount(context)`，可以导出 `unmount()`：

```javascript
export async function mount(context) {
  context.root.textContent = '模块已加载';
  const state = await context.request('/api/v1/example/status');
  context.notify(state.ready ? '已就绪' : '需要处理');
}

export function unmount() {}
```

当前 context 只有：

- `root`：该模块独占的 DOM 根；
- `module`：不可变模块目录快照；
- `catalog`：不可变目录快照；
- `request`：只允许本模块声明路径的同源请求函数；
- `notify`：带模块名称的公共通知函数。

模块不得访问其他模块 DOM、注册表、本地文件或把业务配置复制到浏览器存储。
入口必须同源，装载超时为 10 秒；404、无 `mount` 或抛错只影响本模块卡片。

## 配置、秘密、日志与错误

`config_schema` 只能声明字段和可选 `x-env-var` 名称。秘密值只存在本机环境，不写
manifest、catalog、注册表、日志、错误响应或浏览器。配置检查只返回缺少的字段名。
模块错误必须有限、结构化且不包含完整上游正文、路径、Token、Cookie、用户内容或
调用栈。模块只能写 `server/data/modules/<data_namespace>/`；不得读取、覆盖或迁移
其他 namespace。安装 ZIP 永远不能携带用户数据，升级也不能覆盖数据目录。

## in_process 与 sidecar

- `in_process` 在 API 装配时注册路由。启用、停用、更新、回滚以及已装载模块的
  卸载可能返回 `restart_required=true`；Core 不承诺从运行中 Python 进程热移除
  路由。
- `sidecar` manifest 只能声明 Core 已注册的 adapter 名称和健康检查超时。manifest
  不能提供命令、可执行文件路径或 shell。停用必须通过 adapter 停止其后台任务；
  停止失败进入 `broken`，不能伪装成功。

受审查 adapter 由生产 composition 调用
`features.module_manager.service.register_core_sidecar_adapter(name, adapter)` 显式注册。
同名 adapter 不能静默替换，manifest 只负责引用固定名称，不能声明 path、command、
cwd 或 env。QQ bridge 的 adapter、配置根和状态根由 PK-140 实现；ModuleManager
不会读取 QQ `.env`。

安装包程序树固定在
`server/runtime/modules/<module_id>/<version>/`，由 Core 视为永久只读；
`installed_tree_sha256` 覆盖包内整个目录，不能排除 `node_modules` 或任何其他
子树。可再生成的 Node 依赖必须写入独立的
`server/runtime/module-dependencies/<module_id>/<version>/`，不能写回包目录。
该依赖部署根不参与包摘要或官方 rollback 信任判断。

PK-020 和受审查 adapter 只能通过 Core 内部
`features.module_manager.service.resolve_sidecar_deployment(module_id, version=None)`
获得冻结的 `SidecarDeploymentDescriptor`：

- `module_id`
- 当前安装的 `version`
- 只读 `package_root`
- 可再生成的 `dependency_deployment_root`
- `installed_tree_sha256`

解析器只接受当前注册版本，核对模块 ID、SemVer、注册表精确相对路径、运行根
containment、包目录和依赖目录中的 symlink/reparse。未安装、非 sidecar、非当前
版本、路径越界或 link 均 fail closed。descriptor 没有 JSON 序列化接缝，绝对路径
不得进入生命周期响应或日志；adapter 的 start/health/stop 异常正文也由 Core
折叠为固定错误。PK-010 不创建依赖目录、不运行 npm；PK-020 负责生成 deployment，
版本切换后必须重新解析，不能继续使用旧 descriptor。
依赖部署完成标记文件名固定为 `.project-kei-deployment.json`，位于对应版本的
`dependency_deployment_root` 根。其布局和字段由 PK-020/PK-140 冻结并消费；
PK-010 不读取或解释 marker，也不根据 marker 改写 readiness。

新的 descriptor-aware adapter 实现四个内部方法：

```python
from core.modules import SidecarReadiness

def deployment_readiness(self, manifest, deployment):
    return SidecarReadiness.from_code(
        "qq_env_missing",
        ("qq_app_id", "qq_access_token"),
    )

def start_deployment(self, manifest, deployment):
    ...

def stop_deployment(self, manifest, deployment):
    ...

def is_deployment_healthy(self, manifest, deployment):
    return True
```

Core 会再次归一化结果，响应只包含
`status/code/message/missing_requirements`。状态固定为 `ready`、
`needs_configuration` 或 `unavailable`；当前受支持 code 为 `ready`、
`legacy_healthcheck`、`qq_env_missing`、`configuration_missing`、
`dependencies_missing`、`deployment_missing`、`node_missing`、
`runtime_missing`、`platform_unsupported`、`deployment_invalid`、
`integrity_mismatch`、`package_tampered`、`entrypoint_missing`、
`adapter_unavailable`。message
由 Core 按 code 生成，missing requirement 只能是小写安全标识符。adapter 抛出的
异常文本、`.env` 内容、秘密、绝对路径、命令和上游错误体都不会进入注册表或响应。

缺配置或运行依赖时，安装/配置检查返回 `install_status=needs_configuration`，
并附 `sidecar_readiness`；启用在调用 `start()` 前以结构化
`sidecar_needs_configuration` 冲突阻断，不产生 enabled 半状态。API 重启恢复已启用
sidecar 时若 readiness 不再满足，也记录/返回 `needs_configuration`，不误标
`broken`。只有 readiness 已就绪而启动或健康检查真正失败时才进入 `broken`。未实现
descriptor 方法的旧 `start/stop/is_healthy` adapter 使用 `legacy_healthcheck`，
继续保持原有启停和健康检查行为；新 adapter 不应自行拼接或扫描磁盘路径。

readiness code 与状态的 Core 稳定映射如下：`dependencies_missing`、
`configuration_missing`、`deployment_missing` 属于
`needs_configuration`；`deployment_invalid`、`integrity_mismatch`、
`package_tampered`、`runtime_missing`、`platform_unsupported` 属于
`unavailable`。兼容 code `qq_env_missing` 仍是 `needs_configuration`，
`node_missing` 与 `entrypoint_missing` 仍是 `unavailable`。未知 code 不透传，
统一折叠为 `adapter_unavailable/unavailable`。前一类允许用户通过受控配置或
PK-020 dependency deployment 修复，后一类是安全、完整性或平台故障，不能靠重填
配置绕过。

模块依赖装配只消费 manifest v1 已存在的 `dependencies` 与
`optional_dependencies`。Core 在进程启动时先完整预检已启用图；强依赖缺失、未
启用、当前版本/manifest 不一致或不可用，以及 self-cycle/cycle，都会在任何
`register`/sidecar start 前拒绝。同层按 module ID 字典序；强依赖与已启用的可选
依赖先于消费者。`register` 与 sidecar start 共用该顺序，shutdown 和失败回滚严格
逆序调用可选的同模块 `unregister(app)` 或 sidecar stop。模块作者不得依赖文件系统
枚举或 Python import 偶然顺序。

manifest v1 还允许可选 `runtime_requirements`；当前只接受声明式
`{"id":"node","supported_major_versions":[20,22,24,26],"architecture":"x64"}`。
Core 只用固定探针检查 Node 版本与架构，不执行 manifest 提供的命令，也不接受
manifest 路径。安装模块不会静默运行 npm；QQ 的锁定依赖必须由用户显式运行
`setup.bat --profile qq`，并部署到包目录之外的可再生成依赖根。

正式 `in_process` 包必须公开幂等 `unregister(app)`。`register(app)` 应记录本次
实例实际新增的路由、`app.state` 对象、Provider、Collector 与 middleware 描述符，
中途失败时立即逆序回滚；`unregister` 只按对象身份解除仍由本实例持有的接缝，不能
清除宿主或其他实例后来替换的对象。Collector 使用 `CollectorRegistry.unregister`
的 collector 身份参数。middleware 只允许删除本次 `add_middleware()` 后在
`user_middleware` 中识别出的精确描述符；装配冻结前可回滚列表，不能清空全局
middleware 或重建已冻结的 `middleware_stack`。Core loader 仍以路由快照提供最后
一道回滚，但模块不能依赖该快照掩盖 Provider、Collector 或中间件泄漏。

## Official Catalog v1 与集中式 GitHub Release

官方分发身份固定为仓库 `songshu-yu/Project-Kei-Modules`。普通用户和浏览器不能
提交 owner、repo、URL、Token 或代理配置。Catalog 源、Schema 和空离线基线分别为：

- `server/core/modules/official-catalog.json`
- `server/core/modules/official-catalog.schema.json`
- `server/core/modules/official-release-fragment.schema.json`

每个 Catalog 条目固定 module ID/名称/版本/Core 范围、根 manifest SHA-256、
Release asset URL、精确字节数、ZIP SHA-256、tag、asset 名、依赖、权限、数据
策略和重启语义。资产命名使用 `<module_id>-<semver>.zip`；同一验证批次的 19 个
模块共享不可复用的批次 tag，例如 `modules-2026.08.02`，并作为同一 Release 的
不同附件上传。同 tag/asset 不得替换内容；任一附件内容改变都必须提升模块 SemVer
并创建新的批次 tag，Catalog 只能指向已经完整上传并核验的批次。

模块任务提供通过
`server/core/modules/official-release-fragment.schema.json` 的公开元数据片段和
确定性 ZIP。PK-000 在发布前使用：

```powershell
server/.venv-asr/Scripts/python.exe scripts/build_official_module_catalog.py `
  --fragment <focus-release-fragment.json> `
  --asset-root <release-assets-directory> `
  --generated-at <UTC timestamp> `
  --output server/core/modules/official-catalog.json
```

工具从 ZIP 直接计算字节数、包摘要和根 manifest 摘要，核对片段与 manifest，
拒绝重复版本、非官方 URL、摘要/兼容性/字段不一致，并按 module ID/版本稳定排序。
`--check` 验证相同输入能精确重建受跟踪 catalog；
`--validate-catalog` 只验证现有源文件。PK-011 当前官方目录精确包含 19 个可安装
业务项；三项 Core `module_manager`、`catalog`、`dashboard` 永远不列为
downloadable。目录进入仓库不等于资产已经发布：只有同一提交的 PK-900 全量验收
通过并把全部不可变 ZIP 上传到集中批次 Release 后，用户端安装动作才具备真实下载
闭环。PK-010 本身不上传 Release、不执行 GitHub 发布；旧的逐模块 Release 只作兼容
保留，不进入新 Catalog。

## 获取、缓存与离线行为

- `GET /api/v1/modules/official-catalog` 只读最后有效缓存或内置基线，不联网。
- `POST /api/v1/modules/official-catalog/refresh` 才匿名读取固定官方 catalog URL。
- `install-official/update-official` 只从本机已验证目录选择固定版本，再访问其固定
  GitHub Release asset；`rollback-official` 不联网，只允许已安装且仍匹配 catalog
  与本地内容摘要的前一官方版本。
- 下载关闭环境代理继承，不发送 Authorization，手工限制重定向到受信 GitHub
  Release asset 主机，限制目录 1 MiB、ZIP 64 MiB、逐块计算摘要并使用随机临时目录。
- 断网、限流、超时、非法重定向、截断、超限、摘要不符、恶意 ZIP 或 manifest
  不一致都会清理临时文件；刷新失败保持最后有效目录，Core 和已安装模块离线可用。

## 最小测试与禁止项

模块 Release 至少必须测试：Schema/兼容性、确定性包与摘要、Core ID/namespace、
依赖/冲突、安装/启用/停用、更新/回滚、卸载保留数据、精确 purge 确认、
`restart_required`、dashboard 入口/请求隔离，以及 traversal、绝对路径、重复
路径、symlink/reparse 和失败原子性。

HTTP 测试使用 ASGITransport；下载使用 MockTransport/fake downloader；registry、
runtime、data、catalog、ZIP 全部位于 `TemporaryDirectory`。禁止真实 GitHub、
任意 URL、`git pull` 当前源码树、远程脚本、静默依赖安装、LAN 管理入口、真实
个人状态、`.env`、缓存、模型、付费调用、QQ 消息或 vendor。
