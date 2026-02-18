"""Cron job runner that executes scheduled jobs.

Provides the async scheduler loop that checks job schedules and
executes them. Can run as part of the SDK poller daemon or standalone.
"""

import asyncio
import logging
import os
import subprocess
import time
import uuid
from datetime import datetime
from pathlib import Path

import yaml

from ultrawork.models.cronjob import (
    CronExecutionLog,
    CronJob,
    CronJobAction,
    CronJobStatus,
    CronScheduleType,
)
from ultrawork.scheduler.manager import CronJobManager

logger = logging.getLogger("cron_runner")

# Day name to weekday number
DAY_MAP = {
    "monday": 0,
    "tuesday": 1,
    "wednesday": 2,
    "thursday": 3,
    "friday": 4,
    "saturday": 5,
    "sunday": 6,
}


class CronRunner:
    """Runs cron jobs on schedule.

    Can be integrated into the SDK poller daemon or run standalone.
    """

    def __init__(
        self,
        data_dir: Path,
        slack_token: str | None = None,
        slack_cookie: str | None = None,
    ) -> None:
        self.data_dir = Path(data_dir)
        self.manager = CronJobManager(data_dir)
        self.slack_token = slack_token
        self.slack_cookie = slack_cookie
        self._running = False
        self._stop_event = asyncio.Event()

    def _should_run(self, job: CronJob, now: datetime) -> bool:
        """Determine if a job should run now.

        Args:
            job: The cron job to check
            now: Current datetime

        Returns:
            True if the job should run
        """
        if job.status != CronJobStatus.ACTIVE:
            return False

        schedule = job.schedule

        # If never run, run now
        if job.last_run_at is None:
            return True

        last_run = job.last_run_at
        if isinstance(last_run, str):
            last_run = datetime.fromisoformat(last_run)

        if schedule.type == CronScheduleType.INTERVAL:
            interval_hours = schedule.hours or 0
            interval_minutes = schedule.minutes or 0
            total_minutes = interval_hours * 60 + interval_minutes
            if total_minutes <= 0:
                total_minutes = 60  # Default 1 hour
            elapsed = (now - last_run).total_seconds() / 60
            return elapsed >= total_minutes

        elif schedule.type == CronScheduleType.DAILY:
            target_time = schedule.at or "09:00"
            target_h, target_m = map(int, target_time.split(":"))
            # Run if we're past the target time and haven't run today
            if now.hour > target_h or (now.hour == target_h and now.minute >= target_m):
                return last_run.date() < now.date()
            return False

        elif schedule.type == CronScheduleType.WEEKDAY:
            target_time = schedule.at or "09:00"
            target_h, target_m = map(int, target_time.split(":"))
            # Only on weekdays (Mon-Fri = 0-4)
            if now.weekday() > 4:
                return False
            if now.hour > target_h or (now.hour == target_h and now.minute >= target_m):
                return last_run.date() < now.date()
            return False

        elif schedule.type == CronScheduleType.WEEKLY:
            target_time = schedule.at or "09:00"
            target_h, target_m = map(int, target_time.split(":"))
            target_day = DAY_MAP.get((schedule.day or "monday").lower(), 0)
            if now.weekday() != target_day:
                return False
            if now.hour > target_h or (now.hour == target_h and now.minute >= target_m):
                return (now - last_run).days >= 7
            return False

        elif schedule.type == CronScheduleType.CRON:
            # Simple cron expression support (limited)
            # For full support, consider croniter package
            return self._match_cron_expression(schedule.expression or "", now, last_run)

        return False

    def _match_cron_expression(
        self, expression: str, now: datetime, last_run: datetime
    ) -> bool:
        """Basic cron expression matcher.

        Supports: minute hour day_of_month month day_of_week
        Only handles simple patterns (no ranges, steps, etc.)

        Args:
            expression: Cron expression (e.g., "0 9 * * 1-5")
            now: Current time
            last_run: Last execution time
        """
        parts = expression.strip().split()
        if len(parts) != 5:
            return False

        minute, hour, dom, month, dow = parts

        def _matches(field: str, value: int) -> bool:
            if field == "*":
                return True
            # Handle ranges like "1-5"
            if "-" in field:
                start, end = map(int, field.split("-"))
                return start <= value <= end
            # Handle comma-separated values
            if "," in field:
                return value in [int(x) for x in field.split(",")]
            return value == int(field)

        if not _matches(minute, now.minute):
            return False
        if not _matches(hour, now.hour):
            return False
        if not _matches(dom, now.day):
            return False
        if not _matches(month, now.month):
            return False
        if not _matches(dow, now.weekday()):
            return False

        # Ensure we haven't already run this minute
        return last_run.replace(second=0, microsecond=0) < now.replace(
            second=0, microsecond=0
        )

    def _get_slack_client(self):
        """Create a Slack WebClient if token is available."""
        if not self.slack_token:
            return None

        from slack_sdk import WebClient

        headers = {}
        if self.slack_token.startswith("xoxc-") and self.slack_cookie:
            headers["Cookie"] = f"d={self.slack_cookie}"
        return WebClient(token=self.slack_token, headers=headers)

    def _execute_check_thread_reactions(self, job: CronJob) -> CronExecutionLog:
        """Execute a thread reaction checking job."""
        log = CronExecutionLog(
            log_id=str(uuid.uuid4())[:8],
            job_id=job.job_id,
        )
        start_time = time.time()

        client = self._get_slack_client()
        if not client:
            log.success = False
            log.error = "No Slack token available"
            return log

        findings = []
        for target in job.thread_targets:
            try:
                result = client.conversations_replies(
                    channel=target.channel_id,
                    ts=target.thread_ts,
                    limit=50,
                )
                messages = result.get("messages", [])
                log.threads_checked += 1

                # Check for new replies since last run
                last_run_ts = "0"
                if job.last_run_at:
                    last_run_dt = job.last_run_at
                    if isinstance(last_run_dt, str):
                        last_run_dt = datetime.fromisoformat(last_run_dt)
                    last_run_ts = str(last_run_dt.timestamp())

                new_replies = [
                    m
                    for m in messages[1:]  # Skip parent
                    if float(m.get("ts", "0")) > float(last_run_ts)
                ]
                log.new_replies_found += len(new_replies)

                # Check for reactions on thread parent
                parent = messages[0] if messages else {}
                reactions = parent.get("reactions", [])
                for reaction in reactions:
                    if reaction.get("name") in ("thumbsup", "+1", "white_check_mark"):
                        log.new_reactions_found += 1

                if new_replies:
                    reply_summaries = []
                    for reply in new_replies[:5]:  # Max 5 for summary
                        text = reply.get("text", "")[:100]
                        user = reply.get("user", "unknown")
                        reply_summaries.append(f"<@{user}>: {text}")

                    findings.append(
                        {
                            "thread": f"{target.channel_id}/{target.thread_ts}",
                            "channel_name": target.channel_name,
                            "description": target.description,
                            "new_replies": len(new_replies),
                            "reply_summaries": reply_summaries,
                            "reactions": [r.get("name", "") for r in reactions],
                        }
                    )

            except Exception as e:
                logger.error(
                    f"Failed to check thread {target.channel_id}/{target.thread_ts}: {e}"
                )
                log.error = str(e)

        # Send DM if there are findings and notification is configured
        if findings and job.notify_channel_id:
            dm_text = self._format_thread_check_dm(job, findings)
            log.dm_content = dm_text
            try:
                client.chat_postMessage(
                    channel=job.notify_channel_id,
                    text=dm_text,
                )
                log.dm_sent = True
            except Exception as e:
                logger.error(f"Failed to send DM: {e}")
                log.error = f"DM send failed: {e}"

        log.duration_ms = int((time.time() - start_time) * 1000)
        return log

    def _execute_monitor_thread_updates(self, job: CronJob) -> CronExecutionLog:
        """Execute a thread update monitoring job."""
        # Similar to check_thread_reactions but also looks for
        # unhandled requests and pending actions
        log = self._execute_check_thread_reactions(job)
        # Additional monitoring logic can be added here
        return log

    def _execute_scan_mentions(self, job: CronJob) -> CronExecutionLog:
        """Execute a mention scanning job."""
        log = CronExecutionLog(
            log_id=str(uuid.uuid4())[:8],
            job_id=job.job_id,
        )
        start_time = time.time()

        client = self._get_slack_client()
        if not client:
            log.success = False
            log.error = "No Slack token available"
            return log

        from ultrawork.config import get_config

        config = get_config()
        bot_user_id = config.slack.bot_user_id
        trigger_pattern = config.slack.trigger_pattern

        queries = []
        if bot_user_id:
            queries.append(f"<@{bot_user_id}>")
        if trigger_pattern:
            queries.append(trigger_pattern)

        findings = []
        for query in queries:
            try:
                result = client.search_messages(
                    query=query,
                    sort="timestamp",
                    sort_dir="desc",
                    count=20,
                )
                matches = result.get("messages", {}).get("matches", [])

                # Filter to recent messages since last run
                last_run_ts = "0"
                if job.last_run_at:
                    last_run_dt = job.last_run_at
                    if isinstance(last_run_dt, str):
                        last_run_dt = datetime.fromisoformat(last_run_dt)
                    last_run_ts = str(last_run_dt.timestamp())

                new_matches = [
                    m
                    for m in matches
                    if float(m.get("ts", "0")) > float(last_run_ts)
                ]

                for m in new_matches:
                    findings.append(
                        {
                            "channel": m.get("channel", {}).get("name", "unknown"),
                            "text": m.get("text", "")[:200],
                            "user": m.get("user", ""),
                            "ts": m.get("ts", ""),
                        }
                    )

            except Exception as e:
                logger.error(f"Mention scan failed for query '{query}': {e}")

        if findings and job.notify_channel_id:
            dm_text = self._format_mention_scan_dm(job, findings)
            log.dm_content = dm_text
            try:
                client.chat_postMessage(
                    channel=job.notify_channel_id,
                    text=dm_text,
                )
                log.dm_sent = True
            except Exception as e:
                logger.error(f"Failed to send DM: {e}")

        log.pending_tasks_found = len(findings)
        log.duration_ms = int((time.time() - start_time) * 1000)
        return log

    def _execute_dm_pending_tasks(self, job: CronJob) -> CronExecutionLog:
        """Execute a pending tasks DM summary job."""
        log = CronExecutionLog(
            log_id=str(uuid.uuid4())[:8],
            job_id=job.job_id,
        )
        start_time = time.time()

        # Check for pending approvals from task files
        from ultrawork.context import ContextIndexer

        indexer = ContextIndexer(self.data_dir)
        pending = indexer.get_pending_approvals()
        log.pending_tasks_found = len(pending)

        if pending and job.notify_channel_id:
            client = self._get_slack_client()
            if client:
                dm_text = self._format_pending_tasks_dm(job, pending)
                log.dm_content = dm_text
                try:
                    client.chat_postMessage(
                        channel=job.notify_channel_id,
                        text=dm_text,
                    )
                    log.dm_sent = True
                except Exception as e:
                    logger.error(f"Failed to send DM: {e}")

        log.duration_ms = int((time.time() - start_time) * 1000)
        return log

    def _execute_custom(self, job: CronJob) -> CronExecutionLog:
        """Execute a custom cron job via Claude CLI."""
        log = CronExecutionLog(
            log_id=str(uuid.uuid4())[:8],
            job_id=job.job_id,
        )
        start_time = time.time()

        prompt = job.action_config.get("prompt", "")
        if not prompt:
            log.success = False
            log.error = "No prompt configured for custom job"
            return log

        try:
            env = os.environ.copy()
            env["IS_SANDBOX"] = "1"

            result = subprocess.run(
                [
                    "claude",
                    "--dangerously-skip-permissions",
                    "-p",
                    prompt,
                ],
                timeout=600,
                capture_output=True,
                text=True,
                cwd=str(self.data_dir.parent),
                env=env,
            )

            log.success = result.returncode == 0
            if not log.success:
                log.error = result.stderr[:500] if result.stderr else "Unknown error"

        except subprocess.TimeoutExpired:
            log.success = False
            log.error = "Custom job timed out"
        except Exception as e:
            log.success = False
            log.error = str(e)

        log.duration_ms = int((time.time() - start_time) * 1000)
        return log

    def execute_job(self, job: CronJob) -> CronExecutionLog:
        """Execute a single cron job.

        Args:
            job: The cron job to execute

        Returns:
            Execution log
        """
        logger.info(f"Executing cron job: {job.job_id} ({job.name})")

        action_handlers = {
            CronJobAction.CHECK_THREAD_REACTIONS: self._execute_check_thread_reactions,
            CronJobAction.MONITOR_THREAD_UPDATES: self._execute_monitor_thread_updates,
            CronJobAction.SCAN_MENTIONS: self._execute_scan_mentions,
            CronJobAction.DM_PENDING_TASKS: self._execute_dm_pending_tasks,
            CronJobAction.CUSTOM: self._execute_custom,
        }

        handler = action_handlers.get(job.action, self._execute_custom)
        log = handler(job)

        # Record execution
        self.manager.record_execution(
            job.job_id,
            success=log.success,
            error=log.error,
        )

        # Save execution log
        log_path = self.manager.logs_dir / f"{job.job_id}_{log.log_id}.yaml"
        log_path.write_text(
            yaml.dump(log.model_dump(mode="json"), allow_unicode=True),
            encoding="utf-8",
        )

        logger.info(
            f"Cron job {job.job_id} completed: success={log.success}, "
            f"duration={log.duration_ms}ms"
        )
        return log

    def _format_thread_check_dm(self, job: CronJob, findings: list[dict]) -> str:
        """Format a DM message for thread check results."""
        lines = [f"*{job.name}* - Thread Update Summary\n"]

        for f in findings:
            desc = f.get("description", "")
            ch_name = f.get("channel_name", "")
            header = f"*#{ch_name}*" if ch_name else f"`{f['thread']}`"
            if desc:
                header += f" - {desc}"
            lines.append(header)

            if f.get("new_replies", 0) > 0:
                lines.append(f"  New replies: {f['new_replies']}")
                for summary in f.get("reply_summaries", []):
                    lines.append(f"  > {summary}")

            reactions = f.get("reactions", [])
            if reactions:
                emoji_str = " ".join(f":{r}:" for r in reactions)
                lines.append(f"  Reactions: {emoji_str}")

            lines.append("")

        lines.append(
            "Reply with the thread link to process, or ignore to skip."
        )
        return "\n".join(lines)

    def _format_mention_scan_dm(self, job: CronJob, findings: list[dict]) -> str:
        """Format a DM message for mention scan results."""
        lines = [
            f"*{job.name}* - Unhandled Mentions Found: {len(findings)}\n"
        ]

        for f in findings[:10]:
            lines.append(f"*#{f['channel']}* - <@{f['user']}>")
            lines.append(f"  > {f['text'][:150]}")
            lines.append("")

        if len(findings) > 10:
            lines.append(f"...and {len(findings) - 10} more")

        lines.append(
            "\nReply with 'process [number]' to handle, or 'skip' to ignore all."
        )
        return "\n".join(lines)

    def _format_pending_tasks_dm(self, job: CronJob, pending: list[dict]) -> str:
        """Format a DM message for pending tasks summary."""
        lines = [
            f"*{job.name}* - Pending Approvals: {len(pending)}\n"
        ]

        for p in pending:
            lines.append(f"*{p['task_id']}* - {p['title']}")
            lines.append(f"  Stage: {p['stage']}")
            lines.append("")

        lines.append(
            "Use `/approve <task_id>` or `/reject <task_id>` to process."
        )
        return "\n".join(lines)

    async def run_tick(self) -> int:
        """Check all jobs and execute those that are due.

        Returns:
            Number of jobs executed
        """
        now = datetime.now()
        active_jobs = self.manager.get_active_jobs()
        executed = 0

        for job in active_jobs:
            if self._should_run(job, now):
                try:
                    self.execute_job(job)
                    executed += 1
                except Exception as e:
                    logger.error(f"Failed to execute job {job.job_id}: {e}")
                    self.manager.record_execution(
                        job.job_id, success=False, error=str(e)
                    )

        return executed

    async def run_daemon(self, check_interval: int = 60) -> None:
        """Run as a continuous daemon, checking jobs periodically.

        Args:
            check_interval: Seconds between schedule checks
        """
        self._running = True
        self._stop_event = asyncio.Event()
        logger.info("Cron runner daemon started")

        try:
            while self._running:
                try:
                    executed = await self.run_tick()
                    if executed > 0:
                        logger.info(f"Executed {executed} cron jobs")
                except Exception as e:
                    logger.error(f"Cron tick error: {e}")

                try:
                    await asyncio.wait_for(
                        self._stop_event.wait(),
                        timeout=check_interval,
                    )
                    break
                except TimeoutError:
                    continue
        finally:
            self._running = False
            logger.info("Cron runner daemon stopped")

    def stop(self) -> None:
        """Stop the daemon."""
        self._running = False
        self._stop_event.set()
