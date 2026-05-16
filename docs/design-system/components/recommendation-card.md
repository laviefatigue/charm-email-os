---
name: RecommendationCard
category: charm
status: generated
batch: 5
created: 2026-05-15
---

# RecommendationCard

The hero surface of the agent runtime. Renders a `request_confirmation` interaction posted by an analyst agent — analysis summary, cited context docs, accept/reject CTAs. This is where the "combining dashboard with real tools" promise pays off.

## Purpose

Maps one row in `issue_interactions` (kind=`request_confirmation`) from [[../architecture/agent-runtime]] §Recommendation Surfacing. Lives in:

- The cross-workspace **Recommendations** mailbox (top-level nav)
- The per-workspace **Recommendations** sub-page
- The workspace detail Overview as an "attention required" surface

## Layout

- Bold-outlined card (1.5px ink) **plus `--shadow-flat` (4px 4px 0 ink)** — this is a hero surface, the offset shadow signals "this matters"
- Header: amber-sparkle agent identity tile + agent name + "recommends" + mono timestamp
- Prompt as Fraunces h3 (the question the agent is asking)
- Summary as body copy (the analysis writeup)
- Optional detail link ("View proposed rotation slate")
- **Cited Context section** — collapsible list of `{path, commitSha, relevance}` pulled from the recommendation payload. Mono-styled paths, clickable to open the source doc in the Context panel.
- **Actions footer** — Reject (outlined) + Approve (amber filled, the hearth color). If `rejectRequiresReason`, the Reject button reveals a textarea for the rejection reason before final submit.

## Tokens Used

- Color: [[design-system/tokens/colors]] — `--amber` (primary CTA + agent identity), `--ink` (border-bold), `--cream-light`, `--rust`/`--honey`/`--moss` for state nuances
- Typography: [[design-system/tokens/typography]] — Fraunces h3 for prompt, Manrope body for summary, mono for timestamps + cited paths
- Spacing: [[design-system/tokens/spacing]] — `--space-6` card padding, `--space-5` between sections
- Effects: [[design-system/tokens/effects]] — `--radius-xl` (20px, hero surface), `--border-bold` + `--shadow-flat`

## Usage

```tsx
import { RecommendationCard } from "@/components/charm";

<RecommendationCard
  recommendation={{
    id: "rec-...",
    agentName: "Performance Analyst",
    prompt: "Rotate these 5 domains before EOD?",
    summary: "Workspace HYPERTIDE — burn rate +18% MoM, kill cascade modeled to trigger in 4–6d…",
    citedContext: [
      { path: "decisions/DECISION_burn-threshold.md", commitSha: "a3b7c9d", relevance: "policy gate" },
      { path: "feedback/feedback_aggressive-rotation.md", commitSha: "a3b7c9d", relevance: "client preference" },
    ],
    createdAt: new Date(),
    rejectRequiresReason: true,
  }}
  onAccept={async (id) => approve(id)}
  onReject={async (id, reason) => reject(id, reason)}
  onOpenCitation={(path, sha) => openContextDoc(path, sha)}
/>
```

## Guidelines

- DO always carry `--shadow-flat` — these surfaces *should* punch out of the page
- DO render cited context inline (collapsible) so the operator can verify the agent's grounding before approving
- DO use `rejectRequiresReason: true` for high-stakes actions (rotation, kill, firewall override) — the rejection reason trains the agent next heartbeat
- DON'T strip the agent identity tile — operator needs to know *which agent* is asking
- DON'T allow accept without showing what's cited — the trust mechanism is the citation

## See Also

- [[design-system/components/index]] | [[design-system/components/agent-card]]
- [[../architecture/agent-runtime]] §Recommendation Surfacing
- [[../architecture/client-context-sync]] §Integration with Agent Runtime — cited_context payload
