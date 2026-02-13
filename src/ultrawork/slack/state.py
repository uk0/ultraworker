"""Polling state management for Slack monitoring."""

from datetime import datetime
from pathlib import Path

import yaml

from ultrawork.models.polling import PendingResponse, PollingState, PollingStats


class PollingStateManager:
    """Manages persistent polling state and pending responses."""

    def __init__(self, data_dir: Path):
        """Initialize the state manager.

        Args:
            data_dir: Base data directory
        """
        self.data_dir = Path(data_dir)
        self.state_dir = self.data_dir / "state"
        self.pending_dir = self.data_dir / "pending"
        self.state_file = self.state_dir / "polling_state.yaml"
        self.stats_file = self.state_dir / "polling_stats.yaml"

        # Ensure directories exist
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.pending_dir.mkdir(parents=True, exist_ok=True)

    def load_state(self) -> PollingState:
        """Load polling state from file."""
        if self.state_file.exists():
            try:
                content = self.state_file.read_text(encoding="utf-8")
                # Handle corrupted files with null characters
                if "\x00" in content:
                    # File is corrupted, reset it
                    import logging

                    logging.getLogger("state").warning(
                        "Corrupted state file with null chars, resetting"
                    )
                    self.state_file.unlink()
                    return PollingState()
                data = yaml.safe_load(content)
                if data:
                    # Convert set from list
                    if "processed_messages" in data and isinstance(
                        data["processed_messages"], list
                    ):
                        data["processed_messages"] = set(data["processed_messages"])
                    return PollingState(**data)
            except (yaml.YAMLError, ValueError) as e:
                # File is corrupted, log and reset
                import logging

                logging.getLogger("state").warning(f"Corrupted state file, resetting: {e}")
                self.state_file.unlink()
        return PollingState()

    def save_state(self, state: PollingState) -> None:
        """Save polling state to file."""
        data = state.model_dump(mode="json")
        # Convert set to list for YAML serialization
        data["processed_messages"] = list(state.processed_messages)
        self.state_file.write_text(
            yaml.dump(data, allow_unicode=True, default_flow_style=False),
            encoding="utf-8",
        )

    def mark_processed(self, message_ts: str) -> None:
        """Mark a message as processed."""
        state = self.load_state()
        state.processed_messages.add(message_ts)
        self.save_state(state)

    def is_processed(self, message_ts: str) -> bool:
        """Check if a message has been processed."""
        state = self.load_state()
        return message_ts in state.processed_messages

    def update_last_checked(self, ts: str) -> None:
        """Update the last checked timestamp."""
        state = self.load_state()
        # Only update if newer
        if not state.last_checked_ts or ts > state.last_checked_ts:
            state.last_checked_ts = ts
        state.last_poll_at = datetime.now()
        state.poll_count += 1
        self.save_state(state)

    def record_error(self, error: str) -> None:
        """Record a polling error."""
        state = self.load_state()
        state.error_count += 1
        state.consecutive_errors += 1
        state.last_error = error
        self.save_state(state)

    def clear_errors(self) -> None:
        """Clear consecutive error count after successful poll."""
        state = self.load_state()
        if state.consecutive_errors > 0:
            state.consecutive_errors = 0
            self.save_state(state)

    def set_daemon_running(self, pid: int) -> None:
        """Mark the daemon as running."""
        state = self.load_state()
        state.daemon_pid = pid
        state.daemon_started_at = datetime.now()
        self.save_state(state)

    def clear_daemon(self) -> None:
        """Clear daemon status."""
        state = self.load_state()
        state.daemon_pid = None
        state.daemon_started_at = None
        self.save_state(state)

    def set_dashboard_running(self, pid: int) -> None:
        """Mark the dashboard as running."""
        state = self.load_state()
        state.dashboard_pid = pid
        state.dashboard_started_at = datetime.now()
        self.save_state(state)

    def clear_dashboard(self) -> None:
        """Clear dashboard status."""
        state = self.load_state()
        state.dashboard_pid = None
        state.dashboard_started_at = None
        self.save_state(state)

    def is_daemon_running(self) -> bool:
        """Check if daemon is running."""
        state = self.load_state()
        if state.daemon_pid is None:
            return False

        # Check if process is actually running
        import os

        try:
            os.kill(state.daemon_pid, 0)
            return True
        except (OSError, ProcessLookupError):
            # Process not running, clear state
            self.clear_daemon()
            return False

    def cleanup_old_processed(self, max_age_days: int = 7, max_count: int = 10000) -> int:
        """Clean up old processed message IDs to prevent unbounded growth.

        Args:
            max_age_days: Remove entries older than this (not implemented for ts-only storage)
            max_count: Maximum number of entries to keep

        Returns:
            Number of entries removed
        """
        state = self.load_state()
        original_count = len(state.processed_messages)

        if original_count > max_count:
            # Keep only the most recent entries (sorted by timestamp)
            sorted_ts = sorted(state.processed_messages, reverse=True)
            state.processed_messages = set(sorted_ts[:max_count])
            self.save_state(state)

        return original_count - len(state.processed_messages)

    # --- Pending Response Management ---

    def add_pending_response(self, response: PendingResponse) -> str:
        """Add a pending response for manual review.

        Returns:
            The file path where the response was saved
        """
        file_path = self.pending_dir / f"{response.message_id.replace('.', '-')}.yaml"
        data = response.model_dump(mode="json")
        file_path.write_text(
            yaml.dump(data, allow_unicode=True, default_flow_style=False),
            encoding="utf-8",
        )
        return str(file_path)

    def get_pending_response(self, message_id: str) -> PendingResponse | None:
        """Get a specific pending response."""
        file_path = self.pending_dir / f"{message_id.replace('.', '-')}.yaml"
        if file_path.exists():
            data = yaml.safe_load(file_path.read_text(encoding="utf-8"))
            return PendingResponse(**data)
        return None

    def list_pending_responses(self) -> list[PendingResponse]:
        """List all pending responses."""
        responses = []
        for file_path in sorted(self.pending_dir.glob("*.yaml"), reverse=True):
            data = yaml.safe_load(file_path.read_text(encoding="utf-8"))
            if data:
                responses.append(PendingResponse(**data))
        return responses

    def remove_pending_response(self, message_id: str) -> bool:
        """Remove a pending response after approval/rejection."""
        file_path = self.pending_dir / f"{message_id.replace('.', '-')}.yaml"
        if file_path.exists():
            file_path.unlink()
            return True
        return False

    def approve_response(self, message_id: str) -> PendingResponse | None:
        """Approve and return a pending response for sending."""
        response = self.get_pending_response(message_id)
        if response:
            self.remove_pending_response(message_id)
        return response

    # --- Statistics ---

    def load_stats(self) -> PollingStats:
        """Load polling statistics."""
        if self.stats_file.exists():
            try:
                content = self.stats_file.read_text(encoding="utf-8")
                # Handle corrupted files with null characters
                if "\x00" in content:
                    # File is corrupted, reset it
                    self.stats_file.unlink()
                    return PollingStats()
                data = yaml.safe_load(content)
                if data:
                    return PollingStats(**data)
            except (yaml.YAMLError, ValueError) as e:
                # File is corrupted, log and reset
                import logging

                logging.getLogger("state").warning(f"Corrupted stats file, resetting: {e}")
                self.stats_file.unlink()
        return PollingStats()

    def save_stats(self, stats: PollingStats) -> None:
        """Save polling statistics."""
        self.stats_file.write_text(
            yaml.dump(stats.model_dump(mode="json"), allow_unicode=True),
            encoding="utf-8",
        )

    def record_poll(
        self,
        mentions_found: int,
        responses_sent: int,
        responses_pending: int,
        duration_ms: int,
    ) -> None:
        """Record statistics for a poll cycle."""
        stats = self.load_stats()
        stats.total_polls += 1
        stats.total_mentions_found += mentions_found
        stats.total_responses_sent += responses_sent
        stats.total_responses_pending += responses_pending
        stats.last_poll_duration_ms = duration_ms

        # Update running average
        if stats.total_polls > 1:
            stats.average_poll_duration_ms = (
                stats.average_poll_duration_ms * (stats.total_polls - 1) + duration_ms
            ) / stats.total_polls
        else:
            stats.average_poll_duration_ms = float(duration_ms)

        self.save_stats(stats)
