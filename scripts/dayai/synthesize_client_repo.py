#!/usr/bin/env python3
"""
Synthesize the 5 enriched files for a client repo, given a charm_client_id.

REFERENCE IMPLEMENTATION. Currently hard-coded to Sammy as proof-of-concept.

Produces text content for:
  - client.md                  (machine-readable frontmatter + human body)
  - notes/contacts.md          (full roster from Day.AI relationships)
  - notes/status.md            (deal status + risks + next step)
  - notes/insights.md          (buyer voice, goals, decision process, competitors)
  - onboarding/dayai-opp.md    (audit snapshot + raw JSON)

Writes to stdout as a single JSON object keyed by repo path -> file content.
That output is consumed by onboard_client_repo.py which does the GitHub commit.

TODO before bulk rollout:
  - Parameterize CLIENT_NAME, CLIENT_SLUG, CLIENT_DOMAIN, charm_client_id
    (pass as argparse args)
  - Fetch the Day.AI opp by domain (search_objects with domain filter) instead
    of loading from a cached JSON file
  - Fetch the charm-email-os clients row + workspace via API instead of
    hardcoded dict
  - Fetch EmailBison workspace via /api/workspaces/{uuid}
  - Slug normalization rule for names like "Ink'd", "Stable Kernel Market Research"

See ../../docs/dayai/HANDOFF_client_repo_pipeline.md for full design context.
"""
from __future__ import annotations

import datetime
import json
import sys
from typing import Any


# --- HARDCODED FOR SAMMY (parameterize per TODO above) ---

CLIENT_NAME = 'Sammy'
CLIENT_SLUG = 'sammy'
CLIENT_DOMAIN = 'withsammy.ai'

# Charm-email-os clients row — pulled via:
#   curl https://api.wizardgrimoire.cloud/api/clients?page_size=100
CHARM_CLIENT = {
    'id': '4ac7f374-8751-4d89-8017-7dfca23fb5f8',
    'workspace_id': 'bbfee135-bff8-4b02-9270-e7946725ab14',
    'workspace_name': 'Sammy',
    'onboarding_complete': True,
    'created_at': '2026-01-14T20:45:39.245836Z',
    'inbox_count': 661,
    'domain_count': 59,
    'campaign_count': 8,
    'connected_inbox_count': 68,
    'package_inbox_target': 699,
    'package_name': 'Starter',
    'sync_enabled': True,
}

# EmailBison workspace lookup — pulled via:
#   curl https://api.wizardgrimoire.cloud/api/workspaces/<workspace_id>
EB_WORKSPACE = {
    'emailbison_workspace_id': 8,
    'emailbison_workspace_name': 'Sammy',
    'sender_account_count': 661,
}

# Day.AI opp — fetched via dayai.DayAIClient.list_opportunities_in_stages(),
# filtered to objectId == this opp. For Sammy we cached the full JSON to disk.
OPP_JSON_PATH = 'd:/tmp/sammy-opp.json'


def y(key: str, value: Any, comment: str | None = None) -> str:
    """Format a YAML scalar with optional inline comment.

    Numbers / bools / null stay bare; strings get JSON-quoted (handles
    embedded quotes). Lists are inline JSON arrays.
    """
    if value is None or value == '':
        rendered = 'null'
    elif isinstance(value, bool):
        rendered = 'true' if value else 'false'
    elif isinstance(value, (int, float)):
        rendered = str(value)
    elif isinstance(value, list):
        rendered = '[' + ', '.join(json.dumps(v) for v in value) + ']' if value else '[]'
    else:
        rendered = json.dumps(str(value))
    line = f'{key}: {rendered}'
    if comment:
        line += f'  # {comment}'
    return line


def parse_relationships(rels: list[dict], client_domain: str) -> dict:
    """Sort the opp's relationships into client / charm / external / org buckets."""
    primary_org = None
    client_contacts: list[dict] = []
    charm_team: list[dict] = []
    external_contacts: list[dict] = []
    for r in rels:
        otype = r.get('objectType')
        oid = r.get('objectId') or ''
        title = r.get('title')
        verb = r.get('relationship')
        if otype == 'native_organization' and verb == 'is a deal with':
            primary_org = {'id': oid, 'name': title}
        elif otype == 'native_contact' and verb == 'involves person':
            entry = {'email': oid, 'name': title if (title and title != oid) else ''}
            if oid.endswith('@' + client_domain):
                client_contacts.append(entry)
            elif oid.endswith('@hirecharm.com'):
                charm_team.append(entry)
            else:
                external_contacts.append(entry)
    return {
        'primary_org': primary_org,
        'client_contacts': client_contacts,
        'charm_team': charm_team,
        'external_contacts': external_contacts,
    }


def pick_primary_contact(client_contacts: list[dict], role_by_email: dict) -> dict:
    """Heuristic: PRIMARY_CONTACT > CHAMPION/BUYER/DECISION_MAKER > first with real name > first."""
    for c in client_contacts:
        roles = role_by_email.get(c['email'], {}).get('roles', [])
        if 'PRIMARY_CONTACT' in roles:
            return {'name': c['name'] or c['email'].split('@')[0].title(), 'email': c['email'], 'roles': roles}
    for c in client_contacts:
        roles = role_by_email.get(c['email'], {}).get('roles', [])
        if any(r in ('CHAMPION', 'BUYER', 'DECISION_MAKER') for r in roles):
            return {'name': c['name'] or c['email'].split('@')[0].title(), 'email': c['email'], 'roles': roles}
    for c in client_contacts:
        if c['name']:
            return {'name': c['name'], 'email': c['email'], 'roles': []}
    if client_contacts:
        c = client_contacts[0]
        return {'name': c['email'].split('@')[0].title(), 'email': c['email'], 'roles': []}
    return {'name': '', 'email': '', 'roles': []}


def render_client_md(
    client_name: str,
    client_slug: str,
    client_domain: str,
    charm_client: dict,
    eb_workspace: dict,
    opp: dict,
    parsed_rels: dict,
    primary_contact: dict,
    today: str,
) -> str:
    """Render the canonical client.md (YAML frontmatter + human body)."""
    props = opp.get('properties', {})
    primary_org = parsed_rels['primary_org'] or {}
    org_name = primary_org.get('name') or ''
    org_id = primary_org.get('id') or ''
    onboarded_date = charm_client['created_at'].split('T')[0]
    close_date = (props.get('Close Date') or '').split('T')[0]
    last_contacted = (props.get('Last Contacted') or '').split('T')[0]
    next_step = (props.get('Next Step') or '').split('T')[0]
    owner_email = props.get('ownerEmail') or ''
    owner_user_id = props.get('ownerId') or ''
    charm_ae_name = next(
        (c['name'] for c in parsed_rels['charm_team'] if c['email'] == owner_email and c['name']),
        '',
    )

    fm = [
        '---',
        '# Foam metadata',
        y('name', client_name),
        y('type', 'client-card'),
        y('status', 'active'),
        y('created', onboarded_date),
        'related: ["[[CLAUDE]]", "[[README]]", "[[contacts]]", "[[status]]", "[[insights]]", "[[dayai-opp]]"]',
        '',
        '# Identity (seeds for downstream automation: workspace naming, domain generation)',
        y('slug', client_slug),
        y('domain', client_domain, 'primary client domain; seed for similar-domain generation'),
        y('organization_name', org_name, 'legal entity name from Day.AI'),
        '',
        '# Charm OS IDs (UUID strings — use for clients/workspaces table joins)',
        y('charm_client_id', charm_client['id']),
        y('charm_workspace_id', charm_client['workspace_id']),
        '',
        '# EmailBison (numeric ID — used in EB API URLs)',
        y('emailbison_workspace_id', eb_workspace['emailbison_workspace_id']),
        y('emailbison_workspace_name', eb_workspace['emailbison_workspace_name']),
        y('emailbison_sender_account_count', eb_workspace['sender_account_count']),
        '',
        '# Day.AI (UUID strings)',
        y('dayai_opp_id', opp.get('objectId')),
        y('dayai_organization_id', org_id, 'Day.AI uses domain as objectId for orgs in many cases'),
        y('dayai_owner_user_id', owner_user_id, 'Charm AE Day.AI user UUID (matches roles.OWNER_EMAIL)'),
        y('dayai_owner_email', owner_email),
        '',
        '# Dates (ISO 8601)',
        y('closed_won_date', close_date),
        y('onboarded_date', onboarded_date),
        y('last_contacted_date', last_contacted),
        y('next_step_date', next_step),
        '',
        '# Primary contact (parsed from Day.AI roles array)',
        y('primary_contact_name', primary_contact['name']),
        y('primary_contact_email', primary_contact['email']),
        y('primary_contact_roles', primary_contact['roles']),
        '',
        '# Charm OS package state (clients row)',
        y('package_name', charm_client['package_name']),
        y('package_inbox_target', charm_client['package_inbox_target']),
        y('inbox_count', charm_client['inbox_count']),
        y('connected_inbox_count', charm_client['connected_inbox_count']),
        y('domain_count', charm_client['domain_count']),
        y('campaign_count', charm_client['campaign_count']),
        y('sync_enabled', charm_client['sync_enabled']),
        '',
        '# Slack / Hypertide / dashboard (filled later; keys exist for parsers)',
        y('slack_client_channel_id', None),
        y('slack_notifications_channel_id', None),
        y('hypertide_workspace_ref', None),
        y('custom_dashboard_url', None),
        '',
        '# Template provenance',
        y('template_version', '0.4'),
        y('last_synced', today),
        '---',
        '',
    ]

    body = f"""# {client_name} — Client Card

> Reference card. Frontmatter is machine-readable — any script can `import yaml`
> and pull IDs directly. Body is for humans. Update fields when facts change.
> Keys above must remain present (use `null` if the value does not apply yet).

## Identity
- **Name:** {client_name}
- **Slug:** `{client_slug}`
- **Domain:** {client_domain}
- **Organization:** {org_name or 'n/a'}
- **Closed Won:** {close_date or 'n/a'}
- **Onboarded in Charm:** {onboarded_date}

## Charm OS
- **Charm client ID:** `{charm_client['id']}`
- **Charm workspace ID (local UUID):** `{charm_client['workspace_id']}`
- **Workspace name:** {charm_client['workspace_name']}
- **Package:** {charm_client['package_name']} — target {charm_client['package_inbox_target']} inboxes
- **Inboxes:** {charm_client['inbox_count']} total / {charm_client['connected_inbox_count']} connected
- **Domains:** {charm_client['domain_count']}
- **Campaigns:** {charm_client['campaign_count']}
- **Sync enabled:** {charm_client['sync_enabled']}

## EmailBison
- **Workspace ID (numeric):** `{eb_workspace['emailbison_workspace_id']}` — use for EB API
- **Workspace name:** {eb_workspace['emailbison_workspace_name']}
- **Sender accounts:** {eb_workspace['sender_account_count']}
- **API key:** stored in `charm_email_os.workspace_api_keys` keyed by `workspace_id` UUID. NEVER paste here.

## Day.AI
- **Opportunity ID:** `{opp.get('objectId')}`
- **Organization ID:** `{org_id or 'n/a'}` ({org_name or 'n/a'})
- **Owner (Charm AE):** {charm_ae_name or '?'} (`{owner_email}`) — Day.AI user `{owner_user_id}`
- **Stage:** Closed Won
- **Close Date:** {close_date or 'n/a'}
- **Last Contacted:** {last_contacted or 'n/a'}
- **Next Step due:** {next_step or 'n/a'}
- **Full snapshot:** see [[dayai-opp]]

## Primary contact
- **Name:** {primary_contact['name'] or 'n/a'}
- **Email:** {primary_contact['email'] or 'n/a'}
- **Day.AI roles:** {', '.join(primary_contact['roles']) if primary_contact['roles'] else 'n/a'}

## Cross-references
- [[contacts]] — full client + Charm + external roster
- [[status]] — current deal state, risks, blockers (refreshed each Day.AI sync)
- [[insights]] — buyer voice, goals, decision process, competitors
- [[dayai-opp]] — audit snapshot

## How automations consume this file

The YAML frontmatter above is the canonical machine-readable shape:

```python
import frontmatter
data = frontmatter.load("client.md")
eb_id = data["emailbison_workspace_id"]   # numeric, ready for EB API
domain = data["domain"]                    # seed for related-domain generation
opp_id = data["dayai_opp_id"]              # for Day.AI joins
```
"""
    return '\n'.join(fm) + body


def render_contacts_md(client_name: str, parsed_rels: dict, role_by_email: dict, today: str) -> str:
    """Render notes/contacts.md from parsed relationships + roles array."""
    cc = parsed_rels['client_contacts']
    ct = parsed_rels['charm_team']
    ec = parsed_rels['external_contacts']

    lines = [
        '---',
        f'name: Contact roster - {client_name}',
        'type: reference',
        'tags: [contacts, dayai, onboarding]',
        f'created: {today}',
        'status: active',
        'related: ["[[client]]", "[[dayai-opp]]"]',
        '---',
        '',
        f'# {client_name} — Contact Roster',
        '',
        '> Pulled from Day.AI opp relationships at onboarding time. Roles sourced',
        '> from Day.AI `roles` property. Update manually when new contacts emerge;',
        '> the next Day.AI sync will also refresh.',
        '',
        f'## Client-side contacts ({len(cc)})',
        '',
        '| Name | Email | Role(s) | Notes |',
        '|---|---|---|---|',
    ]
    for c in sorted(cc, key=lambda c: c['email']):
        info = role_by_email.get(c['email'], {})
        role_str = ','.join(info.get('roles', []))
        reasoning = (info.get('reasoning', '') or '')[:80].replace('\n', ' ')
        lines.append(f'| {c["name"]} | {c["email"]} | {role_str} | {reasoning} |')

    lines += ['', f'## Charm team on this account ({len(ct)})', '', '| Name | Email | Role |', '|---|---|---|']
    for c in ct:
        info = role_by_email.get(c['email'], {})
        role_str = ','.join(info.get('roles', [])) or 'Charm AE'
        lines.append(f'| {c["name"]} | {c["email"]} | {role_str} |')

    if ec:
        lines += [
            '',
            f'## External / ambiguous ({len(ec)})',
            '',
            '> Appeared in Day.AI relationships but not clearly client-side or',
            '> Charm-side. Review when context arises.',
            '',
            '| Name | Email | Notes |',
            '|---|---|---|',
        ]
        for c in ec:
            lines.append(f'| {c["name"]} | {c["email"]} |  |')
    return '\n'.join(lines) + '\n'


def render_status_md(client_name: str, opp: dict, parsed_rels: dict, today: str) -> str:
    props = opp.get('properties', {})
    close_date = (props.get('Close Date') or '').split('T')[0]
    last_contacted = (props.get('Last Contacted') or '').split('T')[0]
    next_step = (props.get('Next Step') or '').split('T')[0]
    owner_email = props.get('ownerEmail') or ''
    charm_ae_name = next(
        (c['name'] for c in parsed_rels['charm_team'] if c['email'] == owner_email and c['name']),
        '',
    )
    status_text = props.get('Status') or ''
    risks_text = props.get('Risks') or ''
    return f"""---
name: Deal status - {client_name}
type: reference
tags: [status, dayai, live]
created: {today}
status: active
related: ["[[client]]", "[[insights]]", "[[dayai-opp]]"]
---

# {client_name} — Deal Status

> Current live-deal state pulled from Day.AI opp. Updated at each Day.AI sync.
> Do not edit manually — edits will be overwritten on next sync.

## Timeline
- **Close Date:** {close_date or 'n/a'}
- **Last Contacted:** {last_contacted or 'n/a'}
- **Next Step due:** {next_step or 'n/a'}
- **Owner:** {charm_ae_name or '?'} (`{owner_email}`)

## Status

{status_text or '_No status content captured in Day.AI._'}

## Risks

{risks_text or '_No risks noted in Day.AI._'}
"""


def render_insights_md(client_name: str, opp: dict, today: str) -> str:
    props = opp.get('properties', {})
    return f"""---
name: Client insights - {client_name}
type: reference
tags: [insights, dayai, buyer-voice, goals, competitors]
created: {today}
status: active
related: ["[[client]]", "[[status]]", "[[dayai-opp]]"]
---

# {client_name} — Client Insights

> Context snapshot pulled from Day.AI opp custom fields. Updated at each
> Day.AI sync. Primary reference for any Claude session generating campaigns
> or decisions for this client.

## Buyer Voice

{props.get('Buyer Voice') or '_No buyer voice captured in Day.AI._'}

## Goals

{props.get('Goals') or '_No goals captured in Day.AI._'}

## Decision Process

{props.get('Decision Process') or '_No decision process captured in Day.AI._'}

## Competitors

{props.get('Competitors') or '_No competitors captured in Day.AI._'}
"""


def render_dayai_opp_md(client_name: str, client_domain: str, opp: dict, parsed_rels: dict, today: str) -> str:
    props = opp.get('properties', {})
    primary_org = parsed_rels['primary_org'] or {}
    org_name = primary_org.get('name') or 'n/a'
    cc = parsed_rels['client_contacts']
    ct = parsed_rels['charm_team']
    ec = parsed_rels['external_contacts']
    ct_names = ', '.join((c['name'] or c['email']) for c in ct) or 'n/a'
    ec_names = ', '.join((c['name'] or c['email']) for c in ec) or 'n/a'
    close_date = (props.get('Close Date') or '').split('T')[0]
    owner_email = props.get('ownerEmail') or ''
    charm_ae_name = next(
        (c['name'] for c in ct if c['email'] == owner_email and c['name']),
        '',
    )
    return f"""---
name: Day.AI opportunity snapshot - {client_name}
type: reference
tags: [dayai, opp, onboarding, audit]
created: {today}
status: active
related: ["[[client]]", "[[contacts]]", "[[status]]", "[[insights]]"]
---

# Day.AI Opp Snapshot — {client_name}

> Record of the closed-won state that triggered this client's onboarding.
> Do not delete. Audit trail + rebuild source if the clients table is lost.

## Summary

| Field | Value |
|---|---|
| Opportunity ID | `{opp.get('objectId')}` |
| Title | {opp.get('title') or props.get('title') or client_domain} |
| Domain | {client_domain} |
| Organization | {org_name} |
| Stage | Closed Won |
| Close Date | {close_date or 'n/a'} |
| Charm owner | {charm_ae_name or '?'} (`{owner_email}`) |
| Created in Day.AI | {(opp.get('createdAt') or '').split('T')[0]} |

## Relationships ({len(opp.get('relationships', []))} total)

- **Client-side contacts** ({len(cc)}): see [[contacts]]
- **Charm team on account** ({len(ct)}): {ct_names}
- **External contacts** ({len(ec)}): {ec_names}

## Narrative fields

See dedicated files:
- [[insights]] — Buyer Voice, Goals, Decision Process, Competitors
- [[status]] — Status, Risks, Next Step

## Full opp JSON (truncated to 4000 chars)

```json
{json.dumps(opp, indent=2)[:4000]}
```
"""


def main() -> int:
    """Render the 5 files for the configured client. Emit JSON map to stdout."""
    sys.stdout.reconfigure(encoding='utf-8')
    with open(OPP_JSON_PATH, encoding='utf-8') as f:
        opp = json.load(f)

    parsed_rels = parse_relationships(opp.get('relationships') or [], CLIENT_DOMAIN)

    roles_raw = opp.get('properties', {}).get('roles') or []
    if isinstance(roles_raw, str):
        try:
            roles_raw = json.loads(roles_raw)
        except Exception:
            roles_raw = []
    role_by_email = {r.get('personEmail'): r for r in roles_raw if r.get('personEmail')}

    primary_contact = pick_primary_contact(parsed_rels['client_contacts'], role_by_email)
    today = datetime.date.today().isoformat()

    files = {
        'client.md': render_client_md(
            CLIENT_NAME, CLIENT_SLUG, CLIENT_DOMAIN, CHARM_CLIENT, EB_WORKSPACE,
            opp, parsed_rels, primary_contact, today,
        ),
        'notes/contacts.md': render_contacts_md(CLIENT_NAME, parsed_rels, role_by_email, today),
        'notes/status.md': render_status_md(CLIENT_NAME, opp, parsed_rels, today),
        'notes/insights.md': render_insights_md(CLIENT_NAME, opp, today),
        'onboarding/dayai-opp.md': render_dayai_opp_md(CLIENT_NAME, CLIENT_DOMAIN, opp, parsed_rels, today),
    }
    json.dump(files, sys.stdout, indent=2)
    return 0


if __name__ == '__main__':
    sys.exit(main())
