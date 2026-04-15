"""Interaction event logging for real-time dashboard display.

This module logs user inputs, bot responses, and processing events
to enable real-time interaction display in the dashboard.
"""

import json
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any


class InteractionType(str, Enum):
    """Types of interaction events."""

    USER_INPUT = "user_input"  # User's Slack mention
    BOT_RESPONSE = "bot_response"  # Bot's Slack response
    PROCESSING_STARTED = "processing_started"  # Claude processing started
    PROCESSING_HEARTBEAT = "processing_heartbeat"  # Claude processing still running
    PROCESSING_COMPLETED = "processing_completed"  # Claude processing completed
    PROCESSING_FAILED = "processing_failed"  # Claude processing failed
    SESSION_RESUMED = "session_resumed"  # Session was resumed (not new)
    SESSION_CREATED = "session_created"  # New session created


class InteractionLogger:
    """Logger for user-bot interactions.

    Logs interactions to a JSONL file for real-time streaming
    to the dashboard via SSE.
    """

    def __init__(self, data_dir: Path | str) -> None:
        """Initialize InteractionLogger.

        Args:
            data_dir: Base data directory
        """
        self.data_dir = Path(data_dir)
        self.log_file = self.data_dir / "logs" / "interactions.jsonl"
        self.log_file.parent.mkdir(parents=True, exist_ok=True)

    def log(
        self,
        interaction_type: InteractionType,
        session_id: str,
        channel_id: str,
        thread_ts: str,
        content: str,
        user_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Log an interaction event.

        Args:
            interaction_type: Type of interaction
            session_id: Agent session ID
            channel_id: Slack channel ID
            thread_ts: Slack thread timestamp
            content: Event content/message
            user_id: User ID (for user inputs)
            metadata: Additional metadata

        Returns:
            The logged entry dictionary
        """
        entry = {
            "timestamp": datetime.now().isoformat(),
            "type": interaction_type.value,
            "session_id": session_id,
            "channel_id": channel_id,
            "thread_ts": thread_ts,
            "content": content,
            "user_id": user_id,
            "metadata": metadata or {},
        }

        with open(self.log_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

        return entry

    def log_user_input(
        self,
        session_id: str,
        channel_id: str,
        thread_ts: str,
        content: str,
        user_id: str,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Log a user input event.

        Args:
            session_id: Agent session ID
            channel_id: Slack channel ID
            thread_ts: Slack thread timestamp
            content: User's message content
            user_id: User's Slack ID
            metadata: Additional metadata

        Returns:
            The logged entry
        """
        return self.log(
            interaction_type=InteractionType.USER_INPUT,
            session_id=session_id,
            channel_id=channel_id,
            thread_ts=thread_ts,
            content=content,
            user_id=user_id,
            metadata=metadata,
        )

    def log_bot_response(
        self,
        session_id: str,
        channel_id: str,
        thread_ts: str,
        content: str,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Log a bot response event.

        Args:
            session_id: Agent session ID
            channel_id: Slack channel ID
            thread_ts: Slack thread timestamp
            content: Bot's response content
            metadata: Additional metadata

        Returns:
            The logged entry
        """
        return self.log(
            interaction_type=InteractionType.BOT_RESPONSE,
            session_id=session_id,
            channel_id=channel_id,
            thread_ts=thread_ts,
            content=content,
            metadata=metadata,
        )

    def log_processing_started(
        self,
        session_id: str,
        channel_id: str,
        thread_ts: str,
        is_resuming: bool = False,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Log processing started event.

        Args:
            session_id: Agent session ID
            channel_id: Slack channel ID
            thread_ts: Slack thread timestamp
            is_resuming: Whether resuming existing session
            metadata: Additional metadata

        Returns:
            The logged entry
        """
        content = (
            f"Resuming session {session_id}"
            if is_resuming
            else f"Starting new session {session_id}"
        )
        meta = metadata or {}
        meta["is_resuming"] = is_resuming

        return self.log(
            interaction_type=InteractionType.PROCESSING_STARTED,
            session_id=session_id,
            channel_id=channel_id,
            thread_ts=thread_ts,
            content=content,
            metadata=meta,
        )

    def log_processing_completed(
        self,
        session_id: str,
        channel_id: str,
        thread_ts: str,
        success: bool,
        exit_code: int = 0,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Log processing completed event.

        Args:
            session_id: Agent session ID
            channel_id: Slack channel ID
            thread_ts: Slack thread timestamp
            success: Whether processing succeeded
            exit_code: Process exit code
            metadata: Additional metadata

        Returns:
            The logged entry
        """
        interaction_type = (
            InteractionType.PROCESSING_COMPLETED if success else InteractionType.PROCESSING_FAILED
        )
        content = (
            "Processing completed successfully"
            if success
            else f"Processing failed with exit code {exit_code}"
        )
        meta = metadata or {}
        meta["success"] = success
        meta["exit_code"] = exit_code

        return self.log(
            interaction_type=interaction_type,
            session_id=session_id,
            channel_id=channel_id,
            thread_ts=thread_ts,
            content=content,
            metadata=meta,
        )

    def log_processing_heartbeat(
        self,
        session_id: str,
        channel_id: str,
        thread_ts: str,
        elapsed_seconds: int,
        pid: int | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Log processing heartbeat while a long-running command is active."""
        content = (
            f"Still running (elapsed={elapsed_seconds}s, pid={pid})"
            if pid
            else f"Still running (elapsed={elapsed_seconds}s)"
        )
        meta = metadata or {}
        meta["elapsed_seconds"] = elapsed_seconds
        if pid:
            meta["pid"] = pid

        return self.log(
            interaction_type=InteractionType.PROCESSING_HEARTBEAT,
            session_id=session_id,
            channel_id=channel_id,
            thread_ts=thread_ts,
            content=content,
            metadata=meta,
        )

    def get_recent(
        self,
        limit: int = 100,
        session_id: str | None = None,
    ) -> list[dict[str, Any]]:
        """Get recent interaction events.

        Args:
            limit: Maximum number of events to return
            session_id: Filter by session ID (optional)

        Returns:
            List of recent interaction entries
        """
        if not self.log_file.exists():
            return []

        entries = []
        with open(self.log_file, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        entry = json.loads(line)
                        if session_id is None or entry.get("session_id") == session_id:
                            entries.append(entry)
                    except json.JSONDecodeError:
                        continue

        # Return most recent entries
        return entries[-limit:]

    def get_by_session(self, session_id: str) -> list[dict[str, Any]]:
        """Get all interactions for a session.

        Args:
            session_id: Session ID to filter by

        Returns:
            List of interactions for the session
        """
        return self.get_recent(limit=1000, session_id=session_id)

    def clear(self) -> None:
        """Clear all interaction logs."""
        if self.log_file.exists():
            self.log_file.unlink()
