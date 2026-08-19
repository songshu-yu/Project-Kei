"""Validated and atomic persistence for demon-slayer personal state."""

from __future__ import annotations

import copy
import json
import os
import tempfile
import threading
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, Tuple, TypeVar


def _default_data_dir() -> Path:
    source = Path(__file__).resolve()
    for parent in source.parents:
        if parent.name == "runtime":
            return parent.parent / "systems" / "data"
    return source.parents[2] / "systems" / "data"


DATA_DIR = _default_data_dir()
DEFAULT_STORE = DATA_DIR / "demon_slayer.json"

DEFAULT_WISHES = [
    {
        "id": "small_treat",
        "title": "完成一件让自己开心的小事",
        "cost": 60,
        "description": "一顿喜欢的饭、一集番、一次不内疚的休息。",
    },
    {
        "id": "half_day_quest",
        "title": "半天自由行动券",
        "cost": 160,
        "description": "拿来做自己喜欢的事，Kei 会正式批准。",
    },
    {
        "id": "big_wish",
        "title": "一个认真许下的大愿望",
        "cost": 360,
        "description": "买一样想要的东西，或者安排一次真正期待的体验。",
    },
]


class DemonSlayerStateError(RuntimeError):
    """The persisted personal state cannot be interpreted safely."""


class DemonSlayerPersistenceError(RuntimeError):
    """A state change could not be committed atomically."""


ResultT = TypeVar("ResultT")
Mutation = Callable[[Dict[str, Any]], Tuple[ResultT, bool]]

_LOCKS_GUARD = threading.Lock()
_PATH_LOCKS: Dict[str, threading.RLock] = {}


def _path_lock(path: Path) -> threading.RLock:
    key = str(path.resolve(strict=False)).casefold()
    with _LOCKS_GUARD:
        return _PATH_LOCKS.setdefault(key, threading.RLock())


class DemonSlayerStore:
    """Own one demon-slayer state file and serialize read/modify/write operations."""

    def __init__(self, path: Path = DEFAULT_STORE):
        self.path = Path(path)
        self._lock = _path_lock(self.path)

    @staticmethod
    def empty_state() -> Dict[str, Any]:
        return {
            "goals": [],
            "checkins": [],
            "wishes": copy.deepcopy(DEFAULT_WISHES),
            "redemptions": [],
            "bonuses": [],
            "points": 0,
            "created_at": datetime.now().isoformat(timespec="seconds"),
        }

    def _empty_state(self) -> Dict[str, Any]:
        """Compatibility alias for old callers without exposing persistence internals."""
        return self.empty_state()

    @staticmethod
    def validate_shape(state: Any) -> Dict[str, Any]:
        if not isinstance(state, dict):
            raise DemonSlayerStateError("demon-slayer state root must be an object")
        for key in ("goals", "checkins", "wishes", "redemptions", "bonuses"):
            if key not in state:
                state[key] = copy.deepcopy(DEFAULT_WISHES) if key == "wishes" else []
            if not isinstance(state[key], list):
                raise DemonSlayerStateError(f"demon-slayer state {key} must be a list")
            if any(not isinstance(item, dict) for item in state[key]):
                raise DemonSlayerStateError(f"demon-slayer state {key} entries must be objects")
        if "points" not in state:
            state["points"] = 0
        try:
            points = int(state["points"])
        except (TypeError, ValueError) as exc:
            raise DemonSlayerStateError("demon-slayer points must be an integer") from exc
        if points < 0:
            raise DemonSlayerStateError("demon-slayer points must not be negative")
        state["points"] = points
        for goal in state["goals"]:
            goal.setdefault("active", True)
            repeat_mode = str(goal.get("repeat_mode") or "recurring").lower()
            goal["repeat_mode"] = repeat_mode if repeat_mode in {"recurring", "once"} else "recurring"
        return state

    def _load_unlocked(self) -> Dict[str, Any]:
        if not self.path.exists():
            return self.empty_state()
        try:
            with self.path.open("r", encoding="utf-8") as handle:
                state = json.load(handle)
        except (json.JSONDecodeError, OSError, UnicodeError) as exc:
            raise DemonSlayerStateError("demon-slayer state could not be read") from exc
        return self.validate_shape(state)

    def load(self) -> Dict[str, Any]:
        with self._lock:
            return self._load_unlocked()

    def _save_unlocked(self, state: Dict[str, Any]) -> None:
        self.validate_shape(state)
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
            raise DemonSlayerPersistenceError("demon-slayer state could not be saved") from exc

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


DemonSlayerRepository = DemonSlayerStore


__all__ = [
    "DATA_DIR",
    "DEFAULT_STORE",
    "DEFAULT_WISHES",
    "DemonSlayerPersistenceError",
    "DemonSlayerRepository",
    "DemonSlayerStateError",
    "DemonSlayerStore",
]
