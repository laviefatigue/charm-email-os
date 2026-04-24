"""
Typed snapshots for Day.AI objects we care about.

Keep these minimal — only fields the watcher + future automations actively
consume. The raw `properties` dict is always preserved on each snapshot for
audit/replay and for fields we haven't typed yet.

Day.AI nests most fields under `properties`; top-level has objectId, title,
relationships, createdAt, updatedAt. Some fields (like stageId) live under
properties. Normalization flattens the fields we care about while keeping the
raw nested structure.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class OpportunitySnapshot:
    """Flat view of a Day.AI opportunity. `raw` holds the full original object."""

    id: str
    title: str | None = None
    stage_id: str | None = None
    domain: str | None = None
    amount: float | None = None
    expected_close_date: str | None = None
    timeframe_end: str | None = None
    pipeline_id: str | None = None
    organization_id: str | None = None
    raw: dict[str, Any] = field(default_factory=dict)

    def to_jsonb(self) -> dict[str, Any]:
        """Shape used for the dayai_snapshot JSONB column in dayai_watcher_state."""
        return self.raw


def normalize_opportunity(raw: dict[str, Any]) -> OpportunitySnapshot:
    """
    Build an OpportunitySnapshot from a raw Day.AI opportunity object.

    Mirrors the normalize() function in the Node watcher (src/dayai.ts) so the
    behavior is identical and migration 093's dayai_snapshot column stays
    semantically consistent.
    """
    props = raw.get("properties") or {}

    def pick(key: str) -> Any:
        if key in raw:
            return raw[key]
        return props.get(key)

    def as_str(v: Any) -> str | None:
        return str(v) if v is not None else None

    def as_float(v: Any) -> float | None:
        if v is None:
            return None
        try:
            return float(v)
        except (TypeError, ValueError):
            return None

    object_id = raw.get("objectId") or raw.get("id")
    if not object_id:
        raise ValueError(
            f"Day.AI opportunity missing objectId/id: keys={list(raw.keys())[:10]}"
        )

    return OpportunitySnapshot(
        id=str(object_id),
        title=as_str(pick("title")),
        stage_id=as_str(pick("stageId")),
        domain=as_str(pick("domain")),
        amount=as_float(pick("amount")),
        expected_close_date=as_str(pick("expectedCloseDate")),
        timeframe_end=as_str(pick("timeframeEnd")),
        pipeline_id=as_str(pick("pipelineId")),
        organization_id=as_str(pick("organizationId")),
        raw=raw,
    )
