from pathlib import Path

from fastapi.testclient import TestClient

from cc_history.main import app
from cc_history.services import indexer, scanner, search


def _write_session(project_dir: Path, session_id: str, text: str) -> None:
    project_dir.mkdir(parents=True, exist_ok=True)
    (project_dir / f"{session_id}.jsonl").write_text(
        "\n".join(
            [
                (
                    '{"type":"user","sessionId":"'
                    + session_id
                    + '","uuid":"u-'
                    + session_id
                    + '","timestamp":"2026-05-14T00:00:00Z","message":{"role":"user","content":"'
                    + text
                    + '"}}'
                ),
                (
                    '{"type":"assistant","sessionId":"'
                    + session_id
                    + '","uuid":"a-'
                    + session_id
                    + '","timestamp":"2026-05-14T00:00:01Z","message":{"id":"msg","type":"message","role":"assistant","model":"claude","content":[{"type":"text","text":"assistant reply"}]}}'
                ),
            ],
        ),
        encoding="utf-8",
    )


def test_index_and_search_messages(
    tmp_path: Path,
    monkeypatch,
) -> None:
    nas_root = tmp_path / "claude-logs"
    cache_dir = tmp_path / "cache"
    project_dir = nas_root / "projects" / "-home-alice-app"
    _write_session(project_dir, "session-1", "Transformer accuracy improved")
    _write_session(project_dir, "session-2", "Unrelated note")
    monkeypatch.setattr(scanner.settings, "nas_root", nas_root)
    monkeypatch.setattr(scanner.settings, "cache_dir", cache_dir)

    summary = indexer.index_all_sessions()
    results = search.search_messages("Transformer")

    assert summary.indexed_sessions == 2
    assert len(results) == 1
    assert results[0].session_id == "session-1"
    assert results[0].user == "local"
    assert "<mark>Transformer</mark>" in results[0].text
    assert "accuracy improved" in results[0].text


def test_search_api_indexes_before_query(
    tmp_path: Path,
    monkeypatch,
) -> None:
    nas_root = tmp_path / "claude-logs"
    cache_dir = tmp_path / "cache"
    project_dir = nas_root / "projects" / "-home-alice-app"
    _write_session(project_dir, "session-1", "fall detection model")
    monkeypatch.setattr(scanner.settings, "nas_root", nas_root)
    monkeypatch.setattr(scanner.settings, "cache_dir", cache_dir)

    client = TestClient(app)
    response = client.get("/api/search", params={"q": "fall detection"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["query"] == "fall detection"
    assert len(payload["results"]) == 1
    assert payload["results"][0]["session_id"] == "session-1"


def test_search_keeps_same_session_id_separate_across_users(
    tmp_path: Path,
    monkeypatch,
) -> None:
    nas_root = tmp_path / "private-share"
    cache_dir = tmp_path / "cache"
    _write_session(
        nas_root / "alice" / "claude-logs" / "projects" / "-home-team-app",
        "shared-session",
        "shared duplicate term from alice",
    )
    _write_session(
        nas_root / "bob" / "claude-logs" / "projects" / "-home-team-app",
        "shared-session",
        "shared duplicate term from bob",
    )
    monkeypatch.setattr(scanner.settings, "nas_root", nas_root)
    monkeypatch.setattr(scanner.settings, "cache_dir", cache_dir)

    summary = indexer.index_all_sessions()
    results = search.search_messages("shared duplicate")

    assert summary.indexed_sessions == 2
    assert len(results) == 2
    assert {result.user for result in results} == {"alice", "bob"}
    assert {result.session_id for result in results} == {"shared-session"}


def test_search_page_and_results_fragment(
    tmp_path: Path,
    monkeypatch,
) -> None:
    nas_root = tmp_path / "claude-logs"
    cache_dir = tmp_path / "cache"
    project_dir = nas_root / "projects" / "-home-alice-app"
    _write_session(project_dir, "session-1", "learning curve")
    monkeypatch.setattr(scanner.settings, "nas_root", nas_root)
    monkeypatch.setattr(scanner.settings, "cache_dir", cache_dir)

    client = TestClient(app)
    page = client.get("/search", params={"q": "learning"})
    fragment = client.get("/search/results", params={"q": "learning"})

    assert page.status_code == 200
    assert 'hx-get="/search/results"' in page.text
    assert "learning" in page.text
    assert fragment.status_code == 200
    assert "session-1" in fragment.text
    assert "<mark>learning</mark>" in fragment.text
