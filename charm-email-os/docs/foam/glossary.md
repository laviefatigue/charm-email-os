# Glossary

Key terms and concepts in Charm Email OS.

## A

### Alert
Notification about health issues. Types include kill triggers, domain flags, capacity warnings.

### Angle
The messaging approach for a [[campaigns|campaign]]. Examples: "Pain Point Pivot", "Case Study Teaser".

### Approval Workflow
Process where domains, inboxes, or campaign ideas move from `pending_approval` to `approved` or `rejected`.

## B

### Backup Capacity
Reserve [[inboxes]] ready to replace killed ones. Target: 100%+ backup ratio.

### Bounce
Email delivery failure. **Hard bounce** = permanent failure. **Soft bounce** = temporary.

### Bounce Rate
Percentage of sent emails that bounced. Key metric for [[health-monitoring]].

## C

### Campaign
Active email outreach operation. Created from approved [[campaign-ideas]].

### Campaign Idea
AI-generated or manual strategy proposal. Goes through approval before becoming a [[campaigns|campaign]].

### Clay Variables
Personalization variables for email templates. Core, high-signal, and custom fields.

### Client
Organization using Charm Email OS. Top-level entity with infrastructure and campaigns.

### Confirming Kill
[[kill-triggers|Kill trigger]] that requires retest before executing. Less severe than instant kill.

## D

### Daily Send Limit
Maximum emails an [[inboxes|inbox]] can send per day. Increases during warmup.

### Dead (State)
Terminal state for [[inboxes]] or [[domains]]. Inboxes: single dead. Domains: ≥2 dead inboxes.

### Domain
Email sending domain (e.g., `mail-techflow.io`). Contains multiple [[inboxes]].

### Domain Lifecycle Phase
Stage based on domain age: warming → ramping → establishing → peak → monitoring → rotation.

## E

### ESP (Email Service Provider)
Email platform like Gmail or Microsoft 365. ESP reputation affects deliverability.

### ESP Health Summary
Reputation status with Gmail and Microsoft, including authentication (SPF, DKIM, DMARC).

## F

### Flagged (State)
Domain state when 1 inbox is dead. Warning before domain death.

### Follow-up Email
Subsequent email in a campaign sequence after the initial contact.

## H

### Hard Bounce
Permanent delivery failure (invalid email, domain doesn't exist).

### Health Score
0-100 rating of [[inboxes|inbox]], [[domains|domain]], or overall infrastructure health.

### Health State
Current status: live, flagged, dead, or quarantined.

## I

### Inbox
Email account for sending (e.g., `alex.smith@mail-techflow.io`).

### Inbox Placement Rate
Percentage of emails landing in inbox vs spam. Key deliverability metric.

### Instant Kill
[[kill-triggers|Kill trigger]] that immediately terminates an inbox. No retest.

## K

### Kill Trigger
Condition that terminates an [[inboxes|inbox]]. Instant (immediate) or confirming (requires retest).

## L

### Lead
Contact record in a [[campaigns|campaign]]. Has status: queued, contacted, replied, bounced.

### Lead Source
Origin of leads: manual_upload, script_pull, enrichment, manual_entry.

### List Contamination
Poor quality leads causing high bounce rates and harming sender reputation.

### Live (State)
Healthy, operational state for inboxes, domains, or campaigns.

## O

### Onboarding
Setup process for new [[clients]]. Collects info needed to generate infrastructure.

## P

### Persona
The identity (first name, last name) associated with an [[inboxes|inbox]].

### Provider
Email service: gmail, microsoft, or other.

## Q

### QA Score
Quality assessment score (0-100) for [[campaign-ideas]] copy. Checks situation recognition, value clarity, personalization, CTA, length, subject line.

### Quarantined (State)
Campaign paused due to health concerns. Can be cleared to live or confirmed dead.

### Queued
Lead status: waiting to be contacted.

## R

### Rotation
Planned replacement of aging [[domains]]. Required at 240+ days.

## S

### Segment
Target audience subdivision within an industry for [[campaigns]].

### Soft Bounce
Temporary delivery failure (mailbox full, server timeout).

### Spam Complaint
User marking email as spam. Instant kill trigger at ≥1.

### Spam Placement Rate
Percentage of emails landing in spam folder. Should be <5%.

### Status
Current state of an entity. Examples: pending_approval, active, dead.

### Store
Zustand state management container. Examples: [[clientStore]], [[healthStore]].

## T

### Trigger
See [[kill-triggers|Kill Trigger]].

## W

### Warmup
Gradual increase of sending volume for new [[inboxes]] to build reputation.

### Warmup Progress
Percentage (0-100) of inbox warmup completion.

## Related

- [[index]] - Main documentation
- [[data-models]] - Type definitions
- [[health-monitoring]] - Health system details

---
Tags: #glossary #terms #reference
