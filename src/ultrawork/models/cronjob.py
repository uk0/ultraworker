"""Cronjob models for scheduled task execution.

This module provides models for defining and managing cron jobs
that periodically check threads, monitor reactions, and trigger
actions based on configurable schedules.
"""

from datetime import datetime
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field


class CronScheduleType(str, Enum):
    """Type of cron schedule."""

    INTERVAL = "interval"  # Every N hours/minutes
    DAILY = "daily"  # At specific time daily
    WEEKDAY = "weekday"  # At specific time on weekdays (Mon-Fri)
    WEEKLY = "weekly"  # At specific time on specific day of week
    CRON = "cron"  # Full cron expression


class CronJobStatus(str, Enum):
    """Status of a cron job."""

    ACTIVE = "active"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    DELETED = "deleted"


class CronJobAction(str, Enum):
    """Actions a cron job can perform."""

    CHECK_THREAD_REACTIONS = "check_thread_reactions"
    MONITOR_THREAD_UPDATES = "monitor_thread_updates"
    SCAN_MENTIONS = "scan_mentions"
    DM_PENDING_TASKS = "dm_pending_tasks"
    CUSTOM = "custom"


class CronSchedule(BaseModel):
    """Defines a cron schedule.

    Supports multiple schedule types:
    - interval: {"type": "interval", "hours": 2}
    - daily: {"type": "daily", "at": "09:00"}
    - weekday: {"type": "weekday", "at": "09:00"}
    - weekly: {"type": "weekly", "day": "monday", "at": "09:00"}
    - cron: {"type": "cron", "expression": "0 9 * * 1-5"}
    """

    type: CronScheduleType = CronScheduleType.INTERVAL
    # For interval type
    hours: int | None = None
    minutes: int | None = None
    # For daily/weekday/weekly
    at: str | None = None  # "HH:MM" format (24h)
    # For weekly
    day: str | None = None  # "monday", "tuesday", etc.
    # For cron expression
    expression: str | None = None

    def get_description(self) -> str:
        """Get human-readable schedule description."""
        if self.type == CronScheduleType.INTERVAL:
            parts = []
            if self.hours:
                parts.append(f"{self.hours}h")
            if self.minutes:
                parts.append(f"{self.minutes}m")
            return f"Every {' '.join(parts)}" if parts else "Every hour"
        elif self.type == CronScheduleType.DAILY:
            return f"Daily at {self.at or '09:00'}"
        elif self.type == CronScheduleType.WEEKDAY:
            return f"Weekdays at {self.at or '09:00'}"
        elif self.type == CronScheduleType.WEEKLY:
            return f"Every {self.day or 'Monday'} at {self.at or '09:00'}"
        elif self.type == CronScheduleType.CRON:
            return f"Cron: {self.expression}"
        return "Unknown schedule"


class ThreadTarget(BaseModel):
    """A thread to monitor as part of a cron job."""

    channel_id: str
    thread_ts: str
    channel_name: str = ""
    description: str = ""  # What to look for in this thread


class CronJob(BaseModel):
    """A scheduled cron job definition.

    Cron jobs can:
    - Monitor threads for new reactions/replies
    - Check for pending approvals
    - Scan channels for unhandled mentions
    - Send DM summaries of pending work
    """

    job_id: str  # CRON-YYYY-MMDD-NNN format
    name: str
    description: str = ""

    # Schedule
    schedule: CronSchedule

    # Action
    action: CronJobAction
    action_config: dict[str, Any] = Field(default_factory=dict)

    # Targets (threads/channels to monitor)
    thread_targets: list[ThreadTarget] = Field(default_factory=list)
    channel_targets: list[str] = Field(default_factory=list)  # Channel IDs

    # DM notification settings
    notify_user_id: str = ""  # User to send DM to
    notify_channel_id: str = ""  # DM channel ID

    # Auto-action settings
    auto_process: bool = False  # If True, process without asking
    require_approval: bool = True  # If True, ask via DM before acting

    # Status
    status: CronJobStatus = CronJobStatus.ACTIVE
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)

    # Execution tracking
    last_run_at: datetime | None = None
    next_run_at: datetime | None = None
    run_count: int = 0
    error_count: int = 0
    last_error: str | None = None

    # Source
    created_by: Literal["user", "skill", "system"] = "user"
    source_session_id: str | None = None  # Session that created this job

    def pause(self) -> None:
        """Pause the cron job."""
        self.status = CronJobStatus.PAUSED
        self.updated_at = datetime.now()

    def resume(self) -> None:
        """Resume a paused cron job."""
        self.status = CronJobStatus.ACTIVE
        self.updated_at = datetime.now()

    def record_run(self, success: bool = True, error: str | None = None) -> None:
        """Record a run of the cron job."""
        self.last_run_at = datetime.now()
        self.run_count += 1
        self.updated_at = datetime.now()
        if not success:
            self.error_count += 1
            self.last_error = error

    def delete(self) -> None:
        """Mark the cron job as deleted."""
        self.status = CronJobStatus.DELETED
        self.updated_at = datetime.now()


class CronExecutionLog(BaseModel):
    """Log entry for a cron job execution."""

    log_id: str
    job_id: str
    executed_at: datetime = Field(default_factory=datetime.now)
    success: bool = True
    error: str | None = None

    # What was found
    threads_checked: int = 0
    new_reactions_found: int = 0
    new_replies_found: int = 0
    pending_tasks_found: int = 0

    # Actions taken
    dm_sent: bool = False
    dm_content: str = ""
    actions_proposed: list[str] = Field(default_factory=list)
    actions_approved: list[str] = Field(default_factory=list)
    actions_executed: list[str] = Field(default_factory=list)

    # Duration
    duration_ms: int = 0
