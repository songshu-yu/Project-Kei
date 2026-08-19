"""HTTP models for the PK-130 versioned profile-cache boundary."""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class BilibiliProfileResolveRequest(BaseModel):
    uid: Optional[int] = Field(default=None, gt=0)
    refresh: bool = False


class BilibiliCredentialUpdate(BaseModel):
    sessdata: str = Field(min_length=1, max_length=4096)
    bili_jct: str = Field(min_length=1, max_length=4096)
    buvid3: str = Field(min_length=1, max_length=4096)

    class Config:
        extra = "forbid"


__all__ = ["BilibiliCredentialUpdate", "BilibiliProfileResolveRequest"]
