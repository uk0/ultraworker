import json
from pathlib import Path

from ultrawork.dashboard.worktree_parser import (
    parse_session_worktree_events,
    summarize_event_counts,
)


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def test_parse_session_worktree_events_maps_core_types(tmp_path: Path) -> None:
    log_path = tmp_path / "session.jsonl"
    _write_jsonl(
        log_path,
        [
            {
                "type": "assistant",
                "timestamp": "2026-02-06T10:00:00Z",
                "message": {
                    "role": "assistant",
                    "content": [
                        {"type": "thinking", "thinking": "먼저 확인합니다."},
                        {"type": "text", "text": "로그를 먼저 읽어보겠습니다."},
                        {
                            "type": "tool_use",
                            "id": "toolu_1",
                            "name": "mcp__slack__slack_get_thread",
                            "input": {"channel_id": "C123", "thread_ts": "1700.1"},
                        },
                    ],
                },
            },
            {
                "type": "user",
                "timestamp": "2026-02-06T10:00:01Z",
                "message": {
                    "role": "user",
                    "content": [
                        {
                            "type": "tool_result",
                            "tool_use_id": "toolu_1",
                            "content": [{"type": "text", "text": "ok: 3 replies"}],
                        }
                    ],
                },
            },
            {
                "type": "assistant",
                "timestamp": "2026-02-06T10:00:02Z",
                "message": {
                    "role": "assistant",
                    "content": [{"type": "text", "text": "결론: 이슈는 재현되지 않았습니다."}],
                },
            },
        ],
    )

    events = parse_session_worktree_events(
        session_id="sess-1",
        thread_key="C123_1700.1",
        log_path=log_path,
        command_text="스레드를 분석해줘",
        command_ts="2026-02-06T09:59:59Z",
    )

    kinds = [event["kind"] for event in events]
    assert kinds == [
        "user_command",
        "assistant_thinking",
        "assistant_observation",
        "tool_call",
        "tool_result",
        "assistant_output",
    ]

    tool_call_event = next(event for event in events if event["kind"] == "tool_call")
    tool_result_event = next(event for event in events if event["kind"] == "tool_result")

    assert tool_result_event["tool_use_id"] == "toolu_1"
    assert tool_result_event["parent_event_id"] == tool_call_event["event_id"]

    counts = summarize_event_counts(events)
    assert counts == {
        "thinking": 1,
        "tool_call": 1,
        "tool_result": 1,
        "output": 1,
    }


def test_parse_session_worktree_events_without_log_returns_command_only() -> None:
    events = parse_session_worktree_events(
        session_id="sess-2",
        thread_key="C123_1700.2",
        log_path=None,
        command_text="명령",
        command_ts="2026-02-06T10:01:00Z",
    )

    assert len(events) == 1
    assert events[0]["kind"] == "user_command"
    assert events[0]["summary"] == "명령"
