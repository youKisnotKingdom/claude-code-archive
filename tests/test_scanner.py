from pathlib import Path

from cc_history.services import scanner


def test_decode_project_name() -> None:
    assert scanner.decode_project_name("-Users-alice-myapp") == "/Users/alice/myapp"
    assert scanner.decode_project_name("-home-bob-proj") == "/home/bob/proj"
    assert scanner.decode_project_name("plain-project") == "plain/project"


def test_scanner_lists_users_projects_and_sessions(
    tmp_path: Path,
    monkeypatch,
) -> None:
    nas_root = tmp_path / "private-share"
    project_dir = nas_root / "alice" / "claude-logs" / "projects" / "-home-alice-app"
    project_dir.mkdir(parents=True)
    session_file = project_dir / "session-1.jsonl"
    session_file.write_text('{"type":"user","message":{}}\n', encoding="utf-8")
    ignored_file = project_dir / "notes.txt"
    ignored_file.write_text("ignore", encoding="utf-8")
    unrelated_dir = nas_root / "bob"
    unrelated_dir.mkdir()
    monkeypatch.setattr(scanner.settings, "nas_root", nas_root)

    assert scanner.list_users() == ["alice"]
    assert scanner.list_projects("alice") == ["-home-alice-app"]

    sessions = scanner.list_sessions("alice", "-home-alice-app")
    assert len(sessions) == 1
    assert sessions[0].user == "alice"
    assert sessions[0].project == "-home-alice-app"
    assert sessions[0].project_decoded == "/home/alice/app"
    assert sessions[0].session_id == "session-1"
    assert sessions[0].file_path == session_file
    assert scanner.get_session_path("alice", "-home-alice-app", "session-1") == session_file
    assert scanner.get_session_path("alice", "-home-alice-app", "missing") is None


def test_scanner_rejects_unsafe_path_segments(
    tmp_path: Path,
    monkeypatch,
) -> None:
    nas_root = tmp_path / "private-share"
    project_dir = nas_root / "alice" / "claude-logs" / "projects" / "-home-alice-app"
    project_dir.mkdir(parents=True)
    session_file = project_dir / "session-1.jsonl"
    session_file.write_text('{"type":"user","message":{"role":"user","content":"hello"}}\n')
    monkeypatch.setattr(scanner.settings, "nas_root", nas_root)

    assert scanner.list_projects("..") == []
    assert scanner.list_sessions("alice", "..") == []
    assert scanner.get_session_path("alice", "..", "session-1") is None
    assert scanner.get_session_path("alice", "-home-alice-app", "../session-1") is None
    assert scanner.get_session_path("../alice", "-home-alice-app", "session-1") is None


def test_scanner_extracts_session_title_and_metadata(
    tmp_path: Path,
    monkeypatch,
) -> None:
    nas_root = tmp_path / "private-share"
    project_dir = nas_root / "alice" / "claude-logs" / "projects" / "-home-alice-app"
    project_dir.mkdir(parents=True)
    session_file = project_dir / "session-1.jsonl"
    session_file.write_text(
        "\n".join(
            [
                '{"type":"ai-title","aiTitle":"AI title"}',
                '{"type":"custom-title","customTitle":"Custom title"}',
                '{"type":"user","uuid":"u1","cwd":"/work/app","gitBranch":"main","timestamp":"2026-05-14T00:00:00Z","message":{"role":"user","content":"Please inspect the repository."}}',
                '{"type":"assistant","uuid":"a1","timestamp":"2026-05-14T00:00:02Z","message":{"id":"m1","type":"message","role":"assistant","model":"claude-sonnet","content":[{"type":"text","text":"Done"}],"usage":{"input_tokens":3,"output_tokens":5}}}',
            ],
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(scanner.settings, "nas_root", nas_root)

    sessions = scanner.list_sessions("alice", "-home-alice-app")

    assert len(sessions) == 1
    assert sessions[0].title == "Custom title"
    assert sessions[0].first_user_text == "Please inspect the repository."
    assert sessions[0].message_count == 2
    assert sessions[0].model_name == "claude-sonnet"
    assert sessions[0].total_tokens == 8
    assert sessions[0].cwd == "/work/app"
    assert sessions[0].git_branch == "main"
    assert sessions[0].last_message_at == "2026-05-14T00:00:02Z"


def test_scanner_supports_single_claude_config_dir_layout(
    tmp_path: Path,
    monkeypatch,
) -> None:
    claude_logs = tmp_path / "claude-logs"
    project_dir = claude_logs / "projects" / "-home-alice-app"
    project_dir.mkdir(parents=True)
    session_file = project_dir / "session-1.jsonl"
    session_file.write_text('{"type":"user","message":{}}\n', encoding="utf-8")
    monkeypatch.setattr(scanner.settings, "nas_root", claude_logs)
    monkeypatch.setattr(scanner.settings, "single_user_name", "local")

    assert scanner.list_users() == ["local"]
    assert scanner.list_projects("local") == ["-home-alice-app"]

    sessions = scanner.list_sessions("local", "-home-alice-app")
    assert len(sessions) == 1
    assert sessions[0].user == "local"
    assert sessions[0].file_path == session_file
    assert scanner.get_session_path("local", "-home-alice-app", "session-1") == session_file
    assert scanner.list_projects("alice") == []
