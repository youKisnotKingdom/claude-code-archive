# ロードマップ

このプロジェクトは 2 つの柱で構成される:

- **柱 A: 履歴ビューア** — JSONL を読み・整理し・検索する基盤
- **柱 B: ナレッジ管理** — 履歴からパターン・知見を抽出し、再利用できるようにする

各柱は独立して価値を持ち、後で組み合わせる構造。

```
┌─────────────────────────────────────────────────────────┐
│ 柱 A: 履歴ビューア                                       │
│   Phase 1 → 2 → 3                                       │
│   (MVP, 詳細表示+検索, マルチユーザー)                    │
└──────────────────┬──────────────────────────────────────┘
                   │ 履歴データを供給
                   ▼
┌─────────────────────────────────────────────────────────┐
│ 柱 B: ナレッジ管理                                       │
│   Phase 4 → 5 → 6 → 7                                   │
│   (整理基盤, 自動抽出, 再利用, MCP/SDK 連携)              │
└─────────────────────────────────────────────────────────┘
```

実装は各フェーズが独立して動作する状態で完了させる (= 動くものをまず作って育てる)。

---

## 柱 A: 履歴ビューア

### Phase 1: MVP — JSONL を読んで表示する

**目標**: 単一ユーザーの JSONL を読み込み、ブラウザで会話を閲覧できる。

含むもの:

- FastAPI プロジェクト雛形
- Pydantic で JSONL の最小スキーマ
- パース失敗時のエラーエントリハンドリング
- NAS 上の `projects/` をスキャンしてセッション一覧を返す
- セッション JSONL をパースして HTML で表示
- Jinja2 + Tailwind + HTMX の最小 UI

完了条件:

- ユーザー → プロジェクト → セッション → 会話 のドリルダウンが動く
- ツール呼び出しは最低限「Tool: Bash」のような表示で OK

詳細: `PHASE1_TASKS.md`

### Phase 2: 詳細表示 + 検索

**目標**: ContentBlock を完全に表示し、全文検索を実装する。

含むもの:

- ContentBlock の 7 種を Pydantic で判別ユニオン化
- ツール呼び出しの整形表示 (Bash・編集差分・ファイル読み込み)
- Thinking ブロックの折りたたみ
- 画像 (base64) のインライン表示
- SQLite + FTS5 で全文検索
- 検索 UI (HTMX でインクリメンタル検索)
- インデックスの差分更新

### Phase 3: マルチユーザー対応の完成

**目標**: 複数ユーザーの履歴を区別しつつ横断的に扱える。

含むもの:

- NAS の `/private-share/*/claude-logs/` を自動スキャン
- ユーザー切り替え UI
- ユーザーフィルタ付き検索
- セッションメタデータの集計表示
- パスワード認証
- ファイル監視で新セッションを自動検知 (watchdog)

完了条件:

- ユーザー A の履歴と B の履歴が明確に区別される
- 新規ユーザー・新規セッションが再起動なしで認識される

---

## 柱 B: ナレッジ管理

### Phase 4: 整理基盤 (タグ付け・メモ・お気に入り)

**目標**: ユーザーが履歴を「自分の使える状態」にできる UI と DB を整える。
自動化はせず、まず手動で整理できる土台を作る。

含むもの:

- セッションへのタグ付け (複数タグ可)
- セッション単位のメモ機能 (後付けで追記)
- お気に入りフラグ・アーカイブフラグ
- セッションタイトルの手動編集
- タグ・メモのフルテキスト検索
- タグでの絞り込み UI

DB 追加テーブル:

```sql
CREATE TABLE session_annotations (
  session_id TEXT PRIMARY KEY,
  user TEXT NOT NULL,            -- 注釈の所有者
  manual_title TEXT,
  note TEXT,
  is_favorite INTEGER DEFAULT 0,
  is_archived INTEGER DEFAULT 0,
  updated_at TEXT NOT NULL
);

CREATE TABLE session_tags (
  session_id TEXT NOT NULL,
  tag TEXT NOT NULL,
  source TEXT NOT NULL,          -- 'manual' | 'auto' | 'suggested'
  confidence REAL,               -- auto/suggested の確信度
  created_at TEXT NOT NULL,
  PRIMARY KEY (session_id, tag)
);

CREATE INDEX idx_tags_tag ON session_tags(tag);
```

完了条件:

- セッション一覧でタグ・お気に入り・アーカイブ状態が見える
- タグで絞り込んで一覧できる
- セッション詳細画面からタグ・メモを編集できる

### Phase 5: 自動ナレッジ抽出

**目標**: LLM を使って履歴から構造化された知見を抽出する。
ここから先は研究的要素が大きい。詳細は `KNOWLEDGE_EXTRACTION.md` を参照。

含むもの:

- セッション要約の自動生成 (LLM)
- タグ自動候補 (LLM が `suggested` として提案、ユーザーが承認すると `manual` に昇格)
- セッション内のキーアーティファクト抽出
  - 解決した問題 / 採用したアプローチ / 試して捨てた案
  - 使ったコマンド / 触ったファイル / 学んだこと
- メッセージ単位の embedding 化 (sentence-transformers or Ollama)
- セッション類似度検索 (「これに似た過去セッション」)
- プロジェクト単位の知見ロールアップ (複数セッションを跨いだ要約)

DB 追加:

```sql
CREATE TABLE session_summaries (
  session_id TEXT PRIMARY KEY,
  one_liner TEXT,                -- 1 行サマリ
  detailed_summary TEXT,         -- 段落単位のサマリ
  problems_solved TEXT,          -- JSON: ["問題1", "問題2"]
  approaches_tried TEXT,         -- JSON
  artifacts TEXT,                -- JSON: 触ったファイル等
  model_used TEXT,
  generated_at TEXT NOT NULL
);

CREATE TABLE knowledge_items (
  id TEXT PRIMARY KEY,
  type TEXT NOT NULL,            -- 'pattern' | 'pitfall' | 'convention' | 'snippet'
  scope TEXT NOT NULL,           -- 'user' | 'project' | 'org'
  scope_id TEXT NOT NULL,        -- user 名 / project ID / 'global'
  title TEXT NOT NULL,
  body TEXT NOT NULL,
  source_sessions TEXT,          -- JSON: このアイテムの抽出元 session_id 配列
  status TEXT NOT NULL,          -- 'draft' | 'reviewed' | 'archived'
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
```

完了条件:

- 各セッションに自動で 1 行サマリが付く
- 「過去にこのバグを修正したか」が類似度検索で見つかる
- 抽出された `knowledge_items` を一覧・編集できる

### Phase 6: ナレッジ再利用 (AGENT.md 生成 / コンテキスト注入)

**目標**: 蓄積したナレッジを新しい Claude Code セッションで活用できる形に変換する。

含むもの:

- プロジェクト単位の `AGENT.md` / `CLAUDE.md` 自動生成
  - 規約・パターン・落とし穴・推奨コマンドをまとめた Markdown
  - ナレッジアイテムから動的に組み立て
- 「オンボーディング資料」生成 (新しく入った人向け)
- スニペット集の出力
- 任意のプロジェクトに対する `CLAUDE.md` の継続的な提案 (人間が承認して反映)
- ナレッジアイテムごとに「どのセッションから来たか」をトレース可能

UI:

- プロジェクトページに「AGENT.md をプレビュー / ダウンロード」ボタン
- 自動生成された Markdown を編集して保存できる
- 「最新のセッションを取り込んで AGENT.md を更新する」差分提案

完了条件:

- 任意のプロジェクトに対して使える `AGENT.md` を出力できる
- 内容が実際に「使える」レベルになっている (LLM の幻覚が混じっていない)
- ナレッジアイテムから AGENT.md へのトレースができる

### Phase 7: MCP / Agent SDK 連携

**目標**: 別の Claude Code セッションがこのアプリを直接参照できるようにする。

含むもの:

- MCP サーバー実装 (Anthropic Python SDK)
  - `list_sessions` / `search_messages` / `get_session_outline` / `get_messages` / `export_session`
  - `get_knowledge` / `search_knowledge` (Phase 5 で作ったナレッジを引く)
  - `get_agent_md` (Phase 6 の AGENT.md を返す)
- セッション開始時に自動でナレッジを注入する仕組み (SessionStart フック)
- バックアップ・アーカイブ機構 (30 日自動削除に備える)
- (オプション) RBAC: 誰が誰のナレッジを参照できるか

完了条件:

- 新しい Claude Code セッションが `mcp__cc-history__search_knowledge` で過去の知見を引ける
- 「このプロジェクトの過去の経験を踏まえて作業して」が動く

---

## フェーズを跨ぐ原則

1. **JSONL は read-only**: 元データを絶対に書き換えない
2. **SQLite はローカルディスクのみ**: NAS には絶対置かない
3. **パース失敗を許容**: 未知のフィールド・行は `extra="allow"` か `ErrorEntry` で素通り
4. **段階的型強化**: Phase 1 は dict で持ち、Phase 2 以降で構造化
5. **LLM 抽出はトレース可能に**: 生成された知見は必ず元セッションへのリンクを保持
6. **人間がループに入れる設計**: 自動抽出 → 提案 → 人間が承認、の流れを基本とする
7. **テストを書く**: 各フェーズで fixture JSONL を使った unit test を揃える

## 期間目安 (参考)

| Phase | 期間                 |
| ----- | -------------------- |
| 1     | 1〜2 日              |
| 2     | 3〜5 日              |
| 3     | 3〜5 日              |
| 4     | 3〜5 日              |
| 5     | 2〜3 週間 (研究込み) |
| 6     | 1〜2 週間            |
| 7     | 1〜2 週間            |
