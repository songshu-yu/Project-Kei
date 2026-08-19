"""Isolated compatibility checks for the long-term memory system."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

os.environ["PROJECT_KEI_ENV_FILE"] = str(Path(tempfile.gettempdir()) / "project-kei-pk160-tests" / "missing.env")

import _path_setup  # noqa: E402,F401

from core.memory_store import MemoryStore


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="kei-memory-legacy-") as temp_dir:
        store = MemoryStore(Path(temp_dir) / "memories.json")
        command = store.parse_command("记住 我喜欢你叫我老师")
        assert command and command.action == "add"
        memory = store.add(command.content)
        assert memory.content.endswith("老师")
        assert "老师" in store.prompt_context()
        assert store.parse_command("你记得什么").action == "list"
        removed = store.delete_by_index(1)
        assert removed and "老师" in removed.content
        assert store.list() == []
        assert store.clear() == 0
    print("memory compatibility tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
