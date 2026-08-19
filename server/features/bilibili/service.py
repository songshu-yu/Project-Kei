"""Use-case boundary for Bilibili UID display profiles."""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Mapping, Optional, Sequence

from features.bilibili.client import BilibiliClientError, BilibiliPublicClient, normalize_uid
from features.bilibili.credentials import (
    BilibiliCredentialRepository,
    BilibiliCredentials,
)
from core.intel_contracts import CollectRequest, CoverageStatus
from intel.collectors.bilibili import BilibiliCollector
from services.bilibili_profile_cache import (
    DEFAULT_PATH,
    ProfileFetcher,
    get_bilibili_profiles,
    resolve_bilibili_profiles,
    store_bilibili_profiles,
)


UidProvider = Callable[[], Sequence[object]]
ClientFactory = Callable[[BilibiliCredentials], BilibiliPublicClient]
GLOBAL_UPSTREAM_FAILURE_CODES = frozenset({
    "anti_bot",
    "rate_limited",
    "timeout",
    "upstream_failed",
    "upstream_rejected",
    "upstream_unavailable",
    "wbi_key_unavailable",
})


class BilibiliCredentialValidationError(RuntimeError):
    """A safe validation failure that never embeds upstream text or secrets."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = str(code or "validation_failed")[:80]
        self.message = str(message or "B 站参数验证失败，请检查后重试。")[:160]


def _default_client_factory(credentials: BilibiliCredentials) -> BilibiliPublicClient:
    return BilibiliPublicClient(cookies=credentials.as_cookies())


class BilibiliService:
    """Keep source-list ownership outside PK-130 via an injected provider."""

    def __init__(
        self,
        uid_provider: UidProvider,
        *,
        profile_path: str | Path = DEFAULT_PATH,
        profile_fetcher: Optional[ProfileFetcher] = None,
        now: Optional[datetime] = None,
        credential_repository: Optional[BilibiliCredentialRepository] = None,
        client_factory: ClientFactory = _default_client_factory,
    ) -> None:
        self._uid_provider = uid_provider
        self._profile_path = Path(profile_path)
        self._profile_fetcher = profile_fetcher
        self._now = now
        self._credential_repository = credential_repository or BilibiliCredentialRepository()
        self._client_factory = client_factory
        # Module registration is synchronous and may happen before an asyncio
        # event loop exists (or after a previous test loop was closed). Create
        # the lock lazily inside the first async mutation instead.
        self._mutation_lock: Optional[asyncio.Lock] = None
        self._mutation_loop: Optional[asyncio.AbstractEventLoop] = None
        self._operation_state = "idle"

    def _lock(self) -> asyncio.Lock:
        loop = asyncio.get_running_loop()
        if self._mutation_lock is None or self._mutation_loop is not loop:
            self._mutation_lock = asyncio.Lock()
            self._mutation_loop = loop
        return self._mutation_lock

    def configured_uids(self) -> list[int]:
        result: list[int] = []
        seen: set[int] = set()
        for value in self._uid_provider():
            uid = normalize_uid(value)
            if uid not in seen:
                seen.add(uid)
                result.append(uid)
        return result

    def _selected_uids(self, uid: Optional[int]) -> list[int]:
        configured = self.configured_uids()
        if uid is None:
            return configured
        normalized = normalize_uid(uid)
        if normalized not in configured:
            raise ValueError("Bilibili UID is not in the current source list")
        return [normalized]

    def read_profiles(self, uid: Optional[int] = None) -> dict:
        return get_bilibili_profiles(
            self._selected_uids(uid),
            path=self._profile_path,
        )

    async def resolve_profiles(self, uid: Optional[int] = None, *, refresh: bool = False) -> dict:
        return await resolve_bilibili_profiles(
            self._selected_uids(uid),
            refresh=refresh,
            path=self._profile_path,
            fetcher=self._profile_fetcher,
            now=self._now,
        )

    def credential_status(self) -> dict:
        status = self._credential_repository.status()
        status["operation_state"] = self._operation_state
        return status

    async def save_credentials(self, values: Mapping[str, object]) -> dict:
        """Atomically stage candidate values without performing network I/O."""
        async with self._lock():
            self._operation_state = "idle"
            status = self._credential_repository.save_candidate(values)
            status["operation_state"] = self._operation_state
            return status

    def _clock(self) -> datetime:
        value = self._now or datetime.now(timezone.utc)
        if value.tzinfo is None or value.utcoffset() is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)

    async def validate_and_collect(self) -> dict:
        """Validate candidate/active credentials, then collect profiles and dynamics.

        Profile cache changes occur only after validation and dynamic collection
        both succeed. The daily briefing cache remains owned by PK-110 and is not
        rewritten by this source-specific operation.
        """
        async with self._lock():
            self._operation_state = "validating"
            credentials, is_candidate = self._credential_repository.pending_or_active()
            if credentials is None:
                self._operation_state = "idle"
                raise BilibiliCredentialValidationError(
                    "credentials_missing",
                    "请先填写并保存三项 B 站参数。",
                )
            uids = self.configured_uids()
            if not uids:
                self._operation_state = "idle"
                raise BilibiliCredentialValidationError(
                    "uid_missing",
                    "请先在 B 站栏目添加至少一个 UID。",
                )
            status = self._credential_repository.status()
            retry_after = str(status.get("retry_after") or "")
            if status.get("state") == "invalid" and retry_after:
                try:
                    retry_time = datetime.fromisoformat(retry_after)
                except ValueError:
                    retry_time = None
                if retry_time is not None and retry_time > self._clock():
                    self._operation_state = "failed"
                    raise BilibiliCredentialValidationError(
                        "validation_cooldown",
                        f"当前参数验证失败后正在冷却，请更新参数或在 {retry_after} 后重试。",
                    )

            client = self._client_factory(credentials)
            public_profiles: dict[int, dict] = {}
            profile_failures = 0
            try:
                for uid in uids:
                    try:
                        public_profiles[uid] = await client.fetch_profile(uid)
                    except BilibiliClientError as exc:
                        profile_failures += 1
                        # These failures describe the shared session/network/WBI
                        # boundary, not one UID. Retrying the same failure for
                        # every configured UID only hides the root cause and can
                        # make a single validation take several minutes.
                        if exc.code in GLOBAL_UPSTREAM_FAILURE_CODES:
                            self._credential_repository.mark_validation_failed(
                                candidate=is_candidate,
                                error_code=exc.code,
                            )
                            raise BilibiliCredentialValidationError(
                                exc.code,
                                "B 站公共接口暂时拒绝了本次验证；旧参数与已有缓存均未更改。",
                            )
                    except ValueError:
                        profile_failures += 1

                collector = BilibiliCollector(client=client, now=self._clock)
                request = CollectRequest(
                    local_date=self._clock().date(),
                    timezone="Asia/Shanghai",
                    source_ids=("bilibili",),
                    refresh=True,
                    lookback=24,
                    source_config_snapshot={"bilibili_uids": list(uids)},
                )
                result = await collector.collect(request)
                if not public_profiles or result.coverage.status is CoverageStatus.FAILED:
                    self._credential_repository.mark_validation_failed(
                        candidate=is_candidate,
                        error_code="upstream_parameters_rejected",
                    )
                    raise BilibiliCredentialValidationError(
                        "upstream_parameters_rejected",
                        "B 站未接受当前参数，旧参数和已有缓存均未更改。",
                    )

                if is_candidate:
                    self._credential_repository.promote_candidate()
                else:
                    self._credential_repository.mark_active_validated()

                cache_updated = True
                cache_warning = ""
                try:
                    profiles = store_bilibili_profiles(
                        public_profiles,
                        path=self._profile_path,
                        now=self._clock(),
                    )
                except OSError:
                    cache_updated = False
                    cache_warning = "资料已验证，但本机资料缓存暂未更新。"
                    profiles = self.read_profiles()

                self._operation_state = "succeeded"
                response = {
                    "credential_status": self.credential_status(),
                    "profiles": profiles.get("profiles", {}),
                    "profile_failures": profile_failures,
                    "profile_cache_updated": cache_updated,
                    "collection": {
                        "source_id": result.source_id,
                        "status": result.coverage.status.value,
                        "item_count": result.coverage.item_count,
                        "fetched_at": result.fetched_at,
                        "retry_after": result.retry_after,
                        "warnings": list(result.warnings),
                    },
                    "message": (
                        "B 站参数已验证并完成资料与动态采集。"
                        if cache_updated
                        else cache_warning
                    ),
                }
                return response
            except BilibiliCredentialValidationError:
                self._operation_state = "failed"
                raise
            except (BilibiliClientError, ValueError):
                self._credential_repository.mark_validation_failed(
                    candidate=is_candidate,
                    error_code="validation_failed",
                )
                self._operation_state = "failed"
                raise BilibiliCredentialValidationError(
                    "validation_failed",
                    "B 站参数验证失败，旧参数和已有缓存均未更改。",
                )
            finally:
                await client.aclose()


__all__ = [
    "BilibiliCredentialValidationError",
    "BilibiliService",
    "ClientFactory",
    "GLOBAL_UPSTREAM_FAILURE_CODES",
    "UidProvider",
]
