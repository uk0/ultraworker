# TODO Generator Agent

An agent that creates actionable TODO lists based on exploration results.

## Purpose

- Extract action items from exploration results
- Determine workflow type (full/simple)
- Generate specific TODO items
- Send first approval request to Slack

## Tools Used

```
Read, Write
mcp__slack__slack_send_message
```

## Execution Steps

### 1. Read Exploration Results
```
Read: data/explorations/EXP-{id}.md
```

Information to extract:
- `current_problem`: Problem to solve
- `recommended_actions`: Recommended actions
- `key_decisions`: Already decided items
- `trigger.channel_id`, `trigger.message_ts`: Original thread

### 2. Determine Workflow Type

**Full Workflow** (requires code changes):
- New feature implementation
- Bug fixes
- Refactoring
- Infrastructure changes

**Simple Workflow** (no code required):
- Documentation updates
- Configuration changes
- Information verification
- Process inquiries

### 3. Generate TODO Items

Convert recommended actions to specific TODOs:
```markdown
## TODO

- [ ] {Include specific file/function names}
- [ ] {Measurable completion criteria}
- [ ] {Can specify assignee}
```

Example:
```markdown
## TODO

- [ ] Install redis-py package (add to pyproject.toml)
- [ ] Create src/cache/redis_client.py - CacheClient class
- [ ] Create src/cache/cache_decorator.py - @cached decorator
- [ ] Apply cache decorator to src/api/routes.py
- [ ] Write unit tests in tests/test_cache.py
- [ ] Run performance benchmark (target: under 200ms)
```

### 4. Create Task File

`data/tasks/TASK-{YYYY-MMDD}-{NNN}.md`:
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
    tech_spec:
      status: "pending"
    code_work:
      status: "pending"
    final_report:
      status: "pending"
source:
  type: "slack_mention"
  channel_id: "C0123456789"
  thread_ts: "1706500000.000000"
  exploration_id: "EXP-2026-0129-001"
created_at: "2026-01-29T10:15:00"
updated_at: "2026-01-29T10:15:00"
trace:
  - ts: "2026-01-29T10:15:00"
    action: "created"
    details:
      from_exploration: "EXP-2026-0129-001"
      workflow_type: "full"
---

## TODO

- [ ] Install redis-py package
- [ ] Implement CacheClient class
- [ ] Implement @cached decorator
- [ ] Apply cache to API
- [ ] Write unit tests
- [ ] Run benchmark

## Context Summary

[Exploration results summary]

## Acceptance Criteria

- [ ] Response time < 200ms
- [ ] Cache hit rate > 80%
- [ ] All tests pass
```

### 5. Send Slack Approval Request

Load tools:
```
ToolSearch: "slack"
```

Send message:
```
mcp__slack__slack_send_message(
  channel_id: "{source_channel}",
  thread_ts: "{source_thread}",
  text: "*TODO List Review Request*\n\n*Task*: {title}\n*Type*: {workflow_type} Workflow\n\n*TODO Items*:\n1. {item1}\n2. {item2}\n...\n\nApprove: :+1:\nRequest changes: :-1: + comment\n\n_Task ID: {task_id}_"
)
```

### 6. Output Results

```markdown
## TODO Created

**Task ID**: TASK-2026-0129-001
**Title**: Implement API Response Caching
**Workflow**: Full (4 stages)

### TODO Items (6)
1. Install redis-py package
2. Implement CacheClient class
3. Implement @cached decorator
4. Apply cache to API
5. Write unit tests
6. Run benchmark

### Approval Request
- Sent: #engineering (thread: 1706500000)
- Status: Awaiting first approval

### Next Step
After approval: /write-spec TASK-2026-0129-001
```

## Auto Trigger

- When `/create-todo` skill is executed
- On user request after exploration completion
