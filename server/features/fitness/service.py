"""Daily fitness check-in, streak and six-day reward rules."""

from __future__ import annotations

import re
from datetime import date, datetime, timedelta
from typing import Any, Callable, Dict, Iterable, List, Optional, Tuple

from .models import FitnessCheckinResult
from .repository import FitnessRepository, FitnessStateError


REWARD_STREAK_DAYS = 6
MAX_NOTE_LENGTH = 500
_DAY_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}$")

KEI_REWARDS = [
    "连续 6 天都坚持健身了，真的很厉害。今天请认真奖励自己：去完成一件你喜欢的事，我会站在你这边。",
    "第 6 天达成。不是一时兴起，是你真的把自己照顾起来了。今天允许自己去做一件喜欢的事，这是 Kei 给你的正式奖励。",
    "你已经连续 6 天没有放弃健身了。辛苦了，也很漂亮。现在去做一件让自己开心的事吧，这是你应得的。",
]


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


def normalize_day(day: Optional[str], *, clock: Callable[[], date] = date.today) -> str:
    if day is None or day == "":
        return clock().isoformat()
    return parse_day(day).isoformat()


def sorted_days(checkins: Iterable[Dict[str, Any]]) -> List[str]:
    days = []
    for item in checkins:
        value = item.get("date")
        if not isinstance(value, str):
            continue
        try:
            days.append(parse_day(value).isoformat())
        except ValueError:
            continue
    return sorted(set(days))


def streak_for_day(days: Iterable[str], target_day: str) -> int:
    day_set = set(days)
    current = parse_day(target_day)
    streak = 0
    while current.isoformat() in day_set:
        streak += 1
        current -= timedelta(days=1)
    return streak


def reward_key_for_streak(target_day: str, streak: int) -> str:
    block = max((streak - 1) // REWARD_STREAK_DAYS, 0)
    return f"{target_day}:{block}"


def choose_reward(streak: int) -> str:
    index = ((streak // REWARD_STREAK_DAYS) - 1) % len(KEI_REWARDS)
    return KEI_REWARDS[index]


def next_reward_in(streak: int) -> int:
    remainder = streak % REWARD_STREAK_DAYS
    return REWARD_STREAK_DAYS if remainder == 0 else REWARD_STREAK_DAYS - remainder


def _unique_rewards(rewards: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    unique: List[Dict[str, Any]] = []
    seen = set()
    for reward in rewards:
        key = reward["key"]
        try:
            parse_day(reward["date"])
        except ValueError as exc:
            raise FitnessStateError("fitness reward date is invalid") from exc
        streak = reward["streak"]
        if streak % REWARD_STREAK_DAYS != 0:
            raise FitnessStateError("fitness reward milestone is invalid")
        if key != reward_key_for_streak(reward["date"], streak):
            raise FitnessStateError("fitness reward key does not match its milestone")
        if reward["text"] != choose_reward(streak):
            raise FitnessStateError("fitness reward text does not match its milestone")
        if key in seen:
            continue
        seen.add(key)
        unique.append(dict(reward))
    return unique


def _recent_unique_rewards(rewards: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return _unique_rewards(rewards)[-10:]


class FitnessService:
    def __init__(
        self,
        repository: FitnessRepository,
        *,
        clock: Callable[[], date] = date.today,
        timestamp: Callable[[], datetime] = datetime.now,
    ):
        self.repository = repository
        self.clock = clock
        self.timestamp = timestamp

    def _normalize_day(self, day: Optional[str]) -> str:
        return normalize_day(day, clock=self.clock)

    @staticmethod
    def _normalize_note(note: str) -> str:
        if not isinstance(note, str):
            raise ValueError("note must be text")
        value = note.strip()
        if len(value) > MAX_NOTE_LENGTH:
            raise ValueError(f"note must be at most {MAX_NOTE_LENGTH} characters")
        return value

    def get_status(self, day: Optional[str] = None) -> Dict[str, Any]:
        target_day = self._normalize_day(day)
        state = self.repository.load()
        days = sorted_days(state["checkins"])
        streak = streak_for_day(days, target_day)
        return {
            "date": target_day,
            "checked_today": target_day in set(days),
            "streak": streak,
            "total_checkins": len(days),
            "next_reward_in": next_reward_in(streak),
            "reward_streak_days": REWARD_STREAK_DAYS,
            "recent_checkins": days[-14:],
            "rewards": _recent_unique_rewards(state["rewards"]),
        }

    def check_in(self, day: Optional[str] = None, note: str = "") -> FitnessCheckinResult:
        target_day = self._normalize_day(day)
        normalized_note = self._normalize_note(note)

        def mutation(state: Dict[str, Any]) -> Tuple[FitnessCheckinResult, bool]:
            validated_rewards = _unique_rewards(state["rewards"])
            days = sorted_days(state["checkins"])
            already_checked_in = target_day in set(days)
            changed = False
            if not already_checked_in:
                state["checkins"].append({
                    "date": target_day,
                    "note": normalized_note,
                    "created_at": self.timestamp().isoformat(timespec="seconds"),
                })
                days = sorted_days(state["checkins"])
                changed = True

            streak = streak_for_day(days, target_day)
            reward_unlocked = False
            reward_text = ""
            if streak > 0 and streak % REWARD_STREAK_DAYS == 0:
                reward_key = reward_key_for_streak(target_day, streak)
                known_keys = {reward["key"] for reward in validated_rewards}
                if reward_key not in known_keys:
                    reward_unlocked = True
                    reward_text = choose_reward(streak)
                    state["rewards"].append({
                        "key": reward_key,
                        "date": target_day,
                        "streak": streak,
                        "text": reward_text,
                        "created_at": self.timestamp().isoformat(timespec="seconds"),
                    })
                    changed = True

            return FitnessCheckinResult(
                checked_in=not already_checked_in,
                already_checked_in=already_checked_in,
                date=target_day,
                streak=streak,
                total_checkins=len(days),
                reward_unlocked=reward_unlocked,
                reward_text=reward_text,
                next_reward_in=next_reward_in(streak),
            ), changed

        return self.repository.mutate(mutation)

    def reset(self) -> Tuple[int, int]:
        def mutation(state: Dict[str, Any]) -> Tuple[Tuple[int, int], bool]:
            counts = (len(sorted_days(state["checkins"])), len(_unique_rewards(state["rewards"])))
            state.clear()
            state.update(self.repository.empty_state())
            return counts, True

        return self.repository.mutate(mutation)


__all__ = [
    "FitnessService",
    "KEI_REWARDS",
    "MAX_NOTE_LENGTH",
    "REWARD_STREAK_DAYS",
    "choose_reward",
    "next_reward_in",
    "normalize_day",
    "parse_day",
    "reward_key_for_streak",
    "sorted_days",
    "streak_for_day",
    "today_key",
]
