# Strategy-AI Update: Complete EmailBison Campaign Generation

## Overview

Update the Strategy-AI container to generate **complete 4-email sequences** that match EmailBison's campaign structure, rather than single email variants. This allows push-to-emailbison to create fully configured campaigns with minimal manual work.

---

## Target Output: Complete Campaign Structure

### EmailBison Campaign Components

A complete campaign in EmailBison requires:

| Component | Description |
|-----------|-------------|
| **Campaign Name** | Subject line of Email 1 |
| **Sequence** | 4 emails with specific timing and threading |
| **Schedule** | Business hours M-F 8am-5pm |
| **Senders** | Assigned from workspace inbox pool |
| **Leads** | Added separately (not part of this spec) |

### The 4-Email Sequence Structure

| Email | Timing | Subject Line | Thread | Strategy |
|-------|--------|--------------|--------|----------|
| 1 | Day 0 | New (2-4 words OR whole offer) | No | Custom signal OR whole offer - lead with strongest value prop |
| 2 | Day 3-4 | NONE | Yes (threads to Email 1) | Rotate value prop, creative ideas, or stats/data hook |
| 3 | Day 7-8 | New (fresh thread) | No | Drop AI, go direct OR case study deep dive |
| 4 | Day 11-12 | Thread OR new | Optional | Redirect to colleague OR offer resources OR value bomb |

---

## The "3 Offers" Framework

Every email should lead with one of these value props, rotating through the sequence:

1. **Save Time** - Efficiency, automation, less manual work
2. **Save Money** - Reduce costs, better ROI, do more with same team
3. **Make Money** - Increase revenue, conversions, pipeline

**Rotation example:**
- Email 1 (Save Time): "Have you figured out how to do X without adding headcount?"
- Email 2 (Make Money): "Had some ideas that could increase your pipeline..."
- Email 3 (Save Money): "Most teams can't justify 3x headcount but need 3x volume..."
- Email 4 (Value Bomb): Send actual contacts/data as proof

---

## Email Templates by Position

### Email 1: Full Campaign (Day 0)

**Purpose**: First impression, best shot at earning a reply

**Structure**:
```
Subject: [2-4 words intrigue] OR [Whole offer question]

{{first_name}}—[specific signal about them]

[Value prop + proof in 1-2 sentences]

[Optional: "Specifically, it looks like you're trying to sell to {{ai_customer_type}}, and we can help with that."]

[Low-effort CTA: "Worth exploring?"]
```

**Word count**: 50-90 words (strict)

---

### Email 2: Rotate Value Prop (Day 3-4, Threaded)

**Purpose**: They saw Email 1 but didn't reply - try different angle

**Subject**: NONE (threads to Email 1)

**Template A: Creative Ideas**
```
{{first_name}}—I was back on your site today and had some ideas for you.

• [Idea 1 using Feature X]—would help with [their pain]
• [Idea 2 using Feature Y]—could improve [their goal]
• [Idea 3 using Feature Z]—might address [their challenge]

But of course, I wrote this without knowing your current bottlenecks.

If it's interesting, happy to share what's working in {{industry}}.
```

**Template B: Stats/Data Hook**
```
{{first_name}}—I sent an email with subject "[Email 1 subject]" that probably didn't do a good enough job showing how we could help.

[Show data about them]:
• [Stat 1 about their company]
• [Stat 2 about their situation]
• [Stat 3 that proves capability]

Wanna see how this works for {{company_name}}?
```

---

### Email 3: Fresh Thread, Direct Approach (Day 7-8)

**Purpose**: Reset attention with new thread, consider dropping AI personalization

**Subject**: New subject line (e.g., "Scaling outbound" or "[Pain point]")

**Template A: Whole Offer (Drop AI)**
```
{{first_name}},

[Describe the problem they have in 1-2 sentences]

[Explain solution + case study with specific metric]

Worth exploring?
```

**Template B: Case Study Deep Dive**
```
Subject: [Customer type] case study

{{first_name}},

Quick story: [Similar customer] was struggling with [specific problem].

They were [bad state] and needed to [outcome].

We helped them [action] and they saw [metric] in [timeframe].

Given what {{company_name}} does, figured this might be relevant.

Worth a quick chat?
```

---

### Email 4: Final Email (Day 11-12)

**Purpose**: Last shot - redirect, offer resources, or show value

**Template A: Redirect to Colleague**
```
{{first_name}}—let me know if {{employee_1}} or {{employee_2}} would be better to speak about [specific problem].

Either way, appreciate the time!
```

**Template B: Resource Offer**
```
{{first_name}}—Alternatively, if {{company_name}} is taking all your time, we have some resources on [topic] that could help.

Would it be useful if I sent those over?
```

**Template C: Value Bomb (Show Don't Tell)**
```
Subject: show and tell

{{first_name}}—Last email. I figured you sell to {{ai_customer_type}}.

I went ahead and pulled some contacts for you:

{{contact_1}} – {{linkedin}} – {{email}}
{{contact_2}} – {{linkedin}} – {{email}}
{{contact_3}} – {{linkedin}} – {{email}}

Want to see how I did this automatically?
```

---

## Variable Transformation

Strategy-AI uses `{{double_braces}}` variables. EmailBison uses `{SINGLE_BRACES}`.

**Mapping**:
| Strategy-AI | EmailBison |
|-------------|------------|
| `{{first_name}}` | `{FIRST_NAME}` |
| `{{company_name}}` | `{COMPANY_NAME}` |
| `{{role_title}}` | `{JOB_TITLE}` |
| `{{industry}}` | `{INDUSTRY}` |
| `{{ai_customer_type}}` | Custom variable (team configures) |

Push-to-emailbison should transform variables before sending to EmailBison API.

---

## Updated Strategy-AI Output Schema

```json
{
  "job_id": "uuid",
  "client_id": "uuid",
  "campaign_type": "custom_signal | creative_ideas | whole_offer | fallback",
  "campaign_name": "Subject line of Email 1",
  "value_prop_rotation": ["save_time", "make_money", "save_money"],
  "sequence": [
    {
      "position": 1,
      "wait_days": 0,
      "subject_line": "Quick q about {{company_name}}",
      "email_body": "...",
      "thread_reply": false,
      "strategy": "custom_signal",
      "value_prop": "save_time",
      "word_count": 72
    },
    {
      "position": 2,
      "wait_days": 3,
      "subject_line": null,
      "email_body": "...",
      "thread_reply": true,
      "strategy": "creative_ideas",
      "value_prop": "make_money",
      "word_count": 85
    },
    {
      "position": 3,
      "wait_days": 4,
      "subject_line": "Scaling outbound",
      "email_body": "...",
      "thread_reply": false,
      "strategy": "case_study",
      "value_prop": "save_money",
      "word_count": 58
    },
    {
      "position": 4,
      "wait_days": 4,
      "subject_line": null,
      "email_body": "...",
      "thread_reply": true,
      "strategy": "redirect",
      "value_prop": null,
      "word_count": 32
    }
  ],
  "used_variables": ["{{first_name}}", "{{company_name}}", "{{ai_customer_type}}"],
  "missing_variables": ["{{employee_1}}", "{{employee_2}}"],
  "score": 87,
  "rationale": "..."
}
```

---

## QA Checklist (Per Email)

Before saving each email in the sequence:

1. ☐ **First line = specific signal** (Email 1) OR **different angle** (Email 2-4)
2. ☐ **No hallucinations** (every fact verifiable from context)
3. ☐ **Variables formatted correctly** `{{double_braces}}`
4. ☐ **No banned phrases** (see list below)
5. ☐ **Recipient:sender ratio >= 3:1** (them vs us sentences)
6. ☐ **50-90 words** (strict)
7. ☐ **CTA = low-effort** (can reply in 5 words or less)
8. ☐ **Reads in under 20 seconds**
9. ☐ **Value prop rotated** (different from previous email)
10. ☐ **Threading correct** (Email 2 threads, Email 3 fresh)
11. ☐ **"Would I reply?" = YES**

### Banned Phrases (Delete & Rewrite)

**Generic Openers**:
- "I hope this email finds you well"
- "I wanted to reach out"
- "I came across your profile"
- "Just wanted to touch base"

**Weak Value Props**:
- "We help companies..." (unless immediately followed by case study)
- "Our solution..."
- "I wanted to show you..."

**High-Effort CTAs**:
- Any request for "15 minutes" or "30 minutes"
- "Would love to schedule..."
- "Let's hop on a call"

**Hedging**:
- "I think", "perhaps", "maybe", "possibly"
- "I was wondering if"

---

## Scoring Rubric (0-100)

| Dimension | Points | What's Measured |
|-----------|--------|-----------------|
| Situation Recognition | 25 | Specific data about them? Uses research? |
| Value Clarity | 25 | Clear offer + proof? Reader knows what you do? |
| Personalization Quality | 20 | Custom signal OR AI insight? Not just {{name}}? |
| CTA Effort | 15 | 5 words or less to reply? Low friction? |
| Punchiness | 10 | 50-90 words? No fluff? 3:1 ratio? |
| Subject Line | 5 | 2-4 words OR whole offer value prop? |

**Thresholds**:
- **85+** = Ship it
- **70-84** = One more pass
- **<70** = Start over

---

## Push-to-EmailBison Changes

Once strategy-ai generates full sequences, update push-to-emailbison to:

1. **Create campaign** with Email 1 subject as name
2. **Add all 4 sequence steps** with correct timing:
   ```python
   sequence_steps = [
       {"email_subject": email1.subject, "email_body": transform_vars(email1.body),
        "order": 1, "wait_in_days": 0, "thread_reply": False},
       {"email_subject": "", "email_body": transform_vars(email2.body),
        "order": 2, "wait_in_days": 3, "thread_reply": True},
       {"email_subject": email3.subject, "email_body": transform_vars(email3.body),
        "order": 3, "wait_in_days": 4, "thread_reply": False},
       {"email_subject": "", "email_body": transform_vars(email4.body),
        "order": 4, "wait_in_days": 4, "thread_reply": True}
   ]
   ```
3. **Attach sender inboxes** from workspace pool
4. **Create schedule** (M-F 8am-5pm, client timezone)

---

## Database Schema Updates

### New: `strategy_sequences` table

```sql
CREATE TABLE strategy_sequences (
    id UUID PRIMARY KEY,
    suggestion_id UUID REFERENCES strategy_suggestions(id),
    position INTEGER NOT NULL,  -- 1, 2, 3, or 4
    wait_days INTEGER NOT NULL,
    subject_line TEXT,  -- NULL for threaded emails
    email_body TEXT NOT NULL,
    thread_reply BOOLEAN DEFAULT FALSE,
    strategy VARCHAR(50),  -- custom_signal, creative_ideas, etc.
    value_prop VARCHAR(50),  -- save_time, save_money, make_money
    word_count INTEGER,
    created_at TIMESTAMP DEFAULT NOW()
);
```

Or alternatively, store as JSONB in existing `strategy_suggestions`:

```sql
ALTER TABLE strategy_suggestions
ADD COLUMN sequence_data JSONB;
-- sequence_data contains array of {position, wait_days, subject_line, email_body, thread_reply, ...}
```

---

## Frontend Redesign: Strategy Page

### Current State

The strategy page shows individual email variants as cards:
- 3 variants per generation
- Single subject + body per card
- Approve/Deny/Revision buttons per variant
- "Push to EmailBison" button for approved variants

### Target State

Display complete 4-email sequences as expandable campaign cards:

```
┌─────────────────────────────────────────────────────────────────┐
│ 📧 Campaign: "Quick q about {{company_name}}"                   │
│ Status: ⏳ Pending Review        Score: 87/100                  │
│ Type: custom_signal             Value Props: Time → Money → $   │
├─────────────────────────────────────────────────────────────────┤
│ ▼ Email 1 (Day 0) - New Thread                    72 words     │
│   Subject: Quick q about {{company_name}}                       │
│   ┌──────────────────────────────────────────────────────────┐ │
│   │ {{first_name}}—saw you sell to sales leaders...           │ │
│   │ [email body preview]                                      │ │
│   └──────────────────────────────────────────────────────────┘ │
│   [Edit]                                                        │
├─────────────────────────────────────────────────────────────────┤
│ ▶ Email 2 (Day 3) - Threads to Email 1            85 words     │
│   [Click to expand]                                             │
├─────────────────────────────────────────────────────────────────┤
│ ▶ Email 3 (Day 7) - Fresh Thread                  58 words     │
│   Subject: Scaling outbound                                     │
├─────────────────────────────────────────────────────────────────┤
│ ▶ Email 4 (Day 11) - Threads                      32 words     │
│   [Click to expand]                                             │
├─────────────────────────────────────────────────────────────────┤
│ [Approve Sequence] [Deny] [Request Revision] [Push to EmailBison]│
└─────────────────────────────────────────────────────────────────┘
```

### UI Components

#### 1. Campaign Card (Collapsed View)
- Campaign name (Email 1 subject)
- Overall score
- Campaign type badge
- Value prop rotation indicator
- Status badge
- Quick stats (4 emails, total word count)

#### 2. Email Step Row (Expandable)
```tsx
interface EmailStepRow {
  position: 1 | 2 | 3 | 4;
  timing: string;           // "Day 0", "Day 3", etc.
  threadType: "new" | "reply";
  subjectLine: string | null;
  bodyPreview: string;      // First 100 chars
  wordCount: number;
  valueProp: "save_time" | "save_money" | "make_money" | null;
  isExpanded: boolean;
}
```

#### 3. Email Editor Modal
When clicking "Edit" on any email:
- Subject line input (disabled for threaded emails)
- Body textarea with character/word count
- Variable highlighting/autocomplete
- Preview pane
- Save/Cancel buttons

#### 4. Sequence Timeline Visualization
Visual timeline showing:
```
Day 0        Day 3        Day 7        Day 11
  │            │            │            │
  ●────────────●────────────●────────────●
  │            │            │            │
Email 1    Email 2     Email 3     Email 4
(New)      (Thread)    (New)       (Thread)
```

### User Flow: Viewing Campaign Sequences

**Step 1: Campaign List View**
```
┌─────────────────────────────────────────────────────────────────┐
│ Campaign Suggestions                    [Generate More] [Filter]│
├─────────────────────────────────────────────────────────────────┤
│ ┌─────────────────────────────────────────────────────────────┐ │
│ │ 📧 "Quick q about {{company_name}}"          Score: 87     │ │
│ │ custom_signal • 4 emails • 247 words total   ⏳ Pending    │ │
│ │ [Expand Sequence ▼]                                         │ │
│ └─────────────────────────────────────────────────────────────┘ │
│                                                                 │
│ ┌─────────────────────────────────────────────────────────────┐ │
│ │ 📧 "Scaling without headcount"               Score: 82     │ │
│ │ whole_offer • 4 emails • 198 words total     ⏳ Pending    │ │
│ │ [Expand Sequence ▼]                                         │ │
│ └─────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────┘
```

**Step 2: Expanded Sequence View**
```
┌─────────────────────────────────────────────────────────────────┐
│ 📧 "Quick q about {{company_name}}"                            │
│ Score: 87 • custom_signal • Value Props: ⏱️→💰→💵              │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  Day 0          Day 3          Day 7          Day 11           │
│    ●──────────────●──────────────●──────────────●              │
│    │              │              │              │              │
│  Email 1      Email 2        Email 3        Email 4            │
│  New Thread   → Threads      New Thread     → Threads          │
│                                                                 │
├─────────────────────────────────────────────────────────────────┤
│ ┌─ EMAIL 1 (Day 0) ─────────────────────────────────────────┐  │
│ │ Subject: Quick q about {{company_name}}                    │  │
│ │ Strategy: custom_signal • Value: Save Time • 72 words     │  │
│ │ ──────────────────────────────────────────────────────────│  │
│ │ {{first_name}}—saw you sell to sales leaders.              │  │
│ │                                                            │  │
│ │ Noticed John is a BDR on the team. Have you figured out   │  │
│ │ how he could leverage better data and GPT-4 for...        │  │
│ │ ──────────────────────────────────────────────────────────│  │
│ │ [Edit] [Request Revision for Email 1]                      │  │
│ └────────────────────────────────────────────────────────────┘  │
│                                                                 │
│ ┌─ EMAIL 2 (Day 3) ─────────────────────────────────────────┐  │
│ │ Subject: (threads to Email 1)                              │  │
│ │ Strategy: creative_ideas • Value: Make Money • 85 words   │  │
│ │ ──────────────────────────────────────────────────────────│  │
│ │ {{first_name}}—I was back on your site and had some...    │  │
│ │ ──────────────────────────────────────────────────────────│  │
│ │ [Edit] [Request Revision for Email 2]                      │  │
│ └────────────────────────────────────────────────────────────┘  │
│                                                                 │
│ [Email 3 collapsed - click to expand]                          │
│ [Email 4 collapsed - click to expand]                          │
│                                                                 │
├─────────────────────────────────────────────────────────────────┤
│ [✓ Approve Entire Sequence] [✗ Deny] [Push to EmailBison]      │
└─────────────────────────────────────────────────────────────────┘
```

---

### User Flow: Requesting Revision on Specific Email

**Scenario**: User likes Email 1, 2, and 4 but wants Email 3 revised.

**Step 1**: User expands Email 3 and clicks `[Request Revision for Email 3]`

**Step 2**: Revision Modal Opens
```
┌─────────────────────────────────────────────────────────────────┐
│ Request Revision - Email 3                              [X]    │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│ Current Email 3:                                                │
│ ┌───────────────────────────────────────────────────────────┐  │
│ │ Subject: Scaling outbound                                  │  │
│ │ {{first_name}}, Most teams hit a wall when they need...   │  │
│ └───────────────────────────────────────────────────────────┘  │
│                                                                 │
│ What would you like changed?                                    │
│ ┌───────────────────────────────────────────────────────────┐  │
│ │ Include a specific case study about a SaaS company.       │  │
│ │ Make it more direct - drop the "most teams" generalization│  │
│ │ and lead with our proof point.                            │  │
│ │                                                            │  │
│ └───────────────────────────────────────────────────────────┘  │
│                                                                 │
│ Revision applies to:                                            │
│ ○ Just Email 3                                                  │
│ ○ Email 3 and all subsequent emails (3 & 4)                    │
│ ○ Entire sequence (regenerate all 4)                           │
│                                                                 │
│                              [Cancel] [Submit Revision Request] │
└─────────────────────────────────────────────────────────────────┘
```

**Step 3**: After submission, sequence shows revision status
```
┌─ EMAIL 3 (Day 7) ──────────────────────────────────────────────┐
│ 🔄 REVISION REQUESTED                                           │
│ "Include a specific case study about a SaaS company..."        │
│ Requested by: john@agency.com • 2 min ago                       │
└─────────────────────────────────────────────────────────────────┘
```

---

### User Flow: Editing Individual Email

**Step 1**: User clicks `[Edit]` on Email 2

**Step 2**: Editor Modal Opens
```
┌─────────────────────────────────────────────────────────────────┐
│ Edit Email 2 - Day 3 (Threaded Reply)                   [X]    │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│ Subject Line:                                                   │
│ ┌───────────────────────────────────────────────────────────┐  │
│ │ (Disabled - Email 2 threads to Email 1)                   │  │
│ └───────────────────────────────────────────────────────────┘  │
│                                                                 │
│ Email Body:                                    Word Count: 85  │
│ ┌───────────────────────────────────────────────────────────┐  │
│ │ {{first_name}}—I was back on your site today and had      │  │
│ │ some ideas for you.                                        │  │
│ │                                                            │  │
│ │ • Automate SDR research with Clay integration—would       │  │
│ │   save 10+ hours/week                                     │  │
│ │ • Set up intent signals from G2/Bombora—catch buyers     │  │
│ │   earlier in the cycle                                    │  │
│ │ • Build LinkedIn engagement workflow—warm leads before    │  │
│ │   cold outreach                                           │  │
│ │                                                            │  │
│ │ But of course, I wrote this without knowing your current  │  │
│ │ bottlenecks.                                              │  │
│ │                                                            │  │
│ │ If it's interesting, happy to share what's working in    │  │
│ │ {{industry}}.                                             │  │
│ └───────────────────────────────────────────────────────────┘  │
│                                                                 │
│ Variables Used: {{first_name}}, {{industry}}                   │
│ ⚠️ Warning: Word count exceeds 90 (target: 50-90)              │
│                                                                 │
│ Preview:                                                        │
│ ┌───────────────────────────────────────────────────────────┐  │
│ │ John—I was back on your site today and had...             │  │
│ └───────────────────────────────────────────────────────────┘  │
│                                                                 │
│                                    [Cancel] [Save Changes]     │
└─────────────────────────────────────────────────────────────────┘
```

---

### Component Structure (React/Next.js)

```
app/clients/[clientId]/strategy/
├── page.tsx                      # Main strategy page
├── components/
│   ├── CampaignSequenceList.tsx  # List of all sequences
│   ├── CampaignSequenceCard.tsx  # Single sequence card (collapsed/expanded)
│   ├── SequenceTimeline.tsx      # Visual timeline component
│   ├── EmailStepCard.tsx         # Individual email within sequence
│   ├── EmailEditorModal.tsx      # Edit individual email
│   ├── RevisionRequestModal.tsx  # Request revision with scope selector
│   ├── SequenceActions.tsx       # Approve/Deny/Push buttons
│   └── SequenceFilters.tsx       # Filter and sort controls
├── hooks/
│   ├── useSequences.ts           # Fetch/mutate sequences
│   └── useRevisionRequest.ts     # Handle revision submissions
└── types/
    └── sequence.ts               # TypeScript interfaces
```

### TypeScript Interfaces

```typescript
// types/sequence.ts

interface CampaignSequence {
  id: string;
  jobId: string;
  clientId: string;
  campaignName: string;          // Email 1 subject
  campaignType: 'custom_signal' | 'creative_ideas' | 'whole_offer' | 'fallback';
  status: 'pending' | 'approved' | 'denied' | 'revision_requested' | 'sent';
  score: number;
  valuePropRotation: ('save_time' | 'save_money' | 'make_money')[];
  emails: SequenceEmail[];
  usedVariables: string[];
  missingVariables: string[];
  rationale: string;
  createdAt: string;
  reviewedAt?: string;
  reviewedBy?: string;
  pushedAt?: string;
}

interface SequenceEmail {
  position: 1 | 2 | 3 | 4;
  waitDays: number;
  subjectLine: string | null;    // null for threaded emails
  emailBody: string;
  editedSubjectLine?: string;    // user edits
  editedEmailBody?: string;
  threadReply: boolean;
  strategy: string;
  valueProp: 'save_time' | 'save_money' | 'make_money' | null;
  wordCount: number;
  revisionRequest?: RevisionRequest;
}

interface RevisionRequest {
  id: string;
  emailPosition: number;         // which email (1-4)
  instruction: string;
  scope: 'single' | 'subsequent' | 'all';
  requestedBy: string;
  requestedAt: string;
  processed: boolean;
}
```

### API Endpoints

```typescript
// GET /api/strategy/sequences/:clientId
// Returns all sequences for a client
Response: { sequences: CampaignSequence[] }

// PATCH /api/strategy/sequences/:sequenceId
// Update sequence status (approve/deny)
Request: { status: 'approved' | 'denied', reviewedBy: string }

// PATCH /api/strategy/sequences/:sequenceId/emails/:position
// Edit specific email in sequence
Request: { editedSubjectLine?: string, editedEmailBody?: string }

// POST /api/strategy/sequences/:sequenceId/revision
// Request revision for specific email or entire sequence
Request: {
  emailPosition: number,         // 1-4 or 0 for whole sequence
  instruction: string,
  scope: 'single' | 'subsequent' | 'all'
}

// POST /api/strategy/sequences/:sequenceId/push-to-emailbison
// Push approved sequence to EmailBison
Response: {
  emailbisonCampaignId: number,
  sequenceStepsCreated: number,
  sendersAttached: number,
  scheduleConfigured: boolean
}
```

### Filtering & Sorting

Update filters to work with sequences:
- Sort by: Date created, Score, Campaign type
- Filter by: Status, Campaign type, Has revisions
- Search: Subject lines, body content

### Responsive Design

**Desktop (>1024px)**: Full card view with inline expansion
**Tablet (768-1024px)**: Stacked cards, modal for expansion
**Mobile (<768px)**: List view, full-screen editor modal

---

## Backend Robustness

### Push-to-EmailBison: Multi-Step Transaction

The push operation involves multiple API calls that must be handled atomically:

```python
async def push_sequence_to_emailbison(sequence_id: UUID):
    """
    Push approved sequence to EmailBison with full error handling.
    Uses a step-tracking approach for partial failure recovery.
    """

    # Track which steps completed for potential rollback
    created_campaign_id = None
    steps_completed = []

    try:
        # Step 1: Switch workspace
        await switch_workspace(emailbison_workspace_id)
        steps_completed.append("workspace_switch")

        # Step 2: Create campaign
        campaign = await create_campaign(name=subject, type="outbound")
        created_campaign_id = campaign["id"]
        steps_completed.append("campaign_create")

        # Step 3: Add sequence steps (all 4 emails)
        await create_sequence_steps(
            campaign_id=created_campaign_id,
            steps=transform_sequence_to_emailbison_format(sequence)
        )
        steps_completed.append("sequence_steps")

        # Step 4: Attach senders (graceful if none available)
        if sender_email_ids:
            await attach_sender_emails(created_campaign_id, sender_email_ids)
            steps_completed.append("senders_attached")
        else:
            logger.warning(f"No senders available for campaign {created_campaign_id}")

        # Step 5: Create schedule
        await create_schedule(
            campaign_id=created_campaign_id,
            schedule=get_default_schedule(client_timezone)
        )
        steps_completed.append("schedule_created")

        # Step 6: Update local database (only after all EmailBison calls succeed)
        await update_sequence_status(
            sequence_id=sequence_id,
            status="sent",
            emailbison_campaign_id=created_campaign_id,
            pushed_at=datetime.utcnow()
        )

        return PushResult(
            success=True,
            emailbison_campaign_id=created_campaign_id,
            steps_completed=steps_completed
        )

    except EmailBisonAPIError as e:
        logger.error(f"EmailBison API error at step {steps_completed[-1] if steps_completed else 'init'}: {e}")

        # Attempt rollback if campaign was created
        if created_campaign_id and "campaign_create" in steps_completed:
            try:
                await archive_campaign(created_campaign_id)
                logger.info(f"Rolled back campaign {created_campaign_id}")
            except Exception as rollback_error:
                logger.error(f"Rollback failed: {rollback_error}")

        raise HTTPException(
            status_code=502,
            detail={
                "error": "EmailBison push failed",
                "failed_step": steps_completed[-1] if steps_completed else "workspace_switch",
                "completed_steps": steps_completed,
                "message": str(e)
            }
        )
```

### Error Handling Matrix

| Step | Failure Mode | Recovery Action |
|------|--------------|-----------------|
| Workspace switch | Auth error, workspace not found | Return error, no cleanup needed |
| Campaign create | API error, validation error | Return error, no cleanup needed |
| Sequence steps | Invalid format, API timeout | Archive created campaign, return error |
| Attach senders | Invalid sender IDs | Log warning, continue (campaign still usable) |
| Schedule create | Invalid timezone, API error | Log warning, continue (use EmailBison default) |
| DB update | Connection error | Log error, campaign exists in EmailBison but marked as not pushed |

### Idempotency Protection

Prevent duplicate pushes:

```python
# Before starting push
existing_push = await fetch_one("""
    SELECT emailbison_campaign_id, pushed_at
    FROM campaign_sequences
    WHERE id = $1 AND pushed_to_emailbison = TRUE
""", sequence_id)

if existing_push:
    raise HTTPException(
        status_code=400,
        detail={
            "error": "Already pushed",
            "emailbison_campaign_id": existing_push["emailbison_campaign_id"],
            "pushed_at": existing_push["pushed_at"].isoformat()
        }
    )
```

### Retry Logic for Transient Failures

```python
async def call_emailbison_with_retry(
    func: Callable,
    *args,
    max_retries: int = 3,
    retry_delay: float = 1.0
):
    """
    Retry EmailBison API calls for transient failures.
    Only retries 5xx errors and timeouts, not 4xx errors.
    """
    last_error = None

    for attempt in range(max_retries):
        try:
            return await func(*args)
        except httpx.HTTPStatusError as e:
            if e.response.status_code >= 500:
                last_error = e
                await asyncio.sleep(retry_delay * (attempt + 1))
            else:
                raise  # Don't retry 4xx errors
        except httpx.TimeoutException as e:
            last_error = e
            await asyncio.sleep(retry_delay * (attempt + 1))

    raise last_error
```

### Validation Before Push

```python
def validate_sequence_for_push(sequence: CampaignSequence) -> list[str]:
    """
    Validate sequence is ready for push. Returns list of errors.
    """
    errors = []

    # Must be approved
    if sequence.status != "approved":
        errors.append(f"Sequence status is '{sequence.status}', expected 'approved'")

    # Must have 4 emails
    if len(sequence.emails) != 4:
        errors.append(f"Sequence has {len(sequence.emails)} emails, expected 4")

    # Check email positions
    positions = [e.position for e in sequence.emails]
    if sorted(positions) != [1, 2, 3, 4]:
        errors.append(f"Invalid email positions: {positions}")

    # Validate email content
    for email in sequence.emails:
        if not email.email_body or len(email.email_body.strip()) < 10:
            errors.append(f"Email {email.position} has no/empty body")

        if email.position in [1, 3] and not email.subject_line:
            errors.append(f"Email {email.position} requires subject line (new thread)")

    # Check workspace mapping
    if not sequence.emailbison_workspace_id:
        errors.append("Client has no EmailBison workspace configured")

    return errors
```

### Logging & Observability

```python
# Structured logging for debugging
logger.info("push_to_emailbison_started", extra={
    "sequence_id": str(sequence_id),
    "client_id": str(client_id),
    "emailbison_workspace_id": emailbison_workspace_id,
    "email_count": len(sequence.emails),
    "sender_count": len(sender_email_ids)
})

# After each step
logger.info("push_step_completed", extra={
    "sequence_id": str(sequence_id),
    "step": "sequence_steps",
    "campaign_id": created_campaign_id,
    "duration_ms": step_duration
})

# On success
logger.info("push_to_emailbison_completed", extra={
    "sequence_id": str(sequence_id),
    "emailbison_campaign_id": created_campaign_id,
    "total_duration_ms": total_duration,
    "steps_completed": steps_completed
})
```

---

## Implementation Phases

### Phase 1: Update Strategy-AI Output
- Modify generation to produce 4-email sequences
- Update output schema
- Apply QA checklist to each email
- Implement value prop rotation

### Phase 2: Update Charm Database
- Add sequence storage (JSONB column recommended)
- Update API endpoints to return sequence data
- Create migration script

### Phase 3: Update Frontend
- Redesign strategy page for sequence display
- Build expandable campaign cards
- Add email editor modal
- Add sequence timeline visualization
- Update approve/deny/revision flow

### Phase 4: Update Push-to-EmailBison
- Create all 4 sequence steps with retry logic
- Transform variables
- Attach senders with graceful degradation
- Configure schedule
- Add validation, error handling, and logging

---

## Files to Reference

**Cold Email Skill** (full methodology):
- `D:\Work\Claude Campaign Copywriting Skill-20251120T015618Z-1-001\Claude Campaign Copywriting Skill\cold_email_v2_skill.txt`
- `D:\Work\Claude Campaign Copywriting Skill-20251120T015618Z-1-001\Claude Campaign Copywriting Skill\followups_md.txt`

**Current Strategy Generation**:
- `D:\Work\charm-email-os\.claude\skills\generate-strategy.md`

**Current Push Implementation**:
- `D:\Work\charm-email-os\api\routes\strategy.py` (push_to_emailbison endpoint)

**EmailBison API Reference**:
- `D:\Work\Email-Bison MCP\emailbison-api-reference-2025.yaml`
