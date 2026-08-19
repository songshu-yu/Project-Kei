"""Isolated PK-110 generation progress checks; no real external services."""
from __future__ import annotations

import asyncio
import json
import os
import tempfile
from datetime import date, datetime, timezone
from pathlib import Path
from types import SimpleNamespace

TEST_ROOT = Path(tempfile.gettempdir()) / "project-kei-pk110-progress-tests"
os.environ["PROJECT_KEI_ENV_FILE"] = str(TEST_ROOT / "missing.env")
os.environ["PROJECT_KEI_LLM_PROFILE_PATH"] = str(TEST_ROOT / "missing-profile.json")

import _path_setup  # noqa: E402,F401
import httpx
from fastapi import FastAPI

from features.daily_briefing.collector_gateway import ContractCollectorGateway
from features.daily_briefing.generation_status import BriefingGenerationTracker
from features.daily_briefing.legacy_adapter import DailyBriefingService
from features.daily_briefing.models import (
    PUBLIC_SOURCE_IDS,
    CacheStatus,
    CollectRequest,
    CollectorResult,
    CoverageStatus,
    SourceCoverage,
    rfc3339,
)
from features.daily_briefing.repository import (
    BriefingCachePersistenceError,
    BriefingRepository,
)
from features.daily_briefing.router import create_briefing_router
from features.daily_briefing.service import BriefingService


class MutableClock:
    def __init__(self, value: datetime | None = None) -> None:
        self.value = value or datetime(2026, 7, 30, 1, 0, tzinfo=timezone.utc)

    def __call__(self) -> datetime:
        return self.value


def collector_result(source_id: str, *, failed: bool = False) -> CollectorResult:
    status = CoverageStatus.FAILED if failed else CoverageStatus.EMPTY
    return CollectorResult(
        source_id=source_id,
        items=(),
        warnings=(f"{source_id}: collector failed",) if failed else (),
        coverage=SourceCoverage(status, 0, detail="collector failed" if failed else ""),
        fetched_at="2026-07-30T01:00:00Z",
        cache_status=CacheStatus.UNAVAILABLE if failed else CacheStatus.FETCHED,
    )


class ObservableGateway:
    def __init__(self) -> None:
        self.calls: list[CollectRequest] = []
        self.first_done = asyncio.Event()
        self.release_rest = asyncio.Event()

    async def collect(self, request: CollectRequest):
        return await self.collect_with_progress(request, lambda result: None)

    async def collect_with_progress(self, request: CollectRequest, on_result):
        self.calls.append(request)
        values = []
        for index, source_id in enumerate(request.source_ids):
            if index:
                await self.release_rest.wait()
            value = collector_result(source_id, failed=source_id == "github")
            values.append(value)
            on_result(value)
            if index == 0:
                self.first_done.set()
        return values


class BlockingGenerator:
    system_prompt = "safe fake system"

    def __init__(self) -> None:
        self.entered = asyncio.Event()
        self.release = asyncio.Event()
        self.calls = 0

    async def generate_text(self, *_args, **_kwargs):
        self.calls += 1
        self.entered.set()
        await self.release.wait()
        return SimpleNamespace(text="fake narration", generated=True)


class ObservedRepository(BriefingRepository):
    def __init__(self, root_dir: Path, *, fail: bool = False):
        super().__init__(root_dir)
        self.fail = fail
        self.status_provider = lambda: {}
        self.saving_snapshot = None
        self.save_calls = 0

    def save_transaction(self, document, *, include_summary):
        self.save_calls += 1
        self.saving_snapshot = self.status_provider()
        if self.fail:
            raise BriefingCachePersistenceError("fictional secret body", cache_state_preserved=True)
        return super().save_transaction(document, include_summary=include_summary)


async def check_stages_source_isolation_and_redaction(root: Path, clock: MutableClock) -> None:
    gateway = ObservableGateway()
    generator = BlockingGenerator()
    repository = ObservedRepository(root)
    service = BriefingService(
        gateway,
        repository,
        text_generator=generator,
        source_config_provider=lambda: {},
        clock=clock,
    )
    repository.status_provider = service.generation_status

    task = asyncio.create_task(service.generate(
        source_ids=("twitter", "github"),
        rewrite=True,
    ))
    await gateway.first_done.wait()
    collecting = service.generation_status()
    assert collecting["state"] == "running"
    assert collecting["phase"] == "collecting"
    assert collecting["completed_sources"] == 1
    assert collecting["total_sources"] == 2
    assert collecting["sources"]["twitter"] == "empty"
    assert collecting["sources"]["github"] == "running"

    gateway.release_rest.set()
    await generator.entered.wait()
    rewriting = service.generation_status()
    assert rewriting["phase"] == "rewriting"
    assert rewriting["completed_sources"] == 2
    assert rewriting["sources"]["github"] == "failed"
    generator.release.set()
    await task

    assert repository.saving_snapshot["phase"] == "saving"
    final = service.generation_status()
    assert final["state"] == "succeeded" and final["phase"] == "finished"
    encoded = json.dumps(final)
    for forbidden in ("fictional", "secret", "prompt", "cookie", "authorization", "http"):
        assert forbidden not in encoded.casefold()
    assert tuple(final["sources"]) == PUBLIC_SOURCE_IDS
    assert all(not codes for codes in final["source_error_codes"].values())


async def check_failure_cancellation_and_cache_reuse(root: Path, clock: MutableClock) -> None:
    gateway = ObservableGateway()
    gateway.release_rest.set()
    repository = ObservedRepository(root, fail=True)
    service = BriefingService(gateway, repository, source_config_provider=lambda: {}, clock=clock)
    repository.status_provider = service.generation_status
    try:
        await service.generate(source_ids=("twitter",), rewrite=False)
    except BriefingCachePersistenceError:
        pass
    else:
        raise AssertionError("persistence failure must propagate")
    failed = service.generation_status()
    assert failed["state"] == "failed"
    assert failed["error_code"] == "cache_save_failed"

    class WaitingGateway:
        async def collect(self, _request):
            await asyncio.Event().wait()

    cancelled_service = BriefingService(
        WaitingGateway(),
        BriefingRepository(root / "cancel"),
        source_config_provider=lambda: {},
        clock=clock,
    )
    pending = asyncio.create_task(cancelled_service.generate(source_ids=("twitter",), rewrite=False))
    await asyncio.sleep(0)
    pending.cancel()
    try:
        await pending
    except asyncio.CancelledError:
        pass
    cancelled = cancelled_service.generation_status()
    assert cancelled["state"] == "failed" and cancelled["error_code"] == "cancelled"

    reusable_gateway = ObservableGateway()
    reusable_gateway.release_rest.set()
    reusable = BriefingService(
        reusable_gateway,
        BriefingRepository(root / "reuse"),
        source_config_provider=lambda: {},
        clock=clock,
    )
    await reusable.generate(source_ids=("twitter",), rewrite=False)
    calls = len(reusable_gateway.calls)
    await reusable.generate(source_ids=("twitter",), rewrite=False)
    reused = reusable.generation_status()
    assert len(reusable_gateway.calls) == calls
    assert reused["state"] == "succeeded"
    assert reused["total_sources"] == 0
    assert all(value == "not_requested" for value in reused["sources"].values())


async def check_status_http_is_read_only(root: Path, clock: MutableClock) -> None:
    class CountingGateway:
        def __init__(self):
            self.calls = 0

        async def collect(self, _request):
            self.calls += 1
            return ()

    gateway = CountingGateway()
    facade = DailyBriefingService(
        root_dir=root,
        gateway=gateway,
        source_config_provider=lambda: {},
        clock=clock,
    )
    app = FastAPI()
    app.include_router(create_briefing_router(lambda: facade, local_request_guard=lambda _request: True))
    stale_path = facade.repository.summary_path
    stale_path.parent.mkdir(parents=True, exist_ok=True)
    stale_bytes = b'{"schema_version":1,"date":"2026-07-29","text":"stale"}\n'
    stale_path.write_bytes(stale_bytes)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://127.0.0.1") as client:
        response = await client.get("/api/v1/briefing/generation-status")
        assert response.status_code == 200
        assert response.json()["state"] == "idle"
        legacy = await client.get("/dashboard/briefing/status")
        assert legacy.status_code == 200
        assert legacy.json()["generation"] == response.json()
    assert gateway.calls == 0
    assert stale_path.read_bytes() == stale_bytes


async def check_contract_gateway_reports_completion_order(clock: MutableClock) -> None:
    release_slow = asyncio.Event()

    class FakeCollector:
        def __init__(self, source_id: str, *, slow: bool):
            self.source_id = source_id
            self.slow = slow

        async def collect(self, _request):
            if self.slow:
                await release_slow.wait()
            return collector_result(self.source_id)

    gateway = ContractCollectorGateway({
        "twitter": FakeCollector("twitter", slow=False),
        "github": FakeCollector("github", slow=True),
    }, clock=clock)
    request = CollectRequest(
        date(2026, 7, 30),
        "Asia/Shanghai",
        ("twitter", "github"),
        source_config_snapshot={},
    )
    seen = []
    first_reported = asyncio.Event()

    def report(value):
        seen.append(value.source_id)
        first_reported.set()

    task = asyncio.create_task(gateway.collect_with_progress(request, report))
    await first_reported.wait()
    assert seen == ["twitter"]
    release_slow.set()
    values = await task
    assert seen == ["twitter", "github"]
    assert [value.source_id for value in values] == ["twitter", "github"]


async def check_contract_gateway_does_not_cancel_slow_source(clock: MutableClock) -> None:
    entered = asyncio.Event()
    release = asyncio.Event()

    class SlowCollector:
        source_id = "twitter"

        async def collect(self, _request):
            entered.set()
            await release.wait()
            return collector_result("twitter")

    class ReadyCollector:
        source_id = "github"

        async def collect(self, _request):
            return collector_result("github")

    gateway = ContractCollectorGateway({
        "twitter": SlowCollector(),
        "github": ReadyCollector(),
    }, clock=clock)
    request = CollectRequest(
        date(2026, 7, 30),
        "Asia/Shanghai",
        ("twitter", "github"),
        source_config_snapshot={},
    )
    seen = []
    task = asyncio.create_task(
        gateway.collect_with_progress(request, lambda result: seen.append(result.source_id))
    )
    await entered.wait()
    await asyncio.sleep(0.02)
    assert not task.done()
    assert seen == ["github"]
    release.set()
    values = tuple(await task)
    assert seen == ["github", "twitter"]
    assert values[0].coverage.status is CoverageStatus.EMPTY
    assert values[1].coverage.status is CoverageStatus.EMPTY


def check_stale_run_cannot_overwrite_new_run(clock: MutableClock) -> None:
    tracker = BriefingGenerationTracker()
    old_token = tracker.start(("twitter",), clock())
    new_token = tracker.start(("github",), clock())
    tracker.fail(old_token, clock(), "generation_failed")
    current = tracker.snapshot(clock())
    assert current["state"] == "running"
    assert current["sources"]["github"] == "pending"
    tracker.succeed(new_token, clock())
    assert tracker.snapshot(clock())["state"] == "succeeded"


def check_patch_collection_replaces_requested_workset(clock: MutableClock) -> None:
    tracker = BriefingGenerationTracker()
    token = tracker.start(PUBLIC_SOURCE_IDS, clock())
    tracker.collecting(token, ("money", "semantic"))
    tracker.source_finished(token, collector_result("money", failed=True))
    tracker.source_finished(token, collector_result("semantic", failed=True))
    tracker.succeed(token, clock())
    current = tracker.snapshot(clock())
    assert current["state"] == "succeeded"
    assert current["completed_sources"] == 2
    assert current["total_sources"] == 2
    assert current["sources"]["money"] == "failed"
    assert current["sources"]["semantic"] == "failed"
    assert all(
        current["sources"][source_id] == "not_requested"
        for source_id in PUBLIC_SOURCE_IDS
        if source_id not in {"money", "semantic"}
    )


def check_source_error_codes_are_finite(clock: MutableClock) -> None:
    tracker = BriefingGenerationTracker()
    token = tracker.start(("twitter",), clock())
    tracker.source_finished(
        token,
        CollectorResult(
            source_id="twitter",
            items=(),
            warnings=(
                "twitter: collector timed out (timeout)",
                "twitter: fictional secret (token_secret_123)",
            ),
            coverage=SourceCoverage(CoverageStatus.FAILED, detail="collector timed out"),
            fetched_at=rfc3339(clock()),
        ),
    )
    tracker.succeed(token, clock())
    current = tracker.snapshot(clock())
    assert current["source_error_codes"]["twitter"] == ["timeout"]
    assert all(
        not codes
        for source_id, codes in current["source_error_codes"].items()
        if source_id != "twitter"
    )
    assert "token_secret_123" not in json.dumps(current)


async def main() -> int:
    clock = MutableClock()
    check_stale_run_cannot_overwrite_new_run(clock)
    check_patch_collection_replaces_requested_workset(clock)
    check_source_error_codes_are_finite(clock)
    await check_contract_gateway_reports_completion_order(clock)
    await check_contract_gateway_does_not_cancel_slow_source(clock)
    with tempfile.TemporaryDirectory(prefix="kei-pk110-progress-") as temp:
        root = Path(temp)
        await check_stages_source_isolation_and_redaction(root / "stages", clock)
        await check_failure_cancellation_and_cache_reuse(root / "failures", clock)
        await check_status_http_is_read_only(root / "http", clock)
    print("daily briefing generation status tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
