---
description: Generate a themed shadcn/ui component library from brand tokens — 5 batched phases with validation gates
---

# Design System Generator — Component Library from Brand Tokens

You are a senior design engineer. Your job is to take the brand documentation produced by `/design-brand-consult` and generate a real, working component library built on shadcn/ui + Tailwind CSS, fully themed to the project's brand.

## Prerequisites

Before proceeding, verify ALL of these exist:
1. `docs/design-system/tokens/colors.md`
2. `docs/design-system/tokens/typography.md`
3. `docs/design-system/tokens/spacing.md`
4. `docs/design-system/tokens/effects.md`
5. `docs/design-system/brand-brief.md`

If any are missing, tell the user: "Missing design tokens. Run `/design-brand-consult` first."

Read ALL token files and the brand-brief before generating anything. Pay attention to:
- `[exact]`, `[scraped]`, and `[visual-estimate]` confidence tags — prefer higher-confidence values
- The `framework` and `paths` fields in `brand-brief.md` — these determine where files go
- The `type` field — this determines which composite components to generate

## Phase 0: Project Environment Gate

Read `docs/design-system/brand-brief.md` for `framework` and `paths` fields.

Verify ALL of the following exist. If ANY are missing, stop and redirect — do not attempt to install or scaffold here:

1. **`package.json`** exists in the project root — if NO: "Run `/design-init` first to scaffold your project."
2. **Tailwind is configured** (`tailwind.config.ts` or `tailwind.config.js`) — if NO: "Run `/design-init` — Tailwind is not set up."
3. **shadcn/ui is initialized** (`components.json` exists) — if NO: "Run `/design-init` — shadcn/ui is not initialized."
4. **Required dependencies** in `package.json`: `class-variance-authority`, `clsx`, `tailwind-merge`, `lucide-react` — if ANY missing: "Run `/design-init` to install missing dependencies: [list]."

Only proceed past Phase 0 if all checks pass.

Determine output paths from `brand-brief.md`:

| Variable | Description | Example |
|----------|-------------|---------|
| `COMPONENT_DIR` | UI component directory | `src/components/ui/` |
| `COMPOSITE_DIR` | Composite component directory | `src/components/` |
| `STYLES_DIR` | Global styles location | `src/app/globals.css` |
| `CONFIG_DIR` | Tailwind config location | project root |
| `DOCS_DIR` | Component docs | `docs/design-system/components/` |

If `brand-brief.md` doesn't have paths, detect from framework:
- Next.js (App Router): components in `src/components/ui/`, styles in `src/app/globals.css`
- Next.js (Pages Router): components in `src/components/ui/`, styles in `src/styles/globals.css`
- Vite + React: components in `src/components/ui/`, styles in `src/index.css`
- Remix: components in `app/components/ui/`, styles in `app/tailwind.css`
- Astro: components in `src/components/ui/`, styles in `src/styles/global.css`

## Phase 0B: Design Branch

Before generating any component files:

1. Run `git branch --show-current`
2. If `main` or `master` → `git checkout -b design/system`
3. If any other branch → stay on it (user chose it deliberately)
4. If `design/system` already exists → `git checkout design/system`
5. If git is not initialized → warn user, skip branching

Tell user which branch you're working on.

## Phase 1: Foundation + Core Primitives (Batch 1 of 5)

### 1A: Tailwind + CSS Variable Foundation

**`tailwind.config.ts`** — Extend Tailwind with ALL brand tokens from the docs:
- Map every color from `colors.md` to CSS variable references
- Set up the spacing scale from `spacing.md`
- Configure border-radius scale from `effects.md`
- Set font families from `typography.md`
- Configure the type scale (fontSize entries with lineHeight)
- Add custom animation keyframes from `effects.md` motion tokens

**`STYLES_DIR/globals.css`** (path from brand-brief):
- Define all CSS custom properties in HSL: `--primary: 220 70% 50%;`
- Include both `:root` (light) and `.dark` (dark mode) palettes
- Dark mode palette should be a thoughtful inversion — not just swapped values. Reference the brand docs for mood guidance.
- Define typography custom properties
- Import Tailwind base layers

### 1B: Core Primitive Components

Generate these 5 in `COMPONENT_DIR`:

1. **`button.tsx`** — Variants: default, secondary, outline, ghost, destructive, link. Sizes: sm, default, lg, icon. Full hover/focus/active states.
2. **`card.tsx`** — Card, CardHeader, CardTitle, CardDescription, CardContent, CardFooter. Shadow and border per brand effects tokens.
3. **`input.tsx`** — Text input with focus ring color from brand, error state using destructive token, disabled state.
4. **`badge.tsx`** — Variants: default, secondary, outline, destructive.
5. **`separator.tsx`** — Horizontal and vertical, using border token.

### 1C: Component Requirements (apply to ALL components in ALL batches)

Every component file MUST include:
- Full TypeScript types with `React.ComponentPropsWithoutRef` or `React.HTMLAttributes`
- All variants defined with `cva` (class-variance-authority)
- Tailwind classes using CSS variables ONLY (e.g., `bg-primary text-primary-foreground`), NEVER raw colors
- Proper `forwardRef` usage
- Keyboard accessibility (tabIndex, role, aria attributes where needed)
- Comment block at top: `/** Uses tokens: --primary, --radius-md, etc. See [[design-system/components/button]] */`

### 1D: Documentation for Batch 1

For EACH component in this batch, create a Foam doc in `DOCS_DIR`:

```markdown
---
name: {Component Name}
category: ui
status: generated
batch: 1
---

# {Component Name}

## Purpose
What this component is for and when to use it.

## Variants
| Variant | Description | When to Use |
|---------|-------------|-------------|
| default | [desc] | [guidance] |
| ... | ... | ... |

## Tokens Used
- Color: [[design-system/tokens/colors]] — `--primary`, `--primary-foreground`, etc.
- Typography: [[design-system/tokens/typography]] — body font at base size
- Spacing: [[design-system/tokens/spacing]] — internal padding `--space-4`
- Effects: [[design-system/tokens/effects]] — radius `--radius-md`

## Usage Guidelines
- DO: [specific positive guidance]
- DON'T: [specific anti-patterns]

## See Also
- [[design-system/components/index]] | [[design-system/tokens/colors]] | [[design-system/tokens/typography]]
- Related: [[design-system/components/other-component]]
```

### 1E: Validation Gate

After writing all Batch 1 files, run these checks using Grep:

1. **Raw color check:** Grep all generated `.tsx` files for `blue-|gray-|indigo-|red-|green-|yellow-|purple-|pink-|orange-|slate-|zinc-|neutral-|stone-` class patterns. Also grep for `#[0-9a-fA-F]{3,8}` and `rgb(`. Any matches = FAIL. Fix before proceeding.
2. **Arbitrary value check:** Grep for `\-\[` (e.g., `p-[13px]`, `w-[200px]`). Any matches = FAIL.
3. **CVA check:** Grep each component file for `cva(`. Every component with variants must have it.
4. List files created and report to user: "Batch 1 complete: [files]. All checks passed. Proceeding to Batch 2..."

If any check fails, fix the offending file immediately before proceeding.

---

## Phase 2: Form Components (Batch 2 of 5)

Generate in `COMPONENT_DIR`:
1. **`textarea.tsx`** — Matching input styling, auto-resize optional
2. **`label.tsx`** — Consistent with typography tokens
3. **`select.tsx`** — Custom select dropdown with brand styling
4. **`checkbox.tsx`** — Styled checkbox with brand primary for checked state
5. **`switch.tsx`** — Toggle switch with brand primary

Documentation for each in `DOCS_DIR`. Same format as Batch 1.

**Validation gate:** Run the same Grep checks as Batch 1 on new files. Also read `input.tsx` and verify form components use the same focus ring, border, and radius classes. Report to user.

---

## Phase 3: Overlay Components (Batch 3 of 5)

Generate in `COMPONENT_DIR`:
1. **`dialog.tsx`** — Modal with overlay, animation using brand motion tokens
2. **`dropdown-menu.tsx`** — Styled to brand
3. **`sheet.tsx`** — Slide-out panel for mobile menus
4. **`tooltip.tsx`** — Styled to brand
5. **`toast.tsx`** — Notification component with variants (default, success, destructive)

Documentation for each in `DOCS_DIR`.

**Validation gate:** Run the same Grep checks as Batch 1. Also grep for `duration-` and `ease-` classes to confirm motion tokens are applied to overlays. Report to user.

---

## Phase 4: Navigation + Display (Batch 4 of 5)

Generate in `COMPONENT_DIR`:
1. **`navigation-menu.tsx`** — Desktop nav with dropdown support
2. **`tabs.tsx`** — Tab navigation with active indicator
3. **`avatar.tsx`** — With fallback initials, uses brand radius
4. **`skeleton.tsx`** — Loading placeholder using brand muted color
5. **`scroll-area.tsx`** — Custom scrollbar if brand calls for it

Documentation for each in `DOCS_DIR`.

**Validation gate:** Run the same Grep checks as Batch 1. Also grep `navigation-menu.tsx` for `onKeyDown` or `role=` to confirm keyboard nav is wired. Report to user.

---

## Phase 5: Composite Components (Batch 5 of 5 — Conditional)

Read `docs/design-system/brand-brief.md` for the `type` field. Generate ONLY the relevant set in `COMPOSITE_DIR`:

### If type = marketing | landing | portfolio:
1. **`hero-section.tsx`** — Based on patterns from brand references
2. **`feature-grid.tsx`** — Feature highlights section
3. **`cta-section.tsx`** — Call to action block
4. **`testimonial-card.tsx`** — Social proof component
5. **`pricing-card.tsx`** — Pricing tier display
6. **`navbar.tsx`** — Responsive nav (desktop nav-menu + mobile sheet)
7. **`footer.tsx`** — Standard footer layout

### If type = app | dashboard | SaaS:
1. **`stat-card.tsx`** — Metric display with label, value, trend indicator
2. **`data-table.tsx`** — Table wrapper with header, rows, pagination skeleton
3. **`sidebar-layout.tsx`** — Fixed sidebar + scrollable main content area
4. **`command-palette.tsx`** — Cmd+K search dialog
5. **`chart-container.tsx`** — Wrapper for chart libraries with brand color tokens
6. **`navbar.tsx`** — App header bar with breadcrumbs + actions
7. **`footer.tsx`** — Minimal app footer

### If type = e-commerce:
1. **`product-card.tsx`** — Image, title, price, add-to-cart
2. **`cart-summary.tsx`** — Cart item list with totals
3. **`checkout-form.tsx`** — Multi-step form layout
4. **`category-grid.tsx`** — Category browsing layout
5. **`navbar.tsx`** — Nav with cart icon + count
6. **`footer.tsx`** — E-commerce footer with links

### If type = monorepo (web + mobile):
Generate the set that matches the web portion of the project. Mobile components are handled by `/design-mobile`.

### If type is missing or unclear:
ASK the user. Do not default to marketing.

All composites MUST import from `COMPONENT_DIR` only. No custom UI primitives. No styling outside the design system tokens.

Documentation for each composite in `DOCS_DIR`.

**Validation gate:** Run Grep checks as Batch 1. Also grep each composite for imports from `COMPONENT_DIR` — every composite must import at least one UI primitive. Grep for inline `className="bg-` with raw Tailwind colors to catch leaked styling. Report to user.

**Commit:** Stage all component files, docs, and config generated across all 5 batches:
```bash
git add {COMPONENT_DIR}/ {COMPOSITE_DIR}/ {STYLES_DIR} tailwind.config.ts {DOCS_DIR}/
git commit -m "Generate component library — {N} components across 5 batches"
```

---

## Final: Component Inventory Update

After all 5 batches complete:

1. Update `docs/design-system/components/index.md` with a full inventory table:
```markdown
# Component Library

## UI Primitives (from `COMPONENT_DIR`)

| Component | Category | Batch | Status | Doc |
|-----------|----------|-------|--------|-----|
| Button | Interactive | 1 | Generated | [[design-system/components/button]] |
| Card | Layout | 1 | Generated | [[design-system/components/card]] |
| ... | ... | ... | ... | ... |

## Composite Components (from `COMPOSITE_DIR`)

| Component | Category | Project Type | Doc |
|-----------|----------|-------------|-----|
| Navbar | Navigation | All | [[design-system/components/navbar]] |
| ... | ... | ... | ... |
```

2. Update `docs/design-system/index.md` to link to the components section.

3. **Final commit:**
   ```bash
   git add docs/design-system/components/index.md docs/design-system/index.md
   git commit -m "Update component inventory — {total} components across 5 batches"
   ```

4. Output final summary:
   - Total files created (components + docs)
   - Branch name and total commits made
   - Any tokens that were `[visual-estimate]` confidence — flag for user review
   - Next step: "Run `/design-review` to audit the system, or `/design-web` to start building pages. Merge `design/system` when satisfied."

## Critical Rules

- NEVER use raw color values in components. Always `bg-primary`, `text-muted-foreground`, etc.
- NEVER use arbitrary Tailwind values like `p-[13px]`. Only values from the spacing scale.
- NEVER use default Tailwind palette colors (`text-blue-500`, `bg-gray-100`). Only semantic token colors.
- EVERY component must work in both light and dark mode via CSS variables.
- EVERY component must be keyboard accessible.
- shadcn/ui is the base — customize through the theming layer, don't rewrite primitives from scratch.
- Component files are self-contained. One component per file. Composites import from `COMPONENT_DIR`.
- Use Lucide React for all icons. Never inline SVGs.
- All sizing responsive. Use Tailwind responsive prefixes where needed.
- ALL Foam wiki links must be path-qualified: `[[design-system/components/button]]` not `[[button]]`.
- Use the path variables from Phase 0 — never hardcode `src/components/ui/`.
