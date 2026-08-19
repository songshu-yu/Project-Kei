"""Legacy Python facade for :mod:`features.demon_slayer`.

All business and persistence rules live in the built-in feature module.  This
file keeps existing imports used by scripts and the legacy voice pipeline.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from features.demon_slayer.models import CheckinResult
from features.demon_slayer.repository import (
    DATA_DIR,
    DEFAULT_STORE,
    DEFAULT_WISHES,
    DemonSlayerPersistenceError,
    DemonSlayerStateError,
    DemonSlayerStore,
)
from features.demon_slayer.service import (
    CADENCE_META,
    CATEGORY_META,
    CATEGORY_RULES,
    DAILY_POINTS,
    MONTHLY_POINTS,
    PERFECT_DAY_BONUS,
    PERFECT_MONTH_BONUS,
    PERFECT_WEEK_BONUS,
    PERFECT_YEAR_BONUS,
    WEEKLY_POINTS,
    YEARLY_POINTS,
    DemonSlayerService,
    classify_goal,
    daily_review_message,
    infer_cadence,
    normalize_day,
    parse_day,
    today_key,
    week_start_for,
    weekly_review_message,
)


_DEFAULT_SERVICE = DemonSlayerService(DemonSlayerStore(DEFAULT_STORE))


def get_default_service() -> DemonSlayerService:
    return _DEFAULT_SERVICE


def _service(store: Optional[DemonSlayerStore]) -> DemonSlayerService:
    return DemonSlayerService(store) if store is not None else _DEFAULT_SERVICE


def create_plan(
    text: str,
    reset_existing: bool = False,
    cadence: Optional[str] = None,
    category: Optional[str] = None,
    repeat_mode: str = "recurring",
    target_date: Optional[str] = None,
    store: Optional[DemonSlayerStore] = None,
) -> Dict[str, Any]:
    return _service(store).create_plan(
        text,
        reset_existing=reset_existing,
        cadence=cadence,
        category=category,
        repeat_mode=repeat_mode,
        target_date=target_date,
    )


def add_goal(
    title: str,
    cadence: str = "auto",
    category: str = "auto",
    repeat_mode: str = "recurring",
    target_date: Optional[str] = None,
    store: Optional[DemonSlayerStore] = None,
) -> Dict[str, Any]:
    return _service(store).add_goal(
        title,
        cadence=cadence,
        category=category,
        repeat_mode=repeat_mode,
        target_date=target_date,
    )


def update_goal(
    goal_id: str,
    *,
    title: Optional[str] = None,
    cadence: Optional[str] = None,
    category: Optional[str] = None,
    repeat_mode: Optional[str] = None,
    target_date: Optional[str] = None,
    store: Optional[DemonSlayerStore] = None,
) -> Dict[str, Any]:
    return _service(store).update_goal(
        goal_id,
        title=title,
        cadence=cadence,
        category=category,
        repeat_mode=repeat_mode,
        target_date=target_date,
    )


def delete_goal(goal_id: str, store: Optional[DemonSlayerStore] = None) -> Dict[str, Any]:
    return _service(store).delete_goal(goal_id)


def check_in(
    goal_id: str,
    day: Optional[str] = None,
    done: bool = True,
    note: str = "",
    store: Optional[DemonSlayerStore] = None,
) -> CheckinResult:
    return _service(store).check_in(goal_id, day=day, done=done, note=note)


def get_status(day: Optional[str] = None, store: Optional[DemonSlayerStore] = None) -> Dict[str, Any]:
    return _service(store).get_status(day)


def active_goals(state: Dict[str, Any], cadence: Optional[str] = None) -> List[Dict[str, Any]]:
    goals = [goal for goal in state.get("goals", []) if goal.get("active", True)]
    return [goal for goal in goals if not cadence or goal.get("cadence") == cadence]


def period_review(period: str, anchor: Optional[str] = None, store: Optional[DemonSlayerStore] = None) -> Dict[str, Any]:
    return _service(store).period_review(period, anchor=anchor)


def daily_review(day: Optional[str] = None, store: Optional[DemonSlayerStore] = None) -> Dict[str, Any]:
    return _service(store).daily_review(day)


def weekly_review(week_start: Optional[str] = None, store: Optional[DemonSlayerStore] = None) -> Dict[str, Any]:
    return _service(store).weekly_review(week_start)


def monthly_review(month: Optional[str] = None, store: Optional[DemonSlayerStore] = None) -> Dict[str, Any]:
    return _service(store).monthly_review(month)


def yearly_review(year: Optional[str] = None, store: Optional[DemonSlayerStore] = None) -> Dict[str, Any]:
    return _service(store).yearly_review(year)


def reminder(day: Optional[str] = None, store: Optional[DemonSlayerStore] = None) -> str:
    return _service(store).reminder(day)


def add_wish(
    title: str,
    cost: int,
    description: str = "",
    store: Optional[DemonSlayerStore] = None,
) -> Dict[str, Any]:
    return _service(store).add_reward(title, cost, description)


def redeem_wish(
    wish_id: str,
    store: Optional[DemonSlayerStore] = None,
    request_id: Optional[str] = None,
) -> Dict[str, Any]:
    return _service(store).redeem_reward(wish_id, request_id=request_id)


def reset(store: Optional[DemonSlayerStore] = None) -> Dict[str, int]:
    return _service(store).reset()


def plan_message(created: List[Dict[str, Any]]) -> str:
    return DemonSlayerService.plan_message(created)


def checkin_message(goal: Dict[str, Any], done: bool, points: int, total: int) -> str:
    return DemonSlayerService.checkin_message(goal, done, points, total)


__all__ = [
    "CADENCE_META",
    "CATEGORY_META",
    "CATEGORY_RULES",
    "CheckinResult",
    "DAILY_POINTS",
    "DATA_DIR",
    "DEFAULT_STORE",
    "DEFAULT_WISHES",
    "DemonSlayerPersistenceError",
    "DemonSlayerService",
    "DemonSlayerStateError",
    "DemonSlayerStore",
    "MONTHLY_POINTS",
    "PERFECT_DAY_BONUS",
    "PERFECT_MONTH_BONUS",
    "PERFECT_WEEK_BONUS",
    "PERFECT_YEAR_BONUS",
    "WEEKLY_POINTS",
    "YEARLY_POINTS",
    "active_goals",
    "add_goal",
    "add_wish",
    "check_in",
    "checkin_message",
    "classify_goal",
    "create_plan",
    "daily_review",
    "daily_review_message",
    "delete_goal",
    "get_default_service",
    "get_status",
    "infer_cadence",
    "monthly_review",
    "normalize_day",
    "parse_day",
    "period_review",
    "plan_message",
    "redeem_wish",
    "reminder",
    "reset",
    "today_key",
    "update_goal",
    "week_start_for",
    "weekly_review",
    "weekly_review_message",
    "yearly_review",
]
