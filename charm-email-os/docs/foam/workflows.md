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

## Infrastructure Approval

### Domain Approval

```
1. View Pending Domains
   └── Navigate to /clients/[id]/inboxes

2. Review Each Domain
   ├── Check domain name quality
   └── Verify availability

3. Approve or Reject
   ├── Approve → Ready for provisioning
   └── Reject → Won't be used

4. Generate Inboxes
   └── Approved domains get inbox suggestions
```

### Inbox Approval

```
1. View Pending Inboxes
   └── Under each approved domain

2. Review Persona
   ├── Check name combination
   └── Verify email format

3. Approve or Reject
   ├── Approve → Queue for provisioning
   └── Reject → Won't be created
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
- [[routing]] - Page navigation
- [[components]] - UI components used

---
Tags: #workflows #guides #howto
