---
ref: vercel
type: mono-font-only
source-pages:
  - https://vercel.com/font
captured: 2026-05-15
revised: 2026-05-15
status: demoted-single-token-contribution
---

# Reference: Vercel (Geist) — Demoted to Mono Font Token

**Original role:** Visual + structural + token reference for warm-modern direction.
**Revised role:** Single-token contribution. Geist Mono only.

**Why demoted:** User redirected toward full paperclip Village aesthetic. Vercel's visual language (cool-grey-warm-shifted, Swiss-minimal, dense corporate dashboard) was synthesizing-toward-the-middle and diluting the opinionated direction the user wants. We're not stitching together "Vercel structure + paperclip warmth" — we're committing to the Village.

**What survives:** Geist Mono is paperclip's chosen mono font too (per [paperclip typography.md](D:\Work\paperclip\docs\design-system\tokens\typography.md)). It pairs cleanly with Fraunces + Manrope and is OFL-licensed. We lift it for code-tone tokens: timestamps, IDs, domain names, EB campaign IDs in tables, JSON payloads in event-log detail.

**What we drop from Vercel:**
- Geist Sans (paperclip uses Manrope for body — friendlier, more humanist, OFL)
- Geist 1–10 color scale system (paperclip's named-token semantic palette is more opinionated)
- Vercel dashboard structural patterns (paperclip's IA already covers this)
- Vercel's "calm Swiss density" tonality

## Token Contribution

| Token | Value | Source |
|-------|-------|--------|
| `--font-mono` | `"Geist Mono", "JetBrains Mono", "Fira Code", ui-monospace, monospace` | [vercel.com/font](https://vercel.com/font) — OFL |

Installed via `npm i geist` (already in paperclip's stack convention).

## See Also

- [[design-system/references/ref-paperclip]] — primary reference (full lift)
- [[design-system/brand-brief]]
