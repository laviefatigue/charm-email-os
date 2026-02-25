"""
MCP Server providing domain generation tools to Claude Code.

This server gives Claude the ability to:
- Get client context including existing domains and onboarding data
- Enrich context by fetching and analyzing client website
- Save domain suggestions for human review
- Mark generation jobs as complete
"""
import json
import os
import re
import uuid
from datetime import datetime
from typing import Optional
import psycopg2
from psycopg2.extras import RealDictCursor
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent
import httpx
from bs4 import BeautifulSoup

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


def extract_base_name(website: str) -> Optional[str]:
    """
    Extract brand base name from website URL.

    Examples:
        hirecharm.com → charm
        usecharm.com → charm
        selery.com → selery
        getspout.io → spout

    For cold email domains, we want the client's brand as the SUFFIX,
    so generated domains will be like: trycharm.com, getcharm.co
    """
    from urllib.parse import urlparse

    if not website:
        return None

    # Parse the URL
    parsed = urlparse(website if '://' in website else f'https://{website}')
    hostname = parsed.netloc or parsed.path

    # Remove www. prefix
    if hostname.startswith('www.'):
        hostname = hostname[4:]

    # Remove port if present
    hostname = hostname.split(':')[0]

    # Get domain without TLD (handle multi-part TLDs like .co.uk)
    parts = hostname.split('.')
    if len(parts) < 2:
        return hostname if hostname else None

    # Take the first part (subdomain/main domain)
    domain_part = parts[0].lower()

    # Strip common prefixes to get the brand name
    prefixes_to_strip = ['get', 'try', 'use', 'hire', 'go', 'my', 'the', 'hello', 'meet', 'join', 'hey']
    for prefix in prefixes_to_strip:
        if domain_part.startswith(prefix) and len(domain_part) > len(prefix) + 2:
            # Only strip if remaining part is long enough to be a brand
            return domain_part[len(prefix):]

    return domain_part


async def fetch_website_keywords(url: str) -> dict:
    """
    Fetch a website and extract business-relevant keywords.

    Returns a dict with:
    - title: Page title
    - description: Meta description
    - keywords: List of extracted business keywords
    - industry_terms: Cold-email relevant industry terms
    """
    try:
        # Ensure URL has protocol
        if not url.startswith(('http://', 'https://')):
            url = f'https://{url}'

        async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
            response = await client.get(url, headers={
                'User-Agent': 'Mozilla/5.0 (compatible; DomainBot/1.0)'
            })
            response.raise_for_status()

        soup = BeautifulSoup(response.text, 'html.parser')

        # Extract title
        title = soup.title.string.strip() if soup.title else ""

        # Extract meta description
        meta_desc = soup.find('meta', attrs={'name': 'description'})
        description = meta_desc.get('content', '').strip() if meta_desc else ""

        # Extract meta keywords if present
        meta_keywords = soup.find('meta', attrs={'name': 'keywords'})
        meta_kw_list = []
        if meta_keywords:
            meta_kw_list = [k.strip().lower() for k in meta_keywords.get('content', '').split(',')]

        # Extract text from key elements
        text_content = []
        for tag in ['h1', 'h2', 'h3', 'p']:
            for element in soup.find_all(tag)[:10]:  # Limit to first 10 of each
                text_content.append(element.get_text(strip=True))

        full_text = ' '.join(text_content).lower()

        # Cold email / B2B relevant industry terms to look for
        industry_term_patterns = {
            # Sales & GTM
            'gtm': ['gtm', 'go-to-market', 'go to market'],
            'sales': ['sales', 'selling', 'revenue'],
            'outreach': ['outreach', 'prospecting', 'cold email'],
            'growth': ['growth', 'scaling', 'scale'],
            'leads': ['leads', 'lead gen', 'lead generation'],
            # Fulfillment & Logistics
            'fulfillment': ['fulfillment', 'fulfil', '3pl', 'warehouse'],
            'shipping': ['shipping', 'ship', 'delivery', 'logistics'],
            'ecommerce': ['ecommerce', 'e-commerce', 'online store', 'shopify'],
            # Tech & SaaS
            'saas': ['saas', 'software', 'platform', 'app'],
            'api': ['api', 'integration', 'developer'],
            'automation': ['automation', 'automate', 'workflow'],
            # Finance
            'fintech': ['fintech', 'payments', 'billing', 'invoicing'],
            'commission': ['commission', 'compensation', 'incentive'],
            # Marketing
            'marketing': ['marketing', 'advertising', 'brand'],
            'content': ['content', 'copywriting', 'messaging'],
            # HR & Recruiting
            'recruiting': ['recruiting', 'hiring', 'talent', 'hr'],
            'staffing': ['staffing', 'workforce', 'employment'],
        }

        found_terms = []
        for term_key, patterns in industry_term_patterns.items():
            for pattern in patterns:
                if pattern in full_text or pattern in title.lower() or pattern in description.lower():
                    found_terms.append(term_key)
                    break

        # Extract unique keywords from title and description
        keywords = set()

        # Add meta keywords
        keywords.update([k for k in meta_kw_list if len(k) > 2 and len(k) < 20])

        # Extract significant words from title
        title_words = re.findall(r'\b[a-z]{3,15}\b', title.lower())
        keywords.update([w for w in title_words if w not in ['the', 'and', 'for', 'with', 'your', 'our', 'that', 'this', 'from', 'are', 'was', 'were', 'will', 'have', 'has', 'been']])

        return {
            "title": title[:200],
            "description": description[:500],
            "keywords": list(keywords)[:20],
            "industry_terms": list(set(found_terms)),
            "success": True
        }

    except Exception as e:
        return {
            "title": "",
            "description": "",
            "keywords": [],
            "industry_terms": [],
            "success": False,
            "error": str(e)
        }


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
            description="""Save a single domain suggestion as available for purchase.
            Each domain will be immediately available for the user to select and buy.
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
        ),
        Tool(
            name="enrich_client_context",
            description="""Fetch the client's website and extract business keywords for better domain generation.

            Call this AFTER get_client_context if you want to generate contextual domains.
            Returns industry terms and keywords extracted from the website content.

            IMPORTANT: Brand name must ALWAYS be at the END of the domain (suffix).

            Use the returned keywords to generate domains like:
            - {keyword}with{brand}.com (e.g., growthwithcharm.com, shipwithselery.com)
            - {keyword}{brand}.com (e.g., gtmcharm.com, fulfillmentselery.com)
            - {action}{keyword}{brand}.com (e.g., scalegrowthcharm.com)

            The brand is ALWAYS the suffix - never put it at the beginning.""",
            inputSchema={
                "type": "object",
                "properties": {
                    "website_url": {
                        "type": "string",
                        "description": "The client's website URL to fetch and analyze"
                    }
                },
                "required": ["website_url"]
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
            # Get client info including website
            cur.execute("""
                SELECT c.id, c.name, c.workspace_id, c.onboarding_data,
                       c.onboarding_complete, c.website, c.domain_pattern
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

            # Get website from client or onboarding data
            website = client.get("website") or onboarding.get("website") or onboarding.get("company_website")

            # Extract base name for suffix-based generation
            base_name = extract_base_name(website) if website else None

            # Also check client's explicit domain_pattern
            client_domain_pattern = client.get("domain_pattern")

            # Determine generation mode
            if base_name:
                generation_mode = "suffix"  # Generate domains ending with brand name
            elif onboarding:
                generation_mode = "onboarding"
            else:
                generation_mode = "pattern_fallback"

            context = {
                "client_id": str(client["id"]),
                "client_name": client["name"],
                "has_onboarding": client["onboarding_complete"] or bool(onboarding),
                "onboarding_data": onboarding,
                "industry": onboarding.get("industry", "Unknown"),
                "product": onboarding.get("product", onboarding.get("core_product", "")),
                "workspace_id": str(workspace_id) if workspace_id else None,
                "website": website,
                "base_name": base_name,  # For suffix-based generation (e.g., "charm" -> trycharm.com)
                "client_domain_pattern": client_domain_pattern,  # Explicit pattern if set
                "total_domains": len(domain_names),
                "existing_domains": domain_names[:20],  # Limit to first 20
                "approved_domains": approved_domains[:10],
                "denied_domains": denied_domains,  # Show all denied to avoid
                "domain_pattern": domain_pattern,  # Extracted from existing domains
                "used_prefixes": used_prefixes[:50],  # Limit
                "generation_mode": generation_mode
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

            # Insert new domain as 'available' - ready for user to select and purchase
            domain_id = str(uuid.uuid4())
            cur.execute("""
                INSERT INTO domains (id, workspace_id, domain_name, notes, rationale,
                                     legitimacy_score, approval_status, created_at)
                VALUES (%s, %s, %s, %s, %s, %s, 'available', NOW())
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

    elif name == "enrich_client_context":
        website_url = arguments["website_url"]

        # Fetch and analyze the website
        result = await fetch_website_keywords(website_url)

        if result["success"]:
            # Generate suggested domain patterns based on found terms
            suggested_patterns = []
            for term in result["industry_terms"][:5]:
                suggested_patterns.extend([
                    f"{term}with{{brand}}.com",
                    f"{term}{{brand}}.com",
                ])

            result["suggested_patterns"] = suggested_patterns
            result["usage_hint"] = (
                "Use these industry_terms to create contextual domains. "
                "ALWAYS put the brand name at the END. Examples:\n"
                "- growthwithcharm.com (growth + with + charm)\n"
                "- gtmcharm.com (gtm + charm)\n"
                "- fulfillmentwithselery.com (fulfillment + with + selery)"
            )

        return [TextContent(type="text", text=json.dumps(result, indent=2))]

    else:
        return [TextContent(type="text", text=f"❌ Unknown tool: {name}")]


async def main():
    """Run the MCP server."""
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
