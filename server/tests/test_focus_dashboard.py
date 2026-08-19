"""Node-based contract checks for the installable focus dashboard entrypoint."""

from __future__ import annotations

import sys
import subprocess
import tempfile
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse

import _path_setup  # noqa: F401

from core.modules import InProcessModuleLoader, ModuleManager
from features.catalog.service import get_module_catalog
from features.dashboard.router import dashboard_static_asset
from features.focus.package_builder import build_focus_package, file_sha256


SERVER_ROOT = Path(__file__).resolve().parents[1]
ENTRYPOINT = SERVER_ROOT / "features" / "focus" / "package_source" / "dashboard" / "index.js"
DASHBOARD_HTML = SERVER_ROOT / "static" / "dashboard.html"


def run_node(args: list[str]) -> None:
    completed = subprocess.run(
        ["node", *args],
        cwd=SERVER_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    if completed.returncode:
        raise AssertionError(completed.stderr or completed.stdout)


def check_source_boundary() -> None:
    source = ENTRYPOINT.read_text(encoding="utf-8")
    assert "export async function mount(context)" in source
    assert "export async function unmount()" in source
    assert "localStorage" not in source and "sessionStorage" not in source
    assert "document.querySelector" not in source
    assert "/api/v1/focus/status" in source
    assert "/api/v1/focus/start" in source
    assert "/api/v1/focus/stop" in source
    assert "/api/v1/focus/reset" in source
    assert "/demon/" not in source and "/fitness/" not in source and "/calendar/" not in source
    run_node(["--check", str(ENTRYPOINT)])


def check_mount_unmount() -> None:
    with tempfile.TemporaryDirectory(prefix="kei-focus-dashboard-") as temp_dir:
        module_path = Path(temp_dir) / "index.mjs"
        module_path.write_text(ENTRYPOINT.read_text(encoding="utf-8"), encoding="utf-8")
        probe = f"""
class FakeElement {{
  constructor(tag, ownerDocument) {{
    this.tagName = tag;
    this.ownerDocument = ownerDocument;
    this.children = [];
    this.dataset = {{}};
    this.listeners = {{}};
    this.value = '';
    this.disabled = false;
    this.textContent = '';
    this.className = '';
  }}
  append(...items) {{
    for (const item of items) {{
      this.children.push(item);
      if (this.tagName === 'select' && item?.value && !this.value) this.value = item.value;
    }}
  }}
  replaceChildren(...items) {{ this.children = [...items]; }}
  addEventListener(name, handler) {{ this.listeners[name] = handler; }}
  querySelector(selector) {{
    const match = selector.match(/^\\[data-focus-role="([^"]+)"\\]$/);
    if (!match) return null;
    const role = match[1];
    const visit = (node) => {{
      if (!node || typeof node !== 'object') return null;
      if (node.dataset?.focusRole === role) return node;
      for (const child of node.children || []) {{
        const found = visit(child);
        if (found) return found;
      }}
      return null;
    }};
    return visit(this);
  }}
}}
const ownerDocument = {{createElement: (tag) => new FakeElement(tag, ownerDocument)}};
const root = new FakeElement('root', ownerDocument);
const calls = [];
const notices = [];
let cleared = false;
globalThis.setInterval = () => 41;
globalThis.clearInterval = (value) => {{ if (value === 41) cleared = true; }};
const mod = await import({module_path.as_uri()!r});
await mod.mount({{
  root,
  request: async (path, options = {{}}) => {{
    calls.push([path, options.method || 'GET']);
    if (path.endsWith('/start')) return {{active:true, completed:false, label:'番茄钟', task:'fixture', remaining_seconds:300, message:'started'}};
    if (path.endsWith('/stop')) return {{active:false, completed:false, label:'番茄钟', task:'fixture', remaining_seconds:0, message:'stopped'}};
    if (path.endsWith('/reset')) return {{status:'ok', cleared_sessions:1}};
    return {{active:false, completed:false, label:'', task:'', remaining_seconds:0, message:'idle'}};
  }},
  notify: (text, type) => notices.push([text, type]),
}});
if (root.children.length !== 4) throw new Error('focus panel did not mount inside its root');
if (calls.length !== 1 || calls[0][0] !== '/api/v1/focus/status') throw new Error('mount used an undeclared endpoint');
await root.querySelector('[data-focus-role="start"]').listeners.click();
if (calls[1][0] !== '/api/v1/focus/start' || calls[1][1] !== 'POST') throw new Error('start request contract changed');
await root.querySelector('[data-focus-role="stop"]').listeners.click();
if (calls[2][0] !== '/api/v1/focus/stop' || calls[2][1] !== 'POST') throw new Error('stop request contract changed');
const reset = root.querySelector('[data-focus-role="reset"]');
await reset.listeners.click();
if (calls.length !== 3) throw new Error('reset skipped explicit confirmation');
await reset.listeners.click();
if (calls[3][0] !== '/api/v1/focus/reset' || calls[3][1] !== 'POST') throw new Error('reset request contract changed');
if (reset.disabled || reset.textContent !== '重置专注记录') throw new Error('reset button did not re-arm after success');
if (!calls.every(([path]) => path.startsWith('/api/v1/focus/'))) throw new Error('focus panel escaped its API namespace');
await mod.unmount();
if (root.children.length !== 0 || !cleared) throw new Error('focus panel did not unmount cleanly');
"""
        run_node(["--input-type=module", "-e", probe])


def create_preview_app(root: Path) -> FastAPI:
    """Build and mount the real focus package using only temporary state."""
    manager = ModuleManager(
        runtime_root=root / "runtime" / "modules",
        registry_path=root / "data" / "module_registry.json",
        data_root=root / "data" / "modules",
    )
    package = build_focus_package(root / "focus.zip")
    manager.install(package, file_sha256(package), expected_module_id="focus")
    manager.enable("focus")

    app = FastAPI(title="Project Kei isolated focus preview")
    app.state.focus_state_path = root / "state" / "focus_timer.json"
    results = InProcessModuleLoader().load(app, manager.enabled_in_process_descriptors())
    manager.record_load_results(results)
    if results != [{"module_id": "focus", "status": "loaded"}]:
        raise AssertionError(f"focus preview load failed: {results}")

    @app.get("/dashboard")
    async def preview_dashboard():
        return FileResponse(DASHBOARD_HTML, media_type="text/html; charset=utf-8")

    @app.get("/dashboard/static/{asset_path:path}")
    async def preview_dashboard_static(asset_path: str):
        return await dashboard_static_asset(asset_path)

    @app.get("/api/v1/modules")
    async def preview_catalog():
        return get_module_catalog(lifecycle_snapshot=manager.snapshot())

    @app.get("/api/v1/modules/{module_id}/assets/{asset_path:path}")
    async def preview_module_asset(module_id: str, asset_path: str):
        try:
            return FileResponse(manager.asset_path(module_id, asset_path))
        except Exception as exc:
            raise HTTPException(status_code=404, detail="Module asset not found") from exc

    return app


def run_preview(port: int) -> int:
    import uvicorn

    with tempfile.TemporaryDirectory(prefix="kei-focus-browser-preview-") as temp_dir:
        uvicorn.run(
            create_preview_app(Path(temp_dir)),
            host="127.0.0.1",
            port=port,
            log_level="warning",
        )
    return 0


def main() -> int:
    check_source_boundary()
    check_mount_unmount()
    print("focus dashboard tests passed")
    return 0


if __name__ == "__main__":
    if len(sys.argv) >= 2 and sys.argv[1] == "--preview":
        preview_port = int(sys.argv[2]) if len(sys.argv) >= 3 else 8766
        raise SystemExit(run_preview(preview_port))
    raise SystemExit(main())
