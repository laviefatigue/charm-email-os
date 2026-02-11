"""
MCP Server providing strategy generation tools to Claude Code.

This server gives Claude the ability to:
- Get client context including onboarding data, segments, and personas
- Get feedback summary from previous strategy generations
- Save campaign variants for human review
- Mark generation jobs as complete

LOCAL_MODE: When STRATEGY_LOCAL_MODE=true, output is saved to local filesystem
instead of the production database. This enables local testing and validation.
"""
import json
import os
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional
import psycopg2
from psycopg2.extras import RealDictCursor, Json
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

# Local mode configuration
LOCAL_MODE = os.getenv("STRATEGY_LOCAL_MODE", "false").lower() == "true"
LOCAL_OUTPUT_DIR = Path(os.getenv("STRATEGY_OUTPUT_DIR", "/app/test-output"))

# Debug: Log LOCAL_MODE status at startup
import sys
print(f"[MCP SERVER DEBUG] LOCAL_MODE={LOCAL_MODE}, STRATEGY_LOCAL_MODE env={os.getenv('STRATEGY_LOCAL_MODE', 'NOT SET')}", file=sys.stderr)

# Database configuration from environment
DB_CONFIG = {
    "host": os.getenv("POSTGRES_HOST", "localhost"),
    "port": int(os.getenv("POSTGRES_PORT", "5432")),
    "database": os.getenv("POSTGRES_DB", "postgres"),
    "user": os.getenv("POSTGRES_USER", "postgres"),
    "password": os.getenv("POSTGRES_PASSWORD", ""),
}


def save_locally(job_id: str, document: dict, filename: str = "campaign_document.json") -> str:
    """Save output to local filesystem instead of database (LOCAL_MODE only)."""
    job_dir = LOCAL_OUTPUT_DIR / "jobs" / job_id
    job_dir.mkdir(parents=True, exist_ok=True)

    # Add timestamp
    document["saved_at"] = datetime.now().isoformat()
    document["local_mode"] = True

    # Save document
    output_path = job_dir / filename
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(document, f, indent=2, ensure_ascii=False)

    # Update latest.json symlink/copy
    latest = LOCAL_OUTPUT_DIR / "latest.json"
    try:
        if latest.exists():
            latest.unlink()
        # On Windows, use copy instead of symlink
        if os.name == 'nt':
            import shutil
            shutil.copy(output_path, latest)
        else:
            latest.symlink_to(output_path)
    except Exception:
        pass  # Non-critical, continue even if latest link fails

    return str(output_path)

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
        ),
        # NOTE: save_campaign_batch removed - use save_campaign_document instead
        Tool(
            name="save_cycle_package",
            description="""[PREFERRED - Use for full strategy generation]
            Save a complete 4-campaign cycle package in one atomic operation.
            This creates a full 14-day cycle with 4 distinct campaign angles.

            Required structure:
            - cycle_config: Shared ICP, cycle variables, strategic focus
            - campaigns: Array of 4 campaign documents, each with:
              - angle: 'custom_signal', 'persona_pain', 'case_study', 'risk_efficiency'
              - campaign_variables: Variables unique to this campaign angle
              - email_positions: 4 positions with 2-3 variants each

            Campaign Angles:
            1. Custom Signal - Job postings, funding triggers, tool adoption
            2. Persona Pain - Role-specific overwhelm and challenges
            3. Case Study - Social proof with specific results
            4. Risk/Efficiency - Board pressure, ROI focus, efficiency gains

            All 4 campaigns share the ICP mapping and cycle variables.
            Each campaign has its own QA score + overall cycle score.""",
            inputSchema={
                "type": "object",
                "properties": {
                    "job_id": {
                        "type": "string",
                        "description": "The strategy generation job ID"
                    },
                    "cycle_name": {
                        "type": "string",
                        "description": "Cycle name (e.g., 'Q1 2026 Outbound Cycle')"
                    },
                    "cycle_config": {
                        "type": "object",
                        "description": "Shared cycle-level configuration",
                        "properties": {
                            "icp_mapping": {
                                "type": "object",
                                "description": "Target ICP, pain points, objections (shared across all 4 campaigns)"
                            },
                            "cycle_variables": {
                                "type": "array",
                                "description": "Variables at cycle level (apply to all campaigns)",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "name": {"type": "string"},
                                        "description": {"type": "string"},
                                        "source": {"type": "string"}
                                    }
                                }
                            },
                            "strategic_focus": {
                                "type": "string",
                                "description": "Overall strategic focus for this cycle"
                            },
                            "target_outcome": {
                                "type": "string",
                                "description": "Expected outcome from this cycle"
                            },
                            "vertical": {"type": "string"},
                            "objective": {"type": "string"}
                        }
                    },
                    "campaigns": {
                        "type": "array",
                        "description": "Array of 4 campaign documents",
                        "items": {
                            "type": "object",
                            "properties": {
                                "campaign_number": {"type": "integer", "description": "1-4"},
                                "campaign_name": {"type": "string"},
                                "angle": {
                                    "type": "string",
                                    "enum": ["custom_signal", "persona_pain", "case_study", "risk_efficiency"]
                                },
                                "campaign_variables": {
                                    "type": "array",
                                    "description": "Variables unique to this campaign angle",
                                    "items": {"type": "object"}
                                },
                                "email_positions": {
                                    "type": "array",
                                    "description": "4 email positions with variants"
                                },
                                "qa_scoring": {
                                    "type": "object",
                                    "description": "QA scoring for this campaign"
                                },
                                "strategy_notes": {
                                    "type": "object",
                                    "description": "Campaign-specific callouts and notes"
                                }
                            },
                            "required": ["campaign_number", "campaign_name", "angle", "email_positions"]
                        },
                        "minItems": 4,
                        "maxItems": 4
                    },
                    "overall_qa_score": {
                        "type": "integer",
                        "description": "Overall QA score for the entire cycle (0-100)"
                    },
                    "overall_verdict": {
                        "type": "string",
                        "description": "Cycle-level verdict (e.g., 'Ship it', 'Needs review')"
                    }
                },
                "required": ["job_id", "cycle_name", "cycle_config", "campaigns"]
            }
        ),
        Tool(
            name="save_cycle_scaffold",
            description="""[PHASED GENERATION - Phase 1]
            Create cycle structure with campaign stubs (no email content).
            This is the first phase of phased generation.

            Creates:
            - campaign_cycle record
            - cycle_strategy_config (ICP, cycle_variables)
            - 4 campaign_document stubs (angle, campaign_variables, no emails)

            After this completes, 4 campaign_copy phases should be triggered
            to generate emails for each campaign.

            Campaign angles:
            1. custom_signal - Job postings, funding triggers
            2. persona_pain - Role-specific overwhelm
            3. case_study - Social proof focus
            4. risk_efficiency - Board pressure, ROI""",
            inputSchema={
                "type": "object",
                "properties": {
                    "job_id": {
                        "type": "string",
                        "description": "The strategy generation job ID"
                    },
                    "client_id": {
                        "type": "string",
                        "description": "The client UUID"
                    },
                    "cycle_config": {
                        "type": "object",
                        "description": "Shared cycle-level configuration",
                        "properties": {
                            "icp_mapping": {"type": "object"},
                            "cycle_variables": {"type": "array"},
                            "strategic_focus": {"type": "string"},
                            "target_outcome": {"type": "string"},
                            "vertical": {"type": "string"},
                            "objective": {"type": "string"}
                        }
                    },
                    "campaigns": {
                        "type": "array",
                        "description": "Array of 4 campaign stubs (no email content)",
                        "items": {
                            "type": "object",
                            "properties": {
                                "campaign_number": {"type": "integer", "description": "1-4"},
                                "campaign_name": {"type": "string"},
                                "angle": {
                                    "type": "string",
                                    "enum": ["custom_signal", "persona_pain", "case_study", "risk_efficiency"]
                                },
                                "campaign_variables": {"type": "array"}
                            },
                            "required": ["campaign_number", "campaign_name", "angle"]
                        },
                        "minItems": 4,
                        "maxItems": 4
                    }
                },
                "required": ["job_id", "client_id", "cycle_config", "campaigns"]
            }
        ),
        Tool(
            name="get_campaign_context",
            description="""[PHASED GENERATION - Phase 2 Input]
            Fetch all context needed to generate one campaign's emails.
            Call this at the start of each campaign_copy phase.

            Returns merged context:
            - Client submission data (company, ICP, messaging)
            - Cycle config (ICP mapping, cycle variables, strategic focus)
            - Campaign stub (name, angle, campaign-level variables)

            Use this context to generate 4 email positions with 2-3 variants each.""",
            inputSchema={
                "type": "object",
                "properties": {
                    "job_id": {
                        "type": "string",
                        "description": "The strategy generation job ID"
                    },
                    "campaign_number": {
                        "type": "integer",
                        "description": "Which campaign (1-4) to get context for"
                    }
                },
                "required": ["job_id", "campaign_number"]
            }
        ),
        Tool(
            name="save_campaign_copy",
            description="""[PHASED GENERATION - Phase 2 Output]
            Save generated email copy to an existing campaign document stub.
            Updates the stub (created by save_cycle_scaffold) with full email content.

            Include for each position:
            - 2-3 variants with subject_line, email_body, word_count
            - One variant marked is_recommended=true
            - QA scoring for this campaign
            - Strategy notes

            All emails should be 50-90 words, with 3:1 them:us ratio.""",
            inputSchema={
                "type": "object",
                "properties": {
                    "job_id": {
                        "type": "string",
                        "description": "The strategy generation job ID"
                    },
                    "campaign_number": {
                        "type": "integer",
                        "description": "Which campaign (1-4) to save copy for"
                    },
                    "email_positions": {
                        "type": "array",
                        "description": "Array of 4 email positions with variants",
                        "items": {
                            "type": "object",
                            "properties": {
                                "position": {"type": "integer"},
                                "variants": {"type": "array"}
                            }
                        }
                    },
                    "qa_scoring": {
                        "type": "object",
                        "description": "QA scoring for this campaign"
                    },
                    "strategy_notes": {
                        "type": "object",
                        "description": "Strategy notes for this campaign"
                    },
                    "variable_schema": {
                        "type": "object",
                        "description": "Variables used in this campaign's emails"
                    }
                },
                "required": ["job_id", "campaign_number", "email_positions"]
            }
        ),
        Tool(
            name="save_campaign_document",
            description="""[SINGLE CAMPAIGN - Use for individual campaign generation]
            Save a complete campaign document in stablekernel format for human review.
            For full 4-campaign cycles, use save_cycle_package instead.

            Required structure:
            - icp_mapping: target_icp, pain_points (4 categories), objections (3 with preemption)
            - variable_schema: core, high_signal, ai_generated arrays with sources
            - email_positions: 4 positions with 2-3 variants each, is_recommended flags
            - qa_scoring: overall_score, verdict, 6 dimension breakdowns with notes
            - strategy_notes: callouts, data_enrichment, ab_testing arrays

            Mark one variant per position as is_recommended=true.""",
            inputSchema={
                "type": "object",
                "properties": {
                    "job_id": {
                        "type": "string",
                        "description": "The strategy generation job ID"
                    },
                    "document_name": {
                        "type": "string",
                        "description": "Document name (e.g., 'Financial Services Campaign v1')"
                    },
                    "vertical": {
                        "type": "string",
                        "description": "Target vertical/industry"
                    },
                    "objective": {
                        "type": "string",
                        "description": "Primary GTM objective"
                    },
                    "icp_mapping": {
                        "type": "object",
                        "description": "Target ICP, pain points, and objections",
                        "properties": {
                            "target_icp": {
                                "type": "object",
                                "properties": {
                                    "role": {"type": "string"},
                                    "company_type": {"type": "string"},
                                    "company_size": {"type": "string"}
                                }
                            },
                            "pain_points": {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "category": {"type": "string"},
                                        "label": {"type": "string"},
                                        "points": {"type": "array", "items": {"type": "string"}}
                                    }
                                }
                            },
                            "objections": {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "objection": {"type": "string"},
                                        "preemption": {"type": "string"}
                                    }
                                }
                            }
                        }
                    },
                    "variable_schema": {
                        "type": "object",
                        "description": "Variable definitions with sources",
                        "properties": {
                            "core": {"type": "array", "items": {"type": "object"}},
                            "high_signal": {"type": "array", "items": {"type": "object"}},
                            "ai_generated": {"type": "array", "items": {"type": "object"}}
                        }
                    },
                    "email_positions": {
                        "type": "array",
                        "description": "Array of 4 email positions with variants",
                        "items": {
                            "type": "object",
                            "properties": {
                                "position": {"type": "integer"},
                                "title": {"type": "string"},
                                "variants": {
                                    "type": "array",
                                    "items": {
                                        "type": "object",
                                        "properties": {
                                            "variant_number": {"type": "integer"},
                                            "variant_name": {"type": "string"},
                                            "is_recommended": {"type": "boolean"},
                                            "subject_line": {"type": ["string", "null"]},
                                            "email_body": {"type": "string"},
                                            "wait_days": {"type": "integer"},
                                            "thread_reply": {"type": "boolean"},
                                            "word_count": {"type": "integer"},
                                            "them_us_ratio": {"type": "string"},
                                            "score": {"type": "integer"},
                                            "angle": {"type": "string"},
                                            "strategy": {"type": "string"},
                                            "value_prop": {"type": "string"}
                                        }
                                    }
                                },
                                "subject_options": {
                                    "type": "array",
                                    "items": {
                                        "type": "object",
                                        "properties": {
                                            "subject_line": {"type": "string"},
                                            "rationale": {"type": "string"}
                                        }
                                    }
                                }
                            }
                        }
                    },
                    "sequence_summary": {
                        "type": "array",
                        "description": "Timeline steps for sequence overview",
                        "items": {
                            "type": "object",
                            "properties": {
                                "day": {"type": "string"},
                                "title": {"type": "string"},
                                "description": {"type": "string"}
                            }
                        }
                    },
                    "qa_scoring": {
                        "type": "object",
                        "description": "QA scoring breakdown for lead variant",
                        "properties": {
                            "overall_score": {"type": "integer"},
                            "verdict": {"type": "string"},
                            "dimensions": {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "name": {"type": "string"},
                                        "score": {"type": "string"},
                                        "notes": {"type": "string"}
                                    }
                                }
                            }
                        }
                    },
                    "strategy_notes": {
                        "type": "object",
                        "description": "Callouts, data enrichment, A/B testing",
                        "properties": {
                            "callouts": {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "type": {"type": "string"},
                                        "text": {"type": "string"}
                                    }
                                }
                            },
                            "data_enrichment": {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "variable": {"type": "string"},
                                        "source": {"type": "string"}
                                    }
                                }
                            },
                            "ab_testing": {"type": "array", "items": {"type": "string"}}
                        }
                    },
                    "used_variables": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Variables used across the document"
                    },
                    "missing_variables": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Variables referenced but not available"
                    }
                },
                "required": ["job_id", "document_name", "email_positions"]
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

            # Build context object with all available fields
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
                "hq_location": submission.get("hq_location") if submission else None,

                # Offering details
                "core_product": submission.get("core_product") if submission else onboarding.get("product"),
                "target_customer": submission.get("target_customer") if submission else None,
                "acv": submission.get("acv") if submission else None,
                "sales_cycle_length": submission.get("sales_cycle_length") if submission else None,
                "annual_revenue": submission.get("annual_revenue") if submission else None,
                "self_serve_pct": submission.get("self_serve_pct") if submission else None,

                # Market signals
                "buying_signals": submission.get("signals") if submission else [],
                "job_titles": submission.get("job_titles") if submission else [],

                # Competitive landscape (NEW)
                "competitors": submission.get("competitors") if submission else [],
                "key_differentiators": submission.get("key_differentiators") if submission else None,
                "common_objections": submission.get("common_objections") if submission else None,
                "buying_triggers_global": submission.get("buying_triggers_global") if submission else None,

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
                "case_studies": submission.get("case_studies") if submission else None,
                "industry_jargon": submission.get("industry_jargon") if submission else None,

                # Tech stack / Core vendors (NEW - for {{core_vendor}} variable)
                "core_vendors": submission.get("core_vendors") if submission else [],

                # Process & Performance (NEW)
                "monthly_volume": submission.get("monthly_volume") if submission else None,
                "current_open_rate": submission.get("current_open_rate") if submission else None,
                "current_reply_rate": submission.get("current_reply_rate") if submission else None,
                "other_channels": submission.get("other_channels") if submission else None,
                "messages_worked": submission.get("messages_worked") if submission else None,
                "approaches_failed": submission.get("approaches_failed") if submission else None,

                # Tools
                "outbound_tools": submission.get("outbound_tools") if submission else [],
                "crm": submission.get("crm") if submission else None,

                # Goals
                "primary_objective": submission.get("primary_gtm_objective") if submission else None,
                "success_metrics": submission.get("success_metrics") if submission else [],
                "success_definition": submission.get("success_definition") if submission else None,
                "engagement_win": submission.get("engagement_win") if submission else None,
                "additional_context": submission.get("additional_context") if submission else None,

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

        # LOCAL MODE: Save variant to local filesystem
        if LOCAL_MODE:
            job_dir = LOCAL_OUTPUT_DIR / "jobs" / job_id
            job_dir.mkdir(parents=True, exist_ok=True)

            # Load existing variants or create new list
            variants_file = job_dir / "variants.json"
            if variants_file.exists():
                with open(variants_file, "r", encoding="utf-8") as f:
                    variants = json.load(f)
            else:
                variants = {"job_id": job_id, "variants": [], "saved_at": None}

            # Add this variant
            variant_data = {
                "variant_number": variant_number,
                "subject_line": subject_line,
                "email_body": email_body,
                "score": score,
                "rationale": rationale,
                "used_variables": used_variables,
                "campaign_type": campaign_type,
                "original_suggestion_id": original_suggestion_id,
                "strategy_id": strategy_id,
                "saved_at": datetime.now().isoformat()
            }
            variants["variants"].append(variant_data)
            variants["saved_at"] = datetime.now().isoformat()

            # Save back
            with open(variants_file, "w", encoding="utf-8") as f:
                json.dump(variants, f, indent=2, ensure_ascii=False)

            revision_note = " (revision)" if original_suggestion_id else ""
            return [TextContent(type="text", text=f"[LOCAL MODE] Saved variant {variant_number}{revision_note}: {subject_line[:50]}... (score: {score or 'N/A'})\n"
                               f"Output: {variants_file}")]

        # PRODUCTION MODE: Save to database
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

        # LOCAL MODE: Just log completion
        if LOCAL_MODE:
            job_dir = LOCAL_OUTPUT_DIR / "jobs" / job_id
            metadata_path = job_dir / "metadata.json"

            if job_dir.exists():
                metadata = {
                    "job_id": job_id,
                    "status": "completed",
                    "completed_at": datetime.now().isoformat()
                }
                with open(metadata_path, "w") as f:
                    json.dump(metadata, f, indent=2)

            return [TextContent(type="text", text=f"[LOCAL MODE] Job {job_id} marked complete\n"
                               f"Output directory: {job_dir}\n\n"
                               f"To validate: python scripts/validate_output.py")]

        # PRODUCTION MODE: Update database
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

    elif name == "save_campaign_batch":
        # DEPRECATED: Return error directing to use save_campaign_document instead
        return [TextContent(type="text", text="""ERROR: save_campaign_batch is DEPRECATED and has been removed.

You MUST use save_campaign_document instead. This tool creates the stablekernel format with:
- icp_mapping (target_icp, pain_points, objections)
- variable_schema (core, high_signal, ai_generated)
- email_positions with variants
- qa_scoring with dimension breakdowns
- strategy_notes with callouts, enrichment, A/B testing

Please call save_campaign_document with the complete document structure.""")]

    elif name == "save_cycle_package":
        job_id = arguments["job_id"]
        cycle_name = arguments["cycle_name"]
        cycle_config = arguments["cycle_config"]
        campaigns = arguments["campaigns"]
        overall_qa_score = arguments.get("overall_qa_score")
        overall_verdict = arguments.get("overall_verdict")

        # Extract shared config
        icp_mapping = cycle_config.get("icp_mapping")
        cycle_variables = cycle_config.get("cycle_variables", [])
        strategic_focus = cycle_config.get("strategic_focus")
        target_outcome = cycle_config.get("target_outcome")
        vertical = cycle_config.get("vertical")
        objective = cycle_config.get("objective")

        # Count total variants across all campaigns
        total_variants = sum(
            sum(len(pos.get("variants", [])) for pos in c.get("email_positions", []))
            for c in campaigns
        )

        # LOCAL MODE: Save to filesystem
        if LOCAL_MODE:
            cycle_package = {
                "cycle_id": str(uuid.uuid4()),
                "job_id": job_id,
                "cycle_name": cycle_name,
                "cycle_config": {
                    "icp_mapping": icp_mapping,
                    "cycle_variables": cycle_variables,
                    "strategic_focus": strategic_focus,
                    "target_outcome": target_outcome,
                    "vertical": vertical,
                    "objective": objective
                },
                "campaigns": [],
                "overall_qa_score": overall_qa_score,
                "overall_verdict": overall_verdict,
                "created_at": datetime.now().isoformat()
            }

            # Process each campaign
            for campaign in campaigns:
                campaign_data = {
                    "campaign_id": str(uuid.uuid4()),
                    "campaign_number": campaign["campaign_number"],
                    "campaign_name": campaign["campaign_name"],
                    "angle": campaign["angle"],
                    "campaign_variables": campaign.get("campaign_variables", []),
                    "email_positions": campaign.get("email_positions", []),
                    "qa_scoring": campaign.get("qa_scoring"),
                    "strategy_notes": campaign.get("strategy_notes")
                }
                cycle_package["campaigns"].append(campaign_data)

            output_path = save_locally(job_id, cycle_package, "cycle_package.json")

            return [TextContent(type="text", text=f"[LOCAL MODE] Saved cycle package: {cycle_name}\n"
                               f"  Output file: {output_path}\n"
                               f"  Campaigns: {len(campaigns)}\n"
                               f"  Total email variants: {total_variants}\n"
                               f"  ICP mapping: {'Yes' if icp_mapping else 'No'}\n"
                               f"  Cycle variables: {len(cycle_variables)}\n"
                               f"  Overall QA: {overall_qa_score or 'N/A'} - {overall_verdict or 'N/A'}\n\n"
                               f"Run validation: python scripts/validate_output.py {output_path}")]

        # PRODUCTION MODE: Save to database
        conn = get_db()
        cur = conn.cursor(cursor_factory=RealDictCursor)

        try:
            # Get job info
            cur.execute("""
                SELECT client_id, strategy_id
                FROM strategy_generation_jobs
                WHERE id = %s
            """, (job_id,))
            job = cur.fetchone()

            if not job:
                return [TextContent(type="text", text=f"Error: Job {job_id} not found")]

            client_id = str(job["client_id"])
            strategy_id = job.get("strategy_id")

            # Create or get campaign cycle
            cycle_id = str(uuid.uuid4())
            cur.execute("""
                INSERT INTO campaign_cycles
                (id, client_id, status, created_at)
                VALUES (%s, %s, 'active', NOW())
                RETURNING id
            """, (cycle_id, client_id))
            cycle_id = str(cur.fetchone()["id"])

            # Create cycle strategy config (if table exists)
            try:
                cur.execute("""
                    INSERT INTO cycle_strategy_config
                    (id, cycle_id, icp_mapping, cycle_variables, strategic_focus, target_outcome)
                    VALUES (%s, %s, %s, %s, %s, %s)
                """, (str(uuid.uuid4()), cycle_id,
                      Json(icp_mapping) if icp_mapping else None,
                      Json(cycle_variables) if cycle_variables else None,
                      strategic_focus,
                      target_outcome))
            except Exception as e:
                # Table might not exist yet - log but continue
                print(f"[MCP] Warning: Could not save cycle_strategy_config: {e}", file=sys.stderr)

            document_ids = []

            # Create each campaign document linked to the cycle
            for campaign in campaigns:
                document_id = str(uuid.uuid4())
                campaign_name = campaign["campaign_name"]
                angle = campaign["angle"]
                campaign_variables = campaign.get("campaign_variables", [])
                email_positions = campaign.get("email_positions", [])
                qa_scoring = campaign.get("qa_scoring")
                strategy_notes = campaign.get("strategy_notes")

                # Build variable schema with campaign-level variables
                variable_schema = {
                    "core": [],
                    "high_signal": [],
                    "ai_generated": [],
                    "campaign_level": campaign_variables
                }

                # Add angle to strategy_notes for reference
                notes_with_angle = strategy_notes or {}
                notes_with_angle["campaign_angle"] = angle

                cur.execute("""
                    INSERT INTO campaign_documents
                    (id, job_id, client_id, strategy_id, cycle_id, document_name, document_version,
                     vertical, objective, icp_mapping, variable_schema, campaign_variables,
                     qa_scoring, strategy_notes, status, campaign_number)
                    VALUES (%s, %s, %s, %s, %s, %s, 1, %s, %s, %s, %s, %s, %s, %s, 'draft', %s)
                """, (document_id, job_id, client_id, strategy_id, cycle_id, campaign_name,
                      vertical, objective,
                      Json(icp_mapping) if icp_mapping else None,
                      Json(variable_schema),
                      Json(campaign_variables) if campaign_variables else None,
                      Json(qa_scoring) if qa_scoring else None,
                      Json(notes_with_angle),
                      campaign.get("campaign_number", 1)))

                # Insert email variants for each position
                for position_data in email_positions:
                    position = position_data.get("position", 1)
                    variants = position_data.get("variants", [])

                    for variant in variants:
                        variant_id = str(uuid.uuid4())
                        cur.execute("""
                            INSERT INTO document_email_variants
                            (id, document_id, email_position, variant_number, variant_name,
                             is_recommended, subject_line, email_body, wait_days, thread_reply,
                             word_count, them_us_ratio, score, angle, strategy, value_prop)
                            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        """, (variant_id, document_id, position,
                              variant.get("variant_number", 1),
                              variant.get("variant_name"),
                              variant.get("is_recommended", False),
                              variant.get("subject_line"),
                              variant.get("email_body", ""),
                              variant.get("wait_days", 0),
                              variant.get("thread_reply", False),
                              variant.get("word_count"),
                              variant.get("them_us_ratio"),
                              variant.get("score"),
                              variant.get("angle"),
                              variant.get("strategy"),
                              variant.get("value_prop")))

                document_ids.append({
                    "document_id": document_id,
                    "campaign_name": campaign_name,
                    "angle": angle
                })

            conn.commit()

            # Build response
            campaign_summary = "\n".join([
                f"  {i+1}. {c['campaign_name']} ({c['angle']}): {c['document_id'][:8]}..."
                for i, c in enumerate(document_ids)
            ])

            return [TextContent(type="text", text=f"Saved cycle package: {cycle_name}\n"
                               f"  Cycle ID: {cycle_id}\n"
                               f"  Campaigns:\n{campaign_summary}\n"
                               f"  Total variants: {total_variants}\n"
                               f"  Overall QA: {overall_qa_score or 'N/A'} - {overall_verdict or 'N/A'}")]

        except Exception as e:
            conn.rollback()
            return [TextContent(type="text", text=f"Error saving cycle package: {str(e)}")]

        finally:
            cur.close()
            conn.close()

    elif name == "save_cycle_scaffold":
        job_id = arguments["job_id"]
        client_id = arguments["client_id"]
        cycle_config = arguments["cycle_config"]
        campaigns = arguments["campaigns"]

        # DEBUG: Log what we received
        print(f"[MCP] save_cycle_scaffold called", file=sys.stderr)
        print(f"[MCP]   job_id: {job_id}", file=sys.stderr)
        print(f"[MCP]   client_id: {client_id}", file=sys.stderr)
        print(f"[MCP]   campaigns count: {len(campaigns)}", file=sys.stderr)
        for i, c in enumerate(campaigns):
            print(f"[MCP]   campaign {i+1}: {c.get('campaign_name', 'NO NAME')}, angle={c.get('angle', 'NO ANGLE')}", file=sys.stderr)

        # Extract config
        icp_mapping = cycle_config.get("icp_mapping")
        cycle_variables = cycle_config.get("cycle_variables", [])
        strategic_focus = cycle_config.get("strategic_focus")
        target_outcome = cycle_config.get("target_outcome")
        vertical = cycle_config.get("vertical")
        objective = cycle_config.get("objective")

        # LOCAL MODE: Save scaffold to filesystem
        if LOCAL_MODE:
            scaffold = {
                "cycle_id": str(uuid.uuid4()),
                "job_id": job_id,
                "client_id": client_id,
                "cycle_config": {
                    "icp_mapping": icp_mapping,
                    "cycle_variables": cycle_variables,
                    "strategic_focus": strategic_focus,
                    "target_outcome": target_outcome,
                    "vertical": vertical,
                    "objective": objective
                },
                "campaigns": [],
                "created_at": datetime.now().isoformat()
            }

            # Add campaign stubs
            for campaign in campaigns:
                scaffold["campaigns"].append({
                    "campaign_document_id": str(uuid.uuid4()),
                    "campaign_number": campaign["campaign_number"],
                    "campaign_name": campaign["campaign_name"],
                    "angle": campaign["angle"],
                    "campaign_variables": campaign.get("campaign_variables", []),
                    "email_positions": []  # Empty - will be filled by save_campaign_copy
                })

            output_path = save_locally(job_id, scaffold, "cycle_scaffold.json")

            return [TextContent(type="text", text=f"[LOCAL MODE] Saved cycle scaffold:\n"
                               f"  Output file: {output_path}\n"
                               f"  Cycle ID: {scaffold['cycle_id']}\n"
                               f"  ICP mapping: {'Yes' if icp_mapping else 'No'}\n"
                               f"  Cycle variables: {len(cycle_variables)}\n"
                               f"  Campaign stubs: {len(campaigns)}\n\n"
                               f"Next: Run 4 campaign_copy phases to generate emails")]

        # PRODUCTION MODE: Save to database
        conn = get_db()
        cur = conn.cursor(cursor_factory=RealDictCursor)

        try:
            # Create campaign cycle
            cycle_id = str(uuid.uuid4())
            cur.execute("""
                INSERT INTO campaign_cycles
                (id, client_id, status, created_at)
                VALUES (%s, %s, 'active', NOW())
                RETURNING id
            """, (cycle_id, client_id))
            cycle_id = str(cur.fetchone()["id"])

            # Create cycle strategy config
            try:
                cur.execute("""
                    INSERT INTO cycle_strategy_config
                    (id, cycle_id, icp_mapping, cycle_variables, strategic_focus, target_outcome)
                    VALUES (%s, %s, %s, %s, %s, %s)
                """, (str(uuid.uuid4()), cycle_id,
                      Json(icp_mapping) if icp_mapping else None,
                      Json(cycle_variables) if cycle_variables else None,
                      strategic_focus,
                      target_outcome))
            except Exception as e:
                print(f"[MCP] Warning: Could not save cycle_strategy_config: {e}", file=sys.stderr)

            # Update job with cycle_id
            cur.execute("""
                UPDATE strategy_generation_jobs
                SET cycle_id = %s
                WHERE id = %s
            """, (cycle_id, job_id))

            campaign_stubs = []

            # Create 4 campaign document stubs (no email content yet)
            for campaign in campaigns:
                document_id = str(uuid.uuid4())
                campaign_number = campaign["campaign_number"]
                campaign_name = campaign["campaign_name"]
                angle = campaign["angle"]
                campaign_variables = campaign.get("campaign_variables", [])

                cur.execute("""
                    INSERT INTO campaign_documents
                    (id, job_id, client_id, cycle_id, document_name, document_version,
                     vertical, objective, icp_mapping, campaign_variables, angle,
                     campaign_number, status)
                    VALUES (%s, %s, %s, %s, %s, 1, %s, %s, %s, %s, %s, %s, 'draft')
                """, (document_id, job_id, client_id, cycle_id, campaign_name,
                      vertical, objective,
                      Json(icp_mapping) if icp_mapping else None,
                      Json(campaign_variables) if campaign_variables else None,
                      angle,
                      campaign_number))

                campaign_stubs.append({
                    "campaign_number": campaign_number,
                    "campaign_document_id": document_id
                })

            conn.commit()
            print(f"[MCP]   Created {len(campaign_stubs)} campaign stubs, cycle_id={cycle_id}", file=sys.stderr)

            # Build response with IDs for creating phases
            campaign_summary = "\n".join([
                f"  {c['campaign_number']}. {c['campaign_document_id'][:8]}..."
                for c in campaign_stubs
            ])

            return [TextContent(type="text", text=f"Saved cycle scaffold:\n"
                               f"  Cycle ID: {cycle_id}\n"
                               f"  ICP mapping: {'Yes' if icp_mapping else 'No'}\n"
                               f"  Cycle variables: {len(cycle_variables)}\n"
                               f"  Campaign stubs:\n{campaign_summary}\n\n"
                               f"Campaign IDs for phases: {json.dumps(campaign_stubs)}")]

        except Exception as e:
            conn.rollback()
            return [TextContent(type="text", text=f"Error saving cycle scaffold: {str(e)}")]

        finally:
            cur.close()
            conn.close()

    elif name == "get_campaign_context":
        job_id = arguments["job_id"]
        campaign_number = arguments["campaign_number"]

        # LOCAL MODE: Read from scaffold file
        if LOCAL_MODE:
            scaffold_path = LOCAL_OUTPUT_DIR / "jobs" / job_id / "cycle_scaffold.json"
            if not scaffold_path.exists():
                return [TextContent(type="text", text=f"Error: Scaffold not found at {scaffold_path}. "
                                   f"Run save_cycle_scaffold first.")]

            with open(scaffold_path, "r", encoding="utf-8") as f:
                scaffold = json.load(f)

            # Find the campaign stub
            campaign_stub = None
            for c in scaffold.get("campaigns", []):
                if c.get("campaign_number") == campaign_number:
                    campaign_stub = c
                    break

            if not campaign_stub:
                return [TextContent(type="text", text=f"Error: Campaign {campaign_number} not found in scaffold")]

            # Build context (in local mode, we don't have client context from DB)
            context = {
                "mode": "local",
                "job_id": job_id,
                "client_id": scaffold.get("client_id"),
                "cycle_config": scaffold.get("cycle_config", {}),
                "campaign": {
                    "campaign_document_id": campaign_stub.get("campaign_document_id"),
                    "campaign_number": campaign_number,
                    "campaign_name": campaign_stub.get("campaign_name"),
                    "angle": campaign_stub.get("angle"),
                    "campaign_variables": campaign_stub.get("campaign_variables", [])
                },
                "note": "Local mode - use get_client_context for full client data"
            }

            return [TextContent(type="text", text=json.dumps(context, indent=2))]

        # PRODUCTION MODE: Fetch from database
        conn = get_db()
        cur = conn.cursor(cursor_factory=RealDictCursor)

        try:
            # Get job info
            cur.execute("""
                SELECT client_id, cycle_id
                FROM strategy_generation_jobs
                WHERE id = %s
            """, (job_id,))
            job = cur.fetchone()

            if not job:
                return [TextContent(type="text", text=f"Error: Job {job_id} not found")]

            if not job.get("cycle_id"):
                return [TextContent(type="text", text=f"Error: Job {job_id} has no cycle_id. "
                                   f"Run save_cycle_scaffold first.")]

            client_id = str(job["client_id"])
            cycle_id = str(job["cycle_id"])

            # Get cycle config
            cur.execute("""
                SELECT icp_mapping, cycle_variables, strategic_focus, target_outcome
                FROM cycle_strategy_config
                WHERE cycle_id = %s
            """, (cycle_id,))
            cycle_config = cur.fetchone() or {}

            # Get campaign document stub
            cur.execute("""
                SELECT id, document_name, angle, campaign_variables, icp_mapping,
                       vertical, objective
                FROM campaign_documents
                WHERE cycle_id = %s AND campaign_number = %s
            """, (cycle_id, campaign_number))
            campaign = cur.fetchone()

            if not campaign:
                return [TextContent(type="text", text=f"Error: Campaign {campaign_number} not found for cycle {cycle_id}")]

            # Get basic client info
            cur.execute("""
                SELECT c.id, c.name, c.industry, c.website
                FROM clients c
                WHERE c.id = %s
            """, (client_id,))
            client = cur.fetchone()

            # Build context
            context = {
                "job_id": job_id,
                "client": {
                    "id": str(client["id"]) if client else client_id,
                    "name": client["name"] if client else None,
                    "industry": client.get("industry") if client else None,
                    "website": client.get("website") if client else None
                },
                "cycle_config": {
                    "cycle_id": cycle_id,
                    "icp_mapping": cycle_config.get("icp_mapping"),
                    "cycle_variables": cycle_config.get("cycle_variables", []),
                    "strategic_focus": cycle_config.get("strategic_focus"),
                    "target_outcome": cycle_config.get("target_outcome")
                },
                "campaign": {
                    "campaign_document_id": str(campaign["id"]),
                    "campaign_number": campaign_number,
                    "campaign_name": campaign["document_name"],
                    "angle": campaign["angle"],
                    "campaign_variables": campaign.get("campaign_variables", []),
                    "icp_mapping": campaign.get("icp_mapping"),
                    "vertical": campaign.get("vertical"),
                    "objective": campaign.get("objective")
                }
            }

            return [TextContent(type="text", text=json.dumps(context, indent=2, default=str))]

        finally:
            cur.close()
            conn.close()

    elif name == "save_campaign_copy":
        job_id = arguments["job_id"]
        campaign_number = arguments["campaign_number"]
        email_positions = arguments["email_positions"]
        qa_scoring = arguments.get("qa_scoring")
        strategy_notes = arguments.get("strategy_notes")
        variable_schema = arguments.get("variable_schema")

        # Count variants
        variant_count = sum(len(pos.get("variants", [])) for pos in email_positions)

        # LOCAL MODE: Update scaffold with email content
        if LOCAL_MODE:
            scaffold_path = LOCAL_OUTPUT_DIR / "jobs" / job_id / "cycle_scaffold.json"
            if not scaffold_path.exists():
                return [TextContent(type="text", text=f"Error: Scaffold not found at {scaffold_path}")]

            with open(scaffold_path, "r", encoding="utf-8") as f:
                scaffold = json.load(f)

            # Find and update the campaign
            campaign_found = False
            for i, c in enumerate(scaffold.get("campaigns", [])):
                if c.get("campaign_number") == campaign_number:
                    scaffold["campaigns"][i]["email_positions"] = email_positions
                    scaffold["campaigns"][i]["qa_scoring"] = qa_scoring
                    scaffold["campaigns"][i]["strategy_notes"] = strategy_notes
                    scaffold["campaigns"][i]["variable_schema"] = variable_schema
                    scaffold["campaigns"][i]["completed_at"] = datetime.now().isoformat()
                    campaign_found = True
                    break

            if not campaign_found:
                return [TextContent(type="text", text=f"Error: Campaign {campaign_number} not found in scaffold")]

            # Save updated scaffold
            scaffold["last_updated"] = datetime.now().isoformat()
            with open(scaffold_path, "w", encoding="utf-8") as f:
                json.dump(scaffold, f, indent=2, ensure_ascii=False)

            # Also save as separate campaign file for easy access
            campaign_path = LOCAL_OUTPUT_DIR / "jobs" / job_id / f"campaign_{campaign_number}.json"
            campaign_doc = scaffold["campaigns"][campaign_number - 1]
            with open(campaign_path, "w", encoding="utf-8") as f:
                json.dump(campaign_doc, f, indent=2, ensure_ascii=False)

            return [TextContent(type="text", text=f"[LOCAL MODE] Saved campaign {campaign_number} copy:\n"
                               f"  Scaffold updated: {scaffold_path}\n"
                               f"  Campaign file: {campaign_path}\n"
                               f"  Positions: {len(email_positions)}\n"
                               f"  Total variants: {variant_count}\n"
                               f"  QA Score: {qa_scoring.get('overall_score') if qa_scoring else 'N/A'}")]

        # PRODUCTION MODE: Update campaign document in database
        conn = get_db()
        cur = conn.cursor(cursor_factory=RealDictCursor)

        try:
            # Get job and cycle info
            cur.execute("""
                SELECT cycle_id
                FROM strategy_generation_jobs
                WHERE id = %s
            """, (job_id,))
            job = cur.fetchone()

            if not job or not job.get("cycle_id"):
                return [TextContent(type="text", text=f"Error: Job {job_id} not found or has no cycle_id")]

            cycle_id = str(job["cycle_id"])

            # Get the campaign document
            cur.execute("""
                SELECT id, client_id
                FROM campaign_documents
                WHERE cycle_id = %s AND campaign_number = %s
            """, (cycle_id, campaign_number))
            campaign = cur.fetchone()

            if not campaign:
                return [TextContent(type="text", text=f"Error: Campaign {campaign_number} not found for cycle {cycle_id}")]

            document_id = str(campaign["id"])

            # Update campaign document with email content
            cur.execute("""
                UPDATE campaign_documents
                SET email_positions = %s,
                    qa_scoring = %s,
                    strategy_notes = %s,
                    variable_schema = %s,
                    status = 'draft',
                    updated_at = NOW()
                WHERE id = %s
            """, (Json(email_positions),
                  Json(qa_scoring) if qa_scoring else None,
                  Json(strategy_notes) if strategy_notes else None,
                  Json(variable_schema) if variable_schema else None,
                  document_id))

            # Also insert individual variants into document_email_variants
            for position_data in email_positions:
                position = position_data.get("position", 1)
                variants = position_data.get("variants", [])

                for variant in variants:
                    variant_id = str(uuid.uuid4())
                    cur.execute("""
                        INSERT INTO document_email_variants
                        (id, document_id, email_position, variant_number, variant_name,
                         is_recommended, subject_line, email_body, wait_days, thread_reply,
                         word_count, them_us_ratio, score, angle, strategy, value_prop)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (document_id, email_position, variant_number)
                        DO UPDATE SET
                            variant_name = EXCLUDED.variant_name,
                            is_recommended = EXCLUDED.is_recommended,
                            subject_line = EXCLUDED.subject_line,
                            email_body = EXCLUDED.email_body,
                            wait_days = EXCLUDED.wait_days,
                            thread_reply = EXCLUDED.thread_reply,
                            word_count = EXCLUDED.word_count,
                            them_us_ratio = EXCLUDED.them_us_ratio,
                            score = EXCLUDED.score,
                            angle = EXCLUDED.angle,
                            strategy = EXCLUDED.strategy,
                            value_prop = EXCLUDED.value_prop
                    """, (variant_id, document_id, position,
                          variant.get("variant_number", 1),
                          variant.get("variant_name"),
                          variant.get("is_recommended", False),
                          variant.get("subject_line"),
                          variant.get("email_body", ""),
                          variant.get("wait_days", 0),
                          variant.get("thread_reply", False),
                          variant.get("word_count"),
                          variant.get("them_us_ratio"),
                          variant.get("score"),
                          variant.get("angle"),
                          variant.get("strategy"),
                          variant.get("value_prop")))

            conn.commit()

            qa_score = qa_scoring.get("overall_score") if qa_scoring else None

            return [TextContent(type="text", text=f"Saved campaign {campaign_number} copy:\n"
                               f"  Document ID: {document_id}\n"
                               f"  Positions: {len(email_positions)}\n"
                               f"  Total variants: {variant_count}\n"
                               f"  QA Score: {qa_score or 'N/A'}")]

        except Exception as e:
            conn.rollback()
            return [TextContent(type="text", text=f"Error saving campaign copy: {str(e)}")]

        finally:
            cur.close()
            conn.close()

    elif name == "save_campaign_document":
        job_id = arguments["job_id"]
        document_name = arguments["document_name"]
        vertical = arguments.get("vertical")
        objective = arguments.get("objective")
        icp_mapping = arguments.get("icp_mapping")
        variable_schema = arguments.get("variable_schema")
        email_positions = arguments["email_positions"]
        sequence_summary = arguments.get("sequence_summary")
        qa_scoring = arguments.get("qa_scoring")
        strategy_notes = arguments.get("strategy_notes")
        used_variables = arguments.get("used_variables", [])
        missing_variables = arguments.get("missing_variables", [])

        # Count variants
        variant_count = sum(len(pos.get("variants", [])) for pos in email_positions)

        # LOCAL MODE: Save to filesystem instead of database
        if LOCAL_MODE:
            document = {
                "document_id": str(uuid.uuid4()),
                "job_id": job_id,
                "document_name": document_name,
                "vertical": vertical,
                "objective": objective,
                "icp_mapping": icp_mapping,
                "variable_schema": variable_schema,
                "email_positions": email_positions,
                "sequence_summary": sequence_summary,
                "qa_scoring": qa_scoring,
                "strategy_notes": strategy_notes,
                "used_variables": used_variables,
                "missing_variables": missing_variables,
                "created_at": datetime.now().isoformat()
            }

            output_path = save_locally(job_id, document)

            return [TextContent(type="text", text=f"[LOCAL MODE] Saved campaign document: {document_name}\n"
                               f"  Output file: {output_path}\n"
                               f"  Positions: {len(email_positions)}\n"
                               f"  Total variants: {variant_count}\n"
                               f"  ICP mapping: {'Yes' if icp_mapping else 'No'}\n"
                               f"  QA scoring: {'Yes' if qa_scoring else 'No'}\n\n"
                               f"Run validation: python scripts/validate_output.py {output_path}")]

        # PRODUCTION MODE: Save to database
        conn = get_db()
        cur = conn.cursor(cursor_factory=RealDictCursor)

        try:
            # Get job info
            cur.execute("""
                SELECT client_id, strategy_id
                FROM strategy_generation_jobs
                WHERE id = %s
            """, (job_id,))
            job = cur.fetchone()

            if not job:
                return [TextContent(type="text", text=f"Error: Job {job_id} not found")]

            client_id = str(job["client_id"])
            strategy_id = job.get("strategy_id")

            # Create the campaign document
            document_id = str(uuid.uuid4())
            cur.execute("""
                INSERT INTO campaign_documents
                (id, job_id, client_id, strategy_id, document_name, document_version,
                 vertical, objective, icp_mapping, variable_schema,
                 sequence_summary, qa_scoring, strategy_notes, status)
                VALUES (%s, %s, %s, %s, %s, 1, %s, %s, %s, %s, %s, %s, %s, 'draft')
            """, (document_id, job_id, client_id, strategy_id, document_name,
                  vertical, objective,
                  Json(icp_mapping) if icp_mapping else None,
                  Json(variable_schema) if variable_schema else None,
                  Json(sequence_summary) if sequence_summary else None,
                  Json(qa_scoring) if qa_scoring else None,
                  Json(strategy_notes) if strategy_notes else None))

            # Insert email variants for each position
            for position_data in email_positions:
                position = position_data["position"]
                variants = position_data.get("variants", [])
                subject_options = position_data.get("subject_options", [])

                for variant in variants:
                    variant_id = str(uuid.uuid4())
                    cur.execute("""
                        INSERT INTO document_email_variants
                        (id, document_id, email_position, variant_number, variant_name,
                         is_recommended, subject_line, email_body, wait_days, thread_reply,
                         word_count, them_us_ratio, score, angle, strategy, value_prop)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """, (variant_id, document_id, position,
                          variant.get("variant_number", 1),
                          variant.get("variant_name"),
                          variant.get("is_recommended", False),
                          variant.get("subject_line"),
                          variant["email_body"],
                          variant.get("wait_days", 0),
                          variant.get("thread_reply", False),
                          variant.get("word_count"),
                          variant.get("them_us_ratio"),
                          variant.get("score"),
                          variant.get("angle"),
                          variant.get("strategy"),
                          variant.get("value_prop")))

                # Insert subject line options
                for idx, subj_opt in enumerate(subject_options):
                    cur.execute("""
                        INSERT INTO document_subject_options
                        (id, document_id, email_position, subject_line, rationale, sort_order)
                        VALUES (%s, %s, %s, %s, %s, %s)
                    """, (str(uuid.uuid4()), document_id, position,
                          subj_opt["subject_line"],
                          subj_opt.get("rationale"),
                          idx))

            conn.commit()

            result = {
                "document_id": document_id,
                "document_name": document_name,
                "positions": len(email_positions),
                "variants": variant_count,
                "has_icp_mapping": icp_mapping is not None,
                "has_qa_scoring": qa_scoring is not None
            }

            return [TextContent(type="text", text=f"Saved campaign document: {document_name}\n"
                               f"  Document ID: {document_id}\n"
                               f"  Positions: {len(email_positions)}\n"
                               f"  Total variants: {variant_count}\n"
                               f"  ICP mapping: {'Yes' if icp_mapping else 'No'}\n"
                               f"  QA scoring: {'Yes' if qa_scoring else 'No'}")]

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
