"""Rate limiting for Slack API calls."""

import asyncio
import time
from collections import deque
from collections.abc import Callable
from typing import Any


class SlackRateLimiter:
    """Handles Slack API rate limiting with token bucket algorithm."""

    def __init__(
        self,
        max_requests_per_minute: int = 50,
        initial_backoff: float = 1.0,
        max_backoff: float = 60.0,
    ):
        """Initialize the rate limiter.

        Args:
            max_requests_per_minute: Maximum requests allowed per minute
            initial_backoff: Initial backoff time in seconds
            max_backoff: Maximum backoff time in seconds
        """
        self.max_requests_per_minute = max_requests_per_minute
        self.initial_backoff = initial_backoff
        self.max_backoff = max_backoff
        self.backoff_seconds = initial_backoff

        # Track request timestamps
        self.requests: deque[float] = deque()

    def _cleanup_old_requests(self) -> None:
        """Remove requests older than 1 minute."""
        now = time.time()
        while self.requests and self.requests[0] < now - 60:
            self.requests.popleft()

    def can_make_request(self) -> bool:
        """Check if a request can be made without waiting."""
        self._cleanup_old_requests()
        return len(self.requests) < self.max_requests_per_minute

    def get_wait_time(self) -> float:
        """Get the time to wait before next request can be made.

        Returns:
            Time in seconds to wait (0 if no wait needed)
        """
        self._cleanup_old_requests()

        if len(self.requests) < self.max_requests_per_minute:
            return 0.0

        # Calculate how long until oldest request expires
        oldest = self.requests[0]
        wait_time = 60 - (time.time() - oldest)
        return max(0.0, wait_time)

    def record_request(self) -> None:
        """Record that a request was made."""
        self.requests.append(time.time())

    async def wait_if_needed(self) -> float:
        """Wait if we're approaching the rate limit.

        Returns:
            Time waited in seconds
        """
        wait_time = self.get_wait_time()
        if wait_time > 0:
            await asyncio.sleep(wait_time)
        self.record_request()
        return wait_time

    def handle_rate_limit_error(self, retry_after: int | None = None) -> float:
        """Handle a rate limit error from Slack.

        Args:
            retry_after: Retry-After header value from Slack (if provided)

        Returns:
            Time to wait before retrying
        """
        if retry_after is not None:
            self.backoff_seconds = max(self.backoff_seconds, float(retry_after))
        else:
            # Exponential backoff
            self.backoff_seconds = min(self.backoff_seconds * 2, self.max_backoff)

        return self.backoff_seconds

    def reset_backoff(self) -> None:
        """Reset backoff after a successful request."""
        self.backoff_seconds = self.initial_backoff

    def get_stats(self) -> dict:
        """Get rate limiter statistics."""
        self._cleanup_old_requests()
        return {
            "requests_last_minute": len(self.requests),
            "max_requests_per_minute": self.max_requests_per_minute,
            "current_backoff": self.backoff_seconds,
            "available_requests": max(0, self.max_requests_per_minute - len(self.requests)),
        }


class ResilientClient:
    """Wraps operations with retry logic and rate limiting."""

    def __init__(
        self,
        rate_limiter: SlackRateLimiter | None = None,
        max_retries: int = 3,
    ):
        """Initialize the resilient client.

        Args:
            rate_limiter: Rate limiter instance (creates one if not provided)
            max_retries: Maximum number of retry attempts
        """
        self.rate_limiter = rate_limiter or SlackRateLimiter()
        self.max_retries = max_retries

    async def execute_with_retry(
        self,
        operation: Callable[..., Any],
        *args: Any,
        **kwargs: Any,
    ) -> Any:
        """Execute an operation with rate limiting and retry logic.

        Args:
            operation: Async callable to execute
            *args: Positional arguments for the operation
            **kwargs: Keyword arguments for the operation

        Returns:
            Result of the operation

        Raises:
            Exception: If all retries are exhausted
        """
        last_error = None

        for attempt in range(self.max_retries):
            try:
                # Wait for rate limiter
                await self.rate_limiter.wait_if_needed()

                # Execute operation
                result = await operation(*args, **kwargs)

                # Success - reset backoff
                self.rate_limiter.reset_backoff()
                return result

            except RateLimitError as e:
                last_error = e
                wait_time = self.rate_limiter.handle_rate_limit_error(
                    getattr(e, "retry_after", None)
                )
                await asyncio.sleep(wait_time)

            except ConnectionError as e:
                last_error = e
                # Exponential backoff for connection errors
                wait_time = 2**attempt
                await asyncio.sleep(wait_time)

            except Exception as e:
                last_error = e
                # For other errors, use basic backoff
                if attempt < self.max_retries - 1:
                    await asyncio.sleep(1)

        raise MaxRetriesExceededError(
            f"Failed after {self.max_retries} attempts: {last_error}"
        ) from last_error


class RateLimitError(Exception):
    """Raised when rate limited by Slack."""

    def __init__(self, message: str, retry_after: int | None = None):
        super().__init__(message)
        self.retry_after = retry_after


class MaxRetriesExceededError(Exception):
    """Raised when maximum retries are exhausted."""

    pass
