"""
Layer 1: Database tool tests.

Tests the same DB operations that purchase_mcp/server.py uses.
Connects to the remote PostgreSQL, creates test data, exercises
each tool function, then cleans up.

Usage:
    cd d:\Work\charm-email-os
    python tests/test_mcp_db_tools.py
"""

import json
import os
import sys
import uuid

import psycopg2
from psycopg2.extras import RealDictCursor

# Database connection (same as production)
DB_CONFIG = {
    "host": os.environ.get("POSTGRES_HOST", "31.97.142.123"),
    "port": int(os.environ.get("POSTGRES_PORT", "5432")),
    "dbname": os.environ.get("POSTGRES_DB", "postgres"),
    "user": os.environ.get("POSTGRES_USER", "postgres"),
    "password": os.environ.get("POSTGRES_PASSWORD", "ZEN3hMv6UpA0hfd8OcAUSiJWgpY33q5V"),
}

TEST_JOB_ID = str(uuid.uuid4())
TEST_CLIENT_ID = "4bd07dc0-059a-448b-b6f4-3275d0c104a9"  # Charm


def get_conn():
    return psycopg2.connect(**DB_CONFIG)


def test_insert_job():
    """Insert a test job with worker_mode='test' (invisible to production worker)."""
    print("\n[Test 1] Insert test job")
    conn = get_conn()
    cur = conn.cursor()
    try:
        cur.execute("""
            INSERT INTO inbox_purchase_jobs (
                id, client_id, status, worker_mode, provider_type,
                domain_names, domain_ids, company_name,
                hypertide_email, hypertide_password,
                bison_username, bison_password, bison_workspace_name,
                forwarding_domain, use_saved_payment, created_at
            ) VALUES (
                %s, %s, 'pending', 'test', 'entra',
                ARRAY['test.invalid'], ARRAY[%s]::uuid[], 'TEST-COMPANY',
                'test@example.com', 'testpassword',
                'test-bison@example.com', 'testbisonpass', 'TestWorkspace',
                'example.com', false, NOW()
            )
        """, (TEST_JOB_ID, TEST_CLIENT_ID, str(uuid.uuid4())))
        conn.commit()
        print(f"  Inserted job: {TEST_JOB_ID}")
        print(f"  worker_mode='test' (production worker won't pick this up)")
        return True
    except Exception as e:
        conn.rollback()
        print(f"  FAIL: {e}")
        return False
    finally:
        cur.close()
        conn.close()


def test_get_purchase_job():
    """Read the test job back (mirrors get_purchase_job MCP tool)."""
    print("\n[Test 2] get_purchase_job")
    conn = get_conn()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    try:
        cur.execute("""
            SELECT id, client_id, status, worker_mode, provider_type,
                   domain_names, company_name, hypertide_email,
                   bison_username, bison_workspace_name, forwarding_domain,
                   use_saved_payment
            FROM inbox_purchase_jobs WHERE id = %s
        """, (TEST_JOB_ID,))
        row = cur.fetchone()
        if row:
            print(f"  id: {row['id']}")
            print(f"  status: {row['status']}")
            print(f"  worker_mode: {row['worker_mode']}")
            print(f"  provider_type: {row['provider_type']}")
            print(f"  domain_names: {row['domain_names']}")
            print(f"  company_name: {row['company_name']}")
            print(f"  -> PASS")
            return True
        else:
            print(f"  -> FAIL: job not found")
            return False
    finally:
        cur.close()
        conn.close()


def test_update_job_status():
    """Update job status (mirrors update_job_status MCP tool)."""
    print("\n[Test 3] update_job_status")
    conn = get_conn()
    cur = conn.cursor()
    try:
        cur.execute("""
            UPDATE inbox_purchase_jobs
            SET status = %s, current_step = %s
            WHERE id = %s
        """, ("processing", "test_step", TEST_JOB_ID))
        conn.commit()

        # Verify
        cur2 = conn.cursor(cursor_factory=RealDictCursor)
        cur2.execute("SELECT status, current_step FROM inbox_purchase_jobs WHERE id = %s", (TEST_JOB_ID,))
        row = cur2.fetchone()
        ok = row and row["status"] == "processing" and row["current_step"] == "test_step"
        print(f"  status={row['status']}, current_step={row['current_step']}")
        print(f"  -> {'PASS' if ok else 'FAIL'}")
        cur2.close()
        return ok
    except Exception as e:
        conn.rollback()
        print(f"  -> FAIL: {e}")
        return False
    finally:
        cur.close()
        conn.close()


def test_log_step():
    """Insert audit step (mirrors log_step MCP tool)."""
    print("\n[Test 4] log_step")
    conn = get_conn()
    cur = conn.cursor()
    try:
        step_id = str(uuid.uuid4())
        cur.execute("""
            INSERT INTO purchase_job_steps (id, job_id, step_name, notes, created_at)
            VALUES (%s, %s, %s, %s, NOW())
        """, (step_id, TEST_JOB_ID, "test_step", "Automated test step"))
        conn.commit()

        # Verify
        cur2 = conn.cursor(cursor_factory=RealDictCursor)
        cur2.execute("SELECT * FROM purchase_job_steps WHERE job_id = %s", (TEST_JOB_ID,))
        rows = cur2.fetchall()
        print(f"  Inserted step. Total steps for job: {len(rows)}")
        print(f"  -> {'PASS' if len(rows) > 0 else 'FAIL'}")
        cur2.close()
        return len(rows) > 0
    except Exception as e:
        conn.rollback()
        print(f"  -> FAIL: {e}")
        return False
    finally:
        cur.close()
        conn.close()


def test_fail_job():
    """Mark job as failed (mirrors fail_job MCP tool)."""
    print("\n[Test 5] fail_job")
    conn = get_conn()
    cur = conn.cursor()
    try:
        cur.execute("""
            UPDATE inbox_purchase_jobs
            SET status = 'failed',
                current_step = %s,
                errors = array_append(COALESCE(errors, ARRAY[]::text[]), %s)
            WHERE id = %s
        """, ("test_failure", "Test error message", TEST_JOB_ID))
        conn.commit()

        # Verify
        cur2 = conn.cursor(cursor_factory=RealDictCursor)
        cur2.execute("SELECT status, current_step, errors FROM inbox_purchase_jobs WHERE id = %s", (TEST_JOB_ID,))
        row = cur2.fetchone()
        ok = row and row["status"] == "failed" and "Test error message" in (row["errors"] or [])
        print(f"  status={row['status']}, errors={row['errors']}")
        print(f"  -> {'PASS' if ok else 'FAIL'}")
        cur2.close()
        return ok
    except Exception as e:
        conn.rollback()
        print(f"  -> FAIL: {e}")
        return False
    finally:
        cur.close()
        conn.close()


def cleanup():
    """Remove all test data."""
    print("\n[Cleanup] Removing test data")
    conn = get_conn()
    cur = conn.cursor()
    try:
        cur.execute("DELETE FROM purchase_job_steps WHERE job_id = %s", (TEST_JOB_ID,))
        steps_deleted = cur.rowcount
        cur.execute("DELETE FROM inbox_purchase_jobs WHERE id = %s", (TEST_JOB_ID,))
        jobs_deleted = cur.rowcount
        conn.commit()
        print(f"  Deleted {jobs_deleted} job(s), {steps_deleted} step(s)")
        print(f"  -> CLEAN")
    except Exception as e:
        conn.rollback()
        print(f"  -> CLEANUP FAILED: {e}")
    finally:
        cur.close()
        conn.close()


def main():
    print("=" * 60)
    print("Layer 1: Database Tool Tests")
    print(f"DB: {DB_CONFIG['host']}:{DB_CONFIG['port']}/{DB_CONFIG['dbname']}")
    print(f"Test job ID: {TEST_JOB_ID}")
    print("=" * 60)

    results = {}
    try:
        results["insert_job"] = test_insert_job()
        results["get_purchase_job"] = test_get_purchase_job()
        results["update_job_status"] = test_update_job_status()
        results["log_step"] = test_log_step()
        results["fail_job"] = test_fail_job()
    finally:
        cleanup()

    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    all_pass = all(results.values())
    for name, ok in results.items():
        print(f"  {name:25s} {'PASS' if ok else 'FAIL'}")
    print(f"\nOverall: {'ALL PASS' if all_pass else 'SOME FAILURES'}")
    print("=" * 60)

    return all_pass


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
