---
description: Collect and summarize Slack channel history by quarter and store in memory.
---

# /sync-channel-history - Channel History Memory Sync

## Language

All output, Slack messages, and user-facing text from this skill MUST follow the language setting in `ultrawork.yaml` (`language.default`). Check the `## Language Configuration` section in CLAUDE.md for the current language. Technical terms, code, file paths, and commands remain in their original form.

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
