"""Small .env loader for local development.

The project deliberately avoids printing secret values. Existing environment
variables win unless override=True is passed.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Iterable, List


def _strip_quotes(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1]
    return value


def load_env_file(path: str | Path, override: bool = False) -> List[str]:
    env_path = Path(path)
    if not env_path.exists():
        return []

    loaded: List[str] = []
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.lower().startswith("export "):
            line = line[7:].strip()
        if "=" not in line:
            continue

        key, value = line.split("=", 1)
        key = key.strip()
        if not key:
            continue
        if not override and key in os.environ:
            continue

        os.environ[key] = _strip_quotes(value)
        loaded.append(key)
    return loaded


def mask_env_names(names: Iterable[str]) -> str:
    names = sorted(set(names))
    return ", ".join(names) if names else "none"
