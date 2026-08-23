"""Frozen public Provider and normalized forecast contracts for PK-240."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date
from typing import Any, Protocol, runtime_checkable


@dataclass(frozen=True, slots=True)
class LocationConfig:
    """Validated local configuration passed to a weather Provider."""

    city: str
    latitude: float
    longitude: float
    provider: str
    fortune_enabled: bool

    def provider_view(self) -> "LocationConfig":
        """Keep the local city label out of third-party requests and adapters."""
        return LocationConfig(
            city="",
            latitude=self.latitude,
            longitude=self.longitude,
            provider=self.provider,
            fortune_enabled=False,
        )


@dataclass(frozen=True, slots=True)
class ForecastResult:
    """Provider-neutral facts. Text fields are from local allowlists only."""

    provider: str
    local_date: str
    timezone: str
    condition_code: int
    condition: str
    current_temperature_c: float
    apparent_temperature_c: float
    temperature_max_c: float
    temperature_min_c: float
    precipitation_probability_max_pct: float
    wind_speed_max_kmh: float
    uv_index_max: float | None
    us_aqi: float | None
    warnings_status: str
    warnings: tuple[dict[str, str], ...]
    fetched_at: str
    attribution: tuple[dict[str, str], ...]

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["warnings"] = [dict(item) for item in self.warnings]
        payload["attribution"] = [dict(item) for item in self.attribution]
        return payload


@runtime_checkable
class WeatherProvider(Protocol):
    """Version 1.0 public Provider contract."""

    provider_id: str

    def fetch(self, location: LocationConfig, local_date: date) -> ForecastResult:
        """Fetch and normalize one explicitly requested local day."""
        ...


WEATHER_PROVIDER_CONTRACT_VERSION = "1.0"

__all__ = [
    "ForecastResult",
    "LocationConfig",
    "WEATHER_PROVIDER_CONTRACT_VERSION",
    "WeatherProvider",
]
