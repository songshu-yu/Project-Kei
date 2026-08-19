"""Bounded HTTPS downloader with per-hop trust validation."""

from __future__ import annotations

import hashlib
import time
from pathlib import Path
from urllib.parse import urljoin, urlparse

import httpx

from ..catalog import CatalogEntry
from .errors import DistributionError


_REDIRECTS = {301, 302, 303, 307, 308}


class HTTPSDownloader:
    def __init__(
        self,
        *,
        client: httpx.Client | None = None,
        connect_timeout: float = 10.0,
        read_timeout: float = 30.0,
        total_timeout: float = 300.0,
        max_redirects: int = 4,
        clock=time.monotonic,
    ):
        self._owns_client = client is None
        self.client = client or httpx.Client(
            timeout=httpx.Timeout(
                connect=connect_timeout,
                read=read_timeout,
                write=read_timeout,
                pool=connect_timeout,
            ),
            follow_redirects=False,
            trust_env=False,
        )
        self.total_timeout = float(total_timeout)
        self.max_redirects = int(max_redirects)
        self.clock = clock

    @staticmethod
    def _trusted(url: str, allowed_hosts: tuple[str, ...]) -> str:
        parsed = urlparse(url)
        if (
            parsed.scheme != "https"
            or (parsed.hostname or "").lower() not in set(allowed_hosts)
            or parsed.username is not None
            or parsed.password is not None
            or parsed.fragment
        ):
            raise DistributionError(
                "download target is not trusted", code="voice_pack_source_untrusted"
            )
        return url

    def download(self, entry: CatalogEntry, destination: Path) -> dict[str, object]:
        current = self._trusted(entry.download_url, entry.allowed_redirect_hosts)
        deadline = self.clock() + self.total_timeout
        redirects = 0
        digest = hashlib.sha256()
        total = 0
        try:
            while True:
                if self.clock() > deadline:
                    raise DistributionError(
                        "Voice Pack download timed out", code="voice_pack_download_timeout"
                    )
                request = self.client.build_request("GET", current)
                response = self.client.send(request, stream=True)
                try:
                    if response.status_code in _REDIRECTS:
                        location = response.headers.get("location")
                        if not location or redirects >= self.max_redirects:
                            raise DistributionError(
                                "Voice Pack redirect policy rejected the response",
                                code="voice_pack_redirect_rejected",
                            )
                        current = self._trusted(
                            urljoin(current, location), entry.allowed_redirect_hosts
                        )
                        redirects += 1
                        continue
                    if response.status_code != 200:
                        raise DistributionError(
                            "Voice Pack download failed",
                            code="voice_pack_download_failed",
                        )
                    declared = response.headers.get("content-length")
                    if declared is not None:
                        try:
                            declared_size = int(declared)
                        except ValueError as exc:
                            raise DistributionError(
                                "Voice Pack response size is invalid",
                                code="voice_pack_size_mismatch",
                            ) from exc
                        if declared_size != entry.size_bytes:
                            raise DistributionError(
                                "Voice Pack response size does not match catalog",
                                code="voice_pack_size_mismatch",
                            )
                    with Path(destination).open("xb") as output:
                        for chunk in response.iter_bytes(1024 * 1024):
                            if self.clock() > deadline:
                                raise DistributionError(
                                    "Voice Pack download timed out",
                                    code="voice_pack_download_timeout",
                                )
                            total += len(chunk)
                            if total > entry.size_bytes:
                                raise DistributionError(
                                    "Voice Pack response exceeds catalog size",
                                    code="voice_pack_size_mismatch",
                                )
                            output.write(chunk)
                            digest.update(chunk)
                    break
                finally:
                    response.close()
        except DistributionError:
            Path(destination).unlink(missing_ok=True)
            raise
        except httpx.TimeoutException as exc:
            Path(destination).unlink(missing_ok=True)
            raise DistributionError(
                "Voice Pack download timed out", code="voice_pack_download_timeout"
            ) from exc
        except (httpx.HTTPError, OSError) as exc:
            Path(destination).unlink(missing_ok=True)
            raise DistributionError(
                "Voice Pack download failed", code="voice_pack_download_failed"
            ) from exc
        if total != entry.size_bytes or digest.hexdigest() != entry.sha256:
            Path(destination).unlink(missing_ok=True)
            raise DistributionError(
                "Voice Pack integrity does not match catalog",
                code="voice_pack_integrity_mismatch",
            )
        return {"size_bytes": total, "sha256": digest.hexdigest(), "redirects": redirects}

    def close(self) -> None:
        if self._owns_client:
            self.client.close()
