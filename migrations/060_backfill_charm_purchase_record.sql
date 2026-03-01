-- Migration 060: Backfill domain purchase record for Charm
-- Creates a historical domain_purchase_jobs record for already-purchased domains

-- Get Charm's client_id and workspace_id
DO $$
DECLARE
    charm_client_id UUID := '4bd07dc0-059a-448b-b6f4-3275d0c104a9';
    charm_workspace_id UUID;
    new_job_id UUID;
    purchased_domain_ids UUID[];
    purchased_domain_names TEXT[];
    domain_count INT;
BEGIN
    -- Get Charm's workspace
    SELECT workspace_id INTO charm_workspace_id
    FROM clients WHERE id = charm_client_id;

    -- Get all purchased domains for Charm that don't have a job_id
    SELECT
        ARRAY_AGG(d.id),
        ARRAY_AGG(d.domain_name)
    INTO purchased_domain_ids, purchased_domain_names
    FROM domains d
    WHERE d.workspace_id = charm_workspace_id
    AND d.purchased_at IS NOT NULL
    AND d.job_id IS NULL;

    domain_count := COALESCE(array_length(purchased_domain_ids, 1), 0);

    IF domain_count > 0 THEN
        -- Create a historical purchase job record
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
            purchased_domain_ids,
            purchased_domain_names,
            'dynadot',  -- Historical purchases were via Dynadot
            'completed',
            domain_count,
            0,
            0,  -- Historical cost unknown
            jsonb_build_object(
                'note', 'Backfilled historical purchase record',
                'domains_count', domain_count,
                'backfilled_at', NOW()
            ),
            '2026-02-12 02:16:46.274593+00',  -- Original purchase date
            '2026-02-12 02:16:46.274593+00',
            '2026-02-12 02:16:46.274593+00'
        );

        -- Update domains to reference this job
        UPDATE domains
        SET job_id = new_job_id
        WHERE id = ANY(purchased_domain_ids);

        RAISE NOTICE 'Created purchase job % for % domains', new_job_id, domain_count;
    ELSE
        RAISE NOTICE 'No purchased domains without job_id found for Charm';
    END IF;
END $$;
