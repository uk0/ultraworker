"""Local dashboard server for Ultrawork."""

from __future__ import annotations

import json
import os
import re
import subprocess
import threading
import time
from dataclasses import dataclass
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse

import yaml

from ultrawork.agent.session_manager import SessionManager
from ultrawork.config import get_config
from ultrawork.dashboard.worktree_parser import (
    parse_session_worktree_events,
    summarize_event_counts,
)
from ultrawork.events.interaction_logger import InteractionLogger
from ultrawork.models.agent import AgentRole, SessionStatus

try:
    from ultrawork.context.manager import ContextManager
except ModuleNotFoundError:  # pragma: no cover - optional dependency in lightweight envs
    ContextManager = None  # type: ignore[assignment]


@dataclass(frozen=True)
class DashboardConfig:
    """Runtime configuration for the dashboard server."""

    data_dir: Path
    log_root: Path
    host: str
    port: int
    refresh_seconds: float = 1.0


_process_lock = threading.Lock()
_running_processes: dict[str, subprocess.Popen[str]] = {}


def serve_dashboard(
    data_dir: Path,
    log_root: Path,
    host: str = "127.0.0.1",
    port: int = 7878,
) -> None:
    """Start the dashboard HTTP server."""

    config = DashboardConfig(
        data_dir=data_dir,
        log_root=log_root.expanduser(),
        host=host,
        port=port,
    )

    handler = _make_handler(config)
    server = ThreadingHTTPServer((host, port), handler)
    server.daemon_threads = True

    print("Ultrawork dashboard running")
    print(f"  http://{host}:{port}")
    print(f"  data_dir: {data_dir}")
    print(f"  claude_log_dir: {config.log_root}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping dashboard...")
    finally:
        server.server_close()


def _make_handler(config: DashboardConfig) -> type[BaseHTTPRequestHandler]:
    class DashboardHandler(BaseHTTPRequestHandler):
        server_version = "UltraworkDashboard/0.1"

        def do_GET(self) -> None:  # noqa: N802
            parsed = urlparse(self.path)
            if parsed.path == "/":
                self._serve_static("index.html", content_type="text/html; charset=utf-8")
                return

            if parsed.path.startswith("/static/"):
                file_name = parsed.path.replace("/static/", "", 1)
                if file_name.endswith(".css"):
                    content_type = "text/css; charset=utf-8"
                elif file_name.endswith(".js"):
                    content_type = "application/javascript; charset=utf-8"
                else:
                    content_type = "application/octet-stream"
                self._serve_static(file_name, content_type=content_type)
                return

            if parsed.path == "/api/state":
                query = parse_qs(parsed.query)
                limit = _parse_int(_first(query.get("limit")), default=5)
                self._send_json(_build_state(config, limit=limit))
                return

            if parsed.path == "/api/logs":
                query = parse_qs(parsed.query)
                session = _first(query.get("session"))
                limit = _parse_int(_first(query.get("limit")), default=200)
                payload = _build_log_snapshot(config, session=session, limit=limit)
                self._send_json(payload)
                return

            if parsed.path == "/api/stream":
                query = parse_qs(parsed.query)
                session = _first(query.get("session"))
                self._stream_logs(config, session=session)
                return

            # === Agent Session Endpoints ===
            if parsed.path == "/api/agent/sessions":
                query = parse_qs(parsed.query)
                status_filter = _first(query.get("status"))
                role_filter = _first(query.get("role"))
                limit = _parse_int(_first(query.get("limit")), default=50)
                payload = _build_agent_sessions(config, status_filter, role_filter, limit)
                self._send_json(payload)
                return

            # Match /api/agent/sessions/{id}
            session_match = re.match(r"^/api/agent/sessions/([^/]+)$", parsed.path)
            if session_match:
                session_id = session_match.group(1)
                payload = _build_agent_session_detail(config, session_id)
                self._send_json(payload)
                return

            # Match /api/agent/sessions/{id}/timeline
            timeline_match = re.match(r"^/api/agent/sessions/([^/]+)/timeline$", parsed.path)
            if timeline_match:
                session_id = timeline_match.group(1)
                payload = _build_session_timeline(config, session_id)
                self._send_json(payload)
                return

            # === Workflow Endpoints ===
            # Match /api/workflows/{session_id}/graph
            workflow_match = re.match(r"^/api/workflows/([^/]+)/graph$", parsed.path)
            if workflow_match:
                session_id = workflow_match.group(1)
                payload = _build_workflow_graph(config, session_id)
                self._send_json(payload)
                return

            # Match /api/workflows/{session_id}/stream (SSE)
            workflow_stream_match = re.match(r"^/api/workflows/([^/]+)/stream$", parsed.path)
            if workflow_stream_match:
                session_id = workflow_stream_match.group(1)
                _stream_workflow(self, config, session_id)
                return

            # === Thread Endpoints ===
            if parsed.path == "/api/threads":
                query = parse_qs(parsed.query)
                limit = _parse_int(_first(query.get("limit")), default=0)
                page = max(1, _parse_int(_first(query.get("page")), default=1))
                page_size = _parse_int(_first(query.get("page_size")), default=5)
                if limit > 0 and _first(query.get("page_size")) is None:
                    page_size = limit
                page_size = max(1, min(20, page_size))
                payload = _build_threads(
                    config,
                    page=page,
                    page_size=page_size,
                )
                self._send_json(payload)
                return

            # Match /api/threads/{channel_id}/{thread_ts}/sessions
            thread_sessions_match = re.match(
                r"^/api/threads/([^/]+)/([^/]+)/sessions$",
                parsed.path,
            )
            if thread_sessions_match:
                channel_id = unquote(thread_sessions_match.group(1))
                thread_ts = unquote(thread_sessions_match.group(2))
                payload = _build_thread_sessions(config, channel_id, thread_ts)
                self._send_json(payload)
                return

            # Match /api/threads/{channel_id}/{thread_ts}/sessions/{session_id}/worktree
            session_worktree_match = re.match(
                r"^/api/threads/([^/]+)/([^/]+)/sessions/([^/]+)/worktree$",
                parsed.path,
            )
            if session_worktree_match:
                query = parse_qs(parsed.query)
                channel_id = unquote(session_worktree_match.group(1))
                thread_ts = unquote(session_worktree_match.group(2))
                session_id = unquote(session_worktree_match.group(3))
                cursor = _parse_int(_first(query.get("cursor")), default=0)
                limit = max(0, _parse_int(_first(query.get("limit")), default=0))
                before_seq = max(0, _parse_int(_first(query.get("before_seq")), default=0))
                payload = _build_session_worktree(
                    config,
                    channel_id=channel_id,
                    thread_ts=thread_ts,
                    session_id=session_id,
                    cursor=max(0, cursor),
                    limit=limit,
                    before_seq=before_seq,
                )
                self._send_json(payload)
                return

            # Match /api/threads/{channel_id}/{thread_ts}/stream (SSE)
            thread_stream_match = re.match(
                r"^/api/threads/([^/]+)/([^/]+)/stream$",
                parsed.path,
            )
            if thread_stream_match:
                channel_id = unquote(thread_stream_match.group(1))
                thread_ts = unquote(thread_stream_match.group(2))
                _stream_thread(self, config, channel_id, thread_ts)
                return

            # === Thread Workflow Endpoints ===
            # Match /api/threads/{channel_id}/{thread_ts}/workflow
            thread_workflow_match = re.match(
                r"^/api/threads/([^/]+)/([^/]+)/workflow$", parsed.path
            )
            if thread_workflow_match:
                channel_id = thread_workflow_match.group(1)
                thread_ts = thread_workflow_match.group(2)
                payload = _build_thread_workflow(config, channel_id, thread_ts)
                self._send_json(payload)
                return

            # Match /api/threads/{channel_id}/{thread_ts}/messages
            thread_messages_match = re.match(
                r"^/api/threads/([^/]+)/([^/]+)/messages$", parsed.path
            )
            if thread_messages_match:
                channel_id = thread_messages_match.group(1)
                thread_ts = thread_messages_match.group(2)
                payload = _build_thread_messages(config, channel_id, thread_ts)
                self._send_json(payload)
                return

            # Match /api/threads/{channel_id}/{thread_ts}/memory
            thread_memory_match = re.match(r"^/api/threads/([^/]+)/([^/]+)/memory$", parsed.path)
            if thread_memory_match:
                channel_id = thread_memory_match.group(1)
                thread_ts = thread_memory_match.group(2)
                payload = _build_thread_memory(config, channel_id, thread_ts)
                self._send_json(payload)
                return

            # Match /api/threads/{channel_id}/{thread_ts}/tasks
            thread_tasks_match = re.match(r"^/api/threads/([^/]+)/([^/]+)/tasks$", parsed.path)
            if thread_tasks_match:
                channel_id = thread_tasks_match.group(1)
                thread_ts = thread_tasks_match.group(2)
                payload = _build_thread_tasks(config, channel_id, thread_ts)
                self._send_json(payload)
                return

            # === Skill Execution Endpoints ===
            if parsed.path == "/api/executions":
                query = parse_qs(parsed.query)
                session_id = _first(query.get("session_id"))
                limit = _parse_int(_first(query.get("limit")), default=50)
                payload = _build_executions(config, session_id, limit)
                self._send_json(payload)
                return

            # Match /api/executions/{id}
            exec_match = re.match(r"^/api/executions/([^/]+)$", parsed.path)
            if exec_match:
                execution_id = exec_match.group(1)
                payload = _build_execution_detail(config, execution_id)
                self._send_json(payload)
                return

            # === Feedback Endpoints ===
            if parsed.path == "/api/feedback/pending":
                payload = _build_pending_feedback(config)
                self._send_json(payload)
                return

            # Match /api/feedback/{id}
            feedback_match = re.match(r"^/api/feedback/([^/]+)$", parsed.path)
            if feedback_match:
                request_id = feedback_match.group(1)
                payload = _build_feedback_detail(config, request_id)
                self._send_json(payload)
                return

            # === Memory Endpoints ===
            # Match /api/memory/{session_id}
            memory_match = re.match(r"^/api/memory/([^/]+)$", parsed.path)
            if memory_match:
                session_id = memory_match.group(1)
                payload = _build_memory_context(config, session_id)
                self._send_json(payload)
                return

            self.send_response(404)
            self.end_headers()

        def do_POST(self) -> None:  # noqa: N802
            """Handle POST requests."""
            parsed = urlparse(self.path)
            body = _read_json_body(self)

            # Match /api/threads/{channel_id}/{thread_ts}/sessions
            create_thread_session_match = re.match(
                r"^/api/threads/([^/]+)/([^/]+)/sessions$",
                parsed.path,
            )
            if create_thread_session_match:
                channel_id = unquote(create_thread_session_match.group(1))
                thread_ts = unquote(create_thread_session_match.group(2))
                payload, status_code = _handle_create_thread_session(
                    config,
                    channel_id=channel_id,
                    thread_ts=thread_ts,
                    data=body,
                )
                self._send_json(payload, status=status_code)
                return

            # Match /api/threads/{channel_id}/{thread_ts}/sessions/{session_id}/terminate
            terminate_session_match = re.match(
                r"^/api/threads/([^/]+)/([^/]+)/sessions/([^/]+)/terminate$",
                parsed.path,
            )
            if terminate_session_match:
                channel_id = unquote(terminate_session_match.group(1))
                thread_ts = unquote(terminate_session_match.group(2))
                session_id = unquote(terminate_session_match.group(3))
                payload, status_code = _handle_terminate_thread_session(
                    config,
                    channel_id=channel_id,
                    thread_ts=thread_ts,
                    session_id=session_id,
                    data=body,
                )
                self._send_json(payload, status=status_code)
                return

            # Match /api/feedback/{id}/respond
            feedback_respond_match = re.match(r"^/api/feedback/([^/]+)/respond$", parsed.path)
            if feedback_respond_match:
                request_id = feedback_respond_match.group(1)
                payload = _handle_feedback_response(config, request_id, body)
                self._send_json(payload)
                return

            self.send_response(404)
            self.end_headers()

        def log_message(self, format: str, *args: Any) -> None:  # noqa: A003
            # Silence the default console logging.
            return

        def _serve_static(self, file_name: str, content_type: str) -> None:
            static_dir = Path(__file__).resolve().parent / "static"
            file_path = static_dir / file_name
            if not file_path.exists():
                self.send_response(404)
                self.end_headers()
                return

            content = file_path.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            self.wfile.write(content)

        def _send_json(self, payload: dict[str, Any], status: int = 200) -> None:
            data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def _stream_logs(self, cfg: DashboardConfig, session: str | None) -> None:
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Connection", "keep-alive")
            self.end_headers()

            offsets: dict[Path, int] = {}
            last_scan = 0.0

            # Initialize interaction logger for reading interactions
            interaction_logger = InteractionLogger(cfg.data_dir)
            last_interaction_count = 0

            try:
                while True:
                    now = time.time()
                    if now - last_scan > 2.0:
                        log_paths = _get_log_paths(cfg, session=session)
                        for path in log_paths:
                            offsets.setdefault(path, 0)
                        last_scan = now
                    else:
                        log_paths = list(offsets.keys())

                    events: list[dict[str, Any]] = []
                    for path in log_paths:
                        new_events = _read_new_events(path, offsets, cfg.log_root)
                        if new_events:
                            events.extend(new_events)

                    # Read new interactions
                    interactions: list[dict[str, Any]] = []
                    all_interactions = interaction_logger.get_recent(limit=100)
                    if len(all_interactions) > last_interaction_count:
                        # Get only new interactions since last read
                        interactions = all_interactions[last_interaction_count:]
                        last_interaction_count = len(all_interactions)

                    if events or interactions:
                        payload = {
                            "events": events[-200:],
                            "interactions": interactions,
                            "session": session,
                            "ts": datetime.now().isoformat(),
                        }
                        message = f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"
                        self.wfile.write(message.encode("utf-8"))
                        self.wfile.flush()

                    time.sleep(cfg.refresh_seconds)
            except (BrokenPipeError, ConnectionResetError):
                return

    return DashboardHandler


def _build_state(config: DashboardConfig, limit: int = 5) -> dict[str, Any]:
    manager = _get_context_manager(config.data_dir)
    tasks = manager.list_tasks(active_only=False)

    task_items: list[dict[str, Any]] = []
    for task in tasks[:limit]:  # Limit tasks
        stage = task.workflow.current_stage.value
        stage_info = task.workflow.stages.get(stage)
        trace = task.trace[-1] if task.trace else None
        task_items.append(
            {
                "task_id": task.task_id,
                "title": task.title,
                "stage": stage,
                "stage_status": stage_info.status.value if stage_info else "unknown",
                "type": task.workflow.type.value,
                "updated_at": task.updated_at.isoformat(),
                "trace_action": trace.action if trace else "",
                "trace_ts": trace.ts.isoformat() if trace else "",
                "thread_id": task.source.thread_id,
            }
        )

    task_items.sort(key=lambda item: item["updated_at"], reverse=True)

    context_snapshot = _build_context_snapshot(config.data_dir)
    mention_snapshot = _build_mention_snapshot(config.data_dir)
    log_index = _build_log_index(config.log_root)
    sessions = _build_sessions(config.log_root)
    requests = _build_requests(config, log_index, manager, limit=limit)

    return {
        "generated_at": datetime.now().isoformat(),
        "tasks": task_items,
        "context": context_snapshot,
        "mentions": mention_snapshot,
        "sessions": sessions,
        "requests": requests,
    }


class _NullContextManager:
    """Fallback manager used when optional context deps are unavailable."""

    def list_tasks(self, active_only: bool = False) -> list[Any]:
        _ = active_only
        return []

    def find_tasks_by_thread(self, thread_id: str) -> list[Any]:
        _ = thread_id
        return []


def _get_context_manager(data_dir: Path) -> Any:
    if ContextManager is None:
        return _NullContextManager()
    return ContextManager(data_dir)


def _build_context_snapshot(data_dir: Path) -> dict[str, Any]:
    explorations = list((data_dir / "explorations").glob("EXP-*.md"))
    specs = list((data_dir / "specs").glob("TASK-*_spec.md"))
    threads = list((data_dir / "threads").rglob("*.md"))
    tasks = list((data_dir / "tasks").glob("TASK-*.md"))

    memory_root = data_dir / "memory" / "channel_history"
    memory_channels = (
        [p for p in memory_root.iterdir() if p.is_dir() and not p.name.startswith(".")]
        if memory_root.exists()
        else []
    )
    memory_files = list(memory_root.rglob("*.yaml")) if memory_root.exists() else []

    return {
        "explorations": len(explorations),
        "specs": len(specs),
        "threads": len(threads),
        "tasks": len(tasks),
        "memory_channels": len(memory_channels),
        "memory_files": len(memory_files),
    }


def _build_mention_snapshot(data_dir: Path) -> dict[str, Any]:
    mentions_dir = data_dir / "mentions"
    pending = len(list((mentions_dir / "pending").glob("*.yaml"))) if mentions_dir.exists() else 0
    completed = (
        len(list((mentions_dir / "completed").glob("*.yaml"))) if mentions_dir.exists() else 0
    )
    failed = len(list((mentions_dir / "failed").glob("*.yaml"))) if mentions_dir.exists() else 0

    return {
        "pending": pending,
        "completed": completed,
        "failed": failed,
        "total": pending + completed + failed,
    }


def _build_sessions(log_root: Path) -> list[dict[str, Any]]:
    sessions: list[dict[str, Any]] = []

    for path in _iter_log_files(log_root):
        stat = path.stat()
        last_event = _read_last_event(path)
        last_event_summary = last_event.get("summary") if last_event else ""
        last_event_type = last_event.get("event_type") if last_event else ""
        last_event_ts = last_event.get("ts") if last_event else ""

        sessions.append(
            {
                "session_id": path.stem,
                "project": _project_name(path, log_root),
                "relative_path": _relative_path(path, log_root),
                "updated_at": datetime.fromtimestamp(stat.st_mtime).isoformat(),
                "status": _activity_status(stat.st_mtime),
                "last_event": last_event_summary,
                "last_event_type": last_event_type,
                "last_event_ts": last_event_ts,
            }
        )

    sessions.sort(key=lambda item: item["updated_at"], reverse=True)
    return sessions


def _build_requests(
    config: DashboardConfig,
    log_index: dict[str, Path],
    manager: ContextManager,
    limit: int = 5,
) -> list[dict[str, Any]]:
    mentions_root = config.data_dir / "mentions"
    if not mentions_root.exists():
        return []

    user_map, channel_map = _load_registry(config.data_dir)
    requests: list[dict[str, Any]] = []

    # Sort mention directories by modification time (newest first) and limit
    mention_dirs = [
        d
        for d in mentions_root.iterdir()
        if d.is_dir() and d.name not in {"pending", "completed", "failed"}
    ]
    mention_dirs.sort(key=lambda d: d.stat().st_mtime, reverse=True)
    mention_dirs = mention_dirs[:limit]

    for mention_dir in mention_dirs:
        input_data = _read_yaml(mention_dir / "input.yaml")
        if not input_data:
            continue

        session_data = _read_yaml(mention_dir / "session.yaml")
        response_data = _read_yaml(mention_dir / "response.yaml")

        channel_id = str(input_data.get("channel_id") or "")
        user_id = str(input_data.get("user") or "")
        message_ts = str(input_data.get("message_ts") or "")
        thread_ts = str(input_data.get("thread_ts") or message_ts)
        text = str(input_data.get("text") or "")
        created_at = str(input_data.get("created_at") or "")

        thread_id = f"{channel_id}-{thread_ts}" if channel_id and thread_ts else ""
        linked_tasks = manager.find_tasks_by_thread(thread_id) if thread_id else []
        linked_tasks.sort(key=lambda t: t.updated_at, reverse=True)
        primary_task = linked_tasks[0] if linked_tasks else None

        workflow_task = bool(
            session_data.get("workflow_task")
            or response_data.get("workflow_task")
            or input_data.get("workflow_task")
        )
        complexity = str(input_data.get("complexity") or session_data.get("complexity") or "")

        if primary_task:
            workflow_type = primary_task.workflow.type.value
            current_stage = primary_task.workflow.current_stage.value
            stage_statuses = {
                key: value.status.value for key, value in primary_task.workflow.stages.items()
            }
        else:
            workflow_type = "full" if workflow_task else "simple"
            current_stage = ""
            stage_statuses = {}

        mode = "workflow" if workflow_type == "full" else "simple"

        session_id = (
            session_data.get("session_id")
            or response_data.get("session_id")
            or input_data.get("session_id")
        )
        session_id = str(session_id) if session_id else ""
        session_candidates = _session_candidates(session_id, channel_id, thread_ts)
        resolved_session_id, log_path = _resolve_log_path(log_index, session_candidates)

        log_status = _activity_status(log_path.stat().st_mtime) if log_path else "missing"

        requests.append(
            {
                "request_id": mention_dir.name,
                "channel_id": channel_id,
                "channel_name": channel_map.get(channel_id, channel_id),
                "user_id": user_id,
                "user_name": user_map.get(user_id, user_id),
                "message_ts": message_ts,
                "thread_ts": thread_ts,
                "text": text,
                "created_at": created_at,
                "complexity": complexity,
                "mode": mode,
                "workflow_task": workflow_task,
                "workflow_type": workflow_type,
                "current_stage": current_stage,
                "stage_statuses": stage_statuses,
                "task_ids": [task.task_id for task in linked_tasks],
                "task_titles": [task.title for task in linked_tasks],
                "session_id": session_id,
                "log_session_id": resolved_session_id,
                "log_available": bool(log_path),
                "log_status": log_status,
                "log_path": _relative_path(log_path, config.log_root) if log_path else "",
                "session_status": str(session_data.get("status") or ""),
                "response_success": bool(response_data.get("success")) if response_data else None,
                "response_completed_at": str(response_data.get("completed_at") or ""),
            }
        )

    requests.sort(key=lambda item: item.get("created_at") or "", reverse=True)
    return requests


def _build_threads(
    config: DashboardConfig,
    page: int = 1,
    page_size: int = 5,
) -> dict[str, Any]:
    """Build paginated threads for the session worktree dashboard."""
    user_map, channel_map = _load_registry(config.data_dir)
    session_mgr = _get_session_manager(config)

    mention_records = _iter_mention_records(config.data_dir)
    mentions_by_thread: dict[str, list[dict[str, Any]]] = {}
    for record in mention_records:
        thread_key = str(record.get("thread_key") or "").strip()
        if not thread_key:
            continue
        mentions_by_thread.setdefault(thread_key, []).append(record)
    for items in mentions_by_thread.values():
        items.sort(key=lambda item: _to_time_value(item.get("created_at")))

    session_to_canonical_thread = _build_session_to_thread_key_map(mention_records)
    raw_thread_index = _load_thread_session_index(config.data_dir)
    canonical_thread_index = _canonicalize_thread_sessions(
        raw_thread_index,
        session_to_canonical_thread,
        session_mgr,
    )

    thread_keys = {
        key
        for key in (set(mentions_by_thread.keys()) | set(canonical_thread_index.keys()))
        if _is_valid_thread_key(key)
    }

    threads: list[dict[str, Any]] = []
    for thread_key in thread_keys:
        channel_id, thread_ts = thread_key.rsplit("_", 1)
        mentions = mentions_by_thread.get(thread_key, [])

        mention_session_ids = [
            str(item.get("session_id") or "").strip()
            for item in mentions
            if str(item.get("session_id") or "").strip()
        ]
        index_session_ids = _normalize_session_ids(canonical_thread_index.get(thread_key))
        session_ids = _unique_preserve(mention_session_ids + index_session_ids)

        session_items: list[dict[str, Any]] = []
        latest_session_text = ""
        latest_session_text_time = 0.0
        for session_id in session_ids:
            session_obj = session_mgr.get_session(session_id)
            mention_for_session = next(
                (item for item in mentions if item.get("session_id") == session_id),
                None,
            )

            status = ""
            created_at = ""
            updated_at = ""

            if session_obj:
                status = str(session_obj.status.value)
                created_at = (
                    session_obj.created_at.isoformat()
                    if session_obj.created_at
                    else str(mention_for_session.get("created_at") or "")
                )
                updated_at = (
                    session_obj.updated_at.isoformat()
                    if session_obj.updated_at
                    else created_at
                )

                if session_obj.original_message:
                    updated_ts = _to_time_value(updated_at)
                    if updated_ts >= latest_session_text_time:
                        latest_session_text = str(session_obj.original_message)
                        latest_session_text_time = updated_ts
            elif mention_for_session:
                status = str(mention_for_session.get("status") or "pending")
                created_at = str(mention_for_session.get("created_at") or "")
                updated_at = created_at

            if not created_at and mention_for_session:
                created_at = str(mention_for_session.get("created_at") or "")
            if not updated_at:
                updated_at = created_at
            if not status:
                status = "pending"

            session_items.append(
                {
                    "session_id": session_id,
                    "status": status,
                    "created_at": created_at,
                    "updated_at": updated_at,
                }
            )

        live_session_count = sum(
            1 for item in session_items if _is_live_session_status(item.get("status"))
        )
        latest_session = max(
            session_items,
            key=lambda item: _to_time_value(item.get("updated_at")),
            default=None,
        )
        latest_session_id = latest_session.get("session_id") if latest_session else None

        if mentions:
            created_at = min(mentions, key=lambda item: _to_time_value(item.get("created_at"))).get(
                "created_at", ""
            )
            updated_at = max(mentions, key=lambda item: _to_time_value(item.get("created_at"))).get(
                "created_at", ""
            )
            latest_request = max(mentions, key=lambda item: _to_time_value(item.get("created_at")))
        else:
            created_at = min(
                (item.get("created_at") for item in session_items),
                key=_to_time_value,
                default="",
            )
            updated_at = max(
                (item.get("updated_at") for item in session_items),
                key=_to_time_value,
                default="",
            )
            latest_request = None

        updated_at_candidates = [updated_at] + [
            str(item.get("updated_at") or "") for item in session_items
        ]
        updated_at = max(updated_at_candidates, key=_to_time_value, default=updated_at)

        status = _derive_thread_status(
            [str(item.get("status") or "") for item in session_items],
            [str(item.get("status") or "") for item in mentions],
        )

        participants = _unique_preserve(
            [
                str(item.get("user_id") or "")
                for item in mentions
                if str(item.get("user_id") or "").strip()
            ]
        )

        latest_mention_text = str(latest_request.get("text") or "") if latest_request else ""
        title_seed = latest_mention_text or latest_session_text
        fallback_title = f"#{channel_id} / {thread_ts}"
        title = _build_thread_title(title_seed, fallback=fallback_title)

        requests_payload = [
            {
                "request_id": item.get("request_id"),
                "message_ts": item.get("message_ts"),
                "thread_ts": item.get("thread_ts"),
                "user_id": item.get("user_id"),
                "user_name": user_map.get(str(item.get("user_id") or ""), item.get("user_id")),
                "text": item.get("text"),
                "created_at": item.get("created_at"),
                "status": item.get("status"),
                "session_id": item.get("session_id"),
            }
            for item in mentions
        ]

        threads.append(
            {
                "thread_id": f"{channel_id}-{thread_ts}",
                "thread_key": thread_key,
                "title": title,
                "channel_id": channel_id,
                "channel_name": channel_map.get(channel_id, channel_id),
                "thread_ts": thread_ts,
                "created_at": created_at,
                "updated_at": updated_at,
                "status": status,
                "request_count": len(mentions),
                "session_count": len(session_items),
                "latest_session_id": latest_session_id,
                "live_session_count": live_session_count,
                "latest_text": latest_mention_text,
                "latest_request": requests_payload[-1] if requests_payload else None,
                "participants": participants,
                "requests": requests_payload,
            }
        )

    threads.sort(key=lambda item: _to_time_value(item.get("updated_at")), reverse=True)

    total = len(threads)
    safe_page_size = max(1, min(20, page_size))
    total_pages = (total + safe_page_size - 1) // safe_page_size if total else 0
    safe_page = max(1, page)
    if total_pages and safe_page > total_pages:
        safe_page = total_pages
    elif total_pages == 0:
        safe_page = 1

    start = (safe_page - 1) * safe_page_size
    end = start + safe_page_size
    paged_threads = threads[start:end]

    return {
        "generated_at": datetime.now().isoformat(),
        "threads": paged_threads,
        "total": total,
        "page": safe_page,
        "page_size": safe_page_size,
        "total_pages": total_pages,
    }


def _iter_mention_records(data_dir: Path) -> list[dict[str, Any]]:
    """Load mention records from data/mentions/*/input.yaml."""
    mentions_root = data_dir / "mentions"
    if not mentions_root.exists():
        return []

    records: list[dict[str, Any]] = []
    for mention_dir in mentions_root.iterdir():
        if (
            not mention_dir.is_dir()
            or mention_dir.name in {"pending", "completed", "failed"}
        ):
            continue

        input_data = _read_yaml(mention_dir / "input.yaml")
        if not input_data:
            continue

        session_data = _read_yaml(mention_dir / "session.yaml")
        response_data = _read_yaml(mention_dir / "response.yaml")

        channel_id = str(input_data.get("channel_id") or "").strip()
        message_ts = str(input_data.get("message_ts") or "").strip()
        thread_ts = str(input_data.get("thread_ts") or message_ts).strip()
        if not channel_id or not thread_ts:
            continue

        session_id = str(
            session_data.get("session_id")
            or input_data.get("session_id")
            or response_data.get("session_id")
            or ""
        ).strip()

        created_at = str(
            input_data.get("created_at")
            or session_data.get("created_at")
            or response_data.get("created_at")
            or datetime.fromtimestamp(mention_dir.stat().st_mtime).isoformat()
        )

        status = _derive_mention_status(session_data, response_data)
        user_id = str(input_data.get("user") or input_data.get("user_id") or "").strip()

        records.append(
            {
                "request_id": mention_dir.name,
                "mention_dir": mention_dir.name,
                "channel_id": channel_id,
                "thread_ts": thread_ts,
                "message_ts": message_ts,
                "thread_key": f"{channel_id}_{thread_ts}",
                "user_id": user_id,
                "text": str(input_data.get("text") or ""),
                "created_at": created_at,
                "status": status,
                "session_id": session_id,
            }
        )

    records.sort(key=lambda item: _to_time_value(item.get("created_at")))
    return records


def _group_mentions_by_thread(data_dir: Path) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for record in _iter_mention_records(data_dir):
        grouped.setdefault(str(record.get("thread_key")), []).append(record)
    for items in grouped.values():
        items.sort(key=lambda item: _to_time_value(item.get("created_at")))
    return grouped


def _build_session_to_thread_key_map(
    mention_records: list[dict[str, Any]],
) -> dict[str, str]:
    mapping: dict[str, str] = {}
    for record in mention_records:
        session_id = str(record.get("session_id") or "").strip()
        thread_key = str(record.get("thread_key") or "").strip()
        if not session_id or not _is_valid_thread_key(thread_key):
            continue
        mapping[session_id] = thread_key
    return mapping


def _canonicalize_thread_sessions(
    thread_index: dict[str, Any],
    session_to_thread_key: dict[str, str],
    session_mgr: SessionManager,
) -> dict[str, list[str]]:
    canonical: dict[str, list[str]] = {}

    for raw_key, raw_value in thread_index.items():
        raw_thread_key = str(raw_key or "").strip()
        session_ids = _normalize_session_ids(raw_value)
        for session_id in session_ids:
            canonical_key = session_to_thread_key.get(session_id, "")
            if not canonical_key:
                session_obj = session_mgr.get_session(session_id)
                if session_obj and session_obj.channel_id and session_obj.thread_ts:
                    canonical_key = f"{session_obj.channel_id}_{session_obj.thread_ts}"

            if not canonical_key:
                canonical_key = raw_thread_key
            if not _is_valid_thread_key(canonical_key):
                continue
            canonical.setdefault(canonical_key, []).append(session_id)

    for thread_key, session_ids in list(canonical.items()):
        canonical[thread_key] = _unique_preserve(session_ids)

    return canonical


def _derive_mention_status(
    session_data: dict[str, Any],
    response_data: dict[str, Any],
) -> str:
    if response_data.get("success") is True:
        return "completed"
    if response_data.get("error"):
        return "failed"
    if session_data.get("status"):
        return str(session_data.get("status"))
    return "pending"


def _load_thread_session_index(data_dir: Path) -> dict[str, Any]:
    path = data_dir / "index" / "thread_sessions.yaml"
    if not path.exists():
        return {}
    payload = _read_yaml(path)
    threads = payload.get("threads") if isinstance(payload, dict) else {}
    return threads if isinstance(threads, dict) else {}


def _normalize_session_ids(value: Any) -> list[str]:
    if isinstance(value, str):
        text = value.strip()
        return [text] if text else []
    if isinstance(value, list):
        output: list[str] = []
        for item in value:
            text = str(item or "").strip()
            if text:
                output.append(text)
        return output
    return []


def _derive_thread_status(
    session_statuses: list[str],
    request_statuses: list[str],
) -> str:
    statuses = [str(status or "").lower() for status in session_statuses + request_statuses]
    if any(status in {"active", "initializing", "running"} for status in statuses):
        return "active"
    if any(status in {"waiting_feedback", "waiting", "paused"} for status in statuses):
        return "waiting"
    if any(status in {"cancelled"} for status in statuses):
        return "cancelled"
    if any(status in {"failed", "error"} for status in statuses):
        return "failed"
    if statuses and all(status in {"completed", "success"} for status in statuses):
        return "completed"
    return "pending"


def _resolve_session_status(
    primary_status: str | None,
    events: list[dict[str, Any]],
) -> str:
    normalized = str(primary_status or "").strip().lower()
    if normalized:
        if normalized in {"cancelled"}:
            return "cancelled"
        if normalized in {"error"}:
            return "failed"
        if normalized in {"running", "initializing"}:
            return "active"
        if normalized in {"waiting_feedback"}:
            return "waiting"
        if normalized in {"success", "done"}:
            return "completed"
        if normalized in {
            "active",
            "waiting",
            "completed",
            "failed",
            "pending",
            "paused",
            "cancelled",
        }:
            return normalized

    if not events:
        return "pending"

    has_error = any(
        str(event.get("kind") or "") == "tool_result"
        and str(event.get("status") or "").lower() == "error"
        for event in events
    )
    if has_error:
        return "failed"

    last_event = events[-1]
    last_kind = str(last_event.get("kind") or "")
    last_status = str(last_event.get("status") or "").lower()
    if last_status in {"running"} or last_kind == "tool_call":
        return "active"
    if last_kind == "assistant_output":
        return "completed"
    if any(
        str(event.get("kind") or "") in {"assistant_thinking", "assistant_observation"}
        for event in events
    ):
        return "active"
    return "pending"


def _build_thread_title(text: str, fallback: str) -> str:
    cleaned = re.sub(r"<@[A-Z0-9]+>", "", str(text or "")).strip()
    cleaned = re.sub(r"\s+", " ", cleaned)
    if not cleaned:
        return fallback
    if len(cleaned) <= 52:
        return cleaned
    return cleaned[:51] + "…"


def _is_valid_thread_key(value: str | None) -> bool:
    thread_key = str(value or "").strip()
    if not thread_key:
        return False
    parts = thread_key.rsplit("_", 1)
    if len(parts) != 2:
        return False
    channel_id, thread_ts = parts
    return bool(channel_id and thread_ts)


def _is_live_session_status(value: str | None) -> bool:
    status = str(value or "").strip().lower()
    return status in {"active", "initializing", "running", "waiting_feedback"}


def _to_time_value(value: Any) -> float:
    if value is None:
        return 0.0
    if isinstance(value, int | float):
        numeric = float(value)
        if numeric > 1_000_000_000_000:
            numeric = numeric / 1000.0
        return numeric if numeric > 0 else 0.0

    text = str(value).strip()
    if not text:
        return 0.0

    try:
        numeric = float(text)
        if numeric > 1_000_000_000_000:
            numeric = numeric / 1000.0
        if numeric > 1_000_000_000:
            return numeric
    except ValueError:
        pass

    iso_text = text.replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(iso_text).timestamp()
    except ValueError:
        return 0.0


def _unique_preserve(items: list[str]) -> list[str]:
    output: list[str] = []
    seen: set[str] = set()
    for item in items:
        if not item or item in seen:
            continue
        output.append(item)
        seen.add(item)
    return output


def _calculate_thread_status(
    sessions: list[Any],
    requests: list[dict[str, Any]],
) -> str:
    """Calculate overall thread status from sessions and requests.

    Priority: active > waiting > failed > completed > pending
    """
    if not sessions and not requests:
        return "pending"

    # Check session statuses first
    if sessions:
        statuses = [s.status.value for s in sessions]
        if "active" in statuses:
            return "active"
        if "waiting_feedback" in statuses:
            return "waiting"
        if "cancelled" in statuses:
            return "cancelled"
        if "failed" in statuses:
            return "failed"
        if all(s == "completed" for s in statuses):
            return "completed"

    # Fall back to request statuses
    request_statuses = [r.get("status", "pending") for r in requests]
    if "active" in request_statuses:
        return "active"
    if "waiting" in request_statuses:
        return "waiting"
    if "failed" in request_statuses:
        return "failed"
    if all(s == "completed" for s in request_statuses):
        return "completed"

    return "pending"


def _build_thread_workflow_summary(sessions: list[Any]) -> dict[str, Any]:
    """Build a summary of workflow progress for a thread."""
    if not sessions:
        return {
            "total_skills": 0,
            "completed_skills": 0,
            "current_role": None,
            "stages": [],
        }

    total_skills = 0
    completed_skills = 0
    current_role = None
    stages: list[str] = []

    for session in sessions:
        total_skills += len(session.skill_executions)
        # Count completed skills (approximate - would need to check each execution)
        completed_skills += len(session.skill_executions)
        current_role = session.current_role.value

        # Collect unique stage transitions
        for transition in session.role_transitions:
            role_name = transition.to_role.value
            if role_name not in stages:
                stages.append(role_name)

    return {
        "total_skills": total_skills,
        "completed_skills": completed_skills,
        "current_role": current_role,
        "stages": stages,
    }


def _build_thread_sessions(
    config: DashboardConfig,
    channel_id: str,
    thread_ts: str,
) -> dict[str, Any]:
    """Build session list for a thread with event summaries."""
    thread_key = f"{channel_id}_{thread_ts}"
    session_mgr = _get_session_manager(config)
    mention_records = _iter_mention_records(config.data_dir)
    mentions_by_thread: dict[str, list[dict[str, Any]]] = {}
    for record in mention_records:
        mentions_by_thread.setdefault(str(record.get("thread_key")), []).append(record)
    for items in mentions_by_thread.values():
        items.sort(key=lambda item: _to_time_value(item.get("created_at")))
    mentions = mentions_by_thread.get(thread_key, [])

    index_map = _canonicalize_thread_sessions(
        _load_thread_session_index(config.data_dir),
        _build_session_to_thread_key_map(mention_records),
        session_mgr,
    )
    mention_session_ids = [
        str(item.get("session_id") or "").strip()
        for item in mentions
        if str(item.get("session_id") or "").strip()
    ]
    index_session_ids = _normalize_session_ids(index_map.get(thread_key))
    session_ids = _unique_preserve(mention_session_ids + index_session_ids)

    sessions: list[dict[str, Any]] = []
    for session_id in session_ids:
        mention_for_session = next(
            (item for item in mentions if item.get("session_id") == session_id),
            None,
        )
        command_text = str(mention_for_session.get("text") or "") if mention_for_session else None
        command_ts = (
            str(mention_for_session.get("created_at") or "")
            if mention_for_session
            else None
        )

        events = _get_session_worktree_events(
            config=config,
            channel_id=channel_id,
            thread_ts=thread_ts,
            session_id=session_id,
            command_text=command_text,
            command_ts=command_ts,
        )
        counts = summarize_event_counts(events)

        model_status = None
        session_obj = session_mgr.get_session(session_id)
        if session_obj:
            model_status = str(session_obj.status.value)
            created_at = (
                session_obj.created_at.isoformat() if session_obj.created_at else command_ts or ""
            )
            updated_at = (
                session_obj.updated_at.isoformat() if session_obj.updated_at else created_at
            )
        else:
            model_status = str(mention_for_session.get("status") or "pending") if mention_for_session else "pending"
            created_at = command_ts or ""
            updated_at = created_at

        status = _resolve_session_status(model_status, events)

        summary_source = next(
            (
                event
                for event in reversed(events)
                if event.get("kind") in {"assistant_output", "assistant_observation"}
            ),
            events[-1] if events else None,
        )
        summary = str(summary_source.get("summary") or "") if summary_source else ""
        request_full = (
            command_text
            or (str(session_obj.original_message or "") if session_obj else "")
            or summary
            or ""
        )
        request_preview = (
            command_text
            or (str(session_obj.original_message or "") if session_obj else "")
            or ""
        )

        sessions.append(
            {
                "session_id": session_id,
                "status": status,
                "created_at": created_at,
                "updated_at": updated_at,
                "event_count": len(events),
                "event_counts": counts,
                "summary": _trim(summary, 220),
                "request_full": request_full,
                "request_preview": _trim(request_preview, 220),
                "is_live": _is_live_session_status(status),
            }
        )

    sessions.sort(key=lambda item: _to_time_value(item.get("created_at")))
    latest_session = max(
        sessions,
        key=lambda item: _to_time_value(item.get("updated_at")),
        default=None,
    )

    return {
        "channel_id": channel_id,
        "thread_ts": thread_ts,
        "thread_key": thread_key,
        "sessions": sessions,
        "latest_session_id": latest_session.get("session_id") if latest_session else None,
        "total": len(sessions),
    }


def _build_session_worktree(
    config: DashboardConfig,
    channel_id: str,
    thread_ts: str,
    session_id: str,
    cursor: int = 0,
    limit: int = 0,
    before_seq: int = 0,
) -> dict[str, Any]:
    """Build normalized worktree events for a session."""
    thread_key = f"{channel_id}_{thread_ts}"
    mention_records = _iter_mention_records(config.data_dir)
    mentions_by_thread: dict[str, list[dict[str, Any]]] = {}
    for record in mention_records:
        mentions_by_thread.setdefault(str(record.get("thread_key")), []).append(record)
    mentions = mentions_by_thread.get(thread_key, [])
    mention_for_session = next(
        (item for item in mentions if item.get("session_id") == session_id),
        None,
    )
    command_text = str(mention_for_session.get("text") or "") if mention_for_session else None
    command_ts = str(mention_for_session.get("created_at") or "") if mention_for_session else None

    events = _get_session_worktree_events(
        config=config,
        channel_id=channel_id,
        thread_ts=thread_ts,
        session_id=session_id,
        command_text=command_text,
        command_ts=command_ts,
    )

    sorted_events = sorted(events, key=lambda event: int(event.get("seq") or 0))

    # Synthetic "interaction" events are useful to render, but they must not affect the
    # streaming cursor; otherwise the cursor can advance ahead of the real log stream and
    # cause subsequent worktree events to be skipped.
    base_events = [
        event
        for event in sorted_events
        if ":interaction:" not in str(event.get("event_id") or "")
    ]
    last_seq = max((int(event.get("seq") or 0) for event in base_events), default=0)
    min_seq = min((int(event.get("seq") or 0) for event in base_events), default=0)

    filtered: list[dict[str, Any]]
    if cursor > 0:
        filtered = [
            event
            for event in sorted_events
            if ":interaction:" not in str(event.get("event_id") or "")
            and int(event.get("seq") or 0) > cursor
        ]
    elif before_seq > 0:
        older_events = [event for event in sorted_events if int(event.get("seq") or 0) < before_seq]
        if limit > 0:
            filtered = older_events[-limit:]
        else:
            filtered = older_events
    else:
        filtered = sorted_events[-limit:] if limit > 0 else sorted_events

    range_start_seq = min((int(event.get("seq") or 0) for event in filtered), default=0)
    range_end_seq = max((int(event.get("seq") or 0) for event in filtered), default=0)
    has_older = bool(filtered) and range_start_seq > min_seq

    return {
        "channel_id": channel_id,
        "thread_ts": thread_ts,
        "thread_key": thread_key,
        "session_id": session_id,
        "cursor": last_seq,
        "events": filtered,
        "total_events": len(sorted_events),
        "range_start_seq": range_start_seq,
        "range_end_seq": range_end_seq,
        "has_older": has_older,
    }


def _get_session_worktree_events(
    *,
    config: DashboardConfig,
    channel_id: str,
    thread_ts: str,
    session_id: str,
    command_text: str | None,
    command_ts: str | None,
) -> list[dict[str, Any]]:
    thread_key = f"{channel_id}_{thread_ts}"
    log_path = _resolve_session_log_path(config.log_root, session_id)
    events = parse_session_worktree_events(
        session_id=session_id,
        thread_key=thread_key,
        log_path=log_path,
        command_text=command_text,
        command_ts=command_ts,
    )

    events = _append_interaction_fallback_events(
        config=config,
        events=events,
        session_id=session_id,
        thread_key=thread_key,
        channel_id=channel_id,
        thread_ts=thread_ts,
    )

    events.sort(key=lambda event: int(event.get("seq") or 0))
    return events


def _resolve_session_log_path(log_root: Path, session_id: str) -> Path | None:
    if not log_root.exists():
        return None
    matches = [path for path in log_root.rglob(f"{session_id}.jsonl") if path.is_file()]
    if not matches:
        return None
    matches.sort(key=lambda path: path.stat().st_mtime, reverse=True)
    return matches[0]


def _append_interaction_fallback_events(
    *,
    config: DashboardConfig,
    events: list[dict[str, Any]],
    session_id: str,
    thread_key: str,
    channel_id: str,
    thread_ts: str,
) -> list[dict[str, Any]]:
    """Use interactions.jsonl as fallback/augmentation for sparse sessions."""
    interactions_path = config.data_dir / "logs" / "interactions.jsonl"
    if not interactions_path.exists():
        return events

    existing_signatures = {
        (
            str(event.get("kind") or ""),
            str(event.get("ts") or ""),
            _trim(str(event.get("preview") or ""), 120),
        )
        for event in events
    }
    existing_ids = {str(event.get("event_id") or "") for event in events}
    seq = max((int(event.get("seq") or 0) for event in events), default=0)

    mapped_entries: list[dict[str, Any]] = []
    try:
        with interactions_path.open(encoding="utf-8") as handle:
            for raw_line in handle:
                line = raw_line.strip()
                if not line:
                    continue
                try:
                    payload = json.loads(line)
                except json.JSONDecodeError:
                    continue

                if str(payload.get("session_id") or "") != session_id:
                    continue
                if str(payload.get("channel_id") or "") != channel_id:
                    continue
                if str(payload.get("thread_ts") or "") != thread_ts:
                    continue

                interaction_type = str(payload.get("type") or "")
                content = str(payload.get("content") or "")
                ts = str(payload.get("timestamp") or "")
                status = "info"
                kind = "assistant_observation"
                title = "Interaction"

                if interaction_type == "user_input":
                    kind = "user_command"
                    title = "User Command"
                    status = "ok"
                elif interaction_type == "bot_response":
                    kind = "assistant_output"
                    title = "Assistant Output"
                    status = "ok"
                elif interaction_type == "processing_started":
                    kind = "assistant_observation"
                    title = "Processing Started"
                    status = "running"
                elif interaction_type == "processing_completed":
                    kind = "assistant_observation"
                    title = "Processing Completed"
                    status = "ok"
                elif interaction_type == "processing_failed":
                    kind = "assistant_observation"
                    title = "Processing Failed"
                    status = "error"
                else:
                    continue

                signature = (kind, ts, _trim(content, 120))
                if signature in existing_signatures:
                    continue

                mapped_entries.append(
                    {
                        "kind": kind,
                        "ts": ts,
                        "status": status,
                        "title": title,
                        "summary": _trim(content, 160),
                        "preview": _trim(content, 800),
                        "raw": payload,
                    }
                )
    except OSError:
        return events

    for index, entry in enumerate(mapped_entries):
        seq += 1
        event_id = f"{session_id}:interaction:{index}"
        if event_id in existing_ids:
            continue
        events.append(
            {
                "event_id": event_id,
                "thread_key": thread_key,
                "session_id": session_id,
                "seq": seq,
                "ts": entry.get("ts") or "",
                "kind": entry.get("kind"),
                "status": entry.get("status"),
                "title": entry.get("title"),
                "summary": entry.get("summary"),
                "preview": entry.get("preview"),
                "parent_event_id": None,
                "tool_use_id": None,
                "raw": entry.get("raw") or {},
            }
        )

    return events


def _stream_thread(
    handler: Any,
    config: DashboardConfig,
    channel_id: str,
    thread_ts: str,
) -> None:
    """SSE stream for thread-level session/event updates."""
    handler.send_response(200)
    handler.send_header("Content-Type", "text/event-stream")
    handler.send_header("Cache-Control", "no-cache")
    handler.send_header("Connection", "keep-alive")
    handler.end_headers()

    session_signatures: dict[str, str] = {}
    cursors: dict[str, int] = {}
    last_heartbeat = 0.0

    try:
        while True:
            sessions_payload = _build_thread_sessions(config, channel_id, thread_ts)
            sessions = sessions_payload.get("sessions", [])
            current_session_ids = {
                str(item.get("session_id") or "") for item in sessions if item.get("session_id")
            }

            for session in sessions:
                session_id = str(session.get("session_id") or "")
                if not session_id:
                    continue

                signature = json.dumps(
                    {
                        "status": session.get("status"),
                        "updated_at": session.get("updated_at"),
                        "event_count": session.get("event_count"),
                        "event_counts": session.get("event_counts"),
                    },
                    ensure_ascii=False,
                    sort_keys=True,
                )

                if session_id not in session_signatures:
                    _emit_sse_event(handler, "session_added", session)
                elif session_signatures.get(session_id) != signature:
                    _emit_sse_event(handler, "session_updated", session)

                session_signatures[session_id] = signature

                cursor = cursors.get(session_id, 0)
                worktree = _build_session_worktree(
                    config,
                    channel_id=channel_id,
                    thread_ts=thread_ts,
                    session_id=session_id,
                    cursor=cursor,
                )
                new_events = worktree.get("events", [])
                if new_events:
                    for event in new_events:
                        _emit_sse_event(
                            handler,
                            "event_added",
                            {
                                "channel_id": channel_id,
                                "thread_ts": thread_ts,
                                "thread_key": worktree.get("thread_key"),
                                "session_id": session_id,
                                "event": event,
                            },
                        )

                cursors[session_id] = int(worktree.get("cursor") or cursor)

            removed_sessions = set(session_signatures.keys()) - current_session_ids
            for session_id in removed_sessions:
                session_signatures.pop(session_id, None)
                cursors.pop(session_id, None)

            now = time.time()
            if now - last_heartbeat >= 5.0:
                _emit_sse_event(
                    handler,
                    "heartbeat",
                    {
                        "channel_id": channel_id,
                        "thread_ts": thread_ts,
                        "ts": datetime.now().isoformat(),
                    },
                )
                last_heartbeat = now

            time.sleep(config.refresh_seconds)
    except (BrokenPipeError, ConnectionResetError):
        return


def _emit_sse_event(handler: Any, event: str, payload: dict[str, Any]) -> None:
    message = (
        f"event: {event}\n"
        f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"
    )
    handler.wfile.write(message.encode("utf-8"))
    handler.wfile.flush()


def _build_log_snapshot(
    config: DashboardConfig,
    session: str | None,
    limit: int,
) -> dict[str, Any]:
    log_paths = _get_log_paths(config, session=session)
    events: list[dict[str, Any]] = []

    for path in log_paths:
        events.extend(_read_tail_events(path, config.log_root, limit=limit))

    events.sort(key=lambda item: item.get("ts") or "", reverse=False)
    if len(events) > limit:
        events = events[-limit:]

    return {
        "session": session,
        "events": events,
    }


def _iter_log_files(log_root: Path) -> list[Path]:
    if not log_root.exists():
        return []
    return [path for path in log_root.rglob("*.jsonl") if path.is_file()]


def _build_log_index(log_root: Path) -> dict[str, Path]:
    index: dict[str, Path] = {}
    for path in _iter_log_files(log_root):
        stem = path.stem
        if stem not in index:
            index[stem] = path
            continue
        if path.stat().st_mtime > index[stem].stat().st_mtime:
            index[stem] = path
    return index


def _get_log_paths(config: DashboardConfig, session: str | None) -> list[Path]:
    if not config.log_root.exists():
        return []

    if session:
        matches = list(config.log_root.rglob(f"{session}.jsonl"))
        if matches:
            return matches
        # Allow partial match for convenience
        return [path for path in config.log_root.rglob("*.jsonl") if session in path.stem]

    return _iter_log_files(config.log_root)


def _read_last_event(path: Path) -> dict[str, Any] | None:
    try:
        size = path.stat().st_size
        if size == 0:
            return None
        chunk = 65536
        with path.open("rb") as handle:
            if size > chunk:
                handle.seek(-chunk, os.SEEK_END)
            data = handle.read().splitlines()
        for line in reversed(data):
            if not line.strip():
                continue
            event = _parse_event(line.decode("utf-8", errors="ignore"), path)
            if event:
                return event
        return None
    except OSError:
        return None


def _read_tail_events(path: Path, log_root: Path, limit: int) -> list[dict[str, Any]]:
    lines = _tail_lines(path, limit=limit)
    events: list[dict[str, Any]] = []

    for line in lines:
        event = _parse_event(line, path, log_root=log_root)
        if event:
            events.append(event)

    return events


def _read_new_events(
    path: Path,
    offsets: dict[Path, int],
    log_root: Path,
) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    try:
        current_size = path.stat().st_size
        offset = offsets.get(path, 0)
        if current_size < offset:
            offset = 0
        with path.open("rb") as handle:
            handle.seek(offset)
            data = handle.read()
            offsets[path] = handle.tell()
        if not data:
            return []
        for raw_line in data.splitlines():
            if not raw_line.strip():
                continue
            line = raw_line.decode("utf-8", errors="ignore")
            event = _parse_event(line, path, log_root=log_root)
            if event:
                events.append(event)
    except OSError:
        return []
    return events


def _tail_lines(path: Path, limit: int, block_size: int = 8192) -> list[str]:
    if limit <= 0:
        return []
    try:
        with path.open("rb") as handle:
            handle.seek(0, os.SEEK_END)
            end = handle.tell()
            buffer = b""
            while end > 0 and buffer.count(b"\n") <= limit:
                read_size = min(block_size, end)
                end -= read_size
                handle.seek(end)
                buffer = handle.read(read_size) + buffer
            lines = buffer.splitlines()[-limit:]
            return [line.decode("utf-8", errors="ignore") for line in lines]
    except OSError:
        return []


def _parse_event(line: str, path: Path, log_root: Path | None = None) -> dict[str, Any] | None:
    try:
        payload = json.loads(line)
        raw_line = None
    except json.JSONDecodeError:
        payload = {"raw_line": line.strip()}
        raw_line = line.strip()

    summary = _summarize_event(payload)
    if not summary:
        return None

    return {
        "session_id": path.stem,
        "project": _project_name(path, log_root or path.parent),
        "relative_path": _relative_path(path, log_root or path.parent),
        "event_type": summary.get("event_type", ""),
        "summary": summary.get("summary", ""),
        "ts": summary.get("ts", ""),
        "raw": summary.get("raw"),
        "payload": payload,
        "raw_line": raw_line,
    }


def _summarize_event(payload: dict[str, Any]) -> dict[str, Any]:
    if not payload:
        return {}

    event_type = str(
        payload.get("event_type")
        or payload.get("event")
        or payload.get("type")
        or payload.get("action")
        or payload.get("name")
        or ""
    )

    ts = _extract_timestamp(payload)

    summary = ""
    if "message" in payload and isinstance(payload["message"], str):
        summary = payload["message"].strip()
    elif "content" in payload and isinstance(payload["content"], str):
        summary = payload["content"].strip()
    elif "command" in payload:
        summary = f"command: {payload.get('command')}"
    elif "tool" in payload:
        summary = f"tool: {payload.get('tool')}"
    elif "status" in payload:
        summary = f"status: {payload.get('status')}"
    elif "error" in payload:
        summary = f"error: {payload.get('error')}"
    elif "raw" in payload:
        summary = str(payload.get("raw", "")).strip()

    if not summary:
        if isinstance(payload.get("event"), dict):
            event_payload = payload.get("event") or {}
            if not event_type:
                event_type = str(event_payload.get("type") or event_payload.get("name") or "")
            msg = event_payload.get("message")
            content = event_payload.get("content")
            if isinstance(msg, str):
                summary = msg.strip()
            elif isinstance(content, str):
                summary = content.strip()

    if not summary:
        for key in ("stage", "state", "detail", "info"):
            if key in payload:
                summary = f"{key}: {payload.get(key)}"
                break

    if not summary:
        if event_type:
            summary = event_type
        else:
            try:
                summary = json.dumps(payload, ensure_ascii=False)
            except TypeError:
                summary = str(payload)

    summary = _trim(summary, 240)

    return {
        "event_type": event_type or "event",
        "summary": summary,
        "ts": ts,
        "raw": payload if "raw" in payload else None,
    }


def _extract_timestamp(payload: dict[str, Any]) -> str:
    for key in ("timestamp", "ts", "time", "created_at", "createdAt"):
        if key not in payload:
            continue
        value = payload.get(key)
        if value is None:
            continue
        if isinstance(value, int | float):
            return _format_epoch(value)
        if isinstance(value, str):
            return value
    return ""


def _format_epoch(value: float) -> str:
    if value > 1_000_000_000_000:
        value = value / 1000
    try:
        return datetime.fromtimestamp(value).isoformat()
    except (OSError, OverflowError):
        return ""


def _trim(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return text[: limit - 1] + "..."


def _activity_status(last_mtime: float) -> str:
    delta = time.time() - last_mtime
    if delta < 60:
        return "live"
    if delta < 300:
        return "warm"
    return "idle"


def _project_name(path: Path, log_root: Path) -> str:
    try:
        rel = path.relative_to(log_root)
        if len(rel.parts) > 1:
            return rel.parts[0]
    except ValueError:
        pass
    return path.parent.name


def _relative_path(path: Path, log_root: Path) -> str:
    try:
        return str(path.relative_to(log_root))
    except ValueError:
        return str(path)


def _read_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except OSError:
        return {}
    return data or {}


def _load_registry(data_dir: Path) -> tuple[dict[str, str], dict[str, str]]:
    users_map: dict[str, str] = {}
    channels_map: dict[str, str] = {}

    users_file = data_dir / "registry" / "users.yaml"
    if users_file.exists():
        data = _read_yaml(users_file)
        for uid, info in (data.get("users") or {}).items():
            name = info.get("display_name") or info.get("real_name") or info.get("name") or uid
            users_map[str(uid)] = str(name)

    channels_file = data_dir / "registry" / "channels.yaml"
    if channels_file.exists():
        data = _read_yaml(channels_file)
        channels = data.get("channels") or {}
        for key, info in channels.items():
            channel_id = info.get("id")
            if not channel_id and str(key).startswith(("C", "D")):
                channel_id = key
            if not channel_id:
                continue
            name = info.get("name") or channel_id
            channels_map[str(channel_id)] = str(name)

    return users_map, channels_map


def _session_candidates(session_id: str, channel_id: str, thread_ts: str) -> list[str]:
    candidates = []
    if session_id:
        candidates.append(session_id)
    if channel_id and thread_ts:
        candidates.append(f"{channel_id}_{thread_ts.replace('.', '_')}")
        candidates.append(f"{channel_id}_{thread_ts}")
    return list(dict.fromkeys(candidates))


def _resolve_log_path(
    log_index: dict[str, Path],
    candidates: list[str],
) -> tuple[str | None, Path | None]:
    for candidate in candidates:
        if candidate in log_index:
            return candidate, log_index[candidate]
    if candidates:
        return candidates[0], None
    return None, None


def _first(values: list[str] | None) -> str | None:
    if not values:
        return None
    return values[0]


def _parse_int(value: str | None, default: int) -> int:
    if not value:
        return default
    try:
        return int(value)
    except ValueError:
        return default


def _parse_bool(value: Any, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "y", "on"}:
        return True
    if text in {"0", "false", "no", "n", "off"}:
        return False
    return default


def _read_json_body(handler: Any) -> dict[str, Any]:
    content_length = int(handler.headers.get("Content-Length", 0) or 0)
    if content_length <= 0:
        return {}
    raw = handler.rfile.read(content_length).decode("utf-8", errors="ignore")
    try:
        payload = json.loads(raw) if raw else {}
    except json.JSONDecodeError:
        payload = {}
    return payload if isinstance(payload, dict) else {}


def _normalize_context_text(text: Any) -> str:
    value = str(text or "")
    value = re.sub(r"\s+", " ", value)
    return value.strip()


def _collect_thread_context_for_manual_run(
    config: DashboardConfig,
    *,
    channel_id: str,
    thread_ts: str,
    message_limit: int = 12,
    session_limit: int = 6,
) -> dict[str, Any]:
    context: dict[str, Any] = {
        "thread_summary": "",
        "recent_messages": [],
        "recent_sessions": [],
    }

    try:
        messages_payload = _build_thread_messages(config, channel_id, thread_ts)
        recent_messages = list(messages_payload.get("messages") or [])[-max(1, message_limit) :]
        normalized_messages: list[dict[str, str]] = []
        for item in recent_messages:
            text = _normalize_context_text(item.get("text"))
            if not text:
                continue
            speaker = (
                _normalize_context_text(item.get("user_name"))
                or _normalize_context_text(item.get("user_id"))
                or ("assistant" if bool(item.get("is_bot")) else "user")
            )
            ts = _normalize_context_text(item.get("timestamp"))
            normalized_messages.append(
                {
                    "speaker": _trim(speaker, 42),
                    "ts": ts,
                    "text": _trim(text, 280),
                }
            )
        context["recent_messages"] = normalized_messages
    except Exception:
        context["recent_messages"] = []

    try:
        session_mgr = _get_session_manager(config)
        sessions = session_mgr.get_sessions_by_thread(channel_id, thread_ts)[-max(1, session_limit) :]
        recent_sessions: list[dict[str, str]] = []
        for session in sessions:
            status = (
                str(session.status.value)
                if hasattr(session, "status") and hasattr(session.status, "value")
                else str(getattr(session, "status", ""))
            )
            updated_at = (
                session.updated_at.isoformat()
                if hasattr(session, "updated_at") and session.updated_at
                else ""
            )
            recent_sessions.append(
                {
                    "session_id": str(getattr(session, "session_id", "") or ""),
                    "status": _normalize_context_text(status),
                    "updated_at": _normalize_context_text(updated_at),
                    "message": _trim(
                        _normalize_context_text(getattr(session, "original_message", "")),
                        220,
                    ),
                }
            )
        context["recent_sessions"] = recent_sessions
    except Exception:
        context["recent_sessions"] = []

    try:
        manager = _get_context_manager(config.data_dir)
        getter = getattr(manager, "get_thread_record", None)
        if callable(getter):
            thread_record = getter(channel_id, thread_ts)
            if thread_record:
                summary = _normalize_context_text(getattr(thread_record, "summary", ""))
                if not summary:
                    summary = _normalize_context_text(
                        getattr(thread_record, "messages_markdown", "")
                    )
                context["thread_summary"] = _trim(summary, 500) if summary else ""
    except Exception:
        context["thread_summary"] = context.get("thread_summary") or ""

    return context


def _build_manual_executor_prompt(
    *,
    user_message: str,
    context_bundle: dict[str, Any],
    max_chars: int = 6000,
) -> tuple[str, int]:
    request_text = str(user_message or "").strip()
    if not request_text:
        return "", 0

    lines: list[str] = []

    summary = _normalize_context_text(context_bundle.get("thread_summary"))
    if summary:
        lines.append("Thread Summary:")
        lines.append(f"- {summary}")

    recent_messages = list(context_bundle.get("recent_messages") or [])
    if recent_messages:
        lines.append("Recent Thread Messages:")
        for item in recent_messages:
            speaker = _trim(
                _normalize_context_text(item.get("speaker") or "user"),
                42,
            )
            ts = _normalize_context_text(item.get("ts"))
            text = _normalize_context_text(item.get("text"))
            if not text:
                continue
            if ts:
                lines.append(f"- [{ts}] {speaker}: {text}")
            else:
                lines.append(f"- {speaker}: {text}")

    recent_sessions = list(context_bundle.get("recent_sessions") or [])
    if recent_sessions:
        lines.append("Previous Sessions In This Thread:")
        for item in recent_sessions:
            session_id = _normalize_context_text(item.get("session_id"))
            status = _normalize_context_text(item.get("status"))
            updated_at = _normalize_context_text(item.get("updated_at"))
            message = _normalize_context_text(item.get("message"))
            meta_parts = [part for part in [session_id, status, updated_at] if part]
            meta = " | ".join(meta_parts) if meta_parts else "session"
            if message:
                lines.append(f"- ({meta}) {message}")
            else:
                lines.append(f"- ({meta})")

    context_text = "\n".join(lines).strip()
    if not context_text:
        return request_text, 0

    prefix = (
        "You are continuing work in the same Slack thread.\n"
        "Use the context below to keep continuity with prior sessions.\n\n"
        "Context:\n"
    )
    suffix = f"\n\nNew Request:\n{request_text}"
    available_context = max_chars - len(prefix) - len(suffix)
    if available_context <= 0:
        return request_text, 0

    if len(context_text) > available_context:
        context_text = _trim(context_text, available_context)

    prompt = f"{prefix}{context_text}{suffix}"
    return prompt, len(context_text)


def _handle_create_thread_session(
    config: DashboardConfig,
    *,
    channel_id: str,
    thread_ts: str,
    data: dict[str, Any],
) -> tuple[dict[str, Any], int]:
    message = str(data.get("message") or "").strip()
    user_id = str(data.get("user_id") or "dashboard_user").strip() or "dashboard_user"
    run_executor = str(data.get("run_executor") or "claude").strip().lower() or "claude"

    if not channel_id or not thread_ts:
        return {
            "ok": False,
            "error": "missing_thread",
            "message": "channel_id/thread_ts is required",
        }, 400
    if not message:
        return {
            "ok": False,
            "error": "missing_message",
            "message": "message is required",
        }, 400
    if run_executor != "claude":
        return {
            "ok": False,
            "error": "unsupported_executor",
            "message": "Only run_executor=claude is supported",
        }, 400

    session_mgr = _get_session_manager(config)
    interaction_logger = InteractionLogger(config.data_dir)

    session = session_mgr.create_session(
        channel_id=channel_id,
        thread_ts=thread_ts,
        user_id=user_id,
        message=message,
        trigger_type="manual",
    )
    session_mgr.register_thread_session(channel_id, thread_ts, session.session_id)

    context_bundle: dict[str, Any] = {}
    prompt_with_context = message
    context_applied = False
    context_chars = 0
    try:
        context_bundle = _collect_thread_context_for_manual_run(
            config,
            channel_id=channel_id,
            thread_ts=thread_ts,
        )
        prompt_with_context, context_chars = _build_manual_executor_prompt(
            user_message=message,
            context_bundle=context_bundle,
            max_chars=6000,
        )
        context_applied = bool(context_chars > 0 and prompt_with_context != message)
    except Exception:
        context_bundle = {}
        prompt_with_context = message
        context_applied = False
        context_chars = 0

    interaction_logger.log_user_input(
        session_id=session.session_id,
        channel_id=channel_id,
        thread_ts=thread_ts,
        content=message,
        user_id=user_id,
        metadata={"source": "dashboard", "mode": "manual_parallel"},
    )
    interaction_logger.log_processing_started(
        session_id=session.session_id,
        channel_id=channel_id,
        thread_ts=thread_ts,
        is_resuming=False,
        metadata={"source": "dashboard", "executor": run_executor},
    )

    started, pid, error = _start_manual_session_executor(
        config=config,
        session_id=session.session_id,
        channel_id=channel_id,
        thread_ts=thread_ts,
        message=prompt_with_context,
        executor=run_executor,
    )

    if context_bundle:
        try:
            context_snapshot = {
                "generated_at": datetime.now().isoformat(),
                "channel_id": channel_id,
                "thread_ts": thread_ts,
                "context_applied": context_applied,
                "context_chars": context_chars,
                "snapshot": context_bundle,
            }
            session_mgr.add_memory_entry(
                session.session_id,
                key="thread_context_snapshot",
                value=context_snapshot,
                summary="Thread context snapshot for manual parallel session.",
                source="dashboard",
            )
        except Exception:
            pass

    if not started and error:
        interaction_logger.log_processing_completed(
            session_id=session.session_id,
            channel_id=channel_id,
            thread_ts=thread_ts,
            success=False,
            exit_code=-1,
            metadata={"source": "dashboard", "error": error},
        )

    refreshed = session_mgr.get_session(session.session_id) or session
    session_payload = {
        "session_id": refreshed.session_id,
        "channel_id": channel_id,
        "thread_ts": thread_ts,
        "status": str(refreshed.status.value),
        "created_at": refreshed.created_at.isoformat() if refreshed.created_at else "",
        "updated_at": refreshed.updated_at.isoformat() if refreshed.updated_at else "",
        "request_full": message,
        "request_preview": _trim(message, 220),
        "summary": "",
        "event_count": 0,
        "event_counts": {
            "thinking": 0,
            "tool_call": 0,
            "tool_result": 0,
            "output": 0,
        },
        "is_live": True,
    }

    return {
        "ok": True,
        "session": session_payload,
        "run": {
            "started": started,
            "pid": pid,
            "executor": run_executor,
            "error": error,
            "context_applied": context_applied,
            "context_chars": context_chars,
        },
    }, 202


def _handle_terminate_thread_session(
    config: DashboardConfig,
    *,
    channel_id: str,
    thread_ts: str,
    session_id: str,
    data: dict[str, Any],
) -> tuple[dict[str, Any], int]:
    reason = str(data.get("reason") or "terminated_by_user").strip() or "terminated_by_user"
    force = _parse_bool(data.get("force"), default=True)
    session_mgr = _get_session_manager(config)
    session = session_mgr.get_session(session_id)

    if not session:
        return {
            "ok": False,
            "error": "session_not_found",
            "session_id": session_id,
        }, 404
    if session.channel_id != channel_id or session.thread_ts != thread_ts:
        return {
            "ok": False,
            "error": "thread_mismatch",
            "session_id": session_id,
        }, 400

    was_running = False
    terminated = False
    process: subprocess.Popen[str] | None = None

    with _process_lock:
        process = _running_processes.get(session_id)

    if process and process.poll() is None:
        was_running = True
        process.terminate()
        try:
            process.wait(timeout=3)
            terminated = True
        except subprocess.TimeoutExpired:
            if force:
                process.kill()
                try:
                    process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    pass
                terminated = process.poll() is not None
            else:
                terminated = process.poll() is not None

        if process.poll() is not None:
            with _process_lock:
                _running_processes.pop(session_id, None)

    terminal_statuses = {"completed", "failed", "cancelled"}
    current_status = str(session.status.value)
    if current_status not in terminal_statuses or was_running:
        session_mgr.cancel_session(session_id, reason=reason)
        current_status = "cancelled"

        interaction_logger = InteractionLogger(config.data_dir)
        interaction_logger.log_processing_completed(
            session_id=session_id,
            channel_id=channel_id,
            thread_ts=thread_ts,
            success=False,
            exit_code=-15,
            metadata={
                "source": "dashboard",
                "terminated": True,
                "reason": reason,
                "force": force,
                "was_running": was_running,
            },
        )

    return {
        "ok": True,
        "terminated": terminated,
        "session_id": session_id,
        "status": current_status,
        "was_running": was_running,
    }, 200


def _start_manual_session_executor(
    *,
    config: DashboardConfig,
    session_id: str,
    channel_id: str,
    thread_ts: str,
    message: str,
    executor: str,
) -> tuple[bool, int | None, str | None]:
    _ = executor  # currently claude-only

    try:
        runtime_cfg = get_config()
        claude_cmd = str(runtime_cfg.executor.claude_command or "claude")
        timeout_seconds = int(runtime_cfg.executor.agentic_timeout_seconds or 1800)
    except Exception:
        claude_cmd = "claude"
        timeout_seconds = 1800

    command = [
        claude_cmd,
        "--dangerously-skip-permissions",
        "--session-id",
        session_id,
        "-p",
        message,
    ]

    env = os.environ.copy()
    env["IS_SANDBOX"] = "1"

    try:
        process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            cwd=str(config.data_dir.parent),
            env=env,
        )
    except Exception as exc:  # pragma: no cover - environment-dependent spawn failure
        session_mgr = _get_session_manager(config)
        session_mgr.complete_session(session_id, success=False)
        return False, None, str(exc)

    with _process_lock:
        _running_processes[session_id] = process

    watcher = threading.Thread(
        target=_watch_manual_session_process,
        kwargs={
            "config": config,
            "session_id": session_id,
            "channel_id": channel_id,
            "thread_ts": thread_ts,
            "process": process,
            "timeout_seconds": timeout_seconds,
        },
        daemon=True,
    )
    watcher.start()

    return True, process.pid, None


def _watch_manual_session_process(
    *,
    config: DashboardConfig,
    session_id: str,
    channel_id: str,
    thread_ts: str,
    process: subprocess.Popen[str],
    timeout_seconds: int,
) -> None:
    exit_code = -1
    try:
        process.communicate(timeout=max(1, timeout_seconds))
        exit_code = int(process.returncode or 0)
    except subprocess.TimeoutExpired:
        process.terminate()
        try:
            process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            process.kill()
            try:
                process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                pass
        exit_code = int(process.returncode or -9)
    finally:
        with _process_lock:
            _running_processes.pop(session_id, None)

    session_mgr = _get_session_manager(config)
    interaction_logger = InteractionLogger(config.data_dir)
    session = session_mgr.get_session(session_id)
    if session and str(session.status.value).lower() == "cancelled":
        return

    if exit_code == 0:
        session_mgr.complete_session(session_id, success=True)
        interaction_logger.log_processing_completed(
            session_id=session_id,
            channel_id=channel_id,
            thread_ts=thread_ts,
            success=True,
            exit_code=0,
            metadata={"source": "dashboard", "executor": "claude"},
        )
        return

    session_mgr.complete_session(session_id, success=False)
    interaction_logger.log_processing_completed(
        session_id=session_id,
        channel_id=channel_id,
        thread_ts=thread_ts,
        success=False,
        exit_code=exit_code,
        metadata={"source": "dashboard", "executor": "claude"},
    )


# === Agent Session Helpers ===


def _get_session_manager(config: DashboardConfig) -> SessionManager:
    """Get or create SessionManager instance."""
    return SessionManager(config.data_dir)


def _build_agent_sessions(
    config: DashboardConfig,
    status_filter: str | None,
    role_filter: str | None,
    limit: int,
) -> dict[str, Any]:
    """Build agent sessions list."""
    session_mgr = _get_session_manager(config)
    sessions_data: list[dict[str, Any]] = []

    # List all session files
    sessions_dir = config.data_dir / "sessions"
    if not sessions_dir.exists():
        return {"sessions": [], "total": 0}

    session_files = sorted(
        sessions_dir.glob("*.yaml"), key=lambda p: p.stat().st_mtime, reverse=True
    )

    for session_file in session_files[: limit * 2]:  # Get extra for filtering
        session = session_mgr.get_session(session_file.stem)
        if not session:
            continue

        # Apply filters
        if status_filter and session.status.value != status_filter:
            continue
        if role_filter and session.current_role.value != role_filter:
            continue

        sessions_data.append(
            {
                "session_id": session.session_id,
                "status": session.status.value,
                "current_role": session.current_role.value,
                "channel_id": session.channel_id,
                "thread_ts": session.thread_ts,
                "user_id": session.user_id,
                "trigger_message": session.original_message[:100]
                if session.original_message
                else "",
                "started_at": session.created_at.isoformat() if session.created_at else "",
                "updated_at": session.updated_at.isoformat() if session.updated_at else "",
                "skill_count": len(session.skill_executions),
                "transition_count": len(session.role_transitions),
                "exploration_id": session.exploration_id,
                "task_id": session.task_id,
            }
        )

        if len(sessions_data) >= limit:
            break

    return {
        "sessions": sessions_data,
        "total": len(sessions_data),
        "filters": {
            "status": status_filter,
            "role": role_filter,
        },
    }


def _build_agent_session_detail(
    config: DashboardConfig,
    session_id: str,
) -> dict[str, Any]:
    """Build agent session detail."""
    session_mgr = _get_session_manager(config)
    session = session_mgr.get_session(session_id)

    if not session:
        return {"error": "Session not found", "session_id": session_id}

    return {
        "session_id": session.session_id,
        "status": session.status.value,
        "current_role": session.current_role.value,
        "channel_id": session.channel_id,
        "thread_ts": session.thread_ts,
        "user_id": session.user_id,
        "trigger_type": session.trigger_type,
        "trigger_message": session.original_message,
        "started_at": session.created_at.isoformat() if session.created_at else "",
        "updated_at": session.updated_at.isoformat() if session.updated_at else "",
        "completed_at": session.completed_at.isoformat() if session.completed_at else "",
        "exploration_id": session.exploration_id,
        "task_id": session.task_id,
        "workflow_type": session.workflow_type,
        "skill_executions": session.skill_executions,
        "role_transitions": [
            {
                "from_role": t.from_role.value if t.from_role else None,
                "to_role": t.to_role.value,
                "reason": t.reason,
                "trigger_skill": t.trigger_skill,
                "timestamp": t.timestamp.isoformat() if t.timestamp else "",
            }
            for t in session.role_transitions
        ],
        "context_memory_id": session.context_memory_id,
        "pending_feedback": session.pending_feedback,
    }


def _build_session_timeline(
    config: DashboardConfig,
    session_id: str,
) -> dict[str, Any]:
    """Build session event timeline."""
    session_mgr = _get_session_manager(config)
    session = session_mgr.get_session(session_id)

    if not session:
        return {"error": "Session not found", "session_id": session_id, "events": []}

    events: list[dict[str, Any]] = []

    # Add session start event
    if session.created_at:
        events.append(
            {
                "type": "session_start",
                "timestamp": session.created_at.isoformat(),
                "data": {
                    "trigger_type": session.trigger_type,
                    "trigger_message": session.original_message[:100]
                    if session.original_message
                    else "",
                    "initial_role": AgentRole.RESPONDER.value,
                },
            }
        )

    # Add role transitions
    for transition in session.role_transitions:
        events.append(
            {
                "type": "role_transition",
                "timestamp": transition.timestamp.isoformat() if transition.timestamp else "",
                "data": {
                    "from_role": transition.from_role.value if transition.from_role else None,
                    "to_role": transition.to_role.value,
                    "reason": transition.reason,
                    "trigger_skill": transition.trigger_skill,
                },
            }
        )

    # Add skill executions
    for exec_id in session.skill_executions:
        execution = session_mgr.get_execution(exec_id)
        if execution:
            events.append(
                {
                    "type": "skill_start",
                    "timestamp": execution.started_at.isoformat() if execution.started_at else "",
                    "data": {
                        "execution_id": execution.execution_id,
                        "skill_name": execution.skill_name,
                        "role_at_start": execution.role_at_start,
                    },
                }
            )
            if execution.completed_at:
                events.append(
                    {
                        "type": "skill_complete",
                        "timestamp": execution.completed_at.isoformat(),
                        "data": {
                            "execution_id": execution.execution_id,
                            "skill_name": execution.skill_name,
                            "status": execution.status.value,
                            "duration_ms": execution.duration_ms,
                            "role_at_end": execution.role_at_end,
                        },
                    }
                )

    # Add session completion
    if session.completed_at:
        events.append(
            {
                "type": "session_complete",
                "timestamp": session.completed_at.isoformat(),
                "data": {
                    "status": session.status.value,
                    "final_role": session.current_role.value,
                },
            }
        )

    # Sort events by timestamp
    events.sort(key=lambda e: e.get("timestamp") or "")

    return {
        "session_id": session_id,
        "events": events,
        "total": len(events),
    }


# === Workflow Helpers ===


def _build_workflow_graph(
    config: DashboardConfig,
    session_id: str,
) -> dict[str, Any]:
    """Build workflow graph for visualization."""
    session_mgr = _get_session_manager(config)

    # Try to get existing workflow graph
    graph = session_mgr.get_workflow(session_id)

    if graph:
        return {
            "graph_id": graph.graph_id,
            "session_id": graph.session_id,
            "nodes": [
                {
                    "node_id": n.node_id,
                    "node_type": n.node_type.value,
                    "label": n.label,
                    "status": n.status.value,
                    "x": n.x,
                    "y": n.y,
                    "input_nodes": n.input_nodes,
                    "output_nodes": n.output_nodes,
                    "input_data": n.input_data,
                }
                for n in graph.nodes.values()
            ],
            "created_at": graph.created_at.isoformat() if graph.created_at else "",
            "updated_at": graph.updated_at.isoformat() if graph.updated_at else "",
        }

    # Create basic graph from session if not exists
    session = session_mgr.get_session(session_id)
    if not session:
        return {"error": "Session not found", "session_id": session_id}

    # Return minimal graph structure for frontend to build
    return {
        "graph_id": f"graph-{session_id}",
        "session_id": session_id,
        "nodes": [],
        "message": "Graph not yet created. Use session timeline to visualize.",
    }


def _build_thread_workflow(
    config: DashboardConfig,
    channel_id: str,
    thread_ts: str,
) -> dict[str, Any]:
    """Build combined workflow graph for all sessions in a thread.

    This enables displaying the full collaboration flow within a thread,
    where multiple requests may have been made.
    """
    session_mgr = _get_session_manager(config)

    # Get combined graph for all sessions in the thread
    graph_data = session_mgr.get_thread_workflow_graph(channel_id, thread_ts)

    if not graph_data.get("nodes"):
        return {
            "channel_id": channel_id,
            "thread_ts": thread_ts,
            "nodes": [],
            "edges": [],
            "session_count": 0,
            "message": "No workflow data for this thread.",
        }

    return graph_data


def _build_thread_messages(
    config: DashboardConfig,
    channel_id: str,
    thread_ts: str,
) -> dict[str, Any]:
    """Build list of messages exchanged in a thread (user inputs + bot responses)."""
    messages: list[dict[str, Any]] = []

    # Decode thread_ts if URL-encoded
    import urllib.parse

    thread_ts = urllib.parse.unquote(thread_ts)

    # Read from interactions log
    interactions_log = config.data_dir / "logs" / "interactions.jsonl"
    if interactions_log.exists():
        try:
            with open(interactions_log, encoding="utf-8") as f:
                for line in f:
                    if not line.strip():
                        continue
                    try:
                        entry = json.loads(line)
                        # Match thread
                        if (
                            entry.get("channel_id") == channel_id
                            and entry.get("thread_ts") == thread_ts
                        ):
                            msg_type = entry.get("type", "")
                            if msg_type in ("user_input", "bot_response"):
                                messages.append(
                                    {
                                        "timestamp": entry.get("timestamp"),
                                        "text": entry.get("content", ""),
                                        "user_id": entry.get("user_id"),
                                        "is_bot": msg_type == "bot_response",
                                        "session_id": entry.get("session_id"),
                                    }
                                )
                    except json.JSONDecodeError:
                        continue
        except Exception:
            pass

    # Also check mentions directory for additional messages
    mentions_root = config.data_dir / "mentions"
    if mentions_root.exists():
        for mention_dir in sorted(mentions_root.iterdir()):
            input_file = mention_dir / "input.yaml"
            if input_file.exists():
                data = _read_yaml(input_file)
                if data:
                    mention_thread_ts = data.get("thread_ts") or data.get("message_ts", "")
                    if data.get("channel_id") == channel_id and mention_thread_ts == thread_ts:
                        messages.append(
                            {
                                "timestamp": data.get("created_at"),
                                "text": data.get("text", ""),
                                "user_id": data.get("user_id"),
                                "user_name": data.get("user_name"),
                                "is_bot": False,
                            }
                        )
            # Check for bot response
            response_file = mention_dir / "response.yaml"
            if response_file.exists():
                resp_data = _read_yaml(response_file)
                if resp_data:
                    input_data = _read_yaml(input_file) if input_file.exists() else {}
                    mention_thread_ts = input_data.get("thread_ts") or input_data.get(
                        "message_ts", ""
                    )
                    if (
                        input_data.get("channel_id") == channel_id
                        and mention_thread_ts == thread_ts
                    ):
                        messages.append(
                            {
                                "timestamp": resp_data.get("sent_at")
                                or resp_data.get("created_at"),
                                "text": resp_data.get("text", resp_data.get("response", "")),
                                "is_bot": True,
                            }
                        )

    # Sort by timestamp
    messages.sort(key=lambda x: x.get("timestamp") or "")

    return {
        "channel_id": channel_id,
        "thread_ts": thread_ts,
        "messages": messages,
        "total": len(messages),
    }


def _build_thread_memory(
    config: DashboardConfig,
    channel_id: str,
    thread_ts: str,
) -> dict[str, Any]:
    """Build memory context for a thread (short-term and long-term)."""
    import urllib.parse

    thread_ts = urllib.parse.unquote(thread_ts)

    short_term: list[dict[str, Any]] = []
    long_term: list[dict[str, Any]] = []

    # Find session(s) for this thread
    session_mgr = _get_session_manager(config)
    sessions = session_mgr.get_sessions_by_thread(channel_id, thread_ts)

    for session in sessions:
        # Check if session has memory data
        session_memory_dir = config.data_dir / "memory" / "sessions" / session.session_id
        if session_memory_dir.exists():
            # Short-term memory file
            short_term_file = session_memory_dir / "short_term.yaml"
            if short_term_file.exists():
                st_data = _read_yaml(short_term_file)
                if st_data and isinstance(st_data, list):
                    short_term.extend(st_data)
                elif st_data and isinstance(st_data, dict):
                    for key, value in st_data.items():
                        short_term.append(
                            {
                                "key": key,
                                "value": str(value) if not isinstance(value, str) else value,
                                "session_id": session.session_id,
                            }
                        )

            # Long-term memory file
            long_term_file = session_memory_dir / "long_term.yaml"
            if long_term_file.exists():
                lt_data = _read_yaml(long_term_file)
                if lt_data and isinstance(lt_data, list):
                    long_term.extend(lt_data)
                elif lt_data and isinstance(lt_data, dict):
                    for key, value in lt_data.items():
                        long_term.append(
                            {
                                "key": key,
                                "value": str(value) if not isinstance(value, str) else value,
                                "session_id": session.session_id,
                            }
                        )

    # Also check explorations for context
    explorations_root = config.data_dir / "explorations"
    if explorations_root.exists():
        for exp_file in sorted(explorations_root.glob("EXP-*.md"), reverse=True):
            content = exp_file.read_text(encoding="utf-8", errors="ignore")
            # Check if this exploration is related to this thread
            if channel_id in content or thread_ts in content:
                short_term.append(
                    {
                        "key": "exploration",
                        "value": exp_file.name,
                        "type": "reference",
                        "created_at": exp_file.stat().st_mtime,
                    }
                )
                break  # Only include latest related exploration

    return {
        "channel_id": channel_id,
        "thread_ts": thread_ts,
        "short_term": short_term,
        "long_term": long_term,
    }


def _build_thread_tasks(
    config: DashboardConfig,
    channel_id: str,
    thread_ts: str,
) -> dict[str, Any]:
    """Build list of tasks created from this thread."""
    import urllib.parse

    thread_ts = urllib.parse.unquote(thread_ts)

    tasks: list[dict[str, Any]] = []

    # Find session(s) for this thread
    session_mgr = _get_session_manager(config)
    sessions = session_mgr.get_sessions_by_thread(channel_id, thread_ts)
    session_ids = {s.session_id for s in sessions}

    # Check tasks directory
    tasks_root = config.data_dir / "tasks"
    if tasks_root.exists():
        for task_file in sorted(tasks_root.glob("TASK-*.md"), reverse=True):
            try:
                content = task_file.read_text(encoding="utf-8", errors="ignore")
                # Parse YAML frontmatter
                if content.startswith("---"):
                    parts = content.split("---", 2)
                    if len(parts) >= 3:
                        frontmatter = yaml.safe_load(parts[1])
                        if frontmatter:
                            # Check if task is related to this thread
                            task_channel = frontmatter.get("channel_id")
                            task_thread = frontmatter.get("thread_ts")
                            task_session = frontmatter.get("session_id")

                            is_related = (
                                (task_channel == channel_id and task_thread == thread_ts)
                                or (task_session and task_session in session_ids)
                                or (channel_id in content and thread_ts in content)
                            )

                            if is_related:
                                workflow = frontmatter.get("workflow", {})
                                stages = workflow.get("stages", {})

                                # Calculate progress
                                completed = sum(
                                    1 for s in stages.values() if s.get("status") == "approved"
                                )
                                total = len(stages) or 1
                                progress = int((completed / total) * 100)

                                tasks.append(
                                    {
                                        "task_id": frontmatter.get("task_id", task_file.stem),
                                        "title": frontmatter.get("title", "Untitled"),
                                        "status": frontmatter.get("status", "pending"),
                                        "current_stage": workflow.get("current_stage"),
                                        "workflow_type": workflow.get("type"),
                                        "progress": progress,
                                        "created_at": frontmatter.get("created_at"),
                                        "updated_at": frontmatter.get("updated_at"),
                                    }
                                )
            except Exception:
                continue

    return {
        "channel_id": channel_id,
        "thread_ts": thread_ts,
        "tasks": tasks,
        "total": len(tasks),
    }


def _stream_workflow(handler: Any, config: DashboardConfig, session_id: str) -> None:
    """Stream workflow updates via SSE."""
    handler.send_response(200)
    handler.send_header("Content-Type", "text/event-stream")
    handler.send_header("Cache-Control", "no-cache")
    handler.send_header("Connection", "keep-alive")
    handler.end_headers()

    session_mgr = _get_session_manager(config)
    last_update = ""

    try:
        while True:
            session = session_mgr.get_session(session_id)
            if not session:
                message = 'data: {"error": "Session not found"}\n\n'
                handler.wfile.write(message.encode("utf-8"))
                handler.wfile.flush()
                break

            current_update = session.updated_at.isoformat() if session.updated_at else ""

            if current_update != last_update:
                last_update = current_update

                graph = session_mgr.get_workflow(session_id)
                payload = {
                    "session_id": session_id,
                    "status": session.status.value,
                    "current_role": session.current_role.value,
                    "updated_at": current_update,
                    "skill_count": len(session.skill_executions),
                    "graph": {
                        "nodes": [
                            {
                                "node_id": n.node_id,
                                "status": n.status.value,
                            }
                            for n in graph.nodes.values()
                        ]
                        if graph
                        else [],
                    }
                    if graph
                    else None,
                }

                message = f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"
                handler.wfile.write(message.encode("utf-8"))
                handler.wfile.flush()

            # Check if session is completed
            if session.status in (SessionStatus.COMPLETED, SessionStatus.FAILED):
                break

            time.sleep(1.0)
    except (BrokenPipeError, ConnectionResetError):
        return


# === Execution Helpers ===


def _build_executions(
    config: DashboardConfig,
    session_id: str | None,
    limit: int,
) -> dict[str, Any]:
    """Build skill executions list."""
    session_mgr = _get_session_manager(config)
    executions_data: list[dict[str, Any]] = []

    executions_dir = config.data_dir / "executions"
    if not executions_dir.exists():
        return {"executions": [], "total": 0}

    exec_files = sorted(
        executions_dir.glob("*.yaml"), key=lambda p: p.stat().st_mtime, reverse=True
    )

    for exec_file in exec_files[: limit * 2]:
        execution = session_mgr.get_execution(exec_file.stem)
        if not execution:
            continue

        # Filter by session if specified
        if session_id and execution.session_id != session_id:
            continue

        executions_data.append(
            {
                "execution_id": execution.execution_id,
                "session_id": execution.session_id,
                "skill_name": execution.skill_name,
                "operation_count": len(execution.operations),
                "status": execution.status.value,
                "started_at": execution.started_at.isoformat() if execution.started_at else "",
                "completed_at": execution.completed_at.isoformat()
                if execution.completed_at
                else "",
                "duration_ms": execution.duration_ms,
                "role_at_start": execution.role_at_start,
                "role_at_end": execution.role_at_end,
            }
        )

        if len(executions_data) >= limit:
            break

    return {
        "executions": executions_data,
        "total": len(executions_data),
        "session_id": session_id,
    }


def _build_execution_detail(
    config: DashboardConfig,
    execution_id: str,
) -> dict[str, Any]:
    """Build execution detail."""
    session_mgr = _get_session_manager(config)
    execution = session_mgr.get_execution(execution_id)

    if not execution:
        return {"error": "Execution not found", "execution_id": execution_id}

    return {
        "execution_id": execution.execution_id,
        "session_id": execution.session_id,
        "skill_name": execution.skill_name,
        "operations": [
            {
                "operation_id": op.operation_id,
                "operation_type": op.operation_type,
                "name": op.name,
                "success": op.success,
                "duration_ms": op.duration_ms,
            }
            for op in execution.operations
        ],
        "status": execution.status.value,
        "started_at": execution.started_at.isoformat() if execution.started_at else "",
        "completed_at": execution.completed_at.isoformat() if execution.completed_at else "",
        "duration_ms": execution.duration_ms,
        "role_at_start": execution.role_at_start,
        "role_at_end": execution.role_at_end,
        "input_args": execution.input_args,
        "output_data": execution.output_data,
        "error_message": execution.error_message,
    }


# === Feedback Helpers ===


def _load_feedback_request(config: DashboardConfig, request_id: str) -> dict[str, Any] | None:
    """Load a feedback request from YAML file."""
    from ultrawork.models.memory import FeedbackRequest

    path = config.data_dir / "feedback" / f"{request_id}.yaml"
    if not path.exists():
        return None
    try:
        data = _read_yaml(path)
        if not data:
            return None
        request = FeedbackRequest.model_validate(data)
        return {
            "request_id": request.request_id,
            "session_id": request.session_id,
            "request_type": request.feedback_type.value,
            "title": request.title,
            "description": request.description,
            "status": request.status.value,
            "created_at": request.created_at.isoformat() if request.created_at else "",
            "responded_at": request.responded_at.isoformat() if request.responded_at else "",
            "expires_at": request.expires_at.isoformat() if request.expires_at else "",
            "options": [
                {"label": opt.label, "value": opt.option_id, "description": opt.description}
                for opt in (request.options or [])
            ],
            "response": request.response,
            "responded_by": request.responded_by,
        }
    except Exception:
        return None


def _build_pending_feedback(config: DashboardConfig) -> dict[str, Any]:
    """Build pending feedback requests list."""
    feedback_data: list[dict[str, Any]] = []

    feedback_dir = config.data_dir / "feedback"
    if not feedback_dir.exists():
        return {"requests": [], "total": 0}

    for feedback_file in feedback_dir.glob("*.yaml"):
        request_data = _load_feedback_request(config, feedback_file.stem)
        if not request_data:
            continue

        # Only include pending requests
        if request_data.get("status") != "pending":
            continue

        feedback_data.append(
            {
                "request_id": request_data["request_id"],
                "session_id": request_data.get("session_id"),
                "request_type": request_data.get("request_type"),
                "title": request_data.get("title"),
                "description": (request_data.get("description") or "")[:200],
                "created_at": request_data.get("created_at"),
                "expires_at": request_data.get("expires_at"),
                "options": request_data.get("options", []),
            }
        )

    # Sort by created_at
    feedback_data.sort(key=lambda f: f.get("created_at") or "", reverse=True)

    return {
        "requests": feedback_data,
        "total": len(feedback_data),
    }


def _build_feedback_detail(
    config: DashboardConfig,
    request_id: str,
) -> dict[str, Any]:
    """Build feedback request detail."""
    request_data = _load_feedback_request(config, request_id)

    if not request_data:
        return {"error": "Feedback request not found", "request_id": request_id}

    return request_data


def _handle_feedback_response(
    config: DashboardConfig,
    request_id: str,
    data: dict[str, Any],
) -> dict[str, Any]:
    """Handle feedback response submission."""
    session_mgr = _get_session_manager(config)

    response_value = data.get("response")
    responded_by = data.get("responded_by", "dashboard_user")

    try:
        session_mgr.respond_to_feedback(
            request_id=request_id,
            user_id=responded_by,
            approved=bool(response_value) if response_value is not None else None,
            response_text=str(response_value) if response_value else "",
        )
        return {
            "success": True,
            "request_id": request_id,
            "message": "Feedback response recorded",
        }
    except Exception as e:
        return {
            "success": False,
            "request_id": request_id,
            "error": str(e),
        }


# === Memory Helpers ===


def _build_memory_context(
    config: DashboardConfig,
    session_id: str,
) -> dict[str, Any]:
    """Build memory context for a session."""
    from ultrawork.agent.memory_manager import MemoryManager

    memory_mgr = MemoryManager(config.data_dir)
    memory = memory_mgr.get_session_memory(session_id)

    if not memory:
        return {
            "session_id": session_id,
            "memory_id": None,
            "entries": [],
            "total": 0,
            "message": "No memory found for this session",
        }

    entries_data = []
    for entry in memory.entries.values():
        entries_data.append(
            {
                "entry_id": entry.entry_id,
                "key": entry.key,
                "value": entry.value,
                "summary": entry.summary,
                "memory_type": entry.memory_type.value,
                "scope": entry.scope.value,
                "created_at": entry.created_at.isoformat() if entry.created_at else "",
                "accessed_at": entry.accessed_at.isoformat() if entry.accessed_at else "",
                "access_count": entry.access_count,
                "relevance_score": entry.relevance_score,
                "is_expired": entry.is_expired(),
            }
        )

    # Sort by relevance and access count
    entries_data.sort(
        key=lambda e: (e.get("relevance_score", 0), e.get("access_count", 0)), reverse=True
    )

    return {
        "session_id": session_id,
        "memory_id": memory.memory_id,
        "entries": entries_data,
        "total": len(entries_data),
        "by_key": list(memory.by_key.keys()),
    }
