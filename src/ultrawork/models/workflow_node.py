"""Workflow node models for visual representation.

This module provides models for representing workflows as directed graphs
for visualization in the dashboard UI.
"""

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class NodeType(str, Enum):
    """Type of workflow node."""

    TRIGGER = "trigger"  # Entry point (mention, manual)
    SKILL = "skill"  # Skill execution
    DECISION = "decision"  # Branching point
    APPROVAL = "approval"  # Human approval gate
    OUTPUT = "output"  # Final output
    SUBPROCESS = "subprocess"  # Nested workflow


class NodeStatus(str, Enum):
    """Status of a workflow node."""

    PENDING = "pending"
    ACTIVE = "active"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"
    WAITING = "waiting"


class WorkflowNode(BaseModel):
    """A single node in the workflow graph.

    Each node represents a step in the workflow pipeline, such as:
    - A trigger event (Slack mention)
    - A skill execution (explore-context, create-todo, etc.)
    - A decision point (branching based on conditions)
    - An approval gate (human-in-the-loop)
    - An output (final response, report)
    """

    node_id: str
    node_type: NodeType
    label: str  # Display label
    description: str = ""

    # Position for visualization (auto-calculated or manual)
    x: float = 0.0
    y: float = 0.0

    # Status
    status: NodeStatus = NodeStatus.PENDING
    started_at: datetime | None = None
    completed_at: datetime | None = None

    # Connections
    input_nodes: list[str] = Field(default_factory=list)  # Node IDs
    output_nodes: list[str] = Field(default_factory=list)  # Node IDs

    # Data
    input_data: dict[str, Any] = Field(default_factory=dict)
    output_data: dict[str, Any] = Field(default_factory=dict)

    # Linked execution (for skill nodes)
    skill_execution_id: str | None = None

    # Metadata
    metadata: dict[str, Any] = Field(default_factory=dict)

    # Styling hints
    icon: str = ""  # Emoji or icon name
    color: str = ""  # Color override

    def activate(self) -> None:
        """Mark this node as active."""
        self.status = NodeStatus.ACTIVE
        self.started_at = datetime.now()

    def complete(self, output_data: dict[str, Any] | None = None) -> None:
        """Mark this node as completed."""
        self.status = NodeStatus.COMPLETED
        self.completed_at = datetime.now()
        if output_data:
            self.output_data = output_data

    def fail(self, error: str | None = None) -> None:
        """Mark this node as failed."""
        self.status = NodeStatus.FAILED
        self.completed_at = datetime.now()
        if error:
            self.metadata["error"] = error

    def skip(self) -> None:
        """Mark this node as skipped."""
        self.status = NodeStatus.SKIPPED
        self.completed_at = datetime.now()

    def wait_for_input(self) -> None:
        """Mark this node as waiting for input."""
        self.status = NodeStatus.WAITING

    def get_duration_ms(self) -> int | None:
        """Get node execution duration in milliseconds."""
        if self.started_at and self.completed_at:
            return int((self.completed_at - self.started_at).total_seconds() * 1000)
        return None


class WorkflowGraph(BaseModel):
    """Complete workflow graph for a session.

    A WorkflowGraph represents the entire workflow pipeline for an agent session,
    including all nodes and their connections. It provides methods for:
    - Adding and connecting nodes
    - Tracking active/completed nodes
    - Auto-layout for visualization
    - Serialization for the frontend
    """

    graph_id: str
    session_id: str
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)

    nodes: dict[str, WorkflowNode] = Field(default_factory=dict)

    # Current execution state
    active_nodes: list[str] = Field(default_factory=list)
    completed_nodes: list[str] = Field(default_factory=list)

    # Layout settings
    auto_layout: bool = True
    layout_direction: str = "LR"  # LR (left-right) or TB (top-bottom)

    def add_node(self, node: WorkflowNode) -> None:
        """Add a node to the graph."""
        self.nodes[node.node_id] = node
        self.updated_at = datetime.now()

    def get_node(self, node_id: str) -> WorkflowNode | None:
        """Get a node by ID."""
        return self.nodes.get(node_id)

    def connect(self, from_id: str, to_id: str) -> bool:
        """Connect two nodes.

        Args:
            from_id: Source node ID
            to_id: Target node ID

        Returns:
            True if connection was made, False if nodes don't exist
        """
        if from_id not in self.nodes or to_id not in self.nodes:
            return False

        from_node = self.nodes[from_id]
        to_node = self.nodes[to_id]

        if to_id not in from_node.output_nodes:
            from_node.output_nodes.append(to_id)
        if from_id not in to_node.input_nodes:
            to_node.input_nodes.append(from_id)

        self.updated_at = datetime.now()
        return True

    def activate_node(self, node_id: str) -> bool:
        """Mark a node as active.

        Args:
            node_id: Node ID to activate

        Returns:
            True if node was activated
        """
        if node_id not in self.nodes:
            return False

        node = self.nodes[node_id]
        node.activate()

        if node_id not in self.active_nodes:
            self.active_nodes.append(node_id)

        self.updated_at = datetime.now()
        return True

    def complete_node(self, node_id: str, output_data: dict[str, Any] | None = None) -> bool:
        """Mark a node as completed.

        Args:
            node_id: Node ID to complete
            output_data: Optional output data

        Returns:
            True if node was completed
        """
        if node_id not in self.nodes:
            return False

        node = self.nodes[node_id]
        node.complete(output_data)

        if node_id in self.active_nodes:
            self.active_nodes.remove(node_id)
        if node_id not in self.completed_nodes:
            self.completed_nodes.append(node_id)

        self.updated_at = datetime.now()
        return True

    def fail_node(self, node_id: str, error: str | None = None) -> bool:
        """Mark a node as failed.

        Args:
            node_id: Node ID to fail
            error: Optional error message

        Returns:
            True if node was marked failed
        """
        if node_id not in self.nodes:
            return False

        node = self.nodes[node_id]
        node.fail(error)

        if node_id in self.active_nodes:
            self.active_nodes.remove(node_id)

        self.updated_at = datetime.now()
        return True

    def get_next_nodes(self, node_id: str) -> list[WorkflowNode]:
        """Get nodes that follow the specified node."""
        if node_id not in self.nodes:
            return []

        node = self.nodes[node_id]
        return [self.nodes[nid] for nid in node.output_nodes if nid in self.nodes]

    def get_previous_nodes(self, node_id: str) -> list[WorkflowNode]:
        """Get nodes that precede the specified node."""
        if node_id not in self.nodes:
            return []

        node = self.nodes[node_id]
        return [self.nodes[nid] for nid in node.input_nodes if nid in self.nodes]

    def auto_layout_nodes(self) -> None:
        """Auto-calculate node positions for visualization.

        Uses a simple topological sort with level-based positioning.
        """
        if not self.auto_layout or not self.nodes:
            return

        # Calculate levels using BFS
        levels = self._compute_levels()

        # Position nodes
        horizontal_spacing = 220
        vertical_spacing = 120
        start_x = 50
        start_y = 200

        max_nodes_per_level = max(len(level) for level in levels) if levels else 1

        for level_idx, level_nodes in enumerate(levels):
            level_y_offset = (max_nodes_per_level - len(level_nodes)) * vertical_spacing / 2

            for node_idx, node_id in enumerate(level_nodes):
                if node_id in self.nodes:
                    node = self.nodes[node_id]
                    node.x = start_x + level_idx * horizontal_spacing
                    node.y = start_y + level_y_offset + node_idx * vertical_spacing

        self.updated_at = datetime.now()

    def _compute_levels(self) -> list[list[str]]:
        """Compute node levels for layout using BFS."""
        levels: list[list[str]] = []
        visited: set[str] = set()
        in_degree: dict[str, int] = {nid: 0 for nid in self.nodes}

        # Compute in-degrees
        for node in self.nodes.values():
            for out_id in node.output_nodes:
                if out_id in in_degree:
                    in_degree[out_id] += 1

        # Start with roots (in-degree 0)
        current_level = [nid for nid, deg in in_degree.items() if deg == 0]
        for nid in current_level:
            visited.add(nid)

        while current_level:
            levels.append(current_level)
            next_level = []

            for node_id in current_level:
                if node_id in self.nodes:
                    for next_id in self.nodes[node_id].output_nodes:
                        if next_id not in visited and next_id in self.nodes:
                            visited.add(next_id)
                            next_level.append(next_id)

            current_level = next_level

        return levels

    def to_visualization_data(self) -> dict[str, Any]:
        """Convert graph to data format for frontend visualization."""
        nodes_data = []
        edges_data = []

        for node in self.nodes.values():
            nodes_data.append(
                {
                    "id": node.node_id,
                    "type": node.node_type.value,
                    "label": node.label,
                    "description": node.description,
                    "status": node.status.value,
                    "x": node.x,
                    "y": node.y,
                    "icon": node.icon or self._get_default_icon(node.node_type),
                    "color": node.color,
                    "skill_execution_id": node.skill_execution_id,
                    "duration_ms": node.get_duration_ms(),
                }
            )

            for target_id in node.output_nodes:
                edges_data.append(
                    {
                        "source": node.node_id,
                        "target": target_id,
                    }
                )

        return {
            "graph_id": self.graph_id,
            "session_id": self.session_id,
            "updated_at": self.updated_at.isoformat(),
            "nodes": nodes_data,
            "edges": edges_data,
            "active_nodes": self.active_nodes,
            "completed_nodes": self.completed_nodes,
        }

    @staticmethod
    def _get_default_icon(node_type: NodeType) -> str:
        """Get default icon for a node type."""
        icons = {
            NodeType.TRIGGER: "bolt",
            NodeType.SKILL: "wrench",
            NodeType.DECISION: "shuffle",
            NodeType.APPROVAL: "hand",
            NodeType.OUTPUT: "upload",
            NodeType.SUBPROCESS: "refresh",
        }
        return icons.get(node_type, "circle")


def create_workflow_for_session(
    graph_id: str,
    session_id: str,
    trigger_label: str = "Slack Mention",
    trigger_description: str = "",
) -> WorkflowGraph:
    """Create an initial workflow graph for a session.

    Args:
        graph_id: Unique graph ID
        session_id: Parent session ID
        trigger_label: Label for the trigger node
        trigger_description: Description for the trigger node

    Returns:
        A new WorkflowGraph with a trigger node
    """
    graph = WorkflowGraph(
        graph_id=graph_id,
        session_id=session_id,
    )

    # Add trigger node
    trigger_node = WorkflowNode(
        node_id="trigger",
        node_type=NodeType.TRIGGER,
        label=trigger_label,
        description=trigger_description,
        x=50,
        y=200,
        icon="bolt",
    )
    graph.add_node(trigger_node)

    return graph


def add_skill_node_to_graph(
    graph: WorkflowGraph,
    node_id: str,
    skill_name: str,
    skill_execution_id: str,
    connect_from: str | None = None,
) -> WorkflowNode:
    """Add a skill node to a workflow graph.

    Args:
        graph: The workflow graph
        node_id: Unique node ID
        skill_name: Name of the skill
        skill_execution_id: ID of the skill execution
        connect_from: Node ID to connect from (optional)

    Returns:
        The created WorkflowNode
    """
    # Get position based on existing nodes
    x = 50 + len(graph.nodes) * 220
    y = 200

    node = WorkflowNode(
        node_id=node_id,
        node_type=NodeType.SKILL,
        label=skill_name,
        description=f"Skill: {skill_name}",
        x=x,
        y=y,
        skill_execution_id=skill_execution_id,
        icon="wrench",
    )

    graph.add_node(node)

    # Connect from previous node if specified
    if connect_from and connect_from in graph.nodes:
        graph.connect(connect_from, node_id)
    elif graph.completed_nodes:
        # Connect from last completed node
        graph.connect(graph.completed_nodes[-1], node_id)
    elif "trigger" in graph.nodes and node_id != "trigger":
        # Connect from trigger
        graph.connect("trigger", node_id)

    return node


def add_approval_node_to_graph(
    graph: WorkflowGraph,
    node_id: str,
    label: str,
    description: str = "",
    connect_from: str | None = None,
) -> WorkflowNode:
    """Add an approval gate node to a workflow graph.

    Args:
        graph: The workflow graph
        node_id: Unique node ID
        label: Display label
        description: Description
        connect_from: Node ID to connect from (optional)

    Returns:
        The created WorkflowNode
    """
    x = 50 + len(graph.nodes) * 220
    y = 200

    node = WorkflowNode(
        node_id=node_id,
        node_type=NodeType.APPROVAL,
        label=label,
        description=description,
        x=x,
        y=y,
        icon="hand",
    )

    graph.add_node(node)

    if connect_from and connect_from in graph.nodes:
        graph.connect(connect_from, node_id)
    elif graph.completed_nodes:
        graph.connect(graph.completed_nodes[-1], node_id)

    return node
