from dataclasses import dataclass
from datetime import UTC, datetime

from cc_history.services import annotations
from cc_history.services import scanner

DEFAULT_STATUSES = ("candidate", "reviewed")
DEFAULT_SCOPES = ("project", "org")


@dataclass(frozen=True)
class AgentContextSource:
    user: str
    project: str
    project_decoded: str
    session_id: str
    title: str
    note: str
    tags: list[str]
    review_status: str
    knowledge_scope: str
    is_favorite: bool
    last_message_at: str | None
    url: str


@dataclass(frozen=True)
class AgentContextPack:
    title: str
    user: str | None
    project: str | None
    project_decoded: str | None
    generated_at: str
    statuses: list[str]
    scopes: list[str]
    include_archived: bool
    sources: list[AgentContextSource]
    markdown: str

    @property
    def source_count(self) -> int:
        return len(self.sources)


def _normalize_filter(values: list[str] | None, defaults: tuple[str, ...]) -> list[str]:
    if values is None:
        return list(defaults)
    cleaned = [value for value in values if value]
    return cleaned or list(defaults)


def _project_keys(user: str | None, project: str | None) -> list[tuple[str, str]]:
    if user and project:
        return [(user, project)] if project in scanner.list_projects(user) else []
    if user:
        return [(user, project_name) for project_name in scanner.list_projects(user)]

    keys: list[tuple[str, str]] = []
    for user_name in scanner.list_users():
        keys.extend((user_name, project_name) for project_name in scanner.list_projects(user_name))
    return keys


def _source_sort_key(source: AgentContextSource) -> tuple[int, str, str, str]:
    favorite_rank = 0 if source.is_favorite else 1
    last_message_at = source.last_message_at or ""
    return (favorite_rank, source.user, source.project, last_message_at)


def _context_sources(
    user: str | None,
    project: str | None,
    statuses: list[str],
    scopes: list[str],
    include_archived: bool,
) -> list[AgentContextSource]:
    sources: list[AgentContextSource] = []
    for user_name, project_name in _project_keys(user, project):
        project_annotations = annotations.list_project_annotations(user_name, project_name)
        sessions = {
            session.session_id: session
            for session in scanner.list_sessions(user_name, project_name)
        }
        for session_id, annotation in project_annotations.items():
            if not include_archived and annotation.is_archived:
                continue
            if annotation.review_status not in statuses:
                continue
            if annotation.knowledge_scope not in scopes:
                continue
            session = sessions.get(session_id)
            if session is None:
                continue
            title = annotation.manual_title or session.title
            sources.append(
                AgentContextSource(
                    user=user_name,
                    project=project_name,
                    project_decoded=session.project_decoded,
                    session_id=session_id,
                    title=title,
                    note=annotation.note,
                    tags=annotation.tags,
                    review_status=annotation.review_status,
                    knowledge_scope=annotation.knowledge_scope,
                    is_favorite=annotation.is_favorite,
                    last_message_at=session.last_message_at,
                    url=f"/users/{user_name}/projects/{project_name}/sessions/{session_id}",
                ),
            )

    return sorted(sources, key=_source_sort_key)


def _markdown_list_item(label: str, value: str | None) -> str:
    return f"- {label}: {value or '-'}"


def _render_markdown(pack: AgentContextPack) -> str:
    lines = [
        f"# Agent Context: {pack.title}",
        "",
        "## Scope",
        "",
        _markdown_list_item("User", pack.user),
        _markdown_list_item("Project", pack.project_decoded or pack.project),
        _markdown_list_item("Generated", pack.generated_at),
        _markdown_list_item("Review statuses", ", ".join(pack.statuses)),
        _markdown_list_item("Knowledge scopes", ", ".join(pack.scopes)),
        _markdown_list_item(
            "Archived sessions", "included" if pack.include_archived else "excluded"
        ),
        "",
        "## Selected Knowledge",
        "",
    ]

    if not pack.sources:
        lines.extend(
            [
                "No reviewed context sources match the selected filters.",
                "",
                "Use session notes, tags, review status, and scope to promote useful sessions.",
            ],
        )
        return "\n".join(lines)

    for source in pack.sources:
        lines.extend(
            [
                f"### {source.title}",
                "",
                _markdown_list_item("Source", source.url),
                _markdown_list_item("User", source.user),
                _markdown_list_item("Project", source.project_decoded),
                _markdown_list_item("Status", source.review_status),
                _markdown_list_item("Scope", source.knowledge_scope),
                _markdown_list_item("Tags", ", ".join(source.tags)),
                "",
            ],
        )
        if source.note:
            lines.extend([source.note, ""])

    lines.extend(
        [
            "## Open Questions",
            "",
            "- Review whether these notes should become durable project rules.",
            "- Confirm that no private data is included before sharing this context.",
        ],
    )
    return "\n".join(lines)


def build_agent_context_pack(
    user: str | None = None,
    project: str | None = None,
    statuses: list[str] | None = None,
    scopes: list[str] | None = None,
    include_archived: bool = False,
) -> AgentContextPack:
    selected_statuses = _normalize_filter(statuses, DEFAULT_STATUSES)
    selected_scopes = _normalize_filter(scopes, DEFAULT_SCOPES)
    generated_at = datetime.now(UTC).isoformat()
    project_decoded = scanner.decode_project_name(project) if project else None
    title = project_decoded or user or "All Projects"
    sources = _context_sources(
        user=user,
        project=project,
        statuses=selected_statuses,
        scopes=selected_scopes,
        include_archived=include_archived,
    )
    pack = AgentContextPack(
        title=title,
        user=user,
        project=project,
        project_decoded=project_decoded,
        generated_at=generated_at,
        statuses=selected_statuses,
        scopes=selected_scopes,
        include_archived=include_archived,
        sources=sources,
        markdown="",
    )
    return AgentContextPack(
        title=pack.title,
        user=pack.user,
        project=pack.project,
        project_decoded=pack.project_decoded,
        generated_at=pack.generated_at,
        statuses=pack.statuses,
        scopes=pack.scopes,
        include_archived=pack.include_archived,
        sources=pack.sources,
        markdown=_render_markdown(pack),
    )
