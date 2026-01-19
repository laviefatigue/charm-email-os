"""
Insert test onboarding submission for Charm client.
Run this once to create test data for strategy generation.
"""
import asyncio
import asyncpg
import os
from uuid import uuid4
from datetime import datetime

# Database config (use env vars in production)
DB_CONFIG = {
    "host": os.getenv("POSTGRES_HOST", "aws-0-us-east-1.pooler.supabase.com"),
    "port": int(os.getenv("POSTGRES_PORT", "6543")),
    "database": os.getenv("POSTGRES_DB", "postgres"),
    "user": os.getenv("POSTGRES_USER", "postgres.lhnzdotfevttijwyfcib"),
    "password": os.getenv("POSTGRES_PASSWORD", ""),
}

CLIENT_ID = "4bd07dc0-059a-448b-b6f4-3275d0c104a9"

async def insert_test_submission():
    if not DB_CONFIG["password"]:
        print("ERROR: Set POSTGRES_PASSWORD environment variable")
        return

    conn = await asyncpg.connect(**DB_CONFIG)

    try:
        submission_id = uuid4()

        # Insert main submission
        await conn.execute("""
            INSERT INTO client_onboarding_submissions (
                id, client_id, company_name, website, contact_name, contact_email,
                employee_count, funding_stage, hq_location,
                core_product, target_customer, acv, sales_cycle_length,
                signals, job_titles,
                outbound_tools, crm,
                customer_voice, roi_results, tone_style,
                primary_gtm_objective, success_metrics, success_definition,
                submission_status, submitted_at, created_at
            ) VALUES (
                $1, $2, $3, $4, $5, $6,
                $7, $8, $9,
                $10, $11, $12, $13,
                $14, $15,
                $16, $17,
                $18, $19, $20,
                $21, $22, $23,
                $24, $25, $26
            )
        """,
            submission_id,
            CLIENT_ID,
            "Charm",
            "https://usecharm.com",
            "Elliott LaVieFatigue",
            "elliott@laviefatigue.com",
            "11-50 employees",
            "Series A",
            "San Francisco, USA",
            "Client management platform for outbound email campaigns. Manage domains, inboxes, campaign strategies, leads, and health monitoring at scale.",
            "B2B SaaS companies with 50-500 employees who need to scale outbound email campaigns. Series A-C funded, heads of sales/marketing.",
            "$15,000/year",
            "1-3 months",
            ["New funding raised", "Leadership change", "Job postings (specific roles)", "Tech stack changes", "Company expansion", "Product launch", "Industry event attendance", "Content engagement"],
            ["VP of Sales", "Head of Growth", "SDR Manager"],
            ["Apollo", "Instantly", "Outreach", "Salesloft", "HubSpot", "Salesforce"],
            "Salesforce",
            "Finally a platform that understands outbound at scale. The health monitoring alone saved us from burning domains.",
            "3x reply rate improvement, 40% reduction in inbox burnout, 10+ hours saved per week on infrastructure management",
            "Direct & no-nonsense",
            "Pipeline Generation",
            ["Reply rate", "Meetings booked", "Pipeline generated", "Inbox health score", "Domain reputation"],
            "Consistently generate 5+ qualified meetings per week from cold outbound with healthy infrastructure that scales",
            "submitted",
            datetime.utcnow(),
            datetime.utcnow()
        )
        print(f"✅ Inserted submission: {submission_id}")

        # Insert segment
        segment_id = uuid4()
        await conn.execute("""
            INSERT INTO client_segments (
                id, submission_id, segment_name, revenue_percentage,
                unique_characteristics, pain_points, buying_triggers
            ) VALUES ($1, $2, $3, $4, $5, $6, $7)
        """,
            segment_id,
            submission_id,
            "Mid-Market SaaS",
            60,
            "Aggressive growth targets, hiring SDRs, expanding outbound efforts",
            "Low reply rates, poor deliverability, inbox management chaos, scaling email infrastructure",
            "New funding round, new sales hire quota, CEO pressure to scale pipeline"
        )
        print(f"✅ Inserted segment: {segment_id}")

        # Insert persona
        persona_id = uuid4()
        await conn.execute("""
            INSERT INTO client_personas (
                id, submission_id, job_title, primary_segment, seniority_level,
                pain_before_buying, aha_moment, objections
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
        """,
            persona_id,
            submission_id,
            "VP of Sales",
            "Mid-Market SaaS",
            "VP",
            "Low reply rates, poor deliverability, inbox management chaos",
            "When they see all their domains and inboxes managed in one place with health monitoring",
            "We already have a tool, It's too expensive, We can do this in-house"
        )
        print(f"✅ Inserted persona: {persona_id}")

        print(f"\n🎉 Test submission created successfully!")
        print(f"   Submission ID: {submission_id}")
        print(f"   Client ID: {CLIENT_ID}")

    finally:
        await conn.close()

if __name__ == "__main__":
    asyncio.run(insert_test_submission())
