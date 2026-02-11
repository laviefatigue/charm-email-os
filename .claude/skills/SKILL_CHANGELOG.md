# Generate Strategy Skill Changelog

## v1.0 (2026-02-10) - BASELINE

**File:** `generate-strategy-v1.0.md`

### Features
- Single campaign document generation
- 4 email positions × 2-3 variants each
- ICP mapping with 4 pain point categories, 3 objections with preemption
- Variable schema: core, high-signal, AI-generated with sources
- QA scoring with 6 dimensions (Situation Recognition, Value Clarity, Personalization Quality, CTA Effort, Punchiness, Subject Lines)
- Strategy notes with callouts, data enrichment, A/B testing recommendations
- 50-90 word count enforcement per email
- Recipient:Sender ratio >= 3:1

### MCP Tools Used
- `get_client_context` - Fetches submission data
- `get_feedback_summary` - Gets approval/denial patterns
- `save_campaign_document` - Saves stablekernel format output
- `complete_job` - Marks job as ready for review

### Proven Results
- Successfully generates Charm B2B SaaS campaign
- QA Score: 87 ("Ship it")
- ICP: VP Sales / Head of Growth / Founder-CEO at B2B SaaS scaling outbound
- Pain Points: Infrastructure, Ops, Revenue, Talent categories

---

## v2.0 (2026-02-10) - FULL CYCLE PACKAGE

**File:** `generate-strategy.md`

### New Features
- Generates complete cycle with **4 campaigns** in one job
- Each campaign has distinct angle:
  1. Custom Signal (hiring/funding triggers)
  2. Persona Pain (role-specific overwhelm)
  3. Case Study (social proof focus)
  4. Risk/Efficiency (board pressure, ROI)
- Shared ICP mapping at cycle level
- Campaign-level variables unique to each angle
- Per-campaign QA scoring + overall cycle score
- Total: 16 emails (4 campaigns × 4 positions) with ~40 variants

### New MCP Tools
- `save_cycle_package` - Atomic save of all 4 campaigns + cycle config
  - Accepts: job_id, cycle_name, cycle_config, campaigns array
  - Creates: campaign_cycle, cycle_strategy_config, 4 campaign_documents
  - Returns: cycle_id + all document_ids

### Campaign Variables by Angle
| Campaign | Variables |
|----------|-----------|
| Custom Signal | `{{job_signal}}`, `{{outbound_tool}}`, `{{hiring_role}}` |
| Persona Pain | `{{persona_pain}}`, `{{team_size}}`, `{{daily_challenge}}` |
| Case Study | `{{case_study_company}}`, `{{case_study_result}}`, `{{case_study_timeline}}` |
| Risk/Efficiency | `{{efficiency_metric}}`, `{{roi_timeline}}`, `{{board_pressure}}` |

### Output Structure
```
1 Cycle Package
├── Cycle Config (shared)
│   ├── ICP Mapping
│   ├── Cycle Variables
│   └── Strategic Focus
└── 4 Campaign Documents
    ├── Campaign 1: Custom Signal (4 emails)
    ├── Campaign 2: Persona Pain (4 emails)
    ├── Campaign 3: Case Study (4 emails)
    └── Campaign 4: Risk/Efficiency (4 emails)
```

---

## Migration Notes

### From v1.0 to v2.0
- v1.0 outputs remain compatible with frontend
- v2.0 adds cycle linkage but doesn't break existing documents
- Frontend transforms single documents into unified view via `transformDocumentToCycleData()`
