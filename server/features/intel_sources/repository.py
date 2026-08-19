"""Atomic local persistence for the PK-115 intelligence-source registry."""

from __future__ import annotations

import json
import os
import tempfile
import threading
import time
from pathlib import Path
from typing import Any, Callable, Mapping, Optional, Tuple, TypeVar


def project_server_root() -> Path:
    """Find the server root from source and installed runtime packages."""
    source = Path(__file__).resolve()
    for parent in source.parents:
        if parent.name == "server":
            return parent
    return source.parents[2]


SERVER_ROOT = project_server_root()
DEFAULT_PATH = SERVER_ROOT / "data" / "intel_sources.json"


class IntelSourceStateError(RuntimeError):
    """The local source registry cannot be safely interpreted."""


class IntelSourcePersistenceError(RuntimeError):
    """The local source registry could not be atomically persisted."""


ResultT = TypeVar("ResultT")
Mutation = Callable[[Optional[Mapping[str, Any]]], Tuple[Optional[Mapping[str, Any]], ResultT]]
Replace = Callable[[Any, Any], None]

_LOCKS_GUARD = threading.Lock()
_PATH_LOCKS: dict[str, threading.RLock] = {}
_TRANSIENT_WINDOWS_REPLACE_ERRORS = frozenset({5, 32, 33})
_REPLACE_RETRY_DELAYS_SECONDS = (0.01, 0.025, 0.05, 0.1)


def _path_lock(path: Path) -> threading.RLock:
    key = str(path.resolve(strict=False)).casefold()
    with _LOCKS_GUARD:
        return _PATH_LOCKS.setdefault(key, threading.RLock())


class IntelSourceConfigRepository:
    """Read and update exactly one injected ``intel_sources.json`` path."""

    def __init__(self, path: str | Path = DEFAULT_PATH, *, replace: Replace = os.replace):
        self.path = Path(path)
        self._replace = replace
        self._lock = _path_lock(self.path)

    def _load_unlocked(self) -> Mapping[str, Any] | None:
        try:
            with self.path.open("r", encoding="utf-8") as handle:
                payload = json.load(handle)
        except FileNotFoundError:
            return None
        except (json.JSONDecodeError, OSError, UnicodeError) as exc:
            raise IntelSourceStateError("local source registry could not be read") from exc
        if not isinstance(payload, dict):
            raise IntelSourceStateError("local source registry root must be an object")
        return payload

    def load(self) -> Mapping[str, Any] | None:
        with self._lock:
            payload = self._load_unlocked()
            return dict(payload) if payload is not None else None

    def _replace_atomically(self, source: Path, target: Path) -> None:
        """Retry only Windows sharing/access races while retaining the path lock."""
        attempt = 0
        while True:
            try:
                self._replace(source, target)
                return
            except OSError as exc:
                winerror = getattr(exc, "winerror", None)
                if (
                    winerror not in _TRANSIENT_WINDOWS_REPLACE_ERRORS
                    or attempt >= len(_REPLACE_RETRY_DELAYS_SECONDS)
                ):
                    raise
                time.sleep(_REPLACE_RETRY_DELAYS_SECONDS[attempt])
                attempt += 1

    def _save_unlocked(self, payload: Mapping[str, Any]) -> None:
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
                json.dump(dict(payload), handle, ensure_ascii=False, indent=2)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            self._replace_atomically(temporary_path, self.path)
            temporary_path = None
        except (OSError, TypeError, ValueError) as exc:
            raise IntelSourcePersistenceError("local source registry could not be saved") from exc
        finally:
            if temporary_path is not None:
                try:
                    temporary_path.unlink(missing_ok=True)
                except OSError:
                    pass

    def save(self, payload: Mapping[str, Any]) -> None:
        with self._lock:
            self._save_unlocked(payload)

    def mutate(self, mutation: Mutation[ResultT]) -> ResultT:
        """Run one read/modify/write operation under the shared path lock."""
        with self._lock:
            next_payload, result = mutation(self._load_unlocked())
            if next_payload is not None:
                self._save_unlocked(next_payload)
            return result


__all__ = [
    "DEFAULT_PATH",
    "IntelSourceConfigRepository",
    "IntelSourcePersistenceError",
    "IntelSourceStateError",
    "project_server_root",
]
