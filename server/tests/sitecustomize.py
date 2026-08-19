"""Make tests runnable as `python tests/<script>.py` from the server root."""
from __future__ import annotations

import sys
from pathlib import Path

SERVER_ROOT = Path(__file__).resolve().parents[1]
server_root_str = str(SERVER_ROOT)
if server_root_str not in sys.path:
    sys.path.insert(0, server_root_str)
