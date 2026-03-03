"""Long-Term Memory subsystem.

Provides the Graphless Graph architecture for agent memory:
- FacetKey-based implicit edges
- ShallowLink explicit edges
- CausalLink causal chain tracking
- 4-Signal Gate + NDREI save policy
- File-based inverted index with weighted search
- QMD indexes for agent-readable navigation
"""

from ultrawork.memory.facet import (
    create_facet_key,
    extract_facets_from_record,
    normalize_facet_value,
    parse_facet_key,
)
from ultrawork.memory.facet_index import FacetIndex
from ultrawork.memory.linker import RecordLinker
from ultrawork.memory.qmd_index import QmdIndexManager
from ultrawork.memory.record_store import RecordStore
from ultrawork.memory.redact import generate_dedupe_key, redact_secrets
from ultrawork.memory.save_policy import SaveContext, SaveDecision, SavePolicyEngine
from ultrawork.memory.search import MemorySearchEngine, SearchResult

__all__ = [
    # Facet utilities
    "create_facet_key",
    "extract_facets_from_record",
    "normalize_facet_value",
    "parse_facet_key",
    # Index
    "FacetIndex",
    # Storage
    "RecordStore",
    # Save policy
    "SaveContext",
    "SaveDecision",
    "SavePolicyEngine",
    # Linking
    "RecordLinker",
    # QMD Index
    "QmdIndexManager",
    # Search
    "MemorySearchEngine",
    "SearchResult",
    # Security
    "generate_dedupe_key",
    "redact_secrets",
]
