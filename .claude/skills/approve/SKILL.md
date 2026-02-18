---
description: Approve the current stage and proceed to the next step. Records approver information and timestamp, and guides to the appropriate next action.
---

# /approve - Stage Approval

## Language

All output, Slack messages, and user-facing text from this skill MUST follow the language setting in `ultrawork.yaml` (`language.default`). Check the `## Language Configuration` section in CLAUDE.md for the current language. Technical terms, code, file paths, and commands remain in their original form.

Approve the current workflow stage and proceed to the next step.

## Usage

```
/approve TASK-2026-0129-001
/approve TASK-2026-0129-001 --user U06CLS6E694
/approve TASK-2026-0129-001 --comment "LGTM, proceed"
```

## Arguments

| Argument | Description | Example |
|----------|-------------|---------|
| Task ID | Required. Task ID | `TASK-2026-0129-001` |
| `--user` | Approver User ID | `--user U06CLS6E694` |
| `--comment` | Approval comment | `--comment "LGTM"` |

## Detailed Execution Steps

### Step 1: Check Task Status

```
Read data/tasks/TASK-2026-0129-001.md
```

Check current status:
```yaml
workflow:
  current_stage: "todo"  # Current stage
  stages:
    todo:
      status: "pending"  # Awaiting approval
```

### Step 2: Validate Approval

Verify:
- Current stage is in `pending` status
- Approval request has been sent

If invalid:
```
Error: Current stage has already been approved.
Current stage: todo
Status: approved

Please proceed to the next step.
```

### Step 3: Record Approval

Update task file:
```yaml
workflow:
  stages:
    todo:
      status: "approved"
      approved_at: "2026-01-29T10:30:00"
      approved_by: "U06CLS6E694"
      approval_comment: "LGTM, proceed"
trace:
  - ts: "2026-01-29T10:30:00"
    action: "stage_approved"
    stage: "todo"
    details:
      approved_by: "U06CLS6E694"
      comment: "LGTM, proceed"
```

### Step 4: Proceed to Next Stage

```yaml
workflow:
  current_stage: "tech_spec"  # todo -> tech_spec
  stages:
    tech_spec:
      status: "pending"
```

### Step 5: Stage-specific Guidance Messages

#### After TODO Approval (Full Workflow)

```
## TODO Approved

**Task**: TASK-2026-0129-001
**Approved Stage**: TODO
**Approver**: @hm (U06CLS6E694)
**Time**: 2026-01-29 10:30:00

### Progress
[x] TODO - Approved
[ ] Tech Spec - In Progress
[ ] Code Work
[ ] Final Report

### Next Step
Tech spec needs to be written:
```
/write-spec TASK-2026-0129-001
```
```

#### After TODO Approval (Simple Workflow)

```
## TODO Approved

**Task**: TASK-2026-0129-002
**Approved Stage**: TODO
**Workflow**: Simple (2 stages)

### Progress
[x] TODO - Approved
[ ] Final Report - Pending

### Next Step
Complete the work and then generate the final report:
```
/report TASK-2026-0129-002
```
```

#### After Tech Spec Approval

```
## Tech Spec Approved

**Task**: TASK-2026-0129-001
**Approved Stage**: Tech Spec

### Progress
[x] TODO - Approved
[x] Tech Spec - Approved
[ ] Code Work - In Progress
[ ] Final Report

### Next Step
Start code implementation:

**Option 1: Claude CLI**
```bash
claude -p "Implement according to data/specs/TASK-2026-0129-001_spec.md spec"
```

**Option 2: Codex CLI**
```bash
codex -p "implement API caching according to the spec file"
```

**Option 3: Direct Implementation**
Reference spec file: `data/specs/TASK-2026-0129-001_spec.md`

After implementation:
```
/approve TASK-2026-0129-001
```
```

#### After Code Work Approval

```
## Code Work Approved

**Task**: TASK-2026-0129-001
**Approved Stage**: Code Work

### Progress
[x] TODO - Approved
[x] Tech Spec - Approved
[x] Code Work - Approved
[ ] Final Report - In Progress

### Next Step
Generate the final report:
```
/report TASK-2026-0129-001
```
```

#### After Final Report Approval

```
## Task Complete!

**Task**: TASK-2026-0129-001
**Title**: Implement API Response Caching
**Completion Time**: 2026-01-29 16:00:00

### Final Progress
[x] TODO - Approved (10:30)
[x] Tech Spec - Approved (11:30)
[x] Code Work - Approved (15:00)
[x] Final Report - Approved (16:00)

### Time Spent
- Total: 5 hours 30 minutes
- Start: 2026-01-29 10:00
- End: 2026-01-29 16:00

### Approval History
| Stage | Approver | Time |
|-------|----------|------|
| TODO | @hm | 10:30 |
| Tech Spec | @tech_lead | 11:30 |
| Code Work | @reviewer | 15:00 |
| Final Report | @hm | 16:00 |

Sending completion notification to Slack...
```

Completion notification message:
```
ToolSearch: "slack"
```

```
mcp__slack__slack_send_message(
  channel_id: "C0123456789",
  thread_ts: "1706500000.000000",
  text: completion_message
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
  text: completion_message
)
```

```
*Task Complete*

TASK-2026-0129-001 - Implement API Response Caching

All 4 stages have been approved!

*Time Spent*: 5 hours 30 minutes
*Approvals*: 4/4

Thank you!
```

## Workflow Transition Table

| Current Stage | Next Stage | Next Action |
|---------------|------------|-------------|
| todo | tech_spec | Run `/write-spec` |
| tech_spec | code_work | Implement with Claude/Codex |
| code_work | final_report | Run `/report` |
| final_report | done | Complete |

## Simple Workflow Transition Table

| Current Stage | Next Stage | Next Action |
|---------------|------------|-------------|
| todo | final_report | Work then `/report` |
| final_report | done | Complete |

## Notes

- Stages cannot be skipped
- Already approved stages cannot be re-approved
- To reject, use the `/reject` command
- All approvals are recorded in trace

## Fallback Strategy Summary

| Primary (mcp__slack__) | Fallback (mcp__slack-bot-mcp__) |
|------------------------|----------------------------------|
| `slack_send_message` | `slack_post_message` or `slack_reply_to_thread` |
