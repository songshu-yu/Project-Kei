"""Atomic, local-only Voice Pack registry storage."""

from __future__ import annotations

import json
import os
import tempfile
import threading
from copy import deepcopy
from pathlib import Path
from typing import Any

from .errors import VoicePackRegistryError


REGISTRY_VERSION = 1


def empty_registry() -> dict[str, Any]:
    return {"registry_version": REGISTRY_VERSION, "active": None, "packs": {}}


class VoicePackRegistry:
    def __init__(self, path: Path):
        self.path = Path(path)
        self._lock = threading.RLock()

    def load(self) -> dict[str, Any]:
        with self._lock:
            if not self.path.exists():
                return empty_registry()
            try:
                payload = json.loads(self.path.read_text(encoding="utf-8"))
            except (OSError, UnicodeError, json.JSONDecodeError) as exc:
                raise VoicePackRegistryError("Voice Pack registry is unreadable") from exc
            if (
                not isinstance(payload, dict)
                or payload.get("registry_version") != REGISTRY_VERSION
                or not isinstance(payload.get("packs"), dict)
                or payload.get("active") is not None and not isinstance(payload.get("active"), str)
            ):
                raise VoicePackRegistryError("Voice Pack registry has an unsupported structure")
            return deepcopy(payload)

    def save(self, payload: dict[str, Any]) -> None:
        with self._lock:
            if payload.get("registry_version") != REGISTRY_VERSION or not isinstance(payload.get("packs"), dict):
                raise VoicePackRegistryError("refusing to write an invalid Voice Pack registry")
            self.path.parent.mkdir(parents=True, exist_ok=True)
            temp_path: Path | None = None
            try:
                with tempfile.NamedTemporaryFile(
                    mode="w", encoding="utf-8", dir=str(self.path.parent),
                    prefix=self.path.name + ".", suffix=".tmp", delete=False,
                ) as handle:
                    temp_path = Path(handle.name)
                    json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True)
                    handle.write("\n")
                    handle.flush()
                    os.fsync(handle.fileno())
                os.replace(str(temp_path), str(self.path))
            except OSError as exc:
                raise VoicePackRegistryError("Voice Pack registry update failed") from exc
            finally:
                if temp_path is not None and temp_path.exists():
                    try:
                        temp_path.unlink()
                    except OSError:
                        pass
