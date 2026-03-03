"""Agent session lifecycle management.

This module provides SessionManager for tracking and managing agent sessions,
skill executions, and workflow graphs throughout the agent lifecycle.
"""

import logging
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

import yaml

from ultrawork.models.agent import AgentRole, AgentSession, SessionStatus
from ultrawork.models.memory import (
    ContextMemory,
    FeedbackRequest,
    FeedbackStatus,
    FeedbackType,
    MemoryEntry,
    MemoryScope,
    MemoryType,
)
from ultrawork.models.skill import (
    SkillExecution,
    get_role_after_skill,
)
from ultrawork.models.workflow_node import (
    NodeStatus,
    WorkflowGraph,
    WorkflowNode,
    add_approval_node_to_graph,
    add_skill_node_to_graph,
    create_workflow_for_session,
)


class SessionManager:
    """Manages agent session lifecycle.

    SessionManager handles:
    - Session creation and state management
    - Skill execution tracking
    - Workflow graph updates
    - Context memory management
    - Feedback request handling
    - Persistence to YAML files
    """

    def __init__(self, data_dir: Path | str) -> None:
        """Initialize SessionManager.

        Args:
            data_dir: Base directory for data storage
        """
        self.data_dir = Path(data_dir)

        # Create required directories
        self.sessions_dir = self.data_dir / "sessions"
        self.executions_dir = self.data_dir / "executions"
        self.workflows_dir = self.data_dir / "workflows"
        self.memory_dir = self.data_dir / "memory" / "context"
        self.feedback_dir = self.data_dir / "feedback"

        for dir_path in [
            self.sessions_dir,
            self.executions_dir,
            self.workflows_dir,
            self.memory_dir,
            self.feedback_dir,
        ]:
            dir_path.mkdir(parents=True, exist_ok=True)

        # In-memory caches
        self._sessions: dict[str, AgentSession] = {}
        self._executions: dict[str, SkillExecution] = {}
        self._workflows: dict[str, WorkflowGraph] = {}
        self._memories: dict[str, ContextMemory] = {}
        self._feedback_requests: dict[str, FeedbackRequest] = {}

        # Current active session
        self._active_session_id: str | None = None

    # === Session Management ===

    def create_session(
        self,
        channel_id: str,
        thread_ts: str,
        user_id: str,
        message: str,
        trigger_type: Literal["mention", "manual", "scheduled"] = "mention",
        forked_from: str | None = None,
    ) -> AgentSession:
        """Create a new agent session.

        Args:
            channel_id: Slack channel ID
            thread_ts: Slack thread timestamp
            user_id: User who triggered the session
            message: Original message content
            trigger_type: How the session was triggered
            forked_from: Session ID this session is forked from (for context continuity)

        Returns:
            The created AgentSession
        """
        session_id = str(uuid.uuid4())

        session = AgentSession(
            session_id=session_id,
            trigger_type=trigger_type,
            channel_id=channel_id,
            thread_ts=thread_ts,
            user_id=user_id,
            original_message=message,
            status=SessionStatus.ACTIVE,
            current_role=AgentRole.RESPONDER,
            forked_from=forked_from,
        )

        # Create associated workflow graph
        graph = create_workflow_for_session(
            graph_id=f"graph-{session_id}",
            session_id=session_id,
            trigger_label="Slack Mention" if trigger_type == "mention" else "Manual",
            trigger_description=message[:100],
        )
        graph.activate_node("trigger")

        # Create context memory
        memory = ContextMemory(
            memory_id=f"memory-{session_id}",
            session_id=session_id,
        )

        # Store initial context
        memory.add_entry(
            MemoryEntry(
                entry_id=f"entry-{uuid.uuid4().hex[:8]}",
                memory_type=MemoryType.EPISODIC,
                scope=MemoryScope.SESSION,
                key="original_request",
                value=message,
                summary=f"Original request from user {user_id}",
                session_id=session_id,
                channel_id=channel_id,
                thread_ts=thread_ts,
                source="session_creation",
            )
        )

        # Cache and persist
        self._sessions[session_id] = session
        self._workflows[session_id] = graph
        self._memories[session_id] = memory
        self._active_session_id = session_id

        self._save_session(session)
        self._save_workflow(graph)
        self._save_memory(memory)

        return session

    def get_session(self, session_id: str) -> AgentSession | None:
        """Get a session by ID.

        Args:
            session_id: Session ID

        Returns:
            The AgentSession or None if not found
        """
        if session_id in self._sessions:
            return self._sessions[session_id]

        # Try loading from disk
        session = self._load_session(session_id)
        if session:
            self._sessions[session_id] = session
        return session

    def get_active_session(self) -> AgentSession | None:
        """Get the currently active session."""
        if self._active_session_id:
            return self.get_session(self._active_session_id)
        return None

    # === Thread-based Session Lookup ===

    def _make_thread_key(self, channel_id: str, thread_ts: str) -> str:
        """Create thread key for indexing.

        Args:
            channel_id: Slack channel ID
            thread_ts: Slack thread timestamp

        Returns:
            Thread key in format: {channel_id}_{thread_ts}
        """
        return f"{channel_id}_{thread_ts}"

    def _load_thread_index(self) -> dict:
        """Load thread-to-session index from disk.

        Returns:
            Index dictionary with 'threads' mapping
        """
        index_path = self.data_dir / "index" / "thread_sessions.yaml"
        if index_path.exists():
            with open(index_path) as f:
                raw = yaml.safe_load(f) or {}
                threads = raw.get("threads")
                if not isinstance(threads, dict):
                    raw["threads"] = {}
                return raw
        return {"threads": {}}

    def _save_thread_index(self, index: dict) -> None:
        """Save thread-to-session index to disk.

        Args:
            index: Index dictionary to save
        """
        index_path = self.data_dir / "index" / "thread_sessions.yaml"
        index_path.parent.mkdir(parents=True, exist_ok=True)
        index["updated_at"] = datetime.now().isoformat()
        with open(index_path, "w") as f:
            yaml.safe_dump(index, f, allow_unicode=True, sort_keys=False)

    def get_session_by_thread(self, channel_id: str, thread_ts: str) -> AgentSession | None:
        """Get existing session for a Slack thread.

        This enables session resumption within the same thread.
        When a user sends follow-up mentions in the same thread,
        we can resume the existing session instead of creating a new one.

        Args:
            channel_id: Slack channel ID
            thread_ts: Slack thread timestamp

        Returns:
            The AgentSession if found, None otherwise
        """
        thread_key = self._make_thread_key(channel_id, thread_ts)
        index = self._load_thread_index()
        session_data = index.get("threads", {}).get(thread_key)

        if isinstance(session_data, str):
            session_ids = [session_data]
        elif isinstance(session_data, list):
            session_ids = [str(sid) for sid in session_data if sid]
        else:
            session_ids = []

        # Return the latest valid session for this thread.
        for session_id in reversed(session_ids):
            session = self.get_session(session_id)
            if session:
                return session
        return None

    def get_forkable_session_for_thread(
        self, channel_id: str, thread_ts: str
    ) -> AgentSession | None:
        """Get the most recent completed/failed session for forking.

        Returns the latest session in this thread that is in a terminal
        state (completed or failed). Active sessions are excluded to
        avoid data races in Claude's conversation storage.
        """
        forkable = {SessionStatus.COMPLETED, SessionStatus.FAILED}
        thread_key = self._make_thread_key(channel_id, thread_ts)
        index = self._load_thread_index()
        session_data = index.get("threads", {}).get(thread_key)

        if isinstance(session_data, str):
            session_ids = [session_data]
        elif isinstance(session_data, list):
            session_ids = [str(sid) for sid in session_data if sid]
        else:
            return None

        for session_id in reversed(session_ids):
            session = self.get_session(session_id)
            if session and session.status in forkable:
                return session
        return None

    def register_thread_session(self, channel_id: str, thread_ts: str, session_id: str) -> None:
        """Register a thread-to-session mapping.

        This allows looking up sessions by thread for resumption.

        Args:
            channel_id: Slack channel ID
            thread_ts: Slack thread timestamp
            session_id: Session ID to map
        """
        thread_key = self._make_thread_key(channel_id, thread_ts)
        index = self._load_thread_index()

        threads = index.setdefault("threads", {})
        existing = threads.get(thread_key)

        if isinstance(existing, str):
            session_ids = [existing]
        elif isinstance(existing, list):
            session_ids = [str(sid) for sid in existing if sid]
        else:
            session_ids = []

        if session_id not in session_ids:
            session_ids.append(session_id)

        threads[thread_key] = session_ids
        self._save_thread_index(index)

    def unregister_thread_session(self, channel_id: str, thread_ts: str) -> bool:
        """Remove a thread-to-session mapping.

        Args:
            channel_id: Slack channel ID
            thread_ts: Slack thread timestamp

        Returns:
            True if removed, False if not found
        """
        thread_key = self._make_thread_key(channel_id, thread_ts)
        index = self._load_thread_index()
        if thread_key in index.get("threads", {}):
            del index["threads"][thread_key]
            self._save_thread_index(index)
            return True
        return False

    def get_sessions_by_thread(self, channel_id: str, thread_ts: str) -> list[AgentSession]:
        """Get all sessions for a Slack thread (sorted by creation time).

        This enables displaying the full collaboration flow within a thread,
        where multiple requests may have been made.

        Args:
            channel_id: Slack channel ID
            thread_ts: Slack thread timestamp

        Returns:
            List of AgentSessions sorted by creation time
        """
        thread_key = self._make_thread_key(channel_id, thread_ts)
        index = self._load_thread_index()
        session_data = index.get("threads", {}).get(thread_key)

        if not session_data:
            return []

        # Handle both single session ID (legacy) and list of session IDs
        if isinstance(session_data, str):
            session_ids = [session_data]
        elif isinstance(session_data, list):
            session_ids = [str(sid) for sid in session_data if sid]
        else:
            session_ids = []

        sessions = []
        for sid in session_ids:
            session = self.get_session(sid)
            if session:
                sessions.append(session)

        # Sort by creation time
        return sorted(sessions, key=lambda s: s.created_at)

    def get_thread_workflow_graph(self, channel_id: str, thread_ts: str) -> dict[str, Any]:
        """Build a combined workflow graph for all sessions in a thread.

        This creates a unified view of the entire collaboration flow,
        connecting multiple sessions with thread_continuation edges.

        Args:
            channel_id: Slack channel ID
            thread_ts: Slack thread timestamp

        Returns:
            Dictionary with nodes, edges, and thread metadata
        """
        sessions = self.get_sessions_by_thread(channel_id, thread_ts)

        all_nodes: list[dict[str, Any]] = []
        all_edges: list[dict[str, Any]] = []
        prev_output_node_id: str | None = None

        for session_idx, session in enumerate(sessions):
            # Get workflow graph for this session
            graph = self.get_workflow(session.session_id)
            if not graph:
                continue

            vis_data = graph.to_visualization_data()
            session_nodes = vis_data.get("nodes", [])
            session_edges = vis_data.get("edges", [])

            # Add session metadata to nodes
            for node in session_nodes:
                node["session_id"] = session.session_id
                node["session_index"] = session_idx

            all_nodes.extend(session_nodes)
            all_edges.extend(session_edges)

            # Connect previous session's output to this session's trigger
            if prev_output_node_id and session_nodes:
                # Find trigger node in this session
                trigger_node = next(
                    (n for n in session_nodes if n.get("type") == "trigger"),
                    None,
                )
                if trigger_node:
                    all_edges.append(
                        {
                            "from": prev_output_node_id,
                            "to": trigger_node["id"],
                            "type": "thread_continuation",
                        }
                    )

            # Find last respond/output node for next session connection
            respond_nodes = [n for n in session_nodes if n.get("type") == "respond"]
            if respond_nodes:
                prev_output_node_id = respond_nodes[-1]["id"]
            else:
                # Fallback to last completed node
                completed = [n for n in session_nodes if n.get("status") == "completed"]
                if completed:
                    prev_output_node_id = completed[-1]["id"]

        return {
            "nodes": all_nodes,
            "edges": all_edges,
            "thread_ts": thread_ts,
            "channel_id": channel_id,
            "session_count": len(sessions),
        }

    def update_session_status(self, session_id: str, status: SessionStatus) -> bool:
        """Update session status.

        Args:
            session_id: Session ID
            status: New status

        Returns:
            True if updated successfully
        """
        session = self.get_session(session_id)
        if not session:
            return False

        session.status = status
        session.updated_at = datetime.now()
        self._save_session(session)
        return True

    def complete_session(self, session_id: str, success: bool = True) -> bool:
        """Mark a session as completed.

        Args:
            session_id: Session ID
            success: Whether session completed successfully

        Returns:
            True if completed successfully
        """
        session = self.get_session(session_id)
        if not session:
            return False

        session.complete(success)
        self._save_session(session)

        # Complete workflow trigger
        graph = self.get_workflow(session_id)
        if graph:
            graph.complete_node("trigger")
            self._save_workflow(graph)

        if self._active_session_id == session_id:
            self._active_session_id = None

        # Save LTM records on successful session completion
        if success:
            self._save_session_ltm(session)

        return True

    def _save_session_ltm(self, session: AgentSession) -> None:
        """Save RequestRecord + WorkRecord to LTM when a session completes.

        This is the primary programmatic path for LTM saves, triggered by
        complete_session() which the SDK poller calls after subprocess finishes.
        """
        try:
            from ultrawork.agent.memory_manager import MemoryManager
            from ultrawork.memory.save_policy import SaveContext

            mm = MemoryManager(self.data_dir)

            # 1. Save RequestRecord (the original request)
            req = mm.create_request_record(
                who=session.user_id or "unknown",
                where=session.channel_id or "unknown",
                what=session.original_message[:200] if session.original_message else "No message",
            )
            req_ctx = SaveContext(
                record_type="request",
                content_summary=session.original_message[:200] if session.original_message else "",
                is_novel=True,
                led_to_decision=True,
                scope="cross_session",
            )
            mm.commit_record(req, req_ctx)

            # 2. Save WorkRecord (the execution result)
            outputs = [v for v in [
                f"exploration:{session.exploration_id}" if session.exploration_id else "",
                f"task:{session.task_id}" if session.task_id else "",
            ] if v]
            work = mm.create_work_record(
                request_id=req.id,
                step_id="session_complete",
                who="claude",
                why_kind="advance_step",
                immediate_goal=f"Session processing: {session.original_message[:100]}",
                actions=[{"action": "session_processing", "output": f"status={session.status.value}"}],
                outputs=outputs,
            )
            work_ctx = SaveContext(
                record_type="work",
                content_summary=f"Session {session.session_id}: {session.original_message[:100]}",
                is_novel=True,
                led_to_decision=True,
                scope="cross_session",
            )
            mm.commit_record(work, work_ctx)

        except Exception:
            logging.getLogger("ultrawork.session_manager").warning(
                "LTM session save failed", exc_info=True
            )

    def cancel_session(self, session_id: str, reason: str = "") -> bool:
        """Mark a session as cancelled.

        Args:
            session_id: Session ID
            reason: Optional cancellation reason

        Returns:
            True if cancelled successfully
        """
        session = self.get_session(session_id)
        if not session:
            return False

        session.status = SessionStatus.CANCELLED
        session.completed_at = datetime.now()
        session.updated_at = datetime.now()
        self._save_session(session)

        graph = self.get_workflow(session_id)
        if graph:
            try:
                trigger_node = graph.nodes.get("trigger")
                if trigger_node and trigger_node.status == NodeStatus.ACTIVE:
                    graph.fail_node("trigger", reason or "Session cancelled")
                    self._save_workflow(graph)
            except Exception:
                # Keep cancellation robust even if workflow graph is partially missing.
                pass

        if self._active_session_id == session_id:
            self._active_session_id = None

        return True

    # === Role Management ===

    def transition_role(
        self,
        session_id: str,
        new_role: AgentRole,
        reason: str = "",
        trigger_skill: str | None = None,
    ) -> bool:
        """Transition session to a new role.

        Args:
            session_id: Session ID
            new_role: New role to transition to
            reason: Reason for transition
            trigger_skill: Skill that triggered the transition

        Returns:
            True if transitioned successfully
        """
        session = self.get_session(session_id)
        if not session:
            return False

        # Record transition
        session.transition_role(new_role, reason)
        if trigger_skill:
            session.role_transitions[-1].trigger_skill = trigger_skill

        self._save_session(session)
        return True

    # === Skill Execution Tracking ===

    def start_skill_execution(
        self,
        session_id: str,
        skill_name: str,
        input_args: dict[str, Any] | None = None,
    ) -> SkillExecution:
        """Start tracking a skill execution.

        Args:
            session_id: Parent session ID
            skill_name: Name of the skill
            input_args: Input arguments for the skill

        Returns:
            The created SkillExecution
        """
        execution_id = f"exec-{uuid.uuid4().hex[:12]}"

        session = self.get_session(session_id)
        current_role = session.current_role.value if session else ""

        execution = SkillExecution(
            execution_id=execution_id,
            session_id=session_id,
            skill_name=skill_name,
            input_args=input_args or {},
            role_at_start=current_role,
        )
        execution.start()

        # Add to session
        if session:
            session.add_skill_execution(execution_id)
            self._save_session(session)

        # Update workflow graph
        graph = self.get_workflow(session_id)
        if graph:
            # Find last completed or active node
            connect_from = None
            if graph.completed_nodes:
                connect_from = graph.completed_nodes[-1]
            elif graph.active_nodes:
                connect_from = graph.active_nodes[-1]

            node = add_skill_node_to_graph(
                graph,
                node_id=f"skill-{execution_id}",
                skill_name=skill_name,
                skill_execution_id=execution_id,
                connect_from=connect_from,
            )
            graph.activate_node(node.node_id)
            graph.auto_layout_nodes()
            self._save_workflow(graph)

        self._executions[execution_id] = execution
        self._save_execution(execution)

        return execution

    def complete_skill_execution(
        self,
        execution_id: str,
        output_data: dict[str, Any] | None = None,
        error: str | None = None,
    ) -> bool:
        """Complete a skill execution.

        Args:
            execution_id: Execution ID
            output_data: Output data from the skill
            error: Error message if failed

        Returns:
            True if completed successfully
        """
        execution = self._executions.get(execution_id)
        if not execution:
            execution = self._load_execution(execution_id)
            if not execution:
                return False

        if error:
            execution.fail(error)
        else:
            execution.complete(output_data)

        # Get session for role transition
        session = self.get_session(execution.session_id)
        if session:
            execution.role_at_end = session.current_role.value

            # Check for role transition
            if not error:
                new_role = get_role_after_skill(execution.skill_name, session.current_stage)
                if new_role:
                    self.transition_role(
                        execution.session_id,
                        AgentRole(new_role),
                        reason=f"Completed skill: {execution.skill_name}",
                        trigger_skill=execution.skill_name,
                    )
                    execution.role_at_end = new_role

        # Update workflow graph
        graph = self.get_workflow(execution.session_id)
        if graph:
            node_id = f"skill-{execution_id}"
            if error:
                graph.fail_node(node_id, error)
            else:
                graph.complete_node(node_id, output_data)
            self._save_workflow(graph)

        self._save_execution(execution)

        # LTM backup: save a WorkRecord as safety net for prompt-level /remember
        if not error:
            self._save_ltm_backup(execution)

        return True

    def _save_ltm_backup(self, execution: SkillExecution) -> None:
        """Save a WorkRecord as backup when prompt-level /remember is skipped.

        This ensures at least minimal LTM records exist for every completed
        skill execution, even if the Claude subprocess didn't invoke /remember.
        """
        try:
            from ultrawork.agent.memory_manager import MemoryManager
            from ultrawork.memory.save_policy import SaveContext

            mm = MemoryManager(self.data_dir)

            # Build a concise summary from execution data
            summary = f"Skill execution: {execution.skill_name}"
            if execution.output_data:
                out_keys = list(execution.output_data.keys())[:3]
                summary += f" (output keys: {', '.join(out_keys)})"

            # Determine the session user for `who`
            session = self.get_session(execution.session_id)
            who = session.user_id if session else "system"

            record = mm.create_work_record(
                request_id="auto",
                step_id=execution.skill_name,
                who=who,
                why_kind="advance_step",
                immediate_goal=summary,
                actions=[
                    {"action": execution.skill_name, "output": str(execution.output_data)[:200]}
                ],
                inputs=list(execution.input_args.keys())[:5] if execution.input_args else [],
                outputs=execution.artifacts[:5] if execution.artifacts else [],
                evidence=[],
            )
            save_ctx = SaveContext(
                record_type="work",
                content_summary=summary,
                is_novel=True,
                led_to_decision=True,
                scope="cross_session",
                related_record_count=0,
            )
            mm.commit_record(record, save_ctx)
        except Exception:
            # Backup failure must never break main flow
            logging.getLogger("ultrawork.session_manager").warning(
                "LTM backup save failed", exc_info=True
            )

    def get_execution(self, execution_id: str) -> SkillExecution | None:
        """Get a skill execution by ID."""
        if execution_id in self._executions:
            return self._executions[execution_id]
        return self._load_execution(execution_id)

    def add_operation_to_execution(
        self,
        execution_id: str,
        operation_type: str,
        name: str,
        input_summary: str = "",
        output_summary: str = "",
        duration_ms: int = 0,
        success: bool = True,
        error: str | None = None,
    ) -> bool:
        """Add an operation to a skill execution.

        Args:
            execution_id: Execution ID
            operation_type: Type of operation
            name: Operation name
            input_summary: Input summary
            output_summary: Output summary
            duration_ms: Duration in milliseconds
            success: Whether operation succeeded
            error: Error message if failed

        Returns:
            True if added successfully
        """
        execution = self._executions.get(execution_id)
        if not execution:
            return False

        operation_id = f"op-{uuid.uuid4().hex[:8]}"
        execution.add_operation(
            operation_id=operation_id,
            operation_type=operation_type,
            name=name,
            input_summary=input_summary,
            output_summary=output_summary,
            duration_ms=duration_ms,
            success=success,
            error=error,
        )
        self._save_execution(execution)
        return True

    # === Workflow Graph ===

    def get_workflow(self, session_id: str) -> WorkflowGraph | None:
        """Get workflow graph for a session."""
        if session_id in self._workflows:
            return self._workflows[session_id]
        return self._load_workflow(session_id)

    def add_approval_node(
        self,
        session_id: str,
        node_id: str,
        label: str,
        description: str = "",
        connect_from: str | None = None,
    ) -> WorkflowNode | None:
        """Add an approval node to the workflow.

        Args:
            session_id: Session ID
            node_id: Unique node ID
            label: Display label
            description: Node description
            connect_from: Node to connect from

        Returns:
            The created WorkflowNode or None
        """
        graph = self.get_workflow(session_id)
        if not graph:
            return None

        node = add_approval_node_to_graph(graph, node_id, label, description, connect_from)
        graph.auto_layout_nodes()
        self._save_workflow(graph)
        return node

    def update_node_status(
        self,
        session_id: str,
        node_id: str,
        status: NodeStatus,
        output_data: dict[str, Any] | None = None,
    ) -> bool:
        """Update workflow node status.

        Args:
            session_id: Session ID
            node_id: Node ID
            status: New status
            output_data: Optional output data

        Returns:
            True if updated successfully
        """
        graph = self.get_workflow(session_id)
        if not graph or node_id not in graph.nodes:
            return False

        if status == NodeStatus.ACTIVE:
            graph.activate_node(node_id)
        elif status == NodeStatus.COMPLETED:
            graph.complete_node(node_id, output_data)
        elif status == NodeStatus.FAILED:
            graph.fail_node(node_id)
        elif status == NodeStatus.WAITING:
            graph.nodes[node_id].wait_for_input()
        elif status == NodeStatus.SKIPPED:
            graph.nodes[node_id].skip()

        self._save_workflow(graph)
        return True

    # === Feedback Requests ===

    def create_feedback_request(
        self,
        session_id: str,
        feedback_type: FeedbackType,
        title: str,
        description: str = "",
        options: list[tuple[str, str, str]] | None = None,
        task_id: str | None = None,
        workflow_stage: str | None = None,
        channel_id: str | None = None,
        thread_ts: str | None = None,
    ) -> FeedbackRequest:
        """Create a feedback request.

        Args:
            session_id: Session ID
            feedback_type: Type of feedback
            title: Request title
            description: Request description
            options: Options for choice type (id, label, description)
            task_id: Linked task ID
            workflow_stage: Current workflow stage
            channel_id: Slack channel ID
            thread_ts: Slack thread timestamp

        Returns:
            The created FeedbackRequest
        """
        from ultrawork.models.memory import FeedbackOption

        request_id = f"feedback-{uuid.uuid4().hex[:12]}"

        request = FeedbackRequest(
            request_id=request_id,
            session_id=session_id,
            feedback_type=feedback_type,
            title=title,
            description=description,
            task_id=task_id,
            workflow_stage=workflow_stage,
            channel_id=channel_id,
            thread_ts=thread_ts,
        )

        if options and feedback_type == FeedbackType.CHOICE:
            request.options = [
                FeedbackOption(option_id=oid, label=label, description=desc)
                for oid, label, desc in options
            ]

        # Update session
        session = self.get_session(session_id)
        if session:
            session.add_pending_feedback(request_id)
            self._save_session(session)

        # Add approval node to workflow
        graph = self.get_workflow(session_id)
        if graph:
            node = add_approval_node_to_graph(
                graph,
                node_id=f"approval-{request_id}",
                label=title,
                description=description,
            )
            node.wait_for_input()
            graph.auto_layout_nodes()
            self._save_workflow(graph)

        self._feedback_requests[request_id] = request
        self._save_feedback(request)

        return request

    def respond_to_feedback(
        self,
        request_id: str,
        user_id: str,
        approved: bool | None = None,
        response_text: str = "",
        option_id: str | None = None,
    ) -> bool:
        """Respond to a feedback request.

        Args:
            request_id: Request ID
            user_id: User responding
            approved: Approval response (for approval type)
            response_text: Text response
            option_id: Selected option (for choice type)

        Returns:
            True if responded successfully
        """
        request = self._feedback_requests.get(request_id)
        if not request:
            request = self._load_feedback(request_id)
            if not request:
                return False

        if request.feedback_type == FeedbackType.APPROVAL:
            if approved:
                request.approve(user_id, response_text)
            else:
                request.reject(user_id, response_text)
        elif request.feedback_type == FeedbackType.CHOICE and option_id:
            request.respond_with_choice(user_id, option_id)
        elif request.feedback_type == FeedbackType.INPUT:
            request.respond_with_input(user_id, response_text)

        # Update session
        session = self.get_session(request.session_id)
        if session:
            session.resolve_feedback(request_id)
            self._save_session(session)

        # Update workflow node
        graph = self.get_workflow(request.session_id)
        if graph:
            node_id = f"approval-{request_id}"
            if request.status == FeedbackStatus.APPROVED:
                graph.complete_node(node_id, {"response": request.response})
            else:
                graph.fail_node(node_id, request.response_text)
            self._save_workflow(graph)

        self._save_feedback(request)
        return True

    def get_pending_feedback(self, session_id: str | None = None) -> list[FeedbackRequest]:
        """Get pending feedback requests.

        Args:
            session_id: Filter by session ID

        Returns:
            List of pending FeedbackRequests
        """
        pending = []
        for request in self._feedback_requests.values():
            if request.is_pending():
                if session_id is None or request.session_id == session_id:
                    pending.append(request)
        return pending

    # === Context Memory ===

    def get_memory(self, session_id: str) -> ContextMemory | None:
        """Get context memory for a session."""
        if session_id in self._memories:
            return self._memories[session_id]
        return self._load_memory(session_id)

    def add_memory_entry(
        self,
        session_id: str,
        key: str,
        value: Any,
        memory_type: MemoryType = MemoryType.SHORT_TERM,
        scope: MemoryScope = MemoryScope.SESSION,
        summary: str = "",
        source: str = "",
    ) -> bool:
        """Add a memory entry.

        Args:
            session_id: Session ID
            key: Entry key
            value: Entry value
            memory_type: Type of memory
            scope: Memory scope
            summary: Human-readable summary
            source: Source of the memory

        Returns:
            True if added successfully
        """
        memory = self.get_memory(session_id)
        if not memory:
            return False

        entry = MemoryEntry(
            entry_id=f"entry-{uuid.uuid4().hex[:8]}",
            memory_type=memory_type,
            scope=scope,
            key=key,
            value=value,
            summary=summary,
            session_id=session_id,
            source=source,
        )
        memory.add_entry(entry)
        self._save_memory(memory)
        return True

    def get_memory_context(
        self, session_id: str, keywords: list[str] | None = None, limit: int = 10
    ) -> list[dict[str, Any]]:
        """Get relevant memory context.

        Args:
            session_id: Session ID
            keywords: Keywords to filter by
            limit: Maximum entries

        Returns:
            List of context dictionaries
        """
        memory = self.get_memory(session_id)
        if not memory:
            return []

        entries = memory.get_relevant_context(keywords=keywords, limit=limit)
        return [
            {
                "key": e.key,
                "value": e.value,
                "summary": e.summary,
                "type": e.memory_type.value,
                "scope": e.scope.value,
            }
            for e in entries
        ]

    # === Link Management ===

    def link_exploration(self, session_id: str, exploration_id: str) -> bool:
        """Link an exploration to a session."""
        session = self.get_session(session_id)
        if not session:
            return False
        session.link_exploration(exploration_id)
        self._save_session(session)
        return True

    def link_task(
        self,
        session_id: str,
        task_id: str,
        workflow_type: Literal["simple", "full"] | None = None,
    ) -> bool:
        """Link a task to a session."""
        session = self.get_session(session_id)
        if not session:
            return False
        session.link_task(task_id, workflow_type)
        self._save_session(session)
        return True

    def update_stage(self, session_id: str, stage: str) -> bool:
        """Update the current workflow stage."""
        session = self.get_session(session_id)
        if not session:
            return False
        session.update_stage(stage)
        self._save_session(session)
        return True

    # === List Methods ===

    def list_sessions(
        self,
        status: SessionStatus | None = None,
        limit: int = 50,
    ) -> list[AgentSession]:
        """List sessions with optional filtering.

        Args:
            status: Filter by status
            limit: Maximum sessions to return

        Returns:
            List of sessions
        """
        sessions = list(self._sessions.values())

        # Load from disk if needed
        if len(sessions) < limit:
            for path in self.sessions_dir.glob("*.yaml"):
                session_id = path.stem
                if session_id not in self._sessions:
                    session = self._load_session(session_id)
                    if session:
                        self._sessions[session_id] = session
                        sessions.append(session)

        if status:
            sessions = [s for s in sessions if s.status == status]

        # Sort by creation time (newest first)
        sessions.sort(key=lambda s: s.created_at, reverse=True)
        return sessions[:limit]

    def list_executions(
        self, session_id: str | None = None, limit: int = 50
    ) -> list[SkillExecution]:
        """List skill executions.

        Args:
            session_id: Filter by session ID
            limit: Maximum executions to return

        Returns:
            List of executions
        """
        executions = list(self._executions.values())

        if session_id:
            executions = [e for e in executions if e.session_id == session_id]

        executions.sort(key=lambda e: e.started_at, reverse=True)
        return executions[:limit]

    # === Persistence Methods ===

    def _save_session(self, session: AgentSession) -> None:
        """Save session to YAML file."""
        path = self.sessions_dir / f"{session.session_id}.yaml"
        data = session.model_dump(mode="json")
        with open(path, "w") as f:
            yaml.safe_dump(data, f, allow_unicode=True, sort_keys=False)

    def _load_session(self, session_id: str) -> AgentSession | None:
        """Load session from YAML file."""
        path = self.sessions_dir / f"{session_id}.yaml"
        if not path.exists():
            return None
        with open(path) as f:
            data = yaml.safe_load(f)
        return AgentSession.model_validate(data)

    def _save_execution(self, execution: SkillExecution) -> None:
        """Save execution to YAML file."""
        path = self.executions_dir / f"{execution.execution_id}.yaml"
        data = execution.model_dump(mode="json")
        with open(path, "w") as f:
            yaml.safe_dump(data, f, allow_unicode=True, sort_keys=False)

    def _load_execution(self, execution_id: str) -> SkillExecution | None:
        """Load execution from YAML file."""
        path = self.executions_dir / f"{execution_id}.yaml"
        if not path.exists():
            return None
        with open(path) as f:
            data = yaml.safe_load(f)
        return SkillExecution.model_validate(data)

    def _save_workflow(self, graph: WorkflowGraph) -> None:
        """Save workflow graph to YAML file."""
        path = self.workflows_dir / f"{graph.session_id}.yaml"
        data = graph.model_dump(mode="json")
        with open(path, "w") as f:
            yaml.safe_dump(data, f, allow_unicode=True, sort_keys=False)

    def _load_workflow(self, session_id: str) -> WorkflowGraph | None:
        """Load workflow graph from YAML file."""
        path = self.workflows_dir / f"{session_id}.yaml"
        if not path.exists():
            return None
        with open(path) as f:
            data = yaml.safe_load(f)
        return WorkflowGraph.model_validate(data)

    def _save_memory(self, memory: ContextMemory) -> None:
        """Save context memory to YAML file."""
        path = self.memory_dir / f"{memory.session_id}.yaml"
        data = memory.model_dump(mode="json")
        with open(path, "w") as f:
            yaml.safe_dump(data, f, allow_unicode=True, sort_keys=False)

    def _load_memory(self, session_id: str) -> ContextMemory | None:
        """Load context memory from YAML file."""
        path = self.memory_dir / f"{session_id}.yaml"
        if not path.exists():
            return None
        with open(path) as f:
            data = yaml.safe_load(f)
        return ContextMemory.model_validate(data)

    def _save_feedback(self, request: FeedbackRequest) -> None:
        """Save feedback request to YAML file."""
        path = self.feedback_dir / f"{request.request_id}.yaml"
        data = request.model_dump(mode="json")
        with open(path, "w") as f:
            yaml.safe_dump(data, f, allow_unicode=True, sort_keys=False)

    def _load_feedback(self, request_id: str) -> FeedbackRequest | None:
        """Load feedback request from YAML file."""
        path = self.feedback_dir / f"{request_id}.yaml"
        if not path.exists():
            return None
        with open(path) as f:
            data = yaml.safe_load(f)
        return FeedbackRequest.model_validate(data)

    # === Export Methods ===

    def get_session_timeline(self, session_id: str) -> list[dict[str, Any]]:
        """Get timeline events for a session.

        Args:
            session_id: Session ID

        Returns:
            List of timeline events
        """
        session = self.get_session(session_id)
        if not session:
            return []

        events = session.to_timeline_events()

        # Add skill execution events
        for exec_id in session.skill_executions:
            execution = self.get_execution(exec_id)
            if execution:
                events.append(
                    {
                        "type": "skill_started",
                        "timestamp": execution.started_at.isoformat(),
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
                            "type": "skill_completed",
                            "timestamp": execution.completed_at.isoformat(),
                            "data": {
                                "execution_id": execution.execution_id,
                                "skill_name": execution.skill_name,
                                "status": execution.status.value,
                                "role_at_end": execution.role_at_end,
                                "duration_ms": execution.duration_ms,
                            },
                        }
                    )

        return sorted(events, key=lambda e: e["timestamp"])

    def get_workflow_visualization(self, session_id: str) -> dict[str, Any] | None:
        """Get workflow visualization data.

        Args:
            session_id: Session ID

        Returns:
            Visualization data or None
        """
        graph = self.get_workflow(session_id)
        if not graph:
            return None
        return graph.to_visualization_data()
