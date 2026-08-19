"""Build a reviewable directory or deterministic Bilibili module ZIP."""

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
OFFICIAL_ASSET_NAME = "bilibili-1.0.2.zip"
FIXED_ZIP_DATETIME = (2026, 1, 1, 0, 0, 0)
BACKEND_SOURCES = {
    "__init__.py": PACKAGE_SOURCE / "backend" / "__init__.py",
    "client.py": FEATURE_ROOT / "client.py",
    "collector.py": SERVER_ROOT / "intel" / "collectors" / "bilibili.py",
    "credentials.py": FEATURE_ROOT / "credentials.py",
    "models.py": FEATURE_ROOT / "models.py",
    "profile_cache.py": SERVER_ROOT / "services" / "bilibili_profile_cache.py",
    "router.py": FEATURE_ROOT / "router.py",
    "service.py": FEATURE_ROOT / "service.py",
}
IMPORT_REWRITES = {
    "collector.py": (
        ("from features.bilibili.client import (", "from .client import ("),
        (
            "from features.bilibili.credentials import load_active_bilibili_cookies",
            "from .credentials import load_active_bilibili_cookies",
        ),
    ),
    "profile_cache.py": (
        ("from features.bilibili.client import normalize_uid", "from .client import normalize_uid"),
        (
            "from intel.collectors.bilibili import fetch_bilibili_profile",
            "from .collector import fetch_bilibili_profile",
        ),
    ),
    "service.py": (
        (
            "from features.bilibili.client import BilibiliClientError, BilibiliPublicClient, normalize_uid",
            "from .client import BilibiliClientError, BilibiliPublicClient, normalize_uid",
        ),
        ("from features.bilibili.credentials import (", "from .credentials import ("),
        ("from intel.collectors.bilibili import BilibiliCollector", "from .collector import BilibiliCollector"),
        ("from services.bilibili_profile_cache import (", "from .profile_cache import ("),
    ),
}


def _write_utf8_lf(path: Path, content: str) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(content)


def _source_text(name: str) -> str:
    text = BACKEND_SOURCES[name].read_text(encoding="utf-8")
    for old, new in IMPORT_REWRITES.get(name, ()):
        if old not in text:
            raise RuntimeError("expected Bilibili package import was not found: %s" % old)
        text = text.replace(old, new, 1)
    return text


def _materialize_directory(destination: Path, version: str) -> Path:
    if destination.exists():
        raise FileExistsError("package destination already exists: %s" % destination)
    (destination / "backend").mkdir(parents=True)
    (destination / "dashboard").mkdir(parents=True)
    manifest = json.loads((PACKAGE_SOURCE / "manifest.json").read_text(encoding="utf-8"))
    manifest["version"] = version
    _write_utf8_lf(
        destination / "manifest.json",
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
    )
    for name in sorted(BACKEND_SOURCES):
        _write_utf8_lf(destination / "backend" / name, _source_text(name))
    _write_utf8_lf(
        destination / "dashboard" / "index.js",
        (PACKAGE_SOURCE / "dashboard" / "index.js").read_text(encoding="utf-8"),
    )
    return destination


def _files(root: Path) -> Iterable[Path]:
    return sorted(
        (path for path in root.rglob("*") if path.is_file()),
        key=lambda path: path.relative_to(root).as_posix(),
    )


def _write_zip(source: Path, destination: Path) -> None:
    if destination.exists():
        raise FileExistsError("package destination already exists: %s" % destination)
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


def build_bilibili_package(
    destination: Path,
    version: str = OFFICIAL_RELEASE_VERSION,
) -> Path:
    destination = Path(destination)
    if destination.suffix.lower() == ".zip":
        with tempfile.TemporaryDirectory(prefix="kei-bilibili-package-") as temp_dir:
            source = _materialize_directory(Path(temp_dir) / "bilibili", version)
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
    parser = argparse.ArgumentParser(description="Build the local Bilibili installable package")
    parser.add_argument("output", type=Path, help="New output directory or .zip path")
    parser.add_argument("--version", default=OFFICIAL_RELEASE_VERSION)
    args = parser.parse_args()
    result = build_bilibili_package(args.output, args.version)
    print(result)
    if result.is_file():
        print(file_sha256(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
