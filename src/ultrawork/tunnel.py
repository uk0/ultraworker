"""Cloudflare Tunnel integration for Ultrawork dashboard.

Starts a cloudflared quick tunnel (trycloudflare.com) and notifies Slack
with the public URL whenever the dashboard is started.
"""

from __future__ import annotations

import os
import re
import subprocess
import threading
import time
from pathlib import Path
from typing import Optional

# Cloudflared outputs the URL to stderr
_URL_PATTERN = re.compile(r"https://[a-z0-9\-]+\.trycloudflare\.com")
_CLOUDFLARED_BIN = "cloudflared"


def _find_url_in_output(stream, result: list[str], found_event: threading.Event) -> None:
    """Background thread: read cloudflared output until URL is found, then drain."""
    try:
        for line in stream:
            if not result:
                match = _URL_PATTERN.search(line)
                if match:
                    result.append(match.group())
                    found_event.set()
    except Exception:
        pass
    finally:
        found_event.set()  # Unblock caller even on error


def start_tunnel(port: int = 7878, timeout: int = 30) -> tuple[subprocess.Popen, str]:
    """Start a cloudflared quick tunnel to localhost:{port}.

    Returns:
        (process, url) tuple. Caller is responsible for terminating the process.

    Raises:
        RuntimeError: if cloudflared is not found or URL not captured within timeout.
    """
    try:
        proc = subprocess.Popen(
            [_CLOUDFLARED_BIN, "tunnel", "--url", f"http://localhost:{port}"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            text=True,
            # Detach from parent process group so cloudflared survives parent exit
            start_new_session=True,
        )
    except FileNotFoundError:
        raise RuntimeError(
            "cloudflared not found. Install with: brew install cloudflared"
        )

    result: list[str] = []
    found_event = threading.Event()
    reader = threading.Thread(
        target=_find_url_in_output,
        args=(proc.stderr, result, found_event),
        daemon=True,
    )
    reader.start()

    found_event.wait(timeout=timeout)

    if not result:
        proc.terminate()
        raise RuntimeError(
            f"cloudflared did not provide a tunnel URL within {timeout}s. "
            "Make sure the dashboard is running on the specified port."
        )

    return proc, result[0]


def notify_slack(url: str, channel_id: str, thread_ts: str = "") -> bool:
    """Post the tunnel URL to a Slack channel using the SDK.

    Uses SLACK_TOKEN + SLACK_COOKIE from environment (personal token flow).

    Returns:
        True on success, False on failure.
    """
    token = os.environ.get("SLACK_TOKEN")
    if not token:
        return False

    try:
        from slack_sdk import WebClient

        headers: dict[str, str] = {}
        cookie = os.environ.get("SLACK_COOKIE")
        if token.startswith("xoxc-") and cookie:
            cookie_value = cookie
            if cookie_value.startswith("xoxd-"):
                headers["Cookie"] = f"d={cookie_value}"
            else:
                headers["Cookie"] = cookie_value

        client = WebClient(token=token, headers=headers)

        text = (
            f":rocket: *Dashboard 터널이 열렸습니다!*\n"
            f"공개 URL: {url}\n"
            f"_(trycloudflare.com 무료 터널 · 재시작 시 URL 변경됨)_"
        )

        kwargs: dict = {"channel": channel_id, "text": text}
        if thread_ts:
            kwargs["thread_ts"] = thread_ts

        client.chat_postMessage(**kwargs)
        return True
    except Exception:
        return False


class TunnelManager:
    """Manages the lifecycle of a cloudflared tunnel process.

    Stores state in a simple JSON file alongside polling state.
    """

    def __init__(self, state_dir: Path):
        self.state_dir = Path(state_dir)
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self._state_file = self.state_dir / "tunnel_state.json"
        self._proc: Optional[subprocess.Popen] = None

    # --- State persistence ---

    def _load(self) -> dict:
        if self._state_file.exists():
            import json
            try:
                return json.loads(self._state_file.read_text())
            except Exception:
                pass
        return {}

    def _save(self, data: dict) -> None:
        import json
        self._state_file.write_text(json.dumps(data, indent=2))

    def get_url(self) -> str | None:
        """Return the current tunnel URL if running."""
        state = self._load()
        pid = state.get("pid")
        if pid is None:
            return None
        try:
            os.kill(pid, 0)
            return state.get("url")
        except (OSError, ProcessLookupError):
            self._save({})
            return None

    def is_running(self) -> bool:
        return self.get_url() is not None

    def start(
        self,
        port: int = 7878,
        notify_channel: str = "",
        notify_thread_ts: str = "",
    ) -> str:
        """Start tunnel, persist state, optionally notify Slack.

        Returns the tunnel URL.
        """
        proc, url = start_tunnel(port=port)
        self._proc = proc
        self._save({"pid": proc.pid, "url": url, "port": port})

        if notify_channel:
            notify_slack(url, notify_channel, notify_thread_ts)

        return url

    def stop(self) -> bool:
        """Stop the running tunnel. Returns True if a process was stopped."""
        state = self._load()
        pid = state.get("pid")
        stopped = False

        if pid:
            try:
                import signal
                os.kill(pid, signal.SIGTERM)
                stopped = True
            except (OSError, ProcessLookupError):
                pass

        if self._proc is not None:
            try:
                self._proc.terminate()
                stopped = True
            except Exception:
                pass
            self._proc = None

        self._save({})
        return stopped
