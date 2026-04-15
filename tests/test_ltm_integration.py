"""Integration tests for the complete LTM pipeline.

Tests the full flow: create -> link -> save policy -> commit -> search.
"""

from pathlib import Path

from ultrawork.memory.facet_index import FacetIndex
from ultrawork.memory.linker import RecordLinker
from ultrawork.memory.record_store import RecordStore
from ultrawork.memory.save_policy import SaveContext, SavePolicyEngine
from ultrawork.memory.search import MemorySearchEngine
from ultrawork.models.ltm import (
    HowStep,
    LinkRelation,
    RequestRecord,
    ShallowLink,
    WhyHypothesis,
    WorkAction,
    WorkRecord,
    WorkWhere,
    WorkWhy,
    WorkWhyKind,
)


def _full_setup(
    tmp_path: Path,
) -> tuple[RecordStore, FacetIndex, RecordLinker, MemorySearchEngine, SavePolicyEngine]:
    store = RecordStore(tmp_path)
    index = store.facet_index
    linker = RecordLinker(store, index)
    engine = MemorySearchEngine(store, index)
    policy = SavePolicyEngine()
    return store, index, linker, engine, policy


class TestFullPipeline:
    def test_create_link_search(self, tmp_path: Path) -> None:
        """RequestRecord -> WorkRecord -> step_ref link -> search finds both."""
        store, index, linker, engine, policy = _full_setup(tmp_path)

        # Create request
        req = RequestRecord(
            id=store.generate_request_id(),
            who="developer",
            where="eng-common",
            what="Optimize database query performance",
            why=[
                WhyHypothesis(
                    hypothesis="Queries taking >5 seconds",
                    confidence=0.9,
                    evidence=["metrics dashboard"],
                )
            ],
            how=[
                HowStep(
                    step_id="s01", goal="Profile slow queries", expected_artifacts=["profile.log"]
                ),
                HowStep(step_id="s02", goal="Add indexes", expected_artifacts=["migration.sql"]),
            ],
        )
        store.save_request(req)

        # Create work linked to step
        work = WorkRecord(
            id=store.generate_work_id(req.id),
            who="claude",
            why=WorkWhy(
                kind=WorkWhyKind.ADVANCE_STEP,
                step_ref=f"{req.id}#s01",
                immediate_goal="Profile queries",
            ),
            where=WorkWhere(inputs=["src/db/queries.py"], outputs=["profile.log"]),
            what=[WorkAction(action="Ran query profiler", output="3 slow queries identified")],
            evidence=["profile.log shows N+1 pattern on user_orders join"],
        )
        linker.link_work_to_step(work, req.id, "s01")
        store.save_work(work)

        # Validate link
        assert linker.validate_step_ref(work)

        # Search should find both
        results = engine.search("database query performance")
        record_ids = [r.record_id for r in results]
        assert req.id in record_ids

        # Chase links from work should find request
        linked = engine.chase_links([work.id])
        assert req.id in linked

    def test_save_policy_commits_valuable_records(self, tmp_path: Path) -> None:
        """Save policy should commit records with artifacts."""
        store, _, _, _, policy = _full_setup(tmp_path)

        RequestRecord(
            id=store.generate_request_id(),
            who="user",
            what="Deploy new feature",
        )

        ctx = SaveContext(
            content_summary="Deployed new search feature with improved indexing",
            artifacts_produced=["src/search/index.py"],
            facts_extracted=["New B-tree index added", "Query latency reduced by 60%"],
            used_in_answer=True,
            decisions_made=["Use B-tree instead of hash index"],
        )
        decision = policy.evaluate(ctx)
        assert decision.should_commit
        assert "hard_trigger" in decision.reason

    def test_save_policy_rejects_simple_browsing(self, tmp_path: Path) -> None:
        """Save policy should reject simple file browsing logs."""
        _, _, _, _, policy = _full_setup(tmp_path)

        ctx = SaveContext(
            content_summary="Looked at some files",
            facts_extracted=[],
            used_in_answer=False,
        )
        decision = policy.evaluate(ctx)
        assert not decision.should_commit
        assert "rejected" in decision.reason

    def test_facet_index_update_on_save(self, tmp_path: Path) -> None:
        """Saving a record should auto-update the facet index."""
        store, index, _, _, _ = _full_setup(tmp_path)

        req = RequestRecord(
            id=store.generate_request_id(),
            who="admin",
            where="eng-common",
            what="Fix CI pipeline",
        )
        store.save_request(req)

        # Index should have facets for this record
        facets = index.get_facets_for_record(req.id)
        assert len(facets) > 0
        assert any("admin" in f for f in facets)

    def test_one_hop_expansion(self, tmp_path: Path) -> None:
        """1-hop expansion should discover related records."""
        store, index, _, engine, _ = _full_setup(tmp_path)

        # Create several related records
        r1 = RequestRecord(
            id=store.generate_request_id(),
            who="dev-team",
            where="eng-common",
            what="Fix search indexer timeout",
        )
        store.save_request(r1)

        r2 = RequestRecord(
            id=store.generate_request_id(),
            who="dev-team",
            where="eng-common",
            what="Optimize search query cache",
        )
        store.save_request(r2)

        r3 = RequestRecord(
            id=store.generate_request_id(),
            who="other-team",
            where="product",
            what="Update search UI",
        )
        store.save_request(r3)

        # 1-hop from r1 should find r2 (shared who + where facets)
        expanded = engine.expand_one_hop([r1.id], top_k_per_key=3)
        assert r2.id in expanded

    def test_deduplication_prevents_double_commit(self, tmp_path: Path) -> None:
        """Duplicate records should not be saved twice."""
        store, _, linker, _, _ = _full_setup(tmp_path)

        r1 = RequestRecord(
            id=store.generate_request_id(),
            who="user",
            what="Fix the bug in search module",
        )
        store.save_request(r1)

        r2 = RequestRecord(
            id=store.generate_request_id(),
            who="user",
            what="Fix the bug in search module",
        )
        dup = linker.check_duplicate(r2)
        assert dup == r1.id

    def test_link_updates_merge_existing(self, tmp_path: Path) -> None:
        """Updating links should preserve manually-set links."""
        store, _, linker, _, _ = _full_setup(tmp_path)

        r1 = RequestRecord(
            id=store.generate_request_id(),
            who="user",
            what="Task A",
            links=[
                ShallowLink(target_id="req-99999999-9999", relation=LinkRelation.PARENT, weight=1.0)
            ],
        )
        store.save_request(r1)

        r2 = RequestRecord(
            id=store.generate_request_id(),
            who="user",
            what="Task B related to A",
        )
        store.save_request(r2)

        linker.update_shallow_links(r1.id, max_links=7)
        updated = store.load_request(r1.id)
        assert updated is not None
        # Manual link should be preserved
        manual_link = next(
            (lnk for lnk in updated.links if lnk.target_id == "req-99999999-9999"), None
        )
        assert manual_link is not None
        assert manual_link.relation == LinkRelation.PARENT
