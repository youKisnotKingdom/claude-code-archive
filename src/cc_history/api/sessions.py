from fastapi import APIRouter, HTTPException

from cc_history.services import scanner
from cc_history.services.parser import ParsedEntry, parse_jsonl_file

router = APIRouter()


def serialize_session(session: scanner.SessionInfo) -> dict[str, str | float | int]:
    return {
        "user": session.user,
        "project": session.project,
        "project_decoded": session.project_decoded,
        "session_id": session.session_id,
        "file_path": str(session.file_path),
        "mtime": session.mtime,
        "size": session.size,
        "title": session.title,
        "first_user_text": session.first_user_text or "",
        "message_count": session.message_count,
        "last_message_at": session.last_message_at or "",
        "model_name": session.model_name or "",
        "total_tokens": session.total_tokens,
        "cwd": session.cwd or "",
        "git_branch": session.git_branch or "",
    }


def serialize_entry(entry: ParsedEntry) -> dict:
    return entry.model_dump(mode="json")


@router.get("/users/{user}/projects/{project}/sessions")
def get_sessions(user: str, project: str) -> dict[str, list[dict[str, str | float | int]]]:
    sessions = [serialize_session(session) for session in scanner.list_sessions(user, project)]
    return {"sessions": sessions}


@router.get("/users/{user}/projects/{project}/sessions/{session_id}")
def get_session_entries(user: str, project: str, session_id: str) -> dict[str, list[dict]]:
    path = scanner.get_session_path(user, project, session_id)
    if path is None:
        raise HTTPException(status_code=404, detail="Session not found")

    entries = [serialize_entry(entry) for entry in parse_jsonl_file(path)]
    return {"entries": entries}
