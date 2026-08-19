"""Build the deterministic, asset-free Voice Pack Registry module package."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import tempfile
import zipfile
from pathlib import Path
from typing import Iterable


FEATURE_ROOT = Path(__file__).resolve().parent
PACKAGE_SOURCE = FEATURE_ROOT / "package_source"
VOICE_PACK_SOURCE = FEATURE_ROOT.parent / "voice" / "voice_packs"
OFFICIAL_RELEASE_VERSION = "1.0.0"
OFFICIAL_RELEASE_TAG = "modules-2026.08.02"
OFFICIAL_ASSET_NAME = "voice_pack_registry-1.0.0.zip"
FIXED_ZIP_DATETIME = (2026, 1, 1, 0, 0, 0)
COPIED_BACKEND_FILES = (
    "errors.py",
    "manifest.py",
    "registry.py",
    "router.py",
    "security.py",
    "service.py",
)
PACKAGE_SOURCE_BACKEND_FILES = (
    "__init__.py",
    "contracts.py",
    "module.py",
)
FORBIDDEN_PACKAGE_SUFFIXES = {
    ".bat",
    ".cmd",
    ".com",
    ".exe",
    ".msi",
    ".ps1",
    ".psm1",
    ".sh",
    ".vbs",
}
FORBIDDEN_NAMES = {
    ".env",
    "install.py",
    "installer.py",
    "post_install.py",
    "pre_install.py",
}
SEMVER_PATTERN = re.compile(
    r"^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)"
    r"(?:-[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?"
    r"(?:\+[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?$"
)


def _write_utf8_lf(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(content)


def _read_text(source: Path) -> str:
    return source.read_text(encoding="utf-8")


def _copy_text(source: Path, destination: Path) -> None:
    _write_utf8_lf(destination, _read_text(source))


def _packaged_backend_source(name: str) -> str:
    content = _read_text(VOICE_PACK_SOURCE / name)
    if name == "service.py":
        old_errors = "from ..errors import VoiceError"
        old_models = (
            "from ..models import ProviderCapabilities, ProviderHealth, VoicePackRef"
        )
        if content.count(old_errors) != 1 or content.count(old_models) != 1:
            raise RuntimeError("PK-210 Voice Pack source imports changed; review package adapter")
        content = content.replace(
            old_errors,
            "from .contracts import VoiceError",
        ).replace(
            old_models,
            "from .contracts import ProviderCapabilities, ProviderHealth, VoicePackRef",
        )
    return content


def _validate_version(version: str) -> None:
    if not isinstance(version, str) or not SEMVER_PATTERN.fullmatch(version):
        raise ValueError("version must be semantic versioning")


def _validate_materialized_tree(root: Path) -> None:
    allowed_top_level = {"backend", "dashboard", "schemas", "manifest.json"}
    for child in root.iterdir():
        if child.name not in allowed_top_level:
            raise RuntimeError(f"unexpected package root entry: {child.name}")
    for path in root.rglob("*"):
        if path.is_symlink():
            raise RuntimeError("package source cannot contain links")
        if not path.is_file():
            continue
        lowered = path.name.lower()
        if lowered in FORBIDDEN_NAMES or path.suffix.lower() in FORBIDDEN_PACKAGE_SUFFIXES:
            raise RuntimeError(f"forbidden executable or installer content: {path.name}")
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    if manifest["id"] != "voice_pack_registry":
        raise RuntimeError("package manifest identity changed")
    if manifest["entrypoint"] != "backend.register":
        raise RuntimeError("package manifest entrypoint changed")
    if manifest["dependencies"] != ["voice"]:
        raise RuntimeError("Voice Pack Registry must depend only on the public voice module")


def _materialize_directory(destination: Path, version: str) -> Path:
    _validate_version(version)
    if destination.exists():
        raise FileExistsError(f"package destination already exists: {destination}")
    (destination / "backend").mkdir(parents=True)
    (destination / "dashboard").mkdir(parents=True)
    (destination / "schemas").mkdir(parents=True)

    manifest = json.loads(
        (PACKAGE_SOURCE / "manifest.json").read_text(encoding="utf-8")
    )
    manifest["version"] = version
    _write_utf8_lf(
        destination / "manifest.json",
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
    )
    for name in PACKAGE_SOURCE_BACKEND_FILES:
        _copy_text(
            PACKAGE_SOURCE / "backend" / name,
            destination / "backend" / name,
        )
    for name in COPIED_BACKEND_FILES:
        _write_utf8_lf(
            destination / "backend" / name,
            _packaged_backend_source(name),
        )
    _copy_text(
        PACKAGE_SOURCE / "dashboard" / "index.js",
        destination / "dashboard" / "index.js",
    )
    _copy_text(
        VOICE_PACK_SOURCE / "voice-pack.schema.json",
        destination / "schemas" / "voice-pack.schema.json",
    )
    _validate_materialized_tree(destination)
    return destination


def _files(root: Path) -> Iterable[Path]:
    return sorted(
        (path for path in root.rglob("*") if path.is_file()),
        key=lambda path: path.relative_to(root).as_posix(),
    )


def _write_zip(source: Path, destination: Path) -> None:
    if destination.exists():
        raise FileExistsError(f"package destination already exists: {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(destination, "w", compression=zipfile.ZIP_STORED) as archive:
        for path in _files(source):
            relative = path.relative_to(source).as_posix()
            info = zipfile.ZipInfo(relative, date_time=FIXED_ZIP_DATETIME)
            info.compress_type = zipfile.ZIP_STORED
            info.create_system = 3
            info.create_version = 20
            info.extract_version = 20
            info.internal_attr = 0
            info.external_attr = 0o100644 << 16
            info.extra = b""
            info.comment = b""
            archive.writestr(info, path.read_bytes())


def build_voice_pack_registry_package(
    destination: Path,
    version: str = OFFICIAL_RELEASE_VERSION,
) -> Path:
    """Build a new review directory or byte-for-byte deterministic ZIP."""
    destination = Path(destination)
    if destination.suffix.lower() == ".zip":
        with tempfile.TemporaryDirectory(prefix="kei-voice-pack-registry-") as temp:
            source = _materialize_directory(
                Path(temp) / "voice_pack_registry",
                version,
            )
            _write_zip(source, destination)
        return destination
    return _materialize_directory(destination, version)


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build the installable Voice Pack Registry package"
    )
    parser.add_argument("output", type=Path, help="New output directory or .zip path")
    parser.add_argument("--version", default=OFFICIAL_RELEASE_VERSION)
    args = parser.parse_args()
    result = build_voice_pack_registry_package(args.output, args.version)
    print(result)
    if result.is_file():
        print(file_sha256(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
