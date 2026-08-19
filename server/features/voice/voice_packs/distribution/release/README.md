# Voice Pack 分发模块发布输入

本目录只保存 `voice_pack_distribution@1.0.1` 的公开模块发布元数据，不保存
Voice Pack、模型权重、参考音频、真实 catalog 条目、下载缓存、Registry、本机路径
或凭据。

确定性模块资产由 `features.voice.voice_packs.distribution.package_builder` 在显式
临时/输出目录生成。PK-000 只有在语音批通过独立验收后，才可将条目并入官方模块
Catalog 并执行 GitHub Release；PK-213 不发布。

`1.0.1` 的 `network_download` 只覆盖用户精确确认后的固定官方 HTTPS 获取。
模块注册、启动、页面加载和普通只读操作不得联网；发布输入不接受任意 URL、
headers、proxy、命令或脚本，下载内容只作校验与安全导入数据，绝不执行。
