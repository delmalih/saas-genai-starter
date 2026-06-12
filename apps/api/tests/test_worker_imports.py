import subprocess
import sys

CHECK = """
import src.worker  # the standalone entry point under test
from src.core.db import Base

tables = set(Base.metadata.tables)
required = {"organizations", "documents", "document_chunks", "chat_messages", "llm_usage"}
missing = required - tables
assert not missing, f"missing tables in registry: {missing}"
"""


def test_worker_entry_point_has_a_complete_model_registry() -> None:
    """Run in a FRESH interpreter: pytest imports every model module through
    the app, which masks registry gaps that break the worker in production
    ('could not find table organizations' on lazy FK resolution)."""
    result = subprocess.run(  # noqa: S603 — fixed argv, our own interpreter
        [sys.executable, "-c", CHECK],
        capture_output=True,
        text=True,
        env={
            "PATH": "",
            "DATABASE_URL": "postgresql+asyncpg://x:x@localhost/x",
            "REDIS_URL": "redis://localhost:6379/0",
        },
        check=False,
    )
    assert result.returncode == 0, result.stderr
