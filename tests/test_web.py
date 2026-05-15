from pathlib import Path

from fastapi.testclient import TestClient

from cc_history.main import app
from cc_history.services import scanner


def test_web_drilldown_and_api_render_phase1_mvp(
    tmp_path: Path,
    monkeypatch,
) -> None:
    nas_root = tmp_path / "private-share"
    project_dir = nas_root / "alice" / "claude-logs" / "projects" / "-home-alice-demo"
    project_dir.mkdir(parents=True)
    session_file = project_dir / "sample-session.jsonl"
    sample = Path("tests/fixtures/sample_session.jsonl").read_text(encoding="utf-8")
    metadata_entry = (
        '{"type":"permission-mode","sessionId":"sample-session","permissionMode":"default"}'
    )
    session_file.write_text(f"{metadata_entry}\n{sample}\nnot json\n", encoding="utf-8")
    monkeypatch.setattr(scanner.settings, "nas_root", nas_root)

    client = TestClient(app)

    users_response = client.get("/api/users")
    assert users_response.status_code == 200
    assert users_response.json() == {"users": ["alice"]}

    projects_response = client.get("/api/users/alice/projects")
    assert projects_response.status_code == 200
    assert projects_response.json() == {
        "projects": [
            {
                "name": "-home-alice-demo",
                "decoded": "/home/alice/demo",
            },
        ],
    }

    sessions_response = client.get("/api/users/alice/projects/-home-alice-demo/sessions")
    assert sessions_response.status_code == 200
    sessions = sessions_response.json()["sessions"]
    assert len(sessions) == 1
    assert sessions[0]["session_id"] == "sample-session"

    entries_response = client.get(
        "/api/users/alice/projects/-home-alice-demo/sessions/sample-session",
    )
    assert entries_response.status_code == 200
    entries = entries_response.json()["entries"]
    assert entries[-1]["type"] == "x-error"

    home_response = client.get("/")
    assert home_response.status_code == 200
    assert "alice" in home_response.text

    project_response = client.get("/users/alice/projects/-home-alice-demo")
    assert project_response.status_code == 200
    assert "sample-session" in project_response.text

    session_response = client.get("/users/alice/projects/-home-alice-demo/sessions/sample-session")
    assert session_response.status_code == 200
    assert "ccv-session-shell" in session_response.text
    assert "ccv-main-scroll" in session_response.text
    assert "ccv-meta-event" in session_response.text
    assert "Please inspect the repository." in session_response.text
    assert "Tool: Bash" in session_response.text
    assert 'class="ccv-tool-card is-bash" open' not in session_response.text
    assert "not json" in session_response.text
    assert "x-error" in session_response.text


def test_session_list_and_detail_use_readable_title_and_markdown(
    tmp_path: Path,
    monkeypatch,
) -> None:
    nas_root = tmp_path / "private-share"
    project_dir = nas_root / "alice" / "claude-logs" / "projects" / "-home-alice-demo"
    project_dir.mkdir(parents=True)
    session_file = project_dir / "sample-session.jsonl"
    session_file.write_text(
        "\n".join(
            [
                '{"type":"ai-title","aiTitle":"Readable session"}',
                '{"type":"user","uuid":"u1","timestamp":"2026-05-14T00:00:00Z","message":{"role":"user","content":"Please inspect."}}',
                '{"type":"assistant","uuid":"a1","timestamp":"2026-05-14T00:00:01Z","message":{"id":"m1","type":"message","role":"assistant","model":"claude","content":[{"type":"text","text":"## Result\\n\\n- Done"}]}}',
            ],
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(scanner.settings, "nas_root", nas_root)

    client = TestClient(app)
    project_response = client.get("/users/alice/projects/-home-alice-demo")
    session_response = client.get("/users/alice/projects/-home-alice-demo/sessions/sample-session")

    assert project_response.status_code == 200
    assert "Readable session" in project_response.text
    assert session_response.status_code == 200
    assert "Readable session" in session_response.text
    assert "<h2>Result</h2>" in session_response.text
    assert "<li>Done</li>" in session_response.text


def test_session_page_shows_find_ui_edited_files_and_structured_tool_result(
    tmp_path: Path,
    monkeypatch,
) -> None:
    nas_root = tmp_path / "private-share"
    project_dir = nas_root / "alice" / "claude-logs" / "projects" / "-home-alice-demo"
    project_dir.mkdir(parents=True)
    session_file = project_dir / "sample-session.jsonl"
    session_file.write_text(
        "\n".join(
            [
                '{"type":"user","uuid":"u1","cwd":"/workspace/demo","message":{"role":"user","content":"Please edit app.py"}}',
                '{"type":"assistant","uuid":"a1","timestamp":"2026-05-14T00:00:01Z","message":{"id":"m1","type":"message","role":"assistant","model":"claude","content":[{"type":"tool_use","id":"tool-1","name":"Edit","input":{"file_path":"/workspace/demo/app.py","old_string":"old","new_string":"new"}},{"type":"tool_use","id":"tool-2","name":"Bash","input":{"command":"pytest"}}]}}',
                '{"type":"user","uuid":"u2","toolUseResult":{"stdout":"2 passed","stderr":"warning","interrupted":false,"isImage":false},"message":{"role":"user","content":[{"type":"tool_result","tool_use_id":"tool-2","content":"2 passed"}]}}',
            ],
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(scanner.settings, "nas_root", nas_root)

    client = TestClient(app)
    response = client.get("/users/alice/projects/-home-alice-demo/sessions/sample-session")

    assert response.status_code == 200
    assert "ccv-session-find-input" in response.text
    assert "ccv-edited-files" in response.text
    assert "app.py" in response.text
    assert "ccv-result-stream is-stdout" in response.text
    assert "2 passed" in response.text
    assert "warning" in response.text


def test_session_page_loads_subagent_file_transcript(
    tmp_path: Path,
    monkeypatch,
) -> None:
    nas_root = tmp_path / "private-share"
    project_dir = nas_root / "alice" / "claude-logs" / "projects" / "-home-alice-demo"
    subagent_dir = project_dir / "sample-session" / "subagents"
    subagent_dir.mkdir(parents=True)
    session_file = project_dir / "sample-session.jsonl"
    session_file.write_text(
        "\n".join(
            [
                '{"type":"assistant","uuid":"assistant-1","message":{"id":"msg-1","type":"message","role":"assistant","model":"claude","content":[{"type":"tool_use","id":"tool-1","name":"Task","input":{"prompt":"Inspect side task"}}]}}',
                '{"type":"user","uuid":"user-1","toolUseResult":{"agentId":"agent1"},"message":{"role":"user","content":[{"type":"tool_result","tool_use_id":"tool-1","content":"done"}]}}',
            ],
        ),
        encoding="utf-8",
    )
    (subagent_dir / "agent-agent1.jsonl").write_text(
        "\n".join(
            [
                '{"type":"user","uuid":"agent-user-1","parentUuid":null,"sessionId":"agent-session","isSidechain":true,"agentId":"agent1","message":{"role":"user","content":"Inspect side task"}}',
                '{"type":"assistant","uuid":"agent-assistant-1","parentUuid":"agent-user-1","sessionId":"agent-session","isSidechain":true,"message":{"id":"agent-msg-1","type":"message","role":"assistant","model":"claude","content":[{"type":"text","text":"Side task complete."}]}}',
            ],
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(scanner.settings, "nas_root", nas_root)

    client = TestClient(app)
    response = client.get("/users/alice/projects/-home-alice-demo/sessions/sample-session")

    assert response.status_code == 200
    assert "ccv-subagent" in response.text
    assert "Inspect side task" in response.text
    assert "Side task complete." in response.text
