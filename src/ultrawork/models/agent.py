"""Agent session and execution tracking models.

This module provides models for tracking agent sessions, role transitions,
and overall agent lifecycle management for the supervision system.
"""

from datetime import datetime
from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field


class AgentRole(str, Enum):
    """Role of the agent during execution.

    Roles represent the current focus/mode of the agent as it progresses
    through the workflow stages.
    """

    RESPONDER = "responder"  # Initial mention response
    PLANNER = "planner"  # Context exploration, TODO creation
    SPEC_WRITER = "spec_writer"  # Technical specification
    IMPLEMENTER = "implementer"  # Code implementation
    REPORTER = "reporter"  # Final reporting
    REVIEWER = "reviewer"  # Approval/rejection handling


class SessionStatus(str, Enum):
    """Status of an agent session."""

    INITIALIZING = "initializing"
    ACTIVE = "active"
    WAITING_FEEDBACK = "waiting_feedback"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class RoleTransition(BaseModel):
    """Records a single role transition during a session."""

    from_role: AgentRole
    to_role: AgentRole
    timestamp: datetime = Field(default_factory=datetime.now)
    reason: str = ""
    trigger_skill: str | None = None  # Skill that caused transition


class AgentSession(BaseModel):
    """Tracks a complete agent working session.

    An AgentSession represents a single end-to-end work session,
    typically triggered by a Slack mention. It tracks:
    - The current role and role transition history
    - All skill executions within the session
    - Linked artifacts (explorations, tasks, specs)
    - Feedback requests and responses
    - Session metrics (duration, tokens, tool calls)
    """

    session_id: str  # UUID
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)
    completed_at: datetime | None = None

    # Source information
    trigger_type: Literal["mention", "manual", "scheduled"] = "mention"
    channel_id: str = ""
    thread_ts: str = ""
    user_id: str = ""
    original_message: str = ""

    # Session state
    status: SessionStatus = SessionStatus.INITIALIZING
    current_role: AgentRole = AgentRole.RESPONDER

    # Linked artifacts
    exploration_id: str | None = None
    task_id: str | None = None
    spec_file: str | None = None
    forked_from: str | None = None  # session_id of fork source

    # Workflow tracking
    workflow_type: Literal["simple", "full"] | None = None
    current_stage: str | None = None

    # Role transition history
    role_transitions: list[RoleTransition] = Field(default_factory=list)

    # Skill executions within this session
    skill_executions: list[str] = Field(default_factory=list)  # SkillExecution IDs

    # Feedback requests
    pending_feedback: list[str] = Field(default_factory=list)  # FeedbackRequest IDs

    # Memory references
    context_memory_id: str | None = None

    # Metrics
    total_duration_ms: int = 0
    token_usage: int = 0
    tool_calls: int = 0

    def transition_role(self, new_role: AgentRole, reason: str = "") -> None:
        """Record a role transition.

        Args:
            new_role: The new role to transition to
            reason: Optional reason for the transition
        """
        transition = RoleTransition(
            from_role=self.current_role,
            to_role=new_role,
            timestamp=datetime.now(),
            reason=reason,
        )
        self.role_transitions.append(transition)
        self.current_role = new_role
        self.updated_at = datetime.now()

    def add_skill_execution(self, execution_id: str) -> None:
        """Add a skill execution ID to the session."""
        self.skill_executions.append(execution_id)
        self.updated_at = datetime.now()

    def add_pending_feedback(self, feedback_id: str) -> None:
        """Add a pending feedback request ID."""
        self.pending_feedback.append(feedback_id)
        self.status = SessionStatus.WAITING_FEEDBACK
        self.updated_at = datetime.now()

    def resolve_feedback(self, feedback_id: str) -> None:
        """Mark a feedback request as resolved."""
        if feedback_id in self.pending_feedback:
            self.pending_feedback.remove(feedback_id)
        if not self.pending_feedback:
            self.status = SessionStatus.ACTIVE
        self.updated_at = datetime.now()

    def complete(self, success: bool = True) -> None:
        """Mark the session as completed.

        Args:
            success: Whether the session completed successfully
        """
        self.completed_at = datetime.now()
        self.status = SessionStatus.COMPLETED if success else SessionStatus.FAILED
        if self.created_at:
            self.total_duration_ms = int(
                (self.completed_at - self.created_at).total_seconds() * 1000
            )
        self.updated_at = datetime.now()

    def link_exploration(self, exploration_id: str) -> None:
        """Link an exploration to this session."""
        self.exploration_id = exploration_id
        self.updated_at = datetime.now()

    def link_task(
        self, task_id: str, workflow_type: Literal["simple", "full"] | None = None
    ) -> None:
        """Link a task to this session."""
        self.task_id = task_id
        if workflow_type:
            self.workflow_type = workflow_type
        self.updated_at = datetime.now()

    def update_stage(self, stage: str) -> None:
        """Update the current workflow stage."""
        self.current_stage = stage
        self.updated_at = datetime.now()

    def to_timeline_events(self) -> list[dict]:
        """Convert session history to timeline events for visualization."""
        events = []

        # Session created
        events.append(
            {
                "type": "session_created",
                "timestamp": self.created_at.isoformat(),
                "data": {
                    "trigger_type": self.trigger_type,
                    "channel_id": self.channel_id,
                    "user_id": self.user_id,
                },
            }
        )

        # Role transitions
        for transition in self.role_transitions:
            events.append(
                {
                    "type": "role_transition",
                    "timestamp": transition.timestamp.isoformat(),
                    "data": {
                        "from_role": transition.from_role.value,
                        "to_role": transition.to_role.value,
                        "reason": transition.reason,
                        "trigger_skill": transition.trigger_skill,
                    },
                }
            )

        # Session completed
        if self.completed_at:
            events.append(
                {
                    "type": "session_completed",
                    "timestamp": self.completed_at.isoformat(),
                    "data": {
                        "status": self.status.value,
                        "duration_ms": self.total_duration_ms,
                    },
                }
            )

        return sorted(events, key=lambda e: e["timestamp"])
