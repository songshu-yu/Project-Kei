"""Compatibility exports for the modular PK-160 relationship service."""

from features.affection_memory.compatibility import (
    AffectionResult,
    AffectionStore,
    EVENTS,
    LEVELS,
    STAT_LIMITS,
    VOICE_CUES,
    choose_event,
    choose_response,
    clamp,
    event_matches_context,
    get_status,
    level_for_affection,
    public_stats,
    reset,
    strip_choice_effects,
    trigger_event,
)
from features.affection_memory.repository import DEFAULT_RELATIONSHIP_PATH as DEFAULT_STORE

DATA_DIR = DEFAULT_STORE.parent

__all__ = [
    "AffectionResult",
    "AffectionStore",
    "DATA_DIR",
    "DEFAULT_STORE",
    "EVENTS",
    "LEVELS",
    "STAT_LIMITS",
    "VOICE_CUES",
    "choose_event",
    "choose_response",
    "clamp",
    "event_matches_context",
    "get_status",
    "level_for_affection",
    "public_stats",
    "reset",
    "strip_choice_effects",
    "trigger_event",
]
