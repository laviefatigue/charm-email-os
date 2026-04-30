"""Shadow-validation comparison: watcher's proposed candidates vs actual graduations.

Per docs/operations/2026-04-30-deploy-runbook.md §7.4 and
apps/incubation-watcher/HANDOFF.md §6 — the acceptance criterion for
incubation-watcher cutover is 7 consecutive days of zero divergence
between what the watcher would propose and what the existing
sync_modules/lifecycle_tag_sync actually graduates.

This module computes that diff for one workspace. Operator runs it daily
during the validation window. Any non-empty `watcher_only` or `actual_only`
set is a divergence that warrants investigation BEFORE any cutover.

Pure-set comparison; no EB calls; no DB writes.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

import asyncpg


@dataclass(frozen=True)
class ShadowComparison:
    """Set-difference result for a single workspace + window."""
    workspace_name: str
    since: datetime
    proposed_emails: frozenset[str]   # what the watcher would graduate NOW
    actual_emails: frozenset[str]     # what existing module actually graduated since `since`

    @property
    def matched(self) -> frozenset[str]:
        return self.proposed_emails & self.actual_emails

    @property
    def watcher_only(self) -> frozenset[str]:
        """Watcher proposed, but existing module did NOT graduate. Divergence."""
        return self.proposed_emails - self.actual_emails

    @property
    def actual_only(self) -> frozenset[str]:
        """Existing module graduated, but watcher did NOT propose. Divergence."""
        return self.actual_emails - self.proposed_emails

    @property
    def has_divergence(self) -> bool:
        return bool(self.watcher_only or self.actual_only)


async def fetch_actual_graduations(
    conn: asyncpg.Connection,
    workspace_id: UUID,
    since: datetime,
) -> frozenset[str]:
    """Pull the email set that the existing `lifecycle_tag_sync` actually
    graduated for the given workspace since the cutoff.

    The query filters on `triggered_by` so we only see graduations from the
    existing module — not from this watcher (when it eventually runs in
    --apply mode). During shadow validation, the watcher is in --apply=False
    mode so it never appears in rotation_history. After cutover, this
    filter prevents counting the watcher's own writes.
    """
    rows = await conn.fetch(
        """
        SELECT DISTINCT target_inbox_email
        FROM inbox_rotation_history
        WHERE workspace_id = $1
          AND rotation_type = 'graduate'
          AND triggered_by = 'lifecycle_tag_sync'
          AND executed_at >= $2
        """,
        workspace_id,
        since,
    )
    return frozenset(r["target_inbox_email"] for r in rows)


def render_comparison(comp: ShadowComparison) -> list[str]:
    """Format the comparison for stdout. Caller prints lines."""
    lines: list[str] = []
    lines.append(f"workspace={comp.workspace_name}")
    lines.append(f"since={comp.since.isoformat()}")
    lines.append("")
    lines.append(f"proposed (by watcher, RIGHT NOW):    {len(comp.proposed_emails)}")
    lines.append(f"actual   (by existing module):       {len(comp.actual_emails)}")
    lines.append(f"matched  (both proposed AND actual): {len(comp.matched)}")
    lines.append("")

    if comp.watcher_only:
        lines.append(
            f"DIVERGENCE: {len(comp.watcher_only)} inbox(es) proposed by watcher "
            f"but NOT graduated by existing module:"
        )
        for email in sorted(comp.watcher_only):
            lines.append(f"  - watcher_only: {email}")
        lines.append("")

    if comp.actual_only:
        lines.append(
            f"DIVERGENCE: {len(comp.actual_only)} inbox(es) graduated by existing "
            f"module but NOT proposed by watcher:"
        )
        for email in sorted(comp.actual_only):
            lines.append(f"  - actual_only:  {email}")
        lines.append("")

    if not comp.has_divergence:
        lines.append("RESULT: zero divergence — proposed == actual.")
    else:
        lines.append("RESULT: divergence detected. Investigate BEFORE any cutover.")

    return lines
