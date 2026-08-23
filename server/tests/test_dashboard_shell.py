"""Side-effect-free regression checks for the PK-100 dashboard shell."""

from __future__ import annotations

import asyncio
import json
import os
import re
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, Response

os.environ["PROJECT_KEI_ENV_FILE"] = str(
    Path(tempfile.gettempdir()) / "project-kei-pk100-tests" / "missing.env"
)
os.environ.pop("PROJECT_KEI_SUPERVISOR_SESSION", None)

import _path_setup  # noqa: E402,F401

from features.dashboard.router import (  # noqa: E402
    DASHBOARD_ASSET_ROOT,
    create_dashboard_ui_router,
    dashboard_static_asset,
)
from features.dashboard.ui_assets import DashboardUiAssetStore  # noqa: E402


SERVER_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = SERVER_ROOT.parent
DASHBOARD_HTML = SERVER_ROOT / "static" / "dashboard.html"
DASHBOARD_ASSETS = SERVER_ROOT / "static" / "dashboard"
PUBLIC_README = PROJECT_ROOT / "README.md"
NODE = "node"

CORE_MODULE_IDS = ("catalog", "module_manager", "dashboard")
OFFICIAL_MODULE_IDS = (
    "affection_memory",
    "bilibili",
    "calendar",
    "conversation",
    "daily_briefing",
    "demon_slayer",
    "fitness",
    "focus",
    "github_intel",
    "gpt_sovits_engine_provider",
    "intel_sources",
    "papers",
    "qq_bridge",
    "rss_intel",
    "voice",
    "voice_pack_distribution",
    "voice_pack_registry",
    "x_monitor",
    "youtube",
)
INSTALLABLE_MODULE_IDS = tuple(sorted((*OFFICIAL_MODULE_IDS, "life_forecast")))


def run_node(args: list[str], *, input_text: str | None = None) -> None:
    completed = subprocess.run(
        [NODE, *args],
        cwd=SERVER_ROOT,
        input=input_text,
        text=True,
        encoding="utf-8",
        capture_output=True,
        check=False,
    )
    if completed.returncode:
        raise AssertionError(completed.stderr or completed.stdout)


def package_manifests() -> list[Path]:
    manifests = sorted(
        path
        for path in (SERVER_ROOT / "features").rglob("manifest.json")
        if "package_source" in path.parts
    )
    manifests.append(SERVER_ROOT / "qq_bridge" / "package_source" / "manifest.json")
    return manifests


def check_html_contract() -> None:
    html = DASHBOARD_HTML.read_text(encoding="utf-8")
    ids = set(re.findall(r'\bid="([^"]+)"', html))
    assert {
        "dashboard-theme",
        "refresh",
        "overall-dot",
        "overall",
        "updated",
        "services",
        "refresh-official-module-catalog",
        "toggle-official-module-batch",
        "official-module-catalog-status",
        "official-module-install-confirmation",
        "official-module-batch-toolbar",
        "official-module-batch-count",
        "select-all-official-modules",
        "cancel-official-module-batch",
        "install-selected-official-modules",
        "official-module-batch-confirmation",
        "official-module-batch-summary",
        "official-module-batch-list",
        "official-module-catalog",
        "refresh-installed-modules",
        "module-operation-status",
        "module-catalog-status",
        "module-catalog",
        "builtin-module-catalog-status",
        "builtin-module-catalog",
        "local-module-id",
        "local-module-id-suggestions",
        "local-module-zip",
        "local-module-upload-status",
        "install-local-module-zip",
        "local-module-id-choice",
        "local-module-id-choice-heading",
        "local-module-id-choice-copy",
        "restart-project-kei",
        "restart-project-kei-status",
        "restart-project-kei-confirmation",
        "restart-project-kei-confirmation-heading",
        "restart-project-kei-confirmation-copy",
        "confirm-restart-project-kei",
        "cancel-restart-project-kei",
        "gpt-sovits-engine-heading",
        "gpt-sovits-engine-status",
        "select-gpt-sovits-engine",
        "dashboard-module-mounts",
        "notice",
    } <= ids
    assert 'data-panel-id="configuration-readiness"' in html
    assert "配置就绪情况" in html
    assert '<noscript>' in html
    assert html.count('<script type="module" src=') == 2
    assert not re.search(r"<script(?:\s[^>]*)?>(?!\s*</script>)", html)
    assert "只有 catalog、module_manager 与 dashboard 属于 Core 固定模块" in html
    assert "等待本机配置的 sidecar 受信面板" in html
    assert "不会访问 GitHub，也不会请求未安装业务接口" in html
    assert "服务器路径" in html and "任意下载网址" in html
    assert 'accept=".zip,application/zip"' in html
    assert "选择文件不会联网或安装" in html
    assert 'placeholder="将从 manifest 自动识别"' in html
    for choice in ("keep", "manifest", "cancel"):
        assert f'data-local-module-id-choice="{choice}"' in html
    assert "保留手工 ID" in html and "使用新包自动识别" in html
    assert "批量选择" in html and "全选兼容项" in html and "安装已选" in html
    assert 'aria-pressed="false"' in html
    assert "pk100-20260808-controls1" in html
    assert "重启期间控制台会短暂断开并自动尝试重连" in html
    assert "选择已有引擎目录" in html
    assert "首批只有 focus" not in html
    assert "Calendar/Fitness/Demon/Conversation/Intel" not in html

    forbidden_ids = {
        "build",
        "start-qq-bridge",
        "refresh-qq-bridge",
        "intel-sources-status",
        "briefing",
        "llm-preset",
        "affection-stats",
        "demon-summary",
        "fitness-summary",
        "focus-summary",
        "calendar-summary",
        "memory-summary",
        "schedule-enabled",
        "config",
    }
    assert forbidden_ids.isdisjoint(ids)
    for route in (
        "/api/v1/relationship",
        "/api/v1/briefing",
        "/api/v1/intel-sources",
        "/api/v1/qq-control",
        "/api/v1/voice",
        "/api/v1/fitness",
        "/api/v1/demon-slayer",
        "/api/v1/calendar",
        "/api/v1/memories",
        "/focus/",
    ):
        assert route not in html


def check_public_readme_contract() -> None:
    readme = PUBLIC_README.read_text(encoding="utf-8")
    assert "模块 ID 默认由 Core 从已验证的包内" in readme
    assert "预期模块 ID”只是可选的高级核对项" in readme
    assert "POST /api/v1/modules/install-upload" in readme
    assert "POST /api/v1/modules/{module_id}/install-upload" in readme
    assert "浏览器式 status GET 不携带 Origin 时可读" in readme
    assert '{"confirmation":"restart-project-kei-core"}' in readme
    assert "QQ 模块卡提供本机 AppID/Secret 配置表单" in readme
    assert "Secret 永不回显" in readme
    assert "ASR 的“选择模型" in readme
    assert "GPT-SoVITS 的" in readme and "选择已有引擎目录" in readme
    assert "/api/v1/voice-control/asr/model-directory/select" in readme
    assert "/api/v1/gpt-sovits-engine/select-existing" in readme
    assert "浏览器不会提交路径、" in readme


def check_manifest_inventory() -> None:
    manifests = package_manifests()
    assert len(manifests) == len(INSTALLABLE_MODULE_IDS)
    records = [json.loads(path.read_text(encoding="utf-8")) for path in manifests]
    assert tuple(sorted(record["id"] for record in records)) == INSTALLABLE_MODULE_IDS
    dashboard_records = [record for record in records if record.get("dashboard_entrypoint")]
    assert len(dashboard_records) == 19
    assert next(record for record in records if record["id"] == "youtube").get(
        "dashboard_entrypoint"
    ) in (None, "")
    for manifest, record in zip(manifests, records):
        entrypoint = record.get("dashboard_entrypoint")
        if not entrypoint:
            continue
        source = (manifest.parent / entrypoint).read_text(encoding="utf-8")
        assert re.search(r"(?<![.\w])fetch\s*\(", source) is None, manifest


def check_javascript_contract() -> None:
    expected_scripts = {
        "app.js",
        "avatar-store.js",
        "briefing-progress.js",
        "core-status.js",
        "gpt-sovits-control.js",
        "module-loader.js",
        "module-management.js",
        "notifications.js",
        "panels.js",
        "registry.js",
        "request.js",
        "restart-control.js",
        "status-visuals.js",
        "theme.js",
    }
    scripts = sorted(DASHBOARD_ASSETS.glob("*.js"))
    assert {path.name for path in scripts} == expected_scripts
    for path in scripts:
        run_node(["--check", str(path)])

    app = (DASHBOARD_ASSETS / "app.js").read_text(encoding="utf-8")
    core = (DASHBOARD_ASSETS / "core-status.js").read_text(encoding="utf-8")
    loader = (DASHBOARD_ASSETS / "module-loader.js").read_text(encoding="utf-8")
    manager = (DASHBOARD_ASSETS / "module-management.js").read_text(encoding="utf-8")
    restart = (DASHBOARD_ASSETS / "restart-control.js").read_text(encoding="utf-8")
    gpt_sovits = (DASHBOARD_ASSETS / "gpt-sovits-control.js").read_text(encoding="utf-8")
    panels = (DASHBOARD_ASSETS / "panels.js").read_text(encoding="utf-8")
    css = (DASHBOARD_ASSETS / "shell.css").read_text(encoding="utf-8")

    assert "service-control-state" in core
    assert "external.setAttribute('role', 'status')" in core
    assert "stop.disabled" not in core
    assert "#services {\n  grid-template-columns:repeat(2,minmax(0,1fr))" in css
    assert "grid-template-columns:58px minmax(0,1fr);" in css
    assert "grid-column:1/-1;" in css
    assert "@media (min-width:421px) and (max-width:760px)" in css
    assert ".service-status-control" in css
    assert "'暂无目录更新'" in manager

    assert "loadLegacy" not in app and "briefing-progress" not in app
    assert "coreStatus.refresh()" in app
    assert "moduleManagement.refreshInstalled()" in app
    assert "moduleManagement.readOfficialCache()" in app
    assert "restartControl.refreshStatus()" in app
    assert "gptSovitsControl.refreshStatus()" in app
    assert "setInterval(() => void coreStatus.refresh()" in app
    assert "/dashboard/status" in core
    assert "/api/v1/qq-control/status" in core
    assert "/api/v1/voice-control/status" in core
    for route in (
        "/api/v1/voice-control/asr/start-background",
        "/api/v1/voice-control/gpt-sovits/start-background",
        "/api/v1/qq-control/stop",
        "/api/v1/voice-control/asr/stop",
        "/api/v1/voice-control/gpt-sovits/stop",
    ):
        assert route in core
    assert "control?.can_stop !== true" in core
    assert "external.className = 'service-status-control service-control-state'" in core
    assert "globalThis.confirm" in core
    assert "start.title = '在后台启动，不打开调试窗口。'" in core
    assert "start.textContent = '启动服务'" in core
    assert "value?.process_running === true" in core
    assert "ready ? '启动' : '未启动'" in core
    assert "key !== 'qq'" in core
    for route in ("/api/v1/relationship", "/api/v1/briefing"):
        assert route not in core

    with tempfile.TemporaryDirectory(prefix="kei-pk100-service-controls-") as temp_dir:
        module_path = Path(temp_dir) / "core-status.mjs"
        module_path.write_text(core, encoding="utf-8")
        (Path(temp_dir) / "status-visuals.js").write_text(
            "export function setupServiceStatusVisuals() {}\n",
            encoding="utf-8",
        )
        node_script = f"""
import {{pathToFileURL}} from 'node:url';
const listeners = [];
class Element {{
  constructor(tag) {{
    this.tag = tag; this.children = []; this.dataset = {{}}; this.style = {{}};
    this.classList = {{toggle() {{}}, remove() {{}}}};
  }}
  append(...items) {{ this.children.push(...items); }}
  replaceChildren(...items) {{ this.children = [...items]; }}
  addEventListener(type, callback) {{ listeners.push([this.textContent, type, callback]); }}
  setAttribute() {{}}
  querySelector() {{ return null; }}
  querySelectorAll() {{ return []; }}
}}
const elements = Object.fromEntries(['services','overall','overall-dot','updated'].map((id) => [id, new Element(id)]));
const documentRoot = {{
  body: new Element('body'),
  createElement: (tag) => new Element(tag),
  querySelector: (selector) => elements[selector.replace('#', '')] || null,
  querySelectorAll: () => [],
}};
globalThis.document = documentRoot;
globalThis.window = {{setTimeout, clearTimeout, location: {{href:'http://127.0.0.1:8000/dashboard', origin:'http://127.0.0.1:8000'}}}};
globalThis.confirm = () => true;
const requests = [];
let phase = 'ready';
const request = async (path, options={{}}) => {{
  requests.push([path, options.method || 'GET']);
  if (path === '/dashboard/status') return {{services: {{
    api: {{ok:true}}, asr: {{ok:false}}, tts: {{ok:false}}, llm: {{configured:true}}
  }}}};
  if (path === '/api/v1/qq-control/status') return {{process_running:false}};
  if (path === '/api/v1/voice-control/status') return {{
    asr: phase === 'ready' ? {{state:'ready', running:false}} : {{state:'running', running:true, can_stop:true}},
    'gpt-sovits': {{state:'ready', running:false}},
  }};
  if (path.endsWith('/start-background')) {{ phase = 'running'; return {{started:true}}; }}
  if (path.endsWith('/stop')) {{ phase = 'ready'; return {{stopped:true}}; }}
  throw new Error('unexpected path ' + path);
}};
const module = await import(pathToFileURL({json.dumps(str(module_path))}).href);
const controller = module.createCoreStatusController({{request, notify() {{}}, documentRoot}});
await controller.refresh();
const starts = listeners.filter(([label, type]) => label === '启动服务' && type === 'click');
if (starts.length !== 2) throw new Error('expected two background start buttons');
await starts[0][2]();
if (requests.filter(([path, method]) => path === '/api/v1/voice-control/asr/start-background' && method === 'POST').length !== 1) throw new Error('ASR background POST mismatch');
if (requests.some(([path]) => path === '/api/v1/voice-control/asr/start')) throw new Error('debug route was used by top card');
const stop = listeners.find(([label, type]) => label === '关闭服务' && type === 'click');
if (!stop) throw new Error('owned running service has no stop button');
await stop[2]();
if (requests.filter(([path, method]) => path === '/api/v1/voice-control/asr/stop' && method === 'POST').length !== 1) throw new Error('ASR stop POST mismatch');
"""
        run_node(["--input-type=module", "-"], input_text=node_script)

    assert "const active = new Map()" in loader
    assert "let operationQueue = Promise.resolve()" in loader
    assert "registry.unregister(moduleId)" in loader
    assert "beforeLifecycleAction" in loader
    assert "entrypoint.pathname.startsWith(prefix)" in loader
    assert "module-group-intelligence" in loader
    assert "module-group-voice" in loader
    for module_id in (
        "intel_sources",
        "x_monitor",
        "bilibili",
        "github_intel",
        "papers",
        "rss_intel",
        "voice",
        "voice_pack_registry",
        "voice_pack_distribution",
    ):
        assert module_id in loader
    assert "data-module-group-tab" in loader
    assert "aria-selected" in loader
    assert "projectOwnedConfiguration" in loader
    assert "data-module-config-target" in loader
    assert "eval(" not in loader and "new Function" not in loader
    assert "['catalog', 'module_manager', 'dashboard']" in manager
    assert "后台 Collector / 服务模块，无独立面板。" in manager
    assert "首批只有 focus" not in manager
    assert "package_path" not in manager
    assert "type = 'url'" not in manager
    assert "/api/v1/modules/install-upload" in manager
    assert "expected_module_id=" in manager
    assert "X-Project-Kei-Package-SHA256" in manager
    assert "application/zip" in manager
    assert "crypto.subtle.digest('SHA-256'" in manager
    assert "文件名不会作为模块身份" in manager
    assert "suggestedModuleIdFromFilename" not in manager
    assert "localUploadSelectionVersion" in manager
    assert "data-local-module-id-choice" in manager
    assert "showModal" in manager and "event.preventDefault()" in manager
    assert "localModuleUploadMaxBytes = 64 * 1024 * 1024" in manager
    assert "runtimeRequirementsText" in manager
    assert "runtimeReadinessText" in manager
    assert "dependencyReadinessText" in manager
    assert "模块依赖检查" in manager
    assert "setup.bat --profile qq" in manager
    assert "模块安装不会静默运行" in manager
    assert "buildOfficialBatchPlan" in manager
    assert "runOfficialBatchQueue" in manager
    assert "reconcileOfficialModules" in manager
    assert "compareModuleVersions" in manager
    assert "strictRegistryModuleId" in manager
    assert "BigInt(match[1])" in manager and "BigInt(leftPart)" in manager
    assert "package_source !== 'official_github_release'" in manager
    assert "下载并更新" in manager and "本机版本较新" in manager
    assert "await reloadLocalModuleViews(officialState.message)" in manager
    assert "await officialRequest(request, item, 'install_official')" in manager
    assert "Promise.all" not in manager
    assert "批量安装已停止" in manager and "未执行" in manager
    assert "可手动刷新后继续操作" in manager
    zip_selection_source = manager.split("async function selectLocalModuleZip", 1)[1].split(
        "async function installLocalModuleZip", 1
    )[0]
    assert "request(" not in zip_selection_source
    assert "id && !localModuleIdPattern.test(id)" in manager
    assert "/api/v1/dashboard/service/restart/status" in restart
    assert "/api/v1/dashboard/service/restart" in restart
    assert "restart-project-kei-core" in restart
    assert "JSON.stringify({ confirmation: restartConfirmation })" in restart
    assert "kill(" not in restart and "pid" not in restart.lower() and "command" not in restart.lower()
    assert "/api/v1/gpt-sovits-engine/status" in gpt_sovits
    assert "/api/v1/gpt-sovits-engine/select-existing" in gpt_sovits
    assert "method: 'POST'" in gpt_sovits
    assert "body:" not in gpt_sovits
    assert "GitHub Token" not in manager and "Cookie" not in manager
    assert "feature-center" in panels
    assert "start-qq-bridge" not in panels
    assert "project-kei.dashboard.compact-cards.v2" in panels
    assert "Object.keys(state).forEach" in panels
    for theme in ("cloud", "sakura", "moon"):
        assert f'[data-theme="{theme}"]' in css
    assert "prefers-reduced-motion" in css
    assert "overflow-x:clip" in css.replace(" ", "")
    assert "@media(max-width:720px)" in css.replace(" ", "")
    compact_css = re.sub(r"\s+", "", css)
    assert "body>main>.core-status-summary" in compact_css
    assert "body>main>.module-management" not in compact_css
    assert "body>main>.dynamic-modules-region" in compact_css
    assert "#dashboard-module-mounts:not(:empty){display:grid" in compact_css
    assert "grid-template-columns:repeat(3,minmax(0,1fr))" in compact_css
    assert "#dashboard-module-mounts>section.module-group:not(.collapsed){grid-column:1/-1;}" in compact_css
    assert ".module-panel-host>.module-mount-content>.module-owned-panels" in compact_css
    assert ".module-group-panel[hidden]{display:none;}" in compact_css
    assert ".module-group-tabs{position:sticky;" in compact_css
    shared_detail_layout = (
        '.section.has-module-shell-header:not(.collapsed)>.module-shell-layout'
        '{display:grid;grid-template-columns:minmax(220px,280px)minmax(0,1fr)'
    )
    assert shared_detail_layout in compact_css
    intelligence_layout_override = (
        '.section.module-group[data-dashboard-group="intelligence"]'
        '.has-module-shell-header:not(.collapsed)>.module-shell-layout'
    )
    assert intelligence_layout_override not in compact_css
    assert (
        '[data-dashboard-group="intelligence"].has-module-shell-header:not(.collapsed)'
        '>.module-shell-header-generated'
    ) not in compact_css
    assert (
        '.section.module-group[data-dashboard-group="intelligence"]{overflow:visible;}'
        in compact_css
    )
    assert ".x-monitor-users>details.module-card>summary>img" in compact_css
    assert "width:52px;height:52px" in compact_css
    assert "'module-group-intelligence': Object.freeze" in panels
    assert "avatar: 'intel-sources.png'" in panels
    assert "'configuration-readiness': Object.freeze" in panels
    assert "avatar: 'configuration.png'" in panels
    assert "'module-group-voice': Object.freeze" in panels
    assert "avatar: 'voice-pack.png'" in panels
    assert "#dashboard-module-mounts:not(:empty){display:contents" not in compact_css
    assert "'/dashboard/assets/qq-launch.png'" in panels
    assert "force:true" in re.sub(r"\s+", "", panels)
    assert "enhanceQQLaunchVisual" in panels
    assert "start.click()" in panels
    assert "'module-affection': Object.freeze" in panels
    assert "'module-long-term-memory': Object.freeze" in panels
    assert ".qq-launch-fallback-control{display:none!important;}" in compact_css
    assert ".module-configuration-guide>a{" in compact_css
    assert ".official-module-batch-toolbar[hidden]{display:none;}" in compact_css
    assert ".official-module-choice:focus-within{" in compact_css

    with tempfile.TemporaryDirectory(prefix="kei-dashboard-js-") as temp_dir:
        root = Path(temp_dir)
        for name in (
            "request", "module-loader", "registry", "module-management", "theme",
            "restart-control", "gpt-sovits-control",
        ):
            source = (DASHBOARD_ASSETS / f"{name}.js").read_text(encoding="utf-8")
            source = source.replace("'./request.js?v=pk100-20260808-localzip2'", "'./request.mjs'")
            (root / f"{name}.mjs").write_text(source, encoding="utf-8")

        loader_url = (root / "module-loader.mjs").as_uri()
        request_url = (root / "request.mjs").as_uri()
        registry_url = (root / "registry.mjs").as_uri()
        manager_url = (root / "module-management.mjs").as_uri()
        theme_url = (root / "theme.mjs").as_uri()
        restart_url = (root / "restart-control.mjs").as_uri()
        gpt_sovits_url = (root / "gpt-sovits-control.mjs").as_uri()
        probe = f"""
globalThis.window = {{
  location: {{href:'http://127.0.0.1:8765/dashboard', origin:'http://127.0.0.1:8765'}},
  setTimeout, clearTimeout,
}};
const loader = await import({loader_url!r});
const request = await import({request_url!r});
const registryModule = await import({registry_url!r});
const manager = await import({manager_url!r});
const theme = await import({theme_url!r});
const restart = await import({restart_url!r});
const gptSovits = await import({gpt_sovits_url!r});
const localDigest = await manager.sha256Hex(new Blob(['kei']));
if (localDigest !== '368848dc82d198e1c7cb0ae4aba2781e181e19e7a275405caf2af6399b1b4244')
  throw new Error('local package SHA-256 failed');
if (manager.manualModuleIdNeedsConfirmation('manifest', 'old_module'))
  throw new Error('automatic id incorrectly prompted during package swap');
if (!manager.manualModuleIdNeedsConfirmation('manual', 'old_module'))
  throw new Error('manual id did not require package-swap confirmation');
if (restart.restartConfirmation !== 'restart-project-kei-core')
  throw new Error('restart confirmation contract drifted');
if (restart.boundedRetryDelay(1) !== 250 || restart.boundedRetryDelay(99999) !== 5000)
  throw new Error('restart retry bounds drifted');
if (!gptSovits.statusCopy({{registration_state:'registered_existing',
  integrity_status:'unverified_existing_install'}}).includes('尚未由'))
  throw new Error('unverified existing engine state was hidden');
const focus = {{key:'focus', enabled:true,
  dashboard_entrypoint:'/api/v1/modules/focus/assets/dashboard/index.js'}};
if (!loader.shouldLoadModule(focus) || !loader.isTrustedModuleEntrypoint(focus))
  throw new Error('trusted enabled module rejected');
if (loader.shouldLoadModule({{...focus, enabled:false}}))
  throw new Error('disabled module accepted');
const configuringSidecar = {{key:'qq_bridge', type:'sidecar', enabled:false,
  install_status:'needs_configuration',
  dashboard_entrypoint:'/api/v1/modules/qq_bridge/assets/dashboard/index.js'}};
if (!loader.shouldLoadModule(configuringSidecar)
    || !loader.isTrustedModuleEntrypoint(configuringSidecar))
  throw new Error('configuration sidecar rejected');
if (loader.isTrustedModuleEntrypoint({{...focus,
  dashboard_entrypoint:'https://example.com/index.js'}}))
  throw new Error('remote entrypoint accepted');
if (loader.isTrustedModuleEntrypoint({{...focus,
  dashboard_entrypoint:'/dashboard/static/app.js'}}))
  throw new Error('foreign same-origin entrypoint accepted');
let blocked = false;
try {{ request.resolveSameOriginUrl('https://example.com/'); }}
catch (error) {{ blocked = error.code === 'cross_origin'; }}
if (!blocked) throw new Error('cross-origin request accepted');
const scoped = request.createScopedRequest({{
  key:'focus', api_namespaces:['/api/v1/focus'], legacy_endpoints:['/focus']
}});
blocked = false;
try {{ scoped('/api/v1/calendar/status'); }}
catch (error) {{ blocked = error.code === 'namespace_denied'; }}
if (!blocked) throw new Error('undeclared namespace accepted');
const lifecycle = {{mount(){{globalThis.mounts=(globalThis.mounts||0)+1;}},
  unmount(){{globalThis.unmounts=(globalThis.unmounts||0)+1;}}}};
const registry = registryModule.createModuleRegistry();
registry.register('fixture', lifecycle);
await registry.mount('fixture', {{}});
await registry.mount('fixture', {{}});
if (globalThis.mounts !== 1) throw new Error('duplicate mount');
await registry.unregister('fixture');
if (globalThis.unmounts !== 1) throw new Error('unmount missing');
if (manager.coreModuleIds.join(',') !== 'catalog,module_manager,dashboard')
  throw new Error('wrong fixed Core set');
if (manager.isBuiltinFeature({{key:'calendar'}}))
  throw new Error('business module treated as Core');
if (!manager.isBuiltinFeature({{key:'dashboard'}}))
  throw new Error('dashboard not protected');
if (manager.allowedLifecycleActions({{
  key:'dashboard', managed:true, installed_version:'1.0.0',
  install_status:'enabled', available_actions:['disable','uninstall']
}}).length) throw new Error('Core destructive action exposed');
const optional = manager.allowedLifecycleActions({{
  key:'calendar', managed:true, installed_version:'1.0.0',
  install_status:'enabled', available_actions:['disable','uninstall','purge_data']
}});
if (optional.join(',') !== 'disable,uninstall,purge_data')
  throw new Error('optional lifecycle actions lost');
const officialFixture = (id, dependencies = [], compatible = true) => ({{
  module_id:id, name:id, version:'1.0.0', dependencies, optional_dependencies:[],
  permissions:['local_state'], package_size:10, compatible,
  available_actions:['install_official'],
}});
const officialCatalog = modules => ({{
  source:{{owner:'songshu-yu',repository:'Project-Kei-Modules'}}, modules,
}});
const batchCatalog = officialCatalog([
  officialFixture('feature',['support']), officialFixture('support'),
]);
const batchPlan = manager.buildOfficialBatchPlan(
  batchCatalog, {{modules:[]}}, new Set(['feature@1.0.0','support@1.0.0']),
);
if (batchPlan.queue.map(item => item.module_id).join(',') !== 'support,feature')
  throw new Error('batch dependency order is not deterministic');
if (batchPlan.totalBytes !== 20 || batchPlan.permissions.join(',') !== 'local_state')
  throw new Error('batch confirmation summary is incomplete');
const installedDependencyPlan = manager.buildOfficialBatchPlan(
  officialCatalog([officialFixture('feature',['support'])]),
  {{modules:[{{key:'legacy-support',module_id:'support',managed:true,installed_version:'1.0.0',install_status:'enabled'}}]}},
  new Set(['feature@1.0.0']),
);
if (installedDependencyPlan.queue.map(item => item.module_id).join(',') !== 'feature')
  throw new Error('installed dependency was not treated as satisfied');
for (const [catalog, keys, code] of [
  [officialCatalog([officialFixture('feature',['missing'])]), ['feature@1.0.0'], 'batch_dependency_missing'],
  [officialCatalog([officialFixture('a',['b']),officialFixture('b',['a'])]), ['a@1.0.0','b@1.0.0'], 'batch_dependency_cycle'],
  [officialCatalog([officialFixture('bad',[],false)]), ['bad@1.0.0'], 'batch_module_incompatible'],
]) {{
  let rejected = '';
  try {{ manager.buildOfficialBatchPlan(catalog, {{modules:[]}}, new Set(keys)); }}
  catch (error) {{ rejected = error.code; }}
  if (rejected !== code) throw new Error(`batch preflight did not fail closed: ${{code}}`);
}}
const installedRecord = (id, version, source = 'official_github_release') => ({{
  key:id, module_id:id, managed:true, installed_version:version,
  install_status:'enabled', package_source:source, available_actions:['update_official'],
}});
const versionedRelease = (id, version, compatible = true) => ({{
  ...officialFixture(id, [], compatible), version,
  available_actions:['install_official','update_official'],
}});
if (!(manager.compareModuleVersions('1.0.0-rc.2','1.0.0-rc.10') < 0)
    || !(manager.compareModuleVersions('1.0.0','1.0.0-rc.10') > 0)
    || manager.compareModuleVersions('1.0.0+build.2','1.0.0+build.1') !== 0)
  throw new Error('controlled SemVer order diverged from Core');
if (manager.compareModuleVersions('9007199254740992.0.0','9007199254740993.0.0') !== -1
    || manager.compareModuleVersions('9007199254740993.0.0','9007199254740992.0.0') !== 1)
  throw new Error('large Core SemVer fields lost integer precision');
if (manager.compareModuleVersions('1.0.0-9007199254740992','1.0.0-9007199254740993') !== -1
    || manager.compareModuleVersions('1.0.0-9007199254740993','1.0.0-9007199254740992') !== 1)
  throw new Error('large numeric prerelease fields lost integer precision');
const nativeBigInt = globalThis.BigInt;
let missingBigIntRejected = false;
try {{
  globalThis.BigInt = undefined;
  manager.compareModuleVersions('1.0.0','1.0.1');
}} catch (_error) {{ missingBigIntRejected = true; }}
finally {{ globalThis.BigInt = nativeBigInt; }}
if (!missingBigIntRejected) throw new Error('missing BigInt silently fell back to Number');
let invalidSemverRejected = false;
try {{ manager.compareModuleVersions('1.0','1.0.0'); }}
catch (_error) {{ invalidSemverRejected = true; }}
if (!invalidSemverRejected) throw new Error('invalid SemVer was accepted');
const versionCatalog = officialCatalog([
  versionedRelease('fresh','1.0.0'),
  versionedRelease('same','1.0.0'),
  versionedRelease('older','1.1.0'),
  versionedRelease('newer','1.0.0'),
  versionedRelease('blocked','2.0.0',false),
  versionedRelease('foreign','2.0.0'),
  versionedRelease('multi','1.1.0'),
  versionedRelease('multi','1.2.0'),
]);
const versionRegistry = {{modules:[
  installedRecord('same','1.0.0'), installedRecord('older','1.0.0'),
  installedRecord('newer','2.0.0'), installedRecord('blocked','1.0.0'),
  installedRecord('foreign','1.0.0','local_import'), installedRecord('multi','1.0.0'),
]}};
const versionViews = manager.reconcileOfficialModules(versionCatalog, versionRegistry);
const stateOf = (id, version) => versionViews.find(item => item.module_id === id && item.version === version)?.comparison_state;
if (stateOf('fresh','1.0.0') !== 'install') throw new Error('uninstalled module not installable');
if (stateOf('same','1.0.0') !== 'installed') throw new Error('same version not converged');
if (stateOf('older','1.1.0') !== 'update') throw new Error('newer official version not updatable');
if (stateOf('newer','1.0.0') !== 'local_newer') throw new Error('older cloud version treated as update');
if (stateOf('blocked','2.0.0') !== 'incompatible') throw new Error('incompatible update exposed');
if (stateOf('foreign','2.0.0') !== 'source_conflict') throw new Error('foreign source overwrite exposed');
if (stateOf('multi','1.1.0') !== 'superseded' || stateOf('multi','1.2.0') !== 'update')
  throw new Error('multiple official versions produced an ambiguous target');
const alphaCatalog = officialCatalog([versionedRelease('alpha','1.0.0')]);
const alphaState = registry => manager.reconcileOfficialModules(alphaCatalog, registry)[0].comparison_state;
if (alphaState({{modules:[{{...installedRecord('alpha','1.0.0'),key:'wrong'}}]}}) !== 'installed')
  throw new Error('registry module_id was incorrectly replaced by key');
if (alphaState({{modules:[{{...installedRecord('beta','1.0.0'),key:'alpha'}}]}}) !== 'install')
  throw new Error('registry key was incorrectly accepted as module_id');
if (alphaState({{modules:[{{...installedRecord('alpha','1.0.0'),module_id:'',key:'alpha'}}]}}) !== 'install')
  throw new Error('empty registry module_id was not ignored');
const alphaFirst = {{...installedRecord('alpha','1.0.0'),key:'first',label:'First',package_source:'official_github_release'}};
const alphaSecond = {{...installedRecord('alpha','0.9.0','local_import'),key:'second',label:'Second'}};
const conflictForward = manager.reconcileOfficialModules(alphaCatalog, {{modules:[alphaFirst,alphaSecond]}});
const conflictReverse = manager.reconcileOfficialModules(alphaCatalog, {{modules:[alphaSecond,alphaFirst]}});
if (JSON.stringify(conflictForward) !== JSON.stringify(conflictReverse)
    || conflictForward[0].comparison_state !== 'registry_conflict'
    || conflictForward[0].local_module !== null
    || ['install','update'].includes(conflictForward[0].comparison_state))
  throw new Error('duplicate registry conflict leaked order-dependent candidate data');
for (const registry of [{{modules:[alphaFirst,alphaSecond]}},{{modules:[alphaSecond,alphaFirst]}}]) {{
  let conflictBatchCode = '';
  try {{ manager.buildOfficialBatchPlan(alphaCatalog, registry, new Set(['alpha@1.0.0'])); }}
  catch (error) {{ conflictBatchCode = error.code; }}
  if (conflictBatchCode !== 'batch_selection_stale')
    throw new Error('duplicate registry conflict entered batch install');
}}
const batchKeys = manager.buildOfficialBatchPlan(
  officialCatalog([versionedRelease('fresh','1.0.0'),versionedRelease('same','1.0.0')]),
  {{modules:[installedRecord('same','1.0.0')]}}, new Set(['fresh@1.0.0']),
).queue.map(item => item.module_id);
if (batchKeys.join(',') !== 'fresh') throw new Error('installed/update module entered batch install');
const updateCalls = [];
await manager.officialRequest(async (path, options) => {{
  updateCalls.push([path, options]);
  return {{installed_version:'1.1.0'}};
}}, versionViews.find(item => item.module_id === 'older'), 'update_official');
if (updateCalls.length !== 1
    || updateCalls[0][0] !== '/api/v1/modules/older/update-official'
    || updateCalls[0][1].method !== 'POST'
    || updateCalls[0][1].body !== JSON.stringify({{version:'1.1.0',confirmation:'older@1.1.0'}}))
  throw new Error('official update did not use the single frozen lifecycle request');
let activeBatchRequests = 0;
let maxActiveBatchRequests = 0;
const batchCalls = [];
const serialResult = await manager.runOfficialBatchQueue(batchPlan.queue, async item => {{
  activeBatchRequests += 1;
  maxActiveBatchRequests = Math.max(maxActiveBatchRequests, activeBatchRequests);
  batchCalls.push(item.module_id);
  await new Promise(resolve => setTimeout(resolve, 2));
  activeBatchRequests -= 1;
}});
if (maxActiveBatchRequests !== 1 || batchCalls.join(',') !== 'support,feature'
    || serialResult.failed !== null)
  throw new Error('batch installs were not strictly serial');
const stoppedQueue = [officialFixture('first'), officialFixture('second'), officialFixture('third')];
const stoppedCalls = [];
const stoppedResult = await manager.runOfficialBatchQueue(stoppedQueue, async item => {{
  stoppedCalls.push(item.module_id);
  if (item.module_id === 'second') throw new Error('fixture failure');
}});
if (stoppedCalls.join(',') !== 'first,second' || stoppedResult.completed.length !== 1
    || stoppedResult.failed.module_id !== 'second'
    || stoppedResult.remaining.map(item => item.module_id).join(',') !== 'third')
  throw new Error('batch failure result was not bounded');
const successfulState = manager.recoverOfficialModuleState(manager.createOfficialModuleState({{
  phase:'success', catalog:batchCatalog, message:'installed',
}}));
if (successfulState.phase !== 'cache_ready' || successfulState.message !== 'installed')
  throw new Error('single install remained in a blocking success phase');
const refreshFailureState = manager.recoverOfficialModuleState(manager.createOfficialModuleState({{
  phase:'installing', catalog:batchCatalog,
}}), {{failed:true, message:'refresh failed'}});
if (refreshFailureState.phase !== 'failed' || refreshFailureState.message !== 'refresh failed')
  throw new Error('refresh failure did not recover interaction');
if (theme.defaultDashboardTheme !== 'cloud') throw new Error('wrong default theme');
if (theme.normalizeDashboardTheme('bad') !== 'cloud') throw new Error('theme fallback failed');
const badStorage = {{getItem(){{throw new Error('blocked');}},
  setItem(){{throw new Error('blocked');}}}};
if (theme.readDashboardTheme(badStorage) !== 'cloud') throw new Error('storage fallback failed');
theme.writeDashboardTheme(badStorage, 'moon');
"""
        run_node(["--input-type=module", "-e", probe])
    preview_record = _module_record("focus", managed=True, enabled=True)
    assert preview_record["module_id"] == "focus"
    assert preview_record["key"] == "focus"


def check_static_asset_boundary() -> None:
    response = asyncio.run(dashboard_static_asset("shell.css"))
    assert Path(response.path).resolve() == (DASHBOARD_ASSET_ROOT / "shell.css").resolve()
    assert response.headers["cache-control"] == "no-store, max-age=0"
    avatar = asyncio.run(dashboard_static_asset("default-avatars/configuration.png"))
    assert Path(avatar.path).is_file()
    voice_avatar = asyncio.run(dashboard_static_asset("default-avatars/voice-pack.png"))
    assert Path(voice_avatar.path).is_file()
    assert len(list((DASHBOARD_ASSETS / "default-avatars").glob("*.png"))) == 16
    try:
        asyncio.run(dashboard_static_asset("../dashboard.html"))
    except HTTPException as exc:
        assert exc.status_code == 404
    else:
        raise AssertionError("dashboard asset route allowed path traversal")


def check_ui_asset_api() -> None:
    async def exercise() -> None:
        with tempfile.TemporaryDirectory(prefix="kei-dashboard-ui-") as temp_dir:
            app = FastAPI()
            app.include_router(
                create_dashboard_ui_router(
                    DashboardUiAssetStore(Path(temp_dir)),
                    local_control_guard=lambda _request: True,
                )
            )
            image = (DASHBOARD_ASSETS / "default-avatars" / "configuration.png").read_bytes()
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(
                transport=transport, base_url="http://testserver"
            ) as client:
                empty = await client.get("/api/v1/dashboard/ui-assets")
                assert empty.status_code == 200 and empty.json() == {"avatars": []}
                saved = await client.put(
                    "/api/v1/dashboard/ui-assets/module-group-intelligence/avatar",
                    content=image,
                    headers={"content-type": "image/png"},
                )
                assert saved.status_code == 200
                assert saved.json()["panel_id"] == "module-group-intelligence"
                listed = await client.get("/api/v1/dashboard/ui-assets")
                assert [item["panel_id"] for item in listed.json()["avatars"]] == [
                    "module-group-intelligence"
                ]
                loaded = await client.get(
                    "/api/v1/dashboard/ui-assets/module-group-intelligence/avatar"
                )
                assert loaded.status_code == 200 and loaded.content == image
                deleted = await client.delete(
                    "/api/v1/dashboard/ui-assets/module-group-intelligence/avatar"
                )
                assert deleted.json() == {
                    "panel_id": "module-group-intelligence",
                    "deleted": True,
                }

    asyncio.run(exercise())


def _module_record(
    module_id: str,
    *,
    managed: bool,
    enabled: bool,
    dashboard_entrypoint: str | None = None,
) -> dict:
    installed = "1.0.0" if managed else None
    actions = ["configuration_check"]
    if managed:
        actions += ["disable" if enabled else "enable", "uninstall", "purge_data"]
    return {
        "key": module_id,
        "module_id": module_id,
        "label": module_id.replace("_", " ").title(),
        "required": module_id in CORE_MODULE_IDS,
        "managed": managed,
        "installed_version": installed,
        "install_status": "enabled" if enabled else (
            "installed_disabled" if managed else "available"
        ),
        "enabled": enabled,
        "configuration_ready": True,
        "dependencies": [],
        "optional_dependencies": [],
        "conflicts": [],
        "permissions": ["local_state"] if managed else [],
        "requires_restart": managed,
        "restart_required": False,
        "dashboard_entrypoint": dashboard_entrypoint,
        "api_namespaces": [f"/api/v1/{module_id.replace('_', '-')}"] if managed else [],
        "legacy_endpoints": [],
        "target_namespace": f"/api/v1/{module_id.replace('_', '-')}",
        "package_source": "official_github_release" if managed else "core",
        "available_actions": actions,
        "previous_version": None,
        "last_operation": None,
        "data_policy": "preserve_on_uninstall",
    }


def create_preview_app() -> FastAPI:
    """Return a sanitized local-only app for read-only Browser acceptance."""
    app = FastAPI(title="Project Kei PK-100 preview")
    calls: list[str] = []
    intelligence_modules = {
        "intel_sources",
        "x_monitor",
        "bilibili",
        "github_intel",
        "papers",
        "rss_intel",
    }
    preview_modules = intelligence_modules | {"focus"}
    installed_fixture = set(preview_modules | {"calendar", "youtube"})
    restart_fixture = {"generation": 4, "pending": False}
    gpt_sovits_fixture = {
        "registration_state": "unregistered",
        "integrity_status": "not_registered",
        "selection_in_progress": False,
        "can_select_existing": True,
    }

    @app.middleware("http")
    async def audit(request, call_next):
        calls.append(f"{request.method} {request.url.path}")
        return await call_next(request)

    @app.get("/dashboard")
    async def dashboard():
        return FileResponse(DASHBOARD_HTML, media_type="text/html; charset=utf-8")

    @app.get("/dashboard/static/{asset_path:path}")
    async def static_asset(asset_path: str):
        return await dashboard_static_asset(asset_path)

    @app.get("/dashboard/status")
    async def status():
        return {
            "status": "degraded",
            "services": {
                "api": {"ok": True, "url": "http://127.0.0.1"},
                "asr": {"ok": False, "error": "只读验收未连接 ASR"},
                "tts": {"ok": False, "error": "只读验收未连接 TTS"},
                "llm": {"configured": True, "base_url": "本机配置（未调用）"},
            },
            "server_time": datetime.now(timezone.utc).isoformat(),
        }

    @app.get("/api/v1/dashboard/service/restart/status")
    async def restart_status():
        if restart_fixture["pending"]:
            restart_fixture["pending"] = False
            restart_fixture["generation"] += 1
        return {
            "available": True,
            "state": "running",
            "scope": "project-kei-core",
            "request_id": None,
            "generation": restart_fixture["generation"],
            "retry_after_ms": 250,
            "message": "受控重启已就绪。",
        }

    @app.post("/api/v1/dashboard/service/restart", status_code=202)
    async def restart_service(request: Request):
        body = await request.json()
        if body != {"confirmation": "restart-project-kei-core"}:
            raise HTTPException(status_code=400, detail="invalid restart confirmation")
        restart_fixture["pending"] = True
        return {
            "available": True,
            "state": "accepted",
            "scope": "project-kei-core",
            "request_id": "pk100-fake-restart",
            "generation": restart_fixture["generation"],
            "retry_after_ms": 250,
            "message": "已接受受控重启请求。",
        }

    @app.get("/api/v1/gpt-sovits-engine/status")
    async def gpt_sovits_status():
        return dict(gpt_sovits_fixture)

    @app.post("/api/v1/gpt-sovits-engine/select-existing")
    async def gpt_sovits_select_existing(request: Request):
        if request.url.query or (await request.body()).strip():
            raise HTTPException(status_code=422, detail="invalid_request")
        gpt_sovits_fixture.update(
            {
                "action": "cancelled",
                "selection_in_progress": False,
                "can_select_existing": True,
            }
        )
        return dict(gpt_sovits_fixture)

    @app.get("/api/v1/modules")
    async def modules():
        core = [
            _module_record(module_id, managed=False, enabled=True)
            for module_id in CORE_MODULE_IDS
        ]
        business = [
            _module_record(
                module_id,
                managed=module_id in installed_fixture,
                enabled=module_id in preview_modules,
                dashboard_entrypoint=(
                    f"/api/v1/modules/{module_id}/assets/dashboard/index.js"
                    if module_id in preview_modules
                    else None
                ),
            )
            for module_id in INSTALLABLE_MODULE_IDS
        ]
        return {"modules": core + business, "module_manager_error": None}

    def official_catalog() -> dict:
        modules = []
        for module_id in OFFICIAL_MODULE_IDS:
            modules.append(
                {
                    "module_id": module_id,
                    "name": module_id.replace("_", " ").title(),
                    "version": "1.0.0",
                    "core_compatibility": ">=1.0.0 <2.0.0",
                    "compatible": True,
                    "package_size": 2048,
                    "package_sha256": "a" * 64,
                    "release_tag": f"{module_id}-v1.0.0",
                    "asset_name": f"{module_id}-1.0.0.zip",
                    "dependencies": (
                        ["conversation"] if module_id == "affection_memory" else []
                    ),
                    "optional_dependencies": [],
                    "conflicts": [],
                    "permissions": ["local_state"],
                    "data_policy": "preserve_on_uninstall",
                    "requires_restart": True,
                    "installed_version": (
                        "1.0.0" if module_id in installed_fixture else None
                    ),
                    "available_actions": (
                        [] if module_id in installed_fixture
                        else ["install_official"]
                    ),
                }
            )
        return {
            "source": {"owner": "songshu-yu", "repository": "Project-Kei-Modules"},
            "generated_at": "2026-07-30T00:00:00Z",
            "cache_source": "fixture",
            "refresh_status": "not_requested",
            "network_accessed": False,
            "modules": modules,
        }

    @app.get("/api/v1/modules/official-catalog")
    async def catalog():
        return official_catalog()

    @app.post("/api/v1/modules/official-catalog/refresh")
    async def refresh_catalog():
        result = official_catalog()
        result["network_accessed"] = True
        result["refresh_status"] = "success"
        return result

    @app.post("/api/v1/modules/{module_id}/install-official")
    async def install_official(module_id: str, request: Request):
        body = await request.json()
        if body != {"version": "1.0.0", "confirmation": f"{module_id}@1.0.0"}:
            raise HTTPException(status_code=400, detail="invalid official confirmation")
        if module_id not in OFFICIAL_MODULE_IDS:
            raise HTTPException(status_code=404, detail="unknown fixture module")
        installed_fixture.add(module_id)
        return {
            "module_id": module_id,
            "installed_version": "1.0.0",
            "restart_required": True,
        }

    @app.post("/api/v1/modules/install-upload")
    async def install_upload(request: Request, expected_module_id: Optional[str] = None):
        body = await request.body()
        if not body:
            raise HTTPException(status_code=400, detail="empty package")
        return {
            "module_id": expected_module_id or "manifest_fixture",
            "restart_required": False,
            "local_upload": {
                "received_bytes": len(body),
                "sha256": request.headers.get("x-project-kei-package-sha256", ""),
            },
        }

    @app.get("/api/v1/modules/{module_id}/assets/dashboard/index.js")
    async def preview_entrypoint(module_id: str):
        if module_id not in preview_modules:
            raise HTTPException(status_code=404, detail="fixture entrypoint not found")
        safe_module_id = json.dumps(module_id)
        source = f"""
export function mount(context) {{
  const note = document.createElement('p');
  note.dataset.fixtureMounted = {safe_module_id};
  note.textContent = {safe_module_id} + ' 模块动态面板已隔离装载。';
  context.root.append(note);
}}
export function unmount() {{}}
"""
        return Response(source, media_type="text/javascript")

    @app.get("/__pk100_audit")
    async def audit_log():
        return {"calls": calls}

    return app


def run_preview(port: int) -> int:
    import uvicorn

    uvicorn.run(create_preview_app(), host="127.0.0.1", port=port, log_level="warning")
    return 0


def check_production_core_control_contract() -> None:
    """Exercise the production Core routes without touching real local state."""

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        import api as production_api
        from features.voice.providers.gpt_sovits.acquisition import LocalEngineRegistry
    finally:
        asyncio.set_event_loop(None)

    engine_selection = production_api.MODULE_HOST.gpt_sovits_engine_selection
    original_registry = engine_selection.registry
    original_picker = engine_selection.picker

    async def exercise() -> None:
        transport = httpx.ASGITransport(
            app=production_api.app,
            client=("127.0.0.1", 43100),
        )
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://127.0.0.1:8000",
        ) as client:
            restart_status = await client.get(
                "/api/v1/dashboard/service/restart/status"
            )
            assert restart_status.status_code == 200
            assert restart_status.json()["available"] is False

            restart_without_origin = await client.post(
                "/api/v1/dashboard/service/restart",
                json={"confirmation": "restart-project-kei-core"},
            )
            assert restart_without_origin.status_code == 403

            restart_confirmed = await client.post(
                "/api/v1/dashboard/service/restart",
                headers={"Origin": "http://127.0.0.1:8000"},
                json={"confirmation": "restart-project-kei-core"},
            )
            assert restart_confirmed.status_code == 503
            assert restart_confirmed.json()["state"] == "unavailable"

            engine_status = await client.get(
                "/api/v1/gpt-sovits-engine/status"
            )
            assert engine_status.status_code == 200
            assert engine_status.json()["registration_state"] == "unregistered"

            engine_cancelled = await client.post(
                "/api/v1/gpt-sovits-engine/select-existing",
                headers={"Origin": "http://127.0.0.1:8000"},
            )
            assert engine_cancelled.status_code == 200
            assert engine_cancelled.json()["action"] == "cancelled"

    try:
        with tempfile.TemporaryDirectory(prefix="kei-pk100-production-") as temp:
            registry_path = Path(temp) / "engine.json"
            engine_selection.registry = LocalEngineRegistry(registry_path)
            engine_selection.picker = lambda: None
            loop.run_until_complete(exercise())
            assert not registry_path.exists()
    finally:
        engine_selection.registry = original_registry
        engine_selection.picker = original_picker
        loop.close()


def main() -> int:
    check_html_contract()
    check_public_readme_contract()
    check_manifest_inventory()
    check_javascript_contract()
    check_static_asset_boundary()
    check_ui_asset_api()
    check_production_core_control_contract()
    print("dashboard shell tests passed")
    return 0


if __name__ == "__main__":
    if len(sys.argv) >= 2 and sys.argv[1] == "--preview":
        preview_port = int(sys.argv[2]) if len(sys.argv) >= 3 else 8765
        raise SystemExit(run_preview(preview_port))
    raise SystemExit(main())
