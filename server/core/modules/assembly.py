"""Atomic dependency-ordered assembly for installed modules."""

from __future__ import annotations

from typing import Any, Dict, List

from .exceptions import SidecarReadinessError
from .loader import InProcessModuleLoader


class ModuleActivationCoordinator:
    """Use one preflighted order for in-process and sidecar activation."""

    def __init__(self, manager: Any, loader: InProcessModuleLoader):
        self._manager = manager
        self._loader = loader
        self._active: List[Dict[str, Any]] = []

    def activate(self, app: Any) -> List[Dict[str, str]]:
        descriptors = self._manager.enabled_activation_descriptors()
        activated: List[Dict[str, Any]] = []
        results: List[Dict[str, str]] = []
        for descriptor in descriptors:
            module_id = descriptor["module_id"]
            if descriptor["manifest_object"].type == "in_process":
                result = self._loader.load_one(app, descriptor)
                if result["status"] not in {"loaded", "already_loaded"}:
                    rollback = self._rollback(app, activated)
                    self._active = []
                    return rollback + [{
                        "module_id": module_id,
                        "status": "failed",
                        "error": "module registration failed",
                    }]
                results.append(result)
            else:
                adapter = self._manager.resolve_sidecar_adapter(
                    descriptor["manifest_object"].sidecar.adapter
                )
                if getattr(adapter, "start_automatically", True) is False:
                    results.append({
                        "module_id": module_id,
                        "status": "waiting_manual_start",
                    })
                    activated.append(descriptor)
                    continue
                try:
                    self._manager.start_sidecar_descriptor(descriptor)
                except SidecarReadinessError as exc:
                    results.append({
                        "module_id": module_id,
                        "status": "needs_configuration",
                        "error": exc.readiness.code,
                    })
                    continue
                except Exception:
                    rollback = self._rollback(app, activated)
                    self._active = []
                    return rollback + [{
                        "module_id": module_id,
                        "status": "failed",
                        "error": "sidecar startup failed",
                    }]
                results.append({"module_id": module_id, "status": "started"})
            activated.append(descriptor)
        self._active = list(activated)
        self._manager.record_load_results(
            result
            for result in results
            if result["status"] in {"loaded", "already_loaded"}
        )
        return results

    def _rollback(
        self,
        app: Any,
        descriptors: List[Dict[str, Any]],
    ) -> List[Dict[str, str]]:
        results: List[Dict[str, str]] = []
        for descriptor in reversed(descriptors):
            module_id = descriptor["module_id"]
            try:
                if descriptor["manifest_object"].type == "in_process":
                    unloaded = self._loader.unload_one(app, module_id)
                    if unloaded["status"] == "failed":
                        results.append({
                            "module_id": module_id,
                            "status": "rollback_failed",
                        })
                        continue
                else:
                    self._manager.stop_sidecar_descriptor(descriptor)
                results.append({"module_id": module_id, "status": "rolled_back"})
            except Exception:
                results.append({
                    "module_id": module_id,
                    "status": "rollback_failed",
                })
        return results

    def deactivate(self, app: Any) -> List[Dict[str, str]]:
        results = self._rollback(app, self._active)
        for result in results:
            if result["status"] == "rolled_back":
                result["status"] = "stopped"
        self._active = []
        return results

    async def deactivate_async(self, app: Any) -> List[Dict[str, str]]:
        """Reverse activation while awaiting module-owned async cleanup."""

        results: List[Dict[str, str]] = []
        for descriptor in reversed(self._active):
            module_id = descriptor["module_id"]
            try:
                if descriptor["manifest_object"].type == "in_process":
                    unloaded = await self._loader.unload_one_async(app, module_id)
                    if unloaded["status"] == "failed":
                        results.append({
                            "module_id": module_id,
                            "status": "rollback_failed",
                        })
                        continue
                else:
                    self._manager.stop_sidecar_descriptor(descriptor)
                results.append({"module_id": module_id, "status": "stopped"})
            except Exception:
                results.append({
                    "module_id": module_id,
                    "status": "rollback_failed",
                })
        self._active = []
        return results
