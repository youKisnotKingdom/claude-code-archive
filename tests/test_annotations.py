from pathlib import Path

from cc_history.services import annotations
from cc_history.services import scanner


def _write_session(project_dir: Path, session_id: str, lines: list[str]) -> None:
    project_dir.mkdir(parents=True, exist_ok=True)
    (project_dir / f"{session_id}.jsonl").write_text("\n".join(lines), encoding="utf-8")


def test_save_and_load_session_annotation(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(annotations.settings, "cache_dir", tmp_path / "cache")

    saved = annotations.save_session_annotation(
        user="alice",
        project="-home-alice-app",
        session_id="session-1",
        manual_title="Deployment fix",
        note="Keep this for the deploy checklist.",
        is_favorite=True,
        is_archived=False,
        review_status="candidate",
        knowledge_scope="project",
        tags=["deploy", "pitfall", "deploy"],
    )
    loaded = annotations.get_session_annotation("alice", "-home-alice-app", "session-1")
    project_annotations = annotations.list_project_annotations("alice", "-home-alice-app")

    assert saved.manual_title == "Deployment fix"
    assert loaded.note == "Keep this for the deploy checklist."
    assert loaded.is_favorite is True
    assert loaded.is_archived is False
    assert loaded.review_status == "candidate"
    assert loaded.knowledge_scope == "project"
    assert loaded.tags == ["deploy", "pitfall"]
    assert project_annotations["session-1"].manual_title == "Deployment fix"


def test_parse_tag_text_normalizes_and_deduplicates() -> None:
    assert annotations.parse_tag_text(" Deploy, pitfall\nDeploy  ,  ") == ["deploy", "pitfall"]


def test_invalid_review_values_fall_back_to_unreviewed(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(annotations.settings, "cache_dir", tmp_path / "cache")

    loaded = annotations.save_session_annotation(
        user="alice",
        project="-home-alice-app",
        session_id="session-1",
        manual_title="",
        note="",
        is_favorite=False,
        is_archived=False,
        review_status="unexpected",
        knowledge_scope="invalid",
        tags=[],
    )

    assert loaded.review_status == "unreviewed"
    assert loaded.knowledge_scope == "unset"


def test_backfill_auto_labels_all_sessions_and_preserves_manual_tags(
    tmp_path: Path,
    monkeypatch,
) -> None:
    nas_root = tmp_path / "private-share"
    cache_dir = tmp_path / "cache"
    project_dir = nas_root / "alice" / "claude-logs" / "projects" / "-home-alice-app"
    _write_session(
        project_dir,
        "session-1",
        [
            '{"type":"user","uuid":"u1","message":{"role":"user","content":"Fix failing pytest"}}',
            '{"type":"assistant","uuid":"a1","message":{"id":"m1","type":"message","role":"assistant","model":"claude","content":[{"type":"tool_use","id":"tool-1","name":"Bash","input":{"command":"pytest"}},{"type":"tool_use","id":"tool-2","name":"Edit","input":{"file_path":"app.py","old_string":"old","new_string":"new"}}]}}',
        ],
    )
    _write_session(
        project_dir,
        "session-2",
        [
            '{"type":"user","uuid":"u2","message":{"role":"user","content":"Read the docs"}}',
        ],
    )
    monkeypatch.setattr(scanner.settings, "nas_root", nas_root)
    monkeypatch.setattr(scanner.settings, "cache_dir", cache_dir)
    monkeypatch.setattr(annotations.settings, "cache_dir", cache_dir)
    annotations.save_session_annotation(
        user="alice",
        project="-home-alice-app",
        session_id="session-1",
        manual_title="Manual title",
        note="Manual note",
        is_favorite=True,
        is_archived=False,
        review_status="candidate",
        knowledge_scope="project",
        tags=["manual-keep"],
    )

    summary = annotations.backfill_auto_labels()
    first = annotations.get_session_annotation("alice", "-home-alice-app", "session-1")
    second = annotations.get_session_annotation("alice", "-home-alice-app", "session-2")

    assert summary.scanned_sessions == 2
    assert summary.labeled_sessions == 2
    assert summary.created_annotations == 1
    assert "manual-keep" in first.tags
    assert "debugging" in first.tags
    assert "testing" in first.tags
    assert "uses-bash" in first.tags
    assert "file-edit" in first.tags
    assert second.review_status == "unreviewed"
    assert second.knowledge_scope == "unset"
    assert "docs" in second.tags


def test_list_review_items_filters_by_status_scope_and_tag(
    tmp_path: Path,
    monkeypatch,
) -> None:
    nas_root = tmp_path / "private-share"
    cache_dir = tmp_path / "cache"
    project_dir = nas_root / "alice" / "claude-logs" / "projects" / "-home-alice-app"
    _write_session(
        project_dir,
        "session-1",
        ['{"type":"user","uuid":"u1","message":{"role":"user","content":"Fix pytest"}}'],
    )
    _write_session(
        project_dir,
        "session-2",
        ['{"type":"user","uuid":"u2","message":{"role":"user","content":"Read docs"}}'],
    )
    monkeypatch.setattr(scanner.settings, "nas_root", nas_root)
    monkeypatch.setattr(scanner.settings, "cache_dir", cache_dir)
    monkeypatch.setattr(annotations.settings, "cache_dir", cache_dir)
    annotations.backfill_auto_labels()
    annotations.save_session_annotation(
        user="alice",
        project="-home-alice-app",
        session_id="session-1",
        manual_title="Pytest fix",
        note="Candidate for project testing rule.",
        is_favorite=False,
        is_archived=False,
        review_status="candidate",
        knowledge_scope="project",
        tags=["testing"],
    )

    all_items = annotations.list_review_items()
    candidate_items = annotations.list_review_items(status="candidate", scope="project")
    testing_items = annotations.list_review_items(tag="testing")

    assert [item.session_id for item in all_items] == ["session-2", "session-1"]
    assert [item.session_id for item in candidate_items] == ["session-1"]
    assert [item.session_id for item in testing_items] == ["session-1"]
