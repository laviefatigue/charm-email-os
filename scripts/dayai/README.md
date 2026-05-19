# scripts/dayai/

Reference implementations for the Day.AI -> client-repo onboarding pipeline.

These started as one-off scripts proving the concept on Sammy. They're committed
here so the next session has working code to extend, not just prose.

**Read the handoff first:** `../../docs/dayai/HANDOFF_client_repo_pipeline.md`

## Files

| File | Purpose |
|---|---|
| `synthesize_client_repo.py` | Given a `charm_client_id`, pull Day.AI opp + DB + EB workspace data and render the 5 enriched files (`client.md`, `notes/contacts.md`, `notes/status.md`, `notes/insights.md`, `onboarding/dayai-opp.md`) as text strings. No I/O to GitHub. |
| `onboard_client_repo.py` | Given a slug + rendered files, create (or update) `HireCharm/client-<slug>` via the Charm Onboarder GitHub App. Atomic single-commit via git-data API. |

## Usage (current state — single-client manual)

```bash
# 1. Render the files for a specific client
python scripts/dayai/synthesize_client_repo.py --charm-client-id 4ac7f374-8751-4d89-8017-7dfca23fb5f8

# 2. Push to GitHub (creates repo if missing, otherwise commits to main)
python scripts/dayai/onboard_client_repo.py --slug sammy --from-render
```

(The current scripts are hard-coded to Sammy as proof-of-concept. Parameterize
them before bulk rollout — see TODO at top of each file.)

## What's still hard-coded for Sammy (TODO to parameterize)

- `synthesize_client_repo.py`: client_name, client_slug, client_domain, charm_client_id, eb_workspace_id, opp JSON path
- `onboard_client_repo.py`: target repo name (`client-sammy`), file paths

Replacing these hard-codes with a `charm_client_id`-based lookup is the
mechanical next step before bulk rollout.

## Lookups the scripts perform

| Source | Endpoint / mechanism | Used for |
|---|---|---|
| charm-email-os clients table | `GET /api/clients?page_size=100` (filter by id) | name, workspace_id, package, inbox counts |
| charm-email-os workspaces table | `GET /api/workspaces/{workspace_id}` | `emailbison_workspace_id` (NUMERIC) |
| Day.AI opportunities | `dayai.DayAIClient.list_opportunities_in_stages([...])` or direct `search_objects` with `objectId eq` | opp metadata, relationships, narrative properties (Buyer Voice, Goals, etc.) |
| Charm Onboarder GitHub App | PEM at `d:/Work/Charm/.secrets/charm-onboarder.pem`, App ID 3480661, Install 126503394 | repo creation from template + git-data commits |

## What you should add next

Per the handoff doc's "NEXT STEP" section:

1. `dayai/queries.py` with `meetings_for_organization()` and `meeting_full_context()` helpers
2. `scripts/dayai/sync_meetings_to_client_repo.py` that consumes those helpers and writes to `notes/meetings/YYYY-MM-DD_<slug>.md` in the client repo
3. End-to-end test: clone client-sammy, open in Claude Code, ask agent a question only meetings would answer

Once that works, generalize the pipeline (templating, bulk runner, watcher
wire-up). See handoff §5 for design notes.
