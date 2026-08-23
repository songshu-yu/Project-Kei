"""Daily-briefing models plus Collector 1.0 compatibility re-exports."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Dict, List, Mapping, Optional

from pydantic import BaseModel, ConfigDict, Field, StrictBool

from core.intel_contracts import (
    COLLECTOR_CONTRACT_VERSION,
    PUBLIC_SOURCE_IDS,
    PUBLIC_SOURCE_ID_SET,
    CacheStatus,
    CollectRequest,
    CollectorResult,
    CoverageStatus,
    IntelItem,
    SourceCoverage,
    aware_timestamp,
    ensure_compatible_contract,
    get_timezone,
    is_valid_source_id,
    json_safe_mapping,
    normalize_source_ids,
    normalize_url,
    rfc3339,
    sanitize_external_text,
    stable_item_id,
)


BRIEFING_CACHE_SCHEMA_VERSION = 1
LIFE_FORECAST_PROJECTION_SCHEMA_VERSION = 1
LIFE_FORECAST_PROJECTION_FIELD_IDS = (
    "weather_condition",
    "temperature_range",
    "apparent_temperature",
    "precipitation_probability",
    "wind",
    "alerts",
    "clothing",
    "travel_umbrella",
    "uv",
    "air_quality",
    "fortune",
)


@dataclass
class BriefingDocument:
    local_date: str
    timezone: str
    items: List[IntelItem]
    coverage: Dict[str, SourceCoverage]
    warnings: List[str]
    text: str
    script: str
    fetched: bool
    rewritten: bool
    rewrite_status: str
    created_at: str
    updated_at: str
    patch_attempts: Dict[str, str] = field(default_factory=dict)
    cache_status: CacheStatus = CacheStatus.FETCHED
    schema_version: int = BRIEFING_CACHE_SCHEMA_VERSION
    refresh_status: str = "not_requested"
    refresh_message: str = ""

    def __post_init__(self) -> None:
        date.fromisoformat(str(self.local_date))
        get_timezone(self.timezone)
        self.created_at = aware_timestamp(self.created_at, required=True)
        self.updated_at = aware_timestamp(self.updated_at, required=True)
        self.items = list(self.items)
        if any(not isinstance(item, IntelItem) for item in self.items):
            raise ValueError("briefing items must be IntelItem values")
        self.coverage = {
            str(key): (
                value
                if isinstance(value, SourceCoverage)
                else SourceCoverage.from_dict(value)
            )
            for key, value in self.coverage.items()
            if is_valid_source_id(key)
        }
        self.warnings = [
            cleaned
            for item in self.warnings
            if (cleaned := sanitize_external_text(item, limit=240))
        ]
        self.text = sanitize_external_text(
            self.text,
            limit=200_000,
            collapse_whitespace=False,
        )
        self.script = sanitize_external_text(
            self.script,
            limit=200_000,
            collapse_whitespace=False,
        )
        self.patch_attempts = {
            str(key): aware_timestamp(value, required=True)
            for key, value in self.patch_attempts.items()
            if is_valid_source_id(key)
        }
        self.cache_status = CacheStatus(self.cache_status)
        self.refresh_status = str(self.refresh_status or "not_requested")
        self.refresh_message = sanitize_external_text(
            self.refresh_message,
            limit=240,
        )

    def to_dict(self, *, include_cache_status: bool = True) -> Dict[str, object]:
        payload: Dict[str, object] = {
            "schema_version": self.schema_version,
            "collector_contract_version": COLLECTOR_CONTRACT_VERSION,
            "local_date": self.local_date,
            "timezone": self.timezone,
            "items": [item.to_dict() for item in self.items],
            "coverage": {
                key: value.to_dict()
                for key, value in self.coverage.items()
            },
            "warnings": list(self.warnings),
            "text": self.text,
            "script": self.script,
            "fetched": self.fetched,
            "rewritten": self.rewritten,
            "rewrite_status": self.rewrite_status,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "patch_attempts": dict(self.patch_attempts),
        }
        if include_cache_status:
            payload["cache_status"] = self.cache_status.value
        return payload

    @classmethod
    def from_dict(cls, value: Mapping[str, object]) -> "BriefingDocument":
        if int(value.get("schema_version", 0)) != BRIEFING_CACHE_SCHEMA_VERSION:
            raise ValueError("unsupported briefing cache schema")
        ensure_compatible_contract(
            value.get(
                "collector_contract_version",
                COLLECTOR_CONTRACT_VERSION,
            )
        )
        local_date = str(value.get("local_date", ""))
        date.fromisoformat(local_date)
        raw_coverage = value.get("coverage", {})
        raw_attempts = value.get("patch_attempts", {})
        coverage = raw_coverage if isinstance(raw_coverage, Mapping) else {}
        attempts = raw_attempts if isinstance(raw_attempts, Mapping) else {}
        return cls(
            schema_version=BRIEFING_CACHE_SCHEMA_VERSION,
            local_date=local_date,
            timezone=str(value.get("timezone", "")) or "Asia/Shanghai",
            items=[
                IntelItem.from_dict(item)
                for item in value.get("items", [])
                if isinstance(item, Mapping)
            ],
            coverage={
                str(key): SourceCoverage.from_dict(item)
                for key, item in coverage.items()
                if is_valid_source_id(key) and isinstance(item, Mapping)
            },
            warnings=[
                sanitize_external_text(item, limit=240)
                for item in value.get("warnings", [])
                if str(item or "").strip()
            ],
            text=str(value.get("text", "")),
            script=str(value.get("script", "")),
            fetched=bool(value.get("fetched", False)),
            rewritten=bool(value.get("rewritten", False)),
            rewrite_status=str(value.get("rewrite_status", "not_requested")),
            created_at=str(value.get("created_at", "")),
            updated_at=str(value.get("updated_at", "")),
            patch_attempts={
                str(key): aware_timestamp(item, required=True)
                for key, item in attempts.items()
                if is_valid_source_id(key)
            },
            cache_status=CacheStatus(
                value.get("cache_status", CacheStatus.HIT.value)
            ),
        )


class BriefingGenerateRequest(BaseModel):
    source_ids: Optional[List[str]] = None
    refresh: bool = False
    rewrite: bool = True
    rewrite_refresh: bool = False
    patch_missing: bool = True
    lookback: int = Field(default=24, ge=1, le=720)


class LifeForecastProjectionFields(BaseModel):
    model_config = ConfigDict(extra="forbid")

    weather_condition: StrictBool
    temperature_range: StrictBool
    apparent_temperature: StrictBool
    precipitation_probability: StrictBool
    wind: StrictBool
    alerts: StrictBool
    clothing: StrictBool
    travel_umbrella: StrictBool
    uv: StrictBool
    air_quality: StrictBool
    fortune: StrictBool

class LifeForecastProjectionUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: StrictBool
    fields: LifeForecastProjectionFields

def disabled_life_forecast_projection() -> LifeForecastProjectionUpdate:
    return LifeForecastProjectionUpdate(
        enabled=False,
        fields={key: False for key in LIFE_FORECAST_PROJECTION_FIELD_IDS},
    )


__all__ = [
    "BRIEFING_CACHE_SCHEMA_VERSION",
    "LIFE_FORECAST_PROJECTION_FIELD_IDS",
    "LIFE_FORECAST_PROJECTION_SCHEMA_VERSION",
    "COLLECTOR_CONTRACT_VERSION",
    "PUBLIC_SOURCE_IDS",
    "PUBLIC_SOURCE_ID_SET",
    "BriefingDocument",
    "BriefingGenerateRequest",
    "LifeForecastProjectionFields",
    "LifeForecastProjectionUpdate",
    "CacheStatus",
    "CollectRequest",
    "CollectorResult",
    "CoverageStatus",
    "IntelItem",
    "SourceCoverage",
    "aware_timestamp",
    "ensure_compatible_contract",
    "json_safe_mapping",
    "normalize_source_ids",
    "normalize_url",
    "rfc3339",
    "sanitize_external_text",
    "stable_item_id",
    "disabled_life_forecast_projection",
]
