"""Public PK-132 GitHub intelligence Collector boundary."""

from .collector import GitHubCollector, GitHubCollectorSettings
from .provider import (
    COLLECTOR_STATE_ATTRIBUTE,
    REGISTRY_STATE_ATTRIBUTE,
    register,
)

__all__ = [
    "COLLECTOR_STATE_ATTRIBUTE",
    "GitHubCollector",
    "GitHubCollectorSettings",
    "REGISTRY_STATE_ATTRIBUTE",
    "register",
]
