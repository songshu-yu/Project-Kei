"""Single source of truth for identities and API space owned by Project Kei Core."""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Mapping, Optional, Tuple


@dataclass(frozen=True)
class CoreModuleContract:
    module_id: str
    api_namespaces: Tuple[str, ...]
    required: bool = True
    managed: bool = False
    source: str = "core_builtin"


CORE_MODULE_CONTRACTS: Mapping[str, CoreModuleContract] = MappingProxyType({
    "catalog": CoreModuleContract(
        module_id="catalog",
        api_namespaces=("/api/v1/modules",),
    ),
    "module_manager": CoreModuleContract(
        module_id="module_manager",
        api_namespaces=("/api/v1/modules",),
    ),
    "dashboard": CoreModuleContract(
        module_id="dashboard",
        api_namespaces=("/api/v1/dashboard",),
    ),
})

CORE_RESERVED_MODULE_IDS = frozenset(CORE_MODULE_CONTRACTS)
CORE_RESERVED_API_NAMESPACES = frozenset(
    namespace
    for contract in CORE_MODULE_CONTRACTS.values()
    for namespace in contract.api_namespaces
)


def core_contract(module_id: str) -> Optional[CoreModuleContract]:
    return CORE_MODULE_CONTRACTS.get(module_id)


def namespaces_overlap(left: str, right: str) -> bool:
    """Treat a namespace and every slash-delimited child as one owned boundary."""
    left = left.rstrip("/")
    right = right.rstrip("/")
    return left == right or left.startswith(right + "/") or right.startswith(left + "/")


def conflicting_core_namespace(namespace: str) -> Optional[str]:
    for reserved in sorted(CORE_RESERVED_API_NAMESPACES):
        if namespaces_overlap(namespace, reserved):
            return reserved
    return None
