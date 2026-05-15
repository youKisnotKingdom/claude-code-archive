from typing import Any, Literal, TypeAlias

from pydantic import BaseModel, ConfigDict, Field


class ContentBase(BaseModel):
    model_config = ConfigDict(extra="allow")

    type: str


class TextContent(ContentBase):
    type: Literal["text"]
    text: str


class ThinkingContent(ContentBase):
    type: Literal["thinking"]
    thinking: str
    signature: str | None = None


class ToolUseContent(ContentBase):
    type: Literal["tool_use"]
    id: str
    name: str
    input: dict[str, Any] = Field(default_factory=dict)


class ToolReferenceContent(ContentBase):
    type: Literal["tool_reference"]
    name: str | None = None
    tool_name: str | None = None


class Base64Source(BaseModel):
    model_config = ConfigDict(extra="allow")

    type: Literal["base64"]
    media_type: str
    data: str


class DocumentSource(BaseModel):
    model_config = ConfigDict(extra="allow")

    type: Literal["text", "base64"]
    media_type: str
    data: str


class ImageContent(ContentBase):
    type: Literal["image"]
    source: Base64Source


class DocumentContent(ContentBase):
    type: Literal["document"]
    source: DocumentSource


class UnknownContent(ContentBase):
    """Content block not modeled yet. Kept losslessly for forward compatibility."""


ToolResultChildContent: TypeAlias = TextContent | ImageContent | DocumentContent | UnknownContent


class ToolResultContent(ContentBase):
    type: Literal["tool_result"]
    tool_use_id: str
    content: str | list[ToolResultChildContent] | None = None
    is_error: bool | None = None


ContentBlock: TypeAlias = (
    TextContent
    | ThinkingContent
    | ToolUseContent
    | ToolResultContent
    | ToolReferenceContent
    | ImageContent
    | DocumentContent
    | UnknownContent
)
UserContentBlock: TypeAlias = str | TextContent | ToolResultContent | ImageContent | DocumentContent
QueueOperationContentBlock: TypeAlias = (
    str | TextContent | ToolResultContent | ImageContent | DocumentContent
)
