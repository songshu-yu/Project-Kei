# 每日生活预报

PK-240 的独立可安装模块。安装、启用并重启 Core 后提供：

- `GET /api/v1/life-forecast/today`：只读用户本地今天缓存，零上游网络；
- `GET/PUT /api/v1/life-forecast/config`：读取/保存本机位置、Provider 与娱乐开关；
- `POST /api/v1/life-forecast/refresh`：唯一上游联网入口，失败保留旧缓存。

默认 Provider 为 `disabled`。选择 `open_meteo` 并显式刷新时只发送经纬度到固定
Open-Meteo 天气和空气质量 API；城市标签与娱乐内容留在本机。Open-Meteo 数据按
CC BY 4.0 署名，空气质量另署名 CAMS。免费公共服务适合非商业低频使用；商业部署
需按 Open-Meteo 当前条款配置合适服务，本模块不内置或回显 API Key。

第一版 Provider 没有官方灾害预警字段，因此 `warnings_status=unavailable`，不会把
普通天气代码伪造成预警。今日运势使用公开的本地日期 SHA-256 固定文案规则，同日
稳定、可关闭，并始终标注“娱乐内容、非事实预测”。
