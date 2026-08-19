"""Record from the PC microphone and send it to /voice/chat.

Example:
    python tests/test_mic_voice_chat.py
    python tests/test_mic_voice_chat.py --seconds 5 --play
    python tests/test_mic_voice_chat.py --list-devices
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import wave
from pathlib import Path

import _path_setup  # noqa: F401
import httpx


SERVER_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_DIR = SERVER_ROOT / "output" / "mic_tests"


def _load_audio_deps():
    try:
        import numpy as np  # type: ignore
        import sounddevice as sd  # type: ignore

        return np, sd
    except ImportError as exc:
        missing = exc.name or "sounddevice/numpy"
        print(f"Missing optional audio dependency: {missing}")
        print("Install in the current environment:")
        print(r"  .\.venv-asr\Scripts\python.exe -m pip install sounddevice numpy")
        return None, None


def list_devices() -> int:
    _, sd = _load_audio_deps()
    if sd is None:
        return 2
    print(sd.query_devices())
    return 0


def write_wav(path: Path, audio, sample_rate: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(audio.tobytes())


def record_fixed_seconds(path: Path, seconds: float, sample_rate: int, device=None) -> Path:
    np, sd = _load_audio_deps()
    if sd is None:
        raise RuntimeError("audio dependencies are not installed")

    frames = int(seconds * sample_rate)
    print(f"Recording {seconds:.1f}s... speak now.")
    audio = sd.rec(frames, samplerate=sample_rate, channels=1, dtype="int16", device=device)
    sd.wait()
    write_wav(path, audio, sample_rate)
    print(f"Saved recording: {path}")
    return path


def record_press_enter(path: Path, sample_rate: int, device=None) -> Path:
    np, sd = _load_audio_deps()
    if sd is None:
        raise RuntimeError("audio dependencies are not installed")

    chunks = []

    def callback(indata, frames, time_info, status):  # noqa: ANN001
        if status:
            print(f"record status: {status}", file=sys.stderr)
        chunks.append(indata.copy())

    input("Press Enter to start recording...")
    print("Recording. Press Enter again to stop.")
    with sd.InputStream(samplerate=sample_rate, channels=1, dtype="int16", callback=callback, device=device):
        input()

    if not chunks:
        raise RuntimeError("no audio captured")
    audio = np.concatenate(chunks, axis=0)
    write_wav(path, audio, sample_rate)
    print(f"Saved recording: {path}")
    return path


def send_voice_chat(
    audio_path: Path,
    url: str,
    language: str,
    vad_filter: bool,
    include_audio_base64: bool,
    split_tts: bool,
) -> dict:
    with audio_path.open("rb") as f:
        files = {"file": (audio_path.name, f, "audio/wav")}
        data = {
            "language": language,
            "vad_filter": "true" if vad_filter else "false",
            "include_audio_base64": "true" if include_audio_base64 else "false",
            "split_tts": "true" if split_tts else "false",
        }
        resp = httpx.post(url, files=files, data=data, timeout=300.0, trust_env=False)

    print(f"status: {resp.status_code}")
    if resp.status_code != 200:
        print(resp.text)
        raise RuntimeError("voice chat request failed")
    return resp.json()


def stream_voice_chat(
    audio_path: Path,
    url: str,
    language: str,
    vad_filter: bool,
    split_tts: bool,
    play: bool,
) -> dict:
    stream_url = url.rstrip("/")
    if stream_url.endswith("/voice/chat"):
        stream_url = f"{stream_url}/stream"

    final_result: dict = {}
    with audio_path.open("rb") as f:
        files = {"file": (audio_path.name, f, "audio/wav")}
        data = {
            "language": language,
            "vad_filter": "true" if vad_filter else "false",
            "split_tts": "true" if split_tts else "false",
        }
        with httpx.Client(timeout=300.0, trust_env=False) as client:
            with client.stream("POST", stream_url, files=files, data=data) as resp:
                print(f"status: {resp.status_code}")
                if resp.status_code != 200:
                    print(resp.read().decode("utf-8", errors="replace"))
                    raise RuntimeError("voice chat stream request failed")

                for line in resp.iter_lines():
                    if not line:
                        continue
                    event = json.loads(line)
                    event_type = event.get("event")
                    if event_type == "reply":
                        final_result.update(event)
                        print(f"user_text: {event.get('user_text')}")
                        print(f"assistant_text: {event.get('assistant_text')}")
                        print(f"emotion: {event.get('emotion')}")
                        print(f"timings_ms_so_far: {event.get('timings_ms')}")
                    elif event_type == "audio_part":
                        index = event.get("index")
                        total = event.get("total")
                        path = event.get("audio_path", "")
                        print(f"audio_part: {index}/{total} {event.get('elapsed_ms')}ms {path}")
                        if play and path:
                            play_wav(path)
                    elif event_type == "done":
                        final_result.update(event)
                        print(f"audio_path: {event.get('audio_path')}")
                        print(f"audio_paths: {event.get('audio_paths')}")
                        print(f"timings_ms: {event.get('timings_ms')}")
                    elif event_type == "error":
                        raise RuntimeError(event.get("error", "stream error"))
                    else:
                        print(event)

    return final_result


def play_wav(path: str) -> None:
    if not path:
        print("No reply audio_path returned.")
        return
    wav_path = Path(path)
    if not wav_path.is_absolute():
        wav_path = SERVER_ROOT / wav_path
    if not wav_path.exists():
        print(f"Reply audio file not found: {wav_path}")
        return

    try:
        import winsound

        print(f"Playing: {wav_path}")
        winsound.PlaySound(str(wav_path), winsound.SND_FILENAME)
    except Exception as exc:
        print(f"Playback failed: {type(exc).__name__}: {exc}")


def play_reply_paths(result: dict) -> None:
    paths = result.get("audio_paths") or []
    if paths:
        for path in paths:
            play_wav(path)
        return
    play_wav(result.get("audio_path", ""))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://127.0.0.1:8000/voice/chat")
    parser.add_argument("--language", default="zh")
    parser.add_argument("--seconds", type=float, default=0.0, help="Fixed recording length. Default: press Enter to stop.")
    parser.add_argument("--sample-rate", type=int, default=16000)
    parser.add_argument("--device", default=None, help="Optional sounddevice input device id/name")
    parser.add_argument("--vad", action="store_true", help="Enable ASR VAD")
    parser.add_argument("--audio-base64", action="store_true", help="Return audio_base64 in JSON")
    parser.add_argument("--play", action="store_true", help="Play the returned reply wav on Windows")
    parser.add_argument("--split-tts", action="store_true", help="Split the assistant reply into multiple TTS wav files")
    parser.add_argument("--stream", action="store_true", help="Use /voice/chat/stream and play parts as they are produced")
    parser.add_argument("--list-devices", action="store_true")
    args = parser.parse_args()

    if args.list_devices:
        return list_devices()

    timestamp = time.strftime("%Y%m%d_%H%M%S")
    audio_path = DEFAULT_OUTPUT_DIR / f"mic_{timestamp}.wav"

    try:
        if args.seconds and args.seconds > 0:
            record_fixed_seconds(audio_path, args.seconds, args.sample_rate, args.device)
        else:
            record_press_enter(audio_path, args.sample_rate, args.device)

        if args.stream:
            result = stream_voice_chat(
                audio_path=audio_path,
                url=args.url,
                language=args.language,
                vad_filter=args.vad,
                split_tts=args.split_tts,
                play=args.play,
            )
        else:
            result = send_voice_chat(
                audio_path=audio_path,
                url=args.url,
                language=args.language,
                vad_filter=args.vad,
                include_audio_base64=args.audio_base64,
                split_tts=args.split_tts,
            )

            print(f"user_text: {result.get('user_text')}")
            print(f"assistant_text: {result.get('assistant_text')}")
            print(f"emotion: {result.get('emotion')}")
            print(f"audio_path: {result.get('audio_path')}")
            print(f"audio_paths: {result.get('audio_paths')}")
            print(f"timings_ms: {result.get('timings_ms')}")
            if result.get("audio_base64"):
                print(f"audio_base64: {len(result['audio_base64'])} chars")
            if args.play:
                play_reply_paths(result)
        return 0
    except KeyboardInterrupt:
        print("\nCanceled.")
        return 130
    except Exception as exc:
        print(f"Error: {type(exc).__name__}: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
