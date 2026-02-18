---
description: Create, list, pause, resume, or delete cron jobs for scheduled task monitoring. Ultraworker can create cronjobs autonomously via this skill.
---

# /manage-cronjob - Cron Job Management

Manage scheduled cron jobs that periodically monitor threads, check reactions, scan mentions, and notify via DM.

## Usage

```
/manage-cronjob create "Job Name" --schedule weekday --at 09:00 --action check_thread_reactions
/manage-cronjob list
/manage-cronjob pause CRON-2026-0219-001
/manage-cronjob resume CRON-2026-0219-001
/manage-cronjob delete CRON-2026-0219-001
```

## Supported Actions

| Action | Description |
|--------|-------------|
| `check_thread_reactions` | Check threads for new reactions/replies |
| `monitor_thread_updates` | Monitor threads for updates and pending actions |
| `scan_mentions` | Scan channels for unhandled mentions |
| `dm_pending_tasks` | Send DM summary of pending approvals |
| `custom` | Execute a custom Claude prompt on schedule |

## Supported Schedules

| Type | Example | Description |
|------|---------|-------------|
| `interval` | Every 2 hours | `--schedule interval --hours 2` |
| `daily` | Daily at 9 AM | `--schedule daily --at 09:00` |
| `weekday` | Weekdays at 9 AM | `--schedule weekday --at 09:00` |
| `weekly` | Every Monday at 9 AM | `--schedule weekly --day monday --at 09:00` |
| `cron` | Custom cron expr | `--schedule cron --expression "0 9 * * 1-5"` |

---

## Execution Steps

### Creating a Cron Job

#### Step 1: Determine Parameters

From the user request, extract:
- **Name**: Human-readable job name
- **Schedule**: When to run (type, time, day)
- **Action**: What to do
- **Targets**: Which threads/channels to monitor
- **Notification**: Who to DM with results

#### Step 2: Create via CLI or Python

CLI:
```bash
ultrawork cron:create "Morning Thread Check" \
  --schedule weekday --at 09:00 \
  --action check_thread_reactions \
  --notify-user U06CLS6E694 \
  --notify-channel D06CVUV964C
```

Python (for skill/autonomous creation):
```python
from ultrawork.scheduler import CronJobManager
from ultrawork.models.cronjob import CronSchedule, CronScheduleType, CronJobAction, ThreadTarget
from ultrawork.config import get_config

config = get_config()
manager = CronJobManager(config.data_dir)

schedule = CronSchedule(type=CronScheduleType.WEEKDAY, at="09:00")

job = manager.create_job(
    name="Morning Thread Check",
    schedule=schedule,
    action=CronJobAction.CHECK_THREAD_REACTIONS,
    thread_targets=[
        ThreadTarget(
            channel_id="C0123456789",
            thread_ts="1706500000.000000",
            channel_name="eng-common",
            description="Feature request discussion",
        ),
    ],
    notify_user_id="U06CLS6E694",
    notify_channel_id="D06CVUV964C",
    require_approval=True,
    created_by="skill",
)
```

#### Step 3: Confirm Creation

```
Created cron job: CRON-2026-0219-001
- Name: Morning Thread Check
- Schedule: Weekdays at 09:00
- Action: Check thread reactions
- Notifications: DM to user
```

### Self-Creation by Ultraworker

When processing a task that needs follow-up monitoring:

```python
job = manager.create_job(
    name=f"Follow-up: {task_summary[:50]}",
    description=f"Monitor thread for approval/feedback",
    schedule=CronSchedule(type=CronScheduleType.INTERVAL, hours=1),
    action=CronJobAction.CHECK_THREAD_REACTIONS,
    thread_targets=[ThreadTarget(
        channel_id=channel_id,
        thread_ts=thread_ts,
        description=f"Task approval monitoring",
    )],
    notify_user_id=user_id,
    notify_channel_id=dm_channel_id,
    require_approval=True,
    created_by="skill",
    source_session_id=session_id,
)
```

---

## DM Notification Flow

1. Cron job checks threads/channels for activity
2. Formats findings into a summary DM
3. Sends DM to configured user
4. User can reply to approve/process or ignore

### Example DM

```
*Morning Thread Check* - Thread Update Summary

*#eng-common* - Feature request discussion
  New replies: 3
  > @user1: I think we should go with option A
  > @user2: Agreed, let's proceed
  Reactions: :thumbsup: :white_check_mark:

Reply with the thread link to process, or ignore to skip.
```

---

## CLI Commands

| Command | Description |
|---------|-------------|
| `ultrawork cron:list` | List all cron jobs |
| `ultrawork cron:show <id>` | Show job details |
| `ultrawork cron:create` | Create a new job |
| `ultrawork cron:pause <id>` | Pause a job |
| `ultrawork cron:resume <id>` | Resume a paused job |
| `ultrawork cron:delete <id>` | Delete a job |
| `ultrawork cron:run <id>` | Manually trigger a job |
| `ultrawork cron:logs <id>` | View execution logs |
