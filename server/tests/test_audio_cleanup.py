"""Inspect or run generated-audio cleanup."""
from __future__ import annotations

import _path_setup  # noqa: F401
import argparse

from services.audio_cleanup import cleanup_audio_outputs
from tests._path_setup import SERVER_ROOT


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="Actually delete files. Default is dry-run.")
    args = parser.parse_args()

    stats = cleanup_audio_outputs(SERVER_ROOT, dry_run=not args.apply)
    print(stats.to_dict())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
