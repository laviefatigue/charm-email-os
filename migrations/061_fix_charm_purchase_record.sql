-- Migration 061: Fix Charm purchase record
-- Only activatecharm.com was actually purchased (via Porkbun)
-- Other domains are legacy with unknown purchase history

DO $$
DECLARE
    charm_client_id UUID := '4bd07dc0-059a-448b-b6f4-3275d0c104a9';
    charm_workspace_id UUID;
    activate_domain_id UUID;
    new_job_id UUID;
BEGIN
    -- Get Charm's workspace
    SELECT workspace_id INTO charm_workspace_id
    FROM clients WHERE id = charm_client_id;

    -- Get activatecharm.com domain ID
    SELECT id INTO activate_domain_id
    FROM domains
    WHERE domain_name = 'activatecharm.com'
    AND workspace_id = charm_workspace_id;

    IF activate_domain_id IS NULL THEN
        RAISE NOTICE 'activatecharm.com not found for Charm';
        RETURN;
    END IF;

    -- Clear job_id from ALL Charm domains (remove incorrect backfill)
    UPDATE domains
    SET job_id = NULL
    WHERE workspace_id = charm_workspace_id
    AND job_id IS NOT NULL;

    RAISE NOTICE 'Cleared job_id from legacy domains';

    -- Delete the incorrect backfill job
    DELETE FROM domain_purchase_jobs
    WHERE client_id = charm_client_id
    AND results->>'note' LIKE 'Backfilled%';

    RAISE NOTICE 'Deleted incorrect backfill job';

    -- Create correct purchase job for activatecharm.com only
    new_job_id := gen_random_uuid();

    INSERT INTO domain_purchase_jobs (
        id,
        client_id,
        workspace_id,
        domain_ids,
        domain_names,
        registrar,
        status,
        successful_count,
        failed_count,
        total_cost,
        results,
        created_at,
        started_at,
        completed_at
    ) VALUES (
        new_job_id,
        charm_client_id,
        charm_workspace_id,
        ARRAY[activate_domain_id],
        ARRAY['activatecharm.com'],
        'porkbun',
        'completed',
        1,
        0,
        9.99,  -- Price from Porkbun screenshot
        jsonb_build_object(
            'note', 'activatecharm.com purchased via Porkbun',
            'created_at', NOW()
        ),
        '2026-02-28 00:00:00+00'::timestamptz,
        '2026-02-28 00:00:00+00'::timestamptz,
        '2026-02-28 00:00:00+00'::timestamptz
    );

    -- Link only activatecharm.com to this job
    UPDATE domains
    SET job_id = new_job_id,
        selected_provider = 'porkbun'
    WHERE id = activate_domain_id;

    RAISE NOTICE 'Created purchase job % for activatecharm.com', new_job_id;
END $$;
