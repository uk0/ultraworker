---
description: Search long-term memory records by 5W1H dimensions (who, what, where, when), trace causal chains, and retrieve related records with weighted ranking.
---

# /recall - Search Long-Term Memory

Search LTM records using 5W1H dimensions, causal chain traversal, and weighted facet matching.

## Usage

```
/recall --what authentication
/recall --who U0123456789
/recall --where src/auth/middleware.py
/recall --what authentication --who U0123 --when 2026-Q1
/recall --trace-cause work-20260225-0001
/recall --trace-effect req-20260225-0001
/recall --request req-20260225-0001
```

## Arguments

| Argument | Description | Example |
|----------|-------------|---------|
| `--what <topic>` | Search by topic/entity | `authentication`, `jwt` |
| `--who <user_id>` | Search by person | `U0123456789` |
| `--where <path>` | Search by file or channel | `src/auth/middleware.py` |
| `--when <quarter>` | Filter by time period | `2026-Q1` |
| `--request <req_id>` | Get all records for a request | `req-20260225-0001` |
| `--trace-cause <id>` | Trace causal chain backwards (root cause) | `work-20260225-0001` |
| `--trace-effect <id>` | Trace causal chain forwards (blast radius) | `req-20260225-0001` |
| `--top-k <n>` | Max results (default 10) | `5` |

## Execution Flow

```
Phase 1: Index-Based Candidate Collection
  - Extract 5W1H dimensions from query
  - Search facet_index.yaml with weighted scoring:
    step:5, req:4, what/why/how:3, where:2, who:1
  - Search QMD indexes (who.md, what.md, where.md) for additional context
  - Full-text keyword search across record files

Phase 2: Scoring & Ranking
  - Weighted facet overlap score
  - Recency boost: 1.0 / (1 + days_old / 30)
  - Link bonus: +0.5 for records with causal links
  - Records matching 2+ dimensions rank higher

Phase 3: Cross-Reference Expansion (1-hop)
  - Follow links[], step_ref, and causality fields
  - Add connected records with decayed relevance (0.7x)
  - Respect per-dimension quotas

Return: Top-K results with scores, matched facets, and snippets
```

## Auto-Invocation Rules

| Situation | Invoke? | Search Dimensions |
|-----------|---------|-------------------|
| `/explore-context` starting | YES | `--what` (thread keywords), `--who` (requester) |
| `/write-spec` starting | YES | `--request` (linked REQ), `--where` (related files) |
| Code implementation starting | YES | `--where` (target files) |
| New request analysis | YES | `--who` (same requester history), `--what` (similar topics) |
| Unknown term/project found | YES | `--what` (the term) |
| User says "previously..." | YES | Context-appropriate dimensions |

## Implementation

```python
from ultrawork.memory import MemorySearchEngine, RecordStore, FacetIndex, RecordLinker
from pathlib import Path

store = RecordStore("data/")
engine = MemorySearchEngine(store, store.facet_index)
linker = RecordLinker(store, store.facet_index)

# Basic search
results = engine.search("authentication middleware", top_k=10)

# Expand results with 1-hop traversal
initial_ids = [r.record_id for r in results]
expanded = engine.expand_one_hop(initial_ids)
linked = engine.chase_links(initial_ids)

# Trace causal chain
root_causes = linker.trace_cause("work-20260225-0001")
effects = linker.trace_effect("req-20260225-0001")

# Also read QMD indexes for context
# Read data/memory/indexes/what.md for topic clustering insights
# Read data/memory/indexes/who.md for requester pattern insights
```

## Output Format

```
Found 5 records for: --what authentication

1. [REQ] req-20260225-0001 (score: 4.2)
   "Auth middleware refactoring"
   Topics: authentication, middleware, refactoring
   Matched: k/what/authentication, k/what/middleware
   Causal: caused_by req-20260220-0003

2. [WRK] work-20260225-0001 (score: 3.8)
   "JWT verifier extraction"
   Topics: jwt, authentication
   Step ref: req-20260225-0001#step1
   Files: src/auth/jwt_verifier.py (created)

3. [WRK] work-20260225-0003 (score: 3.1)
   "Middleware chain pipeline conversion"
   Topics: middleware, authentication
   Caused by: work-20260225-0001

---
Related (1-hop expansion):
- req-20260220-0003: "Auth module performance improvement"
```

## Structural Inference

Beyond index search, use directory structure for inference:

1. **Time proximity**: Same date prefix records are from the same session
2. **ID-based search**: Found REQ-20260225-*? Also check WRK-20260225-*
3. **Intent chains**: Check links.md intent_to_works for request's work records
4. **File backtracking**: Check where.md for all records touching a specific file
5. **Topic clustering**: Check what.md body for co-occurring topic patterns
