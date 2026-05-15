# これまでの調査ログ

新規実装を始める前に、既に試したこと・学んだことをまとめておく。
Codex に渡す際の前提知識として参照してほしい。

## 試したこと

### 1. シンボリックリンクで JSONL を共有する案

各ユーザーの `~/.claude/projects` を NAS 上のディレクトリにシンボリックリンクする方法を検討した。
動くが、設定ファイルや認証情報もまとめて扱える `CLAUDE_CONFIG_DIR` の方がシンプルなので採用しなかった。

### 2. CLAUDE_CONFIG_DIR で NAS に向ける (採用)

各ユーザーの `.bashrc` / `.zshrc` に:

```bash
export CLAUDE_CONFIG_DIR=/mnt/shared-ai3-01/private-share/$USER/claude-logs
```

を追加。これで Claude Code のすべての状態 (projects/, history.jsonl, settings.json, .credentials.json など) が NAS に保存される。
NAS 上で書き込まれた瞬間に他のマシンからも見える。

### 3. claude-code-viewer (TypeScript) をフォークして改造

公式の `d-kimuson/claude-code-viewer` を試した。

**動かす上で詰まったポイント:**

| 問題                                      | 解決策                                                                                                             |
| ----------------------------------------- | ------------------------------------------------------------------------------------------------------------------ |
| Node.js v22 系では動かない                | nvm で v24 をインストール                                                                                          |
| `npm install` が依存解決失敗              | このリポジトリは **pnpm 専用**。`.npmrc` の `manage-package-manager-versions=true` が手がかり                      |
| `pnpm install` で `ERR_PNPM_MISSING_TIME` | ストアキャッシュ削除 + lockfile 削除で解決した                                                                     |
| Vite が Bus error (core dumped)           | npm で入れていた node_modules が壊れていた。pnpm でクリーンインストールしたら直った                                |
| SQLite が「database is locked」で起動失敗 | DrizzleService がキャッシュ DB を `CLAUDE_CONFIG_DIR` の親 (= NAS 上) に作っていた。SQLite は NFS/SMB と相性が悪い |

**SQLite ロック問題の修正パッチ** (`src/server/lib/db/DrizzleService.ts`):

```typescript
// 修正前
const dbDirPath = path.resolve(homeDirectory, ".claude-code-viewer");

// 修正後
const dbDirPath = process.env["CCV_CACHE_DIR"]
  ? path.resolve(process.env["CCV_CACHE_DIR"])
  : path.resolve(homeDirectory, ".claude-code-viewer");
```

そして `.env.local` に `CCV_CACHE_DIR=/home/<user>/.cache/claude-code-viewer` を追加するとローカルディスクに退避できる。

→ この経験から **「SQLite は絶対に NAS に置かない」が新規実装の鉄則** であることが分かった。

### 4. 結論: Python で書き直すことにした

claude-code-viewer は機能豊富だが、

- React + TanStack Router + Effect-ts + Drizzle + Vite + Lingui + Radix UI + PWA というスタックの大きさ
- 単一ユーザー前提の設計 (`CCV_GLOBAL_CLAUDE_DIR` が 1 パス固定)
- マルチユーザー対応は公式に「リバースプロキシでやれ」のスタンス
- LLM 二次処理 (embedding, RAG, 要約) は Python の方が圧倒的に有利

を理由に、Pythonスタックで一から書き直すことを決めた。
ただし、Zod スキーマ定義は丁寧に作り込まれているので、Pydantic 移植時の参照元として活用する。

## 学んだ JSONL の仕様

- **append-only**: Claude Code がセッション中に追記し続ける。viewer 側は read-only 前提
- **30 日で自動削除**: デフォルト設定。`cleanupPeriodDays` で延長可能
- **type フィールドで判別**: 15 種類のエントリ型のユニオン (詳細は `JSONL_SCHEMA.md`)
- **parentUuid でチェーン**: 各レコードが前のレコードを指す連結リスト
- **compact_boundary でリセット**: コンテキスト圧縮時に書かれる特殊レコードでチェーンが切れる
- **プロジェクト名はエンコード済み**: `/Users/alice/myapp` → `-Users-alice-myapp` の形でディレクトリ名になっている

## 環境情報 (参考)

| 項目                   | 値                                                |
| ---------------------- | ------------------------------------------------- |
| OS                     | Ubuntu (x86_64, GLIBC 2.39)                       |
| NAS マウント           | `/mnt/shared-ai3-01/private-share/` (SMB or NFS)  |
| Claude Code 実行モデル | オンプレ vLLM ホスト ( `ANTHROPIC_BASE_URL` 経由) |
| 開発マシンのメモリ     | 108 GB (十分)                                     |

## 参考リソース

- claude-code-viewer: https://github.com/d-kimuson/claude-code-viewer
- Claude Code 公式 .claude ディレクトリ仕様: https://code.claude.com/docs/en/claude-directory
- Claude Code セッション JSONL の解説: https://blog.fsck.com/releases/2026/02/22/claude-code-session-continuation/
