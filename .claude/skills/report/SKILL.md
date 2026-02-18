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

### Step 5: Send Slack Final Approval Request

```
ToolSearch: "slack"
```

```
mcp__slack__slack_send_message(
  channel_id: "C0123456789",
  thread_ts: "1706500000.000000",
  text: final_report_message
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
  text: final_report_message
)
```

Or:
```
mcp__slack-bot-mcp__slack_post_message(
  channel_id: "C0123456789",
  text: final_report_message
)
```

Message:
```
*Final Report - TASK-2026-0129-001*

*Title*: Implement API Response Caching

### Summary
Added write-through Redis cache layer, improving API response time by 88%.

### Key Results
| Metric | Before | After |
|--------|--------|-------|
| Response time | 800ms | 95ms |
| Cache hit rate | - | 85% |

### Changes
- New files: 4 (src/cache/*)
- Modified files: 2
- Tests: 10 added (92% coverage)

### Verification
Tests passed (18/18)
Code review complete (PR #42)
Staging deployment complete

Final approval: :+1:
Request changes: :-1: + comment

_This is the final approval stage (4/4)_
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

On final approval (after `/approve` execution):

```
*Task Complete*

TASK-2026-0129-001 - Implement API Response Caching

All stages approved!

*Time Spent*: 5 hours 30 minutes
*Approvals*: 4/4

*Results*:
- 88% response time improvement
- SLA compliance achieved

Thank you!
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
