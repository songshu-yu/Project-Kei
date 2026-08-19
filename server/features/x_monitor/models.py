"""PK-120 target classification models shared by X cache and HTTP layers."""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from typing import Literal, Mapping

from pydantic import BaseModel


STANDARD_GROUP = "twitter_users"
INFORMATION_GAP_GROUP = "money_twitter_users"
_HANDLE_RE = re.compile(r"[A-Za-z0-9_]{1,30}")
XPostQueryMode = Literal["day", "since"]


def normalize_handle(value: object) -> str:
    result = str(value or "").strip().lstrip("@")
    if not _HANDLE_RE.fullmatch(result):
        raise ValueError("X username must contain only letters, numbers, or underscores")
    return result


@dataclass(frozen=True)
class XTarget:
    username: str
    config_groups: tuple[str, ...]

    @property
    def key(self) -> str:
        return self.username.casefold()


class XPostQueryRequest(BaseModel):
    username: str
    mode: XPostQueryMode
    date: date

    class Config:
        extra = "forbid"


def classify_x_targets(source_config_snapshot: Mapping[str, object]) -> tuple[XTarget, ...]:
    """Dedupe shared X targets without losing either configuration group."""
    targets: dict[str, dict[str, object]] = {}
    order: list[str] = []
    for group in (STANDARD_GROUP, INFORMATION_GAP_GROUP):
        values = source_config_snapshot.get(group, [])
        if not isinstance(values, (list, tuple)):
            raise ValueError(f"{group} must be a list")
        for value in values:
            username = normalize_handle(value)
            key = username.casefold()
            if key not in targets:
                targets[key] = {"username": username, "groups": []}
                order.append(key)
            groups = targets[key]["groups"]
            if isinstance(groups, list) and group not in groups:
                groups.append(group)
    return tuple(
        XTarget(str(targets[key]["username"]), tuple(targets[key]["groups"]))
        for key in order
    )


__all__ = [
    "INFORMATION_GAP_GROUP",
    "STANDARD_GROUP",
    "XTarget",
    "XPostQueryMode",
    "XPostQueryRequest",
    "classify_x_targets",
    "normalize_handle",
]
