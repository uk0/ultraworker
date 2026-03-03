"""Skill execution tracking models.

This module provides models for tracking individual skill executions,
including their inputs, outputs, operations, and metrics.
"""

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class SkillStatus(str, Enum):
    """Status of a skill execution."""

    PENDING = "pending"
    RUNNING = "running"
    WAITING_INPUT = "waiting_input"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


class SkillOperation(BaseModel):
    """A single operation within a skill execution.

    Operations represent individual tool calls, API requests, or file
    operations that occur during skill execution.
    """

    operation_id: str
    operation_type: str  # "tool_call", "api_call", "file_write", "file_read", etc.
    name: str  # Tool/function name
    timestamp: datetime = Field(default_factory=datetime.now)

    input_summary: str = ""  # Truncated input for display
    output_summary: str = ""  # Truncated output for display

    duration_ms: int = 0
    success: bool = True
    error: str | None = None

    # Additional metadata
    metadata: dict[str, Any] = Field(default_factory=dict)


class SkillExecution(BaseModel):
    """Tracks a single skill execution.

    A SkillExecution represents one invocation of a skill (e.g., /explore-context,
    /create-todo) within an agent session. It tracks:
    - Input arguments and output data
    - Role context (before and after)
    - Individual operations within the skill
    - Timing and metrics
    - Error information if failed
    """

    execution_id: str  # UUID
    session_id: str  # Parent AgentSession ID
    skill_name: str  # e.g., "explore-context", "create-todo", "write-spec"

    started_at: datetime = Field(default_factory=datetime.now)
    completed_at: datetime | None = None
    status: SkillStatus = SkillStatus.PENDING

    # Input/Output
    input_args: dict[str, Any] = Field(default_factory=dict)
    output_data: dict[str, Any] = Field(default_factory=dict)

    # Role context
    role_at_start: str = ""
    role_at_end: str = ""

    # Sub-operations (tool calls within skill)
    operations: list[SkillOperation] = Field(default_factory=list)

    # Error information
    error_message: str | None = None
    error_type: str | None = None

    # Metrics
    duration_ms: int = 0
    tool_calls: int = 0
    api_calls: int = 0

    # Artifacts produced
    artifacts: list[str] = Field(default_factory=list)  # File paths

    # Linked entities
    exploration_id: str | None = None
    task_id: str | None = None

    def start(self) -> None:
        """Mark the execution as started."""
        self.status = SkillStatus.RUNNING
        self.started_at = datetime.now()

    def complete(self, output_data: dict[str, Any] | None = None) -> None:
        """Mark the execution as completed.

        Args:
            output_data: Optional output data from the skill
        """
        self.status = SkillStatus.COMPLETED
        self.completed_at = datetime.now()
        if output_data:
            self.output_data = output_data
        self._calculate_duration()

    def fail(self, error_message: str, error_type: str | None = None) -> None:
        """Mark the execution as failed.

        Args:
            error_message: Error description
            error_type: Type/category of error
        """
        self.status = SkillStatus.FAILED
        self.completed_at = datetime.now()
        self.error_message = error_message
        self.error_type = error_type
        self._calculate_duration()

    def _calculate_duration(self) -> None:
        """Calculate execution duration."""
        if self.completed_at and self.started_at:
            self.duration_ms = int((self.completed_at - self.started_at).total_seconds() * 1000)

    def add_operation(
        self,
        operation_id: str,
        operation_type: str,
        name: str,
        input_summary: str = "",
        output_summary: str = "",
        duration_ms: int = 0,
        success: bool = True,
        error: str | None = None,
    ) -> SkillOperation:
        """Add an operation to this execution.

        Args:
            operation_id: Unique operation ID
            operation_type: Type of operation (tool_call, api_call, etc.)
            name: Name of the tool/function
            input_summary: Truncated input
            output_summary: Truncated output
            duration_ms: Operation duration
            success: Whether operation succeeded
            error: Error message if failed

        Returns:
            The created SkillOperation
        """
        operation = SkillOperation(
            operation_id=operation_id,
            operation_type=operation_type,
            name=name,
            input_summary=input_summary,
            output_summary=output_summary,
            duration_ms=duration_ms,
            success=success,
            error=error,
        )
        self.operations.append(operation)

        # Update counters
        if operation_type == "tool_call":
            self.tool_calls += 1
        elif operation_type == "api_call":
            self.api_calls += 1

        return operation

    def add_artifact(self, path: str) -> None:
        """Add an artifact path produced by this execution."""
        if path not in self.artifacts:
            self.artifacts.append(path)

    def to_summary(self) -> dict[str, Any]:
        """Create a summary for display/logging."""
        return {
            "execution_id": self.execution_id,
            "skill_name": self.skill_name,
            "status": self.status.value,
            "duration_ms": self.duration_ms,
            "operations_count": len(self.operations),
            "tool_calls": self.tool_calls,
            "artifacts_count": len(self.artifacts),
            "role_at_start": self.role_at_start,
            "role_at_end": self.role_at_end,
            "error": self.error_message,
        }


# Skill name to role transition mapping
SKILL_ROLE_TRANSITIONS: dict[str, tuple[str | None, str | None]] = {
    "explore-context": (None, "planner"),  # Any -> PLANNER
    "create-todo": (None, None),  # No transition (stays PLANNER)
    "write-spec": ("planner", "spec_writer"),  # PLANNER -> SPEC_WRITER
    "approve": (None, None),  # Context-dependent (see below)
    "reject": (None, None),  # No role transition
    "report": ("implementer", "reporter"),  # IMPLEMENTER -> REPORTER
    "sync-slack": (None, None),  # Utility, no transition
    "respond-mention": (None, None),  # Initial response
    "manage-cronjob": (None, None),  # Utility, no transition
    "remember": (None, None),  # LTM save, no role transition
    "recall": (None, None),  # LTM search, no role transition
}

# Approve skill transitions based on current stage
APPROVE_STAGE_TRANSITIONS: dict[str, str] = {
    "tech_spec": "implementer",  # Approved spec -> IMPLEMENTER
    "code_work": "reporter",  # Approved code -> REPORTER
    "final_report": "",  # Approved report -> Session complete
}


def get_role_after_skill(skill_name: str, current_stage: str | None = None) -> str | None:
    """Get the role to transition to after a skill completes.

    Args:
        skill_name: Name of the skill that completed
        current_stage: Current workflow stage (for approve skill)

    Returns:
        New role to transition to, or None if no transition
    """
    if skill_name == "approve" and current_stage:
        return APPROVE_STAGE_TRANSITIONS.get(current_stage)

    _, new_role = SKILL_ROLE_TRANSITIONS.get(skill_name, (None, None))
    return new_role
