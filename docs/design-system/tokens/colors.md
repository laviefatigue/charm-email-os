---
name: Color Palette
type: tokens
status: defined
---

# Color Palette

All colors in HSL format. Use CSS variable names in code — never raw values. Palette lifted verbatim from [[design-system/references/ref-paperclip]] (Howl's Moving Castle source). No `#fff`, no `#000` — *the film has no pure extremes*.

## Primitives — Howl's Palette `[scraped]`

| Token | CSS Variable | HSL Value | Source Frame | Confidence |
|-------|-------------|-----------|--------------|------------|
| Amber | `--amber` | `hsl(34 78% 56%)` | Calcifer's flame, lantern glow | `[scraped]` |
| Honey | `--honey` | `hsl(38 65% 68%)` | Late-afternoon sunlight | `[scraped]` |
| Copper | `--copper` | `hsl(22 55% 48%)` | Brass mechanical parts | `[scraped]` |
| Rust | `--rust` | `hsl(14 55% 42%)` | Oxidised iron | `[scraped]` |
| Cream | `--cream` | `hsl(38 35% 88%)` | Walls, papers | `[scraped]` |
| Cream-light | `--cream-light` | `hsl(40 40% 94%)` | Backlit highlights — page bg | `[scraped]` |
| Sage | `--sage` | `hsl(85 22% 58%)` | Hillsides, Howl's coat | `[scraped]` |
| Moss | `--moss` | `hsl(95 25% 38%)` | Forest shadow | `[scraped]` |
| Sky | `--sky` | `hsl(205 45% 72%)` | Daytime sky, Markl's eyes | `[scraped]` |
| Blue-howl | `--blue-howl` | `hsl(210 40% 38%)` | Howl's coat-blue | `[scraped]` |
| Storm | `--storm` | `hsl(220 18% 30%)` | Wartime overcast | `[scraped]` |
| Rose | `--rose` | `hsl(345 35% 78%)` | Sophie's ribbon | `[scraped]` |
| Rose-deep | `--rose-deep` | `hsl(355 38% 58%)` | Sunset accent | `[scraped]` |
| Ink | `--ink` | `hsl(28 18% 22%)` | Outlines, body text (warm-brown) | `[scraped]` |
| Ink-soft | `--ink-soft` | `hsl(28 14% 36%)` | Secondary text, muted strokes | `[scraped]` |

Derived from: [[design-system/references/ref-paperclip]] §Color Tokens

## Semantic Roles — Light Mode ("Morning Village")

| Token | CSS Variable | Maps To | Purpose |
|-------|-------------|---------|---------|
| Background | `--background` | `var(--cream-light)` | Page ground |
| Foreground | `--foreground` | `var(--ink)` | Body text, default ink |
| Card | `--card` | `var(--cream-light)` | Card surface |
| Card Foreground | `--card-foreground` | `var(--ink)` | Card body text |
| Primary | `--primary` | `var(--amber)` | CTAs: Approve kill, Enable EOD reapply, Add domain |
| Primary Foreground | `--primary-foreground` | `var(--ink)` | Text on amber (high contrast) |
| Secondary | `--secondary` | `var(--sage)` | Earth-anchored supporting accents |
| Secondary Foreground | `--secondary-foreground` | `var(--ink)` | Text on sage |
| Accent | `--accent` | `var(--copper)` | "Look here" highlights, icon backgrounds |
| Accent Foreground | `--accent-foreground` | `var(--cream-light)` | Text on copper |
| Muted | `--muted` | `var(--cream)` | Disabled, subtle surfaces |
| Muted Foreground | `--muted-foreground` | `var(--ink-soft)` | Captions, metadata, "Last updated 2h ago" |
| Border | `--border` | `var(--ink-soft)` | Default 1px borders — inputs, dividers, table grid |
| Border Bold | `--border-bold` | `var(--ink)` | 1.5px outline on cards, modals, primary CTAs |
| Ring | `--ring` | `var(--amber)` | Focus ring — Calcifer's hearth-light on your hand |
| Destructive | `--destructive` | `var(--rust)` | Kill confirmed, Burn confirmed, errors |
| Destructive Foreground | `--destructive-foreground` | `var(--cream-light)` | Text on rust |
| Success | `--success` | `var(--moss)` | "Live" status, "Healthy" |
| Warning | `--warning` | `var(--honey)` | "Reserve" status, "Drift detected" cautions |
| Info | `--info` | `var(--sky)` | "Incubating" status, queued, scheduled |

## Semantic Roles — Dark Mode ("Evening Village")

Warm-dark interior, **never corporate-grey**. Inverted ink/cream pairing.

| Token | CSS Variable | HSL Value | Purpose |
|-------|-------------|-----------|---------|
| Background | `--background` | `hsl(28 18% 14%)` | Deep warm dark — interior at night |
| Foreground | `--foreground` | `hsl(40 30% 92%)` | Cream-light text |
| Card | `--card` | `hsl(28 18% 18%)` | Slightly raised from bg |
| Card Foreground | `--card-foreground` | `hsl(40 30% 92%)` | |
| Primary | `--primary` | `hsl(38 70% 62%)` | Honey-shifted amber (lighter for dark-mode visibility) |
| Primary Foreground | `--primary-foreground` | `hsl(28 18% 14%)` | |
| Secondary | `--secondary` | `hsl(85 22% 48%)` | Slightly darker sage |
| Accent | `--accent` | `hsl(22 55% 56%)` | Lighter copper for dark-mode contrast |
| Muted | `--muted` | `hsl(28 14% 24%)` | |
| Muted Foreground | `--muted-foreground` | `hsl(28 10% 65%)` | |
| Border | `--border` | `hsl(40 20% 50%)` | Soft cream-ish 1px |
| Border Bold | `--border-bold` | `hsl(40 30% 92%)` | **Inverted — cream outline on dark surfaces** |
| Ring | `--ring` | `hsl(38 70% 62%)` | Honey ring |
| Destructive | `--destructive` | `hsl(14 55% 52%)` | Lighter rust for contrast |
| Success | `--success` | `hsl(95 30% 52%)` | Lighter moss |
| Warning | `--warning` | `hsl(38 65% 68%)` | Honey unchanged |
| Info | `--info` | `hsl(205 50% 65%)` | Sky slightly darker for legibility on dark |

## Charm Status Vocabulary

Domain / inbox lifecycle states map directly to primitives — no invented tokens.

| Lifecycle State | Token | Visual Treatment |
|-----------------|-------|------------------|
| Incubating | `--sky` | Outlined sky pill, ink text |
| Reserve | `--sage` | Outlined sage pill, ink text |
| Live | `--moss` | Filled moss + cream-light text |
| Dead (rest cycle) | `--ink-soft` | Outlined ink-soft pill |
| Burned | `--rust` | Outlined rust pill |
| Kill-pending (needs operator nod) | `--amber` (filled) | Filled amber + ink text — hearth signal |
| EOD reapply scheduled | `--amber` (outlined) | Outlined amber pill, ink text |
| Disconnected | `--storm` | Outlined storm pill |
| Drift detected | `--honey` | Outlined honey pill |
| Quarantined | `--rust` (filled) | Filled rust + cream text |

## Chart Palette

5-color rotation to prevent single-bar domination. Use in this order for default charts:

1. `var(--amber)` (Calcifer)
2. `var(--sage)`
3. `var(--copper)`
4. `var(--sky)`
5. `var(--rose-deep)`

Burn-velocity charts, kill-breakdown charts, hypertide drift charts all rotate this 5-step cycle.

## Usage Rules

- **NEVER** use raw HSL values in components — always reference CSS variables.
- **NEVER** use `#fff`, `#000`, or default Tailwind colors (blue-500, gray-100, slate-*, zinc-*).
- **NEVER** use `border-radius: 0` on interactive elements (sharp corners are out-of-vocabulary).
- **NEVER** use gradients. The film has no gradients. The UI has no gradients.
- **NEVER** use soft drop-shadows where `--shadow-flat` could carry the elevation. See [[design-system/tokens/effects]].
- Primary (amber) is for CTAs only — overuse dilutes Calcifer's signal.
- Muted/secondary for supporting elements; ink-soft for captions.
- Status pills use *outlined* style by default; *filled* style reserved for "action required" states (kill-pending, quarantined).

## Contrast Notes (light mode)

| Combination | Approx Ratio | WCAG | Status |
|-------------|-------|------|--------|
| ink on cream-light | 11:1 | AAA | Pass |
| ink on amber | 5.2:1 | AA Large | Pass for headings + buttons |
| cream-light on rust | 6.1:1 | AA | Pass |
| cream-light on copper | 4.8:1 | AA | Pass for body |
| ink-soft on cream-light | 7.4:1 | AAA | Pass |

Run a contrast audit during `/design-review` for any new color pairings outside this table.

## See Also

- [[design-system/tokens/index]]
- [[design-system/tokens/typography]]
- [[design-system/tokens/spacing]]
- [[design-system/tokens/effects]]
- [[design-system/references/ref-paperclip]] — source
- [Source: paperclip colors.md](D:\Work\paperclip\docs\design-system\tokens\colors.md)
