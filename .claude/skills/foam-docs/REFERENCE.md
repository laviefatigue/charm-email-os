# Foam Documentation Reference

## Efficient Context Scanning

### Grep Patterns for Quick Analysis

```bash
# Find all wiki-links in a file
grep -oE '\[\[[^\]]+\]\]' docs/**/*.md

# Find hub notes (by tag)
grep -l 'tags:.*hub' docs/**/*.md

# Find ADRs
ls docs/adr/*.md

# Find orphan candidates (files not linked anywhere)
# Compare: all files vs all wiki-link targets

# Find broken links (referenced but don't exist)
# Extract [[links]], check if matching .md files exist

# Find outdated docs (updated > 6 months ago)
grep -l 'updated: 2023' docs/**/*.md
```

### Frontmatter Quick Extract

When scanning many files, extract just frontmatter:

```bash
# Get title and tags from all docs
head -20 docs/**/*.md | grep -E '^(title:|tags:)'
```

### Link Graph Mental Model

Build a mental map by identifying:

```
HUBS (high connectivity)     → Read first
├── index.md                 → Project entry
├── architecture.md          → System design
├── *-hub.md                 → Domain entries
│
CONCEPTS (medium connectivity) → Read as needed
├── concepts/*.md            → Definitions
├── Components referenced    → Implementation
│
LEAVES (low connectivity)    → Read if directly relevant
├── guides/*.md              → Procedures
├── reference/*.md           → Specs
└── adr/*.md                 → Decisions (always valuable)
```

### Reading Priority Matrix

| File Type | When to Read | What to Extract |
|-----------|--------------|-----------------|
| index.md | Always first | Structure, key links |
| *-hub.md | When entering domain | Concept inventory |
| adr/*.md | For any non-trivial task | Design rationale |
| concepts/*.md | When concept unclear | Definitions |
| guides/*.md | When doing that task | Procedures |
| reference/*.md | When implementing | Specs, schemas |

---

## Wiki-Link Syntax Deep Dive

### Basic Links

```markdown
[[note-name]]           # Links to note-name.md
[[note-name|Display]]   # Links with custom display text
[[folder/note-name]]    # Links to note in subfolder
[[note-name#section]]   # Links to specific heading
```

### Link Resolution

Foam resolves links in this order:
1. Exact match in same directory
2. Exact match anywhere in workspace
3. Partial match (finds `user-authentication.md` for `[[user-auth]]`)

### Embedding Content

```markdown
![[note-name]]           # Embed entire note
![[note-name#section]]   # Embed specific section
![[image.png]]           # Embed image
```

## Frontmatter Schema

### Required Fields

```yaml
---
title: string           # Human-readable title
created: YYYY-MM-DD     # Creation date
updated: YYYY-MM-DD     # Last modification date
tags: [string]          # Array of tags
---
```

### Optional Fields

```yaml
---
aliases: [string]       # Alternative names for linking
status: string          # draft | review | stable | deprecated
parent: "[[note]]"      # Hierarchical parent
related: ["[[a]]"]      # Key related concepts
summary: string         # One-line summary for graph tooltips
---
```

## Tag Hierarchy

### Standard Prefixes

| Prefix | Purpose | Examples |
|--------|---------|----------|
| `type/` | Document type | `type/concept`, `type/guide`, `type/adr` |
| `domain/` | Business domain | `domain/auth`, `domain/billing` |
| `tech/` | Technology | `tech/python`, `tech/react` |
| `status/` | Document status | `status/draft`, `status/stable` |
| `project/` | Project name | `project/lead-engine` |

### Flat Tags (No Prefix)

Use for high-frequency, obvious categories:
- `concept`, `guide`, `reference`, `hub`
- `api`, `database`, `frontend`, `backend`
- `draft`, `deprecated`

## Graph Optimization

### Hub-and-Spoke Pattern

Create hub notes that serve as entry points:

```
                    [[index]]
                        |
        +---------------+---------------+
        |               |               |
   [[auth-hub]]    [[api-hub]]    [[infra-hub]]
        |               |               |
    +---+---+       +---+---+       +---+---+
    |   |   |       |   |   |       |   |   |
  notes...        notes...        notes...
```

### Avoiding Orphans

An orphan is a note with no incoming links. Prevent orphans by:

1. **Always link from a hub** when creating new notes
2. **Add "Related" sections** with bidirectional links
3. **Use the graph view** periodically to spot disconnected nodes
4. **Create inbox notes** for quick capture, then integrate later

### Link Density Guidelines

| Note Type | Incoming Links | Outgoing Links |
|-----------|---------------|----------------|
| Hub/Index | Many (5+) | Many (10+) |
| Concept | Some (2-5) | Some (3-7) |
| Guide | Few (1-3) | Many (5+) |
| Reference | Few (1-2) | Few (1-3) |

## File Organization

### By Type (Recommended for Small Projects)

```
docs/
├── concepts/
├── guides/
├── reference/
└── adr/
```

### By Domain (Recommended for Large Projects)

```
docs/
├── auth/
│   ├── concepts/
│   ├── guides/
│   └── reference/
├── billing/
│   ├── concepts/
│   └── guides/
└── shared/
    └── concepts/
```

### Mixed (Domain + Type)

```
docs/
├── concepts/           # Cross-cutting concepts
├── auth/              # Auth domain (mixed types)
├── billing/           # Billing domain (mixed types)
└── adr/               # All ADRs together
```

## VS Code Integration

### Recommended Extensions

- **Foam** (`foam.foam-vscode`) - Core Foam functionality
- **Markdown All in One** - Enhanced markdown editing
- **Paste Image** - Quick image embedding

### Useful Commands

| Command | Shortcut | Action |
|---------|----------|--------|
| Foam: Show Graph | - | Open graph visualization |
| Foam: Open Daily Note | - | Create/open today's note |
| Foam: Create Note | - | New note from template |
| Foam: Create Note From Template | - | Choose template |

### Settings (`.vscode/settings.json`)

```json
{
  "foam.edit.linkReferenceDefinitions": "withExtensions",
  "foam.openDailyNote.directory": "daily",
  "foam.openDailyNote.filenameFormat": "yyyy-mm-dd",
  "foam.files.newNotePath": "currentDir",
  "foam.graph.style": {
    "node": {
      "note": { "color": "#277da1" },
      "tag": { "color": "#f94144" }
    }
  }
}
```

## Foam Workspace Setup

### Initialization Checklist

1. Create `.foam/` directory
2. Add templates in `.foam/templates/`
3. Configure `.vscode/settings.json`
4. Create `index.md` as entry point
5. Set up directory structure
6. Add `.foam/config.json` if needed

### `.foam/templates/` Structure

```
.foam/
└── templates/
    ├── concept.md
    ├── guide.md
    ├── adr.md
    └── daily.md
```

## Common Patterns

### Changelog Section

For notes that evolve:

```markdown
## Changelog

- **2024-01-15**: Initial creation
- **2024-01-20**: Added section on X
- **2024-02-01**: Deprecated Y approach, see [[new-approach]]
```

### Status Badges

For visual status in rendered markdown:

```markdown
> **Status**: ![Draft](https://img.shields.io/badge/status-draft-yellow)

> **Status**: ![Stable](https://img.shields.io/badge/status-stable-green)
```

### Cross-Project References

When referencing external projects:

```markdown
## External References

- [Project Repo](https://github.com/org/project) - External link
- [[local-notes-about-project]] - Internal analysis/notes
```

## Quality Metrics

### Healthy Knowledge Base Indicators

| Metric | Healthy Range |
|--------|---------------|
| Orphan notes | < 5% of total |
| Average links per note | 3-7 |
| Hub notes | 1 per ~20 notes |
| Notes without tags | 0 |
| Broken links | 0 |

### Periodic Review Tasks

- [ ] Check graph for orphans weekly
- [ ] Update `updated:` dates when editing
- [ ] Archive deprecated notes (move to `archive/`)
- [ ] Review and merge similar concepts
- [ ] Update hub notes with new additions
