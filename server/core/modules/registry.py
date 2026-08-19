"""Atomic local registry storage for installable modules."""

from __future__ import annotations

import json
import os
import tempfile
import threading
from copy import deepcopy
from pathlib import Path
from typing import Any, Dict

from .exceptions import RegistryError


REGISTRY_VERSION = 1


def empty_registry() -> Dict[str, Any]:
    return {"registry_version": REGISTRY_VERSION, "modules": {}}


class ModuleRegistry:
    """Read and replace one JSON registry without exposing partial writes."""

    def __init__(self, path: Path):
        self.path = Path(path)
        self._lock = threading.RLock()

    def load(self) -> Dict[str, Any]:
        with self._lock:
            if not self.path.exists():
                return empty_registry()
            try:
                payload = json.loads(self.path.read_text(encoding="utf-8"))
            except (OSError, UnicodeError, json.JSONDecodeError) as exc:
                raise RegistryError("module registry is unreadable: %s" % type(exc).__name__) from exc
            if not isinstance(payload, dict):
                raise RegistryError("module registry root must be an object")
            if payload.get("registry_version") != REGISTRY_VERSION:
                raise RegistryError("unsupported module registry version")
            modules = payload.get("modules")
            if not isinstance(modules, dict) or any(not isinstance(key, str) for key in modules):
                raise RegistryError("module registry contains an invalid modules map")
            return deepcopy(payload)

    def save(self, payload: Dict[str, Any]) -> None:
        with self._lock:
            if payload.get("registry_version") != REGISTRY_VERSION or not isinstance(payload.get("modules"), dict):
                raise RegistryError("refusing to write an invalid module registry")
            self.path.parent.mkdir(parents=True, exist_ok=True)
            temp_path = None
            try:
                with tempfile.NamedTemporaryFile(
                    mode="w",
                    encoding="utf-8",
                    dir=str(self.path.parent),
                    prefix=self.path.name + ".",
                    suffix=".tmp",
                    delete=False,
                ) as handle:
                    temp_path = Path(handle.name)
                    json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True)
                    handle.write("\n")
                    handle.flush()
                    os.fsync(handle.fileno())
                os.replace(str(temp_path), str(self.path))
            except OSError as exc:
                raise RegistryError("could not update module registry: %s" % type(exc).__name__) from exc
            finally:
                if temp_path is not None and temp_path.exists():
                    try:
                        temp_path.unlink()
                    except OSError:
                        pass
