"""Slack monitoring for mentions and threads."""

from datetime import datetime
from pathlib import Path
from typing import Any

from ultrawork.context import ContextManager
from ultrawork.models import (
    LinkedTask,
    Participant,
    ParticipantRole,
    ThreadRecord,
)
from ultrawork.slack.registry import SlackRegistry


class SlackMonitor:
    """Monitors Slack for mentions and thread updates."""

    def __init__(self, data_dir: str | Path = "data", bot_user_id: str = ""):
        self.data_dir = Path(data_dir)
        self.bot_user_id = bot_user_id
        self.registry = SlackRegistry(data_dir)
        self.context = ContextManager(data_dir)

        # Track last checked timestamps per channel
        self._last_checked: dict[str, str] = {}

    def process_mentions(self, messages: list[dict[str, Any]]) -> list[ThreadRecord]:
        """Process messages that mention the bot.

        Args:
            messages: List of Slack messages from search results

        Returns:
            List of created/updated thread records
        """
        threads = []

        for msg in messages:
            channel_id = msg.get("channel", {}).get("id", "")
            thread_ts = msg.get("ts", "")

            if not channel_id or not thread_ts:
                continue

            # Check if this is a thread reply or main message
            parent_ts = msg.get("thread_ts", thread_ts)

            # Get or create thread record
            thread = self.context.get_thread_record(channel_id, parent_ts)
            if not thread:
                thread = self._create_thread_from_message(msg, channel_id, parent_ts)
            else:
                # Update existing thread
                thread = self._update_thread_from_message(thread, msg)

            self.context.update_thread_record(thread)
            threads.append(thread)

        return threads

    def process_thread_messages(
        self,
        channel_id: str,
        thread_ts: str,
        messages: list[dict[str, Any]],
    ) -> ThreadRecord:
        """Process all messages from a thread.

        Args:
            channel_id: Channel ID
            thread_ts: Thread timestamp
            messages: List of messages in the thread

        Returns:
            Updated thread record
        """
        # Get or create thread record
        thread = self.context.get_thread_record(channel_id, thread_ts)
        if not thread:
            channel_name = self.registry.get_channel_display_name(channel_id)
            thread = ThreadRecord(
                thread_id=ThreadRecord.create_id(channel_id, thread_ts),
                channel_id=channel_id,
                channel_name=channel_name,
                thread_ts=thread_ts,
                created_at=datetime.now(),
                updated_at=datetime.now(),
            )

        # Process all messages
        participants_map: dict[str, Participant] = {p.user_id: p for p in thread.participants}

        message_rows = []
        latest_ts = thread_ts

        for msg in messages:
            user_id = msg.get("user", "")
            ts = msg.get("ts", "")
            text = msg.get("text", "")[:100]  # Truncate for summary

            if ts > latest_ts:
                latest_ts = ts

            # Add participant if new
            if user_id and user_id not in participants_map:
                user_name = self.registry.get_user_display_name(user_id)
                role = (
                    ParticipantRole.AGENT
                    if user_id == self.bot_user_id
                    else ParticipantRole.REQUESTER
                )
                participants_map[user_id] = Participant(
                    user_id=user_id,
                    name=user_name,
                    role=role,
                )

            # Build message history row
            msg_time = datetime.fromtimestamp(float(ts))
            user_name = self.registry.get_user_display_name(user_id)
            message_rows.append(f"| {msg_time.strftime('%H:%M')} | {user_name} | {text} |")

        # Update thread
        thread.participants = list(participants_map.values())
        thread.message_count = len(messages)
        thread.last_sync_ts = latest_ts
        thread.updated_at = datetime.now()

        # Build markdown table
        thread.messages_markdown = (
            "| Time | Sender | Content |\n|------|--------|---------|" + "\n".join(message_rows)
        )

        self.context.update_thread_record(thread)
        return thread

    def _create_thread_from_message(
        self,
        msg: dict[str, Any],
        channel_id: str,
        thread_ts: str,
    ) -> ThreadRecord:
        """Create a new thread record from a message."""
        channel_name = self.registry.get_channel_display_name(channel_id)
        user_id = msg.get("user", "")
        user_name = self.registry.get_user_display_name(user_id)

        participants = []
        if user_id:
            participants.append(
                Participant(
                    user_id=user_id,
                    name=user_name,
                    role=ParticipantRole.REQUESTER,
                )
            )

        return ThreadRecord(
            thread_id=ThreadRecord.create_id(channel_id, thread_ts),
            channel_id=channel_id,
            channel_name=channel_name,
            thread_ts=thread_ts,
            created_at=datetime.now(),
            updated_at=datetime.now(),
            participants=participants,
            message_count=1,
            last_sync_ts=msg.get("ts", thread_ts),
        )

    def _update_thread_from_message(
        self,
        thread: ThreadRecord,
        msg: dict[str, Any],
    ) -> ThreadRecord:
        """Update an existing thread record with new message info."""
        user_id = msg.get("user", "")
        ts = msg.get("ts", "")

        # Add new participant if not exists
        existing_ids = {p.user_id for p in thread.participants}
        if user_id and user_id not in existing_ids:
            user_name = self.registry.get_user_display_name(user_id)
            role = (
                ParticipantRole.AGENT if user_id == self.bot_user_id else ParticipantRole.OBSERVER
            )
            thread.participants.append(Participant(user_id=user_id, name=user_name, role=role))

        # Update timestamps
        if ts and (not thread.last_sync_ts or ts > thread.last_sync_ts):
            thread.last_sync_ts = ts

        thread.updated_at = datetime.now()
        return thread

    def get_threads_needing_sync(self, max_age_seconds: int = 300) -> list[ThreadRecord]:
        """Get threads that need to be synced.

        Args:
            max_age_seconds: Threads older than this need sync

        Returns:
            List of threads needing sync
        """
        threads = self.context.list_threads()
        now = datetime.now()

        needing_sync = []
        for thread in threads:
            # Check if any linked task is active
            has_active_task = any(
                lt.status not in ("done", "completed") for lt in thread.linked_tasks
            )

            if not has_active_task:
                continue

            # Check age
            age = (now - thread.updated_at).total_seconds()
            if age > max_age_seconds:
                needing_sync.append(thread)

        return needing_sync

    def link_thread_to_task(
        self, thread: ThreadRecord, task_id: str, status: str = "pending"
    ) -> None:
        """Link a thread to a task."""
        existing_ids = {lt.task_id for lt in thread.linked_tasks}
        if task_id not in existing_ids:
            thread.linked_tasks.append(LinkedTask(task_id=task_id, status=status))
            self.context.update_thread_record(thread)

    def extract_mention_trigger(self, message: dict[str, Any]) -> dict[str, Any] | None:
        """Extract trigger info from a mention message.

        Returns dict with:
        - channel_id
        - thread_ts
        - message_ts
        - user_id
        - text
        """
        text = message.get("text", "")

        # Check if bot is mentioned
        if f"<@{self.bot_user_id}>" not in text and self.bot_user_id:
            return None

        channel_info = message.get("channel", {})
        channel_id = channel_info.get("id", "") if isinstance(channel_info, dict) else channel_info

        return {
            "channel_id": channel_id,
            "thread_ts": message.get("thread_ts", message.get("ts", "")),
            "message_ts": message.get("ts", ""),
            "user_id": message.get("user", ""),
            "text": text,
        }
