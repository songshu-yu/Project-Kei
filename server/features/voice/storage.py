"""Per-request staging and controlled publication for generated audio."""
from __future__ import annotations

import os
import shutil
import uuid
from pathlib import Path


class VoiceArtifactSession:
    def __init__(self, temp_root: Path, output_root: Path, request_id: str):
        self.temp_root = temp_root.resolve()
        self.output_root = output_root.resolve()
        self.request_id = request_id
        self.request_dir = self.temp_root / request_id
        self._published: list[Path] = []
        self._committed = False

    def __enter__(self) -> "VoiceArtifactSession":
        self.request_dir.mkdir(parents=True, exist_ok=False)
        self.output_root.mkdir(parents=True, exist_ok=True)
        return self

    def publish(self, audio: bytes, *, index: int) -> str:
        if not audio:
            raise ValueError("empty audio")
        filename = f"reply_{self.request_id}_{index:02d}_{uuid.uuid4().hex[:8]}.wav"
        staging = self.request_dir / filename
        target = self.output_root / filename
        staging.write_bytes(audio)
        os.replace(staging, target)
        self._published.append(target)
        return filename

    def commit(self) -> None:
        self._committed = True

    def cleanup(self) -> None:
        if not self._committed:
            for path in self._published:
                try:
                    path.unlink()
                except FileNotFoundError:
                    pass
        shutil.rmtree(self.request_dir, ignore_errors=True)

    def __exit__(self, _exc_type, _exc, _tb) -> None:
        self.cleanup()


class VoiceArtifactStore:
    def __init__(self, temp_root: str | Path, output_root: str | Path):
        self.temp_root = Path(temp_root)
        self.output_root = Path(output_root)

    def session(self, request_id: str) -> VoiceArtifactSession:
        return VoiceArtifactSession(self.temp_root, self.output_root, request_id)

    def resolve_audio(self, filename: str) -> Path | None:
        if Path(filename).name != filename or not filename.lower().endswith(".wav"):
            return None
        candidate = (self.output_root / filename).resolve()
        try:
            candidate.relative_to(self.output_root.resolve())
        except ValueError:
            return None
        return candidate if candidate.is_file() else None
