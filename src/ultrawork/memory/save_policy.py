"""Draft/Commit 2-stage save policy engine.

Prevents simple exploration logs from polluting long-term memory.
Two evaluation modes:
1. 4-Signal Gate: Boolean signals with variable thresholds per record type
2. NDREI Scoring: Weighted multi-dimensional scoring for nuanced evaluation
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from ultrawork.models.ltm import SaveSignals


class SaveContext(BaseModel):
    """Context for evaluating whether a record should be committed."""

    record_type: str = "work"  # "request" or "work"
    content_summary: str = ""
    facts_extracted: list[str] = Field(default_factory=list)
    used_in_answer: bool = False
    artifacts_produced: list[str] = Field(default_factory=list)
    decisions_made: list[str] = Field(default_factory=list)
    preferences_updated: list[str] = Field(default_factory=list)
    existing_memory_keys: list[str] = Field(default_factory=list)

    # 4-Signal Gate inputs
    is_novel: bool | None = None
    led_to_decision: bool = False
    changed_approach: bool = False
    scope: str = ""  # "session", "cross_session", "domain_knowledge", "architecture"
    related_record_count: int = 0

    # used_in_answer computation inputs
    output_references_finding: bool = False
    modifications_after_discovery: bool = False
    cited_in_decision: bool = False


class SaveDecision(BaseModel):
    """Result of save policy evaluation."""

    should_commit: bool
    reason: str  # "4signal:<count>/<threshold>" | "hard_trigger:<name>" | "score_commit" | "rejected:<gate>"
    signals: SaveSignals | None = None
    score_breakdown: dict[str, float] | None = None
    gates: dict[str, bool] | None = None


class SavePolicyEngine:
    """Evaluates whether a record should be committed to LTM.

    Primary: 4-Signal Gate with variable thresholds
    Fallback: NDREI multi-dimensional scoring
    """

    # 4-Signal Gate thresholds per record type
    SIGNAL_THRESHOLDS: dict[str, int] = {
        "request": 2,  # Need 2/4 signals for request records
        "work": 3,  # Need 3/4 signals for work records
    }

    # NDREI scoring thresholds (fallback)
    SOFT_SCORE_THRESHOLD = 0.65
    MIN_HIGH_DIMENSIONS = 2
    HIGH_DIMENSION_THRESHOLD = 0.7

    def evaluate_signals(self, context: SaveContext) -> SaveSignals:
        """Evaluate the 4 boolean signals.

        Args:
            context: The save context to evaluate

        Returns:
            SaveSignals with evaluated boolean values
        """
        novelty = self._check_novelty(context)
        actionability = self._check_actionability(context)
        persistence = self._check_persistence(context)
        connectedness = self._check_connectedness(context)

        return SaveSignals(
            novelty=novelty,
            actionability=actionability,
            persistence=persistence,
            connectedness=connectedness,
        )

    def evaluate_4signal(self, context: SaveContext) -> SaveDecision:
        """Evaluate using the 4-Signal Gate with variable thresholds.

        RequestRecord: 2/4 signals required
        WorkRecord: 3/4 signals required

        Args:
            context: The save context to evaluate

        Returns:
            SaveDecision with commit/reject decision
        """
        signals = self.evaluate_signals(context)
        threshold = self.SIGNAL_THRESHOLDS.get(context.record_type, 1)
        score = signals.score

        if score >= threshold:
            return SaveDecision(
                should_commit=True,
                reason=f"4signal:{score}/{threshold}",
                signals=signals,
            )

        return SaveDecision(
            should_commit=False,
            reason=f"rejected:4signal_{score}/{threshold}",
            signals=signals,
        )

    def evaluate(self, context: SaveContext) -> SaveDecision:
        """Full evaluation: 4-Signal Gate first, then NDREI fallback.

        1. Check 4-Signal Gate -> commit/reject
        2. If rejected by gate, check hard triggers -> commit if any
        3. If still rejected, check NDREI score -> commit if threshold met

        Args:
            context: The save context to evaluate

        Returns:
            SaveDecision with commit/reject decision
        """
        # 1. Primary: 4-Signal Gate
        gate_decision = self.evaluate_4signal(context)
        if gate_decision.should_commit:
            return gate_decision

        # 2. Fallback: Hard triggers
        trigger = self.check_hard_triggers(context)
        if trigger:
            return SaveDecision(
                should_commit=True,
                reason=f"hard_trigger:{trigger}",
                signals=gate_decision.signals,
            )

        # 3. Fallback: NDREI scoring
        gates_passed, gates = self.check_gates(context)
        if not gates_passed:
            failed = [k for k, v in gates.items() if not v]
            return SaveDecision(
                should_commit=False,
                reason=f"rejected:gate_{'+'.join(failed)}",
                signals=gate_decision.signals,
                gates=gates,
            )

        total_score, breakdown = self.calculate_soft_score(context)
        high_dims = sum(1 for v in breakdown.values() if v >= self.HIGH_DIMENSION_THRESHOLD)
        if total_score >= self.SOFT_SCORE_THRESHOLD and high_dims >= self.MIN_HIGH_DIMENSIONS:
            return SaveDecision(
                should_commit=True,
                reason="score_commit",
                signals=gate_decision.signals,
                score_breakdown=breakdown,
                gates=gates,
            )

        return SaveDecision(
            should_commit=False,
            reason=f"rejected:low_score_{total_score:.3f}_dims_{high_dims}",
            signals=gate_decision.signals,
            score_breakdown=breakdown,
            gates=gates,
        )

    # --- 4-Signal Gate helpers ---

    def _check_novelty(self, context: SaveContext) -> bool:
        """Is this new information not already in memory?"""
        if context.is_novel is not None:
            return context.is_novel
        # Heuristic: no existing memory keys overlap with content
        if not context.existing_memory_keys:
            return True
        summary_words = set(context.content_summary.lower().split())
        overlap = sum(
            1
            for key in context.existing_memory_keys
            if any(w in key.lower() for w in summary_words)
        )
        return overlap < len(context.existing_memory_keys) * 0.3

    def _check_actionability(self, context: SaveContext) -> bool:
        """Did this lead to a concrete action or decision?"""
        if context.led_to_decision or context.changed_approach:
            return True
        if context.decisions_made:
            return True
        if context.artifacts_produced:
            return True
        return self.compute_used_in_answer(context)

    def _check_persistence(self, context: SaveContext) -> bool:
        """Is this useful beyond the current session?"""
        return context.scope in ("cross_session", "domain_knowledge", "architecture")

    def _check_connectedness(self, context: SaveContext) -> bool:
        """Can this connect to existing records?"""
        return context.related_record_count > 0

    @staticmethod
    def compute_used_in_answer(context: SaveContext) -> bool:
        """Determine if search/exploration results were actually used."""
        if context.output_references_finding:
            return True
        if context.modifications_after_discovery:
            return True
        return bool(context.cited_in_decision)

    # --- NDREI scoring (fallback) ---

    def check_hard_triggers(self, context: SaveContext) -> str | None:
        """Check for hard commit triggers."""
        if any(
            fact.startswith(("file://", "http://", "https://", "schema://"))
            for fact in context.facts_extracted
        ):
            return "stable_fact"
        if context.decisions_made:
            return "decision"
        if context.artifacts_produced:
            return "artifact"
        failure_keywords = {"error", "fix", "workaround", "solution", "resolved"}
        content_lower = context.content_summary.lower()
        if sum(1 for kw in failure_keywords if kw in content_lower) >= 2:
            return "failure_pattern"
        if context.preferences_updated:
            return "preference_update"
        return None

    def calculate_soft_score(self, context: SaveContext) -> tuple[float, dict[str, float]]:
        """Calculate NDREI soft commit score."""
        if context.existing_memory_keys:
            summary_words = set(context.content_summary.lower().split())
            overlap = sum(
                1
                for key in context.existing_memory_keys
                if any(w in key.lower() for w in summary_words)
            )
            novelty = max(0.0, 1.0 - (overlap / max(len(context.existing_memory_keys), 1)))
        else:
            novelty = 1.0

        density = min(1.0, len(context.facts_extracted) / 5.0)
        relevance = 1.0 if context.used_in_answer else 0.0
        evidence_count = len(context.artifacts_produced) + len(context.facts_extracted)
        evidence = min(1.0, evidence_count / 4.0)
        impact_count = len(context.decisions_made) + len(context.preferences_updated)
        impact = min(1.0, impact_count / 2.0)

        breakdown = {
            "novelty": round(novelty, 3),
            "density": round(density, 3),
            "relevance": round(relevance, 3),
            "evidence": round(evidence, 3),
            "impact": round(impact, 3),
        }
        total = 0.25 * novelty + 0.20 * density + 0.20 * relevance + 0.20 * evidence + 0.15 * impact
        return round(total, 3), breakdown

    def check_gates(self, context: SaveContext) -> tuple[bool, dict[str, bool]]:
        """Check NDREI commit gates."""
        used_in_answer = context.used_in_answer
        has_enough_facts = len(context.facts_extracted) >= 2

        gates = {
            "used_in_answer": used_in_answer,
            "extracted_fact_count": has_enough_facts,
        }
        return all(gates.values()), gates
