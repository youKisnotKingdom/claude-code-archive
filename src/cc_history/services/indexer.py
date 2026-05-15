from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
import sqlite3

from cc_history.db.connection import connect
from cc_history.schema import AiTitleEntry, CustomTitleEntry, ErrorEntry
from cc_history.services import scanner
from cc_history.services.parser import ParsedEntry, parse_jsonl_file
from cc_history.services.rendering import entry_search_text

SCHEMA_PATH = Path(__file__).parents[1] / "db" / "schema.sql"


@dataclass(frozen=True)
class IndexSummary:
    scanned_sessions: int
    indexed_sessions: int
    skipped_sessions: int


def ensure_schema(connection: sqlite3.Connection) -> None:
    existing_columns = connection.execute("PRAGMA table_info(sessions)").fetchall()
    if existing_columns:
        primary_key_columns = [
            row["name"]
            for row in sorted(existing_columns, key=lambda item: item["pk"])
            if row["pk"]
        ]
        if primary_key_columns != ["user", "project", "id"]:
            connection.execute("DROP TABLE IF EXISTS sessions")
            connection.execute("DROP TABLE IF EXISTS messages_fts")
            connection.commit()

    connection.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
    connection.commit()


def _session_is_current(connection: sqlite3.Connection, session: scanner.SessionInfo) -> bool:
    row = connection.execute(
        "SELECT source_mtime, source_size FROM sessions WHERE id = ? AND user = ? AND project = ?",
        (session.session_id, session.user, session.project),
    ).fetchone()
    if row is None:
        return False
    return row["source_mtime"] == session.mtime and row["source_size"] == session.size


def _collect_session_metadata(entries: list[ParsedEntry]) -> dict[str, str | int | None]:
    timestamps = [
        entry.timestamp
        for entry in entries
        if not isinstance(entry, ErrorEntry) and entry.timestamp is not None
    ]
    custom_title = next(
        (entry.customTitle for entry in entries if isinstance(entry, CustomTitleEntry)),
        None,
    )
    ai_title = next((entry.aiTitle for entry in entries if isinstance(entry, AiTitleEntry)), None)
    message_count = sum(
        1
        for entry in entries
        if not isinstance(entry, ErrorEntry) and entry.type in {"user", "assistant", "system"}
    )
    return {
        "first_message_at": min(timestamps) if timestamps else None,
        "last_message_at": max(timestamps) if timestamps else None,
        "message_count": message_count,
        "custom_title": custom_title,
        "ai_title": ai_title,
    }


def index_session(
    session: scanner.SessionInfo,
    connection: sqlite3.Connection | None = None,
    force: bool = False,
) -> bool:
    owns_connection = connection is None
    active_connection = connection or connect()
    ensure_schema(active_connection)

    try:
        if not force and _session_is_current(active_connection, session):
            return False

        entries = list(parse_jsonl_file(session.file_path))
        metadata = _collect_session_metadata(entries)
        indexed_at = datetime.now(UTC).isoformat()

        with active_connection:
            active_connection.execute(
                "DELETE FROM messages_fts WHERE session_id = ? AND user = ? AND project = ?",
                (session.session_id, session.user, session.project),
            )
            active_connection.execute(
                """
                INSERT INTO sessions (
                  id, user, project, project_decoded, file_path,
                  first_message_at, last_message_at, message_count,
                  custom_title, ai_title, source_mtime, source_size, indexed_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(user, project, id) DO UPDATE SET
                  project_decoded = excluded.project_decoded,
                  file_path = excluded.file_path,
                  first_message_at = excluded.first_message_at,
                  last_message_at = excluded.last_message_at,
                  message_count = excluded.message_count,
                  custom_title = excluded.custom_title,
                  ai_title = excluded.ai_title,
                  source_mtime = excluded.source_mtime,
                  source_size = excluded.source_size,
                  indexed_at = excluded.indexed_at
                """,
                (
                    session.session_id,
                    session.user,
                    session.project,
                    session.project_decoded,
                    str(session.file_path),
                    metadata["first_message_at"],
                    metadata["last_message_at"],
                    metadata["message_count"],
                    metadata["custom_title"],
                    metadata["ai_title"],
                    session.mtime,
                    session.size,
                    indexed_at,
                ),
            )

            for entry in entries:
                if isinstance(entry, ErrorEntry):
                    continue
                role, text = entry_search_text(entry)
                if not text:
                    continue
                active_connection.execute(
                    """
                    INSERT INTO messages_fts (session_id, user, project, uuid, role, text, timestamp)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        session.session_id,
                        session.user,
                        session.project,
                        entry.uuid,
                        role,
                        text,
                        entry.timestamp,
                    ),
                )

        return True
    finally:
        if owns_connection:
            active_connection.close()


def index_all_sessions(force: bool = False) -> IndexSummary:
    scanned_sessions = 0
    indexed_sessions = 0
    skipped_sessions = 0

    with connect() as connection:
        ensure_schema(connection)
        for user in scanner.list_users():
            for project in scanner.list_projects(user):
                for session in scanner.list_sessions(user, project):
                    scanned_sessions += 1
                    if index_session(session, connection, force):
                        indexed_sessions += 1
                    else:
                        skipped_sessions += 1

    return IndexSummary(
        scanned_sessions=scanned_sessions,
        indexed_sessions=indexed_sessions,
        skipped_sessions=skipped_sessions,
    )
