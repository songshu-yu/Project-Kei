"""Local-only credential storage for the PK-130 Bilibili collector."""
from __future__ import annotations

import json
import os
import tempfile
import threading
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable, Mapping, Optional


SERVER_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_PATH = SERVER_ROOT / "data" / "bilibili_credentials.local.json"
SCHEMA_VERSION = 1
MAX_SECRET_LENGTH = 4096
FAILURE_COOLDOWN = timedelta(hours=6)


@dataclass(frozen=True)
class CredentialField:
    key: str
    cookie_name: str
    environment_name: str
    purpose: str
    required: bool = True


CREDENTIAL_FIELDS = (
    CredentialField(
        key="sessdata",
        cookie_name="SESSDATA",
        environment_name="BILI_SESSDATA",
        purpose="本人 B 站登录会话标识，用于资料与空间动态请求。",
    ),
    CredentialField(
        key="bili_jct",
        cookie_name="bili_jct",
        environment_name="BILI_JCT",
        purpose="本人会话的 CSRF Cookie；与同一浏览器会话的 SESSDATA 配套。",
    ),
    CredentialField(
        key="buvid3",
        cookie_name="buvid3",
        environment_name="BILI_BUVID3",
        purpose="本人浏览器的设备 Cookie，用于降低资料与动态请求被上游拒绝的概率。",
    ),
)


class BilibiliCredentialPersistenceError(RuntimeError):
    """A bounded local persistence failure with no credential material."""


@dataclass(frozen=True, repr=False)
class BilibiliCredentials:
    sessdata: str
    bili_jct: str
    buvid3: str

    def as_cookies(self) -> dict[str, str]:
        return {
            "SESSDATA": self.sessdata,
            "bili_jct": self.bili_jct,
            "buvid3": self.buvid3,
        }


EnvironmentProvider = Callable[[], Mapping[str, str]]
Clock = Callable[[], datetime]


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _timestamp(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat(timespec="seconds")


def _environment_values() -> dict[str, str]:
    return {
        field.key: str(os.getenv(field.environment_name, "") or "").strip()
        for field in CREDENTIAL_FIELDS
    }


def _normalize_values(values: Mapping[str, object]) -> dict[str, str]:
    normalized: dict[str, str] = {}
    for field in CREDENTIAL_FIELDS:
        value = str(values.get(field.key) or "").strip()
        if field.required and not value:
            raise ValueError(f"{field.cookie_name} is required")
        if len(value) > MAX_SECRET_LENGTH:
            raise ValueError(f"{field.cookie_name} is too long")
        if any(ord(character) < 32 or ord(character) == 127 for character in value):
            raise ValueError(f"{field.cookie_name} contains invalid control characters")
        normalized[field.key] = value
    return normalized


def _credential_set(values: Mapping[str, object]) -> Optional[BilibiliCredentials]:
    try:
        normalized = _normalize_values(values)
    except ValueError:
        return None
    return BilibiliCredentials(**normalized)


def _safe_error_code(value: object) -> str:
    text = str(value or "validation_failed").strip().casefold()
    allowed = "".join(character for character in text if character.isalnum() or character in "_-")
    return (allowed or "validation_failed")[:80]


class BilibiliCredentialRepository:
    """Own an atomic active/candidate local secret file.

    Candidate values are never activated until the caller has completed an
    explicit upstream validation. Public methods returning status contain only
    booleans, timestamps, fixed metadata and masked tails.
    """

    def __init__(
        self,
        path: str | Path = DEFAULT_PATH,
        *,
        environment_provider: EnvironmentProvider = _environment_values,
        clock: Clock = _utc_now,
        replace: Callable[[str, str], None] = os.replace,
    ) -> None:
        self.path = Path(path)
        self._environment_provider = environment_provider
        self._clock = clock
        self._replace = replace
        self._lock = threading.RLock()

    @staticmethod
    def _empty_document() -> dict:
        return {
            "schema_version": SCHEMA_VERSION,
            "active": None,
            "candidate": None,
            "environment_status": None,
        }

    def _read(self) -> dict:
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return self._empty_document()
        except (OSError, json.JSONDecodeError):
            return {
                **self._empty_document(),
                "store_error": "invalid_local_store",
            }
        if not isinstance(payload, dict) or payload.get("schema_version") != SCHEMA_VERSION:
            return {
                **self._empty_document(),
                "store_error": "invalid_local_store",
            }
        result = self._empty_document()
        for key in ("active", "candidate", "environment_status"):
            value = payload.get(key)
            result[key] = value if isinstance(value, dict) else None
        return result

    def _write(self, document: Mapping[str, object]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        serialized = json.dumps(document, ensure_ascii=False, indent=2)
        temp_path: Optional[Path] = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=str(self.path.parent),
                prefix=f".{self.path.name}.",
                suffix=".tmp",
                delete=False,
            ) as handle:
                temp_path = Path(handle.name)
                handle.write(serialized)
                handle.flush()
                os.fsync(handle.fileno())
            try:
                os.chmod(str(temp_path), 0o600)
            except OSError:
                pass
            self._replace(str(temp_path), str(self.path))
        except OSError as exc:
            raise BilibiliCredentialPersistenceError("credential_store_write_failed") from exc
        finally:
            if temp_path is not None:
                try:
                    temp_path.unlink()
                except FileNotFoundError:
                    pass

    def _environment_value_map(self) -> dict[str, str]:
        try:
            values = self._environment_provider()
        except Exception:
            return {}
        return {
            field.key: str(values.get(field.key) or "").strip()
            for field in CREDENTIAL_FIELDS
        }

    def _environment_credentials(self) -> Optional[BilibiliCredentials]:
        return _credential_set(self._environment_value_map())

    def active_credentials(self) -> Optional[BilibiliCredentials]:
        with self._lock:
            document = self._read()
            active = document.get("active")
            if isinstance(active, dict):
                values = active.get("values")
                if isinstance(values, dict):
                    credentials = _credential_set(values)
                    if credentials is not None:
                        return credentials
            return self._environment_credentials()

    def pending_or_active(self) -> tuple[Optional[BilibiliCredentials], bool]:
        with self._lock:
            document = self._read()
            if document.get("store_error"):
                raise BilibiliCredentialPersistenceError("credential_store_invalid")
            candidate = document.get("candidate")
            if isinstance(candidate, dict):
                values = candidate.get("values")
                if isinstance(values, dict):
                    credentials = _credential_set(values)
                    if credentials is not None:
                        return credentials, True
            return self.active_credentials(), False

    def save_candidate(self, values: Mapping[str, object]) -> dict:
        normalized = _normalize_values(values)
        with self._lock:
            document = self._read()
            if document.get("store_error"):
                raise BilibiliCredentialPersistenceError("credential_store_invalid")
            updated_at = _timestamp(self._clock())
            document["candidate"] = {
                "values": normalized,
                "state": "configured",
                "updated_at": updated_at,
                "validated_at": None,
                "last_error_code": None,
                "retry_after": None,
            }
            self._write(document)
            return self.status()

    def promote_candidate(self) -> dict:
        with self._lock:
            document = self._read()
            candidate = document.get("candidate")
            if not isinstance(candidate, dict) or _credential_set(candidate.get("values") or {}) is None:
                raise BilibiliCredentialPersistenceError("credential_candidate_missing")
            validated_at = _timestamp(self._clock())
            document["active"] = {
                "values": dict(candidate["values"]),
                "state": "configured",
                "updated_at": str(candidate.get("updated_at") or validated_at),
                "validated_at": validated_at,
                "last_error_code": None,
                "retry_after": None,
            }
            document["candidate"] = None
            document["environment_status"] = None
            self._write(document)
            return self.status()

    def mark_validation_failed(self, *, candidate: bool, error_code: str) -> dict:
        safe_code = _safe_error_code(error_code)
        with self._lock:
            document = self._read()
            if document.get("store_error"):
                raise BilibiliCredentialPersistenceError("credential_store_invalid")
            now = _timestamp(self._clock())
            retry_after = _timestamp(self._clock() + FAILURE_COOLDOWN)
            if candidate and isinstance(document.get("candidate"), dict):
                document["candidate"]["state"] = "invalid"
                document["candidate"]["validated_at"] = now
                document["candidate"]["last_error_code"] = safe_code
                document["candidate"]["retry_after"] = retry_after
            elif isinstance(document.get("active"), dict):
                document["active"]["state"] = "invalid"
                document["active"]["validated_at"] = now
                document["active"]["last_error_code"] = safe_code
                document["active"]["retry_after"] = retry_after
            elif self._environment_credentials() is not None:
                document["environment_status"] = {
                    "state": "invalid",
                    "validated_at": now,
                    "last_error_code": safe_code,
                    "retry_after": retry_after,
                }
            self._write(document)
            return self.status()

    def mark_active_validated(self) -> dict:
        with self._lock:
            document = self._read()
            if document.get("store_error"):
                raise BilibiliCredentialPersistenceError("credential_store_invalid")
            now = _timestamp(self._clock())
            if isinstance(document.get("active"), dict):
                document["active"]["state"] = "configured"
                document["active"]["validated_at"] = now
                document["active"]["last_error_code"] = None
                document["active"]["retry_after"] = None
            elif self._environment_credentials() is not None:
                document["environment_status"] = {
                    "state": "configured",
                    "validated_at": now,
                    "last_error_code": None,
                    "retry_after": None,
                }
            else:
                raise BilibiliCredentialPersistenceError("active_credentials_missing")
            self._write(document)
            return self.status()

    @staticmethod
    def _masked_tail(value: str) -> str:
        return f"••••{value[-4:]}" if value else ""

    def status(self) -> dict:
        with self._lock:
            document = self._read()
            store_error = str(document.get("store_error") or "")
            candidate = document.get("candidate") if isinstance(document.get("candidate"), dict) else None
            active = document.get("active") if isinstance(document.get("active"), dict) else None
            environment_values = self._environment_value_map()
            environment = _credential_set(environment_values)
            environment_status = (
                document.get("environment_status")
                if isinstance(document.get("environment_status"), dict)
                else None
            )

            if candidate is not None:
                selected = candidate
                values = candidate.get("values") if isinstance(candidate.get("values"), dict) else {}
                state = str(candidate.get("state") or "configured")
                source = "local_candidate"
            elif active is not None and _credential_set(active.get("values") or {}) is not None:
                selected = active
                values = active.get("values") if isinstance(active.get("values"), dict) else {}
                state = str(active.get("state") or "configured")
                source = "local_active"
            elif any(environment_values.values()):
                selected = environment_status or {}
                values = environment_values
                default_state = "configured" if environment is not None else "missing"
                state = str((environment_status or {}).get("state") or default_state)
                source = "environment"
            else:
                selected = {}
                values = {}
                state = "invalid" if store_error else "missing"
                source = "none"

            if state not in {"missing", "configured", "invalid"}:
                state = "invalid"
            active_available = (
                (active is not None and _credential_set(active.get("values") or {}) is not None)
                or environment is not None
            )
            active_state = "missing"
            if active is not None and _credential_set(active.get("values") or {}) is not None:
                active_state = str(active.get("state") or "configured")
            elif environment is not None:
                active_state = str((environment_status or {}).get("state") or "configured")
            if active_state not in {"missing", "configured", "invalid"}:
                active_state = "invalid"

            updated_at = str(selected.get("updated_at") or "")
            fields = []
            for field in CREDENTIAL_FIELDS:
                value = str(values.get(field.key) or "")
                fields.append({
                    "key": field.key,
                    "cookie_name": field.cookie_name,
                    "purpose": field.purpose,
                    "required": field.required,
                    "configured": bool(value),
                    "masked_tail": self._masked_tail(value),
                    "updated_at": updated_at or None,
                })
            return {
                "schema_version": SCHEMA_VERSION,
                "state": state,
                "source": source,
                "active_available": bool(active_available),
                "active_state": active_state,
                "candidate_state": (
                    str(candidate.get("state") or "configured")
                    if candidate is not None
                    else "missing"
                ),
                "updated_at": updated_at or None,
                "validated_at": str(selected.get("validated_at") or "") or None,
                "last_error_code": str(selected.get("last_error_code") or "") or None,
                "retry_after": str(selected.get("retry_after") or "") or None,
                "fields": fields,
            }


def load_active_bilibili_cookies(
    path: str | Path = DEFAULT_PATH,
) -> dict[str, str]:
    credentials = BilibiliCredentialRepository(path).active_credentials()
    return credentials.as_cookies() if credentials is not None else {}


__all__ = [
    "CREDENTIAL_FIELDS",
    "DEFAULT_PATH",
    "BilibiliCredentialPersistenceError",
    "BilibiliCredentialRepository",
    "BilibiliCredentials",
    "load_active_bilibili_cookies",
]
