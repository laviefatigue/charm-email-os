---
name: Tokens
type: tokens-index
status: defined
---

# Tokens

Design tokens for Charm Email OS. **All values lifted verbatim from [[design-system/references/ref-paperclip]]** (Village aesthetic — Howl's Moving Castle palette + outlined-flat-chunky idiom). HSL color format throughout. Defined 2026-05-15 via `/design-brand-consult`.

## Token Docs

| Doc | What it covers |
|-----|----------------|
| [[design-system/tokens/colors]] | Howl primitives (amber, honey, cream, ink, sage, moss, etc.), light + dark semantic roles, Charm status vocabulary mapping, chart palette |
| [[design-system/tokens/typography]] | Fraunces (headings, variable axes) + Manrope (body) + Geist Mono (code-tone). 8-step type scale, letter-spacing, font-loading config |
| [[design-system/tokens/spacing]] | 4px base, scale 1–32, density model ("generous between, dense inside"), layout container widths |
| [[design-system/tokens/effects]] | Border-radius (6/10/14/20), 1.5px ink outline as signature, `4px 4px 0 var(--ink)` offset shadow, motion (Ghibli-pacing), focus rings |

## The Three Non-Negotiables

These prevent the UI from reading as generic AI design:

1. **Warm ink, never cold.** `--ink: hsl(28 18% 22%)` replaces `#000`. `--cream-light: hsl(40 40% 94%)` replaces `#fff`.
2. **Offset shadow is the signature.** `4px 4px 0 var(--ink)` reserved for hero surfaces (workspace cards needing attention, kill modals).
3. **Outline carries hierarchy.** Cards, modals, primary buttons all get `--border-bold` (1.5px ink). Fill is secondary.

## Status

| Phase | Status |
|-------|--------|
| Color tokens | ✅ defined (light + dark mode + Charm status vocab) |
| Typography tokens | ✅ defined (Fraunces + Manrope + Geist Mono + Variable axes) |
| Spacing tokens | ✅ defined |
| Effects tokens | ✅ defined |
| Component library | ⏳ pending — run `/design-system` next |
| Page designs | ⏳ pending — run `/design-app` after component library |

## See Also

- [[design-system/index]]
- [[design-system/brand-brief]]
- [[design-system/references/ref-paperclip]] — primary source
- [[design-system/references/index]]
