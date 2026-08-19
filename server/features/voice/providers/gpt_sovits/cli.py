"""User-invoked CLI. It accepts no URL, command, BAT, or PowerShell input."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from .acquisition import (
    AcquisitionError,
    LocalEngineRegistry,
    acquire_builtin_engine,
    register_existing_install,
)
from .descriptor import DEFAULT_LOCAL_CONFIG_PATH, DescriptorError, load_descriptor


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Project Kei GPT-SoVITS 受控获取与本机登记")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("status", help="只读取项目描述与本机登记状态")

    register = subparsers.add_parser("register", help="登记已有本机安装；不下载、不扫描")
    register.add_argument("--install-root", required=True, type=Path)
    register.add_argument("--api-style", choices=("auto", "api_py", "legacy_v2"), default="auto")

    acquire = subparsers.add_parser("acquire", help="从项目固定来源显式获取")
    acquire.add_argument("--install-root", required=True, type=Path)
    acquire.add_argument("--confirm-engine-id", required=True)
    acquire.add_argument("--api-style", choices=("auto", "api_py", "legacy_v2"), default="auto")
    acquire.add_argument("--offline", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        descriptor = load_descriptor()
        if args.command == "status":
            result = LocalEngineRegistry(DEFAULT_LOCAL_CONFIG_PATH).status(descriptor)
        elif args.command == "register":
            result = register_existing_install(
                args.install_root,
                api_style=args.api_style,
                descriptor=descriptor,
            ).to_public_dict()
        else:
            result = acquire_builtin_engine(
                args.install_root,
                confirmation=args.confirm_engine_id,
                api_style=args.api_style,
                offline=args.offline,
            ).to_public_dict()
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
        return 0
    except (AcquisitionError, DescriptorError) as exc:
        print(json.dumps({"status": "failed", "code": exc.code, "message": str(exc)}, ensure_ascii=False))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
