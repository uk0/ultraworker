"""Agentic context explorer for Slack conversations."""

from datetime import datetime
from pathlib import Path
from typing import Any

import frontmatter

from ultrawork.models import (
    CurrentProblem,
    DiscoveredContext,
    ExplorationRecord,
    ExplorationScope,
    ExplorationTrigger,
    KeyDecision,
    OngoingIssue,
    RecommendedAction,
    RelatedDiscussion,
    Severity,
    TriggerType,
)
from ultrawork.slack.registry import SlackRegistry


class SlackExplorer:
    """Agentic context explorer that recursively explores Slack conversations.

    This explorer implements a recursive exploration strategy:
    1. Start from a trigger message
    2. Extract keywords and participants
    3. Search for related threads
    4. Analyze context and build understanding
    5. Repeat until sufficient context is gathered
    """

    def __init__(
        self,
        data_dir: str | Path = "data",
        max_depth: int = 5,
        relevance_threshold: float = 0.3,
    ):
        self.data_dir = Path(data_dir)
        self.explorations_dir = self.data_dir / "explorations"
        self.explorations_dir.mkdir(parents=True, exist_ok=True)

        self.registry = SlackRegistry(data_dir)
        self.max_depth = max_depth
        self.relevance_threshold = relevance_threshold

        # Track exploration state
        self._visited_threads: set[str] = set()
        self._current_exploration: ExplorationRecord | None = None

    def explore(
        self,
        trigger_type: TriggerType,
        channel_id: str | None = None,
        message_ts: str | None = None,
        user_id: str | None = None,
        keyword: str | None = None,
    ) -> ExplorationRecord:
        """Start a new exploration session.

        Args:
            trigger_type: What triggered this exploration
            channel_id: Channel where trigger occurred
            message_ts: Timestamp of trigger message
            user_id: User who triggered
            keyword: Search keyword for manual exploration

        Returns:
            Completed exploration record
        """
        # Create new exploration
        exploration = ExplorationRecord(
            exploration_id=ExplorationRecord.generate_id(),
            trigger=ExplorationTrigger(
                type=trigger_type,
                channel_id=channel_id,
                message_ts=message_ts,
                user_id=user_id,
                keyword=keyword,
            ),
        )

        self._current_exploration = exploration
        self._visited_threads = set()

        # Set up scope
        exploration.scope = ExplorationScope(
            time_range_start=datetime.now(),
        )

        if channel_id:
            exploration.scope.channels_searched.append(channel_id)
            exploration.source_thread_id = f"{channel_id}-{message_ts}" if message_ts else None

        return exploration

    def add_thread_analysis(
        self,
        thread_id: str,
        channel_id: str,
        messages: list[dict[str, Any]],
        relevance_score: float = 0.5,
    ) -> None:
        """Add analysis of a thread to the current exploration.

        Args:
            thread_id: Thread ID
            channel_id: Channel ID
            messages: Messages in the thread
            relevance_score: How relevant this thread is (0.0 to 1.0)
        """
        if not self._current_exploration:
            return

        if thread_id in self._visited_threads:
            return

        self._visited_threads.add(thread_id)

        # Update scope
        self._current_exploration.scope.threads_analyzed += 1
        self._current_exploration.scope.messages_processed += len(messages)

        if channel_id not in self._current_exploration.scope.channels_searched:
            self._current_exploration.scope.channels_searched.append(channel_id)

        # Extract summary from messages
        summary = self._summarize_messages(messages)

        # Extract participants
        participants = list({msg.get("user", "") for msg in messages if msg.get("user")})

        # Get timestamp
        first_ts = messages[0].get("ts", "") if messages else ""
        timestamp = datetime.fromtimestamp(float(first_ts)) if first_ts else None

        # Add as related discussion
        self._current_exploration.add_related_discussion(
            thread_id=thread_id,
            channel_id=channel_id,
            summary=summary,
            relevance_score=relevance_score,
        )

        # Update the related discussion with more details
        discussion = self._current_exploration.context_discovered.previous_discussions[-1]
        discussion.key_participants = participants
        discussion.timestamp = timestamp

    def extract_keywords(self, text: str) -> list[str]:
        """Extract search keywords from text.

        This is a simple extraction. In production, use NLP.
        """
        # Remove mentions and special characters
        import re

        text = re.sub(r"<@\w+>", "", text)
        text = re.sub(r"<#\w+\|[^>]+>", "", text)
        text = re.sub(r"[^\w\s가-힣]", " ", text)

        # Split and filter
        words = text.lower().split()
        stopwords = {
            "the",
            "a",
            "an",
            "is",
            "are",
            "was",
            "were",
            "be",
            "been",
            "have",
            "has",
            "do",
            "does",
            "did",
        }

        keywords = [w for w in words if len(w) > 2 and w not in stopwords]

        # Return unique keywords
        return list(dict.fromkeys(keywords))[:10]

    def add_decision(
        self,
        decision: str,
        date: datetime | None = None,
        participants: list[str] | None = None,
        thread_id: str | None = None,
    ) -> None:
        """Record a key decision found during exploration."""
        if not self._current_exploration:
            return

        self._current_exploration.context_discovered.key_decisions.append(
            KeyDecision(
                date=date or datetime.now(),
                decision=decision,
                participants=participants or [],
                thread_id=thread_id,
            )
        )

    def add_ongoing_issue(
        self,
        description: str,
        status: str = "open",
        related_threads: list[str] | None = None,
    ) -> None:
        """Record an ongoing issue found during exploration."""
        if not self._current_exploration:
            return

        self._current_exploration.context_discovered.ongoing_issues.append(
            OngoingIssue(
                description=description,
                first_mentioned=datetime.now(),
                status=status,  # type: ignore
                related_threads=related_threads or [],
            )
        )

    def set_current_problem(
        self,
        summary: str,
        severity: Severity = Severity.MEDIUM,
        affected_users: list[str] | None = None,
        related_threads: list[str] | None = None,
        root_cause: str = "",
    ) -> None:
        """Set the analysis of the current problem."""
        if not self._current_exploration:
            return

        self._current_exploration.current_problem = CurrentProblem(
            summary=summary,
            severity=severity,
            affected_users=affected_users or [],
            related_threads=related_threads or [],
            root_cause_hypothesis=root_cause,
        )

    def add_recommendation(
        self,
        action: str,
        priority: int = 1,
        rationale: str = "",
        effort: str = "medium",
    ) -> None:
        """Add a recommended action."""
        if not self._current_exploration:
            return

        self._current_exploration.recommended_actions.append(
            RecommendedAction(
                action=action,
                priority=priority,
                rationale=rationale,
                estimated_effort=effort,  # type: ignore
            )
        )

    def complete_exploration(
        self,
        summary: str = "",
        context_summary: str = "",
        analysis: str = "",
    ) -> ExplorationRecord:
        """Complete the exploration and save results.

        Args:
            summary: Overall exploration summary
            context_summary: Summary of discovered context
            analysis: Situation analysis

        Returns:
            Completed exploration record
        """
        if not self._current_exploration:
            raise ValueError("No exploration in progress")

        exploration = self._current_exploration

        # Update summaries
        exploration.exploration_summary = summary
        exploration.previous_context_summary = context_summary
        exploration.situation_analysis = analysis

        # Update scope
        exploration.scope.time_range_end = datetime.now()
        exploration.scope.max_depth_reached = len(self._visited_threads)

        # Sort recommendations by priority
        exploration.recommended_actions.sort(key=lambda r: r.priority)

        # Mark as complete
        exploration.complete(summary)

        # Save to file
        self._save_exploration(exploration)

        # Clear state
        self._current_exploration = None
        self._visited_threads = set()

        return exploration

    def _summarize_messages(self, messages: list[dict[str, Any]], max_length: int = 200) -> str:
        """Create a brief summary from messages."""
        if not messages:
            return ""

        # Combine first few message texts
        texts = []
        total_len = 0
        for msg in messages[:5]:
            text = msg.get("text", "")[:100]
            if total_len + len(text) > max_length:
                break
            texts.append(text)
            total_len += len(text)

        return " | ".join(texts)

    def _save_exploration(self, exploration: ExplorationRecord) -> Path:
        """Save exploration record to markdown file."""
        file_path = self.explorations_dir / f"{exploration.exploration_id}.md"

        # Build YAML metadata
        metadata = {
            "exploration_id": exploration.exploration_id,
            "trigger": exploration.trigger.model_dump(mode="json", exclude_none=True),
            "created_at": exploration.created_at.isoformat(),
            "completed_at": exploration.completed_at.isoformat()
            if exploration.completed_at
            else None,
            "status": exploration.status,
            "scope": exploration.scope.model_dump(mode="json", exclude_none=True),
            "context_discovered": {
                "previous_discussions": [
                    d.model_dump(mode="json", exclude_none=True)
                    for d in exploration.context_discovered.previous_discussions
                ],
                "ongoing_issues": [
                    i.model_dump(mode="json", exclude_none=True)
                    for i in exploration.context_discovered.ongoing_issues
                ],
                "key_decisions": [
                    d.model_dump(mode="json", exclude_none=True)
                    for d in exploration.context_discovered.key_decisions
                ],
            },
        }

        if exploration.current_problem:
            metadata["current_problem"] = exploration.current_problem.model_dump(
                mode="json", exclude_none=True
            )

        if exploration.linked_task_id:
            metadata["linked_task_id"] = exploration.linked_task_id

        # Build markdown content
        content_parts = []

        content_parts.append("## Exploration Summary")
        content_parts.append(exploration.exploration_summary or "[Summary pending]")

        content_parts.append("\n## Previous Context")
        content_parts.append(exploration.previous_context_summary or "[Context summary pending]")

        content_parts.append("\n## Situation Analysis")
        content_parts.append(exploration.situation_analysis or "[Analysis pending]")

        content_parts.append("\n## Recommended Actions")
        if exploration.recommended_actions:
            for i, rec in enumerate(exploration.recommended_actions, 1):
                content_parts.append(f"{i}. **{rec.action}** ({rec.estimated_effort})")
                if rec.rationale:
                    content_parts.append(f"   - {rec.rationale}")
        else:
            content_parts.append("[No recommendations yet]")

        content = "\n".join(content_parts)

        # Create frontmatter post and save
        post = frontmatter.Post(content, **metadata)
        file_path.write_text(frontmatter.dumps(post), encoding="utf-8")

        return file_path

    def load_exploration(self, exploration_id: str) -> ExplorationRecord | None:
        """Load an exploration record from file."""
        file_path = self.explorations_dir / f"{exploration_id}.md"
        if not file_path.exists():
            return None

        post = frontmatter.load(file_path)

        # Reconstruct the exploration record
        trigger_data = post.metadata.get("trigger", {})
        trigger_data["type"] = TriggerType(trigger_data.get("type", "manual"))

        scope_data = post.metadata.get("scope", {})
        context_data = post.metadata.get("context_discovered", {})

        # Build context
        previous_discussions = [
            RelatedDiscussion(**d) for d in context_data.get("previous_discussions", [])
        ]
        ongoing_issues = [OngoingIssue(**i) for i in context_data.get("ongoing_issues", [])]
        key_decisions = [KeyDecision(**d) for d in context_data.get("key_decisions", [])]

        context = DiscoveredContext(
            previous_discussions=previous_discussions,
            ongoing_issues=ongoing_issues,
            key_decisions=key_decisions,
        )

        # Build current problem if exists
        current_problem = None
        if "current_problem" in post.metadata:
            cp_data = post.metadata["current_problem"]
            cp_data["severity"] = Severity(cp_data.get("severity", "medium"))
            current_problem = CurrentProblem(**cp_data)

        return ExplorationRecord(
            exploration_id=post.metadata["exploration_id"],
            trigger=ExplorationTrigger(**trigger_data),
            created_at=post.metadata["created_at"],
            completed_at=post.metadata.get("completed_at"),
            status=post.metadata.get("status", "completed"),
            scope=ExplorationScope(**scope_data),
            context_discovered=context,
            current_problem=current_problem,
            exploration_summary=post.content.split("## Previous Context")[0]
            .replace("## Exploration Summary", "")
            .strip(),
            linked_task_id=post.metadata.get("linked_task_id"),
        )

    def should_continue_exploring(self, current_depth: int = 0) -> bool:
        """Determine if exploration should continue.

        This is a heuristic that can be enhanced with ML.
        """
        if current_depth >= self.max_depth:
            return False

        if not self._current_exploration:
            return False

        # Continue if we haven't found enough context
        discussions = self._current_exploration.context_discovered.previous_discussions
        if len(discussions) < 3:
            return True

        # Check average relevance
        if discussions:
            avg_relevance = sum(d.relevance_score for d in discussions) / len(discussions)
            return avg_relevance > self.relevance_threshold

        return False

    def get_search_queries(self, base_keywords: list[str]) -> list[str]:
        """Generate search queries for exploration.

        Args:
            base_keywords: Initial keywords from trigger message

        Returns:
            List of search queries to try
        """
        queries = []

        # Direct keyword queries
        for kw in base_keywords[:5]:
            queries.append(kw)

        # Combination queries
        if len(base_keywords) >= 2:
            queries.append(f"{base_keywords[0]} {base_keywords[1]}")

        # Add context from ongoing exploration
        if self._current_exploration:
            # Add keywords from discovered context
            for issue in self._current_exploration.context_discovered.ongoing_issues:
                keywords = self.extract_keywords(issue.description)
                queries.extend(keywords[:2])

        return list(dict.fromkeys(queries))[:10]  # Unique queries, max 10
