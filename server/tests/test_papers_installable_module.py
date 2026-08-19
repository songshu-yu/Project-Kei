"""PK-133 installable papers package, provider, and lifecycle regressions."""

from __future__ import annotations

import asyncio
import json
import os
import subprocess
import tempfile
import zipfile
from datetime import date, datetime, timezone
from pathlib import Path

TEST_ROOT = Path(tempfile.gettempdir()) / "project-kei-papers-module-tests"
os.environ["PROJECT_KEI_ENV_FILE"] = str(TEST_ROOT / "missing.env")
os.environ["SEMANTIC_SCHOLAR_API_KEY"] = ""

import _path_setup  # noqa: E402,F401
import httpx  # noqa: E402
from fastapi import FastAPI  # noqa: E402

from core.intel_contracts import (  # noqa: E402
    CollectRequest,
    CollectorRegistry,
)
from core.modules import InProcessModuleLoader, ModuleManager  # noqa: E402
from core.modules.exceptions import ModuleConflictError  # noqa: E402
from features.papers import (  # noqa: E402
    PaperHttpRuntime,
    UpstreamPolicy,
    project_today_payload,
    register,
)
from features.papers.package_builder import build_papers_package  # noqa: E402


SERVER_ROOT = Path(__file__).resolve().parents[1]
FIXED_NOW = datetime(2026, 7, 30, 4, 0, tzinfo=timezone.utc)


class TrackingTransport(httpx.MockTransport):
    def __init__(self) -> None:
        self.calls = 0
        self.closes = 0

        def handler(request: httpx.Request) -> httpx.Response:
            self.calls += 1
            return httpx.Response(200, json={"ok": True}, request=request)

        super().__init__(handler)

    async def aclose(self) -> None:
        self.closes += 1
        await super().aclose()


class FixedCollector:
    source_id = "crossref"

    async def collect(self, request):
        raise AssertionError("fixed duplicate collector must not run")


class DuckRuntime:
    def __init__(self) -> None:
        self.calls = 0
        self.closes = 0
        self.closed = False
        self.limiters = {
            source_id: object()
            for source_id in ("arxiv", "crossref", "semantic")
        }

    async def get(self, *args, **kwargs):
        self.calls += 1
        raise AssertionError("registration and cached reads must not call HTTP")

    def limiter(self, source_id: str):
        return self.limiters[source_id]

    async def aclose(self) -> None:
        self.closes += 1
        self.closed = True


def manager(root: Path) -> ModuleManager:
    return ModuleManager(
        runtime_root=root / "runtime" / "modules",
        registry_path=root / "data" / "module_registry.json",
        data_root=root / "data" / "modules",
    )


def write_dependency(root: Path) -> Path:
    package = root / "intel_sources-1.0.0"
    package.mkdir(parents=True)
    manifest = {
        "schema_version": 1,
        "id": "intel_sources",
        "name": "Fake Intel Sources",
        "version": "1.0.0",
        "type": "in_process",
        "required": False,
        "core_compatibility": ">=1.0.0 <2.0.0",
        "entrypoint": "backend.register",
        "dependencies": [],
        "optional_dependencies": [],
        "conflicts": [],
        "api_namespaces": ["/api/v1/intel-sources-test"],
        "legacy_endpoints": [],
        "dashboard_entrypoint": None,
        "data_namespace": "intel_sources",
        "config_schema": None,
        "permissions": ["local_state"],
        "requires_restart": True,
    }
    (package / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False),
        encoding="utf-8",
    )
    (package / "backend.py").write_text(
        "def register(app):\n    app.state.fake_intel_sources_loaded = True\n",
        encoding="utf-8",
    )
    return package


def install(module_manager: ModuleManager, package: Path, module_id: str) -> dict:
    digest = module_manager.calculate_package_sha256(package)
    return module_manager.install(package, digest, expected_module_id=module_id)


def today_payload() -> dict:
    common = {
        "category": "papers",
        "fetched_at": "2026-07-30T04:00:00Z",
        "published_at": "2026-07-30T01:00:00Z",
        "author": "<svg onload=alert(1)>",
    }
    return {
        "ready": True,
        "date": "2026-07-30",
        "items": [
            {
                **common,
                "stable_id": "arxiv:one",
                "source_id": "arxiv",
                "title": "<img src=x onerror=alert(1)>",
                "summary": "",
                "url": "javascript:alert(1)",
            },
            {
                **common,
                "stable_id": "crossref:one",
                "source_id": "crossref",
                "title": " <img   src=x onerror=alert(1)> ",
                "summary": "<script>cached abstract</script>",
                "url": "https://doi.org/10.1000/fake",
            },
        ],
        "coverage": {
            "arxiv": {"status": "complete", "item_count": 1, "detail": ""},
            "crossref": {
                "status": "partial",
                "item_count": 1,
                "detail": "fixed warning",
            },
        },
        "warnings": ["crossref: fixed warning"],
        "script": "Kei 固定播报总结",
    }


def tree_snapshot(root: Path) -> dict[str, bytes]:
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def check_projection_and_package_sources(root: Path) -> None:
    projected = project_today_payload(today_payload())
    assert projected["ready"] is True
    assert len(projected["items"]) == 1
    assert projected["items"][0]["summary"] == "<script>cached abstract</script>"
    assert projected["items"][0]["url"] == "https://doi.org/10.1000/fake"
    assert projected["coverage"]["crossref"]["status"] == "partial"
    assert projected["script"] == "Kei 固定播报总结"
    assert project_today_payload({"ready": False})["items"] == []

    first = build_papers_package(root / "papers-a.zip")
    second = build_papers_package(root / "papers-b.zip")
    assert first.read_bytes() == second.read_bytes()
    with zipfile.ZipFile(first) as archive:
        names = set(archive.namelist())
        assert {
            "manifest.json",
            "backend/__init__.py",
            "backend/arxiv.py",
            "backend/collectors.py",
            "backend/http.py",
            "backend/module.py",
            "dashboard/index.js",
        } <= names
        manifest = json.loads(archive.read("manifest.json"))
        assert manifest["dependencies"] == ["intel_sources"]
        assert manifest["api_namespaces"] == ["/api/v1/papers"]
        release = json.loads(
            (
                SERVER_ROOT
                / "features"
                / "papers"
                / "release"
                / "official-release-fragment.json"
            ).read_text(encoding="utf-8")
        )
        assert release["asset_name"] == "papers-1.0.0.zip"
        assert release["data_policy"] == "preserve_on_uninstall"
        combined = "\n".join(
            archive.read(name).decode("utf-8")
            for name in names
            if name.endswith((".py", ".js", ".json"))
        )
        assert "features.daily_briefing" not in combined
        assert "features.intel_sources" not in combined
        assert all(
            "features.papers" not in path.read_text(encoding="utf-8")
            for path in (SERVER_ROOT / "core").rglob("*.py")
        )
        for forbidden in (
            "intel_sources.json",
            ".env",
            "briefing_cache",
            "vendor/",
        ):
            assert forbidden not in names

    panel = (
        SERVER_ROOT
        / "features"
        / "papers"
        / "package_source"
        / "dashboard"
        / "index.js"
    )
    source = panel.read_text(encoding="utf-8")
    assert "fetch(" not in source
    assert "innerHTML" not in source
    assert "textContent" in source
    assert "/api/v1/papers/today" in source
    assert "/api/v1/papers/refresh" in source
    module_copy = root / "papers-panel.mjs"
    module_copy.write_text(source, encoding="utf-8")
    completed = subprocess.run(
        ["node", "--check", str(module_copy)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    assert completed.returncode == 0, completed.stderr


def configured_app(
    runtime: PaperHttpRuntime,
    registry: CollectorRegistry,
    *,
    refreshed: list[tuple[str, ...]],
) -> FastAPI:
    app = FastAPI()
    app.state.intel_collector_registry = registry
    app.state.papers_http_runtime = runtime
    app.state.papers_http_runtime_owned_by_module = True
    app.state.papers_arxiv_cache_dir = TEST_ROOT / "never-used-real-cache"
    app.state.papers_arxiv_queries_provider = lambda: (
        {
            "label": "fake",
            "keywords": ["fake"],
            "max_results": 1,
        },
    )
    app.state.papers_journals_provider = lambda: ()
    app.state.semantic_scholar_api_key_provider = lambda: ""
    app.state.papers_clock = lambda: FIXED_NOW
    app.state.papers_today_provider = today_payload

    async def refresh(source_ids):
        refreshed.append(tuple(source_ids))
        return today_payload()

    app.state.papers_refresh_provider = refresh
    app.state.papers_local_request_guard = lambda _request: True
    return app


async def check_lifecycle_routes_and_zero_network(root: Path) -> None:
    module_manager = manager(root)
    dependency = write_dependency(root / "packages")
    install(module_manager, dependency, "intel_sources")
    module_manager.enable("intel_sources")
    package = build_papers_package(root / "papers-package", version="1.0.1")
    installed = install(module_manager, package, "papers")
    assert installed["install_status"] == "installed_disabled"
    module_manager.enable("papers")

    transport = TrackingTransport()
    runtime = PaperHttpRuntime(
        policies={
            source_id: UpstreamPolicy(min_interval=0, max_concurrency=1)
            for source_id in ("arxiv", "crossref", "semantic")
        },
        transports={
            source_id: transport
            for source_id in ("arxiv", "crossref", "semantic")
        },
        clock=lambda: FIXED_NOW,
    )
    registry = CollectorRegistry()
    refreshed: list[tuple[str, ...]] = []
    app = configured_app(runtime, registry, refreshed=refreshed)
    loader = InProcessModuleLoader()
    results = loader.load(app, module_manager.enabled_in_process_descriptors())
    assert {value["module_id"]: value["status"] for value in results} == {
        "intel_sources": "loaded",
        "papers": "loaded",
    }, results
    assert set(registry.snapshot(("arxiv", "crossref", "semantic"))) == {
        "arxiv",
        "crossref",
        "semantic",
    }
    coordinator = app.state.papers_collector_coordinator
    assert all(
        collector.runtime is runtime
        for collector in coordinator.collectors.values()
    )
    assert all(
        collector.runtime.limiter(source_id) is runtime.limiter(source_id)
        for source_id, collector in coordinator.collectors.items()
    )

    before = transport.calls
    before_files = tree_snapshot(root)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        today = await client.get("/api/v1/papers/today")
        assert today.status_code == 200
        assert len(today.json()["items"]) == 1
        assert transport.calls == before
        assert tree_snapshot(root) == before_files
        refreshed_response = await client.post("/api/v1/papers/refresh")
        assert refreshed_response.status_code == 200
    assert refreshed == [("arxiv", "crossref", "semantic")]
    assert transport.calls == before

    await runtime.get("arxiv", "https://example.invalid/fake")
    assert transport.calls == before + 1
    await app.router.shutdown()
    await app.router.shutdown()
    assert transport.closes == 1
    assert registry.snapshot(("arxiv", "crossref", "semantic")) == {}

    module_manager.disable("papers")
    data_path = root / "data" / "modules" / "papers"
    data_path.mkdir(parents=True, exist_ok=True)
    (data_path / "preserved.json").write_text("{}", encoding="utf-8")
    removed = module_manager.uninstall("papers")
    assert removed["data_preserved"] is True
    assert (data_path / "preserved.json").is_file()
    reinstalled = install(module_manager, package, "papers")
    assert reinstalled["install_status"] == "installed_disabled"


async def check_empty_state_self_owned_runtime(root: Path) -> None:
    module_manager = manager(root)
    dependency = write_dependency(root / "packages")
    install(module_manager, dependency, "intel_sources")
    module_manager.enable("intel_sources")
    package = build_papers_package(root / "papers-package")
    install(module_manager, package, "papers")
    module_manager.enable("papers")

    app = FastAPI()
    loader = InProcessModuleLoader()
    results = loader.load(app, module_manager.enabled_in_process_descriptors())
    assert {value["module_id"]: value["status"] for value in results} == {
        "intel_sources": "loaded",
        "papers": "loaded",
    }, results
    runtime = app.state.papers_http_runtime
    registry = app.state.intel_collector_registry
    coordinator = app.state.papers_collector_coordinator
    assert app.state.papers_http_runtime_owned_by_module is True
    assert all(
        collector.runtime is runtime
        for collector in coordinator.collectors.values()
    )
    assert all(
        collector.runtime.limiter(source_id) is runtime.limiter(source_id)
        for source_id, collector in coordinator.collectors.items()
    )
    assert getattr(runtime, "_clients", {}) == {}
    assert loader.load(
        app,
        module_manager.enabled_in_process_descriptors(),
    ) == [
        {"module_id": "intel_sources", "status": "already_loaded"},
        {"module_id": "papers", "status": "already_loaded"},
    ]
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.get("/api/v1/papers/today")
    assert response.status_code == 503
    assert getattr(runtime, "_clients", {}) == {}
    transport = TrackingTransport()
    runtime.transports["arxiv"] = transport
    await runtime.get("arxiv", "https://example.invalid/self-owned")
    await app.state.papers_module_close()
    await app.state.papers_module_close()
    assert runtime.closed is True
    assert transport.calls == 1
    assert transport.closes == 1
    assert registry.snapshot(("arxiv", "crossref", "semantic")) == {}


async def check_injected_duck_runtime_and_repeat_register() -> None:
    runtime = DuckRuntime()
    app = FastAPI()
    app.state.papers_http_runtime = runtime
    register(app)
    collectors = app.state.papers_collectors
    routes = tuple(route.path for route in app.routes)
    register(app)
    assert app.state.papers_collectors is collectors
    assert tuple(route.path for route in app.routes) == routes
    assert app.state.papers_http_runtime is runtime
    assert app.state.papers_http_runtime_owned_by_module is False
    assert all(collector.runtime is runtime for collector in collectors.values())
    assert all(
        collector.runtime.limiter(source_id) is runtime.limiter(source_id)
        for source_id, collector in collectors.items()
    )
    assert runtime.calls == 0
    await app.state.papers_module_close()
    assert runtime.closes == 0
    assert app.state.intel_collector_registry.snapshot(
        ("arxiv", "crossref", "semantic")
    ) == {}


async def check_atomic_duplicate_failures(root: Path) -> None:
    transport = TrackingTransport()
    runtime = PaperHttpRuntime(
        policies={
            source_id: UpstreamPolicy()
            for source_id in ("arxiv", "crossref", "semantic")
        },
        transports={
            source_id: transport
            for source_id in ("arxiv", "crossref", "semantic")
        },
    )
    registry = CollectorRegistry()
    registry.register(FixedCollector())
    app = configured_app(runtime, registry, refreshed=[])
    try:
        register(app)
        raise AssertionError("duplicate collector must fail registration")
    except ValueError:
        pass
    assert registry.get("arxiv") is None
    assert registry.get("semantic") is None
    assert registry.get("crossref").source_id == "crossref"
    assert not {
        "/api/v1/papers/today",
        "/api/v1/papers/refresh",
    } & {route.path for route in app.routes}
    assert not getattr(app.state, "papers_module_registered", False)

    duplicate_app = configured_app(runtime, CollectorRegistry(), refreshed=[])

    @duplicate_app.get("/api/v1/papers/today")
    async def duplicate_today():
        return {}

    try:
        register(duplicate_app)
        raise AssertionError("duplicate route must fail registration")
    except RuntimeError:
        pass
    assert duplicate_app.state.intel_collector_registry.snapshot(
        ("arxiv", "crossref", "semantic")
    ) == {}
    await runtime.aclose()


def check_fallback_with_core_contract() -> None:
    request = CollectRequest(
        local_date=date(2026, 7, 30),
        timezone="UTC",
        source_ids=("arxiv", "crossref", "semantic"),
        refresh=False,
        source_config_snapshot={
            "paper_priority_authors": ["Alice Example"],
            "paper_secondary_authors": [],
            "paper_ai_authors": [],
        },
    )
    assert request.contract_version == "1.0"


async def main() -> int:
    check_fallback_with_core_contract()
    with tempfile.TemporaryDirectory(prefix="kei-papers-installable-") as temp:
        root = Path(temp)
        check_projection_and_package_sources(root / "build")
        await check_empty_state_self_owned_runtime(root / "empty")
        await check_lifecycle_routes_and_zero_network(root / "lifecycle")
        await check_atomic_duplicate_failures(root / "atomic")
        await check_injected_duck_runtime_and_repeat_register()
    print("papers installable module tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
