"""Python compatibility adapter for callers of the pre-PK-210 VoicePipeline.

The HTTP routes use :class:`features.voice.service.VoiceService`.  This adapter
keeps existing imports and local intent helpers stable while downstream modules
finish their own migrations.
"""
from __future__ import annotations

import base64
import time
import uuid
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, AsyncIterator, Callable, Dict, List, Union

from core.calendar_contracts import get_calendar_summary
from core.dialogue_manager import DialogueManager, DialogueReply
from services.audio_cleanup import cleanup_audio_outputs
from services.daily_briefing import DailyBriefingService
from services.text_normalizer import normalize_voice_text
from systems.demon_slayer import (
    daily_review as demon_daily_review,
    get_status as demon_status,
    monthly_review as demon_monthly_review,
    reminder as demon_reminder,
    weekly_review as demon_weekly_review,
    yearly_review as demon_yearly_review,
)

from .providers.asr_http import ASRClient
from .providers.tts_http import TTSClient, split_text_for_tts


CalendarSummaryProvider = Callable[[], Dict[str, Any]]


@dataclass
class VoiceChatResult:
    user_text: str
    assistant_text: str
    emotion: str
    audio_path: str
    audio_paths: List[str]
    audio_base64: str
    timestamp: str
    timings_ms: Dict[str, int]
    asr_segments: List[Dict[str, Any]]
    asr_language: str
    asr_language_probability: float


@dataclass
class VoiceReplyDraft:
    user_text: str
    assistant_text: str
    emotion: str
    timestamp: str
    timings_ms: Dict[str, int]
    asr_segments: List[Dict[str, Any]]
    asr_language: str
    asr_language_probability: float
    started_at: float


class VoicePipeline:
    """Deprecated application adapter; new HTTP orchestration uses VoiceService."""

    def __init__(
        self,
        asr_client: ASRClient,
        dialogue: DialogueManager,
        tts_client: TTSClient,
        daily_briefing: DailyBriefingService | None = None,
        calendar_summary_provider: CalendarSummaryProvider = get_calendar_summary,
        cleanup_root: Union[str, Path, None] = None,
        output_dir: Union[str, Path] = "output/voice_replies",
    ):
        self.asr_client = asr_client
        self.dialogue = dialogue
        self.tts_client = tts_client
        self.daily_briefing = daily_briefing
        self.calendar_summary_provider = calendar_summary_provider
        self.cleanup_root = Path(cleanup_root) if cleanup_root else None
        self.output_dir = Path(output_dir)

    @staticmethod
    def _is_daily_briefing_intent(text: str) -> bool:
        value = "".join(str(text or "").lower().split())
        direct = ("每日情报", "每日简报", "今日情报", "今天情报", "今天有什么")
        topics = ("情报", "动态", "资讯", "新闻", "播报", "简报")
        times = ("今天", "今日", "每日", "最近", "新", "最新")
        return any(item in value for item in direct) or (
            any(item in value for item in topics) and any(item in value for item in times)
        )

    async def _daily_briefing_reply(self) -> str:
        if not self.daily_briefing:
            return ""
        result = self.daily_briefing.load_cached_result()
        if result:
            return result.script
        return "老师，今天的情报缓存还没有准备好。先运行一次每日情报预生成吧。"

    @staticmethod
    def _demon_intent(text: str) -> str:
        value = "".join(str(text or "").lower().split())
        groups = (
            ("yearly_review", ("年度复盘", "年总结", "今年总结", "全年复盘")),
            ("monthly_review", ("月度复盘", "月总结", "本月复盘", "这个月总结")),
            ("weekly_review", ("周复盘", "本周复盘", "每周复盘", "周末复盘")),
            ("daily_review", ("今日复盘", "今天复盘", "每日复盘", "今天做得怎么样", "今天表现")),
        )
        for intent, phrases in groups:
            if any(phrase in value for phrase in phrases):
                return intent
        if any(word in value for word in ("积分", "愿望", "兑换", "奖励")):
            return "status"
        if any(word in value for word in ("斩妖", "妖怪", "没斩", "没做", "剩下", "提醒", "目标")) and "料理" not in value:
            return "reminder"
        return ""

    @staticmethod
    def _format_demon_status(status: Dict[str, Any]) -> str:
        points = int(status.get("points", 0))
        wishes = status.get("wishes", []) or []
        affordable = [item for item in wishes if int(item.get("cost", 0)) <= points]
        lines = [f"老师现在有 {points} 积分。"]
        if affordable:
            lines.append("已经能兑换：" + "、".join(str(item.get("title", "")) for item in affordable[:3]) + "。")
        lines.append(str(status.get("reminder", "")))
        return "\n".join(item for item in lines if item)

    def _demon_reply(self, text: str) -> tuple[str, str]:
        intent = self._demon_intent(text)
        if intent == "reminder":
            return demon_reminder(), "calm"
        if intent == "daily_review":
            review = demon_daily_review()
            return f"{review.get('message', '')}\n{review.get('reminder', '')}".strip(), "happy"
        if intent == "weekly_review":
            return str(demon_weekly_review().get("message", "")), "calm"
        if intent == "monthly_review":
            return str(demon_monthly_review().get("message", "")), "calm"
        if intent == "yearly_review":
            return str(demon_yearly_review().get("message", "")), "calm"
        if intent == "status":
            return self._format_demon_status(demon_status()), "calm"
        return "", "calm"

    @staticmethod
    def _calendar_intent(text: str) -> bool:
        value = "".join(str(text or "").lower().split())
        return any(phrase in value for phrase in (
            "今天是什么日子", "今天几号", "今天有什么备忘", "备忘录", "纪念日",
            "日历", "熟练度", "一万小时", "练了多久",
        ))

    def _calendar_reply(self) -> str:
        summary = self.calendar_summary_provider()
        lines = [str(summary.get("message", ""))]
        skills = summary.get("skills", []) or []
        if len(skills) > 1:
            preview = "；".join(
                f"{item.get('name')} {item.get('total_hours'):g} 小时，{item.get('level', {}).get('name')}"
                for item in skills[:3]
            )
            lines.append(f"熟练度排行：{preview}。")
        return "\n".join(item for item in lines if item)

    async def recognize_and_reply(self, audio: bytes, filename: str = "audio.wav", language: str = "zh", vad_filter: bool = False) -> VoiceReplyDraft:
        started = time.perf_counter()
        transcript = await self.asr_client.transcribe_bytes(audio, filename, language, vad_filter)
        after_asr = time.perf_counter()
        user_text = normalize_voice_text(transcript.text)
        if not user_text:
            raise ValueError("没有识别到可提交的语音文字")
        script = await self._daily_briefing_reply() if self._is_daily_briefing_intent(user_text) else ""
        emotion = "calm"
        if not script:
            script, emotion = self._demon_reply(user_text)
        if not script and self._calendar_intent(user_text):
            script = self._calendar_reply()
        reply = DialogueReply(script, emotion, datetime.now().isoformat(timespec="seconds")) if script else await self.dialogue.reply(user_text)
        after_reply = time.perf_counter()
        return VoiceReplyDraft(
            user_text=user_text,
            assistant_text=reply.text,
            emotion=reply.emotion,
            timestamp=reply.timestamp,
            timings_ms={"asr": int((after_asr - started) * 1000), "llm": int((after_reply - after_asr) * 1000)},
            asr_segments=transcript.segments,
            asr_language=transcript.language,
            asr_language_probability=transcript.language_probability,
            started_at=started,
        )

    async def synthesize_reply_parts(self, text: str, emotion: str, split_tts: bool = False, stem: str = "") -> AsyncIterator[Dict[str, Any]]:
        self.output_dir.mkdir(parents=True, exist_ok=True)
        stem = stem or f"reply_{time.strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}"
        parts = split_text_for_tts(text) if split_tts else [text]
        for index, part_text in enumerate(parts, start=1):
            suffix = f"_part{index:02d}" if split_tts else ""
            path = self.output_dir / f"{stem}{suffix}.wav"
            started = time.perf_counter()
            saved = await self.tts_client.synthesize_to_file(part_text, path, emotion)
            if saved and self.cleanup_root:
                cleanup_audio_outputs(self.cleanup_root)
            yield {
                "index": index,
                "total": len(parts),
                "text": part_text,
                "audio_path": str(path) if saved else "",
                "elapsed_ms": int((time.perf_counter() - started) * 1000),
                "saved": saved,
            }

    async def chat(self, audio: bytes, filename: str = "audio.wav", language: str = "zh", vad_filter: bool = False, include_audio_base64: bool = False, split_tts: bool = False) -> VoiceChatResult:
        draft = await self.recognize_and_reply(audio, filename, language, vad_filter)
        tts_started = time.perf_counter()
        paths: List[str] = []
        async for part in self.synthesize_reply_parts(draft.assistant_text, draft.emotion, split_tts):
            if part["audio_path"]:
                paths.append(part["audio_path"])
        finished = time.perf_counter()
        encoded = ""
        if include_audio_base64 and paths:
            encoded = base64.b64encode(Path(paths[0]).read_bytes()).decode("ascii")
        return VoiceChatResult(
            draft.user_text, draft.assistant_text, draft.emotion,
            paths[0] if paths else "", paths, encoded, draft.timestamp,
            {**draft.timings_ms, "tts": int((finished - tts_started) * 1000), "total": int((finished - draft.started_at) * 1000)},
            draft.asr_segments, draft.asr_language, draft.asr_language_probability,
        )


__all__ = ["VoicePipeline", "VoiceChatResult", "VoiceReplyDraft"]
