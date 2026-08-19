"""Fixed local control protocol for the Project Kei Core supervisor.

The browser never supplies a command, path, process id, host, or port.  A
launcher-created random session name selects one directory below the fixed
runtime root; all actions and public states are closed enums.
"""

from __future__ import annotations

import json
import os
import re
import stat
import threading
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping


SUPERVISOR_ENV = "PROJECT_KEI_SUPERVISOR_SESSION"
RESTART_CONFIRMATION = "restart-project-kei-core"
PROTOCOL_VERSION = 1
SESSION_PATTERN = re.compile(r"^[0-9a-f]{32}$")
REQUEST_ID_PATTERN = re.compile(r"^[0-9a-f]{32}$")
PUBLIC_STATES = {"unavailable", "starting", "running", "accepted", "restarting", "failed"}
STATUS_MESSAGES = {
    "Core is starting under the local supervisor.",
    "Core is running under the local supervisor.",
    "Core restart was accepted by the local supervisor.",
    "Core restart preflight failed; the running Core was left unchanged.",
    "Core is restarting.",
    "Core could not be stopped safely; no replacement was started.",
    "Core port did not become available; no unrelated process was stopped.",
    "The replacement Core process could not be started.",
    "Core restart completed.",
    "The replacement Core process did not become ready.",
    "Core did not become ready.",
    "Core exited; the supervisor did not restart it without a request.",
}


def _is_link_or_reparse(path: Path) -> bool:
    info = path.lstat()
    if stat.S_ISLNK(info.st_mode):
        return True
    return bool(getattr(info, "st_file_attributes", 0) & 0x400)


def _atomic_json(path: Path, payload: Mapping[str, Any]) -> None:
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    encoded = json.dumps(payload, ensure_ascii=True, separators=(",", ":")) + "\n"
    with temporary.open("x", encoding="utf-8", newline="\n") as handle:
        handle.write(encoded)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)


def _read_object(path: Path, *, allowed_keys: set[str]) -> dict[str, Any]:
    info = path.lstat()
    if stat.S_ISLNK(info.st_mode) or bool(getattr(info, "st_file_attributes", 0) & 0x400):
        raise ValueError("control_file_is_link")
    if info.st_size > 16_384:
        raise ValueError("control_file_too_large")
    with path.open("r", encoding="utf-8") as handle:
        value = json.load(handle)
    if not isinstance(value, dict) or not set(value).issubset(allowed_keys):
        raise ValueError("invalid_control_object")
    return value


@dataclass(frozen=True)
class RestartResult:
    status_code: int
    payload: dict[str, Any]


class RestartControlClient:
    """API-side client for a launcher-owned supervisor session."""

    def __init__(self, runtime_root: Path, session_id: str | None) -> None:
        self._runtime_root = Path(runtime_root)
        self._session_id = session_id or ""
        self._lock = threading.Lock()

    @classmethod
    def from_environment(cls, server_root: Path) -> "RestartControlClient":
        return cls(
            Path(server_root) / "runtime" / "supervisor",
            os.getenv(SUPERVISOR_ENV),
        )

    def _session_directory(self) -> Path | None:
        if not SESSION_PATTERN.fullmatch(self._session_id):
            return None
        root = self._runtime_root
        session = root / self._session_id
        try:
            if not root.is_dir() or _is_link_or_reparse(root):
                return None
            if not session.is_dir() or _is_link_or_reparse(session):
                return None
        except OSError:
            return None
        return session

    def _marker_valid(self, session: Path) -> bool:
        marker_path = session / "session.json"
        try:
            marker = _read_object(
                marker_path,
                allowed_keys={"schema_version", "session_id", "scope"},
            )
        except (OSError, ValueError, json.JSONDecodeError):
            return False
        return marker == {
            "schema_version": PROTOCOL_VERSION,
            "session_id": self._session_id,
            "scope": "core",
        }

    @staticmethod
    def unavailable() -> dict[str, Any]:
        return {
            "available": False,
            "state": "unavailable",
            "scope": "core",
            "request_id": None,
            "generation": None,
            "retry_after_ms": 1000,
            "message": "Project Kei was not started by the restart supervisor.",
        }

    def status(self) -> dict[str, Any]:
        session = self._session_directory()
        if session is None or not self._marker_valid(session):
            return self.unavailable()
        try:
            value = _read_object(
                session / "status.json",
                allowed_keys={"schema_version", "state", "scope", "request_id", "generation", "message"},
            )
        except (OSError, ValueError, json.JSONDecodeError):
            return self.unavailable()
        state = value.get("state")
        request_id = value.get("request_id")
        generation = value.get("generation")
        if (
            value.get("schema_version") != PROTOCOL_VERSION
            or value.get("scope") != "core"
            or state not in PUBLIC_STATES - {"unavailable"}
            or (request_id is not None and not isinstance(request_id, str))
            or (request_id is not None and not REQUEST_ID_PATTERN.fullmatch(request_id))
            or not isinstance(generation, int)
            or generation < 0
            or not isinstance(value.get("message"), str)
            or value.get("message") not in STATUS_MESSAGES
        ):
            return self.unavailable()
        return {
            "available": True,
            "state": state,
            "scope": "core",
            "request_id": request_id,
            "generation": generation,
            "retry_after_ms": 500 if state in {"accepted", "restarting", "starting"} else 1000,
            "message": value["message"],
        }

    def request_restart(self, confirmation: str) -> RestartResult:
        if confirmation != RESTART_CONFIRMATION:
            return RestartResult(400, {
                "available": self.status()["available"],
                "state": "confirmation_required",
                "scope": "core",
                "request_id": None,
                "generation": None,
                "retry_after_ms": 1000,
                "message": "Explicit restart confirmation is required.",
            })
        with self._lock:
            current = self.status()
            if not current["available"]:
                return RestartResult(503, current)
            if current["state"] in {"accepted", "restarting"}:
                return RestartResult(202, current)

            session = self._session_directory()
            if session is None or not self._marker_valid(session):
                return RestartResult(503, self.unavailable())
            request_id = uuid.uuid4().hex
            request = {
                "schema_version": PROTOCOL_VERSION,
                "action": "restart_core",
                "session_id": self._session_id,
                "request_id": request_id,
            }
            accepted = {
                "schema_version": PROTOCOL_VERSION,
                "state": "accepted",
                "scope": "core",
                "request_id": request_id,
                "generation": current["generation"],
                "message": "Core restart was accepted by the local supervisor.",
            }
            try:
                _atomic_json(session / "status.json", accepted)
                _atomic_json(session / "request.json", request)
            except OSError:
                try:
                    (session / "request.json").unlink(missing_ok=True)
                    _atomic_json(session / "status.json", {
                        "schema_version": PROTOCOL_VERSION,
                        "state": current["state"],
                        "scope": "core",
                        "request_id": current["request_id"],
                        "generation": current["generation"],
                        "message": current["message"],
                    })
                except OSError:
                    pass
                return RestartResult(503, self.unavailable())
            return RestartResult(202, self.status())


__all__ = [
    "PROTOCOL_VERSION",
    "PUBLIC_STATES",
    "RESTART_CONFIRMATION",
    "RestartControlClient",
    "RestartResult",
    "SUPERVISOR_ENV",
    "STATUS_MESSAGES",
    "_atomic_json",
    "_read_object",
]
