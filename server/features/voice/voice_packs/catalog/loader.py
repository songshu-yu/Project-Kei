"""Strict loader for immutable Voice Pack release metadata."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping
from urllib.parse import urlparse


_SEMVER = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+(?:-[0-9A-Za-z.-]+)?$")
_PACK_ID = re.compile(r"^[a-z][a-z0-9-]{1,63}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_REVISION = re.compile(r"^[0-9a-f]{40}$")
_FIELDS = {
    "catalog_schema_version",
    "pack_id",
    "version",
    "display_name",
    "engine_id",
    "language",
    "core_compatibility",
    "voice_pack_schema_version",
    "engine_protocol",
    "engine_compatibility",
    "download_url",
    "allowed_redirect_hosts",
    "size_bytes",
    "sha256",
    "archive_root",
    "max_files",
    "max_file_bytes",
    "max_uncompressed_bytes",
    "max_compression_ratio",
    "license_url",
    "notice_url",
    "release_tag",
    "revision",
    "published_at",
    "recommend_select",
}


class CatalogError(ValueError):
    code = "voice_pack_catalog_invalid"


@dataclass(frozen=True)
class CatalogEntry:
    pack_id: str
    version: str
    display_name: str
    engine_id: str
    language: str
    core_compatibility: str
    voice_pack_schema_version: int
    engine_protocol: str
    engine_compatibility: str
    download_url: str
    allowed_redirect_hosts: tuple[str, ...]
    size_bytes: int
    sha256: str
    archive_root: str
    max_files: int
    max_file_bytes: int
    max_uncompressed_bytes: int
    max_compression_ratio: float
    license_url: str
    notice_url: str
    release_tag: str
    revision: str
    published_at: str
    recommend_select: bool

    @property
    def key(self) -> str:
        return f"{self.pack_id}@{self.version}"

    def public_dict(self) -> dict[str, Any]:
        return {
            "id": self.pack_id,
            "version": self.version,
            "name": self.display_name,
            "engine_id": self.engine_id,
            "language": self.language,
            "size_bytes": self.size_bytes,
            "license_url": self.license_url,
            "published_at": self.published_at,
            "recommend_select": self.recommend_select,
        }


def _https_url(value: Any, field: str, *, hosts: set[str] | None = None) -> str:
    if not isinstance(value, str):
        raise CatalogError(f"{field} must be an HTTPS URL")
    parsed = urlparse(value)
    hostname = (parsed.hostname or "").lower()
    if (
        parsed.scheme != "https"
        or not hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.fragment
    ):
        raise CatalogError(f"{field} must be an HTTPS URL")
    if hosts is not None and hostname not in hosts:
        raise CatalogError(f"{field} host is not trusted")
    return value


def _positive_int(payload: Mapping[str, Any], field: str, *, maximum: int) -> int:
    value = payload.get(field)
    if isinstance(value, bool) or not isinstance(value, int) or not 0 < value <= maximum:
        raise CatalogError(f"{field} is outside the supported range")
    return value


def _parse_entry(payload: Any) -> CatalogEntry:
    if not isinstance(payload, dict) or set(payload) != _FIELDS:
        raise CatalogError("catalog entry fields do not match schema")
    if payload.get("catalog_schema_version") != 1:
        raise CatalogError("unsupported catalog schema version")
    pack_id = payload.get("pack_id")
    version = payload.get("version")
    if not isinstance(pack_id, str) or not _PACK_ID.fullmatch(pack_id):
        raise CatalogError("invalid pack_id")
    if not isinstance(version, str) or not _SEMVER.fullmatch(version):
        raise CatalogError("version must be an exact semantic version")
    for field in (
        "display_name",
        "engine_id",
        "language",
        "core_compatibility",
        "engine_protocol",
        "engine_compatibility",
        "archive_root",
        "release_tag",
        "published_at",
    ):
        if not isinstance(payload.get(field), str) or not payload[field].strip():
            raise CatalogError(f"{field} must be a non-empty string")
    if payload["release_tag"].lower() in {"latest", "main", "master"}:
        raise CatalogError("release_tag must be immutable")
    if payload["archive_root"] != f"{pack_id}-voice-pack":
        raise CatalogError("archive_root does not match pack_id")
    if payload.get("voice_pack_schema_version") != 1:
        raise CatalogError("unsupported Voice Pack schema version")
    sha256 = payload.get("sha256")
    revision = payload.get("revision")
    if not isinstance(sha256, str) or not _SHA256.fullmatch(sha256):
        raise CatalogError("sha256 must be a lowercase SHA-256 digest")
    if not isinstance(revision, str) or not _REVISION.fullmatch(revision):
        raise CatalogError("revision must be a full immutable commit")
    hosts_raw = payload.get("allowed_redirect_hosts")
    if (
        not isinstance(hosts_raw, list)
        or not hosts_raw
        or len(hosts_raw) > 8
        or any(not isinstance(item, str) or item != item.lower() for item in hosts_raw)
    ):
        raise CatalogError("allowed_redirect_hosts must be a bounded lowercase host list")
    hosts = tuple(dict.fromkeys(hosts_raw))
    if len(hosts) != len(hosts_raw):
        raise CatalogError("allowed_redirect_hosts contains duplicates")
    host_set = set(hosts)
    download_url = _https_url(payload.get("download_url"), "download_url", hosts=host_set)
    license_url = _https_url(payload.get("license_url"), "license_url")
    notice_url = _https_url(payload.get("notice_url"), "notice_url")
    size_bytes = _positive_int(payload, "size_bytes", maximum=20 * 1024**3)
    max_files = _positive_int(payload, "max_files", maximum=4096)
    max_file_bytes = _positive_int(payload, "max_file_bytes", maximum=20 * 1024**3)
    max_uncompressed = _positive_int(
        payload, "max_uncompressed_bytes", maximum=60 * 1024**3
    )
    ratio = payload.get("max_compression_ratio")
    if isinstance(ratio, bool) or not isinstance(ratio, (int, float)) or not 1 <= ratio <= 1000:
        raise CatalogError("max_compression_ratio is outside the supported range")
    if max_file_bytes > max_uncompressed:
        raise CatalogError("max_file_bytes exceeds total uncompressed limit")
    if not isinstance(payload.get("recommend_select"), bool):
        raise CatalogError("recommend_select must be boolean")
    return CatalogEntry(
        pack_id=pack_id,
        version=version,
        display_name=payload["display_name"].strip(),
        engine_id=payload["engine_id"].strip(),
        language=payload["language"].strip(),
        core_compatibility=payload["core_compatibility"].strip(),
        voice_pack_schema_version=1,
        engine_protocol=payload["engine_protocol"].strip(),
        engine_compatibility=payload["engine_compatibility"].strip(),
        download_url=download_url,
        allowed_redirect_hosts=hosts,
        size_bytes=size_bytes,
        sha256=sha256,
        archive_root=payload["archive_root"],
        max_files=max_files,
        max_file_bytes=max_file_bytes,
        max_uncompressed_bytes=max_uncompressed,
        max_compression_ratio=float(ratio),
        license_url=license_url,
        notice_url=notice_url,
        release_tag=payload["release_tag"].strip(),
        revision=revision,
        published_at=payload["published_at"].strip(),
        recommend_select=payload["recommend_select"],
    )


class VoicePackCatalog:
    def __init__(self, entries: Mapping[str, CatalogEntry]):
        self._entries = dict(entries)

    @classmethod
    def load(cls, root: Path) -> "VoicePackCatalog":
        root = Path(root)
        entries: dict[str, CatalogEntry] = {}
        if not root.exists():
            raise CatalogError("trusted catalog directory is missing")
        for path in sorted(root.glob("*.json")):
            if path.name in {"catalog.schema.json", "catalog.example.json"}:
                continue
            try:
                raw = path.read_bytes()
                payload = json.loads(raw.decode("utf-8"))
            except (OSError, UnicodeError, json.JSONDecodeError) as exc:
                raise CatalogError("catalog entry is unreadable") from exc
            entry = _parse_entry(payload)
            if path.stem != f"{entry.pack_id}-{entry.version}":
                raise CatalogError("catalog filename does not match entry identity")
            if entry.key in entries:
                raise CatalogError("duplicate Voice Pack catalog entry")
            entries[entry.key] = entry
        return cls(entries)

    @classmethod
    def from_payloads(cls, payloads: list[Mapping[str, Any]]) -> "VoicePackCatalog":
        entries: dict[str, CatalogEntry] = {}
        for payload in payloads:
            entry = _parse_entry(payload)
            if entry.key in entries:
                raise CatalogError("duplicate Voice Pack catalog entry")
            entries[entry.key] = entry
        return cls(entries)

    def list(self) -> list[CatalogEntry]:
        return [self._entries[key] for key in sorted(self._entries)]

    def get(self, key: str) -> CatalogEntry:
        try:
            return self._entries[key]
        except KeyError as exc:
            raise CatalogError("Voice Pack release is not present in the trusted catalog") from exc

    @staticmethod
    def sha256(path: Path) -> str:
        digest = hashlib.sha256()
        with Path(path).open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()
