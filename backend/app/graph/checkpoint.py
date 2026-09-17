"""Checkpointer factory.

Same graph, two backends:

  * No ``DATABASE_URL``  -> SQLite saver (a local file, zero setup) — great for the CLI
    demo and local development.
  * ``DATABASE_URL`` set -> async Postgres saver (Supabase) — durable, production-grade
    state that survives restarts and Spot-instance evictions.

Both ``from_conn_string`` helpers are *context managers*, so callers use them with
``with`` / ``async with`` to bind the checkpointer for the lifetime of a request or run.
"""

from __future__ import annotations

import os
from contextlib import asynccontextmanager, contextmanager

from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL", "").strip()
SQLITE_PATH = os.getenv("SQLITE_PATH", "checkpoints.sqlite")


@contextmanager
def sync_checkpointer():
    """Synchronous SQLite checkpointer — used by the CLI demo."""
    from langgraph.checkpoint.sqlite import SqliteSaver

    with SqliteSaver.from_conn_string(SQLITE_PATH) as saver:
        yield saver


@asynccontextmanager
async def async_checkpointer():
    """Async checkpointer — Postgres if configured, else async SQLite.

    Used by the FastAPI server. On first use with Postgres, ``setup()`` creates the
    checkpoint tables (idempotent).
    """
    if DATABASE_URL:
        from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

        async with AsyncPostgresSaver.from_conn_string(DATABASE_URL) as saver:
            await saver.setup()
            yield saver
    else:
        from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

        async with AsyncSqliteSaver.from_conn_string(SQLITE_PATH) as saver:
            # WAL + a busy timeout reduce "database is locked" under the concurrent
            # server. SQLite is for local/dev only — set DATABASE_URL for real
            # concurrency (see README).
            try:
                await saver.conn.execute("PRAGMA journal_mode=WAL")
                await saver.conn.execute("PRAGMA busy_timeout=5000")
            except Exception:
                pass
            yield saver
