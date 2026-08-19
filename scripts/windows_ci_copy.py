"""Build the Windows CI checkout from a reviewed, tracked-file surface.

The Git tree is classified using relative path strings before any working-tree
Path is constructed. Protected and malformed candidates therefore cannot reach
lstat, mkdir, open, or copy operations.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys
from typing import Callable, Iterable, Sequence


class CopyPolicyError(RuntimeError):
    """The requested copy would cross the reviewed CI installation surface."""


@dataclass(frozen=True)
class GitTreeEntry:
    mode: str
    object_type: str
    object_id: str
    relative_path: str


@dataclass(frozen=True)
class CopyPlan:
    allowed: tuple[GitTreeEntry, ...]
    protected_rejected: int
    ignored: int


@dataclass(frozen=True)
class CopySummary:
    allowed: int
    protected_rejected: int
    ignored: int
    copied: int


ALLOWED_ROOT_FILES = frozenset(
    {
        ".gitattributes",
        "agents.md",
        "doctor.bat",
        "project_migration_guide.md",
        "pyproject.toml",
        "readme.md",
        "setup.bat",
        "start.bat",
        "tasks.md",
        "voice-pack-build.bat",
        "voice-pack.bat",
    }
)

ALLOWED_PREFIXES = (
    "docs/",
    "requirements/",
    "scripts/",
    "server/core/",
    "server/features/",
    "server/intel/",
    "server/prompts/",
    "server/qq_bridge/",
    "server/scripts/",
    "server/services/",
    "server/static/",
    "server/systems/",
    "server/tests/",
    "server/tools/",
    "tasks/",
)

EXACT_ALLOWED_FILES = frozenset(
    {
        ".github/workflows/windows-install.yml",
    }
)

PROTECTED_PREFIXES = (
    ".git/",
    ".github/",
    ".venv/",
    ".venv-asr/",
    "cyber_girlfriend/",
    "external/",
    "gpt-sovits/",
    "gpt_sovits/",
    "vendor/",
    "server/.venv/",
    "server/.venv-asr/",
    "server/cache/",
    "server/data/",
    "server/gpt-sovits/",
    "server/gpt_sovits/",
    "server/intel_history/",
    "server/models/",
    "server/node_modules/",
    "server/output/",
    "server/profiles/",
    "server/audio/",
    "server/reference_audio/",
    "server/runtime/",
    "server/voice_packs/",
    "server/systems/data/",
    "server/qq_bridge/cache/",
    "server/qq_bridge/data/",
    "server/qq_bridge/audio/",
    "server/qq_bridge/models/",
    "server/qq_bridge/node_modules/",
    "server/qq_bridge/profiles/",
    "server/qq_bridge/runtime/",
)

PROTECTED_DIRECTORY_NAMES = frozenset(
    {
        ".git",
        ".pytest_cache",
        ".venv",
        ".venv-asr",
        "__pycache__",
        "cache",
        "models",
        "node_modules",
        "profile",
        "profiles",
        "reference_audio",
        "runtime",
        "vendor",
        "voice-pack",
        "voice_pack",
        "voice_packs",
    }
)

PROTECTED_BASENAMES = frozenset(
    {
        ".env",
        "readme.local.md",
        "affection_state.json",
        "calendar_memo.json",
        "demon_slayer.json",
        "fitness_checkins.json",
        "focus_timer.json",
        "gpt_sovits_engine.local.json",
        "intel_sources.json",
        "llm_profile.json",
        "memories.json",
        "source_list.json",
        "sources.json",
        "sources.local.json",
        "voice_pack_registry.local.json",
    }
)

PROTECTED_SUFFIXES = (
    ".bin",
    ".ckpt",
    ".flac",
    ".mp3",
    ".onnx",
    ".pth",
    ".pt",
    ".safetensors",
    ".wav",
)

REVIEWED_PRODUCTION_CODE_PREFIXES = (
    "server/features/voice/voice_packs/",
)

REQUIRED_COPY_FILES = frozenset(
    {
        "doctor.bat",
        "setup.bat",
        "start.bat",
        "voice-pack-build.bat",
        "voice-pack.bat",
        "requirements/core-win.lock.txt",
        "requirements/dev-win.lock.txt",
        "requirements/voice-media.in",
        "requirements/voice-media-win.lock.txt",
        "requirements/lock-manifest.json",
        ".github/workflows/windows-install.yml",
        "pyproject.toml",
        "scripts/check_python_test_inventory.py",
        "scripts/doctor.ps1",
        "scripts/project-kei.common.ps1",
        "scripts/python.ps1",
        "scripts/setup.ps1",
        "scripts/start.ps1",
        "server/api.py",
        "server/features/voice/voice_packs/service.py",
        "server/qq_bridge/package-lock.json",
        "server/qq_bridge/package.json",
        "server/tests/_parameter_contract.py",
        "server/tests/conftest.py",
        "server/tests/python-test-inventory.json",
        "server/tests/test_dashboard_shell.py",
        "server/tests/test_gpt_sovits_provider.py",
        "server/tests/test_installable_modules.py",
        "server/tests/test_qq_control.py",
        "server/tests/test_voice_module.py",
        "server/tests/test_voice_pack_registry.py",
        "server/tests/test_windows_install.py",
    }
)


def normalize_git_relative(value: str) -> tuple[str, str]:
    """Return normalized/original-case and case-folded keys without filesystem I/O."""

    if not isinstance(value, str) or not value:
        raise CopyPolicyError("empty Git relative path rejected before filesystem I/O")
    if "\\" in value or "\x00" in value:
        raise CopyPolicyError("non-portable Git relative path rejected before filesystem I/O")
    if value.startswith("/") or value.startswith("//"):
        raise CopyPolicyError("absolute Git path rejected before filesystem I/O")

    parts = value.split("/")
    if (
        len(parts[0]) >= 2
        and parts[0][1] == ":"
        or any(part in ("", ".", "..") for part in parts)
    ):
        raise CopyPolicyError("drive-qualified or traversal path rejected before filesystem I/O")

    normalized = "/".join(parts)
    return normalized, normalized.casefold()


class CopyPolicy:
    """Pure-string policy used before any source Path or file metadata lookup."""

    def classify(self, relative_path: str) -> str:
        normalized, key = normalize_git_relative(relative_path)
        if normalized in EXACT_ALLOWED_FILES:
            return "allowed"
        parts = key.split("/")
        basename = parts[-1]
        reviewed_production_code = any(
            key.startswith(prefix) for prefix in REVIEWED_PRODUCTION_CODE_PREFIXES
        )

        if (
            key == ".env"
            or key == "readme.local.md"
            or any(key.startswith(prefix) for prefix in PROTECTED_PREFIXES)
            or (
                not reviewed_production_code
                and any(part in PROTECTED_DIRECTORY_NAMES for part in parts[:-1])
            )
            or basename in PROTECTED_BASENAMES
            or basename.endswith(PROTECTED_SUFFIXES)
        ):
            return "protected"

        if (
            key in ALLOWED_ROOT_FILES
            or any(key.startswith(prefix) for prefix in ALLOWED_PREFIXES)
            or key.startswith("server/") and key.count("/") == 1
        ):
            return "allowed"
        return "ignored"

    def require_allowed(self, relative_path: str) -> str:
        normalized, _ = normalize_git_relative(relative_path)
        classification = self.classify(normalized)
        if classification != "allowed":
            raise CopyPolicyError(
                f"{classification} source rejected before working-tree filesystem I/O"
            )
        return normalized


def parse_ls_tree(output: bytes) -> tuple[GitTreeEntry, ...]:
    entries: list[GitTreeEntry] = []
    for record in output.split(b"\x00"):
        if not record:
            continue
        try:
            metadata, raw_path = record.split(b"\t", 1)
            mode, object_type, object_id = metadata.decode("ascii").split(" ", 2)
            relative_path = raw_path.decode("utf-8", "strict")
        except (UnicodeDecodeError, ValueError) as exc:
            raise CopyPolicyError("malformed Git tree metadata") from exc
        entries.append(GitTreeEntry(mode, object_type, object_id, relative_path))
    return tuple(entries)


def list_git_tree(repo_root: Path) -> tuple[GitTreeEntry, ...]:
    completed = subprocess.run(
        ["git", "-C", os.fspath(repo_root), "ls-tree", "-rz", "--full-tree", "HEAD"],
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if completed.returncode:
        raise CopyPolicyError("git ls-tree HEAD failed; no working-tree files were read")
    return parse_ls_tree(completed.stdout)


def build_plan(
    entries: Iterable[GitTreeEntry],
    *,
    policy: CopyPolicy | None = None,
    required_files: Iterable[str] = REQUIRED_COPY_FILES,
) -> CopyPlan:
    policy = policy or CopyPolicy()
    allowed: list[GitTreeEntry] = []
    protected_rejected = 0
    ignored = 0
    seen: set[str] = set()

    for entry in entries:
        normalized, key = normalize_git_relative(entry.relative_path)
        if key in seen:
            raise CopyPolicyError("case-insensitive duplicate Git path rejected")
        seen.add(key)

        classification = policy.classify(normalized)
        if classification == "protected":
            protected_rejected += 1
            continue
        if classification == "ignored":
            ignored += 1
            continue
        if entry.object_type != "blob":
            raise CopyPolicyError("non-blob allowed source rejected before filesystem I/O")
        if entry.mode == "120000":
            raise CopyPolicyError("tracked symlink rejected before filesystem I/O")
        if entry.mode not in {"100644", "100755"}:
            raise CopyPolicyError("unsupported tracked mode rejected before filesystem I/O")
        allowed.append(
            GitTreeEntry(entry.mode, entry.object_type, entry.object_id, normalized)
        )

    allowed_keys = {entry.relative_path.casefold() for entry in allowed}
    required_keys = {normalize_git_relative(path)[1] for path in required_files}
    if not required_keys.issubset(allowed_keys):
        raise CopyPolicyError("reviewed CI surface is missing one or more required files")

    return CopyPlan(tuple(allowed), protected_rejected, ignored)


class WorkingTreeCopyGuard:
    """Reject links/reparse points before destination creation or file copying."""

    def __init__(
        self,
        source_root: Path,
        *,
        policy: CopyPolicy | None = None,
        lstat_impl: Callable[[Path], os.stat_result] = os.lstat,
        mkdir_impl: Callable[[Path], None] | None = None,
        copy_impl: Callable[[Path, Path], object] = shutil.copy2,
    ):
        self.source_root = Path(os.path.abspath(os.fspath(source_root)))
        self.policy = policy or CopyPolicy()
        self.lstat_impl = lstat_impl
        self.mkdir_impl = mkdir_impl or (
            lambda path: path.mkdir(parents=True, exist_ok=True)
        )
        self.copy_impl = copy_impl
        self.allowed_io_calls = 0

    def _reject_links_or_reparse(self, normalized: str) -> Path:
        current = self.source_root
        reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
        for part in normalized.split("/"):
            current = current / part
            metadata = self.lstat_impl(current)
            self.allowed_io_calls += 1
            attributes = getattr(metadata, "st_file_attributes", 0)
            if stat.S_ISLNK(metadata.st_mode) or attributes & reparse_flag:
                raise CopyPolicyError(
                    "symlink/reparse source rejected before destination or copy I/O"
                )
        return current

    def copy_entry(self, entry: GitTreeEntry, target_root: Path) -> None:
        normalized = self.policy.require_allowed(entry.relative_path)
        if entry.object_type != "blob" or entry.mode == "120000":
            raise CopyPolicyError("non-file or symlink rejected before filesystem I/O")

        source = self._reject_links_or_reparse(normalized)
        destination = target_root.joinpath(*normalized.split("/"))
        self.mkdir_impl(destination.parent)
        self.copy_impl(source, destination)


def _absolute_path(value: Path) -> Path:
    return Path(os.path.abspath(os.fspath(value)))


def create_filtered_copy(repo_root: Path, target_root: Path) -> CopySummary:
    source = _absolute_path(repo_root)
    target = _absolute_path(target_root)
    try:
        common = Path(os.path.commonpath((os.fspath(source), os.fspath(target))))
    except ValueError as exc:
        raise CopyPolicyError("copy roots cannot be compared safely") from exc
    if common == source:
        raise CopyPolicyError("CI target must be outside the source checkout")
    if target.exists():
        if not target.is_dir() or any(target.iterdir()):
            raise CopyPolicyError("CI target must be absent or an empty directory")

    plan = build_plan(list_git_tree(source))
    target.mkdir(parents=True, exist_ok=True)
    guard = WorkingTreeCopyGuard(source)
    copied = 0
    for entry in plan.allowed:
        guard.copy_entry(entry, target)
        copied += 1
    return CopySummary(
        allowed=len(plan.allowed),
        protected_rejected=plan.protected_rejected,
        ignored=plan.ignored,
        copied=copied,
    )


def _parse_args(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Create a protected-data-free Windows CI working copy."
    )
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--target", required=True, type=Path)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(sys.argv[1:] if argv is None else argv)
    try:
        summary = create_filtered_copy(args.source, args.target)
    except CopyPolicyError as exc:
        print(f"windows-ci-copy: error: {exc}", file=sys.stderr)
        return 2
    print(
        "windows-ci-copy: "
        f"allowed={summary.allowed} "
        f"protected_rejected={summary.protected_rejected} "
        f"ignored={summary.ignored} "
        f"copied={summary.copied}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
