"""Legacy import facade for the PK-131 YouTube Collector."""

from features.youtube import (
    CHANNEL_ID_RE,
    FEED_URL,
    NS,
    YouTubeCollector,
    YouTubeResult,
    YouTubeVideo,
    create_collector,
    fetch_youtube,
    is_channel_id,
    parse_youtube_timestamp,
    validate_channel_id,
    youtube_video_stable_id,
)

__all__ = [
    "CHANNEL_ID_RE",
    "FEED_URL",
    "NS",
    "YouTubeCollector",
    "YouTubeResult",
    "YouTubeVideo",
    "create_collector",
    "fetch_youtube",
    "is_channel_id",
    "parse_youtube_timestamp",
    "validate_channel_id",
    "youtube_video_stable_id",
]
