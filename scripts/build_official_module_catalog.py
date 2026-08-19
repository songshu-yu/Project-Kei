"""Build or verify the official module catalog from explicit release fragments/assets."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SERVER_ROOT = PROJECT_ROOT / "server"
if str(SERVER_ROOT) not in sys.path:
    sys.path.insert(0, str(SERVER_ROOT))

from core.modules.manifest import validate_manifest  # noqa: E402
from core.modules.official_catalog import (  # noqa: E402
    OFFICIAL_OWNER,
    OFFICIAL_PUBLISHER,
    OFFICIAL_REPOSITORY,
    validate_official_catalog,
)


FRAGMENT_FIELDS = {
    "schema_version", "module_id", "name", "version", "core_compatibility",
    "release_tag", "asset_name", "dependencies", "optional_dependencies",
    "conflicts", "permissions", "data_policy", "requires_restart",
}
OPTIONAL_FRAGMENT_FIELDS = {"runtime_requirements"}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(1024 * 1024)
            if not chunk:
                return digest.hexdigest()
            digest.update(chunk)


def _read_manifest(asset: Path) -> tuple[dict, str]:
    with zipfile.ZipFile(str(asset), "r") as source:
        matches = [
            info for info in source.infolist()
            if info.filename.lower().rstrip("/") == "manifest.json"
        ]
        if len(matches) != 1 or matches[0].filename != "manifest.json" or matches[0].is_dir():
            raise ValueError(f"{asset}: expected one root manifest.json")
        raw = source.read(matches[0])
    payload = json.loads(raw.decode("utf-8"))
    validate_manifest(payload)
    return payload, hashlib.sha256(raw).hexdigest()


def _load_fragment(path: Path) -> dict:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if (
        not isinstance(payload, dict)
        or not FRAGMENT_FIELDS.issubset(payload)
        or not set(payload).issubset(FRAGMENT_FIELDS | OPTIONAL_FRAGMENT_FIELDS)
    ):
        raise ValueError(f"{path}: release fragment fields are invalid")
    if payload.get("schema_version") != 1:
        raise ValueError(f"{path}: unsupported release fragment schema")
    return payload


def build_catalog(fragment_paths: list[Path], asset_root: Path, generated_at: str) -> dict:
    releases = []
    seen = set()
    for fragment_path in sorted(fragment_paths, key=lambda item: item.as_posix().casefold()):
        fragment = _load_fragment(fragment_path)
        asset = asset_root / fragment["asset_name"]
        if not asset.is_file() or asset.parent.resolve() != asset_root.resolve():
            raise ValueError(f"{fragment_path}: release asset is missing from the explicit asset root")
        manifest, manifest_sha256 = _read_manifest(asset)
        comparisons = {
            "module_id": manifest["id"],
            "name": manifest["name"],
            "version": manifest["version"],
            "core_compatibility": manifest["core_compatibility"],
            "dependencies": manifest["dependencies"],
            "optional_dependencies": manifest["optional_dependencies"],
            "runtime_requirements": manifest.get("runtime_requirements", []),
            "conflicts": manifest["conflicts"],
            "permissions": manifest["permissions"],
            "requires_restart": manifest["requires_restart"],
        }
        for field, actual in comparisons.items():
            if fragment.get(field, [] if field == "runtime_requirements" else None) != actual:
                raise ValueError(f"{fragment_path}: {field} does not match the ZIP manifest")
        key = (fragment["module_id"], fragment["version"])
        if key in seen:
            raise ValueError(f"duplicate release fragment: {key[0]}@{key[1]}")
        seen.add(key)
        release = {key: value for key, value in fragment.items() if key != "schema_version"}
        runtime_requirements = manifest.get("runtime_requirements", [])
        if runtime_requirements:
            release["runtime_requirements"] = runtime_requirements
        else:
            release.pop("runtime_requirements", None)
        release.update({
            "manifest_sha256": manifest_sha256,
            "package_url": (
                f"https://github.com/{OFFICIAL_OWNER}/{OFFICIAL_REPOSITORY}/"
                f"releases/download/{fragment['release_tag']}/{fragment['asset_name']}"
            ),
            "package_size": asset.stat().st_size,
            "package_sha256": _sha256(asset),
        })
        releases.append(release)
    payload = {
        "schema_version": 1,
        "publisher": OFFICIAL_PUBLISHER,
        "owner": OFFICIAL_OWNER,
        "repository": OFFICIAL_REPOSITORY,
        "generated_at": generated_at,
        "modules": sorted(releases, key=lambda item: (item["module_id"], item["version"])),
    }
    validate_official_catalog(payload)
    return payload


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fragment", action="append", default=[])
    parser.add_argument("--asset-root")
    parser.add_argument(
        "--output",
        default=str(SERVER_ROOT / "core" / "modules" / "official-catalog.json"),
    )
    parser.add_argument("--generated-at")
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--validate-catalog", action="store_true")
    args = parser.parse_args()
    output = Path(args.output).resolve()
    if args.validate_catalog:
        validate_official_catalog(json.loads(output.read_text(encoding="utf-8")))
        print(f"official module catalog valid: {output}")
        return 0
    if not args.fragment or not args.asset_root:
        parser.error("--fragment and --asset-root are required unless --validate-catalog is used")
    generated_at = args.generated_at or datetime.now(timezone.utc).isoformat()
    payload = build_catalog(
        [Path(value).resolve() for value in args.fragment],
        Path(args.asset_root).resolve(),
        generated_at,
    )
    rendered = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if args.check:
        if not output.is_file() or output.read_text(encoding="utf-8") != rendered:
            raise SystemExit("official module catalog is not reproducible from the supplied fragments/assets")
        print(f"official module catalog reproducible: {output}")
        return 0
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(rendered, encoding="utf-8")
    print(f"official module catalog written: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
