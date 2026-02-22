"""Slack interactivity handler for Block Kit button actions.

Processes incoming interaction payloads from Slack when users click
buttons in Block Kit messages (approve, reject, etc.).

Slack sends interaction payloads as HTTP POST to a configured endpoint.
This module parses those payloads and dispatches to appropriate handlers.

Usage:
    from ultrawork.slack.interactions import InteractionHandler

    handler = InteractionHandler(data_dir=Path("data"))
    response = handler.handle_payload(payload_dict)
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Any

from ultrawork.slack.block_kit import (
    ACTION_APPROVE,
    ACTION_REJECT,
    ACTION_SKIP,
    BlockKitBuilder,
    _context,
    send_block_message,
)

logger = logging.getLogger("slack_interactions")


class InteractionHandler:
    """Handles Slack interactive component payloads.

    Processes button clicks from Block Kit messages and triggers
    the appropriate workflow actions (approve, reject, etc.).
    """

    def __init__(self, data_dir: Path, slack_token: str = "", slack_cookie: str = ""):
        self.data_dir = Path(data_dir)
        self.slack_token = slack_token or os.environ.get("SLACK_TOKEN", "")
        self.slack_cookie = slack_cookie or os.environ.get("SLACK_COOKIE", "")

    def _get_client(self):
        """Create a Slack WebClient."""
        if not self.slack_token:
            return None
        from slack_sdk import WebClient

        headers = {}
        if self.slack_token.startswith("xoxc-") and self.slack_cookie:
            headers["Cookie"] = f"d={self.slack_cookie}"
        return WebClient(token=self.slack_token, headers=headers)

    def handle_payload(self, payload: dict) -> dict[str, Any]:
        """Process a Slack interaction payload.

        Args:
            payload: Parsed JSON payload from Slack.

        Returns:
            Response dict. For message replacement, returns new message blocks.
            For acknowledgment, returns empty dict.
        """
        payload_type = payload.get("type", "")

        if payload_type == "block_actions":
            return self._handle_block_actions(payload)

        logger.warning(f"Unhandled payload type: {payload_type}")
        return {}

    def _handle_block_actions(self, payload: dict) -> dict[str, Any]:
        """Handle block_actions payload (button clicks)."""
        actions = payload.get("actions", [])
        if not actions:
            return {}

        action = actions[0]
        action_id = action.get("action_id", "")
        value_str = action.get("value", "{}")
        user = payload.get("user", {})
        user_id = user.get("id", "")
        channel = payload.get("channel", {})
        channel_id = channel.get("id", "")
        message = payload.get("message", {})
        message_ts = message.get("ts", "")
        thread_ts = message.get("thread_ts", "")

        # Parse value
        try:
            value = json.loads(value_str) if value_str else {}
        except (json.JSONDecodeError, TypeError):
            value = {}

        task_id = value.get("task_id", "")
        stage = value.get("stage", "")

        # Route to handler based on action prefix
        if action_id.startswith(ACTION_APPROVE):
            return self._handle_approve(
                task_id=task_id,
                stage=stage,
                user_id=user_id,
                channel_id=channel_id,
                thread_ts=thread_ts or message_ts,
                original_message=message,
            )
        elif action_id.startswith(ACTION_REJECT):
            return self._handle_reject(
                task_id=task_id,
                stage=stage,
                user_id=user_id,
                channel_id=channel_id,
                thread_ts=thread_ts or message_ts,
                original_message=message,
            )
        elif action_id.startswith(ACTION_SKIP):
            return self._handle_skip(action_id, value, user_id)

        logger.info(f"Unhandled action: {action_id}")
        return {}

    def _handle_approve(
        self,
        task_id: str,
        stage: str,
        user_id: str,
        channel_id: str,
        thread_ts: str,
        original_message: dict,
    ) -> dict[str, Any]:
        """Process an approval button click."""
        if not task_id:
            return {"text": "Error: No task_id in action value"}

        logger.info(f"Button approval: {task_id} stage={stage} by {user_id}")

        # Use ReactionApprovalHandler to process (reuses existing logic)
        try:
            from ultrawork.slack.reaction_approval import ReactionApprovalHandler

            handler = ReactionApprovalHandler(
                slack_token=self.slack_token,
                data_dir=self.data_dir,
                slack_cookie=self.slack_cookie if self.slack_cookie else None,
            )
            success = handler._process_approval(task_id, user_id, comment="Approved via button")

            if success:
                # Determine next stage
                from ultrawork.context.manager import ContextManager
                ctx = ContextManager(self.data_dir)
                task = ctx.get_task_record(task_id)
                next_stage = task.workflow.current_stage.value if task else "unknown"

                # Send notification
                notification = BlockKitBuilder.build_approval_notification(
                    task_id=task_id,
                    stage=stage,
                    user_id=user_id,
                    next_stage=next_stage,
                    is_complete=(next_stage == "done"),
                )

                client = self._get_client()
                if client:
                    send_block_message(client, channel_id, notification, thread_ts=thread_ts)

                    # Trigger next stage
                    if next_stage not in ("done", "code_work"):
                        handler._trigger_next_stage(task_id, next_stage, channel_id, thread_ts)

                # Return updated message (replace buttons with confirmation)
                return self._build_action_confirmed_message(
                    original_message, "approved", user_id, stage
                )

        except Exception as e:
            logger.error(f"Approval processing failed: {e}")
            return {"text": f"Error processing approval: {e}"}

        return {}

    def _handle_reject(
        self,
        task_id: str,
        stage: str,
        user_id: str,
        channel_id: str,
        thread_ts: str,
        original_message: dict,
    ) -> dict[str, Any]:
        """Process a rejection button click."""
        if not task_id:
            return {"text": "Error: No task_id in action value"}

        logger.info(f"Button rejection: {task_id} stage={stage} by {user_id}")

        try:
            from ultrawork.slack.reaction_approval import ReactionApprovalHandler

            handler = ReactionApprovalHandler(
                slack_token=self.slack_token,
                data_dir=self.data_dir,
                slack_cookie=self.slack_cookie if self.slack_cookie else None,
            )
            success = handler._process_rejection(
                task_id, user_id, reason="Rejected via button"
            )

            if success:
                notification = BlockKitBuilder.build_rejection_notification(
                    task_id=task_id,
                    stage=stage,
                    user_id=user_id,
                    reason="Rejected via button - please provide feedback in the thread.",
                )

                client = self._get_client()
                if client:
                    send_block_message(client, channel_id, notification, thread_ts=thread_ts)

                return self._build_action_confirmed_message(
                    original_message, "rejected", user_id, stage
                )

        except Exception as e:
            logger.error(f"Rejection processing failed: {e}")
            return {"text": f"Error processing rejection: {e}"}

        return {}

    def _handle_skip(
        self, action_id: str, _value: dict, user_id: str
    ) -> dict[str, Any]:
        """Handle skip actions."""
        logger.info(f"Skip action: {action_id} by {user_id}")
        return {
            "response_type": "ephemeral",
            "text": f":fast_forward: Skipped by <@{user_id}>",
        }

    @staticmethod
    def _build_action_confirmed_message(
        original_message: dict,
        action: str,
        user_id: str,
        _stage: str = "",
    ) -> dict[str, Any]:
        """Replace action buttons in original message with a confirmation.

        This returns a message_update that replaces the actions block
        with a confirmation context block.
        """
        blocks = original_message.get("blocks", [])
        updated_blocks = []

        for block in blocks:
            if block.get("type") == "actions":
                # Replace actions block with confirmation
                emoji = ":white_check_mark:" if action == "approved" else ":x:"
                action_label = "Approved" if action == "approved" else "Rejected"
                updated_blocks.append(
                    _context(
                        f"{emoji} *{action_label}* by <@{user_id}> at {datetime.now().strftime('%Y-%m-%d %H:%M')}"
                    )
                )
            else:
                updated_blocks.append(block)

        return {
            "replace_original": True,
            "blocks": updated_blocks,
            "text": original_message.get("text", ""),
        }


def parse_interaction_payload(raw_body: str) -> dict | None:
    """Parse a Slack interaction payload from raw form-encoded body.

    Slack sends interaction payloads as:
        payload=<url-encoded JSON>

    Args:
        raw_body: Raw HTTP request body string

    Returns:
        Parsed payload dict or None
    """
    from urllib.parse import parse_qs

    try:
        params = parse_qs(raw_body)
        payload_str = params.get("payload", [""])[0]
        if payload_str:
            return json.loads(payload_str)
    except (json.JSONDecodeError, KeyError, IndexError) as e:
        logger.error(f"Failed to parse interaction payload: {e}")

    return None
