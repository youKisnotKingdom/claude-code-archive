# Claude Code JSONL スキーマリファレンス

Claude Code は各セッションを JSONL (JSON Lines) 形式で保存する。
1 行 = 1 つの JSON オブジェクト (1 イベント) で、append-only に書き込まれる。

このドキュメントは `claude-code-viewer` (TypeScript / Zod) のスキーマ定義を読み解いたもの。
Python 側では Pydantic v2 で同等の構造を実装する。

## 基本構造

各行のオブジェクトは `type` フィールドで判別する判別ユニオン。

### 共通フィールド (BaseEntry)

ほぼすべてのエントリが持つ:

```python
{
  "type": "<エントリ種別>",
  "sessionId": "uuid",
  "uuid": "uuid",                  # このメッセージの ID
  "parentUuid": "uuid" | None,     # 親メッセージの ID (チェーン構造)
  "timestamp": "ISO 8601",
  "userType": "external" | None,
  "isMeta": bool | None,
  "isSidechain": bool | None,      # サブエージェント呼び出しか
  "cwd": str | None,
  "version": str | None,           # Claude Code バージョン
  "gitBranch": str | None
}
```

## エントリ種別 (15 種)

| type                    | 説明                                             |
| ----------------------- | ------------------------------------------------ |
| `user`                  | ユーザーメッセージ                               |
| `assistant`             | Claude の返答                                    |
| `system`                | システムイベント (`compact_boundary` などはここ) |
| `summary`               | コンパクション時の要約                           |
| `file-history-snapshot` | ファイル変更のスナップショット                   |
| `queue-operation`       | 実行キューの操作                                 |
| `progress`              | 進捗イベント                                     |
| `custom-title`          | ユーザーが設定したタイトル                       |
| `ai-title`              | AI が自動生成したタイトル                        |
| `agent-name`            | エージェント名の記録                             |
| `agent-setting`         | エージェント設定                                 |
| `permission-mode`       | 権限モードの変更                                 |
| `pr-link`               | PR との紐付け                                    |
| `last-prompt`           | 最後のプロンプト記録                             |
| `attachment`            | 添付ファイル                                     |

最低限 Phase 1 で扱うのは `user`, `assistant`, `system`, `summary`, `custom-title`, `ai-title`。
それ以外は読み飛ばしても表示は成立する (`extra="allow"` で素通し)。

## メッセージの中身

`user` と `assistant` の `message` フィールドは Anthropic Messages API と同形式。

### UserMessage

```python
{
  "role": "user",
  "content": str | list[ContentBlock]
}
```

### AssistantMessage

```python
{
  "id": str,
  "type": "message",
  "role": "assistant",
  "model": str,
  "content": list[ContentBlock],
  "stop_reason": str | None,
  "stop_sequence": str | None,
  "usage": { ... }
}
```

## ContentBlock (7 種)

`content` 配列の各要素。`type` で判別。

### 1. TextContent

```python
{"type": "text", "text": str}
```

### 2. ThinkingContent

```python
{"type": "thinking", "thinking": str, "signature": str | None}
```

### 3. ToolUseContent

```python
{
  "type": "tool_use",
  "id": str,
  "name": str,         # "Bash", "Read", "Edit", "Write", "Grep", "WebFetch", ...
  "input": dict        # ツールごとに構造が違う
}
```

### 4. ToolResultContent

```python
{
  "type": "tool_result",
  "tool_use_id": str,
  "content": str | list[TextContent | ImageContent],
  "is_error": bool | None
}
```

### 5. ToolReferenceContent

```python
{"type": "tool_reference", "name": str}
```

### 6. ImageContent

```python
{
  "type": "image",
  "source": {
    "type": "base64",
    "media_type": "image/png" | "image/jpeg" | "image/gif" | "image/webp",
    "data": str
  }
}
```

### 7. DocumentContent

```python
{
  "type": "document",
  "source": {
    "type": "text" | "base64",
    "media_type": "text/plain" | "application/pdf",
    "data": str
  }
}
```

## 特殊エントリ

### SummaryEntry

```python
{
  "type": "summary",
  "summary": str,
  "leafUuid": str
}
```

セッションをまたぐリンクとして使われる。

### SystemEntry + compact_boundary

コンテキスト圧縮時に書かれる特殊レコード:

```python
{
  "type": "system",
  "subtype": "compact_boundary",
  "sessionId": "...",
  "timestamp": "...",
  "uuid": "...",
  "logicalParentUuid": "...",  # 圧縮前の最後のメッセージ
  "parentUuid": None,           # チェーンがリセットされる
  "content": "Conversation compacted",
  "compactMetadata": {
    "trigger": "auto" | "manual",
    "preTokens": int
  }
}
```

複数 JSONL ファイルにまたがる会話を再構成するには、これを境界としてセッションチェーンを辿る必要がある。

## 親子関係 (parentUuid チェーン)

各レコードの `parentUuid` は前のレコードの `uuid` を指す連結リスト構造。
これを辿ると会話の時系列順序が再構成できる。

`compact_boundary` で `parentUuid` がリセットされる点に注意。

## パース戦略 (Phase 1)

```python
from pydantic import BaseModel, ConfigDict, Field
from typing import Literal, Union, Annotated

class BaseEntry(BaseModel):
    model_config = ConfigDict(extra="allow")  # 未知フィールドは保持

    type: str
    sessionId: str | None = None
    uuid: str | None = None
    parentUuid: str | None = None
    timestamp: str | None = None

# Phase 1: 表示に必要な最低限だけ厳密に
class UserEntry(BaseEntry):
    type: Literal["user"]
    message: dict  # 中身は Phase 2 で構造化

class AssistantEntry(BaseEntry):
    type: Literal["assistant"]
    message: dict

# 判別ユニオン
ConversationEntry = Annotated[
    Union[UserEntry, AssistantEntry, ...],
    Field(discriminator="type")
]
```

パース失敗時は `ErrorEntry` を返して 1 行ずつエラーをハンドリングする (claude-code-viewer の方針を踏襲)。

```python
class ErrorEntry(BaseModel):
    type: Literal["x-error"] = "x-error"
    line: str
    line_number: int
    error: str
```

## 参考実装

`claude-code-viewer` の以下のファイル群に Zod スキーマ定義がある。Pydantic 移植時の参照に。

- `src/lib/conversation-schema/index.ts` (ユニオンのトップ)
- `src/lib/conversation-schema/entry/*.ts` (15 種のエントリ)
- `src/lib/conversation-schema/content/*.ts` (7 種のコンテンツブロック)
- `src/lib/conversation-schema/message/{User,Assistant}MessageSchema.ts`
- `src/lib/conversation-schema/tool/*.ts` (各ツールの input/result スキーマ)
- `src/server/core/claude-code/functions/parseJsonl.ts` (パース本体)
