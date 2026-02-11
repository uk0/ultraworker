"""Indexer for fast lookup of tasks and threads."""

from pathlib import Path
from typing import Any

import yaml

from ultrawork.context.manager import ContextManager
from ultrawork.models import WorkflowStage


class ContextIndexer:
    """Maintains indexes for fast lookup of context records."""

    def __init__(self, data_dir: str | Path = "data"):
        self.data_dir = Path(data_dir)
        self.index_dir = self.data_dir / "index"
        self.index_dir.mkdir(parents=True, exist_ok=True)

        self.active_tasks_file = self.index_dir / "active_tasks.yaml"
        self.thread_map_file = self.index_dir / "thread_map.yaml"

        self._manager = ContextManager(data_dir)

    def rebuild_indexes(self) -> None:
        """Rebuild all indexes from source files."""
        self._rebuild_active_tasks()
        self._rebuild_thread_map()

    def _rebuild_active_tasks(self) -> None:
        """Rebuild the active tasks index."""
        tasks = self._manager.list_tasks(active_only=True)

        index: dict[str, Any] = {
            "updated_at": None,
            "tasks": [],
        }

        from datetime import datetime

        index["updated_at"] = datetime.now().isoformat()

        for task in tasks:
            index["tasks"].append(
                {
                    "task_id": task.task_id,
                    "title": task.title,
                    "stage": task.workflow.current_stage.value,
                    "type": task.workflow.type.value,
                    "thread_id": task.source.thread_id,
                    "updated_at": task.updated_at.isoformat(),
                }
            )

        self._write_yaml(self.active_tasks_file, index)

    def _rebuild_thread_map(self) -> None:
        """Rebuild the thread to task mapping index."""
        tasks = self._manager.list_tasks()

        thread_map: dict[str, list[dict[str, str]]] = {}

        for task in tasks:
            thread_id = task.source.thread_id
            if thread_id:
                if thread_id not in thread_map:
                    thread_map[thread_id] = []
                thread_map[thread_id].append(
                    {
                        "task_id": task.task_id,
                        "title": task.title,
                        "stage": task.workflow.current_stage.value,
                    }
                )

        from datetime import datetime

        index = {
            "updated_at": datetime.now().isoformat(),
            "threads": thread_map,
        }

        self._write_yaml(self.thread_map_file, index)

    def get_active_tasks(self) -> list[dict[str, Any]]:
        """Get list of active tasks from index."""
        if not self.active_tasks_file.exists():
            self._rebuild_active_tasks()

        data = self._read_yaml(self.active_tasks_file)
        return data.get("tasks", [])

    def get_tasks_for_thread(self, thread_id: str) -> list[dict[str, Any]]:
        """Get tasks associated with a thread from index."""
        if not self.thread_map_file.exists():
            self._rebuild_thread_map()

        data = self._read_yaml(self.thread_map_file)
        threads = data.get("threads", {})
        return threads.get(thread_id, [])

    def get_pending_approvals(self) -> list[dict[str, Any]]:
        """Get tasks that are pending approval at their current stage."""
        active = self.get_active_tasks()
        pending = []

        for task_info in active:
            task = self._manager.get_task_record(task_info["task_id"])
            if task:
                current = task.workflow.current_stage.value
                stage_info = task.workflow.stages.get(current)
                if stage_info and stage_info.status.value == "pending":
                    pending.append(
                        {
                            "task_id": task.task_id,
                            "title": task.title,
                            "stage": current,
                            "thread_id": task.source.thread_id,
                        }
                    )

        return pending

    def search_tasks(
        self,
        query: str | None = None,
        stage: WorkflowStage | None = None,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        """Search tasks by title or filter by stage."""
        tasks = self._manager.list_tasks()
        results = []

        for task in tasks:
            # Filter by stage
            if stage and task.workflow.current_stage != stage:
                continue

            # Filter by query (search in title and request_content)
            if query:
                query_lower = query.lower()
                if (
                    query_lower not in task.title.lower()
                    and query_lower not in task.request_content.lower()
                ):
                    continue

            results.append(
                {
                    "task_id": task.task_id,
                    "title": task.title,
                    "stage": task.workflow.current_stage.value,
                    "type": task.workflow.type.value,
                    "updated_at": task.updated_at.isoformat(),
                }
            )

            if len(results) >= limit:
                break

        return results

    def _read_yaml(self, file_path: Path) -> dict[str, Any]:
        """Read a YAML file."""
        if not file_path.exists():
            return {}
        return yaml.safe_load(file_path.read_text(encoding="utf-8")) or {}

    def _write_yaml(self, file_path: Path, data: dict[str, Any]) -> None:
        """Write a YAML file."""
        file_path.write_text(yaml.dump(data, allow_unicode=True), encoding="utf-8")
