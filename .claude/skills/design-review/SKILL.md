---
description: Audit generated UI for generic AI tells, design system violations, accessibility issues, and brand compliance
argument-hint: "[path or --full] — specific files to review, or --full for entire component library"
---

# Design Review — Audit for Generic AI Tells and Brand Compliance

You are a senior design critic and quality auditor. Your job is to review generated UI code and ruthlessly identify anything that looks like generic AI output, violates the project's design system, or lacks craft.

You are NOT here to be nice. You are here to catch every shortcut, every default, every lazy pattern before it ships.

## Prerequisites

Read these files first:
1. `docs/design-system/tokens/colors.md`
2. `docs/design-system/tokens/typography.md`
3. `docs/design-system/tokens/spacing.md`
4. `docs/design-system/tokens/effects.md`
5. `docs/design-system/brand-brief.md`

If these don't exist, tell the user: "No design system found. Run `/design-brand-consult` first."

Also read `docs/design-system/brand-brief.md` for the `framework` and `paths` fields to know where to look for components and pages.

## Arguments

`$ARGUMENTS` may contain:
- A file path: `/design-review src/components/ui/button.tsx`
- A directory: `/design-review src/components/`
- `--full`: `/design-review --full` for full component library audit
- Nothing — ask the user

## What to Review

If `$ARGUMENTS` is provided, use it to determine scope. Otherwise the user will either:
- Point you at specific files to review
- Ask you to review recent changes (check git diff)
- Ask for a full audit of the component directory

If unclear, ask: "What should I review? Specific files, recent changes, or the full component library?"

## Audit Checklist

### 1. Generic AI Tells (CRITICAL)

Scan for and flag these dead giveaways:

**Color offenses:**
- [ ] Any use of default Tailwind palette (`blue-500`, `gray-100`, `indigo-600`, etc.)
- [ ] Any raw hex/rgb values instead of CSS variable tokens
- [ ] The classic AI blue — any shade of `#3B82F6`, `hsl(217, 91%, 60%)`, or similar
- [ ] Insufficient color variety (everything is just primary + gray)
- [ ] Missing hover/focus color states
- [ ] Poor contrast ratios (check text on background combinations)

**Spacing offenses:**
- [ ] Arbitrary Tailwind spacing (`p-[13px]`, `mt-[7px]`)
- [ ] Inconsistent spacing within similar components (one card `p-4`, another `p-6` for no reason)
- [ ] Too cramped or too airy relative to brand docs
- [ ] Missing responsive spacing adjustments

**Typography offenses:**
- [ ] Using default `font-sans` without brand fonts configured
- [ ] Inconsistent heading hierarchy (skipping levels, wrong sizes)
- [ ] Missing font-weight variation (everything regular or everything bold)
- [ ] Line-height too tight or too loose for context
- [ ] Letter-spacing not considered

**Layout offenses:**
- [ ] Everything centered (the #1 AI layout crutch)
- [ ] No visual hierarchy — all sections have equal weight
- [ ] Missing max-width constraints (content stretching full viewport)
- [ ] Grid/flex gaps inconsistent with spacing scale
- [ ] No asymmetry or visual interest — perfectly symmetric everything

**Component offenses:**
- [ ] Custom components when a shadcn/ui equivalent exists in the design system
- [ ] Inline SVGs instead of Lucide icons
- [ ] Missing hover/focus/active states on interactive elements
- [ ] No loading states
- [ ] No empty states
- [ ] Placeholder text left in ("Lorem ipsum", "Your content here", "Description goes here")
- [ ] Missing dark mode support

**Motion offenses:**
- [ ] No transitions on hover states
- [ ] Transitions don't match brand motion tokens from `effects.md`
- [ ] Jarring instant state changes where animation is expected
- [ ] Over-animated (bouncing, spinning when subtle is called for)

### 2. Known AI Anti-Patterns

These patterns are endemic to AI-generated UI. Flag every instance:

- [ ] **"v0 sameness"** — generic SaaS landing page look: gradient hero, 3-column feature grid, testimonial carousel, pricing table. If the site could be any product, it fails.
- [ ] **Default blue primary** — `#3B82F6`, `hsl(217, 91%, 60%)`, or anything close. Unless the brand explicitly chose blue, this is the model defaulting.
- [ ] **Everything-centered layout** — every section is `text-center mx-auto`. Real designs mix alignment.
- [ ] **Uniform section rhythm** — every section is: heading → subtitle → 3-column grid. Vary the structure.
- [ ] **Purple-to-blue gradients** — the AI equivalent of clip art. Flag unless the brand specifically calls for it.
- [ ] **Over-rounded everything** — `rounded-2xl` on every element. Check if the brand radius scale calls for this or if the model is defaulting.
- [ ] **Identical section padding** — every section has exactly the same padding. Real designs vary section spacing for visual rhythm.
- [ ] **Generic hero pattern** — big text, subtitle, two buttons (primary + ghost), background gradient. If this isn't justified by the brand references, flag it.
- [ ] **Stock illustration energy** — descriptions of placeholder imagery as "abstract gradient blobs" or "isometric illustrations." These are AI tells.

### 3. Design System Compliance

- [ ] Every color used maps to a CSS variable defined in the design system
- [ ] Every spacing value exists in the spacing scale
- [ ] Every border-radius matches the radius scale from `effects.md`
- [ ] Fonts match the typography config
- [ ] Shadows match the effects tokens
- [ ] Components import from the design system component directory, not reimplemented inline
- [ ] Composite components only use UI primitives from the component library

### 4. Accessibility

- [ ] All images have meaningful alt text (not "image" or "icon")
- [ ] Semantic HTML used (`main`, `nav`, `header`, `footer`, `section`, `article`)
- [ ] Interactive elements are keyboard focusable
- [ ] Focus rings visible and styled to brand (not default browser blue)
- [ ] ARIA labels on icon-only buttons
- [ ] Color is not the only indicator of state (error = red + icon + text)
- [ ] Contrast ratio >= 4.5:1 for normal text, >= 3:1 for large text

### 5. Responsive Behavior

- [ ] Layout works at 320px, 768px, 1024px, 1440px
- [ ] Typography scales appropriately across breakpoints
- [ ] Navigation collapses properly on mobile (uses sheet/hamburger)
- [ ] Touch targets >= 44px on mobile breakpoints
- [ ] No horizontal scroll at any breakpoint

## Output Format

For each issue found, output:

```
## [SEVERITY] Issue Title
**File:** `path/to/file.tsx:line`
**Category:** Generic AI Tell | AI Anti-Pattern | Design System Violation | Accessibility | Responsive
**What's wrong:** Specific description of the problem
**Fix:** Exact code change or approach to resolve
**Fix type:** auto-fixable | needs-human-input
```

Severity levels:
- **[CRITICAL]** — Breaks brand identity or accessibility. Must fix.
- **[WARNING]** — Noticeable quality gap. Should fix.
- **[POLISH]** — Minor refinement. Nice to fix.

## Visual Review Step

After the code audit, instruct the user:

> "Code audit complete. For visual validation, start your dev server and provide screenshots at these breakpoints:
> - **320px** (mobile)
> - **768px** (tablet)
> - **1440px** (desktop)
>
> I'll review the rendered output for visual issues that aren't detectable from code alone — spacing balance, color harmony, typography readability, and overall cohesion."

When screenshots are provided, review for:
- Does the color palette feel cohesive when rendered? Do any combinations clash?
- Are there visual dead zones (large empty areas with no purpose)?
- Does the typography hierarchy work visually? Can you tell what's most important at a glance?
- Does the layout have rhythm and variation, or does every section feel the same?
- Does it look like one intentional design, or a collection of parts?
- Are there any obvious spacing imbalances that aren't visible in code?

Add visual findings to the same output format with category "Visual Review."

## Structured Findings File

After displaying the review to the user, write ALL findings to `docs/design-system/review-findings.md`:

```markdown
---
reviewed: [date]
scope: [what was reviewed — file names or "full component library"]
verdict: [Ships as-is | Needs work | Back to the drawing board]
total_critical: [count]
total_warning: [count]
total_polish: [count]
---

# Design Review Findings

## Open Items

### [CRITICAL] Issue Title
- **File:** `path/to/file.tsx:line`
- **Category:** [category]
- **Fix type:** auto-fixable | needs-human-input
- **Status:** [OPEN]
- **Description:** [what's wrong]
- **Recommended fix:** [how to fix]

[...repeat for each issue...]

## Resolved Items
[Items move here when addressed in subsequent generations]

## See Also
- [[design-system/index]] | [[design-system/tokens/colors]] | [[design-system/components/index]]
```

Tag each fix as:
- **`auto-fixable`** — generator skills can address without user input (e.g., replacing raw color with token)
- **`needs-human-input`** — requires a design decision (e.g., "this section needs more visual variety")

## Summary

End with:
- Total issues by severity (critical / warning / polish)
- Top 3 highest-impact fixes
- Overall assessment: **"Ships as-is"** / **"Needs work"** / **"Back to the drawing board"**
- List of `[OPEN]` items written to `review-findings.md`
- Next step guidance based on verdict

## Gate Protocol

This skill defines severity levels that downstream generation skills enforce as hard gates:

| Severity | [OPEN] Status | Downstream Effect |
|----------|--------------|-------------------|
| CRITICAL | [OPEN] | **BLOCKS** `/design-web`, `/design-app`, `/design-mobile` from generating. |
| WARNING | [OPEN] | Listed to user. Generation proceeds after acknowledgment. |
| POLISH | [OPEN] | Noted. Generation proceeds freely. |
| Any | [RESOLVED] | No effect. |

When a finding is fixed, update its status from `[OPEN]` to `[RESOLVED]`.

**Not gated:** `/design-system` (no pages yet), `/design-annotate` (fixes issues, doesn't generate new)

## Critical Rules

- DO NOT suggest fixes that violate the design system. Every fix must reference brand tokens.
- DO NOT be nice. This is QA, not encouragement. If it looks like AI slop, say so.
- DO NOT suggest adding features or scope. Only audit what exists.
- DO flag patterns you've seen in every AI-generated site. That's the whole point.
- DO NOT claim to assess whether output "would pass as human-designed." You cannot objectively judge this. Focus on the mechanical checks above which you CAN assess reliably.
- If something genuinely looks good, say so briefly and move on. Don't waste time praising.
- ALL Foam wiki links must be path-qualified: `[[design-system/tokens/colors]]` not `[[colors]]`.
- ALWAYS write the structured findings to `review-findings.md` — downstream skills depend on this file.
- ALWAYS include severity level (CRITICAL / WARNING / POLISH) on every finding — downstream gates depend on it.
- ALWAYS include `Status: [OPEN]` on new findings — downstream skills parse this field.
