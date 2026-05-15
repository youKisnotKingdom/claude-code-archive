from dataclasses import dataclass
import sqlite3

from cc_history.db.connection import connect
from cc_history.services.indexer import ensure_schema


@dataclass(frozen=True)
class SearchResult:
    session_id: str
    user: str
    project: str
    project_decoded: str | None
    uuid: str | None
    role: str
    text: str
    timestamp: str | None
    rank: float


def _to_fts_query(query: str) -> str:
    escaped = query.strip().replace('"', '""')
    return f'"{escaped}"'


def _row_to_result(row: sqlite3.Row) -> SearchResult:
    return SearchResult(
        session_id=row["session_id"],
        user=row["user"],
        project=row["project"],
        project_decoded=row["project_decoded"],
        uuid=row["uuid"],
        role=row["role"],
        text=row["text"],
        timestamp=row["timestamp"],
        rank=row["rank"],
    )


def search_messages(query: str, user: str | None = None, limit: int = 50) -> list[SearchResult]:
    normalized_query = query.strip()
    if not normalized_query:
        return []

    with connect() as connection:
        ensure_schema(connection)
        params: list[str | int] = [_to_fts_query(normalized_query)]
        where = "messages_fts MATCH ?"
        if user:
            where += " AND messages_fts.user = ?"
            params.append(user)
        params.append(limit)

        rows = connection.execute(
            f"""
            SELECT
              messages_fts.session_id,
              messages_fts.user,
              messages_fts.project,
              sessions.project_decoded,
              messages_fts.uuid,
              messages_fts.role,
              snippet(messages_fts, 5, '<mark>', '</mark>', '...', 24) AS text,
              messages_fts.timestamp,
              bm25(messages_fts) AS rank
            FROM messages_fts
            LEFT JOIN sessions
              ON sessions.id = messages_fts.session_id
             AND sessions.user = messages_fts.user
             AND sessions.project = messages_fts.project
            WHERE {where}
            ORDER BY rank
            LIMIT ?
            """,
            params,
        ).fetchall()

    return [_row_to_result(row) for row in rows]
