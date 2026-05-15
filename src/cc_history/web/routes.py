from pathlib import Path

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates

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
    sessions = scanner.list_sessions(user, project)
    project_stats = stats.collect_project_stats(user, project)
    return templates.TemplateResponse(
        request,
        "sessions.html",
        {
            "user": user,
            "project": project,
            "project_decoded": scanner.decode_project_name(project),
            "project_stats": project_stats,
            "sessions": sessions,
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
    sessions = scanner.list_sessions(user, project)
    current_session = next(
        (session for session in sessions if session.session_id == session_id),
        None,
    )
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
            "session_title": current_session.title if current_session is not None else session_id,
            "current_session": current_session,
            "entries": views,
            "sessions": sessions,
            "tool_summary": tool_summary,
            "edited_files": edited_files,
            "session_summary": session_summary,
        },
    )
