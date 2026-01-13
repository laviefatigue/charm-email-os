---
name: foam-docs
description: Enforce Foam documentation conventions when creating or updating project documentation. Use when creating docs, writing notes, documenting features, or when user mentions "foam", "documentation", "wiki", or "knowledge base".
allowed-tools: Read, Write, Edit, Glob, Grep
---

# Foam Documentation Skill

Enforces [Foam](https://foambubble.github.io/foam/) documentation conventions and provides efficient context-gathering from Foam knowledge bases.

## When to Activate

- User asks to create/update documentation
- User mentions "foam", "wiki-links", "knowledge base", "docs"
- Creating README, ADR, or any `.md` file in a docs/ or foam/ directory
- Documenting new features, APIs, or architecture
- **Starting work on a project with Foam docs** (context gathering)
- **User asks to review/understand existing documentation**

---

## Reviewing Foam Documentation (Context Gathering)

Use this workflow to efficiently understand a project's knowledge base before starting work.

### Quick Scan Algorithm (5-Step)

```
1. LOCATE    → Find docs root (docs/, foam/, wiki/, or *.md in root)
2. ENTRY     → Read index.md or README.md (main hub)
3. STRUCTURE → Scan directory tree + hub notes
4. RELEVANT  → Follow wiki-links to task-relevant concepts
5. GAPS      → Note missing docs or broken links
```

### Step 1: Locate Documentation

```bash
# Priority order for finding Foam workspace
docs/           # Most common
foam/           # Explicit Foam directory
wiki/           # Alternative naming
.foam/          # Foam config (docs nearby)
*.md in root    # Flat structure
```

**Action**: Glob for `**/index.md`, `**/README.md`, `**/.foam/`

### Step 2: Read Entry Points

Read in this priority order (stop when found):

| Priority | File | Why |
|----------|------|-----|
| 1 | `docs/index.md` | Foam standard entry |
| 2 | `docs/README.md` | Common alternative |
| 3 | `README.md` (root) | May link to docs |
| 4 | Any `*-hub.md` | Domain entry points |

**Extract from entry point:**
- Project overview / purpose
- Links to key concepts
- Directory structure hints
- Tag taxonomy (if documented)

### Step 3: Map the Structure

**Scan directories** (don't read everything):

```
docs/
├── concepts/     → Core domain knowledge
├── guides/       → How-to procedures
├── reference/    → API specs, schemas
├── adr/          → Architecture decisions (READ THESE)
└── [domain]/     → Domain-specific docs
```

**Identify hub notes** by:
- Files named `*-hub.md`, `*-index.md`, `*-overview.md`
- Files with `tags: [hub]` in frontmatter
- Files with high outgoing link count

**Quick hub scan**: Read hub files to get concept inventory without reading every note.

### Step 4: Follow Relevant Links

Based on the current task, trace wiki-links:

| Task Type | Priority Reads |
|-----------|----------------|
| Bug fix | `[[component]]` → `[[troubleshooting]]` → `[[error-handling]]` |
| New feature | `[[architecture]]` → `[[domain-hub]]` → `[[similar-feature]]` |
| Refactor | `[[adr-*]]` → `[[component]]` → `[[dependencies]]` |
| API work | `[[api-reference]]` → `[[data-model]]` → `[[auth]]` |
| Onboarding | `[[getting-started]]` → `[[architecture]]` → `[[concepts/*]]` |

**Link-following strategy:**
1. Read the directly relevant hub
2. Follow 2-3 most relevant `[[wiki-links]]`
3. Stop when you have enough context (don't over-read)

### Step 5: Note Gaps

While scanning, track:
- Missing documentation for key components
- Broken `[[wiki-links]]` (referenced but don't exist)
- Outdated content (`updated:` date very old)
- Orphan notes (no incoming links)

Report gaps to user if significant.

### Context Summary Template

After review, mentally (or explicitly) summarize:

```
PROJECT CONTEXT
===============
Purpose: [One-line project description]
Tech Stack: [Key technologies from docs]
Architecture: [High-level structure]

KEY CONCEPTS
============
- [[concept-1]]: Brief description
- [[concept-2]]: Brief description
- [[concept-3]]: Brief description

RELEVANT TO CURRENT TASK
========================
- [[directly-relevant]]: Why it matters
- [[related-context]]: Supporting info

DOCUMENTATION GAPS
==================
- Missing: [component] has no docs
- Outdated: [[old-doc]] last updated 2022
- Broken: [[missing-link]] referenced but doesn't exist
```

### Efficiency Tips

| Do | Don't |
|----|-------|
| Read hubs first, then follow links | Read every file sequentially |
| Stop when you have enough context | Over-read "just in case" |
| Extract wiki-links from hubs | Manually search for related docs |
| Check ADRs for architecture decisions | Guess at design rationale |
| Note gaps for later | Try to fix gaps immediately |

### Review Depth by Task

| Task Complexity | Review Depth |
|-----------------|--------------|
| Quick fix | Entry point + 1-2 relevant notes |
| Standard feature | Entry + hub + 3-5 concept notes + ADRs |
| Major refactor | Full structure scan + all relevant ADRs |
| New to project | Entry + architecture + all hubs + key concepts |

---

## Core Foam Conventions

### 1. Wiki-Links (REQUIRED)

**Always use wiki-links** to connect related concepts:

```markdown
<!-- CORRECT -->
See [[authentication]] for auth flow details.
This connects to the [[api-gateway]] service.

<!-- WRONG -->
See [authentication](./authentication.md) for auth flow details.
See the authentication document for details.
```

### 2. File Naming

| Convention | Example |
|------------|---------|
| Kebab-case | `user-authentication.md` |
| Lowercase | `api-reference.md` |
| Descriptive | `deployment-strategy.md` not `deploy.md` |
| No spaces | `error-handling.md` not `error handling.md` |

### 3. Required Frontmatter

Every Foam note MUST have YAML frontmatter:

```yaml
---
title: Human Readable Title
created: 2024-01-15
updated: 2024-01-15
tags: [category, subcategory]
---
```

### 4. Document Structure

```markdown
---
title: Feature Name
created: YYYY-MM-DD
updated: YYYY-MM-DD
tags: [feature, domain]
---

# Feature Name

Brief one-paragraph description of what this is.

## Overview

Expanded context. Link to related concepts: [[related-concept]], [[another-concept]].

## Details

Main content sections...

## Related

- [[parent-concept]] - Parent/category this belongs to
- [[sibling-concept]] - Related at same level
- [[child-concept]] - Sub-topics or implementations

## References

- External links, if any
```

### 5. Graph-Friendly Linking

**Bidirectional awareness**: When creating `[[link-to-B]]` in doc A, consider adding `[[link-to-A]]` in doc B.

**Hub notes**: Create index/MOC (Map of Content) notes that link to related topics:

```markdown
---
title: Authentication Hub
tags: [hub, authentication]
---

# Authentication

Central hub for authentication-related documentation.

## Concepts
- [[oauth2-flow]]
- [[jwt-tokens]]
- [[session-management]]

## Implementation
- [[auth-service]]
- [[middleware-auth]]

## Guides
- [[adding-new-auth-provider]]
```

### 6. Tag Taxonomy

Use consistent, hierarchical tags:

| Category | Tags |
|----------|------|
| Type | `concept`, `guide`, `reference`, `adr`, `hub` |
| Domain | `auth`, `api`, `database`, `frontend`, `infra` |
| Status | `draft`, `review`, `stable`, `deprecated` |

## Directory Structure

```
docs/               # or foam/
├── .foam/          # Foam workspace config
│   └── templates/  # Note templates
├── inbox/          # Quick capture, unsorted notes
├── concepts/       # Core concepts and definitions
├── guides/         # How-to documentation
├── reference/      # API docs, specs
├── adr/            # Architecture Decision Records
├── daily/          # Daily notes (if used)
└── index.md        # Main entry point / hub
```

## Checklist Before Committing

- [ ] Frontmatter present with title, created, updated, tags
- [ ] File name is kebab-case, lowercase, descriptive
- [ ] Wiki-links used for all internal references (`[[concept]]`)
- [ ] At least one incoming link exists (not orphaned)
- [ ] Related section links to parent/sibling concepts
- [ ] Tags follow established taxonomy
- [ ] No broken wiki-links

## Anti-Patterns to Avoid

| Anti-Pattern | Correct Approach |
|--------------|------------------|
| `[Link](./file.md)` | `[[file]]` |
| No frontmatter | Always include YAML frontmatter |
| `My Document.md` | `my-document.md` |
| Orphan notes (no links in/out) | Link from hub or related notes |
| Flat structure | Organize into directories |
| Duplicate concepts | Link to existing, don't recreate |

## Creating New Notes

When user requests new documentation:

1. **Determine type**: concept, guide, reference, ADR, hub?
2. **Choose location**: Which directory fits?
3. **Name file**: kebab-case, descriptive
4. **Add frontmatter**: title, created, updated, tags
5. **Write content**: Follow structure template
6. **Add wiki-links**: Connect to related concepts
7. **Update hubs**: Add link from relevant hub/index
8. **Check for orphans**: Ensure bidirectional linking

## Templates

### Concept Note
```markdown
---
title: Concept Name
created: {{date}}
updated: {{date}}
tags: [concept, domain]
---

# Concept Name

Brief definition in 1-2 sentences.

## Overview

What is this? Why does it matter?

## How It Works

Technical details, diagrams, examples.

## Related

- [[parent-concept]]
- [[related-concept]]
```

### Guide Note
```markdown
---
title: How to Do X
created: {{date}}
updated: {{date}}
tags: [guide, domain]
---

# How to Do X

What you'll accomplish by following this guide.

## Prerequisites

- [[required-concept]]
- Required tools/access

## Steps

### 1. First Step

Details...

### 2. Second Step

Details...

## Troubleshooting

Common issues and solutions.

## Related

- [[concept-this-implements]]
```

### ADR (Architecture Decision Record)
```markdown
---
title: "ADR-NNN: Decision Title"
created: {{date}}
updated: {{date}}
tags: [adr, status/accepted, domain]
status: proposed | accepted | deprecated | superseded
---

# ADR-NNN: Decision Title

## Status

Proposed | Accepted | Deprecated | Superseded by [[adr-xxx]]

## Context

What is the issue motivating this decision?

## Decision

What is the change being proposed/made?

## Consequences

What are the positive and negative outcomes?

## Related

- [[adr-previous]] - Previous related decision
- [[affected-system]]
```
