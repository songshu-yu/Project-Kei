"""Test Project Kei TTS against GPT-SoVITS api.py.

Start GPT-SoVITS first, then run:
    python test_tts_gptsovits.py
    python test_tts_gptsovits.py --text "测试一下 Kei 的声音。" --out output/kei_test.wav
"""
from __future__ import annotations

import _path_setup  # noqa: F401
import argparse
import asyncio
import os
from pathlib import Path

from features.voice.voice_packs import VoicePackRegistry, VoicePackRegistryService
from services.tts_client import TTSClient, TTSConfig


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--text", default="哼，终于知道让我开口了。只是测试语音而已，不要露出那种表情。")
    parser.add_argument("--out", default="output/kei_tts_test.wav")
    parser.add_argument("--emotion", default="calm")
    args = parser.parse_args()

    config = TTSConfig(
        host=os.getenv("TTS_HOST", "127.0.0.1"),
        port=int(os.getenv("TTS_PORT", "9880")),
        api_style=os.getenv("TTS_API_STYLE", "gptsovits"),
    )
    client = TTSClient(config)
    server_root = Path(__file__).resolve().parents[1]
    voice_packs = VoicePackRegistryService(
        VoicePackRegistry(server_root / "data" / "voice_pack_registry.local.json"),
        runtime_root=server_root / "runtime" / "voice_packs",
        activator=client,
    )
    client.set_voice_pack_resolver(voice_packs)
    try:
        ok = await client.check_available()
        if not ok:
            print("GPT-SoVITS service is not available.")
            return 1

        out_path = Path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        saved = await client.synthesize_to_file(args.text, out_path, args.emotion)
        if not saved:
            print("TTS synthesis failed.")
            return 2
        print(f"Saved audio: {out_path.resolve()}")
        return 0
    finally:
        await client.close()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
