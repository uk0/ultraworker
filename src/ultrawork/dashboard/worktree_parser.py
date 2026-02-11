"""Claude session log parser for thread/session worktree rendering."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

PREVIEW_LIMIT = 800
SUMMARY_LIMIT = 160


def parse_session_worktree_events(
    *,
    session_id: str,
    thread_key: str,
    log_path: Path | None,
    command_text: str | None = None,
    command_ts: str | None = None,
) -> list[dict[str, Any]]:
    """Parse a session log file into normalized worktree events."""
    events: list[dict[str, Any]] = []
    seq = 0

    if command_text:
        seq += 1
        command_value = _sanitize_text(command_text)
        events.append(
            {
                "event_id": f"{session_id}:command",
                "thread_key": thread_key,
                "session_id": session_id,
                "seq": seq,
                "ts": command_ts or "",
                "kind": "user_command",
                "status": "ok",
                "title": "User Command",
                "summary": _shorten(command_value, SUMMARY_LIMIT),
                "preview": _shorten(command_value, PREVIEW_LIMIT),
                "parent_event_id": None,
                "tool_use_id": None,
                "raw": {"text": command_value},
            }
        )

    if not log_path or not log_path.exists():
        return events

    items = _parse_log_items(log_path)
    if not items:
        return events

    last_tool_idx = -1
    for idx, item in enumerate(items):
        if item["kind"] == "tool_call":
            last_tool_idx = idx

    tool_event_id_by_use_id: dict[str, str] = {}

    for idx, item in enumerate(items):
        seq += 1
        kind = item["kind"]

        if kind == "assistant_text":
            kind = "assistant_output" if idx > last_tool_idx else "assistant_observation"

        event_id = f"{session_id}:{item['offset']}:{item['part_index']}"
        title = item.get("title") or _default_title(kind)
        text_value = _sanitize_text(item.get("text"))
        summary = _shorten(text_value or title, SUMMARY_LIMIT)
        preview = _shorten(text_value or title, PREVIEW_LIMIT)
        status = item.get("status") or "info"
        parent_event_id: str | None = None

        tool_use_id = item.get("tool_use_id")
        if kind == "tool_call" and tool_use_id:
            tool_event_id_by_use_id[tool_use_id] = event_id
        if kind == "tool_result" and tool_use_id:
            parent_event_id = tool_event_id_by_use_id.get(tool_use_id)

        events.append(
            {
                "event_id": event_id,
                "thread_key": thread_key,
                "session_id": session_id,
                "seq": seq,
                "ts": item.get("ts") or "",
                "kind": kind,
                "status": status,
                "title": _sanitize_text(title),
                "summary": summary,
                "preview": preview,
                "parent_event_id": parent_event_id,
                "tool_use_id": tool_use_id,
                "raw": item.get("raw") or {},
            }
        )

    return events


def summarize_event_counts(events: list[dict[str, Any]]) -> dict[str, int]:
    """Count event kinds for session cards."""
    counts = {
        "thinking": 0,
        "tool_call": 0,
        "tool_result": 0,
        "output": 0,
    }

    for event in events:
        kind = event.get("kind")
        if kind == "assistant_thinking":
            counts["thinking"] += 1
        elif kind == "tool_call":
            counts["tool_call"] += 1
        elif kind == "tool_result":
            counts["tool_result"] += 1
        elif kind == "assistant_output":
            counts["output"] += 1

    return counts


def _parse_log_items(log_path: Path) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []

    try:
        with log_path.open("rb") as handle:
            while True:
                offset = handle.tell()
                raw_line = handle.readline()
                if not raw_line:
                    break

                line = raw_line.decode("utf-8", errors="ignore").strip()
                if not line:
                    continue

                try:
                    payload = json.loads(line)
                except json.JSONDecodeError:
                    continue

                item_ts = _normalize_ts(payload.get("timestamp"))
                payload_type = _sanitize_text(payload.get("type"))
                message = payload.get("message")

                if payload_type == "assistant" and isinstance(message, dict):
                    items.extend(_parse_assistant_items(message, payload, offset, item_ts))
                    continue

                if payload_type == "user" and isinstance(message, dict):
                    items.extend(_parse_user_items(message, payload, offset, item_ts))
                    continue
    except OSError:
        return []

    return items


def _parse_assistant_items(
    message: dict[str, Any],
    payload: dict[str, Any],
    offset: int,
    item_ts: str,
) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    content = message.get("content")

    if isinstance(content, str):
        value = _sanitize_text(content)
        if value:
            items.append(
                {
                    "kind": "assistant_text",
                    "ts": item_ts,
                    "offset": offset,
                    "part_index": 0,
                    "title": "Assistant",
                    "text": value,
                    "status": "ok",
                    "raw": {"text": value},
                }
            )
        return items

    if not isinstance(content, list):
        return items

    for part_index, part in enumerate(content):
        if not isinstance(part, dict):
            continue

        part_type = _sanitize_text(part.get("type"))

        if part_type == "thinking":
            text_value = _sanitize_text(part.get("thinking"))
            if not text_value:
                continue
            items.append(
                {
                    "kind": "assistant_thinking",
                    "ts": item_ts,
                    "offset": offset,
                    "part_index": part_index,
                    "title": "Thinking",
                    "text": text_value,
                    "status": "ok",
                    "raw": {"thinking": text_value},
                }
            )
            continue

        if part_type == "tool_use":
            tool_name = _sanitize_text(part.get("name")) or "tool"
            tool_input = part.get("input")
            items.append(
                {
                    "kind": "tool_call",
                    "ts": item_ts,
                    "offset": offset,
                    "part_index": part_index,
                    "title": tool_name,
                    "text": _format_tool_input(tool_input),
                    "status": "running",
                    "tool_use_id": _sanitize_text(part.get("id")),
                    "raw": {
                        "name": tool_name,
                        "tool_use_id": _sanitize_text(part.get("id")),
                        "input": tool_input,
                    },
                }
            )
            continue

        if part_type == "text":
            text_value = _sanitize_text(part.get("text"))
            if not text_value:
                continue
            items.append(
                {
                    "kind": "assistant_text",
                    "ts": item_ts,
                    "offset": offset,
                    "part_index": part_index,
                    "title": "Assistant",
                    "text": text_value,
                    "status": "ok",
                    "raw": {"text": text_value},
                }
            )

    return items


def _parse_user_items(
    message: dict[str, Any],
    payload: dict[str, Any],
    offset: int,
    item_ts: str,
) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    content = message.get("content")
    if not isinstance(content, list):
        return items

    for part_index, part in enumerate(content):
        if not isinstance(part, dict):
            continue
        if _sanitize_text(part.get("type")) != "tool_result":
            continue

        text_value = _extract_tool_result_text(part.get("content"))
        is_error = bool(part.get("is_error"))
        status = "error" if is_error else "ok"
        tool_use_id = _sanitize_text(part.get("tool_use_id"))

        items.append(
            {
                "kind": "tool_result",
                "ts": item_ts,
                "offset": offset,
                "part_index": part_index,
                "title": "Tool Result",
                "text": text_value,
                "status": status,
                "tool_use_id": tool_use_id,
                "raw": {
                    "tool_use_id": tool_use_id,
                    "is_error": is_error,
                    "content": part.get("content"),
                },
            }
        )

    return items


def _extract_tool_result_text(content: Any) -> str:
    if isinstance(content, str):
        return _sanitize_text(content)

    if isinstance(content, list):
        chunks: list[str] = []
        for part in content:
            if isinstance(part, str):
                chunks.append(part)
                continue
            if isinstance(part, dict):
                text_part = _sanitize_text(part.get("text"))
                if text_part:
                    chunks.append(text_part)
        return _sanitize_text("\n".join(chunks))

    if isinstance(content, dict):
        return _sanitize_text(content.get("text"))

    return ""


def _format_tool_input(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return _sanitize_text(value)
    try:
        return _sanitize_text(json.dumps(value, ensure_ascii=False, sort_keys=True))
    except TypeError:
        return _sanitize_text(str(value))


def _default_title(kind: str) -> str:
    title_map = {
        "user_command": "User Command",
        "assistant_thinking": "Thinking",
        "assistant_observation": "Observation",
        "assistant_output": "Assistant Output",
        "tool_call": "Tool Call",
        "tool_result": "Tool Result",
    }
    return title_map.get(kind, "Event")


def _normalize_ts(value: Any) -> str:
    if isinstance(value, str):
        return value
    return ""


def _sanitize_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    return str(value).strip()


def _shorten(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return text[: limit - 1] + "…"

