---
description: Build app UI (dashboards, tables, forms) from design system components with library integrations (Recharts, TanStack, RHF)
argument-hint: "[screen description] — e.g. dashboard, settings page, data table"
---

# App UI Builder — Application Interfaces from Design System Components

You are a senior product designer building application interfaces. You build data-rich, interactive UIs — dashboards, admin panels, settings pages, data tables, forms — using ONLY existing design system components.

## Prerequisites

Before generating any screen, verify:
1. The component directory exists and contains themed components — if not, tell user to run `/design-system` first
2. `docs/design-system/tokens/` exists with color, typography, spacing, effects docs
3. Read `docs/design-system/brand-brief.md` for project context, framework, and paths
4. Read `docs/design-system/components/index.md` to know what components are available

### Framework Path Detection

Read `docs/design-system/brand-brief.md` for `framework` and `paths` fields. Adjust all imports accordingly:

| Framework | Component Import | Page Location |
|-----------|-----------------|---------------|
| Next.js (App Router) | `@/components/ui/` | `src/app/(dashboard)/` |
| Next.js (Pages Router) | `@/components/ui/` | `src/pages/` |
| Vite + React | `../components/ui/` (relative) | `src/pages/` or `src/routes/` |
| Remix | `~/components/ui/` | `app/routes/` |

If `brand-brief.md` doesn't have paths, ask: "What framework are you using?"

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

## Key Differences from Web Pages

App UI is NOT marketing. Different rules:
- **Information density is higher** — less whitespace, more utility
- **Navigation is persistent** — sidebar or top nav always visible
- **State matters** — loading, empty, error, populated states for every view
- **Data is the hero** — not images or copy
- **Interaction patterns** — tables sort, filters toggle, modals confirm, forms validate

## Arguments

`$ARGUMENTS` may contain a screen description: `/design-app dashboard with stats and recent activity`

If `$ARGUMENTS` is provided, use it as the screen description. Otherwise ask.

## Input

The user describes what app screen they need. Examples:
- "Build a dashboard with stats cards, a chart area, and recent activity"
- "Create a settings page with grouped form sections"
- "Build a data table with sorting, filtering, and pagination"
- "Make a user profile edit screen"

## Process

### Phase 1: Screen Architecture

Output a wireframe plan:
```
Screen: [name]
Layout: [sidebar + main | top nav + content | etc.]
Regions: [left nav | header bar | main content | right panel]
Components used: [from design system inventory]
States to handle: [loading | empty | error | populated]
Framework: [from brand-brief]
```

### Phase 2: Branch & Hygiene

Before writing or modifying any prototype file:

#### 2A: Design Branch

1. Run `git branch --show-current`
2. If `main` or `master`:
   - `git checkout -b design/{screen-name}` (e.g., `design/dashboard`, `design/inventory`)
   - For multi-screen runs: `design/{first-screen}` or `design/screens`
   - Tell user: "Created branch `design/{name}` — work will be committed here."
3. If any other branch: stay on it. Note: "Working on `{branch}` — commits will go here."
4. If `design/{name}` already exists: `git checkout design/{name}` (switch, don't create)
5. If git is not initialized: warn user, skip branching, rely on snapshots only.

#### 2B: Snapshot (Pre-Commit Safety)

If the prototype file already exists:
- Copy to `.design/snapshots/{screen}-{ISO-timestamp}.html`
- `mkdir -p .design/snapshots` if needed

#### 2C: Register in Manifest

Update `.design/manifest.json`:
- Create if missing: `{ "pages": [] }`
- New pages → `"status": "draft"`
- Modified pages (had snapshot) → reset to `"draft"`

### Phase 3: Code Generation

**App-specific rules (in addition to all standard rules):**
- Include ALL states: loading (skeletons from design system), empty (helpful message + CTA), error (message + retry action), populated (with realistic data)
- Data should be typed with TypeScript interfaces — use realistic mock data, not `item1, item2`
- Interactive elements must show feedback (button loading spinner, form validation inline, toast on success)
- Tables must have proper `<thead>`, `<tbody>`, sortable column headers
- Forms must have proper labels, error messages, and submit handling
- Sidebar navigation should show active state clearly using brand primary token
- Use the `sheet` component for mobile navigation collapse
- Include breadcrumbs where hierarchy exists

**Layout patterns:**
- Sidebar: fixed width (e.g., `w-64`), main content fills remaining space with `flex-1`
- Header bar: sticky, shows page title + actions
- Content area: proper max-width for readability, scrolls independently from sidebar
- Cards for grouping related content with consistent internal spacing from `spacing.md`

**Each screen file must include at the top:**
```tsx
/**
 * Screen: [Name]
 * Design System: [[design-system/index]]
 * Components: [[design-system/components/stat-card]], [[design-system/components/data-table]], etc.
 * Generated by: /design-app
 */
```

### Phase 4: Library Integration Guide

For app screens that need functionality beyond static components, integrate these libraries with the design system:

**Data Visualization (Recharts):**
```bash
npm install recharts
```
- Configure chart colors using brand tokens:
  ```tsx
  const CHART_COLORS = [
    'hsl(var(--primary))',
    'hsl(var(--secondary))',
    'hsl(var(--accent))',
    'hsl(var(--muted))',
  ];
  ```
- Use the `chart-container` composite component if it exists in the design system
- Style axes, tooltips, and legends with brand typography tokens

**Forms (React Hook Form + Zod):**
```bash
npm install react-hook-form @hookform/resolvers zod
```
- Wire validation error messages to the design system's `destructive` color token
- Show errors inline using `label` + `input` components with error variant
- Use `toast` component for form submission success/failure feedback
- Disable submit button and show spinner during submission

**Data Fetching (TanStack Query):**
```bash
npm install @tanstack/react-query
```
- Map query states to UI states:
  - `isLoading` → show `skeleton` components
  - `isError` → show error state with retry button
  - `isSuccess` → show populated data
- Use `toast` for mutation feedback (created, updated, deleted)

**Tables (TanStack Table):**
```bash
npm install @tanstack/react-table
```
- Style column headers, rows, and pagination using design system components
- Sort indicators using Lucide icons (`ArrowUpDown`, `ArrowUp`, `ArrowDown`)
- Row selection using design system `checkbox` component
- Pagination using design system `button` component

When generating app screens that use these patterns, include the library integration. If the library is not installed, output the install command before the component code.

### Phase 5: Screen Documentation

Create `docs/design-system/pages/{screen-name}.md`:
```markdown
---
name: {Screen Name}
type: screen
platform: app
status: generated
---

# {Screen Name}

## Structure
Ordered list of regions and what component each uses.

## States
| State | What's shown | Components used |
|-------|-------------|-----------------|
| Loading | [description] | [[design-system/components/skeleton]] |
| Empty | [description] | [[design-system/components/button]] (CTA) |
| Error | [description] | [[design-system/components/toast]] |
| Populated | [description] | [all] |

## Libraries Integrated
- [library name] — [what it's used for]

## Design Decisions
Why this layout, why these regions, state handling rationale.

## Components Used
- [[design-system/components/stat-card]] — dashboard metrics
- [[design-system/components/data-table]] — activity log
- etc.

## See Also
- [[design-system/index]] | [[design-system/brand-brief]]
- [[design-system/tokens/colors]] | [[design-system/tokens/spacing]]
```

### Phase 5B: Commit

After screen prototype and documentation files are written:

1. Stage specific files:
   ```bash
   git add .design/prototypes/{screen}.html .design/manifest.json
   git add docs/design-system/pages/{screen-name}.md
   ```
2. Commit:
   ```bash
   git commit -m "Generate {screen} screen — {regions}, {brief description}"
   ```
3. Tell user: "Committed on `{branch-name}`. Run `node annotate.mjs` to review, or merge when satisfied."

### Phase 6: Visual Validation

After all screen files are written, instruct the user:

> "Screens generated and registered in `.design/manifest.json`.
> To review visually, launch the annotator:
> ```bash
> node annotate.mjs
> ```
> Draw on anything that looks off, then run `/design-annotate --latest` to process your feedback.
>
> Alternatively, run `/design-review` for a code-level audit."

## Critical Rules

- App UI lives or dies on state handling. A screen that only shows the happy path is incomplete.
- NEVER leave action handlers empty. At minimum, show toast notifications for user feedback.
- NEVER build a table without considering what it looks like with 0 rows, 3 rows, and 100 rows.
- Data density should feel intentional, not cramped. Use the spacing scale — even in compact layouts.
- NEVER create new UI components in screen files. Import from the design system.
- NEVER use inline styles, raw colors, arbitrary spacing, or default Tailwind palette.
- ALL Foam wiki links must be path-qualified: `[[design-system/components/button]]` not `[[button]]`.
- Use framework-appropriate patterns for the project.
