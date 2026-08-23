# 每日生活预报模块契约

## 边界与生命周期

`life_forecast` 是 PK-240 独占的可安装 `in_process` 模块，不新增进程或端口。源码、
manifest、动态面板和确定性构建器位于 `server/features/life_forecast/`；安装、启用、
停用、更新、回滚和卸载复用 PK-010。启停类操作需要重启 Core，卸载默认保留数据。

模块只拥有天气事实、由事实推导的生活建议、本地娱乐运势、位置/Provider 配置和
按日缓存。它不读取或修改 daily briefing、calendar、QQ、relationship/memory、
conversation、语音、个人状态或其他模块数据。

## 版本化 API

| 接口 | 网络/写入语义 |
|---|---|
| `GET /api/v1/life-forecast/today` | 只读用户本地“今天”缓存；无上游网络、无写入；旧日期不回退为今天 |
| `GET /api/v1/life-forecast/config` | 只读本机配置；经纬度仅因控制台编辑需要而返回给 loopback 调用方 |
| `PUT /api/v1/life-forecast/config` | 验证城市标签、坐标、Provider、娱乐开关并原子保存；不刷新、不联网 |
| `POST /api/v1/life-forecast/refresh` | 唯一上游联网入口；并发调用合并为一个刷新序列，失败保留旧缓存 |

Core 的全局 loopback/Origin 边界继续保护接口。模块不新增 legacy 路径，不接受上游
URL、Header、Token、Cookie、代理或任意 Provider 名。错误只返回有限 code，不包含
位置、城市、上游正文、路径或调用栈。

## 公共 Provider 1.0

冻结的 Python 接缝为：

```python
class WeatherProvider(Protocol):
    provider_id: str
    def fetch(self, location: LocationConfig, local_date: date) -> ForecastResult: ...
```

`LocationConfig` 在进入第三方 Provider 前会清空城市标签并关闭娱乐字段，只保留明确
配置的经纬度、Provider ID 和本地日期。`ForecastResult` 是不可变 dataclass，固定输出：

- Provider、当地日期、已验证 IANA 时区；
- 本地 allowlist 天气条件与代码；
- 当前温度、体感、最高/最低温（摄氏度）；
- 最大降水概率（百分比）、最大风速（km/h）；
- 可空 UV、可空美国 AQI；
- `available/unavailable` 预警状态与有限结构化预警；
- UTC 获取时间和固定署名链接。

Provider 不写配置/缓存、不生成生活建议/运势、不接触其他模块。温度和风速在边界
转换为固定单位；非有限值、越界值、未知单位、日期不符、未知天气代码、非法时区、
超时、429、网络和 5xx 使用有限错误码失败。外部自由文本不会进入结果。单独空气
质量查询失败时天气仍可用，但 AQI 明确为 `None/unavailable`。

## Open-Meteo 第一版适配

Provider 默认 `disabled`。用户必须先在本机配置中选择 `open_meteo`，再点击“显式
刷新”，才会把经纬度发送到固定的：

- `https://api.open-meteo.com/v1/forecast`
- `https://air-quality-api.open-meteo.com/v1/air-quality`

请求固定为当天、`timezone=auto`、摄氏度和 km/h，不发送城市、生日、星座、娱乐
内容、API Key、Cookie 或其他个人状态。客户端不继承环境代理、不跟随重定向，设置
连接/读取总超时；响应正文和异常正文不进入 API 错误或日志。

Open-Meteo API 数据按 CC BY 4.0 使用，控制台在数据旁显示 Open-Meteo 链接；空气
质量数据同时显示 CAMS 署名。Open-Meteo 免费公共服务当前只适合非商业低频场景；
商业/高量部署必须由部署者按其最新条款选择商业服务。模块不内置 API Key，也不把
Key 放进 manifest、浏览器、配置响应或日志。

Open-Meteo 第一版没有本模块可消费的官方灾害预警字段，因此必要预警严格返回
`warnings_status=unavailable`。普通天气代码或本地阈值不得伪造“官方预警”。未来
Provider 如增加预警，必须给出公开来源、时间、严重度和安全有限文本，并保持
ForecastResult 1.x 向后兼容；破坏性字段变化交 PK-000 提升契约 major。

## 本机数据与原子性

数据根为 Git 忽略的 `server/data/modules/life_forecast/`：

```text
config.json                    # 本机隐私：城市标签、经纬度、Provider、娱乐开关
cache/YYYY-MM-DD.json          # 规范化天气、建议、配置指纹；不保存明文位置
```

缓存 key 永远是注入时钟得到的用户本地日期。普通读取只尝试该日期文件；缺失、损坏、
日期不符或配置指纹变化都返回明确状态和空事实，不向前扫描、不把昨天冒充今天、不写
修复文件。刷新先完整获取/解析/规范化，再在同目录写唯一临时文件、`flush/fsync`、
原子替换；任何获取、解析、暂存或替换失败保留旧目标字节。

缓存只保存经纬度/Provider 的 SHA-256 指纹，不保存城市或明文坐标。位置只在
`config.json` 存在，不进入 Git、安装 ZIP、Catalog、任务文档、日志或 today 响应；
today 只从当前本机配置返回显示所需城市标签。

## 生活建议与娱乐分区

生活建议是确定性本地规则：穿衣只参考体感温度；出行/带伞只参考降水概率、固定
天气代码和风速；UV/AQI 缺失时输出 `unavailable`。建议不是官方警报，也不替代当地
政府、医疗或应急指引。

娱乐运势不使用星座、生日、定位或第三方 API。规则版本固定为
`local-date-sha256-v1`：对“规则版本 + 用户本地 YYYY-MM-DD”做 SHA-256，以前三个
字节分别从固定的提示、颜色、小行动文案表取值。同一日期稳定、跨日变化、无随机
状态、可关闭，响应和控制台始终显示“娱乐内容、非事实预测”。天气事实、生活建议、
娱乐内容必须在动态面板中成为三个带独立标题的语义区块。

## 消费端只读联动（PK-241）

PK-240 不直接修改 daily briefing 或 QQ。PK-241 在 PK-110 与 PK-140 自有边界内实现
以下联动，且不改变 PK-240 公共契约：

1. 每日情报与 QQ 文字关键词的数据源是 PK-240 的只读 `GET /api/v1/life-forecast/today` 或等价进程内 Provider。
   QQ 固定菜单按钮是唯一消费端刷新入口，只能调用一次固定本机 `POST /api/v1/life-forecast/refresh`；消费端仍不得读取私有配置/缓存文件或取得坐标，损坏、跨天、unavailable 与刷新失败不得回退为旧预报。
2. PK-110 保存自己命名空间内的展示偏好，增加生活预报总开关和以下稳定逐项开关：
   `weather_condition`、`temperature_range`、`apparent_temperature`、
   `precipitation_probability`、`wind`、`alerts`、`clothing`、`travel_umbrella`、
   `uv`、`air_quality`、`fortune`。迁移默认关闭；开关只改变简报投影，不复制 PK-240 数据或规则。
3. 每日情报的 `fortune` 是双重许可：PK-240 娱乐开关与 PK-110 对应项同时开启才显示，且必须保留
   “娱乐内容、非事实预测”并与事实分区。
4. PK-140 增加独立生活预报总开关（迁移默认关闭）、固定 action `kei:life-forecast` 和私聊菜单按钮
   “生活预报”。精确关键词固定为 `每日生活预报`、`今日生活预报`、`生活预报`、`今日天气预报`；
   禁止用“天气”等宽泛子串拦截普通对话。点击与关键词共用同一格式化和脱敏边界，但按钮显式刷新、关键词只读缓存。
5. QQ 第一版展示当天全部可用天气事实与生活建议，不复用每日情报的字段开关；娱乐内容仍受 PK-240
   娱乐开关约束并保留完整免责声明。第一版不新增定时推送，不修改既有调度和 at-most-once 状态。
6. 页面加载、设置展开、普通读取、菜单展示与 QQ 关键词查询均不得产生天气上游网络或写入 PK-240 缓存。
   只有明确点击固定“生活预报”按钮允许一次刷新；失败不重试、不回退缓存，既有 QQ interaction 去重保证同一点击不会重复刷新。
7. 若需要专用摘要端点，只能在 `/api/v1/life-forecast` 下做兼容增量，并由 PK-000 先冻结版本/字段；
   任何 PK-110 配置 schema、PK-140 action/关键词或公共接口变化也必须由对应串行任务实施和验收。

集成测试必须使用 fake 摘要与临时配置，覆盖默认关闭、逐项组合、固定 action 单次刷新、关键词只读、
刷新失败无回退、跨天/损坏/unavailable、娱乐双开关与免责声明、普通路径零网络和位置清洗；禁止真实 QQ 或天气网络。

PK-110 的投影配置固定在其 `data/modules/daily_briefing` 命名空间，损坏或未知 schema
只读失败关闭且不覆盖原文件。`GET /api/v1/briefing/today` 只在运行时附加投影；总开关
关闭时不解析 Provider，开启时每次捕获一次 `get_today()` 结构化快照。PK-140 的配置沿用
既有 `.env` 原子存储，菜单/关键词 handler 仅格式化四个允许的顶层字段。两端都不保存
城市、坐标、天气响应或娱乐正文副本。

## 离线验收

自动测试只使用 fake Provider、`httpx.MockTransport`、固定/可变时钟、临时配置与
临时缓存。必须覆盖本地跨日、DST 时区值、超时/429/5xx、AQI 降级、恶意文本、
异常单位/时区、非法坐标、损坏缓存、原子替换失败、并发刷新、单位转换、隐私清洗、
确定性运势、确定性 ZIP 和普通读取零上游网络。禁止真实天气请求、真实定位、付费
API、QQ、LLM、TTS、`.env`、真实 runtime/registry 或个人数据。
