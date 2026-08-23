"""Daily cache orchestration, deterministic advice and local entertainment."""

from __future__ import annotations

import hashlib
import threading
from datetime import date
from typing import Callable, Mapping

from .contracts import ForecastResult, LocationConfig, WeatherProvider
from .providers import ProviderError
from .repository import (
    LifeForecastPersistenceError,
    LifeForecastRepository,
    LifeForecastStateError,
)


FORTUNE_RULESET_VERSION = "local-date-sha256-v1"
FORTUNE_DISCLAIMER = "娱乐内容、非事实预测"
_FORTUNE_FOCUS = (
    "把最重要的小事先完成，会更轻松。",
    "适合给计划留一点机动空间。",
    "今天更适合稳步推进，不必追求一次到位。",
    "整理桌面或待办，可能带来好心情。",
    "留意一次真诚而简短的交流。",
)
_FORTUNE_COLOR = ("海盐蓝", "樱花粉", "薄荷绿", "暖杏色", "月夜蓝")
_FORTUNE_ACTION = (
    "喝一杯水",
    "散步十分钟",
    "提前准备明天的一件物品",
    "完成一个五分钟任务",
    "给自己留一段安静时间",
)


class LifeForecastError(RuntimeError):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def location_fingerprint(config: LocationConfig) -> str:
    raw = f"{config.provider}|{config.latitude:.6f}|{config.longitude:.6f}".encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def deterministic_fortune(local_date: date) -> dict[str, object]:
    digest = hashlib.sha256(
        f"{FORTUNE_RULESET_VERSION}|{local_date.isoformat()}".encode("utf-8")
    ).digest()
    return {
        "enabled": True,
        "disclaimer": FORTUNE_DISCLAIMER,
        "ruleset": FORTUNE_RULESET_VERSION,
        "date": local_date.isoformat(),
        "focus": _FORTUNE_FOCUS[digest[0] % len(_FORTUNE_FOCUS)],
        "color": _FORTUNE_COLOR[digest[1] % len(_FORTUNE_COLOR)],
        "small_action": _FORTUNE_ACTION[digest[2] % len(_FORTUNE_ACTION)],
    }


def _advice(forecast: ForecastResult) -> dict[str, dict[str, object]]:
    feels = forecast.apparent_temperature_c
    if feels <= 5:
        clothing = "体感偏冷，建议保暖外套并注意手脚保温。"
    elif feels <= 15:
        clothing = "体感较凉，建议外套或分层穿着。"
    elif feels <= 26:
        clothing = "体感舒适，按室内外温差准备薄外层。"
    else:
        clothing = "体感偏热，建议轻薄透气衣物并及时补水。"

    wet_codes = {51, 53, 55, 56, 57, 61, 63, 65, 66, 67, 71, 73, 75, 77, 80, 81, 82, 85, 86, 95, 96, 99}
    umbrella = forecast.precipitation_probability_max_pct >= 40 or forecast.condition_code in wet_codes
    travel = "建议带伞，并为降水预留出行时间。" if umbrella else "降水风险较低，仍可按实际云况调整出行。"
    if forecast.wind_speed_max_kmh >= 50:
        travel += " 风力较强，避免松散物品和高空暴露区域。"

    if forecast.uv_index_max is None:
        uv = {"status": "unavailable", "text": "上游未提供紫外线指数。"}
    elif forecast.uv_index_max < 3:
        uv = {"status": "available", "text": "紫外线较低，长时间户外仍建议基础防护。"}
    elif forecast.uv_index_max < 6:
        uv = {"status": "available", "text": "紫外线中等，建议使用遮阳或防晒措施。"}
    elif forecast.uv_index_max < 8:
        uv = {"status": "available", "text": "紫外线较高，减少正午暴露并加强防晒。"}
    else:
        uv = {"status": "available", "text": "紫外线很高，尽量避开正午户外并做好全面防护。"}

    if forecast.us_aqi is None:
        air = {"status": "unavailable", "text": "上游未提供可用空气质量指数。"}
    elif forecast.us_aqi <= 50:
        air = {"status": "available", "text": "空气质量良好，正常安排户外活动。"}
    elif forecast.us_aqi <= 100:
        air = {"status": "available", "text": "空气质量一般，敏感人群可酌情减少长时间户外活动。"}
    elif forecast.us_aqi <= 150:
        air = {"status": "available", "text": "敏感人群可能受影响，建议缩短高强度户外活动。"}
    else:
        air = {"status": "available", "text": "空气质量较差，建议减少户外暴露并参考当地官方指引。"}

    return {
        "clothing": {"status": "available", "text": clothing},
        "travel_umbrella": {
            "status": "available",
            "text": travel,
            "bring_umbrella": umbrella,
        },
        "uv": uv,
        "air_quality": air,
    }


class LifeForecastService:
    def __init__(
        self,
        repository: LifeForecastRepository,
        providers: Mapping[str, WeatherProvider],
        *,
        clock: Callable[[], date] = date.today,
    ):
        self.repository = repository
        self.providers = dict(providers)
        self.clock = clock
        self._refresh_lock = threading.Lock()
        self._refresh_generation = 0

    @staticmethod
    def _config_dict(config: LocationConfig) -> dict[str, object]:
        return {
            "city": config.city,
            "latitude": config.latitude,
            "longitude": config.longitude,
            "provider": config.provider,
            "fortune_enabled": config.fortune_enabled,
            "privacy_notice": (
                "配置只保存在本机；选择 Open-Meteo 并显式刷新时仅发送经纬度，"
                "城市标签、娱乐内容、生日和星座不会发送。"
            ),
        }

    def get_config(self) -> dict[str, object]:
        try:
            return self._config_dict(self.repository.load_config())
        except LifeForecastStateError as exc:
            raise LifeForecastError("configuration_invalid") from exc

    def save_config(self, config: LocationConfig) -> dict[str, object]:
        try:
            self.repository.save_config(config)
        except LifeForecastPersistenceError as exc:
            raise LifeForecastError("configuration_save_failed") from exc
        return self._config_dict(config)

    def get_today(self) -> dict[str, object]:
        local_date = self.clock()
        try:
            config = self.repository.load_config()
        except LifeForecastStateError as exc:
            raise LifeForecastError("configuration_invalid") from exc
        cache_status, cached = self.repository.load_cache(local_date)
        if cached is not None and cached.get("location_fingerprint") != location_fingerprint(config):
            cache_status, cached = "stale_configuration", None
        forecast = None if cached is None else cached.get("forecast")
        advice = None if cached is None else cached.get("life_advice")
        return {
            "schema_version": 1,
            "date": local_date.isoformat(),
            "city": config.city,
            "provider": config.provider,
            "cache_status": cache_status,
            "forecast": forecast,
            "life_advice": advice,
            "fortune": (
                deterministic_fortune(local_date)
                if config.fortune_enabled
                else {
                    "enabled": False,
                    "disclaimer": FORTUNE_DISCLAIMER,
                    "ruleset": FORTUNE_RULESET_VERSION,
                }
            ),
        }

    def refresh(self) -> dict[str, object]:
        generation = self._refresh_generation
        with self._refresh_lock:
            if generation != self._refresh_generation:
                response = self.get_today()
                response["refresh_status"] = "coalesced"
                return response
            try:
                config = self.repository.load_config()
                if config.provider == "disabled":
                    raise LifeForecastError("provider_disabled")
                provider = self.providers.get(config.provider)
                if provider is None:
                    raise LifeForecastError("provider_unavailable")
                local_date = self.clock()
                result = provider.fetch(config.provider_view(), local_date)
                if result.provider != config.provider or result.local_date != local_date.isoformat():
                    raise LifeForecastError("provider_contract_invalid")
                payload = {
                    "location_fingerprint": location_fingerprint(config),
                    "forecast": result.to_dict(),
                    "life_advice": _advice(result),
                }
                self.repository.save_cache(local_date, payload)
                response = self.get_today()
                response["refresh_status"] = "refreshed"
                return response
            except ProviderError as exc:
                raise LifeForecastError(exc.code) from exc
            except LifeForecastStateError as exc:
                raise LifeForecastError("configuration_invalid") from exc
            except LifeForecastPersistenceError as exc:
                raise LifeForecastError("cache_save_failed") from exc
            finally:
                self._refresh_generation += 1


__all__ = [
    "FORTUNE_DISCLAIMER",
    "FORTUNE_RULESET_VERSION",
    "LifeForecastError",
    "LifeForecastService",
    "deterministic_fortune",
    "location_fingerprint",
]
