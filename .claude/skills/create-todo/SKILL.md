---
description: Create an actionable TODO list based on exploration results (EXP-*) and send a first approval request to Slack.
---

# /create-todo - Create TODO

## Language

All output, Slack messages, and user-facing text from this skill MUST follow the language setting in `ultrawork.yaml` (`language.default`). Check the `## Language Configuration` section in CLAUDE.md for the current language. Technical terms, code, file paths, and commands remain in their original form.

Create a TODO list based on exploration results and request approval.

## Usage

```
/create-todo EXP-2026-0129-001
/create-todo EXP-2026-0129-001 --simple
/create-todo EXP-2026-0129-001 --title "Implement API Caching"
```

## Arguments

| Argument | Description | Example |
|----------|-------------|---------|
| Exploration ID | Required. Exploration result ID | `EXP-2026-0129-001` |
| `--simple` | Simple workflow (no code, 2 stages) | `--simple` |
| `--title` | Specify task title directly | `--title "Implement Caching"` |

## Detailed Execution Steps

### Step 1: Read Exploration Results

```
Read data/explorations/EXP-2026-0129-001.md
```

Information to extract:
- `current_problem`: Problem to solve
- `recommended_actions`: Recommended actions
- `trigger.channel_id`, `trigger.message_ts`: Original thread info
- `key_decisions`: Already decided items

### Step 2: Determine Workflow Type

**Full Workflow** (default):
- Tasks requiring code changes
- New feature implementation
- Bug fixes
- Refactoring

**Simple Workflow** (`--simple`):
- Documentation updates
- Configuration changes
- Information verification
- Process-related tasks

### Step 3: Generate TODO Items

Convert recommended actions to specific TODOs:

```markdown
## TODO

- [ ] Install Redis client library (redis-py)
- [ ] Create cache utility module (src/cache/redis_cache.py)
- [ ] Implement write-through cache decorator
- [ ] Apply cache decorator to API endpoints
- [ ] Implement cache invalidation logic (on data changes)
- [ ] Write unit tests (tests/test_cache.py)
- [ ] Write integration tests
- [ ] Run performance benchmarks and document
```

### Step 4: Create Task File

`data/tasks/TASK-2026-0129-001.md`:

```yaml
---
task_id: "TASK-2026-0129-001"
title: "Implement API Response Caching"
workflow:
  type: "full"
  current_stage: "todo"
  stages:
    todo:
      status: "pending"
      approval_requested_at: "2026-01-29T10:15:00"
      approved_at: null
      approved_by: null
    tech_spec:
      status: "pending"
      approval_requested_at: null
      approved_at: null
      approved_by: null
    code_work:
      status: "pending"
      started_at: null
      completed_at: null
    final_report:
      status: "pending"
      approval_requested_at: null
      approved_at: null
      approved_by: null
source:
  type: "slack_mention"
  channel_id: "C0123456789"
  thread_ts: "1706500000.000000"
  exploration_id: "EXP-2026-0129-001"
created_at: "2026-01-29T10:15:00"
updated_at: "2026-01-29T10:15:00"
todo_items:
  - "Install Redis client library"
  - "Create cache utility module"
  - "Implement write-through cache decorator"
  - "Apply cache to API endpoints"
  - "Implement cache invalidation logic"
  - "Write unit tests"
  - "Write integration tests"
  - "Run performance benchmarks"
trace:
  - ts: "2026-01-29T10:15:00"
    action: "created"
    details:
      from_exploration: "EXP-2026-0129-001"
      workflow_type: "full"
---

## TODO

- [ ] Install Redis client library (redis-py)
- [ ] Create cache utility module (src/cache/redis_cache.py)
- [ ] Implement write-through cache decorator
- [ ] Apply cache decorator to API endpoints
- [ ] Implement cache invalidation logic (on data changes)
- [ ] Write unit tests (tests/test_cache.py)
- [ ] Write integration tests
- [ ] Run performance benchmarks and document

## Context Summary

### Problem
API response time averages 800ms, approaching SLA violation. Target 200ms or less with Redis caching.

### Already Decided
- Caching strategy: Write-through (decided 2026-01-27)
- TTL: 5 minutes (decided 2026-01-28)
- Cache key format: `{service}:{resource}:{id}`

### Related Threads
- [Original request] C0123456789-1706500000
- [Strategy discussion] C0987654321-1706300000
- [TTL decision] C0123456789-1706400000

## Acceptance Criteria

- [ ] API response time < 200ms after cache implementation
- [ ] Cache hit rate > 80%
- [ ] No stale data served on data changes
- [ ] All tests pass

## Estimated Effort

- Total estimated effort: Medium (2-3 days)
- Main work: Cache layer implementation and testing
```

### Step 5: Send Slack Approval Request (Block Kit)

Build the message using `BlockKitBuilder.build_todo_approval()` from `src/ultrawork/slack/block_kit.py`:

```python
from ultrawork.slack.block_kit import BlockKitBuilder

msg = BlockKitBuilder.build_todo_approval(
    task_id="TASK-2026-0129-001",
    title="Implement API Response Caching",
    workflow_type="full",
    todo_items=[
        "Install Redis client library",
        "Create cache utility module",
        "Implement write-through cache decorator",
        "Apply cache to API endpoints",
        "Implement cache invalidation logic",
        "Write unit tests",
        "Write integration tests",
        "Run performance benchmarks",
    ],
    exploration_id="EXP-2026-0129-001",
    estimated_effort="Medium (2-3 days)",
    decisions=["Write-through approach (decided 1/27)", "TTL 5 minutes (decided 1/28)"],
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

Block Kit approval message structure:

```json
{
  "blocks": [
    {"type": "header", "text": {"type": "plain_text", "text": ":clipboard:  TODO List Review Request", "emoji": true}},
    {"type": "section", "fields": [
      {"type": "mrkdwn", "text": "*Task*\nImplement API Response Caching"},
      {"type": "mrkdwn", "text": "*Type*\nFull Workflow (4-stage)"},
      {"type": "mrkdwn", "text": "*Task ID*\n`TASK-2026-0129-001`"},
      {"type": "mrkdwn", "text": "*Based on*\n`EXP-2026-0129-001`"}
    ]},
    {"type": "divider"},
    {"type": "section", "text": {"type": "mrkdwn", "text": ":memo: *TODO Items*"}},
    {"type": "section", "text": {"type": "mrkdwn", "text": "1. Install Redis client library\n2. Create cache utility module\n3. Implement write-through cache decorator\n4. Apply cache to API endpoints\n5. Implement cache invalidation logic\n6. Write unit tests\n7. Write integration tests\n8. Run performance benchmarks"}},
    {"type": "divider"},
    {"type": "section", "text": {"type": "mrkdwn", "text": ":bulb: *Already Decided*"}},
    {"type": "section", "text": {"type": "mrkdwn", "text": "• Write-through approach (decided 1/27)\n• TTL 5 minutes (decided 1/28)"}},
    {"type": "divider"},
    {"type": "section", "text": {"type": "mrkdwn", "text": ":bar_chart: *Estimated Effort*: Medium (2-3 days)"}},
    {"type": "divider"},
    {"type": "actions", "block_id": "approval_TASK-2026-0129-001_todo", "elements": [
      {"type": "button", "text": {"type": "plain_text", "text": ":white_check_mark: Approve", "emoji": true}, "style": "primary", "action_id": "uw_approve_todo", "value": "{\"task_id\":\"TASK-2026-0129-001\",\"stage\":\"todo\",\"channel_id\":\"C0123456789\",\"thread_ts\":\"1706500000.000000\"}"},
      {"type": "button", "text": {"type": "plain_text", "text": ":x: Request Changes", "emoji": true}, "style": "danger", "action_id": "uw_reject_todo", "value": "{\"task_id\":\"TASK-2026-0129-001\",\"stage\":\"todo\",\"channel_id\":\"C0123456789\",\"thread_ts\":\"1706500000.000000\"}"}
    ]},
    {"type": "context", "elements": [{"type": "mrkdwn", "text": "_Task ID: TASK-2026-0129-001 | Stage 1/4_"}]}
  ],
  "text": ":clipboard: TODO Review Request - Implement API Response Caching (TASK-2026-0129-001)"
}
```

## Output Example

```
## TODO Created

**Task ID**: TASK-2026-0129-001
**Title**: Implement API Response Caching
**Workflow**: Full (4-stage approval)

### TODO Items (8)
1. Install Redis client library
2. Create cache utility module
3. Implement write-through cache decorator
4. Apply cache to API endpoints
5. Implement cache invalidation logic
6. Write unit tests
7. Write integration tests
8. Run performance benchmarks

### Workflow Stages
1. TODO -> [Current - Awaiting approval]
2. Tech Spec
3. Code Work
4. Final Report

### Approval Request
- Sent to: #engineering (thread: 1706500000)
- Status: Awaiting first approval

### Created Files
- data/tasks/TASK-2026-0129-001.md

### Next Steps
- Await Slack approval
- After approval: `/write-spec TASK-2026-0129-001`
```

## Simple Workflow TODO Example

When running `/create-todo EXP-2026-0129-002 --simple`:

```yaml
---
task_id: "TASK-2026-0129-002"
title: "Update API Documentation"
workflow:
  type: "simple"
  current_stage: "todo"
  stages:
    todo:
      status: "pending"
    final_report:
      status: "pending"
---

## TODO

- [ ] Update caching-related API documentation
- [ ] Document response time changes
- [ ] Add cache-related header descriptions

## Context Summary
Documentation update needed after API caching implementation.
```

Simple Workflow skips tech_spec and code_work stages, requiring only 2-stage approval.

## Fallback Strategy Summary

| Primary (mcp__slack__) | Fallback (mcp__slack-bot-mcp__) |
|------------------------|----------------------------------|
| `slack_send_message` | `slack_post_message` or `slack_reply_to_thread` |
