"""HTTP request models for local module lifecycle operations."""

from typing import Literal

from pydantic import BaseModel


class InstallModuleRequest(BaseModel):
    package_path: str
    expected_sha256: str


class PurgeModuleDataRequest(BaseModel):
    confirmation: str


class OfficialModuleRequest(BaseModel):
    version: str
    confirmation: str
    download_source: Literal["auto", "github", "gitee"] = "auto"


class OfficialCatalogRefreshRequest(BaseModel):
    download_source: Literal["auto", "github", "gitee"] = "auto"
