"""Application composition helpers for the built-in conversation module."""

from __future__ import annotations

from pathlib import Path

from .client import LLMEngine
from .context import ConversationContextProvider, EmptyConversationContextProvider
from .models import LLMProfile
from .repository import LLMProfileRepository, normalize_profile
from .runtime import ConversationRuntime
from .service import ConversationService


def request_options_for(profile: LLMProfile) -> dict:
    if profile.provider == "deepseek":
        return {"thinking": {"type": profile.thinking_mode}}
    return {}


def create_conversation_service(
    *,
    api_key: str,
    default_profile: LLMProfile | dict,
    profile_path: str | Path,
    context_provider: ConversationContextProvider | None = None,
    system_prompt_path: str | Path | None = None,
    max_history: int = 20,
) -> ConversationService:
    repository = LLMProfileRepository(profile_path)
    safe_default = normalize_profile(default_profile)
    active_profile = repository.load(safe_default)

    def client_factory(profile: LLMProfile) -> LLMEngine:
        return LLMEngine(
            api_key=api_key,
            base_url=profile.base_url,
            model=profile.model,
            system_prompt_path=system_prompt_path,
            request_options=request_options_for(profile),
        )

    client = client_factory(active_profile)
    runtime = ConversationRuntime(
        client,
        active_profile,
        context_provider=context_provider or EmptyConversationContextProvider(),
        max_history=max_history,
    )
    return ConversationService(runtime, repository, client_factory)
