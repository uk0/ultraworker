"""Tests for reaction-based automatic approval handler."""

from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from ultrawork.slack.reaction_approval import (
    APPROVE_REACTIONS,
    REJECT_REACTIONS,
    ApprovalResult,
    PendingApprovalTracker,
    ReactionApprovalHandler,
)


class TestApprovalResult:
    def test_creation(self) -> None:
        result = ApprovalResult("TASK-001", "todo", "approved", "U123")
        assert result.task_id == "TASK-001"
        assert result.stage == "todo"
        assert result.action == "approved"
        assert result.user_id == "U123"

    def test_repr(self) -> None:
        result = ApprovalResult("TASK-001", "todo", "pending")
        assert "TASK-001" in repr(result)
        assert "pending" in repr(result)


class TestReactionConstants:
    def test_approve_reactions(self) -> None:
        assert "thumbsup" in APPROVE_REACTIONS
        assert "+1" in APPROVE_REACTIONS
        assert "white_check_mark" in APPROVE_REACTIONS

    def test_reject_reactions(self) -> None:
        assert "thumbsdown" in REJECT_REACTIONS
        assert "-1" in REJECT_REACTIONS
        assert "x" in REJECT_REACTIONS


class TestPendingApprovalTracker:
    def test_register_and_get_pending(self, tmp_path: Path) -> None:
        tracker = PendingApprovalTracker(tmp_path)
        tracker.register_approval_message(
            task_id="TASK-001",
            stage="todo",
            channel_id="C123",
            message_ts="1234567890.000000",
            thread_ts="1234567890.000000",
        )

        pending = tracker.get_pending()
        assert len(pending) == 1
        assert pending[0]["task_id"] == "TASK-001"
        assert pending[0]["channel_id"] == "C123"

    def test_register_updates_duplicate(self, tmp_path: Path) -> None:
        tracker = PendingApprovalTracker(tmp_path)
        tracker.register_approval_message(
            task_id="TASK-001",
            stage="todo",
            channel_id="C123",
            message_ts="1111111111.000000",
        )
        tracker.register_approval_message(
            task_id="TASK-001",
            stage="todo",
            channel_id="C456",
            message_ts="2222222222.000000",
        )

        pending = tracker.get_pending()
        assert len(pending) == 1
        assert pending[0]["channel_id"] == "C456"

    def test_mark_processed(self, tmp_path: Path) -> None:
        tracker = PendingApprovalTracker(tmp_path)
        tracker.register_approval_message(
            task_id="TASK-001",
            stage="todo",
            channel_id="C123",
            message_ts="1234567890.000000",
        )
        tracker.mark_processed("TASK-001", "todo", "approved", "U123")

        pending = tracker.get_pending()
        assert len(pending) == 0

        data = tracker.load()
        assert len(data["processed"]) == 1
        assert data["processed"][0]["action"] == "approved"

    def test_empty_tracker(self, tmp_path: Path) -> None:
        tracker = PendingApprovalTracker(tmp_path)
        assert tracker.get_pending() == []


class TestReactionApprovalHandler:
    @pytest.fixture
    def handler(self, tmp_path: Path) -> ReactionApprovalHandler:
        """Create a handler with mocked Slack client."""
        with patch("ultrawork.slack.reaction_approval.WebClient"):
            h = ReactionApprovalHandler(
                slack_token="xoxb-test-token",
                data_dir=tmp_path,
            )
            h.client = MagicMock()
            return h

    def test_evaluate_reactions_approve(self, handler: ReactionApprovalHandler) -> None:
        reactions = [
            {"name": "thumbsup", "users": ["U123"], "count": 1},
        ]
        action, user_id = handler._evaluate_reactions(reactions)
        assert action == "approved"
        assert user_id == "U123"

    def test_evaluate_reactions_reject(self, handler: ReactionApprovalHandler) -> None:
        reactions = [
            {"name": "thumbsdown", "users": ["U456"], "count": 1},
        ]
        action, user_id = handler._evaluate_reactions(reactions)
        assert action == "rejected"
        assert user_id == "U456"

    def test_evaluate_reactions_no_match(self, handler: ReactionApprovalHandler) -> None:
        reactions = [
            {"name": "heart", "users": ["U123"], "count": 1},
        ]
        action, _ = handler._evaluate_reactions(reactions)
        assert action is None

    def test_evaluate_reactions_empty(self, handler: ReactionApprovalHandler) -> None:
        action, _ = handler._evaluate_reactions([])
        assert action is None

    def test_evaluate_reactions_no_users(self, handler: ReactionApprovalHandler) -> None:
        reactions = [
            {"name": "thumbsup", "users": [], "count": 0},
        ]
        action, _ = handler._evaluate_reactions(reactions)
        assert action is None

    def test_process_approval(self, handler: ReactionApprovalHandler) -> None:
        """Test that approval updates task file correctly."""
        handler.context_manager = MagicMock()

        from ultrawork.models.task import (
            StageInfo,
            StageStatus,
            TaskRecord,
            TaskSource,
            WorkflowStage,
            WorkflowState,
            WorkflowType,
        )

        mock_task = TaskRecord(
            task_id="TASK-TEST-001",
            title="Test Task",
            created_at=datetime(2026, 1, 1),
            updated_at=datetime(2026, 1, 1),
            source=TaskSource(),
            workflow=WorkflowState(
                current_stage=WorkflowStage.TODO,
                type=WorkflowType.FULL,
                stages={
                    "todo": StageInfo(status=StageStatus.PENDING),
                    "tech_spec": StageInfo(status=StageStatus.PENDING),
                    "code_work": StageInfo(status=StageStatus.PENDING),
                    "final_report": StageInfo(status=StageStatus.PENDING),
                },
            ),
        )
        handler.context_manager.get_task_record.return_value = mock_task

        result = handler._process_approval("TASK-TEST-001", "U123")
        assert result is True
        assert mock_task.workflow.stages["todo"].status == StageStatus.APPROVED
        assert mock_task.workflow.stages["todo"].approved_by == "U123"
        assert mock_task.workflow.current_stage == WorkflowStage.TECH_SPEC

    def test_process_approval_nonexistent_task(self, handler: ReactionApprovalHandler) -> None:
        handler.context_manager = MagicMock()
        handler.context_manager.get_task_record.return_value = None

        result = handler._process_approval("TASK-NOPE", "U123")
        assert result is False

    def test_process_approval_already_approved(self, handler: ReactionApprovalHandler) -> None:
        handler.context_manager = MagicMock()

        from ultrawork.models.task import (
            StageInfo,
            StageStatus,
            TaskRecord,
            TaskSource,
            WorkflowStage,
            WorkflowState,
        )

        mock_task = TaskRecord(
            task_id="TASK-TEST-002",
            title="Already Approved",
            created_at=datetime(2026, 1, 1),
            updated_at=datetime(2026, 1, 1),
            source=TaskSource(),
            workflow=WorkflowState(
                current_stage=WorkflowStage.TODO,
                stages={
                    "todo": StageInfo(status=StageStatus.APPROVED),
                    "tech_spec": StageInfo(),
                    "code_work": StageInfo(),
                    "final_report": StageInfo(),
                },
            ),
        )
        handler.context_manager.get_task_record.return_value = mock_task

        result = handler._process_approval("TASK-TEST-002", "U123")
        assert result is False

    def test_process_rejection(self, handler: ReactionApprovalHandler) -> None:
        handler.context_manager = MagicMock()

        from ultrawork.models.task import (
            StageInfo,
            StageStatus,
            TaskRecord,
            TaskSource,
            WorkflowStage,
            WorkflowState,
        )

        mock_task = TaskRecord(
            task_id="TASK-TEST-003",
            title="To Reject",
            created_at=datetime(2026, 1, 1),
            updated_at=datetime(2026, 1, 1),
            source=TaskSource(),
            workflow=WorkflowState(
                current_stage=WorkflowStage.TODO,
                stages={
                    "todo": StageInfo(status=StageStatus.PENDING),
                    "tech_spec": StageInfo(),
                    "code_work": StageInfo(),
                    "final_report": StageInfo(),
                },
            ),
        )
        handler.context_manager.get_task_record.return_value = mock_task

        result = handler._process_rejection("TASK-TEST-003", "U456", "Not ready")
        assert result is True
        assert mock_task.workflow.stages["todo"].status == StageStatus.REJECTED
        assert mock_task.workflow.stages["todo"].rejected_by == "U456"
        assert mock_task.workflow.stages["todo"].rejection_reason == "Not ready"

    def test_get_message_reactions(self, handler: ReactionApprovalHandler) -> None:
        handler.client.reactions_get.return_value = {
            "message": {
                "reactions": [
                    {"name": "thumbsup", "users": ["U123"], "count": 1},
                ]
            }
        }

        reactions = handler._get_message_reactions("C123", "1234567890.000000")
        assert len(reactions) == 1
        assert reactions[0]["name"] == "thumbsup"

    def test_get_message_reactions_no_reactions(self, handler: ReactionApprovalHandler) -> None:
        handler.client.reactions_get.return_value = {"message": {}}

        reactions = handler._get_message_reactions("C123", "1234567890.000000")
        assert reactions == []

    def test_discover_pending_from_tasks(self, handler: ReactionApprovalHandler, tmp_path: Path) -> None:
        """Test that pending tasks can be discovered from task files."""
        tasks_dir = tmp_path / "tasks"
        tasks_dir.mkdir(parents=True, exist_ok=True)

        task_content = """---
task_id: "TASK-DISC-001"
title: "Discoverable Task"
created_at: "2026-01-01T00:00:00"
updated_at: "2026-01-01T00:00:00"
source:
  type: "slack_mention"
  channel_id: "C0ABC"
  thread_ts: "1706500000.000000"
workflow:
  type: "simple"
  current_stage: "todo"
  stages:
    todo:
      status: "pending"
    final_report:
      status: "pending"
---

## TODO
- [ ] Do something
"""
        (tasks_dir / "TASK-DISC-001.md").write_text(task_content, encoding="utf-8")

        handler.context_manager.tasks_dir = tasks_dir
        pending = handler._discover_pending_from_tasks()

        assert len(pending) == 1
        assert pending[0]["task_id"] == "TASK-DISC-001"
        assert pending[0]["channel_id"] == "C0ABC"
        assert pending[0]["thread_ts"] == "1706500000.000000"

    def test_discover_skips_done_tasks(self, handler: ReactionApprovalHandler, tmp_path: Path) -> None:
        tasks_dir = tmp_path / "tasks"
        tasks_dir.mkdir(parents=True, exist_ok=True)

        task_content = """---
task_id: "TASK-DONE-001"
title: "Done Task"
created_at: "2026-01-01T00:00:00"
updated_at: "2026-01-01T00:00:00"
source:
  type: "slack_mention"
  channel_id: "C0ABC"
  thread_ts: "1706500000.000000"
workflow:
  type: "simple"
  current_stage: "done"
  stages:
    todo:
      status: "approved"
    final_report:
      status: "approved"
---
"""
        (tasks_dir / "TASK-DONE-001.md").write_text(task_content, encoding="utf-8")

        handler.context_manager.tasks_dir = tasks_dir
        pending = handler._discover_pending_from_tasks()
        assert len(pending) == 0


class TestCheckAndProcess:
    @pytest.fixture
    def handler(self, tmp_path: Path) -> ReactionApprovalHandler:
        with patch("ultrawork.slack.reaction_approval.WebClient"):
            h = ReactionApprovalHandler(
                slack_token="xoxb-test",
                data_dir=tmp_path,
            )
            h.client = MagicMock()
            return h

    def test_no_pending_returns_empty(self, handler: ReactionApprovalHandler, tmp_path: Path) -> None:
        import asyncio

        handler.context_manager.tasks_dir = tmp_path / "tasks"
        handler.context_manager.tasks_dir.mkdir(parents=True, exist_ok=True)

        results = asyncio.get_event_loop().run_until_complete(handler.check_and_process())
        assert results == []

    def test_pending_with_no_reactions(self, handler: ReactionApprovalHandler) -> None:
        import asyncio

        handler.tracker.register_approval_message(
            task_id="TASK-001",
            stage="todo",
            channel_id="C123",
            message_ts="1234567890.000000",
            thread_ts="1234567890.000000",
        )

        # No reactions on message
        handler.client.reactions_get.return_value = {"message": {}}
        # No approval reactions in thread
        handler.client.conversations_replies.return_value = {"messages": []}

        results = asyncio.get_event_loop().run_until_complete(handler.check_and_process())
        assert len(results) == 1
        assert results[0].action == "pending"

    def test_pending_with_approval_reaction(self, handler: ReactionApprovalHandler) -> None:
        import asyncio

        handler.tracker.register_approval_message(
            task_id="TASK-001",
            stage="todo",
            channel_id="C123",
            message_ts="1234567890.000000",
            thread_ts="1234567890.000000",
        )

        # Approval reaction on message
        handler.client.reactions_get.return_value = {
            "message": {
                "reactions": [
                    {"name": "thumbsup", "users": ["U999"], "count": 1},
                ]
            }
        }

        # Mock process_approval
        handler._process_approval = MagicMock(return_value=True)  # type: ignore[method-assign]
        handler._send_notification = MagicMock()  # type: ignore[method-assign]
        handler._trigger_next_stage = MagicMock()  # type: ignore[method-assign]
        handler.context_manager = MagicMock()
        handler.context_manager.get_task_record.return_value = MagicMock(
            workflow=MagicMock(current_stage=MagicMock(value="tech_spec"))
        )

        results = asyncio.get_event_loop().run_until_complete(handler.check_and_process())
        assert len(results) == 1
        assert results[0].action == "approved"
        assert results[0].user_id == "U999"
        handler._process_approval.assert_called_once_with("TASK-001", "U999")
