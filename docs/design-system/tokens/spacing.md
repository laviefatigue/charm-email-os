---
name: Spacing
type: tokens
status: defined
---

# Spacing Scale

Verbatim lift from [[design-system/references/ref-paperclip]] §Spacing. 4px base unit (Tailwind-compatible).

## Base Grid

**4px base unit.** All spacing tokens are multiples of 4. Maps 1:1 to Tailwind's default scale.

## Scale `[scraped]`

| Token | Value | Rem | Common Use |
|-------|-------|-----|-----------|
| `--space-1` | 4px | 0.25rem | Icon-to-text, status-dot-to-label |
| `--space-2` | 8px | 0.5rem | Small internal padding, tag/badge padding |
| `--space-3` | 12px | 0.75rem | Compact element spacing, form field gap |
| `--space-4` | 16px | 1rem | Default element spacing |
| `--space-5` | 20px | 1.25rem | Slightly larger than default |
| `--space-6` | 24px | 1.5rem | Card internal padding (default) |
| `--space-8` | 32px | 2rem | Section sub-group spacing |
| `--space-10` | 40px | 2.5rem | Generous gaps |
| `--space-12` | 48px | 3rem | Section internal padding |
| `--space-16` | 64px | 4rem | Section top/bottom padding |
| `--space-20` | 80px | 5rem | Generous section separator |
| `--space-24` | 96px | 6rem | Hero section bottom padding |
| `--space-32` | 128px | 8rem | Major section / hero padding |

## Density Direction — Critical for Charm

The Village's density model: **generous between surfaces, dense inside surfaces.**

- *Between* cards, sections, panels: generous breathing room (`--space-12` minimum between sections; `--space-6` gap between workspace cards).
- *Inside* outlined cards: full operator density (tables of inboxes/domains/events pack freely; no internal padding bloat).

This is what enables operator-grade information density without feeling chaotic. The outlined card provides the "frame"; inside, data lives.

| Surface | Padding |
|---------|---------|
| Workspace card | `--space-6` (24px) internal |
| Event-log row | `--space-3` (12px) vertical inside the card |
| Domain table cell | `--space-2` (8px) vertical, `--space-3` (12px) horizontal |
| Modal | `--space-8` (32px) internal |
| Section (between sub-areas of a page) | `--space-12` to `--space-16` |
| Top-level page padding | `--space-8` (32px) on desktop |

## Layout `[scraped]`

| Property | Value | Confidence | Source |
|----------|-------|------------|--------|
| Max content width | 1280px | `[scraped]` | [[design-system/references/ref-paperclip]] |
| Reading column max | 680px | `[scraped]` | (for docs / long-form, not operator views) |
| Mobile side padding (< 640px) | `--space-4` (16px) | `[scraped]` | |
| Tablet side padding (640–1024px) | `--space-6` (24px) | `[scraped]` | |
| Desktop side padding (> 1024px) | `--space-8` (32px) | `[scraped]` | |
| Gutter between columns | `--space-6` (24px) | `[scraped]` | |
| Sidebar (collapsed) | 64px | `[scraped]` | |
| Sidebar (expanded) | 240px | `[scraped]` | |

## Grid for Workspace Cards on Home

5 active workspaces. Default grid:

- Desktop (≥ 1024px): 3 columns, `--space-6` gap, cards auto-sized to content
- Tablet (640–1024px): 2 columns
- Mobile (< 640px): 1 column

Card aspect: content-driven (taller cards for workspaces with more pending integrations / drift). No fixed aspect ratio — let the content breathe.

## Usage Rules

- **NEVER use arbitrary values** (`p-[13px]`, `gap-[7px]`) — only scale values.
- Section padding should use `--space-16` or larger.
- Card padding default is `--space-6`; can compress to `--space-4` for dense tables inside a card.
- Consistent gaps within a single component: pick ONE value and stick to it.
- Sidebar gets its own width tokens, never `--space-*`.

## See Also

- [[design-system/tokens/index]]
- [[design-system/tokens/colors]]
- [[design-system/tokens/typography]]
- [[design-system/tokens/effects]]
- [[design-system/references/ref-paperclip]] — source
- [Source: paperclip spacing.md](D:\Work\paperclip\docs\design-system\tokens\spacing.md)
