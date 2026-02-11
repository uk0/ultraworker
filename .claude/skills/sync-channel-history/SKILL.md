---
description: Collect and summarize Slack channel history by quarter and store in memory.
---

# /sync-channel-history - Channel History Memory Sync

Collect conversation history from key Slack channels and save quarterly summaries.

## Usage

```
/sync-channel-history [channel_name] [options]
```

## What This Skill Does

1. Fetch channel history
2. Analyze threads
3. Extract topics and terminology
4. Save quarterly summaries

## Storage Location

`data/memory/channel_history/{channel}/{year}-Q{quarter}.yaml`
