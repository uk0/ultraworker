"""Slack polling daemon for real-time mention tracking."""

import asyncio
import os
import signal
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from ultrawork.config import PollingConfig, ResponseConfig, get_config
from ultrawork.models.polling import PendingResponse
from ultrawork.slack.explorer import SlackExplorer
from ultrawork.slack.monitor import SlackMonitor
from ultrawork.slack.rate_limiter import SlackRateLimiter
from ultrawork.slack.responder import SlackResponder
from ultrawork.slack.state import PollingStateManager


class SlackPoller:
    """Polls Slack for new mentions and handles responses."""

    def __init__(
        self,
        data_dir: Path,
        bot_user_id: str,
        polling_config: PollingConfig | None = None,
        response_config: ResponseConfig | None = None,
    ):
        """Initialize the poller.

        Args:
            data_dir: Base data directory
            bot_user_id: Slack bot/user ID to monitor mentions for
            polling_config: Polling configuration
            response_config: Response configuration
        """
        self.data_dir = Path(data_dir)
        self.bot_user_id = bot_user_id
        self.polling_config = polling_config or PollingConfig()
        self.response_config = response_config or ResponseConfig()

        # Initialize components
        self.state_manager = PollingStateManager(data_dir)
        self.monitor = SlackMonitor(data_dir, bot_user_id)
        self.explorer = SlackExplorer(data_dir)
        self.responder = SlackResponder(data_dir, response_config)
        self.rate_limiter = SlackRateLimiter()

        # Daemon control
        self._running = False
        self._stop_event: asyncio.Event | None = None

        # MCP tool callbacks (to be set by CLI)
        self._search_messages: Any = None
        self._get_thread: Any = None
        self._send_message: Any = None

    def set_mcp_callbacks(
        self,
        search_messages: Any,
        get_thread: Any,
        send_message: Any,
    ) -> None:
        """Set MCP tool callbacks for Slack operations.

        Args:
            search_messages: Callback for slack_search_messages
            get_thread: Callback for slack_get_thread
            send_message: Callback for slack_send_message
        """
        self._search_messages = search_messages
        self._get_thread = get_thread
        self._send_message = send_message

    def _build_search_query(self, last_ts: str) -> str:
        """Build Slack search query for mentions.

        Note: Slack search API may not work with all MCP implementations.
        Use poll_channels() method for channel-based polling instead.

        Args:
            last_ts: Last checked timestamp

        Returns:
            Search query string
        """
        query_parts = [f"to:@{self.bot_user_id}"]

        if last_ts:
            # Convert timestamp to date for Slack search
            try:
                ts_float = float(last_ts)
                dt = datetime.fromtimestamp(ts_float)
                query_parts.append(f"after:{dt.strftime('%Y-%m-%d')}")
            except (ValueError, OSError):
                pass

        return " ".join(query_parts)

    def is_mention_to_me(self, message: dict) -> bool:
        """Check if a message mentions the bot user.

        Args:
            message: Slack message dict

        Returns:
            True if message mentions the bot
        """
        text = message.get("text", "")
        # Check for direct mention
        return f"<@{self.bot_user_id}>" in text

    async def _search_mentions(self, query: str, count: int = 50) -> list[dict]:
        """Search for mentions via MCP.

        Args:
            query: Search query
            count: Max results

        Returns:
            List of message dicts
        """
        if self._search_messages is None:
            raise RuntimeError(
                "MCP search callback not set. "
                "Call set_mcp_callbacks() or use poll_once_interactive()."
            )

        await self.rate_limiter.wait_if_needed()
        result = await self._search_messages(query=query, count=count)

        # Parse result - format depends on MCP tool response
        messages = []
        if isinstance(result, dict):
            messages = result.get("messages", {}).get("matches", [])
        elif isinstance(result, list):
            messages = result

        return messages

    async def _fetch_thread(self, channel_id: str, thread_ts: str) -> list[dict]:
        """Fetch thread messages via MCP.

        Args:
            channel_id: Slack channel ID
            thread_ts: Thread timestamp

        Returns:
            List of thread messages
        """
        if self._get_thread is None:
            raise RuntimeError(
                "MCP get_thread callback not set. "
                "Call set_mcp_callbacks() or use poll_once_interactive()."
            )

        await self.rate_limiter.wait_if_needed()
        result = await self._get_thread(channel_id=channel_id, thread_ts=thread_ts)

        if isinstance(result, dict):
            return result.get("messages", [])
        elif isinstance(result, list):
            return result
        return []

    async def _send_response(
        self,
        channel_id: str,
        text: str,
        thread_ts: str | None = None,
    ) -> bool:
        """Send a response message via MCP.

        Args:
            channel_id: Channel to send to
            text: Message text
            thread_ts: Thread to reply to

        Returns:
            True if successful
        """
        if self._send_message is None:
            raise RuntimeError(
                "MCP send_message callback not set. "
                "Call set_mcp_callbacks() or use poll_once_interactive()."
            )

        await self.rate_limiter.wait_if_needed()
        try:
            await self._send_message(
                channel_id=channel_id,
                text=text,
                thread_ts=thread_ts,
            )
            return True
        except Exception:
            return False

    async def _process_mention(self, message: dict) -> PendingResponse | None:
        """Process a single mention.

        Args:
            message: Slack message dict

        Returns:
            Pending response if created (None if auto-sent)
        """
        # Extract message info
        channel_info = message.get("channel", {})
        channel_id = (
            channel_info.get("id", "") if isinstance(channel_info, dict) else str(channel_info)
        )
        message_ts = message.get("ts", "")
        thread_ts = message.get("thread_ts", message_ts)

        # Fetch thread context
        thread_messages = []
        if channel_id and thread_ts:
            try:
                thread_messages = await self._fetch_thread(channel_id, thread_ts)
            except Exception:
                pass  # Continue without thread context

        # Process with monitor to create thread record
        thread_record = None
        if thread_messages:
            thread_record = self.monitor.process_thread_messages(
                channel_id=channel_id,
                thread_ts=thread_ts,
                messages=thread_messages,
            )

        # Optionally explore context for complex messages
        context_summary = ""
        exploration_id = None
        if self.polling_config.explore_depth > 0 and len(message.get("text", "")) > 100:
            # Deep exploration for complex messages (simplified here)
            context_summary = f"Thread with {len(thread_messages)} messages"

        # Generate response
        pending, should_send = self.responder.handle_mention(
            message=message,
            thread=thread_record,
            context_summary=context_summary,
            exploration_id=exploration_id,
        )

        # Auto-send if appropriate
        if should_send and channel_id:
            success = await self._send_response(
                channel_id=channel_id,
                text=pending.proposed_response,
                thread_ts=thread_ts,
            )
            if success:
                self.state_manager.mark_processed(message_ts)
                return None

        return pending

    async def poll_once(self) -> dict:
        """Execute a single poll cycle.

        Returns:
            Dictionary with poll results
        """
        start_time = time.time()
        state = self.state_manager.load_state()

        results = {
            "messages_found": 0,
            "new_messages": 0,
            "auto_sent": 0,
            "pending": 0,
            "errors": [],
        }

        try:
            # Build search query
            query = self._build_search_query(state.last_checked_ts)

            # Search for mentions
            messages = await self._search_mentions(
                query=query,
                count=self.polling_config.max_messages_per_poll,
            )
            results["messages_found"] = len(messages)

            # Filter already processed
            new_messages = [
                m for m in messages if not self.state_manager.is_processed(m.get("ts", ""))
            ]
            results["new_messages"] = len(new_messages)

            # Process each new mention
            latest_ts = state.last_checked_ts
            for msg in new_messages:
                msg_ts = msg.get("ts", "")
                try:
                    pending = await self._process_mention(msg)
                    if pending:
                        results["pending"] += 1
                    else:
                        results["auto_sent"] += 1

                    # Track latest timestamp
                    if msg_ts > latest_ts:
                        latest_ts = msg_ts

                except Exception as e:
                    results["errors"].append(f"Error processing {msg_ts}: {e}")

                # Mark as processed
                self.state_manager.mark_processed(msg_ts)

            # Update state
            self.state_manager.update_last_checked(latest_ts)
            self.state_manager.clear_errors()

            # Record stats
            duration_ms = int((time.time() - start_time) * 1000)
            self.state_manager.record_poll(
                mentions_found=results["new_messages"],
                responses_sent=results["auto_sent"],
                responses_pending=results["pending"],
                duration_ms=duration_ms,
            )

        except Exception as e:
            self.state_manager.record_error(str(e))
            results["errors"].append(str(e))

        return results

    async def run_daemon(self) -> None:
        """Run as a continuous daemon."""
        self._running = True
        self._stop_event = asyncio.Event()

        # Record daemon start
        self.state_manager.set_daemon_running(os.getpid())

        # Set up signal handlers
        def handle_signal(signum: int, frame: Any) -> None:  # noqa: ARG001
            self._running = False
            if self._stop_event:
                self._stop_event.set()

        signal.signal(signal.SIGINT, handle_signal)
        signal.signal(signal.SIGTERM, handle_signal)

        try:
            while self._running:
                try:
                    await self.poll_once()
                except Exception as e:
                    self.state_manager.record_error(str(e))

                    # Check consecutive error limit
                    state = self.state_manager.load_state()
                    if state.consecutive_errors >= self.polling_config.max_consecutive_errors:
                        break

                # Wait for next poll or stop signal
                try:
                    await asyncio.wait_for(
                        self._stop_event.wait(),
                        timeout=self.polling_config.poll_interval_seconds,
                    )
                    break  # Stop event was set
                except TimeoutError:
                    continue  # Timeout - do next poll

        finally:
            self.state_manager.clear_daemon()
            self._running = False

    def stop(self) -> None:
        """Stop the daemon."""
        self._running = False
        if self._stop_event:
            self._stop_event.set()

    def get_status(self) -> dict:
        """Get poller status.

        Returns:
            Status dictionary
        """
        state = self.state_manager.load_state()
        stats = self.state_manager.load_stats()
        pending = self.state_manager.list_pending_responses()

        return {
            "daemon_running": self.state_manager.is_daemon_running(),
            "daemon_pid": state.daemon_pid,
            "daemon_started_at": (
                state.daemon_started_at.isoformat() if state.daemon_started_at else None
            ),
            "last_poll_at": (state.last_poll_at.isoformat() if state.last_poll_at else None),
            "poll_count": state.poll_count,
            "error_count": state.error_count,
            "consecutive_errors": state.consecutive_errors,
            "last_error": state.last_error,
            "processed_count": len(state.processed_messages),
            "pending_responses": len(pending),
            "stats": stats.model_dump(),
            "rate_limiter": self.rate_limiter.get_stats(),
        }


class InteractivePoller:
    """Interactive polling using Claude Code MCP tools directly.

    This class is designed to be used within Claude Code sessions
    where MCP tools are available in the conversation context.
    """

    def __init__(self, data_dir: Path | None = None):
        """Initialize interactive poller.

        Args:
            data_dir: Data directory (uses config default if not provided)
        """
        config = get_config()
        self.data_dir = Path(data_dir) if data_dir else config.data_dir
        self.bot_user_id = config.slack.bot_user_id
        self.polling_config = config.polling
        self.response_config = config.response

        self.state_manager = PollingStateManager(self.data_dir)
        self.responder = SlackResponder(self.data_dir, self.response_config)
        self.monitor = SlackMonitor(self.data_dir, self.bot_user_id)

    def build_search_query(self) -> str:
        """Build the search query for current poll.

        Returns:
            Search query string to use with slack_search_messages
        """
        state = self.state_manager.load_state()
        query_parts = [f"to:@{self.bot_user_id}"]

        if state.last_checked_ts:
            try:
                ts_float = float(state.last_checked_ts)
                dt = datetime.fromtimestamp(ts_float)
                query_parts.append(f"after:{dt.strftime('%Y-%m-%d')}")
            except (ValueError, OSError):
                pass

        return " ".join(query_parts)

    def filter_new_messages(self, messages: list[dict]) -> list[dict]:
        """Filter out already processed messages.

        Args:
            messages: List of messages from search

        Returns:
            List of new messages only
        """
        return [m for m in messages if not self.state_manager.is_processed(m.get("ts", ""))]

    def process_message(
        self,
        message: dict,
        thread_messages: list[dict] | None = None,
    ) -> tuple[PendingResponse, bool]:
        """Process a message and generate response.

        Args:
            message: Slack message dict
            thread_messages: Optional thread messages for context

        Returns:
            Tuple of (PendingResponse, should_auto_send)
        """
        # Create thread record if we have thread messages
        thread_record = None
        if thread_messages:
            channel_info = message.get("channel", {})
            channel_id = (
                channel_info.get("id", "") if isinstance(channel_info, dict) else str(channel_info)
            )
            thread_ts = message.get("thread_ts", message.get("ts", ""))

            thread_record = self.monitor.process_thread_messages(
                channel_id=channel_id,
                thread_ts=thread_ts,
                messages=thread_messages,
            )

        return self.responder.handle_mention(
            message=message,
            thread=thread_record,
        )

    def mark_processed(self, message_ts: str) -> None:
        """Mark a message as processed.

        Args:
            message_ts: Message timestamp
        """
        self.state_manager.mark_processed(message_ts)

    def update_last_checked(self, ts: str) -> None:
        """Update last checked timestamp.

        Args:
            ts: Latest message timestamp
        """
        self.state_manager.update_last_checked(ts)

    def get_pending_responses(self) -> list[PendingResponse]:
        """Get all pending responses.

        Returns:
            List of pending responses
        """
        return self.state_manager.list_pending_responses()

    def approve_response(self, message_id: str) -> PendingResponse | None:
        """Approve a pending response.

        Args:
            message_id: Message ID to approve

        Returns:
            The approved response (for sending)
        """
        return self.state_manager.approve_response(message_id)

    def reject_response(self, message_id: str) -> bool:
        """Reject a pending response.

        Args:
            message_id: Message ID to reject

        Returns:
            True if removed
        """
        return self.state_manager.remove_pending_response(message_id)
