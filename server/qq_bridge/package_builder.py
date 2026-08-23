"""Build a reviewable, deterministic QQ bridge sidecar module package."""

from __future__ import annotations

import argparse
import hashlib
import json
import tempfile
import zipfile
from pathlib import Path
from typing import Iterable


BRIDGE_ROOT = Path(__file__).resolve().parent
PACKAGE_SOURCE = BRIDGE_ROOT / "package_source"
OFFICIAL_RELEASE_VERSION = "0.1.26"
OFFICIAL_RELEASE_TAG = "modules-2026.08.20"
OFFICIAL_ASSET_NAME = "qq_bridge-0.1.26.zip"
FIXED_ZIP_DATETIME = (2026, 1, 1, 0, 0, 0)
SIDECAR_SOURCE_FILES = (
    "bridge_core.mjs",
    "business_menu.mjs",
    "daily_briefing_scheduler.mjs",
    "focus_encouragement_scheduler.mjs",
    "gateway_client.mjs",
    "index.mjs",
    "life_support_scheduler.mjs",
    "state_store.mjs",
    "shutdown_control.mjs",
    "voice_reply.mjs",
)


def _is_within(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def _assert_tracked_source(path: Path) -> None:
    if path.is_symlink() or not path.is_file():
        raise ValueError(f"package source is missing or unsafe: {path.name}")


def _write_utf8_lf(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(content.replace("\r\n", "\n").replace("\r", "\n"))


def _copy_text(source: Path, destination: Path) -> None:
    _assert_tracked_source(source)
    _write_utf8_lf(destination, source.read_text(encoding="utf-8"))


def _copy_versioned_node_metadata(source: Path, destination: Path, version: str) -> None:
    _assert_tracked_source(source)
    payload = json.loads(source.read_text(encoding="utf-8"))
    payload["version"] = version
    if source.name == "package-lock.json":
        packages = payload.get("packages")
        if not isinstance(packages, dict) or not isinstance(packages.get(""), dict):
            raise ValueError("package-lock.json is missing its root package metadata")
        packages[""]["version"] = version
    _write_utf8_lf(
        destination,
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
    )


def _assert_output_outside_sources(destination: Path) -> None:
    resolved = destination.resolve()
    if _is_within(resolved, BRIDGE_ROOT):
        raise ValueError("package output must be outside the QQ bridge source root")


def _materialize_directory(destination: Path, version: str) -> Path:
    _assert_output_outside_sources(destination)
    if destination.exists():
        raise FileExistsError(f"package destination already exists: {destination}")
    destination.mkdir(parents=True)

    manifest_source = PACKAGE_SOURCE / "manifest.json"
    _assert_tracked_source(manifest_source)
    manifest = json.loads(manifest_source.read_text(encoding="utf-8"))
    manifest["version"] = version
    _write_utf8_lf(
        destination / "manifest.json",
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
    )
    _copy_text(PACKAGE_SOURCE / "config.schema.json", destination / "config.schema.json")
    _copy_text(PACKAGE_SOURCE / "README.md", destination / "README.md")
    _copy_text(
        PACKAGE_SOURCE / "dashboard" / "index.js",
        destination / "dashboard" / "index.js",
    )
    _copy_versioned_node_metadata(
        BRIDGE_ROOT / "package.json",
        destination / "sidecar" / "package.json",
        version,
    )
    _copy_versioned_node_metadata(
        BRIDGE_ROOT / "package-lock.json",
        destination / "sidecar" / "package-lock.json",
        version,
    )
    for name in SIDECAR_SOURCE_FILES:
        _copy_text(BRIDGE_ROOT / "src" / name, destination / "sidecar" / "src" / name)
    return destination


def _files(root: Path) -> Iterable[Path]:
    return sorted(
        (path for path in root.rglob("*") if path.is_file()),
        key=lambda path: path.relative_to(root).as_posix(),
    )


def _write_zip(source: Path, destination: Path) -> None:
    _assert_output_outside_sources(destination)
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


def build_qq_bridge_package(
    destination: Path,
    version: str = OFFICIAL_RELEASE_VERSION,
) -> Path:
    if version != OFFICIAL_RELEASE_VERSION:
        raise ValueError("QQ bridge package version must match its locked Node metadata")
    destination = Path(destination)
    _assert_output_outside_sources(destination)
    if destination.suffix.lower() == ".zip":
        with tempfile.TemporaryDirectory(prefix="kei-qq-bridge-package-") as temp_dir:
            source = _materialize_directory(Path(temp_dir) / "qq_bridge", version)
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
        description="Build the local QQ bridge installable sidecar package"
    )
    parser.add_argument("output", type=Path, help="New output directory or .zip path")
    parser.add_argument("--version", default=OFFICIAL_RELEASE_VERSION)
    args = parser.parse_args()
    result = build_qq_bridge_package(args.output, args.version)
    print(result)
    if result.is_file():
        print(file_sha256(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
