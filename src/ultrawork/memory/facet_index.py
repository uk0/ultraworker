"""File-based inverted index for Facet Keys.

Storage: data/memory/index/facet_index.yaml
Structure: {facet_key: [record_id, ...]}

Maintains both inverted (facet_key -> record_ids) and forward (record_id -> facet_keys)
indexes for O(1) operations. Uses thread lock and atomic writes for safety.
"""

from __future__ import annotations

import threading
from collections import Counter
from pathlib import Path
from typing import TYPE_CHECKING

import yaml

if TYPE_CHECKING:
    from ultrawork.memory.record_store import RecordStore

# Facet-type weights for weighted search
FACET_WEIGHTS: dict[str, int] = {
    "step": 5,
    "req": 4,
    "what": 3,
    "why": 3,
    "how": 3,
    "where": 2,
    "who": 1,
}


def _atomic_write(path: Path, data: str) -> None:
    """Write data atomically using write-to-tmp + rename pattern."""
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    tmp_path.write_text(data, encoding="utf-8")
    tmp_path.replace(path)  # atomic rename on POSIX


class FacetIndex:
    """Inverted index mapping facet keys to record IDs.

    Persisted as YAML for simplicity and debuggability.
    Thread-safe with lock protection and atomic writes.
    """

    def __init__(self, index_path: Path | str) -> None:
        """Initialize the facet index.

        Args:
            index_path: Path to the YAML index file
        """
        self.index_path = Path(index_path)
        self.index_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._index: dict[str, list[str]] = {}
        self._reverse: dict[str, set[str]] = {}  # record_id -> set of facet_keys
        self.load()

    def load(self) -> None:
        """Load index from disk."""
        with self._lock:
            if self.index_path.exists():
                with open(self.index_path) as f:
                    data = yaml.safe_load(f) or {}
                self._index = {k: list(v) for k, v in data.items() if isinstance(v, list)}
            else:
                self._index = {}
            self._rebuild_reverse()

    def save(self) -> None:
        """Save index to disk atomically."""
        with self._lock:
            content = yaml.safe_dump(self._index, allow_unicode=True, sort_keys=True)
            _atomic_write(self.index_path, content)

    def _rebuild_reverse(self) -> None:
        """Rebuild the reverse index (record_id -> facet_keys)."""
        self._reverse = {}
        for key, record_ids in self._index.items():
            for rid in record_ids:
                if rid not in self._reverse:
                    self._reverse[rid] = set()
                self._reverse[rid].add(key)

    def add(self, record_id: str, facet_keys: list[str]) -> None:
        """Add a record's facet keys to the index.

        Args:
            record_id: The record ID to index
            facet_keys: List of facet key strings
        """
        with self._lock:
            for key in facet_keys:
                if key not in self._index:
                    self._index[key] = []
                if record_id not in self._index[key]:
                    self._index[key].append(record_id)

            if record_id not in self._reverse:
                self._reverse[record_id] = set()
            self._reverse[record_id].update(facet_keys)

        self.save()

    def remove(self, record_id: str) -> None:
        """Remove a record from the index.

        Args:
            record_id: The record ID to remove
        """
        with self._lock:
            facet_keys = self._reverse.pop(record_id, set())
            for key in facet_keys:
                if key in self._index and record_id in self._index[key]:
                    self._index[key].remove(record_id)
                    if not self._index[key]:
                        del self._index[key]

        self.save()

    def search(
        self,
        facet_keys: list[str],
        operator: str = "AND",
    ) -> list[str]:
        """Search for record IDs matching facet keys.

        Args:
            facet_keys: Facet keys to search for
            operator: "AND" (all keys must match) or "OR" (any key matches)

        Returns:
            List of matching record IDs
        """
        if not facet_keys:
            return []

        sets = []
        for key in facet_keys:
            record_ids = self._index.get(key, [])
            sets.append(set(record_ids))

        if operator == "AND":
            if not sets:
                return []
            result = sets[0]
            for s in sets[1:]:
                result &= s
            return sorted(result)
        else:  # OR
            result: set[str] = set()
            for s in sets:
                result |= s
            return sorted(result)

    def weighted_search(self, facet_keys: list[str], top_k: int = 20) -> list[tuple[str, float]]:
        """Search with facet-type weighted scoring.

        Args:
            facet_keys: Facet keys to search for
            top_k: Maximum results to return

        Returns:
            List of (record_id, score) tuples sorted by score descending
        """
        if not facet_keys:
            return []

        scores: Counter[str] = Counter()
        for key in facet_keys:
            facet_type = key.split("/")[1] if "/" in key else "what"
            weight = FACET_WEIGHTS.get(facet_type, 1)
            for rid in self._index.get(key, []):
                scores[rid] += weight

        return scores.most_common(top_k)

    def get_related(self, record_id: str, top_k: int = 5) -> list[str]:
        """Find records related by facet overlap.

        Args:
            record_id: The source record ID
            top_k: Maximum number of related records to return

        Returns:
            List of related record IDs sorted by overlap count (descending)
        """
        my_keys = self._reverse.get(record_id, set())
        if not my_keys:
            return []

        counter: Counter[str] = Counter()
        for key in my_keys:
            for rid in self._index.get(key, []):
                if rid != record_id:
                    counter[rid] += 1

        return [rid for rid, _count in counter.most_common(top_k)]

    def get_facets_for_record(self, record_id: str) -> list[str]:
        """Get all facet keys associated with a record.

        Args:
            record_id: The record ID

        Returns:
            List of facet key strings
        """
        return sorted(self._reverse.get(record_id, set()))

    def get_all_record_ids(self) -> list[str]:
        """Get all indexed record IDs.

        Returns:
            Sorted list of all record IDs in the index
        """
        return sorted(self._reverse.keys())

    def rebuild(self, record_store: RecordStore) -> None:
        """Rebuild the entire index from the record store.

        Use this to recover from index corruption.

        Args:
            record_store: The RecordStore to rebuild from
        """
        from ultrawork.memory.facet import extract_facets_from_record

        with self._lock:
            self._index = {}
            self._reverse = {}

            for record in record_store.list_requests():
                facets = extract_facets_from_record(record)
                merged = list(dict.fromkeys(record.facet_keys + facets))
                for key in merged:
                    if key not in self._index:
                        self._index[key] = []
                    if record.id not in self._index[key]:
                        self._index[key].append(record.id)
                self._reverse[record.id] = set(merged)

            for record in record_store.list_works():
                facets = extract_facets_from_record(record)
                merged = list(dict.fromkeys(record.facet_keys + facets))
                for key in merged:
                    if key not in self._index:
                        self._index[key] = []
                    if record.id not in self._index[key]:
                        self._index[key].append(record.id)
                self._reverse[record.id] = set(merged)

        self.save()
