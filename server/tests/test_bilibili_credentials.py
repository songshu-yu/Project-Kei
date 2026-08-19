"""PK-130 credential/status/recollection regression tests with fake HTTP only."""
from __future__ import annotations

import asyncio
import json
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import parse_qs

import httpx
from fastapi import FastAPI

import _path_setup  # noqa: F401

from features.bilibili.client import (
    DYNAMIC_PATH,
    NAV_PATH,
    PROFILE_PATH,
    BilibiliPublicClient,
)
from features.bilibili.credentials import (
    BilibiliCredentialPersistenceError,
    BilibiliCredentialRepository,
    BilibiliCredentials,
)
from features.bilibili.router import create_bilibili_router
from features.bilibili.service import BilibiliService


NOW = datetime(2026, 7, 28, 4, 0, tzinfo=timezone.utc)
OLD_VALUES = {
    "sessdata": "fictional-old-sessdata",
    "bili_jct": "fictional-old-csrf",
    "buvid3": "fictional-old-buvid3",
}
BAD_VALUES = {
    "sessdata": "fictional-bad-sessdata",
    "bili_jct": "fictional-bad-csrf",
    "buvid3": "fictional-bad-buvid3",
}
NEW_VALUES = {
    "sessdata": "fictional-new-sessdata",
    "bili_jct": "fictional-new-csrf",
    "buvid3": "fictional-new-buvid3",
}
WBI_IMG_KEY = "a" * 32
WBI_SUB_KEY = "b" * 32


def _dynamic_payload(uid: int) -> dict:
    return {
        "code": 0,
        "data": {
            "items": [{
                "id_str": f"credential-dynamic-{uid}",
                "type": "DYNAMIC_TYPE_WORD",
                "modules": {
                    "module_author": {
                        "mid": uid,
                        "name": f"Safe UP {uid}",
                        "pub_ts": int(NOW.timestamp()),
                    },
                    "module_dynamic": {
                        "desc": {"text": "safe dynamic"},
                        "major": {},
                    },
                },
            }],
        },
    }


def _query(request: httpx.Request) -> dict[str, list[str]]:
    return parse_qs(request.url.query.decode("ascii"))


def _nav_payload() -> dict:
    return {
        "code": -101,
        "data": {
            "wbi_img": {
                "img_url": f"https://i.example.test/{WBI_IMG_KEY}.png",
                "sub_url": f"https://i.example.test/{WBI_SUB_KEY}.png",
            }
        },
    }


def _safe_handler(calls: list[str]):
    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.path)
        cookie = request.headers.get("cookie", "")
        if request.url.path == NAV_PATH:
            return httpx.Response(200, json=_nav_payload())
        if "fictional-bad-" in cookie:
            return httpx.Response(
                200,
                json={"code": -352, "message": "SESSDATA=fictional-upstream-secret"},
            )
        assert "fictional-" in cookie
        if request.url.path == PROFILE_PATH:
            uid = int(_query(request)["mid"][0])
            return httpx.Response(200, json={
                "code": 0,
                "data": {
                    "mid": uid,
                    "name": f"Safe UP {uid}",
                    "face": f"https://i.example.test/{uid}.jpg",
                },
            })
        if request.url.path == DYNAMIC_PATH:
            uid = int(_query(request)["host_mid"][0])
            return httpx.Response(200, json=_dynamic_payload(uid))
        raise AssertionError(f"unexpected fake path: {request.url.path}")

    return handler


def _repository(path: Path, **kwargs) -> BilibiliCredentialRepository:
    return BilibiliCredentialRepository(
        path,
        environment_provider=lambda: {},
        clock=lambda: NOW,
        **kwargs,
    )


def _service(
    root: Path,
    calls: list[str],
    *,
    repository: BilibiliCredentialRepository | None = None,
    request_delay: float = 0,
    uids: tuple[int, ...] = (1001,),
) -> BilibiliService:
    transport = httpx.MockTransport(_safe_handler(calls))

    async def yielding_sleep(delay: float) -> None:
        del delay
        await asyncio.sleep(0.01)

    def client_factory(credentials: BilibiliCredentials) -> BilibiliPublicClient:
        return BilibiliPublicClient(
            transport=transport,
            cookies=credentials.as_cookies(),
            request_delay=request_delay,
            retry_delay=0,
            sleep=yielding_sleep,
            wall_clock=lambda: NOW.timestamp(),
        )

    return BilibiliService(
        lambda: list(uids),
        profile_path=root / "profiles.json",
        now=NOW,
        credential_repository=repository or _repository(root / "credentials.json"),
        client_factory=client_factory,
    )


def _body_contains_secret(payload: object) -> bool:
    text = json.dumps(payload, ensure_ascii=False)
    return any(
        value in text
        for values in (OLD_VALUES, BAD_VALUES, NEW_VALUES)
        for value in values.values()
    )


async def check_status_save_and_explicit_network_boundary(root: Path) -> None:
    calls: list[str] = []
    partial = BilibiliCredentialRepository(
        root / "partial-environment.json",
        environment_provider=lambda: {
            "sessdata": "fictional-partial-only",
            "bili_jct": "",
            "buvid3": "",
        },
        clock=lambda: NOW,
    ).status()
    assert partial["state"] == "missing"
    assert [field["configured"] for field in partial["fields"]] == [True, False, False]
    assert "fictional-partial-only" not in json.dumps(partial)
    repository = _repository(root / "credentials.json")
    service = _service(root, calls, repository=repository)
    app = FastAPI()
    app.include_router(create_bilibili_router(
        service,
        local_request_guard=lambda request: request.headers.get("x-local") == "1",
    ))
    transport = httpx.ASGITransport(app=app)
    headers = {"x-local": "1"}

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        missing = await client.get("/api/v1/bilibili/credentials/status", headers=headers)
        assert missing.status_code == 200
        assert missing.json()["state"] == "missing"
        assert calls == []

        saved = await client.put(
            "/api/v1/bilibili/credentials",
            headers=headers,
            json=OLD_VALUES,
        )
        assert saved.status_code == 200
        assert saved.json()["state"] == "configured"
        assert saved.json()["source"] == "local_candidate"
        assert calls == []
        assert not _body_contains_secret(saved.json())

        legacy = await client.get(
            "/dashboard/intel-sources/bilibili-credentials/status",
            headers=headers,
        )
        assert legacy.status_code == 200
        assert legacy.json() == saved.json()
        assert calls == []

        legacy_saved = await client.put(
            "/dashboard/intel-sources/bilibili-credentials",
            headers=headers,
            json=OLD_VALUES,
        )
        assert legacy_saved.status_code == 200
        assert legacy_saved.json()["source"] == "local_candidate"
        assert calls == []

        extra = await client.put(
            "/api/v1/bilibili/credentials",
            headers=headers,
            json={**OLD_VALUES, "cookie": "arbitrary-header-forbidden"},
        )
        assert extra.status_code == 422
        assert calls == []

        collected = await client.post(
            "/api/v1/bilibili/credentials/validate-and-collect",
            headers=headers,
        )
        assert collected.status_code == 200
        payload = collected.json()
        assert payload["collection"]["status"] == "complete"
        assert payload["collection"]["item_count"] == 1
        assert payload["credential_status"]["operation_state"] == "succeeded"
        assert calls == [NAV_PATH, PROFILE_PATH, DYNAMIC_PATH]
        assert not _body_contains_secret(payload)

        legacy_collected = await client.post(
            "/dashboard/intel-sources/bilibili-credentials/validate-and-collect",
            headers=headers,
        )
        assert legacy_collected.status_code == 200
        assert legacy_collected.json()["collection"]["status"] == "complete"
        assert calls == [
            NAV_PATH, PROFILE_PATH, DYNAMIC_PATH,
            NAV_PATH, PROFILE_PATH, DYNAMIC_PATH,
        ]

        forbidden = await client.put(
            "/dashboard/intel-sources/bilibili-credentials",
            json=NEW_VALUES,
        )
        assert forbidden.status_code == 403
        assert calls == [
            NAV_PATH, PROFILE_PATH, DYNAMIC_PATH,
            NAV_PATH, PROFILE_PATH, DYNAMIC_PATH,
        ]


async def check_failure_preserves_active_and_caches(root: Path) -> None:
    calls: list[str] = []
    repository = _repository(root / "credentials.json")
    service = _service(root, calls, repository=repository)
    await service.save_credentials(OLD_VALUES)
    first = await service.validate_and_collect()
    assert first["collection"]["status"] == "complete"
    profile_path = root / "profiles.json"
    profile_before = profile_path.read_bytes()
    active_before = repository.active_credentials()
    assert active_before is not None and active_before.sessdata == OLD_VALUES["sessdata"]

    calls.clear()
    await service.save_credentials(BAD_VALUES)
    failing_service = _service(
        root,
        calls,
        repository=repository,
        uids=(1001, 1002, 1003),
    )
    try:
        await failing_service.validate_and_collect()
    except Exception as exc:
        assert type(exc).__name__ == "BilibiliCredentialValidationError"
        assert "fictional-upstream-secret" not in str(exc)
    else:
        raise AssertionError("invalid candidate should fail")
    assert calls == [NAV_PATH, PROFILE_PATH, PROFILE_PATH]
    active_after = repository.active_credentials()
    assert active_after is not None and active_after.sessdata == OLD_VALUES["sessdata"]
    assert repository.status()["candidate_state"] == "invalid"
    assert profile_path.read_bytes() == profile_before
    assert not _body_contains_secret(repository.status())
    calls_before_cooldown = list(calls)
    try:
        await service.validate_and_collect()
    except Exception as exc:
        assert type(exc).__name__ == "BilibiliCredentialValidationError"
        assert "冷却" in str(exc)
    else:
        raise AssertionError("unchanged invalid candidate should honor cooldown")
    assert calls == calls_before_cooldown

    calls.clear()
    await service.save_credentials(NEW_VALUES)
    recovered = await service.validate_and_collect()
    assert recovered["collection"]["status"] == "complete"
    active_recovered = repository.active_credentials()
    assert active_recovered is not None and active_recovered.sessdata == NEW_VALUES["sessdata"]
    assert repository.status()["candidate_state"] == "missing"
    assert calls == [NAV_PATH, PROFILE_PATH, DYNAMIC_PATH]


async def check_atomic_failures_and_concurrency(root: Path) -> None:
    path = root / "atomic-credentials.json"
    repository = _repository(path)
    repository.save_candidate(OLD_VALUES)
    before = path.read_bytes()

    def fail_replace(_source: str, _target: str) -> None:
        raise OSError("fictional replace failure")

    failing = _repository(path, replace=fail_replace)
    try:
        failing.save_candidate(NEW_VALUES)
    except BilibiliCredentialPersistenceError:
        pass
    else:
        raise AssertionError("atomic save failure should be bounded")
    assert path.read_bytes() == before
    assert not list(root.glob(".*.tmp"))

    calls: list[str] = []
    promotion_path = root / "promotion-credentials.json"
    promotion_repository = _repository(promotion_path)
    promotion_service = _service(root, calls, repository=promotion_repository)
    await promotion_service.save_credentials(OLD_VALUES)
    await promotion_service.validate_and_collect()
    profile_before = (root / "profiles.json").read_bytes()
    await promotion_service.save_credentials(NEW_VALUES)
    calls.clear()
    failing_promotion_repository = _repository(promotion_path, replace=fail_replace)
    failing_promotion_service = _service(
        root,
        calls,
        repository=failing_promotion_repository,
    )
    try:
        await failing_promotion_service.validate_and_collect()
    except BilibiliCredentialPersistenceError:
        pass
    else:
        raise AssertionError("failed candidate promotion should remain atomic")
    active_after_failure = promotion_repository.active_credentials()
    pending_after_failure, is_candidate_after_failure = (
        promotion_repository.pending_or_active()
    )
    assert active_after_failure is not None
    assert active_after_failure.sessdata == OLD_VALUES["sessdata"]
    assert is_candidate_after_failure and pending_after_failure is not None
    assert pending_after_failure.sessdata == NEW_VALUES["sessdata"]
    assert (root / "profiles.json").read_bytes() == profile_before
    assert calls == [NAV_PATH, PROFILE_PATH, DYNAMIC_PATH]
    assert not list(root.glob(".*.tmp"))

    calls.clear()
    service = _service(root, calls, repository=repository, request_delay=0.01)
    collect_task = asyncio.create_task(service.validate_and_collect())
    await asyncio.sleep(0)
    save_task = asyncio.create_task(service.save_credentials(NEW_VALUES))
    collected, saved = await asyncio.gather(collect_task, save_task)
    assert collected["collection"]["status"] == "complete"
    assert saved["candidate_state"] == "configured"
    active = repository.active_credentials()
    pending, is_candidate = repository.pending_or_active()
    assert active is not None and active.sessdata == OLD_VALUES["sessdata"]
    assert is_candidate and pending is not None and pending.sessdata == NEW_VALUES["sessdata"]
    assert calls == [NAV_PATH, PROFILE_PATH, DYNAMIC_PATH]


def check_dashboard_secret_boundary() -> None:
    server_root = Path(__file__).resolve().parents[1]
    dashboard = (
        server_root
        / "features"
        / "bilibili"
        / "package_source"
        / "dashboard"
        / "index.js"
    ).read_text(encoding="utf-8")
    shell_css = (server_root / "static" / "dashboard" / "shell.css").read_text(
        encoding="utf-8"
    )
    assert "export async function mount(context)" in dashboard
    assert "export async function unmount()" in dashboard
    assert "context.request('/api/v1/bilibili/credentials/status')" in dashboard
    assert "context.request('/api/v1/bilibili/profiles')" in dashboard
    assert "'/api/v1/bilibili/credentials'" in dashboard
    assert "'/api/v1/bilibili/credentials/validate-and-collect'" in dashboard
    assert "input.type = 'password'" in dashboard
    assert all(key in dashboard for key in ("sessdata", "bili_jct", "buvid3"))
    assert "勿粘贴整段 Header、脚本或 JSON" in dashboard
    assert "保存只写入本机候选参数，不会联网" in dashboard
    assert "只有“验证并重新采集”会访问 B 站" in dashboard
    assert "fetch(" not in dashboard
    assert "console.log" not in dashboard
    assert "localStorage" not in dashboard
    assert "sessionStorage" not in dashboard
    assert ".module-shell-card" in shell_css
    assert ".status-pill" in shell_css


async def main() -> None:
    with tempfile.TemporaryDirectory(prefix="kei-pk130-credentials-") as temp_dir:
        root = Path(temp_dir)
        first = root / "boundary"
        second = root / "recovery"
        third = root / "atomic"
        first.mkdir()
        second.mkdir()
        third.mkdir()
        await check_status_save_and_explicit_network_boundary(first)
        await check_failure_preserves_active_and_caches(second)
        await check_atomic_failures_and_concurrency(third)
        expected_names = {
            "boundary/credentials.json",
            "boundary/profiles.json",
            "recovery/credentials.json",
            "recovery/profiles.json",
            "atomic/atomic-credentials.json",
            "atomic/promotion-credentials.json",
            "atomic/profiles.json",
        }
        actual_names = {
            path.relative_to(root).as_posix()
            for path in root.rglob("*")
            if path.is_file()
        }
        assert actual_names == expected_names
    check_dashboard_secret_boundary()
    print("bilibili credential tests passed")


if __name__ == "__main__":
    asyncio.run(main())
