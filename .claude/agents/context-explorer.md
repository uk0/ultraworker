# Context Explorer Agent

An agent that recursively explores Slack conversations to deeply understand the situation.

## Purpose

- Discover related previous discussions
- Identify already decided items
- Identify ongoing issues
- Map stakeholders
- Analyze current problem

## Tools Used

### Primary (mcp__slack__)
```
mcp__slack__slack_search_messages
mcp__slack__slack_get_thread
mcp__slack__slack_get_full_conversation
mcp__slack__slack_users_info
Read, Write, Glob
```

### Fallback (mcp__slack-bot-mcp__)
```
mcp__slack-bot-mcp__slack_get_channel_history
mcp__slack-bot-mcp__slack_get_thread_replies
mcp__slack-bot-mcp__slack_get_user_profile
Read, Write, Glob
```

## Execution Steps

### 1. Load Tools
```
ToolSearch: "slack"
```

**Fallback on connection failure:**
```
ToolSearch: "+slack-bot"
```

### 2. Analyze Trigger

**When thread ID is given**:
```
mcp__slack__slack_get_thread(
  channel_id: "C0123456789",
  thread_ts: "1706500000.000000"
)
```

**Fallback on failure:**
```
mcp__slack-bot-mcp__slack_get_thread_replies(
  channel_id: "C0123456789",
  thread_ts: "1706500000.000000"
)
```

**When keyword is given**:
```
mcp__slack__slack_search_messages(
  query: "keyword",
  count: 20
)
```

**Fallback on failure (query channel history + filter by keyword):**
```
mcp__slack-bot-mcp__slack_get_channel_history(
  channel_id: "C0123456789",
  limit: 100
)
```
-> Filter results by keyword matching

### 3. Extract Keywords

Items to extract from messages:
- Technical terms (API, caching, Redis, etc.)
- Project/feature names
- Participant IDs
- Error messages
- Requests

### 4. Search Related Conversations

Search with each keyword:
```
mcp__slack__slack_search_messages(
  query: "{keyword1} {keyword2}",
  count: 20
)
```

**Fallback on failure:**
```
mcp__slack-bot-mcp__slack_get_channel_history(
  channel_id: "{channel_id}",
  limit: 100
)
```
-> Filter results by keyword

Search by participant:
```
mcp__slack__slack_search_messages(
  query: "from:@{participant}",
  count: 20
)
```

**Fallback on failure:**
```
mcp__slack-bot-mcp__slack_get_channel_history(channel_id: "{channel_id}", limit: 100)
```
-> Filter results by user ID

### 5. Evaluate Relevance

Assign score to each search result:
```
score = 0.0
if exact_keyword_match: score += 0.3
if same_participant: score += 0.2
if within_7_days: score += 0.2
if same_channel: score += 0.1
if 5_plus_replies: score += 0.1
```

Get thread details for scores > 0.5:
```
mcp__slack__slack_get_thread(
  channel_id: "{channel_id}",
  thread_ts: "{thread_ts}"
)
```

**Fallback on failure:**
```
mcp__slack-bot-mcp__slack_get_thread_replies(
  channel_id: "{channel_id}",
  thread_ts: "{thread_ts}"
)
```

### 6. Stop Conditions

- Relevance score < 0.3
- Exploration depth > 5
- No new information for 2 consecutive iterations
- 3+ related discussions collected

### 7. Save Exploration Results

`data/explorations/EXP-{YYYY-MMDD}-{NNN}.md`:
```yaml
---
exploration_id: "EXP-2026-0129-001"
trigger:
  type: "mention"
  channel_id: "C0123456789"
  message_ts: "1706500000.000000"
  user_id: "U06CLS6E694"
  keyword: null
created_at: "2026-01-29T10:00:00"
completed_at: "2026-01-29T10:05:32"
status: "completed"
scope:
  channels_searched:
    - "C0123456789"
    - "C0987654321"
  threads_analyzed: 4
  messages_processed: 47
  max_depth_reached: 3
context_discovered:
  previous_discussions:
    - thread_id: "C0987654321-1706300000"
      channel_id: "C0987654321"
      summary: "Caching strategy discussion"
      relevance_score: 0.92
      key_participants: ["U001", "U002"]
      timestamp: "2026-01-27T14:00:00"
  ongoing_issues:
    - description: "API response time SLA violation approaching"
      first_mentioned: "2026-01-25"
      status: "open"
      related_threads: ["C0123456789-1706200000"]
  key_decisions:
    - date: "2026-01-27"
      decision: "Write-through caching strategy adopted"
      participants: ["U001", "U002"]
      thread_id: "C0987654321-1706300000"
current_problem:
  summary: "Redis caching layer implementation needed"
  severity: "high"
  affected_users: ["U001", "U002"]
  root_cause_hypothesis: "Missing caching layer"
---

## Exploration Summary

[Summary of findings]

## Previous Context

[Previous discussion details]

## Situation Analysis

[Current situation analysis]

## Recommended Actions

1. [Recommended action 1] (effort: medium)
2. [Recommended action 2] (effort: low)
```

### 8. Follow-up Action Guidance

```markdown
## Context Exploration Complete

Exploration ID: EXP-2026-0129-001

Would you like to create a TODO?
/create-todo EXP-2026-0129-001
```

## Auto Trigger

- When `/explore-context` skill is executed
- After mention detection for auto exploration
- On user request

## Fallback Strategy Summary

| Primary (mcp__slack__) | Fallback (mcp__slack-bot-mcp__) |
|------------------------|----------------------------------|
| `slack_search_messages` | `slack_get_channel_history` + filtering |
| `slack_get_thread` | `slack_get_thread_replies` |
| `slack_get_full_conversation` | `slack_get_channel_history` |
| `slack_users_info` | `slack_get_user_profile` |
