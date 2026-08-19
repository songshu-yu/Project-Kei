"""PK-119 cross-source composition, API and side-effect isolation checks."""
from __future__ import annotations

import asyncio
import builtins
import io
import json
import os
import re
import tempfile
from contextlib import ExitStack, redirect_stdout
from datetime import date, datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import httpx
from fastapi import FastAPI

import _path_setup  # noqa: F401

from features.daily_briefing.models import (
    PUBLIC_SOURCE_IDS,
    CacheStatus,
    CollectRequest,
    CollectorResult,
    CoverageStatus,
    IntelItem,
    SourceCoverage,
    rfc3339,
)
from features.daily_briefing.router import create_briefing_router
from features.daily_briefing.source_composition import (
    CollectorCloseError,
    ProjectCollectorGateway,
    create_project_collector_gateway,
)
from features.github_intel import GitHubCollector
from features.intel_sources import IntelSourceConfigRepository, IntelSourceRegistry
from features.intel_sources.repository import DEFAULT_PATH as INTEL_SOURCES_PATH
from features.intel_sources.router import (
    create_intel_sources_router,
    create_legacy_intel_sources_router,
)
from features.papers import PaperCollectorCoordinator
from features.rss_intel import RSSIntelCollector
from features.youtube import YouTubeCollector
from intel.collectors.arxiv import ArxivCollector
from intel.collectors.bilibili import BilibiliCollector
from intel.collectors.papers import CrossrefCollector, SemanticScholarCollector
from intel.collectors.twitter import NitterCollector
from services.bilibili_profile_cache import DEFAULT_PATH as BILIBILI_PROFILE_PATH
from services.daily_briefing import DailyBriefingService
from services.x_daily_posts import DEFAULT_PATH as X_POSTS_PATH
from services.x_profile_cache import DEFAULT_PATH as X_PROFILE_PATH


NOW = datetime(2026, 7, 22, 1, 0, tzinfo=timezone.utc)
SERVER_ROOT = Path(__file__).resolve().parents[1]


def _lexical_path(value: object) -> str | None:
    if isinstance(value, int):
        return None
    try:
        return os.path.normcase(os.path.abspath(os.fspath(value)))
    except TypeError:
        return None


def _is_within(path: str, root: str) -> bool:
    try:
        return os.path.commonpath((path, root)) == root
    except ValueError:
        return False


class ProtectedPathTripwire:
    """Block protected state access before I/O and audit test writes."""

    def __init__(self, protected_paths: set[Path]) -> None:
        self._protected = {
            path
            for value in protected_paths
            if (path := _lexical_path(value)) is not None
        }
        self._write_root: str | None = None
        self.protected_attempts: list[tuple[str, str]] = []
        self.outside_write_attempts: list[tuple[str, str]] = []
        self.writes: list[tuple[str, str]] = []
        self._stack = ExitStack()

    def audit_writes_under(self, root: Path) -> None:
        normalized = _lexical_path(root)
        assert normalized is not None
        self._write_root = normalized

    def _guard_read(self, value: object, operation: str) -> None:
        path = _lexical_path(value)
        if path in self._protected:
            self.protected_attempts.append((operation, path))
            raise AssertionError(f"protected path read blocked before I/O: {operation}")

    def _guard_write(self, value: object, operation: str) -> None:
        path = _lexical_path(value)
        if path is None:
            return
        if path in self._protected:
            self.protected_attempts.append((operation, path))
            raise AssertionError(f"protected path write blocked before I/O: {operation}")
        if self._write_root is not None and not _is_within(path, self._write_root):
            self.outside_write_attempts.append((operation, path))
            raise AssertionError(f"write outside isolated temporary root: {operation}")
        if self._write_root is not None:
            self.writes.append((operation, path))

    def assert_isolated(self) -> None:
        assert self.protected_attempts == []
        assert self.outside_write_attempts == []
        assert self._write_root is not None
        assert all(_is_within(path, self._write_root) for _, path in self.writes)

    def __enter__(self) -> "ProtectedPathTripwire":
        original_builtin_open = builtins.open
        original_path_open = Path.open
        original_path_stat = Path.stat
        original_path_lstat = Path.lstat
        original_path_mkdir = Path.mkdir
        original_path_unlink = Path.unlink
        original_path_replace = Path.replace
        original_path_rename = Path.rename
        original_named_temporary_file = tempfile.NamedTemporaryFile
        original_os_stat = os.stat
        original_os_lstat = os.lstat
        original_os_replace = os.replace
        original_os_rename = os.rename
        original_os_remove = os.remove
        original_os_unlink = os.unlink

        def guarded_builtin_open(file, mode="r", *args, **kwargs):
            if any(marker in mode for marker in ("w", "a", "x", "+")):
                self._guard_write(file, "open")
            else:
                self._guard_read(file, "open")
            return original_builtin_open(file, mode, *args, **kwargs)

        def guarded_path_open(path, mode="r", *args, **kwargs):
            if any(marker in mode for marker in ("w", "a", "x", "+")):
                self._guard_write(path, "Path.open")
            else:
                self._guard_read(path, "Path.open")
            return original_path_open(path, mode, *args, **kwargs)

        def guarded_path_stat(path, *args, **kwargs):
            self._guard_read(path, "Path.stat")
            return original_path_stat(path, *args, **kwargs)

        def guarded_path_lstat(path, *args, **kwargs):
            self._guard_read(path, "Path.lstat")
            return original_path_lstat(path, *args, **kwargs)

        def guarded_path_mkdir(path, *args, **kwargs):
            self._guard_write(path, "Path.mkdir")
            return original_path_mkdir(path, *args, **kwargs)

        def guarded_path_unlink(path, *args, **kwargs):
            self._guard_write(path, "Path.unlink")
            return original_path_unlink(path, *args, **kwargs)

        def guarded_path_replace(path, target):
            self._guard_write(path, "Path.replace.source")
            self._guard_write(target, "Path.replace.target")
            return original_path_replace(path, target)

        def guarded_path_rename(path, target):
            self._guard_write(path, "Path.rename.source")
            self._guard_write(target, "Path.rename.target")
            return original_path_rename(path, target)

        def guarded_named_temporary_file(*args, **kwargs):
            directory = kwargs.get("dir")
            if directory is None:
                if self._write_root is not None:
                    self.outside_write_attempts.append(("NamedTemporaryFile", "<default>"))
                    raise AssertionError("temporary write has no isolated directory")
            else:
                self._guard_write(directory, "NamedTemporaryFile.dir")
            return original_named_temporary_file(*args, **kwargs)

        def guarded_os_stat(path, *args, **kwargs):
            self._guard_read(path, "os.stat")
            return original_os_stat(path, *args, **kwargs)

        def guarded_os_lstat(path, *args, **kwargs):
            self._guard_read(path, "os.lstat")
            return original_os_lstat(path, *args, **kwargs)

        def guarded_os_replace(source, target):
            self._guard_write(source, "os.replace.source")
            self._guard_write(target, "os.replace.target")
            return original_os_replace(source, target)

        def guarded_os_rename(source, target):
            self._guard_write(source, "os.rename.source")
            self._guard_write(target, "os.rename.target")
            return original_os_rename(source, target)

        def guarded_os_remove(path, *args, **kwargs):
            self._guard_write(path, "os.remove")
            return original_os_remove(path, *args, **kwargs)

        def guarded_os_unlink(path, *args, **kwargs):
            self._guard_write(path, "os.unlink")
            return original_os_unlink(path, *args, **kwargs)

        for target, name, replacement in (
            (builtins, "open", guarded_builtin_open),
            (Path, "open", guarded_path_open),
            (Path, "stat", guarded_path_stat),
            (Path, "lstat", guarded_path_lstat),
            (Path, "mkdir", guarded_path_mkdir),
            (Path, "unlink", guarded_path_unlink),
            (Path, "replace", guarded_path_replace),
            (Path, "rename", guarded_path_rename),
            (tempfile, "NamedTemporaryFile", guarded_named_temporary_file),
            (os, "stat", guarded_os_stat),
            (os, "lstat", guarded_os_lstat),
            (os, "replace", guarded_os_replace),
            (os, "rename", guarded_os_rename),
            (os, "remove", guarded_os_remove),
            (os, "unlink", guarded_os_unlink),
        ):
            self._stack.enter_context(patch.object(target, name, replacement))
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        self._stack.close()


PROTECTED_LOCAL_PATHS = {
    INTEL_SOURCES_PATH,
    X_PROFILE_PATH,
    X_POSTS_PATH,
    SERVER_ROOT / "data" / "x_daily_replies.json",
    BILIBILI_PROFILE_PATH,
    SERVER_ROOT / ".env",
    SERVER_ROOT / "data" / "fitness_checkins.json",
    SERVER_ROOT / "systems" / "data" / "calendar_memo.json",
    SERVER_ROOT / "systems" / "data" / "demon_slayer.json",
    SERVER_ROOT / "systems" / "data" / "focus_timer.json",
}


class FakeCollector:
    def __init__(self, source_id: str, *, fail: bool = False):
        self.source_id = source_id
        self.fail = fail
        self.calls = []
        self.closed = False

    async def collect(self, request):
        self.calls.append(request)
        if self.fail:
            raise RuntimeError("fake failure body must stay internal")
        return CollectorResult(
            source_id=self.source_id,
            items=(),
            warnings=(),
            coverage=SourceCoverage(CoverageStatus.EMPTY),
            fetched_at=rfc3339(NOW),
            cache_status=CacheStatus.FETCHED,
        )

    async def aclose(self):
        self.closed = True


class CountingGateway:
    def __init__(self):
        self.calls = []

    async def collect(self, request):
        self.calls.append(request)
        return tuple(
            CollectorResult(
                source_id=source_id,
                items=(),
                warnings=(),
                coverage=SourceCoverage(CoverageStatus.EMPTY),
                fetched_at=rfc3339(NOW),
                cache_status=CacheStatus.REFRESHED if request.refresh else CacheStatus.FETCHED,
            )
            for source_id in request.source_ids
        )


class FakeTextGenerator:
    system_prompt = "test system prompt"

    def __init__(self):
        self.calls = []

    async def generate_text(self, system, user, **kwargs):
        self.calls.append((system, user, kwargs))
        return SimpleNamespace(
            text="test narration",
            generated=True,
            fallback=False,
            error_code=None,
        )


def defaults():
    return {
        "twitter_users": [],
        "money_twitter_users": [],
        "github_users": [],
        "github_repos": [],
        "bilibili_uids": [],
        "youtube_channel_ids": [],
        "paper_priority_authors": [],
        "paper_secondary_authors": [],
        "paper_ai_authors": [],
    }


async def check_gateway() -> None:
    platform = {
        source_id: FakeCollector(source_id, fail=source_id == "github")
        for source_id in ("twitter", "github", "bilibili", "youtube", "money")
    }
    papers = {
        source_id: FakeCollector(source_id)
        for source_id in ("arxiv", "crossref", "semantic")
    }
    gateway = ProjectCollectorGateway(
        platform,
        PaperCollectorCoordinator(papers, semantic_fallback_only=True, clock=lambda: NOW),
    )
    request = CollectRequest(
        local_date=date(2026, 7, 22),
        timezone="Asia/Shanghai",
        source_ids=PUBLIC_SOURCE_IDS,
        refresh=False,
        lookback=24,
        source_config_snapshot=defaults(),
    )
    output = io.StringIO()
    with redirect_stdout(output):
        results = tuple(await gateway.collect(request))
    assert tuple(result.source_id for result in results) == PUBLIC_SOURCE_IDS
    github = next(result for result in results if result.source_id == "github")
    assert github.coverage.status is CoverageStatus.FAILED
    assert "fake failure body" not in " ".join((*github.warnings, github.coverage.detail))
    assert "fake failure body" not in output.getvalue()
    assert all(len(collector.calls) == 1 for collector in (*platform.values(), *papers.values()))
    await gateway.aclose()
    assert all(collector.closed for collector in (*platform.values(), *papers.values()))


async def check_paper_gateway_does_not_impose_total_timeout() -> None:
    entered = asyncio.Event()
    release = asyncio.Event()

    class SlowPaper(FakeCollector):
        async def collect(self, request):
            entered.set()
            await release.wait()
            return await super().collect(request)

    paper = SlowPaper("arxiv")
    gateway = ProjectCollectorGateway(
        {},
        PaperCollectorCoordinator(
            {"arxiv": paper},
            semantic_fallback_only=False,
            clock=lambda: NOW,
        ),
    )
    request = CollectRequest(
        local_date=date(2026, 7, 22),
        timezone="Asia/Shanghai",
        source_ids=("arxiv",),
        refresh=True,
        lookback=24,
        source_config_snapshot=defaults(),
    )
    task = asyncio.create_task(gateway.collect(request))
    await entered.wait()
    await asyncio.sleep(0.02)
    assert not task.done()
    release.set()
    results = tuple(await task)
    assert len(results) == 1
    assert results[0].source_id == "arxiv"
    assert results[0].coverage.status is CoverageStatus.EMPTY
    await gateway.aclose()


async def check_close_failure_isolation() -> None:
    class CloseProbe(FakeCollector):
        def __init__(self, source_id: str, *, fail_close: bool, timeline: list[str]):
            super().__init__(source_id)
            self.fail_close = fail_close
            self.timeline = timeline

        async def aclose(self):
            self.timeline.append(self.source_id)
            self.closed = True
            if self.fail_close:
                raise RuntimeError("fake close detail must stay internal")

    for failed_source in ("twitter", "github", "arxiv"):
        timeline: list[str] = []
        probes = {
            source_id: CloseProbe(
                source_id,
                fail_close=source_id == failed_source,
                timeline=timeline,
            )
            for source_id in ("twitter", "github", "arxiv")
        }
        gateway = ProjectCollectorGateway(
            {"twitter": probes["twitter"], "github": probes["github"]},
            PaperCollectorCoordinator(
                {
                    "arxiv": probes["arxiv"],
                    # The same object is deliberately registered twice: it must
                    # still be closed exactly once when another close fails.
                    "crossref": probes["twitter"],
                },
                semantic_fallback_only=False,
                clock=lambda: NOW,
            ),
        )
        try:
            await gateway.aclose()
        except CollectorCloseError as exc:
            assert exc.failures == ((failed_source, "RuntimeError"),)
            assert "fake close detail" not in str(exc)
        else:
            raise AssertionError("a close failure must be reported after cleanup")
        assert timeline == ["twitter", "github", "arxiv"]
        assert all(probe.closed for probe in probes.values())


async def check_production_factory() -> None:
    class FakeConfig:
        NITTER_INSTANCES = ("https://nitter.example/feed",)
        MONEY_CONFIG = {
            "rss_feeds": ("https://feeds.example/money.xml",),
            "keywords": ("finance", "AI"),
        }
        ARXIV_CONFIG = {
            "ai": {
                "categories": ("cs.AI",),
                "keywords": ("agents",),
                "max_results": 3,
            },
        }
        PAPER_ENABLE_CROSSREF_DAILY_SCAN = True
        PAPER_ENABLE_SEMANTIC_SCHOLAR = True
        PAPER_SEMANTIC_SCHOLAR_FALLBACK_ONLY = True
        PAPER_CROSSREF_MAX_PER_JOURNAL = 4
        PAPER_SEMANTIC_SCHOLAR_MAX_RESULTS = 6

    environment = {
        "PAPER_ENABLE_CROSSREF_DAILY_SCAN": "true",
        "PAPER_ENABLE_SEMANTIC_SCHOLAR": "true",
        "PAPER_SEMANTIC_SCHOLAR_FALLBACK_ONLY": "true",
    }
    with patch.dict(os.environ, environment, clear=False):
        gateway = create_project_collector_gateway(FakeConfig)
    try:
        assert gateway.supported_source_ids == PUBLIC_SOURCE_IDS
        assert isinstance(gateway._collectors["twitter"], NitterCollector)
        assert isinstance(gateway._collectors["github"], GitHubCollector)
        assert isinstance(gateway._collectors["bilibili"], BilibiliCollector)
        assert isinstance(gateway._collectors["youtube"], YouTubeCollector)
        assert isinstance(gateway._collectors["money"], RSSIntelCollector)
        assert gateway._collectors["twitter"]._instances == ("https://nitter.example/feed",)
        assert gateway._collectors["money"]._policy.feed_urls == ("https://feeds.example/money.xml",)
        assert gateway._collectors["money"]._keywords == ("finance", "ai")

        paper_collectors = gateway._paper_coordinator.collectors
        assert isinstance(paper_collectors["arxiv"], ArxivCollector)
        assert isinstance(paper_collectors["crossref"], CrossrefCollector)
        assert isinstance(paper_collectors["semantic"], SemanticScholarCollector)
        assert paper_collectors["arxiv"].queries[0].categories == ("cs.AI",)
        assert paper_collectors["arxiv"].queries[0].keywords == ("agents",)
    finally:
        await gateway.aclose()


async def check_concurrency_and_paper_serialization() -> None:
    started = 0
    all_platforms_started = asyncio.Event()
    release_platforms = asyncio.Event()
    paper_timeline = []

    class BlockingPlatform(FakeCollector):
        async def collect(self, request):
            nonlocal started
            self.calls.append(request)
            started += 1
            if started == 5:
                all_platforms_started.set()
            await release_platforms.wait()
            return await super().collect(request)

    class OrderedPaper(FakeCollector):
        async def collect(self, request):
            paper_timeline.append(("start", self.source_id))
            await asyncio.sleep(0)
            result = await super().collect(request)
            paper_timeline.append(("end", self.source_id))
            return result

    platform = {
        source_id: BlockingPlatform(source_id)
        for source_id in ("twitter", "github", "bilibili", "youtube", "money")
    }
    papers = {
        source_id: OrderedPaper(source_id)
        for source_id in ("arxiv", "crossref", "semantic")
    }
    gateway = ProjectCollectorGateway(
        platform,
        PaperCollectorCoordinator(papers, semantic_fallback_only=False, clock=lambda: NOW),
    )
    request = CollectRequest(
        local_date=date(2026, 7, 22),
        timezone="Asia/Shanghai",
        source_ids=PUBLIC_SOURCE_IDS,
        refresh=False,
        lookback=24,
        source_config_snapshot=defaults(),
    )
    task = asyncio.create_task(gateway.collect(request))
    await asyncio.wait_for(all_platforms_started.wait(), timeout=1.0)
    assert started == 5
    release_platforms.set()
    results = tuple(await asyncio.wait_for(task, timeout=1.0))
    assert tuple(result.source_id for result in results) == PUBLIC_SOURCE_IDS
    assert paper_timeline == [
        ("start", "arxiv"), ("end", "arxiv"),
        ("start", "crossref"), ("end", "crossref"),
        ("start", "semantic"), ("end", "semantic"),
    ]
    await gateway.aclose()


async def check_registry_router(root: Path) -> None:
    registry = IntelSourceRegistry(
        IntelSourceConfigRepository(root / "intel_sources.json"),
        defaults_provider=defaults,
        clock=lambda: NOW,
    )
    app = FastAPI()
    app.include_router(create_intel_sources_router(
        registry,
        local_control_guard=lambda request: request.headers.get("origin", "") in {"", "http://localhost:8000"},
        local_read_guard=lambda request: request.headers.get("x-project-kei-read") == "1",
    ))
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.get(
            "/api/v1/intel-sources",
            headers={"x-project-kei-read": "1"},
        )
        assert response.status_code == 200 and response.json()["using_local_override"] is False
        assert (await client.get("/api/v1/intel-sources")).status_code == 403
        response = await client.put(
            "/api/v1/intel-sources",
            json={**defaults(), "youtube_channel_ids": ["UC1234567890123456789012"]},
        )
        assert response.status_code == 200 and response.json()["using_local_override"] is True
        response = await client.post(
            "/api/v1/intel-sources/github_users",
            json={"value": "example-user"},
        )
        assert response.status_code == 200 and response.json()["github_users"] == ["example-user"]
        response = await client.put(
            "/api/v1/intel-sources/github_users/0",
            json={"value": "renamed-user"},
        )
        assert response.status_code == 200 and response.json()["github_users"] == ["renamed-user"]
        response = await client.delete("/api/v1/intel-sources/github_users/0")
        assert response.status_code == 200 and response.json()["github_users"] == []
        response = await client.put(
            "/api/v1/intel-sources",
            headers={"origin": "https://attacker.example"},
            json=defaults(),
        )
        assert response.status_code == 403


async def check_legacy_and_versioned_origin_parity(root: Path) -> None:
    from features.bilibili.router import create_bilibili_router
    from features.bilibili.service import BilibiliService
    from features.x_monitor.router import build_router as build_x_monitor_router
    from features.x_monitor.service import XMonitorService

    tripwire = ProtectedPathTripwire(PROTECTED_LOCAL_PATHS)
    with tripwire:
        tripwire.audit_writes_under(root)
        registry = IntelSourceRegistry(
            IntelSourceConfigRepository(root / "intel-sources.json"),
            defaults_provider=defaults,
            clock=lambda: NOW,
        )
        registry.replace({
            **defaults(),
            "twitter_users": ["ExampleUser"],
            "bilibili_uids": ["123456"],
        })
        before = (root / "intel-sources.json").read_bytes()
        profile_calls: list[str] = []
        post_calls: list[str] = []

        async def fake_x_profile(username: str):
            profile_calls.append(username)
            return {"name": "Public example", "avatar_url": "https://example.invalid/avatar.png"}

        async def fake_x_posts(username: str):
            post_calls.append(username)
            return []

        async def fake_bilibili_profile(uid: str):
            profile_calls.append(uid)
            return {"name": "Public example", "avatar_url": "https://example.invalid/avatar.png"}

        x_service = XMonitorService(
            profile_path=root / "x-profiles.json",
            posts_path=root / "x-posts.json",
            profile_fetcher=fake_x_profile,
            posts_fetcher=fake_x_posts,
            clock=lambda: NOW,
        )
        bilibili_service = BilibiliService(
            lambda: registry.read()["bilibili_uids"],
            profile_path=root / "bilibili-profiles.json",
            profile_fetcher=fake_bilibili_profile,
            now=NOW,
        )

        def isolated_local_control(request) -> bool:
            client_host = request.client.host if request.client else ""
            origin = request.headers.get("origin", "")
            return client_host in {"127.0.0.1", "::1", "localhost"} and origin in {
                "",
                "http://127.0.0.1:8000",
                "http://localhost:8000",
            }

        isolated_versioned_app = FastAPI()
        isolated_versioned_app.include_router(create_intel_sources_router(
            registry,
            local_control_guard=isolated_local_control,
        ))
        isolated_versioned_app.include_router(create_bilibili_router(
            bilibili_service,
            local_request_guard=isolated_local_control,
        ))
        isolated_versioned_app.include_router(
            build_x_monitor_router(x_service, registry.read)
        )
        isolated_legacy_app = FastAPI()
        isolated_legacy_app.include_router(create_legacy_intel_sources_router(
            registry,
            local_control_guard=isolated_local_control,
        ))
        isolated_legacy_app.include_router(
            build_x_monitor_router(
                x_service,
                registry.read,
                include_legacy=True,
            )
        )

        malicious = {"origin": "https://attacker.example"}
        legacy_requests = (
            ("GET", "/dashboard/intel-sources", None),
            ("PUT", "/dashboard/intel-sources", defaults()),
            ("POST", "/dashboard/intel-sources/x-profiles/resolve?username=ExampleUser&refresh=true", None),
            ("GET", "/dashboard/intel-sources/x-posts", None),
            ("POST", "/dashboard/intel-sources/x-posts/fetch?username=ExampleUser&refresh=true", None),
        )
        versioned_requests = (
            ("PUT", "/api/v1/intel-sources", defaults()),
            ("POST", "/api/v1/bilibili/profiles/resolve", {"uid": "123456", "refresh": True}),
            ("GET", "/api/v1/x/profiles", None),
            ("GET", "/api/v1/x/posts", None),
            ("POST", "/api/v1/x/profiles/resolve?username=ExampleUser&refresh=true", None),
            ("POST", "/api/v1/x/posts/fetch?username=ExampleUser", None),
            (
                "POST",
                "/api/v1/x/posts/query",
                {"username": "ExampleUser", "mode": "day", "date": "2026-07-22"},
            ),
        )
        assert all(not url.startswith("/api/v1/") for _, url, _ in legacy_requests)
        assert all(url.startswith("/api/v1/") for _, url, _ in versioned_requests)

        async with httpx.AsyncClient(
                transport=httpx.ASGITransport(
                    app=isolated_legacy_app,
                    client=("127.0.0.1", 43119),
                ),
                base_url="http://test",
            ) as legacy_client, httpx.AsyncClient(
                transport=httpx.ASGITransport(
                    app=isolated_versioned_app,
                    client=("127.0.0.1", 43120),
                ),
                base_url="http://test",
            ) as versioned_client:
                for method, url, body in legacy_requests:
                    response = await legacy_client.request(
                        method,
                        url,
                        headers=malicious,
                        json=body,
                    )
                    assert response.status_code == 403, (method, url, response.status_code)
                for method, url, body in versioned_requests:
                    response = await versioned_client.request(
                        method,
                        url,
                        headers=malicious,
                        json=body,
                    )
                    assert response.status_code == 403, (method, url, response.status_code)

                assert profile_calls == [] and post_calls == []
                assert (await legacy_client.get("/dashboard/intel-sources")).status_code == 200
                legacy_posts = await legacy_client.get("/dashboard/intel-sources/x-posts")
                versioned_posts = await versioned_client.get("/api/v1/x/posts")
                assert legacy_posts.status_code == versioned_posts.status_code == 200
                assert legacy_posts.json() == versioned_posts.json()
                assert post_calls == []

                legacy_fetch = await legacy_client.post(
                    "/dashboard/intel-sources/x-posts/fetch?username=ExampleUser"
                )
                versioned_fetch = await versioned_client.post(
                    "/api/v1/x/posts/fetch?username=ExampleUser"
                )
                assert legacy_fetch.status_code == versioned_fetch.status_code == 200
                assert legacy_fetch.json() == versioned_fetch.json()
                cached_posts_before_query = (root / "x-posts.json").read_bytes()
                versioned_query = await versioned_client.post(
                    "/api/v1/x/posts/query",
                    json={
                        "username": "ExampleUser",
                        "mode": "day",
                        "date": "2026-07-22",
                    },
                )
                assert versioned_query.status_code == 200
                assert versioned_query.json()["timezone"] == "Asia/Shanghai"
                assert (root / "x-posts.json").read_bytes() == cached_posts_before_query

        assert (root / "intel-sources.json").read_bytes() == before
        assert profile_calls == []
        assert post_calls == ["ExampleUser", "ExampleUser", "ExampleUser"]
        tripwire.assert_isolated()


def check_protected_path_tripwire() -> None:
    tripwire = ProtectedPathTripwire(PROTECTED_LOCAL_PATHS)
    with tripwire:
        for mode in ("rb", "wb"):
            try:
                X_POSTS_PATH.open(mode)
            except AssertionError as exc:
                assert "blocked before I/O" in str(exc)
            else:
                raise AssertionError(
                    f"protected-path tripwire did not intercept mode={mode}"
                )
    assert len(tripwire.protected_attempts) == 2
    assert [operation for operation, _ in tripwire.protected_attempts] == [
        "Path.open",
        "Path.open",
    ]


async def check_api_side_effect_boundaries(root: Path) -> None:
    registry = IntelSourceRegistry(
        IntelSourceConfigRepository(root / "intel_sources.json"),
        defaults_provider=defaults,
        clock=lambda: NOW,
    )
    gateway = CountingGateway()
    generator = FakeTextGenerator()
    briefing = DailyBriefingService(
        text_generator=generator,
        root_dir=root,
        gateway=gateway,
        source_config_provider=registry.snapshot,
        clock=lambda: NOW,
    )
    app = FastAPI()
    app.include_router(create_intel_sources_router(
        registry,
        local_control_guard=lambda _request: True,
    ))
    app.include_router(create_briefing_router(
        lambda: briefing,
        local_request_guard=lambda _request: True,
    ))
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        payload = {**defaults(), "twitter_users": ["example_user"]}
        assert (await client.get("/api/v1/intel-sources")).status_code == 200
        assert (await client.put("/api/v1/intel-sources", json=payload)).status_code == 200
        assert not gateway.calls and not generator.calls

        assert (await client.get("/api/v1/briefing/today")).json()["ready"] is False
        assert (await client.get("/briefing/today", params={"fetch": "false"})).json()["fetched"] is False
        assert (await client.get("/dashboard/briefing/status")).json()["ready"] is False
        assert not gateway.calls and not generator.calls

        generated = await client.post(
            "/api/v1/briefing/generate",
            json={"source_ids": ["twitter"], "rewrite": True},
        )
        assert generated.status_code == 200
        assert len(gateway.calls) == 1 and len(generator.calls) == 1
        assert list(gateway.calls[0].source_config_snapshot["twitter_users"]) == ["example_user"]

        assert (await client.post(
            "/api/v1/intel-sources/github_users",
            json={"value": "example-org"},
        )).status_code == 200
        assert (await client.put(
            "/api/v1/intel-sources/github_users/0",
            json={"value": "renamed-org"},
        )).status_code == 200
        assert (await client.delete("/api/v1/intel-sources/github_users/0")).status_code == 200
        assert len(gateway.calls) == 1 and len(generator.calls) == 1

        versioned = (await client.get("/api/v1/briefing/today")).json()
        legacy = (await client.get(
            "/briefing/today",
            params={"fetch": "false", "rewrite": "true"},
        )).json()
        assert versioned["text"] == legacy["text"]
        assert versioned["script"] == legacy["script"]
        assert versioned["collector_contract_version"] == legacy["collector_contract_version"] == "1.0"
        assert len(gateway.calls) == 1 and len(generator.calls) == 1

        refreshed = await client.post(
            "/api/v1/briefing/refresh",
            json={"source_ids": ["twitter"], "rewrite": False},
        )
        assert refreshed.status_code == 200 and len(gateway.calls) == 2


async def check_cross_source_redaction(root: Path) -> None:
    secrets = {
        "warning-secret-119",
        "coverage-secret-119",
        "title-secret-119",
        "summary-secret-119",
        "url-secret-119",
        "metadata-secret-119",
    }

    class SecretGateway:
        async def collect(self, request):
            results = []
            for source_id in request.source_ids:
                item = IntelItem(
                    stable_id=f"{source_id}:fixture",
                    source_id=source_id,
                    category="papers" if source_id in {"arxiv", "crossref", "semantic"} else "general",
                    title="Authorization=Bearer title-secret-119 public title",
                    summary="Cookie=summary-secret-119 public summary",
                    url="https://public.example/item?token=url-secret-119&view=1",
                    author="Example",
                    published_at=rfc3339(NOW),
                    fetched_at=rfc3339(NOW),
                    metadata={"api_key": "metadata-secret-119", "safe": "visible"},
                )
                results.append(CollectorResult(
                    source_id=source_id,
                    items=(item,),
                    warnings=("Authorization=Bearer warning-secret-119",),
                    coverage=SourceCoverage(
                        CoverageStatus.PARTIAL,
                        1,
                        detail="token=coverage-secret-119 partial source",
                    ),
                    fetched_at=rfc3339(NOW),
                    cache_status=CacheStatus.FETCHED,
                ))
            return tuple(results)

    generator = FakeTextGenerator()
    briefing = DailyBriefingService(
        text_generator=generator,
        root_dir=root,
        gateway=SecretGateway(),
        source_config_provider=defaults,
        clock=lambda: NOW,
    )
    document = await briefing.core.generate(
        local_date=date(2026, 7, 22),
        source_ids=PUBLIC_SOURCE_IDS,
        rewrite=True,
    )
    cache_text = briefing.repository.cache_path("2026-07-22").read_text(encoding="utf-8")
    prompt_text = json.dumps(generator.calls, ensure_ascii=False, default=str)
    public_text = json.dumps(briefing.core.public_result(document), ensure_ascii=False)
    combined = "\n".join((cache_text, prompt_text, public_text))
    assert not any(secret in combined for secret in secrets)
    assert "view=1" in combined and "visible" in combined


def check_state_and_dashboard_isolation() -> None:
    from intel.collectors.arxiv import ARXIV_CACHE_DIR

    state_paths = {
        _lexical_path(X_PROFILE_PATH),
        _lexical_path(X_POSTS_PATH),
        _lexical_path(BILIBILI_PROFILE_PATH),
        _lexical_path(ARXIV_CACHE_DIR),
    }
    assert len(state_paths) == 4

    server_root = Path(__file__).resolve().parents[1]
    collector_paths = (
        server_root / "intel" / "collectors" / "twitter.py",
        server_root / "intel" / "collectors" / "bilibili.py",
        server_root / "features" / "youtube" / "collector.py",
        server_root / "features" / "github_intel" / "collector.py",
        server_root / "features" / "rss_intel" / "collector.py",
    )
    protected_state_names = {
        "intel_sources.json", "x_profiles.json", "x_daily_posts.json",
        "bilibili_profiles.json", "briefing_cache",
    }
    for path in collector_paths:
        source = path.read_text(encoding="utf-8")
        assert not any(name in source for name in protected_state_names), path

    dashboard = (server_root / "static" / "dashboard.html").read_text(encoding="utf-8")
    panel_storage = (server_root / "static" / "dashboard" / "panels.js").read_text(encoding="utf-8")
    persist_source = (
        server_root
        / "features"
        / "intel_sources"
        / "package_source"
        / "dashboard"
        / "index.js"
    ).read_text(encoding="utf-8")
    assert "/api/v1/intel-sources" in persist_source
    assert ".request(" in persist_source and "fetch(" not in persist_source
    assert "briefing/generate" not in persist_source and "refresh=true" not in persist_source
    assert "localStorage" not in dashboard and "sessionStorage" not in dashboard
    assert "localStorage" in panel_storage and "panel-open" in panel_storage
    assert not any(
        marker in panel_storage
        for marker in ("twitter_users", "github_repos", "bilibili_uids", "youtube_channel_ids", "api_key", "cookie", "token")
    )


async def main() -> int:
    await check_gateway()
    await check_paper_gateway_does_not_impose_total_timeout()
    await check_close_failure_isolation()
    await check_production_factory()
    await check_concurrency_and_paper_serialization()
    with tempfile.TemporaryDirectory(prefix="kei-pk119-") as temp_dir:
        root = Path(temp_dir)
        await check_registry_router(root / "registry")
        await check_legacy_and_versioned_origin_parity(root / "origin")
        await check_api_side_effect_boundaries(root / "api")
        await check_cross_source_redaction(root / "redaction")
    check_protected_path_tripwire()
    check_state_and_dashboard_isolation()
    print("PK-119 intelligence source integration tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
