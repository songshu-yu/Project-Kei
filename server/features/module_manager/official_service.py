"""Application seam for explicit official catalog refresh and Release installation."""

from __future__ import annotations

import tempfile
import threading
from pathlib import Path
from typing import Any, Dict

from core.modules.exceptions import (
    ManifestValidationError,
    ModuleConflictError,
    ModuleNotFoundError,
    ModuleOperationError,
    PackageValidationError,
    RegistryError,
)
from core.modules.manager import ModuleManager
from core.modules.manifest import version_satisfies
from core.modules.official_catalog import (
    OFFICIAL_CATALOG_URL,
    OFFICIAL_DOWNLOAD_SOURCES,
    OFFICIAL_GITEE_CATALOG_URL,
    OFFICIAL_GITEE_OWNER,
    OFFICIAL_OWNER,
    OFFICIAL_PUBLISHER,
    OFFICIAL_REPOSITORY,
    OfficialCatalogError,
    OfficialCatalogHTTPClient,
    OfficialCatalogStore,
    OfficialModuleRelease,
    validate_release_manifest,
)


class OfficialModuleService:
    def __init__(
        self,
        manager: ModuleManager,
        store: OfficialCatalogStore,
        http_client: OfficialCatalogHTTPClient,
    ):
        self.manager = manager
        self.store = store
        self.http_client = http_client
        self._lock = threading.RLock()

    def _catalog_view(
        self,
        *,
        refresh_status: str = "not_requested",
        refresh_source: str = "none",
    ) -> Dict[str, Any]:
        catalog, cache_source = self.store.load()
        snapshot = self.manager.snapshot()
        modules = []
        for release in catalog.modules:
            item = release.to_dict()
            installed = snapshot.get(release.module_id, {})
            item.update({
                "compatible": version_satisfies(self.manager.core_version, release.core_compatibility),
                "installed_version": installed.get("installed_version"),
                "enabled": bool(installed.get("enabled")),
                "configuration_ready": bool(installed.get("configuration_ready")),
                "restart_required": bool(installed.get("restart_required")),
                "last_operation": installed.get("last_operation"),
                "available_actions": (
                    installed.get("available_actions")
                    if installed else ["install_official"]
                ),
            })
            modules.append(item)
        return {
            "schema_version": 1,
            "source": {
                "publisher": OFFICIAL_PUBLISHER,
                "owner": OFFICIAL_OWNER,
                "repository": OFFICIAL_REPOSITORY,
                "catalog_url": OFFICIAL_CATALOG_URL,
                "catalog_mirrors": {
                    "github": OFFICIAL_CATALOG_URL,
                    "gitee": OFFICIAL_GITEE_CATALOG_URL,
                },
                "download_sources": list(OFFICIAL_DOWNLOAD_SOURCES),
                "anonymous_only": True,
            },
            "generated_at": catalog.generated_at,
            "cache_source": cache_source,
            "refresh_status": refresh_status,
            "refresh_source": refresh_source,
            "network_accessed": refresh_status != "not_requested",
            "modules": modules,
        }

    def list_catalog(self) -> Dict[str, Any]:
        return self._catalog_view()

    def refresh_catalog(self, download_source: str = "auto") -> Dict[str, Any]:
        with self._lock:
            catalog, actual_source = self.http_client.fetch_catalog_with_source(download_source)
            self.store.save(catalog)
            return self._catalog_view(
                refresh_status="success",
                refresh_source=actual_source,
            )

    def test_connectivity(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "schema_version": 1,
                "network_accessed": True,
                "cache_written": False,
                "results": [
                    self.http_client.probe_catalog(source)
                    for source in ("github", "gitee")
                ],
            }

    def _release(self, module_id: str, version: str) -> OfficialModuleRelease:
        catalog, _ = self.store.load()
        for release in catalog.modules:
            if release.module_id == module_id and release.version == version:
                return release
        raise OfficialCatalogError(
            "requested module version is not present in the official catalog",
            code="official_module_not_found",
            stage="catalog_selection",
        )

    @staticmethod
    def _confirm(release: OfficialModuleRelease, confirmation: str) -> None:
        expected = f"{release.module_id}@{release.version}"
        if confirmation != expected:
            raise OfficialCatalogError(
                f"confirmation must exactly match {expected}",
                code="official_module_confirmation_required",
                stage="confirmation",
            )

    @staticmethod
    def _metadata(release: OfficialModuleRelease) -> Dict[str, str]:
        return {
            "source": "official_github_release",
            "publisher": OFFICIAL_PUBLISHER,
            "owner": OFFICIAL_OWNER,
            "repository": OFFICIAL_REPOSITORY,
            "release_tag": release.release_tag,
            "asset_name": release.asset_name,
            "manifest_sha256": release.manifest_sha256,
        }

    @staticmethod
    def _raise_manager_error(exc: Exception, action: str) -> None:
        if isinstance(exc, ModuleConflictError):
            code = "official_module_conflict"
            retryable = False
        elif isinstance(exc, ModuleNotFoundError):
            code = "official_module_not_installed"
            retryable = False
        elif isinstance(exc, (ManifestValidationError, PackageValidationError)):
            code = "official_module_package_rejected"
            retryable = False
        elif isinstance(exc, (RegistryError, ModuleOperationError)):
            code = "official_module_install_failed"
            retryable = True
        else:
            raise exc
        raise OfficialCatalogError(
            str(exc),
            code=code,
            stage=action,
            retryable=retryable,
        ) from exc

    def _download_and_apply(
        self,
        release: OfficialModuleRelease,
        *,
        update: bool,
        download_source: str,
    ) -> Dict[str, Any]:
        with tempfile.TemporaryDirectory(prefix="project-kei-official-module-") as temp:
            archive = Path(temp) / "package.zip"
            progress = self.http_client.download(
                release,
                archive,
                download_source,
            )
            validate_release_manifest(archive, release, self.manager.core_version)
            try:
                if update:
                    result = self.manager.update(
                        release.module_id,
                        archive,
                        release.package_sha256,
                        version_metadata=self._metadata(release),
                    )
                    action = "update_official"
                else:
                    result = self.manager.install(
                        archive,
                        release.package_sha256,
                        expected_module_id=release.module_id,
                        version_metadata=self._metadata(release),
                    )
                    action = "install_official"
            except Exception as exc:
                self._raise_manager_error(
                    exc,
                    "official_update" if update else "official_install",
                )
        result["official_operation"] = {
            "action": action,
            "status": "completed",
            "phase": "installed",
            "received_bytes": progress["received_bytes"],
            "total_bytes": release.package_size,
            "sha256": progress["sha256"],
            "source": (
                f"{progress['source']}:"
                f"{OFFICIAL_GITEE_OWNER if progress['source'] == 'gitee' else OFFICIAL_OWNER}/"
                f"{OFFICIAL_REPOSITORY}@{release.release_tag}"
            ),
            "download_source": progress["source"],
        }
        return result

    def install(
        self,
        module_id: str,
        version: str,
        confirmation: str,
        download_source: str = "auto",
    ) -> Dict[str, Any]:
        with self._lock:
            release = self._release(module_id, version)
            self._confirm(release, confirmation)
            return self._download_and_apply(
                release,
                update=False,
                download_source=download_source,
            )

    def update(
        self,
        module_id: str,
        version: str,
        confirmation: str,
        download_source: str = "auto",
    ) -> Dict[str, Any]:
        with self._lock:
            release = self._release(module_id, version)
            self._confirm(release, confirmation)
            return self._download_and_apply(
                release,
                update=True,
                download_source=download_source,
            )

    def rollback(self, module_id: str, version: str, confirmation: str) -> Dict[str, Any]:
        with self._lock:
            release = self._release(module_id, version)
            self._confirm(release, confirmation)
            try:
                result = self.manager.rollback(
                    module_id,
                    expected_version=version,
                    expected_package_sha256=release.package_sha256,
                    expected_manifest_sha256=release.manifest_sha256,
                    require_official=True,
                )
            except Exception as exc:
                self._raise_manager_error(exc, "official_rollback")
            result["official_operation"] = {
                "action": "rollback_official",
                "status": "completed",
                "phase": "rolled_back",
                "received_bytes": 0,
                "total_bytes": 0,
                "sha256": release.package_sha256,
                "source": f"github:{OFFICIAL_OWNER}/{OFFICIAL_REPOSITORY}@{release.release_tag}",
            }
            return result


__all__ = ["OfficialModuleService"]
