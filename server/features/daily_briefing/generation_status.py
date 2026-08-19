"""Bounded, process-local observability for PK-110 generation mutations."""
from __future__ import annotations

import threading
from datetime import datetime
from typing import Iterable

from .models import PUBLIC_SOURCE_IDS, CollectorResult, CoverageStatus, rfc3339


GENERATION_STATES = frozenset({"idle", "running", "succeeded", "failed"})
GENERATION_PHASES = frozenset({"idle", "collecting", "rewriting", "saving", "finished"})
SOURCE_PROGRESS_STATES = frozenset({
    "not_requested",
    "pending",
    "running",
    "complete",
    "partial",
    "empty",
    "failed",
    "not_configured",
})
GENERATION_ERROR_CODES = frozenset({
    "cancelled",
    "cache_save_failed",
    "generation_failed",
})
SOURCE_ERROR_CODES = frozenset({
    "access_denied",
    "anti_bot",
    "http_error",
    "invalid_response",
    "network_error",
    "not_found",
    "parse_error",
    "rate_limited",
    "redirect_missing_location",
    "redirect_rejected",
    "response_too_large",
    "timeout",
    "too_many_redirects",
    "upstream_failed",
    "upstream_rejected",
    "upstream_unavailable",
})
_TERMINAL_SOURCE_STATES = frozenset({
    "complete",
    "partial",
    "empty",
    "failed",
    "not_configured",
})
_MAX_ELAPSED_MS = 7 * 24 * 60 * 60 * 1000


class BriefingGenerationTracker:
    """Keep one sanitized status snapshot and reject stale run updates."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._sequence = 0
        self._state = "idle"
        self._phase = "idle"
        self._started_at: datetime | None = None
        self._finished_at: datetime | None = None
        self._selected: tuple[str, ...] = ()
        self._sources = {source_id: "not_requested" for source_id in PUBLIC_SOURCE_IDS}
        self._source_error_codes = {source_id: () for source_id in PUBLIC_SOURCE_IDS}
        self._error_code: str | None = None

    def start(self, source_ids: Iterable[str], now: datetime) -> int:
        requested = set(str(value) for value in source_ids)
        selected = tuple(source_id for source_id in PUBLIC_SOURCE_IDS if source_id in requested)
        with self._lock:
            self._sequence += 1
            self._state = "running"
            self._phase = "collecting"
            self._started_at = now
            self._finished_at = None
            self._selected = selected
            selected_public = set(selected)
            self._sources = {
                source_id: ("pending" if source_id in selected_public else "not_requested")
                for source_id in PUBLIC_SOURCE_IDS
            }
            self._source_error_codes = {source_id: () for source_id in PUBLIC_SOURCE_IDS}
            self._error_code = None
            return self._sequence

    def collecting(self, token: int, source_ids: Iterable[str]) -> None:
        requested = set(str(value) for value in source_ids)
        selected = tuple(source_id for source_id in PUBLIC_SOURCE_IDS if source_id in requested)
        with self._lock:
            if token != self._sequence or self._state != "running":
                return
            self._phase = "collecting"
            self._selected = selected
            self._sources = {
                source_id: ("running" if source_id in selected else "not_requested")
                for source_id in PUBLIC_SOURCE_IDS
            }
            self._source_error_codes = {source_id: () for source_id in PUBLIC_SOURCE_IDS}

    def source_finished(self, token: int, result: CollectorResult) -> None:
        status = {
            CoverageStatus.COMPLETE: "complete",
            CoverageStatus.PARTIAL: "partial",
            CoverageStatus.EMPTY: "empty",
            CoverageStatus.FAILED: "failed",
            CoverageStatus.NOT_CONFIGURED: "not_configured",
        }[result.coverage.status]
        codes = tuple(
            code
            for code in sorted(SOURCE_ERROR_CODES)
            if any(f"({code})" in str(warning).casefold() for warning in result.warnings)
        )
        with self._lock:
            if token != self._sequence or self._state != "running":
                return
            if result.source_id in self._sources:
                self._sources[result.source_id] = status
                self._source_error_codes[result.source_id] = codes

    def collection_not_needed(self, token: int) -> None:
        with self._lock:
            if token != self._sequence or self._state != "running":
                return
            self._selected = ()
            self._sources = {source_id: "not_requested" for source_id in PUBLIC_SOURCE_IDS}
            self._source_error_codes = {source_id: () for source_id in PUBLIC_SOURCE_IDS}

    def phase(self, token: int, phase: str) -> None:
        if phase not in GENERATION_PHASES or phase in {"idle", "finished"}:
            raise ValueError("invalid active generation phase")
        with self._lock:
            if token == self._sequence and self._state == "running":
                self._phase = phase

    def succeed(self, token: int, now: datetime) -> None:
        self._finish(token, now, state="succeeded", error_code=None)

    def fail(self, token: int, now: datetime, error_code: str) -> None:
        safe_code = error_code if error_code in GENERATION_ERROR_CODES else "generation_failed"
        self._finish(token, now, state="failed", error_code=safe_code)

    def _finish(self, token: int, now: datetime, *, state: str, error_code: str | None) -> None:
        with self._lock:
            if token != self._sequence:
                return
            self._state = state
            self._phase = "finished"
            self._finished_at = now
            self._error_code = error_code

    def snapshot(self, now: datetime) -> dict[str, object]:
        with self._lock:
            started = self._started_at
            finished = self._finished_at
            endpoint = finished or now
            elapsed_ms = 0
            if started is not None:
                elapsed_ms = max(0, int((endpoint - started).total_seconds() * 1000))
            elapsed_ms = min(elapsed_ms, _MAX_ELAPSED_MS)
            completed = sum(
                1
                for source_id in self._selected
                if self._sources.get(source_id) in _TERMINAL_SOURCE_STATES
            )
            return {
                "state": self._state,
                "phase": self._phase,
                "started_at": rfc3339(started) if started is not None else None,
                "finished_at": rfc3339(finished) if finished is not None else None,
                "elapsed_ms": elapsed_ms,
                "completed_sources": completed,
                "total_sources": len(self._selected),
                "sources": dict(self._sources),
                "source_error_codes": {
                    source_id: list(self._source_error_codes[source_id])
                    for source_id in PUBLIC_SOURCE_IDS
                },
                "error_code": self._error_code,
            }


__all__ = [
    "BriefingGenerationTracker",
    "GENERATION_ERROR_CODES",
    "GENERATION_PHASES",
    "GENERATION_STATES",
    "SOURCE_ERROR_CODES",
    "SOURCE_PROGRESS_STATES",
]
