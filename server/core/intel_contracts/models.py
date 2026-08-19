"""Collector 1.0 public data contract owned by Project Kei Core.

The contract version remains ``1.0``. Readers ignore unknown object keys within
the same major version; missing required fields or another major are rejected.
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from enum import Enum
from typing import Any, Dict, Iterable, Mapping, Optional
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from .time import get_timezone


COLLECTOR_CONTRACT_VERSION = "1.0"
PUBLIC_SOURCE_IDS = (
    "twitter",
    "github",
    "bilibili",
    "youtube",
    "money",
    "arxiv",
    "crossref",
    "semantic",
)
PUBLIC_SOURCE_ID_SET = frozenset(PUBLIC_SOURCE_IDS)
_SOURCE_ID_RE = re.compile(r"[a-z][a-z0-9_.-]{0,63}")
_SENSITIVE_NAME_MARKERS = (
    "authorization", "cookie", "credential", "password", "passwd", "secret",
    "session", "signature", "api_key", "apikey", "access_token",
    "refresh_token", "id_token", "token",
)
_SECRET_ASSIGNMENT_RE = re.compile(
    r"(?i)\b(authorization|proxy[-_ ]?authorization|cookie|set[-_ ]?cookie|"
    r"access[-_ ]?token|refresh[-_ ]?token|id[-_ ]?token|token|api[-_ ]?key|apikey|"
    r"secret|password|passwd|session(?:[-_ ]?id)?|credential|signature)"
    r"\s*[:=]\s*(?:bearer\s+)?[^\s,;&]+"
)
_BEARER_SECRET_RE = re.compile(r"(?i)\bbearer\s+[a-z0-9._~+/=-]{6,}")


def _sensitive_name(value: object) -> bool:
    normalized = re.sub(r"[^a-z0-9]+", "_", str(value or "").casefold()).strip("_")
    compact = normalized.replace("_", "")
    return any(
        marker in normalized or marker.replace("_", "") in compact
        for marker in _SENSITIVE_NAME_MARKERS
    )


def sanitize_external_text(
    value: object,
    *,
    limit: int = 4000,
    collapse_whitespace: bool = True,
) -> str:
    """Bound and redact credential-shaped values in untrusted public text."""
    raw = f"<{type(value).__name__}>" if isinstance(value, BaseException) else str(value or "")
    text = " ".join(raw.split()) if collapse_whitespace else raw.strip()
    text = _SECRET_ASSIGNMENT_RE.sub(lambda match: f"{match.group(1)}=<redacted>", text)
    text = _BEARER_SECRET_RE.sub("Bearer <redacted>", text)
    return text[: max(0, int(limit))]


class CoverageStatus(str, Enum):
    COMPLETE = "complete"
    PARTIAL = "partial"
    EMPTY = "empty"
    FAILED = "failed"
    NOT_CONFIGURED = "not_configured"


class CacheStatus(str, Enum):
    HIT = "hit"
    FETCHED = "fetched"
    REFRESHED = "refreshed"
    BYPASS = "bypass"
    UNAVAILABLE = "unavailable"


def ensure_compatible_contract(version: object) -> str:
    value = str(version or "").strip()
    current_major = COLLECTOR_CONTRACT_VERSION.split(".", 1)[0]
    if not value or value.split(".", 1)[0] != current_major:
        raise ValueError("unsupported collector contract version")
    return value


def is_valid_source_id(value: object) -> bool:
    return bool(_SOURCE_ID_RE.fullmatch(str(value or "")))


def normalize_source_ids(values: Optional[Iterable[object]]) -> tuple[str, ...]:
    source = PUBLIC_SOURCE_IDS if values is None else values
    result: list[str] = []
    seen: set[str] = set()
    for raw in source:
        value = str(raw or "").strip().lower()
        if not is_valid_source_id(value):
            raise ValueError(f"invalid source_id: {value or '<empty>'}")
        if value not in seen:
            seen.add(value)
            result.append(value)
    if not result:
        raise ValueError("source_ids cannot be empty")
    return tuple(result)


def normalize_url(value: object) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    if len(text) > 2048:
        text = text[:2048]
    try:
        parsed = urlsplit(text)
    except ValueError:
        return ""
    if (
        parsed.scheme.lower() not in {"http", "https"}
        or not parsed.netloc
        or parsed.username
        or parsed.password
    ):
        return ""
    host = (parsed.hostname or "").lower()
    if not host:
        return ""
    netloc = host
    try:
        if parsed.port:
            netloc = f"{host}:{parsed.port}"
    except ValueError:
        return ""
    try:
        safe_query = urlencode(
            [
                (key, sanitize_external_text(item, limit=2_048, collapse_whitespace=False))
                for key, item in parse_qsl(parsed.query, keep_blank_values=True)
                if not _sensitive_name(key)
            ],
            doseq=True,
        )
    except ValueError:
        safe_query = ""
    return urlunsplit((parsed.scheme.lower(), netloc, parsed.path or "/", safe_query, ""))


def rfc3339(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    value = value.astimezone(timezone.utc)
    return value.isoformat(timespec="seconds").replace("+00:00", "Z")


def aware_timestamp(value: object, *, required: bool = False) -> str:
    text = str(value or "").strip()
    if not text:
        if required:
            raise ValueError("timezone-aware timestamp is required")
        return ""
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("timestamp must be RFC 3339") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("timestamp must include an explicit timezone")
    return rfc3339(parsed)


def stable_item_id(
    source_id: str,
    *,
    upstream_id: object = "",
    url: object = "",
    title: object = "",
    author: object = "",
    published_at: object = "",
) -> str:
    source = normalize_source_ids([source_id])[0]
    identity = str(upstream_id or "").strip() or normalize_url(url)
    if not identity:
        identity = "\x1f".join(
            " ".join(str(value or "").casefold().split())
            for value in (title, author, published_at)
        )
    digest = hashlib.sha256(f"{source}\x1e{identity}".encode("utf-8")).hexdigest()[:32]
    return f"{source}:{digest}"


def json_safe_mapping(value: object, *, max_depth: int = 4) -> Dict[str, Any]:
    """Return a bounded JSON mapping and reject accidental secret fields."""
    if value is None:
        return {}
    if not isinstance(value, Mapping):
        raise ValueError("metadata/config snapshot must be an object")
    blocked = (
        "token", "cookie", "secret", "authorization", "api_key", "apikey",
        "password", "header",
    )

    def clean(node: object, depth: int) -> Any:
        if depth > max_depth:
            return None
        if node is None or isinstance(node, (bool, int, float)):
            return node
        if isinstance(node, str):
            return sanitize_external_text(node, limit=2000)
        if isinstance(node, Mapping):
            result: Dict[str, Any] = {}
            for key, item in list(node.items())[:100]:
                name = str(key)[:120]
                lowered = name.casefold()
                if any(marker in lowered for marker in blocked) or _sensitive_name(name):
                    continue
                result[name] = clean(item, depth + 1)
            return result
        if isinstance(node, (list, tuple)):
            return [clean(item, depth + 1) for item in list(node)[:200]]
        return f"<{type(node).__name__}>"

    cleaned = clean(value, 0)
    json.dumps(cleaned, ensure_ascii=False)
    return cleaned


@dataclass(frozen=True)
class CollectRequest:
    local_date: date
    timezone: str
    source_ids: tuple[str, ...] = field(default_factory=lambda: PUBLIC_SOURCE_IDS)
    refresh: bool = False
    lookback: int = 24
    source_config_snapshot: Mapping[str, Any] = field(default_factory=dict)
    contract_version: str = COLLECTOR_CONTRACT_VERSION

    def __post_init__(self) -> None:
        if not isinstance(self.local_date, date):
            raise ValueError("local_date must be a date")
        if not str(self.timezone or "").strip():
            raise ValueError("timezone is required")
        get_timezone(self.timezone)
        if isinstance(self.lookback, bool) or not 1 <= int(self.lookback) <= 24 * 30:
            raise ValueError("lookback must be between 1 and 720 hours")
        object.__setattr__(self, "source_ids", normalize_source_ids(self.source_ids))
        object.__setattr__(self, "lookback", int(self.lookback))
        object.__setattr__(
            self,
            "source_config_snapshot",
            json_safe_mapping(self.source_config_snapshot),
        )
        object.__setattr__(
            self,
            "contract_version",
            ensure_compatible_contract(self.contract_version),
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "contract_version": self.contract_version,
            "local_date": self.local_date.isoformat(),
            "timezone": self.timezone,
            "source_ids": list(self.source_ids),
            "refresh": self.refresh,
            "lookback": self.lookback,
            "source_config_snapshot": dict(self.source_config_snapshot),
        }


@dataclass(frozen=True)
class IntelItem:
    stable_id: str
    source_id: str
    category: str
    title: str
    fetched_at: str
    summary: str = ""
    url: str = ""
    author: str = ""
    published_at: str = ""
    metadata: Mapping[str, Any] = field(default_factory=dict)
    contract_version: str = COLLECTOR_CONTRACT_VERSION

    def __post_init__(self) -> None:
        source_id = normalize_source_ids([self.source_id])[0]
        stable_id = sanitize_external_text(self.stable_id, limit=160)
        if not stable_id or len(stable_id) > 160:
            raise ValueError("stable_id is required and must not exceed 160 characters")
        category = sanitize_external_text(self.category or "general", limit=80) or "general"
        title = sanitize_external_text(self.title, limit=1000)
        if not title:
            raise ValueError("title is required")
        object.__setattr__(self, "source_id", source_id)
        object.__setattr__(self, "stable_id", stable_id)
        object.__setattr__(self, "category", category)
        object.__setattr__(self, "title", title)
        object.__setattr__(self, "summary", sanitize_external_text(self.summary, limit=4000))
        object.__setattr__(self, "url", normalize_url(self.url))
        object.__setattr__(self, "author", sanitize_external_text(self.author, limit=300))
        object.__setattr__(self, "published_at", aware_timestamp(self.published_at))
        object.__setattr__(self, "fetched_at", aware_timestamp(self.fetched_at, required=True))
        object.__setattr__(self, "metadata", json_safe_mapping(self.metadata))
        object.__setattr__(
            self,
            "contract_version",
            ensure_compatible_contract(self.contract_version),
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "contract_version": self.contract_version,
            "stable_id": self.stable_id,
            "source_id": self.source_id,
            "category": self.category,
            "title": self.title,
            "summary": self.summary,
            "url": self.url,
            "author": self.author,
            "published_at": self.published_at,
            "fetched_at": self.fetched_at,
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "IntelItem":
        ensure_compatible_contract(
            value.get("contract_version", COLLECTOR_CONTRACT_VERSION)
        )
        return cls(
            stable_id=value.get("stable_id", ""),
            source_id=value.get("source_id", ""),
            category=value.get("category", "general"),
            title=value.get("title", ""),
            summary=value.get("summary", ""),
            url=value.get("url", ""),
            author=value.get("author", ""),
            published_at=value.get("published_at", ""),
            fetched_at=value.get("fetched_at", ""),
            metadata=value.get("metadata", {}),
            contract_version=value.get(
                "contract_version",
                COLLECTOR_CONTRACT_VERSION,
            ),
        )


@dataclass(frozen=True)
class SourceCoverage:
    status: CoverageStatus
    item_count: int = 0
    detail: str = ""
    retry_after: Optional[str] = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "status", CoverageStatus(self.status))
        object.__setattr__(self, "item_count", max(0, int(self.item_count)))
        object.__setattr__(
            self,
            "detail",
            sanitize_external_text(self.detail, limit=240),
        )
        object.__setattr__(
            self,
            "retry_after",
            aware_timestamp(self.retry_after) or None,
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "status": self.status.value,
            "item_count": self.item_count,
            "detail": self.detail,
            "retry_after": self.retry_after,
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "SourceCoverage":
        return cls(
            value.get("status", CoverageStatus.FAILED.value),
            value.get("item_count", 0),
            value.get("detail", ""),
            value.get("retry_after"),
        )


@dataclass(frozen=True)
class CollectorResult:
    source_id: str
    items: tuple[IntelItem, ...]
    warnings: tuple[str, ...]
    coverage: SourceCoverage
    fetched_at: str
    retry_after: Optional[str] = None
    cache_status: CacheStatus = CacheStatus.FETCHED
    contract_version: str = COLLECTOR_CONTRACT_VERSION

    def __post_init__(self) -> None:
        source_id = normalize_source_ids([self.source_id])[0]
        items = tuple(self.items)
        if any(item.source_id != source_id for item in items):
            raise ValueError("collector result contains an item for another source")
        warnings = tuple(
            cleaned
            for value in self.warnings
            if (cleaned := sanitize_external_text(value, limit=240))
        )
        coverage = (
            self.coverage
            if isinstance(self.coverage, SourceCoverage)
            else SourceCoverage.from_dict(self.coverage)
        )
        object.__setattr__(self, "source_id", source_id)
        object.__setattr__(self, "items", items)
        object.__setattr__(self, "warnings", warnings)
        object.__setattr__(self, "coverage", coverage)
        object.__setattr__(self, "fetched_at", aware_timestamp(self.fetched_at, required=True))
        object.__setattr__(
            self,
            "retry_after",
            aware_timestamp(self.retry_after) or None,
        )
        object.__setattr__(self, "cache_status", CacheStatus(self.cache_status))
        object.__setattr__(
            self,
            "contract_version",
            ensure_compatible_contract(self.contract_version),
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "contract_version": self.contract_version,
            "source_id": self.source_id,
            "items": [item.to_dict() for item in self.items],
            "warnings": list(self.warnings),
            "coverage": self.coverage.to_dict(),
            "fetched_at": self.fetched_at,
            "retry_after": self.retry_after,
            "cache_status": self.cache_status.value,
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "CollectorResult":
        ensure_compatible_contract(
            value.get("contract_version", COLLECTOR_CONTRACT_VERSION)
        )
        return cls(
            source_id=value.get("source_id", ""),
            items=tuple(IntelItem.from_dict(item) for item in value.get("items", [])),
            warnings=tuple(value.get("warnings", [])),
            coverage=SourceCoverage.from_dict(value.get("coverage", {})),
            fetched_at=value.get("fetched_at", ""),
            retry_after=value.get("retry_after"),
            cache_status=value.get("cache_status", CacheStatus.FETCHED.value),
            contract_version=value.get(
                "contract_version",
                COLLECTOR_CONTRACT_VERSION,
            ),
        )


__all__ = [
    "COLLECTOR_CONTRACT_VERSION",
    "PUBLIC_SOURCE_IDS",
    "PUBLIC_SOURCE_ID_SET",
    "CacheStatus",
    "CollectRequest",
    "CollectorResult",
    "CoverageStatus",
    "IntelItem",
    "SourceCoverage",
    "aware_timestamp",
    "ensure_compatible_contract",
    "is_valid_source_id",
    "json_safe_mapping",
    "normalize_source_ids",
    "normalize_url",
    "rfc3339",
    "sanitize_external_text",
    "stable_item_id",
]
