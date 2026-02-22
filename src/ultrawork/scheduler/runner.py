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
    ThreadTarget,
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

    def _match_cron_expression(self, expression: str, now: datetime, last_run: datetime) -> bool:
        """Basic cron expression matcher.

        Supports: minute hour day_of_month month day_of_week
        Handles ranges (1-5), comma-separated values (9,13,17), and wildcards (*).

        Note: day_of_week uses standard cron convention: 0=Sunday, 1-6=Mon-Sat.
        Python's weekday() returns 0=Monday, 6=Sunday, so we convert.

        Args:
            expression: Cron expression (e.g., "0 9,13,17 * * 1-5")
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
            # Handle comma-separated values (may contain ranges)
            if "," in field:
                for part in field.split(","):
                    part = part.strip()
                    if "-" in part:
                        start, end = map(int, part.split("-"))
                        if start <= value <= end:
                            return True
                    elif value == int(part):
                        return True
                return False
            # Handle ranges like "1-5"
            if "-" in field:
                start, end = map(int, field.split("-"))
                return start <= value <= end
            return value == int(field)

        if not _matches(minute, now.minute):
            return False
        if not _matches(hour, now.hour):
            return False
        if not _matches(dom, now.day):
            return False
        if not _matches(month, now.month):
            return False

        # Convert Python weekday (0=Mon, 6=Sun) to cron weekday (0=Sun, 1-6=Mon-Sat)
        cron_dow = (now.weekday() + 1) % 7
        if not _matches(dow, cron_dow):
            return False

        # Ensure we haven't already run this minute
        return last_run.replace(second=0, microsecond=0) < now.replace(second=0, microsecond=0)

    def _get_slack_client(self):
        """Create a Slack WebClient if token is available."""
        if not self.slack_token:
            return None

        from slack_sdk import WebClient

        headers = {}
        if self.slack_token.startswith("xoxc-") and self.slack_cookie:
            headers["Cookie"] = f"d={self.slack_cookie}"
        return WebClient(token=self.slack_token, headers=headers)

    def _discover_threads_from_channels(
        self,
        client,
        channel_ids: list[str],
    ) -> list[ThreadTarget]:
        """Discover recent active threads from channel_targets.

        When thread_targets is empty, fetches channel history and extracts
        threads (messages with replies) to monitor.

        Args:
            client: Slack WebClient
            channel_ids: Channel IDs to search for threads

        Returns:
            List of discovered ThreadTarget objects
        """
        discovered = []

        for channel_id in channel_ids:
            try:
                result = client.conversations_history(
                    channel=channel_id,
                    limit=50,
                )
                messages = result.get("messages", [])

                for msg in messages:
                    reply_count = msg.get("reply_count", 0)
                    if reply_count == 0:
                        continue

                    thread_ts = msg.get("thread_ts") or msg.get("ts")
                    if not thread_ts:
                        continue

                    discovered.append(
                        ThreadTarget(
                            channel_id=channel_id,
                            thread_ts=thread_ts,
                            description=msg.get("text", "")[:80],
                        )
                    )

            except Exception as e:
                logger.error(f"Failed to discover threads in {channel_id}: {e}")

        return discovered

    def _execute_check_thread_reactions(self, job: CronJob) -> CronExecutionLog:
        """Execute a thread reaction checking job.

        In addition to the original notification behavior, this now also
        triggers automatic approval/rejection when approval-related reactions
        are detected on threads associated with pending tasks.
        """
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

        # Determine thread list: use thread_targets if available,
        # otherwise discover from channel_targets
        thread_targets = list(job.thread_targets)
        if not thread_targets and job.channel_targets:
            thread_targets = self._discover_threads_from_channels(
                client, job.channel_targets
            )

        # Initialize reaction approval handler for auto-processing
        reaction_handler = None
        if self.slack_token:
            try:
                from ultrawork.slack.reaction_approval import ReactionApprovalHandler

                reaction_handler = ReactionApprovalHandler(
                    slack_token=self.slack_token,
                    data_dir=self.data_dir,
                    slack_cookie=self.slack_cookie,
                )
            except Exception as e:
                logger.debug(f"Reaction approval handler not available: {e}")

        findings = []
        auto_approvals = []
        for target in thread_targets:
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

                # Check for reactions on all messages (not just parent)
                parent = messages[0] if messages else {}
                all_reactions = parent.get("reactions", [])
                approval_detected = False
                rejection_detected = False
                reactor_user = ""

                for msg in messages:
                    for reaction in msg.get("reactions", []):
                        name = reaction.get("name", "")
                        users = reaction.get("users", [])
                        if name in ("thumbsup", "+1", "white_check_mark", "heavy_check_mark"):
                            log.new_reactions_found += 1
                            if not approval_detected and users:
                                approval_detected = True
                                reactor_user = users[0]
                        elif name in ("thumbsdown", "-1", "x", "heavy_multiplication_x"):
                            if not rejection_detected and users:
                                rejection_detected = True
                                reactor_user = users[0]

                # Try auto-approval if reaction handler available
                if reaction_handler and (approval_detected or rejection_detected):
                    auto_approvals.append({
                        "channel_id": target.channel_id,
                        "thread_ts": target.thread_ts,
                        "action": "approved" if approval_detected else "rejected",
                        "user_id": reactor_user,
                    })

                if new_replies:
                    reply_summaries = []
                    for reply in new_replies[:5]:  # Max 5 for summary
                        text = reply.get("text", "").replace("\n", " ")[:30]
                        user = reply.get("user", "unknown")
                        reply_summaries.append(f"<@{user}>: {text}")

                    findings.append(
                        {
                            "thread": f"{target.channel_id}/{target.thread_ts}",
                            "channel_name": target.channel_name,
                            "description": target.description,
                            "new_replies": len(new_replies),
                            "reply_summaries": reply_summaries,
                            "reactions": [r.get("name", "") for r in all_reactions],
                        }
                    )

            except Exception as e:
                logger.error(f"Failed to check thread {target.channel_id}/{target.thread_ts}: {e}")
                log.error = str(e)

        # Process auto-approvals via reaction handler
        if reaction_handler and auto_approvals:
            try:
                import asyncio

                results = asyncio.get_event_loop().run_until_complete(
                    reaction_handler.check_and_process()
                )
                processed = [r for r in results if r.action in ("approved", "rejected")]
                if processed:
                    logger.info(
                        f"Cron auto-approval: {len(processed)} tasks processed via reactions"
                    )
            except Exception as e:
                logger.error(f"Auto-approval processing failed: {e}")

        # Send DM if there are findings and notification is configured
        if findings and job.notify_channel_id:
            from ultrawork.slack.block_kit import BlockKitBuilder, send_block_message

            message = BlockKitBuilder.build_thread_check_dm(job.name, findings)
            log.dm_content = message.get("text", "")
            result = send_block_message(client, job.notify_channel_id, message)
            if result:
                log.dm_sent = True
            else:
                # Fallback to plain text
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

                new_matches = [m for m in matches if float(m.get("ts", "0")) > float(last_run_ts)]

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
            from ultrawork.slack.block_kit import BlockKitBuilder, send_block_message

            message = BlockKitBuilder.build_mention_scan_dm(job.name, findings)
            log.dm_content = message.get("text", "")
            result = send_block_message(client, job.notify_channel_id, message)
            if result:
                log.dm_sent = True
            else:
                # Fallback to plain text
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
                from ultrawork.slack.block_kit import BlockKitBuilder, send_block_message

                message = BlockKitBuilder.build_pending_tasks_dm(job.name, pending)
                log.dm_content = message.get("text", "")
                result = send_block_message(client, job.notify_channel_id, message)
                if result:
                    log.dm_sent = True
                else:
                    # Fallback to plain text
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
            f"Cron job {job.job_id} completed: success={log.success}, duration={log.duration_ms}ms"
        )
        return log

    def _format_thread_check_dm(self, job: CronJob, findings: list[dict]) -> str:
        """Format a DM message for thread check results."""
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
        lines = [f":bar_chart: *{job.name}* - {now_str}\n"]

        for f in findings:
            desc = f.get("description", "")
            if len(desc) > 40:
                desc = desc[:40] + "..."
            ch_name = f.get("channel_name", "")
            new_replies = f.get("new_replies", 0)
            reactions = f.get("reactions", [])
            emoji_str = " ".join(f":{r}:" for r in reactions) if reactions else ""

            lines.append("━━━━━━━━━━━━━━━━━━━━")
            header = f":pushpin: *#{ch_name}*" if ch_name else f":pushpin: `{f['thread']}`"
            header += f" | {new_replies} new"
            if emoji_str:
                header += f" | {emoji_str}"
            lines.append(header)

            if desc:
                lines.append(f"> {desc}")

            if new_replies > 0:
                lines.append("")
                for summary in f.get("reply_summaries", []):
                    lines.append(f"• {summary}")

        lines.append("━━━━━━━━━━━━━━━━━━━━")
        lines.append("")
        lines.append(":bulb: 처리: 스레드 링크로 답장 | 무시: 건너뜀")
        return "\n".join(lines)

    def _format_mention_scan_dm(self, job: CronJob, findings: list[dict]) -> str:
        """Format a DM message for mention scan results."""
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
        lines = [f":bell: *{job.name}* - {now_str}"]
        lines.append(f"미처리 멘션 {len(findings)}건\n")

        for f in findings[:10]:
            text = f.get("text", "").replace("\n", " ")
            if len(text) > 40:
                text = text[:40] + "..."
            lines.append("━━━━━━━━━━━━━━━━━━━━")
            lines.append(f":speech_balloon: *#{f['channel']}* | <@{f['user']}>")
            lines.append(f"> {text}")

        if len(findings) > 10:
            lines.append(f"\n...외 {len(findings) - 10}건")

        lines.append("━━━━━━━━━━━━━━━━━━━━")
        lines.append("")
        lines.append(":bulb: 'process [번호]'로 처리 | 'skip'으로 전체 건너뜀")
        return "\n".join(lines)

    def _format_pending_tasks_dm(self, job: CronJob, pending: list[dict]) -> str:
        """Format a DM message for pending tasks summary."""
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
        lines = [f":clipboard: *{job.name}* - {now_str}"]
        lines.append(f"대기 중인 승인 {len(pending)}건\n")

        for p in pending:
            title = p.get("title", "")
            if len(title) > 40:
                title = title[:40] + "..."
            lines.append("━━━━━━━━━━━━━━━━━━━━")
            lines.append(f":hourglass_flowing_sand: *{p['task_id']}* | {p['stage']}")
            lines.append(f"> {title}")

        lines.append("━━━━━━━━━━━━━━━━━━━━")
        lines.append("")
        lines.append(":bulb: `/approve <task_id>` 또는 `/reject <task_id>`로 처리")
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
                    self.manager.record_execution(job.job_id, success=False, error=str(e))

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
