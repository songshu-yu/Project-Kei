"""Node contract checks for the PK-115 dynamic dashboard entrypoint."""

from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path

import _path_setup  # noqa: F401


SERVER_ROOT = Path(__file__).resolve().parents[1]
ENTRYPOINT = (
    SERVER_ROOT
    / "features"
    / "intel_sources"
    / "package_source"
    / "dashboard"
    / "index.js"
)


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


def check_dashboard_source_boundary() -> None:
    source = ENTRYPOINT.read_text(encoding="utf-8")
    assert "export async function mount(context)" in source
    assert "export async function unmount()" in source
    assert "localStorage" not in source and "sessionStorage" not in source
    assert "document.querySelector" not in source
    for target in ("intel_sources", "x_monitor", "bilibili", "github_intel", "papers"):
        assert f"target: '{target}'" in source
    assert "data.moduleConfigTarget" not in source
    assert "dataset.moduleConfigTarget" in source
    assert "dataset.configOwner = 'intel_sources'" in source
    assert source.count("'/api/v1/intel-sources'") == 2
    assert "/profiles" not in source
    assert "/briefing" not in source
    assert "/collect" not in source
    assert "/refresh" not in source
    run_node(["--check", str(ENTRYPOINT)])


def check_dashboard_mount_read_save_reload_and_unmount() -> None:
    with tempfile.TemporaryDirectory(prefix="kei-intel-sources-dashboard-") as temp_dir:
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
    this.attributes = {{}};
    this.rows = 0;
  }}
  append(...items) {{ this.children.push(...items); }}
  replaceChildren(...items) {{ this.children = [...items]; }}
  addEventListener(name, handler) {{ this.listeners[name] = handler; }}
  setAttribute(name, value) {{ this.attributes[name] = String(value); }}
}}
const ownerDocument = {{createElement: tag => new FakeElement(tag, ownerDocument)}};
const root = new FakeElement('root', ownerDocument);
const calls = [];
const notices = [];
const config = {{
  twitter_users: ['OpenAI'],
  money_twitter_users: [],
  github_users: [],
  github_repos: [],
  bilibili_uids: [],
  youtube_channel_ids: [],
  paper_priority_authors: [],
  paper_secondary_authors: [],
  paper_ai_authors: [],
  using_local_override: false,
  updated_at: null,
}};
const visit = (node, predicate) => {{
  if (predicate(node)) return node;
  for (const child of node.children || []) {{
    const found = visit(child, predicate);
    if (found) return found;
  }}
  return null;
}};
const mod = await import({module_path.as_uri()!r});
await mod.mount({{
  root,
  request: async (path, options = {{}}) => {{
    calls.push([path, options.method || 'GET', options.body || null]);
    if ((options.method || 'GET') === 'PUT') {{
      const payload = JSON.parse(options.body);
      Object.assign(config, payload, {{using_local_override:true, updated_at:'2026-07-30T12:00:00+08:00'}});
    }}
    return {{...config}};
  }},
  notify: (message, kind) => notices.push([message, kind]),
}});
if (calls.length !== 1 || calls[0][0] !== '/api/v1/intel-sources' || calls[0][1] !== 'GET') {{
  throw new Error('mount did not perform exactly one configuration read');
}}
const twitter = visit(root, node => node.dataset?.intelSourcesField === 'twitter_users');
const repository = visit(root, node => node.dataset?.intelSourcesField === 'github_repos');
const save = visit(root, node => node.dataset?.intelSourcesRole === 'save');
const reload = visit(root, node => node.dataset?.intelSourcesRole === 'reload');
if (!twitter || !repository || !save || !reload) throw new Error('source controls are incomplete');
twitter.value = 'OpenAI\\n@KeiBot';
repository.value = 'openai/openai-python';
await save.listeners.click();
if (calls.length !== 2 || calls[1][1] !== 'PUT') throw new Error('save did not use PUT');
const payload = JSON.parse(calls[1][2]);
if (payload.twitter_users.join(',') !== 'OpenAI,@KeiBot') throw new Error('X values changed unexpectedly');
if (payload.github_repos[0] !== 'openai/openai-python') throw new Error('repository was not submitted');
if (Object.keys(payload).length !== 9) throw new Error('save payload field contract changed');
if (!notices.some(([message]) => message.includes('未触发资料查询、采集或缓存刷新'))) {{
  throw new Error('zero-collection confirmation is missing');
}}
await reload.listeners.click();
if (calls.length !== 3 || calls[2][1] !== 'GET') throw new Error('reload did not read configuration');
if (!calls.every(([path]) => path === '/api/v1/intel-sources')) {{
  throw new Error('dashboard escaped the configuration API');
}}
await mod.unmount();
if (root.children.length !== 0) throw new Error('dashboard did not unmount cleanly');
"""
        run_node(["--input-type=module", "-e", probe])


def main() -> int:
    check_dashboard_source_boundary()
    check_dashboard_mount_read_save_reload_and_unmount()
    print("PK-115 intel_sources dashboard tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
