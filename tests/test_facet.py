"""Tests for facet key utilities."""

import pytest

from ultrawork.memory.facet import (
    create_facet_key,
    extract_facets_from_record,
    normalize_facet_value,
    parse_facet_key,
)
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


class TestNormalizeFacetValue:
    def test_lowercase(self) -> None:
        assert normalize_facet_value("HelloWorld") == "helloworld"

    def test_spaces_to_hyphens(self) -> None:
        assert normalize_facet_value("hello world") == "hello-world"

    def test_underscores_to_hyphens(self) -> None:
        assert normalize_facet_value("hello_world") == "hello-world"

    def test_dots_to_hyphens(self) -> None:
        assert normalize_facet_value("path.to.file") == "path-to-file"

    def test_collapse_hyphens(self) -> None:
        assert normalize_facet_value("hello---world") == "hello-world"

    def test_strip_special(self) -> None:
        assert normalize_facet_value("hello!@#world") == "helloworld"

    def test_empty_returns_unknown(self) -> None:
        assert normalize_facet_value("") == "unknown"
        assert normalize_facet_value("!!!") == "unknown"


class TestCreateFacetKey:
    def test_basic(self) -> None:
        assert create_facet_key("who", "admin") == "k/who/admin"

    def test_normalizes_value(self) -> None:
        assert create_facet_key("what", "Fix Bug") == "k/what/fix-bug"

    def test_complex_value(self) -> None:
        assert create_facet_key("where", "eng_common/thread") == "k/where/eng-common-thread"


class TestParseFacetKey:
    def test_valid(self) -> None:
        facet, value = parse_facet_key("k/who/admin")
        assert facet == "who"
        assert value == "admin"

    def test_value_with_hyphens(self) -> None:
        facet, value = parse_facet_key("k/what/fix-search-bug")
        assert facet == "what"
        assert value == "fix-search-bug"

    def test_invalid_no_prefix(self) -> None:
        with pytest.raises(ValueError, match="Must start with"):
            parse_facet_key("who/admin")

    def test_invalid_no_value(self) -> None:
        with pytest.raises(ValueError, match="Expected"):
            parse_facet_key("k/who")


class TestExtractFacetsFromRecord:
    def test_request_record(self) -> None:
        record = RequestRecord(
            id="req-20260226-0001",
            who="user123",
            where="eng-common",
            what="Fix search indexer",
            why=[WhyHypothesis(hypothesis="Search is slow")],
            how=[HowStep(step_id="s01", goal="Profile query")],
        )
        facets = extract_facets_from_record(record)
        assert "k/who/user123" in facets
        assert "k/where/eng-common" in facets
        assert "k/req/req-20260226-0001" in facets
        assert "k/step/s01" in facets
        assert any(f.startswith("k/what/") for f in facets)
        assert any(f.startswith("k/why/") for f in facets)
        assert any(f.startswith("k/how/") for f in facets)

    def test_work_record(self) -> None:
        record = WorkRecord(
            id="work-20260226-req-20260226-0001-01",
            who="claude",
            why=WorkWhy(
                kind=WorkWhyKind.ADVANCE_STEP,
                step_ref="req-20260226-0001#s01",
            ),
            where=WorkWhere(inputs=["src/search.py"]),
            what=[WorkAction(action="Read file")],
        )
        facets = extract_facets_from_record(record)
        assert "k/who/claude" in facets
        assert "k/req/req-20260226-0001" in facets
        assert "k/step/s01" in facets
        assert "k/why/advance-step" in facets

    def test_deduplication(self) -> None:
        record = RequestRecord(
            id="req-20260226-0001",
            who="admin",
            what="admin task",
        )
        facets = extract_facets_from_record(record)
        assert len(facets) == len(set(facets))
