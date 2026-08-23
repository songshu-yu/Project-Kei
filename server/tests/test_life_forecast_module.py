"""Offline PK-240 tests: fake Providers, MockTransport, fixed clocks and temp state."""

from __future__ import annotations

import json
import tempfile
import threading
import time
import zipfile
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timezone
from pathlib import Path

import httpx
import pytest
from pydantic import ValidationError

import _path_setup  # noqa: F401
from features.life_forecast.contracts import ForecastResult, LocationConfig
from features.life_forecast.models import LifeForecastConfigRequest
from features.life_forecast.package_builder import build_life_forecast_package, file_sha256
from features.life_forecast.providers import (
    AIR_QUALITY_URL,
    FORECAST_URL,
    OpenMeteoWeatherProvider,
    ProviderError,
)
from features.life_forecast.repository import LifeForecastPersistenceError, LifeForecastRepository
from features.life_forecast.service import LifeForecastError, LifeForecastService, deterministic_fortune

PROJECT_ROOT = Path(__file__).resolve().parents[2]
FEATURE_ROOT = PROJECT_ROOT / "server" / "features" / "life_forecast"


def normalized_result(day: date, *, timezone_name: str = "Asia/Shanghai") -> ForecastResult:
    return ForecastResult(
        provider="open_meteo", local_date=day.isoformat(), timezone=timezone_name,
        condition_code=61, condition="小雨", current_temperature_c=18.0,
        apparent_temperature_c=17.0, temperature_max_c=22.0, temperature_min_c=13.0,
        precipitation_probability_max_pct=65.0, wind_speed_max_kmh=20.0,
        uv_index_max=4.0, us_aqi=42.0, warnings_status="unavailable", warnings=(),
        fetched_at="2026-08-19T01:00:00Z",
        attribution=({"label": "Open-Meteo", "url": "https://open-meteo.com/"},),
    )


class FakeProvider:
    provider_id = "open_meteo"

    def __init__(self):
        self.calls = []

    def fetch(self, location, local_date):
        self.calls.append((location, local_date))
        return normalized_result(local_date)


def configured_service(root: Path, clock=lambda: date(2026, 8, 19)):
    repository = LifeForecastRepository(root)
    provider = FakeProvider()
    service = LifeForecastService(repository, {"open_meteo": provider}, clock=clock)
    service.save_config(LocationConfig("上海", 31.2304, 121.4737, "open_meteo", True))
    return repository, provider, service


def weather_payload(day="2026-08-19", *, timezone_name="Asia/Shanghai", fahrenheit=False):
    temp_unit = "°F" if fahrenheit else "°C"
    wind_unit = "mph" if fahrenheit else "km/h"
    return {
        "timezone": timezone_name,
        "current": {
            "temperature_2m": 68 if fahrenheit else 20,
            "apparent_temperature": 66.2 if fahrenheit else 19,
            "weather_code": 2,
            "malicious_text": "token=should-not-survive <script>alert(1)</script>",
        },
        "current_units": {"temperature_2m": temp_unit, "apparent_temperature": temp_unit},
        "daily": {
            "time": [day], "weather_code": [2],
            "temperature_2m_max": [77 if fahrenheit else 25],
            "temperature_2m_min": [59 if fahrenheit else 15],
            "precipitation_probability_max": [30],
            "wind_speed_10m_max": [10 if fahrenheit else 16.1],
            "uv_index_max": [5.5],
        },
        "daily_units": {
            "temperature_2m_max": temp_unit, "temperature_2m_min": temp_unit,
            "precipitation_probability_max": "%", "wind_speed_10m_max": wind_unit,
            "uv_index_max": "",
        },
    }


def air_payload(timezone_name="Asia/Shanghai"):
    return {"timezone": timezone_name, "current": {"us_aqi": 55}}


def test_read_config_and_today_are_zero_upstream_network_and_cross_day_is_not_reused():
    with tempfile.TemporaryDirectory(prefix="kei-life-forecast-") as temp:
        days = [date(2026, 3, 8)]
        repository, provider, service = configured_service(Path(temp), clock=lambda: days[0])
        assert service.get_config()["city"] == "上海"
        assert service.get_today()["cache_status"] == "missing"
        assert provider.calls == []
        service.refresh()
        assert len(provider.calls) == 1
        days[0] = date(2026, 3, 9)
        tomorrow = service.get_today()
        assert tomorrow["date"] == "2026-03-09"
        assert tomorrow["cache_status"] == "missing"
        assert tomorrow["forecast"] is None
        assert len(provider.calls) == 1
        assert repository.cache_path("2026-03-08").exists()


def test_refresh_passes_only_coordinates_to_provider_and_cache_omits_location():
    with tempfile.TemporaryDirectory(prefix="kei-life-forecast-") as temp:
        repository, provider, service = configured_service(Path(temp))
        result = service.refresh()
        passed, _ = provider.calls[0]
        assert passed.city == ""
        assert passed.fortune_enabled is False
        cache_text = repository.cache_path("2026-08-19").read_text(encoding="utf-8")
        assert "上海" not in cache_text and "31.2304" not in cache_text and "121.4737" not in cache_text
        assert result["forecast"]["warnings_status"] == "unavailable"
        assert result["life_advice"]["travel_umbrella"]["bring_umbrella"] is True


def test_open_meteo_mock_transport_normalizes_units_and_discards_external_text():
    def handler(request: httpx.Request) -> httpx.Response:
        if str(request.url).startswith(FORECAST_URL):
            return httpx.Response(200, json=weather_payload(fahrenheit=True))
        assert str(request.url).startswith(AIR_QUALITY_URL)
        return httpx.Response(200, json=air_payload())

    provider = OpenMeteoWeatherProvider(
        httpx.Client(transport=httpx.MockTransport(handler)),
        timestamp=lambda: datetime(2026, 8, 19, tzinfo=timezone.utc),
    )
    result = provider.fetch(LocationConfig("", 31.2, 121.4, "open_meteo", False), date(2026, 8, 19))
    assert result.current_temperature_c == 20.0
    assert result.temperature_max_c == 25.0
    assert result.wind_speed_max_kmh == 16.1
    assert result.us_aqi == 55.0
    assert "token" not in json.dumps(result.to_dict(), ensure_ascii=False)


@pytest.mark.parametrize(
    ("response", "expected"),
    [(httpx.Response(429), "upstream_rate_limited"), (httpx.Response(503, text="secret upstream body"), "upstream_unavailable")],
)
def test_provider_429_and_5xx_use_finite_codes_without_response_body(response, expected):
    provider = OpenMeteoWeatherProvider(httpx.Client(transport=httpx.MockTransport(lambda request: response)))
    with pytest.raises(ProviderError) as caught:
        provider.fetch(LocationConfig("", 0, 0, "open_meteo", False), date(2026, 8, 19))
    assert caught.value.code == expected
    assert "secret" not in str(caught.value)


def test_provider_timeout_and_malicious_timezone_fail_closed():
    def timeout(request):
        raise httpx.ReadTimeout("contains private URL", request=request)

    provider = OpenMeteoWeatherProvider(httpx.Client(transport=httpx.MockTransport(timeout)))
    with pytest.raises(ProviderError, match="upstream_timeout"):
        provider.fetch(LocationConfig("", 0, 0, "open_meteo", False), date(2026, 8, 19))

    payload = weather_payload(timezone_name="Asia/Shanghai\nsecret")
    provider = OpenMeteoWeatherProvider(httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(200, json=payload))))
    with pytest.raises(ProviderError, match="upstream_timezone_invalid"):
        provider.fetch(LocationConfig("", 0, 0, "open_meteo", False), date(2026, 8, 19))


def test_air_quality_failure_degrades_to_unavailable_without_losing_weather():
    def handler(request):
        return httpx.Response(200, json=weather_payload()) if str(request.url).startswith(FORECAST_URL) else httpx.Response(429)

    provider = OpenMeteoWeatherProvider(httpx.Client(transport=httpx.MockTransport(handler)))
    result = provider.fetch(LocationConfig("", 0, 0, "open_meteo", False), date(2026, 8, 19))
    assert result.us_aqi is None and result.temperature_max_c == 25


def test_abnormal_units_are_rejected_before_cache_boundary():
    payload = weather_payload()
    payload["daily_units"]["precipitation_probability_max"] = "fraction"
    provider = OpenMeteoWeatherProvider(httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(200, json=payload))))
    with pytest.raises(ProviderError, match="upstream_unit_invalid"):
        provider.fetch(LocationConfig("", 0, 0, "open_meteo", False), date(2026, 8, 19))


def test_illegal_coordinates_and_control_character_city_are_rejected_before_save():
    for values in (
        {"city": "上海", "latitude": 91, "longitude": 0, "provider": "disabled", "fortune_enabled": False},
        {"city": "上海", "latitude": 0, "longitude": 181, "provider": "disabled", "fortune_enabled": False},
        {"city": "bad\ncity", "latitude": 0, "longitude": 0, "provider": "disabled", "fortune_enabled": False},
    ):
        with pytest.raises(ValidationError):
            LifeForecastConfigRequest.model_validate(values)


def test_corrupted_cache_is_reported_and_normal_read_does_not_repair_it():
    with tempfile.TemporaryDirectory(prefix="kei-life-forecast-") as temp:
        repository, _, service = configured_service(Path(temp))
        path = repository.cache_path("2026-08-19")
        path.parent.mkdir(parents=True)
        original = b"{broken cache"
        path.write_bytes(original)
        result = service.get_today()
        assert result["cache_status"] == "corrupted" and result["forecast"] is None
        assert path.read_bytes() == original


def test_atomic_cache_failure_preserves_previous_bytes():
    with tempfile.TemporaryDirectory(prefix="kei-life-forecast-") as temp:
        root = Path(temp)
        repository, _, service = configured_service(root)
        service.refresh()
        path = repository.cache_path("2026-08-19")
        before = path.read_bytes()
        failing = LifeForecastRepository(root, replace=lambda source, target: (_ for _ in ()).throw(OSError("denied")))
        with pytest.raises(LifeForecastPersistenceError):
            failing.save_cache(date(2026, 8, 19), {"forecast": {"changed": True}})
        assert path.read_bytes() == before


def test_provider_failure_during_refresh_keeps_old_cache_bytes():
    class FailingProvider(FakeProvider):
        def fetch(self, location, local_date):
            raise ProviderError("upstream_rate_limited")

    with tempfile.TemporaryDirectory(prefix="kei-life-forecast-") as temp:
        root = Path(temp)
        repository, _, service = configured_service(root)
        service.refresh()
        path = repository.cache_path("2026-08-19")
        before = path.read_bytes()
        failed = LifeForecastService(repository, {"open_meteo": FailingProvider()}, clock=lambda: date(2026, 8, 19))
        with pytest.raises(LifeForecastError, match="upstream_rate_limited"):
            failed.refresh()
        assert path.read_bytes() == before


def test_concurrent_refreshes_are_coalesced_to_one_provider_call():
    class BlockingProvider(FakeProvider):
        def __init__(self):
            super().__init__()
            self.entered = threading.Event()
            self.release = threading.Event()

        def fetch(self, location, local_date):
            self.calls.append((location, local_date))
            self.entered.set()
            assert self.release.wait(2)
            return normalized_result(local_date)

    with tempfile.TemporaryDirectory(prefix="kei-life-forecast-") as temp:
        repository = LifeForecastRepository(temp)
        repository.save_config(LocationConfig("纽约", 40.7, -74.0, "open_meteo", False))
        provider = BlockingProvider()
        service = LifeForecastService(repository, {"open_meteo": provider}, clock=lambda: date(2026, 11, 1))
        with ThreadPoolExecutor(max_workers=2) as pool:
            first = pool.submit(service.refresh)
            assert provider.entered.wait(2)
            second = pool.submit(service.refresh)
            time.sleep(0.05)
            provider.release.set()
            results = [first.result(), second.result()]
        assert len(provider.calls) == 1
        assert {item["refresh_status"] for item in results} == {"refreshed", "coalesced"}


def test_dst_timezone_value_is_preserved_but_cache_key_uses_injected_local_date():
    class DSTProvider(FakeProvider):
        def fetch(self, location, local_date):
            self.calls.append((location, local_date))
            return normalized_result(local_date, timezone_name="America/New_York")

    with tempfile.TemporaryDirectory(prefix="kei-life-forecast-") as temp:
        day = date(2026, 11, 1)
        repository = LifeForecastRepository(temp)
        repository.save_config(LocationConfig("纽约", 40.7, -74.0, "open_meteo", False))
        service = LifeForecastService(repository, {"open_meteo": DSTProvider()}, clock=lambda: day)
        assert service.refresh()["forecast"]["timezone"] == "America/New_York"
        assert repository.cache_path(day).name == "2026-11-01.json"


def test_deterministic_fortune_is_stable_local_only_and_can_be_disabled():
    one = deterministic_fortune(date(2026, 8, 19))
    assert one == deterministic_fortune(date(2026, 8, 19))
    assert one != deterministic_fortune(date(2026, 8, 20))
    assert one["disclaimer"] == "娱乐内容、非事实预测"
    assert "sha256" in one["ruleset"]


def test_package_is_deterministic_and_contains_no_private_state():
    with tempfile.TemporaryDirectory(prefix="kei-life-forecast-package-") as temp:
        first = build_life_forecast_package(Path(temp) / "first.zip")
        second = build_life_forecast_package(Path(temp) / "second.zip")
        assert file_sha256(first) == file_sha256(second)
        with zipfile.ZipFile(first) as archive:
            names = set(archive.namelist())
            manifest = json.loads(archive.read("manifest.json"))
        assert manifest["id"] == "life_forecast"
        assert manifest["permissions"] == ["local_state", "network_download"]
        assert not any(name.endswith(("config.json", ".env")) for name in names)
        assert not any("cache/" in name or "runtime/" in name or "vendor/" in name for name in names)
        entry = json.loads((FEATURE_ROOT / "release" / "official-catalog-entry.json").read_text(encoding="utf-8"))
        assert entry["package_sha256"] == file_sha256(first)
        assert entry["package_size"] == first.stat().st_size
        import hashlib

        assert entry["manifest_sha256"] == hashlib.sha256(
            json.dumps(manifest, ensure_ascii=False, indent=2).encode("utf-8") + b"\n"
        ).hexdigest()


def test_dashboard_has_three_explicit_sections_and_no_direct_upstream_fetch():
    source = (FEATURE_ROOT / "package_source" / "dashboard" / "index.js").read_text(encoding="utf-8")
    for label in ("天气事实", "生活建议", "娱乐运势"):
        assert label in source
    assert "context.request('/api/v1/life-forecast/today')" in source
    assert "context.request('/api/v1/life-forecast/refresh'" in source
    assert "fetch(" not in source
    assert "localStorage" not in source and "sessionStorage" not in source
