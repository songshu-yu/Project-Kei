"""Local cache for X/Nitter display names and avatars used by the dashboard."""
from __future__ import annotations

import asyncio
import json
import os
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Awaitable, Callable, Mapping, Sequence

from core.intel_contracts import normalize_url, sanitize_external_text
from intel.collectors.twitter import fetch_x_profile
from intel.intel_config import NITTER_INSTANCES


SERVER_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PATH = SERVER_ROOT / "data" / "x_profiles.json"
SCHEMA_VERSION = 1
FAILURE_COOLDOWN_HOURS = 6
_HANDLE_RE = re.compile(r"[A-Za-z0-9_]{1,30}")

ProfileFetcher = Callable[[str], Awaitable[dict]]


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _timestamp(value: datetime) -> str:
    return value.isoformat(timespec="seconds")


def _handle(value: object) -> str:
    result = str(value).strip().lstrip("@")
    if not _HANDLE_RE.fullmatch(result):
        raise ValueError("X username must contain only letters, numbers, or underscores")
    return result


def _key(username: str) -> str:
    return username.casefold()


def _avatar_url(value: object) -> str:
    return normalize_url(value)[:1000]


def _normalize_success(username: str, payload: object, updated_at: str) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise ValueError("X profile response must be an object")
    name = sanitize_external_text(payload.get("name"), limit=160)
    if not name:
        raise ValueError("X profile did not return a display name")
    groups = payload.get("x_config_groups", [])
    if not isinstance(groups, (list, tuple)):
        groups = []
    return {
        "username": username,
        "name": name,
        "avatar_url": _avatar_url(payload.get("avatar_url")),
        "x_config_groups": [str(item)[:80] for item in groups if str(item).strip()][:2],
        "status": "ok",
        "updated_at": updated_at,
    }


def _normalize_cached_entry(username: str, payload: object) -> dict[str, Any] | None:
    if not isinstance(payload, dict):
        return None
    updated_at = str(payload.get("updated_at") or "")
    if payload.get("status") == "ok":
        try:
            return _normalize_success(username, payload, updated_at)
        except ValueError:
            return None
    if payload.get("status") == "error":
        groups = payload.get("x_config_groups", [])
        if not isinstance(groups, (list, tuple)):
            groups = []
        return {
            "username": username,
            "name": "",
            "avatar_url": "",
            "x_config_groups": [str(item)[:80] for item in groups if str(item).strip()][:2],
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
        print(f"[X profiles] could not read local cache: {type(exc).__name__}")
        return {}
    profiles = payload.get("profiles", {}) if isinstance(payload, dict) else {}
    if not isinstance(profiles, dict):
        return {}
    result: dict[str, dict[str, Any]] = {}
    for key, value in profiles.items():
        try:
            username = _handle(value.get("username", key) if isinstance(value, dict) else key)
        except ValueError:
            continue
        normalized = _normalize_cached_entry(username, value)
        if normalized is not None:
            result[_key(username)] = normalized
    return result


def _write_cache(profiles: dict[str, dict[str, Any]], path: str | Path) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_suffix(path.suffix + ".tmp")
    temp_path.write_text(
        json.dumps(
            {"schema_version": SCHEMA_VERSION, "profiles": profiles},
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    temp_path.replace(path)


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


async def resolve_x_profiles(
    usernames: list[object],
    *,
    refresh: bool = False,
    path: str | Path = DEFAULT_PATH,
    fetcher: ProfileFetcher | None = None,
    nitter_instances: Sequence[object] = NITTER_INSTANCES,
    now: datetime | None = None,
    groups_by_username: Mapping[str, Sequence[str]] | None = None,
) -> dict[str, Any]:
    """Return cached X profiles and resolve only missing/explicitly refreshed users."""
    selected: list[str] = []
    seen: set[str] = set()
    for value in usernames:
        username = _handle(value)
        key = _key(username)
        if key not in seen:
            seen.add(key)
            selected.append(username)

    profiles = _read_cache(path)
    current_time = now or _now()

    def configured_groups(username: str) -> list[str] | None:
        if groups_by_username is None:
            return None
        values = groups_by_username.get(_key(username), ())
        return [str(item)[:80] for item in values if str(item).strip()][:2]

    async def default_fetcher(username: str) -> dict:
        return await fetch_x_profile(username, nitter_instances)

    fetch = fetcher or default_fetcher
    try:
        request_delay = max(0.0, float(os.getenv("X_PROFILE_REQUEST_DELAY_SECONDS", "0.5")))
    except ValueError:
        request_delay = 0.5
    if fetcher is not None:
        request_delay = 0.0

    changed = False
    fetched = 0
    attempted = 0
    for username in selected:
        key = _key(username)
        cached = profiles.get(key)
        groups = configured_groups(username)
        if groups is not None and cached is not None and cached.get("x_config_groups", []) != groups:
            cached["x_config_groups"] = groups
            changed = True
        if not refresh and cached and (cached.get("status") == "ok" or _retry_is_active(cached, current_time)):
            continue
        if attempted and request_delay:
            await asyncio.sleep(request_delay)
        attempted += 1
        updated_at = _timestamp(current_time)
        try:
            profile = await fetch(username)
            profile = dict(profile)
            profile["x_config_groups"] = groups if groups is not None else (cached or {}).get("x_config_groups", [])
            profiles[key] = _normalize_success(username, profile, updated_at)
            fetched += 1
        except Exception as exc:
            profiles[key] = {
                "username": username,
                "name": "",
                "avatar_url": "",
                "x_config_groups": groups if groups is not None else (cached or {}).get("x_config_groups", []),
                "status": "error",
                "message": "资料暂不可用，可稍后重试",
                "updated_at": updated_at,
                "retry_after": _timestamp(current_time + timedelta(hours=FAILURE_COOLDOWN_HOURS)),
            }
            print(f"[X profiles] lookup failed: {type(exc).__name__}")
        changed = True

    if changed:
        _write_cache(profiles, path)

    return {
        "profiles": {_key(username): profiles[_key(username)] for username in selected if _key(username) in profiles},
        "requested": len(selected),
        "fetched": fetched,
        "cache_path": "server/data/x_profiles.json",
    }


def get_x_profiles(
    usernames: list[object],
    *,
    path: str | Path = DEFAULT_PATH,
    groups_by_username: Mapping[str, Sequence[str]] | None = None,
) -> dict[str, Any]:
    """Read selected cached X profiles without network access or cache writes."""
    selected: list[str] = []
    seen: set[str] = set()
    for value in usernames:
        username = _handle(value)
        key = _key(username)
        if key not in seen:
            seen.add(key)
            selected.append(username)

    profiles = _read_cache(path)
    visible: dict[str, dict[str, Any]] = {}
    for username in selected:
        key = _key(username)
        cached = profiles.get(key)
        if cached is None:
            continue
        entry = dict(cached)
        if groups_by_username is not None:
            entry["x_config_groups"] = [
                str(item)[:80]
                for item in groups_by_username.get(key, ())
                if str(item).strip()
            ][:2]
        visible[key] = entry
    return {
        "profiles": visible,
        "requested": len(selected),
        "fetched": 0,
        "cache_path": "server/data/x_profiles.json",
    }
