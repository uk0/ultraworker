"""YAML frontmatter schema and serialization for context files."""

from datetime import datetime
from pathlib import Path
from typing import Any

import frontmatter
import yaml

from ultrawork.models import TaskRecord, ThreadRecord
from ultrawork.models.ltm import (
    Discovery,
    HowStep,
    LinkRelation,
    RequestRecord,
    ShallowLink,
    WhyHypothesis,
    WorkAction,
    WorkRecord,
    WorkWhere,
    WorkWhy,
    WorkWhyKind,
)


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


def request_to_frontmatter(record: RequestRecord) -> str:
    """Convert a RequestRecord to Markdown with YAML frontmatter."""
    metadata: dict[str, Any] = {
        "id": record.id,
        "type": record.type,
        "who": record.who,
        "when": record.when,
        "where": record.where,
        "created_at": record.created_at,
        "updated_at": record.updated_at,
        "facet_keys": record.facet_keys,
    }
    if record.why:
        metadata["why"] = [h.model_dump(mode="json") for h in record.why]
    if record.how:
        metadata["how"] = [s.model_dump(mode="json") for s in record.how]
    if record.discoveries:
        metadata["discoveries"] = [d.model_dump(mode="json") for d in record.discoveries]
    if record.links:
        metadata["links"] = [lnk.model_dump(mode="json") for lnk in record.links]

    # Build markdown body with facet keys on first line for search stability
    body_parts = [f"# {' '.join(record.facet_keys[:10])}"]

    body_parts.append("\n## What")
    body_parts.append(record.what or "[No description]")

    if record.why:
        body_parts.append("\n## Why")
        for h in record.why:
            body_parts.append(f"- **{h.hypothesis}** (confidence: {h.confidence})")
            for e in h.evidence:
                body_parts.append(f"  - {e}")

    if record.how:
        body_parts.append("\n## How (Steps)")
        for step in record.how:
            check = "x" if step.done else " "
            body_parts.append(f"- [{check}] `{step.step_id}`: {step.goal}")

    if record.discoveries:
        body_parts.append("\n## Discoveries")
        for disc in record.discoveries:
            body_parts.append(f"- {disc.description}")

    content = "\n".join(body_parts)
    post = frontmatter.Post(content, **metadata)
    return frontmatter.dumps(post)


def frontmatter_to_request(file_path: Path) -> RequestRecord:
    """Parse a Markdown file with YAML frontmatter into a RequestRecord."""
    post = frontmatter.load(file_path)
    meta = post.metadata

    why = [WhyHypothesis(**h) for h in meta.get("why", [])]
    how = [HowStep(**s) for s in meta.get("how", [])]
    discoveries = [Discovery(**d) for d in meta.get("discoveries", [])]
    links = [
        ShallowLink(
            target_id=lnk["target_id"],
            relation=LinkRelation(lnk.get("relation", "related")),
            weight=lnk.get("weight", 0.5),
        )
        for lnk in meta.get("links", [])
    ]

    # Extract "what" from body if not in metadata
    what = meta["what"] if "what" in meta else _extract_section(post.content, "What")

    return RequestRecord(
        id=meta["id"],
        who=meta.get("who", ""),
        when=meta.get("when", datetime.now()),
        where=meta.get("where", ""),
        what=what,
        why=why,
        how=how,
        discoveries=discoveries,
        facet_keys=meta.get("facet_keys", []),
        links=links,
        created_at=meta.get("created_at", datetime.now()),
        updated_at=meta.get("updated_at", datetime.now()),
    )


def work_to_frontmatter(record: WorkRecord) -> str:
    """Convert a WorkRecord to Markdown with YAML frontmatter."""
    metadata: dict[str, Any] = {
        "id": record.id,
        "type": record.type,
        "who": record.who,
        "when": record.when,
        "created_at": record.created_at,
        "updated_at": record.updated_at,
        "facet_keys": record.facet_keys,
        "why": record.why.model_dump(mode="json"),
        "where": record.where.model_dump(mode="json"),
    }
    if record.what:
        metadata["what"] = [a.model_dump(mode="json") for a in record.what]
    if record.evidence:
        metadata["evidence"] = record.evidence
    if record.links:
        metadata["links"] = [lnk.model_dump(mode="json") for lnk in record.links]

    body_parts = [f"# {' '.join(record.facet_keys[:10])}"]

    body_parts.append("\n## Purpose")
    body_parts.append(f"Kind: {record.why.kind.value}")
    if record.why.step_ref:
        body_parts.append(f"Step ref: {record.why.step_ref}")
    if record.why.immediate_goal:
        body_parts.append(f"Goal: {record.why.immediate_goal}")

    if record.what:
        body_parts.append("\n## Actions")
        for action in record.what:
            body_parts.append(f"- **{action.action}**")
            if action.output:
                body_parts.append(f"  Output: {action.output}")

    if record.evidence:
        body_parts.append("\n## Evidence")
        for e in record.evidence:
            body_parts.append(f"- {e}")

    content = "\n".join(body_parts)
    post = frontmatter.Post(content, **metadata)
    return frontmatter.dumps(post)


def frontmatter_to_work(file_path: Path) -> WorkRecord:
    """Parse a Markdown file with YAML frontmatter into a WorkRecord."""
    post = frontmatter.load(file_path)
    meta = post.metadata

    why_data = meta.get("why", {})
    why = WorkWhy(
        kind=WorkWhyKind(why_data.get("kind", "advance_step")),
        step_ref=why_data.get("step_ref"),
        immediate_goal=why_data.get("immediate_goal", ""),
    )

    where_data = meta.get("where", {})
    where = WorkWhere(
        inputs=where_data.get("inputs", []),
        outputs=where_data.get("outputs", []),
    )

    what = [WorkAction(**a) for a in meta.get("what", [])]
    links = [
        ShallowLink(
            target_id=lnk["target_id"],
            relation=LinkRelation(lnk.get("relation", "related")),
            weight=lnk.get("weight", 0.5),
        )
        for lnk in meta.get("links", [])
    ]

    return WorkRecord(
        id=meta["id"],
        who=meta.get("who", ""),
        when=meta.get("when", datetime.now()),
        why=why,
        where=where,
        what=what,
        evidence=meta.get("evidence", []),
        facet_keys=meta.get("facet_keys", []),
        links=links,
        created_at=meta.get("created_at", datetime.now()),
        updated_at=meta.get("updated_at", datetime.now()),
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
