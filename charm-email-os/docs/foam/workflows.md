# Workflows

Common user workflows in Charm Email OS.

## Client Setup

### New Client Onboarding

```
1. Create Client
   └── Enter name and primary domain

2. Complete Onboarding Wizard
   ├── Contact Names (inbox personas)
   ├── Primary Domain
   ├── Industry Selection
   ├── Product Description
   └── Inbox Count

3. Auto-Generate Infrastructure
   ├── Domain Variations (4 variations)
   └── Inbox Personas (per domain)

4. Review & Approve
   ├── Approve/Reject Domains
   └── Approve/Reject Inboxes

5. Infrastructure Provisioning
   └── Domains/Inboxes → Active
```

## Campaign Creation

### From Idea to Sending

```
1. Generate Campaign Ideas
   └── Select Industry + Segment → AI generates 3-4 ideas

2. Review Ideas
   ├── Approve → Ready for campaign
   ├── Edit → Refine and re-review
   └── Reject → Archive

3. Create Campaign
   └── Approved Idea → Draft Campaign

4. Upload Leads
   ├── CSV Upload → Map Columns → Import
   └── Or Script Pull → Automated Import

5. Launch Campaign
   └── Draft → Active → Contacts Sent

6. Monitor Progress
   └── Track queued/contacted/replied/bounced
```

## Lead Management

### CSV Upload Flow

```
1. Select Campaign
   └── Choose target campaign from sidebar

2. Open Upload Modal
   └── Click "Upload Leads"

3. Select CSV File
   └── Browse or drag-drop

4. Column Mapping
   ├── Preview detected columns
   ├── Map to lead fields:
   │   - email (required)
   │   - firstName, lastName
   │   - company, title
   │   - Custom fields
   └── Skip unwanted columns

5. Validate & Import
   ├── Check for duplicates
   ├── Validate email format
   └── Import valid leads

6. Review Stats
   └── See total leads added
```

## Health Management

### Responding to Kill Trigger

```
1. Alert Appears
   └── Kill trigger detected for inbox

2. Review Trigger
   ├── Check severity (instant/confirming)
   ├── Review metrics (bounce rate, complaints)
   └── Identify cause

3. Take Action
   ├── Execute Kill → Inbox marked dead
   │   └── Domain flagged if 1st dead inbox
   │   └── Domain dead if 2nd dead inbox
   └── Dismiss (confirming only) → Schedule retest

4. Investigate Source
   ├── Check campaign attribution
   └── Identify contaminated lists

5. Remediate
   ├── Quarantine bad campaigns
   ├── Remove bad leads
   └── Activate backup inboxes
```

### Domain Rotation

```
1. Monitor Domain Age
   └── Track days until rotation (240 day limit)

2. Pre-Rotation (monitoring phase, 180-240 days)
   ├── Order replacement domains
   ├── Start warming new domains
   └── Plan inbox migration

3. Rotation (240+ days)
   ├── Stop sending from old domain
   ├── Activate replacement domain
   └── Archive old domain
```

## Infrastructure Provisioning

### Complete Flow: Domains to Inboxes

```
┌─────────────────────────────────────────────────────────────────┐
│ PHASE 1: DOMAIN DISCOVERY                                       │
│                                                                 │
│ Option A: From Campaign Documentation                           │
│   1. Customer submits campaign docs                             │
│   2. System extracts domain ideas and sender names              │
│   3. Domain candidates auto-generated                           │
│                                                                 │
│ Option B: Manual Generation                                     │
│   1. Navigate to /clients/[id]/inboxes → "Purchase New" tab     │
│   2. Use domain generation tools                                │
│   3. Enter base domain → generate variations                    │
│                                                                 │
│ Result: Domain candidates in "pending" status                   │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│ PHASE 2: DOMAIN APPROVAL & PURCHASE                             │
│                                                                 │
│ 1. Review pending domains                                       │
│ 2. Check availability and pricing                               │
│ 3. Approve domains for purchase                                 │
│ 4. Execute purchase (Porkbun or Dynadot)                        │
│                                                                 │
│ Result: Domains in "purchased" status                           │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│ PHASE 3: NAME CONFIGURATION                                     │
│                                                                 │
│ 1. Navigate to /clients/[id]/inboxes → "Names" tab              │
│ 2. Add base names (seeds): e.g., "Chris Booth"                  │
│ 3. Select variation patterns (firstname.lastname, c.booth, etc) │
│ 4. Generate 10 variations                                       │
│ 5. Review and approve variations                                │
│ 6. Save to client profile                                       │
│                                                                 │
│ Result: Sender names ready for inbox creation                   │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│ PHASE 4: NS VERIFICATION                                        │
│                                                                 │
│ 1. Click "Verify NS" for purchased domains                      │
│ 2. If mismatch → Click "Fix NS" to set DNSimple NS              │
│ 3. Wait 24-48 hours for DNS propagation                         │
│ 4. Re-verify to confirm "verified" status                       │
│                                                                 │
│ Result: Domains with verified nameservers                       │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│ PHASE 5: INBOX SETUP                                            │
│                                                                 │
│ 1. Select domains in "Domains Ready for Setup" section          │
│ 2. Click "Setup Inboxes" to open wizard                         │
│ 3. Wizard loads configured sender names automatically           │
│ 4. Configure Entra/Google split (if applicable)                 │
│ 5. Execute Hypertide automation                                 │
│ 6. Inboxes created and uploaded to EmailBison                   │
│                                                                 │
│ Result: Domains in "active" status with live inboxes            │
└─────────────────────────────────────────────────────────────────┘
```

### Domain Approval (Legacy)

```
1. View Pending Domains
   └── Navigate to /clients/[id]/inboxes

2. Review Each Domain
   ├── Check domain name quality
   └── Verify availability

3. Approve or Reject
   ├── Approve → Ready for purchase
   └── Reject → Won't be used

4. Purchase Domains
   └── Approved domains can be purchased
```

### Inbox Setup via Wizard

```
1. Navigate to "Purchase New" tab
   └── View "Domains Ready for Setup" section

2. Select Domains
   └── Check boxes for domains to provision

3. Open Inbox Purchase Wizard
   └── Click "Setup Inboxes"

4. Configure Provider Split
   ├── Entra inboxes (52 per domain, 2 domains per order)
   └── Google inboxes (3 per domain, 5 domains per order)

5. Review Names
   └── Auto-loaded from Names tab configuration

6. Execute
   └── Hypertide automation runs
       └── Inboxes created → Uploaded to EmailBison
```

## Campaign Lead Fill (Lead Refinery)

### Automated Lead Filling from DuckDB Reservoir

When an EmailBison campaign needs leads, the [[lead-refinery]] fills it from the 75.4M DuckDB reservoir:

```
1. Extract ICP Criteria
   └── From campaign strategy goals (via [[clients|client onboarding]])
       ├── Industry: e.g., "Hospital & Health Care"
       ├── Titles: ["CEO", "VP Operations", "Director"]
       ├── Company Size: 500+
       └── Geography: US, CA

2. Query DuckDB Reservoir
   └── SELECT matches WHERE:
       ├── ICP criteria match
       ├── disposition = 'fresh' OR 'retouch_eligible'
       ├── email not suppressed
       ├── company not suppressed
       └── data freshness >= 50
       ORDER BY freshness_score DESC, sequence_count ASC

3. Validate Through Pipeline
   ├── [[lead-refinery-gates|Gate 0]]: Pre-validation (FREE)
   │   └── Syntax, DNS, email classification, disposable detection
   ├── [[lead-refinery-gates|Gate 1]]: Email verification ($0.005)
   │   └── Valid / catch_all / invalid / dead
   ├── [[lead-refinery-gates|Gate 2]]: AI-ARK employment check ($0.005)
   │   └── Verified / changed_job / unverifiable
   └── [[lead-refinery-gates|Gate 3]]: Spider+Jina rescue ($0.002)
       └── Rescue unverifiable leads via web search

4. Push Verified Leads
   └── Load into EmailBison campaign
       └── Ready for sequence sends

5. Track Performance
   └── Opens, replies, bounces sync back to DuckDB
       ├── [[lead-dispositions]] updated
       └── [[lead-tam-map]] evolves (next pull is cheaper)
```

### Performance Sync Back

After campaign execution, EmailBison performance data flows back to DuckDB:

```
1. Sync Campaign Results
   └── For each lead in EmailBison campaign:
       ├── Bounced → disposition: bounced (permanent email suppress)
       ├── Replied positive → replied_positive (sales pipeline)
       ├── Replied negative → replied_negative (180-day cooldown)
       ├── Unsubscribed → unsubscribed (CAN-SPAM suppress)
       └── Completed no response → 90-day cooldown

2. TAM Map Updates
   ├── Enrichment data written back (AI-ARK company, title, LinkedIn)
   ├── Performance signals improve ICP quality scoring
   └── Job change detections feed re-enrichment
```

## Daily Operations

### Morning Health Check

```
1. View Health Dashboard
   └── /clients/[id]/health

2. Check Overall Score
   └── Green (>80) / Yellow (50-80) / Red (<50)

3. Review Active Alerts
   ├── Kill triggers pending action
   ├── Domains needing rotation
   └── Capacity warnings

4. Check ESP Reputation
   ├── Gmail reputation
   └── Microsoft reputation

5. Verify Backup Capacity
   └── Ensure ≥100% backup ratio
```

### Campaign Performance Review

```
1. View Leads Dashboard
   └── /clients/[id]/leads

2. Select Campaign
   └── From sidebar

3. Review Stats
   ├── Total leads
   ├── Queued vs contacted
   ├── Reply rate
   └── Bounce rate

4. Check Health Impact
   └── Campaign attribution panel

5. Take Action
   ├── Pause if high bounce rate
   └── Continue if healthy
```

## Related

- [[index]] - Documentation home
- [[system-integration]] - How all three systems connect
- [[infrastructure]] - Domain and inbox management
- [[sender-names]] - Name configuration and variations
- [[lead-refinery]] - Automated lead filling pipeline
- [[lead-tam-map]] - Performance-driven TAM map
- [[lead-dispositions]] - Lead state machine and cooldowns
- [[routing]] - Page navigation
- [[components]] - UI components used

---
Tags: #workflows #guides #howto #infrastructure #lead-refinery
