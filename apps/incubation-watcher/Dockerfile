# Incubation Watcher — minimal image for Coolify or any container runtime.
#
# Owns the per-workspace incubation graduation flow:
#   - Find inboxes with 14 BD elapsed since warmup_enabled_since
#   - Untag 'incubating' in EB, tag 'reserve' (Google) or 'live' (Microsoft)
#   - Update inventory_pool_status + inventory_lifecycle_status in DB
#   - Tag new warmup inboxes with 'incubating'
#   - Untag 'incubating' from inboxes already at lifecycle='active' (orphan cleanup)
#
# Operator usage (one-shot, dry-run):
#   docker run --rm \
#     -e DATABASE_URL=postgresql://... \
#     -e EMAILBISON_API_URL=https://spellcast.hirecharm.com/api \
#     <image> check --workspace Charm
#
#   docker run --rm \
#     -e DATABASE_URL=... -e EMAILBISON_API_URL=... \
#     <image> run --workspace Charm --apply  # actually mutates EB + DB
#
# Coolify usage:
#   Build context: this directory (apps/incubation-watcher/)
#   Dockerfile path: ./Dockerfile
#   Service type: Dockerfile
#   Run mode (continuous): override CMD to `incubation-watcher daemon`
#     (when daemon mode is implemented in v2)
#   For v1 (operator-invoked): set CMD to `sleep infinity`, then
#     `coolify exec <service> incubation-watcher run --workspace Charm`

FROM python:3.13-slim AS builder

WORKDIR /build

# Build deps for any wheels that compile (asyncpg, httpx)
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
    && rm -rf /var/lib/apt/lists/*

# Copy only what's needed to install
COPY pyproject.toml ./
COPY src ./src

# Install into a venv we can copy across stages — no test deps in the runtime image
RUN python -m venv /opt/venv \
    && /opt/venv/bin/pip install --no-cache-dir --upgrade pip \
    && /opt/venv/bin/pip install --no-cache-dir .


# ---------- runtime stage ----------
FROM python:3.13-slim AS runtime

# Run as non-root for defense-in-depth
RUN useradd --create-home --shell /bin/bash --uid 1000 watcher
USER watcher

# Copy the venv from the builder; ENTRYPOINT activates it implicitly via PATH
COPY --from=builder --chown=watcher:watcher /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

ENTRYPOINT ["incubation-watcher"]
CMD ["--help"]
