from cc_history.schema import AssistantEntry, UserEntry
from cc_history.services.parser import parse_jsonl_line
from cc_history.services.rendering import (
    build_conversation_views,
    entry_to_view,
    extract_edited_files,
)


def test_render_tool_use_with_command_details() -> None:
    entry = parse_jsonl_line(
        """
        {
          "type": "assistant",
          "timestamp": "2026-05-14T00:00:00Z",
          "message": {
            "id": "msg-1",
            "type": "message",
            "role": "assistant",
            "model": "claude",
            "content": [
              {"type": "tool_use", "id": "tool-1", "name": "Bash", "input": {"command": "pytest", "description": "Run tests"}}
            ]
          }
        }
        """,
        1,
    )

    assert isinstance(entry, AssistantEntry)
    view = entry_to_view(entry)

    assert view["tools"][0]["name"] == "Bash"
    assert "pytest" in view["tools"][0]["body"]
    assert "Run tests" in view["tools"][0]["body"]
    assert view["tools"][0]["display"]["type"] == "bash"
    assert view["tools"][0]["display"]["command"] == "pytest"
    assert view["tools"][0]["display"]["description"] == "Run tests"


def test_render_edit_and_todo_tools_with_dedicated_display() -> None:
    entry = parse_jsonl_line(
        """
        {
          "type": "assistant",
          "message": {
            "id": "msg-1",
            "type": "message",
            "role": "assistant",
            "model": "claude",
            "content": [
              {
                "type": "tool_use",
                "id": "tool-1",
                "name": "Edit",
                "input": {
                  "file_path": "app.py",
                  "old_string": "print('old')",
                  "new_string": "print('new')"
                }
              },
              {
                "type": "tool_use",
                "id": "tool-2",
                "name": "TodoWrite",
                "input": {
                  "todos": [
                    {"content": "Implement renderer", "status": "in_progress", "priority": "high", "id": "1"}
                  ]
                }
              }
            ]
          }
        }
        """,
        1,
    )

    assert isinstance(entry, AssistantEntry)
    view = entry_to_view(entry)

    assert view["tools"][0]["display"]["type"] == "edit"
    assert view["tools"][0]["display"]["file_path"] == "app.py"
    assert view["tools"][0]["display"]["edits"][0]["old"] == "print('old')"
    assert view["tools"][1]["display"]["type"] == "todo"
    assert view["tools"][1]["display"]["todos"][0]["status"] == "in_progress"


def test_render_thinking_and_inline_image() -> None:
    entry = parse_jsonl_line(
        """
        {
          "type": "assistant",
          "message": {
            "id": "msg-1",
            "type": "message",
            "role": "assistant",
            "model": "claude",
            "content": [
              {"type": "thinking", "thinking": "hidden chain"},
              {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": "abc"}}
            ]
          }
        }
        """,
        1,
    )

    assert isinstance(entry, AssistantEntry)
    view = entry_to_view(entry)

    assert view["thinking"] == ["hidden chain"]
    assert view["images"][0]["data_uri"] == "data:image/png;base64,abc"


def test_render_tool_result_image() -> None:
    entry = parse_jsonl_line(
        """
        {
          "type": "user",
          "message": {
            "role": "user",
            "content": [
              {
                "type": "tool_result",
                "tool_use_id": "tool-1",
                "content": [
                  {"type": "text", "text": "plot generated"},
                  {"type": "image", "source": {"type": "base64", "media_type": "image/webp", "data": "xyz"}}
                ]
              }
            ]
          }
        }
        """,
        1,
    )

    assert isinstance(entry, UserEntry)
    view = entry_to_view(entry)

    assert view["texts"] == ["Tool result: plot generated"]
    assert view["images"][0]["data_uri"] == "data:image/webp;base64,xyz"


def test_build_conversation_views_attaches_tool_result_to_tool_use() -> None:
    assistant = parse_jsonl_line(
        """
        {
          "type": "assistant",
          "uuid": "assistant-1",
          "message": {
            "id": "msg-1",
            "type": "message",
            "role": "assistant",
            "model": "claude",
            "content": [
              {"type": "tool_use", "id": "tool-1", "name": "Bash", "input": {"command": "pytest"}}
            ]
          }
        }
        """,
        1,
    )
    tool_result = parse_jsonl_line(
        """
        {
          "type": "user",
          "uuid": "user-1",
          "message": {
            "role": "user",
            "content": [
              {"type": "tool_result", "tool_use_id": "tool-1", "content": "2 passed"}
            ]
          }
        }
        """,
        2,
    )

    views = build_conversation_views([assistant, tool_result])

    assert len(views) == 1
    assert views[0]["type"] == "assistant"
    assert views[0]["tools"][0]["result_texts"] == ["2 passed"]
    assert views[0]["tools"][0]["has_result"] is True


def test_build_conversation_views_structures_command_tool_result() -> None:
    assistant = parse_jsonl_line(
        """
        {
          "type": "assistant",
          "uuid": "assistant-1",
          "message": {
            "id": "msg-1",
            "type": "message",
            "role": "assistant",
            "model": "claude",
            "content": [
              {"type": "tool_use", "id": "tool-1", "name": "Bash", "input": {"command": "pytest"}}
            ]
          }
        }
        """,
        1,
    )
    tool_result = parse_jsonl_line(
        """
        {
          "type": "user",
          "uuid": "user-1",
          "toolUseResult": {
            "stdout": "2 passed",
            "stderr": "warning",
            "interrupted": false,
            "isImage": false
          },
          "message": {
            "role": "user",
            "content": [
              {"type": "tool_result", "tool_use_id": "tool-1", "content": "2 passed"}
            ]
          }
        }
        """,
        2,
    )

    views = build_conversation_views([assistant, tool_result])

    result_display = views[0]["tools"][0]["result_display"]
    assert result_display["type"] == "command"
    assert result_display["stdout"] == "2 passed"
    assert result_display["stderr"] == "warning"
    assert result_display["interrupted"] is False


def test_extract_edited_files_from_rendered_views() -> None:
    assistant = parse_jsonl_line(
        """
        {
          "type": "assistant",
          "timestamp": "2026-05-14T00:00:00Z",
          "message": {
            "id": "msg-1",
            "type": "message",
            "role": "assistant",
            "model": "claude",
            "content": [
              {"type": "tool_use", "id": "tool-1", "name": "Edit", "input": {"file_path": "/work/app.py", "old_string": "old", "new_string": "new"}},
              {"type": "tool_use", "id": "tool-2", "name": "Write", "input": {"file_path": "/work/new.py", "content": "print(1)"}}
            ]
          }
        }
        """,
        1,
    )

    views = build_conversation_views([assistant])
    edited_files = extract_edited_files(views, cwd="/work")

    assert edited_files == [
        {
            "file_path": "/work/app.py",
            "display_path": "app.py",
            "tool_name": "Edit",
            "tool_id": "tool-1",
            "timestamp": "2026-05-14T00:00:00Z",
            "is_external": False,
        },
        {
            "file_path": "/work/new.py",
            "display_path": "new.py",
            "tool_name": "Write",
            "tool_id": "tool-2",
            "timestamp": "2026-05-14T00:00:00Z",
            "is_external": False,
        },
    ]


def test_build_conversation_views_attaches_embedded_sidechain_to_task_tool() -> None:
    assistant = parse_jsonl_line(
        """
        {
          "type": "assistant",
          "uuid": "assistant-1",
          "message": {
            "id": "msg-1",
            "type": "message",
            "role": "assistant",
            "model": "claude",
            "content": [
              {"type": "tool_use", "id": "tool-1", "name": "Task", "input": {"prompt": "Review the parser"}}
            ]
          }
        }
        """,
        1,
    )
    sidechain_user = parse_jsonl_line(
        """
        {
          "type": "user",
          "uuid": "side-user-1",
          "parentUuid": null,
          "isSidechain": true,
          "message": {"role": "user", "content": "Review the parser"}
        }
        """,
        2,
    )
    sidechain_assistant = parse_jsonl_line(
        """
        {
          "type": "assistant",
          "uuid": "side-assistant-1",
          "parentUuid": "side-user-1",
          "isSidechain": true,
          "message": {
            "id": "msg-side-1",
            "type": "message",
            "role": "assistant",
            "model": "claude",
            "content": [{"type": "text", "text": "Parser looks good."}]
          }
        }
        """,
        3,
    )

    views = build_conversation_views([assistant, sidechain_user, sidechain_assistant])

    assert len(views) == 1
    subagent = views[0]["tools"][0]["subagent"]
    assert subagent["prompt"] == "Review the parser"
    assert subagent["message_count"] == 2
    assert subagent["entries"][1]["texts"] == ["Parser looks good."]


def test_build_conversation_views_attaches_agent_file_sidechain_by_agent_id() -> None:
    assistant = parse_jsonl_line(
        """
        {
          "type": "assistant",
          "uuid": "assistant-1",
          "message": {
            "id": "msg-1",
            "type": "message",
            "role": "assistant",
            "model": "claude",
            "content": [
              {"type": "tool_use", "id": "tool-1", "name": "Task", "input": {"prompt": "Check imports"}}
            ]
          }
        }
        """,
        1,
    )
    tool_result = parse_jsonl_line(
        """
        {
          "type": "user",
          "uuid": "user-1",
          "toolUseResult": {"agentId": "agent-1"},
          "message": {
            "role": "user",
            "content": [
              {"type": "tool_result", "tool_use_id": "tool-1", "content": "done"}
            ]
          }
        }
        """,
        2,
    )
    agent_user = parse_jsonl_line(
        """
        {
          "type": "user",
          "uuid": "agent-user-1",
          "parentUuid": null,
          "isSidechain": true,
          "agentId": "agent-1",
          "message": {"role": "user", "content": "Check imports"}
        }
        """,
        1,
    )
    agent_assistant = parse_jsonl_line(
        """
        {
          "type": "assistant",
          "uuid": "agent-assistant-1",
          "parentUuid": "agent-user-1",
          "isSidechain": true,
          "message": {
            "id": "agent-msg-1",
            "type": "message",
            "role": "assistant",
            "model": "claude",
            "content": [{"type": "text", "text": "Imports are clean."}]
          }
        }
        """,
        2,
    )

    views = build_conversation_views(
        [assistant, tool_result],
        agent_sessions={"agent-1": [agent_user, agent_assistant]},
    )

    subagent = views[0]["tools"][0]["subagent"]
    assert subagent["agent_id"] == "agent-1"
    assert subagent["entries"][1]["texts"] == ["Imports are clean."]
