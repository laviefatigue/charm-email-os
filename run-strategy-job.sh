#!/bin/bash
# Charm Email OS - Run Strategy Generation Job
#
# This script runs the charm-strategy-ai container manually with the correct
# volume mount for Claude credentials. Use this when Coolify's deployment
# cannot be configured with custom docker run options.
#
# Usage:
#   ./run-strategy-job.sh <client_id> <job_id> [submission_id]
#
# Prerequisites:
#   - Claude Code authenticated on VPS (credentials at /root/.claude/)
#   - Environment variables set OR edit this script with actual values
#
# To get POSTGRES_PASSWORD:
#   1. Go to Coolify Panel → charm-api → Environment Variables
#   2. Copy the POSTGRES_PASSWORD value
#   3. Set it below or export it before running this script

set -e

# Database configuration - update these or set via environment
POSTGRES_HOST=${POSTGRES_HOST:-"31.97.142.123"}
POSTGRES_PORT=${POSTGRES_PORT:-"5432"}
POSTGRES_DB=${POSTGRES_DB:-"postgres"}
POSTGRES_USER=${POSTGRES_USER:-"postgres"}
POSTGRES_PASSWORD=${POSTGRES_PASSWORD:-""}

# Container image
IMAGE="n008gg4c88kgw4g48wcckk0k:latest"

# Arguments
CLIENT_ID=$1
JOB_ID=$2
SUBMISSION_ID=${3:-""}

# Validate required arguments
if [ -z "$CLIENT_ID" ] || [ -z "$JOB_ID" ]; then
    echo "Usage: ./run-strategy-job.sh <client_id> <job_id> [submission_id]"
    echo ""
    echo "Arguments:"
    echo "  client_id      UUID of the client"
    echo "  job_id         UUID of the strategy generation job"
    echo "  submission_id  (Optional) UUID of the onboarding submission"
    echo ""
    echo "Environment variables (or edit this script):"
    echo "  POSTGRES_PASSWORD  Database password (required)"
    exit 1
fi

# Validate password
if [ -z "$POSTGRES_PASSWORD" ]; then
    echo "ERROR: POSTGRES_PASSWORD not set"
    echo ""
    echo "To get the password:"
    echo "  1. Go to Coolify Panel → charm-api → Environment Variables"
    echo "  2. Copy the POSTGRES_PASSWORD value"
    echo "  3. Run: export POSTGRES_PASSWORD='<value>'"
    echo "  4. Re-run this script"
    exit 1
fi

echo "=== Charm Strategy AI - Manual Run ==="
echo "Client ID: ${CLIENT_ID}"
echo "Job ID: ${JOB_ID}"
echo "Submission ID: ${SUBMISSION_ID:-'(none)'}"
echo "Database: ${POSTGRES_HOST}:${POSTGRES_PORT}/${POSTGRES_DB}"
echo "Image: ${IMAGE}"
echo "======================================"
echo ""

# Build docker run command
CMD="docker run --rm"
CMD+=" -e POSTGRES_HOST=${POSTGRES_HOST}"
CMD+=" -e POSTGRES_PORT=${POSTGRES_PORT}"
CMD+=" -e POSTGRES_DB=${POSTGRES_DB}"
CMD+=" -e POSTGRES_USER=${POSTGRES_USER}"
CMD+=" -e POSTGRES_PASSWORD=${POSTGRES_PASSWORD}"
CMD+=" -v /root/.claude:/root/.claude"
CMD+=" ${IMAGE}"
CMD+=" ${CLIENT_ID}"
CMD+=" ${JOB_ID}"

if [ -n "$SUBMISSION_ID" ]; then
    CMD+=" ${SUBMISSION_ID}"
fi

echo "Running: docker run --rm \\"
echo "  -e POSTGRES_HOST=${POSTGRES_HOST} \\"
echo "  -e POSTGRES_PORT=${POSTGRES_PORT} \\"
echo "  -e POSTGRES_DB=${POSTGRES_DB} \\"
echo "  -e POSTGRES_USER=${POSTGRES_USER} \\"
echo "  -e POSTGRES_PASSWORD=<redacted> \\"
echo "  -v /root/.claude:/root/.claude \\"
echo "  ${IMAGE} \\"
echo "  ${CLIENT_ID} ${JOB_ID} ${SUBMISSION_ID}"
echo ""

# Execute
exec $CMD
