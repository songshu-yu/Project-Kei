"""Atomic per-day cache for the X content shown in the local dashboard."""
from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence
from urllib.parse import urlsplit, urlunsplit

from core.intel_contracts import get_timezone, normalize_url, sanitize_external_text


SCHEMA_VERSION = 2
BUSINESS_TIMEZONE = "Asia/Shanghai"
_BUSINESS_TZ = get_timezone(BUSINESS_TIMEZONE)
_HANDLE_RE = re.compile(r"[A-Za-z0-9_]{1,30}")
_CONTENT_ID_RE = re.compile(r"[A-Za-z0-9:_-]{1,100}")
Replace = Callable[[object, object], None]


class XDailyCachePersistenceError(RuntimeError):
    """Raised when an atomic X daily-cache replacement cannot be completed."""


def _local_now(now: datetime | None = None) -> datetime:
    if now is None:
        return datetime.now(_BUSINESS_TZ)
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("X daily cache clock must be timezone-aware")
    return now.astimezone(_BUSINESS_TZ)


def business_local_now(now: datetime | None = None) -> datetime:
    return _local_now(now)


def _handle(value: object) -> str:
    result = str(value or "").strip().lstrip("@")
    if not _HANDLE_RE.fullmatch(result):
        raise ValueError("X username must contain only letters, numbers, or underscores")
    return result


def normalize_x_handle(value: object) -> str:
    return _handle(value)


def _key(username: str) -> str:
    return username.casefold()


def _safe_url(value: object) -> str:
    url = normalize_url(value)[:2000]
    if not url:
        return ""
    parsed = urlsplit(url)
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, "", ""))


def _stable_content_id(username: str, item: Mapping[str, Any]) -> str:
    for field in ("id", "upstream_id"):
        existing_id = sanitize_external_text(item.get(field), limit=100)
        if _CONTENT_ID_RE.fullmatch(existing_id):
            return existing_id
    material = "\x1f".join(
        (
            username.casefold(),
            str(item.get("kind") or ""),
            str(item.get("url") or ""),
            str(item.get("published_at") or ""),
            str(item.get("content") or ""),
        )
    )
    return hashlib.sha256(material.encode("utf-8")).hexdigest()[:24]


class XDailyContentRepository:
    """Store the single daily X content list used by the dashboard."""

    def __init__(
        self,
        path: str | Path,
        *,
        channel: str,
        replace: Replace = os.replace,
    ) -> None:
        if channel != "posts":
            raise ValueError("X daily cache channel must be posts")
        self.path = Path(path)
        self.channel = channel
        self._replace = replace

    @property
    def allowed_kinds(self) -> set[str]:
        return {"post", "quote", "reply"}

    def _empty(self, day: str) -> dict[str, Any]:
        return {
            "schema_version": SCHEMA_VERSION,
            "channel": self.channel,
            "date": day,
            "updated_at": "",
            "users": {},
        }

    def _normalize_item(
        self,
        username: str,
        payload: object,
        *,
        legacy_posts: bool = False,
    ) -> dict[str, Any] | None:
        if not isinstance(payload, Mapping):
            return None
        kind = str(payload.get("kind") or "").strip().lower()
        if legacy_posts and not kind:
            kind = "post"
        if kind not in self.allowed_kinds:
            return None
        content = sanitize_external_text(payload.get("content"), limit=1_000)
        if not content:
            return None
        item: dict[str, Any] = {
            "id": _stable_content_id(username, payload),
            "kind": kind,
            "content": content,
            "url": _safe_url(payload.get("url")),
            "published": sanitize_external_text(payload.get("published"), limit=40),
            "published_at": sanitize_external_text(payload.get("published_at"), limit=80),
        }
        if kind == "reply":
            reply_to = str(payload.get("reply_to_username") or "").strip().lstrip("@")
            item["reply_to_username"] = (
                _handle(reply_to) if reply_to and _HANDLE_RE.fullmatch(reply_to) else ""
            )
            parent = payload.get("parent_context")
            if isinstance(parent, Mapping):
                parent_username = str(parent.get("username") or "").strip().lstrip("@")
                parent_content = sanitize_external_text(parent.get("content"), limit=1_000)
                parent_published_at = sanitize_external_text(
                    parent.get("published_at"),
                    limit=80,
                )
                if _HANDLE_RE.fullmatch(parent_username) and parent_content:
                    item["parent_context"] = {
                        "username": f"@{parent_username}",
                        "content": parent_content,
                        "published_at": parent_published_at,
                        "url": _safe_url(parent.get("url")),
                    }
        return item

    def _normalize_user(
        self,
        key: object,
        payload: object,
        day: str,
        *,
        legacy_posts: bool = False,
    ) -> dict[str, Any] | None:
        if not isinstance(payload, Mapping):
            return None
        try:
            username = _handle(payload.get("username", key))
        except ValueError:
            return None
        raw_items = payload.get(self.channel, [])
        if not isinstance(raw_items, list):
            raw_items = []
        items: list[dict[str, Any]] = []
        seen_ids: set[str] = set()
        seen_urls: set[str] = set()
        for raw_item in raw_items:
            item = self._normalize_item(
                username,
                raw_item,
                legacy_posts=legacy_posts,
            )
            if item is None:
                continue
            item_url = str(item.get("url") or "")
            if item["id"] in seen_ids or (item_url and item_url in seen_urls):
                continue
            seen_ids.add(item["id"])
            if item_url:
                seen_urls.add(item_url)
            items.append(item)
            if len(items) >= 30:
                break
        groups = payload.get("x_config_groups", [])
        if not isinstance(groups, (list, tuple)):
            groups = []
        return {
            "username": username,
            "date": day,
            "status": "ok",
            "x_config_groups": [
                str(group)[:80] for group in groups if str(group).strip()
            ][:2],
            self.channel: items,
            "count": len(items),
            "fetched_at": sanitize_external_text(payload.get("fetched_at"), limit=80),
        }

    def read_today(self, *, now: datetime | None = None) -> dict[str, Any]:
        """Read today's view; missing, stale, or damaged state causes no write."""
        day = _local_now(now).date().isoformat()
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (FileNotFoundError, OSError, json.JSONDecodeError):
            return self._empty(day)
        legacy_posts = (
            self.channel == "posts"
            and isinstance(payload, Mapping)
            and payload.get("schema_version") == 1
            and "channel" not in payload
        )
        if (
            not isinstance(payload, Mapping)
            or (
                payload.get("schema_version") != SCHEMA_VERSION
                and not legacy_posts
            )
            or payload.get("date") != day
            or not isinstance(payload.get("users"), Mapping)
            or payload.get("channel", self.channel) != self.channel
        ):
            return self._empty(day)
        users: dict[str, dict[str, Any]] = {}
        for key, value in payload["users"].items():
            normalized = self._normalize_user(
                key,
                value,
                day,
                legacy_posts=legacy_posts,
            )
            if normalized is not None:
                users[_key(normalized["username"])] = normalized
        return {
            "schema_version": SCHEMA_VERSION,
            "channel": self.channel,
            "date": day,
            "updated_at": sanitize_external_text(payload.get("updated_at"), limit=80),
            "users": users,
        }

    def read_selected(
        self,
        usernames: Sequence[object],
        *,
        now: datetime | None = None,
        groups_by_username: Mapping[str, Sequence[str]] | None = None,
    ) -> dict[str, Any]:
        payload = self.read_today(now=now)
        selected: list[str] = []
        seen: set[str] = set()
        for value in usernames:
            username = _handle(value)
            key = _key(username)
            if key not in seen:
                seen.add(key)
                selected.append(key)
        users: dict[str, dict[str, Any]] = {}
        for key in selected:
            if key not in payload["users"]:
                continue
            entry = dict(payload["users"][key])
            entry[self.channel] = [dict(item) for item in entry[self.channel]]
            if groups_by_username is not None:
                entry["x_config_groups"] = [
                    str(group)[:80]
                    for group in groups_by_username.get(key, ())
                    if str(group).strip()
                ][:2]
            users[key] = entry
        return {
            "date": payload["date"],
            "updated_at": payload["updated_at"],
            "users": users,
        }

    def replace_user(
        self,
        username: object,
        items: object,
        *,
        now: datetime | None = None,
        x_config_groups: Sequence[str] = (),
    ) -> dict[str, Any]:
        handle = _handle(username)
        local_now = _local_now(now)
        payload = self.read_today(now=local_now)
        if not isinstance(items, list):
            raise ValueError(f"X daily {self.channel} response must be a list")
        entry = self._normalize_user(
            handle,
            {
                "username": handle,
                self.channel: items,
                "x_config_groups": x_config_groups,
                "fetched_at": local_now.isoformat(timespec="seconds"),
            },
            payload["date"],
        )
        if entry is None:
            raise ValueError(f"X daily {self.channel} entry is invalid")
        payload["users"][_key(handle)] = entry
        payload["updated_at"] = local_now.isoformat(timespec="seconds")
        self._write_atomic(payload)
        return entry

    def normalize_items(
        self,
        username: object,
        items: object,
        *,
        day: str,
    ) -> list[dict[str, Any]]:
        """Normalize a response-only query without reading or writing the cache."""
        handle = _handle(username)
        if not isinstance(items, list):
            raise ValueError(f"X daily {self.channel} response must be a list")
        entry = self._normalize_user(
            handle,
            {"username": handle, self.channel: items},
            day,
        )
        if entry is None:
            raise ValueError(f"X daily {self.channel} entry is invalid")
        return entry[self.channel]

    def _write_atomic(self, payload: Mapping[str, Any]) -> None:
        temporary_path: Path | None = None
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=self.path.parent,
                prefix=f".{self.path.name}.",
                suffix=".tmp",
                delete=False,
            ) as temporary:
                json.dump(payload, temporary, ensure_ascii=False, indent=2)
                temporary.flush()
                os.fsync(temporary.fileno())
                temporary_path = Path(temporary.name)
            self._replace(str(temporary_path), str(self.path))
        except OSError as exc:
            raise XDailyCachePersistenceError(
                f"X daily {self.channel} cache could not be saved"
            ) from exc
        finally:
            if temporary_path is not None:
                try:
                    temporary_path.unlink(missing_ok=True)
                except OSError:
                    pass


__all__ = [
    "SCHEMA_VERSION",
    "BUSINESS_TIMEZONE",
    "XDailyCachePersistenceError",
    "XDailyContentRepository",
    "business_local_now",
    "normalize_x_handle",
]
