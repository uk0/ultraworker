"""Polling and response models for real-time Slack tracking."""

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


class ResponseType(str, Enum):
    """Type of response to generate."""

    ACKNOWLEDGE = "acknowledge"  # Simple acknowledgment - auto-send
    SIMPLE_QUERY = "simple_query"  # Simple question answer - auto-send
    ACTION = "action"  # Task creation needed - manual review
    COMPLEX = "complex"  # Complex analysis needed - manual review
    DEFER = "defer"  # Cannot determine - manual review


class ResponseIntent(str, Enum):
    """Detected intent from the message."""

    QUESTION = "question"
    ISSUE_REPORT = "issue_report"
    REQUEST = "request"
    STATUS_QUERY = "status_query"
    GREETING = "greeting"
    GENERAL = "general"


class PollingState(BaseModel):
    """Persistent state for Slack polling."""

    last_checked_ts: str = ""  # Latest message timestamp checked
    last_poll_at: datetime | None = None
    processed_messages: set[str] = Field(default_factory=set)
    poll_count: int = 0
    error_count: int = 0
    consecutive_errors: int = 0
    last_error: str | None = None
    daemon_pid: int | None = None  # PID of running daemon
    daemon_started_at: datetime | None = None

    class Config:
        """Pydantic configuration."""

        arbitrary_types_allowed = True


class PendingResponse(BaseModel):
    """A response waiting for approval."""

    message_id: str  # Slack message timestamp
    channel_id: str
    thread_ts: str
    sender_id: str = ""
    sender_name: str = ""
    original_message: str
    proposed_response: str
    response_type: ResponseType
    intent: ResponseIntent = ResponseIntent.GENERAL
    confidence: float = 0.0
    created_at: datetime = Field(default_factory=datetime.now)
    context_summary: str = ""
    thread_message_count: int = 0
    exploration_id: str | None = None  # Linked exploration if any

    def get_file_path(self, base_dir: str = "data/pending") -> str:
        """Get the file path for this pending response."""
        safe_ts = self.message_id.replace(".", "-")
        return f"{base_dir}/{safe_ts}.yaml"


class ProcessedMention(BaseModel):
    """A processed mention record."""

    message_ts: str
    channel_id: str
    thread_ts: str
    processed_at: datetime = Field(default_factory=datetime.now)
    response_sent: bool = False
    response_type: ResponseType | None = None
    pending_id: str | None = None  # If pending approval


class PollingStats(BaseModel):
    """Statistics for polling activity."""

    total_polls: int = 0
    total_mentions_found: int = 0
    total_responses_sent: int = 0
    total_responses_pending: int = 0
    auto_responses: int = 0
    manual_responses: int = 0
    errors: int = 0
    last_poll_duration_ms: int = 0
    average_poll_duration_ms: float = 0.0
