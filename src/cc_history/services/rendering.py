import json
from typing import Any

from cc_history.schema import (
    AiTitleEntry,
    AssistantEntry,
    CustomTitleEntry,
    ErrorEntry,
    SummaryEntry,
    SystemEntry,
    UserEntry,
)
from cc_history.schema.content import (
    DocumentContent,
    ImageContent,
    TextContent,
    ThinkingContent,
    ToolReferenceContent,
    ToolResultContent,
    ToolUseContent,
    UnknownContent,
)
from cc_history.services.parser import ParsedEntry

SUBAGENT_TOOL_NAMES = {"Task", "Agent"}


def stringify(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False, indent=2)


def _format_tool_input(tool: ToolUseContent) -> str:
    input_value = tool.input
    if tool.name == "Bash":
        parts = []
        description = input_value.get("description")
        command = input_value.get("command")
        if description:
            parts.append(stringify(description))
        if command:
            parts.append("$ " + stringify(command))
        return "\n".join(parts) or stringify(input_value)

    if tool.name in {"Read", "Write", "Edit", "MultiEdit", "NotebookEdit"}:
        file_path = stringify(input_value.get("file_path") or input_value.get("notebook_path"))
        lines = [file_path] if file_path else []
        if tool.name == "Edit":
            old_text = stringify(input_value.get("old_string"))
            new_text = stringify(input_value.get("new_string"))
            if old_text or new_text:
                lines.append("--- old")
                lines.append(old_text)
                lines.append("+++ new")
                lines.append(new_text)
        elif tool.name == "MultiEdit":
            edits = input_value.get("edits")
            if isinstance(edits, list):
                lines.append(f"{len(edits)} edits")
        elif tool.name == "Write":
            content = stringify(input_value.get("content"))
            if content:
                lines.append(content)
        else:
            for key in ("offset", "limit"):
                value = input_value.get(key)
                if value is not None:
                    lines.append(f"{key}: {value}")
        return "\n".join(lines) or stringify(input_value)

    if tool.name == "Grep":
        pattern = stringify(input_value.get("pattern"))
        path = stringify(input_value.get("path"))
        return "\n".join(part for part in [pattern, path] if part) or stringify(input_value)

    return stringify(input_value)


def _tool_display(tool: ToolUseContent) -> dict[str, Any]:
    input_value = tool.input
    if tool.name == "Bash":
        return {
            "type": "bash",
            "description": stringify(input_value.get("description")),
            "command": stringify(input_value.get("command")),
        }

    if tool.name in {"Read", "Write", "Edit", "MultiEdit", "NotebookEdit"}:
        display: dict[str, Any] = {
            "type": tool.name.lower(),
            "file_path": stringify(
                input_value.get("file_path") or input_value.get("notebook_path")
            ),
        }
        if tool.name == "Read":
            display["offset"] = input_value.get("offset")
            display["limit"] = input_value.get("limit")
        elif tool.name == "Write":
            display["content"] = stringify(input_value.get("content"))
        elif tool.name == "Edit":
            display["edits"] = [
                {
                    "old": stringify(input_value.get("old_string")),
                    "new": stringify(input_value.get("new_string")),
                    "replace_all": input_value.get("replace_all"),
                },
            ]
        elif tool.name == "MultiEdit":
            edits = input_value.get("edits")
            display["edits"] = (
                [
                    {
                        "old": stringify(edit.get("old_string")),
                        "new": stringify(edit.get("new_string")),
                        "replace_all": edit.get("replace_all"),
                    }
                    for edit in edits
                    if isinstance(edit, dict)
                ]
                if isinstance(edits, list)
                else []
            )
        return display

    if tool.name == "TodoWrite":
        todos = input_value.get("todos")
        return {
            "type": "todo",
            "todos": todos if isinstance(todos, list) else [],
        }

    if tool.name in {"Grep", "Glob", "LS"}:
        return {
            "type": "search",
            "pattern": stringify(input_value.get("pattern")),
            "path": stringify(input_value.get("path")),
        }

    if tool.name in SUBAGENT_TOOL_NAMES:
        return {
            "type": "subagent",
            "prompt": stringify(input_value.get("prompt")),
        }

    return {
        "type": "raw",
        "input": input_value,
    }


def _image_to_view(content: ImageContent) -> dict[str, str]:
    return {
        "media_type": content.source.media_type,
        "data_uri": f"data:{content.source.media_type};base64,{content.source.data}",
    }


def _document_to_view(content: DocumentContent) -> dict[str, str]:
    return {
        "media_type": content.source.media_type,
        "source_type": content.source.type,
        "text": content.source.data if content.source.type == "text" else "",
    }


def _append_content_block(
    block: object,
    texts: list[str],
    tools: list[dict[str, Any]],
    thinking: list[str],
    images: list[dict[str, str]],
    documents: list[dict[str, str]],
) -> None:
    if isinstance(block, str):
        texts.append(block)
    elif isinstance(block, TextContent):
        texts.append(block.text)
    elif isinstance(block, ThinkingContent):
        thinking.append(block.thinking)
    elif isinstance(block, ToolUseContent):
        body = _format_tool_input(block)
        tools.append(
            {
                "id": block.id,
                "name": block.name,
                "summary": _tool_summary(block),
                "body": body,
                "input_json": stringify(block.input),
                "display": _tool_display(block),
                "kind": block.name.lower(),
                "has_result": False,
                "result_texts": [],
                "result_images": [],
                "result_documents": [],
                "result_is_error": False,
                "result_display": {"type": "none"},
                "subagent": None,
            },
        )
    elif isinstance(block, ToolResultContent):
        _append_tool_result(block, texts, images, documents)
    elif isinstance(block, ToolReferenceContent):
        tool_name = block.name or block.tool_name or "unknown"
        texts.append(f"Tool reference: {tool_name}")
    elif isinstance(block, ImageContent):
        images.append(_image_to_view(block))
    elif isinstance(block, DocumentContent):
        documents.append(_document_to_view(block))
    elif isinstance(block, UnknownContent):
        texts.append(f"{block.type}: {stringify(block.model_dump(mode='json'))}")
    else:
        texts.append(stringify(block))


def _append_tool_result(
    block: ToolResultContent,
    texts: list[str],
    images: list[dict[str, str]],
    documents: list[dict[str, str]],
) -> None:
    prefix = "Tool error: " if block.is_error else "Tool result: "
    if isinstance(block.content, str):
        texts.append(prefix + block.content)
        return
    if block.content is None:
        texts.append(prefix.rstrip())
        return

    for child in block.content:
        if isinstance(child, TextContent):
            texts.append(prefix + child.text)
        elif isinstance(child, ImageContent):
            images.append(_image_to_view(child))
        elif isinstance(child, DocumentContent):
            documents.append(_document_to_view(child))
        else:
            texts.append(prefix + stringify(child.model_dump(mode="json")))


def _tool_summary(tool: ToolUseContent) -> str:
    input_value = tool.input
    if tool.name == "Bash":
        return stringify(input_value.get("description") or input_value.get("command"))
    if tool.name in {"Read", "Write", "Edit", "MultiEdit", "NotebookEdit"}:
        return stringify(input_value.get("file_path") or input_value.get("notebook_path"))
    if tool.name == "Grep":
        pattern = stringify(input_value.get("pattern"))
        path = stringify(input_value.get("path"))
        return " ".join(part for part in [pattern, path] if part)
    if tool.name in {"Glob", "LS"}:
        pattern = stringify(input_value.get("pattern"))
        path = stringify(input_value.get("path"))
        return " ".join(part for part in [pattern, path] if part)
    if tool.name in SUBAGENT_TOOL_NAMES:
        return stringify(input_value.get("prompt"))
    return ""


def _tool_result_to_view(block: ToolResultContent, tool_use_result: Any = None) -> dict[str, Any]:
    texts: list[str] = []
    images: list[dict[str, str]] = []
    documents: list[dict[str, str]] = []
    raw_texts: list[str] = []

    if isinstance(block.content, str):
        raw_texts.append(block.content)
    elif isinstance(block.content, list):
        for child in block.content:
            if isinstance(child, TextContent):
                raw_texts.append(child.text)
            elif isinstance(child, ImageContent):
                images.append(_image_to_view(child))
            elif isinstance(child, DocumentContent):
                documents.append(_document_to_view(child))
            else:
                raw_texts.append(stringify(child.model_dump(mode="json")))

    for text in raw_texts:
        if text:
            texts.append(text)

    return {
        "texts": texts,
        "images": images,
        "documents": documents,
        "is_error": block.is_error is True,
        "tool_use_result": tool_use_result,
    }


def _tool_result_display(result: dict[str, Any]) -> dict[str, Any]:
    tool_use_result = result.get("tool_use_result")
    if isinstance(tool_use_result, dict):
        if {"stdout", "stderr", "interrupted", "isImage"}.issubset(tool_use_result.keys()):
            return {
                "type": "command",
                "stdout": stringify(tool_use_result.get("stdout")),
                "stderr": stringify(tool_use_result.get("stderr")),
                "interrupted": tool_use_result.get("interrupted") is True,
                "is_image": tool_use_result.get("isImage") is True,
            }

        if "filenames" in tool_use_result:
            filenames = tool_use_result.get("filenames")
            return {
                "type": "file_list",
                "filenames": filenames if isinstance(filenames, list) else [],
                "duration_ms": tool_use_result.get("durationMs"),
                "num_files": tool_use_result.get("numFiles"),
                "truncated": tool_use_result.get("truncated") is True,
            }

        file_payload = tool_use_result.get("file")
        if tool_use_result.get("type") == "text" and isinstance(file_payload, dict):
            return {
                "type": "file_content",
                "file_path": stringify(file_payload.get("filePath")),
                "content": stringify(file_payload.get("content")),
                "num_lines": file_payload.get("numLines"),
                "start_line": file_payload.get("startLine"),
                "total_lines": file_payload.get("totalLines"),
            }

        if "oldTodos" in tool_use_result or "newTodos" in tool_use_result:
            old_todos = tool_use_result.get("oldTodos")
            new_todos = tool_use_result.get("newTodos")
            return {
                "type": "todo",
                "old_todos": old_todos if isinstance(old_todos, list) else [],
                "new_todos": new_todos if isinstance(new_todos, list) else [],
            }

        if "structuredPatch" in tool_use_result or "oldString" in tool_use_result:
            patches = tool_use_result.get("structuredPatch")
            return {
                "type": "edit",
                "file_path": stringify(tool_use_result.get("filePath")),
                "old": stringify(tool_use_result.get("oldString")),
                "new": stringify(tool_use_result.get("newString")),
                "user_modified": tool_use_result.get("userModified") is True,
                "replace_all": tool_use_result.get("replaceAll") is True,
                "patches": patches if isinstance(patches, list) else [],
            }

        if tool_use_result.get("type") == "create":
            patches = tool_use_result.get("structuredPatch")
            return {
                "type": "create",
                "file_path": stringify(tool_use_result.get("filePath")),
                "content": stringify(tool_use_result.get("content")),
                "patches": patches if isinstance(patches, list) else [],
            }

        return {
            "type": "json",
            "json": stringify(tool_use_result),
        }

    if result["texts"]:
        return {
            "type": "text",
            "texts": result["texts"],
        }

    return {"type": "none"}


def _iter_tool_results(entry: ParsedEntry) -> list[tuple[ToolResultContent, Any]]:
    if not isinstance(entry, UserEntry):
        return []
    content = entry.message.content
    if not isinstance(content, list):
        return []
    return [
        (block, entry.toolUseResult) for block in content if isinstance(block, ToolResultContent)
    ]


def _is_tool_result_only_entry(entry: ParsedEntry) -> bool:
    if not isinstance(entry, UserEntry):
        return False
    content = entry.message.content
    return (
        isinstance(content, list)
        and len(content) > 0
        and all(isinstance(block, ToolResultContent) for block in content)
    )


def _is_sidechain_entry(entry: ParsedEntry) -> bool:
    return isinstance(entry, UserEntry | AssistantEntry | SystemEntry) and entry.isSidechain is True


def _is_thread_entry(entry: ParsedEntry) -> bool:
    return isinstance(entry, UserEntry | AssistantEntry | SystemEntry)


def _first_user_text(entry: ParsedEntry) -> str | None:
    if not isinstance(entry, UserEntry):
        return None
    content = entry.message.content
    if isinstance(content, str):
        return content
    if not content:
        return None
    first = content[0]
    if isinstance(first, str):
        return first
    if isinstance(first, TextContent):
        return first.text
    return None


def _thread_root(entry: ParsedEntry, entry_by_uuid: dict[str, ParsedEntry]) -> ParsedEntry:
    if not _is_thread_entry(entry) or entry.parentUuid is None:
        return entry
    parent = entry_by_uuid.get(entry.parentUuid)
    if parent is None:
        return entry
    return _thread_root(parent, entry_by_uuid)


def _group_sidechain_threads(
    entries: list[ParsedEntry],
    source_agent_id: str | None,
) -> list[dict[str, Any]]:
    thread_entries = [entry for entry in entries if _is_thread_entry(entry)]
    entry_by_uuid = {entry.uuid: entry for entry in thread_entries if entry.uuid is not None}
    groups: dict[str, list[ParsedEntry]] = {}
    roots: dict[str, ParsedEntry] = {}

    for entry in thread_entries:
        root = _thread_root(entry, entry_by_uuid)
        root_key = root.uuid or entry.uuid or f"{source_agent_id or 'embedded'}-{len(groups)}"
        roots[root_key] = root
        groups.setdefault(root_key, []).append(entry)

    threads: list[dict[str, Any]] = []
    for root_key, group_entries in groups.items():
        root = roots[root_key]
        agent_id = source_agent_id
        if agent_id is None and _is_thread_entry(root):
            agent_id = root.agentId
        threads.append(
            {
                "agent_id": agent_id,
                "prompt": _first_user_text(root),
                "entries": group_entries,
            },
        )
    return threads


def _build_sidechain_index(
    entries: list[ParsedEntry],
    agent_sessions: dict[str, list[ParsedEntry]] | None,
) -> dict[str, dict[str, dict[str, Any]]]:
    by_prompt: dict[str, dict[str, Any]] = {}
    by_agent_id: dict[str, dict[str, Any]] = {}

    embedded_threads = _group_sidechain_threads(
        [entry for entry in entries if _is_sidechain_entry(entry)],
        None,
    )
    agent_threads: list[dict[str, Any]] = []
    for agent_id, agent_entries in (agent_sessions or {}).items():
        agent_threads.extend(_group_sidechain_threads(agent_entries, agent_id))

    for thread in [*embedded_threads, *agent_threads]:
        prompt = thread["prompt"]
        agent_id = thread["agent_id"]
        if isinstance(prompt, str) and prompt:
            by_prompt.setdefault(prompt, thread)
        if isinstance(agent_id, str) and agent_id:
            by_agent_id.setdefault(agent_id, thread)

    return {
        "by_prompt": by_prompt,
        "by_agent_id": by_agent_id,
    }


def _agent_id_from_result(result: dict[str, Any] | None) -> str | None:
    if result is None:
        return None
    tool_use_result = result.get("tool_use_result")
    if not isinstance(tool_use_result, dict):
        return None
    agent_id = tool_use_result.get("agentId")
    return agent_id if isinstance(agent_id, str) and agent_id else None


def _subagent_thread_to_view(thread: dict[str, Any]) -> dict[str, Any]:
    entries = thread["entries"]
    views = build_conversation_views(entries, include_sidechain=True)
    return {
        "agent_id": thread["agent_id"],
        "prompt": thread["prompt"],
        "message_count": len(views),
        "entries": views,
    }


def _attach_subagent_to_tool(
    tool: dict[str, Any],
    result: dict[str, Any] | None,
    sidechain_index: dict[str, dict[str, dict[str, Any]]],
) -> None:
    if tool["name"] not in SUBAGENT_TOOL_NAMES:
        return

    thread = None
    agent_id = _agent_id_from_result(result)
    if agent_id is not None:
        thread = sidechain_index["by_agent_id"].get(agent_id)

    if thread is None:
        prompt = tool.get("summary")
        if isinstance(prompt, str) and prompt:
            thread = sidechain_index["by_prompt"].get(prompt)

    if thread is not None:
        tool["subagent"] = _subagent_thread_to_view(thread)


def content_to_view(content: str | list[object]) -> dict[str, list]:
    texts: list[str] = []
    tools: list[dict[str, Any]] = []
    thinking: list[str] = []
    images: list[dict[str, str]] = []
    documents: list[dict[str, str]] = []

    if isinstance(content, str):
        texts.append(content)
    else:
        for block in content:
            _append_content_block(block, texts, tools, thinking, images, documents)

    return {
        "texts": [text for text in texts if text],
        "tools": tools,
        "thinking": thinking,
        "images": images,
        "documents": documents,
    }


def _base_view(
    entry_type: str,
    title: str,
    timestamp: str | None,
    uuid: str | None = None,
    is_error: bool = False,
    error: str | None = None,
) -> dict[str, Any]:
    return {
        "type": entry_type,
        "uuid": uuid,
        "title": title,
        "timestamp": timestamp,
        "texts": [],
        "tools": [],
        "thinking": [],
        "images": [],
        "documents": [],
        "error": error,
        "is_error": is_error,
    }


def entry_to_view(
    entry: ParsedEntry,
    tool_results: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    if isinstance(entry, ErrorEntry):
        view = _base_view(
            entry.type,
            f"Parse error on line {entry.line_number}",
            None,
            is_error=True,
            error=entry.error,
        )
        view["texts"] = [entry.line]
        return view

    if isinstance(entry, SummaryEntry):
        view = _base_view(entry.type, "Summary", entry.timestamp, entry.uuid)
        view["texts"] = [entry.summary]
        return view

    if isinstance(entry, CustomTitleEntry):
        view = _base_view(entry.type, "Custom title", entry.timestamp, entry.uuid)
        view["texts"] = [entry.customTitle or ""]
        return view

    if isinstance(entry, AiTitleEntry):
        view = _base_view(entry.type, "AI title", entry.timestamp, entry.uuid)
        view["texts"] = [entry.aiTitle or ""]
        return view

    if isinstance(entry, SystemEntry):
        view = _base_view(
            entry.type,
            f"System{': ' + entry.subtype if entry.subtype else ''}",
            entry.timestamp,
            entry.uuid,
        )
        view["texts"] = [entry.content or ""]
        return view

    if isinstance(entry, UserEntry | AssistantEntry):
        view = _base_view(entry.type, entry.message.role.title(), entry.timestamp, entry.uuid)
        content_view = content_to_view(entry.message.content)
        view.update(content_view)
        if tool_results is not None:
            for tool in view["tools"]:
                result = tool_results.get(tool["id"])
                if result is None:
                    continue
                tool["has_result"] = True
                tool["result_texts"] = result["texts"]
                tool["result_images"] = result["images"]
                tool["result_documents"] = result["documents"]
                tool["result_is_error"] = result["is_error"]
                tool["result_display"] = _tool_result_display(result)
        return view

    view = _base_view(entry.type, entry.type, entry.timestamp, entry.uuid)
    view["texts"] = [stringify(entry.model_dump(mode="json"))]
    return view


def build_conversation_views(
    entries: list[ParsedEntry],
    agent_sessions: dict[str, list[ParsedEntry]] | None = None,
    include_sidechain: bool = False,
) -> list[dict[str, Any]]:
    tool_results: dict[str, dict[str, Any]] = {}
    for entry in entries:
        for result, tool_use_result in _iter_tool_results(entry):
            tool_results[result.tool_use_id] = _tool_result_to_view(result, tool_use_result)

    sidechain_index = _build_sidechain_index(entries, agent_sessions)

    views: list[dict[str, Any]] = []
    for entry in entries:
        if _is_tool_result_only_entry(entry):
            continue
        if not include_sidechain and _is_sidechain_entry(entry):
            continue

        view = entry_to_view(entry, tool_results)
        for tool in view["tools"]:
            _attach_subagent_to_tool(tool, tool_results.get(tool["id"]), sidechain_index)
        views.append(view)
    return views


def _edited_file_display_path(file_path: str, cwd: str | None) -> tuple[str, bool]:
    if cwd is None or cwd == "":
        return file_path, True

    cwd_with_slash = cwd if cwd.endswith("/") else cwd + "/"
    if file_path == cwd:
        return ".", False
    if file_path.startswith(cwd_with_slash):
        return file_path[len(cwd_with_slash) :], False
    return file_path, True


def extract_edited_files(
    views: list[dict[str, Any]], cwd: str | None = None
) -> list[dict[str, Any]]:
    edited_files: dict[str, dict[str, Any]] = {}

    for view in views:
        for tool in view["tools"]:
            display = tool.get("display")
            if not isinstance(display, dict):
                continue
            if display.get("type") not in {"write", "edit", "multiedit", "notebookedit"}:
                continue

            file_path = display.get("file_path")
            if not isinstance(file_path, str) or file_path == "":
                continue

            display_path, is_external = _edited_file_display_path(file_path, cwd)
            edited_files[file_path] = {
                "file_path": file_path,
                "display_path": display_path,
                "tool_name": tool["name"],
                "tool_id": tool["id"],
                "timestamp": view["timestamp"],
                "is_external": is_external,
            }

    return list(edited_files.values())


def entry_search_text(entry: ParsedEntry) -> tuple[str, str]:
    view = entry_to_view(entry)
    parts: list[str] = []
    parts.extend(view["texts"])
    parts.extend(view["thinking"])
    parts.extend(tool["name"] + "\n" + tool["body"] for tool in view["tools"])
    parts.extend(document["text"] for document in view["documents"] if document["text"])

    role = view["title"].lower() if view["title"] else entry.type
    return role, "\n".join(part for part in parts if part)
