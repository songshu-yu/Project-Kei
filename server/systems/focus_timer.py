"""Compatibility imports for the modular focus implementation."""

from features.focus.models import TimerResult
from features.focus.repository import DEFAULT_STORE, FocusRepository
from features.focus.service import (
    FOCUS_MODES,
    find_session,
    format_seconds,
    get_status,
    mode_config,
    now_local,
    parse_time,
    refresh_active,
    reset,
    result_from_session,
    seconds_between,
    start_timer,
    stop_timer,
)

DATA_DIR = DEFAULT_STORE.parent
FocusTimerStore = FocusRepository

__all__ = [
    "DATA_DIR",
    "DEFAULT_STORE",
    "FOCUS_MODES",
    "FocusTimerStore",
    "TimerResult",
    "find_session",
    "format_seconds",
    "get_status",
    "mode_config",
    "now_local",
    "parse_time",
    "refresh_active",
    "reset",
    "result_from_session",
    "seconds_between",
    "start_timer",
    "stop_timer",
]
