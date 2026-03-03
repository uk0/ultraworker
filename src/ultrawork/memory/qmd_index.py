"""QMD Index Manager for the Graphless Graph architecture.

Maintains human-readable QMD (YAML frontmatter + Markdown) index files:
- who.md: Person -> records mapping
- what.md: Topic/entity -> records mapping
- where.md: Location (channel/file) -> records mapping
- links.md: Intent-to-work connections and causal chains
- timeline.md: Chronological record listing

These files serve dual purposes:
1. YAML frontmatter: Machine-searchable structured data (Grep)
2. Markdown body: Agent-readable contextual notes (Read)
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

import yaml

from ultrawork.memory.facet_index import _atomic_write
from ultrawork.memory.record_store import RecordStore
from ultrawork.models.ltm import CausalRelation, RequestRecord, WorkRecord, _BaseSemanticRecord


def _datetime_representer(dumper: yaml.Dumper, data: datetime) -> yaml.ScalarNode:
    return dumper.represent_scalar("tag:yaml.org,2002:timestamp", data.isoformat())


yaml.add_representer(datetime, _datetime_representer)


class QmdIndexManager:
    """Manages QMD index files for agent-readable memory navigation."""

    def __init__(self, index_dir: Path | str) -> None:
        """Initialize the QMD index manager.

        Args:
            index_dir: Directory for QMD index files (e.g. data/memory/indexes/)
        """
        self.index_dir = Path(index_dir)
        self.index_dir.mkdir(parents=True, exist_ok=True)

    def update_all(self, record_store: RecordStore) -> None:
        """Rebuild all QMD index files from the record store.

        Args:
            record_store: The RecordStore to read records from
        """
        requests = record_store.list_requests()
        works = record_store.list_works()

        semantics: list[_BaseSemanticRecord] = []
        for sem_type in ("knowledge", "decision", "insight", "event"):
            semantics.extend(record_store.list_semantic(sem_type))

        self._update_who_index(requests, works, semantics)
        self._update_what_index(requests, works, semantics)
        self._update_where_index(requests, works, semantics)
        self._update_links_index(requests, works, semantics)
        self._update_timeline_index(requests, works, semantics)

    def update_for_record(
        self,
        record: RequestRecord | WorkRecord | _BaseSemanticRecord,
        record_store: RecordStore,
    ) -> None:
        """Incrementally update indexes for a single record.

        For efficiency, rebuilds only the affected indexes.

        Args:
            record: The newly saved record
            record_store: The RecordStore for loading related records
        """
        # For simplicity and correctness, do a full rebuild
        # At <500 records this is fast enough (< 100ms)
        self.update_all(record_store)

    def _update_who_index(
        self,
        requests: list[RequestRecord],
        works: list[WorkRecord],
        semantics: list[_BaseSemanticRecord],
    ) -> None:
        """Update the who.md index."""
        sem_keys = {"knowledge": "knowledge", "decision": "decisions",
                      "insight": "insights", "event": "events"}
        all_cats = ["requests", "works"] + list(sem_keys.values())
        users: dict[str, dict[str, Any]] = {}

        def _ensure(who: str) -> dict[str, Any]:
            if who not in users:
                users[who] = {c: [] for c in all_cats}
            return users[who]

        for req in requests:
            if req.who:
                _ensure(req.who)["requests"].append(req.id)

        for wrk in works:
            if wrk.who:
                _ensure(wrk.who)["works"].append(wrk.id)

        for sem in semantics:
            if sem.who:
                cat = sem_keys.get(getattr(sem, "type", ""), "knowledge")
                _ensure(sem.who)[cat].append(sem.id)

        frontmatter_data = {
            "updated_at": datetime.now(),
            "users": users,
        }

        body_parts = ["# Who Index\n"]
        for user_id, data in sorted(users.items()):
            body_parts.append(f"## {user_id}\n")
            for cat in all_cats:
                if data.get(cat):
                    body_parts.append(f"**{cat.title()}:**")
                    for rid in data[cat]:
                        body_parts.append(f"- {rid}")
            body_parts.append("")

        self._write_qmd(self.index_dir / "who.md", frontmatter_data, "\n".join(body_parts))

    def _update_what_index(
        self,
        requests: list[RequestRecord],
        works: list[WorkRecord],
        semantics: list[_BaseSemanticRecord],
    ) -> None:
        """Update the what.md index."""
        sem_keys = {"knowledge": "knowledge", "decision": "decisions",
                      "insight": "insights", "event": "events"}
        all_cats = ["requests", "works"] + list(sem_keys.values())
        topics: dict[str, dict[str, list[str]]] = {}

        def _ensure(topic: str) -> dict[str, list[str]]:
            if topic not in topics:
                topics[topic] = {c: [] for c in all_cats}
            return topics[topic]

        for req in requests:
            for topic in req.topics:
                _ensure(topic)["requests"].append(req.id)

        for wrk in works:
            for topic in wrk.topics:
                _ensure(topic)["works"].append(wrk.id)

        for sem in semantics:
            cat = sem_keys.get(getattr(sem, "type", ""), "knowledge")
            for topic in sem.topics:
                _ensure(topic)[cat].append(sem.id)

        frontmatter_data = {
            "updated_at": datetime.now(),
            "topics": topics,
        }

        body_parts = ["# What Index\n"]
        for topic, data in sorted(topics.items()):
            body_parts.append(f"## {topic}\n")
            all_ids = sum((data.get(c, []) for c in all_cats), [])
            body_parts.append(f"Total records: {len(all_ids)}")
            for cat in all_cats:
                if data.get(cat):
                    body_parts.append(f"{cat.title()}: {', '.join(data[cat])}")
            body_parts.append("")

        self._write_qmd(self.index_dir / "what.md", frontmatter_data, "\n".join(body_parts))

    def _update_where_index(
        self,
        requests: list[RequestRecord],
        works: list[WorkRecord],
        semantics: list[_BaseSemanticRecord],
    ) -> None:
        """Update the where.md index."""
        sem_keys = {"knowledge": "knowledge", "decision": "decisions",
                      "insight": "insights", "event": "events"}
        all_cats = ["requests"] + list(sem_keys.values())
        channels: dict[str, dict[str, list[str]]] = {}
        files: dict[str, list[str]] = {}

        def _ensure_ch(ch: str) -> dict[str, list[str]]:
            if ch not in channels:
                channels[ch] = {c: [] for c in all_cats}
            return channels[ch]

        for req in requests:
            if req.where:
                _ensure_ch(req.where)["requests"].append(req.id)

        for wrk in works:
            for inp in wrk.where.inputs:
                files.setdefault(inp, []).append(wrk.id)
            for out in wrk.where.outputs:
                files.setdefault(out, []).append(wrk.id)

        for sem in semantics:
            if sem.where:
                cat = sem_keys.get(getattr(sem, "type", ""), "knowledge")
                _ensure_ch(sem.where)[cat].append(sem.id)

        frontmatter_data = {
            "updated_at": datetime.now(),
            "channels": channels,
            "files": files,
        }

        body_parts = ["# Where Index\n"]
        if channels:
            body_parts.append("## Channels\n")
            for ch, data in sorted(channels.items()):
                all_ids = sum((data.get(c, []) for c in all_cats), [])
                body_parts.append(f"### {ch} ({len(all_ids)} records)")
                for cat in all_cats:
                    if data.get(cat):
                        body_parts.append(f"{cat.title()}: {', '.join(data[cat][:10])}")
                        if len(data[cat]) > 10:
                            body_parts.append(f"  ... and {len(data[cat]) - 10} more")
                body_parts.append("")

        if files:
            body_parts.append("## Files\n")
            for fp, record_ids in sorted(files.items()):
                body_parts.append(f"### {fp}")
                body_parts.append(f"Works: {', '.join(record_ids)}")
                body_parts.append("")

        self._write_qmd(self.index_dir / "where.md", frontmatter_data, "\n".join(body_parts))

    def _update_links_index(
        self,
        requests: list[RequestRecord],
        works: list[WorkRecord],
        semantics: list[_BaseSemanticRecord],
    ) -> None:
        """Update the links.md index."""
        intent_to_works: dict[str, list[str]] = {}
        request_to_works: dict[str, list[str]] = {}
        shallow_links: dict[str, list[str]] = {}
        causal_caused_by: dict[str, list[str]] = {}
        causal_leads_to: dict[str, list[str]] = {}
        causal_blocks: dict[str, list[str]] = {}

        # Build intent-to-work and request-to-work mappings
        for wrk in works:
            if wrk.request_ref:
                request_to_works.setdefault(wrk.request_ref, []).append(wrk.id)

            if wrk.why.step_ref:
                intent_to_works.setdefault(wrk.why.step_ref, []).append(wrk.id)

            # Causal links from WorkRecord
            for cl in wrk.why.causality:
                if cl.relation == CausalRelation.CAUSED_BY:
                    causal_caused_by.setdefault(wrk.id, []).append(cl.target_id)
                elif cl.relation == CausalRelation.LEADS_TO:
                    causal_leads_to.setdefault(wrk.id, []).append(cl.target_id)
                elif cl.relation == CausalRelation.BLOCKS:
                    causal_blocks.setdefault(wrk.id, []).append(cl.target_id)

        # Causal links from RequestRecord
        for req in requests:
            for cl in req.causality:
                if cl.relation == CausalRelation.CAUSED_BY:
                    causal_caused_by.setdefault(req.id, []).append(cl.target_id)
                elif cl.relation == CausalRelation.LEADS_TO:
                    causal_leads_to.setdefault(req.id, []).append(cl.target_id)
                elif cl.relation == CausalRelation.BLOCKS:
                    causal_blocks.setdefault(req.id, []).append(cl.target_id)

        # Shallow links from semantic records
        for sem in semantics:
            for lnk in sem.links:
                shallow_links.setdefault(sem.id, []).append(lnk.target_id)

        frontmatter_data = {
            "updated_at": datetime.now(),
            "intent_to_works": intent_to_works,
            "request_to_works": request_to_works,
            "shallow_links": shallow_links,
            "causal_chains": {
                "caused_by": causal_caused_by,
                "leads_to": causal_leads_to,
                "blocks": causal_blocks,
            },
        }

        body_parts = ["# Links Index\n"]

        if intent_to_works:
            body_parts.append("## Intent Chains\n")
            body_parts.append("| Intent | Works |")
            body_parts.append("|---|---|")
            for intent, work_ids in sorted(intent_to_works.items()):
                body_parts.append(f"| {intent} | {', '.join(work_ids)} |")
            body_parts.append("")

        if request_to_works:
            body_parts.append("## Request-Work Mappings\n")
            for req_id, work_ids in sorted(request_to_works.items()):
                body_parts.append(f"- **{req_id}**: {', '.join(work_ids)}")
            body_parts.append("")

        if shallow_links:
            body_parts.append("## Shallow Links\n")
            for src_id, targets in sorted(shallow_links.items()):
                body_parts.append(f"- **{src_id}** -> {', '.join(targets)}")
            body_parts.append("")

        if any([causal_caused_by, causal_leads_to, causal_blocks]):
            body_parts.append("## Causal Chains\n")
            if causal_caused_by:
                body_parts.append("### caused_by")
                for src, targets in sorted(causal_caused_by.items()):
                    body_parts.append(f"- {src} <- {', '.join(targets)}")
            if causal_leads_to:
                body_parts.append("### leads_to")
                for src, targets in sorted(causal_leads_to.items()):
                    body_parts.append(f"- {src} -> {', '.join(targets)}")
            if causal_blocks:
                body_parts.append("### blocks")
                for src, targets in sorted(causal_blocks.items()):
                    body_parts.append(f"- {src} blocks {', '.join(targets)}")
            body_parts.append("")

        self._write_qmd(self.index_dir / "links.md", frontmatter_data, "\n".join(body_parts))

    def _update_timeline_index(
        self,
        requests: list[RequestRecord],
        works: list[WorkRecord],
        semantics: list[_BaseSemanticRecord],
    ) -> None:
        """Update the timeline.md index."""
        type_icons = {
            "request": "REQ", "work": "WRK",
            "knowledge": "KNOW", "decision": "DEC",
            "insight": "INS", "event": "EVT",
        }
        records: list[dict[str, Any]] = []

        for req in requests:
            records.append(
                {
                    "id": req.id,
                    "type": "request",
                    "date": req.created_at.strftime("%Y-%m-%d"),
                    "title": req.what[:80] if req.what else "",
                    "topics": req.topics,
                }
            )

        for wrk in works:
            title = wrk.why.immediate_goal or (wrk.what[0].action if wrk.what else "")
            records.append(
                {
                    "id": wrk.id,
                    "type": "work",
                    "date": wrk.created_at.strftime("%Y-%m-%d"),
                    "title": title[:80],
                    "topics": wrk.topics,
                }
            )

        for sem in semantics:
            sem_type = getattr(sem, "type", "knowledge")
            title = sem.what[:80] if sem.what else sem.id
            records.append(
                {
                    "id": sem.id,
                    "type": sem_type,
                    "date": sem.created_at.strftime("%Y-%m-%d"),
                    "title": title,
                    "topics": sem.topics,
                }
            )

        records.sort(key=lambda r: r["date"])

        frontmatter_data = {
            "updated_at": datetime.now(),
            "total_records": len(records),
            "records": records,
        }

        body_parts = ["# Timeline\n"]
        body_parts.append(f"Total: {len(records)} records\n")
        current_date = ""
        for rec in records:
            if rec["date"] != current_date:
                current_date = rec["date"]
                body_parts.append(f"\n### {current_date}")
            icon = type_icons.get(rec["type"], rec["type"].upper())
            body_parts.append(f"- **[{icon}] {rec['id']}**: {rec['title']}")

        self._write_qmd(self.index_dir / "timeline.md", frontmatter_data, "\n".join(body_parts))

    @staticmethod
    def _write_qmd(path: Path, frontmatter_data: dict[str, Any], body: str) -> None:
        """Write a QMD file with YAML frontmatter and markdown body."""
        fm = yaml.safe_dump(
            frontmatter_data, allow_unicode=True, sort_keys=True, default_flow_style=False
        )
        content = f"---\n{fm}---\n\n{body}\n"
        _atomic_write(path, content)
