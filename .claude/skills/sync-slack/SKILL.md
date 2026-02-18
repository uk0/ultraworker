---
description: Sync Slack workspace channel and user information to local registry. Fetches channel list and user list, saving as YAML files in data/registry/.
---

# /sync-slack - Slack Registry Sync

## Language

All output, Slack messages, and user-facing text from this skill MUST follow the language setting in `ultrawork.yaml` (`language.default`). Check the `## Language Configuration` section in CLAUDE.md for the current language. Technical terms, code, file paths, and commands remain in their original form.

Sync Slack workspace channel and user information to local storage.

## Usage

```
/sync-slack
```

## What This Skill Does

1. **Verify Slack connection**: Validate token with `slack_health_check`
2. **Fetch channel list**: Multiple calls to get all channels (bypass API limits)
3. **Fetch user list**: Get all users with `slack_list_users`
4. **Exclude archived channels**: Filter out archived/archive patterns
5. **Preserve manual channels**: Keep channels missing from API
6. **Save local files**: Store as YAML in `data/registry/`

---

## Detailed Execution Steps

### Step 1: Load Slack Tools and Verify Connection

```
ToolSearch: "slack"
```

```
mcp__slack__slack_health_check()
```

Expected result:
```json
{
  "status": "OK",
  "user": "username",
  "team": "Team Name",
  "team_id": "T058B1MTT4Y"
}
```

**Fallback on connection failure:**
```
ToolSearch: "+slack-bot"
```
-> Load Slack Bot MCP tools as alternative

### Step 2: Sync Channel List (Multi-call Strategy)

**Important**: Slack API may miss some channels. Use this strategy to fetch as many as possible:

#### 2.1 Fetch Public Channels
```
mcp__slack__slack_list_conversations(types: "public_channel", limit: 200)
```

**Fallback on failure:**
```
mcp__slack-bot-mcp__slack_list_channels()
```

#### 2.2 Fetch Private Channels (Separate Call)
```
mcp__slack__slack_list_conversations(types: "private_channel", limit: 200)
```

**Fallback on failure:**
```
mcp__slack-bot-mcp__slack_list_channels()
```
-> Slack Bot MCP returns all channels the bot has joined

#### 2.3 Preserve Manually Added Channels from Existing Registry

Some channels may be accessible but not returned by API.
Preserve channels with `# manually added` or `API list missing` comments from existing `channels.yaml`.

Example:
```yaml
# Channel missing from API but accessible
C09L6ATFKA7:
  id: "C09L6ATFKA7"
  name: "project-alpha"
  type: "public"
  _manual: true  # Manually added marker
```

#### 2.4 Filter Archived Channels

Exclude channels matching these patterns:
- Channel name contains `archive`
- Channel name contains `archived`

### Step 3: Sync User List

```
mcp__slack__slack_list_users(limit: 200)
```

**Fallback on failure:**
```
mcp__slack-bot-mcp__slack_get_users()
```

### Step 4: Save Registry Files

**Channel Registry** - `data/registry/channels.yaml`:

```yaml
# Slack Channel Registry
# Updated: 2026-01-29T19:30:00
# Note: Excludes archived channels and DMs
# API limitation: Some channels may not appear in list but are accessible

updated_at: "2026-01-29T19:30:00"

channels:
  # === Manually Added Channels (API Missing) ===
  C09L6ATFKA7:
    id: "C09L6ATFKA7"
    name: "project-alpha"
    type: "public"
    purpose: "Alpha project discussions"
    is_monitored: true
    default_workflow: "full"
    _manual: true

  # === Engineering ===
  C057KN2911V:
    id: "C057KN2911V"
    name: "eng-common"
    type: "public"
    is_monitored: true
    default_workflow: "full"

  # === Product ===
  C05BUTMULMD:
    id: "C05BUTMULMD"
    name: "product-storm"
    type: "public"
    is_monitored: true
    default_workflow: "full"

# Excluded archived channels:
# - C06B3LHNMR7: archive-gke-deploy-pylon
# - C06K0MEV9HV: archived-deploy-stargate
```

**Required Fields**:
- `id`: Channel ID (11-character string starting with C)
- `name`: Channel name
- `type`: "public" or "private"
- `is_monitored`: Whether to monitor (boolean)
- `default_workflow`: "full" or "simple"

**Optional Fields**:
- `purpose`: Channel description
- `_manual`: true if manually added due to API omission

**User Registry** - `data/registry/users.yaml`:

```yaml
# Slack User Registry
# Updated: 2026-01-29T19:30:00

updated_at: "2026-01-29T19:30:00"

users:
  U06CLS6E694:
    id: "U06CLS6E694"
    name: "username"
    display_name: "Display Name"
    email: "user@example.com"
    role: "developer"
    team: "engineering"
    is_bot: false
    is_admin: false
    can_approve: true
    timezone: "America/New_York"
```

---

## Channel Category Classification Rules

Group channels by category for readability:

| Pattern | Category |
|---------|----------|
| `eng-*` | Engineering |
| `product-*` | Product |
| `business-*` | Business |
| `corp-*` | Corp |
| `project-*` | Project |
| `alarm-*` | Alarm |
| `status-*` | Status |
| `noti-*`, `qna` | Notification |
| `research-*` | Research |
| `collaboration-*` | Collaboration |
| `contact-*` | Contact |
| `deploy-*` | Deploy |
| `guest-*` | Guest |
| `storm-*` | Storm |
| `poc_*`, `*_demo` | POC |
| `random*`, `standup`, `meal`, `sig-*` | Social |
| `test-*`, `*_test_*` | Test |
| `fyi-*`, `announcement` | Announcement |

---

## Output Example

```
## Slack Sync Complete

**Workspace**: Team Name (T058B1MTT4Y)
**User**: username

### Channels
- API fetched: 100
- Manually added: 1 (project-alpha)
- Archived excluded: 2
- **Total channels**: 99

**By Category**:
- Engineering: 7
- Product: 6
- Project: 10
- Alarm: 3 (monitoring)
- ...

**Monitoring enabled**: 8
- project-alpha, eng-common, product-storm, qna, noti-spec-review, alarm-* (3)

### Users
- Total users: 63
  - Active: 58
  - Bots: 5
- Approvers: 12

### Saved Files
- data/registry/channels.yaml
- data/registry/users.yaml
```

---

## Manually Adding Channels Missing from API

If a channel is accessible but not returned by API:

1. Get channel ID (Slack -> channel info -> copy channel ID)
2. Test access with channel history:
   ```
   mcp__slack__slack_conversations_history(channel_id: "C09L6ATFKA7", limit: 1)
   ```
   **Fallback on failure:**
   ```
   mcp__slack-bot-mcp__slack_get_channel_history(channel_id: "C09L6ATFKA7", limit: 1)
   ```
3. If successful, manually add to `channels.yaml` (with `_manual: true`)

---

## Preserving Existing Settings

Existing settings are preserved during sync:
- `is_monitored`: Channel monitoring status
- `can_approve`: User approval permission
- `role`: User role
- `team`: Team affiliation
- `_manual`: Manual addition marker

---

## Troubleshooting

### Channel Not Appearing in List

1. **Test direct access by channel ID**:
   ```
   mcp__slack__slack_conversations_history(channel_id: "CHANNEL_ID", limit: 1)
   ```
   **Fallback on failure:**
   ```
   mcp__slack-bot-mcp__slack_get_channel_history(channel_id: "CHANNEL_ID", limit: 1)
   ```

2. **If access succeeds**: Manually add with `_manual: true`
3. **If access fails**: Not a member of that channel

### Token Expired

```
mcp__slack__slack_refresh_tokens()
```

Chrome must have Slack open.

### Complete Slack MCP Failure

```
Slack MCP unavailable - switching to Slack Bot MCP

ToolSearch: "+slack-bot"

Using alternative tools:
- slack_list_channels (channel list)
- slack_get_users (user list)
- slack_get_channel_history (channel history)
```

---

## Follow-up Tasks

Configure channel monitoring after sync:
```yaml
# Edit directly in channels.yaml
C057KN2911V:
  is_monitored: true  # Enable monitoring
```

Set approval permissions:
```yaml
# Edit directly in users.yaml
U06CLS6E694:
  can_approve: true  # Grant approval permission
```
