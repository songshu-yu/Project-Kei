"""Explicit, fixed-source acquisition and local registration for GPT-SoVITS."""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import stat
import tempfile
import urllib.parse
import urllib.request
import uuid
import zipfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any, Callable, Mapping

from .descriptor import (
    DEFAULT_LOCAL_CONFIG_PATH,
    PROJECT_ROOT,
    ArchiveLimits,
    DescriptorError,
    EngineDescriptor,
    load_descriptor,
)


class AcquisitionError(RuntimeError):
    """Sanitized acquisition failure; details never include URLs or local paths."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code

    def to_public_dict(self) -> dict[str, str]:
        return {"code": self.code, "message": str(self)}


@dataclass(frozen=True)
class AcquisitionResult:
    engine_id: str
    status: str
    integrity_status: str
    api_style: str

    def to_public_dict(self) -> dict[str, str]:
        return {
            "engine_id": self.engine_id,
            "status": self.status,
            "integrity_status": self.integrity_status,
            "api_style": self.api_style,
        }


Downloader = Callable[[EngineDescriptor, Path], None]
Extractor = Callable[[EngineDescriptor, Path, Path], None]


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _is_within(path: Path, root: Path) -> bool:
    path_text = os.path.normcase(str(path.resolve(strict=False)))
    root_text = os.path.normcase(str(root.resolve(strict=False)))
    try:
        return os.path.commonpath([path_text, root_text]) == root_text
    except ValueError:
        return False


def validate_external_root(path: Path, *, project_root: Path = PROJECT_ROOT) -> Path:
    if not path.is_absolute():
        raise AcquisitionError("install_root_invalid", "安装目录必须是项目外的绝对路径")
    resolved = path.resolve(strict=False)
    if str(resolved) == resolved.anchor or _is_within(resolved, project_root):
        raise AcquisitionError("install_root_invalid", "安装目录必须位于项目外且不能是磁盘根目录")
    return resolved


def _child(root: Path, relative: str) -> Path:
    candidate = (root / Path(*PurePosixPath(relative).parts)).resolve(strict=False)
    if not _is_within(candidate, root):
        raise AcquisitionError("install_layout_invalid", "引擎入口超出安装目录")
    return candidate


def _required_files_ready(descriptor: EngineDescriptor, root: Path) -> bool:
    return all(_child(root, relative).is_file() for relative in descriptor.required_files)


class LocalEngineRegistry:
    """Ignored machine-local state. Public status never returns the absolute path."""

    def __init__(self, path: Path = DEFAULT_LOCAL_CONFIG_PATH):
        self.path = path

    def load(self) -> dict[str, Any] | None:
        if not self.path.exists():
            return None
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise AcquisitionError("local_config_invalid", "本机引擎配置不可读") from exc
        if not isinstance(data, dict):
            raise AcquisitionError("local_config_invalid", "本机引擎配置格式无效")
        return data

    def save(self, data: Mapping[str, Any]) -> None:
        temp_path = self.path.with_name(f".{self.path.name}.{uuid.uuid4().hex}.tmp")
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with temp_path.open("x", encoding="utf-8", newline="\n") as handle:
                json.dump(dict(data), handle, ensure_ascii=False, indent=2, sort_keys=True)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp_path, self.path)
        except Exception as exc:
            try:
                temp_path.unlink(missing_ok=True)
            except OSError:
                pass
            raise AcquisitionError("local_config_write_failed", "本机引擎配置写入失败") from exc

    def status(self, descriptor: EngineDescriptor) -> dict[str, Any]:
        data = self.load()
        if data is None:
            result = descriptor.public_summary()["installation"]
            return {
                "engine_id": descriptor.engine_id,
                "configured": False,
                "status": result["status"],
                "integrity_status": "not_checked",
                "entrypoints_ready": False,
            }
        if data.get("engine_id") != descriptor.engine_id:
            raise AcquisitionError("local_config_invalid", "本机配置的 engine id 不匹配")
        root_text = data.get("install_root")
        if not isinstance(root_text, str) or not root_text:
            raise AcquisitionError("local_config_invalid", "本机配置缺少安装目录")
        try:
            root = validate_external_root(Path(root_text))
            ready = root.is_dir() and _required_files_ready(descriptor, root)
        except AcquisitionError:
            ready = False
        return {
            "engine_id": descriptor.engine_id,
            "configured": True,
            "status": data.get("install_status", "registered_existing") if ready else "registered_missing",
            "integrity_status": data.get("integrity_status", "unverified_existing_install"),
            "entrypoints_ready": ready,
            "api_style": data.get("api_style", descriptor.default_api_style),
        }

    def register(
        self,
        descriptor: EngineDescriptor,
        root: Path,
        *,
        api_style: str,
        install_status: str,
        integrity_status: str,
    ) -> AcquisitionResult:
        root = validate_external_root(root)
        if api_style not in descriptor.supported_api_styles:
            raise AcquisitionError("api_style_invalid", "API 风格不受当前 Provider 支持")
        if not root.is_dir() or not _required_files_ready(descriptor, root):
            raise AcquisitionError("install_not_ready", "安装目录缺少固定入口文件")
        self.save({
            "schema_version": 1,
            "engine_id": descriptor.engine_id,
            "release_identity": descriptor.release_identity,
            "distribution_revision": descriptor.distribution_revision,
            "install_root": str(root),
            "api_style": api_style,
            "install_status": install_status,
            "integrity_status": integrity_status,
            "registered_at": _utc_now(),
        })
        return AcquisitionResult(descriptor.engine_id, install_status, integrity_status, api_style)


def register_existing_install(
    install_root: Path,
    *,
    api_style: str = "auto",
    registry_path: Path = DEFAULT_LOCAL_CONFIG_PATH,
    descriptor: EngineDescriptor | None = None,
) -> AcquisitionResult:
    selected = descriptor or load_descriptor()
    return LocalEngineRegistry(registry_path).register(
        selected,
        install_root,
        api_style=api_style,
        install_status="registered_existing",
        integrity_status="unverified_existing_install",
    )


def _marker_data(descriptor: EngineDescriptor) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "engine_id": descriptor.engine_id,
        "release_identity": descriptor.release_identity,
        "distribution_revision": descriptor.distribution_revision,
        "integrity": {
            "algorithm": descriptor.integrity_algorithm,
            "digest": descriptor.integrity_digest,
        },
        "installed_at": _utc_now(),
        "scripts_executed": False,
    }


def _matching_marker(descriptor: EngineDescriptor, root: Path) -> bool:
    marker = _child(root, descriptor.marker_file)
    try:
        data = json.loads(marker.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return False
    integrity = data.get("integrity", {}) if isinstance(data, dict) else {}
    return (
        data.get("engine_id") == descriptor.engine_id
        and data.get("release_identity") == descriptor.release_identity
        and data.get("distribution_revision") == descriptor.distribution_revision
        and isinstance(integrity, dict)
        and integrity.get("algorithm") == descriptor.integrity_algorithm
        and integrity.get("digest") == descriptor.integrity_digest
    )


def download_fixed_source(descriptor: EngineDescriptor, destination: Path) -> None:
    """Download only the URL already validated by the built-in descriptor."""
    request = urllib.request.Request(
        descriptor.download_url,
        headers={"User-Agent": "Project-Kei-PK-211/1"},
        method="GET",
    )
    try:
        with urllib.request.urlopen(request, timeout=60) as response, destination.open("xb") as output:
            final_url = urllib.parse.urlparse(response.geturl())
            if final_url.scheme != "https" or final_url.username is not None or final_url.password is not None:
                raise AcquisitionError("source_not_approved", "固定来源重定向不安全")
            declared = response.headers.get("Content-Length")
            if declared and int(declared) != descriptor.size_bytes:
                raise AcquisitionError("download_size_mismatch", "下载文件大小与固定元数据不符")
            total = 0
            while True:
                chunk = response.read(1024 * 1024)
                if not chunk:
                    break
                total += len(chunk)
                if total > descriptor.size_bytes:
                    raise AcquisitionError("download_size_mismatch", "下载文件超过固定大小")
                output.write(chunk)
            output.flush()
            os.fsync(output.fileno())
    except AcquisitionError:
        raise
    except Exception as exc:
        raise AcquisitionError("download_interrupted", "固定来源下载中断") from exc


def verify_archive(descriptor: EngineDescriptor, archive_path: Path) -> None:
    digest = hashlib.sha256()
    total = 0
    try:
        with archive_path.open("rb") as handle:
            while True:
                chunk = handle.read(1024 * 1024)
                if not chunk:
                    break
                total += len(chunk)
                if total > descriptor.size_bytes:
                    raise AcquisitionError("download_size_mismatch", "下载文件超过固定大小")
                digest.update(chunk)
    except AcquisitionError:
        raise
    except OSError as exc:
        raise AcquisitionError("download_unreadable", "下载文件不可读") from exc
    if total != descriptor.size_bytes:
        raise AcquisitionError("download_size_mismatch", "下载文件大小与固定元数据不符")
    if digest.hexdigest() != descriptor.integrity_digest:
        raise AcquisitionError("integrity_mismatch", "下载文件 SHA-256 校验失败")


def _safe_member(name: str) -> PurePosixPath:
    normalized = str(name or "").replace("\\", "/")
    path = PurePosixPath(normalized)
    if (
        not normalized
        or normalized.startswith("/")
        or path.is_absolute()
        or ".." in path.parts
        or re.match(r"^[A-Za-z]:", normalized)
    ):
        raise AcquisitionError("archive_unsafe", "归档包含不安全路径")
    return path


def _check_archive_totals(file_count: int, uncompressed: int, compressed: int, limits: ArchiveLimits) -> None:
    if file_count > limits.max_files or uncompressed > limits.max_uncompressed_bytes:
        raise AcquisitionError("archive_limits_exceeded", "归档超过文件数或解压大小限制")
    if compressed > 0 and uncompressed > compressed * limits.max_compression_ratio:
        raise AcquisitionError("archive_limits_exceeded", "归档压缩比超过限制")


def _extract_zip(descriptor: EngineDescriptor, archive_path: Path, destination: Path) -> None:
    try:
        with zipfile.ZipFile(archive_path, "r") as archive:
            infos = archive.infolist()
            total_uncompressed = sum(max(0, info.file_size) for info in infos)
            total_compressed = sum(max(0, info.compress_size) for info in infos)
            _check_archive_totals(len(infos), total_uncompressed, total_compressed, descriptor.archive_limits)
            members: list[tuple[zipfile.ZipInfo, PurePosixPath]] = []
            for info in infos:
                member = _safe_member(info.filename)
                unix_mode = (info.external_attr >> 16) & 0xFFFF
                if stat.S_ISLNK(unix_mode):
                    raise AcquisitionError("archive_unsafe", "归档包含链接")
                members.append((info, member))
            for info, member in members:
                target = destination.joinpath(*member.parts)
                if not _is_within(target, destination):
                    raise AcquisitionError("archive_unsafe", "归档成员逃逸目标目录")
                if info.is_dir():
                    target.mkdir(parents=True, exist_ok=True)
                    continue
                target.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(info, "r") as source, target.open("xb") as output:
                    shutil.copyfileobj(source, output, length=1024 * 1024)
    except AcquisitionError:
        raise
    except (OSError, zipfile.BadZipFile) as exc:
        raise AcquisitionError("archive_extract_failed", "归档解包失败") from exc


def _truthy_attribute(value: Any) -> bool:
    try:
        return bool(value() if callable(value) else value)
    except Exception:
        return True


def _extract_7z(descriptor: EngineDescriptor, archive_path: Path, destination: Path) -> None:
    try:
        import py7zr  # type: ignore
    except ImportError as exc:
        raise AcquisitionError(
            "extractor_dependency_missing",
            "缺少 7z Python 解包依赖；必须由用户显式安装后重试",
        ) from exc
    try:
        with py7zr.SevenZipFile(archive_path, mode="r") as archive:
            infos = archive.list()
            total_uncompressed = sum(max(0, int(getattr(info, "uncompressed", 0) or 0)) for info in infos)
            _check_archive_totals(len(infos), total_uncompressed, descriptor.size_bytes, descriptor.archive_limits)
            names: list[PurePosixPath] = []
            for info in infos:
                member = _safe_member(getattr(info, "filename", ""))
                attributes = int(getattr(info, "attributes", 0) or 0)
                posix_mode = int(getattr(info, "posix_mode", 0) or 0)
                if (
                    _truthy_attribute(getattr(info, "is_symlink", False))
                    or _truthy_attribute(getattr(info, "is_hardlink", False))
                    or stat.S_ISLNK(posix_mode)
                    or attributes & 0x400
                ):
                    raise AcquisitionError("archive_unsafe", "归档包含链接或重解析点")
                names.append(member)
            archive.extractall(path=destination)
            for member in names:
                target = destination.joinpath(*member.parts)
                if target.is_symlink() or not _is_within(target, destination):
                    raise AcquisitionError("archive_unsafe", "归档成员逃逸目标目录")
    except AcquisitionError:
        raise
    except Exception as exc:
        raise AcquisitionError("archive_extract_failed", "归档解包失败") from exc


def safe_extract_archive(descriptor: EngineDescriptor, archive_path: Path, destination: Path) -> None:
    if descriptor.archive_format == "zip":
        _extract_zip(descriptor, archive_path, destination)
    elif descriptor.archive_format == "7z":
        _extract_7z(descriptor, archive_path, destination)
    else:
        raise AcquisitionError("archive_format_unsupported", "归档格式不受支持")


def acquire_engine(
    descriptor: EngineDescriptor,
    install_root: Path,
    *,
    confirmation: str,
    api_style: str = "auto",
    offline: bool = False,
    registry_path: Path = DEFAULT_LOCAL_CONFIG_PATH,
    project_root: Path = PROJECT_ROOT,
    downloader: Downloader = download_fixed_source,
    extractor: Extractor = safe_extract_archive,
) -> AcquisitionResult:
    if confirmation != descriptor.engine_id:
        raise AcquisitionError("confirmation_required", "必须精确确认固定 engine id")
    if api_style not in descriptor.supported_api_styles:
        raise AcquisitionError("api_style_invalid", "API 风格不受当前 Provider 支持")
    destination = validate_external_root(install_root, project_root=project_root)
    registry = LocalEngineRegistry(registry_path)

    if destination.is_dir() and _matching_marker(descriptor, destination) and _required_files_ready(descriptor, destination):
        return registry.register(
            descriptor,
            destination,
            api_style=api_style,
            install_status="installed_verified",
            integrity_status="sha256_verified",
        )

    if offline:
        data = registry.load()
        if data and data.get("engine_id") == descriptor.engine_id and data.get("install_root") == str(destination):
            if destination.is_dir() and _required_files_ready(descriptor, destination):
                return AcquisitionResult(
                    descriptor.engine_id,
                    "offline_reuse",
                    str(data.get("integrity_status", "unverified_existing_install")),
                    str(data.get("api_style", api_style)),
                )
        raise AcquisitionError("offline_unavailable", "离线模式下没有可复用的显式安装")

    destination.parent.mkdir(parents=True, exist_ok=True)
    destination_was_empty = False
    if destination.exists():
        if not destination.is_dir() or any(destination.iterdir()):
            raise AcquisitionError("target_exists", "安装目录已存在且非空，拒绝覆盖")
        destination_was_empty = True

    staging = Path(tempfile.mkdtemp(prefix=".project-kei-gptsovits-", dir=str(destination.parent)))
    installed = False
    committed = False
    try:
        with tempfile.TemporaryDirectory(prefix="project-kei-gptsovits-download-") as download_dir:
            archive_path = Path(download_dir) / descriptor.archive_name
            downloader(descriptor, archive_path)
            verify_archive(descriptor, archive_path)
            extractor(descriptor, archive_path, staging)

        extracted_root = _child(staging, descriptor.archive_root)
        if not extracted_root.is_dir() or not _required_files_ready(descriptor, extracted_root):
            raise AcquisitionError("install_layout_invalid", "归档缺少固定引擎入口")
        marker_path = _child(extracted_root, descriptor.marker_file)
        marker_path.write_text(json.dumps(_marker_data(descriptor), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

        if destination_was_empty:
            destination.rmdir()
        if destination.exists():
            raise AcquisitionError("target_exists", "安装目录在获取期间被创建，拒绝覆盖")
        os.replace(extracted_root, destination)
        installed = True
        result = registry.register(
            descriptor,
            destination,
            api_style=api_style,
            install_status="installed_verified",
            integrity_status="sha256_verified",
        )
        committed = True
        return result
    except AcquisitionError:
        raise
    except Exception as exc:
        raise AcquisitionError("install_failed", "引擎获取或安装失败") from exc
    finally:
        if installed and not committed:
            shutil.rmtree(destination, ignore_errors=True)
        shutil.rmtree(staging, ignore_errors=True)


def acquire_builtin_engine(
    install_root: Path,
    *,
    confirmation: str,
    api_style: str = "auto",
    offline: bool = False,
    registry_path: Path = DEFAULT_LOCAL_CONFIG_PATH,
) -> AcquisitionResult:
    try:
        descriptor = load_descriptor()
    except DescriptorError as exc:
        raise AcquisitionError(exc.code, str(exc)) from exc
    return acquire_engine(
        descriptor,
        install_root,
        confirmation=confirmation,
        api_style=api_style,
        offline=offline,
        registry_path=registry_path,
    )


__all__ = [
    "AcquisitionError",
    "AcquisitionResult",
    "LocalEngineRegistry",
    "acquire_builtin_engine",
    "acquire_engine",
    "download_fixed_source",
    "register_existing_install",
    "safe_extract_archive",
    "validate_external_root",
    "verify_archive",
]
