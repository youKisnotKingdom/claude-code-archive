from typing import Any, Literal

from pydantic import BaseModel, ConfigDict

from cc_history.schema.content import ContentBlock, UserContentBlock


class UserMessage(BaseModel):
    model_config = ConfigDict(extra="allow")

    role: Literal["user"]
    content: str | list[UserContentBlock]


class AssistantMessage(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: str | None = None
    type: Literal["message"] | str = "message"
    role: Literal["assistant"]
    model: str | None = None
    content: list[ContentBlock]
    stop_reason: str | None = None
    stop_sequence: str | None = None
    usage: dict[str, Any] | None = None
