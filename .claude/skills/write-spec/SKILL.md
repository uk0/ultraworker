---
description: Write detailed tech spec based on approved TODO and send second approval request to Slack. Analyzes codebase and creates implementation plan.
---

# /write-spec - Write Tech Spec

## Language

All output, Slack messages, and user-facing text from this skill MUST follow the language setting in `ultrawork.yaml` (`language.default`). Check the `## Language Configuration` section in CLAUDE.md for the current language. Technical terms, code, file paths, and commands remain in their original form.

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

### Step 1.5: Search Existing Memory

Before deep analysis, search LTM for related past work on the same files or topics.

```
/recall --what "relevant topics from the TODO"
/recall --where "files that will be modified"
```

Incorporate any discovered past decisions or architectural context into the spec.

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

### Step 6: Send Slack Second Approval Request (Block Kit)

Build the message using `BlockKitBuilder.build_spec_approval()` from `src/ultrawork/slack/block_kit.py`:

```python
from ultrawork.slack.block_kit import BlockKitBuilder

msg = BlockKitBuilder.build_spec_approval(
    task_id="TASK-2026-0129-001",
    title="Implement API Response Caching",
    file_changes=[
        "Create `src/cache/` package (4 files)",
        "Modify `src/api/routes.py` (apply decorator)",
        "Modify `src/config.py` (Redis settings)",
    ],
    test_plan="• 8 unit tests\n• 2 integration tests",
    spec_file="data/specs/TASK-2026-0129-001_spec.md",
    channel_id="C0123456789",
    thread_ts="1706500000.000000",
)
# msg = {"blocks": [...], "text": "fallback text"}
```

Send via MCP tools:

```
ToolSearch: "slack"
```

```
mcp__slack__slack_send_message(
  channel_id: "C0123456789",
  thread_ts: "1706500000.000000",
  text: msg["text"],
  blocks: json.dumps(msg["blocks"])
)
```

> **Note**: The `blocks` parameter must be a JSON string of the blocks array. The `text` field serves as the fallback for notifications and clients that do not support Block Kit.

**Fallback on failure:**
```
ToolSearch: "+slack-bot"
```
```
mcp__slack-bot-mcp__slack_reply_to_thread(
  channel_id: "C0123456789",
  thread_ts: "1706500000.000000",
  text: msg["text"],
  blocks: json.dumps(msg["blocks"])
)
```

Or:
```
mcp__slack-bot-mcp__slack_post_message(
  channel_id: "C0123456789",
  text: msg["text"],
  blocks: json.dumps(msg["blocks"])
)
```

Block Kit spec approval message structure:

```json
{
  "blocks": [
    {"type": "header", "text": {"type": "plain_text", "text": ":page_facing_up:  Tech Spec Review Request", "emoji": true}},
    {"type": "section", "fields": [
      {"type": "mrkdwn", "text": "*Task*\nImplement API Response Caching"},
      {"type": "mrkdwn", "text": "*Task ID*\n`TASK-2026-0129-001`"},
      {"type": "mrkdwn", "text": "*Spec File*\n`data/specs/TASK-2026-0129-001_spec.md`"},
      {"type": "mrkdwn", "text": "*Stage*\nTech Spec (2/4)"}
    ]},
    {"type": "divider"},
    {"type": "section", "text": {"type": "mrkdwn", "text": ":file_folder: *Key Changes*"}},
    {"type": "section", "text": {"type": "mrkdwn", "text": "• Create `src/cache/` package (4 files)\n• Modify `src/api/routes.py` (apply decorator)\n• Modify `src/config.py` (Redis settings)"}},
    {"type": "divider"},
    {"type": "section", "text": {"type": "mrkdwn", "text": ":test_tube: *Test Plan*\n• 8 unit tests\n• 2 integration tests"}},
    {"type": "divider"},
    {"type": "actions", "block_id": "approval_TASK-2026-0129-001_tech_spec", "elements": [
      {"type": "button", "text": {"type": "plain_text", "text": ":white_check_mark: Approve", "emoji": true}, "style": "primary", "action_id": "uw_approve_tech_spec", "value": "{\"task_id\":\"TASK-2026-0129-001\",\"stage\":\"tech_spec\",\"channel_id\":\"C0123456789\",\"thread_ts\":\"1706500000.000000\"}"},
      {"type": "button", "text": {"type": "plain_text", "text": ":x: Request Changes", "emoji": true}, "style": "danger", "action_id": "uw_reject_tech_spec", "value": "{\"task_id\":\"TASK-2026-0129-001\",\"stage\":\"tech_spec\",\"channel_id\":\"C0123456789\",\"thread_ts\":\"1706500000.000000\"}"}
    ]},
    {"type": "context", "elements": [{"type": "mrkdwn", "text": "_Spec: data/specs/TASK-2026-0129-001_spec.md | Task: TASK-2026-0129-001_"}]}
  ],
  "text": ":page_facing_up: Tech Spec Review - Implement API Response Caching (TASK-2026-0129-001)"
}
```

### Step 7: Save to Long-Term Memory

After spec is written and Slack notification sent, you MUST save a WorkRecord to LTM using `/remember`.

WorkRecord fields to save:
- **request-ref**: Related RequestRecord ID (from exploration, if available)
- **purpose**: The spec writing goal
- **action**: `spec_writing`
- **topics**: Key technical topics from the spec
- **files-created**: Path to the spec file

```
/remember work --request-ref "{req_id}" \
  --purpose "Write tech spec for {task_title}" \
  --action spec_writing --topics "{topic1},{topic2}" \
  --files-created "data/specs/{task_id}_spec.md"
```

Example:
```
/remember work --request-ref req-20260129-0001 \
  --purpose "Write tech spec for API Response Caching" \
  --action spec_writing --topics caching,redis,api-performance \
  --files-created "data/specs/TASK-2026-0129-001_spec.md"
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
