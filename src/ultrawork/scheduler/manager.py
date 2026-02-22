"""Cron job manager for CRUD operations on cron jobs.

Handles creation, listing, updating, and deletion of cron jobs,
persisting them as YAML files in the data/cronjobs/ directory.
"""

from datetime import datetime
from pathlib import Path
from typing import Literal

import yaml

from ultrawork.models.cronjob import (
    CronJob,
    CronJobAction,
    CronJobStatus,
    CronSchedule,
    CronScheduleType,
    ThreadTarget,
)


class CronJobManager:
    """Manages cron job lifecycle and persistence."""

    def __init__(self, data_dir: Path) -> None:
        self.data_dir = Path(data_dir)
        self.jobs_dir = self.data_dir / "cronjobs"
        self.logs_dir = self.data_dir / "cronjobs" / "logs"
        self.jobs_dir.mkdir(parents=True, exist_ok=True)
        self.logs_dir.mkdir(parents=True, exist_ok=True)

    def _generate_job_id(self) -> str:
        """Generate a unique cron job ID."""
        now = datetime.now()
        date_part = now.strftime("%Y-%m%d")

        # Find next sequence number
        existing = list(self.jobs_dir.glob(f"CRON-{date_part}-*.yaml"))
        seq = len(existing) + 1
        return f"CRON-{date_part}-{seq:03d}"

    def _job_path(self, job_id: str) -> Path:
        """Get the file path for a cron job."""
        return self.jobs_dir / f"{job_id}.yaml"

    def create_job(
        self,
        name: str,
        schedule: CronSchedule,
        action: CronJobAction,
        description: str = "",
        thread_targets: list[ThreadTarget] | None = None,
        channel_targets: list[str] | None = None,
        notify_user_id: str = "",
        notify_channel_id: str = "",
        auto_process: bool = False,
        require_approval: bool = True,
        action_config: dict | None = None,
        created_by: Literal["user", "skill", "system"] = "user",
        source_session_id: str | None = None,
    ) -> CronJob:
        """Create a new cron job.

        Args:
            name: Human-readable job name
            schedule: Cron schedule configuration
            action: Action to perform
            description: Job description
            thread_targets: Threads to monitor
            channel_targets: Channel IDs to monitor
            notify_user_id: User to DM
            notify_channel_id: DM channel ID
            auto_process: Process without asking
            require_approval: Ask via DM before acting
            action_config: Additional action config
            created_by: Creator type (user/skill/system)
            source_session_id: Session that created this

        Returns:
            Created CronJob instance
        """
        job_id = self._generate_job_id()

        job = CronJob(
            job_id=job_id,
            name=name,
            description=description,
            schedule=schedule,
            action=action,
            action_config=action_config or {},
            thread_targets=thread_targets or [],
            channel_targets=channel_targets or [],
            notify_user_id=notify_user_id,
            notify_channel_id=notify_channel_id,
            auto_process=auto_process,
            require_approval=require_approval,
            created_by=created_by,
            source_session_id=source_session_id,
        )

        self._save_job(job)
        return job

    def _save_job(self, job: CronJob) -> None:
        """Save a cron job to YAML file."""
        path = self._job_path(job.job_id)
        data = job.model_dump(mode="json")
        # Convert datetime fields
        for key in ("created_at", "updated_at", "last_run_at", "next_run_at"):
            if data.get(key):
                data[key] = str(data[key])
        path.write_text(
            yaml.dump(data, allow_unicode=True, default_flow_style=False),
            encoding="utf-8",
        )

    def load_job(self, job_id: str) -> CronJob | None:
        """Load a cron job from file."""
        path = self._job_path(job_id)
        if not path.exists():
            return None

        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        if not data:
            return None

        return CronJob(**data)

    def list_jobs(
        self,
        status: CronJobStatus | None = None,
        active_only: bool = False,
    ) -> list[CronJob]:
        """List all cron jobs, optionally filtered by status.

        Args:
            status: Filter by specific status
            active_only: If True, only return active jobs

        Returns:
            List of CronJob instances
        """
        jobs = []
        for path in sorted(self.jobs_dir.glob("CRON-*.yaml")):
            try:
                data = yaml.safe_load(path.read_text(encoding="utf-8"))
                if not data:
                    continue
                job = CronJob(**data)

                if status and job.status != status:
                    continue
                if active_only and job.status != CronJobStatus.ACTIVE:
                    continue

                jobs.append(job)
            except Exception:
                continue

        return jobs

    def update_job(self, job: CronJob) -> None:
        """Update an existing cron job."""
        job.updated_at = datetime.now()
        self._save_job(job)

    def delete_job(self, job_id: str) -> bool:
        """Soft-delete a cron job (mark as deleted)."""
        job = self.load_job(job_id)
        if not job:
            return False

        job.delete()
        self._save_job(job)
        return True

    def pause_job(self, job_id: str) -> bool:
        """Pause a cron job."""
        job = self.load_job(job_id)
        if not job:
            return False

        job.pause()
        self._save_job(job)
        return True

    def resume_job(self, job_id: str) -> bool:
        """Resume a paused cron job."""
        job = self.load_job(job_id)
        if not job:
            return False

        job.resume()
        self._save_job(job)
        return True

    def record_execution(self, job_id: str, success: bool = True, error: str | None = None) -> bool:
        """Record a job execution result."""
        job = self.load_job(job_id)
        if not job:
            return False

        job.record_run(success=success, error=error)
        self._save_job(job)
        return True

    def get_active_jobs(self) -> list[CronJob]:
        """Get all active cron jobs."""
        return self.list_jobs(active_only=True)

    def create_thread_monitor_job(
        self,
        name: str,
        threads: list[dict],
        schedule_type: str = "weekday",
        at: str = "09:00",
        notify_user_id: str = "",
        notify_channel_id: str = "",
    ) -> CronJob:
        """Convenience method to create a thread monitoring job.

        Args:
            name: Job name
            threads: List of {"channel_id": ..., "thread_ts": ..., "description": ...}
            schedule_type: "interval", "daily", "weekday"
            at: Time for daily/weekday schedules
            notify_user_id: User to DM
            notify_channel_id: DM channel ID

        Returns:
            Created CronJob
        """
        schedule = CronSchedule(
            type=CronScheduleType(schedule_type),
            at=at,
        )

        targets = [
            ThreadTarget(
                channel_id=t["channel_id"],
                thread_ts=t["thread_ts"],
                description=t.get("description", ""),
                channel_name=t.get("channel_name", ""),
            )
            for t in threads
        ]

        return self.create_job(
            name=name,
            schedule=schedule,
            action=CronJobAction.CHECK_THREAD_REACTIONS,
            thread_targets=targets,
            notify_user_id=notify_user_id,
            notify_channel_id=notify_channel_id,
            require_approval=True,
        )

    def create_mention_scan_job(
        self,
        name: str,
        channels: list[str],
        schedule_type: str = "interval",
        hours: int = 2,
        notify_user_id: str = "",
        notify_channel_id: str = "",
    ) -> CronJob:
        """Convenience method to create a mention scanning job.

        Args:
            name: Job name
            channels: Channel IDs to scan
            schedule_type: Schedule type
            hours: Hours between scans (for interval type)
            notify_user_id: User to DM
            notify_channel_id: DM channel ID

        Returns:
            Created CronJob
        """
        schedule = CronSchedule(
            type=CronScheduleType(schedule_type),
            hours=hours,
        )

        return self.create_job(
            name=name,
            schedule=schedule,
            action=CronJobAction.SCAN_MENTIONS,
            channel_targets=channels,
            notify_user_id=notify_user_id,
            notify_channel_id=notify_channel_id,
            require_approval=True,
        )
