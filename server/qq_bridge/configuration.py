"""Owned, atomic storage for the QQ sidecar's persistent credentials.

Only this PK-140 component interprets the two QQ credential fields and the
non-secret voice/life-forecast opt-ins and operator capability declaration. Callers receive a finite configuration summary
and never receive either credential value.
"""

from __future__ import annotations

import os
import re
import threading
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable


_ASSIGNMENT = re.compile(
    r"^[ \t]*(?:export[ \t]+)?([A-Za-z_][A-Za-z0-9_]*)[ \t]*=(.*)$"
)
_APP_ID = re.compile(r"^[A-Za-z0-9_-]{1,128}$")
_SECRET = re.compile(r"^[\x21\x23-\x26\x28-\x5B\x5D-\x7E]{1,256}$")
_MEDIA_CAPABILITIES = frozenset({"unknown", "available", "unavailable", "denied"})
_TARGETS = (
    "QQBOT_APPID",
    "QQBOT_SECRET",
    "QQBOT_REPLY_WITH_VOICE",
    "QQBOT_MEDIA_UPLOAD_CAPABILITY",
    "QQBOT_LIFE_FORECAST_ENABLED",
)
_MAX_ENV_BYTES = 64 * 1024


class QQConfigurationError(RuntimeError):
    """Finite failure safe to map to a fixed HTTP response."""

    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


@dataclass(frozen=True)
class QQConfigurationSummary:
    configured: bool
    appid_configured: bool
    secret_configured: bool
    appid_masked: str | None
    state: str
    reply_with_voice: bool
    voice_setting_valid: bool
    qq_media_upload_capability: str
    media_capability_valid: bool
    life_forecast_enabled: bool
    restart_required: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "configured": self.configured,
            "appid_configured": self.appid_configured,
            "secret_configured": self.secret_configured,
            "appid_masked": self.appid_masked,
            "state": self.state,
            "reply_with_voice": self.reply_with_voice,
            "voice_setting_valid": self.voice_setting_valid,
            "qq_media_upload_capability": self.qq_media_upload_capability,
            "media_capability_valid": self.media_capability_valid,
            "life_forecast_enabled": self.life_forecast_enabled,
            "restart_required": self.restart_required,
        }


class QQBridgeConfigurationStore:
    """Read and atomically update one trusted QQ `.env` path."""

    def __init__(self, env_path: str | Path, *, replace=os.replace) -> None:
        self._env_path = Path(os.path.abspath(os.fspath(env_path)))
        self._replace = replace
        self._lock = threading.RLock()

    @staticmethod
    def _decoded_value(raw: str) -> str:
        value = raw.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
            value = value[1:-1]
        return value.strip()

    def _read(self) -> tuple[str, dict[str, str]]:
        if not self._env_path.exists():
            return "", {}
        if not self._env_path.is_file() or self._env_path.is_symlink():
            raise QQConfigurationError("configuration_invalid")
        try:
            raw = self._env_path.read_bytes()
        except OSError as exc:
            raise QQConfigurationError("configuration_unavailable") from exc
        if len(raw) > _MAX_ENV_BYTES or b"\x00" in raw:
            raise QQConfigurationError("configuration_invalid")
        try:
            text = raw.decode("utf-8-sig")
        except UnicodeDecodeError as exc:
            raise QQConfigurationError("configuration_invalid") from exc
        values: dict[str, str] = {}
        for line in text.splitlines():
            match = _ASSIGNMENT.match(line)
            if match and match.group(1) in _TARGETS and match.group(1) not in values:
                values[match.group(1)] = self._decoded_value(match.group(2))
        return text, values

    @staticmethod
    def _mask_appid(value: str) -> str | None:
        if not value:
            return None
        if len(value) <= 4:
            return "*" * len(value)
        return f"{'*' * min(8, len(value) - 4)}{value[-4:]}"

    @classmethod
    def _summary(
        cls,
        values: dict[str, str],
        *,
        restart_required: bool = False,
    ) -> QQConfigurationSummary:
        appid = values.get("QQBOT_APPID", "")
        secret = values.get("QQBOT_SECRET", "")
        appid_ok = bool(_APP_ID.fullmatch(appid))
        secret_ok = bool(_SECRET.fullmatch(secret))
        raw_voice = values.get("QQBOT_REPLY_WITH_VOICE", "false").strip().lower()
        voice_setting_valid = raw_voice in {"true", "false"}
        raw_capability = values.get(
            "QQBOT_MEDIA_UPLOAD_CAPABILITY", "unknown"
        ).strip().lower()
        media_capability_valid = raw_capability in _MEDIA_CAPABILITIES
        capability = raw_capability if media_capability_valid else "unknown"
        raw_life_forecast = values.get(
            "QQBOT_LIFE_FORECAST_ENABLED", "false"
        ).strip().lower()
        return QQConfigurationSummary(
            configured=appid_ok and secret_ok,
            appid_configured=appid_ok,
            secret_configured=secret_ok,
            appid_masked=cls._mask_appid(appid) if appid_ok else None,
            state="configured" if appid_ok and secret_ok else "missing",
            reply_with_voice=(
                raw_voice == "true"
                if voice_setting_valid and capability == "available"
                else False
            ),
            voice_setting_valid=voice_setting_valid,
            qq_media_upload_capability=capability,
            media_capability_valid=media_capability_valid,
            life_forecast_enabled=raw_life_forecast == "true",
            restart_required=restart_required,
        )

    def status(self) -> dict[str, Any]:
        with self._lock:
            _, values = self._read()
            return self._summary(values).to_dict()

    @staticmethod
    def _validate_update(appid: str | None, secret: str | None) -> tuple[str | None, str | None]:
        normalized_appid = None if appid is None or not appid.strip() else appid.strip()
        normalized_secret = None if secret is None or not secret.strip() else secret.strip()
        if normalized_appid is not None and not _APP_ID.fullmatch(normalized_appid):
            raise QQConfigurationError("invalid_appid")
        if normalized_secret is not None and not _SECRET.fullmatch(normalized_secret):
            raise QQConfigurationError("invalid_secret")
        return normalized_appid, normalized_secret

    def update(
        self,
        *,
        appid: str | None,
        secret: str | None,
        reply_with_voice: bool | None = None,
        qq_media_upload_capability: str | None = None,
        life_forecast_enabled: bool | None = None,
    ) -> dict[str, Any]:
        if reply_with_voice is not None and not isinstance(reply_with_voice, bool):
            raise QQConfigurationError("invalid_voice_setting")
        if (
            qq_media_upload_capability is not None
            and qq_media_upload_capability not in _MEDIA_CAPABILITIES
        ):
            raise QQConfigurationError("invalid_media_capability")
        if life_forecast_enabled is not None and not isinstance(
            life_forecast_enabled, bool
        ):
            raise QQConfigurationError("invalid_life_forecast_setting")
        appid, secret = self._validate_update(appid, secret)
        with self._lock:
            text, existing = self._read()
            values = dict(existing)
            changed = False
            if appid is not None:
                changed = changed or appid != existing.get("QQBOT_APPID")
                values["QQBOT_APPID"] = appid
            if secret is not None:
                changed = changed or secret != existing.get("QQBOT_SECRET")
                values["QQBOT_SECRET"] = secret
            if reply_with_voice is not None:
                voice_value = "true" if reply_with_voice else "false"
                changed = changed or voice_value != existing.get(
                    "QQBOT_REPLY_WITH_VOICE", "false"
                ).strip().lower()
                values["QQBOT_REPLY_WITH_VOICE"] = voice_value
            if qq_media_upload_capability is not None:
                changed = changed or qq_media_upload_capability != existing.get(
                    "QQBOT_MEDIA_UPLOAD_CAPABILITY", "unknown"
                ).strip().lower()
                values["QQBOT_MEDIA_UPLOAD_CAPABILITY"] = qq_media_upload_capability
                if qq_media_upload_capability != "available":
                    changed = changed or values.get(
                        "QQBOT_REPLY_WITH_VOICE", "false"
                    ).strip().lower() != "false"
                    values["QQBOT_REPLY_WITH_VOICE"] = "false"
            if life_forecast_enabled is not None:
                life_forecast_value = (
                    "true" if life_forecast_enabled else "false"
                )
                changed = changed or life_forecast_value != existing.get(
                    "QQBOT_LIFE_FORECAST_ENABLED", "false"
                ).strip().lower()
                values["QQBOT_LIFE_FORECAST_ENABLED"] = life_forecast_value
            summary = self._summary(values)
            if not summary.configured:
                raise QQConfigurationError("configuration_incomplete")
            if not changed:
                return summary.to_dict()

            updates = {
                "QQBOT_APPID": values["QQBOT_APPID"],
                "QQBOT_SECRET": values["QQBOT_SECRET"],
                "QQBOT_REPLY_WITH_VOICE": values.get(
                    "QQBOT_REPLY_WITH_VOICE", "false"
                ),
                "QQBOT_MEDIA_UPLOAD_CAPABILITY": values.get(
                    "QQBOT_MEDIA_UPLOAD_CAPABILITY", "unknown"
                ),
                "QQBOT_LIFE_FORECAST_ENABLED": values.get(
                    "QQBOT_LIFE_FORECAST_ENABLED", "false"
                ),
            }
            seen: set[str] = set()
            lines: list[str] = []
            for line in text.splitlines():
                match = _ASSIGNMENT.match(line)
                key = match.group(1) if match else None
                if key in updates:
                    if key not in seen:
                        lines.append(f"{key}={updates[key]}")
                        seen.add(key)
                    continue
                lines.append(line)
            for key in _TARGETS:
                if key not in seen:
                    lines.append(f"{key}={updates[key]}")
            content = ("\n".join(lines).rstrip("\n") + "\n").encode("utf-8")

            self._env_path.parent.mkdir(parents=True, exist_ok=True)
            temporary = self._env_path.with_name(
                f".{self._env_path.name}.{uuid.uuid4().hex}.tmp"
            )
            try:
                with temporary.open("xb") as handle:
                    handle.write(content)
                    handle.flush()
                    os.fsync(handle.fileno())
                self._replace(temporary, self._env_path)
            except OSError as exc:
                try:
                    temporary.unlink(missing_ok=True)
                except OSError:
                    pass
                raise QQConfigurationError("configuration_save_failed") from exc
            return self._summary(values, restart_required=True).to_dict()


def create_qq_media_capability_provider(
    configuration_store: QQBridgeConfigurationStore,
) -> Callable[[], str]:
    """Return a side-effect-free snapshot provider for production composition."""

    def snapshot() -> str:
        try:
            return str(
                configuration_store.status().get(
                    "qq_media_upload_capability", "unknown"
                )
            )
        except Exception:
            return "unknown"

    return snapshot


__all__ = [
    "QQBridgeConfigurationStore",
    "QQConfigurationError",
    "QQConfigurationSummary",
    "create_qq_media_capability_provider",
]
