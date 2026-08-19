"""Installable papers module registration and host-provider seam."""

from __future__ import annotations

from pathlib import Path
from types import MappingProxyType
from typing import Any

from core.intel_contracts import CollectorRegistry

from .arxiv import ArxivCollector
from .collectors import CrossrefCollector, SemanticScholarCollector
from .domain import PAPER_SOURCE_IDS
from .http import (
    default_paper_http_runtime,
    install_default_paper_http_runtime,
    uninstall_default_paper_http_runtime,
)
from .router import create_papers_router
from .service import PaperCollectorCoordinator


OWNED_ROUTE_PATHS = frozenset(
    {"/api/v1/papers/today", "/api/v1/papers/refresh"}
)


def _default_cache_dir() -> Path:
    for parent in Path(__file__).resolve().parents:
        if parent.name == "server":
            return parent / "data" / "cache" / "arxiv"
        if parent.name == "runtime":
            return parent.parent / "data" / "modules" / "papers" / "cache" / "arxiv"
    return Path(__file__).resolve().parent / ".papers-cache" / "arxiv"


def _provider_value(provider: Any, default: Any) -> Any:
    if provider is None:
        return default
    value = provider()
    return default if value is None else value


def _existing_owned_routes(app: Any) -> set[str]:
    return {
        str(getattr(route, "path", ""))
        for route in getattr(app, "routes", ())
        if str(getattr(route, "path", "")) in OWNED_ROUTE_PATHS
    }


def _runtime(app: Any) -> tuple[Any, bool]:
    runtime = getattr(app.state, "papers_http_runtime", None)
    if runtime is None:
        runtime = default_paper_http_runtime()
        app.state.papers_http_runtime = runtime
        owned = True
    else:
        owned = bool(
            getattr(app.state, "papers_http_runtime_owned_by_module", False)
        )
    for member in ("get", "limiter", "aclose"):
        if not callable(getattr(runtime, member, None)):
            raise TypeError("papers_http_runtime does not implement the shared runtime contract")
    install_default_paper_http_runtime(runtime)
    app.state.papers_http_runtime_owned_by_module = owned
    return runtime, owned


def _registry(app: Any) -> Any:
    registry = getattr(app.state, "intel_collector_registry", None)
    if registry is None:
        registry = CollectorRegistry()
        app.state.intel_collector_registry = registry
    for member in ("register", "unregister", "get"):
        if not callable(getattr(registry, member, None)):
            raise TypeError("intel_collector_registry does not implement the Core contract")
    return registry


async def unregister(app: Any) -> None:
    """Idempotently detach collectors and close only a package-owned runtime."""
    if getattr(app.state, "papers_module_closed", False):
        return
    app.state.papers_module_closed = True
    registry = getattr(app.state, "intel_collector_registry", None)
    collectors = getattr(app.state, "papers_collectors", {})
    if registry is not None:
        for source_id in PAPER_SOURCE_IDS:
            collector = collectors.get(source_id) if hasattr(collectors, "get") else None
            if collector is not None:
                registry.unregister(source_id, collector=collector)
    if bool(getattr(app.state, "papers_http_runtime_owned_by_module", False)):
        runtime = getattr(app.state, "papers_http_runtime", None)
        if runtime is not None:
            await runtime.aclose()
    runtime = getattr(app.state, "papers_http_runtime", None)
    if runtime is not None:
        uninstall_default_paper_http_runtime(runtime)
    app.state.papers_module_registered = False


def register(app: Any) -> None:
    """Register three collectors, one shared runtime, and package-owned routes."""
    if getattr(app.state, "papers_module_registered", False):
        return
    duplicates = _existing_owned_routes(app)
    if duplicates:
        raise RuntimeError(
            "papers routes already registered: %s" % ", ".join(sorted(duplicates))
        )

    runtime, runtime_owned = _runtime(app)
    registry = _registry(app)
    app.state.papers_http_runtime_owned_by_module = runtime_owned
    app.state.papers_module_closed = False
    async def close_module() -> None:
        await unregister(app)
    app.state.papers_module_close = close_module
    app.add_event_handler("shutdown", close_module)
    queries = _provider_value(
        getattr(app.state, "papers_arxiv_queries_provider", None),
        (),
    )
    if not isinstance(queries, (list, tuple)):
        raise TypeError("papers_arxiv_queries_provider must return a sequence")
    journals = _provider_value(
        getattr(app.state, "papers_journals_provider", None),
        (),
    )
    if not isinstance(journals, (list, tuple)):
        raise TypeError("papers_journals_provider must return a sequence")
    clock = getattr(app.state, "papers_clock", None)
    collector_options: dict[str, Any] = {"runtime": runtime}
    if callable(clock):
        collector_options["clock"] = clock
    key_provider = getattr(
        app.state,
        "semantic_scholar_api_key_provider",
        lambda: "",
    )
    if not callable(key_provider):
        raise TypeError("semantic_scholar_api_key_provider must be callable")

    configured_cache_dir = getattr(app.state, "papers_arxiv_cache_dir", None)
    cache_dir = Path(configured_cache_dir) if configured_cache_dir is not None else (
        _default_cache_dir()
    )
    arxiv = ArxivCollector(
        queries=queries,
        cache_dir=cache_dir,
        **collector_options,
    )
    crossref = CrossrefCollector(
        allowed_journals=journals,
        **collector_options,
    )
    semantic = SemanticScholarCollector(
        api_key_provider=key_provider,
        **collector_options,
    )
    collectors = {
        "arxiv": arxiv,
        "crossref": crossref,
        "semantic": semantic,
    }
    coordinator = PaperCollectorCoordinator(
        collectors,
        abstract_resolver=semantic,
        http_runtime=runtime,
        **({"clock": clock} if callable(clock) else {}),
    )

    registered: list[tuple[str, Any]] = []
    try:
        for source_id in PAPER_SOURCE_IDS:
            collector = collectors[source_id]
            registry.register(collector)
            registered.append((source_id, collector))
    except Exception:
        for source_id, collector in reversed(registered):
            registry.unregister(source_id, collector=collector)
        uninstall_default_paper_http_runtime(runtime)
        raise

    try:
        app.include_router(
            create_papers_router(
                getattr(app.state, "papers_today_provider", None),
                getattr(app.state, "papers_refresh_provider", None),
                local_request_guard=getattr(
                    app.state,
                    "papers_local_request_guard",
                    None,
                ),
            )
        )
    except Exception:
        for source_id, collector in reversed(registered):
            registry.unregister(source_id, collector=collector)
        uninstall_default_paper_http_runtime(runtime)
        raise

    app.state.papers_collectors = MappingProxyType(collectors)
    app.state.papers_collector_coordinator = coordinator
    app.state.papers_module_registered = True

__all__ = ["OWNED_ROUTE_PATHS", "register", "unregister"]
