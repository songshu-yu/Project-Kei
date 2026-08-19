"""Persistence owned by the focus module."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict


def project_server_root() -> Path:
    """Find the server root both in source and in an installed runtime package."""
    source = Path(__file__).resolve()
    for parent in source.parents:
        if parent.name == "server":
            return parent
    return source.parents[2]


# Keep the path used by the pre-module implementation. PK-180 deliberately does
# not move or inspect either historical focus_timer.json file.
DEFAULT_STORE = project_server_root() / "systems" / "data" / "focus_timer.json"


class FocusStateError(RuntimeError):
    """The existing focus state cannot be interpreted safely."""


class FocusRepository:
    def __init__(self, path: Path = DEFAULT_STORE):
        self.path = Path(path)

    @staticmethod
    def empty_state() -> Dict[str, Any]:
        return {"active_id": None, "sessions": []}

    def load(self) -> Dict[str, Any]:
        if not self.path.exists():
            return self.empty_state()
        try:
            with self.path.open("r", encoding="utf-8") as handle:
                state = json.load(handle)
        except (json.JSONDecodeError, OSError, UnicodeError) as exc:
            raise FocusStateError("focus_state_invalid") from exc
        if not isinstance(state, dict):
            raise FocusStateError("focus_state_invalid")
        active_id = state.get("active_id")
        sessions = state.get("sessions")
        if active_id is not None and not isinstance(active_id, str):
            raise FocusStateError("focus_state_invalid")
        if not isinstance(sessions, list) or any(not isinstance(item, dict) for item in sessions):
            raise FocusStateError("focus_state_invalid")
        state["active_id"] = active_id
        state["sessions"] = sessions
        return state

    def save(self, state: Dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(".tmp")
        with temporary.open("w", encoding="utf-8") as handle:
            json.dump(state, handle, ensure_ascii=False, indent=2)
        temporary.replace(self.path)
