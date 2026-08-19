"""Project Kei conversation module public contracts."""

from .context import (
    AppStateConversationContextProvider,
    ConversationContextProvider,
    EmptyConversationContextProvider,
)
from .models import (
    ChatMessage,
    ConversationReply,
    LLMProfile,
    LLMProfileUpdate,
    TextGenerationResult,
)
from .module import register, unregister
from .service import ConversationService, TextGenerator

__all__ = [
    "ChatMessage",
    "AppStateConversationContextProvider",
    "ConversationContextProvider",
    "ConversationReply",
    "ConversationService",
    "EmptyConversationContextProvider",
    "LLMProfile",
    "LLMProfileUpdate",
    "register",
    "TextGenerationResult",
    "TextGenerator",
    "unregister",
]
