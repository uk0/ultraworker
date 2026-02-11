"""Exploration data models for agentic context discovery."""

from datetime import datetime
from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field


class TriggerType(str, Enum):
    """Type of exploration trigger."""

    MENTION = "mention"
    SCHEDULED = "scheduled"
    MANUAL = "manual"
    THREAD_UPDATE = "thread_update"


class Severity(str, Enum):
    """Severity level of discovered issues."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ExplorationTrigger(BaseModel):
    """What triggered the exploration."""

    type: TriggerType
    message_ts: str | None = None
    channel_id: str | None = None
    user_id: str | None = None
    keyword: str | None = None


class ExplorationScope(BaseModel):
    """Scope of the exploration."""

    channels_searched: list[str] = Field(default_factory=list)
    time_range_start: datetime | None = None
    time_range_end: datetime | None = None
    threads_analyzed: int = 0
    messages_processed: int = 0
    max_depth_reached: int = 0


class RelatedDiscussion(BaseModel):
    """A related discussion found during exploration."""

    thread_id: str
    channel_id: str
    summary: str
    relevance_score: float = 0.0  # 0.0 to 1.0
    key_participants: list[str] = Field(default_factory=list)
    timestamp: datetime | None = None


class KeyDecision(BaseModel):
    """A key decision found during exploration."""

    date: datetime
    decision: str
    context: str = ""
    participants: list[str] = Field(default_factory=list)
    thread_id: str | None = None


class OngoingIssue(BaseModel):
    """An ongoing issue discovered."""

    description: str
    first_mentioned: datetime | None = None
    last_mentioned: datetime | None = None
    status: Literal["open", "in_progress", "blocked", "resolved"] = "open"
    related_threads: list[str] = Field(default_factory=list)


class DiscoveredContext(BaseModel):
    """Context discovered during exploration."""

    previous_discussions: list[RelatedDiscussion] = Field(default_factory=list)
    ongoing_issues: list[OngoingIssue] = Field(default_factory=list)
    key_decisions: list[KeyDecision] = Field(default_factory=list)
    key_stakeholders: list[str] = Field(default_factory=list)
    related_keywords: list[str] = Field(default_factory=list)


class CurrentProblem(BaseModel):
    """Analysis of the current problem."""

    summary: str
    severity: Severity = Severity.MEDIUM
    affected_users: list[str] = Field(default_factory=list)
    related_threads: list[str] = Field(default_factory=list)
    root_cause_hypothesis: str = ""
    dependencies: list[str] = Field(default_factory=list)


class RecommendedAction(BaseModel):
    """A recommended action based on exploration."""

    action: str
    priority: int = 1  # 1 = highest
    rationale: str = ""
    estimated_effort: Literal["small", "medium", "large"] = "medium"


class ExplorationRecord(BaseModel):
    """Complete record of an exploration session."""

    exploration_id: str
    trigger: ExplorationTrigger
    created_at: datetime = Field(default_factory=datetime.now)
    completed_at: datetime | None = None
    status: Literal["in_progress", "completed", "failed"] = "in_progress"

    scope: ExplorationScope = Field(default_factory=ExplorationScope)
    context_discovered: DiscoveredContext = Field(default_factory=DiscoveredContext)
    current_problem: CurrentProblem | None = None
    recommended_actions: list[RecommendedAction] = Field(default_factory=list)

    # AI-generated summaries
    exploration_summary: str = ""
    previous_context_summary: str = ""
    situation_analysis: str = ""

    # Linked artifacts
    linked_task_id: str | None = None
    source_thread_id: str | None = None

    @classmethod
    def generate_id(cls) -> str:
        """Generate a new exploration ID."""
        now = datetime.now()
        import random

        suffix = f"{random.randint(0, 999):03d}"
        return f"EXP-{now.strftime('%Y-%m%d')}-{suffix}"

    def get_file_path(self, base_dir: str = "data/explorations") -> str:
        """Get the file path for this exploration record."""
        return f"{base_dir}/{self.exploration_id}.md"

    def add_related_discussion(
        self,
        thread_id: str,
        channel_id: str,
        summary: str,
        relevance_score: float = 0.5,
    ) -> None:
        """Add a related discussion."""
        self.context_discovered.previous_discussions.append(
            RelatedDiscussion(
                thread_id=thread_id,
                channel_id=channel_id,
                summary=summary,
                relevance_score=relevance_score,
            )
        )

    def add_key_decision(
        self,
        decision: str,
        date: datetime | None = None,
        participants: list[str] | None = None,
    ) -> None:
        """Add a key decision."""
        self.context_discovered.key_decisions.append(
            KeyDecision(
                date=date or datetime.now(),
                decision=decision,
                participants=participants or [],
            )
        )

    def complete(self, summary: str = "") -> None:
        """Mark exploration as complete."""
        self.status = "completed"
        self.completed_at = datetime.now()
        if summary:
            self.exploration_summary = summary
