# アーキテクチャ

## システム全体像

```
┌─────────────────────────────────────────────────────────────┐
│                      ユーザー (ブラウザ)                       │
└────────────────────────────┬────────────────────────────────┘
                             │ HTTP / HTMX
                             ▼
┌─────────────────────────────────────────────────────────────┐
│              FastAPI アプリケーション                          │
│  ┌────────────────────────────────────────────────────┐     │
│  │  Web UI (Jinja2 テンプレート + HTMX + Tailwind)     │     │
│  └────────────────────────────────────────────────────┘     │
│  ┌────────────────────────────────────────────────────┐     │
│  │  API レイヤ (/api/users, /api/projects, /api/...)   │     │
│  └────────────────────────────────────────────────────┘     │
│  ┌────────────────────────────────────────────────────┐     │
│  │  サービス層 (NASScanner, JSONLParser, Indexer, ...)  │     │
│  └────────────────────────────────────────────────────┘     │
└─────────────┬──────────────────────────┬────────────────────┘
              │                          │
              ▼                          ▼
┌─────────────────────────┐  ┌──────────────────────────────┐
│  NAS (read-only)        │  │  ローカル SQLite             │
│  /mnt/.../private-share │  │  ~/.cache/cc-history/       │
│    /<user>/claude-logs/ │  │    cache.db                  │
│      projects/          │  │    (メタデータ, FTS5 index) │
│        <project>/       │  │                              │
│          <session>.jsonl│  │                              │
└─────────────────────────┘  └──────────────────────────────┘
```

## ディレクトリ構造 (新規プロジェクト)

```
cc-history-viewer/
├── pyproject.toml              # uv / hatch などで管理
├── README.md
├── docs/                       # ハンドオフ資料一式
│   ├── ARCHITECTURE.md
│   ├── JSONL_SCHEMA.md
│   ├── ROADMAP.md
│   └── PHASE1_TASKS.md
├── src/
│   └── cc_history/
│       ├── __init__.py
│       ├── main.py             # FastAPI エントリポイント
│       ├── config.py           # 環境変数・設定 (pydantic-settings)
│       ├── schema/             # JSONL の Pydantic モデル
│       │   ├── __init__.py
│       │   ├── content.py      # TextContent, ToolUseContent, ...
│       │   ├── entry.py        # UserEntry, AssistantEntry, ...
│       │   └── conversation.py # ConversationEntry (Union)
│       ├── services/
│       │   ├── __init__.py
│       │   ├── scanner.py      # NAS をスキャンしてユーザー/プロジェクト/セッション一覧を返す
│       │   ├── parser.py       # JSONL を Pydantic でパース
│       │   ├── indexer.py      # SQLite + FTS5 にインデックスを構築
│       │   └── search.py       # 検索クエリ実行
│       ├── db/
│       │   ├── __init__.py
│       │   ├── connection.py   # SQLite 接続管理
│       │   └── schema.sql      # テーブル定義 + FTS5
│       ├── api/
│       │   ├── __init__.py
│       │   ├── users.py        # GET /api/users
│       │   ├── projects.py     # GET /api/users/{user}/projects
│       │   ├── sessions.py     # GET /api/users/{user}/projects/{project}/sessions
│       │   └── search.py       # GET /api/search?q=...
│       ├── web/
│       │   ├── __init__.py
│       │   ├── routes.py       # HTML を返すルート
│       │   ├── templates/      # Jinja2 テンプレート
│       │   │   ├── base.html
│       │   │   ├── users.html
│       │   │   ├── projects.html
│       │   │   ├── sessions.html
│       │   │   └── conversation.html
│       │   └── static/
│       │       └── css/        # Tailwind ビルド先
│       └── llm/                # Phase 4 で追加
│           ├── __init__.py
│           ├── embeddings.py
│           └── mcp_server.py
├── tests/
│   ├── fixtures/               # サンプル JSONL
│   ├── test_parser.py
│   ├── test_scanner.py
│   └── test_search.py
└── tailwind.config.js
```

## URL 設計

| URL                                                   | 説明                         |
| ----------------------------------------------------- | ---------------------------- |
| `/`                                                   | ユーザー一覧                 |
| `/users/{user}`                                       | ユーザーのプロジェクト一覧   |
| `/users/{user}/projects/{project}`                    | プロジェクトのセッション一覧 |
| `/users/{user}/projects/{project}/sessions/{session}` | 会話表示                     |
| `/search?q=...&user=...`                              | 全文検索                     |
| `/api/...`                                            | JSON API (HTMX からも叩く)   |

## NAS のパス解決ルール

環境変数 `CC_NAS_ROOT` で NAS ルートを指定する。デフォルト: `/mnt/shared-ai3-01/private-share`

ユーザー一覧の取得:

```
{CC_NAS_ROOT}/*/claude-logs/projects/
                ↑
              これがユーザー名
```

セッションファイル:

```
{CC_NAS_ROOT}/<user>/claude-logs/projects/<project-encoded>/<session-uuid>.jsonl
```

`<project-encoded>` は Claude Code がプロジェクトの絶対パスを `-` 区切りにエンコードしたもの。
例: `/Users/alice/myapp` → `-Users-alice-myapp`

## キャッシュ DB スキーマ (SQLite)

```sql
-- ユーザー・プロジェクト・セッションのメタデータ
CREATE TABLE sessions (
  id TEXT PRIMARY KEY,           -- session UUID
  user TEXT NOT NULL,
  project TEXT NOT NULL,         -- エンコード済みのプロジェクトパス
  project_decoded TEXT,          -- デコード済みの元パス
  file_path TEXT NOT NULL,
  first_message_at TEXT,
  last_message_at TEXT,
  message_count INTEGER,
  custom_title TEXT,
  ai_title TEXT,
  indexed_at TEXT NOT NULL       -- 最終インデックス時刻
);

CREATE INDEX idx_sessions_user_project ON sessions(user, project);
CREATE INDEX idx_sessions_last_message ON sessions(last_message_at DESC);

-- メッセージ全文検索
CREATE VIRTUAL TABLE messages_fts USING fts5(
  session_id UNINDEXED,
  user UNINDEXED,
  uuid UNINDEXED,
  role,                          -- user / assistant / system
  text,
  timestamp UNINDEXED,
  tokenize = 'unicode61'
);

-- Phase 4 で追加するベクトルテーブル (vec0 拡張 or 別ファイル)
-- CREATE VIRTUAL TABLE message_embeddings USING vec0(...);
```

DB のパスは `CC_CACHE_DIR` 環境変数で指定。デフォルト `~/.cache/cc-history-viewer/cache.db`。

**重要**: SQLite は必ずローカルディスク。NAS 上に置くと NFS/SMB のロック挙動でエラーになる。

## 設定 (環境変数)

| 変数               | デフォルト                         | 説明                             |
| ------------------ | ---------------------------------- | -------------------------------- |
| `CC_NAS_ROOT`      | `/mnt/shared-ai3-01/private-share` | NAS のルートディレクトリ         |
| `CC_CACHE_DIR`     | `~/.cache/cc-history-viewer`       | SQLite キャッシュの置き場        |
| `CC_HOST`          | `0.0.0.0`                          | bind するホスト                  |
| `CC_PORT`          | `8000`                             | ポート                           |
| `CC_AUTH_PASSWORD` | なし                               | 設定するとパスワード認証を有効化 |
| `CC_LOG_LEVEL`     | `INFO`                             | ログレベル                       |

## セキュリティとアクセス制御

- Phase 1〜3 は単一パスワード認証のみ (環境変数 `CC_AUTH_PASSWORD`)
- 本格的なマルチユーザー認証 (OAuth, OIDC) はリバースプロキシ層で対応する想定
- 「他人の履歴を見られるか」は閲覧者の信頼レベルで運用する (Phase 5 で RBAC 検討)
