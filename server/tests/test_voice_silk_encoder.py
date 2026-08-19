"""PK-210 production Silk adapter tests; no real wheel, codec, process, or audio."""
from __future__ import annotations

import asyncio

import _path_setup  # noqa: F401

from features.voice.media import OUTPUT_PROFILE
from features.voice.models import UtteranceEncodingRequest
from features.voice.silk_encoder import (
    MAX_PCM_BYTES,
    SILK_TENCENT_HEADER,
    SILK_VERSION,
    SilkEncoderError,
    SilkPythonUtteranceEncoder,
    WINDOWS_X64_WHEEL_SHA256,
)


class FakeProcess:
    def __init__(self, *, output=SILK_TENCENT_HEADER + b"fake", wait=None, code=0):
        self.output = output
        self.gate = wait
        self.planned_code = code
        self.returncode = None
        self.inputs = []
        self.terminated = 0
        self.killed = 0
        self.started = asyncio.Event()

    async def communicate(self, input=None):
        self.inputs.append(input)
        self.started.set()
        if self.gate is not None:
            await self.gate.wait()
        if self.returncode is None:
            self.returncode = self.planned_code
        return self.output, b"must-not-be-published"

    def terminate(self):
        self.terminated += 1
        self.returncode = -15
        if self.gate is not None:
            self.gate.set()

    def kill(self):
        self.killed += 1
        self.returncode = -9
        if self.gate is not None:
            self.gate.set()

    async def wait(self):
        if self.gate is not None:
            await self.gate.wait()
        if self.returncode is None:
            self.returncode = self.planned_code
        return self.returncode


def request(*, request_id="req-1", pcm=b"\x01\x00" * 240, timeout=1.0):
    return UtteranceEncodingRequest(
        request_id=request_id,
        utterance_id="opaque",
        output_profile=OUTPUT_PROFILE,
        pcm_s16le=pcm,
        sample_rate=24_000,
        channels=1,
        sample_width=2,
        timeout_seconds=timeout,
    )


def encoder(factory, *, version=SILK_VERSION, module=True, runtime=True):
    return SilkPythonUtteranceEncoder(
        process_factory=factory,
        version_provider=lambda _name: version,
        module_probe=lambda _name: module,
        runtime_probe=lambda: runtime,
    )


async def check():
    created = []

    async def success_factory():
        process = FakeProcess()
        created.append(process)
        return process

    service = encoder(success_factory)
    health = await service.health()
    assert health.available and health.error_code is None
    capabilities = service.capabilities().to_dict()
    assert capabilities == {
        "provider": "silk-python/0.2.8",
        "operations": ["encode"],
        "audio_formats": ["qq_c2c_voice_v1"],
        "streaming": False,
        "cancellable": True,
        "default_timeout_seconds": 30.0,
    }
    result = await service.encode(request())
    assert result.audio == SILK_TENCENT_HEADER + b"fake"
    assert result.media_type == "audio/silk" and result.output_profile == OUTPUT_PROFILE
    assert len(created) == 1 and created[0].inputs == [b"\x01\x00" * 240]

    unavailable_created = []

    async def unavailable_factory():
        unavailable_created.append(True)
        return FakeProcess()

    for kwargs, code in (
        ({"module": False}, "dependency_missing"),
        ({"version": "9.9.9"}, "dependency_version_mismatch"),
        ({"runtime": False}, "runtime_unsupported"),
    ):
        missing = encoder(unavailable_factory, **kwargs)
        missing_health = await missing.health()
        assert not missing_health.available and missing_health.error_code == code
        try:
            await missing.encode(request())
            raise AssertionError("unavailable dependency must not encode")
        except SilkEncoderError as exc:
            assert exc.code == "encoding_unavailable"
    assert unavailable_created == []

    invalid = encoder(success_factory)
    bad_requests = (
        request(pcm=b""),
        request(pcm=b"x"),
        request(pcm=b"\x00\x00" * (MAX_PCM_BYTES // 2 + 1)),
        UtteranceEncodingRequest("x", "u", "arbitrary", b"\x00\x00"),
        UtteranceEncodingRequest("x", "u", OUTPUT_PROFILE, b"\x00\x00", sample_rate=48_000),
        request(timeout=31.0),
    )
    before = len(created)
    for bad in bad_requests:
        try:
            await invalid.encode(bad)
            raise AssertionError("invalid request must fail before process creation")
        except SilkEncoderError as exc:
            assert exc.code == "encoding_request_invalid"
    assert len(created) == before

    async def malformed_factory():
        return FakeProcess(output=b"C:/private/not-silk")

    try:
        await encoder(malformed_factory).encode(request())
        raise AssertionError("malformed output must fail")
    except SilkEncoderError as exc:
        assert exc.code == "encoding_failed" and "private" not in str(exc)

    timeout_process = FakeProcess(wait=asyncio.Event())

    async def timeout_factory():
        return timeout_process

    try:
        await encoder(timeout_factory).encode(request(timeout=0.01))
        raise AssertionError("timeout must fail")
    except SilkEncoderError as exc:
        assert exc.code == "encoding_timeout"
    assert timeout_process.terminated == 1

    cancel_process = FakeProcess(wait=asyncio.Event())

    async def cancel_factory():
        return cancel_process

    cancellable = encoder(cancel_factory)
    pending = asyncio.create_task(cancellable.encode(request(request_id="cancel-me")))
    await cancel_process.started.wait()
    pending.cancel()
    try:
        await pending
        raise AssertionError("cancelled task must remain cancelled")
    except asyncio.CancelledError:
        pass
    assert cancel_process.terminated == 1

    close_process = FakeProcess(wait=asyncio.Event())

    async def close_factory():
        return close_process

    closing = encoder(close_factory)
    active = asyncio.create_task(closing.encode(request(request_id="close-me")))
    await close_process.started.wait()
    await closing.close()
    await closing.close()
    try:
        await active
        raise AssertionError("closed process must not produce audio")
    except SilkEncoderError as exc:
        assert exc.code == "encoding_failed"
    assert close_process.terminated == 1
    closed_health = await closing.health()
    assert not closed_health.available and closed_health.error_code == "encoder_closed"

    assert set(WINDOWS_X64_WHEEL_SHA256) == {"cp310", "cp311", "cp312", "cp313"}
    assert all(len(value) == 64 for value in WINDOWS_X64_WHEEL_SHA256.values())


def main():
    asyncio.run(check())
    print("voice silk encoder tests passed")


if __name__ == "__main__":
    main()
