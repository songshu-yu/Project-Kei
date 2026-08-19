from __future__ import annotations

import contextlib
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import socket
import stat
import subprocess
import tempfile
import types
import unittest
from unittest import mock


REPO_ROOT = Path(__file__).resolve().parents[2]
POWERSHELL = shutil.which("powershell.exe") or shutil.which("powershell")

INSTALL_SURFACE_FILES = (
    "setup.bat",
    "doctor.bat",
    "start.bat",
    "scripts/project-kei.common.ps1",
    "scripts/project-kei.pause.cmd",
    "scripts/resolve_qq_module_runtime.py",
    "scripts/setup.ps1",
    "scripts/doctor.ps1",
    "scripts/start.ps1",
    "scripts/supervise_core.py",
    "server/core/restart_supervisor.py",
    "requirements/core.in",
    "requirements/core-win.lock.txt",
    "requirements/asr.in",
    "requirements/asr-win.lock.txt",
    "requirements/voice-media.in",
    "requirements/voice-media-win.lock.txt",
    "requirements/dev.in",
    "requirements/dev-win.lock.txt",
    "requirements/lock-manifest.json",
    "server/core/modules/__init__.py",
    "server/core/modules/assembly.py",
    "server/core/modules/contracts.py",
    "server/core/modules/exceptions.py",
    "server/core/modules/loader.py",
    "server/core/modules/manager.py",
    "server/core/modules/manifest.py",
    "server/core/modules/manifest.schema.json",
    "server/core/modules/registry.py",
    "server/core/modules/runtime_requirements.py",
    "server/core/modules/sidecar.py",
    "server/qq_bridge/package.json",
    "server/qq_bridge/package-lock.json",
)

USER_BATCH_FILES = (
    "setup.bat",
    "doctor.bat",
    "start.bat",
    "voice-pack.bat",
    "voice-pack-build.bat",
    "server/start_api.bat",
    "server/start_asr.bat",
    "server/start_gptsovits.bat",
    "server/start_all_services.bat",
    "server/prebuild_daily_briefing.bat",
    "server/qq_bridge/start_qq_bridge.bat",
)

PROTECTED_INSTALL_PREFIXES = (
    ".env",
    "README.local.md",
    "server/.env",
    "server/qq_bridge/.env",
    "server/qq_bridge/data",
    "server/data",
    "server/systems/data",
    "server/cache",
    "server/models",
    "server/profiles",
    "server/reference_audio",
    "server/voice_packs",
    "vendor",
    "external",
)

PROTECTED_SYNTHETIC_SENTINELS = {
    "qq-data": "server/qq_bridge/data/runtime-state.json",
    "server-env": "server/.env",
    "qq-env": "server/qq_bridge/.env",
    "cache": "server/cache/briefing-cache.json",
    "personal-state": "server/systems/data/personal-state.json",
    "source-list": "server/data/intel_sources.json",
    "llm-profile": "server/data/llm_profile.json",
    "model": "server/models/asr/model.bin",
    "reference-audio": "server/reference_audio/reference.wav",
    "voice-pack-registry": "server/data/voice_pack_registry.local.json",
    "external-gpt-sovits": "external/GPT-SoVITS/api.py",
}

RUNTIME_SCAN_SUFFIXES = {".py", ".ps1", ".bat", ".cmd", ".mjs", ".json"}

RUNTIME_SCAN_ALLOWED_PREFIXES = (
    "scripts/",
    "requirements/",
    "server/core/",
    "server/features/",
    "server/intel/",
    "server/services/",
    "server/scripts/",
    "server/static/",
    "server/systems/",
    "server/qq_bridge/src/",
    "client/",
    "pi_client/",
)

RUNTIME_SCAN_ALLOWED_FILES = {
    "setup.bat",
    "doctor.bat",
    "start.bat",
    "voice-pack.bat",
    "voice-pack-build.bat",
    "server/qq_bridge/package.json",
    "server/qq_bridge/package-lock.json",
}

RUNTIME_SCAN_PROTECTED_PREFIXES = (
    ".git/",
    ".venv/",
    ".venv-asr/",
    "cyber_girlfriend/",
    "external/",
    "tasks/",
    "vendor/",
    "server/cache/",
    "server/data/",
    "server/intel_history/",
    "server/models/",
    "server/output/",
    "server/profiles/",
    "server/reference_audio/",
    "server/runtime/",
    "server/voice_packs/",
    "server/systems/data/",
    "server/qq_bridge/data/",
    "server/qq_bridge/node_modules/",
)

RUNTIME_SCAN_PROTECTED_BASENAMES = {
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
    "voice_pack_registry.local.json",
}

RUNTIME_SCAN_PROTECTED_SUFFIXES = {
    ".bin",
    ".ckpt",
    ".flac",
    ".mp3",
    ".onnx",
    ".pth",
    ".pt",
    ".safetensors",
    ".wav",
}

RUNTIME_SCAN_SYNTHETIC_SENTINELS = {
    **PROTECTED_SYNTHETIC_SENTINELS,
    "local-readme": "README.local.md",
    "runtime-registry": "server/runtime/modules/registry.json",
    "generated-audio": "server/output/generated.wav",
    "local-profile-directory": "server/profiles/private.json",
    "tracked-personal-state": "server/data/affection_state.json",
    "tracked-system-state": "server/systems/data/calendar_memo.json",
}


def _portable_path_key(value: str | Path) -> str:
    return "/".join(part.casefold() for part in Path(value).parts)


def _normalize_runtime_relative(value: str) -> tuple[str, str] | None:
    normalized = value.replace("\\", "/")
    while normalized.startswith("./"):
        normalized = normalized[2:]
    parts = normalized.split("/")
    if (
        not normalized
        or normalized.startswith("/")
        or ":" in parts[0]
        or any(part in ("", ".", "..") for part in parts)
    ):
        return None
    return normalized, normalized.casefold()


class InstallSurfaceTripwire:
    """Reject non-install and protected sources before the underlying copy I/O."""

    def __init__(
        self,
        source_root: Path,
        *,
        copy_impl=shutil.copy2,
        lstat_impl=os.lstat,
    ):
        self.source_root = Path(os.path.abspath(os.fspath(source_root)))
        self.allowed = {_portable_path_key(path) for path in INSTALL_SURFACE_FILES}
        self.protected = tuple(_portable_path_key(path) for path in PROTECTED_INSTALL_PREFIXES)
        self.copy_impl = copy_impl
        self.lstat_impl = lstat_impl
        self.copied: list[str] = []
        self.rejected: list[str] = []

    def _source_relative(self, source: Path) -> Path:
        absolute = Path(os.path.abspath(os.fspath(source)))
        try:
            return absolute.relative_to(self.source_root)
        except ValueError as exc:
            self.rejected.append(os.fspath(absolute))
            raise PermissionError("install-surface source is outside the synthetic/project root") from exc

    def _reject_link_or_reparse(self, relative: Path, source_key: str):
        current = self.source_root
        reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
        for part in relative.parts:
            current = current / part
            metadata = self.lstat_impl(current)
            attributes = getattr(metadata, "st_file_attributes", 0)
            if stat.S_ISLNK(metadata.st_mode) or attributes & reparse_flag:
                self.rejected.append(source_key)
                raise PermissionError(
                    f"link/reparse install-surface source rejected: {source_key}"
                )

    def copy_file(self, source: Path, destination: Path):
        relative = self._source_relative(source)
        source_key = _portable_path_key(relative)
        if any(
            source_key == prefix or source_key.startswith(prefix + "/")
            for prefix in self.protected
        ):
            self.rejected.append(source_key)
            raise PermissionError(f"protected install-surface source rejected: {source_key}")
        if source_key not in self.allowed:
            self.rejected.append(source_key)
            raise PermissionError(f"non-whitelisted install-surface source rejected: {source_key}")
        self._reject_link_or_reparse(relative, source_key)
        result = self.copy_impl(source, destination)
        self.copied.append(source_key)
        return result


class RuntimePathScanTripwire:
    """Classify relative strings before constructing paths or invoking file I/O."""

    def __init__(
        self,
        repo_root: Path,
        *,
        is_file_impl=None,
        read_text_impl=None,
    ):
        self.repo_root = repo_root
        self.is_file_impl = is_file_impl or (lambda path: path.is_file())
        self.read_text_impl = read_text_impl or (
            lambda path: path.read_text(encoding="utf-8", errors="ignore")
        )
        self.protected_rejections: list[str] = []
        self.ignored: list[str] = []
        self.io_calls = 0

    @staticmethod
    def _is_protected(key: str) -> bool:
        basename = key.rsplit("/", 1)[-1]
        suffix = "." + basename.rsplit(".", 1)[-1] if "." in basename else ""
        return (
            basename in RUNTIME_SCAN_PROTECTED_BASENAMES
            or suffix in RUNTIME_SCAN_PROTECTED_SUFFIXES
            or any(
                key == prefix.removesuffix("/") or key.startswith(prefix)
                for prefix in RUNTIME_SCAN_PROTECTED_PREFIXES
            )
            or "/node_modules/" in f"/{key}/"
            or "/__pycache__/" in f"/{key}/"
            or "/.pytest_cache/" in f"/{key}/"
        )

    @staticmethod
    def _is_runtime_surface(key: str) -> bool:
        if key in RUNTIME_SCAN_ALLOWED_FILES:
            return True
        if any(key.startswith(prefix) for prefix in RUNTIME_SCAN_ALLOWED_PREFIXES):
            return True
        if key.startswith("server/") and key.count("/") == 1:
            return True
        return False

    def read_candidate(self, relative_name: str) -> str | None:
        normalized = _normalize_runtime_relative(relative_name)
        if normalized is None:
            self.protected_rejections.append(relative_name)
            return None
        display_name, key = normalized
        if self._is_protected(key):
            self.protected_rejections.append(display_name)
            return None
        basename = key.rsplit("/", 1)[-1]
        suffix = "." + basename.rsplit(".", 1)[-1] if "." in basename else ""
        if suffix not in RUNTIME_SCAN_SUFFIXES or not self._is_runtime_surface(key):
            self.ignored.append(display_name)
            return None

        path = self.repo_root.joinpath(*display_name.split("/"))
        self.io_calls += 1
        if not self.is_file_impl(path):
            return None
        self.io_calls += 1
        return self.read_text_impl(path)


def run(command: list[str], *, cwd: Path, env: dict[str, str], timeout: int = 120):
    return subprocess.run(
        command,
        cwd=cwd,
        env=env,
        text=True,
        encoding="utf-8",
        errors="replace",
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=timeout,
        check=False,
    )


def tree_state(root: Path) -> dict[str, tuple[int, int]]:
    return {
        str(path.relative_to(root)): (path.stat().st_size, path.stat().st_mtime_ns)
        for path in root.rglob("*")
        if path.is_file()
    }


def module_tree_sha256(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(root.rglob("*"), key=lambda item: item.as_posix().lower()):
        if not path.is_file():
            continue
        relative = path.relative_to(root).as_posix().encode("utf-8")
        digest.update(len(relative).to_bytes(4, "big"))
        digest.update(relative)
        digest.update(path.stat().st_size.to_bytes(8, "big"))
        digest.update(path.read_bytes())
    return digest.hexdigest()


class WindowsInstallTest(unittest.TestCase):
    maxDiff = None

    def setUp(self):
        if os.name != "nt" or not POWERSHELL:
            self.skipTest("PK-020 launchers are validated on Windows")
        self._temp = tempfile.TemporaryDirectory(prefix="pk020-")
        self.temp_root = Path(self._temp.name)
        self.project = self.temp_root / "Project Kei 中文路径"
        self.protected = self.temp_root / "protected-do-not-touch"
        self.process_temp = self.temp_root / "process-temp"
        self.protected.mkdir()
        self.process_temp.mkdir()
        self.protected_sentinel = self.protected / "sentinel.bin"
        self.protected_sentinel.write_bytes(b"PK020-PROTECTED")
        install_guard = self._copy_install_surface(self.project)
        self.assertEqual(set(install_guard.copied), install_guard.allowed)
        self.assertEqual(install_guard.rejected, [])
        self.fake_site = self.project / ".fake-site"
        self.fake_bin = self.project / ".fake-bin"
        self.fake_site.mkdir()
        self.fake_bin.mkdir()
        self._write_fake_python_packages()
        self._write_fake_node(major=22)
        self.env = os.environ.copy()
        self.env["PYTHONPATH"] = str(self.fake_site)
        self.env["PATH"] = str(self.fake_bin) + os.pathsep + self.env["PATH"]
        self.env["PIP_DISABLE_PIP_VERSION_CHECK"] = "1"
        self.env["TEMP"] = str(self.process_temp)
        self.env["TMP"] = str(self.process_temp)
        self.env["FAKE_PIP_LOG"] = str(self.project / "fake-pip.log")
        self.env["FAKE_NPM_LOG"] = str(self.project / "fake-npm.log")
        self.env["FAKE_NPM_TARGET_LOG"] = str(self.project / "fake-npm-target.log")
        self.env["FAKE_PROCESS_LOG"] = str(self.project / "fake-process.log")
        self.env["PROJECT_KEI_NO_PAUSE"] = "1"
        self.env["PROJECT_KEI_NO_BROWSER"] = "1"

    def tearDown(self):
        self.assertEqual(self.protected_sentinel.read_bytes(), b"PK020-PROTECTED")
        self._temp.cleanup()

    @staticmethod
    def _copy_install_surface(target: Path, *, source_root: Path = REPO_ROOT):
        target.mkdir(parents=True)
        guard = InstallSurfaceTripwire(source_root)
        for relative_name in INSTALL_SURFACE_FILES:
            relative = Path(relative_name)
            destination = target / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            guard.copy_file(source_root / relative, destination)
        return guard

    def _assert_protected_sources_are_rejected_before_copy_io(self):
        source_root = self.temp_root / "synthetic-install-source"
        destination_root = self.temp_root / "synthetic-install-target"
        original_copy_calls = []

        for relative_name in PROTECTED_SYNTHETIC_SENTINELS.values():
            sentinel = source_root / relative_name
            sentinel.parent.mkdir(parents=True, exist_ok=True)
            sentinel.write_bytes(b"SYNTHETIC-PROTECTED")

        def original_copy_io(source, destination):
            original_copy_calls.append((source, destination))
            raise AssertionError("protected source reached original copy I/O")

        guard = InstallSurfaceTripwire(source_root, copy_impl=original_copy_io)
        for category, relative_name in PROTECTED_SYNTHETIC_SENTINELS.items():
            with self.subTest(protected_category=category):
                with self.assertRaisesRegex(PermissionError, "protected"):
                    guard.copy_file(
                        source_root / relative_name,
                        destination_root / relative_name,
                    )

        outside_source = self.temp_root / "synthetic-external-gpt-sovits" / "api.py"
        outside_source.parent.mkdir(parents=True, exist_ok=True)
        outside_source.write_bytes(b"SYNTHETIC-EXTERNAL")
        with self.assertRaisesRegex(PermissionError, "outside"):
            guard.copy_file(outside_source, destination_root / "outside-api.py")

        self.assertEqual(original_copy_calls, [])
        self.assertEqual(
            len(guard.rejected),
            len(PROTECTED_SYNTHETIC_SENTINELS) + 1,
        )

        link_copy_calls = []
        link_lstat_calls = []

        def synthetic_symlink_lstat(path):
            link_lstat_calls.append(path)
            return types.SimpleNamespace(st_mode=stat.S_IFLNK, st_file_attributes=0)

        link_guard = InstallSurfaceTripwire(
            source_root,
            copy_impl=lambda source, destination: link_copy_calls.append((source, destination)),
            lstat_impl=synthetic_symlink_lstat,
        )
        with self.assertRaisesRegex(PermissionError, "link/reparse"):
            link_guard.copy_file(source_root / "setup.bat", destination_root / "setup.bat")

        reparse_lstat_calls = []

        def synthetic_reparse_lstat(path):
            reparse_lstat_calls.append(path)
            is_reparse = Path(path).name.casefold() == "scripts"
            return types.SimpleNamespace(
                st_mode=stat.S_IFREG,
                st_file_attributes=(
                    getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
                    if is_reparse
                    else 0
                ),
            )

        reparse_guard = InstallSurfaceTripwire(
            source_root,
            copy_impl=lambda source, destination: link_copy_calls.append((source, destination)),
            lstat_impl=synthetic_reparse_lstat,
        )
        with self.assertRaisesRegex(PermissionError, "link/reparse"):
            reparse_guard.copy_file(
                source_root / "scripts" / "setup.ps1",
                destination_root / "scripts" / "setup.ps1",
            )

        self.assertEqual(link_copy_calls, [])
        self.assertEqual(len(link_lstat_calls), 1)
        self.assertEqual(len(reparse_lstat_calls), 1)

    def _assert_runtime_scan_rejects_protected_strings_before_io(self):
        io_calls = []

        def synthetic_is_file(path):
            io_calls.append(("is_file", path))
            return True

        def synthetic_read_text(path):
            io_calls.append(("read_text", path))
            return "portable"

        guard = RuntimePathScanTripwire(
            self.temp_root / "synthetic-runtime-root",
            is_file_impl=synthetic_is_file,
            read_text_impl=synthetic_read_text,
        )
        for category, relative_name in RUNTIME_SCAN_SYNTHETIC_SENTINELS.items():
            with self.subTest(runtime_protected_category=category):
                self.assertIsNone(guard.read_candidate(relative_name))

        self.assertEqual(io_calls, [])
        self.assertEqual(
            len(guard.protected_rejections),
            len(RUNTIME_SCAN_SYNTHETIC_SENTINELS),
        )
        self.assertEqual(
            guard.read_candidate("server/core/synthetic_runtime.py"),
            "portable",
        )
        self.assertEqual([operation for operation, _ in io_calls], ["is_file", "read_text"])

    def _write_fake_python_packages(self):
        pip_package = self.fake_site / "pip"
        pip_package.mkdir()
        (pip_package / "__init__.py").write_text("", encoding="utf-8")
        (pip_package / "__main__.py").write_text(
            """
import os
from pathlib import Path
import sys
log = Path(os.environ["FAKE_PIP_LOG"])
with log.open("a", encoding="utf-8") as handle:
    handle.write(" ".join(sys.argv[1:]) + "\\n")
if os.environ.get("FAKE_PIP_FAIL") == "1":
    raise SystemExit(17)
failure_lock = os.environ.get("FAKE_PIP_FAIL_LOCK", "")
if failure_lock and any(failure_lock in value for value in sys.argv[1:]):
    raise SystemExit(18)
if any("voice-media-win.lock.txt" in value for value in sys.argv[1:]):
    site = Path(sys.prefix) / "Lib" / "site-packages"
    module = site / "pysilk"
    module.mkdir(parents=True, exist_ok=True)
    (module / "__init__.py").write_text(
        "def encode(*args, **kwargs): raise RuntimeError('doctor must not encode')\\n",
        encoding="utf-8",
    )
    metadata = site / "silk_python-0.2.8.dist-info"
    metadata.mkdir(parents=True, exist_ok=True)
    (metadata / "METADATA").write_text(
        "Metadata-Version: 2.1\\nName: silk-python\\nVersion: 0.2.8\\n",
        encoding="utf-8",
    )
""".lstrip(),
            encoding="utf-8",
        )
        for name in (
            "fastapi",
            "httpx",
            "pydantic",
            "uvicorn",
            "faster_whisper",
            "pytest",
            "pytest_asyncio",
            "piptools",
        ):
            package = self.fake_site / name
            package.mkdir()
            (package / "__init__.py").write_text("", encoding="utf-8")
        (self.fake_site / "uvicorn" / "__main__.py").write_text(
            """
import os
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
import sys
Path(os.environ["FAKE_PROCESS_LOG"]).write_text(" ".join(sys.argv[1:]), encoding="utf-8")

class ReadyHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"ok")

    def log_message(self, format, *args):
        return

HTTPServer(("127.0.0.1", 8000), ReadyHandler).handle_request()
""".lstrip(),
            encoding="utf-8",
        )

    def _write_fake_node(self, *, major: int):
        (self.fake_bin / "node.cmd").write_text(
            (
                "@echo off\r\n"
                f'if "%~1"=="--version" (echo v{major}.0.0& exit /b 0)\r\n'
                'if "%~1"=="-p" (echo x64& exit /b 0)\r\n'
                "exit /b 0\r\n"
            ),
            encoding="ascii",
        )
        (self.fake_bin / "npm.cmd").write_text(
            (
                "@echo off\r\n"
                'if "%~1"=="--version" (echo 10.9.0& exit /b 0)\r\n'
                'echo %*>>"%FAKE_NPM_LOG%"\r\n'
                'if "%FAKE_NPM_FAIL%"=="1" exit /b 19\r\n'
                'if /i not "%~1"=="ci" exit /b 23\r\n'
                'for %%I in ("%CD%") do set "FAKE_NPM_DIR=%%~nxI"\r\n'
                'if "%FAKE_NPM_DIR:~0,1%"=="." (echo installed-deployment>>"%FAKE_NPM_TARGET_LOG%") else (echo legacy-source>>"%FAKE_NPM_TARGET_LOG%")\r\n'
                'mkdir "%CD%\\node_modules\\ws" 2>nul\r\n'
                '> "%CD%\\node_modules\\ws\\package.json" echo {"type":"module","main":"index.js"}\r\n'
                '> "%CD%\\node_modules\\ws\\index.js" echo export default {};\r\n'
                "exit /b 0\r\n"
            ),
            encoding="ascii",
        )

    def invoke_batch(self, name: str, *arguments: str, timeout: int = 120):
        command = ["cmd.exe", "/d", "/c", "call", str(self.project / name), *arguments]
        return run(command, cwd=self.temp_root, env=self.env, timeout=timeout)

    @contextlib.contextmanager
    def mapped_non_system_project(self):
        system_drive = Path(os.environ.get("SystemDrive", "C:")).drive.upper()
        drive = next(
            (
                f"{letter}:"
                for letter in reversed("PQRSTUVWXYZ")
                if f"{letter}:" != system_drive and not Path(f"{letter}:\\").exists()
            ),
            None,
        )
        if not drive:
            self.skipTest("no unused drive letter is available")
        mapping = run(["subst.exe", drive, str(self.temp_root)], cwd=self.temp_root, env=self.env)
        if mapping.returncode != 0:
            self.skipTest(f"subst unavailable: {mapping.stdout}")
        original = self.project
        self.project = Path(drive + "\\") / original.relative_to(self.temp_root)
        self.env["PYTHONPATH"] = str(self.project / ".fake-site")
        self.env["PATH"] = str(self.project / ".fake-bin") + os.pathsep + os.environ["PATH"]
        self.env["FAKE_PIP_LOG"] = str(self.project / "fake-pip.log")
        self.env["FAKE_NPM_LOG"] = str(self.project / "fake-npm.log")
        self.env["FAKE_NPM_TARGET_LOG"] = str(self.project / "fake-npm-target.log")
        self.env["FAKE_PROCESS_LOG"] = str(self.project / "fake-process.log")
        try:
            yield
        finally:
            self.project = original
            run(["subst.exe", drive, "/d"], cwd=self.temp_root, env=os.environ.copy())

    def test_core_setup_on_non_system_unicode_space_path_is_idempotent(self):
        with self.mapped_non_system_project():
            first = self.invoke_batch("setup.bat", "--profile", "core")
            self.assertEqual(first.returncode, 0, first.stdout)
            venv_config = self.project / ".venv" / "pyvenv.cfg"
            self.assertTrue(venv_config.is_file())
            first_stat = venv_config.stat()
            second = self.invoke_batch("setup.bat", "--profile", "core")
            self.assertEqual(second.returncode, 0, second.stdout)
            self.assertIn("reusing .venv", second.stdout)
            self.assertEqual(
                (first_stat.st_size, first_stat.st_mtime_ns),
                (venv_config.stat().st_size, venv_config.stat().st_mtime_ns),
            )
            pip_lines = (self.project / "fake-pip.log").read_text(encoding="utf-8").splitlines()
            self.assertEqual(len(pip_lines), 2)
            self.assertTrue(all("--requirement" in line for line in pip_lines))

    def test_profiles_use_locks_and_qq_uses_only_npm_ci(self):
        core = self.invoke_batch("setup.bat", "--profile=core")
        self.assertEqual(core.returncode, 0, core.stdout)
        voice = self.invoke_batch("setup.bat", "--profile", "voice")
        self.assertEqual(voice.returncode, 0, voice.stdout)
        qq = self.invoke_batch("setup.bat", "--profile", "qq")
        self.assertEqual(qq.returncode, 0, qq.stdout)
        full = self.invoke_batch("setup.bat", "--profile", "full")
        self.assertEqual(full.returncode, 0, full.stdout)
        dev = self.invoke_batch("setup.bat", "--profile", "dev")
        self.assertEqual(dev.returncode, 0, dev.stdout)
        npm_lines = (self.project / "fake-npm.log").read_text(encoding="utf-8").splitlines()
        self.assertEqual(npm_lines, ["ci --ignore-scripts", "ci --ignore-scripts"])
        pip_text = (self.project / "fake-pip.log").read_text(encoding="utf-8")
        self.assertIn("core-win.lock.txt", pip_text)
        self.assertIn("asr-win.lock.txt", pip_text)
        self.assertIn("voice-media-win.lock.txt", pip_text)
        self.assertIn("dev-win.lock.txt", pip_text)
        voice_media_lines = [
            line for line in pip_text.splitlines()
            if "voice-media-win.lock.txt" in line
        ]
        self.assertEqual(len(voice_media_lines), 2)
        self.assertTrue(all("--require-hashes" in line for line in voice_media_lines))
        self.assertTrue(all("--only-binary=:all:" in line for line in voice_media_lines))
        self.assertFalse((self.project / "server" / "qq_bridge" / ".env").exists())
        self.assertEqual(
            (self.project / "fake-npm-target.log").read_text(encoding="ascii").splitlines(),
            ["legacy-source", "legacy-source"],
        )
        voice_doctor = self.invoke_batch("doctor.bat", "--profile", "voice")
        self.assertEqual(voice_doctor.returncode, 0, voice_doctor.stdout)
        self.assertIn(
            "did not scan the disk or download anything",
            voice_doctor.stdout,
        )
        self.assertIn("no audio was encoded", voice_doctor.stdout)
        qq_doctor = self.invoke_batch("doctor.bat", "--profile", "qq")
        self.assertEqual(qq_doctor.returncode, 0, qq_doctor.stdout)
        self.assertIn("Core is unaffected", qq_doctor.stdout)

        site = self.project / ".venv" / "Lib" / "site-packages"
        shutil.rmtree(site / "pysilk")
        shutil.rmtree(site / "silk_python-0.2.8.dist-info")
        before_missing_probe = tree_state(self.project)
        core_without_media = self.invoke_batch("doctor.bat", "--profile", "core")
        self.assertEqual(core_without_media.returncode, 0, core_without_media.stdout)
        voice_without_media = self.invoke_batch("doctor.bat", "--profile", "voice")
        self.assertEqual(voice_without_media.returncode, 1, voice_without_media.stdout)
        self.assertIn("voice media unavailable (dependency_missing)", voice_without_media.stdout)
        self.assertIn("Core remains available", voice_without_media.stdout)
        self.assertEqual(tree_state(self.project), before_missing_probe)

    def _write_synthetic_installed_qq(
        self,
        *,
        current_version: str = "0.1.0",
        manifest_version: str = "0.1.0",
        record_path: str = "qq_bridge/0.1.0",
        source: str = "official_github_release",
        lock_mutator=None,
        include_lock: bool = True,
    ):
        runtime_root = self.project / "server" / "runtime" / "modules"
        registry_path = self.project / "server" / "data" / "module_registry.json"
        if runtime_root.exists():
            shutil.rmtree(runtime_root)
        package_root = runtime_root / "qq_bridge" / current_version
        sidecar_root = package_root / "sidecar"
        (sidecar_root / "src").mkdir(parents=True)
        for source_name in (
            "bridge_core.mjs",
            "business_menu.mjs",
            "daily_briefing_scheduler.mjs",
            "focus_encouragement_scheduler.mjs",
            "gateway_client.mjs",
            "index.mjs",
            "life_support_scheduler.mjs",
            "shutdown_control.mjs",
            "state_store.mjs",
            "voice_reply.mjs",
        ):
            (sidecar_root / "src" / source_name).write_text(
                f"// synthetic {source_name}\n",
                encoding="utf-8",
            )
        package = json.loads(
            (self.project / "server" / "qq_bridge" / "package.json").read_text(
                encoding="utf-8"
            )
        )
        package["version"] = current_version
        (sidecar_root / "package.json").write_text(
            json.dumps(package, indent=2) + "\n",
            encoding="utf-8",
        )
        lock = json.loads(
            (self.project / "server" / "qq_bridge" / "package-lock.json").read_text(
                encoding="utf-8"
            )
        )
        lock["version"] = current_version
        lock["packages"][""]["version"] = current_version
        if lock_mutator is not None:
            lock_mutator(lock)
        if include_lock:
            (sidecar_root / "package-lock.json").write_text(
                json.dumps(lock, indent=2) + "\n",
                encoding="utf-8",
            )
        manifest = {
            "schema_version": 1,
            "id": "qq_bridge",
            "name": "QQ Bridge",
            "version": manifest_version,
            "type": "sidecar",
            "required": False,
            "core_compatibility": ">=1.0.0 <2.0.0",
            "dependencies": [],
            "optional_dependencies": [],
            "conflicts": [],
            "api_namespaces": ["/api/v1/qq-control"],
            "legacy_endpoints": [],
            "dashboard_entrypoint": None,
            "data_namespace": "qq_bridge",
            "config_schema": None,
            "permissions": ["local_state"],
            "requires_restart": False,
            "sidecar": {
                "adapter": "qq_bridge",
                "healthcheck_timeout_seconds": 15,
            },
        }
        (package_root / "manifest.json").write_text(
            json.dumps(manifest, indent=2) + "\n",
            encoding="utf-8",
        )
        installed_tree_sha256 = module_tree_sha256(package_root)
        registry = {
            "registry_version": 1,
            "modules": {
                "qq_bridge": {
                    "manifest": manifest,
                    "current_version": current_version,
                    "previous_version": None,
                    "versions": {
                        current_version: {
                            "path": record_path,
                            "source": source,
                            "sha256": "0" * 64,
                            "installed_tree_sha256": installed_tree_sha256,
                            "installed_at": "2026-07-30T00:00:00+00:00",
                        }
                    },
                    "enabled": False,
                    "configuration_ready": False,
                    "sidecar_readiness": None,
                    "state": "needs_configuration",
                    "restart_required": False,
                    "last_operation": None,
                }
            },
        }
        registry_path.parent.mkdir(parents=True, exist_ok=True)
        registry_path.write_text(
            json.dumps(registry, indent=2) + "\n",
            encoding="utf-8",
        )
        return package_root, sidecar_root, registry_path

    def test_installed_qq_module_uses_current_lock_idempotently_and_doctor_is_read_only(self):
        package_root, sidecar_root, registry_path = self._write_synthetic_installed_qq()
        registry_before = registry_path.read_bytes()
        package_before = tree_state(package_root)

        before_missing_doctor = tree_state(self.project)
        missing_doctor = self.invoke_batch("doctor.bat", "--profile", "qq")
        self.assertEqual(missing_doctor.returncode, 1, missing_doctor.stdout)
        self.assertIn(
            "installed QQ module dependencies are missing",
            missing_doctor.stdout,
        )
        self.assertNotIn(str(self.project), missing_doctor.stdout)
        self.assertEqual(tree_state(self.project), before_missing_doctor)
        self.assertFalse((self.project / "fake-npm.log").exists())

        first = self.invoke_batch("setup.bat", "--profile", "qq")
        self.assertEqual(first.returncode, 0, first.stdout)
        self.assertIn("dependency deployment now matches", first.stdout)
        second = self.invoke_batch("setup.bat", "--profile", "qq")
        self.assertEqual(second.returncode, 0, second.stdout)
        self.assertIn("dependency deployment already matches", second.stdout)
        self.assertEqual(
            (self.project / "fake-npm-target.log").read_text(encoding="ascii").splitlines(),
            ["installed-deployment"],
        )
        deployment_root = (
            self.project
            / "server"
            / "runtime"
            / "module-dependencies"
            / "qq_bridge"
            / "0.1.0"
        )
        self.assertTrue((deployment_root / "node_modules" / "ws").is_dir())
        self.assertTrue((deployment_root / "src" / "shutdown_control.mjs").is_file())
        self.assertFalse((sidecar_root / "node_modules").exists())
        self.assertFalse(
            (self.project / "server" / "qq_bridge" / "node_modules").exists()
        )
        marker = json.loads(
            (deployment_root / ".project-kei-deployment.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(
            set(marker),
            {
                "schema_version",
                "module_id",
                "version",
                "installed_tree_sha256",
                "package_json_sha256",
                "lock_sha256",
                "node_version",
                "npm_version",
            },
        )
        self.assertIn(int(marker["node_version"].split(".", 1)[0]), {20, 22, 24, 26})
        self.assertEqual(marker["npm_version"], "10.9.0")
        for name in (
            "installed_tree_sha256",
            "package_json_sha256",
            "lock_sha256",
        ):
            self.assertRegex(marker[name], r"^[0-9a-f]{64}$")
        self.assertEqual(
            {path.name for path in deployment_root.iterdir()},
            {
                ".project-kei-deployment.json",
                "package.json",
                "package-lock.json",
                "src",
                "node_modules",
            },
        )
        self.assertEqual(
            {path.name for path in (deployment_root / "src").iterdir()},
            {
                "bridge_core.mjs",
                "business_menu.mjs",
                "daily_briefing_scheduler.mjs",
                "focus_encouragement_scheduler.mjs",
                "gateway_client.mjs",
                "index.mjs",
                "life_support_scheduler.mjs",
                "shutdown_control.mjs",
                "state_store.mjs",
                "voice_reply.mjs",
            },
        )
        self.assertEqual(tree_state(package_root), package_before)
        self.assertEqual(registry_path.read_bytes(), registry_before)
        self.assertFalse((self.project / "server" / "qq_bridge" / ".env").exists())
        self.assertFalse((self.project / "server" / "qq_bridge" / "data").exists())
        self.assertFalse((self.project / "fake-process.log").exists())

        before = tree_state(package_root)
        doctor = self.invoke_batch("doctor.bat", "--profile", "qq")
        self.assertEqual(doctor.returncode, 0, doctor.stdout)
        self.assertIn(
            "deployment marker, package digests, lock, Node/npm contract, and dependencies are ready",
            doctor.stdout,
        )
        self.assertNotIn(str(self.project), doctor.stdout)
        self.assertEqual(tree_state(package_root), before)
        self.assertEqual(registry_path.read_bytes(), registry_before)
        self.assertEqual(
            (self.project / "fake-npm.log").read_text(encoding="utf-8").splitlines(),
            ["ci --ignore-scripts"],
        )

    def test_installed_qq_module_rejects_untrusted_registry_and_lock_without_npm(self):
        cases = {
            "traversal": {"record_path": "../qq_bridge/0.1.0"},
            "absolute": {"record_path": "C:/qq_bridge/0.1.0"},
            "backslash": {"record_path": "qq_bridge\\0.1.0"},
            "non-current": {"record_path": "qq_bridge/0.0.9"},
            "unknown-source": {"source": "unknown"},
            "version-mismatch": {"manifest_version": "0.0.9"},
            "missing-lock": {"include_lock": False},
            "lock-version": {
                "lock_mutator": lambda lock: lock.update(lockfileVersion=2)
            },
            "lock-root-name": {
                "lock_mutator": lambda lock: lock["packages"][""].update(
                    name="not-project-kei"
                )
            },
            "private-registry": {
                "lock_mutator": lambda lock: lock["packages"]["node_modules/ws"].update(
                    resolved="https://packages.invalid/ws.tgz"
                )
            },
            "missing-integrity": {
                "lock_mutator": lambda lock: lock["packages"]["node_modules/ws"].pop(
                    "integrity", None
                )
            },
        }
        for name, arguments in cases.items():
            with self.subTest(name=name):
                for log_name in ("fake-npm.log", "fake-npm-target.log"):
                    (self.project / log_name).unlink(missing_ok=True)
                self._write_synthetic_installed_qq(**arguments)
                result = self.invoke_batch("setup.bat", "--profile", "qq")
                self.assertEqual(result.returncode, 14, result.stdout)
                self.assertIn("installed_qq_module_invalid:", result.stdout)
                self.assertFalse((self.project / "fake-npm.log").exists())
                self.assertFalse((self.project / "fake-npm-target.log").exists())
                self.assertFalse((self.project / "fake-process.log").exists())
                qq_error_lines = [
                    line
                    for line in result.stdout.splitlines()
                    if "installed_qq_module_invalid:" in line
                ]
                self.assertEqual(len(qq_error_lines), 1)
                self.assertNotIn(str(self.project), qq_error_lines[0])

        for log_name in ("fake-npm.log", "fake-npm-target.log"):
            (self.project / log_name).unlink(missing_ok=True)
        _, sidecar_root, _ = self._write_synthetic_installed_qq()
        (sidecar_root / "src" / "index.mjs").write_text(
            "// changed after registry digest\n",
            encoding="utf-8",
        )
        digest_mismatch = self.invoke_batch("setup.bat", "--profile", "qq")
        self.assertEqual(digest_mismatch.returncode, 14, digest_mismatch.stdout)
        self.assertIn("qq_module_package_digest_mismatch", digest_mismatch.stdout)
        self.assertFalse((self.project / "fake-npm.log").exists())

    def test_local_zip_qq_module_receives_the_same_locked_dependency_deployment(self):
        package_root, sidecar_root, registry_path = self._write_synthetic_installed_qq(
            source="local_import"
        )
        package_before = tree_state(package_root)
        registry_before = registry_path.read_bytes()

        first = self.invoke_batch("setup.bat", "--profile", "qq")
        self.assertEqual(first.returncode, 0, first.stdout)
        self.assertIn("dependency deployment now matches", first.stdout)
        second = self.invoke_batch("doctor.bat", "--profile", "qq")
        self.assertEqual(second.returncode, 0, second.stdout)
        self.assertEqual(tree_state(package_root), package_before)
        self.assertEqual(registry_path.read_bytes(), registry_before)
        self.assertFalse((sidecar_root / "node_modules").exists())
        self.assertEqual(
            (self.project / "fake-npm-target.log").read_text(encoding="ascii").splitlines(),
            ["installed-deployment"],
        )

    def test_node_26_x64_is_accepted_for_the_qq_profile(self):
        self._write_fake_node(major=26)
        result = self.invoke_batch("setup.bat", "--profile", "qq")
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertNotIn("Node.js 20, 22, 24, or 26 x64 is unavailable", result.stdout)

    def test_installed_qq_module_npm_failure_is_stable_and_has_no_business_side_effects(self):
        package_root, sidecar_root, registry_path = self._write_synthetic_installed_qq()
        registry_before = registry_path.read_bytes()
        package_before = tree_state(package_root)
        self.env["FAKE_NPM_FAIL"] = "1"

        result = self.invoke_batch("setup.bat", "--profile", "qq")

        self.assertEqual(result.returncode, 14, result.stdout)
        self.assertIn("npm_ci_failed for installed QQ module", result.stdout)
        self.assertEqual(
            (self.project / "fake-npm.log").read_text(encoding="utf-8").splitlines(),
            ["ci --ignore-scripts"],
        )
        self.assertFalse((sidecar_root / "node_modules").exists())
        dependency_parent = (
            self.project
            / "server"
            / "runtime"
            / "module-dependencies"
            / "qq_bridge"
        )
        self.assertFalse((dependency_parent / "0.1.0").exists())
        self.assertEqual(
            list(dependency_parent.glob(".*.staging-*"))
            if dependency_parent.exists()
            else [],
            [],
        )
        self.assertEqual(tree_state(package_root), package_before)
        self.assertEqual(registry_path.read_bytes(), registry_before)
        self.assertFalse((self.project / "server" / "qq_bridge" / ".env").exists())
        self.assertFalse((self.project / "server" / "qq_bridge" / "data").exists())
        self.assertFalse((self.project / "fake-process.log").exists())

    def test_qq_module_resolver_rejects_attack_strings_and_reparse_before_package_io(self):
        helper_path = REPO_ROOT / "scripts" / "resolve_qq_module_runtime.py"
        spec = importlib.util.spec_from_file_location("pk020_qq_resolver_test", helper_path)
        resolver = importlib.util.module_from_spec(spec)
        assert spec and spec.loader
        spec.loader.exec_module(resolver)

        _, sidecar_root, registry_path = self._write_synthetic_installed_qq(
            record_path="../outside"
        )
        package_io = mock.Mock(side_effect=AssertionError("package I/O reached"))
        with mock.patch.object(resolver, "_copy_allowlist", package_io):
            with self.assertRaisesRegex(
                resolver.DeploymentError, "qq_module_registry_invalid"
            ):
                resolver.prepare(self.project)
        package_io.assert_not_called()

        copy_io = mock.Mock(side_effect=AssertionError("copy I/O reached"))
        original_lstat = resolver.os.lstat
        attacked = sidecar_root / "package.json"

        def reparse_file(path):
            metadata = original_lstat(path)
            if Path(path) == attacked:
                return types.SimpleNamespace(
                    st_mode=stat.S_IFREG,
                    st_nlink=1,
                    st_file_attributes=getattr(
                        stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400
                    ),
                )
            return metadata

        destination = self.temp_root / "synthetic-deployment"
        with mock.patch.object(resolver.os, "lstat", side_effect=reparse_file):
            with mock.patch.object(resolver.shutil, "copyfile", copy_io):
                with self.assertRaisesRegex(
                    resolver.DeploymentError, "qq_module_link_rejected"
                ):
                    resolver._copy_allowlist(sidecar_root, destination)
        copy_io.assert_not_called()

        def hardlinked_file(path):
            metadata = original_lstat(path)
            if Path(path) == attacked:
                return types.SimpleNamespace(
                    st_mode=stat.S_IFREG,
                    st_nlink=2,
                    st_file_attributes=0,
                )
            return metadata

        with mock.patch.object(resolver.os, "lstat", side_effect=hardlinked_file):
            with mock.patch.object(resolver.shutil, "copyfile", copy_io):
                with self.assertRaisesRegex(
                    resolver.DeploymentError, "qq_module_link_rejected"
                ):
                    resolver._copy_allowlist(sidecar_root, destination)
        copy_io.assert_not_called()
        self.assertTrue(registry_path.is_file())

    def test_qq_dependency_deployments_are_version_isolated_and_fail_atomically(self):
        package_v1, _, _ = self._write_synthetic_installed_qq()
        first = self.invoke_batch("setup.bat", "--profile", "qq")
        self.assertEqual(first.returncode, 0, first.stdout)
        dependencies = (
            self.project / "server" / "runtime" / "module-dependencies" / "qq_bridge"
        )
        version_one_before = tree_state(dependencies / "0.1.0")
        self._write_synthetic_installed_qq(
            current_version="0.2.0",
            manifest_version="0.2.0",
            record_path="qq_bridge/0.2.0",
        )
        self.env["FAKE_NPM_FAIL"] = "1"
        failed = self.invoke_batch("setup.bat", "--profile", "qq")
        self.assertEqual(failed.returncode, 14, failed.stdout)
        self.assertEqual(tree_state(dependencies / "0.1.0"), version_one_before)
        self.assertFalse((dependencies / "0.2.0").exists())
        self.assertFalse(any(dependencies.glob(".0.2.0.staging-*")))

        self.env.pop("FAKE_NPM_FAIL")
        succeeded = self.invoke_batch("setup.bat", "--profile", "qq")
        self.assertEqual(succeeded.returncode, 0, succeeded.stdout)
        self.assertTrue((dependencies / "0.1.0").is_dir())
        self.assertTrue((dependencies / "0.2.0").is_dir())
        self.assertEqual(tree_state(dependencies / "0.1.0"), version_one_before)
        self.assertFalse((package_v1 / "sidecar" / "node_modules").exists())

    def test_qq_dependency_marker_tamper_fails_closed_without_npm(self):
        package_root, _, _ = self._write_synthetic_installed_qq()
        setup = self.invoke_batch("setup.bat", "--profile", "qq")
        self.assertEqual(setup.returncode, 0, setup.stdout)
        marker_path = (
            self.project
            / "server"
            / "runtime"
            / "module-dependencies"
            / "qq_bridge"
            / "0.1.0"
            / ".project-kei-deployment.json"
        )
        marker = json.loads(marker_path.read_text(encoding="utf-8"))
        marker["unexpected"] = "rejected"
        marker_path.write_text(json.dumps(marker), encoding="utf-8")
        npm_before = (self.project / "fake-npm.log").read_bytes()
        package_before = tree_state(package_root)

        doctor = self.invoke_batch("doctor.bat", "--profile", "qq")
        self.assertEqual(doctor.returncode, 1, doctor.stdout)
        self.assertIn("qq_module_deployment_marker_invalid", doctor.stdout)
        rerun = self.invoke_batch("setup.bat", "--profile", "qq")
        self.assertEqual(rerun.returncode, 14, rerun.stdout)
        self.assertIn("qq_module_deployment_marker_invalid", rerun.stdout)
        self.assertEqual((self.project / "fake-npm.log").read_bytes(), npm_before)
        self.assertEqual(tree_state(package_root), package_before)

    def test_doctor_is_read_only_and_does_not_invoke_installers(self):
        self._assert_protected_sources_are_rejected_before_copy_io()
        setup = self.invoke_batch("setup.bat", "--profile", "core")
        self.assertEqual(setup.returncode, 0, setup.stdout)
        pip_before = (self.project / "fake-pip.log").read_text(encoding="utf-8")
        before = tree_state(self.project)
        doctor = self.invoke_batch("doctor.bat", "--profile", "core")
        self.assertEqual(doctor.returncode, 0, doctor.stdout)
        self.assertEqual(before, tree_state(self.project))
        self.assertEqual(pip_before, (self.project / "fake-pip.log").read_text(encoding="utf-8"))
        self.assertFalse((self.project / "fake-npm.log").exists())
        self.assertNotIn("Invoke-WebRequest", doctor.stdout)

    def test_start_does_not_install_or_create_configuration(self):
        setup = self.invoke_batch("setup.bat", "--profile", "qq")
        self.assertEqual(setup.returncode, 0, setup.stdout)
        pip_before = (self.project / "fake-pip.log").read_text(encoding="utf-8")
        npm_before = (self.project / "fake-npm.log").read_text(encoding="utf-8")
        probe = socket.socket()
        try:
            probe.bind(("127.0.0.1", 8000))
        except OSError:
            self.skipTest("port 8000 is already occupied")
        finally:
            probe.close()
        core = self.invoke_batch("start.bat")
        self.assertEqual(core.returncode, 0, core.stdout)
        self.assertIn("http://127.0.0.1:8000/dashboard", core.stdout)
        self.assertIn("automatic browser launch is disabled", core.stdout)
        self.assertIn("API listener on 127.0.0.1:8000", core.stdout)
        fake_process = (self.project / "fake-process.log").read_text(encoding="utf-8")
        self.assertIn("api:app", fake_process)
        self.assertIn("--host 127.0.0.1", fake_process)
        self.assertIn("--port 8000", fake_process)
        start = self.invoke_batch("start.bat", "--only", "qq", "--current-window")
        self.assertEqual(start.returncode, 2, start.stdout)
        self.assertIn("internal --only must be api|asr|gptsovits", start.stdout)
        self.assertEqual(pip_before, (self.project / "fake-pip.log").read_text(encoding="utf-8"))
        self.assertEqual(npm_before, (self.project / "fake-npm.log").read_text(encoding="utf-8"))
        self.assertFalse((self.project / "server" / "qq_bridge" / ".env").exists())

    def test_start_rejects_incomplete_venv_before_starting_process(self):
        setup = self.invoke_batch("setup.bat", "--profile", "core")
        self.assertEqual(setup.returncode, 0, setup.stdout)
        shutil.rmtree(self.fake_site / "uvicorn")
        process_log = self.project / "fake-process.log"
        process_log.unlink(missing_ok=True)

        started = self.invoke_batch("start.bat", "--only", "api", "--current-window")

        self.assertEqual(started.returncode, 21, started.stdout)
        self.assertIn("dependencies are incomplete", started.stdout)
        self.assertIn("setup.bat --profile core", started.stdout)
        self.assertFalse(process_log.exists())

    def test_start_all_preflights_core_before_optional_services(self):
        setup = self.invoke_batch("setup.bat", "--profile", "core")
        self.assertEqual(setup.returncode, 0, setup.stdout)
        shutil.rmtree(self.fake_site / "uvicorn")
        process_log = self.project / "fake-process.log"
        process_log.unlink(missing_ok=True)

        started = self.invoke_batch("start.bat", "--profile", "all")

        self.assertEqual(started.returncode, 21, started.stdout)
        self.assertIn("dependencies are incomplete", started.stdout)
        self.assertIn("setup.bat --profile full", started.stdout)
        self.assertNotIn("starting registered 127.0.0.1:9880", started.stdout)
        self.assertNotIn("starting sidecar in its own window", started.stdout)
        self.assertFalse(process_log.exists())

        start_text = (self.project / "scripts" / "start.ps1").read_text(encoding="utf-8")
        main_flow = start_text[start_text.index("$CoreSetupProfile = switch") :]
        self.assertLess(
            main_flow.index("$CorePreflightExit = Test-CorePreflight"),
            main_flow.index("Start-GptSoVitsOptional"),
        )
        self.assertNotIn('Arguments @("--only", "qq"', main_flow)
        self.assertIn("waits for an explicit dashboard avatar", main_flow)

    def test_voice_start_imports_only_allowlisted_asr_settings(self):
        env_file = self.project / "server" / ".env"
        synthetic_model = r"D:\Synthetic Models\中文 ASR"
        synthetic_secret = "must-not-enter-launcher-environment"
        env_file.write_text(
            "\n".join(
                (
                    f'ASR_MODEL_PATH="{synthetic_model}"',
                    "ASR_DEVICE=cpu",
                    "ASR_COMPUTE_TYPE=int8",
                    f"PROJECT_KEI_SYNTHETIC_SECRET={synthetic_secret}",
                )
            )
            + "\n",
            encoding="utf-8",
        )
        probe = self.process_temp / "asr-env-allowlist-probe.ps1"
        common = self.project / "scripts" / "project-kei.common.ps1"
        probe.write_text(
            "\n".join(
                (
                    "$ErrorActionPreference = 'Stop'",
                    f". '{str(common).replace(chr(39), chr(39) * 2)}'",
                    f"$loaded = @(Import-KeiEnvAllowlist -Path '{str(env_file).replace(chr(39), chr(39) * 2)}' -Names @('ASR_MODEL_PATH','ASR_DEVICE','ASR_COMPUTE_TYPE'))",
                    "if ($loaded.Count -ne 3) { exit 31 }",
                    "if ([string]::IsNullOrWhiteSpace($env:ASR_MODEL_PATH)) { exit 32 }",
                    "if ($env:ASR_DEVICE -ne 'cpu' -or $env:ASR_COMPUTE_TYPE -ne 'int8') { exit 33 }",
                    "if (-not [string]::IsNullOrWhiteSpace($env:PROJECT_KEI_SYNTHETIC_SECRET)) { exit 34 }",
                    "exit 0",
                )
            )
            + "\n",
            encoding="utf-8-sig",
        )
        isolated_env = self.env.copy()
        for name in (
            "ASR_MODEL_PATH",
            "ASR_DEVICE",
            "ASR_COMPUTE_TYPE",
            "PROJECT_KEI_SYNTHETIC_SECRET",
        ):
            isolated_env.pop(name, None)

        result = run(
            [
                POWERSHELL,
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(probe),
            ],
            cwd=self.temp_root,
            env=isolated_env,
        )

        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertNotIn(synthetic_model, result.stdout)
        self.assertNotIn(synthetic_secret, result.stdout)
        start_text = (self.project / "scripts" / "start.ps1").read_text(encoding="utf-8")
        self.assertIn('Names @("ASR_MODEL_PATH", "ASR_DEVICE", "ASR_COMPUTE_TYPE")', start_text)
        self.assertNotIn("LLM_API_KEY", start_text)
        self.assertNotIn("QQBOT", start_text)

    def test_asr_model_resolution_prefers_config_then_project_medium_and_small(self):
        common = self.project / "scripts" / "project-kei.common.ps1"
        probe = self.process_temp / "asr-model-resolution-probe.ps1"
        medium = self.project / "server" / "models" / "asr" / "medium"
        small = self.project / "server" / "models" / "asr" / "small"
        medium.mkdir(parents=True)
        small.mkdir(parents=True)
        probe.write_text(
            "\n".join(
                (
                    "$ErrorActionPreference = 'Stop'",
                    f". '{str(common).replace(chr(39), chr(39) * 2)}'",
                    "$env:ASR_MODEL_PATH = ''",
                    "$source = Resolve-KeiAsrModelPath",
                    "if ($source -ne 'project-medium') { exit 31 }",
                    "if (-not $env:ASR_MODEL_PATH.EndsWith('server\\models\\asr\\medium')) { exit 32 }",
                    "$env:ASR_MODEL_PATH = 'configured-model-token'",
                    "$source = Resolve-KeiAsrModelPath",
                    "if ($source -ne 'configured') { exit 33 }",
                    "if ($env:ASR_MODEL_PATH -ne 'configured-model-token') { exit 34 }",
                    "exit 0",
                )
            )
            + "\n",
            encoding="utf-8-sig",
        )
        isolated_env = self.env.copy()
        isolated_env.pop("ASR_MODEL_PATH", None)

        result = run(
            [
                POWERSHELL,
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(probe),
            ],
            cwd=self.temp_root,
            env=isolated_env,
        )

        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertNotIn(str(medium), result.stdout)
        shutil.rmtree(medium)
        probe.write_text(
            "\n".join(
                (
                    "$ErrorActionPreference = 'Stop'",
                    f". '{str(common).replace(chr(39), chr(39) * 2)}'",
                    "$env:ASR_MODEL_PATH = ''",
                    "$source = Resolve-KeiAsrModelPath",
                    "if ($source -ne 'project-small') { exit 35 }",
                    "if (-not $env:ASR_MODEL_PATH.EndsWith('server\\models\\asr\\small')) { exit 36 }",
                    "exit 0",
                )
            )
            + "\n",
            encoding="utf-8-sig",
        )
        result = run(
            [
                POWERSHELL,
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(probe),
            ],
            cwd=self.temp_root,
            env=isolated_env,
        )
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertNotIn(str(small), result.stdout)

    def test_lock_pip_npm_and_version_failures_are_stable(self):
        lock = self.project / "requirements" / "core-win.lock.txt"
        lock.write_text(lock.read_text(encoding="utf-8") + "# corrupt\n", encoding="utf-8")
        damaged = self.invoke_batch("setup.bat", "--profile", "core")
        self.assertEqual(damaged.returncode, 12, damaged.stdout)
        self.assertIn("lock_checksum_mismatch", damaged.stdout)

        shutil.copy2(REPO_ROOT / "requirements" / "core-win.lock.txt", lock)
        self.env["FAKE_PIP_FAIL"] = "1"
        pip_failed = self.invoke_batch("setup.bat", "--profile", "core")
        self.assertEqual(pip_failed.returncode, 13, pip_failed.stdout)
        self.assertIn("dependency_install_failed", pip_failed.stdout)
        self.env.pop("FAKE_PIP_FAIL")

        self.env["FAKE_PIP_FAIL_LOCK"] = "voice-media-win.lock.txt"
        voice_media_failed = self.invoke_batch("setup.bat", "--profile", "voice")
        self.assertEqual(voice_media_failed.returncode, 13, voice_media_failed.stdout)
        self.assertIn("voice_media_install_failed", voice_media_failed.stdout)
        self.assertIn("No source or unlocked version was used", voice_media_failed.stdout)
        self.env.pop("FAKE_PIP_FAIL_LOCK")

        self.env["FAKE_NPM_FAIL"] = "1"
        npm_failed = self.invoke_batch("setup.bat", "--profile", "qq")
        self.assertEqual(npm_failed.returncode, 14, npm_failed.stdout)
        self.assertIn("npm_ci_failed", npm_failed.stdout)

        self._write_fake_node(major=21)
        windows_root = Path(os.environ["SystemRoot"])
        self.env["PATH"] = os.pathsep.join(
            (
                str(self.fake_bin),
                str(windows_root / "System32"),
                str(windows_root / "System32" / "WindowsPowerShell" / "v1.0"),
            )
        )
        unsupported = self.invoke_batch("doctor.bat", "--profile", "qq")
        self.assertNotEqual(unsupported.returncode, 0)
        self.assertIn("Node.js 20, 22, 24, or 26", unsupported.stdout)

    def test_port_occupied_prevents_core_process_start(self):
        setup = self.invoke_batch("setup.bat", "--profile", "core")
        self.assertEqual(setup.returncode, 0, setup.stdout)
        listener = socket.socket()
        try:
            listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            listener.bind(("127.0.0.1", 8000))
            listener.listen()
        except OSError:
            listener.close()
            listener = None
        try:
            started = self.invoke_batch("start.bat", "--only", "api", "--current-window")
        finally:
            if listener is not None:
                listener.close()
        self.assertEqual(started.returncode, 22, started.stdout)
        self.assertIn("already in use", started.stdout)
        self.assertNotIn("pip install", started.stdout)

    def test_missing_and_unsupported_python_fail_without_install(self):
        windows_root = Path(os.environ["SystemRoot"])
        isolated_path = os.pathsep.join(
            (
                str(self.fake_bin),
                str(windows_root / "System32"),
                str(windows_root / "System32" / "WindowsPowerShell" / "v1.0"),
            )
        )
        self.env["PATH"] = isolated_path
        missing = self.invoke_batch("setup.bat", "--profile", "core")
        self.assertEqual(missing.returncode, 11, missing.stdout)
        self.assertIn("Python 3.10, 3.11, 3.12, or 3.13 x64", missing.stdout)

        (self.fake_bin / "python.cmd").write_text(
            "@echo off\r\necho 3.9^|64^|CPython\r\nexit /b 0\r\n",
            encoding="ascii",
        )
        unsupported = self.invoke_batch("setup.bat", "--profile", "core")
        self.assertEqual(unsupported.returncode, 11, unsupported.stdout)
        self.assertIn("Python 3.10, 3.11, 3.12, or 3.13 x64", unsupported.stdout)
        self.assertFalse((self.project / ".venv").exists())

    def test_python_probe_accepts_310_through_313_x64_only(self):
        common = self.project / "scripts" / "project-kei.common.ps1"
        common_text = common.read_text(encoding="utf-8")
        self.assertIn('"3.14"', common_text)
        self.assertIn('"-3.13-64"', common_text)

        for version, bits, expected in (
            ("3.9", "64", False),
            ("3.10", "64", True),
            ("3.11", "64", True),
            ("3.12", "64", True),
            ("3.13", "64", True),
            ("3.13", "32", False),
            ("3.14", "64", False),
        ):
            with self.subTest(version=version, bits=bits):
                fake = self.fake_bin / f"python-{version}-{bits}.cmd"
                fake.write_text(
                    f"@echo off\r\necho {version}^|{bits}^|CPython\r\nexit /b 0\r\n",
                    encoding="ascii",
                )
                escaped_common = str(common).replace("'", "''")
                escaped_fake = str(fake).replace("'", "''")
                command = (
                    f". '{escaped_common}'; "
                    f"$candidate=New-KeiPythonCandidate -Name synthetic -FilePath '{escaped_fake}'; "
                    + (
                        "if ($null -eq $candidate) { exit 1 }; "
                        f"if ($candidate.Version -ne '{version}' -or $candidate.Bits -ne 64) {{ exit 2 }}"
                        if expected
                        else "if ($null -ne $candidate) { exit 3 }"
                    )
                )
                result = run(
                    [
                        POWERSHELL,
                        "-NoProfile",
                        "-ExecutionPolicy",
                        "Bypass",
                        "-Command",
                        command,
                    ],
                    cwd=self.temp_root,
                    env=self.env,
                )
                self.assertEqual(result.returncode, 0, result.stdout)

    def test_unknown_profiles_fail_before_side_effects(self):
        before = tree_state(self.project)
        for launcher, profile in (
            ("setup.bat", "unknown"),
            ("doctor.bat", "unknown"),
            ("start.bat", "full"),
        ):
            result = self.invoke_batch(launcher, "--profile", profile)
            self.assertEqual(result.returncode, 2, result.stdout)
            self.assertIn("arguments", result.stdout)
        self.assertEqual(before, tree_state(self.project))

    def test_runtime_scripts_have_no_developer_absolute_paths(self):
        self._assert_runtime_scan_rejects_protected_strings_before_io()
        offenders = []
        tracked_result = subprocess.run(
            ["git", "ls-files", "-z"],
            cwd=REPO_ROOT,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            check=False,
        )
        if tracked_result.returncode == 0:
            relative_names = {
                value.decode("utf-8")
                for value in tracked_result.stdout.split(b"\0")
                if value
            }
        else:
            relative_names = set()
        relative_names.update(INSTALL_SURFACE_FILES)

        guard = RuntimePathScanTripwire(REPO_ROOT)
        for relative_name in sorted(relative_names, key=str.casefold):
            text = guard.read_candidate(relative_name)
            if text is None:
                continue
            lowered = text.lower()
            if "c:\\users\\11201" in lowered or "e:\\cyber girlfriend" in lowered:
                offenders.append(relative_name)
        print(
            "[PK-020] runtime_scan_tripwire "
            f"protected_rejected={len(guard.protected_rejections)} "
            f"allowed_io_calls={guard.io_calls}"
        )
        self.assertEqual(offenders, [])

    def test_lock_files_are_exact_and_free_of_local_artifacts(self):
        manifest = json.loads(
            (REPO_ROOT / "requirements" / "lock-manifest.json").read_text(encoding="utf-8")
        )
        forbidden = ("file://", "-e ", "--editable", "localhost", "cuda==", "nvidia-")
        for name, expected in manifest["files"].items():
            data = (REPO_ROOT / "requirements" / name).read_bytes()
            self.assertEqual(hashlib.sha256(data).hexdigest(), expected)
            text = data.decode("utf-8").lower()
            self.assertFalse(any(value in text for value in forbidden), name)
            for line in text.splitlines():
                stripped = line.strip()
                if stripped and not stripped.startswith("#"):
                    if name == "voice-media-win.lock.txt" and stripped.startswith("--hash="):
                        self.assertRegex(stripped, r"^--hash=sha256:[0-9a-f]{64}$")
                    else:
                        self.assertIn("==", stripped, f"{name}: {line}")

        for lock_name in manifest["files"]:
            header = (
                REPO_ROOT / "requirements" / lock_name
            ).read_text(encoding="utf-8").splitlines()[:3]
            self.assertTrue(
                any(">=3.10,<3.14" in line for line in header),
                lock_name,
            )

        voice_media = (
            REPO_ROOT / "requirements" / "voice-media-win.lock.txt"
        ).read_text(encoding="utf-8")
        expected_voice_hashes = {
            "3.10": "6f4533e320239c0599ef272654f230020442d94273be457f136ce8c48b4aa808",
            "3.11": "3afcebce1dd18130d352a2d669a8b16977c36b789d5f708c379959a08b05a3f5",
            "3.12": "b9bb030589150e0d91f8148971eebf6f9211e6839af64dd39b26b9802be242b0",
            "3.13": "450dc26c71e9fd3cbdc694319d5fb24aae50d20321c9e29982d358aafbee628c",
        }
        expected_cffi_hashes = {
            "3.10": "0f048dcf80db46f0098ccac01132761580d28e28bc0f78ae0d58048063317e15",
            "3.11": "caaf0640ef5f5517f49bc275eca1406b0ffa6aa184892812030f04c2abf589a0",
            "3.12": "51392eae71afec0d0c8fb1a53b204dbb3bcabcb3c9b807eedf3e1e6ccf2de903",
            "3.13": "f6a16c31041f09ead72d69f583767292f750d24913dadacf5756b966aacb3f1a",
        }
        self.assertEqual(voice_media.count("silk-python==0.2.8"), 4)
        self.assertEqual(voice_media.count("cffi==1.17.1"), 4)
        self.assertEqual(voice_media.count("pycparser==2.22"), 1)
        for version, wheel_hash in expected_voice_hashes.items():
            self.assertIn(f'python_version == "{version}"', voice_media)
            self.assertIn(f"--hash=sha256:{wheel_hash}", voice_media)
        for wheel_hash in expected_cffi_hashes.values():
            self.assertIn(f"--hash=sha256:{wheel_hash}", voice_media)
        self.assertIn(
            "--hash=sha256:c3702b6d3dd8c7abc1afa565d7e63d53a1d0bd86cdc24edd75470f4de499cfcc",
            voice_media,
        )
        self.assertNotIn("win32", voice_media.lower())
        self.assertNotIn("arm64", voice_media.lower())

        asr_lines = set(
            (REPO_ROOT / "requirements" / "asr-win.lock.txt")
            .read_text(encoding="utf-8")
            .splitlines()
        )
        for compatible_pin in (
            "av==14.0.0",
            "ctranslate2==4.6.0",
            "faster-whisper==1.1.1",
            "numpy==2.1.3",
            "onnxruntime==1.20.1",
            "pyreadline3==3.5.6",
            "setuptools==75.2.0",
        ):
            self.assertIn(compatible_pin, asr_lines)
        self.assertIn(
            "setuptools==75.2.0",
            (REPO_ROOT / "requirements" / "asr.in").read_text(encoding="utf-8"),
        )

        dev_lines = {
            line.strip()
            for line in (
                REPO_ROOT / "requirements" / "dev-win.lock.txt"
            ).read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.lstrip().startswith("#")
        }
        conditional = {line for line in dev_lines if ";" in line}
        self.assertEqual(
            conditional,
            {
                'exceptiongroup==1.2.2; python_version < "3.11"',
                'tomli==2.0.2; python_version < "3.11"',
            },
        )
        unconditional_count = len(dev_lines - conditional)
        for version, expected_count in (
            ((3, 10), unconditional_count + 2),
            ((3, 11), unconditional_count),
            ((3, 12), unconditional_count),
            ((3, 13), unconditional_count),
        ):
            active_count = unconditional_count + (2 if version < (3, 11) else 0)
            self.assertEqual(expected_count, active_count)

    def test_active_documentation_has_portable_install_commands(self):
        documents = (
            REPO_ROOT / "README.md",
            REPO_ROOT / "AGENTS.md",
            REPO_ROOT / "PROJECT_MIGRATION_GUIDE.md",
            REPO_ROOT / "docs" / "asr-setup.md",
            REPO_ROOT / "docs" / "architecture" / "windows-install.md",
            REPO_ROOT / "server" / "qq_bridge" / "README.md",
            REPO_ROOT / "server" / "features" / "focus" / "README.md",
            REPO_ROOT / "server" / "CONTROL_DASHBOARD.md",
        )
        for path in documents:
            text = path.read_text(encoding="utf-8")
            lowered = text.lower()
            self.assertNotIn("c:\\users\\11201", lowered, str(path))
            self.assertNotIn("e:\\cyber girlfriend", lowered, str(path))
            self.assertNotIn("npm.cmd install", lowered, str(path))
            if path.name != "windows-install.md":
                self.assertNotIn(".venv-asr\\scripts\\python", lowered, str(path))

    def test_powershell_ast_and_batch_delegation(self):
        ps_files = list((REPO_ROOT / "scripts").glob("*.ps1")) + list(
            (REPO_ROOT / "server" / "scripts").glob("start_*.ps1")
        )
        quoted = ",".join("'" + str(path).replace("'", "''") + "'" for path in ps_files)
        command = (
            f"$failed=0; @({quoted}) | % {{ $t=$null; $e=$null; "
            "[void][Management.Automation.Language.Parser]::ParseFile($_,[ref]$t,[ref]$e); "
            "if($e){$failed++} }; exit $failed"
        )
        parsed = run([POWERSHELL, "-NoProfile", "-Command", command], cwd=REPO_ROOT, env=os.environ.copy())
        self.assertEqual(parsed.returncode, 0, parsed.stdout)
        for path in (
            REPO_ROOT / "setup.bat",
            REPO_ROOT / "doctor.bat",
            REPO_ROOT / "start.bat",
            REPO_ROOT / "voice-pack.bat",
            REPO_ROOT / "voice-pack-build.bat",
            *sorted((REPO_ROOT / "server").glob("start_*.bat")),
            REPO_ROOT / "server" / "qq_bridge" / "start_qq_bridge.bat",
        ):
            text = path.read_text(encoding="utf-8")
            self.assertIn("%~dp0", text, str(path))
            self.assertNotIn("C:\\", text, str(path))

        start_text = (REPO_ROOT / "scripts" / "start.ps1").read_text(encoding="utf-8")
        self.assertIn("--no-browser", start_text)
        self.assertIn("PROJECT_KEI_NO_BROWSER", start_text)
        self.assertIn("http://127.0.0.1:8000/dashboard", start_text)
        self.assertNotIn("Start-Process -FilePath \"http://0.0.0.0", start_text)

    def test_production_core_and_asr_bind_loopback_only(self):
        controlled = (
            "scripts/start.ps1",
            "server/api.py",
            "server/services/asr_server.py",
            "server/scripts/start_api.ps1",
            "server/scripts/start_asr.ps1",
            "server/start_api.bat",
            "server/start_asr.bat",
        )
        for relative_name in controlled:
            with self.subTest(path=relative_name):
                text = (REPO_ROOT / relative_name).read_text(encoding="utf-8")
                self.assertNotIn("0.0.0.0", text)
        start_text = (REPO_ROOT / "scripts" / "start.ps1").read_text(
            encoding="utf-8"
        )
        self.assertGreaterEqual(
            start_text.count('"--host", "127.0.0.1"'),
            2,
        )
        self.assertIn("API listener on 127.0.0.1:8000", start_text)
        self.assertIn("starting 127.0.0.1:8010", start_text)

    def test_all_user_batch_launchers_pause_once_and_preserve_exit_codes(self):
        helper = REPO_ROOT / "scripts" / "project-kei.pause.cmd"
        helper_text = helper.read_text(encoding="utf-8").lower()
        self.assertIn('if not "%project_kei_no_pause%"=="1"', helper_text)
        self.assertEqual(helper_text.count("pause >nul"), 1)
        self.assertIn("exit /b %_project_kei_exit%", helper_text)

        automated_env = os.environ.copy()
        automated_env["PROJECT_KEI_NO_PAUSE"] = "1"
        for code in (0, 29):
            with self.subTest(automation_exit_code=code):
                result = run(
                    ["cmd.exe", "/d", "/c", "call", str(helper), str(code), "synthetic"],
                    cwd=REPO_ROOT,
                    env=automated_env,
                )
                self.assertEqual(result.returncode, code, result.stdout)
                self.assertNotIn("Press any key", result.stdout)

        default = run(
            [
                "cmd.exe",
                "/d",
                "/c",
                "(echo x)|call scripts\\project-kei.pause.cmd 37 synthetic_default",
            ],
            cwd=REPO_ROOT,
            env={key: value for key, value in os.environ.items() if key != "PROJECT_KEI_NO_PAUSE"},
        )
        self.assertEqual(default.returncode, 37, default.stdout)
        self.assertIn("Press any key to close this window", default.stdout)

        internal_launchers = {
            "server/start_api.bat",
            "server/start_asr.bat",
            "server/start_gptsovits.bat",
            "server/start_all_services.bat",
            "server/qq_bridge/start_qq_bridge.bat",
        }
        for relative_name in USER_BATCH_FILES:
            with self.subTest(batch=relative_name):
                text = (REPO_ROOT / relative_name).read_text(encoding="utf-8").lower()
                self.assertIn("%~dp0", text)
                self.assertIn("project-kei.pause.cmd", text)
                self.assertIn('set "_project_kei_exit=%errorlevel%"', text)
                self.assertIn("exit /b %_project_kei_exit%", text)
                self.assertIn("%*", text)
                self.assertEqual(text.count("project-kei.pause.cmd"), 1)
                self.assertLess(
                    text.index('set "_project_kei_exit=%errorlevel%"'),
                    text.index("project-kei.pause.cmd"),
                )
                self.assertLess(
                    text.index("project-kei.pause.cmd"),
                    text.index("exit /b %_project_kei_exit%"),
                )
                if relative_name in internal_launchers:
                    self.assertIn('set "project_kei_no_pause=1"', text)

        scheduler = (
            REPO_ROOT / "server" / "scripts" / "install_daily_briefing_task.ps1"
        ).read_text(encoding="utf-8")
        self.assertIn("PROJECT_KEI_NO_PAUSE=1", scheduler)


if __name__ == "__main__":
    unittest.main()
