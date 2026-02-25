# Generate Strategy - Full 4-Campaign Cycle Package

You are generating a **complete Cycle Package** containing **4 distinct campaigns**, each with 4 email positions and 2-3 variants per position. This creates a 14-day outbound cycle with multiple angles for testing.

## Output Architecture

| Aspect | Description |
|--------|-------------|
| Structure | 1 Cycle → 4 Campaigns → 4 Emails per campaign → 2-3 variants per email |
| Shared Config | ICP mapping, cycle variables, strategic focus (applies to all 4 campaigns) |
| Campaign Angles | Custom Signal, Persona Pain, Case Study, Risk/Efficiency |
| Total Emails | 16 emails (4 campaigns × 4 positions) |
| Total Variants | ~40 variants across all campaigns |

---

## Campaign Angle Definitions

| # | Angle | Focus | Primary Trigger | Campaign Variables |
|---|-------|-------|-----------------|-------------------|
| 1 | **Custom Signal** | Job postings, funding, tool adoption | Hiring for outbound roles, funding news | `{{job_signal}}`, `{{outbound_tool}}` |
| 2 | **Persona Pain** | Role-specific overwhelm | Day-to-day frustrations of target persona | `{{persona_pain}}`, `{{team_size}}` |
| 3 | **Case Study** | Social proof with specific results | Similar company success story | `{{case_study_company}}`, `{{case_study_result}}` |
| 4 | **Risk/Efficiency** | Board pressure, ROI, efficiency | Need to do more with less | `{{efficiency_metric}}`, `{{roi_timeline}}` |

---

## 5 Non-Negotiable Principles

1. **50-90 Words Per Email** — Each email reads aloud in under 20 seconds
2. **Recipient:Sender Ratio >= 3:1** — Count sentences about THEM vs US
3. **Research IS the Personalization** — Custom signals > clever copy tricks
4. **Rotate Value Props** — Save Time → Make Money → Save Money across sequence
5. **Thread Correctly** — Email 1 & 3 new thread, Email 2 & 4 thread reply

---

## The 4-Email Position Structure (Per Campaign)

| Position | Timing | Subject | Thread | Variants |
|----------|--------|---------|--------|----------|
| 1 | Day 0 | New (2-4 words) | New | 2-3 variants aligned to campaign angle |
| 2 | Day 3-4 | NONE | Threads to Email 1 | 1-2 variants |
| 3 | Day 7-8 | New (fresh thread) | New | 2 variants |
| 4 | Day 11-12 | Thread OR new | Optional | 2 variants |

---

## Instructions

### Step 1: Get Client Context

Call `get_client_context(client_id="{client_id}")` to retrieve:
- Company info (name, industry, product)
- Onboarding data (target customer, ICP, messaging)
- **Segments and personas** (critical for Persona Pain campaign)
- **Competitors and key differentiators**
- **Case studies and ROI results** (critical for Case Study campaign)
- **Signals** (critical for Custom Signal campaign)
- Previous suggestions and their status

### Step 2: Get Feedback Summary

Call `get_feedback_summary(client_id="{client_id}")` to learn:
- Which variants were approved (patterns that work)
- Which were denied (patterns to avoid)
- Revision requests (specific guidance)

### Step 3: Develop Shared ICP & Objection Mapping

This applies to ALL 4 campaigns in the cycle.

**Target ICP:**
```json
{
  "role": "VP Sales / Head of Growth / Founder-CEO",
  "company_type": "B2B SaaS, Series A-C",
  "company_size": "50-500 employees, scaling outbound"
}
```

**Pain Points by Category** (4 categories, 3-4 points each):

| Category | Label | Points |
|----------|-------|--------|
| Infrastructure | "Sending Infrastructure Problems" | ["Deliverability issues causing missed opportunities", "IP warmup takes months", ...] |
| Ops | "Operational Overhead" | ["SDR time wasted on manual tasks", "No visibility into what's working", ...] |
| Revenue | "Pipeline Pressure" | ["Miss quota from cold outreach", "High CAC from paid channels", ...] |
| Talent | "Team Scaling Challenges" | ["Hard to hire experienced SDRs", "Training takes too long", ...] |

**Top 3 Objections with Preemption:**

| Objection | Preemption Strategy |
|-----------|---------------------|
| "We're already using [competitor]" | Acknowledge, show differentiation via specialization |
| "We don't have budget this quarter" | Position as pipeline ROI, show payback timeline |
| "Our team is too small" | Emphasize turnkey approach, minimal lift required |

### Step 4: Define Variable Schema

**Cycle Variables (Apply to ALL 4 campaigns):**
| Variable | Description | Source |
|----------|-------------|--------|
| `{{competitor}}` | Main competitor they're considering | Onboarding form |
| `{{industry_trend}}` | Relevant market trend | Research |

**Core Variables (Always Available):**
| Variable | Description |
|----------|-------------|
| `{{first_name}}` | Prospect's first name |
| `{{company_name}}` | Their company |
| `{{role_title}}` | Job title |

**Campaign-Specific Variables (defined per campaign):**
- Campaign 1: `{{job_signal}}`, `{{outbound_tool}}`, `{{hiring_role}}`
- Campaign 2: `{{persona_pain}}`, `{{team_size}}`, `{{daily_challenge}}`
- Campaign 3: `{{case_study_company}}`, `{{case_study_result}}`, `{{case_study_timeline}}`
- Campaign 4: `{{efficiency_metric}}`, `{{roi_timeline}}`, `{{board_pressure}}`

### Step 5: Plan All 4 Campaigns

Before drafting emails, outline each campaign's approach:

| Campaign | Primary Hook | Email 1 Focus | Unique Variable |
|----------|--------------|---------------|-----------------|
| 1. Custom Signal | Hiring/tool adoption signal | "Noticed you're hiring..." | `{{hiring_role}}` |
| 2. Persona Pain | Role-specific frustration | "Most [role] I talk to..." | `{{persona_pain}}` |
| 3. Case Study | Social proof | "Quick story about [company]..." | `{{case_study_company}}` |
| 4. Risk/Efficiency | Board/ROI pressure | "Given the pressure to..." | `{{efficiency_metric}}` |

### Step 6: Draft All 16 Email Positions

Generate 4 complete campaigns, each with 4 email positions and 2-3 variants per position.

---

#### CAMPAIGN 1: Custom Signal

**Campaign Variables:** `{{job_signal}}`, `{{outbound_tool}}`, `{{hiring_role}}`

**Email 1 (Day 0) - 3 Variants:**

| Variant | Angle | Strategy | Value Prop |
|---------|-------|----------|------------|
| V1 | Hiring Signal | Job posting → scaling pain | save_time |
| V2 | Tool Signal | Using [tool] → limitation | make_money |
| V3 | Funding Signal | Recent raise → growth pressure | save_time |

**Template V1:**
```
Subject: {{hiring_role}} hire?

{{first_name}}—saw {{company_name}} is hiring a {{hiring_role}}.

When teams scale outbound, the usual blocker is infrastructure eating up SDR time.

We handle the technical side so your reps focus on conversations, not deliverability.

Worth a quick look?
```

**Email 2 (Day 3-4) - 1 Variant:**
Subject: NONE (threads to Email 1)

**Email 3 (Day 7-8) - 2 Variants:**
New thread, different angle

**Email 4 (Day 11-12) - 2 Variants:**
Redirect or Value Bomb

---

#### CAMPAIGN 2: Persona Pain

**Campaign Variables:** `{{persona_pain}}`, `{{team_size}}`, `{{daily_challenge}}`

**Email 1 (Day 0) - 2 Variants:**

| Variant | Angle | Strategy | Value Prop |
|---------|-------|----------|------------|
| V1 | SDR Overwhelm | Too many tools, not enough time | save_time |
| V2 | Manager Pressure | Pipeline visibility gaps | make_money |

**Template V1:**
```
Subject: SDR bandwidth

{{first_name}}—most {{role_title}}s I talk to are drowning in manual work.

Between list building, sequencing, and inbox management, actual selling gets squeezed.

We automate the infrastructure so your team can focus on conversations.

Make sense to explore?
```

---

#### CAMPAIGN 3: Case Study

**Campaign Variables:** `{{case_study_company}}`, `{{case_study_result}}`, `{{case_study_timeline}}`

**Email 1 (Day 0) - 2 Variants:**

| Variant | Angle | Strategy | Value Prop |
|---------|-------|----------|------------|
| V1 | Similar Company | Peer comparison | make_money |
| V2 | Specific Result | Lead with number | save_money |

**Template V1:**
```
Subject: How {{case_study_company}} did it

{{first_name}}—quick story:

{{case_study_company}} was struggling to scale outbound. Deliverability issues meant missed opportunities.

After working with us, they hit {{case_study_result}} in {{case_study_timeline}}.

Given what {{company_name}} is building, thought this might resonate.

Worth a chat?
```

---

#### CAMPAIGN 4: Risk/Efficiency

**Campaign Variables:** `{{efficiency_metric}}`, `{{roi_timeline}}`, `{{board_pressure}}`

**Email 1 (Day 0) - 2 Variants:**

| Variant | Angle | Strategy | Value Prop |
|---------|-------|----------|------------|
| V1 | Do More With Less | Efficiency pressure | save_money |
| V2 | Board Expectations | Growth without headcount | save_time |

**Template V1:**
```
Subject: Doing more with less

{{first_name}}—heard this from a few {{role_title}}s lately:

"We need to 2x pipeline without 2x headcount."

We help teams hit {{efficiency_metric}} improvement in outbound efficiency—typically in {{roi_timeline}}.

Worth exploring?
```

---

### Step 7: Apply 3-Pass Cutting to All Emails

For all 16 email positions across 4 campaigns:
1. Pass 1: Delete fluff (target 20% cut)
2. Pass 2: Compress sentences (target 15% cut)
3. Pass 3: Cut adjectives (target 10% cut)

Target: 50-90 words per email.

### Step 8: Run QA Scoring Per Campaign

Score each campaign's recommended variants:

| Dimension | Max | Notes |
|-----------|-----|-------|
| Situation Recognition | 25 | Specific data about them in Email 1? |
| Value Clarity | 25 | Clear offer + proof? |
| Personalization Quality | 20 | Custom signal OR insight? |
| CTA Effort | 15 | Low friction across all 4 emails? |
| Punchiness | 10 | All emails 50-90 words? |
| Subject Line | 5 | Intriguing subjects? |

**Per-Campaign Verdict:**
- 90+ = Ship it
- 75-89 = One more pass
- <75 = Needs work

**Overall Cycle Score:** Average of 4 campaign scores

### Step 9: Create Strategy Notes Per Campaign

For each campaign, document:

**Callouts:**
```json
[
  {"type": "recommendation", "text": "Lead with hiring signal for highest response rate"},
  {"type": "warning", "text": "Avoid pricing mentions in cold emails"}
]
```

**A/B Testing Recommendations:**
- Campaign 1: Test V1 (Hiring) vs V2 (Tool) openers
- Campaign 3: Test V1 (Story) vs V2 (Number) openers

### Step 10: Save Cycle Package

Call `save_cycle_package` with the complete 4-campaign structure:

```json
{
  "job_id": "{job_id}",
  "cycle_name": "{Client Name} Outbound Cycle v1",
  "cycle_config": {
    "icp_mapping": {
      "target_icp": {
        "role": "VP Sales / Head of Growth",
        "company_type": "B2B SaaS, Series A-C",
        "company_size": "50-500 employees"
      },
      "pain_points": [
        {"category": "Infrastructure", "label": "Sending Problems", "points": ["..."]},
        {"category": "Ops", "label": "Operational Overhead", "points": ["..."]},
        {"category": "Revenue", "label": "Pipeline Pressure", "points": ["..."]},
        {"category": "Talent", "label": "Team Scaling", "points": ["..."]}
      ],
      "objections": [
        {"objection": "Using competitor", "preemption": "Show differentiation"},
        {"objection": "No budget", "preemption": "Position as ROI"},
        {"objection": "Team too small", "preemption": "Emphasize turnkey"}
      ]
    },
    "cycle_variables": [
      {"name": "competitor", "description": "Main competitor", "source": "Onboarding"},
      {"name": "industry_trend", "description": "Relevant trend", "source": "Research"}
    ],
    "strategic_focus": "Scale outbound pipeline without scaling headcount",
    "target_outcome": "15+ qualified meetings per month from cold outreach",
    "vertical": "B2B SaaS",
    "objective": "Generate qualified pipeline from VP-level decision makers"
  },
  "campaigns": [
    {
      "campaign_number": 1,
      "campaign_name": "Custom Signal Campaign",
      "angle": "custom_signal",
      "campaign_variables": [
        {"name": "job_signal", "description": "Hiring signal from job postings"},
        {"name": "outbound_tool", "description": "Current outbound tool"},
        {"name": "hiring_role", "description": "Role they're hiring for"}
      ],
      "email_positions": [
        {
          "position": 1,
          "title": "Email 1: Hiring Signal — Day 0",
          "variants": [
            {
              "variant_number": 1,
              "variant_name": "Hiring Signal Opener",
              "is_recommended": true,
              "subject_line": "{{hiring_role}} hire?",
              "email_body": "{{first_name}}—saw {{company_name}} is hiring...",
              "wait_days": 0,
              "thread_reply": false,
              "word_count": 65,
              "them_us_ratio": "4:1",
              "score": 87,
              "angle": "custom_signal",
              "value_prop": "save_time"
            }
          ]
        }
      ],
      "qa_scoring": {
        "overall_score": 87,
        "verdict": "Ship it",
        "dimensions": [
          {"name": "Situation Recognition", "score": "24/25", "notes": "Strong hiring signal"}
        ]
      },
      "strategy_notes": {
        "callouts": [{"type": "recommendation", "text": "Hiring signal = highest response"}],
        "ab_testing": ["Test Hiring vs Tool signal in Position 1"]
      }
    },
    {
      "campaign_number": 2,
      "campaign_name": "Persona Pain Campaign",
      "angle": "persona_pain",
      "campaign_variables": [
        {"name": "persona_pain", "description": "Role-specific pain point"},
        {"name": "team_size", "description": "SDR team size"},
        {"name": "daily_challenge", "description": "Daily frustration"}
      ],
      "email_positions": [],
      "qa_scoring": {"overall_score": 85, "verdict": "Ship it"},
      "strategy_notes": {}
    },
    {
      "campaign_number": 3,
      "campaign_name": "Case Study Campaign",
      "angle": "case_study",
      "campaign_variables": [
        {"name": "case_study_company", "description": "Reference customer"},
        {"name": "case_study_result", "description": "Specific result achieved"},
        {"name": "case_study_timeline", "description": "Time to achieve result"}
      ],
      "email_positions": [],
      "qa_scoring": {"overall_score": 88, "verdict": "Ship it"},
      "strategy_notes": {}
    },
    {
      "campaign_number": 4,
      "campaign_name": "Risk/Efficiency Campaign",
      "angle": "risk_efficiency",
      "campaign_variables": [
        {"name": "efficiency_metric", "description": "Efficiency improvement target"},
        {"name": "roi_timeline", "description": "Time to ROI"},
        {"name": "board_pressure", "description": "Board/investor pressure point"}
      ],
      "email_positions": [],
      "qa_scoring": {"overall_score": 84, "verdict": "One more pass"},
      "strategy_notes": {}
    }
  ],
  "overall_qa_score": 86,
  "overall_verdict": "Ship it"
}
```

### Step 11: Complete Job

Call `complete_job(job_id="{job_id}")` when all 4 campaigns are saved.

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

- `client_id`: The UUID of the client to generate the cycle for
- `job_id`: The generation job ID to associate the cycle with
- `submission_id`: (Optional) Specific onboarding submission to use

---

## Quick Reference

1. **1 cycle = 4 campaigns** — Custom Signal, Persona Pain, Case Study, Risk/Efficiency
2. **4 emails per campaign** — 4 positions with threading rules
3. **2-3 variants per email** — different angles/strategies
4. **Shared ICP mapping** — applies to all 4 campaigns
5. **Campaign-specific variables** — unique to each angle
6. **Per-campaign QA scoring** — plus overall cycle score
7. **Use `save_cycle_package`** — NOT save_campaign_document for full cycles
