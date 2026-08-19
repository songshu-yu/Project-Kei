# Project Kei 语音公共契约与编排

## 边界与依赖

PK-210 是主 API 内的 `voice` 模块，只拥有语音 Provider 协议、请求编排、HTTP 兼容、阶段错误和单次请求的临时文件生命周期。依赖方向固定为：

```text
multipart audio
  -> SpeechToTextProvider
  -> PK-200 ConversationService adapter
  -> TextToSpeechProvider + VoicePackResolver
  -> controlled WAV publication
```

文字回复只能由注入的 PK-200 `ConversationService.chat()` 产生；voice 不读取 LLM profile、角色提示或 history。GPT-SoVITS 上游来源、版本和获取归 PK-211，权重、参考音频、Voice Pack 注册表和切换归 PK-212。PK-210 不扫描引擎目录，不解析或移动模型资产，也不新增进程或端口。

`voice@1.0.9` 现作为可选 `in_process` 包交付，manifest 将 `conversation` 声明为
强依赖，将 `calendar` 声明为可选依赖。Core 不安装 voice 时不装配语音路由或动态
面板，模块中心显示未安装状态，而不是对 8010/9880 发起健康检查后显示连接失败。
安装、启停、更新、回滚和卸载遵循 PK-010 的重启语义。

## 模块结构

- `models.py`：不含可公开本机路径的请求、结果、健康、能力和 `VoicePackRef`；Pack 的 `handle` 只在进程内作为不透明值传递。
- `contracts.py`：可注入、可替换的 `SpeechToTextProvider`、`ConversationProvider`、`TextToSpeechProvider`、`VoicePackResolver` 与 `UtteranceEncoder`。
- `service.py`：ASR → conversation → TTS 的语音对话编排，以及既有最终文字 → TTS → 统一 PCM → 单次编码的隔离编排；统一处理阶段超时、文字降级、取消和关闭。
- `media.py`：分段顺序校验、固定 PCM 变换、完整 utterance 合并与固定输出 profile/时长校验。
- `silk_encoder.py`：固定 `silk-python==0.2.8` 的可选生产适配器；不携带或安装上游源码、wheel、二进制。
- `storage.py`：请求 UUID 隔离的暂存目录与受控 `.wav` 发布；只清理当前请求创建的内容。
- `router.py`：同时注册 `/api/v1/voice/*` 与 `/voice/*`，限制上传类型、大小和分块读取。
- `control_router.py`：只把注入的 runtime-control duck provider 暴露为受保护的
  版本化状态/显式启动接口；不拥有启动实现。
- `providers/`：8010 HTTP 适配、PK-200 service 适配和 9880 的 PK-211 `gpt_sovits/` Provider。PK-212 已用 `voice_packs/` 的本机注册表替换临时静态引用；编排仍只解析 PK-210 `VoicePackRef`，不读取资产或注册表。
- `legacy_pipeline.py`：仅保留既有 Python 导入和语音业务意图辅助函数；生产语音 HTTP 不经过它。
- `module.py`：`backend.register(app)` 的包入口；从 composition state 延迟取得
  PK-200 与可选 Provider，拒绝重复路由，并把 calendar 公共 registry 暴露给
  PK-190 包。
- `package_builder.py`、`package_source/`、`release/`：显式 allowlist 的确定性
  ZIP、动态面板和公开 Release/Catalog 交接元数据。

`server/services/asr_client.py`、`tts_client.py`、`voice_pipeline.py` 只保留兼容导出，不再拥有实现。

## 可安装包与跨包 Provider

`backend.register(app)` 只消费公共装配状态。conversation 使用延迟 adapter，因此
ModuleManager 的实际描述符顺序不会让 voice 在依赖包稍后注册时损坏；manifest
强依赖仍保证缺失或停用 conversation 时不能启用 voice。ASR、TTS 与 Voice Pack
Resolver 是可选运行时 Provider，不作为引擎或资产包依赖；缺失时继续遵守下文的
ASR 明确失败和 TTS 文字降级。

`voice_pack_registry` 的 manifest 强依赖 voice，所以 PK-210 不捕获注册瞬间的
`app.state.voice_pack_resolver`。voice 注册后发布可链式
`voice_pack_resolver_consumer`，并让同一 `VoiceService` 始终持有
`DynamicVoicePackResolver`。consumer 只接受同时提供 health、capabilities、
resolve、cancel 与 close 的结构化候选；合法候选或显式 `None` 在 app-scoped
锁内原子绑定/解绑，非法对象保持旧绑定。已有 consumer 会先被安全调用；voice
卸载时仅恢复自己直接替换的前置 consumer，若已有后装 consumer 则保持其链条并
只停用自己的代理。

每次 resolver 操作先取得单一候选快照；`resolve_active_pack()` 返回后，请求把
该 `VoicePackRef` 传入 TTS。因此并发 bind 不会把一次请求的 Pack 从中途切换，
后续请求才观察新 resolver；GPT-SoVITS 内部仍由 PK-211 的共享引擎会话锁保证
权重切换与合成边界。PK-210 不导入 PK-212，也不拥有 registry 或 Pack 内容。

calendar 兼容意图不再静态导入 `features.calendar.service`。稳定公共层
`core.calendar_contracts` 提供线程安全、进程内且至多单 provider 的
`CalendarSummaryProviderRegistry`。PK-190 包在 `register`/`unregister` 中发布和
解除公开 summary provider；voice 只查询 registry。未安装、停用、解除、异常或
并发切换时，registry 返回新建的
`available=false/error_code=calendar_unavailable/message=""/skills=[]`，不查找或
读取 calendar 状态文件，也不让语音兼容管线崩溃。

确定性包仅复制 `control_router/contracts/errors/models/module/router/service/storage/text`、
包入口和动态面板。包内不存在 GPT-SoVITS 上游、ASR 模型、权重、参考音频、
Voice Pack 内容、生成输出、`.env`、本机路径、`vendor/` 或脚本。卸载默认保留
模块数据；本机 Provider/模型登记、外部资产和用户音频不属于 voice 包，不能由
卸载或 purge 隐式删除。

## HTTP 与流式协议

同步、流式和音频读取分别由以下新旧路径共用同一 `VoiceService`：

| 版本化 | 兼容 |
|---|---|
| `POST /api/v1/voice/chat` | `POST /voice/chat` |
| `POST /api/v1/voice/chat/stream` | `POST /voice/chat/stream` |
| `GET /api/v1/voice/audio/{filename}` | `GET /voice/audio/{filename}` |
| `GET /api/v1/voice/health` | `GET /voice/health` |

另有仅版本化的 `POST /api/v1/voice/synthesize`，没有 `/voice/synthesize` legacy
别名。请求精确为 `{"purpose":"qq_reply","text":"..."}`；它消费 PK-200 已经生成的
最终回复，只调用一次 TTS，不调用 ASR、conversation、LLM、history、长期记忆或
Collector。`purpose` 不能由调用者扩展，文字最多 1500 个 Unicode 字符；请求不能携带
profile、codec、bitrate、命令、路径、URL、模型或 Voice Pack 参数。

该入口固定输出 profile `qq_c2c_voice_v1`。Provider 可在一次调用内返回有序短句段，
但所有段必须携带与输入完全一致、连续且无重复的 `segment_id/sequence`。PK-210 将受控
WAV 解码为 24 kHz/mono/signed 16-bit PCM，执行有界静音裁剪、响度/峰值归一与 5 ms
淡入淡出，随后只合并一次；缺段、重复、乱序、解码错误或超过 60 秒均 fail closed。
独立 WAV、MP3、AAC、Opus、Ogg 或 Silk 文件不能靠字节拼接成为 final utterance。

合并 PCM 只交给注入的 `UtteranceEncoder` 一次。成功必须是单个
`Content-Type: audio/silk` 响应，`X-Kei-Audio-Final: true`，不超过 8 MiB；响应只带
固定 profile 与不含身份、文字、路径或模型信息的随机 `utterance_id`。缺少或未就绪的
受控 Silk encoder 返回 `encoding_unavailable`，绝不回退 WAV 给 QQ。恶意上游错误、
超时、编码失败和超限只映射为稳定 code，不回显正文或路径。

受控无 Origin sidecar 可提交严格 16–80 字符 `Idempotency-Key`；浏览器 Origin 不能
提交持久 key。同 key/同文字并发最多执行一次 TTS 和一次最终编码，失败也在短 TTL 内
复用而不隐藏重试；同 key 换文字返回 `idempotency_conflict`。统一 PCM 随同一进程内
utterance 结果短暂保留，供 QQ/Pi 从同一生成派生或消费，消费者不得再次调用 TTS。
中间及最终字节全部有界驻留内存，不创建临时文件；断开、取消、失败、超时和 shutdown
会取消最后一个活动所有者并释放缓存/Provider 引用。

同步结果保留 `user_text`、`assistant_text`、`emotion`、`audio_path(s)`、`audio_base64`、`timestamp`、`timings_ms` 和 ASR 字段，并增加 `audio_available`、`mode`、`degraded` 与结构化 `errors`。`audio_path(s)` 现在是对应命名空间下的受控 URL，不是本机路径。

NDJSON 成功顺序为一个 `reply`、零到多个 `audio_part`、一个 `done`。ASR 或 conversation 的致命失败以一个已清洗的 `error` 终止。TTS/Pack 缺失、超时或失败保留已经取得的文字，以 `done.mode=text_only`、`degraded=true` 和结构化错误结束，不伪造音频。

### 本地 readiness 与 QQ 能力边界

`GET /api/v1/voice/health` 只读本地语音能力：TTS engine、活动 Voice Pack 和
`qq_c2c_voice_v1` encoder readiness。它不读取 QQ Secret，不因存在 AppID/Secret 推断
媒体权限，也不通过真实消息做能力探测。QQ 协议层具备 C2C 富媒体上传/发送能力，与
Project Kei 当前 Node sidecar 是否实现该链路、具体 Bot 是否获准该能力是三件独立的事。

PK-140 已实现受控 C2C 媒体上传，但整体 QQ voice 仍必须由双重 readiness 门禁。PK-140 合并 readiness
时只使用非秘密枚举 `qq_media_upload_capability=unknown|available|unavailable|denied`；
默认 `unknown` 并 fail closed。权限状态只可来自官方无副作用 capability 接口（若存在）
或 fake/sandbox，不发送真实用户消息，也不回显权限正文或账号标识。只有本地
`audio/silk` profile ready 且该枚举明确为 `available` 时，UI 才能允许用户开启；纯文字
功能始终不受影响。

## 上传、错误和生命周期

- 上传只接受批准的音频 MIME 与扩展名，默认最大 16 MiB；读取采用 64 KiB 上限分块并在超过限制的第一个字节停止。
- ASR 缺失、失败、超时、空结果或超长结果均不会调用 PK-200；conversation 失败不会调用 TTS。
- Provider 公开健康、能力、默认超时、操作、取消和关闭；上游异常映射为有限的 `stage/code/message/retryable`，不返回响应正文、异常链、请求头、音频字节或本机路径。
- 对共享 9880 实例，PK-211 在每次合成持有完整引擎会话，并在会话内重新确认 PK-212 的活动 Pack；Pack 选择和活动 ID 提交使用同一会话，因此不同请求不能在一次合成期间改写权重。
- 合成先在内存完成全部分段，再进入请求专属暂存目录并原子发布。任一分段失败不会留下半成品。
- 正常同步/完整流仅保留已发布的受控输出；暂存目录始终清理。失败、取消、客户端断开或流生成器提前关闭时，当前请求已发布的文件也会删除，不影响并发请求或既有文件。
- 已发布输出继续位于忽略的 `server/output/voice_replies/`，遵循现有音频保留清理；请求暂存位于忽略的 `server/output/.voice_tmp/`。
- `backend.unregister(app)` 为幂等 async 生命周期入口。注册时创建的
  `VoiceService` 以独立 owner state 记录；unregister 只 await 该实例，即使
  `app.state.voice_service` 后来被替换也不会关闭或删除替换对象。close 先把
  service 的四个 Provider 引用置空，再逐个 await 原快照，单个关闭异常被安全
  隔离。成功关闭后才解除 PK-210 resolver consumer/binding、service owner 和
  模块标记；composition 注入的 Provider state 与用户音频始终保留。通用 loader
  的 async 逆序卸载因此会真实等待关闭完成，重复 shutdown 不会重复 close。

## 进程与兼容

主 API 仍为 8000，ASR 仍为 8010，TTS 仍为 9880；根 `start.bat` 默认只启动 Core，只有显式 `--profile voice|all` 才尝试语音进程。`server/start_all_services.bat`、`start_asr.bat` 与 `start_gptsovits.bat` 的名称继续兼容并委托统一解析器。ASR 优先使用显式 `ASR_MODEL_PATH`，未配置时只检查项目内固定的 `server/models/asr/medium`、`small`，并始终强制本地文件模式；不扫描磁盘或下载模型。GPT-SoVITS 启动器只读取忽略的本机登记与项目固定描述，不再内置角色权重、参考音频或公开绝对路径。模块导入和主 API 应用启动不会连接或获取 Provider，只有显式语音调用/health 访问已有 9880；受控获取必须由用户独立触发。完整边界见 [GPT-SoVITS 外部引擎 Provider 与受控获取](gpt-sovits-engine.md)。

安装 `voice@1.0.9` 后，控制台可读取
`GET /api/v1/voice-control/status`，并在用户明确
点击后调用 `POST /api/v1/voice-control/asr/start` 或
`POST /api/v1/voice-control/gpt-sovits/start`。该 runtime-control 只拥有固定
BAT 的脱敏就绪检查、并发去重和新控制台窗口创建，不拥有 Provider 业务、引擎
获取或模型资产。写接口要求 loopback 与可信控制台 Origin，拒绝非空请求体；
前端不能传入路径、命令、参数或环境变量。

ASR 模型缺失时，动态面板还会读取
`GET /api/v1/voice-control/asr/model-directory/status`；只有用户点击“选择 ASR
模型目录”才发送空的
`POST /api/v1/voice-control/asr/model-directory/select`。普通浏览器目录输入不能
提供可信服务器绝对路径，因此这里由本机 provider 打开一次 Windows 系统选择器，
HTTP 不接受任何路径。provider 只验证被选中的单一目录和必要模型文件，拒绝重解析
点，不扫描、下载、复制或移动模型；验证通过后原子保存非秘密本机配置，失败或取消
保持旧配置。公开响应最多显示安全目录名，绝对路径只在启动固定 ASR BAT 的子进程
环境中使用。

可安装包自身不构造上述固定启动实现，只在注册时动态读取 composition 注入的
`app.state.voice_runtime_control_provider`。公共 duck contract 只有同步
`status()`、`start(target)`、`stop(target)`、`asr_model_selection_status()` 与
`select_asr_model_directory()`；target 只能由路由固定为 `asr` 或
`gpt-sovits`。GET/status 在 provider 缺失、结构错误或异常时仍以 200 返回两个
脱敏 `unavailable` 项，零写入、零进程、零网络；POST 在缺 provider 时明确 503，
provider 异常时返回固定错误，响应只保留 allowlist 字段。模块加载、面板挂载、
刷新、折叠和普通 health 都不会调用 `start` 或 `stop`。动态面板不使用全局
`fetch`。停止请求只允许当前 Core 所启动并持有的固定进程组，二次确认后发送空 body；
外部实例只返回 `can_stop=false`，不允许通过 PID、端口、路径或命令扩大控制范围。

活动声音现由 PK-212 的稳定 Voice Pack ID 决定。解析、导入、原子切换、失败回滚、脱敏 API、本机资产绑定和默认不删除语义见 [Voice Pack Schema、注册表与切换](voice-packs.md)；PK-210 的同步/流式编排和临时音频生命周期没有因此改变。

## 生产 Silk encoder 接缝

voice 包拥有固定的 `SilkPythonUtteranceEncoder` 适配器，PK-020 继续拥有依赖安装 profile
和共享 composition root。适配器只接受统一的 24 kHz/mono/s16le PCM，只输出
`qq_c2c_voice_v1`/`audio/silk`。它以固定参数在隔离子进程调用本地固定版本
`silk-python==0.2.8`；请求不能提供 command、path、codec、bitrate、URL 或下载源。
health 零副作用，缺少或不兼容依赖时 Core 保持运行，合成 fail closed。

集成接缝保持显式：PK-020 需要为 CPython 3.10–3.13 Windows x64 新增逐 wheel hash 锁定的
voice-media 依赖，并只加入 `voice`/`full`；doctor 只检查 version/import/capability。
composition root 需要固定创建适配器并注入 `app.state.voice_utterance_encoder`，不得静默
换用未固定实现。两步完成前，本地 Silk readiness 为 false，QQ 保持纯文本。

synthesize 成功响应包含 `X-Kei-Audio-Duration-Ms`，它是已验证逻辑 PCM 时长毫秒数的
向上取整。零、NaN、infinity 或范围 1..60000 之外的值在发布二进制响应前失败。
