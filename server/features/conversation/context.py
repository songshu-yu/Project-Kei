"""Read-only context contracts consumed by conversation."""

from __future__ import annotations

import inspect
from typing import Any, Callable, Protocol, runtime_checkable


@runtime_checkable
class ConversationContextProvider(Protocol):
    """Return already-filtered prompt text without exposing backing state."""

    def get_context(self) -> str:
        ...


class EmptyConversationContextProvider:
    def get_context(self) -> str:
        return ""


class CallableConversationContextProvider:
    """Temporary application-layer adapter for an existing read-only callable."""

    def __init__(self, callback: Callable[[], str]):
        self._callback = callback

    def get_context(self) -> str:
        return self._callback()


class AppStateConversationContextProvider:
    """Resolve the current read-only provider from application state per call."""

    def __init__(
        self,
        app: Any,
        attribute: str = "conversation_context_provider",
    ):
        self._app = app
        self._attribute = attribute

    def get_context(self) -> str:
        try:
            provider = getattr(self._app.state, self._attribute, None)
            if provider is None or provider is self:
                return ""
            getter = getattr(provider, "get_context", None)
            if not callable(getter):
                return ""
            value = getter()
            if inspect.isawaitable(value):
                if inspect.iscoroutine(value):
                    value.close()
                return ""
            return value if isinstance(value, str) else ""
        except Exception:
            return ""


__all__ = [
    "AppStateConversationContextProvider",
    "CallableConversationContextProvider",
    "ConversationContextProvider",
    "EmptyConversationContextProvider",
]
