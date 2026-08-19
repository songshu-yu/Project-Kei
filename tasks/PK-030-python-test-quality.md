# PK-030 — Python 测试发现、质量基线与 CI 收编

- 状态：已完成
- 优先级：P0
- 所属模块：`project_quality`
- 依赖任务：PK-001、PK-020
- 负责路径：根目录 `pyproject.toml`/质量工具配置、`server/tests/**` 的测试发现接缝、Python 测试依赖锁、`.github/workflows/**` 的 Python 测试作业、相关脚本与文档
- 当前对话：由 PK-000 于 2026-07-29 创建独立任务框
- 2026-08-02 发布接缝修复：`x_monitor@1.1.0` 新增的离线 `test_x_fxembed.py` 已登记进 `default_offline`。GitHub Windows 四版本矩阵此前均在 inventory 门禁以 `missing=['test_x_fxembed.py']` 停止；本修复只同步测试资产清单，不改变测试分类、业务实现或网络边界。

## 目标

把现有 Python 测试脚本转化为能够被标准测试运行器完整发现、隔离执行和在 CI 中持续回归的项目资产；建立可复现的 pytest 与 ruff 基线，使单个断言失败只影响对应测试项，并让安全的离线测试不再依赖人工维护的少量文件清单。

## 不在本任务内

- 不修改业务行为、API 契约、业务数据格式或模块所有权。
- 不借测试收编重写全部测试、统一业务架构或清理混合工作区。
- 不运行真实 Nitter/B站/GitHub/论文/RSS、LLM、TTS、ASR、QQ 或付费服务。
- 不读取或修改真实 `.env`、凭据、来源名单、缓存、个人状态、模型、Voice Pack、`vendor/`、现有虚拟环境或 `node_modules`。
- 不把明确需要真实网络、硬件、模型或秘密的诊断脚本伪装成默认单元测试；这类脚本必须分类、隔离并有显式运行条件。

## 接口契约

- 默认测试入口：从仓库受控 Python 环境执行 `pytest`，自动发现全部符合离线回归条件的 Python 测试。
- 兼容入口：现有可安全执行的单文件 `main()` 测试入口在迁移期间保持可用，不能一次性破坏其他任务记录中的既有命令。
- 质量入口：ruff 使用受版本控制的配置和明确文件范围；首次收编不得用全仓自动格式化制造无关差异。
- CI：不再仅依赖手写的少量测试文件列表；通过测试发现、清晰分组或生成矩阵覆盖全部已分类的离线测试。

## 数据所有权

- 本任务不拥有任何业务状态。
- pytest 临时文件、缓存和编译产物只能写入系统临时目录或明确的 CI 工作目录，不得落入真实 `server/data`、`server/systems/data` 或本机凭据目录。
- 测试发现和 CI 必须提供受保护路径防护，避免导入期或夹具误读默认个人状态、缓存、来源名单和秘密文件。

## 实施清单

- [x] 盘点全部 Python 测试、`check_*`、`main()` 和导入期副作用，按纯离线、需临时依赖、显式集成/手工诊断分类。
- [x] 建立 pytest 配置与 `conftest.py`，让离线 `check_*` 成为独立可报告测试项；选择批量改名或兼容收集钩子时保留现有单文件入口。
- [x] 为异步测试、临时路径、固定时钟、fake/MockTransport 和受保护路径提供统一夹具；禁止默认网络和真实状态访问。
- [x] 建立 ruff 的最小可执行配置与 CI 命令，记录首期基线和逐步收紧策略。
- [x] 把 Python 测试 CI 从少量硬编码文件升级为完整的已分类离线测试集合；单项失败应保留其他测试结果。
- [x] 保持 Windows Python 3.10–3.13 x64 安装矩阵与 PK-020 锁文件兼容，避免重复安装逻辑。
- [x] 更新任务记录、公开开发说明和专项质量文档。
- [x] 运行 pytest 收集审计、完整离线回归、ruff、文档门禁和 `git diff --check`。

## 验收标准

- `pytest --collect-only` 能列出所有已分类为自动回归的测试，不再只有手写 CI 清单中的少数文件。
- 原有 `check_*` 检查以独立测试项报告；一个失败不会阻止同文件其他可收集测试执行。
- CI 覆盖全部安全离线测试，并明确列出被隔离的真实网络/模型/硬件诊断项及理由。
- pytest 与 ruff 配置均受版本控制，命令在公开文档中唯一且可复制。
- 测试默认禁止外部网络，并在真实 I/O 前拒绝受保护的个人状态、缓存、来源名单和秘密路径。
- 不更改业务实现，不读取或修改真实用户数据，不把 `.pytest_cache`、临时文件或测试产物纳入 Git。
- PK-020 的 Python 3.10–3.13 Windows 支持范围保持通过；任何不兼容依赖必须先退回依赖锁所有者处理。

## 工作记录

- 2026-07-29：PK-000 根据项目审计登记本任务。现状为大量 Python 检查通过各文件 `main()` 顺序执行，CI 只手工运行少量文件；本任务将先重建真实测试清单和隔离等级，再冻结 pytest/ruff/CI 方案。
- 2026-07-29：实际 AST/文件扫描得到 67 个 `test_*.py`，其中 53 个默认离线、
  6 个受控集成、8 个人工诊断；顶层 `check_*` 为 180 个，其中 106 个异步。
  这些数字由 `scripts/check_python_test_inventory.py --json` 生成，不沿用任务输入中的估算。
- 2026-07-29：新增根 `pyproject.toml`、`server/tests/conftest.py`、
  `server/tests/python-test-inventory.json` 与 `server/tests/test_pytest_quality_gate.py`。
  pytest 收集测试模块自身定义的 `check_*`，异步检查由 `pytest-asyncio` 真实 await；
  12 个安全历史 `main()`/`demo()`/`check()` 入口以兼容包装器保留。完整性 hook 和清单
  审计共同阻止新增检查逃逸 pytest/CI。
- 2026-07-29：默认环境把状态路径和 profile/registry 环境变量指向系统临时目录，
  禁止所有 outbound socket（含真实 loopback 服务）及仓库写入；在真实内容/调用 I/O 前
  拒绝 `.env`、本机说明、凭据/来源名单状态目录、缓存、模型、输出、Voice Pack、
  `vendor/`、现有虚拟环境和真实 `node_modules`。默认测试只使用临时目录、固定时钟、
  ASGI/MockTransport 与 fake 依赖。
- 2026-07-29：隔离 14 个脚本及逐项理由已写入机器清单和
  `docs/architecture/python-test-quality.md`。CI 在 Windows Python
  3.10/3.11/3.12/3.13 每个矩阵项运行清单审计、完整 collect-only、完整默认 pytest
  与 ruff，不启动服务或下载模型。PK-020 已锁定 `pytest==8.3.3`、
  `pytest-asyncio==0.24.0`、`ruff==0.7.1`，本任务没有手工修改输入或生成锁。
- 2026-07-29：ruff 首期范围固定为 `server/tests` 和清单脚本，只启用
  `E9/F63/F7/F82`；格式化、import 顺序和更广泛风格规则明确后置，未执行全仓格式化。
- 2026-07-29：在全新系统临时 Python 3.12.7 venv 中严格按
  `requirements/core-win.lock.txt` 与 `requirements/dev-win.lock.txt` 安装：
  collect-only 收集 260 项；完整离线套件 259 passed、1 skipped（既有 PK-020
  端口占用条件），0 failed；质量夹具证明异步已 await、外部 DNS/真实 loopback 被
  阻断、protected path 在 I/O 前失败，且嵌套故意失败仍报告后续 1 passed。
  ruff 与机器清单审计通过。Python 3.10–3.13 的跨版本执行交由保留的 CI x64 矩阵，
  本机没有伪称运行其他解释器。
- 2026-07-29：未读取/输出/修改真实秘密、来源名单、模型、Voice Pack registry、
  `vendor/`、现有 venv、`node_modules` 或个人状态；未启动 API、QQ、ASR、TTS、
  GPT-SoVITS、collector 或模型。保留 PK-020/100/120/130/133/140/150/210/213
  及个人状态的全部混合修改；未暂存、提交、推送、切分支、清理或改动现有 PR。
- 2026-07-29：交 PK-900 独立复验。重点核对 67/53/14 文件清单、260 项收集、
  14 个隔离理由、四版本 workflow、零 outbound/零真实数据 tripwire、ruff 范围，
  以及共享 PK-020 workflow/copy surface 的最小差异；PK-030 不自行标记“已完成”。
- 2026-07-29：PK-900 独立发现过滤副本根因：`PROTECTED_PREFIXES` 拒绝整个
  `.github/`，而 inventory 与默认质量测试都必须读取受控 workflow，因此副本内稳定
  退出 2。最小整改在 `CopyPolicy.classify()` 的 protected-prefix 判断前增加唯一、
  大小写敏感的精确允许文件 `.github/workflows/windows-install.yml`，并将它加入
  `REQUIRED_COPY_FILES`；没有增加 `.github/` allowed prefix，也没有改变任何其他
  allowlist/protected prefix。
- 2026-07-29：copy tripwire 扩为 8 项并通过。合法 workflow 逐组件 lstat 后复制；
  evil workflow、`.github/actions/**`、大小写/分隔符/穿越/绝对路径变体在底层 I/O
  前拒绝；workflow symlink mode、组件 symlink/reparse、缺失与大小写替代项均
  fail closed，目标目录和 copy 调用保持为零。
- 2026-07-29：使用同一 policy 从当前混合工作树构造候选安全过滤副本，补入尚未
  发布但 policy 判为 allowed 的普通未跟踪文件；结果为 allowed/copied 387、
  protected rejected 7、ignored 8，副本 `.github/` 中唯一文件就是受控 workflow。
  副本内 `check_python_test_inventory.py --json` 通过并报告 67/53/14、180/106；
  `pytest -q server/tests/test_pytest_quality_gate.py` 为 6 passed；
  `test_windows_ci_copy.py` 为 7 passed、1 个“无 Git metadata”预期 skip。没有通过
  workflow 缺失跳过，也没有降低四版本、pytest 或 ruff 审计。精确发布后 PK-900
  仍须用真实 tracked Git tree 重放 `create_filtered_copy()` 与远端新矩阵。
- 2026-07-29：PK-900 已独立复验候选工作树整改并确认无新增本地缺陷。其独立
  合成逆向覆盖精确 workflow、evil/actions、大小写/分隔符/traversal/绝对/缺失、
  Git symlink mode 与组件 symlink/reparse，均符合 fail closed；同一生产 policy
  构造的候选副本中 `.github` 仍只有目标 workflow。副本 inventory、质量门禁 6/6、
  copy-policy 7 passed + 1 个无 Git metadata 预期 skip、260 项 collect-only、
  完整 pytest 258 passed + 2 个预期 skip、ruff 均通过；独立 AST 再次得到
  67/53/14、180/106，14 项隔离理由逐项成立。PK-020/PK-030 继续“待集成”、
  PK-900 继续“进行中”；精确发布后的真实 tracked `create_filtered_copy()` 和
  Python 3.10–3.13、Node 22、双 PowerShell 远端矩阵仍是最终门禁。
- 2026-07-29：按 PK-000 定向复核，把顶层 `check_*` 的参数可满足性加入
  `scripts/check_python_test_inventory.py` 与 `conftest.py` 的共同收集前门禁。
  AST 对当前 183 个默认顶层检查逐项解析必需 positional-only、positional 和
  keyword-only 参数，并识别项目/pytest fixture 及 literal `parametrize`：
  98 个零参数、85 个全部由 fixture/parametrize 满足、0 个 legacy wrapper 参数
  例外、0 个不可满足；13 个实际必需参数名也写入 `--json` 证据。12 个 legacy
  入口另行确认均为零必需参数，符合包装器无参调用契约。新增默认检查后若参数无法
  满足，会在导入测试模块和 pytest fixture 解析前以 UsageError fail closed。
- 2026-07-29：质量门禁新增三个永久回归。合成模块包含
  `check_manual_payload(manual_payload)` 且由 `main()` 手工传值，纯 AST 审计与
  `conftest._validate_default_check_parameters()` 都必须在 collection 前明确拒绝；
  另两个真实收集项分别证明普通 fixture 注入和 async fixture + async check 均被
  pytest 正常注入并 await。`test_pytest_quality_gate.py` 现为 9 passed，没有以
  `fixture not found`、skip 或 never-awaited 获得绿灯。
- 2026-07-29：受控入口复核发现 `scripts/python.ps1` 会先切换到 `server`，因此
  原 CI/README 中无显式路径的 pytest 会回退递归 `server`，而 inventory/ruff 的
  根相对路径也不再成立。CI、README、质量架构文档和机器审计已统一为
  `-m pytest tests`、`..\scripts\check_python_test_inventory.py` 与
  `-m ruff check tests ..\scripts\check_python_test_inventory.py`；没有修改
  Python 运行器或业务目录。当前仓库既有迁移 venv 的 pytest 插件版本不符合 dev
  lock，复核未读取、修改或向其中安装依赖；改用临时 dev-lock venv 和临时受控根，
  `server` 始终指向当前工作树。
- 2026-07-29：最终 Windows 受控命令结果：完整 collect-only 263 项、退出 0，
  无 unknown fixture/collection error；完整默认套件 262 passed、1 个明确预期
  skip（端口 8000 已占用）、0 failed；quality gate 9/9、copy-policy 8/8、
  ruff `All checks passed`、inventory 67/53/14 且参数分类 98/85/0/0。
  四个新增/修改 Python 质量文件均通过 Python 3.10 grammar 静态解析，保留 workflow
  的 3.10/3.11/3.12/3.13 x64 矩阵；任务文档门禁 24/24、`git diff --check` 通过。
  临时 sandbox 用户运行 Git metadata tripwire 时仅通过进程环境声明当前仓库为
  safe directory，没有写全局 Git 配置。未访问网络、真实状态、秘密、模型、现有
  venv 内容或 vendor，未启动服务，也未执行暂存、提交、推送、清理。PK-030 保持
  “待集成”，等待 PK-900 在精确发布后重放真实 tracked 副本与远端矩阵。
- 2026-07-29：PK-900 独立逆向发现参数契约仍有两个边界缺陷：必需
  positional-only 参数名与 fixture 相同时被错误放行到 call phase `TypeError`；
  模块自身合法 fixture 未并入可用集合而被错误拒绝。PK-030 接受精确退回，
  PK-020 产品安全逻辑、server-cwd 命令、workflow 精确复制例外及其他隔离边界
  均未改动。
- 2026-07-29：共享契约现把必需 positional-only 单独记录并无条件判为不可注入，
  同名 builtin/conftest fixture 或 literal `parametrize` 都不能抵消；同时由
  `validate_check_parameters()` 自身解析并合并每个模块可证明来自 pytest 的 fixture。
  支持 `pytest.fixture`、`import pytest as ...`、`from pytest import fixture as ...`、
  非空 literal `name=`、`params=` 及 async fixture。动态名称、任意同名 decorator、
  pytest import alias 重绑定、同模块重复暴露名和 fixture decorator 位置参数均以
  可理解错误 fail closed。
- 2026-07-29：永久逆向覆盖纯 AST 与真实子 pytest collection：
  `check_posonly(tmp_path, /)` 在模块导入/fixture 解析前固定 UsageError，输出不含
  call-phase TypeError 或 fixture-not-found；同名 literal parametrize positional-only
  同样拒绝。模块本地同步参数化 fixture、明确 decorator alias、literal
  parametrize、keyword-only builtin fixture、async fixture + async check 均被接受
  并真实执行；普通/keyword-only unknown、非 literal 名称及重复名继续拒绝。
- 2026-07-29：整改后实际树为 67/53/14 文件、185 个默认顶层 `check_*`、
  107 async，参数分类 99 零参数、86 fixture/parametrize、0 wrapper 例外、
  0 不可满足，12/12 legacy 入口无必需参数。Windows 受控入口 collect-only
  265 项、退出 0；完整默认套件 264 passed、1 个端口 8000 占用预期 skip、
  0 failed；quality gate 11/11、copy-policy 8/8、ruff 和 Python 3.10 grammar
  静态检查通过。PK-030 继续“待集成”，交 PK-900 重新独立复验；未访问保护数据、
  启动服务或执行 Git 修改操作。
- 2026-07-29：PK-900 第二次独立复验确认前两项修复有效，但又发现两个精确阻断：
  pytest alias 在模块级控制流内被重绑定时仍受信任；参数化 check 的
  `[param-id]` 展示 node id 未被 exact-string 完整性检查识别。PK-030 再次接受
  退回，仅修改参数契约、collection 完整性和质量回归；PK-020、workflow copy
  例外、业务代码及安全中间件均未改动。
- 2026-07-29：alias 分析改为模块执行作用域 visitor，递归模块级控制流但不进入
  function/class/lambda/comprehension 内部；覆盖解包/星号、同步与 async loop/with、
  except name、NamedExpr、Delete、match pattern、条件 import 和定义默认值表达式。
  `for/if/try/except/with/walrus/del` 七类反例均由纯 AST 与真实子 pytest 在
  collection 前拒绝，扩展边界也 fail closed；嵌套词法作用域的局部同名变量不会
  误伤未重绑定的明确 pytest alias。
- 2026-07-29：collection 完整性不再解析展示 node id，而以 item 解析后的模块路径、
  pytest `originalname` 和顶层 `Module` parent 建立严格 base identity，并排除
  `skip/skipif` item。永久子项目以双参数、多个含方括号/`::`/斜线/空格的 param id、
  同名不同模块和同名类方法执行 collect/full 4/4；同名前缀、伪造方括号、类方法和
  skipped item 均不能满足顶层函数。
- 2026-07-29：最终实际树为 67/53/14 文件、187 个默认顶层 `check_*`、
  107 async，参数分类 99 零参数、88 fixture/parametrize、0 wrapper 例外、
  0 不可满足，12/12 legacy 无必需参数。受控默认 collect-only 267 项、退出 0，
  完整套件最终 266 passed、1 个端口 8000 占用预期 skip、0 failed；quality
  gate 13/13。首次 full run 曾有既有 fitness 并发临时文件 `WinError 5`，定向
  复跑 1/1 与随后完整复跑均通过，未修改业务实现。PK-030 保持“待集成”，等待
  PK-900 第三次独立复验后再恢复 tracked copy/远端矩阵。
- 2026-07-29：PK-900 第三次独立复验确认本地候选通过，两项第二次退回阻断关闭。
  其未复用来源临时目录，新建同生产 policy 候选过滤副本，得到
  `allowed/copied=388 protected=112 ignored=8 lstat=1329`，且 `.github` 唯一
  文件仍为受控 `windows-install.yml`。14 类 alias 模块作用域重绑定纯 AST 全部
  拒绝，原七类子 pytest 均在 collection 前 UsageError；nested
  function/class/lambda/comprehension/async function 局部同名均合法接受。
- 2026-07-29：PK-900 独立 identity/junction 逆向覆盖特殊 param id、双参数、
  同名不同模块、同名前缀、类方法、skip/skipif，结果 collect 8、full
  6 passed + 2 expected skipped，伪造 bracket/class/skip 均不能满足 base identity。
  指向整个候选副本的真实 junction 以 `.\tests\..\tests` 调用生产 conftest，
  267 collected、退出 0；inventory 与独立 recount 同为
  67/53/14、187/107、99/88/0、legacy 12/12。
- 2026-07-29：独立候选 quality 13/13、copy 7 passed + 1 个无 Git metadata
  预期 skip，共享根 copy 8/8、ruff、Python 3.10 grammar、docs 24 和 diff-check
  全部通过。fitness 定向 3/3；两轮独立 basetemp 完整默认套件均
  265 passed + 2 expected skipped、0 failed，未复现 `WinError 5` 且无临时替换
  残留。PK-030 仍为“待集成”、PK-900 仍“进行中”；下一步仅由 PK-000 精确发布，
  随后 PK-900 从真实 tracked Git tree 执行 `create_filtered_copy()` 并取得
  Python 3.10–3.13、Node 22、PowerShell 5.1/7.4+ 同 commit 矩阵，不提前关闭。

## 完成文档门禁

任务进入“待集成”或“已完成”前必须全部勾选；不适用项也必须写明原因。

- [x] TASK_RECORD — 已记录测试分类、发现机制、CI 范围、副作用、验证和遗留问题。
- [x] TASKS_BOARD — 已同步 `TASKS.md` 的状态、名称、优先级和依赖。
- [x] PUBLIC_README — 已更新开发者测试与质量检查入口。
- [x] MODULE_CATALOG — 不适用：不改变业务模块目录或运行接口。
- [x] ARCHITECTURE_DOCS — 已新增 Python 测试、隔离与 CI 质量架构说明。
- [x] LOCAL_README — 不适用：未改变本机路径、解释器、端口或服务位置。
- [x] AGENT_RULES — 默认 Python 验证入口已改为完整 pytest 与首期 ruff 基线。
- [x] VALIDATION — 已记录实际 pytest/ruff/CI 静态证据、文档门禁和 `git diff --check`。

## 独立对话启动提示

```text
继续 Project Kei 的 PK-030「Python 测试发现、质量基线与 CI 收编」。
先完整阅读 README.md、AGENTS.md、README.local.md（如存在）、TASKS.md、
tasks/PK-030-python-test-quality.md、tasks/PK-020-windows-install.md 和现有
Windows workflow；检查 git status 与全部 Python 测试的实际结构。先只读盘点并
分类，再以最小兼容方式建立 pytest/ruff/CI。禁止真实网络、模型、QQ、个人状态和
秘密访问；保留混合工作区，不执行 Git 发布操作。
```
