from cc_history.schema import AssistantEntry, UserEntry
from cc_history.schema.content import (
    DocumentContent,
    ImageContent,
    TextContent,
    ThinkingContent,
    ToolReferenceContent,
    ToolResultContent,
    ToolUseContent,
)
from cc_history.services.parser import parse_jsonl_line


def test_parse_assistant_content_blocks() -> None:
    line = """
    {
      "type": "assistant",
      "message": {
        "id": "msg-1",
        "type": "message",
        "role": "assistant",
        "model": "claude",
        "content": [
          {"type": "text", "text": "hello"},
          {"type": "thinking", "thinking": "private reasoning", "signature": "sig"},
          {"type": "tool_use", "id": "tool-1", "name": "Bash", "input": {"command": "pytest"}},
          {"type": "tool_reference", "name": "Bash"},
          {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": "abc"}},
          {"type": "document", "source": {"type": "text", "media_type": "text/plain", "data": "doc"}}
        ]
      }
    }
    """

    entry = parse_jsonl_line(line, 1)

    assert isinstance(entry, AssistantEntry)
    content = entry.message.content
    assert isinstance(content, list)
    assert isinstance(content[0], TextContent)
    assert isinstance(content[1], ThinkingContent)
    assert isinstance(content[2], ToolUseContent)
    assert isinstance(content[3], ToolReferenceContent)
    assert isinstance(content[4], ImageContent)
    assert isinstance(content[5], DocumentContent)


def test_parse_user_tool_result_content_blocks() -> None:
    line = """
    {
      "type": "user",
      "message": {
        "role": "user",
        "content": [
          {
            "type": "tool_result",
            "tool_use_id": "tool-1",
            "content": [
              {"type": "text", "text": "result text"},
              {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": "xyz"}}
            ],
            "is_error": false
          }
        ]
      }
    }
    """

    entry = parse_jsonl_line(line, 1)

    assert isinstance(entry, UserEntry)
    content = entry.message.content
    assert isinstance(content, list)
    assert isinstance(content[0], ToolResultContent)
    result_content = content[0].content
    assert isinstance(result_content, list)
    assert isinstance(result_content[0], TextContent)
    assert isinstance(result_content[1], ImageContent)
