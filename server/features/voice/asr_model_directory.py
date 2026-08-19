"""Controlled local ASR model-directory selection and validation."""
from __future__ import annotations

import json
import os
import stat
import tempfile
import threading
from pathlib import Path
from typing import Any, Callable, Optional


DirectoryPicker = Callable[[], Optional[str]]
ReplaceFunction = Callable[[str, str], None]
ResolveFunction = Callable[[Path], Path]
MAX_CONFIG_BYTES = 1024 * 1024
TOKENIZER_FILES = ("tokenizer.json", "vocabulary.json", "vocabulary.txt")


def windows_directory_picker() -> Optional[str]:
    """Open one native dialog. No browser-controlled value reaches the picker."""
    if os.name != "nt":
        return None
    root = None
    try:
        import tkinter
        from tkinter import filedialog

        root = tkinter.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        selected = filedialog.askdirectory(
            parent=root,
            title="选择 Project Kei ASR 模型目录",
            mustexist=True,
        )
        return selected or None
    finally:
        if root is not None:
            root.destroy()


def _is_reparse_point(path: Path) -> bool:
    try:
        details = path.lstat()
    except OSError:
        return True
    if stat.S_ISLNK(details.st_mode):
        return True
    attributes = getattr(details, "st_file_attributes", 0)
    marker = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    return bool(attributes & marker)


def _is_local_absolute_path(path: Path) -> bool:
    if not path.is_absolute():
        return False
    if os.name != "nt":
        return True
    drive = path.drive
    if len(drive) != 2 or drive[1] != ":" or not drive[0].isalpha():
        return False
    try:
        import ctypes

        drive_type = ctypes.windll.kernel32.GetDriveTypeW(f"{drive}\\")
        return drive_type not in {0, 1, 4}
    except Exception:
        return False


def _resolve_strict(path: Path) -> Path:
    return path.resolve(strict=True)


class AsrModelDirectoryService:
    """Validate one selected directory and atomically persist its local path."""

    def __init__(
        self,
        config_path: str | Path,
        *,
        picker: DirectoryPicker = windows_directory_picker,
        replace: ReplaceFunction = os.replace,
        reparse_checker: Callable[[Path], bool] = _is_reparse_point,
        resolve: ResolveFunction = _resolve_strict,
    ) -> None:
        self._config_path = Path(config_path)
        self._picker = picker
        self._replace = replace
        self._reparse_checker = reparse_checker
        self._resolve = resolve
        self._selection_lock = threading.Lock()

    @staticmethod
    def _safe_name(path: Path) -> str:
        name = path.name.strip()
        if not name or name in {".", ".."} or "/" in name or "\\" in name:
            return "ASR 模型目录"
        return name[:80]

    @staticmethod
    def _readable_nonempty(path: Path) -> bool:
        try:
            if not path.is_file() or path.stat().st_size <= 0:
                return False
            with path.open("rb") as handle:
                return bool(handle.read(1))
        except OSError:
            return False

    def validate(self, candidate: str | Path) -> Optional[Path]:
        """Validate only the chosen directory; never search parent directories."""
        try:
            raw = Path(candidate)
            if (
                not _is_local_absolute_path(raw)
                or any(part in {".", ".."} for part in raw.parts)
                or self._reparse_checker(raw)
            ):
                return None
            resolved = self._resolve(raw)
            if not _is_local_absolute_path(resolved) or not resolved.is_dir():
                return None
            required_names = ("model.bin", "config.json")
            tokenizer_name = next(
                (name for name in TOKENIZER_FILES if (resolved / name).is_file()),
                None,
            )
            if tokenizer_name is None:
                return None
            model_names = (*required_names, tokenizer_name)
            raw_files = tuple(raw / name for name in model_names)
            resolved_files = tuple(resolved / name for name in model_names)
            if any(
                self._reparse_checker(item)
                for item in (*raw_files, *resolved_files)
            ) or not all(self._readable_nonempty(item) for item in resolved_files):
                return None
            config_path = resolved / "config.json"
            if config_path.stat().st_size > MAX_CONFIG_BYTES:
                return None
            payload = json.loads(config_path.read_text(encoding="utf-8"))
            if not isinstance(payload, dict):
                return None
            return resolved
        except (OSError, UnicodeError, ValueError, json.JSONDecodeError):
            return None

    def configured_path(self) -> Optional[Path]:
        try:
            if not self._config_path.is_file() or self._config_path.stat().st_size > MAX_CONFIG_BYTES:
                return None
            payload = json.loads(self._config_path.read_text(encoding="utf-8"))
            if not isinstance(payload, dict) or payload.get("schema_version") != 1:
                return None
            value = payload.get("model_path")
            if not isinstance(value, str) or not value:
                return None
            return self.validate(value)
        except (OSError, UnicodeError, ValueError, json.JSONDecodeError):
            return None

    def status(self) -> dict[str, Any]:
        configured = self.configured_path()
        if configured is None:
            state = "invalid_configuration" if self._config_path.exists() else "unconfigured"
            return {
                "available": os.name == "nt" or self._picker is not windows_directory_picker,
                "configured": False,
                "state": state,
                "directory_name": None,
            }
        return {
            "available": True,
            "configured": True,
            "state": "configured",
            "directory_name": self._safe_name(configured),
        }

    def _atomic_save(self, path: Path) -> None:
        self._config_path.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=".asr-model-",
            suffix=".json.tmp",
            dir=str(self._config_path.parent),
        )
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
                json.dump(
                    {"schema_version": 1, "model_path": str(path)},
                    handle,
                    ensure_ascii=False,
                    separators=(",", ":"),
                )
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            self._replace(temporary_name, str(self._config_path))
        except BaseException:
            try:
                os.unlink(temporary_name)
            except OSError:
                pass
            raise

    def select(self) -> dict[str, Any]:
        if not self._selection_lock.acquire(blocking=False):
            return {
                "available": True,
                "configured": self.configured_path() is not None,
                "state": "selection_in_progress",
                "directory_name": None,
            }
        try:
            try:
                selected = self._picker()
            except Exception:
                return {**self.status(), "state": "picker_failed"}
            if not selected:
                return {**self.status(), "state": "cancelled"}
            validated = self.validate(selected)
            if validated is None:
                return {**self.status(), "state": "invalid_model"}
            try:
                self._atomic_save(validated)
            except Exception:
                return {**self.status(), "state": "save_failed"}
            return {
                "available": True,
                "configured": True,
                "state": "configured",
                "directory_name": self._safe_name(validated),
            }
        finally:
            self._selection_lock.release()


__all__ = ["AsrModelDirectoryService", "windows_directory_picker"]
