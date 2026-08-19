"""Local import, validation, activation, and resolution for Voice Packs."""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import re
import shutil
import stat
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any, Callable, Mapping, Protocol, TypeVar

from ..errors import VoiceError
from ..models import ProviderCapabilities, ProviderHealth, VoicePackRef
from .errors import (
    VoicePackConflictError,
    VoicePackError,
    VoicePackNotFoundError,
    VoicePackPackageError,
    VoicePackRegistryError,
    VoicePackSwitchError,
)
from .manifest import (
    FORBIDDEN_PACKAGE_SUFFIXES,
    MANIFEST_FILENAME,
    VoicePackManifest,
    load_manifest,
    parse_manifest,
    safe_relative_path,
    validate_assets,
    validate_package_tree,
)
from .registry import VoicePackRegistry


MAX_ARCHIVE_FILES = 2048
MAX_ARCHIVE_BYTES = 40 * 1024 * 1024 * 1024
_T = TypeVar("_T")


class VoicePackActivator(Protocol):
    async def activate_voice_pack(self, voice_pack: VoicePackRef) -> None: ...


class TransactionalVoicePackActivator(VoicePackActivator, Protocol):
    async def activate_voice_pack_transaction(
        self,
        voice_pack: VoicePackRef,
        commit: Callable[[], _T],
    ) -> _T: ...

    def voice_pack_state(self) -> Mapping[str, Any]: ...


def _key(pack_id: str, version: str) -> str:
    return f"{pack_id}@{version}"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _version_key(value: str) -> tuple[int, int, int, int, str]:
    match = re.match(r"^(\d+)\.(\d+)\.(\d+)(?:-([^+]+))?", value)
    if not match:
        return 0, 0, 0, 0, value
    prerelease = match.group(4) or ""
    return int(match.group(1)), int(match.group(2)), int(match.group(3)), 1 if not prerelease else 0, prerelease


class VoicePackRegistryService:
    """PK-212 service and PK-210 VoicePackResolver implementation."""

    def __init__(
        self,
        registry: VoicePackRegistry,
        *,
        runtime_root: Path,
        activator: VoicePackActivator | None = None,
    ):
        self.registry = registry
        self.runtime_root = Path(runtime_root)
        self.activator = activator
        self._operation_lock: asyncio.Lock | None = None
        self._operation_loop = None
        self._closed = False
        self._engine_state_unknown = False

    def _lock(self) -> asyncio.Lock:
        loop = asyncio.get_running_loop()
        if self._operation_lock is None or self._operation_loop is not loop:
            self._operation_lock = asyncio.Lock()
            self._operation_loop = loop
        return self._operation_lock

    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(
            provider="voice-pack-registry",
            operations=("import", "list", "enable", "select", "disable", "unregister", "resolve"),
            default_timeout_seconds=5.0,
        )

    async def health(self) -> ProviderHealth:
        if self._closed:
            return ProviderHealth(False, "closed", error_code="voice_pack_closed")
        engine_status = self._activator_status()
        if engine_status == "unknown":
            return ProviderHealth(False, "unknown", error_code="voice_pack_engine_state_unknown")
        if engine_status == "closed":
            return ProviderHealth(False, "closed", error_code="voice_pack_engine_closed")
        if engine_status == "switching":
            return ProviderHealth(False, "switching", error_code="voice_pack_engine_switching")
        try:
            snapshot = self.registry.load()
            active = snapshot.get("active")
            available = bool(active and active in snapshot["packs"] and snapshot["packs"][active].get("enabled"))
            return ProviderHealth(available, "available" if available else "unconfigured", error_code=None if available else "voice_pack_unconfigured")
        except VoicePackRegistryError:
            return ProviderHealth(False, "invalid", error_code="voice_pack_registry_invalid")

    def _activator_status(self) -> str | None:
        if self._engine_state_unknown:
            return "unknown"
        state_reader = getattr(self.activator, "voice_pack_state", None)
        if not callable(state_reader):
            return None
        try:
            state = state_reader()
        except Exception:
            return "unknown"
        if not isinstance(state, Mapping):
            return "unknown"
        status = state.get("status")
        return str(status) if status is not None else "unknown"

    def _require_known_engine_state(self) -> None:
        status = self._activator_status()
        if status == "unknown":
            raise VoiceError(
                stage="voice_pack",
                code="voice_pack_engine_state_unknown",
                message="Voice Pack 引擎状态未知",
                status_code=503,
            )
        if status in {"closed", "switching"}:
            raise VoiceError(
                stage="voice_pack",
                code="voice_pack_unavailable",
                message="Voice Pack 不可用",
                status_code=503,
            )

    @staticmethod
    def _public_entry(entry: Mapping[str, Any], *, active: bool) -> dict[str, Any]:
        manifest = dict(entry["manifest"])
        return {
            "id": manifest["id"],
            "name": manifest["name"],
            "version": manifest["version"],
            "engine": manifest["engine"],
            "supported_languages": manifest["supported_languages"],
            "integrity": {
                "gpt_checkpoint": manifest["gpt_checkpoint"]["integrity"]["mode"],
                "sovits_checkpoint": manifest["sovits_checkpoint"]["integrity"]["mode"],
                "reference_audio": manifest["reference_audio"]["integrity"]["mode"],
            },
            "enabled": bool(entry.get("enabled")),
            "active": active,
            "registered_at": entry.get("registered_at"),
            "source_type": entry.get("source_type"),
        }

    async def list_packs(self) -> dict[str, Any]:
        async with self._lock():
            snapshot = self.registry.load()
            engine_status = self._activator_status()
            active = None if engine_status in {"unknown", "closed", "switching"} else snapshot.get("active")
            packs = [
                self._public_entry(entry, active=key == active)
                for key, entry in sorted(snapshot["packs"].items())
            ]
            return {
                "registry_version": snapshot["registry_version"],
                "active": active,
                "engine_state": engine_status or "external",
                "packs": packs,
            }

    @staticmethod
    def _entry_manifest(entry: Mapping[str, Any]) -> VoicePackManifest:
        return parse_manifest(entry.get("manifest"), portable=bool(entry.get("portable", True)))

    @staticmethod
    def _entry_bindings(entry: Mapping[str, Any]) -> Mapping[str, str]:
        bindings = entry.get("asset_bindings")
        if not isinstance(bindings, dict) or any(not isinstance(k, str) or not isinstance(v, str) for k, v in bindings.items()):
            raise VoicePackRegistryError("Voice Pack registry contains invalid local bindings")
        return bindings

    def _validate_entry(self, entry: Mapping[str, Any]) -> tuple[VoicePackManifest, dict[str, str]]:
        manifest = self._entry_manifest(entry)
        bindings = self._entry_bindings(entry)
        return manifest, validate_assets(manifest, bindings=bindings, verify_digest=True)

    @staticmethod
    def _content_fingerprint(manifest: VoicePackManifest) -> str:
        payload = json.dumps(
            manifest.to_dict(),
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
        return hashlib.sha256(payload).hexdigest()

    @staticmethod
    def _ref(manifest: VoicePackManifest, bindings: Mapping[str, str]) -> VoicePackRef:
        handle = {
            "gpt_checkpoint_path": bindings[manifest.gpt_checkpoint.path],
            "sovits_checkpoint_path": bindings[manifest.sovits_checkpoint.path],
            "ref_audio_path": bindings[manifest.reference_audio.path],
            "prompt_text": manifest.reference_text,
            "prompt_lang": manifest.reference_language,
            "text_lang": manifest.default_text_language,
            "supported_languages": list(manifest.supported_languages),
            "generation_parameters": dict(manifest.generation_parameters),
        }
        return VoicePackRef(manifest.id, manifest.version, manifest.engine.provider, handle=handle)

    async def resolve_active_pack(self) -> VoicePackRef:
        if self._closed:
            raise VoiceError(stage="voice_pack", code="voice_pack_unavailable", message="Voice Pack 不可用", status_code=503)
        self._require_known_engine_state()
        try:
            snapshot = self.registry.load()
            active = snapshot.get("active")
            if not active or active not in snapshot["packs"]:
                raise VoicePackNotFoundError("no active Voice Pack")
            entry = snapshot["packs"][active]
            if not entry.get("enabled"):
                raise VoicePackNotFoundError("active Voice Pack is disabled")
            manifest, bindings = self._validate_entry(entry)
            return self._ref(manifest, bindings)
        except VoicePackNotFoundError as exc:
            raise VoiceError(stage="voice_pack", code="voice_pack_unavailable", message="Voice Pack 不可用", status_code=503) from exc
        except VoicePackError as exc:
            raise VoiceError(stage="voice_pack", code="voice_pack_invalid", message="Voice Pack 配置无效", status_code=503) from exc

    async def resolve_pack(self, pack_id: str) -> VoicePackRef:
        if self._closed:
            raise VoiceError(stage="voice_pack", code="voice_pack_unavailable", message="Voice Pack 不可用", status_code=503)
        self._require_known_engine_state()
        try:
            snapshot = self.registry.load()
            candidates = [
                entry for entry in snapshot["packs"].values()
                if entry.get("manifest", {}).get("id") == pack_id and entry.get("enabled")
            ]
            if not candidates:
                raise VoicePackNotFoundError("Voice Pack not found")
            candidates.sort(key=lambda item: _version_key(item["manifest"]["version"]), reverse=True)
            manifest, bindings = self._validate_entry(candidates[0])
            return self._ref(manifest, bindings)
        except VoicePackNotFoundError as exc:
            raise VoiceError(stage="voice_pack", code="voice_pack_not_found", message="Voice Pack 不存在", status_code=404) from exc
        except VoicePackError as exc:
            raise VoiceError(stage="voice_pack", code="voice_pack_invalid", message="Voice Pack 配置无效", status_code=503) from exc

    @staticmethod
    def _safe_zip_member(name: str) -> PurePosixPath:
        safe_relative_path(name.rstrip("/"), "archive member")
        return PurePosixPath(name.rstrip("/"))

    def _extract_zip(self, archive: Path) -> Path:
        self.runtime_root.parent.mkdir(parents=True, exist_ok=True)
        temp_root = Path(tempfile.mkdtemp(prefix="voice-pack-", dir=str(self.runtime_root.parent)))
        try:
            with zipfile.ZipFile(archive) as package:
                infos = package.infolist()
                if len(infos) > MAX_ARCHIVE_FILES or sum(item.file_size for item in infos) > MAX_ARCHIVE_BYTES:
                    raise VoicePackPackageError("Voice Pack archive exceeds safety limits")
                for info in infos:
                    member = self._safe_zip_member(info.filename)
                    mode = info.external_attr >> 16
                    if stat.S_ISLNK(mode):
                        raise VoicePackPackageError("symbolic links are not allowed in Voice Packs")
                    if member.suffix.lower() in FORBIDDEN_PACKAGE_SUFFIXES:
                        raise VoicePackPackageError("Voice Packs cannot contain executable or installer files")
                    target = temp_root.joinpath(*member.parts)
                    target.parent.mkdir(parents=True, exist_ok=True)
                    if info.is_dir():
                        target.mkdir(parents=True, exist_ok=True)
                    else:
                        with package.open(info) as source, target.open("wb") as destination:
                            shutil.copyfileobj(source, destination, length=1024 * 1024)
            return temp_root
        except (OSError, zipfile.BadZipFile, VoicePackError) as exc:
            shutil.rmtree(temp_root, ignore_errors=True)
            if isinstance(exc, VoicePackError):
                raise
            raise VoicePackPackageError("Voice Pack archive is invalid") from exc

    async def import_pack(self, package_path: Path) -> dict[str, Any]:
        async with self._lock():
            source = Path(package_path)
            staged: Path | None = None
            managed: Path | None = None
            try:
                if source.is_dir():
                    root = source
                    source_type = "directory"
                elif source.is_file() and source.suffix.lower() == ".zip":
                    staged = self._extract_zip(source)
                    root = staged
                    source_type = "archive"
                else:
                    raise VoicePackPackageError("Voice Pack import source must be a local directory or ZIP")
                validate_package_tree(root)
                manifest = load_manifest(root / MANIFEST_FILENAME, portable=True)
                bindings = validate_assets(manifest, package_root=root, verify_digest=True)
                key = _key(manifest.id, manifest.version)
                snapshot = self.registry.load()
                if key in snapshot["packs"]:
                    raise VoicePackConflictError("Voice Pack ID and version are already registered")
                if staged is not None:
                    managed = self.runtime_root / manifest.id / manifest.version
                    if managed.exists():
                        raise VoicePackConflictError("Voice Pack runtime version already exists")
                    managed.parent.mkdir(parents=True, exist_ok=True)
                    os.replace(str(staged), str(managed))
                    staged = None
                    bindings = validate_assets(manifest, package_root=managed, verify_digest=True)
                snapshot["packs"][key] = {
                    "manifest": manifest.to_dict(),
                    "portable": True,
                    "asset_bindings": bindings,
                    "source_type": source_type,
                    "enabled": False,
                    "registered_at": _utc_now(),
                }
                self.registry.save(snapshot)
                return self._public_entry(snapshot["packs"][key], active=False)
            except Exception:
                if managed is not None and managed.exists():
                    shutil.rmtree(managed, ignore_errors=True)
                raise
            finally:
                if staged is not None and staged.exists():
                    shutil.rmtree(staged, ignore_errors=True)

    async def register_local(
        self,
        manifest_payload: Mapping[str, Any],
        bindings: Mapping[str, str | Path],
        *,
        enabled: bool = True,
        make_active: bool = True,
    ) -> dict[str, Any]:
        """Register existing files without reading their contents or calculating digests."""
        async with self._lock():
            manifest = parse_manifest(dict(manifest_payload), portable=False)
            normalized = validate_assets(manifest, bindings=bindings, verify_digest=False)
            key = _key(manifest.id, manifest.version)
            snapshot = self.registry.load()
            if key in snapshot["packs"]:
                raise VoicePackConflictError("Voice Pack ID and version are already registered")
            snapshot["packs"][key] = {
                "manifest": manifest.to_dict(),
                "portable": False,
                "asset_bindings": normalized,
                "source_type": "local_binding",
                "enabled": bool(enabled),
                "registered_at": _utc_now(),
            }
            if make_active:
                snapshot["active"] = key
            self.registry.save(snapshot)
            return self._public_entry(snapshot["packs"][key], active=make_active)

    async def enable(self, pack_id: str, version: str) -> dict[str, Any]:
        async with self._lock():
            snapshot = self.registry.load()
            key = _key(pack_id, version)
            entry = snapshot["packs"].get(key)
            if entry is None:
                raise VoicePackNotFoundError("Voice Pack not found")
            self._validate_entry(entry)
            entry["enabled"] = True
            self.registry.save(snapshot)
            return self._public_entry(entry, active=snapshot.get("active") == key)

    async def verify(self, pack_id: str, version: str) -> dict[str, Any]:
        """Revalidate one installed Pack without changing Registry or Engine state."""
        async with self._lock():
            snapshot = self.registry.load()
            key = _key(pack_id, version)
            entry = snapshot["packs"].get(key)
            if entry is None:
                raise VoicePackNotFoundError("Voice Pack not found")
            self._validate_entry(entry)
            return self._public_entry(entry, active=snapshot.get("active") == key)

    async def compare_content(
        self,
        pack_id: str,
        version: str,
        candidate_root: Path,
    ) -> dict[str, Any]:
        """Compare validated Pack content without exposing paths or changing state."""
        async with self._lock():
            snapshot = self.registry.load()
            key = _key(pack_id, version)
            entry = snapshot["packs"].get(key)
            if entry is None:
                raise VoicePackNotFoundError("Voice Pack not found")
            installed_manifest, _ = self._validate_entry(entry)
            root = Path(candidate_root)
            validate_package_tree(root)
            candidate_manifest = load_manifest(root / MANIFEST_FILENAME, portable=True)
            validate_assets(candidate_manifest, package_root=root, verify_digest=True)
            candidate_key = _key(candidate_manifest.id, candidate_manifest.version)
            equivalent = (
                candidate_key == key
                and self._content_fingerprint(installed_manifest)
                == self._content_fingerprint(candidate_manifest)
            )
            return {
                "id": pack_id,
                "version": version,
                "equivalent": equivalent,
            }

    async def select(self, pack_id: str, version: str) -> dict[str, Any]:
        async with self._lock():
            snapshot = self.registry.load()
            key = _key(pack_id, version)
            entry = snapshot["packs"].get(key)
            if entry is None:
                raise VoicePackNotFoundError("Voice Pack not found")
            if not entry.get("enabled"):
                raise VoicePackSwitchError("Voice Pack must be enabled before selection")
            manifest, bindings = self._validate_entry(entry)
            candidate = self._ref(manifest, bindings)
            previous_key = snapshot.get("active")
            previous_ref: VoicePackRef | None = None
            if previous_key and previous_key in snapshot["packs"]:
                old_manifest, old_bindings = self._validate_entry(snapshot["packs"][previous_key])
                previous_ref = self._ref(old_manifest, old_bindings)
            transaction = getattr(self.activator, "activate_voice_pack_transaction", None)
            snapshot["active"] = key
            try:
                if callable(transaction):
                    await transaction(candidate, lambda: self.registry.save(snapshot))
                else:
                    if self.activator is not None:
                        await self.activator.activate_voice_pack(candidate)
                    self.registry.save(snapshot)
                self._engine_state_unknown = False
            except asyncio.CancelledError:
                if not callable(transaction) and self.activator is not None and previous_ref is not None:
                    rollback = asyncio.create_task(self.activator.activate_voice_pack(previous_ref))
                    try:
                        await asyncio.shield(rollback)
                    except Exception:
                        self._engine_state_unknown = True
                if self._activator_status() == "unknown":
                    self._engine_state_unknown = True
                raise
            except Exception as exc:
                if not callable(transaction) and self.activator is not None and previous_ref is not None:
                    try:
                        await self.activator.activate_voice_pack(previous_ref)
                    except Exception:
                        self._engine_state_unknown = True
                if self._activator_status() == "unknown":
                    self._engine_state_unknown = True
                if self._engine_state_unknown:
                    raise VoicePackSwitchError("Voice Pack selection failed; engine state is unknown") from exc
                if isinstance(exc, VoicePackRegistryError):
                    raise
                raise VoicePackSwitchError("Voice Pack selection failed; previous selection was preserved") from exc
            return self._public_entry(entry, active=True)

    async def disable(self, pack_id: str, version: str) -> dict[str, Any]:
        async with self._lock():
            snapshot = self.registry.load()
            key = _key(pack_id, version)
            entry = snapshot["packs"].get(key)
            if entry is None:
                raise VoicePackNotFoundError("Voice Pack not found")
            entry["enabled"] = False
            if snapshot.get("active") == key:
                snapshot["active"] = None
            self.registry.save(snapshot)
            return self._public_entry(entry, active=False)

    async def unregister(self, pack_id: str, version: str) -> dict[str, Any]:
        async with self._lock():
            snapshot = self.registry.load()
            key = _key(pack_id, version)
            entry = snapshot["packs"].get(key)
            if entry is None:
                raise VoicePackNotFoundError("Voice Pack not found")
            del snapshot["packs"][key]
            if snapshot.get("active") == key:
                snapshot["active"] = None
            self.registry.save(snapshot)
            return {
                "id": pack_id,
                "version": version,
                "unregistered": True,
                "source_assets_deleted": False,
            }

    async def cancel(self, _request_id: str) -> None:
        return None

    async def close(self) -> None:
        self._closed = True
