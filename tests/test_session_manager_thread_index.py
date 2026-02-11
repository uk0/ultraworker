from pathlib import Path

import yaml

from ultrawork.agent.session_manager import SessionManager


def test_register_thread_session_appends_list_and_returns_latest(tmp_path: Path) -> None:
    manager = SessionManager(tmp_path)

    session_one = manager.create_session(
        channel_id="C123",
        thread_ts="1700.123",
        user_id="U1",
        message="first",
        trigger_type="mention",
    )
    manager.register_thread_session("C123", "1700.123", session_one.session_id)

    session_two = manager.create_session(
        channel_id="C123",
        thread_ts="1700.123",
        user_id="U1",
        message="second",
        trigger_type="mention",
    )
    manager.register_thread_session("C123", "1700.123", session_two.session_id)

    index_path = Path(tmp_path) / "index" / "thread_sessions.yaml"
    payload = yaml.safe_load(index_path.read_text(encoding="utf-8"))
    mapped = payload["threads"]["C123_1700.123"]

    assert mapped == [session_one.session_id, session_two.session_id]

    sessions = manager.get_sessions_by_thread("C123", "1700.123")
    assert [session.session_id for session in sessions] == [
        session_one.session_id,
        session_two.session_id,
    ]

    latest = manager.get_session_by_thread("C123", "1700.123")
    assert latest is not None
    assert latest.session_id == session_two.session_id


def test_cancel_session_sets_cancelled_and_completed_at(tmp_path: Path) -> None:
    manager = SessionManager(tmp_path)
    session = manager.create_session(
        channel_id="C777",
        thread_ts="1777.777",
        user_id="U7",
        message="cancel target",
        trigger_type="manual",
    )

    ok = manager.cancel_session(session.session_id, reason="user_stop")
    assert ok is True

    refreshed = manager.get_session(session.session_id)
    assert refreshed is not None
    assert refreshed.status.value == "cancelled"
    assert refreshed.completed_at is not None
