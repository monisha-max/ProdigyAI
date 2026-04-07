"""
Google Workspace MCP adapter.

This module wraps a community Google Workspace MCP server behind stable local
Python functions so the rest of the app does not depend on third-party tool
names or payload shapes.
"""

from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
from datetime import datetime, timezone
from typing import Any

from google.adk.tools import FunctionTool


WORKSPACE_MCP_URL = os.getenv("GOOGLE_WORKSPACE_MCP_URL", "http://127.0.0.1:8765/mcp")
WORKSPACE_MCP_TIMEOUT = float(os.getenv("GOOGLE_WORKSPACE_MCP_TIMEOUT", "12"))
WORKSPACE_MCP_ENABLED = os.getenv("GOOGLE_WORKSPACE_MCP_ENABLED", "true").lower() not in {
    "0",
    "false",
    "no",
}

_SESSION_ID = None

DEFAULT_TOOL_MAP = {
    "calendar_list_today": "get_events",
    "calendar_create_event": "manage_event",
    "tasks_list": "list_tasks",
    "tasks_create": "manage_task",
    "tasks_complete": "manage_task",
    "gmail_list_priority_threads": "search_gmail_messages",
    "gmail_get_thread_summary": "get_gmail_thread_content",
    "gmail_create_draft": "draft_gmail_message",
}

TOOL_HINTS = {
    "calendar_list_today": ["calendar", "event", "list", "get", "today", "upcoming"],
    "calendar_create_event": ["calendar", "event", "create", "insert", "schedule", "add"],
    "tasks_list": ["task", "tasks", "list", "get", "open", "pending"],
    "tasks_create": ["task", "tasks", "create", "add", "insert"],
    "tasks_complete": ["task", "tasks", "complete", "update", "mark", "close"],
    "gmail_list_priority_threads": ["gmail", "email", "thread", "threads", "inbox", "list", "search"],
    "gmail_get_thread_summary": ["gmail", "email", "thread", "message", "read", "get", "summary"],
    "gmail_create_draft": ["gmail", "email", "draft", "reply", "compose", "create"],
}


def _load_tool_map() -> dict[str, str]:
    raw = os.getenv("GOOGLE_WORKSPACE_MCP_TOOL_MAP", "").strip()
    if not raw:
        return dict(DEFAULT_TOOL_MAP)
    try:
        parsed = json.loads(raw)
        merged = dict(DEFAULT_TOOL_MAP)
        merged.update({k: str(v) for k, v in parsed.items() if str(v).strip()})
        return merged
    except json.JSONDecodeError:
        return dict(DEFAULT_TOOL_MAP)


TOOL_MAP = _load_tool_map()


def _build_headers() -> dict[str, str]:
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
    }
    if _SESSION_ID:
        headers["Mcp-Session-Id"] = _SESSION_ID
    return headers


def _extract_response_json(resp: Any) -> dict[str, Any]:
    global _SESSION_ID
    if resp.headers.get("Mcp-Session-Id"):
        _SESSION_ID = resp.headers["Mcp-Session-Id"]
    content_type = resp.headers.get("Content-Type", "")
    if "text/event-stream" in content_type:
        data_lines: list[str] = []
        while True:
            line = resp.readline().decode("utf-8")
            if not line:
                break
            stripped_line = line.strip()
            if not stripped_line:
                if data_lines:
                    break
                continue
            if stripped_line.startswith("data:"):
                data_lines.append(stripped_line[5:].strip())
        raw = data_lines[-1] if data_lines else "{}"
    else:
        raw = resp.read().decode("utf-8")
    if not raw.strip():
        return {}
    stripped = raw.lstrip()
    if "data:" in stripped and any(
        line.startswith(("data:", "event:", "id:", "retry:"))
        for line in stripped.splitlines()
        if line.strip()
    ):
        lines = [line[5:].strip() for line in stripped.splitlines() if line.startswith("data:")]
        raw = lines[-1] if lines else "{}"
    return json.loads(raw)


def _post_rpc(method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = {
        "jsonrpc": "2.0",
        "id": int(datetime.now(tz=timezone.utc).timestamp() * 1000),
        "method": method,
    }
    if params is not None:
        payload["params"] = params
    req = urllib.request.Request(
        WORKSPACE_MCP_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers=_build_headers(),
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=WORKSPACE_MCP_TIMEOUT) as resp:
        result = _extract_response_json(resp)
    if result.get("error"):
        raise RuntimeError(result["error"].get("message", "Workspace MCP error"))
    return result.get("result", {})


def _ensure_initialized() -> None:
    if not WORKSPACE_MCP_ENABLED:
        raise RuntimeError("Google Workspace MCP disabled")
    if _SESSION_ID:
        return
    _post_rpc(
        "initialize",
        {
            "protocolVersion": "2025-06-18",
            "capabilities": {},
            "clientInfo": {"name": "ProdigyAI", "version": "1.0"},
        },
    )


def _safe_json(value: Any) -> Any:
    if isinstance(value, str):
        text = value.strip()
        if (text.startswith("{") and text.endswith("}")) or (text.startswith("[") and text.endswith("]")):
            try:
                return json.loads(text)
            except json.JSONDecodeError:
                return value
    return value


def _extract_structured_payload(result: dict[str, Any]) -> Any:
    if "result" in result and isinstance(result["result"], (str, dict, list)):
        return result["result"]
    if "structuredContent" in result:
        return result["structuredContent"]
    content = result.get("content") or []
    if isinstance(content, list):
        text_parts = []
        for item in content:
            if isinstance(item, dict):
                if item.get("type") == "text" and item.get("text"):
                    text_parts.append(item["text"])
                if item.get("data") is not None:
                    return item["data"]
        if text_parts:
            combined = "\n".join(text_parts)
            parsed = _safe_json(combined)
            return parsed
    return result


def _normalize_list(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if isinstance(payload, dict):
        for key in ("items", "events", "tasks", "threads", "results", "data"):
            value = payload.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
    return []


def _workspace_user_email() -> str:
    email = os.getenv("GOOGLE_WORKSPACE_USER_EMAIL", "").strip() or os.getenv("USER_GOOGLE_EMAIL", "").strip()
    if email:
        return email
    raise RuntimeError("Set GOOGLE_WORKSPACE_USER_EMAIL in ProdigyAI .env to the Gmail address you authenticated with.")


def _workspace_task_list_id() -> str:
    configured = os.getenv("GOOGLE_WORKSPACE_TASK_LIST_ID", "").strip()
    if configured:
        return configured

    payload, _ = _call_named_tool("list_task_lists", {"user_google_email": _workspace_user_email(), "max_results": 10})
    text = _extract_result_text(payload)
    task_list_id = _extract_labeled_value(text, ["Task List ID", "ID"])
    if task_list_id:
        return task_list_id
    paren_match = re.search(r"\(ID:\s*([^)]+)\)", text)
    if paren_match:
        return paren_match.group(1).strip()
    raise RuntimeError("Unable to determine a Google Tasks list ID. Set GOOGLE_WORKSPACE_TASK_LIST_ID in ProdigyAI .env.")


def _workspace_timezone() -> str | None:
    timezone = os.getenv("GOOGLE_WORKSPACE_TIMEZONE", "").strip()
    return timezone or None


def _extract_result_text(payload: Any) -> str:
    if isinstance(payload, str):
        return payload
    if isinstance(payload, dict):
        if isinstance(payload.get("result"), str):
            return payload["result"]
        if isinstance(payload.get("text"), str):
            return payload["text"]
    return ""


def _extract_labeled_value(text: str, labels: list[str]) -> str:
    for label in labels:
        pattern = re.compile(rf"(?im)(?:^|\|\s*){re.escape(label)}\s*:\s*(.+?)(?:\s*\|\s*|$)")
        match = pattern.search(text)
        if match:
            return match.group(1).strip()
        bullet_pattern = re.compile(rf"(?im)^\s*[-*]?\s*{re.escape(label)}\s*:\s*(.+?)\s*$")
        bullet_match = bullet_pattern.search(text)
        if bullet_match:
            return bullet_match.group(1).strip()
        paren_pattern = re.compile(rf"(?im)\(\s*{re.escape(label)}\s*:\s*([^)]+)\)")
        paren_match = paren_pattern.search(text)
        if paren_match:
            return paren_match.group(1).strip()
    return ""


def _record_blocks(text: str, anchor_labels: list[str]) -> list[str]:
    if not text.strip():
        return []
    blocks = []
    current: list[str] = []
    anchor_re = re.compile(rf"(?im)^\s*(?:{'|'.join(re.escape(label) for label in anchor_labels)})\s*:")
    for line in text.splitlines():
        if anchor_re.search(line) and current:
            blocks.append("\n".join(current).strip())
            current = [line]
        else:
            current.append(line)
    if current:
        blocks.append("\n".join(current).strip())
    return [block for block in blocks if any(label.lower() in block.lower() for label in anchor_labels)]


def _parse_calendar_text(text: str, start_date: str, end_date: str) -> list[dict[str, Any]]:
    events = []
    bullet_seen = set()
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped.startswith("- "):
            continue
        title_match = re.match(r'-\s+"(?P<title>.+?)"', stripped)
        starts_match = re.search(r"Starts:\s*(?P<start>[^,]+)", stripped)
        ends_match = re.search(r"Ends:\s*(?P<end>[^)]+)", stripped)
        id_match = re.search(r"\bID:\s*(?P<id>[^\s|]+)", stripped)
        if not title_match or not starts_match:
            continue
        start_value = starts_match.group("start").strip()
        event_date = _parse_date(start_value) or start_date
        if event_date and (event_date < start_date or event_date > end_date):
            continue
        end_value = ends_match.group("end").strip() if ends_match else ""
        meeting_match = re.search(r"\bMeeting:\s*(?P<link>https?://\S+)", stripped)
        link_match = re.search(r"\bLink:\s*(?P<link>https?://\S+)", stripped)
        event_id = id_match.group("id").strip() if id_match else f"{event_date}:{title_match.group('title').strip()}"
        bullet_seen.add(event_id)
        events.append(
            {
                "id": event_id,
                "title": title_match.group("title").strip() or "Google event",
                "event_date": event_date,
                "start_time": _parse_time(start_value),
                "end_time": _parse_time(end_value),
                "attendees": "",
                "location": (meeting_match.group("link").strip() if meeting_match else "") or (
                    link_match.group("link").strip() if link_match else ""
                ),
                "summary": stripped,
                "source": "google",
            }
        )
    for block in _record_blocks(text, ["Event ID", "ID", "Summary", "Title"]):
        event_date = _parse_date(
            _extract_labeled_value(block, ["Date", "Event Date", "Start Time", "Start"])
        ) or start_date
        if event_date and (event_date < start_date or event_date > end_date):
            continue
        event_id = _extract_labeled_value(block, ["Event ID", "ID"])
        if event_id and event_id in bullet_seen:
            continue
        title = _extract_labeled_value(block, ["Summary", "Title"]) or "Google event"
        start_value = _extract_labeled_value(block, ["Start Time", "Start"])
        end_value = _extract_labeled_value(block, ["End Time", "End"])
        events.append(
            {
                "id": event_id,
                "title": title,
                "event_date": event_date,
                "start_time": _parse_time(start_value),
                "end_time": _parse_time(end_value),
                "attendees": _extract_labeled_value(block, ["Attendees", "Guests"]),
                "location": _extract_labeled_value(block, ["Location"]),
                "summary": _extract_labeled_value(block, ["Description", "Details"]),
                "source": "google",
            }
        )
    return events


def _parse_task_text(text: str) -> list[dict[str, Any]]:
    tasks = []
    inline_blocks = [block.strip() for block in re.split(r"(?im)(?=^\s*-\s+)", text) if block.strip().startswith("- ")]
    seen_ids = set()
    for block in inline_blocks:
        first_line = block.splitlines()[0].strip()
        summary_match = re.match(r"-\s+(?P<title>.+?)\s+\(ID:\s*(?P<id>[^)]+)\)", first_line)
        if not summary_match:
            continue
        task_id = summary_match.group("id").strip()
        seen_ids.add(task_id)
        status = (_extract_labeled_value(block, ["Status"]) or "needsAction").lower()
        tasks.append(
            {
                "id": task_id,
                "title": summary_match.group("title").strip() or "Google task",
                "notes": _extract_labeled_value(block, ["Notes", "Description"]),
                "due_date": _parse_date(_extract_labeled_value(block, ["Due", "Due Date"])),
                "status": "done" if status in {"done", "completed"} else "todo",
                "priority": "medium",
                "thread_id": "",
                "source": "google",
            }
        )
    bullet_blocks = [block.strip() for block in re.split(r"(?im)(?=^\s*-\s*Title:\s*)", text) if block.strip().startswith("- Title:")]
    for block in bullet_blocks:
        task_id = _extract_labeled_value(block, ["Task ID", "ID"])
        if task_id:
            seen_ids.add(task_id)
        status = (_extract_labeled_value(block, ["Status"]) or "needsAction").lower()
        tasks.append(
            {
                "id": task_id,
                "title": _extract_labeled_value(block, ["Title"]) or "Google task",
                "notes": _extract_labeled_value(block, ["Notes", "Description"]),
                "due_date": _parse_date(_extract_labeled_value(block, ["Due", "Due Date"])),
                "status": "done" if status in {"done", "completed"} else "todo",
                "priority": "medium",
                "thread_id": "",
                "source": "google",
            }
        )
    for block in _record_blocks(text, ["Task ID", "ID", "Title"]):
        task_id = _extract_labeled_value(block, ["Task ID", "ID"])
        if task_id and task_id in seen_ids:
            continue
        status = (_extract_labeled_value(block, ["Status"]) or "needsAction").lower()
        tasks.append(
            {
                "id": task_id,
                "title": _extract_labeled_value(block, ["Title"]) or "Google task",
                "notes": _extract_labeled_value(block, ["Notes", "Description"]),
                "due_date": _parse_date(_extract_labeled_value(block, ["Due", "Due Date"])),
                "status": "done" if status in {"done", "completed"} else "todo",
                "priority": "medium",
                "thread_id": "",
                "source": "google",
            }
        )
    return tasks


def _parse_gmail_search_text(text: str) -> list[dict[str, Any]]:
    threads = []
    for block in _record_blocks(text, ["Thread ID", "Message ID", "Subject"]):
        thread_id = _extract_labeled_value(block, ["Thread ID", "ID"])
        if not thread_id:
            continue
        threads.append(
            {
                "id": thread_id,
                "subject": _extract_labeled_value(block, ["Subject"]) or "Email thread",
                "snippet": _extract_labeled_value(block, ["Snippet", "Preview"]),
                "summary": _extract_labeled_value(block, ["Snippet", "Preview"]),
                "sender": _extract_labeled_value(block, ["From", "Sender"]),
                "unread_count": 0,
                "message_count": 1,
                "received_at": _coerce_dt(_extract_labeled_value(block, ["Date", "Received"])),
                "source": "google",
            }
        )
    return threads


def _coerce_dt(value: Any) -> str | None:
    if not value:
        return None
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(value, tz=timezone.utc).isoformat()
    text = str(value).strip()
    if not text:
        return None
    if text.endswith("Z"):
        return text.replace("Z", "+00:00")
    return text


def _parse_date(value: Any) -> str | None:
    text = _coerce_dt(value)
    if not text:
        return None
    return text.split("T")[0]


def _parse_time(value: Any) -> str | None:
    text = _coerce_dt(value)
    if not text:
        return None
    if "T" in text:
        return text.split("T", 1)[1][:5]
    return text[:5]


def _stringify_people(value: Any) -> str:
    if isinstance(value, list):
        parts = []
        for item in value:
            if isinstance(item, dict):
                parts.append(str(item.get("email") or item.get("name") or item.get("displayName") or ""))
            elif item:
                parts.append(str(item))
        return ", ".join(part for part in parts if part)
    if isinstance(value, dict):
        return str(value.get("email") or value.get("name") or value.get("displayName") or "")
    return str(value or "")


def _score_tool(tool: dict[str, Any], hints: list[str]) -> int:
    haystack = f"{tool.get('name', '')} {tool.get('description', '')}".lower()
    return sum(1 for hint in hints if hint in haystack)


def _tool_name_for(operation: str) -> str | None:
    if TOOL_MAP.get(operation):
        return TOOL_MAP[operation]
    status = get_workspace_status()
    tools = status.get("available_tools", [])
    if not tools:
        return None
    scored = sorted(
        ((tool.get("name"), _score_tool(tool, TOOL_HINTS[operation])) for tool in tools),
        key=lambda item: item[1],
        reverse=True,
    )
    name, score = scored[0]
    return name if score > 0 else None


def _call_named_tool(name: str, arguments: dict[str, Any]) -> tuple[Any, str]:
    _ensure_initialized()
    cleaned_arguments = {key: value for key, value in arguments.items() if value is not None}
    result = _post_rpc("tools/call", {"name": name, "arguments": cleaned_arguments})
    return _extract_structured_payload(result), name


def _call_remote_tool(operation: str, arguments: dict[str, Any]) -> tuple[Any, str | None]:
    _ensure_initialized()
    tool_name = _tool_name_for(operation)
    if not tool_name:
        raise RuntimeError(f"No Workspace MCP tool mapped for {operation}")
    cleaned_arguments = {key: value for key, value in arguments.items() if value is not None}
    result = _post_rpc("tools/call", {"name": tool_name, "arguments": cleaned_arguments})
    return _extract_structured_payload(result), tool_name


def get_workspace_status() -> dict[str, Any]:
    if not WORKSPACE_MCP_ENABLED:
        return {
            "connected": False,
            "status": "disabled",
            "message": "Google Workspace MCP disabled via environment.",
            "available_tools": [],
        }
    try:
        _ensure_initialized()
        result = _post_rpc("tools/list")
        tools = result.get("tools", []) if isinstance(result, dict) else []
        return {
            "connected": True,
            "status": "connected",
            "message": f"Connected to Workspace MCP at {WORKSPACE_MCP_URL}",
            "available_tools": tools,
        }
    except (urllib.error.URLError, RuntimeError, TimeoutError, OSError) as exc:
        return {
            "connected": False,
            "status": "disconnected",
            "message": str(exc),
            "available_tools": [],
        }


def list_calendar_events(start_date: str | None = None, end_date: str | None = None) -> dict[str, Any]:
    today = datetime.now().date().isoformat()
    start_date = start_date or today
    end_date = end_date or start_date
    status = get_workspace_status()
    if not status["connected"]:
        return {"status": status, "events": []}
    payload, tool_name = _call_remote_tool(
        "calendar_list_today",
        {
            "user_google_email": _workspace_user_email(),
            "time_min": f"{start_date}T00:00:00Z",
            "time_max": f"{end_date}T23:59:59Z",
            "calendar_id": "primary",
            "max_results": 250,
            "timezone": _workspace_timezone(),
        },
    )
    events = _parse_calendar_text(_extract_result_text(payload), start_date, end_date)
    return {"status": status, "events": events, "tool": tool_name}


def list_calendar_events_today() -> dict[str, Any]:
    today = datetime.now().date().isoformat()
    return list_calendar_events(start_date=today, end_date=today)


def create_calendar_event(
    title: str,
    event_date: str,
    start_time: str = "10:00",
    end_time: str = "11:00",
    location: str = "",
    attendees: str = "",
    description: str = "",
    timezone: str = "",
) -> dict[str, Any]:
    status = get_workspace_status()
    if not status["connected"]:
        return {"status": status, "event": None}
    payload, tool_name = _call_remote_tool(
        "calendar_create_event",
        {
            "summary": title,
            "user_google_email": _workspace_user_email(),
            "action": "create",
            "start_time": f"{event_date}T{start_time}:00",
            "end_time": f"{event_date}T{end_time}:00",
            "location": location,
            "attendees": [item.strip() for item in attendees.split(",") if item.strip()],
            "description": description,
            "calendar_id": "primary",
            "timezone": timezone or _workspace_timezone(),
        },
    )
    text = _extract_result_text(payload)
    parsed = _parse_calendar_text(text, event_date, event_date)
    item = parsed[0] if parsed else {}
    event = {
        "id": item.get("id") or _extract_labeled_value(text, ["Event ID", "ID"]),
        "title": item.get("title") or title,
        "event_date": item.get("event_date") or event_date,
        "start_time": item.get("start_time") or start_time,
        "end_time": item.get("end_time") or end_time,
        "attendees": item.get("attendees") or attendees,
        "location": item.get("location") or location,
        "summary": item.get("summary") or description,
        "source": "google",
    }
    return {"status": status, "event": event, "tool": tool_name}


def list_google_tasks() -> dict[str, Any]:
    status = get_workspace_status()
    if not status["connected"]:
        return {"status": status, "tasks": []}
    payload, tool_name = _call_remote_tool(
        "tasks_list",
        {
            "user_google_email": _workspace_user_email(),
            "task_list_id": _workspace_task_list_id(),
            "max_results": 50,
            "show_completed": True,
            "show_deleted": False,
            "show_hidden": False,
        },
    )
    tasks = _parse_task_text(_extract_result_text(payload))
    return {"status": status, "tasks": tasks, "tool": tool_name}


def create_google_task(
    title: str,
    notes: str = "",
    due_date: str = "",
    priority: str = "medium",
    thread_id: str = "",
) -> dict[str, Any]:
    status = get_workspace_status()
    if not status["connected"]:
        return {"status": status, "task": None}
    payload, tool_name = _call_remote_tool(
        "tasks_create",
        {
            "user_google_email": _workspace_user_email(),
            "action": "create",
            "task_list_id": _workspace_task_list_id(),
            "title": title,
            "notes": notes,
            "due": f"{due_date}T23:59:59Z" if due_date else None,
        },
    )
    text = _extract_result_text(payload)
    parsed = _parse_task_text(text)
    item = parsed[0] if parsed else {}
    task = {
        "id": item.get("id") or _extract_labeled_value(text, ["Task ID", "ID"]),
        "title": item.get("title") or title,
        "notes": item.get("notes") or notes,
        "due_date": item.get("due_date") or due_date or None,
        "status": item.get("status") or "todo",
        "priority": priority,
        "thread_id": thread_id,
        "source": "google",
    }
    return {"status": status, "task": task, "tool": tool_name}


def complete_google_task(task_id: str) -> dict[str, Any]:
    status = get_workspace_status()
    if not status["connected"]:
        return {"status": status, "success": False}
    payload, tool_name = _call_remote_tool(
        "tasks_complete",
        {
            "user_google_email": _workspace_user_email(),
            "action": "update",
            "task_list_id": _workspace_task_list_id(),
            "task_id": task_id,
            "status": "completed",
        },
    )
    success = bool(_extract_result_text(payload) or isinstance(payload, (dict, list)))
    return {"status": status, "success": success, "task_id": task_id, "tool": tool_name}


def list_priority_gmail_threads() -> dict[str, Any]:
    status = get_workspace_status()
    if not status["connected"]:
        return {"status": status, "threads": [], "unread_count": 0}
    payload, tool_name = _call_remote_tool(
        "gmail_list_priority_threads",
        {"user_google_email": _workspace_user_email(), "query": "in:inbox newer_than:7d", "page_size": 5},
    )
    threads = _parse_gmail_search_text(_extract_result_text(payload))
    unread_total = len(threads)
    return {"status": status, "threads": threads, "unread_count": unread_total, "tool": tool_name}


def get_gmail_thread_summary(thread_id: str) -> dict[str, Any]:
    status = get_workspace_status()
    if not status["connected"]:
        return {"status": status, "thread": None}
    payload, tool_name = _call_remote_tool(
        "gmail_get_thread_summary",
        {"user_google_email": _workspace_user_email(), "thread_id": thread_id},
    )
    text = _extract_result_text(payload)
    thread = {
        "id": thread_id,
        "subject": _extract_labeled_value(text, ["Subject"]) or "No subject",
        "snippet": _extract_labeled_value(text, ["Snippet", "Preview"]),
        "summary": _extract_labeled_value(text, ["Summary", "Body Summary"]) or text[:400],
        "sender": _extract_labeled_value(text, ["From", "Sender"]),
        "message_count": 1,
        "received_at": _coerce_dt(_extract_labeled_value(text, ["Date", "Received"])),
        "source": "google",
    }
    return {"status": status, "thread": thread, "tool": tool_name}


def create_gmail_draft(
    thread_id: str,
    to: str = "",
    subject: str = "",
    body: str = "",
) -> dict[str, Any]:
    status = get_workspace_status()
    if not status["connected"]:
        return {"status": status, "draft": None}
    payload, tool_name = _call_remote_tool(
        "gmail_create_draft",
        {
            "user_google_email": _workspace_user_email(),
            "subject": subject,
            "body": body,
            "to": to or None,
            "thread_id": thread_id or None,
        },
    )
    text = _extract_result_text(payload)
    draft = {
        "id": _extract_labeled_value(text, ["Draft ID", "ID"]),
        "thread_id": thread_id,
        "to": to,
        "subject": subject,
        "status": "draft_created",
    }
    return {"status": status, "draft": draft, "tool": tool_name}


def safe_list_calendar_events_today() -> dict[str, Any]:
    try:
        return list_calendar_events_today()
    except Exception as exc:
        return {"status": {"connected": False, "status": "error", "message": str(exc)}, "events": [], "error": str(exc)}


def safe_create_calendar_event(
    title: str,
    event_date: str,
    start_time: str = "10:00",
    end_time: str = "11:00",
    location: str = "",
    attendees: str = "",
    description: str = "",
) -> dict[str, Any]:
    try:
        return create_calendar_event(title, event_date, start_time, end_time, location, attendees, description)
    except Exception as exc:
        return {"status": {"connected": False, "status": "error", "message": str(exc)}, "event": None, "error": str(exc)}


def safe_list_google_tasks() -> dict[str, Any]:
    try:
        return list_google_tasks()
    except Exception as exc:
        return {"status": {"connected": False, "status": "error", "message": str(exc)}, "tasks": [], "error": str(exc)}


def safe_create_google_task(
    title: str,
    notes: str = "",
    due_date: str = "",
    priority: str = "medium",
    thread_id: str = "",
) -> dict[str, Any]:
    try:
        return create_google_task(title, notes, due_date, priority, thread_id)
    except Exception as exc:
        return {"status": {"connected": False, "status": "error", "message": str(exc)}, "task": None, "error": str(exc)}


def safe_complete_google_task(task_id: str) -> dict[str, Any]:
    try:
        return complete_google_task(task_id)
    except Exception as exc:
        return {"status": {"connected": False, "status": "error", "message": str(exc)}, "success": False, "task_id": task_id, "error": str(exc)}


def safe_list_priority_gmail_threads() -> dict[str, Any]:
    try:
        return list_priority_gmail_threads()
    except Exception as exc:
        return {"status": {"connected": False, "status": "error", "message": str(exc)}, "threads": [], "unread_count": 0, "error": str(exc)}


def safe_get_gmail_thread_summary(thread_id: str) -> dict[str, Any]:
    try:
        return get_gmail_thread_summary(thread_id)
    except Exception as exc:
        return {"status": {"connected": False, "status": "error", "message": str(exc)}, "thread": None, "error": str(exc)}


def safe_create_gmail_draft(
    thread_id: str,
    to: str = "",
    subject: str = "",
    body: str = "",
) -> dict[str, Any]:
    try:
        return create_gmail_draft(thread_id, to, subject, body)
    except Exception as exc:
        return {"status": {"connected": False, "status": "error", "message": str(exc)}, "draft": None, "error": str(exc)}


google_calendar_today_tool = FunctionTool(func=safe_list_calendar_events_today)
google_create_event_tool = FunctionTool(func=safe_create_calendar_event)
google_tasks_list_tool = FunctionTool(func=safe_list_google_tasks)
google_task_create_tool = FunctionTool(func=safe_create_google_task)
google_task_complete_tool = FunctionTool(func=safe_complete_google_task)
gmail_list_threads_tool = FunctionTool(func=safe_list_priority_gmail_threads)
gmail_thread_summary_tool = FunctionTool(func=safe_get_gmail_thread_summary)
gmail_create_draft_tool = FunctionTool(func=safe_create_gmail_draft)


def get_workspace_calendar_tools():
    return [google_calendar_today_tool, google_create_event_tool]


def get_workspace_task_tools():
    return [google_tasks_list_tool, google_task_create_tool, google_task_complete_tool]


def get_workspace_gmail_tools():
    return [gmail_list_threads_tool, gmail_thread_summary_tool, gmail_create_draft_tool]
