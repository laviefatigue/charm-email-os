# SENDER NAMES FLOW - How Names Are Stored and Used

## Storage Location

**Sender names are stored in `clients.onboarding_data` JSONB field, NOT in a separate table.**

### Database Structure

```sql
-- clients table
CREATE TABLE clients (
    id UUID PRIMARY KEY,
    name VARCHAR(255),
    onboarding_data JSONB,  -- ← Sender names stored here
    workspace_id UUID REFERENCES workspaces(id),
    ...
);
```

### onboarding_data Structure

```json
{
  "baseSenderNames": [
    {
      "firstName": "Chris",
      "lastName": "Booth",
      "isFounder": true,
      "createdAt": "2026-01-15T10:30:00Z"
    }
  ],
  "preGeneratedSenderNames": [
    {
      "firstName": "Chris",
      "lastName": "Booth",
      "emailPrefix": "chris.booth",
      "source": "founder"
    },
    {
      "firstName": "Chris",
      "lastName": "Booth",
      "emailPrefix": "chris",
      "source": "founder"
    },
    {
      "firstName": "Chris",
      "lastName": "Booth",
      "emailPrefix": "c.booth",
      "source": "founder"
    }
    // ... up to 52 prefixes total
  ],
  "senderNamePreferences": {
    "usePersonas": false,
    "nameCount": 52,
    "provider": "entra",
    "customNames": []
  },
  "primaryDomain": "hirecharm.com",
  "personas": []
}
```

---

## Example: Charm Client

For a client like "Charm" with founder "Chris Booth":

```json
{
  "baseSenderNames": [
    {
      "firstName": "Chris",
      "lastName": "Booth",
      "isFounder": true
    }
  ],
  "preGeneratedSenderNames": [
    {"emailPrefix": "chris.booth", "firstName": "Chris", "lastName": "Booth", "source": "founder"},
    {"emailPrefix": "chris", "firstName": "Chris", "lastName": "Booth", "source": "founder"},
    {"emailPrefix": "c.booth", "firstName": "Chris", "lastName": "Booth", "source": "founder"},
    {"emailPrefix": "chrisbooth", "firstName": "Chris", "lastName": "Booth", "source": "founder"},
    {"emailPrefix": "chris.b", "firstName": "Chris", "lastName": "Booth", "source": "founder"},
    // ... 47 more prefixes
  ],
  "primaryDomain": "hirecharm.com"
}
```

---

## API Endpoints for Sender Names

### 1. Set Base Sender Name (Simplified)

**Endpoint:** `POST /api/clients/{client_id}/set-sender-name`

**Request:**
```json
{
  "firstName": "Chris",
  "lastName": "Booth",
  "provider": "entra"
}
```

**What it does:**
1. Stores base name in `onboarding_data.baseSenderNames`
2. Auto-generates 52 email prefixes (Entra) or 10 prefixes (Google)
3. Stores prefixes in `onboarding_data.preGeneratedSenderNames`
4. Uses pattern ranking system (chris.booth, chris, c.booth, etc.)

**Response:**
```json
{
  "baseName": {
    "firstName": "Chris",
    "lastName": "Booth",
    "isFounder": true
  },
  "variations": [
    {"emailPrefix": "chris.booth", "pattern": "first.last"},
    {"emailPrefix": "chris", "pattern": "first"},
    // ... all 52 variations
  ],
  "provider": "entra",
  "totalVariations": 52
}
```

---

### 2. Get Sender Names for Provisioning

**Endpoint:** `GET /api/clients/{client_id}/sender-names-for-provisioning`

**What it does:**
1. Fetches `onboarding_data.baseSenderNames` and `onboarding_data.preGeneratedSenderNames`
2. Groups prefixes by base name
3. Returns HyperTide-ready format with constraints

**Response:**
```json
{
  "clientId": "uuid",
  "clientName": "Charm",
  "forwardingDomain": "hirecharm.com",
  "emailbisonWorkspaceId": "12345",
  "workspaceId": "uuid",
  "senderNames": [
    {
      "id": "name-0",
      "firstName": "Chris",
      "lastName": "Booth",
      "isFounder": true,
      "prefixes": ["chris.booth", "chris", "c.booth", ...],
      "totalPrefixCount": 52,
      "entraPrefixCount": 50,
      "googlePrefixCount": 3,
      "entraPrefixes": ["chris.booth", "chris", ...],  // Top 50
      "googlePrefixes": ["chris.booth", "chris", "c.booth"],  // Top 3
      "provider": "entra"
    }
  ],
  "totalNames": 1,
  "hypertideConstraints": {
    "entra": {
      "domainsPerOrder": 2,
      "inboxesPerDomain": 50,
      "inboxesPerOrder": 100
    },
    "google": {
      "domainsPerOrder": 5,
      "inboxesPerDomain": 3,
      "inboxesPerOrder": 15
    }
  }
}
```

---

### 3. Generate Bulk Sender Names

**Endpoint:** `POST /api/clients/{client_id}/generate-sender-names`

**Request:**
```json
{
  "count": 100,
  "usePersonas": true,
  "useClientStrategy": true,
  "customNames": [
    {
      "firstName": "Chris",
      "lastName": "Booth",
      "emailPrefix": "chris.booth"
    }
  ]
}
```

**Priority Order:**
1. **Founder name** (from client strategy - e.g., "Chris Booth" for "Charm")
2. **Custom names** (explicitly provided)
3. **Personas** (from onboarding_data.personas)
4. **Random names** (from 50+ name pool)

**Response:**
```json
{
  "names": [
    {
      "firstName": "Chris",
      "lastName": "Booth",
      "emailPrefix": "chris.booth",
      "source": "founder"
    },
    {
      "firstName": "Sarah",
      "lastName": "Chen",
      "emailPrefix": "sarah.chen",
      "source": "persona"
    }
    // ... up to 100 names
  ],
  "totalCount": 100,
  "fromFounder": 1,
  "fromPersonas": 5,
  "fromCustom": 2,
  "fromGenerated": 92,
  "strategyApplied": "charm"
}
```

---

## HyperTide Order Flow with Sender Names

### Step 1: Fetch Sender Names

```typescript
const response = await api.clients.getSenderNamesForProvisioning(clientId);

// Response includes:
// - senderNames: Array of base names with prefixes
// - forwardingDomain: "hirecharm.com"
// - hypertideConstraints: Entra/Google limits
```

### Step 2: Display in HyperTide Order Modal

```tsx
<HyperTideOrderModal>
  {/* For each order group */}
  {orderGroups.map(group => (
    <OrderGroup>
      <h3>{group.orderType === 'entra' ? 'Entra' : 'Google'} Order</h3>
      <p>Domains: {group.domainIds.length}</p>

      {/* Sender name selector */}
      <Select value={group.senderNameId}>
        {senderNames.map(name => (
          <option value={name.id}>
            {name.firstName} {name.lastName}
            {name.isFounder && ' (Founder)'}
            - {group.orderType === 'entra' ? name.entraPrefixCount : name.googlePrefixCount} prefixes
          </option>
        ))}
      </Select>
    </OrderGroup>
  ))}
</HyperTideOrderModal>
```

### Step 3: Submit HyperTide Order

```typescript
const order: HyperTideOrderRequest = {
  clientId: selectedClient.id,
  workspaceId: selectedClient.workspace_id,
  orderGroups: [
    {
      orderType: 'entra',
      domainIds: ['uuid1', 'uuid2'],  // 2 domains for Entra
      senderNameId: 'name-0'  // References Chris Booth
    }
  ],
  forwardingDomain: 'hirecharm.com',
  bisonWorkspace: 'workspace-12345'
};

await api.infrastructure.createHyperTideOrder(order);
```

### Step 4: Backend Resolves Sender Name

```python
# In infrastructure.py hypertide-order endpoint
async def create_hypertide_order(request: HyperTideOrderRequest):
    # Fetch client's sender names from onboarding_data
    client = await conn.fetchrow(
        "SELECT onboarding_data FROM clients WHERE id = $1",
        request.client_id
    )

    onboarding_data = json.loads(client['onboarding_data'])
    sender_names = onboarding_data.get('preGeneratedSenderNames', [])

    # For each order group, resolve sender_name_id to actual prefixes
    for group in request.order_groups:
        # Get the specific sender name's prefixes
        # senderNameId format: "name-0", "name-1", etc.
        name_index = int(group.sender_name_id.split('-')[1])
        base_names = onboarding_data.get('baseSenderNames', [])

        if name_index < len(base_names):
            base_name = base_names[name_index]
            # Filter prefixes for this base name
            prefixes = [
                s['emailPrefix']
                for s in sender_names
                if s['firstName'] == base_name['firstName']
                and s['lastName'] == base_name['lastName']
            ]

            # Use appropriate count for provider
            if group.order_type == 'entra':
                inbox_prefixes = prefixes[:50]  # Top 50 for Entra
            else:
                inbox_prefixes = prefixes[:3]   # Top 3 for Google

    # Store in request_data for Playwright worker
    request_data = {
        "order_groups": [
            {
                "order_type": g.order_type,
                "domain_ids": g.domain_ids,
                "inbox_prefixes": inbox_prefixes,  # Actual prefixes to create
                "base_name": base_name  # For reference
            }
            for g in request.order_groups
        ],
        "forwarding_domain": request.forwarding_domain,
        "bison_workspace": request.bison_workspace
    }
```

---

## Pattern Ranking System

Prefixes are generated in priority order using `data/name_variations.py`:

### Tier 1 Patterns (Most Professional)
1. `first.last` - chris.booth
2. `first` - chris
3. `f.last` - c.booth
4. `firstlast` - chrisbooth
5. `first.l` - chris.b

### Tier 2 Patterns
6. `flast` - cbooth
7. `first_last` - chris_booth
8. `firstl` - chrisb
9. `last.first` - booth.chris
10. `lastfirst` - boothchris

### Tier 3+ Patterns
- Variations with numbers, underscores, middle initials
- Total of 52 patterns for full coverage

**HyperTide Usage:**
- **Entra**: Uses top 50 patterns (skips bottom 2)
- **Google**: Uses top 3 patterns only

---

## Why NOT a Separate sender_names Table?

### Current Design Benefits:
1. ✅ **Single source of truth**: All client config in one place
2. ✅ **Atomic updates**: JSONB field updates are transactional
3. ✅ **Flexible schema**: Easy to add new fields without migrations
4. ✅ **Versioning**: Can store multiple name sets per client
5. ✅ **Fast queries**: No JOIN needed to get sender names with client

### If We Used a Separate Table:
```sql
-- This would be redundant!
CREATE TABLE sender_names (
    id UUID PRIMARY KEY,
    client_id UUID,  -- ← Already have client.id
    workspace_id UUID,  -- ← Derived from client.workspace_id
    first_name VARCHAR(100),
    last_name VARCHAR(100),
    is_founder BOOLEAN
);
```

**Problems:**
- ❌ Duplicates data already in onboarding_data
- ❌ Requires JOIN for every query
- ❌ Need to maintain sync between table and JSONB
- ❌ More complex updates (UPDATE + INSERT)
- ❌ Harder to version/rollback

---

## Migration Impact

### REMOVE from migration 045:

```sql
-- DELETE THIS - NOT NEEDED
CREATE TABLE IF NOT EXISTS sender_names (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  workspace_id UUID NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
  first_name VARCHAR(100) NOT NULL,
  last_name VARCHAR(100) NOT NULL,
  ...
);
```

### KEEP in infrastructure.py endpoint:

```python
@router.get("/sender-names/{client_id}")
async def get_sender_names(client_id: str):
    """
    Get sender names for client (reads from onboarding_data).
    """
    client = await conn.fetchrow(
        "SELECT onboarding_data, workspace_id FROM clients WHERE id = $1",
        client_id
    )

    onboarding_data = json.loads(client['onboarding_data'])
    base_names = onboarding_data.get('baseSenderNames', [])

    return {
        "clientId": client_id,
        "workspaceId": str(client['workspace_id']),
        "senderNames": base_names
    }
```

---

## Summary

- ✅ Sender names stored in `clients.onboarding_data` JSONB
- ✅ Use existing endpoint `/clients/{client_id}/sender-names-for-provisioning`
- ✅ HyperTide order references sender name by index (`"name-0"`, `"name-1"`)
- ✅ Backend resolves index to actual prefixes from onboarding_data
- ❌ DO NOT create separate `sender_names` table
- ❌ DO NOT duplicate data across tables
