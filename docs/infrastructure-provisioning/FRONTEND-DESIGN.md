# Infrastructure Provisioning SPA - Frontend Design Specification

**Date:** 2026-02-25
**Purpose:** Complete visual design, UX patterns, and component specifications for the waterfall SPA

---

## 🎨 Design System

### Color Palette

**Stage Status Colors:**
```css
/* Stage completion states */
--stage-empty: #F3F4F6;        /* gray-100 - Not reached */
--stage-active: #DBEAFE;        /* blue-100 - Current stage */
--stage-complete: #D1FAE5;      /* green-100 - Completed */
--stage-error: #FEE2E2;         /* red-100 - Error/failed */
--stage-warning: #FEF3C7;       /* yellow-100 - Needs attention */

/* Provider colors */
--provider-entra: #3B82F6;      /* blue-500 - Microsoft Entra */
--provider-google: #EF4444;     /* red-500 - Google Workspace */

/* Ownership badges */
--owned-bg: #DCFCE7;            /* green-100 */
--owned-text: #15803D;          /* green-700 */
--deployed-bg: #DBEAFE;         /* blue-100 */
--deployed-text: #1E40AF;       /* blue-700 */
```

**Action Colors:**
```css
/* Bulk action buttons */
--action-primary: #4F46E5;      /* indigo-600 */
--action-primary-hover: #4338CA; /* indigo-700 */
--action-secondary: #6B7280;    /* gray-500 */
--action-success: #10B981;      /* green-500 */
--action-danger: #EF4444;       /* red-500 */
```

### Typography

```css
/* Headers */
--font-header: 'Inter', sans-serif;
--text-xl: 20px / 28px;  /* Column headers */
--text-lg: 18px / 28px;  /* Section headers */

/* Body */
--text-base: 14px / 20px;  /* Domain names, prices */
--text-sm: 12px / 16px;    /* Badges, timestamps */
--text-xs: 10px / 14px;    /* Helper text */
```

### Spacing

```css
/* Cell padding */
--cell-padding: 12px;
--cell-min-width: 200px;
--cell-max-width: 280px;

/* Table layout */
--header-height: 80px;
--row-height: auto; /* Min 60px */
--table-gap: 1px;   /* Border between cells */
```

---

## 🖼️ Page Layout

### Overall Structure

```
┌─────────────────────────────────────────────────────────────────────────────┐
│  Header                                                                      │
│  ┌──────────────────┬──────────────────────────────────────────┬──────────┐ │
│  │ Infrastructure   │ [All] [Owned] [New]                      │ [Client] │ │
│  │ Provisioning     │                                          │ Selector │ │
│  └──────────────────┴──────────────────────────────────────────┴──────────┘ │
├─────────────────────────────────────────────────────────────────────────────┤
│  Waterfall Table (horizontal scroll)                                        │
│  ┌───────┬────────┬────────┬─────────┬──────────┬──────────┬──────┬───────┐│
│  │ [ ] ▼ │ Gen    │ Priced │ Bought  │ DNS Set  │ DNS ✓    │ Prov │ Order ││
│  │       │ [Bulk] │ [Bulk] │ [Bulk]  │ [Bulk]   │ [Bulk]   │[Bulk]│[Bulk] ││
│  ├───────┼────────┼────────┼─────────┼──────────┼──────────┼──────┼───────┤│
│  │ [ ]   │ dom.io │ $8.99  │ ✓ 2h    │ ✓ NS set │ ✓ All OK │ 🔵   │ #123  ││
│  │       │ ✓ Own  │ Porkbun│ Porkbun │ 24h ago  │ SPF ✓    │ Entra│ 3/5   ││
│  │       │ 87%    │        │         │          │ DKIM ✓   │      │       ││
│  ├───────┼────────┼────────┼─────────┼──────────┼──────────┼──────┼───────┤│
│  │ [ ]   │ test.io│ $12.49 │         │          │          │      │       ││
│  │       │ 92%    │ Dynadot│         │          │          │      │       ││
│  └───────┴────────┴────────┴─────────┴──────────┴──────────┴──────┴───────┘│
│                                                                              │
│  ┌────────────────────────────────────────────────────────────────────────┐ │
│  │ Footer: X domains selected • Total cost: $XXX.XX • Last sync: 2m ago  │ │
│  └────────────────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Responsive Behavior

**Desktop (>1440px):**
- Show all 9 columns with horizontal scroll
- Sticky first column (checkbox + domain name)
- Sticky header with bulk actions

**Tablet (768px - 1440px):**
- Show 5-6 columns at a time
- Horizontal scroll required
- Collapsible filters

**Mobile (<768px):**
- Card-based view (not table)
- Stage progress bar at top of each card
- Vertical stack of cards

---

## 🧩 Component Specifications

### 1. Header Bar

**Location:** Top of page, sticky on scroll

**Layout:**
```tsx
<div className="flex justify-between items-center p-6 bg-white border-b sticky top-0 z-50">
  {/* Left: Title */}
  <div>
    <h1 className="text-2xl font-bold text-gray-900">Infrastructure Provisioning</h1>
    <p className="text-sm text-gray-500">Bulk domain & inbox setup workflow</p>
  </div>

  {/* Center: View filters */}
  <div className="flex gap-2">
    <Button variant={view === 'all' ? 'default' : 'outline'} onClick={() => setView('all')}>
      All Domains
    </Button>
    <Button variant={view === 'owned' ? 'default' : 'outline'} onClick={() => setView('owned')}>
      Owned ({ownedCount})
    </Button>
    <Button variant={view === 'new' ? 'default' : 'outline'} onClick={() => setView('new')}>
      New ({newCount})
    </Button>
  </div>

  {/* Right: Client selector */}
  <ClientSelector value={clientId} onChange={setClientId} />
</div>
```

**Visual State:**
- Active view button: Indigo background, white text
- Inactive view button: White background, gray border
- Client selector: Dropdown with search

---

### 2. Waterfall Table Container

**Layout:**
```tsx
<div className="overflow-x-auto">
  <table className="min-w-full border-collapse bg-white">
    <WaterfallHeader />
    <tbody>
      {domains.map(domain => (
        <WaterfallRow key={domain.id} domain={domain} />
      ))}
    </tbody>
  </table>
</div>
```

**Features:**
- Horizontal scroll with shadow indicators on edges
- Sticky first column (checkbox + domain info)
- Sticky header row
- Zebra striping on rows (alternate bg-gray-50)
- Hover state on rows (bg-blue-50)

---

### 3. Column Header (with Bulk Action)

**Layout:**
```tsx
<th className="border border-gray-200 bg-gray-50 p-3 min-w-[200px] sticky top-0">
  <div className="flex flex-col gap-2">
    {/* Stage label */}
    <div className="flex items-center gap-2">
      <span className="font-semibold text-sm text-gray-900">{stage.label}</span>
      <Badge variant="outline" className="text-xs">{stageCount}</Badge>
    </div>

    {/* Stage description */}
    <p className="text-xs text-gray-500 leading-tight">{stage.description}</p>

    {/* Bulk action button */}
    {bulkAction && (
      <Button
        size="sm"
        onClick={handleBulkAction}
        disabled={selectedCount === 0}
        className="w-full"
      >
        {bulkAction.icon}
        {bulkAction.label} ({selectedCount})
      </Button>
    )}
  </div>
</th>
```

**Column Headers (9 stages):**

1. **Generated**
   - Label: "Generated"
   - Description: "AI-generated domains ready for pricing"
   - Bulk Action: None (domains auto-added here)
   - Badge: Domain count

2. **Priced**
   - Label: "Priced"
   - Description: "Check prices from Porkbun & Dynadot"
   - Bulk Action: "Check Prices" button (💰 icon)
   - Badge: Priced count

3. **Purchased**
   - Label: "Purchased"
   - Description: "Buy domains from selected registrar"
   - Bulk Action: "Purchase All" button (🛒 icon)
   - Badge: Purchased count

4. **DNS Moved**
   - Label: "DNS Moved"
   - Description: "Nameservers changed to DNSimple"
   - Bulk Action: "Set Nameservers" button (🔧 icon)
   - Badge: NS updated count

5. **DNS Verified**
   - Label: "DNS Verified"
   - Description: "SPF, DKIM, DMARC, MX configured"
   - Bulk Action: "Verify DNS" button (✓ icon)
   - Badge: Verified count

6. **Provider Assigned**
   - Label: "Provider Assigned"
   - Description: "Entra or Google infrastructure type"
   - Bulk Action: "Assign Provider" dropdown (🔵/🔴 icon)
   - Badge: Assigned count

7. **HyperTide Ordered**
   - Label: "HyperTide Ordered"
   - Description: "Inbox provisioning order submitted"
   - Bulk Action: "Create Order" button (📦 icon)
   - Badge: Ordered count

8. **Provisioned**
   - Label: "Provisioned"
   - Description: "Inboxes created by HyperTide"
   - Bulk Action: None (waiting on vendor)
   - Badge: Provisioned count

9. **Synced**
   - Label: "Synced"
   - Description: "Inboxes synced to EmailBison"
   - Bulk Action: None (auto-synced)
   - Badge: Synced count

---

### 4. Stage Cells (9 Variations)

#### Cell 1: Generated Cell

**Visual Design:**
```
┌──────────────────────────┐
│ example.io               │
│ ┌────┐ ┌──────┐         │
│ │Owned│ │Deployed│        │
│ └────┘ └──────┘         │
│ Score: 87%               │
│ 2 hours ago              │
└──────────────────────────┘
```

**Component:**
```tsx
<div className="space-y-2">
  {/* Domain name */}
  <div className="font-medium text-sm text-gray-900">{domain.name}</div>

  {/* Ownership badges */}
  <div className="flex gap-1 flex-wrap">
    {domain.owned && (
      <Badge className="text-xs bg-green-100 text-green-700 border-green-300">
        Owned ✓
      </Badge>
    )}
    {domain.deployed && (
      <Badge className="text-xs bg-blue-100 text-blue-700 border-blue-300">
        Deployed ✓
      </Badge>
    )}
  </div>

  {/* Legitimacy score */}
  {domain.legitimacyScore && (
    <div className="flex items-center gap-1">
      <span className="text-xs text-gray-500">Score:</span>
      <span className={`text-xs font-medium ${
        domain.legitimacyScore >= 0.8 ? 'text-green-600' :
        domain.legitimacyScore >= 0.6 ? 'text-yellow-600' :
        'text-red-600'
      }`}>
        {(domain.legitimacyScore * 100).toFixed(0)}%
      </span>
    </div>
  )}

  {/* Timestamp */}
  <div className="text-xs text-gray-400">
    {formatDistanceToNow(domain.createdAt, { addSuffix: true })}
  </div>
</div>
```

**Empty State:**
```tsx
<div className="text-xs text-gray-400 italic">Not generated</div>
```

---

#### Cell 2: Priced Cell

**Visual Design:**
```
┌──────────────────────────┐
│ 💰 $8.99                 │
│ ┌────────┐              │
│ │ Porkbun │              │
│ └────────┘              │
│ ┌──────┐                │
│ │ Valid │                │
│ └──────┘                │
│ Checked 2h ago           │
└──────────────────────────┘
```

**Component:**
```tsx
<div className="space-y-2">
  {/* Price display */}
  {domain.cachedPrice && (
    <div className="flex items-center gap-1">
      <DollarSign className="w-4 h-4 text-green-600" />
      <span className="font-semibold text-base text-gray-900">
        ${domain.cachedPrice.toFixed(2)}
      </span>
    </div>
  )}

  {/* Provider badge */}
  {domain.selectedProvider && (
    <Badge variant="outline" className="text-xs">
      {domain.selectedProvider === 'porkbun' ? 'Porkbun' : 'Dynadot'}
    </Badge>
  )}

  {/* Price status */}
  <Badge className={`text-xs ${
    domain.priceStatus === 'valid' ? 'bg-green-100 text-green-800' :
    domain.priceStatus === 'stale' ? 'bg-yellow-100 text-yellow-800' :
    'bg-red-100 text-red-800'
  }`}>
    {domain.priceStatus === 'valid' ? 'Valid' :
     domain.priceStatus === 'stale' ? 'Stale' :
     'Unavailable'}
  </Badge>

  {/* Warning for stale prices */}
  {domain.priceStatus === 'stale' && (
    <div className="text-xs text-yellow-600 flex items-center gap-1">
      <AlertCircle className="w-3 h-3" />
      Recheck needed
    </div>
  )}

  {/* Timestamp */}
  {domain.priceCheckedAt && (
    <div className="text-xs text-gray-400">
      Checked {formatDistanceToNow(domain.priceCheckedAt, { addSuffix: true })}
    </div>
  )}
</div>
```

**Empty State:**
```tsx
<div className="space-y-2">
  <div className="text-xs text-gray-400">Not priced</div>
  <Button size="xs" variant="ghost" onClick={handleCheckPrice}>
    Check Price
  </Button>
</div>
```

---

#### Cell 3: Purchased Cell

**Visual Design:**
```
┌──────────────────────────┐
│ ✓ Purchased              │
│ ┌────────┐              │
│ │ Porkbun │              │
│ └────────┘              │
│ 2 hours ago              │
└──────────────────────────┘
```

**Component:**
```tsx
<div className="space-y-2">
  {/* Purchased indicator */}
  <div className="flex items-center gap-1 text-green-600">
    <CheckCircle className="w-4 h-4" />
    <span className="text-sm font-medium">Purchased</span>
  </div>

  {/* Provider */}
  {domain.selectedProvider && (
    <Badge variant="outline" className="text-xs">
      {domain.selectedProvider === 'porkbun' ? 'Porkbun' : 'Dynadot'}
    </Badge>
  )}

  {/* Purchase job status */}
  {domain.purchaseJobId && domain.purchaseJobStatus !== 'completed' && (
    <div className="flex items-center gap-1">
      <Loader2 className="w-3 h-3 animate-spin text-blue-500" />
      <span className="text-xs text-blue-600">Processing...</span>
    </div>
  )}

  {/* Timestamp */}
  {domain.purchasedAt && (
    <div className="text-xs text-gray-400">
      {formatDistanceToNow(domain.purchasedAt, { addSuffix: true })}
    </div>
  )}
</div>
```

**Empty State:**
```tsx
<div className="space-y-2">
  <div className="text-xs text-gray-400">Not purchased</div>
  {domain.cachedPrice && (
    <Button size="xs" variant="ghost" onClick={handlePurchase}>
      Purchase ${domain.cachedPrice.toFixed(2)}
    </Button>
  )}
</div>
```

---

#### Cell 4: DNS Moved Cell

**Visual Design:**
```
┌──────────────────────────┐
│ ✓ Nameservers Set        │
│ ns1.dnsimple.com         │
│ ns2.dnsimple-edge.net    │
│ ┌───────────┐           │
│ │ Propagating│           │
│ └───────────┘           │
│ Updated 24h ago          │
└──────────────────────────┘
```

**Component:**
```tsx
<div className="space-y-2">
  {/* DNS status */}
  <div className="flex items-center gap-1 text-blue-600">
    <Server className="w-4 h-4" />
    <span className="text-sm font-medium">NS Updated</span>
  </div>

  {/* Current nameservers (truncated) */}
  {domain.currentNameservers && (
    <div className="text-xs text-gray-600 space-y-0.5">
      {domain.currentNameservers.slice(0, 2).map((ns, i) => (
        <div key={i} className="truncate">{ns}</div>
      ))}
      {domain.currentNameservers.length > 2 && (
        <div className="text-gray-400">+{domain.currentNameservers.length - 2} more</div>
      )}
    </div>
  )}

  {/* Migration status badge */}
  <Badge className={`text-xs ${
    domain.dnsMigrationStatus === 'propagated' ? 'bg-green-100 text-green-800' :
    domain.dnsMigrationStatus === 'propagating' ? 'bg-blue-100 text-blue-800' :
    'bg-gray-100 text-gray-800'
  }`}>
    {domain.dnsMigrationStatus === 'propagated' ? '✓ Propagated' :
     domain.dnsMigrationStatus === 'propagating' ? '⏳ Propagating' :
     'Not Set'}
  </Badge>

  {/* Timestamp */}
  {domain.nameserversUpdatedAt && (
    <div className="text-xs text-gray-400">
      {formatDistanceToNow(domain.nameserversUpdatedAt, { addSuffix: true })}
    </div>
  )}
</div>
```

**Empty State:**
```tsx
<div className="space-y-2">
  <div className="text-xs text-gray-400">NS not set</div>
  <Button size="xs" variant="ghost" onClick={handleSetNameservers}>
    Set Nameservers
  </Button>
</div>
```

---

#### Cell 5: DNS Verified Cell

**Visual Design:**
```
┌──────────────────────────┐
│ ✓ All Records Configured │
│ ✓ SPF configured         │
│ ✓ DKIM configured        │
│ ✓ DMARC configured       │
│ ✓ MX configured          │
│ Verified 1h ago          │
└──────────────────────────┘
```

**Component:**
```tsx
<div className="space-y-2">
  {/* Overall status */}
  {domain.dnsRecordsConfigured ? (
    <div className="flex items-center gap-1 text-green-600">
      <CheckCircle className="w-4 h-4" />
      <span className="text-sm font-medium">All Set</span>
    </div>
  ) : (
    <div className="flex items-center gap-1 text-yellow-600">
      <AlertCircle className="w-4 h-4" />
      <span className="text-sm font-medium">Incomplete</span>
    </div>
  )}

  {/* DNS record checklist */}
  <div className="space-y-1">
    <DNSRecordItem label="SPF" configured={domain.spfConfigured} />
    <DNSRecordItem label="DKIM" configured={domain.dkimConfigured} />
    <DNSRecordItem label="DMARC" configured={domain.dmarcConfigured} />
    <DNSRecordItem label="MX" configured={domain.mxConfigured} />
  </div>

  {/* Verify button if not all configured */}
  {!domain.dnsRecordsConfigured && (
    <Button size="xs" variant="ghost" onClick={handleVerifyDNS}>
      Verify Records
    </Button>
  )}

  {/* Timestamp */}
  {domain.nameserverVerifiedAt && (
    <div className="text-xs text-gray-400">
      Verified {formatDistanceToNow(domain.nameserverVerifiedAt, { addSuffix: true })}
    </div>
  )}
</div>

// Helper component
function DNSRecordItem({ label, configured }: { label: string; configured: boolean }) {
  return (
    <div className="flex items-center gap-1 text-xs">
      {configured ? (
        <CheckCircle className="w-3 h-3 text-green-500" />
      ) : (
        <XCircle className="w-3 h-3 text-gray-300" />
      )}
      <span className={configured ? 'text-gray-700' : 'text-gray-400'}>{label}</span>
    </div>
  );
}
```

**Empty State:**
```tsx
<div className="text-xs text-gray-400">Not verified</div>
```

---

#### Cell 6: Provider Assigned Cell

**Visual Design:**
```
┌──────────────────────────┐
│ 🔵 Microsoft Entra       │
│ ┌─────────────┐         │
│ │ Assigned 2h ago│        │
│ └─────────────┘         │
└──────────────────────────┘
```

**Component:**
```tsx
<div className="space-y-2">
  {/* Provider badge */}
  {domain.assignedProvider ? (
    <div className="flex items-center gap-2">
      <div className={`w-3 h-3 rounded-full ${
        domain.assignedProvider === 'entra' ? 'bg-blue-500' : 'bg-red-500'
      }`} />
      <span className="text-sm font-medium text-gray-900">
        {domain.assignedProvider === 'entra' ? 'Microsoft Entra' : 'Google Workspace'}
      </span>
    </div>
  ) : (
    <div className="text-xs text-gray-400">Not assigned</div>
  )}

  {/* Provider info */}
  {domain.assignedProvider && (
    <div className="text-xs text-gray-600">
      {domain.assignedProvider === 'entra'
        ? '2 domains per order'
        : '5 domains per order'}
    </div>
  )}

  {/* Assign button if not set */}
  {!domain.assignedProvider && (
    <div className="flex gap-1">
      <Button
        size="xs"
        variant="outline"
        onClick={() => handleAssignProvider('entra')}
        className="flex-1"
      >
        🔵 Entra
      </Button>
      <Button
        size="xs"
        variant="outline"
        onClick={() => handleAssignProvider('google')}
        className="flex-1"
      >
        🔴 Google
      </Button>
    </div>
  )}
</div>
```

---

#### Cell 7: HyperTide Ordered Cell

**Visual Design:**
```
┌──────────────────────────┐
│ 📦 Order #12345          │
│ ┌──────────────┐        │
│ │ ⏳ Step 3/5    │        │
│ │ [████████░░░]  │        │
│ └──────────────┘        │
│ Ordered 1h ago           │
└──────────────────────────┘
```

**Component:**
```tsx
<div className="space-y-2">
  {/* Order status */}
  {domain.hyperTideOrderJobId ? (
    <>
      <div className="flex items-center gap-1 text-blue-600">
        <Package className="w-4 h-4" />
        <span className="text-sm font-medium">Order #{domain.hyperTideOrderJobId.slice(0, 8)}</span>
      </div>

      {/* Progress indicator */}
      {domain.hyperTideOrderStatus !== 'completed' && (
        <div className="space-y-1">
          <div className="flex items-center gap-1">
            <Loader2 className="w-3 h-3 animate-spin text-blue-500" />
            <span className="text-xs text-blue-600">{domain.hyperTideCurrentStep}</span>
          </div>
          <Progress value={getProgressPercent(domain.hyperTideCurrentStep)} className="h-1" />
        </div>
      )}

      {/* Completed state */}
      {domain.hyperTideOrderStatus === 'completed' && (
        <div className="flex items-center gap-1 text-green-600">
          <CheckCircle className="w-3 h-3" />
          <span className="text-xs">Order Complete</span>
        </div>
      )}

      {/* Timestamp */}
      <div className="text-xs text-gray-400">
        Ordered {formatDistanceToNow(domain.hyperTideOrderedAt, { addSuffix: true })}
      </div>
    </>
  ) : (
    <div className="text-xs text-gray-400">Not ordered</div>
  )}
</div>
```

---

#### Cell 8: Provisioned Cell

**Visual Design:**
```
┌──────────────────────────┐
│ ✓ Provisioned            │
│ ┌────────────┐          │
│ │ Awaiting sync│          │
│ └────────────┘          │
│ Completed 30m ago        │
└──────────────────────────┘
```

**Component:**
```tsx
<div className="space-y-2">
  {/* Provisioning status */}
  {domain.provisioningStatus === 'synced' ? (
    <div className="flex items-center gap-1 text-green-600">
      <CheckCircle className="w-4 h-4" />
      <span className="text-sm font-medium">Synced</span>
    </div>
  ) : domain.provisioningStatus === 'awaiting_sync' ? (
    <div className="flex items-center gap-1 text-blue-600">
      <Clock className="w-4 h-4" />
      <span className="text-sm font-medium">Awaiting Sync</span>
    </div>
  ) : domain.provisioningStatus === 'provisioning' ? (
    <div className="flex items-center gap-1 text-yellow-600">
      <Loader2 className="w-4 h-4 animate-spin" />
      <span className="text-sm font-medium">Provisioning</span>
    </div>
  ) : (
    <div className="text-xs text-gray-400">Not started</div>
  )}

  {/* Status badge */}
  <Badge variant="outline" className="text-xs">
    {domain.provisioningStatus.replace('_', ' ')}
  </Badge>

  {/* Note about vendor control */}
  {domain.provisioningStatus === 'provisioning' && (
    <div className="text-xs text-gray-500 italic">
      HyperTide processing...
    </div>
  )}
</div>
```

---

#### Cell 9: Synced Cell

**Visual Design:**
```
┌──────────────────────────┐
│ ✓ 100/100 Inboxes        │
│ ┌──────────────┐        │
│ │ [████████████]│        │
│ └──────────────┘        │
│ Last sync: 5m ago        │
└──────────────────────────┘
```

**Component:**
```tsx
<div className="space-y-2">
  {/* Inbox count */}
  {domain.syncedInboxCount > 0 ? (
    <>
      <div className="flex items-center gap-1 text-green-600">
        <Mail className="w-4 h-4" />
        <span className="text-sm font-medium">
          {domain.syncedInboxCount}/{domain.expectedInboxCount} Inboxes
        </span>
      </div>

      {/* Progress bar */}
      <Progress
        value={(domain.syncedInboxCount / domain.expectedInboxCount) * 100}
        className="h-2"
      />

      {/* Completion badge */}
      {domain.syncedInboxCount === domain.expectedInboxCount ? (
        <Badge className="text-xs bg-green-100 text-green-800">
          ✓ Complete
        </Badge>
      ) : (
        <Badge className="text-xs bg-yellow-100 text-yellow-800">
          {domain.expectedInboxCount - domain.syncedInboxCount} remaining
        </Badge>
      )}

      {/* Last sync timestamp */}
      {domain.lastInboxSyncedAt && (
        <div className="text-xs text-gray-400">
          Last sync {formatDistanceToNow(domain.lastInboxSyncedAt, { addSuffix: true })}
        </div>
      )}
    </>
  ) : (
    <div className="text-xs text-gray-400">No inboxes synced</div>
  )}
</div>
```

---

### 5. Row Layout

**Complete Row Structure:**
```tsx
<tr
  className={`
    border-b border-gray-200
    hover:bg-blue-50 transition-colors
    ${domain.currentStage >= 9 ? 'bg-green-50' : ''}
  `}
>
  {/* Checkbox column (sticky) */}
  <td className="border-r border-gray-200 p-3 sticky left-0 bg-white z-10">
    <input
      type="checkbox"
      checked={selectedDomainIds.has(domain.id)}
      onChange={() => toggleSelection(domain.id)}
      className="w-4 h-4 text-indigo-600 rounded"
    />
  </td>

  {/* Stage cells */}
  <td className="border-r border-gray-200 p-3 min-w-[200px]">
    <GeneratedCell domain={domain} />
  </td>
  <td className="border-r border-gray-200 p-3 min-w-[200px]">
    <PricedCell domain={domain} />
  </td>
  {/* ... remaining 7 cells ... */}
</tr>
```

**Row States:**
- **Default:** White background
- **Hover:** Light blue background (bg-blue-50)
- **Selected:** Checkmark in checkbox
- **Completed (stage 9):** Light green background (bg-green-50)

---

### 6. Footer Bar

**Layout:**
```tsx
<div className="sticky bottom-0 bg-white border-t border-gray-200 p-4 flex justify-between items-center">
  {/* Left: Selection info */}
  <div className="flex items-center gap-4">
    <span className="text-sm text-gray-700">
      <strong>{selectedCount}</strong> domains selected
    </span>
    {selectedCount > 0 && (
      <>
        <span className="text-sm text-gray-500">•</span>
        <span className="text-sm text-gray-700">
          Total cost: <strong>${totalCost.toFixed(2)}</strong>
        </span>
        <Button
          variant="ghost"
          size="sm"
          onClick={clearSelection}
          className="text-gray-500"
        >
          Clear selection
        </Button>
      </>
    )}
  </div>

  {/* Right: Status info */}
  <div className="flex items-center gap-4 text-sm text-gray-500">
    <span>
      {totalDomains} total domains
    </span>
    <span>•</span>
    <span className="flex items-center gap-1">
      <RefreshCw className="w-3 h-3" />
      Last sync: {formatDistanceToNow(lastSync, { addSuffix: true })}
    </span>
  </div>
</div>
```

---

## 🎭 Modals

### 1. Bulk Price Check Modal

**Visual Design:**
```
┌─────────────────────────────────────────────────────┐
│ Check Prices for 15 Domains                    [×] │
├─────────────────────────────────────────────────────┤
│                                                     │
│ ┌─────────────────────────────────────────────┐   │
│ │ Checking prices from Porkbun and Dynadot... │   │
│ │                                               │   │
│ │ Progress: 8/15 domains checked                │   │
│ │ [████████████░░░░░░░░]  53%                  │   │
│ └─────────────────────────────────────────────┘   │
│                                                     │
│ ┌─────────────────────────────────────────────┐   │
│ │ Domain          │ Porkbun │ Dynadot │ Best  │   │
│ ├─────────────────┼─────────┼─────────┼───────┤   │
│ │ example.io      │ $8.99   │ $9.49   │ PB ✓  │   │
│ │ test.io         │ $12.49  │ $11.99  │ DY ✓  │   │
│ │ ... (scrollable)│         │         │       │   │
│ └─────────────────────────────────────────────┘   │
│                                                     │
│               [Cancel]  [Done]                      │
└─────────────────────────────────────────────────────┘
```

**Features:**
- Real-time progress updates
- Side-by-side price comparison
- Auto-select lowest price provider
- Error handling for unavailable domains

---

### 2. Bulk Purchase Modal

**Visual Design:**
```
┌─────────────────────────────────────────────────────┐
│ Purchase 15 Domains                             [×] │
├─────────────────────────────────────────────────────┤
│                                                     │
│ ┌─────────────────────────────────────────────┐   │
│ │ Total Cost                                    │   │
│ │ $127.85                                       │   │
│ └─────────────────────────────────────────────┘   │
│                                                     │
│ Provider Selection:                                 │
│ ○ Auto-select lowest price (Recommended)           │
│ ○ Porkbun only                                      │
│ ○ Dynadot only                                      │
│                                                     │
│ ┌─────────────────────────────────────────────┐   │
│ │ Domain          │ Price   │ Provider        │   │
│ ├─────────────────┼─────────┼─────────────────┤   │
│ │ example.io      │ $8.99   │ Porkbun         │   │
│ │ test.io         │ $11.99  │ Dynadot         │   │
│ │ ... (scrollable)│         │                 │   │
│ └─────────────────────────────────────────────┘   │
│                                                     │
│ ⚠️  This action cannot be undone. Charges will be  │
│    applied immediately.                             │
│                                                     │
│               [Cancel]  [Purchase All]              │
└─────────────────────────────────────────────────────┘
```

**Features:**
- Cost summary at top
- Provider selection (auto/manual)
- Breakdown table
- Warning about irreversible action
- Confirmation button with total cost

---

### 3. DNS Verification Modal

**Visual Design:**
```
┌─────────────────────────────────────────────────────┐
│ Verify DNS Records for 15 Domains              [×] │
├─────────────────────────────────────────────────────┤
│                                                     │
│ ┌─────────────────────────────────────────────┐   │
│ │ Verifying DNS records...                      │   │
│ │                                               │   │
│ │ Progress: 12/15 domains verified              │   │
│ │ [████████████████░░░]  80%                   │   │
│ └─────────────────────────────────────────────┘   │
│                                                     │
│ ┌─────────────────────────────────────────────┐   │
│ │ Domain     │ SPF │ DKIM│DMARC│ MX │ Status  │   │
│ ├────────────┼─────┼─────┼─────┼────┼─────────┤   │
│ │ example.io │ ✓   │ ✓   │ ✓   │ ✓  │ ✓ OK    │   │
│ │ test.io    │ ✓   │ ✗   │ ✓   │ ✓  │ ⚠ Incomplete│ │
│ │ ... (scrollable)                              │   │
│ └─────────────────────────────────────────────┘   │
│                                                     │
│ ℹ️  Incomplete records will be configured          │
│    automatically in the next sync.                  │
│                                                     │
│               [Close]  [Retry Failed]               │
└─────────────────────────────────────────────────────┘
```

**Features:**
- Per-record verification status
- Visual checkmarks/X marks
- Auto-retry for failed checks
- Explanation of incomplete records

---

### 4. HyperTide Order Modal

**Visual Design:**
```
┌─────────────────────────────────────────────────────┐
│ Create HyperTide Order                          [×] │
├─────────────────────────────────────────────────────┤
│                                                     │
│ Order Summary:                                      │
│ • 10 domains (8 Entra + 2 Google)                  │
│ • 4 orders (4 Entra @ 2 domains, 1 Google @ 5)     │
│ • Forwarding: client@emailbison.com                │
│                                                     │
│ ┌─────────────────────────────────────────────┐   │
│ │ Order │ Provider │ Domains │ Sender Name    │   │
│ ├───────┼──────────┼─────────┼────────────────┤   │
│ │ #1    │ 🔵 Entra │ 2       │ John Smith     │   │
│ │ #2    │ 🔵 Entra │ 2       │ Jane Doe       │   │
│ │ #3    │ 🔵 Entra │ 2       │ Mike Johnson   │   │
│ │ #4    │ 🔵 Entra │ 2       │ Sarah Williams │   │
│ │ #5    │ 🔴 Google│ 2       │ David Brown    │   │
│ └─────────────────────────────────────────────┘   │
│                                                     │
│ ⏱️  Estimated completion: 1-4 hours                │
│                                                     │
│ ⚠️  Orders are submitted to HyperTide and cannot   │
│    be cancelled. HyperTide will provision inboxes  │
│    within their standard SLA.                       │
│                                                     │
│               [Cancel]  [Submit Orders]             │
└─────────────────────────────────────────────────────┘
```

**Features:**
- Order grouping summary (2 for Entra, 5 for Google)
- Sender name selection per order
- Estimated completion time
- Warning about irreversible action

---

## 🔄 Loading & Error States

### Loading States

**Page-level loading:**
```tsx
<div className="flex items-center justify-center h-96">
  <div className="text-center space-y-4">
    <Loader2 className="w-12 h-12 animate-spin text-indigo-600 mx-auto" />
    <p className="text-gray-600">Loading waterfall data...</p>
  </div>
</div>
```

**Cell-level loading:**
```tsx
<div className="flex items-center gap-2">
  <Loader2 className="w-3 h-3 animate-spin text-gray-400" />
  <span className="text-xs text-gray-500">Loading...</span>
</div>
```

**Bulk action in progress:**
```tsx
<div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
  <div className="bg-white rounded-lg p-6 space-y-4 max-w-md">
    <Loader2 className="w-8 h-8 animate-spin text-indigo-600 mx-auto" />
    <p className="text-center font-medium">Purchasing 15 domains...</p>
    <Progress value={progress} />
    <p className="text-center text-sm text-gray-500">{progress}% complete</p>
  </div>
</div>
```

---

### Error States

**Page-level error:**
```tsx
<div className="flex items-center justify-center h-96">
  <div className="text-center space-y-4 max-w-md">
    <AlertCircle className="w-12 h-12 text-red-500 mx-auto" />
    <h3 className="text-lg font-semibold text-gray-900">Failed to load data</h3>
    <p className="text-gray-600">{error.message}</p>
    <Button onClick={handleRetry}>Retry</Button>
  </div>
</div>
```

**Cell-level error:**
```tsx
<div className="space-y-2">
  <div className="flex items-center gap-1 text-red-600">
    <XCircle className="w-4 h-4" />
    <span className="text-sm font-medium">Error</span>
  </div>
  <p className="text-xs text-red-600">{error.message}</p>
  <Button size="xs" variant="ghost" onClick={handleRetry}>
    Retry
  </Button>
</div>
```

**Toast notifications:**
```tsx
// Success
toast.success('15 domains purchased successfully');

// Error
toast.error('Price check failed for 3 domains');

// Warning
toast.warning('2 domains have stale prices');

// Info
toast.info('DNS verification in progress...');
```

---

## 🎯 Interaction Patterns

### Selection Behavior

**Single selection:**
- Click checkbox to toggle
- Row highlights on selection

**Select all:**
- Checkbox in header selects all visible domains
- Shows "(X selected)" count

**Bulk actions:**
- Only enabled when domains are selected
- Button shows count: "Purchase (15)"
- Clicking opens modal with selected domains

---

### Keyboard Shortcuts

```
Cmd/Ctrl + A     - Select all domains
Cmd/Ctrl + D     - Deselect all
Cmd/Ctrl + R     - Refresh data
Escape           - Close modal / clear selection
Arrow Up/Down    - Navigate rows
Space            - Toggle checkbox
```

---

### Responsive Behavior

**Mobile view (<768px):**
```tsx
<div className="space-y-4 p-4">
  {domains.map(domain => (
    <DomainCard key={domain.id} domain={domain}>
      {/* Card header */}
      <div className="flex justify-between items-start mb-3">
        <div>
          <h3 className="font-medium">{domain.name}</h3>
          {domain.owned && <Badge size="sm">Owned</Badge>}
        </div>
        <input type="checkbox" />
      </div>

      {/* Stage progress bar */}
      <div className="mb-3">
        <Progress value={(domain.currentStage / 9) * 100} />
        <p className="text-xs text-gray-500 mt-1">
          Stage {domain.currentStage}/9: {STAGE_LABELS[domain.currentStage]}
        </p>
      </div>

      {/* Current stage details */}
      <div className="p-3 bg-gray-50 rounded">
        {renderCurrentStageCell(domain)}
      </div>

      {/* Actions */}
      <div className="mt-3 flex gap-2">
        {getAvailableActions(domain).map(action => (
          <Button key={action.id} size="sm" variant="outline">
            {action.label}
          </Button>
        ))}
      </div>
    </DomainCard>
  ))}
</div>
```

---

## 📊 Summary

### Component Hierarchy
```
InfrastructurePage
├── Header
│   ├── Title
│   ├── ViewFilters (All/Owned/New)
│   └── ClientSelector
├── WaterfallTable
│   ├── WaterfallHeader
│   │   ├── CheckboxColumn
│   │   └── StageColumns (9)
│   │       ├── StageLabel
│   │       ├── StageDescription
│   │       └── BulkActionButton
│   └── WaterfallBody
│       └── WaterfallRow (per domain)
│           ├── CheckboxCell
│           ├── GeneratedCell
│           ├── PricedCell
│           ├── PurchasedCell
│           ├── DNSMovedCell
│           ├── DNSVerifiedCell
│           ├── ProviderAssignedCell
│           ├── HyperTideOrderedCell
│           ├── ProvisionedCell
│           └── SyncedCell
├── Footer
│   ├── SelectionInfo
│   └── StatusInfo
└── Modals
    ├── BulkPriceCheckModal
    ├── BulkPurchaseModal
    ├── BulkDNSSetModal
    ├── DNSVerificationModal
    ├── ProviderAssignmentModal
    └── HyperTideOrderModal
```

### Design Tokens Summary
- **Colors:** 15 status colors, 5 action colors, 2 provider colors
- **Typography:** 5 text sizes (xs to xl)
- **Spacing:** Consistent 12px cell padding, 200-280px cell width
- **Components:** 25+ components (table, cells, modals, badges)

---

**All frontend design specifications complete. Ready for implementation in Phase 2-3.**
