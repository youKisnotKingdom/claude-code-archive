from pathlib import Path

from cc_history.services import watcher


class FakeEvent:
    def __init__(self, src_path: Path, is_directory: bool = False) -> None:
        self.src_path = str(src_path)
        self.is_directory = is_directory


def test_jsonl_event_handler_runs_callback_for_jsonl_files(tmp_path: Path) -> None:
    calls: list[Path] = []
    handler = watcher.JsonlEventHandler(lambda path: calls.append(path))
    session_path = tmp_path / "session.jsonl"

    handler.on_created(FakeEvent(session_path))
    handler.on_modified(FakeEvent(session_path))
    handler.on_created(FakeEvent(tmp_path / "notes.txt"))
    handler.on_created(FakeEvent(tmp_path / "nested", is_directory=True))

    assert calls == [session_path, session_path]


def test_refresh_index_for_event_indexes_all_sessions(monkeypatch, tmp_path: Path) -> None:
    calls: list[bool] = []
    monkeypatch.setattr(watcher.indexer, "index_all_sessions", lambda: calls.append(True))

    watcher.refresh_index_for_event(tmp_path / "session.jsonl")

    assert calls == [True]
