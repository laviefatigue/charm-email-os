"""
MCP Server providing strategy generation tools to Claude Code.

This server gives Claude the ability to:
- Get client context including onboarding data, segments, and personas
- Get feedback summary from previous strategy generations
- Save campaign variants for human review
- Mark generation jobs as complete
"""
import json
import os
import uuid
from datetime import datetime
from typing import Optional
import psycopg2
from psycopg2.extras import RealDictCursor, Json
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

# Database configuration from environment
DB_CONFIG = {
    "host": os.getenv("POSTGRES_HOST", "localhost"),
    "port": int(os.getenv("POSTGRES_PORT", "5432")),
    "database": os.getenv("POSTGRES_DB", "postgres"),
    "user": os.getenv("POSTGRES_USER", "postgres"),
    "password": os.getenv("POSTGRES_PASSWORD", ""),
}

server = Server("strategy-generator")


def get_db():
    """Get database connection with dict cursor."""
    conn = psycopg2.connect(**DB_CONFIG)
    return conn


@server.list_tools()
async def list_tools():
    """List available strategy generation tools."""
    return [
        Tool(
            name="get_client_context",
            description="""Get full client context for strategy generation including:
            - Company info (name, industry, product)
            - Onboarding data (target customer, ICP, messaging)
            - Customer segments with characteristics
            - Buyer personas with pain points
            - Case studies and ROI results
            - Previous suggestions and feedback

            ALWAYS call this first to understand the client before generating strategies.""",
            inputSchema={
                "type": "object",
                "properties": {
                    "client_id": {
                        "type": "string",
                        "description": "The client UUID to get context for"
                    }
                },
                "required": ["client_id"]
            }
        ),
        Tool(
            name="get_feedback_summary",
            description="""Get summary of human feedback on previous strategy suggestions.
            Shows which variants were approved, denied (with reasons), and revision requests.
            Use this to understand what works and what to avoid.""",
            inputSchema={
                "type": "object",
                "properties": {
                    "client_id": {
                        "type": "string",
                        "description": "The client UUID to get feedback for"
                    }
                },
                "required": ["client_id"]
            }
        ),
        Tool(
            name="save_campaign_variant",
            description="""Save a single email campaign variant for human review.
            Each variant is independently reviewable - approved, denied, or revision requested.

            For initial generation, create 3 variants with different angles:
            - V1: Opens with custom signal/insight
            - V2: Opens with case study proof
            - V3: Opens with risk/efficiency angle

            For revision, create 1 revised variant with original_suggestion_id set.

            Include QA score from the 0-100 rubric.""",
            inputSchema={
                "type": "object",
                "properties": {
                    "job_id": {
                        "type": "string",
                        "description": "The strategy generation job ID"
                    },
                    "variant_number": {
                        "type": "integer",
                        "description": "Variant number (1, 2, or 3, or 1 for revisions)"
                    },
                    "subject_line": {
                        "type": "string",
                        "description": "Email subject line"
                    },
                    "email_body": {
                        "type": "string",
                        "description": "Full email body text"
                    },
                    "score": {
                        "type": "integer",
                        "description": "QA score 0-100 from the scoring rubric"
                    },
                    "rationale": {
                        "type": "string",
                        "description": "Why this variant scores well / areas for improvement"
                    },
                    "used_variables": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Variables used like ['{{first_name}}', '{{company_name}}']"
                    },
                    "campaign_type": {
                        "type": "string",
                        "description": "Type: custom_signal, creative_ideas, whole_offer, or fallback"
                    },
                    "original_suggestion_id": {
                        "type": "string",
                        "description": "For revisions: the original suggestion UUID this revises"
                    },
                    "strategy_id": {
                        "type": "string",
                        "description": "Optional: the strategy UUID to associate with"
                    }
                },
                "required": ["job_id", "variant_number", "subject_line", "email_body"]
            }
        ),
        Tool(
            name="complete_job",
            description="""Mark a strategy generation job as complete (ready for review).
            Call this after saving all variants for the job.""",
            inputSchema={
                "type": "object",
                "properties": {
                    "job_id": {
                        "type": "string",
                        "description": "The job ID to mark complete"
                    }
                },
                "required": ["job_id"]
            }
        ),
        Tool(
            name="get_revision_context",
            description="""Get context for revising a specific suggestion.
            Returns the original suggestion content and the user's revision instruction.
            Use this when processing a revision job.""",
            inputSchema={
                "type": "object",
                "properties": {
                    "suggestion_id": {
                        "type": "string",
                        "description": "The original suggestion UUID to revise"
                    }
                },
                "required": ["suggestion_id"]
            }
        ),
        Tool(
            name="mark_revision_processed",
            description="""Mark a revision request as processed after generating the revised variant.
            Call this after saving the revised variant.""",
            inputSchema={
                "type": "object",
                "properties": {
                    "suggestion_id": {
                        "type": "string",
                        "description": "The original suggestion UUID that was revised"
                    }
                },
                "required": ["suggestion_id"]
            }
        ),
        Tool(
            name="save_campaign_sequence",
            description="""Save a complete 4-email campaign sequence for human review.
            This is the preferred method for generating campaigns as it creates a full
            sequence matching EmailBison's structure.

            The sequence should include:
            - Email 1 (Day 0): New thread, custom signal or whole offer opener
            - Email 2 (Day 3-4): Threads to Email 1, rotated value prop
            - Email 3 (Day 7-8): New thread, different approach
            - Email 4 (Day 11-12): Final email, redirect or value bomb

            Value props should rotate through: save_time, make_money, save_money""",
            inputSchema={
                "type": "object",
                "properties": {
                    "job_id": {
                        "type": "string",
                        "description": "The strategy generation job ID"
                    },
                    "campaign_name": {
                        "type": "string",
                        "description": "Campaign name (typically Email 1 subject line)"
                    },
                    "campaign_type": {
                        "type": "string",
                        "description": "Type: custom_signal, creative_ideas, whole_offer, or fallback"
                    },
                    "sequence": {
                        "type": "array",
                        "description": "Array of 4 email objects",
                        "items": {
                            "type": "object",
                            "properties": {
                                "position": {"type": "integer", "description": "1, 2, 3, or 4"},
                                "wait_days": {"type": "integer", "description": "Days after previous email"},
                                "subject_line": {"type": ["string", "null"], "description": "Subject (null for threaded replies)"},
                                "email_body": {"type": "string", "description": "Email body text"},
                                "thread_reply": {"type": "boolean", "description": "True if threads to previous email"},
                                "strategy": {"type": "string", "description": "Strategy for this email"},
                                "value_prop": {"type": ["string", "null"], "description": "save_time, make_money, save_money, or null"},
                                "word_count": {"type": "integer", "description": "Word count of email body"}
                            },
                            "required": ["position", "wait_days", "email_body", "thread_reply"]
                        }
                    },
                    "value_prop_rotation": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Value props in order: ['save_time', 'make_money', 'save_money']"
                    },
                    "used_variables": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Variables used across the sequence"
                    },
                    "missing_variables": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Variables referenced but not available"
                    },
                    "score": {
                        "type": "integer",
                        "description": "Overall QA score 0-100"
                    },
                    "rationale": {
                        "type": "string",
                        "description": "Explanation of sequence strategy and quality"
                    },
                    "strategy_id": {
                        "type": "string",
                        "description": "Optional: the strategy UUID to associate with"
                    }
                },
                "required": ["job_id", "campaign_name", "campaign_type", "sequence"]
            }
        )
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict):
    """Handle tool calls."""

    if name == "get_client_context":
        client_id = arguments["client_id"]
        conn = get_db()
        cur = conn.cursor(cursor_factory=RealDictCursor)

        try:
            # Get client info
            cur.execute("""
                SELECT c.id, c.name, c.workspace_id, c.onboarding_data,
                       c.onboarding_complete, c.contact_name, c.contact_email,
                       c.website, c.industry, c.domain_pattern
                FROM clients c
                WHERE c.id = %s
            """, (client_id,))
            client = cur.fetchone()

            if not client:
                return [TextContent(type="text", text=f"Error: Client {client_id} not found")]

            # Get the most recent onboarding submission
            cur.execute("""
                SELECT *
                FROM client_onboarding_submissions
                WHERE client_id = %s
                ORDER BY created_at DESC
                LIMIT 1
            """, (client_id,))
            submission = cur.fetchone()

            # Get segments if submission exists
            segments = []
            personas = []
            if submission:
                cur.execute("""
                    SELECT segment_name, revenue_percentage, unique_characteristics,
                           pain_points, buying_triggers
                    FROM client_segments
                    WHERE submission_id = %s
                """, (submission["id"],))
                segments = cur.fetchall() or []

                cur.execute("""
                    SELECT job_title, primary_segment, seniority_level,
                           pain_before_buying, aha_moment, objections
                    FROM client_personas
                    WHERE submission_id = %s
                """, (submission["id"],))
                personas = cur.fetchall() or []

            # Parse legacy onboarding data
            onboarding = {}
            if client["onboarding_data"]:
                if isinstance(client["onboarding_data"], str):
                    onboarding = json.loads(client["onboarding_data"])
                else:
                    onboarding = client["onboarding_data"]

            # Build context object
            context = {
                "client_id": str(client["id"]),
                "client_name": client["name"],
                "contact_name": client.get("contact_name"),
                "contact_email": client.get("contact_email"),
                "website": client.get("website") or (submission.get("website") if submission else None),
                "industry": client.get("industry") or (submission.get("industry") if submission else onboarding.get("industry")),

                # Company info from submission
                "company_name": submission.get("company_name") if submission else client["name"],
                "employee_count": submission.get("employee_count") if submission else None,
                "funding_stage": submission.get("funding_stage") if submission else None,

                # Offering details
                "core_product": submission.get("core_product") if submission else onboarding.get("product"),
                "target_customer": submission.get("target_customer") if submission else None,
                "acv": submission.get("acv") if submission else None,
                "sales_cycle_length": submission.get("sales_cycle_length") if submission else None,

                # Market signals
                "buying_signals": submission.get("signals") if submission else [],
                "job_titles": submission.get("job_titles") if submission else [],

                # Segments and personas
                "segments": [
                    {
                        "name": s["segment_name"],
                        "revenue_percentage": s["revenue_percentage"],
                        "characteristics": s.get("unique_characteristics"),
                        "pain_points": s.get("pain_points"),
                        "buying_triggers": s.get("buying_triggers")
                    }
                    for s in segments
                ],
                "personas": [
                    {
                        "job_title": p["job_title"],
                        "segment": p.get("primary_segment"),
                        "seniority": p.get("seniority_level"),
                        "pain_before_buying": p.get("pain_before_buying"),
                        "aha_moment": p.get("aha_moment"),
                        "objections": p.get("objections")
                    }
                    for p in personas
                ],

                # Messaging
                "customer_voice": submission.get("customer_voice") if submission else None,
                "roi_results": submission.get("roi_results") if submission else None,
                "tone_style": submission.get("tone_style") if submission else None,

                # Tools
                "outbound_tools": submission.get("outbound_tools") if submission else [],
                "crm": submission.get("crm") if submission else None,

                # Goals
                "primary_objective": submission.get("primary_gtm_objective") if submission else None,
                "success_metrics": submission.get("success_metrics") if submission else [],
                "success_definition": submission.get("success_definition") if submission else None,

                # Generation info
                "has_comprehensive_onboarding": submission is not None,
                "submission_status": submission.get("submission_status") if submission else None,
            }

            return [TextContent(type="text", text=json.dumps(context, indent=2, default=str))]

        finally:
            cur.close()
            conn.close()

    elif name == "get_feedback_summary":
        client_id = arguments["client_id"]
        conn = get_db()
        cur = conn.cursor(cursor_factory=RealDictCursor)

        try:
            # Get approved suggestions
            cur.execute("""
                SELECT subject_line, email_body, score, rationale, campaign_type
                FROM strategy_suggestions
                WHERE client_id = %s AND status = 'approved'
                ORDER BY reviewed_at DESC
                LIMIT 10
            """, (client_id,))
            approved = cur.fetchall() or []

            # Get denied suggestions
            cur.execute("""
                SELECT subject_line, email_body, score, human_comment, campaign_type
                FROM strategy_suggestions
                WHERE client_id = %s AND status = 'denied'
                ORDER BY reviewed_at DESC
                LIMIT 10
            """, (client_id,))
            denied = cur.fetchall() or []

            # Get revision requests
            cur.execute("""
                SELECT r.instruction, s.subject_line, s.email_body
                FROM strategy_revision_requests r
                LEFT JOIN strategy_suggestions s ON s.id = r.variant_id
                WHERE r.client_id = %s AND r.processed = FALSE
                ORDER BY r.created_at DESC
                LIMIT 10
            """, (client_id,))
            revision_requests = cur.fetchall() or []

            summary = {
                "approved_count": len(approved),
                "denied_count": len(denied),
                "pending_revisions": len(revision_requests),
                "approved_examples": [
                    {
                        "subject": a["subject_line"],
                        "score": a["score"],
                        "type": a.get("campaign_type"),
                        "rationale": a.get("rationale")
                    }
                    for a in approved[:5]
                ],
                "denied_examples": [
                    {
                        "subject": d["subject_line"],
                        "score": d["score"],
                        "reason": d.get("human_comment", "No reason provided")
                    }
                    for d in denied[:5]
                ],
                "revision_requests": [
                    {
                        "instruction": r["instruction"],
                        "original_subject": r.get("subject_line")
                    }
                    for r in revision_requests
                ],
                "guidance": _generate_guidance(approved, denied, revision_requests)
            }

            return [TextContent(type="text", text=json.dumps(summary, indent=2))]

        finally:
            cur.close()
            conn.close()

    elif name == "save_campaign_variant":
        job_id = arguments["job_id"]
        variant_number = arguments["variant_number"]
        subject_line = arguments["subject_line"]
        email_body = arguments["email_body"]
        score = arguments.get("score")
        rationale = arguments.get("rationale")
        used_variables = arguments.get("used_variables", [])
        campaign_type = arguments.get("campaign_type")
        original_suggestion_id = arguments.get("original_suggestion_id")
        strategy_id = arguments.get("strategy_id")

        conn = get_db()
        cur = conn.cursor(cursor_factory=RealDictCursor)

        try:
            # Get job info including strategy_id
            cur.execute("""
                SELECT client_id, generation_round, strategy_id
                FROM strategy_generation_jobs
                WHERE id = %s
            """, (job_id,))
            job = cur.fetchone()

            if not job:
                return [TextContent(type="text", text=f"Error: Job {job_id} not found")]

            client_id = job["client_id"]
            generation_round = job["generation_round"]
            # Use strategy_id from argument or job
            final_strategy_id = strategy_id or job.get("strategy_id")

            # Insert suggestion with new columns
            suggestion_id = str(uuid.uuid4())
            cur.execute("""
                INSERT INTO strategy_suggestions
                (id, job_id, client_id, variant_number, subject_line, email_body,
                 score, rationale, used_variables, campaign_type, generation_round,
                 strategy_id, original_suggestion_id, status)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'pending')
            """, (suggestion_id, job_id, client_id, variant_number, subject_line,
                  email_body, score, rationale, Json(used_variables),
                  campaign_type, generation_round, final_strategy_id, original_suggestion_id))

            conn.commit()

            revision_note = " (revision)" if original_suggestion_id else ""
            return [TextContent(type="text", text=f"Saved variant {variant_number}{revision_note}: {subject_line[:50]}... (score: {score or 'N/A'})")]

        finally:
            cur.close()
            conn.close()

    elif name == "complete_job":
        job_id = arguments["job_id"]
        conn = get_db()
        cur = conn.cursor()

        try:
            cur.execute("""
                UPDATE strategy_generation_jobs
                SET status = 'review', completed_at = NOW()
                WHERE id = %s
            """, (job_id,))
            conn.commit()

            return [TextContent(type="text", text=f"Job {job_id} marked as ready for review")]

        finally:
            cur.close()
            conn.close()

    elif name == "get_revision_context":
        suggestion_id = arguments["suggestion_id"]
        conn = get_db()
        cur = conn.cursor(cursor_factory=RealDictCursor)

        try:
            # Get original suggestion content
            cur.execute("""
                SELECT id, subject_line, email_body, score, rationale,
                       used_variables, campaign_type, strategy_id, client_id
                FROM strategy_suggestions
                WHERE id = %s
            """, (suggestion_id,))
            suggestion = cur.fetchone()

            if not suggestion:
                return [TextContent(type="text", text=f"Error: Suggestion {suggestion_id} not found")]

            # Get revision instruction from revision request
            cur.execute("""
                SELECT instruction, created_at
                FROM strategy_revision_requests
                WHERE variant_id = %s AND processed = FALSE
                ORDER BY created_at DESC
                LIMIT 1
            """, (suggestion_id,))
            revision_request = cur.fetchone()

            # Get feedback patterns for context
            cur.execute("""
                SELECT subject_line, human_comment, status
                FROM strategy_suggestions
                WHERE client_id = %s AND status IN ('approved', 'denied')
                ORDER BY reviewed_at DESC
                LIMIT 5
            """, (suggestion["client_id"],))
            feedback_history = cur.fetchall() or []

            context = {
                "original_suggestion": {
                    "id": str(suggestion["id"]),
                    "subject_line": suggestion["subject_line"],
                    "email_body": suggestion["email_body"],
                    "score": suggestion["score"],
                    "rationale": suggestion["rationale"],
                    "used_variables": suggestion["used_variables"],
                    "campaign_type": suggestion["campaign_type"],
                    "strategy_id": str(suggestion["strategy_id"]) if suggestion["strategy_id"] else None,
                },
                "revision_instruction": revision_request["instruction"] if revision_request else "No specific instruction provided",
                "feedback_patterns": [
                    {
                        "subject": f["subject_line"][:50],
                        "status": f["status"],
                        "comment": f.get("human_comment")
                    }
                    for f in feedback_history
                ]
            }

            return [TextContent(type="text", text=json.dumps(context, indent=2, default=str))]

        finally:
            cur.close()
            conn.close()

    elif name == "mark_revision_processed":
        suggestion_id = arguments["suggestion_id"]
        conn = get_db()
        cur = conn.cursor()

        try:
            # Mark all revision requests for this suggestion as processed
            cur.execute("""
                UPDATE strategy_revision_requests
                SET processed = TRUE
                WHERE variant_id = %s AND processed = FALSE
            """, (suggestion_id,))
            rows_updated = cur.rowcount
            conn.commit()

            if rows_updated > 0:
                return [TextContent(type="text", text=f"Marked {rows_updated} revision request(s) as processed for suggestion {suggestion_id}")]
            else:
                return [TextContent(type="text", text=f"No pending revision requests found for suggestion {suggestion_id}")]

        finally:
            cur.close()
            conn.close()

    elif name == "save_campaign_sequence":
        job_id = arguments["job_id"]
        campaign_name = arguments["campaign_name"]
        campaign_type = arguments["campaign_type"]
        sequence = arguments["sequence"]
        value_prop_rotation = arguments.get("value_prop_rotation", [])
        used_variables = arguments.get("used_variables", [])
        missing_variables = arguments.get("missing_variables", [])
        score = arguments.get("score")
        rationale = arguments.get("rationale")
        strategy_id = arguments.get("strategy_id")

        conn = get_db()
        cur = conn.cursor(cursor_factory=RealDictCursor)

        try:
            # Get job info
            cur.execute("""
                SELECT client_id, generation_round, strategy_id
                FROM strategy_generation_jobs
                WHERE id = %s
            """, (job_id,))
            job = cur.fetchone()

            if not job:
                return [TextContent(type="text", text=f"Error: Job {job_id} not found")]

            client_id = job["client_id"]
            generation_round = job["generation_round"]
            final_strategy_id = strategy_id or job.get("strategy_id")

            # Calculate total word count
            total_word_count = sum(email.get("word_count", 0) for email in sequence)

            # Get subject line from Email 1 for the suggestion record
            email_1 = next((e for e in sequence if e.get("position") == 1), sequence[0])
            subject_line = email_1.get("subject_line") or campaign_name
            email_body = email_1.get("email_body", "")

            # Insert as a sequence suggestion
            suggestion_id = str(uuid.uuid4())
            cur.execute("""
                INSERT INTO strategy_suggestions
                (id, job_id, client_id, variant_number, subject_line, email_body,
                 score, rationale, used_variables, missing_variables, campaign_type,
                 generation_round, strategy_id, status,
                 sequence_data, value_prop_rotation, is_sequence, total_word_count)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'pending',
                        %s, %s, TRUE, %s)
            """, (suggestion_id, job_id, client_id, 1, subject_line, email_body,
                  score, rationale, Json(used_variables), Json(missing_variables),
                  campaign_type, generation_round, final_strategy_id,
                  Json(sequence), Json(value_prop_rotation), total_word_count))

            conn.commit()

            return [TextContent(type="text", text=f"Saved 4-email sequence '{campaign_name}' with {total_word_count} total words (score: {score or 'N/A'})")]

        finally:
            cur.close()
            conn.close()

    else:
        return [TextContent(type="text", text=f"Error: Unknown tool: {name}")]


def _generate_guidance(approved, denied, revisions):
    """Generate guidance based on feedback patterns."""
    guidance = []

    if approved:
        avg_score = sum(a["score"] or 0 for a in approved) / len(approved)
        guidance.append(f"Approved variants average score: {avg_score:.0f}")

    if denied:
        guidance.append(f"Avoid patterns from {len(denied)} denied variants")

    if revisions:
        instructions = [r["instruction"] for r in revisions]
        guidance.append(f"Address {len(revisions)} revision requests: {'; '.join(instructions[:3])}")

    return guidance if guidance else ["No previous feedback - generate initial variants"]


async def main():
    """Run the MCP server."""
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
