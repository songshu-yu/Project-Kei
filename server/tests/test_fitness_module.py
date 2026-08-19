"""Isolated PK-170 service, repository, HTTP and safety checks."""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import zipfile
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta
from pathlib import Path
from unittest.mock import patch

import httpx
from fastapi import FastAPI

import _path_setup  # noqa: F401

from core.modules import InProcessModuleLoader, ModuleManager
from core.modules.exceptions import ModuleConflictError
from features.fitness import (
    FitnessOriginGuardMiddleware,
    FitnessPersistenceError,
    FitnessRepository,
    FitnessService,
    FitnessStateError,
    create_fitness_router,
)
from features.fitness.package_builder import (
    BACKEND_FILES,
    FIXED_ZIP_DATETIME,
    OFFICIAL_ASSET_NAME,
    OFFICIAL_RELEASE_TAG,
    OFFICIAL_RELEASE_VERSION,
    build_fitness_package,
    file_sha256,
)
from features.fitness.service import choose_reward


FIXED_TODAY = date(2026, 1, 12)
FIXED_NOW = datetime(2026, 1, 12, 9, 30, 0)
PROJECT_ROOT = Path(__file__).resolve().parents[2]
SERVER_ROOT = PROJECT_ROOT / "server"
FITNESS_ROOT = SERVER_ROOT / "features" / "fitness"
DASHBOARD_ENTRYPOINT = FITNESS_ROOT / "package_source" / "dashboard" / "index.js"
RELEASE_ROOT = FITNESS_ROOT / "release"
RELEASE_FRAGMENT = RELEASE_ROOT / "official-release-fragment.json"
CATALOG_ENTRY = RELEASE_ROOT / "official-catalog-entry.json"
CATALOG_BUILDER = PROJECT_ROOT / "scripts" / "build_official_module_catalog.py"
CATALOG_GENERATED_AT = "2026-07-30T00:00:00Z"
EXPECTED_PACKAGE_NAMES = {
    "manifest.json",
    "backend/__init__.py",
    "dashboard/index.js",
    *(f"backend/{name}" for name in BACKEND_FILES),
}
FITNESS_ROUTE_PATHS = {
    "/api/v1/fitness/status",
    "/api/v1/fitness/checkins",
    "/fitness/status",
    "/fitness/checkin",
    "/fitness/reset",
}


def service_for(path: Path) -> FitnessService:
    return FitnessService(
        FitnessRepository(path),
        clock=lambda: FIXED_TODAY,
        timestamp=lambda: FIXED_NOW,
    )


def write_fixture(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def make_manager(root: Path) -> ModuleManager:
    return ModuleManager(
        runtime_root=root / "runtime" / "modules",
        registry_path=root / "data" / "module_registry.json",
        data_root=root / "data" / "modules",
    )


def restarted_app(
    manager: ModuleManager,
    state_path: Path,
    *,
    audio_synthesizer=None,
) -> tuple[FastAPI, list[dict]]:
    app = FastAPI()
    app.state.fitness_state_path = state_path
    app.state.fitness_local_control_guard = lambda _request: True
    if audio_synthesizer is not None:
        app.state.fitness_audio_synthesizer = audio_synthesizer
    results = InProcessModuleLoader().load(app, manager.enabled_in_process_descriptors())
    manager.record_load_results(results)
    return app, results


async def request(app: FastAPI, method: str, path: str, **kwargs) -> httpx.Response:
    transport = httpx.ASGITransport(app=app, client=("127.0.0.1", 43173))
    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://127.0.0.1:8000",
    ) as client:
        return await client.request(method, path, **kwargs)


def reward_tamper_cases() -> dict[str, dict]:
    valid_text = choose_reward(6)
    return {
        "invalid-date": {
            "key": "2026-13-06:0",
            "date": "2026-13-06",
            "streak": 6,
            "text": valid_text,
        },
        "non-multiple-streak": {
            "key": "2026-05-06:0",
            "date": "2026-05-06",
            "streak": 5,
            "text": valid_text,
        },
        "mismatched-key": {
            "key": "2026-05-07:0",
            "date": "2026-05-06",
            "streak": 6,
            "text": valid_text,
        },
        "tampered-text": {
            "key": "2026-05-06:0",
            "date": "2026-05-06",
            "streak": 6,
            "text": "tampered frozen reward text",
        },
    }


def check_streaks_rewards_and_legacy_dates(root: Path) -> None:
    state_path = root / "streaks.json"
    service = service_for(state_path)
    assert service.get_status()["total_checkins"] == 0
    assert not state_path.exists(), "status must not create an absent state file"

    start = date(2026, 1, 1)
    results = [
        service.check_in((start + timedelta(days=offset)).isoformat(), f"fictional note {offset}")
        for offset in range(12)
    ]
    assert results[5].reward_unlocked and results[5].streak == 6
    assert results[11].reward_unlocked and results[11].streak == 12
    duplicate = service.check_in("2026-01-12", "must not replace the first note")
    assert duplicate.already_checked_in and not duplicate.checked_in
    assert not duplicate.reward_unlocked

    status = service.get_status("2026-01-12")
    assert status["streak"] == 12 and status["total_checkins"] == 12
    assert status["next_reward_in"] == 6 and len(status["rewards"]) == 2
    fixture = json.loads(state_path.read_text(encoding="utf-8"))
    assert len(fixture["checkins"]) == 12 and len(fixture["rewards"]) == 2
    assert fixture["checkins"][-1]["note"] == "fictional note 11"

    interrupted_path = root / "interrupted.json"
    interrupted = service_for(interrupted_path)
    for day in ("2026-02-01", "2026-02-02", "2026-02-04"):
        interrupted.check_in(day)
    assert interrupted.get_status("2026-02-04")["streak"] == 1

    legacy_path = root / "legacy.json"
    write_fixture(legacy_path, {
        "checkins": [
            {"date": "2026-03-03", "note": "third"},
            {"date": "not-a-date", "note": "ignored"},
            {"date": "2026-03-01", "note": "first"},
            {"date": "2026-03-02", "note": "second"},
            {"date": "2026-03-02", "note": "duplicate"},
            {"date": None, "note": "invalid legacy date"},
        ],
        "rewards": [],
    })
    legacy = service_for(legacy_path).get_status("2026-03-03")
    assert legacy["streak"] == 3 and legacy["total_checkins"] == 3
    assert legacy["recent_checkins"] == ["2026-03-01", "2026-03-02", "2026-03-03"]


def check_concurrent_checkin(root: Path) -> None:
    state_path = root / "concurrent.json"
    service = service_for(state_path)
    for offset in range(5):
        service.check_in((date(2026, 4, 1) + timedelta(days=offset)).isoformat())

    def check_once(index: int):
        return service_for(state_path).check_in("2026-04-06", f"worker {index}")

    with ThreadPoolExecutor(max_workers=12) as executor:
        results = list(executor.map(check_once, range(24)))
    assert sum(result.checked_in for result in results) == 1
    assert sum(result.reward_unlocked for result in results) == 1
    state = FitnessRepository(state_path).load()
    assert len([item for item in state["checkins"] if item.get("date") == "2026-04-06"]) == 1
    assert len(state["rewards"]) == 1


def check_failure_safety(root: Path) -> None:
    transient_path = root / "transient-permission.json"
    transient_service = service_for(transient_path)
    transient_service.check_in("2026-04-30", "committed before retry")
    original_replace = os.replace
    replace_attempts = []

    def transient_permission_denial(source, destination):
        replace_attempts.append((Path(source), Path(destination)))
        if len(replace_attempts) < 3:
            raise PermissionError("fictional transient Windows sharing denial")
        return original_replace(source, destination)

    with patch(
        "features.fitness.repository.os.replace",
        side_effect=transient_permission_denial,
    ):
        with patch("features.fitness.repository.time.sleep") as retry_sleep:
            retried = transient_service.check_in(
                "2026-05-01",
                "committed after retry",
            )
    assert retried.checked_in is True
    assert len(replace_attempts) == 3
    assert retry_sleep.call_count == 2
    assert FitnessRepository(transient_path).load()["checkins"][-1]["note"] == (
        "committed after retry"
    )
    assert not list(root.glob(f".{transient_path.name}.*.tmp"))

    exhausted_path = root / "exhausted-permission.json"
    exhausted_service = service_for(exhausted_path)
    exhausted_service.check_in("2026-04-30", "old committed note")
    exhausted_before = exhausted_path.read_bytes()
    with patch(
        "features.fitness.repository.os.replace",
        side_effect=PermissionError("fictional persistent Windows sharing denial"),
    ) as exhausted_replace:
        with patch("features.fitness.repository.time.sleep") as exhausted_sleep:
            try:
                exhausted_service.check_in("2026-05-01", "must not persist")
            except FitnessPersistenceError:
                pass
            else:
                raise AssertionError("persistent sharing denial was not surfaced")
    assert exhausted_replace.call_count == 4
    assert exhausted_sleep.call_count == 3
    assert exhausted_path.read_bytes() == exhausted_before
    assert not list(root.glob(f".{exhausted_path.name}.*.tmp"))

    state_path = root / "atomic.json"
    service = service_for(state_path)
    service.check_in("2026-05-01", "old committed note")
    before = state_path.read_bytes()
    with patch(
        "features.fitness.repository.os.replace",
        side_effect=OSError("fictional replace failure"),
    ) as failed_replace:
        try:
            service.check_in("2026-05-02", "uncommitted note")
        except FitnessPersistenceError:
            pass
        else:
            raise AssertionError("replace failure was not surfaced")
    assert failed_replace.call_count == 1, "non-permission failures must not be retried"
    assert state_path.read_bytes() == before
    assert service.get_status("2026-05-02")["total_checkins"] == 1
    assert not list(root.glob(f".{state_path.name}.*.tmp"))

    corrupt_path = root / "corrupt.json"
    corrupt_path.write_bytes(b"{broken-json")
    corrupt_before = corrupt_path.read_bytes()
    corrupt = service_for(corrupt_path)
    for operation in (corrupt.get_status, lambda: corrupt.check_in("2026-05-03")):
        try:
            operation()
        except FitnessStateError:
            pass
        else:
            raise AssertionError("corrupt state did not fail closed")
    assert corrupt_path.read_bytes() == corrupt_before

    tampered_path = root / "tampered.json"
    write_fixture(tampered_path, {"checkins": {}, "rewards": []})
    try:
        service_for(tampered_path).get_status()
    except FitnessStateError:
        pass
    else:
        raise AssertionError("invalid root fields did not fail closed")

    for case_name, reward in reward_tamper_cases().items():
        reward_tamper_path = root / f"reward-tamper-{case_name}.json"
        write_fixture(reward_tamper_path, {"checkins": [], "rewards": [reward]})
        before = reward_tamper_path.read_bytes()
        for operation in (
            service_for(reward_tamper_path).get_status,
            lambda path=reward_tamper_path: service_for(path).check_in("2026-05-07", "must not persist"),
        ):
            try:
                operation()
            except FitnessStateError:
                pass
            else:
                raise AssertionError(f"{case_name} reward tampering did not fail closed")
        assert reward_tamper_path.read_bytes() == before
        assert not list(root.glob(f".{reward_tamper_path.name}.*.tmp"))

    duplicate_reward_path = root / "duplicate-valid-reward.json"
    valid_reward = {
        "key": "2026-05-06:0",
        "date": "2026-05-06",
        "streak": 6,
        "text": choose_reward(6),
    }
    write_fixture(duplicate_reward_path, {
        "checkins": [{"date": f"2026-05-0{day}", "note": "fictional"} for day in range(1, 7)],
        "rewards": [valid_reward, dict(valid_reward)],
    })
    duplicate_before = duplicate_reward_path.read_bytes()
    duplicate_status = service_for(duplicate_reward_path).get_status("2026-05-06")
    assert len(duplicate_status["rewards"]) == 1
    assert duplicate_reward_path.read_bytes() == duplicate_before
    accepted = service_for(duplicate_reward_path).check_in("2026-05-07", "fictional")
    assert accepted.checked_in is True and accepted.reward_unlocked is False
    assert len(FitnessRepository(duplicate_reward_path).load()["rewards"]) == 2


async def check_tampered_reward_http_writes(root: Path) -> None:
    endpoints = (
        ("versioned", "/api/v1/fitness/checkins", {"date": "2026-05-07", "note": "fictional"}),
        ("legacy", "/fitness/checkin", {"date": "2026-05-07", "note": "fictional", "with_audio": False}),
    )
    for case_name, reward in reward_tamper_cases().items():
        for endpoint_name, endpoint, payload in endpoints:
            state_path = root / f"http-reward-tamper-{case_name}-{endpoint_name}.json"
            write_fixture(state_path, {"checkins": [], "rewards": [reward]})
            before = state_path.read_bytes()
            app = FastAPI()
            app.add_middleware(FitnessOriginGuardMiddleware)
            app.include_router(create_fitness_router(service_for(state_path)))
            transport = httpx.ASGITransport(app=app, client=("127.0.0.1", 43172))
            async with httpx.AsyncClient(transport=transport, base_url="http://127.0.0.1:8000") as client:
                response = await client.post(endpoint, json=payload)
            assert response.status_code == 500
            assert response.json() == {"detail": "fitness state is invalid"}
            assert case_name not in response.text
            assert reward["text"] not in response.text
            assert str(state_path) not in response.text and "Traceback" not in response.text
            assert state_path.read_bytes() == before
            assert not list(root.glob(f".{state_path.name}.*.tmp"))


async def check_http_contract(root: Path) -> None:
    state_path = root / "http.json"
    service = service_for(state_path)
    audio_calls: list[tuple[str, str]] = []

    async def fake_audio(text: str, emotion: str) -> bytes:
        audio_calls.append((text, emotion))
        return b"fictional-audio"

    app = FastAPI()
    app.add_middleware(FitnessOriginGuardMiddleware)
    app.include_router(create_fitness_router(service, audio_synthesizer=fake_audio))
    transport = httpx.ASGITransport(app=app, client=("127.0.0.1", 43170))
    async with httpx.AsyncClient(transport=transport, base_url="http://127.0.0.1:8000") as client:
        for offset in range(5):
            service.check_in((date(2026, 6, 1) + timedelta(days=offset)).isoformat())
        before = state_path.read_bytes()
        versioned_status = await client.get("/api/v1/fitness/status", params={"date": "2026-06-05"})
        legacy_status = await client.get("/fitness/status", params={"date": "2026-06-05"})
        assert versioned_status.status_code == legacy_status.status_code == 200
        assert versioned_status.json() == legacy_status.json()
        assert state_path.read_bytes() == before, "status routes must perform zero writes"

        versioned = await client.post("/api/v1/fitness/checkins", json={"date": "2026-06-06", "note": "fictional"})
        assert versioned.status_code == 200 and versioned.json()["reward_unlocked"] is True
        assert "audio_base64" not in versioned.json()
        assert audio_calls == [], "versioned fitness must not invoke TTS"
        duplicate = await client.post(
            "/fitness/checkin",
            json={"date": "2026-06-06", "note": "duplicate", "with_audio": True},
        )
        assert duplicate.status_code == 200 and duplicate.json()["already_checked_in"] is True
        assert audio_calls == []

        service.reset()
        for offset in range(5):
            service.check_in((date(2026, 7, 1) + timedelta(days=offset)).isoformat())
        legacy_reward = await client.post(
            "/fitness/checkin",
            json={"date": "2026-07-06", "note": "fictional", "with_audio": True},
        )
        assert legacy_reward.status_code == 200 and legacy_reward.json()["audio_base64"]
        assert len(audio_calls) == 1

        invalid = await client.post("/api/v1/fitness/checkins", json={"date": "2026-02-30", "note": "x"})
        assert invalid.status_code == 422
        assert str(state_path) not in invalid.text and "Traceback" not in invalid.text
        overlong = await client.post(
            "/api/v1/fitness/checkins",
            json={"date": "2026-07-07", "note": "sensitive-fictional-note-" + ("x" * 500)},
        )
        assert overlong.status_code == 422
        assert "sensitive-fictional-note" not in overlong.text

        protected_before = state_path.read_bytes()
        forbidden = await client.get(
            "/api/v1/fitness/status",
            headers={"Origin": "https://attacker.example"},
        )
        preflight = await client.options(
            "/fitness/reset",
            headers={"Origin": "https://attacker.example", "Access-Control-Request-Method": "POST"},
        )
        assert forbidden.status_code == preflight.status_code == 403
        assert state_path.read_bytes() == protected_before

    remote_transport = httpx.ASGITransport(app=app, client=("203.0.113.9", 43170))
    async with httpx.AsyncClient(transport=remote_transport, base_url="http://project-kei.test") as remote:
        assert (await remote.get("/fitness/status")).status_code == 403

    damaged_path = root / "http-damaged.json"
    damaged_path.write_bytes(b"not-json")
    damaged_before = damaged_path.read_bytes()
    damaged_app = FastAPI()
    damaged_app.add_middleware(FitnessOriginGuardMiddleware)
    damaged_app.include_router(create_fitness_router(service_for(damaged_path)))
    damaged_transport = httpx.ASGITransport(app=damaged_app, client=("127.0.0.1", 43171))
    async with httpx.AsyncClient(transport=damaged_transport, base_url="http://127.0.0.1:8000") as client:
        response = await client.get("/api/v1/fitness/status")
        assert response.status_code == 500 and response.json()["detail"] == "fitness state is invalid"
    assert damaged_path.read_bytes() == damaged_before


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
    assert not any(
        token in name.casefold()
        for name in names
        for token in (
            ".env",
            "__pycache__",
            "fitness_checkins.json",
            "registry",
            "runtime",
            "script",
            "state",
            "test",
            "vendor",
        )
    )


def check_deterministic_installable_package(root: Path) -> None:
    package_root = root / "deterministic-package"
    first = build_fitness_package(package_root / "fitness-first.zip")
    second = build_fitness_package(package_root / "fitness-second.zip")
    assert first.read_bytes() == second.read_bytes()
    assert file_sha256(first) == file_sha256(second)
    _assert_package_contents(first)
    _assert_package_contents(second)

    materialized = build_fitness_package(package_root / "materialized")
    assert {
        path.relative_to(materialized).as_posix()
        for path in materialized.rglob("*")
        if path.is_file()
    } == EXPECTED_PACKAGE_NAMES
    for path in materialized.rglob("*"):
        if path.is_file():
            assert b"\r\n" not in path.read_bytes()

    manifest = json.loads(
        (materialized / "manifest.json").read_text(encoding="utf-8")
    )
    assert manifest["id"] == "fitness"
    assert manifest["version"] == OFFICIAL_RELEASE_VERSION
    assert manifest["entrypoint"] == "backend.register"
    assert manifest["api_namespaces"] == ["/api/v1/fitness"]
    assert manifest["legacy_endpoints"] == [
        "/fitness/status",
        "/fitness/checkin",
        "/fitness/reset",
    ]
    assert manifest["data_namespace"] == "fitness"
    assert manifest["permissions"] == ["local_state"]
    assert manifest["requires_restart"] is True


def check_official_release_metadata(root: Path) -> None:
    fragment = json.loads(RELEASE_FRAGMENT.read_text(encoding="utf-8"))
    expected_entry = json.loads(CATALOG_ENTRY.read_text(encoding="utf-8"))
    assert fragment["module_id"] == "fitness"
    assert fragment["version"] == OFFICIAL_RELEASE_VERSION
    assert fragment["release_tag"] == OFFICIAL_RELEASE_TAG
    assert fragment["asset_name"] == OFFICIAL_ASSET_NAME
    assert fragment["permissions"] == ["local_state"]
    assert fragment["data_policy"] == "preserve_on_uninstall"
    assert fragment["requires_restart"] is True

    asset_root = root / "release-assets"
    asset_root.mkdir()
    package = build_fitness_package(asset_root / OFFICIAL_ASSET_NAME)
    output = root / "generated-catalog.json"
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
    assert catalog["owner"] == "songshu-yu"
    assert catalog["repository"] == "Project-Kei-Modules"
    assert catalog["modules"] == [expected_entry]

    with zipfile.ZipFile(package) as archive:
        manifest_raw = archive.read("manifest.json")
        manifest = json.loads(manifest_raw.decode("utf-8"))
    assert manifest["id"] == fragment["module_id"]
    assert manifest["name"] == fragment["name"]
    assert manifest["version"] == fragment["version"]
    assert manifest["core_compatibility"] == fragment["core_compatibility"]
    assert expected_entry["manifest_sha256"] == hashlib.sha256(manifest_raw).hexdigest()
    assert expected_entry["package_size"] == package.stat().st_size
    assert expected_entry["package_sha256"] == file_sha256(package)
    assert expected_entry["package_url"] == (
        "https://github.com/songshu-yu/Project-Kei-Modules/releases/download/"
        f"{OFFICIAL_RELEASE_TAG}/{OFFICIAL_ASSET_NAME}"
    )
    _assert_package_contents(package)


def check_installable_lifecycle_and_safety(root: Path) -> None:
    lifecycle_root = root / "installable-lifecycle"
    manager = make_manager(lifecycle_root)
    package = build_fitness_package(lifecycle_root / OFFICIAL_ASSET_NAME)
    digest = file_sha256(package)

    installed = manager.install(package, digest, expected_module_id="fitness")
    assert installed["install_status"] == "installed_disabled"
    assert installed["enabled"] is False
    assert installed["requires_restart"] is True
    enabled = manager.enable("fitness")
    assert enabled["enabled"] is True
    assert enabled["restart_required"] is True

    audio_calls = []

    async def fake_audio(text: str, emotion: str) -> bytes:
        audio_calls.append((text, emotion))
        return b"temporary-audio"

    state_path = lifecycle_root / "protected-history" / "fitness_checkins.json"
    app, results = restarted_app(
        manager,
        state_path,
        audio_synthesizer=fake_audio,
    )
    assert results == [{"module_id": "fitness", "status": "loaded"}]
    assert app.state.fitness_module_registration_mode == "module"
    assert app.state.fitness_service.repository.path == state_path
    assert not state_path.exists()
    status = asyncio.run(request(app, "GET", "/api/v1/fitness/status"))
    assert status.status_code == 200
    assert status.json()["total_checkins"] == 0
    assert not state_path.exists(), "installable status must perform zero writes"

    for offset in range(5):
        response = asyncio.run(request(
            app,
            "POST",
            "/api/v1/fitness/checkins",
            json={
                "date": (date(2026, 8, 1) + timedelta(days=offset)).isoformat(),
                "note": f"temporary module note {offset}",
            },
        ))
        assert response.status_code == 200
    versioned_reward = asyncio.run(request(
        app,
        "POST",
        "/api/v1/fitness/checkins",
        json={"date": "2026-08-06", "note": "temporary sixth day"},
    ))
    assert versioned_reward.status_code == 200
    assert versioned_reward.json()["reward_unlocked"] is True
    assert "audio_base64" not in versioned_reward.json()
    assert audio_calls == [], "versioned installable endpoint must not invoke TTS"
    duplicate = asyncio.run(request(
        app,
        "POST",
        "/fitness/checkin",
        json={"date": "2026-08-06", "note": "duplicate", "with_audio": True},
    ))
    assert duplicate.status_code == 200
    assert duplicate.json()["already_checked_in"] is True
    assert audio_calls == []
    versioned_status = asyncio.run(request(
        app,
        "GET",
        "/api/v1/fitness/status?date=2026-08-06",
    ))
    legacy_status = asyncio.run(request(
        app,
        "GET",
        "/fitness/status?date=2026-08-06",
    ))
    assert versioned_status.json() == legacy_status.json()
    assert versioned_status.json()["streak"] == 6

    legacy_audio_path = (
        lifecycle_root / "legacy-audio-history" / "fitness_checkins.json"
    )
    legacy_audio_app, legacy_audio_results = restarted_app(
        manager,
        legacy_audio_path,
        audio_synthesizer=fake_audio,
    )
    assert legacy_audio_results == [{"module_id": "fitness", "status": "loaded"}]
    for offset in range(5):
        legacy_audio_app.state.fitness_service.check_in(
            (date(2026, 8, 11) + timedelta(days=offset)).isoformat()
        )
    legacy_reward = asyncio.run(request(
        legacy_audio_app,
        "POST",
        "/fitness/checkin",
        json={
            "date": "2026-08-16",
            "note": "temporary legacy reward",
            "with_audio": True,
        },
    ))
    assert legacy_reward.status_code == 200
    assert legacy_reward.json()["reward_unlocked"] is True
    assert legacy_reward.json()["audio_base64"]
    assert len(audio_calls) == 1
    assert audio_calls[0][1] == "happy"

    concurrent_path = lifecycle_root / "concurrent-history" / "fitness_checkins.json"
    concurrent_app, concurrent_results = restarted_app(manager, concurrent_path)
    assert concurrent_results == [{"module_id": "fitness", "status": "loaded"}]
    concurrent_service = concurrent_app.state.fitness_service
    for offset in range(5):
        concurrent_service.check_in(
            (date(2026, 9, 1) + timedelta(days=offset)).isoformat()
        )

    def concurrent_checkin(index: int):
        return concurrent_app.state.fitness_service.check_in(
            "2026-09-06",
            f"temporary worker {index}",
        )

    with ThreadPoolExecutor(max_workers=12) as executor:
        concurrent_results = list(executor.map(concurrent_checkin, range(24)))
    assert sum(result.checked_in for result in concurrent_results) == 1
    assert sum(result.reward_unlocked for result in concurrent_results) == 1
    concurrent_state = concurrent_service.repository.load()
    assert len([
        item
        for item in concurrent_state["checkins"]
        if item.get("date") == "2026-09-06"
    ]) == 1
    assert len(concurrent_state["rewards"]) == 1

    rules_path = lifecycle_root / "rules-history" / "fitness_checkins.json"
    rules_app, rules_results = restarted_app(manager, rules_path)
    assert rules_results == [{"module_id": "fitness", "status": "loaded"}]
    rules_service = rules_app.state.fitness_service
    rewards = [
        rules_service.check_in(
            (date(2026, 10, 1) + timedelta(days=offset)).isoformat()
        )
        for offset in range(12)
    ]
    assert rewards[5].reward_unlocked and rewards[5].streak == 6
    assert rewards[11].reward_unlocked and rewards[11].streak == 12
    rules_service.check_in("2026-10-14")
    assert rules_service.get_status("2026-10-14")["streak"] == 1

    atomic_path = lifecycle_root / "atomic-history" / "fitness_checkins.json"
    atomic_app, atomic_results = restarted_app(manager, atomic_path)
    assert atomic_results == [{"module_id": "fitness", "status": "loaded"}]
    atomic_service = atomic_app.state.fitness_service
    atomic_service.check_in("2026-11-01", "committed")
    old_bytes = atomic_path.read_bytes()
    repository_globals = atomic_service.repository._save_unlocked.__globals__
    with patch.object(
        repository_globals["os"],
        "replace",
        side_effect=OSError("temporary replace failure"),
    ):
        try:
            atomic_service.check_in("2026-11-02", "must not persist")
        except Exception as exc:
            assert type(exc).__name__ == "FitnessPersistenceError"
        else:
            raise AssertionError("installable atomic replace failure was not surfaced")
    assert atomic_path.read_bytes() == old_bytes
    assert atomic_service.get_status("2026-11-02")["total_checkins"] == 1
    assert not list(atomic_path.parent.glob(f".{atomic_path.name}.*.tmp"))

    corrupt_path = lifecycle_root / "corrupt-history" / "fitness_checkins.json"
    corrupt_path.parent.mkdir(parents=True)
    corrupt_path.write_bytes(b"{temporary-corruption")
    corrupt_bytes = corrupt_path.read_bytes()
    corrupt_app, corrupt_results = restarted_app(manager, corrupt_path)
    assert corrupt_results == [{"module_id": "fitness", "status": "loaded"}]
    for endpoint in ("/api/v1/fitness/status", "/fitness/status"):
        response = asyncio.run(request(corrupt_app, "GET", endpoint))
        assert response.status_code == 500
        assert response.json() == {"detail": "fitness state is invalid"}
        assert str(corrupt_path) not in response.text
    assert corrupt_path.read_bytes() == corrupt_bytes
    assert not list(corrupt_path.parent.glob(f".{corrupt_path.name}.*.tmp"))

    for case_name, reward in reward_tamper_cases().items():
        tampered_path = (
            lifecycle_root
            / "tampered-history"
            / case_name
            / "fitness_checkins.json"
        )
        write_fixture(tampered_path, {"checkins": [], "rewards": [reward]})
        tampered_bytes = tampered_path.read_bytes()
        tampered_app, tampered_results = restarted_app(manager, tampered_path)
        assert tampered_results == [{"module_id": "fitness", "status": "loaded"}]
        for endpoint, payload in (
            (
                "/api/v1/fitness/checkins",
                {"date": "2026-11-03", "note": "must not persist"},
            ),
            (
                "/fitness/checkin",
                {
                    "date": "2026-11-03",
                    "note": "must not persist",
                    "with_audio": False,
                },
            ),
        ):
            response = asyncio.run(request(
                tampered_app,
                "POST",
                endpoint,
                json=payload,
            ))
            assert response.status_code == 500
            assert response.json() == {"detail": "fitness state is invalid"}
            assert reward["text"] not in response.text
            assert str(tampered_path) not in response.text
            assert "Traceback" not in response.text
            assert tampered_path.read_bytes() == tampered_bytes
            assert not list(
                tampered_path.parent.glob(f".{tampered_path.name}.*.tmp")
            )

    disabled = manager.disable("fitness")
    assert disabled["install_status"] == "installed_disabled"
    assert disabled["restart_required"] is True
    assert asyncio.run(request(app, "GET", "/api/v1/fitness/status")).status_code == 200
    disabled_app, disabled_results = restarted_app(manager, state_path)
    assert disabled_results == []
    assert asyncio.run(
        request(disabled_app, "GET", "/api/v1/fitness/status")
    ).status_code == 404
    try:
        manager.asset_path("fitness", "dashboard/index.js")
    except ModuleConflictError:
        pass
    else:
        raise AssertionError("disabled fitness dashboard asset remained available")

    uninstall_result = manager.uninstall("fitness")
    assert uninstall_result["data_preserved"] is True
    assert state_path.is_file()
    uninstalled_app, uninstalled_results = restarted_app(manager, state_path)
    assert uninstalled_results == []
    assert asyncio.run(
        request(uninstalled_app, "GET", "/fitness/status")
    ).status_code == 404

    manager.install(package, digest, expected_module_id="fitness")
    manager.enable("fitness")
    reinstalled_app, reinstalled_results = restarted_app(manager, state_path)
    assert reinstalled_results == [{"module_id": "fitness", "status": "loaded"}]
    relinked = asyncio.run(request(
        reinstalled_app,
        "GET",
        "/api/v1/fitness/status?date=2026-08-06",
    ))
    assert relinked.status_code == 200
    assert relinked.json()["total_checkins"] == 6
    assert len(relinked.json()["rewards"]) == 1

    module_data = manager.data_root / "fitness"
    module_data.mkdir(parents=True)
    (module_data / "temporary-sentinel.txt").write_text("temporary", encoding="utf-8")
    try:
        manager.purge_data("fitness", "FITNESS")
    except ModuleConflictError:
        pass
    else:
        raise AssertionError("inexact fitness purge confirmation was accepted")
    assert module_data.is_dir()
    assert state_path.is_file()
    purged = manager.purge_data("fitness", "fitness")
    assert purged["purged"] is True
    assert not module_data.exists()
    assert state_path.is_file(), "purge removed protected fitness history"

    existing_app = FastAPI()
    existing_service = service_for(
        lifecycle_root / "existing-assembly" / "fitness_checkins.json"
    )
    existing_app.include_router(create_fitness_router(
        existing_service,
        local_control_guard=lambda _request: True,
    ))
    descriptor = manager.enabled_in_process_descriptors()
    first_load = InProcessModuleLoader().load(existing_app, descriptor)
    second_load = InProcessModuleLoader().load(existing_app, descriptor)
    assert first_load == second_load == [{"module_id": "fitness", "status": "loaded"}]
    assert existing_app.state.fitness_module_registration_mode == "existing_routes"
    for path in FITNESS_ROUTE_PATHS:
        assert sum(
            getattr(route, "path", None) == path
            for route in existing_app.routes
        ) == 1
    shared_result = asyncio.run(request(
        existing_app,
        "POST",
        "/api/v1/fitness/checkins",
        json={"date": "2026-12-01", "note": "temporary shared service"},
    ))
    assert shared_result.status_code == 200
    assert existing_service.get_status("2026-12-01")["total_checkins"] == 1

    missing_path_app = FastAPI()
    missing_path_result = InProcessModuleLoader().load(missing_path_app, descriptor)
    assert missing_path_result[0]["module_id"] == "fitness"
    assert missing_path_result[0]["status"] == "failed"
    assert "fitness state path is not configured" in missing_path_result[0]["error"]
    assert not any(
        getattr(route, "path", None) in FITNESS_ROUTE_PATHS
        for route in missing_path_app.routes
    )

    partial_app = FastAPI()

    @partial_app.get("/api/v1/fitness/status")
    async def partial_status():
        return {"temporary": True}

    partial_result = InProcessModuleLoader().load(partial_app, descriptor)
    assert partial_result[0]["module_id"] == "fitness"
    assert partial_result[0]["status"] == "failed"
    assert "fitness route assembly is incomplete" in partial_result[0]["error"]
    assert sum(
        getattr(route, "path", None) == "/api/v1/fitness/status"
        for route in partial_app.routes
    ) == 1


def _run_node(args: list[str]) -> None:
    completed = subprocess.run(
        ["node", *args],
        cwd=SERVER_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    if completed.returncode:
        raise AssertionError(completed.stderr or completed.stdout)


def check_dynamic_dashboard_entrypoint(root: Path) -> None:
    source = DASHBOARD_ENTRYPOINT.read_text(encoding="utf-8")
    assert "export async function mount(context)" in source
    assert "export async function unmount()" in source
    assert "localStorage" not in source
    assert "sessionStorage" not in source
    assert "document.querySelector" not in source
    assert "/api/v1/fitness/status" in source
    assert "/api/v1/fitness/checkins" in source
    assert "context.request('/fitness/" not in source
    assert "/api/v1/focus" not in source
    assert "/api/v1/demon" not in source
    _run_node(["--check", str(DASHBOARD_ENTRYPOINT)])

    module_path = root / "fitness-dashboard.mjs"
    module_path.write_text(source, encoding="utf-8")
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
    this.style = {{}};
    this.maxLength = 0;
  }}
  append(...items) {{ this.children.push(...items); }}
  replaceChildren(...items) {{ this.children = [...items]; }}
  addEventListener(name, handler) {{ this.listeners[name] = handler; }}
  querySelector(selector) {{
    const match = selector.match(/^\\[data-fitness-role="([^"]+)"\\]$/);
    if (!match) return null;
    const role = match[1];
    const visit = (node) => {{
      if (!node || typeof node !== 'object') return null;
      if (node.dataset?.fitnessRole === role) return node;
      for (const child of node.children || []) {{
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
let checked = false;
const mod = await import({module_path.as_uri()!r});
await mod.mount({{
  root,
  request: async (path, options = {{}}) => {{
    calls.push([path, options.method || 'GET', options.body || '']);
    if (path.endsWith('/checkins')) {{
      checked = true;
      return {{
        checked_in: true,
        already_checked_in: false,
        date: '2030-01-06',
        streak: 6,
        total_checkins: 6,
        reward_unlocked: true,
        reward_text: 'temporary reward',
        next_reward_in: 6,
      }};
    }}
    return {{
      date: '2030-01-06',
      checked_today: checked,
      streak: checked ? 6 : 5,
      total_checkins: checked ? 6 : 5,
      next_reward_in: checked ? 6 : 1,
      reward_streak_days: 6,
      recent_checkins: [],
      rewards: [],
    }};
  }},
  notify: (text, type) => notices.push([text, type]),
}});
if (root.children.length !== 4) throw new Error('fitness panel did not mount inside its root');
if (calls.length !== 1 || calls[0][0] !== '/api/v1/fitness/status' || calls[0][1] !== 'GET') {{
  throw new Error('fitness mount produced a write or escaped its status endpoint');
}}
if (root.dataset.panelSettings !== '今日备注|完成今日运动') {{
  throw new Error('fitness panel settings metadata changed');
}}
const note = root.querySelector('[data-fitness-role="note"]');
note.value = 'temporary dashboard note';
await root.querySelector('[data-fitness-role="checkin"]').listeners.click();
if (calls.length !== 3) throw new Error('fitness check-in did not refresh status exactly once');
if (calls[1][0] !== '/api/v1/fitness/checkins' || calls[1][1] !== 'POST') {{
  throw new Error('fitness check-in request contract changed');
}}
const payload = JSON.parse(calls[1][2]);
if (payload.note !== 'temporary dashboard note' || Object.keys(payload).length !== 1) {{
  throw new Error('fitness dashboard submitted unexpected fields');
}}
if (calls[2][0] !== '/api/v1/fitness/status' || calls[2][1] !== 'GET') {{
  throw new Error('fitness dashboard did not refresh via the versioned status endpoint');
}}
if (notices.length !== 1 || notices[0][0] !== 'temporary reward') {{
  throw new Error('fitness reward notice changed');
}}
if (!root.querySelector('[data-fitness-role="checkin"]').disabled) {{
  throw new Error('fitness check-in did not become idempotently disabled');
}}
if (!calls.every(([path]) => path.startsWith('/api/v1/fitness/'))) {{
  throw new Error('fitness panel escaped its API namespace');
}}
await mod.unmount();
if (root.children.length !== 0 || 'panelSettings' in root.dataset) {{
  throw new Error('fitness panel did not unmount cleanly');
}}
"""
    _run_node(["--input-type=module", "-e", probe])


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="kei-fitness-module-") as temp_dir:
        root = Path(temp_dir)
        check_streaks_rewards_and_legacy_dates(root)
        check_concurrent_checkin(root)
        check_failure_safety(root)
        asyncio.run(check_tampered_reward_http_writes(root))
        asyncio.run(check_http_contract(root))
        check_deterministic_installable_package(root)
        check_official_release_metadata(root)
        check_installable_lifecycle_and_safety(root)
        check_dynamic_dashboard_entrypoint(root)
    print("fitness module tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
