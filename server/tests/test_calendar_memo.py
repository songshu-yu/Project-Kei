"""Isolated regression checks for calendar, memo and mastery behavior."""

from __future__ import annotations

import json
import math
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import _path_setup  # noqa: F401

from features.calendar import repository as repository_module
from systems.calendar_memo import (
    MASTERY_REALMS,
    MASTERY_STAGES,
    CalendarMemoStore,
    CalendarPersistenceError,
    CalendarStateError,
    add_event,
    add_practice,
    events_for_day,
    get_status,
    mastery_level,
    parse_day,
    reset,
    today_summary,
    upcoming_events,
)


def expect_error(error_type: type[BaseException], operation) -> None:
    try:
        operation()
    except error_type:
        return
    raise AssertionError(f"expected {error_type.__name__}")


def isolated_store(root: str) -> CalendarMemoStore:
    return CalendarMemoStore(Path(root) / "calendar_memo.json")


def check_dates_events_and_summary() -> None:
    assert parse_day("2026-07-21").isoformat() == "2026-07-21"
    for invalid in ("", "2026-7-21", "2026-02-30", "not-a-date"):
        expect_error(ValueError, lambda value=invalid: parse_day(value))

    with tempfile.TemporaryDirectory(prefix="kei-calendar-events-") as temp_dir:
        store = isolated_store(temp_dir)
        first = add_event(
            "示例乙",
            "2026-12-31",
            note="去标识化备注",
            tags=["示例标签"],
            store=store,
        )
        duplicate = add_event(
            "示例乙",
            "2026-12-31",
            note="不同备注不改变既有去重语义",
            tags=["不同标签"],
            store=store,
        )
        assert duplicate["id"] == first["id"]
        add_event("示例甲", "2026-12-31", store=store)
        add_event("跨年示例", "2027-01-02", store=store)
        add_event("年度示例", "2000-12-31", repeat="yearly", store=store)
        assert [item["title"] for item in events_for_day("2026-12-31", store)] == [
            "年度示例",
            "示例乙",
            "示例甲",
        ]
        status = get_status("2026-12-31", store)
        assert status["events_count"] == 4
        assert status["events"][0]["title"] == "年度示例"
        future = upcoming_events("2026-12-30", days=7, store=store)
        assert [(item["occurrence_date"], item["days_left"]) for item in future] == [
            ("2026-12-31", 1),
            ("2026-12-31", 1),
            ("2026-12-31", 1),
            ("2027-01-02", 3),
        ]
        same_day = upcoming_events("2026-12-31", days=0, store=store)
        assert len(same_day) == 3 and all(item["days_left"] == 0 for item in same_day)
        expect_error(ValueError, lambda: upcoming_events("2026-12-31", days=-1, store=store))
        summary = today_summary("2026-12-31", store)
        assert summary["weekday"] == "星期四"
        assert all(item["days_left"] > 0 for item in summary["upcoming_events"])
        assert "今天是 2026-12-31，星期四。" in summary["message"]

        before = store.path.read_text(encoding="utf-8")
        for operation in (
            lambda: add_event(" ", "2026-12-31", store=store),
            lambda: add_event("无效日期", "2026-02-30", store=store),
            lambda: add_event("无效重复", "2026-12-31", repeat="weekly", store=store),
        ):
            expect_error(ValueError, operation)
            assert store.path.read_text(encoding="utf-8") == before


def check_yearly_leap_day() -> None:
    with tempfile.TemporaryDirectory(prefix="kei-calendar-leap-") as temp_dir:
        store = isolated_store(temp_dir)
        add_event("闰日示例", "2020-02-29", repeat="yearly", store=store)
        assert events_for_day("2024-02-29", store=store)
        assert not events_for_day("2025-02-28", store=store)
        next_occurrence = upcoming_events("2025-01-01", days=1200, store=store)
        assert next_occurrence[0]["occurrence_date"] == "2028-02-29"


def check_practice_and_mastery() -> None:
    with tempfile.TemporaryDirectory(prefix="kei-calendar-practice-") as temp_dir:
        store = isolated_store(temp_dir)
        for invalid_skill, invalid_hours in ((" ", 1), ("示例技能", 0), ("示例技能", -1)):
            expect_error(ValueError, lambda s=invalid_skill, h=invalid_hours: add_practice(s, h, store=store))
        for invalid in (math.nan, math.inf, -math.inf):
            expect_error(ValueError, lambda value=invalid: add_practice("示例技能", value, store=store))
        assert not store.path.exists()

        add_practice("示例技能", 0.25, day="2026-07-20", note="样例", store=store)
        result = add_practice("示例技能", 1.5, day="2026-07-21", store=store)
        assert result["skill"]["total_hours"] == 1.75
        for index in range(21):
            add_practice("示例技能", 0.1, day="2026-07-21", note=f"样例 {index}", store=store)
        status = get_status("2026-07-21", store)
        assert len(status["recent_practice_logs"]) == 20
        assert status["skills"][0]["total_hours"] == 3.85
        counts = reset(store)
        assert counts == {"events": 0, "skills": 1, "practice_logs": 23}

    with tempfile.TemporaryDirectory(prefix="kei-calendar-mastery-target-") as temp_dir:
        target = add_practice("万小时样例", 10000, store=isolated_store(temp_dir))
        assert target["skill"]["level"]["realm"] == "飞升"
        assert target["skill"]["level"]["hours_to_next"] == 0

    for index, (threshold, realm) in enumerate(MASTERY_REALMS):
        level = mastery_level(threshold)
        assert level["realm"] == realm and level["realm_index"] == index
    for realm_index, ((threshold, realm), (next_threshold, _)) in enumerate(zip(MASTERY_REALMS, MASTERY_REALMS[1:])):
        stage_width = (next_threshold - threshold) / len(MASTERY_STAGES)
        for stage_index, stage in enumerate(MASTERY_STAGES):
            level = mastery_level(threshold + stage_width * stage_index)
            assert level["realm"] == realm and level["realm_index"] == realm_index
            assert level["stage"] == stage and level["stage_index"] == stage_index
            assert 0 <= level["hours_to_next"] <= round(stage_width, 2)
    complete = mastery_level(10000)
    assert complete["realm"] == "飞升" and complete["stage"] == "圆满"
    assert complete["hours_to_next"] == 0 and complete["progress_to_10000"] == 100


def check_state_validation_and_atomic_failure() -> None:
    malformed_states = [
        "{not-json",
        json.dumps([]),
        json.dumps({"skills": [], "practice_logs": []}),
        json.dumps({"events": [], "practice_logs": []}),
        json.dumps({"events": [], "skills": []}),
        json.dumps({"events": {}, "skills": [], "practice_logs": []}),
        json.dumps({"events": [], "skills": "bad", "practice_logs": []}),
        json.dumps({"events": [], "skills": [], "practice_logs": {}}),
        json.dumps({"events": ["bad"], "skills": [], "practice_logs": []}),
    ]
    for raw in malformed_states:
        with tempfile.TemporaryDirectory(prefix="kei-calendar-invalid-") as temp_dir:
            path = Path(temp_dir) / "calendar_memo.json"
            path.write_text(raw, encoding="utf-8")
            expect_error(CalendarStateError, CalendarMemoStore(path).load)
            assert path.read_text(encoding="utf-8") == raw

    with tempfile.TemporaryDirectory(prefix="kei-calendar-atomic-") as temp_dir:
        store = isolated_store(temp_dir)
        add_event("原始样例", "2026-07-21", store=store)
        original = store.path.read_text(encoding="utf-8")
        original_replace = repository_module.os.replace

        def fail_replace(_source, _target):
            raise OSError("isolated replace failure")

        repository_module.os.replace = fail_replace
        try:
            expect_error(
                CalendarPersistenceError,
                lambda: add_event("失败样例", "2026-07-22", store=store),
            )
        finally:
            repository_module.os.replace = original_replace
        assert store.path.read_text(encoding="utf-8") == original
        assert not list(store.path.parent.glob(f".{store.path.name}.*.tmp"))


def check_concurrent_updates() -> None:
    with tempfile.TemporaryDirectory(prefix="kei-calendar-concurrent-") as temp_dir:
        path = Path(temp_dir) / "calendar_memo.json"

        def add_same_event(_index: int) -> None:
            add_event("并发样例", "2026-07-21", store=CalendarMemoStore(path))

        def add_hours(_index: int) -> None:
            add_practice("并发技能", 0.25, day="2026-07-21", store=CalendarMemoStore(path))

        with ThreadPoolExecutor(max_workers=8) as executor:
            list(executor.map(add_same_event, range(24)))
            list(executor.map(add_hours, range(40)))
        state = CalendarMemoStore(path).load()
        assert len(state["events"]) == 1
        assert len(state["practice_logs"]) == 40
        assert state["skills"][0]["total_hours"] == 10.0


def main() -> int:
    check_dates_events_and_summary()
    check_yearly_leap_day()
    check_practice_and_mastery()
    check_state_validation_and_atomic_failure()
    check_concurrent_updates()
    print("calendar memo tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
