"""Source-owned value objects for generic RSS and Atom feeds."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RSSFeedEntry:
    """An untrusted entry parsed from one bounded feed response."""

    feed_title: str
    title: str
    summary: str = ""
    url: str = ""
    author: str = ""
    published_raw: str = ""
    upstream_id: str = ""


__all__ = ["RSSFeedEntry"]
