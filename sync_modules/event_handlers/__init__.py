"""
Event handlers — Tier 1 of the event-driven architecture.

Each handler is responsible for ONE event_type and is designed to be:
  - Idempotent (safe to run twice on the same event row)
  - DB-only (never touches EB API directly; enqueues tag_op events instead)
  - Fast (the listener dispatches handlers as separate asyncio tasks
    so a slow handler doesn't block the next notification)

Handlers register with EventListener at startup:

    from sync_modules.event_listener import EventListener
    from sync_modules.event_handlers import (
        kill_queued_handler,
        inbox_died_handler,
        bounce_observed_handler,
        # ...
    )

    listener = EventListener(db_dsn=DSN)
    listener.register('kill_queued',  kill_queued_handler)
    listener.register('inbox_died',   inbox_died_handler)
    listener.register('bounce_observed', bounce_observed_handler)

Plan: docs/plans/event-driven-architecture.md

Phase 2 ships the triggers (migration 108). Phase 3 ships these handlers.
This package is a placeholder until Phase 3.
"""
