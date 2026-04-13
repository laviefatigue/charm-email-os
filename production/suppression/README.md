# Per-Client Domain Suppression

Keeps client-owned domains out of EmailBison campaigns. Each client gets an isolated suppression list. Clay calls our check endpoint before submitting leads; any lead whose domain is in the list is blocked.

## How it works

```
Clay enrichment step
  → POST /api/suppressions/check  (X-Suppression-Token: <client token>)
  ← { "suppressed": true/false, "matched_domain": "acme.com" }

Clay filter: drop rows where suppressed = true

Leads import (our internal API)
  → suppression gate runs automatically per lead
  → suppressed leads stamped with status = "suppressed", never sent to EB
```

Domain matching uses three passes (single SQL query):
1. **Direct** — `lead_domain = domain`
2. **Umbrella** — `lead_domain = umbrella_domain`
3. **Subdomain** — `lead_domain LIKE '%.umbrella_domain'`

So a rule of `rotorooter.com / umbrella: chemed.com` blocks:
- `rotorooter.com` (direct)
- `chemed.com` (umbrella direct)
- `subsidiaryof.chemed.com` (subdomain)

---

## Clay integration

### 1. Get the client's API token

```
GET /api/suppressions/clients/{client_id}/config
```

Returns `api_token` — a 64-char hex string. This is the only credential needed.

### 2. Add HTTP enrichment step in Clay

| Field | Value |
|-------|-------|
| Method | POST |
| URL | `https://api.wizardgrimoire.cloud/api/suppressions/check` |
| Header | `X-Suppression-Token: <api_token>` |
| Body | `{ "email": "{{email}}", "company_domain": "{{company_website}}" }` |

Both `email` and `company_domain` are optional but recommended together. The endpoint extracts the domain from the email address and checks both the email domain and the explicit company domain.

### 3. Add filter step

Filter out rows where `suppressed = true`.

### Response shape

```json
{
  "suppressed": true,
  "reason": "Domain match: acme.com",
  "matched_domain": "acme.com",
  "match_type": "direct",
  "client_id": "b311f290-..."
}
```

`match_type` is one of `direct`, `umbrella`, or `subdomain`.

### Error responses

| Status | Meaning |
|--------|---------|
| 401 | Missing or invalid `X-Suppression-Token` |
| 422 | Malformed request body |

When suppression is disabled (`is_enabled = false`) the endpoint returns `suppressed: false` for all calls — safe for pre-launch wiring.

---

## Managing suppression lists

### Upload a seed list (CSV)

```bash
curl -X POST "https://api.wizardgrimoire.cloud/api/suppressions/clients/{client_id}/domains/upload-csv" \
  -F "file=@seedlist.csv" \
  -F "replace_all=false"
```

CSV format (header required):
```
domain,umbrella_domain
acme.com,
rotorooter.com,chemed.com
subsidiary.com,chemed.com
```

- `umbrella_domain` column is optional; leave blank if there's no parent company relationship.
- `replace_all=true` wipes existing domains before import. `false` (default) merges — duplicates are silently skipped.
- Max 10,000 rows per upload.
- Domains are auto-cleaned: strips `https://`, `www.`, trailing slashes, ports.

### Add a single domain

```bash
curl -X POST "https://api.wizardgrimoire.cloud/api/suppressions/clients/{client_id}/domains" \
  -H "Content-Type: application/json" \
  -d '{"domain": "acme.com", "umbrella_domain": "parentcorp.com"}'
```

### Enable / disable suppression

```bash
# Enable
curl -X PATCH ".../clients/{client_id}/config" \
  -H "Content-Type: application/json" \
  -d '{"is_enabled": true}'

# Disable (passthrough mode — check endpoint returns suppressed=false)
curl -X PATCH ".../clients/{client_id}/config" \
  -H "Content-Type: application/json" \
  -d '{"is_enabled": false}'
```

### Rotate the API token

```bash
curl -X POST ".../clients/{client_id}/config/rotate-token"
```

Returns `{ "api_token": "<new_token>", "token_created_at": "..." }`. Update Clay immediately after.

---

## Current clients

| Client | client_id | Domains | Status |
|--------|-----------|---------|--------|
| Search Atlas | `b311f290-017e-4d67-85f7-d38292b4b08d` | 628 | Enabled |

### Search Atlas token

```
20136b363986df6bfdeeccb019d30da8df8370d6a81d3fa938c7323aea3208bc
```

Seed list source: HubSpot CRM export (all deals, 2026-04-10). Both `Website` and `Umbrella Domain` columns extracted and deduped. File: `searchatlas-suppression-seedlist.csv`.

---

## API reference

Base URL: `https://api.wizardgrimoire.cloud/api/suppressions`

| Method | Path | Description |
|--------|------|-------------|
| GET | `/clients/{id}/config` | Get/bootstrap config (auto-creates on first call) |
| PATCH | `/clients/{id}/config` | Update `is_enabled`, `notes` |
| POST | `/clients/{id}/config/rotate-token` | Issue new API token |
| GET | `/clients/{id}/domains` | List domains (paginated, supports `?search=`) |
| POST | `/clients/{id}/domains` | Add single domain |
| POST | `/clients/{id}/domains/bulk` | Add domains from JSON array |
| POST | `/clients/{id}/domains/upload-csv` | Upload CSV file |
| DELETE | `/clients/{id}/domains/{domain_id}` | Remove one domain |
| DELETE | `/clients/{id}/domains` | Clear all domains |
| GET | `/clients/{id}/stats` | Dashboard stats (counts, Clay call history) |
| POST | `/clients/{id}/scan` | Retroactively evaluate existing leads |
| POST | `/check` | Clay check endpoint (token auth) |

---

## Database tables

| Table | Purpose |
|-------|---------|
| `client_suppression_configs` | One row per client — token, enabled flag, counts |
| `client_suppression_domains` | Seed list — one row per domain per client |
| `suppression_check_log` | Async audit log of Clay calls |

All rows include `client_id` FK. Cross-client data access is structurally impossible — every query filters by `client_id`, and the Clay endpoint resolves `client_id` from the token alone.

---

## Onboarding a new client

1. Get `client_id` from `GET /api/clients?search=<name>`
2. Bootstrap config: `GET /api/suppressions/clients/{id}/config` — note the `api_token`
3. Upload seed CSV from HubSpot export
4. Enable: `PATCH /api/suppressions/clients/{id}/config` with `{"is_enabled": true}`
5. Give `api_token` to Clay team, wire up the enrichment step
6. Verify: `POST /api/suppressions/check` with a known domain from the list — should return `suppressed: true`
