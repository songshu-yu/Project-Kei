"""Download/cache the faster-whisper model used by asr_server.py.

Examples:
    python download_asr_model.py --model small
    python download_asr_model.py --model small --cache-dir models/asr
"""
from __future__ import annotations

import argparse
import os

from faster_whisper.utils import download_model


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default=os.getenv("ASR_MODEL_SIZE", "small"))
    parser.add_argument("--cache-dir", default=os.getenv("ASR_MODEL_CACHE", "models/asr"))
    parser.add_argument("--local-files-only", action="store_true")
    args = parser.parse_args()

    print(f"HF_ENDPOINT={os.getenv('HF_ENDPOINT', '<default huggingface.co>')}")
    print(f"HTTP_PROXY={os.getenv('HTTP_PROXY', '<unset>')}")
    print(f"HTTPS_PROXY={os.getenv('HTTPS_PROXY', '<unset>')}")
    print(f"model={args.model}")
    print(f"cache_dir={args.cache_dir}")

    model_path = download_model(
        args.model,
        output_dir=args.cache_dir,
        local_files_only=args.local_files_only,
    )
    print(f"Downloaded model path: {model_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
