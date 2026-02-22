"""Slack SDK-based polling daemon for real-time mention tracking.

This module provides a standalone polling daemon that uses the Slack SDK
directly, allowing it to run as a background process independent of
Claude Code sessions.

Features:
- Real-time mention detection with reaction indicators
- Session-based agentic response with complexity classification
- Output logging for all executions
- Human Framework for natural responses

Usage:
    # As a module
    python -m ultrawork.slack.sdk_poller

    # Or via CLI
    ultrawork daemon:start --agentic
"""

import asyncio
import logging
import os
import shutil
import signal
import subprocess
import sys
import threading
import time
from datetime import datetime
from pathlib import Path

import yaml
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError

from ultrawork.agent.session_manager import SessionManager
from ultrawork.config import get_config
from ultrawork.events.interaction_logger import InteractionLogger
from ultrawork.models.agent import AgentRole
from ultrawork.slack.downloader import SlackFileDownloader
from ultrawork.slack.reaction_approval import ReactionApprovalHandler
from ultrawork.slack.state import PollingStateManager

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("data/logs/sdk_poller.log"),
    ],
)
logger = logging.getLogger("sdk_poller")

# Reaction emojis
EMOJI_PROCESSING = "eyes"  # 👀
EMOJI_DONE = "white_check_mark"  # ✅
EMOJI_ERROR = "x"  # ❌

# Human Framework prompt for natural responses
HUMAN_RESPONSE_GUIDE = """## Response Style Guide

Follow these rules to write natural responses:

### Avoid
- Overusing formal or bureaucratic phrasing
- Repetitive sentence structures (more than 3 times)
- Overly complex or indirect language

### Recommended Style
- Be polite and professional
- Mix short and long sentences
- Include specific examples or context
- Be honest if unsure: "I'm not certain about that"
- Use emojis sparingly (not excessive)

### Examples
Bad: "I shall proceed to utilize the aforementioned information to provide you with a response."
Good: "Based on what I found, here's my answer."
"""


def _get_language_prompt() -> str:
    """Get language instruction prompt based on configured language."""
    from ultrawork.config import SUPPORTED_LANGUAGES

    try:
        config = get_config()
        lang_code = config.language.default
    except Exception:
        lang_code = "en"

    if lang_code == "en":
        return ""

    lang_name = SUPPORTED_LANGUAGES.get(lang_code, lang_code)
    return (
        f"\n## Language Requirement\n\n"
        f"**CRITICAL**: You MUST write ALL responses, thinking, and Slack messages in **{lang_name}** (`{lang_code}`).\n"
        f"This includes:\n"
        f"- All Slack messages and thread replies\n"
        f"- All analysis and reasoning output\n"
        f"- All TODO items, spec content, report content\n"
        f"- All approval request messages\n"
        f"- All error messages and status updates\n"
        f"- All exploration summaries\n\n"
        f"Technical terms, code identifiers, file paths, and command names should remain in their original form.\n"
    )


# Complexity keywords for classification
COMPLEX_KEYWORDS = [
    "implement",
    "write",
    "create",
    "analyze",
    "refactor",
    "bug",
    "error",
    "fix",
    "code",
    "develop",
    "design",
    "architecture",
    "test",
    "deploy",
    "migration",
    "PR",
    "pull request",
    "commit",
    "branch",
    "merge",
    "review",
]


class SlackSDKPoller:
    """Polls Slack for mentions using the Slack SDK with skill-based response."""

    def __init__(
        self,
        token: str,
        bot_user_id: str = "",
        trigger_pattern: str = "",
        data_dir: Path | None = None,
        poll_interval: int = 60,
        channels: list[str] | None = None,
        cookie: str | None = None,
        agentic_mode: bool = False,
        only_new_mentions: bool = True,
    ):
        """Initialize the SDK poller.

        Args:
            token: Slack API token (xoxc-*, xoxb-*, or xoxp-*)
            bot_user_id: User ID to monitor mentions for (optional if trigger_pattern set)
            trigger_pattern: Custom keyword to trigger responses (optional if bot_user_id set)
            data_dir: Data directory for state persistence
            poll_interval: Seconds between polls
            channels: List of channel IDs to monitor (None = all DMs)
            cookie: Slack cookie (required for xoxc-* tokens)
            agentic_mode: If True, use claude -p skill for intelligent responses
            only_new_mentions: If True, skip backlog and handle only mentions after daemon start
        """
        if not bot_user_id and not trigger_pattern:
            raise ValueError("Either bot_user_id or trigger_pattern must be set")

        # For xoxc tokens, we need to pass the cookie as a header
        headers = {}
        if token.startswith("xoxc-") and cookie:
            headers["Cookie"] = f"d={cookie}"

        self.client = WebClient(token=token, headers=headers)
        self.bot_user_id = bot_user_id
        self.trigger_pattern = trigger_pattern
        self.data_dir = Path(data_dir) if data_dir else Path("data")
        self.poll_interval = poll_interval
        self.channels = channels or []
        self.agentic_mode = agentic_mode
        self.only_new_mentions = only_new_mentions

        # Initialize state manager
        self.state_manager = PollingStateManager(self.data_dir)

        # Initialize session manager for agent supervision
        self.session_manager = SessionManager(self.data_dir)

        # Initialize interaction logger for real-time dashboard
        self.interaction_logger = InteractionLogger(self.data_dir)

        # Daemon control
        self._running = False
        self._stop_event = asyncio.Event()
        self._startup_ts: str | None = None

        # Ensure directories exist
        (self.data_dir / "logs").mkdir(parents=True, exist_ok=True)
        (self.data_dir / "mentions" / "pending").mkdir(parents=True, exist_ok=True)
        (self.data_dir / "mentions" / "completed").mkdir(parents=True, exist_ok=True)
        (self.data_dir / "mentions" / "failed").mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _format_slack_ts(value: float) -> str:
        """Format a float timestamp in Slack's expected string format."""
        return f"{value:.6f}"

    @staticmethod
    def _ts_to_float(ts: str | None) -> float:
        """Convert a Slack timestamp string to float."""
        if not ts:
            return 0.0
        try:
            return float(ts)
        except (TypeError, ValueError):
            return 0.0

    def _prime_new_only_baseline(self) -> None:
        """Initialize last_checked_ts so we only process new mentions."""
        if not self.only_new_mentions:
            return

        now_ts = self._format_slack_ts(time.time())
        state = self.state_manager.load_state()

        # If state is somehow ahead, honor it to avoid moving backwards.
        if self._ts_to_float(state.last_checked_ts) > self._ts_to_float(now_ts):
            now_ts = state.last_checked_ts

        self._startup_ts = now_ts

        # Skip backlog by starting from now.
        if self._ts_to_float(state.last_checked_ts) < self._ts_to_float(now_ts):
            state.last_checked_ts = now_ts
            self.state_manager.save_state(state)
            logger.info(f"New-only mode: skipping mentions before {state.last_checked_ts}")

    def _get_conversations_to_monitor(self) -> list[dict]:
        """Get list of conversations to monitor."""
        if self.channels:
            return [{"id": ch, "type": "channel"} for ch in self.channels]

        # Load channels from registry file
        conversations = []
        registry_path = self.data_dir / "registry" / "channels.yaml"

        if registry_path.exists():
            try:
                with open(registry_path, encoding="utf-8") as f:
                    registry = yaml.safe_load(f) or {}

                channels_data = registry.get("channels", {})
                for key, ch in channels_data.items():
                    # Only include channels with valid IDs (skip those with _needs_id)
                    ch_id = ch.get("id") if isinstance(ch, dict) else None
                    if ch_id and ch_id.startswith("C"):
                        conversations.append(
                            {
                                "id": ch_id,
                                "type": "channel",
                                "name": ch.get("name", key),
                            }
                        )

                logger.info(f"Loaded {len(conversations)} channels from registry")
            except Exception as e:
                logger.error(f"Failed to load channel registry: {e}")

        # Also get DMs via API
        try:
            result = self.client.conversations_list(types="im", limit=100)
            dm_count = 0
            for ch in result.get("channels", []):
                conversations.append(
                    {
                        "id": ch["id"],
                        "type": "dm",
                    }
                )
                dm_count += 1
            logger.info(f"Found {dm_count} DMs, total: {len(conversations)} conversations")
        except SlackApiError as e:
            logger.error(f"Failed to list DMs: {e}")

        return conversations

    def _get_channel_history(
        self,
        channel_id: str,
        oldest: str | None = None,
        limit: int = 50,
    ) -> list[dict]:
        """Get recent messages from a channel."""
        try:
            kwargs = {"channel": channel_id, "limit": limit}
            if oldest:
                kwargs["oldest"] = oldest

            result = self.client.conversations_history(**kwargs)
            return result.get("messages", [])
        except SlackApiError as e:
            logger.error(f"Failed to get history for {channel_id}: {e}")
            return []

    def _get_thread_replies(
        self,
        channel_id: str,
        thread_ts: str,
        oldest: str | None = None,
    ) -> list[dict]:
        """Get replies in a thread."""
        try:
            kwargs = {"channel": channel_id, "ts": thread_ts, "limit": 100}
            if oldest:
                kwargs["oldest"] = oldest

            result = self.client.conversations_replies(**kwargs)
            messages = result.get("messages", [])
            # Skip the first message (parent) - we only want replies
            return messages[1:] if len(messages) > 1 else []
        except SlackApiError as e:
            logger.debug(f"Failed to get thread replies for {thread_ts}: {e}")
            return []

    def _search_mentions(self, oldest_ts: str | None = None) -> list[dict]:
        """Search for recent mentions of the bot user.

        Args:
            oldest_ts: Only return mentions newer than this timestamp
        """
        try:
            queries: list[str] = []
            if self.bot_user_id:
                queries.append(f"<@{self.bot_user_id}>")
            if self.trigger_pattern:
                queries.append(self.trigger_pattern)

            if not queries:
                return []

            matches_by_ts = {}
            for query in queries:
                result = self.client.search_messages(
                    query=query,
                    sort="timestamp",
                    sort_dir="desc",
                    count=50,
                )

                for message in result.get("messages", {}).get("matches", []):
                    message_ts = message.get("ts", "")
                    if not message_ts:
                        continue

                    existing = matches_by_ts.get(message_ts)
                    if existing is None or self._ts_to_float(message.get("ts")) > self._ts_to_float(
                        existing.get("ts", "")
                    ):
                        matches_by_ts[message_ts] = message

            matches = list(matches_by_ts.values())

            # Filter by timestamp if oldest_ts is provided
            if oldest_ts:
                matches = [
                    m
                    for m in matches
                    if self._ts_to_float(m.get("ts", "0")) > self._ts_to_float(oldest_ts)
                ]

            matches = [m for m in matches if self._is_mention_to_me(m)]
            matches.sort(
                key=lambda message: self._ts_to_float(message.get("ts", "0")), reverse=True
            )

            logger.info(f"Found {len(matches)} new mentions via search")
            return matches
        except SlackApiError as e:
            logger.error(f"Failed to search mentions: {e}")
            return []

    def _add_reaction(self, channel_id: str, timestamp: str, emoji: str) -> bool:
        """Add a reaction to a message."""
        try:
            self.client.reactions_add(
                channel=channel_id,
                timestamp=timestamp,
                name=emoji,
            )
            logger.debug(f"Added :{emoji}: to {timestamp}")
            return True
        except SlackApiError as e:
            # Ignore "already_reacted" errors
            if "already_reacted" not in str(e):
                logger.error(f"Failed to add reaction: {e}")
            return False

    def _remove_reaction(self, channel_id: str, timestamp: str, emoji: str) -> bool:
        """Remove a reaction from a message."""
        try:
            self.client.reactions_remove(
                channel=channel_id,
                timestamp=timestamp,
                name=emoji,
            )
            logger.debug(f"Removed :{emoji}: from {timestamp}")
            return True
        except SlackApiError as e:
            # Ignore "no_reaction" errors
            if "no_reaction" not in str(e):
                logger.error(f"Failed to remove reaction: {e}")
            return False

    def _is_mention_to_me(self, message: dict) -> bool:
        """Check if message mentions the bot user or contains trigger pattern."""
        text = message.get("text", "")
        if self.bot_user_id and f"<@{self.bot_user_id}>" in text:
            return True
        if self.trigger_pattern and self.trigger_pattern in text:
            return True
        return False

    def _classify_complexity(self, text: str) -> str:
        """Classify question complexity.

        Returns:
            "simple" for quick answers, "complex" for multi-step tasks
        """
        text_lower = text.lower()
        if any(kw in text_lower for kw in COMPLEX_KEYWORDS):
            return "complex"
        return "simple"

    def _is_workflow_task(self, text: str) -> bool:
        """Determine if the task requires a full workflow.

        Workflow tasks require:
        - Context exploration (explore-context)
        - TODO creation (create-todo)
        - Tech spec writing (write-spec)
        - Final report (report)

        Returns:
            True if requires workflow, False for simple responses
        """
        text_lower = text.lower()

        # Workflow trigger keywords (tasks requiring multi-step process)
        workflow_keywords = [
            # Development tasks
            "implement",
            "create",
            "develop",
            "write",
            "modify",
            "fix",
            "refactor",
            "refactoring",
            "optimize",
            # Analysis tasks
            "analyze",
            "investigate",
            "review",
            "examine",
            # Planning tasks
            "plan",
            "design",
            "architecture",
            "spec",
            "specification",
            # Bug/Issue tasks
            "bug",
            "error",
            "issue",
            "problem",
            "incident",
            # Explicit workflow triggers
            "workflow",
            "task",
            "todo",
        ]

        # Check for workflow keywords
        for kw in workflow_keywords:
            if kw in text_lower:
                return True

        # Long messages (>200 chars) are more likely workflow tasks
        if len(text) > 200:
            return True

        return False

    def _create_mention_dir(self, message_ts: str) -> Path:
        """Create directory for mention processing data.

        Args:
            message_ts: Message timestamp

        Returns:
            Path to mention directory
        """
        dir_name = message_ts.replace(".", "_")
        mention_dir = self.data_dir / "mentions" / dir_name
        mention_dir.mkdir(parents=True, exist_ok=True)
        return mention_dir

    def _save_execution_result(
        self,
        mention_dir: Path,
        result: subprocess.CompletedProcess,
        stage: str = "main",
    ) -> None:
        """Save execution result to files.

        Args:
            mention_dir: Directory to save results
            result: subprocess result
            stage: Execution stage name (for multiple runs)
        """
        # Save full output log
        log_file = mention_dir / f"execution_{stage}.log"
        with open(log_file, "w", encoding="utf-8") as f:
            f.write(f"=== STDOUT ===\n{result.stdout}\n\n")
            f.write(f"=== STDERR ===\n{result.stderr}\n\n")
            f.write(f"=== RETURN CODE ===\n{result.returncode}\n")

        # Save result summary
        result_data = {
            "stage": stage,
            "returncode": result.returncode,
            "executed_at": datetime.now().isoformat(),
            "stdout_length": len(result.stdout) if result.stdout else 0,
            "stderr_length": len(result.stderr) if result.stderr else 0,
            "success": result.returncode == 0,
        }
        result_file = mention_dir / f"result_{stage}.yaml"
        with open(result_file, "w", encoding="utf-8") as f:
            yaml.dump(result_data, f, allow_unicode=True)

        logger.info(f"Saved execution result to {mention_dir}")

    def _try_context_recovery(
        self,
        base_cmd: list[str],
        session_id: str,
        original_prompt: str,
        timeout: int,
        env: dict,
        mention_dir: Path,
    ) -> subprocess.CompletedProcess:
        """Try to recover from 'prompt too long' error using /compact or /clear.

        First attempts /compact to summarize context, then falls back to /clear
        if that fails. Finally retries the original prompt.

        Args:
            base_cmd: Base claude command
            session_id: Session ID to recover
            original_prompt: Original prompt to retry
            timeout: Command timeout
            env: Environment variables
            mention_dir: Directory for saving logs

        Returns:
            The result of the final prompt execution
        """
        project_root = str(self.data_dir.parent)

        # Step 1: Try /compact
        compact_cmd = base_cmd + ["-r", session_id, "/compact"]
        logger.info(f"[Agentic] Trying /compact for session {session_id}")

        compact_result = subprocess.run(
            compact_cmd,
            timeout=timeout,
            capture_output=True,
            text=True,
            cwd=project_root,
            env=env,
        )
        self._save_execution_result(mention_dir, compact_result, "compact")

        # Check if /compact succeeded
        if compact_result.returncode == 0:
            logger.info("[Agentic] /compact succeeded, retrying original prompt")
            retry_cmd = base_cmd + ["-r", session_id, original_prompt]
            result = subprocess.run(
                retry_cmd,
                timeout=timeout,
                capture_output=True,
                text=True,
                cwd=project_root,
                env=env,
            )
            self._save_execution_result(mention_dir, result, "retry_after_compact")
            return result

        # Step 2: /compact failed, try /clear
        logger.warning("[Agentic] /compact failed, trying /clear")
        clear_cmd = base_cmd + ["-r", session_id, "/clear"]

        clear_result = subprocess.run(
            clear_cmd,
            timeout=timeout,
            capture_output=True,
            text=True,
            cwd=project_root,
            env=env,
        )
        self._save_execution_result(mention_dir, clear_result, "clear")

        # Retry original prompt after /clear
        logger.info("[Agentic] Retrying original prompt after /clear")
        retry_cmd = base_cmd + ["-r", session_id, original_prompt]
        result = subprocess.run(
            retry_cmd,
            timeout=timeout,
            capture_output=True,
            text=True,
            cwd=project_root,
            env=env,
        )
        self._save_execution_result(mention_dir, result, "retry_after_clear")
        return result

    def _get_message_thread_ts(self, channel_id: str, message_ts: str) -> str | None:
        """Get the thread_ts for a message by fetching it from the API."""
        try:
            # Use conversations.history with latest/oldest to get specific message
            result = self.client.conversations_history(
                channel=channel_id,
                latest=message_ts,
                oldest=message_ts,
                inclusive=True,
                limit=1,
            )
            messages = result.get("messages", [])
            if messages:
                return messages[0].get("thread_ts")

            # If not found in history, try conversations.replies
            # The message might be a thread reply
            result = self.client.conversations_replies(
                channel=channel_id,
                ts=message_ts,
                limit=1,
            )
            messages = result.get("messages", [])
            if messages:
                return messages[0].get("thread_ts")

        except SlackApiError as e:
            logger.debug(f"Failed to get thread_ts for {message_ts}: {e}")

        return None

    def _save_mention_file(self, message: dict, channel_id: str) -> tuple[Path, dict]:
        """Save mention info to a YAML file in dedicated directory.

        Returns:
            Tuple of (mention_directory, mention_data)
        """
        message_ts = message.get("ts", "")
        text = message.get("text", "")

        # Handle thread_ts - search results may have different structure
        thread_ts = message.get("thread_ts")

        # If no thread_ts from search, try to get from API
        if not thread_ts:
            thread_ts = self._get_message_thread_ts(channel_id, message_ts)

        # Default to message_ts if still no thread_ts (top-level message)
        if not thread_ts:
            thread_ts = message_ts

        logger.info(f"Mention: channel={channel_id}, msg_ts={message_ts}, thread_ts={thread_ts}")

        # Classify complexity
        complexity = self._classify_complexity(text)

        mention_data = {
            "channel_id": channel_id,
            "message_ts": message_ts,
            "thread_ts": thread_ts,
            "text": text,
            "user": message.get("user", ""),
            "complexity": complexity,
            "created_at": datetime.now().isoformat(),
        }

        # Create dedicated directory for this mention
        mention_dir = self._create_mention_dir(message_ts)

        # Save input data
        input_file = mention_dir / "input.yaml"
        with open(input_file, "w", encoding="utf-8") as f:
            yaml.dump(mention_data, f, allow_unicode=True, default_flow_style=False)

        # Also save to pending for backward compatibility
        filename = f"{message_ts.replace('.', '_')}.yaml"
        pending_file = self.data_dir / "mentions" / "pending" / filename
        with open(pending_file, "w", encoding="utf-8") as f:
            yaml.dump(mention_data, f, allow_unicode=True, default_flow_style=False)

        return mention_dir, mention_data

    def _download_thread_files(
        self,
        channel_id: str,
        thread_ts: str,
        mention_dir: Path,
    ) -> str:
        """Download files from a Slack thread and format for Claude.

        Args:
            channel_id: Slack channel ID
            thread_ts: Thread timestamp
            mention_dir: Directory to save downloaded files

        Returns:
            Formatted text describing thread files for Claude prompt context.
        """
        try:
            download_dir = mention_dir / "files"
            download_dir.mkdir(exist_ok=True)

            downloader = SlackFileDownloader(
                token=self.client.token,
                cookie=os.environ.get("SLACK_COOKIE"),
                download_dir=download_dir,
            )

            files = downloader.get_thread_files(channel_id, thread_ts)
            if not files:
                return ""

            logger.info(f"[Files] Found {len(files)} files in thread {thread_ts}")

            processed = downloader.download_all(files)
            formatted = downloader.format_for_claude(processed)

            # Save file manifest
            manifest = {
                "thread_ts": thread_ts,
                "channel_id": channel_id,
                "files": [pf.to_dict() for pf in processed],
                "downloaded_at": datetime.now().isoformat(),
            }
            manifest_file = mention_dir / "files_manifest.yaml"
            with open(manifest_file, "w", encoding="utf-8") as f:
                yaml.dump(manifest, f, allow_unicode=True, default_flow_style=False)

            logger.info(
                f"[Files] Downloaded {sum(1 for pf in processed if pf.is_success)}/{len(processed)} files"
            )
            return formatted

        except Exception as e:
            logger.error(f"[Files] Failed to download thread files: {e}")
            return ""

    def _process_mention_agentic_sync(self, message: dict, channel_id: str) -> bool:
        """Process a mention using claude -p with session support (synchronous worker)."""
        message_ts = message.get("ts", "")
        user_id = message.get("user", "")
        text = message.get("text", "")

        try:
            # Save mention info to file and get directory
            mention_dir, mention_data = self._save_mention_file(message, channel_id)
            logger.info(f"[Agentic] Saved mention to: {mention_dir}")

            # Canonical thread_ts is resolved in _save_mention_file (API fallback included).
            thread_ts = str(mention_data.get("thread_ts") or message_ts)

            complexity = mention_data.get("complexity", "simple")
            logger.info(f"[Agentic] Complexity: {complexity}")

            # Policy: create a new session for every mention event (same thread can have many sessions).
            agent_session = self.session_manager.create_session(
                channel_id=channel_id,
                thread_ts=thread_ts,
                user_id=user_id,
                message=text,
                trigger_type="mention",
            )
            session_id = agent_session.session_id
            is_resuming = False

            # Register thread-session mapping for thread-level history view.
            self.session_manager.register_thread_session(channel_id, thread_ts, session_id)
            logger.info(f"[Agentic] Created new session: {session_id}")

            # Log user input for real-time dashboard
            self.interaction_logger.log_user_input(
                session_id=session_id,
                channel_id=channel_id,
                thread_ts=thread_ts,
                content=text,
                user_id=user_id,
                metadata={
                    "complexity": complexity,
                    "is_resuming": is_resuming,
                    "is_new_thread": thread_ts == message_ts,
                },
            )

            # Log processing started
            self.interaction_logger.log_processing_started(
                session_id=session_id,
                channel_id=channel_id,
                thread_ts=thread_ts,
                is_resuming=is_resuming,
                metadata={"complexity": complexity},
            )

            # Store initial context in memory
            self.session_manager.add_memory_entry(
                session_id=session_id,
                key="complexity",
                value=complexity,
                summary=f"Message complexity: {complexity}",
                source="sdk_poller",
            )

            # Save session info (for backward compatibility)
            session_data = {
                "session_id": session_id,
                "channel_id": channel_id,
                "thread_ts": thread_ts,
                "complexity": complexity,
                "status": "started",
                "created_at": datetime.now().isoformat(),
            }
            session_file = mention_dir / "session.yaml"
            with open(session_file, "w", encoding="utf-8") as f:
                yaml.dump(session_data, f, allow_unicode=True)

            # Build prompt using /respond-mention skill with workflow trigger
            input_file = mention_dir / "input.yaml"

            # Determine if this is a complex task requiring full workflow
            is_workflow_task = self._is_workflow_task(mention_data["text"])
            mention_data["workflow_task"] = is_workflow_task
            with open(input_file, "w", encoding="utf-8") as f:
                yaml.dump(mention_data, f, allow_unicode=True, default_flow_style=False)

            session_data["workflow_task"] = is_workflow_task
            with open(session_file, "w", encoding="utf-8") as f:
                yaml.dump(session_data, f, allow_unicode=True)

            # Download files from the thread (if any)
            files_context = self._download_thread_files(channel_id, thread_ts, mention_dir)
            if files_context:
                logger.info(f"[Agentic] Thread files context added ({len(files_context)} chars)")

            lang_prompt = _get_language_prompt()

            if is_workflow_task:
                # Complex task: Start workflow (explore → todo → spec → report)
                prompt = f"""{HUMAN_RESPONSE_GUIDE}
{lang_prompt}
## 🔄 Complex Task Detected - Starting Workflow

This request has been classified as complex and will proceed through a step-by-step workflow.

## Mention Info
- channel_id: {channel_id}
- message_ts: {mention_data["message_ts"]}
- thread_ts: {thread_ts}
- text: {mention_data["text"]}
- user: {mention_data["user"]}
{
                    f'''
## Thread Attachments
{files_context}
'''
                    if files_context
                    else ""
                }
## 📌 Required Execution Order

### Step 1: Initial Response (MUST send - Block Kit)
First, send a Block Kit message to notify the user that work is starting:

```
ToolSearch: "slack"
mcp__slack__slack_send_message(
  channel_id: "{channel_id}",
  thread_ts: "{thread_ts}",
  text: "Got it! Processing your request...",
  blocks: '[{{"type":"section","text":{{"type":"mrkdwn","text":":mag: *Got it!*"}}}},{{"type":"divider"}},{{"type":"section","text":{{"type":"mrkdwn","text":"This appears to be a complex task, so I\\'ll proceed step by step:\\n1️⃣ Analyzing context...\\n2️⃣ TODO creation pending\\n3️⃣ Work proceeds after approval"}}}},{{"type":"context","elements":[{{"type":"mrkdwn","text":"_I\\'ll share detailed analysis results shortly._"}}]}}]'
)
```

### Step 2: Context Exploration (/explore-context)
Execute the explore-context skill using the Skill tool:
```
Skill: explore-context
Args: {channel_id}-{thread_ts}
```

### Step 3: TODO Creation (/create-todo)
After exploration, execute the create-todo skill:
```
Skill: create-todo
Args: [exploration result ID]
```

Once the TODO is created, an approval request with reaction guide will be automatically sent to Slack via Block Kit.
The user can approve by adding :+1: reaction or reject by adding :-1: reaction on the approval message.

### Step 4: Completion Notice (Block Kit)
```
mcp__slack__slack_send_message(
  channel_id: "{channel_id}",
  thread_ts: "{thread_ts}",
  text: "Analysis complete! Please review the TODO list.",
  blocks: '[{{"type":"section","text":{{"type":"mrkdwn","text":":clipboard: *Analysis complete!*"}}}},{{"type":"divider"}},{{"type":"section","text":{{"type":"mrkdwn","text":"Please review and approve the TODO list above."}}}},{{"type":"context","elements":[{{"type":"mrkdwn","text":"_위의 TODO 메시지에 :+1: (승인) 또는 :-1: (수정 요청) 리액션을 달아주세요._"}}]}}]'
)
```

## ⚠️ Important: Slack Message Required
- Send progress updates to Slack at **every** step using Block Kit format
- All approval request messages MUST include reaction guide (:+1: = approve, :-1: = reject)
- If message sending fails, use slack-bot MCP: mcp__slack-bot__slack_reply_to_thread
- NEVER end work without sending a message"""
            else:
                # Simple task: Use respond-mention skill
                prompt = f"""{HUMAN_RESPONSE_GUIDE}
{lang_prompt}
## Mention Response (/respond-mention skill execution)

## Mention Info
- channel_id: {channel_id}
- message_ts: {mention_data["message_ts"]}
- thread_ts: {thread_ts}
- text: {mention_data["text"]}
- user: {mention_data["user"]}
- input_file: {input_file}
{
                    f'''
## Thread Attachments
{files_context}
'''
                    if files_context
                    else ""
                }
## 📌 Required Execution Order

### Step 1: Load Slack tools
```
ToolSearch: "slack"
```

### Step 2: Fetch thread context
```
mcp__slack__slack_get_thread_replies(channel_id: "{channel_id}", thread_ts: "{thread_ts}")
```

### Step 3: Search related keywords
Extract key terms from the message and search:
```
mcp__slack__slack_get_channel_history(channel_id: "{channel_id}", limit: 30)
```

### Step 4: Generate and send response (⚠️ Required - Block Kit)
Based on context, write a natural response and **MUST** send it using Block Kit format:

```
mcp__slack__slack_send_message(
  channel_id: "{channel_id}",
  thread_ts: "{thread_ts}",
  text: [generated response as plain text fallback],
  blocks: [Block Kit blocks JSON string - use section blocks for content, context blocks for metadata]
)
```

Example Block Kit structure for a response:
```json
[
  {{"type": "section", "text": {{"type": "mrkdwn", "text": ":wave: *Response Title*\\n\\nYour detailed answer here..."}}}},
  {{"type": "divider"}},
  {{"type": "context", "elements": [{{"type": "mrkdwn", "text": "_Searched N related conversations_"}}]}}
]
```

## ⚠️ Important: Slack Message Required

1. **NEVER end without sending a message**
2. If Block Kit `blocks` parameter is not supported by the MCP tool, fall back to plain `text` only
3. If slack MCP fails, use slack-bot MCP:
   - mcp__slack-bot__slack_reply_to_thread(channel_id, thread_ts, text)
4. Write responses naturally following Human Framework rules
5. Even if no context found, send a response like "I couldn't find related information"

## Response Style
- Friendly and natural language
- Use Block Kit sections for structured information
- Use emojis appropriately
- Be honest if uncertain
- Keep it short and clear"""

            # Use session-id for all tasks to ensure log mapping in the dashboard
            # Allow both slack (xoxc) and slack-bot (xoxb) MCP tools
            allowed_tools = [
                # slack MCP (xoxc token)
                "mcp__slack__slack_send_message",
                "mcp__slack__slack_post_message",
                "mcp__slack__slack_reply_to_thread",
                "mcp__slack__slack_get_thread",
                "mcp__slack__slack_get_thread_replies",
                "mcp__slack__slack_get_channel_history",
                "mcp__slack__slack_search_messages",
                "mcp__slack__slack_conversations_history",
                "mcp__slack__slack_list_conversations",
                "mcp__slack__slack_list_channels",
                "mcp__slack__slack_users_info",
                "mcp__slack__slack_get_full_conversation",
                "mcp__slack__slack_add_reaction",
                "mcp__slack__slack_get_user_profile",
                "mcp__slack__slack_get_users",
                # slack-bot-mcp MCP (xoxb token) - fallback
                "mcp__slack-bot-mcp__slack_post_message",
                "mcp__slack-bot-mcp__slack_reply_to_thread",
                "mcp__slack-bot-mcp__slack_get_channel_history",
                "mcp__slack-bot-mcp__slack_get_thread_replies",
                "mcp__slack-bot-mcp__slack_list_channels",
                "mcp__slack-bot-mcp__slack_get_users",
                "mcp__slack-bot-mcp__slack_get_user_profile",
                "mcp__slack-bot-mcp__slack_add_reaction",
                # Common tools
                "ToolSearch",
                # Skill tool for workflow triggers
                "Skill",
                # File tools for exploration results
                "Read",
                "Write",
                "Glob",
            ]
            base_cmd = [
                "claude",
                "--dangerously-skip-permissions",
                "--allowedTools",
            ] + allowed_tools

            # Build command based on session mode
            if is_resuming:
                # Resume existing session: claude -r <session_id> "query"
                # This preserves conversation context from previous interactions
                cmd = base_cmd + ["-r", session_id, prompt]
                logger.info(f"[Agentic] Resuming session {session_id} with claude -r")
            else:
                # New session: claude --session-id <uuid> -p "prompt"
                cmd = base_cmd + ["--session-id", session_id, "-p", prompt]
                logger.info(f"[Agentic] Starting new session {session_id}")

            logger.info(f"[Agentic] Running claude (complexity={complexity}): {mention_dir}")

            # Get timeout from config (default 30 minutes, configurable via ULTRAWORK_AGENTIC_TIMEOUT env)
            agentic_timeout = get_config().executor.agentic_timeout_seconds

            # Set IS_SANDBOX=1 to allow --dangerously-skip-permissions with root/sudo
            env = os.environ.copy()
            env["IS_SANDBOX"] = "1"

            result = subprocess.run(
                cmd,
                timeout=agentic_timeout,
                capture_output=True,
                text=True,
                cwd=str(self.data_dir.parent),  # Project root
                env=env,
            )

            # Handle "Prompt is too long" error with /compact or /clear
            prompt_too_long = (
                result.returncode != 0
                and result.stderr
                and "prompt is too long" in result.stderr.lower()
            )
            if prompt_too_long and is_resuming:
                logger.warning(
                    f"[Agentic] Prompt too long for session {session_id}, trying /compact..."
                )
                result = self._try_context_recovery(
                    base_cmd, session_id, prompt, agentic_timeout, env, mention_dir
                )

            # Save execution result
            self._save_execution_result(mention_dir, result, "main")

            # Log output for debugging
            if result.stdout:
                logger.info(f"[Agentic] stdout: {result.stdout[:500]}")
            if result.stderr:
                logger.warning(f"[Agentic] stderr: {result.stderr[:500]}")

            # Update session status via SessionManager
            if result.returncode == 0:
                # Transition role based on workflow type
                if is_workflow_task:
                    self.session_manager.transition_role(
                        session_id,
                        AgentRole.PLANNER,
                        reason="Started workflow processing",
                        trigger_skill="respond-mention",
                    )
                self.session_manager.complete_session(session_id, success=True)
            else:
                self.session_manager.complete_session(session_id, success=False)

            # Log processing completed for real-time dashboard
            self.interaction_logger.log_processing_completed(
                session_id=session_id,
                channel_id=channel_id,
                thread_ts=thread_ts,
                success=(result.returncode == 0),
                exit_code=result.returncode,
                metadata={
                    "complexity": complexity,
                    "is_workflow_task": is_workflow_task,
                    "is_resuming": is_resuming,
                },
            )

            # Update session file (for backward compatibility)
            session_data["status"] = "completed" if result.returncode == 0 else "failed"
            session_data["completed_at"] = datetime.now().isoformat()
            with open(session_file, "w", encoding="utf-8") as f:
                yaml.dump(session_data, f, allow_unicode=True)

            # Update reactions based on result
            self._remove_reaction(channel_id, message_ts, EMOJI_PROCESSING)

            # Save response summary
            response_data = {
                "success": result.returncode == 0,
                "complexity": complexity,
                "session_id": session_id,
                "workflow_task": is_workflow_task,
                "is_resuming": is_resuming,
                "response_length": len(result.stdout) if result.stdout else 0,
                "completed_at": datetime.now().isoformat(),
            }
            response_file = mention_dir / "response.yaml"
            with open(response_file, "w", encoding="utf-8") as f:
                yaml.dump(response_data, f, allow_unicode=True)

            if result.returncode == 0:
                self._add_reaction(channel_id, message_ts, EMOJI_DONE)
                logger.info(f"[Agentic] Successfully handled: {message_ts}")

                # Move pending file to completed
                pending_file = (
                    self.data_dir / "mentions" / "pending" / f"{message_ts.replace('.', '_')}.yaml"
                )
                if pending_file.exists():
                    completed_file = self.data_dir / "mentions" / "completed" / pending_file.name
                    shutil.move(str(pending_file), str(completed_file))

                return True
            else:
                self._add_reaction(channel_id, message_ts, EMOJI_ERROR)
                logger.error(
                    f"[Agentic] Failed: {result.stderr[:200] if result.stderr else 'no stderr'}"
                )

                # Move pending file to failed
                pending_file = (
                    self.data_dir / "mentions" / "pending" / f"{message_ts.replace('.', '_')}.yaml"
                )
                if pending_file.exists():
                    failed_file = self.data_dir / "mentions" / "failed" / pending_file.name
                    shutil.move(str(pending_file), str(failed_file))

                return False

        except subprocess.TimeoutExpired:
            logger.error(f"[Agentic] Timeout for {message_ts}")
            self._remove_reaction(channel_id, message_ts, EMOJI_PROCESSING)
            self._add_reaction(channel_id, message_ts, EMOJI_ERROR)
            return False

        except Exception as e:
            logger.error(f"[Agentic] Error: {e}")
            self._remove_reaction(channel_id, message_ts, EMOJI_PROCESSING)
            self._add_reaction(channel_id, message_ts, EMOJI_ERROR)
            return False

    def _process_mention_agentic(self, message: dict, channel_id: str) -> bool:
        """Process a mention using claude -p skill (non-blocking)."""
        message_ts = message.get("ts", "")
        text = message.get("text", "")

        logger.info(f"[Agentic] Processing: {text[:50]}...")

        # Add 👀 reaction to indicate processing
        self._add_reaction(channel_id, message_ts, EMOJI_PROCESSING)

        # Run in background thread so polling continues
        thread = threading.Thread(
            target=self._process_mention_agentic_sync,
            args=(message, channel_id),
            daemon=True,
        )
        thread.start()

        return True

    def _process_mention_simple(self, message: dict, channel_id: str) -> None:
        """Process a mention in simple mode (queue for manual review)."""
        message_ts = message.get("ts", "")
        self._add_reaction(channel_id, message_ts, EMOJI_PROCESSING)
        logger.info(f"[Simple] Queued mention for review: {message_ts}")

    def _process_mention(self, message: dict, channel_id: str) -> None:
        """Process a mention."""
        if self.agentic_mode:
            self._process_mention_agentic(message, channel_id)
        else:
            self._process_mention_simple(message, channel_id)

    async def poll_once(self) -> dict:
        """Execute a single poll cycle."""
        start_time = time.time()
        state = self.state_manager.load_state()

        results = {
            "channels_checked": 0,
            "messages_found": 0,
            "mentions_found": 0,
            "responses_sent": 0,
            "errors": [],
        }

        try:
            # Use search API to find all mentions (including threads)
            # Only get mentions newer than last checked timestamp
            oldest_ts = state.last_checked_ts
            if self.only_new_mentions and self._startup_ts:
                if self._ts_to_float(oldest_ts) < self._ts_to_float(self._startup_ts):
                    oldest_ts = self._startup_ts

            mentions = self._search_mentions(oldest_ts=oldest_ts)
            results["messages_found"] = len(mentions)

            for msg in mentions:
                msg_ts = msg.get("ts", "")
                channel_id = msg.get("channel", {}).get("id", "")

                if not channel_id:
                    continue

                # Skip already processed
                if self.state_manager.is_processed(msg_ts):
                    continue

                results["mentions_found"] += 1
                logger.info(f"Processing mention: {msg.get('text', '')[:50]}...")

                try:
                    self._process_mention(msg, channel_id)
                    results["responses_sent"] += 1
                except Exception as e:
                    logger.error(f"Error processing mention: {e}")
                    results["errors"].append(str(e))

                # Mark as processed
                self.state_manager.mark_processed(msg_ts)

                # Update last checked timestamp
                if msg_ts > (state.last_checked_ts or ""):
                    state.last_checked_ts = msg_ts

            # Update state
            if state.last_checked_ts:
                self.state_manager.update_last_checked(state.last_checked_ts)
            self.state_manager.clear_errors()

            # Record stats
            duration_ms = int((time.time() - start_time) * 1000)
            self.state_manager.record_poll(
                mentions_found=results["mentions_found"],
                responses_sent=results["responses_sent"],
                responses_pending=0,
                duration_ms=duration_ms,
            )

            logger.info(
                f"Poll complete: {results['mentions_found']} mentions, "
                f"{results['responses_sent']} responses in {duration_ms}ms"
            )

        except Exception as e:
            logger.error(f"Poll error: {e}")
            self.state_manager.record_error(str(e))
            results["errors"].append(str(e))

        return results

    async def run_daemon(self) -> None:
        """Run as a continuous daemon."""
        self._running = True
        self._stop_event = asyncio.Event()

        # Record daemon start
        self.state_manager.set_daemon_running(os.getpid())
        self._prime_new_only_baseline()
        logger.info(f"Daemon started (PID: {os.getpid()})")

        # Initialize cron runner
        cron_runner = None
        try:
            from ultrawork.scheduler.runner import CronRunner

            token = os.environ.get("SLACK_TOKEN")
            cookie = os.environ.get("SLACK_COOKIE")
            cron_runner = CronRunner(
                data_dir=self.data_dir,
                slack_token=token,
                slack_cookie=cookie,
            )
            logger.info("Cron runner initialized")
        except Exception as e:
            logger.warning(f"Cron runner initialization failed (non-fatal): {e}")

        # Initialize reaction approval handler
        reaction_handler = None
        try:
            token = os.environ.get("SLACK_TOKEN")
            cookie = os.environ.get("SLACK_COOKIE")
            if token:
                reaction_handler = ReactionApprovalHandler(
                    slack_token=token,
                    data_dir=self.data_dir,
                    slack_cookie=cookie,
                )
                logger.info("Reaction approval handler initialized")
        except Exception as e:
            logger.warning(f"Reaction approval handler init failed (non-fatal): {e}")

        # Set up signal handlers
        def handle_signal(signum: int, frame) -> None:  # noqa: ARG001
            logger.info(f"Received signal {signum}, stopping...")
            self._running = False
            self._stop_event.set()

        signal.signal(signal.SIGINT, handle_signal)
        signal.signal(signal.SIGTERM, handle_signal)

        try:
            while self._running:
                try:
                    await self.poll_once()
                except Exception as e:
                    logger.error(f"Poll error: {e}")
                    self.state_manager.record_error(str(e))

                    # Check consecutive error limit
                    state = self.state_manager.load_state()
                    if state.consecutive_errors >= 5:
                        logger.error("Too many consecutive errors, stopping")
                        break

                # Run cron jobs check
                if cron_runner:
                    try:
                        executed = await cron_runner.run_tick()
                        if executed > 0:
                            logger.info(f"Cron: executed {executed} jobs")
                    except Exception as e:
                        logger.error(f"Cron tick error: {e}")

                # Check for reaction-based approvals
                if reaction_handler:
                    try:
                        results = await reaction_handler.check_and_process()
                        processed = [r for r in results if r.action in ("approved", "rejected")]
                        if processed:
                            logger.info(
                                f"Reaction approvals: {len(processed)} processed "
                                f"({', '.join(f'{r.task_id}={r.action}' for r in processed)})"
                            )
                    except Exception as e:
                        logger.error(f"Reaction approval check error: {e}")

                # Wait for next poll or stop signal
                try:
                    await asyncio.wait_for(
                        self._stop_event.wait(),
                        timeout=self.poll_interval,
                    )
                    break  # Stop event was set
                except TimeoutError:
                    continue  # Timeout - do next poll

        finally:
            self.state_manager.clear_daemon()
            logger.info("Daemon stopped")
            self._running = False

    def stop(self) -> None:
        """Stop the daemon."""
        self._running = False
        self._stop_event.set()


def main() -> None:
    """Main entry point for SDK poller daemon."""
    import argparse

    from dotenv import load_dotenv

    # Parse arguments
    parser = argparse.ArgumentParser(description="Slack mention polling daemon")
    parser.add_argument(
        "--agentic",
        action="store_true",
        help="Enable agentic mode: use claude -p skill for intelligent responses",
    )
    parser.add_argument(
        "--interval",
        type=int,
        default=None,
        help="Poll interval in seconds (overrides config)",
    )
    args = parser.parse_args()

    # Try multiple locations for .env
    env_paths = [
        Path.cwd() / ".env",
        Path(__file__).parent.parent.parent.parent / ".env",  # Project root
    ]
    for env_path in env_paths:
        if env_path.exists():
            load_dotenv(env_path)
            break

    # Load config
    config = get_config()

    # Get Slack token from environment
    token = os.environ.get("SLACK_TOKEN")
    if not token:
        print("Error: SLACK_TOKEN environment variable not set")
        print("Set it with: export SLACK_TOKEN='xoxc-...' or export SLACK_TOKEN='xoxb-...'")
        sys.exit(1)

    # Get cookie for xoxc tokens
    cookie = os.environ.get("SLACK_COOKIE")
    if token.startswith("xoxc-") and not cookie:
        print("Error: SLACK_COOKIE environment variable required for xoxc tokens")
        print("Set it with: export SLACK_COOKIE='xoxd-...'")
        sys.exit(1)

    bot_user_id = config.slack.bot_user_id
    trigger_pattern = config.slack.trigger_pattern

    if not bot_user_id and not trigger_pattern:
        print("Error: Either bot_user_id or trigger_pattern must be configured in ultrawork.yaml")
        print("  - For @mention mode: set slack.bot_user_id")
        print("  - For keyword mode: set slack.trigger_pattern (e.g., '!uw')")
        sys.exit(1)

    poll_interval = args.interval or config.polling.poll_interval_seconds

    print("Starting SDK poller daemon...")
    if bot_user_id:
        print(f"  Bot User ID: {bot_user_id}")
    if trigger_pattern:
        print(f"  Trigger Pattern: {trigger_pattern}")
    print(f"  Poll Interval: {poll_interval}s")
    print(f"  Data Dir: {config.data_dir}")
    print(f"  Token Type: {'xoxc (with cookie)' if token.startswith('xoxc-') else 'bot/user'}")
    print(f"  Agentic Mode: {'ENABLED (claude -p skill)' if args.agentic else 'disabled'}")
    print("Press Ctrl+C to stop\n")

    # Create and run poller
    poller = SlackSDKPoller(
        token=token,
        bot_user_id=bot_user_id,
        trigger_pattern=trigger_pattern,
        data_dir=config.data_dir,
        poll_interval=poll_interval,
        cookie=cookie,
        agentic_mode=args.agentic,
    )

    asyncio.run(poller.run_daemon())


if __name__ == "__main__":
    main()
