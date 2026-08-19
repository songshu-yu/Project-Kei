"""Production assembly regression for the PK-211 local engine picker."""

from __future__ import annotations

import asyncio
import os
import tempfile
from pathlib import Path

os.environ["PROJECT_KEI_ENV_FILE"] = str(
    Path(tempfile.gettempdir()) / "project-kei-pk211-no-env-file"
)

import _path_setup  # noqa: E402,F401
import httpx  # noqa: E402

import api as production_api  # noqa: E402
from features.voice.providers.gpt_sovits.acquisition import (  # noqa: E402
    LocalEngineRegistry,
)


STATUS_PATH = "/api/v1/gpt-sovits-engine/status"
SELECT_PATH = "/api/v1/gpt-sovits-engine/select-existing"
TRUSTED_ORIGIN = "http://127.0.0.1:8000"


class ForbiddenRegistry:
    def __init__(self) -> None:
        self.calls = 0

    def load(self):
        self.calls += 1
        raise AssertionError("rejected requests must not read the engine registry")

    def register(self, *_args, **_kwargs):
        self.calls += 1
        raise AssertionError("rejected requests must not write the engine registry")


def test_production_app_mounts_one_guarded_path_free_engine_picker() -> None:
    paths = [
        route.path
        for route in production_api.app.routes
        if route.path in {STATUS_PATH, SELECT_PATH}
    ]
    assert paths.count(STATUS_PATH) == 1
    assert paths.count(SELECT_PATH) == 1

    service = production_api.MODULE_HOST.gpt_sovits_engine_selection
    original_registry = service.registry
    original_picker = service.picker
    forbidden_registry = ForbiddenRegistry()
    picker_calls = []
    service.registry = forbidden_registry
    service.picker = lambda: picker_calls.append(True)

    async def rejected_requests() -> None:
        loopback = httpx.ASGITransport(
            app=production_api.app,
            client=("127.0.0.1", 4100),
        )
        async with httpx.AsyncClient(transport=loopback, base_url="http://test") as client:
            malicious_origin = await client.post(
                SELECT_PATH,
                headers={"origin": "https://evil.invalid"},
            )
            assert malicious_origin.status_code == 403
            no_origin = await client.post(SELECT_PATH)
            assert no_origin.status_code == 403
            query = await client.post(
                SELECT_PATH + "?path=forbidden",
                headers={"origin": TRUSTED_ORIGIN},
            )
            assert query.status_code == 422
            body = await client.post(
                SELECT_PATH,
                headers={"origin": TRUSTED_ORIGIN},
                json={
                    "path": "forbidden",
                    "command": "forbidden",
                    "url": "https://invalid.example",
                },
            )
            assert body.status_code == 422
            status_query = await client.get(STATUS_PATH + "?path=forbidden")
            assert status_query.status_code == 422

        remote = httpx.ASGITransport(
            app=production_api.app,
            client=("192.0.2.8", 4100),
        )
        async with httpx.AsyncClient(transport=remote, base_url="http://test") as client:
            status = await client.get(STATUS_PATH)
            select = await client.post(
                SELECT_PATH,
                headers={"origin": TRUSTED_ORIGIN},
            )
            assert status.status_code == 403
            assert select.status_code == 403

    try:
        asyncio.run(rejected_requests())
        assert forbidden_registry.calls == 0
        assert picker_calls == []

        with tempfile.TemporaryDirectory(prefix="kei-pk211-production-") as temp:
            root = Path(temp)
            registry_path = root / "state" / "engine.json"
            service.registry = LocalEngineRegistry(registry_path)
            service.picker = lambda: None

            async def accepted_requests() -> None:
                transport = httpx.ASGITransport(
                    app=production_api.app,
                    client=("127.0.0.1", 4100),
                )
                async with httpx.AsyncClient(
                    transport=transport,
                    base_url="http://test",
                ) as client:
                    core = await client.get("/")
                    assert core.status_code == 200
                    assert core.json()["status"] == "online"

                    status = await client.get(STATUS_PATH)
                    assert status.status_code == 200
                    assert status.json()["registration_state"] == "unregistered"

                    cancelled = await client.post(
                        SELECT_PATH,
                        headers={"origin": TRUSTED_ORIGIN},
                    )
                    assert cancelled.status_code == 200
                    assert cancelled.json()["action"] == "cancelled"
                    assert cancelled.json()["selection_in_progress"] is False
                    assert str(root) not in cancelled.text

            asyncio.run(accepted_requests())
            assert not registry_path.exists()
    finally:
        service.registry = original_registry
        service.picker = original_picker


def main() -> int:
    test_production_app_mounts_one_guarded_path_free_engine_picker()
    print("GPT-SoVITS production picker assembly tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
