from pathlib import Path

from cc_history.schema import (
    AgentNameEntry,
    AgentSettingEntry,
    AssistantEntry,
    AttachmentEntry,
    ErrorEntry,
    FileHistorySnapshotEntry,
    LastPromptEntry,
    PermissionModeEntry,
    PrLinkEntry,
    ProgressEntry,
    QueueOperationEntry,
    UnknownEntry,
    UserEntry,
)
from cc_history.services.parser import parse_jsonl_file, parse_jsonl_line


def test_parse_valid_jsonl_fixture() -> None:
    entries = list(parse_jsonl_file(Path("tests/fixtures/sample_session.jsonl")))

    assert len(entries) == 4
    assert any(isinstance(entry, UserEntry) for entry in entries)
    assert any(isinstance(entry, AssistantEntry) for entry in entries)
    errors = [entry for entry in entries if isinstance(entry, ErrorEntry)]
    assert len(errors) == 0


def test_parse_broken_line(tmp_path: Path) -> None:
    file_path = tmp_path / "broken.jsonl"
    file_path.write_text(
        '{"type": "user", "message": {"role": "user", "content": "hello"}}\nthis is not json\n',
        encoding="utf-8",
    )

    entries = list(parse_jsonl_file(file_path))

    assert len(entries) == 2
    assert isinstance(entries[0], UserEntry)
    assert isinstance(entries[1], ErrorEntry)
    assert entries[1].line_number == 2


def test_parse_unknown_type_preserves_extra_fields() -> None:
    entry = parse_jsonl_line('{"type":"new-type","extraValue":42}', 1)

    assert isinstance(entry, UnknownEntry)
    assert entry.type == "new-type"
    assert entry.model_extra == {"extraValue": 42}


def test_parse_non_object_line_returns_error() -> None:
    entry = parse_jsonl_line('["not", "object"]', 3)

    assert isinstance(entry, ErrorEntry)
    assert entry.line_number == 3
    assert entry.error == "not a JSON object"


def test_parse_all_known_non_message_entry_types() -> None:
    examples = [
        (
            '{"type":"file-history-snapshot","messageId":"m1","snapshot":{"messageId":"m1","trackedFileBackups":{},"timestamp":"2026-05-14T00:00:00Z"},"isSnapshotUpdate":false}',
            FileHistorySnapshotEntry,
        ),
        (
            '{"type":"queue-operation","operation":"enqueue","sessionId":"s1","timestamp":"2026-05-14T00:00:00Z","content":"queued"}',
            QueueOperationEntry,
        ),
        (
            '{"type":"progress","data":{"status":"running"},"toolUseID":"tool-1"}',
            ProgressEntry,
        ),
        (
            '{"type":"agent-name","agentName":"reviewer","sessionId":"s1"}',
            AgentNameEntry,
        ),
        (
            '{"type":"agent-setting","agentSetting":"default","sessionId":"s1"}',
            AgentSettingEntry,
        ),
        (
            '{"type":"permission-mode","permissionMode":"default","sessionId":"s1"}',
            PermissionModeEntry,
        ),
        (
            '{"type":"pr-link","sessionId":"s1","prNumber":12,"prUrl":"https://example.test/pr/12","prRepository":"owner/repo","timestamp":"2026-05-14T00:00:00Z"}',
            PrLinkEntry,
        ),
        (
            '{"type":"last-prompt","lastPrompt":"continue","sessionId":"s1"}',
            LastPromptEntry,
        ),
        (
            '{"type":"attachment","attachment":{"type":"file","filename":"README.md","displayPath":"README.md","content":{"type":"text","file":{"filePath":"README.md","content":"hello","numLines":1,"startLine":1,"totalLines":1}}}}',
            AttachmentEntry,
        ),
    ]

    for line, expected_type in examples:
        entry = parse_jsonl_line(line, 1)
        assert isinstance(entry, expected_type)
