"""Tests for record linker."""

from pathlib import Path

from ultrawork.memory.facet_index import FacetIndex
from ultrawork.memory.linker import RecordLinker
from ultrawork.memory.record_store import RecordStore
from ultrawork.models.ltm import (
    HowStep,
    RequestRecord,
    WorkAction,
    WorkRecord,
    WorkWhy,
    WorkWhyKind,
)


def _setup(tmp_path: Path) -> tuple[RecordStore, FacetIndex, RecordLinker]:
    store = RecordStore(tmp_path)
    index = store.facet_index
    linker = RecordLinker(store, index)
    return store, index, linker


def _make_request(store: RecordStore) -> RequestRecord:
    rid = store.generate_request_id()
    return RequestRecord(
        id=rid,
        who="user",
        what="Fix search",
        how=[
            HowStep(step_id="s01", goal="Profile", expected_artifacts=["profile.json"]),
            HowStep(step_id="s02", goal="Optimize", expected_artifacts=["opt.py"]),
        ],
    )


class TestLinkWorkToStep:
    def test_sets_step_ref(self, tmp_path: Path) -> None:
        store, _, linker = _setup(tmp_path)
        req = _make_request(store)
        store.save_request(req)

        work = WorkRecord(
            id=store.generate_work_id(req.id),
            who="claude",
            why=WorkWhy(kind=WorkWhyKind.ADVANCE_STEP),
            what=[WorkAction(action="Profiled")],
        )
        linker.link_work_to_step(work, req.id, "s01")
        assert work.why.step_ref == f"{req.id}#s01"


class TestValidateStepRef:
    def test_valid_ref(self, tmp_path: Path) -> None:
        store, _, linker = _setup(tmp_path)
        req = _make_request(store)
        store.save_request(req)

        work = WorkRecord(
            id=store.generate_work_id(req.id),
            who="claude",
            why=WorkWhy(kind=WorkWhyKind.ADVANCE_STEP, step_ref=f"{req.id}#s01"),
            what=[WorkAction(action="Profiled")],
        )
        assert linker.validate_step_ref(work)

    def test_invalid_step(self, tmp_path: Path) -> None:
        store, _, linker = _setup(tmp_path)
        req = _make_request(store)
        store.save_request(req)

        work = WorkRecord(
            id=store.generate_work_id(req.id),
            who="claude",
            why=WorkWhy(kind=WorkWhyKind.ADVANCE_STEP, step_ref=f"{req.id}#nonexistent"),
            what=[],
        )
        assert not linker.validate_step_ref(work)

    def test_no_step_ref(self, tmp_path: Path) -> None:
        store, _, linker = _setup(tmp_path)
        work = WorkRecord(
            id="work-20260226-req-20260226-0001-01",
            who="claude",
            why=WorkWhy(kind=WorkWhyKind.MAINTENANCE),
            what=[],
        )
        assert not linker.validate_step_ref(work)


class TestFindSimilarRecords:
    def test_finds_similar(self, tmp_path: Path) -> None:
        store, _, linker = _setup(tmp_path)
        r1 = _make_request(store)
        store.save_request(r1)

        r2_id = store.generate_request_id()
        r2 = RequestRecord(id=r2_id, who="user", what="Fix search indexer too")
        store.save_request(r2)

        similar = linker.find_similar_records(r1.id, top_k=5)
        assert r2.id in similar


class TestUpdateShallowLinks:
    def test_adds_links(self, tmp_path: Path) -> None:
        store, _, linker = _setup(tmp_path)
        r1 = _make_request(store)
        store.save_request(r1)

        r2_id = store.generate_request_id()
        r2 = RequestRecord(id=r2_id, who="user", what="Related search fix")
        store.save_request(r2)

        linker.update_shallow_links(r1.id, max_links=7)
        updated = store.load_request(r1.id)
        assert updated is not None
        target_ids = {link.target_id for link in updated.links}
        assert r2.id in target_ids


class TestCheckDuplicate:
    def test_detects_duplicate(self, tmp_path: Path) -> None:
        store, _, linker = _setup(tmp_path)
        r1 = _make_request(store)
        store.save_request(r1)

        r2_id = store.generate_request_id()
        r2 = RequestRecord(id=r2_id, who="user", what="Fix search")  # Same what
        dup = linker.check_duplicate(r2)
        assert dup == r1.id

    def test_no_duplicate(self, tmp_path: Path) -> None:
        store, _, linker = _setup(tmp_path)
        r1 = _make_request(store)
        store.save_request(r1)

        r2_id = store.generate_request_id()
        r2 = RequestRecord(id=r2_id, who="user", what="Completely different task")
        dup = linker.check_duplicate(r2)
        assert dup is None


class TestDecomposeStep:
    def test_no_decompose_single_artifact(self, tmp_path: Path) -> None:
        store, _, linker = _setup(tmp_path)
        req = _make_request(store)
        result = linker.decompose_step_if_needed(req, "s01")
        assert len(result) == 1
        assert result[0].step_id == "s01"

    def test_decompose_multiple_artifacts(self, tmp_path: Path) -> None:
        store, _, linker = _setup(tmp_path)
        req = RequestRecord(
            id=store.generate_request_id(),
            who="user",
            what="Build feature",
            how=[
                HowStep(
                    step_id="s01",
                    goal="Create module",
                    expected_artifacts=["module.py", "test_module.py", "docs.md"],
                ),
            ],
        )
        result = linker.decompose_step_if_needed(req, "s01")
        assert len(result) == 3
        assert result[0].step_id == "s01-01"
        assert result[1].step_id == "s01-02"
        assert result[2].step_id == "s01-03"
        # Original step should be replaced in request.how
        assert len(req.how) == 3

    def test_nonexistent_step(self, tmp_path: Path) -> None:
        store, _, linker = _setup(tmp_path)
        req = _make_request(store)
        result = linker.decompose_step_if_needed(req, "nonexistent")
        assert result == []
