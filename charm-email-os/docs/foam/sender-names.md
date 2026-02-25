# Sender Names

Sender name configuration and variation generation for email inbox creation.

## Overview

Each [[clients|client]] needs sender identities for their email inboxes. Rather than creating many unique names, the system generates **variations** from a small number of **base names** (seeds).

## Concept: Base Names to Variations

```
Base Name (Seed)          Variations Generated
─────────────────         ────────────────────
"Chris Booth"      →      chris.booth
                          c.booth
                          chrisbooth
                          chris.b
                          cbooth
                          booth.chris
                          chris_booth
                          chris.booth1
                          chris.booth2
```

A client typically provides 1-2 real identities. The system generates 10 unique email prefix variations from those seeds.

## Data Sources

### 1. Campaign Documentation
When a customer submits campaign documentation:
- Extract founder/sender names from docs
- Auto-populate base names with `isFounder: true`

### 2. Manual Entry
Via the **Names Tab** in the Domains/Inboxes page:
- Add base names (first name, last name)
- Mark one as "Founder" if applicable
- Generate variations on demand

## Variation Patterns

| Pattern | Example | Description |
|---------|---------|-------------|
| `firstname.lastname` | chris.booth | Full name with dot separator |
| `f.lastname` | c.booth | First initial + last name |
| `firstnamelastname` | chrisbooth | Concatenated, no separator |
| `firstname.l` | chris.b | First name + last initial |
| `flastname` | cbooth | First initial + last name (no dot) |
| `lastname.firstname` | booth.chris | Reversed order |
| `lastname.f` | booth.c | Last name + first initial |
| `firstname_lastname` | chris_booth | Underscore separator |
| `numbered` | chris.booth1 | Base pattern with suffix |

## Data Model

### Base Name (Seed)

```typescript
interface BaseName {
  firstName: string;      // "Chris"
  lastName: string;       // "Booth"
  isFounder?: boolean;    // If true, prioritized in generation
}
```

### Sender Name Variation

```typescript
interface SenderNameVariation {
  firstName: string;      // Display first name (may be abbreviated)
  lastName: string;       // Display last name (may be abbreviated)
  emailPrefix: string;    // e.g., "chris.booth", "c.booth"
  baseName: string;       // Reference: "Chris Booth"
  pattern: string;        // Pattern used for generation
  isFounder?: boolean;    // Inherited from base name (for first variation)
}
```

## Storage

Stored in `client.onboardingData`:

```json
{
  "baseSenderNames": [
    {"firstName": "Chris", "lastName": "Booth", "isFounder": true}
  ],
  "variationPatterns": [
    "firstname.lastname",
    "f.lastname",
    "firstnamelastname"
  ],
  "preGeneratedSenderNames": [
    {"firstName": "Chris", "lastName": "Booth", "emailPrefix": "chris.booth", ...},
    {"firstName": "C", "lastName": "Booth", "emailPrefix": "c.booth", ...}
  ]
}
```

## UI Component: Names Tab

Located in `components/inboxes/SenderNamesTab.tsx`

### Sections

1. **Base Names (Seeds)**
   - Add/remove base identities
   - Mark one as "Founder"
   - First/last name input fields

2. **Variation Patterns**
   - Checkboxes to select which patterns to use
   - Live preview of pattern output

3. **Generated Variations**
   - Table with: Name, Email Prefix, Pattern, Status
   - Approval checkboxes per row
   - "Save to Client" button

### Table Columns

| Column | Content |
|--------|---------|
| # | Row number |
| Name | Full base name (e.g., "Chris Booth") |
| Email Prefix | Generated prefix (e.g., "chris.booth") |
| Pattern | Pattern variable used |
| Status | Saved (green) or New (gray) |

## API Endpoints

### Generate Variations

```
POST /api/v1/clients/{client_id}/generate-name-variations
```

**Request:**
```json
{
  "baseNames": [{"firstName": "Chris", "lastName": "Booth", "isFounder": true}],
  "patterns": ["firstname.lastname", "f.lastname", "firstnamelastname"],
  "count": 10
}
```

**Response:**
```json
{
  "variations": [
    {"firstName": "Chris", "lastName": "Booth", "emailPrefix": "chris.booth", "baseName": "Chris Booth", "pattern": "firstname.lastname"},
    ...
  ]
}
```

### Save Names

```
PUT /api/v1/clients/{client_id}/sender-names
```

Saves base names, patterns, and approved variations to client record.

## Backend Generation Logic

Located in `api/data/name_variations.py`:

```python
VARIATION_PATTERNS = {
    'firstname.lastname': lambda f, l: f"{f.lower()}.{l.lower()}",
    'f.lastname': lambda f, l: f"{f[0].lower()}.{l.lower()}",
    # ... other patterns
}

def generate_variations(base_names, patterns, count=10):
    """
    1. Generate one variation per pattern for each base name
    2. If count > patterns * base_names, add numbered suffixes
    3. Return unique variations (no duplicate prefixes)
    """
```

## Integration with Inbox Setup

When the [[inbox-purchase-wizard|InboxPurchaseWizard]] runs:

1. Load `client.onboardingData.preGeneratedSenderNames`
2. Display in Step 2 (Names) of the wizard
3. Send to Hypertide for inbox creation
4. Each variation becomes an inbox: `{emailPrefix}@{domain}`

## Workflow

```
Campaign Docs Submitted
       │
       ▼
Names Extracted (optional)
       │
       ▼
Names Tab: Add/Edit Base Names
       │
       ▼
Select Variation Patterns
       │
       ▼
Generate Variations (up to 10)
       │
       ▼
Review & Approve Variations
       │
       ▼
Save to Client Profile
       │
       ▼
Inbox Setup Wizard Loads Names
       │
       ▼
Hypertide Creates Inboxes
```

## Related

- [[infrastructure]] - Domain and inbox management
- [[workflows]] - Infrastructure provisioning workflow
- [[inbox-purchase-wizard]] - Inbox creation process
- [[clients]] - Client data model

---
Tags: #sender-names #infrastructure #inbox-setup
