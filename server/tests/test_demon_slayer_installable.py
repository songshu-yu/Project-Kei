"""Isolated lifecycle and release checks for the installable demon-slayer package."""

from __future__ import annotations

import asyncio
import hashlib
import json
import re
import subprocess
import sys
import tempfile
import zipfile
from datetime import date, datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import httpx
from fastapi import FastAPI

import _path_setup  # noqa: F401

from core.modules import InProcessModuleLoader, ModuleManager
from core.modules.exceptions import ModuleConflictError
from features.demon_slayer.package_builder import (
    BACKEND_FILES,
    FIXED_ZIP_DATETIME,
    OFFICIAL_ASSET_NAME,
    OFFICIAL_RELEASE_TAG,
    OFFICIAL_RELEASE_VERSION,
    build_demon_slayer_package,
    file_sha256,
)
from features.demon_slayer.repository import DemonSlayerPersistenceError, DemonSlayerStore
from features.demon_slayer.router import create_demon_slayer_router
from features.demon_slayer.service import DemonSlayerService


PROJECT_ROOT = Path(__file__).resolve().parents[2]
SERVER_ROOT = PROJECT_ROOT / "server"
FEATURE_ROOT = SERVER_ROOT / "features" / "demon_slayer"
RELEASE_FRAGMENT = FEATURE_ROOT / "release" / "official-release-fragment.json"
CATALOG_BUILDER = PROJECT_ROOT / "scripts" / "build_official_module_catalog.py"
EXPECTED_PACKAGE_NAMES = {
    "manifest.json",
    "dashboard/index.js",
    *(f"backend/{name}" for name in BACKEND_FILES),
}


class FakeClock:
    def __init__(self, current: date):
        self.current = current

    def set(self, value: str) -> None:
        self.current = date.fromisoformat(value)

    def today(self) -> date:
        return self.current

    def now(self) -> datetime:
        return datetime(self.current.year, self.current.month, self.current.day, 9, 30, 0)


class FakeGenerator:
    system_prompt = "isolated fake Kei"

    def __init__(self) -> None:
        self.calls: list[tuple[str, str, dict]] = []

    async def generate_text(self, system: str, user: str, **kwargs):
        self.calls.append((system, user, kwargs))
        if "语气选择器" in system:
            return SimpleNamespace(text='{"tone":"warm"}', generated=True, error_code=None)
        return SimpleNamespace(text='{"verdict":"mixed"}', generated=True, error_code=None)


async def call(app: FastAPI, method: str, path: str, **kwargs) -> httpx.Response:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        return await client.request(method, path, **kwargs)


def make_manager(root: Path) -> ModuleManager:
    return ModuleManager(
        runtime_root=root / "runtime" / "modules",
        registry_path=root / "data" / "module_registry.json",
        data_root=root / "data" / "modules",
    )


def restarted_app(
    manager: ModuleManager,
    state_path: Path,
    fake_clock: FakeClock,
    generator: FakeGenerator | None = None,
) -> tuple[FastAPI, list[dict]]:
    app = FastAPI()
    app.state.demon_slayer_state_path = state_path
    app.state.demon_slayer_clock = fake_clock.today
    app.state.demon_slayer_timestamp = fake_clock.now
    if generator is not None:
        app.state.demon_slayer_text_generator_provider = lambda: generator
    results = InProcessModuleLoader().load(app, manager.enabled_in_process_descriptors())
    manager.record_load_results(results)
    return app, results


def _assert_package_contents(package: Path) -> None:
    with zipfile.ZipFile(package) as archive:
        infos = [info for info in archive.infolist() if not info.is_dir()]
        names = sorted(info.filename for info in infos)
        assert names == sorted(EXPECTED_PACKAGE_NAMES)
        assert len(names) == len({name.casefold() for name in names})
        contents: list[str] = []
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
            contents.append(archive.read(info).decode("utf-8"))
    package_text = "\n".join(contents)
    assert "\r\n" not in package_text
    assert "features.conversation" not in package_text
    assert not re.search(r"(?i)\b[A-Z]:[\\/](?:Users|AppData|Desktop|Temp)\b", package_text)
    assert not any(
        token in name.casefold()
        for name in names
        for token in (
            ".env",
            "cache",
            "fixture",
            "history.json",
            "node_modules",
            "registry",
            "runtime",
            "script",
            "state.json",
            "test",
            "vendor",
        )
    )


def check_deterministic_package_and_release() -> None:
    fragment = json.loads(RELEASE_FRAGMENT.read_text(encoding="utf-8"))
    assert fragment["module_id"] == "demon_slayer"
    assert fragment["version"] == OFFICIAL_RELEASE_VERSION
    assert fragment["release_tag"] == OFFICIAL_RELEASE_TAG
    assert fragment["asset_name"] == OFFICIAL_ASSET_NAME
    assert fragment["dependencies"] == []
    assert fragment["optional_dependencies"] == ["conversation"]
    assert fragment["data_policy"] == "preserve_on_uninstall"

    with tempfile.TemporaryDirectory(prefix="kei-demon-package-") as temp_dir:
        root = Path(temp_dir)
        first = build_demon_slayer_package(root / "first.zip")
        second = build_demon_slayer_package(root / "second.zip")
        assert first.read_bytes() == second.read_bytes()
        assert file_sha256(first) == file_sha256(second)
        _assert_package_contents(first)
        _assert_package_contents(second)

        materialized = build_demon_slayer_package(root / "materialized")
        manifest = json.loads((materialized / "manifest.json").read_text(encoding="utf-8"))
        assert manifest["id"] == "demon_slayer"
        assert manifest["entrypoint"] == "backend.register"
        assert manifest["optional_dependencies"] == ["conversation"]
        assert manifest["dashboard_entrypoint"] == "dashboard/index.js"
        dashboard = (materialized / "dashboard" / "index.js").read_text(encoding="utf-8")
        assert "export async function mount(context)" in dashboard
        assert "export async function unmount()" in dashboard
        assert "formatGoalStatistics" in dashboard
        assert "context.request('/api/v1/demon-slayer/status')" in dashboard
        assert "localStorage" not in dashboard
        assert "fetch(" not in dashboard
        assert "/demon/" not in dashboard
        panel_module = root / "panel.mjs"
        panel_module.write_text(dashboard, encoding="utf-8")
        syntax = subprocess.run(
            ["node", "--check", str(panel_module)],
            text=True,
            capture_output=True,
            check=False,
        )
        if syntax.returncode:
            raise AssertionError(syntax.stderr or syntax.stdout)
        runner = root / "render-statistics.mjs"
        runner.write_text(
            """
import {formatGoalStatistics} from './panel.mjs';
const values = [
  formatGoalStatistics({repeat_mode:'recurring', active_since:'2030-01-01', active_days:1, current_streak:0, longest_streak:0, streak_unit:'day'}),
  formatGoalStatistics({repeat_mode:'recurring', active_since:'2030-01-01', active_days:8, current_streak:2, longest_streak:3, streak_unit:'week'}),
  formatGoalStatistics({repeat_mode:'recurring', active_since:null, active_days:null, current_streak:null, longest_streak:null, streak_unit:'month'}),
  formatGoalStatistics({repeat_mode:'recurring', active_since:'2028-01-01', active_days:1000, current_streak:1, longest_streak:4, streak_unit:'year'}),
  formatGoalStatistics({repeat_mode:'once', active_since:null, active_days:null, current_streak:0, longest_streak:0, streak_unit:'day'}),
];
process.stdout.write(JSON.stringify(values));
            """.lstrip(),
            encoding="utf-8",
        )
        rendered = subprocess.run(
            ["node", str(runner)],
            text=True,
            encoding="utf-8",
            capture_output=True,
            check=False,
        )
        if rendered.returncode:
            raise AssertionError(rendered.stderr or rendered.stdout)
        values = json.loads(rendered.stdout)
        assert "已启用 1 天 · 当前连续 0 天 · 历史最长 0 天" in values[0]
        assert "当前连续 2 周 · 历史最长 3 周" in values[1]
        assert "启用起点 未知 · 已启用 未知 · 当前连续 0 月" in values[2]
        assert "当前连续 1 年 · 历史最长 4 年" in values[3]
        assert "临时目标不累计启用天数 · 当前连续 0 天" in values[4]
        assert "undefined" not in "".join(values)
        assert "NaN" not in "".join(values)

        asset_root = root / "assets"
        asset_root.mkdir()
        asset = build_demon_slayer_package(asset_root / OFFICIAL_ASSET_NAME)
        catalog_path = root / "official-catalog.json"
        completed = subprocess.run(
            [
                sys.executable,
                str(CATALOG_BUILDER),
                "--fragment",
                str(RELEASE_FRAGMENT),
                "--asset-root",
                str(asset_root),
                "--output",
                str(catalog_path),
                "--generated-at",
                "2026-07-30T00:00:00Z",
            ],
            cwd=PROJECT_ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
        if completed.returncode:
            raise AssertionError(completed.stderr or completed.stdout)
        entry = json.loads(catalog_path.read_text(encoding="utf-8"))["modules"][0]
        assert entry["module_id"] == "demon_slayer"
        assert entry["package_size"] == asset.stat().st_size
        assert entry["package_sha256"] == file_sha256(asset)
        assert entry["optional_dependencies"] == ["conversation"]
        with zipfile.ZipFile(asset) as archive:
            manifest_raw = archive.read("manifest.json")
        assert entry["manifest_sha256"] == hashlib.sha256(manifest_raw).hexdigest()


def check_install_lifecycle_and_domain_regressions() -> None:
    with tempfile.TemporaryDirectory(prefix="kei-demon-lifecycle-") as temp_dir:
        root = Path(temp_dir)
        manager = make_manager(root)
        package_v1 = build_demon_slayer_package(root / OFFICIAL_ASSET_NAME)
        package_v2 = build_demon_slayer_package(root / "demon_slayer-1.1.0.zip", version="1.1.0")
        digest_v1 = file_sha256(package_v1)

        installed = manager.install(package_v1, digest_v1, expected_module_id="demon_slayer")
        assert installed["install_status"] == "installed_disabled"
        assert installed["enabled"] is False
        assert installed["optional_dependencies"] == ["conversation"]
        enabled = manager.enable("demon_slayer")
        assert enabled["enabled"] is True and enabled["restart_required"] is True

        fake_clock = FakeClock(date(2030, 1, 15))
        default_app = FastAPI()
        default_results = InProcessModuleLoader().load(
            default_app,
            manager.enabled_in_process_descriptors(),
        )
        assert default_results == [{"module_id": "demon_slayer", "status": "loaded"}]
        assert default_app.state.demon_slayer_service.repository.path.resolve(
            strict=False
        ) == (root / "systems" / "data" / "demon_slayer.json").resolve(strict=False)
        assert not default_app.state.demon_slayer_service.repository.path.exists()

        state_path = root / "personal-history" / "demon_slayer.json"
        app, results = restarted_app(manager, state_path, fake_clock)
        assert results == [{"module_id": "demon_slayer", "status": "loaded"}]
        expected_paths = {
            "/api/v1/demon-slayer/status",
            "/api/v1/demon-slayer/goals",
            "/api/v1/demon-slayer/goals/{goal_id}",
            "/api/v1/demon-slayer/checkins",
            "/api/v1/demon-slayer/reviews/{period}",
            "/api/v1/demon-slayer/rewards",
            "/api/v1/demon-slayer/rewards/{reward_id}/redeem",
            "/demon/status",
            "/demon/plan",
            "/demon/goals/{goal_id}",
            "/demon/checkin",
            "/demon/reminder",
            "/demon/review/daily",
            "/demon/review/weekly",
            "/demon/review/monthly",
            "/demon/review/yearly",
            "/demon/wish",
            "/demon/redeem",
            "/demon/reset",
        }
        assert expected_paths <= {route.path for route in app.routes}

        recurring = asyncio.run(call(app, "POST", "/api/v1/demon-slayer/goals", json={
            "title": "每天完成隔离练习",
            "cadence": "daily",
            "category": "auto",
            "repeat_mode": "recurring",
            "target_date": None,
        }))
        once = asyncio.run(call(app, "POST", "/api/v1/demon-slayer/goals", json={
            "title": "本周完成一次隔离报告",
            "cadence": "weekly",
            "category": "auto",
            "repeat_mode": "once",
            "target_date": "2030-01-15",
        }))
        assert recurring.status_code == 200 and once.status_code == 200
        recurring_id = recurring.json()["goal"]["id"]
        once_id = once.json()["goal"]["id"]

        first = asyncio.run(call(app, "POST", "/api/v1/demon-slayer/checkins", json={
            "goal_id": recurring_id,
            "done": True,
            "with_encouragement": True,
        }))
        assert first.status_code == 200
        assert first.json()["points_awarded"] == 10
        assert first.json()["kei_generated"] is False
        assert first.json()["encouragement"]
        duplicate = asyncio.run(call(app, "POST", "/demon/checkin", json={
            "goal_id": recurring_id,
            "done": True,
            "with_encouragement": True,
            "with_audio": False,
        }))
        assert duplicate.status_code == 200
        assert duplicate.json()["duplicate"] is True
        assert duplicate.json()["points_awarded"] == 0
        assert duplicate.json()["total_points"] == 10

        once_done = asyncio.run(call(app, "POST", "/api/v1/demon-slayer/checkins", json={
            "goal_id": once_id,
            "date": "2030-01-15",
            "done": True,
        }))
        assert once_done.status_code == 200
        assert once_done.json()["points_awarded"] == 35
        future = asyncio.run(call(app, "POST", "/api/v1/demon-slayer/checkins", json={
            "goal_id": recurring_id,
            "date": "2030-01-16",
            "done": True,
        }))
        assert future.status_code == 422

        reward = asyncio.run(call(app, "POST", "/api/v1/demon-slayer/rewards", json={
            "title": "隔离奖励",
            "cost": 10,
            "description": "temporary",
        })).json()["reward"]
        redeemed = asyncio.run(call(
            app,
            "POST",
            f"/api/v1/demon-slayer/rewards/{reward['id']}/redeem",
            json={"request_id": "isolated-reward-request"},
        )).json()
        repeated = asyncio.run(call(
            app,
            "POST",
            f"/api/v1/demon-slayer/rewards/{reward['id']}/redeem",
            json={"request_id": "isolated-reward-request"},
        )).json()
        assert redeemed["status"] == "redeemed"
        assert repeated["status"] == "already_redeemed"
        assert redeemed["points"] == repeated["points"] == 35

        review = asyncio.run(call(app, "GET", "/api/v1/demon-slayer/reviews/daily"))
        assert review.status_code == 200
        assert review.json()["kei_generated"] is False
        assert review.json()["message"]

        deleted = asyncio.run(call(
            app,
            "DELETE",
            f"/api/v1/demon-slayer/goals/{recurring_id}",
        ))
        assert deleted.status_code == 200
        status = asyncio.run(call(app, "GET", "/api/v1/demon-slayer/status")).json()
        assert all(goal["id"] != recurring_id for goal in status["goals"])
        inactive = asyncio.run(call(
            app,
            "GET",
            "/api/v1/demon-slayer/goals?include_inactive=true",
        )).json()["goals"]
        assert any(goal["id"] == recurring_id and goal["active"] is False for goal in inactive)
        stored = DemonSlayerStore(state_path).load()
        assert any(item["goal_id"] == recurring_id for item in stored["checkins"])
        assert stored["points"] == status["points"]
        assert stored["points"] >= repeated["points"]

        upgraded = manager.update("demon_slayer", package_v2, file_sha256(package_v2))
        assert upgraded["installed_version"] == "1.1.0"
        assert upgraded["enabled"] is True and upgraded["restart_required"] is True
        rolled_back = manager.rollback("demon_slayer")
        assert rolled_back["installed_version"] == OFFICIAL_RELEASE_VERSION
        assert rolled_back["enabled"] is True and rolled_back["restart_required"] is True

        running_app = app
        disabled = manager.disable("demon_slayer")
        assert disabled["install_status"] == "installed_disabled"
        assert asyncio.run(call(running_app, "GET", "/api/v1/demon-slayer/status")).status_code == 200
        stopped_app, stopped_results = restarted_app(manager, state_path, fake_clock)
        assert stopped_results == []
        assert asyncio.run(call(stopped_app, "GET", "/api/v1/demon-slayer/status")).status_code == 404

        uninstalled = manager.uninstall("demon_slayer")
        assert uninstalled["data_preserved"] is True
        assert state_path.is_file()
        manager.install(package_v1, digest_v1, expected_module_id="demon_slayer")
        manager.enable("demon_slayer")
        restored_app, restored_results = restarted_app(manager, state_path, fake_clock)
        assert restored_results == [{"module_id": "demon_slayer", "status": "loaded"}]
        restored = asyncio.run(call(
            restored_app,
            "GET",
            "/api/v1/demon-slayer/goals?include_inactive=true",
        )).json()["goals"]
        assert any(goal["id"] == recurring_id and goal["active"] is False for goal in restored)

        module_data = root / "data" / "modules" / "demon_slayer"
        module_data.mkdir(parents=True, exist_ok=True)
        (module_data / "temporary.txt").write_text("temporary", encoding="utf-8")
        try:
            manager.purge_data("demon_slayer", "DEMON_SLAYER")
        except ModuleConflictError:
            pass
        else:
            raise AssertionError("inexact purge confirmation was accepted")
        assert state_path.is_file() and module_data.is_dir()
        assert manager.purge_data("demon_slayer", "demon_slayer")["purged"] is True
        assert state_path.is_file() and not module_data.exists()


def check_optional_provider_and_read_failures() -> None:
    with tempfile.TemporaryDirectory(prefix="kei-demon-provider-") as temp_dir:
        root = Path(temp_dir)
        manager = make_manager(root)
        package = build_demon_slayer_package(root / OFFICIAL_ASSET_NAME)
        manager.install(package, file_sha256(package), expected_module_id="demon_slayer")
        manager.enable("demon_slayer")
        clock = FakeClock(date(2031, 2, 3))
        generator = FakeGenerator()
        generated_path = root / "generated.json"
        app, results = restarted_app(manager, generated_path, clock, generator)
        assert results == [{"module_id": "demon_slayer", "status": "loaded"}]
        goal = asyncio.run(call(app, "POST", "/api/v1/demon-slayer/goals", json={
            "title": "每天完成生成器隔离练习",
            "cadence": "daily",
            "category": "auto",
            "repeat_mode": "recurring",
            "target_date": None,
        })).json()["goal"]
        checked = asyncio.run(call(app, "POST", "/api/v1/demon-slayer/checkins", json={
            "goal_id": goal["id"],
            "done": True,
            "with_encouragement": True,
        })).json()
        assert checked["kei_generated"] is True
        assert len(generator.calls) == 1
        assert all("conversation history" not in repr(call_data).lower() for call_data in generator.calls)

        legacy_path = root / "legacy.json"
        legacy_path.write_text(json.dumps({
            "goals": [{
                "id": "legacy_recurring",
                "title": "旧常驻目标",
                "cadence": "daily",
                "active": True,
            }],
            "checkins": [],
            "wishes": [],
            "redemptions": [],
            "bonuses": [],
            "points": 0,
        }, ensure_ascii=False), encoding="utf-8")
        before = legacy_path.read_bytes()
        legacy_app, legacy_results = restarted_app(manager, legacy_path, clock)
        assert legacy_results == [{"module_id": "demon_slayer", "status": "loaded"}]
        first = asyncio.run(call(legacy_app, "GET", "/api/v1/demon-slayer/status?date=2031-01-01"))
        second = asyncio.run(call(legacy_app, "GET", "/demon/status?date=2031-02-03"))
        assert first.status_code == second.status_code == 200
        assert first.json()["daily_goals"][0]["active_since"] is None
        assert second.json()["daily_goals"][0]["active_since"] is None
        assert legacy_path.read_bytes() == before

        corrupt_path = root / "corrupt.json"
        corrupt_bytes = b'{"goals":['
        corrupt_path.write_bytes(corrupt_bytes)
        corrupt_app, corrupt_results = restarted_app(manager, corrupt_path, clock)
        assert corrupt_results == [{"module_id": "demon_slayer", "status": "loaded"}]
        corrupt = asyncio.run(call(corrupt_app, "GET", "/api/v1/demon-slayer/status"))
        assert corrupt.status_code == 500
        assert corrupt_path.read_bytes() == corrupt_bytes

        atomic_path = root / "atomic.json"
        atomic_app, atomic_results = restarted_app(manager, atomic_path, clock)
        assert atomic_results == [{"module_id": "demon_slayer", "status": "loaded"}]
        first_goal = asyncio.run(call(atomic_app, "POST", "/api/v1/demon-slayer/goals", json={
            "title": "原子写旧目标",
            "cadence": "daily",
            "category": "auto",
            "repeat_mode": "recurring",
            "target_date": None,
        }))
        assert first_goal.status_code == 200
        old_bytes = atomic_path.read_bytes()
        repository = atomic_app.state.demon_slayer_service.repository
        repository_module = sys.modules[repository.__class__.__module__]
        with patch.object(
            repository_module.os,
            "replace",
            side_effect=OSError("isolated replace failure"),
        ):
            failed = asyncio.run(call(atomic_app, "POST", "/api/v1/demon-slayer/goals", json={
                "title": "原子写失败目标",
                "cadence": "daily",
                "category": "auto",
                "repeat_mode": "recurring",
                "target_date": None,
            }))
        assert failed.status_code == 500
        assert atomic_path.read_bytes() == old_bytes
        assert not list(atomic_path.parent.glob(f".{atomic_path.name}.*.tmp"))


def check_duplicate_route_protection() -> None:
    with tempfile.TemporaryDirectory(prefix="kei-demon-routes-") as temp_dir:
        root = Path(temp_dir)
        manager = make_manager(root)
        package = build_demon_slayer_package(root / OFFICIAL_ASSET_NAME)
        manager.install(package, file_sha256(package), expected_module_id="demon_slayer")
        manager.enable("demon_slayer")
        clock = FakeClock(date(2032, 1, 1))
        state_path = root / "routes.json"

        app, results = restarted_app(manager, state_path, clock)
        assert results == [{"module_id": "demon_slayer", "status": "loaded"}]
        before = [(route.path, route.name, tuple(sorted(route.methods or ()))) for route in app.routes]
        repeated = InProcessModuleLoader().load(app, manager.enabled_in_process_descriptors())
        assert repeated == [{"module_id": "demon_slayer", "status": "loaded"}]
        after = [(route.path, route.name, tuple(sorted(route.methods or ()))) for route in app.routes]
        assert after == before

        source_app = FastAPI()
        source_service = DemonSlayerService(
            DemonSlayerStore(root / "source-routes.json"),
            clock=clock.today,
            timestamp=clock.now,
        )
        source_app.include_router(create_demon_slayer_router(source_service))
        source_before = len(source_app.routes)
        compatible = InProcessModuleLoader().load(
            source_app,
            manager.enabled_in_process_descriptors(),
        )
        assert compatible == [{"module_id": "demon_slayer", "status": "loaded"}]
        assert len(source_app.routes) == source_before
        assert source_app.state.demon_slayer_module_registration == "preexisting_compatible_routes"

        conflict_app = FastAPI()

        @conflict_app.get("/api/v1/demon-slayer/status", name="foreign_status")
        async def foreign_status():
            return {"foreign": True}

        conflict_before = len(conflict_app.routes)
        conflict = InProcessModuleLoader().load(
            conflict_app,
            manager.enabled_in_process_descriptors(),
        )
        assert conflict[0]["module_id"] == "demon_slayer"
        assert conflict[0]["status"] == "failed"
        assert "RuntimeError" in conflict[0]["error"]
        assert len(conflict_app.routes) == conflict_before


def main() -> int:
    check_deterministic_package_and_release()
    check_install_lifecycle_and_domain_regressions()
    check_optional_provider_and_read_failures()
    check_duplicate_route_protection()
    print("demon slayer installable module tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
