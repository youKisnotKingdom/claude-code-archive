# Claude Code History Viewer & Knowledge Manager (仮称)

複数ユーザーの Claude Code 会話履歴 (JSONL) を NAS 上で一元管理し、
さらに**履歴から経験知を抽出して新しいセッションで再利用する**ためのプラットフォーム。

## 背景

- 社内では Claude Code をオンプレ環境 (vLLM 経由) で運用している
- 各ユーザーは `CLAUDE_CONFIG_DIR` を NAS 上のディレクトリに向けて使う設定済み
  - 例: `CLAUDE_CONFIG_DIR=/mnt/shared-ai3-01/private-share/$USER/claude-logs`
- これにより `/mnt/shared-ai3-01/private-share/<user>/claude-logs/projects/**/*.jsonl` に各ユーザーのセッション履歴が常時書き込まれている
- 既存ツール (claude-code-viewer 等) は単一ユーザーの `~/.claude` を見る前提で、複数ユーザー横断や知見抽出には対応していない

## このプロジェクトの 2 つの柱

### 柱 A: 履歴ビューア (Phase 1〜3)

**多人数の Claude Code 履歴を 1 箇所で見られるようにする。**

- マルチユーザー横断の閲覧・検索
- セッション・プロジェクト・ユーザー単位のドリルダウン
- ツール呼び出しや差分の見やすい表示

### 柱 B: ナレッジ管理 (Phase 4〜7)

**履歴を「経験知」として蓄積し、新しいセッションで活用する。**

- 手動でのタグ付け・メモ・お気に入り (Phase 4)
- LLM による自動要約・パターン抽出 (Phase 5)
- プロジェクト単位の `AGENT.md` / `CLAUDE.md` 自動生成 (Phase 6)
- 新しい Claude Code セッションへのコンテキスト注入 (Phase 7, MCP 経由)

最終的に「過去の自分・チームの経験を踏まえて作業する Claude Code」を実現する。

## 技術スタック

- **バックエンド**: Python 3.11+ / FastAPI / Pydantic v2
- **フロントエンド**: Jinja2 + HTMX + Tailwind CSS
- **DB (キャッシュ・検索・ナレッジ)**: SQLite + FTS5 → 必要に応じて PostgreSQL + pgvector
- **JSONL ソース**: NAS 上の `/mnt/shared-ai3-01/private-share/<user>/claude-logs/projects/`
- **LLM (Phase 5 以降)**: オンプレ vLLM (Claude 互換) / sentence-transformers / Ollama
- **MCP サーバー (Phase 7)**: Anthropic 公式 Python SDK

## なぜこの構成か

参考実装である `claude-code-viewer` (TypeScript / React / Effect-ts / Drizzle) は機能豊富だが、

- 依存ツリーが大規模で改造コストが高い
- マルチユーザーは「リバースプロキシ層で対応を」として未実装
- 後段の LLM 処理 (embedding, RAG, 要約) は Python エコシステムの方が圧倒的に有利
- ナレッジ管理という独自方向に伸ばすには Python の方が研究系ライブラリと馴染む

そのため JSONL スキーマ定義など参考にすべき部分は流用しつつ、Python ベースで書き直す。

## 重要な制約

- **SQLite は NAS 上に置かない**: ロックの挙動が壊れる (NFS/SMB の既知問題)。キャッシュ DB はローカルディスクに置く
- **JSONL は read-only**: 元データは Claude Code が常時書き込み中なので、append-only として扱い、こちらからは絶対に書き換えない
- **30 日自動削除に注意**: Claude Code はデフォルトで JSONL を 30 日後に削除する。長期保存したい場合は別途アーカイブが必要 (Phase 7 で対応予定)
- **LLM 抽出はトレース可能に**: 自動生成された知見は必ず元セッションへの出典リンクを保持する
- **人間がループに入れる**: 自動抽出 → 提案 → 人間が承認、の流れを基本とする

## ドキュメント構成

| ファイル                   | 役割                                              |
| -------------------------- | ------------------------------------------------- |
| `README.md` (このファイル) | プロジェクト全体像と思想                          |
| `CONTEXT.md`               | これまでに試したこと・詰まったポイント (前提知識) |
| `CURRENT_STATUS.md`        | 現在の実装状況・検証結果・次の推奨作業            |
| `ARCHITECTURE.md`          | 詳細な設計・ディレクトリ構造・DB スキーマ         |
| `JSONL_SCHEMA.md`          | Claude Code JSONL のデータ構造リファレンス        |
| `ROADMAP.md`               | Phase 1〜7 の段階的実装計画                       |
| `PHASE1_TASKS.md`          | 最初に着手する MVP の具体的タスク                 |
| `KNOWLEDGE_EXTRACTION.md`  | ナレッジ抽出・再利用の研究設計                    |
| `AGENT_CONTEXT_HANDOFF.md` | AGENT に渡す文脈パックの手順・UI 設計             |

## 進め方

1. `CONTEXT.md` を読んで前提を把握
2. `ROADMAP.md` で全体像を理解
3. `CURRENT_STATUS.md` で現在の実装済み範囲を確認する
4. Phase 4 以降は `KNOWLEDGE_EXTRACTION.md` と
   `AGENT_CONTEXT_HANDOFF.md` も併せて読む
