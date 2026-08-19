"""Bounded, dependency-free RSS 2.x and Atom 1.0 parsing helpers."""

from __future__ import annotations

import html
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from html.parser import HTMLParser
from typing import Iterable, Optional, Sequence
from urllib.parse import urljoin

from core.intel_contracts import localize

from .models import RSSFeedEntry


_FORBIDDEN_XML_RE = re.compile(br"<!\s*(?:DOCTYPE|ENTITY)\b", re.IGNORECASE)
_WHITESPACE_RE = re.compile(r"\s+")


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts = []

    def handle_data(self, data: str) -> None:
        if data:
            self.parts.append(data)


def _local_name(tag: object) -> str:
    return str(tag or "").rsplit("}", 1)[-1].casefold()


def _text(element: Optional[ET.Element]) -> str:
    if element is None:
        return ""
    return _WHITESPACE_RE.sub(" ", " ".join(element.itertext())).strip()


def _child(element: ET.Element, names: Iterable[str]) -> Optional[ET.Element]:
    wanted = {name.casefold() for name in names}
    for candidate in list(element):
        if _local_name(candidate.tag) in wanted:
            return candidate
    return None


def _child_text(element: ET.Element, names: Iterable[str]) -> str:
    return _text(_child(element, names))


def _plain_text(value: object, *, limit: int) -> str:
    raw = html.unescape(str(value or ""))
    extractor = _TextExtractor()
    try:
        extractor.feed(raw)
        extractor.close()
        text = " ".join(extractor.parts)
    except Exception:
        text = raw
    return _WHITESPACE_RE.sub(" ", text).strip()[:limit]


def _entry_link(element: ET.Element, feed_url: str) -> str:
    candidates = []
    for child in list(element):
        if _local_name(child.tag) != "link":
            continue
        href = str(child.attrib.get("href", "") or "").strip()
        rel = str(child.attrib.get("rel", "") or "").strip().casefold()
        if href:
            candidates.append((0 if rel in {"", "alternate"} else 1, href))
        else:
            value = _text(child)
            if value:
                candidates.append((0, value))
    if not candidates:
        guid = _child(element, ("guid",))
        if guid is not None and str(guid.attrib.get("isPermaLink", "true")).casefold() != "false":
            value = _text(guid)
            if value.startswith(("http://", "https://")):
                candidates.append((0, value))
    if not candidates:
        return ""
    candidates.sort(key=lambda item: item[0])
    return urljoin(feed_url, candidates[0][1])


def _entry_author(element: ET.Element) -> str:
    author = _child(element, ("author", "creator"))
    if author is None:
        return ""
    name = _child_text(author, ("name",))
    return name or _text(author)


def parse_feed(xml_bytes: bytes, feed_url: str, *, max_entries: int = 30) -> Sequence[RSSFeedEntry]:
    """Parse one already-fetched response without resolving external entities."""
    if not isinstance(xml_bytes, bytes):
        raise TypeError("feed payload must be bytes")
    if _FORBIDDEN_XML_RE.search(xml_bytes[:4096]):
        raise ValueError("unsafe XML declaration")
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError as exc:
        raise ValueError("invalid feed XML") from exc

    root_name = _local_name(root.tag)
    if root_name not in {"rss", "rdf", "rdf:rdf", "feed"}:
        raise ValueError("unsupported feed document")

    channel = next((item for item in root.iter() if _local_name(item.tag) == "channel"), None)
    feed_title = _child_text(channel if channel is not None else root, ("title",))
    entry_name = "entry" if root_name == "feed" else "item"
    elements = [item for item in root.iter() if _local_name(item.tag) == entry_name]
    entries = []
    for element in elements[: max(0, int(max_entries))]:
        title = _plain_text(_child_text(element, ("title",)), limit=1000)
        if not title:
            continue
        summary = _plain_text(
            _child_text(element, ("description", "summary", "content", "encoded")),
            limit=4000,
        )
        entries.append(
            RSSFeedEntry(
                feed_title=_plain_text(feed_title, limit=300),
                title=title,
                summary=summary,
                url=_entry_link(element, feed_url),
                author=_plain_text(_entry_author(element), limit=300),
                published_raw=_child_text(element, ("pubdate", "published", "updated", "date"))[:200],
                upstream_id=_child_text(element, ("guid", "id"))[:1000],
            )
        )
    return tuple(entries)


def parse_published(value: object, timezone_name: str) -> Optional[datetime]:
    """Return an aware UTC timestamp, or ``None`` for missing/invalid input."""
    text = str(value or "").strip()
    if not text:
        return None
    parsed = None
    try:
        parsed = parsedate_to_datetime(text)
    except (TypeError, ValueError, OverflowError):
        pass
    if parsed is None:
        normalized = text[:-1] + "+00:00" if text.endswith(("Z", "z")) else text
        try:
            parsed = datetime.fromisoformat(normalized)
        except ValueError:
            return None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        try:
            parsed = localize(parsed, timezone_name)
        except (KeyError, ValueError, OverflowError):
            return None
    return parsed.astimezone(timezone.utc)


__all__ = ["parse_feed", "parse_published"]
