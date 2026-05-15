from pathlib import Path

from fastapi.testclient import TestClient

from cc_history.main import app
from cc_history.services import agent_context, annotations, scanner


def _write_session(project_dir: Path, session_id: str, text: str) -> None:
    project_dir.mkdir(parents=True, exist_ok=True)
    (project_dir / f"{session_id}.jsonl").write_text(
        (
            '{"type":"user","sessionId":"'
            + session_id
            + '","uuid":"u-'
            + session_id
            + '","timestamp":"2026-05-14T00:00:00Z","message":{"role":"user","content":"'
            + text
            + '"}}\n'
        ),
        encoding="utf-8",
    )


def test_build_agent_context_pack_from_reviewed_project_annotations(
    tmp_path: Path,
    monkeypatch,
) -> None:
    nas_root = tmp_path / "private-share"
    cache_dir = tmp_path / "cache"
    project_dir = nas_root / "alice" / "claude-logs" / "projects" / "-home-alice-demo"
    _write_session(project_dir, "session-1", "deploy fix")
    _write_session(project_dir, "session-2", "private note")
    monkeypatch.setattr(scanner.settings, "nas_root", nas_root)
    monkeypatch.setattr(scanner.settings, "cache_dir", cache_dir)
    monkeypatch.setattr(annotations.settings, "cache_dir", cache_dir)

    annotations.save_session_annotation(
        user="alice",
        project="-home-alice-demo",
        session_id="session-1",
        manual_title="Deployment checklist rule",
        note="Run the deploy smoke test before promoting this service.",
        is_favorite=True,
        is_archived=False,
        review_status="reviewed",
        knowledge_scope="project",
        tags=["deploy", "command"],
    )
    annotations.save_session_annotation(
        user="alice",
        project="-home-alice-demo",
        session_id="session-2",
        manual_title="Private scratch",
        note="Do not include by default.",
        is_favorite=False,
        is_archived=False,
        review_status="reviewed",
        knowledge_scope="private",
        tags=["private"],
    )

    pack = agent_context.build_agent_context_pack(
        user="alice",
        project="-home-alice-demo",
        statuses=["reviewed"],
        scopes=["project"],
    )

    assert pack.source_count == 1
    assert pack.project_decoded == "/home/alice/demo"
    assert "Deployment checklist rule" in pack.markdown
    assert "Run the deploy smoke test" in pack.markdown
    assert "deploy, command" in pack.markdown
    assert "/users/alice/projects/-home-alice-demo/sessions/session-1" in pack.markdown
    assert "Private scratch" not in pack.markdown


def test_agent_context_preview_route_renders_markdown_from_annotations(
    tmp_path: Path,
    monkeypatch,
) -> None:
    nas_root = tmp_path / "private-share"
    cache_dir = tmp_path / "cache"
    project_dir = nas_root / "alice" / "claude-logs" / "projects" / "-home-alice-demo"
    _write_session(project_dir, "session-1", "deployment")
    monkeypatch.setattr(scanner.settings, "nas_root", nas_root)
    monkeypatch.setattr(scanner.settings, "cache_dir", cache_dir)
    monkeypatch.setattr(annotations.settings, "cache_dir", cache_dir)

    annotations.save_session_annotation(
        user="alice",
        project="-home-alice-demo",
        session_id="session-1",
        manual_title="Deployment checklist rule",
        note="Run the deploy smoke test before promoting this service.",
        is_favorite=True,
        is_archived=False,
        review_status="candidate",
        knowledge_scope="project",
        tags=["deploy"],
    )

    response = TestClient(app).get(
        "/agent-context",
        params={
            "user": "alice",
            "project": "-home-alice-demo",
            "status": "candidate",
            "scope": "project",
        },
    )

    assert response.status_code == 200
    assert "Agent Context" in response.text
    assert "Deployment checklist rule" in response.text
    assert "Run the deploy smoke test" in response.text
    assert "Copy Markdown" in response.text
