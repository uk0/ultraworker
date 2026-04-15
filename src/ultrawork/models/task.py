"""Task data model for workflow management."""

import json
from datetime import datetime
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator


class WorkflowStage(str, Enum):
    """Workflow stages for task processing."""

    TODO = "todo"
    TECH_SPEC = "tech_spec"
    CODE_WORK = "code_work"
    FINAL_REPORT = "final_report"
    DONE = "done"


class StageStatus(str, Enum):
    """Status of a workflow stage."""

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    APPROVED = "approved"
    REJECTED = "rejected"
    SKIPPED = "skipped"


class WorkflowType(str, Enum):
    """Type of workflow - full or simplified."""

    FULL = "full"
    SIMPLE = "simple"


class TaskSource(BaseModel):
    """Source information for a task."""

    type: Literal["slack_thread", "manual"] = "slack_thread"
    thread_id: str | None = None
    trigger_message_ts: str | None = None
    requester: str | None = None


class StageInfo(BaseModel):
    """Information about a workflow stage."""

    status: StageStatus = StageStatus.PENDING
    started_at: datetime | None = None
    approved_at: datetime | None = None
    approved_by: str | None = None
    rejected_at: datetime | None = None
    rejected_by: str | None = None
    rejection_reason: str | None = None
    spec_file: str | None = None
    executor: Literal["claude", "codex"] | None = None


class WorkflowState(BaseModel):
    """Current workflow state for a task."""

    current_stage: WorkflowStage = WorkflowStage.TODO
    type: WorkflowType = WorkflowType.FULL

    stages: dict[str, StageInfo] = Field(
        default_factory=lambda: {
            "todo": StageInfo(),
            "tech_spec": StageInfo(),
            "code_work": StageInfo(),
            "final_report": StageInfo(),
        }
    )


class Artifact(BaseModel):
    """An artifact produced during task execution."""

    type: Literal["spec", "code_change", "report", "other"]
    path: str | None = None
    repo: str | None = None
    pr_url: str | None = None
    description: str | None = None


class TraceEntry(BaseModel):
    """A trace entry for auditing task actions."""

    ts: datetime
    action: str
    details: str | None = None
    stage: str | None = None
    by: str | None = None

    @field_validator("details", mode="before")
    @classmethod
    def coerce_details(cls, v: Any) -> str | None:
        if isinstance(v, dict):
            return json.dumps(v, ensure_ascii=False)
        return v


class TaskRecord(BaseModel):
    """A task record with full workflow state and tracing."""

    task_id: str
    title: str
    created_at: datetime
    updated_at: datetime

    source: TaskSource
    workflow: WorkflowState = Field(default_factory=WorkflowState)

    artifacts: list[Artifact] = Field(default_factory=list)
    trace: list[TraceEntry] = Field(default_factory=list)

    todo_items: list[str] = Field(default_factory=list)
    request_content: str = ""
    work_notes: str = ""

    @classmethod
    def generate_id(cls) -> str:
        """Generate a new task ID."""
        now = datetime.now()
        import random

        suffix = f"{random.randint(0, 999):03d}"
        return f"TASK-{now.strftime('%Y-%m%d')}-{suffix}"

    def get_file_path(self, base_dir: str = "data/tasks") -> str:
        """Get the file path for this task record."""
        return f"{base_dir}/{self.task_id}.md"

    def add_trace(self, action: str, details: str | None = None, **kwargs: str | None) -> None:
        """Add a trace entry."""
        self.trace.append(
            TraceEntry(
                ts=datetime.now(),
                action=action,
                details=details,
                stage=kwargs.get("stage"),
                by=kwargs.get("by"),
            )
        )
        self.updated_at = datetime.now()

    def get_next_stage(self) -> WorkflowStage | None:
        """Get the next stage in the workflow."""
        stage_order = [
            WorkflowStage.TODO,
            WorkflowStage.TECH_SPEC,
            WorkflowStage.CODE_WORK,
            WorkflowStage.FINAL_REPORT,
            WorkflowStage.DONE,
        ]

        if self.workflow.type == WorkflowType.SIMPLE:
            stage_order = [
                WorkflowStage.TODO,
                WorkflowStage.FINAL_REPORT,
                WorkflowStage.DONE,
            ]

        current_idx = stage_order.index(self.workflow.current_stage)
        if current_idx < len(stage_order) - 1:
            return stage_order[current_idx + 1]
        return None
