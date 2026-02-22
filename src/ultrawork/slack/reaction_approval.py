"""Reaction-based automatic approval handler for Slack.

Monitors Slack messages for approval/rejection reactions and automatically
processes workflow stage transitions when appropriate reactions are detected.

Approval reactions: thumbsup, +1, white_check_mark, heavy_check_mark
Rejection reactions: thumbsdown, -1, x, heavy_multiplication_x

Usage:
    handler = ReactionApprovalHandler(
        slack_token="xoxc-...",
        slack_cookie="xoxd-...",
        data_dir=Path("data"),
    )

    # Check and process all pending approvals
    results = await handler.check_and_process()
"""

import logging
import subprocess
import os
from datetime import datetime
from pathlib import Path

import yaml
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError

from ultrawork.agent.session_manager import SessionManager
from ultrawork.context.manager import ContextManager
from ultrawork.models.task import StageStatus

logger = logging.getLogger("reaction_approval")

# Reactions that count as approval
APPROVE_REACTIONS = frozenset({"thumbsup", "+1", "white_check_mark", "heavy_check_mark"})

# Reactions that count as rejection
REJECT_REACTIONS = frozenset({"thumbsdown", "-1", "x", "heavy_multiplication_x"})


class ApprovalResult:
    """Result of a single reaction-based approval check."""

    def __init__(
        self,
        task_id: str,
        stage: str,
        action: str,  # "approved", "rejected", "pending", "error"
        user_id: str = "",
        message: str = "",
    ):
        self.task_id = task_id
        self.stage = stage
        self.action = action
        self.user_id = user_id
        self.message = message
        self.timestamp = datetime.now()

    def __repr__(self) -> str:
        return f"ApprovalResult({self.task_id}, {self.stage}, {self.action})"


class PendingApprovalTracker:
    """Tracks which messages are pending approval reactions.

    Stores mapping of (channel_id, message_ts) -> task_id for messages
    that contain approval requests. This allows the handler to check
    reactions on specific messages rather than scanning all threads.
    """

    def __init__(self, data_dir: Path):
        self.data_dir = Path(data_dir)
        self.tracker_file = self.data_dir / "index" / "pending_approvals.yaml"
        self.tracker_file.parent.mkdir(parents=True, exist_ok=True)

    def load(self) -> dict:
        """Load pending approval tracker data."""
        if not self.tracker_file.exists():
            return {"pending": [], "processed": []}
        try:
            with open(self.tracker_file, encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
            return {
                "pending": data.get("pending", []),
                "processed": data.get("processed", []),
            }
        except Exception as e:
            logger.error(f"Failed to load tracker: {e}")
            return {"pending": [], "processed": []}

    def save(self, data: dict) -> None:
        """Save pending approval tracker data."""
        try:
            with open(self.tracker_file, "w", encoding="utf-8") as f:
                yaml.dump(data, f, allow_unicode=True, default_flow_style=False)
        except Exception as e:
            logger.error(f"Failed to save tracker: {e}")

    def register_approval_message(
        self,
        task_id: str,
        stage: str,
        channel_id: str,
        message_ts: str,
        thread_ts: str = "",
    ) -> None:
        """Register a message that is waiting for approval reactions."""
        data = self.load()
        # Avoid duplicates
        for entry in data["pending"]:
            if entry["task_id"] == task_id and entry["stage"] == stage:
                # Update existing entry
                entry["channel_id"] = channel_id
                entry["message_ts"] = message_ts
                entry["thread_ts"] = thread_ts
                entry["registered_at"] = datetime.now().isoformat()
                self.save(data)
                return

        data["pending"].append({
            "task_id": task_id,
            "stage": stage,
            "channel_id": channel_id,
            "message_ts": message_ts,
            "thread_ts": thread_ts,
            "registered_at": datetime.now().isoformat(),
        })
        self.save(data)
        logger.info(f"Registered approval message: {task_id} stage={stage} ts={message_ts}")

    def mark_processed(
        self,
        task_id: str,
        stage: str,
        action: str,
        user_id: str = "",
    ) -> None:
        """Mark an approval message as processed."""
        data = self.load()
        remaining = []
        for entry in data["pending"]:
            if entry["task_id"] == task_id and entry["stage"] == stage:
                entry["processed_at"] = datetime.now().isoformat()
                entry["action"] = action
                entry["processed_by"] = user_id
                data["processed"].append(entry)
            else:
                remaining.append(entry)
        data["pending"] = remaining
        # Keep only last 100 processed entries
        data["processed"] = data["processed"][-100:]
        self.save(data)

    def get_pending(self) -> list[dict]:
        """Get all pending approval entries."""
        data = self.load()
        return data.get("pending", [])


class ReactionApprovalHandler:
    """Handles automatic approval/rejection based on Slack reactions.

    Monitors pending approval messages for thumbsup/thumbsdown reactions
    and automatically triggers the /approve or /reject skill.
    """

    def __init__(
        self,
        slack_token: str,
        data_dir: Path,
        slack_cookie: str | None = None,
    ):
        headers = {}
        if slack_token.startswith("xoxc-") and slack_cookie:
            headers["Cookie"] = f"d={slack_cookie}"

        self.client = WebClient(token=slack_token, headers=headers)
        self.data_dir = Path(data_dir)
        self.tracker = PendingApprovalTracker(data_dir)
        self.context_manager = ContextManager(data_dir)

    def _get_message_reactions(
        self, channel_id: str, message_ts: str
    ) -> list[dict]:
        """Get reactions on a specific message.

        Returns:
            List of reaction dicts: [{"name": "thumbsup", "users": ["U123"], "count": 1}]
        """
        try:
            result = self.client.reactions_get(
                channel=channel_id,
                timestamp=message_ts,
                full=True,
            )
            message = result.get("message", {})
            return message.get("reactions", [])
        except SlackApiError as e:
            if "no_item_found" in str(e) or "message_not_found" in str(e):
                logger.debug(f"Message not found: {channel_id}/{message_ts}")
            else:
                logger.error(f"Failed to get reactions: {e}")
            return []

    def _check_thread_for_approval_reactions(
        self, channel_id: str, thread_ts: str
    ) -> tuple[str | None, str, list[str]]:
        """Check all messages in a thread for approval/rejection reactions.

        Scans bot messages in a thread for approval-related reactions.

        Returns:
            Tuple of (action, reactor_user_id, reaction_names) or (None, "", [])
            where action is "approved" or "rejected"
        """
        try:
            result = self.client.conversations_replies(
                channel=channel_id,
                ts=thread_ts,
                limit=100,
            )
            messages = result.get("messages", [])

            for msg in messages:
                reactions = msg.get("reactions", [])
                if not reactions:
                    continue

                for reaction in reactions:
                    name = reaction.get("name", "")
                    users = reaction.get("users", [])

                    if name in APPROVE_REACTIONS and users:
                        return "approved", users[0], [name]
                    if name in REJECT_REACTIONS and users:
                        return "rejected", users[0], [name]

        except SlackApiError as e:
            logger.error(f"Failed to check thread reactions: {e}")

        return None, "", []

    def _process_approval(
        self,
        task_id: str,
        user_id: str,
        comment: str = "",
    ) -> bool:
        """Process an approval by updating the task file directly.

        This mirrors what the /approve SKILL.md does but in code.
        """
        task = self.context_manager.get_task_record(task_id)
        if not task:
            logger.error(f"Task not found: {task_id}")
            return False

        current_stage = task.workflow.current_stage.value
        stage_info = task.workflow.stages.get(current_stage)

        if not stage_info:
            logger.error(f"Stage not found: {current_stage}")
            return False

        if stage_info.status != StageStatus.PENDING and stage_info.status != StageStatus.IN_PROGRESS:
            logger.info(f"Stage {current_stage} is not pending/in_progress: {stage_info.status}")
            return False

        # Record approval
        stage_info.status = StageStatus.APPROVED
        stage_info.approved_at = datetime.now()
        stage_info.approved_by = user_id

        # Move to next stage
        next_stage = task.get_next_stage()
        if next_stage:
            task.workflow.current_stage = next_stage
            # Initialize next stage if not done
            next_stage_name = next_stage.value
            if next_stage_name in task.workflow.stages:
                task.workflow.stages[next_stage_name].status = StageStatus.PENDING

        # Add trace
        task.add_trace(
            "reaction_auto_approved",
            f"Auto-approved via Slack reaction by <@{user_id}>. {comment}",
            stage=current_stage,
            by=user_id,
        )

        # Save
        self.context_manager.update_task_record(task)

        # Also resolve any pending FeedbackRequest for this task/stage
        self._resolve_feedback_requests(task_id, current_stage, user_id, approved=True)

        logger.info(
            f"Auto-approved {task_id} stage={current_stage} by {user_id}, "
            f"next_stage={next_stage.value if next_stage else 'done'}"
        )
        return True

    def _process_rejection(
        self,
        task_id: str,
        user_id: str,
        reason: str = "Rejected via Slack reaction",
    ) -> bool:
        """Process a rejection by updating the task file directly."""
        task = self.context_manager.get_task_record(task_id)
        if not task:
            logger.error(f"Task not found: {task_id}")
            return False

        current_stage = task.workflow.current_stage.value
        stage_info = task.workflow.stages.get(current_stage)

        if not stage_info:
            logger.error(f"Stage not found: {current_stage}")
            return False

        if stage_info.status != StageStatus.PENDING and stage_info.status != StageStatus.IN_PROGRESS:
            logger.info(f"Stage {current_stage} is not pending/in_progress: {stage_info.status}")
            return False

        # Record rejection
        stage_info.status = StageStatus.REJECTED
        stage_info.rejected_at = datetime.now()
        stage_info.rejected_by = user_id
        stage_info.rejection_reason = reason

        # Add trace
        task.add_trace(
            "reaction_auto_rejected",
            f"Auto-rejected via Slack reaction by <@{user_id}>. {reason}",
            stage=current_stage,
            by=user_id,
        )

        # Save
        self.context_manager.update_task_record(task)

        # Also resolve any pending FeedbackRequest for this task/stage
        self._resolve_feedback_requests(task_id, current_stage, user_id, approved=False)

        logger.info(f"Auto-rejected {task_id} stage={current_stage} by {user_id}")
        return True

    def _resolve_feedback_requests(
        self,
        task_id: str,
        stage: str,
        user_id: str,
        approved: bool,
    ) -> None:
        """Resolve any pending FeedbackRequest linked to this task/stage.

        This bridges the reaction-based approval with the dashboard's
        FeedbackRequest system so both stay in sync.
        """
        try:
            session_manager = SessionManager(self.data_dir)
            # Search all pending feedback for matching task_id
            feedback_dir = self.data_dir / "feedback"
            if not feedback_dir.exists():
                return

            for fb_file in feedback_dir.glob("*.yaml"):
                try:
                    raw = fb_file.read_text(encoding="utf-8")
                    fb_data = yaml.safe_load(raw) or {}

                    if fb_data.get("task_id") != task_id:
                        continue
                    if fb_data.get("workflow_stage") != stage:
                        continue
                    if fb_data.get("status") != "pending":
                        continue

                    request_id = fb_data.get("request_id", "")
                    if request_id:
                        session_manager.respond_to_feedback(
                            request_id=request_id,
                            user_id=user_id,
                            approved=approved,
                            response_text=f"Auto-{'approved' if approved else 'rejected'} via Slack reaction",
                        )
                        logger.info(f"Resolved feedback {request_id} for {task_id}/{stage}")
                except Exception as e:
                    logger.debug(f"Failed to process feedback file {fb_file}: {e}")
        except Exception as e:
            logger.debug(f"FeedbackRequest resolution failed (non-fatal): {e}")

    def _send_notification(
        self,
        channel_id: str,
        thread_ts: str,
        task_id: str,
        action: str,
        stage: str,
        user_id: str,
        next_stage: str = "",
    ) -> None:
        """Send a Block Kit notification message about the auto-approval/rejection."""
        from ultrawork.slack.block_kit import BlockKitBuilder, send_block_message

        if action == "approved":
            message = BlockKitBuilder.build_approval_notification(
                task_id=task_id,
                stage=stage,
                user_id=user_id,
                next_stage=next_stage,
                is_complete=(next_stage == "done"),
            )
        else:
            message = BlockKitBuilder.build_rejection_notification(
                task_id=task_id,
                stage=stage,
                user_id=user_id,
                reason="수정이 필요합니다. 피드백을 스레드에 남겨주세요.",
            )

        result = send_block_message(self.client, channel_id, message, thread_ts=thread_ts)
        if result is None:
            logger.error(f"Failed to send Block Kit notification for {task_id}")

    def _trigger_next_stage(
        self,
        task_id: str,
        next_stage: str,
        channel_id: str,
        thread_ts: str,
    ) -> None:
        """Trigger the next workflow stage after approval.

        For certain stages, automatically starts the next skill.
        """
        stage_skill_map = {
            "tech_spec": "write-spec",
            "final_report": "report",
        }

        skill_name = stage_skill_map.get(next_stage)
        if not skill_name:
            return

        logger.info(f"Auto-triggering /{skill_name} for {task_id}")

        try:
            from ultrawork.config import get_config
            config = get_config()
            lang_prompt = ""
            if config.language.default != "en":
                lang_prompt = f"Respond in {config.language.default}. "

            env = os.environ.copy()
            env["IS_SANDBOX"] = "1"

            prompt = (
                f"{lang_prompt}"
                f"Execute the /{skill_name} skill for {task_id}. "
                f"The task was just auto-approved via Slack reaction. "
                f"Channel: {channel_id}, Thread: {thread_ts}"
            )

            subprocess.Popen(
                [
                    "claude",
                    "--dangerously-skip-permissions",
                    "-p",
                    prompt,
                ],
                cwd=str(self.data_dir.parent),
                env=env,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except Exception as e:
            logger.error(f"Failed to trigger next stage: {e}")

    async def check_and_process(self) -> list[ApprovalResult]:
        """Check all pending approvals for reactions and process them.

        This is the main entry point called by the SDK poller daemon.

        Returns:
            List of ApprovalResult for each processed item.
        """
        results = []
        pending = self.tracker.get_pending()

        if not pending:
            # Fall back to scanning task files for pending approvals
            pending = self._discover_pending_from_tasks()

        for entry in pending:
            task_id = entry["task_id"]
            stage = entry["stage"]
            channel_id = entry["channel_id"]
            message_ts = entry.get("message_ts", "")
            thread_ts = entry.get("thread_ts", "")

            # First try specific message reactions
            if message_ts:
                reactions = self._get_message_reactions(channel_id, message_ts)
                action, user_id = self._evaluate_reactions(reactions)
            else:
                action, user_id = None, ""

            # Fall back to thread-level scan
            if action is None and thread_ts:
                action, user_id, _ = self._check_thread_for_approval_reactions(
                    channel_id, thread_ts
                )

            if action is None:
                results.append(ApprovalResult(task_id, stage, "pending"))
                continue

            # Process the action
            if action == "approved":
                success = self._process_approval(task_id, user_id)
            else:
                success = self._process_rejection(task_id, user_id)

            if success:
                self.tracker.mark_processed(task_id, stage, action, user_id)

                # Determine next stage for notification
                task = self.context_manager.get_task_record(task_id)
                next_stage = task.workflow.current_stage.value if task else "unknown"

                self._send_notification(
                    channel_id=channel_id,
                    thread_ts=thread_ts or message_ts,
                    task_id=task_id,
                    action=action,
                    stage=stage,
                    user_id=user_id,
                    next_stage=next_stage,
                )

                # Trigger next stage skill if appropriate
                if action == "approved" and next_stage not in ("done", "code_work"):
                    self._trigger_next_stage(
                        task_id, next_stage, channel_id, thread_ts or message_ts
                    )

                results.append(ApprovalResult(task_id, stage, action, user_id))
            else:
                results.append(
                    ApprovalResult(task_id, stage, "error", message="Processing failed")
                )

        return results

    def _evaluate_reactions(self, reactions: list[dict]) -> tuple[str | None, str]:
        """Evaluate a list of reactions to determine approval/rejection.

        Returns:
            Tuple of (action, user_id) where action is "approved", "rejected", or None
        """
        for reaction in reactions:
            name = reaction.get("name", "")
            users = reaction.get("users", [])
            if not users:
                continue

            if name in APPROVE_REACTIONS:
                return "approved", users[0]
            if name in REJECT_REACTIONS:
                return "rejected", users[0]

        return None, ""

    def _discover_pending_from_tasks(self) -> list[dict]:
        """Discover pending approvals by scanning task files.

        Used as fallback when no explicit tracker entries exist.
        Reads YAML frontmatter directly to get channel_id/thread_ts
        which may not be in the Pydantic TaskSource model.
        """
        pending = []

        for task_file in self.context_manager.tasks_dir.glob("*.md"):
            try:
                raw = task_file.read_text(encoding="utf-8")
                # Parse YAML frontmatter between --- delimiters
                if not raw.startswith("---"):
                    continue
                end_idx = raw.index("---", 3)
                yaml_text = raw[3:end_idx]
                metadata: dict = yaml.safe_load(yaml_text) or {}

                workflow = metadata.get("workflow", {})
                current_stage = workflow.get("current_stage", "")
                if current_stage == "done":
                    continue

                stages = workflow.get("stages", {})
                stage_info = stages.get(current_stage, {})
                status = stage_info.get("status", "")

                if status not in ("pending", "in_progress"):
                    continue

                source = metadata.get("source", {})
                channel_id: str = source.get("channel_id", "")
                thread_ts: str = source.get("thread_ts", "")

                # Fallback: extract from thread_id (format: "CHANNEL-THREAD_TS")
                if not channel_id:
                    thread_id: str = source.get("thread_id", "")
                    if thread_id and "-" in thread_id:
                        channel_id, thread_ts = thread_id.split("-", 1)

                if not channel_id:
                    continue

                pending.append({
                    "task_id": metadata.get("task_id", ""),
                    "stage": current_stage,
                    "channel_id": channel_id,
                    "message_ts": source.get("message_ts", ""),
                    "thread_ts": thread_ts,
                })
            except Exception as e:
                logger.debug(f"Failed to parse task file {task_file}: {e}")

        return pending
