"""
Project Directory Assistant - MCP Server

A FastMCP server that gives teammates' Claude instances contextual access
to the linkedin-scanner project. Uses Claude Code inside the container for
synthesis questions, and direct file operations for simple lookups.

Exposed via streamable-http transport so teammates connect via Custom Connector
or MCP config pointing at http://<host>:3000/mcp

Tools (Context & Research):
    ask_project         - Spawn Claude Code to research and answer complex questions
    get_architecture    - Static architecture overview
    get_db_schema       - Database schema with columns, types, indexes
    get_api_endpoints   - All API routes and descriptions
    get_pipeline_overview - Waterfall verification pipeline details
    search_project      - Grep-style search across project files
    get_file            - Read a specific file with line numbers
    list_files          - List directory contents
    get_recent_changes  - Git log showing recent project changes
    query_database      - Run read-only SQL queries against DuckDB (75M+ contacts)

Tools (Notes & Collaboration):
    submit_note         - Leave a note for the project owner (feature ideas, bugs, context)
    get_notes           - Read notes filtered by type, teammate, or status
    update_note         - Owner updates note status and adds a response

Tools (Activity):
    get_query_log       - View recent teammate queries (for pattern analysis)

Authentication:
    Claude Code CLI inside the container uses OAuth credentials mounted
    at /home/claude/.claude via Docker volume. Your subscription, your auth.

Logging:
    All queries and notes logged to SQLite at /app/logs/queries.db for
    quality improvement, team coordination, and planning visibility.
"""

import os
import json
import subprocess
import sqlite3
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
from datetime import datetime
from pathlib import Path

from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
PROJECT_DIR = os.getenv("PROJECT_DIR", "/app/project")
LOG_DB = os.getenv("LOG_DB", "/app/logs/queries.db")
NOTES_DIR = os.getenv("NOTES_DIR", "/app/notes")
CLAUDE_MAX_TURNS = int(os.getenv("CLAUDE_MAX_TURNS", "6"))
CLAUDE_PROFILE = os.getenv("CLAUDE_PROFILE", "")

# Timeout settings (all in seconds)
# Cloudflare's edge proxy read timeout is 100s (non-Enterprise), so all tool
# timeouts must complete well under that to avoid 524 errors for teammates.
QUERY_TIMEOUT = int(os.getenv("QUERY_TIMEOUT", "30"))
SEARCH_TIMEOUT = int(os.getenv("SEARCH_TIMEOUT", "15"))
REQUEST_TIMEOUT = int(os.getenv("REQUEST_TIMEOUT", "95"))

mcp = FastMCP(
    name="project-assistant",
    host=os.getenv("FASTMCP_HOST", "0.0.0.0"),
    port=int(os.getenv("FASTMCP_PORT", "3000")),
    transport_security=TransportSecuritySettings(
        enable_dns_rebinding_protection=False,
    ),
)

# ---------------------------------------------------------------------------
# Query Logging (SQLite)
# ---------------------------------------------------------------------------

def init_db():
    """Create the query log and notes tables if they don't exist."""
    os.makedirs(os.path.dirname(LOG_DB), exist_ok=True)
    conn = sqlite3.connect(LOG_DB)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS query_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            teammate TEXT,
            tool_name TEXT,
            question TEXT,
            context_area TEXT,
            response_preview TEXT,
            response_length INTEGER,
            duration_ms INTEGER,
            files_referenced TEXT,
            created_at TEXT DEFAULT (datetime('now'))
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS notes (
            id TEXT PRIMARY KEY,
            teammate TEXT NOT NULL,
            note_type TEXT NOT NULL,
            title TEXT NOT NULL,
            body TEXT NOT NULL,
            related_files TEXT DEFAULT '[]',
            related_code TEXT DEFAULT '',
            status TEXT DEFAULT 'new',
            owner_response TEXT DEFAULT '',
            created_at TEXT DEFAULT (datetime('now')),
            updated_at TEXT DEFAULT (datetime('now'))
        )
    """)
    conn.commit()
    conn.close()


def log_query(teammate, tool_name, question, context_area, response, duration_ms, files_ref=None):
    """Log a query to SQLite for analytics and quality tracking."""
    try:
        conn = sqlite3.connect(LOG_DB)
        conn.execute(
            """INSERT INTO query_log
               (teammate, tool_name, question, context_area, response_preview,
                response_length, duration_ms, files_referenced)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                teammate,
                tool_name,
                question,
                context_area,
                response[:500],
                len(response),
                duration_ms,
                json.dumps(files_ref or []),
            ),
        )
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"[LOG ERROR] {e}")


# ---------------------------------------------------------------------------
# Knowledge Base (Foam Documentation)
# ---------------------------------------------------------------------------

DOCS_DIR = os.path.join(PROJECT_DIR, "docs")
_knowledge_cache: dict = {}  # path -> (mtime, parsed_frontmatter)
import re as _re


def _strip_frontmatter(content: str) -> str:
    """Remove YAML frontmatter delimited by --- lines."""
    if content.startswith("---"):
        parts = content.split("---", 2)
        if len(parts) >= 3:
            return parts[2].strip()
    return content


def _parse_frontmatter(filepath: str) -> dict:
    """Parse YAML frontmatter from a Foam markdown file.

    Returns dict with keys: path, title, tags, area, summary, related.
    Uses simple string parsing -- no PyYAML dependency.
    """
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()
    except Exception:
        return {}

    if not content.startswith("---"):
        return {"path": filepath}

    parts = content.split("---", 2)
    if len(parts) < 3:
        return {"path": filepath}

    fm_text = parts[1].strip()
    result = {"path": filepath}

    for line in fm_text.split("\n"):
        line = line.strip()
        if ":" not in line:
            continue
        key, _, val = line.partition(":")
        key = key.strip()
        val = val.strip()

        if key in ("title", "area", "summary"):
            result[key] = val.strip("\"'")
        elif key in ("tags", "related"):
            # Parse inline YAML list: [tag1, tag2] or multiline
            if val.startswith("["):
                items = val.strip("[]").split(",")
                result[key] = [i.strip().strip("\"'") for i in items if i.strip()]
            else:
                result[key] = []

    return result


def _load_knowledge_index() -> list:
    """Load all docs and their frontmatter into a searchable catalog.

    Uses mtime-based caching to avoid re-reading unchanged files.
    """
    global _knowledge_cache
    if not os.path.isdir(DOCS_DIR):
        return []

    catalog = []
    for root, _dirs, files in os.walk(DOCS_DIR):
        for fname in files:
            if not fname.endswith(".md"):
                continue
            fpath = os.path.join(root, fname)
            mtime = os.path.getmtime(fpath)

            if fpath in _knowledge_cache and _knowledge_cache[fpath][0] == mtime:
                catalog.append(_knowledge_cache[fpath][1])
            else:
                parsed = _parse_frontmatter(fpath)
                if parsed:
                    _knowledge_cache[fpath] = (mtime, parsed)
                    catalog.append(parsed)
    return catalog


def _score_document(doc: dict, question: str, context_area: str) -> int:
    """Score a document's relevance to a question.

    Scoring: area match (+10), title keyword (+5), summary keyword (+3), tag match (+2).
    """
    score = 0
    q_words = [w.lower() for w in question.split() if len(w) > 2]
    doc_area = doc.get("area", "")
    doc_title = doc.get("title", "").lower()
    doc_summary = doc.get("summary", "").lower()
    doc_tags = [t.lower() for t in doc.get("tags", [])]

    # Area match
    if context_area and context_area != "general" and doc_area == context_area:
        score += 10

    # Keyword matching
    for word in q_words:
        if word in doc_title:
            score += 5
        if word in doc_summary:
            score += 3
        if word in doc_tags:
            score += 2

    return score


def _extract_wikilinks(content: str) -> list:
    """Extract [[wikilink]] targets from markdown content."""
    return _re.findall(r"\[\[([^\]]+)\]\]", content)


def _resolve_wikilink(link_target: str) -> str | None:
    """Resolve a wikilink name to a file path in docs/ tree."""
    if not os.path.isdir(DOCS_DIR):
        return None
    target_lower = link_target.lower().replace(" ", "-")
    for root, _dirs, files in os.walk(DOCS_DIR):
        for fname in files:
            if fname.lower().replace(".md", "") == target_lower:
                return os.path.join(root, fname)
    return None


def _read_doc(filepath: str) -> str:
    """Read a Foam doc and return content without frontmatter."""
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            return _strip_frontmatter(f.read())
    except Exception:
        return ""


def _try_docs_answer(question: str, context_area: str) -> str | None:
    """Attempt to answer from Foam docs. Returns None if docs insufficient.

    Returns None for code-level questions (line, function, bug, error, etc.)
    so they fall through to Claude CLI.
    """
    code_indicators = [
        "line ", "function ", "class ", "method ", "bug ", "error ",
        "traceback", "exception", "implementation detail",
        "why does", "how does the code", "what happens when",
        "source code", "refactor", "debug",
    ]
    question_lower = question.lower()
    if any(indicator in question_lower for indicator in code_indicators):
        return None

    catalog = _load_knowledge_index()
    if not catalog:
        return None

    scored = [(doc, _score_document(doc, question, context_area)) for doc in catalog]
    scored.sort(key=lambda x: x[1], reverse=True)

    if not scored or scored[0][1] < 8:
        return None

    # Read top 3 relevant docs
    parts = []
    for doc, score in scored[:3]:
        if score < 5:
            break
        fpath = doc.get("path", "")
        content = _read_doc(fpath)
        if content:
            rel = os.path.relpath(fpath, PROJECT_DIR) if fpath else ""
            parts.append(f"## From: {doc.get('title', 'Untitled')} ({rel})\n\n{content}")

    if not parts or sum(len(p) for p in parts) < 200:
        return None

    return "\n\n---\n\n".join(parts)


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------

@mcp.tool()
def query_knowledge(
    question: str,
    context_area: str = "general",
    max_docs: int = 3,
    teammate: str = "anonymous",
) -> str:
    """Query the project knowledge base (Foam documentation) for answers.

    Searches structured documentation FIRST -- much faster and cheaper than
    ask_project(). Use this for conceptual, architectural, and reference
    questions. Falls back guidance to use ask_project() for code-level detail.

    Args:
        question: Your question about the project.
        context_area: Focus area to narrow the search.
            One of: general, database, api, pipeline, config, deployment, testing, module, algorithm
        max_docs: Maximum number of documents to include in response (default 3).
        teammate: Your name (for query logging).

    Returns:
        Answer assembled from documentation, with cross-references.
    """
    start = time.time()
    max_docs = min(max_docs, 5)

    catalog = _load_knowledge_index()
    if not catalog:
        duration_ms = int((time.time() - start) * 1000)
        log_query(teammate, "query_knowledge", question, context_area, "NO_DOCS", duration_ms)
        return (
            "No documentation found. The docs/ directory may not exist yet.\n"
            "Use ask_project() to query the codebase directly."
        )

    scored = [(doc, _score_document(doc, question, context_area)) for doc in catalog]
    scored.sort(key=lambda x: x[1], reverse=True)

    # Read top-N docs
    parts = []
    all_wikilinks = set()
    matched_paths = set()

    for doc, score in scored[:max_docs]:
        if score < 3:
            break
        fpath = doc.get("path", "")
        if not fpath:
            continue
        matched_paths.add(fpath)
        content = _read_doc(fpath)
        if content:
            rel = os.path.relpath(fpath, PROJECT_DIR) if fpath else ""
            parts.append(f"## {doc.get('title', 'Untitled')} ({rel})\n\n{content}")
            all_wikilinks.update(_extract_wikilinks(content))

    if not parts:
        duration_ms = int((time.time() - start) * 1000)
        log_query(teammate, "query_knowledge", question, context_area, "NO_MATCH", duration_ms)
        return (
            f"No documentation matched your question about '{question}'.\n"
            "Try ask_project() for code-level answers, or search_project() for keyword search."
        )

    # Resolve wikilinks to add related context
    related = []
    for link in sorted(all_wikilinks):
        resolved = _resolve_wikilink(link)
        if resolved and resolved not in matched_paths:
            fm = _parse_frontmatter(resolved)
            summary = fm.get("summary", "")
            if summary:
                related.append(f"- [[{link}]] -- {summary}")

    output = "# Knowledge Base Results\n\n"
    output += "\n\n---\n\n".join(parts)

    if related:
        output += "\n\n---\n\n## Related Documents\n\n"
        output += "\n".join(related[:10])

    output += "\n\n---\n*Answered from project documentation. For code-level detail, use ask_project().*"

    duration_ms = int((time.time() - start) * 1000)
    log_query(teammate, "query_knowledge", question, context_area, output[:500], duration_ms)
    return output


@mcp.tool()
def ask_project(
    question: str,
    context_area: str = "general",
    teammate: str = "anonymous",
) -> str:
    """Ask the project assistant a question about the linkedin-scanner codebase.

    Checks project documentation (Foam knowledge base) FIRST for fast answers.
    Only spawns Claude Code if documentation cannot answer the question.

    Args:
        question: Your question about the project.
        context_area: Focus area to narrow the search.
            One of: general, database, api, pipeline, config, deployment, testing
        teammate: Your name (for query logging and team visibility).

    Returns:
        A synthesized answer referencing specific files and code.
    """
    start = time.time()

    # Phase 1: Try docs-first strategy (instant, free)
    docs_answer = _try_docs_answer(question, context_area)
    if docs_answer:
        duration_ms = int((time.time() - start) * 1000)
        log_query(teammate, "ask_project", question, context_area, docs_answer[:500], duration_ms)
        return (
            docs_answer
            + "\n\n---\n*Answered from project documentation. "
            "For code-level detail, re-ask with specifics about files, functions, or line numbers.*"
        )

    # Phase 2: Fall back to Claude CLI (expensive, thorough)
    area_hints = {
        "database": (
            "Focus on DuckDB schema, schema_migrations.py, contacts table columns, "
            "and data models in contract_refinery/models.py."
        ),
        "api": (
            "Focus on api_production.py endpoints, request/response models, "
            "authentication (X-API-Key), and route handlers."
        ),
        "pipeline": (
            "Focus on contract_refinery/ package: refinery.py orchestrator, "
            "email_verifier.py (Gate 1), aiark_client.py (Gate 2), "
            "rescue_layer.py + spider_client.py + jina_client.py (Gate 3), "
            "gate0_prevalidation.py, matching.py."
        ),
        "config": (
            "Focus on contract_refinery/config.py, configs/ directory, "
            "environment variables, and Pydantic configuration models."
        ),
        "deployment": (
            "Focus on Dockerfile, docker-compose.yml, requirements.txt, "
            "and any deployment or infrastructure documentation."
        ),
        "testing": (
            "Focus on gate0_accuracy_test.py, gate0_dns_test.py, "
            "gate0_targeted_test.py, gate1_live_api_test.py, "
            "gate1_validation_test.py."
        ),
        "general": "Search broadly across the entire project.",
    }

    hint = area_hints.get(context_area, area_hints["general"])

    prompt = f"""You are a project directory assistant for the linkedin-scanner project.
A teammate is asking you a question. Research the codebase thoroughly and provide
a clear, actionable answer. Reference specific files and line numbers.

Context area: {context_area}
Hint: {hint}

QUESTION: {question}

Instructions:
- Read relevant files to answer accurately
- Include specific file paths and code snippets where helpful
- Be concise but thorough
- If you are unsure, say so rather than guessing
- Format your response so another Claude instance can consume it
  (the teammate's Claude will use your answer to help them code)
"""

    cmd = [
        "claude",
        "-p",
        prompt,
        "--dangerously-skip-permissions",
        "--max-turns",
        str(CLAUDE_MAX_TURNS),
    ]

    if CLAUDE_PROFILE:
        cmd.extend(["--profile", CLAUDE_PROFILE])

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=90,  # Must finish under Cloudflare's 100s proxy read timeout
            cwd=PROJECT_DIR,
        )

        duration_ms = int((time.time() - start) * 1000)

        if result.returncode != 0:
            error = result.stderr or result.stdout or "Unknown error"
            log_query(teammate, "ask_project", question, context_area, f"ERROR: {error}", duration_ms)
            return f"Error from project assistant: {error[:1000]}"

        response = result.stdout.strip()
        log_query(teammate, "ask_project", question, context_area, response, duration_ms)
        return response

    except subprocess.TimeoutExpired:
        duration_ms = int((time.time() - start) * 1000)
        log_query(teammate, "ask_project", question, context_area, "TIMEOUT", duration_ms)
        return (
            "The question took too long to answer (>90 sec). "
            "Try narrowing your context_area or asking a more specific question."
        )
    except Exception as e:
        return f"Failed to run project assistant: {e}"


@mcp.tool()
def get_architecture() -> str:
    """Get the project architecture overview including tech stack,
    directory structure, waterfall pipeline summary, and key components.

    Reads from Foam documentation (docs/architecture/overview.md).
    For deeper questions, use query_knowledge() or ask_project().
    """
    doc_path = os.path.join(PROJECT_DIR, "docs", "architecture", "overview.md")
    if os.path.exists(doc_path):
        return _read_doc(doc_path)

    # Fallback: hardcoded content (used before docs/ directory exists)
    return """# LinkedIn Scanner - Architecture Overview

## Tech Stack
- **Language:** Python 3.12
- **API Framework:** FastAPI (api_production.py, 1437 lines)
- **Database:** DuckDB (linkedin.duckdb, 75M+ contacts)
- **Data Validation:** Pydantic 2.0
- **HTTP Client:** httpx with retry logic
- **Fuzzy Matching:** rapidfuzz
- **Deployment:** Docker + Docker Compose

## Directory Structure
```
linkedin-scanner/
├── api_production.py            # Production FastAPI (all endpoints)
├── contract_refinery/           # Core lead verification pipeline
│   ├── refinery.py              #   Main ContractRefinery orchestrator (670 lines)
│   ├── email_verifier.py        #   Gate 1: Multi-provider email verification (670 lines)
│   ├── matching.py              #   Fuzzy company name matching (220 lines)
│   ├── models.py                #   Data models: RawLead, WaterfallResult, etc. (241 lines)
│   ├── config.py                #   ContractConfig + ContractFilters (Pydantic) (190 lines)
│   ├── cli.py                   #   Command-line interface (252 lines)
│   ├── gate0_prevalidation.py   #   Gate 0: DNS/syntax pre-validation
│   ├── rescue_layer.py          #   Gate 3: Spider + Jina rescue orchestrator
│   ├── spider_client.py         #   Spider.cloud web scraping client
│   ├── jina_client.py           #   Jina.ai HTML extraction client
│   ├── ingestion.py             #   Bulk import & deduplication
│   ├── freshness.py             #   Lead freshness tracking
│   └── freshness_worker.py      #   Freshness validation worker
├── aiark_client.py              # Gate 2: AI-ARK people enrichment (561 lines)
├── schema_migrations.py         # DuckDB schema migrations (192 lines)
├── validation_worker.py         # Async validation worker
├── configs/                     # Client contract JSON configurations
│   └── example_client_config.json
├── Lead Refinery Technical Specification.md  # Master spec doc
├── Dockerfile                   # Production API container
├── docker-compose.yml           # Local deployment
├── requirements.txt             # Python dependencies
└── linkedin.duckdb              # 75M+ contact database
```

## Core Architecture: Waterfall Pipeline

```
Client Contract (target: 5000 verified leads)
  │
  ▼  Extract raw leads (target × 2.5 multiplier)
Gate 0: Pre-validation (DNS/syntax)         ─── Free, filters ~15%
  │
  ▼
Gate 1: Email Verification                  ─── $0.003/lead
  │    Providers: LeadMagic, Reoon, ZeroBounce
  │    Yield: ~70% pass
  ▼
Gate 2: AI-ARK Enrichment                   ─── $0.005/lead
  │    Fuzzy company match (80% threshold)
  │    Result: VERIFIED / CHANGED_JOB / UNVERIFIABLE
  ▼
Gate 3: Spider + Jina Rescue                ─── $0.002/lead
  │    For "unknown" from Gate 2
  │    Google search → HTML extraction → employment proof
  ▼
Results written to DuckDB → CSV export → EmailBison import
```

## Key Patterns
- **ContractRefinery** orchestrates the full pipeline end-to-end
- **Modular email verifier** with swappable provider backends
- **Fuzzy matching** with rapidfuzz + configurable thresholds
- **DuckDB** for lightweight columnar storage (no DB server needed)
- **Staging table pattern** for safe bulk updates
- **API key auth** with admin/user role separation
- **Lead locking** via client_contract_id prevents reuse across contracts
"""


@mcp.tool()
def get_db_schema() -> str:
    """Get the complete database schema including all columns, types,
    indexes, and the migration system. Also returns the raw
    schema_migrations.py source for full context.

    Reads from Foam documentation (docs/database/schema.md) when available.
    """
    schema_file = os.path.join(PROJECT_DIR, "schema_migrations.py")
    schema_content = ""
    if os.path.exists(schema_file):
        with open(schema_file, "r", encoding="utf-8") as f:
            schema_content = f.read()

    doc_path = os.path.join(PROJECT_DIR, "docs", "database", "schema.md")
    if os.path.exists(doc_path):
        content = _read_doc(doc_path)
        if schema_content:
            content += f"\n\n---\n\n## schema_migrations.py (source)\n\n```python\n{schema_content}\n```"
        return content

    # Fallback: hardcoded content
    return f"""# LinkedIn Scanner - Database Schema

## Database: DuckDB (linkedin.duckdb)
## Primary Table: contacts (~75M rows)

### Original Columns
| Column | Type | Description |
|--------|------|-------------|
| id | INTEGER | Unique row identifier |
| Emails | VARCHAR | Email address(es) |
| First Name | VARCHAR | First name |
| Last Name | VARCHAR | Last name |
| Full name | VARCHAR | Full name |
| Company Name | VARCHAR | Current employer |
| Job title | VARCHAR | Job title |
| LinkedIn Url | VARCHAR | LinkedIn profile URL |
| Industry | VARCHAR | Industry classification |
| Company Size | VARCHAR | Range (e.g. "51-200") |
| Location | VARCHAR | Geographic location |
| Skills | VARCHAR | LinkedIn skills |
| Region | VARCHAR | US state/region |
| Inferred Salary | VARCHAR | Salary range (e.g. "$100K-150K") |
| Years Experience | VARCHAR | Career tenure |
| Company Website | VARCHAR | Company domain |
| Phone numbers | VARCHAR | Phone numbers |
| Mobile | VARCHAR | Mobile number |
| Source State | VARCHAR | State field |
| Summary | VARCHAR | LinkedIn summary |

### Columns Added via Migrations
| Column | Type | Description |
|--------|------|-------------|
| client_contract_id | VARCHAR | Contract ownership lock (prevents lead reuse) |
| spider_verification_url | VARCHAR | Proof URL from Gate 3 rescue layer |
| validation_status | VARCHAR | pending / verified / dead / changed_job / unverifiable / updated |
| validation_source | VARCHAR | email_check / aiark / spider / manual |
| validated_at | TIMESTAMP | When validation last occurred |
| enriched_data | VARCHAR | JSON blob with enrichment payload |
| email_verified | BOOLEAN | Email verification flag |
| bounce_reason | VARCHAR | Bounce classification |

### Indexes
- `idx_client_contract_id` on (client_contract_id)
- `idx_validation_contract` on (validation_status, client_contract_id)

### Migration System
Managed by schema_migrations.py. Uses idempotent ALTER TABLE with column
existence checks before adding. Safe to run multiple times.

### Freshness Tiers
- Fresh: < 30 days since validated_at
- Recent: 30-90 days
- Stale: 90-180 days
- Expired: > 180 days

---

## schema_migrations.py (source)

```python
{schema_content}
```
"""


@mcp.tool()
def get_api_endpoints() -> str:
    """Get all API endpoints with methods, paths, auth requirements,
    and descriptions. Sourced from api_production.py.

    Reads from Foam documentation (docs/api/endpoints.md) when available.
    """
    doc_path = os.path.join(PROJECT_DIR, "docs", "api", "endpoints.md")
    if os.path.exists(doc_path):
        return _read_doc(doc_path)

    # Fallback: hardcoded content
    return """# LinkedIn Scanner - API Endpoints (api_production.py)

## Authentication
All endpoints require `X-API-Key` header.
Roles: `admin` (full access), `user` (read + search).

## Health & Info
| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/` | No | Health check |
| GET | `/docs` | No | Swagger UI |
| GET | `/version` | No | API version info |

## Lead Search
| Method | Path | Auth | Description |
|--------|------|------|-------------|
| POST | `/leads/search` | user | Search with complex ICP filters |
| GET | `/leads/{lead_id}` | user | Get single lead by ID |
| POST | `/leads/export` | admin | Export filtered leads to CSV |

## Analytics
| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/stats` | user | DB stats (total, verified, dead) |
| GET | `/filters/industries` | user | Available industry values |
| GET | `/filters/states` | user | Available state values |
| GET | `/filters/company-sizes` | user | Available company size values |

## Validation Pipeline
| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/validation/stats` | user | Validation counts by status |
| POST | `/validation/get-batch` | admin | Batch of leads needing validation |
| POST | `/validation/update` | admin | Bulk update validation results |
| POST | `/validation/mark-dead` | admin | Mark leads as dead/bounced |
| GET | `/validation/dead-leads` | user | Review dead leads |

## Contract Management
| Method | Path | Auth | Description |
|--------|------|------|-------------|
| POST | `/contracts/create` | admin | Create & run contract (full pipeline) |
| GET | `/contracts/{client_id}/status` | user | Contract execution status |
| GET | `/contracts/{client_id}/export` | admin | Export contract leads as CSV |
| GET | `/contracts/list` | user | List all contracts |

## EmailBison Integration
| Method | Path | Auth | Description |
|--------|------|------|-------------|
| POST | `/emailbison/search` | user | Search & format for EmailBison |
| POST | `/emailbison/export-csv` | admin | CSV export for EmailBison |
| GET | `/emailbison/icp-stats` | user | ICP planning statistics |

## Lead Ingestion
| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/ingestion/search` | user | Search by email/LinkedIn URL |
| GET | `/ingestion/sources` | user | Source statistics |
| POST | `/ingestion/check-duplicates` | user | Duplicate detection |

## Freshness System
| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/freshness/stats` | user | Freshness tier statistics |
| GET | `/freshness/queue` | user | Priority re-validation queue |
| GET | `/freshness/estimate` | user | Cost estimate for updates |
| GET | `/freshness/stale-leads` | user | Stale leads needing refresh |
| POST | `/freshness/get-batch` | admin | Batch for freshness validation |
"""


@mcp.tool()
def get_pipeline_overview() -> str:
    """Get detailed overview of the waterfall verification pipeline
    including all gates, providers, cost models, yield expectations,
    and key data models.

    Reads from Foam documentation (docs/pipeline/overview.md) when available.
    """
    doc_path = os.path.join(PROJECT_DIR, "docs", "pipeline", "overview.md")
    if os.path.exists(doc_path):
        return _read_doc(doc_path)

    # Fallback: hardcoded content
    return """# Waterfall Verification Pipeline

## Pipeline Stages

### Gate 0: Pre-validation (gate0_prevalidation.py)
- DNS/MX record validation
- Email syntax checking
- Filters obvious invalids before paid APIs
- Cost: $0 (local checks)
- Yield: Removes ~10-15% bad emails

### Gate 1: Email Verification (contract_refinery/email_verifier.py)
- Providers (modular, swappable):
  - LeadMagic ($0.01/email, pack pricing)
  - Reoon ($0.0007/email, cheapest)
  - ZeroBounce ($0.01/email, highest accuracy)
- Results: valid / invalid / catch_all / unknown
- Features: Rate limiting, retry logic, session management, provider abstraction
- Yield: ~70% pass rate

### Gate 2: AI-ARK Enrichment (aiark_client.py)
- Endpoint: POST /v1/people (people search API)
- Flow: Name + Company → API lookup → fuzzy company match
- Matching: rapidfuzz with 80% threshold (contract_refinery/matching.py)
- Results: VERIFIED / CHANGED_JOB / UNVERIFIABLE
- Cost: 0.5 credits ($0.005) per enrichment
- Yield: ~60% verified

### Gate 3: Spider + Jina Rescue (contract_refinery/rescue_layer.py)
- For leads marked "unknown" by Gate 2
- spider_client.py: Google search for LinkedIn profile
- jina_client.py: Extract HTML to verify current employment
- Stores proof URL in spider_verification_url column
- Cost: ~$0.002 per attempt
- Yield: ~30% rescue rate

## Cost Model
| Gate | Per Lead | Cumulative |
|------|----------|-----------|
| Gate 0 | Free | $0 |
| Gate 1 | ~$0.003 | $0.003 |
| Gate 2 | ~$0.005 | $0.008 |
| Gate 3 | ~$0.002 | $0.010 |
| **Average total** | | **~$0.015/lead** |

## Contract Execution (contract_refinery/refinery.py)
1. Load ContractConfig (target count, ICP filters, multiplier)
2. Query DuckDB for raw leads matching filters (target x multiplier)
3. Lock leads with client_contract_id (prevents reuse)
4. Run through gates sequentially
5. Save results to DuckDB (validation_status, validation_source, etc.)
6. Export verified leads to CSV
7. Return ContractResult with gate-level stats

## Key Data Models (contract_refinery/models.py)
- `RawLead` - Input lead from DuckDB
- `EmailCheckResult` - Gate 1 output per email
- `LeadValidationResult` - Per-lead pipeline result
- `WaterfallResult` - Batch statistics by gate
- `ContractResult` - Final contract summary + export path
- `ValidationStatus` enum: pending, verified, dead, changed_job, unverifiable, updated
- `ValidationSource` enum: email_check, aiark, spider, manual

## Config Models (contract_refinery/config.py)
- `ContractConfig` - Top-level: client_id, target, multiplier, filters, flags
- `ContractFilters` - ICP definition: industries, titles, sizes, states, excludes
"""


@mcp.tool()
def search_project(
    query: str,
    file_pattern: str = "*.py",
    teammate: str = "anonymous",
) -> str:
    """Search project files for a keyword or phrase (case-insensitive).

    Args:
        query: Search term to find in file contents.
        file_pattern: Glob pattern to filter files.
            Examples: "*.py", "*.md", "contract_refinery/*.py", "*"
        teammate: Your name (for logging).

    Returns:
        Matching lines with file paths and line numbers.
    """
    start = time.time()
    results = []
    search_dir = Path(PROJECT_DIR)

    if file_pattern == "*":
        patterns = [
            "**/*.py", "**/*.md", "**/*.json", "**/*.yml",
            "**/*.yaml", "**/*.txt", "**/*.toml", "**/*.cfg",
        ]
    else:
        patterns = [f"**/{file_pattern}"] if "/" not in file_pattern else [file_pattern]

    files_searched = 0
    timed_out = False
    for pattern in patterns:
        for filepath in search_dir.glob(pattern):
            if time.time() - start > SEARCH_TIMEOUT:
                timed_out = True
                break
            if not filepath.is_file():
                continue
            if any(skip in str(filepath) for skip in [".git", "__pycache__", "node_modules", ".duckdb"]):
                continue
            try:
                content = filepath.read_text(encoding="utf-8", errors="ignore")
                files_searched += 1
                for i, line in enumerate(content.split("\n"), 1):
                    if query.lower() in line.lower():
                        rel_path = filepath.relative_to(search_dir)
                        results.append(f"{rel_path}:{i}: {line.strip()}")
                        if len(results) >= 50:
                            break
            except Exception:
                continue
            if len(results) >= 50:
                break
        if len(results) >= 50 or timed_out:
            break

    duration_ms = int((time.time() - start) * 1000)

    output = f"Search: '{query}' in {file_pattern} ({files_searched} files)\n"
    output += f"Found {len(results)} match(es):\n\n"
    output += "\n".join(results[:50])
    if timed_out:
        output += f"\n\n(search timed out after {SEARCH_TIMEOUT}s — {files_searched} files searched, results may be incomplete)"
    elif len(results) >= 50:
        output += "\n\n(truncated at 50 results)"

    log_query(teammate, "search_project", query, file_pattern, output, duration_ms)
    return output


@mcp.tool()
def get_file(path: str, teammate: str = "anonymous") -> str:
    """Read a specific project file by its relative path.

    Args:
        path: Relative path from project root.
            Examples: "contract_refinery/models.py", "api_production.py"
        teammate: Your name (for logging).

    Returns:
        File contents with line numbers, or error message.
    """
    start = time.time()
    full_path = os.path.join(PROJECT_DIR, path)

    # Prevent path traversal
    real_path = os.path.realpath(full_path)
    real_project = os.path.realpath(PROJECT_DIR)
    if not real_path.startswith(real_project):
        return "Error: path traversal not allowed."

    if not os.path.exists(full_path):
        return f"Error: file not found: {path}"
    if not os.path.isfile(full_path):
        return f"Error: not a file: {path}"

    try:
        with open(full_path, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read()

        duration_ms = int((time.time() - start) * 1000)
        log_query(teammate, "get_file", path, "", content[:200], duration_ms, [path])

        lines = content.split("\n")
        numbered = "\n".join(f"{i + 1:4d} | {line}" for i, line in enumerate(lines))
        return f"# {path} ({len(lines)} lines)\n\n{numbered}"

    except Exception as e:
        return f"Error reading file: {e}"


@mcp.tool()
def list_files(directory: str = "") -> str:
    """List files and subdirectories in a project directory.

    Args:
        directory: Relative path from project root.
            Empty string or omit for the project root.

    Returns:
        Directory listing with file sizes.
    """
    target = os.path.join(PROJECT_DIR, directory) if directory else PROJECT_DIR

    real_path = os.path.realpath(target)
    real_project = os.path.realpath(PROJECT_DIR)
    if not real_path.startswith(real_project):
        return "Error: path traversal not allowed."

    if not os.path.isdir(target):
        return f"Error: not a directory: {directory or '(root)'}"

    items = []
    for item in sorted(os.listdir(target)):
        if item.startswith(".") or item in ("__pycache__", "node_modules"):
            continue
        full = os.path.join(target, item)
        if os.path.isdir(full):
            items.append(f"  [dir]  {item}/")
        else:
            size = os.path.getsize(full)
            if size > 1024 * 1024:
                sz = f"{size / (1024 * 1024):.1f}MB"
            elif size > 1024:
                sz = f"{size / 1024:.1f}KB"
            else:
                sz = f"{size}B"
            items.append(f"  {sz:>8s}  {item}")

    return f"# {directory or '(project root)'}\n\n" + "\n".join(items)


# ---------------------------------------------------------------------------
# Database Tools
# ---------------------------------------------------------------------------

@mcp.tool()
def query_database(
    sql: str,
    teammate: str = "anonymous",
    max_rows: int = 100,
) -> str:
    """Run a read-only SQL query against the project's DuckDB database (75M+ contacts).

    The database file is linkedin.duckdb with a main table called `contacts`.
    Use get_db_schema() first to understand the available columns.

    Args:
        sql: A SELECT query to run. Only SELECT statements are allowed.
            Examples:
                "SELECT COUNT(*) FROM contacts"
                "SELECT \"Job title\", COUNT(*) as cnt FROM contacts GROUP BY 1 ORDER BY 2 DESC LIMIT 20"
                "SELECT * FROM contacts WHERE \"Company Name\" ILIKE '%google%' LIMIT 10"
            Note: Column names with spaces require double quotes (e.g. "Job title").
        teammate: Your name (for query logging).
        max_rows: Maximum rows to return (default 100, max 1000).

    Returns:
        Query results as a formatted table, or error message.
    """
    try:
        import duckdb
    except ImportError:
        return "DuckDB is not installed in this container. Contact the project owner."

    # Validate: SELECT only
    sql_stripped = sql.strip().rstrip(";").strip()
    if not sql_stripped:
        return "Empty query. Please provide a SELECT statement."

    first_word = sql_stripped.split()[0].upper()
    blocked = [
        "INSERT", "UPDATE", "DELETE", "DROP", "ALTER", "CREATE",
        "TRUNCATE", "REPLACE", "MERGE", "GRANT", "REVOKE",
        "ATTACH", "DETACH", "COPY", "EXPORT", "IMPORT",
    ]

    if first_word != "SELECT":
        return (
            f"Only SELECT queries are allowed (got '{first_word}'). "
            "This is a read-only interface.\n"
            "Example: SELECT COUNT(*) FROM contacts"
        )

    max_rows = min(max_rows, 1000)
    db_path = os.path.join(PROJECT_DIR, "linkedin.duckdb")
    if not os.path.exists(db_path):
        return "Database file linkedin.duckdb not found in the project directory."

    start = time.time()

    # Run query in a thread with timeout to prevent long-running scans from
    # blocking the server.  DuckDB has no native Python query timeout, so we
    # use concurrent.futures + conn.interrupt() to cancel on timeout.
    conn_holder = {}

    def _run_query():
        c = duckdb.connect(db_path, read_only=True)
        conn_holder["conn"] = c
        try:
            res = c.execute(sql_stripped).fetchmany(max_rows)
            cols = [desc[0] for desc in c.description]
            return res, cols
        finally:
            c.close()

    try:
        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(_run_query)
            try:
                result, columns = future.result(timeout=QUERY_TIMEOUT)
            except FuturesTimeoutError:
                if "conn" in conn_holder:
                    try:
                        conn_holder["conn"].interrupt()
                    except Exception:
                        pass
                duration_ms = int((time.time() - start) * 1000)
                log_query(teammate, "query_database", sql, "database", "TIMEOUT", duration_ms)
                return (
                    f"Query timed out after {QUERY_TIMEOUT}s. "
                    "Try adding LIMIT, filtering with WHERE, or simplifying aggregations.\n\n"
                    f"SQL: {sql_stripped}"
                )

        duration_ms = int((time.time() - start) * 1000)

        if not result:
            log_query(teammate, "query_database", sql, "database", "0 rows", duration_ms)
            return f"Query returned 0 rows.\n\nSQL: {sql_stripped}"

        # Format as table
        col_widths = [len(str(c)) for c in columns]
        str_rows = []
        for row in result:
            cells = []
            for i, val in enumerate(row):
                s = str(val) if val is not None else "NULL"
                if len(s) > 60:
                    s = s[:57] + "..."
                cells.append(s)
                col_widths[i] = min(max(col_widths[i], len(s)), 60)
            str_rows.append(cells)

        header = " | ".join(c.ljust(col_widths[i]) for i, c in enumerate(columns))
        separator = "-+-".join("-" * w for w in col_widths)

        row_lines = []
        for cells in str_rows:
            row_lines.append(" | ".join(cells[i].ljust(col_widths[i]) for i in range(len(cells))))

        output = f"Query: {sql_stripped}\n"
        output += f"Rows: {len(result)}{' (limit reached)' if len(result) == max_rows else ''}\n"
        output += f"Time: {duration_ms}ms\n\n"
        output += header + "\n"
        output += separator + "\n"
        output += "\n".join(row_lines)

        log_query(teammate, "query_database", sql, "database", output[:500], duration_ms)
        return output

    except FuturesTimeoutError:
        pass  # Already handled above

    except Exception as e:
        duration_ms = int((time.time() - start) * 1000)
        error_msg = str(e)
        log_query(teammate, "query_database", sql, "database", f"ERROR: {error_msg}", duration_ms)
        return (
            f"Query error: {error_msg}\n\n"
            f"SQL: {sql_stripped}\n\n"
            "Tip: Column names with spaces need double quotes, e.g. \"Job title\""
        )


# ---------------------------------------------------------------------------
# Notes & Collaboration Tools
# ---------------------------------------------------------------------------

@mcp.tool()
def submit_note(
    teammate: str,
    note_type: str,
    title: str,
    body: str,
    related_files: str = "",
    related_code: str = "",
) -> str:
    """Leave a note for the project owner with context, ideas, or findings.

    Use this after researching the codebase to share what you learned,
    propose a feature, flag a bug, or document how you plan to integrate.

    Args:
        teammate: Your name (required — so the owner knows who wrote it).
        note_type: One of:
            feature_idea  - A new feature or extension you want to build
            bug           - A bug, inconsistency, or issue you found
            insight       - Something you learned that others should know
            integration   - How you plan to integrate with this project
            question      - A question that ask_project couldn't fully answer
            architecture  - Feedback on the current architecture or patterns
        title: Short summary (1 line) of the note.
        body: Full context. Include:
            - What you found or what you're proposing
            - Which files/functions are relevant
            - Your reasoning or approach
            - Any open questions for the owner
        related_files: Comma-separated file paths this note references.
            Example: "contract_refinery/email_verifier.py,api_production.py"
        related_code: Optional code snippet or pseudocode illustrating your idea.

    Returns:
        Note ID for future reference.
    """
    valid_types = ["feature_idea", "bug", "insight", "integration", "question", "architecture"]
    if note_type not in valid_types:
        return f"Invalid note_type '{note_type}'. Must be one of: {', '.join(valid_types)}"

    if not teammate or teammate == "anonymous":
        return "Please provide your name in the 'teammate' field so the owner knows who left the note."

    note_id = str(uuid.uuid4())[:8]
    files_list = [f.strip() for f in related_files.split(",") if f.strip()] if related_files else []
    timestamp = datetime.now()
    date_str = timestamp.strftime("%Y-%m-%d")
    time_str = timestamp.strftime("%H:%M")

    # Write markdown file to notes directory
    md_filename = f"{date_str}-{teammate}-{note_type}-{note_id}.md"
    md_path = os.path.join(NOTES_DIR, md_filename)

    # Build markdown content
    md_content = f"""# {title}

**From:** {teammate}
**Type:** {note_type}
**Date:** {date_str} {time_str}
**ID:** {note_id}
**Status:** new

---

{body}
"""
    if files_list:
        md_content += f"\n## Related Files\n\n"
        for f in files_list:
            md_content += f"- `{f}`\n"

    if related_code:
        md_content += f"\n## Code Reference\n\n```\n{related_code}\n```\n"

    try:
        os.makedirs(NOTES_DIR, exist_ok=True)
        with open(md_path, "w", encoding="utf-8") as f:
            f.write(md_content)
    except Exception as e:
        return f"Failed to write note file: {e}"

    # Also save to SQLite for querying/filtering
    try:
        conn = sqlite3.connect(LOG_DB)
        conn.execute(
            """INSERT INTO notes
               (id, teammate, note_type, title, body, related_files, related_code)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (note_id, teammate, note_type, title, body, json.dumps(files_list), related_code),
        )
        conn.commit()
        conn.close()
    except Exception as e:
        # Note file was written, just log the DB error
        pass

    # Also log to query_log for unified activity feed
    log_query(teammate, "submit_note", title, note_type, body, 0, files_list)

    return (
        f"Note saved.\n\n"
        f"  ID: {note_id}\n"
        f"  Type: {note_type}\n"
        f"  From: {teammate}\n"
        f"  Title: {title}\n"
        f"  File: .notes/{md_filename}\n"
        f"  Status: new (owner will review)\n\n"
        f"The project owner will see this note in their .notes/ folder."
    )


@mcp.tool()
def get_notes(
    filter_type: str = "",
    filter_teammate: str = "",
    filter_status: str = "",
    last_n: int = 20,
) -> str:
    """Read notes left by teammates, with optional filters.

    Args:
        filter_type: Filter by note type (feature_idea, bug, insight,
            integration, question, architecture). Empty for all.
        filter_teammate: Filter by teammate name. Empty for all.
        filter_status: Filter by status (new, reviewed, planned,
            in_progress, implemented, wont_do). Empty for all.
        last_n: Max notes to return (default 20).

    Returns:
        Formatted list of notes with full context.
    """
    try:
        conn = sqlite3.connect(LOG_DB)
        query = "SELECT id, teammate, note_type, title, body, related_files, related_code, status, owner_response, created_at, updated_at FROM notes WHERE 1=1"
        params = []

        if filter_type:
            query += " AND note_type = ?"
            params.append(filter_type)
        if filter_teammate:
            query += " AND teammate = ?"
            params.append(filter_teammate)
        if filter_status:
            query += " AND status = ?"
            params.append(filter_status)

        query += " ORDER BY created_at DESC LIMIT ?"
        params.append(last_n)

        cursor = conn.execute(query, params)
        rows = cursor.fetchall()
        conn.close()

        if not rows:
            filters = []
            if filter_type:
                filters.append(f"type={filter_type}")
            if filter_teammate:
                filters.append(f"teammate={filter_teammate}")
            if filter_status:
                filters.append(f"status={filter_status}")
            filter_str = f" (filters: {', '.join(filters)})" if filters else ""
            return f"No notes found{filter_str}."

        output = f"# Notes ({len(rows)} found)\n\n"
        for row in rows:
            (note_id, teammate, ntype, title, body, files_json,
             code, status, owner_resp, created, updated) = row

            files = json.loads(files_json) if files_json else []
            status_icon = {
                "new": "[NEW]",
                "reviewed": "[REVIEWED]",
                "planned": "[PLANNED]",
                "in_progress": "[IN PROGRESS]",
                "implemented": "[DONE]",
                "wont_do": "[WON'T DO]",
            }.get(status, f"[{status.upper()}]")

            output += f"## {status_icon} {title}\n"
            output += f"**ID:** {note_id} | **From:** {teammate} | **Type:** {ntype}\n"
            output += f"**Created:** {created}"
            if updated != created:
                output += f" | **Updated:** {updated}"
            output += "\n\n"
            output += f"{body}\n"

            if files:
                output += f"\n**Related files:** {', '.join(files)}\n"
            if code:
                output += f"\n**Code/pseudocode:**\n```\n{code}\n```\n"
            if owner_resp:
                output += f"\n**Owner response:** {owner_resp}\n"
            output += "\n---\n\n"

        return output

    except Exception as e:
        return f"Error reading notes: {e}"


@mcp.tool()
def update_note(
    note_id: str,
    status: str = "",
    owner_response: str = "",
) -> str:
    """Update a note's status and add an owner response.

    Use this as the project owner to respond to teammate notes,
    mark them as planned/in-progress/implemented, or decline them.

    Args:
        note_id: The note ID (returned by submit_note or visible in get_notes).
        status: New status. One of:
            reviewed    - Acknowledged, thinking about it
            planned     - Will implement
            in_progress - Currently working on it
            implemented - Done, shipped
            wont_do     - Declining with reason in owner_response
        owner_response: Your response to the teammate. Explain your decision,
            ask follow-up questions, or share next steps.

    Returns:
        Updated note summary.
    """
    valid_statuses = ["reviewed", "planned", "in_progress", "implemented", "wont_do"]
    if status and status not in valid_statuses:
        return f"Invalid status '{status}'. Must be one of: {', '.join(valid_statuses)}"

    if not status and not owner_response:
        return "Provide at least a status or an owner_response."

    try:
        conn = sqlite3.connect(LOG_DB)

        # Verify note exists
        cursor = conn.execute("SELECT id, teammate, title, status FROM notes WHERE id = ?", (note_id,))
        row = cursor.fetchone()
        if not row:
            conn.close()
            return f"Note '{note_id}' not found."

        old_status = row[3]
        updates = []
        params = []

        if status:
            updates.append("status = ?")
            params.append(status)
        if owner_response:
            updates.append("owner_response = ?")
            params.append(owner_response)

        updates.append("updated_at = datetime('now')")
        params.append(note_id)

        conn.execute(
            f"UPDATE notes SET {', '.join(updates)} WHERE id = ?",
            params,
        )
        conn.commit()
        conn.close()

        result = f"Note '{note_id}' updated.\n\n"
        result += f"  Title: {row[2]}\n"
        result += f"  From: {row[1]}\n"
        if status:
            result += f"  Status: {old_status} -> {status}\n"
        if owner_response:
            result += f"  Response: {owner_response[:200]}\n"

        return result

    except Exception as e:
        return f"Error updating note: {e}"


# ---------------------------------------------------------------------------
# Git & Activity Tools
# ---------------------------------------------------------------------------

@mcp.tool()
def get_recent_changes(last_n: int = 20, path_filter: str = "") -> str:
    """Show recent git commits to see what changed in the project.

    Useful for understanding what the project owner has been working on,
    what files were recently modified, and the direction of development.

    Args:
        last_n: Number of recent commits to show (default 20).
        path_filter: Optional path to filter commits by.
            Example: "contract_refinery/" to see only pipeline changes.

    Returns:
        Git log with commit messages, authors, dates, and changed files.
    """
    cmd = [
        "git", "log",
        f"--max-count={last_n}",
        "--format=%h | %ar | %an | %s",
        "--name-only",
    ]
    if path_filter:
        cmd.append("--")
        cmd.append(path_filter)

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=15,
            cwd=PROJECT_DIR,
        )

        if result.returncode != 0:
            error = result.stderr or ""
            if "not a git repository" in error:
                return (
                    "This project is not a git repository. "
                    "No commit history available."
                )
            return f"Git error: {error[:300]}"

        output = result.stdout.strip()
        if not output:
            return "No commits found" + (f" for path '{path_filter}'" if path_filter else "") + "."

        return f"# Recent Changes (last {last_n} commits)\n\n```\n{output}\n```"

    except FileNotFoundError:
        return "Git is not installed in this container."
    except subprocess.TimeoutExpired:
        return "Git log timed out."
    except Exception as e:
        return f"Error running git log: {e}"


@mcp.tool()
def get_query_log(last_n: int = 20) -> str:
    """View recent query log entries to see what teammates have been asking.
    Useful for identifying documentation gaps and common confusion points.

    Args:
        last_n: Number of recent entries to return (default 20).
    """
    try:
        conn = sqlite3.connect(LOG_DB)
        cursor = conn.execute(
            """SELECT teammate, tool_name, question, context_area,
                      response_length, duration_ms, created_at
               FROM query_log ORDER BY id DESC LIMIT ?""",
            (last_n,),
        )
        rows = cursor.fetchall()
        conn.close()

        if not rows:
            return "No queries logged yet."

        output = f"# Recent Queries (last {len(rows)})\n\n"
        for teammate, tool, question, area, resp_len, duration, created in rows:
            output += f"**{created}** | {teammate} | `{tool}`"
            if area:
                output += f" | area={area}"
            output += f"\n  Q: {question[:120]}\n"
            output += f"  Response: {resp_len} chars, {duration}ms\n\n"

        return output
    except Exception as e:
        return f"Error reading log: {e}"


# ---------------------------------------------------------------------------
# Auth Middleware
# ---------------------------------------------------------------------------

ASSISTANT_API_KEY = os.getenv("ASSISTANT_API_KEY", "")


class BearerAuthMiddleware:
    """ASGI middleware that requires a valid Bearer token on all HTTP requests.

    Checks the Authorization header against the ASSISTANT_API_KEY env var.
    If no key is set, all requests pass through (open access).
    """

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http" and ASSISTANT_API_KEY:
            from starlette.responses import JSONResponse

            headers = dict(scope.get("headers", []))
            auth_value = headers.get(b"authorization", b"").decode()

            if auth_value != f"Bearer {ASSISTANT_API_KEY}":
                response = JSONResponse(
                    {"error": "Unauthorized — valid Bearer token required"},
                    status_code=401,
                )
                await response(scope, receive, send)
                return

        await self.app(scope, receive, send)


class RequestTimeoutMiddleware:
    """ASGI middleware that enforces a global timeout on every HTTP request.

    If any request (including long-running MCP tool calls) exceeds
    REQUEST_TIMEOUT seconds, the client receives a 504 instead of hanging.
    This is the safety net below Cloudflare's hard 100s proxy read timeout.
    """

    def __init__(self, app, timeout: int = 95):
        self.app = app
        self.timeout = timeout

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        import asyncio

        try:
            await asyncio.wait_for(
                self.app(scope, receive, send),
                timeout=self.timeout,
            )
        except asyncio.TimeoutError:
            from starlette.responses import JSONResponse

            response = JSONResponse(
                {"error": f"Request timed out after {self.timeout}s"},
                status_code=504,
            )
            await response(scope, receive, send)


# ---------------------------------------------------------------------------
# Startup
# ---------------------------------------------------------------------------
init_db()

if __name__ == "__main__":
    transport = os.getenv("MCP_TRANSPORT", "stdio")
    if transport == "http":
        import uvicorn

        host = os.getenv("FASTMCP_HOST", "0.0.0.0")
        port = int(os.getenv("FASTMCP_PORT", "3000"))

        print(f"Project Assistant MCP server starting on http://{host}:{port}/mcp")
        print(f"Project directory: {PROJECT_DIR}")
        print(f"Query log: {LOG_DB}")

        # Get the Starlette ASGI app from FastMCP
        app = mcp.streamable_http_app()

        # Middleware stack (outermost applied first):
        # 1. Request timeout — catches hangs before Cloudflare's 100s edge limit
        # 2. Bearer auth — rejects unauthenticated requests before any work
        if ASSISTANT_API_KEY:
            app = BearerAuthMiddleware(app)
            print("Bearer token auth: ENABLED")
        else:
            print("Bearer token auth: DISABLED (set ASSISTANT_API_KEY to enable)")

        app = RequestTimeoutMiddleware(app, timeout=REQUEST_TIMEOUT)
        print(f"Request timeout: {REQUEST_TIMEOUT}s")

        uvicorn.run(
            app,
            host=host,
            port=port,
            timeout_keep_alive=30,
            timeout_graceful_shutdown=15,
        )
    else:
        mcp.run()
