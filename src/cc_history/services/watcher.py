from pathlib import Path
from typing import Callable

from cc_history.config import settings
from cc_history.services import indexer

try:
    from watchdog.events import FileSystemEvent, FileSystemEventHandler
    from watchdog.observers import Observer
except ImportError:
    FileSystemEvent = object
    FileSystemEventHandler = object
    Observer = None


def refresh_index_for_event(path: Path) -> None:
    if path.suffix == ".jsonl":
        indexer.index_all_sessions()


class JsonlEventHandler(FileSystemEventHandler):
    def __init__(self, on_jsonl_change: Callable[[Path], None]) -> None:
        super().__init__()
        self._on_jsonl_change = on_jsonl_change

    def on_created(self, event: FileSystemEvent) -> None:
        self._handle_event(event)

    def on_modified(self, event: FileSystemEvent) -> None:
        self._handle_event(event)

    def _handle_event(self, event: FileSystemEvent) -> None:
        if getattr(event, "is_directory", False):
            return
        path = Path(str(getattr(event, "src_path", "")))
        if path.suffix != ".jsonl":
            return
        self._on_jsonl_change(path)


class WatchManager:
    def __init__(self) -> None:
        self._observer = None

    def start(self) -> None:
        if not settings.watch_enabled or Observer is None or not settings.nas_root.exists():
            return

        observer = Observer()
        handler = JsonlEventHandler(refresh_index_for_event)
        observer.schedule(handler, str(settings.nas_root), recursive=True)
        observer.start()
        self._observer = observer

    def stop(self) -> None:
        if self._observer is None:
            return
        self._observer.stop()
        self._observer.join(timeout=5)
        self._observer = None
