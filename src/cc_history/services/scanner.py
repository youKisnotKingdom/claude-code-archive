from dataclasses import dataclass
from pathlib import Path

from cc_history.schema import AiTitleEntry, AssistantEntry, CustomTitleEntry, ErrorEntry, UserEntry
from cc_history.schema.content import TextContent, ToolResultContent
from cc_history.config import settings
from cc_history.services.parser import parse_jsonl_file


@dataclass(frozen=True)
class SessionInfo:
    user: str
    project: str
    project_decoded: str
    session_id: str
    file_path: Path
    mtime: float
    size: int
    title: str
    first_user_text: str | None
    message_count: int
    last_message_at: str | None
    model_name: str | None
    total_tokens: int
    cwd: str | None
    git_branch: str | None


@dataclass(frozen=True)
class SessionMetadata:
    title: str
    first_user_text: str | None
    message_count: int
    last_message_at: str | None
    model_name: str | None
    total_tokens: int
    cwd: str | None
    git_branch: str | None


def _is_single_config_root() -> bool:
    return (settings.nas_root / "projects").is_dir()


def _is_safe_segment(segment: str) -> bool:
    return segment not in {"", ".", ".."} and Path(segment).name == segment


def _resolve_under(base: Path, candidate: Path) -> Path | None:
    resolved_base = base.resolve(strict=False)
    resolved_candidate = candidate.resolve(strict=False)
    if not resolved_candidate.is_relative_to(resolved_base):
        return None
    return resolved_candidate


def _projects_dir_for_user(user: str) -> Path | None:
    if _is_single_config_root():
        if user != settings.single_user_name:
            return None
        return settings.nas_root / "projects"
    if not _is_safe_segment(user):
        return None
    projects_dir = settings.nas_root / user / "claude-logs" / "projects"
    return _resolve_under(settings.nas_root, projects_dir)


def decode_project_name(encoded: str) -> str:
    """Decode Claude Code's path-like project directory name."""
    if encoded.startswith("-"):
        return "/" + encoded[1:].replace("-", "/")
    return encoded.replace("-", "/")


def list_users() -> list[str]:
    """List users that have a claude-logs/projects directory under the NAS root."""
    if _is_single_config_root():
        return [settings.single_user_name]

    if not settings.nas_root.is_dir():
        return []

    users: list[str] = []
    for entry in settings.nas_root.iterdir():
        if not entry.is_dir():
            continue
        projects = entry / "claude-logs" / "projects"
        if projects.is_dir():
            users.append(entry.name)
    return sorted(users)


def list_projects(user: str) -> list[str]:
    """List encoded project names for one user."""
    projects_dir = _projects_dir_for_user(user)
    if projects_dir is None or not projects_dir.is_dir():
        return []
    return sorted(
        project.name
        for project in projects_dir.iterdir()
        if project.is_dir() and _is_safe_segment(project.name)
    )


def _first_user_text(entry: UserEntry) -> str | None:
    if entry.isSidechain is True:
        return None
    content = entry.message.content
    if isinstance(content, str):
        return content
    if not content or all(isinstance(block, ToolResultContent) for block in content):
        return None
    first = content[0]
    if isinstance(first, str):
        return first
    if isinstance(first, TextContent):
        return first.text
    return None


def _short_title(text: str, limit: int = 96) -> str:
    normalized = " ".join(text.split())
    if len(normalized) <= limit:
        return normalized
    return normalized[: limit - 1].rstrip() + "…"


def _usage_tokens(usage: dict | None) -> int:
    if usage is None:
        return 0
    total = 0
    for key in (
        "input_tokens",
        "output_tokens",
        "cache_creation_input_tokens",
        "cache_read_input_tokens",
    ):
        value = usage.get(key)
        if isinstance(value, int):
            total += value

    cache_creation = usage.get("cache_creation")
    if isinstance(cache_creation, dict):
        for key in ("ephemeral_5m_input_tokens", "ephemeral_1h_input_tokens"):
            value = cache_creation.get(key)
            if isinstance(value, int):
                total += value
    return total


def _read_session_metadata(file_path: Path, fallback_title: str) -> SessionMetadata:
    custom_title: str | None = None
    ai_title: str | None = None
    first_user_text: str | None = None
    message_count = 0
    timestamps: list[str] = []
    model_name: str | None = None
    total_tokens = 0
    cwd: str | None = None
    git_branch: str | None = None

    for entry in parse_jsonl_file(file_path):
        if isinstance(entry, ErrorEntry):
            continue
        if entry.timestamp is not None:
            timestamps.append(entry.timestamp)
        if cwd is None and entry.cwd:
            cwd = entry.cwd
        if git_branch is None and entry.gitBranch:
            git_branch = entry.gitBranch
        if isinstance(entry, CustomTitleEntry):
            custom_title = entry.customTitle
        elif isinstance(entry, AiTitleEntry):
            ai_title = entry.aiTitle
        elif isinstance(entry, UserEntry):
            if entry.isSidechain is not True:
                message_count += 1
            if first_user_text is None:
                first_user_text = _first_user_text(entry)
        elif isinstance(entry, AssistantEntry):
            if entry.isSidechain is not True:
                message_count += 1
            if model_name is None:
                model_name = entry.message.model
            total_tokens += _usage_tokens(entry.message.usage)
        elif entry.type == "system" and entry.isSidechain is not True:
            message_count += 1

    title = custom_title or ai_title or (first_user_text and _short_title(first_user_text))
    return SessionMetadata(
        title=title or fallback_title,
        first_user_text=first_user_text,
        message_count=message_count,
        last_message_at=max(timestamps) if timestamps else None,
        model_name=model_name,
        total_tokens=total_tokens,
        cwd=cwd,
        git_branch=git_branch,
    )


def list_sessions(user: str, project: str) -> list[SessionInfo]:
    """List JSONL sessions for one encoded project, newest first."""
    projects_dir = _projects_dir_for_user(user)
    if projects_dir is None or not _is_safe_segment(project):
        return []

    project_dir = projects_dir / project
    resolved_project_dir = _resolve_under(projects_dir, project_dir)
    if resolved_project_dir is None or not resolved_project_dir.is_dir():
        return []

    sessions: list[SessionInfo] = []
    for file_path in resolved_project_dir.iterdir():
        if file_path.suffix != ".jsonl":
            continue
        stat = file_path.stat()
        metadata = _read_session_metadata(file_path, file_path.stem)
        sessions.append(
            SessionInfo(
                user=user,
                project=project,
                project_decoded=decode_project_name(project),
                session_id=file_path.stem,
                file_path=file_path,
                mtime=stat.st_mtime,
                size=stat.st_size,
                title=metadata.title,
                first_user_text=metadata.first_user_text,
                message_count=metadata.message_count,
                last_message_at=metadata.last_message_at,
                model_name=metadata.model_name,
                total_tokens=metadata.total_tokens,
                cwd=metadata.cwd,
                git_branch=metadata.git_branch,
            ),
        )
    return sorted(sessions, key=lambda session: session.mtime, reverse=True)


def get_session_path(user: str, project: str, session_id: str) -> Path | None:
    projects_dir = _projects_dir_for_user(user)
    if projects_dir is None or not _is_safe_segment(project) or not _is_safe_segment(session_id):
        return None

    project_dir = projects_dir / project
    path = project_dir / f"{session_id}.jsonl"
    resolved = _resolve_under(projects_dir, path)
    return resolved if resolved is not None and resolved.is_file() else None
