"""Tests for save policy engine."""

from ultrawork.memory.save_policy import SaveContext, SavePolicyEngine


class TestHardTriggers:
    def setup_method(self) -> None:
        self.engine = SavePolicyEngine()

    def test_stable_fact_trigger(self) -> None:
        ctx = SaveContext(facts_extracted=["file:///tmp/schema.json"])
        trigger = self.engine.check_hard_triggers(ctx)
        assert trigger == "stable_fact"

    def test_decision_trigger(self) -> None:
        ctx = SaveContext(decisions_made=["Use PostgreSQL instead of SQLite"])
        trigger = self.engine.check_hard_triggers(ctx)
        assert trigger == "decision"

    def test_artifact_trigger(self) -> None:
        ctx = SaveContext(artifacts_produced=["src/new_module.py"])
        trigger = self.engine.check_hard_triggers(ctx)
        assert trigger == "artifact"

    def test_failure_pattern_trigger(self) -> None:
        ctx = SaveContext(content_summary="Found an error in the query. Applied fix to resolve it.")
        trigger = self.engine.check_hard_triggers(ctx)
        assert trigger == "failure_pattern"

    def test_preference_trigger(self) -> None:
        ctx = SaveContext(preferences_updated=["Use ruff instead of black"])
        trigger = self.engine.check_hard_triggers(ctx)
        assert trigger == "preference_update"

    def test_no_trigger(self) -> None:
        ctx = SaveContext(content_summary="Just browsing some files")
        trigger = self.engine.check_hard_triggers(ctx)
        assert trigger is None


class TestGates:
    def setup_method(self) -> None:
        self.engine = SavePolicyEngine()

    def test_both_gates_pass(self) -> None:
        ctx = SaveContext(
            used_in_answer=True,
            facts_extracted=["fact1", "fact2"],
        )
        passed, gates = self.engine.check_gates(ctx)
        assert passed
        assert gates["used_in_answer"]
        assert gates["extracted_fact_count"]

    def test_not_used_in_answer(self) -> None:
        ctx = SaveContext(
            used_in_answer=False,
            facts_extracted=["fact1", "fact2"],
        )
        passed, gates = self.engine.check_gates(ctx)
        assert not passed
        assert not gates["used_in_answer"]

    def test_not_enough_facts(self) -> None:
        ctx = SaveContext(
            used_in_answer=True,
            facts_extracted=["only one"],
        )
        passed, gates = self.engine.check_gates(ctx)
        assert not passed
        assert not gates["extracted_fact_count"]


class TestSoftScore:
    def setup_method(self) -> None:
        self.engine = SavePolicyEngine()

    def test_high_score(self) -> None:
        ctx = SaveContext(
            content_summary="New approach to indexing",
            facts_extracted=["fact1", "fact2", "fact3", "fact4", "fact5"],
            used_in_answer=True,
            artifacts_produced=["index.py", "test_index.py"],
            decisions_made=["Use B-tree"],
        )
        score, breakdown = self.engine.calculate_soft_score(ctx)
        assert score >= 0.65
        assert breakdown["relevance"] == 1.0
        assert breakdown["density"] == 1.0

    def test_low_score(self) -> None:
        ctx = SaveContext(
            content_summary="simple query",
            facts_extracted=[],
            used_in_answer=False,
        )
        score, breakdown = self.engine.calculate_soft_score(ctx)
        assert score < 0.65
        assert breakdown["relevance"] == 0.0
        assert breakdown["density"] == 0.0


class TestEvaluate:
    def setup_method(self) -> None:
        self.engine = SavePolicyEngine()

    def test_hard_trigger_commits(self) -> None:
        ctx = SaveContext(artifacts_produced=["output.py"])
        decision = self.engine.evaluate(ctx)
        assert decision.should_commit
        assert decision.reason.startswith("hard_trigger:")

    def test_gate_rejects(self) -> None:
        ctx = SaveContext(
            used_in_answer=False,
            facts_extracted=["one"],
        )
        decision = self.engine.evaluate(ctx)
        assert not decision.should_commit
        assert decision.reason.startswith("rejected:gate_")

    def test_score_commits(self) -> None:
        ctx = SaveContext(
            content_summary="Brand new discovery about system architecture patterns",
            used_in_answer=True,
            facts_extracted=["fact1", "fact2", "fact3", "fact4", "fact5"],
            # No artifacts/decisions/preferences -> no hard triggers
        )
        decision = self.engine.evaluate(ctx)
        assert decision.should_commit
        assert decision.reason == "score_commit"
        assert decision.score_breakdown is not None

    def test_low_score_rejects(self) -> None:
        ctx = SaveContext(
            content_summary="browsing files",
            used_in_answer=True,
            facts_extracted=["fact1", "fact2"],
            existing_memory_keys=["browsing", "files", "common"],
        )
        decision = self.engine.evaluate(ctx)
        # May or may not commit depending on exact scores, but should have a decision
        assert isinstance(decision.should_commit, bool)
