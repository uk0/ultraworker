"""Tests for LTM data models."""

import pytest

from ultrawork.models.ltm import (
    URI,
    Discovery,
    FacetKey,
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


class TestFacetKey:
    def test_valid_facet_key(self) -> None:
        key = FacetKey._validate("k/who/admin")
        assert key == "k/who/admin"

    def test_invalid_format_no_prefix(self) -> None:
        with pytest.raises(ValueError, match="Invalid FacetKey"):
            FacetKey._validate("who/admin")

    def test_invalid_format_uppercase(self) -> None:
        with pytest.raises(ValueError, match="Invalid FacetKey"):
            FacetKey._validate("k/WHO/admin")


class TestURI:
    def test_valid_uri(self) -> None:
        uri = URI._validate("file:///tmp/test.py")
        assert uri == "file:///tmp/test.py"

    def test_valid_http(self) -> None:
        uri = URI._validate("https://example.com")
        assert uri == "https://example.com"

    def test_invalid_no_scheme(self) -> None:
        with pytest.raises(ValueError, match="Invalid URI"):
            URI._validate("/tmp/test.py")


class TestRequestRecord:
    def test_create_minimal(self) -> None:
        record = RequestRecord(id="req-20260226-0001")
        assert record.type == "request"
        assert record.who == ""
        assert record.facet_keys == []
        assert record.links == []

    def test_create_full(self) -> None:
        record = RequestRecord(
            id="req-20260226-0001",
            who="user123",
            where="eng-common",
            what="Fix the search indexer",
            why=[
                WhyHypothesis(
                    hypothesis="Search is slow", confidence=0.8, evidence=["latency > 5s"]
                )
            ],
            how=[HowStep(step_id="s01", goal="Profile query", expected_artifacts=["profile.json"])],
            discoveries=[
                Discovery(description="Found N+1 query", facet_keys=["k/what/n-plus-one"])
            ],
            facet_keys=["k/who/user123", "k/what/fix-search"],
            links=[ShallowLink(target_id="req-20260226-0002", relation=LinkRelation.RELATED)],
        )
        assert record.who == "user123"
        assert len(record.why) == 1
        assert record.why[0].confidence == 0.8
        assert len(record.how) == 1
        assert record.how[0].step_id == "s01"
        assert len(record.discoveries) == 1
        assert len(record.links) == 1

    def test_invalid_id(self) -> None:
        with pytest.raises(ValueError, match="Invalid RequestRecord ID"):
            RequestRecord(id="bad-id")

    def test_valid_id_pattern(self) -> None:
        record = RequestRecord(id="req-20260226-0001")
        assert record.id == "req-20260226-0001"


class TestWorkRecord:
    def test_create_minimal(self) -> None:
        record = WorkRecord(id="work-20260226-req-20260226-0001-01")
        assert record.type == "work"
        assert record.why.kind == WorkWhyKind.ADVANCE_STEP

    def test_create_with_actions(self) -> None:
        record = WorkRecord(
            id="work-20260226-req-20260226-0001-01",
            who="claude",
            why=WorkWhy(
                kind=WorkWhyKind.ADVANCE_STEP,
                step_ref="req-20260226-0001#s01",
                immediate_goal="Profile the query",
            ),
            where=WorkWhere(inputs=["file:///src/search.py"], outputs=["file:///profile.json"]),
            what=[WorkAction(action="Ran profiler", output="95% time in query loop")],
            evidence=["profile.json shows N+1 pattern"],
        )
        assert record.who == "claude"
        assert record.why.step_ref == "req-20260226-0001#s01"
        assert len(record.what) == 1
        assert len(record.where.inputs) == 1

    def test_invalid_id(self) -> None:
        with pytest.raises(ValueError, match="Invalid WorkRecord ID"):
            WorkRecord(id="work-bad")


class TestHowStep:
    def test_atomicity(self) -> None:
        step = HowStep(step_id="s01", goal="Build feature", expected_artifacts=["a.py", "b.py"])
        assert len(step.expected_artifacts) == 2
        assert not step.done

    def test_mark_done(self) -> None:
        step = HowStep(step_id="s01", goal="Test", done=True)
        assert step.done


class TestShallowLink:
    def test_defaults(self) -> None:
        link = ShallowLink(target_id="req-20260226-0002")
        assert link.relation == LinkRelation.RELATED
        assert link.weight == 0.5

    def test_custom_weight(self) -> None:
        link = ShallowLink(target_id="req-20260226-0002", weight=0.9)
        assert link.weight == 0.9
