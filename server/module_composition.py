"""Production-only composition for installed Project Kei modules.

This file owns the narrow host seams that packages may consume.  It must not
read user state while the application is imported and it must never expose
paths, commands, credentials, or repository objects through HTTP.
"""

from __future__ import annotations

import inspect
import os
import re
import subprocess
from pathlib import Path
from typing import Any

from core.intel_contracts import CollectorRegistry
from features.module_manager.service import get_module_manager
from features.qq_control import create_qq_control_router
from features.voice import SilkPythonUtteranceEncoder
from features.voice.providers.gpt_sovits import (
    ADAPTER_NAME as GPT_SOVITS_ADAPTER_NAME,
    GPTSoVITSSidecarAdapter,
    LocalEngineRegistry,
    LocalEngineSelectionService,
    create_gpt_sovits_engine_router,
    register_gpt_sovits_sidecar,
)
from features.voice.runtime_control import VoiceRuntimeControlService
from qq_bridge.configuration import (
    QQBridgeConfigurationStore,
    create_qq_media_capability_provider,
)
from qq_bridge.control_facade import QQControlAdapterFacade
from qq_bridge.module_adapter import (
    ADAPTER_NAME as QQ_BRIDGE_ADAPTER_NAME,
    QQBridgeSidecarAdapter,
    register_qq_bridge_sidecar,
)
from intel.intel_config import MONEY_CONFIG
from services.asr_client import ASRClient, ASRConfig
from services.qq_bridge_control import qq_control_service
from services.tts_client import TTSClient, TTSConfig


def _reuse_or_register_official_sidecar(
    manager: Any,
    name: str,
    adapter_type: type,
    register: Any,
    reuse_validator: Any = None,
) -> Any:
    """Make only an exact reviewed production adapter registration idempotent."""

    existing = manager.resolve_sidecar_adapter(name)
    if existing is not None:
        if type(existing) is not adapter_type:
            raise ValueError("sidecar adapter name is owned by a different implementation")
        if reuse_validator is not None and not reuse_validator(existing):
            raise ValueError("sidecar adapter is bound to a different production root")
        return existing
    try:
        adapter = register()
    except ValueError as exc:
        if str(exc) != "sidecar adapter is already registered":
            raise
        existing = manager.resolve_sidecar_adapter(name)
        if existing is None or type(existing) is not adapter_type:
            raise
        if reuse_validator is not None and not reuse_validator(existing):
            raise ValueError("sidecar adapter is bound to a different production root")
        return existing
    if type(adapter) is not adapter_type:
        raise ValueError("sidecar adapter registration returned an unexpected implementation")
    return adapter


def qq_control_route_available(snapshot: Any) -> bool:
    """Return whether the fixed local QQ control facade must be reachable."""

    return isinstance(snapshot, dict) and (
        snapshot.get("enabled") is True
        or (
            snapshot.get("type") == "sidecar"
            and snapshot.get("install_status") == "needs_configuration"
        )
    )


class InstalledModuleHost:
    """Configure stable app-state providers and trusted sidecar adapters."""

    def __init__(
        self,
        server_root: Path,
        *,
        local_read_guard: Any,
        local_write_guard: Any,
    ) -> None:
        self.server_root = Path(server_root).resolve()
        self.local_read_guard = local_read_guard
        self.local_write_guard = local_write_guard
        self.manager = get_module_manager()
        self.collectors = CollectorRegistry()
        self.asr = ASRClient(ASRConfig(
            url=os.getenv("ASR_URL", "http://127.0.0.1:8010/asr/transcribe"),
            language=os.getenv("ASR_LANGUAGE", "zh"),
            initial_prompt=os.getenv("ASR_INITIAL_PROMPT", ""),
            postprocess=os.getenv(
                "ASR_ENABLE_POSTPROCESS", "true"
            ).casefold() in {"1", "true", "yes"},
        ))
        self.tts = TTSClient(TTSConfig(
            host=os.getenv("TTS_HOST", "127.0.0.1"),
            port=int(os.getenv("TTS_PORT", "9880")),
            api_style=os.getenv("TTS_API_STYLE", "gptsovits"),
        ))
        self.runtime_control = VoiceRuntimeControlService(
            asr_launcher=self.server_root / "start_asr.bat",
            gpt_sovits_launcher=self.server_root / "start_gptsovits.bat",
            asr_readiness=self._asr_ready,
            gpt_sovits_readiness=self._gpt_sovits_registered,
        )
        # The adapter is safe to construct without the optional pinned wheel.
        # Its health remains unavailable until PK-020 installs that dependency.
        self.voice_utterance_encoder = SilkPythonUtteranceEncoder()
        self.gpt_sovits_engine_selection = LocalEngineSelectionService(
            registry=LocalEngineRegistry(
                self.server_root / "data" / "gpt_sovits_engine.local.json"
            )
        )
        self.gpt_sovits_adapter = _reuse_or_register_official_sidecar(
            self.manager,
            GPT_SOVITS_ADAPTER_NAME,
            GPTSoVITSSidecarAdapter,
            lambda: register_gpt_sovits_sidecar(self.manager),
        )
        qq_env_path = self.server_root / "qq_bridge" / ".env"
        qq_data_root = self.server_root / "qq_bridge" / "data"
        self.qq_adapter = _reuse_or_register_official_sidecar(
            self.manager,
            QQ_BRIDGE_ADAPTER_NAME,
            QQBridgeSidecarAdapter,
            lambda: register_qq_bridge_sidecar(
                self.manager,
                process_probe=self._qq_process_probe,
                process_identity_probe=self._qq_process_identity_probe,
                env_path=qq_env_path,
                data_root=qq_data_root,
            ),
            reuse_validator=lambda adapter: (
                adapter.configuration_path == qq_env_path
                and adapter.data_root == qq_data_root
            ),
        )
        self.qq_configuration_store = QQBridgeConfigurationStore(
            self.qq_adapter.configuration_path
        )
        self.qq_media_capability_provider = create_qq_media_capability_provider(
            self.qq_configuration_store
        )

    def _asr_ready(self) -> bool:
        configured = os.getenv("ASR_MODEL_PATH", "").strip()
        if configured:
            return True
        model_root = self.server_root / "models" / "asr"
        return any((model_root / name).is_dir() for name in ("medium", "small"))

    def _gpt_sovits_registered(self) -> bool:
        return (self.server_root / "data" / "gpt_sovits_engine.local.json").is_file()

    @staticmethod
    def _powershell_literal(value: str) -> str:
        return "'" + value.replace("'", "''") + "'"

    def _qq_process_probe(self, dependency_root: Path) -> bool:
        """Match only node.exe whose command line contains the exact fixed entry."""

        entry = (Path(dependency_root) / "src" / "index.mjs").resolve()
        escaped = re.escape(str(entry))
        script = (
            "$pattern = "
            + self._powershell_literal(
                r'(?i)(?:^|\s|")' + escaped + r'(?:"|\s|$)'
            )
            + "; $match = Get-CimInstance Win32_Process "
            "-Filter \"Name = 'node.exe'\" -ErrorAction SilentlyContinue | "
            "Where-Object { $_.CommandLine -match $pattern } | "
            "Select-Object -First 1; "
            "if ($null -ne $match) { [Console]::Out.Write('running') }"
        )
        try:
            result = subprocess.run(
                [
                    "powershell.exe",
                    "-NoProfile",
                    "-NonInteractive",
                    "-Command",
                    script,
                ],
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        except (OSError, subprocess.SubprocessError):
            return False
        return result.returncode == 0 and result.stdout == "running"

    def _qq_process_identity_probe(self, dependency_root: Path, process_id: int) -> bool:
        """Match one exact PID to the fixed reviewed QQ sidecar entry."""

        if not isinstance(process_id, int) or isinstance(process_id, bool) or not 0 < process_id <= 0x7FFFFFFF:
            return False
        entry = (Path(dependency_root) / "src" / "index.mjs").resolve()
        escaped = re.escape(str(entry))
        script = (
            "$pattern = "
            + self._powershell_literal(r'(?i)(?:^|\s|")' + escaped + r'(?:"|\s|$)')
            + "; $match = Get-CimInstance Win32_Process -Filter "
            + self._powershell_literal(f"ProcessId = {process_id} AND Name = 'node.exe'")
            + " -ErrorAction SilentlyContinue | Where-Object { $_.CommandLine -match $pattern }; "
            + "if ($null -ne $match) { [Console]::Out.Write('running') }"
        )
        try:
            result = subprocess.run(
                ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script],
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        except (OSError, subprocess.SubprocessError):
            return False
        return result.returncode == 0 and result.stdout == "running"

    def configure_app_state(self, app: Any) -> None:
        """Publish paths and structural Providers without reading their contents."""

        data = self.server_root / "data"
        systems_data = self.server_root / "systems" / "data"
        app.state.intel_collector_registry = self.collectors
        app.state.collector_registry = self.collectors
        app.state.intel_source_config_path = data / "intel_sources.json"
        app.state.intel_source_local_read_guard = self.local_read_guard
        app.state.intel_source_local_control_guard = self.local_write_guard
        app.state.intel_source_registry_provider = (
            lambda: getattr(app.state, "intel_source_registry", None)
        )
        app.state.intel_collector_registry_provider = lambda: self.collectors
        app.state.bilibili_data_root_provider = lambda: data
        app.state.bilibili_local_read_guard = self.local_read_guard
        app.state.bilibili_local_request_guard = self.local_write_guard
        app.state.x_monitor_profile_path = data / "x_profiles.json"
        app.state.x_monitor_posts_path = data / "x_daily_posts.json"

        app.state.daily_briefing_root_dir = self.server_root
        app.state.daily_briefing_source_config_provider = (
            lambda: self._source_snapshot(app)
        )
        app.state.daily_briefing_text_generator_provider = (
            lambda: getattr(app.state, "conversation_service", None)
        )
        app.state.daily_briefing_local_request_guard = self.local_read_guard

        app.state.conversation_profile_path = data / "llm_profile.json"
        app.state.conversation_local_read_guard = self.local_read_guard
        app.state.conversation_local_control_guard = self.local_write_guard
        app.state.affection_memory_relationship_path = data / "affection_state.json"
        app.state.affection_memory_memory_path = data / "memories.json"
        app.state.affection_memory_local_read_guard = self.local_read_guard
        app.state.affection_memory_local_control_guard = self.local_write_guard
        app.state.fitness_state_path = data / "fitness_checkins.json"
        app.state.fitness_local_read_guard = self.local_read_guard
        app.state.fitness_local_control_guard = self.local_write_guard
        app.state.focus_state_path = systems_data / "focus_timer.json"
        app.state.focus_local_request_guard = self.local_read_guard
        app.state.focus_text_generator_provider = (
            lambda: getattr(app.state, "conversation_service", None)
        )
        app.state.calendar_state_path = systems_data / "calendar_memo.json"
        app.state.demon_slayer_state_path = systems_data / "demon_slayer.json"
        app.state.demon_slayer_text_generator_provider = (
            lambda: getattr(app.state, "conversation_service", None)
        )

        app.state.papers_arxiv_cache_dir = data / "cache" / "arxiv"
        app.state.papers_today_provider = lambda: self._papers_today(app)
        app.state.papers_refresh_provider = (
            lambda source_ids: self._papers_refresh(app, source_ids)
        )
        app.state.papers_local_request_guard = self.local_write_guard
        app.state.semantic_scholar_api_key_provider = (
            lambda: os.getenv("SEMANTIC_SCHOLAR_API_KEY", "")
        )
        app.state.rss_intel_source_config_provider = (
            lambda: {
                "rss_feeds": list(MONEY_CONFIG.get("rss_feeds", ())),
                "keywords": list(MONEY_CONFIG.get("keywords", ())),
            }
        )

        app.state.voice_data_root = data / "modules" / "voice"
        app.state.voice_asr_provider = self.asr
        app.state.voice_tts_provider = self.tts
        app.state.voice_runtime_control_provider = self.runtime_control
        app.state.voice_pack_registry_path = data / "voice_pack_registry.local.json"
        app.state.voice_pack_runtime_root = self.server_root / "runtime" / "voice_packs"
        app.state.voice_pack_activator = self.tts
        app.state.voice_utterance_encoder = self.voice_utterance_encoder
        # This reads only the explicit finite operator declaration.  It never
        # infers media permission from AppID/Secret and never probes QQ.
        app.state.qq_media_upload_capability_provider = (
            self.qq_media_capability_provider
        )

    def include_core_routes(self, app: Any) -> None:
        """Mount fixed local controls that must exist before module activation."""

        app.include_router(
            create_gpt_sovits_engine_router(
                self.gpt_sovits_engine_selection,
                read_guard=self.local_read_guard,
                write_guard=self.local_write_guard,
            )
        )

    @staticmethod
    def _source_snapshot(app: Any) -> dict[str, Any]:
        provider = getattr(app.state, "intel_source_snapshot_provider", None)
        if not callable(provider):
            return {}
        try:
            value = provider()
        except Exception:
            return {}
        return dict(value) if isinstance(value, dict) else {}

    @staticmethod
    def _papers_today(app: Any) -> dict[str, Any]:
        service = getattr(app.state, "daily_briefing_service", None)
        core = getattr(service, "core", None)
        if core is None:
            return {"ready": False, "items": [], "coverage": {}, "warnings": []}
        document = core.read_today()
        if document is None:
            return {
                "ready": False,
                "date": core.today().isoformat(),
                "items": [],
                "coverage": {},
                "warnings": [],
            }
        return {"ready": True, **core.public_result(document)}

    @staticmethod
    async def _papers_refresh(app: Any, source_ids: Any) -> dict[str, Any]:
        service = getattr(app.state, "daily_briefing_service", None)
        core = getattr(service, "core", None)
        if core is None:
            return {"ready": False, "items": [], "coverage": {}, "warnings": []}
        document = await core.generate(
            source_ids=source_ids,
            refresh=True,
            rewrite=False,
            rewrite_refresh=False,
            patch_missing=True,
        )
        return {"ready": True, **core.public_result(document)}

    @staticmethod
    async def _voice_health_snapshot(app: Any) -> dict[str, Any] | None:
        """Read the installed voice service health without starting providers."""

        service = getattr(app.state, "voice_service", None)
        health = getattr(service, "health", None)
        if not callable(health):
            return None
        try:
            value = health()
            if inspect.isawaitable(value):
                value = await value
        except Exception:
            return None
        return value if isinstance(value, dict) else None

    @staticmethod
    async def _qq_media_capability_snapshot(app: Any) -> str:
        """Return only the finite non-secret permission state; unknown fails closed."""

        provider = getattr(
            app.state,
            "qq_media_upload_capability_provider",
            None,
        )
        try:
            value = provider() if callable(provider) else provider
            if inspect.isawaitable(value):
                value = await value
        except Exception:
            return "unknown"
        normalized = str(value or "unknown").casefold()
        if normalized not in {"unknown", "available", "unavailable", "denied"}:
            return "unknown"
        return normalized

    def include_enabled_sidecar_routes(self, app: Any) -> None:
        """Install the QQ facade while enabled or awaiting local configuration.

        The needs-configuration case exposes only the fixed local control and
        schedule facade.  It does not start or mark the sidecar enabled.
        """

        try:
            qq = self.manager.get("qq_bridge")
        except Exception:
            qq = None
        if qq_control_route_available(qq):
            facade = QQControlAdapterFacade(
                self.manager,
                self.qq_adapter,
                qq_control_service,
                text_generator_provider=(
                    lambda: getattr(app.state, "conversation_service", None)
                ),
                configuration_store=self.qq_configuration_store,
                voice_health_provider=(
                    lambda: self._voice_health_snapshot(app)
                ),
                qq_media_capability_provider=(
                    lambda: self._qq_media_capability_snapshot(app)
                ),
            )
            app.include_router(create_qq_control_router(
                facade,
                read_guard=self.local_read_guard,
                write_guard=self.local_write_guard,
            ))


__all__ = ["InstalledModuleHost", "qq_control_route_available"]
