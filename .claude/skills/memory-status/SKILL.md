---
description: Display the current status of the Long-Term Memory system including record counts, index health, facet coverage, and causal chain statistics.
---

# /memory-status - LTM System Status

Display a summary of the current Long-Term Memory system state.

## Usage

```
/memory-status
```

## Execution Flow

```
1. Count request records: Glob data/memory/requests/req-*.md
2. Count work records: Glob data/memory/works/work-*.md
3. Load facet index: data/memory/index/facet_index.yaml
4. Check QMD index freshness: data/memory/indexes/*.md
5. Calculate facet coverage per dimension (who, what, where, why, how)
6. Count causal chains from links.md
7. Display summary
```

## Implementation

```python
from pathlib import Path
from ultrawork.memory import RecordStore, FacetIndex

store = RecordStore("data/")
requests = store.list_requests()
works = store.list_works()

# Facet coverage
facet_index = store.facet_index
all_facets = {}
for rid in facet_index.get_all_record_ids():
    for fk in facet_index.get_facets_for_record(rid):
        facet_type = fk.split("/")[1]
        all_facets.setdefault(facet_type, 0)
        all_facets[facet_type] += 1

# Causal chain count
causal_count = sum(
    len(r.causality) for r in requests
) + sum(
    len(w.why.causality) for w in works
)
```

## Output Format

```
LTM Status
- Requests: 15 records
- Works: 42 records
- Index health: OK (facet_index.yaml synced)
- Facet coverage:
    who:   90% (52/57 records)
    what:  100% (57/57 records)
    where: 85% (48/57 records)
    why:   70% (40/57 records)
    how:   65% (37/57 records)
- Causal chains: 8 links
- QMD indexes: 5 files, last updated 2026-02-25
```
