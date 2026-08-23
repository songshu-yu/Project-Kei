"""Private configuration and daily cache storage owned only by PK-240."""

from __future__ import annotations

import json
import os
import threading
import uuid
from datetime import date
from pathlib import Path
from typing import Any, Callable, Mapping

from .contracts import LocationConfig
from .models import config_from_mapping


CONFIG_SCHEMA_VERSION = 1
CACHE_SCHEMA_VERSION = 1


class LifeForecastStateError(RuntimeError):
    pass


class LifeForecastPersistenceError(RuntimeError):
    pass


def default_data_dir() -> Path:
    for parent in Path(__file__).resolve().parents:
        if parent.name.casefold() == "server":
            return parent / "data" / "modules" / "life_forecast"
    raise RuntimeError("Project Kei server root could not be resolved")


class LifeForecastRepository:
    def __init__(
        self,
        data_dir: str | Path,
        *,
        replace: Callable[[str | Path, str | Path], None] = os.replace,
    ):
        self.data_dir = Path(data_dir)
        self.config_path = self.data_dir / "config.json"
        self.cache_dir = self.data_dir / "cache"
        self._replace = replace
        self._lock = threading.RLock()

    @staticmethod
    def default_config() -> LocationConfig:
        return LocationConfig(
            city="未配置",
            latitude=0.0,
            longitude=0.0,
            provider="disabled",
            fortune_enabled=False,
        )

    @staticmethod
    def _read_json(path: Path) -> Any:
        try:
            with path.open("r", encoding="utf-8") as handle:
                return json.load(handle)
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise LifeForecastStateError("local state could not be read") from exc

    def load_config(self) -> LocationConfig:
        with self._lock:
            if not self.config_path.exists():
                return self.default_config()
            value = self._read_json(self.config_path)
            if not isinstance(value, dict) or value.get("schema_version") != CONFIG_SCHEMA_VERSION:
                raise LifeForecastStateError("configuration schema is invalid")
            try:
                return config_from_mapping(value.get("configuration"))
            except ValueError as exc:
                raise LifeForecastStateError("configuration is invalid") from exc

    @staticmethod
    def _payload_for_config(config: LocationConfig) -> dict[str, Any]:
        return {
            "schema_version": CONFIG_SCHEMA_VERSION,
            "configuration": {
                "city": config.city,
                "latitude": config.latitude,
                "longitude": config.longitude,
                "provider": config.provider,
                "fortune_enabled": config.fortune_enabled,
            },
        }

    def _atomic_write(self, path: Path, payload: Mapping[str, Any]) -> None:
        temporary: Path | None = None
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
            with temporary.open("w", encoding="utf-8", newline="\n") as handle:
                json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            self._replace(temporary, path)
        except (OSError, TypeError, ValueError) as exc:
            if temporary is not None:
                try:
                    temporary.unlink(missing_ok=True)
                except OSError:
                    pass
            raise LifeForecastPersistenceError("local state could not be saved") from exc

    def save_config(self, config: LocationConfig) -> None:
        with self._lock:
            self._atomic_write(self.config_path, self._payload_for_config(config))

    def cache_path(self, local_date: date | str) -> Path:
        value = local_date.isoformat() if isinstance(local_date, date) else date.fromisoformat(str(local_date)).isoformat()
        return self.cache_dir / f"{value}.json"

    def load_cache(self, local_date: date) -> tuple[str, dict[str, Any] | None]:
        path = self.cache_path(local_date)
        with self._lock:
            if not path.exists():
                return "missing", None
            try:
                value = self._read_json(path)
                if not isinstance(value, dict):
                    raise ValueError
                if value.get("schema_version") != CACHE_SCHEMA_VERSION:
                    raise ValueError
                if value.get("local_date") != local_date.isoformat():
                    return "stale", None
                forecast = value.get("forecast")
                if not isinstance(forecast, dict):
                    raise ValueError
                return "available", value
            except (LifeForecastStateError, ValueError, TypeError):
                return "corrupted", None

    def save_cache(self, local_date: date, payload: Mapping[str, Any]) -> None:
        value = dict(payload)
        value["schema_version"] = CACHE_SCHEMA_VERSION
        value["local_date"] = local_date.isoformat()
        with self._lock:
            self._atomic_write(self.cache_path(local_date), value)


__all__ = [
    "CACHE_SCHEMA_VERSION",
    "CONFIG_SCHEMA_VERSION",
    "LifeForecastPersistenceError",
    "LifeForecastRepository",
    "LifeForecastStateError",
    "default_data_dir",
]
