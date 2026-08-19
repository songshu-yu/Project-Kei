"""Controlled optional silk-python adapter for ``qq_c2c_voice_v1``.

The dependency is deliberately imported only by a short-lived isolated worker.
Core and the voice module therefore remain importable when the optional wheel is
not installed.  PK-020 owns installing the exact wheel through the voice profile.
"""
from __future__ import annotations

import asyncio
import importlib.util
import platform
import subprocess
import sys
from importlib import metadata
from typing import Awaitable, Callable, Dict, Optional, Tuple

from .media import OUTPUT_MEDIA_TYPE, OUTPUT_PROFILE
from .models import (
    EncodedUtterance,
    ProviderCapabilities,
    ProviderHealth,
    UtteranceEncodingRequest,
)


SILK_DISTRIBUTION = "silk-python"
SILK_IMPORT_NAME = "pysilk"
SILK_VERSION = "0.2.8"
SILK_SOURCE = "https://pypi.org/project/silk-python/0.2.8/"
SILK_LICENSE = "BSD (binding metadata); bundled silk-v3-decoder revision is MIT"
SILK_TENCENT_HEADER = b"\x02#!SILK_V3"
MAX_PCM_BYTES = 24_000 * 1 * 2 * 60
MAX_SILK_BYTES = 8 * 1024 * 1024
DEFAULT_TIMEOUT_SECONDS = 30.0

# PyPI file hashes for the only supported production target: Windows CPython x64.
WINDOWS_X64_WHEEL_SHA256 = {
    "cp310": "6f4533e320239c0599ef272654f230020442d94273be457f136ce8c48b4aa808",
    "cp311": "3afcebce1dd18130d352a2d669a8b16977c36b789d5f708c379959a08b05a3f5",
    "cp312": "b9bb030589150e0d91f8148971eebf6f9211e6839af64dd39b26b9802be242b0",
    "cp313": "450dc26c71e9fd3cbdc694319d5fb24aae50d20321c9e29982d358aafbee628c",
}

_WORKER = r"""
import io
import sys
from importlib import metadata

try:
    if metadata.version("silk-python") != "0.2.8":
        raise RuntimeError("version")
    import pysilk
    pcm = sys.stdin.buffer.read(2880001)
    if not pcm or len(pcm) > 2880000 or len(pcm) % 2:
        raise RuntimeError("input")
    output = io.BytesIO()
    pysilk.encode(
        io.BytesIO(pcm), output, 24000, 24000,
        max_internal_sample_rate=24000,
        packet_loss_percentage=0,
        complexity=2,
        use_inband_fec=False,
        use_dtx=False,
        tencent=True,
    )
    encoded = output.getvalue()
    if (not encoded or len(encoded) > 8388608
            or not encoded.startswith(b"\x02#!SILK_V3")):
        raise RuntimeError("output")
    sys.stdout.buffer.write(encoded)
except BaseException:
    raise SystemExit(20)
"""


class SilkEncoderError(RuntimeError):
    """Stable internal error; callers must publish only the code."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


ProcessFactory = Callable[[], Awaitable[asyncio.subprocess.Process]]
VersionProvider = Callable[[str], str]
ModuleProbe = Callable[[str], bool]
RuntimeProbe = Callable[[], bool]


def _module_available(name: str) -> bool:
    try:
        return importlib.util.find_spec(name) is not None
    except (ImportError, AttributeError, ValueError):
        return False


def _supported_runtime() -> bool:
    return (
        sys.platform == "win32"
        and sys.implementation.name == "cpython"
        and (3, 10) <= sys.version_info[:2] <= (3, 13)
        and platform.machine().casefold() in {"amd64", "x86_64"}
    )


async def _default_process_factory() -> asyncio.subprocess.Process:
    return await asyncio.create_subprocess_exec(
        sys.executable,
        "-I",
        "-c",
        _WORKER,
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.DEVNULL,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )


class SilkPythonUtteranceEncoder:
    """Encode fixed normalized PCM with a pinned local ``silk-python`` wheel."""

    def __init__(
        self,
        *,
        process_factory: ProcessFactory = _default_process_factory,
        version_provider: VersionProvider = metadata.version,
        module_probe: ModuleProbe = _module_available,
        runtime_probe: RuntimeProbe = _supported_runtime,
        max_concurrency: int = 2,
    ) -> None:
        if max_concurrency < 1 or max_concurrency > 4:
            raise ValueError("max_concurrency must be between 1 and 4")
        self._process_factory = process_factory
        self._version_provider = version_provider
        self._module_probe = module_probe
        self._runtime_probe = runtime_probe
        self._semaphore = asyncio.Semaphore(max_concurrency)
        self._lock = asyncio.Lock()
        self._processes: Dict[str, asyncio.subprocess.Process] = {}
        self._closed = False

    def _dependency_ready(self) -> Tuple[bool, Optional[str]]:
        if self._closed:
            return False, "encoder_closed"
        try:
            if not self._runtime_probe():
                return False, "runtime_unsupported"
            if self._version_provider(SILK_DISTRIBUTION) != SILK_VERSION:
                return False, "dependency_version_mismatch"
            if not self._module_probe(SILK_IMPORT_NAME):
                return False, "dependency_missing"
        except metadata.PackageNotFoundError:
            return False, "dependency_missing"
        except Exception:
            return False, "dependency_unavailable"
        return True, None

    async def health(self) -> ProviderHealth:
        ready, code = self._dependency_ready()
        return ProviderHealth(
            available=ready,
            status="available" if ready else "unavailable",
            error_code=code,
        )

    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(
            provider="silk-python/%s" % SILK_VERSION,
            operations=("encode",),
            audio_formats=(OUTPUT_PROFILE,),
            streaming=False,
            cancellable=True,
            default_timeout_seconds=DEFAULT_TIMEOUT_SECONDS,
        )

    @staticmethod
    def _validate(request: UtteranceEncodingRequest) -> None:
        if (
            request.output_profile != OUTPUT_PROFILE
            or request.sample_rate != 24_000
            or request.channels != 1
            or request.sample_width != 2
            or not isinstance(request.pcm_s16le, bytes)
            or not request.pcm_s16le
            or len(request.pcm_s16le) > MAX_PCM_BYTES
            or len(request.pcm_s16le) % 2
            or not 0 < request.timeout_seconds <= DEFAULT_TIMEOUT_SECONDS
        ):
            raise SilkEncoderError("encoding_request_invalid")

    @staticmethod
    async def _stop_process(process: asyncio.subprocess.Process) -> None:
        if process.returncode is not None:
            return
        try:
            process.terminate()
        except ProcessLookupError:
            return
        try:
            await asyncio.wait_for(process.wait(), timeout=1.0)
        except (asyncio.TimeoutError, ProcessLookupError):
            try:
                process.kill()
            except ProcessLookupError:
                return
            try:
                await process.wait()
            except ProcessLookupError:
                pass

    async def encode(self, request: UtteranceEncodingRequest) -> EncodedUtterance:
        self._validate(request)
        ready, _code = self._dependency_ready()
        if not ready:
            raise SilkEncoderError("encoding_unavailable")
        async with self._semaphore:
            if self._closed:
                raise SilkEncoderError("encoding_unavailable")
            process = await self._process_factory()
            async with self._lock:
                if self._closed or request.request_id in self._processes:
                    await self._stop_process(process)
                    raise SilkEncoderError("encoding_unavailable")
                self._processes[request.request_id] = process
            try:
                try:
                    stdout, _stderr = await asyncio.wait_for(
                        process.communicate(input=request.pcm_s16le),
                        timeout=request.timeout_seconds,
                    )
                except asyncio.TimeoutError as exc:
                    await self._stop_process(process)
                    raise SilkEncoderError("encoding_timeout") from exc
                if (
                    process.returncode != 0
                    or not stdout
                    or len(stdout) > MAX_SILK_BYTES
                    or not stdout.startswith(SILK_TENCENT_HEADER)
                ):
                    raise SilkEncoderError("encoding_failed")
                return EncodedUtterance(stdout, OUTPUT_MEDIA_TYPE, OUTPUT_PROFILE)
            except asyncio.CancelledError:
                await self._stop_process(process)
                raise
            finally:
                async with self._lock:
                    if self._processes.get(request.request_id) is process:
                        self._processes.pop(request.request_id, None)

    async def cancel(self, request_id: str) -> None:
        async with self._lock:
            process = self._processes.get(request_id)
        if process is not None:
            await self._stop_process(process)

    async def close(self) -> None:
        async with self._lock:
            if self._closed:
                return
            self._closed = True
            processes = tuple(self._processes.values())
            self._processes.clear()
        await asyncio.gather(
            *(self._stop_process(process) for process in processes),
            return_exceptions=True,
        )


__all__ = [
    "DEFAULT_TIMEOUT_SECONDS",
    "MAX_PCM_BYTES",
    "MAX_SILK_BYTES",
    "SILK_DISTRIBUTION",
    "SILK_LICENSE",
    "SILK_SOURCE",
    "SILK_VERSION",
    "SilkEncoderError",
    "SilkPythonUtteranceEncoder",
    "WINDOWS_X64_WHEEL_SHA256",
]
