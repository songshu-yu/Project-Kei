"""Restart-time loader for enabled in-process module packages."""

from __future__ import annotations

import asyncio
import importlib.util
import inspect
import sys
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional, Tuple

from .exceptions import ModuleOperationError
from .manifest import ModuleManifest


def _clear_import_tree(import_name: str) -> None:
    """Remove one generated package and every child imported beneath it."""

    prefix = import_name + "."
    for name in tuple(sys.modules):
        if name == import_name or name.startswith(prefix):
            sys.modules.pop(name, None)


def _run_or_queue_async_cleanup(app: Any, value: Any) -> None:
    if not inspect.isawaitable(value):
        return
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        asyncio.run(value)
        return
    state = getattr(app, "state", None)
    if state is None:
        close = getattr(value, "close", None)
        if callable(close):
            close()
        return
    pending = getattr(state, "_module_cleanup_awaitables", None)
    if not isinstance(pending, list):
        pending = []
        setattr(state, "_module_cleanup_awaitables", pending)
    pending.append(value)


def _resolve_entrypoint(
    package_root: Path,
    manifest: ModuleManifest,
) -> Tuple[Callable[[Any], Any], Optional[Callable[[Any], Any]], str]:
    if not manifest.entrypoint:
        raise ModuleOperationError("module %s has no in-process entrypoint" % manifest.id)
    parts = manifest.entrypoint.split(".")
    callable_name = parts[-1]
    module_parts = parts[:-1]
    module_file = package_root.joinpath(*module_parts).with_suffix(".py")
    package_file = package_root.joinpath(*module_parts, "__init__.py")
    if module_file.is_file():
        source_path = module_file
        search_locations = None
    elif package_file.is_file():
        source_path = package_file
        search_locations = [str(package_file.parent)]
    else:
        raise ModuleOperationError("entrypoint module file is missing for %s" % manifest.id)

    import_name = "_project_kei_module_%s_%s" % (
        manifest.id,
        manifest.version.replace(".", "_").replace("-", "_"),
    )
    spec = importlib.util.spec_from_file_location(
        import_name,
        str(source_path),
        submodule_search_locations=search_locations,
    )
    if spec is None or spec.loader is None:
        raise ModuleOperationError("could not create an import spec for %s" % manifest.id)
    module = importlib.util.module_from_spec(spec)
    sys.modules[import_name] = module
    try:
        spec.loader.exec_module(module)
    except Exception as exc:
        _clear_import_tree(import_name)
        raise ModuleOperationError(
            "entrypoint import failed for %s: %s" % (manifest.id, type(exc).__name__)
        ) from exc
    register = getattr(module, callable_name, None)
    if not callable(register) or callable_name.startswith("_"):
        _clear_import_tree(import_name)
        raise ModuleOperationError("entrypoint callable is missing for %s" % manifest.id)
    unregister = getattr(module, "unregister", None)
    if unregister is not None and (
        not callable(unregister) or getattr(unregister, "__name__", "").startswith("_")
    ):
        unregister = None
    return register, unregister, import_name


class InProcessModuleLoader:
    """Load enabled modules once while the FastAPI application is assembled."""

    def __init__(self):
        self._loaded = set()
        self._registrations: Dict[str, Dict[str, Any]] = {}

    def load_one(self, app: Any, descriptor: Dict[str, Any]) -> Dict[str, str]:
        """Register one preflighted module, cleaning partial routes on failure."""

        module_id = descriptor["manifest"]["id"]
        if module_id in self._loaded:
            return {"module_id": module_id, "status": "already_loaded"}
        routes_before = list(getattr(app.router, "routes", ()))
        unregister = None
        import_name = None
        try:
            manifest = descriptor["manifest_object"]
            register, unregister, import_name = _resolve_entrypoint(
                Path(descriptor["package_root"]),
                manifest,
            )
            register(app)
            self._loaded.add(module_id)
            self._registrations[module_id] = {
                "unregister": unregister,
                "import_name": import_name,
                "routes_before": routes_before,
            }
            return {"module_id": module_id, "status": "loaded"}
        except Exception as exc:
            if callable(unregister):
                try:
                    _run_or_queue_async_cleanup(app, unregister(app))
                except Exception:
                    pass
            if hasattr(app.router, "routes"):
                app.router.routes[:] = routes_before
            if import_name:
                _clear_import_tree(import_name)
            return {
                "module_id": module_id,
                "status": "failed",
                "error": "%s: %s" % (type(exc).__name__, str(exc)),
            }

    def unload_one(self, app: Any, module_id: str) -> Dict[str, str]:
        """Undo one successful registration during reverse-topology shutdown."""

        registration = self._registrations.pop(module_id, None)
        if registration is None:
            self._loaded.discard(module_id)
            return {"module_id": module_id, "status": "not_loaded"}
        error = None
        unregister = registration.get("unregister")
        if callable(unregister):
            try:
                _run_or_queue_async_cleanup(app, unregister(app))
            except Exception as exc:
                error = type(exc).__name__
        if hasattr(app.router, "routes"):
            app.router.routes[:] = registration["routes_before"]
        import_name = registration.get("import_name")
        if import_name:
            _clear_import_tree(import_name)
        self._loaded.discard(module_id)
        if error:
            return {"module_id": module_id, "status": "failed", "error": error}
        return {"module_id": module_id, "status": "unloaded"}

    async def unload_one_async(self, app: Any, module_id: str) -> Dict[str, str]:
        """Async shutdown variant that also awaits module-owned cleanup."""

        registration = self._registrations.pop(module_id, None)
        if registration is None:
            self._loaded.discard(module_id)
            return {"module_id": module_id, "status": "not_loaded"}
        error = None
        unregister = registration.get("unregister")
        if callable(unregister):
            try:
                result = unregister(app)
                if inspect.isawaitable(result):
                    await result
            except Exception as exc:
                error = type(exc).__name__
        if hasattr(app.router, "routes"):
            app.router.routes[:] = registration["routes_before"]
        import_name = registration.get("import_name")
        if import_name:
            _clear_import_tree(import_name)
        self._loaded.discard(module_id)
        if error:
            return {"module_id": module_id, "status": "failed", "error": error}
        return {"module_id": module_id, "status": "unloaded"}

    def rollback(self, app: Any, module_ids: Iterable[str]) -> List[Dict[str, str]]:
        return [self.unload_one(app, module_id) for module_id in reversed(list(module_ids))]

    def load(self, app: Any, descriptors: Iterable[Dict[str, Any]]) -> List[Dict[str, str]]:
        results = []
        for descriptor in descriptors:
            results.append(self.load_one(app, descriptor))
        return results
