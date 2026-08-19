"""Goal, check-in, reward and factual review rules for demon slayer."""

from __future__ import annotations

import hashlib
import json
import re
from bisect import bisect_right
from dataclasses import replace
from datetime import date, datetime, timedelta
from typing import Any, Callable, Dict, List, Optional, Protocol, Tuple

from .models import CheckinResult
from .repository import DEFAULT_WISHES, DemonSlayerStateError, DemonSlayerStore


DAILY_POINTS = 10
WEEKLY_POINTS = 35
MONTHLY_POINTS = 120
YEARLY_POINTS = 500
PERFECT_DAY_BONUS = 5
PERFECT_WEEK_BONUS = 30
PERFECT_MONTH_BONUS = 100
PERFECT_YEAR_BONUS = 500

CADENCE_META = {
    "daily": {"label": "日目标", "rank": "小妖", "points": DAILY_POINTS},
    "weekly": {"label": "周目标", "rank": "大妖", "points": WEEKLY_POINTS},
    "monthly": {"label": "月目标", "rank": "大大妖", "points": MONTHLY_POINTS},
    "yearly": {"label": "年目标", "rank": "妖王", "points": YEARLY_POINTS},
}
STREAK_UNITS = {
    "daily": "day",
    "weekly": "week",
    "monthly": "month",
    "yearly": "year",
}

CATEGORY_RULES = [
    ("study", "学业妖", ("论文", "学习", "读书", "课程", "复习", "英语", "研究", "paper", "study", "read")),
    ("fitness", "虚弱妖", ("健身", "运动", "跑步", "力量", "睡眠", "饮食", "健康", "workout", "gym")),
    ("focus", "拖延妖", ("代码", "项目", "开发", "写作", "实验", "工作", "专注", "番茄", "code", "project")),
    ("life", "混乱妖", ("整理", "打扫", "房间", "日程", "收纳", "洗", "clean", "schedule")),
    ("creative", "枯竭妖", ("画", "音乐", "创作", "视频", "设计", "写小说", "create", "draw")),
]
CATEGORY_META = {
    category: {"category": category, "demon": demon}
    for category, demon, _keywords in CATEGORY_RULES
}
CATEGORY_META["general"] = {"category": "general", "demon": "迷雾妖"}

_DAY_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_EMOTION_PATTERN = re.compile(r"\[emotion:(happy|sad|calm|angry|shy|surprised)\]", re.IGNORECASE)
_CADENCE_ORDER = tuple(CADENCE_META)


class TextGenerator(Protocol):
    system_prompt: str

    async def generate_text(self, system: str, user: str, **kwargs: Any) -> Any:
        ...


def parse_day(day: str) -> date:
    value = str(day or "")
    if not _DAY_PATTERN.fullmatch(value):
        raise ValueError("date must use YYYY-MM-DD")
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError("date must be a valid YYYY-MM-DD") from exc


def today_key() -> str:
    return date.today().isoformat()


def normalize_day(day: Optional[str]) -> str:
    return today_key() if not day else parse_day(day).isoformat()


def week_start_for(day: Optional[str] = None) -> str:
    target = parse_day(normalize_day(day))
    return (target - timedelta(days=target.weekday())).isoformat()


def _stable_id(prefix: str, value: str) -> str:
    return f"{prefix}_{hashlib.sha1(value.encode('utf-8')).hexdigest()[:8]}"


def _slug(value: str) -> str:
    return _stable_id("goal", value)


def _split_goal_text(text: str) -> List[str]:
    chunks = [raw.strip(" -\t\r") for raw in re.split(r"[\n;；]+", str(text or ""))]
    return [chunk for chunk in chunks if chunk]


def classify_goal(title: str) -> Dict[str, str]:
    lower = str(title).lower()
    for category, demon, keywords in CATEGORY_RULES:
        if any(keyword.lower() in lower for keyword in keywords):
            return {"category": category, "demon": demon}
    return {"category": "general", "demon": "迷雾妖"}


def infer_cadence(title: str) -> str:
    lower = str(title).lower()
    groups = (
        ("yearly", ("每年", "年度", "全年", "一年", "yearly", "annual", "year")),
        ("monthly", ("每月", "月度", "本月", "一个月", "monthly", "month")),
        ("weekly", ("每周", "周末", "一周", "weekly", "week", "复盘", "总结")),
        ("daily", ("每天", "每日", "天天", "daily", "day")),
    )
    for cadence, words in groups:
        if any(word in lower for word in words):
            return cadence
    return "daily"


def _clean_title(title: str) -> str:
    value = str(title or "").strip()
    value = re.sub(r"^(每天|每日|每周|周末|每月|月度|每年|年度|我要|我想|目标是|目标：|目标:)\s*", "", value)
    value = value.strip()
    if not value:
        raise ValueError("goal title must not be blank")
    if len(value) > 200:
        raise ValueError("goal title is too long")
    return value


def _normalize_cadence(value: Optional[str], title: str) -> str:
    cadence = str(value or "auto").strip().lower()
    if cadence in {"", "auto"}:
        cadence = infer_cadence(title)
    if cadence not in CADENCE_META:
        raise ValueError(f"unsupported cadence: {value}")
    return cadence


def _normalize_category(value: Optional[str], title: str) -> Dict[str, str]:
    category = str(value or "auto").strip().lower()
    if category in {"", "auto"}:
        return classify_goal(title)
    if category not in CATEGORY_META:
        raise ValueError(f"unsupported demon category: {value}")
    return dict(CATEGORY_META[category])


def _normalize_repeat_mode(value: Optional[str]) -> str:
    repeat_mode = str(value or "recurring").strip().lower()
    if repeat_mode not in {"recurring", "once"}:
        raise ValueError(f"unsupported repeat mode: {value}")
    return repeat_mode


def _period_key(cadence: str, day: str) -> str:
    target = parse_day(day)
    if cadence == "daily":
        return target.isoformat()
    if cadence == "weekly":
        return (target - timedelta(days=target.weekday())).isoformat()
    if cadence == "monthly":
        return target.strftime("%Y-%m")
    if cadence == "yearly":
        return target.strftime("%Y")
    raise ValueError(f"unsupported cadence: {cadence}")


def _period_bounds(cadence: str, target: date) -> Tuple[date, date]:
    if cadence == "daily":
        return target, target
    if cadence == "weekly":
        start = target - timedelta(days=target.weekday())
        end = date.max if start > date.max - timedelta(days=6) else start + timedelta(days=6)
        return start, end
    if cadence == "monthly":
        start = target.replace(day=1)
        if start.year == date.max.year and start.month == 12:
            return start, date.max
        next_month = (
            date(start.year + 1, 1, 1)
            if start.month == 12
            else date(start.year, start.month + 1, 1)
        )
        return start, next_month - timedelta(days=1)
    if cadence == "yearly":
        return date(target.year, 1, 1), date(target.year, 12, 31)
    raise ValueError(f"unsupported cadence: {cadence}")


def _next_period_start(cadence: str, start: date) -> Optional[date]:
    if cadence == "daily":
        return None if start == date.max else start + timedelta(days=1)
    if cadence == "weekly":
        return None if start > date.max - timedelta(days=7) else start + timedelta(days=7)
    if cadence == "monthly":
        if start.year == date.max.year and start.month == 12:
            return None
        return date(start.year + 1, 1, 1) if start.month == 12 else date(start.year, start.month + 1, 1)
    if cadence == "yearly":
        return None if start.year == date.max.year else date(start.year + 1, 1, 1)
    raise ValueError(f"unsupported cadence: {cadence}")


def _previous_period_start(cadence: str, start: date) -> Optional[date]:
    if cadence == "daily":
        return None if start == date.min else start - timedelta(days=1)
    if cadence == "weekly":
        return None if start < date.min + timedelta(days=7) else start - timedelta(days=7)
    if cadence == "monthly":
        if start.year == date.min.year and start.month == 1:
            return None
        return date(start.year - 1, 12, 1) if start.month == 1 else date(start.year, start.month - 1, 1)
    if cadence == "yearly":
        return None if start.year == date.min.year else date(start.year - 1, 1, 1)
    raise ValueError(f"unsupported cadence: {cadence}")


def _date_from_timestamp(value: object) -> Optional[date]:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return parse_day(text[:10])
    except ValueError:
        return None


def _checkin_cadence(item: Dict[str, Any], goal: Dict[str, Any]) -> str:
    cadence = str(item.get("cadence") or goal.get("cadence") or "daily")
    return cadence if cadence in CADENCE_META else "daily"


def _checkin_period_key(item: Dict[str, Any], goal: Dict[str, Any]) -> str:
    cadence = _checkin_cadence(item, goal)
    return str(item.get("period_key") or _period_key(cadence, str(item.get("date", ""))))


class DemonSlayerService:
    def __init__(
        self,
        repository: DemonSlayerStore,
        *,
        text_generator_provider: Optional[Callable[[], Optional[TextGenerator]]] = None,
        clock: Callable[[], date] = date.today,
        timestamp: Callable[[], datetime] = datetime.now,
    ):
        self.repository = repository
        self.text_generator_provider = text_generator_provider or (lambda: None)
        self.clock = clock
        self.timestamp = timestamp

    def _now(self) -> str:
        return self.timestamp().isoformat(timespec="seconds")

    def _normalize_day(self, day: Optional[str]) -> str:
        return self.clock().isoformat() if not day else parse_day(day).isoformat()

    def _normalize_state(self, state: Dict[str, Any]) -> Dict[str, Any]:
        if state.get("created_at") and _date_from_timestamp(state.get("created_at")) is None:
            raise DemonSlayerStateError("demon-slayer state creation time is invalid")
        for goal in state["goals"]:
            title = str(goal.get("title") or "未命名目标").strip() or "未命名目标"
            cadence = str(goal.get("cadence") or "daily").lower()
            if cadence not in CADENCE_META:
                cadence = "daily"
            inferred = classify_goal(title)
            category = str(goal.get("category") or inferred["category"]).lower()
            if category not in CATEGORY_META:
                category = inferred["category"]
            repeat_mode = str(goal.get("repeat_mode") or "recurring").lower()
            if repeat_mode not in {"recurring", "once"}:
                repeat_mode = "recurring"
            goal["title"] = title
            goal["cadence"] = cadence
            goal["category"] = category
            goal["demon"] = str(goal.get("demon") or CATEGORY_META[category]["demon"])
            goal["rank"] = str(goal.get("rank") or CADENCE_META[cadence]["rank"])
            try:
                points = int(goal.get("points", CADENCE_META[cadence]["points"]))
            except (TypeError, ValueError):
                points = CADENCE_META[cadence]["points"]
            goal["points"] = max(points, 0)
            goal["active"] = bool(goal.get("active", True))
            goal["repeat_mode"] = repeat_mode
            goal["id"] = str(goal.get("id") or _slug(f"{title}:{cadence}:{category}"))
            for field in ("created_at", "deleted_at"):
                if goal.get(field) and _date_from_timestamp(goal.get(field)) is None:
                    raise DemonSlayerStateError("demon-slayer goal lifecycle is invalid")
            inactive_periods = goal.get("inactive_periods", [])
            if not isinstance(inactive_periods, list) or any(not isinstance(item, dict) for item in inactive_periods):
                raise DemonSlayerStateError("demon-slayer goal lifecycle is invalid")
            for interval in inactive_periods:
                start = _date_from_timestamp(interval.get("start"))
                end = _date_from_timestamp(interval.get("end"))
                if start is None:
                    raise DemonSlayerStateError("demon-slayer goal lifecycle is invalid")
                if interval.get("end") and end is None:
                    raise DemonSlayerStateError("demon-slayer goal lifecycle is invalid")
                if start and end and end < start:
                    raise DemonSlayerStateError("demon-slayer goal lifecycle is invalid")
            if repeat_mode == "once":
                target = str(goal.get("target_date") or str(goal.get("created_at") or state.get("created_at") or self._now())[:10])
                target_date = parse_day(target).isoformat()
                goal["target_date"] = target_date
                goal["target_period"] = _period_key(cadence, target_date)
        known_ids = {str(goal.get("id")) for goal in state["goals"]}
        for item in state["checkins"]:
            if str(item.get("goal_id") or "") not in known_ids:
                continue
            try:
                item["date"] = parse_day(str(item.get("date") or "")).isoformat()
                awarded = int(item.get("points_awarded", 0))
            except (TypeError, ValueError) as exc:
                raise DemonSlayerStateError("demon-slayer check-in is invalid") from exc
            if awarded < 0:
                raise DemonSlayerStateError("demon-slayer check-in points must not be negative")
            item["points_awarded"] = awarded
            item["done"] = bool(item.get("done", False))
        return state

    def _goal_payload(
        self,
        title: str,
        cadence: Optional[str],
        category: Optional[str],
        repeat_mode: Optional[str],
        target_date: Optional[str],
    ) -> Dict[str, Any]:
        cleaned = _clean_title(title)
        normalized_cadence = _normalize_cadence(cadence, title)
        category_meta = _normalize_category(category, cleaned)
        normalized_repeat = _normalize_repeat_mode(repeat_mode)
        normalized_target = ""
        if normalized_repeat == "once":
            if not target_date:
                raise ValueError("target_date is required for a one-time goal")
            normalized_target = parse_day(target_date).isoformat()
        identity = f"{cleaned}:{normalized_cadence}:{category_meta['category']}"
        if normalized_repeat == "once":
            identity += f":once:{_period_key(normalized_cadence, normalized_target)}"
        goal = {
            "id": _slug(identity),
            "title": cleaned,
            "cadence": normalized_cadence,
            "category": category_meta["category"],
            "demon": category_meta["demon"],
            "rank": CADENCE_META[normalized_cadence]["rank"],
            "points": CADENCE_META[normalized_cadence]["points"],
            "repeat_mode": normalized_repeat,
            "active": True,
            "created_at": self._now(),
        }
        if normalized_repeat == "once":
            goal["target_date"] = normalized_target
            goal["target_period"] = _period_key(normalized_cadence, normalized_target)
        return goal

    @staticmethod
    def _goal_applies_to_day(goal: Dict[str, Any], target: date) -> bool:
        if str(goal.get("repeat_mode", "recurring")) != "once":
            return True
        cadence = str(goal.get("cadence", "daily"))
        target_period = str(goal.get("target_period") or _period_key(cadence, str(goal.get("target_date"))))
        return target_period == _period_key(cadence, target.isoformat())

    @classmethod
    def _goal_active_on(cls, goal: Dict[str, Any], target: date) -> bool:
        if not cls._goal_applies_to_day(goal, target):
            return False
        created = _date_from_timestamp(goal.get("created_at"))
        if created and target < created:
            return False
        for interval in goal.get("inactive_periods", []):
            start = _date_from_timestamp(interval.get("start"))
            end = _date_from_timestamp(interval.get("end"))
            if start and target >= start and (end is None or target < end):
                return False
        deleted = _date_from_timestamp(goal.get("deleted_at"))
        if not goal.get("active", True) and (deleted is None or target >= deleted):
            return False
        return True

    @staticmethod
    def _freeze_goal_checkins(state: Dict[str, Any], goal: Dict[str, Any]) -> None:
        for item in state["checkins"]:
            if item.get("goal_id") != goal.get("id"):
                continue
            cadence = str(goal.get("cadence", "daily"))
            item.setdefault("cadence", cadence)
            item.setdefault("period_key", _period_key(cadence, str(item.get("date"))))
            item.setdefault("goal_title", str(goal.get("title", "")))
            item.setdefault("goal_rank", str(goal.get("rank", "")))
            item.setdefault("goal_demon", str(goal.get("demon", "")))

    def create_plan(
        self,
        text: str,
        *,
        reset_existing: bool = False,
        cadence: Optional[str] = None,
        category: Optional[str] = None,
        repeat_mode: str = "recurring",
        target_date: Optional[str] = None,
    ) -> Dict[str, Any]:
        chunks = _split_goal_text(text)
        if not chunks:
            raise ValueError("at least one goal is required")
        candidates = [self._goal_payload(chunk, cadence, category, repeat_mode, target_date) for chunk in chunks]

        def mutation(state: Dict[str, Any]) -> Tuple[Dict[str, Any], bool]:
            self._normalize_state(state)
            changed = False
            now = self._now()
            if reset_existing:
                for current in state["goals"]:
                    if current.get("active", True):
                        current["active"] = False
                        current["deleted_at"] = now
                        changed = True
            known = {str(goal.get("id")): goal for goal in state["goals"]}
            created: List[Dict[str, Any]] = []
            for candidate in candidates:
                existing = known.get(candidate["id"])
                if existing and existing.get("active", True):
                    continue
                if existing:
                    deleted_at = existing.get("deleted_at")
                    if deleted_at:
                        existing.setdefault("inactive_periods", []).append({"start": deleted_at, "end": now})
                    original_created_at = existing.get("created_at")
                    existing.update(candidate)
                    if original_created_at:
                        existing["created_at"] = original_created_at
                    existing.pop("deleted_at", None)
                    goal = existing
                else:
                    state["goals"].append(candidate)
                    known[candidate["id"]] = candidate
                    goal = candidate
                created.append(dict(goal))
                changed = True
            response = {"status": "ok", "created": created, "message": self.plan_message(created)}
            for cadence_key in CADENCE_META:
                response[f"{cadence_key}_goals"] = [
                    dict(goal) for goal in state["goals"]
                    if goal.get("active", True) and goal.get("cadence") == cadence_key
                ]
            return response, changed

        return self.repository.mutate(mutation)

    def add_goal(
        self,
        title: str,
        *,
        cadence: str = "auto",
        category: str = "auto",
        repeat_mode: str = "recurring",
        target_date: Optional[str] = None,
    ) -> Dict[str, Any]:
        result = self.create_plan(
            title,
            cadence=cadence,
            category=category,
            repeat_mode=repeat_mode,
            target_date=target_date,
        )
        result["goal"] = result["created"][0] if result["created"] else None
        return result

    def update_goal(
        self,
        goal_id: str,
        *,
        title: Optional[str] = None,
        cadence: Optional[str] = None,
        category: Optional[str] = None,
        repeat_mode: Optional[str] = None,
        target_date: Optional[str] = None,
    ) -> Dict[str, Any]:
        def mutation(state: Dict[str, Any]) -> Tuple[Dict[str, Any], bool]:
            self._normalize_state(state)
            goal = next((item for item in state["goals"] if item.get("id") == goal_id), None)
            if goal is None or not goal.get("active", True):
                raise KeyError(goal_id)
            next_title = _clean_title(title if title is not None else str(goal.get("title", "")))
            next_cadence = _normalize_cadence(cadence if cadence is not None else str(goal.get("cadence")), next_title)
            category_input = category if category is not None else str(goal.get("category"))
            next_category = _normalize_category(category_input, next_title)
            next_repeat = _normalize_repeat_mode(repeat_mode if repeat_mode is not None else str(goal.get("repeat_mode")))
            if next_repeat == "once":
                next_target = target_date or str(goal.get("target_date") or "")
                if not next_target:
                    raise ValueError("target_date is required for a one-time goal")
                next_target = parse_day(next_target).isoformat()
            else:
                next_target = ""
            self._freeze_goal_checkins(state, goal)
            goal.update({
                "title": next_title,
                "cadence": next_cadence,
                "category": next_category["category"],
                "demon": next_category["demon"],
                "rank": CADENCE_META[next_cadence]["rank"],
                "points": CADENCE_META[next_cadence]["points"],
                "repeat_mode": next_repeat,
                "updated_at": self._now(),
            })
            if next_repeat == "once":
                goal["target_date"] = next_target
                goal["target_period"] = _period_key(next_cadence, next_target)
            else:
                goal.pop("target_date", None)
                goal.pop("target_period", None)
            return {
                "status": "ok",
                "goal": dict(goal),
                "message": f"目标“{next_title}”已更新；历史打卡和既得积分保持不变。",
            }, True

        return self.repository.mutate(mutation)

    def delete_goal(self, goal_id: str) -> Dict[str, Any]:
        def mutation(state: Dict[str, Any]) -> Tuple[Dict[str, Any], bool]:
            self._normalize_state(state)
            goal = next((item for item in state["goals"] if item.get("id") == goal_id), None)
            if goal is None:
                raise KeyError(goal_id)
            if not goal.get("active", True):
                return {
                    "status": "already_inactive",
                    "goal": dict(goal),
                    "message": f"目标“{goal.get('title', '')}”已经停止追踪；历史记录保持不变。",
                }, False
            goal["active"] = False
            goal["deleted_at"] = self._now()
            return {
                "status": "ok",
                "goal": dict(goal),
                "message": f"已移除目标“{goal.get('title', '')}”。历史打卡和积分会保留。",
            }, True

        return self.repository.mutate(mutation)

    @staticmethod
    def plan_message(created: List[Dict[str, Any]]) -> str:
        if not created:
            return "目标没有新增。哼，是不是已经登记过了？那就别光看，去行动。"
        counts = {cadence: sum(1 for goal in created if goal["cadence"] == cadence) for cadence in CADENCE_META}
        details = "，".join(f"{CADENCE_META[key]['label']} {count} 个" for key, count in counts.items() if count)
        temporary = sum(1 for goal in created if goal.get("repeat_mode") == "once")
        suffix = f"，其中临时目标 {temporary} 个" if temporary else ""
        return f"作战计划登记完成：{details}{suffix}。从小妖到妖王都记下了，老师不许只立目标不行动。"

    @staticmethod
    def _find_checkin(state: Dict[str, Any], goal: Dict[str, Any], target_day: str) -> Optional[Dict[str, Any]]:
        cadence = str(goal.get("cadence", "daily"))
        period_key = _period_key(cadence, target_day)
        compatible = None
        for item in state["checkins"]:
            if item.get("goal_id") != goal.get("id"):
                continue
            if _checkin_cadence(item, goal) == cadence and _checkin_period_key(item, goal) == period_key:
                return item
            try:
                if _period_key(cadence, str(item.get("date", ""))) == period_key:
                    compatible = compatible or item
            except ValueError:
                continue
        return compatible

    @staticmethod
    def _day_is_inactive(goal: Dict[str, Any], target: date) -> bool:
        for interval in goal.get("inactive_periods", []):
            start = _date_from_timestamp(interval.get("start"))
            end = _date_from_timestamp(interval.get("end"))
            if start is not None and target >= start and (end is None or target < end):
                return True
        deleted = _date_from_timestamp(goal.get("deleted_at"))
        return bool(not goal.get("active", True) and (deleted is None or target >= deleted))

    @classmethod
    def _goal_created_on(
        cls,
        state: Dict[str, Any],
        goal: Dict[str, Any],
        as_of: date,
    ) -> Optional[date]:
        created = _date_from_timestamp(goal.get("created_at"))
        if created is not None:
            return created
        state_created = _date_from_timestamp(state.get("created_at"))
        known_days: List[date] = []
        if state_created is not None and state_created <= as_of:
            known_days.append(state_created)
        for item in state["checkins"]:
            if item.get("goal_id") != goal.get("id"):
                continue
            checkin_day = _date_from_timestamp(item.get("date"))
            if checkin_day is not None and checkin_day <= as_of and not cls._day_is_inactive(goal, checkin_day):
                known_days.append(checkin_day)
        for interval in goal.get("inactive_periods", []):
            reactivated = _date_from_timestamp(interval.get("end"))
            if reactivated is not None and reactivated <= as_of and not cls._day_is_inactive(goal, reactivated):
                known_days.append(reactivated)
        return min(known_days) if known_days else None

    @classmethod
    def _active_segments(
        cls,
        state: Dict[str, Any],
        goal: Dict[str, Any],
        as_of: date,
    ) -> List[Tuple[date, date]]:
        created = cls._goal_created_on(state, goal, as_of)
        if created is None or created > as_of:
            return []
        inactive: List[Tuple[date, date]] = []
        for interval in goal.get("inactive_periods", []):
            start = _date_from_timestamp(interval.get("start"))
            end = _date_from_timestamp(interval.get("end"))
            if start is None or (end is not None and end <= start):
                continue
            inclusive_end = as_of if end is None or end > as_of else end - timedelta(days=1)
            clipped_start = max(start, created)
            if clipped_start <= inclusive_end:
                inactive.append((clipped_start, inclusive_end))
        if not goal.get("active", True):
            deleted = _date_from_timestamp(goal.get("deleted_at")) or created
            if deleted <= as_of:
                inactive.append((max(deleted, created), as_of))
        inactive.sort()
        merged: List[Tuple[date, date]] = []
        for start, end in inactive:
            adjacent = bool(merged and merged[-1][1] < date.max and start == merged[-1][1] + timedelta(days=1))
            if merged and (start <= merged[-1][1] or adjacent):
                merged[-1] = (merged[-1][0], max(merged[-1][1], end))
            else:
                merged.append((start, end))

        segments: List[Tuple[date, date]] = []
        cursor = created
        for start, end in merged:
            if cursor < start:
                segments.append((cursor, start - timedelta(days=1)))
            if end >= as_of:
                cursor = None
                break
            cursor = max(cursor, end + timedelta(days=1))
        if cursor is not None and cursor <= as_of:
            segments.append((cursor, as_of))
        return [(start, end) for start, end in segments if start <= end]

    @staticmethod
    def _checkin_revision(item: Dict[str, Any]) -> float:
        raw = str(item.get("updated_at") or item.get("created_at") or "").strip()
        try:
            value = datetime.fromisoformat(raw.replace("Z", "+00:00")).timestamp()
        except (TypeError, ValueError, OSError):
            value = float("-inf")
        return value

    def _goal_statistics(
        self,
        state: Dict[str, Any],
        goal: Dict[str, Any],
        as_of: date,
    ) -> Dict[str, Any]:
        cadence = str(goal.get("cadence", "daily"))
        result = {
            "active_since": None,
            "active_days": None,
            "current_streak": 0,
            "longest_streak": 0,
            "streak_unit": STREAK_UNITS[cadence],
        }
        if str(goal.get("repeat_mode", "recurring")) != "recurring":
            return result

        segments = self._active_segments(state, goal, as_of)
        if not segments or not (segments[-1][0] <= as_of <= segments[-1][1]):
            return result
        current_start = segments[-1][0]
        result["active_since"] = current_start.isoformat()
        result["active_days"] = (as_of - current_start).days + 1

        outcomes: Dict[Tuple[int, date], Tuple[float, bool]] = {}
        segment_starts = [segment[0] for segment in segments]
        for item in state["checkins"]:
            if item.get("goal_id") != goal.get("id"):
                continue
            snapshot_cadence = str(item.get("cadence") or cadence)
            if snapshot_cadence != cadence:
                continue
            checkin_day = _date_from_timestamp(item.get("date"))
            if checkin_day is None or checkin_day > as_of:
                continue
            segment_index = bisect_right(segment_starts, checkin_day) - 1
            if segment_index < 0 or checkin_day > segments[segment_index][1]:
                continue
            period_start = _period_bounds(cadence, checkin_day)[0]
            key = (segment_index, period_start)
            revision = self._checkin_revision(item)
            completed = bool(item.get("done"))
            previous = outcomes.get(key)
            if previous is None or revision > previous[0] or (revision == previous[0] and not completed):
                outcomes[key] = (revision, completed)

        completed_by_segment: Dict[int, set[date]] = {}
        for (segment_index, period_start), (_revision, completed) in outcomes.items():
            if completed:
                completed_by_segment.setdefault(segment_index, set()).add(period_start)

        longest = 0
        for completed_periods in completed_by_segment.values():
            run = 0
            previous = None
            for period_start in sorted(completed_periods):
                run = run + 1 if previous is not None and _next_period_start(cadence, previous) == period_start else 1
                longest = max(longest, run)
                previous = period_start

        current_periods = completed_by_segment.get(len(segments) - 1, set())
        current_period = _period_bounds(cadence, as_of)[0]
        candidate = current_period if current_period in current_periods else _previous_period_start(cadence, current_period)
        first_current_period = _period_bounds(cadence, current_start)[0]
        current = 0
        while candidate is not None and candidate >= first_current_period and candidate in current_periods:
            current += 1
            candidate = _previous_period_start(cadence, candidate)

        result["current_streak"] = current
        result["longest_streak"] = longest
        return result

    def check_in(self, goal_id: str, *, day: Optional[str] = None, done: bool = True, note: str = "") -> CheckinResult:
        target_day = self._normalize_day(day)
        target = parse_day(target_day)
        if target > self.clock():
            raise ValueError("future check-ins are not allowed")
        clean_note = str(note or "").strip()[:500]

        def mutation(state: Dict[str, Any]) -> Tuple[CheckinResult, bool]:
            self._normalize_state(state)
            goal = next((item for item in state["goals"] if item.get("id") == goal_id), None)
            if goal is None:
                raise KeyError(goal_id)
            if not self._goal_active_on(goal, target):
                raise ValueError("goal is inactive or outside its target period")
            existing = self._find_checkin(state, goal, target_day)
            previous_points = int(existing.get("points_awarded", 0)) if existing else 0
            cadence_changed_after_completion = bool(
                existing
                and existing.get("done")
                and _checkin_cadence(existing, goal) != str(goal.get("cadence", "daily"))
            )
            desired_points = previous_points if done and cadence_changed_after_completion else int(goal.get("points", 0)) if done else 0
            delta = desired_points - previous_points
            next_balance = int(state.get("points", 0)) + delta
            if next_balance < 0:
                raise ValueError("completed points have already been spent and cannot be revoked")
            duplicate = bool(existing and bool(existing.get("done")) == bool(done) and str(existing.get("note", "")) == clean_note)
            changed = not duplicate
            if existing:
                if changed:
                    existing.update({
                        "done": bool(done),
                        "note": clean_note,
                        "points_awarded": desired_points,
                        "updated_at": self._now(),
                    })
            else:
                cadence = str(goal.get("cadence", "daily"))
                state["checkins"].append({
                    "goal_id": goal_id,
                    "date": target_day,
                    "cadence": cadence,
                    "period_key": _period_key(cadence, target_day),
                    "goal_title": str(goal.get("title", "")),
                    "goal_rank": str(goal.get("rank", "")),
                    "goal_demon": str(goal.get("demon", "")),
                    "done": bool(done),
                    "note": clean_note,
                    "points_awarded": desired_points,
                    "created_at": self._now(),
                })
                changed = True
            if changed:
                state["points"] = next_balance
            awarded_this_request = max(delta, 0) if changed else 0
            message = self.checkin_message(goal, bool(done), awarded_this_request, int(state["points"]), duplicate)
            statistics = self._goal_statistics(state, goal, target)
            result = CheckinResult(
                goal_id=goal_id,
                date=target_day,
                done=bool(done),
                points_awarded=awarded_this_request,
                total_points=int(state["points"]),
                message=message,
                duplicate=duplicate,
                repeat_mode=str(goal.get("repeat_mode", "recurring")),
                active_since=statistics["active_since"],
                active_days=statistics["active_days"],
                current_streak=int(statistics["current_streak"]),
                longest_streak=int(statistics["longest_streak"]),
                streak_unit=str(statistics["streak_unit"]),
            )
            return replace(result, encouragement=self._checkin_encouragement(result)), changed

        return self.repository.mutate(mutation)

    @staticmethod
    def _parse_encouragement_tone(text: str) -> str:
        clean = _EMOTION_PATTERN.sub("", str(text or "")).strip().lower()
        match = re.search(r"(?:\"?tone\"?\s*[:=]\s*\"?)?(warm|strict|playful)(?:\"|\s|}|$)", clean)
        return match.group(1) if match else ""

    @staticmethod
    def _checkin_encouragement(result: CheckinResult, tone: str = "warm") -> str:
        if result.duplicate:
            return "Kei：这个周期已经记录过了，成绩不会重复计算。保持住现在的节奏就好。"
        if not result.done:
            return "Kei：这次没完成也要如实面对。整理好原因，下个周期重新把它击破。"

        unit = {
            "day": "天",
            "week": "周",
            "month": "月",
            "year": "年",
        }.get(result.streak_unit, "个周期")
        if result.current_streak > 0:
            achievement = f"已经连续完成 {result.current_streak} {unit}"
        elif result.repeat_mode == "once":
            achievement = "这个临时目标已经完成"
        else:
            achievement = "这个周期已经完成"

        endings = {
            "warm": "我看到了你的坚持，继续保持。",
            "strict": "做得不错，但别停在这里，下个周期也要交出结果。",
            "playful": "哼，确实有点厉害。下一次也别掉链子。",
        }
        return f"Kei：{achievement}。{endings.get(tone, endings['warm'])}"

    async def check_in_with_encouragement(
        self,
        goal_id: str,
        *,
        day: Optional[str] = None,
        done: bool = True,
        note: str = "",
    ) -> CheckinResult:
        result = self.check_in(goal_id, day=day, done=done, note=note)
        if result.duplicate or not result.done:
            return result
        try:
            generator = self.text_generator_provider()
        except Exception:
            return result
        if generator is None:
            return result

        facts = {
            "goal_id": result.goal_id,
            "date": result.date,
            "done": result.done,
            "repeat_mode": result.repeat_mode,
            "active_since": result.active_since,
            "active_days": result.active_days,
            "current_streak": result.current_streak,
            "longest_streak": result.longest_streak,
            "streak_unit": result.streak_unit,
            "points_awarded": result.points_awarded,
            "total_points": result.total_points,
        }
        persona = str(getattr(generator, "system_prompt", "") or "").strip()
        system = ((persona + "\n\n") if persona else "") + (
            "你是天童 Kei 的打卡鼓励语气选择器。只能依据用户提供的 JSON 事实，不得补充、"
            "改写或猜测目标、日期、连续完成、积分或其他经历。只返回一个 tone："
            "warm、strict 或 playful；不要返回鼓励正文。"
        )
        user = "斩妖打卡事实：\n" + json.dumps(facts, ensure_ascii=False, sort_keys=True)
        try:
            generated = await generator.generate_text(
                system,
                user,
                max_tokens=20,
                temperature=0.2,
                fallback="",
            )
        except Exception:
            return result
        if not generated.generated:
            return result
        tone = self._parse_encouragement_tone(generated.text)
        if not tone:
            return result
        return replace(
            result,
            encouragement=self._checkin_encouragement(result, tone),
            kei_generated=True,
        )

    @staticmethod
    def checkin_message(goal: Dict[str, Any], done: bool, points: int, total: int, duplicate: bool = False) -> str:
        enemy = f"{goal.get('rank', '小妖')}·{goal.get('demon', '迷雾妖')}"
        if duplicate:
            return f"{enemy}本周期已经记录过了，没有重复发放积分。总积分 {total}。"
        if not done:
            return f"{enemy}暂时没击破。先如实记下，下一次继续。"
        return f"{enemy}击破。获得 {points} 积分，总积分 {total}。做得不错……才不是夸你太多。"

    def list_goals(self, *, include_inactive: bool = False) -> List[Dict[str, Any]]:
        state = self._normalize_state(self.repository.load())
        return [dict(goal) for goal in state["goals"] if include_inactive or goal.get("active", True)]

    def get_status(self, day: Optional[str] = None) -> Dict[str, Any]:
        state = self._normalize_state(self.repository.load())
        target_day = self._normalize_day(day)
        target = parse_day(target_day)
        factual_as_of = min(target, self.clock())
        goals = []
        for goal in state["goals"]:
            if not self._goal_active_on(goal, target):
                continue
            checkin = self._find_checkin(state, goal, target_day) if target <= factual_as_of else None
            enriched = dict(goal)
            enriched["completed"] = bool(checkin and checkin.get("done"))
            enriched["checkin_date"] = str(checkin.get("date", "")) if checkin else ""
            enriched.update(self._goal_statistics(state, goal, factual_as_of))
            goals.append(enriched)
        result = {
            "date": target_day,
            "points": int(state["points"]),
            "goals": goals,
            "cadence_options": [{"value": key, **value} for key, value in CADENCE_META.items()],
            "category_options": [{"value": key, "label": value["demon"]} for key, value in CATEGORY_META.items()],
            "auto_classification_supported": True,
            "wishes": [dict(item) for item in state["wishes"]],
            "recent_checkins": [dict(item) for item in state["checkins"][-100:]],
            "recent_redemptions": [dict(item) for item in state["redemptions"][-10:]],
        }
        for cadence in CADENCE_META:
            result[f"{cadence}_goals"] = [goal for goal in goals if goal.get("cadence") == cadence]
        result["reminder"] = self._reminder_from_state(state, target)
        return result

    def _reminder_from_state(self, state: Dict[str, Any], target: date) -> str:
        pending = []
        for goal in state["goals"]:
            if not self._goal_active_on(goal, target):
                continue
            checkin = self._find_checkin(state, goal, target.isoformat())
            if not bool(checkin and checkin.get("done")):
                pending.append(goal)
        if not pending:
            return "今天的妖怪清得很干净。哼，老师偶尔也挺让人省心。"
        names = [f"{CADENCE_META[str(goal.get('cadence', 'daily'))]['label']}：{goal.get('title', '')}" for goal in pending[:5]]
        return "还没击破：" + "；".join(names) + "。别拖到睡前才想起来。"

    def reminder(self, day: Optional[str] = None) -> str:
        state = self._normalize_state(self.repository.load())
        return self._reminder_from_state(state, parse_day(self._normalize_day(day)))

    def _review_bounds(self, period: str, anchor: Optional[str]) -> Tuple[date, date, date]:
        today = self.clock()
        if period == "daily":
            start = parse_day(anchor) if anchor else today
            nominal_end = start
        elif period == "weekly":
            target = parse_day(anchor) if anchor else today
            start = target - timedelta(days=target.weekday())
            nominal_end = start + timedelta(days=6)
        elif period == "monthly":
            value = str(anchor or today.strftime("%Y-%m"))
            try:
                start = datetime.strptime(value, "%Y-%m").date().replace(day=1)
            except ValueError as exc:
                raise ValueError("month must use YYYY-MM") from exc
            next_month = (start.replace(day=28) + timedelta(days=4)).replace(day=1)
            nominal_end = next_month - timedelta(days=1)
        elif period == "yearly":
            value = str(anchor or today.year)
            if not re.fullmatch(r"\d{4}", value):
                raise ValueError("year must use YYYY")
            start = date(int(value), 1, 1)
            nominal_end = date(int(value), 12, 31)
        else:
            raise ValueError(f"unsupported review period: {period}")
        if start > today:
            raise ValueError("future review periods are not available")
        return start, min(nominal_end, today), nominal_end

    @staticmethod
    def _review_message(period: str, completed: int, total: int, points: int, missed: List[str]) -> str:
        label = {"daily": "今日", "weekly": "本周", "monthly": "本月", "yearly": "本年"}[period]
        if total == 0:
            return f"{label}还没有对应的作战目标。先立靶子，Kei 才能按事实监督你。"
        if completed == total:
            return f"{label}全清，完成 {completed}/{total}，获得 {points} 积分。做得很漂亮，这次可以认真夸你。"
        if completed == 0:
            return f"{label}完成 0/{total}。这次没有可记为击破的目标，必须按事实批评；先从最小的一只妖开始补救。"
        return f"{label}完成 {completed}/{total}，获得 {points} 积分。完成的部分值得表扬；还漏了 {len(missed)} 项，也必须认真批评。"

    @staticmethod
    def _review_period_closed(period: str, nominal_end: date, today: date) -> bool:
        if nominal_end > today:
            return False
        if period == "daily":
            return True
        if period == "weekly":
            return nominal_end.weekday() == 6
        if period == "monthly":
            return (nominal_end + timedelta(days=1)).month != nominal_end.month
        return period == "yearly" and nominal_end.month == 12 and nominal_end.day == 31

    def period_review(self, period: str, *, anchor: Optional[str] = None) -> Dict[str, Any]:
        start, end, nominal_end = self._review_bounds(period, anchor)
        days = [start + timedelta(days=offset) for offset in range((end - start).days + 1)]
        included = _CADENCE_ORDER[: _CADENCE_ORDER.index(period) + 1]

        def mutation(state: Dict[str, Any]) -> Tuple[Dict[str, Any], bool]:
            self._normalize_state(state)
            breakdown = {cadence: {"completed": 0, "total": 0, "goals": 0} for cadence in included}
            missed_titles: List[str] = []
            completed_titles: List[str] = []
            notes: List[str] = []
            counted: set[Tuple[str, str, str]] = set()
            goals_by_id = {str(goal.get("id")): goal for goal in state["goals"]}

            for goal in state["goals"]:
                cadence = str(goal.get("cadence", "daily"))
                if cadence not in included:
                    continue
                expected = {_period_key(cadence, target.isoformat()) for target in days if self._goal_active_on(goal, target)}
                done_items = [
                    item for item in state["checkins"]
                    if item.get("goal_id") == goal.get("id")
                    and item.get("done")
                    and _checkin_cadence(item, goal) == cadence
                    and start.isoformat() <= str(item.get("date", "")) <= end.isoformat()
                ]
                done_keys = {_checkin_period_key(item, goal) for item in done_items}
                expected |= done_keys
                if not expected:
                    continue
                completed_keys = expected & done_keys
                breakdown[cadence]["goals"] += 1
                breakdown[cadence]["total"] += len(expected)
                breakdown[cadence]["completed"] += len(completed_keys)
                counted.update((str(goal.get("id")), cadence, key) for key in completed_keys)
                if completed_keys:
                    completed_titles.append(str(goal.get("title", "")))
                if expected - completed_keys:
                    missed_titles.append(str(goal.get("title", "")))

            for item in state["checkins"]:
                if not item.get("done") or not (start.isoformat() <= str(item.get("date", "")) <= end.isoformat()):
                    continue
                goal = goals_by_id.get(str(item.get("goal_id")))
                if goal is None:
                    continue
                cadence = _checkin_cadence(item, goal)
                if cadence not in included:
                    continue
                key = (str(item.get("goal_id")), cadence, _checkin_period_key(item, goal))
                if key not in counted:
                    breakdown[cadence]["goals"] += 1
                    breakdown[cadence]["total"] += 1
                    breakdown[cadence]["completed"] += 1
                    counted.add(key)
                    completed_titles.append(str(item.get("goal_title") or goal.get("title", "")))
                clean_note = str(item.get("note", "")).strip()
                if clean_note:
                    notes.append(clean_note)

            completed = sum(item["completed"] for item in breakdown.values())
            total = sum(item["total"] for item in breakdown.values())
            points = sum(
                int(item.get("points_awarded", 0))
                for item in state["checkins"]
                if item.get("done")
                and start.isoformat() <= str(item.get("date", "")) <= end.isoformat()
                and (goals_by_id.get(str(item.get("goal_id"))) is not None)
                and _checkin_cadence(item, goals_by_id[str(item.get("goal_id"))]) in included
            )
            unique_missed = list(dict.fromkeys(title for title in missed_titles if title))
            unique_completed = list(dict.fromkeys(title for title in completed_titles if title))
            bonus_points = {
                "daily": PERFECT_DAY_BONUS,
                "weekly": PERFECT_WEEK_BONUS,
                "monthly": PERFECT_MONTH_BONUS,
                "yearly": PERFECT_YEAR_BONUS,
            }[period]
            bonus_key = f"{period}:{start.isoformat()}"
            bonus_exists = any(item.get("key") == bonus_key for item in state["bonuses"])
            bonus = bonus_points if total and completed == total and self._review_period_closed(period, nominal_end, self.clock()) and not bonus_exists else 0
            if bonus:
                state["points"] = int(state["points"]) + bonus
                state["bonuses"].append({"key": bonus_key, "points": bonus, "created_at": self._now()})
            result = {
                "period": period,
                "period_start": start.isoformat(),
                "period_end": end.isoformat(),
                "completed": completed,
                "total": total,
                "completion_rate": round(completed / total, 4) if total else 0.0,
                "completed_goals": unique_completed,
                "missed": unique_missed,
                "notes": notes[-20:],
                "breakdown": breakdown,
                "points_earned": points + bonus,
                "bonus": bonus,
                "total_points": int(state["points"]),
                "message": self._review_message(period, completed, total, points + bonus, unique_missed),
            }
            return result, bool(bonus)

        return self.repository.mutate(mutation)

    @staticmethod
    def _parse_verdict(text: str) -> str:
        clean = _EMOTION_PATTERN.sub("", str(text or "")).strip().lower()
        match = re.search(r"(?:\"?verdict\"?\s*[:=]\s*\"?)?(praise|criticize|mixed)(?:\"|\s|}|$)", clean)
        return match.group(1) if match else ""

    @staticmethod
    def _verdict_message(review: Dict[str, Any], verdict: str) -> Tuple[str, str]:
        completed = int(review.get("completed", 0))
        total = int(review.get("total", 0))
        done = "、".join(review.get("completed_goals", [])) or "无"
        missed = "、".join(review.get("missed", [])) or "无"
        facts = f"实际完成 {completed}/{total}；已完成：{done}；未完成：{missed}。"
        if verdict == "praise":
            return facts + "这些真实成果值得表扬，继续保持。", "happy"
        if verdict == "criticize":
            return facts + "这次必须按事实批评：别回避未完成项，从最小的一项开始补救。", "sad"
        return facts + "完成的部分值得表扬，未完成的部分也必须批评；把收尾做好。", "calm"

    async def review(self, period: str, *, anchor: Optional[str] = None) -> Dict[str, Any]:
        return await self.evaluate_review(self.period_review(period, anchor=anchor))

    async def evaluate_review(self, review: Dict[str, Any]) -> Dict[str, Any]:
        review = dict(review)
        review["kei_generated"] = False
        review["emotion"] = "calm"
        completed = int(review.get("completed", 0))
        total = int(review.get("total", 0))
        if not total:
            return review
        generator = self.text_generator_provider()
        if generator is None:
            return review
        facts = {
            "period": review.get("period"),
            "period_start": review.get("period_start"),
            "period_end": review.get("period_end"),
            "completed": completed,
            "total": total,
            "completion_rate": review.get("completion_rate", round(completed / total, 4)),
            "completed_goals": list(review.get("completed_goals", [])),
            "missed_goals": list(review.get("missed", [])),
            "notes": list(review.get("notes", [])),
            "breakdown": dict(review.get("breakdown", {})),
            "points_earned": int(review.get("points_earned", 0)),
        }
        persona = str(getattr(generator, "system_prompt", "") or "").strip()
        system = ((persona + "\n\n") if persona else "") + (
            "你是天童 Kei 的复盘裁决器。只能依据用户提供的 JSON 事实，不得补充、改写或猜测完成情况，"
            "不得发放积分或修改状态。只返回一个 verdict：praise、criticize 或 mixed。"
        )
        user = "斩妖复盘事实：\n" + json.dumps(facts, ensure_ascii=False, sort_keys=True)
        try:
            generated = await generator.generate_text(
                system,
                user,
                max_tokens=40,
                temperature=0.1,
                fallback="",
            )
        except Exception:
            return review
        if not generated.generated:
            return review
        verdict = self._parse_verdict(generated.text)
        allowed = {"praise"} if completed == total else {"criticize"} if completed == 0 else {"praise", "criticize", "mixed"}
        if verdict not in allowed:
            return review
        review["message"], review["emotion"] = self._verdict_message(review, verdict)
        review["kei_generated"] = True
        return review

    def daily_review(self, day: Optional[str] = None) -> Dict[str, Any]:
        result = self.period_review("daily", anchor=day)
        result["date"] = result["period_start"]
        result["reminder"] = self.reminder(result["date"])
        return result

    def weekly_review(self, week_start: Optional[str] = None) -> Dict[str, Any]:
        result = self.period_review("weekly", anchor=week_start)
        result.update({
            "week_start": result["period_start"],
            "week_end": result["period_end"],
            "daily_completed": result["breakdown"].get("daily", {}).get("completed", 0),
            "daily_total": result["breakdown"].get("daily", {}).get("total", 0),
            "weekly_completed": result["breakdown"].get("weekly", {}).get("completed", 0),
            "weekly_total": result["breakdown"].get("weekly", {}).get("total", 0),
        })
        return result

    def monthly_review(self, month: Optional[str] = None) -> Dict[str, Any]:
        result = self.period_review("monthly", anchor=month)
        result["month"] = result["period_start"][:7]
        return result

    def yearly_review(self, year: Optional[str] = None) -> Dict[str, Any]:
        result = self.period_review("yearly", anchor=year)
        result["year"] = result["period_start"][:4]
        return result

    def add_reward(self, title: str, cost: int, description: str = "") -> Dict[str, Any]:
        clean_title = str(title or "").strip()
        if not clean_title:
            raise ValueError("reward title must not be blank")
        amount = int(cost)
        if amount < 1:
            raise ValueError("reward cost must be positive")
        reward_id = _stable_id("reward", f"{clean_title}:{amount}")

        def mutation(state: Dict[str, Any]) -> Tuple[Dict[str, Any], bool]:
            self._normalize_state(state)
            existing = next((item for item in state["wishes"] if item.get("id") == reward_id), None)
            if existing:
                return dict(existing), False
            reward = {
                "id": reward_id,
                "title": clean_title,
                "cost": amount,
                "description": str(description or "").strip(),
                "created_at": self._now(),
            }
            state["wishes"].append(reward)
            return dict(reward), True

        return self.repository.mutate(mutation)

    def redeem_reward(self, reward_id: str, *, request_id: Optional[str] = None) -> Dict[str, Any]:
        clean_request_id = str(request_id or "").strip()
        if len(clean_request_id) > 120:
            raise ValueError("request_id is too long")
        idempotency_key = f"redeem:{reward_id}:{clean_request_id or 'default'}"

        def mutation(state: Dict[str, Any]) -> Tuple[Dict[str, Any], bool]:
            self._normalize_state(state)
            reward = next((item for item in state["wishes"] if item.get("id") == reward_id), None)
            if reward is None:
                raise KeyError(reward_id)
            if clean_request_id:
                previous = next((item for item in state["redemptions"] if item.get("idempotency_key") == idempotency_key), None)
            else:
                previous = next((item for item in state["redemptions"] if item.get("wish_id") == reward_id), None)
            if previous:
                return {
                    "status": "already_redeemed",
                    "wish": dict(reward),
                    "redemption": dict(previous),
                    "points": int(state["points"]),
                    "message": "这次兑换请求已经处理过了，没有重复扣除积分。",
                }, False
            cost = int(reward.get("cost", 0))
            points = int(state["points"])
            if points < cost:
                return {
                    "status": "not_enough_points",
                    "wish": dict(reward),
                    "points": points,
                    "needed": cost - points,
                    "message": f"积分还差 {cost - points}。愿望可以有，但妖怪也得继续斩。",
                }, False
            redemption = {
                "wish_id": reward_id,
                "title": reward.get("title", ""),
                "cost": cost,
                "idempotency_key": idempotency_key,
                "created_at": self._now(),
            }
            state["points"] = points - cost
            state["redemptions"].append(redemption)
            return {
                "status": "redeemed",
                "wish": dict(reward),
                "redemption": dict(redemption),
                "points": int(state["points"]),
                "message": f"愿望兑换批准：{reward.get('title')}。这是你赢来的，不许心虚。",
            }, True

        return self.repository.mutate(mutation)

    def reset(self) -> Dict[str, int]:
        def mutation(state: Dict[str, Any]) -> Tuple[Dict[str, int], bool]:
            self._normalize_state(state)
            counts = {
                "goals": len(state["goals"]),
                "checkins": len(state["checkins"]),
                "redemptions": len(state["redemptions"]),
            }
            state.clear()
            state.update(self.repository.empty_state())
            return counts, True

        return self.repository.mutate(mutation)


def daily_review_message(completed: int, total: int, missed: List[Dict[str, Any]], points: int) -> str:
    names = [str(item.get("title", "")) for item in missed]
    return DemonSlayerService._review_message("daily", completed, total, points, names)


def weekly_review_message(completed: int, total: int, points: int) -> str:
    return DemonSlayerService._review_message("weekly", completed, total, points, [])


__all__ = [
    "CADENCE_META",
    "CATEGORY_META",
    "CATEGORY_RULES",
    "DAILY_POINTS",
    "DEFAULT_WISHES",
    "DemonSlayerService",
    "MONTHLY_POINTS",
    "PERFECT_DAY_BONUS",
    "PERFECT_MONTH_BONUS",
    "PERFECT_WEEK_BONUS",
    "PERFECT_YEAR_BONUS",
    "WEEKLY_POINTS",
    "YEARLY_POINTS",
    "classify_goal",
    "daily_review_message",
    "infer_cadence",
    "normalize_day",
    "parse_day",
    "today_key",
    "week_start_for",
    "weekly_review_message",
]
