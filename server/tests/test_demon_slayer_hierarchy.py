"""Focused compatibility checks for hierarchical demon-slayer goals."""
from __future__ import annotations

import tempfile
from datetime import date, timedelta
from pathlib import Path

import _path_setup  # noqa: F401

from systems.demon_slayer import (
    DemonSlayerStore,
    check_in,
    create_plan,
    daily_review,
    delete_goal,
    get_status,
    monthly_review,
    yearly_review,
)


def main() -> int:
    with tempfile.TemporaryDirectory() as temp_dir:
        store = DemonSlayerStore(Path(temp_dir) / "demon_slayer.json")
        today = date.today()

        daily = create_plan("完成角色速写", cadence="daily", category="creative", store=store)["created"][0]
        discarded = create_plan("临时测试目标", cadence="daily", category="general", store=store)["created"][0]
        monthly = create_plan("完成论文阶段报告", cadence="monthly", category="study", store=store)["created"][0]
        yearly = create_plan("完成年度作品集", cadence="yearly", category="general", store=store)["created"][0]

        assert daily["rank"] == "小妖" and daily["demon"] == "枯竭妖"
        assert monthly["rank"] == "大大妖" and monthly["points"] == 120
        assert yearly["rank"] == "妖王" and yearly["points"] == 500

        delete_goal(discarded["id"], store=store)
        assert discarded["title"] not in daily_review(day=today.isoformat(), store=store)["missed"]

        first = check_in(monthly["id"], day=today.isoformat(), store=store)
        second = check_in(monthly["id"], day=today.isoformat(), store=store)
        assert first.total_points == 120
        assert second.total_points == 120, "monthly goals must award points only once per month"
        assert second.points_awarded == 0 and second.duplicate is True

        temporary_daily = create_plan(
            "今天整理临时资料",
            cadence="daily",
            category="life",
            repeat_mode="once",
            target_date=today.isoformat(),
            store=store,
        )["created"][0]
        assert temporary_daily["repeat_mode"] == "once"
        assert temporary_daily["target_date"] == today.isoformat()
        assert any(
            goal["id"] == temporary_daily["id"]
            for goal in get_status(day=today.isoformat(), store=store)["daily_goals"]
        )
        assert not any(
            goal["id"] == temporary_daily["id"]
            for goal in get_status(day=(today + timedelta(days=1)).isoformat(), store=store)["goals"]
        )
        try:
            check_in(temporary_daily["id"], day=(today + timedelta(days=1)).isoformat(), store=store)
        except ValueError:
            pass
        else:
            raise AssertionError("a one-time daily goal must reject check-ins outside its target day")
        check_in(temporary_daily["id"], day=today.isoformat(), store=store)

        temporary_weekly = create_plan(
            "本周临时提交一次材料",
            cadence="weekly",
            category="study",
            repeat_mode="once",
            target_date=today.isoformat(),
            store=store,
        )["created"][0]
        assert temporary_weekly["target_period"] == (today - timedelta(days=today.weekday())).isoformat()
        weekly_first = check_in(temporary_weekly["id"], day=today.isoformat(), store=store)
        weekly_second = check_in(temporary_weekly["id"], day=today.isoformat(), store=store)
        assert weekly_second.total_points == weekly_first.total_points
        assert not any(
            goal["id"] == temporary_weekly["id"]
            for goal in get_status(day=(today + timedelta(days=7)).isoformat(), store=store)["goals"]
        )

        assert daily["repeat_mode"] == "recurring", "existing and default goals remain recurring"
        assert any(
            goal["id"] == daily["id"]
            for goal in get_status(day=(today + timedelta(days=1)).isoformat(), store=store)["daily_goals"]
        )
        legacy_state = store.load()
        next(goal for goal in legacy_state["goals"] if goal["id"] == daily["id"]).pop("repeat_mode")
        store.save(legacy_state)
        migrated_daily = next(goal for goal in store.load()["goals"] if goal["id"] == daily["id"])
        assert migrated_daily["repeat_mode"] == "recurring"

        status = get_status(day=today.isoformat(), store=store)
        monthly_status = next(goal for goal in status["monthly_goals"] if goal["id"] == monthly["id"])
        assert monthly_status["completed"] is True
        assert status["cadence_options"][2]["rank"] == "大大妖"
        assert any(option["label"] == "学业妖" for option in status["category_options"])

        month = monthly_review(month=today.strftime("%Y-%m"), store=store)
        assert month["period"] == "monthly"
        assert month["period_end"] == today.isoformat(), "current-month reviews must not penalize future days"
        assert month["breakdown"]["monthly"]["completed"] == 1
        assert monthly["title"] in month["completed_goals"]
        assert temporary_daily["title"] in month["completed_goals"]
        assert temporary_weekly["title"] in month["completed_goals"]

        year = yearly_review(year=str(today.year), store=store)
        assert year["period"] == "yearly"
        assert year["period_end"] == today.isoformat(), "current-year reviews must be year-to-date"
        assert "yearly" in year["breakdown"]
        assert yearly["title"] in year["missed"]

        points_before_delete = get_status(store=store)["points"]
        deleted = delete_goal(monthly["id"], store=store)
        assert deleted["goal"]["active"] is False
        assert not any(goal["id"] == monthly["id"] for goal in get_status(store=store)["goals"])
        assert get_status(store=store)["points"] == points_before_delete
        assert any(item["goal_id"] == monthly["id"] for item in store.load()["checkins"])

        restored = create_plan("完成论文阶段报告", cadence="monthly", category="study", store=store)
        assert restored["created"][0]["active"] is True

    print("demon slayer hierarchy tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
