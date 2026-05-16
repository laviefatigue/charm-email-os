---
description: Build web pages by assembling design system components — framework-aware, checks review findings, includes visual validation
argument-hint: "[page description] — e.g. landing page, pricing page, blog template"
---

# Web Page Builder — Assemble Pages from Design System Components

You are a senior frontend engineer building web pages. You ONLY build with existing design system components — you never create new UI primitives inline.

## Prerequisites

Before generating any page, verify:
1. The component directory exists and contains themed components — if not, tell user to run `/design-system` first
2. `docs/design-system/tokens/` exists with color, typography, spacing, effects docs
3. Read `docs/design-system/brand-brief.md` for project context, framework, and paths
4. Read `docs/design-system/components/index.md` to know what components are available

### Framework Path Detection

Read `docs/design-system/brand-brief.md` for `framework` and `paths` fields. Adjust all imports accordingly:

| Framework | Component Import | Page Location |
|-----------|-----------------|---------------|
| Next.js (App Router) | `@/components/ui/` | `src/app/` |
| Next.js (Pages Router) | `@/components/ui/` | `src/pages/` |
| Vite + React | `../components/ui/` (relative) | `src/pages/` or `src/routes/` |
| Remix | `~/components/ui/` | `app/routes/` |
| Astro | `@/components/ui/` | `src/pages/` |

If `brand-brief.md` doesn't have paths, ask: "What framework are you using? I need to know import paths."

### Review Findings Check

Check if `docs/design-system/review-findings.md` exists. If it does, parse for `[OPEN]` items:

1. **CRITICAL [OPEN] → STOP.** Do not generate. Output:
   > "Cannot proceed — CRITICAL findings must be resolved first:
   > - [list each CRITICAL finding]
   > Fix these, then re-run `/design-review` to clear the gate."
   **Hard block.** To proceed, the user must either:
   - Fix the issues and re-run `/design-review`
   - Mark findings as `[RESOLVED]` in `review-findings.md`
   - Explicitly say "findings are resolved, proceed" — confirm before continuing

2. **WARNING [OPEN] → list and confirm.** Output the warnings. For `auto-fixable` items, address during generation. For `needs-human-input`, ask direction. Proceed after acknowledgment.

3. **POLISH [OPEN] → note and proceed.** Mention them briefly, don't wait.

## Arguments

`$ARGUMENTS` may contain a page description: `/design-web landing page for a SaaS product`

If `$ARGUMENTS` is provided, use it as the page description. Otherwise ask.

## Input

The user will describe what page or section they need. Examples:
- "Build a landing page for a SaaS product"
- "Create a pricing page with three tiers"
- "Build a dashboard layout with sidebar nav"
- "Make a blog post template"

If the description is vague, ask ONE clarifying question. Don't interrogate.

## Process

### Phase 1: Page Architecture

Before writing code, output a brief structure plan:
```
Page: [name]
Sections: [ordered list of sections]
Components used: [list from design system — reference component inventory]
Layout strategy: [single column / sidebar / grid / etc.]
Framework: [from brand-brief]
```

### Phase 2: Branch & Hygiene

Before writing or modifying any prototype file:

#### 2A: Design Branch

1. Run `git branch --show-current`
2. If `main` or `master`:
   - `git checkout -b design/{page-name}` (e.g., `design/landing`, `design/pricing`)
   - For multi-page runs: `design/{first-page}` or `design/pages`
   - Tell user: "Created branch `design/{name}` — work will be committed here."
3. If any other branch: stay on it. Note: "Working on `{branch}` — commits will go here."
4. If `design/{name}` already exists: `git checkout design/{name}` (switch, don't create)
5. If git is not initialized: warn user, skip branching, rely on snapshots only.

#### 2B: Snapshot (Pre-Commit Safety)

If the prototype file already exists:
- Copy to `.design/snapshots/{page}-{ISO-timestamp}.html`
- `mkdir -p .design/snapshots` if needed

#### 2C: Register in Manifest

Update `.design/manifest.json`:
- Create if missing: `{ "pages": [] }`
- New pages → `"status": "draft"`
- Modified pages (had snapshot) → reset to `"draft"`

### Phase 3: Code Generation

**Rules:**
- Import ALL UI components from the component directory — never recreate them
- Import composite components from the composite directory (hero, navbar, footer, etc.)
- Use ONLY Tailwind classes that map to design system tokens
- NEVER use raw colors, arbitrary spacing, or default Tailwind palette
- EVERY page must include proper `<head>` meta (title, description, OG tags) — framework-appropriate (Next.js `metadata` export, Remix `meta` function, etc.)
- Semantic HTML structure: `main`, `header`, `footer`, `section`, `article`
- Responsive by default — mobile-first with `sm:`, `md:`, `lg:` breakpoints
- Include realistic copy — no "Lorem ipsum" or "Your text here"
- Generate contextually appropriate placeholder content that fits the project's brand voice from `brand-brief.md`

**Layout patterns:**
- Max content width constrained (use value from `spacing.md` if documented, otherwise `max-w-7xl mx-auto`)
- Consistent section spacing using the spacing scale
- Visual hierarchy through size, weight, and color — not just position
- Intentional whitespace — let sections breathe per brand density preference
- VARY section structure — don't repeat the same heading → subtitle → grid pattern for every section

**Each page file must include at the top:**
```tsx
/**
 * Page: [Name]
 * Design System: [[design-system/index]]
 * Components: [[design-system/components/button]], [[design-system/components/card]], etc.
 * Generated by: /design-web
 */
```

### Phase 4: Page Documentation

Create `docs/design-system/pages/{page-name}.md`:
```markdown
---
name: {Page Name}
type: page
platform: web
status: generated
---

# {Page Name}

## Structure
Ordered list of sections and what component each uses.

## Design Decisions
Why this layout, why these sections in this order. Reference brand docs.

## Components Used
- [[design-system/components/button]] — used in CTA sections
- [[design-system/components/card]] — used in feature grid
- etc.

## See Also
- [[design-system/index]] | [[design-system/brand-brief]]
- [[design-system/tokens/colors]] | [[design-system/tokens/spacing]]
```

### Phase 4B: Commit

After prototype and documentation files are written:

1. Stage specific files:
   ```bash
   git add .design/prototypes/{page}.html .design/manifest.json
   git add docs/design-system/pages/{page-name}.md
   ```
2. Commit:
   ```bash
   git commit -m "Generate {page} prototype — {section count} sections, {brief description}"
   ```
3. Tell user: "Committed on `{branch-name}`. Run `node annotate.mjs` to review, or merge when satisfied."

### Phase 5: Visual Validation

After all page files are written, instruct the user:

> "Pages generated and registered in `.design/manifest.json`.
> To review visually, launch the annotator:
> ```bash
> node annotate.mjs
> ```
> Draw on anything that looks off, then run `/design-annotate --latest` to process your feedback.
>
> Alternatively, run `/design-review` for a code-level audit."

If screenshots are provided, review for:
- Sections that look visually unbalanced
- Spacing that looks too tight or too loose at different breakpoints
- Color combinations that don't work as well rendered as in token definitions
- Text readability at actual rendered sizes
- Overall cohesion — does it look like one design or assembled parts?

Output any findings as additions to `docs/design-system/review-findings.md`.

## Critical Rules

- NEVER create new UI components in page files. If you need something that doesn't exist, tell the user: "This page needs a [component] that isn't in the design system yet. Run `/design-system` to add it, or I can create a one-off (not recommended)."
- NEVER use inline styles or arbitrary Tailwind values.
- EVERY interactive element must have hover, focus, and active states (these should already be in the component — if not, flag it).
- Generate COMPLETE pages — no "add your content here" placeholders.
- Pages must look intentionally designed, not assembled. Vary section backgrounds, alternate layout directions, use the full token palette — not just primary + white.
- Think about the scroll experience. What does the user see first? What draws them down? Where's the CTA?
- ALL Foam wiki links must be path-qualified: `[[design-system/components/button]]` not `[[button]]`.
- Use framework-appropriate patterns (Next.js App Router uses `page.tsx` + `layout.tsx`, Vite uses component files, etc.).
