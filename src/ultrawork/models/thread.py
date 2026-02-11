"""Thread data model for Slack thread records."""

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


class ParticipantRole(str, Enum):
    """Role of a participant in a thread."""

    REQUESTER = "requester"
    AGENT = "agent"
    REVIEWER = "reviewer"
    OBSERVER = "observer"


class Participant(BaseModel):
    """A participant in a Slack thread."""

    user_id: str
    name: str
    role: ParticipantRole


class LinkedTask(BaseModel):
    """Reference to a task linked from a thread."""

    task_id: str
    status: str


class ThreadRecord(BaseModel):
    """A Slack thread record with context information."""

    thread_id: str = Field(description="Composite ID: {channel_id}-{thread_ts}")
    channel_id: str
    channel_name: str
    thread_ts: str
    created_at: datetime
    updated_at: datetime

    participants: list[Participant] = Field(default_factory=list)
    linked_tasks: list[LinkedTask] = Field(default_factory=list)

    last_sync_ts: str | None = None
    message_count: int = 0

    summary: str = ""
    messages_markdown: str = ""

    @classmethod
    def create_id(cls, channel_id: str, thread_ts: str) -> str:
        """Create a thread ID from channel and timestamp."""
        return f"{channel_id}-{thread_ts}"

    def get_file_path(self, base_dir: str = "data/threads") -> str:
        """Get the file path for this thread record."""
        return f"{base_dir}/{self.channel_id}/{self.thread_ts}.md"
