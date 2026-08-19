"""Verify non-HTTP consumers share PK-200's controlled generation service."""

from __future__ import annotations

import asyncio
import os
import tempfile
from datetime import date, datetime
from pathlib import Path

TEST_LOCAL_ROOT = Path(tempfile.gettempdir()) / "project-kei-pk200-tests"
os.environ["PROJECT_KEI_ENV_FILE"] = str(TEST_LOCAL_ROOT / "missing.env")
os.environ["PROJECT_KEI_LLM_PROFILE_PATH"] = str(TEST_LOCAL_ROOT / "missing-profile.json")
os.environ["LLM_API_KEY"] = "test-key"

import _path_setup  # noqa: E402,F401

from core.dialogue_manager import DialogueManager  # noqa: E402
from features.affection_memory import MemoryRepository, MemoryService  # noqa: E402
from features.conversation.models import LLMProfile  # noqa: E402
from features.conversation.repository import LLMProfileRepository  # noqa: E402
from features.conversation.runtime import ConversationRuntime  # noqa: E402
from features.conversation.service import ConversationService  # noqa: E402
from features.focus.repository import FocusRepository  # noqa: E402
from features.focus.service import FocusEncouragementService, FocusService  # noqa: E402
from services.daily_briefing import DailyBriefingService  # noqa: E402
from services.voice_pipeline import VoicePipeline  # noqa: E402


class FakeClient:
    system_prompt = "你是测试用 Kei。"

    def __init__(self, model: str):
        self.model = model
        self.closed = False

    async def chat_completion(self, _messages, **_kwargs) -> str:
        assert not self.closed
        return f"[emotion:calm] chat:{self.model}"

    async def complete(self, _system: str, _user: str, **_kwargs) -> str:
        assert not self.closed
        return f"[emotion:calm] generated:{self.model}"

    async def test(self) -> None:
        assert not self.closed

    async def close(self) -> None:
        self.closed = True


async def check() -> None:
    with tempfile.TemporaryDirectory(prefix="kei-consumers-") as temp_dir:
        root = Path(temp_dir)
        old = FakeClient("old")
        old_profile = LLMProfile("custom", "http://127.0.0.1:9999/v1", "old")
        repository = LLMProfileRepository(root / "profile.json")
        runtime = ConversationRuntime(old, old_profile)
        service = ConversationService(
            runtime,
            repository,
            lambda value: FakeClient(value.model),
        )

        memories = MemoryService(MemoryRepository(root / "memories.json"))
        dialogue = DialogueManager(service, memories)
        voice = VoicePipeline(None, dialogue, None)
        briefing = DailyBriefingService(text_generator=service, root_dir=root)

        command_reply = await voice.dialogue.reply("请记住：消费者测试的虚构记忆")
        assert command_reply.emotion == "happy" and len(memories.list()) == 1
        assert await service.history() == []
        list_reply = await voice.dialogue.reply("你还记得什么？")
        assert "消费者测试" in list_reply.text and await service.history() == []
        delete_reply = await voice.dialogue.reply("删除第 1 条记忆")
        assert "已经忘掉" in delete_reply.text and memories.list() == []
        assert await service.history() == []

        first = await voice.dialogue.reply("切换前")
        assert first.text == "chat:old"
        before_history = await service.history()
        await service.update_profile({
            "provider": "custom",
            "base_url": "http://127.0.0.1:9998/v1",
            "model": "new",
            "thinking_mode": "disabled",
        })
        assert old.closed
        assert await service.history() == before_history

        second = await voice.dialogue.reply("切换后")
        assert second.text == "chat:new"
        briefing_text = await briefing._rewrite_as_kei("测试情报", date(2026, 7, 21))
        assert "generated:new" in briefing_text

        focus = FocusService(
            FocusRepository(root / "focus.json"),
            clock=lambda: datetime(2030, 1, 2, 8, 0, 0),
            id_factory=lambda: "consumer-focus-session",
        )
        started = focus.start(mode="pomodoro", minutes=25, task="bounded fixture")
        history_before_generation = await service.history()
        result = await FocusEncouragementService(focus, lambda: service).generate(
            session_id=started.session_id,
            start_at=started.start_at,
        )
        assert result.generated is True
        assert result.text == "generated:new"
        assert await service.history() == history_before_generation
        assert len(await service.history()) == len(before_history) + 2


def main() -> int:
    asyncio.run(check())
    print("conversation consumer tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
