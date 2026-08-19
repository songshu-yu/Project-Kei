"""Adapter that consumes only PK-200's public ConversationService."""
from __future__ import annotations

import asyncio

from features.conversation.service import ConversationClosedError, ConversationService

from ..errors import failed, unavailable
from ..models import ProviderCapabilities, ProviderHealth


class ConversationServiceProvider:
    def __init__(self, service: ConversationService):
        self._service = service
        self._active: dict[str, asyncio.Task] = {}
        self._closed = False

    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(provider="pk-200-conversation", operations=("chat",), default_timeout_seconds=120.0)

    async def health(self) -> ProviderHealth:
        if self._closed:
            return ProviderHealth(False, "closed", error_code="conversation_closed")
        try:
            await self._service.get_profile()
            return ProviderHealth(True, "available")
        except Exception:
            return ProviderHealth(False, "unavailable", error_code="conversation_unavailable")

    async def chat(self, message: str, *, request_id: str):
        if self._closed:
            raise unavailable("conversation")
        task = asyncio.current_task()
        if task:
            self._active[request_id] = task
        try:
            return await self._service.chat(message)
        except asyncio.CancelledError:
            raise
        except ConversationClosedError as exc:
            raise unavailable("conversation") from exc
        except ValueError as exc:
            raise failed("conversation") from exc
        except Exception as exc:
            raise failed("conversation") from exc
        finally:
            self._active.pop(request_id, None)

    async def cancel(self, request_id: str) -> None:
        task = self._active.get(request_id)
        if task and task is not asyncio.current_task():
            task.cancel()

    async def close(self) -> None:
        # PK-200 lifecycle is owned by the application composition root.
        self._closed = True
        for task in list(self._active.values()):
            if task is not asyncio.current_task():
                task.cancel()
