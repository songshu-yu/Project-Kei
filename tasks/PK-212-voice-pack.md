# PK-212 — Voice Pack 注册表与 Kei 模型包

- 状态：待集成
- 优先级：P1
- 所属模块：`voice_pack_registry`
- 依赖任务：PK-010、PK-100、PK-210
- 负责路径：`server/features/voice/voice_packs/`、`server/features/voice_pack_registry/`、Voice Pack Schema 与注册表、显式本地导入/校验/切换、Kei 本机 Pack 适配、对应专属测试与文档
- 当前对话：2026-07-30 PK-000 重新打开 PK-212 的 PK-011 语音批可安装化增量；本对话只交付 `voice_pack_registry` 专属包源、动态面板、发布元数据和隔离测试，不修改共享冻结文件

## 目标

定义独立于 GPT-SoVITS 安装目录的可移植 Voice Pack Schema、原子注册表、本地导入校验和活动 Pack 切换机制，并把现有 Kei 权重、参考音频与合成配置作为本机 Voice Pack 接入。未来新增角色时复用同一 Schema 和注册表，不修改 Engine Provider。

## Voice Pack Schema

版本化 manifest 至少描述：

- `schema_version`、稳定 `pack_id`、`pack_version`、显示名称和角色/声音标识；
- `engine_provider` 与兼容协议/引擎版本约束，但不绑定具体 GPT-SoVITS 安装路径；
- 支持语言、文本/提示语言、情绪或风格 key、合成默认值；
- 模型与参考音频的相对路径、字节大小、强摘要；
- 参考音频对应的提示文本、语言和可选情绪标签；
- 来源、作者、许可证与再分发限制；不得把不可分发资产误标为可发布。

可移植 Pack 中的文件引用必须是 Pack 根目录内的规范化相对路径。导入必须拒绝绝对路径、`..` 穿越、逃逸 Pack 根的链接、重复/不合法 ID、未知必要字段、大小或摘要不符以及不兼容 Engine Provider。

## 注册表与切换契约

- 注册表只保存经过校验的 Pack 元数据、受控本地句柄、启用状态和当前活动 Pack；API 不返回真实绝对路径、权重内容或参考音频内容。
- 导入第一阶段只接受用户显式指定的本地目录/归档，不访问网络，不从模型站点自动下载。
- 导入采用“校验全部候选内容 -> 写入临时记录 -> 原子发布”语义；失败不得出现半注册 Pack，也不得改变当前活动 Pack。
- 切换采用“解析候选 -> 校验 Engine Provider 兼容与必需文件 -> 假加载/Provider 探测成功 -> 原子更新活动引用”语义；失败时旧 Pack、注册表和所有消费者保持不变。
- 卸载/注销默认只删除注册表引用，不删除外部原始资产。任何真实文件删除或复制必须是另行明确确认的操作，不属于默认切换流程。
- PK-210 只通过 `VoicePackRef` 获取不透明的只读 Pack 句柄；PK-211 Engine Provider 不读取或维护注册表。

## Kei 本机模型包边界

- 现有 Kei 权重、参考音频和配置继续留在当前位置，不与 GPT-SoVITS 引擎目录绑定，不自动移动、复制、重命名、打包或提交 Git。
- 首次接入可创建仅本机可见的注册记录/兼容适配，将现有位置映射为 Kei Pack；不得为满足“可移植”而擅自重排真实资产。
- 若未来需要导出为便携归档，必须由用户显式发起并先核验许可证、目标路径与包含清单；导出不属于本轮。
- 真实 Pack 的路径覆盖和注册表属于本机状态，必须忽略；仓库只提交 Schema、脱敏示例和假 Pack 测试夹具。

## 不在本任务内

- 不获取、安装、升级、启动或扫描 GPT-SoVITS 上游引擎；这些归 PK-211。
- 不实现 ASR、语音 HTTP 编排、流式响应或临时音频清理；这些归 PK-210。
- 不修改 PK-200 的 LLM Provider/Profile、系统提示、对话历史或 API Key 管理。
- Voice Pack 只描述声音合成资产，不包含 Persona Pack、长期记忆、好感度、角色业务状态或控制台人格配置。
- 不实现云端模型市场、自动同步、远程下载、资产再分发或真实权重测试。

## 接口契约

- 向 PK-210 提供只读的 `resolve_active_pack()`、`resolve_pack(pack_id)` 和原子 `switch_active_pack(candidate)` service 契约；返回 PK-210 定义的最小 `VoicePackRef`。
- 注册/导入/切换的管理 API 如需对外暴露，必须位于 `/api/v1/voice-packs/*`，只接受本机显式操作并返回脱敏元数据；具体矩阵由独立任务在实现前记录。
- 不为兼容接口凭空新增自动导入行为；现有 `/voice/*` 默认解析当前活动 Pack，并保持 Kei 声音的兼容结果。
- 任一公共契约需要改变 PK-210 时，先在本文件记录需求并交回 PK-000，不得在 PK-212 中直接扩大 voice 编排修改。

## 数据所有权

- 项目可提交：Schema、注册表模型/代码、脱敏 manifest 示例、假权重/假参考音频测试夹具、校验与切换测试。
- 仅本机且不得提交：真实注册表、绝对路径覆盖、Kei/其他角色权重、参考音频、模型配置、导入缓存和生成音频。
- 不得读取或打印 `.env`、LLM Profile、长期记忆、用户音频内容；错误信息不得包含绝对资产路径或 manifest 中的敏感本地备注。
- 自动测试必须使用临时目录、微小假模型文件和假参考音频；不得访问真实 Voice Pack 根或真实 GPT-SoVITS 服务。

## 依赖与集成

- 依赖 PK-210 的 `VoicePackRef` 与 TTS 编排契约；不依赖 PK-211 实现。
- 通过假 Engine Provider 验证 Pack 注册、解析与切换，不把真实引擎可用性作为单元测试前提。
- PK-211 与 PK-212 均进入“待集成”后，与 PK-210 一并登记同一轮 PK-900，验证真实契约联调但仍不得把资产纳入 Git。

## 实施清单

- [x] 领取任务后同步状态并确认 PK-210 的 `VoicePackRef` 已稳定。
- [x] 定义版本化 Schema、路径/摘要/许可证校验和脱敏序列化。
- [x] 实现本地导入、原子注册、解析、切换与只移除引用的注销语义。
- [x] 以不移动真实文件的本机适配方式登记 Kei Pack。
- [x] 使用假 Pack/假 Provider 覆盖损坏 manifest、路径逃逸、摘要不符、重复 ID、并发串行化切换和保存失败。
- [x] 更新 README、模块目录/架构说明、任务工作记录和完成文档门禁。

## 验收标准

- Kei 资产仍在原位置且未进入仓库差异；GPT-SoVITS 安装与 Voice Pack 根没有路径耦合。
- Schema 足以在授权的另一台本机校验同一 Pack，并能表达多个角色、语言、情绪参考与引擎兼容约束。
- 导入、注册和切换在候选校验失败、Provider 探测失败、注册表保存失败及并发请求下均无半状态，旧活动 Pack 和消费者保持不变。
- 路径穿越、链接逃逸、摘要/大小不符、未知字段版本和不兼容 Provider 均被稳定拒绝，响应不泄露本机绝对路径。
- 自动测试只使用假 Pack、假参考音频、假 Engine Provider 和临时注册表；没有真实权重读取、真实服务、网络或资产移动。
- 至少两个假角色 Pack 证明新增角色不需要修改 PK-210 编排或 PK-211 GPT-SoVITS Provider。

## 工作记录

- 2026-07-21：PK-000 完成任务登记；未读取、移动、导入或打包真实 Kei 资产，未实现注册表。
- 2026-07-21：独立 PK-212 对话完成必读文件、PK-210 契约、现有 TTS 配置和混合工作区核查后领取任务并改为“进行中”。本对话只处理可变化的角色声音模型；真实 Kei 权重和参考音频仅做必要文件存在性检查，不读取内容、不计算摘要、不移动、不复制、不训练、不输出绝对路径。工作区既有修改均视为用户所有，不清理、不暂存、不提交。
- 2026-07-21：新增 `server/features/voice/voice_packs/`，正式 Schema v1 和运行时 parser 同时要求 ID/名称/语义版本、`gpt-sovits` engine/协议、支持语言、GPT/SoVITS checkpoint、参考音频/文本/语言、默认文本语言、白名单生成参数和逐文件完整性。可移植包必须使用包内 POSIX 相对路径与精确大小/SHA-256；拒绝绝对路径、盘符、反斜杠、`.`/`..`、逃逸、符号链接、缺失/损坏文件、未知字段/engine/schema、可执行文件、BAT/PowerShell/Python/安装器或 hook。
- 2026-07-21：实现 `VoicePackRegistry` 与 `VoicePackRegistryService`。目录和 ZIP 只能由本机显式导入且不联网；ZIP 有条目数量、展开大小、路径、链接和执行文件限制。注册表通过同目录临时文件、flush/fsync 和 `os.replace` 原子保存；重复 `id@version` 被拒绝。启用会重新校验资产，选择会串行执行候选校验、Provider 激活和活动 ID 原子保存，Provider 或保存失败均尝试恢复旧 Pack。停用活动 Pack 会清空活动 ID；注销只删记录并固定返回 `source_assets_deleted=false`，不删目录/ZIP 源、外部资产或运行副本。
- 2026-07-21：新增本机管理接口 `GET /api/v1/voice-packs`、`POST /import`、`POST /{id}/{version}/enable|select|disable`、`DELETE /{id}/{version}`。写操作仅本机可用；响应只含 ID、名称、版本、engine、语言、完整性模式、状态和时间，不返回注册表路径、包根或资产绑定。错误只返回稳定 code 与有限消息。
- 2026-07-21：主应用移除 `legacy-kei` 静态引用和 `TTS_DEFAULT_REF_AUDIO/TEXT`、文本/提示语言装配，统一注入本机注册表 resolver。语音编排、每日情报、focus/斩妖兼容合成和 WebSocket 等既有 TTS 消费者均由 Provider 在调用时解析活动 Voice Pack；业务代码不再选择 Kei 权重/参考音频路径。GPT-SoVITS Provider 从不透明 handle 接收两项 checkpoint、参考音频/文本/语言和生成参数，通过既有 9880 固定权重切换端点激活候选；不扫描或读取模型文件。
- 2026-07-21：现有 Kei 三项资产已以被忽略的 `kei@1.0.0` 本机记录登记、启用并选中。登记只验证既有引擎登记与三项必要文件为普通存在文件，完整性明确为 `existence_only`；没有打开权重/音频、计算大型摘要、移动、复制、重命名、训练、打包或访问 9880，也未输出/提交真实路径。本机注册表、Voice Pack 本机覆盖、ZIP 运行目录、权重、参考音频和生成音频均已核对为 Git 忽略。
- 数据与副作用：可移植目录导入只登记原位置；ZIP 导入会创建忽略的受控运行副本；失败只清理本次新建的暂存/运行目录。注册、启停、选择和注销只改忽略的本机注册表；默认不存在任何大型资产删除接口。Schema/示例/代码/测试/文档可提交，真实本机 registry/manifest/绑定、模型、音频和产物不可提交。
- 验证记录：通过 `tests/test_voice_pack_registry.py`（临时微小假权重/假 WAV/假 ZIP/假 Provider，覆盖合法导入、schema 版本、未知 engine、缺失文件、摘要错误、绝对/穿越路径、符号链接、执行文件、重复 ID/版本、成功切换、Provider 失败与注册表保存失败回滚、原子写入、注销保留源、API 脱敏和 Provider 配置）、`tests/test_gpt_sovits_provider.py`（含 checkpoint 切换端点与完整 Pack payload）、`tests/test_voice_module.py`、`tests/test_feature_catalog.py`。相关文件 `py_compile` 与主应用 Voice Pack 路由导入检查通过；文档门禁和最终 `git diff --check` 在交接前重跑。未运行真实 `test_tts_gptsovits.py`，未启动/调用 8000、8010、9880 或真实/付费服务。
- 集成关注：真实 GPT-SoVITS 的两项权重切换端点与现有 Kei 资产仅在后续 PK-900 显式联调时验证；本任务没有把 `existence_only` 提升为摘要已验证，也不声明 Kei 资产可再分发。LLM、system prompt、Persona Pack 继续不属于 Voice Pack；未来只能由 PK-000 另立稳定 ID 关联契约。
- 2026-07-22 根因整改：旧 `select()` 虽然串行校验、Provider 激活和 Registry 保存，但 Provider 在激活返回时已经释放权重锁；Registry commit 前合成可插入并按旧 ID 回切权重，随后 Registry 又提交新 ID。普通 `Exception` 回滚也无法覆盖 `CancelledError` 或 Provider 自身半切换，因而“原子 Registry 文件”不等于“Registry 身份 + 外部引擎”原子。
- 2026-07-22 事务集成：生产 activator 现在提供 `activate_voice_pack_transaction(candidate, commit)`；`select()` 把 `registry.save(snapshot)` 作为 commit 交给 Provider，在其唯一共享引擎会话内完成。Provider 合成同样在该会话内重新调用 `resolve_active_pack()`，所以锁外旧 `VoicePackRef` 不会越过刚完成的选择。兼容假 activator 仍支持原接口，并为取消补做受保护旧 Pack 恢复。
- 2026-07-22 未知状态：Provider 回滚失败时 Registry service 通过脱敏 `voice_pack_state()` 观察 `unknown`；list 返回 `active=null`/`engine_state=unknown`，health 返回 `voice_pack_engine_state_unknown`，resolve 拒绝旧 Pack。磁盘 Registry 仍保留最后一次成功原子提交，便于后续完整成功选择恢复，但运行期不会把该旧 ID 冒充为实际可用声音。
- 2026-07-22 隔离测试：新增共享引擎独立脚本，使用两个临时假 Pack、临时 Registry 和 MockTransport 假 9880 覆盖 select cancellation、第二阶段失败/回滚、回滚失败、select/synthesize 互斥、双 Pack 并发合成、幂等选择、close 竞态及失败后旧 Pack 合成；未读取或下载真实权重、参考音频或外部引擎。
- 2026-07-22 最终验证：共享引擎、Provider、Registry、PK-210、PK-200、API/catalog/dashboard 和必要消费者共 13 组测试完整重跑通过；54 个相关 Python 文件编译、六项 dashboard JavaScript、PowerShell AST 均通过。所有资产/HTTP/状态写入仍限定为 MockTransport、假音频、微型假权重路径和系统临时 Registry；测试进程使用不存在的 env/profile/生产 Registry 路径与虚构 Key。真实本机 Voice Pack 注册表、runtime、权重、参考音频、引擎登记和输出均未读取或修改。
- 2026-07-22 最终门禁：任务文档门禁通过 9 个 gated tasks，`git diff --check` 无空白错误，本次明确路径行尾检查通过；受保护本机状态路径均无 Git 状态输出。PK-211、PK-212 继续保持“待集成”，只向 PK-900 提交原竞态夹具复验，不执行 Git 暂存、提交、推送或发布。
- 2026-07-22 跨站写入根因：Voice Pack 写路由原 `_require_local()` 只检查 `request.client.host`；浏览器访问 localhost 时客户端地址仍是本机，但请求可携带恶意站点 Origin。主应用又使用通配 CORS，OPTIONS 预检在路由前完成，因此仅靠本机 IP 或路由内校验都不能构成浏览器写保护。
- 2026-07-22 Origin/CORS 修复：`create_voice_pack_router()` 现在接收并在全部 import/enable/select/disable/unregister 路由复用主应用 `local_control_guard`，实际写入必须同时满足本机客户端和受信 8000 本机 Origin；缺失 Origin 的本机脚本/测试/CLI 兼容不变。主应用在通配 CORS 外层安装 `VoicePackOriginGuardMiddleware`，对 Voice Pack 实际写方法和声明写方法的 OPTIONS 提前执行同样限制，恶意预检不会获得 CORS 允许头；GET/只读预检保持原行为。
- 2026-07-22 独立安全测试：新增 `tests/test_voice_pack_origin_guard.py`，全部使用 `TemporaryDirectory` 内的微型假 checkpoint、假 WAV、两个假包、临时 `VoicePackRegistry` 和纯 ASGI 客户端。恶意 Origin 对五类写接口均为 403 且注册表原始字节不变；合法 `127.0.0.1:8000`/`localhost:8000`、无 Origin 本机调用正常；非本机无 Origin 仍拒绝；恶意 POST/DELETE 预检为 403 且无 `access-control-allow-origin`，合法写预检和跨站只读 GET/GET 预检保持可用。
- 2026-07-22 数据隔离证据：本轮安全测试与全部回归未启动真实应用 lifespan，未打开、读取或修改真实 `voice_pack_registry.local.json`、Voice Pack runtime、GPT/SoVITS 权重、参考音频或生成音频；独立夹具的 registry/package/runtime 均在系统临时目录并自动清理。生产本机注册表只做 Git 忽略状态核对，不读取内容。
- 2026-07-22 PK-900 复验通知：跨站 Origin 阻断整改已就绪，请按原恶意 Origin ASGI 夹具重跑 import/enable/select/disable/unregister，并核对主应用通配 CORS 下恶意写预检为 403、状态不变；PK-212 仍为“待集成”，本通知不构成 PK-900 通过结论。
- 2026-07-22 Origin 整改最终验证：`test_voice_pack_origin_guard.py`、`test_voice_pack_registry.py`、`test_gpt_sovits_engine_sessions.py`、`test_gpt_sovits_provider.py`、`test_voice_module.py`、`test_feature_catalog.py`、`test_dashboard_shell.py`、`test_conversation_module.py`、`test_conversation_consumers.py` 全部通过；相关 `features/voice`、catalog、API 和测试完成 `compileall`。文档门禁通过 9 个 gated tasks，`git diff --check` 无空白错误，仅有混合工作区既有 LF→CRLF 提示。所有导入主应用的回归均将 Voice Pack 注册表指向独立临时路径，未启动 lifespan 或生产服务。
- 2026-07-22 PK-000 最终复核：路径穿越、绝对路径、反斜杠路径、符号链接和执行脚本均被拒绝；Voice Pack 切换失败后注册表、Provider 与模拟引擎仍使用旧 Pack。

## 2026-07-30 PK-011 可安装化增量

### 交付范围

- 新增 `server/features/voice_pack_registry/` 专属包源。正式 manifest 为
  `voice_pack_registry@1.0.0`、`in_process`、`backend.register`，只依赖稳定
  `voice` 模块，拥有 `/api/v1/voice-packs` namespace、动态
  `dashboard/index.js`、`local_state` 最小权限和
  `preserve_on_uninstall` 数据策略。
- `package_builder.py` 使用固定 allowlist，把现有 PK-212
  `errors/manifest/registry/router/security/service` 逻辑规范化为包内
  `backend/`，并加入结构等价的 PK-210 `VoicePackRef`/health/capabilities
  值、`backend.register` 和 Voice Pack JSON Schema。所有文本统一 UTF-8/LF，
  ZIP 使用固定时间、权限、无 extra/comment 的 `ZIP_STORED` 条目；相同输入构建
  字节和 SHA-256 完全一致。
- 包内只含模块 manifest、Voice Pack Schema、Registry/导入校验/启停选择注销
  程序、动态管理面板；不含 `voice-pack.json` 实例、Kei/其他角色权重、参考音频、
  模型配置实例、真实 registry、本机绝对路径、`.env`、vendor、BAT/PowerShell/
  shell、安装器或自动执行 hook。
- 动态面板只通过受限 `context.request` 调用 `/api/v1/voice-packs`，支持读取、
  高级本机路径导入、启用、选择、停用和只注销记录。浏览器不持久化路径或业务
  状态；注销确认明确说明不会删除源模型或参考音频。

### Provider 与装配接缝

- `backend.register(app)` 在无现有 Voice Pack 路由时创建临时/生产可注入的
  Registry service，公开 `app.state.voice_pack_resolver` 与
  `app.state.voice_pack_registry_service`。可通过
  `app.state.voice_pack_registry_bind_activator(provider)` 在 Provider 可用时
  绑定；若 Provider 实现 `set_voice_pack_resolver()`，包会把同一 Resolver
  回注。可选 `voice_pack_resolver_consumer` 允许 PK-210 的后续装配消费 Resolver。
- 路由、Registry 和 Provider 都不互相导入 GPT-SoVITS Engine 实现；无 Pack、
  无 activator 时空列表与 Core 其他路由仍可使用。选择失败继续保留旧活动 Pack。
- 当前共享 `server/api.py` 仍静态注册同一 namespace，并在 lifespan 内创建旧
  service。为避免开发源码与安装包产生重复路由，模块入口检测到任何既有
  `/api/v1/voice-packs` 路由时幂等进入 `existing_routes` 模式，不创建 registry、
  runtime 或重复中间件。PK-000 串行装配时需移除静态 Voice Pack router/middleware/
  lifespan service 所有权，并在 Provider 创建后调用上述 binder；这属于共享
  文件窗口，本对话没有越权修改。

### Release 元数据

- `release/official-release-fragment.json` 与
  `official-catalog-entry.json` 已固定
  `module-voice-pack-registry-v1.0.0` /
  `voice_pack_registry-1.0.0.zip`、官方仓库 URL、精确 64000 字节、
  manifest SHA-256
  `d2b36c58eeb1d567631c947e1912c51eae3b13eed69b35adebd917be9f741cef`
  和 ZIP SHA-256
  `cedc0291488fee9daee8d387047bd0d746255ec6b663dd35a727fcaa8c41b7df`。
  元数据通过 PK-010 官方 Catalog builder 从临时确定性 ZIP 重建；未把条目写入
  共享官方 Catalog，未生成或发布仓库内 Release 资产。

### 数据与卸载语义

- 专项测试的 ModuleManager、模块 registry/runtime/data、Voice Pack Registry、
  两个微型假 Pack、假 checkpoint、假 WAV 和 fake activator 全部位于
  `TemporaryDirectory`。未读取或修改真实
  `voice_pack_registry.local.json`、真实 `server/runtime/voice_packs`、模型、
  参考音频、Engine 登记、`.env`、个人状态或 vendor。
- 生命周期测试证明模块卸载只删除 ModuleManager 的可再生成程序版本，保留独立
  Voice Pack Registry 原字节和源假 Pack 资产；重新安装并启用后可重新读取原活动
  Pack。模块 `purge-data` 只可能针对新的
  `server/data/modules/voice_pack_registry/` namespace，不能删除/移动 Voice Pack
  Registry 或模型资产。

### 隔离验证与共享遗留

- 通过 `tests/test_voice_pack_registry_module.py`：覆盖确定性目录/ZIP、固定文件
  清单和 release 元数据重建；临时 fake `voice` 依赖；安装、启用、装载、停用/
  卸载、重装；空 Registry/无 Engine Core 正常；两 Pack 导入/启用/选择；
  Provider 收到正确不透明配置；候选激活失败后旧 Registry/Provider/活动 Pack
  保持；真实源假资产保留；重复 loader/重复 `register`/既有静态 namespace
  不产生重复路由；traversal、Unix/盘符绝对路径、symlink、Windows reparse 和
  manifest `install_script` 恶意 ZIP 均在正式 runtime/registry 前拒绝。
- 通过原 PK-212/Provider/生命周期回归：
  `test_voice_pack_registry.py`、`test_voice_pack_origin_guard.py`、
  `test_installable_modules.py`、`test_gpt_sovits_provider.py`、
  `test_gpt_sovits_engine_sessions.py`、`test_voice_module.py`、
  `test_official_module_catalog.py`。新包源码/测试 `compileall` 与动态入口
  `node --check` 通过。
- `test_dashboard_shell.py`、`test_feature_catalog.py` 在迁移期 Python 3.8
  解释器导入当前并行 `features/rss_intel.provider` 时，因未延迟求值的
  `RSSIntelSourceConfig | Mapping[...]` 抛出 `TypeError`；系统 Python 3.12
  没有 FastAPI/Starlette，无法替代复跑。本任务未修改 RSS、Dashboard、Catalog
  或 API，失败发生在导入本任务代码前，交 PK-000 在共享新解释器环境复验。
- `scripts/check_python_test_inventory.py` 如实报告 13 个并行业务批新增测试尚未
  收编，其中包括 `test_voice_pack_registry_module.py`；测试 inventory 是共享
  文件，按冻结规则未修改，交 PK-000/PK-030 串行合并。
- 迁移解释器没有安装 `ruff`，因此专属 ruff 命令无法启动；没有伪称通过。
  本任务未暂存、提交、推送、发布、清理或修改 `TASKS.md`。
- 最终门禁：`check_task_docs.py` 通过 19 个 gated tasks；`git diff --check`
  退出码 0，仅报告混合工作区既有 LF→CRLF 提示；本任务专属路径无暂存内容。
  真实 Registry、模型和输出只做 Git 忽略状态核对，未读取内容。

## 完成文档门禁

任务进入“待集成”或“已完成”前必须全部勾选；不适用项也必须写明原因。

- [x] TASK_RECORD — 已追加可安装 manifest、确定性包、动态面板、Provider binder、
  重复路由、卸载保留资产、release 摘要、临时数据证据、测试结果和共享遗留。
- [x] TASKS_BOARD — PK-000 已把 PK-212 重新置为“进行中”并补
  PK-010/PK-100/PK-210 依赖；本对话按明确冻结要求不修改 `TASKS.md`，任务板最终
  “待集成”回写交 PK-000 串行完成。
- [x] PUBLIC_README — 本轮不适用：`README.md` 属 PK-011 共享冻结路径；准确用户
  行为、包内容和限制已记录在本文件，交 PK-000 语音批收口。
- [x] MODULE_CATALOG — 本轮不修改共享 catalog service 或官方 Catalog；专属
  Release fragment/entry 已生成并验证，等待 PK-000 在全批通过后合并。
- [x] ARCHITECTURE_DOCS — 本轮不适用：模块包和 Voice Pack 架构文档均为共享
  冻结路径；本增量的接缝、生命周期和遗留已完整记录，未改变既有 Schema/Provider
  公共语义。
- [x] LOCAL_README — 不适用：未改变本机路径、启动器、解释器、端口或环境位置，
  也未读取/写入任何真实 Voice Pack 本机绑定。
- [x] AGENT_RULES — 不适用：未改变 agent 工作流、安全、验证、文档或 Git 政策。
- [x] VALIDATION — 已记录专属安装包、恶意 ZIP、生命周期、Provider/回滚、资产
  保留、原 PK-212/voice/engine/Core/Catalog 回归、compileall、Node 语法及环境
  阻断；最终文档门禁和 `git diff --check` 已重跑通过。

## 独立对话启动提示

```text
领取 PK-212“Voice Pack 注册表与 Kei 模型包”。先完整阅读项目启动文件、
PK-210/PK-212 任务说明和相关架构文档，检查混合工作区。只实现版本化
Voice Pack Schema、脱敏注册表、本地显式导入校验、原子切换和 Kei 本机 Pack
适配。不要扫描 GPT-SoVITS 源码，不要读取/移动/打包/提交真实权重和参考音频，
不要实现 Persona Pack 或 PK-200 配置。测试只使用临时假 Pack 与假 Provider。
如需改变 PK-210 契约，先记录并交回 PK-000。
```
