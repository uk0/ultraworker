"""Tests for facet index."""

from pathlib import Path

from ultrawork.memory.facet_index import FacetIndex


class TestFacetIndex:
    def _make_index(self, tmp_path: Path) -> FacetIndex:
        return FacetIndex(tmp_path / "facet_index.yaml")

    def test_add_and_search_and(self, tmp_path: Path) -> None:
        index = self._make_index(tmp_path)
        index.add("req-001", ["k/who/admin", "k/what/fix-bug"])
        index.add("req-002", ["k/who/admin", "k/what/add-feature"])
        index.add("req-003", ["k/who/other", "k/what/fix-bug"])

        # AND: both keys must match
        results = index.search(["k/who/admin", "k/what/fix-bug"], operator="AND")
        assert results == ["req-001"]

    def test_add_and_search_or(self, tmp_path: Path) -> None:
        index = self._make_index(tmp_path)
        index.add("req-001", ["k/who/admin"])
        index.add("req-002", ["k/what/fix-bug"])

        results = index.search(["k/who/admin", "k/what/fix-bug"], operator="OR")
        assert set(results) == {"req-001", "req-002"}

    def test_remove(self, tmp_path: Path) -> None:
        index = self._make_index(tmp_path)
        index.add("req-001", ["k/who/admin", "k/what/fix-bug"])
        index.remove("req-001")

        results = index.search(["k/who/admin"], operator="AND")
        assert results == []

    def test_get_related(self, tmp_path: Path) -> None:
        index = self._make_index(tmp_path)
        index.add("req-001", ["k/who/admin", "k/what/fix-bug", "k/where/eng"])
        index.add("req-002", ["k/who/admin", "k/what/fix-bug"])
        index.add("req-003", ["k/who/admin"])

        related = index.get_related("req-001", top_k=5)
        # req-002 shares 2 facets, req-003 shares 1
        assert related[0] == "req-002"
        assert "req-003" in related

    def test_persistence(self, tmp_path: Path) -> None:
        index_path = tmp_path / "facet_index.yaml"
        index = FacetIndex(index_path)
        index.add("req-001", ["k/who/admin"])
        index.save()

        # Reload
        index2 = FacetIndex(index_path)
        results = index2.search(["k/who/admin"], operator="AND")
        assert results == ["req-001"]

    def test_empty_search(self, tmp_path: Path) -> None:
        index = self._make_index(tmp_path)
        assert index.search([], operator="AND") == []
        assert index.search([], operator="OR") == []

    def test_get_facets_for_record(self, tmp_path: Path) -> None:
        index = self._make_index(tmp_path)
        index.add("req-001", ["k/who/admin", "k/what/fix-bug"])
        facets = index.get_facets_for_record("req-001")
        assert set(facets) == {"k/who/admin", "k/what/fix-bug"}

    def test_get_all_record_ids(self, tmp_path: Path) -> None:
        index = self._make_index(tmp_path)
        index.add("req-001", ["k/who/admin"])
        index.add("req-002", ["k/who/other"])
        ids = index.get_all_record_ids()
        assert set(ids) == {"req-001", "req-002"}
