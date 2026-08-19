"""Build a reviewable directory or deterministic conversation ZIP package."""

from __future__ import annotations

import argparse
import hashlib
import json
import tempfile
import zipfile
from pathlib import Path
from typing import Iterable


FEATURE_ROOT = Path(__file__).resolve().parent
SERVER_ROOT = FEATURE_ROOT.parents[1]
PACKAGE_SOURCE = FEATURE_ROOT / "package_source"
OFFICIAL_RELEASE_VERSION = "1.0.2"
OFFICIAL_RELEASE_TAG = "modules-2026.08.02"
OFFICIAL_ASSET_NAME = "conversation-1.0.2.zip"
FIXED_ZIP_DATETIME = (2026, 1, 1, 0, 0, 0)
BACKEND_FILES = (
    "__init__.py",
    "client.py",
    "composition.py",
    "context.py",
    "locks.py",
    "models.py",
    "module.py",
    "provider/__init__.py",
    "provider/contracts.py",
    "repository.py",
    "router.py",
    "runtime.py",
    "service.py",
)
PACKAGE_SOURCE_FILES = (
    "config.schema.json",
    "dashboard/index.js",
)


def _write_utf8_lf(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(content)


def _copy_text(source: Path, destination: Path) -> None:
    _write_utf8_lf(destination, source.read_text(encoding="utf-8"))


def _materialize_directory(destination: Path, version: str) -> Path:
    if destination.exists():
        raise FileExistsError(f"package destination already exists: {destination}")
    destination.mkdir(parents=True)
    manifest = json.loads(
        (PACKAGE_SOURCE / "manifest.json").read_text(encoding="utf-8")
    )
    manifest["version"] = version
    _write_utf8_lf(
        destination / "manifest.json",
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
    )
    for name in BACKEND_FILES:
        _copy_text(FEATURE_ROOT / name, destination / "backend" / name)
    _copy_text(
        SERVER_ROOT / "prompts" / "kei_system.txt",
        destination / "backend" / "kei_system.txt",
    )
    for name in PACKAGE_SOURCE_FILES:
        _copy_text(PACKAGE_SOURCE / name, destination / name)
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


def build_conversation_package(
    destination: Path,
    version: str = OFFICIAL_RELEASE_VERSION,
) -> Path:
    destination = Path(destination)
    if destination.suffix.casefold() == ".zip":
        with tempfile.TemporaryDirectory(
            prefix="kei-conversation-package-"
        ) as temp_dir:
            source = _materialize_directory(
                Path(temp_dir) / "conversation",
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
        description="Build the local conversation installable package"
    )
    parser.add_argument("output", type=Path, help="New output directory or .zip path")
    parser.add_argument("--version", default=OFFICIAL_RELEASE_VERSION)
    args = parser.parse_args()
    result = build_conversation_package(args.output, args.version)
    print(result)
    if result.is_file():
        print(file_sha256(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
