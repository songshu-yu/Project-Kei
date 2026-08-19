"""Add the server root to sys.path for direct test script execution."""
from __future__ import annotations

import os
import sys
from pathlib import Path

SERVER_ROOT = Path(__file__).resolve().parents[1]
server_root_str = str(SERVER_ROOT)
if server_root_str not in sys.path:
    sys.path.insert(0, server_root_str)

from core.env_loader import load_env_file

load_env_file(Path(os.getenv("PROJECT_KEI_ENV_FILE", str(SERVER_ROOT / ".env"))))
