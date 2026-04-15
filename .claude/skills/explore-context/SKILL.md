---
description: Agentically explore context based on Slack threads or keywords. Recursively find and analyze related conversations, previous decisions, and ongoing issues.
---

# /explore-context - Context Exploration

## Language

All output, Slack messages, and user-facing text from this skill MUST follow the language setting in `ultrawork.yaml` (`language.default`). Check the `## Language Configuration` section in CLAUDE.md for the current language. Technical terms, code, file paths, and commands remain in their original form.

Recursively explore Slack conversations to deeply understand the situation.

## Usage

```
/explore-context C0123456789-1706500000.000000
/explore-context "API authentication refactoring"
/explore-context --channel C0123456789 --keyword "performance improvement"
```

## Arguments

| Argument | Description | Example |
|----------|-------------|---------|
| Thread ID | `{channel_id}-{thread_ts}` format | `C0123456789-1706500000.000000` |
| Keyword | Search term in quotes | `"database migration"` |
| `--channel` | Limit to specific channel | `--channel C0123456789` |
| `--depth` | Exploration depth (default: 5) | `--depth 3` |

## Detailed Execution Steps

### Step 0: Load Slack Tools

```
ToolSearch: "slack"
```

**Fallback on connection failure:**
```
ToolSearch: "+slack-bot"
```

### Step 0.5: Search Existing Memory

Before starting exploration, search LTM for related past requests/work to avoid duplicate analysis and build on prior context.

```
/recall --what "relevant keywords from the trigger"
/recall --where "channel name or file path if known"
```

If related records are found, incorporate their context into the exploration (skip re-analyzing threads that were already explored).

### Step 1: Analyze Trigger

If thread ID is given:
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

Expected result:
```json
{
  "messages": [
    {
      "user": "U06CLS6E694",
      "text": "<@UBOT123> API response time is too slow. Please review implementing caching.",
      "ts": "1706500000.000000",
      "reply_count": 5
    },
    {
      "user": "U00ENGINEER1",
      "text": "We discussed Redis caching before, let me check the decisions from that time",
      "ts": "1706500100.000000"
    }
  ]
}
```

### Step 2: Extract Keywords

Extract key keywords from messages:
- `API response time`
- `caching`
- `Redis`
- Participants: `U06CLS6E694`, `U00ENGINEER1`

### Step 3: Search Related Conversations

Search with each keyword:
```
mcp__slack__slack_search_messages(
  query: "caching Redis",
  count: 20
)
```

**Fallback on failure (query channel history + filter):**
```
mcp__slack-bot-mcp__slack_get_channel_history(
  channel_id: "C0123456789",
  limit: 100
)
```
-> Filter results by keywords ("caching", "Redis")

Expected result:
```json
{
  "messages": {
    "matches": [
      {
        "channel": {"id": "C0123456789", "name": "engineering"},
        "ts": "1706400000.000000",
        "text": "Decided to use 5-minute TTL for Redis caching",
        "user": "U00TECH_LEAD"
      },
      {
        "channel": {"id": "C0987654321", "name": "architecture"},
        "ts": "1706300000.000000",
        "text": "Caching strategy discussion: Write-through vs Write-behind",
        "user": "U00ARCHITECT"
      }
    ]
  }
}
```

### Step 4: Detailed Analysis of Related Threads

Get details for threads with high relevance scores:
```
mcp__slack__slack_get_thread(
  channel_id: "C0987654321",
  thread_ts: "1706300000.000000"
)
```

**Fallback on failure:**
```
mcp__slack-bot-mcp__slack_get_thread_replies(
  channel_id: "C0987654321",
  thread_ts: "1706300000.000000"
)
```

### Step 5: Save Exploration Results

Create file `data/explorations/EXP-2026-0129-001.md`:

```yaml
---
exploration_id: "EXP-2026-0129-001"
trigger:
  type: "mention"
  channel_id: "C0123456789"
  message_ts: "1706500000.000000"
  user_id: "U06CLS6E694"
created_at: "2026-01-29T10:00:00"
completed_at: "2026-01-29T10:05:32"
status: "completed"
scope:
  channels_searched:
    - "C0123456789"  # engineering
    - "C0987654321"  # architecture
  threads_analyzed: 4
  messages_processed: 47
  max_depth_reached: 3
context_discovered:
  previous_discussions:
    - thread_id: "C0987654321-1706300000"
      channel_id: "C0987654321"
      summary: "Caching strategy discussion: Write-through vs Write-behind comparison, Write-through adopted"
      relevance_score: 0.92
      key_participants: ["U00ARCHITECT", "U00TECH_LEAD"]
      timestamp: "2026-01-27T14:00:00"
    - thread_id: "C0123456789-1706400000"
      channel_id: "C0123456789"
      summary: "Redis TTL set to 5 minutes, cache key naming convention agreed"
      relevance_score: 0.85
      key_participants: ["U00TECH_LEAD", "U00ENGINEER1"]
      timestamp: "2026-01-28T09:00:00"
  ongoing_issues:
    - description: "Current API response time averaging 800ms, approaching SLA violation"
      first_mentioned: "2026-01-25"
      status: "open"
      related_threads: ["C0123456789-1706200000"]
  key_decisions:
    - date: "2026-01-27"
      decision: "Write-through approach adopted for caching strategy"
      participants: ["U00ARCHITECT", "U00TECH_LEAD"]
      thread_id: "C0987654321-1706300000"
    - date: "2026-01-28"
      decision: "Redis TTL 5 minutes, cache key format: {service}:{resource}:{id}"
      participants: ["U00TECH_LEAD"]
      thread_id: "C0123456789-1706400000"
current_problem:
  summary: "Redis caching layer needed to improve API response time"
  severity: "high"
  affected_users: ["U06CLS6E694", "U00ENGINEER1", "U00PRODUCT"]
  related_threads:
    - "C0123456789-1706500000"
    - "C0123456789-1706200000"
  root_cause_hypothesis: "Latency from direct database queries, missing caching layer"
---

## Exploration Summary

Explored context for API response time improvement request. Caching strategy discussions already exist, with Write-through approach and Redis TTL of 5 minutes decided. Only implementation remains.

## Previous Context

### One Week Ago (2026-01-27)
Caching strategy discussion in #architecture channel:
- Write-through vs Write-behind comparison
- **Decision**: Write-through adopted (data consistency priority)
- Participants: @architect, @tech_lead

### Two Days Ago (2026-01-28)
Implementation details discussion in #engineering channel:
- **Decision**: Redis TTL 5 minutes
- **Decision**: Cache key format `{service}:{resource}:{id}`
- Participants: @tech_lead, @engineer1

## Situation Analysis

**Current Situation**:
- API response time averaging 800ms (target: under 200ms)
- High urgency due to approaching SLA violation
- Caching strategy already decided, only implementation needed

**Blockers**:
- None. Decision-making complete.

**Stakeholders**:
- @hm (requester)
- @tech_lead (decision maker)
- @engineer1 (previous discussion participant)

## Recommended Actions

1. **Implement Redis caching middleware** (effort: medium)
   - Add cache layer with write-through approach
   - Follow existing decisions

2. **Add cache invalidation logic** (effort: low)
   - Delete related cache on data changes
   - Apply 5-minute TTL

3. **Add monitoring dashboard** (effort: low)
   - Cache hit rate, response time metrics
   - Alert configuration
```

### Step 6: Save to Long-Term Memory

After exploration is complete and saved, you MUST save a RequestRecord to LTM using `/remember`.

RequestRecord fields to save:
- **who**: The user who made the request (from the trigger message)
- **where**: The Slack channel/thread where the request originated
- **what**: Concise summary of the exploration findings
- **why**: The original purpose/reason for the request
- **topics**: Key technical topics discovered during exploration
- **intents**: Recommended actions (from the exploration results)

```
/remember req --who "{requester_user_id}" --where "{channel_name}" \
  --what "{exploration_summary}" --topics "{topic1},{topic2}" \
  --why "{original_request_purpose}" \
  --intents "{action1};{action2};{action3}"
```

Example:
```
/remember req --who U06CLS6E694 --where eng-common \
  --what "API response time improvement: Redis caching strategy already decided, implementation needed" \
  --topics caching,redis,api-performance \
  --why "API response time approaching SLA violation" \
  --intents "Implement Redis caching middleware;Add cache invalidation;Add monitoring dashboard"
```

## Output Example

```
## Context Exploration Complete

**Exploration ID**: EXP-2026-0129-001
**Trigger**: C0123456789-1706500000 (mention)

### Exploration Scope
- Channels searched: 2 (engineering, architecture)
- Threads analyzed: 4
- Messages processed: 47
- Exploration depth: 3

### Discovered Context

**Previous Discussions** (2):
1. [C0987654321-1706300000] Caching strategy discussion (relevance: 92%)
2. [C0123456789-1706400000] Redis TTL decision (relevance: 85%)

**Key Decisions** (2):
1. 2026-01-27: Write-through approach adopted
2. 2026-01-28: TTL 5 minutes, key format decided

**Ongoing Issues** (1):
1. API response time SLA violation approaching

### Current Problem
Redis caching layer implementation needed (severity: HIGH)

### Recommended Actions
1. Implement Redis caching middleware (medium)
2. Add cache invalidation logic (low)
3. Add monitoring dashboard (low)

### Saved Files
- data/explorations/EXP-2026-0129-001.md

### Next Step
Create TODO: `/create-todo EXP-2026-0129-001`
```

## Exploration Stop Conditions

Exploration stops under these conditions:
- Relevance score drops below 0.3
- Maximum depth (default 5) reached
- No new information for 2 consecutive iterations
- Sufficient context collected (3+ related discussions)

## Relevance Score Calculation

| Factor | Points |
|--------|--------|
| Exact keyword match | +0.3 |
| Same participant | +0.2 |
| Within last 7 days | +0.2 |
| Same channel | +0.1 |
| 5+ replies | +0.1 |

## Fallback Strategy Summary

| Primary (mcp__slack__) | Fallback (mcp__slack-bot-mcp__) |
|------------------------|----------------------------------|
| `slack_get_thread` | `slack_get_thread_replies` |
| `slack_search_messages` | `slack_get_channel_history` + filtering |
| `slack_users_info` | `slack_get_user_profile` |
