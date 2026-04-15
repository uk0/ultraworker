"""Long-Term Memory ontology models.

RequestRecord and WorkRecord form the "Graphless Graph" architecture:
- FacetKey (implicit edges) for facet-based linking
- ShallowLink (explicit edges) for direct record-to-record connections
- CausalLink for causal chain tracking (caused_by, leads_to, blocks, supersedes)
- 2-stage save policy (Draft/Commit) to prevent log pollution
"""

from __future__ import annotations

import re
from datetime import datetime
from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field, field_validator

SCHEMA_VERSION = 1

# --- Primitive types ---

FACET_KEY_PATTERN = re.compile(r"^k/[a-z]+/[a-z0-9][a-z0-9\-]*$")


class FacetKey(str):
    """Facet key in the form k/<facet>/<value>.

    Facets are kebab-case identifiers used as implicit graph edges.
    Required facets: who, where, what, why, how, req, step.
    """

    @classmethod
    def __get_validators__(cls):  # noqa: N805 – Pydantic v1 compat
        yield cls._validate

    @classmethod
    def _validate(cls, v: str) -> FacetKey:
        if not isinstance(v, str):
            raise TypeError("FacetKey must be a string")
        if not FACET_KEY_PATTERN.match(v):
            raise ValueError(f"Invalid FacetKey format: {v!r}. Expected k/<facet>/<value>")
        return cls(v)

    @classmethod
    def __get_pydantic_core_schema__(cls, _source_type, _handler):  # noqa: N805
        from pydantic import GetCoreSchemaHandler  # noqa: F401
        from pydantic_core import core_schema

        return core_schema.no_info_plain_validator_function(
            cls._validate,
            serialization=core_schema.to_string_ser_schema(),
        )


class URI(str):
    """A URI reference (file://, http://, slack://, etc.)."""

    URI_PATTERN = re.compile(r"^[a-z][a-z0-9+\-.]*://")

    @classmethod
    def _validate(cls, v: str) -> URI:
        if not isinstance(v, str):
            raise TypeError("URI must be a string")
        if not cls.URI_PATTERN.match(v):
            raise ValueError(f"Invalid URI scheme: {v!r}")
        return cls(v)

    @classmethod
    def __get_pydantic_core_schema__(cls, _source_type, _handler):  # noqa: N805
        from pydantic_core import core_schema

        return core_schema.no_info_plain_validator_function(
            cls._validate,
            serialization=core_schema.to_string_ser_schema(),
        )


# --- Enums ---


class RecordType(str, Enum):
    """Type discriminator for LTM records."""

    REQUEST = "request"
    WORK = "work"
    KNOWLEDGE = "knowledge"
    DECISION = "decision"
    INSIGHT = "insight"
    EVENT = "event"


class LinkRelation(str, Enum):
    """Relation types for shallow links."""

    PARENT = "parent"
    CHILD = "child"
    RELATED = "related"
    DERIVED_FROM = "derived_from"
    SUPERSEDES = "supersedes"
    BLOCKED_BY = "blocked_by"
    IMPLEMENTS = "implements"


class WorkWhyKind(str, Enum):
    """Why-kind for WorkRecord."""

    ADVANCE_STEP = "advance_step"
    DISCOVERY = "discovery"
    MAINTENANCE = "maintenance"


class CausalRelation(str, Enum):
    """Causal relationship types between records."""

    CAUSED_BY = "caused_by"
    LEADS_TO = "leads_to"
    BLOCKS = "blocks"
    SUPERSEDES = "supersedes"


# --- Shared sub-models ---


class WhyHypothesis(BaseModel):
    """A hypothesis about why the request exists."""

    hypothesis: str
    confidence: float = Field(ge=0.0, le=1.0, default=0.5)
    evidence: list[str] = Field(default_factory=list)


class HowStep(BaseModel):
    """A single step in a request's execution plan."""

    step_id: str
    goal: str
    done: bool = False
    expected_artifacts: list[str] = Field(default_factory=list)
    related_queries: list[str] = Field(default_factory=list)


class Discovery(BaseModel):
    """An unexpected finding during exploration or work."""

    description: str
    facet_keys: list[str] = Field(default_factory=list)
    evidence: list[str] = Field(default_factory=list)


class ShallowLink(BaseModel):
    """An explicit link to another record."""

    target_id: str
    relation: LinkRelation = LinkRelation.RELATED
    weight: float = Field(ge=0.0, le=1.0, default=0.5)


class CausalLink(BaseModel):
    """A causal relationship to another record."""

    target_id: str
    relation: CausalRelation
    reason: str = ""


class SaveSignals(BaseModel):
    """4-Signal Gate evaluation result for save decisions."""

    novelty: bool = False
    actionability: bool = False
    persistence: bool = False
    connectedness: bool = False

    @property
    def score(self) -> int:
        return sum([self.novelty, self.actionability, self.persistence, self.connectedness])


# --- WorkRecord sub-models ---


class WorkAction(BaseModel):
    """A single action performed during work."""

    action: str
    output: str = ""


class WorkWhy(BaseModel):
    """Why this work was performed."""

    kind: WorkWhyKind = WorkWhyKind.ADVANCE_STEP
    step_ref: str | None = None  # format: "req-YYYYMMDD-NNNN#step_id"
    immediate_goal: str = ""
    causality: list[CausalLink] = Field(default_factory=list)


class WorkWhere(BaseModel):
    """Input/output locations for work."""

    inputs: list[str] = Field(default_factory=list)
    outputs: list[str] = Field(default_factory=list)


# --- Primary record models ---


class RequestRecord(BaseModel):
    """A request record capturing a user/system ask.

    ID format: req-YYYYMMDD-NNNN (e.g. req-20260226-0001)
    """

    id: str
    type: Literal["request"] = "request"
    schema_version: int = SCHEMA_VERSION

    # 5W1H
    who: str = ""  # requester identifier
    when: datetime = Field(default_factory=datetime.now)
    where: str = ""  # source channel/context
    what: str = ""  # concise description
    why: list[WhyHypothesis] = Field(default_factory=list)
    how: list[HowStep] = Field(default_factory=list)

    # Semantic metadata
    topics: list[str] = Field(default_factory=list)

    # Discoveries made during exploration
    discoveries: list[Discovery] = Field(default_factory=list)

    # Facet keys for implicit graph edges
    facet_keys: list[str] = Field(default_factory=list)

    # Explicit links to other records
    links: list[ShallowLink] = Field(default_factory=list)

    # Causal chain links
    causality: list[CausalLink] = Field(default_factory=list)

    # Artifact URIs
    touched_uris: list[str] = Field(default_factory=list)
    produced_uris: list[str] = Field(default_factory=list)

    # Deduplication
    dedupe_key: str = ""

    # Save signals (recorded at commit time)
    save_signals: SaveSignals | None = None

    # Metadata
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)

    @field_validator("id")
    @classmethod
    def validate_id(cls, v: str) -> str:
        if not re.match(r"^req-\d{8}-\d{4}$", v):
            raise ValueError(f"Invalid RequestRecord ID format: {v!r}. Expected req-YYYYMMDD-NNNN")
        return v


class WorkRecord(BaseModel):
    """A work record capturing an action taken by the agent.

    ID format: work-YYYYMMDD-<req_id>-NN (e.g. work-20260226-req-20260226-0001-01)
    """

    id: str
    type: Literal["work"] = "work"
    schema_version: int = SCHEMA_VERSION

    # Context
    who: str = ""  # executor identifier
    when: datetime = Field(default_factory=datetime.now)

    # Purpose
    why: WorkWhy = Field(default_factory=WorkWhy)

    # Explicit request reference (for direct tracking)
    request_ref: str | None = None  # e.g. "req-20260226-0001"

    # Location
    where: WorkWhere = Field(default_factory=WorkWhere)

    # Actions taken
    what: list[WorkAction] = Field(default_factory=list)

    # Semantic metadata
    topics: list[str] = Field(default_factory=list)

    # Evidence / outputs
    evidence: list[str] = Field(default_factory=list)

    # Facet keys for implicit graph edges
    facet_keys: list[str] = Field(default_factory=list)

    # Explicit links to other records
    links: list[ShallowLink] = Field(default_factory=list)

    # Artifact URIs
    touched_uris: list[str] = Field(default_factory=list)
    produced_uris: list[str] = Field(default_factory=list)

    # Deduplication
    dedupe_key: str = ""

    # Save signals (recorded at commit time)
    save_signals: SaveSignals | None = None

    # Metadata
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)

    @field_validator("id")
    @classmethod
    def validate_id(cls, v: str) -> str:
        if not re.match(r"^work-\d{8}-req-\d{8}-\d{4}-\d{2}$", v):
            raise ValueError(
                f"Invalid WorkRecord ID format: {v!r}. Expected work-YYYYMMDD-req-YYYYMMDD-NNNN-NN"
            )
        return v


# --- Semantic memory records ---


class _BaseSemanticRecord(BaseModel):
    """Shared base for knowledge/decision/insight/event records.

    These records use a simpler schema than Request/Work:
    ID prefix determines the type, body is freeform markdown.
    """

    id: str
    schema_version: int = SCHEMA_VERSION
    who: str = ""
    when: datetime = Field(default_factory=datetime.now)
    where: str = ""
    what: str = ""
    topics: list[str] = Field(default_factory=list)
    facet_keys: list[str] = Field(default_factory=list)
    links: list[ShallowLink] = Field(default_factory=list)
    dedupe_key: str = ""
    save_signals: SaveSignals | None = None
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)


class KnowledgeRecord(_BaseSemanticRecord):
    """Factual knowledge: channel summaries, doc summaries, API specs, etc.

    ID format: know-XXXXXXXX
    """

    type: Literal["knowledge"] = "knowledge"
    source: str = ""  # origin: "channel-history", "document", "api-spec", etc.
    period: str = ""  # time range if applicable: "2026-Q1"
    summary: str = ""

    @field_validator("id")
    @classmethod
    def validate_id(cls, v: str) -> str:
        if not re.match(r"^know-[a-f0-9]{8}$", v):
            raise ValueError(f"Invalid KnowledgeRecord ID: {v!r}. Expected know-XXXXXXXX")
        return v


class DecisionRecord(_BaseSemanticRecord):
    """Architectural/policy decisions with rationale.

    ID format: dec-YYYYMMDD-NNNN
    """

    type: Literal["decision"] = "decision"
    context: str = ""  # why decision was needed
    alternatives: list[str] = Field(default_factory=list)
    rationale: str = ""
    outcome: str = ""

    @field_validator("id")
    @classmethod
    def validate_id(cls, v: str) -> str:
        if not re.match(r"^dec-\d{8}-\d{4}$", v):
            raise ValueError(f"Invalid DecisionRecord ID: {v!r}. Expected dec-YYYYMMDD-NNNN")
        return v


class InsightRecord(_BaseSemanticRecord):
    """Patterns, lessons learned, best practices.

    ID format: ins-XXXXXXXX
    """

    type: Literal["insight"] = "insight"
    pattern: str = ""
    evidence: list[str] = Field(default_factory=list)
    implication: str = ""

    @field_validator("id")
    @classmethod
    def validate_id(cls, v: str) -> str:
        if not re.match(r"^ins-[a-f0-9]{8}$", v):
            raise ValueError(f"Invalid InsightRecord ID: {v!r}. Expected ins-XXXXXXXX")
        return v


class EventRecord(_BaseSemanticRecord):
    """Incidents, deployments, milestones.

    ID format: evt-YYYYMMDD-NNNN
    """

    type: Literal["event"] = "event"
    severity: str = ""  # critical, high, medium, low
    impact: str = ""
    resolution: str = ""

    @field_validator("id")
    @classmethod
    def validate_id(cls, v: str) -> str:
        if not re.match(r"^evt-\d{8}-\d{4}$", v):
            raise ValueError(f"Invalid EventRecord ID: {v!r}. Expected evt-YYYYMMDD-NNNN")
        return v
