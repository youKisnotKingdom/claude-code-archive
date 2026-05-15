import sqlite3
from pathlib import Path

from cc_history.config import settings


def connect(db_path: Path | None = None) -> sqlite3.Connection:
    path = db_path or settings.cache_db_path
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection
