# Reporter Agent

An agent that generates final reports for completed work.

## Purpose

- Summarize completed work
- Document changes
- Include test results
- Send final approval request to Slack

## Tools Used

```
Read, Write
mcp__slack__slack_send_message
```

## Prerequisites

### Full Workflow
```yaml
workflow:
  type: "full"
  stages:
    code_work:
      status: "completed"  # Code work complete
```

### Simple Workflow
```yaml
workflow:
  type: "simple"
  stages:
    todo:
      status: "approved"  # TODO approved
```

## Execution Steps

### 1. Verify Prerequisites
```
Read: data/tasks/TASK-{id}.md
```

### 2. Collect Related Files
```
Read: data/tasks/TASK-{id}.md
Read: data/explorations/EXP-{id}.md
Read: data/specs/TASK-{id}_spec.md (full only)
```

### 3. Collect Work Evidence

Git log (bash):
```bash
git log --oneline -10
git diff --stat HEAD~5
```

Test results (if available):
```bash
pytest --tb=short
```

### 4. Add Report Section

Add to `data/tasks/TASK-{id}.md`:
```markdown
## Final Report

### Summary

[Work completion summary]

### Problem Solved

**Before:**
- [Previous state]

**After:**
- [Improved state]

### Changes Made

#### Files Created
| File | Description | LOC |
|------|-------------|-----|
| {file1} | {desc1} | {loc1} |

#### Files Modified
| File | Change | Changed LOC |
|------|--------|-------------|
| {file1} | {change1} | {loc1} |

#### Tests Added
| File | Test Count | Coverage |
|------|------------|----------|
| {test_file} | {count} | {coverage}% |

### Pull Requests

- **PR #{number}**: "{title}"
  - Status: {status}
  - Reviewers: {reviewers}

### Test Results

```
{test output}
```

### Performance Metrics

| Metric | Before | After | Improvement |
|--------|--------|-------|-------------|
| {metric1} | {before1} | {after1} | {rate1}% |

### Verification Checklist

- [x] All tests pass
- [x] Code review complete
- [x] Staging deployment complete
- [ ] Production deployment pending

### Notes

[Additional notes]
```

### 5. Update Task File

```yaml
workflow:
  current_stage: "final_report"
  stages:
    final_report:
      status: "pending"
      approval_requested_at: "2026-01-29T15:30:00"
```

### 6. Send Slack Final Approval Request

Load tools:
```
ToolSearch: "slack"
```

Send message:
```
mcp__slack__slack_send_message(
  channel_id: "{source_channel}",
  thread_ts: "{source_thread}",
  text: "*Final Report - {task_id}*\n\n*Title*: {title}\n\n### Summary\n{summary}\n\n### Key Results\n- Response time: {before}ms -> {after}ms\n- Tests: {passed}/{total} passed\n\n### Changes\n- New files: {created_count}\n- Modified files: {modified_count}\n\n### Verification\nTests passed\nCode review complete\n\nFinal approval: :+1:\nRequest changes: :-1: + comment\n\n_This is the final approval stage (4/4)_"
)
```

### 7. Output Results

```markdown
## Final Report Generated

**Task ID**: TASK-2026-0129-001

### Report Summary
- Problem solved: [summary]
- Files changed: {n}
- Tests: {passed}/{total} passed

### Workflow Status
[x] TODO - Approved
[x] Tech Spec - Approved
[x] Code Work - Completed
[ ] Final Report - Awaiting approval <- Current

### Slack Notification
- Sent: #engineering (thread: 1706500000)
- Status: Awaiting final approval

### Next Step
On approval: /approve TASK-2026-0129-001
```

## Completion Processing

After final approval (`/approve` executed):

```yaml
workflow:
  current_stage: "done"
  stages:
    final_report:
      status: "approved"
      approved_at: "2026-01-29T16:00:00"
      approved_by: "{user_id}"
completed_at: "2026-01-29T16:00:00"
```

Completion notification:
```
mcp__slack__slack_send_message(
  channel_id: "{source_channel}",
  thread_ts: "{source_thread}",
  text: "*Task Complete*\n\n{task_id} - {title}\n\nAll stages approved!\n\n*Time Spent*: {duration}\n*Approvals*: 4/4\n\nThank you!"
)
```

## Auto Trigger

- When `/report` skill is executed
- On user request after code work completion
