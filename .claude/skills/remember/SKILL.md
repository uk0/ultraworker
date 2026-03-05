---
description: Save a memory record (RequestRecord or WorkRecord) to long-term memory with 4-Signal Gate evaluation, secret redaction, deduplication, and index updates.
---

# /remember - Save to Long-Term Memory

Save information to the LTM system. Evaluates the 4-Signal Gate to determine if the record should be committed.

## Usage

```
/remember req --who U0123 --what "Auth refactoring" --topics authentication,middleware
/remember work --request-ref req-20260225-0001 --step-ref "req-20260225-0001#step1" --purpose "Extract JWT module"
/remember link --source req-20260225-0001 --target req-20260220-0003 --relation caused_by
/remember update --id req-20260225-0001 --intent-status step1=done
```

## Subtypes

| Subtype | Description | Typical Trigger |
|---------|-------------|-----------------|
| `req` | Save a RequestRecord (5W1H) | After `/explore-context` completion |
| `work` | Save a WorkRecord (action + artifact) | After code changes, test writing, decisions |
| `link` | Add causal link between records | When discovering record connections |
| `update` | Update existing record fields | When intent status changes |

## Execution Flow

```
1. Collect context from the current conversation
2. Evaluate 4-Signal Gate:
   - novelty: Is this new info not in memory?
   - actionability: Did this lead to a decision/action?
   - persistence: Useful beyond this session?
   - connectedness: Links to existing records?
3. Apply variable threshold:
   - RequestRecord: need 2/4 signals
   - WorkRecord: need 1/4 signals
4. If threshold met:
   a. Generate record ID (req-YYYYMMDD-NNNN or work-YYYYMMDD-req-...-NN)
   b. Apply redact_secrets() to remove sensitive tokens
   c. Check for duplicates via dedupe_key
   d. Save record file (atomic write)
   e. Update facet index
   f. Update QMD indexes (who.md, what.md, where.md, links.md, timeline.md)
   g. Set up causal links if applicable
5. Return saved record ID and summary
```

## Auto-Invocation Rules

| Situation | Invoke? | Subtype |
|-----------|---------|---------|
| `/explore-context` completed | YES | `req` |
| Code file modified | YES | `work` |
| Test written | YES | `work` |
| Architecture/direction decided | YES | `work` |
| `/write-spec` completed | YES | `work` |
| Past record connection found | YES | `link` |
| Intent status changed | YES | `update` |
| Simple file path check | NO | - |
| grep search only | NO | - |
| Already recorded info confirmed | NO | - |
| Empty search results | NO | - |

## Arguments (req subtype)

| Argument | Required | Description | Example |
|----------|----------|-------------|---------|
| `--who` | Yes | Requester identifier | `U0123456789` |
| `--what` | Yes | Concise description | `"Auth middleware refactoring"` |
| `--where` | No | Source channel/context | `eng-common` |
| `--topics` | No | Comma-separated topic list | `authentication,middleware` |
| `--why` | No | Reason/hypothesis | `"SRP violation causing bugs"` |
| `--intents` | No | Semicolon-separated steps | `"JWT split;Chain improve;Tests"` |

## Arguments (work subtype)

| Argument | Required | Description | Example |
|----------|----------|-------------|---------|
| `--request-ref` | No | Parent RequestRecord ID | `req-20260225-0001` |
| `--step-ref` | No | Intent reference | `req-20260225-0001#step1` |
| `--purpose` | Yes | Why this work was done | `"Extract JWT verifier"` |
| `--action` | No | Action type | `extract_module` |
| `--topics` | No | Comma-separated topic list | `jwt,authentication` |
| `--files-modified` | No | Modified file paths | `src/auth/middleware.py` |
| `--files-created` | No | Created file paths | `src/auth/jwt_verifier.py` |

## Arguments (link subtype)

| Argument | Required | Description | Example |
|----------|----------|-------------|---------|
| `--source` | Yes | Source record ID | `req-20260225-0001` |
| `--target` | Yes | Target record ID | `req-20260220-0003` |
| `--relation` | Yes | Relation type | `caused_by`, `leads_to`, `blocks`, `supersedes` |
| `--reason` | No | Human-readable reason | `"Performance issue revealed structural problem"` |

## Implementation

```python
from ultrawork.memory import RecordStore, SavePolicyEngine, SaveContext, RecordLinker, QmdIndexManager
from ultrawork.memory.redact import redact_secrets
from ultrawork.models.ltm import RequestRecord, WorkRecord, SaveSignals, CausalLink, CausalRelation
from pathlib import Path

# Initialize
store = RecordStore("data/")
policy = SavePolicyEngine()
linker = RecordLinker(store, store.facet_index)
qmd = QmdIndexManager(Path("data/memory/indexes"))

# For req subtype
context = SaveContext(
    record_type="request",
    content_summary=what,
    is_novel=True,  # or check against existing memory
    led_to_decision=True,
    scope="cross_session",
    related_record_count=linker.find_similar_records_count(topics),
)
decision = policy.evaluate_4signal(context)

if decision.should_commit:
    req_id = store.generate_request_id()
    record = RequestRecord(id=req_id, who=who, what=what, topics=topics, ...)

    # Check duplicate
    dup = linker.check_duplicate(record)
    if dup:
        print(f"Duplicate found: {dup}")
        return

    store.save_request(record)  # auto-redacts secrets
    qmd.update_for_record(record, store)
    print(f"Saved: {req_id}")
```

## Output Format

```
Saved RequestRecord: req-20260226-0001
  Signals: novelty=T actionability=T persistence=T connectedness=F (3/4, threshold=2)
  Topics: authentication, middleware
  Facet keys: k/who/admin, k/what/auth-middleware-refactoring, k/where/eng-common
  Indexes updated: who.md, what.md, where.md, links.md, timeline.md
```
