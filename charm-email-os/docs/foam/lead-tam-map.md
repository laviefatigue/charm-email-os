# Lead TAM Map

A living Total Addressable Market built from campaign-driven enrichment and performance tracking.

## The Core Concept

The 75.4M lead database in DuckDB is a **reservoir** of potential leads. When a [[campaigns|campaign]] needs leads, the system queries this reservoir against the campaign's strategy goals, validates matches through the [[lead-refinery|refinery pipeline]], pushes verified leads into [[infrastructure|EmailBison]] for execution, and tracks performance back to the database.

Every cycle enriches the database. Over time, it transforms from a static Sales Navigator export into a living TAM map with real performance data.

```
Campaign Strategy (EmailBison)
  → Extract ICP criteria from goals
  → Query DuckDB (75.4M reservoir) for matches
  → Refinery validates + freshens selected leads
  → Push verified leads INTO EmailBison campaign
  → Track performance per lead (opens, replies, bounces)
  → Performance + enrichment data flows BACK to database
  → Disposition updated, TAM map evolves
  → Next campaign pull is smarter and cheaper
```

## The Closed Loop

```
┌─────────────────────────────────────────────────────────┐
│                    EmailBison                            │
│  Campaign ← Strategy Goals (industry, titles, size)     │
│     │                                          ↑        │
│     │  "Fill campaign"                         │        │
│     ↓                                          │        │
│  Leads loaded ──→ Sequence ──→ Performance     │        │
│                    sends        opens/replies   │        │
│                    bounces      unsubscribes    │        │
└──────┬──────────────────────────────┬───────────┘        │
       │                              │                    │
       │ Verified leads pushed up     │ Performance        │
       │                              │ data pushed down   │
       │                              ↓                    │
┌──────┴──────────────────────────────────────────┐        │
│              DuckDB (75.4M leads)                │        │
│                                                  │        │
│  ICP query ──→ Refinery Pipeline                 │        │
│                  Gate 0: classify + select email  │        │
│                  Gate 1: verify email             │        │
│                  Gate 2: AI-ARK employment check ─┤        │
│                  Gate 3: Spider+Jina rescue       │        │
│                                                  │        │
│  ← Write back: enrichment data + performance    │        │
│     • current_company (AI-ARK)                   │        │
│     • current_title (AI-ARK)                     │        │
│     • opens, replies, bounces (EmailBison)       │        │
│     • disposition_status updated                 │        │
│     • enriched_at = NOW()                        │        │
└──────────────────────────────────────────────────┘
```

## Two Data Flows Back to Database

### 1. Enrichment Data (from Refinery)

Every lead that passes through [[lead-refinery-gates|Gate 2 (AI-ARK)]] returns fresh employment data. This gets written back regardless of pass/fail:

| Field Returned | What It Tells Us | TAM Value |
|----------------|------------------|-----------|
| `current_company` | Where they work NOW | Account targeting |
| `title` | Current role | Seniority filtering, ICP matching |
| `linkedin` | Profile URL | Multi-channel outreach |
| `company_linkedin` | Company page | Account-level enrichment |
| `job_start` | Role start date | Tenure/stability signal |
| `location` | City/country | Geo-targeting |
| `full_name` | Verified name | Personalization accuracy |

A "company mismatch" is still valuable - it tells us where that person works NOW.

### 2. Performance Data (from EmailBison)

After leads are loaded into a campaign, EmailBison tracks engagement. This flows back to update the lead's [[lead-dispositions|disposition]]:

| Signal | Disposition Update | TAM Impact |
|--------|-------------------|------------|
| Email delivered | `in_sequence` | Confirmed deliverable |
| Opened | `in_sequence` (engaged) | Active inbox confirmed |
| Replied positive | `replied_positive` | Sales pipeline |
| Replied negative | `replied_negative` | 180-day cooldown |
| Replied hard no | `replied_hard_no` | Permanent suppress |
| Bounced | `bounced` | Email dead, try other channels |
| Unsubscribed | `unsubscribed` | CAN-SPAM suppress |
| No response (sequence complete) | `completed_no_response` | 90-day cooldown |

This means every campaign teaches the database:
- Which emails actually deliver (better than Gate 1 verification alone)
- Which leads engage (ICP quality signal)
- Which leads to never contact again (permanent suppress)
- Which domains/companies are responsive (account-level intelligence)

## Campaign Fill Flow

When a campaign in EmailBison needs leads:

```
1. CAMPAIGN defines ICP:
   - Industry: "Hospital & Health Care"
   - Titles: ["CEO", "VP Operations", "Director"]
   - Company size: 500+
   - Geography: US, CA

2. QUERY DuckDB reservoir:
   SELECT * FROM contacts
   WHERE industry MATCHES campaign.industry
     AND title MATCHES campaign.titles
     AND company_size >= campaign.min_size
     AND location IN campaign.geo
     AND disposition_status IN ('fresh', 'retouch_eligible')
     AND email_suppressed = false
     AND email_cooldown_until < NOW()
     AND company_suppressed = false
     AND freshness_score >= 50  -- prefer fresh data
   ORDER BY
     freshness_score DESC,       -- freshest first
     disposition_status = 'fresh' DESC,  -- untouched first
     sequence_count ASC          -- least contacted first
   LIMIT campaign.volume * 2.5   -- pull 2.5x for pipeline losses

3. REFINERY validates selected leads:
   Gate 0 → Gate 1 → Gate 2 → Gate 3
   (enrichment data written back at each stage)

4. PUSH verified leads to EmailBison campaign

5. TRACK performance, update dispositions
```

## Enrichment Write-Back Details

### On VERIFIED (company matches)

```
UPDATE contacts SET
  enriched_company    = '{ai_ark.current_company}',
  enriched_title      = '{ai_ark.title}',
  enriched_linkedin   = '{ai_ark.linkedin}',
  enriched_location   = '{ai_ark.location}',
  enriched_job_start  = '{ai_ark.job_start}',
  enriched_at         = NOW(),
  validation_status   = 'verified',
  freshness_score     = 100
WHERE id = {lead_id}
```

### On CHANGED_JOB (company mismatch)

Still valuable - we now know where they went:

```
UPDATE contacts SET
  enriched_company    = '{ai_ark.current_company}',   -- NEW company
  enriched_title      = '{ai_ark.title}',              -- NEW title
  enriched_linkedin   = '{ai_ark.linkedin}',
  enriched_location   = '{ai_ark.location}',
  enriched_at         = NOW(),
  validation_status   = 'changed_job',
  previous_company    = '{original_company}',          -- Keep history
  freshness_score     = 100                            -- Data is fresh!
WHERE id = {lead_id}
```

A `changed_job` lead is NOT dead. It is a **fresh lead at a new company** that may match a different client's ICP. This feeds back into [[lead-dispositions|JOB CHANGE DETECTED]] status.

### On UNVERIFIABLE (no AI-ARK match)

```
UPDATE contacts SET
  enriched_at         = NOW(),        -- We tried
  validation_status   = 'unverifiable',
  freshness_score     = 30            -- Low confidence but timestamped
WHERE id = {lead_id}
```

## Compounding Returns

Every campaign run makes future campaigns cheaper and smarter.

### Why costs decrease over time

- Contract 1 validates 8,750 leads through Gate 2. Database now has 8,750 fresh records in this ICP segment.
- Contract 2 in the same segment: 2,000 leads already fresh from last run, skip Gate 2. Saves ~$12.
- Contract 10: 55% of segment already fresh. Cost drops from $59.50 to ~$28.
- The TAM map for high-activity segments becomes nearly complete.

### Why quality increases over time

- Performance data teaches which ICP segments respond best
- Bounced emails get permanently flagged (no wasted sends)
- Hard-no contacts and suppressed companies are excluded automatically
- Responsive companies get prioritized (account-level signal)
- Fresh data means fewer job-change surprises mid-campaign

## Job Change Intelligence

`changed_job` leads create a secondary data asset: a **job change feed**.

When AI-ARK reports a company mismatch, we know:
- **Who** moved (name, email)
- **From** where (our original data)
- **To** where (AI-ARK's current data)
- **When** approximately (job_start date)

This enables:
- Re-targeting the person at their new company (if it matches another client's ICP)
- Backfilling the vacated position (new person in that role at old company)
- Detecting company growth/contraction patterns
- Triggering [[lead-dispositions|JOB CHANGE DETECTED]] disposition for re-enrichment

## TAM Health Metrics

These metrics track the overall market state, building on [[lead-dispositions|TAM Tracking]]:

| Metric | Query | Purpose |
|--------|-------|---------|
| **Total Universe** | `COUNT(*) WHERE matches_icp` | Full TAM size |
| **Freshly Enriched** | `COUNT(*) WHERE enriched_at > NOW() - 30d` | Recently verified |
| **Campaign Tested** | `COUNT(*) WHERE sequence_count > 0` | Have real performance data |
| **Stale** | `COUNT(*) WHERE enriched_at < NOW() - 180d` | Needs re-enrichment |
| **Never Enriched** | `COUNT(*) WHERE enriched_at IS NULL` | Unknown data quality |
| **Job Changers** | `COUNT(*) WHERE validation_status = 'changed_job'` | Market movement |
| **Available Fresh** | `COUNT(*) WHERE freshness_score >= 50 AND disposition = 'fresh'` | Ready to pull |
| **Permanently Suppressed** | `COUNT(*) WHERE email_suppressed = true` | Exhausted from TAM |
| **Burn Rate** | `COUNT(*) WHERE disposition_updated_at > NOW() - 7d` | Weekly consumption |
| **TAM Exhaustion ETA** | `available_fresh / burn_rate` | Weeks until segment drained |

## Implementation Notes

### Write-back at pipeline level

The [[lead-refinery|refinery orchestrator]] handles write-back. Individual gates return data; the refinery persists it:

```python
# In refinery.py (conceptual)
gate2_result = aiark.validate_lead(...)

# Always write back enrichment data, regardless of pass/fail
if gate2_result.enriched_data:
    db.update_enrichment(
        lead_id=lead.id,
        enriched_data=gate2_result.enriched_data,
        status=gate2_result.status,
        enriched_at=datetime.now()
    )
```

### Freshness check before Gate 2

Skip Gate 2 if data is already fresh (saves credits):

```python
if lead.freshness_score >= 85 and lead.enriched_at > (now - 30_days):
    result = use_cached_enrichment(lead)  # Skip Gate 2
else:
    result = gate2.validate(lead)  # Call AI-ARK
```

### Performance sync from EmailBison

Periodically pull campaign performance and update dispositions:

```python
# Conceptual - sync performance data back
for lead in emailbison.get_campaign_results(campaign_id):
    if lead.bounced:
        db.update_disposition(lead.email, 'bounced')
    elif lead.replied and lead.sentiment == 'positive':
        db.update_disposition(lead.email, 'replied_positive')
    elif lead.unsubscribed:
        db.update_disposition(lead.email, 'unsubscribed')
    # ... etc
```

## Database Schema Additions

Fields needed for TAM map (extending [[lead-dispositions|contact-level schema]]):

| Field | Type | Purpose |
|-------|------|---------|
| `enriched_company` | string | Company per AI-ARK (may differ from original) |
| `enriched_title` | string | Current title per AI-ARK |
| `enriched_linkedin` | string | Verified LinkedIn URL |
| `enriched_location` | string | Current location |
| `enriched_job_start` | string | When current role started |
| `enriched_at` | timestamp | Last enrichment date |
| `previous_company` | string | Company before job change |
| `freshness_score` | integer | 0-100 decay score |
| `validation_status` | enum | verified / changed_job / unverifiable / dead |
| `spider_verification_url` | string | Gate 3 proof URL |
| `campaign_id` | string | Which EmailBison campaign |
| `last_send_outcome` | enum | delivered / bounced / opened / replied |
| `reply_sentiment` | enum | positive / neutral / negative / hard_no |

## Related

- [[campaigns]] - Campaign strategy drives lead selection
- [[lead-dispositions]] - Disposition states and TAM tracking metrics
- [[lead-refinery]] - Pipeline that validates and enriches leads
- [[lead-refinery-gates]] - Gate 2 (AI-ARK) returns enrichment data
- [[lead-refinery-freshness]] - Freshness scoring and decay model
- [[lead-refinery-config]] - Configuration for enrichment behavior
- [[infrastructure]] - EmailBison execution layer
- [[clients]] - Client ICP drives campaign strategy
- [[system-integration]] - Full platform architecture

---
Tags: #concept #lead-refinery #tam #enrichment #freshness #ai-ark #campaigns #closed-loop
