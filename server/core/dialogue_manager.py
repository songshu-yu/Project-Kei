"""Compatibility dialogue adapter used by the existing voice pipeline."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Optional, Protocol

from features.conversation.service import ConversationService


@dataclass
class DialogueReply:
    text: str
    emotion: str
    timestamp: str


class MemoryCommandStore(Protocol):
    """Legacy PK-160-owned command seam; conversation never imports its store."""

    def parse_command(self, text: str) -> Any:
        ...

    def add(self, content: str) -> Any:
        ...

    def summary_text(self) -> str:
        ...

    def delete_by_index(self, index: int) -> Any:
        ...


class DialogueManager:
    def __init__(
        self,
        conversation: ConversationService,
        memory_store: Optional[MemoryCommandStore] = None,
    ):
        self.conversation = conversation
        self.memory_store = memory_store

    async def reply(self, user_text: str) -> DialogueReply:
        if self.memory_store:
            command = self.memory_store.parse_command(user_text)
            if command and command.action == "add":
                memory = self.memory_store.add(command.content)
                return DialogueReply(
                    text=f"好啦，我记住了：{memory.content}",
                    emotion="happy",
                    timestamp=datetime.now().isoformat(timespec="seconds"),
                )
            if command and command.action == "list":
                return DialogueReply(
                    text=self.memory_store.summary_text(),
                    emotion="calm",
                    timestamp=datetime.now().isoformat(timespec="seconds"),
                )
            if command and command.action == "delete_index":
                removed = self.memory_store.delete_by_index(command.index or 0)
                if removed:
                    text = f"已经忘掉第 {command.index} 条了：{removed.content}"
                    emotion = "calm"
                else:
                    text = f"找不到第 {command.index} 条记忆哦。"
                    emotion = "sad"
                return DialogueReply(
                    text=text,
                    emotion=emotion,
                    timestamp=datetime.now().isoformat(timespec="seconds"),
                )

        chat_message = await self.conversation.chat(user_text)
        return DialogueReply(
            text=chat_message.text,
            emotion=chat_message.emotion,
            timestamp=chat_message.timestamp,
        )
