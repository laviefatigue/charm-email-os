"""
Insert a controlled test purchase job into the database.

This creates a job that the purchase worker can pick up (worker_mode='worker').
Only job-specific data is stored in the DB row — global credentials (Hypertide
login, Bison login, API key, Stripe) come from ENV vars on the worker container,
injected by the MCP server's get_purchase_job() handler.

Usage:
    cd d:\Work\charm-email-os
    python tests/insert_test_purchase_job.py

    # View job status:
    python tests/insert_test_purchase_job.py --status <JOB_ID>

    # Reset a job for re-testing:
    python tests/insert_test_purchase_job.py --reset <JOB_ID>

    # Delete a test job:
    python tests/insert_test_purchase_job.py --delete <JOB_ID>
"""

import argparse
import json
import os
import sys
import uuid

import psycopg2
from psycopg2.extras import RealDictCursor

DB_CONFIG = {
    "host": os.environ.get("POSTGRES_HOST", "31.97.142.123"),
    "port": int(os.environ.get("POSTGRES_PORT", "5432")),
    "dbname": os.environ.get("POSTGRES_DB", "postgres"),
    "user": os.environ.get("POSTGRES_USER", "postgres"),
    "password": os.environ.get("POSTGRES_PASSWORD", "ZEN3hMv6UpA0hfd8OcAUSiJWgpY33q5V"),
}

CLIENT_ID = "4bd07dc0-059a-448b-b6f4-3275d0c104a9"  # Charm


def get_conn():
    return psycopg2.connect(**DB_CONFIG)


def insert_test_job():
    """Insert a test purchase job (job-specific data only)."""
    job_id = str(uuid.uuid4())

    # Workspace name: query from client → workspaces join (matches production behavior)
    bison_workspace = "Charm"
    try:
        conn_tmp = get_conn()
        cur_tmp = conn_tmp.cursor()
        cur_tmp.execute("""
            SELECT w.workspace_name
            FROM clients c
            JOIN workspaces w ON c.workspace_id = w.id
            WHERE c.id = %s
        """, (CLIENT_ID,))
        row = cur_tmp.fetchone()
        bison_workspace = row[0] if row and row[0] else "Charm"
        cur_tmp.close()
        conn_tmp.close()
        print(f"  Workspace from DB: {bison_workspace}")
    except Exception as e:
        print(f"  WARNING: Could not query workspace from DB ({e}), using 'Charm'")

    conn = get_conn()
    cur = conn.cursor()
    try:
        # Hypertide Entra requires 2 domains per order set
        domain_id_1 = str(uuid.uuid4())
        domain_id_2 = str(uuid.uuid4())
        cur.execute("""
            INSERT INTO inbox_purchase_jobs (
                id, client_id, status, worker_mode, provider_type,
                domain_names, domain_ids, company_name,
                bison_workspace_name,
                forwarding_domain, use_saved_payment,
                sender_names, order_count,
                created_at
            ) VALUES (
                %s, %s, 'pending', 'worker', 'entra',
                ARRAY['test1.invalid', 'test2.invalid'], ARRAY[%s, %s]::uuid[], 'TEST-DRY-RUN',
                %s,
                'hirecharm.com', false,
                %s, 1,
                NOW()
            )
        """, (
            job_id, CLIENT_ID, domain_id_1, domain_id_2,
            bison_workspace,
            json.dumps([{"firstName": "Test", "lastName": "User"}]),
        ))
        conn.commit()

        print(f"\nTest job created (job-specific data only):")
        print(f"  Job ID:       {job_id}")
        print(f"  Status:       pending")
        print(f"  Worker mode:  worker")
        print(f"  Provider:     entra")
        print(f"  Domains:      ['test1.invalid', 'test2.invalid']")
        print(f"  Company:      TEST-DRY-RUN")
        print(f"  Workspace:    {bison_workspace}")
        print(f"  Saved payment: false")
        print()
        print("Global credentials (Hypertide, Bison, Stripe) come from ENV vars on the worker container.")
        print()
        print("The worker will pick this up. Use --stop-after-step to control how far it goes:")
        print(f"  python3 /app/purchase_worker.py --single-job {job_id} --stop-after-step 2")
        print()
        print("To check status:")
        print(f"  python tests/insert_test_purchase_job.py --status {job_id}")
        print()
        print("To reset for re-testing:")
        print(f"  python tests/insert_test_purchase_job.py --reset {job_id}")

        return job_id
    except Exception as e:
        conn.rollback()
        print(f"FAILED to insert job: {e}")
        sys.exit(1)
    finally:
        cur.close()
        conn.close()


def show_status(job_id: str):
    """Show job status and audit trail."""
    conn = get_conn()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    try:
        cur.execute("""
            SELECT id, status, worker_mode, current_step, errors,
                   provider_type, domain_names, company_name,
                   hypertide_order_id, created_at, started_at, completed_at
            FROM inbox_purchase_jobs WHERE id = %s
        """, (job_id,))
        job = cur.fetchone()
        if not job:
            print(f"Job {job_id} not found")
            return

        print(f"\nJob: {job['id']}")
        print(f"  Status:       {job['status']}")
        print(f"  Current step: {job['current_step']}")
        print(f"  Worker mode:  {job['worker_mode']}")
        print(f"  Provider:     {job['provider_type']}")
        print(f"  Domains:      {job['domain_names']}")
        print(f"  Company:      {job['company_name']}")
        print(f"  Order ID:     {job['hypertide_order_id']}")
        print(f"  Errors:       {job['errors']}")
        print(f"  Created:      {job['created_at']}")
        print(f"  Started:      {job['started_at']}")
        print(f"  Completed:    {job['completed_at']}")

        # Audit trail
        cur.execute("""
            SELECT step_name, notes, created_at,
                   CASE WHEN screenshot_base64 IS NOT NULL THEN 'yes' ELSE 'no' END as has_screenshot
            FROM purchase_job_steps
            WHERE job_id = %s
            ORDER BY created_at
        """, (job_id,))
        steps = cur.fetchall()
        if steps:
            print(f"\n  Audit trail ({len(steps)} steps):")
            for s in steps:
                print(f"    [{s['created_at']}] {s['step_name']} (screenshot: {s['has_screenshot']})")
                if s["notes"]:
                    print(f"      {s['notes'][:200]}")
        else:
            print("\n  No audit steps yet.")
    finally:
        cur.close()
        conn.close()


def reset_job(job_id: str):
    """Reset a job to pending for re-testing."""
    conn = get_conn()
    cur = conn.cursor()
    try:
        cur.execute("""
            UPDATE inbox_purchase_jobs
            SET status = 'pending', current_step = NULL, errors = NULL,
                started_at = NULL, completed_at = NULL, hypertide_order_id = NULL
            WHERE id = %s
        """, (job_id,))
        cur.execute("DELETE FROM purchase_job_steps WHERE job_id = %s", (job_id,))
        steps_deleted = cur.rowcount
        conn.commit()
        print(f"Job {job_id} reset to 'pending'. Deleted {steps_deleted} audit step(s).")
    except Exception as e:
        conn.rollback()
        print(f"FAILED to reset: {e}")
    finally:
        cur.close()
        conn.close()


def delete_job(job_id: str):
    """Delete a test job and its audit trail."""
    conn = get_conn()
    cur = conn.cursor()
    try:
        cur.execute("DELETE FROM purchase_job_steps WHERE job_id = %s", (job_id,))
        steps = cur.rowcount
        cur.execute("DELETE FROM inbox_purchase_jobs WHERE id = %s", (job_id,))
        jobs = cur.rowcount
        conn.commit()
        print(f"Deleted {jobs} job(s), {steps} step(s).")
    except Exception as e:
        conn.rollback()
        print(f"FAILED to delete: {e}")
    finally:
        cur.close()
        conn.close()


def main():
    parser = argparse.ArgumentParser(description="Test Purchase Job Manager")
    parser.add_argument("--status", type=str, help="Show status of a job by ID")
    parser.add_argument("--reset", type=str, help="Reset a job to pending")
    parser.add_argument("--delete", type=str, help="Delete a job and its steps")
    args = parser.parse_args()

    if args.status:
        show_status(args.status)
    elif args.reset:
        reset_job(args.reset)
    elif args.delete:
        delete_job(args.delete)
    else:
        insert_test_job()


if __name__ == "__main__":
    main()
