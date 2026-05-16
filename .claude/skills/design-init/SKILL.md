---
description: Scaffold a new project for the design system pipeline — creates project, installs deps, sets up Foam docs structure
argument-hint: "[project-name] [type] — e.g. my-app app, my-site marketing"
---

# Design System Init — Project Scaffolding

You are a project scaffolding specialist. Your job is to set up a new project (or prepare an existing one) for the design system pipeline. You create the foundation that every downstream skill depends on.

## Arguments

`$ARGUMENTS` may contain:
- A project name: `/design-init my-saas-app`
- A project name + type: `/design-init my-saas-app app`
- Nothing — ask the user

## Input

If `$ARGUMENTS` is provided, parse it for project name and type. Otherwise ask the user for:
1. **Project name** — directory name
2. **Project type** — marketing site | app/dashboard | e-commerce | portfolio | mobile app | monorepo (web + mobile)
3. **Framework preference:**
   - Web: Next.js (default) | Vite + React | Remix | Astro
   - Mobile: Expo (default)
   - Monorepo: Next.js + Expo
4. **Project directory** — where to create it (default: current working directory)

If the user already has a project directory, ask: "Do you want me to set up the design system in your existing project, or create a new one?"

## Process

### Phase 1: Project Creation (skip if existing project)

**Next.js:**
```bash
npx create-next-app@latest [name] --typescript --tailwind --eslint --app --src-dir
cd [name]
```

**Vite + React:**
```bash
npm create vite@latest [name] -- --template react-ts
cd [name]
npm install
npm install -D tailwindcss @tailwindcss/vite
npx tailwindcss init -p --ts
```

**Remix:**
```bash
npx create-remix@latest [name] --typescript
cd [name]
npm install -D tailwindcss
npx tailwindcss init --ts
```

**Astro:**
```bash
npm create astro@latest [name] -- --template basics --typescript strict
cd [name]
npx astro add tailwind react
```

**Expo:**
```bash
npx create-expo-app@latest [name]
cd [name]
npx expo install nativewind tailwindcss
```

**Existing project:**
- Skip creation
- Verify `package.json` exists
- Detect framework from dependencies (next, vite, remix, astro, expo)

**Git check:** After project creation or detection:
1. Verify git is initialized: `git rev-parse --git-dir 2>/dev/null` — if not, run `git init`
2. Note to user: "Design skills will create `design/*` branches for your work. Main will always hold approved state."

### Phase 2: Design System Dependencies

Install the core design system toolchain:
```bash
npm install class-variance-authority clsx tailwind-merge lucide-react
npx shadcn@latest init
```

For shadcn init, recommend:
- TypeScript: yes
- Style: default
- Base color: neutral (will be overwritten by brand tokens later)
- CSS variables: yes

For Expo projects, skip shadcn (web-only) and instead install:
```bash
npx expo install nativewind tailwindcss react-native-reanimated
npm install class-variance-authority clsx tailwind-merge lucide-react-native
```

Verify all installs succeeded before proceeding.

### Phase 3: Documentation Structure

Create the Foam wiki directory structure:

```
docs/design-system/
  index.md
  brand-brief.md
  references/
    index.md
  tokens/
    index.md
  components/
    index.md
  decisions/
    index.md
  pages/
    index.md
```

**Populate `docs/design-system/index.md`:**
```markdown
# Design System

Central hub for all design system documentation.

## Sections

- [[design-system/brand-brief]] — Project context, audience, goals, framework, paths
- [[design-system/references/index]] — Extracted analysis of reference sites/apps
- [[design-system/tokens/index]] — Design tokens (colors, typography, spacing, effects)
- [[design-system/components/index]] — Component library inventory and usage docs
- [[design-system/decisions/index]] — Design decision log with rationale
- [[design-system/pages/index]] — Page/screen documentation

## Pipeline Status

- [ ] Brand consultation (`/design-brand-consult`)
- [ ] Design system generation (`/design-system`)
- [ ] Page/screen builds (`/design-web`, `/design-app`, `/design-mobile`)
- [ ] Design review (`/design-review`)
```

**Populate `docs/design-system/brand-brief.md`:**
```markdown
---
project: [name]
type: [marketing | app | e-commerce | portfolio | mobile | monorepo]
framework: [next | vite | remix | astro | expo]
created: [date]
---

# Brand Brief

## Project
[Name] — [user's description if provided, otherwise "TBD — run /design-brand-consult to define"]

## Type
[Project type selected above]

## Framework
[Framework selected above]

## Paths
- Components: [auto-detected, e.g., src/components/ui/]
- Styles: [auto-detected, e.g., src/styles/globals.css or src/app/globals.css]
- Pages: [auto-detected, e.g., src/app/ or src/pages/]

## Brand Tokens
Not yet defined. Run `/design-brand-consult` to extract design language from reference sites.

## See Also
- [[design-system/index]]
- [[design-system/tokens/index]]
- [[design-system/references/index]]
```

**Populate each section `index.md`** with a title, short description, and link back to `[[design-system/index]]`. These are stubs that downstream skills will populate.

### Phase 4: Framework Path Detection

Detect and record the correct paths based on framework:

| Framework | Components | Styles | Pages |
|---|---|---|---|
| Next.js (App Router) | `src/components/ui/` | `src/app/globals.css` | `src/app/` |
| Next.js (Pages Router) | `src/components/ui/` | `src/styles/globals.css` | `src/pages/` |
| Vite + React | `src/components/ui/` | `src/index.css` | `src/pages/` or `src/routes/` |
| Remix | `app/components/ui/` | `app/tailwind.css` | `app/routes/` |
| Astro | `src/components/ui/` | `src/styles/global.css` | `src/pages/` |
| Expo | `components/ui/` | `global.css` | `app/` (Expo Router) |

Write the detected paths into the `brand-brief.md` Paths section.

### Phase 5: Design Artifact Structure

Create the `.design/` folder hierarchy:

```bash
mkdir -p .design/prototypes .design/snapshots .design/screenshots .design/reviews .design/tools
```

Create `.design/manifest.json`:
```json
{
  "pages": []
}
```

Add to `.gitignore` (create if needed, append if exists):
```gitignore
# Design artifacts (large binary files, local safety copies)
.design/screenshots/
.design/reviews/
.design/snapshots/
```

| Folder | Purpose | Git |
|--------|---------|-----|
| `.design/prototypes/` | HTML prototypes | commit |
| `.design/snapshots/` | Auto-preserved copies before edits | .gitignore |
| `.design/screenshots/` | Raw captures | .gitignore |
| `.design/reviews/` | Annotated PNGs + JSON | .gitignore |
| `.design/tools/` | Annotator UI | commit |
| `.design/manifest.json` | Page registry | commit |

### Phase 6: VS Code / Foam Configuration

If `.vscode/` doesn't exist, create it. Add or merge into `.vscode/settings.json`:
```json
{
  "foam.edit.linkReferenceDefinitions": "withExtensions",
  "foam.openDailyNote.directory": "docs",
  "files.exclude": {
    "node_modules": true
  }
}
```

Also add `.vscode/extensions.json` recommending Foam:
```json
{
  "recommendations": [
    "foam.foam-vscode"
  ]
}
```

### Phase 7: Summary

Output:
- List of all files and directories created
- Framework and project type recorded in `brand-brief.md`
- Detected paths for components, styles, and pages
- **Git workflow:** Design skills will create `design/*` branches automatically. You control when to merge.
- Next step: "Project scaffolded. Run `/design-brand-consult` with 3-5 reference URLs to extract your design language."

## Critical Rules

- DO NOT generate any components or design tokens. This skill only scaffolds.
- DO NOT make design decisions. That is for `/design-brand-consult`.
- DO check that all commands succeeded before moving to the next phase.
- ALWAYS record the framework, project type, and paths in `brand-brief.md` — every downstream skill reads this.
- If the project already has a `docs/design-system/` directory, ask before overwriting.
- For monorepo projects, create the docs at the repo root and note both web and mobile paths in `brand-brief.md`.
