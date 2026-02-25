# Foam Documentation Templates

Copy-paste ready templates for common documentation scenarios.

---

## Index / Entry Point

```markdown
---
title: Project Documentation
created: {{DATE}}
updated: {{DATE}}
tags: [hub, index]
---

# Project Name Documentation

Welcome to the knowledge base. Start here to explore.

## Quick Links

- [[getting-started]] - New here? Start with this guide
- [[architecture-overview]] - System design and components
- [[api-reference]] - API documentation

## By Domain

### [[auth-hub|Authentication]]
User authentication, authorization, and session management.

### [[api-hub|API]]
REST endpoints, GraphQL schema, webhooks.

### [[infra-hub|Infrastructure]]
Deployment, monitoring, scaling.

## Recent Updates

- {{DATE}}: Created initial documentation structure

## Contributing

See [[contributing-to-docs]] for documentation guidelines.
```

---

## Hub / Map of Content (MOC)

```markdown
---
title: Domain Hub
created: {{DATE}}
updated: {{DATE}}
tags: [hub, domain-name]
---

# Domain Name

Central hub for domain-related documentation.

## Overview

Brief description of this domain and its importance.

## Concepts

Core concepts you need to understand:

- [[concept-1]] - Description
- [[concept-2]] - Description
- [[concept-3]] - Description

## Guides

How-to documentation:

- [[how-to-do-x]] - Step-by-step guide
- [[how-to-do-y]] - Another guide

## Reference

Technical specifications:

- [[api-spec]] - API documentation
- [[data-model]] - Schema definitions

## Decisions

Architecture decisions for this domain:

- [[adr-001-decision]] - Why we chose X
- [[adr-002-decision]] - Approach to Y

## External Resources

- [Official Docs](https://example.com)
- [Tutorial](https://example.com/tutorial)
```

---

## Concept Note

```markdown
---
title: Concept Name
created: {{DATE}}
updated: {{DATE}}
tags: [concept, domain]
aliases: [alternative-name, abbreviation]
---

# Concept Name

**One-sentence definition** of what this concept is.

## Overview

Expanded explanation of the concept. Why it exists, what problem it solves, and how it fits into the larger picture.

Related to: [[related-concept-1]], [[related-concept-2]].

## How It Works

Technical explanation with examples.

### Key Components

1. **Component A**: Description
2. **Component B**: Description

### Example

```code
// Example code or configuration
```

## When to Use

- Scenario 1: When X happens
- Scenario 2: When you need Y

## When NOT to Use

- Anti-pattern: Don't use this when Z

## Related

- [[parent-concept]] - Broader category
- [[sibling-concept]] - Alternative approach
- [[child-concept]] - More specific implementation
- [[guide-using-this]] - Practical guide

## References

- [External documentation](https://example.com)
- [[internal-reference]]
```

---

## How-To Guide

```markdown
---
title: How to Do X
created: {{DATE}}
updated: {{DATE}}
tags: [guide, domain]
---

# How to Do X

Brief description of what you'll accomplish.

## Prerequisites

Before starting, ensure you have:

- [ ] [[prerequisite-concept]] understanding
- [ ] Required tool installed
- [ ] Necessary access/permissions

## Steps

### 1. First Step

Detailed instructions for step 1.

```bash
# Example command
command --flag value
```

### 2. Second Step

Detailed instructions for step 2.

> **Note**: Important callout or tip.

### 3. Third Step

Detailed instructions for step 3.

## Verification

How to confirm the task was successful:

```bash
# Verification command
check-command
```

Expected output:
```
Success message
```

## Troubleshooting

### Issue: Error message X

**Cause**: Why this happens.

**Solution**: How to fix it.

### Issue: Error message Y

**Cause**: Why this happens.

**Solution**: How to fix it.

## Next Steps

- [[follow-up-guide]] - What to do next
- [[related-guide]] - Related task

## Related

- [[concept-this-uses]] - Underlying concept
- [[alternative-approach]] - Different way to achieve same goal
```

---

## API Reference

```markdown
---
title: API Name Reference
created: {{DATE}}
updated: {{DATE}}
tags: [reference, api, domain]
---

# API Name Reference

Technical reference for the API Name API.

## Base URL

```
https://api.example.com/v1
```

## Authentication

See [[authentication-concept]] for details.

```bash
Authorization: Bearer <token>
```

## Endpoints

### GET /resource

Retrieves a list of resources.

**Parameters**

| Name | Type | Required | Description |
|------|------|----------|-------------|
| `limit` | integer | No | Max items (default: 20) |
| `offset` | integer | No | Pagination offset |

**Response**

```json
{
  "data": [],
  "meta": {
    "total": 100,
    "limit": 20,
    "offset": 0
  }
}
```

### POST /resource

Creates a new resource.

**Request Body**

```json
{
  "name": "string",
  "value": "string"
}
```

**Response**

```json
{
  "id": "uuid",
  "name": "string",
  "value": "string",
  "created_at": "ISO8601"
}
```

## Error Codes

| Code | Meaning | Resolution |
|------|---------|------------|
| 400 | Bad Request | Check request body |
| 401 | Unauthorized | Check [[authentication-concept]] |
| 404 | Not Found | Resource doesn't exist |
| 500 | Server Error | Contact support |

## Rate Limits

- 100 requests per minute
- 1000 requests per hour

## Related

- [[api-hub]] - All API documentation
- [[authentication-concept]] - How to authenticate
- [[sdk-usage]] - Using the SDK
```

---

## Architecture Decision Record (ADR)

```markdown
---
title: "ADR-NNN: Decision Title"
created: {{DATE}}
updated: {{DATE}}
tags: [adr, status/proposed, domain]
status: proposed
---

# ADR-NNN: Decision Title

## Status

**Proposed** | Accepted | Deprecated | Superseded by [[adr-xxx]]

## Context

What is the issue that we're seeing that is motivating this decision or change?

Describe:
- The current situation
- The problem or opportunity
- Constraints we're working within
- Related decisions: [[adr-previous]]

## Decision Drivers

- Driver 1: Description
- Driver 2: Description
- Driver 3: Description

## Considered Options

### Option 1: Name

Description of the option.

**Pros:**
- Pro 1
- Pro 2

**Cons:**
- Con 1
- Con 2

### Option 2: Name

Description of the option.

**Pros:**
- Pro 1
- Pro 2

**Cons:**
- Con 1
- Con 2

## Decision

We will use **Option X** because [reasoning].

## Consequences

### Positive

- Positive outcome 1
- Positive outcome 2

### Negative

- Negative outcome 1 (mitigation: how we'll handle it)
- Negative outcome 2

### Neutral

- Change that's neither good nor bad

## Implementation

High-level implementation notes or link to [[implementation-guide]].

## Related

- [[adr-previous]] - Previous related decision
- [[affected-component]] - Component this affects
- [[domain-hub]] - Domain this belongs to
```

---

## Daily Note

```markdown
---
title: {{DATE}}
created: {{DATE}}
tags: [daily]
---

# {{DATE}}

## Summary

One-line summary of the day.

## Tasks

- [ ] Task 1
- [ ] Task 2
- [x] Completed task

## Notes

### Topic 1

Notes about topic 1. Links to [[related-concept]].

### Topic 2

Notes about topic 2.

## Links Created

- [[new-note-today]] - Brief description

## Tomorrow

- Follow up on X
- Continue working on Y
```

---

## Troubleshooting Guide

```markdown
---
title: Troubleshooting X
created: {{DATE}}
updated: {{DATE}}
tags: [guide, troubleshooting, domain]
---

# Troubleshooting X

Common issues and solutions for X.

## Quick Diagnostics

```bash
# Check status
status-command

# View logs
log-command
```

## Common Issues

### Issue: Error Message Here

**Symptoms:**
- What the user sees
- Related error codes

**Cause:**
Why this happens.

**Solution:**

1. Step 1
2. Step 2
3. Step 3

**Prevention:**
How to avoid this in the future.

---

### Issue: Another Error

**Symptoms:**
- Symptom 1

**Cause:**
Explanation.

**Solution:**

```bash
fix-command
```

---

## Escalation

If none of the above solutions work:

1. Gather logs: `collect-logs-command`
2. Note the timestamp and error
3. Contact [[support-team]] or create issue

## Related

- [[component-overview]] - Understanding the component
- [[monitoring-guide]] - How to monitor for issues
```
