"""Compatibility facade for the PK-115 local intelligence-source registry."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping, Sequence

from features.intel_sources import (
    DEFAULT_PATH,
    SOURCE_CONFIG_SCHEMA_VERSION,
    SOURCE_FIELDS,
    IntelSourceConfigRepository,
    IntelSourceRegistry,
)
from features.intel_sources.models import mutable_source_config, normalize_source_config
from intel import intel_config


SCHEMA_VERSION = SOURCE_CONFIG_SCHEMA_VERSION
LIST_FIELDS = SOURCE_FIELDS


def default_intel_sources() -> dict[str, Any]:
    """Return a fresh copy of legacy defaults without writing local state."""
    return {
        "twitter_users": list(getattr(intel_config, "TWITTER_USERS", [])),
        "money_twitter_users": list(getattr(intel_config, "MONEY_TWITTER_USERS", [])),
        "github_users": list(getattr(intel_config, "GITHUB_USERS", [])),
        "github_repos": list(getattr(intel_config, "GITHUB_REPOS", [])),
        "bilibili_uids": list(getattr(intel_config, "BILIBILI_UIDS", [])),
        "youtube_channel_ids": list(getattr(intel_config, "YOUTUBE_CHANNELS", [])),
        "paper_priority_authors": list(getattr(intel_config, "PAPER_PRIORITY_AUTHORS", [])),
        "paper_secondary_authors": list(getattr(intel_config, "PAPER_SECONDARY_AUTHORS", [])),
        "paper_ai_authors": list(getattr(intel_config, "PAPER_AI_AUTHORS", [])),
    }


def _registry(path: str | Path) -> IntelSourceRegistry:
    return IntelSourceRegistry(
        IntelSourceConfigRepository(path),
        defaults_provider=default_intel_sources,
    )


def normalize_intel_sources(
    payload: object,
    defaults: Mapping[str, Sequence[object]] | None = None,
) -> dict[str, Any]:
    config = normalize_source_config(payload, defaults or default_intel_sources())
    return mutable_source_config(config)


def load_intel_sources(path: str | Path = DEFAULT_PATH) -> dict[str, Any]:
    return _registry(path).read()


def save_intel_sources(payload: object, path: str | Path = DEFAULT_PATH) -> dict[str, Any]:
    return _registry(path).replace(payload)


def get_intel_source_snapshot(
    path: str | Path = DEFAULT_PATH,
    source_ids: Sequence[object] | None = None,
) -> Mapping[str, Any]:
    return _registry(path).snapshot(source_ids)


__all__ = [
    "DEFAULT_PATH",
    "LIST_FIELDS",
    "SCHEMA_VERSION",
    "default_intel_sources",
    "get_intel_source_snapshot",
    "load_intel_sources",
    "normalize_intel_sources",
    "save_intel_sources",
]
