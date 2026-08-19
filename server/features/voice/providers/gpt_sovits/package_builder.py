"""Build the deterministic GPT-SoVITS Provider sidecar module package."""

from __future__ import annotations

import argparse
import hashlib
import json
import tempfile
import zipfile
from pathlib import Path
from typing import Iterable


FEATURE_ROOT = Path(__file__).resolve().parent
PACKAGE_SOURCE = FEATURE_ROOT / "package_source"
OFFICIAL_RELEASE_VERSION = "1.0.2"
OFFICIAL_RELEASE_TAG = "modules-2026.08.12"
OFFICIAL_ASSET_NAME = "gpt_sovits_engine_provider-1.0.2.zip"
FIXED_ZIP_DATETIME = (2026, 1, 1, 0, 0, 0)
PROVIDER_FILES = (
    "acquisition.py",
    "descriptor.py",
    "local_selection.py",
    "provider.py",
    "selection_router.py",
    "sidecar_adapter.py",
    "engine.json",
)


def _write_utf8_lf(path: Path, content: str) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(content)


def _copy_text(source: Path, destination: Path) -> None:
    _write_utf8_lf(destination, source.read_text(encoding="utf-8"))


def _copy_provider_source(name: str, destination: Path) -> None:
    content = (FEATURE_ROOT / name).read_text(encoding="utf-8")
    if name == "provider.py":
        content = content.replace(
            "from ...errors import VoiceError, failed, timed_out, unavailable",
            "from features.voice.errors import VoiceError, failed, timed_out, unavailable",
        ).replace(
            "from ...models import AudioResult, ProviderCapabilities, ProviderHealth, SynthesisRequest, VoicePackRef",
            "from features.voice.models import AudioResult, ProviderCapabilities, ProviderHealth, SynthesisRequest, VoicePackRef",
        )
    _write_utf8_lf(destination, content)


def _materialize_directory(destination: Path, version: str) -> Path:
    if destination.exists():
        raise FileExistsError("package destination already exists")
    (destination / "dashboard").mkdir(parents=True)
    (destination / "provider").mkdir()

    manifest = json.loads((PACKAGE_SOURCE / "manifest.json").read_text(encoding="utf-8"))
    manifest["version"] = version
    _write_utf8_lf(
        destination / "manifest.json",
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
    )
    _copy_text(PACKAGE_SOURCE / "config.schema.json", destination / "config.schema.json")
    _copy_text(PACKAGE_SOURCE / "dashboard" / "index.js", destination / "dashboard" / "index.js")
    _copy_text(PACKAGE_SOURCE / "provider" / "__init__.py", destination / "provider" / "__init__.py")
    for name in PROVIDER_FILES:
        _copy_provider_source(name, destination / "provider" / name)
    return destination


def _files(root: Path) -> Iterable[Path]:
    return sorted((path for path in root.rglob("*") if path.is_file()), key=lambda path: path.as_posix())


def _write_zip(source: Path, destination: Path) -> None:
    if destination.exists():
        raise FileExistsError("package destination already exists")
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


def build_gpt_sovits_provider_package(
    destination: Path,
    version: str = OFFICIAL_RELEASE_VERSION,
) -> Path:
    destination = Path(destination)
    if destination.suffix.lower() == ".zip":
        with tempfile.TemporaryDirectory(prefix="kei-gpt-sovits-provider-package-") as temp_dir:
            source = _materialize_directory(Path(temp_dir) / "gpt_sovits_engine_provider", version)
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
    parser = argparse.ArgumentParser(description="Build the GPT-SoVITS Provider sidecar module package")
    parser.add_argument("output", type=Path, help="New output directory or .zip path")
    parser.add_argument("--version", default=OFFICIAL_RELEASE_VERSION)
    args = parser.parse_args()
    result = build_gpt_sovits_provider_package(args.output, args.version)
    print(result)
    if result.is_file():
        print(file_sha256(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
