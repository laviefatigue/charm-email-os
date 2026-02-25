# Generate Strategy - Campaign Document with Variants

You are generating a **single Campaign Document** containing **multiple variants per email position**. This replaces the old 4-campaigns approach with a stablekernel-style document that includes ICP mapping, variable schema, QA scoring, and strategy notes.

## Output Architecture

| Aspect | Description |
|--------|-------------|
| Structure | 1 document with 4 email positions, each with 2-3 variants |
| ICP Mapping | Target ICP, pain points by category, objections with preemption |
| Variable Schema | Core, High-Signal, AI-Generated variables with sources |
| QA Scoring | Detailed breakdown by dimension (25/25, 24/25, etc.) |
| Strategy Notes | Callouts, data enrichment sources, A/B testing recommendations |

---

## 5 Non-Negotiable Principles

1. **50-90 Words Per Email** — Each email reads aloud in under 20 seconds
2. **Recipient:Sender Ratio >= 3:1** — Count sentences about THEM vs US
3. **Research IS the Personalization** — Custom signals > clever copy tricks
4. **Rotate Value Props** — Save Time → Make Money → Save Money across sequence
5. **Thread Correctly** — Email 1 & 3 new thread, Email 2 & 4 thread reply

---

## The 4-Email Position Structure

| Position | Timing | Subject | Thread | Variants |
|----------|--------|---------|--------|----------|
| 1 | Day 0 | New (2-4 words) | New | 3 variants: Custom Signal, Persona Pain, Case Study |
| 2 | Day 3-4 | NONE | Threads to Email 1 | 1-2 variants: Creative Ideas |
| 3 | Day 7-8 | New (fresh thread) | New | 2 variants: Whole Offer, Case Study Deep Dive |
| 4 | Day 11-12 | Thread OR new | Optional | 2 variants: Redirect, Value Bomb |

---

## The "3 Offers" Framework (Value Prop Rotation)

Every email should lead with one of these, rotating through the sequence:

1. **Save Time** — Efficiency, automation, less manual work
2. **Make Money** — Increase revenue, conversions, pipeline
3. **Save Money** — Reduce costs, better ROI, do more with same team

---

## Instructions

### Step 1: Get Client Context

Call `get_client_context(client_id="{client_id}")` to retrieve:
- Company info (name, industry, product)
- Onboarding data (target customer, ICP, messaging)
- **Segments and personas** (critical for variant targeting)
- **Competitors and key differentiators**
- Case studies and ROI results
- Previous suggestions and their status

### Step 2: Get Feedback Summary

Call `get_feedback_summary(client_id="{client_id}")` to learn:
- Which variants were approved (patterns that work)
- Which were denied (patterns to avoid)
- Revision requests (specific guidance)

### Step 3: Develop ICP & Objection Mapping

Based on client context, create the ICP mapping section:

**Target ICP:**
```json
{
  "role": "VP of Finance / CFO",
  "company_type": "Regional Banks, Credit Unions, Community Banks",
  "company_size": "$500M - $5B in assets"
}
```

**Pain Points by Category** (4 categories, 3-4 points each):

| Category | Label | Points |
|----------|-------|--------|
| Tech Debt | "Legacy System Constraints" | ["Core banking contracts lock innovation", "Mobile apps behind neobanks", ...] |
| Talent | "Build vs Buy Dilemma" | ["In-house dev teams are expensive", "Hard to attract fintech talent", ...] |
| Competition | "Competitive Pressure" | ["Neobanks offer instant account opening", "Big banks have deeper pockets", ...] |
| Ops | "Operational Friction" | ["Branch + digital creates ops overhead", ...] |

**Top 3 Objections with Preemption:**

| Objection | Preemption Strategy |
|-----------|---------------------|
| "We're already working with {{competitor}}" | Acknowledge competitor, show differentiation via specialization |
| "We don't have budget this quarter" | Position as cost-saving, show ROI timeline |
| "Our IT team is stretched thin" | Emphasize turnkey implementation, minimal IT burden |

### Step 4: Define Variable Schema

Document all variables used across the campaign:

**Core Variables (Always Available):**
| Variable | Description |
|----------|-------------|
| `{{first_name}}` | Prospect's first name |
| `{{company_name}}` | Their company |
| `{{role_title}}` | Job title |

**High-Signal Variables (From Enrichment):**
| Variable | Description | Source |
|----------|-------------|--------|
| `{{core_vendor}}` | Current core banking vendor | ZoomInfo or LinkedIn |
| `{{competitor_neobank}}` | Regional neobank competitor | Manual research |
| `{{recent_announcement}}` | Recent news/PR about company | Google News |

**AI-Generated Variables:**
| Variable | Description |
|----------|-------------|
| `{{ai_customer_type}}` | Inferred customer segment (e.g., "small business owners") |
| `{{ai_pain_summary}}` | One-line pain point summary from research |

### Step 5: ICP Role-Play

Answer these 4 questions before drafting:

1. **How are they doing this now?** (Current state, tools, manual processes)
2. **Why would they switch?** (What's broken? The "last straw" moment?)
3. **What objections will they have?** ("We already have X", "No budget")
4. **What's their personal benefit?** (Not company ROI—what do THEY get?)

### Step 6: Draft Email Variants by Position

Generate multiple variants for each email position:

#### Email Position 1 (Day 0) - 3 Variants

| Variant | Angle | Strategy | Value Prop | Mark |
|---------|-------|----------|------------|------|
| V1 | Custom Signal | Core vendor frustration | save_time | `is_recommended: true` |
| V2 | Persona Pain | Hiring signal → backlog | make_money | |
| V3 | Case Study | Proof-first opener | save_money | |

**Template for V1 (Custom Signal):**
```
Subject: Quick question, {{first_name}}

{{first_name}}—noticed {{company_name}} is on {{core_vendor}}.

Most teams I talk to are stuck waiting 6+ months for simple features.

We help {{industry}} companies ship customer-facing apps in weeks, not quarters—without touching core.

Worth exploring?
```

**Template for V2 (Persona Pain):**
```
Subject: {{role_title}} at {{company_name}}

{{first_name}}—given {{company_name}}'s growth, curious how you're keeping up with feature requests.

Most {{role_title}}s I talk to are drowning in a backlog their core vendor can't touch.

We've helped similar teams ship 3x faster without adding headcount.

Make sense to chat?
```

**Template for V3 (Case Study):**
```
Subject: How {{case_study_company}} did it

{{first_name}}—quick story:

{{case_study_company}} was losing customers to {{competitor_neobank}} because of slow onboarding.

We helped them launch a 5-minute account opening flow. They saw {{case_study_result}}.

Given what {{company_name}} faces, figured this might resonate.

Worth a quick chat?
```

#### Email Position 2 (Day 3-4) - 1-2 Variants

**Subject**: NONE (threads to Email 1)

| Variant | Angle | Strategy |
|---------|-------|----------|
| V1 | Creative Ideas | Specific ideas based on research |

**Template:**
```
{{first_name}}—I was back on your site today and had some ideas:

• Mobile deposit UX could match what {{competitor_neobank}} offers
• Self-service account opening would reduce branch load
• Real-time notifications would improve engagement

But I wrote this without knowing your roadmap.

If it's interesting, happy to share what's working for other {{industry}} teams.
```

#### Email Position 3 (Day 7-8) - 2 Variants

| Variant | Angle | Strategy | Value Prop | Mark |
|---------|-------|----------|------------|------|
| V1 | Whole Offer | Direct, drop AI | save_money | |
| V2 | Results First | Case study deep dive | make_money | `is_recommended: true` |

**Template for V1 (Whole Offer):**
```
Subject: Scaling digital at {{company_name}}

{{first_name}},

Most {{industry}} teams are stuck between "wait for core" and "build from scratch."

We're a third option: ship customer-facing apps that sit on top of core, without replacing anything.

Clients like {{case_study_company}} went from idea to live app in 8 weeks.

Worth exploring?
```

**Template for V2 (Results First):**
```
Subject: {{case_study_result}} in 8 weeks

{{first_name}},

{{case_study_company}} was losing accounts to neobanks.

8 weeks later, they had a mobile-first account opening flow that matched the competition.

Result: {{case_study_result}}.

Given {{company_name}}'s position, thought this might be relevant.

Quick chat?
```

#### Email Position 4 (Day 11-12) - 2 Variants

| Variant | Angle | Strategy | Mark |
|---------|-------|----------|------|
| V1 | Redirect | Colleague handoff | |
| V2 | Value Bomb | Send actual asset | `is_recommended: true` |

**Template for V1 (Redirect):**
```
{{first_name}}—let me know if {{employee_1}} or {{employee_2}} would be better to speak about digital roadmap.

Either way, appreciate the time!
```

**Template for V2 (Value Bomb):**
```
{{first_name}}—last note.

I put together a quick competitive teardown of what {{competitor_neobank}} is doing well.

It's not a pitch deck—just observations that might be useful for your roadmap.

Want me to send it over?
```

### Step 7: Apply 3-Pass Cutting to All Emails

For all email variants:
1. Pass 1: Delete fluff (target 20% cut)
2. Pass 2: Compress sentences (target 15% cut)
3. Pass 3: Cut adjectives (target 10% cut)

Target: 50-90 words per email.

### Step 8: Run QA Scoring with Dimension Breakdown

Score the recommended variants (lead variant per position) using this rubric:

| Dimension | Max | Score | Notes |
|-----------|-----|-------|-------|
| Situation Recognition | 25 | ? | Specific data about them in Email 1? |
| Value Clarity | 25 | ? | Clear offer + proof? Reader knows what you do? |
| Personalization Quality | 20 | ? | Custom signal OR AI insight? Not just {{name}}? |
| CTA Effort | 15 | ? | Low friction across all 4 emails? |
| Punchiness | 10 | ? | All emails 50-90 words? Good rotation? |
| Subject Line | 5 | ? | Email 1 & 3 subjects intriguing? |

**Verdict Thresholds:**
- **90+** = "Ship it"
- **75-89** = "One more pass"
- **<75** = "Start over"

### Step 9: Create Strategy Notes

Document strategic recommendations:

**Callouts** (type: recommendation, warning, or info):
```json
[
  {"type": "recommendation", "text": "Lead with {{core_vendor}} signal—highest response rate trigger for this ICP"},
  {"type": "warning", "text": "Avoid mentioning pricing in cold emails—their objection is 'no budget' so wait for call"},
  {"type": "info", "text": "{{competitor_neobank}} recently launched in their market—topical hook opportunity"}
]
```

**Data Enrichment Sources:**
| Variable | Source |
|----------|--------|
| `{{core_vendor}}` | ZoomInfo or BuiltWith |
| `{{competitor_neobank}}` | Manual research, LinkedIn |
| `{{recent_announcement}}` | Google News alert |

**A/B Testing Recommendations:**
- Test V1 (Core Vendor) vs V3 (Case Study) openers in Position 1
- Test short subject ("Quick q") vs specific ("How {{case_study_company}} did it")
- Test Redirect vs Value Bomb in Position 4

### Step 10: Save Campaign Document

Call `save_campaign_document` with the complete document structure:

```json
{
  "job_id": "{job_id}",
  "document_name": "{Client Name} {Vertical} Campaign v1",
  "vertical": "Financial Services",
  "objective": "Generate qualified meetings with VP/C-level at regional banks looking to modernize digital offerings",
  "icp_mapping": {
    "target_icp": {
      "role": "VP of Finance / CFO",
      "company_type": "Regional Banks, Credit Unions",
      "company_size": "$500M - $5B in assets"
    },
    "pain_points": [
      {
        "category": "Tech Debt",
        "label": "Legacy System Constraints",
        "points": ["Core banking contracts lock innovation", "Mobile apps behind neobanks"]
      },
      {
        "category": "Talent",
        "label": "Build vs Buy Dilemma",
        "points": ["In-house dev teams expensive", "Hard to attract fintech talent"]
      }
    ],
    "objections": [
      {"objection": "We're already working with {{competitor}}", "preemption": "Acknowledge, show differentiation"},
      {"objection": "No budget this quarter", "preemption": "Position as cost-saving, show ROI"},
      {"objection": "IT team is stretched", "preemption": "Emphasize turnkey, minimal IT burden"}
    ]
  },
  "variable_schema": {
    "core": [
      {"name": "first_name", "description": "Prospect's first name"},
      {"name": "company_name", "description": "Their company"},
      {"name": "role_title", "description": "Job title"}
    ],
    "high_signal": [
      {"name": "core_vendor", "description": "Current core banking vendor", "source": "ZoomInfo"},
      {"name": "competitor_neobank", "description": "Regional neobank competitor", "source": "Manual research"}
    ],
    "ai_generated": [
      {"name": "ai_customer_type", "description": "Inferred customer segment"}
    ]
  },
  "email_positions": [
    {
      "position": 1,
      "title": "Email 1: Custom Signal — Day 0",
      "variants": [
        {
          "variant_number": 1,
          "variant_name": "Core Vendor Frustration",
          "is_recommended": true,
          "subject_line": "Quick question, {{first_name}}",
          "email_body": "{{first_name}}—noticed {{company_name}} is on {{core_vendor}}...",
          "wait_days": 0,
          "thread_reply": false,
          "word_count": 65,
          "them_us_ratio": "4:1",
          "score": 87,
          "angle": "custom_signal",
          "strategy": "Core vendor frustration",
          "value_prop": "save_time"
        },
        {
          "variant_number": 2,
          "variant_name": "Hiring Signal → Backlog",
          "is_recommended": false,
          "subject_line": "{{role_title}} at {{company_name}}",
          "email_body": "{{first_name}}—given {{company_name}}'s growth...",
          "wait_days": 0,
          "thread_reply": false,
          "word_count": 58,
          "them_us_ratio": "3:1",
          "score": 82,
          "angle": "persona_pain",
          "value_prop": "make_money"
        },
        {
          "variant_number": 3,
          "variant_name": "Case Study Opener",
          "is_recommended": false,
          "subject_line": "How {{case_study_company}} did it",
          "email_body": "{{first_name}}—quick story...",
          "wait_days": 0,
          "thread_reply": false,
          "word_count": 72,
          "them_us_ratio": "3:1",
          "score": 85,
          "angle": "case_study",
          "value_prop": "save_money"
        }
      ],
      "subject_options": [
        {"subject_line": "Quick question, {{first_name}}", "rationale": "Curiosity gap, personal"},
        {"subject_line": "{{core_vendor}} question", "rationale": "High-signal, specific"},
        {"subject_line": "How {{case_study_company}} did it", "rationale": "Social proof, story-based"}
      ]
    },
    {
      "position": 2,
      "title": "Email 2: Creative Ideas — Day 3-4",
      "variants": [
        {
          "variant_number": 1,
          "variant_name": "Specific Ideas",
          "is_recommended": true,
          "subject_line": null,
          "email_body": "{{first_name}}—I was back on your site...",
          "wait_days": 3,
          "thread_reply": true,
          "word_count": 62,
          "them_us_ratio": "5:1",
          "score": 84,
          "strategy": "creative_ideas",
          "value_prop": "make_money"
        }
      ]
    },
    {
      "position": 3,
      "title": "Email 3: Whole Offer — Day 7-8",
      "variants": [
        {
          "variant_number": 1,
          "variant_name": "Direct Whole Offer",
          "is_recommended": false,
          "subject_line": "Scaling digital at {{company_name}}",
          "email_body": "{{first_name}}, Most {{industry}} teams...",
          "wait_days": 4,
          "thread_reply": false,
          "word_count": 58,
          "them_us_ratio": "3:1",
          "score": 80,
          "strategy": "whole_offer",
          "value_prop": "save_money"
        },
        {
          "variant_number": 2,
          "variant_name": "Results First",
          "is_recommended": true,
          "subject_line": "{{case_study_result}} in 8 weeks",
          "email_body": "{{first_name}}, {{case_study_company}} was losing...",
          "wait_days": 4,
          "thread_reply": false,
          "word_count": 55,
          "them_us_ratio": "4:1",
          "score": 88,
          "strategy": "case_study",
          "value_prop": "make_money"
        }
      ]
    },
    {
      "position": 4,
      "title": "Email 4: Value Bomb — Day 11-12",
      "variants": [
        {
          "variant_number": 1,
          "variant_name": "Redirect",
          "is_recommended": false,
          "subject_line": null,
          "email_body": "{{first_name}}—let me know if {{employee_1}}...",
          "wait_days": 4,
          "thread_reply": true,
          "word_count": 22,
          "them_us_ratio": "5:1",
          "score": 75,
          "strategy": "redirect",
          "value_prop": null
        },
        {
          "variant_number": 2,
          "variant_name": "Competitive Teardown",
          "is_recommended": true,
          "subject_line": null,
          "email_body": "{{first_name}}—last note. I put together...",
          "wait_days": 4,
          "thread_reply": true,
          "word_count": 45,
          "them_us_ratio": "4:1",
          "score": 86,
          "strategy": "value_bomb",
          "value_prop": null
        }
      ]
    }
  ],
  "sequence_summary": [
    {"day": "Day 0", "title": "Email 1: Custom Signal", "description": "Lead with specific research about their situation"},
    {"day": "Day 3-4", "title": "Email 2: Creative Ideas", "description": "Thread reply with specific, actionable ideas"},
    {"day": "Day 7-8", "title": "Email 3: Fresh Thread", "description": "New subject, whole offer or case study"},
    {"day": "Day 11-12", "title": "Email 4: Final Touch", "description": "Redirect or value bomb to close"}
  ],
  "qa_scoring": {
    "overall_score": 87,
    "verdict": "Ship it",
    "dimensions": [
      {"name": "Situation Recognition", "score": "24/25", "notes": "Strong core vendor signal in opener"},
      {"name": "Value Clarity", "score": "23/25", "notes": "Clear 'ship in weeks' value prop"},
      {"name": "Personalization Quality", "score": "18/20", "notes": "Good variable usage, could add more research signals"},
      {"name": "CTA Effort", "score": "14/15", "notes": "All CTAs answerable in 5 words or less"},
      {"name": "Punchiness", "score": "8/10", "notes": "Email 3 slightly long at 72 words"},
      {"name": "Subject Line", "score": "5/5", "notes": "Intriguing without being clickbait"}
    ]
  },
  "strategy_notes": {
    "callouts": [
      {"type": "recommendation", "text": "Lead with {{core_vendor}} signal—highest response rate trigger"},
      {"type": "warning", "text": "Avoid pricing mentions—wait for discovery call"},
      {"type": "info", "text": "{{competitor_neobank}} recently launched—topical hook available"}
    ],
    "data_enrichment": [
      {"variable": "core_vendor", "source": "ZoomInfo or BuiltWith"},
      {"variable": "competitor_neobank", "source": "Manual research"},
      {"variable": "recent_announcement", "source": "Google News alert"}
    ],
    "ab_testing": [
      "Test V1 vs V3 openers in Position 1",
      "Test short subject vs specific subject",
      "Test Redirect vs Value Bomb in Position 4"
    ]
  }
}
```

### Step 11: Complete Job

Call `complete_job(job_id="{job_id}")` when the document is saved.

---

## 11-Point QA Checklist (Per Email Variant)

Before including each email, verify:

1. **First line = specific signal** (Position 1) OR **different angle** (Position 2-4)
2. **No hallucinations** (every fact verifiable)
3. **Variables formatted {{correctly}}**
4. **No banned phrases**
5. **Recipient:sender ratio >= 3:1**
6. **50-90 words**
7. **CTA = low-effort** (5 words to reply)
8. **Reads in under 20 seconds**
9. **Value prop rotated** (different from previous position)
10. **Threading correct** (Position 2 threads, Position 3 fresh)
11. **"Would I reply?" = YES**

---

## Scoring Rubric (0-100)

| Dimension | Points | What's Measured |
|-----------|--------|-----------------|
| Situation Recognition | 25 | Specific data about them in Email 1? |
| Value Clarity | 25 | Clear offer + proof? Reader knows what you do? |
| Personalization Quality | 20 | Custom signal OR AI insight? Not just {{name}}? |
| CTA Effort | 15 | Low friction across all 4 emails? |
| Punchiness | 10 | All emails 50-90 words? Good rotation? |
| Subject Lines | 5 | Email 1 & 3 subjects intriguing? |

**Verdicts:**
- **90+** = Ship it
- **75-89** = One more pass
- **<75** = Start over

---

## Banned Phrases (Delete & Rewrite)

**Generic Openers:**
- "I hope this email finds you well"
- "I wanted to reach out"
- "I came across your profile"
- "Just wanted to touch base"

**Weak Value Props:**
- "We help companies..." (unless followed by case study)
- "Our solution..."

**High-Effort CTAs:**
- Any request for "15 minutes" or "30 minutes"
- "Would love to schedule..."

**Hedging:**
- "I think", "perhaps", "maybe"
- "I was wondering if"

---

## Parameters

- `client_id`: The UUID of the client to generate the document for
- `job_id`: The generation job ID to associate the document with
- `submission_id`: (Optional) Specific onboarding submission to use

---

## Quick Reference

1. **1 document per generation** — with 4 email positions
2. **2-3 variants per position** — different angles/strategies
3. **Mark recommended variants** — `is_recommended: true` for best option
4. **Include ICP mapping** — target, pain points, objections
5. **Include variable schema** — core, high-signal, AI-generated
6. **Include QA scoring** — dimension breakdown with notes
7. **Include strategy notes** — callouts, enrichment, A/B testing
8. **Use `save_campaign_document`** — NOT save_campaign_batch
