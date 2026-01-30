# Lead Dispositions

Lead state machine with cooldown logic, company-level tracking, and TAM exhaustion metrics.

## Overview

Every [[leads|lead]] in Charm OS has a **disposition status** that controls whether it can be contacted, when it becomes re-eligible, and how it flows through the outbound pipeline. Dispositions operate at two levels:

- **Contact-level**: Individual lead state and cooldown
- **Company-level**: Aggregate state across all contacts at a company

## Contact-Level Disposition States

```
FRESH ──→ IN SEQUENCE ──→ COMPLETED (NO RESPONSE) ──→ RETOUCH ELIGIBLE ──→ FRESH
                      ├──→ REPLIED - POSITIVE ──→ WON / LOST
                      ├──→ REPLIED - NEUTRAL ──→ NURTURE / RETOUCH ELIGIBLE
                      ├──→ REPLIED - NEGATIVE ──→ RETOUCH (180d) / PERMANENT SUPPRESS
                      ├──→ REPLIED - HARD NO ──→ COMPANY SUPPRESS DECISION
                      ├──→ BOUNCED ──→ LINKEDIN / PHONE / DATA DECAY
                      └──→ UNSUBSCRIBED ──→ LINKEDIN / PHONE (CAN-SPAM)
```

| State | Description | Cooldown | Next States |
|-------|-------------|----------|-------------|
| **FRESH** | Never contacted, data validated | None | in_sequence, suppressed_duplicate |
| **IN SEQUENCE** | Currently receiving emails | N/A (active) | completed, replied_*, bounced, unsubscribed |
| **COMPLETED - NO RESPONSE** | Finished sequence, no engagement | 90 days | retouch_eligible, stale_data |
| **REPLIED - POSITIVE** | Interested, wants meeting/info | Permanent (sales pipeline) | won, lost |
| **REPLIED - NEUTRAL** | "Not right now", "Send info", etc. | 30-60 days | nurture_sequence, retouch_eligible |
| **REPLIED - NEGATIVE** | "Not interested" but not hostile | 180 days | retouch_eligible, permanent_suppress |
| **REPLIED - HARD NO** | Hostile opt-out | PERMANENT (contact-level) | company_suppress_decision |
| **BOUNCED** | Email invalid/undeliverable | Permanent email suppress | linkedin_eligible, phone_eligible, data_decay |
| **UNSUBSCRIBED** | Legally opted out of email | Permanent email suppress (CAN-SPAM) | linkedin_eligible, phone_eligible |
| **RETOUCH ELIGIBLE** | Cooldown expired, ready for new campaign | Re-enrichment check required | fresh, stale_data, job_change_detected |
| **STALE DATA** | Data >6 months old, needs refresh | Requires re-enrichment | fresh, job_change_detected, data_invalid |
| **JOB CHANGE DETECTED** | Contact moved companies | Fresh start at new company | fresh |
| **WON - CUSTOMER** | Converted to paying customer | Move to customer success track | (terminal) |
| **LOST - CLOSED** | Sales cycle ended, no deal | 90 days | retouch_eligible |

## Company-Level States

Aggregate state based on all contacts at a company.

| State | Description |
|-------|-------------|
| **COMPANY - FRESH** | No contacts at company touched |
| **COMPANY - ACTIVE** | 1+ contacts in sequence |
| **COMPANY - COOLING** | Recent contact, others on hold |
| **COMPANY - SUPPRESSED** | Hard no received, all contacts blocked |
| **COMPANY - CUSTOMER** | Active customer, suppress outbound |

## TAM (Total Addressable Market) Tracking

These metrics track lead pool health and prevent TAM exhaustion:

| Metric | Description |
|--------|-------------|
| **Total Universe** | All leads matching ICP criteria |
| **Never Touched** | Fresh leads, no contact history |
| **In Cooldown** | Touched but not yet re-eligible |
| **Available Now** | Fresh + retouch eligible |
| **Permanent Suppress** | Hard no, bounced, unsubscribed |
| **Burn Rate** | Leads consumed per week at current velocity |
| **TAM Exhaustion ETA** | Weeks until Available Now = 0 |

## Pull Logic Decision Tree

When a user clicks "Fill Campaign":

```
1. GET campaign requirements (industry, segment, title, volume)

2. QUERY contacts WHERE:
   - matches ICP criteria (industry, segment, title)
   - disposition_status IN ('fresh', 'retouch_eligible')
   - email_suppressed = false
   - email_cooldown_until < NOW() OR email_cooldown_until IS NULL
   - company.company_suppressed = false
   - company.is_customer = false
   - company.contacts_in_sequence < max_contacts_per_company
   - data_enriched_at > NOW() - INTERVAL '6 months'

3. ORDER BY:
   - disposition_status = 'fresh' DESC   (prioritize untouched)
   - data_enriched_at DESC                (freshest data first)
   - sequence_count ASC                   (least touched first)

4. LIMIT to requested volume

5. FOR EACH selected contact:
   - SET disposition_status = 'in_sequence'
   - SET email_last_contacted = NOW()
   - INCREMENT company.contacts_in_sequence
   - SET company.company_status = 'active'

6. RETURN contacts to campaign loader
```

## Database Schema

### Contact Level

| Field | Type | Purpose |
|-------|------|---------|
| `email` | string (PK) | Primary identifier |
| `company_domain` | string (FK) | Links to company record |
| `disposition_status` | enum | Current state |
| `disposition_updated_at` | timestamp | Last state change |
| `email_last_contacted` | timestamp | Last email sent |
| `linkedin_last_contacted` | timestamp | Last LinkedIn touch |
| `phone_last_contacted` | timestamp | Last phone call |
| `email_cooldown_until` | timestamp | When email re-eligible |
| `linkedin_cooldown_until` | timestamp | When LinkedIn re-eligible |
| `email_suppressed` | boolean | Permanent email block |
| `linkedin_suppressed` | boolean | Permanent LinkedIn block |
| `data_enriched_at` | timestamp | Last enrichment date |
| `last_known_title` | string | Job title at enrichment |
| `last_known_company` | string | Company at enrichment |
| `sequence_count` | integer | Times through sequences |
| `client_id` | string | Client isolation |

### Company Level

| Field | Type | Purpose |
|-------|------|---------|
| `domain` | string (PK) | Company domain |
| `company_status` | enum | Aggregate state |
| `company_suppressed` | boolean | Block all contacts |
| `suppressed_reason` | string | Why suppressed |
| `suppressed_at` | timestamp | When suppressed |
| `contacts_touched_count` | integer | Total contacts touched |
| `contacts_in_sequence` | integer | Currently in sequence |
| `last_contact_date` | timestamp | Most recent contact |
| `company_cooldown_until` | timestamp | Company-wide cooldown |
| `is_customer` | boolean | Active customer flag |
| `customer_since` | timestamp | Customer start date |
| `client_owner_id` | string | Which client owns |

## Open Design Questions

### Cross-Client Deconfliction

- Same company targeted by multiple clients - who wins?
- Options: first-mover priority, client tier, persona silo
- Need: client isolation flag or shared pool toggle

### Channel-Specific Cooldowns

- Email exhausted does not mean LinkedIn exhausted
- Track: `email_last_touched`, `linkedin_last_touched`, `phone_last_touched`
- Different cooldowns per channel (email: 90d, LinkedIn: 30d)

### Disposition Inheritance Rules

- Hard bounce: suppress email only, or all channels?
- Unsubscribe: CAN-SPAM email only, LinkedIn fair game
- Company-level hard no: suppress all contacts?

### Lead Freshness Decay

- Data age tracking via `enriched_at` timestamp
- Force re-enrichment after 6 months
- Job change detection triggers refresh (ties into [[lead-refinery-gates|Gate 2/3]] detection)

### Velocity-Based Throttling

- Don't burn all fresh leads in week 1
- Mix ratio: 70% fresh / 30% retouch
- Reserve pool for high-signal triggers

## Integration with Lead Refinery

The [[lead-refinery]] pipeline feeds leads into the disposition system:

- **Gate 0**: Classifies email type, selects best email per contact
- **Gate 1**: Validates email deliverability (invalid/bounced set to `BOUNCED` before ever sending)
- **Gate 2**: Verifies employment (job change sets `JOB CHANGE DETECTED`)
- **Gate 3**: Rescues unverifiable leads via web scraping

Leads enter the disposition system as `FRESH` after passing the refinery pipeline.

## Related

- [[leads]] - Lead data model and CSV upload
- [[campaigns]] - Campaign management
- [[lead-tam-map]] - AI-ARK enrichment builds a living TAM map
- [[lead-refinery]] - Verification pipeline that feeds dispositions
- [[lead-refinery-gates]] - Gate details (email verification, employment check)
- [[health-monitoring]] - Inbox/domain health affected by bounces
- [[infrastructure]] - Sending infrastructure
- [[clients]] - Client onboarding provides ICP criteria
- [[system-integration]] - Full platform architecture

---
Tags: #concept #leads #dispositions #state-machine #tam #cooldown
