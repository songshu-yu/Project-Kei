"""Explicit local administration for existing Voice Pack assets."""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

from .registry import VoicePackRegistry
from .service import VoicePackRegistryService


SERVER_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_REGISTRY = SERVER_ROOT / "data" / "voice_pack_registry.local.json"
DEFAULT_RUNTIME_ROOT = SERVER_ROOT / "runtime" / "voice_packs"


def _service(registry_path: Path) -> VoicePackRegistryService:
    return VoicePackRegistryService(VoicePackRegistry(registry_path), runtime_root=DEFAULT_RUNTIME_ROOT)


def _local_manifest(args: argparse.Namespace) -> tuple[dict, dict[str, Path]]:
    logical_gpt = f"assets/{args.id}-gpt.ckpt"
    logical_sovits = f"assets/{args.id}-sovits.pth"
    logical_audio = f"assets/{args.id}-reference.wav"
    integrity = {"mode": "existence_only"}
    manifest = {
        "schema_version": 1,
        "id": args.id,
        "name": args.name,
        "version": args.version,
        "engine": {"provider": "gpt-sovits", "protocol_version": "pk210-tts-v1"},
        "supported_languages": sorted(set(args.languages + [args.reference_language, args.default_text_language])),
        "gpt_checkpoint": {"path": logical_gpt, "integrity": integrity},
        "sovits_checkpoint": {"path": logical_sovits, "integrity": integrity},
        "reference_audio": {"path": logical_audio, "integrity": integrity},
        "reference_text": args.reference_text,
        "reference_language": args.reference_language,
        "default_text_language": args.default_text_language,
        "generation_parameters": {
            "top_k": 15,
            "top_p": 1.0,
            "temperature": 1.0,
            "speed_factor": 1.0,
            "text_split_method": "cut5"
        },
        "metadata": {
            "source": "existing local assets",
            "author": "local-only",
            "license": "not audited",
            "redistribution": "restricted"
        }
    }
    bindings = {
        logical_gpt: Path(args.gpt_checkpoint),
        logical_sovits: Path(args.sovits_checkpoint),
        logical_audio: Path(args.reference_audio),
    }
    return manifest, bindings


async def _run(args: argparse.Namespace) -> dict:
    service = _service(Path(args.registry))
    if args.command == "list":
        return await service.list_packs()
    if args.command == "register-existing":
        manifest, bindings = _local_manifest(args)
        return await service.register_local(manifest, bindings, enabled=True, make_active=not args.no_select)
    raise ValueError("unsupported command")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Project Kei local Voice Pack registry")
    parser.add_argument("--registry", default=str(DEFAULT_REGISTRY), help=argparse.SUPPRESS)
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("list", help="List path-redacted local Voice Packs")
    register = subparsers.add_parser("register-existing", help="Register existing files without copying or hashing")
    register.add_argument("--id", required=True)
    register.add_argument("--name", required=True)
    register.add_argument("--version", required=True)
    register.add_argument("--gpt-checkpoint", required=True)
    register.add_argument("--sovits-checkpoint", required=True)
    register.add_argument("--reference-audio", required=True)
    register.add_argument("--reference-text", required=True)
    register.add_argument("--reference-language", default="ja")
    register.add_argument("--default-text-language", default="zh")
    register.add_argument("--languages", nargs="+", default=["zh", "ja"])
    register.add_argument("--no-select", action="store_true")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    result = asyncio.run(_run(args))
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
