"""Public PK-134 RSS/Atom source boundary."""

from .collector import RSSIntelCollector, SOURCE_ID
from .http_client import (
    FeedFetchError,
    FeedURLPolicy,
    Resolver,
    normalize_entry_url,
    normalize_feed_url,
)
from .module import SOURCE_CONFIG_PROVIDER_STATE, register, unregister
from .models import RSSFeedEntry
from .parser import parse_feed, parse_published
from .provider import RSSIntelCollectorProvider, RSSIntelSourceConfig

__all__ = [
    "FeedFetchError",
    "FeedURLPolicy",
    "Resolver",
    "RSSFeedEntry",
    "RSSIntelCollector",
    "RSSIntelCollectorProvider",
    "RSSIntelSourceConfig",
    "SOURCE_ID",
    "SOURCE_CONFIG_PROVIDER_STATE",
    "normalize_entry_url",
    "normalize_feed_url",
    "parse_feed",
    "parse_published",
    "register",
    "unregister",
]
