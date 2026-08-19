"""Validation and immutable snapshot models for local intelligence sources."""

from __future__ import annotations

import re
from types import MappingProxyType
from typing import Any, Callable, Mapping, Sequence

from core.intel_contracts import json_safe_mapping, normalize_source_ids


SOURCE_CONFIG_SCHEMA_VERSION = 1
MAX_TARGETS_PER_GROUP = 500

SOURCE_FIELDS = (
    "twitter_users",
    "money_twitter_users",
    "github_users",
    "github_repos",
    "bilibili_uids",
    "youtube_channel_ids",
    "paper_priority_authors",
    "paper_secondary_authors",
    "paper_ai_authors",
)

SOURCE_FIELD_IDS: Mapping[str, tuple[str, ...]] = MappingProxyType(
    {
        "twitter_users": ("twitter",),
        "money_twitter_users": ("twitter",),
        "github_users": ("github",),
        "github_repos": ("github",),
        "bilibili_uids": ("bilibili",),
        "youtube_channel_ids": ("youtube",),
        "paper_priority_authors": ("arxiv", "crossref", "semantic"),
        "paper_secondary_authors": ("arxiv", "crossref", "semantic"),
        "paper_ai_authors": ("arxiv", "crossref", "semantic"),
    }
)

_STORAGE_METADATA_FIELDS = frozenset({"schema_version", "updated_at"})
_RESPONSE_METADATA_FIELDS = frozenset({"using_local_override", "load_warning"})
_HANDLE_RE = re.compile(r"[A-Za-z0-9_]{1,30}")
_GITHUB_USER_RE = re.compile(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?")
_GITHUB_REPO_RE = re.compile(
    r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?/[A-Za-z0-9_.-]{1,100}"
)
_YOUTUBE_CHANNEL_RE = re.compile(r"UC[A-Za-z0-9_-]{22}")


def _text(value: object, label: str, max_length: int) -> str:
    if not isinstance(value, (str, int)) or isinstance(value, bool):
        raise ValueError(f"{label} must be text")
    result = " ".join(str(value).strip().split())
    if not result:
        raise ValueError(f"{label} cannot be empty")
    if len(result) > max_length:
        raise ValueError(f"{label} is too long")
    if any(ord(character) < 32 for character in result):
        raise ValueError(f"{label} contains control characters")
    return result


def normalize_twitter_handle(value: object) -> str:
    result = _text(value, "X username", 31).lstrip("@")
    if not _HANDLE_RE.fullmatch(result):
        raise ValueError("X username must contain only letters, numbers, or underscores")
    return result


def normalize_github_user(value: object) -> str:
    result = _text(value, "GitHub username", 39)
    if not _GITHUB_USER_RE.fullmatch(result):
        raise ValueError("GitHub username format is invalid")
    return result


def normalize_github_repo(value: object) -> str:
    result = _text(value, "GitHub repository", 140)
    if not _GITHUB_REPO_RE.fullmatch(result):
        raise ValueError("GitHub repository must use owner/repository format")
    return result


def normalize_bilibili_uid(value: object) -> int:
    result = _text(value, "Bilibili UID", 20)
    if not result.isdigit() or int(result) <= 0:
        raise ValueError("Bilibili UID must be a positive integer")
    return int(result)


def normalize_youtube_channel(value: object) -> str:
    result = _text(value, "YouTube channel ID", 128)
    if not _YOUTUBE_CHANNEL_RE.fullmatch(result):
        raise ValueError("YouTube channel ID format is invalid")
    return result


def normalize_author(value: object) -> str:
    return _text(value, "Author name", 180)


FIELD_NORMALIZERS: Mapping[str, Callable[[object], Any]] = MappingProxyType(
    {
        "twitter_users": normalize_twitter_handle,
        "money_twitter_users": normalize_twitter_handle,
        "github_users": normalize_github_user,
        "github_repos": normalize_github_repo,
        "bilibili_uids": normalize_bilibili_uid,
        "youtube_channel_ids": normalize_youtube_channel,
        "paper_priority_authors": normalize_author,
        "paper_secondary_authors": normalize_author,
        "paper_ai_authors": normalize_author,
    }
)


def require_source_field(field: object) -> str:
    value = str(field or "").strip()
    if value not in SOURCE_FIELDS:
        raise ValueError("unknown intelligence source field")
    return value


def normalize_source_values(field: str, values: object) -> tuple[Any, ...]:
    field = require_source_field(field)
    if not isinstance(values, list):
        raise ValueError(f"{field} must be a list")
    if len(values) > MAX_TARGETS_PER_GROUP:
        raise ValueError(f"{field} cannot contain more than {MAX_TARGETS_PER_GROUP} targets")
    normalizer = FIELD_NORMALIZERS[field]
    result: list[Any] = []
    seen: set[str] = set()
    for value in values:
        normalized = normalizer(value)
        key = str(normalized).casefold()
        if key not in seen:
            seen.add(key)
            result.append(normalized)
    return tuple(result)


def normalize_source_config(
    payload: object,
    defaults: Mapping[str, Sequence[object]],
) -> dict[str, tuple[Any, ...]]:
    """Validate a full or partial JSON-shaped source configuration."""
    if payload is not None and not isinstance(payload, Mapping):
        raise ValueError("source configuration must be an object")
    source = dict(payload or {})
    unknown = set(source) - set(SOURCE_FIELDS) - _STORAGE_METADATA_FIELDS - _RESPONSE_METADATA_FIELDS
    if unknown:
        raise ValueError(f"unknown source configuration field: {sorted(unknown)[0]}")
    schema_version = source.get("schema_version", SOURCE_CONFIG_SCHEMA_VERSION)
    if type(schema_version) is not int or schema_version != SOURCE_CONFIG_SCHEMA_VERSION:
        raise ValueError("unsupported source configuration schema")

    normalized: dict[str, tuple[Any, ...]] = {}
    for field in SOURCE_FIELDS:
        if field not in defaults:
            raise ValueError(f"source defaults are missing {field}")
        values = source[field] if field in source else list(defaults[field])
        normalized[field] = normalize_source_values(field, values)
    return normalized


def mutable_source_config(config: Mapping[str, Sequence[object]]) -> dict[str, list[Any]]:
    return {field: list(config[field]) for field in SOURCE_FIELDS}


def readonly_source_snapshot(
    config: Mapping[str, Sequence[object]],
    source_ids: Sequence[object] | None = None,
) -> Mapping[str, Any]:
    """Return a secret-safe, recursively immutable Collector config snapshot."""
    selected = None if source_ids is None else frozenset(normalize_source_ids(source_ids))
    snapshot = {
        field: list(config[field])
        for field in SOURCE_FIELDS
        if selected is None or selected.intersection(SOURCE_FIELD_IDS[field])
    }
    safe = json_safe_mapping(snapshot)
    return MappingProxyType(
        {
            key: tuple(value) if isinstance(value, list) else value
            for key, value in safe.items()
        }
    )


__all__ = [
    "FIELD_NORMALIZERS",
    "MAX_TARGETS_PER_GROUP",
    "SOURCE_CONFIG_SCHEMA_VERSION",
    "SOURCE_FIELDS",
    "SOURCE_FIELD_IDS",
    "mutable_source_config",
    "normalize_source_config",
    "normalize_source_values",
    "readonly_source_snapshot",
    "require_source_field",
]
