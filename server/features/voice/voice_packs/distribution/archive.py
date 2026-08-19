"""Outer release ZIP audit and deterministic safe extraction."""

from __future__ import annotations

import os
import shutil
import stat
import zipfile
from pathlib import Path, PurePosixPath

from ..catalog import CatalogEntry
from ..manifest import FORBIDDEN_PACKAGE_SUFFIXES, safe_relative_path
from .errors import DistributionError


_FIXED_FILES = {"voice-pack.json", "README.md", "LICENSE.txt", "NOTICE.txt"}
_MODEL_SUFFIXES = {".ckpt", ".pth"}
_REFERENCE_SUFFIXES = {".wav"}


def _member_path(name: str, root: str) -> PurePosixPath:
    if not name or "\\" in name:
        raise DistributionError("Voice Pack ZIP path is invalid", code="voice_pack_archive_unsafe")
    normalized = name.rstrip("/")
    try:
        safe_relative_path(normalized, "release archive member")
    except Exception as exc:
        raise DistributionError(
            "Voice Pack ZIP path is invalid", code="voice_pack_archive_unsafe"
        ) from exc
    path = PurePosixPath(normalized)
    if not path.parts or path.parts[0] != root:
        raise DistributionError(
            "Voice Pack ZIP has an unexpected root", code="voice_pack_archive_unsafe"
        )
    return path


def _allowed_payload(path: PurePosixPath, *, is_dir: bool) -> bool:
    relative = PurePosixPath(*path.parts[1:])
    if not relative.parts:
        return is_dir
    if is_dir:
        return relative.as_posix() in {"models", "references"}
    if relative.as_posix() in _FIXED_FILES:
        return True
    if len(relative.parts) != 2:
        return False
    if relative.parts[0] == "models":
        return relative.suffix.lower() in _MODEL_SUFFIXES
    if relative.parts[0] == "references":
        return relative.suffix.lower() in _REFERENCE_SUFFIXES
    return False


def audit_archive(archive: Path, entry: CatalogEntry) -> list[zipfile.ZipInfo]:
    try:
        package = zipfile.ZipFile(archive)
    except (OSError, zipfile.BadZipFile) as exc:
        raise DistributionError(
            "Voice Pack ZIP is invalid", code="voice_pack_archive_invalid"
        ) from exc
    with package:
        infos = package.infolist()
        if not infos or len(infos) > entry.max_files:
            raise DistributionError(
                "Voice Pack ZIP file count exceeds catalog limits",
                code="voice_pack_archive_limit",
            )
        seen: set[str] = set()
        files: set[str] = set()
        directories: set[str] = set()
        total = 0
        for info in infos:
            path = _member_path(info.filename, entry.archive_root)
            key = path.as_posix().casefold()
            if key in seen:
                raise DistributionError(
                    "Voice Pack ZIP contains duplicate paths",
                    code="voice_pack_archive_unsafe",
                )
            seen.add(key)
            mode = info.external_attr >> 16
            if stat.S_ISLNK(mode) or (mode and not (stat.S_ISREG(mode) or stat.S_ISDIR(mode))):
                raise DistributionError(
                    "Voice Pack ZIP links are forbidden",
                    code="voice_pack_archive_unsafe",
                )
            if not _allowed_payload(path, is_dir=info.is_dir()):
                raise DistributionError(
                    "Voice Pack ZIP contains an undeclared file",
                    code="voice_pack_archive_unsafe",
                )
            if path.suffix.lower() in FORBIDDEN_PACKAGE_SUFFIXES:
                raise DistributionError(
                    "Voice Pack ZIP contains executable content",
                    code="voice_pack_archive_unsafe",
                )
            if info.is_dir():
                directories.add(key)
                continue
            files.add(key)
            parent = path.parent
            while parent.parts:
                if parent.as_posix().casefold() in files:
                    raise DistributionError(
                        "Voice Pack ZIP has conflicting paths",
                        code="voice_pack_archive_unsafe",
                    )
                parent = parent.parent
            if key in directories or info.file_size > entry.max_file_bytes:
                raise DistributionError(
                    "Voice Pack ZIP exceeds per-file limits",
                    code="voice_pack_archive_limit",
                )
            total += info.file_size
            if total > entry.max_uncompressed_bytes:
                raise DistributionError(
                    "Voice Pack ZIP exceeds expanded size limits",
                    code="voice_pack_archive_limit",
                )
            if info.file_size:
                compressed = max(1, info.compress_size)
                if info.file_size / compressed > entry.max_compression_ratio:
                    raise DistributionError(
                        "Voice Pack ZIP compression ratio is unsafe",
                        code="voice_pack_archive_limit",
                    )
        required = {
            f"{entry.archive_root}/voice-pack.json".casefold(),
            f"{entry.archive_root}/README.md".casefold(),
            f"{entry.archive_root}/LICENSE.txt".casefold(),
            f"{entry.archive_root}/NOTICE.txt".casefold(),
        }
        if not required.issubset(files):
            raise DistributionError(
                "Voice Pack ZIP is missing release metadata",
                code="voice_pack_archive_invalid",
            )
        return infos


def extract_archive(archive: Path, entry: CatalogEntry, destination: Path) -> Path:
    infos = audit_archive(archive, entry)
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=False)
    try:
        with zipfile.ZipFile(archive) as package:
            for info in infos:
                path = _member_path(info.filename, entry.archive_root)
                target = destination.joinpath(*path.parts)
                target.parent.mkdir(parents=True, exist_ok=True)
                if info.is_dir():
                    target.mkdir(parents=True, exist_ok=True)
                    continue
                written = 0
                with package.open(info) as source, target.open("xb") as output:
                    while True:
                        chunk = source.read(1024 * 1024)
                        if not chunk:
                            break
                        written += len(chunk)
                        if written > info.file_size:
                            raise DistributionError(
                                "Voice Pack ZIP entry changed while extracting",
                                code="voice_pack_archive_invalid",
                            )
                        output.write(chunk)
                if written != info.file_size:
                    raise DistributionError(
                        "Voice Pack ZIP entry size is invalid",
                        code="voice_pack_archive_invalid",
                    )
                if target.is_symlink() or not stat.S_ISREG(os.lstat(target).st_mode):
                    raise DistributionError(
                        "Voice Pack ZIP produced an unsafe file",
                        code="voice_pack_archive_unsafe",
                    )
        return destination / entry.archive_root
    except Exception:
        shutil.rmtree(destination, ignore_errors=True)
        raise
