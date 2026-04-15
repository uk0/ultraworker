"""Facet Key utilities for the Graphless Graph architecture.

Facet keys are implicit edges in the form k/<facet>/<value>.
Required facets: who, where, what, why, how, req, step.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ultrawork.models.ltm import RequestRecord, WorkRecord

# Valid facet names
VALID_FACETS = {"who", "where", "what", "why", "how", "req", "step"}


def normalize_facet_value(value: str) -> str:
    """Convert a value to kebab-case for use in facet keys.

    Args:
        value: Raw value string

    Returns:
        Kebab-case normalized value
    """
    # Lowercase
    result = value.lower().strip()
    # Replace underscores, spaces, dots, slashes with hyphens
    result = re.sub(r"[_\s./\\]+", "-", result)
    # Remove non-alphanumeric characters except hyphens
    result = re.sub(r"[^a-z0-9\-]", "", result)
    # Collapse multiple hyphens
    result = re.sub(r"-{2,}", "-", result)
    # Strip leading/trailing hyphens
    result = result.strip("-")
    return result or "unknown"


def create_facet_key(facet: str, value: str) -> str:
    """Create a facet key in k/<facet>/<value> format.

    Args:
        facet: Facet name (e.g. "who", "what")
        value: Raw value (will be normalized to kebab-case)

    Returns:
        Formatted facet key string
    """
    normalized = normalize_facet_value(value)
    return f"k/{facet}/{normalized}"


def parse_facet_key(key: str) -> tuple[str, str]:
    """Parse a facet key into (facet, value) tuple.

    Args:
        key: Facet key string (e.g. "k/who/admin")

    Returns:
        Tuple of (facet_name, value)

    Raises:
        ValueError: If key format is invalid
    """
    if not key.startswith("k/"):
        raise ValueError(f"Invalid facet key format: {key!r}. Must start with 'k/'")
    parts = key.split("/", 2)
    if len(parts) != 3:
        raise ValueError(f"Invalid facet key format: {key!r}. Expected k/<facet>/<value>")
    return parts[1], parts[2]


def extract_facets_from_record(record: RequestRecord | WorkRecord) -> list[str]:
    """Auto-extract facet keys from a record.

    Extracts facets based on record fields:
    - who: from record.who
    - where: from record source location
    - what: from record description/actions
    - why: from hypotheses or work-why
    - how: from steps or actions
    - req: from request ID references
    - step: from step references

    Args:
        record: A RequestRecord or WorkRecord

    Returns:
        List of facet key strings
    """
    facets: list[str] = []

    # who facet
    if record.who:
        facets.append(create_facet_key("who", record.who))

    if record.type == "request":
        # RequestRecord-specific extraction
        if record.where:
            facets.append(create_facet_key("where", record.where))

        if record.what:
            # Extract key terms from what (first 3 words)
            words = record.what.split()[:3]
            if words:
                facets.append(create_facet_key("what", "-".join(words)))

        for hyp in record.why:
            if hyp.hypothesis:
                words = hyp.hypothesis.split()[:3]
                if words:
                    facets.append(create_facet_key("why", "-".join(words)))

        for step in record.how:
            facets.append(create_facet_key("step", step.step_id))
            if step.goal:
                words = step.goal.split()[:3]
                if words:
                    facets.append(create_facet_key("how", "-".join(words)))

        # Self-reference
        facets.append(create_facet_key("req", record.id))

    elif record.type == "work":
        # WorkRecord-specific extraction
        if record.where.inputs:
            for inp in record.where.inputs[:3]:
                facets.append(create_facet_key("where", inp))

        for action in record.what[:3]:
            if action.action:
                words = action.action.split()[:3]
                if words:
                    facets.append(create_facet_key("what", "-".join(words)))

        if record.why.kind:
            facets.append(create_facet_key("why", record.why.kind.value))

        if record.why.step_ref:
            # Extract request ID and step from step_ref (format: req-YYYYMMDD-NNNN#step_id)
            parts = record.why.step_ref.split("#", 1)
            req_id = parts[0]
            facets.append(create_facet_key("req", req_id))
            if len(parts) > 1:
                facets.append(create_facet_key("step", parts[1]))

    # Deduplicate while preserving order
    seen: set[str] = set()
    unique_facets: list[str] = []
    for f in facets:
        if f not in seen:
            seen.add(f)
            unique_facets.append(f)

    return unique_facets
