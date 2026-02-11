"""Context file manager for CRUD operations on task and thread records."""

from datetime import datetime
from pathlib import Path

from ultrawork.context.schema import (
    frontmatter_to_task,
    frontmatter_to_thread,
    task_to_frontmatter,
    thread_to_frontmatter,
)
from ultrawork.models import (
    TaskRecord,
    TaskSource,
    ThreadRecord,
    TraceEntry,
    WorkflowStage,
)


class ContextManager:
    """Manages context files for tasks and threads."""

    def __init__(self, data_dir: str | Path = "data"):
        self.data_dir = Path(data_dir)
        self.threads_dir = self.data_dir / "threads"
        self.tasks_dir = self.data_dir / "tasks"
        self.specs_dir = self.data_dir / "specs"
        self.index_dir = self.data_dir / "index"

        # Ensure directories exist
        for dir_path in [self.threads_dir, self.tasks_dir, self.specs_dir, self.index_dir]:
            dir_path.mkdir(parents=True, exist_ok=True)

    # --- Thread Operations ---

    def create_thread_record(self, thread: ThreadRecord) -> Path:
        """Create a new thread record file."""
        channel_dir = self.threads_dir / thread.channel_id
        channel_dir.mkdir(parents=True, exist_ok=True)

        file_path = channel_dir / f"{thread.thread_ts}.md"
        content = thread_to_frontmatter(thread)
        file_path.write_text(content, encoding="utf-8")
        return file_path

    def get_thread_record(self, channel_id: str, thread_ts: str) -> ThreadRecord | None:
        """Get a thread record by channel and timestamp."""
        file_path = self.threads_dir / channel_id / f"{thread_ts}.md"
        if not file_path.exists():
            return None
        return frontmatter_to_thread(file_path)

    def update_thread_record(self, thread: ThreadRecord) -> Path:
        """Update an existing thread record."""
        thread.updated_at = datetime.now()
        return self.create_thread_record(thread)  # Overwrites existing

    def list_threads(self, channel_id: str | None = None) -> list[ThreadRecord]:
        """List all thread records, optionally filtered by channel."""
        threads = []
        search_dir = self.threads_dir / channel_id if channel_id else self.threads_dir

        for file_path in search_dir.rglob("*.md"):
            try:
                threads.append(frontmatter_to_thread(file_path))
            except Exception:
                continue  # Skip invalid files

        return sorted(threads, key=lambda t: t.updated_at, reverse=True)

    # --- Task Operations ---

    def create_task_record(
        self,
        title: str,
        source: TaskSource,
        request_content: str = "",
    ) -> TaskRecord:
        """Create a new task record."""
        now = datetime.now()
        task = TaskRecord(
            task_id=TaskRecord.generate_id(),
            title=title,
            created_at=now,
            updated_at=now,
            source=source,
            request_content=request_content,
        )
        task.add_trace("task_created", f"Task created from {source.type}")

        self._save_task(task)
        return task

    def get_task_record(self, task_id: str) -> TaskRecord | None:
        """Get a task record by ID."""
        file_path = self.tasks_dir / f"{task_id}.md"
        if not file_path.exists():
            return None
        return frontmatter_to_task(file_path)

    def update_task_record(self, task: TaskRecord) -> Path:
        """Update an existing task record."""
        task.updated_at = datetime.now()
        return self._save_task(task)

    def _save_task(self, task: TaskRecord) -> Path:
        """Save a task record to file."""
        file_path = self.tasks_dir / f"{task.task_id}.md"
        content = task_to_frontmatter(task)
        file_path.write_text(content, encoding="utf-8")
        return file_path

    def list_tasks(
        self,
        stage: WorkflowStage | None = None,
        active_only: bool = False,
    ) -> list[TaskRecord]:
        """List all task records with optional filtering."""
        tasks = []
        for file_path in self.tasks_dir.glob("*.md"):
            try:
                task = frontmatter_to_task(file_path)
                if stage and task.workflow.current_stage != stage:
                    continue
                if active_only and task.workflow.current_stage == WorkflowStage.DONE:
                    continue
                tasks.append(task)
            except Exception:
                continue

        return sorted(tasks, key=lambda t: t.updated_at, reverse=True)

    def find_tasks_by_thread(self, thread_id: str) -> list[TaskRecord]:
        """Find all tasks associated with a thread."""
        tasks = []
        for task in self.list_tasks():
            if task.source.thread_id == thread_id:
                tasks.append(task)
        return tasks

    # --- Trace Operations ---

    def add_trace(
        self,
        task_id: str,
        action: str,
        details: str | None = None,
        stage: str | None = None,
        by: str | None = None,
    ) -> bool:
        """Add a trace entry to a task."""
        task = self.get_task_record(task_id)
        if not task:
            return False

        task.trace.append(
            TraceEntry(
                ts=datetime.now(),
                action=action,
                details=details,
                stage=stage,
                by=by,
            )
        )
        self.update_task_record(task)
        return True

    # --- Linking Operations ---

    def link_task_to_thread(self, task_id: str, thread_id: str) -> bool:
        """Link a task to a thread (bidirectional)."""
        # Parse thread_id
        parts = thread_id.split("-", 1)
        if len(parts) != 2:
            return False
        channel_id, thread_ts = parts

        task = self.get_task_record(task_id)
        thread = self.get_thread_record(channel_id, thread_ts)

        if not task or not thread:
            return False

        # Update task source
        task.source.thread_id = thread_id
        self.update_task_record(task)

        # Update thread linked tasks
        from ultrawork.models import LinkedTask

        existing_ids = {lt.task_id for lt in thread.linked_tasks}
        if task_id not in existing_ids:
            thread.linked_tasks.append(
                LinkedTask(task_id=task_id, status=task.workflow.current_stage.value)
            )
            self.update_thread_record(thread)

        return True
