"""
Workspace Write Orchestrator

Runs DB→EB write operations (lifecycle tagging, set tagging, kill processing)
per workspace, concurrently across workspaces, using workspace-scoped API keys.

Architecture
────────────
For each active workspace with a valid entry in workspace_api_keys:
    client = EmailBisonClient(api_key=ws.key_token, is_workspace_scoped=True)
    await lifecycle_tag_sync.sync_workspace_tags(...)   ┐
    await set_tag_sync.sync_workspace_sets(...)         │ sequential within ws
    await kill_processor.process_workspace_queue(...)   ┘

Workspaces are processed concurrently via asyncio.Semaphore(concurrency).

Why a separate orchestrator and not WorkspaceSyncQueue
──────────────────────────────────────────────────────
WorkspaceSyncQueue is for data-pull jobs (EB → DB) that are independently
orderable. Tag/kill writes have a strict intra-workspace ordering invariant:
lifecycle_tag_sync graduates inboxes → set_tag_sync allocates pool tags →
kill_processor finalizes flagged inboxes. Mixing the two queues would lose
that ordering guarantee.

Why workspace-scoped API keys
─────────────────────────────
Before migration 089, every write call required a `switch_workspace()` API
hit on a single shared client. That serialized all workspaces and was the
source of context-race bugs (a switch failing silently, the next call
landing in the wrong workspace, dual-tagged inboxes). With workspace-scoped
keys, the API token carries workspace context — no switch needed, safe
concurrent execution.
"""
import asyncio
import logging
from typing import List, Optional
from uuid import UUID

import asyncpg

from .audit_logger import AuditLogger, SyncResult
from .emailbison_client import EmailBisonClient
from .kill_processor import KillProcessor
from .lifecycle_tag_sync import LifecycleTagSyncModule
from .pool_promotion import (
    count_pool_state,
    pick_promotion_candidates,
    promote_inbox_to_deployed,
)
from .set_tag_sync import SetTagSyncModule
from .slack_alerter import SlackAlerter

logger = logging.getLogger(__name__)


class WorkspaceWriteOrchestrator:
    """
    Concurrent per-workspace driver for tag and kill writes.

    Args:
        db:           shared asyncpg pool
        audit_logger: shared audit logger
        alerter:      shared Slack alerter
        concurrency:  max workspaces running simultaneously (default 3)
    """

    def __init__(
        self,
        db: asyncpg.Pool,
        audit_logger: AuditLogger,
        alerter: Optional[SlackAlerter] = None,
        concurrency: int = 3,
        enable_lifecycle_tagging: bool = True,
        enable_kill_processing: bool = True,
    ):
        self.db = db
        self.audit_logger = audit_logger
        self.alerter = alerter or SlackAlerter()
        self.concurrency = concurrency
        # Phase-level kill switches — match the legacy worker env flags
        # (ENABLE_LIFECYCLE_TAGGING, ENABLE_KILL_PROCESSING) so operators can
        # disable a phase without redeploying. The "set tagging" phase is
        # bundled with lifecycle because they share a write-ordering invariant.
        self.enable_lifecycle_tagging = enable_lifecycle_tagging
        self.enable_kill_processing = enable_kill_processing

    async def run(self) -> List[SyncResult]:
        """
        Run lifecycle → set → kill for every active workspace with a valid API key.

        Workspaces missing a key are skipped (logged once per session at startup
        by WorkspaceSyncQueue.log_missing_keys()). Workspaces that fail one phase
        do not block siblings — exceptions are captured per-task.
        """
        workspaces = await self._load_active_workspaces_with_keys()

        if not workspaces:
            logger.debug("[WorkspaceWrites] No workspaces with active API keys; skipping run")
            return []

        semaphore = asyncio.Semaphore(self.concurrency)
        tasks = [self._run_workspace(ws, semaphore) for ws in workspaces]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        sync_results: List[SyncResult] = []
        for i, r in enumerate(results):
            if isinstance(r, Exception):
                ws = workspaces[i]
                logger.error(
                    "[WorkspaceWrites] Unhandled exception for workspace %s (%s): %s",
                    ws['workspace_name'], ws['id'], r,
                    exc_info=r,
                )
                if self.alerter:
                    try:
                        await self.alerter.alert_sync_failure(
                            module='workspace_writes',
                            error=str(r),
                            workspace=ws['workspace_name'],
                        )
                    except Exception:
                        pass
            elif r is not None:
                sync_results.extend(r)

        return sync_results

    async def _load_active_workspaces_with_keys(self) -> List[asyncpg.Record]:
        """
        Fetch every active workspace that has a usable workspace-scoped API key.

        Workspaces without a key are silently excluded — log_missing_keys() at
        startup is the discoverability surface for that condition. We do not
        want this orchestrator to alert on missing keys every cycle.

        Also pulls package configuration so the threshold-maintenance phase
        can compute deficits without a second query per workspace.
        """
        return await self.db.fetch("""
            SELECT
                w.id,
                w.workspace_name,
                w.emailbison_workspace_id,
                w.a_set_tag_name,
                w.b_set_tag_name,
                w.package_id,
                w.target_live_count_override,
                w.pause_pool_transitions,
                p.target_live_count        AS package_live_target,
                p.target_reserve_count     AS package_reserve_minimum,
                wak.key_token
            FROM workspaces w
            JOIN workspace_api_keys wak
                ON wak.workspace_id = w.id
                AND wak.is_active = TRUE
            LEFT JOIN workspace_packages p
                ON p.id = w.package_id
            WHERE w.is_active = TRUE
              AND w.emailbison_workspace_id IS NOT NULL
            ORDER BY w.workspace_name
        """)

    async def _run_workspace(
        self,
        ws: asyncpg.Record,
        semaphore: asyncio.Semaphore,
    ) -> List[SyncResult]:
        """
        Build a workspace-scoped client and run lifecycle → set → kill in order.

        Phase failures inside a workspace do not stop the next phase from
        running: each phase is wrapped so a lifecycle hiccup does not block
        kill processing for that workspace, and a kill hiccup never reverts
        a successful tag pass. Each phase produces its own SyncResult.
        """
        async with semaphore:
            workspace_id: UUID = ws['id']
            workspace_name: str = ws['workspace_name']
            eb_workspace_id: int = int(ws['emailbison_workspace_id'])
            a_tag_name: Optional[str] = ws.get('a_set_tag_name')
            b_tag_name: Optional[str] = ws.get('b_set_tag_name')
            key_token: str = ws['key_token']

            results: List[SyncResult] = []

            async with EmailBisonClient(
                api_key=key_token,
                is_workspace_scoped=True,
            ) as client:
                # PHASE A: lifecycle tagging — incubating → live/reserve, dead cleanup
                if self.enable_lifecycle_tagging:
                    try:
                        lifecycle = LifecycleTagSyncModule(
                            db=self.db, client=client,
                            audit_logger=self.audit_logger, alerter=self.alerter,
                        )
                        res = await lifecycle.sync_workspace_tags(
                            workspace_id=workspace_id,
                            workspace_name=workspace_name,
                            emailbison_workspace_id=eb_workspace_id,
                        )
                        results.append(res)
                    except Exception as e:
                        logger.error(
                            "[WorkspaceWrites:%s] lifecycle phase failed: %s",
                            workspace_name, e, exc_info=True,
                        )

                # PHASE A2: pool threshold maintenance (proactive promotion).
                # Honors:
                #   - workspace.pause_pool_transitions: skip entirely if TRUE
                #   - workspace.package_id: NULL means no proactive promotion
                #     (the workspace is purely reactive to kills, current behavior)
                #   - workspace.target_live_count_override: caps the package default
                # Runs BEFORE set_tag_sync so any DB changes from this phase get
                # reconciled to EB tags in the same cycle.
                if (
                    self.enable_lifecycle_tagging
                    and ws.get('package_id') is not None
                    and not ws.get('pause_pool_transitions', False)
                ):
                    try:
                        await self._maintain_pool_thresholds(ws)
                    except Exception as e:
                        logger.error(
                            "[WorkspaceWrites:%s] threshold maintenance failed: %s",
                            workspace_name, e, exc_info=True,
                        )
                elif (
                    self.enable_lifecycle_tagging
                    and ws.get('package_id') is None
                ):
                    # No package = no proactive promotion. Pre-2026-05-05 this
                    # was a silent skip — Charm sat with 45 graduated reserves
                    # idle for 6 months because no signal fired. Surface the
                    # condition: count graduated Gmail reserves; if > 0, log
                    # so the operator sees there's latent capacity stuck
                    # behind the missing package config.
                    try:
                        await self._warn_if_latent_capacity_stalled(ws)
                    except Exception as e:
                        logger.warning(
                            "[WorkspaceWrites:%s] latent-capacity check failed: %s",
                            workspace_name, e,
                        )

                # PHASE B: set tagging — per-inbox pool reconciliation. Bundled
                # with lifecycle: if lifecycle is disabled we also skip set tags
                # because the new graduations they coordinate would be inconsistent.
                if self.enable_lifecycle_tagging:
                    try:
                        set_tags = SetTagSyncModule(
                            db=self.db, client=client,
                            audit_logger=self.audit_logger, alerter=self.alerter,
                        )
                        res = await set_tags.sync_workspace_sets(
                            workspace_id=workspace_id,
                            workspace_name=workspace_name,
                            emailbison_workspace_id=eb_workspace_id,
                            a_set_tag_name=a_tag_name,
                            b_set_tag_name=b_tag_name,
                        )
                        results.append(res)
                    except Exception as e:
                        logger.error(
                            "[WorkspaceWrites:%s] set tagging phase failed: %s",
                            workspace_name, e, exc_info=True,
                        )

                # PHASE C: kill processing — must run AFTER tagging so newly
                # graduated inboxes are not picked up before pool allocation
                if self.enable_kill_processing:
                    try:
                        kill = KillProcessor(
                            db=self.db, client=client,
                            audit_logger=self.audit_logger, alerter=self.alerter,
                        )
                        res = await kill.process_workspace_queue(
                            workspace_id=workspace_id,
                            workspace_name=workspace_name,
                        )
                        results.append(res)
                    except Exception as e:
                        logger.error(
                            "[WorkspaceWrites:%s] kill phase failed: %s",
                            workspace_name, e, exc_info=True,
                        )

            return results

    async def _warn_if_latent_capacity_stalled(self, ws: asyncpg.Record) -> None:
        """
        For workspaces without a package_id assigned, surface latent-capacity
        stalls so the operator sees that reserves are sitting idle behind a
        config gap.

        A "stalled reserve" is a Gmail inbox that:
          - is_active = TRUE
          - inbox_state = 'live'
          - inventory_pool_status = 'reserve'
          - inventory_lifecycle_status = 'active' (graduated, not still in incubation)
          - status = 'Connected'
          - graduated more than the visibility threshold ago

        We log at WARNING level when stalled count > 0. We do NOT alert via
        Slack — the operator decision is "do you want a package on this
        workspace" and that's a one-time config call, not an every-cycle
        alarm. Polluting the Slack alert channel would teach operators to
        ignore it.

        Pre-2026-05-05 this was a silent skip; Charm sat with 45 graduated
        Gmail reserves idle for ~6 months because no signal fired. See
        docs/work-logs/2026-05-04-kill-rule-rate-rewrite-and-revival.md
        for the broader context (the rule rewrite pulled this gap to the
        surface as part of the fleet audit).
        """
        workspace_id = ws['id']
        workspace_name = ws['workspace_name']

        row = await self.db.fetchrow("""
            SELECT
                COUNT(*) FILTER (
                    WHERE sa.inventory_pool_status = 'reserve'
                ) AS stalled_reserves,
                COUNT(*) FILTER (
                    WHERE sa.inventory_pool_status = 'live'
                ) AS current_live
            FROM sender_accounts sa
            WHERE sa.workspace_id = $1
              AND sa.esp = 'gmail'
              AND sa.is_active = TRUE
              AND sa.inbox_state = 'live'
              AND sa.status = 'Connected'
              AND sa.inventory_lifecycle_status = 'active'
        """, workspace_id)

        if not row:
            return

        stalled = int(row['stalled_reserves'] or 0)
        live = int(row['current_live'] or 0)
        if stalled <= 0:
            return

        logger.warning(
            "[WorkspaceWrites:%s] latent-capacity stall: %d graduated Gmail "
            "reserves idle (current_live=%d). No package_id set on workspace, "
            "so _maintain_pool_thresholds doesn't run. Either assign a "
            "workspace_packages row, or set target_live_count_override to "
            "lock the active count and acknowledge the reserves as a buffer.",
            workspace_name, stalled, live,
        )

    async def _maintain_pool_thresholds(self, ws: asyncpg.Record) -> None:
        """
        Proactive promotion to maintain the workspace's contracted live capacity.

        Algorithm:
          1. effective_live_target = override if set, else package default
          2. current_live = count of Google deployed Connected inboxes
          3. deficit = effective_live_target - current_live
          4. If deficit > 0: pick `deficit` candidates via the domain-aware
             selector and promote them (sets inventory_pool_status='live'
             plus an inbox_rotation_history row each).
          5. Reserve runway alert: if current_reserve < package.target_reserve_count,
             post a Slack note. We do NOT freeze promotion to protect reserve —
             that would actively harm capacity to protect a buffer, which is
             the wrong tradeoff. The alert is the signal to order more domains.

        Lower-override behavior: this method is one-way. Lowering the override
        from 150 → 100 does NOT demote currently-deployed inboxes. Natural
        attrition (kills) eventually brings the count to the new target. This
        protects sender reputation that's already established.
        """
        workspace_id = ws['id']
        workspace_name = ws['workspace_name']

        package_live = ws.get('package_live_target')
        package_reserve_min = ws.get('package_reserve_minimum')
        override = ws.get('target_live_count_override')

        if package_live is None:
            return  # belt-and-suspenders; caller already filtered

        effective_live_target = override if override is not None else package_live

        current_live = await count_pool_state(
            self.db, workspace_id, 'live', esp='gmail'
        )
        current_reserve = await count_pool_state(
            self.db, workspace_id, 'reserve', esp='gmail'
        )

        # Reserve runway alert (one-way alert — does not block promotion).
        if (
            package_reserve_min is not None
            and current_reserve < package_reserve_min
            and self.alerter
        ):
            try:
                await self.alerter.send_alert(
                    level="warning",
                    title=f"Reserve runway low: {workspace_name}",
                    message=(
                        f"Google reserve count {current_reserve} is below "
                        f"package minimum {package_reserve_min}. Consider "
                        f"ordering more Google domains via HyperTide, or lower "
                        f"`target_live_count_override` to keep more inboxes on "
                        f"the bench."
                    ),
                    context={
                        'workspace_id': str(workspace_id),
                        'workspace_name': workspace_name,
                        'current_reserve': current_reserve,
                        'package_reserve_minimum': package_reserve_min,
                    },
                )
            except Exception as e:
                logger.warning("[WorkspaceWrites:%s] reserve alert failed: %s",
                               workspace_name, e)

        deficit = effective_live_target - current_live
        if deficit <= 0:
            return  # at or above target — nothing to do

        candidates = await pick_promotion_candidates(self.db, workspace_id, deficit)
        if not candidates:
            # Deficit exists but no candidates — runway is exhausted.
            # The reserve alert above already fired if we're below minimum.
            logger.warning(
                "[WorkspaceWrites:%s] threshold deficit=%d but no promotable reserves",
                workspace_name, deficit,
            )
            if self.alerter:
                try:
                    await self.alerter.send_alert(
                        level="critical",
                        title=f"Live capacity deficit, no promotable reserves: {workspace_name}",
                        message=(
                            f"Need to promote {deficit} more inboxes to reach "
                            f"effective_live_target={effective_live_target}, but "
                            f"no eligible reserve inboxes are available. Workspace "
                            f"is below contracted capacity."
                        ),
                        context={
                            'workspace_id': str(workspace_id),
                            'workspace_name': workspace_name,
                            'effective_live_target': effective_live_target,
                            'current_live': current_live,
                            'deficit': deficit,
                            'current_reserve': current_reserve,
                        },
                    )
                except Exception as e:
                    logger.warning("[WorkspaceWrites:%s] deficit alert failed: %s",
                                   workspace_name, e)
            return

        promoted = 0
        for c in candidates:
            ok = await promote_inbox_to_deployed(
                db=self.db,
                inbox_id=c['id'],
                workspace_id=workspace_id,
                reason=(
                    f"threshold_maintenance: live={current_live}+{promoted+1} "
                    f"target={effective_live_target}, "
                    f"source domain={c['domain_name']} "
                    f"(deployed_count={c['deployed_count']}, "
                    f"reserve_count={c['reserve_count']})"
                ),
                triggered_by='orchestrator',
                rotation_type='threshold_promotion',
                metadata={
                    'effective_live_target': effective_live_target,
                    'current_live_before': current_live,
                    'deficit': deficit,
                    'source_domain': c['domain_name'],
                    'source_domain_deployed_count': c['deployed_count'],
                    'source_domain_reserve_count': c['reserve_count'],
                },
            )
            if ok:
                promoted += 1

        if promoted > 0:
            logger.info(
                "[WorkspaceWrites:%s] promoted %d/%d (target=%d, was %d, reserve runway %d)",
                workspace_name, promoted, deficit,
                effective_live_target, current_live, current_reserve,
            )
