---
name: CostBudgetMeter
category: charm
status: generated
batch: 5
created: 2026-05-15
---

# CostBudgetMeter

Per-agent monthly LLM cost budget bar. Maps `agents.spent_monthly_cents` vs `agents.budget_monthly_cents` (see [[../architecture/agent-runtime]] §Cost Tracking) to a single horizontal meter with status label.

## Purpose

Three tonal bands aligned with paperclip's budget enforcement thresholds:

| Utilization | Fill Tone | Status Label |
|-------------|-----------|--------------|
| 0–80% | moss | Healthy |
| 80–100% | honey | Approaching cap |
| > 100% | rust | Over budget · +N% |

## Tokens Used

- Color: [[design-system/tokens/colors]] — `--moss`, `--honey`, `--rust`, `--cream`, `--ink`, `--ink-soft`
- Typography: [[design-system/tokens/typography]] — mono for dollar values
- Effects: [[design-system/tokens/effects]] — `--radius-full` (pill bar), 1.5px outline

## Usage

```tsx
import { CostBudgetMeter } from "@/components/charm";

<CostBudgetMeter spentCents={1240} budgetCents={5000} size="sm" />
<CostBudgetMeter spentCents={5300} budgetCents={5000} size="lg" />  // over budget
```

## Sizes

- `sm` — fits inside agent card row (no labels needed in tight spaces; pass `showLabels={false}`)
- `md` (default) — agent detail header
- `lg` — workspace settings / costs page

## Guidelines

- DO use this as the single visual representation of agent budget across all surfaces
- DON'T show only a percentage — operators want the absolute dollar amount alongside
- DON'T animate the fill on every render (only on data change via the 300ms transition)

## See Also

- [[design-system/components/index]] | [[design-system/components/agent-card]]
- [[../architecture/agent-runtime]] §Cost Tracking
