"""Upload an audio file to the Project Kei ASR service.

Example:
    python test_asr_upload.py --file sample.wav
    python test_asr_upload.py --url http://192.168.1.10:8010/asr/transcribe --file sample.wav
"""
from __future__ import annotations

import _path_setup  # noqa: F401
import argparse
from pathlib import Path

import httpx


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://127.0.0.1:8010/asr/transcribe")
    parser.add_argument("--file", required=True, help="Path to wav/mp3/m4a/flac audio")
    parser.add_argument("--language", default="zh")
    parser.add_argument("--no-vad", action="store_true")
    parser.add_argument("--initial-prompt", default="")
    parser.add_argument("--no-postprocess", action="store_true")
    args = parser.parse_args()

    audio_path = Path(args.file)
    if not audio_path.exists():
        print(f"Audio file not found: {audio_path}")
        return 1

    with audio_path.open("rb") as f:
        files = {"file": (audio_path.name, f, "application/octet-stream")}
        data = {
            "language": args.language,
            "vad_filter": "false" if args.no_vad else "true",
            "postprocess": "false" if args.no_postprocess else "true",
        }
        if args.initial_prompt:
            data["initial_prompt"] = args.initial_prompt
        resp = httpx.post(args.url, files=files, data=data, timeout=180.0, trust_env=False)

    print(f"status: {resp.status_code}")
    if resp.status_code != 200:
        print(resp.text)
        return 2

    result = resp.json()
    print(f"language: {result.get('language')} p={result.get('language_probability')}")
    print(f"duration: {result.get('duration')}s")
    print("\ntext:")
    print(result.get("text", ""))
    if result.get("original_text") and result.get("original_text") != result.get("text"):
        print("\noriginal_text:")
        print(result.get("original_text", ""))
    print("\nsegments:")
    for seg in result.get("segments", []):
        print(f"  {seg['start']:.2f}-{seg['end']:.2f}: {seg['text']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
