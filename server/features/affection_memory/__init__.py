"""Built-in affection and long-term memory module."""

from .context import AffectionMemoryContextProvider, create_context_provider
from .models import MemoryCommand, MemoryCommandReply, MemoryEntry, RelationshipResult
from .module import register, unregister
from .repository import (
    DEFAULT_MEMORY_PATH,
    DEFAULT_RELATIONSHIP_PATH,
    MemoryPersistenceError,
    MemoryRepository,
    MemoryStateError,
    RelationshipPersistenceError,
    RelationshipRepository,
    RelationshipStateError,
)
from .router import create_affection_memory_router
from .security import AffectionMemoryOriginGuardMiddleware, default_local_control_guard
from .service import MemoryService, RelationshipService

__all__ = [
    "AffectionMemoryContextProvider",
    "AffectionMemoryOriginGuardMiddleware",
    "DEFAULT_MEMORY_PATH",
    "DEFAULT_RELATIONSHIP_PATH",
    "MemoryCommand",
    "MemoryCommandReply",
    "MemoryEntry",
    "MemoryPersistenceError",
    "MemoryRepository",
    "MemoryService",
    "MemoryStateError",
    "RelationshipPersistenceError",
    "RelationshipRepository",
    "RelationshipResult",
    "RelationshipService",
    "RelationshipStateError",
    "create_affection_memory_router",
    "create_context_provider",
    "default_local_control_guard",
    "register",
    "unregister",
]
