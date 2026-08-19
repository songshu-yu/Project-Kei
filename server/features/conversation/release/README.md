# Conversation official release handoff

本目录冻结 `conversation@1.0.2` 的 PK-011 官方发布输入。确定性 ZIP 不进入仓库，
由 PK-000 在临时目录重建、复核并发布；本任务不创建 GitHub Release、不上传资产，
也不修改共享官方 Catalog。

发布身份：

- Release tag：`modules-2026.08.02`
- Asset：`conversation-1.0.2.zip`
- 固定来源：`songshu-yu/Project-Kei-Modules`
- 权限：`local_state`，仅用于非秘密 `llm_profile.json`
- 配置：`LLM_API_KEY` 只从进程环境读取，不进入包、profile、响应或浏览器
- 数据策略：卸载保留既有 profile；重装后由 Core 装配重新关联
- 重启：启用、停用、更新、回滚和卸载后需要重启 Core 才改变路由与面板

从项目根目录向新的临时输出路径构建：

```powershell
.\scripts\python.ps1 -m features.conversation.package_builder `
  "<temporary-directory>\conversation-1.0.2.zip"
```

包只含 allowlist Python 程序、Kei 角色提示、manifest、配置声明和动态面板；不含
`.env`、API Key、profile、history、长期记忆、好感度、缓存、模型、vendor、
安装脚本或运行目录。
