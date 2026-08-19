# PK-213 — Voice Pack 发布、远程获取与一键安装

- 状态：待集成
- 优先级：P1
- 所属模块：`voice_pack_distribution`
- 依赖任务：PK-010、PK-020、PK-100、PK-211、PK-212
- 负责路径：根目录 `voice-pack.bat`、`voice-pack-build.bat`；对应
  `scripts/voice-pack*.ps1` 薄入口；`server/features/voice/voice_packs/`
  下独立 `distribution/`、`catalog/` 子边界；分发专项测试、fake Release
  夹具、本任务文件和窄范围公开安装/语音架构说明
- 当前对话：2026-07-30 已按 PK-010 冻结权限发布
  `voice_pack_distribution@1.0.1` 确定性输入；PK-213 保持“待集成”，等待
  PK-000 串行装配与新的独立累计验收

## 目标

在不改变 PK-211 Engine 所有权和 PK-212 本机 Schema/Registry 所有权的前提下，
建立可审计的 Voice Pack 发布与可信分发链路。最终用户应能从项目根目录运行
`voice-pack.bat install kei@1.0.0`，由工具从受版本控制的可信 catalog 解析固定
来源，完成下载、大小/SHA-256 校验、安全解压、PK-212 导入、启用和选择，并把
“Pack 已安装”与“所需 GPT-SoVITS Engine 已可用”分别报告。

本任务分为两个门禁阶段：

1. **预发布技术阶段**：完成构建器、catalog Schema/加载器、下载器、CLI/BAT、
   fake Release/HTTP、干净机器安装测试、文档与安全审计；不得包含真实 Kei
   资产、真实生产 URL 或编造摘要。实现完成后置为“待集成”，由 PK-900 做首次
   独立技术验收。
2. **真实发布阶段**：只有首次 PK-900 通过、PK-000 记录分发权结论且用户明确
   授权后，才可从用户明确提供的源目录构建真实包、创建 tag/Release、上传资产、
   把最终固定 URL/大小/SHA-256 合入 catalog，再由 PK-900 做发布后复核。

首次技术验收通过不等于真实 Kei Pack 已可下载。只有发布后复核通过，PK-000
才能把 PK-213 和对应 PK-900 最终标记“已完成”。

## 依赖与所有权

- **PK-020**：提供受支持的 Windows/Python 环境、根目录可移植入口和路径/中文/
  非系统盘基线。PK-213 不修改 setup/profile/锁语义；PK-020 未完成前 PK-213
  不得进入“进行中”。
- **PK-211**：唯一拥有 GPT-SoVITS Engine 描述、固定来源、受控获取、本机登记、
  9880 Provider 和 Engine 启动定位。PK-213 只读取脱敏 Engine ID/兼容范围/
  无路径状态，不复制或自动调用 Engine 下载器。
- **PK-212**：唯一拥有 `voice-pack.json` Schema、逐文件完整性、本机 Registry、
  导入、启停和原子选择。PK-213 负责包级来源、下载与归档外层防护，最终必须
  调用 PK-212 公开 service/API 接缝，不维护第二套 manifest 或 Registry 规则。

若实现必须改变任一依赖的公共契约，独立任务必须停止扩大修改，在本文件记录
具体调用缺口、所需签名和最小兼容建议，交回 PK-000 决定。

## 分发权门禁

真实构建前必须由 PK-000 记录并由用户确认：

- GPT 与 SoVITS 权重是否允许公开分发；
- 参考音频是否由项目拥有或已获得公开分发授权；
- 是否包含第三方角色、配音演员或其他受限制素材；
- 包使用的许可证、NOTICE 和署名要求；
- 是否允许修改、再训练及再分发。

2026-08-01 的当前结论为：**用户明确声明拥有 GPT/SoVITS 权重与参考音频的公开
再分发权，并授权 `songshu-yu` 以非商用 Voice Pack 许可公开发布完整包。** 权利
范围允许公开下载、使用和原样再分发完整包；必须保留 LICENSE/NOTICE/README/
manifest，禁止商业使用、单独资产再分发、二次训练、冒充和违法用途。

在该授权以前适用的预发布限制历史保留如下；它们不再阻止本次经确认的 1.0.0
构建，但仍适用于任何未单独确认的新资产或新版本：

- 只能开发工具、Schema、空/假 catalog 和微型虚构测试包；
- 不得读取、摘要、复制、移动、打包或上传真实 Kei 权重/参考音频；
- 不得扫描磁盘寻找模型；
- 不得创建真实 GitHub tag/Release 或生产 catalog 条目；
- 不得编造 URL、字节数、SHA-256、许可证或“已发布”状态。

真实构建必须要求用户显式提供模型源根、项目外的新输出路径、版本和精确确认；
构建器不得读取源根之外的训练文件，也不得覆盖既有输出。

## 正式包契约

正式 Release Asset 名称冻结为：

```text
kei-voice-pack-<semver>.zip
kei-voice-pack-<semver>.zip.sha256
kei-voice-pack-<semver>.release.json
```

ZIP 的单一根目录冻结为 `kei-voice-pack/`：

```text
kei-voice-pack/
├── voice-pack.json
├── models/
│   ├── kei-gpt.ckpt
│   └── kei-sovits.pth
├── references/
│   └── kei-reference.wav
├── README.md
├── LICENSE.txt
└── NOTICE.txt
```

具体资产文件名由真实构建前的授权清单确认，但允许路径只能落在上述声明位置，
并与 `voice-pack.json` 的相对路径、大小和 SHA-256 完全一致。正式包不得包含：

- GPT-SoVITS Engine 或其他公共运行时；
- 原始训练集、未使用 checkpoint、训练日志、缓存或中间产物；
- 开发者绝对路径、私有下载源或本机 wheel；
- `.env`、Cookie、Token、API Key、用户状态、聊天记录或 QQ 标识；
- BAT、CMD、PS1、PY、SH、EXE、DLL、安装器、hook 或命令字段；
- 未声明额外文件、符号链接、硬链接或 Windows 重解析点。

发布构建器必须生成确定性 ZIP、文件级与包级 SHA-256、完整资产清单和
`release.json`，扫描秘密形态、绝对路径、训练缓存和禁止扩展名。它不得修改
源模型、覆盖输出或在失败后留下看似成功的 ZIP。

## 可信 catalog 契约

第一版 catalog 只来自受版本控制的应用内置目录，建议路径：

```text
server/features/voice/voice_packs/catalog/
├── catalog.schema.json
└── <pack-id>.json
```

生产条目至少固定：

- `pack_id`、语义化 `version`、display name、engine ID、language；
- Core、Voice Pack Schema、Engine 协议/版本兼容范围；
- 固定 HTTPS 下载地址和逐跳允许主机；
- 精确 ZIP 字节数和 SHA-256；
- 最大文件数、单文件大小、总解压大小和压缩比；
- license/notice URL；
- release/tag/完整 commit 或固定 revision 身份；
- 是否推荐在用户确认后自动 select；
- 发布时间和 catalog schema 版本。

catalog 加载必须拒绝未知字段、重复 `id@version`、非 HTTPS、非允许主机、空或
非固定版本、`latest`、`main`、可变重定向、非 SHA-256、无精确大小和不合理
限制。浏览器、普通用户、命令行参数和本机配置均不能提供 URL、Git URL、镜像、
header、Cookie、代理凭证、shell 命令或安装脚本。

`.sha256` 远程资产只供人工核对，不是信任锚。安装器必须使用合并进 Git 的
catalog 摘要。真实发布前只能提交 catalog Schema 与 fake 测试条目；生产
`kei.json` 必须等待最终 Release 已存在且真实元数据已复核。

## CLI/BAT 契约

普通 Windows 用户入口冻结为根目录 `voice-pack.bat`。它从 `%~dp0` 解析项目根，
使用 PK-020 的受支持 Python 解析器，完整转发参数/退出码，对空格、中文和
非系统盘路径安全；不要求用户启动 FastAPI、手写 HTTP 或 Python import。

第一版命令冻结为：

```text
voice-pack.bat list
voice-pack.bat status [<pack@version>]
voice-pack.bat install <pack@version>
voice-pack.bat install <pack@version> --download-only
voice-pack.bat import <local-zip-or-directory>
voice-pack.bat select <pack@version>
voice-pack.bat verify <pack@version>
```

- `list`：只读受信 catalog，并合并脱敏的本机安装/活动状态；零网络。
- `status`：只读 Pack 与所需 Engine 的脱敏状态；不读取模型内容。
- `install`：唯一可触发 catalog 网络下载的命令。下载前显示名称、版本、下载/
  解压大小、许可证、所需 Engine、预计磁盘、正式运行目录，并要求用户精确输入
  `<pack@version>`。自动化只能使用同值的显式 `--confirm <pack@version>`。
- `--download-only`：完成来源、大小、摘要和完整 ZIP 安全验证后，把不可变包
  原子保存到忽略的下载缓存；不导入、不启用、不选择。不得留下未验证文件。
- `import`：只接受用户明确给出的本机 ZIP 或目录，不删除/移动源。已收录版本的
  ZIP 必须匹配 catalog 包级摘要；未收录 ZIP 必须由用户同时给出预期 SHA-256
  和精确 `id@version` 确认，不能从同一远程位置临时下载 checksum 后信任。
  目录没有 ZIP 包级摘要，只能按 PK-212 的精确逐文件大小/SHA 校验并标记为
  `local_unpublished`，不能冒充 catalog Release 或通过该路径生成生产条目。
- `select`：只选择已安装且启用的 Pack，继续使用 PK-212/211 原子事务。
- `verify`：重新验证下载缓存、运行副本和 Registry 中可安全公开的完整性状态；
  不读取或输出模型内容、本机绝对路径或参考音频。

首版不提供任意 URL 安装、搜索市场、自动更新、删除/清理资产或强制覆盖。
构建入口独立为：

```text
voice-pack-build.bat --source <explicit-root> --output <new-zip> \
  --version <semver> --confirm <pack@version>
```

## 下载、解压与安装事务

远程安装固定按以下顺序执行：

1. 从受信 catalog 按精确 `id@version` 解析唯一条目。
2. 显示元数据、磁盘与目标并取得精确确认。
3. 在系统临时目录创建本次唯一隔离根；不复用其他任务临时目录。
4. 设置连接、读取和总下载超时；流式下载并限制最大字节数。
5. 限制重定向次数，每一跳都重新验证 HTTPS、允许主机和固定目标策略。
6. 检查精确下载大小与 catalog SHA-256。
7. 在读取条目数据前审计 ZIP central directory，拒绝绝对路径、盘符、`..`、
   目录逃逸、链接/重解析点、重复/冲突路径、未知额外文件、禁止扩展名、过多
   文件、单文件/总解压大小超限和异常压缩比。
8. 在隔离根展开，再调用 PK-212 解析 `voice-pack.json` 并校验每项资产。
9. 只有包级和 PK-212 校验均成功后，才由 PK-212 原子导入到正式运行目录/
   Registry；不得先发布半成品目录或半条 Registry。
10. 根据 catalog 建议和用户确认启用/选择。

事务边界明确分成：

- **安装事务**：下载/本地源 → 包级校验 → PK-212 导入提交。提交前失败时，
  Registry 和正式运行目录不变；只清理本次临时产物。
- **选择事务**：候选已安装后，由 PK-212/PK-211 完成 Engine 权重与活动 ID
  原子切换。选择失败时可保留新安装 Pack，但旧活动 Pack、旧 Engine 权重和
  旧活动 ID 必须不变，并明确报告“已安装、未选择”。

同版本且包级/逐文件摘要一致时幂等复用；任一摘要不一致都拒绝覆盖。不同版本
并存，旧版本默认保留。不得删除用户提供的 ZIP/目录。Engine 未登记时 Pack 可
安装并启用，但必须报告“语音不可用”、缺失 Engine ID 和下一条精确 PK-211
获取/登记命令；不得自动下载约 8 GB Engine、安装 CUDA/驱动/7-Zip 或把 Pack
安装成功等同于语音可用。

## 数据所有权

- 可提交：distribution/catalog 代码、catalog Schema、无真实来源的测试 catalog、
  BAT/CLI/build 工具、脱敏示例、fake Release/HTTP 测试和文档。
- Git 忽略：已验证下载缓存、临时 marker、展开 staging、PK-212 runtime/
  Registry、本机 Engine 登记、真实构建输出和失败诊断细节。
- 用户所有：本机 ZIP/目录、真实权重、参考音频、训练资产、许可证原件和外部
  Engine。默认不移动、不删除、不扫描。
- 错误和日志只能返回稳定错误码、pack ID/version 和有限阶段信息；不得输出
  本机绝对路径、模型/音频内容、上游响应正文、重定向中的秘密或异常链。

## 不在本任务内

- 不改变 PK-210 ASR → conversation → TTS 编排或 `/api/v1/voice`。
- 不改变 PK-211 Engine 描述、来源、Provider、9880、登记或获取所有权。
- 不改变 PK-212 Schema/Registry/导入/启停/选择的业务规则；只调用公开接缝。
- 不把 LLM Profile、system prompt、Persona Pack、长期记忆或角色状态装入
  Voice Pack。
- 不实现云端市场、搜索、评分、账号、自动同步、后台更新、P2P 或任意镜像。
- 不提供 reset、force、覆盖安装、批量删除或默认删除旧版本/用户源。
- 不在实现或首次 PK-900 中读取/构建/上传真实 Kei 资产或创建真实 Release。

## 允许修改的边界

- 新建 `voice-pack.bat`、`voice-pack-build.bat` 和对应 `scripts/` 薄入口。
- 新建 `server/features/voice/voice_packs/distribution/**` 与
  `server/features/voice/voice_packs/catalog/**`。
- 新建 PK-213 专项测试和完全虚构的小型 Release/HTTP/ZIP 夹具。
- 窄范围调用 PK-212 已有公开 service/API；如缺少可注入 composition seam，
  先记录需求交回 PK-000。
- 更新本任务、`TASKS.md`、`README.md`、`docs/architecture/voice-packs.md`、
  `docs/architecture/gpt-sovits-engine.md`、`docs/architecture/windows-install.md`
  及必要的模块 Catalog 条目。

不得修改 `server/api.py`、PK-210 编排、PK-211 Provider/descriptor、PK-212
Schema/Registry 规则、真实本机登记或其他业务模块，除非 PK-000 对已记录的
最小公共接缝另行授权。

## 验收标准

- 正常 fake catalog 链路覆盖下载、大小/SHA、解压、PK-212 导入、启用、选择，
  且只通过公开契约协作。
- `download-only` 只产生完整验证的忽略缓存；离线 ZIP 必须使用 catalog 或用户
  显式提供的预期包级 SHA，目录必须标记为未发布并执行 PK-212 逐文件校验；
  两者都不删除用户源。
- 重复安装同摘要幂等；摘要冲突拒绝覆盖；新旧版本并存且旧版本不被删除。
- 下载中断、连接/读取/总超时、过大流、错误大小/SHA、危险重定向、白名单外
  主机和任意用户 URL 均在副作用前失败；白名单外 URL 请求数为零。
- ZIP 拒绝路径穿越、绝对/盘符路径、目录逃逸、链接/重解析点、重复路径、
  ZIP bomb、文件数/单文件/总大小/压缩比超限、未知额外文件及
  EXE/BAT/CMD/PS1/PY/SH/DLL。
- manifest 缺失/未知字段/版本、文件大小或摘要不符继续由 PK-212 拒绝；PK-213
  不维护另一套放宽规则。
- Registry 原子失败不留下运行目录或半记录；选择/权重/Registry 保存失败时旧
  Pack 与旧 Engine 保持可用，或按 PK-212 已冻结的回滚失败语义进入明确 unknown。
- Engine 缺失时 Pack 可安装但明确不可用，输出所需 Engine ID 和精确 PK-211
  下一步；零自动 Engine/CUDA/驱动/解包器安装。
- 构建器不扫描源外、不改源、不覆盖输出，生成确定性 ZIP/清单/摘要；失败不留
  成功外观产物，并拒绝秘密形态、训练缓存、绝对路径和禁止扩展名。
- 路径含空格、中文和非系统盘时 BAT、构建、下载缓存、导入与选择保持正确。
- 所有测试只用 fake HTTP、微型虚构 checkpoint/WAV/ZIP、fake Engine 和系统
  临时目录；不访问真实模型、参考音频、Registry、Engine、网络或 GitHub。
- 项目差异不包含真实权重、音频、Engine、`.env`、秘密、个人状态、缓存、
  本机路径、`vendor/` 或未授权 Release 资产。

## PK-900 验收与发布门禁

### 首次：预发布技术验收

PK-213 实现完成后保持“待集成”，登记独立 `PK-900 = PK-213`。PK-900 必须：

- 独立使用 fake HTTPS/重定向和微型包重放全部安全/原子失败矩阵；
- 在干净、含空格/中文、非系统盘的 PK-020 环境运行 BAT/CLI；
- 证明 PK-211 Engine 与 PK-212 Registry 所有权未被复制；
- 扫描差异确认无真实资产、秘密、本机路径、伪造生产 URL/SHA 或 Release；
- 核对 README、catalog Schema、架构、模块目录和实际实现一致。

通过后只记录“预发布技术验收通过”，不得把真实 Kei Pack 描述为可用，也不得
自动把 PK-213 标记“已完成”。

### 第二次：真实发布后复核

只有用户另行明确授权后，才允许真实构建、许可证/清单人工核对、tag/Release、
资产上传和生产 catalog 更新。发布后 PK-900 必须重新核对：

- Release/tag/revision 不可变身份；
- 远程资产实际字节数和 SHA-256 与 catalog/本地构建产物一致；
- 公开 LICENSE/NOTICE/Release Notes 与授权记录一致；
- 一台无本机 Kei Pack 的隔离机器能用正式 catalog 完成下载/验证/安装；
- Engine 缺失、已登记两种状态都如实报告；
- 最终公开差异仍无真实权重、参考音频或秘密。

只有第二次复核通过，PK-000 才能把 PK-213 和该发布批次 PK-900 改为“已完成”。

## 实施清单

- [x] PK-020 由 PK-000 最终标记“已完成”后领取任务并同步为“进行中”。
- [x] 审计 PK-212 实际公开导入/启用/选择接缝；缺口先交回 PK-000。
- [x] 定义 catalog Schema、严格加载器和无真实来源的测试 catalog。
- [x] 实现边界明确的 fake/真实可替换 HTTP 下载器和安全 ZIP 外层验证。
- [x] 实现根 BAT/CLI、download-only、离线导入、verify 与状态输出。
- [x] 实现确定性发布构建器和资产/秘密/训练产物扫描。
- [x] 完成全部 fake、临时目录、失败/并发/原子/路径测试。
- [x] 更新 README、架构、模块目录、任务记录和八项文档门禁。
- [x] 保持“待集成”并交给首次独立 PK-900；不创建真实 Release。

## 工作记录

- 2026-07-30：完成 PK-011 可安装化增量入场审计。`TASKS.md` 已由 PK-000
  将 PK-213 置为“进行中”并补充 PK-010/100/211/212 依赖，本对话未修改总板。
  现有 PK-010 manifest/loader 只支持 `in_process` 与 `sidecar`；
  `in_process` 的 `backend.register(app)` 只接收 FastAPI app，模块包契约同时
  禁止反向导入其他 `features.*` 内部实现。PK-213 的可信安装、同 key 内容比较、
  verify、导入、启用与选择必须继续调用 PK-212 service，不能复制 manifest/
  Registry/原子选择规则；当前 PK-212 任务记录尚未冻结其
  `voice_pack_registry` 包的 `backend.register` composition、跨包只读/写 service
  获取方式、依赖/重启语义，以及卸载/重装时现有 Voice Pack Registry、runtime
  和已安装资产的保留契约。
- 2026-07-30：当前 PK-010 也没有 `project tooling` 模块类型、声明式 tooling
  入口或 Core 拥有的已安装包 CLI 调度接缝。直接新增 manifest 类型/命令字段会
  修改冻结 Schema；让根 `voice-pack.bat` 直接导入 runtime 包、开发源码或私有
  Registry 会绕过 ModuleManager 和 PK-212 所有权。因此本轮在任何实现、构建、
  测试或包产物前停止，向 PK-000 请求先由 PK-212 冻结最小公开接缝：
  1) `voice_pack_registry` 安装包的 `backend.register(app)` composition；
  2) PK-213 可在不反向导入内部实现、不读取 Registry 私有 JSON的前提下调用
  `verify/compare_content/import/enable/select` 的稳定方式；
  3) 卸载 PK-212/PK-213 时 Registry、runtime、下载缓存和已安装 Voice Pack
  均保留的责任边界；4) 根兼容 CLI shim 由 Core 串行装配时可调用已安装
  PK-213 包的声明式入口。若 PK-010 不能用现有 `in_process` 安全表达第 4 项，
  应由 PK-000 先批准最小 Core tooling 接缝；manifest 仍不得包含命令、脚本、
  任意路径或 shell。
- 2026-07-30：入场审计只读取项目规则、任务/架构文档和项目自有源码，未读取
  私有 Registry、本机 Engine 登记、真实权重/参考音频、`.env`、个人状态、
  cache、`node_modules` 或 `vendor/`；未联网、安装、下载、运行 Engine/9880、
  LLM、QQ、ASR/TTS，未创建模块 ZIP、catalog 条目、tag/Release，也未修改
  `TASKS.md`、README、Core modules、API、Catalog、dashboard 或其他冻结共享文件。
- 2026-07-30：PK-212 已冻结 `voice_pack_registry@1.0.0` 的动态 composition。
  PK-213 新增 `voice_pack_distribution@1.0.0` 确定性 `in_process` 包，只依赖
  `voice_pack_registry`，通过
  `app.state.voice_pack_registry_service` /
  `voice_pack_resolver_consumer` 获取 PK-212 公开 service。包内调用
  `list_packs/import_pack/enable/select/verify/compare_content`，不读取 Registry
  JSON、不反向导入 PK-212 源码，也不复制其 Schema、资产摘要校验或原子选择规则。
  Core 任意加载顺序下，分发模块若先加载会先登记 consumer，Registry 随后就绪时
  再完成 `/api/v1/voice-pack-distribution` 路由与 service 绑定；依赖缺失时
  ModuleManager 明确报告 `voice_pack_registry`，Core 其他功能不受影响。
- 2026-07-30：模块包源位于
  `server/features/voice/voice_packs/distribution/package_source/`，只含严格
  catalog loader/Schema、逐跳 HTTPS 下载器、外层 ZIP 审计/安全展开、PK-212
  service 适配、动态分发面板和 manifest。内置 catalog 只有公开 Schema，没有
  Voice Pack 生产条目、权重、参考音频、Engine、真实 Registry、绝对路径、秘密、
  `vendor`、远程脚本或任意执行 hook。普通 register/list/status/verify 零网络；
  只有用户明确调用 install/download-only 才能访问 catalog 固定 HTTPS 来源，
  每次重定向均重验 scheme/host，精确校验大小/SHA 后才审计 ZIP。
- 2026-07-30：`package_builder.py` 使用固定文件 allowlist、逐层 `lstat`、
  symlink/reparse/hardlink 拒绝、源内输出拒绝、UTF-8/LF 归一化、固定排序/
  时间/权限和 `ZIP_STORED`，两次构建字节完全一致。公开 release 片段与可复建
  Catalog entry 固定模块 tag/asset、62223 字节、manifest SHA-256
  `761989899a1649f52c1e2d10df39bef7b21dc0084357889f4ef34acf71d7c5e3`
  和 package SHA-256
  `c9941ac51d76aa1a5ff4030c5b15b32d3616d007b43a016cbc492091803703fd`；
  仓库内没有生成 ZIP，也没有并入共享 Catalog、创建 tag/Release 或上传资产。
- 2026-07-30：新增 `test_voice_pack_distribution_module.py`，全部夹具位于
  `TemporaryDirectory`，使用真实临时 ModuleManager、PK-212 临时 Registry/
  runtime、fake HTTPS、微型虚构 checkpoint/WAV/ZIP 和 fake Engine 状态。覆盖
  确定性/无资产包、下载前零网络、download-only、可信安装、可信内容与本机相同
  内容幂等、同 key 不同内容稳定 conflict、Registry/cache/源资产不变、恶意
  跨主机重定向零正文读取、响应大小/SHA 错误、ZIP symlink、安装/启停/卸载/
  重装、缓存与 Pack 保留及缺依赖提示，专项通过。原 PK-213 13 项、PK-212
  Registry/Origin/安装包、PK-211 Provider/Engine session、Voice 安装包、
  官方模块 Catalog 和 Windows CI copy 均通过。
- 2026-07-30：累计门禁的两个共享失败如实保留且未越权整改：
  `test_installable_modules.py` 在 sidecar readiness 状态机断言失败；
  `test_windows_install.py` 的 QQ 模块复制夹具缺少并行新增
  `core.modules.assembly`、Python 3.8 不支持测试内 `str.removesuffix`，并连带
  产生 QQ dependency 断言失败。这些失败发生在导入/运行 PK-213 代码之外，
  `test_windows_ci_copy.py` 8/8 通过；共享 Python test inventory 也如实报告
  18 个并行业务批新增测试尚未收编，其中包含本任务与 PK-212 的模块专项。
  inventory 属冻结共享清单，本轮未修改；以上均交 PK-000 在共享串行窗口复验。
- 2026-07-30：PK-010 manifest 当前仅允许 `local_state` 权限，不能声明
  “只有显式 install 才可联网”；也没有 `project tooling` 类型或已安装包 CLI
  调度入口。PK-213 未向 manifest 添加未知 `network` 权限、命令或脚本，未修改
  根 `voice-pack.bat`/PowerShell shim。请 PK-000 串行决定最小声明式 network/
  tooling 契约，并让兼容 CLI 在分发模块缺失时给出安装提示、存在时调用已安装
  包入口；在此之前旧开发源码 CLI 继续兼容，但不冒充模块化 CLI 已完成。
- 2026-07-30：本轮未修改 `TASKS.md`、README、架构、共享 Catalog/API/Core/
  dashboard/BAT；这些路径按 PK-011 冻结交 PK-000 批次收口。未访问真实网络、
  Registry、Engine、9880、权重、参考音频、`.env`、个人状态、`node_modules`
  或 `vendor`，未暂存、提交、推送、清理或发布。PK-213 恢复“待集成”，等待
  PK-000 安排新的独立累计验收，不标记“已完成”。
- 2026-07-30：在 PK-010/PK-020/PK-134 最新共享改动后重新收口。此前
  `core.modules.assembly` 缺失和 SidecarReadiness 状态机全量失败已经关闭：
  `test_installable_modules.py` 通过；Python 3.12 下完整
  `test_windows_install.py` 25/25 通过（270.770 秒，
  `protected_rejected=34 allowed_io_calls=460`），Windows CI copy 8/8 通过。
  Python 3.8 的 `str.removesuffix` 唯一项目命中精确位于 PK-020 所属
  `server/tests/test_windows_install.py:288`，不在 PK-213 专属路径；本轮没有
  越权修改。公开 README 已声明受支持 Python 为 3.10–3.13，因此 3.8 结果只作
  共享测试夹具归属证据，不冒充目标运行时矩阵。
- 2026-07-30：PK-213 模块生命周期与原 13 项专项均通过；PK-212 Registry、
  Registry installable module、Origin guard、PK-211 Provider、共享 Engine
  session 和官方模块 Catalog 回归均通过。所有夹具仍只使用临时目录、fake
  HTTPS/`MockTransport`、微型虚构资产与 fake Engine，没有访问真实网络、
  Registry、Engine、9880、模型、音频、`.env`、个人状态、`node_modules`
  或 `vendor`。
- 2026-07-30：确定性模块包再次并行构建两份，字节摘要一致；每份均为 62223
  字节，package SHA-256 为
  `c9941ac51d76aa1a5ff4030c5b15b32d3616d007b43a016cbc492091803703fd`，
  包内 `manifest.json` SHA-256 为
  `761989899a1649f52c1e2d10df39bef7b21dc0084357889f4ef34acf71d7c5e3`。
  结果与现有 release fragment/Catalog 输入完全一致；仓库内未保留 ZIP，未合并
  共享 Catalog，也未创建 tag、Release 或上传资产。
- 2026-07-30：发布层的声明式 network/tooling 阻断仍存在。当前 manifest、
  release fragment 和官方 Catalog Schema 的 `permissions` 只允许
  `local_state`，而安装包确有用户显式 `install`/`download-only` 后的固定来源
  HTTPS 副作用，不能诚实声明或由 Core 审核该能力。最小共享字段可新增一个固定
  枚举权限（建议 `network_explicit_acquire`），语义严格限定为 register/list/
  status/verify 零网络，仅本机显式获取动作可联网；不得接受 URL、命令、脚本、
  cwd、环境变量或 shell。
- 2026-07-30：当前 manifest 只有生命周期 `entrypoint`，没有已安装模块工具
  声明；ModuleManager/OfficialModuleService 也没有工具解析或调用接缝。最小
  tooling 契约建议为 manifest 中受 Schema 约束的
  `tools: [{"id": "voice-pack", "entrypoint": "backend.cli.main"}]`，只允许
  包内公开 Python callable，不允许命令行字符串、脚本或任意路径；Core 提供只读
  `resolve_module_tool(module_id, tool_id) -> ModuleToolDescriptor`，在当前已安装
  版本、包 containment 和 tree digest 复验后解析，以及 Core 自有
  `run_module_tool(module_id, tool_id, argv) -> int` 作无 shell 调用。根兼容
  shim 只调用该接口，模块缺失时返回稳定安装提示。官方 Catalog API 目前只负责
  catalog refresh 与模块 install/update/rollback，不能调度包内 CLI；PK-020
  workflow 只部署 Python/QQ/sidecar 依赖，同样不能解析已安装模块工具。因此
  动态面板/API 已可加载不等于兼容 CLI 已模块化，正式发布仍应等待 PK-000
  串行批准并装配这两个最小共享接缝。PK-213 保持“待集成”，不标记“已完成”。
- 2026-07-30：收口后的 PK-213 Python `compileall`、全部 13 个项目自有
  PowerShell 文件 AST、25 项任务文档门禁和 `git diff --check` 均通过；
  diff check 仅报告混合工作区既有 LF→CRLF 提示。两份系统临时构建产物在摘要
  取证后删除；未清理或改写任何项目工作树内容。
- 2026-07-30：根据 PK-000 的 19-builder 文件级独立构建证据复核
  `package_source`。显式发布源仍精确为 10 项：`backend/` 下 7 个固定 Python
  文件、`catalog/catalog.schema.json`、`dashboard/index.js` 和
  `manifest.json`；额外文件全部是先前语法检查/测试生成的
  `backend/__pycache__/*.pyc`，不是模块源码或发布资产，未加入发布 allowlist。
  构建器现只忽略命名符合标准 CPython cache tag、且 stem 能反向对应上述显式
  allowlist 中 Python 源文件的直接字节码缓存；仍先对目录和文件执行
  `lstat`/reparse/hardlink 门禁，任何未知 `.pyc`、未知源码或其他额外文件继续
  fail closed，未改成递归全收。
- 2026-07-30：新增永久回归先断言当前 `_source_files()` 精确等于 10 项
  allowlist，再以临时副本验证合规派生缓存不进入包，并注入
  `backend/unexpected.py`，确认稳定抛出
  `RuntimeError: package source file allowlist changed` 且目标 ZIP 不存在。
  PK-213 installable module 专项与原 13 项均通过。系统 Python 使用文件级
  import（不导入 FastAPI）在 `TemporaryDirectory` 连续构建两次，字节相同；
  ZIP 仍为 62223 字节，package SHA-256 仍为
  `c9941ac51d76aa1a5ff4030c5b15b32d3616d007b43a016cbc492091803703fd`，
  manifest SHA-256 仍为
  `761989899a1649f52c1e2d10df39bef7b21dc0084357889f4ef34acf71d7c5e3`，
  精确只含 10 项，因此 release fragment/Catalog 输入无需变更，也未生成或保留
  仓库内资产。最终两个变更文件 `py_compile`、24 项任务文档门禁和
  `git diff --check` 均通过；diff check 只报告混合工作区既有 LF→CRLF 提示。
- 2026-07-30：PK-010 已正式冻结 `network_download` 权限；此前记录的网络能力
  声明阻断据此关闭，tooling/已安装模块 CLI 调度仍是独立共享接缝。由于
  `voice_pack_distribution@1.0.0` 的同名 tag、asset、size 和摘要均属不可变
  发布身份，本轮不覆盖旧资产，将模块提升为 `1.0.1`，新 tag 为
  `module-voice-pack-distribution-v1.0.1`，新 asset 为
  `voice_pack_distribution-1.0.1.zip`。manifest、release fragment 与专属
  Catalog 输入统一声明 `permissions=["local_state","network_download"]`；
  未修改共享 manifest/官方 Catalog Schema 或真实官方 Catalog。
- 2026-07-30：`network_download` 只描述既有显式获取边界：register、启动、
  页面加载、list、status 和 verify 均不下载；只有本机用户精确确认
  `id@version` 后调用 install/download-only，才从受版本控制 catalog 的固定
  HTTPS URL 发起请求。catalog 使用 exact fields，拒绝任意 URL、headers、
  proxy、命令或脚本；逐跳重验 HTTPS/host，限制重定向、连接/读取/总超时和
  精确字节数，最终要求 SHA-256 匹配。生产 HTTP client 使用
  `trust_env=False`，下载内容只作为隔离 ZIP 数据接受安全审计和 PK-212 导入，
  不执行归档内任何内容，也不读取秘密。
- 2026-07-30：系统 Python 以文件级 import 在 `TemporaryDirectory` 对
  `1.0.1` 连续构建两次，两个 ZIP 字节完全一致并精确只含原 10 项；此前
  pycache 窄排除、未知文件 fail-closed 和临时输出根整改保持有效。新 ZIP 为
  62247 字节，package SHA-256 为
  `69c35f1610169271a06f3434fe16c6b8ac1253bbe1ca2251aa3916918b255ecf`，
  manifest SHA-256 为
  `e0dc2596259fb6dbcc309385282854e0aaa64d7ff8bcd644e3106b75d5f969a5`。
  构建只发生在系统临时目录并已自动清理；未联网、未生成仓库内 ZIP、未创建或
  覆盖 tag/Release、未上传资产。
- 2026-07-30：累计验证通过 PK-213 installable module 专项、原分发专项
  13/13、PK-212 Registry/安装包/Origin guard、PK-211 Provider/共享 Engine
  session、官方模块 Catalog 与 Core installable lifecycle；三个变更 Python
  测试/构建文件 `py_compile`、24 项任务文档门禁和 `git diff --check` 通过，
  diff check 仅有混合工作区既有 LF→CRLF 提示。全部网络夹具使用 fake
  downloader 或 `httpx.MockTransport`，没有真实网络、Registry、Engine、模型、
  音频、`.env`、个人状态、`node_modules` 或 `vendor` 访问。未改 README、
  TASKS、共享 API/dashboard/Catalog，PK-213 保持“待集成”且不标记“已完成”。

- 2026-07-26：完成预发布技术实现。新增严格 catalog v1 Schema/加载器；内置
  catalog 不含任何生产条目。新增逐跳 HTTPS host allowlist、重定向/阶段超时、
  流式精确字节/SHA、原子忽略缓存；ZIP 外层拒绝穿越、绝对/盘符、链接、
  重复/冲突、未声明/执行文件、数量/单文件/总展开量/压缩比异常。展开后只调用
  PK-212 manifest/逐文件校验和导入/启用/选择/verify，不维护第二套 Registry。
- 2026-07-26：根入口为 `voice-pack.bat` 和 `voice-pack-build.bat`，均从
  `%~dp0` 定位、复用 PK-020 Python 解析器和统一暂停语义。实现只读
  list/status/verify、可信 install/download-only、本机 ZIP/目录 import、select
  与确定性构建；目录标记 `local_unpublished`，ZIP 必须匹配 catalog 或用户提供
  精确 identity/SHA，源不删除不移动。Engine 缺失时安装/启用可成功但选择跳过，
  不调用 PK-211 acquire、9880 或系统安装器。
- 2026-07-26：构建器只接受显式 source/new ZIP/version/精确 confirmation，
  调用 PK-212 校验三个声明资产，要求 README/LICENSE/NOTICE，拒绝额外文件、
  链接、训练/缓存目录、秘密形态和绝对路径，固定排序、时间戳、权限并流式生成
  ZIP、`.zip.sha256`、`.release.json`；失败清理本次输出且不改源。
- 2026-07-26：隔离验证使用系统临时目录、9 个微型 fake 包/HTTPS 用例和
  `httpx.MockTransport`，覆盖成功下载/导入/启用、Engine 缺失、幂等复用、
  download-only 零 Registry、可信/恶意重定向、超时、错误确认/SHA、危险 ZIP、
  严格 catalog、确定性构建/秘密拒绝与本机目录源保留，9/9 通过。PK-212
  Registry、共享引擎 session、Origin guard、PK-211 Provider、模块 Catalog
  回归均通过；Windows Core 正常/不完整依赖/端口定向 3/3 和 BAT/AST 2/2 通过。
  未访问真实 Registry、Engine 登记、模型、音频、网络、9880、`.env`、个人状态
  或 `vendor/`。
- 2026-07-26：最终 Python 编译、四个相关 PowerShell AST、25 项任务文档门禁
  和 `git diff --check` 均通过；diff check 只有既有 LF→CRLF 提示。受支持
  Python 3.10–3.13、含空格/中文/非系统盘的真实 BAT/CLI 累计矩阵，以及 Registry
  保存失败/选择回滚的独立重放仍归首次 `PK-900 = PK-213`，本任务未用当前旧版
  迁移解释器冒充该矩阵。
- 2026-07-26：实现前公共接缝审计确认 PK-212 已有导入、启用、选择与脱敏列表，
  但缺少供 PK-213 `verify` 重验指定 `id@version` 运行副本的只读入口。PK-000
  批准最小增加 `VoicePackRegistryService.verify(pack_id, version)`：它只在
  PK-212 自身锁内复用既有 `_validate_entry` 并返回既有脱敏结构，不新增 HTTP
  API，不写 Registry/Engine，不改变 Schema、导入或选择规则；PK-213 不复制
  manifest/逐文件校验逻辑。
- 2026-07-26：PK-000 完成 PK-020 最终远端矩阵复核后重新放行。确认
  `TASKS.md` 中 PK-020、PK-211、PK-212 均为“已完成”，PK-213 入场依赖已满足；
  本任务正式改为“进行中”。继续冻结真实 Kei 权重、参考音频、Engine、本机
  Registry、`.env`、个人状态、缓存和 `vendor/`，本轮只使用 fake HTTP、微型虚构
  ZIP/资产和系统临时目录，不创建真实 URL、tag 或 Release。
- 2026-07-26：PK-000 完成任务登记与范围冻结。已确认 PK-211、PK-212 为
  “已完成”，PK-020 仍为“待集成”并缺少目标版本干净矩阵，因此 PK-213 暂不
  授权领取。当前未确认真实 Kei 资产分发权，未读取/扫描模型，未创建 catalog
  生产条目、URL、摘要、ZIP、tag 或 Release，未实现代码。
- 2026-07-26：本次独立领取按冻结门禁完成必读文档、分支/混合工作区、依赖状态
  与相关入口存在性预检。`TASKS.md` 和三份依赖任务记录一致：PK-211、PK-212
  已由 PK-000 最终标记“已完成”，但 PK-020 仍为“待集成”，等待 PK-900 补齐
  Python 3.11 x64、Node 22、PowerShell 7.4+ 目标版本矩阵，未满足 PK-213 的
  入场条件。本次保持 PK-213“待开始”，交回 PK-000；未修改 `TASKS.md`、README、
  架构、Catalog、PK-211/212 或任何实现，未运行安装、下载、网络、Engine、
  9880、LLM、QQ、ASR/TTS、测试或发布操作，未读取/扫描/移动/打包真实 Kei 资产，
  未创建 URL、摘要、ZIP、tag 或 Release，也未暂存、提交、推送或清理工作区。

## 完成文档门禁

任务进入“待集成”或“已完成”前必须全部勾选；不适用项也必须写明原因。

- [x] TASK_RECORD — 已记录实际命令、catalog、下载/构建事务、副作用、验证、
  分发权结论和遗留问题。
- [x] TASKS_BOARD — 已同步状态、P1 和 PK-020/211/212 依赖。
- [x] PUBLIC_README — 已同步真实可用命令、远程/离线流程、Engine 分离、失败
  语义和未发布限制；未发布前不得写成可用。
- [x] MODULE_CATALOG — 已登记 CLI/catalog 表面、进程边界、网络副作用、数据
  所有权、失败模式和当前无生产条目限制。
- [x] ARCHITECTURE_DOCS — 已同步分发层、PK-211/212 依赖、信任锚、事务和发布
  门禁。
- [x] LOCAL_README — 不适用：未改变本机绝对路径、解释器、端口、Engine 或
  Pack 登记；未修改忽略文件。
- [x] AGENT_RULES — 不适用：现有外部引擎、模型资产、秘密、远程脚本和 Git
  安全规则已完整覆盖，未新增跨任务长期政策。
- [x] VALIDATION — 已记录 fake/临时目录测试、本机可执行的 BAT/AST 定向检查、
  Python 编译、任务文档门禁和 `git diff --check`；当前累计结果与仍需独立
  PK-900 重放的边界见本文件最新工作记录。

## 独立对话启动提示

```text
领取 Project Kei 的 PK-213「Voice Pack 发布、远程获取与一键安装」。

开始前完整阅读 README.md、AGENTS.md、README.local.md（如存在）、TASKS.md、
tasks/PK-213-voice-pack-distribution.md、tasks/PK-020-windows-install.md、
tasks/PK-211-gpt-sovits-engine-provider.md、tasks/PK-212-voice-pack.md、
docs/architecture/windows-install.md、docs/architecture/voice-packs.md 和
docs/architecture/gpt-sovits-engine.md，并检查 git status 和实际相关代码。

先确认 PK-020、PK-211、PK-212 均已由 PK-000 标记“已完成”。当前登记时
PK-020 仍为“待集成”；若领取时尚未完成，只做存在性/状态预检并记录阻断，
不得把 PK-213 改为“进行中”或修改实现。依赖全部满足后再领取任务。

只实现 PK-213 分发层：受版本控制的可信 catalog Schema/加载器、固定来源下载、
包级大小/SHA 校验、安全 ZIP 外层、调用 PK-212 的导入/启用/选择、根
voice-pack.bat/voice-pack-build.bat、离线导入、download-only、verify、
确定性构建器和对应测试。不得复制或改写 PK-211 Engine 获取/Provider，也不得
复制或放宽 PK-212 Schema/Registry/原子选择规则；需要公共接缝时先记录并交回
PK-000。

当前没有真实 Kei 权重/参考音频分发授权。本轮只能使用 fake HTTP、微型虚构
checkpoint/WAV/ZIP、fake Engine 和系统临时目录。不得扫描磁盘、读取/摘要/移动/
打包真实 Kei 资产，不得编造生产 URL/大小/SHA，不得创建 tag、GitHub Release
或上传任何资产，不得执行真实网络、Engine、9880、LLM、QQ、ASR/TTS。

严格覆盖可信来源、逐跳重定向、流式大小、SHA、ZIP 穿越/链接/reparse/bomb/
额外文件/执行文件、原子失败、重复安装、版本并存、Engine 缺失、选择回滚、
空格/中文/非系统盘和错误脱敏。不得读取或修改真实 Registry、Engine 登记、
.env、个人状态、缓存、模型、音频、vendor、现有虚拟环境或 node_modules。

完成代码和累计验证后更新任务工作记录、README、架构、模块 Catalog 和八项门禁，
把 PK-213 置为“待集成”并交给独立 PK-900 预发布技术验收。不要自行标记
“已完成”，不要创建真实 Release，不要暂存、提交、推送或清理工作区。
```

## 首次预发布技术复核退回（2026-07-26）

- PK-900 重跑 PK-213 专项 9/9，并确认 PK-212 Registry、共享 Engine session、
  Origin guard、PK-211 Provider 和模块 Catalog 回归通过；内置 catalog 仍为空，
  相关差异没有真实权重、参考音频、生产 URL、秘密或本机绝对路径。
- 阻断一为可信 Release 的同版本内容身份未闭合。独立临时夹具先
  `download-only` 缓存可信 `fake-kei@1.0.0`，再导入同一 `id@version` 但 GPT
  资产和 manifest 摘要均不同的 `local_unpublished` Pack，随后执行可信
  `install`。实现只检查“可信 ZIP 缓存有效 + Registry 中该 key 自身可验证”，
  错误返回 `already_installed`，未证明已安装 Pack 与可信 Release 是同一内容。
  这违反“同版本仅同摘要幂等；摘要冲突拒绝覆盖”验收标准。
- 阻断二为发布构建器未拒绝硬链接。独立临时夹具把声明的 GPT checkpoint
  创建为指向源目录外微型假文件的硬链接（`st_nlink=2`），同步合法大小/SHA 后，
  `build_release()` 返回 `built` 并生成 ZIP。当前 `_source_files()` 只检查
  `is_symlink()`，没有拒绝硬链接，也没有完整覆盖 Windows reparse/junction；
  这违反正式包不得包含硬链接/重解析点及构建器不得读取源外资产的门禁。
- 最小整改归 PK-213：已安装同 key 的快速幂等返回前，必须通过 PK-212 的只读
  公共接缝证明候选可信 Release manifest/逐资产摘要与 Registry 记录完全一致；
  无法证明或来源冲突时返回稳定 conflict，不能直接接受。不得由 PK-213 读取
  Registry 私有文件或复制 manifest 规则；如需新增只读 fingerprint/compare
  接缝，先记录精确签名并由 PK-000 确认。
- 构建器必须对 source root、每个路径组件和每个文件执行不跟随链接的检查，
  拒绝 symlink、hardlink（普通文件 `st_nlink != 1`）及 Windows
  `FILE_ATTRIBUTE_REPARSE_POINT`；输出 ZIP 和 sidecar 还应确认位于 source root
  之外且目标/父链不存在链接或 reparse。补充独立临时 hardlink、junction/
  reparse、源外读取 tripwire 和同 key 内容冲突永久测试。
- PK-213 退回“进行中”；本轮 PK-900 保持“进行中”。即使上述技术阻断修复并
  通过首次验收，真实分发权、真实构建、Release/catalog 和发布后复核仍未发生，
  因此不得把 PK-213 标为“已完成”或声称 `kei@1.0.0` 已可远程安装。

## 首次预发布技术复核整改交回（2026-07-26）

- 依照 PK-000 的最小授权，在
  `VoicePackRegistryService.compare_content(pack_id, version, candidate_root)`
  增加无 HTTP、无写入的 PK-212 只读 service 接缝。它在 PK-212 自身锁内先以
  既有 `_validate_entry` 重验已安装 manifest/资产，再用既有
  `validate_package_tree`、`load_manifest`、`validate_assets` 验证候选；只比较
  规范化 manifest 内容指纹并返回 `id/version/equivalent`，不返回路径，不改变
  Schema、Registry 格式、Origin、导入/选择或原子切换契约，也未新增 API。
- PK-213 的同 key 快速路径现在先展开已验证 catalog cache，并调用上述公开接缝。
  只有内容身份完全一致才返回 `already_installed`；内容不同、候选/已安装校验
  失败或其他无法证明情形统一返回 `voice_pack_install_conflict`。永久回归先
  `download-only` 缓存可信 fake Release，再导入同 key、不同 GPT 字节/manifest
  SHA 的 `local_unpublished` Pack 并设为活动，确认 conflict 前后临时 Registry、
  runtime、cache、活动 Pack 均逐项不变且网络请求仍只有一次；真正相同内容继续
  幂等。
- 构建器把 fail-closed 元数据门禁前移到任何 manifest/资产内容 I/O 之前：
  source root 及父链、逐层目录、每个文件和输出父链均用可注入 `lstat`/Windows
  文件属性检查；拒绝 symlink、普通文件 `st_nlink != 1`、junction/reparse 和
  非普通文件。ZIP、`.zip.sha256`、`.release.json` 必须位于 source root 外且
  目标未使用；创建输出目录后会再次检查父链与目标。临时 `os.link` 源外资产
  回归通过，`load_manifest`/`_hash_file` tripwire 均为零调用；另有真实或注入
  symlink、注入 reparse 目录/输出父链及 source 内输出永久回归。
- 累计验证只使用系统临时目录、微型虚构 checkpoint/WAV/ZIP、
  `httpx.MockTransport` 和 fake Engine：PK-213 专项 13/13；PK-212 Registry
  （含只读比较相同/冲突/零写入/无路径）、共享 Engine session、Origin guard、
  PK-211 Provider 与 feature Catalog 全部通过；PK-020 Windows 安装 15/15
  （224.880 秒，`protected_rejected=33 allowed_io_calls=422`）及 Windows CI
  copy 7/7 通过；相关 Python `compileall` 与四个 PowerShell 入口 AST 4/4
  通过；状态同步后的任务文档门禁通过 24 个 gated tasks，`git diff --check`
  退出 0，只有混合工作区既有 LF→CRLF 提示。没有访问真实网络、
  Registry/runtime、Engine 登记、9880、模型、音频、
  `.env`、个人状态、`node_modules` 或 `vendor/`，也没有启动 API、浏览器、
  QQ、LLM、ASR/TTS 或安装器。
- PK-213 已恢复“待集成”，`TASKS.md` 同步；PK-900 保持“进行中”，应重新执行
  两条原始逆向夹具和全部累计门禁。真实 Kei 分发授权、生产 URL/大小/SHA、
  真实构建、tag/Release/上传及发布后复核仍未发生，不能把 PK-213 标成“已完成”。

## 真实 Kei Pack 授权与发布候选（2026-08-01）

- 用户明确声明拥有本包 GPT/SoVITS 权重与参考音频的公开再分发权，并授权把
  manifest 的 `redistribution` 改为 `allowed`、采用
  `Project Kei Voice Pack Non-Commercial Redistribution License 1.0`，以及公开
  上传完整包。许可允许非商用下载、使用和原样再分发完整包；要求保留全部许可与
  NOTICE，禁止商业使用、单独资产分发、二次训练、冒充和违法用途。
- PK-000 只处理用户明确提供的桌面 ZIP。原包只读审计为 7 个文件、单一根目录、
  无穿越/重复/链接/脚本/可执行/加密内容；manifest Schema v1 与三项声明资产的
  字节数、SHA-256 均通过 PK-212 校验。原 ZIP 保留不覆盖。
- 在系统临时发布源中同步修改 `voice-pack.json`、README、LICENSE 和 NOTICE 后，
  PK-213 正式 builder 重新执行路径/链接/reparse/硬链接、公开文本和逐资产摘要
  门禁，生成规范候选：`kei-voice-pack-1.0.0.zip`，303635280 字节，SHA-256
  `bc679c8ab97d5be44d959506c841e642cda19f8215ba3aede07e18d91807c83a`；同时生成
  `.zip.sha256` 与 `.release.json`。三个文件另存到用户桌面独立发布目录，未放入
  Git 工作树。
- 生产 Catalog 条目仍须等待实际 Git commit/release tag 的固定 revision 和 GitHub
  Release URL 后再写入；在 Release 与发布后 PK-900 复核完成前，不能声称远程安装
  已可用，也不能把 PK-213 标为“已完成”。

## 私有预发布记录（2026-08-01）

- 精确提交 `48e06b09aa5decde3ba34d096b851416b8b4a782` 的 Windows 安装矩阵
  `30648742199` 已在 Python 3.10/3.11/3.12/3.13 x64 全绿；Python 3.11 同时
  覆盖 Node 22、QQ `npm ci`、Node 测试与脚本检查，PS 5.1/7.4、Ruff、完整
  离线 pytest、文档门禁均通过。
- 已在当前私有仓库创建固定 Release `voice-pack-kei-v1.0.0`，上传规范 ZIP、
  `.zip.sha256` 和 `.release.json` 三个资产。GitHub 返回的 ZIP 大小为
  303635280 字节，服务端 digest 为
  `sha256:bc679c8ab97d5be44d959506c841e642cda19f8215ba3aede07e18d91807c83a`，
  与本机构建结果一致。
- 仓库经 GitHub API 确认为 `PRIVATE`，匿名 HEAD 与 Range GET 均返回 404；下载器
  按安全契约不接收 GitHub Token。因此本轮没有写入生产 `kei-1.0.0.json`，README
  明确授权协作者通过 GitHub 下载后离线导入，普通用户远程安装须等待仓库公开及
  发布后复核。模型、参考音频和 sidecar 只作为私有 Release 资产，未放入 Git 树。
