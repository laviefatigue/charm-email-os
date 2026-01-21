"""
MCP Server providing domain generation tools to Claude Code.

This server gives Claude the ability to:
- Get client context including existing domains and onboarding data
- Save domain suggestions for human review
- Mark generation jobs as complete
"""
import json
import os
import uuid
from datetime import datetime
from typing import Optional
import psycopg2
from psycopg2.extras import RealDictCursor
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

# STRICT TLD POLICY: Only these TLDs are allowed
ALLOWED_TLDS = [".com", ".co", ".info"]

server = Server("domain-generator")


def get_db():
    """Get database connection with dict cursor."""
    conn = psycopg2.connect(**DB_CONFIG)
    return conn


def find_common_suffix(domain_names: list[str]) -> Optional[str]:
    """
    Extract the common suffix from a list of domain names.
    Example: ["boostcheckout.com", "getcheckout.com"] -> "checkout.com"
    """
    if not domain_names:
        return None

    # Split each domain into parts
    # Example: "boostcheckoutcomponents.com" -> ["boostcheckoutcomponents", "com"]
    domain_parts = [d.rsplit(".", 1) for d in domain_names]

    # Get the TLD (should be consistent)
    tlds = set(p[1] for p in domain_parts if len(p) == 2)
    if len(tlds) != 1:
        return None  # Mixed TLDs, can't extract pattern
    tld = list(tlds)[0]

    # Get base names (part before TLD)
    bases = [p[0] for p in domain_parts if len(p) == 2]
    if not bases:
        return None

    # Find longest common suffix among bases
    # Start from the end of the shortest base
    min_len = min(len(b) for b in bases)

    common_suffix = ""
    for i in range(1, min_len + 1):
        # Get the last i characters from each base
        suffixes = set(b[-i:] for b in bases)
        if len(suffixes) == 1:
            common_suffix = list(suffixes)[0]
        else:
            break

    if common_suffix:
        return f"{common_suffix}.{tld}"

    return None


@server.list_tools()
async def list_tools():
    """List available domain generation tools."""
    return [
        Tool(
            name="get_client_context",
            description="""Get full context for a client including onboarding data and existing domains.
            ALWAYS call this first to understand the client's domain pattern and what domains already exist.
            Returns: client name, industry, onboarding data, existing domains, denied domains, and domain pattern.""",
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
            name="save_domain_suggestion",
            description="""Save a single domain suggestion for human review.
            Each domain can be independently approved or denied by the user.
            Call this once per domain - don't batch them.

            STRICT TLD POLICY: Only .com, .co, and .info domains are allowed.
            Domains with other TLDs (.io, .ai, .xyz, etc.) will be REJECTED.""",
            inputSchema={
                "type": "object",
                "properties": {
                    "job_id": {
                        "type": "string",
                        "description": "The job ID this suggestion belongs to"
                    },
                    "domain_name": {
                        "type": "string",
                        "description": "Full domain name (e.g., 'growthcheckout.com')"
                    },
                    "rationale": {
                        "type": "string",
                        "description": "Why this domain is a good fit (1-2 sentences)"
                    },
                    "legitimacy_score": {
                        "type": "number",
                        "description": "Professional/legitimate score 0.0-1.0 (0.7+ is good)"
                    }
                },
                "required": ["job_id", "domain_name", "rationale", "legitimacy_score"]
            }
        ),
        Tool(
            name="complete_job",
            description="""Mark a domain generation job as complete after saving all suggestions.
            Call this when you're done generating domains for this job.""",
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
            name="get_feedback_summary",
            description="""Get summary of human feedback on previous suggestions.
            Shows which domains were approved, denied (with reasons), and any revision requests.
            Use this to understand what to avoid and what works well.""",
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
                       c.onboarding_complete
                FROM clients c
                WHERE c.id = %s
            """, (client_id,))
            client = cur.fetchone()

            if not client:
                return [TextContent(type="text", text=f"❌ Client {client_id} not found")]

            workspace_id = client["workspace_id"]

            # Get existing domains
            cur.execute("""
                SELECT domain_name, approval_status
                FROM domains
                WHERE workspace_id = %s
                ORDER BY domain_name
            """, (workspace_id,))
            domains = cur.fetchall()

            domain_names = [d["domain_name"] for d in domains]
            approved_domains = [d["domain_name"] for d in domains if d.get("approval_status") == "approved"]
            denied_domains = [d["domain_name"] for d in domains if d.get("approval_status") == "denied"]

            # Extract domain pattern
            domain_pattern = find_common_suffix(domain_names) if domain_names else None

            # Extract used prefixes
            used_prefixes = []
            if domain_pattern:
                for d in domain_names:
                    if d.endswith(domain_pattern):
                        prefix = d[:-len(domain_pattern)]
                        if prefix:
                            used_prefixes.append(prefix)

            # Parse onboarding data
            onboarding = {}
            if client["onboarding_data"]:
                if isinstance(client["onboarding_data"], str):
                    onboarding = json.loads(client["onboarding_data"])
                else:
                    onboarding = client["onboarding_data"]

            context = {
                "client_id": str(client["id"]),
                "client_name": client["name"],
                "has_onboarding": client["onboarding_complete"] or bool(onboarding),
                "onboarding_data": onboarding,
                "industry": onboarding.get("industry", "Unknown"),
                "product": onboarding.get("product", onboarding.get("core_product", "")),
                "workspace_id": str(workspace_id) if workspace_id else None,
                "total_domains": len(domain_names),
                "existing_domains": domain_names[:20],  # Limit to first 20
                "approved_domains": approved_domains[:10],
                "denied_domains": denied_domains,  # Show all denied to avoid
                "domain_pattern": domain_pattern,
                "used_prefixes": used_prefixes[:50],  # Limit
                "generation_mode": "onboarding" if onboarding else "pattern_fallback"
            }

            return [TextContent(type="text", text=json.dumps(context, indent=2))]

        finally:
            cur.close()
            conn.close()

    elif name == "save_domain_suggestion":
        job_id = arguments["job_id"]
        domain_name = arguments["domain_name"].lower().strip()
        rationale = arguments["rationale"]
        legitimacy_score = float(arguments["legitimacy_score"])

        # STRICT TLD VALIDATION
        # Extract TLD and validate against allowed list
        parts = domain_name.rsplit(".", 1)
        base_name = parts[0] if len(parts) > 1 else domain_name
        tld = "." + parts[1] if len(parts) > 1 else ".com"

        if tld not in ALLOWED_TLDS:
            return [TextContent(
                type="text",
                text=f"❌ REJECTED: TLD '{tld}' not allowed. Only use: {', '.join(ALLOWED_TLDS)}"
            )]

        conn = get_db()
        cur = conn.cursor(cursor_factory=RealDictCursor)

        try:
            # Get job info to find workspace
            cur.execute("""
                SELECT j.client_id, c.workspace_id
                FROM domain_generation_jobs j
                JOIN clients c ON c.id = j.client_id
                WHERE j.id = %s
            """, (job_id,))
            job = cur.fetchone()

            if not job:
                return [TextContent(type="text", text=f"❌ Job {job_id} not found")]

            workspace_id = job["workspace_id"]

            # Check if domain already exists
            cur.execute(
                "SELECT id FROM domains WHERE workspace_id = %s AND domain_name = %s",
                (workspace_id, domain_name)
            )
            existing = cur.fetchone()

            if existing:
                return [TextContent(type="text", text=f"⚠️ Domain {domain_name} already exists, skipping")]

            # TLD already extracted above for validation

            # Insert new domain
            domain_id = str(uuid.uuid4())
            cur.execute("""
                INSERT INTO domains (id, workspace_id, domain_name, notes, rationale,
                                     legitimacy_score, approval_status, created_at)
                VALUES (%s, %s, %s, %s, %s, %s, 'pending', NOW())
            """, (domain_id, workspace_id, domain_name,
                  f"AI generated: {rationale}", rationale, legitimacy_score))

            conn.commit()

            return [TextContent(type="text", text=f"✓ Saved domain: {domain_name} (score: {legitimacy_score:.2f})")]

        finally:
            cur.close()
            conn.close()

    elif name == "complete_job":
        job_id = arguments["job_id"]
        conn = get_db()
        cur = conn.cursor()

        try:
            cur.execute("""
                UPDATE domain_generation_jobs
                SET status = 'completed', completed_at = NOW()
                WHERE id = %s
            """, (job_id,))
            conn.commit()

            return [TextContent(type="text", text=f"✓ Job {job_id} marked complete")]

        finally:
            cur.close()
            conn.close()

    elif name == "get_feedback_summary":
        client_id = arguments["client_id"]
        conn = get_db()
        cur = conn.cursor(cursor_factory=RealDictCursor)

        try:
            # Get workspace
            cur.execute("SELECT workspace_id FROM clients WHERE id = %s", (client_id,))
            client = cur.fetchone()

            if not client or not client["workspace_id"]:
                return [TextContent(type="text", text=f"❌ Client {client_id} not found or no workspace")]

            workspace_id = client["workspace_id"]

            # Get approved domains
            cur.execute("""
                SELECT domain_name, rationale
                FROM domains
                WHERE workspace_id = %s AND approval_status = 'approved'
                ORDER BY reviewed_at DESC
                LIMIT 20
            """, (workspace_id,))
            approved = cur.fetchall()

            # Get denied domains with reasons
            cur.execute("""
                SELECT domain_name, rationale, notes
                FROM domains
                WHERE workspace_id = %s AND approval_status = 'denied'
                ORDER BY reviewed_at DESC
            """, (workspace_id,))
            denied = cur.fetchall()

            summary = {
                "approved_count": len(approved),
                "denied_count": len(denied),
                "approved_examples": [
                    {"domain": d["domain_name"], "rationale": d.get("rationale", "")}
                    for d in approved[:5]
                ],
                "denied_domains": [
                    {"domain": d["domain_name"], "reason": d.get("notes", d.get("rationale", ""))}
                    for d in denied
                ],
                "patterns_to_avoid": list(set(
                    d["domain_name"].split(".")[0][:4]  # First 4 chars of denied prefixes
                    for d in denied
                    if d["domain_name"]
                ))
            }

            return [TextContent(type="text", text=json.dumps(summary, indent=2))]

        finally:
            cur.close()
            conn.close()

    else:
        return [TextContent(type="text", text=f"❌ Unknown tool: {name}")]


async def main():
    """Run the MCP server."""
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
