# Conversation module

本目录拥有文字对话、单进程 history、只读上下文消费、受控文本生成、非秘密模型
profile 和活动 LLM client。`router.py`、`service.py`、`runtime.py`、
`repository.py` 与 `client.py` 保持单一实现；安装包构建器只复制这套实现，不维护
第二套业务代码。

## 安装包

- `package_source/manifest.json`：`conversation@1.0.1` 的 PK-010 声明。
- `module.py`：包内 `backend.register(app)` 与幂等异步
  `backend.unregister(app)` 接缝；卸载只关闭本次注册拥有的 service，并以身份
  校验清理本模块设置的 `app.state` 引用，不触碰上下文 Provider。
- `package_source/dashboard/index.js`：LLM profile 动态面板。
- `package_builder.py`：固定 allowlist、UTF-8 LF、固定 ZIP 元数据和
  `ZIP_STORED` 的字节稳定构建器。
- `release/`：交给 PK-000 的公开 Release fragment、精确 Catalog 条目与发布说明。

包仅从环境读取 `LLM_API_KEY`。profile 仍是既有本机
`server/data/llm_profile.json`，不进入包；卸载程序不删除 profile，重装后继续
关联。普通 history 只在当前进程内存中，停用、卸载或重启不会将其持久化。

## Core 装配接缝

`register(app)` 可以从 `app.state` 读取以下可选装配值：

- `conversation_service_factory`：测试或 Core 提供的无参数 service factory；
- `conversation_profile_path`、`conversation_default_profile`；
- `conversation_context_provider`：只读 `get_context() -> str`。默认 service 每次生成
  请求才从 `app.state` 解析当前 provider，因此 conversation 先注册、上下文模块后
  注册或运行时替换都可立即生效；缺失、递归、非结构实现、异常和非字符串结果均按
  空上下文降级；
- `conversation_local_control_guard`；
- `conversation_legacy_command_handler`：外部记忆命令兼容处理；
- `conversation_audio_synthesizer`：仅 legacy `/chat` 与 `/ws/chat` 的可选音频接缝。

注册成功后只公开 `conversation_service`、
`conversation_text_generator_provider` 与 `conversation_service_close` 到
`app.state`。其他模块应由 Core 的稳定 Provider 取得 service 或空实现，不能
导入安装包的动态 Python 名称。当前共享 `server/api.py` 仍保留上一阶段的内置
导入和消费者接线；按 PK-011 冻结矩阵，该删除/降级装配由 PK-000 串行完成，不在
本目录越界修改。
