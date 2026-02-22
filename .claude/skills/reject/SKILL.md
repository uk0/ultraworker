---
description: Reject the current stage and request revisions. Records the rejection reason and sends a notification to Slack.
---

# /reject - Stage Rejection

## Language

All output, Slack messages, and user-facing text from this skill MUST follow the language setting in `ultrawork.yaml` (`language.default`). Check the `## Language Configuration` section in CLAUDE.md for the current language. Technical terms, code, file paths, and commands remain in their original form.

Reject the current workflow stage and request revisions.

## Usage

```
/reject TASK-2026-0129-001 "Error handling is missing"
/reject TASK-2026-0129-001 --reason "Insufficient test cases" --user U06CLS6E694
```

## Arguments

| Argument | Description | Example |
|----------|-------------|---------|
| Task ID | Required. Task ID | `TASK-2026-0129-001` |
| Rejection reason | Required. Reason in quotes | `"Missing error handling"` |
| `--reason` | Rejection reason (explicit) | `--reason "Insufficient tests"` |
| `--user` | Rejector User ID | `--user U06CLS6E694` |

## Detailed Execution Steps

### Step 1: Check Task Status

```
Read data/tasks/TASK-2026-0129-001.md
```

Current status:
```yaml
workflow:
  current_stage: "tech_spec"
  stages:
    tech_spec:
      status: "pending"  # Awaiting review
```

### Step 2: Record Rejection

Update task file:
```yaml
workflow:
  stages:
    tech_spec:
      status: "rejected"
      rejected_at: "2026-01-29T11:45:00"
      rejected_by: "U06CLS6E694"
      rejection_reason: "Error handling logic is missing. Fallback handling is needed for Redis connection failures."
      revision_count: 1
trace:
  - ts: "2026-01-29T11:45:00"
    action: "stage_rejected"
    stage: "tech_spec"
    details:
      rejected_by: "U06CLS6E694"
      reason: "Error handling logic is missing..."
      revision: 1
```

### Step 3: Send Slack Notification (Block Kit)

Build the message using `BlockKitBuilder.build_rejection_notification()` from `src/ultrawork/slack/block_kit.py`:

```python
from ultrawork.slack.block_kit import BlockKitBuilder

msg = BlockKitBuilder.build_rejection_notification(
    task_id="TASK-2026-0129-001",
    stage="Tech Spec",
    user_id="U06CLS6E694",
    reason="Error handling logic is missing. Fallback handling is needed for Redis connection failures.",
    revision_count=1,
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

Block Kit rejection notification structure:

```json
{
  "blocks": [
    {"type": "header", "text": {"type": "plain_text", "text": ":x:  Revision Requested", "emoji": true}},
    {"type": "section", "fields": [
      {"type": "mrkdwn", "text": "*Task*\n`TASK-2026-0129-001`"},
      {"type": "mrkdwn", "text": "*Rejected Stage*\nTech Spec"},
      {"type": "mrkdwn", "text": "*Rejected By*\n<@U06CLS6E694> (reaction)"},
      {"type": "mrkdwn", "text": "*Revision Count*\n1"}
    ]},
    {"type": "divider"},
    {"type": "section", "text": {"type": "mrkdwn", "text": ":speech_balloon: *Reason*\n> Error handling logic is missing. Fallback handling is needed for Redis connection failures."}},
    {"type": "divider"},
    {"type": "section", "text": {"type": "mrkdwn", "text": ":pencil2: Please incorporate the feedback and resubmit."}},
    {"type": "context", "elements": [{"type": "mrkdwn", "text": "_Task: TASK-2026-0129-001 | Revision limit: 3_"}]}
  ],
  "text": ":x: Revision Requested - TASK-2026-0129-001 (Tech Spec)"
}
```

### Step 4: Stage-specific Revision Guidance

#### TODO Rejection

```
## TODO Revision Needed

**Task**: TASK-2026-0129-001
**Rejected Stage**: TODO
**Revision Count**: 1

### Rejection Reason
> TODO items are too abstract. Please include specific file names and function names.

### Current Status
[ ] TODO - Rejected (revision needed)
[ ] Tech Spec
[ ] Code Work
[ ] Final Report

### How to Revise
1. Edit task file:
   ```
   Edit data/tasks/TASK-2026-0129-001.md
   ```

2. Update TODO section:
   ```markdown
   ## TODO

   - [ ] Create src/cache/redis_client.py - Redis connection class
   - [ ] Create src/cache/cache_decorator.py - @cached decorator
   ...
   ```

3. After revision complete:
   Leave a revision complete message in the Slack thread for re-review.
```

#### Tech Spec Rejection

```
## Tech Spec Revision Needed

**Task**: TASK-2026-0129-001
**Rejected Stage**: Tech Spec
**Revision Count**: 1

### Rejection Reason
> Error handling logic is missing. Fallback handling is needed for Redis connection failures.

### Current Status
[x] TODO - Approved
[ ] Tech Spec - Rejected (revision needed)
[ ] Code Work
[ ] Final Report

### How to Revise
1. Edit spec file:
   ```
   Edit data/specs/TASK-2026-0129-001_spec.md
   ```

2. Add error handling section:
   ```markdown
   ### 3.6 Error Handling (Added)

   File: `src/cache/redis_client.py`

   ```python
   class CacheClient:
       def get(self, key: str) -> str | None:
           try:
               return self.client.get(key)
           except redis.ConnectionError:
               logger.warning(f"Redis connection failed, fallback to None")
               return None  # Fallback: treat as cache miss
   ```
   ```

3. Resubmit after revision:
   ```
   /write-spec TASK-2026-0129-001 --resubmit
   ```
```

#### Code Work Rejection

```
## Code Revision Needed

**Task**: TASK-2026-0129-001
**Rejected Stage**: Code Work
**Revision Count**: 1

### Rejection Reason
> Test coverage is below 70%. Please add edge case tests.

### Current Status
[x] TODO - Approved
[x] Tech Spec - Approved
[ ] Code Work - Rejected (revision needed)
[ ] Final Report

### How to Revise
1. Add missing tests:
   ```python
   # tests/test_cache.py

   def test_cache_connection_failure():
       """Test fallback on Redis connection failure"""
       ...

   def test_cache_empty_value():
       """Test caching empty values"""
       ...
   ```

2. Run tests:
   ```bash
   pytest --cov=src/cache tests/test_cache.py
   ```

3. Request re-approval after verifying coverage:
   ```
   /approve TASK-2026-0129-001
   ```
```

#### Final Report Rejection

```
## Report Revision Needed

**Task**: TASK-2026-0129-001
**Rejected Stage**: Final Report
**Revision Count**: 1

### Rejection Reason
> Performance benchmark results are missing. Please include response time improvement numbers.

### Current Status
[x] TODO - Approved
[x] Tech Spec - Approved
[x] Code Work - Approved
[ ] Final Report - Rejected (revision needed)

### How to Revise
1. Run benchmarks:
   ```bash
   pytest tests/benchmark_api.py --benchmark-json=benchmark.json
   ```

2. Update report section in task file:
   ```markdown
   ### Performance Results

   | Metric | Before | After | Improvement |
   |--------|--------|-------|-------------|
   | Avg response time | 800ms | 95ms | 88% |
   | P99 response time | 1200ms | 150ms | 87% |
   | Cache hit rate | N/A | 85% | - |
   ```

3. Regenerate report:
   ```
   /report TASK-2026-0129-001 --resubmit
   ```
```

## Revision Limit

- Default maximum revisions: **3**
- Escalation required after 3 rejections

```
*Revision Limit Reached*

TASK-2026-0129-001 tech_spec stage has been rejected 3 times.

Manual review is required:
- Re-review task requirements
- Consider assigning to different owner
- Consider reducing scope
```

## Output Example

```
## Rejection Processed

**Task**: TASK-2026-0129-001
**Stage**: Tech Spec
**Rejected by**: @hm
**Revision Count**: 1/3

### Rejection Reason
Error handling logic is missing. Fallback handling is needed for Redis connection failures.

### Current Status
[x] TODO - Approved
[ ] Tech Spec - Rejected <- Revision needed
[ ] Code Work
[ ] Final Report

### Slack Notification
- Sent to: #engineering (thread: 1706500000)
- Status: Revision request sent

### Next Steps
1. Edit data/specs/TASK-2026-0129-001_spec.md
2. Add error handling section
3. `/write-spec TASK-2026-0129-001 --resubmit`
```

## Notes

- Specific reason required for rejection
- Cannot reject with empty reason
- All rejections are recorded in trace
- Constructive feedback recommended

## Fallback Strategy Summary

| Primary (mcp__slack__) | Fallback (mcp__slack-bot-mcp__) |
|------------------------|----------------------------------|
| `slack_send_message` | `slack_post_message` or `slack_reply_to_thread` |
