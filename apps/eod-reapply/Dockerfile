# EOD Reapply CLI — minimal image for Coolify or any container runtime.
#
# Operator usage (one-shot):
#   docker run --rm \
#     -e DATABASE_URL=postgresql://... \
#     -e EMAILBISON_API_URL=https://spellcast.hirecharm.com/api \
#     <image> check --workspace Sammy
#
#   docker run --rm \
#     -e DATABASE_URL=postgresql://... \
#     <image> reapply --workspace Sammy --campaign-id 123 --skip-time-check
#
# Coolify usage:
#   Build context: this directory (apps/eod-reapply/)
#   Dockerfile path: ./Dockerfile
#   Service type: "Dockerfile" (not docker-compose)
#   For v1 (operator-invoked): set the run command to a no-op or sleep, then
#     `coolify exec <service> eod-reapply check --workspace Sammy`.
#   For v2 (scheduler): override CMD with the scheduler entrypoint.

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
RUN useradd --create-home --shell /bin/bash --uid 1000 reapply
USER reapply

# Copy the venv from the builder; ENTRYPOINT activates it implicitly via PATH
COPY --from=builder --chown=reapply:reapply /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# Default to the CLI entrypoint. Operator passes the subcommand and args.
#   docker run <image> check --workspace Sammy
#   docker run <image> reapply --workspace Sammy --campaign-id 123 --apply
ENTRYPOINT ["eod-reapply"]
CMD ["--help"]
