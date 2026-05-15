import json
from pathlib import Path

from cc_history.services.parser import ParsedEntry, parse_jsonl_file


def _first_line_session_id(path: Path) -> str | None:
    try:
        first_line = path.read_text(encoding="utf-8").splitlines()[0]
    except (OSError, IndexError):
        return None

    try:
        data = json.loads(first_line)
    except json.JSONDecodeError:
        return None

    if not isinstance(data, dict):
        return None
    session_id = data.get("sessionId")
    return session_id if isinstance(session_id, str) else None


def _agent_id_from_filename(path: Path) -> str | None:
    name = path.name
    if not name.startswith("agent-") or not name.endswith(".jsonl"):
        return None
    agent_id = name[len("agent-") : -len(".jsonl")]
    return agent_id or None


def discover_agent_session_files(project_dir: Path, session_id: str) -> dict[str, Path]:
    agent_files: dict[str, Path] = {}

    subagents_dir = project_dir / session_id / "subagents"
    if subagents_dir.is_dir():
        for path in sorted(subagents_dir.glob("agent-*.jsonl")):
            agent_id = _agent_id_from_filename(path)
            if agent_id is not None and _first_line_session_id(path) is not None:
                agent_files[agent_id] = path

    for path in sorted(project_dir.glob("agent-*.jsonl")):
        agent_id = _agent_id_from_filename(path)
        if agent_id is not None and _first_line_session_id(path) == session_id:
            agent_files.setdefault(agent_id, path)

    return agent_files


def load_agent_sessions(project_dir: Path, session_id: str) -> dict[str, list[ParsedEntry]]:
    sessions: dict[str, list[ParsedEntry]] = {}
    for agent_id, path in discover_agent_session_files(project_dir, session_id).items():
        sessions[agent_id] = list(parse_jsonl_file(path))
    return sessions
