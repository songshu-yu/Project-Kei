"""Isolated module/API/persistence checks for PK-150."""

from __future__ import annotations

import asyncio
import json
import tempfile
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime
from pathlib import Path
from unittest.mock import patch

import httpx
from fastapi import FastAPI

import _path_setup  # noqa: F401

from features.conversation.models import TextGenerationResult
from features.demon_slayer.repository import (
    DemonSlayerPersistenceError,
    DemonSlayerStateError,
    DemonSlayerStore,
)
from features.demon_slayer.router import create_demon_slayer_router
from features.demon_slayer.service import DemonSlayerService


TODAY = date(2026, 7, 22)


class FakeKei:
    system_prompt = "fake Kei"

    def __init__(self) -> None:
        self.calls = []

    async def generate_text(self, system: str, user: str, **kwargs) -> TextGenerationResult:
        self.calls.append((system, user, kwargs))
        return TextGenerationResult(text='{"verdict":"mixed"}', generated=True, fallback=False, model="fake")


def make_service(path: Path, fake: FakeKei | None = None) -> DemonSlayerService:
    return DemonSlayerService(
        DemonSlayerStore(path),
        text_generator_provider=lambda: fake,
        clock=lambda: TODAY,
        timestamp=lambda: datetime(2026, 7, 22, 9, 30, 0),
    )


async def call(app: FastAPI, method: str, path: str, **kwargs) -> httpx.Response:
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        return await client.request(method, path, **kwargs)


async def check_api(path: Path) -> None:
    fake = FakeKei()
    service = make_service(path, fake)
    app = FastAPI()
    app.include_router(create_demon_slayer_router(service))

    created = await call(app, "POST", "/api/v1/demon-slayer/goals", json={
        "title": "每月完成论文阶段报告",
        "cadence": "auto",
        "category": "auto",
        "repeat_mode": "recurring",
    })
    assert created.status_code == 200
    goal = created.json()["goal"]
    assert goal["cadence"] == "monthly" and goal["rank"] == "大大妖"

    legacy_status = await call(app, "GET", "/demon/status?date=2026-07-22")
    assert legacy_status.status_code == 200
    assert legacy_status.json()["monthly_goals"][0]["id"] == goal["id"]

    edited = await call(app, "PATCH", f"/api/v1/demon-slayer/goals/{goal['id']}", json={
        "title": "每周完成论文阶段报告",
        "cadence": "weekly",
        "category": "study",
    })
    assert edited.status_code == 200
    assert edited.json()["goal"]["id"] == goal["id"]
    assert edited.json()["goal"]["rank"] == "大妖"

    first = await call(app, "POST", "/api/v1/demon-slayer/checkins", json={"goal_id": goal["id"], "note": "真实完成"})
    duplicate = await call(app, "POST", "/demon/checkin", json={"goal_id": goal["id"], "note": "真实完成", "with_audio": False})
    assert first.json()["points_awarded"] == 35
    assert duplicate.json()["duplicate"] is True
    assert duplicate.json()["points_awarded"] == 0
    assert duplicate.json()["total_points"] == 35

    edited_after_completion = await call(app, "PATCH", f"/api/v1/demon-slayer/goals/{goal['id']}", json={"cadence": "monthly"})
    assert edited_after_completion.status_code == 200
    after_edit_retry = await call(app, "POST", "/api/v1/demon-slayer/checkins", json={"goal_id": goal["id"], "note": "真实完成"})
    assert after_edit_retry.json()["points_awarded"] == 0
    assert after_edit_retry.json()["total_points"] == 35

    daily = await call(app, "POST", "/api/v1/demon-slayer/goals", json={
        "title": "每天整理资料",
        "cadence": "daily",
        "category": "life",
    })
    daily_goal = daily.json()["goal"]
    review = await call(app, "GET", "/api/v1/demon-slayer/reviews/weekly?anchor=2026-07-22")
    payload = review.json()
    assert payload["kei_generated"] is True
    assert payload["completed"] == 1 and payload["total"] == 2
    assert daily_goal["title"] in payload["missed"]
    assert "实际完成 1/2" in payload["message"]
    assert fake.calls and "只能依据" in fake.calls[0][0]

    future = await call(app, "POST", "/api/v1/demon-slayer/checkins", json={"goal_id": daily_goal["id"], "date": "2026-07-23"})
    assert future.status_code == 422

    reward = await call(app, "POST", "/api/v1/demon-slayer/rewards", json={"title": "测试奖励", "cost": 20})
    reward_id = reward.json()["reward"]["id"]
    redeemed = await call(app, "POST", f"/api/v1/demon-slayer/rewards/{reward_id}/redeem", json={})
    repeated = await call(app, "POST", f"/api/v1/demon-slayer/rewards/{reward_id}/redeem", json={})
    assert redeemed.json()["status"] == "redeemed" and redeemed.json()["points"] == 15
    assert repeated.json()["status"] == "already_redeemed" and repeated.json()["points"] == 15

    deleted = await call(app, "DELETE", f"/demon/goals/{goal['id']}")
    deleted_again = await call(app, "DELETE", f"/api/v1/demon-slayer/goals/{goal['id']}")
    assert deleted.json()["status"] == "ok"
    assert deleted_again.json()["status"] == "already_inactive"
    state = DemonSlayerStore(path).load()
    assert any(item["goal_id"] == goal["id"] for item in state["checkins"])
    assert state["points"] == 15


def check_legacy_schema(path: Path) -> None:
    path.write_text(json.dumps({
        "goals": [{"title": "每天读书", "cadence": "daily", "created_at": "2026-07-20T08:00:00"}],
        "checkins": [],
        "points": 0,
    }, ensure_ascii=False), encoding="utf-8")
    status = make_service(path).get_status("2026-07-22")
    goal = status["goals"][0]
    assert goal["repeat_mode"] == "recurring"
    assert goal["rank"] == "小妖" and goal["id"].startswith("goal_")


def check_corrupt_and_atomic_failure(root: Path) -> None:
    corrupt = root / "corrupt.json"
    corrupt.write_text("{broken", encoding="utf-8")
    try:
        make_service(corrupt).get_status()
    except DemonSlayerStateError:
        pass
    else:
        raise AssertionError("corrupt state must fail closed")
    assert corrupt.read_text(encoding="utf-8") == "{broken"

    state_path = root / "atomic.json"
    service = make_service(state_path)
    service.add_goal("每天写测试", cadence="daily")
    before = state_path.read_bytes()
    with patch("features.demon_slayer.repository.os.replace", side_effect=OSError("replace failed")):
        try:
            service.add_goal("每天写文档", cadence="daily")
        except DemonSlayerPersistenceError:
            pass
        else:
            raise AssertionError("replace failure must be surfaced")
    assert state_path.read_bytes() == before
    assert not list(root.glob(f".{state_path.name}.*.tmp"))


def check_concurrent_duplicate(path: Path) -> None:
    service = make_service(path)
    goal = service.add_goal("每天并发测试", cadence="daily")["goal"]
    with ThreadPoolExecutor(max_workers=8) as executor:
        results = list(executor.map(lambda _index: service.check_in(goal["id"], day=TODAY.isoformat()), range(12)))
    assert sum(result.points_awarded for result in results) == 10
    assert service.get_status()["points"] == 10
    assert len(DemonSlayerStore(path).load()["checkins"]) == 1


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="kei-demon-module-") as temp_dir:
        root = Path(temp_dir)
        asyncio.run(check_api(root / "api.json"))
        check_legacy_schema(root / "legacy.json")
        check_corrupt_and_atomic_failure(root)
        check_concurrent_duplicate(root / "concurrent.json")
    print("demon slayer module tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
