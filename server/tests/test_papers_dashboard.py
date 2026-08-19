"""PK-133 read-only paper projection and safe dashboard rendering checks."""

from __future__ import annotations

import asyncio
import json
import os
import re
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path

TEST_ROOT = Path(tempfile.gettempdir()) / "project-kei-pk133-dashboard-tests"
os.environ["PROJECT_KEI_ENV_FILE"] = str(TEST_ROOT / "missing.env")
os.environ["PROJECT_KEI_LLM_PROFILE_PATH"] = str(TEST_ROOT / "missing-profile.json")

import _path_setup  # noqa: E402,F401
import httpx  # noqa: E402
from fastapi import FastAPI  # noqa: E402

from features.daily_briefing.legacy_adapter import DailyBriefingService  # noqa: E402
from features.daily_briefing.models import (  # noqa: E402
    BriefingDocument,
    CacheStatus,
    CoverageStatus,
    IntelItem,
    SourceCoverage,
)
from features.daily_briefing.router import create_briefing_router  # noqa: E402


SERVER_ROOT = Path(__file__).resolve().parents[1]
DASHBOARD_HTML = SERVER_ROOT / "static" / "dashboard.html"
FIXED_NOW = datetime(2026, 7, 28, 1, 0, tzinfo=timezone.utc)


class ForbiddenGateway:
    def __init__(self) -> None:
        self.calls = []

    async def collect(self, request):
        self.calls.append(request)
        raise AssertionError("a read-only paper view must not call collectors")


class ForbiddenTextGenerator:
    def __init__(self) -> None:
        self.calls = []

    async def generate_text(self, *args, **kwargs):
        self.calls.append((args, kwargs))
        raise AssertionError("a read-only paper view must not call an LLM")


class ForbiddenVoice:
    def __init__(self) -> None:
        self.calls = []

    async def synthesize_briefing(self, *args, **kwargs):
        self.calls.append((args, kwargs))
        raise AssertionError("a read-only paper view must not call voice")


def paper(
    stable_id: str,
    source_id: str,
    title: str,
    *,
    summary: str = "",
    url: str = "",
    author: str = "",
) -> IntelItem:
    return IntelItem(
        stable_id=stable_id,
        source_id=source_id,
        category="papers",
        title=title,
        summary=summary,
        url=url,
        author=author,
        published_at="2026-07-28T00:30:00Z",
        fetched_at="2026-07-28T01:00:00Z",
    )


def document(local_date: str, items: list[IntelItem]) -> BriefingDocument:
    stamp = "2026-07-28T01:00:00Z"
    return BriefingDocument(
        local_date=local_date,
        timezone="Asia/Shanghai",
        items=items,
        coverage={
            "arxiv": SourceCoverage(CoverageStatus.COMPLETE, 1),
            "crossref": SourceCoverage(CoverageStatus.PARTIAL, 1, "fixed warning"),
            "semantic": SourceCoverage(CoverageStatus.EMPTY, 0),
        },
        warnings=["crossref: fixed warning"],
        text="固定测试情报",
        script="固定 Kei 播报总结",
        fetched=True,
        rewritten=True,
        rewrite_status="generated",
        created_at=stamp,
        updated_at=stamp,
        cache_status=CacheStatus.FETCHED,
    )


def cache_snapshot(root: Path) -> dict[str, bytes]:
    cache_dir = root / "data" / "briefing_cache"
    return {
        path.relative_to(cache_dir).as_posix(): path.read_bytes()
        for path in sorted(cache_dir.glob("*"))
        if path.is_file()
    }


async def check_read_only_today_api(root: Path) -> None:
    gateway = ForbiddenGateway()
    generator = ForbiddenTextGenerator()
    voice = ForbiddenVoice()
    facade = DailyBriefingService(
        text_generator=generator,
        root_dir=root,
        voice=voice,
        gateway=gateway,
        source_config_provider=lambda: {},
        clock=lambda: FIXED_NOW,
    )
    app = FastAPI()
    app.include_router(
        create_briefing_router(
            lambda: facade,
            local_request_guard=lambda _request: True,
        )
    )

    facade.repository.save(document("2026-07-27", [
        paper("arxiv:old", "arxiv", "昨天的论文"),
    ]))
    facade.repository.save(document("2026-07-29", [
        paper("semantic:future", "semantic", "未来缓存中的论文"),
    ]))
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        old_only = await client.get("/api/v1/briefing/today")
        assert old_only.status_code == 200
        assert old_only.json()["ready"] is False

        todays_items = [
            paper(
                "arxiv:duplicate",
                "arxiv",
                "A Shared Paper",
                summary="已有摘要",
                url="https://arxiv.org/abs/2607.00001",
                author="测试作者",
            ),
            paper(
                "crossref:duplicate",
                "crossref",
                "A Shared Paper",
                summary="更完整的已有摘要",
                url="https://doi.org/10.0000/example",
                author="测试作者",
            ),
            paper("semantic:missing", "semantic", "No Abstract"),
            IntelItem(
                stable_id="github:not-paper",
                source_id="github",
                category="development",
                title="非论文条目",
                fetched_at="2026-07-28T01:00:00Z",
            ),
        ]
        facade.repository.save_transaction(
            document("2026-07-28", todays_items),
            include_summary=True,
        )
        before = cache_snapshot(root)

        today = await client.get("/api/v1/briefing/today")
        status = await client.get("/dashboard/briefing/status")

    assert today.status_code == 200
    payload = today.json()
    assert payload["ready"] is True
    assert payload["date"] == "2026-07-28"
    assert payload["items"][0]["title"] == "A Shared Paper"
    assert payload["items"][0]["summary"] == "已有摘要"
    assert payload["coverage"]["crossref"]["status"] == "partial"
    assert payload["warnings"] == ["crossref: fixed warning"]
    assert payload["script"] == "固定 Kei 播报总结"
    assert status.status_code == 200
    assert status.json()["summary"]["text"] == "固定 Kei 播报总结"
    assert cache_snapshot(root) == before
    assert not gateway.calls
    assert not generator.calls
    assert not voice.calls


def check_dashboard_renderer() -> None:
    html = DASHBOARD_HTML.read_text(encoding="utf-8")
    if 'id="briefing-papers"' not in html:
        dynamic_panel = (
            SERVER_ROOT
            / "features"
            / "papers"
            / "package_source"
            / "dashboard"
            / "index.js"
        )
        source = dynamic_panel.read_text(encoding="utf-8")
        assert "innerHTML" not in source
        assert "textContent" in source
        assert "new URL" in source
        assert '["http:", "https:"]' in source
        assert "noopener noreferrer" in source
        assert "摘要暂缺" in source
        assert 'context.request("/api/v1/papers/today")' in source
        assert 'context.request("/api/v1/papers/refresh"' in source
        assert "fetch(" not in source
        with tempfile.TemporaryDirectory(prefix="kei-papers-panel-js-") as temp_dir:
            module_path = Path(temp_dir) / "index.mjs"
            module_path.write_text(source, encoding="utf-8")
            completed = subprocess.run(
                ["node", "--check", str(module_path)],
                text=True,
                encoding="utf-8",
                capture_output=True,
                check=False,
            )
        if completed.returncode:
            raise AssertionError(completed.stderr or completed.stdout)
        return
    assert 'id="briefing-papers"' in html
    assert 'id="briefing-papers-meta"' in html
    match = re.search(
        r"(function normalizePaperKey.*?)(?=\nfunction isDeepSeek)",
        html,
        re.DOTALL,
    )
    assert match
    source = match.group(1)
    assert "innerHTML" not in source
    assert "textContent" in source
    assert "replaceChildren" in source
    assert "new URL" in source
    assert "['http:','https:']" in source
    assert "noopener noreferrer" in source
    assert "摘要暂缺" in source
    assert "apiJson('/api/v1/briefing/today')" in source
    assert "addEventListener" not in source
    for forbidden in ("briefing/generate", "briefing/refresh", "/voice", "arxiv.org", "crossref.org"):
        assert forbidden not in source

    harness = r"""
class FakeNode {
  constructor(tagName) {
    this.tagName = tagName;
    this.children = [];
    this.className = '';
    this._textContent = '';
  }
  set textContent(value) {
    this._textContent = String(value);
    this.children = [];
  }
  get textContent() { return this._textContent; }
  append(...children) { this.children.push(...children); }
  replaceChildren(...children) {
    this._textContent = '';
    this.children = [...children];
  }
}
const root = new FakeNode('div');
const meta = new FakeNode('span');
const document = {
  querySelector(selector) {
    if (selector === '#briefing-papers') return root;
    if (selector === '#briefing-papers-meta') return meta;
    throw new Error('unexpected selector: ' + selector);
  },
  createElement(tagName) { return new FakeNode(tagName); },
};
const exported = new Function(
  'document',
  'URL',
  SOURCE + '\nreturn {paperItems, renderTodayPapers};'
)(document, URL);
const payload = {
  ready: true,
  items: [
    {stable_id:'arxiv:one', source_id:'arxiv', category:'papers',
     title:'Duplicate Paper', summary:'', author:'A',
     url:'https://arxiv.org/abs/1'},
    {stable_id:'crossref:one', source_id:'crossref', category:'papers',
     title:'  duplicate   paper ', summary:'Complete abstract', author:'A',
     url:'https://doi.org/10.1/example'},
    {stable_id:'semantic:evil', source_id:'semantic', category:'papers',
     title:'<img src=x onerror=alert(1)>', summary:'<script>alert(2)</script>',
     author:'<svg onload=alert(3)>', url:'javascript:alert(4)'},
    {stable_id:'semantic:missing', source_id:'semantic', category:'papers',
     title:'No Abstract', summary:'   ', author:'', url:''},
    {stable_id:'github:other', source_id:'github', category:'development',
     title:'Not a paper', summary:'ignore me'},
  ],
};
exported.renderTodayPapers(payload);
if (root.children.length !== 3) throw new Error('cross-source duplicate was not removed');
if (meta.textContent !== '3 篇 · 仅来自当天缓存') throw new Error('paper count is wrong');
const duplicate = root.children[0];
if (duplicate.children[1].textContent !== 'Complete abstract') throw new Error('richer cached summary was not kept');
const malicious = root.children[1];
if (malicious.children[0].textContent !== '<img src=x onerror=alert(1)>') throw new Error('title was not rendered as text');
if (malicious.children[1].textContent !== '<script>alert(2)</script>') throw new Error('summary was not rendered as text');
if (malicious.children[2].children[0].textContent !== '<svg onload=alert(3)> · semantic') throw new Error('author was not rendered as text');
if (malicious.children[2].children.some(node => node.tagName === 'a')) throw new Error('dangerous URL became a link');
const missing = root.children[2];
if (missing.children[1].textContent !== '摘要暂缺') throw new Error('missing-summary fallback is wrong');
const safeLink = duplicate.children[2].children.find(node => node.tagName === 'a');
if (!safeLink || !safeLink.href.startsWith('https://') || safeLink.rel !== 'noopener noreferrer') throw new Error('safe source link contract is wrong');
exported.renderTodayPapers({ready:false, items:payload.items});
if (root.children.length !== 1 || root.children[0].textContent !== '今日暂无论文') throw new Error('empty state is wrong');
"""
    completed = subprocess.run(
        ["node", "-"],
        cwd=SERVER_ROOT,
        input=f"const SOURCE={json.dumps(source)};\n{harness}",
        text=True,
        encoding="utf-8",
        capture_output=True,
        check=False,
    )
    if completed.returncode:
        raise AssertionError(completed.stderr or completed.stdout)


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="kei-pk133-dashboard-") as temp_dir:
        asyncio.run(check_read_only_today_api(Path(temp_dir)))
    check_dashboard_renderer()
    print("PK-133 dashboard paper tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
