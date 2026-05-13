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

# v1 operator-invoked mode. On every container start, run audit-dry-run
# once to surface any config/connectivity errors, then sleep so the
# container stays up for ad-hoc command execution and scheduled tasks.
# Audit is idempotent and read-only without --apply.
# Phase 2 (daemon mode) will replace this with CMD = ["hypertide-worker", "daemon"].
CMD ["bash", "-c", "echo '=== hypertide-worker container start ==='; hypertide-worker audit 2>&1 || echo '=== AUDIT FAILED ==='; echo '=== container entering sleep mode ==='; sleep infinity"]
