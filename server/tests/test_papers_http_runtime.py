"""PK-133 permanent regression: one paper HTTP owner across old/new entry points."""
from __future__ import annotations

import asyncio
import os
import tempfile
from datetime import date, datetime, timezone
from pathlib import Path

TEST_LOCAL_ROOT = Path(tempfile.gettempdir()) / "project-kei-pk133-http-tests"
os.environ["PROJECT_KEI_ENV_FILE"] = str(TEST_LOCAL_ROOT / "missing.env")
os.environ["SEMANTIC_SCHOLAR_API_KEY"] = ""

import _path_setup  # noqa: F401,E402
import httpx  # noqa: E402

from features.daily_briefing.models import CollectRequest, CoverageStatus  # noqa: E402
from features.papers import (  # noqa: E402
    ArxivCollector,
    ArxivQuery,
    CrossrefCollector,
    PaperHttpRuntime,
    SemanticScholarCollector,
    UpstreamPolicy,
)
from intel.collectors.arxiv import fetch_arxiv_papers  # noqa: E402
from intel.collectors.arxiv import ArxivCollector as LegacyArxivCollector  # noqa: E402
from intel.collectors.papers import CrossrefCollector as LegacyCrossrefCollector  # noqa: E402
from intel.collectors.papers import SemanticScholarCollector as LegacySemanticCollector  # noqa: E402
from intel.collectors.papers import (  # noqa: E402
    fetch_recent_crossref_for_authors,
    search_by_author_semantic_scholar,
)


NOW = datetime(2026, 7, 29, 8, 0, tzinfo=timezone.utc)
ROOT = Path(__file__).resolve().parents[1]


def arxiv_xml() -> str:
    return """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom" xmlns:arxiv="http://arxiv.org/schemas/atom">
  <entry>
    <id>https://arxiv.org/abs/2607.29001</id>
    <published>2026-07-29T02:00:00Z</published>
    <title>Shared Runtime Paper</title>
    <summary>Summary from a deterministic fake transport.</summary>
    <author><name>Alice Example</name></author>
    <link href="https://arxiv.org/abs/2607.29001" rel="alternate" />
    <arxiv:primary_category term="cs.AI" />
  </entry>
</feed>"""


def collect_request(*, source_id: str = "arxiv", authors=()) -> CollectRequest:
    return CollectRequest(
        local_date=date(2026, 7, 29),
        timezone="UTC",
        source_ids=(source_id,),
        refresh=True,
        lookback=24,
        source_config_snapshot={
            "paper_priority_authors": list(authors),
            "paper_secondary_authors": [],
            "paper_ai_authors": [],
        },
    )


class FakeClock:
    def __init__(self) -> None:
        self.value = 0.0
        self.sleeps: list[float] = []

    def monotonic(self) -> float:
        return self.value

    async def sleep(self, delay: float) -> None:
        self.sleeps.append(delay)
        self.value += delay
        await asyncio.sleep(0)


class TrackingTransport(httpx.AsyncBaseTransport):
    def __init__(self, responder, *, block_first: bool = False) -> None:
        self.responder = responder
        self.block_first = block_first
        self.first_entered = asyncio.Event()
        self.release_first = asyncio.Event()
        self.active = 0
        self.maximum_active = 0
        self.calls = 0
        self.closed = 0
        self.times: list[float] = []
        self.read_time = lambda: 0.0

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        self.calls += 1
        call_number = self.calls
        self.active += 1
        self.maximum_active = max(self.maximum_active, self.active)
        self.times.append(self.read_time())
        try:
            if self.block_first and call_number == 1:
                self.first_entered.set()
                await self.release_first.wait()
            response = self.responder(call_number)
            response.request = request
            return response
        finally:
            self.active -= 1

    async def aclose(self) -> None:
        self.closed += 1


def runtime_for(
    transport: httpx.AsyncBaseTransport,
    *,
    upstream: str = "arxiv",
    min_interval: float = 0.0,
    fake_clock: FakeClock | None = None,
) -> PaperHttpRuntime:
    fake_clock = fake_clock or FakeClock()
    return PaperHttpRuntime(
        policies={
            upstream: UpstreamPolicy(
                min_interval=min_interval,
                max_concurrency=1,
                timeout=5.0,
            )
        },
        transports={upstream: transport},
        monotonic=fake_clock.monotonic,
        sleep=fake_clock.sleep,
        clock=lambda: NOW,
    )


async def check_legacy_and_collector_share_concurrency(temp_root: Path) -> None:
    transport = TrackingTransport(
        lambda _call: httpx.Response(200, text=arxiv_xml()),
        block_first=True,
    )
    runtime = runtime_for(transport)
    collector = ArxivCollector(
        queries=(ArxivQuery("collector", keywords=("runtime",), max_results=1),),
        cache_dir=temp_root / "collector",
        max_retries=0,
        clock=lambda: NOW,
        runtime=runtime,
    )
    legacy = asyncio.create_task(
        fetch_arxiv_papers(
            categories=("cs.AI",),
            max_results=1,
            field_label="legacy",
            runtime=runtime,
            cache_dir=temp_root / "legacy",
            clock=lambda: NOW,
        )
    )
    current = asyncio.create_task(collector.collect(collect_request()))
    await asyncio.wait_for(transport.first_entered.wait(), timeout=1.0)
    await asyncio.sleep(0)
    assert transport.calls == 1
    transport.release_first.set()
    legacy_output, collector_output = await asyncio.gather(legacy, current)
    assert transport.maximum_active == 1
    assert legacy_output[0].title == collector_output.items[0].title
    assert collector_output.coverage.status is CoverageStatus.COMPLETE
    await collector.aclose()  # externally owned runtime: no close
    await runtime.aclose()
    await runtime.aclose()
    assert transport.closed == 1


async def check_minimum_interval_is_shared(temp_root: Path) -> None:
    fake_clock = FakeClock()
    transport = TrackingTransport(lambda _call: httpx.Response(200, text=arxiv_xml()))
    transport.read_time = fake_clock.monotonic
    runtime = runtime_for(transport, min_interval=5.0, fake_clock=fake_clock)
    collector = ArxivCollector(
        queries=(ArxivQuery("collector", keywords=("interval",), max_results=1),),
        cache_dir=temp_root / "interval-collector",
        max_retries=0,
        clock=lambda: NOW,
        runtime=runtime,
    )
    await asyncio.gather(
        fetch_arxiv_papers(
            keywords=("legacy-interval",),
            max_results=1,
            runtime=runtime,
            cache_dir=temp_root / "interval-legacy",
            clock=lambda: NOW,
        ),
        collector.collect(collect_request()),
    )
    assert transport.maximum_active == 1
    assert transport.times == [0.0, 5.0]
    assert fake_clock.sleeps == [5.0]
    await runtime.aclose()


async def check_crossref_legacy_and_collector_share_owner() -> None:
    response_payload = {
        "message": {
            "items": [{
                "DOI": "10.1234/shared-crossref",
                "title": ["Shared Crossref Runtime"],
                "author": [{"given": "Alice", "family": "Example"}],
                "abstract": "Fake Crossref abstract.",
                "published": {"date-parts": [[2026, 7, 29]]},
                "container-title": ["Optica"],
                "URL": "https://doi.org/10.1234/shared-crossref",
            }]
        }
    }
    transport = TrackingTransport(
        lambda _call: httpx.Response(200, json=response_payload),
        block_first=True,
    )
    runtime = runtime_for(transport, upstream="crossref")
    collector = CrossrefCollector(
        runtime=runtime,
        max_retries=0,
        clock=lambda: NOW,
    )
    legacy = asyncio.create_task(
        fetch_recent_crossref_for_authors(
            ["Alice Example"],
            journals=["Optica"],
            max_per_journal=1,
            runtime=runtime,
        )
    )
    current = asyncio.create_task(
        collector.collect(collect_request(source_id="crossref", authors=["Alice Example"]))
    )
    await asyncio.wait_for(transport.first_entered.wait(), timeout=1.0)
    await asyncio.sleep(0)
    assert transport.calls == 1
    transport.release_first.set()
    legacy_output, collector_output = await asyncio.gather(legacy, current)
    assert legacy_output and collector_output.items
    assert transport.maximum_active == 1
    await runtime.aclose()


async def check_semantic_legacy_and_collector_share_owner() -> None:
    response_payload = {
        "data": [{
            "paperId": "shared-semantic",
            "title": "Shared Semantic Runtime",
            "authors": [{"name": "Alice Example"}],
            "publicationDate": "2026-07-29",
            "abstract": "Fake Semantic Scholar abstract.",
            "externalIds": {},
            "url": "https://www.semanticscholar.org/paper/shared-semantic",
            "journal": {"name": "Optica"},
        }]
    }
    transport = TrackingTransport(
        lambda _call: httpx.Response(200, json=response_payload),
        block_first=True,
    )
    runtime = runtime_for(transport, upstream="semantic")
    collector = SemanticScholarCollector(
        runtime=runtime,
        max_retries=0,
        clock=lambda: NOW,
        api_key_provider=lambda: "",
    )
    legacy = asyncio.create_task(
        search_by_author_semantic_scholar(
            "Alice Example",
            max_results=1,
            runtime=runtime,
        )
    )
    current = asyncio.create_task(
        collector.collect(collect_request(source_id="semantic", authors=["Alice Example"]))
    )
    await asyncio.wait_for(transport.first_entered.wait(), timeout=1.0)
    await asyncio.sleep(0)
    assert transport.calls == 1
    transport.release_first.set()
    legacy_output, collector_output = await asyncio.gather(legacy, current)
    assert legacy_output and collector_output.items
    assert transport.maximum_active == 1
    await runtime.aclose()


async def check_retry_after_defers_other_consumer(temp_root: Path) -> None:
    fake_clock = FakeClock()
    transport = TrackingTransport(
        lambda call: (
            httpx.Response(429, headers={"Retry-After": "7"})
            if call == 1
            else httpx.Response(200, text=arxiv_xml())
        )
    )
    transport.read_time = fake_clock.monotonic
    runtime = runtime_for(transport, fake_clock=fake_clock)
    first = await fetch_arxiv_papers(
        keywords=("rate-limit",),
        max_results=1,
        runtime=runtime,
        cache_dir=temp_root / "retry-legacy",
        clock=lambda: NOW,
    )
    collector = ArxivCollector(
        queries=(ArxivQuery("collector", keywords=("after-429",), max_results=1),),
        cache_dir=temp_root / "retry-collector",
        max_retries=0,
        clock=lambda: NOW,
        runtime=runtime,
    )
    second = await collector.collect(collect_request())
    assert first == []
    assert second.coverage.status is CoverageStatus.COMPLETE
    assert transport.times == [0.0, 45.0]
    assert fake_clock.sleeps == [45.0]
    await runtime.aclose()


async def check_cancellation_releases_shared_limiter(temp_root: Path) -> None:
    transport = TrackingTransport(
        lambda _call: httpx.Response(200, text=arxiv_xml()),
        block_first=True,
    )
    runtime = runtime_for(transport)
    legacy = asyncio.create_task(
        fetch_arxiv_papers(
            keywords=("cancel",),
            max_results=1,
            runtime=runtime,
            cache_dir=temp_root / "cancel-legacy",
            clock=lambda: NOW,
        )
    )
    await asyncio.wait_for(transport.first_entered.wait(), timeout=1.0)
    legacy.cancel()
    try:
        await legacy
    except asyncio.CancelledError:
        pass
    else:
        raise AssertionError("legacy consumer cancellation did not propagate")
    transport.block_first = False
    collector = ArxivCollector(
        queries=(ArxivQuery("collector", keywords=("survives",), max_results=1),),
        cache_dir=temp_root / "cancel-collector",
        max_retries=0,
        clock=lambda: NOW,
        runtime=runtime,
    )
    result = await asyncio.wait_for(collector.collect(collect_request()), timeout=1.0)
    assert result.coverage.status is CoverageStatus.COMPLETE
    assert transport.calls == 2 and transport.maximum_active == 1
    await runtime.aclose()


async def check_failure_releases_shared_limiter(temp_root: Path) -> None:
    def responder(call: int) -> httpx.Response:
        if call == 1:
            raise httpx.ConnectError("deterministic fake failure")
        return httpx.Response(200, text=arxiv_xml())

    transport = TrackingTransport(responder)
    runtime = runtime_for(transport)
    failed = await fetch_arxiv_papers(
        keywords=("failure",),
        max_results=1,
        runtime=runtime,
        cache_dir=temp_root / "failure-legacy",
        clock=lambda: NOW,
    )
    collector = ArxivCollector(
        queries=(ArxivQuery("collector", keywords=("after-failure",), max_results=1),),
        cache_dir=temp_root / "failure-collector",
        max_retries=0,
        clock=lambda: NOW,
        runtime=runtime,
    )
    recovered = await collector.collect(collect_request())
    assert failed == []
    assert recovered.coverage.status is CoverageStatus.COMPLETE
    assert transport.calls == 2 and transport.maximum_active == 1
    await runtime.aclose()


def check_import_ownership() -> None:
    feature_sources = (
        ROOT / "features" / "papers" / "arxiv.py",
        ROOT / "features" / "papers" / "collectors.py",
        ROOT / "features" / "papers" / "service.py",
        ROOT / "features" / "papers" / "http.py",
    )
    for path in feature_sources:
        text = path.read_text(encoding="utf-8")
        assert "intel.collectors.arxiv" not in text
        assert "intel.collectors.papers" not in text
    for name in ("arxiv.py", "papers.py"):
        facade = (ROOT / "intel" / "collectors" / name).read_text(encoding="utf-8")
        assert "features.papers" in facade
        assert "AsyncClient" not in facade
        assert "asyncio.Lock" not in facade
    composition = (
        ROOT / "features" / "daily_briefing" / "source_composition.py"
    ).read_text(encoding="utf-8")
    assert "from features.papers import" in composition
    assert "intel.collectors.arxiv" not in composition
    assert "intel.collectors.papers" not in composition
    assert LegacyArxivCollector is ArxivCollector
    assert LegacyCrossrefCollector is CrossrefCollector
    assert LegacySemanticCollector is SemanticScholarCollector


def check_all_collectors_use_injected_runtime() -> None:
    runtime = PaperHttpRuntime(
        policies={
            "arxiv": UpstreamPolicy(),
            "crossref": UpstreamPolicy(),
            "semantic": UpstreamPolicy(),
        }
    )
    arxiv = ArxivCollector(runtime=runtime)
    crossref = CrossrefCollector(runtime=runtime)
    semantic = SemanticScholarCollector(runtime=runtime, api_key_provider=lambda: "")
    assert arxiv.runtime is crossref.runtime is semantic.runtime is runtime
    assert runtime.limiter("arxiv") is arxiv.runtime.limiter("arxiv")
    assert runtime.limiter("crossref") is crossref.runtime.limiter("crossref")
    assert runtime.limiter("semantic") is semantic.runtime.limiter("semantic")


async def main() -> int:
    check_import_ownership()
    check_all_collectors_use_injected_runtime()
    with tempfile.TemporaryDirectory(prefix="kei-pk133-http-") as temp_dir:
        root = Path(temp_dir)
        await check_legacy_and_collector_share_concurrency(root)
        await check_minimum_interval_is_shared(root)
        await check_crossref_legacy_and_collector_share_owner()
        await check_semantic_legacy_and_collector_share_owner()
        await check_retry_after_defers_other_consumer(root)
        await check_cancellation_releases_shared_limiter(root)
        await check_failure_releases_shared_limiter(root)
    print("paper shared HTTP runtime tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
