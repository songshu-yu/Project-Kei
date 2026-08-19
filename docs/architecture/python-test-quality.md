# Python 测试与质量基线

PK-030 把 `server/tests/` 中安全的脚本式检查收编为标准 pytest 离线回归，同时保留
仍被任务记录引用的安全单文件入口。配置、分类清单和完整性审计分别位于：

- `pyproject.toml`：pytest 发现、异步模式、marker 与 ruff 首期规则。
- `server/tests/conftest.py`：`check_*` 收集接缝、临时目录/固定时钟夹具、网络和
  protected-path tripwire。
- `server/tests/_parameter_contract.py`：共享的 fixture/parametrize 参数契约解析，
  在 pytest fixture 解析前拒绝不可满足的默认检查。
- `server/tests/python-test-inventory.json`：每个测试文件的唯一分类及隔离理由。
- `scripts/check_python_test_inventory.py`：机器可核验的清单、依赖和 CI 门禁。

## 标准命令

从仓库根目录运行：

```powershell
.\setup.bat --profile dev
.\scripts\python.ps1 ..\scripts\check_python_test_inventory.py
.\scripts\python.ps1 -m pytest tests --collect-only -q
.\scripts\python.ps1 -m pytest tests
.\scripts\python.ps1 -m ruff check tests ..\scripts\check_python_test_inventory.py
```

pytest 将测试模块自身定义的顶层 `check_*` 作为独立项目收集，异步检查由
`pytest-asyncio` 的 auto 模式真实 await。导入的业务 `check_*` 和仅供测试内部复用的
helper 不会伪装成测试。12 个仍有安全 `main()`/`demo()`/`check()` 入口的脚本由兼容
包装器覆盖，因此旧单文件命令仍可使用。

清单审计和 `conftest.py` 使用同一 AST 参数契约：逐项检查顶层 `check_*` 的必需参数
是否为 pytest/项目 fixture 或 literal `parametrize` 参数，并确认 legacy 包装入口
可被无参调用。新增无法满足的参数不会等到运行阶段才显示 `fixture not found`，而会
在 collection 前 fail closed；带合法 fixture 的同步检查和 async fixture/check
仍由 pytest 正常注入并 await。

必需 positional-only 参数不能由 pytest 的关键字注入，因此即使与 fixture 或
`parametrize` 同名也一律在 collection 前拒绝。逐文件审计还会合并模块自身可静态
证明的 pytest fixture：支持 `pytest.fixture`、明确的 pytest import alias、
非空 literal `name=`、带 `params=` 的同步 fixture 和 async fixture；动态 fixture
名称、任意同名 decorator、pytest import alias 重绑定、重复模块 fixture 名及不受
支持的位置参数声明均 fail closed。模块本地 fixture 可以合法覆盖
conftest/builtin 名称，重复仅针对同一模块内两个 fixture 暴露同一名称。

pytest import alias 的信任按模块执行作用域保守失效：递归检查模块级
`if/for/try/except/with/match`，覆盖赋值、解包/星号目标、同步/async loop 与
with target、except name、walrus、delete 和 import 覆盖，但不进入函数、类、
lambda 或 comprehension 的内部词法作用域。任何可能覆盖可信 alias 的模块路径都会
使它失效。

collection 完整性不解析 pytest 的展示 node id，也不按字符串前缀或方括号截断。
它以 collection item 的解析后模块路径、pytest `originalname` 和 parent 是否为
顶层 `Module` 建立 base identity；因此任意数量及特殊字符的参数 ID 都归属于同一
顶层函数，而同名不同模块、类方法、同名前缀和伪造方括号不会互相满足。带
`skip/skipif` 的 item 不可充当“至少一个可执行节点”的证据，collection error
仍由 pytest 自身保持非零退出。

## 默认隔离边界

默认套件只使用系统临时目录、固定时钟、ASGI/MockTransport 和 fake 依赖。套件在
socket I/O 前拒绝所有 outbound connect/send（包括真实 loopback 服务），并在内容或
测试调用 I/O 前拒绝仓库/服务 `.env`、`README.local.md`、凭据与来源名单所在状态目录、
缓存、模型、生成输出、Voice Pack registry、`vendor/`、现有虚拟环境和真实
`node_modules`。仓库内写入也会失败；pytest cache 与 bytecode 均不落入工作区。

## 隔离清单

受控集成共 6 个，只能由操作者准备明确的本机依赖后定向运行：

| 文件 | 默认隔离理由 |
|---|---|
| `test_asr_upload.py` | 需要用户音频文件和 8010 ASR 服务 |
| `test_daily_briefing_voice.py` | 可触发运行中 API、采集、LLM 改写、缓存和 TTS |
| `test_health_full.py` | 探测 API/ASR/TTS，且可显式触发付费 LLM |
| `test_mic_voice_chat.py` | 需要麦克风、音频驱动、多个运行中服务并写音频 |
| `test_tts_gptsovits.py` | 读取本机 Voice Pack registry、连接 9880 并写音频 |
| `test_voice_chat.py` | 需要用户音频以及 API、ASR、LLM、TTS 服务 |

显式人工诊断共 8 个，不属于自动回归：

| 文件 | 默认隔离理由 |
|---|---|
| `test_audio_cleanup.py` | 检查真实输出，`--apply` 可删除用户文件 |
| `test_intel.py` | 联系真实 arXiv、GitHub、Nitter、B站、YouTube、RSS |
| `test_llm_debug.py` | 读取本机模型配置并发送真实/可能付费请求 |
| `test_twitter_debug.py` | 读取真实来源配置并执行 Nitter 网络诊断 |
| `test_weibo_debug.py` | 执行真实 RSSHub 网络诊断 |
| `test_youtube_debug.py` | 读取频道配置并执行 YouTube 网络诊断 |
| `test_zuo.py` | 执行真实期刊与 Semantic Scholar 搜索 |
| `test_zuo_deepseek_summary.py` | 读取模型凭据、真实补全论文并调用 DeepSeek |

`python-test-inventory.json` 是机器判定源；新增 `test_*.py`、顶层 `check_*`、兼容入口
或分类变化后必须同步清单。审计脚本会拒绝遗漏、过期路径、无理由隔离、缺少依赖、
失去 Python 3.10–3.13 CI 矩阵或重新出现硬编码少量测试文件。

## CI 与 Ruff

Windows workflow 在 Python 3.10、3.11、3.12、3.13 x64 的每个矩阵项上依次运行清单
审计、完整 collect-only、完整默认 pytest 和 ruff。它不启动业务服务或下载模型。
Python 依赖继续由 PK-020 的输入文件与生成锁控制，不接受 `pip freeze` 或手工改锁。
PK-020 的安全 CI 副本仍保护整个 `.github/`，仅对精确、大小写敏感的
`.github/workflows/windows-install.yml` 放行并列为 required file，使过滤副本中的
inventory 审计读取的就是同一受控 workflow；其他 workflow、action、路径变体和链接
仍在目标目录或复制 I/O 前拒绝。

ruff 首期仅覆盖 `server/tests` 与清单审计脚本，启用 `E9`、`F63`、`F7`、`F82`，
用于阻断语法、非法控制流和未定义名称。格式化、import 排序及更广泛风格规则留给
后续独立任务逐步收紧，不能用全仓自动格式化掩盖业务差异。
