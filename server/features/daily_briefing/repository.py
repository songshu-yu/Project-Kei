"""Atomic local cache repository owned by PK-110."""
from __future__ import annotations

import hashlib
import json
import os
import uuid
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping, Optional

from .collector_gateway import _legacy_timestamp
from .models import (
    BRIEFING_CACHE_SCHEMA_VERSION,
    PUBLIC_SOURCE_IDS,
    BriefingDocument,
    CacheStatus,
    CoverageStatus,
    IntelItem,
    SourceCoverage,
    rfc3339,
    sanitize_external_text,
    stable_item_id,
)


class BriefingCacheError(RuntimeError):
    pass


class BriefingCachePersistenceError(BriefingCacheError):
    def __init__(self, message: str, *, cache_state_preserved: bool):
        super().__init__(message)
        self.cache_state_preserved = bool(cache_state_preserved)


def document_digest(document: BriefingDocument) -> str:
    material = {
        "date": document.local_date,
        "text": document.text,
        "items": [item.to_dict() for item in document.items],
        "coverage": {key: value.to_dict() for key, value in sorted(document.coverage.items())},
        "warnings": list(document.warnings),
    }
    encoded = json.dumps(material, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


class BriefingRepository:
    def __init__(
        self,
        root_dir: str | Path,
        *,
        replace: Callable[[str | Path, str | Path], None] = os.replace,
    ):
        self.root_dir = Path(root_dir)
        self.cache_dir = self.root_dir / "data" / "briefing_cache"
        self.summary_path = self.cache_dir / "kei_summary_today.json"
        self._replace = replace

    def cache_path(self, local_date: date | str) -> Path:
        value = local_date.isoformat() if isinstance(local_date, date) else date.fromisoformat(str(local_date)).isoformat()
        return self.cache_dir / f"{value}.json"

    @staticmethod
    def _write_json_temp(path: Path, payload: Mapping[str, Any]) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
        try:
            with temp_path.open("w", encoding="utf-8", newline="\n") as handle:
                json.dump(payload, handle, ensure_ascii=False, indent=2)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            return temp_path
        except Exception:
            try:
                temp_path.unlink()
            except OSError:
                pass
            raise

    @staticmethod
    def _snapshot(path: Path) -> Optional[bytes]:
        try:
            return path.read_bytes()
        except FileNotFoundError:
            return None

    @staticmethod
    def _restore(path: Path, snapshot: Optional[bytes]) -> None:
        if snapshot is None:
            try:
                path.unlink()
            except FileNotFoundError:
                return
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        restore_path = path.with_name(f".{path.name}.{uuid.uuid4().hex}.restore.tmp")
        try:
            with restore_path.open("wb") as handle:
                handle.write(snapshot)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(restore_path, path)
        finally:
            try:
                restore_path.unlink()
            except FileNotFoundError:
                pass

    @staticmethod
    def _cleanup_temp(path: Path) -> None:
        try:
            path.unlink()
        except FileNotFoundError:
            pass

    def _commit_payloads(self, payloads: list[tuple[Path, Mapping[str, Any]]]) -> None:
        staged: list[tuple[Path, Path]] = []
        snapshots: dict[Path, Optional[bytes]] = {}
        try:
            for target, payload in payloads:
                snapshots[target] = self._snapshot(target)
                staged.append((target, self._write_json_temp(target, payload)))
        except Exception as exc:
            for _, temp_path in staged:
                self._cleanup_temp(temp_path)
            raise BriefingCachePersistenceError(
                "briefing cache could not be staged",
                cache_state_preserved=True,
            ) from exc

        try:
            for target, temp_path in staged:
                self._replace(temp_path, target)
        except Exception as exc:
            rollback_ok = True
            for target, _ in staged:
                try:
                    self._restore(target, snapshots[target])
                except OSError:
                    rollback_ok = False
            for _, temp_path in staged:
                self._cleanup_temp(temp_path)
            raise BriefingCachePersistenceError(
                "briefing cache transaction failed",
                cache_state_preserved=rollback_ok,
            ) from exc
        finally:
            for _, temp_path in staged:
                self._cleanup_temp(temp_path)

    def _atomic_json(self, path: Path, payload: Mapping[str, Any]) -> None:
        self._commit_payloads([(path, payload)])

    @staticmethod
    def _legacy_warning_matches(source_id: str, warning: object) -> bool:
        markers = {
            "arxiv": ("arxiv",),
            "crossref": ("crossref",),
            "semantic": ("semantic scholar", "semantic"),
            "twitter": ("twitter", "nitter"),
            "github": ("github",),
            "bilibili": ("bilibili",),
            "youtube": ("youtube",),
            "money": ("money_tips", "v2ex", "hacker news", "product hunt"),
        }
        value = str(warning or "").casefold()
        return any(marker in value for marker in markers[source_id])

    def _legacy_document(self, value: Mapping[str, Any], path: Path, expected_date: date) -> BriefingDocument:
        local_date = str(value.get("date", ""))
        if local_date != expected_date.isoformat():
            raise ValueError("legacy cache date mismatch")
        fetched_at = rfc3339(datetime.fromtimestamp(path.stat().st_mtime, timezone.utc))
        category_source = {
            "twitter": "twitter",
            "github": "github",
            "bilibili": "bilibili",
            "youtube": "youtube",
            "money": "money",
        }
        items: list[IntelItem] = []
        for category, values in (value.get("items", {}) or {}).items():
            for raw in values or []:
                if not isinstance(raw, Mapping):
                    continue
                source_id = category_source.get(category, "")
                if category == "papers":
                    label = str(raw.get("source", "")).casefold()
                    source_id = "crossref" if label == "crossref" else "semantic" if label in {"semantic", "semantic_scholar"} else "arxiv"
                if not source_id:
                    continue
                title = str(raw.get("title", ""))
                if not title.strip():
                    continue
                published_at = _legacy_timestamp(raw.get("published", ""), "Asia/Shanghai")
                author = "" if category == "papers" else str(raw.get("source", ""))
                try:
                    items.append(IntelItem(
                        stable_id=stable_item_id(
                            source_id,
                            url=raw.get("url", ""),
                            title=title,
                            author=author,
                            published_at=published_at,
                        ),
                        source_id=source_id,
                        category="papers" if category == "papers" else category,
                        title=title,
                        summary=raw.get("summary", ""),
                        url=raw.get("url", ""),
                        author=author,
                        published_at=published_at,
                        fetched_at=fetched_at,
                        metadata={"legacy_source_label": raw.get("source", "")},
                    ))
                except ValueError:
                    continue
        warnings = [
            cleaned
            for item in value.get("warnings", [])
            if (cleaned := sanitize_external_text(item, limit=240))
        ]
        coverage: dict[str, SourceCoverage] = {}
        for source_id in PUBLIC_SOURCE_IDS:
            count = sum(1 for item in items if item.source_id == source_id)
            failed = any(self._legacy_warning_matches(source_id, warning) for warning in warnings)
            status = CoverageStatus.PARTIAL if failed and count else CoverageStatus.FAILED if failed else CoverageStatus.COMPLETE if count else CoverageStatus.EMPTY
            coverage[source_id] = SourceCoverage(status, count, "migrated from legacy cache")
        created_at = fetched_at
        return BriefingDocument(
            local_date=local_date,
            timezone="Asia/Shanghai",
            items=items,
            coverage=coverage,
            warnings=warnings,
            text=str(value.get("text", "")),
            script=str(value.get("script", "")),
            fetched=bool(value.get("fetched", False)),
            rewritten=bool(value.get("rewritten", False)),
            rewrite_status="generated" if value.get("rewritten") else "not_requested",
            created_at=created_at,
            updated_at=created_at,
            patch_attempts={str(key): _legacy_timestamp(item, "Asia/Shanghai") for key, item in (value.get("patch_attempts", {}) or {}).items() if str(key) in PUBLIC_SOURCE_IDS and _legacy_timestamp(item, "Asia/Shanghai")},
            cache_status=CacheStatus.HIT,
        )

    def load(self, local_date: date) -> Optional[BriefingDocument]:
        path = self.cache_path(local_date)
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return None
        except (OSError, json.JSONDecodeError, UnicodeError):
            return None
        if not isinstance(payload, Mapping):
            return None
        try:
            legacy_cache = "schema_version" not in payload and "date" in payload
            if legacy_cache:
                document = self._legacy_document(payload, path, local_date)
            else:
                document = BriefingDocument.from_dict(payload)
                if document.local_date != local_date.isoformat():
                    return None
            document.cache_status = CacheStatus.HIT
            summary = self.load_summary(
                local_date,
                document_digest(document),
                allow_legacy_undigested=legacy_cache,
            )
            if summary:
                document.script = summary["text"]
                document.rewritten = bool(summary["generated"])
                document.rewrite_status = "generated" if summary["generated"] else "fallback"
            return document
        except (KeyError, TypeError, ValueError):
            return None

    @staticmethod
    def _main_payload(document: BriefingDocument) -> dict[str, Any]:
        payload = document.to_dict(include_cache_status=False)
        # The narration has its own current-day cache and is intentionally not
        # embedded in the normalized item cache.
        payload["script"] = ""
        payload["rewritten"] = False
        payload["rewrite_status"] = "not_requested"
        return payload

    @staticmethod
    def _summary_payload(document: BriefingDocument, *, generated: bool, fallback: bool) -> dict[str, Any]:
        return {
            "schema_version": BRIEFING_CACHE_SCHEMA_VERSION,
            "date": document.local_date,
            "text": document.script,
            "generated": bool(generated),
            "fallback": bool(fallback),
            "updated_at": document.updated_at,
            "source_digest": document_digest(document),
        }

    def save(self, document: BriefingDocument) -> None:
        self._atomic_json(self.cache_path(document.local_date), self._main_payload(document))

    def save_transaction(self, document: BriefingDocument, *, include_summary: bool) -> None:
        payloads: list[tuple[Path, Mapping[str, Any]]] = [
            (self.cache_path(document.local_date), self._main_payload(document)),
        ]
        if include_summary:
            if not document.script.strip():
                raise ValueError("summary transaction requires narration text")
            payloads.append((
                self.summary_path,
                self._summary_payload(
                    document,
                    generated=document.rewritten,
                    fallback=not document.rewritten,
                ),
            ))
        self._commit_payloads(payloads)

    def load_summary(
        self,
        local_date: date,
        source_digest: str,
        *,
        allow_legacy_undigested: bool = False,
    ) -> Optional[dict[str, Any]]:
        try:
            payload = json.loads(self.summary_path.read_text(encoding="utf-8"))
        except (FileNotFoundError, OSError, json.JSONDecodeError, UnicodeError):
            return None
        if not isinstance(payload, Mapping):
            return None
        if payload.get("date") != local_date.isoformat():
            return None
        text = sanitize_external_text(
            payload.get("text", ""),
            limit=200_000,
            collapse_whitespace=False,
        )
        if not text:
            return None
        cached_digest = str(payload.get("source_digest", ""))
        # Legacy summary cache had no digest. It remains readable only when the
        # main cache was also legacy; callers may explicitly regenerate later.
        if cached_digest and cached_digest != source_digest:
            return None
        if not cached_digest and not allow_legacy_undigested:
            return None
        return {
            "schema_version": int(payload.get("schema_version", 0) or 0),
            "date": local_date.isoformat(),
            "text": text,
            "generated": bool(payload.get("generated", True)),
            "fallback": bool(payload.get("fallback", False)),
            "updated_at": payload.get("updated_at"),
            "source_digest": cached_digest,
        }

    def save_summary(self, document: BriefingDocument, *, generated: bool, fallback: bool) -> None:
        if not document.script.strip():
            return
        payload = self._summary_payload(document, generated=generated, fallback=fallback)
        self._atomic_json(self.summary_path, payload)

    def invalidate_stale_summary(self, today: date) -> bool:
        try:
            payload = json.loads(self.summary_path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return False
        except (OSError, json.JSONDecodeError, UnicodeError):
            return False
        if isinstance(payload, Mapping) and payload.get("date") == today.isoformat():
            return False
        try:
            self.summary_path.unlink()
            return True
        except OSError:
            return False


__all__ = [
    "BriefingCacheError",
    "BriefingCachePersistenceError",
    "BriefingRepository",
    "document_digest",
]
