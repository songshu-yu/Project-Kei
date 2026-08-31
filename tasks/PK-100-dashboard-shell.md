# PK-100 — 控制台公共外壳

- 状态：待集成
- 优先级：P1
- 所属模块：`dashboard`
- 依赖任务：PK-001、PK-010、PK-020、PK-211
- 负责路径：`server/static/dashboard.html`、未来 `server/static/dashboard/`、未来 `server/tests/test_dashboard_shell.py`
- 当前对话：2026-07-28 由 PK-000 授权继续使用 PK-100；目的为在不改变 PK-130/PK-140 业务、凭据、进程或 API 契约的前提下，将 B 站参数区的视觉结构抽象为公共模块卡片头，并增加纯本地三档主题、QQ 单向启动卡迁移及无障碍/移动端回归；用户后续确认所有主功能采用小图加标题的响应式组件网格，点击标题后跨整行展开为大图、完整说明和原有功能，并要求右侧动作形成紧凑工具栏。2026-07-29 进一步确认 PK-100 是全部控制台组件的统一 UI 注册层，自定义图片应写入 PK-100 自有服务端 UI 素材目录并跨刷新保留，而不是仅作本页预览或落入业务模块。2026-07-30 由 PK-000 冻结新增“官方模块中心”控制面：将模块管理明确分为 PK-010 官方 GitHub Catalog 缓存的“可安装模块”、registry 的“已安装模块”和只读“内置功能”；普通加载零 GitHub 网络，现已消费 PK-010 冻结的缓存、显式刷新、精确确认安装/更新/回滚及既有生命周期接口，并实现网页布局、状态、确认、并发保护、失败隔离与安全提示。本轮继续消费 PK-010 最终冻结矩阵，补齐官方目录来源/刷新联网状态、依赖信息和完整结构化错误元数据。2026-07-30 用户确认当前控制台自定义图片已基本敲定，授权将其提升为版本化项目默认素材并登记到组件视觉注册信息；本增量只复制经确认的 UI 图片、建立 panel/status 注册映射和回归，不改变业务模块、接口或本机覆盖语义。2026-07-30 PK-000 开放最终共享 Dashboard 串行窗口：19 个业务包均已形成 manifest/动态入口或明确无独立面板，本轮删除全部静态 legacy 业务 DOM/内联业务 JS，只保留固定 Core 三模块、健康摘要、主题/本地视觉、生产模块管理与动态挂载，并补齐 loader 的卸载、幂等刷新和失败隔离生命周期。2026-08-02 本轮由 PK-000 接回共享视觉缺陷：审计并最小修复“每日情报来源与采集”聚合卡，使其保持标准收起小卡，并在展开态复用公共大图左栏、来源子导航及完整功能右栏布局；不得改变 PK-110/115/120 业务、接口或网络语义。
- 最终关闭：2026-08-02 PK-900 对 PK-100 + PK-120 累计候选完成独立源码、逆向、浏览器和回归验收；桌面双栏、移动端单列、收起小卡、六来源标签及零业务网络契约均通过。PK-000 复核后将本任务置为“已完成”。
- 2026-08-02 用户重新打开 PK-010 + PK-100 离线安装增量：高级区补充浏览器本地
  ZIP 选择、SHA-256 和显式安装控件；只消费 PK-010 新增的本机原始 ZIP 上传接口，
  不接受服务器路径、任意 URL、Token/Cookie，也不改变官方目录或业务模块界面。
- 2026-08-08 PK-000 重新打开本地 ZIP 连续换包与受控重启增量：换包时必须区分
  manifest 自动识别 ID 与用户手工 ID，并在保留、自动识别、取消换包之间明确确认；
  文件选择全程零网络。串行窗口中 PK-020 已冻结 supervisor/restart API，PK-211
  已冻结无路径的 GPT-SoVITS 本机目录选择 API；本轮仅消费两份正式契约，不直接
  控制进程、注入目录或扩张后端。
- 2026-08-19 PK-000 授权继续官方模块中心增量：修复单项官方安装成功后停留繁忙态、
  未重读本机官方目录缓存的问题，并增加默认关闭、显式确认、依赖预检和严格串行的
  前端批量安装模式；不新增后端接口，不改变 PK-010 单包校验与生命周期语义。

## 目标

把单文件控制台收口为稳定的 Core 公共外壳和可独立失败的动态模块面板：公共外壳只负责页面骨架、Core 健康摘要、模块管理、主题/本地视觉、统一通知、同源请求封装和模块入口生命周期；具体业务 DOM、事件与请求由各自安装包的 `dashboard_entrypoint` 维护。控制台只加载 PK-010 registry 中已启用且声明了受信同源入口的模块。

## 不在本任务内

- 不实现或改写 PK-010 的 manifest 校验、模块注册表、依赖解析及安装、启停、升级、回滚、卸载后端语义。
- 不迁移每日情报、X/Nitter、B 站、QQ、斩妖、好感度、健身、专注、日历、对话或语音等具体业务规则、数据模型和服务端接口。
- 不把任何业务面板、元素 ID、事件监听或 API 调用重新复制回 Core HTML；业务兼容接口继续由对应模块维护。
- 不修改、删除或重新定义 `/dashboard/*` 之外的业务接口；静态 legacy 面板移除只改变展示所有权，不改变后端契约。
- 不引入远程模块商店、第三方脚本源、新常驻进程、新端口或面向公网的管理入口。
- 不在浏览器存储、DOM、日志或错误提示中保存或展示密钥、Cookie、Token、个人名单、业务缓存或模块私有状态。
- 不对控制台做与模块化无关的视觉重设计或大范围格式化。

## 负责路径与协作边界

- `server/static/dashboard.html`：继续作为 `GET /dashboard` 的兼容 HTML 入口，仅保留公共骨架和迁移期接缝。
- `server/static/dashboard/`：承载公共样式、请求/通知工具、功能中心、模块加载器和公共外壳资源。
- `server/tests/test_dashboard_shell.py`：验证目录过滤、入口加载策略、失败隔离及安全边界；若采用浏览器测试，测试资源仍归本任务记录。
- `server/api.py`、`server/features/catalog/` 和 `server/core/modules/` 是共享或其他任务负责路径。若实现需要改变静态资源挂载、目录响应字段或生命周期语义，先在本文件记录所需契约并交 PK-000/PK-010 确认，不由 PK-100 直接扩张修改范围。
- 各业务模块的面板内容、事件处理和接口适配归对应 `PK-xxx` 任务；PK-100 只定义并维护它们接入公共外壳的契约。

## 接口契约

- 当前兼容入口：`GET /dashboard` 继续返回可直接打开的控制台；`GET /dashboard/status` 的现有语义和响应字段不由本任务改变。
- 公共资源：新增只读 `GET /dashboard/static/{asset_path}`，只允许读取 `server/static/dashboard/` 内的文件；现有 `/dashboard/assets/qq-launch.png` 不变。路径穿越和不存在文件统一返回 404。
- 控制台 UI 素材：`GET /api/v1/dashboard/ui-assets` 列出已自定义组件头像；
  `GET/PUT/DELETE /api/v1/dashboard/ui-assets/{panel_id}/avatar` 分别读取、上传和
  恢复默认。写入只接受本机客户端与受信控制台 Origin、有限 panel ID、最大 8MB
  且文件签名匹配的 PNG/JPG/WebP；响应不返回绝对路径。
- 组件注册：每个顶层 legacy/动态组件以稳定且唯一的 `panel_id` 作为 PK-100 UI
  注册键，并声明标题、单行说明、仓库默认图片和可选设置入口。新增或迁移组件时只
  更新这份展示元数据和模块目录；所有组件复用上述通用 UI 素材接口，不新增各业务
  模块的头像接口，也不把业务规则复制进 PK-100。
- 状态视觉：保留 `service-status-normal` 与 `service-status-attention` 两个 UI
  注册键，分别供所有“正常”和“需要处理”服务卡共享。它们只消费
  `/dashboard/status` 的既有结果，复用 UI 素材 API，不改变健康判断或服务接口。
- 模块目录：只读调用 `GET /api/v1/modules`，至少消费 `key`、`label`、`required`、`install_status`、`enabled`、`dependencies`、`configuration_ready`、`requires_restart`、`restart_required`、`dashboard_entrypoint`、`permissions`、`data_policy` 和 `last_operation`。PK-010 新增字段必须保持目录向后兼容。
- 装载条件：仅当目录项 `enabled === true` 且 `dashboard_entrypoint` 非空时加载该模块脚本；`required` 模块仍须满足已启用条件，且功能中心不得提供停用或卸载操作。
- 前端入口：`dashboard_entrypoint` 必须是目录返回的同源、受信任模块资源。第一版入口采用 ES module，必须导出 `mount(context)`，可以导出 `unmount()`；`context` 仅提供该模块的 DOM 根节点、目录快照、统一 `request` 和 `notify` 能力。
- 实际入口限制：动态 URL 必须位于同源 `/api/v1/modules/<module_id>/assets/`；加载超过 10 秒、404、模块未导出 `mount()` 或 `mount()` 抛错时，只更新该模块的功能中心状态和挂载容器。
- 请求边界：模块面板只通过公共 `request` 调用自己的 `api_namespaces` 或 `legacy_endpoints`；公共封装只接受同源 HTTP(S) 路径，统一处理非 2xx、JSON/文本错误和超时，不读取本地文件或绕过后端权限检查。PK-010 官方操作错误保留有限的 `code`、`message`、`stage`、`retryable`、`received_bytes` 与 `retry_after`，仅用于可理解的本地提示，不展示完整异常或上游正文。
- 失败隔离：目录请求失败、单个入口缺失、模块加载异常或 `mount()` 抛错都必须转为该模块可见的错误状态；已经加载的其他模块和公共外壳继续工作。
- 生命周期操作：功能中心可以在用户明确操作后调用 PK-010 提供的 `/api/v1/modules/{module_id}/...` 接口，但不直接读写模块注册表。安装、更新、启停和卸载遵守 PK-010 返回的状态；`purge-data` 必须独立展示准确影响并二次确认，不得与卸载合并。
- 官方目录：`GET /api/v1/modules/official-catalog` 只读取 PK-010 的本机最后有效
  缓存/内置空基线，不访问 GitHub；只有用户点击“刷新官方模块目录”才调用
  `POST /api/v1/modules/official-catalog/refresh`。目录卡只展示真实存在、
  `compatible !== false` 且 `available_actions` 包含 `install_official` 的版本。
- 官方安装：用户先查看固定仓库、版本、Core 兼容范围、字节大小、ZIP SHA-256、
  权限和数据策略，再在独立确认面板中确认。请求为
  `POST /api/v1/modules/{module_id}/install-official`，JSON 仅含
  `version` 与精确 `confirmation="<module_id>@<version>"`；更新/回滚使用同样
  确认语义的 `update-official`/`rollback-official`。浏览器不提交 URL、owner、
  repo、服务器路径、Token/Cookie，不直接下载或解包，也不在安装后静默启用。
- 三类展示：官方 Catalog 中未安装且允许 `install_official` 的可信版本进入
  “可安装模块”；PK-010 registry 中 `managed=true` 且有 `installed_version`
  的条目进入“已安装模块”；只有 `catalog`、`module_manager`、`dashboard`
  进入只读“Core 固定模块”。19 个业务包均属于可安装模块，不再把 calendar、
  fitness、demon、conversation、intel 等标为 Core 内置功能，也不再硬编码
  “首批只有 focus”。`required=true` 或 Core 三项永远不出现安装、停用、卸载、
  更新、回滚或 purge 动作；空 Catalog/尚未发布资产显示说明而不生成假按钮。
- 已安装操作：按钮完全依据 PK-010 `available_actions`，同模块操作使用 busy
  锁阻止重复点击。停用/卸载有独立确认，卸载明确默认保留数据；purge 放在分离
  危险区并要求输入精确 module ID。`restart_required=true` 只显示“需要重启
  Core 才生效”及安全步骤，不自动杀进程、重启 Core 或安装依赖。
- 业务接口：迁移期各模块继续调用自己的公开 HTTP 接口；PK-100 不改变其请求/响应语义，也不直接读取后端数据文件。

## 数据所有权

- 服务端数据：本模块不拥有业务数据、模块注册表、manifest、凭证或业务缓存；仅拥有
  Git 忽略的 `server/data/dashboard_ui/avatars/` 控制台外观素材目录。默认素材仍
  位于版本化静态资源中，用户上传素材按 panel ID 原子替换。
- 浏览器状态：只允许保存纯 UI 偏好；必须兼容现有 `project-kei.dashboard.panel-open.v1` 折叠状态键。新增键统一使用 `project-kei.dashboard.*` 命名，并在本任务工作记录中列明用途和迁移策略。
- 读写副作用：普通页面打开只额外读取一次 UI 素材目录，不写盘；只有用户明确选择
  图片或点击“恢复默认”才写入/删除 dashboard 自有素材。上述操作不得触发安装、
  外网采集、服务启动、付费调用或业务数据写入。
- DOM 所有权：公共外壳拥有页面骨架、通知区、功能中心和模块根容器；每个模块只维护分配给自己的根容器，不依赖或改写其他模块的 DOM 和运行状态。
- 禁止直接访问：除 dashboard 自有 `server/data/dashboard_ui/avatars/` 外的
  `server/data/`、`server/.env`、`server/qq_bridge/.env`、`server/runtime/`、
  其他模块私有文件，以及任何 Cookie、Token、API Key、个人名单和业务缓存。

## 依赖任务与后续协作

- PK-001（已完成）：提供模块目录、任务映射和 `GET /api/v1/modules` 基础兼容响应。
- PK-010（本批待集成）：提供生命周期字段、固定官方 Catalog/Release 接口、
  可信 `dashboard_entrypoint`、Core 保留边界和本机写接口；PK-100 不自行改变
  其后端状态语义。
- PK-180（本批进行中）：交付首个正式 focus Release asset/Catalog 片段，并保留
  `/focus/*` 兼容接口；正式发布前 PK-100 只显示 PK-010 的合法空基线。
- 其他功能任务（下游）：逐项迁移自己的业务面板；不得把领域逻辑重新放回公共外壳。
- PK-900（待累计验收）：本轮按 `PK-010 + PK-100 + PK-180（官方 focus 包）`
  重新执行累计验收；PK-100 不自行标记完成。

## 2026-07-28 共享视觉增量契约

- 公共卡头类位于 `server/static/dashboard/shell.css`，允许组合
  `module-shell-header`、`module-shell-identity`、`module-avatar`、
  `module-shell-heading`、`status-pill`、`module-shell-actions` 和现有折叠入口；
  头像、状态、动作均可选，不要求业务模块复制规则或更改接口。
- 用户后续进一步明确主功能应采用“小组件网格”，而不是纵向摘要列表。
  `panels.js` 会为仍使用直属 `<h2>` 的 legacy 主面板渐进生成图片槽和标题按钮；
  收起时桌面三列、平板两列、窄屏单列，只显示小图与标题。展开时组件占满整行，
  卡头使用最大 280×350（4:5）竖图和右侧完整详情两列布局；图片使用
  `object-fit:contain` 居中完整展示，不使用放大 transform。标题、操作坞、设置和
  原业务内容全部进入右侧详情列，不再把业务内容放在图片下方制造空白。窄屏改为
  单列并将图片限制为最大 260×325、水平居中。
- PK-100 是全部控制台组件的统一展示注册层：稳定 `panel_id` 关联标题、说明、
  默认图片、设置入口和用户自定义图片。业务组件升级时同步自己的展示元数据/模块
  目录即可；自定义图片仍由一个通用 PK-100 API 按 `panel_id` 管理，不为 QQ、
  每日情报或其他模块扩张业务接口。
- 无自定义素材时显示“添加图片”入口。用户可选择 8MB 内 PNG/JPG/WebP，前端先以
  `URL.createObjectURL` 预览，再通过 dashboard 自有同源 API 上传到 Git 忽略的
  UI 素材目录；刷新、换浏览器或重启 API 后仍恢复。上传失败只保留本页预览并明确
  提示，不能伪装成保存成功。“恢复默认”删除上传素材；仓库默认图仍可通过
  `data-panel-avatar`/`data-panel-avatar-alt` 声明。
  新会话默认全部收起，已有 `project-kei.dashboard.panel-open.v1` 布尔记录继续恢复。
- 标题按钮只负责展开/收起；QQ 头像仍是独立的唯一 start 按钮，渲染标题明确注明
  “单击头像可以启动 QQ”，点击标题绝不启动 QQ。
- 公共折叠发现范围同时覆盖 main 直属 legacy 面板和
  `#dashboard-module-mounts > section.section` 动态模块；loader 在模块挂载完成后
  继续调用同一 `setupDashboardPanels()`。静态与动态模块都显示明确的
  “展开详情/收起详情”状态；QQ 与通用主组件收起小图统一为 16px 圆角矩形。
- `panels.js` 兼容原直属 `<h2>`，也能在结构化卡头的
  `.module-shell-heading > h2` 上建立原生 `<button>` 折叠控件。原 panel ID、
  `aria-expanded`、默认展开集合和 `project-kei.dashboard.panel-open.v1` 不变。
- QQ 卡使用已有 `qq-launch.png`，桌面头像 64px、窄屏 56px；头像仍是
  `#start-qq-bridge` 的唯一启动按钮，状态胶囊只映射已有
  `running/ready/starting/failed` 展示。仍只调用一次
  `POST /api/v1/qq-control/start`，不存在 stop、toggle 或新进程契约。
- B 站参数区保留 PK-130 的 `#bilibili-credential-panel`、42px 本地思考头像、
  状态 ID、密码字段、独立 `<details>`、候选保存和显式验证采集函数，只附加公共
  卡头类；窄屏头像沿用 36px，不移动凭据或 Collector 所有权。
- 功能中心的只读模块卡头复用同一标题/状态胶囊类；动态模块
  `mount(context)`、入口过滤、同源请求和失败隔离协议不变。
- 每个顶层 legacy/动态组件由 `panels.js` 自动附加独立“设置”按钮与
  `aria-controls`/`aria-expanded`。设置面板自动发现 `label.field`、
  `label.switch-row`、`data-setting-label`；动态模块也可在自己的 root 声明
  `data-panel-settings="说明一|说明二"`。入口只展开卡片、列出最多 8 项并把焦点
  定位到原控件，不复制字段、不读取/展示输入值、不自动保存业务字段。每个设置面板
  固定提供“设置本机图片/恢复默认”，只调用 PK-100 自有 UI asset API；前者明确
  保存当前安装实例的自定义覆盖而不修改项目默认素材，后者删除覆盖并回到仓库
  默认图/空槽；QQ 只替换当前
  `<img>`，外层 `#start-qq-bridge` 按钮及单击启动行为不变。无设置模块显示占位；
  QQ 只列出现有头像启动/状态刷新并明确无 stop。
- 展开卡右栏按“标题/单行说明 → 状态/刷新/设置操作坞”排列。操作坞左对齐、允许
  换行并使用独立弱边界，避免按钮由图片跨行拉伸后悬在媒体中部；720px 以下宽度
  占满单列且不产生水平滚动。该分区只改变公共 CSS 布局，不重排 DOM、不改变动作
  顺序或事件监听。
- 三主题由 `theme.js` 独占，允许值为 `cloud/sakura/moon`，默认 `cloud`。
  `project-kei.dashboard.theme.v1` 只保存这个 UI 枚举；读取、写入或存储异常均不
  调用 `fetch`/公共请求封装，异常时回退云朵白且当前页面仍可切换。
- CSS 以语义变量驱动云朵白、樱花粉、月夜蓝，保留高对比文本、全局
  `:focus-visible`、ARIA live 状态、`prefers-reduced-motion` 和 720px 以下
  响应式。无 JavaScript 时 HTML 标题、说明、表单和内容仍直接存在，只有动态状态
  与交互不可用。

## 实施清单

- [x] 盘点 `dashboard.html` 的现有元素 ID、面板默认状态、公共工具、业务脚本和接口调用，形成兼容基线。
- [x] 固化公共外壳目录结构、模块根容器和 `mount(context)`/`unmount()` 前端入口协议。
- [x] 抽离公共样式、通知与同源请求封装，保留 `GET /dashboard` 和现有静态资源兼容。
- [x] 建立功能中心，按目录状态展示依赖、配置、权限、重启要求、最近操作和数据保留策略，绝不展示敏感值。
- [x] 将功能中心增量为三分区模块管理：官方可安装、registry 已安装与只读内置
  功能；接入 PK-010 固定官方缓存/刷新/安装契约和既有生命周期接口。
- [x] 永久保护 Core 固定三项和 `required=true` 条目；19 个业务包按 Catalog/
  registry 真实状态展示，没有官方版本时不生成虚假下载动作。
- [x] 建立动态模块加载和错误隔离，只加载已启用且声明入口的模块。
- [x] 从 `dashboard.html` 清除好感度、斩妖、健身、日历、对话/LLM、每日情报、
  情报来源、X/B 站、语音/语音包、QQ 等静态业务 DOM、内联业务 JS 与启动监听。
- [x] 盘点 19 个 package manifest；18 个入口由 loader 动态挂载，YouTube 明确
  显示“后台 Collector / 服务模块，无独立面板”。
- [x] README/TASKS/Catalog/架构说明按 PK-000 共享冻结不改；最终用户文案、
  接口、数据副作用、验证结果和共享文档遗留均记录在本任务文件。
- [x] 运行 12 个 Dashboard JavaScript 语法检查、Core-only shell 回归、fake
  Browser 桌面/移动端交互、文档门禁和 `git diff --check`。

## 验收标准

- `GET /dashboard` 在没有任何可选模块时仍能打开公共外壳、显示功能中心，并保留首次安装集合所需入口；页面打开不产生业务或生命周期写副作用。
- Core HTML 不含业务元素 ID 或业务 API；业务模块挂载后仍使用公共卡片、原生按钮、
  `aria-expanded` 和纯 UI 折叠偏好独立展开/收起。
- 使用包含必需、已启用、已停用、待配置、损坏和无前端入口模块的目录夹具时，只有 `enabled === true` 且具有 `dashboard_entrypoint` 的脚本被请求和执行。
- 任一模块入口返回 404、加载超时或在 `mount()` 中抛错时，错误只显示在该模块容器/功能中心，其他模块和公共导航仍可操作。
- 功能中心准确展示模块状态、必需/可选属性、依赖、配置是否就绪、权限、重启要求、最近操作和卸载数据策略；不渲染密钥值、个人配置内容或完整后端异常响应。
- 必需模块没有停用或卸载入口；清除数据与卸载是两个操作，清除数据必须经过独立二次确认且仅调用 PK-010 的公开接口。
- 新模块入口只获得约定的 `context`，通过公共同源请求封装调用声明的 API；控制台代码中不存在对后端状态文件、注册表或其他模块私有数据的直接访问。
- JavaScript/ES module 语法检查、加载器定向测试、浏览器交互回归和 `git diff --check` 全部通过；实际命令与结果写入工作记录。

## 工作记录

- 2026-07-30：PK-000 紧急更正模块中心产品入口为 Project Kei 固定官方 GitHub
  Catalog/Release，而非本机 ZIP。PK-100 新增 `module-management.js`，将原只读
  功能中心升级为“可安装模块 / 已安装模块 / 内置功能”三层控制面；本地 ZIP
  仅保留在高级区的说明，不提供服务器路径、任意 URL 或未冻结的上传控件。
- 2026-07-30：消费 PK-010 冻结接口：
  `GET /api/v1/modules/official-catalog`、显式
  `POST /official-catalog/refresh`、精确 `module_id@version` 确认的
  `install-official`/`update-official`/`rollback-official`，以及既有
  enable/disable/config-check/rollback/uninstall/purge-data。页面普通加载只做
  两次本机 GET，不访问 GitHub；官方刷新和确认后的下载才可能由 PK-010 联网。
- 2026-07-30：控制台严格以 `managed + installed_version` 区分 registry 已安装
  模块，以 `required/installable/managed` 区分 Core 内置功能。所有内置卡均只读，
  即使恶意夹具声明 install/disable/uninstall/purge 动作也会被前端过滤；首批
  Catalog 只有正式发布后的 focus，空基线明确提示“尚未发布”，不伪造成功。
- 2026-07-30：官方卡展示固定仓库、Release/资产名、Core 兼容、大小、SHA-256、
  必需/可选依赖、冲突、权限、数据策略和重启语义；目录状态同时展示固定
  owner/repository、生成时间、缓存来源、刷新状态以及本次读取是否联网。
  安装前弹出可键盘聚焦的二次确认。已安装卡展示版本、依赖、配置、重启、入口和
  最近操作；同模块 busy 锁防重复，卸载保留数据与 purge 精确确认分离。结构化
  PK-010 错误不再被公共请求封装压成 `[object Object]`，保留
  code/message/stage/retryable/received_bytes/retry_after 供用户理解断网、
  超时、摘要或兼容失败。
- 2026-07-30：Browser 使用 `test_dashboard_shell.py --preview` 的 fake Catalog/
  registry 验收；只点击公共折叠、主题、官方安装确认/取消和 fake 目录刷新，未
  确认安装、启停、卸载或 purge。1265px 与 375px 均满足
  `scrollWidth === clientWidth`，移动端四张模块卡单列；内置 dashboard/calendar
  的生命周期动作计数为 0，故意缺失入口仅标记自身失败，console error 为 0。
  樱花粉切换后 reload 正确恢复，验收结束恢复云朵白和收起状态。
- 2026-07-30：最终 11 个 dashboard JavaScript 文件 `node --check` 通过；
  Dashboard shell、官方 Catalog、Feature Catalog、可安装模块生命周期、focus、
  8 项 QQ control、B 站 collector/feature/credentials 全部通过。Browser 标签、
  viewport 和 8765 fake 预览进程已关闭；未启动真实 Core、QQ/B 站、采集或模型。
  `scripts/check_task_docs.py` 通过 23 个门禁任务；`git diff --check` 退出 0，
  仅报告混合工作区既存 LF→CRLF 提示；PK-100 修改路径无行尾空白。
  PK-100 置“待集成”，交给 PK-000/PK-900 与 PK-010、PK-180 串行收口；未执行
  `git add`、commit、push、切分支、PR 或清理混合工作区。
- 2026-07-30 最终冻结矩阵补验：重新完整读取
  `official-catalog.schema.json` 与 `module-package-contract.md`，按 PK-010
  实际响应补齐目录来源/联网状态、依赖/冲突、重启语义和全部有限错误元数据。
  11 个 dashboard JavaScript 文件语法、Dashboard shell、官方 Catalog、
  Feature Catalog、可安装模块生命周期、focus、QQ 8 项与 B 站
  collector/feature/credentials 再次通过。尝试以 Browser skill 连接 8766 fake
  预览时，本轮 Browser URL 安全策略拒绝 localhost/127.0.0.1，未绕过；同一 fake
  harness 的上一轮桌面/375px 视觉验收仍有效，本轮新增内容由 DOM/Node 静态回归
  覆盖。fake 进程和 Browser 标签均已关闭，未连接真实 GitHub 或点击任何生命周期
  写操作。最终 `scripts/check_task_docs.py` 通过当前 22 个门禁任务，
  `git diff --check` 退出 0；输出仅含混合工作区既存 LF→CRLF 提示。
- 2026-07-30 README 操作说明草案（交 PK-000 串行收口）：控制台底部“模块管理”
  先展示本机官方目录缓存；如需查看新版本，用户显式点击“刷新官方模块目录”，
  选择官方版本并核对来源/大小/摘要/权限后确认“下载并安装”。安装完成不会自动
  启用，需在“已安装模块”显式启用；停用/卸载可能提示重启 Core，卸载默认保留
  数据。清数据位于独立危险区并要求输入 module ID。离线时已安装模块和内置功能
  继续可用；本地 ZIP 以后只作为高级入口，不接受服务器路径或任意 URL。

- 2026-07-28：PK-000 明确授权 PK-100 接管共享控制台视觉增量，不新建任务编号；PK-130 继续独占 B 站参数与凭据安全，PK-140 继续独占 QQ start、白名单和 sidecar 契约。本轮只计划修改公共 dashboard HTML/CSS/JS、PK-100 回归及必要文档；主题、折叠与卡片交互不得调用 API 或写业务状态，QQ 不新增 stop 或伪装启停开关。
- 2026-07-28：共享视觉增量实现、离线回归、Browser 只读验收和八项文档门禁均完成；PK-100 只恢复为“待集成”，交回 PK-000/PK-900 复核，不自行标记完成。没有暂存、提交、推送、切分支、创建 PR 或清理混合工作区。
- 2026-07-28：用户以 QQ 摘要条和每日情报展开页为视觉参考，要求所有主功能统一
  使用“头像槽 + 标题/摘要”的收起状态，点击标题后再显示完整说明和功能。PK-100
  在不改 HTML 元素 ID 或业务接口的前提下扩展 `panels.js`：自动包装 legacy
  `<h2>` 面板、保留空头像槽与可选本地素材属性、区分标题折叠和 QQ 头像启动，
  并把新会话默认状态调整为全部收起。旧版本已保存的布尔折叠记录仍按原键恢复。
- 2026-07-28：用户再次澄清目标是类似 Dashboard gallery 的小组件网格，展开后
  采用大图详情页结构，而不是横向列表。公共 CSS 调整为桌面三列/平板两列/移动端
  单列，小组件展开时跨越整行；无素材卡增加明确的本地图片临时预览入口。由于永久
  上传需要新增后端素材所有权和写接口，本任务未伪装持久保存，也未扩大 API 契约。
- 2026-07-28：用户指出 QQ 与动态专注模块缺少清晰的展开/收起表现。根因是公共
  脚本只扫描 main 直属 section，遗漏 `#dashboard-module-mounts` 子节点；同时旧
  状态文字对比度和边界不足。PK-100 扩展发现选择器并复用 loader 的既有
  `onPanelAdded` 回调，没有修改 focus 或 QQ API；状态提示改为带边框胶囊的
  “展开详情/收起详情”，收起态 QQ 为圆形、专注和通用图片槽为圆角方形。
- 2026-07-28：用户实际页面仍呈现旧版标题行。对照截图和当前 DOM 后确认不是
  focus/QQ 接口问题，而是 `/dashboard` 与公共 ES module 的缓存版本不一致：
  HTML、入口和内部 import 没有共享同一失效标记。PK-100 为 HTML、CSS、入口及
  公共依赖统一使用 `pk100-20260728-widget3`，并为 `GET /dashboard` 和
  `/dashboard/static/*` 增加 `Cache-Control: no-store, max-age=0` 与
  `Pragma: no-cache`。这不改变业务 URL、参数、响应、模块契约或浏览器数据；
  已运行的主 API 只需重启一次以加载新的 Python 响应头。
- 2026-07-29：用户要求统一界面中的每个小组件自带可视化设置入口，具体业务设置
  可逐步补充。PK-100 增加纯 UI 设置导航：所有主功能、动态 focus 与加载失败卡
  自动获得设置按钮；已有表单自动形成设置项，当前覆盖 LLM、生命维持、好感互动
  场景、斩妖参数、健身备注、日历/修炼、长期记忆、每日推送和 focus 启动参数。
  无独立字段的今日情报、配置状态和功能中心显示有限说明；QQ 不新增 stop。
  公共资源版本同步提升为 `pk100-20260728-widget4`，避免再次加载旧脚本。
- 2026-07-29：用户指出展开图片被横幅比例和放大 transform 裁切，且 QQ 圆形
  收起头像与其他主组件不一致。PK-100 将主组件展开媒体框统一为最大宽 680px 的
  16:9，图片改用 `object-fit:contain`、居中、`transform:none`；QQ 收起态同步为
  16px 圆角矩形。B 站参数次级头像仍由 PK-130 保持原独立圆形样式。公共资源版本
  提升为 `pk100-20260729-widget5`，未改变图片来源、上传边界或 QQ start 行为。
- 2026-07-29：用户进一步明确展开后只需要原图所在的竖版矩形，不需要横向留白
  画框。PK-100 将过渡版 680px/16:9 媒体框替换为更紧凑的公共角色卡布局：桌面
  320×400 竖图在左、标题/状态/设置在右；移动端 280×350 居中、文字在下。
  图片仍完整 contain，收起态仍为统一圆角矩形。资源版本提升为
  `pk100-20260729-widget6`。
- 2026-07-29：用户指出右栏状态/刷新/设置漂在图片中部，并要求每张卡的设置都能
  更换头像。PK-100 参考 Fluent 2 Card 的 preview/header/action 分区和 Carbon
  Tile 的底部左对齐嵌套动作原则，把右栏整理为标题说明下方的紧凑操作坞；不移动
  任何业务 DOM 或动作。所有设置面板新增统一头像入口，文件限 8MB PNG/JPG/WebP，
  只用对象 URL 更新当前卡片，刷新恢复；QQ 外层 start 按钮保持不变。资源版本
  提升为 `pk100-20260729-widget7`，没有新增接口、存储键或后端数据所有权。
- 2026-07-29：Browser skill 在 1280px 预览中测得 QQ 标题底部 413.55px、操作坞
  顶部 427.55px，固定间距 14px；操作坞为 1px 弱边界、可换行且位于图片顶部区域，
  320×400 图片仍完整显示。375px 视口下图片为 280×350，操作坞宽 304px，标题与
  操作坞仍间隔 14px，document 与卡片横向溢出均为 0。15 个顶层卡各有一个头像
  设置按钮与 `image/png,image/jpeg,image/webp` 隐藏输入；QQ 和动态 focus 设置
  面板均显示“不上传、不保存”，focus 原模式/分钟/任务定位项保留。未打开文件选择、
  未点击 QQ start、focus 启停、采集、保存、模型、删除、打卡或其他业务写操作，
  Browser warning/error 日志为空，临时 8765 预览已关闭。
- 2026-07-29：`server/tests/test_dashboard_shell.py`、Feature Catalog、focus
  module、8 项 QQ control、B 站 feature/collector/credentials 全部通过；7 个
  dashboard 公共 JavaScript 文件逐项 `node --check` 通过。专项回归锁定三行
  Grid、14px 操作坞间距、统一头像设置入口、MIME/8MB 限制、WeakMap 对象 URL
  回收、零 `fetch`/`apiJson`/FileReader 和 `widget7` 一致缓存标记。
- 2026-07-29：API/dashboard router/专项测试 `py_compile` 通过；
  `scripts/check_task_docs.py` 通过当前 24 项任务，八项文档门禁仍完整；
  `git diff --check` 退出 0，仅报告混合工作区既有 LF→CRLF 提示。PK-100 保持
  “待集成”，未暂存、提交、推送、切分支、创建 PR 或清理其他任务内容。
- 2026-07-29：用户确认自定义头像属于 Project Kei 控制台前端 UI 美化数据，不应
  仅保存在浏览器。PK-100 因此撤销未完成的 IndexedDB 方向，新增 dashboard 自有
  `GET/PUT/DELETE /api/v1/dashboard/ui-assets*` 和 Git 忽略的原子素材目录；只接受
  本机可信请求、合法 panel ID、8MB 内且签名匹配的 PNG/JPG/WebP。前端设置改为
  “更换头像/恢复默认”，上传成功后跨刷新恢复，失败仅保留本页预览。展开结构同时
  改为 280×350 媒体列 + 完整详情列，原业务内容进入右侧以消除大片留白；窄屏为
  260×325 单列。资源版本提升为 `pk100-20260729-widget8`，没有修改任何业务模块
  API、规则、凭据或数据文件。
- 2026-07-29：进一步明确 PK-100 是全部控制台组件的统一 UI 注册层；每个组件用
  稳定 `panel_id` 关联标题、说明、仓库默认图、设置入口和用户自定义图。新增组件
  只同步展示元数据/模块目录并复用通用 UI asset API，不给业务 router 增加头像
  契约。dashboard 模块目录已登记该通用接口、外观数据所有权、网络副作用和失败
  模式。
- 2026-07-29：Browser 使用临时预览路径上传仓库内安全图片到 `briefing` 夹具，
  刷新后同源头像 URL 仍恢复；点击“恢复默认”并再次刷新后回到“添加图片”空槽。
  桌面展开卡媒体列为 280×350，详情/原业务内容同处右列且无大片空白；375px 视口
  下为 260×325 单列，document 与组件横向溢出均为 0。未点击 QQ start、focus
  启停、采集、保存、模型、打卡、删除或个人状态写操作；预览素材只写临时目录，
  预览进程和 Browser 会话均已关闭。
- 2026-07-29：最终复跑 8 个 dashboard JavaScript 文件 `node --check` 与
  `api.py`、dashboard router/store、Catalog、专项测试 `py_compile` 均通过；
  Dashboard shell、Feature Catalog、focus module、8 项 QQ control、B 站
  collector/feature/credentials 全部通过。`scripts/check_task_docs.py` 通过
  24 个门禁任务，`git diff --check` 退出 0，仅有混合工作区既存 LF→CRLF 提示。
  PK-100 保持“待集成”，未暂存、提交、推送、切分支、创建 PR 或清理其他任务内容。
- 2026-07-29：根据项目默认素材与用户覆盖的所有权区别，将设置文案改为“设置本机
  图片”，并明确保存的是当前安装实例的自定义覆盖，不会修改项目默认素材；“恢复
  默认”明确删除覆盖并回到仓库默认图/空槽。API、目录与业务契约均未改变，专项
  JavaScript 语法、Dashboard shell、24 项文档门禁和 `git diff --check` 通过。
- 2026-07-29：为顶部服务摘要增加“正常/需要处理”两类共享状态视觉槽；卡片根据
  既有 `serviceOk()` 结果选择 56px 圆角图片，窄屏为 50px，无图片时显示勾号或
  感叹号。点击图片只展开“设置本机图片/恢复默认”，分别以
  `service-status-normal`/`service-status-attention` 复用 PK-100 UI asset API；
  未新增健康检查、服务启停、配置写入或业务接口。资源版本提升为
  `pk100-20260729-widget9`。
- 2026-07-29：Browser 脱敏预览确认四张服务卡按既有状态显示正常/提醒视觉；
  桌面状态图为 56×56，点击正常状态图后出现“设置本机图片/恢复默认”菜单。375px
  视口下四卡单列、状态图为 50×50，document `scrollWidth === clientWidth`，
  warning/error 日志为空。未选择文件，未点击刷新、生成、ASR、TTS、QQ 或任何
  业务操作；临时预览进程和 Browser 会话已关闭。
- 2026-07-29：状态视觉最终复跑 9 个 dashboard JavaScript 文件 `node --check`
  与相关 Python `py_compile` 通过；Dashboard shell、Feature Catalog、focus
  module、8 项 QQ control、B 站 collector/feature/credentials 全部通过。
  `scripts/check_task_docs.py` 通过 24 个门禁任务，`git diff --check` 退出 0，
  仅有混合工作区既存 LF→CRLF 提示。
- 2026-07-29：用户报告状态图上传后刷新消失。检查确认
  `service-status-normal.png` 与 `service-status-attention.png` 均已真实写入，
  store 列表和图片读取返回正确记录/200；根因是素材目录 JSON 未声明 `no-store`，
  浏览器可能在刷新时复用上传前的空目录。修复为目录响应和前端 fetch 双重
  `no-store`，状态图 URL 附加 `updated_at` 版本；资源版本提升为
  `pk100-20260729-widget10`，不修改已保存图片或业务接口。
- 2026-07-29：脱敏临时目录端到端复验先以仓库安全图片写入正常状态槽，确认目录
  响应为 `Cache-Control: no-store, max-age=0`/`Pragma: no-cache`；随后连续两次
  浏览器刷新均恢复同一 `?v=<updated_at>` 图片，页面 warning/error 为空。真实
  素材仅核对文件名、大小和只读接口结果，未读取内容、覆盖或删除。由于后端响应头
  属于已启动 router 代码，用户需要重启一次主 API 后再刷新控制台。最终 9 个
  dashboard JavaScript、相关 Python 编译、Dashboard/Catalog/focus/QQ/B 站回归、
  24 项文档门禁和 `git diff --check` 全部通过。
- 2026-07-29：用户再次报告保存成功后仍看到勾/感叹号。Browser 脱敏夹具确认图片
  目录、带版本 URL 和 `<img>` 均已正确恢复；实际根因是占位符虽带 `hidden`，
  `.service-status-visual-placeholder { display:grid }` 仍覆盖浏览器原生隐藏样式，
  将图片挤到 56px 裁剪区外。公共 CSS 现为占位符和状态图补充显式 `[hidden]`
  规则，资源版本提升为 `pk100-20260729-widget11`；不改素材数据、状态 API 或业务
  请求。
- 2026-07-29：修复后 Browser 再次刷新，正常状态自定义图与 56px 卡槽重合，
  占位符计算样式为 `display:none`；375px 视口下状态图内容区为 48×48（外框
  50×50），`scrollWidth === clientWidth`，warning/error 日志为空。验收只向
  临时预览目录写入仓库安全夹具图，未读取、覆盖或删除用户真实素材，未调用任何
  业务写 API。9 个 dashboard JavaScript 语法、相关 Python 编译、
  Dashboard/Catalog/focus/QQ/B 站定向回归均通过；`scripts/check_task_docs.py`
  通过 24 项文档门禁，`git diff --check` 退出 0，仅报告混合工作区既有
  LF→CRLF 提示。
- 2026-07-30：用户确认当前控制台的 15 张本机自定义图片已基本敲定，授权将其
  提升为项目默认素材。PK-100 保留 Git 忽略的本机覆盖文件不动，将相同 PNG
  复制到版本化的 `server/static/dashboard/default-avatars/`，并在
  `panelVisualRegistry` 中按稳定 `panel_id` 登记 13 个组件默认图；QQ 继续使用
  既有 `qq-launch.png`，没有重复或改变其单向启动契约。动态 focus 使用
  `module-focus` 注册键，随 module-loader 生成的 panel ID 自动取得默认图。
- 2026-07-30：服务摘要的 `service-status-normal` 与
  `service-status-attention` 同步登记仓库默认图。本机 UI asset 记录存在时仍
  优先显示自定义覆盖；用户点击“恢复默认”后回到带
  `pk100-20260730-defaults1` 版本标记的同源静态图。普通页面加载不新增外网、
  安装、采集、模型、QQ、业务写入或浏览器存储副作用。
- 2026-07-21：PK-000 根据当前模块化单体与可安装模块规范完成正式登记，确认本任务只划定公共外壳和前端装载边界；未领取、未修改业务代码、未运行服务或业务测试。
- 2026-07-21：本对话领取 PK-100。计划先保留 `dashboard.html` 中的业务面板与既有 ID，抽出公共样式、同源请求、通知、折叠状态、页面启动、模块注册和失败隔离；不调用生命周期写接口或任何真实采集、付费模型、QQ 消息、删除、打卡及个人状态写入操作。
- 2026-07-21：完成第一阶段渐进拆分。新增 `server/static/dashboard/` 公共资源目录，将原有 CSS 原样迁入 `shell.css`，将同源请求、通知、折叠状态、启动、模块注册与装载分别放入小型 ES modules；`dashboard.html` 保留全部既有业务 DOM、元素 ID、按钮处理与 API 路径，通过 `bootstrapDashboard({loadLegacy: load})` 形成唯一兼容接缝。
- 2026-07-21：新增只读功能中心和 `#dashboard-module-mounts` 边界。目录卡片只展示状态摘要；页面不会调用安装、启停、升级、回滚、卸载或清除数据接口。加载器只处理已启用且具有入口的模块，并校验同源模块资产前缀、模块 API 命名空间和 10 秒超时；入口失败不会中断 legacy 面板或其他入口。
- 2026-07-21：`server/features/dashboard/router.py` 只提供 `/dashboard/static/{asset_path}` 并阻止路径穿越；`server/features/catalog/service.py` 将 dashboard 标记为首次安装必需的 `core_builtin`、`modular` 模块，并同步静态资源入口，不改变其他模块的生命周期状态或接口字段。
- 2026-07-21：为 Browser 验收在 `test_dashboard_shell.py --preview` 中建立去标识化只读夹具，所有业务写路由均不存在，并加入一个故意 404 的模块入口。Browser skill 已按规定连接，但其 URL 安全策略阻止访问本机预览地址，并明确禁止用其他浏览器、变体 URL 或间接控制绕过；因此未执行鼠标/键盘折叠、通知和移动端视觉验收，也未宣称通过。
- 2026-07-21：用户随后在普通浏览器打开同一只读预览，确认故意缺失的 `preview_missing` 入口只在“失败隔离夹具”中显示动态导入失败，每日情报关注对象为去标识化空夹具（全部 0），其余页面样式、面板展开/收起、折叠状态保持和移动端布局均正常。人工补验未连接真实 API，也未触发业务写操作。
- 2026-07-21：PK-900 集成验收修正两项公共外壳缺陷：功能中心最近操作改为读取 PK-010 实际返回的 `last_operation.action`；模块入口失败信息增加窄屏任意位置换行，避免包含长同源 URL 时产生横向溢出。定向测试新增临时模块包跨层夹具，验证安装、启用、目录合并、入口 URL 和 dashboard 资产边界。
- 2026-07-21：PK-000 独立复核确认 PK-100 定向测试与跨层接缝通过，未发现新的外壳专属阻断项；批次因 PK-010 Core 保留 ID/namespace 隔离缺口退回，PK-100 保持“待集成”等待依赖整改和批次重验。
- 2026-07-21：PK-010 依赖整改后，PK-000 二次独立复验确认目录 Core 契约不可被覆盖，PK-100 定向测试、跨层夹具和六个公共 JavaScript 语法检查继续通过；PK-100 随本批验收完成。

### 当前代码划分

- 公共外壳：`shell.css`、`theme.js`、`request.js`、`notifications.js`、
  `avatar-store.js`、`panels.js`、`registry.js`、`module-loader.js`、`app.js`。
- 版本化默认视觉：`default-avatars/*.png` 由 `panels.js` 的
  `panelVisualRegistry` 和 `status-visuals.js` 的状态注册表引用；组件升级只需
  发布新素材版本并更新对应注册条目。本机 UI asset API 始终作为实例级覆盖层。
- 模块控制面：`module-management.js` 独占官方缓存状态机、三类目录渲染、显式
  确认、生命周期 busy 锁、重启/数据保留提示和失败隔离；不复制 PK-010 规则。
- UI 素材后端：`features/dashboard/ui_assets.py` 独占校验与原子文件持久化，
  `features/dashboard/router.py` 独占 dashboard UI asset HTTP。
- 动态业务接缝：`dashboard.html` 不再拥有任何情报、X/B 站、QQ、LLM、好感度、
  斩妖、健身、专注、日历、记忆、语音或定时推送 DOM/函数；这些模块仅在 registry
  返回 `enabled=true` 且提供受信 `dashboard_entrypoint` 时，由
  `module-loader.js` 取得 `mount(context)`/`unmount()` 生命周期。
- 公共读取 API：`GET /dashboard`、`GET /dashboard/static/{asset_path}`、
  `GET /dashboard/status`、`GET /api/v1/modules`、
  `GET /api/v1/modules/official-catalog`、
  `GET /api/v1/dashboard/ui-assets*`；头像 `PUT/DELETE` 只来自用户明确设置操作。

### 数据与副作用

- 新增服务端持久化：`server/data/dashboard_ui/avatars/`，只保存显式上传的控制台
  外观图片并被 Git 忽略；测试使用临时目录。普通读取不创建目录，PUT 原子替换，
  DELETE 仅清对应 panel ID 的允许图片后缀。
- 项目默认图片是只读、可版本化的公共静态文件。本轮仅复制用户明确确认的
  15 张控制台 UI 图片，未删除或改写其本机覆盖副本，也未读取业务数据、凭据、
  名单、缓存、模型、个人状态或 `vendor/`。
- 缓存副作用：仅改变控制台 HTML/公共静态资源的 HTTP 缓存头，并同步前端资源
  版本标记；不读取或清除浏览器业务数据，不触发业务 API，也不改服务端业务缓存。
- 浏览器持久化：沿用 `project-kei.dashboard.panel-open.v1`，值为
  `{panel_id: boolean}`；新增 `project-kei.dashboard.theme.v1`，值仅可为
  `cloud/sakura/moon`。两者都属于纯 UI 状态；未使用 `sessionStorage`，也未保存
  业务配置、日程、名单、凭据、缓存或个人状态。
- 设置入口不新增浏览器持久化。打开/关闭、生成设置项和定位原控件均只修改当前
  DOM/焦点；头像更换/恢复只调用 dashboard 自有 UI API，不自动触发原业务保存、
  启动或采集按钮。
- 模块管理：页面加载只读本机 registry 与官方 Catalog 缓存；显式刷新官方目录
  和确认后的官方安装/更新/回滚才可能让 PK-010 联网。启停、检查配置、回滚、
  卸载和 purge 仅由用户点击当前 `available_actions` 后调用同源 PK-010 API；
  浏览器不保存 Catalog、模块包、路径、Token/Cookie 或生命周期状态。

### 遗留问题

- 共享文档与 Catalog 的旧叙述仍可能把部分业务称为“内置功能”或写成“首批只有
  focus”。PK-000 明确冻结 README、TASKS、Catalog 与架构共享 hunk，本轮未越权
  修改；串行收口时应统一为“Core 固定三项 + 19 个可安装业务包”。
- `server/features/catalog/service.py` 的展示元数据若仍列举 legacy
  `dashboard_surface`，其所有权不在 PK-100；当前生产 UI 不读取该字段，也不会
  据此渲染业务面板，后续由 PK-000/对应目录任务清理。
- 浏览器本地 ZIP 上传尚无已冻结的流式输入契约；本轮只在高级区解释边界，不暴露
  旧 `package_path`。后续若保留离线安装，必须由 PK-010 先提供不接受服务器路径
  的受控 ZIP 上传接口。
- PK-010 当前官方 install/update/rollback 是同步请求，只在结束后返回
  `official_operation.phase`，没有轮询或事件流可准确报告实时字节与
  downloading → verifying → installing 切换。PK-100 已冻结全部阶段状态和
  结构化失败 `stage`，请求中诚实显示“Core 正在下载、校验并安装”，不伪造进度；
  若 PK-900 要求实时分阶段进度，需由 PK-010/PK-000 决定新增只读进度契约。

未执行真实 QQ/B 站/业务 API 端到端，因为这会扩大到凭据、进程、外部网络或个人
数据。Browser 中原生折叠按钮可获得焦点，鼠标折叠及刷新恢复通过；当前浏览器
控制层的合成 Enter 未触发按钮 activation，因此键盘契约以原生 `<button>`、
`aria-expanded` 和静态回归固定，留给 PK-900 在其浏览器环境复按。

### 验证结果

- 2026-07-30 最终生产收口：`tests/test_dashboard_shell.py` 通过，覆盖 Core-only
  HTML、19 个 package manifest、18 个动态入口/YouTube 无面板、入口无 global
  `fetch`、12 个公共 JS 的 `node --check`、Core 三项保护、同源/namespace
  拒绝、registry 幂等 mount/unmount、本地头像临时目录 API、15 张默认 PNG 和
  静态路径穿越。fake Browser 普通加载只请求 Core status、registry、官方缓存、
  本地 UI 素材与已启用入口；审计无业务 API、无官方刷新、无生命周期写操作。
  Catalog 元数据为 19 项且 `network_accessed=false`；Core 卡精确为
  `catalog/module_manager/dashboard`，Focus 成功动态挂载、Calendar 404 仅自身
  失败、YouTube 显示后台 Collector。主题切换/reload、鼠标折叠/reload、ARIA 和
  375px 单列均通过，移动端控件/图片无溢出，document 无水平滚动。
  `test_official_module_catalog.py` 与 `test_installable_modules.py` 通过；
  `test_feature_catalog.py` 在项目 `.venv-asr` 的 Python 3.8.20 导入共享
  `api.py` 时因其 `dict[str, Any]` 注解需要 Python 3.9+（或
  `eval_type_backport`）而停止，系统 Python 3.12 又未安装 Starlette。该失败发生
  在测试收集/应用导入阶段，与 PK-100 HTML/JS 无关，本轮未安装依赖或越权修改
  `api.py`。`scripts/check_task_docs.py` 通过 24 项，`git diff --check` 退出 0，
  仅有混合工作区既有 LF→CRLF 提示。
- 2026-07-30 默认素材注册专项：15 张经用户确认的 PNG 已完整复制到
  `server/static/dashboard/default-avatars/`，均通过 PNG 签名检查且不受
  `.gitignore` 排除；嵌套静态资源路由解析到 dashboard 公共目录内。11 个
  dashboard JavaScript 文件逐项 `node --check` 通过；
  `tests/test_dashboard_shell.py`、`tests/test_feature_catalog.py` 与
  `tests/test_focus_module.py` 通过。回归固定 13 个 panel 注册键、2 个状态注册键、
  `pk100-20260730-defaults1` 版本、同源路径、本机覆盖优先和恢复仓库默认语义。
  未启动服务、访问外网、调用业务 API 或修改原本机图片。
- 2026-07-30 模块中心专项：11 个 dashboard JavaScript 文件逐项 `node --check`
  通过；`tests/test_dashboard_shell.py` 通过，新增覆盖官方状态机、空/单 focus
  Catalog、精确确认、required/内置保护、无 URL/path、重复点击锁、结构化错误、
  ARIA、移动端和无浏览器下载。`test_official_module_catalog.py`、
  `test_feature_catalog.py`、`test_installable_modules.py` 全部通过，均使用 fake
  HTTP/ASGI 与临时 registry/runtime/data，不访问真实 GitHub 或用户状态。
- 2026-07-30 Browser fake 预览：官方 focus 展示、安装确认/取消、显式目录刷新、
  已安装失败夹具隔离、内置零动作、主题 reload、折叠 reload、375px 单列无溢出
  通过；未确认任何生命周期写操作，未读取真实模块数据、凭据或个人状态。

- 2026-07-28 后续视觉验收：`node --check server/static/dashboard/panels.js`、
  `node --check server/static/dashboard/app.js` 和
  `server/.venv-asr/Scripts/python.exe server/tests/test_dashboard_shell.py` 通过。
  Browser 脱敏预览确认 13 个 legacy 主功能均生成公共摘要头；QQ 收起后标题明确
  “单击头像可以启动 QQ”，每日情报点击标题后显示完整说明和 9 个原有来源分组。
  375px 实际视口下 document `scrollWidth === clientWidth === 375`，QQ 外层头像按钮
  为 56px，长标题自然换行且右边界位于卡片内。全程未点击 QQ 头像、生成、采集、
  保存、打卡、删除或模型操作；标题点击仅写既有纯 UI 折叠键。Browser 控制层的
  合成 Enter 仍未激活原生按钮，保留 PK-900 人工键盘复验；DOM 使用原生
  `<button>`、`aria-expanded` 和可见焦点，静态回归继续锁定该契约。最终再次运行
  Dashboard 公共 JS、Dashboard shell、Catalog、QQ control、B 站 collector/feature/
  credentials 回归均通过；`scripts/check_task_docs.py` 通过当前 24 个门禁任务，
  `git diff --check` 退出 0，仅有混合工作区既有 LF→CRLF 提示。
- 2026-07-28 小组件网格复验：Browser 脱敏预览在 1265px 宽度确认连续三列组件，
  收起卡为约 343×136px，小图/图片入口为 64px；展开每日情报后组件宽约 1060px，
  大图槽约 1026×420px，完整说明和 9 个来源分组继续存在。375px 实际视口为单列，
  小图 56px、大图约 319×179px，页面和全部面板均无水平溢出。QQ 标题展开得到
  同样的大图位，未点击头像，start API 调用数为 0；开发者 error/warn 日志为空。
- 2026-07-28 动态折叠复验：脱敏预览通过真实 focus 前端入口与只读
  `/api/v1/focus/status` fixture 验证挂载完成后自动获得公共卡头。桌面收起时 QQ
  为 64×64 圆形、focus 为 64×64 且 `border-radius:16px`，两者均显示
  “展开详情 ▾”及 `aria-expanded=false`；focus 展开后媒体槽约 1026×420px，
  原有状态/模式/任务/开始与停止入口存在。375px 下两者均为 56×56，页面和卡片
  `scrollWidth === clientWidth`。未点击 QQ 头像或 focus 开始/停止/reset，日志无
  error/warn。最终公共 JS、Dashboard shell、focus module、Catalog 和 8 项 QQ
  control 回归通过；文档门禁通过当前 24 项，`git diff --check` 退出 0。
- 2026-07-28 缓存修复复验：同一 `/dashboard` 地址普通 reload 后，CSS 与入口
  均解析到 `?v=pk100-20260728-widget3`；QQ 标题明确显示“展开详情/收起详情”，
  动态 focus 同样获得公共折叠按钮。Browser 只点击标题折叠：QQ 收起外框在
  375px 视口为 56×56 圆形，focus 收起图片槽为 56×56、16px 圆角，展开时原有
  状态、模式、任务及开始/停止入口均存在；document
  `scrollWidth === clientWidth === 375`，开发者日志为空。未点击 QQ 头像、
  focus 开始/停止/reset 或任何业务写操作。Dashboard shell 专项测试同时锁定
  HTML/静态资源 `no-store` 响应头与所有公共 import 的一致版本标记。
- 2026-07-28 缓存修复最终门禁：Dashboard shell、Feature Catalog、focus module、
  8 项 QQ control、B 站 collector/feature/credentials 全部通过；`api.py`、
  dashboard router 与测试夹具 `py_compile` 通过，8 个相关前端 JS 逐项
  `node --check` 通过。`scripts/check_task_docs.py` 通过 24 项任务，
  `git diff --check` 退出 0，仅报告混合工作区既有 LF→CRLF 提示。
- 2026-07-29 公共设置入口 Browser 验收：预览中的 15 个顶层卡（13 个 legacy、
  动态 focus、失败隔离夹具）均有独立设置按钮。LLM 设置面板列出方案、Base URL、
  模型 ID 与思考模式，点击“方案”后焦点准确位于原 `#llm-preset`，字段值未改变；
  focus 列出模式、自定义分钟和当前任务，原开始/停止按钮仍存在且未点击；QQ 只
  显示头像启动、刷新状态和无 stop 说明，DOM 中不存在停止控件。375px 下收起卡
  图片 56×56，标题右边界 272px、设置按钮左边界 282px，设置面板与 document
  `scrollWidth === clientWidth`，无 error/warn。全程只点击公共设置/定位按钮，
  未调用保存、启动、采集、模型、打卡、删除或个人状态写操作。
- 2026-07-29 设置入口最终门禁：Dashboard shell、Feature Catalog、focus module、
  8 项 QQ control、B 站 collector/feature/credentials 全部通过；8 个相关前端
  JS 逐项 `node --check`，API/dashboard router/测试夹具 `py_compile` 通过。
  `scripts/check_task_docs.py` 通过 24 项，`git diff --check` 退出 0，仅有混合
  工作区既存 LF→CRLF 提示。未读取或修改真实凭据、名单、缓存、vendor 或个人状态。
- 2026-07-29 整图适配 Browser 验收：QQ 原图自然尺寸 1122×1402，桌面展开媒体
  框为 680×383、实际图片框 676×379，计算样式为 `object-fit:contain`、
  `object-position:50% 50%`、`transform:none`；QQ 与动态 focus 收起态均为
  64×64、16px 圆角。375px 视口下 QQ 展开为 319×179、收起为 56×56，
  document `scrollWidth === clientWidth`，页面 error/warn 日志为空。只点击
  公共标题折叠，未点击 QQ 头像或任何业务操作。
- 2026-07-29 整图适配最终回归：Dashboard shell、Feature Catalog、focus module、
  8 项 QQ control、B 站 collector/feature/credentials 全部通过；8 个相关前端
  JS 逐项 `node --check` 通过。静态回归固定 680px/16:9/contain、QQ 通用圆角
  矩形、无旧 16:7 和无放大 transform 契约。
- 2026-07-29 竖版角色卡 Browser 验收：桌面 QQ 媒体框为 320×400（比例 0.8），
  图片 `object-fit:contain`、`transform:none`；标题起点位于图片右侧 20px，
  状态/刷新/设置与标题同列，document 无横向溢出。375px 视口下图片为 280×350、
  水平中心偏差 0，标题位于图片下方，`scrollWidth === clientWidth`，页面
  error/warn 日志为空。只读取布局并复用标题折叠状态，未触发 QQ start。
- 2026-07-29 竖版角色卡最终回归：Dashboard shell、Feature Catalog、focus
  module、8 项 QQ control 与 B 站 feature 通过；8 个相关前端 JS 逐项
  `node --check` 通过。静态回归固定桌面 320×400、窄屏 280×350、4:5、两列转
  单列、contain 和无放大 transform。
- 2026-07-28：公共 dashboard 7 个 JavaScript 文件逐项 `node --check` 通过；
  `tests/test_dashboard_shell.py` 通过，覆盖三主题变量/default、切换与刷新恢复、
  `localStorage` 读写异常降级、theme/panel 脚本零请求、无 JS 基本可读、QQ
  单 click 单 start 且无 stop、结构化卡头/ARIA、移动端头像和无溢出静态契约、
  内联脚本语法、模块入口过滤与失败隔离。
- 2026-07-28：`tests/test_feature_catalog.py`、`tests/test_qq_control.py`、
  `tests/test_bilibili_collector.py`、`tests/test_bilibili_feature.py`、
  `tests/test_bilibili_credentials.py` 全部通过。B 站测试继续使用虚构 Cookie、
  MockTransport 和临时目录；QQ control 使用 fake process/临时日程。
- 2026-07-28：QQ bridge `node --test tests/*.test.mjs` 为 83/83，通过；全部
  `src/*.mjs` 与 `tests/*.mjs` 逐文件 `node --check` 通过。未启动 sidecar、BAT、
  Gateway、Token、真实 QQ、业务 API、LLM、Collector 或发送。
- 2026-07-28 Browser 只读预览：云朵白、樱花粉、月夜蓝切换成功，樱花粉刷新
  后恢复；QQ 折叠刷新后保持，B 站父栏目与参数卡独立展开；桌面 QQ/B 头像为
  64/42px，375px 视口为 56/36px，document、QQ 卡头、标题和动作的
  `scrollWidth === clientWidth`。QQ 未就绪按钮保持禁用；故意缺失入口仅在自身
  显示失败；控制台无额外 error/warn。预览不含业务写路由，未点击采集、保存、
  生成、启动、打卡、删除或个人状态操作。
- 2026-07-28：最终 `tests/test_dashboard_shell.py`、B 站凭据回归、公共 JS
  `node --check` 与两项 Python 测试文件 `py_compile` 复跑通过；
  `scripts/check_task_docs.py` 在状态切换前通过 24 项。根 `scripts/python.ps1`
  的最终调用先因工作目录写错、随后因本机 PowerShell execution policy 被拒；
  按项目既有解释器直接执行
  `server/.venv-asr/Scripts/python.exe scripts/check_task_docs.py` 后通过 25 项，
  不是文档或代码失败。最终 `git diff --check` 退出 0，仅报告混合工作区既有
  LF→CRLF 提示。

- 通过：`server/.venv-asr/Scripts/python.exe server/tests/test_dashboard_shell.py`（从 `server/` 目录以 `./.venv-asr/Scripts/python.exe tests/test_dashboard_shell.py` 执行）。覆盖既有关键元素 ID、外部 CSS/ES module 接缝、唯一 UI 存储边界、内联 legacy 脚本 `new Function(...)` 语法、所有公共 JS `node --check`、启用/停用/缺入口过滤、同源入口、模块资产前缀、请求命名空间拒绝、静态路径穿越和应用路由。
- 通过：`server/.venv-asr/Scripts/python.exe server/tests/test_feature_catalog.py`；dashboard 目录项为必需 `core_builtin`、`modular`，现有模块目录契约继续可解析。
- 通过：`server/.venv-asr/Scripts/python.exe -m py_compile api.py features/dashboard/router.py features/dashboard/ui_assets.py features/catalog/service.py tests/test_dashboard_shell.py`。
- 通过：`node --check` 对 `request.js`、`notifications.js`、`panels.js`、
  `registry.js`、`module-loader.js`、`app.js`、`theme.js` 和
  `avatar-store.js` 逐项执行。
- 通过：`server/.venv-asr/Scripts/python.exe scripts/check_task_docs.py`，输出 `task documentation gate passed: 2 gated task(s)`。
- 通过：`git diff --check`，退出码 0；仅输出工作区既存的 LF→CRLF 转换提示，无空白错误。另用 `rg -n '[ \t]+$'` 检查 PK-100 新增/修改路径，无匹配。
- 通过（人工补验）：Browser skill 已连接 Codex In-app Browser，但自动访问被本机 URL 安全策略拒绝且未绕过。用户随后在普通浏览器检查同一去标识化只读预览，确认预期的单模块 404 隔离、空关注名单夹具、其余页面样式、面板折叠/状态保持和移动端布局正常；没有连接真实 API 或触发采集、付费模型、QQ 消息、删除、打卡、配置保存及个人状态写入。

## 完成文档门禁

本轮官方模块中心增量进入“待集成”前重新执行全部八项；旧基线勾选不替代本轮记录。

- [x] TASK_RECORD — 已记录三类模块视图、官方接口矩阵、默认视觉注册、
  本机覆盖优先级、确认/并发/错误状态、数据副作用、测试结果和发布装配遗留。
- [x] TASKS_BOARD — PK-000 已将 PK-100 置为“进行中”，并明确要求本对话不要修改
  `TASKS.md` 的共享 hunk；本任务文件最终置“待集成”，任务板串行回写交 PK-000。
- [x] PUBLIC_README — 本轮不适用：PK-000 明确保留 PK-010/100/180 收口后的
  README 串行窗口且最终增量再次冻结 README；准确的模块中心用户操作文案与
  Core-only 展示契约已写入本任务工作记录。
- [x] MODULE_CATALOG — 本轮不修改 PK-010 catalog service/schema：组件图片属于
  PK-100 前端视觉注册，不改变 `managed`、`installed_version`、
  `available_actions` 或安装包字段；19 个模块仅消费现有 manifest/entrypoint。
- [x] ARCHITECTURE_DOCS — 本轮不适用：PK-000 明确冻结共享架构 hunk；当前实现
  只消费 PK-010 已冻结的官方目录/包契约。需要清理的“内置功能/首批 focus”旧
  叙述已列入遗留问题，交 PK-000 串行回写。
- [x] LOCAL_README — 不适用：没有改变本机路径、端口、启动器、解释器或环境；
  8765 仅为已经关闭的 fake Browser 预览。
- [x] AGENT_RULES — 不适用：没有改变 agent 工作流、安全、验证、文档或 Git 规则。
- [x] VALIDATION — 已记录 15 张 PNG/静态路由、19 个 manifest、18 个动态入口、
  YouTube 后台能力、Core 三项、Dashboard shell、12 个 JavaScript 语法检查、
  fake Browser 桌面/375px、请求审计、文档门禁和 `git diff --check`；未访问
  真实 GitHub、registry、runtime/data、模块状态、凭据、缓存、模型或个人数据。

## 独立对话启动提示

```text
领取 Project Kei 的 PK-100 控制台公共外壳任务。先完整阅读 README.md、
AGENTS.md、README.local.md（如存在）、TASKS.md、
tasks/PK-100-dashboard-shell.md、docs/architecture/modular-monolith.md 和
docs/architecture/installable-modules.md，检查 git status 与实际控制台代码。
只处理公共外壳、功能中心、请求/通知工具和模块入口加载；消费 PK-010 的公开目录
与生命周期接口，不直接修改注册表或各业务模块规则。跨模块契约变化先记录并交
PK-000 确认，完成前执行本任务的全部文档和验证门禁。
```

## 2026-08-01 本机模块恢复后的布局与健康摘要修复

- 实机安装 19 个模块后确认公共 `main` 三列网格把三个新增包装区误当作单张卡片：Core 摘要、模块管理和动态模块区分别被挤入左/中/右列，而 `#dashboard-module-mounts { display: contents; }` 又把所有业务卡继续限制在右列。修复为三个包装区始终跨整行，动态挂载区独立使用桌面三列、窄屏两列、移动端单列；展开卡继续跨整行，页面无横向溢出。
- 恢复 Core 健康摘要对 PK-210 已有只读 `voice_runtime_control_provider.status()` 和 PK-200 公开 `conversation_service.get_profile()` 的消费：只显示 API、ASR、GPT-SoVITS 与非秘密 LLM Base URL 状态，不启动进程、不探测上游模型、不返回 API Key。ASR/GPT-SoVITS 的显式启动仍只归 voice 动态面板。
- 本机动态入口失败的根因不是模块代码，而是隔离安装进程创建的 runtime 目录 ACL 未授予实际 Windows 登录用户读取权限；已仅对 `server/runtime/modules/` 授予当前登录用户权限，未触碰个人状态、模型、凭据或缓存。权限恢复后 conversation 配置检查通过，17 个 in-process 模块形成无错误激活图；QQ/GPT-SoVITS sidecar 仍不自动启动。
- 永久回归在 `test_dashboard_shell.py` 锁定包装区全宽、动态三列网格、响应式降列和禁止 `display: contents` 回退；Dashboard shell、模块生命周期、voice runtime control、voice installable、Bilibili installable 与官方 Catalog 专项均通过。

## 2026-08-01 模块界面分组与既有资料恢复

- 冻结“安装单元独立、界面按领域聚合”：`intel_sources`、`x_monitor`、`bilibili`、`github_intel`、`papers`、`rss_intel` 仍是六个独立可安装模块，但控制台统一显示为“每日情报来源与采集”总卡片，并以来源配置、X/Nitter、B 站、GitHub、论文、RSS 六个本地标签页切换。`voice`、`voice_pack_registry`、`voice_pack_distribution` 同理聚合为“语音与 Voice Pack”总卡片的三个标签页。

## 配置面板与折叠能力恢复（2026-08-01）

- “配置就绪情况”恢复为独立可展开/收起的 Core 面板。动态 loader 除正常 enabled
  模块外，只额外装载 `needs_configuration` sidecar 的受信 dashboard entrypoint；
  不因此启用模块、启动进程或复制业务 API 到公共外壳。
- QQ 动态面板恢复“QQ 功能启动 / 每日情报定时推送 / 生命维持系统”三个独立
  `<details>`；好感度与长期记忆也恢复为两个独立 `<details>`。所有折叠操作只改变
  页面状态，零业务写入、零外部网络。
- 公共 loader/HTML/JS 统一提升缓存标记，避免重启 Core 后仍命中旧入口。专项回归
  覆盖配置型 sidecar 允许、普通 disabled 模块拒绝、配置就绪标题和动态入口契约。
- 标签切换只改变已经挂载的本地 DOM，不重新请求 API、不联网、不改变模块生命周期；任一子模块停用/卸载时只移除自身标签，其他子模块继续可用。总卡片使用公共默认插图，不再为每个子模块生成空头像卡。
- Browser 实机验收确认两个总卡均为 1060px 全宽、情报六标签与语音三标签各自始终只有一个可见面板、空头像数量为 0、页面与总卡水平溢出均为 0。B 站与来源配置资料恢复只核对条目数量/非空字段长度，没有输出来源内容。
- 永久回归补充聚合成员清单、全宽总卡、ARIA tab/tabpanel、隐藏非活动面板和资源版本门禁；模块仍通过各自受限 `mount(context)` 加载，公共外壳不复制任何业务规则。

## 聚合卡收起尺寸与模块自有子卡（2026-08-01）

- `.module-group` 仅在展开时跨越整行；收起后回到与普通模块一致的三列小方块布局，
  并随公共断点降为两列/一列。
- 动态入口可用 `.module-owned-panels` 声明多个独立子卡；公共外壳为每个稳定
  `data-panel-id` 继续提供图片、设置、折叠、ARIA 和响应式能力。父安装单元本身不再
  占据一张空白大卡。
- QQ 的启动、每日推送与生命维持作为首个三子卡实例；不改变 QQ 的单 sidecar 生命周期。

## 情报与语音组合面板视觉回归（2026-08-01）

- 控制台展示层把情报来源六个独立安装模块收纳为一个工作区，并把语音编排、Voice Pack 注册表与远程安装收纳为另一个工作区；安装、启停、卸载和数据所有权仍按原模块独立处理。
- 情报工作区恢复紧凑无大图布局；顶部来源切换栏采用本地 DOM 切换并在长列表滚动时保持可见，切换不会发起 API 或业务网络请求。
- X 用户头像固定为 `52px` 紧凑摘要，用户内容继续按账号折叠；B 站、GitHub、论文及 RSS 原有功能入口不改变。
- 情报来源配置由其所有者模块渲染，再由公共外壳投放到 X、B 站、GitHub、论文对应子页；没有扩大任一采集模块的 API namespace，也没有复制配置业务规则。
- 语音与 Voice Pack 新增组合面板保留图片设置能力，后续可由用户分别配置本机图片。
## 动态模块紧凑卡收口（2026-08-01）

- 修正动态模块网格：聚合模块仅在展开时跨满整行，收起后一律恢复为与普通模块一致的小卡片。
- 动态入口可通过 `.module-owned-panels` 声明多个独立子卡；每个子卡继续使用公共折叠、头像、设置与响应式契约。
- 增加一次性 `project-kei.dashboard.compact-cards.v2` 本地 UI 状态迁移，清除旧布局遗留的展开状态；仅写浏览器 `localStorage`，零业务 API、零网络副作用。
- 验证：dashboard shell 脚本测试通过；`panels.js`、`module-loader.js`、`app.js` Node 语法检查通过。任务状态保持“待集成”。

## QQ 启动卡与模块管理紧凑显示修正（2026-08-01）

- `模块管理` 不再由公共网格强制占满整行；收起时与其他功能一致显示为小卡片，展开时仍可使用完整管理界面。
- QQ 启动卡强制使用仓库既有 `/dashboard/assets/qq-launch.png`，避免已安装旧面板引用不存在的默认头像而显示破图。
- QQ 插图本身代理既有显式 `POST /api/v1/qq-control/start` 按钮；运行中继续禁用，未增加自动启动、重复进程或新的业务接口。
- `打开 QQ 开放平台配置机器人` 使用明确按钮样式，但仍只是用户主动点击的外部链接；页面加载、折叠和图片显示均不触发外部网络。
- Browser 实机只读验收确认：模块管理为小卡、QQ 原图完整显示、状态为 `running` 时插图按钮禁用、配置入口为按钮。未点击启动或外部链接，未读取 QQ 配置。

## 好感度与长期记忆双卡兼容（2026-08-01）

- 公共视觉注册表为 `module-affection` 和 `module-long-term-memory` 提供独立默认插图；父安装单元使用 `.module-owned-panels` 后不再显示为一张合并大卡。
- Browser 实机确认两个独立标题、图片、设置与折叠按钮均已生成，原动态入口 409 已由正式 1.0.3 更新恢复为 HTTP 200。公共外壳没有复制关系或记忆业务规则。

## 默认图片映射最终收口（2026-08-01）

- 已把仓库确认的公共 PNG 全部保持为只读默认素材；补齐
  `module-group-intelligence -> intel-sources.png`，语音聚合、QQ 启动、好感度、长期
  记忆、每日推送、生命维持及普通业务卡继续使用既有注册映射。收起状态仍为三列小卡，
  只有展开中的聚合卡跨整行，未恢复第一版的大图堆叠或平铺子模块布局。
- 每张卡继续复用 PK-100 的 `GET/PUT/DELETE /api/v1/dashboard/ui-assets*`：默认图只读，
  用户显式上传写入 Git 忽略的本机 UI 目录，“恢复默认”删除覆盖后回到仓库图片。
  页面加载、折叠、主题和默认图显示均不写业务 API，也不会把本机图片打入模块 ZIP。
- 用户在本机控制台确认的两张图片已提升为公开默认映射：
  `configuration-readiness -> configuration.png`、`module-group-voice -> voice-pack.png`；
  本机覆盖接口保持不变，后续仍可分别替换，不会互相覆盖。

## 每日情报聚合卡展开布局修复（2026-08-02）

### 根因与实现

- 实际聚合标识为 `data-dashboard-group="intelligence"`，稳定 UI 注册键为
  `module-group-intelligence`；默认图继续使用版本化本地素材
  `default-avatars/intel-sources.png`。`panels.js` 的默认映射、通用
  `data-panel-avatar` 恢复流程和 `/api/v1/dashboard/ui-assets/{panel_id}/avatar`
  本机覆盖接口原本均正确。
- 根因是 `shell.css` 中先后存在三组 intelligence 专用覆盖：它们在展开态强制
  单列并隐藏 `.module-avatar-main`/`.module-avatar-picker-wrap`，因此公共
  `module-shell-layout` 已经生成了大图和详情 DOM，页面却无法显示大图左栏。
- 删除上述布局例外，使聚合卡重新消费公共的桌面
  `minmax(220px,280px) minmax(0,1fr)` 双栏和移动端单列规则；仅保留聚合卡
  `overflow:visible`，用于来源标签栏的既有 sticky 行为。2026-08-01 工作记录中的
  “情报工作区紧凑无大图布局”已被本次用户确认的统一组件视觉契约取代。
- 收起态仍是标准 136px 小卡；展开态左侧显示完整 4:5 `object-fit:contain` 图片，
  右侧仍由动态 loader 保留来源配置、X/Nitter、B 站、GitHub、论文和 RSS 六个
  独立 tab/tabpanel 及各模块完整 DOM。未修改 PK-110/115/120 动态入口或业务规则。

### 接口、数据所有权与副作用

- 无新增或变更 API、请求字段、响应字段、模块生命周期和 Collector 契约。折叠、
  展开及来源标签切换只变更已挂载 DOM；页面初始请求仍限定为 Core status、UI 素材
  索引、本机 module registry、官方目录缓存和已启用模块的同源 entrypoint。
- 默认图片是仓库内只读静态素材；本机自定义图片仍由用户显式操作后写入 PK-100
  自有、Git 忽略的 UI 素材目录。本次 API 回归只使用临时目录，保存、读取、列出和
  删除 `module-group-intelligence` 覆盖图后自动清理，没有读取真实来源、缓存、
  Cookie、Token、`.env`、registry、runtime、个人状态或 vendor。
- Browser 验收使用 fake FastAPI 目录和六个无业务请求的 fixture entrypoint；预览
  进程验收后已关闭。没有启动真实 Project Kei、Collector、X/B 站、QQ、模型或
  sidecar，也没有点击采集、生成、保存、启停、卸载、打卡或删除按钮。

### 永久回归与验收结果

- `server/.venv-asr/Scripts/python.exe tests/test_dashboard_shell.py`：通过。新增断言
  固定公共双栏、禁止 intelligence 再引入单列/隐藏图片例外、保留 sticky 容器，
  并以临时目录验证聚合 panel ID 的自定义头像 PUT/GET/list/DELETE；fake 预览现在
  同时装载六个来源模块，未定义任何业务 API。
- `server/.venv-asr/Scripts/python.exe tests/test_intel_sources_dashboard.py`、
  `tests/test_x_monitor_dashboard.py` 与 `node tests/test_dashboard_briefing_progress.mjs`：
  全部通过，来源配置、X/Nitter 和每日情报公共展示入口未回归。
- 公共 Dashboard JavaScript 全部由 `test_dashboard_shell.py` 逐文件执行
  `node --check` 并通过；另独立复核 `app.js`、`module-loader.js`、`panels.js` 通过。
- Browser skill 的本地只读验收：桌面展开卡为 1060px，网格实测
  `280px + 726px`，图片 280×350、详情 726px；六个 tab、六个 tabpanel 和六个
  fixture 内容全部存在，始终只有一个 panel 可见。默认图片 URL 为本地
  `intel-sources.png`。收起卡为 343×136，`aria-expanded` 正确随操作切换；标题是
  原生 `button[type=button]`，焦点与 ARIA 关系保留。X 标签切换及折叠操作的即时
  请求增量均只有验收端的 `GET /__pk100_audit`，业务 API 计数为 0。
- 375px 移动端展开为单列，图片 260×325 后居中、详情宽 319px；来源标签栏在自身
  317px 可视区域内横向滚动，document `clientWidth === scrollWidth === 375`，
  无页面水平溢出。桌面与移动端截图均人工确认标题、图片和内容未覆盖。
- 遗留问题：无接口冲突或 PK-000 决策项。本增量只待 PK-900 串行集成验收。

### 本轮八项完成文档门禁

- [x] TASK_RECORD — 已记录根因、布局差异、接口、数据副作用、测试结果和遗留项。
- [x] TASKS_BOARD — 本轮按授权只更新 PK-100 任务记录；`TASKS.md` 当前已为
  “待集成”，未触碰共享任务板 hunk。
- [x] PUBLIC_README — 不适用：仅修复既有组件视觉行为，不改变用户操作、启动方式
  或公共接口；且 PK-000 明确冻结本轮 README 共享 hunk。
- [x] MODULE_CATALOG — 不适用：未改变模块元数据、版本、依赖、入口或生命周期。
- [x] ARCHITECTURE_DOCS — 不适用：未改变模块边界、加载顺序或接口契约，只删除
  与公共布局相冲突的 CSS 视觉例外。
- [x] LOCAL_README — 不适用：未改变本机路径、端口、环境或启动命令；8765 仅为
  已关闭的 fake 预览端口。
- [x] AGENT_RULES — 不适用：未改变开发、安全、验证或协作规则。
- [x] VALIDATION — Dashboard/PK-110/115/120 前端专项、JS 语法、fake Browser
  桌面/移动端、请求审计、文档门禁与范围内 `git diff --check` 均已执行；真实数据
  与混合工作区保持隔离。

## 浏览器本地 ZIP 导入界面（2026-08-02）

- “高级 / 离线安装”由占位说明升级为可操作表单：用户填写预期模块 ID、从浏览器
  选择 `.zip`，浏览器用 Web Crypto 在本机计算 SHA-256；文件选择和摘要计算不会
  发出请求，只有启用后的“上传并安装”按钮会调用 PK-010 本机接口。
- 前端只发送原始 ZIP、`Content-Type: application/zip` 和摘要头，不发送客户端
  路径、文件名、任意 URL、GitHub Token 或 Cookie。文件名只用于本页显示和可选的
  模块 ID 建议；Core 仍以包内 manifest 为准。64 MiB 上限在浏览器和 Core 双重检查。
- 安装成功后刷新本机模块列表，但不自动启用、重启或调用模块业务接口；失败只更新
  离线安装状态和通知，原有模块卡、官方目录及动态业务面板保持不变。移动端表单由
  双列降为单列，继续沿用公共主题、焦点和 reduced-motion 契约。
- 专项测试固定控件 ID、`.zip` accept、Web Crypto、同源原始上传、无
  `package_path`/URL 输入、文件名建议安全性和摘要向量；未读取真实模块 registry、
  runtime、个人状态、缓存、凭据或 vendor。
- 实际验证：`test_dashboard_shell.py` 通过；`module-management.js`、`app.js`、
  `module-loader.js`、`panels.js` 均通过 `node --check`；相关 Python 编译、PK-010/
  Catalog 回归、26 项任务文档门禁和 `git diff --check` 均通过。

### 本增量完成文档门禁

- [x] TASK_RECORD — 已记录 UI 流程、请求边界、失败隔离、副作用和验证结果。
- [x] TASKS_BOARD — PK-100 已由“已完成”重新打开并置“待集成”，等待累计复核。
- [x] PUBLIC_README — 已增加本地 ZIP 控制台操作和私有协作者下载后的导入步骤。
- [x] MODULE_CATALOG — 不适用：只消费现有本机/官方模块 ID，不改变目录字段。
- [x] ARCHITECTURE_DOCS — PK-010 安装规范已同步浏览器上传契约。
- [x] LOCAL_README — 不适用：未改变端口、启动器、解释器或本机私有路径。
- [x] AGENT_RULES — 不适用：未改变协作、安全、测试或 Git 规则。
- [x] VALIDATION — Dashboard/PK-010 专项、JS/py_compile、文档和 diff 门禁已执行。

## 本地换包、受控重启与 GPT-SoVITS 目录选择（2026-08-08）

### 界面与接口收口

- 离线 ZIP 的“预期模块 ID”改为可选手工校验。每次选择新包时，自动/默认 ID
  立即清空并显示“将从 manifest 自动识别”；浏览器不再解析 ZIP manifest，也绝不
  从文件名推断安全身份。显式上传调用
  `POST /api/v1/modules/install-upload`，只有用户保留手工 ID 时才附加
  `expected_module_id` 查询参数；Core 始终以已验证包内 manifest 的 `id` 为事实来源。
- 当前 ID 由用户手工填写时，新文件选择会打开原生 `<dialog>`，明确提供“保留手工
  ID / 使用新包自动识别 / 取消换包”。取消后继续保留上一文件的内部引用、摘要和
  手工 ID；若浏览器安全策略不允许恢复文件输入框的可见文件名，状态区会准确说明
  仍保留的包，安装按钮不会指向新包。文件选择、摘要、弹窗及三种选择均零请求。
- 顶部新增受控“重启 Project Kei 服务”，只消费 PK-020 的
  `GET /api/v1/dashboard/service/restart/status` 与
  `POST /api/v1/dashboard/service/restart`；POST 固定为
  `{"confirmation":"restart-project-kei-core"}`。接口未装配或 supervisor 不可用时
  按钮禁用；确认前零写入，确认后防重复提交，并对 accepted/restarting/running/
  failed、短暂断线、90 秒重连超时提供可恢复提示。页面不接收命令、PID、端口或路径，
  不直接 kill、重启或静默控制任何进程。
- Core 健康区新增“GPT-SoVITS 本机引擎”安全入口，仅调用 PK-211 固定的
  `GET /api/v1/gpt-sovits-engine/status` 与用户点击后的空 body
  `POST /api/v1/gpt-sovits-engine/select-existing`。目录选择、取消及验证全部由受控本机
  picker 完成；浏览器不提交 path/URL/command，不显示绝对路径，不扫描、不下载、
  不执行脚本。界面区分取消、选择中、验证失败、`registered_existing` 与
  `unverified_existing_install`；路由未串行挂载时明确显示暂不可用。

### 数据副作用与安全边界

- 普通加载新增的两个读取只限 Core 重启状态与 GPT-SoVITS 引擎登记状态；不会启动
  sidecar、访问 GitHub、读取模型目录或请求未安装业务 API。主题、折叠、换包、弹窗
  和 ZIP 摘要继续只处理浏览器 UI/内存。
- 显式重启仅请求 PK-020 supervisor，显式引擎选择仅唤起 PK-211 本机 picker；两者
  的权限、Origin、loopback、持久化和进程语义仍由各自后端负责。PK-100 没有修改
  `api.py`、router、supervisor、模块 registry/runtime、业务服务或安装包源码。
- Browser 验收使用 fake FastAPI、临时 ZIP 和内存状态；未读取或修改真实模块包、
  registry、runtime/data、引擎目录、模型、来源名单、凭据、缓存或个人状态。临时
  预览进程与两个 ZIP 已在验收后关闭/删除。

### 验证结果与遗留

- `server/.venv-asr/Scripts/python.exe tests/test_dashboard_shell.py`：通过；逐个
  `node --check` 覆盖 14 个 Dashboard ES module，并固定可选 expected ID、零网络
  选择区、受控重启确认、空 body 引擎选择、ARIA、移动端与禁止命令/路径输入。
- `server/.venv-asr/Scripts/python.exe features/voice/providers/gpt_sovits/tests/test_local_selection.py`：
  通过，包含取消、验证、并发、保存失败与同源空 body API 边界。
- Browser skill fake 验收：自动换包后 ID 为空且按钮可用；手工 ID 的保留、清除和
  取消均正确，dialog 初始焦点落在“保留手工 ID”。打开/取消重启确认时 POST 为 0，
  最终确认只产生 1 次 POST 并恢复为“已重启并重新连接”；引擎选择产生 1 次空 body
  POST 并正确显示取消。ZIP 安装和官方目录刷新 POST 均为 0。390px 下
  `scrollWidth=375 <= innerWidth=390`，按钮可见且无水平溢出。
- PK-020 的独立 pytest 文件无法在单一现有解释器直接运行：`.venv-asr` 有 FastAPI
  但没有 pytest，全局解释器有 pytest 但没有 FastAPI；不安装依赖。使用最小装饰器
  兼容方式执行时，后端测试自身的固定命令断言因当前解释器目录包含 `asr` 字样失败，
  这不是 PK-100 前端契约失败，也未越权修改 PK-020 测试，交 PK-020/PK-900 复核。
- 初轮串行审计发现 restart `GET /status` 曾与 POST 共用写 guard；PK-020 随后已将
  status 改为 `_is_local_request`，允许真实 loopback 的无 Origin GET，并补足专项
  回归。PK-100 保留失败降级，实际 supervisor 端到端仍交累计验收。
- 遗留：GPT-SoVITS 固定 Core router 已由 PK-211 串行装配并完成 1.0.1 生产回归；
  PK-900 仍需累计复核 PK-010 + PK-020 + PK-100 + PK-211，并由 PK-000 处理最终
  安装包/发布流程。本任务不自行发布。

### 本轮八项完成文档门禁

- [x] TASK_RECORD — 已记录换包状态机、三项选择、两个串行接口、数据副作用、测试及遗留。
- [x] TASKS_BOARD — 按总控要求不修改共享 `TASKS.md`；本任务文件置“待集成”。
- [x] PUBLIC_README — 不适用：最终安装与用户说明由 PK-000 串行收口，本轮禁止改 README。
- [x] MODULE_CATALOG — 不适用：未改变 manifest/catalog/package 字段，仅消费已冻结接口。
- [x] ARCHITECTURE_DOCS — 不适用：PK-010/020/211 已冻结契约，本轮没有定义第二套架构。
- [x] LOCAL_README — 不适用：未改变真实端口、路径或启动方式；8765 仅为已关闭 fake 预览。
- [x] AGENT_RULES — 不适用：未改变协作、安全、验证或 Git 规则。
- [x] VALIDATION — 已覆盖 Dashboard、PK-211、fake Browser、移动端、请求计数、文档门禁
  与范围内 diff；PK-020 独立环境问题已如实记录并交累计验收。

## README 与生产控制台契约串行收口（2026-08-08）

- README 离线安装流程已改为正式语义：默认由 Core 从已验证 ZIP manifest 自动识别
  模块 ID，“预期模块 ID”只作可选高级核对；连续换包说明覆盖自动清除、保留手工
  ID、改用 manifest 和取消。常用 API 同时记录正式
  `POST /api/v1/modules/install-upload`、可选 `expected_module_id`、legacy
  `POST /api/v1/modules/{module_id}/install-upload` 与维护者本机路径接口。
- 用户说明补齐顶部受控 Core 重启、QQ AppID/Secret 本机表单、ASR 模型目录选择和
  GPT-SoVITS 现有引擎目录选择。Secret 只写本机配置且不回显；浏览器目录操作不传
  path/URL/command、不显示绝对路径、不扫描、不下载、不执行脚本。QQ 保存后按返回
  状态处理：bridge 已运行时由用户在其本机窗口正常关闭，再使用既有单向启动；未
  增加 stop 或静默重启契约。
- `test_dashboard_shell.py` 新增 README 永久契约，固定上述正式/legacy 上传路由、
  无 Origin restart status、精确重启确认、QQ Secret 脱敏及 ASR/GPT 无路径选择文案。
  公共三列小卡、展开大图、动态模块和移动端 CSS/JS 未改。
- 生产源码与实际 ASGI 装配复核：PK-020 的 restart router 使用独立的本机只读/写入
  guard，因此真实 loopback 的无 Origin `GET /restart/status` 返回 200，POST 无
  Origin 被拒绝；精确确认在测试隔离的无 supervisor 环境返回可恢复的 503，未产生
  进程控制。PK-211 1.0.1 已由 `server/api.py` 调用
  `InstalledModuleHost.include_core_routes()` 完成固定 Core 路由装配；实际生产
  `GET /api/v1/gpt-sovits-engine/status` 返回 200，空 body 的显式 POST 在临时登记库
  与取消型 fake picker 下返回 `cancelled`，没有创建登记文件或泄露路径，不再是 404。
- 永久回归新增 `check_production_core_control_contract()`：测试进程先清除 supervisor
  会话，再对实际 `api.app` 验证 restart GET/POST 与 GPT status/select；结束后恢复
  Provider 服务对象。QQ 配置专项 6 项测试通过，Voice runtime 与可安装模块 Dashboard
  回归固定普通 mount/刷新零 POST，只有用户点击保存、ASR 目录选择或 ASR/GPT 启动时
  才各发一次对应 POST。离线 ZIP 的自动识别、保留手工 ID、改用 manifest、取消换包
  三分支继续由 Dashboard 永久测试与既有 fake Browser 请求计数覆盖。
- 本轮没有启动真实 Core、QQ、ASR、GPT-SoVITS 或 supervisor，没有点击真实保存、
  picker、启动、安装或重启，也没有读取 runtime、registry、本机目录、秘密、模型、
  个人状态或缓存。

### 本轮八项完成文档门禁

- [x] TASK_RECORD — 已记录 README 更正、四类用户操作、生产装配及最终复验结果。
- [x] TASKS_BOARD — 按总控要求不修改 `TASKS.md`；PK-100 保持“待集成”。
- [x] PUBLIC_README — 已更新正式/legacy 上传、重启、QQ、ASR 与 GPT-SoVITS 用户说明。
- [x] MODULE_CATALOG — 不适用：未修改 Catalog、manifest、版本或生命周期字段。
- [x] ARCHITECTURE_DOCS — 不适用：只消费 PK-010/020/140/210/211 已冻结契约。
- [x] LOCAL_README — 不适用：未记录、读取或修改任何本机绝对路径或秘密。
- [x] AGENT_RULES — 不适用：未改变协作、安全、验证或 Git 规则。
- [x] VALIDATION — README/Dashboard、实际 Core restart/GPT 装配、QQ 配置、Voice
  runtime/模块面板、PK-010 生命周期、JavaScript 语法、文档门禁与范围内 diff 均已
  执行；全部写入使用临时目录、fake picker 或不可用 supervisor，未触发真实业务副作用。
## 配置就绪情况增加 QQ 启动状态（2026-08-12）

- 用户在 QQ 改为显式手动启动后无法再借助黑框判断进程状态。本轮只在 PK-100 公共“配置就绪情况”中增加 `QQ 服务`状态卡；它读取既有只读 `GET /api/v1/qq-control/status`，严格以 `process_running` 显示`启动`或`未启动`。
- QQ 状态不参与 Core API、ASR、GPT-SoVITS、LLM 的原有就绪分数和总状态计算；未启动不再显示“需要处理”，接口缺失或读取失败也只安全显示`未启动`。页面加载、定时刷新和手动刷新均不调用 QQ start，不写配置、不启动 sidecar、不联网到 QQ。
- `server/static/dashboard/core-status.js` 保持 Core 状态为主请求，并用独立 `Promise.allSettled` 读取 QQ 状态；QQ 读取失败不会让 Core 状态卡整体失败。缓存版本已更新，用户 `Ctrl+F5` 后即可看到第五张状态卡。
- 验证：`node --check server/static/dashboard/core-status.js`、`node --check server/static/dashboard/app.js` 通过；`server/.venv-asr/Scripts/python.exe server/tests/test_dashboard_shell.py` 输出 `dashboard shell tests passed`。当前根 `.venv` 无 pytest、系统 pytest 环境无 FastAPI，未安装或修改依赖。
- 混合工作区中的 PK-020/140/210、个人状态、`server/runtime/`、模型、Voice Pack、`.env` 与 `vendor/` 均未触碰；未执行 Git 暂存、提交、推送或清理。

### 本轮八项文档门禁

- [x] TASK_RECORD — 本节记录展示契约、只读接口、计数隔离和验证证据。
- [x] TASKS_BOARD — 本轮不改变 PK-100 总状态，不抢写 `TASKS.md`。
- [x] PUBLIC_README — 只是状态可见性增量，不新增用户安装或公共接口，README 无需扩写。
- [x] MODULE_CATALOG — 不改变模块包、版本、依赖或 Catalog。
- [x] ARCHITECTURE_DOCS — 不改变架构或数据所有权。
- [x] LOCAL_README — 不改变端口、解释器、本机路径或私有配置。
- [x] AGENT_RULES — 不改变项目协作、安全或测试规则。
- [x] VALIDATION — JavaScript 语法和 dashboard shell 专项如上通过。
## 顶部服务安全关闭入口（2026-08-12）

- “配置就绪情况”现在同时只读加载 QQ 与语音运行时状态；QQ、ASR、GPT-SoVITS
  仅在 `running=true && can_stop=true` 时显示可用的“关闭服务”。
- 关闭必须经过浏览器二次确认，并只调用固定、空 body 的同源 POST；页面不会提交
  PID、端口、路径、命令或环境变量。外部启动的进程只显示“外部启动”，按钮禁用。
- Core 不提供同页关闭按钮：关闭 Core 会立即使当前控制台失联；仍使用受控重启和
  启动窗口中的 Ctrl+C。LLM 为远程配置，不是本机 sidecar 进程。
- 回归覆盖顶部三条固定 stop 路由、所有权门槛、二次确认、JS 语法与现有布局契约。

## 外部进程状态与目录更新提示修正（2026-08-12）

- Core 重启后可能只读探测到仍在运行的 QQ 进程，但当前 Core 不拥有其进程句柄。该场景继续禁止关闭操作，并从灰色禁用按钮改为居中的只读“外部启动”状态胶囊；真正由当前 Core 启动且 `can_stop=true` 的服务仍显示“关闭服务”。
- 服务卡桌面布局固定为“状态图片 / 状态文字 / 操作或状态”三列，移动端降为两列；状态文字和控件均居中对齐，不再掉到卡片左下方。
- 已安装模块在官方目录缓存中不存在更高受信版本时，禁用动作改为明确显示“暂无目录更新”，保留原安全门槛，不把尚未发布的源码候选伪装成可下载更新。
- 验证：`test_dashboard_shell.py` 通过；`core-status.js`、`module-management.js`、`app.js` 均通过 `node --check`；范围内 `git diff --check` 通过。运行中的 Core 已提供新缓存版本，页面只需 `Ctrl+F5`，无需重启服务。

### 本增量八项文档门禁

- [x] TASK_RECORD — 已记录状态语义、布局、目录提示、缓存与验证结果。
- [x] TASKS_BOARD — 不改变 PK-100 状态，不修改共享总板。
- [x] PUBLIC_README — 未改变安装步骤、启动方式或公共接口，无需扩写。
- [x] MODULE_CATALOG — 未伪造或提升官方目录版本；目录发布继续由总控串行完成。
- [x] ARCHITECTURE_DOCS — 未改变进程所有权或模块生命周期契约。
- [x] LOCAL_README — 未涉及本机路径、端口、解释器或秘密。
- [x] AGENT_RULES — 未改变协作、安全、测试或 Git 规则。
- [x] VALIDATION — Dashboard 专项、三项 JS 语法和范围内 diff 均通过。

## ASR/GPT 顶部后台启动控件（2026-08-12）

- “配置就绪情况”中的 ASR 与 GPT-SoVITS 在 voice runtime 返回精确 `ready` 时新增
  “启动服务”，只调用 PK-210 新增的固定 `start-background` 空 POST；不会调用语音
  模块内保留的可见窗口调试 `/start`。运行后复用既有 owned-only“关闭服务”。
- 外部端口实例仍只显示“外部启动”，Core、LLM 和 QQ 的既有状态/控制语义不变；页面
  加载与刷新仍零 POST。按钮使用现有公共卡片布局、键盘可访问原生 button 和通知样式。
- fake DOM 回归真实点击 ASR 顶部按钮，断言仅一次 background POST、调试路由零请求；
  随后刷新为 owned/running 并断言关闭只请求一次固定 stop。Dashboard shell 专项通过。

### 本增量八项文档门禁

- [x] TASK_RECORD — 已记录顶部/底部入口分层、请求副作用和测试结果。
- [x] TASKS_BOARD — PK-100 保持待集成，不修改共享总板。
- [x] PUBLIC_README — 已同步顶部后台日常启动、底部可见窗口调试启动和关闭所有权说明。
- [x] MODULE_CATALOG — 公共 UI 不改 Catalog；voice 1.0.9 元数据归 PK-210。
- [x] ARCHITECTURE_DOCS — 未改变固定本机进程所有权与 loopback/Origin 安全契约。
- [x] LOCAL_README — 不记录本机路径、模型、进程或秘密。
- [x] AGENT_RULES — 不改变协作、安全、测试或 Git 规则。
- [x] VALIDATION — Dashboard fake DOM、JS 语法及 voice 跨模块专项已执行。
## Core 服务卡可读性修复（2026-08-12）

- 根因是配置就绪区域在约 740px 内容宽度中强制排成三列，而服务卡内部又采用
  “58px 状态图 / 文本 / 操作”三列，ASR 与 GPT-SoVITS 的中文标题、说明和按钮
  被挤压成近似竖排。此次仅修改 PK-100 公共服务卡布局，不改变任何状态判断、
  启动/关闭路由、进程所有权或确认流程。
- `#services` 桌面端固定为两列；卡内改为“头像 + 标题/状态/说明”两列，操作按钮
  独占底部操作行并右对齐。421–760px 与不超过 420px 时服务区改为单列，最窄屏
  按钮横向铺满，避免文字、图片和按钮互相覆盖或产生页面横向溢出。
- 实际本地控制台以 1280px 视口复核：服务区计算结果为 `356px + 356px`，页面
  `clientWidth === scrollWidth === 1265`；API、ASR、GPT-SoVITS、LLM 的标题与
  状态均保持横向可读，启动按钮位于对应卡片右下方。
- 验证：`test_dashboard_shell.py`、`node --check core-status.js`、28 项任务文档门禁
  与范围内 `git diff --check` 均通过。未启动或关闭真实服务，未访问个人状态、
  runtime、模型、Voice Pack、`.env` 或 vendor，也未执行 Git 发布操作。

## 官方安装恢复与批量模式（2026-08-19）

### 根因、界面与公共契约

- 根因是 `runOfficialOperation()` 在成功后把官方目录状态停在 `success`，而单项
  安装按钮只接受 `cache_ready|failed`；同时成功路径只重读本机 registry，没有重读
  `GET /api/v1/modules/official-catalog` 的本机缓存投影，导致已安装卡仍留在可安装区。
- 单项安装现在成功后依次只读重载本机 registry 与官方目录缓存，并保留成功文案；
  二次读取任一失败会显示明确警告，`finally` 仍保证状态离开 confirming/downloading/
  installing/success 阻塞态。失败态继续允许刷新或安装其他模块，不会把旧模块面板清空。
- “可安装模块”新增默认关闭的“批量选择”。开启后才显示兼容、未安装且声明
  `install_official` 的复选框、已选计数、全选兼容项、取消和安装已选；所有选择操作
  只变更内存 DOM，不写 localStorage，不发 API。
- 总确认使用原生 `dialog`，列出确定性安装顺序、模块与版本、固定官方来源、合计大小、
  必需依赖和权限；初始焦点落在确认按钮，取消按钮与 Escape 均可关闭，确认前零 POST。
  移动端工具栏降为单列，复选框保持 40px 可操作区且页面无水平溢出。

### 依赖计划、执行与数据副作用

- `buildOfficialBatchPlan()` 仅使用已读取的 Catalog/registry 快照：已安装依赖视为满足，
  所选依赖按 module_id 稳定拓扑排序；缺失、循环、不兼容、过期选择或同模块多版本均在
  任何 POST 前 fail closed，可选依赖不参与阻断。
- 用户确认后由 `runOfficialBatchQueue()` 以 `for` + `await` 严格串行复用现有
  `POST /api/v1/modules/{module_id}/install-official`，请求体仍为既有
  `{version, confirmation:"module_id@version"}`。没有 Promise.all、批量后端接口、自动
  启用、自动重启、业务 API 或浏览器直连 GitHub。
- 任一项失败立即停止：报告已完成、失败和未执行，保留已成功模块且不回滚；随后仍只读
  重载本机 registry/Catalog，清除已完成选择并保留可重试项。全部成功则退出批量模式并
  恢复其他安装按钮。fake Browser 中顺序为 `conversation` 后
  `affection_memory`，随后两次本机 GET；确认前安装 POST 为 0。
- 测试与 Browser 均只使用内存状态、临时/fake API；没有访问 GitHub、真实 registry、
  runtime、个人数据、缓存、凭据、模型或 vendor，也没有安装真实模块。

### 验证结果与遗留

- `node --check server/static/dashboard/module-management.js`：通过。
- `check_html_contract()` + `check_javascript_contract()`：通过；纯 JS 回归覆盖默认隐藏、
  安装成功恢复、二次目录失败恢复、已安装依赖、稳定排序、缺失/循环/不兼容零 POST、
  最大并发 1、第二项失败停止及剩余队列报告。
- Browser skill fake 验收：开启批量选择后 10 个候选复选框可见，选择/总确认前安装
  POST 为 0；确认文案显示 2 项、4.0 KiB、依赖与权限；实际 fake POST 严格按依赖顺序
  两次执行，随后 registry/Catalog 各 GET 一次，卡片移除、状态回到 `cache_ready`、其他
  安装按钮可用。单项安装后同样移除卡片并可继续安装。375px 视口
  `clientWidth === scrollWidth === 375`，工具栏宽 291px，复选框均在视口内；确认按钮
  自动聚焦且 Escape 关闭。
- 完整 `test_dashboard_shell.py` 当前在进入本增量检查前，被共享工作区中 PK-230 新增但
  尚未同步到该测试清单的 `learning` manifest 数量断言阻断；未覆盖或代替 PK-230 hunk，
  已单独执行本增量的 HTML/JS 专项。PK-900 应在 PK-230 清单收口后重跑完整文件。
- PK-100 保持“待集成”，由 PK-000/PK-900 串行复核；不修改 `TASKS.md`、README、
  PK-010 后端或 PK-241 路径，不自行暂存、提交、推送或发布。

### 本增量八项完成文档门禁

- [x] TASK_RECORD — 已记录根因、单项恢复、批量状态机、依赖计划、数据副作用和验证。
- [x] TASKS_BOARD — 按授权不修改共享 `TASKS.md`；PK-100 任务文件保持“待集成”。
- [x] PUBLIC_README — 不适用：本轮总控冻结 README，且未增加端点或改变安装语义。
- [x] MODULE_CATALOG — 不适用：只消费现有 Catalog 字段和单包接口，不改目录元数据。
- [x] ARCHITECTURE_DOCS — 不适用：批量仅为前端串行编排，PK-010 单包边界不变。
- [x] LOCAL_README — 不适用：未改变或读取本机路径、端口、解释器、模型或秘密。
- [x] AGENT_RULES — 不适用：未改变协作、安全、测试、文档或 Git 规则。
- [x] VALIDATION — 已记录 JS、专项 fake、Browser、移动端、请求审计、文档门禁与 diff；
  完整 Dashboard 清单的共享 PK-230 阻断如实保留待串行收口。

## 官方目录与本机版本可靠归并（2026-08-20）

### 接口与界面契约

- 官方卡不再把 Catalog 投影中的 `installed_version` 当作唯一事实源；前端用官方条目的
  `module_id` 精确关联 `GET /api/v1/modules` registry 项，再用与 Core
  `compare_semver()` 一致的受控 SemVer 规则比较版本。非法版本、未知本机目录或非受信
  `songshu-yu/Project-Kei-Modules` 来源均 fail closed。
- 未安装模块只对同一 `module_id` 的最高兼容受信版本显示“下载并安装”；同版本显示
  “已安装”并禁用按钮；本机较旧且 registry 明确允许 `update_official` 时，仅最高合法
  目标显示“下载并更新”；本机较新显示“本机版本较新”。不兼容版本、多版本中的非目标
  版本和本机非 `official_github_release` 来源均显示明确只读状态，不进入批量候选。
- 更新继续唯一复用
  `POST /api/v1/modules/{module_id}/update-official` 与既有
  `{version, confirmation:"module_id@version"}` 确认体；没有新增更新逻辑、任意 URL、
  浏览器下载、自动回滚、自动启用或自动重启。批量模式仍只包含未安装的 install 项。
- 单项安装/更新成功后仍只读重载 registry 与官方 Catalog 本机缓存；并发初始 GET
  无论完成顺序如何，registry 到达后都会重新渲染版本状态。二次 GET 失败继续由既有恢复
  路径解除 busy，保留成功/警告文案和其他可操作按钮。

### 数据副作用、测试与遗留

- 页面加载、版本比较、批量开关和选择只读取本机 Core 数据并修改内存 DOM，零 POST、
  零 GitHub 网络、零浏览器持久化；只有用户在二次确认后才发送单次 install/update POST。
- `node --check server/static/dashboard/module-management.js` 与 Python 语法检查通过；
  `check_html_contract()`、`check_javascript_contract()` 通过。纯 JS 回归覆盖 SemVer
  预发布/构建元数据、非法版本、未安装、同版本、可更新、本机较新、不兼容、非官方来源、
  多官方版本唯一目标、批量排除已安装项，以及唯一冻结 update 请求路径和请求体。
- Browser skill 仅连接内存 fake 控制台：同版本卡显示禁用“已安装”；显式安装
  `conversation@1.0.0` 后卡片立即收敛为“已安装”，另一安装按钮保持可用；批量模式排除
  已安装项。375px 视口 `clientWidth === scrollWidth === 375`，官方卡单列 291px，无横向
  溢出。未刷新官方目录、未访问 GitHub、未安装真实模块。
- 完整 `test_dashboard_shell.py` 仍在本增量执行前被共享 PK-230 新增 `learning` manifest
  与旧清单数量断言阻断；该共享 hunk 未在 PK-100 越权修改，交 PK-900 串行收口后重跑。
  PK-100 状态保持“待集成”。

### 本增量八项完成文档门禁

- [x] TASK_RECORD — 本节记录归并主键、SemVer、来源门槛、动作、副作用和验证。
- [x] TASKS_BOARD — 按授权不修改混合 `TASKS.md`；任务文件保持“待集成”。
- [x] PUBLIC_README — 不适用：未新增用户端点或改变安装步骤，且 README 属共享冻结路径。
- [x] MODULE_CATALOG — 不适用：只消费 PK-010 已冻结字段，不修改或伪造官方目录。
- [x] ARCHITECTURE_DOCS — 不适用：前端归并不改变模块生命周期或数据所有权。
- [x] LOCAL_README — 不适用：未改变或读取本机路径、端口、registry、runtime 或秘密。
- [x] AGENT_RULES — 不适用：未改变协作、安全、文档、测试或 Git 规则。
- [x] VALIDATION — JS/Python 语法、专项 JS、fake Browser、移动端和范围 diff 已验证；
  完整测试的 PK-230 清单阻断已如实记录。

## PK-900 P1 退回整改：严格身份与任意精度 SemVer（2026-08-20）

### 退回根因与最小修复

- PK-900 独立验收确认首轮归并仍通过公共 `moduleId()` 的 `key || module_id` 兼容逻辑
  建立 registry 索引，导致 `key` 与 `module_id` 交叉时误判安装状态。本轮保留旧 UI 对
  `key` 的展示/生命周期兼容，但官方归并新增独立严格身份路径：只接受原值精确匹配
  `^[a-z][a-z0-9_]{0,63}$` 的非空 registry `module_id`，不回退 key、name、label 或文件名。
- registry 中同一合法 `module_id` 的任意重复记录均标记为
  `registry_conflict`，官方卡显示“本机 registry 身份冲突，拒绝操作”；不会用第一条或
  最后一条决定安装/更新。空或非法 `module_id` 不会借助 `key` 关联任何官方模块。
- 首轮 SemVer 将数字段转成 JavaScript `Number`，在超过安全整数范围后与 Core 的 Python
  任意精度整数失配。本轮主/次/补丁和纯数字 prerelease 标识符全部使用 `BigInt` 比较；
  不支持 BigInt 的运行环境直接报错并 fail closed，不存在 Number/parseInt 降级。合法性、
  前导零、release 高于 prerelease、数字标识符低于字符串标识符、字符串字典序和 build
  metadata 不参与优先级均继续与 Core `compare_semver()` 一致。

### 永久回归、数据副作用与结果

- 新增逆向固定：官方 `alpha` + 本机 `key=wrong,module_id=alpha` 必须为 installed；本机
  `key=alpha,module_id=beta` 必须让官方 alpha 保持 install；空 module_id + key=alpha
  不得关联；两个 alpha registry 记录必须为 registry_conflict。
- 新增大整数正反序固定：`9007199254740992.0.0 < 9007199254740993.0.0` 及反序，
  `1.0.0-9007199254740992 < 1.0.0-9007199254740993` 及反序；同时保留普通
  prerelease/build、非法版本、完整状态矩阵、唯一 update POST、批量只含 install、成功后
  registry/Catalog 双 GET 与失败恢复回归。
- `node --check`、Python `py_compile`、`check_html_contract()`、
  `check_javascript_contract()` 均通过。Browser skill 仅连接 fake FastAPI：同版本官方卡
  禁用、未安装卡可用、批量候选排除已安装项；375px 下
  `clientWidth === scrollWidth === 375`。页面读取与比较没有 GitHub、真实 registry/runtime、
  个人数据、秘密或真实模块副作用。
- 完整 Dashboard 文件仍预期在共享 PK-230 `learning` manifest 21/20 清单处停止；本轮未
  修改该清单、PK-230、Core、API、Catalog、README 或 TASKS。PK-100 保持“待集成”，交同一
  PK-900 复验。

### 本次整改八项完成文档门禁

- [x] TASK_RECORD — 已记录 PK-900 退回证据、根因、严格身份、BigInt 与实际验证。
- [x] TASKS_BOARD — PK-000 最终复核后已同步 `TASKS.md` 为“已完成”。
- [x] PUBLIC_README — 不适用：未改变用户安装步骤、公共端点或界面操作流程。
- [x] MODULE_CATALOG — 不适用：未修改目录内容、来源、版本或发布元数据。
- [x] ARCHITECTURE_DOCS — 不适用：只修复前端读取归并，不改变生命周期或数据所有权。
- [x] LOCAL_README — 不适用：未读取或记录本机 registry、runtime、路径、状态或秘密。
- [x] AGENT_RULES — 不适用：未改变协作、安全、测试、文档或 Git 规则。
- [x] VALIDATION — 精确身份和大整数逆向、JS/Python、Browser、文档与 scoped diff 均执行。

## PK-900 第二次退回收口：冲突确定性与生产同形 Browser 夹具（2026-08-20）

- 第二次复验确认严格 `module_id` 与 BigInt 两项已关闭，但重复 ID 的归并仍把输入第一条
  记录放入 `local_module`，使冲突卡的本机版本随排列变化。本轮在任何版本、来源和动作
  计算前将冲突 ID 的本机候选固定为 `null`；公开结果只保留稳定的
  `registry_conflict` 与“本机 registry 身份冲突，拒绝操作”，不泄漏任一候选的 key、
  version、label、来源或其他字段。
- 永久逆向使用两条同为 alpha、但 key、version、label、来源均不同的记录，正反顺序的
  完整归并结果必须 `JSON.stringify` 全等、`local_module === null`、状态为
  `registry_conflict`；两个顺序均不能产生 install/update，批量计划均在零请求前以
  `batch_selection_stale` 拒绝。单条严格合法记录及既有身份/版本矩阵继续通过。
- Browser preview 的 `_module_record()` 已补齐生产 `ModuleManager._describe()` 同形的
  `module_id`，没有让产品回退 `key`。实际 fake 页面确认 bilibili 同版卡显示“已安装”且
  按钮禁用，conversation 未安装卡可操作；批量候选中 bilibili 数量为 0。总确认 dialog
  具有 `aria-labelledby`/`aria-describedby` 且确认按钮获得焦点，Escape 关闭；375px
  `clientWidth === scrollWidth === 375`。fake audit 在页面加载、展开、批量选择与取消后
  `POST=0`，只发生 registry/Catalog 各一次本机 GET。
- 本轮只修改 PK-100 三个授权文件，不改变 Core/API/Catalog、PK-230、README 或 TASKS；
  未读取真实 registry/runtime、业务数据、秘密或访问 GitHub。任务继续“待集成”，交同一
  PK-900 再次聚焦复验。

### 本次收口八项完成文档门禁

- [x] TASK_RECORD — 已记录第二次退回、确定性冲突结果、生产同形夹具和实际 Browser 证据。
- [x] TASKS_BOARD — 不修改共享 `TASKS.md`；PK-100 继续“待集成”。
- [x] PUBLIC_README — 不适用：未改变用户操作、端点或安装说明。
- [x] MODULE_CATALOG — 不适用：未访问远端或修改目录内容与版本。
- [x] ARCHITECTURE_DOCS — 不适用：未改变 registry 或生命周期契约。
- [x] LOCAL_README — 不适用：未读取或记录本机私有状态、路径或秘密。
- [x] AGENT_RULES — 不适用：未改变项目协作、安全、测试或 Git 规则。
- [x] VALIDATION — 正反深度等价、零动作、JS/Python、Browser、docs30 与 scoped diff 已执行。

## PK-000 最终关闭（2026-08-20）

- PK-900 对第二次最小收口完成独立聚焦复验并判定通过：重复 `module_id` 冲突的正反输入公开结果完全相等、`local_module=null` 且不泄露候选字段；严格身份、超大整数 BigInt SemVer、状态矩阵、唯一 `update-official`、批量 install-only、双 GET 恢复与 375px Browser fake 均通过。
- PK-000 重新核对正式报告与实际差异，并独立运行 `check_html_contract()`、`check_javascript_contract()`，结果通过；文档门禁与范围 `git diff --check` 继续通过。共享 PK-230 `learning` manifest 21/20 冲突保持独立，不作为 PK-100 阻断，也未由本任务越权修改。
- PK-100 本轮累计增量正式关闭为“已完成”，并同步 `TASKS.md`。PK-900 因仍承载其他开放批次继续保持“进行中”；本结论不授权 Git 提交、推送、发布或工作区清理。

### 最终关闭八项完成文档门禁

- [x] TASK_RECORD — 已记录两次退回、独立复验与总控最终结论。
- [x] TASKS_BOARD — 已由 PK-000 同步为“已完成”。
- [x] PUBLIC_README — 不适用：本次收口未改变用户操作或公共端点。
- [x] MODULE_CATALOG — 不适用：未修改官方目录内容或发布元数据。
- [x] ARCHITECTURE_DOCS — 不适用：未改变 registry、生命周期或数据所有权契约。
- [x] LOCAL_README — 不适用：未记录本机路径、registry、runtime、状态或秘密。
- [x] AGENT_RULES — 不适用：未改变协作与安全规则。
- [x] VALIDATION — PK-900 聚焦复验、总控 HTML/JS 契约、docs30 与范围 diff-check 均通过。

## 官方模块下载来源与镜像故障恢复（2026-08-26）

- 测试人员在批量安装时遇到 GitHub Release 资产下载失败。模块中心新增固定来源选择：
  “自动（推荐）”“仅 GitHub”“仅 Gitee”。选择仅保存在浏览器 `localStorage`，加载、
  切换、展开和批量勾选均零网络、零生命周期 POST。
- 刷新目录、单项安装、更新和批量安装均把有限枚举 `download_source` 交给 PK-010；
  不接受任意 URL、仓库、Token、Cookie、代理或路径。确认对话框显示实际选择，结果
  显示服务端最终使用的镜像；Gitee 限流与下载错误使用有限、可操作提示。
- 自动模式的具体回退规则完全由 PK-010 服务端执行。前端不能对摘要/manifest 失败
  自行重试另一来源，也不会改变既有批量拓扑、严格串行、失败即停和成功后 registry/
  Catalog 双 GET 恢复语义。
- 永久静态/Browser 契约覆盖来源控件、默认 auto、刷新/安装请求体、切换零请求、批量
  复用同一来源和窄屏无溢出。任务重新进入“待集成”，等待双镜像实际发布和累计验收。

### 本增量完成文档门禁

- [x] TASK_RECORD — 已记录用户故障、界面行为、接口边界、零网络语义和测试。
- [x] TASKS_BOARD — 已把本轮重新打开的 PK-100 同步为“待集成”。
- [x] PUBLIC_README — 已同步自动/GitHub/Gitee 的用户操作与安全边界。
- [x] MODULE_CATALOG — 不适用：前端只消费固定目录，不修改包版本或摘要。
- [x] ARCHITECTURE_DOCS — 已由 PK-010 规范同步双镜像和回退分类。
- [x] LOCAL_README — 不适用：来源偏好仅在浏览器保存，不涉及本机私密路径或配置。
- [x] AGENT_RULES — 不适用：未改变协作、安全、测试或 Git 规则。
- [x] VALIDATION — HTML/JS、Catalog fake、Dashboard 契约、移动端及 diff 门禁已执行。
