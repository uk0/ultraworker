---
description: Rebuild the Long-Term Memory indexes from all stored records. Use when indexes are corrupted or out of sync with record files.
---

# /memory-rebuild - Rebuild LTM Indexes

Rebuild all LTM indexes from scratch by scanning all record files. Use this when the facet index or QMD indexes are corrupted or out of sync.

## Usage

```
/memory-rebuild
/memory-rebuild --index facet     # Rebuild only facet_index.yaml
/memory-rebuild --index qmd       # Rebuild only QMD indexes
/memory-rebuild --index all       # Rebuild everything (default)
```

## Arguments

| Argument | Description | Default |
|----------|-------------|---------|
| `--index` | Which indexes to rebuild | `all` |

## Execution Flow

```
1. Scan all record files:
   - data/memory/requests/req-*.md
   - data/memory/works/work-*.md
   - data/memory/knowledge/know-*.md
   - data/memory/decisions/dec-*.md
   - data/memory/insights/ins-*.md
   - data/memory/events/evt-*.md
2. Parse each record's frontmatter
3. Rebuild facet index:
   - Clear facet_index.yaml
   - Re-extract facet keys from each record
   - Rebuild forward + inverted index
4. Rebuild QMD indexes:
   - who.md: Re-map users to records
   - what.md: Re-map topics to records
   - where.md: Re-map locations to records
   - links.md: Re-map intent chains + causal links
   - timeline.md: Re-sort chronologically
5. Verify integrity
6. Report results
```

## Implementation

```python
from pathlib import Path
from ultrawork.memory import RecordStore, FacetIndex, QmdIndexManager

store = RecordStore("data/")

# Rebuild facet index
store.facet_index.rebuild(store)
print("Facet index rebuilt")

# Rebuild QMD indexes
qmd = QmdIndexManager(Path("data/memory/indexes"))
qmd.update_all(store)
print("QMD indexes rebuilt")
```

## Output Format

```
LTM Index Rebuild Complete
- Records scanned: 1152 (4 requests, 4 works, 1144 knowledge)
- Facet index: rebuilt (facet_index.yaml)
  - 496 facet keys indexed
  - 1152 records in forward index
- QMD indexes: rebuilt
  - who.md: 8 users
  - what.md: 221 topics
  - where.md: 31 files, 100+ channels
  - links.md: 12 intent chains, 8 causal links
  - timeline.md: 1152 entries
```

## When to Use

- After manual record file edits
- When facet index appears inconsistent (search returns wrong results)
- After recovering from a failed save operation
- Periodically as maintenance (e.g., weekly)
