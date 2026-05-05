"""
Tag Op Worker — Tier 2 of the event-driven architecture.

Plan: docs/plans/event-driven-architecture.md § "Tier 2 — EB tag synchronization"

Purpose
───────
Drain pending `tag_op_attach` and `tag_op_remove` events from `event_log`
and apply them to EmailBison in bulk per workspace. Each workspace
processed with its own scoped EB API key (per ADR-006 — no global EB
client, ever).

Tier 1 (event_listener.py + handlers) does DB-only work. Handlers
enqueue tag_op events into event_log with status='pending' and
workspace_id set (CHECK constraint enforces). Tier 2 (this module)
flushes those events to EB in batches.

Two-tier rationale:
  - DB state is real-time (sub-second handler latency)
  - EB tag application is batched (every 30 minutes, low EB API load)
  - DB is source of truth; EB tag staleness up to 30min is acceptable
    because routing/eligibility decisions read from DB, not EB tags

Coexistence with set_tag_sync
─────────────────────────────
Both modules write tag changes to EB. They run in parallel during the
event-driven rollout (Gate 5 of the plan). This is safe because EB
tag operations are idempotent — attaching a tag that's already on an
inbox is a 200 OK no-op; same for removal.

After Gate 6 (drop state polling), set_tag_sync becomes redundant
because every state change fires triggers that produce tag_op events.
set_tag_sync code stays in the codebase but its callers are removed.

Per-workspace partitioning
──────────────────────────
- Each workspace processed with its OWN EmailBisonClient
  (workspace-scoped API key from workspace_api_keys.key_token).
- Workspace A's API key issues never block Workspace B's batch.
- Concurrency capped via SYNC_WORKSPACE_CONCURRENCY semaphore (3).
- The CHECK constraint in event_log enforces workspace_id NOT NULL on
  tag_op_* events, so the per-workspace SELECT can never miss rows.

Failure handling
────────────────
- 4xx auth/permission: mark events `failed` with retry_after; alert.
- 5xx transient: mark `failed` with retry_after backoff; watchdog
  re-emits.
- Inbox missing emailbison_account_id: just that event marked `failed`,
  others in batch proceed.
- Tag doesn't exist: get_or_create_tag creates it on demand.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple
from uuid import UUID

import asyncpg

from .audit_logger import AuditLogger, SyncResult
from .emailbison_client import EmailBisonClient, EmailBisonAPIError
from .slack_alerter import SlackAlerter

logger = logging.getLogger(__name__)


# Match the rest of the worker's per-workspace concurrency cap.
SYNC_WORKSPACE_CONCURRENCY = int(os.getenv('SYNC_WORKSPACE_CONCURRENCY', 3))

# Cap rows pulled per workspace per cycle. Higher = bigger batches but
# slower convergence on small workspaces. 500 is roughly 5 batches of
# 100 inboxes per tag — comfortably under EB rate limits.
TAG_OP_BATCH_LIMIT = int(os.getenv('TAG_OP_BATCH_LIMIT', 500))


class TagOpWorker:
    """Drains tag_op events from event_log per workspace, bulk-applies to EB.

    Usage (one cycle):
        worker = TagOpWorker(db, audit_logger, alerter)
        result = await worker.run_once()

    Usage (poll loop integration in emailbison_sync_worker.py):
        if self._should_run(self.last_tag_op_drain, POLL_INTERVAL_TAG_OP):
            await self.run_tag_op_drain()
            self.last_tag_op_drain = now
    """

    def __init__(
        self,
        db: asyncpg.Pool,
        audit_logger: AuditLogger,
        alerter: Optional[SlackAlerter] = None,
    ):
        self.db = db
        self.audit_logger = audit_logger
        self.alerter = alerter or SlackAlerter()

    async def run_once(self) -> SyncResult:
        """Drain pending tag_ops across all active workspaces.

        Concurrent over workspaces (semaphore-limited). Each workspace
        gets its own EB client + session. Workspace failures are isolated.

        Returns a SyncResult with aggregate counts.
        """
        audit = await self.audit_logger.start_audit(
            sync_type='tag_op_drain',
            metadata={'scope': 'all_workspaces'},
        )

        try:
            workspaces = await self._fetch_workspaces_with_keys()
            if not workspaces:
                return await audit.complete()

            sem = asyncio.Semaphore(SYNC_WORKSPACE_CONCURRENCY)
            results = await asyncio.gather(
                *[self._drain_workspace(ws, sem) for ws in workspaces],
                return_exceptions=True,
            )

            total_completed = 0
            total_failed = 0
            for ws, res in zip(workspaces, results):
                if isinstance(res, Exception):
                    audit.add_error(
                        record_id=ws['workspace_name'],
                        error=str(res),
                    )
                    continue
                total_completed += res.get('completed', 0)
                total_failed += res.get('failed', 0)
                if res.get('completed', 0) > 0 or res.get('failed', 0) > 0:
                    audit.increment_processed()
                if res.get('completed', 0) > 0:
                    audit.increment_updated()

            if total_completed > 0 or total_failed > 0:
                logger.info(
                    "[TagOpWorker] cycle: completed=%d failed=%d across %d workspaces",
                    total_completed, total_failed, len(workspaces),
                )

            return await audit.complete()

        except Exception as exc:
            return await audit.fail(exc)

    async def _fetch_workspaces_with_keys(self) -> List[asyncpg.Record]:
        """Active workspaces with usable workspace-scoped API keys.

        Mirrors the same query workspace_writes.py uses. Workspaces
        without a key are silently excluded (they can't have tag_ops
        either since there'd be no EB to send to).
        """
        return await self.db.fetch("""
            SELECT
                w.id,
                w.workspace_name,
                w.emailbison_workspace_id,
                wak.key_token
            FROM workspaces w
            JOIN workspace_api_keys wak
                ON wak.workspace_id = w.id
                AND wak.is_active = TRUE
            WHERE w.is_active = TRUE
              AND w.emailbison_workspace_id IS NOT NULL
            ORDER BY w.workspace_name
        """)

    async def _drain_workspace(
        self, ws: asyncpg.Record, sem: asyncio.Semaphore,
    ) -> Dict[str, int]:
        """Process pending tag_ops for one workspace under the concurrency
        semaphore. Returns {'completed': N, 'failed': M, 'skipped': K}.

        Holds an EB client for the duration of this workspace's drain.
        On any unexpected exception, marks all in-flight events as
        failed and lets the watchdog re-emit later.
        """
        async with sem:
            workspace_id = ws['id']
            workspace_name = ws['workspace_name']

            # Pull pending tag_ops for this workspace, skipping ones still
            # on retry_after backoff. ORDER BY emitted_at preserves causal
            # ordering (a kill's attach-flagged tag-op was emitted before
            # any subsequent reconnect tag-op, etc.).
            rows = await self.db.fetch(
                """
                SELECT
                    el.id              AS event_id,
                    el.event_type,
                    el.payload,
                    el.retry_count,
                    sa.id              AS inbox_id,
                    sa.email_address,
                    sa.emailbison_account_id
                FROM event_log el
                LEFT JOIN sender_accounts sa ON sa.id = el.entity_id
                WHERE el.event_type LIKE 'tag_op_%'
                  AND el.status = 'pending'
                  AND el.workspace_id = $1
                  AND (el.retry_after IS NULL OR el.retry_after < NOW())
                ORDER BY el.emitted_at
                LIMIT $2
                """,
                workspace_id, TAG_OP_BATCH_LIMIT,
            )

            if not rows:
                return {'completed': 0, 'failed': 0, 'skipped': 0}

            # Group by (event_type, tag_name). Each group → one bulk EB call.
            # attach[(tag_name)] = [(event_id, eb_account_id), ...]
            attach_groups: Dict[str, List[Tuple[UUID, int]]] = defaultdict(list)
            remove_groups: Dict[str, List[Tuple[UUID, int]]] = defaultdict(list)

            # Events that can't be processed (e.g., missing eb_account_id)
            # — fail individually, don't poison the bulk groups.
            unprocessable: List[Tuple[UUID, str]] = []

            for r in rows:
                payload = r['payload']
                if isinstance(payload, str):
                    payload = json.loads(payload)

                tag_name = payload.get('tag_name')
                if not tag_name:
                    unprocessable.append((r['event_id'], 'missing tag_name in payload'))
                    continue

                eb_account_id = r['emailbison_account_id']
                if eb_account_id is None:
                    unprocessable.append((
                        r['event_id'],
                        f'inbox {r["inbox_id"]} has no emailbison_account_id',
                    ))
                    continue

                key = tag_name
                if r['event_type'] == 'tag_op_attach':
                    attach_groups[key].append((r['event_id'], int(eb_account_id)))
                elif r['event_type'] == 'tag_op_remove':
                    remove_groups[key].append((r['event_id'], int(eb_account_id)))
                else:
                    unprocessable.append((
                        r['event_id'],
                        f'unknown tag_op event_type {r["event_type"]}',
                    ))

            # Mark unprocessable ones failed up front
            failed_count = 0
            for ev_id, reason in unprocessable:
                await self._mark_failed(ev_id, reason)
                failed_count += 1

            if not attach_groups and not remove_groups:
                return {'completed': 0, 'failed': failed_count, 'skipped': 0}

            # Open a workspace-scoped EB session for the duration of this
            # workspace's drain. ADR-006: workspace-scoped key, never global.
            try:
                async with EmailBisonClient(
                    api_key=ws['key_token'],
                    is_workspace_scoped=True,
                ) as client:
                    completed = 0
                    # Tag id cache: avoid GET /tags per group within a workspace
                    tag_id_cache: Dict[str, int] = {}

                    for tag_name, ops in attach_groups.items():
                        try:
                            tag_id = await self._resolve_tag_id(client, tag_name, tag_id_cache)
                            await client.tag_inboxes_bulk(tag_id, [a for _, a in ops])
                            await self._mark_completed_bulk([ev for ev, _ in ops])
                            completed += len(ops)
                        except Exception as exc:
                            logger.exception(
                                "[TagOpWorker:%s] attach %s failed for %d ops: %s",
                                workspace_name, tag_name, len(ops), exc,
                            )
                            await self._mark_failed_bulk(
                                [ev for ev, _ in ops],
                                f'attach {tag_name}: {exc!r}'[:500],
                            )
                            failed_count += len(ops)

                    for tag_name, ops in remove_groups.items():
                        try:
                            tag_id = await self._resolve_tag_id(client, tag_name, tag_id_cache)
                            await client.untag_inboxes_bulk(tag_id, [a for _, a in ops])
                            await self._mark_completed_bulk([ev for ev, _ in ops])
                            completed += len(ops)
                        except Exception as exc:
                            logger.exception(
                                "[TagOpWorker:%s] remove %s failed for %d ops: %s",
                                workspace_name, tag_name, len(ops), exc,
                            )
                            await self._mark_failed_bulk(
                                [ev for ev, _ in ops],
                                f'remove {tag_name}: {exc!r}'[:500],
                            )
                            failed_count += len(ops)

            except Exception as exc:
                # Workspace-level failure (couldn't open EB session, expired
                # key, etc.). Mark all in-flight events failed so the watchdog
                # picks them up later. This isolation is the key property
                # — workspace A's connection issue doesn't block workspace B.
                logger.exception(
                    "[TagOpWorker:%s] workspace-level failure: %s",
                    workspace_name, exc,
                )
                in_flight_ids = (
                    [ev for ops in attach_groups.values() for ev, _ in ops]
                    + [ev for ops in remove_groups.values() for ev, _ in ops]
                )
                if in_flight_ids:
                    await self._mark_failed_bulk(
                        in_flight_ids,
                        f'workspace_session: {exc!r}'[:500],
                    )
                    failed_count += len(in_flight_ids)
                completed = 0

            return {
                'completed': completed,
                'failed': failed_count,
                'skipped': 0,
            }

    async def _resolve_tag_id(
        self, client: EmailBisonClient, tag_name: str,
        cache: Dict[str, int],
    ) -> int:
        """Get-or-create the tag, with per-workspace per-cycle cache."""
        if tag_name in cache:
            return cache[tag_name]
        tag = await client.get_or_create_tag(tag_name)
        tag_id = tag.get('id')
        if tag_id is None:
            raise RuntimeError(f"could not resolve tag id for {tag_name!r}: {tag!r}")
        cache[tag_name] = int(tag_id)
        return cache[tag_name]

    async def _mark_completed_bulk(self, event_ids: List[UUID]) -> None:
        if not event_ids:
            return
        await self.db.execute(
            """
            UPDATE event_log
            SET status = 'completed',
                handler_started_at = COALESCE(handler_started_at, NOW()),
                handler_completed_at = NOW()
            WHERE id = ANY($1::uuid[])
              AND status = 'pending'
            """,
            event_ids,
        )

    async def _mark_failed(self, event_id: UUID, reason: str) -> None:
        await self.db.execute(
            """
            UPDATE event_log
            SET status = 'failed',
                error_message = $2,
                retry_count = retry_count + 1,
                retry_after = NOW() + (INTERVAL '1 minute' * POWER(2, LEAST(retry_count, 6)))
            WHERE id = $1
              AND status = 'pending'
            """,
            event_id, reason[:1000],
        )

    async def _mark_failed_bulk(self, event_ids: List[UUID], reason: str) -> None:
        if not event_ids:
            return
        await self.db.execute(
            """
            UPDATE event_log
            SET status = 'failed',
                error_message = $2,
                retry_count = retry_count + 1,
                retry_after = NOW() + (INTERVAL '1 minute' * POWER(2, LEAST(retry_count, 6)))
            WHERE id = ANY($1::uuid[])
              AND status = 'pending'
            """,
            event_ids, reason[:1000],
        )
