"""Pure paper normalization, author matching, windowing, and deduplication."""
from __future__ import annotations

import hashlib
import re
import unicodedata
from datetime import date, datetime, time, timedelta, timezone
from typing import Iterable, Mapping, Optional, Sequence
from urllib.parse import unquote, urlsplit

try:
    from zoneinfo import ZoneInfo

    def _timezone(name: str):
        return ZoneInfo(name)

    def _localize(value: datetime, timezone_name: str) -> datetime:
        return value.replace(tzinfo=ZoneInfo(timezone_name))

except ImportError:  # Project Kei currently supports Python 3.8.
    import pytz

    def _timezone(name: str):
        return pytz.timezone(name)

    def _localize(value: datetime, timezone_name: str) -> datetime:
        return pytz.timezone(timezone_name).localize(value)

from core.intel_contracts import (
    PUBLIC_SOURCE_IDS,
    CollectRequest,
    IntelItem,
    normalize_url,
)


PAPER_SOURCE_IDS = ("arxiv", "crossref", "semantic")
AUTHOR_CONFIG_KEYS = (
    "paper_priority_authors",
    "paper_secondary_authors",
    "paper_ai_authors",
)
_DOI_RE = re.compile(r"10\.\d{4,9}/[-._;()/:a-z0-9]+", re.IGNORECASE)
_ARXIV_ID_RE = re.compile(
    r"(?:arxiv:|/abs/|/pdf/)(?P<identifier>(?:[a-z-]+(?:\.[a-z-]+)?/\d{7}|\d{4}\.\d{4,5}))(?:v\d+)?(?:\.pdf)?$",
    re.IGNORECASE,
)


def _text(value: object) -> str:
    return " ".join(str(value or "").split())


def _ascii_name(value: object) -> str:
    normalized = unicodedata.normalize("NFKD", _text(value).casefold())
    return "".join(character for character in normalized if not unicodedata.combining(character))


def _name_tokens(value: object) -> tuple[str, ...]:
    return tuple(re.findall(r"[^\W_]+", _ascii_name(value), flags=re.UNICODE))


def normalize_author_name(value: object) -> str:
    """Normalize without guessing name order or exposing the original target."""
    return " ".join(_name_tokens(value))


def _name_forms(value: object) -> set[tuple[str, ...]]:
    tokens = _name_tokens(value)
    if not tokens:
        return set()
    forms = {tokens}
    raw = _text(value)
    if "," in raw and len(tokens) > 1:
        family_size = len(_name_tokens(raw.split(",", 1)[0]))
        if family_size:
            forms.add(tokens[family_size:] + tokens[:family_size])
    if len(tokens) > 1:
        forms.add((tokens[-1], *tokens[:-1]))
    return forms


def _given_tokens_match(left: Sequence[str], right: Sequence[str]) -> bool:
    if len(left) != len(right):
        return False
    return all(a == b or (len(a) == 1 and b.startswith(a)) or (len(b) == 1 and a.startswith(b)) for a, b in zip(left, right))


def author_name_matches(target_name: object, candidate_name: object) -> bool:
    """Match full names and initials while requiring an exact family-name token."""
    target_forms = _name_forms(target_name)
    candidate_forms = _name_forms(candidate_name)
    if not target_forms or not candidate_forms:
        return False
    for target in target_forms:
        for candidate in candidate_forms:
            if len(target) == len(candidate) == 1:
                if target[0] == candidate[0]:
                    return True
                continue
            if len(target) != len(candidate) or target[-1] != candidate[-1]:
                continue
            if _given_tokens_match(target[:-1], candidate[:-1]):
                return True
    return False


def authors_from_snapshot(snapshot: Mapping[str, object]) -> tuple[str, ...]:
    """Read only the frozen non-secret author-list keys, preserving order."""
    result: list[str] = []
    seen: set[str] = set()
    for key in AUTHOR_CONFIG_KEYS:
        raw_values = snapshot.get(key, ())
        if not isinstance(raw_values, (list, tuple)):
            continue
        for raw in raw_values:
            value = _text(raw)[:300]
            normalized = normalize_author_name(value)
            if value and normalized and normalized not in seen:
                seen.add(normalized)
                result.append(value)
    return tuple(result)


def covered_authors(items: Iterable[IntelItem], authors: Iterable[str]) -> set[str]:
    """Return normalized target names represented by item author metadata."""
    targets = {normalize_author_name(author): author for author in authors if normalize_author_name(author)}
    covered: set[str] = set()
    for item in items:
        metadata_authors = item.metadata.get("authors", ())
        candidates = list(metadata_authors) if isinstance(metadata_authors, list) else []
        if item.author:
            candidates.extend(part.strip() for part in item.author.split(",") if part.strip())
        for normalized, target in targets.items():
            if normalized in covered:
                continue
            if any(author_name_matches(target, candidate) for candidate in candidates):
                covered.add(normalized)
    return covered


def normalize_doi(value: object) -> str:
    text = unquote(_text(value)).casefold()
    for prefix in ("https://doi.org/", "http://doi.org/", "http://dx.doi.org/", "doi:"):
        if text.startswith(prefix):
            text = text[len(prefix) :]
            break
    match = _DOI_RE.search(text)
    return match.group(0).rstrip(".>") if match else ""


def arxiv_identifier(value: object) -> str:
    text = _text(value).casefold().split("?", 1)[0].rstrip("/")
    match = _ARXIV_ID_RE.search(text)
    return match.group("identifier") if match else ""


def normalize_paper_title(value: object) -> str:
    text = unicodedata.normalize("NFKC", _text(value).casefold())
    return " ".join(re.findall(r"[^\W_]+", text, flags=re.UNICODE))


def paper_identity_key(item: IntelItem) -> tuple[str, str]:
    doi = normalize_doi(item.metadata.get("doi", "")) or normalize_doi(item.url)
    if doi:
        return "doi", doi
    arxiv_id = arxiv_identifier(item.metadata.get("arxiv_id", "")) or arxiv_identifier(item.url)
    if arxiv_id:
        return "arxiv", arxiv_id
    url = normalize_url(item.url)
    if url:
        return "url", url.casefold()
    return "title", normalize_paper_title(item.title)


def parse_publication(value: object) -> tuple[Optional[datetime], str]:
    text_value = _text(value)
    if not text_value:
        return None, ""
    try:
        if re.fullmatch(r"\d{4}", text_value):
            return datetime(int(text_value), 1, 1, tzinfo=timezone.utc), "year"
        if re.fullmatch(r"\d{4}-\d{2}", text_value):
            parsed = datetime.strptime(text_value, "%Y-%m").replace(tzinfo=timezone.utc)
            return parsed, "month"
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", text_value):
            parsed = datetime.strptime(text_value, "%Y-%m-%d").replace(tzinfo=timezone.utc)
            return parsed, "day"
        parsed = datetime.fromisoformat(text_value.replace("Z", "+00:00"))
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            return None, ""
        return parsed.astimezone(timezone.utc), "second"
    except (TypeError, ValueError):
        return None, ""


def publication_in_window(value: object, request: CollectRequest, now: datetime) -> bool:
    """Apply the request window without turning imprecise old dates into recent facts."""
    published, precision = parse_publication(value)
    if published is None:
        return False
    local_zone = _timezone(request.timezone)
    current = now.astimezone(timezone.utc)
    if request.local_date == current.astimezone(local_zone).date():
        end = current
    else:
        end = _localize(datetime.combine(request.local_date + timedelta(days=1), time.min), request.timezone).astimezone(timezone.utc)
    cutoff = end - timedelta(hours=request.lookback)
    if precision == "second":
        return cutoff <= published <= end + timedelta(minutes=5)
    local_day = published.astimezone(local_zone).date()
    if precision == "day":
        return cutoff.astimezone(local_zone).date() <= local_day <= end.astimezone(local_zone).date()
    if precision == "month":
        return (local_day.year, local_day.month) in {
            (cutoff.astimezone(local_zone).year, cutoff.astimezone(local_zone).month),
            (end.astimezone(local_zone).year, end.astimezone(local_zone).month),
        }
    return request.lookback >= 24 * 365 and cutoff.year <= local_day.year <= end.year


def publication_rfc3339(value: object) -> tuple[str, str]:
    parsed, precision = parse_publication(value)
    if parsed is None:
        return "", ""
    return parsed.isoformat(timespec="seconds").replace("+00:00", "Z"), precision


def _paper_keys(item: IntelItem) -> tuple[tuple[str, str], ...]:
    keys: list[tuple[str, str]] = []
    doi = normalize_doi(item.metadata.get("doi", "")) or normalize_doi(item.url)
    if doi:
        keys.append(("doi", doi))
    arxiv_id = arxiv_identifier(item.metadata.get("arxiv_id", "")) or arxiv_identifier(item.url)
    if arxiv_id:
        keys.append(("arxiv", arxiv_id))
    url = normalize_url(item.url)
    if url:
        keys.append(("url", url.casefold()))
    title = normalize_paper_title(item.title)
    if title:
        keys.append(("title", title))
    return tuple(keys) or (("stable", item.stable_id),)


def _source_priority(source_id: str) -> tuple[int, str]:
    try:
        return PUBLIC_SOURCE_IDS.index(source_id), source_id
    except ValueError:
        return len(PUBLIC_SOURCE_IDS), source_id


def _merge_group(items: Sequence[IntelItem]) -> IntelItem:
    ordered = sorted(items, key=lambda item: (_source_priority(item.source_id), item.stable_id))
    sources = sorted({item.source_id for item in items}, key=_source_priority)
    canonical = ordered[0]
    all_keys = sorted({key for item in items for key in _paper_keys(item)})
    strongest = next((key for kind in ("doi", "arxiv", "url", "title", "stable") for key in all_keys if key[0] == kind), all_keys[0])
    digest = hashlib.sha256(f"{strongest[0]}\x1f{strongest[1]}".encode("utf-8")).hexdigest()[:32]
    metadata: dict[str, object] = {}
    for item in ordered:
        for name, value in item.metadata.items():
            if name not in metadata or metadata[name] in ("", None, []):
                metadata[name] = value
    metadata["discovery_sources"] = sources
    metadata["alternate_stable_ids"] = sorted({item.stable_id for item in items})[:20]
    merged_authors: list[str] = []
    merged_matches: list[str] = []
    for item in ordered:
        for name, target in (("authors", merged_authors), ("matched_authors", merged_matches)):
            values = item.metadata.get(name, ())
            if not isinstance(values, list):
                continue
            for value in values:
                text_value = _text(value)[:300]
                if text_value and text_value not in target:
                    target.append(text_value)
    if merged_authors:
        metadata["authors"] = merged_authors[:50]
    if merged_matches:
        metadata["matched_authors"] = merged_matches[:50]
    dois = sorted({doi for item in items if (doi := normalize_doi(item.metadata.get("doi", "")) or normalize_doi(item.url))})
    if dois:
        metadata["doi"] = dois[0]
    summaries = sorted((item.summary for item in items if item.summary), key=lambda value: (len(value), value))
    titles = sorted((item.title for item in items if item.title), key=lambda value: (len(value), value.casefold()))
    authors = sorted((item.author for item in items if item.author), key=lambda value: (len(value), value.casefold()))
    published = sorted(item.published_at for item in items if item.published_at)
    urls = [item.url for item in ordered if item.url]
    fetched = max(item.fetched_at for item in items)
    return IntelItem(
        stable_id=f"shared:{digest}" if len(sources) > 1 else canonical.stable_id,
        source_id=canonical.source_id,
        category="papers",
        title=titles[-1] if titles else canonical.title,
        summary=summaries[-1] if summaries else "",
        url=urls[0] if urls else "",
        author=authors[-1] if authors else "",
        published_at=published[0] if published else "",
        fetched_at=fetched,
        metadata=metadata,
    )


def deduplicate_paper_items(items: Iterable[IntelItem]) -> tuple[IntelItem, ...]:
    """Deduplicate transitively by DOI, arXiv ID, normalized URL, then title."""
    values = [item for item in items if item.category == "papers" and item.source_id in PAPER_SOURCE_IDS]
    if not values:
        return ()
    parents = list(range(len(values)))

    def find(index: int) -> int:
        while parents[index] != index:
            parents[index] = parents[parents[index]]
            index = parents[index]
        return index

    def union(left: int, right: int) -> None:
        left_root, right_root = find(left), find(right)
        if left_root != right_root:
            parents[max(left_root, right_root)] = min(left_root, right_root)

    owners: dict[tuple[str, str], int] = {}
    for index, item in enumerate(values):
        for key in _paper_keys(item):
            if key in owners:
                union(index, owners[key])
            else:
                owners[key] = index
    groups: dict[int, list[IntelItem]] = {}
    for index, item in enumerate(values):
        groups.setdefault(find(index), []).append(item)
    merged = [_merge_group(group) for _, group in sorted(groups.items())]

    def sort_key(item: IntelItem):
        published, _precision = parse_publication(item.published_at)
        stamp = published.timestamp() if published is not None else float("-inf")
        return -stamp, item.stable_id

    return tuple(sorted(merged, key=sort_key))


def request_with_authors(request: CollectRequest, authors: Iterable[str]) -> CollectRequest:
    snapshot = dict(request.source_config_snapshot)
    for key in AUTHOR_CONFIG_KEYS:
        snapshot[key] = []
    snapshot[AUTHOR_CONFIG_KEYS[0]] = list(authors)
    return CollectRequest(
        local_date=request.local_date,
        timezone=request.timezone,
        source_ids=request.source_ids,
        refresh=request.refresh,
        lookback=request.lookback,
        source_config_snapshot=snapshot,
        contract_version=request.contract_version,
    )


__all__ = [
    "AUTHOR_CONFIG_KEYS",
    "PAPER_SOURCE_IDS",
    "arxiv_identifier",
    "author_name_matches",
    "authors_from_snapshot",
    "covered_authors",
    "deduplicate_paper_items",
    "normalize_author_name",
    "normalize_doi",
    "normalize_paper_title",
    "paper_identity_key",
    "parse_publication",
    "publication_in_window",
    "publication_rfc3339",
    "request_with_authors",
]
