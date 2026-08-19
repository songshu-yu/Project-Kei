"""PK-150 recurring-goal status statistics with only temporary state and fake time."""

from __future__ import annotations

import asyncio
import tempfile
from datetime import date, datetime, time
from pathlib import Path

import httpx
from fastapi import FastAPI

import _path_setup  # noqa: F401

from features.demon_slayer.repository import DemonSlayerStateError, DemonSlayerStore
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


def make_service(path: Path, fake_time: FakeTime) -> DemonSlayerService:
    return DemonSlayerService(
        DemonSlayerStore(path),
        clock=fake_time.today,
        timestamp=fake_time.now,
    )


async def request(app: FastAPI, method: str, path: str, **kwargs) -> httpx.Response:
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        return await client.request(method, path, **kwargs)


async def check_versioned_and_legacy_contract(path: Path) -> None:
    fake_time = FakeTime(date(2026, 1, 15))
    service = make_service(path, fake_time)
    app = FastAPI()
    app.include_router(create_demon_slayer_router(service))

    created = {}
    for cadence in ("daily", "weekly", "monthly", "yearly"):
        response = await request(app, "POST", "/api/v1/demon-slayer/goals", json={
            "title": f"{cadence} recurring target",
            "cadence": cadence,
            "category": "auto",
            "repeat_mode": "recurring",
            "target_date": None,
        })
        assert response.status_code == 200
        created[cadence] = response.json()["goal"]

    listed = await request(app, "GET", "/api/v1/demon-slayer/goals")
    assert listed.status_code == 200 and listed.json()["count"] == 4

    status = (await request(app, "GET", "/api/v1/demon-slayer/status?date=2026-01-15")).json()
    assert {goal["id"] for goal in status["goals"]} == {goal["id"] for goal in created.values()}
    for cadence, unit in {
        "daily": "day",
        "weekly": "week",
        "monthly": "month",
        "yearly": "year",
    }.items():
        group = status[f"{cadence}_goals"]
        assert [goal["id"] for goal in group] == [created[cadence]["id"]]
        goal = group[0]
        assert goal["active_since"] == "2026-01-15"
        assert goal["active_days"] == 1
        assert goal["current_streak"] == 0 and goal["longest_streak"] == 0
        assert goal["streak_unit"] == unit and goal["completed"] is False

    once = await request(app, "POST", "/api/v1/demon-slayer/goals", json={
        "title": "one-time target",
        "cadence": "daily",
        "category": "auto",
        "repeat_mode": "once",
        "target_date": "2026-01-15",
    })
    once_id = once.json()["goal"]["id"]
    versioned = (await request(app, "GET", "/api/v1/demon-slayer/status?date=2026-01-15")).json()
    legacy = (await request(app, "GET", "/demon/status?date=2026-01-15")).json()
    versioned_once = next(goal for goal in versioned["daily_goals"] if goal["id"] == once_id)
    legacy_once = next(goal for goal in legacy["daily_goals"] if goal["id"] == once_id)
    for goal in (versioned_once, legacy_once):
        assert goal["active_since"] is None and goal["active_days"] is None
        assert goal["current_streak"] == 0 and goal["longest_streak"] == 0
        assert goal["streak_unit"] == "day"
    assert legacy_once["completed"] == versioned_once["completed"]
    assert legacy == versioned


def check_daily_streaks_and_history(path: Path) -> None:
    fake_time = FakeTime(date(2026, 1, 1))
    service = make_service(path, fake_time)
    goal = service.add_goal("daily history target", cadence="daily")["goal"]

    fake_time.set("2026-01-03")
    service.check_in(goal["id"], day="2026-01-03")
    service.check_in(goal["id"], day="2026-01-01")
    service.check_in(goal["id"], day="2026-01-02")
    duplicate = service.check_in(goal["id"], day="2026-01-02")
    assert duplicate.duplicate is True and duplicate.points_awarded == 0
    status = service.get_status("2026-01-03")["daily_goals"][0]
    assert status["current_streak"] == 3 and status["longest_streak"] == 3

    fake_time.set("2026-01-04")
    service.check_in(goal["id"], day="2026-01-04", done=False)
    open_period = service.get_status()["daily_goals"][0]
    assert open_period["current_streak"] == 3, "the unfinished current day must not break yesterday's streak"

    fake_time.set("2026-01-05")
    service.check_in(goal["id"], done=True)
    after_gap = service.get_status()["daily_goals"][0]
    assert after_gap["current_streak"] == 1
    assert after_gap["longest_streak"] == 3

    fake_time.set("2026-01-06")
    service.check_in(goal["id"], done=False)
    assert service.get_status()["daily_goals"][0]["current_streak"] == 1
    fake_time.set("2026-01-07")
    service.check_in(goal["id"], done=True)
    final = service.get_status()["daily_goals"][0]
    assert final["current_streak"] == 1 and final["longest_streak"] == 3
    assert service.get_status()["points"] == 50

    state = service.repository.load()
    state["checkins"].append({
        "goal_id": goal["id"],
        "date": "2026-01-08",
        "cadence": "daily",
        "period_key": "2026-01-08",
        "done": True,
        "points_awarded": 10,
        "created_at": "2026-01-08T09:30:00",
    })
    service.repository.save(state)
    no_future = service.get_status("2026-01-07")["daily_goals"][0]
    assert no_future["current_streak"] == 1 and no_future["longest_streak"] == 3


def _check_cadence_streak(
    path: Path,
    *,
    cadence: str,
    created: str,
    completed: tuple[str, ...],
    queried: str,
    expected_unit: str,
) -> None:
    fake_time = FakeTime(date.fromisoformat(created))
    service = make_service(path, fake_time)
    goal = service.add_goal(f"{cadence} streak target", cadence=cadence)["goal"]
    fake_time.set(queried)
    for target in reversed(completed):
        service.check_in(goal["id"], day=target)
    status = service.get_status()[f"{cadence}_goals"][0]
    assert status["current_streak"] == len(completed)
    assert status["longest_streak"] == len(completed)
    assert status["streak_unit"] == expected_unit
    assert status["active_days"] == (date.fromisoformat(queried) - date.fromisoformat(created)).days + 1


def check_lifecycle_boundaries(path: Path) -> None:
    fake_time = FakeTime(date(2026, 2, 1))
    service = make_service(path, fake_time)
    goal = service.add_goal("reactivated recurring target", cadence="daily")["goal"]
    for target in ("2026-02-01", "2026-02-02", "2026-02-03"):
        fake_time.set(target)
        service.check_in(goal["id"])

    fake_time.set("2026-02-04")
    service.delete_goal(goal["id"])
    assert service.get_status()["daily_goals"] == []
    assert service.get_status("2026-02-03")["daily_goals"][0]["longest_streak"] == 3
    fake_time.set("2026-02-08")
    assert service.get_status()["daily_goals"] == []

    fake_time.set("2026-02-10")
    restored = service.add_goal("reactivated recurring target", cadence="daily")["goal"]
    assert restored["id"] == goal["id"]
    status = service.get_status()["daily_goals"][0]
    assert status["active_since"] == "2026-02-10" and status["active_days"] == 1
    assert status["current_streak"] == 0 and status["longest_streak"] == 3

    service.check_in(goal["id"])
    status = service.get_status()["daily_goals"][0]
    assert status["current_streak"] == 1 and status["longest_streak"] == 3
    fake_time.set("2026-02-11")
    status = service.get_status()["daily_goals"][0]
    assert status["active_days"] == 2 and status["current_streak"] == 1
    assert service.get_status("2026-01-31")["goals"] == []


def check_unfinished_cadence_periods(path: Path) -> None:
    cases = (
        ("weekly", "2026-01-05", ("2026-01-05", "2026-01-12"), "2026-01-21", "2026-01-26"),
        ("monthly", "2026-01-01", ("2026-01-01", "2026-02-01"), "2026-03-15", "2026-04-01"),
        ("yearly", "2023-01-01", ("2023-01-01", "2024-01-01"), "2025-07-01", "2026-01-01"),
    )
    for cadence, created, completed, open_query, closed_query in cases:
        fake_time = FakeTime(date.fromisoformat(closed_query))
        service = make_service(path.with_name(f"{path.stem}-{cadence}.json"), fake_time)
        fake_time.set(created)
        goal = service.add_goal(f"{cadence} unfinished period", cadence=cadence)["goal"]
        fake_time.set(closed_query)
        for target in completed:
            service.check_in(goal["id"], day=target)
        open_status = service.get_status(open_query)[f"{cadence}_goals"][0]
        assert open_status["current_streak"] == 2
        assert open_status["longest_streak"] == 2
        closed_status = service.get_status(closed_query)[f"{cadence}_goals"][0]
        assert closed_status["current_streak"] == 0
        assert closed_status["longest_streak"] == 2


def check_legacy_anchor_is_stable_and_read_only(path: Path) -> None:
    fake_time = FakeTime(date(2026, 3, 1))
    store = DemonSlayerStore(path)
    state = store.empty_state()
    state.pop("created_at")
    state["goals"] = [{
        "id": "legacy_without_anchor",
        "title": "legacy recurring target",
        "cadence": "daily",
        "category": "general",
        "repeat_mode": "recurring",
        "active": True,
    }]
    store.save(state)
    before = path.read_bytes()

    def unexpected_save(_state: dict) -> None:
        raise AssertionError("status must never enter the persistence write path")

    store._save_unlocked = unexpected_save  # type: ignore[method-assign]
    service = DemonSlayerService(store, clock=fake_time.today, timestamp=fake_time.now)

    first = service.get_status("2026-01-10")["daily_goals"][0]
    later = service.get_status("2026-02-10")["daily_goals"][0]
    repeated = service.get_status("2026-01-10")["daily_goals"][0]
    for goal in (first, later, repeated):
        assert goal["active_since"] is None
        assert goal["active_days"] is None
        assert goal["current_streak"] == 0
        assert goal["longest_streak"] == 0
        assert goal["completed"] is False
    assert path.read_bytes() == before, "status must not persist compatibility defaults or anchors"


def check_read_only_evidence_anchors(path: Path) -> None:
    fake_time = FakeTime(date(2026, 1, 12))
    store = DemonSlayerStore(path)
    state = store.empty_state()
    state.pop("created_at")
    state["goals"] = [{
        "id": "legacy_reactivated",
        "title": "legacy reactivated target",
        "cadence": "daily",
        "category": "general",
        "repeat_mode": "recurring",
        "active": True,
        "inactive_periods": [{"start": "2026-01-01", "end": "2026-01-10"}],
    }]
    store.save(state)
    before = path.read_bytes()
    goal = make_service(path, fake_time).get_status()["daily_goals"][0]
    assert goal["active_since"] == "2026-01-10"
    assert goal["active_days"] == 3
    assert goal["current_streak"] == 0 and goal["longest_streak"] == 0
    assert path.read_bytes() == before


def check_future_query_uses_only_facts_through_today(path: Path) -> None:
    fake_time = FakeTime(date(2026, 1, 1))
    service = make_service(path, fake_time)
    goal = service.add_goal("future query target", cadence="daily")["goal"]
    state = service.repository.load()
    state["checkins"].append({
        "goal_id": goal["id"],
        "date": "2026-01-10",
        "cadence": "daily",
        "period_key": "2026-01-10",
        "done": True,
        "points_awarded": 0,
    })
    service.repository.save(state)
    fake_time.set("2026-01-05")
    status = service.get_status("2026-01-10")["daily_goals"][0]
    assert status["active_since"] == "2026-01-01"
    assert status["active_days"] == 5
    assert status["current_streak"] == 0 and status["longest_streak"] == 0
    assert status["completed"] is False


def check_extreme_span_is_bounded_and_overflow_safe(path: Path) -> None:
    fake_time = FakeTime(date.max)
    store = DemonSlayerStore(path)
    state = store.empty_state()
    state["created_at"] = "0001-01-01T00:00:00"
    state["goals"] = [
        {
            "id": f"extreme_{cadence}",
            "title": f"extreme {cadence}",
            "cadence": cadence,
            "category": "general",
            "repeat_mode": "recurring",
            "active": True,
            "created_at": "0001-01-01T00:00:00",
        }
        for cadence in ("daily", "weekly", "monthly", "yearly")
    ]
    store.save(state)
    status = make_service(path, fake_time).get_status(date.max.isoformat())
    expected_days = (date.max - date.min).days + 1
    for cadence in ("daily", "weekly", "monthly", "yearly"):
        goal = status[f"{cadence}_goals"][0]
        assert goal["active_since"] == date.min.isoformat()
        assert goal["active_days"] == expected_days
        assert goal["current_streak"] == 0 and goal["longest_streak"] == 0


def check_conflicting_duplicate_history(path: Path) -> None:
    fake_time = FakeTime(date(2026, 4, 3))
    store = DemonSlayerStore(path)
    state = store.empty_state()
    state["created_at"] = "2026-04-01T09:30:00"
    state["goals"] = [{
        "id": "goal_conflict",
        "title": "conflicting history target",
        "cadence": "daily",
        "category": "general",
        "repeat_mode": "recurring",
        "active": True,
        "created_at": "2026-04-01T09:30:00",
    }]
    state["checkins"] = [
        {"goal_id": "goal_conflict", "date": "2026-04-03", "done": True, "points_awarded": 0},
        {"goal_id": "goal_conflict", "date": "2026-04-02", "done": False, "points_awarded": 0},
        {"goal_id": "goal_conflict", "date": "2026-04-01", "done": True, "points_awarded": 0},
        {"goal_id": "goal_conflict", "date": "2026-04-02", "done": True, "points_awarded": 0},
    ]
    store.save(state)
    goal = make_service(path, fake_time).get_status()["daily_goals"][0]
    assert goal["current_streak"] == 1 and goal["longest_streak"] == 1


def check_invalid_lifecycle_fails_closed(path: Path) -> None:
    fake_time = FakeTime(date(2026, 3, 1))
    service = make_service(path, fake_time)
    goal = service.add_goal("corrupt lifecycle target", cadence="daily")["goal"]
    store = DemonSlayerStore(path)
    state = store.load()
    next(item for item in state["goals"] if item["id"] == goal["id"])["inactive_periods"] = "broken"
    store.save(state)
    before = path.read_bytes()
    try:
        service.get_status()
    except DemonSlayerStateError:
        pass
    else:
        raise AssertionError("invalid lifecycle state must fail closed")
    assert path.read_bytes() == before

    for invalid_lifecycle in (
        [{"end": "2026-03-02"}],
        [{"start": "not-a-date", "end": "2026-03-02"}],
        [{"start": "2026-03-03", "end": "2026-03-02"}],
    ):
        state = store.load()
        next(item for item in state["goals"] if item["id"] == goal["id"])["inactive_periods"] = invalid_lifecycle
        store.save(state)
        before = path.read_bytes()
        try:
            service.get_status()
        except DemonSlayerStateError:
            pass
        else:
            raise AssertionError("malformed lifecycle intervals must fail closed")
        assert path.read_bytes() == before

    state = store.load()
    stored_goal = next(item for item in state["goals"] if item["id"] == goal["id"])
    stored_goal["inactive_periods"] = []
    stored_goal["created_at"] = "not-a-date"
    store.save(state)
    before = path.read_bytes()
    try:
        service.get_status()
    except DemonSlayerStateError:
        pass
    else:
        raise AssertionError("malformed goal lifecycle timestamps must fail closed")
    assert path.read_bytes() == before

    state = store.load()
    next(item for item in state["goals"] if item["id"] == goal["id"]).pop("created_at")
    state["created_at"] = "not-a-date"
    store.save(state)
    before = path.read_bytes()
    try:
        service.get_status()
    except DemonSlayerStateError:
        pass
    else:
        raise AssertionError("malformed state creation timestamps must fail closed")
    assert path.read_bytes() == before


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="kei-demon-statistics-") as temp_dir:
        root = Path(temp_dir)
        asyncio.run(check_versioned_and_legacy_contract(root / "contract.json"))
        check_daily_streaks_and_history(root / "daily.json")
        _check_cadence_streak(
            root / "weekly.json",
            cadence="weekly",
            created="2026-01-01",
            completed=("2026-01-01", "2026-01-05", "2026-01-12"),
            queried="2026-01-12",
            expected_unit="week",
        )
        _check_cadence_streak(
            root / "monthly.json",
            cadence="monthly",
            created="2026-01-15",
            completed=("2026-01-15", "2026-02-01", "2026-03-01"),
            queried="2026-03-01",
            expected_unit="month",
        )
        _check_cadence_streak(
            root / "yearly.json",
            cadence="yearly",
            created="2024-06-10",
            completed=("2024-06-10", "2025-01-01", "2026-01-01"),
            queried="2026-01-01",
            expected_unit="year",
        )
        check_lifecycle_boundaries(root / "lifecycle.json")
        check_unfinished_cadence_periods(root / "unfinished-periods.json")
        check_legacy_anchor_is_stable_and_read_only(root / "legacy-unknown-anchor.json")
        check_read_only_evidence_anchors(root / "legacy-reactivation-anchor.json")
        check_future_query_uses_only_facts_through_today(root / "future-query.json")
        check_extreme_span_is_bounded_and_overflow_safe(root / "extreme-span.json")
        check_conflicting_duplicate_history(root / "conflicting-history.json")
        check_invalid_lifecycle_fails_closed(root / "invalid-lifecycle.json")
    print("demon slayer statistics tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
