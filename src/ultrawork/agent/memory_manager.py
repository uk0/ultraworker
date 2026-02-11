"""Context memory management for agent sessions.

This module provides MemoryManager for managing long-term and short-term
context memory across agent sessions.
"""

import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import yaml

from ultrawork.models.memory import (
    ContextMemory,
    MemoryEntry,
    MemoryScope,
    MemoryType,
)


class MemoryManager:
    """Manages context memory across sessions.

    MemoryManager handles:
    - Long-term memory persistence
    - Short-term memory with TTL
    - Cross-session memory retrieval
    - Memory consolidation and cleanup
    """

    def __init__(self, data_dir: Path | str) -> None:
        """Initialize MemoryManager.

        Args:
            data_dir: Base directory for memory storage
        """
        self.data_dir = Path(data_dir)

        # Memory directories
        self.context_dir = self.data_dir / "memory" / "context"
        self.long_term_dir = self.data_dir / "memory" / "long_term"
        self.semantic_dir = self.data_dir / "memory" / "semantic"

        for dir_path in [self.context_dir, self.long_term_dir, self.semantic_dir]:
            dir_path.mkdir(parents=True, exist_ok=True)

        # In-memory caches
        self._session_memories: dict[str, ContextMemory] = {}
        self._long_term_entries: dict[str, MemoryEntry] = {}

        # Load long-term memory index
        self._load_long_term_index()

    def _load_long_term_index(self) -> None:
        """Load long-term memory index from disk."""
        index_path = self.long_term_dir / "_index.yaml"
        if index_path.exists():
            with open(index_path) as f:
                index_data = yaml.safe_load(f) or {}
                for entry_id in index_data.get("entries", []):
                    entry = self._load_long_term_entry(entry_id)
                    if entry:
                        self._long_term_entries[entry_id] = entry

    def _save_long_term_index(self) -> None:
        """Save long-term memory index to disk."""
        index_path = self.long_term_dir / "_index.yaml"
        index_data = {
            "updated_at": datetime.now().isoformat(),
            "entries": list(self._long_term_entries.keys()),
        }
        with open(index_path, "w") as f:
            yaml.safe_dump(index_data, f, allow_unicode=True)

    # === Session Memory ===

    def get_session_memory(self, session_id: str) -> ContextMemory | None:
        """Get memory for a specific session.

        Args:
            session_id: Session ID

        Returns:
            ContextMemory or None if not found
        """
        if session_id in self._session_memories:
            return self._session_memories[session_id]

        # Try loading from disk
        path = self.context_dir / f"{session_id}.yaml"
        if path.exists():
            with open(path) as f:
                data = yaml.safe_load(f)
            memory = ContextMemory.model_validate(data)
            self._session_memories[session_id] = memory
            return memory

        return None

    def create_session_memory(self, session_id: str) -> ContextMemory:
        """Create memory for a new session.

        Args:
            session_id: Session ID

        Returns:
            Created ContextMemory
        """
        memory = ContextMemory(
            memory_id=f"memory-{session_id}",
            session_id=session_id,
        )
        self._session_memories[session_id] = memory
        self._save_session_memory(memory)
        return memory

    def _save_session_memory(self, memory: ContextMemory) -> None:
        """Save session memory to disk."""
        path = self.context_dir / f"{memory.session_id}.yaml"
        data = memory.model_dump(mode="json")
        with open(path, "w") as f:
            yaml.safe_dump(data, f, allow_unicode=True, sort_keys=False)

    # === Memory Operations ===

    def store(
        self,
        session_id: str,
        key: str,
        value: Any,
        memory_type: MemoryType = MemoryType.SHORT_TERM,
        scope: MemoryScope = MemoryScope.SESSION,
        summary: str = "",
        source: str = "",
        ttl_hours: int | None = None,
        **metadata: Any,
    ) -> str:
        """Store a memory entry.

        Args:
            session_id: Session ID
            key: Lookup key
            value: Value to store
            memory_type: Type of memory
            scope: Memory scope
            summary: Human-readable summary
            source: Source of the memory
            ttl_hours: Time-to-live in hours (for short-term)
            **metadata: Additional metadata

        Returns:
            Entry ID
        """
        memory = self.get_session_memory(session_id)
        if not memory:
            memory = self.create_session_memory(session_id)

        entry_id = f"entry-{uuid.uuid4().hex[:12]}"

        expires_at = None
        if ttl_hours and memory_type == MemoryType.SHORT_TERM:
            expires_at = datetime.now() + timedelta(hours=ttl_hours)

        entry = MemoryEntry(
            entry_id=entry_id,
            memory_type=memory_type,
            scope=scope,
            key=key,
            value=value,
            summary=summary,
            session_id=session_id,
            source=source,
            expires_at=expires_at,
        )

        # Add metadata
        if metadata:
            entry.source = f"{entry.source} | {metadata}"

        memory.add_entry(entry)
        self._save_session_memory(memory)

        # Also store in long-term if applicable
        if memory_type == MemoryType.LONG_TERM:
            self._store_long_term(entry)

        return entry_id

    def retrieve(
        self,
        session_id: str,
        key: str,
    ) -> Any | None:
        """Retrieve a memory entry by key.

        Args:
            session_id: Session ID
            key: Lookup key

        Returns:
            The stored value or None
        """
        memory = self.get_session_memory(session_id)
        if not memory:
            return None

        entry = memory.get_by_key(key)
        if entry and not entry.is_expired():
            return entry.value

        # Try long-term memory
        for entry in self._long_term_entries.values():
            if entry.key == key:
                entry.access()
                return entry.value

        return None

    def search(
        self,
        session_id: str | None = None,
        keywords: list[str] | None = None,
        memory_type: MemoryType | None = None,
        scope: MemoryScope | None = None,
        limit: int = 10,
        include_long_term: bool = True,
    ) -> list[dict[str, Any]]:
        """Search memory entries.

        Args:
            session_id: Filter by session (None for cross-session)
            keywords: Keywords to match
            memory_type: Filter by type
            scope: Filter by scope
            limit: Maximum results
            include_long_term: Include long-term memory

        Returns:
            List of matching entries as dictionaries
        """
        results: list[MemoryEntry] = []

        # Search session memory
        if session_id:
            memory = self.get_session_memory(session_id)
            if memory:
                entries = memory.get_relevant_context(
                    keywords=keywords, scope=scope, limit=limit * 2
                )
                results.extend(entries)
        else:
            # Search all session memories
            for memory in self._session_memories.values():
                entries = memory.get_relevant_context(keywords=keywords, scope=scope, limit=limit)
                results.extend(entries)

        # Search long-term memory
        if include_long_term:
            for entry in self._long_term_entries.values():
                if memory_type and entry.memory_type != memory_type:
                    continue
                if scope and entry.scope != scope:
                    continue

                # Keyword matching
                if keywords:
                    entry_text = f"{entry.key} {entry.summary} {str(entry.value)}".lower()
                    if not any(kw.lower() in entry_text for kw in keywords):
                        continue

                results.append(entry)

        # Deduplicate and sort by relevance
        seen = set()
        unique_results = []
        for entry in results:
            if entry.entry_id not in seen:
                seen.add(entry.entry_id)
                unique_results.append(entry)

        unique_results.sort(key=lambda e: (e.relevance_score, e.access_count), reverse=True)

        return [
            {
                "entry_id": e.entry_id,
                "key": e.key,
                "value": e.value,
                "summary": e.summary,
                "type": e.memory_type.value,
                "scope": e.scope.value,
                "relevance": e.relevance_score,
                "session_id": e.session_id,
            }
            for e in unique_results[:limit]
        ]

    def delete(self, session_id: str, key: str) -> bool:
        """Delete a memory entry.

        Args:
            session_id: Session ID
            key: Entry key

        Returns:
            True if deleted
        """
        memory = self.get_session_memory(session_id)
        if not memory:
            return False

        entry_id = memory.by_key.get(key)
        if entry_id:
            memory.remove_entry(entry_id)
            self._save_session_memory(memory)
            return True

        return False

    # === Long-term Memory ===

    def _store_long_term(self, entry: MemoryEntry) -> None:
        """Store entry in long-term memory."""
        self._long_term_entries[entry.entry_id] = entry

        # Save to disk
        path = self.long_term_dir / f"{entry.entry_id}.yaml"
        data = entry.model_dump(mode="json")
        with open(path, "w") as f:
            yaml.safe_dump(data, f, allow_unicode=True, sort_keys=False)

        self._save_long_term_index()

    def _load_long_term_entry(self, entry_id: str) -> MemoryEntry | None:
        """Load a long-term entry from disk."""
        path = self.long_term_dir / f"{entry_id}.yaml"
        if not path.exists():
            return None
        with open(path) as f:
            data = yaml.safe_load(f)
        return MemoryEntry.model_validate(data)

    def promote_to_long_term(self, session_id: str, key: str, summary: str | None = None) -> bool:
        """Promote a short-term entry to long-term.

        Args:
            session_id: Session ID
            key: Entry key
            summary: Optional updated summary

        Returns:
            True if promoted
        """
        memory = self.get_session_memory(session_id)
        if not memory:
            return False

        entry = memory.get_by_key(key)
        if not entry:
            return False

        # Update entry
        entry.memory_type = MemoryType.LONG_TERM
        entry.scope = MemoryScope.GLOBAL
        entry.expires_at = None
        if summary:
            entry.summary = summary

        self._store_long_term(entry)
        self._save_session_memory(memory)
        return True

    # === Semantic Memory ===

    def store_semantic(
        self,
        key: str,
        value: Any,
        category: str,
        summary: str = "",
        source: str = "",
    ) -> str:
        """Store semantic (fact-based) memory.

        Semantic memory is session-independent knowledge.

        Args:
            key: Unique key for the fact
            value: The fact/knowledge
            category: Category (e.g., "project", "user", "term")
            summary: Human-readable summary
            source: Source of the knowledge

        Returns:
            Entry ID
        """
        entry_id = f"semantic-{uuid.uuid4().hex[:12]}"

        entry = MemoryEntry(
            entry_id=entry_id,
            memory_type=MemoryType.SEMANTIC,
            scope=MemoryScope.GLOBAL,
            key=key,
            value=value,
            summary=summary,
            source=source,
        )

        # Store in semantic directory by category
        category_dir = self.semantic_dir / category
        category_dir.mkdir(exist_ok=True)

        path = category_dir / f"{entry_id}.yaml"
        data = entry.model_dump(mode="json")
        with open(path, "w") as f:
            yaml.safe_dump(data, f, allow_unicode=True, sort_keys=False)

        # Also add to long-term cache for quick access
        self._long_term_entries[entry_id] = entry

        return entry_id

    def get_semantic(self, key: str, category: str | None = None) -> Any | None:
        """Get semantic memory by key.

        Args:
            key: Memory key
            category: Optional category filter

        Returns:
            The stored value or None
        """
        # Search long-term entries
        for entry in self._long_term_entries.values():
            if entry.memory_type == MemoryType.SEMANTIC and entry.key == key:
                entry.access()
                return entry.value

        # Search semantic directory
        search_dirs = [self.semantic_dir / category] if category else self.semantic_dir.iterdir()

        for search_dir in search_dirs:
            if not search_dir.is_dir():
                continue
            for path in search_dir.glob("*.yaml"):
                with open(path) as f:
                    data = yaml.safe_load(f)
                entry = MemoryEntry.model_validate(data)
                if entry.key == key:
                    self._long_term_entries[entry.entry_id] = entry
                    return entry.value

        return None

    # === Cleanup ===

    def cleanup_expired(self, session_id: str | None = None) -> int:
        """Remove expired entries.

        Args:
            session_id: Clean specific session or all if None

        Returns:
            Number of entries removed
        """
        removed = 0

        if session_id:
            memory = self.get_session_memory(session_id)
            if memory:
                removed = memory.cleanup_expired()
                self._save_session_memory(memory)
        else:
            for memory in self._session_memories.values():
                removed += memory.cleanup_expired()
                self._save_session_memory(memory)

        return removed

    def cleanup_session(self, session_id: str, keep_long_term: bool = True) -> int:
        """Clean up session memory.

        Args:
            session_id: Session to clean
            keep_long_term: Whether to preserve long-term entries

        Returns:
            Number of entries removed
        """
        memory = self.get_session_memory(session_id)
        if not memory:
            return 0

        removed = 0
        entries_to_remove = []

        for entry_id, entry in memory.entries.items():
            if keep_long_term and entry.memory_type == MemoryType.LONG_TERM:
                continue
            entries_to_remove.append(entry_id)

        for entry_id in entries_to_remove:
            if memory.remove_entry(entry_id):
                removed += 1

        self._save_session_memory(memory)
        return removed

    # === Context Building ===

    def build_context(
        self,
        session_id: str,
        keywords: list[str] | None = None,
        include_long_term: bool = True,
        include_semantic: bool = True,
        max_entries: int = 20,
    ) -> dict[str, Any]:
        """Build a context dictionary for agent use.

        Args:
            session_id: Current session ID
            keywords: Relevant keywords
            include_long_term: Include long-term memories
            include_semantic: Include semantic knowledge
            max_entries: Maximum entries to include

        Returns:
            Context dictionary
        """
        context: dict[str, Any] = {
            "session_id": session_id,
            "timestamp": datetime.now().isoformat(),
            "short_term": {},
            "long_term": {},
            "semantic": {},
        }

        # Get session memory
        memory = self.get_session_memory(session_id)
        if memory:
            # Short-term entries
            short_term = memory.get_by_type(MemoryType.SHORT_TERM)
            for entry in short_term[: max_entries // 2]:
                if not entry.is_expired():
                    context["short_term"][entry.key] = {
                        "value": entry.value,
                        "summary": entry.summary,
                    }

            # Long-term entries from session
            if include_long_term:
                long_term = memory.get_by_type(MemoryType.LONG_TERM)
                for entry in long_term[: max_entries // 4]:
                    context["long_term"][entry.key] = {
                        "value": entry.value,
                        "summary": entry.summary,
                    }

        # Add global long-term memories
        if include_long_term:
            relevant = self.search(
                keywords=keywords,
                memory_type=MemoryType.LONG_TERM,
                include_long_term=True,
                limit=max_entries // 4,
            )
            for item in relevant:
                if item["key"] not in context["long_term"]:
                    context["long_term"][item["key"]] = {
                        "value": item["value"],
                        "summary": item["summary"],
                    }

        # Add semantic knowledge
        if include_semantic:
            semantic = self.search(
                keywords=keywords,
                memory_type=MemoryType.SEMANTIC,
                include_long_term=True,
                limit=max_entries // 4,
            )
            for item in semantic:
                context["semantic"][item["key"]] = {
                    "value": item["value"],
                    "summary": item["summary"],
                }

        return context
