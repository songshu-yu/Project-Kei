# Project Kei 可安装模块生命周期规范

## 目标

Project Kei 的首次安装只提供一个可稳定启动的基础集合，用户以后按需安装、配置、启用、停用、升级或卸载其他功能。该能力建立在[模块化单体规范](modular-monolith.md)之上，不改变“一个 FastAPI 主进程”的总体架构，也不要求把每个功能拆成微服务。

本规范定义模块包和运行生命周期；PK-010 实现固定官方 GitHub/Gitee 双镜像目录、
本地高级导入和动态加载，各业务模块仍由自己的 `PK-xxx` 任务迁移。模块作者的
真实代码接缝、打包、测试和发布门禁见
[模块包交互与发布契约](module-package-contract.md)。

## 首次安装集合

首次安装集合必须能够在没有 Node.js、ASR 模型、GPT-SoVITS、QQ 凭证和情报来源配置的情况下启动。建议固定包含：

- FastAPI 应用装配、配置、日志、错误处理和健康检查；
- 模块目录、模块管理器和本地模块注册表；
- 控制台公共外壳与功能中心；
- Kei 人格、基础文字对话和 LLM 方案配置；
- 最小对话上下文及模块共用的本地存储基础设施。

首次安装集合中的必需模块可以使用与可选模块相同的 manifest，但标记为 `required`，不能在控制台卸载或停用。语音、QQ、每日情报、信息源监控、个人成长和效率工具默认属于可选模块。

## 模块类型

| 类型 | 运行方式 | 适用范围 | 生命周期要求 |
|---|---|---|---|
| `in_process` | 注册到 FastAPI 主进程，共用 `8000` | 对话扩展、每日情报、斩妖、健身、专注、日历等 Python 业务 | 安装、升级、启用或停用后允许要求重启 API |
| `sidecar` | 独立进程、运行环境或端口，由 Core 监控 | QQ bridge、faster-whisper ASR、GPT-SoVITS | 可独立启动/停止；必须提供健康检查和明确的外部依赖说明 |

不得仅为了可安装而把普通业务模块改成 sidecar。新模块类型需要由 `PK-000` 确认后才能加入规范。

## 开发源码、安装产物和用户数据

- 仓库开发源码继续位于 `server/features/<module_id>/`，遵守 `router -> service -> repository`。
- 打包后的本机安装产物使用独立版本目录，例如 `server/runtime/modules/<module_id>/<version>/`；该目录是本机可再生成状态，不进入功能提交。
- 模块注册表使用本机状态文件，例如 `server/data/module_registry.json`，记录当前版本、启用状态和安装结果，不记录密钥。
- 新模块的数据默认放入 `server/data/modules/<module_id>/`，安装包升级不得覆盖它。
- 现有已经跟踪或已经投入使用的数据文件保持原位，迁移前必须由对应功能任务单独制定兼容与回滚方案。

最终运行目录可由 `PK-010` 根据 Windows 打包方式调整，但必须保持“程序、安装状态、用户数据”三者分离。

## 模块包结构

一个标准模块包至少包含：

```text
<module-package>/
├── manifest.json             # 身份、兼容性、入口、依赖和权限声明
├── backend/                  # in_process 后端入口；无后端时可省略
├── dashboard/                # 控制台面板入口与静态资源；无面板时可省略
├── migrations/               # 版本化数据迁移；无迁移时可省略
├── checks/                   # 离线健康检查定义；可省略
└── sidecar/                  # 独立组件启动描述；仅 sidecar 使用
```

安装器只能执行 Core 支持的声明式操作。模块不得通过 manifest 要求执行未审查的任意 PowerShell、批处理或 Python 安装脚本。

## Manifest 最小契约

第一版 manifest 采用以下字段；正式 JSON Schema 已固化在 `server/core/modules/manifest.schema.json`，运行时校验器位于 `server/core/modules/manifest.py`：

```json
{
  "schema_version": 1,
  "id": "focus",
  "name": "专注计时",
  "version": "1.0.0",
  "type": "in_process",
  "required": false,
  "core_compatibility": ">=1.0.0 <2.0.0",
  "entrypoint": "backend.register",
  "dependencies": [],
  "optional_dependencies": [],
  "runtime_requirements": [],
  "conflicts": [],
  "api_namespaces": ["/api/v1/focus"],
  "legacy_endpoints": ["/focus/status", "/focus/start", "/focus/stop", "/focus/reset"],
  "dashboard_entrypoint": "dashboard/index.js",
  "data_namespace": "focus",
  "config_schema": "config.schema.json",
  "permissions": ["local_state"],
  "requires_restart": true
}
```

约束如下：

- `id` 永久稳定，只能使用小写字母、数字和下划线；不得通过改名规避升级兼容。
- `version` 使用语义化版本；`schema_version` 表示 manifest 格式版本。
- `core_compatibility` 必须在安装前验证，不兼容时不得部分安装。
- `dependencies` / `optional_dependencies` 只声明 Project Kei 模块 ID；安装结果会
  返回必需模块的 `ready`、`missing` 或 `disabled` 检查，启用前再次强制验证。
- `runtime_requirements` 只声明 Core 支持的电脑运行时及版本/架构闭集。当前唯一
  支持项是 Node.js x64；不得包含命令、路径、下载地址或安装脚本。旧 manifest
  省略该字段时等同空数组。
- `entrypoint` 只能指向模块包内部的受支持注册入口。
- `api_namespaces` 不得与已安装模块冲突；旧接口必须列入 `legacy_endpoints` 并调用同一 service。
- `permissions` 必须最小化；闭集为 `local_state` 与 `network_download`，新增权限名称
  仍需要 `PK-000` 审批。
- 敏感配置只声明字段及是否必需，不在 manifest、日志、浏览器存储或模块注册表中保存值。
- 第一版 `entrypoint` 使用单层 `module.callable` 形式，例如 `backend.register`；Core 在 API 装配时以 `register(app)` 调用，模块停用后需要重启才能确保旧路由不再装配。
- `network_download` 只表示模块可能在用户显式触发并再次确认后，从模块代码或受版本
  控制 Catalog 固定的 HTTPS allowlist 做有界下载。实现必须逐跳重验重定向主机，
  限制连接、读取和总超时，核对精确字节数与 SHA-256，且不得执行下载内容。
  浏览器、manifest 和普通配置不能提供或覆盖 URL、header、cookie、token、proxy、
  shell 或 allowlist；页面加载、Core/模块启动、普通 GET 与后台任务不得自动联网。
  该权限只进入目录和生命周期展示，不会令 Core 自动创建下载客户端或授予任意网络。
- `sidecar` 额外声明 `sidecar.adapter` 和可选的本地健康检查超时。adapter 必须由
  Core 生产 composition 显式注册；manifest 不能声明 path、command、cwd、env、
  命令行或 shell 脚本。新 adapter 可返回 Core 归一化的
  `ready/needs_configuration/unavailable` readiness；缺 QQ 配置、Node.js、依赖或
  固定入口时只返回稳定 code、Core 固定 message 和安全 requirement 名，不返回
  `.env` 值、绝对路径、命令或上游错误体。缺失项会进入
  `needs_configuration`，不会误记为 `broken`；旧三方法 adapter 继续兼容。
- 安装程序树 `server/runtime/modules/<id>/<version>/` 是不可变包内容，
  `installed_tree_sha256` 覆盖全部子树。Node 等可再生成依赖只能部署到 Core 内部
  `server/runtime/module-dependencies/<id>/<version>/`。ModuleManager 只为当前安装
  版本产生包含 module/version、只读 package root、dependency root 与安装树摘要的
  内部 descriptor，并拒绝非当前版本、越界和 symlink/reparse；该 descriptor 及
  绝对路径不进入公开 API。依赖部署树不参加包摘要和官方 rollback 校验，PK-010
  不运行 npm，PK-020 负责生成，受审查 sidecar adapter 只消费 descriptor。
  版本部署 marker 文件名固定为 `.project-kei-deployment.json`；PK-010 只冻结
  名称和安全根，不解析 marker 内容，布局及字段由 PK-020/PK-140 负责。

### Core 保留身份与 namespace

Core 保留契约的唯一代码来源是 `server/core/modules/contracts.py`，ModuleManager、模块目录和回归测试必须共同消费它，不能分别维护 ID 或 namespace 常量副本。

- 保留模块 ID：`catalog`、`module_manager`、`dashboard`。本地可选包不得安装或升级为这些 ID，生命周期快照也不得覆盖其 `required=true`、`managed=false`、`source=core_builtin` 和 Core namespace 属性。
- Core namespace：`/api/v1/modules` 是当前目录、生命周期和模块资产路由的实际边界；`/api/v1/dashboard` 为必需 dashboard 模块的保留目标 namespace。两者及其斜杠分隔的子 namespace 均不能由本地包声明。
- 比 Core namespace 更宽、会包含 Core 路由的父 namespace 同样冲突；名称仅相似但不在同一斜杠边界内的路径不视为冲突。
- 保留校验在创建 `server/runtime/modules/<id>/<version>/` 或写入 `server/data/module_registry.json` 之前完成。失败包只存在于自动清理的临时校验目录。
- 可选模块可以依赖始终启用的 Core 模块，但不能声明与必需 Core 模块冲突。

本地高级导入可以使用目录或 ZIP。维护者路径接口必须同时提供包路径和预先计算的
SHA-256；目录使用按相对路径和内容生成的确定性摘要，ZIP 使用归档文件摘要。
控制台另提供浏览器本地 ZIP 接缝：用户选择文件并点击安装，浏览器在零网络条件下
计算 SHA-256，再以原始 `application/zip` 请求体上传；Core 从已验证的包内 manifest
取得实际模块 ID。调用方可以附带可选的预期模块 ID 作显式核对，但文件名和旧表单
状态都不能决定安装身份。Core 限制 64 MiB、流式写入自动清理的系统临时目录、重新
计算摘要，再委托同一 ModuleManager。该接缝不接受文件路径、任意 URL、Token、
Cookie 或 multipart 表单。普通在线产品入口则从固定
`songshu-yu/Project-Kei-Modules` 官方 Catalog v1 选择版本。只有显式刷新或确认
安装/更新才联网；所有远端包仍委托同一个 ModuleManager 校验和安装。

## 依赖规则

- `dependencies` 是启用当前模块所必需的模块；安装器必须先计算完整依赖图并检测循环依赖。
- `optional_dependencies` 缺失时只能关闭对应增强能力，不能让模块整体不可用。
- `conflicts` 命中已启用模块时，安装器必须停止并解释冲突，不得静默停用另一模块。
- Core 版本、Python/Node 版本、GPU、模型大小、端口和磁盘空间属于环境前置条件，必须在下载大型资源前展示并检查。
- 依赖安装必须锁定版本并可复现。`in_process` 模块不得引入与 Core 运行环境冲突的依赖；重型或需要独立依赖栈的能力应使用 `sidecar`。

API 进程每次启动先由 `ModuleManager.enabled_activation_descriptors()` 对全部已启用
可选模块做一次无副作用预检，再执行任何 `backend.register` 或 sidecar start：

- 强依赖必须已安装、当前版本记录与已验证 manifest 一致、已启用且配置可用；当前
  manifest v1 只声明模块 ID，没有依赖版本范围，因此版本满足的实际含义是 current
  SemVer、当前版本 manifest 与 Core compatibility 均有效，不能臆造未实现的范围。
- 已安装且已启用的 optional dependency 形成排序边；缺失或停用的 optional
  dependency 不阻断。
- 拓扑排序按层执行，同层按 `module_id` 字典序，in-process register 与 sidecar
  start 消费同一序列。缺失、版本不一致、self-cycle 或 cycle 均在第一个运行副作用
  前拒绝，错误只包含稳定原因和模块 ID。
- 任一步失败时，已成功步骤按严格逆序执行 `unregister` 或 sidecar stop；API
  shutdown 同样使用成功装配序列的逆序。仍有已启用强依赖消费者时，disable 和
  uninstall 继续 fail closed。

## 状态模型

模块目录至少区分以下状态：

| 状态 | 含义 |
|---|---|
| `available` | 可安装，但本机没有安装产物 |
| `installing` | 正在校验、下载或准备依赖 |
| `installed_disabled` | 已安装但未启用 |
| `needs_configuration` | 已安装，缺少必需的本地配置 |
| `enabled` | 已装配到 API 或 sidecar 已获准运行 |
| `update_available` | 当前版本可用，另有兼容更新 |
| `broken` | 文件、依赖、迁移或健康检查失败，需要修复或回滚 |
| `uninstalling` | 正在移除程序文件，不代表删除用户数据 |

注册表还应保留最近一次操作结果和可回滚版本，但不得保存凭证、Cookie、个人内容或完整异常响应。

## 生命周期

### 安装

```text
读取 manifest
-> 检查来源、哈希/签名与 Core 兼容性
-> 解析依赖、冲突、磁盘和环境条件
-> 在临时目录下载并展开
-> 验证包内路径和声明入口
-> 准备依赖与迁移计划
-> 原子移动到版本目录
-> 更新本地注册表
-> 根据声明提示配置或重启
-> 执行不触发付费/外部副作用的健康检查
```

任一步失败都不得留下“看似已安装”的半成品状态；临时文件应安全清理，旧版本继续可用。

### 启用和停用

- 启用前重新检查必需依赖、配置和端口；缺少条件时进入 `needs_configuration` 或 `broken`。
- 动态业务入口默认只为已启用模块提供。受信安装且处于 `needs_configuration` 的
  `sidecar` 可以只暴露 manifest 声明的 dashboard 静态入口，用于显示脱敏状态、
  配置指引和显式启动操作；这项例外不得注册业务路由、启动进程、读取秘密或把模块
  伪装成已启用。普通停用的 `in_process` 模块及其他 sidecar 仍不得读取静态入口。
- 停用必须停止模块自己的定时任务、后台循环和 sidecar，不得影响其他模块。
- `in_process` 路由通常在应用启动时装配，因此启用或停用可以要求重启 API；第一版不承诺无重启卸载 Python 路由。
- 每个正式 `in_process` 包必须提供幂等 `unregister(app)`，在启动装配失败和进程
  shutdown 时按实例身份释放自己的 Provider、Collector、状态引用和可安全移除的
  middleware；这项进程内清理不改变产品层仍需重启才能应用启停/升级的语义。
- 必需模块不得停用。其他模块不得直接修改注册表绕过生命周期管理器。

### 升级和回滚

- 新版本安装到新的版本目录，不覆盖当前可运行版本。
- 数据迁移必须有版本号、幂等性说明和失败处理；不可逆迁移必须在确认前明确提示。
- 只有新版本装配和健康检查通过后才切换当前版本。
- 切换失败时回滚程序版本；若数据迁移不可回滚，必须阻止自动升级并要求单独备份确认。

### 卸载和清除数据

- 默认“卸载”只移除模块程序和可再生成依赖，保留配置、个人状态和历史数据。
- “清除模块数据”是独立的破坏性操作，必须列出准确目录并二次确认，不能与卸载按钮合并执行。
- 被其他已启用模块依赖时不得卸载，除非用户明确确认一并停用或卸载完整依赖链。
- 必需模块不得卸载；缓存清理也不得顺带删除个人状态。

## Core 接口

现有 `GET /api/v1/modules` 保持只读和向后兼容，并逐步增加可选字段，例如版本、类型、安装状态、启用状态、依赖、配置状态和重启要求。旧客户端忽略新增字段后仍能工作。

生命周期接口建议统一为：

```text
GET    /api/v1/modules
POST   /api/v1/modules/{module_id}/install
POST   /api/v1/modules/install-upload
POST   /api/v1/modules/{module_id}/install-upload
POST   /api/v1/modules/{module_id}/enable
POST   /api/v1/modules/{module_id}/disable
POST   /api/v1/modules/{module_id}/update
POST   /api/v1/modules/{module_id}/rollback
POST   /api/v1/modules/{module_id}/configuration/check
DELETE /api/v1/modules/{module_id}
POST   /api/v1/modules/{module_id}/purge-data
GET    /api/v1/modules/official-catalog
POST   /api/v1/modules/official-catalog/refresh
POST   /api/v1/modules/official-catalog/connectivity
POST   /api/v1/modules/{module_id}/install-official
POST   /api/v1/modules/{module_id}/update-official
POST   /api/v1/modules/{module_id}/rollback-official
```

这些写接口只允许 loopback 客户端；浏览器还必须来自受信 8000 控制台 Origin。
安装、更新、重启、卸载和清除数据必须提供明确的操作结果；不得因为查看模块目录
或官方目录而自动下载、联网、启动服务或调用付费 API。

安装和升级请求体使用：

```json
{
  "package_path": "C:/local/packages/focus-1.0.0.zip",
  "expected_sha256": "64-character-lowercase-or-uppercase-hex-digest"
}
```

浏览器 ZIP 的正式入口是 `POST /api/v1/modules/install-upload`：请求体是原始 ZIP
字节，`Content-Type: application/zip`，并携带浏览器计算的
`X-Project-Kei-Package-SHA256`。默认以通过完整包校验后的 `manifest.id` 为安装身份；
可选查询参数 `expected_module_id` 只作显式核对，缺省、空字符串或仅空白时均不参与
身份判断，非空时必须符合模块 ID 格式且与 manifest 完全一致。兼容入口
`POST /api/v1/modules/{module_id}/install-upload` 保留，并把路径参数视为非空的显式
核对值。成功响应中的 `module_id` 与 `installed_version` 是实际安装的 manifest 身份。
服务器不使用客户端文件名或路径，不返回临时路径；摘要不符、空包、超限、无效
预期 ID、manifest ID 不匹配或包校验失败均不得留下 registry/runtime/data 半状态。
文件选择和摘要计算本身不发出 HTTP 请求，只有用户点击上传安装才发送 ZIP。

`purge-data` 请求体使用 `{"confirmation": "<module_id>"}`。确认值必须与路由中的模块 ID 完全一致；卸载接口本身从不清除 `server/data/modules/` 下的数据。

官方 install/update/rollback 请求体使用：

```json
{"version": "1.0.0", "confirmation": "example@1.0.0"}
```

owner、repository、catalog URL 和 package URL 均由项目固定，客户端不能提交。
客户端只能选择固定枚举 `auto|github|gitee`；普通 GET 只读本机缓存/内置空基线，
refresh 才访问对应的固定 catalog URL。`auto` 先访问 GitHub，只在连接、超时、限流
或明确可重试服务端故障时切换 Gitee；摘要、大小、manifest、URL/重定向及其他安全
失败不得触发镜像回退。install/update 下载固定 GitHub Release asset 或同字节 Gitee
`packages/<release_tag>/<asset_name>`，限制重定向、时间、字节数并流式核对
SHA-256，随后复用本地包的 manifest、依赖、Core 保留和原子安装规则。官方
rollback 不下载，只允许目录仍信任且本地安装内容摘要未变化的前一版本。

`connectivity` 是显式本机动作且只接受无 query、空 body；它按固定顺序分别下载并完整
验证 GitHub/Gitee Catalog，单源最多 8 秒，只返回 `available|unavailable`、有界毫秒数、
模块数或稳定脱敏错误码。它不复用 `auto` 回退、不保存目录缓存、不安装模块，也不接受
任意 URL、凭据、代理或远程命令。普通页面加载和切换来源仍然零网络。

已启用模块的控制台入口通过 `GET /api/v1/modules` 返回可直接请求的 `dashboard_entrypoint`。静态资源读取限制在该包的 `dashboard/` 子目录，不能借此读取 backend、manifest 或配置 Schema。

## 控制台装载契约

- 公共外壳负责模块列表、安装进度、统一通知、配置对话框和请求封装。
- 只有 `enabled` 模块的 `dashboard_entrypoint` 可以加载；单个模块脚本失败不能阻止其他面板工作。
- 第一版入口使用 ES module，必须导出 `mount(context)`，可以导出 `unmount()`；入口 URL 必须位于同源 `/api/v1/modules/<module_id>/assets/` 边界，加载超时为可隔离失败。
- `context` 只提供模块自己的 DOM 根节点、只读目录快照、按该模块 `api_namespaces`/`legacy_endpoints` 限制的同源请求函数和统一通知函数，不提供注册表、文件系统或其他模块 DOM。
- 模块面板只能调用自己的公开 API，不能读取其他模块的数据文件或把服务端配置复制到浏览器存储。
- 迁移期间保留现有元素 ID 和旧接口行为；同一业务不能长期维护两套独立前端逻辑。
- 安装前应从官方目录展示模块名、版本、来源、下载大小、ZIP/manifest 摘要、
  外部依赖、权限、是否需要重启和卸载数据策略，并要求精确 `module_id@version`
  再确认。

PK-100 功能中心以只读发现和加载状态为基础，同时提供显式刷新官方目录、安装、启用、停用、更新、回滚和卸载操作。页面加载、展开、主题切换和读取缓存不得产生生命周期写副作用；每个写操作都必须由用户明确点击。清除数据仍与卸载分离，并要求精确 `module_id` 二次确认。

### Focus 试点实现

focus 的可审阅包源位于 `server/features/focus/package_source/`，正式 manifest 声明 `id=focus`、`in_process`、`backend.register`、`/api/v1/focus`、四个 `/focus/*` 兼容入口、`dashboard/index.js`、`data_namespace=focus`、`local_state` 和 `requires_restart=true`。`package_builder.py` 在临时目录或调用者指定的新路径中，把同一份 `models/router/service/repository/module` 源码复制到包内 `backend/`；包内不包含 BAT、PowerShell、shell、`.env`、状态文件或安装命令。

安装进入 `installed_disabled`。启用、升级、停用和卸载后都按 `in_process` 语义要求重启 API：启用后的新进程装配新旧路由和动态面板；停用/卸载后的新进程不装配，旧进程中已经存在的路由保持到重启为止。模块静态资产只在已启用状态可读。

第一阶段不迁移既有计时文件。卸载删除 runtime 程序版本但保留 `server/systems/data/focus_timer.json`、`server/data/focus_timer.json` 及其他同名历史状态，重装后继续关联配置的历史路径。`POST /api/v1/modules/focus/purge-data` 仍只处理新的 `server/data/modules/focus/` namespace，并要求精确确认 `focus`；它不绕过 PK-180 的历史数据保护。清空当前计时历史属于 focus 自身显式 reset 操作，不与卸载合并。

## 安全与集中发布

- 官方来源固定为 GitHub `songshu-yu/Project-Kei-Modules` 与 Gitee
  `songshuyu957/Project-Kei-Modules` 镜像。GitHub 使用集中批次 Release asset，
  Gitee 使用固定 raw 路径；两者必须是逐字节相同的 ZIP，匿名访问且
  不读取 Token。Catalog 固定精确字节数、ZIP/manifest SHA-256，普通用户不能输入
  URL。同一批次的模块共享 Release tag，但每个附件名和摘要仍独立冻结。
- 解压必须阻止绝对路径、`..` 路径穿越、符号链接逃逸和覆盖 Core 文件。
- 模块包不得包含 `.env`、Token、Cookie、个人缓存、模型输出或其他机器上的运行状态。
- 安装管理器不得为完成一次测试而发送 QQ 消息、触发真实采集、调用付费 LLM 或生成 TTS。
- 模块版本发布继续遵守 `AGENTS.md` 的 README、验证、显式暂存和 Git 安全门禁。

## 当前模块的计划分类

| 能力 | 计划形态 | 首次安装 |
|---|---|---|
| Core、catalog、控制台外壳 | 必需基础 | 是 |
| Kei 人格、文字对话、LLM 方案 | 可选 `conversation` in-process 模块 | 否 |
| 好感度与长期记忆 | 可选 `affection_memory` in-process 模块 | 否 |
| 专注、健身、日历、斩妖 | 可选 `in_process` 模块 | 否 |
| 每日情报、X/Nitter、B 站 | 可选 `in_process` 模块及依赖关系 | 否 |
| QQ bridge | 可选 `sidecar` | 否 |
| faster-whisper ASR | 可选 `sidecar` | 否 |
| GPT-SoVITS | 可选 `sidecar` | 否 |
| 树莓派客户端与硬件控制 | 独立分发目标，后续单独定契约 | 否 |

## 试点与全量迁移结果

1. `PK-010` 实现 manifest Schema、注册表、状态查询、固定官方 GitHub/Gitee 双镜像
   目录与本地高级导入的共同生命周期骨架。
2. `PK-100` 拆出控制台公共外壳和动态面板入口。
3. `PK-180` 将专注计时作为第一个端到端可安装模块，保留现有 `/focus/*` 接口兼容。
4. `PK-011` 在同一契约上完成 19 个业务项的确定性包候选：本地业务、情报来源/
   聚合、语音/Voice Pack 工具与 QQ sidecar；三项 Core 永不打包。
5. 官方目录由 19 个 release fragment 和实际 ZIP 重建；每个 ZIP 连续构建必须
   字节一致，并通过安装、停用/启用、卸载保留数据和重装回归。sidecar 的外部依赖
   与大型模型不进入包，缺失时返回可修复状态且不阻塞 Core。
6. 这些候选只有在 PK-900 对同一 Git 提交与全部 Release 资产验收通过后才正式
   发布；任务文档中的“待集成”不能对外表述为已发布可下载。

## 验收基线

- 没有任何可选模块时，Core 能启动、显示模块中心和健康状态；文字对话只有安装并
  启用 `conversation` 后出现。
- 安装并启用模块后，其 API 和控制台面板同时可发现；停用后定时任务和后台循环停止。
- 缺少依赖、配置或端口时给出可操作错误，不产生半安装状态。
- 升级失败可以继续运行旧版本；卸载默认保留用户数据，重装后可以重新关联。
- 模块不能修改其他模块的私有状态，不能覆盖 Core 文件，也不能把密钥带到前端或日志。
- 现有兼容接口和数据在对应迁移任务验收前保持可用。

## 暂缓决策

第一版远端能力只支持项目固定官方 GitHub 仓库中的 Catalog v1 和不可变 Release
asset，不是开放模块商店。第三方仓库、用户 URL、发布者签名体系、自动更新、
付费模块和第三方开放 SDK 仍由 PK-000 后续单独决策。

## 聚合面板与 sidecar 配置面板

- 聚合模块的父容器收起时遵循普通三列模块卡尺寸，展开后才跨越整行；响应式下依次
  降为两列和一列。父容器不得用 `display: contents` 绕过折叠、ARIA 或错误隔离。
- 一个安装单元可以在受信 dashboard entrypoint 内声明
  `.module-owned-panels`，提供多个独立的本地功能卡。每张卡必须有稳定
  `data-panel-id`，并继续由公共外壳负责头像、设置、折叠和键盘语义。
- `qq_bridge` 仍是一个 sidecar 安装单元和一套凭证/进程；其启动、每日推送和生命
  维持是三个独立视觉卡，不复制为三个安装包。等待配置时只装配固定同源 control
  facade 与受信静态面板，不启用或启动进程，也不开放任意命令、路径或环境变量。
- QQ 包内 manifest、`package.json`、`package-lock.json` 根版本必须一致。依赖仅由
  PK-020 的显式 staging/`npm ci --ignore-scripts`/原子 marker 流程部署到包外目录。
## 动态模块的视觉卡与 sidecar 子功能

安装生命周期以 manifest 的 `module_id` 为单位；一个 sidecar 不应为了多个界面功能复制进程、凭证或依赖目录。控制台可以在同一动态入口根节点下返回 `.module-owned-panels`，其中每个直接子 `section` 都是独立可折叠的小卡片。收起时参与统一三列网格，展开时占满当前模块区域。

QQ 因此仍只有一个 `qq_bridge` 安装单元和一个 Node 进程，但展示为 QQ 启动、每日情报推送、生命维持三个独立卡片。配置状态只能由受控 adapter/facade 返回非秘密布尔值；动态面板不得读取或回显 `.env`，也不得在页面加载时安装依赖、启动 sidecar 或发送消息。
