"""Local persistence for user-customized dashboard UI images."""

from __future__ import annotations

import os
import re
import threading
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path


MAX_AVATAR_BYTES = 8 * 1024 * 1024
PANEL_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{1,128}$")
CONTENT_TYPE_EXTENSIONS = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
}
EXTENSION_CONTENT_TYPES = {extension: content_type for content_type, extension in CONTENT_TYPE_EXTENSIONS.items()}


class DashboardUiAssetError(ValueError):
    """Raised when a dashboard UI asset is invalid or cannot be persisted."""


@dataclass(frozen=True)
class DashboardUiAvatar:
    panel_id: str
    path: Path
    content_type: str
    size: int
    updated_at: str


def _valid_panel_id(panel_id: str) -> str:
    value = str(panel_id or "")
    if not PANEL_ID_PATTERN.fullmatch(value):
        raise DashboardUiAssetError("invalid panel id")
    return value


def _valid_image_bytes(content_type: str, payload: bytes) -> bool:
    if content_type == "image/png":
        return payload.startswith(b"\x89PNG\r\n\x1a\n")
    if content_type == "image/jpeg":
        return payload.startswith(b"\xff\xd8\xff")
    if content_type == "image/webp":
        return len(payload) >= 12 and payload.startswith(b"RIFF") and payload[8:12] == b"WEBP"
    return False


class DashboardUiAssetStore:
    """Own only dashboard appearance assets beneath an injected local root."""

    def __init__(self, root: Path):
        self._root = Path(root)
        self._lock = threading.RLock()

    def _candidates(self, panel_id: str) -> list[Path]:
        safe_id = _valid_panel_id(panel_id)
        if not self._root.is_dir():
            return []
        candidates = [
            self._root / f"{safe_id}{extension}"
            for extension in EXTENSION_CONTENT_TYPES
            if (self._root / f"{safe_id}{extension}").is_file()
        ]
        return sorted(candidates, key=lambda path: path.stat().st_mtime_ns, reverse=True)

    @staticmethod
    def _record(panel_id: str, path: Path) -> DashboardUiAvatar:
        stat = path.stat()
        return DashboardUiAvatar(
            panel_id=panel_id,
            path=path,
            content_type=EXTENSION_CONTENT_TYPES[path.suffix.lower()],
            size=stat.st_size,
            updated_at=datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat(),
        )

    def get(self, panel_id: str) -> DashboardUiAvatar | None:
        with self._lock:
            candidates = self._candidates(panel_id)
            return self._record(_valid_panel_id(panel_id), candidates[0]) if candidates else None

    def list(self) -> list[DashboardUiAvatar]:
        with self._lock:
            if not self._root.is_dir():
                return []
            panel_ids = {
                path.stem
                for path in self._root.iterdir()
                if path.is_file()
                and path.suffix.lower() in EXTENSION_CONTENT_TYPES
                and PANEL_ID_PATTERN.fullmatch(path.stem)
            }
            return [
                record
                for panel_id in sorted(panel_ids)
                if (record := self.get(panel_id)) is not None
            ]

    def save(self, panel_id: str, content_type: str, payload: bytes) -> DashboardUiAvatar:
        safe_id = _valid_panel_id(panel_id)
        normalized_type = str(content_type or "").split(";", 1)[0].strip().lower()
        extension = CONTENT_TYPE_EXTENSIONS.get(normalized_type)
        if extension is None:
            raise DashboardUiAssetError("unsupported image type")
        if not payload or len(payload) > MAX_AVATAR_BYTES:
            raise DashboardUiAssetError("invalid image size")
        if not _valid_image_bytes(normalized_type, payload):
            raise DashboardUiAssetError("image content does not match content type")

        with self._lock:
            self._root.mkdir(parents=True, exist_ok=True)
            target = self._root / f"{safe_id}{extension}"
            temporary = self._root / f".{safe_id}.{uuid.uuid4().hex}.tmp"
            try:
                with temporary.open("xb") as handle:
                    handle.write(payload)
                    handle.flush()
                    os.fsync(handle.fileno())
                os.replace(temporary, target)
                for old_extension in EXTENSION_CONTENT_TYPES:
                    old_path = self._root / f"{safe_id}{old_extension}"
                    if old_path != target:
                        old_path.unlink(missing_ok=True)
            except OSError as exc:
                temporary.unlink(missing_ok=True)
                raise DashboardUiAssetError("dashboard avatar could not be saved") from exc
            return self._record(safe_id, target)

    def delete(self, panel_id: str) -> bool:
        with self._lock:
            candidates = self._candidates(panel_id)
            try:
                for path in candidates:
                    path.unlink(missing_ok=True)
            except OSError as exc:
                raise DashboardUiAssetError("dashboard avatar could not be deleted") from exc
            return bool(candidates)


__all__ = [
    "DashboardUiAssetError",
    "DashboardUiAssetStore",
    "DashboardUiAvatar",
    "MAX_AVATAR_BYTES",
]
