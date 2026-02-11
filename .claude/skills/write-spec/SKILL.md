---
description: Write detailed tech spec based on approved TODO and send second approval request to Slack. Analyzes codebase and creates implementation plan.
---

# /write-spec - Write Tech Spec

Write detailed technical specification based on approved TODO.

## Usage

```
/write-spec TASK-2026-0129-001
/write-spec TASK-2026-0129-001 --analyze-codebase
```

## Arguments

| Argument | Description | Example |
|----------|-------------|---------|
| Task ID | Required. Task ID | `TASK-2026-0129-001` |
| `--analyze-codebase` | Deep code analysis (more accurate but slower) | `--analyze-codebase` |

## Prerequisites

- Task must be in `todo` stage
- TODO stage must be **approved**

## Detailed Execution Steps

### Step 1: Verify Prerequisites

```
Read data/tasks/TASK-2026-0129-001.md
```

Check:
```yaml
workflow:
  current_stage: "todo"  # Must be todo stage
  stages:
    todo:
      status: "approved"  # Must be approved
```

Error if not approved:
```
Error: TODO stage has not been approved yet.
Current status: pending

Please try again after approval.
```

### Step 2: Collect Context

Read related files:
```
Read data/tasks/TASK-2026-0129-001.md
Read data/explorations/EXP-2026-0129-001.md
```

### Step 3: Analyze Codebase

Search for related files:
```
Glob: **/*.py
Grep: "api" "cache" "redis"
```

Analysis result example:
```
Related files found:
- src/api/routes.py (API endpoints)
- src/api/handlers.py (Request handlers)
- src/db/queries.py (Database queries)
- src/config.py (Configuration file)

Dependencies:
- FastAPI
- SQLAlchemy
- Pydantic

Test files:
- tests/test_api.py
- tests/conftest.py
```

### Step 4: Write Tech Spec

Create `data/specs/TASK-2026-0129-001_spec.md`

(See existing documentation for detailed spec template)

### Step 5: Update Task File

```yaml
workflow:
  current_stage: "tech_spec"
  stages:
    todo:
      status: "approved"
      approved_at: "2026-01-29T10:30:00"
      approved_by: "U06CLS6E694"
    tech_spec:
      status: "pending"
      approval_requested_at: "2026-01-29T11:00:00"
```

### Step 6: Send Slack Second Approval Request

```
ToolSearch: "slack"
```

```
mcp__slack__slack_send_message(
  channel_id: "C0123456789",
  thread_ts: "1706500000.000000",
  text: spec_approval_message
)
```

**Fallback on failure:**
```
ToolSearch: "+slack-bot"
```
```
mcp__slack-bot-mcp__slack_reply_to_thread(
  channel_id: "C0123456789",
  thread_ts: "1706500000.000000",
  text: spec_approval_message
)
```

Or:
```
mcp__slack-bot-mcp__slack_post_message(
  channel_id: "C0123456789",
  text: spec_approval_message
)
```

Message:

```
*Tech Spec Review Request*

*Task*: Implement API Response Caching
*Spec ID*: SPEC-TASK-2026-0129-001

*Key Changes*:
- Create `src/cache/` package (4 files)
- Modify `src/api/routes.py` (apply decorator)
- Modify `src/config.py` (Redis settings)

*Test Plan*:
- 8 unit tests
- 2 integration tests

*Risks*:
- Cache inconsistency -> Mitigated with write-through + invalidation
- Redis failure -> Mitigated with DB fallback

Approve: :+1:
Request changes: :-1: + comment

_Spec file: data/specs/TASK-2026-0129-001_spec.md_
```

## Output Example

```
## Tech Spec Complete

**Spec ID**: SPEC-TASK-2026-0129-001
**Task**: Implement API Response Caching

### Summary
Implementing Redis cache layer with write-through caching strategy.
Incorporated existing decisions (5-min TTL, key format).

### File Change Plan
| File | Change |
|------|--------|
| src/cache/__init__.py | Create |
| src/cache/redis_client.py | Create |
| src/cache/cache_decorator.py | Create |
| src/cache/invalidation.py | Create |
| src/api/routes.py | Modify |
| src/config.py | Modify |
| tests/test_cache.py | Create |

### Test Plan
- Unit tests: 8
- Integration tests: 2

### Approval Request
- Sent to: #engineering (thread: 1706500000)
- Status: Awaiting second approval

### Created File
- data/specs/TASK-2026-0129-001_spec.md

### Next Steps
After approval, implement code:
```
claude -p "Implement according to data/specs/TASK-2026-0129-001_spec.md"
```
Or
```
codex -p "implement according to spec"
```

After implementation: `/approve TASK-2026-0129-001`
```

## Fallback Strategy Summary

| Primary (mcp__slack__) | Fallback (mcp__slack-bot-mcp__) |
|------------------------|----------------------------------|
| `slack_send_message` | `slack_post_message` or `slack_reply_to_thread` |
