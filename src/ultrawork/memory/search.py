"""Memory search engine for the Graphless Graph architecture.

Supports Facet Key matching with weighted reranking, full-text keyword search,
1-hop expansion, and causal chain traversal.
Uses the 3-query minimum "Query Pack" pattern.
"""

from __future__ import annotations

import re
from collections import Counter
from datetime import datetime

from pydantic import BaseModel, Field

from ultrawork.memory.facet import create_facet_key
from ultrawork.memory.facet_index import FACET_WEIGHTS, FacetIndex
from ultrawork.memory.record_store import RecordStore

# Recency decay constant (days)
_RECENCY_HALF_LIFE = 30.0


class SearchResult(BaseModel):
    """A single search result."""

    record_id: str
    record_type: str  # "request" | "work" | "knowledge" | "decision" | "insight" | "event"
    score: float = 0.0
    matched_facets: list[str] = Field(default_factory=list)
    snippet: str = ""


class MemorySearchEngine:
    """Search engine combining facet-key matching and keyword search.

    Uses weighted facet reranking:
    - step: 5, req: 4, what/why/how: 3, where: 2, who: 1
    - Recency boost based on record creation date
    - Link bonus for records with causal links
    """

    def __init__(self, record_store: RecordStore, facet_index: FacetIndex) -> None:
        self.record_store = record_store
        self.facet_index = facet_index

    def search(self, query: str, top_k: int = 10) -> list[SearchResult]:
        """Search LTM records using the 3-query pack pattern.

        1. Facet key query: Extract facet keys from query and match
        2. Full-text query: Keyword matching on record bodies
        3. Perspective query: Re-query focusing on where/what facets

        Args:
            query: Natural language query string
            top_k: Maximum results to return

        Returns:
            Ranked list of SearchResult
        """
        candidates: dict[str, SearchResult] = {}

        # Query 1: Facet key matching with weighted scoring
        query_facets = self._extract_query_facets(query)
        if query_facets:
            weighted_results = self.facet_index.weighted_search(query_facets, top_k=top_k * 3)
            for rid, weight_score in weighted_results:
                matched = self._get_matched_facets(rid, query_facets)
                candidates[rid] = SearchResult(
                    record_id=rid,
                    record_type=self._detect_type(rid),
                    score=weight_score * 0.1,
                    matched_facets=matched,
                )

        # Query 2: Full-text keyword matching
        keywords = self._extract_keywords(query)
        if keywords:
            text_results = self._search_full_text(keywords)
            for rid, snippet, match_count in text_results:
                if rid in candidates:
                    candidates[rid].score += match_count * 0.2
                    if not candidates[rid].snippet:
                        candidates[rid].snippet = snippet
                else:
                    candidates[rid] = SearchResult(
                        record_id=rid,
                        record_type=self._detect_type(rid),
                        score=match_count * 0.2,
                        snippet=snippet,
                    )

        # Query 3: Perspective query (where/what focused)
        perspective_facets = [f for f in query_facets if f.startswith(("k/where/", "k/what/"))]
        if perspective_facets:
            persp_results = self.facet_index.search(perspective_facets, operator="OR")
            for rid in persp_results:
                if rid in candidates:
                    candidates[rid].score += 0.1
                else:
                    candidates[rid] = SearchResult(
                        record_id=rid,
                        record_type=self._detect_type(rid),
                        score=0.1,
                    )

        # Apply recency boost and link bonus
        for result in candidates.values():
            result.score += self._recency_boost(result.record_id)
            result.score += self._link_bonus(result.record_id)

        # Rank and return
        results = sorted(candidates.values(), key=lambda r: r.score, reverse=True)
        return results[:top_k]

    def expand_one_hop(
        self,
        initial_results: list[str],
        top_k_per_key: int = 3,
    ) -> list[str]:
        """Expand results by 1-hop facet key traversal.

        Takes the top 5 facet keys from initial results, searches each,
        and returns up to top_k_per_key additional records per key.

        Args:
            initial_results: Initial record IDs to expand from
            top_k_per_key: Max additional records per facet key

        Returns:
            List of additional record IDs (deduplicated)
        """
        if not initial_results:
            return []

        key_counter: Counter[str] = Counter()
        for rid in initial_results:
            facets = self.facet_index.get_facets_for_record(rid)
            for f in facets:
                key_counter[f] += 1

        top_keys = [k for k, _ in key_counter.most_common(5)]

        expanded: list[str] = []
        seen: set[str] = set(initial_results)

        for key in top_keys:
            results = self.facet_index.search([key], operator="AND")
            count = 0
            for rid in results:
                if rid not in seen:
                    expanded.append(rid)
                    seen.add(rid)
                    count += 1
                    if count >= top_k_per_key:
                        break

        return expanded

    def chase_links(
        self,
        record_ids: list[str],
        max_chase: int = 5,
    ) -> list[str]:
        """Follow links[], step_ref, and causal links to discover connected records.

        Args:
            record_ids: Starting record IDs
            max_chase: Maximum total linked records to return

        Returns:
            List of linked record IDs
        """
        seen = set(record_ids)
        linked: list[str] = []

        for rid in record_ids:
            if len(linked) >= max_chase:
                break

            record = self.record_store.load_request(rid)
            if not record:
                record = self.record_store.load_work(rid)
            if not record:
                record = self.record_store.load_semantic(rid)
            if not record:
                continue

            # Follow explicit links
            for link in record.links:
                if link.target_id not in seen and len(linked) < max_chase:
                    linked.append(link.target_id)
                    seen.add(link.target_id)

            # Follow step_ref for work records
            if hasattr(record, "why") and hasattr(record.why, "step_ref"):
                step_ref = record.why.step_ref
                if step_ref:
                    req_id = step_ref.split("#")[0]
                    if req_id not in seen and len(linked) < max_chase:
                        linked.append(req_id)
                        seen.add(req_id)

            # Follow causal links
            causal_links = []
            if hasattr(record, "causality"):
                causal_links = record.causality  # RequestRecord
            elif hasattr(record, "why") and hasattr(record.why, "causality"):
                causal_links = record.why.causality  # WorkRecord

            for cl in causal_links:
                if cl.target_id not in seen and len(linked) < max_chase:
                    linked.append(cl.target_id)
                    seen.add(cl.target_id)

        return linked

    def rerank(
        self,
        candidates: list[SearchResult],
        query_facets: list[str],
    ) -> list[SearchResult]:
        """Re-rank results by weighted facet overlap + recency + link bonus.

        Args:
            candidates: Search results to re-rank
            query_facets: Facet keys from the original query

        Returns:
            Re-ranked list of SearchResult
        """
        query_set = set(query_facets)
        for result in candidates:
            record_facets = set(self.facet_index.get_facets_for_record(result.record_id))
            overlap_facets = record_facets & query_set

            # Weighted overlap score
            weighted_bonus = 0.0
            for fk in overlap_facets:
                facet_type = fk.split("/")[1] if "/" in fk else "what"
                weighted_bonus += FACET_WEIGHTS.get(facet_type, 1) * 0.05

            result.score += weighted_bonus
            result.score += self._recency_boost(result.record_id)
            result.score += self._link_bonus(result.record_id)
            result.matched_facets = sorted(overlap_facets)

        return sorted(candidates, key=lambda r: r.score, reverse=True)

    # --- Internal helpers ---

    def _recency_boost(self, record_id: str) -> float:
        """Calculate recency boost for a record."""
        record = self.record_store.load_request(record_id)
        if not record:
            record = self.record_store.load_work(record_id)
        if not record:
            record = self.record_store.load_semantic(record_id)
        if not record:
            return 0.0

        days_old = (datetime.now() - record.created_at).days
        return 1.0 / (1.0 + days_old / _RECENCY_HALF_LIFE)

    def _link_bonus(self, record_id: str) -> float:
        """Calculate link bonus for records with causal links."""
        record = self.record_store.load_request(record_id)
        if record and record.causality:
            return 0.5

        work = self.record_store.load_work(record_id)
        if work and work.why.causality:
            return 0.5

        sem = self.record_store.load_semantic(record_id)
        if sem and sem.links:
            return 0.5

        return 0.0

    def _extract_query_facets(self, query: str) -> list[str]:
        """Extract facet keys from a natural language query."""
        facets: list[str] = []

        for match in re.finditer(r"k/[a-z]+/[a-z0-9\-]+", query):
            facets.append(match.group())

        words = re.findall(r"[a-z0-9]+(?:-[a-z0-9]+)*", query.lower())
        for word in words:
            if len(word) >= 3:
                facets.append(create_facet_key("what", word))

        return list(dict.fromkeys(facets))

    def _extract_keywords(self, query: str) -> list[str]:
        """Extract search keywords from a query."""
        cleaned = re.sub(r"k/[a-z]+/[a-z0-9\-]+", "", query)
        words = re.findall(r"\w+", cleaned.lower())
        stop_words = {
            "the",
            "a",
            "an",
            "is",
            "was",
            "are",
            "in",
            "on",
            "at",
            "to",
            "for",
            "of",
            "and",
            "or",
        }
        return [w for w in words if w not in stop_words and len(w) >= 2]

    def _search_full_text(self, keywords: list[str]) -> list[tuple[str, str, int]]:
        """Search record files for keyword matches across all 6 directories."""
        results: list[tuple[str, str, int]] = []

        scan_targets = [
            (self.record_store.requests_dir, "req-"),
            (self.record_store.works_dir, "work-"),
            (self.record_store.knowledge_dir, "know-"),
            (self.record_store.decisions_dir, "dec-"),
            (self.record_store.insights_dir, "ins-"),
            (self.record_store.events_dir, "evt-"),
        ]

        for dir_path, prefix in scan_targets:
            if not dir_path.exists():
                continue
            for path in dir_path.glob(f"{prefix}*.md"):
                content = path.read_text(encoding="utf-8").lower()
                match_count = sum(1 for kw in keywords if kw in content)
                if match_count > 0:
                    snippet = self._extract_snippet(content, keywords[0])
                    results.append((path.stem, snippet, match_count))

        return results

    def _extract_snippet(self, content: str, keyword: str, context_chars: int = 100) -> str:
        """Extract a text snippet around a keyword match."""
        idx = content.find(keyword)
        if idx == -1:
            return content[: context_chars * 2]
        start = max(0, idx - context_chars)
        end = min(len(content), idx + len(keyword) + context_chars)
        snippet = content[start:end].strip()
        if start > 0:
            snippet = "..." + snippet
        if end < len(content):
            snippet = snippet + "..."
        return snippet

    def _get_matched_facets(self, record_id: str, query_facets: list[str]) -> list[str]:
        """Get facets that match between a record and query facets."""
        record_facets = set(self.facet_index.get_facets_for_record(record_id))
        return sorted(set(query_facets) & record_facets)

    def _detect_type(self, record_id: str) -> str:
        """Detect record type from ID prefix."""
        prefix_map = {
            "req-": "request", "work-": "work", "know-": "knowledge",
            "dec-": "decision", "ins-": "insight", "evt-": "event",
        }
        for prefix, type_name in prefix_map.items():
            if record_id.startswith(prefix):
                return type_name
        return "unknown"
