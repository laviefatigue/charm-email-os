# Generate Strategy Scaffold - Phase 1

You are creating the **Strategy Scaffold** - the foundation for a 4-campaign cycle. This is Phase 1 of a 2-phase generation process. Phase 2 (generate-campaign-copy.md) will create the email content.

## What This Phase Creates

| Component | Description |
|-----------|-------------|
| Campaign Cycle | 14-day cycle record in the database |
| Cycle Strategy Config | ICP mapping, cycle variables, strategic focus |
| 4 Campaign Stubs | Name, angle, campaign-level variables (NO email content) |

**NOT created in this phase:** Email content, QA scoring for emails, strategy notes for emails.

---

## Campaign Angles (Fixed Structure)

| # | Angle | Focus | Primary Signal |
|---|-------|-------|----------------|
| 1 | `custom_signal` | Job postings, funding, tool adoption | High-signal research triggers |
| 2 | `persona_pain` | Role-specific overwhelm, challenges | Pain-first messaging |
| 3 | `case_study` | Social proof, specific results | Proof-first messaging |
| 4 | `risk_efficiency` | Board pressure, ROI, efficiency | Business outcome focus |

---

## Instructions

### Step 1: Get Client Context

Call `get_client_context(client_id="{client_id}")` to retrieve:
- Company info (name, industry, product)
- Onboarding data (target customer, ICP, messaging)
- Segments and personas
- Competitors and differentiators
- Case studies and ROI results
- Signals and triggers

### Step 2: Get Feedback Summary

Call `get_feedback_summary(client_id="{client_id}")` to learn:
- Which approaches were approved (patterns that work)
- Which were denied (patterns to avoid)
- Revision requests (specific guidance)

### Step 3: Develop ICP Mapping

Based on client context, create comprehensive ICP mapping:

**Target ICP:**
```json
{
  "role": "VP of Finance / CFO",
  "company_type": "Regional Banks, Credit Unions",
  "company_size": "$500M - $5B in assets"
}
```

**Pain Points by Category** (4 categories, 3-4 points each):

| Category | Label | Points |
|----------|-------|--------|
| Tech Debt | "Legacy System Constraints" | ["Core systems limit innovation", "Mobile behind competitors", ...] |
| Talent | "Build vs Buy Dilemma" | ["In-house teams expensive", "Hard to attract talent", ...] |
| Competition | "Competitive Pressure" | ["Neobanks offer better UX", "Big players have deeper pockets", ...] |
| Ops | "Operational Friction" | ["Manual processes slow growth", ...] |

**Top 3 Objections with Preemption:**

| Objection | Preemption Strategy |
|-----------|---------------------|
| "We're already working with {{competitor}}" | Acknowledge, show differentiation |
| "We don't have budget this quarter" | Position as cost-saving, show ROI |
| "Our team is stretched thin" | Emphasize turnkey implementation |

### Step 4: Define Cycle Variables

Variables that apply across ALL 4 campaigns:

**Cycle-Level Variables:**
| Variable | Description | Source |
|----------|-------------|--------|
| `{{competitor}}` | Main competitor they might be using | Enrichment |
| `{{industry_trend}}` | Current trend affecting their space | Research |
| `{{market_driver}}` | External force driving change | Industry news |

### Step 5: Plan Campaign Angles with Campaign Variables

For each of the 4 campaigns, define:

**Campaign 1: Custom Signal**
- Focus: Job postings, funding triggers, tool adoption signals
- Campaign Variables:
  - `{{job_signal}}`: Recent hiring indicator
  - `{{hiring_role}}`: Specific role they're hiring for
  - `{{tech_signal}}`: Technology they're evaluating

**Campaign 2: Persona Pain**
- Focus: Role-specific overwhelm and challenges
- Campaign Variables:
  - `{{persona_pain}}`: Primary pain point for this role
  - `{{team_size}}`: Size of their team (understaffed signal)
  - `{{backlog_indicator}}`: Signs of overwhelming workload

**Campaign 3: Case Study**
- Focus: Social proof with specific results
- Campaign Variables:
  - `{{case_study_company}}`: Reference customer name
  - `{{case_study_result}}`: Quantified result achieved
  - `{{similar_challenge}}`: Challenge they shared with prospect

**Campaign 4: Risk/Efficiency**
- Focus: Board pressure, ROI, efficiency gains
- Campaign Variables:
  - `{{efficiency_metric}}`: Key efficiency gain possible
  - `{{risk_factor}}`: Business risk they're facing
  - `{{roi_timeline}}`: Time to see results

### Step 6: Define Strategic Focus

Create the overall strategic direction for this cycle:

```
Strategic Focus: "Position as the fast-track alternative to waiting on legacy vendors,
focusing on banks' need to compete with neobanks on digital experience"

Target Outcome: "Generate 8-12 qualified meetings with VP/C-level at regional banks
actively evaluating digital transformation options"
```

### Step 7: Save Cycle Scaffold

Call `save_cycle_scaffold` with the complete structure:

```json
{
  "job_id": "{job_id}",
  "client_id": "{client_id}",
  "cycle_config": {
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
          "points": ["Core systems limit innovation", "Mobile behind competitors"]
        },
        // ... 3 more categories
      ],
      "objections": [
        {"objection": "Already working with {{competitor}}", "preemption": "Acknowledge, show differentiation"},
        {"objection": "No budget this quarter", "preemption": "Position as cost-saving"},
        {"objection": "Team is stretched", "preemption": "Emphasize turnkey implementation"}
      ]
    },
    "cycle_variables": [
      {"name": "competitor", "description": "Main competitor", "source": "Enrichment"},
      {"name": "industry_trend", "description": "Current trend", "source": "Research"},
      {"name": "market_driver", "description": "External force", "source": "Industry news"}
    ],
    "strategic_focus": "Position as fast-track alternative to legacy vendors...",
    "target_outcome": "Generate 8-12 qualified meetings with VP/C-level...",
    "vertical": "Financial Services",
    "objective": "Generate qualified meetings with decision makers"
  },
  "campaigns": [
    {
      "campaign_number": 1,
      "campaign_name": "Custom Signal Campaign",
      "angle": "custom_signal",
      "campaign_variables": [
        {"name": "job_signal", "description": "Recent hiring indicator"},
        {"name": "hiring_role", "description": "Specific role hiring for"},
        {"name": "tech_signal", "description": "Technology evaluating"}
      ]
    },
    {
      "campaign_number": 2,
      "campaign_name": "Persona Pain Campaign",
      "angle": "persona_pain",
      "campaign_variables": [
        {"name": "persona_pain", "description": "Primary pain point"},
        {"name": "team_size", "description": "Size of their team"},
        {"name": "backlog_indicator", "description": "Signs of workload"}
      ]
    },
    {
      "campaign_number": 3,
      "campaign_name": "Case Study Campaign",
      "angle": "case_study",
      "campaign_variables": [
        {"name": "case_study_company", "description": "Reference customer"},
        {"name": "case_study_result", "description": "Quantified result"},
        {"name": "similar_challenge", "description": "Shared challenge"}
      ]
    },
    {
      "campaign_number": 4,
      "campaign_name": "Risk/Efficiency Campaign",
      "angle": "risk_efficiency",
      "campaign_variables": [
        {"name": "efficiency_metric", "description": "Key efficiency gain"},
        {"name": "risk_factor", "description": "Business risk facing"},
        {"name": "roi_timeline", "description": "Time to results"}
      ]
    }
  ]
}
```

### Step 8: Done

**DO NOT call `complete_job`** - the worker handles phase completion automatically.
After `save_cycle_scaffold` returns, your task is done.
The worker will then create 4 campaign_copy phases to generate emails.

---

## Checklist Before Saving

- [ ] ICP mapping has target_icp, 4 pain point categories, 3 objections
- [ ] Cycle variables defined (apply to all campaigns)
- [ ] Each campaign has distinct angle and campaign-specific variables
- [ ] Strategic focus and target outcome are clear and measurable
- [ ] All variable names use snake_case (no spaces)

---

## Parameters

- `client_id`: The UUID of the client
- `job_id`: The generation job ID

---

## What Happens Next

After this phase completes:
1. Worker creates 4 `campaign_copy` phases
2. Each phase calls `generate-campaign-copy.md` skill
3. Each campaign generates 4 email positions with variants
4. Full cycle is complete when all 4 campaigns are done
