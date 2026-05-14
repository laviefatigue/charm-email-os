# Hypertide Worker — reconciliation service.
#
# Phase 1: read-only HT↔DB audit, drift detection, backfill of
# domains.hypertide_* columns. No writes to Hypertide.
#
# Operator usage:
#   docker run --rm \
#     -e DATABASE_URL=postgresql://... \
#     -e HYPERTIDE_API_KEY=... \
#     -e HYPERTIDE_API_URL=https://backend.hypertide.io \
#     <image> audit                          # full fleet audit, dry-run
#
#   docker run --rm <image> backfill         # one-time backfill
#   docker run --rm <image> mark-legacy      # set is_legacy on unmatched
#   docker run --rm <image> inspect-domain <name>
#
# Coolify usage:
#   Build context: this directory (apps/hypertide-worker/)
#   Dockerfile path: ./Dockerfile
#   Service type: Dockerfile
#   Cron schedule (Phase 1): `0 6 * * *` running `hypertide-worker audit`
#   v2 (daemon mode for Phase 2 job claim): override CMD to `daemon`

FROM python:3.13-slim AS builder

WORKDIR /build

RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml ./
COPY src ./src

RUN python -m venv /opt/venv \
    && /opt/venv/bin/pip install --no-cache-dir --upgrade pip \
    && /opt/venv/bin/pip install --no-cache-dir .


FROM python:3.13-slim AS runtime

RUN useradd --create-home --shell /bin/bash --uid 1000 worker
USER worker

COPY --from=builder --chown=worker:worker /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# v1 freshness-timer mode. Unlike apps/eod-reapply and apps/incubation-watcher
# (genuine operator tools invoked on demand), hypertide-worker's job is keeping
# the DB mirror of Hypertide state current — that's background freshness, not
# an operator action. So the container runs a simple 24h loop:
#   run audit --apply  ->  sleep 24h  ->  repeat
#
# Properties:
#   - audit --apply is idempotent + read-only toward Hypertide (only UPDATEs
#     our own hypertide_* columns, never INSERTs, never calls HT write APIs)
#   - a crashed audit does NOT crashloop: the loop sleeps 24h then retries
#   - first iteration runs immediately on container start, so a deploy gives
#     you a fresh audit right away
#   - ad-hoc commands still work: `docker exec <c> hypertide-worker inspect-domain X`
#
# This is NOT the Phase 2 job-queue daemon (which claims rows from
# hypertide_jobs). That replaces this loop entirely when Phase 2 ships.
# For precise scheduling (e.g. exactly 06:00 UTC) a Coolify scheduled task
# can be layered on; see HANDOFF.md.
CMD ["bash", "-c", "while true; do echo \"=== hypertide audit run $(date -u +%FT%TZ) ===\"; hypertide-worker audit --apply 2>&1 || echo '=== AUDIT FAILED (retry next cycle) ==='; echo '=== sleeping 24h ==='; sleep 86400; done"]
