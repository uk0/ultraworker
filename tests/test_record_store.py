"""Tests for record store CRUD."""

from pathlib import Path

from ultrawork.memory.record_store import RecordStore
from ultrawork.models.ltm import (
    HowStep,
    RequestRecord,
    WhyHypothesis,
    WorkAction,
    WorkRecord,
    WorkWhere,
    WorkWhy,
    WorkWhyKind,
)


def _make_store(tmp_path: Path) -> RecordStore:
    return RecordStore(tmp_path)


def _make_request(store: RecordStore) -> RequestRecord:
    rid = store.generate_request_id()
    return RequestRecord(
        id=rid,
        who="user123",
        where="eng-common",
        what="Fix the search",
        why=[WhyHypothesis(hypothesis="It's slow", confidence=0.8)],
        how=[HowStep(step_id="s01", goal="Profile query")],
    )


def _make_work(store: RecordStore, request_id: str) -> WorkRecord:
    wid = store.generate_work_id(request_id)
    return WorkRecord(
        id=wid,
        who="claude",
        why=WorkWhy(kind=WorkWhyKind.ADVANCE_STEP, step_ref=f"{request_id}#s01"),
        where=WorkWhere(inputs=["src/search.py"], outputs=["profile.json"]),
        what=[WorkAction(action="Profiled query", output="N+1 detected")],
        evidence=["profile.json"],
    )


class TestRecordStoreRequestCRUD:
    def test_save_and_load(self, tmp_path: Path) -> None:
        store = _make_store(tmp_path)
        record = _make_request(store)
        path = store.save_request(record)
        assert path.exists()

        loaded = store.load_request(record.id)
        assert loaded is not None
        assert loaded.id == record.id
        assert loaded.who == "user123"
        assert loaded.what == "Fix the search"
        assert len(loaded.why) == 1
        assert len(loaded.how) == 1

    def test_list_requests(self, tmp_path: Path) -> None:
        store = _make_store(tmp_path)
        r1 = _make_request(store)
        store.save_request(r1)
        # Second record with different content to get different ID
        r2_id = store.generate_request_id()
        r2 = RequestRecord(
            id=r2_id,
            who="other-user",
            where="product",
            what="Different task entirely",
        )
        store.save_request(r2)

        records = store.list_requests()
        assert len(records) >= 2

    def test_delete_request(self, tmp_path: Path) -> None:
        store = _make_store(tmp_path)
        record = _make_request(store)
        store.save_request(record)
        assert store.delete_request(record.id)
        assert store.load_request(record.id) is None

    def test_load_nonexistent(self, tmp_path: Path) -> None:
        store = _make_store(tmp_path)
        assert store.load_request("req-99999999-9999") is None

    def test_auto_facet_indexing(self, tmp_path: Path) -> None:
        store = _make_store(tmp_path)
        record = _make_request(store)
        store.save_request(record)

        # Should have facets in index
        facets = store.facet_index.get_facets_for_record(record.id)
        assert len(facets) > 0
        assert any("k/who/" in f for f in facets)


class TestRecordStoreWorkCRUD:
    def test_save_and_load(self, tmp_path: Path) -> None:
        store = _make_store(tmp_path)
        req = _make_request(store)
        store.save_request(req)

        work = _make_work(store, req.id)
        path = store.save_work(work)
        assert path.exists()

        loaded = store.load_work(work.id)
        assert loaded is not None
        assert loaded.who == "claude"
        assert loaded.why.kind == WorkWhyKind.ADVANCE_STEP
        assert len(loaded.what) == 1

    def test_delete_work(self, tmp_path: Path) -> None:
        store = _make_store(tmp_path)
        req = _make_request(store)
        store.save_request(req)
        work = _make_work(store, req.id)
        store.save_work(work)
        assert store.delete_work(work.id)
        assert store.load_work(work.id) is None


class TestIDGeneration:
    def test_request_id_format(self, tmp_path: Path) -> None:
        store = _make_store(tmp_path)
        rid = store.generate_request_id()
        assert rid.startswith("req-")
        parts = rid.split("-")
        assert len(parts) == 3
        assert len(parts[1]) == 8  # YYYYMMDD
        assert len(parts[2]) == 4  # NNNN

    def test_request_id_sequential(self, tmp_path: Path) -> None:
        store = _make_store(tmp_path)
        r1 = _make_request(store)
        store.save_request(r1)
        rid2 = store.generate_request_id()
        # Second ID should have higher sequence
        seq1 = int(r1.id.split("-")[-1])
        seq2 = int(rid2.split("-")[-1])
        assert seq2 > seq1

    def test_work_id_format(self, tmp_path: Path) -> None:
        store = _make_store(tmp_path)
        req_id = store.generate_request_id()
        wid = store.generate_work_id(req_id)
        assert wid.startswith("work-")
        assert req_id in wid
