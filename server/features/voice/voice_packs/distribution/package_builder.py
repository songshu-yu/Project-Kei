"""Build the deterministic, asset-free Voice Pack distribution module."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import stat
import tempfile
import zipfile
from pathlib import Path
from typing import Iterable


FEATURE_ROOT = Path(__file__).resolve().parent
PACKAGE_SOURCE = FEATURE_ROOT / "package_source"
OFFICIAL_RELEASE_VERSION = "1.0.1"
OFFICIAL_RELEASE_TAG = "modules-2026.08.02"
OFFICIAL_ASSET_NAME = "voice_pack_distribution-1.0.1.zip"
FIXED_ZIP_DATETIME = (2026, 1, 1, 0, 0, 0)
SEMVER_PATTERN = re.compile(
    r"^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)"
    r"(?:-[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?"
    r"(?:\+[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?$"
)
FORBIDDEN_SUFFIXES = {
    ".bat",
    ".cmd",
    ".com",
    ".dll",
    ".exe",
    ".msi",
    ".ps1",
    ".sh",
    ".wav",
    ".ckpt",
    ".pth",
    ".pyc",
}
EXPECTED_PACKAGE_FILES = {
    "backend/__init__.py",
    "backend/archive.py",
    "backend/catalog.py",
    "backend/downloader.py",
    "backend/errors.py",
    "backend/module.py",
    "backend/service.py",
    "catalog/catalog.schema.json",
    "dashboard/index.js",
    "manifest.json",
}
_EXPECTED_BYTECODE_CACHE = re.compile(
    r"^(?P<stem>[A-Za-z_][A-Za-z0-9_]*)"
    r"\.cpython-[0-9]{2,3}(?:\.opt-[12])?\.pyc$"
)


def _absolute(path: Path) -> Path:
    return Path(os.path.abspath(str(path)))


def _is_within(path: Path, root: Path) -> bool:
    try:
        _absolute(path).relative_to(_absolute(root))
        return True
    except ValueError:
        return False


def _metadata(path: Path) -> os.stat_result:
    try:
        return os.lstat(path)
    except OSError as exc:
        raise RuntimeError("package source metadata is unavailable") from exc


def _is_reparse(metadata: os.stat_result) -> bool:
    return bool(getattr(metadata, "st_file_attributes", 0) & 0x400)


def _assert_real_directory(path: Path) -> None:
    metadata = _metadata(path)
    if (
        stat.S_ISLNK(metadata.st_mode)
        or _is_reparse(metadata)
        or not stat.S_ISDIR(metadata.st_mode)
    ):
        raise RuntimeError("package source contains a linked or invalid directory")


def _is_expected_bytecode_cache(path: Path) -> bool:
    """Ignore only caches derived from an explicitly allowed Python source."""

    relative = path.relative_to(PACKAGE_SOURCE)
    if len(relative.parts) < 3 or relative.parts[-2] != "__pycache__":
        return False
    match = _EXPECTED_BYTECODE_CACHE.fullmatch(relative.name)
    if match is None:
        return False
    source_relative = "/".join(
        (*relative.parts[:-2], match.group("stem") + ".py")
    )
    return source_relative in EXPECTED_PACKAGE_FILES


def _source_files() -> list[Path]:
    _assert_real_directory(PACKAGE_SOURCE)
    files: list[Path] = []

    def walk(directory: Path) -> None:
        _assert_real_directory(directory)
        try:
            children = sorted(directory.iterdir(), key=lambda item: item.name.casefold())
        except OSError as exc:
            raise RuntimeError("package source directory is unreadable") from exc
        for child in children:
            metadata = _metadata(child)
            if stat.S_ISLNK(metadata.st_mode) or _is_reparse(metadata):
                raise RuntimeError("package source cannot contain links or reparse points")
            if stat.S_ISDIR(metadata.st_mode):
                walk(child)
                continue
            if (
                not stat.S_ISREG(metadata.st_mode)
                or getattr(metadata, "st_nlink", 1) != 1
            ):
                raise RuntimeError("package source files must be unique regular files")
            if _is_expected_bytecode_cache(child):
                continue
            if child.suffix.lower() in FORBIDDEN_SUFFIXES:
                raise RuntimeError("package source contains forbidden assets or scripts")
            files.append(child)

    walk(PACKAGE_SOURCE)
    ordered = sorted(
        files,
        key=lambda item: item.relative_to(PACKAGE_SOURCE).as_posix(),
    )
    actual = {item.relative_to(PACKAGE_SOURCE).as_posix() for item in ordered}
    if actual != EXPECTED_PACKAGE_FILES:
        raise RuntimeError("package source file allowlist changed")
    return ordered


def _assert_new_output(path: Path) -> None:
    path = _absolute(path)
    if _is_within(path, PACKAGE_SOURCE):
        raise ValueError("package output must be outside package_source")
    if path.exists():
        raise FileExistsError(f"package destination already exists: {path}")
    cursor = path.parent
    while not cursor.exists():
        parent = cursor.parent
        if parent == cursor:
            raise RuntimeError("package output parent is unavailable")
        cursor = parent
    while True:
        _assert_real_directory(cursor)
        parent = cursor.parent
        if parent == cursor:
            break
        cursor = parent


def _write_utf8_lf(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(content)


def _materialize_directory(destination: Path, version: str) -> Path:
    if not SEMVER_PATTERN.fullmatch(version):
        raise ValueError("version must use semantic versioning")
    _assert_new_output(destination)
    source_files = _source_files()
    for source in source_files:
        relative = source.relative_to(PACKAGE_SOURCE)
        content = source.read_text(encoding="utf-8")
        if relative.as_posix() == "manifest.json":
            manifest = json.loads(content)
            manifest["version"] = version
            content = json.dumps(manifest, ensure_ascii=False, indent=2) + "\n"
        _write_utf8_lf(destination / relative, content)
    manifest = json.loads((destination / "manifest.json").read_text(encoding="utf-8"))
    if (
        manifest.get("id") != "voice_pack_distribution"
        or manifest.get("entrypoint") != "backend.register"
        or manifest.get("dependencies") != ["voice_pack_registry"]
    ):
        raise RuntimeError("Voice Pack distribution package identity changed")
    return destination


def _files(root: Path) -> Iterable[Path]:
    return sorted(
        (path for path in root.rglob("*") if path.is_file()),
        key=lambda item: item.relative_to(root).as_posix(),
    )


def _write_zip(source: Path, destination: Path) -> None:
    _assert_new_output(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    try:
        with zipfile.ZipFile(
            destination,
            "x",
            compression=zipfile.ZIP_STORED,
        ) as archive:
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
    except Exception:
        destination.unlink(missing_ok=True)
        raise


def build_voice_pack_distribution_package(
    destination: Path,
    version: str = OFFICIAL_RELEASE_VERSION,
) -> Path:
    destination = _absolute(Path(destination))
    if destination.suffix.lower() == ".zip":
        _assert_new_output(destination)
        with tempfile.TemporaryDirectory(
            prefix="kei-voice-pack-distribution-"
        ) as temp:
            source = _materialize_directory(
                Path(temp) / "voice_pack_distribution",
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
        description="Build the installable Voice Pack distribution package"
    )
    parser.add_argument("output", type=Path, help="New output directory or .zip path")
    parser.add_argument("--version", default=OFFICIAL_RELEASE_VERSION)
    args = parser.parse_args()
    result = build_voice_pack_distribution_package(args.output, args.version)
    print(result)
    if result.is_file():
        print(file_sha256(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
