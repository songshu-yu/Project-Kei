"""Atomic repositories for the two QQ scheduler configuration files."""
from __future__ import annotations

import json
import os
import threading
import uuid
from pathlib import Path
from typing import Any, Callable, Dict


ScheduleValidator = Callable[[Dict[str, Any]], object]


class ScheduleStateError(RuntimeError):
    """The existing schedule cannot be safely interpreted."""


class SchedulePersistenceError(RuntimeError):
    """A schedule update could not be atomically committed."""


class QQScheduleRepository:
    """Own both schedule files while keeping their validation in the service."""

    def __init__(self, daily_path: str | Path, life_support_path: str | Path) -> None:
        self.daily_path = Path(daily_path)
        self.life_support_path = Path(life_support_path)
        self._locks = {
            "daily": threading.RLock(),
            "life_support": threading.RLock(),
        }

    def read_daily(self) -> dict[str, Any] | None:
        return self._read(self.daily_path, self._locks["daily"])

    def read_life_support(self) -> dict[str, Any] | None:
        return self._read(self.life_support_path, self._locks["life_support"])

    def replace_daily(
        self,
        payload: dict[str, Any],
        *,
        validate_existing: ScheduleValidator,
    ) -> dict[str, Any]:
        return self._replace_validated(
            self.daily_path,
            payload,
            self._locks["daily"],
            validate_existing,
        )

    def replace_life_support(
        self,
        payload: dict[str, Any],
        *,
        validate_existing: ScheduleValidator,
    ) -> dict[str, Any]:
        return self._replace_validated(
            self.life_support_path,
            payload,
            self._locks["life_support"],
            validate_existing,
        )

    @staticmethod
    def _read(target: Path, lock: threading.RLock) -> dict[str, Any] | None:
        with lock:
            return QQScheduleRepository._read_unlocked(target)

    @staticmethod
    def _read_unlocked(target: Path) -> dict[str, Any] | None:
        try:
            raw = target.read_text(encoding="utf-8")
        except FileNotFoundError:
            return None
        except OSError as exc:
            raise ScheduleStateError("schedule_unreadable") from exc
        try:
            payload = json.loads(raw)
        except (TypeError, ValueError, json.JSONDecodeError) as exc:
            raise ScheduleStateError("schedule_corrupt") from exc
        if not isinstance(payload, dict):
            raise ScheduleStateError("schedule_invalid_root")
        return payload

    @staticmethod
    def _replace_validated(
        target: Path,
        payload: dict[str, Any],
        lock: threading.RLock,
        validate_existing: ScheduleValidator,
    ) -> dict[str, Any]:
        """Validate the current file and replace it in one repository lock domain."""
        with lock:
            existing = QQScheduleRepository._read_unlocked(target)
            if existing is not None:
                validate_existing(existing)
            return QQScheduleRepository._save_unlocked(target, payload)

    @staticmethod
    def _save_unlocked(target: Path, payload: dict[str, Any]) -> dict[str, Any]:
        serialized = f"{json.dumps(payload, ensure_ascii=False, indent=2)}\n"
        temp_path = target.with_name(f".{target.name}.{os.getpid()}.{uuid.uuid4().hex}.tmp")
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            with temp_path.open("x", encoding="utf-8", newline="\n") as handle:
                handle.write(serialized)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp_path, target)
        except (OSError, ValueError) as exc:
            try:
                temp_path.unlink(missing_ok=True)
            except OSError:
                pass
            raise SchedulePersistenceError("schedule_save_failed") from exc
        return dict(payload)
