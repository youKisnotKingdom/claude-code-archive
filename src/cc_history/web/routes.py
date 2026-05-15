from pathlib import Path

from fastapi import APIRouter, Form, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates

from cc_history.services import agent_context
from cc_history.services import annotations
from cc_history.services import indexer
from cc_history.services import scanner
from cc_history.services import search as search_service
from cc_history.services import sidechain
from cc_history.services import stats
from cc_history.services.markdown import render_markdown
from cc_history.services.parser import parse_jsonl_file
from cc_history.services.rendering import build_conversation_views, extract_edited_files
from cc_history.web import auth

router = APIRouter()
templates = Jinja2Templates(directory=Path(__file__).parent / "templates")
templates.env.globals["auth_enabled"] = auth.auth_enabled


def _message_html(text: str) -> str:
    return render_markdown(text)


templates.env.filters["message_html"] = _message_html


def _session_to_view(
    session: scanner.SessionInfo,
    annotation: annotations.SessionAnnotation,
) -> dict[str, object]:
    return {
        "user": session.user,
        "project": session.project,
        "project_decoded": session.project_decoded,
        "session_id": session.session_id,
        "file_path": session.file_path,
        "mtime": session.mtime,
        "size": session.size,
        "title": annotation.manual_title or session.title,
        "source_title": session.title,
        "first_user_text": session.first_user_text,
        "message_count": session.message_count,
        "last_message_at": session.last_message_at,
        "model_name": session.model_name,
        "total_tokens": session.total_tokens,
        "cwd": session.cwd,
        "git_branch": session.git_branch,
        "annotation": annotation,
        "tags": annotation.tags,
        "is_favorite": annotation.is_favorite,
        "is_archived": annotation.is_archived,
        "review_status": annotation.review_status,
        "knowledge_scope": annotation.knowledge_scope,
    }


def _session_views(user: str, project: str) -> list[dict[str, object]]:
    project_annotations = annotations.list_project_annotations(user, project)
    return [
        _session_to_view(
            session,
            project_annotations.get(session.session_id)
            or annotations.empty_session_annotation(user, project, session.session_id),
        )
        for session in scanner.list_sessions(user, project)
    ]


def _safe_return_to(value: str) -> str:
    if value.startswith("/") and not value.startswith("//"):
        return value
    return "/"


@router.get("/", response_class=HTMLResponse)
def home(request: Request) -> HTMLResponse:
    overview = stats.collect_overview_stats()
    return templates.TemplateResponse(
        request,
        "users.html",
        {
            "users": overview.users,
            "overview": overview,
        },
    )


@router.get("/login", response_class=HTMLResponse)
def login_page(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        "login.html",
        {
            "error": None,
        },
    )


@router.post("/login", response_class=HTMLResponse)
def login_submit(request: Request, password: str = Form(default="")) -> Response:
    if not auth.authenticate_password(password):
        return templates.TemplateResponse(
            request,
            "login.html",
            {
                "error": "Invalid password",
            },
            status_code=401,
        )

    response = RedirectResponse("/", status_code=303)
    auth.set_auth_cookie(response)
    return response


@router.post("/logout")
def logout() -> RedirectResponse:
    response = RedirectResponse("/login", status_code=303)
    auth.clear_auth_cookie(response)
    return response


def _search_results(q: str, user: str | None) -> dict[str, object]:
    summary = indexer.index_all_sessions()
    results = search_service.search_messages(q, user=user)
    return {
        "q": q,
        "user": user,
        "index_summary": summary,
        "results": [
            {
                "session_id": result.session_id,
                "user": result.user,
                "project": result.project,
                "project_decoded": result.project_decoded,
                "role": result.role,
                "text": result.text,
                "timestamp": result.timestamp,
                "url": (
                    f"/users/{result.user}/projects/{result.project}/sessions/{result.session_id}"
                    + (f"#{result.uuid}" if result.uuid else "")
                ),
            }
            for result in results
        ],
    }


@router.get("/search", response_class=HTMLResponse)
def search_page(request: Request, q: str = "", user: str | None = None) -> HTMLResponse:
    context = _search_results(q, user) if q.strip() else {"q": q, "user": user, "results": []}
    context["users"] = scanner.list_users()
    return templates.TemplateResponse(request, "search.html", context)


@router.get("/search/results", response_class=HTMLResponse)
def search_results(request: Request, q: str = "", user: str | None = None) -> HTMLResponse:
    context = _search_results(q, user) if q.strip() else {"q": q, "user": user, "results": []}
    return templates.TemplateResponse(request, "search_results.html", context)


@router.get("/agent-context", response_class=HTMLResponse)
def agent_context_page(
    request: Request,
    user: str | None = None,
    project: str | None = None,
    status: list[str] | None = Query(default=None),
    scope: list[str] | None = Query(default=None),
    include_archived: bool = False,
) -> HTMLResponse:
    selected_statuses = status or list(agent_context.DEFAULT_STATUSES)
    selected_scopes = scope or list(agent_context.DEFAULT_SCOPES)
    pack = agent_context.build_agent_context_pack(
        user=user,
        project=project,
        statuses=selected_statuses,
        scopes=selected_scopes,
        include_archived=include_archived,
    )
    projects = scanner.list_projects(user) if user else []
    return templates.TemplateResponse(
        request,
        "agent_context.html",
        {
            "pack": pack,
            "users": scanner.list_users(),
            "projects": projects,
            "selected_user": user or "",
            "selected_project": project or "",
            "selected_statuses": selected_statuses,
            "selected_scopes": selected_scopes,
            "include_archived": include_archived,
            "review_statuses": annotations.REVIEW_STATUSES,
            "knowledge_scopes": annotations.KNOWLEDGE_SCOPES,
        },
    )


@router.post("/labels/backfill")
def backfill_labels(
    user: str = Form(default=""),
    project: str = Form(default=""),
    return_to: str = Form(default="/agent-context"),
) -> RedirectResponse:
    annotations.backfill_auto_labels(
        user=user or None,
        project=project or None,
    )
    return RedirectResponse(_safe_return_to(return_to), status_code=303)


@router.get("/review", response_class=HTMLResponse)
def review_inbox(
    request: Request,
    user: str | None = None,
    project: str | None = None,
    status: str | None = None,
    scope: str | None = None,
    tag: str | None = None,
    include_archived: bool = False,
) -> HTMLResponse:
    projects = scanner.list_projects(user) if user else []
    items = annotations.list_review_items(
        user=user,
        project=project,
        status=status,
        scope=scope,
        tag=tag,
        include_archived=include_archived,
    )
    return templates.TemplateResponse(
        request,
        "review.html",
        {
            "items": items,
            "users": scanner.list_users(),
            "projects": projects,
            "selected_user": user or "",
            "selected_project": project or "",
            "selected_status": status or "",
            "selected_scope": scope or "",
            "selected_tag": tag or "",
            "include_archived": include_archived,
            "review_statuses": annotations.REVIEW_STATUSES,
            "knowledge_scopes": annotations.KNOWLEDGE_SCOPES,
        },
    )


@router.post("/review/session")
def update_review_session(
    user: str = Form(),
    project: str = Form(),
    session_id: str = Form(),
    manual_title: str = Form(default=""),
    note: str = Form(default=""),
    tags: str = Form(default=""),
    is_favorite: bool = Form(default=False),
    is_archived: bool = Form(default=False),
    review_status: str = Form(default="unreviewed"),
    knowledge_scope: str = Form(default="unset"),
    return_to: str = Form(default="/review"),
) -> RedirectResponse:
    if scanner.get_session_path(user, project, session_id) is None:
        raise HTTPException(status_code=404, detail="Session not found")

    annotations.save_session_annotation(
        user=user,
        project=project,
        session_id=session_id,
        manual_title=manual_title,
        note=note,
        is_favorite=is_favorite,
        is_archived=is_archived,
        review_status=review_status,
        knowledge_scope=knowledge_scope,
        tags=annotations.parse_tag_text(tags),
    )
    return RedirectResponse(_safe_return_to(return_to), status_code=303)


@router.get("/users/{user}", response_class=HTMLResponse)
def user_projects(request: Request, user: str) -> HTMLResponse:
    user_stats = stats.collect_user_stats(user)
    projects = [
        {
            "name": project,
            "decoded": scanner.decode_project_name(project),
            "stats": stats.collect_project_stats(user, project),
        }
        for project in scanner.list_projects(user)
    ]
    return templates.TemplateResponse(
        request,
        "projects.html",
        {
            "user": user,
            "user_stats": user_stats,
            "projects": projects,
        },
    )


@router.get("/users/{user}/projects/{project}", response_class=HTMLResponse)
def project_sessions(request: Request, user: str, project: str) -> HTMLResponse:
    project_stats = stats.collect_project_stats(user, project)
    return templates.TemplateResponse(
        request,
        "sessions.html",
        {
            "user": user,
            "project": project,
            "project_decoded": scanner.decode_project_name(project),
            "project_stats": project_stats,
            "sessions": _session_views(user, project),
            "agent_context_url": f"/agent-context?user={user}&project={project}",
        },
    )


@router.get("/users/{user}/projects/{project}/sessions/{session_id}", response_class=HTMLResponse)
def session_detail(request: Request, user: str, project: str, session_id: str) -> HTMLResponse:
    path = scanner.get_session_path(user, project, session_id)
    if path is None:
        raise HTTPException(status_code=404, detail="Session not found")

    entries = list(parse_jsonl_file(path))
    agent_sessions = sidechain.load_agent_sessions(path.parent, session_id)
    views = build_conversation_views(entries, agent_sessions=agent_sessions)
    raw_sessions = scanner.list_sessions(user, project)
    sessions = _session_views(user, project)
    current_session = next(
        (session for session in raw_sessions if session.session_id == session_id),
        None,
    )
    annotation = annotations.get_session_annotation(user, project, session_id)
    tool_summary = [tool for entry in views for tool in entry["tools"]]
    edited_files = extract_edited_files(
        views,
        cwd=current_session.cwd if current_session is not None else None,
    )
    session_summary = {
        "message_count": len([entry for entry in views if entry["type"] in {"user", "assistant"}]),
        "user_count": len([entry for entry in views if entry["type"] == "user"]),
        "assistant_count": len([entry for entry in views if entry["type"] == "assistant"]),
        "tool_count": len(tool_summary),
        "error_count": len([entry for entry in views if entry["is_error"]]),
    }
    return templates.TemplateResponse(
        request,
        "session.html",
        {
            "user": user,
            "project": project,
            "project_decoded": scanner.decode_project_name(project),
            "session_id": session_id,
            "session_title": (
                annotation.manual_title
                or (current_session.title if current_session is not None else session_id)
            ),
            "current_session": current_session,
            "annotation": annotation,
            "annotation_tags_text": ", ".join(annotation.tags),
            "review_statuses": annotations.REVIEW_STATUSES,
            "knowledge_scopes": annotations.KNOWLEDGE_SCOPES,
            "entries": views,
            "sessions": sessions,
            "tool_summary": tool_summary,
            "edited_files": edited_files,
            "session_summary": session_summary,
        },
    )


@router.post("/users/{user}/projects/{project}/sessions/{session_id}/annotation")
def update_session_annotation(
    user: str,
    project: str,
    session_id: str,
    manual_title: str = Form(default=""),
    note: str = Form(default=""),
    tags: str = Form(default=""),
    is_favorite: bool = Form(default=False),
    is_archived: bool = Form(default=False),
    review_status: str = Form(default="unreviewed"),
    knowledge_scope: str = Form(default="unset"),
) -> RedirectResponse:
    if scanner.get_session_path(user, project, session_id) is None:
        raise HTTPException(status_code=404, detail="Session not found")

    annotations.save_session_annotation(
        user=user,
        project=project,
        session_id=session_id,
        manual_title=manual_title,
        note=note,
        is_favorite=is_favorite,
        is_archived=is_archived,
        review_status=review_status,
        knowledge_scope=knowledge_scope,
        tags=annotations.parse_tag_text(tags),
    )
    return RedirectResponse(
        f"/users/{user}/projects/{project}/sessions/{session_id}",
        status_code=303,
    )
