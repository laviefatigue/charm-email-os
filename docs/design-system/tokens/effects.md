---
name: Effects
type: tokens
status: defined
---

# Visual Effects

Verbatim lift from [[design-system/references/ref-paperclip]] §Effects. This is where the Village's *signature* lives — the outline + offset shadow vocabulary that makes the UI unmistakably non-shadcn-default.

## Border Radius `[scraped]`

| Token | Value | Rem | Use For | Confidence |
|-------|-------|-----|---------|------------|
| `--radius-sm` | 6px | 0.375rem | Status pills, badges, tags | `[scraped]` |
| `--radius-md` | 10px | 0.625rem | Buttons, inputs, dropdowns | `[scraped]` |
| `--radius-lg` | 14px | 0.875rem | Workspace cards, panels, popovers | `[scraped]` |
| `--radius-xl` | 20px | 1.25rem | Modals (kill confirm, firewall override), dialogs | `[scraped]` |
| `--radius-full` | 9999px | — | Avatars, status dots | — |

**Critical:** Never `border-radius: 0` on interactive elements. Sharp corners are out-of-vocabulary against the chunky-cartoon idiom.

## Borders `[scraped]`

| Token | Color | Width | Use For |
|-------|-------|-------|---------|
| `--border-bold` | `var(--ink)` | **1.5px** | **The cartoon-idiom outline.** Workspace cards, modals, primary buttons, hero surfaces. |
| `--border` | `var(--ink-soft)` | 1px | Inputs, dividers, table grid lines, secondary surfaces |

Dark mode: `--border-bold` inverts to cream (`hsl(40 30% 92%)`); `--border` becomes a soft cream-ish hairline. See [[design-system/tokens/colors]] §Dark Mode.

## Shadows `[scraped]`

| Token | Value | Use For |
|-------|-------|---------|
| `--shadow-none` | `none` | Default — most surfaces |
| `--shadow-flat` | `4px 4px 0 var(--ink)` | **Graphic-novel offset shadow.** Hero surfaces only — workspace cards needing attention, kill-confirm modals, the pending-gates panel header. Carries the cartoon idiom. |
| `--shadow-flat-sm` | `2px 2px 0 var(--ink)` | Hover state on cards, popovers, floating elements |
| `--shadow-soft` | `0 4px 16px hsl(28 18% 22% / 0.08)` | **Reserved fallback.** Use only when offset-flat fights surrounding content (rare). Prefer `--shadow-flat`. |

**Critical:** A card with `--border-bold` typically does **not** also need a shadow. Outline + flat fill carries the elevation. Reserve `--shadow-flat` for surfaces that earn "this matters" status:

- Workspace cards with pending gates / drift / over-budget → `--shadow-flat`
- Workspace cards in healthy steady-state → `--border-bold` only, no shadow
- Hover on any card → `--shadow-flat-sm`
- Kill-confirm modal → `--shadow-flat` always (every kill is a hero moment)
- Default outlined card / table / panel → `--shadow-none`

Dark mode: shadow color shifts to `hsl(40 30% 92%)` (cream-light offset on warm-dark surface). The offset still reads.

## Motion `[scraped]`

| Token | Duration | Easing | Use For |
|-------|----------|--------|---------|
| `--duration-instant` | 0ms | — | Checkbox / radio state |
| `--duration-fast` | 150ms | `ease-out` | Hovers, button presses, small state shifts |
| `--duration-normal` | 250ms | `cubic-bezier(0.25, 0.46, 0.45, 0.94)` | Modal open, drawer slides, popover reveals |
| `--duration-slow` | 400ms | `cubic-bezier(0.4, 0, 0.2, 1)` | Page transitions, activity-log scrub |

**Philosophy:** "Studio Ghibli's atmospheric pacing translates to UI as **calm, deliberate, never twitchy**."

Avoid:
- Bouncy springs
- Long durations on small interactions (>200ms for a hover is too slow)
- Cascading staggered animations on lists (a 50-row table should not animate row-by-row)
- Looping idle animations (no pulsing CTAs, no breathing logos)

## Focus States

| Property | Value |
|----------|-------|
| Ring color | `var(--ring)` (amber in light, honey in dark) |
| Ring width | `2px` |
| Ring offset | `2px` |
| Ring style | `solid` (not dashed) |

```css
.focusable:focus-visible {
  outline: 2px solid var(--ring);
  outline-offset: 2px;
}
```

Narrative: the amber ring on a cream-light page reads as Calcifer's hearth-light highlighting your hand — on-narrative for an operator picking a workspace.

## Composition Rules

The three signature moves (do not break):

1. **Warm ink, never cold.** Borders, text, outlines all use `--ink` / `--ink-soft`. Never `gray-*`, never `slate-*`, never `zinc-*`.
2. **Offset shadow as signature.** Only `--shadow-flat` (4px+ offset). Never soft drop-shadows except as last-resort fallback.
3. **Outline carries hierarchy.** A workspace card gets `--border-bold`. A primary button gets the same outline. The amber fill is *secondary* to the outline. Operators learn "outlined = this is a unit."

## See Also

- [[design-system/tokens/index]]
- [[design-system/tokens/colors]]
- [[design-system/tokens/typography]]
- [[design-system/tokens/spacing]]
- [[design-system/references/ref-paperclip]] §The Three Non-Negotiables
- [Source: paperclip effects.md](D:\Work\paperclip\docs\design-system\tokens\effects.md)
