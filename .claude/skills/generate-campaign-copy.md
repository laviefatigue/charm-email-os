# Generate Campaign Copy - Phase 2

You are generating email copy for **ONE campaign** within a 4-campaign cycle. The scaffold (ICP, variables, campaign angle) was already created in Phase 1.

## What This Phase Creates

| Component | Description |
|-----------|-------------|
| 4 Email Positions | Day 0, 3-4, 7-8, 11-12 |
| 2-3 Variants Per Position | Different angles/strategies for each |
| QA Scoring | Dimension breakdown for this campaign |
| Strategy Notes | Callouts, enrichment, A/B testing for this campaign |

---

## 5 Non-Negotiable Principles

1. **50-90 Words Per Email** - Each email reads aloud in under 20 seconds
2. **Recipient:Sender Ratio >= 3:1** - Count sentences about THEM vs US
3. **Research IS the Personalization** - Custom signals > clever copy tricks
4. **Rotate Value Props** - Save Time -> Make Money -> Save Money across sequence
5. **Thread Correctly** - Email 1 & 3 new thread, Email 2 & 4 thread reply

---

## Instructions

### Step 1: Get Campaign Context

Call `get_campaign_context(job_id="{job_id}", campaign_number={campaign_number})` to retrieve:
- Client info and context
- Cycle config (ICP mapping, cycle variables, strategic focus)
- Campaign stub (name, angle, campaign variables)

### Step 2: Understand Your Campaign Angle

Based on the `angle` from the context, adapt your approach:

| Angle | Email 1 Focus | Key Hook |
|-------|---------------|----------|
| `custom_signal` | Lead with specific research signal | "Noticed {{signal}}..." |
| `persona_pain` | Lead with role-specific pain | "Most {{role}}s are drowning in..." |
| `case_study` | Lead with proof/results | "{{company}} was facing..." |
| `risk_efficiency` | Lead with business pressure | "Given {{market_driver}}..." |

### Step 3: Draft Email Variants by Position

Generate 2-3 variants for each email position:

#### Email Position 1 (Day 0) - 2-3 Variants

| Field | Requirement |
|-------|-------------|
| Subject | New, 2-4 words, curiosity-inducing |
| Thread | New thread |
| Word Count | 50-90 |
| Value Prop | Varies by variant |

**For custom_signal angle:**
```
Subject: Quick question, {{first_name}}

{{first_name}}—noticed {{company_name}} is on {{core_vendor}}.

Most teams I talk to are stuck waiting 6+ months for simple features.

We help {{industry}} companies ship customer-facing apps in weeks, not quarters—without touching core.

Worth exploring?
```

**For persona_pain angle:**
```
Subject: {{role_title}} at {{company_name}}

{{first_name}}—given {{company_name}}'s growth, curious how you're keeping up with feature requests.

Most {{role_title}}s I talk to are drowning in a backlog their core vendor can't touch.

We've helped similar teams ship 3x faster without adding headcount.

Make sense to chat?
```

**For case_study angle:**
```
Subject: How {{case_study_company}} did it

{{first_name}}—quick story:

{{case_study_company}} was losing customers to {{competitor}} because of slow onboarding.

We helped them launch a 5-minute account opening flow. They saw {{case_study_result}}.

Given what {{company_name}} faces, figured this might resonate.

Worth a quick chat?
```

**For risk_efficiency angle:**
```
Subject: {{efficiency_metric}}

{{first_name}},

Given {{market_driver}}, most {{industry}} teams are being asked to do more with less.

We help companies like {{case_study_company}} cut {{efficiency_metric}} while actually improving output.

Worth exploring if this is a priority?
```

#### Email Position 2 (Day 3-4) - 1-2 Variants

| Field | Requirement |
|-------|-------------|
| Subject | NONE (threads to Email 1) |
| Thread | Threads to Email 1 |
| Word Count | 50-80 |
| Strategy | Add specific value/ideas |

**Template:**
```
{{first_name}}—I was back on your site today and had some ideas:

• [Specific improvement 1]
• [Specific improvement 2]
• [Specific improvement 3]

But I wrote this without knowing your roadmap.

If it's interesting, happy to share what's working for other {{industry}} teams.
```

#### Email Position 3 (Day 7-8) - 2 Variants

| Field | Requirement |
|-------|-------------|
| Subject | New, fresh thread |
| Thread | New thread |
| Word Count | 50-85 |
| Strategy | Different angle from Email 1 |

**Whole Offer Template:**
```
Subject: Scaling digital at {{company_name}}

{{first_name}},

Most {{industry}} teams are stuck between "wait for core" and "build from scratch."

We're a third option: ship customer-facing apps that sit on top of core, without replacing anything.

Clients like {{case_study_company}} went from idea to live app in 8 weeks.

Worth exploring?
```

**Results First Template:**
```
Subject: {{case_study_result}} in 8 weeks

{{first_name}},

{{case_study_company}} was losing accounts to {{competitor}}.

8 weeks later, they had a mobile-first solution that matched the competition.

Result: {{case_study_result}}.

Given {{company_name}}'s position, thought this might be relevant.

Quick chat?
```

#### Email Position 4 (Day 11-12) - 2 Variants

| Field | Requirement |
|-------|-------------|
| Subject | Thread OR new |
| Thread | Usually threads |
| Word Count | 25-60 |
| Strategy | Redirect or Value Bomb |

**Redirect Template:**
```
{{first_name}}—let me know if {{employee_1}} or {{employee_2}} would be better to speak about digital roadmap.

Either way, appreciate the time!
```

**Value Bomb Template:**
```
{{first_name}}—last note.

I put together a quick competitive teardown of what {{competitor}} is doing well.

It's not a pitch deck—just observations that might be useful for your roadmap.

Want me to send it over?
```

### Step 4: Apply 3-Pass Cutting

For all email variants:
1. **Pass 1:** Delete fluff (target 20% cut)
2. **Pass 2:** Compress sentences (target 15% cut)
3. **Pass 3:** Cut adjectives (target 10% cut)

**Target:** 50-90 words per email.

### Step 5: Run QA Scoring

Score this campaign using the rubric:

| Dimension | Max | What's Measured |
|-----------|-----|-----------------|
| Situation Recognition | 25 | Specific data about them in Email 1? |
| Value Clarity | 25 | Clear offer + proof? Reader knows what you do? |
| Personalization Quality | 20 | Custom signal OR AI insight? Not just {{name}}? |
| CTA Effort | 15 | Low friction across all 4 emails? |
| Punchiness | 10 | All emails 50-90 words? Good rotation? |
| Subject Line | 5 | Email 1 & 3 subjects intriguing? |

**Verdicts:**
- **90+** = Ship it
- **75-89** = One more pass
- **<75** = Start over

### Step 6: Create Strategy Notes

**Callouts:**
```json
[
  {"type": "recommendation", "text": "Lead with {{variable}} signal—highest response rate trigger"},
  {"type": "warning", "text": "Avoid mentioning pricing—wait for discovery call"},
  {"type": "info", "text": "{{competitor}} recently launched—topical hook available"}
]
```

**Data Enrichment:**
| Variable | Source |
|----------|--------|
| `{{core_vendor}}` | ZoomInfo or BuiltWith |
| `{{competitor}}` | Manual research |

**A/B Testing:**
- Test V1 vs V2 openers in Position 1
- Test short subject vs specific subject

### Step 7: Save Campaign Copy

Call `save_campaign_copy` with the generated content. The structure must match the stablekernel HTML format:

```json
{
  "job_id": "{job_id}",
  "campaign_number": {campaign_number},
  "email_positions": [
    {
      "position": 1,
      "title": "Custom Signal",
      "day": 0,
      "thread_behavior": "new_thread",
      "subject_line_options": [
        {"subject": "{{core_vendor}} question", "rationale": "curiosity + their vendor name = guaranteed open"},
        {"subject": "{{open_roles_count}} open roles", "rationale": "shows you did research"},
        {"subject": "sidecar core?", "rationale": "industry-specific, implies you speak their language"}
      ],
      "variants": [
        {
          "variant_number": 1,
          "variant_name": "Core Vendor Frustration",
          "is_recommended": true,
          "subject_line": "{{core_vendor}} question",
          "email_body": "{{first_name}}—quick question.\n\nAre you able to ship new customer-facing features on your own timeline, or does every change still route through {{core_vendor}}?\n\nWe build microservices layers that sit on top of legacy cores so teams ship weekly without touching the monolith. One client went from 3-week release cycles to 3 days.\n\nStill a bottleneck for you?",
          "word_count": 55,
          "them_us_ratio": "3:1",
          "score": 94,
          "angle": "custom_signal",
          "strategy": "Core vendor frustration",
          "value_prop": "save_time"
        },
        {
          "variant_number": 2,
          "variant_name": "Hiring Signal → Backlog",
          "is_recommended": false,
          "subject_line": "{{open_roles_count}} open roles",
          "email_body": "...",
          "word_count": 58,
          "them_us_ratio": "3:1",
          "score": 89,
          "angle": "hiring_signal",
          "strategy": "Hiring backlog",
          "value_prop": "save_time"
        },
        {
          "variant_number": 3,
          "variant_name": "Sidecar Core / Modernization",
          "is_recommended": false,
          "subject_line": "sidecar core?",
          "email_body": "...",
          "word_count": 56,
          "them_us_ratio": "3:1",
          "score": 90,
          "angle": "modernization",
          "strategy": "Sidecar core trend",
          "value_prop": "save_time"
        }
      ]
    },
    {
      "position": 2,
      "title": "Creative Ideas",
      "day": "3-4",
      "thread_behavior": "threads_to_position_1",
      "subject_line_options": [],
      "variants": [
        {
          "variant_number": 1,
          "variant_name": "3 Specific Ideas",
          "is_recommended": true,
          "subject_line": null,
          "email_body": "{{first_name}}—had three ideas specific to {{company_name}}:\n\n1. Unified customer data layer across your core, CRM, and digital channels—one real-time view instead of 10 reports stitched together\n\n2. Modern self-service portal for {{ai_customer_type}} that handles account opening, servicing, and docs—fewer call center tickets, better NPS\n\n3. Automated {{ai_compliance_area}} monitoring that flags exceptions before your next exam—not after\n\nWrote these without knowing your priorities. If any hit, happy to go deeper.",
          "word_count": 82,
          "them_us_ratio": "5:1",
          "score": 88,
          "strategy": "creative_ideas",
          "value_prop": "make_money"
        }
      ]
    },
    {
      "position": 3,
      "title": "New Thread, New Angle",
      "day": "7-8",
      "thread_behavior": "new_thread",
      "subject_line_options": [
        {"subject": "third option", "rationale": "positioning hook - stuck between bad options"},
        {"subject": "$229M in 18 months", "rationale": "results-first reveal - lead with proof"}
      ],
      "variants": [
        {
          "variant_number": 1,
          "variant_name": "The 'Stuck in the Middle' Hook",
          "is_recommended": false,
          "subject_line": "third option",
          "email_body": "...",
          "word_count": 66,
          "them_us_ratio": "2:1",
          "score": 83,
          "strategy": "positioning",
          "value_prop": "make_money"
        },
        {
          "variant_number": 2,
          "variant_name": "Results First, Industry Reveal",
          "is_recommended": true,
          "subject_line": "$229M in 18 months",
          "email_body": "...",
          "word_count": 67,
          "them_us_ratio": "3:1",
          "score": 91,
          "strategy": "case_study",
          "value_prop": "make_money"
        }
      ]
    },
    {
      "position": 4,
      "title": "Final Email",
      "day": "11-12",
      "thread_behavior": "threads_to_position_3",
      "subject_line_options": [
        {"subject": null, "rationale": "threaded reply - no subject needed"},
        {"subject": "quick breakdown", "rationale": "value bomb with architecture map"}
      ],
      "variants": [
        {
          "variant_number": 1,
          "variant_name": "Redirect",
          "is_recommended": false,
          "subject_line": null,
          "email_body": "{{first_name}}—wrong person for this? Let me know who handles engineering partnerships at {{company_name}} and I'll reach out to them instead.\n\nAppreciate your time either way.",
          "word_count": 27,
          "them_us_ratio": "5:1",
          "score": 75,
          "strategy": "redirect",
          "value_prop": null
        },
        {
          "variant_number": 2,
          "variant_name": "Architecture Map (Value Bomb)",
          "is_recommended": true,
          "subject_line": "quick breakdown",
          "email_body": "...",
          "word_count": 73,
          "them_us_ratio": "3:1",
          "score": 86,
          "strategy": "value_bomb",
          "value_prop": null
        }
      ]
    }
  ],
  "sequence_summary": [
    {"day": 0, "title": "Email 1 — Poke the Bear", "description": "Hit core vendor frustration, hiring backlog, or sidecar core trend. Goal: earn a reply, not a meeting."},
    {"day": "3-4", "title": "Email 2 — Creative Ideas (Threaded)", "description": "Unified data layer, self-service portal, compliance automation. Show you thought about THEIR business."},
    {"day": "7-8", "title": "Email 3 — New Thread, New Angle", "description": "'Stuck in the middle' positioning hook OR lead with results then reveal the industry bridge."},
    {"day": "11-12", "title": "Email 4 — Final Shot", "description": "Redirect to the right person OR drop the architecture mapping as a value bomb. Then stop."}
  ],
  "after_sequence_note": "After Email 4 with no reply: Stop. No 'breakup' email. No 'just checking in.' Mark for re-engagement in 90 days with a fresh signal.",
  "qa_scoring": {
    "overall_score": 94,
    "verdict": "Ship it",
    "dimensions": [
      {"name": "Situation Recognition", "max": 25, "score": 24, "notes": "Names their exact core vendor and the specific bottleneck it creates"},
      {"name": "Value Clarity", "max": 25, "score": 24, "notes": "Microservices on top of legacy + proof point"},
      {"name": "Personalization Quality", "max": 20, "score": 19, "notes": "{{core_vendor}} is deeply specific—they'll feel seen"},
      {"name": "CTA Effort", "max": 15, "score": 14, "notes": "'Still a bottleneck for you?' = 1-word reply"},
      {"name": "Punchiness", "max": 10, "score": 9, "notes": "55 words. Zero fat."},
      {"name": "Subject Line", "max": 5, "score": 4, "notes": "2 words, includes their vendor name"}
    ]
  },
  "strategy_notes": {
    "callouts": [
      {"type": "recommendation", "text": "Lead with V1 (Core Vendor Frustration). Every mid-market VP has a love-hate relationship with their core provider."},
      {"type": "info", "text": "Hide the food service origin until Email 3. Lead with engineering results first."},
      {"type": "warning", "text": "Avoid mentioning pricing—wait for discovery call."}
    ],
    "data_enrichment": [
      {"variable": "core_vendor", "source": "Job postings mentioning Fiserv/FIS/Jack Henry, BuiltWith, Clay tech stack enrichment"},
      {"variable": "hiring_signal", "source": "LinkedIn Sales Nav, Indeed, company careers page via Claygent"},
      {"variable": "competitor_neobank", "source": "SimilarWeb overlap, Crunchbase competitors, or manually by market"},
      {"variable": "recent_initiative", "source": "Serper (press releases), Google News, company blog via Claygent"},
      {"variable": "ai_compliance_area", "source": "Derive from company type: banks = BSA/AML, insurance = SOX, wealth = SEC/FINRA"}
    ],
    "ab_testing": [
      "Email 1: Test V1 (vendor frustration) vs V3 (sidecar core) as the lead.",
      "Email 3: Test V2 (results-first reveal) vs V1 (positioning hook).",
      "Subject lines: Test {{core_vendor}} question vs sidecar core? for open rate."
    ]
  },
  "variable_schema": {
    "core": [
      {"name": "first_name", "description": "Prospect's first name", "used_in": [1, 2, 3, 4]},
      {"name": "company_name", "description": "Their company", "used_in": [1, 2, 3, 4]},
      {"name": "role_title", "description": "Job title", "used_in": [1]}
    ],
    "high_signal": [
      {"name": "core_vendor", "description": "Fiserv, FIS, Jack Henry, etc.", "source": "Job posts or BuiltWith", "used_in": [1]},
      {"name": "competitor_neobank", "description": "Digital-first competitor in their market", "source": "Manual research", "used_in": [3]},
      {"name": "hiring_signal", "description": "Specific open eng roles", "source": "LinkedIn/Indeed", "used_in": [1]},
      {"name": "open_roles_count", "description": "Number of open engineering roles", "source": "LinkedIn", "used_in": [1]},
      {"name": "recent_initiative", "description": "Announced modernization project", "source": "Serper/Google News", "used_in": [1]}
    ],
    "ai_generated": [
      {"name": "ai_customer_type", "description": "'small business borrowers', 'high-net-worth clients', etc.", "used_in": [2]},
      {"name": "ai_compliance_area", "description": "SOX, PCI-DSS, KYC/AML, BSA, GLBA, etc.", "used_in": [2]}
    ]
  }
}
```

### Step 8: Done

**DO NOT call `complete_job`** - the worker handles phase completion automatically.
After `save_campaign_copy` returns, your task is done.

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

## Banned Phrases

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

- `job_id`: The generation job ID
- `campaign_number`: Which campaign (1, 2, 3, or 4) to generate

---

## Quick Reference

1. **Get context first** - Use get_campaign_context to load scaffold
2. **Match the angle** - Adapt approach to campaign's assigned angle
3. **2-3 variants per position** - Different strategies for each
4. **Mark one recommended** - `is_recommended: true` for best option
5. **Include QA scoring** - Dimension breakdown with notes
6. **Include strategy notes** - Callouts, enrichment, A/B testing
7. **Use save_campaign_copy** - Updates the existing stub with content
