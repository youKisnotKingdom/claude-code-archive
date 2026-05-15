from dataclasses import dataclass
from datetime import UTC, datetime

from cc_history.config import settings
from cc_history.db.connection import connect
from cc_history.schema import AssistantEntry, ErrorEntry, UserEntry
from cc_history.schema.content import TextContent, ToolResultContent, ToolUseContent
from cc_history.services.indexer import ensure_schema
from cc_history.services.parser import parse_jsonl_file
from cc_history.services import scanner

REVIEW_STATUSES = ("unreviewed", "candidate", "reviewed", "ignored")
KNOWLEDGE_SCOPES = ("unset", "private", "user", "project", "org")


@dataclass(frozen=True)
class SessionAnnotation:
    user: str
    project: str
    session_id: str
    manual_title: str | None
    note: str
    is_favorite: bool
    is_archived: bool
    review_status: str
    knowledge_scope: str
    updated_at: str | None
    tags: list[str]


@dataclass(frozen=True)
class AutoLabelSummary:
    scanned_sessions: int
    labeled_sessions: int
    created_annotations: int
    inserted_labels: int


def empty_session_annotation(user: str, project: str, session_id: str) -> SessionAnnotation:
    return SessionAnnotation(
        user=user,
        project=project,
        session_id=session_id,
        manual_title=None,
        note="",
        is_favorite=False,
        is_archived=False,
        review_status="unreviewed",
        knowledge_scope="unset",
        updated_at=None,
        tags=[],
    )


def parse_tag_text(value: str) -> list[str]:
    tags: list[str] = []
    seen: set[str] = set()
    for raw_tag in value.replace("\n", ",").split(","):
        tag = " ".join(raw_tag.strip().lower().split())
        if not tag or tag in seen:
            continue
        tags.append(tag)
        seen.add(tag)
    return tags


def _clean_optional_text(value: str) -> str | None:
    cleaned = value.strip()
    return cleaned or None


def _clean_text(value: str) -> str:
    return value.strip()


def _valid_review_status(value: str) -> str:
    return value if value in REVIEW_STATUSES else "unreviewed"


def _valid_knowledge_scope(value: str) -> str:
    return value if value in KNOWLEDGE_SCOPES else "unset"


def _append_label(labels: list[str], label: str) -> None:
    if label not in labels:
        labels.append(label)


def _text_mentions_any(text: str, terms: tuple[str, ...]) -> bool:
    normalized = text.lower()
    return any(term in normalized for term in terms)


def _content_text(content: object) -> str:
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return ""

    texts: list[str] = []
    for block in content:
        if isinstance(block, str):
            texts.append(block)
        elif isinstance(block, TextContent):
            texts.append(block.text)
        elif isinstance(block, ToolResultContent):
            if isinstance(block.content, str):
                texts.append(block.content)
            elif isinstance(block.content, list):
                for child in block.content:
                    if isinstance(child, TextContent):
                        texts.append(child.text)
    return "\n".join(texts)


def _append_text_labels(labels: list[str], text: str) -> None:
    if _text_mentions_any(
        text, ("fix", "bug", "error", "fail", "exception", "修正", "バグ", "エラー")
    ):
        _append_label(labels, "debugging")
    if _text_mentions_any(text, ("test", "pytest", "vitest", "テスト")):
        _append_label(labels, "testing")
    if _text_mentions_any(text, ("doc", "docs", "readme", "documentation", "ドキュメント")):
        _append_label(labels, "docs")
    if _text_mentions_any(text, ("refactor", "cleanup", "整理", "リファクタ")):
        _append_label(labels, "refactor")


def _append_tool_labels(labels: list[str], tool: ToolUseContent) -> None:
    _append_label(labels, "uses-tools")
    if tool.name == "Bash":
        _append_label(labels, "uses-bash")
        command = tool.input.get("command")
        if isinstance(command, str):
            _append_text_labels(labels, command)
        return
    if tool.name in {"Write", "Edit", "MultiEdit", "NotebookEdit"}:
        _append_label(labels, "file-edit")
        return
    if tool.name == "Read":
        _append_label(labels, "file-read")
        return
    if tool.name in {"Grep", "Glob", "LS"}:
        _append_label(labels, "search")
        return
    if tool.name == "TodoWrite":
        _append_label(labels, "todo")
        return
    if tool.name in {"Task", "Agent"}:
        _append_label(labels, "subagent")


def derive_auto_labels(session: scanner.SessionInfo) -> list[str]:
    labels: list[str] = []

    if session.message_count >= 40:
        _append_label(labels, "long-session")
    elif session.message_count <= 3:
        _append_label(labels, "short-session")

    if session.git_branch:
        _append_label(labels, "has-git-branch")

    for entry in parse_jsonl_file(session.file_path):
        if isinstance(entry, ErrorEntry):
            _append_label(labels, "parse-error")
            continue
        if isinstance(entry, UserEntry):
            _append_text_labels(labels, _content_text(entry.message.content))
            content = entry.message.content
            if isinstance(content, list):
                for block in content:
                    if isinstance(block, ToolResultContent) and block.is_error is True:
                        _append_label(labels, "tool-error")
        elif isinstance(entry, AssistantEntry):
            if entry.isApiErrorMessage is True:
                _append_label(labels, "api-error")
            content = entry.message.content
            if isinstance(content, list):
                for block in content:
                    if isinstance(block, ToolUseContent):
                        _append_tool_labels(labels, block)
                    elif isinstance(block, TextContent):
                        _append_text_labels(labels, block.text)

    if not labels:
        labels.append("general")
    return labels


def _tags_for_session(user: str, project: str, session_id: str) -> list[str]:
    with connect(settings.cache_db_path) as connection:
        ensure_schema(connection)
        rows = connection.execute(
            """
            SELECT tag
            FROM session_tags
            WHERE user = ? AND project = ? AND session_id = ?
            ORDER BY rowid
            """,
            (user, project, session_id),
        ).fetchall()
    return [row["tag"] for row in rows]


def get_session_annotation(user: str, project: str, session_id: str) -> SessionAnnotation:
    with connect(settings.cache_db_path) as connection:
        ensure_schema(connection)
        row = connection.execute(
            """
            SELECT *
            FROM session_annotations
            WHERE user = ? AND project = ? AND session_id = ?
            """,
            (user, project, session_id),
        ).fetchone()
        tag_rows = connection.execute(
            """
            SELECT tag
            FROM session_tags
            WHERE user = ? AND project = ? AND session_id = ?
            ORDER BY rowid
            """,
            (user, project, session_id),
        ).fetchall()

    if row is None:
        return empty_session_annotation(user, project, session_id)

    return SessionAnnotation(
        user=user,
        project=project,
        session_id=session_id,
        manual_title=row["manual_title"],
        note=row["note"],
        is_favorite=bool(row["is_favorite"]),
        is_archived=bool(row["is_archived"]),
        review_status=row["review_status"],
        knowledge_scope=row["knowledge_scope"],
        updated_at=row["updated_at"],
        tags=[tag_row["tag"] for tag_row in tag_rows],
    )


def list_project_annotations(user: str, project: str) -> dict[str, SessionAnnotation]:
    with connect(settings.cache_db_path) as connection:
        ensure_schema(connection)
        rows = connection.execute(
            """
            SELECT *
            FROM session_annotations
            WHERE user = ? AND project = ?
            ORDER BY updated_at DESC
            """,
            (user, project),
        ).fetchall()
        tag_rows = connection.execute(
            """
            SELECT session_id, tag
            FROM session_tags
            WHERE user = ? AND project = ?
            ORDER BY session_id, rowid
            """,
            (user, project),
        ).fetchall()

    tags_by_session: dict[str, list[str]] = {}
    for tag_row in tag_rows:
        tags_by_session.setdefault(tag_row["session_id"], []).append(tag_row["tag"])

    annotations: dict[str, SessionAnnotation] = {}
    for row in rows:
        session_id = row["session_id"]
        annotations[session_id] = SessionAnnotation(
            user=user,
            project=project,
            session_id=session_id,
            manual_title=row["manual_title"],
            note=row["note"],
            is_favorite=bool(row["is_favorite"]),
            is_archived=bool(row["is_archived"]),
            review_status=row["review_status"],
            knowledge_scope=row["knowledge_scope"],
            updated_at=row["updated_at"],
            tags=tags_by_session.get(session_id, []),
        )
    return annotations


def save_session_annotation(
    user: str,
    project: str,
    session_id: str,
    manual_title: str,
    note: str,
    is_favorite: bool,
    is_archived: bool,
    review_status: str,
    knowledge_scope: str,
    tags: list[str],
) -> SessionAnnotation:
    updated_at = datetime.now(UTC).isoformat()
    cleaned_title = _clean_optional_text(manual_title)
    cleaned_note = _clean_text(note)
    cleaned_review_status = _valid_review_status(review_status)
    cleaned_knowledge_scope = _valid_knowledge_scope(knowledge_scope)
    cleaned_tags = parse_tag_text(",".join(tags))

    with connect(settings.cache_db_path) as connection:
        ensure_schema(connection)
        with connection:
            connection.execute(
                """
                INSERT INTO session_annotations (
                  user, project, session_id, manual_title, note,
                  is_favorite, is_archived, review_status, knowledge_scope, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(user, project, session_id) DO UPDATE SET
                  manual_title = excluded.manual_title,
                  note = excluded.note,
                  is_favorite = excluded.is_favorite,
                  is_archived = excluded.is_archived,
                  review_status = excluded.review_status,
                  knowledge_scope = excluded.knowledge_scope,
                  updated_at = excluded.updated_at
                """,
                (
                    user,
                    project,
                    session_id,
                    cleaned_title,
                    cleaned_note,
                    int(is_favorite),
                    int(is_archived),
                    cleaned_review_status,
                    cleaned_knowledge_scope,
                    updated_at,
                ),
            )
            connection.execute(
                """
                DELETE FROM session_tags
                WHERE user = ? AND project = ? AND session_id = ? AND source = 'manual'
                """,
                (user, project, session_id),
            )
            for tag in cleaned_tags:
                connection.execute(
                    """
                    INSERT OR IGNORE INTO session_tags (
                      user, project, session_id, tag, source, category, created_at
                    )
                    VALUES (?, ?, ?, ?, 'manual', 'topic', ?)
                    """,
                    (user, project, session_id, tag, updated_at),
                )

    return get_session_annotation(user, project, session_id)


def _project_keys(user: str | None, project: str | None) -> list[tuple[str, str]]:
    if user and project:
        return [(user, project)] if project in scanner.list_projects(user) else []
    if user:
        return [(user, project_name) for project_name in scanner.list_projects(user)]

    keys: list[tuple[str, str]] = []
    for user_name in scanner.list_users():
        keys.extend((user_name, project_name) for project_name in scanner.list_projects(user_name))
    return keys


def backfill_auto_labels(
    user: str | None = None,
    project: str | None = None,
) -> AutoLabelSummary:
    scanned_sessions = 0
    labeled_sessions = 0
    created_annotations = 0
    inserted_labels = 0
    updated_at = datetime.now(UTC).isoformat()

    with connect(settings.cache_db_path) as connection:
        ensure_schema(connection)
        for user_name, project_name in _project_keys(user, project):
            existing_annotations = list_project_annotations(user_name, project_name)
            for session in scanner.list_sessions(user_name, project_name):
                scanned_sessions += 1
                labels = derive_auto_labels(session)
                with connection:
                    if session.session_id not in existing_annotations:
                        created_annotations += 1
                        connection.execute(
                            """
                            INSERT INTO session_annotations (
                              user, project, session_id, manual_title, note,
                              is_favorite, is_archived, review_status, knowledge_scope, updated_at
                            )
                            VALUES (?, ?, ?, NULL, '', 0, 0, 'unreviewed', 'unset', ?)
                            """,
                            (user_name, project_name, session.session_id, updated_at),
                        )
                    connection.execute(
                        """
                        DELETE FROM session_tags
                        WHERE user = ? AND project = ? AND session_id = ? AND source = 'auto'
                        """,
                        (user_name, project_name, session.session_id),
                    )
                    for label in labels:
                        cursor = connection.execute(
                            """
                            INSERT OR IGNORE INTO session_tags (
                              user, project, session_id, tag, source, category, created_at
                            )
                            VALUES (?, ?, ?, ?, 'auto', 'signal', ?)
                            """,
                            (user_name, project_name, session.session_id, label, updated_at),
                        )
                        inserted_labels += cursor.rowcount
                labeled_sessions += 1

    return AutoLabelSummary(
        scanned_sessions=scanned_sessions,
        labeled_sessions=labeled_sessions,
        created_annotations=created_annotations,
        inserted_labels=inserted_labels,
    )
