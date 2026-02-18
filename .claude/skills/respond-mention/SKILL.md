---
description: Respond to Slack mentions by performing deep context search. Triggers workflows for complex tasks.
---

# /respond-mention - Slack Mention Response

Detect Slack mentions, perform deep context search, and **always** respond.

## Important: Message Sending Required

**This skill must always send a Slack message.**
- Send a response whether or not context is found
- Send an error message even if an error occurs
- Never terminate without sending a message

## Usage

```bash
/respond-mention data/mentions/pending/{timestamp}.yaml
```

## Arguments

- `mention_file`: Path to YAML file containing mention information

## Mention File Format

```yaml
channel_id: "D06CVUV964C"
message_ts: "1234567890.123456"
thread_ts: "1234567890.123456"
text: "<@U06CLS6E694> question content"
user: "U0123456789"
created_at: "2026-01-29T10:00:00"
complexity: "simple" | "complex"
```

## Message Classification

### Ignore (No Response Needed) - Check First
If these conditions apply, **exit silently without responding**:

1. **Tag only**: No meaningful text besides the mention
   - `<@U06CLS6E694>` (mention only)
   - `<@U06CLS6E694> ` (mention + whitespace only)

2. **Greeting only**: Mention + simple greeting only
   - `<@U06CLS6E694> hi`
   - `<@U06CLS6E694> hello`
   - `<@U06CLS6E694> hey`

3. **Meaningless text**: Mention + meaningless characters only
   - `<@U06CLS6E694> ...`
   - `<@U06CLS6E694> lol`

**Criteria**: After removing the mention, remaining text:
- Is empty or whitespace only
- Is 2 characters or less of simple greeting/interjection
- Is not a meaningful question/request/command

**Exceptions**: Must respond to:
- `<@U06CLS6E694> what are you doing?` -> Question, respond
- `<@U06CLS6E694> help me` -> Request, respond
- `<@U06CLS6E694> there's a bug` -> Report, respond

### Simple (Direct Response)
- Can answer question directly
- Only needs information lookup
- Simple request

### Complex (Workflow Needed)
Start workflow if these keywords are present:
- Development: implement, create, build, modify, refactor
- Analysis: analyze, investigate, review
- Planning: design, architecture, spec, plan
- Issues: bug, error, problem, issue, outage

**For Complex cases, start this workflow:**
```
1. Send initial response (work started notification)
2. Run /explore-context (context exploration)
3. Run /create-todo (TODO creation + approval request)
4. Wait for user approval
5. Run /write-spec (tech spec writing)
6. Wait for user approval
7. Implement code
8. Run /report (final report)
```

## Common Execution Steps

### Step 0: Simple Tag Check (Check First)
1. Remove `<@U...>` pattern from mention text
2. Normalize remaining text (trim whitespace, lowercase)
3. Check conditions:
   - Text is empty -> **Ignore**
   - Text is 2 chars or less + greeting/interjection -> **Ignore**
   - Otherwise -> Continue

**Output when ignoring:**
```yaml
result:
  status: "ignored"
  reason: "simple_tag"
  original_text: "<@U06CLS6E694>"
  response_sent: false
```

## Execution Steps (Simple)

### Step 1: Read Mention File
Use Read tool to read mention file and understand the information.

### Step 2: Load Slack Tools
```
ToolSearch: "slack"
```
Load all Slack MCP tools.

**Fallback on connection failure:**
```
ToolSearch: "+slack-bot"
```

### Step 3: Get Full Thread
```
mcp__slack__slack_get_thread(channel_id, thread_ts)
```

**Fallback on failure:**
```
mcp__slack-bot-mcp__slack_get_thread_replies(channel_id, thread_ts)
```

- All messages in thread
- Identify participants
- Previous discussion context

### Step 3.5: Process Thread Attachments (if any)

If the thread contains files or images, they are automatically downloaded by the SDK poller
and included in the prompt as `## Thread Attachments`. The following file types are supported:

| Category | File Types | Processing |
|----------|-----------|------------|
| Images | PNG, JPG, GIF, WEBP | Downloaded to local path, use Read tool to view |
| PDFs | PDF | Downloaded to local path, use Read tool to view |
| Text | CSV, TXT, JSON, YAML, MD, code files | Content included inline in prompt |
| Archives | ZIP | Extracted, each file processed individually |
| Binary | Other | Metadata only (file name, size, type) |

**When thread attachments are present:**
- Text file contents are already included inline in the prompt
- For images: Use `Read` tool with the provided local path to view
- For PDFs: Use `Read` tool with the provided local path to read
- Reference files in your response when relevant to the user's question

### Step 4: Get Channel History
```
mcp__slack__slack_conversations_history(channel_id, limit: 50)
```

**Fallback on failure:**
```
mcp__slack-bot-mcp__slack_get_channel_history(channel_id, limit: 50)
```

- Last 50 messages
- Understand previous conversation patterns

### Step 5: Keyword-based Search (Optional)
If meaningful keywords exist, search:
```
mcp__slack__slack_search_messages(query: "keyword", count: 20)
```

**Fallback on failure:**
```
mcp__slack-bot-mcp__slack_get_channel_history(channel_id: "related_channel", limit: 100)
```
-> Filter results by keyword

### Step 6: Generate and Send Response (Required)
```
mcp__slack__slack_send_message(
  channel_id: {channel_id},
  text: {response},
  thread_ts: {thread_ts}
)
```

**Fallback on failure:**
```
mcp__slack-bot-mcp__slack_post_message(
  channel_id: {channel_id},
  text: {response}
)
```

Or:
```
mcp__slack-bot-mcp__slack_reply_to_thread(
  channel_id: {channel_id},
  thread_ts: {thread_ts},
  text: {response}
)
```

## Execution Steps (Complex - Workflow)

### Step 1: Send Initial Response (Required)
```
mcp__slack__slack_send_message(
  channel_id: {channel_id},
  text: "Request received! \n\nThis looks like a complex task, so I'll proceed step by step:\n1. Analyzing context...\n2. Will create TODO\n3. Will proceed after approval\n\nI'll share detailed analysis results shortly.",
  thread_ts: {thread_ts}
)
```

**Fallback on failure:**
```
mcp__slack-bot-mcp__slack_reply_to_thread(
  channel_id: {channel_id},
  thread_ts: {thread_ts},
  text: "Request received!..."
)
```

### Step 2: Context Exploration
```
Skill: explore-context
Args: {channel_id}-{thread_ts}
```

### Step 3: Create TODO
Create TODO with exploration result ID (EXP-YYYY-MMDD-NNN):
```
Skill: create-todo
Args: EXP-YYYY-MMDD-NNN
```

### Step 4: Send Completion Notification (Required)
```
mcp__slack__slack_send_message(
  channel_id: {channel_id},
  text: "Analysis complete!\n\nPlease review the TODO list in the thread above and approve.\nApprove: :+1: reaction\nRequest changes: :-1: reaction + comment",
  thread_ts: {thread_ts}
)
```

**Fallback on failure:**
```
mcp__slack-bot-mcp__slack_reply_to_thread(
  channel_id: {channel_id},
  thread_ts: {thread_ts},
  text: "Analysis complete!..."
)
```

## Response Generation Rules

1. **Context-based answers**: Answer questions based on collected Slack context
2. **Honesty**: If no relevant information found, say "I couldn't find related information. Please provide more details!"
3. **Friendly**: Respond in a friendly manner
4. **Appropriate emoji**: Use emoji appropriately (not excessively)

## Response Sending - Never Skip

```
mcp__slack__slack_send_message(
  channel_id: {channel_id},
  text: {response},
  thread_ts: {thread_ts}
)
```

**Always** include thread_ts to reply in the thread.

**Always use fallback on send failure:**
```
mcp__slack-bot-mcp__slack_reply_to_thread(
  channel_id: {channel_id},
  thread_ts: {thread_ts},
  text: {response}
)
```

Or:
```
mcp__slack-bot-mcp__slack_post_message(
  channel_id: {channel_id},
  text: {response}
)
```

## Output Format

Output results in this format after completion:

```yaml
result:
  status: "success" | "error"
  context_summary:
    thread_messages: N
    channel_messages: N
    keyword_matches: N
  response_sent: true  # Must be true
  response_text: "Response content sent"
  workflow_triggered: false | true
  error_message: "Error message if error"
```

## Example Workflow (Simple)

```
1. Read: data/mentions/pending/1234567890_123456.yaml
   -> channel_id: D06CVUV964C, text: "<@U06CLS6E694> where did we order that stew from?"

2. ToolSearch: "slack"
   -> Slack tools loaded
   -> On failure: ToolSearch: "+slack-bot"

3. mcp__slack__slack_get_thread(channel_id: "D06CVUV964C", thread_ts: "1234567890.123456")
   -> On failure: mcp__slack-bot-mcp__slack_get_thread_replies(...)
   -> Collect thread context

4. mcp__slack__slack_conversations_history(channel_id: "D06CVUV964C", limit: 30)
   -> On failure: mcp__slack-bot-mcp__slack_get_channel_history(...)
   -> Collect DM history

5. Analyze context and generate response

6. mcp__slack__slack_send_message(
     channel_id: "D06CVUV964C",
     text: "We ordered from 'Seoul Kitchen' last Tuesday!",
     thread_ts: "1234567890.123456"
   )
   -> On failure: mcp__slack-bot-mcp__slack_reply_to_thread(...)
   -> Response sent (required)
```

## Example Workflow (Complex)

```
1. Read: data/mentions/pending/1234567890_123456.yaml
   -> channel_id: C0123456789, text: "<@U06CLS6E694> improve API response time"

2. ToolSearch: "slack"
   -> Slack tools loaded
   -> On failure: ToolSearch: "+slack-bot"

3. mcp__slack__slack_send_message(
     channel_id: "C0123456789",
     text: "Request received!...",
     thread_ts: "1234567890.123456"
   )
   -> On failure: mcp__slack-bot-mcp__slack_reply_to_thread(...)
   -> Initial response sent (required)

4. Skill: explore-context
   Args: C0123456789-1234567890.123456
   -> Context exploration, EXP-2026-0130-001 created

5. Skill: create-todo
   Args: EXP-2026-0130-001
   -> TODO created, TASK-2026-0130-001 created, Slack approval request sent

6. mcp__slack__slack_send_message(
     channel_id: "C0123456789",
     text: "Analysis complete!...",
     thread_ts: "1234567890.123456"
   )
   -> On failure: mcp__slack-bot-mcp__slack_reply_to_thread(...)
   -> Completion notification sent (required)
```

## Notes

- Do not include sensitive information (personal data, passwords, etc.) in responses
- Clearly indicate if information is uncertain
- **Always send a response** even if no context is found
- **Send an error notification message** even if an error occurs

## Fallback Strategy Summary

| Primary (mcp__slack__) | Fallback (mcp__slack-bot-mcp__) |
|------------------------|----------------------------------|
| `slack_get_thread` | `slack_get_thread_replies` |
| `slack_conversations_history` | `slack_get_channel_history` |
| `slack_search_messages` | `slack_get_channel_history` + filtering |
| `slack_send_message` | `slack_post_message` or `slack_reply_to_thread` |
| `slack_users_info` | `slack_get_user_profile` |
