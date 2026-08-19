"""Event-loop-lazy lock used by restart-time module registration."""

from __future__ import annotations

import asyncio
from types import TracebackType
from typing import Optional, Type


class LazyAsyncLock:
    """Create the real asyncio lock on the first async operation.

    PK-010 imports and registers in-process modules while assembling the FastAPI
    application, before a running event loop exists on supported Python 3.10.
    Conversation still uses one lock per boundary; only its loop binding is
    deferred until the first request or lifespan operation.
    """

    def __init__(self):
        self._lock: asyncio.Lock | None = None

    def _get(self) -> asyncio.Lock:
        asyncio.get_running_loop()
        if self._lock is None:
            self._lock = asyncio.Lock()
        return self._lock

    async def __aenter__(self) -> "LazyAsyncLock":
        await self._get().acquire()
        return self

    async def __aexit__(
        self,
        exc_type: Optional[Type[BaseException]],
        exc: Optional[BaseException],
        traceback: Optional[TracebackType],
    ) -> None:
        self._get().release()


__all__ = ["LazyAsyncLock"]
