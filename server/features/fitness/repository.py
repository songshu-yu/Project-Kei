"""Validated, locked and atomic persistence owned by the fitness module."""

from __future__ import annotations

import json
import os
import tempfile
import threading
import time
from pathlib import Path
from typing import Any, Callable, Dict, Tuple, TypeVar


DEFAULT_STORE = Path(__file__).resolve().parents[2] / "data" / "fitness_checkins.json"


class FitnessStateError(RuntimeError):
    """The persisted fitness state cannot be safely interpreted."""


class FitnessPersistenceError(RuntimeError):
    """The fitness state could not be atomically persisted."""


ResultT = TypeVar("ResultT")
Mutation = Callable[[Dict[str, Any]], Tuple[ResultT, bool]]

_LOCKS_GUARD = threading.Lock()
_PATH_LOCKS: Dict[str, threading.RLock] = {}
_REPLACE_RETRY_DELAYS = (0.01, 0.025, 0.05)


def _path_lock(path: Path) -> threading.RLock:
    key = str(path.resolve(strict=False)).casefold()
    with _LOCKS_GUARD:
        return _PATH_LOCKS.setdefault(key, threading.RLock())


def _replace_atomically(source: Path, destination: Path) -> None:
    """Replace a closed temp file, tolerating brief Windows sharing denials."""

    for attempt in range(len(_REPLACE_RETRY_DELAYS) + 1):
        try:
            os.replace(source, destination)
            return
        except PermissionError:
            if attempt >= len(_REPLACE_RETRY_DELAYS):
                raise
            time.sleep(_REPLACE_RETRY_DELAYS[attempt])


class FitnessRepository:
    """Own one fitness JSON file and serialize every read/modify/write cycle."""

    def __init__(self, path: Path = DEFAULT_STORE):
        self.path = Path(path)
        self._lock = _path_lock(self.path)

    @staticmethod
    def empty_state() -> Dict[str, Any]:
        return {"checkins": [], "rewards": []}

    def _empty_state(self) -> Dict[str, Any]:
        """Compatibility alias for the former store."""
        return self.empty_state()

    @staticmethod
    def validate(state: Any) -> Dict[str, Any]:
        if not isinstance(state, dict):
            raise FitnessStateError("fitness state root must be an object")
        for key in ("checkins", "rewards"):
            if key not in state or not isinstance(state[key], list):
                raise FitnessStateError(f"fitness state {key} must be a list")
            if any(not isinstance(item, dict) for item in state[key]):
                raise FitnessStateError(f"fitness state {key} entries must be objects")

        for item in state["checkins"]:
            if "note" in item and not isinstance(item["note"], str):
                raise FitnessStateError("fitness check-in note must be text")
            if "created_at" in item and not isinstance(item["created_at"], str):
                raise FitnessStateError("fitness check-in timestamp must be text")

        for reward in state["rewards"]:
            if not isinstance(reward.get("key"), str) or not reward["key"]:
                raise FitnessStateError("fitness reward key is invalid")
            if not isinstance(reward.get("date"), str):
                raise FitnessStateError("fitness reward date is invalid")
            streak = reward.get("streak")
            if isinstance(streak, bool) or not isinstance(streak, int) or streak <= 0:
                raise FitnessStateError("fitness reward streak is invalid")
            if not isinstance(reward.get("text"), str):
                raise FitnessStateError("fitness reward text is invalid")
            if "created_at" in reward and not isinstance(reward["created_at"], str):
                raise FitnessStateError("fitness reward timestamp is invalid")
        return state

    def _load_unlocked(self) -> Dict[str, Any]:
        if not self.path.exists():
            return self.empty_state()
        try:
            with self.path.open("r", encoding="utf-8") as handle:
                state = json.load(handle)
        except (json.JSONDecodeError, OSError, UnicodeError) as exc:
            raise FitnessStateError("fitness state could not be read") from exc
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
            _replace_atomically(temporary_path, self.path)
        except (OSError, TypeError, ValueError) as exc:
            if temporary_path is not None:
                try:
                    temporary_path.unlink(missing_ok=True)
                except OSError:
                    pass
            raise FitnessPersistenceError("fitness state could not be saved") from exc

    def save(self, state: Dict[str, Any]) -> None:
        with self._lock:
            self._save_unlocked(state)

    def mutate(self, mutation: Mutation[ResultT]) -> ResultT:
        with self._lock:
            state = self._load_unlocked()
            result, changed = mutation(state)
            if changed:
                self._save_unlocked(state)
            return result


FitnessCheckinStore = FitnessRepository


__all__ = [
    "DEFAULT_STORE",
    "FitnessCheckinStore",
    "FitnessPersistenceError",
    "FitnessRepository",
    "FitnessStateError",
]
