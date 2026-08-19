"""Legacy Python and voice-command adapters backed by the PK-160 services."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from .event_catalog import EVENTS, LEVELS, STAT_LIMITS, VOICE_CUES
from .models import MemoryCommand, MemoryEntry, RelationshipResult
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
from .service import (
    MemoryService,
    RelationshipService,
    choose_event,
    clamp,
    event_matches_context,
    level_for_affection,
    public_stats,
    strip_choice_effects,
)


AffectionResult = RelationshipResult
AffectionStore = RelationshipRepository

def _relationship_service(store: Optional[AffectionStore]) -> RelationshipService:
    repository = store or RelationshipRepository(DEFAULT_RELATIONSHIP_PATH)
    return RelationshipService(repository)


def get_status(store: Optional[AffectionStore] = None) -> dict:
    return _relationship_service(store).get_status()


def trigger_event(
    context: str = "",
    force_event: str = "",
    seed: Optional[int] = None,
    store: Optional[AffectionStore] = None,
) -> RelationshipResult:
    return _relationship_service(store).trigger_event(context=context, force_event=force_event, seed=seed)


def choose_response(choice_id: str, store: Optional[AffectionStore] = None) -> RelationshipResult:
    return _relationship_service(store).choose_response(choice_id)


def reset(store: Optional[AffectionStore] = None) -> int:
    return _relationship_service(store).reset()


class MemoryStore:
    """Old ``core.memory_store.MemoryStore`` surface over one MemoryService."""

    def __init__(
        self,
        path: str | Path | None = None,
        max_prompt_memories: int = 12,
        *,
        service: MemoryService | None = None,
    ):
        self._service = service or MemoryService(
            MemoryRepository(path or DEFAULT_MEMORY_PATH),
            max_prompt_memories=max_prompt_memories,
        )
        self.path = self._service.repository.path
        self.max_prompt_memories = self._service.max_prompt_memories

    @property
    def _memories(self) -> list[MemoryEntry]:
        return self._service.list()

    def load(self) -> None:
        self._service.list()

    def save(self) -> None:
        self._service.repository.save(self._service.list())

    def list(self) -> list[MemoryEntry]:
        return self._service.list()

    def add(self, content: str, tags: Optional[list[str]] = None, source: str = "user") -> MemoryEntry:
        return self._service.add(content, tags=tags, source=source)

    def delete(self, memory_id: str) -> Optional[MemoryEntry]:
        return self._service.delete(memory_id)

    def delete_by_index(self, index: int) -> Optional[MemoryEntry]:
        return self._service.delete_by_index(index)

    def clear(self) -> int:
        return self._service.clear()

    def prompt_context(self) -> str:
        return self._service.prompt_context()

    def summary_text(self) -> str:
        return self._service.summary_text()

    def to_dict(self) -> dict:
        return self._service.to_dict()

    parse_command = staticmethod(MemoryService.parse_command)


class MemoryCommandConversationProvider:
    """Keep explicit voice memory commands without changing PK-200/PK-210."""

    def __init__(self, provider, memories: MemoryService):
        self._provider = provider
        self._memories = memories

    def capabilities(self):
        return self._provider.capabilities()

    async def health(self):
        return await self._provider.health()

    async def chat(self, message: str, *, request_id: str):
        command_reply = self._memories.handle_command(message)
        if command_reply is not None:
            return command_reply
        return await self._provider.chat(message, request_id=request_id)

    async def cancel(self, request_id: str) -> None:
        await self._provider.cancel(request_id)

    async def close(self) -> None:
        await self._provider.close()


__all__ = [
    "AffectionResult",
    "AffectionStore",
    "DEFAULT_MEMORY_PATH",
    "DEFAULT_RELATIONSHIP_PATH",
    "EVENTS",
    "LEVELS",
    "MemoryCommand",
    "MemoryCommandConversationProvider",
    "MemoryEntry",
    "MemoryPersistenceError",
    "MemoryStateError",
    "MemoryStore",
    "STAT_LIMITS",
    "RelationshipPersistenceError",
    "RelationshipStateError",
    "VOICE_CUES",
    "choose_event",
    "choose_response",
    "clamp",
    "event_matches_context",
    "get_status",
    "level_for_affection",
    "public_stats",
    "reset",
    "strip_choice_effects",
    "trigger_event",
]
