"""Legacy fitness imports backed by :mod:`features.fitness`."""

from features.fitness import (
    DEFAULT_STORE,
    KEI_REWARDS,
    REWARD_STREAK_DAYS,
    FitnessCheckinResult as CheckinResult,
    FitnessCheckinStore,
    check_in,
    get_status,
    reset,
)
from features.fitness.service import (
    choose_reward,
    next_reward_in,
    normalize_day,
    parse_day,
    reward_key_for_streak,
    sorted_days,
    streak_for_day,
    today_key,
)

__all__ = [
    "CheckinResult",
    "DEFAULT_STORE",
    "FitnessCheckinStore",
    "KEI_REWARDS",
    "REWARD_STREAK_DAYS",
    "check_in",
    "choose_reward",
    "get_status",
    "next_reward_in",
    "normalize_day",
    "parse_day",
    "reset",
    "reward_key_for_streak",
    "sorted_days",
    "streak_for_day",
    "today_key",
]
