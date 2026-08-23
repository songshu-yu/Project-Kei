"""Weather Provider implementations and upstream normalization."""

from __future__ import annotations

import math
import re
from datetime import date, datetime, timezone
from typing import Any, Callable, Mapping, Sequence
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import httpx

from .contracts import ForecastResult, LocationConfig


FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
AIR_QUALITY_URL = "https://air-quality-api.open-meteo.com/v1/air-quality"
_TIMEZONE = re.compile(r"^[A-Za-z0-9._+-]+(?:/[A-Za-z0-9._+-]+)*$")

WEATHER_CODES = {
    0: "晴",
    1: "大致晴朗",
    2: "局部多云",
    3: "阴",
    45: "雾",
    48: "雾凇",
    51: "小毛毛雨",
    53: "毛毛雨",
    55: "强毛毛雨",
    56: "轻微冻毛毛雨",
    57: "强冻毛毛雨",
    61: "小雨",
    63: "中雨",
    65: "大雨",
    66: "轻微冻雨",
    67: "强冻雨",
    71: "小雪",
    73: "中雪",
    75: "大雪",
    77: "米雪",
    80: "小阵雨",
    81: "阵雨",
    82: "强阵雨",
    85: "小阵雪",
    86: "强阵雪",
    95: "雷暴",
    96: "雷暴伴小冰雹",
    99: "雷暴伴大冰雹",
}


class ProviderError(RuntimeError):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def _finite(value: object, *, minimum: float, maximum: float, field: str) -> float:
    if isinstance(value, bool):
        raise ProviderError("upstream_payload_invalid")
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise ProviderError("upstream_payload_invalid") from exc
    if not math.isfinite(result) or not minimum <= result <= maximum:
        raise ProviderError(f"upstream_{field}_invalid")
    return result


def _first(values: object) -> object:
    if not isinstance(values, Sequence) or isinstance(values, (str, bytes)) or not values:
        raise ProviderError("upstream_payload_invalid")
    return values[0]


def _temperature(value: object, unit: object) -> float:
    number = _finite(value, minimum=-200, maximum=300, field="temperature")
    if unit in {"°C", "C", "celsius"}:
        result = number
    elif unit in {"°F", "F", "fahrenheit"}:
        result = (number - 32.0) * 5.0 / 9.0
    else:
        raise ProviderError("upstream_unit_invalid")
    if not -100 <= result <= 70:
        raise ProviderError("upstream_temperature_invalid")
    return round(result, 1)


def _wind_speed(value: object, unit: object) -> float:
    number = _finite(value, minimum=0, maximum=1000, field="wind")
    if unit in {"km/h", "kmh"}:
        result = number
    elif unit in {"mph"}:
        result = number * 1.609344
    elif unit in {"m/s", "ms"}:
        result = number * 3.6
    elif unit in {"kn", "knot", "knots"}:
        result = number * 1.852
    else:
        raise ProviderError("upstream_unit_invalid")
    if not 0 <= result <= 500:
        raise ProviderError("upstream_wind_invalid")
    return round(result, 1)


def _timezone(value: object) -> str:
    text = str(value)
    if len(text) > 64 or not _TIMEZONE.fullmatch(text):
        raise ProviderError("upstream_timezone_invalid")
    try:
        ZoneInfo(text)
    except ZoneInfoNotFoundError as exc:
        raise ProviderError("upstream_timezone_invalid") from exc
    return text


class OpenMeteoWeatherProvider:
    """Fixed-host Open-Meteo adapter. It never receives the local city label."""

    provider_id = "open_meteo"

    def __init__(
        self,
        client: httpx.Client | None = None,
        *,
        timestamp: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
        timeout_seconds: float = 10.0,
    ):
        self._client = client or httpx.Client(
            timeout=httpx.Timeout(timeout_seconds),
            follow_redirects=False,
            trust_env=False,
        )
        self._owns_client = client is None
        self._timestamp = timestamp

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def _get_json(self, url: str, params: Mapping[str, object]) -> Mapping[str, Any]:
        try:
            response = self._client.get(url, params=params)
        except httpx.TimeoutException as exc:
            raise ProviderError("upstream_timeout") from exc
        except httpx.HTTPError as exc:
            raise ProviderError("upstream_network_error") from exc
        if response.status_code == 429:
            raise ProviderError("upstream_rate_limited")
        if response.status_code < 200 or response.status_code >= 300:
            raise ProviderError("upstream_unavailable")
        try:
            payload = response.json()
        except (ValueError, UnicodeError) as exc:
            raise ProviderError("upstream_payload_invalid") from exc
        if not isinstance(payload, Mapping):
            raise ProviderError("upstream_payload_invalid")
        return payload

    @staticmethod
    def _weather_params(location: LocationConfig, local_date: date) -> dict[str, object]:
        return {
            "latitude": location.latitude,
            "longitude": location.longitude,
            "timezone": "auto",
            "start_date": local_date.isoformat(),
            "end_date": local_date.isoformat(),
            "temperature_unit": "celsius",
            "wind_speed_unit": "kmh",
            "current": "temperature_2m,apparent_temperature,weather_code",
            "daily": (
                "weather_code,temperature_2m_max,temperature_2m_min,"
                "precipitation_probability_max,wind_speed_10m_max,uv_index_max"
            ),
        }

    @staticmethod
    def _air_params(location: LocationConfig, local_date: date) -> dict[str, object]:
        return {
            "latitude": location.latitude,
            "longitude": location.longitude,
            "timezone": "auto",
            "start_date": local_date.isoformat(),
            "end_date": local_date.isoformat(),
            "current": "us_aqi",
        }

    def fetch(self, location: LocationConfig, local_date: date) -> ForecastResult:
        weather = self._get_json(FORECAST_URL, self._weather_params(location, local_date))
        current = weather.get("current")
        current_units = weather.get("current_units")
        daily = weather.get("daily")
        daily_units = weather.get("daily_units")
        if not all(isinstance(item, Mapping) for item in (current, current_units, daily, daily_units)):
            raise ProviderError("upstream_payload_invalid")
        timezone_name = _timezone(weather.get("timezone"))
        daily_date = str(_first(daily.get("time")))
        if daily_date != local_date.isoformat():
            raise ProviderError("upstream_date_mismatch")
        raw_condition = current.get("weather_code")
        if raw_condition is None:
            raw_condition = _first(daily.get("weather_code"))
        condition_code = int(_finite(
            raw_condition,
            minimum=0,
            maximum=999,
            field="weather_code",
        ))
        if condition_code not in WEATHER_CODES:
            raise ProviderError("upstream_weather_code_invalid")
        precipitation = _finite(
            _first(daily.get("precipitation_probability_max")),
            minimum=0,
            maximum=100,
            field="precipitation_probability",
        )
        if daily_units.get("precipitation_probability_max") != "%":
            raise ProviderError("upstream_unit_invalid")
        uv_value: float | None
        try:
            raw_uv = _first(daily.get("uv_index_max"))
            uv_value = None if raw_uv is None else round(
                _finite(raw_uv, minimum=0, maximum=30, field="uv_index"), 1
            )
        except ProviderError:
            uv_value = None

        aqi_value: float | None = None
        try:
            air = self._get_json(AIR_QUALITY_URL, self._air_params(location, local_date))
            if _timezone(air.get("timezone")) != timezone_name:
                raise ProviderError("upstream_timezone_invalid")
            air_current = air.get("current")
            if not isinstance(air_current, Mapping):
                raise ProviderError("upstream_payload_invalid")
            raw_aqi = air_current.get("us_aqi")
            if raw_aqi is not None:
                aqi_value = round(_finite(raw_aqi, minimum=0, maximum=500, field="aqi"), 1)
        except ProviderError:
            aqi_value = None

        fetched_at = self._timestamp()
        if fetched_at.tzinfo is None:
            fetched_at = fetched_at.replace(tzinfo=timezone.utc)
        maximum_temperature = _temperature(
            _first(daily.get("temperature_2m_max")), daily_units.get("temperature_2m_max")
        )
        minimum_temperature = _temperature(
            _first(daily.get("temperature_2m_min")), daily_units.get("temperature_2m_min")
        )
        if minimum_temperature > maximum_temperature:
            raise ProviderError("upstream_temperature_invalid")
        return ForecastResult(
            provider=self.provider_id,
            local_date=local_date.isoformat(),
            timezone=timezone_name,
            condition_code=condition_code,
            condition=WEATHER_CODES[condition_code],
            current_temperature_c=_temperature(
                current.get("temperature_2m"), current_units.get("temperature_2m")
            ),
            apparent_temperature_c=_temperature(
                current.get("apparent_temperature"), current_units.get("apparent_temperature")
            ),
            temperature_max_c=maximum_temperature,
            temperature_min_c=minimum_temperature,
            precipitation_probability_max_pct=round(precipitation, 1),
            wind_speed_max_kmh=_wind_speed(
                _first(daily.get("wind_speed_10m_max")), daily_units.get("wind_speed_10m_max")
            ),
            uv_index_max=uv_value,
            us_aqi=aqi_value,
            warnings_status="unavailable",
            warnings=(),
            fetched_at=fetched_at.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
            attribution=(
                {
                    "label": "Weather data by Open-Meteo.com (CC BY 4.0)",
                    "url": "https://open-meteo.com/",
                },
                {
                    "label": "Air quality data: CAMS via Open-Meteo",
                    "url": "https://open-meteo.com/en/docs/air-quality-api",
                },
            ),
        )


__all__ = [
    "AIR_QUALITY_URL",
    "FORECAST_URL",
    "OpenMeteoWeatherProvider",
    "ProviderError",
    "WEATHER_CODES",
]
