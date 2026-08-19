"""HTTP request models for local module lifecycle operations."""

from pydantic import BaseModel


class InstallModuleRequest(BaseModel):
    package_path: str
    expected_sha256: str


class PurgeModuleDataRequest(BaseModel):
    confirmation: str


class OfficialModuleRequest(BaseModel):
    version: str
    confirmation: str
