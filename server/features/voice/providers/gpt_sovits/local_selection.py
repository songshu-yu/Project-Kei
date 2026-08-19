"""Explicit local folder selection and atomic GPT-SoVITS registration."""

from __future__ import annotations

import json
import os
import stat
import threading
from dataclasses import dataclass
from pathlib import Path, PureWindowsPath
from typing import Any, Callable, Mapping, Optional, Union

from .acquisition import AcquisitionError, LocalEngineRegistry, validate_external_root
from .descriptor import DEFAULT_LOCAL_CONFIG_PATH, PROJECT_ROOT, EngineDescriptor, load_descriptor


FILE_ATTRIBUTE_REPARSE_POINT = 0x0400
MAX_MARKER_BYTES = 64 * 1024
DirectoryPicker = Callable[[], Optional[Union[str, Path]]]


class EngineSelectionError(RuntimeError):
    """A path-free error safe to return from the local control API."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code

    def to_public_dict(self) -> dict[str, str]:
        return {"code": self.code, "message": str(self)}


@dataclass(frozen=True)
class ValidatedExistingInstall:
    root: Path
    display_name: str
    install_status: str
    integrity_status: str


def _is_reparse_point(path: Path) -> bool:
    try:
        metadata = path.lstat()
    except OSError as exc:
        raise EngineSelectionError("install_not_ready", "所选目录缺少固定引擎入口") from exc
    attributes = int(getattr(metadata, "st_file_attributes", 0) or 0)
    return stat.S_ISLNK(metadata.st_mode) or bool(attributes & FILE_ATTRIBUTE_REPARSE_POINT)


def _path_chain(path: Path) -> tuple[Path, ...]:
    chain = []
    current = path
    while True:
        chain.append(current)
        parent = current.parent
        if parent == current:
            break
        current = parent
    chain.reverse()
    return tuple(chain)


def _reject_reparse_chain(path: Path, *, floor: Optional[Path] = None) -> None:
    chain = _path_chain(path)
    if floor is not None:
        try:
            start = chain.index(floor)
        except ValueError as exc:
            raise EngineSelectionError("install_layout_invalid", "引擎入口超出所选目录") from exc
        chain = chain[start:]
    for component in chain:
        if _is_reparse_point(component):
            raise EngineSelectionError("install_reparse_point", "所选目录不能包含重解析点")


def _safe_display_name(path: Path) -> str:
    name = path.name or PureWindowsPath(str(path)).name
    name = "".join(
        character
        for character in name
        if character.isprintable() and character not in "\\/:"
    )
    name = name.strip().strip(".")[:80]
    return name or "已登记目录"


def _marker_state(descriptor: EngineDescriptor, root: Path) -> tuple[str, str]:
    marker = root / descriptor.marker_file
    try:
        marker_metadata = marker.lstat()
    except FileNotFoundError:
        return "registered_existing", "unverified_existing_install"
    except OSError as exc:
        raise EngineSelectionError("install_marker_invalid", "引擎完整性标记无效") from exc
    if (
        _is_reparse_point(marker)
        or not marker.is_file()
        or marker_metadata.st_size <= 0
        or marker_metadata.st_size > MAX_MARKER_BYTES
    ):
        raise EngineSelectionError("install_marker_invalid", "引擎完整性标记无效")
    try:
        data = json.loads(marker.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise EngineSelectionError("install_marker_invalid", "引擎完整性标记无效") from exc
    integrity = data.get("integrity", {}) if isinstance(data, Mapping) else {}
    matches = (
        isinstance(data, Mapping)
        and data.get("engine_id") == descriptor.engine_id
        and data.get("release_identity") == descriptor.release_identity
        and data.get("distribution_revision") == descriptor.distribution_revision
        and isinstance(integrity, Mapping)
        and integrity.get("algorithm") == descriptor.integrity_algorithm
        and integrity.get("digest") == descriptor.integrity_digest
        and data.get("scripts_executed") is False
    )
    if not matches:
        raise EngineSelectionError("install_marker_invalid", "引擎完整性标记无效")
    return "installed_verified", "sha256_verified"


def validate_selected_existing_install(
    selected_root: Union[str, Path],
    descriptor: EngineDescriptor,
    *,
    project_root: Path = PROJECT_ROOT,
) -> ValidatedExistingInstall:
    """Validate only the selected root, fixed entrypoints, and fixed marker."""

    raw_root = Path(selected_root)
    if not raw_root.is_absolute():
        raise EngineSelectionError("install_root_invalid", "所选目录必须是项目外的绝对路径")
    try:
        _reject_reparse_chain(raw_root)
        root = validate_external_root(raw_root, project_root=project_root)
    except AcquisitionError as exc:
        raise EngineSelectionError(exc.code, str(exc)) from exc
    if not root.is_dir():
        raise EngineSelectionError("install_not_ready", "所选目录缺少固定引擎入口")

    for relative in descriptor.required_files:
        candidate = root.joinpath(*relative.split("/"))
        _reject_reparse_chain(candidate, floor=root)
        try:
            resolved = candidate.resolve(strict=True)
            resolved.relative_to(root)
        except (OSError, ValueError) as exc:
            raise EngineSelectionError("install_layout_invalid", "固定引擎入口无效") from exc
        if not candidate.is_file():
            raise EngineSelectionError("install_not_ready", "所选目录缺少固定引擎入口")

    install_status, integrity_status = _marker_state(descriptor, root)
    return ValidatedExistingInstall(
        root=root,
        display_name=_safe_display_name(root),
        install_status=install_status,
        integrity_status=integrity_status,
    )


def windows_directory_picker() -> Optional[Path]:
    """Open one project-owned native dialog; never enumerate or execute the selection."""

    if os.name != "nt":
        raise EngineSelectionError("picker_unavailable", "本机目录选择器仅支持 Windows")
    try:
        import tkinter
        from tkinter import filedialog

        root = tkinter.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        try:
            selected = filedialog.askdirectory(
                parent=root,
                mustexist=True,
                title="选择已有 GPT-SoVITS 引擎目录",
            )
        finally:
            root.destroy()
    except EngineSelectionError:
        raise
    except Exception as exc:
        raise EngineSelectionError("picker_unavailable", "无法打开本机目录选择器") from exc
    return Path(selected) if selected else None


class LocalEngineSelectionService:
    """Serialize explicit picker actions and commit only a validated selection."""

    def __init__(
        self,
        *,
        descriptor: Optional[EngineDescriptor] = None,
        registry: Optional[LocalEngineRegistry] = None,
        picker: DirectoryPicker = windows_directory_picker,
        project_root: Path = PROJECT_ROOT,
    ):
        self.descriptor = descriptor or load_descriptor()
        self.registry = registry or LocalEngineRegistry(DEFAULT_LOCAL_CONFIG_PATH)
        self.picker = picker
        self.project_root = project_root
        self._selection_lock = threading.Lock()

    def status(self) -> dict[str, Any]:
        picker_available = os.name == "nt" or self.picker is not windows_directory_picker
        base = {
            "engine_id": self.descriptor.engine_id,
            "registration_state": "unregistered",
            "integrity_status": "not_checked",
            "entrypoints_ready": False,
            "display_name": None,
            "selection_in_progress": self._selection_lock.locked(),
            "can_select_existing": picker_available,
        }
        try:
            data = self.registry.load()
            if data is None:
                return base
            if data.get("engine_id") != self.descriptor.engine_id:
                raise EngineSelectionError("local_config_invalid", "本机引擎登记无效")
            root_text = data.get("install_root")
            if not isinstance(root_text, str) or not root_text:
                raise EngineSelectionError("local_config_invalid", "本机引擎登记无效")
            validated = validate_selected_existing_install(
                root_text,
                self.descriptor,
                project_root=self.project_root,
            )
            base.update(
                {
                    "registration_state": validated.install_status,
                    "integrity_status": validated.integrity_status,
                    "entrypoints_ready": True,
                    "display_name": validated.display_name,
                }
            )
            return base
        except (AcquisitionError, EngineSelectionError):
            base.update(
                {
                    "registration_state": "invalid",
                    "error_code": "local_registration_invalid",
                }
            )
            return base

    def select_existing_install(self) -> dict[str, Any]:
        if not self._selection_lock.acquire(blocking=False):
            raise EngineSelectionError("selection_in_progress", "已有目录选择正在进行")
        try:
            try:
                selected = self.picker()
            except EngineSelectionError:
                raise
            except Exception as exc:
                raise EngineSelectionError("picker_unavailable", "无法打开本机目录选择器") from exc
            if selected is None or str(selected).strip() == "":
                result = self.status()
                result["action"] = "cancelled"
                result["selection_in_progress"] = False
                return result
            validated = validate_selected_existing_install(
                selected,
                self.descriptor,
                project_root=self.project_root,
            )
            try:
                self.registry.register(
                    self.descriptor,
                    validated.root,
                    api_style=self.descriptor.default_api_style,
                    install_status=validated.install_status,
                    integrity_status=validated.integrity_status,
                )
            except AcquisitionError as exc:
                raise EngineSelectionError(exc.code, str(exc)) from exc
            return {
                "action": "registered",
                "engine_id": self.descriptor.engine_id,
                "registration_state": validated.install_status,
                "integrity_status": validated.integrity_status,
                "entrypoints_ready": True,
                "display_name": validated.display_name,
                "selection_in_progress": False,
                "can_select_existing": True,
            }
        finally:
            self._selection_lock.release()


__all__ = [
    "DirectoryPicker",
    "EngineSelectionError",
    "LocalEngineSelectionService",
    "ValidatedExistingInstall",
    "validate_selected_existing_install",
    "windows_directory_picker",
]
