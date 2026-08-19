"""End-to-end, isolated checks for the installable calendar module."""

from __future__ import annotations

import asyncio
import hashlib
import json
import math
import re
import subprocess
import sys
import tempfile
import zipfile
from datetime import date, datetime
from pathlib import Path

import httpx
from fastapi import FastAPI

import _path_setup  # noqa: F401

from core.modules import InProcessModuleLoader, ModuleManager
from core.modules.exceptions import ModuleConflictError
from features.calendar import repository as repository_module
from features.calendar.module import CALENDAR_ROUTE_PATHS, register, unregister
from features.calendar.package_builder import (
    BACKEND_FILES,
    FIXED_ZIP_DATETIME,
    OFFICIAL_ASSET_NAME,
    OFFICIAL_RELEASE_TAG,
    OFFICIAL_RELEASE_VERSION,
    build_calendar_package,
    file_sha256,
)
from features.calendar.repository import (
    CalendarMemoStore,
    CalendarPersistenceError,
)
from features.calendar.router import create_calendar_router
from features.calendar.service import CalendarService


PROJECT_ROOT = Path(__file__).resolve().parents[2]
CALENDAR_ROOT = PROJECT_ROOT / "server" / "features" / "calendar"
RELEASE_ROOT = CALENDAR_ROOT / "release"
RELEASE_FRAGMENT = RELEASE_ROOT / "official-release-fragment.json"
CATALOG_ENTRY = RELEASE_ROOT / "official-catalog-entry.json"
CATALOG_BUILDER = PROJECT_ROOT / "scripts" / "build_official_module_catalog.py"
CATALOG_GENERATED_AT = "2026-07-30T00:00:00Z"
EXPECTED_PACKAGE_NAMES = {
    "manifest.json",
    "dashboard/index.js",
    *(f"backend/{name}" for name in BACKEND_FILES),
}


class IsolatedVoiceCalendarRegistry:
    """Test double for the public registry contract owned by PK-210."""

    def __init__(self) -> None:
        self.provider = None
        self.registered = []
        self.unregistered = []

    def register_calendar_summary_provider(self, provider) -> None:
        self.provider = provider
        self.registered.append(provider)

    def unregister_calendar_summary_provider(self, provider) -> None:
        assert provider is self.provider
        self.unregistered.append(provider)
        self.provider = None

    def summary(self) -> dict:
        if self.provider is None:
            return {
                "available": False,
                "module_id": "calendar",
                "message": "",
                "today_events": [],
                "upcoming_events": [],
                "skills": [],
            }
        return {"available": True, **self.provider()}


async def call(app: FastAPI, method: str, path: str, **kwargs) -> httpx.Response:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        return await client.request(method, path, **kwargs)


def service_for(path: Path, *, today: date = date(2026, 7, 21)) -> CalendarService:
    return CalendarService(
        CalendarMemoStore(path),
        clock=lambda: today,
        timestamp=lambda: datetime(2026, 7, 21, 9, 0, 0),
    )


def make_manager(root: Path) -> ModuleManager:
    return ModuleManager(
        runtime_root=root / "runtime" / "modules",
        registry_path=root / "data" / "module_registry.json",
        data_root=root / "data" / "modules",
    )


def restarted_app(
    manager: ModuleManager,
    state_path: Path,
) -> tuple[FastAPI, list[dict], IsolatedVoiceCalendarRegistry]:
    app = FastAPI()
    registry = IsolatedVoiceCalendarRegistry()
    app.state.calendar_state_path = state_path
    app.state.voice_calendar_provider_registry = registry
    results = InProcessModuleLoader().load(app, manager.enabled_in_process_descriptors())
    manager.record_load_results(results)
    return app, results, registry


def expect_error(error_type: type[BaseException], operation) -> None:
    try:
        operation()
    except error_type:
        return
    raise AssertionError(f"expected {error_type.__name__}")


def check_calendar_rules_and_atomic_write() -> None:
    with tempfile.TemporaryDirectory(prefix="kei-calendar-rules-") as temp_dir:
        root = Path(temp_dir)
        state_path = root / "isolated-calendar-state.json"
        service = service_for(state_path, today=date(2026, 12, 30))

        first = service.add_event(
            "跨年准备",
            "2026-12-31",
            note="保留备注",
            tags=["年度", "复盘"],
        )
        duplicate = service.add_event(
            "跨年准备",
            "2026-12-31",
            note="重复事件不得覆盖原备注",
            tags=["不同标签"],
        )
        assert duplicate["id"] == first["id"]
        assert len(service.repository.load()["events"]) == 1
        assert service.repository.load()["events"][0]["note"] == "保留备注"
        assert service.repository.load()["events"][0]["tags"] == ["年度", "复盘"]

        service.add_event("跨年事件", "2027-01-02")
        service.add_event("年度事件", "2000-12-31", repeat="yearly")
        upcoming = service.upcoming_events("2026-12-30", days=7)
        assert [(item["title"], item["occurrence_date"], item["days_left"]) for item in upcoming] == [
            ("年度事件", "2026-12-31", 1),
            ("跨年准备", "2026-12-31", 1),
            ("跨年事件", "2027-01-02", 3),
        ]

        service.add_event("闰日事件", "2020-02-29", repeat="yearly")
        assert service.events_for_day("2024-02-29")
        assert not service.events_for_day("2025-02-28")
        leap = next(
            item for item in service.upcoming_events("2025-01-01", days=1200)
            if item["title"] == "闰日事件"
        )
        assert leap["occurrence_date"] == "2028-02-29"

        first_log = service.add_practice("写作", 0.25, day="2026-12-30", note="热身")
        second_log = service.add_practice("写作", 1.5, day="2026-12-31")
        assert first_log["skill"]["total_hours"] == 0.25
        assert second_log["skill"]["total_hours"] == 1.75
        assert len(service.repository.load()["practice_logs"]) == 2
        for invalid in (0, -1, math.nan, math.inf, -math.inf):
            expect_error(
                ValueError,
                lambda value=invalid: service.add_practice("写作", value),
            )

        original = state_path.read_bytes()
        original_replace = repository_module.os.replace

        def fail_replace(_source, _target):
            raise OSError("isolated replace failure")

        repository_module.os.replace = fail_replace
        try:
            expect_error(
                CalendarPersistenceError,
                lambda: service.add_event("不得写入", "2027-01-03"),
            )
        finally:
            repository_module.os.replace = original_replace
        assert state_path.read_bytes() == original
        assert not list(state_path.parent.glob(f".{state_path.name}.*.tmp"))


async def api_scenario(prefix: str, state_path: Path) -> list[tuple[int, dict]]:
    app = FastAPI()
    app.include_router(create_calendar_router(service_for(state_path)))
    event_path = "events" if prefix.startswith("/api/v1") else "event"
    requests = [
        ("GET", f"{prefix}/today?date=2026-07-21", {}),
        ("POST", f"{prefix}/{event_path}", {"json": {
            "title": "API 样例",
            "date": "2026-07-21",
            "repeat": "yearly",
            "note": "保留备注",
            "tags": ["样例"],
        }}),
        ("POST", f"{prefix}/practice", {"json": {
            "skill": "API 技能",
            "hours": 1.25,
            "date": "2026-07-21",
            "note": "样例",
        }}),
        ("GET", f"{prefix}/status?date=2026-07-21", {}),
    ]
    responses = []
    for method, path, kwargs in requests:
        response = await call(app, method, path, **kwargs)
        responses.append((response.status_code, response.json()))
    return responses


def check_api_equivalence_and_reset_boundary() -> None:
    with tempfile.TemporaryDirectory(prefix="kei-calendar-api-") as temp_dir:
        root = Path(temp_dir)
        versioned = asyncio.run(api_scenario(
            "/api/v1/calendar",
            root / "versioned-isolated-state.json",
        ))
        legacy = asyncio.run(api_scenario(
            "/calendar",
            root / "legacy-isolated-state.json",
        ))
        assert versioned == legacy
        assert versioned[1][1]["event"]["tags"] == ["样例"]
        assert versioned[3][1]["recent_practice_logs"][0]["note"] == "样例"

        state_path = root / "reset-isolated-state.json"
        app = FastAPI()
        app.include_router(create_calendar_router(service_for(state_path)))
        asyncio.run(call(app, "POST", "/api/v1/calendar/events", json={
            "title": "保留到精确确认",
            "date": "2026-07-21",
            "repeat": "none",
            "note": "",
            "tags": [],
        }))
        rejected = asyncio.run(call(
            app,
            "POST",
            "/api/v1/calendar/reset",
            json={"confirmation": "Calendar"},
        ))
        assert rejected.status_code == 422
        assert len(CalendarMemoStore(state_path).load()["events"]) == 1
        accepted = asyncio.run(call(
            app,
            "POST",
            "/api/v1/calendar/reset",
            json={"confirmation": "calendar"},
        ))
        assert accepted.status_code == 200
        assert accepted.json()["cleared"]["events"] == 1

        # Compatibility risk is intentional and documented: legacy reset remains
        # confirmation-free, but the dynamic module panel must never expose it.
        asyncio.run(call(app, "POST", "/calendar/event", json={
            "title": "legacy 风险记录",
            "date": "2026-07-21",
            "repeat": "none",
            "note": "",
            "tags": [],
        }))
        legacy_reset = asyncio.run(call(app, "POST", "/calendar/reset"))
        assert legacy_reset.status_code == 200
        assert legacy_reset.json()["cleared"]["events"] == 1


def check_provider_registration_and_duplicate_routes() -> None:
    with tempfile.TemporaryDirectory(prefix="kei-calendar-provider-") as temp_dir:
        app = FastAPI()
        registry = IsolatedVoiceCalendarRegistry()
        state_path = Path(temp_dir) / "provider-isolated-state.json"
        app.state.calendar_state_path = state_path
        app.state.voice_calendar_provider_registry = registry
        register(app)

        assert len(registry.registered) == 1
        assert registry.provider is app.state.calendar_summary_provider
        assert registry.summary()["available"] is True
        assert registry.summary()["date"] == date.today().isoformat()
        route_paths = [route.path for route in app.routes]
        assert CALENDAR_ROUTE_PATHS <= set(route_paths)
        counts_before = {path: route_paths.count(path) for path in CALENDAR_ROUTE_PATHS}
        assert set(counts_before.values()) == {1}

        register(app)
        route_paths_after = [route.path for route in app.routes]
        assert {path: route_paths_after.count(path) for path in CALENDAR_ROUTE_PATHS} == counts_before
        assert len(registry.registered) == 1

        unregister(app)
        assert registry.provider is None
        assert len(registry.unregistered) == 1
        empty = registry.summary()
        assert empty["available"] is False
        assert empty["message"] == ""
        assert empty["today_events"] == []
        assert not hasattr(app.state, "calendar_summary_provider")

        conflicting = FastAPI()
        conflicting.get("/api/v1/calendar/status")(lambda: {"status": "occupied"})
        before = len(conflicting.routes)
        expect_error(RuntimeError, lambda: register(conflicting))
        assert len(conflicting.routes) == before
        assert not hasattr(conflicting.state, "calendar_module_registered")


def _assert_package_contents(package: Path) -> None:
    with zipfile.ZipFile(package) as archive:
        infos = [info for info in archive.infolist() if not info.is_dir()]
        names = sorted(info.filename for info in infos)
        assert names == sorted(EXPECTED_PACKAGE_NAMES)
        assert len(names) == len(set(name.casefold() for name in names))
        combined = []
        for info in infos:
            assert not info.filename.startswith(("/", "\\"))
            assert "\\" not in info.filename
            assert ".." not in Path(info.filename).parts
            assert ":" not in info.filename.split("/", 1)[0]
            assert info.date_time == FIXED_ZIP_DATETIME
            assert info.compress_type == zipfile.ZIP_STORED
            assert info.create_system == 3
            assert info.create_version == 20
            assert info.extract_version == 20
            assert info.internal_attr == 0
            assert info.external_attr == 0o100644 << 16
            assert info.extra == b""
            assert info.comment == b""
            combined.append(archive.read(info).decode("utf-8"))
    package_text = "\n".join(combined)
    assert "\r\n" not in package_text
    assert not re.search(r"(?i)\b[A-Z]:[\\/](?:Users|AppData|Desktop|Temp)\b", package_text)
    assert not any(name.casefold().endswith("calendar_memo.json") for name in names)
    assert not any(
        token in name.casefold()
        for name in names
        for token in (
            ".env",
            "state",
            "registry",
            "runtime",
            "cache",
            "test",
            "fixture",
            "vendor",
            "script",
        )
    )


def check_deterministic_package_and_panel_boundary() -> None:
    dashboard = (
        CALENDAR_ROOT / "package_source" / "dashboard" / "index.js"
    ).read_text(encoding="utf-8")
    assert "export async function mount(context)" in dashboard
    assert "export async function unmount()" in dashboard
    assert "/api/v1/calendar/status" in dashboard
    assert "/api/v1/calendar/events" in dashboard
    assert "/api/v1/calendar/practice" in dashboard
    assert "/api/v1/calendar/reset" not in dashboard
    assert "context.request('/calendar/" not in dashboard

    with tempfile.TemporaryDirectory(prefix="kei-calendar-deterministic-") as temp_dir:
        root = Path(temp_dir)
        first = build_calendar_package(root / "calendar-first.zip")
        second = build_calendar_package(root / "calendar-second.zip")
        assert first.read_bytes() == second.read_bytes()
        assert file_sha256(first) == file_sha256(second)
        _assert_package_contents(first)
        _assert_package_contents(second)

        materialized = build_calendar_package(root / "materialized")
        for path in materialized.rglob("*"):
            if path.is_file():
                assert b"\r\n" not in path.read_bytes()


def check_lifecycle_uninstall_and_reinstall() -> None:
    with tempfile.TemporaryDirectory(prefix="kei-calendar-lifecycle-") as temp_dir:
        root = Path(temp_dir)
        manager = make_manager(root)
        package = build_calendar_package(root / OFFICIAL_ASSET_NAME)
        digest = file_sha256(package)
        installed = manager.install(package, digest, expected_module_id="calendar")
        assert installed["install_status"] == "installed_disabled"
        assert installed["enabled"] is False
        assert installed["requires_restart"] is True
        manager.enable("calendar")

        state_path = root / "user-state" / "isolated-calendar-state.json"
        app, results, registry = restarted_app(manager, state_path)
        assert results == [{"module_id": "calendar", "status": "loaded"}]
        assert registry.provider is not None
        assert CALENDAR_ROUTE_PATHS <= {route.path for route in app.routes}

        event = asyncio.run(call(app, "POST", "/api/v1/calendar/events", json={
            "title": "重装后保留",
            "date": "2026-07-21",
            "repeat": "yearly",
            "note": "事件备注",
            "tags": ["保留标签"],
        }))
        practice = asyncio.run(call(app, "POST", "/calendar/practice", json={
            "skill": "可安装化",
            "hours": 2.5,
            "date": "2026-07-21",
            "note": "练习备注",
        }))
        assert event.status_code == 200
        assert practice.status_code == 200
        preserved_bytes = state_path.read_bytes()

        manager.disable("calendar")
        disabled_app, disabled_results, disabled_registry = restarted_app(manager, state_path)
        assert disabled_results == []
        assert disabled_registry.summary()["available"] is False
        assert asyncio.run(call(
            disabled_app,
            "GET",
            "/api/v1/calendar/status",
        )).status_code == 404
        assert state_path.read_bytes() == preserved_bytes

        manager.enable("calendar")
        manager.disable("calendar")
        uninstall_result = manager.uninstall("calendar")
        assert uninstall_result["data_preserved"] is True
        assert state_path.read_bytes() == preserved_bytes
        uninstalled_app, uninstalled_results, uninstalled_registry = restarted_app(
            manager,
            state_path,
        )
        assert uninstalled_results == []
        assert uninstalled_registry.summary()["available"] is False

        manager.install(package, digest, expected_module_id="calendar")
        manager.enable("calendar")
        restored_app, restored_results, restored_registry = restarted_app(manager, state_path)
        assert restored_results == [{"module_id": "calendar", "status": "loaded"}]
        restored = asyncio.run(call(
            restored_app,
            "GET",
            "/api/v1/calendar/status?date=2026-07-21",
        ))
        assert restored.status_code == 200
        assert restored.json()["events"][0]["tags"] == ["保留标签"]
        assert restored.json()["recent_practice_logs"][0]["note"] == "练习备注"
        assert restored_registry.summary()["available"] is True

        module_data = root / "data" / "modules" / "calendar"
        module_data.mkdir(parents=True, exist_ok=True)
        (module_data / "isolated-sentinel.txt").write_text("temporary", encoding="utf-8")
        expect_error(
            ModuleConflictError,
            lambda: manager.purge_data("calendar", "Calendar"),
        )
        assert module_data.is_dir()
        assert state_path.read_bytes() == preserved_bytes
        purged = manager.purge_data("calendar", "calendar")
        assert purged["purged"] is True
        assert not module_data.exists()
        # ModuleManager purge owns only its namespace and must never reach the
        # historical calendar state location configured for this installation.
        assert state_path.read_bytes() == preserved_bytes


def check_official_release_metadata() -> None:
    fragment = json.loads(RELEASE_FRAGMENT.read_text(encoding="utf-8"))
    expected_entry = json.loads(CATALOG_ENTRY.read_text(encoding="utf-8"))
    assert fragment["module_id"] == "calendar"
    assert fragment["version"] == OFFICIAL_RELEASE_VERSION
    assert fragment["release_tag"] == OFFICIAL_RELEASE_TAG
    assert fragment["asset_name"] == OFFICIAL_ASSET_NAME
    assert fragment["dependencies"] == []
    assert fragment["optional_dependencies"] == []
    assert fragment["permissions"] == ["local_state"]
    assert fragment["data_policy"] == "preserve_on_uninstall"
    assert fragment["requires_restart"] is True

    with tempfile.TemporaryDirectory(prefix="kei-calendar-official-release-") as temp_dir:
        root = Path(temp_dir)
        asset_root = root / "assets"
        asset_root.mkdir()
        package = build_calendar_package(asset_root / OFFICIAL_ASSET_NAME)
        output = root / "official-catalog.json"
        completed = subprocess.run(
            [
                sys.executable,
                str(CATALOG_BUILDER),
                "--fragment",
                str(RELEASE_FRAGMENT),
                "--asset-root",
                str(asset_root),
                "--output",
                str(output),
                "--generated-at",
                CATALOG_GENERATED_AT,
            ],
            cwd=PROJECT_ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
        if completed.returncode:
            raise AssertionError(completed.stderr or completed.stdout)
        catalog = json.loads(output.read_text(encoding="utf-8"))
        assert catalog["modules"] == [expected_entry]

        with zipfile.ZipFile(package) as archive:
            manifest_raw = archive.read("manifest.json")
            manifest = json.loads(manifest_raw.decode("utf-8"))
        assert manifest["id"] == fragment["module_id"]
        assert manifest["name"] == fragment["name"]
        assert manifest["version"] == fragment["version"]
        assert expected_entry["manifest_sha256"] == hashlib.sha256(manifest_raw).hexdigest()
        assert expected_entry["package_size"] == package.stat().st_size
        assert expected_entry["package_sha256"] == file_sha256(package)
        assert expected_entry["package_url"].endswith(
            f"/{OFFICIAL_RELEASE_TAG}/{OFFICIAL_ASSET_NAME}"
        )
        _assert_package_contents(package)


def main() -> int:
    check_calendar_rules_and_atomic_write()
    check_api_equivalence_and_reset_boundary()
    check_provider_registration_and_duplicate_routes()
    check_deterministic_package_and_panel_boundary()
    check_lifecycle_uninstall_and_reinstall()
    check_official_release_metadata()
    print("calendar installable module tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
