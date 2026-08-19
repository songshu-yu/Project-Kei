"""Isolated versioned Bilibili service/router checks."""
from __future__ import annotations

import asyncio
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import httpx
from fastapi import FastAPI

import _path_setup  # noqa: F401

from features.bilibili.router import create_bilibili_router
from features.bilibili.service import BilibiliService


async def check_service_and_versioned_router() -> None:
    calls: list[int] = []

    async def profile(uid: int) -> dict:
        calls.append(uid)
        return {
            "uid": uid,
            "name": f"Profile-{uid}",
            "avatar_url": f"https://i.example.test/{uid}.jpg",
        }

    with tempfile.TemporaryDirectory(prefix="kei-pk130-router-") as temp_dir:
        service = BilibiliService(
            lambda: [11, "12", 11],
            profile_path=Path(temp_dir) / "profiles.json",
            profile_fetcher=profile,
            now=datetime(2026, 7, 22, 4, 0, tzinfo=timezone.utc),
        )
        app = FastAPI()
        app.include_router(create_bilibili_router(
            service,
            local_request_guard=lambda request: request.headers.get("x-project-kei-local") == "1",
            local_read_guard=lambda request: request.headers.get("x-project-kei-read") == "1",
        ))

        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            read_empty = await client.get(
                "/api/v1/bilibili/profiles",
                headers={"x-project-kei-read": "1"},
            )
            assert read_empty.status_code == 200
            assert read_empty.json()["profiles"] == {}
            assert calls == []

            resolved = await client.post(
                "/api/v1/bilibili/profiles/resolve",
                headers={"x-project-kei-local": "1"},
                json={"uid": 11, "refresh": False},
            )
            assert resolved.status_code == 200
            assert resolved.json()["profiles"]["11"]["name"] == "Profile-11"
            assert calls == [11]

            read_cached = await client.get(
                "/api/v1/bilibili/profiles?uid=11",
                headers={"x-project-kei-read": "1"},
            )
            assert read_cached.status_code == 200
            assert read_cached.json()["profiles"]["11"]["status"] == "ok"
            assert calls == [11]

            unknown = await client.post(
                "/api/v1/bilibili/profiles/resolve",
                headers={"x-project-kei-local": "1"},
                json={"uid": 99, "refresh": False},
            )
            assert unknown.status_code == 422
            assert calls == [11]

            forbidden = await client.post(
                "/api/v1/bilibili/profiles/resolve",
                json={"uid": 11, "refresh": True},
            )
            assert forbidden.status_code == 403
            assert calls == [11]
            forbidden_read = await client.get(
                "/api/v1/bilibili/profiles",
                headers={"x-project-kei-local": "1"},
            )
            assert forbidden_read.status_code == 403


async def main() -> None:
    await check_service_and_versioned_router()
    print("bilibili feature tests passed")


if __name__ == "__main__":
    asyncio.run(main())
