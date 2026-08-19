"""Calendar, recurring-event and 10,000-hour mastery rules."""

from __future__ import annotations

import hashlib
import math
import re
from datetime import date, datetime, timedelta
from typing import Any, Callable, Dict, List, Optional

from .models import CalendarEvent
from .repository import CalendarMemoStore, CalendarStateError


MASTERY_TARGET_HOURS = 10000.0
MASTERY_REALMS = [
    (0.0, "凡人"),
    (5.0, "练气"),
    (15.0, "筑基"),
    (35.0, "结丹"),
    (70.0, "金丹"),
    (120.0, "元婴"),
    (200.0, "化神"),
    (350.0, "炼虚"),
    (600.0, "合体"),
    (1000.0, "大乘"),
    (1800.0, "渡劫"),
    (3000.0, "地仙"),
    (5000.0, "天仙"),
    (7500.0, "真仙"),
    (10000.0, "飞升"),
]
MASTERY_STAGES = ["一重", "二重", "三重", "四重", "五重", "六重", "七重", "八重", "九重", "圆满"]
WEEKDAYS = ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"]
_DAY_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def today_key() -> str:
    return date.today().isoformat()


def parse_day(day: str) -> date:
    value = str(day)
    if not _DAY_PATTERN.fullmatch(value):
        raise ValueError("date must use YYYY-MM-DD")
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError("date must be a valid YYYY-MM-DD") from exc


def normalize_day(day: Optional[str]) -> str:
    return today_key() if day is None else parse_day(day).isoformat()


def _id(prefix: str, *parts: str) -> str:
    raw = ":".join(str(part) for part in parts)
    return f"{prefix}_{hashlib.sha1(raw.encode('utf-8')).hexdigest()[:8]}"


def _occurs_on(event: Dict[str, Any], target: date) -> bool:
    try:
        event_day = parse_day(str(event.get("date", "")))
    except ValueError:
        return False
    if event.get("repeat") == "yearly":
        return (event_day.month, event_day.day) == (target.month, target.day)
    return event_day == target


def _next_occurrence(event: Dict[str, Any], start: date) -> Optional[date]:
    try:
        event_day = parse_day(str(event.get("date", "")))
    except ValueError:
        return None
    if event.get("repeat") != "yearly":
        return event_day if event_day >= start else None
    year = start.year
    while year <= date.max.year:
        try:
            candidate = date(year, event_day.month, event_day.day)
        except ValueError:
            year += 1
            continue
        if candidate >= start:
            return candidate
        year += 1
    return None


def mastery_level(total_hours: float) -> Dict[str, Any]:
    total_hours = float(total_hours)
    if not math.isfinite(total_hours):
        raise ValueError("total hours must be finite")
    total_hours = max(total_hours, 0.0)
    current_index = 0
    for index, realm in enumerate(MASTERY_REALMS):
        if total_hours >= realm[0]:
            current_index = index
    current = MASTERY_REALMS[current_index]
    next_realm = MASTERY_REALMS[current_index + 1] if current_index + 1 < len(MASTERY_REALMS) else None
    if not next_realm:
        return {
            "name": "飞升",
            "realm": "飞升",
            "stage": "圆满",
            "realm_index": current_index,
            "stage_index": len(MASTERY_STAGES) - 1,
            "threshold_hours": current[0],
            "next_name": "",
            "next_realm": "",
            "hours_to_next": 0.0,
            "hours_to_next_realm": 0.0,
            "realm_progress": 100.0,
            "progress_to_10000": 100.0,
        }
    span = max(next_realm[0] - current[0], 1.0)
    progressed = min(max(total_hours - current[0], 0.0), span)
    stage_width = span / len(MASTERY_STAGES)
    stage_index = min(int(progressed // stage_width), len(MASTERY_STAGES) - 1)
    stage = MASTERY_STAGES[stage_index]
    next_stage_boundary = current[0] + min((stage_index + 1) * stage_width, span)
    next_name = f"{current[1]}{MASTERY_STAGES[stage_index + 1]}" if stage_index + 1 < len(MASTERY_STAGES) else next_realm[1]
    return {
        "name": f"{current[1]}{stage}",
        "realm": current[1],
        "stage": stage,
        "realm_index": current_index,
        "stage_index": stage_index,
        "threshold_hours": current[0],
        "next_name": next_name,
        "next_realm": next_realm[1],
        "hours_to_next": round(max(next_stage_boundary - total_hours, 0.0), 2),
        "hours_to_next_realm": round(max(next_realm[0] - total_hours, 0.0), 2),
        "realm_progress": round((progressed / span) * 100, 2),
        "progress_to_10000": round(min(total_hours / MASTERY_TARGET_HOURS, 1.0) * 100, 2),
    }


def skill_status(skill: Dict[str, Any]) -> Dict[str, Any]:
    try:
        total = round(float(skill.get("total_hours", 0.0)), 2)
        level = mastery_level(total)
    except (TypeError, ValueError) as exc:
        raise CalendarStateError("calendar skill totals are invalid") from exc
    return {"id": skill.get("id"), "name": skill.get("name"), "total_hours": total, "level": level}


def practice_message(skill: Dict[str, Any], hours: float) -> str:
    status = skill_status(skill)
    level = status["level"]
    if level["next_name"]:
        return (
            f"{status['name']} 增加 {hours:g} 小时，总计 {status['total_hours']:g} 小时，"
            f"当前 {level['name']}，距离 {level['next_name']} 还差 {level['hours_to_next']:g} 小时。"
        )
    return f"{status['name']} 增加 {hours:g} 小时，已经飞升圆满。哼，真的练到一万小时了。"


def today_message(target: date, events: List[Dict[str, Any]], upcoming: List[Dict[str, Any]], skills: List[Dict[str, Any]]) -> str:
    lines = [f"今天是 {target.isoformat()}，{WEEKDAYS[target.weekday()]}。"]
    if events:
        lines.append(f"今天的备忘：{'、'.join(item.get('title', '') for item in events)}。")
    else:
        lines.append("今天没有特别登记的日子。")
    if upcoming:
        preview = "；".join(f"{item.get('days_left')} 天后：{item.get('title')}" for item in upcoming[:3])
        lines.append(f"接下来一周要注意：{preview}。")
    if skills:
        top = skills[0]
        lines.append(f"熟练度最高的是 {top['name']}，累计 {top['total_hours']:g} 小时，当前 {top['level']['name']}。")
    return "\n".join(lines)


class CalendarService:
    def __init__(
        self,
        repository: CalendarMemoStore,
        *,
        clock: Callable[[], date] = date.today,
        timestamp: Callable[[], datetime] = datetime.now,
    ):
        self.repository = repository
        self.clock = clock
        self.timestamp = timestamp

    def _normalize_day(self, day: Optional[str]) -> str:
        return self.clock().isoformat() if day is None else parse_day(day).isoformat()

    @staticmethod
    def _events_for_target(state: Dict[str, Any], target: date) -> List[Dict[str, Any]]:
        events = []
        for event in state["events"]:
            if _occurs_on(event, target):
                item = dict(event)
                item["occurrence_date"] = target.isoformat()
                events.append(item)
        return sorted(events, key=lambda item: (item["occurrence_date"], str(item.get("title", ""))))

    @staticmethod
    def _upcoming_from_state(state: Dict[str, Any], start: date, days: int) -> List[Dict[str, Any]]:
        if days < 0:
            raise ValueError("days must be zero or greater")
        end = start + timedelta(days=days)
        upcoming = []
        for event in state["events"]:
            occurrence = _next_occurrence(event, start)
            if occurrence and occurrence <= end:
                item = dict(event)
                item["occurrence_date"] = occurrence.isoformat()
                item["days_left"] = (occurrence - start).days
                upcoming.append(item)
        return sorted(upcoming, key=lambda item: (item["occurrence_date"], str(item.get("title", ""))))

    @staticmethod
    def _skill_overview(state: Dict[str, Any]) -> List[Dict[str, Any]]:
        return sorted(
            [skill_status(skill) for skill in state["skills"]],
            key=lambda item: item["total_hours"],
            reverse=True,
        )

    def add_event(self, title: str, day: str, repeat: str = "none", note: str = "", tags: Optional[List[str]] = None) -> Dict[str, Any]:
        event_title = str(title).strip()
        if not event_title:
            raise ValueError("title must not be blank")
        target_day = self._normalize_day(day)
        repeat_value = str(repeat).strip().lower() or "none"
        if repeat_value not in {"none", "yearly"}:
            raise ValueError("repeat must be 'none' or 'yearly'")
        event = CalendarEvent(
            id=_id("event", event_title, target_day, repeat_value),
            title=event_title,
            date=target_day,
            repeat=repeat_value,
            note=str(note).strip(),
            tags=list(tags or []),
        ).to_dict()
        event["created_at"] = self.timestamp().isoformat(timespec="seconds")

        def mutation(state: Dict[str, Any]) -> tuple[Dict[str, Any], bool]:
            known = {item.get("id") for item in state["events"]}
            if event["id"] in known:
                return event, False
            state["events"].append(event)
            return event, True

        return self.repository.mutate(mutation)

    def events_for_day(self, day: Optional[str] = None) -> List[Dict[str, Any]]:
        target = parse_day(self._normalize_day(day))
        return self._events_for_target(self.repository.load(), target)

    def upcoming_events(self, day: Optional[str] = None, days: int = 7) -> List[Dict[str, Any]]:
        start = parse_day(self._normalize_day(day))
        return self._upcoming_from_state(self.repository.load(), start, days)

    def add_practice(self, skill: str, hours: float, day: Optional[str] = None, note: str = "") -> Dict[str, Any]:
        skill_name = str(skill).strip()
        if not skill_name:
            raise ValueError("skill must not be blank")
        amount = float(hours)
        if not math.isfinite(amount) or amount <= 0:
            raise ValueError("hours must be a finite number greater than zero")
        target_day = self._normalize_day(day)
        skill_id = _id("skill", skill_name.lower())
        created_at = self.timestamp().isoformat(timespec="seconds")

        def mutation(state: Dict[str, Any]) -> tuple[Dict[str, Any], bool]:
            existing = next((item for item in state["skills"] if item.get("id") == skill_id), None)
            if existing is None:
                existing = {"id": skill_id, "name": skill_name, "total_hours": 0.0, "created_at": created_at}
                state["skills"].append(existing)
            try:
                current_total = float(existing.get("total_hours", 0.0))
            except (TypeError, ValueError) as exc:
                raise CalendarStateError("calendar skill totals are invalid") from exc
            if not math.isfinite(current_total) or current_total < 0:
                raise CalendarStateError("calendar skill totals are invalid")
            existing["total_hours"] = round(current_total + amount, 2)
            log = {
                "skill_id": skill_id,
                "skill": skill_name,
                "hours": amount,
                "date": target_day,
                "note": str(note).strip(),
                "created_at": created_at,
            }
            state["practice_logs"].append(log)
            return {
                "status": "ok",
                "skill": skill_status(existing),
                "log": log,
                "message": practice_message(existing, amount),
            }, True

        return self.repository.mutate(mutation)

    def skill_overview(self) -> List[Dict[str, Any]]:
        return self._skill_overview(self.repository.load())

    def today_summary(self, day: Optional[str] = None) -> Dict[str, Any]:
        target = parse_day(self._normalize_day(day))
        state = self.repository.load()
        today_events = self._events_for_target(state, target)
        upcoming = [item for item in self._upcoming_from_state(state, target, 7) if item["days_left"] > 0]
        skills = self._skill_overview(state)
        return {
            "date": target.isoformat(),
            "weekday": WEEKDAYS[target.weekday()],
            "today_events": today_events,
            "upcoming_events": upcoming[:5],
            "skills": skills,
            "message": today_message(target, today_events, upcoming[:5], skills[:3]),
        }

    def get_status(self, day: Optional[str] = None) -> Dict[str, Any]:
        target = parse_day(self._normalize_day(day))
        state = self.repository.load()
        today_events = self._events_for_target(state, target)
        upcoming = [item for item in self._upcoming_from_state(state, target, 7) if item["days_left"] > 0]
        skills = self._skill_overview(state)
        summary = {
            "date": target.isoformat(),
            "weekday": WEEKDAYS[target.weekday()],
            "today_events": today_events,
            "upcoming_events": upcoming[:5],
            "skills": skills,
            "message": today_message(target, today_events, upcoming[:5], skills[:3]),
        }
        events = sorted(state["events"], key=lambda item: (str(item.get("date", "")), str(item.get("title", ""))))
        return {
            "date": summary["date"],
            "weekday": summary["weekday"],
            "events_count": len(state["events"]),
            "skills_count": len(state["skills"]),
            "today": summary,
            "events": events,
            "skills": skills,
            "recent_practice_logs": state["practice_logs"][-20:],
        }

    def reset(self) -> Dict[str, int]:
        def mutation(state: Dict[str, Any]) -> tuple[Dict[str, int], bool]:
            counts = {key: len(state[key]) for key in ("events", "skills", "practice_logs")}
            state.clear()
            state.update(self.repository.empty_state())
            return counts, True

        return self.repository.mutate(mutation)


_DEFAULT_SERVICE = CalendarService(CalendarMemoStore())


def get_default_service() -> CalendarService:
    return _DEFAULT_SERVICE


def _service(store: Optional[CalendarMemoStore]) -> CalendarService:
    return CalendarService(store) if store is not None else _DEFAULT_SERVICE


def add_event(title: str, day: str, repeat: str = "none", note: str = "", tags: Optional[List[str]] = None, store: Optional[CalendarMemoStore] = None) -> Dict[str, Any]:
    return _service(store).add_event(title, day, repeat=repeat, note=note, tags=tags)


def events_for_day(day: Optional[str] = None, store: Optional[CalendarMemoStore] = None) -> List[Dict[str, Any]]:
    return _service(store).events_for_day(day)


def upcoming_events(day: Optional[str] = None, days: int = 7, store: Optional[CalendarMemoStore] = None) -> List[Dict[str, Any]]:
    return _service(store).upcoming_events(day, days)


def add_practice(skill: str, hours: float, day: Optional[str] = None, note: str = "", store: Optional[CalendarMemoStore] = None) -> Dict[str, Any]:
    return _service(store).add_practice(skill, hours, day=day, note=note)


def skill_overview(store: Optional[CalendarMemoStore] = None) -> List[Dict[str, Any]]:
    return _service(store).skill_overview()


def today_summary(day: Optional[str] = None, store: Optional[CalendarMemoStore] = None) -> Dict[str, Any]:
    return _service(store).today_summary(day)


def get_status(day: Optional[str] = None, store: Optional[CalendarMemoStore] = None) -> Dict[str, Any]:
    return _service(store).get_status(day)


def reset(store: Optional[CalendarMemoStore] = None) -> Dict[str, int]:
    return _service(store).reset()


__all__ = [
    "CalendarService",
    "MASTERY_REALMS",
    "MASTERY_STAGES",
    "MASTERY_TARGET_HOURS",
    "WEEKDAYS",
    "add_event",
    "add_practice",
    "events_for_day",
    "get_default_service",
    "get_status",
    "mastery_level",
    "normalize_day",
    "parse_day",
    "practice_message",
    "reset",
    "skill_overview",
    "skill_status",
    "today_key",
    "today_message",
    "today_summary",
    "upcoming_events",
]
