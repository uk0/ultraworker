import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
import yaml

from ultrawork.agent.session_manager import SessionManager
from ultrawork.dashboard.server import (
    DashboardConfig,
    _build_session_worktree,
    _build_thread_sessions,
    _build_threads,
    _handle_create_thread_session,
    _handle_terminate_thread_session,
)


def _write_yaml(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(payload, allow_unicode=True, sort_keys=False), encoding="utf-8")


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def _create_mention(
    data_dir: Path,
    mention_id: str,
    *,
    channel_id: str,
    thread_ts: str,
    message_ts: str,
    text: str,
    session_id: str,
    created_at: str,
) -> None:
    mention_dir = data_dir / "mentions" / mention_id
    _write_yaml(
        mention_dir / "input.yaml",
        {
            "channel_id": channel_id,
            "thread_ts": thread_ts,
            "message_ts": message_ts,
            "text": text,
            "created_at": created_at,
            "user": "U1",
        },
    )
    _write_yaml(
        mention_dir / "session.yaml",
        {
            "session_id": session_id,
            "status": "completed",
            "created_at": created_at,
        },
    )


def _cfg(tmp_path: Path) -> DashboardConfig:
    return DashboardConfig(
        data_dir=tmp_path / "data",
        log_root=tmp_path / "logs",
        host="127.0.0.1",
        port=7878,
    )


def test_build_threads_merges_legacy_thread_keys_and_removes_untitled(tmp_path: Path) -> None:
    cfg = _cfg(tmp_path)
    manager = SessionManager(cfg.data_dir)

    session = manager.create_session(
        channel_id="C100",
        thread_ts="1700.100",
        user_id="U1",
        message="fallback original message",
        trigger_type="mention",
    )

    # Intentionally wrong legacy index key; canonical key should come from mention.
    manager.register_thread_session("C100", "1700.999", session.session_id)

    _create_mention(
        cfg.data_dir,
        "m-001",
        channel_id="C100",
        thread_ts="1700.100",
        message_ts="1700.100",
        text="Real mention title",
        session_id=session.session_id,
        created_at="2026-02-06T12:00:00Z",
    )

    payload = _build_threads(cfg, page=1, page_size=5)

    assert payload["total"] == 1
    assert payload["total_pages"] == 1
    thread = payload["threads"][0]

    assert thread["thread_key"] == "C100_1700.100"
    assert thread["thread_id"] == "C100-1700.100"
    assert "Untitled" not in thread["title"]


def test_build_threads_supports_five_item_pagination(tmp_path: Path) -> None:
    cfg = _cfg(tmp_path)

    # Mentions-only threads are enough to build thread pages.
    for index in range(7):
        ts = f"1700.{index}"
        _create_mention(
            cfg.data_dir,
            f"m-{index}",
            channel_id="CPAGE",
            thread_ts=ts,
            message_ts=ts,
            text=f"thread {index}",
            session_id=f"sess-{index}",
            created_at=f"2026-02-06T12:0{index}:00Z",
        )

    page1 = _build_threads(cfg, page=1, page_size=5)
    page2 = _build_threads(cfg, page=2, page_size=5)

    assert page1["total"] == 7
    assert page1["page"] == 1
    assert page1["page_size"] == 5
    assert page1["total_pages"] == 2
    assert len(page1["threads"]) == 5

    assert page2["page"] == 2
    assert len(page2["threads"]) == 2


def test_build_session_worktree_supports_tail_and_before_seq_chunking(tmp_path: Path) -> None:
    cfg = _cfg(tmp_path)
    manager = SessionManager(cfg.data_dir)

    session = manager.create_session(
        channel_id="CWT",
        thread_ts="1700.777",
        user_id="U1",
        message="check logs",
        trigger_type="mention",
    )
    manager.register_thread_session("CWT", "1700.777", session.session_id)

    _create_mention(
        cfg.data_dir,
        "m-wt",
        channel_id="CWT",
        thread_ts="1700.777",
        message_ts="1700.777",
        text="analyze session",
        session_id=session.session_id,
        created_at="2026-02-06T10:00:00Z",
    )

    _write_jsonl(
        cfg.log_root / "project" / f"{session.session_id}.jsonl",
        [
            {
                "type": "assistant",
                "timestamp": "2026-02-06T10:00:01Z",
                "message": {
                    "role": "assistant",
                    "content": [
                        {"type": "thinking", "thinking": "first think"},
                        {"type": "text", "text": "observe"},
                        {
                            "type": "tool_use",
                            "id": "toolu_1",
                            "name": "Bash",
                            "input": {"command": "echo hi"},
                        },
                    ],
                },
            },
            {
                "type": "user",
                "timestamp": "2026-02-06T10:00:02Z",
                "message": {
                    "role": "user",
                    "content": [
                        {
                            "type": "tool_result",
                            "tool_use_id": "toolu_1",
                            "content": "ok",
                        }
                    ],
                },
            },
            {
                "type": "assistant",
                "timestamp": "2026-02-06T10:00:03Z",
                "message": {
                    "role": "assistant",
                    "content": [{"type": "text", "text": "final output"}],
                },
            },
        ],
    )

    tail_payload = _build_session_worktree(
        cfg,
        channel_id="CWT",
        thread_ts="1700.777",
        session_id=session.session_id,
        limit=2,
    )

    assert tail_payload["total_events"] == 6
    assert [event["seq"] for event in tail_payload["events"]] == [5, 6]
    assert tail_payload["range_start_seq"] == 5
    assert tail_payload["range_end_seq"] == 6
    assert tail_payload["has_older"] is True

    older_payload = _build_session_worktree(
        cfg,
        channel_id="CWT",
        thread_ts="1700.777",
        session_id=session.session_id,
        before_seq=5,
        limit=2,
    )

    assert [event["seq"] for event in older_payload["events"]] == [3, 4]
    assert older_payload["has_older"] is True

    cursor_payload = _build_session_worktree(
        cfg,
        channel_id="CWT",
        thread_ts="1700.777",
        session_id=session.session_id,
        cursor=6,
    )

    assert cursor_payload["events"] == []


def test_handle_create_thread_session_creates_manual_session(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cfg = _cfg(tmp_path)

    def _fake_start_executor(**kwargs):  # noqa: ANN003
        _ = kwargs
        return True, 12345, None

    monkeypatch.setattr(
        "ultrawork.dashboard.server._start_manual_session_executor",
        _fake_start_executor,
    )

    payload, status = _handle_create_thread_session(
        cfg,
        channel_id="CCREATE",
        thread_ts="1700.200",
        data={"message": "run this task", "user_id": "U2", "run_executor": "claude"},
    )

    assert status == 202
    assert payload["ok"] is True
    assert payload["run"]["started"] is True
    assert payload["run"]["pid"] == 12345

    session_id = payload["session"]["session_id"]
    manager = SessionManager(cfg.data_dir)
    session = manager.get_session(session_id)
    assert session is not None
    assert session.trigger_type == "manual"
    assert session.channel_id == "CCREATE"
    assert session.thread_ts == "1700.200"


def test_build_thread_sessions_includes_request_full(tmp_path: Path) -> None:
    cfg = _cfg(tmp_path)
    manager = SessionManager(cfg.data_dir)

    session_with_mention = manager.create_session(
        channel_id="CFULL",
        thread_ts="1700.900",
        user_id="U1",
        message="session fallback message",
        trigger_type="mention",
    )
    manager.register_thread_session("CFULL", "1700.900", session_with_mention.session_id)
    _create_mention(
        cfg.data_dir,
        "m-full-1",
        channel_id="CFULL",
        thread_ts="1700.900",
        message_ts="1700.900",
        text="<@U123ABCD> mention priority message",
        session_id=session_with_mention.session_id,
        created_at="2026-02-06T12:00:00Z",
    )

    session_without_mention = manager.create_session(
        channel_id="CFULL",
        thread_ts="1700.900",
        user_id="U1",
        message="original session message only",
        trigger_type="manual",
    )
    manager.register_thread_session("CFULL", "1700.900", session_without_mention.session_id)

    payload = _build_thread_sessions(cfg, "CFULL", "1700.900")
    by_id = {item["session_id"]: item for item in payload["sessions"]}

    assert (
        by_id[session_with_mention.session_id]["request_full"]
        == "<@U123ABCD> mention priority message"
    )
    assert (
        by_id[session_without_mention.session_id]["request_full"] == "original session message only"
    )


def test_handle_create_thread_session_injects_context_into_executor_prompt(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cfg = _cfg(tmp_path)
    captured: dict[str, str] = {}

    def _fake_collect_context(*args, **kwargs):  # noqa: ANN002,ANN003
        _ = args, kwargs
        return {
            "thread_summary": "Shipping thread summary",
            "recent_messages": [
                {
                    "speaker": "user",
                    "ts": "2026-02-06T12:00:00Z",
                    "text": "Previous user instruction",
                }
            ],
            "recent_sessions": [
                {
                    "session_id": "sess-prev",
                    "status": "completed",
                    "updated_at": "2026-02-06T12:05:00Z",
                    "message": "Prior completed attempt",
                }
            ],
        }

    def _fake_start_executor(**kwargs):  # noqa: ANN003
        captured["message"] = str(kwargs.get("message") or "")
        return True, 12345, None

    monkeypatch.setattr(
        "ultrawork.dashboard.server._collect_thread_context_for_manual_run",
        _fake_collect_context,
    )
    monkeypatch.setattr(
        "ultrawork.dashboard.server._start_manual_session_executor",
        _fake_start_executor,
    )

    payload, status = _handle_create_thread_session(
        cfg,
        channel_id="CCONTEXT",
        thread_ts="1700.400",
        data={"message": "run this task", "user_id": "U2", "run_executor": "claude"},
    )

    assert status == 202
    assert payload["ok"] is True
    assert payload["run"]["context_applied"] is True
    assert payload["run"]["context_chars"] > 0
    assert "Context:" in captured["message"]
    assert "Recent Thread Messages:" in captured["message"]
    assert "Previous Sessions In This Thread:" in captured["message"]
    assert "New Request:\nrun this task" in captured["message"]

    session_id = payload["session"]["session_id"]
    stored = SessionManager(cfg.data_dir).get_session(session_id)
    assert stored is not None
    assert stored.original_message == "run this task"


def test_handle_create_thread_session_context_fallback_on_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cfg = _cfg(tmp_path)
    captured: dict[str, str] = {}

    def _raise_collect_context(*args, **kwargs):  # noqa: ANN002,ANN003
        _ = args, kwargs
        raise RuntimeError("context build failed")

    def _fake_start_executor(**kwargs):  # noqa: ANN003
        captured["message"] = str(kwargs.get("message") or "")
        return True, 12345, None

    monkeypatch.setattr(
        "ultrawork.dashboard.server._collect_thread_context_for_manual_run",
        _raise_collect_context,
    )
    monkeypatch.setattr(
        "ultrawork.dashboard.server._start_manual_session_executor",
        _fake_start_executor,
    )

    payload, status = _handle_create_thread_session(
        cfg,
        channel_id="CFALLBACK",
        thread_ts="1700.401",
        data={"message": "raw prompt only", "user_id": "U2", "run_executor": "claude"},
    )

    assert status == 202
    assert payload["run"]["context_applied"] is False
    assert payload["run"]["context_chars"] == 0
    assert captured["message"] == "raw prompt only"


def test_handle_terminate_thread_session_marks_cancelled(tmp_path: Path) -> None:
    cfg = _cfg(tmp_path)
    manager = SessionManager(cfg.data_dir)
    session = manager.create_session(
        channel_id="CTERM",
        thread_ts="1700.300",
        user_id="U3",
        message="terminate me",
        trigger_type="manual",
    )
    manager.register_thread_session("CTERM", "1700.300", session.session_id)

    payload, status = _handle_terminate_thread_session(
        cfg,
        channel_id="CTERM",
        thread_ts="1700.300",
        session_id=session.session_id,
        data={"reason": "user_stop", "force": True},
    )

    assert status == 200
    assert payload["ok"] is True
    assert payload["was_running"] is False
    assert payload["terminated"] is False
    assert payload["status"] == "cancelled"

    refreshed = SessionManager(cfg.data_dir).get_session(session.session_id)
    assert refreshed is not None
    assert refreshed.status.value == "cancelled"


def test_build_thread_sessions_marks_stalled_without_heartbeat(tmp_path: Path) -> None:
    cfg = _cfg(tmp_path)
    manager = SessionManager(cfg.data_dir)

    session = manager.create_session(
        channel_id="CSTALL",
        thread_ts="1999.001",
        user_id="U1",
        message="stalled request",
        trigger_type="mention",
    )
    manager.register_thread_session("CSTALL", "1999.001", session.session_id)
    _create_mention(
        cfg.data_dir,
        "m-stalled",
        channel_id="CSTALL",
        thread_ts="1999.001",
        message_ts="1999.001",
        text="run long task",
        session_id=session.session_id,
        created_at="2026-02-06T12:00:00Z",
    )

    started_at = (datetime.now(timezone.utc) - timedelta(minutes=20)).isoformat()
    _write_jsonl(
        cfg.data_dir / "logs" / "interactions.jsonl",
        [
            {
                "timestamp": started_at,
                "type": "processing_started",
                "session_id": session.session_id,
                "channel_id": "CSTALL",
                "thread_ts": "1999.001",
                "content": f"Starting new session {session.session_id}",
                "metadata": {},
            }
        ],
    )

    payload = _build_thread_sessions(cfg, "CSTALL", "1999.001")
    by_id = {item["session_id"]: item for item in payload["sessions"]}
    stalled = by_id[session.session_id]

    assert stalled["status"] == "stalled"
    assert int(stalled["elapsed_seconds"]) >= 1000


def test_build_thread_sessions_uses_heartbeat_runtime_metadata(tmp_path: Path) -> None:
    cfg = _cfg(tmp_path)
    manager = SessionManager(cfg.data_dir)

    session = manager.create_session(
        channel_id="CHEART",
        thread_ts="1999.002",
        user_id="U1",
        message="heartbeat request",
        trigger_type="mention",
    )
    manager.register_thread_session("CHEART", "1999.002", session.session_id)
    _create_mention(
        cfg.data_dir,
        "m-heartbeat",
        channel_id="CHEART",
        thread_ts="1999.002",
        message_ts="1999.002",
        text="run long task with heartbeat",
        session_id=session.session_id,
        created_at="2026-02-06T12:00:00Z",
    )

    started_at = (datetime.now(timezone.utc) - timedelta(seconds=90)).isoformat()
    heartbeat_at = (datetime.now(timezone.utc) - timedelta(seconds=15)).isoformat()
    _write_jsonl(
        cfg.data_dir / "logs" / "interactions.jsonl",
        [
            {
                "timestamp": started_at,
                "type": "processing_started",
                "session_id": session.session_id,
                "channel_id": "CHEART",
                "thread_ts": "1999.002",
                "content": f"Starting new session {session.session_id}",
                "metadata": {},
            },
            {
                "timestamp": heartbeat_at,
                "type": "processing_heartbeat",
                "session_id": session.session_id,
                "channel_id": "CHEART",
                "thread_ts": "1999.002",
                "content": "Still running",
                "metadata": {"elapsed_seconds": 75, "pid": 4242},
            },
        ],
    )

    payload = _build_thread_sessions(cfg, "CHEART", "1999.002")
    by_id = {item["session_id"]: item for item in payload["sessions"]}
    active = by_id[session.session_id]

    assert active["status"] == "active"
    assert int(active["elapsed_seconds"]) >= 75
    assert active["runner_pid"] == 4242
