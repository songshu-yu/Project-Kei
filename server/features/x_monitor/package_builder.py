"""Build a reviewable x_monitor directory or deterministic local ZIP."""

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
OFFICIAL_RELEASE_VERSION = "1.1.0"
OFFICIAL_RELEASE_TAG = "modules-2026.08.02"
OFFICIAL_ASSET_NAME = "x_monitor-1.1.0.zip"
FIXED_ZIP_DATETIME = (2026, 1, 1, 0, 0, 0)
BACKEND_SOURCES = {
    "__init__.py": FEATURE_ROOT / "__init__.py",
    "fxembed.py": FEATURE_ROOT / "fxembed.py",
    "models.py": FEATURE_ROOT / "models.py",
    "module.py": FEATURE_ROOT / "module.py",
    "provider.py": FEATURE_ROOT / "provider.py",
    "router.py": FEATURE_ROOT / "router.py",
    "service.py": FEATURE_ROOT / "service.py",
    "twitter.py": SERVER_ROOT / "intel" / "collectors" / "twitter.py",
    "x_daily_cache.py": SERVER_ROOT / "services" / "x_daily_cache.py",
    "x_daily_posts.py": SERVER_ROOT / "services" / "x_daily_posts.py",
    "x_profile_cache.py": SERVER_ROOT / "services" / "x_profile_cache.py",
}
_IMPORT_REWRITES = {
    "from intel.collectors.twitter import ": "from .twitter import ",
    "from intel.intel_config import NITTER_INSTANCES": (
        "from .provider import DEFAULT_NITTER_INSTANCES as NITTER_INSTANCES"
    ),
    "from services.x_daily_cache import ": "from .x_daily_cache import ",
    "from services.x_daily_posts import ": "from .x_daily_posts import ",
    "from services.x_profile_cache import ": "from .x_profile_cache import ",
}


def _write_utf8_lf(path: Path, content: str) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(content)


def _package_backend_text(source: Path) -> str:
    content = source.read_text(encoding="utf-8")
    for old, new in _IMPORT_REWRITES.items():
        content = content.replace(old, new)
    return content


def _materialize_directory(destination: Path, version: str) -> Path:
    if destination.exists():
        raise FileExistsError(f"package destination already exists: {destination}")
    (destination / "backend").mkdir(parents=True)
    (destination / "dashboard").mkdir(parents=True)
    manifest = json.loads(
        (PACKAGE_SOURCE / "manifest.json").read_text(encoding="utf-8")
    )
    manifest["version"] = version
    _write_utf8_lf(
        destination / "manifest.json",
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
    )
    for name, source in sorted(BACKEND_SOURCES.items()):
        _write_utf8_lf(destination / "backend" / name, _package_backend_text(source))
    _write_utf8_lf(
        destination / "dashboard" / "index.js",
        (PACKAGE_SOURCE / "dashboard" / "index.js").read_text(encoding="utf-8"),
    )
    return destination


def _files(root: Path) -> Iterable[Path]:
    return sorted(
        (path for path in root.rglob("*") if path.is_file()),
        key=lambda path: path.as_posix(),
    )


def _write_zip(source: Path, destination: Path) -> None:
    if destination.exists():
        raise FileExistsError(f"package destination already exists: {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(destination, "w", compression=zipfile.ZIP_STORED) as archive:
        for path in _files(source):
            info = zipfile.ZipInfo(
                path.relative_to(source).as_posix(),
                date_time=FIXED_ZIP_DATETIME,
            )
            info.compress_type = zipfile.ZIP_STORED
            info.create_system = 3
            info.create_version = 20
            info.extract_version = 20
            info.internal_attr = 0
            info.external_attr = 0o100644 << 16
            info.extra = b""
            info.comment = b""
            archive.writestr(info, path.read_bytes())


def build_x_monitor_package(
    destination: Path,
    version: str = OFFICIAL_RELEASE_VERSION,
) -> Path:
    destination = Path(destination)
    if destination.suffix.lower() == ".zip":
        with tempfile.TemporaryDirectory(prefix="kei-x-monitor-package-") as temp_dir:
            source = _materialize_directory(Path(temp_dir) / "x_monitor", version)
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
        description="Build the local x_monitor installable package"
    )
    parser.add_argument("output", type=Path)
    parser.add_argument("--version", default=OFFICIAL_RELEASE_VERSION)
    args = parser.parse_args()
    result = build_x_monitor_package(args.output, args.version)
    print(result)
    if result.is_file():
        print(file_sha256(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
