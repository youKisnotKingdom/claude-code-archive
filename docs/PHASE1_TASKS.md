# Phase 1: 詳細タスクリスト

Codex に渡す前提で、順に実行すれば動く MVP が完成するように書く。

## 前提

- Python 3.11 以上
- パッケージマネージャは `uv` を推奨 (高速)。`pip` でも可
- NAS は `/mnt/shared-ai3-01/private-share` にマウント済み
- 開発マシンから NAS が読める

## タスク 1: プロジェクト雛形作成

### 1.1 pyproject.toml

```toml
[project]
name = "cc-history-viewer"
version = "0.1.0"
description = "Multi-user Claude Code history viewer"
requires-python = ">=3.11"
dependencies = [
  "fastapi>=0.115",
  "uvicorn[standard]>=0.32",
  "pydantic>=2.9",
  "pydantic-settings>=2.6",
  "jinja2>=3.1",
  "python-multipart>=0.0.12",
]

[project.optional-dependencies]
dev = [
  "pytest>=8.0",
  "pytest-asyncio>=0.24",
  "httpx>=0.27",
  "ruff>=0.7",
]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/cc_history"]
```

### 1.2 ディレクトリを作る

```
mkdir -p src/cc_history/{schema,services,api,web/templates,web/static}
touch src/cc_history/__init__.py
touch src/cc_history/{schema,services,api,web}/__init__.py
```

### 1.3 セットアップ

```bash
uv venv
uv sync
# または
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
```

## タスク 2: 設定 (config.py)

`src/cc_history/config.py`:

```python
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="CC_", env_file=".env")

    nas_root: Path = Path("/mnt/shared-ai3-01/private-share")
    cache_dir: Path = Path.home() / ".cache" / "cc-history-viewer"
    host: str = "0.0.0.0"
    port: int = 8000
    auth_password: str | None = None
    log_level: str = "INFO"

    @property
    def cache_db_path(self) -> Path:
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        return self.cache_dir / "cache.db"


settings = Settings()
```

## タスク 3: JSONL スキーマ (最小版)

詳細は `JSONL_SCHEMA.md` を参照。

`src/cc_history/schema/entry.py`:

```python
from typing import Any, Literal
from pydantic import BaseModel, ConfigDict


class BaseEntry(BaseModel):
    """全エントリ共通フィールド。未知のフィールドは保持する。"""
    model_config = ConfigDict(extra="allow")

    type: str
    sessionId: str | None = None
    uuid: str | None = None
    parentUuid: str | None = None
    timestamp: str | None = None
    cwd: str | None = None
    version: str | None = None
    gitBranch: str | None = None
    isSidechain: bool | None = None
    isMeta: bool | None = None


class UserEntry(BaseEntry):
    type: Literal["user"]
    message: dict[str, Any]


class AssistantEntry(BaseEntry):
    type: Literal["assistant"]
    message: dict[str, Any]


class SystemEntry(BaseEntry):
    type: Literal["system"]
    subtype: str | None = None
    content: str | None = None


class SummaryEntry(BaseEntry):
    type: Literal["summary"]
    summary: str
    leafUuid: str | None = None


class CustomTitleEntry(BaseEntry):
    type: Literal["custom-title"]
    customTitle: str | None = None


class AiTitleEntry(BaseEntry):
    type: Literal["ai-title"]
    aiTitle: str | None = None


class UnknownEntry(BaseEntry):
    """上記いずれにもマッチしなかった既知でない type のエントリ。"""
    pass


class ErrorEntry(BaseModel):
    """パース失敗を表す合成エントリ。"""
    type: Literal["x-error"] = "x-error"
    line: str
    line_number: int
    error: str
```

`src/cc_history/schema/__init__.py`:

```python
from .entry import (
    BaseEntry, UserEntry, AssistantEntry, SystemEntry,
    SummaryEntry, CustomTitleEntry, AiTitleEntry,
    UnknownEntry, ErrorEntry,
)

__all__ = [
    "BaseEntry", "UserEntry", "AssistantEntry", "SystemEntry",
    "SummaryEntry", "CustomTitleEntry", "AiTitleEntry",
    "UnknownEntry", "ErrorEntry",
]
```

## タスク 4: JSONL パーサー

`src/cc_history/services/parser.py`:

```python
import json
from pathlib import Path
from typing import Iterator

from cc_history.schema import (
    UserEntry, AssistantEntry, SystemEntry, SummaryEntry,
    CustomTitleEntry, AiTitleEntry, UnknownEntry, ErrorEntry,
)

# type フィールドから対応するモデルへのマッピング
_TYPE_MAP = {
    "user": UserEntry,
    "assistant": AssistantEntry,
    "system": SystemEntry,
    "summary": SummaryEntry,
    "custom-title": CustomTitleEntry,
    "ai-title": AiTitleEntry,
}


def parse_jsonl_line(line: str, line_number: int):
    """1 行をパースして適切なエントリを返す。失敗時は ErrorEntry。"""
    try:
        data = json.loads(line)
    except json.JSONDecodeError as e:
        return ErrorEntry(line=line, line_number=line_number, error=f"JSONDecode: {e}")

    if not isinstance(data, dict):
        return ErrorEntry(line=line, line_number=line_number, error="not a JSON object")

    type_ = data.get("type")
    model = _TYPE_MAP.get(type_, UnknownEntry)

    try:
        return model.model_validate(data)
    except Exception as e:
        return ErrorEntry(line=line, line_number=line_number, error=f"Validation: {e}")


def parse_jsonl_file(path: Path) -> Iterator:
    """JSONL ファイルを 1 行ずつパースしてイテレータで返す。"""
    with path.open("r", encoding="utf-8") as f:
        for i, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue
            yield parse_jsonl_line(line, i)
```

## タスク 5: NAS スキャナー

`src/cc_history/services/scanner.py`:

```python
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

from cc_history.config import settings


@dataclass
class SessionInfo:
    user: str
    project: str           # エンコード済みのプロジェクト名
    project_decoded: str   # デコード済み
    session_id: str        # ファイル名 (拡張子除く)
    file_path: Path
    mtime: float
    size: int


def decode_project_name(encoded: str) -> str:
    """`-Users-alice-myapp` → `/Users/alice/myapp`"""
    if encoded.startswith("-"):
        return "/" + encoded[1:].replace("-", "/")
    return encoded.replace("-", "/")


def list_users() -> list[str]:
    """NAS 上の全ユーザーを列挙。"""
    if not settings.nas_root.is_dir():
        return []
    users = []
    for entry in settings.nas_root.iterdir():
        if not entry.is_dir():
            continue
        projects = entry / "claude-logs" / "projects"
        if projects.is_dir():
            users.append(entry.name)
    return sorted(users)


def list_projects(user: str) -> list[str]:
    """指定ユーザーのプロジェクト一覧。"""
    projects_dir = settings.nas_root / user / "claude-logs" / "projects"
    if not projects_dir.is_dir():
        return []
    return sorted(p.name for p in projects_dir.iterdir() if p.is_dir())


def list_sessions(user: str, project: str) -> list[SessionInfo]:
    """指定プロジェクトのセッションファイル一覧。"""
    project_dir = settings.nas_root / user / "claude-logs" / "projects" / project
    if not project_dir.is_dir():
        return []
    sessions = []
    for f in project_dir.iterdir():
        if f.suffix != ".jsonl":
            continue
        stat = f.stat()
        sessions.append(SessionInfo(
            user=user,
            project=project,
            project_decoded=decode_project_name(project),
            session_id=f.stem,
            file_path=f,
            mtime=stat.st_mtime,
            size=stat.st_size,
        ))
    return sorted(sessions, key=lambda s: s.mtime, reverse=True)


def get_session_path(user: str, project: str, session_id: str) -> Path | None:
    p = settings.nas_root / user / "claude-logs" / "projects" / project / f"{session_id}.jsonl"
    return p if p.is_file() else None
```

## タスク 6: FastAPI エントリポイント

`src/cc_history/main.py`:

```python
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from pathlib import Path

from cc_history.web.routes import router as web_router
from cc_history.api.users import router as users_api
from cc_history.api.projects import router as projects_api
from cc_history.api.sessions import router as sessions_api

app = FastAPI(title="CC History Viewer")

# 静的ファイル
static_dir = Path(__file__).parent / "web" / "static"
static_dir.mkdir(parents=True, exist_ok=True)
app.mount("/static", StaticFiles(directory=static_dir), name="static")

# ルーター
app.include_router(web_router)
app.include_router(users_api, prefix="/api")
app.include_router(projects_api, prefix="/api")
app.include_router(sessions_api, prefix="/api")


def main():
    import uvicorn
    from cc_history.config import settings
    uvicorn.run(
        "cc_history.main:app",
        host=settings.host,
        port=settings.port,
        reload=True,
    )


if __name__ == "__main__":
    main()
```

## タスク 7: Web ルートとテンプレート

詳細は実装時に決めて良いが、最低限必要なルート:

- `GET /` → ユーザー一覧
- `GET /users/{user}` → プロジェクト一覧
- `GET /users/{user}/projects/{project}` → セッション一覧
- `GET /users/{user}/projects/{project}/sessions/{session_id}` → 会話表示

API:

- `GET /api/users` → ユーザー一覧 JSON
- `GET /api/users/{user}/projects` → プロジェクト一覧 JSON
- `GET /api/users/{user}/projects/{project}/sessions` → セッション一覧 JSON
- `GET /api/users/{user}/projects/{project}/sessions/{session_id}` → パース済みエントリ配列 JSON

### ベーステンプレートのスタイル

Tailwind は CDN 版 (Play CDN) で開発を開始して OK:

```html
<script src="https://cdn.tailwindcss.com"></script>
```

本番ビルドは Phase 2 以降で対応。HTMX も CDN で:

```html
<script src="https://unpkg.com/htmx.org@2.0.3"></script>
```

## タスク 8: 動作確認

```bash
# 環境変数を設定 (NAS 以外の場所でテストする場合)
export CC_NAS_ROOT=/path/to/test/private-share

# サーバー起動
uv run python -m cc_history.main

# ブラウザで http://localhost:8000/
```

## タスク 9: テスト

最低限の unit test を書く。

`tests/fixtures/sample_session.jsonl`: claude-code-viewer の `mock-global-claude-dir/` から数行コピーするか、自前のセッションから 1 つ用意。

`tests/test_parser.py`:

```python
from pathlib import Path
from cc_history.services.parser import parse_jsonl_file
from cc_history.schema import UserEntry, AssistantEntry, ErrorEntry


def test_parse_valid_jsonl():
    entries = list(parse_jsonl_file(Path("tests/fixtures/sample_session.jsonl")))
    assert len(entries) > 0
    # エラーが過半数を占めないこと
    errors = [e for e in entries if isinstance(e, ErrorEntry)]
    assert len(errors) < len(entries) / 2


def test_parse_broken_line(tmp_path):
    f = tmp_path / "broken.jsonl"
    f.write_text('{"type": "user", "message": {}}\nthis is not json\n')
    entries = list(parse_jsonl_file(f))
    assert len(entries) == 2
    assert isinstance(entries[0], UserEntry)
    assert isinstance(entries[1], ErrorEntry)
```

`tests/test_scanner.py`:

```python
from cc_history.services.scanner import decode_project_name


def test_decode_project_name():
    assert decode_project_name("-Users-alice-myapp") == "/Users/alice/myapp"
    assert decode_project_name("-home-bob-proj") == "/home/bob/proj"
```

## チェックリスト

Phase 1 完了時に以下が動くこと:

- [ ] `uv run python -m cc_history.main` でサーバーが起動する
- [ ] `http://localhost:8000/` を開くと NAS 上のユーザー一覧が表示される
- [ ] ユーザーをクリックするとプロジェクト一覧が見える
- [ ] プロジェクトをクリックするとセッション一覧 (新しい順) が見える
- [ ] セッションをクリックすると会話が時系列で読める
- [ ] ツール呼び出しは最低限「Tool: <name>」と表示される
- [ ] `pytest` がパスする
- [ ] パース失敗した行が `ErrorEntry` として赤く表示される (壊れない)

## 次のステップ

Phase 1 が動いたら `ROADMAP.md` の Phase 2 (詳細表示 + 検索) に進む。
