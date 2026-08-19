"""Trusted, application-supplied configuration seam for the RSS Collector."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Iterable, Mapping, Optional, Union

import httpx

from .collector import RSSIntelCollector
from .http_client import Resolver


@dataclass(frozen=True)
class RSSIntelSourceConfig:
    """Closed-world source inputs supplied by application composition."""

    feed_urls: tuple[object, ...] = ()
    keywords: tuple[object, ...] = ()
    allowed_redirect_hosts: tuple[object, ...] = ()

    @classmethod
    def from_mapping(cls, value: object) -> "RSSIntelSourceConfig":
        if value is None:
            return cls()
        if isinstance(value, cls):
            return value
        if not isinstance(value, Mapping):
            raise ValueError("RSS source provider must return an object")
        allowed = {"feed_urls", "keywords", "allowed_redirect_hosts"}
        unknown = set(value) - allowed
        if unknown:
            raise ValueError(f"unknown RSS source provider field: {sorted(unknown)[0]}")

        def values(name: str) -> tuple[object, ...]:
            raw = value.get(name, ())
            if isinstance(raw, str):
                return (raw,)
            if not isinstance(raw, Iterable):
                raise ValueError(f"{name} must be an iterable")
            return tuple(raw)

        return cls(
            feed_urls=values("feed_urls"),
            keywords=values("keywords"),
            allowed_redirect_hosts=values("allowed_redirect_hosts"),
        )


SourceConfigProvider = Callable[
    [],
    Union[RSSIntelSourceConfig, Mapping[str, object]],
]


class RSSIntelCollectorProvider:
    """Create one Collector without reading files, environment, or user input."""

    module_id = "rss_intel"
    source_id = "money"

    def __init__(
        self,
        source_config_provider: Optional[SourceConfigProvider] = None,
        *,
        client: Optional[httpx.AsyncClient] = None,
        resolver: Optional[Resolver] = None,
        clock=None,
    ) -> None:
        self._source_config_provider = source_config_provider
        self._client = client
        self._resolver = resolver
        self._clock = clock

    def create_collector(self) -> RSSIntelCollector:
        raw = self._source_config_provider() if self._source_config_provider else None
        config = RSSIntelSourceConfig.from_mapping(raw)
        return RSSIntelCollector(
            config.feed_urls,
            config.keywords,
            allowed_redirect_hosts=config.allowed_redirect_hosts,
            client=self._client,
            resolver=self._resolver,
            clock=self._clock,
        )


__all__ = [
    "RSSIntelCollectorProvider",
    "RSSIntelSourceConfig",
    "SourceConfigProvider",
]
