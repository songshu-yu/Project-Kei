"""Compatibility facade for pre-PK-110 Python and HTTP consumers."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Mapping, Optional

from .collector_gateway import LegacyCollectorGateway
from .models import BriefingDocument, CacheStatus, IntelItem, SourceCoverage, rfc3339, stable_item_id
from .prompt_builder import BriefingPromptBuilder
from .providers import (
    BriefingTextGenerator,
    BriefingVoiceProvider,
    BriefingVoiceProviderResolver,
)
from .repository import BriefingRepository, LifeForecastProjectionRepository
from .service import BriefingService


def _load_legacy_source_config() -> Mapping[str, Any]:
    from services.intel_source_config import load_intel_sources

    return load_intel_sources()


def _legacy_gateway(clock, source_config_provider):
    from intel.briefing import gather_all_intel

    return LegacyCollectorGateway(
        gather_all_intel,
        source_config_provider,
        clock=clock,
    )


@dataclass
class BriefingItem:
    source: str
    title: str
    summary: str = ""
    url: str = ""
    published: str = ""


@dataclass
class DailyBriefingResult:
    date: str
    fetched: bool
    rewritten: bool
    text: str
    script: str
    audio_path: str = ""
    cached: bool = False
    cache_path: str = ""
    counts: Dict[str, int] = field(default_factory=dict)
    items: Dict[str, List[Dict[str, Any]]] = field(default_factory=dict)
    warnings: List[str] = field(default_factory=list)
    patch_attempts: Dict[str, str] = field(default_factory=dict)
    coverage: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    schema_version: int = 1
    collector_contract_version: str = "1.0"
    rewrite_status: str = "not_requested"
    generated: bool = False
    fallback: bool = False
    audio_available: bool = False
    mode: str = "text_only"
    degraded: bool = False
    errors: List[Dict[str, Any]] = field(default_factory=list)
    updated_at: Optional[str] = None
    refresh_status: str = "not_requested"
    refresh_message: str = ""


def _legacy_category(item: IntelItem) -> str:
    if item.category == "papers":
        return "papers"
    if item.source_id == "twitter":
        return "twitter"
    if item.source_id == "github":
        return "github"
    if item.source_id == "bilibili":
        return "bilibili"
    if item.source_id == "youtube":
        return "youtube"
    if item.source_id == "money":
        return "money"
    return "papers" if item.source_id in {"arxiv", "crossref", "semantic"} else "money"


def _legacy_result(service: BriefingService, document: BriefingDocument, repository: BriefingRepository) -> DailyBriefingResult:
    grouped = {key: [] for key in ("papers", "twitter", "github", "bilibili", "youtube", "money")}
    for item in document.items:
        category = _legacy_category(item)
        sources = item.metadata.get("discovery_sources", [item.source_id])
        source_label = "/".join(str(value) for value in sources)
        grouped[category].append({
            "source": source_label if category == "papers" else item.author or source_label,
            "title": item.title,
            "summary": item.summary,
            "url": item.url,
            "published": item.published_at,
            "stable_id": item.stable_id,
            "source_id": item.source_id,
            "metadata": dict(item.metadata),
        })
    return DailyBriefingResult(
        date=document.local_date,
        fetched=document.fetched,
        rewritten=document.rewritten,
        text=document.text,
        script=document.script,
        cached=document.cache_status is CacheStatus.HIT,
        cache_path=str(repository.cache_path(document.local_date)),
        counts={key: len(values) for key, values in grouped.items()},
        items=grouped,
        warnings=[
            *document.warnings,
            *([document.refresh_message] if document.refresh_message else []),
        ],
        patch_attempts=dict(document.patch_attempts),
        coverage={key: value.to_dict() for key, value in document.coverage.items()},
        rewrite_status=document.rewrite_status,
        generated=document.rewritten,
        fallback=document.rewrite_status in {"fallback", "not_requested"},
        updated_at=document.updated_at,
        refresh_status=document.refresh_status,
        refresh_message=document.refresh_message,
    )


class DailyBriefingService:
    """Stable legacy facade delegating every use case to ``BriefingService``."""

    def __init__(
        self,
        text_generator: Optional[BriefingTextGenerator] = None,
        tts: object = None,
        root_dir: str | Path = ".",
        *,
        voice: Optional[BriefingVoiceProvider] = None,
        voice_provider_resolver: Optional[BriefingVoiceProviderResolver] = None,
        timezone_name: str = "Asia/Shanghai",
        clock=lambda: datetime.now(timezone.utc),
        gateway=None,
        source_config_provider: Optional[Callable[[], Mapping[str, Any]]] = None,
        patch_cooldown=None,
        rewrite_timeout: float = 60.0,
        section_limits=None,
        life_forecast_provider: Optional[Callable[[], object]] = None,
    ):
        # ``tts`` remains accepted so old constructors do not crash, but PK-110
        # never invokes it. Narration audio must arrive through ``voice``.
        del tts
        source_config_provider = source_config_provider or _load_legacy_source_config
        self.root_dir = Path(root_dir)
        self.repository = BriefingRepository(self.root_dir)
        self.life_forecast_projection_repository = (
            LifeForecastProjectionRepository(self.root_dir)
        )
        self.gateway = gateway or _legacy_gateway(clock, source_config_provider)
        kwargs = {}
        if patch_cooldown is not None:
            kwargs["patch_cooldown"] = patch_cooldown
        self.core = BriefingService(
            self.gateway,
            self.repository,
            text_generator=text_generator,
            source_config_provider=source_config_provider,
            timezone_name=timezone_name,
            clock=clock,
            rewrite_timeout=rewrite_timeout,
            section_limits=section_limits,
            life_forecast_projection_repository=(
                self.life_forecast_projection_repository
            ),
            life_forecast_provider=life_forecast_provider,
            **kwargs,
        )
        self.text_generator = text_generator
        self.voice = voice
        self._voice_provider_resolver = voice_provider_resolver
        self.repository.invalidate_stale_summary(self.core.today())

    def _resolve_voice_provider(self) -> Optional[BriefingVoiceProvider]:
        provider: object = self.voice
        if self._voice_provider_resolver is not None:
            try:
                provider = self._voice_provider_resolver()
            except Exception:
                return None
        synthesize = getattr(provider, "synthesize_briefing", None)
        return provider if callable(synthesize) else None

    @staticmethod
    def _voice_failed(result: DailyBriefingResult, code: str) -> None:
        result.audio_path = ""
        result.audio_available = False
        result.mode = "text_only"
        result.degraded = True
        result.errors = [{
            "stage": "tts",
            "code": code,
            "message": "播报语音不可用，已返回文本",
        }]

    @classmethod
    def _apply_voice_result(
        cls,
        result: DailyBriefingResult,
        voice_result: object,
    ) -> None:
        if not isinstance(voice_result, Mapping):
            cls._voice_failed(result, "voice_failed")
            return
        audio_available = voice_result.get("audio_available")
        audio_path = voice_result.get("audio_path", "")
        if (
            not isinstance(audio_available, bool)
            or not isinstance(audio_path, str)
            or len(audio_path) > 512
            or (audio_available and not audio_path.strip())
        ):
            cls._voice_failed(result, "voice_failed")
            return
        if audio_available:
            result.audio_path = audio_path
            result.audio_available = True
            result.mode = "audio"
            result.degraded = False
            result.errors = []
            return
        code = "voice_failed"
        errors = voice_result.get("errors")
        if isinstance(errors, list) and errors and isinstance(errors[0], Mapping):
            candidate = errors[0].get("code")
            if candidate in {
                "empty_narration",
                "voice_failed",
                "voice_unavailable",
            }:
                code = candidate
        cls._voice_failed(result, code)

    @staticmethod
    def _parse_date(value: Optional[str]) -> date:
        return date.fromisoformat(value) if value else date.today()

    async def build(
        self,
        target_date: Optional[str] = None,
        fetch: bool = True,
        rewrite: bool = False,
        synthesize: bool = False,
        use_cache: bool = True,
        refresh: bool = False,
        rewrite_refresh: bool = False,
        auto_patch_missing: bool = True,
    ) -> DailyBriefingResult:
        del use_cache
        target = self._parse_date(target_date) if target_date else self.core.today()
        if not fetch:
            document = self.core.read(target)
            if document is None:
                stamp = rfc3339(self.core._now())
                document = BriefingDocument(
                    local_date=target.isoformat(),
                    timezone=self.core.timezone_name,
                    items=[],
                    coverage={},
                    warnings=[],
                    text="今日情报缓存尚未生成。",
                    script="老师，今天的情报缓存还没有准备好。先运行一次每日情报预生成吧。",
                    fetched=False,
                    rewritten=False,
                    rewrite_status="not_requested",
                    created_at=stamp,
                    updated_at=stamp,
                    cache_status=CacheStatus.UNAVAILABLE,
                )
            elif not document.script:
                document.script = self.core.prompt_builder.fallback_script(document)
                document.rewritten = False
                document.rewrite_status = "fallback"
            # Read-only means no Collector and no PK-200 call even when a
            # legacy consumer sends rewrite=true.
        else:
            document = await self.core.generate(
                local_date=target,
                refresh=refresh,
                rewrite=rewrite,
                rewrite_refresh=rewrite_refresh,
                patch_missing=auto_patch_missing,
            )
        result = _legacy_result(self.core, document, self.repository)
        if synthesize:
            # Resolve exactly once per explicit narration request. This keeps
            # optional-provider load order dynamic while preventing a provider
            # replacement from changing an in-flight request.
            voice = self._resolve_voice_provider()
            if voice is None:
                self._voice_failed(result, "voice_unavailable")
            else:
                try:
                    voice_result = await voice.synthesize_briefing(
                        result.script,
                        local_date=result.date,
                    )
                except Exception:
                    self._voice_failed(result, "voice_failed")
                else:
                    self._apply_voice_result(result, voice_result)
        return result

    def load_cached_result(self, target_date: Optional[str] = None) -> Optional[DailyBriefingResult]:
        target = self._parse_date(target_date) if target_date else self.core.today()
        document = self.core.read(target)
        return _legacy_result(self.core, document, self.repository) if document else None

    def load_current_summary(self) -> Dict[str, Any]:
        return self.core.summary_result(self.core.read_today())

    def status(self) -> Dict[str, Any]:
        # Dashboard status is observational: unlike normal briefing reads it
        # must not invalidate/delete a stale summary as a side effect.
        document = self.repository.load(self.core.today())
        cached = _legacy_result(self.core, document, self.repository) if document else None
        summary = self.core.summary_result(document)
        return {
            "ready": cached is not None,
            "updated_at": cached.updated_at if cached else None,
            "counts": cached.counts if cached else {},
            "coverage": cached.coverage if cached else {},
            "warnings": cached.warnings if cached else [],
            "summary": summary,
            "generation": self.core.generation_status(),
        }

    def prepare_summary_cache(self) -> Dict[str, Any]:
        today = self.core.today()
        if self.repository.invalidate_stale_summary(today):
            return {
                "ready": False,
                "date": today.isoformat(),
                "text": "",
                "generated": False,
                "fallback": False,
                "updated_at": None,
            }
        return self.load_current_summary()

    async def _rewrite_as_kei(self, text: str, day: date) -> str:
        stamp = rfc3339(self.core._now())
        document = BriefingDocument(
            local_date=day.isoformat(),
            timezone=self.core.timezone_name,
            items=[],
            coverage={},
            warnings=[],
            text=text,
            script="",
            fetched=False,
            rewritten=False,
            rewrite_status="not_requested",
            created_at=stamp,
            updated_at=stamp,
        )
        await self.core._rewrite(document, refresh=True)
        return document.script

    def _save_cache(self, result: DailyBriefingResult) -> None:
        stamp = rfc3339(self.core._now())
        document = BriefingDocument(
            local_date=result.date,
            timezone=self.core.timezone_name,
            items=[],
            coverage={key: SourceCoverage.from_dict(value) for key, value in result.coverage.items()},
            warnings=list(result.warnings),
            text=result.text,
            script=result.script,
            fetched=result.fetched,
            rewritten=result.rewritten,
            rewrite_status=result.rewrite_status or ("generated" if result.rewritten else "not_requested"),
            created_at=stamp,
            updated_at=stamp,
            patch_attempts=dict(result.patch_attempts),
        )
        self.repository.save_transaction(
            document,
            include_summary=(
                document.local_date == self.core.today().isoformat()
                and bool(document.script.strip())
            ),
        )


__all__ = [
    "BriefingItem",
    "BriefingVoiceProvider",
    "DailyBriefingResult",
    "DailyBriefingService",
]
