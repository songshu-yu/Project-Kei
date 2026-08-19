"""Validated, project-owned description of the external GPT-SoVITS engine."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Mapping
from urllib.parse import urlparse


PACKAGE_ROOT = Path(__file__).resolve().parent
SERVER_ROOT = PACKAGE_ROOT.parents[3]
PROJECT_ROOT = SERVER_ROOT.parent
BUILTIN_DESCRIPTOR_PATH = PACKAGE_ROOT / "engine.json"
DEFAULT_LOCAL_CONFIG_PATH = SERVER_ROOT / "data" / "gpt_sovits_engine.local.json"

OFFICIAL_UPSTREAM_REPOSITORY = "https://github.com/RVC-Boss/GPT-SoVITS"
OFFICIAL_DISTRIBUTION_REPOSITORY = "https://huggingface.co/lj1995/GPT-SoVITS-windows-package"
FULL_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
ENGINE_ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]{2,63}$")
RELEASE_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{1,63}$")


class DescriptorError(ValueError):
    """A stable error that never includes remote content or local paths."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def _mapping(value: Any, name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise DescriptorError("descriptor_invalid", f"{name} 必须是对象")
    return value


def _string(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise DescriptorError("descriptor_invalid", f"{name} 必须是非空字符串")
    return value.strip()


def _safe_relative(value: Any, name: str) -> str:
    text = _string(value, name).replace("\\", "/")
    path = PurePosixPath(text)
    if path.is_absolute() or ".." in path.parts or re.match(r"^[A-Za-z]:", text):
        raise DescriptorError("descriptor_invalid", f"{name} 必须是安全相对路径")
    return text


@dataclass(frozen=True)
class ArchiveLimits:
    max_files: int
    max_uncompressed_bytes: int
    max_compression_ratio: int


@dataclass(frozen=True)
class EngineDescriptor:
    schema_version: int
    engine_id: str
    provider_key: str
    provider_protocol_version: str
    version: str
    upstream_repository: str
    upstream_release: str
    upstream_commit: str
    upstream_release_url: str
    upstream_license: str
    upstream_license_url: str
    source_id: str
    distribution_repository: str
    distribution_revision: str
    download_url: str
    archive_name: str
    archive_format: str
    archive_root: str
    size_bytes: int
    integrity_algorithm: str
    integrity_digest: str
    default_api_style: str
    supported_api_styles: tuple[str, ...]
    health_method: str
    health_path: str
    health_timeout_seconds: float
    operations: tuple[str, ...]
    audio_formats: tuple[str, ...]
    streaming: bool
    default_timeout_seconds: float
    port: int
    bundled: bool
    source_tree_policy: str
    local_config_relative: str
    default_install_status: str
    required_files: tuple[str, ...]
    marker_file: str
    archive_limits: ArchiveLimits

    @classmethod
    def from_mapping(cls, raw: Mapping[str, Any]) -> "EngineDescriptor":
        upstream = _mapping(raw.get("upstream"), "upstream")
        distribution = _mapping(raw.get("distribution"), "distribution")
        integrity = _mapping(distribution.get("integrity"), "distribution.integrity")
        api_styles = _mapping(raw.get("api_styles"), "api_styles")
        health = _mapping(raw.get("health_check"), "health_check")
        capabilities = _mapping(raw.get("capabilities"), "capabilities")
        installation = _mapping(raw.get("installation"), "installation")
        limits = _mapping(raw.get("archive_limits"), "archive_limits")

        engine_id = _string(raw.get("engine_id"), "engine_id")
        if not ENGINE_ID_RE.fullmatch(engine_id):
            raise DescriptorError("descriptor_invalid", "engine_id 格式无效")
        release = _string(upstream.get("release"), "upstream.release")
        if not RELEASE_RE.fullmatch(release):
            raise DescriptorError("descriptor_invalid", "固定 release 格式无效")
        commit = _string(upstream.get("commit"), "upstream.commit").lower()
        revision = _string(distribution.get("revision"), "distribution.revision").lower()
        digest = _string(integrity.get("digest"), "distribution.integrity.digest").lower()
        if not FULL_SHA_RE.fullmatch(commit) or not FULL_SHA_RE.fullmatch(revision):
            raise DescriptorError("descriptor_unpinned", "release 与分发源必须固定到完整 commit")
        if _string(integrity.get("algorithm"), "distribution.integrity.algorithm").lower() != "sha256":
            raise DescriptorError("descriptor_invalid", "只接受 SHA-256 完整性算法")
        if not SHA256_RE.fullmatch(digest):
            raise DescriptorError("descriptor_invalid", "SHA-256 摘要格式无效")

        upstream_repository = _string(upstream.get("repository"), "upstream.repository").rstrip("/")
        distribution_repository = _string(distribution.get("repository"), "distribution.repository").rstrip("/")
        if upstream_repository != OFFICIAL_UPSTREAM_REPOSITORY:
            raise DescriptorError("source_not_approved", "上游来源未获总控确认")
        if distribution_repository != OFFICIAL_DISTRIBUTION_REPOSITORY:
            raise DescriptorError("source_not_approved", "分发来源未获总控确认")
        release_url = _string(upstream.get("release_url"), "upstream.release_url")
        license_url = _string(upstream.get("license_url"), "upstream.license_url")
        if release_url != f"{OFFICIAL_UPSTREAM_REPOSITORY}/releases/tag/{release}":
            raise DescriptorError("source_not_approved", "release 地址未获总控确认")
        if license_url != f"{OFFICIAL_UPSTREAM_REPOSITORY}/blob/{commit}/LICENSE":
            raise DescriptorError("source_not_approved", "许可证地址未固定到上游 commit")

        archive_name = _safe_relative(distribution.get("archive_name"), "distribution.archive_name")
        if "/" in archive_name:
            raise DescriptorError("descriptor_invalid", "归档文件名不能包含目录")
        download_url = _string(distribution.get("download_url"), "distribution.download_url")
        parsed = urlparse(download_url)
        expected_path = f"/lj1995/GPT-SoVITS-windows-package/resolve/{revision}/{archive_name}"
        if (
            parsed.scheme != "https"
            or parsed.hostname != "huggingface.co"
            or parsed.username is not None
            or parsed.password is not None
            or parsed.path != expected_path
            or parsed.query not in {"", "download=true"}
            or parsed.fragment
        ):
            raise DescriptorError("source_not_approved", "下载地址不是获确认的固定官方来源")

        supported = api_styles.get("supported")
        if not isinstance(supported, list) or not supported or not all(isinstance(item, str) for item in supported):
            raise DescriptorError("descriptor_invalid", "api_styles.supported 格式无效")
        supported_tuple = tuple(supported)
        default_style = _string(api_styles.get("default"), "api_styles.default")
        if default_style not in supported_tuple or not set(supported_tuple).issubset({"auto", "api_py", "legacy_v2"}):
            raise DescriptorError("descriptor_invalid", "API 风格不受 Provider 支持")

        required = installation.get("required_files")
        if not isinstance(required, list) or not required:
            raise DescriptorError("descriptor_invalid", "installation.required_files 不能为空")
        required_files = tuple(_safe_relative(item, "installation.required_files") for item in required)
        archive_format = _string(distribution.get("archive_format"), "distribution.archive_format").lower()
        if archive_format not in {"zip", "7z"}:
            raise DescriptorError("descriptor_invalid", "只支持 zip 或 7z 归档")

        try:
            size_bytes = int(distribution.get("size_bytes"))
            port = int(capabilities.get("port"))
            schema_version = int(raw.get("schema_version"))
            max_files = int(limits.get("max_files"))
            max_uncompressed = int(limits.get("max_uncompressed_bytes"))
            max_ratio = int(limits.get("max_compression_ratio"))
            health_timeout = float(health.get("timeout_seconds"))
            default_timeout = float(capabilities.get("default_timeout_seconds"))
        except (TypeError, ValueError) as exc:
            raise DescriptorError("descriptor_invalid", "描述文件数值字段无效") from exc
        if schema_version != 1 or size_bytes <= 0 or not 1 <= port <= 65535:
            raise DescriptorError("descriptor_invalid", "描述文件版本、大小或端口无效")
        if min(max_files, max_uncompressed, max_ratio) <= 0 or min(health_timeout, default_timeout) <= 0:
            raise DescriptorError("descriptor_invalid", "归档限制或超时必须为正数")

        operations = capabilities.get("operations")
        formats = capabilities.get("audio_formats")
        if not isinstance(operations, list) or not all(isinstance(item, str) for item in operations):
            raise DescriptorError("descriptor_invalid", "capabilities.operations 格式无效")
        if not isinstance(formats, list) or not all(isinstance(item, str) for item in formats):
            raise DescriptorError("descriptor_invalid", "capabilities.audio_formats 格式无效")

        return cls(
            schema_version=schema_version,
            engine_id=engine_id,
            provider_key=_string(raw.get("provider_key"), "provider_key"),
            provider_protocol_version=_string(raw.get("provider_protocol_version"), "provider_protocol_version"),
            version=_string(raw.get("version"), "version"),
            upstream_repository=upstream_repository,
            upstream_release=release,
            upstream_commit=commit,
            upstream_release_url=release_url,
            upstream_license=_string(upstream.get("license"), "upstream.license"),
            upstream_license_url=license_url,
            source_id=_string(distribution.get("source_id"), "distribution.source_id"),
            distribution_repository=distribution_repository,
            distribution_revision=revision,
            download_url=download_url,
            archive_name=archive_name,
            archive_format=archive_format,
            archive_root=_safe_relative(distribution.get("archive_root"), "distribution.archive_root"),
            size_bytes=size_bytes,
            integrity_algorithm="sha256",
            integrity_digest=digest,
            default_api_style=default_style,
            supported_api_styles=supported_tuple,
            health_method=_string(health.get("method"), "health_check.method").upper(),
            health_path=_string(health.get("path"), "health_check.path"),
            health_timeout_seconds=health_timeout,
            operations=tuple(operations),
            audio_formats=tuple(formats),
            streaming=bool(capabilities.get("streaming", False)),
            default_timeout_seconds=default_timeout,
            port=port,
            bundled=bool(installation.get("bundled", False)),
            source_tree_policy=_string(installation.get("source_tree_policy"), "installation.source_tree_policy"),
            local_config_relative=_safe_relative(installation.get("local_config"), "installation.local_config"),
            default_install_status=_string(installation.get("default_status"), "installation.default_status"),
            required_files=required_files,
            marker_file=_safe_relative(installation.get("marker_file"), "installation.marker_file"),
            archive_limits=ArchiveLimits(max_files, max_uncompressed, max_ratio),
        )

    @property
    def release_identity(self) -> str:
        return f"{self.upstream_release}@{self.upstream_commit}"

    def public_summary(self) -> dict[str, Any]:
        return {
            "engine_id": self.engine_id,
            "provider_key": self.provider_key,
            "version": self.version,
            "release": self.upstream_release,
            "commit": self.upstream_commit,
            "distribution_revision": self.distribution_revision,
            "integrity": {"algorithm": self.integrity_algorithm, "digest": self.integrity_digest},
            "api_styles": list(self.supported_api_styles),
            "health_check": {"method": self.health_method, "path": self.health_path},
            "capabilities": {
                "operations": list(self.operations),
                "audio_formats": list(self.audio_formats),
                "streaming": self.streaming,
                "port": self.port,
            },
            "installation": {
                "bundled": self.bundled,
                "status": self.default_install_status,
                "source_tree_policy": self.source_tree_policy,
                "local_config": self.local_config_relative,
            },
        }


def load_descriptor(path: Path = BUILTIN_DESCRIPTOR_PATH) -> EngineDescriptor:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise DescriptorError("descriptor_unreadable", "引擎描述文件不可读") from exc
    return EngineDescriptor.from_mapping(_mapping(raw, "descriptor"))


__all__ = [
    "BUILTIN_DESCRIPTOR_PATH",
    "DEFAULT_LOCAL_CONFIG_PATH",
    "DescriptorError",
    "EngineDescriptor",
    "PROJECT_ROOT",
    "load_descriptor",
]
