"""PK-241 consumer contracts with fake providers and temporary state only."""
from __future__ import annotations

import asyncio
import json
import tempfile
import threading
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import _path_setup  # noqa: F401
import httpx
from fastapi import FastAPI

from features.daily_briefing.models import (
    BriefingDocument,
    LIFE_FORECAST_PROJECTION_FIELD_IDS,
    LifeForecastProjectionUpdate,
)
from features.daily_briefing.repository import (
    BriefingRepository,
    LifeForecastProjectionPersistenceError,
    LifeForecastProjectionRepository,
)
from features.daily_briefing.router import create_briefing_router
from features.daily_briefing.service import BriefingService


NOW = datetime(2030, 1, 2, 8, 0, tzinfo=timezone.utc)


class NoCollectorGateway:
    async def collect(self, _request):
        raise AssertionError("read-only projection must not collect")


class FakeTodayProvider:
    def __init__(self, result):
        self.result = result
        self.calls = 0

    def __call__(self):
        self.calls += 1
        return self.result


def all_fields(value: bool = False, **overrides: bool) -> dict[str, bool]:
    result = {key: value for key in LIFE_FORECAST_PROJECTION_FIELD_IDS}
    result.update(overrides)
    return result


def fake_today(local_date: str = "2030-01-02") -> dict[str, object]:
    return {
        "cache_status": "available",
        "city": "must-not-leak",
        "provider": "must-not-leak",
        "forecast": {
            "provider": "must-not-leak",
            "local_date": local_date,
            "timezone": "must-not-leak",
            "condition_code": 2,
            "condition": "多云",
            "current_temperature_c": 16,
            "apparent_temperature_c": 15.5,
            "temperature_max_c": 20,
            "temperature_min_c": 11,
            "precipitation_probability_max_pct": 35,
            "wind_speed_max_kmh": 18,
            "uv_index_max": 4,
            "us_aqi": 42,
            "warnings_status": "available",
            "warnings": [{"title": "测试预警", "severity": "低", "description": "测试说明"}],
            "fetched_at": "must-not-leak",
            "attribution": "must-not-leak",
        },
        "life_advice": {
            "clothing": {"status": "available", "text": "带一件薄外套"},
            "travel_umbrella": {
                "status": "available",
                "text": "可带折叠伞",
                "bring_umbrella": True,
            },
            "uv": {"status": "available", "text": "适度防晒"},
            "air_quality": {"status": "available", "text": "适合通风"},
        },
        "fortune": {
            "enabled": True,
            "date": local_date,
            "disclaimer": "娱乐内容、非事实预测",
            "ruleset": "local-date-sha256-v1",
            "focus": "整理",
            "color": "蓝色",
            "small_action": "收拾桌面",
        },
    }


def document() -> BriefingDocument:
    stamp = "2030-01-02T08:00:00Z"
    return BriefingDocument(
        local_date="2030-01-02",
        timezone="Asia/Shanghai",
        items=[],
        coverage={},
        warnings=[],
        text="fixed briefing",
        script="fixed script",
        fetched=False,
        rewritten=False,
        rewrite_status="fallback",
        created_at=stamp,
        updated_at=stamp,
    )


async def check_projection_http(root: Path) -> None:
    briefing_repository = BriefingRepository(root)
    briefing_repository.save(document())
    cache_path = briefing_repository.cache_path("2030-01-02")
    original_cache = cache_path.read_bytes()
    provider = FakeTodayProvider(fake_today())
    projection_repository = LifeForecastProjectionRepository(root)
    core = BriefingService(
        NoCollectorGateway(),
        briefing_repository,
        clock=lambda: NOW,
        life_forecast_projection_repository=projection_repository,
        life_forecast_provider=provider,
    )
    service = SimpleNamespace(core=core)
    app = FastAPI()
    app.include_router(
        create_briefing_router(lambda: service, local_request_guard=lambda _request: True)
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        configuration = await client.get(
            "/api/v1/briefing/life-forecast-projection"
        )
        assert configuration.status_code == 200
        assert configuration.json() == {
            "schema_version": 1,
            "enabled": False,
            "fields": all_fields(),
        }
        today = await client.get("/api/v1/briefing/today")
        assert today.status_code == 200
        assert today.json()["life_forecast"] == {
            "enabled": False,
            "ready": False,
            "cache_status": "disabled",
            "fields": {},
        }
        assert provider.calls == 0

        strict = await client.put(
            "/api/v1/briefing/life-forecast-projection",
            json={"enabled": True, "fields": {"weather_condition": True}},
        )
        assert strict.status_code == 422
        extra = await client.put(
            "/api/v1/briefing/life-forecast-projection",
            json={"enabled": True, "fields": {**all_fields(), "extra": False}},
        )
        assert extra.status_code == 422
        coercion = await client.put(
            "/api/v1/briefing/life-forecast-projection",
            json={"enabled": 1, "fields": all_fields()},
        )
        assert coercion.status_code == 422

        saved = await client.put(
            "/api/v1/briefing/life-forecast-projection",
            json={
                "enabled": True,
                "fields": all_fields(
                    weather_condition=True,
                    temperature_range=True,
                    clothing=True,
                    fortune=True,
                ),
            },
        )
        assert saved.status_code == 200
        today = await client.get("/api/v1/briefing/today")
        projection = today.json()["life_forecast"]
        assert provider.calls == 1
        assert projection["ready"] is True
        assert set(projection["fields"]) == {
            "weather_condition",
            "temperature_range",
            "clothing",
            "fortune",
        }
        serialized = json.dumps(projection, ensure_ascii=False)
        for forbidden in (
            "must-not-leak",
            "city",
            "provider",
            "timezone",
            "attribution",
            "fetched_at",
        ):
            assert forbidden not in serialized
        assert "娱乐内容、非事实预测" in serialized
        assert cache_path.read_bytes() == original_cache

        provider.result = fake_today()
        provider.result["fortune"]["enabled"] = False
        no_fortune = await client.get("/api/v1/briefing/today")
        assert "fortune" not in no_fortune.json()["life_forecast"]["fields"]
        assert provider.calls == 2

        provider.result = fake_today("2029-12-31")
        stale = await client.get("/api/v1/briefing/today")
        assert stale.json()["life_forecast"]["ready"] is False
        assert stale.json()["life_forecast"]["fields"] == {}
        assert provider.calls == 3
        assert cache_path.read_bytes() == original_cache


def check_projection_storage(root: Path) -> None:
    repository = LifeForecastProjectionRepository(root)
    update = LifeForecastProjectionUpdate(
        enabled=True,
        fields=all_fields(weather_condition=True),
    )
    repository.save(update)
    original = repository.path.read_bytes()

    failing = LifeForecastProjectionRepository(
        root,
        replace=lambda _source, _target: (_ for _ in ()).throw(OSError("fake")),
    )
    try:
        failing.save(
            LifeForecastProjectionUpdate(enabled=False, fields=all_fields())
        )
        raise AssertionError("replace failure must be finite")
    except LifeForecastProjectionPersistenceError:
        pass
    assert repository.path.read_bytes() == original
    assert not list(repository.path.parent.glob("*.tmp"))

    repository.path.write_text('{"schema_version":999}', encoding="utf-8")
    corrupt = repository.path.read_bytes()
    loaded = repository.load()
    assert loaded.enabled is False
    assert all(not getattr(loaded.fields, key) for key in LIFE_FORECAST_PROJECTION_FIELD_IDS)
    assert repository.path.read_bytes() == corrupt

    repository.path.unlink()
    concurrent = LifeForecastProjectionRepository(root)
    errors: list[Exception] = []

    def save(index: int) -> None:
        try:
            concurrent.save(
                LifeForecastProjectionUpdate(
                    enabled=index % 2 == 0,
                    fields=all_fields(weather_condition=index % 2 == 1),
                )
            )
        except Exception as exc:  # pragma: no cover - assertion reports it
            errors.append(exc)

    threads = [threading.Thread(target=save, args=(index,)) for index in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert errors == []
    payload = json.loads(concurrent.path.read_text(encoding="utf-8"))
    assert payload["schema_version"] == 1
    assert set(payload["fields"]) == set(LIFE_FORECAST_PROJECTION_FIELD_IDS)
    assert all(type(value) is bool for value in payload["fields"].values())
    assert not list(concurrent.path.parent.glob("*.tmp"))


async def main() -> int:
    with tempfile.TemporaryDirectory(prefix="kei-pk241-") as temp_dir:
        root = Path(temp_dir)
        check_projection_storage(root / "storage")
        await check_projection_http(root / "http")
    print("life forecast consumer Python tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
