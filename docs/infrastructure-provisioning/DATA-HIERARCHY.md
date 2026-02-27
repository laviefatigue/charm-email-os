# DATA HIERARCHY - Charm Email OS Database

## Database Relationship Structure

```
workspaces (Top Level)
    ↓ (1:many)
clients
    ↓ (has workspace_id FK)
domains
    ↓ (has workspace_id FK)
sender_accounts (inboxes)
    ↓ (has workspace_id FK + domain_id FK)
```

## Table Relationships

### 1. `workspaces` Table (Top Level)
**Primary Key:** `id` (UUID)

**Purpose:** Top-level organizational unit. Represents an EmailBison workspace.

**Key Fields:**
- `workspace_name` - Name of workspace
- `emailbison_workspace_id` - External sync ID to EmailBison
- `is_active` - Active flag
- `sender_account_count` - Count of inboxes
- `domain_count` - Count of domains

**Relationships:**
- Has many `clients` (via `clients.workspace_id`)
- Has many `domains` (via `domains.workspace_id`)
- Has many `sender_accounts` (via `sender_accounts.workspace_id`)
- Has many `sender_names` (via `sender_names.workspace_id`)
- Has many `inbox_purchase_jobs` (via `inbox_purchase_jobs.workspace_id`)

---

### 2. `clients` Table
**Primary Key:** `id` (UUID)
**Foreign Key:** `workspace_id` → `workspaces(id)` (nullable, ON DELETE SET NULL)

**Purpose:** Customer/client records. Each client belongs to a workspace.

**Key Fields:**
- `name` - Client name
- `workspace_id` - Parent workspace
- `onboarding_complete` - Boolean flag
- `contact_name`, `contact_email` - Contact info
- `industry`, `domain_pattern` - Business context

**Relationships:**
- Belongs to one `workspace`
- Has many `inbox_purchase_jobs` (via `inbox_purchase_jobs.client_id`)
- Has many `campaign_cycles` (via `campaign_cycles.client_id`)
- Has many `strategies` (via `strategies.client_id`)

**NOTE:** Clients do NOT directly own domains. Domains belong to workspaces.

---

### 3. `domains` Table
**Primary Key:** `id` (UUID)
**Foreign Key:** `workspace_id` → `workspaces(id)` (NOT NULL)

**Purpose:** Domain records for infrastructure provisioning.

**Key Fields:**
- `workspace_id` - Parent workspace (NOT NULL)
- `domain_name` - The domain
- `approval_status` - 'owned', 'available', 'purchased', etc.
- `infrastructure_type` - 'entra' or 'google'
- `purchased_at`, `price_checked_at` - Lifecycle timestamps
- `purchase_job_id` - FK to `inbox_purchase_jobs(id)`

**Relationships:**
- Belongs to one `workspace` (required)
- Has many `sender_accounts` (via `sender_accounts.domain_id`)
- Optionally linked to one `inbox_purchase_job` (via `purchase_job_id`)

**CRITICAL:** No direct `client_id` FK. Domains are workspace-scoped, not client-scoped.

---

### 4. `sender_accounts` Table (Inboxes)
**Primary Key:** `id` (UUID)
**Foreign Keys:**
- `workspace_id` → `workspaces(id)` (NOT NULL)
- `domain_id` → `domains(id)` (nullable)

**Purpose:** Email inbox records provisioned from HyperTide.

**Key Fields:**
- `workspace_id` - Parent workspace
- `domain_id` - Associated domain
- `email_address` - Full email
- `esp_type` - 'gmail', 'microsoft', 'other'
- `emailbison_account_id` - External sync ID

**Relationships:**
- Belongs to one `workspace` (required)
- Belongs to one `domain` (optional)

---

### 5. `inbox_purchase_jobs` Table
**Primary Key:** `id` (UUID)
**Foreign Keys:**
- `client_id` → `clients(id)` (NOT NULL, ON DELETE CASCADE)
- `workspace_id` → `workspaces(id)` (nullable)

**Purpose:** HyperTide order jobs for inbox provisioning.

**Key Fields:**
- `client_id` - Which client ordered this
- `workspace_id` - Target workspace for syncing inboxes
- `status` - 'pending', 'executing', 'completed', 'failed'
- `provider_type` - 'entra' or 'google'
- `domain_ids` - Array of domain UUIDs being provisioned
- `domain_names` - Array of domain names
- `orders_total`, `orders_completed` - Progress tracking

**Relationships:**
- Belongs to one `client` (required)
- Belongs to one `workspace` (optional but recommended)
- References multiple `domains` (via `domain_ids` array)

---

### 6. `sender_names` Table (NEW in migration 045)
**Primary Key:** `id` (UUID)
**Foreign Key:** `workspace_id` → `workspaces(id)` (NOT NULL, ON DELETE CASCADE)

**Purpose:** First/last name combinations for HyperTide inbox provisioning.

**Key Fields:**
- `workspace_id` - Parent workspace
- `first_name`, `last_name` - Name components
- `full_name` - GENERATED column
- `email` - Optional email
- `is_active` - Active flag

**Relationships:**
- Belongs to one `workspace` (required)

**UNIQUE CONSTRAINT:** `(workspace_id, first_name, last_name)`

---

## Query Patterns for Infrastructure Waterfall

### ✅ CORRECT: Query by workspace_id

```sql
-- Get all domains for a workspace (for waterfall view)
SELECT * FROM v_infrastructure_waterfall
WHERE workspace_id = $1;

-- Get domains across multiple workspaces for a client
SELECT d.* FROM domains d
JOIN clients c ON d.workspace_id = c.workspace_id
WHERE c.id = $1;
```

### ❌ INCORRECT: Query domains by client_id directly

```sql
-- WRONG - domains table has no client_id FK
SELECT * FROM domains WHERE client_id = $1;  -- This column doesn't exist!
```

### ✅ CORRECT: Create HyperTide order

```sql
INSERT INTO inbox_purchase_jobs (
  client_id,           -- Required: which client is ordering
  workspace_id,        -- Required: where to sync inboxes
  domain_ids,          -- Array of domain UUIDs
  provider_type,       -- 'entra' or 'google'
  ...
) VALUES (...);
```

---

## Client Selection Flow for Infrastructure Waterfall

### User Interface Flow:

1. **User selects CLIENT** (dropdown showing all clients)
2. **System looks up CLIENT's workspace_id**
3. **System queries domains by workspace_id**
4. **Waterfall table shows all workspace domains**

### API Pattern:

```typescript
// Frontend
const selectedClient = clients.find(c => c.id === selectedClientId);
const workspaceId = selectedClient.workspace_id;

// API call
const waterfall = await api.infrastructure.getWaterfall(workspaceId);
```

### Backend Query:

```python
@router.get("/waterfall/{workspace_id}")
async def get_waterfall_data(workspace_id: str):
    # Query domains by workspace_id (NOT client_id)
    query = "SELECT * FROM v_infrastructure_waterfall WHERE workspace_id = $1"
    rows = await conn.fetch(query, workspace_id)
    return rows
```

---

## HyperTide Order Creation

### Required Data:

1. **client_id** - Which client is placing the order
2. **workspace_id** - Where to sync resulting inboxes (usually client's workspace)
3. **domain_ids** - Array of domain UUIDs from workspace
4. **order_groups** - Grouped by provider (Entra: 2 domains, Google: 5 domains)
5. **forwardingDomain** - Email forwarding domain
6. **bisonWorkspace** - EmailBison workspace ID for sync destination

### Database Insert:

```sql
INSERT INTO inbox_purchase_jobs (
  client_id,
  workspace_id,
  domain_ids,
  domain_names,
  provider_type,
  orders_total,
  total_inboxes,
  request_data
) VALUES (
  $1,  -- client_id (from client selector)
  $2,  -- workspace_id (from client.workspace_id)
  $3,  -- domain_ids (from selected domains)
  $4,  -- domain_names
  $5,  -- 'entra' or 'google'
  $6,  -- count of orders
  $7,  -- count of inboxes to create
  $8   -- JSONB with full order config
);
```

---

## Summary

### Key Relationships:
- **Workspaces** are top-level containers
- **Clients** belong to workspaces (many clients can share one workspace)
- **Domains** belong to workspaces (NOT to clients directly)
- **Sender accounts** belong to workspaces AND domains
- **Purchase jobs** belong to clients AND workspaces

### Critical for Infrastructure SPA:
1. Client selector → Get `client.workspace_id`
2. Query domains by `workspace_id` (not client_id)
3. Create orders with both `client_id` AND `workspace_id`
4. Sync inboxes to `workspace_id` specified in order

### Why This Matters:
- Multiple clients can share infrastructure in the same workspace
- Domains are workspace resources, not client-exclusive
- Orders track which client requested them (billing)
- Inboxes sync to workspace (operational container)
