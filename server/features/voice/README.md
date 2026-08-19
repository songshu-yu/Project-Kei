# Voice module

`features/voice/` 是 PK-210 的开发源码；`package_builder.py` 以显式 allowlist
生成 `voice@1.0.9` 的确定性 `in_process` 包。包入口为
`backend.register(app)`，动态面板位于 `package_source/dashboard/index.js`。

## 运行时注入

包不创建 Provider、不下载资产，也不读取 `.env`。装配层通过 `app.state` 提供：

- `voice_conversation_provider`，或 PK-200 的公开 `conversation_service`；
- 可选 `voice_asr_provider`；
- 可选 `voice_tts_provider`；
- 可选 `voice_pack_resolver`；
- 可选 `voice_utterance_encoder`，只接受固定 `qq_c2c_voice_v1` PCM 编码请求；
- 可选 `voice_runtime_control_provider`，公开同步 `status()`、
  `start("asr"|"gpt-sovits")`、`stop("asr"|"gpt-sovits")`、脱敏的
  `asr_model_selection_status()` 与仅由
  显式点击触发的 `select_asr_model_directory()`；
- 可选 `voice_data_root`，默认使用模块本机数据 namespace。

manifest 将 `conversation` 声明为强依赖。voice 的注册使用延迟适配，避免依赖包
装载顺序影响启动；请求发生时若 PK-200 provider 实际不可用，返回结构化错误。
ASR 缺失会在提交文字前失败；TTS/Voice Pack 缺失会保留文字并明确
`mode=text_only`。

## 已生成文字的单次合成

`POST /api/v1/voice/synthesize` 只接受严格 JSON
`{"purpose":"qq_reply","text":"..."}`。`purpose` 当前只有 `qq_reply`，文字去除
首尾空白后必须非空、最多 1500 个 Unicode 字符且不能含控制字符。该入口不调用
ASR、PK-200 conversation、LLM、history、长期记忆或 Collector；一次请求至多调用
一次 TTS 和一次最终 encoder，不注册 `/voice/synthesize` 兼容入口。

TTS 可返回带连续 `segment_id/sequence` 的短句 WAV。PK-210 将每段有界解码为
24 kHz、单声道、signed 16-bit PCM，执行受控静音裁剪、RMS/峰值归一和 5 ms
淡入淡出，再按原输入顺序合成一个逻辑 utterance。缺段、重复、乱序、格式错误或
超过 60 秒均整体失败；多个 WAV 或压缩容器绝不直接拼接。最终只允许固定
`qq_c2c_voice_v1`，由注入的 `UtteranceEncoder` 编码一次，成功响应固定为
`audio/silk`、`final=true` 且不超过 8 MiB，不返回 WAV、路径、URL、base64、模型、
Voice Pack 内容、提示词或临时文件名。没有受控 encoder 时返回
`encoding_unavailable`，由调用方保留纯文字。

受控 sidecar 可通过 16–80 字符的有限 `Idempotency-Key` 合并同 key 并发请求；带
浏览器 Origin 的请求不能提交持久 key。相同 key 与相同文字在短 TTL 内共享一次 TTS、
一次编码及同一进程内 PCM 产物，失败结果也不会隐藏重试；冲突文字固定拒绝。该接口的
中间 WAV/PCM/结果仅有界保存在内存中，最后一个等待者断开、取消、超时、失败或模块关闭
时停止工作并释放引用，不写输出目录、个人状态或 sidecar runtime。

`GET /api/v1/voice/health` 的 `synthesis_profiles.qq_c2c_voice_v1` 只报告本机 TTS
engine、活动 Voice Pack 和 encoder 是否就绪，不读取 QQ AppID/Secret，不推断 Bot
媒体权限，也不发送消息探测。QQ 协议支持 C2C 富媒体不等于当前 Node sidecar 已完成
上传链路；PK-140 完成前整体 QQ voice 必须保持 unavailable。PK-140 后续只可合并非秘密
`qq_media_upload_capability=unknown|available|unavailable|denied`，`unknown` 默认
fail closed；只有本地 Silk profile ready 且该能力明确 `available` 时才能允许开启。

Voice Pack Registry 强依赖 voice，因此 voice 注册时还会发布可链式
`voice_pack_resolver_consumer`。`VoiceService` 永久持有 PK-210 自己的动态
resolver 代理；PK-212 后装时只需把满足公共结构契约的 service 交给 consumer，
无需导入或改写 voice。绑定、解绑和并发替换均为 app-scoped 原子操作；正在执行的
请求继续使用其已取得的 resolver/Pack 快照，新请求使用新绑定。非法候选不会覆盖
当前有效 resolver。

## 显式运行时控制

manifest 同时声明 `/api/v1/voice` 与 `/api/v1/voice-control`。包注册七个受
loopback 与可信控制台 Origin 保护的控制入口：

- `GET /api/v1/voice-control/status`；
- `POST /api/v1/voice-control/asr/start`；
- `POST /api/v1/voice-control/asr/start-background`；
- `POST /api/v1/voice-control/asr/stop`；
- `GET /api/v1/voice-control/asr/model-directory/status`；
- `POST /api/v1/voice-control/asr/model-directory/select`；
- `POST /api/v1/voice-control/gpt-sovits/start`；
- `POST /api/v1/voice-control/gpt-sovits/start-background`；
- `POST /api/v1/voice-control/gpt-sovits/stop`。

注册、页面加载、刷新、折叠和 health 查询都不会启动或关闭进程。顶部配置就绪卡
只调用两个 `start-background` 固定入口，以隐藏窗口启动日常服务；语音模块内原有
`start` 按钮明确保留为会打开控制台窗口的调试入口。两种模式都由同一 provider
持有进程句柄，并只允许关闭自己启动的实例。动态面板只通过
`context.request` 读取脱敏状态；只有用户明确点击某一个按钮才向对应固定 target
发送一次空 POST。关闭按钮还要求 `can_stop=true` 并经过二次确认；外部启动实例只读
显示，不能按 PID、端口、路径或命令关闭。包不包含 `VoiceRuntimeControlService`、BAT、路径、命令、安装器
或下载逻辑，只把 composition 注入的公共 duck provider 适配为 HTTP。provider
缺失或状态异常时 GET 仍返回两个固定 `unavailable` 状态，按钮保持禁用；启动
异常返回稳定错误，不回显异常、命令或本机路径。

ASR 目录选择不使用浏览器 directory input，也不接受路径、URL、命令或参数。只有
loopback、精确可信 Origin 的空 POST 才会让本机 provider 打开一次 Windows 系统
目录对话框。取消零写入；选中后只检查该目录的 `model.bin`、`config.json` 与
tokenizer/vocabulary 必要文件、可读性和重解析点，再原子保存忽略的本机配置。
验证或保存失败时旧配置不变。HTTP 只返回 configured/state 与安全目录名，不返回
绝对路径；启动固定 ASR BAT 时 provider 才在子进程环境中使用已验证路径。

## Calendar 可选接缝

兼容 `legacy_pipeline.py` 只调用 `core.calendar_contracts` 的进程内
`CalendarSummaryProviderRegistry`，不导入 `features.calendar`，也不读取 calendar
状态文件。PK-190 包负责 provider 的注册和解除；缺失、停用或 provider 失败时返回
固定的 empty/unavailable 摘要。

## 异步关闭

`backend.unregister(app)` 是幂等 async 入口。它只 await 注册时由 PK-210 创建并
记录的同一 `VoiceService`，不会因为其他模块后来替换
`app.state.voice_service` 而关闭替换对象。`VoiceService.close()` 先原子进入
closed 状态并解除 ASR/conversation/TTS/Voice Pack 引用，再逐个 await Provider
close；单个 Provider 异常不会阻止其余关闭或 app-state 清理。

通用 loader 的 async 逆序卸载会等待 close 完成后再移除路由和模块入口。重复
unregister/unload 不会重复关闭 Provider。清理只移除 PK-210 自己发布的
service、resolver consumer/binding 和模块标记，不删除 composition 注入的
Provider state、外部登记、已发布用户音频或其他模块后来安装的接缝。

## 包与数据边界

ZIP 只包含语音协议、编排、版本化/legacy 路由、受限 runtime-control 适配、
请求级临时音频管理和动态状态
面板。它不包含 ASR 模型、GPT-SoVITS、安装器、权重、参考音频、Voice Pack 内容、
生成输出、本机路径、`.env`、`vendor/` 或脚本。卸载只移除程序包，外部 Provider
登记、模型资产和用户音频不属于 voice 包的数据清除范围。

## QQ Silk 生产适配器与时长头

`SilkPythonUtteranceEncoder` 是 `qq_c2c_voice_v1` 的受控可选生产适配器。它只接受
24 kHz、单声道、signed 16-bit PCM，使用固定参数在隔离的短生命周期 Python 子进程中
调用 `silk-python==0.2.8`，只接受带 Tencent SILK 头的有界 `audio/silk` 输出。适配器
不接受客户端 command、path、URL、codec 或 bitrate，不回显 stderr；超时、取消、关闭和
输出上限均 fail closed。模块包不携带该项目的源码、wheel 或其他二进制。

固定来源为 `https://pypi.org/project/silk-python/0.2.8/`。PyPI 元数据声明 BSD；其固定
`silk-v3-decoder` revision `507be6bca8ce1fb977a061481f1d79e8c610e309` 的上游
LICENSE 为 MIT。Windows CPython x64 唯一允许的 wheel SHA-256 已冻结在
`silk_encoder.WINDOWS_X64_WHEEL_SHA256`，覆盖 cp310、cp311、cp312、cp313。依赖缺失、
版本不符或平台不符时 health 明确 unavailable，Core 仍可启动且 synthesize 返回
`encoding_unavailable`。

当前源码只提供适配器，尚未越权修改 PK-020 的依赖 profile 或共享 composition；因此在
PK-020 安装锁和 composition 固定注入完成前，真实 `/api/v1/voice/synthesize` 仍必须视为
不可用。PK-020 接缝为：新增 voice-media Windows lock，逐个冻结上述四个 wheel hash，
只在 `voice`/`full` profile 安装；doctor 只检查 distribution 版本、import 与能力，不编码、
不写文件、不联网。composition 接缝为：创建此适配器并注入
`app.state.voice_utterance_encoder`，不得按用户输入选择实现；缺依赖仍注入 unavailable
适配器，以便 health 给出稳定原因。

成功的 `POST /api/v1/voice/synthesize` 还固定返回
`X-Kei-Audio-Duration-Ms`。该值只从已经验证的 `SynthesizedUtterance.duration_seconds`
使用 `ceil(seconds * 1000)` 派生，范围为十进制整数 1..60000；非有限、零、负值或超限
整体失败，不从响应字节或客户端字段估算。
控制台只允许关闭由当前 Core 显式启动并持有句柄的 ASR/GPT-SoVITS 进程组；
外部启动的服务仅展示运行状态，不按端口或 PID 强制终止。
