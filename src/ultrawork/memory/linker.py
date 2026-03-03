"""Record linking system for the Graphless Graph architecture.

Manages explicit ShallowLink connections between records,
validates step references, deduplicates, decomposes steps,
and tracks causal chains (caused_by, leads_to, blocks, supersedes).
"""

from __future__ import annotations

from ultrawork.memory.facet_index import FacetIndex
from ultrawork.memory.record_store import RecordStore
from ultrawork.memory.redact import generate_dedupe_key
from ultrawork.models.ltm import (
    CausalLink,
    CausalRelation,
    HowStep,
    LinkRelation,
    RequestRecord,
    ShallowLink,
    WorkRecord,
)


class RecordLinker:
    """Manages record-to-record links and structural integrity."""

    def __init__(self, record_store: RecordStore, facet_index: FacetIndex) -> None:
        self.record_store = record_store
        self.facet_index = facet_index

    def link_work_to_step(
        self,
        work: WorkRecord,
        request_id: str,
        step_id: str,
    ) -> None:
        """Set a WorkRecord's step_ref to point at a RequestRecord step.

        Also sets request_ref for direct tracking.

        Args:
            work: The WorkRecord to link
            request_id: Target RequestRecord ID
            step_id: Target HowStep ID within the request
        """
        work.why.step_ref = f"{request_id}#{step_id}"
        work.request_ref = request_id

    def validate_step_ref(self, work: WorkRecord) -> bool:
        """Validate that a WorkRecord's step_ref maps to an actual HowStep.

        Args:
            work: The WorkRecord to validate

        Returns:
            True if step_ref is valid, False otherwise
        """
        if not work.why.step_ref:
            return False

        parts = work.why.step_ref.split("#", 1)
        if len(parts) != 2:
            return False

        request_id, step_id = parts
        request = self.record_store.load_request(request_id)
        if not request:
            return False

        return any(step.step_id == step_id for step in request.how)

    def find_similar_records(self, record_id: str, top_k: int = 5) -> list[str]:
        """Find records similar to the given one via facet overlap.

        Args:
            record_id: Source record ID
            top_k: Maximum similar records to return

        Returns:
            List of similar record IDs
        """
        return self.facet_index.get_related(record_id, top_k=top_k)

    def update_shallow_links(self, record_id: str, max_links: int = 7) -> None:
        """Update a record's links[] with similar records.

        Merges new links with existing ones, respecting max_links limit.

        Args:
            record_id: The record to update links for
            max_links: Maximum total links to maintain
        """
        record = self.record_store.load_request(record_id)
        is_request = record is not None
        if not record:
            record = self.record_store.load_work(record_id)
        if not record:
            return

        existing_targets = {link.target_id for link in record.links}
        similar = self.facet_index.get_related(record_id, top_k=max_links * 2)

        new_links = list(record.links)
        for rid in similar:
            if rid in existing_targets:
                continue
            if len(new_links) >= max_links:
                break
            new_links.append(
                ShallowLink(
                    target_id=rid,
                    relation=LinkRelation.RELATED,
                    weight=0.5,
                )
            )
            existing_targets.add(rid)

        record.links = new_links

        if is_request:
            self.record_store.save_request(record)  # type: ignore[arg-type]
        else:
            self.record_store.save_work(record)  # type: ignore[arg-type]

    def check_duplicate(self, record: RequestRecord | WorkRecord) -> str | None:
        """Check if a semantically equivalent record already exists.

        Args:
            record: The record to check for duplicates

        Returns:
            Existing record ID if duplicate found, None otherwise
        """
        if isinstance(record, RequestRecord):
            content = record.what
            step_ref = ""
            uris: list[str] = []
        else:
            content = " ".join(a.action for a in record.what)
            step_ref = record.why.step_ref or ""
            uris = record.where.inputs + record.where.outputs

        new_key = generate_dedupe_key(content, step_ref, uris)

        if isinstance(record, RequestRecord):
            existing = self.record_store.list_requests()
            for existing_record in existing:
                if existing_record.id == record.id:
                    continue
                existing_key = generate_dedupe_key(existing_record.what, "", [])
                if existing_key == new_key:
                    return existing_record.id
        else:
            existing_works = self.record_store.list_works()
            for existing_record in existing_works:
                if existing_record.id == record.id:
                    continue
                existing_key = generate_dedupe_key(
                    " ".join(a.action for a in existing_record.what),
                    existing_record.why.step_ref or "",
                    existing_record.where.inputs + existing_record.where.outputs,
                )
                if existing_key == new_key:
                    return existing_record.id

        return None

    def decompose_step_if_needed(
        self,
        request: RequestRecord,
        step_id: str,
    ) -> list[HowStep]:
        """Decompose a step if it violates atomicity (2+ expected artifacts).

        Args:
            request: The parent RequestRecord
            step_id: The step to potentially decompose

        Returns:
            List of resulting steps (original if no decomposition needed)
        """
        step = next((s for s in request.how if s.step_id == step_id), None)
        if not step:
            return []

        if len(step.expected_artifacts) <= 1:
            return [step]

        new_steps: list[HowStep] = []
        for i, artifact in enumerate(step.expected_artifacts, 1):
            new_steps.append(
                HowStep(
                    step_id=f"{step_id}-{i:02d}",
                    goal=f"{step.goal} -> {artifact}",
                    done=step.done,
                    expected_artifacts=[artifact],
                    related_queries=step.related_queries,
                )
            )

        idx = next(i for i, s in enumerate(request.how) if s.step_id == step_id)
        request.how = request.how[:idx] + new_steps + request.how[idx + 1 :]

        return new_steps

    # --- Causal Chain Management ---

    def add_causal_link(
        self,
        source_id: str,
        target_id: str,
        relation: CausalRelation,
        reason: str = "",
    ) -> bool:
        """Add a causal link between two records.

        For RequestRecords, adds to record.causality.
        For WorkRecords, adds to record.why.causality.

        Args:
            source_id: The source record ID
            target_id: The target record ID
            relation: The causal relationship type
            reason: Human-readable reason for the link

        Returns:
            True if link was added successfully
        """
        record = self.record_store.load_request(source_id)
        is_request = record is not None
        if not record:
            record = self.record_store.load_work(source_id)
        if not record:
            return False

        link = CausalLink(target_id=target_id, relation=relation, reason=reason)

        if is_request:
            req = record  # type: ignore[assignment]
            if not any(
                cl.target_id == target_id and cl.relation == relation for cl in req.causality
            ):
                req.causality.append(link)
                self.record_store.save_request(req)  # type: ignore[arg-type]
        else:
            wrk = record  # type: ignore[assignment]
            if not any(
                cl.target_id == target_id and cl.relation == relation for cl in wrk.why.causality
            ):
                wrk.why.causality.append(link)
                self.record_store.save_work(wrk)  # type: ignore[arg-type]

        return True

    def trace_cause(self, record_id: str, max_depth: int = 10) -> list[str]:
        """Recursively trace caused_by links back to the root cause.

        Args:
            record_id: Starting record ID
            max_depth: Maximum traversal depth

        Returns:
            List of record IDs forming the causal chain (root first)
        """
        chain: list[str] = []
        visited: set[str] = {record_id}

        current_id = record_id
        for _ in range(max_depth):
            causes = self._get_causal_targets(current_id, CausalRelation.CAUSED_BY)
            if not causes:
                break
            cause_id = causes[0]
            if cause_id in visited:
                break
            visited.add(cause_id)
            chain.append(cause_id)
            current_id = cause_id

        chain.reverse()
        return chain

    def trace_effect(self, record_id: str, max_depth: int = 10) -> list[str]:
        """Recursively trace leads_to links forward to discover blast radius.

        Args:
            record_id: Starting record ID
            max_depth: Maximum traversal depth

        Returns:
            List of affected record IDs (breadth-first order)
        """
        effects: list[str] = []
        visited: set[str] = {record_id}
        queue: list[str] = [record_id]

        for _ in range(max_depth):
            if not queue:
                break
            current_id = queue.pop(0)
            targets = self._get_causal_targets(current_id, CausalRelation.LEADS_TO)
            targets += self._get_causal_targets(current_id, CausalRelation.BLOCKS)
            for tid in targets:
                if tid not in visited:
                    visited.add(tid)
                    effects.append(tid)
                    queue.append(tid)

        return effects

    def get_blocking_chain(self, record_id: str) -> list[str]:
        """Get all records that block this record (direct + transitive).

        Args:
            record_id: The record to check

        Returns:
            List of blocking record IDs
        """
        blockers: list[str] = []
        visited: set[str] = {record_id}
        queue: list[str] = [record_id]

        while queue:
            current_id = queue.pop(0)
            blocking = self._get_causal_targets(current_id, CausalRelation.CAUSED_BY)
            for bid in blocking:
                if bid not in visited:
                    visited.add(bid)
                    blockers.append(bid)
                    queue.append(bid)

        return blockers

    def _get_causal_targets(self, record_id: str, relation: CausalRelation) -> list[str]:
        """Get target IDs for a specific causal relation type.

        Args:
            record_id: Source record ID
            relation: Causal relation to filter by

        Returns:
            List of target record IDs
        """
        record = self.record_store.load_request(record_id)
        if record:
            return [cl.target_id for cl in record.causality if cl.relation == relation]

        work = self.record_store.load_work(record_id)
        if work:
            return [cl.target_id for cl in work.why.causality if cl.relation == relation]

        return []
