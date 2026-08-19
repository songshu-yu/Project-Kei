"""Locked, validated and atomic persistence for PK-160 personal data."""

from __future__ import annotations

import copy
import hashlib
import json
import os
import re
import tempfile
import threading
from pathlib import Path
from typing import Any, Callable, TypeVar

from .event_catalog import EVENTS, STAT_LIMITS
from .models import MemoryEntry


SERVER_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_RELATIONSHIP_PATH = SERVER_ROOT / "data" / "affection_state.json"
DEFAULT_MEMORY_PATH = SERVER_ROOT / "data" / "memories.json"

MAX_STORED_MEMORY_LENGTH = 20_000
ALLOWED_MEMORY_SOURCES = frozenset({"user", "api", "command"})
_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
_REQUEST_ID_PATTERN = re.compile(r"^[A-Za-z0-9._:-]{1,96}$")
_EVENTS_BY_ID = {event["id"]: event for event in EVENTS}
_FROZEN_EVENT_FIELDS = ("id", "title", "scene", "text", "contexts", "weight", "voice_cue", "choices")
_ACTIVE_EVENT_FIELDS = frozenset((*_FROZEN_EVENT_FIELDS, "instance_id", "created_at"))


class RelationshipStateError(RuntimeError):
    """Persisted relationship state is unreadable or structurally unsafe."""


class RelationshipPersistenceError(RuntimeError):
    """Relationship state could not be atomically committed."""


class MemoryStateError(RuntimeError):
    """Persisted memory state is unreadable or structurally unsafe."""


class MemoryPersistenceError(RuntimeError):
    """Memory state could not be atomically committed."""


_LOCKS_GUARD = threading.Lock()
_PATH_LOCKS: dict[str, threading.RLock] = {}


def _path_lock(path: Path) -> threading.RLock:
    key = str(path.resolve(strict=False)).casefold()
    with _LOCKS_GUARD:
        return _PATH_LOCKS.setdefault(key, threading.RLock())


def _write_json_atomic(path: Path, payload: Any, error_type: type[RuntimeError], message: str) -> None:
    temporary_path: Path | None = None
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            "w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            temporary_path = Path(handle.name)
            json.dump(payload, handle, ensure_ascii=False, indent=2)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_path, path)
    except (OSError, TypeError, ValueError) as exc:
        if temporary_path is not None:
            try:
                temporary_path.unlink(missing_ok=True)
            except OSError:
                pass
        raise error_type(message) from exc


ResultT = TypeVar("ResultT")


class RelationshipRepository:
    """Own one affection state file without caching mutable state."""

    def __init__(self, path: str | Path = DEFAULT_RELATIONSHIP_PATH):
        self.path = Path(path)
        self._lock = _path_lock(self.path)

    @staticmethod
    def empty_state() -> dict[str, Any]:
        return {
            "stats": {"affection": 50, "trust": 10, "mood": 60, "energy": 70},
            "active_event": None,
            "history": [],
        }

    def _empty_state(self) -> dict[str, Any]:
        return self.empty_state()

    def exists(self) -> bool:
        return self.path.is_file()

    @staticmethod
    def validate(state: Any) -> dict[str, Any]:
        if not isinstance(state, dict):
            raise RelationshipStateError("relationship state root must be an object")
        normalized = copy.deepcopy(state)
        stats = normalized.get("stats")
        if not isinstance(stats, dict):
            raise RelationshipStateError("relationship stats must be an object")
        for key, (low, high) in STAT_LIMITS.items():
            value = stats.get(key)
            if isinstance(value, bool) or not isinstance(value, int) or not low <= value <= high:
                raise RelationshipStateError("relationship stats are invalid")
        history = normalized.get("history")
        if not isinstance(history, list) or any(not isinstance(item, dict) for item in history):
            raise RelationshipStateError("relationship history is invalid")
        active_event = normalized.get("active_event")
        if active_event is not None:
            if not isinstance(active_event, dict):
                raise RelationshipStateError("relationship active event is invalid")
            event_id = active_event.get("id")
            catalog_event = _EVENTS_BY_ID.get(event_id) if isinstance(event_id, str) else None
            if set(active_event) - _ACTIVE_EVENT_FIELDS or catalog_event is None or any(
                active_event.get(field) != catalog_event.get(field)
                for field in _FROZEN_EVENT_FIELDS
            ):
                raise RelationshipStateError("relationship active event does not match the frozen catalog")
            instance_id = active_event.get("instance_id")
            if instance_id is None:
                identity_payload = json.dumps(
                    {
                        "event_id": event_id,
                        "stats": stats,
                        "history_count": len(history),
                    },
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                ).encode("utf-8")
                active_event["instance_id"] = "legacy_" + hashlib.sha256(identity_payload).hexdigest()[:24]
            elif not isinstance(instance_id, str) or not _ID_PATTERN.fullmatch(instance_id):
                raise RelationshipStateError("relationship active event identity is invalid")
            created_at = active_event.get("created_at")
            if created_at is None:
                active_event["created_at"] = ""
            elif not isinstance(created_at, str) or len(created_at) > 64:
                raise RelationshipStateError("relationship active event timestamp is invalid")
            choices = active_event.get("choices")
            if not isinstance(choices, list) or any(not isinstance(choice, dict) for choice in choices):
                raise RelationshipStateError("relationship active event choices are invalid")
        return normalized

    def _load_unlocked(self) -> dict[str, Any]:
        if not self.path.exists():
            return self.empty_state()
        try:
            with self.path.open("r", encoding="utf-8") as handle:
                state = json.load(handle)
        except (json.JSONDecodeError, OSError, UnicodeError) as exc:
            raise RelationshipStateError("relationship state could not be read") from exc
        return self.validate(state)

    def load(self) -> dict[str, Any]:
        with self._lock:
            return self._load_unlocked()

    def _save_unlocked(self, state: dict[str, Any]) -> None:
        normalized = self.validate(state)
        _write_json_atomic(
            self.path,
            normalized,
            RelationshipPersistenceError,
            "relationship state could not be saved",
        )

    def save(self, state: dict[str, Any]) -> None:
        with self._lock:
            self._save_unlocked(state)

    def mutate(self, mutation: Callable[[dict[str, Any]], tuple[ResultT, bool]]) -> ResultT:
        with self._lock:
            state = self._load_unlocked()
            result, changed = mutation(state)
            if changed:
                self._save_unlocked(state)
            return result


def _safe_text(value: Any, *, maximum: int, field_name: str) -> str:
    if not isinstance(value, str):
        raise MemoryStateError(f"memory {field_name} must be text")
    normalized = value.strip()
    if not normalized or len(normalized) > maximum or any(ord(char) < 32 and char not in "\n\t" for char in normalized):
        raise MemoryStateError(f"memory {field_name} is invalid")
    return normalized


def _safe_tags(value: Any) -> list[str]:
    if not isinstance(value, list) or len(value) > 32:
        raise MemoryStateError("memory tags are invalid")
    tags: list[str] = []
    seen: set[str] = set()
    for item in value:
        tag = _safe_text(item, maximum=40, field_name="tag")
        marker = tag.casefold()
        if marker not in seen:
            tags.append(tag)
            seen.add(marker)
    return tags


class MemoryRepository:
    """Own one memory file and serialize every read/modify/write transaction."""

    def __init__(self, path: str | Path = DEFAULT_MEMORY_PATH):
        self.path = Path(path)
        self._lock = _path_lock(self.path)

    def exists(self) -> bool:
        return self.path.is_file()

    @staticmethod
    def validate(payload: Any) -> list[MemoryEntry]:
        if not isinstance(payload, dict) or not isinstance(payload.get("memories"), list):
            raise MemoryStateError("memory state root is invalid")
        entries: list[MemoryEntry] = []
        known_ids: set[str] = set()
        known_requests: set[str] = set()
        for raw in payload["memories"]:
            if not isinstance(raw, dict):
                raise MemoryStateError("memory entry is invalid")
            memory_id = raw.get("id")
            if not isinstance(memory_id, str) or not _ID_PATTERN.fullmatch(memory_id) or memory_id in known_ids:
                raise MemoryStateError("memory identity is invalid")
            content = _safe_text(raw.get("content"), maximum=MAX_STORED_MEMORY_LENGTH, field_name="content")
            tags = _safe_tags(raw.get("tags", []))
            source = raw.get("source", "user")
            if source not in ALLOWED_MEMORY_SOURCES:
                raise MemoryStateError("memory source is invalid")
            created_at = raw.get("created_at", "")
            if not isinstance(created_at, str) or len(created_at) > 64:
                raise MemoryStateError("memory timestamp is invalid")
            request_id = raw.get("request_id")
            if request_id is not None:
                if not isinstance(request_id, str) or not _REQUEST_ID_PATTERN.fullmatch(request_id) or request_id in known_requests:
                    raise MemoryStateError("memory request identity is invalid")
                known_requests.add(request_id)
            entries.append(MemoryEntry(memory_id, content, tags, source, created_at, request_id))
            known_ids.add(memory_id)
        return entries

    def _load_unlocked(self) -> list[MemoryEntry]:
        if not self.path.exists():
            return []
        try:
            with self.path.open("r", encoding="utf-8") as handle:
                payload = json.load(handle)
        except (json.JSONDecodeError, OSError, UnicodeError) as exc:
            raise MemoryStateError("memory state could not be read") from exc
        return self.validate(payload)

    def load(self) -> list[MemoryEntry]:
        with self._lock:
            return self._load_unlocked()

    def _save_unlocked(self, entries: list[MemoryEntry]) -> None:
        payload = {"memories": [entry.to_storage_dict() for entry in entries]}
        self.validate(payload)
        _write_json_atomic(self.path, payload, MemoryPersistenceError, "memory state could not be saved")

    def save(self, entries: list[MemoryEntry]) -> None:
        with self._lock:
            self._save_unlocked(entries)

    def mutate(self, mutation: Callable[[list[MemoryEntry]], tuple[ResultT, bool]]) -> ResultT:
        with self._lock:
            entries = self._load_unlocked()
            result, changed = mutation(entries)
            if changed:
                self._save_unlocked(entries)
            return result


__all__ = [
    "ALLOWED_MEMORY_SOURCES",
    "DEFAULT_MEMORY_PATH",
    "DEFAULT_RELATIONSHIP_PATH",
    "MemoryPersistenceError",
    "MemoryRepository",
    "MemoryStateError",
    "RelationshipPersistenceError",
    "RelationshipRepository",
    "RelationshipStateError",
]
