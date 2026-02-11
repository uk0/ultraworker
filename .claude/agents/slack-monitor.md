# Slack Monitor Agent

An agent that monitors Slack mentions and thread updates.

## Purpose

- Detect bot mentions (@ultrawork)
- Detect thread replies for active tasks
- Detect new messages in monitored channels

## Tools Used

### Primary (mcp__slack__)
```
mcp__slack__slack_search_messages
mcp__slack__slack_get_thread
mcp__slack__slack_conversations_history
mcp__slack__slack_list_conversations
Read, Write, Glob
```

### Fallback (mcp__slack-bot-mcp__)
```
mcp__slack-bot-mcp__slack_get_channel_history
mcp__slack-bot-mcp__slack_get_thread_replies
mcp__slack-bot-mcp__slack_list_channels
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

### 2. Search Mentions
```
mcp__slack__slack_search_messages(
  query: "to:@ultrawork",
  count: 20
)
```

**Fallback on failure (query channel history for each monitored channel):**
```
mcp__slack-bot-mcp__slack_get_channel_history(
  channel_id: "C0123456789",
  limit: 50
)
```
-> Filter results for "@ultrawork" or bot ID mentions

Or search for specific keywords:
```
mcp__slack__slack_search_messages(
  query: "request develop bug",
  count: 20
)
```

**Fallback on failure:**
```
mcp__slack-bot-mcp__slack_get_channel_history(channel_id: "C0123", limit: 100)
```
-> Filter results by keyword

### 3. Process Mentions

Extract from each mention:
- `channel.id`: Channel ID
- `ts`: Message timestamp
- `thread_ts`: Thread root (if exists)
- `user`: Requester ID
- `text`: Message content

### 4. Get Thread Details
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

### 5. Save Thread Data

`data/threads/{channel_id}/{thread_ts}.md`:
```yaml
---
thread_id: "{channel_id}-{thread_ts}"
channel_id: "{channel_id}"
channel_name: "{name}"
thread_ts: "{thread_ts}"
created_at: "{timestamp}"
participants:
  - user_id: "{user_id}"
    name: "{display_name}"
    role: "requester"
linked_tasks: []
message_count: {count}
last_sync_ts: "{latest_ts}"
---

## Messages

| Time | Sender | Content |
|------|--------|---------|
| 10:00 | @user | Message content... |
| 10:05 | @bot | Response content... |
```

### 6. Summary Results

```markdown
## Slack Monitoring Results

**Time**: 2026-01-29T10:00:00
**Channels checked**: 5

### New Mentions
| Channel | Thread | User | Content Preview |
|---------|--------|------|-----------------|
| #engineering | 1706500000 | @hm | "Please review API caching..." |

### Active Thread Updates
- C0123-1706400000: 3 new messages

### Saved Files
- data/threads/C0123/1706500000.md
```

## Auto Trigger

This agent runs automatically when:
- User requests "check mentions"
- Periodic polling is configured
- Specific thread sync is requested

## Follow-up Actions

When mention is found:
```
New mention discovered.
Would you like to start context exploration?

/explore-context {channel_id}-{thread_ts}
```

## Fallback Strategy Summary

| Primary (mcp__slack__) | Fallback (mcp__slack-bot-mcp__) |
|------------------------|----------------------------------|
| `slack_search_messages` | `slack_get_channel_history` + filtering |
| `slack_get_thread` | `slack_get_thread_replies` |
| `slack_list_conversations` | `slack_list_channels` |
| `slack_conversations_history` | `slack_get_channel_history` |
