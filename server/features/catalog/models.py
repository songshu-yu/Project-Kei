"""Backward-compatible response models for the Project Kei module catalog."""

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class ModuleInfo(BaseModel):
    key: str
    label: str
    task_id: str
    task_file: str
    process: str
    current_endpoints: List[str]
    target_namespace: str
    migration_status: str
    managed: bool = False
    source: str = "legacy_builtin"
    type: str = "in_process"
    required: bool = False
    install_status: str = "enabled"
    installed_version: Optional[str] = None
    available_versions: List[str] = Field(default_factory=list)
    enabled: bool = True
    configuration_ready: bool = True
    sidecar_readiness: Optional[Dict[str, Any]] = None
    dependencies: List[str] = Field(default_factory=list)
    optional_dependencies: List[str] = Field(default_factory=list)
    conflicts: List[str] = Field(default_factory=list)
    permissions: List[str] = Field(default_factory=list)
    requires_restart: bool = False
    restart_required: bool = False
    dashboard_entrypoint: Optional[str] = None
    dashboard_entrypoint_path: Optional[str] = None
    api_namespaces: List[str] = Field(default_factory=list)
    legacy_endpoints: List[str] = Field(default_factory=list)
    previous_version: Optional[str] = None
    last_operation: Optional[Dict[str, Any]] = None
    data_policy: str = "preserve_on_uninstall"
    available_actions: List[str] = Field(default_factory=list)
    package_source: Optional[str] = None
    release: Optional[Dict[str, Any]] = None
    data_owner: Optional[str] = None
    dashboard_surface: Optional[str] = None
    secret_owner: Optional[str] = None
    network_side_effects: Optional[str] = None
    failure_mode: Optional[str] = None


class ModuleCatalogResponse(BaseModel):
    architecture: str
    catalog_version: int
    module_manager_error: Optional[str] = None
    modules: List[ModuleInfo]
