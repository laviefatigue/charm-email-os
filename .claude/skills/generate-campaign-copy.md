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

Call `save_campaign_copy` with the generated content:

```json
{
  "job_id": "{job_id}",
  "campaign_number": {campaign_number},
  "email_positions": [
    {
      "position": 1,
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
          "variant_name": "Hiring Signal -> Backlog",
          "is_recommended": false,
          "subject_line": "{{role_title}} at {{company_name}}",
          "email_body": "...",
          "wait_days": 0,
          "thread_reply": false,
          "word_count": 58,
          "them_us_ratio": "3:1",
          "score": 82,
          "angle": "persona_pain",
          "value_prop": "make_money"
        }
      ]
    },
    {
      "position": 2,
      "variants": [
        {
          "variant_number": 1,
          "variant_name": "Specific Ideas",
          "is_recommended": true,
          "subject_line": null,
          "email_body": "...",
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
      "variants": [
        {
          "variant_number": 1,
          "variant_name": "Whole Offer",
          "is_recommended": true,
          "subject_line": "Scaling digital at {{company_name}}",
          "email_body": "...",
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
          "is_recommended": false,
          "subject_line": "{{case_study_result}} in 8 weeks",
          "email_body": "...",
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
      "variants": [
        {
          "variant_number": 1,
          "variant_name": "Redirect",
          "is_recommended": false,
          "subject_line": null,
          "email_body": "...",
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
          "variant_name": "Value Bomb",
          "is_recommended": true,
          "subject_line": null,
          "email_body": "...",
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
  "qa_scoring": {
    "overall_score": 87,
    "verdict": "Ship it",
    "dimensions": [
      {"name": "Situation Recognition", "score": "24/25", "notes": "Strong signal in opener"},
      {"name": "Value Clarity", "score": "23/25", "notes": "Clear value prop"},
      {"name": "Personalization Quality", "score": "18/20", "notes": "Good variable usage"},
      {"name": "CTA Effort", "score": "14/15", "notes": "Low friction CTAs"},
      {"name": "Punchiness", "score": "8/10", "notes": "Email 3 slightly long"},
      {"name": "Subject Line", "score": "5/5", "notes": "Intriguing subjects"}
    ]
  },
  "strategy_notes": {
    "callouts": [
      {"type": "recommendation", "text": "Lead with {{core_vendor}} signal"},
      {"type": "warning", "text": "Avoid pricing mentions"}
    ],
    "data_enrichment": [
      {"variable": "core_vendor", "source": "ZoomInfo"}
    ],
    "ab_testing": [
      "Test V1 vs V2 openers"
    ]
  },
  "variable_schema": {
    "core": [
      {"name": "first_name", "description": "Prospect's first name"},
      {"name": "company_name", "description": "Their company"}
    ],
    "high_signal": [
      {"name": "core_vendor", "description": "Current vendor", "source": "ZoomInfo"}
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
