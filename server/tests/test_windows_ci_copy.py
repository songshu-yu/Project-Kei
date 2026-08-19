from __future__ import annotations

import os
from pathlib import Path
import stat
import sys
import types
import unittest


REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, os.fspath(REPO_ROOT / "scripts"))

from windows_ci_copy import (  # noqa: E402
    CopyPolicy,
    CopyPolicyError,
    GitTreeEntry,
    WorkingTreeCopyGuard,
    build_plan,
    list_git_tree,
)


PROTECTED_SENTINELS = (
    ".env",
    "README.local.md",
    "server/.env",
    "server/data/affection_state.json",
    "server/systems/data/focus_timer.json",
    "server/qq_bridge/data/runtime.json",
    "server/qq_bridge/runtime/session.json",
    "server/cache/private.json",
    "server/profiles/private.json",
    "server/models/asr/model.bin",
    "server/reference_audio/reference.wav",
    "server/voice_packs/registry.json",
    "external/GPT-SoVITS/api.py",
    "vendor/engine/source.py",
    ".venv/Scripts/python.exe",
    "server/.venv-asr/Scripts/python.exe",
    "server/qq_bridge/node_modules/package/index.js",
    ".github/workflows/evil.yml",
    ".github/actions/unsafe/action.yml",
    ".GitHub/workflows/windows-install.yml",
)


def _entry(relative_path: str, *, mode: str = "100644") -> GitTreeEntry:
    return GitTreeEntry(mode, "blob", "0" * 40, relative_path)


def _regular_metadata(*, attributes: int = 0):
    return types.SimpleNamespace(st_mode=stat.S_IFREG, st_file_attributes=attributes)


class WindowsCiCopyTripwireTests(unittest.TestCase):
    def test_only_exact_reviewed_workflow_crosses_github_boundary(self):
        workflow = ".github/workflows/windows-install.yml"
        policy = CopyPolicy()
        self.assertEqual("allowed", policy.classify(workflow))
        for candidate in (
            ".github/workflows/evil.yml",
            ".github/actions/unsafe/action.yml",
            ".GitHub/workflows/windows-install.yml",
            ".github/WORKFLOWS/windows-install.yml",
            ".github/workflows/WINDOWS-INSTALL.yml",
        ):
            with self.subTest(candidate=candidate):
                self.assertEqual("protected", policy.classify(candidate))

        calls: list[str] = []
        guard = WorkingTreeCopyGuard(
            Path("synthetic-source"),
            lstat_impl=lambda path: (
                calls.append(f"lstat:{path.name}") or _regular_metadata()
            ),
            mkdir_impl=lambda path: calls.append("mkdir"),
            copy_impl=lambda source, target: calls.append("copy"),
        )
        guard.copy_entry(_entry(workflow), Path("synthetic-target"))
        self.assertEqual(
            [
                "lstat:.github",
                "lstat:workflows",
                "lstat:windows-install.yml",
                "mkdir",
                "copy",
            ],
            calls,
        )

        for kind in ("symlink", "reparse"):
            with self.subTest(kind=kind):
                guarded_calls: list[str] = []

                def fake_lstat(path: Path):
                    guarded_calls.append(f"lstat:{path.name}")
                    if path.name == "workflows":
                        if kind == "symlink":
                            return types.SimpleNamespace(
                                st_mode=stat.S_IFLNK, st_file_attributes=0
                            )
                        return _regular_metadata(attributes=0x400)
                    return _regular_metadata()

                guarded = WorkingTreeCopyGuard(
                    Path("synthetic-source"),
                    lstat_impl=fake_lstat,
                    mkdir_impl=lambda path: guarded_calls.append("mkdir"),
                    copy_impl=lambda source, target: guarded_calls.append("copy"),
                )
                with self.assertRaises(CopyPolicyError):
                    guarded.copy_entry(_entry(workflow), Path("synthetic-target"))
                self.assertNotIn("mkdir", guarded_calls)
                self.assertNotIn("copy", guarded_calls)

        with self.assertRaises(CopyPolicyError):
            build_plan((), required_files=(workflow,))
        with self.assertRaises(CopyPolicyError):
            build_plan(
                (_entry(".GitHub/workflows/windows-install.yml"),),
                required_files=(workflow,),
            )
        with self.assertRaises(CopyPolicyError):
            build_plan(
                (_entry(workflow, mode="120000"),),
                required_files=(workflow,),
            )

    def test_protected_absolute_and_traversal_candidates_stop_before_io(self):
        calls: list[tuple[str, str]] = []
        guard = WorkingTreeCopyGuard(
            Path("synthetic-source"),
            lstat_impl=lambda path: calls.append(("lstat", os.fspath(path))),
            mkdir_impl=lambda path: calls.append(("mkdir", os.fspath(path))),
            copy_impl=lambda source, target: calls.append(("copy", os.fspath(source))),
        )
        candidates = (
            *PROTECTED_SENTINELS,
            "C:/outside/secret.json",
            "/outside/secret.json",
            "../outside/secret.json",
            "server/../outside/secret.json",
            "server\\data\\secret.json",
            ".github/workflows/../actions/evil.yml",
            ".github\\workflows\\windows-install.yml",
        )
        for candidate in candidates:
            with self.subTest(candidate=candidate):
                before = len(calls)
                with self.assertRaises(CopyPolicyError):
                    guard.copy_entry(_entry(candidate), Path("synthetic-target"))
                self.assertEqual(before, len(calls))

    def test_git_symlink_mode_stops_before_io(self):
        calls: list[str] = []
        guard = WorkingTreeCopyGuard(
            Path("synthetic-source"),
            lstat_impl=lambda path: calls.append("lstat"),
            mkdir_impl=lambda path: calls.append("mkdir"),
            copy_impl=lambda source, target: calls.append("copy"),
        )
        with self.assertRaises(CopyPolicyError):
            guard.copy_entry(
                _entry("scripts/setup.ps1", mode="120000"),
                Path("synthetic-target"),
            )
        self.assertEqual([], calls)

    def test_source_symlink_and_reparse_stop_before_destination_io(self):
        for kind in ("symlink", "reparse"):
            with self.subTest(kind=kind):
                calls: list[str] = []

                def fake_lstat(path: Path):
                    calls.append("lstat")
                    if path.name == "scripts":
                        if kind == "symlink":
                            return types.SimpleNamespace(
                                st_mode=stat.S_IFLNK, st_file_attributes=0
                            )
                        return _regular_metadata(attributes=0x400)
                    return _regular_metadata()

                guard = WorkingTreeCopyGuard(
                    Path("synthetic-source"),
                    lstat_impl=fake_lstat,
                    mkdir_impl=lambda path: calls.append("mkdir"),
                    copy_impl=lambda source, target: calls.append("copy"),
                )
                with self.assertRaises(CopyPolicyError):
                    guard.copy_entry(
                        _entry("scripts/setup.ps1"), Path("synthetic-target")
                    )
                self.assertNotIn("mkdir", calls)
                self.assertNotIn("copy", calls)

    def test_allowed_surface_reaches_copy_only_after_component_lstat(self):
        calls: list[str] = []
        guard = WorkingTreeCopyGuard(
            Path("synthetic-source"),
            lstat_impl=lambda path: (
                calls.append(f"lstat:{path.name}") or _regular_metadata()
            ),
            mkdir_impl=lambda path: calls.append("mkdir"),
            copy_impl=lambda source, target: calls.append("copy"),
        )
        guard.copy_entry(_entry("scripts/setup.ps1"), Path("synthetic-target"))
        self.assertEqual(
            ["lstat:scripts", "lstat:setup.ps1", "mkdir", "copy"],
            calls,
        )

    def test_voice_pack_production_code_is_not_confused_with_user_registry(self):
        policy = CopyPolicy()
        self.assertEqual(
            "allowed",
            policy.classify("server/features/voice/voice_packs/service.py"),
        )
        for candidate in (
            "server/voice_packs/registry.json",
            "server/features/voice/voice_packs/reference.wav",
            "server/features/voice/voice_packs/voice_pack_registry.local.json",
        ):
            with self.subTest(candidate=candidate):
                self.assertEqual("protected", policy.classify(candidate))

    def test_current_git_tree_plan_uses_metadata_only_and_keeps_required_surface(self):
        if not (REPO_ROOT / ".git").exists():
            self.skipTest("filtered CI copy intentionally has no Git metadata")
        entries = list(list_git_tree(REPO_ROOT))
        tracked = {entry.relative_path.casefold() for entry in entries}
        for relative_path in (
            "pyproject.toml",
            "scripts/check_python_test_inventory.py",
            "requirements/voice-media.in",
            "requirements/voice-media-win.lock.txt",
            "server/tests/_parameter_contract.py",
            "server/tests/conftest.py",
            "server/tests/python-test-inventory.json",
        ):
            if relative_path.casefold() in tracked:
                continue
            metadata = (REPO_ROOT / relative_path).lstat()
            self.assertTrue(stat.S_ISREG(metadata.st_mode))
            self.assertFalse(stat.S_ISLNK(metadata.st_mode))
            self.assertFalse(getattr(metadata, "st_file_attributes", 0) & 0x400)
            entries.append(_entry(relative_path))
        policy = CopyPolicy()
        expected_protected = sum(
            policy.classify(entry.relative_path) == "protected" for entry in entries
        )
        plan = build_plan(entries)
        self.assertEqual(expected_protected, plan.protected_rejected)
        self.assertGreater(len(plan.allowed), 100)
        allowed = {entry.relative_path.casefold() for entry in plan.allowed}
        self.assertEqual("allowed", CopyPolicy().classify(".gitattributes"))
        self.assertIn("setup.bat", allowed)
        self.assertIn("pyproject.toml", allowed)
        self.assertIn(".github/workflows/windows-install.yml", allowed)
        self.assertIn("voice-pack.bat", allowed)
        self.assertIn("voice-pack-build.bat", allowed)
        self.assertIn("scripts/setup.ps1", allowed)
        self.assertIn("requirements/voice-media-win.lock.txt", allowed)
        self.assertIn("server/api.py", allowed)
        self.assertIn("server/features/voice/voice_packs/service.py", allowed)
        self.assertIn("server/qq_bridge/package-lock.json", allowed)
        self.assertNotIn("server/data/affection_state.json", allowed)
        self.assertNotIn("server/systems/data/focus_timer.json", allowed)

    def test_workflow_freezes_filtered_no_cache_dual_shell_matrix(self):
        workflow_path = REPO_ROOT / ".github/workflows/windows-install.yml"
        self.assertTrue(workflow_path.is_file())
        workflow = workflow_path.read_text(encoding="utf-8")
        attributes_path = REPO_ROOT / ".gitattributes"
        self.assertTrue(attributes_path.exists())
        self.assertIn(
            "requirements/*.lock.txt text eol=lf",
            attributes_path.read_text(encoding="utf-8"),
        )
        dashboard_test = (
            REPO_ROOT / "server/tests/test_dashboard_shell.py"
        ).read_text(encoding="utf-8")
        self.assertNotIn('PROJECT_ROOT.name == "project-kei"', dashboard_test)
        self.assertIn('encoding="utf-8"', dashboard_test)
        self.assertNotIn("git archive", workflow)
        self.assertNotIn("cache: npm", workflow)
        self.assertIn("windows_ci_copy.py", workflow)
        self.assertIn('python-version: ["3.10", "3.11", "3.12", "3.13"]', workflow)
        self.assertIn("python-version: ${{ matrix.python-version }}", workflow)
        self.assertIn('architecture: "x64"', workflow)
        self.assertIn('node-version: "22"', workflow)
        self.assertIn('PIP_NO_CACHE_DIR: "1"', workflow)
        self.assertIn("npm_config_cache", workflow)
        self.assertIn('PROJECT_KEI_NO_PAUSE: "1"', workflow)
        self.assertNotIn("New-Item -ItemType Directory -LiteralPath", workflow)
        self.assertIn("New-Item -ItemType Directory -Path $pipCache", workflow)
        self.assertIn("$null = subst R: /D 2>&1", workflow)
        self.assertIn("'PK020_ROOT=R:\\'", workflow)
        self.assertNotIn('"PK020_ROOT=R:\\"', workflow)
        self.assertIn(
            "$copyScript = Join-Path $env:GITHUB_WORKSPACE 'scripts\\windows_ci_copy.py'",
            workflow,
        )
        self.assertIn(
            "$unicodePath = -join ([char[]](0x4E2D, 0x6587, 0x8DEF, 0x5F84))",
            workflow,
        )
        self.assertIn('"Project Kei $unicodePath"', workflow)
        self.assertNotIn("Project Kei 中文路径", workflow)
        self.assertIn(
            "& python -B $copyScript --source $env:GITHUB_WORKSPACE --target $target",
            workflow,
        )
        self.assertIn("shell: powershell", workflow)
        self.assertIn("shell: pwsh", workflow)
        self.assertIn("setup.bat --profile voice", workflow)
        self.assertIn("doctor.bat --profile voice", workflow)
        self.assertNotIn("import pysilk", workflow)
        self.assertNotIn("metadata.version", workflow)
        self.assertIn("setup.bat --profile dev", workflow)
        self.assertIn(r".\setup.bat --profile qq", workflow)
        self.assertIn("$healthFile = Join-Path $env:RUNNER_TEMP", workflow)
        self.assertIn(r".\scripts\python.ps1 $healthFile", workflow)
        self.assertNotIn(r".\scripts\python.ps1 -c $healthCheck", workflow)
        self.assertGreaterEqual(workflow.count("pre-install doctor unexpectedly succeeded"), 2)
        self.assertGreaterEqual(workflow.count("exit 0"), 3)
        self.assertNotIn("npm ci --ignore-scripts", workflow)
        self.assertIn(r"..\scripts\check_python_test_inventory.py", workflow)
        self.assertIn("-m pytest tests", workflow)
        self.assertIn(
            r"-m ruff check tests ..\scripts\check_python_test_inventory.py",
            workflow,
        )
        self.assertNotIn("test_conversation_module.py", workflow)


if __name__ == "__main__":
    unittest.main()
