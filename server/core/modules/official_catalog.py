"""Trusted, cacheable dual-source catalog for optional Project Kei modules."""

from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
import time
import zipfile
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional
from urllib.parse import urljoin, urlparse

import httpx

from .contracts import CORE_RESERVED_MODULE_IDS
from .manifest import (
    ALLOWED_PERMISSIONS,
    CORE_VERSION,
    MODULE_ID_PATTERN,
    RuntimeRequirement,
    compare_semver,
    validate_manifest,
    version_satisfies,
    parse_runtime_requirements,
)


OFFICIAL_OWNER = "songshu-yu"
OFFICIAL_GITEE_OWNER = "songshuyu957"
OFFICIAL_REPOSITORY = "Project-Kei-Modules"
OFFICIAL_PUBLISHER = "Project Kei"
OFFICIAL_CATALOG_URL = (
    "https://raw.githubusercontent.com/"
    f"{OFFICIAL_OWNER}/{OFFICIAL_REPOSITORY}/main/catalog/official-catalog.json"
)
OFFICIAL_GITEE_CATALOG_URL = (
    f"https://gitee.com/{OFFICIAL_GITEE_OWNER}/{OFFICIAL_REPOSITORY}/"
    "raw/main/catalog/official-catalog.json"
)
OFFICIAL_DOWNLOAD_SOURCES = ("auto", "github", "gitee")
MAX_CATALOG_BYTES = 1024 * 1024
MAX_OFFICIAL_PACKAGE_BYTES = 64 * 1024 * 1024
_REDIRECT_STATUSES = {301, 302, 303, 307, 308}
_RELEASE_REDIRECT_HOSTS = {
    "release-assets.githubusercontent.com",
    "objects.githubusercontent.com",
}
_HEX64 = re.compile(r"^[0-9a-fA-F]{64}$")
_RELEASE_TOKEN = re.compile(r"^[0-9A-Za-z._-]{1,120}$")
_ASSET_NAME = re.compile(r"^[0-9A-Za-z._-]{1,160}\.zip$")


def normalize_official_download_source(value: str) -> str:
    normalized = str(value or "").strip().lower()
    if normalized not in OFFICIAL_DOWNLOAD_SOURCES:
        raise OfficialCatalogError(
            "official download source must be auto, github, or gitee",
            code="official_download_source_invalid",
            stage="source_selection",
        )
    return normalized


def _source_order(value: str) -> tuple[str, ...]:
    source = normalize_official_download_source(value)
    return ("github", "gitee") if source == "auto" else (source,)


def _catalog_url(source: str) -> str:
    return OFFICIAL_CATALOG_URL if source == "github" else OFFICIAL_GITEE_CATALOG_URL


def _gitee_package_url(release_tag: str, asset_name: str) -> str:
    return (
        f"https://gitee.com/{OFFICIAL_GITEE_OWNER}/{OFFICIAL_REPOSITORY}/"
        f"raw/main/packages/{release_tag}/{asset_name}"
    )


def _transport_fallback_allowed(error: "OfficialCatalogError") -> bool:
    return error.retryable and error.code in {
        "official_catalog_refresh_failed",
        "official_github_rate_limited",
        "official_gitee_rate_limited",
        "official_module_download_failed",
        "official_module_download_timeout",
    }


class OfficialCatalogError(Exception):
    def __init__(
        self,
        message: str,
        *,
        code: str,
        stage: str,
        retryable: bool = False,
        received_bytes: int = 0,
        retry_after: Optional[str] = None,
    ):
        super().__init__(message)
        self.code = code
        self.stage = stage
        self.retryable = retryable
        self.received_bytes = received_bytes
        self.retry_after = retry_after

    def detail(self) -> Dict[str, Any]:
        return {
            "code": self.code,
            "message": str(self),
            "stage": self.stage,
            "retryable": self.retryable,
            "received_bytes": self.received_bytes,
            "retry_after": self.retry_after,
        }


@dataclass(frozen=True)
class OfficialModuleRelease:
    module_id: str
    name: str
    version: str
    core_compatibility: str
    manifest_sha256: str
    package_url: str
    package_size: int
    package_sha256: str
    release_tag: str
    asset_name: str
    dependencies: tuple[str, ...]
    optional_dependencies: tuple[str, ...]
    runtime_requirements: tuple[RuntimeRequirement, ...]
    conflicts: tuple[str, ...]
    permissions: tuple[str, ...]
    data_policy: str
    requires_restart: bool

    def to_dict(self) -> Dict[str, Any]:
        payload = asdict(self)
        for field in ("dependencies", "optional_dependencies", "conflicts", "permissions"):
            payload[field] = list(payload[field])
        if self.runtime_requirements:
            payload["runtime_requirements"] = [
                requirement.to_dict() for requirement in self.runtime_requirements
            ]
        else:
            payload.pop("runtime_requirements", None)
        payload["source"] = {
            "publisher": OFFICIAL_PUBLISHER,
            "owner": OFFICIAL_OWNER,
            "repository": OFFICIAL_REPOSITORY,
            "release_tag": self.release_tag,
            "asset_name": self.asset_name,
        }
        return payload


@dataclass(frozen=True)
class OfficialModuleCatalog:
    generated_at: str
    modules: tuple[OfficialModuleRelease, ...]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "schema_version": 1,
            "publisher": OFFICIAL_PUBLISHER,
            "owner": OFFICIAL_OWNER,
            "repository": OFFICIAL_REPOSITORY,
            "generated_at": self.generated_at,
            "modules": [module.to_dict() for module in self.modules],
        }


def _string_list(payload: Dict[str, Any], field: str) -> tuple[str, ...]:
    value = payload.get(field)
    if (
        not isinstance(value, list)
        or any(not isinstance(item, str) or not item for item in value)
        or len(value) != len(set(value))
    ):
        raise OfficialCatalogError(
            f"catalog.{field} must be a unique string array",
            code="official_catalog_invalid",
            stage="catalog_validation",
        )
    if any(not MODULE_ID_PATTERN.fullmatch(item) for item in value):
        raise OfficialCatalogError(
            f"catalog.{field} contains an invalid module id",
            code="official_catalog_invalid",
            stage="catalog_validation",
        )
    return tuple(value)


def _digest(payload: Dict[str, Any], field: str) -> str:
    value = payload.get(field)
    if not isinstance(value, str) or not _HEX64.fullmatch(value):
        raise OfficialCatalogError(
            f"catalog.{field} must be a SHA-256 digest",
            code="official_catalog_invalid",
            stage="catalog_validation",
        )
    return value.lower()


def _release_url(module_id: str, version: str, tag: str, asset_name: str) -> str:
    return (
        f"https://github.com/{OFFICIAL_OWNER}/{OFFICIAL_REPOSITORY}/"
        f"releases/download/{tag}/{asset_name}"
    )


def validate_official_catalog(payload: Any, core_version: str = CORE_VERSION) -> OfficialModuleCatalog:
    if not isinstance(payload, dict):
        raise OfficialCatalogError(
            "official catalog root must be an object",
            code="official_catalog_invalid",
            stage="catalog_validation",
        )
    allowed_top = {"schema_version", "publisher", "owner", "repository", "generated_at", "modules"}
    if set(payload) != allowed_top or payload.get("schema_version") != 1:
        raise OfficialCatalogError(
            "official catalog top-level contract is invalid",
            code="official_catalog_invalid",
            stage="catalog_validation",
        )
    if (
        payload.get("publisher") != OFFICIAL_PUBLISHER
        or payload.get("owner") != OFFICIAL_OWNER
        or payload.get("repository") != OFFICIAL_REPOSITORY
    ):
        raise OfficialCatalogError(
            "official catalog source identity is not trusted",
            code="official_catalog_source_untrusted",
            stage="catalog_validation",
        )
    generated_at = payload.get("generated_at")
    raw_modules = payload.get("modules")
    if not isinstance(generated_at, str) or not 1 <= len(generated_at) <= 64 or not isinstance(raw_modules, list):
        raise OfficialCatalogError(
            "official catalog metadata is invalid",
            code="official_catalog_invalid",
            stage="catalog_validation",
        )
    required_release = {
        "module_id", "name", "version", "core_compatibility", "manifest_sha256",
        "package_url", "package_size", "package_sha256", "release_tag", "asset_name",
        "dependencies", "optional_dependencies", "conflicts", "permissions",
        "data_policy", "requires_restart",
    }
    allowed_release = required_release | {"runtime_requirements"}
    releases: List[OfficialModuleRelease] = []
    seen = set()
    for item in raw_modules:
        if (
            not isinstance(item, dict)
            or not required_release.issubset(item)
            or not set(item).issubset(allowed_release)
        ):
            raise OfficialCatalogError(
                "official catalog module fields are invalid",
                code="official_catalog_invalid",
                stage="catalog_validation",
            )
        module_id = item.get("module_id")
        name = item.get("name")
        version = item.get("version")
        compatibility = item.get("core_compatibility")
        tag = item.get("release_tag")
        asset_name = item.get("asset_name")
        package_size = item.get("package_size")
        if not isinstance(module_id, str) or not MODULE_ID_PATTERN.fullmatch(module_id):
            raise OfficialCatalogError("invalid official module id", code="official_catalog_invalid", stage="catalog_validation")
        if module_id in CORE_RESERVED_MODULE_IDS:
            raise OfficialCatalogError("official catalog cannot publish a Core module id", code="official_catalog_invalid", stage="catalog_validation")
        if not isinstance(name, str) or not 1 <= len(name.strip()) <= 120:
            raise OfficialCatalogError("invalid official module name", code="official_catalog_invalid", stage="catalog_validation")
        if not isinstance(version, str):
            raise OfficialCatalogError("invalid official module version", code="official_catalog_invalid", stage="catalog_validation")
        try:
            compare_semver(version, version)
        except Exception as exc:
            raise OfficialCatalogError("invalid official module version", code="official_catalog_invalid", stage="catalog_validation") from exc
        if not isinstance(compatibility, str):
            raise OfficialCatalogError("invalid Core compatibility", code="official_catalog_invalid", stage="catalog_validation")
        try:
            version_satisfies(core_version, compatibility)
        except Exception as exc:
            raise OfficialCatalogError("invalid Core compatibility", code="official_catalog_invalid", stage="catalog_validation") from exc
        if not isinstance(tag, str) or not _RELEASE_TOKEN.fullmatch(tag):
            raise OfficialCatalogError("invalid official release tag", code="official_catalog_invalid", stage="catalog_validation")
        if not isinstance(asset_name, str) or not _ASSET_NAME.fullmatch(asset_name):
            raise OfficialCatalogError("invalid official asset name", code="official_catalog_invalid", stage="catalog_validation")
        if item.get("package_url") != _release_url(module_id, version, tag, asset_name):
            raise OfficialCatalogError(
                "official package URL is not the fixed repository Release asset",
                code="official_catalog_source_untrusted",
                stage="catalog_validation",
            )
        if (
            not isinstance(package_size, int)
            or isinstance(package_size, bool)
            or not 1 <= package_size <= MAX_OFFICIAL_PACKAGE_BYTES
        ):
            raise OfficialCatalogError("official package size is invalid", code="official_catalog_invalid", stage="catalog_validation")
        dependencies = _string_list(item, "dependencies")
        optional_dependencies = _string_list(item, "optional_dependencies")
        try:
            runtime_requirements = parse_runtime_requirements(item)
        except Exception as exc:
            raise OfficialCatalogError(
                "official runtime requirements are invalid",
                code="official_catalog_invalid",
                stage="catalog_validation",
            ) from exc
        conflicts = _string_list(item, "conflicts")
        permissions = item.get("permissions")
        if (
            not isinstance(permissions, list)
            or any(permission not in ALLOWED_PERMISSIONS for permission in permissions)
            or len(permissions) != len(set(permissions))
        ):
            raise OfficialCatalogError("official permissions are invalid", code="official_catalog_invalid", stage="catalog_validation")
        if item.get("data_policy") != "preserve_on_uninstall" or not isinstance(item.get("requires_restart"), bool):
            raise OfficialCatalogError("official lifecycle metadata is invalid", code="official_catalog_invalid", stage="catalog_validation")
        key = (module_id, version)
        if key in seen:
            raise OfficialCatalogError("duplicate official module version", code="official_catalog_invalid", stage="catalog_validation")
        seen.add(key)
        releases.append(OfficialModuleRelease(
            module_id=module_id,
            name=name.strip(),
            version=version,
            core_compatibility=compatibility,
            manifest_sha256=_digest(item, "manifest_sha256"),
            package_url=item["package_url"],
            package_size=package_size,
            package_sha256=_digest(item, "package_sha256"),
            release_tag=tag,
            asset_name=asset_name,
            dependencies=dependencies,
            optional_dependencies=optional_dependencies,
            runtime_requirements=runtime_requirements,
            conflicts=conflicts,
            permissions=tuple(permissions),
            data_policy="preserve_on_uninstall",
            requires_restart=item["requires_restart"],
        ))
    releases.sort(key=lambda item: (item.module_id, item.version))
    return OfficialModuleCatalog(generated_at=generated_at, modules=tuple(releases))


def _catalog_wire_payload(catalog: OfficialModuleCatalog) -> Dict[str, Any]:
    payload = {
        "schema_version": 1,
        "publisher": OFFICIAL_PUBLISHER,
        "owner": OFFICIAL_OWNER,
        "repository": OFFICIAL_REPOSITORY,
        "generated_at": catalog.generated_at,
        "modules": [],
    }
    for release in catalog.modules:
        item = asdict(release)
        for field in ("dependencies", "optional_dependencies", "conflicts", "permissions"):
            item[field] = list(item[field])
        if release.runtime_requirements:
            item["runtime_requirements"] = [
                requirement.to_dict() for requirement in release.runtime_requirements
            ]
        else:
            item.pop("runtime_requirements", None)
        payload["modules"].append(item)
    return payload


class OfficialCatalogStore:
    def __init__(self, bundled_path: Path, cache_path: Path):
        self.bundled_path = Path(bundled_path)
        self.cache_path = Path(cache_path)
        self.backup_path = self.cache_path.with_name(self.cache_path.stem + ".last-good.json")

    @staticmethod
    def _read(path: Path) -> OfficialModuleCatalog:
        try:
            raw = path.read_bytes()
            if len(raw) > MAX_CATALOG_BYTES:
                raise ValueError("catalog too large")
            return validate_official_catalog(json.loads(raw.decode("utf-8")))
        except OfficialCatalogError:
            raise
        except Exception as exc:
            raise OfficialCatalogError(
                "official catalog cache is unreadable",
                code="official_catalog_cache_invalid",
                stage="catalog_cache",
            ) from exc

    def load(self) -> tuple[OfficialModuleCatalog, str]:
        for path, source in (
            (self.cache_path, "cache"),
            (self.backup_path, "last_good_cache"),
            (self.bundled_path, "bundled"),
        ):
            if path.is_file():
                try:
                    return self._read(path), source
                except OfficialCatalogError:
                    continue
        raise OfficialCatalogError(
            "no valid official module catalog is available",
            code="official_catalog_unavailable",
            stage="catalog_cache",
        )

    @staticmethod
    def _atomic_write(path: Path, payload: bytes) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temp_path: Optional[Path] = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="wb",
                dir=str(path.parent),
                prefix=path.name + ".",
                suffix=".tmp",
                delete=False,
            ) as handle:
                temp_path = Path(handle.name)
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(str(temp_path), str(path))
        finally:
            if temp_path is not None and temp_path.exists():
                try:
                    temp_path.unlink()
                except OSError:
                    pass

    def save(self, catalog: OfficialModuleCatalog) -> None:
        payload = (json.dumps(_catalog_wire_payload(catalog), ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")
        self._atomic_write(self.cache_path, payload)
        try:
            self._atomic_write(self.backup_path, payload)
        except OSError:
            pass


class OfficialCatalogHTTPClient:
    def __init__(
        self,
        client: Optional[httpx.Client] = None,
        *,
        total_timeout: float = 120.0,
        max_redirects: int = 3,
        clock=time.monotonic,
    ):
        self._owns_client = client is None
        self.client = client or httpx.Client(
            timeout=httpx.Timeout(connect=10.0, read=30.0, write=30.0, pool=10.0),
            follow_redirects=False,
            trust_env=False,
            headers={"User-Agent": "Project-Kei-Official-Module-Catalog/1"},
        )
        self.total_timeout = total_timeout
        self.max_redirects = max_redirects
        self.clock = clock

    @staticmethod
    def _rate_limit_error(source: str, *, stage: str, retry_after: Optional[str] = None) -> OfficialCatalogError:
        return OfficialCatalogError(
            f"official {source} source is rate limited",
            code=f"official_{source}_rate_limited",
            stage=stage,
            retryable=True,
            retry_after=retry_after,
        )

    def _fetch_catalog_from(self, source: str) -> OfficialModuleCatalog:
        try:
            with self.client.stream("GET", _catalog_url(source)) as response:
                if response.status_code in {403, 429}:
                    raise self._rate_limit_error(
                        source,
                        stage="catalog_download",
                        retry_after=response.headers.get("retry-after"),
                    )
                if response.status_code != 200:
                    raise OfficialCatalogError(
                        "official catalog refresh failed",
                        code="official_catalog_refresh_failed",
                        stage="catalog_download",
                        retryable=True,
                    )
                payload = bytearray()
                for chunk in response.iter_bytes(64 * 1024):
                    payload.extend(chunk)
                    if len(payload) > MAX_CATALOG_BYTES:
                        raise OfficialCatalogError(
                            "official catalog exceeds its size limit",
                            code="official_catalog_too_large",
                            stage="catalog_download",
                        )
            return validate_official_catalog(json.loads(bytes(payload).decode("utf-8")))
        except OfficialCatalogError:
            raise
        except (UnicodeError, json.JSONDecodeError) as exc:
            raise OfficialCatalogError(
                "official catalog response is invalid",
                code="official_catalog_invalid",
                stage="catalog_validation",
            ) from exc
        except httpx.HTTPError as exc:
            raise OfficialCatalogError(
                "official catalog refresh failed",
                code="official_catalog_refresh_failed",
                stage="catalog_download",
                retryable=True,
            ) from exc

    def fetch_catalog_with_source(
        self,
        source: str = "auto",
    ) -> tuple[OfficialModuleCatalog, str]:
        sources = _source_order(source)
        last_error: Optional[OfficialCatalogError] = None
        for index, candidate in enumerate(sources):
            try:
                return self._fetch_catalog_from(candidate), candidate
            except OfficialCatalogError as exc:
                last_error = exc
                if not _transport_fallback_allowed(exc) or index == len(sources) - 1:
                    raise
        assert last_error is not None
        raise last_error

    def fetch_catalog(self, source: str = "auto") -> OfficialModuleCatalog:
        catalog, _ = self.fetch_catalog_with_source(source)
        return catalog

    @staticmethod
    def _trusted_redirect(url: str, source: str) -> str:
        parsed = urlparse(url)
        host = (parsed.hostname or "").lower()
        trusted_host = (
            host in _RELEASE_REDIRECT_HOSTS
            if source == "github"
            else host == "gitee.com"
        )
        if (
            parsed.scheme != "https"
            or not trusted_host
            or parsed.username is not None
            or parsed.password is not None
            or parsed.fragment
            or (source == "gitee" and parsed.query)
        ):
            raise OfficialCatalogError(
                f"official module redirect left the trusted {source} asset boundary",
                code="official_module_redirect_rejected",
                stage="package_download",
            )
        return url

    def _download_from_source(
        self,
        release: OfficialModuleRelease,
        destination: Path,
        source: str,
    ) -> Dict[str, Any]:
        current = (
            release.package_url
            if source == "github"
            else _gitee_package_url(release.release_tag, release.asset_name)
        )
        deadline = self.clock() + self.total_timeout
        redirects = 0
        received = 0
        digest = hashlib.sha256()
        try:
            while True:
                if self.clock() > deadline:
                    raise OfficialCatalogError(
                        "official module download timed out",
                        code="official_module_download_timeout",
                        stage="package_download",
                        retryable=True,
                        received_bytes=received,
                    )
                with self.client.stream("GET", current) as response:
                    if response.status_code in _REDIRECT_STATUSES:
                        location = response.headers.get("location")
                        if not location or redirects >= self.max_redirects:
                            raise OfficialCatalogError(
                                "official module redirect policy rejected the response",
                                code="official_module_redirect_rejected",
                                stage="package_download",
                                received_bytes=received,
                            )
                        current = self._trusted_redirect(urljoin(current, location), source)
                        redirects += 1
                        continue
                    if response.status_code in {403, 429}:
                        error = self._rate_limit_error(
                            source,
                            stage="package_download",
                            retry_after=response.headers.get("retry-after"),
                        )
                        error.received_bytes = received
                        raise error
                    if response.status_code != 200:
                        raise OfficialCatalogError(
                            "official module download failed",
                            code="official_module_download_failed",
                            stage="package_download",
                            retryable=True,
                            received_bytes=received,
                        )
                    declared = response.headers.get("content-length")
                    if declared is not None:
                        try:
                            if int(declared) != release.package_size:
                                raise ValueError
                        except ValueError as exc:
                            raise OfficialCatalogError(
                                "official module response size does not match the catalog",
                                code="official_module_size_mismatch",
                                stage="package_download",
                            ) from exc
                    with Path(destination).open("xb") as output:
                        for chunk in response.iter_bytes(1024 * 1024):
                            received += len(chunk)
                            if received > release.package_size or received > MAX_OFFICIAL_PACKAGE_BYTES:
                                raise OfficialCatalogError(
                                    "official module response exceeds its catalog size",
                                    code="official_module_size_mismatch",
                                    stage="package_download",
                                    received_bytes=received,
                                )
                            output.write(chunk)
                            digest.update(chunk)
                break
        except OfficialCatalogError:
            Path(destination).unlink(missing_ok=True)
            raise
        except (httpx.HTTPError, OSError) as exc:
            Path(destination).unlink(missing_ok=True)
            raise OfficialCatalogError(
                "official module download failed",
                code="official_module_download_failed",
                stage="package_download",
                retryable=True,
                received_bytes=received,
            ) from exc
        if received != release.package_size:
            Path(destination).unlink(missing_ok=True)
            raise OfficialCatalogError(
                "official module download was truncated",
                code="official_module_size_mismatch",
                stage="package_download",
                retryable=True,
                received_bytes=received,
            )
        if digest.hexdigest() != release.package_sha256:
            Path(destination).unlink(missing_ok=True)
            raise OfficialCatalogError(
                "official module SHA-256 does not match the catalog",
                code="official_module_integrity_mismatch",
                stage="package_download",
                received_bytes=received,
            )
        return {
            "received_bytes": received,
            "sha256": digest.hexdigest(),
            "redirects": redirects,
            "source": source,
        }

    def download(
        self,
        release: OfficialModuleRelease,
        destination: Path,
        source: str = "auto",
    ) -> Dict[str, Any]:
        sources = _source_order(source)
        last_error: Optional[OfficialCatalogError] = None
        for index, candidate in enumerate(sources):
            try:
                return self._download_from_source(release, destination, candidate)
            except OfficialCatalogError as exc:
                last_error = exc
                Path(destination).unlink(missing_ok=True)
                if not _transport_fallback_allowed(exc) or index == len(sources) - 1:
                    raise
        assert last_error is not None
        raise last_error

    def close(self) -> None:
        if self._owns_client:
            self.client.close()


def validate_release_manifest(archive: Path, release: OfficialModuleRelease, core_version: str = CORE_VERSION) -> None:
    try:
        with zipfile.ZipFile(str(archive), "r") as source:
            matches = [info for info in source.infolist() if info.filename.lower().rstrip("/") == "manifest.json"]
            if len(matches) != 1 or matches[0].filename != "manifest.json" or matches[0].is_dir():
                raise OfficialCatalogError(
                    "official module must contain one root manifest.json",
                    code="official_module_manifest_mismatch",
                    stage="package_validation",
                )
            raw = source.read(matches[0])
    except OfficialCatalogError:
        raise
    except (OSError, zipfile.BadZipFile, KeyError) as exc:
        raise OfficialCatalogError(
            "official module ZIP is unreadable",
            code="official_module_archive_invalid",
            stage="package_validation",
        ) from exc
    if hashlib.sha256(raw).hexdigest() != release.manifest_sha256:
        raise OfficialCatalogError(
            "official module manifest digest does not match the catalog",
            code="official_module_manifest_mismatch",
            stage="package_validation",
        )
    try:
        manifest = validate_manifest(json.loads(raw.decode("utf-8")), core_version)
    except Exception as exc:
        raise OfficialCatalogError(
            "official module manifest is invalid",
            code="official_module_manifest_mismatch",
            stage="package_validation",
        ) from exc
    comparisons: Iterable[tuple[bool, str]] = (
        (manifest.id == release.module_id, "module_id"),
        (manifest.name == release.name, "name"),
        (manifest.version == release.version, "version"),
        (manifest.core_compatibility == release.core_compatibility, "core_compatibility"),
        (manifest.dependencies == release.dependencies, "dependencies"),
        (manifest.optional_dependencies == release.optional_dependencies, "optional_dependencies"),
        (manifest.runtime_requirements == release.runtime_requirements, "runtime_requirements"),
        (manifest.conflicts == release.conflicts, "conflicts"),
        (manifest.permissions == release.permissions, "permissions"),
        (manifest.requires_restart == release.requires_restart, "requires_restart"),
    )
    mismatch = next((field for accepted, field in comparisons if not accepted), None)
    if mismatch:
        raise OfficialCatalogError(
            f"official module manifest {mismatch} does not match the catalog",
            code="official_module_manifest_mismatch",
            stage="package_validation",
        )


__all__ = [
    "MAX_OFFICIAL_PACKAGE_BYTES",
    "OFFICIAL_CATALOG_URL",
    "OFFICIAL_DOWNLOAD_SOURCES",
    "OFFICIAL_GITEE_CATALOG_URL",
    "OFFICIAL_GITEE_OWNER",
    "OFFICIAL_OWNER",
    "OFFICIAL_REPOSITORY",
    "OfficialCatalogError",
    "OfficialCatalogHTTPClient",
    "OfficialCatalogStore",
    "OfficialModuleCatalog",
    "OfficialModuleRelease",
    "normalize_official_download_source",
    "validate_official_catalog",
    "validate_release_manifest",
]
