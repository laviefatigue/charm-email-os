--
-- PostgreSQL database dump
--

\restrict cpVonRaZ5pmXlv1YjfacbSpx0PoaEXnYyIAGsfqCWjdQSaxRgFxo836O8R7C8zM

-- Dumped from database version 15.8
-- Dumped by pg_dump version 16.11

SET statement_timeout = 0;
CREATE EXTENSION IF NOT EXISTS pgcrypto;

SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

--
-- Name: public; Type: SCHEMA; Schema: -; Owner: -
--

CREATE SCHEMA IF NOT EXISTS public;


--
-- Name: alert_severity; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.alert_severity AS ENUM (
    'low',
    'medium',
    'high',
    'critical'
);


--
-- Name: campaign_state; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.campaign_state AS ENUM (
    'live',
    'quarantined',
    'dead'
);


--
-- Name: domain_state; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.domain_state AS ENUM (
    'live',
    'flagged',
    'dead'
);


--
-- Name: esp_type; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.esp_type AS ENUM (
    'gmail',
    'microsoft',
    'yahoo',
    'other'
);


--
-- Name: health_event_type; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.health_event_type AS ENUM (
    'inbox_killed',
    'inbox_swapped',
    'domain_flagged',
    'domain_killed',
    'campaign_quarantined',
    'campaign_killed',
    'segment_quarantined',
    'placement_test_failed',
    'placement_test_passed',
    'alert_triggered',
    'kill_trigger_fired',
    'retest_scheduled',
    'backup_promoted'
);


--
-- Name: inbox_role; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.inbox_role AS ENUM (
    'primary',
    'hot_backup',
    'warming'
);


--
-- Name: inbox_state; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.inbox_state AS ENUM (
    'live',
    'dead'
);


--
-- Name: kill_trigger_type; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.kill_trigger_type AS ENUM (
    'spam_complaint',
    'hard_bounces_24h',
    'consecutive_hard_bounces',
    'hard_bounce_rate_7d',
    'bounce_rate_all_7d',
    'provider_block',
    'fresh_inbox_bounce',
    'placement_failure',
    'spam_folder_rate',
    'degrading_trend'
);


--
-- Name: processing_status; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.processing_status AS ENUM (
    'pending',
    'processing',
    'completed',
    'failed'
);


--
-- Name: segment_state; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.segment_state AS ENUM (
    'active',
    'quarantined',
    'purged'
);


--
-- Name: archive_old_partitions(integer); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.archive_old_partitions(retention_months integer DEFAULT 3) RETURNS TABLE(archived_partition text, partition_date date)
    LANGUAGE plpgsql
    AS $_$
DECLARE
    partition_record RECORD;
    cutoff_date DATE;
    archive_table_name TEXT;
BEGIN
    cutoff_date := DATE_TRUNC('month', NOW() - (retention_months || ' months')::INTERVAL)::DATE;

    RAISE NOTICE 'Archiving partitions older than % (cutoff: %)', retention_months || ' months', cutoff_date;

    FOR partition_record IN
        SELECT
            tablename,
            TO_DATE(
                SUBSTRING(tablename FROM '\d{4}_\d{2}$'),
                'YYYY_MM'
            ) as partition_start_date
        FROM pg_tables
        WHERE schemaname = 'public'
        AND tablename LIKE 'rbl_check_logs_%'
        AND tablename ~ 'rbl_check_logs_\d{4}_\d{2}$'
    LOOP
        IF partition_record.partition_start_date < cutoff_date THEN
            -- Detach partition from parent table
            EXECUTE format('ALTER TABLE rbl_check_logs DETACH PARTITION %I', partition_record.tablename);

            -- Move to archive schema
            archive_table_name := 'archive.' || partition_record.tablename;
            EXECUTE format('ALTER TABLE %I SET SCHEMA archive', partition_record.tablename);

            archived_partition := partition_record.tablename;
            partition_date := partition_record.partition_start_date;

            RAISE NOTICE 'Archived partition: % → % (date: %)',
                partition_record.tablename,
                archive_table_name,
                partition_date;

            RETURN NEXT;
        END IF;
    END LOOP;
END;
$_$;


--
-- Name: archive_old_rbl_results(); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.archive_old_rbl_results() RETURNS void
    LANGUAGE plpgsql
    AS $$
BEGIN
    -- Delete check results older than 90 days
    DELETE FROM rbl_check_results
    WHERE checked_at < NOW() - INTERVAL '90 days';

    -- Delete orphaned check runs
    DELETE FROM rbl_check_runs r
    WHERE NOT EXISTS (
        SELECT 1 FROM rbl_check_results c WHERE c.run_id = r.id
    );

    RAISE NOTICE 'Archived old RBL check results';
END;
$$;


--
-- Name: attribute_unattributed_bounces(); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.attribute_unattributed_bounces() RETURNS integer
    LANGUAGE plpgsql
    AS $$

DECLARE

    attributed_count INTEGER;

BEGIN

    -- Update campaign_events where sender_account_id is NULL

    -- but campaign has exactly one inbox assigned

    UPDATE campaign_events ce

    SET sender_account_id = ci.sender_account_id

    FROM (

        SELECT

            ci.emailbison_campaign_id,

            ci.sender_account_id

        FROM campaign_inboxes ci

        JOIN (

            SELECT emailbison_campaign_id

            FROM campaign_inboxes

            WHERE is_active = TRUE

            GROUP BY emailbison_campaign_id

            HAVING COUNT(*) = 1

        ) single ON single.emailbison_campaign_id = ci.emailbison_campaign_id

        WHERE ci.is_active = TRUE

    ) ci

    JOIN emailbison_campaigns ec ON ec.emailbison_campaign_id = ci.emailbison_campaign_id

    WHERE ce.campaign_id = ec.id

    AND ce.sender_account_id IS NULL

    AND ce.event_type = 'bounce';



    GET DIAGNOSTICS attributed_count = ROW_COUNT;



    RETURN attributed_count;

END;

$$;


--
-- Name: create_check_run(character varying, character varying, character varying, character varying); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.create_check_run(p_run_name character varying, p_source character varying, p_prefect_flow_run_id character varying DEFAULT NULL::character varying, p_prefect_flow_name character varying DEFAULT NULL::character varying) RETURNS uuid
    LANGUAGE plpgsql
    AS $$
DECLARE
    v_run_id UUID;
BEGIN
    INSERT INTO rbl_check_runs (
        id,
        run_name,
        source,
        created_at,
        run_status,
        total_domains_checked,
        domains_clean,
        domains_flagged,
        domains_requiring_review,
        error_count,
        prefect_flow_run_id,
        prefect_flow_name
    )
    VALUES (
        uuid_generate_v4(),
        p_run_name,
        p_source,
        NOW(),
        'running',
        0, 0, 0, 0, 0,
        p_prefect_flow_run_id,
        p_prefect_flow_name
    )
    RETURNING id INTO v_run_id;

    RETURN v_run_id;
END;
$$;


--
-- Name: create_next_month_partition(); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.create_next_month_partition() RETURNS void
    LANGUAGE plpgsql
    AS $$
DECLARE
    next_month_start DATE;
    next_month_end DATE;
    partition_name TEXT;
BEGIN
    -- Calculate next month's start date (first day of month after current month)
    next_month_start := DATE_TRUNC('month', NOW() + INTERVAL '1 month')::DATE;
    next_month_end := DATE_TRUNC('month', NOW() + INTERVAL '2 months')::DATE;

    -- Generate partition name (e.g., rbl_check_logs_2025_10)
    partition_name := 'rbl_check_logs_' || TO_CHAR(next_month_start, 'YYYY_MM');

    -- Check if partition already exists
    IF NOT EXISTS (
        SELECT 1 FROM pg_tables
        WHERE schemaname = 'public'
        AND tablename = partition_name
    ) THEN
        -- Create partition
        EXECUTE format(
            'CREATE TABLE %I PARTITION OF rbl_check_logs FOR VALUES FROM (%L) TO (%L)',
            partition_name,
            next_month_start,
            next_month_end
        );

        -- Add comment
        EXECUTE format(
            'COMMENT ON TABLE %I IS %L',
            partition_name,
            'RBL check logs partition for ' || TO_CHAR(next_month_start, 'Month YYYY')
        );

        RAISE NOTICE 'Created partition: % (% to %)', partition_name, next_month_start, next_month_end;
    ELSE
        RAISE NOTICE 'Partition % already exists', partition_name;
    END IF;
END;
$$;


--
-- Name: create_removal_event(uuid, uuid, text, text, timestamp with time zone); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.create_removal_event(p_sender_account_id uuid, p_workspace_id uuid, p_removal_reason text, p_kill_trigger text, p_tagged_at timestamp with time zone) RETURNS uuid
    LANGUAGE plpgsql
    AS $$

DECLARE

    v_event_id UUID;

    v_hard_bounces_24h INTEGER;

    v_hard_bounces_7d INTEGER;

    v_soft_bounces_7d INTEGER;

    v_total_sends_7d INTEGER;

BEGIN

    -- Get current metrics from sender_accounts

    SELECT

        hard_bounces_24h,

        hard_bounces_7d,

        soft_bounces_7d,

        total_sends_7d

    INTO

        v_hard_bounces_24h,

        v_hard_bounces_7d,

        v_soft_bounces_7d,

        v_total_sends_7d

    FROM sender_accounts

    WHERE id = p_sender_account_id;



    -- Insert removal event

    INSERT INTO inbox_removal_events (

        sender_account_id,

        workspace_id,

        removal_reason,

        kill_trigger,

        tagged_at,

        hard_bounces_24h,

        hard_bounces_7d,

        soft_bounces_7d,

        total_sends_7d

    ) VALUES (

        p_sender_account_id,

        p_workspace_id,

        p_removal_reason,

        p_kill_trigger,

        p_tagged_at,

        v_hard_bounces_24h,

        v_hard_bounces_7d,

        v_soft_bounces_7d,

        v_total_sends_7d

    )

    RETURNING id INTO v_event_id;



    RETURN v_event_id;

END;

$$;


--
-- Name: detect_rbl_alerts(); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.detect_rbl_alerts() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
DECLARE
    v_previous_health DECIMAL(5,2);
    v_health_drop DECIMAL(5,2);
    v_critical_listings INTEGER;
BEGIN
    -- Get previous health score
    SELECT last_health_score INTO v_previous_health
    FROM monitored_ips
    WHERE id = NEW.monitored_ip_id;

    -- Health drop alert
    IF v_previous_health IS NOT NULL THEN
        v_health_drop := v_previous_health - NEW.health_score;

        IF v_health_drop > 20 THEN
            INSERT INTO rbl_alerts (
                monitored_ip_id, alert_type, severity, ip_address,
                health_score, previous_health_score, message
            ) VALUES (
                NEW.monitored_ip_id, 'health_drop', 'critical', NEW.ip_address,
                NEW.health_score, v_previous_health,
                format('Health score dropped by %.2f points (%.2f → %.2f)',
                       v_health_drop, v_previous_health, NEW.health_score)
            );
        END IF;
    END IF;

    -- New listings alert (if previously clean)
    IF v_previous_health = 100 AND NEW.health_score < 100 THEN
        INSERT INTO rbl_alerts (
            monitored_ip_id, alert_type, severity, ip_address,
            health_score, previous_health_score, message, details
        ) VALUES (
            NEW.monitored_ip_id, 'new_listing', 'warning', NEW.ip_address,
            NEW.health_score, v_previous_health,
            format('IP %s newly listed on %s RBL(s)', NEW.ip_address::text, NEW.listed_count),
            jsonb_build_object('listed_count', NEW.listed_count, 'rbl_results', NEW.rbl_results)
        );
    END IF;

    -- Critical RBL alert (Spamhaus, etc.)
    SELECT COUNT(*) INTO v_critical_listings
    FROM jsonb_array_elements(NEW.rbl_results) AS rbl
    WHERE (rbl->>'listed')::boolean = true
      AND (rbl->>'rbl_name') IN ('Spamhaus ZEN', 'Spamhaus SBL', 'SpamCop');

    IF v_critical_listings > 0 THEN
        INSERT INTO rbl_alerts (
            monitored_ip_id, alert_type, severity, ip_address,
            health_score, message
        ) VALUES (
            NEW.monitored_ip_id, 'critical_rbl', 'critical', NEW.ip_address,
            NEW.health_score,
            format('IP %s listed on %s critical RBL(s)', NEW.ip_address::text, v_critical_listings)
        );
    END IF;

    RETURN NEW;
END;
$$;


--
-- Name: drop_old_partitions(integer); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.drop_old_partitions(retention_months integer DEFAULT 3) RETURNS TABLE(dropped_partition text, partition_date date)
    LANGUAGE plpgsql
    AS $_$
DECLARE
    partition_record RECORD;
    cutoff_date DATE;
BEGIN
    -- Calculate cutoff date
    cutoff_date := DATE_TRUNC('month', NOW() - (retention_months || ' months')::INTERVAL)::DATE;

    RAISE NOTICE 'Dropping partitions older than % (cutoff: %)', retention_months || ' months', cutoff_date;

    -- Loop through all rbl_check_logs partitions
    FOR partition_record IN
        SELECT
            tablename,
            -- Extract date from partition name (e.g., rbl_check_logs_2025_10 -> 2025-10-01)
            TO_DATE(
                SUBSTRING(tablename FROM '\d{4}_\d{2}$'),
                'YYYY_MM'
            ) as partition_start_date
        FROM pg_tables
        WHERE schemaname = 'public'
        AND tablename LIKE 'rbl_check_logs_%'
        AND tablename ~ 'rbl_check_logs_\d{4}_\d{2}$'
    LOOP
        -- Drop partition if older than cutoff
        IF partition_record.partition_start_date < cutoff_date THEN
            EXECUTE format('DROP TABLE IF EXISTS %I CASCADE', partition_record.tablename);

            dropped_partition := partition_record.tablename;
            partition_date := partition_record.partition_start_date;

            RAISE NOTICE 'Dropped partition: % (date: %)', dropped_partition, partition_date;

            RETURN NEXT;
        END IF;
    END LOOP;
END;
$_$;


--
-- find_similar_leads function removed (requires pgvector)

--
-- Name: fn_create_lead_pull_job(); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.fn_create_lead_pull_job() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
DECLARE
    v_submission_id UUID;
    v_criteria JSONB;
    v_titles JSONB;
    v_signals JSONB;
    v_target TEXT;
    v_pain_points TEXT[];
    v_persona_titles TEXT[];
BEGIN
    -- Only fire when status changes TO 'approved'
    IF NEW.status = 'approved' AND (OLD.status IS NULL OR OLD.status != 'approved') THEN

        -- Get the active onboarding submission for this client
        SELECT id, job_titles, signals, target_customer
        INTO v_submission_id, v_titles, v_signals, v_target
        FROM client_onboarding_submissions
        WHERE client_id = NEW.client_id AND is_active = TRUE
        ORDER BY created_at DESC
        LIMIT 1;

        -- Get persona job titles
        IF v_submission_id IS NOT NULL THEN
            SELECT array_agg(job_title)
            INTO v_persona_titles
            FROM client_personas
            WHERE submission_id = v_submission_id;
        END IF;

        -- Get segment pain points for search keywords
        IF v_submission_id IS NOT NULL THEN
            SELECT array_agg(pain_points)
            INTO v_pain_points
            FROM client_segments
            WHERE submission_id = v_submission_id
              AND pain_points IS NOT NULL;
        END IF;

        -- Build search criteria JSON
        v_criteria := jsonb_build_object(
            'title_keywords', COALESCE(v_titles, '[]'::jsonb),
            'persona_titles', COALESCE(to_jsonb(v_persona_titles), '[]'::jsonb),
            'industry', COALESCE(v_target, ''),
            'search_keywords', COALESCE(to_jsonb(v_pain_points), '[]'::jsonb),
            'signals', COALESCE(v_signals, '[]'::jsonb),
            'campaign_type', COALESCE(NEW.campaign_type, ''),
            'subject_line', COALESCE(NEW.subject_line, ''),
            'variant_number', COALESCE(NEW.variant_number, 1)
        );

        INSERT INTO lead_pull_jobs (
            client_id, suggestion_id, submission_id,
            volume, search_criteria, status
        ) VALUES (
            NEW.client_id, NEW.id, v_submission_id,
            500, v_criteria, 'pending'
        );
    END IF;

    RETURN NEW;
END;
$$;


--
-- Name: get_project_costs(uuid); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.get_project_costs(p_project_id uuid) RETURNS TABLE(service character varying, total_cost double precision, operation_count bigint)
    LANGUAGE plpgsql
    AS $$
BEGIN
    RETURN QUERY
    SELECT
        c.service,
        SUM(c.cost)::FLOAT AS total_cost,
        COUNT(*)::BIGINT AS operation_count
    FROM cost_logs c
    WHERE c.project_id = p_project_id
    GROUP BY c.service
    ORDER BY total_cost DESC;
END;
$$;


--
-- Name: log_inbox_kill_event(); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.log_inbox_kill_event() RETURNS trigger
    LANGUAGE plpgsql
    AS $$

BEGIN

    IF OLD.inbox_state = 'live' AND NEW.inbox_state = 'dead' THEN

        INSERT INTO health_events (

            event_type,

            severity,

            entity_type,

            entity_id,

            entity_name,

            workspace_id,

            trigger_type,

            details,

            metrics_snapshot

        ) VALUES (

            'inbox_killed',

            'high',

            'inbox',

            NEW.id,

            NEW.email_address,

            NEW.workspace_id,

            NEW.kill_trigger,

            jsonb_build_object(

                'kill_reason', NEW.kill_reason,

                'killed_at', NEW.killed_at

            ),

            jsonb_build_object(

                'hard_bounces_24h', NEW.hard_bounces_24h,

                'hard_bounces_7d', NEW.hard_bounces_7d,

                'complaints_lifetime', NEW.complaints_lifetime,

                'consecutive_hard_bounces', NEW.consecutive_hard_bounces,

                'last_placement_primary', NEW.last_placement_primary,

                'last_placement_spam', NEW.last_placement_spam

            )

        );

    END IF;

    RETURN NEW;

END;

$$;


--
-- Name: record_run_error(uuid, character varying, text, jsonb); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.record_run_error(p_run_id uuid, p_workspace_name character varying, p_error_message text, p_error_context jsonb DEFAULT NULL::jsonb) RETURNS void
    LANGUAGE plpgsql
    AS $$
BEGIN
    -- Update run-level error count
    UPDATE rbl_check_runs
    SET
        error_count = error_count + 1,
        run_errors = COALESCE(run_errors, '[]'::jsonb) ||
            jsonb_build_object(
                'timestamp', NOW(),
                'workspace', p_workspace_name,
                'message', p_error_message,
                'context', p_error_context
            )
    WHERE id = p_run_id;

    -- Update workspace-level error tracking
    INSERT INTO workspace_check_summary (
        run_id,
        workspace_name,
        error_count,
        errors
    )
    VALUES (
        p_run_id,
        p_workspace_name,
        1,
        jsonb_build_array(
            jsonb_build_object(
                'timestamp', NOW(),
                'message', p_error_message,
                'context', p_error_context
            )
        )
    )
    ON CONFLICT (run_id, workspace_name)
    DO UPDATE SET
        error_count = workspace_check_summary.error_count + 1,
        errors = COALESCE(workspace_check_summary.errors, '[]'::jsonb) ||
            jsonb_build_object(
                'timestamp', NOW(),
                'message', p_error_message,
                'context', p_error_context
            );
END;
$$;


--
-- Name: tag_inbox_for_removal(uuid, text); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.tag_inbox_for_removal(p_sender_account_id uuid, p_tag text) RETURNS void
    LANGUAGE plpgsql
    AS $$

BEGIN

    UPDATE sender_accounts

    SET removal_tag = p_tag,

        removal_tagged_at = NOW()

    WHERE id = p_sender_account_id

      AND removal_tag IS NULL;  -- Don't re-tag already tagged inboxes

END;

$$;


--
-- Name: update_campaign_inboxes_updated_at(); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.update_campaign_inboxes_updated_at() RETURNS trigger
    LANGUAGE plpgsql
    AS $$

BEGIN

    NEW.updated_at = NOW();

    RETURN NEW;

END;

$$;


--
-- Name: update_campaign_last_snapshot(); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.update_campaign_last_snapshot() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
BEGIN
    -- Update last_snapshot_at in emailbison_campaigns
    UPDATE emailbison_campaigns
    SET last_snapshot_at = NEW.snapshot_timestamp
    WHERE id = NEW.campaign_id;

    RETURN NEW;
END;
$$;


--
-- Name: update_client_onboarding_status(); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.update_client_onboarding_status() RETURNS trigger
    LANGUAGE plpgsql
    AS $$

BEGIN

    -- When submission is marked as 'completed', mark client as onboarded

    IF NEW.submission_status = 'completed' AND (OLD.submission_status IS NULL OR OLD.submission_status != 'completed') THEN

        UPDATE clients

        SET onboarding_complete = TRUE,

            updated_at = NOW()

        WHERE id = NEW.client_id;

    END IF;

    RETURN NEW;

END;

$$;


--
-- Name: update_domain_health_on_inbox_change(); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.update_domain_health_on_inbox_change() RETURNS trigger
    LANGUAGE plpgsql
    AS $$

BEGIN

    -- Recalculate domain health metrics

    WITH inbox_stats AS (

        SELECT

            domain_id,

            COUNT(*) FILTER (WHERE inbox_state = 'live') as live_count,

            COUNT(*) FILTER (WHERE inbox_state = 'dead') as dead_count,

            COUNT(*) as total_count

        FROM sender_accounts

        WHERE domain_id = COALESCE(NEW.domain_id, OLD.domain_id)

        AND domain_id IS NOT NULL

        GROUP BY domain_id

    )

    UPDATE domains d

    SET

        live_inbox_count = COALESCE(s.live_count, 0),

        dead_inbox_count = COALESCE(s.dead_count, 0),

        health_percentage = CASE

            WHEN COALESCE(s.total_count, 0) = 0 THEN 100.00

            ELSE (COALESCE(s.live_count, 0)::DECIMAL / s.total_count * 100)

        END,

        -- Update domain state based on dead inbox count

        domain_state = CASE

            WHEN COALESCE(s.dead_count, 0) >= 2 THEN 'dead'::domain_state

            WHEN COALESCE(s.dead_count, 0) = 1 THEN 'flagged'::domain_state

            ELSE 'live'::domain_state

        END,

        killed_at = CASE

            WHEN COALESCE(s.dead_count, 0) >= 2 AND d.killed_at IS NULL THEN NOW()

            ELSE d.killed_at

        END,

        updated_at = NOW()

    FROM inbox_stats s

    WHERE d.id = s.domain_id;



    RETURN COALESCE(NEW, OLD);

END;

$$;


--
-- Name: update_domain_latest_health(); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.update_domain_latest_health() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
BEGIN
    -- Update denormalized fields in domains table
    UPDATE domains
    SET
        latest_health_score = NEW.health_score,
        latest_blacklist_count = NEW.blacklist_count,
        latest_whitelist_count = NEW.whitelist_count,
        is_clean = NEW.is_clean,
        last_checked_at = NEW.check_timestamp
    WHERE id = NEW.domain_id;

    RETURN NEW;
END;
$$;


--
-- Name: update_domain_lifecycle_stage(); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.update_domain_lifecycle_stage() RETURNS trigger
    LANGUAGE plpgsql
    AS $$

DECLARE

    age_days INTEGER;

BEGIN

    -- Compute domain age dynamically

    age_days := EXTRACT(DAY FROM (NOW() - NEW.created_at))::INTEGER;

    NEW.domain_age_days = age_days;



    NEW.lifecycle_stage = CASE

        WHEN age_days < 14 THEN 'warming'

        WHEN age_days < 30 THEN 'ramping'

        WHEN age_days < 90 THEN 'establishing'

        WHEN age_days < 180 THEN 'peak'

        WHEN age_days < 240 THEN 'monitoring'

        ELSE 'rotation'

    END;



    -- Set rotation due date at 240 days from creation

    IF NEW.rotation_due_at IS NULL THEN

        NEW.rotation_due_at = NEW.created_at + INTERVAL '240 days';

    END IF;



    RETURN NEW;

END;

$$;


--
-- Name: update_inbox_metrics_from_events(); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.update_inbox_metrics_from_events() RETURNS integer
    LANGUAGE plpgsql
    AS $$

DECLARE

    updated_count INTEGER;

BEGIN

    UPDATE sender_accounts sa

    SET

        hard_bounces_24h = ibs.hard_bounces_24h,

        hard_bounces_7d = ibs.hard_bounces_7d,

        soft_bounces_7d = ibs.soft_bounces_7d,

        updated_at = NOW()

    FROM inbox_bounce_summary ibs

    WHERE sa.id = ibs.sender_account_id

    AND (

        sa.hard_bounces_24h IS DISTINCT FROM ibs.hard_bounces_24h

        OR sa.hard_bounces_7d IS DISTINCT FROM ibs.hard_bounces_7d

        OR sa.soft_bounces_7d IS DISTINCT FROM ibs.soft_bounces_7d

    );



    GET DIAGNOSTICS updated_count = ROW_COUNT;



    RETURN updated_count;

END;

$$;


--
-- Name: update_monitored_domain_from_check(); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.update_monitored_domain_from_check() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
BEGIN
    -- Update monitored_domains with latest check results
    UPDATE monitored_domains
    SET
        last_checked_at = NEW.checked_at,
        last_health_score = NEW.health_score,
        is_currently_clean = NEW.is_clean,
        current_listed_count = NEW.listed_count,
        updated_at = NOW()
    WHERE id = NEW.domain_id;

    RETURN NEW;
END;
$$;


--
-- Name: update_monitored_ip_health(); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.update_monitored_ip_health() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
BEGIN
    UPDATE monitored_ips
    SET
        last_checked_at = NEW.checked_at,
        last_health_score = NEW.health_score,
        updated_at = NOW()
    WHERE id = NEW.monitored_ip_id;

    RETURN NEW;
END;
$$;


--
-- Name: update_run_statistics(uuid); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.update_run_statistics(p_run_id uuid) RETURNS void
    LANGUAGE plpgsql
    AS $$
DECLARE
    v_stats RECORD;
BEGIN
    -- Aggregate statistics from domain_check_results
    SELECT
        COUNT(*) AS total_checked,
        COUNT(*) FILTER (WHERE is_clean = TRUE) AS clean_count,
        COUNT(*) FILTER (WHERE is_clean = FALSE) AS flagged_count,
        COUNT(*) FILTER (WHERE health_score < 70) AS review_count,
        ROUND(AVG(health_score), 2) AS avg_health
    INTO v_stats
    FROM domain_check_results
    WHERE run_id = p_run_id;

    -- Update rbl_check_runs
    UPDATE rbl_check_runs
    SET
        total_domains_checked = v_stats.total_checked,
        domains_clean = v_stats.clean_count,
        domains_flagged = v_stats.flagged_count,
        domains_requiring_review = v_stats.review_count,
        average_health_score = v_stats.avg_health,
        run_status = 'completed',
        completed_at = NOW()
    WHERE id = p_run_id;

    -- Update workspace summaries
    INSERT INTO workspace_check_summary (
        run_id,
        workspace_name,
        workspace_id,
        domains_checked,
        domains_clean,
        domains_flagged,
        domains_requiring_review,
        average_health_score,
        error_count
    )
    SELECT
        p_run_id,
        COALESCE(md.workspace_names[1], 'unknown') AS workspace_name,
        md.workspace_id,
        COUNT(*) AS domains_checked,
        COUNT(*) FILTER (WHERE dcr.is_clean = TRUE) AS domains_clean,
        COUNT(*) FILTER (WHERE dcr.is_clean = FALSE) AS domains_flagged,
        COUNT(*) FILTER (WHERE dcr.health_score < 70) AS domains_requiring_review,
        ROUND(AVG(dcr.health_score), 2) AS average_health_score,
        0 AS error_count  -- Updated separately by error tracking
    FROM domain_check_results dcr
    JOIN monitored_domains md ON dcr.domain_id = md.id
    WHERE dcr.run_id = p_run_id
    GROUP BY md.workspace_names[1], md.workspace_id
    ON CONFLICT (run_id, workspace_name)
    DO UPDATE SET
        domains_checked = EXCLUDED.domains_checked,
        domains_clean = EXCLUDED.domains_clean,
        domains_flagged = EXCLUDED.domains_flagged,
        domains_requiring_review = EXCLUDED.domains_requiring_review,
        average_health_score = EXCLUDED.average_health_score;

END;
$$;


--
-- Name: update_updated_at(); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.update_updated_at() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$;


--
-- Name: update_updated_at_column(); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.update_updated_at_column() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$;


--
-- Name: update_workspace_domain_count(); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.update_workspace_domain_count() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
BEGIN
    -- Recalculate domain_count for affected workspace
    UPDATE workspaces
    SET domain_count = (
        SELECT COUNT(*)
        FROM domains
        WHERE workspace_id = COALESCE(NEW.workspace_id, OLD.workspace_id)
        AND is_active = TRUE
    )
    WHERE id = COALESCE(NEW.workspace_id, OLD.workspace_id);

    RETURN COALESCE(NEW, OLD);
END;
$$;


--
-- Name: update_workspace_sender_count(); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.update_workspace_sender_count() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
BEGIN
    -- Recalculate sender_account_count for affected workspace
    UPDATE workspaces
    SET sender_account_count = (
        SELECT COUNT(*)
        FROM sender_accounts
        WHERE workspace_id = COALESCE(NEW.workspace_id, OLD.workspace_id)
        AND is_active = TRUE
    )
    WHERE id = COALESCE(NEW.workspace_id, OLD.workspace_id);

    RETURN COALESCE(NEW, OLD);
END;
$$;


SET default_table_access_method = heap;

--
-- Name: _migrations; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public._migrations (
    name character varying(255) NOT NULL,
    applied_at timestamp without time zone DEFAULT now()
);


--
-- Name: campaign_cycles; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.campaign_cycles (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    client_id uuid NOT NULL,
    strategy_id uuid,
    cycle_number integer NOT NULL,
    cycle_name character varying(100),
    start_date date,
    end_date date,
    duration_days integer DEFAULT 14,
    target_campaigns integer,
    actual_campaigns integer DEFAULT 0,
    status character varying(50) DEFAULT 'planned'::character varying,
    notes text,
    created_at timestamp without time zone DEFAULT now(),
    updated_at timestamp without time zone DEFAULT now()
);


--
-- Name: campaign_documents; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.campaign_documents (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    job_id uuid NOT NULL,
    client_id uuid NOT NULL,
    strategy_id uuid,
    document_name character varying(255) NOT NULL,
    document_version integer DEFAULT 1,
    vertical character varying(100),
    objective text,
    icp_mapping jsonb,
    variable_schema jsonb,
    sequence_summary jsonb,
    qa_scoring jsonb,
    strategy_notes jsonb,
    status character varying(50) DEFAULT 'draft'::character varying,
    human_comment text,
    reviewed_by character varying(255),
    reviewed_at timestamp without time zone,
    created_at timestamp without time zone DEFAULT now(),
    updated_at timestamp without time zone DEFAULT now()
);


--
-- Name: campaign_events; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.campaign_events (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    campaign_id uuid NOT NULL,
    sender_account_id uuid,
    event_timestamp timestamp with time zone DEFAULT now() NOT NULL,
    event_type text NOT NULL,
    emailbison_lead_id text,
    lead_email text,
    lead_name text,
    lead_company text,
    event_data jsonb,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT campaign_events_type_valid CHECK ((event_type = ANY (ARRAY['reply'::text, 'interested_reply'::text, 'automated_reply'::text, 'bounce'::text, 'unsubscribe'::text, 'spam'::text, 'sending_error'::text])))
);


--
-- Name: campaign_inboxes; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.campaign_inboxes (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    campaign_id uuid,
    sender_account_id uuid,
    emailbison_campaign_id text NOT NULL,
    emailbison_sender_id integer NOT NULL,
    assigned_at timestamp with time zone DEFAULT now(),
    removed_at timestamp with time zone,
    is_active boolean DEFAULT true,
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone DEFAULT now()
);


--
-- Name: emailbison_campaigns; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.emailbison_campaigns (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    workspace_id uuid NOT NULL,
    emailbison_campaign_id text NOT NULL,
    campaign_name text NOT NULL,
    campaign_status text,
    campaign_type text,
    total_leads integer DEFAULT 0,
    total_leads_contacted integer DEFAULT 0,
    emails_sent integer DEFAULT 0,
    completion_percentage numeric(5,2),
    is_active boolean DEFAULT true NOT NULL,
    first_seen_at timestamp with time zone DEFAULT now() NOT NULL,
    last_seen_at timestamp with time zone DEFAULT now() NOT NULL,
    last_snapshot_at timestamp with time zone,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    notes text,
    paused_at timestamp with time zone,
    completed_at timestamp with time zone,
    completed_snapshot_taken boolean DEFAULT false NOT NULL,
    campaign_state public.campaign_state DEFAULT 'live'::public.campaign_state,
    quarantined_at timestamp with time zone,
    quarantine_reason text,
    killed_at timestamp with time zone,
    kill_reason text,
    total_sends integer DEFAULT 0,
    bounces integer DEFAULT 0,
    bounce_rate numeric(5,4) DEFAULT 0,
    complaints integer DEFAULT 0,
    inboxes_burned integer DEFAULT 0,
    domains_affected integer DEFAULT 0,
    copy_created_at timestamp with time zone,
    copy_version integer DEFAULT 1,
    copy_age_days integer,
    inboxes_burned_7d integer DEFAULT 0,
    domains_burned_7d integer DEFAULT 0,
    CONSTRAINT emailbison_campaigns_completion_range CHECK (((completion_percentage IS NULL) OR ((completion_percentage >= (0)::numeric) AND (completion_percentage <= (100)::numeric)))),
    CONSTRAINT emailbison_campaigns_emailbison_id_not_empty CHECK ((length(TRIM(BOTH FROM emailbison_campaign_id)) > 0)),
    CONSTRAINT emailbison_campaigns_name_not_empty CHECK ((length(TRIM(BOTH FROM campaign_name)) > 0))
);


--
-- Name: sender_accounts; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.sender_accounts (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    workspace_id uuid NOT NULL,
    email_address character varying(255) NOT NULL,
    emailbison_account_id text,
    status character varying(50),
    health_score integer,
    is_active boolean DEFAULT true NOT NULL,
    first_seen_at timestamp with time zone DEFAULT now() NOT NULL,
    last_seen_at timestamp with time zone DEFAULT now() NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    display_name character varying(255),
    notes text,
    removal_tagged boolean DEFAULT false NOT NULL,
    tagged_at timestamp with time zone,
    domain_id uuid,
    last_check_run_id uuid,
    inbox_state public.inbox_state DEFAULT 'live'::public.inbox_state,
    role public.inbox_role DEFAULT 'primary'::public.inbox_role,
    esp public.esp_type DEFAULT 'other'::public.esp_type,
    warmup_started_at timestamp with time zone,
    sending_started_at timestamp with time zone,
    killed_at timestamp with time zone,
    kill_reason text,
    kill_trigger public.kill_trigger_type,
    hard_bounces_24h integer DEFAULT 0,
    hard_bounces_7d integer DEFAULT 0,
    soft_bounces_7d integer DEFAULT 0,
    total_sends_7d integer DEFAULT 0,
    complaints_lifetime integer DEFAULT 0,
    consecutive_hard_bounces integer DEFAULT 0,
    last_placement_test_at timestamp with time zone,
    last_placement_primary numeric(5,2),
    last_placement_spam numeric(5,2),
    last_placement_other numeric(5,2),
    consecutive_placement_failures integer DEFAULT 0,
    flagged_for_retest boolean DEFAULT false,
    retest_scheduled_at timestamp with time zone,
    retest_trigger public.kill_trigger_type,
    gmail_reputation character varying(20),
    microsoft_snds_status character varying(20),
    hard_bounce_rate_7d numeric(5,4),
    total_bounce_rate_7d numeric(5,4),
    inbox_age_days integer,
    removal_tag text,
    removal_tagged_at timestamp with time zone,
    bounce_rate_7d numeric(5,2) DEFAULT 0,
    last_synced_at timestamp without time zone,
    pool_tier character varying(20) DEFAULT 'primary'::character varying,
    CONSTRAINT sender_accounts_email_format CHECK (((email_address)::text ~* '^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}$'::text)),
    CONSTRAINT sender_accounts_email_not_empty CHECK ((length(TRIM(BOTH FROM email_address)) > 0))
);


--
-- Name: campaign_inbox_counts; Type: VIEW; Schema: public; Owner: -
--

CREATE VIEW public.campaign_inbox_counts AS
 SELECT ec.id AS campaign_id,
    ec.campaign_name,
    ec.emailbison_campaign_id,
    count(ci.sender_account_id) AS inbox_count,
    array_agg(sa.email_address) FILTER (WHERE (sa.email_address IS NOT NULL)) AS inbox_emails,
        CASE
            WHEN (count(ci.sender_account_id) = 1) THEN 'exact'::text
            WHEN (count(ci.sender_account_id) > 1) THEN 'proportional'::text
            ELSE 'unknown'::text
        END AS attribution_type
   FROM ((public.emailbison_campaigns ec
     LEFT JOIN public.campaign_inboxes ci ON (((ci.campaign_id = ec.id) AND (ci.is_active = true))))
     LEFT JOIN public.sender_accounts sa ON ((sa.id = ci.sender_account_id)))
  GROUP BY ec.id, ec.campaign_name, ec.emailbison_campaign_id;


--
-- Name: campaign_snapshots; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.campaign_snapshots (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    campaign_id uuid NOT NULL,
    snapshot_timestamp timestamp with time zone DEFAULT now() NOT NULL,
    period_start timestamp with time zone NOT NULL,
    period_end timestamp with time zone NOT NULL,
    emails_sent integer DEFAULT 0 NOT NULL,
    total_leads_contacted integer DEFAULT 0 NOT NULL,
    total_opens integer DEFAULT 0 NOT NULL,
    unique_opens integer DEFAULT 0 NOT NULL,
    unique_replies integer DEFAULT 0 NOT NULL,
    interested_replies integer DEFAULT 0 NOT NULL,
    bounced integer DEFAULT 0 NOT NULL,
    unsubscribed integer DEFAULT 0 NOT NULL,
    open_rate numeric(5,2),
    reply_rate numeric(5,2),
    bounce_rate numeric(5,2),
    interested_rate numeric(5,2),
    unsubscribe_rate numeric(5,2),
    active_senders integer DEFAULT 0,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    total_leads integer DEFAULT 0 NOT NULL,
    CONSTRAINT campaign_snapshots_metrics_positive CHECK (((emails_sent >= 0) AND (total_leads_contacted >= 0) AND (total_opens >= 0) AND (unique_opens >= 0) AND (unique_replies >= 0) AND (interested_replies >= 0) AND (bounced >= 0) AND (unsubscribed >= 0))),
    CONSTRAINT campaign_snapshots_period_valid CHECK ((period_end > period_start)),
    CONSTRAINT campaign_snapshots_rates_range CHECK ((((open_rate IS NULL) OR ((open_rate >= (0)::numeric) AND (open_rate <= (100)::numeric))) AND ((reply_rate IS NULL) OR ((reply_rate >= (0)::numeric) AND (reply_rate <= (100)::numeric))) AND ((bounce_rate IS NULL) OR ((bounce_rate >= (0)::numeric) AND (bounce_rate <= (100)::numeric))) AND ((interested_rate IS NULL) OR ((interested_rate >= (0)::numeric) AND (interested_rate <= (100)::numeric))) AND ((unsubscribe_rate IS NULL) OR ((unsubscribe_rate >= (0)::numeric) AND (unsubscribe_rate <= (100)::numeric)))))
);


--
-- Name: workspaces; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.workspaces (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    instance_id uuid NOT NULL,
    workspace_name character varying(255) NOT NULL,
    emailbison_workspace_id text,
    is_active boolean DEFAULT true NOT NULL,
    last_sync_at timestamp with time zone,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    sender_account_count integer DEFAULT 0,
    domain_count integer DEFAULT 0,
    notes text,
    automation_enabled boolean DEFAULT true NOT NULL,
    CONSTRAINT workspaces_name_not_empty CHECK ((length(TRIM(BOTH FROM workspace_name)) > 0))
);


--
-- Name: campaign_snapshot_trends; Type: VIEW; Schema: public; Owner: -
--

CREATE VIEW public.campaign_snapshot_trends AS
 SELECT c.id AS campaign_id,
    c.campaign_name,
    c.emailbison_campaign_id,
    w.workspace_name,
    date(s.snapshot_timestamp) AS snapshot_date,
    count(*) AS snapshot_count,
    avg(s.reply_rate) AS avg_reply_rate,
    avg(s.bounce_rate) AS avg_bounce_rate,
    avg(s.open_rate) AS avg_open_rate,
    sum(s.emails_sent) AS total_emails_sent,
    sum(s.unique_replies) AS total_unique_replies,
    sum(s.bounced) AS total_bounced
   FROM ((public.campaign_snapshots s
     JOIN public.emailbison_campaigns c ON ((s.campaign_id = c.id)))
     JOIN public.workspaces w ON ((c.workspace_id = w.id)))
  WHERE (s.snapshot_timestamp >= (now() - '30 days'::interval))
  GROUP BY c.id, c.campaign_name, c.emailbison_campaign_id, w.workspace_name, (date(s.snapshot_timestamp))
  ORDER BY (date(s.snapshot_timestamp)) DESC, c.campaign_name;


--
-- Name: client_onboarding_submissions; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.client_onboarding_submissions (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    client_id uuid NOT NULL,
    submission_version integer DEFAULT 1,
    company_name character varying(255),
    website character varying(500),
    contact_name character varying(255),
    contact_email character varying(255),
    employee_count character varying(50),
    funding_stage character varying(50),
    hq_location character varying(255),
    core_product text,
    target_customer text,
    annual_revenue character varying(50),
    acv character varying(50),
    sales_cycle_length character varying(50),
    self_serve_pct character varying(50),
    signals text[],
    signal_details jsonb,
    job_titles text[],
    outbound_tools text[],
    outbound_tools_other text,
    crm character varying(100),
    lead_sources text[],
    customer_voice text,
    roi_results text,
    case_studies_description text,
    case_studies jsonb,
    tone_style character varying(50),
    messaging_notes text,
    primary_gtm_objective character varying(100),
    primary_gtm_objective_other text,
    success_metrics text[],
    success_definition text,
    timeline_urgency character varying(50),
    monthly_budget character varying(50),
    submission_status character varying(50) DEFAULT 'draft'::character varying,
    submitted_at timestamp with time zone,
    processed_at timestamp with time zone,
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone DEFAULT now(),
    industry character varying(100),
    competitors text[],
    key_differentiators text,
    common_objections text,
    buying_triggers_global text,
    monthly_volume character varying(50),
    current_open_rate character varying(20),
    current_reply_rate character varying(20),
    other_channels text,
    messages_worked text,
    approaches_failed text,
    industry_jargon text,
    engagement_win text,
    additional_context text,
    core_vendors text[],
    CONSTRAINT client_onboarding_submissions_submission_status_check CHECK (((submission_status)::text = ANY ((ARRAY['draft'::character varying, 'submitted'::character varying, 'processing'::character varying, 'completed'::character varying, 'archived'::character varying])::text[])))
);


--
-- Name: client_personas; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.client_personas (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    submission_id uuid NOT NULL,
    persona_order integer DEFAULT 0,
    job_title character varying(255) NOT NULL,
    primary_segment character varying(255),
    seniority_level character varying(50),
    pain_before_buying text,
    aha_moment text,
    objections text,
    decision_criteria text,
    created_at timestamp with time zone DEFAULT now()
);


--
-- Name: client_segments; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.client_segments (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    submission_id uuid NOT NULL,
    segment_order integer DEFAULT 0,
    segment_name character varying(255) NOT NULL,
    revenue_percentage integer,
    unique_characteristics text,
    pain_points text,
    buying_triggers text,
    created_at timestamp with time zone DEFAULT now()
);


--
-- Name: client_subscriptions; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.client_subscriptions (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    client_id uuid NOT NULL,
    package_template_id uuid,
    entra_packages integer DEFAULT 6 NOT NULL,
    entra_domains_per_package integer DEFAULT 2,
    entra_inboxes_per_domain integer DEFAULT 52,
    google_packages integer DEFAULT 5 NOT NULL,
    google_domains_per_package integer DEFAULT 5,
    google_inboxes_per_domain integer DEFAULT 3,
    spare_ratio numeric(3,2) DEFAULT 0.15,
    status character varying(20) DEFAULT 'active'::character varying,
    started_at timestamp without time zone DEFAULT now(),
    cancelled_at timestamp without time zone,
    notes text,
    created_at timestamp without time zone DEFAULT now(),
    updated_at timestamp without time zone DEFAULT now()
);


--
-- Name: clients; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.clients (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    name character varying(255) NOT NULL,
    context jsonb DEFAULT '{}'::jsonb,
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone DEFAULT now(),
    workspace_id uuid,
    logo_url text,
    onboarding_complete boolean DEFAULT false,
    onboarding_data jsonb,
    contact_name character varying(255),
    contact_email character varying(255),
    website character varying(255),
    industry character varying(100),
    domain_pattern character varying(255)
);


--
-- Name: companies; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.companies (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    client_id uuid NOT NULL,
    name character varying(255) NOT NULL,
    domain character varying(255) NOT NULL,
    normalized_domain character varying(255) NOT NULL,
    funding_stage character varying(50),
    funding_amount integer,
    funding_date date,
    investors jsonb DEFAULT '[]'::jsonb,
    employee_count integer,
    employee_range character varying(50),
    industry character varying(100),
    hq_country character varying(100),
    hq_city character varying(100),
    description text,
    tech_stack jsonb DEFAULT '[]'::jsonb,
    hiring_signals jsonb DEFAULT '[]'::jsonb,
    job_posting_count integer,
    domain_age_days integer,
    domain_created date,
    has_mx_records boolean,
    whois_registrar character varying(255),
    whois_privacy boolean DEFAULT false,
    domain_flags jsonb DEFAULT '[]'::jsonb,
    website_accessible boolean,
    website_content_summary text,
    detected_technologies jsonb DEFAULT '[]'::jsonb,
    icp_score integer,
    icp_tier character varying(1),
    tier_confidence integer,
    icp_match_reasons jsonb DEFAULT '[]'::jsonb,
    confidence_score integer DEFAULT 50,
    confidence_adjustments jsonb DEFAULT '[]'::jsonb,
    funding_validated boolean DEFAULT false,
    funding_sources jsonb DEFAULT '[]'::jsonb,
    research_summary text,
    sources jsonb DEFAULT '[]'::jsonb,
    layer integer DEFAULT 1,
    passed_to_layer_2 boolean DEFAULT false,
    passed_to_layer_3 boolean DEFAULT false,
    rejection_reason text,
    total_cost_usd numeric(10,4) DEFAULT 0,
    discovered_at timestamp with time zone DEFAULT now(),
    validated_at timestamp with time zone,
    last_enriched_at timestamp with time zone,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    lead_quality_score integer DEFAULT 0,
    lead_quality_breakdown jsonb DEFAULT '{}'::jsonb,
    red_flags jsonb DEFAULT '[]'::jsonb,
    email_provider text,
    is_b2b_email boolean,
    intent_score integer,
    hiring_velocity integer,
    intent_signals jsonb DEFAULT '[]'::jsonb,
    signals jsonb DEFAULT '[]'::jsonb,
    CONSTRAINT companies_confidence_score_check CHECK (((confidence_score >= 0) AND (confidence_score <= 100))),
    CONSTRAINT companies_icp_score_check CHECK (((icp_score >= 0) AND (icp_score <= 100))),
    CONSTRAINT companies_lead_quality_score_check CHECK (((lead_quality_score >= 0) AND (lead_quality_score <= 100))),
    CONSTRAINT companies_tier_confidence_check CHECK (((tier_confidence >= 0) AND (tier_confidence <= 100)))
);


--
-- Name: cost_logs; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.cost_logs (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    client_id uuid NOT NULL,
    flow_run_id uuid,
    task_name character varying(100),
    api_name character varying(50) NOT NULL,
    operation character varying(50) NOT NULL,
    cost_usd numeric(10,6) NOT NULL,
    input_units integer,
    company_id uuid,
    person_id uuid,
    "timestamp" timestamp with time zone DEFAULT now() NOT NULL,
    project_id uuid,
    service character varying(50)
);


--
-- Name: inbox_deletion_log; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.inbox_deletion_log (
    deletion_id uuid DEFAULT gen_random_uuid() NOT NULL,
    bison_sender_email_id text NOT NULL,
    email_address text NOT NULL,
    bison_workspace_id text NOT NULL,
    workspace_id uuid,
    workspace_name text NOT NULL,
    warmup_score numeric(5,2),
    warmup_emails_sent integer,
    warmup_replies_received integer,
    warmup_spam_saves integer,
    warmup_bounces_received integer,
    deletion_reason text DEFAULT 'low_warmup_score'::text NOT NULL,
    score_threshold_used integer DEFAULT 80 NOT NULL,
    min_emails_sent_threshold integer DEFAULT 8 NOT NULL,
    deleted_at timestamp with time zone DEFAULT now(),
    created_at timestamp with time zone DEFAULT now(),
    provider text,
    deletion_status text DEFAULT 'deleted'::text,
    campaign_protected boolean DEFAULT false,
    active_campaigns text[] DEFAULT ARRAY[]::text[],
    tagged_at timestamp with time zone,
    check_run_id uuid,
    CONSTRAINT inbox_deletion_log_deletion_status_check CHECK ((deletion_status = ANY (ARRAY['deleted'::text, 'tagged_for_removal'::text, 'deleted_after_tagging'::text]))),
    CONSTRAINT provider_valid_values CHECK ((provider = ANY (ARRAY['google'::text, 'azure'::text, 'other'::text])))
);


--
-- Name: daily_deletion_summary; Type: VIEW; Schema: public; Owner: -
--

CREATE VIEW public.daily_deletion_summary AS
 SELECT date(inbox_deletion_log.deleted_at) AS deletion_date,
    count(*) AS total_deleted,
    avg(inbox_deletion_log.warmup_score) AS avg_warmup_score,
    avg(inbox_deletion_log.warmup_emails_sent) AS avg_emails_sent,
    min(inbox_deletion_log.warmup_score) AS min_score,
    max(inbox_deletion_log.warmup_score) AS max_score
   FROM public.inbox_deletion_log
  WHERE (inbox_deletion_log.deleted_at >= (now() - '7 days'::interval))
  GROUP BY (date(inbox_deletion_log.deleted_at))
  ORDER BY (date(inbox_deletion_log.deleted_at)) DESC;


--
-- Name: database_migrations; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.database_migrations (
    id integer NOT NULL,
    migration_name character varying(255) NOT NULL,
    applied_at timestamp with time zone DEFAULT now(),
    description text
);


--
-- Name: database_migrations_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.database_migrations_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: database_migrations_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.database_migrations_id_seq OWNED BY public.database_migrations.id;


--
-- Name: document_email_variants; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.document_email_variants (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    document_id uuid NOT NULL,
    email_position integer NOT NULL,
    variant_number integer NOT NULL,
    variant_name character varying(255),
    is_recommended boolean DEFAULT false,
    subject_line text,
    email_body text NOT NULL,
    wait_days integer DEFAULT 0,
    thread_reply boolean DEFAULT false,
    word_count integer,
    them_us_ratio character varying(10),
    score integer,
    angle character varying(50),
    strategy text,
    value_prop character varying(50),
    edited_subject_line text,
    edited_email_body text,
    created_at timestamp without time zone DEFAULT now(),
    CONSTRAINT document_email_variants_email_position_check CHECK (((email_position >= 1) AND (email_position <= 4))),
    CONSTRAINT document_email_variants_score_check CHECK (((score >= 0) AND (score <= 100)))
);


--
-- Name: document_subject_options; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.document_subject_options (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    document_id uuid NOT NULL,
    email_position integer NOT NULL,
    subject_line text NOT NULL,
    rationale text,
    sort_order integer DEFAULT 0,
    CONSTRAINT document_subject_options_email_position_check CHECK (((email_position >= 1) AND (email_position <= 4)))
);


--
-- Name: domain_check_results; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.domain_check_results (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    run_id uuid,
    domain_id uuid,
    domain character varying(255) NOT NULL,
    checked_at timestamp with time zone DEFAULT now(),
    total_rbls_checked integer DEFAULT 314,
    listed_count integer DEFAULT 0,
    not_listed_count integer DEFAULT 0,
    error_count integer DEFAULT 0,
    health_score numeric(5,2),
    is_clean boolean,
    fcrdns_valid boolean,
    fcrdns_result jsonb,
    spf_valid boolean,
    spf_record text,
    dmarc_valid boolean,
    dmarc_policy text,
    mx_health_score numeric(5,2),
    mx_records jsonb,
    rbl_results jsonb,
    check_duration_seconds numeric(10,3),
    prefect_task_run_id character varying(255)
);


--
-- Name: domain_check_summary; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.domain_check_summary (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    domain_id uuid NOT NULL,
    check_timestamp timestamp with time zone NOT NULL,
    total_rbls_checked integer NOT NULL,
    blacklist_count integer DEFAULT 0 NOT NULL,
    whitelist_count integer DEFAULT 0 NOT NULL,
    health_score numeric(5,2) NOT NULL,
    is_clean boolean NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    total_blacklists_available integer,
    total_whitelists_available integer,
    blacklist_penalty numeric(5,2),
    whitelist_bonus numeric(5,2),
    total_query_time_ms integer,
    avg_query_time_ms integer,
    timeout_count integer DEFAULT 0,
    error_count integer DEFAULT 0,
    notes text,
    check_run_id uuid,
    tier integer,
    CONSTRAINT domain_check_summary_counts_positive CHECK (((total_rbls_checked >= 0) AND (blacklist_count >= 0) AND (whitelist_count >= 0))),
    CONSTRAINT domain_check_summary_health_range CHECK (((health_score >= (0)::numeric) AND (health_score <= (100)::numeric))),
    CONSTRAINT domain_check_summary_tier_check CHECK ((tier = ANY (ARRAY[1, 2, 3])))
);


--
-- Name: domain_generation_jobs; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.domain_generation_jobs (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    client_id uuid NOT NULL,
    count integer DEFAULT 10,
    status character varying(50) DEFAULT 'pending'::character varying,
    error_message text,
    created_at timestamp without time zone DEFAULT now(),
    started_at timestamp without time zone,
    completed_at timestamp without time zone
);


--
-- Name: domain_price_history; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.domain_price_history (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    domain_id uuid NOT NULL,
    porkbun_price numeric(10,2),
    porkbun_available boolean,
    dynadot_price numeric(10,2),
    dynadot_available boolean,
    best_price numeric(10,2),
    best_provider character varying(50),
    checked_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP
);


--
-- Name: domain_purchase_queue; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.domain_purchase_queue (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    domain_id uuid NOT NULL,
    provider character varying(20) NOT NULL,
    expected_price numeric(10,2) NOT NULL,
    status character varying(20) DEFAULT 'pending'::character varying,
    error_message text,
    created_at timestamp without time zone DEFAULT now(),
    processed_at timestamp without time zone,
    CONSTRAINT valid_provider CHECK (((provider)::text = ANY ((ARRAY['porkbun'::character varying, 'dynadot'::character varying])::text[])))
);


--
-- Name: domains; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.domains (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    workspace_id uuid NOT NULL,
    domain_name character varying(255) NOT NULL,
    sender_account_count integer DEFAULT 0 NOT NULL,
    is_active boolean DEFAULT true NOT NULL,
    first_seen_at timestamp with time zone DEFAULT now() NOT NULL,
    last_checked_at timestamp with time zone,
    next_check_at timestamp with time zone,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    latest_health_score numeric(5,2),
    latest_blacklist_count integer,
    latest_whitelist_count integer,
    is_clean boolean,
    notes text,
    domain_state public.domain_state DEFAULT 'live'::public.domain_state,
    provider character varying(100) DEFAULT 'unknown'::character varying,
    killed_at timestamp with time zone,
    kill_reason text,
    dead_inbox_count integer DEFAULT 0,
    live_inbox_count integer DEFAULT 0,
    health_percentage numeric(5,2) DEFAULT 100.00,
    domain_age_days integer,
    lifecycle_stage character varying(20),
    rotation_due_at timestamp with time zone,
    domain_bounce_rate_7d numeric(5,4),
    domain_complaint_count integer DEFAULT 0,
    approval_status character varying(20) DEFAULT 'pending'::character varying,
    reviewed_at timestamp without time zone,
    rationale text,
    legitimacy_score double precision,
    porkbun_price numeric(10,2),
    porkbun_available boolean,
    dynadot_price numeric(10,2),
    dynadot_available boolean,
    selected_provider character varying(20),
    job_id uuid,
    cached_price numeric(10,2),
    price_checked_at timestamp without time zone,
    purchased_at timestamp without time zone,
    nameservers_updated_at timestamp without time zone,
    nameserver_status character varying(20) DEFAULT 'pending'::character varying,
    nameserver_verified_at timestamp without time zone,
    current_nameservers text[],
    registration_date timestamp with time zone,
    available_for_setup_at timestamp with time zone,
    infrastructure_type character varying(20),
    infrastructure_set_at timestamp without time zone,
    last_price_check timestamp with time zone,
    purchase_job_id uuid,
    purchase_job_status text,
    CONSTRAINT domains_account_count_positive CHECK ((sender_account_count >= 0)),
    CONSTRAINT domains_health_score_range CHECK (((latest_health_score IS NULL) OR ((latest_health_score >= (0)::numeric) AND (latest_health_score <= (100)::numeric)))),
    CONSTRAINT domains_name_not_empty CHECK ((length(TRIM(BOTH FROM domain_name)) > 0))
);


--
-- Name: domains_backup_20251112; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.domains_backup_20251112 (
    id uuid,
    workspace_id uuid,
    domain_name character varying(255),
    sender_account_count integer,
    is_active boolean,
    first_seen_at timestamp with time zone,
    last_checked_at timestamp with time zone,
    next_check_at timestamp with time zone,
    created_at timestamp with time zone,
    updated_at timestamp with time zone,
    latest_health_score numeric(5,2),
    latest_blacklist_count integer,
    latest_whitelist_count integer,
    is_clean boolean,
    notes text
);


--
-- Name: emailbison_instances; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.emailbison_instances (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    instance_name character varying(255) NOT NULL,
    api_url text NOT NULL,
    api_key_encrypted text,
    is_active boolean DEFAULT true NOT NULL,
    last_sync_at timestamp with time zone,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    notes text,
    CONSTRAINT emailbison_instances_name_not_empty CHECK ((length(TRIM(BOTH FROM instance_name)) > 0)),
    CONSTRAINT emailbison_instances_url_not_empty CHECK ((length(TRIM(BOTH FROM api_url)) > 0))
);


--
-- Name: fathom_webhook_configs; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.fathom_webhook_configs (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    webhook_id character varying(100) NOT NULL,
    destination_url character varying(500) NOT NULL,
    webhook_secret text NOT NULL,
    include_transcript boolean DEFAULT true,
    include_summary boolean DEFAULT true,
    include_action_items boolean DEFAULT true,
    triggered_for jsonb DEFAULT '["my_recordings"]'::jsonb,
    is_active boolean DEFAULT true,
    created_at timestamp with time zone DEFAULT now()
);


--
-- Name: health_events; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.health_events (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    event_timestamp timestamp with time zone DEFAULT now() NOT NULL,
    event_type public.health_event_type NOT NULL,
    severity public.alert_severity DEFAULT 'medium'::public.alert_severity,
    entity_type character varying(20) NOT NULL,
    entity_id uuid NOT NULL,
    entity_name character varying(255),
    workspace_id uuid,
    trigger_type public.kill_trigger_type,
    details jsonb DEFAULT '{}'::jsonb,
    metrics_snapshot jsonb DEFAULT '{}'::jsonb,
    root_cause character varying(100),
    root_cause_category character varying(50),
    resolution_owner character varying(100),
    resolved_at timestamp with time zone,
    resolution_notes text,
    related_campaign_id uuid,
    related_segment_id uuid,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: icps; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.icps (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    client_id uuid NOT NULL,
    name character varying(255) NOT NULL,
    version integer DEFAULT 1 NOT NULL,
    is_active boolean DEFAULT false NOT NULL,
    company_criteria jsonb DEFAULT '{}'::jsonb NOT NULL,
    person_criteria jsonb DEFAULT '{}'::jsonb NOT NULL,
    weights jsonb DEFAULT '{}'::jsonb NOT NULL,
    tier_thresholds jsonb DEFAULT '{}'::jsonb NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: inbox_bounce_summary; Type: VIEW; Schema: public; Owner: -
--

CREATE VIEW public.inbox_bounce_summary AS
 SELECT sa.id AS sender_account_id,
    sa.email_address,
    sa.inbox_state,
    COALESCE(sum(
        CASE
            WHEN ((ce.event_timestamp > (now() - '24:00:00'::interval)) AND ((ce.event_data ->> 'bounce_type'::text) = 'hard'::text)) THEN 1
            ELSE 0
        END), (0)::bigint) AS hard_bounces_24h,
    COALESCE(sum(
        CASE
            WHEN ((ce.event_timestamp > (now() - '7 days'::interval)) AND ((ce.event_data ->> 'bounce_type'::text) = 'hard'::text)) THEN 1
            ELSE 0
        END), (0)::bigint) AS hard_bounces_7d,
    COALESCE(sum(
        CASE
            WHEN ((ce.event_timestamp > (now() - '7 days'::interval)) AND ((ce.event_data ->> 'bounce_type'::text) = 'soft'::text)) THEN 1
            ELSE 0
        END), (0)::bigint) AS soft_bounces_7d,
    COALESCE(sum(
        CASE
            WHEN (ce.event_timestamp > (now() - '7 days'::interval)) THEN 1
            ELSE 0
        END), (0)::bigint) AS total_bounces_7d,
    max(ce.event_timestamp) FILTER (WHERE (ce.event_type = 'bounce'::text)) AS last_bounce_at,
    now() AS computed_at
   FROM (public.sender_accounts sa
     LEFT JOIN public.campaign_events ce ON (((ce.sender_account_id = sa.id) AND (ce.event_type = 'bounce'::text))))
  WHERE ((sa.inbox_state = 'live'::public.inbox_state) OR (sa.inbox_state IS NULL))
  GROUP BY sa.id, sa.email_address, sa.inbox_state;


--
-- Name: inbox_health_snapshots; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.inbox_health_snapshots (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    inbox_id uuid NOT NULL,
    workspace_id uuid,
    snapshot_timestamp timestamp without time zone DEFAULT now(),
    health_score integer,
    hard_bounces_24h integer DEFAULT 0,
    hard_bounces_7d integer DEFAULT 0,
    total_sends_24h integer DEFAULT 0,
    total_sends_7d integer DEFAULT 0,
    bounce_rate_7d numeric(5,2) DEFAULT 0,
    inbox_placement_rate numeric(5,2),
    spam_placement_rate numeric(5,2),
    warmup_enabled boolean DEFAULT false,
    warmup_score integer,
    connection_status character varying(20),
    source character varying(20) DEFAULT 'emailbison'::character varying
);


--
-- Name: inbox_purchase_jobs; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.inbox_purchase_jobs (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    client_id uuid NOT NULL,
    workspace_id uuid,
    status character varying(50) DEFAULT 'pending'::character varying,
    current_step text,
    provider_type character varying(20),
    domain_ids uuid[],
    domain_names text[],
    entra_orders integer DEFAULT 0,
    google_orders integer DEFAULT 0,
    orders_completed integer DEFAULT 0,
    orders_total integer DEFAULT 0,
    total_inboxes integer DEFAULT 0,
    monthly_cost numeric(10,2),
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    started_at timestamp with time zone,
    completed_at timestamp with time zone,
    results jsonb,
    errors text[],
    request_data jsonb,
    override_age_check boolean DEFAULT false,
    custom_purchase boolean DEFAULT false,
    hypertide_email text,
    hypertide_password text,
    company_name text,
    forwarding_domain text,
    bison_username text,
    bison_password text,
    bison_workspace_name text,
    bison_url text DEFAULT 'https://spellcast.hirecharm.com'::text,
    sender_names jsonb,
    use_saved_payment boolean DEFAULT true,
    order_count integer DEFAULT 1,
    worker_mode character varying(20) DEFAULT 'api'::character varying,
    hypertide_order_id text,
    bison_api_key text,
    error_type text,
    checkout_url text
);


--
-- Name: inbox_removal_events; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.inbox_removal_events (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    sender_account_id uuid NOT NULL,
    workspace_id uuid NOT NULL,
    removal_reason text NOT NULL,
    kill_trigger text,
    health_score_at_removal numeric(5,2),
    removed_from_emailbison boolean DEFAULT false NOT NULL,
    emailbison_removal_at timestamp with time zone,
    emailbison_error text,
    requires_refund boolean DEFAULT false NOT NULL,
    refund_processed boolean DEFAULT false NOT NULL,
    refund_amount numeric(10,2),
    refund_notes text,
    tagged_at timestamp with time zone NOT NULL,
    removed_at timestamp with time zone,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    hard_bounces_24h integer,
    hard_bounces_7d integer,
    soft_bounces_7d integer,
    total_sends_7d integer,
    rbl_listings jsonb,
    CONSTRAINT inbox_removal_events_removal_reason_valid CHECK ((removal_reason = ANY (ARRAY['bounce_threshold'::text, 'rbl_critical'::text, 'warmup_failed'::text, 'provider_block'::text, 'spam_complaint'::text, 'manual'::text])))
);


--
-- Name: inbox_rotation_history; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.inbox_rotation_history (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    workspace_id uuid,
    rotation_type character varying(20) NOT NULL,
    source_inbox_id uuid,
    source_inbox_email character varying(255),
    source_pool character varying(20),
    target_inbox_id uuid,
    target_inbox_email character varying(255),
    target_pool character varying(20),
    reason text,
    triggered_by character varying(100),
    campaign_ids uuid[],
    executed_at timestamp without time zone DEFAULT now(),
    success boolean DEFAULT true,
    error_message text
);


--
-- Name: kill_trigger_events; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.kill_trigger_events (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    workspace_id uuid,
    inbox_id uuid,
    inbox_email character varying(255) NOT NULL,
    domain_id uuid,
    domain_name character varying(255),
    trigger_type character varying(50) NOT NULL,
    severity character varying(20) NOT NULL,
    value numeric(10,4) NOT NULL,
    threshold numeric(10,4) NOT NULL,
    detected_at timestamp without time zone DEFAULT now(),
    retest_at timestamp without time zone,
    resolved_at timestamp without time zone,
    action_taken character varying(20) DEFAULT 'pending'::character varying,
    resolved_by character varying(100),
    notes text,
    campaign_id uuid,
    campaign_name character varying(255),
    created_at timestamp without time zone DEFAULT now()
);


--
-- Name: kill_triggers; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.kill_triggers (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    entity_type character varying(20) NOT NULL,
    entity_id uuid NOT NULL,
    trigger_type public.kill_trigger_type NOT NULL,
    trigger_threshold text,
    actual_value text,
    fired_at timestamp with time zone DEFAULT now() NOT NULL,
    executed_at timestamp with time zone,
    execution_duration_ms integer,
    is_confirming boolean DEFAULT false,
    first_occurrence_at timestamp with time zone,
    confirmation_count integer DEFAULT 1,
    workspace_id uuid,
    source_campaign_id uuid,
    source_segment_id uuid,
    metrics_at_trigger jsonb DEFAULT '{}'::jsonb,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: layer_outputs; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.layer_outputs (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    project_id uuid NOT NULL,
    layer integer NOT NULL,
    batch_data jsonb NOT NULL,
    item_count integer NOT NULL,
    passed_count integer DEFAULT 0,
    agent_reasoning text,
    queries_used jsonb DEFAULT '[]'::jsonb,
    review_status character varying(50) DEFAULT 'pending'::character varying,
    reviewed_at timestamp with time zone,
    reviewed_by character varying(255),
    ai_grades jsonb DEFAULT '{}'::jsonb,
    cost_breakdown jsonb DEFAULT '{}'::jsonb,
    total_cost double precision DEFAULT 0.0,
    created_at timestamp with time zone DEFAULT now()
);


--
-- Name: leads; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.leads (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    project_id uuid NOT NULL,
    company_name character varying(255),
    company_domain character varying(255),
    company_description text,
    industry character varying(100),
    employee_count integer,
    funding_stage character varying(50),
    funding_amount character varying(50),
    person_name character varying(255),
    person_title character varying(255),
    person_email character varying(255),
    person_linkedin character varying(500),
    tier character varying(10),
    confidence_score double precision DEFAULT 0.0,
    relevance_score double precision DEFAULT 0.0,
    layer_1_data jsonb DEFAULT '{}'::jsonb,
    layer_2_data jsonb DEFAULT '{}'::jsonb,
    layer_3_data jsonb DEFAULT '{}'::jsonb,
    layer_4_data jsonb DEFAULT '{}'::jsonb,
    reasoning jsonb DEFAULT '{"key_concerns": [], "key_strengths": [], "signals_found": [], "open_questions": []}'::jsonb,
    -- embedding column removed (requires pgvector)
    current_layer integer DEFAULT 1,
    status character varying(50) DEFAULT 'processing'::character varying,
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone DEFAULT now()
);


--
-- Name: projects; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.projects (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    client_id uuid NOT NULL,
    name character varying(255) NOT NULL,
    icp_analysis jsonb NOT NULL,
    search_strategies jsonb DEFAULT '[]'::jsonb,
    status character varying(50) DEFAULT 'active'::character varying,
    target_leads integer DEFAULT 1000,
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone DEFAULT now()
);


--
-- Name: layer_progress; Type: VIEW; Schema: public; Owner: -
--

CREATE VIEW public.layer_progress AS
 SELECT p.id AS project_id,
    p.name AS project_name,
    l.current_layer,
    count(*) AS lead_count,
    avg(l.confidence_score) AS avg_confidence
   FROM (public.projects p
     JOIN public.leads l ON ((p.id = l.project_id)))
  GROUP BY p.id, p.name, l.current_layer
  ORDER BY p.id, l.current_layer;


--
-- Name: lead_pull_jobs; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.lead_pull_jobs (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    client_id uuid NOT NULL,
    suggestion_id uuid,
    submission_id uuid,
    volume integer DEFAULT 500 NOT NULL,
    channel character varying(50) DEFAULT 'email'::character varying,
    max_external_credits double precision DEFAULT 100.0,
    enable_external boolean DEFAULT true,
    search_criteria jsonb DEFAULT '{}'::jsonb NOT NULL,
    status character varying(50) DEFAULT 'pending'::character varying,
    error_message text,
    result_data jsonb,
    created_at timestamp without time zone DEFAULT now(),
    started_at timestamp without time zone,
    completed_at timestamp without time zone
);


--
-- Name: list_segments; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.list_segments (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    workspace_id uuid NOT NULL,
    segment_name character varying(255) NOT NULL,
    source character varying(100),
    segment_state public.segment_state DEFAULT 'active'::public.segment_state,
    quarantined_at timestamp with time zone,
    quarantine_reason text,
    purged_at timestamp with time zone,
    total_contacts integer DEFAULT 0,
    bounces_caused integer DEFAULT 0,
    last_bounce_at timestamp with time zone,
    hard_bounces_caused integer DEFAULT 0,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    notes text,
    external_segment_id text
);


--
-- Name: oauth_sessions; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.oauth_sessions (
    session_id uuid NOT NULL,
    first_name character varying(100),
    last_name character varying(100),
    email character varying(255),
    auto_share_team boolean,
    google_access_token text,
    google_refresh_token text,
    google_token_expiry timestamp with time zone,
    google_token_uri character varying(500),
    google_client_id character varying(500),
    google_client_secret text,
    google_scopes text,
    root_folder_id character varying(100),
    google_connected boolean,
    fathom_user_email character varying(255),
    fathom_access_token text,
    fathom_refresh_token text,
    fathom_token_expires_at timestamp with time zone,
    fathom_connected boolean,
    created_at timestamp with time zone,
    expires_at timestamp with time zone,
    completed boolean,
    fathom_oauth_state character varying(255)
);


--
-- Name: package_templates; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.package_templates (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    name character varying(100) NOT NULL,
    entra_packages integer DEFAULT 6 NOT NULL,
    entra_domains_per_package integer DEFAULT 2,
    entra_inboxes_per_domain integer DEFAULT 52,
    google_packages integer DEFAULT 5 NOT NULL,
    google_domains_per_package integer DEFAULT 5,
    google_inboxes_per_domain integer DEFAULT 3,
    total_domains integer GENERATED ALWAYS AS (((entra_packages * entra_domains_per_package) + (google_packages * google_domains_per_package))) STORED,
    total_inboxes integer GENERATED ALWAYS AS ((((entra_packages * entra_domains_per_package) * entra_inboxes_per_domain) + ((google_packages * google_domains_per_package) * google_inboxes_per_domain))) STORED,
    monthly_price numeric(10,2),
    is_active boolean DEFAULT true,
    created_at timestamp without time zone DEFAULT now()
);


--
-- Name: pending_refunds; Type: VIEW; Schema: public; Owner: -
--

CREATE VIEW public.pending_refunds AS
 SELECT ire.id,
    ire.removal_reason,
    ire.kill_trigger,
    sa.email_address,
    w.workspace_name,
    ire.tagged_at,
    ire.removed_at,
    ire.refund_amount,
    ire.refund_notes
   FROM ((public.inbox_removal_events ire
     JOIN public.sender_accounts sa ON ((sa.id = ire.sender_account_id)))
     JOIN public.workspaces w ON ((w.id = ire.workspace_id)))
  WHERE ((ire.requires_refund = true) AND (ire.refund_processed = false))
  ORDER BY ire.removed_at;


--
-- Name: persons; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.persons (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    company_id uuid NOT NULL,
    client_id uuid NOT NULL,
    full_name character varying(255) NOT NULL,
    first_name character varying(100),
    last_name character varying(100),
    name_confidence integer DEFAULT 80,
    title character varying(255) NOT NULL,
    normalized_title character varying(255),
    department character varying(100),
    seniority character varying(50),
    bio text,
    bio_summary text,
    social_links jsonb DEFAULT '[]'::jsonb,
    role_match jsonb,
    is_primary_contact boolean DEFAULT false,
    conferences jsonb DEFAULT '[]'::jsonb,
    is_conference_speaker boolean DEFAULT false,
    confidence_score integer DEFAULT 50,
    sources jsonb DEFAULT '[]'::jsonb,
    layer integer DEFAULT 3,
    passed_to_layer_4 boolean DEFAULT false,
    rejection_reason text,
    cost_usd numeric(10,4) DEFAULT 0,
    discovered_at timestamp with time zone DEFAULT now(),
    last_enriched_at timestamp with time zone,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    lead_quality_score integer DEFAULT 0,
    last_activity_date date,
    activity_recency_days integer,
    activity_signals jsonb DEFAULT '[]'::jsonb,
    email text,
    email_confidence integer DEFAULT 0,
    email_validated boolean DEFAULT false,
    enrichment_source text DEFAULT 'serper'::text,
    CONSTRAINT persons_confidence_score_check CHECK (((confidence_score >= 0) AND (confidence_score <= 100))),
    CONSTRAINT persons_lead_quality_score_check CHECK (((lead_quality_score >= 0) AND (lead_quality_score <= 100))),
    CONSTRAINT persons_name_confidence_check CHECK (((name_confidence >= 0) AND (name_confidence <= 100)))
);


--
-- Name: placement_tests; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.placement_tests (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    sender_account_id uuid NOT NULL,
    test_timestamp timestamp with time zone DEFAULT now() NOT NULL,
    seed_list_size integer NOT NULL,
    gmail_primary numeric(5,2),
    gmail_promotions numeric(5,2),
    gmail_spam numeric(5,2),
    microsoft_primary numeric(5,2),
    microsoft_other numeric(5,2),
    microsoft_spam numeric(5,2),
    yahoo_primary numeric(5,2),
    yahoo_spam numeric(5,2),
    overall_primary numeric(5,2),
    overall_spam numeric(5,2),
    overall_other numeric(5,2),
    is_passing boolean,
    failure_reason text,
    test_copy_used text,
    test_provider character varying(50),
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: predicted_emails; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.predicted_emails (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    person_id uuid NOT NULL,
    company_id uuid NOT NULL,
    client_id uuid NOT NULL,
    email character varying(255) NOT NULL,
    pattern_used character varying(50),
    domain_used character varying(255),
    confidence_score integer,
    confidence_factors jsonb,
    validation_tier character varying(20),
    estimated_deliverability numeric(5,4),
    validation_status character varying(20) DEFAULT 'pending'::character varying,
    validation_result character varying(20),
    validation_source character varying(50),
    validation_date timestamp with time zone,
    predicted_at timestamp with time zone DEFAULT now(),
    validated_at timestamp with time zone,
    CONSTRAINT predicted_emails_confidence_score_check CHECK (((confidence_score >= 0) AND (confidence_score <= 100)))
);


--
-- Name: project_dashboard; Type: VIEW; Schema: public; Owner: -
--

CREATE VIEW public.project_dashboard AS
 SELECT p.id AS project_id,
    p.name AS project_name,
    c.name AS client_name,
    p.status,
    p.target_leads,
    count(l.id) AS total_leads,
    count(l.id) FILTER (WHERE ((l.status)::text = 'final'::text)) AS final_leads,
    count(l.id) FILTER (WHERE ((l.tier)::text = 'S'::text)) AS tier_s_count,
    count(l.id) FILTER (WHERE ((l.tier)::text = 'A'::text)) AS tier_a_count,
    COALESCE(sum(cl.cost_usd), (0)::numeric) AS total_cost
   FROM (((public.projects p
     JOIN public.clients c ON ((p.client_id = c.id)))
     LEFT JOIN public.leads l ON ((p.id = l.project_id)))
     LEFT JOIN public.cost_logs cl ON ((p.id = cl.project_id)))
  GROUP BY p.id, p.name, c.name, p.status, p.target_leads;


--
-- Name: provider_deletion_summary; Type: VIEW; Schema: public; Owner: -
--

CREATE VIEW public.provider_deletion_summary AS
 SELECT inbox_deletion_log.provider,
    count(*) AS total_deleted,
    (avg(inbox_deletion_log.warmup_score))::numeric(5,2) AS avg_score,
    (avg(inbox_deletion_log.warmup_emails_sent))::numeric(5,2) AS avg_emails_sent,
    min(inbox_deletion_log.deleted_at) AS first_deletion,
    max(inbox_deletion_log.deleted_at) AS last_deletion
   FROM public.inbox_deletion_log
  WHERE (inbox_deletion_log.deleted_at >= (now() - '30 days'::interval))
  GROUP BY inbox_deletion_log.provider
  ORDER BY (count(*)) DESC;


--
-- Name: purchase_job_steps; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.purchase_job_steps (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    job_id uuid NOT NULL,
    step_name text NOT NULL,
    screenshot_base64 text,
    notes text,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP
);


--
-- Name: rbl_check_logs; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.rbl_check_logs (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    domain_id uuid NOT NULL,
    rbl_definition_id uuid NOT NULL,
    check_timestamp timestamp with time zone DEFAULT now() NOT NULL,
    is_listed boolean NOT NULL,
    response_code character varying(50),
    response_text text,
    query_time_ms integer,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    query_status character varying(50) DEFAULT 'success'::character varying,
    error_message text,
    check_run_id uuid,
    tier integer,
    CONSTRAINT rbl_check_logs_query_time_positive CHECK (((query_time_ms IS NULL) OR (query_time_ms >= 0))),
    CONSTRAINT rbl_check_logs_tier_check CHECK ((tier = ANY (ARRAY[1, 2, 3])))
)
PARTITION BY RANGE (check_timestamp);


--
-- Name: rbl_check_logs_2025_10; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.rbl_check_logs_2025_10 (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    domain_id uuid NOT NULL,
    rbl_definition_id uuid NOT NULL,
    check_timestamp timestamp with time zone DEFAULT now() NOT NULL,
    is_listed boolean NOT NULL,
    response_code character varying(50),
    response_text text,
    query_time_ms integer,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    query_status character varying(50) DEFAULT 'success'::character varying,
    error_message text,
    check_run_id uuid,
    tier integer,
    CONSTRAINT rbl_check_logs_query_time_positive CHECK (((query_time_ms IS NULL) OR (query_time_ms >= 0))),
    CONSTRAINT rbl_check_logs_tier_check CHECK ((tier = ANY (ARRAY[1, 2, 3])))
);


--
-- Name: rbl_check_logs_2025_11; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.rbl_check_logs_2025_11 (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    domain_id uuid NOT NULL,
    rbl_definition_id uuid NOT NULL,
    check_timestamp timestamp with time zone DEFAULT now() NOT NULL,
    is_listed boolean NOT NULL,
    response_code character varying(50),
    response_text text,
    query_time_ms integer,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    query_status character varying(50) DEFAULT 'success'::character varying,
    error_message text,
    check_run_id uuid,
    tier integer,
    CONSTRAINT rbl_check_logs_query_time_positive CHECK (((query_time_ms IS NULL) OR (query_time_ms >= 0))),
    CONSTRAINT rbl_check_logs_tier_check CHECK ((tier = ANY (ARRAY[1, 2, 3])))
);


--
-- Name: rbl_check_logs_2025_12; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.rbl_check_logs_2025_12 (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    domain_id uuid NOT NULL,
    rbl_definition_id uuid NOT NULL,
    check_timestamp timestamp with time zone DEFAULT now() NOT NULL,
    is_listed boolean NOT NULL,
    response_code character varying(50),
    response_text text,
    query_time_ms integer,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    query_status character varying(50) DEFAULT 'success'::character varying,
    error_message text,
    check_run_id uuid,
    tier integer,
    CONSTRAINT rbl_check_logs_query_time_positive CHECK (((query_time_ms IS NULL) OR (query_time_ms >= 0))),
    CONSTRAINT rbl_check_logs_tier_check CHECK ((tier = ANY (ARRAY[1, 2, 3])))
);


--
-- Name: rbl_check_logs_2026_01; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.rbl_check_logs_2026_01 (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    domain_id uuid NOT NULL,
    rbl_definition_id uuid NOT NULL,
    check_timestamp timestamp with time zone DEFAULT now() NOT NULL,
    is_listed boolean NOT NULL,
    response_code character varying(50),
    response_text text,
    query_time_ms integer,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    query_status character varying(50) DEFAULT 'success'::character varying,
    error_message text,
    check_run_id uuid,
    tier integer,
    CONSTRAINT rbl_check_logs_query_time_positive CHECK (((query_time_ms IS NULL) OR (query_time_ms >= 0))),
    CONSTRAINT rbl_check_logs_tier_check CHECK ((tier = ANY (ARRAY[1, 2, 3])))
);


--
-- Name: rbl_check_logs_2026_02; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.rbl_check_logs_2026_02 (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    domain_id uuid NOT NULL,
    rbl_definition_id uuid NOT NULL,
    check_timestamp timestamp with time zone DEFAULT now() NOT NULL,
    is_listed boolean NOT NULL,
    response_code character varying(50),
    response_text text,
    query_time_ms integer,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    query_status character varying(50) DEFAULT 'success'::character varying,
    error_message text,
    check_run_id uuid,
    tier integer,
    CONSTRAINT rbl_check_logs_query_time_positive CHECK (((query_time_ms IS NULL) OR (query_time_ms >= 0))),
    CONSTRAINT rbl_check_logs_tier_check CHECK ((tier = ANY (ARRAY[1, 2, 3])))
);


--
-- Name: rbl_check_logs_2026_03; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.rbl_check_logs_2026_03 (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    domain_id uuid NOT NULL,
    rbl_definition_id uuid NOT NULL,
    check_timestamp timestamp with time zone DEFAULT now() NOT NULL,
    is_listed boolean NOT NULL,
    response_code character varying(50),
    response_text text,
    query_time_ms integer,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    query_status character varying(50) DEFAULT 'success'::character varying,
    error_message text,
    check_run_id uuid,
    tier integer,
    CONSTRAINT rbl_check_logs_query_time_positive CHECK (((query_time_ms IS NULL) OR (query_time_ms >= 0))),
    CONSTRAINT rbl_check_logs_tier_check CHECK ((tier = ANY (ARRAY[1, 2, 3])))
);


--
-- Name: rbl_check_runs; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.rbl_check_runs (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    run_type character varying(50) DEFAULT 'scheduled'::character varying NOT NULL,
    total_ips_checked integer DEFAULT 0 NOT NULL,
    total_checks_performed integer DEFAULT 0 NOT NULL,
    started_at timestamp with time zone DEFAULT now() NOT NULL,
    completed_at timestamp with time zone,
    duration_seconds numeric(10,3),
    triggered_by character varying(100),
    status character varying(50) DEFAULT 'running'::character varying NOT NULL,
    error_message text,
    metadata jsonb,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    prefect_flow_run_id character varying(255),
    prefect_flow_name character varying(255),
    prefect_deployment_id character varying(255),
    run_name character varying(255),
    source character varying(50) DEFAULT 'manual'::character varying,
    total_domains_checked integer DEFAULT 0,
    domains_clean integer DEFAULT 0,
    domains_flagged integer DEFAULT 0,
    domains_requiring_review integer DEFAULT 0,
    average_health_score numeric(5,2),
    run_status character varying(50) DEFAULT 'running'::character varying,
    error_count integer DEFAULT 0,
    run_errors jsonb,
    tiers_checked text[],
    tier1_domains_checked integer DEFAULT 0,
    tier1_domains_passed integer DEFAULT 0,
    tier1_domains_failed integer DEFAULT 0,
    tier1_avg_health_score numeric(5,2),
    tier1_duration_seconds numeric(10,2),
    tier2_domains_checked integer DEFAULT 0,
    tier2_domains_passed integer DEFAULT 0,
    tier2_domains_failed integer DEFAULT 0,
    tier2_avg_health_score numeric(5,2),
    tier2_duration_seconds numeric(10,2),
    tier3_domains_checked integer DEFAULT 0,
    tier3_domains_passed integer DEFAULT 0,
    tier3_domains_failed integer DEFAULT 0,
    tier3_avg_health_score numeric(5,2),
    tier3_duration_seconds numeric(10,2),
    CONSTRAINT rbl_check_runs_run_type_check CHECK (((run_type)::text = ANY ((ARRAY['manual'::character varying, 'scheduled'::character varying, 'triggered'::character varying, 'bulk'::character varying, 'tiered_check'::character varying])::text[]))),
    CONSTRAINT rbl_check_runs_status_check CHECK (((status)::text = ANY ((ARRAY['running'::character varying, 'completed'::character varying, 'failed'::character varying, 'cancelled'::character varying])::text[])))
);


--
-- Name: rbl_definitions; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.rbl_definitions (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    rbl_name character varying(255) NOT NULL,
    rbl_zone character varying(255) NOT NULL,
    rbl_type character(1) NOT NULL,
    is_active boolean DEFAULT true NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    rbl_id character varying(50),
    category character varying(100),
    detail_url text,
    ipv4_support boolean DEFAULT true,
    ipv6_support boolean DEFAULT false,
    is_public boolean DEFAULT true,
    last_checked_at timestamp with time zone,
    consecutive_failures integer DEFAULT 0,
    total_queries integer DEFAULT 0,
    total_timeouts integer DEFAULT 0,
    avg_response_time_ms integer,
    notes text,
    tier integer DEFAULT 3,
    CONSTRAINT rbl_definitions_name_not_empty CHECK ((length(TRIM(BOTH FROM rbl_name)) > 0)),
    CONSTRAINT rbl_definitions_rbl_type_check CHECK ((rbl_type = ANY (ARRAY['b'::bpchar, 'w'::bpchar, 'i'::bpchar, 'c'::bpchar]))),
    CONSTRAINT rbl_definitions_tier_check CHECK ((tier = ANY (ARRAY[1, 2, 3]))),
    CONSTRAINT rbl_definitions_zone_not_empty CHECK ((length(TRIM(BOTH FROM rbl_zone)) > 0))
);


--
-- Name: recent_campaign_events; Type: VIEW; Schema: public; Owner: -
--

CREATE VIEW public.recent_campaign_events AS
 SELECT e.id,
    e.event_timestamp,
    e.event_type,
    c.campaign_name,
    c.emailbison_campaign_id,
    w.workspace_name,
    s.email_address AS sender_email,
    e.lead_email,
    e.lead_name,
    e.lead_company,
    e.event_data
   FROM (((public.campaign_events e
     JOIN public.emailbison_campaigns c ON ((e.campaign_id = c.id)))
     JOIN public.workspaces w ON ((c.workspace_id = w.id)))
     LEFT JOIN public.sender_accounts s ON ((e.sender_account_id = s.id)))
  WHERE (e.event_timestamp >= (now() - '7 days'::interval))
  ORDER BY e.event_timestamp DESC;


--
-- Name: recent_deletions; Type: VIEW; Schema: public; Owner: -
--

CREATE VIEW public.recent_deletions AS
 SELECT inbox_deletion_log.deletion_id,
    inbox_deletion_log.email_address,
    inbox_deletion_log.workspace_name,
    inbox_deletion_log.warmup_score,
    inbox_deletion_log.warmup_emails_sent,
    inbox_deletion_log.deletion_reason,
    inbox_deletion_log.deleted_at
   FROM public.inbox_deletion_log
  WHERE (inbox_deletion_log.deleted_at >= (now() - '30 days'::interval))
  ORDER BY inbox_deletion_log.deleted_at DESC;


--
-- Name: recent_inbox_removals; Type: VIEW; Schema: public; Owner: -
--

CREATE VIEW public.recent_inbox_removals AS
 SELECT ire.id,
    ire.removal_reason,
    ire.kill_trigger,
    sa.email_address,
    w.workspace_name,
    ire.tagged_at,
    ire.removed_at,
    ire.removed_from_emailbison,
    ire.requires_refund,
    ire.refund_processed,
    ire.hard_bounces_24h,
    ire.hard_bounces_7d
   FROM ((public.inbox_removal_events ire
     JOIN public.sender_accounts sa ON ((sa.id = ire.sender_account_id)))
     JOIN public.workspaces w ON ((w.id = ire.workspace_id)))
  WHERE (ire.removed_at >= (now() - '7 days'::interval))
  ORDER BY ire.removed_at DESC;


--
-- Name: reviews; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.reviews (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    layer_output_id uuid NOT NULL,
    claude_grade integer,
    claude_feedback text,
    gemini_grade integer,
    gemini_feedback text,
    decision character varying(50),
    human_feedback text,
    adjustments jsonb DEFAULT '{}'::jsonb,
    created_at timestamp with time zone DEFAULT now(),
    decided_at timestamp with time zone
);


--
-- Name: sender_accounts_backup_20251112; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.sender_accounts_backup_20251112 (
    id uuid,
    workspace_id uuid,
    email_address character varying(255),
    emailbison_account_id text,
    status character varying(50),
    health_score integer,
    is_active boolean,
    first_seen_at timestamp with time zone,
    last_seen_at timestamp with time zone,
    created_at timestamp with time zone,
    updated_at timestamp with time zone,
    display_name character varying(255),
    notes text,
    removal_tagged boolean,
    tagged_at timestamp with time zone
);


--
-- Name: sender_warmup_snapshots; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.sender_warmup_snapshots (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    sender_account_id uuid NOT NULL,
    snapshot_timestamp timestamp with time zone DEFAULT now() NOT NULL,
    period_start timestamp with time zone NOT NULL,
    period_end timestamp with time zone NOT NULL,
    warmup_enabled boolean DEFAULT false NOT NULL,
    warmup_score numeric(5,2),
    warmup_emails_sent integer DEFAULT 0 NOT NULL,
    warmup_replies_received integer DEFAULT 0 NOT NULL,
    warmup_bounces_received_count integer DEFAULT 0 NOT NULL,
    warmup_bounces_caused_count integer DEFAULT 0 NOT NULL,
    warmup_emails_saved_from_spam integer DEFAULT 0 NOT NULL,
    sender_email_status text,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT sender_warmup_snapshots_metrics_positive CHECK (((warmup_emails_sent >= 0) AND (warmup_replies_received >= 0) AND (warmup_bounces_received_count >= 0) AND (warmup_bounces_caused_count >= 0) AND (warmup_emails_saved_from_spam >= 0))),
    CONSTRAINT sender_warmup_snapshots_period_valid CHECK ((period_end > period_start)),
    CONSTRAINT sender_warmup_snapshots_score_range CHECK (((warmup_score IS NULL) OR ((warmup_score >= (0)::numeric) AND (warmup_score <= (100)::numeric))))
);


--
-- Name: spintax_processing_jobs; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.spintax_processing_jobs (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    sequence_id uuid NOT NULL,
    client_id uuid NOT NULL,
    status character varying(50) DEFAULT 'pending'::character varying,
    error_message text,
    created_at timestamp without time zone DEFAULT now(),
    started_at timestamp without time zone,
    completed_at timestamp without time zone
);


--
-- Name: strategies; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.strategies (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    client_id uuid NOT NULL,
    name character varying(255) NOT NULL,
    description text,
    status character varying(50) DEFAULT '''draft'''::character varying,
    emailbison_campaign_id character varying(255),
    created_at timestamp without time zone DEFAULT now(),
    updated_at timestamp without time zone DEFAULT now(),
    submission_id uuid
);


--
-- Name: strategy_generation_jobs; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.strategy_generation_jobs (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    client_id uuid NOT NULL,
    submission_id uuid,
    status character varying(50) DEFAULT 'pending'::character varying,
    generation_round integer DEFAULT 1,
    error_message text,
    created_at timestamp without time zone DEFAULT now(),
    started_at timestamp without time zone,
    completed_at timestamp without time zone,
    strategy_id uuid,
    revision_of uuid,
    job_type character varying(50) DEFAULT 'initial'::character varying,
    strategy_considerations jsonb
);


--
-- Name: strategy_revision_requests; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.strategy_revision_requests (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    job_id uuid NOT NULL,
    client_id uuid NOT NULL,
    variant_id uuid,
    instruction text NOT NULL,
    processed boolean DEFAULT false,
    created_at timestamp without time zone DEFAULT now()
);


--
-- Name: strategy_suggestions; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.strategy_suggestions (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    job_id uuid NOT NULL,
    client_id uuid NOT NULL,
    variant_number integer NOT NULL,
    subject_line text NOT NULL,
    email_body text NOT NULL,
    score integer,
    rationale text,
    used_variables jsonb,
    missing_variables jsonb,
    campaign_type character varying(50),
    status character varying(50) DEFAULT 'pending'::character varying,
    human_comment text,
    reviewed_by character varying(255),
    reviewed_at timestamp without time zone,
    generation_round integer DEFAULT 1,
    created_at timestamp without time zone DEFAULT now(),
    strategy_id uuid,
    edited_subject_line text,
    edited_email_body text,
    pushed_to_emailbison boolean DEFAULT false,
    pushed_at timestamp without time zone,
    original_suggestion_id uuid,
    sequence_data jsonb,
    value_prop_rotation jsonb,
    is_sequence boolean DEFAULT true NOT NULL,
    total_word_count integer,
    spintaxed_sequence_data jsonb,
    cycle_id uuid,
    campaign_version integer DEFAULT 1,
    previous_version_id uuid,
    lineage_id uuid,
    campaign_angle character varying(50),
    target_persona character varying(255),
    target_segment character varying(255),
    opener_pattern character varying(50),
    emailbison_campaign_id character varying(100),
    performance_metrics jsonb,
    last_performance_sync timestamp without time zone,
    is_active boolean DEFAULT true,
    document_id uuid,
    CONSTRAINT chk_is_sequence_true CHECK ((is_sequence = true))
);


--
-- Name: subscription_changes; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.subscription_changes (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    subscription_id uuid NOT NULL,
    change_type character varying(20) NOT NULL,
    previous_entra_packages integer,
    previous_google_packages integer,
    new_entra_packages integer,
    new_google_packages integer,
    reason text,
    changed_by character varying(100),
    created_at timestamp without time zone DEFAULT now()
);


--
-- Name: tagged_inboxes_pending_removal; Type: VIEW; Schema: public; Owner: -
--

CREATE VIEW public.tagged_inboxes_pending_removal AS
 SELECT sa.id AS sender_account_id,
    sa.email_address,
    sa.emailbison_account_id,
    sa.removal_tag,
    sa.removal_tagged_at,
    sa.hard_bounces_24h,
    sa.hard_bounces_7d,
    sa.soft_bounces_7d,
    sa.total_sends_7d,
    sa.inbox_state,
    w.id AS workspace_id,
    w.workspace_name,
    w.emailbison_workspace_id,
    w.automation_enabled
   FROM (public.sender_accounts sa
     JOIN public.workspaces w ON ((w.id = sa.workspace_id)))
  WHERE ((sa.removal_tag IS NOT NULL) AND (sa.inbox_state = 'live'::public.inbox_state) AND (w.automation_enabled = true))
  ORDER BY sa.removal_tagged_at;


--
-- Name: tier_check_summaries; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.tier_check_summaries (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    check_run_id uuid NOT NULL,
    tier integer NOT NULL,
    tier_name character varying(50) NOT NULL,
    rbls_in_tier integer NOT NULL,
    check_interval_hours integer NOT NULL,
    domains_checked integer DEFAULT 0 NOT NULL,
    domains_passed integer DEFAULT 0 NOT NULL,
    domains_failed integer DEFAULT 0 NOT NULL,
    domains_with_errors integer DEFAULT 0,
    avg_health_score numeric(5,2),
    min_health_score numeric(5,2),
    max_health_score numeric(5,2),
    total_blacklist_hits integer DEFAULT 0,
    total_whitelist_hits integer DEFAULT 0,
    domains_with_tier1_blacklists integer DEFAULT 0,
    domains_with_tier2_blacklists integer DEFAULT 0,
    domains_with_tier3_blacklists integer DEFAULT 0,
    total_dns_queries_performed integer,
    dns_queries_succeeded integer,
    dns_queries_failed integer,
    dns_query_success_rate numeric(5,2),
    started_at timestamp with time zone NOT NULL,
    completed_at timestamp with time zone,
    duration_seconds numeric(10,2),
    avg_time_per_domain_seconds numeric(10,2),
    metadata jsonb,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT tier_check_summaries_tier_check CHECK ((tier = ANY (ARRAY[1, 2, 3])))
);


--
-- Name: transcripts; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.transcripts (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    user_id uuid NOT NULL,
    recording_id bigint NOT NULL,
    meeting_title character varying(500),
    recording_start_time timestamp with time zone,
    recording_end_time timestamp with time zone,
    duration_minutes integer,
    fathom_url character varying(500),
    fathom_share_url character varying(500),
    drive_file_id character varying(100),
    drive_file_url character varying(500),
    drive_folder_id character varying(100),
    has_transcript boolean DEFAULT false,
    has_summary boolean DEFAULT false,
    has_action_items boolean DEFAULT false,
    processed_at timestamp with time zone DEFAULT now()
);


--
-- Name: users; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.users (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    first_name character varying(100) NOT NULL,
    last_name character varying(100) NOT NULL,
    email character varying(255) NOT NULL,
    department character varying(100),
    role character varying(100),
    fathom_user_email character varying(255),
    google_access_token text,
    google_refresh_token text,
    google_token_expiry timestamp with time zone,
    google_token_uri character varying(500),
    google_client_id character varying(500),
    google_client_secret text,
    google_scopes text,
    root_folder_id character varying(100),
    folder_structure character varying(50) DEFAULT 'monthly'::character varying,
    is_active boolean DEFAULT true,
    auto_share_team boolean DEFAULT true,
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone DEFAULT now(),
    last_login timestamp with time zone,
    fathom_access_token text,
    fathom_refresh_token text,
    fathom_token_expires_at timestamp with time zone,
    fathom_webhook_id text,
    fathom_webhook_secret text,
    has_fathom_oauth boolean DEFAULT false
);


--
-- Name: v_campaign_health; Type: VIEW; Schema: public; Owner: -
--

CREATE VIEW public.v_campaign_health AS
 SELECT c.id,
    c.campaign_name,
    c.campaign_state,
    c.workspace_id,
    w.workspace_name,
    c.total_sends,
    c.bounces,
    c.bounce_rate,
    c.complaints,
    c.inboxes_burned,
    c.inboxes_burned_7d,
    c.domains_affected,
    c.domains_burned_7d,
    c.copy_created_at,
    c.copy_age_days,
    c.quarantined_at,
    c.quarantine_reason,
    c.killed_at,
    c.kill_reason
   FROM (public.emailbison_campaigns c
     JOIN public.workspaces w ON ((c.workspace_id = w.id)));


--
-- Name: v_campaign_protected_deletions; Type: VIEW; Schema: public; Owner: -
--

CREATE VIEW public.v_campaign_protected_deletions AS
 SELECT inbox_deletion_log.deletion_id,
    inbox_deletion_log.bison_sender_email_id,
    inbox_deletion_log.email_address,
    inbox_deletion_log.workspace_name,
    inbox_deletion_log.deletion_status,
    inbox_deletion_log.campaign_protected,
    inbox_deletion_log.active_campaigns,
    inbox_deletion_log.warmup_score,
    inbox_deletion_log.warmup_emails_sent,
    inbox_deletion_log.tagged_at,
    inbox_deletion_log.deleted_at,
        CASE
            WHEN (inbox_deletion_log.deletion_status = 'tagged_for_removal'::text) THEN 'Tagged (awaiting campaign completion)'::text
            WHEN (inbox_deletion_log.deletion_status = 'deleted_after_tagging'::text) THEN 'Deleted after campaigns finished'::text
            ELSE 'Deleted immediately'::text
        END AS action_description
   FROM public.inbox_deletion_log
  WHERE (inbox_deletion_log.campaign_protected = true)
  ORDER BY COALESCE(inbox_deletion_log.tagged_at, inbox_deletion_log.deleted_at) DESC;


--
-- Name: v_domain_health; Type: VIEW; Schema: public; Owner: -
--

CREATE VIEW public.v_domain_health AS
 SELECT d.id,
    d.domain_name,
    d.domain_state,
    d.workspace_id,
    w.workspace_name,
    d.provider,
    d.live_inbox_count,
    d.dead_inbox_count,
    d.sender_account_count,
    d.health_percentage,
    d.lifecycle_stage,
    (EXTRACT(day FROM (now() - d.created_at)))::integer AS domain_age_days,
    d.rotation_due_at,
    d.domain_bounce_rate_7d,
    d.domain_complaint_count,
    d.killed_at,
    d.kill_reason,
    d.latest_health_score AS rbl_health_score,
    d.is_clean AS rbl_is_clean,
    d.last_checked_at AS rbl_last_checked_at
   FROM (public.domains d
     JOIN public.workspaces w ON ((d.workspace_id = w.id)))
  WHERE ((d.is_active = true) OR (d.domain_state = 'dead'::public.domain_state));


--
-- Name: v_domains_rotation_due; Type: VIEW; Schema: public; Owner: -
--

CREATE VIEW public.v_domains_rotation_due AS
 SELECT d.id,
    d.domain_name,
    d.workspace_id,
    w.workspace_name,
    (EXTRACT(day FROM (now() - d.created_at)))::integer AS domain_age_days,
    d.lifecycle_stage,
    d.rotation_due_at,
    (d.rotation_due_at - now()) AS days_until_rotation,
    d.live_inbox_count,
    d.dead_inbox_count
   FROM (public.domains d
     JOIN public.workspaces w ON ((d.workspace_id = w.id)))
  WHERE ((d.is_active = true) AND (d.domain_state <> 'dead'::public.domain_state) AND (((EXTRACT(day FROM (now() - d.created_at)))::integer >= 180) OR (d.rotation_due_at <= (now() + '30 days'::interval))))
  ORDER BY d.rotation_due_at;


--
-- Name: v_inbox_health; Type: VIEW; Schema: public; Owner: -
--

CREATE VIEW public.v_inbox_health AS
 SELECT sa.id,
    sa.email_address,
    sa.inbox_state,
    sa.role,
    sa.esp,
    sa.workspace_id,
    w.workspace_name,
    sa.domain_id,
    d.domain_name,
    d.domain_state,
    sa.hard_bounces_24h,
    sa.hard_bounces_7d,
    sa.soft_bounces_7d,
    sa.total_sends_7d,
    sa.complaints_lifetime,
    sa.consecutive_hard_bounces,
    sa.hard_bounce_rate_7d,
    sa.total_bounce_rate_7d,
    sa.last_placement_primary,
    sa.last_placement_spam,
    sa.flagged_for_retest,
    sa.retest_scheduled_at,
    (EXTRACT(day FROM (now() - COALESCE(sa.sending_started_at, sa.created_at))))::integer AS inbox_age_days,
    sa.warmup_started_at,
    sa.sending_started_at,
    sa.killed_at,
    sa.kill_reason
   FROM ((public.sender_accounts sa
     JOIN public.workspaces w ON ((sa.workspace_id = w.id)))
     LEFT JOIN public.domains d ON ((sa.domain_id = d.id)))
  WHERE ((sa.is_active = true) OR (sa.inbox_state = 'dead'::public.inbox_state));


--
-- Name: v_partition_statistics; Type: VIEW; Schema: public; Owner: -
--

CREATE VIEW public.v_partition_statistics AS
 SELECT pg_tables.schemaname,
    pg_tables.tablename AS partition_name,
    to_date("substring"((pg_tables.tablename)::text, '\d{4}_\d{2}$'::text), 'YYYY_MM'::text) AS partition_month,
    ( SELECT count(*) AS count
           FROM pg_class
          WHERE (pg_class.relname = pg_tables.tablename)) AS estimated_rows,
    pg_size_pretty(pg_total_relation_size(((((pg_tables.schemaname)::text || '.'::text) || (pg_tables.tablename)::text))::regclass)) AS total_size,
    pg_size_pretty(pg_relation_size(((((pg_tables.schemaname)::text || '.'::text) || (pg_tables.tablename)::text))::regclass)) AS table_size,
    pg_size_pretty(pg_indexes_size(((((pg_tables.schemaname)::text || '.'::text) || (pg_tables.tablename)::text))::regclass)) AS indexes_size,
    (((EXTRACT(year FROM age(now(), (to_date("substring"((pg_tables.tablename)::text, '\d{4}_\d{2}$'::text), 'YYYY_MM'::text))::timestamp with time zone)))::integer * 12) + (EXTRACT(month FROM age(now(), (to_date("substring"((pg_tables.tablename)::text, '\d{4}_\d{2}$'::text), 'YYYY_MM'::text))::timestamp with time zone)))::integer) AS age_months
   FROM pg_tables
  WHERE (((pg_tables.schemaname = 'public'::name) OR (pg_tables.schemaname = 'archive'::name)) AND (pg_tables.tablename ~~ 'rbl_check_logs_%'::text) AND (pg_tables.tablename ~ 'rbl_check_logs_\d{4}_\d{2}$'::text))
  ORDER BY (to_date("substring"((pg_tables.tablename)::text, '\d{4}_\d{2}$'::text), 'YYYY_MM'::text)) DESC;


--
-- Name: v_recent_kills; Type: VIEW; Schema: public; Owner: -
--

CREATE VIEW public.v_recent_kills AS
 SELECT kt.id,
    kt.entity_type,
    kt.entity_id,
    kt.trigger_type,
    kt.trigger_threshold,
    kt.actual_value,
    kt.fired_at,
    kt.is_confirming,
    kt.workspace_id,
    w.workspace_name,
    kt.metrics_at_trigger
   FROM (public.kill_triggers kt
     LEFT JOIN public.workspaces w ON ((kt.workspace_id = w.id)))
  ORDER BY kt.fired_at DESC
 LIMIT 100;


--
-- Name: vw_campaign_generation_context; Type: VIEW; Schema: public; Owner: -
--

CREATE VIEW public.vw_campaign_generation_context AS
 SELECT cos.id AS submission_id,
    c.id AS client_id,
    c.name AS client_name,
    cos.company_name,
    cos.core_product,
    cos.target_customer,
    cos.acv,
    cos.sales_cycle_length,
    cos.primary_gtm_objective,
    cos.signals,
    cos.job_titles,
    cos.customer_voice,
    cos.roi_results,
    cos.case_studies,
    cos.tone_style,
    cos.success_definition,
    ( SELECT COALESCE(jsonb_agg(jsonb_build_object('name', cs.segment_name, 'revenue_pct', cs.revenue_percentage, 'characteristics', cs.unique_characteristics, 'pain_points', cs.pain_points, 'buying_triggers', cs.buying_triggers) ORDER BY cs.segment_order), '[]'::jsonb) AS "coalesce"
           FROM public.client_segments cs
          WHERE (cs.submission_id = cos.id)) AS segments,
    ( SELECT COALESCE(jsonb_agg(jsonb_build_object('job_title', cp.job_title, 'segment', cp.primary_segment, 'seniority', cp.seniority_level, 'pain_before', cp.pain_before_buying, 'aha_moment', cp.aha_moment, 'objections', cp.objections) ORDER BY cp.persona_order), '[]'::jsonb) AS "coalesce"
           FROM public.client_personas cp
          WHERE (cp.submission_id = cos.id)) AS personas
   FROM (public.client_onboarding_submissions cos
     JOIN public.clients c ON ((cos.client_id = c.id)))
  WHERE ((cos.submission_status)::text = ANY ((ARRAY['submitted'::character varying, 'completed'::character varying])::text[]));


--
-- Name: vw_client_onboarding_summary; Type: VIEW; Schema: public; Owner: -
--

CREATE VIEW public.vw_client_onboarding_summary AS
 SELECT cos.id AS submission_id,
    cos.client_id,
    c.name AS client_name,
    cos.company_name,
    cos.website,
    cos.submission_status,
    cos.submission_version,
    cos.submitted_at,
    cos.primary_gtm_objective,
    cos.tone_style,
    cos.acv,
    cos.sales_cycle_length,
    COALESCE(seg_counts.segment_count, (0)::bigint) AS segment_count,
    COALESCE(persona_counts.persona_count, (0)::bigint) AS persona_count,
    COALESCE(array_length(cos.job_titles, 1), 0) AS job_title_count,
    COALESCE(array_length(cos.signals, 1), 0) AS signal_count,
    cos.created_at,
    cos.updated_at
   FROM (((public.client_onboarding_submissions cos
     JOIN public.clients c ON ((cos.client_id = c.id)))
     LEFT JOIN ( SELECT client_segments.submission_id,
            count(*) AS segment_count
           FROM public.client_segments
          GROUP BY client_segments.submission_id) seg_counts ON ((seg_counts.submission_id = cos.id)))
     LEFT JOIN ( SELECT client_personas.submission_id,
            count(*) AS persona_count
           FROM public.client_personas
          GROUP BY client_personas.submission_id) persona_counts ON ((persona_counts.submission_id = cos.id)))
  ORDER BY cos.submitted_at DESC NULLS LAST, cos.created_at DESC;


--
-- Name: vw_prefect_check_history; Type: VIEW; Schema: public; Owner: -
--

CREATE VIEW public.vw_prefect_check_history AS
SELECT
    NULL::uuid AS run_id,
    NULL::character varying(255) AS prefect_flow_run_id,
    NULL::character varying(255) AS prefect_flow_name,
    NULL::character varying(255) AS prefect_deployment_id,
    NULL::character varying(50) AS run_type,
    NULL::integer AS total_ips_checked,
    NULL::timestamp with time zone AS started_at,
    NULL::timestamp with time zone AS completed_at,
    NULL::character varying(50) AS status,
    NULL::numeric AS duration_minutes,
    NULL::bigint AS results_count,
    NULL::numeric AS avg_health_score,
    NULL::double precision AS clean_percentage;


--
-- Name: workspace_check_summary; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.workspace_check_summary (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    run_id uuid NOT NULL,
    workspace_id character varying(255),
    workspace_name character varying(255) NOT NULL,
    domains_checked integer DEFAULT 0,
    domains_clean integer DEFAULT 0,
    domains_flagged integer DEFAULT 0,
    domains_requiring_review integer DEFAULT 0,
    average_health_score numeric(5,2),
    error_count integer DEFAULT 0,
    errors jsonb,
    checked_at timestamp with time zone DEFAULT now()
);


--
-- Name: vw_recent_runs; Type: VIEW; Schema: public; Owner: -
--

CREATE VIEW public.vw_recent_runs AS
 SELECT r.id AS run_id,
    r.run_name,
    r.source,
    r.created_at,
    r.completed_at,
    r.run_status,
    r.total_domains_checked,
    r.domains_clean,
    r.domains_flagged,
    r.domains_requiring_review,
    r.average_health_score,
    r.error_count,
        CASE
            WHEN (r.completed_at IS NOT NULL) THEN EXTRACT(epoch FROM (r.completed_at - r.created_at))
            ELSE EXTRACT(epoch FROM (now() - r.created_at))
        END AS duration_seconds,
    ( SELECT json_agg(json_build_object('workspace_name', ws.workspace_name, 'domains_checked', ws.domains_checked, 'domains_flagged', ws.domains_flagged, 'error_count', ws.error_count)) AS json_agg
           FROM public.workspace_check_summary ws
          WHERE (ws.run_id = r.id)) AS workspace_breakdown
   FROM public.rbl_check_runs r
  ORDER BY r.created_at DESC
 LIMIT 50;


--
-- Name: vw_run_summary; Type: VIEW; Schema: public; Owner: -
--

CREATE VIEW public.vw_run_summary AS
 SELECT r.id AS run_id,
    r.run_name,
    r.source,
    r.created_at,
    r.completed_at,
    r.run_status,
    r.total_domains_checked,
    r.domains_clean,
    r.domains_flagged,
    r.domains_requiring_review,
        CASE
            WHEN (r.total_domains_checked > 0) THEN round((((r.domains_clean)::numeric / (r.total_domains_checked)::numeric) * (100)::numeric), 2)
            ELSE (0)::numeric
        END AS clean_percentage,
        CASE
            WHEN (r.total_domains_checked > 0) THEN round((((r.domains_flagged)::numeric / (r.total_domains_checked)::numeric) * (100)::numeric), 2)
            ELSE (0)::numeric
        END AS flagged_percentage,
        CASE
            WHEN (r.total_domains_checked > 0) THEN round((((r.domains_requiring_review)::numeric / (r.total_domains_checked)::numeric) * (100)::numeric), 2)
            ELSE (0)::numeric
        END AS review_percentage,
    r.average_health_score,
    r.error_count,
        CASE
            WHEN (r.completed_at IS NOT NULL) THEN EXTRACT(epoch FROM (r.completed_at - r.created_at))
            ELSE NULL::numeric
        END AS duration_seconds,
    r.prefect_flow_run_id,
    r.prefect_flow_name
   FROM public.rbl_check_runs r
  ORDER BY r.created_at DESC;


--
-- Name: warmup_check_runs; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.warmup_check_runs (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    run_name character varying(255) NOT NULL,
    source character varying(50) DEFAULT 'prefect'::character varying,
    prefect_flow_run_id character varying(255),
    prefect_flow_name character varying(255) DEFAULT 'warmup-cleanup-multi-workspace'::character varying,
    started_at timestamp with time zone DEFAULT now() NOT NULL,
    completed_at timestamp with time zone,
    duration_seconds integer,
    run_status character varying(50) DEFAULT 'running'::character varying NOT NULL,
    total_inboxes_scanned integer DEFAULT 0,
    total_inboxes_processed integer DEFAULT 0,
    total_inboxes_flagged integer DEFAULT 0,
    total_inboxes_tagged integer DEFAULT 0,
    total_tagging_failed integer DEFAULT 0,
    warmup_score_threshold integer NOT NULL,
    min_emails_sent_threshold integer NOT NULL,
    campaign_tracking_enabled boolean DEFAULT false,
    total_in_active_campaigns integer DEFAULT 0,
    error_count integer DEFAULT 0,
    run_errors jsonb,
    dry_run boolean DEFAULT false,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT warmup_check_runs_source_check CHECK (((source)::text = ANY ((ARRAY['prefect'::character varying, 'manual'::character varying, 'api'::character varying])::text[]))),
    CONSTRAINT warmup_check_runs_status_check CHECK (((run_status)::text = ANY ((ARRAY['running'::character varying, 'completed'::character varying, 'failed'::character varying, 'partial'::character varying])::text[])))
);


--
-- Name: vw_warmup_check_runs_summary; Type: VIEW; Schema: public; Owner: -
--

CREATE VIEW public.vw_warmup_check_runs_summary AS
 SELECT wcr.id AS run_id,
    wcr.run_name,
    wcr.source,
    wcr.started_at,
    wcr.completed_at,
    wcr.run_status,
    wcr.duration_seconds,
    wcr.total_inboxes_scanned,
    wcr.total_inboxes_processed,
    wcr.total_inboxes_flagged,
    wcr.total_inboxes_tagged,
    wcr.total_tagging_failed,
        CASE
            WHEN (wcr.total_inboxes_flagged > 0) THEN round((((wcr.total_inboxes_tagged)::numeric / (wcr.total_inboxes_flagged)::numeric) * (100)::numeric), 2)
            ELSE 100.0
        END AS tagging_success_rate,
        CASE
            WHEN (wcr.total_inboxes_scanned > 0) THEN round((((wcr.total_inboxes_processed)::numeric / (wcr.total_inboxes_scanned)::numeric) * (100)::numeric), 2)
            ELSE 0.0
        END AS processing_success_rate,
        CASE
            WHEN (wcr.total_inboxes_scanned > 0) THEN round((((wcr.total_inboxes_flagged)::numeric / (wcr.total_inboxes_scanned)::numeric) * (100)::numeric), 2)
            ELSE 0.0
        END AS flagged_rate,
    wcr.warmup_score_threshold,
    wcr.min_emails_sent_threshold,
    wcr.campaign_tracking_enabled,
    wcr.total_in_active_campaigns,
    wcr.dry_run,
    wcr.error_count,
    wcr.prefect_flow_run_id,
    wcr.prefect_flow_name,
        CASE
            WHEN (wcr.completed_at IS NOT NULL) THEN (EXTRACT(epoch FROM (now() - wcr.completed_at)))::integer
            ELSE NULL::integer
        END AS seconds_since_completion
   FROM public.warmup_check_runs wcr
  ORDER BY wcr.started_at DESC;


--
-- Name: vw_workspace_health; Type: VIEW; Schema: public; Owner: -
--

CREATE VIEW public.vw_workspace_health AS
 SELECT ws.workspace_name,
    ws.workspace_id,
    count(DISTINCT ws.run_id) AS total_runs,
    sum(ws.domains_checked) AS total_domains_checked,
    sum(ws.domains_clean) AS total_domains_clean,
    sum(ws.domains_flagged) AS total_domains_flagged,
    sum(ws.domains_requiring_review) AS total_domains_requiring_review,
    round(avg(ws.average_health_score), 2) AS overall_average_health_score,
    sum(ws.error_count) AS total_errors,
    count(*) FILTER (WHERE (ws.error_count > 0)) AS runs_with_errors,
    max(ws.checked_at) AS last_checked_at,
        CASE
            WHEN (sum(ws.domains_checked) > 0) THEN round((((sum(ws.domains_clean))::numeric / (sum(ws.domains_checked))::numeric) * (100)::numeric), 2)
            ELSE (0)::numeric
        END AS clean_rate_percentage
   FROM public.workspace_check_summary ws
  GROUP BY ws.workspace_name, ws.workspace_id
  ORDER BY (sum(ws.error_count)) DESC, (round(avg(ws.average_health_score), 2));


--
-- Name: vw_workspaces_with_errors; Type: VIEW; Schema: public; Owner: -
--

CREATE VIEW public.vw_workspaces_with_errors AS
 SELECT ws.workspace_name,
    ws.workspace_id,
    r.run_name,
    r.created_at AS run_created_at,
    ws.error_count,
    ws.errors AS error_details,
    ws.domains_checked,
    ws.domains_flagged,
    ws.average_health_score,
        CASE
            WHEN (ws.error_count >= 10) THEN 'Critical'::text
            WHEN (ws.error_count >= 5) THEN 'High'::text
            WHEN (ws.error_count >= 1) THEN 'Medium'::text
            ELSE 'Low'::text
        END AS error_severity
   FROM (public.workspace_check_summary ws
     JOIN public.rbl_check_runs r ON ((ws.run_id = r.id)))
  WHERE (ws.error_count > 0)
  ORDER BY ws.error_count DESC, r.created_at DESC;


--
-- Name: warmup_health_summary; Type: VIEW; Schema: public; Owner: -
--

CREATE VIEW public.warmup_health_summary AS
 SELECT DISTINCT ON (s.email_address) s.id AS sender_account_id,
    s.email_address,
    w.workspace_name,
    ws.warmup_enabled,
    ws.warmup_score,
    ws.warmup_emails_sent,
    ws.warmup_replies_received,
    ws.warmup_bounces_received_count,
    ws.sender_email_status,
    ws.snapshot_timestamp AS last_snapshot_at
   FROM ((public.sender_warmup_snapshots ws
     JOIN public.sender_accounts s ON ((ws.sender_account_id = s.id)))
     JOIN public.workspaces w ON ((s.workspace_id = w.id)))
  ORDER BY s.email_address, ws.snapshot_timestamp DESC;


--
-- Name: webhook_logs; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.webhook_logs (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    user_id uuid,
    recording_id bigint NOT NULL,
    webhook_received_at timestamp with time zone DEFAULT now(),
    signature_valid boolean NOT NULL,
    raw_payload jsonb,
    status public.processing_status DEFAULT 'pending'::public.processing_status,
    error_message text,
    retry_count integer DEFAULT 0,
    processed_at timestamp with time zone
);


--
-- Name: workspace_deletion_summary; Type: VIEW; Schema: public; Owner: -
--

CREATE VIEW public.workspace_deletion_summary AS
 SELECT inbox_deletion_log.workspace_name,
    inbox_deletion_log.bison_workspace_id,
    count(*) AS total_deleted,
    (avg(inbox_deletion_log.warmup_score))::numeric(5,2) AS avg_score,
    count(
        CASE
            WHEN (inbox_deletion_log.provider = 'google'::text) THEN 1
            ELSE NULL::integer
        END) AS google_count,
    count(
        CASE
            WHEN (inbox_deletion_log.provider = 'azure'::text) THEN 1
            ELSE NULL::integer
        END) AS azure_count,
    count(
        CASE
            WHEN (inbox_deletion_log.provider = 'other'::text) THEN 1
            ELSE NULL::integer
        END) AS other_count,
    min(inbox_deletion_log.deleted_at) AS first_deletion,
    max(inbox_deletion_log.deleted_at) AS last_deletion
   FROM public.inbox_deletion_log
  WHERE (inbox_deletion_log.deleted_at >= (now() - '30 days'::interval))
  GROUP BY inbox_deletion_log.workspace_name, inbox_deletion_log.bison_workspace_id
  ORDER BY (count(*)) DESC;


--
-- Name: workspaces_compat; Type: VIEW; Schema: public; Owner: -
--

CREATE VIEW public.workspaces_compat AS
 SELECT workspaces.id AS workspace_id,
    workspaces.emailbison_workspace_id AS bison_workspace_id,
    workspaces.workspace_name,
    workspaces.workspace_name AS client_name,
    workspaces.is_active,
    workspaces.last_sync_at,
    workspaces.created_at,
    workspaces.updated_at
   FROM public.workspaces;


--
-- Name: rbl_check_logs_2025_10; Type: TABLE ATTACH; Schema: public; Owner: -
--

ALTER TABLE ONLY public.rbl_check_logs ATTACH PARTITION public.rbl_check_logs_2025_10 FOR VALUES FROM ('2025-10-01 00:00:00+00') TO ('2025-11-01 00:00:00+00');


--
-- Name: rbl_check_logs_2025_11; Type: TABLE ATTACH; Schema: public; Owner: -
--

ALTER TABLE ONLY public.rbl_check_logs ATTACH PARTITION public.rbl_check_logs_2025_11 FOR VALUES FROM ('2025-11-01 00:00:00+00') TO ('2025-12-01 00:00:00+00');


--
-- Name: rbl_check_logs_2025_12; Type: TABLE ATTACH; Schema: public; Owner: -
--

ALTER TABLE ONLY public.rbl_check_logs ATTACH PARTITION public.rbl_check_logs_2025_12 FOR VALUES FROM ('2025-12-01 00:00:00+00') TO ('2026-01-01 00:00:00+00');


--
-- Name: rbl_check_logs_2026_01; Type: TABLE ATTACH; Schema: public; Owner: -
--

ALTER TABLE ONLY public.rbl_check_logs ATTACH PARTITION public.rbl_check_logs_2026_01 FOR VALUES FROM ('2026-01-01 00:00:00+00') TO ('2026-02-01 00:00:00+00');


--
-- Name: rbl_check_logs_2026_02; Type: TABLE ATTACH; Schema: public; Owner: -
--

ALTER TABLE ONLY public.rbl_check_logs ATTACH PARTITION public.rbl_check_logs_2026_02 FOR VALUES FROM ('2026-02-01 00:00:00+00') TO ('2026-03-01 00:00:00+00');


--
-- Name: rbl_check_logs_2026_03; Type: TABLE ATTACH; Schema: public; Owner: -
--

ALTER TABLE ONLY public.rbl_check_logs ATTACH PARTITION public.rbl_check_logs_2026_03 FOR VALUES FROM ('2026-03-01 00:00:00+00') TO ('2026-04-01 00:00:00+00');


--
-- Name: database_migrations id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.database_migrations ALTER COLUMN id SET DEFAULT nextval('public.database_migrations_id_seq'::regclass);


--
-- Name: _migrations _migrations_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public._migrations
    ADD CONSTRAINT _migrations_pkey PRIMARY KEY (name);


--
-- Name: campaign_cycles campaign_cycles_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.campaign_cycles
    ADD CONSTRAINT campaign_cycles_pkey PRIMARY KEY (id);


--
-- Name: campaign_documents campaign_documents_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.campaign_documents
    ADD CONSTRAINT campaign_documents_pkey PRIMARY KEY (id);


--
-- Name: campaign_events campaign_events_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.campaign_events
    ADD CONSTRAINT campaign_events_pkey PRIMARY KEY (id);


--
-- Name: campaign_inboxes campaign_inboxes_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.campaign_inboxes
    ADD CONSTRAINT campaign_inboxes_pkey PRIMARY KEY (id);


--
-- Name: campaign_snapshots campaign_snapshots_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.campaign_snapshots
    ADD CONSTRAINT campaign_snapshots_pkey PRIMARY KEY (id);


--
-- Name: campaign_snapshots campaign_snapshots_unique_snapshot; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.campaign_snapshots
    ADD CONSTRAINT campaign_snapshots_unique_snapshot UNIQUE (campaign_id, snapshot_timestamp);


--
-- Name: client_onboarding_submissions client_onboarding_submissions_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.client_onboarding_submissions
    ADD CONSTRAINT client_onboarding_submissions_pkey PRIMARY KEY (id);


--
-- Name: client_personas client_personas_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.client_personas
    ADD CONSTRAINT client_personas_pkey PRIMARY KEY (id);


--
-- Name: client_segments client_segments_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.client_segments
    ADD CONSTRAINT client_segments_pkey PRIMARY KEY (id);


--
-- Name: client_subscriptions client_subscriptions_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.client_subscriptions
    ADD CONSTRAINT client_subscriptions_pkey PRIMARY KEY (id);


--
-- Name: clients clients_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.clients
    ADD CONSTRAINT clients_pkey PRIMARY KEY (id);


--
-- Name: companies companies_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.companies
    ADD CONSTRAINT companies_pkey PRIMARY KEY (id);


--
-- Name: cost_logs cost_logs_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.cost_logs
    ADD CONSTRAINT cost_logs_pkey PRIMARY KEY (id);


--
-- Name: database_migrations database_migrations_migration_name_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.database_migrations
    ADD CONSTRAINT database_migrations_migration_name_key UNIQUE (migration_name);


--
-- Name: database_migrations database_migrations_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.database_migrations
    ADD CONSTRAINT database_migrations_pkey PRIMARY KEY (id);


--
-- Name: document_email_variants document_email_variants_document_id_email_position_variant__key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.document_email_variants
    ADD CONSTRAINT document_email_variants_document_id_email_position_variant__key UNIQUE (document_id, email_position, variant_number);


--
-- Name: document_email_variants document_email_variants_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.document_email_variants
    ADD CONSTRAINT document_email_variants_pkey PRIMARY KEY (id);


--
-- Name: document_subject_options document_subject_options_document_id_email_position_subject_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.document_subject_options
    ADD CONSTRAINT document_subject_options_document_id_email_position_subject_key UNIQUE (document_id, email_position, subject_line);


--
-- Name: document_subject_options document_subject_options_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.document_subject_options
    ADD CONSTRAINT document_subject_options_pkey PRIMARY KEY (id);


--
-- Name: domain_check_results domain_check_results_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.domain_check_results
    ADD CONSTRAINT domain_check_results_pkey PRIMARY KEY (id);


--
-- Name: domain_check_summary domain_check_summary_domain_tier_run_unique; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.domain_check_summary
    ADD CONSTRAINT domain_check_summary_domain_tier_run_unique UNIQUE NULLS NOT DISTINCT (domain_id, check_run_id, tier);


--
-- Name: domain_check_summary domain_check_summary_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.domain_check_summary
    ADD CONSTRAINT domain_check_summary_pkey PRIMARY KEY (id);


--
-- Name: domain_generation_jobs domain_generation_jobs_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.domain_generation_jobs
    ADD CONSTRAINT domain_generation_jobs_pkey PRIMARY KEY (id);


--
-- Name: domain_price_history domain_price_history_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.domain_price_history
    ADD CONSTRAINT domain_price_history_pkey PRIMARY KEY (id);


--
-- Name: domain_purchase_queue domain_purchase_queue_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.domain_purchase_queue
    ADD CONSTRAINT domain_purchase_queue_pkey PRIMARY KEY (id);


--
-- Name: domains domains_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.domains
    ADD CONSTRAINT domains_pkey PRIMARY KEY (id);


--
-- Name: domains domains_unique_per_workspace; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.domains
    ADD CONSTRAINT domains_unique_per_workspace UNIQUE (workspace_id, domain_name);


--
-- Name: emailbison_campaigns emailbison_campaigns_emailbison_campaign_id_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.emailbison_campaigns
    ADD CONSTRAINT emailbison_campaigns_emailbison_campaign_id_key UNIQUE (emailbison_campaign_id);


--
-- Name: emailbison_campaigns emailbison_campaigns_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.emailbison_campaigns
    ADD CONSTRAINT emailbison_campaigns_pkey PRIMARY KEY (id);


--
-- Name: emailbison_instances emailbison_instances_instance_name_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.emailbison_instances
    ADD CONSTRAINT emailbison_instances_instance_name_key UNIQUE (instance_name);


--
-- Name: emailbison_instances emailbison_instances_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.emailbison_instances
    ADD CONSTRAINT emailbison_instances_pkey PRIMARY KEY (id);


--
-- Name: fathom_webhook_configs fathom_webhook_configs_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.fathom_webhook_configs
    ADD CONSTRAINT fathom_webhook_configs_pkey PRIMARY KEY (id);


--
-- Name: fathom_webhook_configs fathom_webhook_configs_webhook_id_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.fathom_webhook_configs
    ADD CONSTRAINT fathom_webhook_configs_webhook_id_key UNIQUE (webhook_id);


--
-- Name: health_events health_events_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.health_events
    ADD CONSTRAINT health_events_pkey PRIMARY KEY (id);


--
-- Name: icps icps_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.icps
    ADD CONSTRAINT icps_pkey PRIMARY KEY (id);


--
-- Name: inbox_deletion_log inbox_deletion_log_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.inbox_deletion_log
    ADD CONSTRAINT inbox_deletion_log_pkey PRIMARY KEY (deletion_id);


--
-- Name: inbox_health_snapshots inbox_health_snapshots_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.inbox_health_snapshots
    ADD CONSTRAINT inbox_health_snapshots_pkey PRIMARY KEY (id);


--
-- Name: inbox_purchase_jobs inbox_purchase_jobs_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.inbox_purchase_jobs
    ADD CONSTRAINT inbox_purchase_jobs_pkey PRIMARY KEY (id);


--
-- Name: inbox_removal_events inbox_removal_events_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.inbox_removal_events
    ADD CONSTRAINT inbox_removal_events_pkey PRIMARY KEY (id);


--
-- Name: inbox_rotation_history inbox_rotation_history_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.inbox_rotation_history
    ADD CONSTRAINT inbox_rotation_history_pkey PRIMARY KEY (id);


--
-- Name: kill_trigger_events kill_trigger_events_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.kill_trigger_events
    ADD CONSTRAINT kill_trigger_events_pkey PRIMARY KEY (id);


--
-- Name: kill_triggers kill_triggers_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.kill_triggers
    ADD CONSTRAINT kill_triggers_pkey PRIMARY KEY (id);


--
-- Name: layer_outputs layer_outputs_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.layer_outputs
    ADD CONSTRAINT layer_outputs_pkey PRIMARY KEY (id);


--
-- Name: lead_pull_jobs lead_pull_jobs_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.lead_pull_jobs
    ADD CONSTRAINT lead_pull_jobs_pkey PRIMARY KEY (id);


--
-- Name: leads leads_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.leads
    ADD CONSTRAINT leads_pkey PRIMARY KEY (id);


--
-- Name: list_segments list_segments_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.list_segments
    ADD CONSTRAINT list_segments_pkey PRIMARY KEY (id);


--
-- Name: list_segments list_segments_unique_name; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.list_segments
    ADD CONSTRAINT list_segments_unique_name UNIQUE (workspace_id, segment_name);


--
-- Name: oauth_sessions oauth_sessions_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.oauth_sessions
    ADD CONSTRAINT oauth_sessions_pkey PRIMARY KEY (session_id);


--
-- Name: package_templates package_templates_name_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.package_templates
    ADD CONSTRAINT package_templates_name_key UNIQUE (name);


--
-- Name: package_templates package_templates_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.package_templates
    ADD CONSTRAINT package_templates_pkey PRIMARY KEY (id);


--
-- Name: persons persons_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.persons
    ADD CONSTRAINT persons_pkey PRIMARY KEY (id);


--
-- Name: placement_tests placement_tests_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.placement_tests
    ADD CONSTRAINT placement_tests_pkey PRIMARY KEY (id);


--
-- Name: predicted_emails predicted_emails_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.predicted_emails
    ADD CONSTRAINT predicted_emails_pkey PRIMARY KEY (id);


--
-- Name: projects projects_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.projects
    ADD CONSTRAINT projects_pkey PRIMARY KEY (id);


--
-- Name: purchase_job_steps purchase_job_steps_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.purchase_job_steps
    ADD CONSTRAINT purchase_job_steps_pkey PRIMARY KEY (id);


--
-- Name: rbl_check_logs rbl_check_logs_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.rbl_check_logs
    ADD CONSTRAINT rbl_check_logs_pkey PRIMARY KEY (id, check_timestamp);


--
-- Name: rbl_check_logs_2025_10 rbl_check_logs_2025_10_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.rbl_check_logs_2025_10
    ADD CONSTRAINT rbl_check_logs_2025_10_pkey PRIMARY KEY (id, check_timestamp);


--
-- Name: rbl_check_logs_2025_11 rbl_check_logs_2025_11_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.rbl_check_logs_2025_11
    ADD CONSTRAINT rbl_check_logs_2025_11_pkey PRIMARY KEY (id, check_timestamp);


--
-- Name: rbl_check_logs_2025_12 rbl_check_logs_2025_12_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.rbl_check_logs_2025_12
    ADD CONSTRAINT rbl_check_logs_2025_12_pkey PRIMARY KEY (id, check_timestamp);


--
-- Name: rbl_check_logs_2026_01 rbl_check_logs_2026_01_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.rbl_check_logs_2026_01
    ADD CONSTRAINT rbl_check_logs_2026_01_pkey PRIMARY KEY (id, check_timestamp);


--
-- Name: rbl_check_logs_2026_02 rbl_check_logs_2026_02_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.rbl_check_logs_2026_02
    ADD CONSTRAINT rbl_check_logs_2026_02_pkey PRIMARY KEY (id, check_timestamp);


--
-- Name: rbl_check_logs_2026_03 rbl_check_logs_2026_03_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.rbl_check_logs_2026_03
    ADD CONSTRAINT rbl_check_logs_2026_03_pkey PRIMARY KEY (id, check_timestamp);


--
-- Name: rbl_check_runs rbl_check_runs_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.rbl_check_runs
    ADD CONSTRAINT rbl_check_runs_pkey PRIMARY KEY (id);


--
-- Name: rbl_definitions rbl_definitions_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.rbl_definitions
    ADD CONSTRAINT rbl_definitions_pkey PRIMARY KEY (id);


--
-- Name: rbl_definitions rbl_definitions_rbl_zone_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.rbl_definitions
    ADD CONSTRAINT rbl_definitions_rbl_zone_key UNIQUE (rbl_zone);


--
-- Name: reviews reviews_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.reviews
    ADD CONSTRAINT reviews_pkey PRIMARY KEY (id);


--
-- Name: sender_accounts sender_accounts_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sender_accounts
    ADD CONSTRAINT sender_accounts_pkey PRIMARY KEY (id);


--
-- Name: sender_accounts sender_accounts_unique_per_workspace; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sender_accounts
    ADD CONSTRAINT sender_accounts_unique_per_workspace UNIQUE (workspace_id, email_address);


--
-- Name: sender_warmup_snapshots sender_warmup_snapshots_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sender_warmup_snapshots
    ADD CONSTRAINT sender_warmup_snapshots_pkey PRIMARY KEY (id);


--
-- Name: sender_warmup_snapshots sender_warmup_snapshots_unique_snapshot; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sender_warmup_snapshots
    ADD CONSTRAINT sender_warmup_snapshots_unique_snapshot UNIQUE (sender_account_id, snapshot_timestamp);


--
-- Name: spintax_processing_jobs spintax_processing_jobs_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.spintax_processing_jobs
    ADD CONSTRAINT spintax_processing_jobs_pkey PRIMARY KEY (id);


--
-- Name: strategies strategies_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.strategies
    ADD CONSTRAINT strategies_pkey PRIMARY KEY (id);


--
-- Name: strategy_generation_jobs strategy_generation_jobs_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.strategy_generation_jobs
    ADD CONSTRAINT strategy_generation_jobs_pkey PRIMARY KEY (id);


--
-- Name: strategy_revision_requests strategy_revision_requests_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.strategy_revision_requests
    ADD CONSTRAINT strategy_revision_requests_pkey PRIMARY KEY (id);


--
-- Name: strategy_suggestions strategy_suggestions_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.strategy_suggestions
    ADD CONSTRAINT strategy_suggestions_pkey PRIMARY KEY (id);


--
-- Name: subscription_changes subscription_changes_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.subscription_changes
    ADD CONSTRAINT subscription_changes_pkey PRIMARY KEY (id);


--
-- Name: tier_check_summaries tier_check_summaries_check_run_id_tier_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.tier_check_summaries
    ADD CONSTRAINT tier_check_summaries_check_run_id_tier_key UNIQUE (check_run_id, tier);


--
-- Name: tier_check_summaries tier_check_summaries_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.tier_check_summaries
    ADD CONSTRAINT tier_check_summaries_pkey PRIMARY KEY (id);


--
-- Name: transcripts transcripts_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.transcripts
    ADD CONSTRAINT transcripts_pkey PRIMARY KEY (id);


--
-- Name: transcripts transcripts_recording_user_unique; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.transcripts
    ADD CONSTRAINT transcripts_recording_user_unique UNIQUE (recording_id, user_id);


--
-- Name: users unique_user_email; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.users
    ADD CONSTRAINT unique_user_email UNIQUE (email);


--
-- Name: campaign_inboxes uq_campaign_inbox; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.campaign_inboxes
    ADD CONSTRAINT uq_campaign_inbox UNIQUE (emailbison_campaign_id, emailbison_sender_id);


--
-- Name: users users_email_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.users
    ADD CONSTRAINT users_email_key UNIQUE (email);


--
-- Name: users users_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.users
    ADD CONSTRAINT users_pkey PRIMARY KEY (id);


--
-- Name: warmup_check_runs warmup_check_runs_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.warmup_check_runs
    ADD CONSTRAINT warmup_check_runs_pkey PRIMARY KEY (id);


--
-- Name: webhook_logs webhook_logs_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.webhook_logs
    ADD CONSTRAINT webhook_logs_pkey PRIMARY KEY (id);


--
-- Name: workspace_check_summary workspace_check_summary_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.workspace_check_summary
    ADD CONSTRAINT workspace_check_summary_pkey PRIMARY KEY (id);


--
-- Name: workspace_check_summary workspace_per_run; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.workspace_check_summary
    ADD CONSTRAINT workspace_per_run UNIQUE (run_id, workspace_name);


--
-- Name: workspaces workspaces_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.workspaces
    ADD CONSTRAINT workspaces_pkey PRIMARY KEY (id);


--
-- Name: workspaces workspaces_unique_per_instance; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.workspaces
    ADD CONSTRAINT workspaces_unique_per_instance UNIQUE (instance_id, workspace_name);


--
-- Name: idx_campaign_docs_client; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_campaign_docs_client ON public.campaign_documents USING btree (client_id);


--
-- Name: idx_campaign_docs_job; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_campaign_docs_job ON public.campaign_documents USING btree (job_id);


--
-- Name: idx_campaign_docs_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_campaign_docs_status ON public.campaign_documents USING btree (status);


--
-- Name: idx_campaign_docs_strategy; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_campaign_docs_strategy ON public.campaign_documents USING btree (strategy_id);


--
-- Name: idx_campaign_events_campaign; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_campaign_events_campaign ON public.campaign_events USING btree (campaign_id, event_timestamp DESC);


--
-- Name: idx_campaign_events_event_data; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_campaign_events_event_data ON public.campaign_events USING gin (event_data);


--
-- Name: idx_campaign_events_lead_email; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_campaign_events_lead_email ON public.campaign_events USING btree (lead_email);


--
-- Name: idx_campaign_events_lead_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_campaign_events_lead_id ON public.campaign_events USING btree (emailbison_lead_id);


--
-- Name: idx_campaign_events_sender; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_campaign_events_sender ON public.campaign_events USING btree (sender_account_id);


--
-- Name: idx_campaign_events_sender_account; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_campaign_events_sender_account ON public.campaign_events USING btree (sender_account_id) WHERE (sender_account_id IS NOT NULL);


--
-- Name: idx_campaign_events_sender_bounces; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_campaign_events_sender_bounces ON public.campaign_events USING btree (sender_account_id, event_timestamp) WHERE ((event_type = 'bounce'::text) AND (sender_account_id IS NOT NULL));


--
-- Name: idx_campaign_events_timestamp; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_campaign_events_timestamp ON public.campaign_events USING btree (event_timestamp DESC);


--
-- Name: idx_campaign_events_type; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_campaign_events_type ON public.campaign_events USING btree (event_type);


--
-- Name: idx_campaign_events_type_timestamp; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_campaign_events_type_timestamp ON public.campaign_events USING btree (event_type, event_timestamp DESC);


--
-- Name: idx_campaign_inboxes_campaign; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_campaign_inboxes_campaign ON public.campaign_inboxes USING btree (campaign_id) WHERE (is_active = true);


--
-- Name: idx_campaign_inboxes_emailbison_campaign; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_campaign_inboxes_emailbison_campaign ON public.campaign_inboxes USING btree (emailbison_campaign_id);


--
-- Name: idx_campaign_inboxes_emailbison_sender; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_campaign_inboxes_emailbison_sender ON public.campaign_inboxes USING btree (emailbison_sender_id);


--
-- Name: idx_campaign_inboxes_sender; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_campaign_inboxes_sender ON public.campaign_inboxes USING btree (sender_account_id) WHERE (is_active = true);


--
-- Name: idx_campaign_snapshots_campaign; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_campaign_snapshots_campaign ON public.campaign_snapshots USING btree (campaign_id, snapshot_timestamp DESC);


--
-- Name: idx_campaign_snapshots_period; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_campaign_snapshots_period ON public.campaign_snapshots USING btree (period_start, period_end);


--
-- Name: idx_campaign_snapshots_progress; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_campaign_snapshots_progress ON public.campaign_snapshots USING btree (campaign_id, total_leads, total_leads_contacted) WHERE (total_leads > 0);


--
-- Name: idx_campaign_snapshots_timestamp; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_campaign_snapshots_timestamp ON public.campaign_snapshots USING btree (snapshot_timestamp DESC);


--
-- Name: idx_campaigns_burned_7d; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_campaigns_burned_7d ON public.emailbison_campaigns USING btree (inboxes_burned_7d DESC);


--
-- Name: idx_campaigns_quarantined; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_campaigns_quarantined ON public.emailbison_campaigns USING btree (quarantined_at) WHERE (quarantined_at IS NOT NULL);


--
-- Name: idx_campaigns_state; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_campaigns_state ON public.emailbison_campaigns USING btree (campaign_state);


--
-- Name: idx_campaigns_workspace; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_campaigns_workspace ON public.emailbison_campaigns USING btree (workspace_id);


--
-- Name: idx_check_runs_prefect_flow_run; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_check_runs_prefect_flow_run ON public.rbl_check_runs USING btree (prefect_flow_run_id);


--
-- Name: idx_clients_workspace_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_clients_workspace_id ON public.clients USING btree (workspace_id);


--
-- Name: idx_companies_b2b_email; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_companies_b2b_email ON public.companies USING btree (is_b2b_email);


--
-- Name: idx_companies_client_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_companies_client_id ON public.companies USING btree (client_id);


--
-- Name: idx_companies_domain; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_companies_domain ON public.companies USING btree (client_id, normalized_domain);


--
-- Name: idx_companies_intent_score; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_companies_intent_score ON public.companies USING btree (client_id, intent_score);


--
-- Name: idx_companies_layer; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_companies_layer ON public.companies USING btree (client_id, layer);


--
-- Name: idx_companies_lead_quality; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_companies_lead_quality ON public.companies USING btree (client_id, lead_quality_score);


--
-- Name: idx_companies_tier; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_companies_tier ON public.companies USING btree (client_id, icp_tier);


--
-- Name: idx_cost_logs_project; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_cost_logs_project ON public.cost_logs USING btree (project_id);


--
-- Name: idx_cost_logs_service; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_cost_logs_service ON public.cost_logs USING btree (service);


--
-- Name: idx_costs_api; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_costs_api ON public.cost_logs USING btree (api_name, "timestamp");


--
-- Name: idx_costs_client_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_costs_client_id ON public.cost_logs USING btree (client_id);


--
-- Name: idx_costs_timestamp; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_costs_timestamp ON public.cost_logs USING btree (client_id, "timestamp");


--
-- Name: idx_cycles_client; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_cycles_client ON public.campaign_cycles USING btree (client_id);


--
-- Name: idx_cycles_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_cycles_status ON public.campaign_cycles USING btree (status);


--
-- Name: idx_cycles_strategy; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_cycles_strategy ON public.campaign_cycles USING btree (strategy_id);


--
-- Name: idx_deletion_log_campaign_protected; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_deletion_log_campaign_protected ON public.inbox_deletion_log USING btree (campaign_protected);


--
-- Name: idx_deletion_log_deleted_at; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_deletion_log_deleted_at ON public.inbox_deletion_log USING btree (deleted_at DESC);


--
-- Name: idx_deletion_log_email; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_deletion_log_email ON public.inbox_deletion_log USING btree (email_address);


--
-- Name: idx_deletion_log_provider; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_deletion_log_provider ON public.inbox_deletion_log USING btree (provider);


--
-- Name: idx_deletion_log_provider_date; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_deletion_log_provider_date ON public.inbox_deletion_log USING btree (provider, deleted_at DESC);


--
-- Name: idx_deletion_log_reason; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_deletion_log_reason ON public.inbox_deletion_log USING btree (deletion_reason);


--
-- Name: idx_deletion_log_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_deletion_log_status ON public.inbox_deletion_log USING btree (deletion_status);


--
-- Name: idx_deletion_log_status_date; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_deletion_log_status_date ON public.inbox_deletion_log USING btree (deletion_status, deleted_at DESC);


--
-- Name: idx_deletion_log_workspace; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_deletion_log_workspace ON public.inbox_deletion_log USING btree (bison_workspace_id);


--
-- Name: idx_deletion_log_workspace_date; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_deletion_log_workspace_date ON public.inbox_deletion_log USING btree (bison_workspace_id, deleted_at DESC);


--
-- Name: idx_domain_check_results_checked_at; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_domain_check_results_checked_at ON public.domain_check_results USING btree (checked_at DESC);


--
-- Name: idx_domain_check_results_clean; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_domain_check_results_clean ON public.domain_check_results USING btree (is_clean);


--
-- Name: idx_domain_check_results_domain; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_domain_check_results_domain ON public.domain_check_results USING btree (domain);


--
-- Name: idx_domain_check_results_domain_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_domain_check_results_domain_id ON public.domain_check_results USING btree (domain_id);


--
-- Name: idx_domain_check_results_health_score; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_domain_check_results_health_score ON public.domain_check_results USING btree (health_score);


--
-- Name: idx_domain_check_results_run_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_domain_check_results_run_id ON public.domain_check_results USING btree (run_id);


--
-- Name: idx_domain_check_summary_check_run_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_domain_check_summary_check_run_id ON public.domain_check_summary USING btree (check_run_id) WHERE (check_run_id IS NOT NULL);


--
-- Name: idx_domain_check_summary_clean; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_domain_check_summary_clean ON public.domain_check_summary USING btree (is_clean) WHERE (is_clean = false);


--
-- Name: idx_domain_check_summary_domain; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_domain_check_summary_domain ON public.domain_check_summary USING btree (domain_id);


--
-- Name: idx_domain_check_summary_domain_latest; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_domain_check_summary_domain_latest ON public.domain_check_summary USING btree (domain_id, check_timestamp DESC);


--
-- Name: idx_domain_check_summary_health_score; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_domain_check_summary_health_score ON public.domain_check_summary USING btree (health_score);


--
-- Name: idx_domain_check_summary_tier; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_domain_check_summary_tier ON public.domain_check_summary USING btree (tier) WHERE (tier IS NOT NULL);


--
-- Name: idx_domain_check_summary_timestamp; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_domain_check_summary_timestamp ON public.domain_check_summary USING btree (check_timestamp);


--
-- Name: idx_domain_jobs_client; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_domain_jobs_client ON public.domain_generation_jobs USING btree (client_id);


--
-- Name: idx_domain_jobs_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_domain_jobs_status ON public.domain_generation_jobs USING btree (status);


--
-- Name: idx_domains_active; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_domains_active ON public.domains USING btree (is_active) WHERE (is_active = true);


--
-- Name: idx_domains_approval_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_domains_approval_status ON public.domains USING btree (workspace_id, approval_status);


--
-- Name: idx_domains_clean; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_domains_clean ON public.domains USING btree (is_clean) WHERE (is_clean = false);


--
-- Name: idx_domains_health; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_domains_health ON public.domains USING btree (workspace_id, is_clean, latest_health_score);


--
-- Name: idx_domains_health_pct; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_domains_health_pct ON public.domains USING btree (health_percentage);


--
-- Name: idx_domains_health_score; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_domains_health_score ON public.domains USING btree (latest_health_score);


--
-- Name: idx_domains_infrastructure; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_domains_infrastructure ON public.domains USING btree (workspace_id, infrastructure_type) WHERE (infrastructure_type IS NOT NULL);


--
-- Name: idx_domains_job_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_domains_job_id ON public.domains USING btree (job_id);


--
-- Name: idx_domains_killed_at; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_domains_killed_at ON public.domains USING btree (killed_at) WHERE (killed_at IS NOT NULL);


--
-- Name: idx_domains_last_checked; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_domains_last_checked ON public.domains USING btree (last_checked_at);


--
-- Name: idx_domains_last_price_check; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_domains_last_price_check ON public.domains USING btree (last_price_check);


--
-- Name: idx_domains_lifecycle; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_domains_lifecycle ON public.domains USING btree (lifecycle_stage);


--
-- Name: idx_domains_name; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_domains_name ON public.domains USING btree (domain_name);


--
-- Name: idx_domains_next_check; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_domains_next_check ON public.domains USING btree (next_check_at) WHERE (is_active = true);


--
-- Name: idx_domains_provider; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_domains_provider ON public.domains USING btree (provider);


--
-- Name: idx_domains_rotation_due; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_domains_rotation_due ON public.domains USING btree (rotation_due_at) WHERE (rotation_due_at IS NOT NULL);


--
-- Name: idx_domains_state; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_domains_state ON public.domains USING btree (domain_state);


--
-- Name: idx_domains_workspace; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_domains_workspace ON public.domains USING btree (workspace_id);


--
-- Name: idx_email_variants_doc; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_email_variants_doc ON public.document_email_variants USING btree (document_id);


--
-- Name: idx_email_variants_position; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_email_variants_position ON public.document_email_variants USING btree (document_id, email_position);


--
-- Name: idx_email_variants_recommended; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_email_variants_recommended ON public.document_email_variants USING btree (document_id, is_recommended) WHERE (is_recommended = true);


--
-- Name: idx_emailbison_campaigns_active; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_emailbison_campaigns_active ON public.emailbison_campaigns USING btree (is_active) WHERE (is_active = true);


--
-- Name: idx_emailbison_campaigns_emailbison_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_emailbison_campaigns_emailbison_id ON public.emailbison_campaigns USING btree (emailbison_campaign_id);


--
-- Name: idx_emailbison_campaigns_last_snapshot; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_emailbison_campaigns_last_snapshot ON public.emailbison_campaigns USING btree (last_snapshot_at);


--
-- Name: idx_emailbison_campaigns_snapshot_eligibility; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_emailbison_campaigns_snapshot_eligibility ON public.emailbison_campaigns USING btree (campaign_status, paused_at, completed_at, completed_snapshot_taken) WHERE (campaign_status = ANY (ARRAY['active'::text, 'paused'::text, 'completed'::text]));


--
-- Name: idx_emailbison_campaigns_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_emailbison_campaigns_status ON public.emailbison_campaigns USING btree (campaign_status);


--
-- Name: idx_emailbison_campaigns_workspace; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_emailbison_campaigns_workspace ON public.emailbison_campaigns USING btree (workspace_id);


--
-- Name: idx_emailbison_instances_active; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_emailbison_instances_active ON public.emailbison_instances USING btree (is_active) WHERE (is_active = true);


--
-- Name: idx_emailbison_instances_last_sync; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_emailbison_instances_last_sync ON public.emailbison_instances USING btree (last_sync_at);


--
-- Name: idx_emails_client_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_emails_client_id ON public.predicted_emails USING btree (client_id);


--
-- Name: idx_emails_person_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_emails_person_id ON public.predicted_emails USING btree (person_id);


--
-- Name: idx_emails_unique; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX idx_emails_unique ON public.predicted_emails USING btree (email);


--
-- Name: idx_emails_validation; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_emails_validation ON public.predicted_emails USING btree (client_id, validation_status, validation_tier);


--
-- Name: idx_health_events_entity; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_health_events_entity ON public.health_events USING btree (entity_type, entity_id);


--
-- Name: idx_health_events_root_cause; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_health_events_root_cause ON public.health_events USING btree (root_cause_category);


--
-- Name: idx_health_events_severity; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_health_events_severity ON public.health_events USING btree (severity);


--
-- Name: idx_health_events_timestamp; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_health_events_timestamp ON public.health_events USING btree (event_timestamp DESC);


--
-- Name: idx_health_events_trigger; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_health_events_trigger ON public.health_events USING btree (trigger_type) WHERE (trigger_type IS NOT NULL);


--
-- Name: idx_health_events_type; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_health_events_type ON public.health_events USING btree (event_type);


--
-- Name: idx_health_events_unresolved; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_health_events_unresolved ON public.health_events USING btree (resolved_at) WHERE (resolved_at IS NULL);


--
-- Name: idx_health_events_workspace; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_health_events_workspace ON public.health_events USING btree (workspace_id);


--
-- Name: idx_health_snapshots_inbox; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_health_snapshots_inbox ON public.inbox_health_snapshots USING btree (inbox_id, snapshot_timestamp DESC);


--
-- Name: idx_health_snapshots_workspace; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_health_snapshots_workspace ON public.inbox_health_snapshots USING btree (workspace_id, snapshot_timestamp DESC);


--
-- Name: idx_icps_active; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_icps_active ON public.icps USING btree (client_id, is_active) WHERE (is_active = true);


--
-- Name: idx_icps_client_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_icps_client_id ON public.icps USING btree (client_id);


--
-- Name: idx_inbox_deletion_log_check_run; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_inbox_deletion_log_check_run ON public.inbox_deletion_log USING btree (check_run_id);


--
-- Name: idx_inbox_removal_events_pending; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_inbox_removal_events_pending ON public.inbox_removal_events USING btree (removed_from_emailbison) WHERE (removed_from_emailbison = false);


--
-- Name: idx_inbox_removal_events_refund_pending; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_inbox_removal_events_refund_pending ON public.inbox_removal_events USING btree (requires_refund) WHERE ((requires_refund = true) AND (refund_processed = false));


--
-- Name: idx_inbox_removal_events_removed_at; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_inbox_removal_events_removed_at ON public.inbox_removal_events USING btree (removed_at DESC) WHERE (removed_at IS NOT NULL);


--
-- Name: idx_inbox_removal_events_sender; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_inbox_removal_events_sender ON public.inbox_removal_events USING btree (sender_account_id);


--
-- Name: idx_inbox_removal_events_tagged_at; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_inbox_removal_events_tagged_at ON public.inbox_removal_events USING btree (tagged_at DESC);


--
-- Name: idx_inbox_removal_events_workspace; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_inbox_removal_events_workspace ON public.inbox_removal_events USING btree (workspace_id);


--
-- Name: idx_kill_events_action; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_kill_events_action ON public.kill_trigger_events USING btree (action_taken);


--
-- Name: idx_kill_events_detected; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_kill_events_detected ON public.kill_trigger_events USING btree (detected_at DESC);


--
-- Name: idx_kill_events_inbox; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_kill_events_inbox ON public.kill_trigger_events USING btree (inbox_id);


--
-- Name: idx_kill_events_pending; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_kill_events_pending ON public.kill_trigger_events USING btree (workspace_id, action_taken) WHERE ((action_taken)::text = 'pending'::text);


--
-- Name: idx_kill_events_workspace; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_kill_events_workspace ON public.kill_trigger_events USING btree (workspace_id);


--
-- Name: idx_kill_triggers_confirming; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_kill_triggers_confirming ON public.kill_triggers USING btree (is_confirming) WHERE (is_confirming = true);


--
-- Name: idx_kill_triggers_entity; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_kill_triggers_entity ON public.kill_triggers USING btree (entity_type, entity_id);


--
-- Name: idx_kill_triggers_fired; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_kill_triggers_fired ON public.kill_triggers USING btree (fired_at DESC);


--
-- Name: idx_kill_triggers_type; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_kill_triggers_type ON public.kill_triggers USING btree (trigger_type);


--
-- Name: idx_kill_triggers_workspace; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_kill_triggers_workspace ON public.kill_triggers USING btree (workspace_id);


--
-- Name: idx_layer_outputs_layer; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_layer_outputs_layer ON public.layer_outputs USING btree (layer);


--
-- Name: idx_layer_outputs_project; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_layer_outputs_project ON public.layer_outputs USING btree (project_id);


--
-- Name: idx_layer_outputs_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_layer_outputs_status ON public.layer_outputs USING btree (review_status);


--
-- Name: idx_lead_pull_jobs_client; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_lead_pull_jobs_client ON public.lead_pull_jobs USING btree (client_id);


--
-- Name: idx_lead_pull_jobs_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_lead_pull_jobs_status ON public.lead_pull_jobs USING btree (status);


--
-- Name: idx_leads_company_domain; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_leads_company_domain ON public.leads USING btree (company_domain);


--
-- Name: idx_leads_current_layer; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_leads_current_layer ON public.leads USING btree (current_layer);


--
-- Name: idx_leads_embedding; Type: INDEX; Schema: public; Owner: -
--

-- index removed (requires pgvector);


--
-- Name: idx_leads_project; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_leads_project ON public.leads USING btree (project_id);


--
-- Name: idx_leads_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_leads_status ON public.leads USING btree (status);


--
-- Name: idx_leads_tier; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_leads_tier ON public.leads USING btree (tier);


--
-- Name: idx_list_segments_bounces; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_list_segments_bounces ON public.list_segments USING btree (bounces_caused DESC);


--
-- Name: idx_list_segments_quarantined; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_list_segments_quarantined ON public.list_segments USING btree (quarantined_at) WHERE (quarantined_at IS NOT NULL);


--
-- Name: idx_list_segments_source; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_list_segments_source ON public.list_segments USING btree (source);


--
-- Name: idx_list_segments_state; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_list_segments_state ON public.list_segments USING btree (segment_state);


--
-- Name: idx_list_segments_workspace; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_list_segments_workspace ON public.list_segments USING btree (workspace_id);


--
-- Name: idx_oauth_sessions_email; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_oauth_sessions_email ON public.oauth_sessions USING btree (email);


--
-- Name: idx_oauth_sessions_expires_at; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_oauth_sessions_expires_at ON public.oauth_sessions USING btree (expires_at);


--
-- Name: idx_oauth_sessions_expires_at_cleanup; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_oauth_sessions_expires_at_cleanup ON public.oauth_sessions USING btree (expires_at) WHERE (completed = false);


--
-- Name: idx_oauth_sessions_fathom_state; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_oauth_sessions_fathom_state ON public.oauth_sessions USING btree (fathom_oauth_state);


--
-- Name: idx_oauth_sessions_session_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_oauth_sessions_session_id ON public.oauth_sessions USING btree (session_id);


--
-- Name: idx_onboarding_client; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_onboarding_client ON public.client_onboarding_submissions USING btree (client_id);


--
-- Name: idx_onboarding_client_active; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX idx_onboarding_client_active ON public.client_onboarding_submissions USING btree (client_id) WHERE ((submission_status)::text <> ALL ((ARRAY['archived'::character varying, 'completed'::character varying])::text[]));


--
-- Name: idx_onboarding_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_onboarding_status ON public.client_onboarding_submissions USING btree (submission_status);


--
-- Name: idx_onboarding_submissions_industry; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_onboarding_submissions_industry ON public.client_onboarding_submissions USING btree (industry);


--
-- Name: idx_onboarding_submitted; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_onboarding_submitted ON public.client_onboarding_submissions USING btree (submitted_at DESC);


--
-- Name: idx_personas_order; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_personas_order ON public.client_personas USING btree (submission_id, persona_order);


--
-- Name: idx_personas_submission; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_personas_submission ON public.client_personas USING btree (submission_id);


--
-- Name: idx_persons_activity_recency; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_persons_activity_recency ON public.persons USING btree (activity_recency_days);


--
-- Name: idx_persons_client_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_persons_client_id ON public.persons USING btree (client_id);


--
-- Name: idx_persons_company_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_persons_company_id ON public.persons USING btree (company_id);


--
-- Name: idx_persons_lead_quality; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_persons_lead_quality ON public.persons USING btree (client_id, lead_quality_score);


--
-- Name: idx_persons_primary; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_persons_primary ON public.persons USING btree (company_id, is_primary_contact) WHERE (is_primary_contact = true);


--
-- Name: idx_placement_tests_account; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_placement_tests_account ON public.placement_tests USING btree (sender_account_id);


--
-- Name: idx_placement_tests_passing; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_placement_tests_passing ON public.placement_tests USING btree (is_passing);


--
-- Name: idx_placement_tests_timestamp; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_placement_tests_timestamp ON public.placement_tests USING btree (test_timestamp DESC);


--
-- Name: idx_price_history_domain; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_price_history_domain ON public.domain_price_history USING btree (domain_id, checked_at DESC);


--
-- Name: idx_projects_client; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_projects_client ON public.projects USING btree (client_id);


--
-- Name: idx_projects_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_projects_status ON public.projects USING btree (status);


--
-- Name: idx_purchase_jobs_client; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_purchase_jobs_client ON public.inbox_purchase_jobs USING btree (client_id, created_at DESC);


--
-- Name: idx_purchase_jobs_retry; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_purchase_jobs_retry ON public.inbox_purchase_jobs USING btree (status) WHERE ((status)::text = 'failed'::text);


--
-- Name: idx_purchase_jobs_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_purchase_jobs_status ON public.inbox_purchase_jobs USING btree (status);


--
-- Name: idx_purchase_jobs_worker_pending; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_purchase_jobs_worker_pending ON public.inbox_purchase_jobs USING btree (status, worker_mode) WHERE (((status)::text = 'pending'::text) AND ((worker_mode)::text = 'worker'::text));


--
-- Name: idx_purchase_queue_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_purchase_queue_status ON public.domain_purchase_queue USING btree (status, created_at);


--
-- Name: idx_purchase_steps_job; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_purchase_steps_job ON public.purchase_job_steps USING btree (job_id, created_at);


--
-- Name: idx_rbl_check_logs_check_run_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_rbl_check_logs_check_run_id ON ONLY public.rbl_check_logs USING btree (check_run_id) WHERE (check_run_id IS NOT NULL);


--
-- Name: idx_rbl_check_logs_domain; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_rbl_check_logs_domain ON ONLY public.rbl_check_logs USING btree (domain_id);


--
-- Name: idx_rbl_check_logs_domain_rbl_time; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_rbl_check_logs_domain_rbl_time ON ONLY public.rbl_check_logs USING btree (domain_id, rbl_definition_id, check_timestamp DESC);


--
-- Name: idx_rbl_check_logs_domain_timestamp; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_rbl_check_logs_domain_timestamp ON ONLY public.rbl_check_logs USING btree (domain_id, check_timestamp DESC);


--
-- Name: idx_rbl_check_logs_listed; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_rbl_check_logs_listed ON ONLY public.rbl_check_logs USING btree (is_listed) WHERE (is_listed = true);


--
-- Name: idx_rbl_check_logs_rbl; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_rbl_check_logs_rbl ON ONLY public.rbl_check_logs USING btree (rbl_definition_id);


--
-- Name: idx_rbl_check_logs_tier; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_rbl_check_logs_tier ON ONLY public.rbl_check_logs USING btree (tier) WHERE (tier IS NOT NULL);


--
-- Name: idx_rbl_check_logs_timestamp; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_rbl_check_logs_timestamp ON ONLY public.rbl_check_logs USING btree (check_timestamp);


--
-- Name: idx_rbl_check_runs_started; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_rbl_check_runs_started ON public.rbl_check_runs USING btree (started_at DESC);


--
-- Name: idx_rbl_check_runs_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_rbl_check_runs_status ON public.rbl_check_runs USING btree (status);


--
-- Name: idx_rbl_check_runs_type; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_rbl_check_runs_type ON public.rbl_check_runs USING btree (run_type);


--
-- Name: idx_rbl_definitions_active; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_rbl_definitions_active ON public.rbl_definitions USING btree (is_active) WHERE (is_active = true);


--
-- Name: idx_rbl_definitions_reliability; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_rbl_definitions_reliability ON public.rbl_definitions USING btree (consecutive_failures, is_active);


--
-- Name: idx_rbl_definitions_tier; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_rbl_definitions_tier ON public.rbl_definitions USING btree (tier, is_active);


--
-- Name: idx_rbl_definitions_type; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_rbl_definitions_type ON public.rbl_definitions USING btree (rbl_type);


--
-- Name: idx_rbl_definitions_type_active; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_rbl_definitions_type_active ON public.rbl_definitions USING btree (rbl_type, is_active) WHERE (is_active = true);


--
-- Name: idx_rbl_definitions_zone; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_rbl_definitions_zone ON public.rbl_definitions USING btree (rbl_zone);


--
-- Name: idx_rbl_runs_created; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_rbl_runs_created ON public.rbl_check_runs USING btree (created_at DESC);


--
-- Name: idx_rbl_runs_source; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_rbl_runs_source ON public.rbl_check_runs USING btree (source);


--
-- Name: idx_rbl_runs_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_rbl_runs_status ON public.rbl_check_runs USING btree (run_status);


--
-- Name: idx_revision_requests_client; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_revision_requests_client ON public.strategy_revision_requests USING btree (client_id);


--
-- Name: idx_revision_requests_job; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_revision_requests_job ON public.strategy_revision_requests USING btree (job_id);


--
-- Name: idx_rotation_history_source; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_rotation_history_source ON public.inbox_rotation_history USING btree (source_inbox_id);


--
-- Name: idx_rotation_history_target; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_rotation_history_target ON public.inbox_rotation_history USING btree (target_inbox_id);


--
-- Name: idx_rotation_history_workspace; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_rotation_history_workspace ON public.inbox_rotation_history USING btree (workspace_id, executed_at DESC);


--
-- Name: idx_segments_order; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_segments_order ON public.client_segments USING btree (submission_id, segment_order);


--
-- Name: idx_segments_submission; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_segments_submission ON public.client_segments USING btree (submission_id);


--
-- Name: idx_sender_accounts_active; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_sender_accounts_active ON public.sender_accounts USING btree (is_active) WHERE (is_active = true);


--
-- Name: idx_sender_accounts_domain_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_sender_accounts_domain_id ON public.sender_accounts USING btree (domain_id);


--
-- Name: idx_sender_accounts_email; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_sender_accounts_email ON public.sender_accounts USING btree (email_address);


--
-- Name: idx_sender_accounts_emailbison_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_sender_accounts_emailbison_id ON public.sender_accounts USING btree (emailbison_account_id);


--
-- Name: idx_sender_accounts_esp; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_sender_accounts_esp ON public.sender_accounts USING btree (esp);


--
-- Name: idx_sender_accounts_flagged_retest; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_sender_accounts_flagged_retest ON public.sender_accounts USING btree (flagged_for_retest) WHERE (flagged_for_retest = true);


--
-- Name: idx_sender_accounts_health_score; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_sender_accounts_health_score ON public.sender_accounts USING btree (health_score);


--
-- Name: idx_sender_accounts_inbox_state; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_sender_accounts_inbox_state ON public.sender_accounts USING btree (inbox_state);


--
-- Name: idx_sender_accounts_killed_at; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_sender_accounts_killed_at ON public.sender_accounts USING btree (killed_at) WHERE (killed_at IS NOT NULL);


--
-- Name: idx_sender_accounts_last_check_run; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_sender_accounts_last_check_run ON public.sender_accounts USING btree (last_check_run_id);


--
-- Name: idx_sender_accounts_live; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_sender_accounts_live ON public.sender_accounts USING btree (inbox_state) WHERE (inbox_state = 'live'::public.inbox_state);


--
-- Name: idx_sender_accounts_pool_tier; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_sender_accounts_pool_tier ON public.sender_accounts USING btree (pool_tier);


--
-- Name: idx_sender_accounts_removal_pending; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_sender_accounts_removal_pending ON public.sender_accounts USING btree (workspace_id, removal_tag) WHERE ((removal_tag IS NOT NULL) AND (inbox_state = 'live'::public.inbox_state));


--
-- Name: idx_sender_accounts_removal_tag; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_sender_accounts_removal_tag ON public.sender_accounts USING btree (removal_tag) WHERE (removal_tag IS NOT NULL);


--
-- Name: idx_sender_accounts_removal_tagged; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_sender_accounts_removal_tagged ON public.sender_accounts USING btree (removal_tagged) WHERE (removal_tagged = true);


--
-- Name: idx_sender_accounts_role; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_sender_accounts_role ON public.sender_accounts USING btree (role);


--
-- Name: idx_sender_accounts_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_sender_accounts_status ON public.sender_accounts USING btree (status);


--
-- Name: idx_sender_accounts_tagged_at; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_sender_accounts_tagged_at ON public.sender_accounts USING btree (tagged_at DESC) WHERE (tagged_at IS NOT NULL);


--
-- Name: idx_sender_accounts_workspace; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_sender_accounts_workspace ON public.sender_accounts USING btree (workspace_id);


--
-- Name: idx_sender_accounts_workspace_state; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_sender_accounts_workspace_state ON public.sender_accounts USING btree (workspace_id, inbox_state);


--
-- Name: idx_sender_accounts_workspace_tagged; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_sender_accounts_workspace_tagged ON public.sender_accounts USING btree (workspace_id, removal_tagged, tagged_at DESC) WHERE (removal_tagged = true);


--
-- Name: idx_sender_warmup_snapshots_enabled; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_sender_warmup_snapshots_enabled ON public.sender_warmup_snapshots USING btree (warmup_enabled) WHERE (warmup_enabled = true);


--
-- Name: idx_sender_warmup_snapshots_period; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_sender_warmup_snapshots_period ON public.sender_warmup_snapshots USING btree (period_start, period_end);


--
-- Name: idx_sender_warmup_snapshots_score; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_sender_warmup_snapshots_score ON public.sender_warmup_snapshots USING btree (warmup_score);


--
-- Name: idx_sender_warmup_snapshots_sender; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_sender_warmup_snapshots_sender ON public.sender_warmup_snapshots USING btree (sender_account_id, snapshot_timestamp DESC);


--
-- Name: idx_sender_warmup_snapshots_timestamp; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_sender_warmup_snapshots_timestamp ON public.sender_warmup_snapshots USING btree (snapshot_timestamp DESC);


--
-- Name: idx_spintax_jobs_client; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_spintax_jobs_client ON public.spintax_processing_jobs USING btree (client_id);


--
-- Name: idx_spintax_jobs_sequence; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_spintax_jobs_sequence ON public.spintax_processing_jobs USING btree (sequence_id);


--
-- Name: idx_spintax_jobs_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_spintax_jobs_status ON public.spintax_processing_jobs USING btree (status, created_at);


--
-- Name: idx_strategies_client; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_strategies_client ON public.strategies USING btree (client_id);


--
-- Name: idx_strategies_submission; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_strategies_submission ON public.strategies USING btree (submission_id);


--
-- Name: idx_strategy_jobs_client; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_strategy_jobs_client ON public.strategy_generation_jobs USING btree (client_id);


--
-- Name: idx_strategy_jobs_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_strategy_jobs_status ON public.strategy_generation_jobs USING btree (status);


--
-- Name: idx_strategy_suggestions_is_sequence; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_strategy_suggestions_is_sequence ON public.strategy_suggestions USING btree (client_id, is_sequence) WHERE (is_sequence = true);


--
-- Name: idx_subject_options_doc; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_subject_options_doc ON public.document_subject_options USING btree (document_id);


--
-- Name: idx_subject_options_position; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_subject_options_position ON public.document_subject_options USING btree (document_id, email_position);


--
-- Name: idx_subscription_changes_created; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_subscription_changes_created ON public.subscription_changes USING btree (created_at);


--
-- Name: idx_subscription_changes_subscription; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_subscription_changes_subscription ON public.subscription_changes USING btree (subscription_id);


--
-- Name: idx_subscriptions_client; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_subscriptions_client ON public.client_subscriptions USING btree (client_id);


--
-- Name: idx_subscriptions_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_subscriptions_status ON public.client_subscriptions USING btree (status);


--
-- Name: idx_suggestions_angle; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_suggestions_angle ON public.strategy_suggestions USING btree (campaign_angle);


--
-- Name: idx_suggestions_client; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_suggestions_client ON public.strategy_suggestions USING btree (client_id);


--
-- Name: idx_suggestions_cycle; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_suggestions_cycle ON public.strategy_suggestions USING btree (cycle_id);


--
-- Name: idx_suggestions_document; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_suggestions_document ON public.strategy_suggestions USING btree (document_id);


--
-- Name: idx_suggestions_job; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_suggestions_job ON public.strategy_suggestions USING btree (job_id);


--
-- Name: idx_suggestions_lineage; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_suggestions_lineage ON public.strategy_suggestions USING btree (lineage_id);


--
-- Name: idx_suggestions_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_suggestions_status ON public.strategy_suggestions USING btree (status);


--
-- Name: idx_suggestions_strategy; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_suggestions_strategy ON public.strategy_suggestions USING btree (strategy_id);


--
-- Name: idx_suggestions_version; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_suggestions_version ON public.strategy_suggestions USING btree (lineage_id, campaign_version);


--
-- Name: idx_tier_check_summaries_check_run_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_tier_check_summaries_check_run_id ON public.tier_check_summaries USING btree (check_run_id);


--
-- Name: idx_tier_check_summaries_domains_failed; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_tier_check_summaries_domains_failed ON public.tier_check_summaries USING btree (domains_failed) WHERE (domains_failed > 0);


--
-- Name: idx_tier_check_summaries_started_at; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_tier_check_summaries_started_at ON public.tier_check_summaries USING btree (started_at DESC);


--
-- Name: idx_tier_check_summaries_tier; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_tier_check_summaries_tier ON public.tier_check_summaries USING btree (tier);


--
-- Name: idx_transcripts_processed_at; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_transcripts_processed_at ON public.transcripts USING btree (processed_at DESC);


--
-- Name: idx_transcripts_recording_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_transcripts_recording_id ON public.transcripts USING btree (recording_id);


--
-- Name: idx_transcripts_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_transcripts_user_id ON public.transcripts USING btree (user_id);


--
-- Name: idx_users_active; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_users_active ON public.users USING btree (is_active);


--
-- Name: idx_users_email; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_users_email ON public.users USING btree (email);


--
-- Name: idx_users_fathom_email; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_users_fathom_email ON public.users USING btree (fathom_user_email);


--
-- Name: idx_users_fathom_oauth; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_users_fathom_oauth ON public.users USING btree (has_fathom_oauth) WHERE (has_fathom_oauth = true);


--
-- Name: idx_warmup_check_runs_latest; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_warmup_check_runs_latest ON public.warmup_check_runs USING btree (completed_at DESC) WHERE ((run_status)::text = ANY ((ARRAY['completed'::character varying, 'partial'::character varying])::text[]));


--
-- Name: idx_warmup_check_runs_prefect; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_warmup_check_runs_prefect ON public.warmup_check_runs USING btree (prefect_flow_run_id) WHERE (prefect_flow_run_id IS NOT NULL);


--
-- Name: idx_warmup_check_runs_source; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_warmup_check_runs_source ON public.warmup_check_runs USING btree (source);


--
-- Name: idx_warmup_check_runs_started; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_warmup_check_runs_started ON public.warmup_check_runs USING btree (started_at DESC);


--
-- Name: idx_warmup_check_runs_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_warmup_check_runs_status ON public.warmup_check_runs USING btree (run_status);


--
-- Name: idx_webhook_logs_received_at; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_webhook_logs_received_at ON public.webhook_logs USING btree (webhook_received_at DESC);


--
-- Name: idx_webhook_logs_recording_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_webhook_logs_recording_id ON public.webhook_logs USING btree (recording_id);


--
-- Name: idx_webhook_logs_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_webhook_logs_status ON public.webhook_logs USING btree (status);


--
-- Name: idx_workspace_summary_errors; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_workspace_summary_errors ON public.workspace_check_summary USING btree (error_count) WHERE (error_count > 0);


--
-- Name: idx_workspace_summary_run; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_workspace_summary_run ON public.workspace_check_summary USING btree (run_id);


--
-- Name: idx_workspace_summary_workspace; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_workspace_summary_workspace ON public.workspace_check_summary USING btree (workspace_name);


--
-- Name: idx_workspaces_active; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_workspaces_active ON public.workspaces USING btree (is_active) WHERE (is_active = true);


--
-- Name: idx_workspaces_automation_enabled; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_workspaces_automation_enabled ON public.workspaces USING btree (id) WHERE (automation_enabled = true);


--
-- Name: idx_workspaces_emailbison_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_workspaces_emailbison_id ON public.workspaces USING btree (emailbison_workspace_id);


--
-- Name: idx_workspaces_instance; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_workspaces_instance ON public.workspaces USING btree (instance_id);


--
-- Name: idx_workspaces_last_sync; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_workspaces_last_sync ON public.workspaces USING btree (last_sync_at);


--
-- Name: rbl_check_logs_2025_10_check_run_id_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX rbl_check_logs_2025_10_check_run_id_idx ON public.rbl_check_logs_2025_10 USING btree (check_run_id) WHERE (check_run_id IS NOT NULL);


--
-- Name: rbl_check_logs_2025_10_check_timestamp_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX rbl_check_logs_2025_10_check_timestamp_idx ON public.rbl_check_logs_2025_10 USING btree (check_timestamp);


--
-- Name: rbl_check_logs_2025_10_domain_id_check_timestamp_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX rbl_check_logs_2025_10_domain_id_check_timestamp_idx ON public.rbl_check_logs_2025_10 USING btree (domain_id, check_timestamp DESC);


--
-- Name: rbl_check_logs_2025_10_domain_id_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX rbl_check_logs_2025_10_domain_id_idx ON public.rbl_check_logs_2025_10 USING btree (domain_id);


--
-- Name: rbl_check_logs_2025_10_domain_id_rbl_definition_id_check_ti_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX rbl_check_logs_2025_10_domain_id_rbl_definition_id_check_ti_idx ON public.rbl_check_logs_2025_10 USING btree (domain_id, rbl_definition_id, check_timestamp DESC);


--
-- Name: rbl_check_logs_2025_10_is_listed_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX rbl_check_logs_2025_10_is_listed_idx ON public.rbl_check_logs_2025_10 USING btree (is_listed) WHERE (is_listed = true);


--
-- Name: rbl_check_logs_2025_10_rbl_definition_id_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX rbl_check_logs_2025_10_rbl_definition_id_idx ON public.rbl_check_logs_2025_10 USING btree (rbl_definition_id);


--
-- Name: rbl_check_logs_2025_10_tier_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX rbl_check_logs_2025_10_tier_idx ON public.rbl_check_logs_2025_10 USING btree (tier) WHERE (tier IS NOT NULL);


--
-- Name: rbl_check_logs_2025_11_check_run_id_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX rbl_check_logs_2025_11_check_run_id_idx ON public.rbl_check_logs_2025_11 USING btree (check_run_id) WHERE (check_run_id IS NOT NULL);


--
-- Name: rbl_check_logs_2025_11_check_timestamp_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX rbl_check_logs_2025_11_check_timestamp_idx ON public.rbl_check_logs_2025_11 USING btree (check_timestamp);


--
-- Name: rbl_check_logs_2025_11_domain_id_check_timestamp_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX rbl_check_logs_2025_11_domain_id_check_timestamp_idx ON public.rbl_check_logs_2025_11 USING btree (domain_id, check_timestamp DESC);


--
-- Name: rbl_check_logs_2025_11_domain_id_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX rbl_check_logs_2025_11_domain_id_idx ON public.rbl_check_logs_2025_11 USING btree (domain_id);


--
-- Name: rbl_check_logs_2025_11_domain_id_rbl_definition_id_check_ti_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX rbl_check_logs_2025_11_domain_id_rbl_definition_id_check_ti_idx ON public.rbl_check_logs_2025_11 USING btree (domain_id, rbl_definition_id, check_timestamp DESC);


--
-- Name: rbl_check_logs_2025_11_is_listed_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX rbl_check_logs_2025_11_is_listed_idx ON public.rbl_check_logs_2025_11 USING btree (is_listed) WHERE (is_listed = true);


--
-- Name: rbl_check_logs_2025_11_rbl_definition_id_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX rbl_check_logs_2025_11_rbl_definition_id_idx ON public.rbl_check_logs_2025_11 USING btree (rbl_definition_id);


--
-- Name: rbl_check_logs_2025_11_tier_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX rbl_check_logs_2025_11_tier_idx ON public.rbl_check_logs_2025_11 USING btree (tier) WHERE (tier IS NOT NULL);


--
-- Name: rbl_check_logs_2025_12_check_run_id_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX rbl_check_logs_2025_12_check_run_id_idx ON public.rbl_check_logs_2025_12 USING btree (check_run_id) WHERE (check_run_id IS NOT NULL);


--
-- Name: rbl_check_logs_2025_12_check_timestamp_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX rbl_check_logs_2025_12_check_timestamp_idx ON public.rbl_check_logs_2025_12 USING btree (check_timestamp);


--
-- Name: rbl_check_logs_2025_12_domain_id_check_timestamp_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX rbl_check_logs_2025_12_domain_id_check_timestamp_idx ON public.rbl_check_logs_2025_12 USING btree (domain_id, check_timestamp DESC);


--
-- Name: rbl_check_logs_2025_12_domain_id_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX rbl_check_logs_2025_12_domain_id_idx ON public.rbl_check_logs_2025_12 USING btree (domain_id);


--
-- Name: rbl_check_logs_2025_12_domain_id_rbl_definition_id_check_ti_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX rbl_check_logs_2025_12_domain_id_rbl_definition_id_check_ti_idx ON public.rbl_check_logs_2025_12 USING btree (domain_id, rbl_definition_id, check_timestamp DESC);


--
-- Name: rbl_check_logs_2025_12_is_listed_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX rbl_check_logs_2025_12_is_listed_idx ON public.rbl_check_logs_2025_12 USING btree (is_listed) WHERE (is_listed = true);


--
-- Name: rbl_check_logs_2025_12_rbl_definition_id_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX rbl_check_logs_2025_12_rbl_definition_id_idx ON public.rbl_check_logs_2025_12 USING btree (rbl_definition_id);


--
-- Name: rbl_check_logs_2025_12_tier_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX rbl_check_logs_2025_12_tier_idx ON public.rbl_check_logs_2025_12 USING btree (tier) WHERE (tier IS NOT NULL);


--
-- Name: rbl_check_logs_2026_01_check_run_id_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX rbl_check_logs_2026_01_check_run_id_idx ON public.rbl_check_logs_2026_01 USING btree (check_run_id) WHERE (check_run_id IS NOT NULL);


--
-- Name: rbl_check_logs_2026_01_check_timestamp_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX rbl_check_logs_2026_01_check_timestamp_idx ON public.rbl_check_logs_2026_01 USING btree (check_timestamp);


--
-- Name: rbl_check_logs_2026_01_domain_id_check_timestamp_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX rbl_check_logs_2026_01_domain_id_check_timestamp_idx ON public.rbl_check_logs_2026_01 USING btree (domain_id, check_timestamp DESC);


--
-- Name: rbl_check_logs_2026_01_domain_id_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX rbl_check_logs_2026_01_domain_id_idx ON public.rbl_check_logs_2026_01 USING btree (domain_id);


--
-- Name: rbl_check_logs_2026_01_domain_id_rbl_definition_id_check_ti_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX rbl_check_logs_2026_01_domain_id_rbl_definition_id_check_ti_idx ON public.rbl_check_logs_2026_01 USING btree (domain_id, rbl_definition_id, check_timestamp DESC);


--
-- Name: rbl_check_logs_2026_01_is_listed_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX rbl_check_logs_2026_01_is_listed_idx ON public.rbl_check_logs_2026_01 USING btree (is_listed) WHERE (is_listed = true);


--
-- Name: rbl_check_logs_2026_01_rbl_definition_id_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX rbl_check_logs_2026_01_rbl_definition_id_idx ON public.rbl_check_logs_2026_01 USING btree (rbl_definition_id);


--
-- Name: rbl_check_logs_2026_01_tier_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX rbl_check_logs_2026_01_tier_idx ON public.rbl_check_logs_2026_01 USING btree (tier) WHERE (tier IS NOT NULL);


--
-- Name: rbl_check_logs_2026_02_check_run_id_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX rbl_check_logs_2026_02_check_run_id_idx ON public.rbl_check_logs_2026_02 USING btree (check_run_id) WHERE (check_run_id IS NOT NULL);


--
-- Name: rbl_check_logs_2026_02_check_timestamp_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX rbl_check_logs_2026_02_check_timestamp_idx ON public.rbl_check_logs_2026_02 USING btree (check_timestamp);


--
-- Name: rbl_check_logs_2026_02_domain_id_check_timestamp_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX rbl_check_logs_2026_02_domain_id_check_timestamp_idx ON public.rbl_check_logs_2026_02 USING btree (domain_id, check_timestamp DESC);


--
-- Name: rbl_check_logs_2026_02_domain_id_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX rbl_check_logs_2026_02_domain_id_idx ON public.rbl_check_logs_2026_02 USING btree (domain_id);


--
-- Name: rbl_check_logs_2026_02_domain_id_rbl_definition_id_check_ti_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX rbl_check_logs_2026_02_domain_id_rbl_definition_id_check_ti_idx ON public.rbl_check_logs_2026_02 USING btree (domain_id, rbl_definition_id, check_timestamp DESC);


--
-- Name: rbl_check_logs_2026_02_is_listed_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX rbl_check_logs_2026_02_is_listed_idx ON public.rbl_check_logs_2026_02 USING btree (is_listed) WHERE (is_listed = true);


--
-- Name: rbl_check_logs_2026_02_rbl_definition_id_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX rbl_check_logs_2026_02_rbl_definition_id_idx ON public.rbl_check_logs_2026_02 USING btree (rbl_definition_id);


--
-- Name: rbl_check_logs_2026_02_tier_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX rbl_check_logs_2026_02_tier_idx ON public.rbl_check_logs_2026_02 USING btree (tier) WHERE (tier IS NOT NULL);


--
-- Name: rbl_check_logs_2026_03_check_run_id_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX rbl_check_logs_2026_03_check_run_id_idx ON public.rbl_check_logs_2026_03 USING btree (check_run_id) WHERE (check_run_id IS NOT NULL);


--
-- Name: rbl_check_logs_2026_03_check_timestamp_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX rbl_check_logs_2026_03_check_timestamp_idx ON public.rbl_check_logs_2026_03 USING btree (check_timestamp);


--
-- Name: rbl_check_logs_2026_03_domain_id_check_timestamp_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX rbl_check_logs_2026_03_domain_id_check_timestamp_idx ON public.rbl_check_logs_2026_03 USING btree (domain_id, check_timestamp DESC);


--
-- Name: rbl_check_logs_2026_03_domain_id_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX rbl_check_logs_2026_03_domain_id_idx ON public.rbl_check_logs_2026_03 USING btree (domain_id);


--
-- Name: rbl_check_logs_2026_03_domain_id_rbl_definition_id_check_ti_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX rbl_check_logs_2026_03_domain_id_rbl_definition_id_check_ti_idx ON public.rbl_check_logs_2026_03 USING btree (domain_id, rbl_definition_id, check_timestamp DESC);


--
-- Name: rbl_check_logs_2026_03_is_listed_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX rbl_check_logs_2026_03_is_listed_idx ON public.rbl_check_logs_2026_03 USING btree (is_listed) WHERE (is_listed = true);


--
-- Name: rbl_check_logs_2026_03_rbl_definition_id_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX rbl_check_logs_2026_03_rbl_definition_id_idx ON public.rbl_check_logs_2026_03 USING btree (rbl_definition_id);


--
-- Name: rbl_check_logs_2026_03_tier_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX rbl_check_logs_2026_03_tier_idx ON public.rbl_check_logs_2026_03 USING btree (tier) WHERE (tier IS NOT NULL);


--
-- Name: unique_fathom_oauth_state_not_null; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX unique_fathom_oauth_state_not_null ON public.oauth_sessions USING btree (fathom_oauth_state) WHERE (fathom_oauth_state IS NOT NULL);


--
-- Name: rbl_check_logs_2025_10_check_run_id_idx; Type: INDEX ATTACH; Schema: public; Owner: -
--

ALTER INDEX public.idx_rbl_check_logs_check_run_id ATTACH PARTITION public.rbl_check_logs_2025_10_check_run_id_idx;


--
-- Name: rbl_check_logs_2025_10_check_timestamp_idx; Type: INDEX ATTACH; Schema: public; Owner: -
--

ALTER INDEX public.idx_rbl_check_logs_timestamp ATTACH PARTITION public.rbl_check_logs_2025_10_check_timestamp_idx;


--
-- Name: rbl_check_logs_2025_10_domain_id_check_timestamp_idx; Type: INDEX ATTACH; Schema: public; Owner: -
--

ALTER INDEX public.idx_rbl_check_logs_domain_timestamp ATTACH PARTITION public.rbl_check_logs_2025_10_domain_id_check_timestamp_idx;


--
-- Name: rbl_check_logs_2025_10_domain_id_idx; Type: INDEX ATTACH; Schema: public; Owner: -
--

ALTER INDEX public.idx_rbl_check_logs_domain ATTACH PARTITION public.rbl_check_logs_2025_10_domain_id_idx;


--
-- Name: rbl_check_logs_2025_10_domain_id_rbl_definition_id_check_ti_idx; Type: INDEX ATTACH; Schema: public; Owner: -
--

ALTER INDEX public.idx_rbl_check_logs_domain_rbl_time ATTACH PARTITION public.rbl_check_logs_2025_10_domain_id_rbl_definition_id_check_ti_idx;


--
-- Name: rbl_check_logs_2025_10_is_listed_idx; Type: INDEX ATTACH; Schema: public; Owner: -
--

ALTER INDEX public.idx_rbl_check_logs_listed ATTACH PARTITION public.rbl_check_logs_2025_10_is_listed_idx;


--
-- Name: rbl_check_logs_2025_10_pkey; Type: INDEX ATTACH; Schema: public; Owner: -
--

ALTER INDEX public.rbl_check_logs_pkey ATTACH PARTITION public.rbl_check_logs_2025_10_pkey;


--
-- Name: rbl_check_logs_2025_10_rbl_definition_id_idx; Type: INDEX ATTACH; Schema: public; Owner: -
--

ALTER INDEX public.idx_rbl_check_logs_rbl ATTACH PARTITION public.rbl_check_logs_2025_10_rbl_definition_id_idx;


--
-- Name: rbl_check_logs_2025_10_tier_idx; Type: INDEX ATTACH; Schema: public; Owner: -
--

ALTER INDEX public.idx_rbl_check_logs_tier ATTACH PARTITION public.rbl_check_logs_2025_10_tier_idx;


--
-- Name: rbl_check_logs_2025_11_check_run_id_idx; Type: INDEX ATTACH; Schema: public; Owner: -
--

ALTER INDEX public.idx_rbl_check_logs_check_run_id ATTACH PARTITION public.rbl_check_logs_2025_11_check_run_id_idx;


--
-- Name: rbl_check_logs_2025_11_check_timestamp_idx; Type: INDEX ATTACH; Schema: public; Owner: -
--

ALTER INDEX public.idx_rbl_check_logs_timestamp ATTACH PARTITION public.rbl_check_logs_2025_11_check_timestamp_idx;


--
-- Name: rbl_check_logs_2025_11_domain_id_check_timestamp_idx; Type: INDEX ATTACH; Schema: public; Owner: -
--

ALTER INDEX public.idx_rbl_check_logs_domain_timestamp ATTACH PARTITION public.rbl_check_logs_2025_11_domain_id_check_timestamp_idx;


--
-- Name: rbl_check_logs_2025_11_domain_id_idx; Type: INDEX ATTACH; Schema: public; Owner: -
--

ALTER INDEX public.idx_rbl_check_logs_domain ATTACH PARTITION public.rbl_check_logs_2025_11_domain_id_idx;


--
-- Name: rbl_check_logs_2025_11_domain_id_rbl_definition_id_check_ti_idx; Type: INDEX ATTACH; Schema: public; Owner: -
--

ALTER INDEX public.idx_rbl_check_logs_domain_rbl_time ATTACH PARTITION public.rbl_check_logs_2025_11_domain_id_rbl_definition_id_check_ti_idx;


--
-- Name: rbl_check_logs_2025_11_is_listed_idx; Type: INDEX ATTACH; Schema: public; Owner: -
--

ALTER INDEX public.idx_rbl_check_logs_listed ATTACH PARTITION public.rbl_check_logs_2025_11_is_listed_idx;


--
-- Name: rbl_check_logs_2025_11_pkey; Type: INDEX ATTACH; Schema: public; Owner: -
--

ALTER INDEX public.rbl_check_logs_pkey ATTACH PARTITION public.rbl_check_logs_2025_11_pkey;


--
-- Name: rbl_check_logs_2025_11_rbl_definition_id_idx; Type: INDEX ATTACH; Schema: public; Owner: -
--

ALTER INDEX public.idx_rbl_check_logs_rbl ATTACH PARTITION public.rbl_check_logs_2025_11_rbl_definition_id_idx;


--
-- Name: rbl_check_logs_2025_11_tier_idx; Type: INDEX ATTACH; Schema: public; Owner: -
--

ALTER INDEX public.idx_rbl_check_logs_tier ATTACH PARTITION public.rbl_check_logs_2025_11_tier_idx;


--
-- Name: rbl_check_logs_2025_12_check_run_id_idx; Type: INDEX ATTACH; Schema: public; Owner: -
--

ALTER INDEX public.idx_rbl_check_logs_check_run_id ATTACH PARTITION public.rbl_check_logs_2025_12_check_run_id_idx;


--
-- Name: rbl_check_logs_2025_12_check_timestamp_idx; Type: INDEX ATTACH; Schema: public; Owner: -
--

ALTER INDEX public.idx_rbl_check_logs_timestamp ATTACH PARTITION public.rbl_check_logs_2025_12_check_timestamp_idx;


--
-- Name: rbl_check_logs_2025_12_domain_id_check_timestamp_idx; Type: INDEX ATTACH; Schema: public; Owner: -
--

ALTER INDEX public.idx_rbl_check_logs_domain_timestamp ATTACH PARTITION public.rbl_check_logs_2025_12_domain_id_check_timestamp_idx;


--
-- Name: rbl_check_logs_2025_12_domain_id_idx; Type: INDEX ATTACH; Schema: public; Owner: -
--

ALTER INDEX public.idx_rbl_check_logs_domain ATTACH PARTITION public.rbl_check_logs_2025_12_domain_id_idx;


--
-- Name: rbl_check_logs_2025_12_domain_id_rbl_definition_id_check_ti_idx; Type: INDEX ATTACH; Schema: public; Owner: -
--

ALTER INDEX public.idx_rbl_check_logs_domain_rbl_time ATTACH PARTITION public.rbl_check_logs_2025_12_domain_id_rbl_definition_id_check_ti_idx;


--
-- Name: rbl_check_logs_2025_12_is_listed_idx; Type: INDEX ATTACH; Schema: public; Owner: -
--

ALTER INDEX public.idx_rbl_check_logs_listed ATTACH PARTITION public.rbl_check_logs_2025_12_is_listed_idx;


--
-- Name: rbl_check_logs_2025_12_pkey; Type: INDEX ATTACH; Schema: public; Owner: -
--

ALTER INDEX public.rbl_check_logs_pkey ATTACH PARTITION public.rbl_check_logs_2025_12_pkey;


--
-- Name: rbl_check_logs_2025_12_rbl_definition_id_idx; Type: INDEX ATTACH; Schema: public; Owner: -
--

ALTER INDEX public.idx_rbl_check_logs_rbl ATTACH PARTITION public.rbl_check_logs_2025_12_rbl_definition_id_idx;


--
-- Name: rbl_check_logs_2025_12_tier_idx; Type: INDEX ATTACH; Schema: public; Owner: -
--

ALTER INDEX public.idx_rbl_check_logs_tier ATTACH PARTITION public.rbl_check_logs_2025_12_tier_idx;


--
-- Name: rbl_check_logs_2026_01_check_run_id_idx; Type: INDEX ATTACH; Schema: public; Owner: -
--

ALTER INDEX public.idx_rbl_check_logs_check_run_id ATTACH PARTITION public.rbl_check_logs_2026_01_check_run_id_idx;


--
-- Name: rbl_check_logs_2026_01_check_timestamp_idx; Type: INDEX ATTACH; Schema: public; Owner: -
--

ALTER INDEX public.idx_rbl_check_logs_timestamp ATTACH PARTITION public.rbl_check_logs_2026_01_check_timestamp_idx;


--
-- Name: rbl_check_logs_2026_01_domain_id_check_timestamp_idx; Type: INDEX ATTACH; Schema: public; Owner: -
--

ALTER INDEX public.idx_rbl_check_logs_domain_timestamp ATTACH PARTITION public.rbl_check_logs_2026_01_domain_id_check_timestamp_idx;


--
-- Name: rbl_check_logs_2026_01_domain_id_idx; Type: INDEX ATTACH; Schema: public; Owner: -
--

ALTER INDEX public.idx_rbl_check_logs_domain ATTACH PARTITION public.rbl_check_logs_2026_01_domain_id_idx;


--
-- Name: rbl_check_logs_2026_01_domain_id_rbl_definition_id_check_ti_idx; Type: INDEX ATTACH; Schema: public; Owner: -
--

ALTER INDEX public.idx_rbl_check_logs_domain_rbl_time ATTACH PARTITION public.rbl_check_logs_2026_01_domain_id_rbl_definition_id_check_ti_idx;


--
-- Name: rbl_check_logs_2026_01_is_listed_idx; Type: INDEX ATTACH; Schema: public; Owner: -
--

ALTER INDEX public.idx_rbl_check_logs_listed ATTACH PARTITION public.rbl_check_logs_2026_01_is_listed_idx;


--
-- Name: rbl_check_logs_2026_01_pkey; Type: INDEX ATTACH; Schema: public; Owner: -
--

ALTER INDEX public.rbl_check_logs_pkey ATTACH PARTITION public.rbl_check_logs_2026_01_pkey;


--
-- Name: rbl_check_logs_2026_01_rbl_definition_id_idx; Type: INDEX ATTACH; Schema: public; Owner: -
--

ALTER INDEX public.idx_rbl_check_logs_rbl ATTACH PARTITION public.rbl_check_logs_2026_01_rbl_definition_id_idx;


--
-- Name: rbl_check_logs_2026_01_tier_idx; Type: INDEX ATTACH; Schema: public; Owner: -
--

ALTER INDEX public.idx_rbl_check_logs_tier ATTACH PARTITION public.rbl_check_logs_2026_01_tier_idx;


--
-- Name: rbl_check_logs_2026_02_check_run_id_idx; Type: INDEX ATTACH; Schema: public; Owner: -
--

ALTER INDEX public.idx_rbl_check_logs_check_run_id ATTACH PARTITION public.rbl_check_logs_2026_02_check_run_id_idx;


--
-- Name: rbl_check_logs_2026_02_check_timestamp_idx; Type: INDEX ATTACH; Schema: public; Owner: -
--

ALTER INDEX public.idx_rbl_check_logs_timestamp ATTACH PARTITION public.rbl_check_logs_2026_02_check_timestamp_idx;


--
-- Name: rbl_check_logs_2026_02_domain_id_check_timestamp_idx; Type: INDEX ATTACH; Schema: public; Owner: -
--

ALTER INDEX public.idx_rbl_check_logs_domain_timestamp ATTACH PARTITION public.rbl_check_logs_2026_02_domain_id_check_timestamp_idx;


--
-- Name: rbl_check_logs_2026_02_domain_id_idx; Type: INDEX ATTACH; Schema: public; Owner: -
--

ALTER INDEX public.idx_rbl_check_logs_domain ATTACH PARTITION public.rbl_check_logs_2026_02_domain_id_idx;


--
-- Name: rbl_check_logs_2026_02_domain_id_rbl_definition_id_check_ti_idx; Type: INDEX ATTACH; Schema: public; Owner: -
--

ALTER INDEX public.idx_rbl_check_logs_domain_rbl_time ATTACH PARTITION public.rbl_check_logs_2026_02_domain_id_rbl_definition_id_check_ti_idx;


--
-- Name: rbl_check_logs_2026_02_is_listed_idx; Type: INDEX ATTACH; Schema: public; Owner: -
--

ALTER INDEX public.idx_rbl_check_logs_listed ATTACH PARTITION public.rbl_check_logs_2026_02_is_listed_idx;


--
-- Name: rbl_check_logs_2026_02_pkey; Type: INDEX ATTACH; Schema: public; Owner: -
--

ALTER INDEX public.rbl_check_logs_pkey ATTACH PARTITION public.rbl_check_logs_2026_02_pkey;


--
-- Name: rbl_check_logs_2026_02_rbl_definition_id_idx; Type: INDEX ATTACH; Schema: public; Owner: -
--

ALTER INDEX public.idx_rbl_check_logs_rbl ATTACH PARTITION public.rbl_check_logs_2026_02_rbl_definition_id_idx;


--
-- Name: rbl_check_logs_2026_02_tier_idx; Type: INDEX ATTACH; Schema: public; Owner: -
--

ALTER INDEX public.idx_rbl_check_logs_tier ATTACH PARTITION public.rbl_check_logs_2026_02_tier_idx;


--
-- Name: rbl_check_logs_2026_03_check_run_id_idx; Type: INDEX ATTACH; Schema: public; Owner: -
--

ALTER INDEX public.idx_rbl_check_logs_check_run_id ATTACH PARTITION public.rbl_check_logs_2026_03_check_run_id_idx;


--
-- Name: rbl_check_logs_2026_03_check_timestamp_idx; Type: INDEX ATTACH; Schema: public; Owner: -
--

ALTER INDEX public.idx_rbl_check_logs_timestamp ATTACH PARTITION public.rbl_check_logs_2026_03_check_timestamp_idx;


--
-- Name: rbl_check_logs_2026_03_domain_id_check_timestamp_idx; Type: INDEX ATTACH; Schema: public; Owner: -
--

ALTER INDEX public.idx_rbl_check_logs_domain_timestamp ATTACH PARTITION public.rbl_check_logs_2026_03_domain_id_check_timestamp_idx;


--
-- Name: rbl_check_logs_2026_03_domain_id_idx; Type: INDEX ATTACH; Schema: public; Owner: -
--

ALTER INDEX public.idx_rbl_check_logs_domain ATTACH PARTITION public.rbl_check_logs_2026_03_domain_id_idx;


--
-- Name: rbl_check_logs_2026_03_domain_id_rbl_definition_id_check_ti_idx; Type: INDEX ATTACH; Schema: public; Owner: -
--

ALTER INDEX public.idx_rbl_check_logs_domain_rbl_time ATTACH PARTITION public.rbl_check_logs_2026_03_domain_id_rbl_definition_id_check_ti_idx;


--
-- Name: rbl_check_logs_2026_03_is_listed_idx; Type: INDEX ATTACH; Schema: public; Owner: -
--

ALTER INDEX public.idx_rbl_check_logs_listed ATTACH PARTITION public.rbl_check_logs_2026_03_is_listed_idx;


--
-- Name: rbl_check_logs_2026_03_pkey; Type: INDEX ATTACH; Schema: public; Owner: -
--

ALTER INDEX public.rbl_check_logs_pkey ATTACH PARTITION public.rbl_check_logs_2026_03_pkey;


--
-- Name: rbl_check_logs_2026_03_rbl_definition_id_idx; Type: INDEX ATTACH; Schema: public; Owner: -
--

ALTER INDEX public.idx_rbl_check_logs_rbl ATTACH PARTITION public.rbl_check_logs_2026_03_rbl_definition_id_idx;


--
-- Name: rbl_check_logs_2026_03_tier_idx; Type: INDEX ATTACH; Schema: public; Owner: -
--

ALTER INDEX public.idx_rbl_check_logs_tier ATTACH PARTITION public.rbl_check_logs_2026_03_tier_idx;


--
-- Name: vw_prefect_check_history _RETURN; Type: RULE; Schema: public; Owner: -
--

CREATE OR REPLACE VIEW public.vw_prefect_check_history AS
 SELECT rcr.id AS run_id,
    rcr.prefect_flow_run_id,
    rcr.prefect_flow_name,
    rcr.prefect_deployment_id,
    rcr.run_type,
    rcr.total_ips_checked,
    rcr.started_at,
    rcr.completed_at,
    rcr.status,
    (EXTRACT(epoch FROM (rcr.completed_at - rcr.started_at)) / (60)::numeric) AS duration_minutes,
    count(dcr.id) AS results_count,
    avg(dcr.health_score) AS avg_health_score,
    (((sum(
        CASE
            WHEN dcr.is_clean THEN 1
            ELSE 0
        END))::double precision / (NULLIF(count(dcr.id), 0))::double precision) * (100)::double precision) AS clean_percentage
   FROM (public.rbl_check_runs rcr
     LEFT JOIN public.domain_check_results dcr ON ((dcr.run_id = rcr.id)))
  GROUP BY rcr.id
  ORDER BY rcr.started_at DESC;


--
-- Name: campaign_inboxes trg_campaign_inboxes_updated_at; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER trg_campaign_inboxes_updated_at BEFORE UPDATE ON public.campaign_inboxes FOR EACH ROW EXECUTE FUNCTION public.update_campaign_inboxes_updated_at();


--
-- Name: sender_accounts trg_log_inbox_kill; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER trg_log_inbox_kill AFTER UPDATE OF inbox_state ON public.sender_accounts FOR EACH ROW EXECUTE FUNCTION public.log_inbox_kill_event();


--
-- Name: sender_accounts trg_update_domain_health; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER trg_update_domain_health AFTER INSERT OR DELETE OR UPDATE OF inbox_state, domain_id ON public.sender_accounts FOR EACH ROW EXECUTE FUNCTION public.update_domain_health_on_inbox_change();


--
-- Name: domains trg_update_domain_lifecycle; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER trg_update_domain_lifecycle BEFORE INSERT OR UPDATE ON public.domains FOR EACH ROW EXECUTE FUNCTION public.update_domain_lifecycle_stage();


--
-- Name: domain_check_results trg_update_monitored_domain_from_check; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER trg_update_monitored_domain_from_check AFTER INSERT ON public.domain_check_results FOR EACH ROW EXECUTE FUNCTION public.update_monitored_domain_from_check();


--
-- Name: clients trigger_clients_updated; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER trigger_clients_updated BEFORE UPDATE ON public.clients FOR EACH ROW EXECUTE FUNCTION public.update_updated_at();


--
-- Name: leads trigger_leads_updated; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER trigger_leads_updated BEFORE UPDATE ON public.leads FOR EACH ROW EXECUTE FUNCTION public.update_updated_at();


--
-- Name: projects trigger_projects_updated; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER trigger_projects_updated BEFORE UPDATE ON public.projects FOR EACH ROW EXECUTE FUNCTION public.update_updated_at();


--
-- Name: client_onboarding_submissions trigger_update_client_onboarding; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER trigger_update_client_onboarding AFTER UPDATE ON public.client_onboarding_submissions FOR EACH ROW EXECUTE FUNCTION public.update_client_onboarding_status();


--
-- Name: campaign_snapshots update_campaign_last_snapshot_trigger; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER update_campaign_last_snapshot_trigger AFTER INSERT ON public.campaign_snapshots FOR EACH ROW EXECUTE FUNCTION public.update_campaign_last_snapshot();


--
-- Name: domain_check_summary update_domain_latest_health_trigger; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER update_domain_latest_health_trigger AFTER INSERT ON public.domain_check_summary FOR EACH ROW EXECUTE FUNCTION public.update_domain_latest_health();


--
-- Name: domains update_domains_updated_at; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER update_domains_updated_at BEFORE UPDATE ON public.domains FOR EACH ROW EXECUTE FUNCTION public.update_updated_at_column();


--
-- Name: emailbison_campaigns update_emailbison_campaigns_updated_at; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER update_emailbison_campaigns_updated_at BEFORE UPDATE ON public.emailbison_campaigns FOR EACH ROW EXECUTE FUNCTION public.update_updated_at_column();


--
-- Name: emailbison_instances update_emailbison_instances_updated_at; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER update_emailbison_instances_updated_at BEFORE UPDATE ON public.emailbison_instances FOR EACH ROW EXECUTE FUNCTION public.update_updated_at_column();


--
-- Name: client_onboarding_submissions update_onboarding_submissions_updated_at; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER update_onboarding_submissions_updated_at BEFORE UPDATE ON public.client_onboarding_submissions FOR EACH ROW EXECUTE FUNCTION public.update_updated_at_column();


--
-- Name: rbl_definitions update_rbl_definitions_updated_at; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER update_rbl_definitions_updated_at BEFORE UPDATE ON public.rbl_definitions FOR EACH ROW EXECUTE FUNCTION public.update_updated_at_column();


--
-- Name: sender_accounts update_sender_accounts_updated_at; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER update_sender_accounts_updated_at BEFORE UPDATE ON public.sender_accounts FOR EACH ROW EXECUTE FUNCTION public.update_updated_at_column();


--
-- Name: warmup_check_runs update_warmup_check_runs_updated_at; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER update_warmup_check_runs_updated_at BEFORE UPDATE ON public.warmup_check_runs FOR EACH ROW EXECUTE FUNCTION public.update_updated_at_column();


--
-- Name: domains update_workspace_domain_count_trigger; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER update_workspace_domain_count_trigger AFTER INSERT OR DELETE OR UPDATE ON public.domains FOR EACH ROW EXECUTE FUNCTION public.update_workspace_domain_count();


--
-- Name: sender_accounts update_workspace_sender_count_trigger; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER update_workspace_sender_count_trigger AFTER INSERT OR DELETE OR UPDATE ON public.sender_accounts FOR EACH ROW EXECUTE FUNCTION public.update_workspace_sender_count();


--
-- Name: workspaces update_workspaces_updated_at; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER update_workspaces_updated_at BEFORE UPDATE ON public.workspaces FOR EACH ROW EXECUTE FUNCTION public.update_updated_at_column();


--
-- Name: users users_updated_at_trigger; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER users_updated_at_trigger BEFORE UPDATE ON public.users FOR EACH ROW EXECUTE FUNCTION public.update_updated_at_column();


--
-- Name: campaign_cycles campaign_cycles_client_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.campaign_cycles
    ADD CONSTRAINT campaign_cycles_client_id_fkey FOREIGN KEY (client_id) REFERENCES public.clients(id);


--
-- Name: campaign_cycles campaign_cycles_strategy_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.campaign_cycles
    ADD CONSTRAINT campaign_cycles_strategy_id_fkey FOREIGN KEY (strategy_id) REFERENCES public.strategies(id);


--
-- Name: campaign_documents campaign_documents_client_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.campaign_documents
    ADD CONSTRAINT campaign_documents_client_id_fkey FOREIGN KEY (client_id) REFERENCES public.clients(id) ON DELETE CASCADE;


--
-- Name: campaign_documents campaign_documents_job_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.campaign_documents
    ADD CONSTRAINT campaign_documents_job_id_fkey FOREIGN KEY (job_id) REFERENCES public.strategy_generation_jobs(id) ON DELETE CASCADE;


--
-- Name: campaign_documents campaign_documents_strategy_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.campaign_documents
    ADD CONSTRAINT campaign_documents_strategy_id_fkey FOREIGN KEY (strategy_id) REFERENCES public.strategies(id) ON DELETE SET NULL;


--
-- Name: campaign_events campaign_events_campaign_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.campaign_events
    ADD CONSTRAINT campaign_events_campaign_id_fkey FOREIGN KEY (campaign_id) REFERENCES public.emailbison_campaigns(id) ON DELETE CASCADE;


--
-- Name: campaign_events campaign_events_sender_account_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.campaign_events
    ADD CONSTRAINT campaign_events_sender_account_id_fkey FOREIGN KEY (sender_account_id) REFERENCES public.sender_accounts(id) ON DELETE SET NULL;


--
-- Name: campaign_inboxes campaign_inboxes_campaign_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.campaign_inboxes
    ADD CONSTRAINT campaign_inboxes_campaign_id_fkey FOREIGN KEY (campaign_id) REFERENCES public.emailbison_campaigns(id) ON DELETE CASCADE;


--
-- Name: campaign_inboxes campaign_inboxes_sender_account_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.campaign_inboxes
    ADD CONSTRAINT campaign_inboxes_sender_account_id_fkey FOREIGN KEY (sender_account_id) REFERENCES public.sender_accounts(id) ON DELETE CASCADE;


--
-- Name: campaign_snapshots campaign_snapshots_campaign_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.campaign_snapshots
    ADD CONSTRAINT campaign_snapshots_campaign_id_fkey FOREIGN KEY (campaign_id) REFERENCES public.emailbison_campaigns(id) ON DELETE CASCADE;


--
-- Name: client_onboarding_submissions client_onboarding_submissions_client_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.client_onboarding_submissions
    ADD CONSTRAINT client_onboarding_submissions_client_id_fkey FOREIGN KEY (client_id) REFERENCES public.clients(id) ON DELETE CASCADE;


--
-- Name: client_personas client_personas_submission_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.client_personas
    ADD CONSTRAINT client_personas_submission_id_fkey FOREIGN KEY (submission_id) REFERENCES public.client_onboarding_submissions(id) ON DELETE CASCADE;


--
-- Name: client_segments client_segments_submission_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.client_segments
    ADD CONSTRAINT client_segments_submission_id_fkey FOREIGN KEY (submission_id) REFERENCES public.client_onboarding_submissions(id) ON DELETE CASCADE;


--
-- Name: client_subscriptions client_subscriptions_client_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.client_subscriptions
    ADD CONSTRAINT client_subscriptions_client_id_fkey FOREIGN KEY (client_id) REFERENCES public.clients(id) ON DELETE CASCADE;


--
-- Name: client_subscriptions client_subscriptions_package_template_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.client_subscriptions
    ADD CONSTRAINT client_subscriptions_package_template_id_fkey FOREIGN KEY (package_template_id) REFERENCES public.package_templates(id);


--
-- Name: clients clients_workspace_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.clients
    ADD CONSTRAINT clients_workspace_id_fkey FOREIGN KEY (workspace_id) REFERENCES public.workspaces(id) ON DELETE SET NULL;


--
-- Name: cost_logs cost_logs_company_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.cost_logs
    ADD CONSTRAINT cost_logs_company_id_fkey FOREIGN KEY (company_id) REFERENCES public.companies(id) ON DELETE SET NULL;


--
-- Name: cost_logs cost_logs_person_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.cost_logs
    ADD CONSTRAINT cost_logs_person_id_fkey FOREIGN KEY (person_id) REFERENCES public.persons(id) ON DELETE SET NULL;


--
-- Name: cost_logs cost_logs_project_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.cost_logs
    ADD CONSTRAINT cost_logs_project_id_fkey FOREIGN KEY (project_id) REFERENCES public.projects(id) ON DELETE SET NULL;


--
-- Name: document_email_variants document_email_variants_document_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.document_email_variants
    ADD CONSTRAINT document_email_variants_document_id_fkey FOREIGN KEY (document_id) REFERENCES public.campaign_documents(id) ON DELETE CASCADE;


--
-- Name: document_subject_options document_subject_options_document_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.document_subject_options
    ADD CONSTRAINT document_subject_options_document_id_fkey FOREIGN KEY (document_id) REFERENCES public.campaign_documents(id) ON DELETE CASCADE;


--
-- Name: domain_check_results domain_check_results_run_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.domain_check_results
    ADD CONSTRAINT domain_check_results_run_id_fkey FOREIGN KEY (run_id) REFERENCES public.rbl_check_runs(id) ON DELETE CASCADE;


--
-- Name: domain_check_summary domain_check_summary_check_run_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.domain_check_summary
    ADD CONSTRAINT domain_check_summary_check_run_id_fkey FOREIGN KEY (check_run_id) REFERENCES public.rbl_check_runs(id) ON DELETE SET NULL;


--
-- Name: domain_check_summary domain_check_summary_domain_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.domain_check_summary
    ADD CONSTRAINT domain_check_summary_domain_id_fkey FOREIGN KEY (domain_id) REFERENCES public.domains(id) ON DELETE CASCADE;


--
-- Name: domain_generation_jobs domain_generation_jobs_client_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.domain_generation_jobs
    ADD CONSTRAINT domain_generation_jobs_client_id_fkey FOREIGN KEY (client_id) REFERENCES public.clients(id);


--
-- Name: domain_price_history domain_price_history_domain_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.domain_price_history
    ADD CONSTRAINT domain_price_history_domain_id_fkey FOREIGN KEY (domain_id) REFERENCES public.domains(id) ON DELETE CASCADE;


--
-- Name: domain_purchase_queue domain_purchase_queue_domain_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.domain_purchase_queue
    ADD CONSTRAINT domain_purchase_queue_domain_id_fkey FOREIGN KEY (domain_id) REFERENCES public.domains(id) ON DELETE CASCADE;


--
-- Name: domains domains_purchase_job_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.domains
    ADD CONSTRAINT domains_purchase_job_id_fkey FOREIGN KEY (purchase_job_id) REFERENCES public.inbox_purchase_jobs(id);


--
-- Name: domains domains_workspace_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.domains
    ADD CONSTRAINT domains_workspace_id_fkey FOREIGN KEY (workspace_id) REFERENCES public.workspaces(id) ON DELETE CASCADE;


--
-- Name: emailbison_campaigns emailbison_campaigns_workspace_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.emailbison_campaigns
    ADD CONSTRAINT emailbison_campaigns_workspace_id_fkey FOREIGN KEY (workspace_id) REFERENCES public.workspaces(id) ON DELETE CASCADE;


--
-- Name: sender_accounts fk_sender_accounts_domain; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sender_accounts
    ADD CONSTRAINT fk_sender_accounts_domain FOREIGN KEY (domain_id) REFERENCES public.domains(id) ON DELETE SET NULL;


--
-- Name: health_events health_events_workspace_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.health_events
    ADD CONSTRAINT health_events_workspace_id_fkey FOREIGN KEY (workspace_id) REFERENCES public.workspaces(id) ON DELETE CASCADE;


--
-- Name: inbox_deletion_log inbox_deletion_log_check_run_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.inbox_deletion_log
    ADD CONSTRAINT inbox_deletion_log_check_run_id_fkey FOREIGN KEY (check_run_id) REFERENCES public.warmup_check_runs(id) ON DELETE SET NULL;


--
-- Name: inbox_deletion_log inbox_deletion_log_workspace_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.inbox_deletion_log
    ADD CONSTRAINT inbox_deletion_log_workspace_id_fkey FOREIGN KEY (workspace_id) REFERENCES public.workspaces(id);


--
-- Name: inbox_health_snapshots inbox_health_snapshots_inbox_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.inbox_health_snapshots
    ADD CONSTRAINT inbox_health_snapshots_inbox_id_fkey FOREIGN KEY (inbox_id) REFERENCES public.sender_accounts(id) ON DELETE CASCADE;


--
-- Name: inbox_health_snapshots inbox_health_snapshots_workspace_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.inbox_health_snapshots
    ADD CONSTRAINT inbox_health_snapshots_workspace_id_fkey FOREIGN KEY (workspace_id) REFERENCES public.workspaces(id);


--
-- Name: inbox_purchase_jobs inbox_purchase_jobs_client_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.inbox_purchase_jobs
    ADD CONSTRAINT inbox_purchase_jobs_client_id_fkey FOREIGN KEY (client_id) REFERENCES public.clients(id) ON DELETE CASCADE;


--
-- Name: inbox_purchase_jobs inbox_purchase_jobs_workspace_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.inbox_purchase_jobs
    ADD CONSTRAINT inbox_purchase_jobs_workspace_id_fkey FOREIGN KEY (workspace_id) REFERENCES public.workspaces(id);


--
-- Name: inbox_removal_events inbox_removal_events_sender_account_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.inbox_removal_events
    ADD CONSTRAINT inbox_removal_events_sender_account_id_fkey FOREIGN KEY (sender_account_id) REFERENCES public.sender_accounts(id) ON DELETE CASCADE;


--
-- Name: inbox_removal_events inbox_removal_events_workspace_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.inbox_removal_events
    ADD CONSTRAINT inbox_removal_events_workspace_id_fkey FOREIGN KEY (workspace_id) REFERENCES public.workspaces(id) ON DELETE CASCADE;


--
-- Name: inbox_rotation_history inbox_rotation_history_source_inbox_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.inbox_rotation_history
    ADD CONSTRAINT inbox_rotation_history_source_inbox_id_fkey FOREIGN KEY (source_inbox_id) REFERENCES public.sender_accounts(id) ON DELETE SET NULL;


--
-- Name: inbox_rotation_history inbox_rotation_history_target_inbox_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.inbox_rotation_history
    ADD CONSTRAINT inbox_rotation_history_target_inbox_id_fkey FOREIGN KEY (target_inbox_id) REFERENCES public.sender_accounts(id) ON DELETE SET NULL;


--
-- Name: inbox_rotation_history inbox_rotation_history_workspace_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.inbox_rotation_history
    ADD CONSTRAINT inbox_rotation_history_workspace_id_fkey FOREIGN KEY (workspace_id) REFERENCES public.workspaces(id);


--
-- Name: kill_trigger_events kill_trigger_events_domain_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.kill_trigger_events
    ADD CONSTRAINT kill_trigger_events_domain_id_fkey FOREIGN KEY (domain_id) REFERENCES public.domains(id) ON DELETE SET NULL;


--
-- Name: kill_trigger_events kill_trigger_events_inbox_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.kill_trigger_events
    ADD CONSTRAINT kill_trigger_events_inbox_id_fkey FOREIGN KEY (inbox_id) REFERENCES public.sender_accounts(id) ON DELETE SET NULL;


--
-- Name: kill_trigger_events kill_trigger_events_workspace_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.kill_trigger_events
    ADD CONSTRAINT kill_trigger_events_workspace_id_fkey FOREIGN KEY (workspace_id) REFERENCES public.workspaces(id);


--
-- Name: kill_triggers kill_triggers_workspace_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.kill_triggers
    ADD CONSTRAINT kill_triggers_workspace_id_fkey FOREIGN KEY (workspace_id) REFERENCES public.workspaces(id) ON DELETE CASCADE;


--
-- Name: layer_outputs layer_outputs_project_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.layer_outputs
    ADD CONSTRAINT layer_outputs_project_id_fkey FOREIGN KEY (project_id) REFERENCES public.projects(id) ON DELETE CASCADE;


--
-- Name: lead_pull_jobs lead_pull_jobs_client_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.lead_pull_jobs
    ADD CONSTRAINT lead_pull_jobs_client_id_fkey FOREIGN KEY (client_id) REFERENCES public.clients(id);


--
-- Name: lead_pull_jobs lead_pull_jobs_submission_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.lead_pull_jobs
    ADD CONSTRAINT lead_pull_jobs_submission_id_fkey FOREIGN KEY (submission_id) REFERENCES public.client_onboarding_submissions(id);


--
-- Name: lead_pull_jobs lead_pull_jobs_suggestion_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.lead_pull_jobs
    ADD CONSTRAINT lead_pull_jobs_suggestion_id_fkey FOREIGN KEY (suggestion_id) REFERENCES public.strategy_suggestions(id);


--
-- Name: leads leads_project_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.leads
    ADD CONSTRAINT leads_project_id_fkey FOREIGN KEY (project_id) REFERENCES public.projects(id) ON DELETE CASCADE;


--
-- Name: list_segments list_segments_workspace_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.list_segments
    ADD CONSTRAINT list_segments_workspace_id_fkey FOREIGN KEY (workspace_id) REFERENCES public.workspaces(id) ON DELETE CASCADE;


--
-- Name: persons persons_company_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.persons
    ADD CONSTRAINT persons_company_id_fkey FOREIGN KEY (company_id) REFERENCES public.companies(id) ON DELETE CASCADE;


--
-- Name: placement_tests placement_tests_sender_account_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.placement_tests
    ADD CONSTRAINT placement_tests_sender_account_id_fkey FOREIGN KEY (sender_account_id) REFERENCES public.sender_accounts(id) ON DELETE CASCADE;


--
-- Name: predicted_emails predicted_emails_company_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.predicted_emails
    ADD CONSTRAINT predicted_emails_company_id_fkey FOREIGN KEY (company_id) REFERENCES public.companies(id) ON DELETE CASCADE;


--
-- Name: predicted_emails predicted_emails_person_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.predicted_emails
    ADD CONSTRAINT predicted_emails_person_id_fkey FOREIGN KEY (person_id) REFERENCES public.persons(id) ON DELETE CASCADE;


--
-- Name: projects projects_client_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.projects
    ADD CONSTRAINT projects_client_id_fkey FOREIGN KEY (client_id) REFERENCES public.clients(id) ON DELETE CASCADE;


--
-- Name: purchase_job_steps purchase_job_steps_job_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.purchase_job_steps
    ADD CONSTRAINT purchase_job_steps_job_id_fkey FOREIGN KEY (job_id) REFERENCES public.inbox_purchase_jobs(id) ON DELETE CASCADE;


--
-- Name: rbl_check_logs rbl_check_logs_check_run_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE public.rbl_check_logs
    ADD CONSTRAINT rbl_check_logs_check_run_id_fkey FOREIGN KEY (check_run_id) REFERENCES public.rbl_check_runs(id) ON DELETE SET NULL;


--
-- Name: rbl_check_logs rbl_check_logs_domain_fk; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE public.rbl_check_logs
    ADD CONSTRAINT rbl_check_logs_domain_fk FOREIGN KEY (domain_id) REFERENCES public.domains(id) ON DELETE CASCADE;


--
-- Name: rbl_check_logs rbl_check_logs_rbl_definition_fk; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE public.rbl_check_logs
    ADD CONSTRAINT rbl_check_logs_rbl_definition_fk FOREIGN KEY (rbl_definition_id) REFERENCES public.rbl_definitions(id) ON DELETE CASCADE;


--
-- Name: reviews reviews_layer_output_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.reviews
    ADD CONSTRAINT reviews_layer_output_id_fkey FOREIGN KEY (layer_output_id) REFERENCES public.layer_outputs(id) ON DELETE CASCADE;


--
-- Name: sender_accounts sender_accounts_last_check_run_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sender_accounts
    ADD CONSTRAINT sender_accounts_last_check_run_id_fkey FOREIGN KEY (last_check_run_id) REFERENCES public.warmup_check_runs(id) ON DELETE SET NULL;


--
-- Name: sender_accounts sender_accounts_workspace_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sender_accounts
    ADD CONSTRAINT sender_accounts_workspace_id_fkey FOREIGN KEY (workspace_id) REFERENCES public.workspaces(id) ON DELETE CASCADE;


--
-- Name: sender_warmup_snapshots sender_warmup_snapshots_sender_account_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sender_warmup_snapshots
    ADD CONSTRAINT sender_warmup_snapshots_sender_account_id_fkey FOREIGN KEY (sender_account_id) REFERENCES public.sender_accounts(id) ON DELETE CASCADE;


--
-- Name: strategies strategies_client_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.strategies
    ADD CONSTRAINT strategies_client_id_fkey FOREIGN KEY (client_id) REFERENCES public.clients(id);


--
-- Name: strategy_generation_jobs strategy_generation_jobs_client_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.strategy_generation_jobs
    ADD CONSTRAINT strategy_generation_jobs_client_id_fkey FOREIGN KEY (client_id) REFERENCES public.clients(id);


--
-- Name: strategy_generation_jobs strategy_generation_jobs_revision_of_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.strategy_generation_jobs
    ADD CONSTRAINT strategy_generation_jobs_revision_of_fkey FOREIGN KEY (revision_of) REFERENCES public.strategy_suggestions(id);


--
-- Name: strategy_generation_jobs strategy_generation_jobs_strategy_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.strategy_generation_jobs
    ADD CONSTRAINT strategy_generation_jobs_strategy_id_fkey FOREIGN KEY (strategy_id) REFERENCES public.strategies(id);


--
-- Name: strategy_revision_requests strategy_revision_requests_client_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.strategy_revision_requests
    ADD CONSTRAINT strategy_revision_requests_client_id_fkey FOREIGN KEY (client_id) REFERENCES public.clients(id);


--
-- Name: strategy_revision_requests strategy_revision_requests_job_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.strategy_revision_requests
    ADD CONSTRAINT strategy_revision_requests_job_id_fkey FOREIGN KEY (job_id) REFERENCES public.strategy_generation_jobs(id);


--
-- Name: strategy_revision_requests strategy_revision_requests_variant_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.strategy_revision_requests
    ADD CONSTRAINT strategy_revision_requests_variant_id_fkey FOREIGN KEY (variant_id) REFERENCES public.strategy_suggestions(id);


--
-- Name: strategy_suggestions strategy_suggestions_client_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.strategy_suggestions
    ADD CONSTRAINT strategy_suggestions_client_id_fkey FOREIGN KEY (client_id) REFERENCES public.clients(id);


--
-- Name: strategy_suggestions strategy_suggestions_cycle_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.strategy_suggestions
    ADD CONSTRAINT strategy_suggestions_cycle_id_fkey FOREIGN KEY (cycle_id) REFERENCES public.campaign_cycles(id);


--
-- Name: strategy_suggestions strategy_suggestions_document_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.strategy_suggestions
    ADD CONSTRAINT strategy_suggestions_document_id_fkey FOREIGN KEY (document_id) REFERENCES public.campaign_documents(id) ON DELETE SET NULL;


--
-- Name: strategy_suggestions strategy_suggestions_job_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.strategy_suggestions
    ADD CONSTRAINT strategy_suggestions_job_id_fkey FOREIGN KEY (job_id) REFERENCES public.strategy_generation_jobs(id);


--
-- Name: strategy_suggestions strategy_suggestions_original_suggestion_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.strategy_suggestions
    ADD CONSTRAINT strategy_suggestions_original_suggestion_id_fkey FOREIGN KEY (original_suggestion_id) REFERENCES public.strategy_suggestions(id);


--
-- Name: strategy_suggestions strategy_suggestions_previous_version_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.strategy_suggestions
    ADD CONSTRAINT strategy_suggestions_previous_version_id_fkey FOREIGN KEY (previous_version_id) REFERENCES public.strategy_suggestions(id);


--
-- Name: strategy_suggestions strategy_suggestions_strategy_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.strategy_suggestions
    ADD CONSTRAINT strategy_suggestions_strategy_id_fkey FOREIGN KEY (strategy_id) REFERENCES public.strategies(id);


--
-- Name: subscription_changes subscription_changes_subscription_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.subscription_changes
    ADD CONSTRAINT subscription_changes_subscription_id_fkey FOREIGN KEY (subscription_id) REFERENCES public.client_subscriptions(id) ON DELETE CASCADE;


--
-- Name: tier_check_summaries tier_check_summaries_check_run_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.tier_check_summaries
    ADD CONSTRAINT tier_check_summaries_check_run_id_fkey FOREIGN KEY (check_run_id) REFERENCES public.rbl_check_runs(id) ON DELETE CASCADE;


--
-- Name: transcripts transcripts_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.transcripts
    ADD CONSTRAINT transcripts_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;


--
-- Name: webhook_logs webhook_logs_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.webhook_logs
    ADD CONSTRAINT webhook_logs_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE SET NULL;


--
-- Name: workspace_check_summary workspace_check_summary_run_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.workspace_check_summary
    ADD CONSTRAINT workspace_check_summary_run_id_fkey FOREIGN KEY (run_id) REFERENCES public.rbl_check_runs(id) ON DELETE CASCADE;


--
-- Name: workspaces workspaces_instance_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.workspaces
    ADD CONSTRAINT workspaces_instance_id_fkey FOREIGN KEY (instance_id) REFERENCES public.emailbison_instances(id) ON DELETE CASCADE;


--
-- Name: oauth_sessions Service role can manage oauth_sessions; Type: POLICY; Schema: public; Owner: -
--

-- CREATE POLICY "Service role can manage oauth_sessions" ON public.oauth_sessions TO service_role USING (true) WITH CHECK (true);


--
-- Name: rbl_check_runs Service role has full access; Type: POLICY; Schema: public; Owner: -
--

-- CREATE POLICY "Service role has full access" ON public.rbl_check_runs TO service_role USING (true);


--
-- Name: oauth_sessions; Type: ROW SECURITY; Schema: public; Owner: -
--

-- RLS disabled for local dev

--
-- Name: rbl_check_runs; Type: ROW SECURITY; Schema: public; Owner: -
--

-- RLS disabled for local dev

--
-- PostgreSQL database dump complete
--

\unrestrict cpVonRaZ5pmXlv1YjfacbSpx0PoaEXnYyIAGsfqCWjdQSaxRgFxo836O8R7C8zM

