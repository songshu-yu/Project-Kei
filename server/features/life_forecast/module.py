"""Installable in-process registration entrypoint."""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any

from .providers import OpenMeteoWeatherProvider
from .repository import LifeForecastRepository, default_data_dir
from .router import create_life_forecast_router
from .service import LifeForecastService


_OWNER = "life_forecast_module_owner"


def register(app: Any) -> None:
    if getattr(app.state, _OWNER, None) is not None:
        return
    configured_data_dir = getattr(app.state, "life_forecast_data_dir", None)
    data_dir = Path(configured_data_dir) if configured_data_dir is not None else default_data_dir()
    provider = getattr(app.state, "life_forecast_open_meteo_provider", None)
    provider_owned = provider is None
    if provider is None:
        provider = OpenMeteoWeatherProvider()
    service = LifeForecastService(
        LifeForecastRepository(data_dir),
        {"open_meteo": provider},
        clock=getattr(app.state, "life_forecast_clock", None) or date.today,
    )
    before = list(app.routes)
    try:
        app.include_router(create_life_forecast_router(service))
    except Exception:
        app.router.routes[:] = before
        if provider_owned:
            provider.close()
        raise
    owner = {"service": service, "provider": provider, "provider_owned": provider_owned}
    app.state.life_forecast_service = service
    setattr(app.state, _OWNER, owner)


def unregister(app: Any) -> None:
    owner = getattr(app.state, _OWNER, None)
    if not isinstance(owner, dict):
        return
    if owner.get("provider_owned"):
        owner["provider"].close()
    if getattr(app.state, "life_forecast_service", None) is owner.get("service"):
        delattr(app.state, "life_forecast_service")
    if getattr(app.state, _OWNER, None) is owner:
        delattr(app.state, _OWNER)


__all__ = ["register", "unregister"]
