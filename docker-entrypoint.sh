#!/bin/bash
# Charm Email OS - Strategy AI Entrypoint
#
# This script is the entrypoint for the charm-strategy-ai container.
# It invokes Claude Code with the strategy skill to generate email variants.
#
# Usage:
#   docker run charm-strategy-ai <client_id> <job_id> [submission_id]
#
# Environment variables (required):
#   POSTGRES_HOST, POSTGRES_PORT, POSTGRES_DB, POSTGRES_USER, POSTGRES_PASSWORD

set -e

CLIENT_ID=$1
JOB_ID=$2
SUBMISSION_ID=${3:-""}

# Validate required arguments
if [ -z "$CLIENT_ID" ] || [ -z "$JOB_ID" ]; then
    echo "Error: Missing required arguments"
    echo ""
    echo "Usage: docker run charm-strategy-ai <client_id> <job_id> [submission_id]"
    echo ""
    echo "Arguments:"
    echo "  client_id      UUID of the client"
    echo "  job_id         UUID of the strategy generation job"
    echo "  submission_id  (Optional) UUID of the onboarding submission"
    echo ""
    echo "Environment variables (required):"
    echo "  POSTGRES_HOST      Database host"
    echo "  POSTGRES_PORT      Database port (default: 5432)"
    echo "  POSTGRES_DB        Database name"
    echo "  POSTGRES_USER      Database user"
    echo "  POSTGRES_PASSWORD  Database password"
    exit 1
fi

# Validate database connection environment
if [ -z "$POSTGRES_HOST" ] || [ -z "$POSTGRES_USER" ] || [ -z "$POSTGRES_PASSWORD" ]; then
    echo "Error: Missing database environment variables"
    echo "Required: POSTGRES_HOST, POSTGRES_USER, POSTGRES_PASSWORD"
    exit 1
fi

# Build the prompt for Claude Code
PROMPT="/generate-strategy client_id=${CLIENT_ID} job_id=${JOB_ID}"
if [ -n "$SUBMISSION_ID" ]; then
    PROMPT="${PROMPT} submission_id=${SUBMISSION_ID}"
fi

echo "=== Charm Strategy AI Component ==="
echo "Client ID: ${CLIENT_ID}"
echo "Job ID: ${JOB_ID}"
echo "Submission ID: ${SUBMISSION_ID:-'(none)'}"
echo "Database: ${POSTGRES_HOST}:${POSTGRES_PORT}/${POSTGRES_DB}"
echo "=================================="
echo ""
echo "Starting Claude Code with strategy skill..."
echo ""

# Run Claude Code with strategy skill
# --dangerously-skip-permissions: Allow MCP tool calls without confirmation
# --mcp-config: Point to the MCP server configuration
exec claude -p "$PROMPT" \
    --dangerously-skip-permissions \
    --mcp-config /app/strategy_mcp_config.json
