from pathlib import Path

from cc_history.services import scanner, stats


def _write_session(path: Path, timestamp: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        (
            '{"type":"user","sessionId":"'
            + path.stem
            + '","uuid":"u-'
            + path.stem
            + '","timestamp":"'
            + timestamp
            + '","message":{"role":"user","content":"hello"}}\n'
        ),
        encoding="utf-8",
    )


def test_collect_overview_stats_for_multi_user_root(
    tmp_path: Path,
    monkeypatch,
) -> None:
    nas_root = tmp_path / "private-share"
    _write_session(
        nas_root / "alice" / "claude-logs" / "projects" / "-home-alice-app" / "session-1.jsonl",
        "2026-05-14T00:00:00Z",
    )
    _write_session(
        nas_root / "alice" / "claude-logs" / "projects" / "-home-alice-lib" / "session-2.jsonl",
        "2026-05-14T00:01:00Z",
    )
    _write_session(
        nas_root / "bob" / "claude-logs" / "projects" / "-home-bob-app" / "session-3.jsonl",
        "2026-05-14T00:02:00Z",
    )
    monkeypatch.setattr(scanner.settings, "nas_root", nas_root)

    overview = stats.collect_overview_stats()

    assert overview.user_count == 2
    assert overview.project_count == 3
    assert overview.session_count == 3
    assert overview.latest_activity == "2026-05-14T00:02:00Z"
    assert [user.user for user in overview.users] == ["alice", "bob"]
    assert overview.users[0].project_count == 2
    assert overview.users[0].session_count == 2
    assert overview.users[1].project_count == 1
    assert overview.users[1].session_count == 1


def test_collect_project_stats(
    tmp_path: Path,
    monkeypatch,
) -> None:
    nas_root = tmp_path / "claude-logs"
    _write_session(
        nas_root / "projects" / "-home-alice-app" / "session-1.jsonl",
        "2026-05-14T00:00:00Z",
    )
    _write_session(
        nas_root / "projects" / "-home-alice-app" / "session-2.jsonl",
        "2026-05-14T00:03:00Z",
    )
    monkeypatch.setattr(scanner.settings, "nas_root", nas_root)

    project_stats = stats.collect_project_stats("local", "-home-alice-app")

    assert project_stats.user == "local"
    assert project_stats.project == "-home-alice-app"
    assert project_stats.session_count == 2
    assert project_stats.message_count == 2
    assert project_stats.latest_activity == "2026-05-14T00:03:00Z"
