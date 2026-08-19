"""Local cache for Bilibili nickname/avatar metadata used by the dashboard."""
from __future__ import annotations

import asyncio
import json
import os
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Awaitable, Callable, Mapping

from features.bilibili.client import normalize_uid
from core.intel_contracts import normalize_url, sanitize_external_text
from intel.collectors.bilibili import fetch_bilibili_profile


SERVER_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PATH = SERVER_ROOT / "data" / "bilibili_profiles.json"
SCHEMA_VERSION = 1
FAILURE_COOLDOWN_HOURS = 6

ProfileFetcher = Callable[[int], Awaitable[dict]]


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _timestamp(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat(timespec="seconds")


def _uid(value: object) -> int:
    return normalize_uid(value)


def _avatar_url(value: object) -> str:
    result = str(value or "").strip()
    if result.startswith("//"):
        result = "https:" + result
    return normalize_url(result)[:1000]


def _normalize_success(uid: int, payload: object, updated_at: str) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise ValueError("Bilibili profile response must be an object")
    name = sanitize_external_text(payload.get("name"), limit=160)
    if not name:
        raise ValueError("Bilibili profile did not return a nickname")
    return {
        "uid": uid,
        "name": name,
        "avatar_url": _avatar_url(payload.get("avatar_url")),
        "status": "ok",
        "updated_at": updated_at,
    }


def _normalize_cached_entry(uid: int, payload: object) -> dict[str, Any] | None:
    if not isinstance(payload, dict):
        return None
    updated_at = str(payload.get("updated_at") or "")
    if payload.get("status") == "ok":
        try:
            return _normalize_success(uid, payload, updated_at)
        except ValueError:
            return None
    if payload.get("status") == "error":
        return {
            "uid": uid,
            "name": "",
            "avatar_url": "",
            "status": "error",
            "message": "资料暂不可用，可稍后重试",
            "updated_at": updated_at,
            "retry_after": str(payload.get("retry_after") or ""),
        }
    return None


def _read_cache(path: str | Path) -> dict[str, dict[str, Any]]:
    path = Path(path)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    except (OSError, json.JSONDecodeError) as exc:
        print(f"[Bilibili profiles] could not read local cache: {type(exc).__name__}")
        return {}
    profiles = payload.get("profiles", {}) if isinstance(payload, dict) else {}
    if not isinstance(profiles, dict):
        return {}
    result: dict[str, dict[str, Any]] = {}
    for key, value in profiles.items():
        try:
            uid = _uid(key)
        except ValueError:
            continue
        normalized = _normalize_cached_entry(uid, value)
        if normalized is not None:
            result[str(uid)] = normalized
    return result


def _write_cache(profiles: dict[str, dict[str, Any]], path: str | Path) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    serialized = json.dumps(
        {"schema_version": SCHEMA_VERSION, "profiles": profiles},
        ensure_ascii=False,
        indent=2,
    )
    temp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=str(path.parent),
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            temp_path = Path(handle.name)
            handle.write(serialized)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(str(temp_path), str(path))
    finally:
        if temp_path is not None:
            try:
                temp_path.unlink()
            except FileNotFoundError:
                pass


def _retry_is_active(entry: dict[str, Any], now: datetime) -> bool:
    if entry.get("status") != "error":
        return False
    try:
        retry_after = datetime.fromisoformat(str(entry.get("retry_after") or ""))
    except ValueError:
        return False
    if retry_after.tzinfo is None:
        retry_after = retry_after.replace(tzinfo=timezone.utc)
    return retry_after > now


async def resolve_bilibili_profiles(
    uids: list[object],
    *,
    refresh: bool = False,
    path: str | Path = DEFAULT_PATH,
    fetcher: ProfileFetcher | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Return cached profiles and resolve only missing/explicitly refreshed UIDs."""
    selected: list[int] = []
    seen: set[int] = set()
    for value in uids:
        uid = _uid(value)
        if uid not in seen:
            seen.add(uid)
            selected.append(uid)

    profiles = _read_cache(path)
    current_time = now or _now()
    if current_time.tzinfo is None or current_time.utcoffset() is None:
        current_time = current_time.replace(tzinfo=timezone.utc)
    else:
        current_time = current_time.astimezone(timezone.utc)
    fetch = fetcher or fetch_bilibili_profile
    try:
        request_delay = max(0.0, float(os.getenv("BILI_PROFILE_REQUEST_DELAY_SECONDS", "1.0")))
    except ValueError:
        request_delay = 1.0
    if fetcher is not None:
        request_delay = 0.0

    changed = False
    fetched = 0
    attempted = 0
    for uid in selected:
        key = str(uid)
        cached = profiles.get(key)
        if cached and _retry_is_active(cached, current_time):
            continue
        if not refresh and cached and cached.get("status") == "ok":
            continue
        if attempted and request_delay:
            await asyncio.sleep(request_delay)
        attempted += 1
        updated_at = _timestamp(current_time)
        try:
            profile = await fetch(uid)
            profiles[key] = _normalize_success(uid, profile, updated_at)
            fetched += 1
        except Exception as exc:
            profiles[key] = {
                "uid": uid,
                "name": "",
                "avatar_url": "",
                "status": "error",
                "message": "资料暂不可用，可稍后重试",
                "updated_at": updated_at,
                "retry_after": _timestamp(current_time + timedelta(hours=FAILURE_COOLDOWN_HOURS)),
            }
            print(f"[Bilibili profiles] lookup failed: {type(exc).__name__}")
        changed = True

    if changed:
        _write_cache(profiles, path)

    return {
        "profiles": {str(uid): profiles[str(uid)] for uid in selected if str(uid) in profiles},
        "requested": len(selected),
        "fetched": fetched,
        "cache_path": "server/data/bilibili_profiles.json",
    }


def get_bilibili_profiles(
    uids: list[object],
    *,
    path: str | Path = DEFAULT_PATH,
) -> dict[str, Any]:
    """Read selected cached profiles without any network or cache write."""
    selected: list[int] = []
    seen: set[int] = set()
    for value in uids:
        uid = _uid(value)
        if uid not in seen:
            seen.add(uid)
            selected.append(uid)
    profiles = _read_cache(path)
    return {
        "profiles": {str(uid): profiles[str(uid)] for uid in selected if str(uid) in profiles},
        "requested": len(selected),
        "fetched": 0,
        "cache_path": "server/data/bilibili_profiles.json",
    }


def store_bilibili_profiles(
    payloads: Mapping[object, object],
    *,
    path: str | Path = DEFAULT_PATH,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Atomically merge already-fetched public profiles without any network."""
    current_time = now or _now()
    updated_at = _timestamp(current_time)
    normalized: dict[str, dict[str, Any]] = {}
    for raw_uid, payload in payloads.items():
        uid = _uid(raw_uid)
        normalized[str(uid)] = _normalize_success(uid, payload, updated_at)
    if not normalized:
        return {
            "profiles": {},
            "requested": 0,
            "fetched": 0,
            "cache_path": "server/data/bilibili_profiles.json",
        }
    profiles = _read_cache(path)
    profiles.update(normalized)
    _write_cache(profiles, path)
    return {
        "profiles": normalized,
        "requested": len(normalized),
        "fetched": len(normalized),
        "cache_path": "server/data/bilibili_profiles.json",
    }


__all__ = [
    "DEFAULT_PATH",
    "FAILURE_COOLDOWN_HOURS",
    "get_bilibili_profiles",
    "resolve_bilibili_profiles",
    "store_bilibili_profiles",
]
