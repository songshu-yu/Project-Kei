"""Node contract checks for the installable X monitor dashboard."""

from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path

import _path_setup  # noqa: F401


SERVER_ROOT = Path(__file__).resolve().parents[1]
ENTRYPOINT = (
    SERVER_ROOT
    / "features"
    / "x_monitor"
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


def check_source_boundary() -> None:
    source = ENTRYPOINT.read_text(encoding="utf-8")
    assert "export async function mount(context)" in source
    assert "export async function unmount()" in source
    assert "localStorage" not in source and "sessionStorage" not in source
    assert "document.querySelector" not in source
    assert "/api/v1/x/profiles" in source
    assert "/api/v1/x/posts" in source
    assert "/api/v1/x/posts/query" in source
    assert "/api/v1/x/replies" not in source
    assert "获取该日言论" in source and "获取该日至今" in source
    assert "node(root, 'button', '发帖'" in source
    assert "node(root, 'button', '回复'" in source
    assert "borderRadius: '999px'" in source
    assert "Nitter/RSS 或 FxEmbed 只展示上游本次实际返回内容" in source
    assert "查看直接父帖" in source
    assert "x-monitor-link-button" in source
    run_node(["--check", str(ENTRYPOINT)])


def check_mount_and_user_isolation() -> None:
    with tempfile.TemporaryDirectory(prefix="kei-x-monitor-dashboard-") as temp_dir:
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
    this.open = false;
    this.href = '';
    this.style = {{}};
    this.attributes = {{}};
  }}
  append(...items) {{ this.children.push(...items); }}
  replaceChildren(...items) {{ this.children = [...items]; }}
  addEventListener(name, handler) {{ this.listeners[name] = handler; }}
  setAttribute(name, value) {{ this.attributes[name] = String(value); }}
  querySelector(selector) {{
    const role = selector.match(/^\\[data-x-role="([^"]+)"\\]$/)?.[1];
    const visit = (item) => {{
      if (!item || typeof item !== 'object') return null;
      if (role && item.dataset?.xRole === role) return item;
      for (const child of item.children || []) {{
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
const responseFor = (body) => ({{
  username: body.username,
  mode: body.mode,
  timezone: 'Asia/Shanghai',
  start_at: `${{body.date}}T00:00:00+08:00`,
  end_at: `${{body.date}}T12:00:00+08:00`,
  count: 1,
  items: [{{
    id: `${{body.username}}-${{body.mode}}`,
    kind: body.mode === 'day' ? 'post' : 'reply',
    content: `${{body.username}} ${{body.mode}} text`,
    url: `https://nitter.net/${{body.username}}/status/1`,
    published_at: `${{body.date}}T08:00:00+08:00`,
    parent_context: body.mode === 'since' ? {{
      username: '@Parent',
      content: 'direct parent text',
      published_at: `${{body.date}}T07:00:00+08:00`,
      url: 'https://x.com/Parent/status/2',
    }} : null,
  }}],
  fetched_at: `${{body.date}}T12:00:00+08:00`,
  coverage: {{status: 'partial'}},
  warnings: [],
}});
const mod = await import({module_path.as_uri()!r});
await mod.mount({{
  root,
  request: async (path, options = {{}}) => {{
    calls.push([path, options.method || 'GET', options.body || '']);
    if (path === '/api/v1/x/profiles') return {{profiles: {{
      alice: {{username:'Alice', name:'Alice', avatar_url:'', x_config_groups:['twitter_users']}},
      bob: {{username:'Bob', name:'Bob', avatar_url:'', x_config_groups:['money_twitter_users']}},
    }}}};
    if (path === '/api/v1/x/posts') return {{users: {{
      alice: {{username:'Alice', posts:[], x_config_groups:['twitter_users']}},
      bob: {{username:'Bob', posts:[], x_config_groups:['money_twitter_users']}},
    }}}};
    if (path === '/api/v1/x/posts/query') return responseFor(JSON.parse(options.body));
    if (path.startsWith('/api/v1/x/profiles/resolve')) return {{profiles: {{}}}};
    throw new Error(`unexpected request: ${{path}}`);
  }},
  notify: (message, type) => notices.push([message, type]),
}});
if (calls.length !== 2) throw new Error('mount must perform exactly two offline GET reads');
if (!calls.every((item) => item[1] === 'GET')) throw new Error('mount triggered a mutation');
const list = root.children[1];
const users = list.children;
if (users.length !== 2) throw new Error('two users were not rendered independently');
const alice = users.find((item) => item.dataset.xUsername === 'Alice');
const bob = users.find((item) => item.dataset.xUsername === 'Bob');
if (!alice || !bob) throw new Error('user identity was lost');
const aliceControls = alice.children[1];
const bobControls = bob.children[1];
const aliceContentTabs = alice.children[3];
const bobContentTabs = bob.children[3];
if (aliceContentTabs.tagName !== 'nav' || bobContentTabs.tagName !== 'nav') {{
  throw new Error('each user must own a persistent post/reply sub-navigation');
}}
if (aliceContentTabs.children.map((item) => item.textContent).join('/') !== '发帖/回复') {{
  throw new Error('Alice post/reply sub-navigation labels are incorrect');
}}
const aliceDate = aliceControls.children[0].children[0];
aliceDate.value = '2026-07-21';
await aliceDate.listeners.change();
if (calls.length !== 2) throw new Error('date selection accessed the API');
alice.open = true;
if (calls.length !== 2) throw new Error('folding accessed the API');
await aliceControls.children[2].listeners.click();
if (calls.length !== 3) throw new Error('day button did not issue exactly one request');
let body = JSON.parse(calls[2][2]);
if (body.username !== 'Alice' || body.mode !== 'day' || body.date !== '2026-07-21') {{
  throw new Error('Alice day request was not isolated');
}}
await bobControls.children[3].listeners.click();
if (calls.length !== 4) throw new Error('since button did not issue exactly one request');
body = JSON.parse(calls[3][2]);
if (body.username !== 'Bob' || body.mode !== 'since') {{
  throw new Error('Bob since request was not isolated');
}}
if (aliceControls.children[2].disabled || bobControls.children[3].disabled) {{
  throw new Error('button loading state was not restored');
}}
const text = (item) => [item.textContent, ...(item.children || []).map(text)].join(' ');
if (!text(alice).includes('Alice day text') || text(alice).includes('Bob since text')) {{
  throw new Error('Alice result was overwritten by Bob');
}}
if (text(bob).includes('Bob since text') || bobContentTabs.children[1].attributes['aria-label'] !== '回复，1 条') {{
  throw new Error('reply content was not separated from the default post view');
}}
const callsBeforeReplySwitch = calls.length;
await bobContentTabs.children[1].listeners.click();
if (calls.length !== callsBeforeReplySwitch) throw new Error('post/reply switch accessed the API');
if (!text(bob).includes('Bob since text') || text(bob).includes('Alice day text')) {{
  throw new Error('Bob result was overwritten by Alice');
}}
if (!text(bob).includes('direct parent text') || !text(bob).includes('查看直接父帖')) {{
  throw new Error('one-level parent context was not rendered');
}}
if (!text(alice).includes('Alice day text')) {{
  throw new Error('Bob reply switch changed Alice post view');
}}
await aliceControls.children[1].listeners.click();
if (calls.length !== 5 || !calls[4][0].includes('/profiles/resolve')) {{
  throw new Error('profile refresh did not remain an explicit action');
}}
await mod.unmount();
if (root.children.length !== 0) throw new Error('unmount did not clear its own root');
"""
        run_node(["--input-type=module", "-e", probe])


def main() -> int:
    check_source_boundary()
    check_mount_and_user_isolation()
    print("x_monitor dashboard tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
