"""Trusted Voice Pack acquisition layered only on the PK-212 service seam."""

from __future__ import annotations

import asyncio
import functools
import hashlib
import json
import os
import shutil
import tempfile
import zipfile
from pathlib import Path, PurePosixPath
from typing import Any, Callable, Mapping, Protocol

from .archive import extract_archive
from .catalog import (
    PACK_ID_PATTERN,
    SEMVER_PATTERN,
    CatalogEntry,
    CatalogError,
    VoicePackCatalog,
)
from .downloader import HTTPSDownloader
from .errors import DistributionError


class RegistryService(Protocol):
    async def list_packs(self) -> dict[str, Any]: ...
    async def import_pack(self, package_path: Path) -> dict[str, Any]: ...
    async def enable(self, pack_id: str, version: str) -> dict[str, Any]: ...
    async def select(self, pack_id: str, version: str) -> dict[str, Any]: ...
    async def verify(self, pack_id: str, version: str) -> dict[str, Any]: ...
    async def compare_content(
        self,
        pack_id: str,
        version: str,
        candidate_root: Path,
    ) -> dict[str, Any]: ...


async def _run_blocking(function, *args):
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, functools.partial(function, *args))


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _safe_manifest_path(value: Any) -> str:
    if not isinstance(value, str) or not value or "\\" in value:
        raise DistributionError(
            "Voice Pack release manifest has an unsafe asset path",
            code="voice_pack_archive_unsafe",
        )
    path = PurePosixPath(value)
    if (
        path.is_absolute()
        or any(part in {"", ".", ".."} for part in path.parts)
        or path.parts[0].endswith(":")
    ):
        raise DistributionError(
            "Voice Pack release manifest has an unsafe asset path",
            code="voice_pack_archive_unsafe",
        )
    return path.as_posix()


def _declared_identity(source_root: Path) -> tuple[str, dict[str, Any]]:
    """Read only the identity precondition; PK-212 owns manifest validation."""
    try:
        payload = json.loads(
            (Path(source_root) / "voice-pack.json").read_text(encoding="utf-8")
        )
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise DistributionError(
            "Voice Pack release manifest is unreadable",
            code="voice_pack_archive_invalid",
        ) from exc
    if not isinstance(payload, dict):
        raise DistributionError(
            "Voice Pack release manifest is invalid",
            code="voice_pack_archive_invalid",
        )
    pack_id = payload.get("id")
    version = payload.get("version")
    if (
        not isinstance(pack_id, str)
        or not PACK_ID_PATTERN.fullmatch(pack_id)
        or not isinstance(version, str)
        or not SEMVER_PATTERN.fullmatch(version)
    ):
        raise DistributionError(
            "Voice Pack release identity is invalid",
            code="voice_pack_identity_mismatch",
        )
    return f"{pack_id}@{version}", payload


def _release_identity_and_files(source_root: Path) -> tuple[str, set[str]]:
    """Read only PK-213 release topology; PK-212 owns full manifest validation."""
    key, payload = _declared_identity(source_root)
    declared = set()
    for field in ("gpt_checkpoint", "sovits_checkpoint", "reference_audio"):
        value = payload.get(field)
        if not isinstance(value, dict):
            raise DistributionError(
                "Voice Pack release asset declaration is invalid",
                code="voice_pack_archive_invalid",
            )
        declared.add(_safe_manifest_path(value.get("path")))
    expected = {
        "voice-pack.json",
        "README.md",
        "LICENSE.txt",
        "NOTICE.txt",
        *declared,
    }
    actual = {
        path.relative_to(source_root).as_posix()
        for path in Path(source_root).rglob("*")
        if path.is_file()
    }
    if actual != expected:
        raise DistributionError(
            "Voice Pack release contains missing or undeclared files",
            code="voice_pack_archive_unsafe",
        )
    return key, expected


def _normalized_zip(source_root: Path, destination: Path) -> None:
    files = sorted(
        (
            path
            for path in Path(source_root).rglob("*")
            if path.is_file() and not path.is_symlink()
        ),
        key=lambda item: item.relative_to(source_root).as_posix(),
    )
    with zipfile.ZipFile(destination, "x", compression=zipfile.ZIP_STORED) as archive:
        for path in files:
            relative = path.relative_to(source_root).as_posix()
            info = zipfile.ZipInfo(relative, date_time=(2026, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_STORED
            info.create_system = 3
            info.create_version = 20
            info.extract_version = 20
            info.internal_attr = 0
            info.external_attr = 0o100644 << 16
            info.extra = b""
            info.comment = b""
            archive.writestr(info, path.read_bytes())


class VoicePackDistributionService:
    def __init__(
        self,
        *,
        catalog: VoicePackCatalog,
        registry_service: RegistryService,
        cache_root: Path,
        downloader: HTTPSDownloader | None = None,
        engine_status: Callable[[], Mapping[str, Any]] | None = None,
    ):
        self.catalog = catalog
        self.registry_service = registry_service
        self.cache_root = Path(cache_root)
        self.downloader = downloader or HTTPSDownloader()
        self.engine_status = engine_status or (
            lambda: {
                "engine_id": "gpt-sovits-v2pro-nvidia50",
                "configured": False,
                "entrypoints_ready": False,
                "status": "unregistered",
            }
        )
        self._lock: asyncio.Lock | None = None

    def _operation_lock(self) -> asyncio.Lock:
        if self._lock is None:
            self._lock = asyncio.Lock()
        return self._lock

    def _cache_path(self, entry: CatalogEntry) -> Path:
        return self.cache_root / f"{entry.pack_id}-{entry.version}-{entry.sha256}.zip"

    @staticmethod
    def _safe_engine_status(
        provider: Callable[[], Mapping[str, Any]],
    ) -> dict[str, Any]:
        try:
            raw = dict(provider())
        except Exception:
            raw = {}
        return {
            "engine_id": str(
                raw.get("engine_id") or "gpt-sovits-v2pro-nvidia50"
            ),
            "configured": bool(raw.get("configured")),
            "entrypoints_ready": bool(raw.get("entrypoints_ready")),
            "status": str(raw.get("status") or "unavailable"),
        }

    def _verify_cached(self, entry: CatalogEntry) -> Path | None:
        target = self._cache_path(entry)
        try:
            if (
                target.is_file()
                and target.stat().st_size == entry.size_bytes
                and _sha256(target) == entry.sha256
            ):
                return target
        except OSError:
            pass
        return None

    async def _installed(self) -> dict[str, dict[str, Any]]:
        snapshot = await self.registry_service.list_packs()
        return {
            f"{item['id']}@{item['version']}": item
            for item in snapshot.get("packs", ())
            if isinstance(item, dict) and item.get("id") and item.get("version")
        }

    async def list(self) -> dict[str, Any]:
        installed = await self._installed()
        engine = self._safe_engine_status(self.engine_status)
        releases = []
        for entry in self.catalog.list():
            local = installed.get(entry.key, {})
            releases.append(
                {
                    **entry.public_dict(),
                    "installed": bool(local),
                    "enabled": bool(local.get("enabled")),
                    "active": bool(local.get("active")),
                    "cached": self._verify_cached(entry) is not None,
                }
            )
        return {
            "catalog_schema_version": 1,
            "releases": releases,
            "engine": engine,
        }

    async def status(self, key: str) -> dict[str, Any]:
        installed = (await self._installed()).get(key)
        engine = self._safe_engine_status(self.engine_status)
        try:
            entry = self.catalog.get(key)
        except CatalogError:
            if installed is None:
                raise
            return {
                "release": None,
                "release_status": "local_unpublished",
                "pack": installed,
                "installed": True,
                "enabled": bool(installed.get("enabled")),
                "active": bool(installed.get("active")),
                "cached": False,
                "voice_available": bool(
                    installed.get("active") and engine["configured"]
                ),
                "engine": engine,
            }
        return {
            "release": entry.public_dict(),
            "installed": installed is not None,
            "enabled": bool(installed and installed.get("enabled")),
            "active": bool(installed and installed.get("active")),
            "cached": self._verify_cached(entry) is not None,
            "voice_available": bool(
                installed and installed.get("active") and engine["configured"]
            ),
            "engine": engine,
        }

    async def _acquire(self, entry: CatalogEntry) -> Path:
        cached = self._verify_cached(entry)
        if cached is not None:
            return cached
        self.cache_root.mkdir(parents=True, exist_ok=True)
        temp_path: Path | None = None
        try:
            fd, name = tempfile.mkstemp(
                prefix=f".{entry.pack_id}-{entry.version}-",
                suffix=".download",
                dir=str(self.cache_root),
            )
            os.close(fd)
            temp_path = Path(name)
            temp_path.unlink()
            await _run_blocking(self.downloader.download, entry, temp_path)
            target = self._cache_path(entry)
            if target.exists():
                existing = self._verify_cached(entry)
                temp_path.unlink(missing_ok=True)
                if existing is None:
                    raise DistributionError(
                        "trusted cache path contains conflicting content",
                        code="voice_pack_install_conflict",
                    )
                return existing
            os.replace(str(temp_path), str(target))
            temp_path = None
            return target
        finally:
            if temp_path is not None:
                temp_path.unlink(missing_ok=True)

    async def download_only(
        self,
        key: str,
        *,
        confirmation: str,
    ) -> dict[str, Any]:
        if confirmation != key:
            raise DistributionError(
                "exact pack confirmation is required",
                code="voice_pack_confirmation_required",
            )
        entry = self.catalog.get(key)
        async with self._operation_lock():
            archive = await self._acquire(entry)
            with tempfile.TemporaryDirectory(
                prefix="project-kei-voice-pack-audit-"
            ) as temp:
                pack_root = await _run_blocking(
                    extract_archive,
                    archive,
                    entry,
                    Path(temp) / "expanded",
                )
                declared_key, _ = await _run_blocking(
                    _release_identity_and_files,
                    pack_root,
                )
                if declared_key != key:
                    raise DistributionError(
                        "release manifest identity does not match catalog",
                        code="voice_pack_identity_mismatch",
                    )
            return {
                "status": "downloaded",
                "id": entry.pack_id,
                "version": entry.version,
                "size_bytes": entry.size_bytes,
                "sha256": entry.sha256,
                "installed": False,
                "selected": False,
            }

    async def install(
        self,
        key: str,
        *,
        confirmation: str,
        select: bool | None = None,
    ) -> dict[str, Any]:
        if confirmation != key:
            raise DistributionError(
                "exact pack confirmation is required",
                code="voice_pack_confirmation_required",
            )
        entry = self.catalog.get(key)
        async with self._operation_lock():
            installed = await self._installed()
            cached = self._verify_cached(entry)
            archive = cached or await self._acquire(entry)
            with tempfile.TemporaryDirectory(
                prefix="project-kei-voice-pack-install-"
            ) as temp:
                temp_root = Path(temp)
                pack_root = await _run_blocking(
                    extract_archive,
                    archive,
                    entry,
                    temp_root / "expanded",
                )
                declared_key, _ = await _run_blocking(
                    _release_identity_and_files,
                    pack_root,
                )
                if declared_key != key:
                    raise DistributionError(
                        "release manifest identity does not match catalog",
                        code="voice_pack_identity_mismatch",
                    )
                if key in installed:
                    try:
                        comparison = await self.registry_service.compare_content(
                            entry.pack_id,
                            entry.version,
                            pack_root,
                        )
                    except Exception as exc:
                        raise DistributionError(
                            "installed Voice Pack content cannot be proven equivalent",
                            code="voice_pack_install_conflict",
                        ) from exc
                    if not comparison.get("equivalent"):
                        raise DistributionError(
                            "installed Voice Pack content conflicts with trusted release",
                            code="voice_pack_install_conflict",
                        )
                    verified = await self.registry_service.verify(
                        entry.pack_id,
                        entry.version,
                    )
                    return {
                        "status": "already_installed",
                        "pack": verified,
                        "selected": bool(verified.get("active")),
                        "engine": self._safe_engine_status(self.engine_status),
                    }
                normalized = temp_root / "pk212-import.zip"
                await _run_blocking(_normalized_zip, pack_root, normalized)
                imported = await self.registry_service.import_pack(normalized)
            enabled = await self.registry_service.enable(
                entry.pack_id,
                entry.version,
            )
            engine = self._safe_engine_status(self.engine_status)
            should_select = entry.recommend_select if select is None else bool(select)
            selected = False
            selection_error = None
            if should_select and engine["configured"]:
                try:
                    enabled = await self.registry_service.select(
                        entry.pack_id,
                        entry.version,
                    )
                    selected = True
                except Exception:
                    selection_error = "voice_pack_selection_failed"
            elif should_select:
                selection_error = "voice_pack_engine_unavailable"
            return {
                "status": "installed",
                "pack": enabled or imported,
                "selected": selected,
                "selection_error": selection_error,
                "engine": engine,
            }

    async def import_local(
        self,
        source: Path,
        *,
        expected_key: str | None = None,
        expected_sha256: str | None = None,
    ) -> dict[str, Any]:
        source = Path(source)
        async with self._operation_lock():
            if source.is_dir():
                if expected_key is not None:
                    declared_key, _ = await _run_blocking(
                        _declared_identity,
                        source,
                    )
                    if declared_key != expected_key:
                        raise DistributionError(
                            "local Voice Pack identity does not match confirmation",
                            code="voice_pack_identity_mismatch",
                        )
                result = await self.registry_service.import_pack(source)
                return {
                    "status": "installed",
                    "release_status": "local_unpublished",
                    "pack": result,
                    "source_preserved": True,
                }
            if not source.is_file() or source.suffix.lower() != ".zip":
                raise DistributionError(
                    "local import requires an explicit ZIP or directory",
                    code="voice_pack_local_source_invalid",
                )
            if expected_key is None:
                raise DistributionError(
                    "local ZIP requires exact id@version confirmation",
                    code="voice_pack_confirmation_required",
                )
            pack_id, separator, version = expected_key.partition("@")
            if (
                not separator
                or not PACK_ID_PATTERN.fullmatch(pack_id)
                or not SEMVER_PATTERN.fullmatch(version)
            ):
                raise DistributionError(
                    "local ZIP identity is invalid",
                    code="voice_pack_identity_mismatch",
                )
            try:
                entry = self.catalog.get(expected_key)
                release_status = "catalog_release"
            except CatalogError:
                digest = await _run_blocking(_sha256, source)
                if expected_sha256 != digest:
                    raise DistributionError(
                        "local ZIP requires the caller-provided SHA-256",
                        code="voice_pack_integrity_mismatch",
                    )
                entry = CatalogEntry(
                    pack_id=pack_id,
                    version=version,
                    display_name=pack_id,
                    engine_id="gpt-sovits-v2pro-nvidia50",
                    language="unknown",
                    core_compatibility="unpublished",
                    voice_pack_schema_version=1,
                    engine_protocol="pk210-tts-v1",
                    engine_compatibility="unpublished",
                    download_url="https://invalid.example/unpublished.zip",
                    allowed_redirect_hosts=("invalid.example",),
                    size_bytes=source.stat().st_size,
                    sha256=digest,
                    archive_root=f"{pack_id}-voice-pack",
                    max_files=2048,
                    max_file_bytes=20 * 1024**3,
                    max_uncompressed_bytes=40 * 1024**3,
                    max_compression_ratio=500.0,
                    license_url="https://invalid.example/license",
                    notice_url="https://invalid.example/notice",
                    release_tag="unpublished",
                    revision="0" * 40,
                    published_at="unpublished",
                    recommend_select=False,
                )
                release_status = "local_unpublished"
            if (
                source.stat().st_size != entry.size_bytes
                or await _run_blocking(_sha256, source) != entry.sha256
            ):
                raise DistributionError(
                    "local ZIP does not match trusted catalog",
                    code="voice_pack_integrity_mismatch",
                )
            with tempfile.TemporaryDirectory(
                prefix="project-kei-voice-pack-local-"
            ) as temp:
                temp_root = Path(temp)
                pack_root = await _run_blocking(
                    extract_archive,
                    source,
                    entry,
                    temp_root / "expanded",
                )
                declared_key, _ = await _run_blocking(
                    _release_identity_and_files,
                    pack_root,
                )
                if declared_key != expected_key:
                    raise DistributionError(
                        "local Voice Pack identity does not match confirmation",
                        code="voice_pack_identity_mismatch",
                    )
                normalized = temp_root / "pk212-import.zip"
                await _run_blocking(_normalized_zip, pack_root, normalized)
                result = await self.registry_service.import_pack(normalized)
            return {
                "status": "installed",
                "release_status": release_status,
                "pack": result,
                "source_preserved": True,
            }

    async def select(self, key: str) -> dict[str, Any]:
        pack_id, separator, version = key.partition("@")
        if not separator:
            raise DistributionError(
                "invalid Voice Pack identity",
                code="voice_pack_identity_mismatch",
            )
        result = await self.registry_service.select(pack_id, version)
        return {"status": "selected", "pack": result}

    async def verify(self, key: str) -> dict[str, Any]:
        pack_id, separator, version = key.partition("@")
        if not separator:
            raise DistributionError(
                "invalid Voice Pack identity",
                code="voice_pack_identity_mismatch",
            )
        result = await self.registry_service.verify(pack_id, version)
        cached = None
        try:
            entry = self.catalog.get(key)
            cached = self._verify_cached(entry) is not None
        except CatalogError:
            pass
        return {
            "status": "verified",
            "pack": result,
            "catalog_cache_verified": cached,
            "engine": self._safe_engine_status(self.engine_status),
        }
