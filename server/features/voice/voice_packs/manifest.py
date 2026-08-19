"""Versioned Voice Pack manifest parsing and asset-integrity validation."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Mapping

from .errors import VoicePackManifestError, VoicePackPackageError


SCHEMA_VERSION = 1
MANIFEST_FILENAME = "voice-pack.json"
PACK_ID_PATTERN = re.compile(r"^[a-z][a-z0-9-]{0,63}$")
SEMVER_PATTERN = re.compile(
    r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)"
    r"(?:-([0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?"
    r"(?:\+[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?$"
)
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
KNOWN_ENGINES = {"gpt-sovits"}
ALLOWED_MODEL_SUFFIXES = {".ckpt", ".pth", ".pt", ".safetensors"}
ALLOWED_AUDIO_SUFFIXES = {".wav", ".mp3", ".flac", ".ogg", ".m4a"}
FORBIDDEN_PACKAGE_SUFFIXES = {
    ".bat", ".cmd", ".ps1", ".psm1", ".py", ".pyw", ".exe", ".com",
    ".msi", ".dll", ".scr", ".js", ".vbs", ".sh",
}
GENERATION_FIELDS = {
    "top_k", "top_p", "temperature", "speed_factor", "text_split_method", "seed",
}


@dataclass(frozen=True)
class AssetIntegrity:
    mode: str
    size_bytes: int | None = None
    sha256: str | None = None


@dataclass(frozen=True)
class AssetSpec:
    path: str
    integrity: AssetIntegrity


@dataclass(frozen=True)
class EngineSpec:
    provider: str
    protocol_version: str


@dataclass(frozen=True)
class VoicePackManifest:
    schema_version: int
    id: str
    name: str
    version: str
    engine: EngineSpec
    supported_languages: tuple[str, ...]
    gpt_checkpoint: AssetSpec
    sovits_checkpoint: AssetSpec
    reference_audio: AssetSpec
    reference_text: str
    reference_language: str
    default_text_language: str
    generation_parameters: Mapping[str, Any]
    metadata: Mapping[str, str]

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["supported_languages"] = list(self.supported_languages)
        payload["generation_parameters"] = dict(self.generation_parameters)
        payload["metadata"] = dict(self.metadata)
        return payload


def _object(value: Any, field: str, allowed: set[str]) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise VoicePackManifestError(f"{field} must be an object")
    unknown = sorted(set(value) - allowed)
    if unknown:
        raise VoicePackManifestError(f"{field} contains unsupported fields")
    return value


def _string(value: Any, field: str, *, maximum: int = 500) -> str:
    if not isinstance(value, str) or not value.strip():
        raise VoicePackManifestError(f"{field} must be a non-empty string")
    normalized = value.strip()
    if len(normalized) > maximum or "\x00" in normalized:
        raise VoicePackManifestError(f"{field} is invalid")
    return normalized


def safe_relative_path(value: Any, field: str) -> str:
    normalized = _string(value, field, maximum=240)
    if "\\" in normalized or re.match(r"^[A-Za-z]:", normalized):
        raise VoicePackManifestError(f"{field} must use a package-relative POSIX path")
    path = PurePosixPath(normalized)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise VoicePackManifestError(f"{field} escapes the Voice Pack")
    if path.suffix.lower() in FORBIDDEN_PACKAGE_SUFFIXES:
        raise VoicePackManifestError(f"{field} cannot reference executable content")
    return path.as_posix()


def _asset(value: Any, field: str, *, portable: bool, suffixes: set[str]) -> AssetSpec:
    payload = _object(value, field, {"path", "integrity"})
    relative = safe_relative_path(payload.get("path"), f"{field}.path")
    if PurePosixPath(relative).suffix.lower() not in suffixes:
        raise VoicePackManifestError(f"{field}.path has an unsupported file type")
    integrity = _object(
        payload.get("integrity"), f"{field}.integrity", {"mode", "size_bytes", "sha256"}
    )
    mode = _string(integrity.get("mode"), f"{field}.integrity.mode", maximum=32)
    if mode not in {"sha256", "existence_only"}:
        raise VoicePackManifestError(f"{field}.integrity.mode is unsupported")
    if portable and mode != "sha256":
        raise VoicePackManifestError("portable Voice Packs require SHA-256 integrity")
    size = integrity.get("size_bytes")
    digest = integrity.get("sha256")
    if mode == "sha256":
        if not isinstance(size, int) or isinstance(size, bool) or size < 0:
            raise VoicePackManifestError(f"{field}.integrity.size_bytes is invalid")
        if not isinstance(digest, str) or not SHA256_PATTERN.fullmatch(digest.lower()):
            raise VoicePackManifestError(f"{field}.integrity.sha256 is invalid")
        digest = digest.lower()
    elif size is not None or digest is not None:
        raise VoicePackManifestError("existence_only integrity cannot claim a digest or size")
    return AssetSpec(relative, AssetIntegrity(mode, size, digest))


def parse_manifest(payload: Any, *, portable: bool = True) -> VoicePackManifest:
    root = _object(payload, "manifest", {
        "schema_version", "id", "name", "version", "engine", "supported_languages",
        "gpt_checkpoint", "sovits_checkpoint", "reference_audio", "reference_text",
        "reference_language", "default_text_language", "generation_parameters", "metadata",
    })
    if root.get("schema_version") != SCHEMA_VERSION:
        raise VoicePackManifestError("unsupported Voice Pack schema_version", code="voice_pack_schema_unsupported")
    pack_id = _string(root.get("id"), "id", maximum=64)
    if not PACK_ID_PATTERN.fullmatch(pack_id):
        raise VoicePackManifestError("id must use lowercase letters, digits, and hyphens")
    version = _string(root.get("version"), "version", maximum=80)
    if not SEMVER_PATTERN.fullmatch(version):
        raise VoicePackManifestError("version must be semantic versioning")
    engine_payload = _object(root.get("engine"), "engine", {"provider", "protocol_version"})
    provider = _string(engine_payload.get("provider"), "engine.provider", maximum=80)
    if provider not in KNOWN_ENGINES:
        raise VoicePackManifestError("unknown Voice Pack engine", code="voice_pack_engine_unknown")
    protocol = _string(engine_payload.get("protocol_version"), "engine.protocol_version", maximum=80)

    languages = root.get("supported_languages")
    if not isinstance(languages, list) or not languages or any(not isinstance(item, str) for item in languages):
        raise VoicePackManifestError("supported_languages must be a non-empty string array")
    normalized_languages = tuple(item.strip().lower() for item in languages)
    if any(not item or len(item) > 20 for item in normalized_languages) or len(set(normalized_languages)) != len(normalized_languages):
        raise VoicePackManifestError("supported_languages contains invalid values")
    reference_language = _string(root.get("reference_language"), "reference_language", maximum=20).lower()
    text_language = _string(root.get("default_text_language"), "default_text_language", maximum=20).lower()
    if reference_language not in normalized_languages or text_language not in normalized_languages:
        raise VoicePackManifestError("reference/default language must be supported")

    generation = root.get("generation_parameters", {})
    generation = _object(generation, "generation_parameters", GENERATION_FIELDS)
    for key, value in generation.items():
        if key in {"top_k", "seed"} and (not isinstance(value, int) or isinstance(value, bool)):
            raise VoicePackManifestError(f"generation_parameters.{key} must be an integer")
        if key in {"top_p", "temperature", "speed_factor"} and (
            not isinstance(value, (int, float)) or isinstance(value, bool) or float(value) <= 0
        ):
            raise VoicePackManifestError(f"generation_parameters.{key} must be positive")
        if key == "text_split_method" and (not isinstance(value, str) or not value.strip()):
            raise VoicePackManifestError("generation_parameters.text_split_method is invalid")

    metadata = root.get("metadata", {})
    metadata = _object(metadata, "metadata", {"source", "author", "license", "redistribution"})
    normalized_metadata = {key: _string(value, f"metadata.{key}", maximum=300) for key, value in metadata.items()}
    if normalized_metadata.get("redistribution") not in {None, "allowed", "restricted", "unknown"}:
        raise VoicePackManifestError("metadata.redistribution is invalid")

    return VoicePackManifest(
        schema_version=SCHEMA_VERSION,
        id=pack_id,
        name=_string(root.get("name"), "name", maximum=120),
        version=version,
        engine=EngineSpec(provider, protocol),
        supported_languages=normalized_languages,
        gpt_checkpoint=_asset(root.get("gpt_checkpoint"), "gpt_checkpoint", portable=portable, suffixes=ALLOWED_MODEL_SUFFIXES),
        sovits_checkpoint=_asset(root.get("sovits_checkpoint"), "sovits_checkpoint", portable=portable, suffixes=ALLOWED_MODEL_SUFFIXES),
        reference_audio=_asset(root.get("reference_audio"), "reference_audio", portable=portable, suffixes=ALLOWED_AUDIO_SUFFIXES),
        reference_text=_string(root.get("reference_text"), "reference_text", maximum=2000),
        reference_language=reference_language,
        default_text_language=text_language,
        generation_parameters=generation,
        metadata=normalized_metadata,
    )


def load_manifest(path: Path, *, portable: bool = True) -> VoicePackManifest:
    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise VoicePackManifestError("Voice Pack manifest is unreadable") from exc
    return parse_manifest(payload, portable=portable)


def asset_specs(manifest: VoicePackManifest) -> tuple[AssetSpec, ...]:
    return manifest.gpt_checkpoint, manifest.sovits_checkpoint, manifest.reference_audio


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def validate_assets(
    manifest: VoicePackManifest,
    *,
    package_root: Path | None = None,
    bindings: Mapping[str, str | Path] | None = None,
    verify_digest: bool = True,
) -> dict[str, str]:
    if (package_root is None) == (bindings is None):
        raise VoicePackPackageError("exactly one asset source is required")
    root = Path(package_root).resolve() if package_root is not None else None
    resolved: dict[str, str] = {}
    for spec in asset_specs(manifest):
        if root is not None:
            candidate = root.joinpath(*PurePosixPath(spec.path).parts)
            try:
                candidate_resolved = candidate.resolve(strict=True)
                candidate_resolved.relative_to(root)
            except (OSError, ValueError) as exc:
                raise VoicePackPackageError("Voice Pack asset is missing or escapes the package") from exc
            cursor = candidate
            while cursor != root:
                if cursor.is_symlink():
                    raise VoicePackPackageError("symbolic links are not allowed in Voice Packs")
                cursor = cursor.parent
        else:
            raw = bindings.get(spec.path) if bindings is not None else None
            if raw is None:
                raise VoicePackPackageError("Voice Pack local asset binding is missing")
            candidate = Path(raw)
            if not candidate.is_absolute():
                raise VoicePackPackageError("local asset bindings must be absolute local state")
            if candidate.is_symlink():
                raise VoicePackPackageError("symbolic links are not allowed in Voice Packs")
            try:
                candidate_resolved = candidate.resolve(strict=True)
            except OSError as exc:
                raise VoicePackPackageError("Voice Pack asset is missing") from exc
        if not candidate_resolved.is_file():
            raise VoicePackPackageError("Voice Pack asset is missing")
        if verify_digest and spec.integrity.mode == "sha256":
            try:
                if candidate_resolved.stat().st_size != spec.integrity.size_bytes:
                    raise VoicePackPackageError("Voice Pack asset size mismatch")
                if _sha256(candidate_resolved) != spec.integrity.sha256:
                    raise VoicePackPackageError("Voice Pack asset digest mismatch")
            except OSError as exc:
                raise VoicePackPackageError("Voice Pack asset could not be validated") from exc
        resolved[spec.path] = str(candidate_resolved)
    return resolved


def validate_package_tree(root: Path) -> None:
    root = Path(root)
    if not root.is_dir() or root.is_symlink():
        raise VoicePackPackageError("Voice Pack package must be a real directory")
    for path in root.rglob("*"):
        if path.is_symlink():
            raise VoicePackPackageError("symbolic links are not allowed in Voice Packs")
        if path.is_file() and path.suffix.lower() in FORBIDDEN_PACKAGE_SUFFIXES:
            raise VoicePackPackageError("Voice Packs cannot contain executable or installer files")
