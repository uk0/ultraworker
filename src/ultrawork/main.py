"""CLI entrypoint for Ultrawork."""

from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

from ultrawork.config import UltraworkConfig, get_config, set_config
from ultrawork.context import ContextIndexer, ContextManager
from ultrawork.models import TaskSource, WorkflowStage, WorkflowType

app = typer.Typer(
    name="ultrawork",
    help="Automated task management and approval system with Slack MCP integration.",
)
console = Console()


@app.callback()
def main(
    data_dir: Optional[Path] = typer.Option(  # noqa: UP007
        None, "--data-dir", "-d", help="Data directory path"
    ),
) -> None:
    """Initialize Ultrawork with optional configuration."""
    config = get_config()
    if data_dir:
        config.data_dir = data_dir
        set_config(config)


# --- Task Commands ---


@app.command("task:list")
def task_list(
    active_only: bool = typer.Option(True, "--active/--all", help="Show only active tasks"),
    stage: Optional[str] = typer.Option(None, "--stage", "-s", help="Filter by stage"),  # noqa: UP007
) -> None:
    """List tasks."""
    config = get_config()
    manager = ContextManager(config.data_dir)

    stage_filter = WorkflowStage(stage) if stage else None
    tasks = manager.list_tasks(stage=stage_filter, active_only=active_only)

    table = Table(title="Tasks")
    table.add_column("ID", style="cyan")
    table.add_column("Title", style="white")
    table.add_column("Stage", style="yellow")
    table.add_column("Type", style="green")
    table.add_column("Updated", style="dim")

    for task in tasks:
        table.add_row(
            task.task_id,
            task.title[:40] + "..." if len(task.title) > 40 else task.title,
            task.workflow.current_stage.value,
            task.workflow.type.value,
            task.updated_at.strftime("%Y-%m-%d %H:%M"),
        )

    console.print(table)


@app.command("task:create")
def task_create(
    title: str = typer.Argument(..., help="Task title"),
    simple: bool = typer.Option(False, "--simple", help="Use simple workflow (no code)"),
) -> None:
    """Create a new task manually."""
    config = get_config()
    manager = ContextManager(config.data_dir)

    source = TaskSource(type="manual")
    task = manager.create_task_record(title=title, source=source)

    if simple:
        task.workflow.type = WorkflowType.SIMPLE
        manager.update_task_record(task)

    console.print(f"[green]Created task:[/green] {task.task_id}")
    console.print(f"[dim]File:[/dim] {task.get_file_path(str(config.data_dir / 'tasks'))}")


@app.command("task:show")
def task_show(
    task_id: str = typer.Argument(..., help="Task ID"),
) -> None:
    """Show task details."""
    config = get_config()
    manager = ContextManager(config.data_dir)

    task = manager.get_task_record(task_id)
    if not task:
        console.print(f"[red]Task not found:[/red] {task_id}")
        raise typer.Exit(1)

    console.print(f"\n[bold cyan]{task.task_id}[/bold cyan] - {task.title}")
    console.print(f"[dim]Stage:[/dim] {task.workflow.current_stage.value}")
    console.print(f"[dim]Type:[/dim] {task.workflow.type.value}")
    console.print(f"[dim]Source:[/dim] {task.source.type}")

    if task.source.thread_id:
        console.print(f"[dim]Thread:[/dim] {task.source.thread_id}")

    console.print("\n[bold]Stages:[/bold]")
    for name, stage in task.workflow.stages.items():
        status_color = {
            "pending": "yellow",
            "in_progress": "blue",
            "approved": "green",
            "rejected": "red",
            "skipped": "dim",
        }.get(stage.status.value, "white")
        console.print(f"  {name}: [{status_color}]{stage.status.value}[/{status_color}]")

    if task.todo_items:
        console.print("\n[bold]TODO:[/bold]")
        for item in task.todo_items:
            console.print(f"  - {item}")

    if task.trace:
        console.print("\n[bold]Recent Trace:[/bold]")
        for entry in task.trace[-5:]:
            console.print(f"  [{entry.ts.strftime('%H:%M')}] {entry.action}")


# --- Index Commands ---


@app.command("index:rebuild")
def index_rebuild() -> None:
    """Rebuild all indexes."""
    config = get_config()
    indexer = ContextIndexer(config.data_dir)
    indexer.rebuild_indexes()
    console.print("[green]Indexes rebuilt successfully.[/green]")


@app.command("index:pending")
def index_pending() -> None:
    """Show tasks pending approval."""
    config = get_config()
    indexer = ContextIndexer(config.data_dir)

    pending = indexer.get_pending_approvals()

    if not pending:
        console.print("[dim]No pending approvals.[/dim]")
        return

    table = Table(title="Pending Approvals")
    table.add_column("Task ID", style="cyan")
    table.add_column("Title", style="white")
    table.add_column("Stage", style="yellow")

    for p in pending:
        table.add_row(p["task_id"], p["title"], p["stage"])

    console.print(table)


# --- Slack Commands ---


@app.command("slack:status")
def slack_status() -> None:
    """Show Slack registry status."""
    from ultrawork.slack import SlackRegistry

    config = get_config()
    registry = SlackRegistry(config.data_dir)

    channels = registry.get_channels()
    users = registry.get_users()

    console.print("\n[bold]Slack Registry Status[/bold]")
    console.print(f"  Channels: {len(channels.channels)}")
    console.print(f"  Monitored: {len(channels.get_monitored_channels())}")
    console.print(f"  Users: {len(users.users)}")
    console.print(f"  Approvers: {len(users.get_approvers())}")

    if channels.channels:
        console.print(
            f"\n  [dim]Last channel sync: {channels.updated_at.strftime('%Y-%m-%d %H:%M')}[/dim]"
        )
    if users.users:
        console.print(f"  [dim]Last user sync: {users.updated_at.strftime('%Y-%m-%d %H:%M')}[/dim]")


@app.command("slack:channels")
def slack_channels(
    monitored_only: bool = typer.Option(
        False, "--monitored", "-m", help="Show only monitored channels"
    ),
) -> None:
    """List Slack channels."""
    from ultrawork.slack import SlackRegistry

    config = get_config()
    registry = SlackRegistry(config.data_dir)

    channels = registry.get_channels()
    channel_list = (
        channels.get_monitored_channels() if monitored_only else list(channels.channels.values())
    )

    if not channel_list:
        console.print("[dim]No channels found. Run slack:sync to fetch from Slack.[/dim]")
        return

    table = Table(title="Slack Channels")
    table.add_column("ID", style="dim")
    table.add_column("Name", style="cyan")
    table.add_column("Type", style="white")
    table.add_column("Monitored", style="green")
    table.add_column("Members", style="dim")

    for ch in channel_list:
        monitored = "[green]Yes[/green]" if ch.is_monitored else "[dim]No[/dim]"
        table.add_row(ch.channel_id, ch.name, ch.type.value, monitored, str(ch.member_count))

    console.print(table)


@app.command("slack:users")
def slack_users(
    approvers_only: bool = typer.Option(False, "--approvers", "-a", help="Show only approvers"),
) -> None:
    """List Slack users."""
    from ultrawork.slack import SlackRegistry

    config = get_config()
    registry = SlackRegistry(config.data_dir)

    users = registry.get_users()
    user_list = users.get_approvers() if approvers_only else list(users.users.values())

    if not user_list:
        console.print("[dim]No users found. Run slack:sync to fetch from Slack.[/dim]")
        return

    table = Table(title="Slack Users")
    table.add_column("ID", style="dim")
    table.add_column("Name", style="cyan")
    table.add_column("Role", style="white")
    table.add_column("Team", style="dim")
    table.add_column("Approver", style="green")

    for u in user_list:
        approver = "[green]Yes[/green]" if u.can_approve else "[dim]No[/dim]"
        table.add_row(u.user_id, u.display_name or u.name, u.role.value, u.team, approver)

    console.print(table)


@app.command("slack:set-monitor")
def slack_set_monitor(
    channel: str = typer.Argument(..., help="Channel ID or name"),
    enabled: bool = typer.Option(True, "--enable/--disable", help="Enable or disable monitoring"),
) -> None:
    """Enable or disable monitoring for a channel."""
    from ultrawork.slack import SlackRegistry

    config = get_config()
    registry = SlackRegistry(config.data_dir)

    channel_id = registry.resolve_channel_id(channel)
    if not channel_id:
        console.print(f"[red]Channel not found:[/red] {channel}")
        raise typer.Exit(1)

    if registry.set_channel_monitored(channel_id, enabled):
        status = "enabled" if enabled else "disabled"
        console.print(f"[green]Monitoring {status} for {channel_id}[/green]")
    else:
        console.print("[red]Failed to update channel[/red]")


@app.command("slack:set-approver")
def slack_set_approver(
    user: str = typer.Argument(..., help="User ID or name"),
    enabled: bool = typer.Option(
        True, "--enable/--disable", help="Enable or disable approval permission"
    ),
) -> None:
    """Grant or revoke approval permission for a user."""
    from ultrawork.slack import SlackRegistry

    config = get_config()
    registry = SlackRegistry(config.data_dir)

    user_id = registry.resolve_user_id(user)
    if not user_id:
        console.print(f"[red]User not found:[/red] {user}")
        raise typer.Exit(1)

    if registry.set_user_can_approve(user_id, enabled):
        status = "granted" if enabled else "revoked"
        console.print(f"[green]Approval permission {status} for {user_id}[/green]")
    else:
        console.print("[red]Failed to update user[/red]")


@app.command("slack:upload")
def slack_upload(
    file_path: Path = typer.Argument(..., help="Path to file to upload"),
    channel: str = typer.Argument(..., help="Channel ID or name"),
    thread_ts: Optional[str] = typer.Option(None, "--thread", "-t", help="Thread timestamp"),  # noqa: UP007
    title: Optional[str] = typer.Option(None, "--title", help="File title"),  # noqa: UP007
    comment: Optional[str] = typer.Option(None, "--comment", "-c", help="Initial comment"),  # noqa: UP007
) -> None:
    """Upload a file to Slack channel or thread."""
    from ultrawork.slack import SlackRegistry, SlackUploader

    config = get_config()

    # Resolve channel ID
    registry = SlackRegistry(config.data_dir)
    channel_id = registry.resolve_channel_id(channel)
    if not channel_id:
        # If not found in registry, assume it's a direct channel ID
        channel_id = channel

    if not file_path.exists():
        console.print(f"[red]File not found:[/red] {file_path}")
        raise typer.Exit(1)

    console.print(f"[dim]Uploading:[/dim] {file_path.name}")
    console.print(f"[dim]To channel:[/dim] {channel_id}")
    if thread_ts:
        console.print(f"[dim]Thread:[/dim] {thread_ts}")

    try:
        uploader = SlackUploader()
        result = uploader.upload_file(
            file_path=file_path,
            channel_id=channel_id,
            thread_ts=thread_ts,
            title=title,
            initial_comment=comment,
        )

        if result["ok"]:
            console.print("[green]Upload successful![/green]")
            console.print(f"[dim]File ID:[/dim] {result.get('file_id', 'N/A')}")
            if result.get("file_url"):
                console.print(f"[dim]URL:[/dim] {result['file_url']}")
        else:
            console.print(f"[red]Upload failed:[/red] {result.get('error', 'Unknown error')}")
            raise typer.Exit(1)
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        console.print("[dim]Set SLACK_BOT_TOKEN environment variable[/dim]")
        raise typer.Exit(1)


@app.command("slack:upload-multiple")
def slack_upload_multiple(
    files: list[Path] = typer.Argument(..., help="Paths to files to upload"),
    channel: str = typer.Option(..., "--channel", "-ch", help="Channel ID or name"),
    thread_ts: Optional[str] = typer.Option(None, "--thread", "-t", help="Thread timestamp"),  # noqa: UP007
    comment: Optional[str] = typer.Option(None, "--comment", "-c", help="Initial comment"),  # noqa: UP007
) -> None:
    """Upload multiple files to Slack channel or thread."""
    from ultrawork.slack import SlackRegistry, SlackUploader

    config = get_config()

    # Resolve channel ID
    registry = SlackRegistry(config.data_dir)
    channel_id = registry.resolve_channel_id(channel)
    if not channel_id:
        channel_id = channel

    # Check all files exist
    for f in files:
        if not f.exists():
            console.print(f"[red]File not found:[/red] {f}")
            raise typer.Exit(1)

    console.print(f"[dim]Uploading {len(files)} files to:[/dim] {channel_id}")

    try:
        uploader = SlackUploader()
        results = uploader.upload_multiple(
            file_paths=files,
            channel_id=channel_id,
            thread_ts=thread_ts,
            initial_comment=comment,
        )

        success_count = sum(1 for r in results if r["ok"])
        console.print(f"[green]Uploaded {success_count}/{len(files)} files[/green]")

        for i, result in enumerate(results):
            if result["ok"]:
                console.print(f"  [green]✓[/green] {files[i].name}")
            else:
                console.print(f"  [red]✗[/red] {files[i].name}: {result.get('error', 'Unknown')}")

    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)


@app.command("slack:explorations")
def slack_explorations(
    limit: int = typer.Option(10, "--limit", "-n", help="Max number to show"),
) -> None:
    """List recent explorations."""
    from ultrawork.slack import SlackExplorer

    config = get_config()
    explorer = SlackExplorer(config.data_dir)

    # List exploration files
    exp_dir = config.data_dir / "explorations"
    if not exp_dir.exists():
        console.print("[dim]No explorations found.[/dim]")
        return

    files = sorted(exp_dir.glob("EXP-*.md"), reverse=True)[:limit]

    if not files:
        console.print("[dim]No explorations found.[/dim]")
        return

    table = Table(title="Recent Explorations")
    table.add_column("ID", style="cyan")
    table.add_column("Status", style="white")
    table.add_column("Threads", style="dim")
    table.add_column("Created", style="dim")

    for f in files:
        exp = explorer.load_exploration(f.stem)
        if exp:
            status_color = "green" if exp.status == "completed" else "yellow"
            table.add_row(
                exp.exploration_id,
                f"[{status_color}]{exp.status}[/{status_color}]",
                str(exp.scope.threads_analyzed),
                exp.created_at.strftime("%Y-%m-%d %H:%M")
                if isinstance(exp.created_at, __import__("datetime").datetime)
                else str(exp.created_at)[:16],
            )

    console.print(table)


# --- Polling Commands ---


@app.command("poll:status")
def poll_status() -> None:
    """Show polling status and statistics."""
    from ultrawork.slack import SlackPoller

    config = get_config()
    poller = SlackPoller(
        data_dir=config.data_dir,
        bot_user_id=config.slack.bot_user_id,
        polling_config=config.polling,
        response_config=config.response,
    )

    status = poller.get_status()

    console.print("\n[bold]Polling Status[/bold]")

    if status["daemon_running"]:
        console.print(f"  [green]Daemon Running[/green] (PID: {status['daemon_pid']})")
        if status["daemon_started_at"]:
            console.print(f"  [dim]Started:[/dim] {status['daemon_started_at']}")
    else:
        console.print("  [yellow]Daemon Not Running[/yellow]")

    console.print(f"\n  [dim]Last Poll:[/dim] {status['last_poll_at'] or 'Never'}")
    console.print(f"  [dim]Total Polls:[/dim] {status['poll_count']}")
    console.print(f"  [dim]Processed Messages:[/dim] {status['processed_count']}")
    console.print(f"  [dim]Pending Responses:[/dim] {status['pending_responses']}")

    if status["consecutive_errors"] > 0:
        console.print(f"\n  [red]Consecutive Errors:[/red] {status['consecutive_errors']}")
        console.print(f"  [dim]Last Error:[/dim] {status['last_error']}")

    stats = status.get("stats", {})
    if stats.get("total_polls", 0) > 0:
        console.print("\n[bold]Statistics[/bold]")
        console.print(f"  Mentions Found: {stats.get('total_mentions_found', 0)}")
        console.print(f"  Auto Responses: {stats.get('auto_responses', 0)}")
        console.print(f"  Avg Poll Duration: {stats.get('average_poll_duration_ms', 0):.0f}ms")


@app.command("poll:start")
def poll_start(
    foreground: bool = typer.Option(False, "--foreground", "-f", help="Run in foreground"),
) -> None:
    """Start the polling daemon."""
    import subprocess
    import sys

    from ultrawork.slack import SlackPoller

    config = get_config()

    if not config.slack.bot_user_id:
        console.print("[red]Error:[/red] bot_user_id not configured")
        console.print("Set it in ultrawork.yaml or use --bot-user-id flag")
        raise typer.Exit(1)

    poller = SlackPoller(
        data_dir=config.data_dir,
        bot_user_id=config.slack.bot_user_id,
        polling_config=config.polling,
        response_config=config.response,
    )

    # Check if already running
    if poller.get_status()["daemon_running"]:
        console.print("[yellow]Daemon is already running[/yellow]")
        raise typer.Exit(0)

    if foreground:
        console.print("[green]Starting polling daemon in foreground...[/green]")
        console.print(f"[dim]Bot User ID:[/dim] {config.slack.bot_user_id}")
        console.print(f"[dim]Poll Interval:[/dim] {config.polling.poll_interval_seconds}s")
        console.print("[dim]Press Ctrl+C to stop[/dim]\n")

        # Note: In foreground mode, MCP callbacks need to be set externally
        # This is primarily for testing/debugging
        console.print("[yellow]Warning:[/yellow] Foreground mode requires MCP callbacks to be set")
        console.print("Use poll:once for interactive polling with MCP tools")
    else:
        # Start as background process
        console.print("[green]Starting polling daemon in background...[/green]")
        subprocess.Popen(
            [sys.executable, "-m", "ultrawork", "poll:start", "--foreground"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        console.print("[dim]Use poll:status to check daemon status[/dim]")


@app.command("poll:stop")
def poll_stop() -> None:
    """Stop the polling daemon."""
    import os
    import signal

    from ultrawork.slack import PollingStateManager

    config = get_config()
    state_manager = PollingStateManager(config.data_dir)
    state = state_manager.load_state()

    if state.daemon_pid is None:
        console.print("[yellow]No daemon running[/yellow]")
        return

    try:
        os.kill(state.daemon_pid, signal.SIGTERM)
        state_manager.clear_daemon()
        console.print(f"[green]Stopped daemon (PID: {state.daemon_pid})[/green]")
    except ProcessLookupError:
        state_manager.clear_daemon()
        console.print("[yellow]Daemon was not running (cleaned up stale state)[/yellow]")
    except PermissionError:
        console.print(f"[red]Permission denied to stop daemon (PID: {state.daemon_pid})[/red]")


@app.command("poll:once")
def poll_once() -> None:
    """Run a single poll cycle (interactive mode).

    Shows how to poll for mentions using MCP tools.
    Since Slack search may not work, use channel history polling instead.
    """
    from ultrawork.slack import InteractivePoller

    config = get_config()

    if not config.slack.bot_user_id:
        console.print("[red]Error:[/red] bot_user_id not configured")
        raise typer.Exit(1)

    poller = InteractivePoller(config.data_dir)
    bot_id = config.slack.bot_user_id

    console.print("\n[bold]Interactive Poll Mode[/bold]")
    console.print(f"[dim]Bot User ID:[/dim] {bot_id}")

    console.print("\n[cyan]To poll for mentions, use these MCP tools:[/cyan]")
    console.print("\n[bold]Option 1: Channel-based polling (Recommended)[/bold]")
    console.print("  1. slack_list_conversations(types='public_channel,private_channel')")
    console.print("  2. For each channel: slack_conversations_history(channel_id, limit=50)")
    console.print(f"  3. Filter messages containing '<@{bot_id}>'")
    console.print("  4. For mentions: slack_get_thread(channel_id, thread_ts)")
    console.print("  5. Process and respond with slack_send_message()")

    console.print("\n[bold]Option 2: DM-based polling[/bold]")
    console.print("  1. slack_list_conversations(types='im')")
    console.print("  2. For each DM: slack_conversations_history(channel_id, limit=20)")
    console.print("  3. Process new messages and respond")

    console.print(f"\n[dim]Mention pattern to search:[/dim] <@{bot_id}>")

    # Show pending responses
    pending = poller.get_pending_responses()
    if pending:
        console.print(f"\n[yellow]Pending Responses: {len(pending)}[/yellow]")
        console.print("[dim]Use response:list to view them[/dim]")


# --- Response Commands ---


@app.command("response:list")
def response_list() -> None:
    """List pending responses awaiting approval."""
    from ultrawork.slack import PollingStateManager

    config = get_config()
    state_manager = PollingStateManager(config.data_dir)
    pending = state_manager.list_pending_responses()

    if not pending:
        console.print("[dim]No pending responses[/dim]")
        return

    table = Table(title="Pending Responses")
    table.add_column("Message ID", style="cyan")
    table.add_column("Type", style="yellow")
    table.add_column("Confidence", style="green")
    table.add_column("Original", style="white")
    table.add_column("Response", style="dim")

    for resp in pending:
        table.add_row(
            resp.message_id[:15] + "...",
            resp.response_type.value,
            f"{resp.confidence:.0%}",
            resp.original_message[:30] + "..."
            if len(resp.original_message) > 30
            else resp.original_message,
            resp.proposed_response[:40] + "..."
            if len(resp.proposed_response) > 40
            else resp.proposed_response,
        )

    console.print(table)
    console.print("\n[dim]Use response:show <message_id> for full details[/dim]")


@app.command("response:show")
def response_show(
    message_id: str = typer.Argument(..., help="Message ID (or partial match)"),
) -> None:
    """Show details of a pending response."""
    from ultrawork.slack import PollingStateManager

    config = get_config()
    state_manager = PollingStateManager(config.data_dir)
    pending = state_manager.list_pending_responses()

    # Find matching response
    match = None
    for resp in pending:
        if resp.message_id.startswith(message_id) or message_id in resp.message_id:
            match = resp
            break

    if not match:
        console.print(f"[red]Response not found:[/red] {message_id}")
        raise typer.Exit(1)

    console.print("\n[bold cyan]Response Details[/bold cyan]")
    console.print(f"[dim]Message ID:[/dim] {match.message_id}")
    console.print(f"[dim]Channel:[/dim] {match.channel_id}")
    console.print(f"[dim]Thread:[/dim] {match.thread_ts}")
    console.print(f"[dim]From:[/dim] {match.sender_name} ({match.sender_id})")
    console.print(f"[dim]Type:[/dim] {match.response_type.value}")
    console.print(f"[dim]Intent:[/dim] {match.intent.value}")
    console.print(f"[dim]Confidence:[/dim] {match.confidence:.0%}")
    console.print(f"[dim]Created:[/dim] {match.created_at}")

    console.print("\n[bold]Original Message:[/bold]")
    console.print(f"  {match.original_message}")

    console.print("\n[bold]Proposed Response:[/bold]")
    console.print(f"  {match.proposed_response}")

    if match.context_summary:
        console.print("\n[bold]Context:[/bold]")
        console.print(f"  {match.context_summary}")

    console.print("\n[dim]Commands:[/dim]")
    console.print(f"  response:approve {match.message_id[:15]}")
    console.print(f"  response:reject {match.message_id[:15]}")


@app.command("response:approve")
def response_approve(
    message_id: str = typer.Argument(..., help="Message ID to approve"),
) -> None:
    """Approve a pending response for sending.

    Note: This approves the response but you'll need to use
    slack_send_message MCP tool to actually send it.
    """
    from ultrawork.slack import PollingStateManager

    config = get_config()
    state_manager = PollingStateManager(config.data_dir)

    # Find and approve
    pending = state_manager.list_pending_responses()
    match = None
    for resp in pending:
        if resp.message_id.startswith(message_id) or message_id in resp.message_id:
            match = resp
            break

    if not match:
        console.print(f"[red]Response not found:[/red] {message_id}")
        raise typer.Exit(1)

    approved = state_manager.approve_response(match.message_id)
    if approved:
        console.print("[green]Response approved![/green]")
        console.print("\n[dim]To send, use:[/dim]")
        console.print("  slack_send_message(")
        console.print(f'    channel_id="{approved.channel_id}",')
        console.print(f'    text="{approved.proposed_response[:50]}...",')
        console.print(f'    thread_ts="{approved.thread_ts}"')
        console.print("  )")
    else:
        console.print("[red]Failed to approve response[/red]")


@app.command("response:reject")
def response_reject(
    message_id: str = typer.Argument(..., help="Message ID to reject"),
) -> None:
    """Reject and remove a pending response."""
    from ultrawork.slack import PollingStateManager

    config = get_config()
    state_manager = PollingStateManager(config.data_dir)

    # Find and reject
    pending = state_manager.list_pending_responses()
    match = None
    for resp in pending:
        if resp.message_id.startswith(message_id) or message_id in resp.message_id:
            match = resp
            break

    if not match:
        console.print(f"[red]Response not found:[/red] {message_id}")
        raise typer.Exit(1)

    if state_manager.remove_pending_response(match.message_id):
        console.print("[yellow]Response rejected and removed[/yellow]")
    else:
        console.print("[red]Failed to remove response[/red]")


# --- Dashboard Commands ---


@app.command("dashboard")
def dashboard_start(
    host: str = typer.Option("127.0.0.1", "--host", help="Dashboard host"),
    port: int = typer.Option(7878, "--port", help="Dashboard port"),
    claude_log_dir: Optional[Path] = typer.Option(  # noqa: UP007
        None,
        "--claude-log-dir",
        help="Claude Code log directory (default: ~/.claude/projects)",
    ),
    data_dir: Optional[Path] = typer.Option(  # noqa: UP007
        None,
        "--data-dir",
        help="Ultrawork data directory (default: from ultrawork.yaml)",
    ),
) -> None:
    """Start the local dashboard server."""
    import os
    import signal
    import errno

    from ultrawork.config import find_config_path
    from ultrawork.dashboard import serve_dashboard
    from ultrawork.slack import PollingStateManager

    config = get_config()
    resolved_data_dir = data_dir.expanduser() if data_dir else config.data_dir
    if not resolved_data_dir.is_absolute():
        config_path = find_config_path()
        if config_path:
            resolved_data_dir = (config_path.parent / resolved_data_dir).resolve()
        else:
            resolved_data_dir = (Path.cwd() / resolved_data_dir).resolve()
    log_dir = claude_log_dir or Path("~/.claude/projects").expanduser()
    state_manager = PollingStateManager(resolved_data_dir)
    state = state_manager.load_state()

    # If a previous dashboard process is still recorded, stop it first.
    if state.dashboard_pid is not None:
        try:
            os.kill(state.dashboard_pid, 0)
            console.print(
                f"[yellow]Stopping existing dashboard process (PID: {state.dashboard_pid})[/yellow]"
            )
            os.kill(state.dashboard_pid, signal.SIGTERM)
            state_manager.clear_dashboard()
        except (ProcessLookupError, OSError):
            state_manager.clear_dashboard()

    state_manager.set_dashboard_running(os.getpid())
    try:
        serve_dashboard(data_dir=resolved_data_dir, log_root=log_dir, host=host, port=port)
    except OSError as exc:
        if exc.errno == errno.EADDRINUSE:
            state_manager.clear_dashboard()
            console.print(f"[red]Address already in use:[/red] http://{host}:{port}")
            console.print("[yellow]Hint:[/yellow] Stop the existing dashboard first:")
            console.print("  uv run ultrawork dashboard:stop")
            console.print("  or run with a different port using --port")
            raise typer.Exit(1)
        raise
    finally:
        state_manager.clear_dashboard()


@app.command("dashboard:stop")
def dashboard_stop() -> None:
    """Stop the local dashboard server."""
    import os
    import signal

    from ultrawork.slack import PollingStateManager

    config = get_config()
    state_manager = PollingStateManager(config.data_dir)
    state = state_manager.load_state()

    if state.dashboard_pid is None:
        console.print("[yellow]No dashboard running[/yellow]")
        return

    try:
        os.kill(state.dashboard_pid, signal.SIGTERM)
        console.print(
            f"[green]Sent stop signal to dashboard (PID: {state.dashboard_pid})[/green]"
        )
        state_manager.clear_dashboard()
        console.print("[dim]Dashboard should stop within a few seconds[/dim]")
    except ProcessLookupError:
        state_manager.clear_dashboard()
        console.print("[yellow]Dashboard was not running (cleaned up stale state)[/yellow]")
    except PermissionError:
        console.print(
            f"[red]Permission denied to stop dashboard (PID: {state.dashboard_pid})[/red]"
        )


# --- Daemon Commands (SDK-based) ---


@app.command("daemon:start")
def daemon_start(
    foreground: bool = typer.Option(True, "--foreground/--background", "-f/-b"),
    agentic: bool = typer.Option(
        False,
        "--agentic",
        "-a",
        help="Enable agentic mode: use claude -p to intelligently search context and respond",
    ),
) -> None:
    """Start the SDK-based polling daemon.

    Requires SLACK_TOKEN environment variable (or .env file).

    Use --agentic to enable intelligent responses using Claude CLI.
    """
    import subprocess
    import sys

    # Load .env file
    from dotenv import load_dotenv

    load_dotenv()

    config = get_config()

    if not config.slack.bot_user_id and not config.slack.trigger_pattern:
        console.print(
            "[red]Error:[/red] Set either slack.bot_user_id (mention mode)"
            " or slack.trigger_pattern (keyword mode) in ultrawork.yaml"
        )
        raise typer.Exit(1)

    import os

    if not os.environ.get("SLACK_TOKEN"):
        console.print("[red]Error:[/red] SLACK_TOKEN environment variable not set")
        console.print("[dim]Set it with: export SLACK_TOKEN='xoxc-...'[/dim]")
        raise typer.Exit(1)

    if foreground:
        console.print("[green]Starting SDK poller daemon...[/green]")
        if config.slack.bot_user_id:
            console.print(f"[dim]Bot User ID:[/dim] {config.slack.bot_user_id}")
        if config.slack.trigger_pattern:
            console.print(f"[dim]Trigger Pattern:[/dim] {config.slack.trigger_pattern}")
        console.print(f"[dim]Poll Interval:[/dim] {config.polling.poll_interval_seconds}s")
        if agentic:
            console.print("[cyan]Agentic Mode:[/cyan] ENABLED (claude -p)")
        console.print("[dim]Press Ctrl+C to stop[/dim]\n")

        # Set args for sdk_poller.main()
        if agentic:
            sys.argv = ["sdk_poller", "--agentic"]
        else:
            sys.argv = ["sdk_poller"]

        # Run the daemon
        from ultrawork.slack.sdk_poller import main as run_daemon

        run_daemon()
    else:
        # Start as background process
        console.print("[green]Starting SDK poller daemon in background...[/green]")
        if agentic:
            console.print("[cyan]Agentic Mode:[/cyan] ENABLED (claude -p)")

        env = os.environ.copy()
        cmd = [sys.executable, "-m", "ultrawork.slack.sdk_poller"]
        if agentic:
            cmd.append("--agentic")

        subprocess.Popen(
            cmd,
            stdout=open(config.data_dir / "logs" / "daemon_stdout.log", "a"),
            stderr=open(config.data_dir / "logs" / "daemon_stderr.log", "a"),
            env=env,
            start_new_session=True,
        )
        console.print("[dim]Use poll:status to check daemon status[/dim]")
        console.print(f"[dim]Logs: {config.data_dir}/logs/sdk_poller.log[/dim]")


@app.command("daemon:stop")
def daemon_stop() -> None:
    """Stop the SDK-based polling daemon."""
    import os
    import signal

    from ultrawork.slack import PollingStateManager

    config = get_config()
    state_manager = PollingStateManager(config.data_dir)
    state = state_manager.load_state()

    if state.daemon_pid is None:
        console.print("[yellow]No daemon running[/yellow]")
        return

    try:
        os.kill(state.daemon_pid, signal.SIGTERM)
        console.print(f"[green]Sent stop signal to daemon (PID: {state.daemon_pid})[/green]")
        console.print("[dim]Daemon should stop within a few seconds[/dim]")
    except ProcessLookupError:
        state_manager.clear_daemon()
        console.print("[yellow]Daemon was not running (cleaned up stale state)[/yellow]")
    except PermissionError:
        console.print(f"[red]Permission denied to stop daemon (PID: {state.daemon_pid})[/red]")


# --- Start Commands ---


@app.command("start")
def start(
    host: str = typer.Option("127.0.0.1", "--host", help="Dashboard host"),
    port: int = typer.Option(7878, "--port", help="Dashboard port"),
    claude_log_dir: Optional[Path] = typer.Option(  # noqa: UP007
        None,
        "--claude-log-dir",
        help="Claude Code log directory (default: ~/.claude/projects)",
    ),
    data_dir: Optional[Path] = typer.Option(  # noqa: UP007
        None,
        "--data-dir",
        help="Ultrawork data directory (default: from ultrawork.yaml)",
    ),
    agentic: bool = typer.Option(
        True,
        "--agentic/--no-agentic",
        help="Enable agentic mode for the polling daemon",
    ),
) -> None:
    """Start polling daemon and dashboard together."""
    daemon_started = False
    try:
        daemon_start(foreground=False, agentic=agentic)
        daemon_started = True
        console.print("[green]Starting dashboard...[/green]")
        dashboard_start(
            host=host,
            port=port,
            claude_log_dir=claude_log_dir,
            data_dir=data_dir,
        )
    finally:
        if daemon_started:
            poll_stop()
            daemon_stop()


@app.command("end")
def end() -> None:
    """Stop all background polling daemons.

    Stops SDK daemon, legacy poll daemon, and dashboard, if running.
    """
    console.print("[yellow]Stopping all Ultrawork background daemons...[/yellow]")
    poll_stop()
    daemon_stop()
    dashboard_stop()


# --- Config Commands ---


@app.command("config:show")
def config_show() -> None:
    """Show current configuration."""
    config = get_config()
    console.print(config.model_dump_json(indent=2))


@app.command("config:init")
def config_init(
    config_path: Path = typer.Option(Path("ultrawork.yaml"), "--output", "-o", help="Output path"),
) -> None:
    """Create a default configuration file."""
    config = UltraworkConfig()
    config.save(config_path)
    console.print(f"[green]Configuration saved to:[/green] {config_path}")


# --- Cron Job Commands ---


@app.command("cron:list")
def cron_list(
    all_jobs: bool = typer.Option(False, "--all", "-a", help="Show all jobs including deleted/completed"),
) -> None:
    """List cron jobs."""
    from ultrawork.scheduler import CronJobManager

    config = get_config()
    manager = CronJobManager(config.data_dir)

    jobs = manager.list_jobs(active_only=not all_jobs)

    if not jobs:
        console.print("[dim]No cron jobs found.[/dim]")
        console.print("[dim]Create one with: ultrawork cron:create[/dim]")
        return

    table = Table(title="Cron Jobs")
    table.add_column("ID", style="cyan")
    table.add_column("Name", style="white")
    table.add_column("Schedule", style="yellow")
    table.add_column("Action", style="green")
    table.add_column("Status", style="white")
    table.add_column("Last Run", style="dim")
    table.add_column("Runs", style="dim")

    for job in jobs:
        status_color = {
            "active": "green",
            "paused": "yellow",
            "completed": "dim",
            "failed": "red",
            "deleted": "dim",
        }.get(job.status.value, "white")

        last_run = ""
        if job.last_run_at:
            lr = job.last_run_at
            if isinstance(lr, str):
                last_run = lr[:16]
            else:
                last_run = lr.strftime("%Y-%m-%d %H:%M")

        table.add_row(
            job.job_id,
            job.name[:30] + "..." if len(job.name) > 30 else job.name,
            job.schedule.get_description(),
            job.action.value,
            f"[{status_color}]{job.status.value}[/{status_color}]",
            last_run or "Never",
            str(job.run_count),
        )

    console.print(table)


@app.command("cron:show")
def cron_show(
    job_id: str = typer.Argument(..., help="Cron job ID"),
) -> None:
    """Show cron job details."""
    from ultrawork.scheduler import CronJobManager

    config = get_config()
    manager = CronJobManager(config.data_dir)

    job = manager.load_job(job_id)
    if not job:
        console.print(f"[red]Job not found:[/red] {job_id}")
        raise typer.Exit(1)

    console.print(f"\n[bold cyan]{job.job_id}[/bold cyan] - {job.name}")
    console.print(f"[dim]Description:[/dim] {job.description}")
    console.print(f"[dim]Schedule:[/dim] {job.schedule.get_description()}")
    console.print(f"[dim]Action:[/dim] {job.action.value}")
    console.print(f"[dim]Status:[/dim] {job.status.value}")
    console.print(f"[dim]Created:[/dim] {job.created_at}")
    console.print(f"[dim]Created by:[/dim] {job.created_by}")
    console.print(f"[dim]Run count:[/dim] {job.run_count}")
    console.print(f"[dim]Error count:[/dim] {job.error_count}")

    if job.last_run_at:
        console.print(f"[dim]Last run:[/dim] {job.last_run_at}")
    if job.last_error:
        console.print(f"[red]Last error:[/red] {job.last_error}")

    if job.notify_user_id:
        console.print(f"[dim]Notify user:[/dim] {job.notify_user_id}")
    if job.notify_channel_id:
        console.print(f"[dim]Notify channel:[/dim] {job.notify_channel_id}")

    if job.thread_targets:
        console.print("\n[bold]Thread Targets:[/bold]")
        for t in job.thread_targets:
            desc = f" - {t.description}" if t.description else ""
            ch = f"#{t.channel_name}" if t.channel_name else t.channel_id
            console.print(f"  {ch}/{t.thread_ts}{desc}")

    if job.channel_targets:
        console.print("\n[bold]Channel Targets:[/bold]")
        for ch_id in job.channel_targets:
            console.print(f"  {ch_id}")


@app.command("cron:create")
def cron_create(
    name: str = typer.Argument(..., help="Job name"),
    schedule: str = typer.Option("weekday", "--schedule", "-s", help="Schedule type: interval|daily|weekday|weekly|cron"),
    at: Optional[str] = typer.Option(None, "--at", help="Time in HH:MM format (for daily/weekday/weekly)"),  # noqa: UP007
    hours: Optional[int] = typer.Option(None, "--hours", help="Hours between runs (for interval)"),  # noqa: UP007
    minutes: Optional[int] = typer.Option(None, "--minutes", help="Minutes between runs (for interval)"),  # noqa: UP007
    day: Optional[str] = typer.Option(None, "--day", help="Day of week (for weekly)"),  # noqa: UP007
    expression: Optional[str] = typer.Option(None, "--expression", help="Cron expression (for cron type)"),  # noqa: UP007
    action: str = typer.Option("check_thread_reactions", "--action", "-a", help="Action type"),
    notify_user: Optional[str] = typer.Option(None, "--notify-user", help="User ID to notify via DM"),  # noqa: UP007
    notify_channel: Optional[str] = typer.Option(None, "--notify-channel", help="DM channel ID for notifications"),  # noqa: UP007
    description: str = typer.Option("", "--description", "-d", help="Job description"),
) -> None:
    """Create a new cron job."""
    from ultrawork.models.cronjob import CronJobAction, CronSchedule, CronScheduleType
    from ultrawork.scheduler import CronJobManager

    config = get_config()
    manager = CronJobManager(config.data_dir)

    cron_schedule = CronSchedule(
        type=CronScheduleType(schedule),
        at=at,
        hours=hours,
        minutes=minutes,
        day=day,
        expression=expression,
    )

    job = manager.create_job(
        name=name,
        description=description,
        schedule=cron_schedule,
        action=CronJobAction(action),
        notify_user_id=notify_user or "",
        notify_channel_id=notify_channel or "",
    )

    console.print(f"[green]Created cron job:[/green] {job.job_id}")
    console.print(f"[dim]Name:[/dim] {job.name}")
    console.print(f"[dim]Schedule:[/dim] {job.schedule.get_description()}")
    console.print(f"[dim]Action:[/dim] {job.action.value}")


@app.command("cron:pause")
def cron_pause(
    job_id: str = typer.Argument(..., help="Cron job ID"),
) -> None:
    """Pause a cron job."""
    from ultrawork.scheduler import CronJobManager

    config = get_config()
    manager = CronJobManager(config.data_dir)

    if manager.pause_job(job_id):
        console.print(f"[yellow]Paused:[/yellow] {job_id}")
    else:
        console.print(f"[red]Job not found:[/red] {job_id}")
        raise typer.Exit(1)


@app.command("cron:resume")
def cron_resume(
    job_id: str = typer.Argument(..., help="Cron job ID"),
) -> None:
    """Resume a paused cron job."""
    from ultrawork.scheduler import CronJobManager

    config = get_config()
    manager = CronJobManager(config.data_dir)

    if manager.resume_job(job_id):
        console.print(f"[green]Resumed:[/green] {job_id}")
    else:
        console.print(f"[red]Job not found:[/red] {job_id}")
        raise typer.Exit(1)


@app.command("cron:delete")
def cron_delete(
    job_id: str = typer.Argument(..., help="Cron job ID"),
) -> None:
    """Delete a cron job."""
    from ultrawork.scheduler import CronJobManager

    config = get_config()
    manager = CronJobManager(config.data_dir)

    if manager.delete_job(job_id):
        console.print(f"[red]Deleted:[/red] {job_id}")
    else:
        console.print(f"[red]Job not found:[/red] {job_id}")
        raise typer.Exit(1)


@app.command("cron:run")
def cron_run(
    job_id: str = typer.Argument(..., help="Cron job ID"),
) -> None:
    """Manually trigger a cron job execution."""
    import os

    from dotenv import load_dotenv

    load_dotenv()

    from ultrawork.scheduler import CronJobManager
    from ultrawork.scheduler.runner import CronRunner

    config = get_config()
    manager = CronJobManager(config.data_dir)

    job = manager.load_job(job_id)
    if not job:
        console.print(f"[red]Job not found:[/red] {job_id}")
        raise typer.Exit(1)

    console.print(f"[yellow]Running:[/yellow] {job.name} ({job.job_id})")

    runner = CronRunner(
        data_dir=config.data_dir,
        slack_token=os.environ.get("SLACK_TOKEN"),
        slack_cookie=os.environ.get("SLACK_COOKIE"),
    )

    log = runner.execute_job(job)

    if log.success:
        console.print("[green]Execution successful[/green]")
    else:
        console.print(f"[red]Execution failed:[/red] {log.error}")

    console.print(f"[dim]Duration:[/dim] {log.duration_ms}ms")
    console.print(f"[dim]Threads checked:[/dim] {log.threads_checked}")
    console.print(f"[dim]New replies:[/dim] {log.new_replies_found}")
    console.print(f"[dim]New reactions:[/dim] {log.new_reactions_found}")
    console.print(f"[dim]DM sent:[/dim] {log.dm_sent}")


@app.command("cron:logs")
def cron_logs(
    job_id: str = typer.Argument(..., help="Cron job ID"),
    limit: int = typer.Option(10, "--limit", "-n", help="Number of logs to show"),
) -> None:
    """View execution logs for a cron job."""
    import yaml as _yaml

    from ultrawork.scheduler import CronJobManager

    config = get_config()
    manager = CronJobManager(config.data_dir)

    job = manager.load_job(job_id)
    if not job:
        console.print(f"[red]Job not found:[/red] {job_id}")
        raise typer.Exit(1)

    log_files = sorted(
        manager.logs_dir.glob(f"{job_id}_*.yaml"),
        reverse=True,
    )[:limit]

    if not log_files:
        console.print("[dim]No execution logs found.[/dim]")
        return

    table = Table(title=f"Execution Logs: {job_id}")
    table.add_column("Time", style="dim")
    table.add_column("Success", style="white")
    table.add_column("Duration", style="dim")
    table.add_column("Threads", style="dim")
    table.add_column("Replies", style="dim")
    table.add_column("DM", style="dim")
    table.add_column("Error", style="red")

    for log_file in log_files:
        data = _yaml.safe_load(log_file.read_text(encoding="utf-8"))
        if not data:
            continue

        success = "[green]Yes[/green]" if data.get("success") else "[red]No[/red]"
        table.add_row(
            str(data.get("executed_at", ""))[:16],
            success,
            f"{data.get('duration_ms', 0)}ms",
            str(data.get("threads_checked", 0)),
            str(data.get("new_replies_found", 0)),
            "Yes" if data.get("dm_sent") else "No",
            (data.get("error", "") or "")[:40],
        )

    console.print(table)


# --- Setup Wizard ---


@app.command("setup")
def setup_wizard() -> None:
    """Launch the interactive setup wizard (TUI)."""
    from ultrawork.installer.app import run_setup

    run_setup(project_dir=Path.cwd())


if __name__ == "__main__":
    app()
