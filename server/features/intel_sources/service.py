"""Side-effect-free registry operations and Collector configuration snapshots."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Callable, Mapping, Sequence

from .models import (
    FIELD_NORMALIZERS,
    SOURCE_CONFIG_SCHEMA_VERSION,
    SOURCE_FIELDS,
    mutable_source_config,
    normalize_source_config,
    readonly_source_snapshot,
    require_source_field,
)
from .repository import IntelSourceConfigRepository, IntelSourceStateError


DefaultsProvider = Callable[[], Mapping[str, Sequence[object]]]
Clock = Callable[[], datetime]


def _default_clock() -> datetime:
    return datetime.now().astimezone()


class IntelSourceRegistry:
    """Manage local targets without querying profiles, Collectors, or briefing caches."""

    def __init__(
        self,
        repository: IntelSourceConfigRepository,
        *,
        defaults_provider: DefaultsProvider,
        clock: Clock = _default_clock,
    ):
        self.repository = repository
        self.defaults_provider = defaults_provider
        self.clock = clock

    def _defaults(self) -> dict[str, tuple[Any, ...]]:
        defaults = self.defaults_provider()
        return normalize_source_config({}, defaults)

    def _config_from_payload(
        self,
        payload: Mapping[str, Any] | None,
    ) -> dict[str, tuple[Any, ...]]:
        defaults = self._defaults()
        return defaults if payload is None else normalize_source_config(payload, defaults)

    @staticmethod
    def _updated_at(payload: Mapping[str, Any] | None) -> str | None:
        value = payload.get("updated_at") if payload is not None else None
        return value if isinstance(value, str) and value.strip() else None

    @staticmethod
    def _response(
        config: Mapping[str, Sequence[object]],
        *,
        local: bool,
        updated_at: str | None,
        warning: str | None = None,
        changed: bool | None = None,
    ) -> dict[str, Any]:
        response: dict[str, Any] = {
            **mutable_source_config(config),
            "schema_version": SOURCE_CONFIG_SCHEMA_VERSION,
            "using_local_override": local,
            "updated_at": updated_at,
        }
        if warning:
            response["load_warning"] = warning
        if changed is not None:
            response["changed"] = changed
        return response

    def read(self) -> dict[str, Any]:
        try:
            payload = self.repository.load()
            config = self._config_from_payload(payload)
        except (IntelSourceStateError, ValueError):
            return self._response(
                self._defaults(),
                local=False,
                updated_at=None,
                warning="local source registry is unavailable; using defaults",
            )
        return self._response(
            config,
            local=payload is not None,
            updated_at=self._updated_at(payload),
        )

    def replace(self, payload: object) -> dict[str, Any]:
        config = normalize_source_config(payload, self._defaults())
        updated_at = self.clock().isoformat(timespec="seconds")
        stored = {
            "schema_version": SOURCE_CONFIG_SCHEMA_VERSION,
            **mutable_source_config(config),
            "updated_at": updated_at,
        }
        self.repository.save(stored)
        return self._response(config, local=True, updated_at=updated_at, changed=True)

    def _mutate_field(
        self,
        field: object,
        operation: Callable[[list[Any]], bool],
    ) -> dict[str, Any]:
        field_name = require_source_field(field)

        def mutation(payload: Mapping[str, Any] | None) -> tuple[Mapping[str, Any] | None, dict[str, Any]]:
            config = self._config_from_payload(payload)
            mutable = mutable_source_config(config)
            changed = operation(mutable[field_name])
            if not changed:
                return None, self._response(
                    config,
                    local=payload is not None,
                    updated_at=self._updated_at(payload),
                    changed=False,
                )
            normalized = normalize_source_config(mutable, self._defaults())
            updated_at = self.clock().isoformat(timespec="seconds")
            stored = {
                "schema_version": SOURCE_CONFIG_SCHEMA_VERSION,
                **mutable_source_config(normalized),
                "updated_at": updated_at,
            }
            return stored, self._response(
                normalized,
                local=True,
                updated_at=updated_at,
                changed=True,
            )

        return self.repository.mutate(mutation)

    def add(self, field: object, value: object) -> dict[str, Any]:
        field_name = require_source_field(field)
        normalized = FIELD_NORMALIZERS[field_name](value)
        normalized_key = str(normalized).casefold()

        def operation(values: list[Any]) -> bool:
            if normalized_key in {str(item).casefold() for item in values}:
                return False
            values.append(normalized)
            return True

        return self._mutate_field(field_name, operation)

    def update(self, field: object, index: int, value: object) -> dict[str, Any]:
        field_name = require_source_field(field)
        if isinstance(index, bool) or not isinstance(index, int):
            raise ValueError("source target index must be an integer")
        normalized = FIELD_NORMALIZERS[field_name](value)

        def operation(values: list[Any]) -> bool:
            if index < 0 or index >= len(values):
                raise ValueError("source target index is out of range")
            if str(values[index]).casefold() == str(normalized).casefold():
                return False
            if any(
                position != index and str(item).casefold() == str(normalized).casefold()
                for position, item in enumerate(values)
            ):
                raise ValueError("source target already exists")
            values[index] = normalized
            return True

        return self._mutate_field(field_name, operation)

    def remove(self, field: object, index: int) -> dict[str, Any]:
        field_name = require_source_field(field)
        if isinstance(index, bool) or not isinstance(index, int):
            raise ValueError("source target index must be an integer")

        def operation(values: list[Any]) -> bool:
            if index < 0 or index >= len(values):
                raise ValueError("source target index is out of range")
            values.pop(index)
            return True

        return self._mutate_field(field_name, operation)

    def snapshot(self, source_ids: Sequence[object] | None = None) -> Mapping[str, Any]:
        """Read a defensive immutable snapshot suitable for ``CollectRequest``."""
        payload = self.repository.load()
        config = self._config_from_payload(payload)
        return readonly_source_snapshot(config, source_ids)


__all__ = ["IntelSourceRegistry"]
