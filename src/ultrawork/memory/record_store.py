"""RequestRecord/WorkRecord CRUD and file management.

Records are stored as YAML-frontmatter Markdown files:
- data/memory/requests/req-YYYYMMDD-NNNN.md
- data/memory/works/work-YYYYMMDD-req-YYYYMMDD-NNNN-NN.md

Uses atomic writes (write-to-tmp + rename) for file safety.
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any

import frontmatter
import yaml

from ultrawork.memory.facet import extract_facets_from_record
from ultrawork.memory.facet_index import FacetIndex, _atomic_write
from ultrawork.memory.redact import redact_secrets
from ultrawork.models.ltm import (
    CausalLink,
    CausalRelation,
    DecisionRecord,
    Discovery,
    EventRecord,
    HowStep,
    InsightRecord,
    KnowledgeRecord,
    LinkRelation,
    RequestRecord,
    SaveSignals,
    ShallowLink,
    WhyHypothesis,
    WorkAction,
    WorkRecord,
    WorkWhere,
    WorkWhy,
    WorkWhyKind,
    _BaseSemanticRecord,
)


def _datetime_representer(dumper: yaml.Dumper, data: datetime) -> yaml.ScalarNode:
    return dumper.represent_scalar("tag:yaml.org,2002:timestamp", data.isoformat())


yaml.add_representer(datetime, _datetime_representer)

logger = logging.getLogger(__name__)


class RecordStore:
    """CRUD layer for RequestRecord and WorkRecord files."""

    def __init__(self, data_dir: Path | str, facet_index: FacetIndex | None = None) -> None:
        """Initialize the record store.

        Args:
            data_dir: Base data directory (e.g. data/)
            facet_index: Optional shared FacetIndex instance
        """
        self.data_dir = Path(data_dir)
        self.requests_dir = self.data_dir / "memory" / "requests"
        self.works_dir = self.data_dir / "memory" / "works"
        self.knowledge_dir = self.data_dir / "memory" / "knowledge"
        self.decisions_dir = self.data_dir / "memory" / "decisions"
        self.insights_dir = self.data_dir / "memory" / "insights"
        self.events_dir = self.data_dir / "memory" / "events"
        self.index_dir = self.data_dir / "memory" / "index"

        # Type prefix -> (directory, glob pattern, model class)
        self._type_registry: dict[str, tuple[Path, str, type]] = {
            "knowledge": (self.knowledge_dir, "know-*.md", KnowledgeRecord),
            "decision": (self.decisions_dir, "dec-*.md", DecisionRecord),
            "insight": (self.insights_dir, "ins-*.md", InsightRecord),
            "event": (self.events_dir, "evt-*.md", EventRecord),
        }

        for d in [
            self.requests_dir, self.works_dir, self.knowledge_dir,
            self.decisions_dir, self.insights_dir, self.events_dir, self.index_dir,
        ]:
            d.mkdir(parents=True, exist_ok=True)

        self.facet_index = facet_index or FacetIndex(self.index_dir / "facet_index.yaml")
        self._search_binary: str | None = None
        self._search_binary_checked = False

    # --- Rust memory-search CLI integration ---

    def _get_search_binary(self) -> str | None:
        """Find the memory-search binary path (cached)."""
        if self._search_binary_checked:
            return self._search_binary
        self._search_binary_checked = True

        # 1. Environment variable
        env_bin = os.environ.get("MEMORY_SEARCH_BIN", "")
        if env_bin and Path(env_bin).is_file():
            self._search_binary = env_bin
            return self._search_binary

        # 2. Project vendored location
        vendored_bin = (
            self.data_dir.parent
            / "vendor"
            / "memory-search"
            / "target"
            / "release"
            / "memory-search"
        )
        if vendored_bin.is_file():
            self._search_binary = str(vendored_bin)
            return self._search_binary

        # 3. Well-known location
        home_bin = Path.home() / "memory-search" / "target" / "release" / "memory-search"
        if home_bin.is_file():
            self._search_binary = str(home_bin)
            return self._search_binary

        # 4. PATH lookup
        which = shutil.which("memory-search")
        if which:
            self._search_binary = which
            return self._search_binary

        return None

    def _notify_index(self, record_id: str) -> None:
        """Fire-and-forget: ask Rust CLI to index a record."""
        binary = self._get_search_binary()
        if not binary:
            return
        try:
            subprocess.Popen(
                [binary, "index", record_id, "--data-dir", str(self.data_dir)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except Exception as exc:
            logger.debug("memory-search index failed: %s", exc)

    def _notify_remove(self, record_id: str) -> None:
        """Fire-and-forget: ask Rust CLI to remove a record from index."""
        binary = self._get_search_binary()
        if not binary:
            return
        try:
            subprocess.Popen(
                [binary, "remove", record_id, "--data-dir", str(self.data_dir)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except Exception as exc:
            logger.debug("memory-search remove failed: %s", exc)

    # --- ID generation ---

    def generate_request_id(self) -> str:
        """Generate a new RequestRecord ID.

        Format: req-YYYYMMDD-NNNN (sequential within the day).
        """
        today = datetime.now().strftime("%Y%m%d")
        existing = sorted(self.requests_dir.glob(f"req-{today}-*.md"))
        if existing:
            last = existing[-1].stem  # e.g. req-20260226-0003
            last_seq = int(last.split("-")[-1])
            seq = last_seq + 1
        else:
            seq = 1
        return f"req-{today}-{seq:04d}"

    def generate_work_id(self, request_id: str) -> str:
        """Generate a new WorkRecord ID for a given request.

        Format: work-YYYYMMDD-<req_id>-NN (sequential per request per day).
        """
        today = datetime.now().strftime("%Y%m%d")
        pattern = f"work-{today}-{request_id}-*.md"
        existing = sorted(self.works_dir.glob(pattern))
        if existing:
            last = existing[-1].stem
            last_seq = int(last.rsplit("-", 1)[-1])
            seq = last_seq + 1
        else:
            seq = 1
        return f"work-{today}-{request_id}-{seq:02d}"

    # --- RequestRecord CRUD ---

    def save_request(self, record: RequestRecord, *, redact: bool = True) -> Path:
        """Save a RequestRecord as a frontmatter Markdown file.

        Auto-extracts facets, redacts secrets, and updates index.

        Args:
            record: The RequestRecord to save
            redact: Whether to apply secret redaction (default True)

        Returns:
            Path to the saved file
        """
        auto_facets = extract_facets_from_record(record)
        merged = list(dict.fromkeys(record.facet_keys + auto_facets))
        record.facet_keys = merged
        record.updated_at = datetime.now()

        metadata = self._request_to_metadata(record)
        body = self._build_request_body(record)

        if redact:
            body = redact_secrets(body)

        content = self._serialize_frontmatter(metadata, body)
        file_path = self.requests_dir / f"{record.id}.md"
        _atomic_write(file_path, content)

        self.facet_index.add(record.id, record.facet_keys)
        self._notify_index(record.id)
        return file_path

    def load_request(self, record_id: str) -> RequestRecord | None:
        """Load a RequestRecord from disk.

        Args:
            record_id: The request ID

        Returns:
            RequestRecord or None if not found
        """
        file_path = self.requests_dir / f"{record_id}.md"
        if not file_path.exists():
            return None
        return self._parse_request(file_path)

    def list_requests(self, **filters: Any) -> list[RequestRecord]:
        """List all RequestRecords, optionally filtered.

        Args:
            **filters: Optional filters (who, where, etc.)

        Returns:
            List of matching RequestRecords
        """
        records = []
        for path in sorted(self.requests_dir.glob("req-*.md")):
            record = self._parse_request(path)
            if record and self._matches_filters(record, filters):
                records.append(record)
        return records

    def delete_request(self, record_id: str) -> bool:
        """Delete a RequestRecord file and remove from index.

        Args:
            record_id: The request ID

        Returns:
            True if deleted
        """
        file_path = self.requests_dir / f"{record_id}.md"
        if not file_path.exists():
            return False
        file_path.unlink()
        self.facet_index.remove(record_id)
        self._notify_remove(record_id)
        return True

    # --- WorkRecord CRUD ---

    def save_work(self, record: WorkRecord, *, redact: bool = True) -> Path:
        """Save a WorkRecord as a frontmatter Markdown file.

        Auto-extracts facets, redacts secrets, and updates index.

        Args:
            record: The WorkRecord to save
            redact: Whether to apply secret redaction (default True)

        Returns:
            Path to the saved file
        """
        auto_facets = extract_facets_from_record(record)
        merged = list(dict.fromkeys(record.facet_keys + auto_facets))
        record.facet_keys = merged
        record.updated_at = datetime.now()

        metadata = self._work_to_metadata(record)
        body = self._build_work_body(record)

        if redact:
            body = redact_secrets(body)

        content = self._serialize_frontmatter(metadata, body)
        file_path = self.works_dir / f"{record.id}.md"
        _atomic_write(file_path, content)

        self.facet_index.add(record.id, record.facet_keys)
        self._notify_index(record.id)
        return file_path

    def load_work(self, record_id: str) -> WorkRecord | None:
        """Load a WorkRecord from disk.

        Args:
            record_id: The work record ID

        Returns:
            WorkRecord or None if not found
        """
        file_path = self.works_dir / f"{record_id}.md"
        if not file_path.exists():
            return None
        return self._parse_work(file_path)

    def list_works(self, **filters: Any) -> list[WorkRecord]:
        """List all WorkRecords, optionally filtered.

        Args:
            **filters: Optional filters (who, etc.)

        Returns:
            List of matching WorkRecords
        """
        records = []
        for path in sorted(self.works_dir.glob("work-*.md")):
            record = self._parse_work(path)
            if record and self._matches_filters(record, filters):
                records.append(record)
        return records

    def delete_work(self, record_id: str) -> bool:
        """Delete a WorkRecord file and remove from index.

        Args:
            record_id: The work record ID

        Returns:
            True if deleted
        """
        file_path = self.works_dir / f"{record_id}.md"
        if not file_path.exists():
            return False
        file_path.unlink()
        self.facet_index.remove(record_id)
        self._notify_remove(record_id)
        return True

    # --- Semantic record CRUD (knowledge, decision, insight, event) ---

    def save_semantic(self, record: _BaseSemanticRecord, *, redact: bool = True) -> Path:
        """Save a semantic record (knowledge/decision/insight/event)."""
        record.updated_at = datetime.now()

        metadata = record.model_dump(mode="json")
        # Pop body-like fields to put in markdown body
        body_parts = [f"# {record.what or record.id}"]
        for field in ("summary", "context", "rationale", "outcome",
                       "pattern", "implication", "impact", "resolution"):
            val = getattr(record, field, None)
            if val:
                body_parts.append(f"\n## {field.title()}\n{val}")
        for field in ("alternatives", "evidence"):
            val = getattr(record, field, None)
            if val:
                body_parts.append(f"\n## {field.title()}")
                for item in val:
                    body_parts.append(f"- {item}")
        body = "\n".join(body_parts)

        if redact:
            body = redact_secrets(body)

        content = self._serialize_frontmatter(metadata, body)

        type_name = record.type
        dir_path, _, _ = self._type_registry[type_name]
        file_path = dir_path / f"{record.id}.md"
        _atomic_write(file_path, content)

        self.facet_index.add(record.id, record.facet_keys)
        self._notify_index(record.id)
        return file_path

    def load_semantic(self, record_id: str) -> _BaseSemanticRecord | None:
        """Load a semantic record by ID prefix detection."""
        type_name = self._detect_type(record_id)
        if not type_name or type_name not in self._type_registry:
            return None
        dir_path, _, model_cls = self._type_registry[type_name]
        file_path = dir_path / f"{record_id}.md"
        if not file_path.exists():
            return None
        return self._parse_semantic(file_path, model_cls)

    def list_semantic(self, type_name: str) -> list[_BaseSemanticRecord]:
        """List all records of a semantic type."""
        if type_name not in self._type_registry:
            return []
        dir_path, pattern, model_cls = self._type_registry[type_name]
        records = []
        for path in sorted(dir_path.glob(pattern)):
            rec = self._parse_semantic(path, model_cls)
            if rec:
                records.append(rec)
        return records

    def delete_semantic(self, record_id: str) -> bool:
        """Delete a semantic record."""
        type_name = self._detect_type(record_id)
        if not type_name or type_name not in self._type_registry:
            return False
        dir_path, _, _ = self._type_registry[type_name]
        file_path = dir_path / f"{record_id}.md"
        if not file_path.exists():
            return False
        file_path.unlink()
        self.facet_index.remove(record_id)
        self._notify_remove(record_id)
        return True

    @staticmethod
    def _detect_type(record_id: str) -> str | None:
        """Detect record type from ID prefix."""
        prefix_map = {
            "know-": "knowledge",
            "dec-": "decision",
            "ins-": "insight",
            "evt-": "event",
        }
        for prefix, type_name in prefix_map.items():
            if record_id.startswith(prefix):
                return type_name
        return None

    def _parse_semantic(self, file_path: Path, model_cls: type) -> _BaseSemanticRecord | None:
        """Parse a semantic record from frontmatter markdown."""
        try:
            post = frontmatter.load(file_path)
            meta = post.metadata
            links = [
                ShallowLink(
                    target_id=lnk["target_id"],
                    relation=LinkRelation(lnk.get("relation", "related")),
                    weight=lnk.get("weight", 0.5),
                )
                for lnk in meta.get("links", [])
            ]
            save_signals = None
            if "save_signals" in meta:
                save_signals = SaveSignals(**meta["save_signals"])
            return model_cls(
                **{
                    k: v
                    for k, v in meta.items()
                    if k not in ("links", "save_signals")
                },
                links=links,
                save_signals=save_signals,
            )
        except Exception:
            return None

    # --- Serialization helpers ---

    @staticmethod
    def _serialize_frontmatter(metadata: dict[str, Any], body: str) -> str:
        """Serialize metadata and body into frontmatter markdown."""
        post = frontmatter.Post(body, **metadata)
        return frontmatter.dumps(post)

    def _build_request_body(self, record: RequestRecord) -> str:
        """Build markdown body for a RequestRecord."""
        parts = [f"# {' '.join(record.facet_keys[:10])}"]

        parts.append("\n## What")
        parts.append(record.what or "[No description]")

        if record.why:
            parts.append("\n## Why")
            for h in record.why:
                parts.append(f"- **{h.hypothesis}** (confidence: {h.confidence})")
                for e in h.evidence:
                    parts.append(f"  - {e}")

        if record.how:
            parts.append("\n## How (Steps)")
            for step in record.how:
                check = "x" if step.done else " "
                parts.append(f"- [{check}] `{step.step_id}`: {step.goal}")
                for artifact in step.expected_artifacts:
                    parts.append(f"  - artifact: {artifact}")

        if record.discoveries:
            parts.append("\n## Discoveries")
            for disc in record.discoveries:
                parts.append(f"- {disc.description}")

        if record.causality:
            parts.append("\n## Causal Links")
            for cl in record.causality:
                parts.append(f"- {cl.relation.value}: {cl.target_id}")
                if cl.reason:
                    parts.append(f"  - {cl.reason}")

        return "\n".join(parts)

    def _build_work_body(self, record: WorkRecord) -> str:
        """Build markdown body for a WorkRecord."""
        parts = [f"# {' '.join(record.facet_keys[:10])}"]

        parts.append("\n## Purpose")
        parts.append(f"Kind: {record.why.kind.value}")
        if record.why.step_ref:
            parts.append(f"Step ref: {record.why.step_ref}")
        if record.why.immediate_goal:
            parts.append(f"Goal: {record.why.immediate_goal}")

        if record.what:
            parts.append("\n## Actions")
            for action in record.what:
                parts.append(f"- **{action.action}**")
                if action.output:
                    parts.append(f"  ```\n  {action.output}\n  ```")

        if record.evidence:
            parts.append("\n## Evidence")
            for e in record.evidence:
                parts.append(f"- {e}")

        if record.why.causality:
            parts.append("\n## Causal Links")
            for cl in record.why.causality:
                parts.append(f"- {cl.relation.value}: {cl.target_id}")
                if cl.reason:
                    parts.append(f"  - {cl.reason}")

        return "\n".join(parts)

    def _request_to_metadata(self, record: RequestRecord) -> dict[str, Any]:
        """Convert RequestRecord to frontmatter metadata dict."""
        metadata: dict[str, Any] = {
            "id": record.id,
            "type": record.type,
            "schema_version": record.schema_version,
            "who": record.who,
            "when": record.when,
            "where": record.where,
            "topics": record.topics,
            "created_at": record.created_at,
            "updated_at": record.updated_at,
            "facet_keys": record.facet_keys,
        }
        if record.why:
            metadata["why"] = [h.model_dump(mode="json") for h in record.why]
        if record.how:
            metadata["how"] = [s.model_dump(mode="json") for s in record.how]
        if record.discoveries:
            metadata["discoveries"] = [d.model_dump(mode="json") for d in record.discoveries]
        if record.links:
            metadata["links"] = [lnk.model_dump(mode="json") for lnk in record.links]
        if record.causality:
            metadata["causality"] = [cl.model_dump(mode="json") for cl in record.causality]
        if record.touched_uris:
            metadata["touched_uris"] = record.touched_uris
        if record.produced_uris:
            metadata["produced_uris"] = record.produced_uris
        if record.dedupe_key:
            metadata["dedupe_key"] = record.dedupe_key
        if record.save_signals:
            metadata["save_signals"] = record.save_signals.model_dump(mode="json")
        return metadata

    def _work_to_metadata(self, record: WorkRecord) -> dict[str, Any]:
        """Convert WorkRecord to frontmatter metadata dict."""
        metadata: dict[str, Any] = {
            "id": record.id,
            "type": record.type,
            "schema_version": record.schema_version,
            "who": record.who,
            "when": record.when,
            "topics": record.topics,
            "created_at": record.created_at,
            "updated_at": record.updated_at,
            "facet_keys": record.facet_keys,
            "why": record.why.model_dump(mode="json"),
            "where": record.where.model_dump(mode="json"),
        }
        if record.request_ref:
            metadata["request_ref"] = record.request_ref
        if record.what:
            metadata["what"] = [a.model_dump(mode="json") for a in record.what]
        if record.evidence:
            metadata["evidence"] = record.evidence
        if record.links:
            metadata["links"] = [lnk.model_dump(mode="json") for lnk in record.links]
        if record.touched_uris:
            metadata["touched_uris"] = record.touched_uris
        if record.produced_uris:
            metadata["produced_uris"] = record.produced_uris
        if record.dedupe_key:
            metadata["dedupe_key"] = record.dedupe_key
        if record.save_signals:
            metadata["save_signals"] = record.save_signals.model_dump(mode="json")
        return metadata

    def _parse_request(self, file_path: Path) -> RequestRecord | None:
        """Parse a frontmatter file into a RequestRecord."""
        try:
            post = frontmatter.load(file_path)
            meta = post.metadata

            why = [WhyHypothesis(**h) for h in meta.get("why", [])]
            how = [HowStep(**s) for s in meta.get("how", [])]
            discoveries = [Discovery(**d) for d in meta.get("discoveries", [])]
            links = [
                ShallowLink(
                    target_id=lnk["target_id"],
                    relation=LinkRelation(lnk.get("relation", "related")),
                    weight=lnk.get("weight", 0.5),
                )
                for lnk in meta.get("links", [])
            ]
            causality = [
                CausalLink(
                    target_id=cl["target_id"],
                    relation=CausalRelation(cl["relation"]),
                    reason=cl.get("reason", ""),
                )
                for cl in meta.get("causality", [])
            ]
            save_signals = None
            if "save_signals" in meta:
                save_signals = SaveSignals(**meta["save_signals"])

            return RequestRecord(
                id=meta["id"],
                schema_version=meta.get("schema_version", 1),
                who=meta.get("who", ""),
                when=meta.get("when", datetime.now()),
                where=meta.get("where", ""),
                what=meta.get(
                    "what",
                    post.content.split("\n## What\n")[-1].split("\n##")[0].strip()
                    if "\n## What\n" in post.content
                    else "",
                ),
                topics=meta.get("topics", []),
                why=why,
                how=how,
                discoveries=discoveries,
                facet_keys=meta.get("facet_keys", []),
                links=links,
                causality=causality,
                touched_uris=meta.get("touched_uris", []),
                produced_uris=meta.get("produced_uris", []),
                dedupe_key=meta.get("dedupe_key", ""),
                save_signals=save_signals,
                created_at=meta.get("created_at", datetime.now()),
                updated_at=meta.get("updated_at", datetime.now()),
            )
        except Exception:
            return None

    def _parse_work(self, file_path: Path) -> WorkRecord | None:
        """Parse a frontmatter file into a WorkRecord."""
        try:
            post = frontmatter.load(file_path)
            meta = post.metadata

            why_data = meta.get("why", {})
            causality_data = why_data.get("causality", [])
            why = WorkWhy(
                kind=WorkWhyKind(why_data.get("kind", "advance_step")),
                step_ref=why_data.get("step_ref"),
                immediate_goal=why_data.get("immediate_goal", ""),
                causality=[
                    CausalLink(
                        target_id=cl["target_id"],
                        relation=CausalRelation(cl["relation"]),
                        reason=cl.get("reason", ""),
                    )
                    for cl in causality_data
                ],
            )

            where_data = meta.get("where", {})
            where = WorkWhere(
                inputs=where_data.get("inputs", []),
                outputs=where_data.get("outputs", []),
            )

            what = [WorkAction(**a) for a in meta.get("what", [])]
            links = [
                ShallowLink(
                    target_id=lnk["target_id"],
                    relation=LinkRelation(lnk.get("relation", "related")),
                    weight=lnk.get("weight", 0.5),
                )
                for lnk in meta.get("links", [])
            ]
            save_signals = None
            if "save_signals" in meta:
                save_signals = SaveSignals(**meta["save_signals"])

            return WorkRecord(
                id=meta["id"],
                schema_version=meta.get("schema_version", 1),
                who=meta.get("who", ""),
                when=meta.get("when", datetime.now()),
                why=why,
                request_ref=meta.get("request_ref"),
                where=where,
                what=what,
                topics=meta.get("topics", []),
                evidence=meta.get("evidence", []),
                facet_keys=meta.get("facet_keys", []),
                links=links,
                touched_uris=meta.get("touched_uris", []),
                produced_uris=meta.get("produced_uris", []),
                dedupe_key=meta.get("dedupe_key", ""),
                save_signals=save_signals,
                created_at=meta.get("created_at", datetime.now()),
                updated_at=meta.get("updated_at", datetime.now()),
            )
        except Exception:
            return None

    def rebuild_qmd_indexes(self) -> None:
        """Rebuild all QMD indexes from current records."""
        from ultrawork.memory.qmd_index import QmdIndexManager

        qmd = QmdIndexManager(self.data_dir / "memory" / "indexes")
        qmd.update_all(self)

    def _matches_filters(self, record: Any, filters: dict[str, Any]) -> bool:
        """Check if a record matches the given filters."""
        for key, value in filters.items():
            if not value:
                continue
            record_value = getattr(record, key, None)
            if record_value != value:
                return False
        return True
