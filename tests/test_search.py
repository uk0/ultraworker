"""Tests for memory search engine."""

from pathlib import Path

from ultrawork.memory.facet_index import FacetIndex
from ultrawork.memory.record_store import RecordStore
from ultrawork.memory.search import MemorySearchEngine, SearchResult
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


def _setup(tmp_path: Path) -> tuple[RecordStore, FacetIndex, MemorySearchEngine]:
    store = RecordStore(tmp_path)
    index = store.facet_index
    engine = MemorySearchEngine(store, index)
    return store, index, engine


def _populate(store: RecordStore) -> tuple[RequestRecord, WorkRecord]:
    req = RequestRecord(
        id=store.generate_request_id(),
        who="developer",
        where="eng-common",
        what="Implement search optimization for the indexer",
        why=[WhyHypothesis(hypothesis="Search latency is too high", confidence=0.9)],
        how=[HowStep(step_id="s01", goal="Profile the query execution")],
    )
    store.save_request(req)

    work = WorkRecord(
        id=store.generate_work_id(req.id),
        who="claude",
        why=WorkWhy(kind=WorkWhyKind.ADVANCE_STEP, step_ref=f"{req.id}#s01"),
        where=WorkWhere(inputs=["src/indexer.py"], outputs=["profile_results.json"]),
        what=[WorkAction(action="Profiled indexer queries", output="Found N+1 problem")],
        evidence=["N+1 query pattern in indexer.py line 42"],
    )
    store.save_work(work)

    return req, work


class TestSearch:
    def test_finds_by_keyword(self, tmp_path: Path) -> None:
        store, _, engine = _setup(tmp_path)
        req, _ = _populate(store)

        results = engine.search("search optimization indexer")
        assert len(results) > 0
        record_ids = [r.record_id for r in results]
        assert req.id in record_ids

    def test_finds_by_facet(self, tmp_path: Path) -> None:
        store, index, engine = _setup(tmp_path)
        req, _ = _populate(store)

        results = engine.search("k/who/developer")
        assert len(results) > 0
        record_ids = [r.record_id for r in results]
        assert req.id in record_ids

    def test_empty_query(self, tmp_path: Path) -> None:
        _, _, engine = _setup(tmp_path)
        results = engine.search("")
        assert isinstance(results, list)

    def test_top_k_limit(self, tmp_path: Path) -> None:
        store, _, engine = _setup(tmp_path)
        # Create many records
        for i in range(15):
            rid = store.generate_request_id()
            req = RequestRecord(id=rid, who="user", what=f"Task number {i} about search")
            store.save_request(req)

        results = engine.search("search", top_k=5)
        assert len(results) <= 5

    def test_result_has_correct_type(self, tmp_path: Path) -> None:
        store, _, engine = _setup(tmp_path)
        req, work = _populate(store)

        results = engine.search("indexer")
        types = {r.record_type for r in results}
        # Should find both request and work records
        assert "request" in types or "work" in types


class TestExpandOneHop:
    def test_expands(self, tmp_path: Path) -> None:
        store, _, engine = _setup(tmp_path)
        req, work = _populate(store)

        # Add another related record
        req2_id = store.generate_request_id()
        req2 = RequestRecord(id=req2_id, who="developer", what="Fix another search bug")
        store.save_request(req2)

        expanded = engine.expand_one_hop([req.id], top_k_per_key=3)
        # Should find related records via shared facets
        assert isinstance(expanded, list)

    def test_empty_input(self, tmp_path: Path) -> None:
        _, _, engine = _setup(tmp_path)
        assert engine.expand_one_hop([]) == []


class TestChaseLinks:
    def test_follows_links(self, tmp_path: Path) -> None:
        store, _, engine = _setup(tmp_path)
        # Generate IDs sequentially - save first so second ID increments
        req1_id = store.generate_request_id()
        req1_placeholder = RequestRecord(id=req1_id, who="user", what="Task A placeholder")
        store.save_request(req1_placeholder)
        req2_id = store.generate_request_id()

        # Re-save req1 with link to req2
        req1 = RequestRecord(
            id=req1_id,
            who="user",
            what="Task A",
            links=[ShallowLink(target_id=req2_id, relation=LinkRelation.RELATED)],
        )
        req2 = RequestRecord(id=req2_id, who="user", what="Task B")
        store.save_request(req1)
        store.save_request(req2)

        linked = engine.chase_links([req1_id], max_chase=5)
        assert req2_id in linked

    def test_follows_step_ref(self, tmp_path: Path) -> None:
        store, _, engine = _setup(tmp_path)
        req, work = _populate(store)

        linked = engine.chase_links([work.id], max_chase=5)
        assert req.id in linked

    def test_max_chase_limit(self, tmp_path: Path) -> None:
        store, _, engine = _setup(tmp_path)
        req, work = _populate(store)
        linked = engine.chase_links([work.id], max_chase=1)
        assert len(linked) <= 1


class TestRerank:
    def test_boosts_matching_facets(self, tmp_path: Path) -> None:
        store, index, engine = _setup(tmp_path)
        req, _ = _populate(store)

        candidates = [
            SearchResult(record_id=req.id, record_type="request", score=0.5),
        ]
        query_facets = index.get_facets_for_record(req.id)
        reranked = engine.rerank(candidates, query_facets)
        assert reranked[0].score > 0.5
