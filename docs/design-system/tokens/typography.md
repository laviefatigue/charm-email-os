---
name: Typography
type: tokens
status: defined
---

# Typography

Verbatim lift from [[design-system/references/ref-paperclip]] §Typography. All fonts open-source (OFL). Self-hostable via `npm` packages — no licensing wrinkles.

## Font Stack `[scraped]`

| Role | Font | Fallback Stack | Source | Confidence |
|------|------|---------------|--------|------------|
| Headings (h1–h4, display) | **Fraunces** | `Georgia, "Times New Roman", serif` | Google Fonts (OFL) / [[design-system/references/ref-paperclip]] | `[scraped]` |
| Body, UI labels, table rows | **Manrope** | `"Public Sans", "Atkinson Hyperlegible", system-ui, sans-serif` | Google Fonts (OFL) / [[design-system/references/ref-paperclip]] | `[scraped]` |
| Mono (IDs, timestamps, domain names, EB campaign IDs, JSON payloads) | **Geist Mono** | `"JetBrains Mono", "Fira Code", ui-monospace, monospace` | Vercel `npm i geist` (OFL) / [[design-system/references/ref-vercel]] | `[scraped]` |

### Loading (Next.js App Router)

```ts
// app/layout.tsx
import { Fraunces, Manrope } from "next/font/google";
import { GeistMono } from "geist/font/mono";

const fraunces = Fraunces({
  subsets: ["latin"],
  axes: ["SOFT", "WONK", "opsz"],
  variable: "--font-heading",
});
const manrope = Manrope({ subsets: ["latin"], variable: "--font-body" });
// Geist Mono comes pre-configured via the `geist` package
```

Then in CSS:

```css
:root {
  --font-heading: var(--font-fraunces);
  --font-body: var(--font-manrope);
  --font-mono: var(--font-geist-mono);
}
```

## Fraunces Variable Axes

Fraunces is a variable serif with `wght`, `opsz` (optical size), `SOFT` (terminal softness), and `WONK` (irregular alt glyphs). Settings per role:

| Use | `wght` | `opsz` | `SOFT` | `WONK` |
|-----|--------|--------|--------|--------|
| h4 (body-size headings, card titles) | 600 | 14 | 50 | 0 |
| h3 (sub-section heads) | 600 | 20 | 75 | 0 |
| h2 (section heads) | 700 | 24 | 75 | 0 |
| h1 (page title) | 800 | 36 | 100 | 1 |
| Display / hero (workspace name on detail page) | 900 | 60 | 100 | 1 |

`SOFT` softens terminals (more cartoon-leaning, on-narrative). `WONK` engages alternate slightly-irregular glyphs — **display only**; never on body or running headings.

## Type Scale (8-step, 1.250 major-third ratio)

| Token | Size | Line Height | Weight | Use |
|-------|------|-------------|--------|-----|
| `--text-xs` | 12px / 0.75rem | 1.5 | 400 | Captions, metadata, table sub-rows |
| `--text-sm` | 14px / 0.875rem | 1.5 | 400 | Secondary text, form helper, table body |
| `--text-base` | 16px / 1rem | 1.6 | 400 | Body text, default UI |
| `--text-lg` | 18px / 1.125rem | 1.5 | 500 | Lead paragraphs |
| `--text-xl` | 20px / 1.25rem | 1.4 | 600 | h4 — card titles, workspace card name |
| `--text-2xl` | 24px / 1.5rem | 1.3 | 600 | h3 — section heads (Domains / Inboxes / Events) |
| `--text-3xl` | 30px / 1.875rem | 1.2 | 700 | h2 — page sub-titles |
| `--text-4xl` | 36px / 2.25rem | 1.15 | 700 | h1 — page titles |
| `--text-5xl` | 48px / 3rem | 1.05 | 800 | Display / hero (workspace name on detail page) |

## Letter-Spacing

| Use | Value |
|-----|-------|
| Display (h1, hero) | `-0.02em` (tighter for large Fraunces) |
| Headings (h2–h4) | `-0.01em` |
| Body | `0` |
| Small caps / micro labels | `0.02em` |
| Code / Mono | `0` |

## Usage Rules

- **Headings are Fraunces ONLY.** Card titles, page headers, section heads — all Fraunces.
- **UI emphasis is bold-Manrope.** Inline bold inside body copy uses Manrope at 600/700 — never Fraunces.
- **Mono is for IDs / data, not body.** Use Geist Mono for: domain names in tables (`vapor-pulse.email`), EB campaign IDs (`cmp_01HX...`), inbox addresses, timestamps (`2026-05-15T14:32:19Z`), JSON payloads in event-log detail panels.
- **Never mix more than 2 families.** Fraunces + Manrope is the system. Mono is a third *only* for code-tone tokens — never for prose or UI labels.
- **Never use font-weight below 400 for body text.** Readability over delicacy.
- **Never use display sizes (4xl+) for anything other than page titles or workspace detail hero.**

## Heading + Body Pairing (visual reference)

```
WORKSPACE: HYPERTIDE          ← --text-5xl Fraunces 900, opsz 60, SOFT 100, WONK 1
Last refresh: 12m ago         ← --text-sm Manrope 400, ink-soft
                                
Domains                       ← --text-2xl Fraunces 700, SOFT 75
  vapor-pulse.email           ← Geist Mono 14px, ink
  echo-pearl.email            ← Geist Mono 14px, ink
  drift-anchor.email          ← Geist Mono 14px, ink

Approve kill                  ← --text-base Manrope 600 on amber CTA
```

## See Also

- [[design-system/tokens/index]]
- [[design-system/tokens/colors]]
- [[design-system/tokens/spacing]]
- [[design-system/tokens/effects]]
- [[design-system/references/ref-paperclip]] — source
- [[design-system/references/ref-vercel]] — Geist Mono contribution
- [Source: paperclip typography.md](D:\Work\paperclip\docs\design-system\tokens\typography.md)
