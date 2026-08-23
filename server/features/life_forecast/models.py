"""HTTP request models and local configuration validation."""

from __future__ import annotations

import math
import re

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .contracts import LocationConfig


PROVIDER_IDS = frozenset({"disabled", "open_meteo"})
_CONTROL = re.compile(r"[\x00-\x1f\x7f]")


def validate_city(value: object) -> str:
    city = str(value).strip()
    if not city or len(city) > 80 or _CONTROL.search(city):
        raise ValueError("city must be 1-80 printable characters")
    return city


def validate_latitude(value: object) -> float:
    result = float(value)
    if not math.isfinite(result) or not -90 <= result <= 90:
        raise ValueError("latitude must be between -90 and 90")
    return result


def validate_longitude(value: object) -> float:
    result = float(value)
    if not math.isfinite(result) or not -180 <= result <= 180:
        raise ValueError("longitude must be between -180 and 180")
    return result


class LifeForecastConfigRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    city: str = Field(min_length=1, max_length=80)
    latitude: float
    longitude: float
    provider: str
    fortune_enabled: bool = False

    @field_validator("city")
    @classmethod
    def _city(cls, value: str) -> str:
        return validate_city(value)

    @field_validator("latitude")
    @classmethod
    def _latitude(cls, value: float) -> float:
        return validate_latitude(value)

    @field_validator("longitude")
    @classmethod
    def _longitude(cls, value: float) -> float:
        return validate_longitude(value)

    @field_validator("provider")
    @classmethod
    def _provider(cls, value: str) -> str:
        provider = str(value).strip().lower()
        if provider not in PROVIDER_IDS:
            raise ValueError("provider is not supported")
        return provider

    def to_contract(self) -> LocationConfig:
        return LocationConfig(**self.model_dump())


def config_from_mapping(value: object) -> LocationConfig:
    if not isinstance(value, dict):
        raise ValueError("configuration root must be an object")
    allowed = {"city", "latitude", "longitude", "provider", "fortune_enabled"}
    if set(value) != allowed:
        raise ValueError("configuration fields are invalid")
    return LifeForecastConfigRequest.model_validate(value).to_contract()


__all__ = [
    "LifeForecastConfigRequest",
    "PROVIDER_IDS",
    "config_from_mapping",
    "validate_city",
    "validate_latitude",
    "validate_longitude",
]
