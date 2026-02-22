"""Slack integration for Ultrawork."""

from ultrawork.slack.block_kit import BlockKitBuilder, send_block_message
from ultrawork.slack.downloader import SlackFileDownloader, download_thread_files
from ultrawork.slack.explorer import SlackExplorer
from ultrawork.slack.interactions import InteractionHandler, parse_interaction_payload
from ultrawork.slack.monitor import SlackMonitor
from ultrawork.slack.poller import InteractivePoller, SlackPoller
from ultrawork.slack.rate_limiter import (
    MaxRetriesExceededError,
    RateLimitError,
    ResilientClient,
    SlackRateLimiter,
)
from ultrawork.slack.registry import SlackRegistry
from ultrawork.slack.responder import SlackResponder
from ultrawork.slack.state import PollingStateManager
from ultrawork.slack.reaction_approval import (
    PendingApprovalTracker,
    ReactionApprovalHandler,
)
from ultrawork.slack.uploader import SlackUploader, upload_to_slack

__all__ = [
    "BlockKitBuilder",
    "InteractionHandler",
    "InteractivePoller",
    "MaxRetriesExceededError",
    "PendingApprovalTracker",
    "PollingStateManager",
    "RateLimitError",
    "ReactionApprovalHandler",
    "ResilientClient",
    "SlackExplorer",
    "SlackFileDownloader",
    "SlackMonitor",
    "SlackPoller",
    "SlackRateLimiter",
    "SlackRegistry",
    "SlackResponder",
    "SlackUploader",
    "download_thread_files",
    "parse_interaction_payload",
    "send_block_message",
    "upload_to_slack",
]
