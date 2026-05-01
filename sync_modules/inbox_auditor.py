"""
Inbox Auditor — per-workspace audit producer (Plan: inbox-audit-overhaul.md).

Phase 2 + 3 of the inbox-audit-overhaul.

Generates a structured per-workspace audit row in `inbox_audits` with:
  - workspace_id (S-1: per-workspace scope)
  - inbox_id_set JSONB (S-2: which inboxes were in scope)
  - audit_data JSONB containing the integrity sections:
       I-1: Cross-workspace pollution (quarantined inboxes)
       I-2: Stuck-in-incubation past 14 business days
       I-3: Workspace-orphan rows (last_synced > 7 days)
       I-4: Lifecycle_tag_sync staleness (not running per workspace)
       I-5: Pool-eligibility lockout (quarantined_inbox_count)
       I-6: Promotion-blocked-by-connection (reserve + disconnected)
       I-7: Cap-exceeded (live count > target_live_count_override)
       I-9 / S-3: Subscription-cancel candidates (all-dead domains)

Deliberately NOT included:
  I-8: Pool-tag drift (DB pool ≠ EB tag) — requires EB API calls.
       Add later as a separate code path or run alongside set_tag_sync.

CONSTRAINT (per D-M):
This module operates on data we already sync from EmailBison via
sync_accounts + sync_events. It does NOT make EB API calls. No
out-of-band signal sources (JMRP, Postmaster Tools) are available, so
all integrity sections key off DB state — which IS the response-parsing
output of EB.

Usage (from operator-facing CLI in scripts/run_inbox_audit.py):
    auditor = InboxAuditor(db)
    result = await auditor.audit_workspace(workspace_id)
    print(result.summary())
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import UUID

import asyncpg


@dataclass
class AuditSection:
    """One integrity section of the per-workspace audit."""
    code: str             # e.g., "I-1"
    name: str             # e.g., "Cross-workspace pollution"
    severity: str         # 'info' | 'warn' | 'critical'
    count: int
    sample_ids: List[str] = field(default_factory=list)  # up to 10 sender_account UUIDs
    details: Dict[str, Any] = field(default_factory=dict)


@dataclass
class WorkspaceAuditResult:
    """Per-workspace audit result, persisted as one row in inbox_audits."""
    workspace_id: UUID
    workspace_name: str
    audit_date: str  # ISO date
    total_inboxes: int
    inbox_id_set: List[str]  # all in-scope sender_account UUIDs (active inboxes)
    sections: List[AuditSection]

    def to_audit_data(self) -> Dict[str, Any]:
        """Serialize sections + summary into the audit_data JSONB shape."""
        return {
            'workspace_name': self.workspace_name,
            'audit_date': self.audit_date,
            'total_inboxes': self.total_inboxes,
            'sections': [asdict(s) for s in self.sections],
            'critical_count': sum(1 for s in self.sections if s.severity == 'critical'),
            'warn_count': sum(1 for s in self.sections if s.severity == 'warn'),
            'generated_at': datetime.now(timezone.utc).isoformat(),
        }

    def summary(self) -> str:
        """Human-readable single-line summary."""
        critical = sum(1 for s in self.sections if s.severity == 'critical' and s.count > 0)
        warn = sum(1 for s in self.sections if s.severity == 'warn' and s.count > 0)
        return (
            f"[{self.workspace_name}] {self.total_inboxes} inboxes audited; "
            f"{critical} critical / {warn} warn / "
            f"{len(self.sections) - critical - warn} clean sections"
        )


class InboxAuditor:
    """Produces and persists per-workspace inbox audits."""

    def __init__(self, db: asyncpg.Pool):
        self.db = db

    async def audit_workspace(self, workspace_id: UUID) -> WorkspaceAuditResult:
        """Run the full audit suite for one workspace, return structured result.

        Does NOT persist — caller decides via persist().
        """
        async with self.db.acquire() as conn:
            ws_row = await conn.fetchrow(
                "SELECT id, workspace_name, target_live_count_override "
                "FROM workspaces WHERE id = $1",
                workspace_id,
            )
            if ws_row is None:
                raise ValueError(f"workspace {workspace_id} not found")

            workspace_name = ws_row['workspace_name']
            target_live_override = ws_row['target_live_count_override']

            inbox_set = await self._fetch_inbox_id_set(conn, workspace_id)

            sections = []
            sections.append(await self._audit_i1_cross_workspace_pollution(conn, workspace_id))
            sections.append(await self._audit_i2_stuck_in_incubation(conn, workspace_id))
            sections.append(await self._audit_i3_workspace_orphans(conn, workspace_id))
            sections.append(await self._audit_i4_lifecycle_sync_stale(conn, workspace_id))
            sections.append(await self._audit_i5_quarantined_count(conn, workspace_id))
            sections.append(await self._audit_i6_promotion_blocked(conn, workspace_id))
            sections.append(await self._audit_i7_cap_exceeded(conn, workspace_id, target_live_override))
            sections.append(await self._audit_i9_subscription_cancel(conn, workspace_id))

        return WorkspaceAuditResult(
            workspace_id=workspace_id,
            workspace_name=workspace_name,
            audit_date=datetime.now(timezone.utc).date().isoformat(),
            total_inboxes=len(inbox_set),
            inbox_id_set=inbox_set,
            sections=sections,
        )

    async def persist(self, result: WorkspaceAuditResult) -> int:
        """Insert the audit result as a row in inbox_audits. Returns the row id.

        One row per workspace per audit_date. Re-running for the same
        workspace+date returns the existing id (idempotent).
        """
        existing = await self.db.fetchval(
            "SELECT id FROM inbox_audits WHERE workspace_id = $1 AND audit_date = $2::date",
            result.workspace_id, result.audit_date,
        )
        if existing:
            await self.db.execute(
                """
                UPDATE inbox_audits
                SET inbox_id_set = $2,
                    audit_data = $3,
                    total_kills = $4,
                    total_disconnected = $5,
                    updated_at = NOW()
                WHERE id = $1
                """,
                existing,
                json.dumps(result.inbox_id_set),
                json.dumps(result.to_audit_data()),
                self._count_critical_inboxes(result),
                self._count_disconnected_inboxes_in_scope(result),
            )
            return existing

        return await self.db.fetchval(
            """
            INSERT INTO inbox_audits (
                workspace_id, audit_date, inbox_id_set, audit_data,
                status, total_kills, total_disconnected
            ) VALUES ($1, $2::date, $3, $4, 'pending', $5, $6)
            RETURNING id
            """,
            result.workspace_id,
            result.audit_date,
            json.dumps(result.inbox_id_set),
            json.dumps(result.to_audit_data()),
            self._count_critical_inboxes(result),
            self._count_disconnected_inboxes_in_scope(result),
        )

    @staticmethod
    def _count_critical_inboxes(result: WorkspaceAuditResult) -> int:
        for s in result.sections:
            if s.code == 'I-1':
                return s.count
        return 0

    @staticmethod
    def _count_disconnected_inboxes_in_scope(result: WorkspaceAuditResult) -> int:
        for s in result.sections:
            if s.code == 'I-6':
                return s.count
        return 0

    # ──────────────────────────────────────────────────────────────────
    # Helpers
    # ──────────────────────────────────────────────────────────────────

    async def _fetch_inbox_id_set(
        self, conn: asyncpg.Connection, workspace_id: UUID
    ) -> List[str]:
        rows = await conn.fetch(
            "SELECT id::text AS id FROM sender_accounts "
            "WHERE workspace_id = $1 AND is_active = TRUE",
            workspace_id,
        )
        return [r['id'] for r in rows]

    @staticmethod
    def _sample(rows: List[asyncpg.Record], key: str = 'id', limit: int = 10) -> List[str]:
        return [str(r[key]) for r in rows[:limit]]

    # ──────────────────────────────────────────────────────────────────
    # Integrity sections — each returns an AuditSection
    # ──────────────────────────────────────────────────────────────────

    async def _audit_i1_cross_workspace_pollution(
        self, conn: asyncpg.Connection, workspace_id: UUID
    ) -> AuditSection:
        """I-1: Foreign inboxes that hold pool tags = cross-tenant leak risk.

        Post-firewall (Plan A), foreign inboxes are quarantined and pool=NULL
        is enforced by chk_quarantined_no_pool. This audit detects any rows
        that bypassed the firewall (which should be impossible given the
        CHECK constraint, but defense-in-depth surfaces violations loudly).
        """
        rows = await conn.fetch(
            """
            SELECT id::text AS id, email_address, inventory_pool_status
            FROM sender_accounts
            WHERE workspace_id = $1
              AND is_active = TRUE
              AND is_quarantined = TRUE
              AND inventory_pool_status IS NOT NULL
            """,
            workspace_id,
        )
        # If any row matches, the CHECK constraint was bypassed — major problem.
        return AuditSection(
            code='I-1',
            name='Cross-workspace pollution (foreign + pool-tagged)',
            severity='critical' if rows else 'info',
            count=len(rows),
            sample_ids=self._sample(rows),
            details={
                'expected': 0,
                'note': 'Post-firewall this should always be 0. Non-zero = chk_quarantined_no_pool was bypassed.',
            },
        )

    async def _audit_i2_stuck_in_incubation(
        self, conn: asyncpg.Connection, workspace_id: UUID
    ) -> AuditSection:
        """I-2: Inboxes still in incubating after 14+ business days elapsed.

        These are eligible for graduation but haven't graduated. Either the
        graduation flow stopped working, or the row has a state issue.
        """
        rows = await conn.fetch(
            """
            SELECT id::text AS id, email_address, warmup_enabled_since,
                   (SELECT COUNT(*)
                    FROM generate_series(warmup_enabled_since::date,
                                         CURRENT_DATE - INTERVAL '1 day',
                                         INTERVAL '1 day') d
                    WHERE EXTRACT(DOW FROM d) NOT IN (0, 6))::int AS bd_elapsed
            FROM sender_accounts
            WHERE workspace_id = $1
              AND is_active = TRUE
              AND inventory_lifecycle_status = 'incubating'
              AND warmup_enabled = TRUE
              AND warmup_enabled_since IS NOT NULL
              AND inbox_state = 'live'
              AND emailbison_account_id IS NOT NULL
              AND (SELECT COUNT(*)
                   FROM generate_series(warmup_enabled_since::date,
                                        CURRENT_DATE - INTERVAL '1 day',
                                        INTERVAL '1 day') d
                   WHERE EXTRACT(DOW FROM d) NOT IN (0, 6)) >= 14
            """,
            workspace_id,
        )
        return AuditSection(
            code='I-2',
            name='Stuck in incubation past 14 business days',
            severity='warn' if rows else 'info',
            count=len(rows),
            sample_ids=self._sample(rows),
            details={
                'note': 'Eligible for graduation but lifecycle_tag_sync did not graduate. '
                        'Investigate next sync cycle or operator-graduate manually.',
            },
        )

    async def _audit_i3_workspace_orphans(
        self, conn: asyncpg.Connection, workspace_id: UUID
    ) -> AuditSection:
        """I-3: DB rows whose EB sender hasn't been synced in >7 days.

        Strong signal that the inbox was moved out of this workspace in EB
        but our DB still has the row labeled here.
        """
        rows = await conn.fetch(
            """
            SELECT id::text AS id, email_address, last_synced_at
            FROM sender_accounts
            WHERE workspace_id = $1
              AND is_active = TRUE
              AND last_synced_at < NOW() - INTERVAL '7 days'
            """,
            workspace_id,
        )
        return AuditSection(
            code='I-3',
            name='Workspace-orphan rows (last_synced > 7 days)',
            severity='warn' if rows else 'info',
            count=len(rows),
            sample_ids=self._sample(rows),
            details={
                'note': 'These rows likely belong to another EB tenant now. '
                        'Operator should audit before any state-mutating action.',
            },
        )

    async def _audit_i4_lifecycle_sync_stale(
        self, conn: asyncpg.Connection, workspace_id: UUID
    ) -> AuditSection:
        """I-4: lifecycle_tag_sync has not run successfully in >2h for this workspace.

        Phase 4 of the connection-state-machine plan calls this out:
        Sammy was processing 0 records but looked broken until investigated.
        """
        last_run = await conn.fetchval(
            """
            SELECT MAX(completed_at)
            FROM sync_audit_log
            WHERE sync_type = 'lifecycle_tags'
              AND workspace_id = $1
              AND status IN ('completed', 'partial')
            """,
            workspace_id,
        )
        # Severity threshold: warn if >2h, critical if >24h.
        if last_run is None:
            severity = 'critical'
            count = 1
            note = 'No successful lifecycle_tags sync EVER for this workspace.'
        else:
            now = datetime.now(timezone.utc)
            # last_run might be timezone-naive depending on DB col; coerce.
            if last_run.tzinfo is None:
                last_run = last_run.replace(tzinfo=timezone.utc)
            stale_minutes = (now - last_run).total_seconds() / 60
            if stale_minutes > 24 * 60:
                severity = 'critical'
                count = int(stale_minutes // 60)
                note = f'lifecycle_tags has not run in {stale_minutes/60:.1f} hours.'
            elif stale_minutes > 2 * 60:
                severity = 'warn'
                count = int(stale_minutes // 60)
                note = f'lifecycle_tags is stale ({stale_minutes/60:.1f} hours since last run).'
            else:
                severity = 'info'
                count = 0
                note = f'lifecycle_tags last ran {stale_minutes:.0f} minutes ago.'

        return AuditSection(
            code='I-4',
            name='Lifecycle_tag_sync staleness',
            severity=severity,
            count=count,
            sample_ids=[],
            details={
                'last_run_at': last_run.isoformat() if last_run else None,
                'note': note,
            },
        )

    async def _audit_i5_quarantined_count(
        self, conn: asyncpg.Connection, workspace_id: UUID
    ) -> AuditSection:
        """I-5: Pool-eligibility lockout — quarantined inbox count.

        Post-firewall metric. Quarantined inboxes are foreign-domain inboxes
        that the firewall has refused to pool-tag.
        """
        rows = await conn.fetch(
            """
            SELECT id::text AS id, email_address, quarantine_reason,
                   quarantine_detected_at::text AS detected_at
            FROM sender_accounts
            WHERE workspace_id = $1
              AND is_active = TRUE
              AND is_quarantined = TRUE
            """,
            workspace_id,
        )
        return AuditSection(
            code='I-5',
            name='Quarantined inboxes (firewall lockout)',
            severity='warn' if rows else 'info',
            count=len(rows),
            sample_ids=self._sample(rows),
            details={
                'note': 'Inboxes the firewall refused to pool-tag because email '
                        'domain does not match clients.domain_pattern.',
            },
        )

    async def _audit_i6_promotion_blocked(
        self, conn: asyncpg.Connection, workspace_id: UUID
    ) -> AuditSection:
        """I-6: Reserve inboxes blocked from promotion because they're disconnected."""
        rows = await conn.fetch(
            """
            SELECT id::text AS id, email_address, status, disconnected_at::text AS disconnected_at
            FROM sender_accounts
            WHERE workspace_id = $1
              AND is_active = TRUE
              AND inventory_pool_status = 'reserve'
              AND status = 'Not connected'
            """,
            workspace_id,
        )
        return AuditSection(
            code='I-6',
            name='Reserve inboxes blocked by disconnection',
            severity='warn' if rows else 'info',
            count=len(rows),
            sample_ids=self._sample(rows),
            details={
                'note': 'These reserves cannot be promoted to live until they reconnect. '
                        'Silent capacity loss.',
            },
        )

    async def _audit_i7_cap_exceeded(
        self, conn: asyncpg.Connection, workspace_id: UUID,
        target_live_override: Optional[int],
    ) -> AuditSection:
        """I-7: Live count > target_live_count_override (over-cap).

        Workspace target is a soft cap. Going over indicates rotation state
        drift (graduations didn't proportionally retire other live inboxes).
        """
        live_count = await conn.fetchval(
            """
            SELECT COUNT(*) FROM sender_accounts
            WHERE workspace_id = $1
              AND is_active = TRUE
              AND inventory_pool_status = 'live'
            """,
            workspace_id,
        )
        if target_live_override is None:
            return AuditSection(
                code='I-7', name='Live count vs target (override unset)',
                severity='info', count=0,
                details={'live_count': live_count, 'note': 'No target_live_count_override set.'},
            )
        excess = max(0, live_count - target_live_override)
        return AuditSection(
            code='I-7',
            name=f'Live count vs target ({live_count}/{target_live_override})',
            severity='warn' if excess > 0 else 'info',
            count=excess,
            sample_ids=[],
            details={
                'live_count': live_count,
                'target': target_live_override,
                'excess': excess,
            },
        )

    async def _audit_i9_subscription_cancel(
        self, conn: asyncpg.Connection, workspace_id: UUID
    ) -> AuditSection:
        """I-9 / S-3: Per-domain rollup — domains where 100% of inboxes are dead.

        Drives Hypertide subscription-cancellation operator queue. Per
        ADR-009 we never auto-cancel; this surfaces candidates for manual
        review.
        """
        rows = await conn.fetch(
            """
            SELECT d.id::text AS id,
                   d.domain_name,
                   COUNT(s.id) AS total_inboxes,
                   COUNT(s.id) FILTER (WHERE s.inbox_state = 'dead') AS dead_inboxes,
                   COUNT(s.id) FILTER (WHERE s.inbox_state = 'dead'
                                         AND s.status = 'Connected') AS dead_connected
            FROM domains d
            JOIN sender_accounts s ON s.domain_id = d.id
            WHERE d.workspace_id = $1
              AND d.is_active = TRUE
              AND s.is_active = TRUE
            GROUP BY d.id, d.domain_name
            HAVING COUNT(s.id) = COUNT(s.id) FILTER (WHERE s.inbox_state = 'dead')
               AND COUNT(s.id) > 0
            """,
            workspace_id,
        )
        return AuditSection(
            code='I-9',
            name='Subscription-cancel candidates (all inboxes dead)',
            severity='warn' if rows else 'info',
            count=len(rows),
            sample_ids=[r['id'] for r in rows[:10]],
            details={
                'note': 'Per-domain rollup. Operator decides whether to cancel '
                        'Hypertide subscription. Never auto-cancel (ADR-009 D-B/D-C).',
                'domains': [
                    {
                        'domain_id': r['id'],
                        'domain_name': r['domain_name'],
                        'total_inboxes': r['total_inboxes'],
                        'dead_inboxes': r['dead_inboxes'],
                        'dead_connected': r['dead_connected'],
                    }
                    for r in rows[:50]  # cap at 50 to keep JSONB row reasonable
                ],
            },
        )
