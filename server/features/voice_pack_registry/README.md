# Voice Pack Registry 可安装模块

该目录是 PK-212 的可安装化交付。构建产物只含 Voice Pack Schema、Registry、
本地导入校验、选择/启停/注销逻辑、`backend.register` 和动态管理面板。

它不包含 Voice Pack manifest 实例、Kei 或其他角色的权重/参考音频、GPT-SoVITS
Engine、LLM Profile、Persona、`.env`、本机注册表、绝对路径、vendor 或安装脚本。
卸载模块只移除可再生成的程序包；真实 `voice_pack_registry.local.json` 和用户
Voice Pack 资产继续留在原处。
