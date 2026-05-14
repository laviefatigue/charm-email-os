"""
Event handlers — Tier 1 of the event-driven architecture.

Each handler is responsible for ONE event_type and is designed to be:
  - Idempotent (safe to run twice on the same event row)
  - DB-only (never touches EB API directly; enqueues tag_op events instead)
  - Fast (the listener dispatches handlers as separate asyncio tasks
    so a slow handler doesn't block the next notification)

Wiring at startup:

    from sync_modules.event_listener import EventListener
    from sync_modules.event_handlers import HANDLER_REGISTRY

    listener = EventListener(db_dsn=DSN)
    for event_type, handler in HANDLER_REGISTRY.items():
        listener.register(event_type, handler)
    await listener.run()

Plan: docs/plans/event-driven-architecture.md

Phase status (2026-05-05):
  Phase 1+2+3 SHIPPED on this branch:
    bounce_observed   — full (queue kill if rate > 5%)
    kill_queued       — full (mark dead + enqueue tag ops)
    inbox_died        — full (Phase 3 — wired to pool_promotion.promote_to_target)
    pool_changed      — full (enqueue tag ops)
    domain_burned     — full (NULL pool_status on all inboxes)
    inbox_pickup      — audit log only
    package_assigned  — full (Phase 3 — wired to promote_to_target)

  Phase 4 (next): refactor set_tag_sync as Tier 2 batch worker reading
  from event_log queue per workspace.

  Phase 5+: deferred handlers (disconnect_observed, sender_ban_detected,
  graduated, reconnected). Folded in from Plan B Phase 2 + Plan D Pass 3.
"""
from .kill_chain import (
    bounce_observed_handler,
    kill_queued_handler,
    inbox_died_handler,
)
from .lifecycle import (
    inbox_pickup_handler,
    pool_changed_handler,
)
from .domain import domain_burned_handler
from .workspace import package_assigned_handler


# Map event_type → handler. Listener iterates this at startup.
# Channels match event_type per the trigger naming convention.
HANDLER_REGISTRY = {
    # Kill chain (hot path)
    'bounce_observed':  bounce_observed_handler,
    'kill_queued':      kill_queued_handler,
    'inbox_died':       inbox_died_handler,

    # Lifecycle
    'inbox_pickup':     inbox_pickup_handler,
    'pool_changed':     pool_changed_handler,

    # Domain
    'domain_burned':    domain_burned_handler,

    # Workspace config
    'package_assigned': package_assigned_handler,
}


__all__ = [
    'HANDLER_REGISTRY',
    'bounce_observed_handler',
    'kill_queued_handler',
    'inbox_died_handler',
    'inbox_pickup_handler',
    'pool_changed_handler',
    'domain_burned_handler',
    'package_assigned_handler',
]
