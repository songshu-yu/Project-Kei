"""PK-150 check-in feedback contract with temporary state and fake Kei."""

from __future__ import annotations

import asyncio
import tempfile
from datetime import date, datetime, time
from pathlib import Path

import httpx
from fastapi import FastAPI

import _path_setup  # noqa: F401

from features.conversation.models import TextGenerationResult
from features.demon_slayer.repository import DemonSlayerStore
from features.demon_slayer.router import create_demon_slayer_router
from features.demon_slayer.service import DemonSlayerService


class FakeTime:
    def __init__(self, current: date):
        self.current = current

    def set(self, value: str) -> None:
        self.current = date.fromisoformat(value)

    def today(self) -> date:
        return self.current

    def now(self) -> datetime:
        return datetime.combine(self.current, time(9, 30))


class FakeKei:
    system_prompt = "你是测试用 Kei。"

    def __init__(self, *, tone: str = "playful", generated: bool = True, raises: bool = False):
        self.tone = tone
        self.generated = generated
        self.raises = raises
        self.calls: list[tuple[str, str, dict]] = []

    async def generate_text(self, system: str, user: str, **kwargs) -> TextGenerationResult:
        self.calls.append((system, user, kwargs))
        if self.raises:
            raise TimeoutError("fake timeout")
        return TextGenerationResult(
            text=f'{{"tone":"{self.tone}"}}' if self.generated else "",
            generated=self.generated,
            fallback=not self.generated,
            model="fake-kei",
            error_code=None if self.generated else "fake_unavailable",
        )


def make_service(path: Path, fake_time: FakeTime, fake_kei: FakeKei | None) -> DemonSlayerService:
    return DemonSlayerService(
        DemonSlayerStore(path),
        text_generator_provider=lambda: fake_kei,
        clock=fake_time.today,
        timestamp=fake_time.now,
    )


async def request(app: FastAPI, method: str, path: str, **kwargs) -> httpx.Response:
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        return await client.request(method, path, **kwargs)


async def check_service_feedback(path: Path) -> None:
    fake_time = FakeTime(date(2030, 1, 1))
    fake_kei = FakeKei(tone="playful")
    service = make_service(path, fake_time, fake_kei)
    goal = service.add_goal("每天完成虚构练习", cadence="daily")["goal"]
    service.check_in(goal["id"], day="2030-01-01")
    fake_time.set("2030-01-02")
    service.check_in(goal["id"], day="2030-01-02")

    fake_time.set("2030-01-03")
    result = await service.check_in_with_encouragement(goal["id"])
    assert result.active_since == "2030-01-01"
    assert result.active_days == 3
    assert result.current_streak == 3 and result.longest_streak == 3
    assert result.streak_unit == "day"
    assert result.kei_generated is True
    assert "连续完成 3 天" in result.encouragement
    assert "哼，确实有点厉害" in result.encouragement
    assert len(fake_kei.calls) == 1
    system, user, kwargs = fake_kei.calls[0]
    assert "只能依据" in system and "不要返回鼓励正文" in system
    assert '"current_streak": 3' in user and '"streak_unit": "day"' in user
    assert kwargs["fallback"] == ""

    before_duplicate = path.read_bytes()
    duplicate = await service.check_in_with_encouragement(goal["id"])
    assert duplicate.duplicate is True
    assert duplicate.points_awarded == 0
    assert duplicate.current_streak == 3
    assert duplicate.kei_generated is False
    assert "不会重复计算" in duplicate.encouragement
    assert len(fake_kei.calls) == 1
    assert path.read_bytes() == before_duplicate


async def check_versioned_legacy_and_fallback(path: Path) -> None:
    fake_time = FakeTime(date(2030, 2, 5))
    fake_kei = FakeKei(generated=False)
    service = make_service(path, fake_time, fake_kei)
    recurring = service.add_goal("每周完成虚构报告", cadence="weekly")["goal"]
    once = service.add_goal(
        "一次性虚构月目标",
        cadence="monthly",
        repeat_mode="once",
        target_date="2030-02-05",
    )["goal"]
    app = FastAPI()
    app.include_router(create_demon_slayer_router(service))

    versioned = await request(
        app,
        "POST",
        "/api/v1/demon-slayer/checkins",
        json={"goal_id": recurring["id"], "done": True, "note": "", "with_encouragement": True},
    )
    assert versioned.status_code == 200
    body = versioned.json()
    assert body["repeat_mode"] == "recurring"
    assert body["active_days"] == 1
    assert body["current_streak"] == 1 and body["longest_streak"] == 1
    assert body["streak_unit"] == "week"
    assert body["kei_generated"] is False
    assert "连续完成 1 周" in body["encouragement"]
    assert len(fake_kei.calls) == 1

    legacy = await request(
        app,
        "POST",
        "/demon/checkin",
        json={"goal_id": recurring["id"], "done": True, "note": "", "with_audio": False},
    )
    assert legacy.status_code == 200
    legacy_body = legacy.json()
    for field in (
        "repeat_mode",
        "active_since",
        "active_days",
        "current_streak",
        "longest_streak",
        "streak_unit",
    ):
        assert legacy_body[field] == body[field]
    assert legacy_body["duplicate"] is True
    assert legacy_body["kei_generated"] is False
    assert "不会重复计算" in legacy_body["encouragement"]
    assert legacy_body["audio_base64"] == ""
    assert len(fake_kei.calls) == 1

    once_result = await service.check_in_with_encouragement(once["id"])
    assert once_result.repeat_mode == "once"
    assert once_result.active_since is None and once_result.active_days is None
    assert once_result.current_streak == 0 and once_result.longest_streak == 0
    assert "临时目标已经完成" in once_result.encouragement

    timeout_time = FakeTime(date(2031, 1, 1))
    timeout_kei = FakeKei(raises=True)
    timeout_service = make_service(path.with_name("timeout.json"), timeout_time, timeout_kei)
    timeout_goal = timeout_service.add_goal("每年完成虚构总结", cadence="yearly")["goal"]
    timeout_result = await timeout_service.check_in_with_encouragement(timeout_goal["id"])
    assert timeout_result.done is True and timeout_result.kei_generated is False
    assert timeout_result.current_streak == 1 and timeout_result.streak_unit == "year"
    assert "连续完成 1 年" in timeout_result.encouragement
    assert len(timeout_kei.calls) == 1


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="kei-demon-feedback-") as temp_dir:
        root = Path(temp_dir)
        asyncio.run(check_service_feedback(root / "service.json"))
        asyncio.run(check_versioned_legacy_and_fallback(root / "api.json"))
    print("demon check-in feedback tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
