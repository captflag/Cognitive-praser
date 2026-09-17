"""Test configuration.

Forces a deterministic environment BEFORE any app module is imported:
  * an isolated temp SQLite checkpoint file (no pollution of the dev DB),
  * no DATABASE_URL (so the async checkpointer stays on SQLite),
  * no GOOGLE_API_KEY (so ingestion uses the deterministic stub).
"""

from __future__ import annotations

import os
import tempfile

# Must run at import time, before app.graph.checkpoint reads these.
_TMP_DB = os.path.join(tempfile.gettempdir(), "rfq_test_checkpoints.sqlite")
for _leftover in (_TMP_DB, _TMP_DB + "-wal", _TMP_DB + "-shm"):
    try:
        os.remove(_leftover)
    except OSError:
        pass

os.environ["SQLITE_PATH"] = _TMP_DB
os.environ["DATABASE_URL"] = ""
os.environ.pop("GOOGLE_API_KEY", None)
