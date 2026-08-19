"""Fixed, read-only probes for declarative module runtime requirements."""

from __future__ import annotations

import re
import shutil
import subprocess
from typing import Callable, Dict, Iterable, Optional, Tuple

from .manifest import RuntimeRequirement


RuntimeProbe = Callable[[str], Optional[Tuple[str, str]]]
_VERSION = re.compile(r"^v?(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)(?:[-+][0-9A-Za-z.-]+)?$")


def probe_host_runtime(runtime_id: str) -> Optional[Tuple[str, str]]:
    """Probe one Core-approved runtime without accepting paths or commands."""

    if runtime_id != "node":
        return None
    executable = shutil.which("node.exe") or shutil.which("node")
    if not executable:
        return None
    try:
        version = subprocess.run(
            [executable, "--version"],
            check=True,
            capture_output=True,
            text=True,
            timeout=3,
        ).stdout.strip().lstrip("v")
        architecture = subprocess.run(
            [executable, "-p", "process.arch"],
            check=True,
            capture_output=True,
            text=True,
            timeout=3,
        ).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return None
    if not _VERSION.fullmatch(version) or architecture not in {"x64"}:
        return (version if _VERSION.fullmatch(version) else "unknown", architecture or "unknown")
    return version, architecture


def check_runtime_requirements(
    requirements: Iterable[RuntimeRequirement],
    probe: RuntimeProbe = probe_host_runtime,
) -> Dict[str, object]:
    checks = []
    for requirement in requirements:
        detected = None
        try:
            detected = probe(requirement.id)
        except Exception:
            detected = None
        if detected is None:
            status = "missing"
            version = None
            architecture = None
        else:
            version, architecture = detected
            match = _VERSION.fullmatch(version)
            major = int(match.group(1)) if match else None
            if architecture != requirement.architecture:
                status = "architecture_unsupported"
            elif major not in requirement.supported_major_versions:
                status = "version_unsupported"
            else:
                status = "ready"
        checks.append({
            "id": requirement.id,
            "status": status,
            "detected_version": version,
            "detected_architecture": architecture,
            "supported_major_versions": list(requirement.supported_major_versions),
            "required_architecture": requirement.architecture,
        })
    return {
        "ready": all(check["status"] == "ready" for check in checks),
        "checks": checks,
    }


__all__ = ["RuntimeProbe", "check_runtime_requirements", "probe_host_runtime"]
