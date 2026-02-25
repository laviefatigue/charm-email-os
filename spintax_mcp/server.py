"""
MCP Server providing spintax processing tools to Claude Code.

This server gives Claude the ability to:
- Get approved sequence content for spintax transformation
- Save spintaxed version of sequences
- Mark spintax processing jobs as complete
"""
import json
import os
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

server = Server("spintax-processor")


def get_db():
    """Get database connection with dict cursor."""
    conn = psycopg2.connect(**DB_CONFIG)
    return conn


@server.list_tools()
async def list_tools():
    """List available spintax processing tools."""
    return [
        Tool(
            name="get_sequence_for_spintax",
            description="""Get the approved sequence data to apply spintax transformations.
            Returns the full 4-email sequence with:
            - Email content (subject lines, bodies)
            - Value prop rotation
            - Variables used
            - Client context for personalization

            Call this first to get the content to transform.""",
            inputSchema={
                "type": "object",
                "properties": {
                    "sequence_id": {
                        "type": "string",
                        "description": "The sequence UUID to fetch for spintax processing"
                    }
                },
                "required": ["sequence_id"]
            }
        ),
        Tool(
            name="save_spintaxed_sequence",
            description="""Save the spintaxed version of the sequence.
            This stores the transformed emails with spintax patterns and liquid syntax
            in the spintaxed_sequence_data column, preserving the original sequence_data.

            The spintaxed sequence should include the same 4-email structure with:
            - Spintax variations applied ({Hi|Hello|Hey})
            - Liquid templates for personalization ({% if ... %})
            - Same structure: position, wait_days, subject_line, email_body, thread_reply

            Important rules:
            - Do NOT change core value propositions
            - Do NOT add more than 2-3 spintax variations per element
            - Keep word count within +/- 5 words of original
            - Preserve all existing {{variables}}""",
            inputSchema={
                "type": "object",
                "properties": {
                    "sequence_id": {
                        "type": "string",
                        "description": "The sequence UUID to save spintax for"
                    },
                    "spintaxed_sequence": {
                        "type": "array",
                        "description": "Array of 4 spintaxed email objects",
                        "items": {
                            "type": "object",
                            "properties": {
                                "position": {
                                    "type": "integer",
                                    "description": "Email position: 1, 2, 3, or 4"
                                },
                                "wait_days": {
                                    "type": "integer",
                                    "description": "Days to wait after previous email"
                                },
                                "subject_line": {
                                    "type": ["string", "null"],
                                    "description": "Subject line with spintax (null for threaded replies)"
                                },
                                "email_body": {
                                    "type": "string",
                                    "description": "Email body with spintax and liquid syntax"
                                },
                                "thread_reply": {
                                    "type": "boolean",
                                    "description": "True if this email threads to previous"
                                },
                                "strategy": {
                                    "type": "string",
                                    "description": "Email strategy type"
                                },
                                "value_prop": {
                                    "type": ["string", "null"],
                                    "description": "Value proposition: save_time, make_money, save_money"
                                },
                                "word_count": {
                                    "type": "integer",
                                    "description": "Approximate word count (may vary due to spintax)"
                                }
                            },
                            "required": ["position", "wait_days", "email_body", "thread_reply"]
                        }
                    }
                },
                "required": ["sequence_id", "spintaxed_sequence"]
            }
        ),
        Tool(
            name="complete_spintax_job",
            description="""Mark the spintax processing job as complete.
            This updates:
            - Job status to 'completed' with completed_at timestamp
            - Sequence status to 'spintaxed'

            Call this after successfully saving the spintaxed sequence.""",
            inputSchema={
                "type": "object",
                "properties": {
                    "job_id": {
                        "type": "string",
                        "description": "The spintax job UUID to mark complete"
                    }
                },
                "required": ["job_id"]
            }
        )
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict):
    """Handle tool calls."""

    if name == "get_sequence_for_spintax":
        sequence_id = arguments["sequence_id"]
        conn = get_db()
        cur = conn.cursor(cursor_factory=RealDictCursor)

        try:
            # Get sequence data
            cur.execute("""
                SELECT s.id, s.client_id, s.subject_line, s.email_body,
                       s.sequence_data, s.value_prop_rotation, s.used_variables,
                       s.campaign_type, s.score, s.status, s.total_word_count
                FROM strategy_suggestions s
                WHERE s.id = %s
            """, (sequence_id,))
            sequence = cur.fetchone()

            if not sequence:
                return [TextContent(type="text", text=f"Error: Sequence {sequence_id} not found")]

            # Get client context for personalization rules
            cur.execute("""
                SELECT c.name, c.industry, c.website,
                       s.core_product, s.target_customer, s.job_titles
                FROM clients c
                LEFT JOIN client_onboarding_submissions s ON s.client_id = c.id
                WHERE c.id = %s
                ORDER BY s.created_at DESC
                LIMIT 1
            """, (sequence["client_id"],))
            client = cur.fetchone()

            context = {
                "sequence_id": str(sequence["id"]),
                "client_id": str(sequence["client_id"]),
                "status": sequence["status"],
                "campaign_type": sequence["campaign_type"],
                "score": sequence["score"],
                "total_word_count": sequence["total_word_count"],

                # The 4-email sequence to transform
                "sequence_data": sequence["sequence_data"],
                "value_prop_rotation": sequence["value_prop_rotation"],
                "used_variables": sequence["used_variables"],

                # Client context for personalization
                "client_context": {
                    "name": client["name"] if client else None,
                    "industry": client["industry"] if client else None,
                    "product": client["core_product"] if client else None,
                    "target_customer": client["target_customer"] if client else None,
                    "job_titles": client["job_titles"] if client else [],
                } if client else None,

                # Instructions for spintax application
                "spintax_instructions": {
                    "apply_to": [
                        "greetings (Hi/Hello/Hey)",
                        "opening hooks (Quick question/Brief note)",
                        "CTAs (Worth a call?/Open to chatting?)",
                        "softeners (I think/I believe)",
                        "time references (this week/soon)"
                    ],
                    "liquid_templates": [
                        "Time-of-day greeting for Email 1",
                        "Day-based availability for CTA",
                        "Title/role-based messaging if job_titles available"
                    ],
                    "rules": [
                        "Keep core value proposition unchanged",
                        "Max 2-3 variations per spintax element",
                        "Word count within +/- 5 of original",
                        "Preserve all {{variables}}"
                    ]
                }
            }

            return [TextContent(type="text", text=json.dumps(context, indent=2, default=str))]

        finally:
            cur.close()
            conn.close()

    elif name == "save_spintaxed_sequence":
        sequence_id = arguments["sequence_id"]
        spintaxed_sequence = arguments["spintaxed_sequence"]

        conn = get_db()
        cur = conn.cursor(cursor_factory=RealDictCursor)

        try:
            # Verify sequence exists
            cur.execute("""
                SELECT id, sequence_data, total_word_count
                FROM strategy_suggestions
                WHERE id = %s
            """, (sequence_id,))
            sequence = cur.fetchone()

            if not sequence:
                return [TextContent(type="text", text=f"Error: Sequence {sequence_id} not found")]

            # Calculate new word count (approximate due to spintax)
            new_word_count = sum(
                len(email.get("email_body", "").split())
                for email in spintaxed_sequence
            )

            # Save spintaxed version (preserves original sequence_data)
            cur.execute("""
                UPDATE strategy_suggestions
                SET spintaxed_sequence_data = %s
                WHERE id = %s
            """, (Json(spintaxed_sequence), sequence_id))

            conn.commit()

            return [TextContent(
                type="text",
                text=f"Saved spintaxed sequence for {sequence_id}. "
                     f"Original word count: {sequence['total_word_count']}, "
                     f"Spintaxed approx: {new_word_count}"
            )]

        finally:
            cur.close()
            conn.close()

    elif name == "complete_spintax_job":
        job_id = arguments["job_id"]
        conn = get_db()
        cur = conn.cursor(cursor_factory=RealDictCursor)

        try:
            # Get job to find sequence_id
            cur.execute("""
                SELECT id, sequence_id, status
                FROM spintax_processing_jobs
                WHERE id = %s
            """, (job_id,))
            job = cur.fetchone()

            if not job:
                return [TextContent(type="text", text=f"Error: Spintax job {job_id} not found")]

            if job["status"] == "completed":
                return [TextContent(type="text", text=f"Job {job_id} is already completed")]

            # Update job status
            cur.execute("""
                UPDATE spintax_processing_jobs
                SET status = 'completed', completed_at = NOW()
                WHERE id = %s
            """, (job_id,))

            # Update sequence status to 'spintaxed'
            cur.execute("""
                UPDATE strategy_suggestions
                SET status = 'spintaxed'
                WHERE id = %s
            """, (job["sequence_id"],))

            conn.commit()

            return [TextContent(
                type="text",
                text=f"Spintax job {job_id} completed. "
                     f"Sequence {job['sequence_id']} status updated to 'spintaxed'."
            )]

        finally:
            cur.close()
            conn.close()

    else:
        return [TextContent(type="text", text=f"Error: Unknown tool: {name}")]


async def main():
    """Run the MCP server."""
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
