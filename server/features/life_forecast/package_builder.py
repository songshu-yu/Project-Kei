"""Build a deterministic life_forecast installable package."""

from __future__ import annotations

import argparse
import hashlib
import json
import tempfile
import zipfile
from pathlib import Path


FEATURE_ROOT = Path(__file__).resolve().parent
PACKAGE_SOURCE = FEATURE_ROOT / "package_source"
OFFICIAL_RELEASE_VERSION = "1.0.0"
OFFICIAL_RELEASE_TAG = "modules-2026.08.19"
OFFICIAL_ASSET_NAME = "life_forecast-1.0.0.zip"
FIXED_ZIP_DATETIME = (2026, 1, 1, 0, 0, 0)
BACKEND_FILES = (
    "__init__.py",
    "contracts.py",
    "models.py",
    "module.py",
    "providers.py",
    "repository.py",
    "router.py",
    "service.py",
)


def _write_text(path: Path, content: str) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(content)


def _materialize(destination: Path, version: str) -> Path:
    if destination.exists():
        raise FileExistsError(f"package destination already exists: {destination}")
    (destination / "backend").mkdir(parents=True)
    (destination / "dashboard").mkdir(parents=True)
    manifest = json.loads((PACKAGE_SOURCE / "manifest.json").read_text(encoding="utf-8"))
    manifest["version"] = version
    _write_text(destination / "manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
    for name in BACKEND_FILES:
        content = (
            '"""Installable backend entrypoint."""\n\n'
            "from .module import register, unregister\n\n"
            '__all__ = ["register", "unregister"]\n'
            if name == "__init__.py"
            else (FEATURE_ROOT / name).read_text(encoding="utf-8")
        )
        _write_text(destination / "backend" / name, content)
    _write_text(
        destination / "dashboard" / "index.js",
        (PACKAGE_SOURCE / "dashboard" / "index.js").read_text(encoding="utf-8"),
    )
    return destination


def _write_zip(source: Path, destination: Path) -> None:
    if destination.exists():
        raise FileExistsError(f"package destination already exists: {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    files = sorted((item for item in source.rglob("*") if item.is_file()), key=lambda item: item.as_posix())
    with zipfile.ZipFile(destination, "w", compression=zipfile.ZIP_STORED) as archive:
        for path in files:
            info = zipfile.ZipInfo(path.relative_to(source).as_posix(), date_time=FIXED_ZIP_DATETIME)
            info.compress_type = zipfile.ZIP_STORED
            info.create_system = 3
            info.external_attr = 0o100644 << 16
            archive.writestr(info, path.read_bytes())


def build_life_forecast_package(destination: Path, version: str = OFFICIAL_RELEASE_VERSION) -> Path:
    destination = Path(destination)
    if destination.suffix.lower() == ".zip":
        with tempfile.TemporaryDirectory(prefix="kei-life-forecast-package-") as temp_dir:
            source = _materialize(Path(temp_dir) / "life_forecast", version)
            _write_zip(source, destination)
        return destination
    return _materialize(destination, version)


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description="Build the life_forecast installable package")
    parser.add_argument("output", type=Path)
    parser.add_argument("--version", default=OFFICIAL_RELEASE_VERSION)
    args = parser.parse_args()
    result = build_life_forecast_package(args.output, args.version)
    print(result)
    if result.is_file():
        print(file_sha256(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
