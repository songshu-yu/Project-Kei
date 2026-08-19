"""PK-133 isolated paper collectors: fake HTTP, fixed clocks, temporary cache."""
from __future__ import annotations

import asyncio
import json
import os
import tempfile
from datetime import date, datetime, timezone
from pathlib import Path

TEST_LOCAL_ROOT = Path(tempfile.gettempdir()) / "project-kei-pk133-tests"
os.environ["PROJECT_KEI_ENV_FILE"] = str(TEST_LOCAL_ROOT / "missing.env")

import _path_setup  # noqa: F401,E402
import httpx  # noqa: E402

from features.daily_briefing.models import (  # noqa: E402
    CacheStatus,
    CollectRequest,
    CollectorResult,
    CoverageStatus,
    IntelItem,
    SourceCoverage,
    rfc3339,
    stable_item_id,
)
from features.papers import (  # noqa: E402
    ArxivCollector,
    ArxivQuery,
    CrossrefCollector,
    PaperCollectorCoordinator,
    SemanticScholarCollector,
    author_name_matches,
    deduplicate_paper_items,
)


NOW = datetime(2026, 7, 22, 8, 0, tzinfo=timezone.utc)
FICTIONAL_AUTHORS = ["Alice Example", "Bob Sample"]


def request(*, refresh: bool = False, authors=None) -> CollectRequest:
    return CollectRequest(
        local_date=date(2026, 7, 22),
        timezone="Asia/Shanghai",
        source_ids=("arxiv", "crossref", "semantic"),
        refresh=refresh,
        lookback=24,
        source_config_snapshot={
            "paper_priority_authors": list(authors if authors is not None else FICTIONAL_AUTHORS),
            "paper_secondary_authors": [],
            "paper_ai_authors": [],
            "arxiv_author_limit": 5,
            "arxiv_author_max_results": 5,
        },
    )


def arxiv_xml() -> str:
    return """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom" xmlns:arxiv="http://arxiv.org/schemas/atom">
  <entry>
    <id>https://arxiv.org/abs/2607.12345v2</id>
    <updated>2026-07-22T02:30:00Z</updated>
    <published>2026-07-22T02:00:00Z</published>
    <title>  A Shared   Paper Title </title>
    <summary>arXiv abstract text.</summary>
    <author><name>Alice Example</name></author>
    <link href="https://arxiv.org/abs/2607.12345v2" rel="alternate" type="text/html" />
    <arxiv:doi>10.1234/Fake.DOI</arxiv:doi>
    <arxiv:primary_category term="cs.AI" />
  </entry>
  <entry>
    <id>https://arxiv.org/abs/2501.00001</id>
    <published>2026-07-20T01:00:00Z</published>
    <title>Old paper outside lookback</title>
    <summary>old</summary>
    <author><name>Alice Example</name></author>
  </entry>
</feed>"""


def check_author_matching() -> None:
    assert author_name_matches("Alice Example", "Example, Alice")
    assert author_name_matches("Alice Example", "A. Example")
    assert author_name_matches("Álice Example", "Alice Example")
    assert not author_name_matches("Alice Example", "Alice Examples")
    assert not author_name_matches("Chao Zuo", "Zhou Chao")
    assert not author_name_matches("Alice Example", "A. Sample")


async def check_arxiv_cache_window_and_refresh(cache_dir: Path) -> None:
    calls = []

    async def handler(incoming: httpx.Request) -> httpx.Response:
        calls.append(str(incoming.url))
        return httpx.Response(200, text=arxiv_xml(), headers={"content-type": "application/atom+xml"})

    collector = ArxivCollector(
        queries=(ArxivQuery("ai", categories=("cs.AI",), max_results=5),),
        cache_dir=cache_dir,
        cache_ttl_seconds=86_400,
        min_interval=0,
        max_retries=0,
        transport=httpx.MockTransport(handler),
        trust_env=False,
        clock=lambda: NOW,
    )
    first = await collector.collect(request(authors=["Alice Example"]))
    assert first.source_id == "arxiv"
    assert first.coverage.status is CoverageStatus.COMPLETE
    assert first.coverage.item_count == 1
    assert len(first.items) == 1 and first.items[0].published_at == "2026-07-22T02:00:00Z"
    assert first.items[0].metadata["doi"] == "10.1234/fake.doi"
    assert len(calls) == 2  # one topic query plus one author query

    second = await collector.collect(request(authors=["Alice Example"]))
    assert second.cache_status is CacheStatus.HIT
    assert len(calls) == 2
    cache_names = [path.name for path in cache_dir.glob("*.xml")]
    assert cache_names and all("alice" not in name.casefold() for name in cache_names)

    refreshed = await collector.collect(request(refresh=True, authors=["Alice Example"]))
    assert refreshed.cache_status is CacheStatus.REFRESHED
    assert len(calls) == 4


async def check_arxiv_failure_is_sanitized(cache_dir: Path) -> None:
    secret_body = "Authorization: Bearer imaginary-secret API_KEY=imaginary-key"

    async def handler(_incoming: httpx.Request) -> httpx.Response:
        return httpx.Response(429, text=secret_body, headers={"Retry-After": "7"})

    collector = ArxivCollector(
        queries=(ArxivQuery("ai", keywords=("safe",), max_results=5),),
        cache_dir=cache_dir,
        min_interval=0,
        max_retries=0,
        transport=httpx.MockTransport(handler),
        clock=lambda: NOW,
    )
    result = await collector.collect(request(authors=[]))
    serialized = json.dumps(result.to_dict(), ensure_ascii=False)
    assert result.coverage.status is CoverageStatus.FAILED
    assert result.retry_after == "2026-07-22T08:00:45Z"
    assert "imaginary-secret" not in serialized and "imaginary-key" not in serialized


async def check_crossref_semantic_fallback_and_dedupe() -> None:
    crossref_queries = []
    semantic_queries = []
    fake_key = "fake-semantic-key"
    secret_body = "token=upstream-body-secret"

    async def handler(incoming: httpx.Request) -> httpx.Response:
        host = incoming.url.host
        if host == "api.crossref.org":
            author = incoming.url.params.get("query.author", "")
            crossref_queries.append(author)
            if author == "Bob Sample":
                return httpx.Response(503, text=secret_body)
            return httpx.Response(
                200,
                json={
                    "message": {
                        "items": [{
                            "DOI": "10.1234/fake.doi",
                            "title": ["A Shared Paper Title"],
                            "author": [{"given": "Alice", "family": "Example"}],
                            "abstract": "",
                            "published": {"date-parts": [[2026, 7, 22]]},
                            "container-title": ["Optica"],
                            "URL": "https://doi.org/10.1234/fake.doi",
                        }]
                    }
                },
            )
        if host == "api.semanticscholar.org":
            author = incoming.url.params.get("query", "")
            semantic_queries.append(author)
            assert incoming.headers.get("x-api-key") == fake_key
            return httpx.Response(
                200,
                json={
                    "data": [{
                        "paperId": "semantic-paper-1",
                        "title": "A Shared Paper Title",
                        "authors": [{"name": "Bob Sample"}],
                        "publicationDate": "2026-07-22",
                        "abstract": "A longer Semantic Scholar abstract used as fallback.",
                        "externalIds": {"DOI": "10.1234/FAKE.DOI"},
                        "url": "https://www.semanticscholar.org/paper/semantic-paper-1",
                        "journal": {"name": "Optica"},
                    }]
                },
            )
        raise AssertionError(f"unexpected fake host: {host}")

    transport = httpx.MockTransport(handler)
    crossref = CrossrefCollector(
        transport=transport,
        clock=lambda: NOW,
        max_retries=0,
        min_interval=0,
    )
    semantic = SemanticScholarCollector(
        transport=transport,
        clock=lambda: NOW,
        max_retries=0,
        min_interval=0,
        api_key_provider=lambda: fake_key,
    )
    coordinator = PaperCollectorCoordinator(
        {"crossref": crossref, "semantic": semantic},
        semantic_fallback_only=True,
        clock=lambda: NOW,
    )
    batch = await coordinator.collect_batch(request())
    by_source = {result.source_id: result for result in batch.results}
    assert tuple(by_source) == ("arxiv", "crossref", "semantic")
    assert by_source["arxiv"].coverage.status is CoverageStatus.NOT_CONFIGURED
    assert by_source["crossref"].coverage.status is CoverageStatus.PARTIAL
    assert by_source["semantic"].coverage.status is CoverageStatus.COMPLETE
    assert crossref_queries == FICTIONAL_AUTHORS
    assert semantic_queries == ["Bob Sample"]  # Alice was already covered; no repeated fallback request.
    assert len(batch.deduplicated_items) == 1
    merged = batch.deduplicated_items[0]
    assert merged.summary.endswith("fallback.")
    assert merged.metadata["discovery_sources"] == ["crossref", "semantic"]
    assert len(merged.metadata["alternate_stable_ids"]) == 2
    assert merged.metadata["matched_authors"] == FICTIONAL_AUTHORS
    serialized = json.dumps([result.to_dict() for result in batch.results], ensure_ascii=False)
    assert "upstream-body-secret" not in serialized
    assert fake_key not in serialized
    assert all(author not in " ".join(by_source["crossref"].warnings) for author in FICTIONAL_AUTHORS)


async def check_fallback_skips_fully_covered_authors() -> None:
    item = IntelItem(
        stable_id=stable_item_id("crossref", upstream_id="10.9999/covered"),
        source_id="crossref",
        category="papers",
        title="Covered",
        author="Alice Example, Bob Sample",
        published_at="2026-07-22T00:00:00Z",
        fetched_at=rfc3339(NOW),
        metadata={"authors": FICTIONAL_AUTHORS, "doi": "10.9999/covered"},
    )

    class FixedCollector:
        def __init__(self, source_id, result):
            self.source_id = source_id
            self.result = result
            self.calls = []

        async def collect(self, collect_request):
            self.calls.append(collect_request)
            return self.result

    crossref = FixedCollector(
        "crossref",
        CollectorResult(
            source_id="crossref",
            items=(item,),
            warnings=(),
            coverage=SourceCoverage(CoverageStatus.COMPLETE, 1),
            fetched_at=rfc3339(NOW),
        ),
    )
    semantic = FixedCollector(
        "semantic",
        CollectorResult(
            source_id="semantic",
            items=(),
            warnings=(),
            coverage=SourceCoverage(CoverageStatus.EMPTY, 0),
            fetched_at=rfc3339(NOW),
        ),
    )
    coordinator = PaperCollectorCoordinator(
        {"crossref": crossref, "semantic": semantic},
        semantic_fallback_only=True,
        clock=lambda: NOW,
    )
    results = await coordinator.collect(request())
    by_source = {result.source_id: result for result in results}
    assert semantic.calls == []
    assert by_source["semantic"].coverage.status is CoverageStatus.EMPTY
    assert by_source["semantic"].cache_status is CacheStatus.BYPASS


async def check_abstract_resolution_without_author_retry() -> None:
    item = IntelItem(
        stable_id=stable_item_id("crossref", upstream_id="10.9999/abstract"),
        source_id="crossref",
        category="papers",
        title="Paper Needing Abstract",
        summary="",
        url="https://doi.org/10.9999/abstract",
        author="Alice Example",
        published_at="2026-07-22T00:00:00Z",
        fetched_at=rfc3339(NOW),
        metadata={"authors": ["Alice Example"], "doi": "10.9999/abstract"},
    )

    class FixedCrossref:
        source_id = "crossref"

        async def collect(self, _request):
            return CollectorResult(
                source_id="crossref",
                items=(item,),
                warnings=(),
                coverage=SourceCoverage(CoverageStatus.COMPLETE, 1),
                fetched_at=rfc3339(NOW),
            )

    calls = []

    async def handler(incoming: httpx.Request) -> httpx.Response:
        calls.append((incoming.url.path, incoming.url.params.get("query", "")))
        assert incoming.headers.get("x-api-key") == "fake-abstract-key"
        assert incoming.url.path.endswith("/paper/DOI:10.9999/abstract")
        return httpx.Response(200, json={"abstract": "Resolved once by DOI without an author retry."})

    semantic = SemanticScholarCollector(
        transport=httpx.MockTransport(handler),
        clock=lambda: NOW,
        max_retries=0,
        min_interval=0,
        api_key_provider=lambda: "fake-abstract-key",
    )
    coordinator = PaperCollectorCoordinator(
        {"crossref": FixedCrossref(), "semantic": semantic},
        semantic_fallback_only=True,
        abstract_resolver=semantic,
        clock=lambda: NOW,
    )
    batch = await coordinator.collect_batch(request(authors=["Alice Example"]))
    by_source = {result.source_id: result for result in batch.results}
    assert by_source["semantic"].cache_status is CacheStatus.BYPASS
    assert by_source["crossref"].items[0].summary.startswith("Resolved once")
    assert by_source["crossref"].items[0].metadata["abstract_source"] == "semantic"
    assert len(calls) == 1 and calls[0][1] == ""


def check_transitive_dedupe() -> None:
    common = {
        "category": "papers",
        "published_at": "2026-07-22T00:00:00Z",
        "fetched_at": rfc3339(NOW),
    }
    arxiv = IntelItem(
        stable_id="arxiv:a",
        source_id="arxiv",
        title="Transitive Paper",
        url="https://arxiv.org/abs/2607.10000",
        metadata={"arxiv_id": "2607.10000"},
        **common,
    )
    crossref = IntelItem(
        stable_id="crossref:b",
        source_id="crossref",
        title="Transitive Paper",
        url="https://doi.org/10.5555/transitive",
        metadata={"doi": "10.5555/transitive"},
        **common,
    )
    semantic = IntelItem(
        stable_id="semantic:c",
        source_id="semantic",
        title="Different publisher casing",
        summary="filled abstract",
        metadata={"doi": "https://doi.org/10.5555/TRANSITIVE", "arxiv_id": "2607.10000"},
        **common,
    )
    merged = deduplicate_paper_items((semantic, crossref, arxiv))
    assert len(merged) == 1
    assert merged[0].stable_id.startswith("shared:")
    assert merged[0].metadata["discovery_sources"] == ["arxiv", "crossref", "semantic"]
    assert merged[0].summary == "filled abstract"
    assert deduplicate_paper_items((arxiv, crossref, semantic))[0].stable_id == merged[0].stable_id


async def main() -> int:
    check_author_matching()
    check_transitive_dedupe()
    with tempfile.TemporaryDirectory(prefix="kei-pk133-") as temp_dir:
        root = Path(temp_dir)
        await check_arxiv_cache_window_and_refresh(root / "arxiv-cache")
        await check_arxiv_failure_is_sanitized(root / "arxiv-failure")
    await check_crossref_semantic_fallback_and_dedupe()
    await check_fallback_skips_fully_covered_authors()
    await check_abstract_resolution_without_author_retry()
    print("paper collector tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
