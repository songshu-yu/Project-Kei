"""Test the end-to-end /voice/chat endpoint.

Services required:
    start_all_services.bat
    python -m uvicorn api:app --host 0.0.0.0 --port 8000

Example:
    python tests/test_voice_chat.py --file output/kei_tts_file_test.wav
"""
from __future__ import annotations

import _path_setup  # noqa: F401
import argparse
from pathlib import Path

import httpx


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://127.0.0.1:8000/voice/chat")
    parser.add_argument("--file", required=True, help="Path to wav/mp3/m4a/flac audio")
    parser.add_argument("--language", default="zh")
    parser.add_argument("--vad", action="store_true", help="Enable ASR VAD")
    parser.add_argument("--audio-base64", action="store_true", help="Return audio_base64 in JSON")
    parser.add_argument("--split-tts", action="store_true", help="Split the assistant reply into multiple TTS wav files")
    args = parser.parse_args()

    audio_path = Path(args.file)
    if not audio_path.exists():
        print(f"Audio file not found: {audio_path}")
        return 1

    with audio_path.open("rb") as f:
        files = {"file": (audio_path.name, f, "application/octet-stream")}
        data = {
            "language": args.language,
            "vad_filter": "true" if args.vad else "false",
            "include_audio_base64": "true" if args.audio_base64 else "false",
            "split_tts": "true" if args.split_tts else "false",
        }
        resp = httpx.post(args.url, files=files, data=data, timeout=300.0, trust_env=False)

    print(f"status: {resp.status_code}")
    if resp.status_code != 200:
        print(resp.text)
        return 2

    result = resp.json()
    print(f"user_text: {result.get('user_text')}")
    print(f"assistant_text: {result.get('assistant_text')}")
    print(f"emotion: {result.get('emotion')}")
    print(f"audio_path: {result.get('audio_path')}")
    print(f"audio_paths: {result.get('audio_paths')}")
    print(f"timings_ms: {result.get('timings_ms')}")
    if result.get("audio_base64"):
        print(f"audio_base64: {len(result['audio_base64'])} chars")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
