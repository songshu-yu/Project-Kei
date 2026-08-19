"""Verify that dashboard reviews ask Kei to judge factual completion data."""
from __future__ import annotations

import asyncio
import os
import tempfile
from pathlib import Path

TEST_LOCAL_ROOT = Path(tempfile.gettempdir()) / "project-kei-pk200-tests"
os.environ["PROJECT_KEI_ENV_FILE"] = str(TEST_LOCAL_ROOT / "missing.env")
os.environ["PROJECT_KEI_LLM_PROFILE_PATH"] = str(TEST_LOCAL_ROOT / "missing-profile.json")
os.environ["LLM_API_KEY"] = "test-key"

import _path_setup  # noqa: E402,F401

from features.conversation.models import TextGenerationResult
from features.demon_slayer import DemonSlayerService, DemonSlayerStore


class FakeKei:
    system_prompt = "你是天童 Kei。"

    def __init__(self) -> None:
        self.system = ""
        self.user = ""

    async def generate_text(self, system: str, user: str, **_kwargs) -> TextGenerationResult:
        self.system = system
        self.user = user
        return TextGenerationResult(
            text='{"verdict":"mixed"}',
            generated=True,
            fallback=False,
            model="fake-model",
        )


async def check() -> None:
    fake = FakeKei()
    with tempfile.TemporaryDirectory(prefix="kei-demon-review-") as temp_dir:
        service = DemonSlayerService(
            DemonSlayerStore(Path(temp_dir) / "demon.json"),
            text_generator_provider=lambda: fake,
        )
        result = await service.evaluate_review({
            "period": "daily",
            "period_start": "2026-07-18",
            "period_end": "2026-07-18",
            "completed": 1,
            "total": 2,
            "completion_rate": 0.5,
            "completed_goals": ["读论文"],
            "missed": ["运动"],
            "notes": ["完成摘要"],
            "breakdown": {"daily": {"completed": 1, "total": 2}},
            "points_earned": 10,
            "message": "fallback",
        })

    assert result["kei_generated"] is True
    assert result["emotion"] == "calm"
    assert "实际完成 1/2" in result["message"]
    assert "读论文" in result["message"] and "运动" in result["message"]
    assert "值得表扬" in result["message"] and "必须批评" in result["message"]
    assert "只能依据" in fake.system
    assert '"completed_goals": ["读论文"]' in fake.user
    assert '"missed_goals": ["运动"]' in fake.user


def main() -> int:
    asyncio.run(check())
    print("Kei demon review tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
