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

# Support both command-line arguments and environment variables
# Command-line args take precedence over env vars
CLIENT_ID=${1:-$STRATEGY_CLIENT_ID}
JOB_ID=${2:-$STRATEGY_JOB_ID}
SUBMISSION_ID=${3:-$STRATEGY_SUBMISSION_ID}

# Validate required arguments
if [ -z "$CLIENT_ID" ] || [ -z "$JOB_ID" ]; then
    echo "Error: Missing required arguments"
    echo ""
    echo "Usage: docker run charm-strategy-ai <client_id> <job_id> [submission_id]"
    echo ""
    echo "Or via environment variables:"
    echo "  STRATEGY_CLIENT_ID      UUID of the client"
    echo "  STRATEGY_JOB_ID         UUID of the strategy generation job"
    echo "  STRATEGY_SUBMISSION_ID  (Optional) UUID of the onboarding submission"
    echo ""
    echo "Database environment variables (required):"
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
# Read the skill file content and embed it directly in the prompt
# This is necessary because -p mode doesn't auto-load skills from ~/.claude/skills/
SKILL_FILE="/app/.claude/skills/generate-strategy.md"
if [ -f "$SKILL_FILE" ]; then
    SKILL_CONTENT=$(cat "$SKILL_FILE")
else
    echo "Error: Skill file not found at $SKILL_FILE"
    exit 1
fi

# Construct the full prompt with embedded skill instructions
PROMPT="You are executing a cold email strategy generation task. Follow these instructions exactly:

${SKILL_CONTENT}

---

NOW EXECUTE THE TASK WITH THESE PARAMETERS:
- client_id: ${CLIENT_ID}
- job_id: ${JOB_ID}"

if [ -n "$SUBMISSION_ID" ]; then
    PROMPT="${PROMPT}
- submission_id: ${SUBMISSION_ID}"
fi

PROMPT="${PROMPT}

Execute all steps:
1. Call get_client_context with the client_id
2. Call get_feedback_summary with the client_id
3. Generate 3 email variants based on the context
4. QA score each variant
5. Call save_campaign_variant for each variant
6. Call complete_job with the job_id"

echo "=== Charm Strategy AI Component ==="
echo "Client ID: ${CLIENT_ID}"
echo "Job ID: ${JOB_ID}"
echo "Submission ID: ${SUBMISSION_ID:-'(none)'}"
echo "Database: ${POSTGRES_HOST}:${POSTGRES_PORT}/${POSTGRES_DB}"
echo "=================================="
echo ""

# Copy skills from /app/.claude/ to user's home directory
# This is needed because the credentials volume mount overwrites ~/.claude/
# but we need skills to be available for Claude Code
echo "Setting up Claude Code skills..."
mkdir -p /home/claude/.claude/skills
cp -r /app/.claude/skills/* /home/claude/.claude/skills/ 2>/dev/null || true
cp /app/.claude/settings.local.json /home/claude/.claude/ 2>/dev/null || true
echo "Skills copied to /home/claude/.claude/skills/"
ls -la /home/claude/.claude/skills/
echo ""

echo "Starting Claude Code with strategy skill..."
echo ""

# Run Claude Code with strategy skill
# --dangerously-skip-permissions: Allow MCP tool calls without confirmation
# --mcp-config: Point to the MCP server configuration
exec claude -p "$PROMPT" \
    --dangerously-skip-permissions \
    --mcp-config /app/strategy_mcp_config.json
