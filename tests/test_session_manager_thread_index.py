from datetime import datetime, timedelta
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


def test_get_forkable_session_respects_max_age(tmp_path: Path) -> None:
    manager = SessionManager(tmp_path)

    old_session = manager.create_session(
        channel_id="COLD",
        thread_ts="1777.100",
        user_id="U1",
        message="older fork source",
        trigger_type="mention",
    )
    manager.register_thread_session("COLD", "1777.100", old_session.session_id)
    manager.complete_session(old_session.session_id, success=True)

    old_session_refreshed = manager.get_session(old_session.session_id)
    assert old_session_refreshed is not None
    old_session_refreshed.completed_at = datetime.now() - timedelta(hours=3)
    old_session_refreshed.updated_at = old_session_refreshed.completed_at
    manager._save_session(old_session_refreshed)  # noqa: SLF001

    recent_session = manager.create_session(
        channel_id="COLD",
        thread_ts="1777.100",
        user_id="U1",
        message="recent fork source",
        trigger_type="mention",
    )
    manager.register_thread_session("COLD", "1777.100", recent_session.session_id)
    manager.complete_session(recent_session.session_id, success=True)

    forkable = manager.get_forkable_session_for_thread(
        "COLD",
        "1777.100",
        max_age_seconds=1800,
    )
    assert forkable is not None
    assert forkable.session_id == recent_session.session_id

    recent_session_refreshed = manager.get_session(recent_session.session_id)
    assert recent_session_refreshed is not None
    recent_session_refreshed.completed_at = datetime.now() - timedelta(hours=2)
    recent_session_refreshed.updated_at = recent_session_refreshed.completed_at
    manager._save_session(recent_session_refreshed)  # noqa: SLF001

    expired = manager.get_forkable_session_for_thread(
        "COLD",
        "1777.100",
        max_age_seconds=1800,
    )
    assert expired is None
