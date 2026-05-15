from typing import Any, Literal

from pydantic import BaseModel, ConfigDict

from cc_history.schema.content import QueueOperationContentBlock
from cc_history.schema.message import AssistantMessage, UserMessage


class BaseEntry(BaseModel):
    """Shared fields for Claude Code JSONL entries. Unknown fields are preserved."""

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
    userType: str | None = None
    toolUseResult: Any = None
    agentId: str | None = None
    entrypoint: str | None = None
    slug: str | None = None
    isCompactSummary: bool | None = None


class UserEntry(BaseEntry):
    type: Literal["user"]
    message: UserMessage


class AssistantEntry(BaseEntry):
    type: Literal["assistant"]
    message: AssistantMessage
    requestId: str | None = None
    isApiErrorMessage: bool | None = None
    usage: dict[str, Any] | None = None


class SystemEntry(BaseEntry):
    type: Literal["system"]
    subtype: str | None = None
    content: str | None = None
    toolUseID: str | None = None
    level: str | None = None
    hookCount: int | None = None
    hookInfos: list[dict[str, Any]] | None = None
    hookErrors: list[Any] | None = None
    preventedContinuation: bool | None = None
    stopReason: str | None = None
    hasOutput: bool | None = None
    durationMs: int | None = None
    logicalParentUuid: str | None = None
    compactMetadata: dict[str, Any] | None = None
    error: dict[str, Any] | None = None
    retryInMs: int | None = None
    retryAttempt: int | None = None
    maxRetries: int | None = None


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


class FileHistorySnapshot(BaseModel):
    model_config = ConfigDict(extra="allow")

    messageId: str
    trackedFileBackups: dict[str, Any]
    timestamp: str


class FileHistorySnapshotEntry(BaseEntry):
    type: Literal["file-history-snapshot"]
    messageId: str
    snapshot: FileHistorySnapshot
    isSnapshotUpdate: bool


class QueueOperationEntry(BaseEntry):
    type: Literal["queue-operation"]
    operation: Literal["enqueue", "dequeue", "remove", "popAll"] | str
    content: str | list[QueueOperationContentBlock] | None = None


class ProgressEntry(BaseEntry):
    type: Literal["progress"]
    data: dict[str, Any]
    toolUseID: str | None = None
    parentToolUseID: str | None = None


class AgentNameEntry(BaseEntry):
    type: Literal["agent-name"]
    agentName: str


class AgentSettingEntry(BaseEntry):
    type: Literal["agent-setting"]
    agentSetting: str


class PermissionModeEntry(BaseEntry):
    type: Literal["permission-mode"]
    permissionMode: str


class PrLinkEntry(BaseEntry):
    type: Literal["pr-link"]
    prNumber: int
    prUrl: str
    prRepository: str


class LastPromptEntry(BaseEntry):
    type: Literal["last-prompt"]
    lastPrompt: str


class AttachmentPayload(BaseModel):
    model_config = ConfigDict(extra="allow")

    type: str


class AttachmentEntry(BaseEntry):
    type: Literal["attachment"]
    attachment: AttachmentPayload


class UnknownEntry(BaseEntry):
    """Entry with a type not modeled in Phase 1."""


class ErrorEntry(BaseModel):
    """Synthetic entry used when a JSONL line cannot be parsed."""

    type: Literal["x-error"] = "x-error"
    line: str
    line_number: int
    error: str
