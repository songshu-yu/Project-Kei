"""Root voice-pack.bat command implementation."""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

from ...providers.gpt_sovits import GPTSoVITSProvider, LocalEngineRegistry, TTSConfig, load_descriptor
from ..catalog import CatalogError, VoicePackCatalog
from ..errors import VoicePackError
from ..registry import VoicePackRegistry
from ..service import VoicePackRegistryService
from .downloader import HTTPSDownloader
from .errors import DistributionError
from .service import VoicePackDistributionService


SERVER_ROOT = Path(__file__).resolve().parents[4]
CATALOG_ROOT = Path(__file__).resolve().parents[1] / "catalog"
REGISTRY_PATH = SERVER_ROOT / "data" / "voice_pack_registry.local.json"
RUNTIME_ROOT = SERVER_ROOT / "runtime" / "voice_packs"
CACHE_ROOT = SERVER_ROOT / "data" / "voice_packs" / "downloads"


def _build_service() -> VoicePackDistributionService:
    descriptor = load_descriptor()
    engine_registry = LocalEngineRegistry(
        SERVER_ROOT / "data" / "gpt_sovits_engine.local.json"
    )
    provider = GPTSoVITSProvider(TTSConfig())
    registry_service = VoicePackRegistryService(
        VoicePackRegistry(REGISTRY_PATH),
        runtime_root=RUNTIME_ROOT,
        activator=provider,
    )
    provider.set_voice_pack_resolver(registry_service)
    return VoicePackDistributionService(
        catalog=VoicePackCatalog.load(CATALOG_ROOT),
        registry_service=registry_service,
        cache_root=CACHE_ROOT,
        downloader=HTTPSDownloader(),
        engine_status=lambda: engine_registry.status(descriptor),
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Project Kei trusted Voice Pack installer (PK-213)"
    )
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("list", help="List trusted releases and local status; never downloads")
    status = sub.add_parser("status", help="Show one trusted release and Engine status")
    status.add_argument("pack")

    install = sub.add_parser("install", help="Install only from the built-in trusted catalog")
    install.add_argument("pack")
    install.add_argument("--confirm")
    install.add_argument("--download-only", action="store_true")
    install.add_argument("--no-select", action="store_true")

    local = sub.add_parser("import", help="Import an explicit local ZIP or directory")
    local.add_argument("source", type=Path)
    local.add_argument("--confirm", dest="expected_key")
    local.add_argument("--sha256", dest="expected_sha256")

    select = sub.add_parser("select", help="Select an installed and enabled Voice Pack")
    select.add_argument("pack")
    verify = sub.add_parser("verify", help="Revalidate an installed Voice Pack")
    verify.add_argument("pack")
    return parser


def _confirmation(args: argparse.Namespace) -> str:
    if args.confirm:
        return args.confirm
    print(
        json.dumps(
            {
                "status": "confirmation_required",
                "pack": args.pack,
                "instruction": f"type {args.pack} to continue",
            },
            ensure_ascii=False,
        )
    )
    try:
        return input("> ").strip()
    except EOFError:
        return ""


async def _run(args: argparse.Namespace) -> dict:
    service = _build_service()
    if args.command == "list":
        return await service.list()
    if args.command == "status":
        return await service.status(args.pack)
    if args.command == "install":
        confirmation = _confirmation(args)
        if args.download_only:
            return await service.download_only(args.pack, confirmation=confirmation)
        return await service.install(
            args.pack, confirmation=confirmation, select=not args.no_select
        )
    if args.command == "import":
        return await service.import_local(
            args.source,
            expected_key=args.expected_key,
            expected_sha256=args.expected_sha256,
        )
    if args.command == "select":
        return await service.select(args.pack)
    if args.command == "verify":
        return await service.verify(args.pack)
    raise DistributionError("unsupported command", code="voice_pack_arguments_invalid")


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        result = asyncio.run(_run(args))
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
        return 0
    except (CatalogError, DistributionError, VoicePackError) as exc:
        print(
            json.dumps(
                {
                    "status": "failed",
                    "code": getattr(exc, "code", "voice_pack_distribution_failed"),
                    "message": str(exc),
                },
                ensure_ascii=False,
            )
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
