---
description: Generate a final report for completed work and send the last approval request to Slack.
---

# /report - Generate Final Report

## Language

All output, Slack messages, and user-facing text from this skill MUST follow the language setting in `ultrawork.yaml` (`language.default`). Check the `## Language Configuration` section in CLAUDE.md for the current language. Technical terms, code, file paths, and commands remain in their original form.

Compile completed work into a final report.

## Usage

```
/report TASK-2026-0129-001
/report TASK-2026-0129-001 --include-metrics
/report TASK-2026-0129-001 --resubmit
```

## Arguments

| Argument | Description | Example |
|----------|-------------|---------|
| Task ID | Required. Task ID | `TASK-2026-0129-001` |
| `--include-metrics` | Include performance metrics | `--include-metrics` |
| `--resubmit` | Resubmit after rejection | `--resubmit` |

## Prerequisites

### Full Workflow
- `code_work` stage must be completed

### Simple Workflow
- `todo` stage must be approved
- Work must be completed

## Detailed Execution Steps

### Step 1: Verify Prerequisites

```
Read data/tasks/TASK-2026-0129-001.md
```

Full Workflow verification:
```yaml
workflow:
  type: "full"
  stages:
    code_work:
      status: "completed"  # Completed
```

### Step 2: Collect Related Files

```
Read data/tasks/TASK-2026-0129-001.md
Read data/explorations/EXP-2026-0129-001.md
Read data/specs/TASK-2026-0129-001_spec.md
```

### Step 3: Collect Work Evidence

Check Git changes:
```bash
git log --oneline -10
git diff --stat HEAD~5
```

Test results:
```bash
pytest --tb=short
```

### Step 4: Generate Report

Add Final Report section to task file

(See existing documentation for detailed report template)

### Step 5: Send Slack Final Approval Request (Block Kit)

Build the message using `BlockKitBuilder.build_final_report_approval()` from `src/ultrawork/slack/block_kit.py`:

```python
from ultrawork.slack.block_kit import BlockKitBuilder

msg = BlockKitBuilder.build_final_report_approval(
    task_id="TASK-2026-0129-001",
    title="Implement API Response Caching",
    summary="Added write-through Redis cache layer, improving API response time by 88%.",
    results=[
        "Response time: 800ms -> 95ms (88% improvement)",
        "Cache hit rate: 85%",
    ],
    changes_summary="• New files: 4 (src/cache/*)\n• Modified files: 2\n• Tests: 10 added (92% coverage)",
    verification="Tests passed (18/18)\nCode review complete (PR #42)\nStaging deployment complete",
    stage_num=4,
    total_stages=4,
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

Block Kit final report approval message structure:

```json
{
  "blocks": [
    {"type": "header", "text": {"type": "plain_text", "text": ":clipboard:  Final Report", "emoji": true}},
    {"type": "section", "fields": [
      {"type": "mrkdwn", "text": "*Task*\nImplement API Response Caching"},
      {"type": "mrkdwn", "text": "*Task ID*\n`TASK-2026-0129-001`"},
      {"type": "mrkdwn", "text": "*Stage*\nFinal Report (4/4)"}
    ]},
    {"type": "divider"},
    {"type": "section", "text": {"type": "mrkdwn", "text": ":page_with_curl: *Summary*\nAdded write-through Redis cache layer, improving API response time by 88%."}},
    {"type": "divider"},
    {"type": "section", "text": {"type": "mrkdwn", "text": ":trophy: *Key Results*"}},
    {"type": "section", "text": {"type": "mrkdwn", "text": "• Response time: 800ms -> 95ms (88% improvement)\n• Cache hit rate: 85%"}},
    {"type": "divider"},
    {"type": "section", "text": {"type": "mrkdwn", "text": ":hammer_and_wrench: *Changes*\n• New files: 4 (src/cache/*)\n• Modified files: 2\n• Tests: 10 added (92% coverage)"}},
    {"type": "divider"},
    {"type": "section", "text": {"type": "mrkdwn", "text": ":white_check_mark: *Verification*\nTests passed (18/18)\nCode review complete (PR #42)\nStaging deployment complete"}},
    {"type": "divider"},
    {"type": "actions", "block_id": "approval_TASK-2026-0129-001_final_report", "elements": [
      {"type": "button", "text": {"type": "plain_text", "text": ":tada: Final Approval", "emoji": true}, "style": "primary", "action_id": "uw_approve_final_report", "value": "{\"task_id\":\"TASK-2026-0129-001\",\"stage\":\"final_report\",\"channel_id\":\"C0123456789\",\"thread_ts\":\"1706500000.000000\"}"},
      {"type": "button", "text": {"type": "plain_text", "text": ":x: Request Changes", "emoji": true}, "style": "danger", "action_id": "uw_reject_final_report", "value": "{\"task_id\":\"TASK-2026-0129-001\",\"stage\":\"final_report\",\"channel_id\":\"C0123456789\",\"thread_ts\":\"1706500000.000000\"}"}
    ]},
    {"type": "context", "elements": [{"type": "mrkdwn", "text": "_This is the final approval stage | Task: TASK-2026-0129-001_"}]}
  ],
  "text": ":clipboard: Final Report - Implement API Response Caching (TASK-2026-0129-001)"
}
```

## Simple Workflow Report

```yaml
---
task_id: "TASK-2026-0129-002"
workflow:
  type: "simple"
  current_stage: "final_report"
---

## Final Report

### Summary
Completed API caching documentation updates.

### Actions Taken
1. Added caching section to README.md
2. Added cache-related header descriptions to API docs
3. Documented response time changes

### Files Updated
| File | Change |
|------|--------|
| README.md | Added caching description |
| docs/api.md | Added header descriptions |

### Verification
- [x] Document content reviewed
- [x] Link validity confirmed
```

## Output Example

```
## Final Report Generated

**Task ID**: TASK-2026-0129-001
**Title**: Implement API Response Caching

### Report Summary
- Problem solved: API response time 800ms -> 95ms (88% improvement)
- Files changed: 6 (4 new, 2 modified)
- Tests: 10 added (92% coverage)
- PR: #42 (Merged)

### Verification Status
Tests passed (18/18)
Code review complete
Staging deployment complete
Performance benchmarks complete

### Workflow Status
[x] TODO - Approved
[x] Tech Spec - Approved
[x] Code Work - Completed
[ ] Final Report - Awaiting approval <- Current

### Slack Notification
- Sent to: #engineering (thread: 1706500000)
- Status: Awaiting final approval (4/4)

### File Updated
- data/tasks/TASK-2026-0129-001.md (report section added)

### Next Steps
- Await final approval on Slack
- On approval: `/approve TASK-2026-0129-001`
- After approval, proceed with production deployment
```

## Completion After Approval

On final approval (after `/approve` execution), build the completion message using `BlockKitBuilder.build_completion_notification()`:

```python
from ultrawork.slack.block_kit import BlockKitBuilder

msg = BlockKitBuilder.build_completion_notification(
    task_id="TASK-2026-0129-001",
    title="Implement API Response Caching",
    duration="5 hours 30 minutes",
    approval_count=4,
    total_stages=4,
)
```

Block Kit completion message structure:

```json
{
  "blocks": [
    {"type": "header", "text": {"type": "plain_text", "text": ":checkered_flag:  Task Complete", "emoji": true}},
    {"type": "section", "text": {"type": "mrkdwn", "text": "*TASK-2026-0129-001* - Implement API Response Caching"}},
    {"type": "divider"},
    {"type": "section", "text": {"type": "mrkdwn", "text": ":white_check_mark: All stages approved!"}},
    {"type": "section", "fields": [
      {"type": "mrkdwn", "text": "*Duration*\n5 hours 30 minutes"},
      {"type": "mrkdwn", "text": "*Approvals*\n4/4"}
    ]},
    {"type": "divider"},
    {"type": "context", "elements": [{"type": "mrkdwn", "text": "_Completed at 2026-01-29 16:00 | Thank you! :pray:_"}]}
  ],
  "text": ":checkered_flag: Task Complete - TASK-2026-0129-001 - Implement API Response Caching"
}
```

Final task file status:
```yaml
workflow:
  current_stage: "done"
  stages:
    final_report:
      status: "approved"
      approved_at: "2026-01-29T16:00:00"
      approved_by: "U06CLS6E694"
completed_at: "2026-01-29T16:00:00"
```

## Fallback Strategy Summary

| Primary (mcp__slack__) | Fallback (mcp__slack-bot-mcp__) |
|------------------------|----------------------------------|
| `slack_send_message` | `slack_post_message` or `slack_reply_to_thread` |
