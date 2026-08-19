"""Root voice-pack-build.bat command implementation."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from ..errors import VoicePackError
from .builder import build_release
from .errors import DistributionError


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build a deterministic Voice Pack release from an explicitly authorized source"
    )
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--version", required=True)
    parser.add_argument("--confirm", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        result = build_release(
            args.source,
            args.output,
            version=args.version,
            confirmation=args.confirm,
        )
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
        return 0
    except (DistributionError, VoicePackError) as exc:
        print(
            json.dumps(
                {
                    "status": "failed",
                    "code": getattr(exc, "code", "voice_pack_build_failed"),
                    "message": str(exc),
                },
                ensure_ascii=False,
            )
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
