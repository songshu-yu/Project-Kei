"""Test and use Project Kei's demon slayer goal system.

Examples:
    python tests/test_demon_slayer.py
    python tests/test_demon_slayer.py --plan "每天读一篇论文；每周写一次总结"
    python tests/test_demon_slayer.py --status
    python tests/test_demon_slayer.py --checkin goal_xxx
    python tests/test_demon_slayer.py --daily-review
    python tests/test_demon_slayer.py --weekly-review
"""
from __future__ import annotations

import argparse
import tempfile
from datetime import date, timedelta
from pathlib import Path

import _path_setup  # noqa: F401

from systems.demon_slayer import (
    DemonSlayerStore,
    check_in,
    create_plan,
    daily_review,
    get_status,
    redeem_wish,
    reset,
    weekly_review,
)


DEMO_PLAN = "每天读一篇论文；每天健身二十分钟；每周写一次学习总结"


def print_goals(status: dict) -> None:
    print(f"points: {status['points']}")
    print("daily goals:")
    for goal in status["daily_goals"]:
        print(f"  {goal['id']} | {goal['demon']} | {goal['title']} | +{goal['points']}")
    print("weekly goals:")
    for goal in status["weekly_goals"]:
        print(f"  {goal['id']} | {goal['demon']} | {goal['title']} | +{goal['points']}")
    print(f"reminder: {status['reminder']}")


def demo() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        store = DemonSlayerStore(Path(tmp) / "demon_slayer.json")
        plan = create_plan(DEMO_PLAN, store=store)
        print(plan["message"])
        print_goals(get_status(store=store))

        today_value = date.today()
        today = today_value.isoformat()
        for goal in get_status(store=store)["daily_goals"][:2]:
            result = check_in(goal["id"], day=today, note="demo done", store=store)
            print(result.to_dict())

        print("daily review:")
        print(daily_review(day=today, store=store))

        week_start = (
            today_value - timedelta(days=today_value.weekday())
        ).isoformat()
        print("weekly review:")
        print(weekly_review(week_start=week_start, store=store))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--plan", help="Create goals from text")
    parser.add_argument("--reset-existing", action="store_true")
    parser.add_argument("--status", action="store_true")
    parser.add_argument("--checkin", help="Goal id to check in")
    parser.add_argument("--miss", action="store_true", help="Mark --checkin as not done")
    parser.add_argument("--date", help="YYYY-MM-DD")
    parser.add_argument("--note", default="")
    parser.add_argument("--daily-review", action="store_true")
    parser.add_argument("--weekly-review", action="store_true")
    parser.add_argument("--redeem", help="Wish id to redeem")
    parser.add_argument("--reset", action="store_true")
    args = parser.parse_args()

    if args.reset:
        print(reset())
        return 0
    if args.plan:
        result = create_plan(args.plan, reset_existing=args.reset_existing)
        print(result["message"])
        print_goals(get_status())
        return 0
    if args.checkin:
        result = check_in(args.checkin, day=args.date, done=not args.miss, note=args.note)
        print(result.to_dict())
        return 0
    if args.daily_review:
        print(daily_review(day=args.date))
        return 0
    if args.weekly_review:
        print(weekly_review(week_start=args.date))
        return 0
    if args.redeem:
        print(redeem_wish(args.redeem))
        return 0
    if args.status:
        print_goals(get_status(day=args.date))
        return 0

    demo()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
