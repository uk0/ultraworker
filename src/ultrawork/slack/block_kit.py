"""Slack Block Kit message builder for Ultrawork.

Provides builders for constructing rich, interactive Slack messages
using the Block Kit framework. All workflow notifications, approval
requests, and status updates use these builders.

Usage:
    from ultrawork.slack.block_kit import BlockKitBuilder

    builder = BlockKitBuilder()
    msg = builder.build_approval_request(
        task_id="TASK-2026-0129-001",
        title="Implement API Caching",
        stage="todo",
        ...
    )
    # msg = {"blocks": [...], "text": "fallback text"}
"""

from __future__ import annotations

from datetime import datetime
from typing import Any


# Action ID prefixes (kept for InteractionHandler backward compatibility)
ACTION_PREFIX = "uw"
ACTION_APPROVE = f"{ACTION_PREFIX}_approve"
ACTION_REJECT = f"{ACTION_PREFIX}_reject"
ACTION_SKIP = f"{ACTION_PREFIX}_skip"


def _section(text: str, accessory: dict | None = None) -> dict:
    """Create a section block with mrkdwn text."""
    block: dict[str, Any] = {
        "type": "section",
        "text": {"type": "mrkdwn", "text": text},
    }
    if accessory:
        block["accessory"] = accessory
    return block


def _header(text: str) -> dict:
    """Create a header block."""
    return {
        "type": "header",
        "text": {"type": "plain_text", "text": text, "emoji": True},
    }


def _divider() -> dict:
    """Create a divider block."""
    return {"type": "divider"}


def _context(*texts: str) -> dict:
    """Create a context block with mrkdwn elements."""
    return {
        "type": "context",
        "elements": [{"type": "mrkdwn", "text": t} for t in texts],
    }


def _fields(field_pairs: list[tuple[str, str]]) -> dict:
    """Create a section block with fields (label-value pairs)."""
    return {
        "type": "section",
        "fields": [
            {"type": "mrkdwn", "text": f"*{label}*\n{value}"}
            for label, value in field_pairs
        ],
    }



class BlockKitBuilder:
    """Builds Slack Block Kit messages for all Ultrawork workflow stages."""

    # --- Approval Request Messages ---

    @staticmethod
    def build_todo_approval(
        task_id: str,
        title: str,
        workflow_type: str,
        todo_items: list[str],
        exploration_id: str = "",
        estimated_effort: str = "",
        decisions: list[str] | None = None,
        channel_id: str = "",
        thread_ts: str = "",
    ) -> dict[str, Any]:
        """Build a TODO approval request message with interactive buttons."""
        stage_count = "4" if workflow_type == "full" else "2"
        type_label = f"Full Workflow ({stage_count}-stage)" if workflow_type == "full" else f"Simple Workflow ({stage_count}-stage)"

        blocks: list[dict] = [
            _header(":clipboard:  TODO List Review Request"),
            _fields([
                ("Task", title),
                ("Type", type_label),
                ("Task ID", f"`{task_id}`"),
                ("Based on", f"`{exploration_id}`" if exploration_id else "N/A"),
            ]),
            _divider(),
            _section(":memo: *TODO Items*"),
        ]

        # Build numbered list of todos
        todo_text = "\n".join(f"{i+1}. {item}" for i, item in enumerate(todo_items))
        blocks.append(_section(todo_text))

        # Decisions section
        if decisions:
            blocks.append(_divider())
            blocks.append(_section(":bulb: *Already Decided*"))
            decision_text = "\n".join(f"• {d}" for d in decisions)
            blocks.append(_section(decision_text))

        # Effort estimate
        if estimated_effort:
            blocks.append(_divider())
            blocks.append(_section(f":bar_chart: *Estimated Effort*: {estimated_effort}"))

        # Reaction-based approval guide (no Interactivity URL needed)
        blocks.append(_divider())
        blocks.append(
            _section(
                ":point_down: *이 메시지에 리액션으로 응답해주세요*\n"
                ":+1: = 승인  |  :-1: = 수정 요청"
            )
        )
        blocks.append(_context(f"_Task ID: {task_id} | Stage 1/{stage_count}_"))

        return {
            "blocks": blocks,
            "text": f":clipboard: TODO Review Request - {title} ({task_id})",
        }

    @staticmethod
    def build_spec_approval(
        task_id: str,
        title: str,
        file_changes: list[str] | None = None,
        test_plan: str = "",
        spec_file: str = "",
        channel_id: str = "",
        thread_ts: str = "",
    ) -> dict[str, Any]:
        """Build a Tech Spec approval request message."""
        blocks: list[dict] = [
            _header(":page_facing_up:  Tech Spec Review Request"),
            _fields([
                ("Task", title),
                ("Task ID", f"`{task_id}`"),
                ("Spec File", f"`{spec_file}`" if spec_file else "N/A"),
                ("Stage", "Tech Spec (2/4)"),
            ]),
            _divider(),
        ]

        if file_changes:
            blocks.append(_section(":file_folder: *Key Changes*"))
            changes_text = "\n".join(f"• {c}" for c in file_changes)
            blocks.append(_section(changes_text))

        if test_plan:
            blocks.append(_divider())
            blocks.append(_section(f":test_tube: *Test Plan*\n{test_plan}"))

        # Reaction-based approval guide
        blocks.append(_divider())
        blocks.append(
            _section(
                ":point_down: *이 메시지에 리액션으로 응답해주세요*\n"
                ":+1: = 승인  |  :-1: = 수정 요청"
            )
        )
        blocks.append(_context(f"_Spec: {spec_file} | Task: {task_id}_"))

        return {
            "blocks": blocks,
            "text": f":page_facing_up: Tech Spec Review - {title} ({task_id})",
        }

    @staticmethod
    def build_final_report_approval(
        task_id: str,
        title: str,
        summary: str = "",
        results: list[str] | None = None,
        changes_summary: str = "",
        verification: str = "",
        stage_num: int = 4,
        total_stages: int = 4,
        channel_id: str = "",
        thread_ts: str = "",
    ) -> dict[str, Any]:
        """Build a Final Report approval request message."""
        blocks: list[dict] = [
            _header(":clipboard:  Final Report"),
            _fields([
                ("Task", title),
                ("Task ID", f"`{task_id}`"),
                ("Stage", f"Final Report ({stage_num}/{total_stages})"),
            ]),
        ]

        if summary:
            blocks.append(_divider())
            blocks.append(_section(f":page_with_curl: *Summary*\n{summary}"))

        if results:
            blocks.append(_divider())
            blocks.append(_section(":trophy: *Key Results*"))
            results_text = "\n".join(f"• {r}" for r in results)
            blocks.append(_section(results_text))

        if changes_summary:
            blocks.append(_divider())
            blocks.append(_section(f":hammer_and_wrench: *Changes*\n{changes_summary}"))

        if verification:
            blocks.append(_divider())
            blocks.append(_section(f":white_check_mark: *Verification*\n{verification}"))

        # Reaction-based approval guide
        blocks.append(_divider())
        blocks.append(
            _section(
                ":point_down: *이 메시지에 리액션으로 응답해주세요*\n"
                ":+1: = 최종 승인  |  :-1: = 수정 요청"
            )
        )
        blocks.append(_context(f"_This is the final approval stage | Task: {task_id}_"))

        return {
            "blocks": blocks,
            "text": f":clipboard: Final Report - {title} ({task_id})",
        }

    # --- Notification Messages ---

    @staticmethod
    def build_approval_notification(
        task_id: str,
        stage: str,
        user_id: str,
        next_stage: str = "",
        is_complete: bool = False,
    ) -> dict[str, Any]:
        """Build an approval notification message."""
        if is_complete or next_stage == "done":
            blocks: list[dict] = [
                _header(":tada:  Task Complete!"),
                _fields([
                    ("Task", f"`{task_id}`"),
                    ("Approved Stage", stage),
                    ("Approved By", f"<@{user_id}> (reaction)"),
                ]),
                _divider(),
                _section(":confetti_ball: All stages have been approved! Great work!"),
                _context(f"_Completed at {datetime.now().strftime('%Y-%m-%d %H:%M')}_"),
            ]
            return {
                "blocks": blocks,
                "text": f":tada: Task Complete - {task_id}",
            }

        blocks = [
            _header(":white_check_mark:  Auto-Approved"),
            _fields([
                ("Task", f"`{task_id}`"),
                ("Approved Stage", stage),
                ("Approved By", f"<@{user_id}> (reaction)"),
                ("Next Stage", next_stage),
            ]),
            _divider(),
            _section(":arrow_right: Proceeding to the next stage automatically."),
            _context(f"_Approved at {datetime.now().strftime('%Y-%m-%d %H:%M')}_"),
        ]
        return {
            "blocks": blocks,
            "text": f":white_check_mark: Auto-Approved - {task_id} ({stage})",
        }

    @staticmethod
    def build_rejection_notification(
        task_id: str,
        stage: str,
        user_id: str,
        reason: str = "",
        revision_count: int = 0,
    ) -> dict[str, Any]:
        """Build a rejection notification message."""
        blocks: list[dict] = [
            _header(":x:  Revision Requested"),
            _fields([
                ("Task", f"`{task_id}`"),
                ("Rejected Stage", stage),
                ("Rejected By", f"<@{user_id}> (reaction)"),
                ("Revision Count", str(revision_count) if revision_count else "1"),
            ]),
        ]

        if reason:
            blocks.append(_divider())
            blocks.append(_section(f":speech_balloon: *Reason*\n> {reason}"))

        blocks.append(_divider())
        blocks.append(_section(":pencil2: Please incorporate the feedback and resubmit."))
        blocks.append(_context(f"_Task: {task_id} | Revision limit: 3_"))

        return {
            "blocks": blocks,
            "text": f":x: Revision Requested - {task_id} ({stage})",
        }

    @staticmethod
    def build_completion_notification(
        task_id: str,
        title: str,
        duration: str = "",
        approval_count: int = 0,
        total_stages: int = 4,
    ) -> dict[str, Any]:
        """Build a task completion notification."""
        blocks: list[dict] = [
            _header(":checkered_flag:  Task Complete"),
            _section(f"*{task_id}* - {title}"),
            _divider(),
            _section(":white_check_mark: All stages approved!"),
        ]

        fields = []
        if duration:
            fields.append(("Duration", duration))
        if approval_count:
            fields.append(("Approvals", f"{approval_count}/{total_stages}"))
        if fields:
            blocks.append(_fields(fields))

        blocks.append(_divider())
        blocks.append(_context(f"_Completed at {datetime.now().strftime('%Y-%m-%d %H:%M')} | Thank you! :pray:_"))

        return {
            "blocks": blocks,
            "text": f":checkered_flag: Task Complete - {task_id} - {title}",
        }

    # --- Cron Job DM Messages ---

    @staticmethod
    def build_thread_check_dm(
        job_name: str,
        findings: list[dict],
    ) -> dict[str, Any]:
        """Build a thread check DM with interactive elements."""
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M")

        blocks: list[dict] = [
            _header(f":bar_chart:  {job_name}"),
            _context(f"*{now_str}* | Thread reaction check results"),
            _divider(),
        ]

        for f in findings:
            desc = f.get("description", "")
            if len(desc) > 60:
                desc = desc[:60] + "..."
            ch_name = f.get("channel_name", "")
            new_replies = f.get("new_replies", 0)
            reactions = f.get("reactions", [])
            emoji_str = " ".join(f":{r}:" for r in reactions) if reactions else ""

            channel_label = f"*#{ch_name}*" if ch_name else f"`{f['thread']}`"
            info_parts = [f"{new_replies} new replies"]
            if emoji_str:
                info_parts.append(emoji_str)

            blocks.append(
                _section(
                    f":pushpin: {channel_label} | {' | '.join(info_parts)}",
                )
            )

            if desc:
                blocks.append(_context(f"> {desc}"))

            if new_replies > 0:
                summaries = f.get("reply_summaries", [])
                if summaries:
                    summary_text = "\n".join(f"• {s}" for s in summaries[:5])
                    blocks.append(_section(summary_text))

            blocks.append(_divider())

        blocks.append(_context(":bulb: React on the thread to approve/reject, or reply for more info."))

        return {
            "blocks": blocks,
            "text": f":bar_chart: {job_name} - {now_str}",
        }

    @staticmethod
    def build_mention_scan_dm(
        job_name: str,
        findings: list[dict],
    ) -> dict[str, Any]:
        """Build a mention scan DM with actionable items."""
        blocks: list[dict] = [
            _header(f":bell:  {job_name}"),
            _context(f"Unhandled Mentions Found: *{len(findings)}*"),
            _divider(),
        ]

        for i, f in enumerate(findings[:10]):
            text_preview = f.get("text", "")[:150]
            channel = f.get("channel", "unknown")
            user = f.get("user", "")

            blocks.append(
                _section(f"*#{channel}* - <@{user}>\n> {text_preview}")
            )

        if len(findings) > 10:
            blocks.append(_context(f"_...and {len(findings) - 10} more_"))

        blocks.append(_divider())
        blocks.append(_context("_처리할 멘션의 스레드 링크를 답장하거나, 무시하려면 \"skip\"을 입력하세요._"))

        return {
            "blocks": blocks,
            "text": f":bell: {job_name} - {len(findings)} unhandled mentions",
        }

    @staticmethod
    def build_pending_tasks_dm(
        job_name: str,
        pending: list[dict],
    ) -> dict[str, Any]:
        """Build a pending tasks DM with approve/reject buttons per task."""
        blocks: list[dict] = [
            _header(f":inbox_tray:  {job_name}"),
            _context(f"Pending Approvals: *{len(pending)}*"),
            _divider(),
        ]

        for p in pending:
            task_id = p.get("task_id", "")
            title = p.get("title", "")
            stage = p.get("stage", "")

            blocks.append(
                _section(f"*{task_id}* - {title}\nStage: `{stage}`")
            )

        blocks.append(_divider())
        blocks.append(_context("_해당 승인 요청 메시지에 :+1: (승인) 또는 :-1: (거부) 리액션을 달아주세요._"))

        return {
            "blocks": blocks,
            "text": f":inbox_tray: {job_name} - {len(pending)} pending approvals",
        }

    # --- Progress Update Messages ---

    @staticmethod
    def build_progress_update(
        task_id: str,
        title: str,
        current_stage: str,
        stages: dict[str, str],
        message: str = "",
    ) -> dict[str, Any]:
        """Build a workflow progress update message.

        Args:
            stages: dict of stage_name -> status (e.g. {"todo": "approved", "tech_spec": "pending"})
        """
        stage_emoji = {
            "approved": ":white_check_mark:",
            "rejected": ":x:",
            "in_progress": ":hourglass_flowing_sand:",
            "pending": ":white_circle:",
            "completed": ":white_check_mark:",
            "skipped": ":fast_forward:",
        }

        stage_labels = {
            "todo": "TODO",
            "tech_spec": "Tech Spec",
            "code_work": "Code Work",
            "final_report": "Final Report",
        }

        blocks: list[dict] = [
            _section(f":gear: *{task_id}* - {title}"),
        ]

        if message:
            blocks.append(_section(message))

        blocks.append(_divider())

        # Progress bar
        progress_lines = []
        for stage_name, status in stages.items():
            emoji = stage_emoji.get(status, ":white_circle:")
            label = stage_labels.get(stage_name, stage_name)
            current_marker = " :point_left:" if stage_name == current_stage else ""
            progress_lines.append(f"{emoji} {label}{current_marker}")

        blocks.append(_section("\n".join(progress_lines)))
        blocks.append(_context(f"_Updated at {datetime.now().strftime('%H:%M')}_"))

        return {
            "blocks": blocks,
            "text": f":gear: Progress - {task_id} ({current_stage})",
        }

    # --- Workflow Start Acknowledgment ---

    @staticmethod
    def build_workflow_start(
        is_complex: bool = True,
    ) -> dict[str, Any]:
        """Build an acknowledgment message when starting workflow processing."""
        if is_complex:
            blocks: list[dict] = [
                _section(":mag: *Got it!*"),
                _divider(),
                _section(
                    "This appears to be a complex task, so I'll proceed step by step:\n"
                    "1\ufe0f\u20e3 Analyzing context...\n"
                    "2\ufe0f\u20e3 TODO creation pending\n"
                    "3\ufe0f\u20e3 Work proceeds after approval"
                ),
                _context("_I'll share detailed analysis results shortly._"),
            ]
        else:
            blocks = [
                _section(":wave: *Got it!*"),
                _context("_Processing your request..._"),
            ]

        return {
            "blocks": blocks,
            "text": "Got it! Processing your request...",
        }

    @staticmethod
    def build_analysis_complete(
        task_id: str = "",
    ) -> dict[str, Any]:
        """Build message for when analysis/TODO creation is complete."""
        blocks: list[dict] = [
            _section(":clipboard: *Analysis complete!*"),
            _divider(),
            _section("Please review and approve the TODO list above."),
        ]

        blocks.append(_context("_위의 TODO 메시지에 :+1: (승인) 또는 :-1: (수정 요청) 리액션을 달아주세요._"))

        return {
            "blocks": blocks,
            "text": ":clipboard: Analysis complete! Please review the TODO list.",
        }


def send_block_message(
    client,
    channel: str,
    message: dict[str, Any],
    thread_ts: str = "",
) -> dict | None:
    """Send a Block Kit message using the Slack SDK client.

    Args:
        client: slack_sdk.WebClient instance
        channel: Channel ID
        message: Dict with 'blocks' and 'text' keys
        thread_ts: Thread timestamp for replies

    Returns:
        API response dict or None on failure
    """
    kwargs: dict[str, Any] = {
        "channel": channel,
        "blocks": message["blocks"],
        "text": message.get("text", ""),
    }
    if thread_ts:
        kwargs["thread_ts"] = thread_ts

    try:
        result = client.chat_postMessage(**kwargs)
        return result
    except Exception:
        return None
