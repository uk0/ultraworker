"""YAML frontmatter schema and serialization for context files."""

from datetime import datetime
from pathlib import Path
from typing import Any

import frontmatter
import yaml

from ultrawork.models import TaskRecord, ThreadRecord


def _datetime_representer(dumper: yaml.Dumper, data: datetime) -> yaml.ScalarNode:
    """Custom YAML representer for datetime objects."""
    return dumper.represent_scalar("tag:yaml.org,2002:timestamp", data.isoformat())


yaml.add_representer(datetime, _datetime_representer)


def task_to_frontmatter(task: TaskRecord) -> str:
    """Convert a TaskRecord to Markdown with YAML frontmatter."""
    # Build YAML metadata
    metadata: dict[str, Any] = {
        "task_id": task.task_id,
        "title": task.title,
        "created_at": task.created_at,
        "updated_at": task.updated_at,
        "source": task.source.model_dump(exclude_none=True),
        "workflow": {
            "current_stage": task.workflow.current_stage.value,
            "type": task.workflow.type.value,
            "stages": {
                name: {k: v for k, v in stage.model_dump(mode="json").items() if v is not None}
                for name, stage in task.workflow.stages.items()
            },
        },
    }

    if task.artifacts:
        metadata["artifacts"] = [
            a.model_dump(mode="json", exclude_none=True) for a in task.artifacts
        ]

    if task.trace:
        metadata["trace"] = [
            {k: v for k, v in t.model_dump(mode="json").items() if v is not None}
            for t in task.trace
        ]

    # Build markdown content
    content_parts = []

    # TODO items
    content_parts.append("## TODO")
    if task.todo_items:
        for item in task.todo_items:
            content_parts.append(f"- [ ] {item}")
    else:
        content_parts.append("[No items yet]")

    # Request content
    content_parts.append("\n## Request Content")
    content_parts.append(task.request_content or "[Original request content]")

    # Work notes
    content_parts.append("\n## Work Notes")
    content_parts.append(task.work_notes or "[Progress notes and issues]")

    content = "\n".join(content_parts)

    # Create frontmatter post
    post = frontmatter.Post(content, **metadata)
    return frontmatter.dumps(post)


def frontmatter_to_task(file_path: Path) -> TaskRecord:
    """Parse a Markdown file with YAML frontmatter into a TaskRecord."""
    post = frontmatter.load(file_path)

    # Parse workflow state
    workflow_data = post.metadata.get("workflow", {})
    stages_data = workflow_data.get("stages", {})

    from ultrawork.models import (
        StageInfo,
        StageStatus,
        WorkflowStage,
        WorkflowState,
        WorkflowType,
    )

    stages = {}
    for name, stage_dict in stages_data.items():
        if "status" in stage_dict:
            stage_dict["status"] = StageStatus(stage_dict["status"])
        stages[name] = StageInfo(**stage_dict)

    workflow = WorkflowState(
        current_stage=WorkflowStage(workflow_data.get("current_stage", "todo")),
        type=WorkflowType(workflow_data.get("type", "full")),
        stages=stages,
    )

    # Parse artifacts
    from ultrawork.models import Artifact

    artifacts = [Artifact(**a) for a in post.metadata.get("artifacts", [])]

    # Parse trace
    from ultrawork.models import TraceEntry

    trace = [TraceEntry(**t) for t in post.metadata.get("trace", [])]

    # Parse source
    from ultrawork.models import TaskSource

    source = TaskSource(**post.metadata.get("source", {}))

    # Extract TODO items from content
    todo_items = []
    content = post.content
    for line in content.split("\n"):
        line = line.strip()
        if line.startswith("- [ ]") or line.startswith("- [x]"):
            todo_items.append(line[6:].strip())

    return TaskRecord(
        task_id=post.metadata["task_id"],
        title=post.metadata["title"],
        created_at=post.metadata["created_at"],
        updated_at=post.metadata["updated_at"],
        source=source,
        workflow=workflow,
        artifacts=artifacts,
        trace=trace,
        todo_items=todo_items,
        request_content=_extract_section(content, "Request Content"),
        work_notes=_extract_section(content, "Work Notes"),
    )


def thread_to_frontmatter(thread: ThreadRecord) -> str:
    """Convert a ThreadRecord to Markdown with YAML frontmatter."""
    metadata: dict[str, Any] = {
        "thread_id": thread.thread_id,
        "channel_id": thread.channel_id,
        "channel_name": thread.channel_name,
        "thread_ts": thread.thread_ts,
        "created_at": thread.created_at,
        "updated_at": thread.updated_at,
        "participants": [p.model_dump(mode="json") for p in thread.participants],
        "linked_tasks": [t.model_dump(mode="json") for t in thread.linked_tasks],
        "last_sync_ts": thread.last_sync_ts,
        "message_count": thread.message_count,
    }

    content_parts = []
    content_parts.append("## Thread Summary")
    content_parts.append(thread.summary or "[Auto-generated summary]")
    content_parts.append("\n## Message History")
    content_parts.append(
        thread.messages_markdown or "| Time | Sender | Content |\n|------|--------|---------|"
    )

    content = "\n".join(content_parts)
    post = frontmatter.Post(content, **metadata)
    return frontmatter.dumps(post)


def frontmatter_to_thread(file_path: Path) -> ThreadRecord:
    """Parse a Markdown file with YAML frontmatter into a ThreadRecord."""
    post = frontmatter.load(file_path)

    from ultrawork.models import LinkedTask, Participant, ParticipantRole

    participants = []
    for p in post.metadata.get("participants", []):
        p["role"] = ParticipantRole(p["role"])
        participants.append(Participant(**p))

    linked_tasks = [LinkedTask(**t) for t in post.metadata.get("linked_tasks", [])]

    return ThreadRecord(
        thread_id=post.metadata["thread_id"],
        channel_id=post.metadata["channel_id"],
        channel_name=post.metadata["channel_name"],
        thread_ts=post.metadata["thread_ts"],
        created_at=post.metadata["created_at"],
        updated_at=post.metadata["updated_at"],
        participants=participants,
        linked_tasks=linked_tasks,
        last_sync_ts=post.metadata.get("last_sync_ts"),
        message_count=post.metadata.get("message_count", 0),
        summary=_extract_section(post.content, "Thread Summary"),
        messages_markdown=_extract_section(post.content, "Message History"),
    )


def _extract_section(content: str, section_name: str) -> str:
    """Extract content from a markdown section."""
    lines = content.split("\n")
    in_section = False
    section_lines = []

    for line in lines:
        if line.startswith("## "):
            if in_section:
                break
            if section_name in line:
                in_section = True
                continue
        elif in_section:
            section_lines.append(line)

    return "\n".join(section_lines).strip()
