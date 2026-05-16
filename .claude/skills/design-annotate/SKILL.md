---
description: Visual annotation review — read annotated screenshots from .design/reviews/, address each comment, and iterate on designs
argument-hint: "[review-file.json | --latest | --setup] — process a specific review, the most recent one, or install the annotation tool"
---

# Design Annotate — Visual Feedback Loop

This skill has two halves:

1. **Capture tool** (CLI) — a standalone Figma-like annotation tool that captures screenshots, lets the user draw and comment, and saves structured output to `.design/reviews/`
2. **Review skill** (this prompt) — reads saved annotations and acts on the feedback

## Arguments

`$ARGUMENTS` may contain:

- **A JSON file path**: `/design-annotate .design/reviews/dashboard-1440x900-2026-04-10T01-39-22.json` — process that specific review
- **`--latest`**: `/design-annotate --latest` — find and process the most recent review in `.design/reviews/`
- **`--setup`**: `/design-annotate --setup` — install the capture tool into the project
- **Nothing**: check for recent reviews, or ask the user

---

## Mode 1: Setup (`--setup` or tool not installed)

If `annotate.mjs` does not exist in the project root, guide the user through setup:

1. Check for `playwright` in `package.json`. If missing:
   ```bash
   npm install --save-dev playwright
   npx playwright install chromium
   ```

2. Copy the tool files from this skill into the project. Use Glob to find the plugin's source files:
   - Glob for `**/design-annotate/tools/annotate.mjs` to locate the plugin directory
   - Read `annotate.mjs` from that location and Write it to the project root as `annotate.mjs`
   - Read `annotator.html` from the same `tools/` directory and Write it to `.design/tools/annotator.html`

3. Create the canonical folder structure:
   ```bash
   mkdir -p .design/prototypes .design/snapshots .design/screenshots .design/reviews .design/tools
   ```

   | Folder | Purpose | Git |
   |--------|---------|-----|
   | `.design/prototypes/` | HTML prototypes (standalone, Tailwind CDN) | commit |
   | `.design/snapshots/` | Auto-preserved copies before edits | .gitignore |
   | `.design/screenshots/` | Raw captures (unannotated) | .gitignore |
   | `.design/reviews/` | Annotated PNGs + JSON sidecars | .gitignore |
   | `.design/tools/` | Annotator UI | commit |
   | `.design/manifest.json` | Page registry | commit |

4. Create `.design/manifest.json` if it doesn't exist:
   ```json
   {
     "pages": []
   }
   ```

5. Ensure `.gitignore` includes:
   ```gitignore
   .design/screenshots/
   .design/reviews/
   .design/snapshots/
   ```

6. Tell the user:
   > Annotator installed. Launch it with:
   > ```bash
   > node annotate.mjs                         # auto-loads pages from manifest
   > node annotate.mjs .design/prototypes/*.html  # ad-hoc targets
   > node annotate.mjs http://localhost:3000    # live dev server
   > ```
   > Pages are registered in `.design/manifest.json` automatically when you run `/design-web` or `/design-app`.
   > When you're done annotating, hit Complete and run `/design-annotate --latest` to process the feedback.

**Do NOT proceed to review mode. Stop here.**

---

## Mode 2: Review (default)

### Step 1: Find the review

If a specific JSON path was provided in `$ARGUMENTS`, use that.

If `--latest` or no argument, find the most recent review:

```bash
ls -t .design/reviews/*.json | head -5
```

Present the recent reviews to the user and confirm which to process. If only one exists, use it.

### Step 2: Read the feedback

For each review JSON file:

1. **Read the JSON** — parse the structured comment data:
   ```json
   {
     "viewport": "1440x900",
     "comments": [
       { "id": 1, "x": 400, "y": 200, "text": "Too much gap here" }
     ],
     "drawingCount": 3
   }
   ```

2. **Read the PNG** (same filename but `.png`) — view the annotated screenshot to see:
   - Where numbered comment bubbles are placed
   - What's circled, arrowed, or highlighted with drawings
   - The comment legend at the bottom with full text

3. **If a session manifest exists** (`session-*.json`), read it to understand multi-page context

### Step 3: Snapshot before editing

**Before modifying any prototype file, copy it to `.design/snapshots/` with a timestamp.**

```bash
mkdir -p .design/snapshots
```

For each file you're about to edit, read the file and write a copy:
- Source: `.design/prototypes/dashboard.html`
- Snapshot: `.design/snapshots/dashboard-2026-04-10T14-22.html`

Use the current ISO timestamp (date + hour-minute). This is pre-commit safety — fast undo before the next git commit.

### Step 4: Address each comment

For every comment in the review:

1. State the comment: **"#1: Too much gap here"**
2. Identify the relevant code/component
3. Make the fix
4. Report what changed: **"Fixed #1 — reduced section gap from 48px to 24px"**

Work through comments in order. Each fix should be specific and traceable to a comment number.

### Step 5: Update manifest

After applying fixes, update `.design/manifest.json`:
- Set status to `draft` for any page that was modified (it needs re-review)

### Step 5B: Commit Fixes

After all comments are addressed and the manifest is updated:

1. Check current branch with `git branch --show-current`. If on `main` or `master`, warn: "You're on main — consider creating a design branch before committing fixes."
2. Stage modified files:
   ```bash
   git add .design/prototypes/{modified-files} .design/manifest.json
   ```
3. Commit with comment references:
   ```bash
   git commit -m "Address review feedback — fix #{numbers}: {brief summaries}"
   ```
   Example: `"Address review feedback — fix #1, #2, #4: reduce hero gap, increase CTA contrast, fix nav overlap"`
4. Tell user: "Committed fixes on `{branch-name}`."

### Step 6: Summary

After all comments are addressed, output:

```
## Review Summary

Processed: {filename}
Viewport: {viewport}
Comments addressed: {count}
Snapshots saved: {list of snapshot filenames}

| # | Feedback | Fix |
|---|----------|-----|
| 1 | Too much gap here | Reduced section gap 48px → 24px |
| 2 | Font too small | Bumped body text 13px → 14px |
| ... | ... | ... |

**Next step:** Launch annotator for verification.
```

**IMPORTANT:** After outputting the summary, ALWAYS launch the annotator so the user can review the fixes:

```bash
node annotate.mjs
```

This is not optional. Every design iteration ends with the annotator open.

---

## Capture Tool Reference

### Launch

```bash
# From manifest (preferred — loads all registered pages)
node annotate.mjs

# Ad-hoc (for one-off captures)
node annotate.mjs http://localhost:3000
node annotate.mjs .design/prototypes/page.html

# Options (combine with manifest or ad-hoc)
node annotate.mjs --size 1280x800
node annotate.mjs --dpr 1
```

Pages load live in an iframe. Interact with the UI normally, then press Tab to switch to Annotate mode and draw/comment.

### Tools

| Tool | Key | What it does |
|------|-----|-------------|
| Mode toggle | Tab | Switch between **Interact** (use the live page) and **Annotate** (draw/comment) |
| Select | V | Click to select, drag to move any annotation. Delete/Backspace to remove. |
| Pen | P | Freehand drawing (smooth bezier curves) |
| Arrow | A | Click-drag to draw arrows pointing at things |
| Rectangle | R | Click-drag to draw outlined rectangles |
| Comment | C | Click to place numbered bubble, opens text popover |
| Colors | 1-5 | Red, Orange, Yellow, Blue, Green (plus White, Black) |
| Undo | Ctrl+Z | Undo last action |
| Save | Ctrl+S | Save current page (annotated PNG + JSON sidecar) |
| Save All | Ctrl+Shift+S | Save all annotated pages with progress (multi-page) |
| Prev/Next | [ / ] | Navigate between pages (multi-page) |

### Viewport Switcher

Built-in presets (ascending): 1024 → 1280 → 1440 → 1920 → 2560.

**Auto-detect on load:** The annotator reads `window.innerWidth` (the actual browser window width, not the monitor resolution) and snaps to the largest preset that fits. A 1440px browser window snaps to 1440; a maximized browser on a 2560 monitor snaps to 2560.

**Clicking a viewport button** resizes the iframe instantly and reloads the page at the new width (clears annotations for that page — different viewport = different layout context). Playwright capture only runs at Save time.

**Fit-to-width display:** Screenshots are automatically scaled down to fill the annotation canvas. The status bar shows the zoom level (e.g., `viewport: 1440x900 @ 72%`). Annotations are placed at full-resolution coordinates regardless of display zoom — accuracy is not affected.

### AI Refine

Each comment bubble has an "AI Refine" button that sends the note to Claude Haiku for clearer design instructions. Requires `ANTHROPIC_API_KEY`.

### Multi-Page Sessions

Multiple files/URLs → page strip with tabs, independent annotation state per page, green dots on annotated tabs, Save All with progress and session manifest.

### Output Location

Always saved to `.design/reviews/`:

- `{page}-{viewport}-{timestamp}.png` — Annotated screenshot + comment legend
- `{page}-{viewport}-{timestamp}.json` — Structured review data
- `session-{timestamp}.json` — Multi-page manifest (Save All only)

---

## Integration with Pipeline

### Iteration loop

```
Make design changes              →  Edit code, snapshot saved automatically
node annotate.mjs                →  Claude launches annotator (loads from manifest)
User annotates and hits Complete →  .design/reviews/ gets PNG + JSON, manifest updated
/design-annotate --latest        →  Claude reads feedback, snapshots, fixes, commits on branch
node annotate.mjs                →  Claude launches annotator again
                                    (repeat until approved → user merges branch to main)
```

**Every design change ends with the annotator open.** This is not optional. The annotator is how the user gives feedback. If you make design changes and don't launch the annotator, the feedback loop is broken.

After the user saves their annotation and you've processed the review, **kill the annotator server** to free the port. Then relaunch after the next round of fixes.

### With `/design-review`

- `/design-review` — mechanical code audit (tokens, accessibility, AI anti-patterns)
- `/design-annotate` — spatial/visual feedback (layout, spacing, "this feels off")
- Both inform the next generation cycle

---

## Folder Convention

```
.design/
├── manifest.json       ← Page registry — what pages exist + status (committed)
├── prototypes/         ← Current HTML prototypes (committed)
├── snapshots/          ← Auto-preserved copies before edits (gitignored)
├── reviews/            ← Annotated PNGs + JSON sidecars (gitignored)
├── screenshots/        ← Raw captures (gitignored)
└── tools/              ← Annotator UI (committed)
```

- `manifest.json` is the source of truth for what pages exist
- Snapshots preserve previous versions before any edit — local safety net
- Reviews are timestamped and accumulate — old iterations stay for reference
- Never put screenshots or prototypes in the project root

---

## Critical Rules

- **Always snapshot before editing** — copy prototype to `.design/snapshots/` with timestamp before modifying
- **Always launch the annotator after design changes** — this is the feedback mechanism
- **Always kill the server after review is processed** — don't waste ports
- **Always check `.design/reviews/` for output** — canonical location, never save elsewhere
- **Commit after fixes** — after addressing all comments, commit on the current branch referencing comment numbers
- **Don't create branches** — work on whatever branch exists. If on main, warn: "Consider creating a design branch first."
- **Read both PNG and JSON** — the PNG shows spatial context, the JSON gives parseable text
- **Reference comment numbers** in fixes — "Fixed #2" not "fixed the spacing issue"
- **Don't batch comments** — address each one individually so the user can track what was fixed
- **Update manifest status** after changes — `draft` when modified, `reviewed` when annotated
- Screenshots are 2x DPI by default — don't reduce unless the user asks
- Annotations are per-page and per-viewport — changing viewport or navigating to a new URL clears annotations for that page
- The server reads `annotator.html` fresh on every browser refresh — no restart needed after HTML edits
- Auto-detect uses `window.innerWidth`, not monitor resolution — viewport snaps to actual browser window width
- Interact mode = clicks fall through to the iframe (pointer-events: none on canvas). Annotate mode = canvas captures all input
- Navigation guard fires if user clicks a link in the iframe with unsaved annotations — prompts Save or Discard
- Playwright capture runs on-demand at Save time, not at startup — server starts instantly regardless of page count
- Fit-to-width is always on — screenshots scale down to fill the canvas, never scale up
