from dataclasses import dataclass

from cc_history.schema import ErrorEntry
from cc_history.services import scanner
from cc_history.services.parser import parse_jsonl_file


@dataclass(frozen=True)
class UserStats:
    user: str
    project_count: int
    session_count: int
    message_count: int
    total_size: int
    latest_activity: str | None


@dataclass(frozen=True)
class ProjectStats:
    user: str
    project: str
    project_decoded: str
    session_count: int
    message_count: int
    total_size: int
    latest_activity: str | None


@dataclass(frozen=True)
class OverviewStats:
    user_count: int
    project_count: int
    session_count: int
    message_count: int
    total_size: int
    latest_activity: str | None
    users: list[UserStats]


def _session_message_stats(session: scanner.SessionInfo) -> tuple[int, str | None]:
    message_count = 0
    timestamps: list[str] = []
    for entry in parse_jsonl_file(session.file_path):
        if isinstance(entry, ErrorEntry):
            continue
        if entry.type in {"user", "assistant", "system"}:
            message_count += 1
        if entry.timestamp:
            timestamps.append(entry.timestamp)
    return message_count, max(timestamps) if timestamps else None


def _latest(values: list[str | None]) -> str | None:
    present_values = [value for value in values if value is not None]
    return max(present_values) if present_values else None


def collect_project_stats(user: str, project: str) -> ProjectStats:
    sessions = scanner.list_sessions(user, project)
    message_count = 0
    latest_values: list[str | None] = []
    total_size = 0

    for session in sessions:
        session_message_count, latest_activity = _session_message_stats(session)
        message_count += session_message_count
        latest_values.append(latest_activity)
        total_size += session.size

    return ProjectStats(
        user=user,
        project=project,
        project_decoded=scanner.decode_project_name(project),
        session_count=len(sessions),
        message_count=message_count,
        total_size=total_size,
        latest_activity=_latest(latest_values),
    )


def collect_user_stats(user: str) -> UserStats:
    projects = scanner.list_projects(user)
    project_stats = [collect_project_stats(user, project) for project in projects]
    return UserStats(
        user=user,
        project_count=len(projects),
        session_count=sum(item.session_count for item in project_stats),
        message_count=sum(item.message_count for item in project_stats),
        total_size=sum(item.total_size for item in project_stats),
        latest_activity=_latest([item.latest_activity for item in project_stats]),
    )


def collect_overview_stats() -> OverviewStats:
    user_names = scanner.list_users()
    user_stats = [collect_user_stats(user) for user in user_names]
    return OverviewStats(
        user_count=len(user_stats),
        project_count=sum(item.project_count for item in user_stats),
        session_count=sum(item.session_count for item in user_stats),
        message_count=sum(item.message_count for item in user_stats),
        total_size=sum(item.total_size for item in user_stats),
        latest_activity=_latest([item.latest_activity for item in user_stats]),
        users=user_stats,
    )
