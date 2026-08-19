"""Audio output cleanup utilities for Project Kei."""
from __future__ import annotations

import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Optional


AUDIO_EXTENSIONS = {".wav", ".mp3", ".m4a", ".flac", ".ogg"}


@dataclass
class CleanupStats:
    scanned: int = 0
    deleted: int = 0
    freed_bytes: int = 0
    remaining_bytes: int = 0
    dry_run: bool = False

    def to_dict(self):
        return {
            "scanned": self.scanned,
            "deleted": self.deleted,
            "freed_bytes": self.freed_bytes,
            "freed_mb": round(self.freed_bytes / 1024 / 1024, 2),
            "remaining_bytes": self.remaining_bytes,
            "remaining_mb": round(self.remaining_bytes / 1024 / 1024, 2),
            "dry_run": self.dry_run,
        }


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except ValueError:
        return default


def _audio_files(paths: Iterable[Path], output_root: Path) -> List[Path]:
    files: List[Path] = []
    root = output_root.resolve()
    for directory in paths:
        if not directory.exists():
            continue
        for path in directory.rglob("*"):
            if not path.is_file() or path.suffix.lower() not in AUDIO_EXTENSIONS:
                continue
            resolved = path.resolve()
            try:
                resolved.relative_to(root)
            except ValueError:
                continue
            files.append(path)
    return files


def _delete_file(path: Path, dry_run: bool) -> int:
    try:
        size = path.stat().st_size
        if not dry_run:
            path.unlink()
        return size
    except FileNotFoundError:
        return 0
    except Exception as exc:
        print(f"[AudioCleanup] failed to delete {path}: {exc}")
        return 0


def cleanup_audio_outputs(root_dir: str | Path, dry_run: bool = False) -> CleanupStats:
    """Clean generated audio files under server/output only."""
    if not _env_bool("AUDIO_CLEANUP_ENABLED", True):
        return CleanupStats(dry_run=dry_run)

    root = Path(root_dir).resolve()
    output_root = root / "output"
    now = time.time()

    default_days = _env_float("AUDIO_RETENTION_DAYS", 3)
    voice_days = _env_float("VOICE_AUDIO_RETENTION_DAYS", default_days)
    briefing_days = _env_float("BRIEFING_AUDIO_RETENTION_DAYS", 7)
    mic_days = _env_float("MIC_TEST_RETENTION_DAYS", 1)
    max_total_mb = _env_float("AUDIO_MAX_TOTAL_MB", 500)

    targets = [
        (output_root / "voice_replies", voice_days),
        (output_root / "briefings", briefing_days),
        (output_root / "mic_tests", mic_days),
    ]

    stats = CleanupStats(dry_run=dry_run)
    all_files = _audio_files((directory for directory, _ in targets), output_root)
    stats.scanned = len(all_files)

    deleted_paths = set()
    for directory, retention_days in targets:
        cutoff = now - retention_days * 86400
        for path in _audio_files([directory], output_root):
            if path in deleted_paths:
                continue
            try:
                if path.stat().st_mtime >= cutoff:
                    continue
            except FileNotFoundError:
                continue
            freed = _delete_file(path, dry_run)
            if freed:
                deleted_paths.add(path)
                stats.deleted += 1
                stats.freed_bytes += freed

    remaining = []
    for path in _audio_files((directory for directory, _ in targets), output_root):
        if path in deleted_paths:
            continue
        try:
            stat = path.stat()
        except FileNotFoundError:
            continue
        remaining.append((path, stat.st_size, stat.st_mtime))

    max_total_bytes = int(max_total_mb * 1024 * 1024)
    total_bytes = sum(size for _, size, _ in remaining)
    if max_total_bytes > 0 and total_bytes > max_total_bytes:
        for path, size, _ in sorted(remaining, key=lambda item: item[2]):
            if total_bytes <= max_total_bytes:
                break
            freed = _delete_file(path, dry_run)
            if freed:
                stats.deleted += 1
                stats.freed_bytes += freed
                total_bytes -= size

    stats.remaining_bytes = max(0, total_bytes)
    if stats.deleted:
        mode = "would delete" if dry_run else "deleted"
        print(f"[AudioCleanup] {mode} {stats.deleted} files, freed {stats.to_dict()['freed_mb']} MB")
    return stats
