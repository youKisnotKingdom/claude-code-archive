import json
from collections.abc import Iterator
from pathlib import Path
from typing import TypeAlias

from pydantic import ValidationError

from cc_history.schema import (
    AiTitleEntry,
    AgentNameEntry,
    AgentSettingEntry,
    AssistantEntry,
    AttachmentEntry,
    CustomTitleEntry,
    ErrorEntry,
    FileHistorySnapshotEntry,
    LastPromptEntry,
    PermissionModeEntry,
    PrLinkEntry,
    ProgressEntry,
    QueueOperationEntry,
    SummaryEntry,
    SystemEntry,
    UnknownEntry,
    UserEntry,
)
from cc_history.schema.entry import BaseEntry

ParsedEntry: TypeAlias = (
    UserEntry
    | AssistantEntry
    | SystemEntry
    | SummaryEntry
    | CustomTitleEntry
    | AiTitleEntry
    | FileHistorySnapshotEntry
    | QueueOperationEntry
    | ProgressEntry
    | AgentNameEntry
    | AgentSettingEntry
    | PermissionModeEntry
    | PrLinkEntry
    | LastPromptEntry
    | AttachmentEntry
    | UnknownEntry
    | ErrorEntry
)

_TYPE_MAP = {
    "user": UserEntry,
    "assistant": AssistantEntry,
    "system": SystemEntry,
    "summary": SummaryEntry,
    "custom-title": CustomTitleEntry,
    "ai-title": AiTitleEntry,
    "file-history-snapshot": FileHistorySnapshotEntry,
    "queue-operation": QueueOperationEntry,
    "progress": ProgressEntry,
    "agent-name": AgentNameEntry,
    "agent-setting": AgentSettingEntry,
    "permission-mode": PermissionModeEntry,
    "pr-link": PrLinkEntry,
    "last-prompt": LastPromptEntry,
    "attachment": AttachmentEntry,
}


def parse_jsonl_line(line: str, line_number: int) -> ParsedEntry:
    """Parse one JSONL line into the best Phase 1 entry model."""
    try:
        data = json.loads(line)
    except json.JSONDecodeError as error:
        return ErrorEntry(line=line, line_number=line_number, error=f"JSONDecode: {error}")

    if not isinstance(data, dict):
        return ErrorEntry(line=line, line_number=line_number, error="not a JSON object")

    type_value = data.get("type")
    model: type[BaseEntry] = _TYPE_MAP.get(type_value, UnknownEntry)

    try:
        return model.model_validate(data)
    except ValidationError as error:
        return ErrorEntry(line=line, line_number=line_number, error=f"Validation: {error}")


def parse_jsonl_file(path: Path) -> Iterator[ParsedEntry]:
    """Yield parsed entries from a JSONL file without modifying the source file."""
    with path.open("r", encoding="utf-8") as file:
        for line_number, raw_line in enumerate(file, start=1):
            line = raw_line.strip()
            if not line:
                continue
            yield parse_jsonl_line(line, line_number)
