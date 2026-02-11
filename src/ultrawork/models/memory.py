"""Context memory and feedback models.

This module provides models for managing agent context memory (short-term
and long-term) and human-in-the-loop feedback requests.
"""

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class MemoryType(str, Enum):
    """Type of memory entry."""

    SHORT_TERM = "short_term"  # Session-scoped, cleared after session
    LONG_TERM = "long_term"  # Persisted across sessions
    EPISODIC = "episodic"  # Specific events/interactions
    SEMANTIC = "semantic"  # Facts and knowledge


class MemoryScope(str, Enum):
    """Scope of memory entry."""

    SESSION = "session"  # Current agent session only
    TASK = "task"  # Linked to a specific task
    THREAD = "thread"  # Slack thread context
    CHANNEL = "channel"  # Channel-level context
    GLOBAL = "global"  # Cross-session knowledge


class MemoryEntry(BaseModel):
    """A single memory entry.

    Memory entries represent individual pieces of context that the agent
    has learned or needs to remember during execution.
    """

    entry_id: str
    memory_type: MemoryType
    scope: MemoryScope

    # Content
    key: str  # Lookup key (e.g., "user_preference", "project_name")
    value: Any  # The actual memory content
    summary: str = ""  # Human-readable summary

    # Associations
    session_id: str | None = None
    task_id: str | None = None
    thread_ts: str | None = None
    channel_id: str | None = None

    # Timestamps
    created_at: datetime = Field(default_factory=datetime.now)
    accessed_at: datetime = Field(default_factory=datetime.now)
    expires_at: datetime | None = None

    # Relevance
    relevance_score: float = 1.0  # 0.0 to 1.0
    access_count: int = 0

    # Source
    source: str = ""  # Where this memory came from
    source_skill: str | None = None  # Skill that created this memory

    def access(self) -> None:
        """Record an access to this memory entry."""
        self.accessed_at = datetime.now()
        self.access_count += 1

    def update_relevance(self, score: float) -> None:
        """Update the relevance score."""
        self.relevance_score = max(0.0, min(1.0, score))

    def is_expired(self) -> bool:
        """Check if this memory entry has expired."""
        if self.expires_at is None:
            return False
        return datetime.now() > self.expires_at


class ContextMemory(BaseModel):
    """Context memory manager for an agent session.

    ContextMemory manages both short-term and long-term memory for an agent
    session. It provides methods for storing, retrieving, and managing
    context entries.
    """

    memory_id: str
    session_id: str
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)

    # Memory storage
    entries: dict[str, MemoryEntry] = Field(default_factory=dict)

    # Indexes for fast lookup
    by_type: dict[str, list[str]] = Field(default_factory=dict)  # type -> entry_ids
    by_scope: dict[str, list[str]] = Field(default_factory=dict)  # scope -> entry_ids
    by_key: dict[str, str] = Field(default_factory=dict)  # key -> entry_id

    # Configuration
    max_short_term_entries: int = 100
    max_long_term_entries: int = 1000

    def add_entry(self, entry: MemoryEntry) -> None:
        """Add a memory entry.

        Args:
            entry: The memory entry to add
        """
        self.entries[entry.entry_id] = entry

        # Update indexes
        type_key = entry.memory_type.value
        if type_key not in self.by_type:
            self.by_type[type_key] = []
        if entry.entry_id not in self.by_type[type_key]:
            self.by_type[type_key].append(entry.entry_id)

        scope_key = entry.scope.value
        if scope_key not in self.by_scope:
            self.by_scope[scope_key] = []
        if entry.entry_id not in self.by_scope[scope_key]:
            self.by_scope[scope_key].append(entry.entry_id)

        self.by_key[entry.key] = entry.entry_id
        self.updated_at = datetime.now()

    def get_entry(self, entry_id: str) -> MemoryEntry | None:
        """Get a memory entry by ID."""
        entry = self.entries.get(entry_id)
        if entry:
            entry.access()
        return entry

    def get_by_key(self, key: str) -> MemoryEntry | None:
        """Get a memory entry by key."""
        entry_id = self.by_key.get(key)
        if entry_id:
            return self.get_entry(entry_id)
        return None

    def get_by_type(self, memory_type: MemoryType) -> list[MemoryEntry]:
        """Get all entries of a specific type."""
        entry_ids = self.by_type.get(memory_type.value, [])
        return [self.entries[eid] for eid in entry_ids if eid in self.entries]

    def get_by_scope(self, scope: MemoryScope) -> list[MemoryEntry]:
        """Get all entries of a specific scope."""
        entry_ids = self.by_scope.get(scope.value, [])
        return [self.entries[eid] for eid in entry_ids if eid in self.entries]

    def remove_entry(self, entry_id: str) -> bool:
        """Remove a memory entry.

        Args:
            entry_id: ID of the entry to remove

        Returns:
            True if entry was removed
        """
        if entry_id not in self.entries:
            return False

        entry = self.entries[entry_id]

        # Remove from indexes
        type_key = entry.memory_type.value
        if type_key in self.by_type and entry_id in self.by_type[type_key]:
            self.by_type[type_key].remove(entry_id)

        scope_key = entry.scope.value
        if scope_key in self.by_scope and entry_id in self.by_scope[scope_key]:
            self.by_scope[scope_key].remove(entry_id)

        if entry.key in self.by_key and self.by_key[entry.key] == entry_id:
            del self.by_key[entry.key]

        del self.entries[entry_id]
        self.updated_at = datetime.now()
        return True

    def cleanup_expired(self) -> int:
        """Remove all expired entries.

        Returns:
            Number of entries removed
        """
        expired_ids = [eid for eid, entry in self.entries.items() if entry.is_expired()]
        for entry_id in expired_ids:
            self.remove_entry(entry_id)
        return len(expired_ids)

    def cleanup_short_term(self) -> int:
        """Remove oldest short-term entries if over limit.

        Returns:
            Number of entries removed
        """
        short_term_ids = self.by_type.get(MemoryType.SHORT_TERM.value, [])
        if len(short_term_ids) <= self.max_short_term_entries:
            return 0

        # Sort by access time and remove oldest
        entries_with_time = [
            (eid, self.entries[eid].accessed_at) for eid in short_term_ids if eid in self.entries
        ]
        entries_with_time.sort(key=lambda x: x[1])

        to_remove = len(short_term_ids) - self.max_short_term_entries
        removed = 0
        for entry_id, _ in entries_with_time[:to_remove]:
            if self.remove_entry(entry_id):
                removed += 1

        return removed

    def get_relevant_context(
        self,
        keywords: list[str] | None = None,
        scope: MemoryScope | None = None,
        limit: int = 10,
    ) -> list[MemoryEntry]:
        """Get relevant context entries.

        Args:
            keywords: Keywords to match against
            scope: Filter by scope
            limit: Maximum entries to return

        Returns:
            List of relevant memory entries, sorted by relevance
        """
        entries = list(self.entries.values())

        # Filter by scope if specified
        if scope:
            entries = [e for e in entries if e.scope == scope]

        # Filter by keywords if specified
        if keywords:
            filtered = []
            for entry in entries:
                # Check if any keyword matches key, summary, or value
                entry_text = f"{entry.key} {entry.summary} {str(entry.value)}".lower()
                if any(kw.lower() in entry_text for kw in keywords):
                    filtered.append(entry)
            entries = filtered

        # Sort by relevance score and access count
        entries.sort(key=lambda e: (e.relevance_score, e.access_count), reverse=True)

        return entries[:limit]

    def to_context_dict(self) -> dict[str, Any]:
        """Export memory as a context dictionary for agent use."""
        return {
            "memory_id": self.memory_id,
            "session_id": self.session_id,
            "total_entries": len(self.entries),
            "by_type": {k: len(v) for k, v in self.by_type.items()},
            "by_scope": {k: len(v) for k, v in self.by_scope.items()},
            "entries": {
                entry.key: {
                    "value": entry.value,
                    "summary": entry.summary,
                    "type": entry.memory_type.value,
                    "scope": entry.scope.value,
                }
                for entry in self.entries.values()
            },
        }


class FeedbackStatus(str, Enum):
    """Status of a feedback request."""

    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXPIRED = "expired"
    CANCELLED = "cancelled"


class FeedbackType(str, Enum):
    """Type of feedback request."""

    APPROVAL = "approval"  # Yes/No approval
    INPUT = "input"  # Free-form text input
    CHOICE = "choice"  # Multiple choice selection
    REVIEW = "review"  # Review and comment


class FeedbackOption(BaseModel):
    """An option for choice-type feedback."""

    option_id: str
    label: str
    description: str = ""
    is_default: bool = False


class FeedbackRequest(BaseModel):
    """A human-in-the-loop feedback request.

    FeedbackRequest represents a request for human input during agent
    execution. This enables human oversight and approval at critical
    decision points in the workflow.
    """

    request_id: str
    session_id: str
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)

    # Request type and status
    feedback_type: FeedbackType
    status: FeedbackStatus = FeedbackStatus.PENDING

    # Content
    title: str
    description: str = ""
    context: dict[str, Any] = Field(default_factory=dict)

    # For choice type
    options: list[FeedbackOption] = Field(default_factory=list)

    # Linked entities
    skill_execution_id: str | None = None
    task_id: str | None = None
    workflow_stage: str | None = None

    # Response
    response: Any = None
    response_text: str = ""
    responded_at: datetime | None = None
    responded_by: str | None = None  # User ID

    # Slack integration
    channel_id: str | None = None
    thread_ts: str | None = None
    message_ts: str | None = None  # Message containing the request

    # Expiration
    expires_at: datetime | None = None

    def approve(self, user_id: str, comment: str = "") -> None:
        """Approve this feedback request.

        Args:
            user_id: ID of the user approving
            comment: Optional approval comment
        """
        self.status = FeedbackStatus.APPROVED
        self.response = True
        self.response_text = comment
        self.responded_at = datetime.now()
        self.responded_by = user_id
        self.updated_at = datetime.now()

    def reject(self, user_id: str, reason: str = "") -> None:
        """Reject this feedback request.

        Args:
            user_id: ID of the user rejecting
            reason: Reason for rejection
        """
        self.status = FeedbackStatus.REJECTED
        self.response = False
        self.response_text = reason
        self.responded_at = datetime.now()
        self.responded_by = user_id
        self.updated_at = datetime.now()

    def respond_with_input(self, user_id: str, text: str) -> None:
        """Respond with free-form text input.

        Args:
            user_id: ID of the user responding
            text: The input text
        """
        self.status = FeedbackStatus.APPROVED
        self.response = text
        self.response_text = text
        self.responded_at = datetime.now()
        self.responded_by = user_id
        self.updated_at = datetime.now()

    def respond_with_choice(self, user_id: str, option_id: str) -> None:
        """Respond with a choice selection.

        Args:
            user_id: ID of the user responding
            option_id: ID of the selected option
        """
        selected = next((o for o in self.options if o.option_id == option_id), None)
        if selected:
            self.status = FeedbackStatus.APPROVED
            self.response = option_id
            self.response_text = selected.label
            self.responded_at = datetime.now()
            self.responded_by = user_id
            self.updated_at = datetime.now()

    def cancel(self) -> None:
        """Cancel this feedback request."""
        self.status = FeedbackStatus.CANCELLED
        self.updated_at = datetime.now()

    def is_expired(self) -> bool:
        """Check if this feedback request has expired."""
        if self.expires_at is None:
            return False
        return datetime.now() > self.expires_at

    def is_pending(self) -> bool:
        """Check if this feedback request is still pending."""
        return self.status == FeedbackStatus.PENDING and not self.is_expired()

    def to_slack_message(self) -> dict[str, Any]:
        """Convert to a Slack message format.

        Returns:
            Dictionary suitable for Slack message API
        """
        emoji_map = {
            FeedbackType.APPROVAL: ":question:",
            FeedbackType.INPUT: ":memo:",
            FeedbackType.CHOICE: ":ballot_box_with_ballot:",
            FeedbackType.REVIEW: ":eyes:",
        }

        blocks = [
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"{emoji_map.get(self.feedback_type, ':bell:')} *{self.title}*",
                },
            }
        ]

        if self.description:
            blocks.append(
                {
                    "type": "section",
                    "text": {"type": "mrkdwn", "text": self.description},
                }
            )

        if self.feedback_type == FeedbackType.APPROVAL:
            blocks.append(
                {
                    "type": "actions",
                    "elements": [
                        {
                            "type": "button",
                            "text": {"type": "plain_text", "text": "Approve"},
                            "style": "primary",
                            "action_id": f"approve_{self.request_id}",
                        },
                        {
                            "type": "button",
                            "text": {"type": "plain_text", "text": "Reject"},
                            "style": "danger",
                            "action_id": f"reject_{self.request_id}",
                        },
                    ],
                }
            )
        elif self.feedback_type == FeedbackType.CHOICE and self.options:
            elements = [
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": opt.label},
                    "action_id": f"choice_{self.request_id}_{opt.option_id}",
                }
                for opt in self.options[:5]  # Slack limit
            ]
            blocks.append({"type": "actions", "elements": elements})

        blocks.append(
            {
                "type": "context",
                "elements": [
                    {
                        "type": "mrkdwn",
                        "text": f"_Request ID: {self.request_id}_",
                    }
                ],
            }
        )

        return {"blocks": blocks}


def create_approval_request(
    request_id: str,
    session_id: str,
    title: str,
    description: str = "",
    task_id: str | None = None,
    workflow_stage: str | None = None,
    channel_id: str | None = None,
    thread_ts: str | None = None,
) -> FeedbackRequest:
    """Create an approval-type feedback request.

    Args:
        request_id: Unique request ID
        session_id: Parent session ID
        title: Request title
        description: Request description
        task_id: Linked task ID
        workflow_stage: Current workflow stage
        channel_id: Slack channel ID
        thread_ts: Slack thread timestamp

    Returns:
        A new FeedbackRequest configured for approval
    """
    return FeedbackRequest(
        request_id=request_id,
        session_id=session_id,
        feedback_type=FeedbackType.APPROVAL,
        title=title,
        description=description,
        task_id=task_id,
        workflow_stage=workflow_stage,
        channel_id=channel_id,
        thread_ts=thread_ts,
    )


def create_choice_request(
    request_id: str,
    session_id: str,
    title: str,
    options: list[tuple[str, str, str]],  # (id, label, description)
    description: str = "",
    task_id: str | None = None,
) -> FeedbackRequest:
    """Create a choice-type feedback request.

    Args:
        request_id: Unique request ID
        session_id: Parent session ID
        title: Request title
        options: List of (option_id, label, description) tuples
        description: Request description
        task_id: Linked task ID

    Returns:
        A new FeedbackRequest configured for choice selection
    """
    feedback_options = [
        FeedbackOption(option_id=oid, label=label, description=desc) for oid, label, desc in options
    ]

    return FeedbackRequest(
        request_id=request_id,
        session_id=session_id,
        feedback_type=FeedbackType.CHOICE,
        title=title,
        description=description,
        options=feedback_options,
        task_id=task_id,
    )
