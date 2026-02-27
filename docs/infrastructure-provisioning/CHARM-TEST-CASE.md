# Charm Client - Perfect Test Case for Infrastructure Waterfall

## Why Charm is the Perfect Test

Charm should have domains at **multiple stages** of the provisioning pipeline:

### Expected Domain Distribution:

1. **Stage 1 (Generated)** - AI-generated domains not yet priced
2. **Stage 2 (Priced)** - Domains with cached pricing from registrars
3. **Stage 3 (Purchased)** - Domains bought but DNS not moved yet
4. **Stage 4 (DNS Moved)** - Nameservers changed to DNSimple
5. **Stage 5 (DNS Verified)** - SPF/DKIM/DMARC/MX configured
6. **Stage 6 (Provider Assigned)** - Entra or Google assigned
7. **Stage 7 (HyperTide Ordered)** - Orders submitted to HyperTide
8. **Stage 8 (Provisioned)** - Inboxes created, awaiting sync
9. **Stage 9 (Synced)** - Inboxes synced to EmailBison

### Real-World Scenarios in Charm Data:

#### ✅ **Owned Domains (Already in EmailBison)**
Domains with `approval_status = 'owned'` that have been:
- Purchased
- DNS configured
- Provider assigned
- Synced to EmailBison workspace
- **May have disconnected inboxes** (killed due to health issues)

**Example Query:**
```sql
SELECT
    domain_name,
    approval_status,
    purchased_at,
    infrastructure_type,
    (SELECT COUNT(*) FROM sender_accounts WHERE domain_id = domains.id) as inbox_count
FROM domains d
JOIN clients c ON d.workspace_id = c.workspace_id
WHERE c.name = 'Charm'
  AND d.approval_status = 'owned'
  AND d.is_active = TRUE
ORDER BY purchased_at DESC;
```

**Expected in Waterfall:**
- Stage 9 (fully synced) - Most stable domains
- Some may show in Stage 8 if inboxes were disconnected
- Displays "Deployed" badge
- Shows inbox sync count (e.g., "75/100" for Entra)

#### 🟡 **Purchased But Not Set Up**
Domains that were purchased but never configured in HyperTide:
- `purchased_at IS NOT NULL`
- `infrastructure_type IS NULL` (no provider assigned)
- No inbox_purchase_jobs record

**Example Query:**
```sql
SELECT
    domain_name,
    purchased_at,
    nameservers_updated_at,
    nameserver_status,
    infrastructure_type
FROM domains d
JOIN clients c ON d.workspace_id = c.workspace_id
WHERE c.name = 'Charm'
  AND d.purchased_at IS NOT NULL
  AND d.infrastructure_type IS NULL
  AND d.is_active = TRUE
ORDER BY purchased_at DESC;
```

**Expected in Waterfall:**
- Stage 3 (Purchased) - If DNS not moved
- Stage 4 (DNS Moved) - If nameservers updated but not verified
- Stage 5 (DNS Verified) - If DNS complete but no provider assigned
- **These are "ready for HyperTide"** domains

#### 🔴 **Disconnected Inboxes**
Domains where inboxes were killed/disconnected:
- Had sender_accounts records
- Accounts marked `is_active = FALSE`
- Domain still exists and functional

**Example Query:**
```sql
SELECT
    d.domain_name,
    COUNT(sa.id) FILTER (WHERE sa.is_active = TRUE) as active_inboxes,
    COUNT(sa.id) FILTER (WHERE sa.is_active = FALSE) as inactive_inboxes,
    MAX(sa.killed_at) as last_kill_date
FROM domains d
JOIN clients c ON d.workspace_id = c.workspace_id
LEFT JOIN sender_accounts sa ON sa.domain_id = d.id
WHERE c.name = 'Charm'
  AND d.is_active = TRUE
GROUP BY d.id, d.domain_name
HAVING COUNT(sa.id) FILTER (WHERE sa.is_active = FALSE) > 0
ORDER BY last_kill_date DESC;
```

**Expected in Waterfall:**
- Stage 9 but with reduced inbox count
- Shows "50/100" instead of "100/100" if half were killed
- May show as Stage 8 if all inboxes disconnected

---

## What You'll See When Loading Charm

### Client Selector:
```
┌─────────────────────────┐
│ Client: [Charm       ▼] │  ← Select this
└─────────────────────────┘
```

### Filter Bar (Initial State):
```
View: [All Domains ▼]  Stage: [All Stages ▼]  Provider: [All Providers ▼]  [🔄 Refresh]
```

### Expected Waterfall Table:

```
┌──┬────────────┬─────────┬──────────┬─────────┬──────────┬─────────┬──────────┬────────────┬─────────┐
│☑ │ Generated  │ Priced  │Purchased │DNS Moved│DNS Verify│Provider │HyperTide │Provisioned │ Synced  │
├──┼────────────┼─────────┼──────────┼─────────┼──────────┼─────────┼──────────┼────────────┼─────────┤
│☐ │startup.com │ $10.88  │Purchased │DNSimple │ ✓ SPF    │🟦 Entra │Order #123│Provisioning│ 85/100  │
│  │Owned ✓     │Dynadot  │Feb 24    │✓ Set    │ ✓ DKIM   │50 inbox │Active    │    ███     │  85%    │
│  │████ 92%    │✓ Valid  │          │24h ago  │ ✓ DMARC  │         │          │            │[View]   │
│  │            │         │          │         │ ✓ MX     │         │          │            │Deployed │
├──┼────────────┼─────────┼──────────┼─────────┼──────────┼─────────┼──────────┼────────────┼─────────┤
│☐ │scale.io    │ $11.25  │Purchased │DNSimple │ ✓ SPF    │🔴Google │Order #124│Completed   │ 15/15   │
│  │Owned ✓     │Porkbun  │Feb 20    │✓ Set    │ ✓ DKIM   │3 inbox  │Completed │     ✓      │ 100%    │
│  │███ 88%     │✓ Valid  │          │48h ago  │ ✓ DMARC  │         │          │            │[View]   │
│  │            │         │          │         │ ✓ MX     │         │          │            │Deployed │
├──┼────────────┼─────────┼──────────┼─────────┼──────────┼─────────┼──────────┼────────────┼─────────┤
│☐ │growth.app  │ $10.50  │Purchased │DNSimple │ ✓ SPF    │🟦 Entra │   ---    │    ---     │   ---   │
│  │            │Dynadot  │Feb 15    │✓ Set    │ ✓ DKIM   │50 inbox │          │            │         │
│  │███ 85%     │✓ Valid  │          │72h ago  │ ✓ DMARC  │         │          │            │         │
│  │            │         │          │         │ ✓ MX     │         │          │            │         │
│  │            │         │          │         │ ✓ Verified│        │          │            │         │
├──┼────────────┼─────────┼──────────┼─────────┼──────────┼─────────┼──────────┼────────────┼─────────┤
│☐ │summit.co   │ $12.99  │Purchased │⏱Pending │⏱ Waiting │   ---   │   ---    │    ---     │   ---   │
│  │            │Porkbun  │Feb 10    │12h left │for NS    │         │          │            │         │
│  │██ 78%      │✓ Valid  │          │         │migration │         │          │            │         │
├──┼────────────┼─────────┼──────────┼─────────┼──────────┼─────────┼──────────┼────────────┼─────────┤
│☐ │venture.io  │ $11.08  │   ---    │   ---   │   ---    │   ---   │   ---    │    ---     │   ---   │
│  │            │Dynadot  │          │         │          │         │          │            │         │
│  │███ 91%     │✓ Valid  │          │         │          │         │          │            │         │
│  │            │         │          │         │          │         │          │            │         │
└──┴────────────┴─────────┴──────────┴─────────┴──────────┴─────────┴──────────┴────────────┴─────────┘
  [Check Prices] [Purchase] [Set DNS] [Verify DNS] [Assign Provider] [Order HyperTide] [Check Status] [View]
       (0)          (1)        (1)       (1)           (2)                (0)              (0)          (2)
```

---

## Filtering Examples

### Filter: View = "Owned Only"
**Shows:** Only domains with `approval_status = 'owned'`
**Expected:**
- Domains already synced to EmailBison
- Most will be in Stage 9
- Some may be in Stage 7-8 if recently ordered

### Filter: Stage = 3 (Purchased)
**Shows:** Domains purchased but DNS not yet moved
**Expected:**
- Domains ready for DNS migration
- Bulk action available: "Set DNS"
- These need nameservers changed to DNSimple

### Filter: Stage = 6 (Provider Assigned)
**Shows:** Domains ready for HyperTide order
**Expected:**
- DNS fully configured
- Provider assigned (Entra or Google)
- Ready to bulk order in HyperTide
- **These are your "ready to provision" domains**

### Filter: Provider = "Entra"
**Shows:** All domains assigned to Entra infrastructure
**Expected:**
- Mix of stages (6, 7, 8, 9)
- Can see which Entra domains need orders
- Can group for 2-domain HyperTide orders

---

## Interactive Testing Scenarios

### Scenario 1: Find Domains Ready for HyperTide
1. Load Charm client
2. Set filter: **Stage = 6** (Provider Assigned)
3. **Expected:** List of domains with DNS verified and provider assigned
4. Select all domains in Stage 6
5. Click "Order HyperTide" bulk action
6. **Result:** Opens modal to configure orders

### Scenario 2: Check Disconnected Inboxes
1. Load Charm client
2. Set filter: **Stage = 9** (Synced)
3. Look for domains with reduced inbox counts
4. **Expected:** Domains showing "45/100" instead of "100/100"
5. These indicate killed inboxes that need replacement

### Scenario 3: Track Purchase to Sync
1. Load Charm client
2. Set filter: **Stage = 3** (Purchased)
3. Select domain(s)
4. Click "Set DNS" → Moves to Stage 4
5. Wait 24 hours → Moves to Stage 5 (auto-verify)
6. Click "Verify DNS" → Confirms Stage 5
7. Click "Assign Provider" → Moves to Stage 6
8. Click "Order HyperTide" → Moves to Stage 7
9. Wait 2 hours → Moves to Stage 8
10. Automatic sync → Moves to Stage 9

---

## Database Queries for Verification

### Get Charm's Current State

```sql
-- Overall distribution across stages
SELECT
    current_stage,
    COUNT(*) as domain_count,
    STRING_AGG(domain_name, ', ' ORDER BY domain_name) as domains
FROM v_infrastructure_waterfall
WHERE workspace_id = (
    SELECT workspace_id FROM clients WHERE name = 'Charm'
)
GROUP BY current_stage
ORDER BY current_stage;
```

### Find "Ready for HyperTide" Domains

```sql
-- Stage 6: DNS verified, provider assigned, ready to order
SELECT
    domain_name,
    assigned_provider,
    dns_records_configured,
    nameserver_status
FROM v_infrastructure_waterfall
WHERE workspace_id = (SELECT workspace_id FROM clients WHERE name = 'Charm')
  AND current_stage = 6
ORDER BY domain_name;
```

### Check Synced Inbox Counts

```sql
-- Stage 9: Show actual vs expected inbox counts
SELECT
    domain_name,
    assigned_provider,
    synced_inbox_count,
    CASE
        WHEN assigned_provider = 'entra' THEN 100
        WHEN assigned_provider = 'google' THEN 15
        ELSE 0
    END as expected_count,
    deployed_to_production
FROM v_infrastructure_waterfall
WHERE workspace_id = (SELECT workspace_id FROM clients WHERE name = 'Charm')
  AND current_stage = 9
ORDER BY synced_inbox_count DESC;
```

---

## Expected Behavior When Loading Charm

### On Page Load:
1. **Client selector** populates with all clients
2. Select "Charm" → Triggers `api.infrastructure.getWaterfallByClient(charm-id)`
3. Backend looks up Charm's `workspace_id`
4. Backend queries `v_infrastructure_waterfall WHERE workspace_id = charm-workspace-id`
5. **Table renders** with all Charm domains distributed across 9 stages

### Visual Indicators:
- ✅ **"Owned" badge** on domains in EmailBison
- 🟦 **Blue Entra badges** on Microsoft infrastructure
- 🔴 **Red Google badges** on Google Workspace infrastructure
- 📊 **Progress bars** showing legitimacy scores, sync percentages
- ⏱️ **Time indicators** showing DNS propagation, order execution
- ✓ **Checkmarks** for completed DNS records

### Selection Features:
- ☑️ Click checkbox to select individual domain
- ☑️ Click column header checkbox to select all in stage
- Numbers update on bulk action buttons: `[Order HyperTide (3)]`

---

## Success Criteria

After loading Charm, you should see:

✅ **Multiple domains across different stages** (not all in one stage)
✅ **Some domains in Stage 9 with 100/100 or 15/15 sync counts**
✅ **Some domains in Stage 6 ready for HyperTide**
✅ **Some domains in Stage 3-5 (purchased but not provisioned)**
✅ **Owned badges on domains already in EmailBison**
✅ **Mix of Entra and Google provider badges**
✅ **Realistic pricing** ($10-15 range)
✅ **Recent dates** on purchased domains

If you see domains distributed across stages 1-9, **the waterfall is working perfectly!**

---

## Next Steps After Loading Charm

Once you see the waterfall populated with Charm's data:

1. **Test Filters:**
   - Switch View to "Owned Only" → Should show fewer domains
   - Filter by Stage 6 → Shows "ready to provision" domains
   - Filter by Provider "Entra" → Shows only Microsoft infrastructure

2. **Test Selection:**
   - Click individual domain checkboxes
   - Click "select all" in a stage column
   - Verify bulk action counts update

3. **Identify Actions:**
   - **Stage 3 domains** → Ready for DNS migration
   - **Stage 6 domains** → Ready for HyperTide orders
   - **Stage 9 with low counts** → Need inbox replenishment

4. **Test Bulk Operations** (when modals implemented):
   - Select multiple Stage 6 domains
   - Group into HyperTide orders (2 Entra or 5 Google per order)
   - Submit orders with sender names from Charm's onboarding_data

---

## Charm-Specific Configuration

### Sender Names from Onboarding Data:
Charm should have in `clients.onboarding_data`:
```json
{
  "baseSenderNames": [
    {
      "firstName": "Chris",
      "lastName": "Booth",
      "isFounder": true
    }
  ],
  "primaryDomain": "hirecharm.com"
}
```

This will be used when creating HyperTide orders for Charm's domains.

---

## Summary

**Charm is perfect because:**
- ✅ Real production data
- ✅ Multiple domain states (purchased, DNS configured, synced)
- ✅ Mix of providers (Entra + Google)
- ✅ Owned domains with inbox history
- ✅ Likely has domains at every stage 1-9

When you load Charm in the waterfall, you'll immediately see the **power of the 9-stage pipeline** with real data distributed across the workflow!
