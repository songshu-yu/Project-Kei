"""Legacy import seam for the modular PK-110 daily briefing boundary."""

from features.daily_briefing.legacy_adapter import (
    BriefingItem,
    BriefingVoiceProvider,
    DailyBriefingResult,
    DailyBriefingService,
)

__all__ = [
    "BriefingItem",
    "BriefingVoiceProvider",
    "DailyBriefingResult",
    "DailyBriefingService",
]
