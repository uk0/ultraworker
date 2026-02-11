"""Dashboard package for Ultrawork."""

from __future__ import annotations

from pathlib import Path

__all__ = ["serve_dashboard"]


def serve_dashboard(
    data_dir: Path,
    log_root: Path,
    host: str = "127.0.0.1",
    port: int = 7878,
) -> None:
    """Lazy wrapper to avoid importing heavy dashboard dependencies at module import time."""
    from ultrawork.dashboard.server import serve_dashboard as _serve_dashboard

    _serve_dashboard(
        data_dir=data_dir,
        log_root=log_root,
        host=host,
        port=port,
    )
