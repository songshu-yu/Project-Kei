"""Validated, atomic persistence owned by the calendar module."""

from __future__ import annotations

import json
import os
import tempfile
import threading
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, Tuple, TypeVar


DATA_DIR = Path(__file__).resolve().parents[2] / "systems" / "data"
DEFAULT_STORE = DATA_DIR / "calendar_memo.json"


class CalendarStateError(RuntimeError):
    """The persisted calendar state cannot be safely interpreted."""


class CalendarPersistenceError(RuntimeError):
    """The calendar state could not be atomically persisted."""


ResultT = TypeVar("ResultT")
Mutation = Callable[[Dict[str, Any]], Tuple[ResultT, bool]]

_LOCKS_GUARD = threading.Lock()
_PATH_LOCKS: Dict[str, threading.RLock] = {}


def _path_lock(path: Path) -> threading.RLock:
    key = str(path.resolve(strict=False)).casefold()
    with _LOCKS_GUARD:
        return _PATH_LOCKS.setdefault(key, threading.RLock())


class CalendarMemoStore:
    """Read, validate and atomically update one calendar state file."""

    def __init__(self, path: Path = DEFAULT_STORE):
        self.path = Path(path)
        self._lock = _path_lock(self.path)

    @staticmethod
    def empty_state() -> Dict[str, Any]:
        return {
            "events": [],
            "skills": [],
            "practice_logs": [],
            "created_at": datetime.now().isoformat(timespec="seconds"),
        }

    def _empty_state(self) -> Dict[str, Any]:
        """Compatibility alias retained for older callers."""
        return self.empty_state()

    @staticmethod
    def validate(state: Any) -> Dict[str, Any]:
        if not isinstance(state, dict):
            raise CalendarStateError("calendar state root must be an object")
        for key in ("events", "skills", "practice_logs"):
            if key not in state:
                raise CalendarStateError(f"calendar state is missing {key}")
            if not isinstance(state[key], list):
                raise CalendarStateError(f"calendar state {key} must be a list")
            if any(not isinstance(item, dict) for item in state[key]):
                raise CalendarStateError(f"calendar state {key} entries must be objects")
        return state

    def _load_unlocked(self) -> Dict[str, Any]:
        if not self.path.exists():
            return self.empty_state()
        try:
            with self.path.open("r", encoding="utf-8") as handle:
                state = json.load(handle)
        except (json.JSONDecodeError, OSError, UnicodeError) as exc:
            raise CalendarStateError("calendar state could not be read") from exc
        return self.validate(state)

    def load(self) -> Dict[str, Any]:
        with self._lock:
            return self._load_unlocked()

    def _save_unlocked(self, state: Dict[str, Any]) -> None:
        self.validate(state)
        temporary_path: Path | None = None
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(
                "w",
                encoding="utf-8",
                dir=self.path.parent,
                prefix=f".{self.path.name}.",
                suffix=".tmp",
                delete=False,
            ) as handle:
                temporary_path = Path(handle.name)
                json.dump(state, handle, ensure_ascii=False, indent=2)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary_path, self.path)
        except (OSError, TypeError, ValueError) as exc:
            if temporary_path is not None:
                try:
                    temporary_path.unlink(missing_ok=True)
                except OSError:
                    pass
            raise CalendarPersistenceError("calendar state could not be saved") from exc

    def save(self, state: Dict[str, Any]) -> None:
        with self._lock:
            self._save_unlocked(state)

    def mutate(self, mutation: Mutation[ResultT]) -> ResultT:
        """Run one read/modify/write operation under the shared path lock."""
        with self._lock:
            state = self._load_unlocked()
            result, changed = mutation(state)
            if changed:
                self._save_unlocked(state)
            return result


CalendarRepository = CalendarMemoStore


__all__ = [
    "CalendarMemoStore",
    "CalendarPersistenceError",
    "CalendarRepository",
    "CalendarStateError",
    "DATA_DIR",
    "DEFAULT_STORE",
]
