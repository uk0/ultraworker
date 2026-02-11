# Spec Writer Agent

An agent that writes detailed tech specs based on approved TODOs.

## Purpose

- Establish implementation plan
- Analyze codebase
- Write detailed technical specification
- Plan test strategy
- Send second approval request to Slack

## Tools Used

```
Read, Write, Glob, Grep
mcp__slack__slack_send_message
```

## Prerequisites

Verify before execution:
```yaml
workflow:
  current_stage: "todo"
  stages:
    todo:
      status: "approved"  # Must be approved
```

## Execution Steps

### 1. Verify Prerequisites
```
Read: data/tasks/TASK-{id}.md
```

If not approved:
```
Error: TODO stage has not been approved yet.
Current status: pending

Please get approval first.
```

### 2. Collect Context
```
Read: data/tasks/TASK-{id}.md
Read: data/explorations/EXP-{id}.md
```

### 3. Analyze Codebase

Search related files:
```
Glob: **/*.py
Glob: **/*.ts
```

Search keywords:
```
Grep: "related keyword"
Grep: "function name"
Grep: "class name"
```

Organize analysis results:
- List of files to modify
- Dependency check
- Test file locations

### 4. Write Tech Spec

`data/specs/TASK-{id}_spec.md`:
```yaml
---
spec_id: "SPEC-TASK-2026-0129-001"
task_id: "TASK-2026-0129-001"
version: 1
created_at: "2026-01-29T11:00:00"
status: "pending_approval"
---

# Technical Specification: {title}

## 1. Problem Statement

### 1.1 Background
[Problem background and context]

### 1.2 Current Architecture
```
[Current architecture diagram]
```

### 1.3 Target Architecture
```
[Target architecture diagram]
```

## 2. Proposed Solution

### 2.1 Overview
[Solution overview]

### 2.2 Key Decisions
| Item | Decision | Rationale |
|------|----------|-----------|
| {item1} | {decision1} | {rationale1} |

### 2.3 Components
```
[Component structure]
```

## 3. Implementation Details

### 3.1 {Component 1}

File: `src/path/file.py`

```python
# Implementation code or pseudo code
class ClassName:
    def method_name(self):
        pass
```

### 3.2 {Component 2}
[Same format]

## 4. Files Summary

| File | Change | Description |
|------|--------|-------------|
| src/file1.py | Create | Description |
| src/file2.py | Modify | Description |

## 5. Testing Strategy

### 5.1 Unit Tests
```python
def test_scenario_1():
    # Test code
    pass
```

### 5.2 Integration Tests
[Integration test plan]

## 6. Rollout Plan

1. Install dependencies
2. Deploy to staging
3. Run tests
4. Deploy to production

### Rollback Plan
[Rollback procedure]

## 7. Risks and Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| {risk1} | Medium | High | {mitigation} |

## 8. Open Questions

- [ ] {Open question 1}
- [ ] {Open question 2}
```

### 5. Update Task File
```
Edit: data/tasks/TASK-{id}.md
```

Changes:
```yaml
workflow:
  current_stage: "tech_spec"
  stages:
    todo:
      status: "approved"
    tech_spec:
      status: "pending"
      approval_requested_at: "2026-01-29T11:00:00"
```

### 6. Send Slack Second Approval Request

Load tools:
```
ToolSearch: "slack"
```

Send message:
```
mcp__slack__slack_send_message(
  channel_id: "{source_channel}",
  thread_ts: "{source_thread}",
  text: "*Tech Spec Review Request*\n\n*Task*: {title}\n\n*Key Changes*:\n- {file1}: {change1}\n- {file2}: {change2}\n\n*Test Plan*:\n- {n} unit tests\n- {m} integration tests\n\nApprove: :+1:\nRequest changes: :-1: + comment\n\n_Spec: data/specs/TASK-{id}_spec.md_"
)
```

### 7. Output Results

```markdown
## Tech Spec Complete

**Spec ID**: SPEC-TASK-2026-0129-001

### Summary
[Solution summary]

### File Change Plan
- Create: 4
- Modify: 2

### Approval Request
- Sent: #engineering (thread: 1706500000)
- Status: Awaiting second approval

### Next Step
After approval, implement code:
```
claude -p "Implement according to data/specs/TASK-{id}_spec.md"
```
```

## Auto Trigger

- When `/write-spec` skill is executed
- On user request after TODO approval
