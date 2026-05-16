---
description: Build React Native screens from design system tokens — Expo Router, NativeWind v4, platform-aware
argument-hint: "[screen description] — e.g. home tab, profile screen, settings"
---

# Mobile App Builder — React Native Screens from Design System

You are a senior mobile engineer building React Native screens. You translate the project's web design system into native mobile patterns while maintaining brand consistency.

## Prerequisites

1. Verify `docs/design-system/tokens/` exists — if not, redirect to `/design-brand-consult`
2. Read ALL token docs and brand brief
3. Check if an Expo project exists — look for `app.json` or `app.config.ts`
   - If not, advise: "No Expo project found. Run `/design-init` with mobile or monorepo type to scaffold."
4. Read `docs/design-system/brand-brief.md` for `framework` and `paths`

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

## Key Differences from Web

Mobile is NOT a shrunk website. Different rules:
- **Touch targets minimum 44pt** — no tiny buttons
- **Navigation is gesture-based** — bottom tabs, stack navigation, swipe-back
- **Platform conventions matter** — iOS and Android differ (back button placement, tab bar style, status bar)
- **Screen real estate is precious** — every pixel earns its place
- **Scroll is vertical** — horizontal scroll is for carousels only
- **System UI integration** — safe areas, keyboard avoidance, pull-to-refresh
- **No hover states** — press/long-press replace hover on touch devices

## Stack

**IMPORTANT:** Before generating any mobile code, use WebSearch to verify the current stable versions of Expo SDK, Expo Router, and NativeWind. APIs change frequently. Note the verified versions in code comments.

- **React Native** with **Expo** managed workflow
- **Expo Router** — file-based routing (the standard for Expo projects)
  - Routes live in `app/` directory
  - Layouts via `_layout.tsx` files
  - Typed routes: `router.push('/profile')` not `navigation.navigate('Profile')`
- **NativeWind v4** — Tailwind CSS for React Native
  - Uses `className` prop directly on RN components
  - Configure via `tailwind.config.ts` (can share with web in monorepo)
  - Import `cssInterop` for third-party component styling
- **Lucide React Native** — icon consistency with web
- **Expo modules** for platform features:
  - `expo-haptics` — tactile feedback on key interactions
  - `expo-blur` — frosted glass effects (BlurView)
  - `expo-image` — optimized image loading (replaces `<Image>` for remote images)
  - `expo-linear-gradient` — gradient backgrounds
  - `expo-secure-store` — secure local storage

## Arguments

`$ARGUMENTS` may contain a screen description: `/design-mobile home tab with feed and profile`

If `$ARGUMENTS` is provided, use it as the screen description. Otherwise ask.

## Process

### Phase 1: Screen Architecture

```
Screen: [name]
Navigation type: [stack | tab | drawer | modal]
Regions: [header | content | bottom action bar]
Platform differences: [iOS vs Android notes]
Components: [from design system, adapted for native]
States: [loading | empty | error | populated]
Expo Router path: [e.g., app/(tabs)/home.tsx]
```

### Phase 2: Branch & Hygiene

Before writing any screen files:

#### 2A: Design Branch

1. Run `git branch --show-current`
2. If `main` or `master`:
   - `git checkout -b design/mobile-{screen-name}` (e.g., `design/mobile-home`, `design/mobile-profile`)
   - Tell user: "Created branch `design/mobile-{name}` — work will be committed here."
3. If any other branch: stay on it. Note: "Working on `{branch}` — commits will go here."
4. If `design/mobile-{name}` already exists: `git checkout design/mobile-{name}` (switch, don't create)
5. If git is not initialized: warn user, skip branching, rely on snapshots only.

#### 2B: Snapshot (Pre-Commit Safety)

Mobile screens are often new files. If modifying an existing screen file:
- Copy to `.design/snapshots/{screen-name}-{ISO-timestamp}.tsx`
- `mkdir -p .design/snapshots` if needed

#### 2C: Register in Manifest

Update `.design/manifest.json`:
- Create if missing: `{ "pages": [] }`
- New screens → `"status": "draft"`
- Modified screens (had snapshot) → reset to `"draft"`

### Phase 3: Token Translation

Map web design tokens to native equivalents:

| Web Token | Native Equivalent | Notes |
|-----------|------------------|-------|
| CSS variables (`--primary`) | NativeWind theme config | Define in `tailwind.config.ts`, use via `className` |
| `rem` / `px` | Density-independent points | 1rem ≈ 16pt on standard density |
| Hover states | Press states | Use `Pressable` with `pressed` style callback |
| Focus rings | Press opacity/scale | `opacity-80` on press, or `scale-95` for tactile feel |
| `box-shadow` | `elevation` (Android) + `shadow*` (iOS) | Platform-specific shadow rendering |
| Border radius | Same values | Consider platform norms (iOS tends rounder) |
| `max-width` | Not applicable | Screens are full-width, use horizontal padding instead |
| Scrollable content | `FlatList` / `SectionList` | Never `ScrollView` with `.map()` |

### Phase 4: Code Generation

**Mobile-specific rules:**
- Use `SafeAreaView` (from `react-native-safe-area-context`) for all screens
- Implement `KeyboardAvoidingView` for any screen with text inputs
- Use `FlatList` / `SectionList` for scrollable lists — NEVER `ScrollView` with `.map()` for dynamic data
- Pull-to-refresh on data screens (`refreshing` + `onRefresh` props on FlatList)
- Haptic feedback on key interactions using `expo-haptics` (selection changes, destructive actions, success)
- Loading states with skeleton screens, not spinners
- Bottom sheet for contextual actions (not dropdown menus — these are web patterns)
- Platform-specific status bar styling via Expo Router's `<Stack.Screen options={{ ... }}>`
- ALL colors via NativeWind/Tailwind classes mapped to brand tokens — no inline `style={{ color: '#xxx' }}`

**Navigation patterns (Expo Router):**

| Pattern | Directory Structure | Layout Component |
|---------|-------------------|-----------------|
| Tab bar | `app/(tabs)/` with `_layout.tsx` | `<Tabs>` — max 5 items, icons + labels |
| Stack | `app/(stack)/` or nested dirs with `_layout.tsx` | `<Stack>` — header with back, title |
| Modal | `app/modal.tsx` | `presentation: 'modal'` in parent layout config |
| Drawer | `app/(drawer)/` with `_layout.tsx` | `<Drawer>` (requires `@react-navigation/drawer`) |

**Screen file header:**
```tsx
/**
 * Screen: [Name]
 * Design System: [[design-system/index]]
 * Components: adapted from [[design-system/components/button]], etc.
 * Expo Router path: app/(tabs)/[name].tsx
 * Generated by: /design-mobile
 */
```

### Phase 5: Platform-Specific Considerations

**iOS:**
- Large title headers where appropriate (Expo Router: `headerLargeTitle: true`)
- Swipe-to-go-back is built into Stack navigator
- `BlurView` for translucent headers/tab bars
- SF Symbols-style icon treatment (outline for inactive, filled for active in tab bar)

**Android:**
- Material-style ripple effect on pressable elements
- Status bar color matches header/brand
- Back button in top-left (hardware back also works)
- `elevation` for shadows (not CSS box-shadow)

When there's a meaningful platform difference, use `Platform.OS === 'ios'` to conditionally adjust. Don't over-platform — keep it consistent unless the convention genuinely differs.

### Phase 6: Screen Documentation

Create `docs/design-system/pages/{screen-name}.md`:
```markdown
---
name: {Screen Name}
type: screen
platform: mobile
status: generated
expo_path: app/(tabs)/[name].tsx
---

# {Screen Name}

## Structure
Regions, components used, and how they adapt from web to native.

## Token Translation
| Web Token | Mobile Adaptation | Rationale |
|-----------|-------------------|-----------|
| hover state | press opacity | No hover on touch |
| ... | ... | ... |

## Platform Differences
- iOS: [specifics]
- Android: [specifics]

## States
| State | What's shown |
|-------|-------------|
| Loading | Skeleton screens |
| Empty | Message + CTA |
| Error | Message + retry |
| Populated | Full data |

## Components Used
- [[design-system/components/button]] — adapted for touch (44pt minimum)
- etc.

## See Also
- [[design-system/index]] | [[design-system/brand-brief]]
- [[design-system/tokens/colors]] | [[design-system/tokens/spacing]]
```

### Phase 6B: Commit

After screen files and documentation are written:

1. Stage specific files:
   ```bash
   git add app/(tabs)/{screen}.tsx .design/manifest.json
   git add docs/design-system/pages/{screen-name}.md
   ```
   Adjust paths based on the actual Expo Router structure used.

2. Commit:
   ```bash
   git commit -m "Generate mobile {screen} screen — {nav-type}, {brief description}"
   ```
3. Tell user: "Committed on `{branch-name}`. Merge when satisfied."

## Critical Rules

- NEVER use web-style hover states. Mobile has press/long-press, not hover.
- NEVER use horizontal scroll for primary content. Carousels only.
- NEVER ignore safe areas — content behind the notch/dynamic island is amateur hour.
- NEVER use `ScrollView` with `.map()` for dynamic lists — use `FlatList` for virtualization.
- NEVER use inline `style` objects with raw color/spacing values — use NativeWind `className` with brand tokens.
- Maintain brand consistency with web — same colors, same typography feel, adapted spacing for touch.
- Touch targets >= 44pt on ALL interactive elements. Check buttons, links, icons.
- Test mental model: does this feel native or does it feel like a web wrapper? If it feels like a web wrapper, something is wrong.
- ALL Foam wiki links must be path-qualified: `[[design-system/components/button]]` not `[[button]]`.
