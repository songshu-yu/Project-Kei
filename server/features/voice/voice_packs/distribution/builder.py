"""Deterministic Voice Pack release builder for explicitly authorized sources."""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import stat
import tempfile
import zipfile
from pathlib import Path
from typing import Any, Callable

from ..manifest import load_manifest, validate_assets, validate_package_tree
from .errors import DistributionError


_REQUIRED_PUBLIC = {"README.md", "LICENSE.txt", "NOTICE.txt"}
_SECRET = re.compile(
    r"(?i)(?:api[_-]?key|token|secret|cookie|authorization)\s*[:=]\s*[\"']?[A-Za-z0-9_./+-]{8,}"
)
_ABSOLUTE = re.compile(r"(?i)(?:[a-z]:[\\/]|\\\\[A-Za-z0-9_.-]+[\\/])")
_TRAINING_PARTS = {
    "logs",
    "log",
    "cache",
    "caches",
    "dataset",
    "datasets",
    "training",
    "train",
    "wandb",
    "__pycache__",
}
_REPARSE_POINT = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
_Lstat = Callable[[Path], os.stat_result]


def _hash_file(path: Path) -> tuple[int, str]:
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            size += len(chunk)
            digest.update(chunk)
    return size, digest.hexdigest()


def _scan_public_text(path: Path) -> None:
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise DistributionError(
            "release metadata must be UTF-8 text", code="voice_pack_build_rejected"
        ) from exc
    if _SECRET.search(text) or _ABSOLUTE.search(text):
        raise DistributionError(
            "release metadata contains private or machine-specific data",
            code="voice_pack_build_rejected",
        )


def _absolute(path: Path) -> Path:
    return Path(os.path.abspath(os.fspath(path)))


def _is_reparse(metadata: os.stat_result) -> bool:
    return bool(getattr(metadata, "st_file_attributes", 0) & _REPARSE_POINT)


def _lstat_required(
    path: Path,
    *,
    lstat: _Lstat,
    code: str,
) -> os.stat_result:
    try:
        return lstat(path)
    except OSError as exc:
        raise DistributionError("release path metadata is unavailable", code=code) from exc


def _assert_real_directory(
    path: Path,
    metadata: os.stat_result,
    *,
    code: str,
) -> None:
    if (
        stat.S_ISLNK(metadata.st_mode)
        or _is_reparse(metadata)
        or not stat.S_ISDIR(metadata.st_mode)
    ):
        raise DistributionError(
            "links and reparse points are forbidden in release paths",
            code=code,
        )


def _assert_new_output(path: Path, *, lstat: _Lstat) -> None:
    try:
        metadata = lstat(path)
    except FileNotFoundError:
        return
    except OSError as exc:
        raise DistributionError(
            "release output metadata is unavailable",
            code="voice_pack_build_output_exists",
        ) from exc
    if stat.S_ISLNK(metadata.st_mode) or _is_reparse(metadata):
        raise DistributionError(
            "release outputs cannot be links or reparse points",
            code="voice_pack_build_output_exists",
        )
    raise DistributionError(
        "release output must use unused names",
        code="voice_pack_build_output_exists",
    )


def _assert_safe_parent_chain(path: Path, *, lstat: _Lstat) -> None:
    chain: list[Path] = []
    cursor = _absolute(path)
    while True:
        chain.append(cursor)
        parent = cursor.parent
        if parent == cursor:
            break
        cursor = parent
    for component in reversed(chain):
        try:
            metadata = lstat(component)
        except FileNotFoundError:
            continue
        except OSError as exc:
            raise DistributionError(
                "release output parent metadata is unavailable",
                code="voice_pack_build_source_invalid",
            ) from exc
        _assert_real_directory(
            component, metadata, code="voice_pack_build_source_invalid"
        )


def _is_within(path: Path, root: Path) -> bool:
    try:
        common = os.path.commonpath((os.fspath(path), os.fspath(root)))
        return os.path.normcase(common) == os.path.normcase(os.fspath(root))
    except ValueError:
        return False


def _source_files(root: Path, *, lstat: _Lstat = os.lstat) -> list[Path]:
    root_metadata = _lstat_required(
        root, lstat=lstat, code="voice_pack_build_source_invalid"
    )
    _assert_real_directory(
        root, root_metadata, code="voice_pack_build_source_invalid"
    )
    files: list[Path] = []

    def walk(directory: Path) -> None:
        try:
            names = sorted(entry.name for entry in os.scandir(directory))
        except OSError as exc:
            raise DistributionError(
                "release source cannot be enumerated",
                code="voice_pack_build_source_invalid",
            ) from exc
        for name in names:
            path = directory / name
            relative = path.relative_to(root)
            if any(part.casefold() in _TRAINING_PARTS for part in relative.parts):
                raise DistributionError(
                    "training or cache artifacts are forbidden",
                    code="voice_pack_build_rejected",
                )
            metadata = _lstat_required(
                path, lstat=lstat, code="voice_pack_build_rejected"
            )
            if stat.S_ISLNK(metadata.st_mode) or _is_reparse(metadata):
                raise DistributionError(
                    "links and reparse points are forbidden in release sources",
                    code="voice_pack_build_rejected",
                )
            if stat.S_ISDIR(metadata.st_mode):
                walk(path)
            elif stat.S_ISREG(metadata.st_mode):
                if metadata.st_nlink != 1:
                    raise DistributionError(
                        "hard-linked files are forbidden in release sources",
                        code="voice_pack_build_rejected",
                    )
                files.append(path)
            else:
                raise DistributionError(
                    "release sources must contain only regular files and directories",
                    code="voice_pack_build_rejected",
                )

    walk(root)
    return files


def build_release(
    source_root: Path,
    output_zip: Path,
    *,
    version: str,
    confirmation: str,
    _lstat: _Lstat = os.lstat,
) -> dict[str, Any]:
    source_root = _absolute(Path(source_root))
    output_zip = _absolute(Path(output_zip))
    if output_zip.suffix.lower() != ".zip":
        raise DistributionError(
            "release output must be a ZIP",
            code="voice_pack_build_output_exists",
        )
    outputs = (
        output_zip,
        output_zip.with_suffix(output_zip.suffix + ".sha256"),
        Path(str(output_zip)[:-4] + ".release.json"),
    )
    if any(_is_within(path, source_root) for path in outputs):
        raise DistributionError(
            "release outputs must be outside the source root",
            code="voice_pack_build_rejected",
        )
    _assert_safe_parent_chain(source_root.parent, lstat=_lstat)
    files = _source_files(source_root, lstat=_lstat)
    _assert_safe_parent_chain(output_zip.parent, lstat=_lstat)
    for path in outputs:
        _assert_new_output(path, lstat=_lstat)

    validate_package_tree(source_root)
    manifest = load_manifest(source_root / "voice-pack.json", portable=True)
    key = f"{manifest.id}@{manifest.version}"
    if manifest.version != version or confirmation != key:
        raise DistributionError(
            "exact source identity and confirmation are required",
            code="voice_pack_confirmation_required",
        )
    validate_assets(manifest, package_root=source_root, verify_digest=True)
    expected_files = {
        "voice-pack.json",
        "README.md",
        "LICENSE.txt",
        "NOTICE.txt",
        manifest.gpt_checkpoint.path,
        manifest.sovits_checkpoint.path,
        manifest.reference_audio.path,
    }
    if {path.relative_to(source_root).as_posix() for path in files} != expected_files:
        raise DistributionError(
            "release source contains missing or undeclared files",
            code="voice_pack_build_rejected",
        )
    for path in files:
        relative = path.relative_to(source_root).as_posix()
        if relative in {"voice-pack.json", *_REQUIRED_PUBLIC}:
            _scan_public_text(path)
    output_zip.parent.mkdir(parents=True, exist_ok=True)
    _assert_safe_parent_chain(output_zip.parent, lstat=_lstat)
    for path in outputs:
        _assert_new_output(path, lstat=_lstat)
    created: list[Path] = []
    temp_zip: Path | None = None
    success = False
    try:
        fd, temp_name = tempfile.mkstemp(
            prefix=f".{output_zip.name}.", suffix=".tmp", dir=str(output_zip.parent)
        )
        os.close(fd)
        temp_zip = Path(temp_name)
        temp_zip.unlink()
        archive_root = f"{manifest.id}-voice-pack"
        file_manifest: list[dict[str, Any]] = []
        with zipfile.ZipFile(
            temp_zip, "x", compression=zipfile.ZIP_DEFLATED, compresslevel=9
        ) as archive:
            for path in files:
                relative = path.relative_to(source_root).as_posix()
                size, digest = _hash_file(path)
                file_manifest.append(
                    {"path": relative, "size_bytes": size, "sha256": digest}
                )
                info = zipfile.ZipInfo(
                    f"{archive_root}/{relative}", date_time=(1980, 1, 1, 0, 0, 0)
                )
                info.compress_type = zipfile.ZIP_DEFLATED
                info.create_system = 3
                info.external_attr = 0o100644 << 16
                with path.open("rb") as source, archive.open(
                    info, "w", force_zip64=True
                ) as target:
                    shutil.copyfileobj(source, target, length=1024 * 1024)
        package_size, package_sha = _hash_file(temp_zip)
        os.replace(str(temp_zip), str(output_zip))
        temp_zip = None
        created.append(output_zip)
        sha_path = outputs[1]
        with sha_path.open("w", encoding="utf-8", newline="\n") as handle:
            handle.write(f"{package_sha}  {output_zip.name}\n")
        created.append(sha_path)
        release_path = outputs[2]
        with release_path.open("w", encoding="utf-8", newline="\n") as handle:
            handle.write(json.dumps(
                {
                    "release_schema_version": 1,
                    "pack_id": manifest.id,
                    "version": manifest.version,
                    "archive_root": archive_root,
                    "archive_name": output_zip.name,
                    "size_bytes": package_size,
                    "sha256": package_sha,
                    "files": file_manifest,
                },
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            ) + "\n")
        created.append(release_path)
        success = True
        return {
            "status": "built",
            "id": manifest.id,
            "version": manifest.version,
            "archive_name": output_zip.name,
            "size_bytes": package_size,
            "sha256": package_sha,
            "file_count": len(files),
        }
    except DistributionError:
        raise
    except Exception as exc:
        raise DistributionError(
            "Voice Pack release build failed", code="voice_pack_build_failed"
        ) from exc
    finally:
        if temp_zip is not None:
            temp_zip.unlink(missing_ok=True)
        if not success:
            for path in created:
                path.unlink(missing_ok=True)
