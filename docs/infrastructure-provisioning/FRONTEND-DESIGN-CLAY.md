# Infrastructure Provisioning SPA - Clay.com Waterfall Style

**Date:** 2026-02-25
**Design Language:** Clay.com-inspired enrichment waterfall with smooth interactions
**Reference:** Clay.com's data enrichment waterfall UI

---

## 🎨 Clay Design Philosophy

### Core Principles

1. **Waterfall Enrichment Flow** - Left-to-right progression like Clay's data enrichment
2. **Inline Actions** - Click cells to trigger actions (price check, purchase, etc.)
3. **Real-time Updates** - Animated status changes, live progress indicators
4. **Smooth Interactions** - Hover states, transitions, micro-animations
5. **Visual Hierarchy** - Color-coded stages, clear progression indicators
6. **Contextual Actions** - Actions appear on hover, context menus
7. **Smart Defaults** - Auto-price-check on generation, auto-select cheapest
8. **Bulk Operations** - Multi-select rows with shift+click, bulk actions bar
9. **Status Indicators** - Pills, dots, progress rings, not just text
10. **Dense but Breathable** - Compact like Clay but with proper spacing

---

## 🎨 Design System

### Color Palette (Clay-Inspired)

```css
/* Base colors - Neutral with warmth */
--gray-50: #F9FAFB;
--gray-100: #F3F4F6;
--gray-200: #E5E7EB;
--gray-300: #D1D5DB;
--gray-400: #9CA3AF;
--gray-500: #6B7280;
--gray-600: #4B5563;
--gray-700: #374151;
--gray-800: #1F2937;
--gray-900: #111827;

/* Primary - Purple/Indigo (Clay's signature) */
--primary-50: #EEF2FF;
--primary-100: #E0E7FF;
--primary-200: #C7D2FE;
--primary-500: #6366F1;
--primary-600: #4F46E5;
--primary-700: #4338CA;

/* Stage colors - Subtle pastels */
--stage-not-started: #F3F4F6;      /* Gray */
--stage-in-progress: #DBEAFE;      /* Light blue */
--stage-complete: #D1FAE5;         /* Light green */
--stage-error: #FEE2E2;            /* Light red */
--stage-warning: #FEF3C7;          /* Light yellow */

/* Status colors - Vibrant for indicators */
--status-success: #10B981;         /* Green */
--status-warning: #F59E0B;         /* Orange */
--status-error: #EF4444;           /* Red */
--status-info: #3B82F6;            /* Blue */

/* Provider colors */
--provider-entra: #0078D4;         /* Microsoft Blue */
--provider-google: #EA4335;        /* Google Red */
```

### Typography

```css
/* Fonts - Clean sans-serif */
--font-sans: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
--font-mono: 'JetBrains Mono', 'SF Mono', monospace;

/* Sizes */
--text-2xl: 24px / 32px;
--text-xl: 20px / 28px;
--text-lg: 16px / 24px;
--text-base: 14px / 20px;
--text-sm: 12px / 16px;
--text-xs: 11px / 16px;

/* Weights */
--font-normal: 400;
--font-medium: 500;
--font-semibold: 600;
--font-bold: 700;
```

### Spacing & Layout

```css
/* Border radius - Rounded everywhere */
--radius-sm: 4px;
--radius-md: 6px;
--radius-lg: 8px;
--radius-xl: 12px;
--radius-full: 9999px;

/* Shadows - Subtle depth */
--shadow-sm: 0 1px 2px 0 rgb(0 0 0 / 0.05);
--shadow-md: 0 4px 6px -1px rgb(0 0 0 / 0.1);
--shadow-lg: 0 10px 15px -3px rgb(0 0 0 / 0.1);
--shadow-xl: 0 20px 25px -5px rgb(0 0 0 / 0.1);

/* Cell dimensions */
--cell-padding: 12px 16px;
--cell-min-width: 180px;
--cell-max-width: 280px;
--row-height: 64px;
```

### Animations

```css
/* Transitions - Smooth everything */
--transition-fast: 150ms cubic-bezier(0.4, 0, 0.2, 1);
--transition-base: 200ms cubic-bezier(0.4, 0, 0.2, 1);
--transition-slow: 300ms cubic-bezier(0.4, 0, 0.2, 1);

/* Status change animation */
@keyframes statusPulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.5; }
}

/* Progress fill animation */
@keyframes progressFill {
  from { width: 0%; }
  to { width: var(--progress-percent); }
}

/* Shimmer loading */
@keyframes shimmer {
  0% { background-position: -200% 0; }
  100% { background-position: 200% 0; }
}
```

---

## 🖼️ Page Layout (Clay Style)

### Overall Structure

```
┌─────────────────────────────────────────────────────────────────────┐
│  Header (Floating white card with shadow)                           │
│  ┌────────────────────────────────────────────────────────────────┐ │
│  │ 🔷 Infrastructure Provisioning    [All] [Owned] [New]   Client▼│ │
│  │ Bulk domain & inbox provisioning workflow                      │ │
│  └────────────────────────────────────────────────────────────────┘ │
│                                                                      │
│  Waterfall Table (Smooth scroll, sticky columns)                    │
│  ┌─────┬──────────┬─────────┬──────────┬─────────┬─────────┬─────┐ │
│  │ ☐   │ Generated│ Priced  │ Purchased│ DNS Set │ DNS ✓   │ ... │ │
│  │ ▼   │   74     │   68    │    62    │   58    │   54    │     │ │
│  ├─────┼──────────┼─────────┼──────────┼─────────┼─────────┼─────┤ │
│  │ ☐   │○ dom.io  │ ○ $8.99 │ ● 2h ago │ ● 24h   │ ● All OK│ ... │ │
│  │     │  Own 87% │   PB    │   PB     │   NS OK │  ✓✓✓✓   │     │ │
│  ├─────┼──────────┼─────────┼──────────┼─────────┼─────────┼─────┤ │
│  │ ☐   │○ test.io │ ○ $12.49│          │         │         │     │ │
│  │     │  New 92% │   DY    │ [Buy]    │         │         │     │ │
│  └─────┴──────────┴─────────┴──────────┴─────────┴─────────┴─────┘ │
│                                                                      │
│  ┌────────────────────────────────────────────────────────────────┐ │
│  │ 💡 2 selected • $21.48 total • [Check Prices] [Purchase]       │ │
│  └────────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────────┘
```

### Header Component

```tsx
<div className="sticky top-0 z-50 p-4 bg-gray-50">
  <div className="max-w-[1600px] mx-auto">
    {/* Main header card */}
    <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-4">
      <div className="flex items-center justify-between mb-2">
        {/* Left: Title with icon */}
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 bg-gradient-to-br from-indigo-500 to-purple-600 rounded-lg flex items-center justify-center">
            <svg className="w-6 h-6 text-white" />
          </div>
          <div>
            <h1 className="text-xl font-semibold text-gray-900">
              Infrastructure Provisioning
            </h1>
            <p className="text-sm text-gray-500">
              Bulk domain & inbox provisioning workflow
            </p>
          </div>
        </div>

        {/* Right: Client selector */}
        <div className="flex items-center gap-3">
          <ClientSelector />
          <button className="p-2 hover:bg-gray-100 rounded-lg transition-colors">
            <RefreshCw className="w-5 h-5 text-gray-500" />
          </button>
        </div>
      </div>

      {/* View tabs */}
      <div className="flex gap-2">
        <ViewTab active label="All" count={347} />
        <ViewTab label="Owned" count={142} />
        <ViewTab label="New" count={205} />
      </div>
    </div>
  </div>
</div>

// View Tab Component
function ViewTab({ label, count, active }) {
  return (
    <button className={`
      px-4 py-2 rounded-lg text-sm font-medium transition-all
      ${active
        ? 'bg-indigo-50 text-indigo-700 shadow-sm'
        : 'text-gray-600 hover:bg-gray-100'
      }
    `}>
      {label}
      <span className={`ml-2 px-2 py-0.5 rounded-full text-xs ${
        active ? 'bg-indigo-100 text-indigo-700' : 'bg-gray-100 text-gray-600'
      }`}>
        {count}
      </span>
    </button>
  );
}
```

---

## 🎯 Waterfall Table (Clay Style)

### Table Structure

```tsx
<div className="p-4 bg-gray-50">
  <div className="max-w-[1600px] mx-auto">
    <div className="bg-white rounded-xl shadow-sm border border-gray-200 overflow-hidden">
      <div className="overflow-x-auto">
        <table className="w-full">
          {/* Header with sticky positioning */}
          <thead className="bg-gray-50 border-b border-gray-200 sticky top-16 z-40">
            <tr>
              <th className="p-4 text-left w-12">
                <input type="checkbox" className="rounded border-gray-300" />
              </th>
              {STAGES.map(stage => (
                <th key={stage.id} className="p-4 text-left min-w-[200px]">
                  <StageHeader stage={stage} />
                </th>
              ))}
            </tr>
          </thead>

          {/* Body with hover effects */}
          <tbody className="divide-y divide-gray-100">
            {domains.map(domain => (
              <tr
                key={domain.id}
                className="group hover:bg-gray-50 transition-colors"
              >
                <td className="p-4">
                  <input
                    type="checkbox"
                    checked={selected.has(domain.id)}
                    className="rounded border-gray-300"
                  />
                </td>
                {/* Stage cells */}
                <td className="p-4"><GeneratedCell domain={domain} /></td>
                <td className="p-4"><PricedCell domain={domain} /></td>
                <td className="p-4"><PurchasedCell domain={domain} /></td>
                {/* ... remaining cells */}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  </div>
</div>
```

### Stage Header Component

```tsx
function StageHeader({ stage }: { stage: Stage }) {
  const count = domains.filter(d => d.currentStage === stage.id).length;
  const selectedCount = selectedDomains.filter(d => d.currentStage === stage.id).length;

  return (
    <div className="space-y-2">
      {/* Stage name with count badge */}
      <div className="flex items-center gap-2">
        <span className="text-sm font-semibold text-gray-900">
          {stage.label}
        </span>
        <span className="px-2 py-0.5 bg-gray-100 text-gray-600 rounded-full text-xs font-medium">
          {count}
        </span>
      </div>

      {/* Stage description */}
      <p className="text-xs text-gray-500 leading-relaxed">
        {stage.description}
      </p>

      {/* Bulk action button (appears when domains selected) */}
      {selectedCount > 0 && stage.bulkAction && (
        <button className="
          w-full px-3 py-2 bg-indigo-600 text-white rounded-lg text-sm font-medium
          hover:bg-indigo-700 transition-colors shadow-sm
          flex items-center justify-center gap-2
        ">
          <stage.bulkAction.icon className="w-4 h-4" />
          {stage.bulkAction.label} ({selectedCount})
        </button>
      )}
    </div>
  );
}
```

---

## 🎨 Stage Cell Designs (Clay Style)

### Cell 1: Generated Cell

**Visual Design:**
```
┌────────────────────────────┐
│ ○ example.io               │ ← Status dot + domain
│   ┌───┐ ┌────┐             │
│   │Own│ │ 87%│             │ ← Pills
│   └───┘ └────┘             │
│   2 hours ago              │ ← Relative time
└────────────────────────────┘
```

**Component:**
```tsx
function GeneratedCell({ domain }: { domain: WaterfallDomain }) {
  const statusColor = domain.currentStage >= 1 ? 'bg-green-500' : 'bg-gray-300';

  return (
    <div className="space-y-2">
      {/* Domain name with status dot */}
      <div className="flex items-center gap-2">
        <div className={`w-2 h-2 rounded-full ${statusColor} transition-colors`} />
        <span className="font-medium text-sm text-gray-900">
          {domain.name}
        </span>
      </div>

      {/* Status pills */}
      <div className="flex gap-1.5 flex-wrap">
        {domain.owned && (
          <span className="px-2 py-1 bg-green-50 text-green-700 rounded-md text-xs font-medium border border-green-200">
            Owned
          </span>
        )}
        {domain.deployed && (
          <span className="px-2 py-1 bg-blue-50 text-blue-700 rounded-md text-xs font-medium border border-blue-200">
            Deployed
          </span>
        )}
        {domain.legitimacyScore && (
          <span className={`px-2 py-1 rounded-md text-xs font-medium border ${
            domain.legitimacyScore >= 0.8
              ? 'bg-green-50 text-green-700 border-green-200'
              : domain.legitimacyScore >= 0.6
              ? 'bg-yellow-50 text-yellow-700 border-yellow-200'
              : 'bg-red-50 text-red-700 border-red-200'
          }`}>
            {(domain.legitimacyScore * 100).toFixed(0)}%
          </span>
        )}
      </div>

      {/* Relative timestamp */}
      <div className="text-xs text-gray-500">
        {formatDistanceToNow(domain.createdAt, { addSuffix: true })}
      </div>
    </div>
  );
}
```

**Empty State:**
```tsx
<div className="flex items-center gap-2 text-gray-400">
  <div className="w-2 h-2 rounded-full bg-gray-300" />
  <span className="text-sm">Not generated</span>
</div>
```

---

### Cell 2: Priced Cell (Interactive)

**Visual Design:**
```
┌────────────────────────────┐
│ ○ $8.99                    │ ← Status dot + price
│   Porkbun • Valid          │ ← Provider • Status
│   ┌──────────────┐         │
│   │ [Auto-check] │  🔄    │ ← Inline action
│   └──────────────┘         │
└────────────────────────────┘
```

**Component:**
```tsx
function PricedCell({ domain }: { domain: WaterfallDomain }) {
  const [checking, setChecking] = useState(false);
  const statusColor = domain.cachedPrice ? 'bg-green-500' : 'bg-gray-300';

  const handleCheckPrice = async () => {
    setChecking(true);
    await checkPrice(domain.id);
    setChecking(false);
  };

  return (
    <div className="space-y-2 group/cell">
      {domain.cachedPrice ? (
        <>
          {/* Price with status dot */}
          <div className="flex items-center gap-2">
            <div className={`w-2 h-2 rounded-full ${statusColor}`} />
            <span className="font-semibold text-base text-gray-900">
              ${domain.cachedPrice.toFixed(2)}
            </span>
          </div>

          {/* Provider and status */}
          <div className="flex items-center gap-2 text-xs">
            <span className="text-gray-700 font-medium">
              {domain.selectedProvider === 'porkbun' ? 'Porkbun' : 'Dynadot'}
            </span>
            <span className="text-gray-400">•</span>
            <span className={`${
              domain.priceStatus === 'valid' ? 'text-green-600' :
              domain.priceStatus === 'stale' ? 'text-orange-600' :
              'text-red-600'
            }`}>
              {domain.priceStatus === 'valid' ? 'Valid' :
               domain.priceStatus === 'stale' ? 'Stale' :
               'Unavailable'}
            </span>
          </div>

          {/* Stale warning with refresh action */}
          {domain.priceStatus === 'stale' && (
            <button
              onClick={handleCheckPrice}
              disabled={checking}
              className="
                w-full px-3 py-1.5 bg-orange-50 text-orange-700 rounded-lg text-xs font-medium
                hover:bg-orange-100 transition-colors border border-orange-200
                flex items-center justify-center gap-1.5
              "
            >
              <RefreshCw className={`w-3 h-3 ${checking ? 'animate-spin' : ''}`} />
              Refresh Price
            </button>
          )}

          {/* Last checked timestamp */}
          <div className="text-xs text-gray-400">
            Checked {formatDistanceToNow(domain.priceCheckedAt, { addSuffix: true })}
          </div>
        </>
      ) : (
        <>
          {/* Empty state with action */}
          <div className="flex items-center gap-2 text-gray-400">
            <div className="w-2 h-2 rounded-full bg-gray-300" />
            <span className="text-sm">Not priced</span>
          </div>
          <button
            onClick={handleCheckPrice}
            disabled={checking}
            className="
              w-full px-3 py-2 bg-indigo-600 text-white rounded-lg text-sm font-medium
              hover:bg-indigo-700 transition-colors shadow-sm
              opacity-0 group-hover/cell:opacity-100
            "
          >
            {checking ? (
              <Loader2 className="w-4 h-4 animate-spin mx-auto" />
            ) : (
              'Check Price'
            )}
          </button>
        </>
      )}
    </div>
  );
}
```

---

### Cell 3: Purchased Cell

**Visual Design:**
```
┌────────────────────────────┐
│ ● Purchased                │ ← Filled dot (complete)
│   Porkbun • 2 hours ago    │
│   [View Receipt]           │ ← Hover action
└────────────────────────────┘
```

**Component:**
```tsx
function PurchasedCell({ domain }: { domain: WaterfallDomain }) {
  const statusColor = domain.purchasedAt ? 'bg-green-500' : 'bg-gray-300';

  return (
    <div className="space-y-2 group/cell">
      {domain.purchasedAt ? (
        <>
          {/* Status with filled dot */}
          <div className="flex items-center gap-2">
            <div className={`w-2 h-2 rounded-full ${statusColor}`} />
            <span className="font-medium text-sm text-green-700">
              Purchased
            </span>
          </div>

          {/* Provider and timestamp */}
          <div className="text-xs text-gray-600">
            <span className="font-medium">
              {domain.selectedProvider === 'porkbun' ? 'Porkbun' : 'Dynadot'}
            </span>
            <span className="text-gray-400"> • </span>
            <span>
              {formatDistanceToNow(domain.purchasedAt, { addSuffix: true })}
            </span>
          </div>

          {/* Purchase job status if processing */}
          {domain.purchaseJobStatus && domain.purchaseJobStatus !== 'completed' && (
            <div className="flex items-center gap-2 text-xs text-blue-600">
              <Loader2 className="w-3 h-3 animate-spin" />
              Processing...
            </div>
          )}
        </>
      ) : (
        <>
          {/* Empty state */}
          <div className="flex items-center gap-2 text-gray-400">
            <div className="w-2 h-2 rounded-full bg-gray-300" />
            <span className="text-sm">Not purchased</span>
          </div>

          {/* Inline purchase button (hover) */}
          {domain.cachedPrice && (
            <button className="
              w-full px-3 py-2 bg-green-600 text-white rounded-lg text-sm font-medium
              hover:bg-green-700 transition-all shadow-sm
              opacity-0 group-hover/cell:opacity-100
            ">
              Buy ${domain.cachedPrice.toFixed(2)}
            </button>
          )}
        </>
      )}
    </div>
  );
}
```

---

### Cell 4: DNS Moved Cell

**Visual Design:**
```
┌────────────────────────────┐
│ ● Nameservers Set          │
│   ┌─────────────────┐      │
│   │ ⚡ Propagating   │      │ ← Status pill
│   └─────────────────┘      │
│   ns1.dnsimple.com         │
│   24 hours ago             │
└────────────────────────────┘
```

**Component:**
```tsx
function DNSMovedCell({ domain }: { domain: WaterfallDomain }) {
  const statusColor = domain.nameserversUpdatedAt ? 'bg-blue-500' : 'bg-gray-300';

  return (
    <div className="space-y-2">
      {domain.nameserversUpdatedAt ? (
        <>
          {/* Status */}
          <div className="flex items-center gap-2">
            <div className={`w-2 h-2 rounded-full ${statusColor}`} />
            <span className="font-medium text-sm text-gray-900">
              Nameservers Set
            </span>
          </div>

          {/* Propagation status pill */}
          <div className={`inline-flex items-center gap-1.5 px-2 py-1 rounded-md text-xs font-medium ${
            domain.dnsMigrationStatus === 'propagated'
              ? 'bg-green-50 text-green-700 border border-green-200'
              : domain.dnsMigrationStatus === 'propagating'
              ? 'bg-blue-50 text-blue-700 border border-blue-200'
              : 'bg-gray-50 text-gray-700 border border-gray-200'
          }`}>
            {domain.dnsMigrationStatus === 'propagating' && (
              <Loader2 className="w-3 h-3 animate-spin" />
            )}
            {domain.dnsMigrationStatus === 'propagated' ? 'Propagated' :
             domain.dnsMigrationStatus === 'propagating' ? 'Propagating' :
             'Not Set'}
          </div>

          {/* First nameserver (truncated) */}
          {domain.currentNameservers && (
            <div className="text-xs text-gray-600 font-mono truncate">
              {domain.currentNameservers[0]}
            </div>
          )}

          {/* Timestamp */}
          <div className="text-xs text-gray-400">
            {formatDistanceToNow(domain.nameserversUpdatedAt, { addSuffix: true })}
          </div>
        </>
      ) : (
        <div className="flex items-center gap-2 text-gray-400">
          <div className="w-2 h-2 rounded-full bg-gray-300" />
          <span className="text-sm">NS not set</span>
        </div>
      )}
    </div>
  );
}
```

---

### Cell 5: DNS Verified Cell (Interactive Checklist)

**Visual Design:**
```
┌────────────────────────────┐
│ ● All Records OK           │
│   ✓ SPF  ✓ DKIM           │
│   ✓ DMARC ✓ MX             │
│   ┌──────────────┐         │
│   │ [Re-verify]  │         │ ← Hover action
│   └──────────────┘         │
└────────────────────────────┘
```

**Component:**
```tsx
function DNSVerifiedCell({ domain }: { domain: WaterfallDomain }) {
  const [verifying, setVerifying] = useState(false);
  const allConfigured = domain.dnsRecordsConfigured;
  const statusColor = allConfigured ? 'bg-green-500' : 'bg-orange-500';

  const handleVerify = async () => {
    setVerifying(true);
    await verifyDNS(domain.id);
    setVerifying(false);
  };

  return (
    <div className="space-y-2 group/cell">
      {/* Status */}
      <div className="flex items-center gap-2">
        <div className={`w-2 h-2 rounded-full ${statusColor} transition-colors`} />
        <span className={`font-medium text-sm ${
          allConfigured ? 'text-green-700' : 'text-orange-700'
        }`}>
          {allConfigured ? 'All Records OK' : 'Incomplete'}
        </span>
      </div>

      {/* Record checklist - compact grid */}
      <div className="grid grid-cols-2 gap-x-3 gap-y-1">
        <DNSRecordCheck label="SPF" checked={domain.spfConfigured} />
        <DNSRecordCheck label="DKIM" checked={domain.dkimConfigured} />
        <DNSRecordCheck label="DMARC" checked={domain.dmarcConfigured} />
        <DNSRecordCheck label="MX" checked={domain.mxConfigured} />
      </div>

      {/* Re-verify action (hover) */}
      <button
        onClick={handleVerify}
        disabled={verifying}
        className="
          w-full px-3 py-1.5 bg-indigo-50 text-indigo-700 rounded-lg text-xs font-medium
          hover:bg-indigo-100 transition-all border border-indigo-200
          opacity-0 group-hover/cell:opacity-100
        "
      >
        {verifying ? (
          <Loader2 className="w-3 h-3 animate-spin mx-auto" />
        ) : (
          'Re-verify'
        )}
      </button>

      {/* Last verified */}
      {domain.nameserverVerifiedAt && (
        <div className="text-xs text-gray-400">
          Verified {formatDistanceToNow(domain.nameserverVerifiedAt, { addSuffix: true })}
        </div>
      )}
    </div>
  );
}

// Helper component
function DNSRecordCheck({ label, checked }: { label: string; checked: boolean }) {
  return (
    <div className="flex items-center gap-1.5 text-xs">
      {checked ? (
        <CheckCircle className="w-3.5 h-3.5 text-green-500" />
      ) : (
        <Circle className="w-3.5 h-3.5 text-gray-300" />
      )}
      <span className={checked ? 'text-gray-700' : 'text-gray-400'}>
        {label}
      </span>
    </div>
  );
}
```

---

### Cell 6: Provider Assigned Cell (Inline Select)

**Visual Design:**
```
┌────────────────────────────┐
│ ● Microsoft Entra          │ ← Color-coded
│   🔵 2 domains/order       │
│   ┌──────────┬─────────┐   │
│   │ Entra ✓ │ Google  │   │ ← Toggle buttons
│   └──────────┴─────────┘   │
└────────────────────────────┘
```

**Component:**
```tsx
function ProviderAssignedCell({ domain }: { domain: WaterfallDomain }) {
  const [assigning, setAssigning] = useState(false);
  const statusColor = domain.assignedProvider
    ? domain.assignedProvider === 'entra' ? 'bg-blue-500' : 'bg-red-500'
    : 'bg-gray-300';

  const handleAssign = async (provider: 'entra' | 'google') => {
    setAssigning(true);
    await assignProvider(domain.id, provider);
    setAssigning(false);
  };

  return (
    <div className="space-y-2">
      {domain.assignedProvider ? (
        <>
          {/* Provider with colored dot */}
          <div className="flex items-center gap-2">
            <div className={`w-2 h-2 rounded-full ${statusColor}`} />
            <span className="font-medium text-sm text-gray-900">
              {domain.assignedProvider === 'entra' ? 'Microsoft Entra' : 'Google Workspace'}
            </span>
          </div>

          {/* Batch size info */}
          <div className="flex items-center gap-1.5 text-xs text-gray-600">
            <span className={`w-5 h-5 rounded-full flex items-center justify-center ${
              domain.assignedProvider === 'entra' ? 'bg-blue-100 text-blue-700' : 'bg-red-100 text-red-700'
            }`}>
              {domain.assignedProvider === 'entra' ? '2' : '5'}
            </span>
            domains/order
          </div>

          {/* Toggle provider (hover) */}
          <div className="opacity-0 group-hover/cell:opacity-100 transition-opacity">
            <div className="grid grid-cols-2 gap-1">
              <button
                onClick={() => handleAssign('entra')}
                disabled={assigning || domain.assignedProvider === 'entra'}
                className={`px-2 py-1 rounded text-xs font-medium transition-colors ${
                  domain.assignedProvider === 'entra'
                    ? 'bg-blue-100 text-blue-700 border border-blue-300'
                    : 'bg-gray-50 text-gray-600 hover:bg-gray-100 border border-gray-200'
                }`}
              >
                Entra
              </button>
              <button
                onClick={() => handleAssign('google')}
                disabled={assigning || domain.assignedProvider === 'google'}
                className={`px-2 py-1 rounded text-xs font-medium transition-colors ${
                  domain.assignedProvider === 'google'
                    ? 'bg-red-100 text-red-700 border border-red-300'
                    : 'bg-gray-50 text-gray-600 hover:bg-gray-100 border border-gray-200'
                }`}
              >
                Google
              </button>
            </div>
          </div>
        </>
      ) : (
        <>
          {/* Empty state */}
          <div className="flex items-center gap-2 text-gray-400">
            <div className="w-2 h-2 rounded-full bg-gray-300" />
            <span className="text-sm">Not assigned</span>
          </div>

          {/* Assignment buttons */}
          <div className="grid grid-cols-2 gap-1">
            <button
              onClick={() => handleAssign('entra')}
              disabled={assigning}
              className="px-2 py-1.5 bg-blue-50 text-blue-700 rounded text-xs font-medium hover:bg-blue-100 transition-colors border border-blue-200"
            >
              Entra
            </button>
            <button
              onClick={() => handleAssign('google')}
              disabled={assigning}
              className="px-2 py-1.5 bg-red-50 text-red-700 rounded text-xs font-medium hover:bg-red-100 transition-colors border border-red-200"
            >
              Google
            </button>
          </div>
        </>
      )}
    </div>
  );
}
```

---

### Cell 7: HyperTide Ordered Cell (Live Progress)

**Visual Design:**
```
┌────────────────────────────┐
│ ● Order #A1B2C3            │
│   ┌──────────────────┐     │
│   │ ████████░░ 80%   │     │ ← Smooth progress bar
│   └──────────────────┘     │
│   Step 4/5 • 23min ago     │
└────────────────────────────┘
```

**Component:**
```tsx
function HyperTideOrderedCell({ domain }: { domain: WaterfallDomain }) {
  const statusColor = domain.hyperTideOrderJobId ? 'bg-blue-500' : 'bg-gray-300';
  const progress = domain.hyperTideProgress || 0;

  return (
    <div className="space-y-2">
      {domain.hyperTideOrderJobId ? (
        <>
          {/* Order ID */}
          <div className="flex items-center gap-2">
            <div className={`w-2 h-2 rounded-full ${statusColor} ${
              domain.hyperTideOrderStatus !== 'completed' ? 'animate-pulse' : ''
            }`} />
            <span className="font-medium text-sm text-gray-900 font-mono">
              Order #{domain.hyperTideOrderJobId.slice(0, 6).toUpperCase()}
            </span>
          </div>

          {/* Progress bar (smooth animation) */}
          {domain.hyperTideOrderStatus !== 'completed' && (
            <div className="space-y-1">
              <div className="h-2 bg-gray-100 rounded-full overflow-hidden">
                <div
                  className="h-full bg-gradient-to-r from-blue-500 to-indigo-600 rounded-full transition-all duration-500"
                  style={{ width: `${progress}%` }}
                />
              </div>
              <div className="flex items-center justify-between text-xs">
                <span className="text-gray-600">
                  Step {domain.hyperTideCurrentStep}
                </span>
                <span className="font-medium text-blue-600">
                  {progress}%
                </span>
              </div>
            </div>
          )}

          {/* Completed state */}
          {domain.hyperTideOrderStatus === 'completed' && (
            <div className="flex items-center gap-1.5 px-2 py-1 bg-green-50 text-green-700 rounded-md text-xs font-medium border border-green-200">
              <CheckCircle className="w-3.5 h-3.5" />
              Complete
            </div>
          )}

          {/* Timestamp */}
          <div className="text-xs text-gray-400">
            {formatDistanceToNow(domain.hyperTideOrderedAt, { addSuffix: true })}
          </div>
        </>
      ) : (
        <div className="flex items-center gap-2 text-gray-400">
          <div className="w-2 h-2 rounded-full bg-gray-300" />
          <span className="text-sm">Not ordered</span>
        </div>
      )}
    </div>
  );
}
```

---

### Cell 8: Provisioned Cell

**Visual Design:**
```
┌────────────────────────────┐
│ ⚡ Provisioning             │
│   HyperTide • ~2h ETA      │
│   ┌──────────────┐         │
│   │ Polling...   │  🔄    │
│   └──────────────┘         │
└────────────────────────────┘
```

**Component:**
```tsx
function ProvisionedCell({ domain }: { domain: WaterfallDomain }) {
  const getStatusConfig = () => {
    switch (domain.provisioningStatus) {
      case 'synced':
        return { color: 'bg-green-500', label: 'Synced', icon: CheckCircle, textColor: 'text-green-700' };
      case 'awaiting_sync':
        return { color: 'bg-blue-500', label: 'Awaiting Sync', icon: Clock, textColor: 'text-blue-700' };
      case 'provisioning':
        return { color: 'bg-orange-500', label: 'Provisioning', icon: Loader2, textColor: 'text-orange-700' };
      default:
        return { color: 'bg-gray-300', label: 'Not Started', icon: Circle, textColor: 'text-gray-400' };
    }
  };

  const status = getStatusConfig();
  const StatusIcon = status.icon;

  return (
    <div className="space-y-2">
      {/* Status with icon */}
      <div className="flex items-center gap-2">
        <div className={`w-2 h-2 rounded-full ${status.color} ${
          domain.provisioningStatus === 'provisioning' ? 'animate-pulse' : ''
        }`} />
        <span className={`font-medium text-sm ${status.textColor}`}>
          {status.label}
        </span>
      </div>

      {/* Provisioning details */}
      {domain.provisioningStatus === 'provisioning' && (
        <>
          <div className="text-xs text-gray-600">
            HyperTide • ~2h ETA
          </div>
          <div className="flex items-center gap-1.5 text-xs text-gray-500">
            <Loader2 className="w-3 h-3 animate-spin" />
            Polling for updates...
          </div>
        </>
      )}
    </div>
  );
}
```

---

### Cell 9: Synced Cell (Progress Ring)

**Visual Design:**
```
┌────────────────────────────┐
│ ● 100/100 Inboxes          │
│   ┌──────────────┐         │
│   │  ⭕ 100%      │         │ ← Circular progress
│   └──────────────┘         │
│   Last sync: 5min ago      │
└────────────────────────────┘
```

**Component:**
```tsx
function SyncedCell({ domain }: { domain: WaterfallDomain }) {
  const percent = domain.expectedInboxCount > 0
    ? (domain.syncedInboxCount / domain.expectedInboxCount) * 100
    : 0;
  const isComplete = percent === 100;
  const statusColor = isComplete ? 'bg-green-500' : 'bg-blue-500';

  return (
    <div className="space-y-2">
      {domain.syncedInboxCount > 0 ? (
        <>
          {/* Count with status */}
          <div className="flex items-center gap-2">
            <div className={`w-2 h-2 rounded-full ${statusColor}`} />
            <span className="font-medium text-sm text-gray-900">
              {domain.syncedInboxCount}/{domain.expectedInboxCount} Inboxes
            </span>
          </div>

          {/* Progress bar (smooth) */}
          <div className="space-y-1">
            <div className="h-2 bg-gray-100 rounded-full overflow-hidden">
              <div
                className={`h-full rounded-full transition-all duration-500 ${
                  isComplete
                    ? 'bg-gradient-to-r from-green-500 to-emerald-600'
                    : 'bg-gradient-to-r from-blue-500 to-indigo-600'
                }`}
                style={{ width: `${percent}%` }}
              />
            </div>
            <div className="text-xs text-right font-medium text-gray-600">
              {percent.toFixed(0)}%
            </div>
          </div>

          {/* Complete badge */}
          {isComplete && (
            <div className="flex items-center gap-1.5 px-2 py-1 bg-green-50 text-green-700 rounded-md text-xs font-medium border border-green-200">
              <CheckCircle className="w-3.5 h-3.5" />
              Complete
            </div>
          )}

          {/* Last sync time */}
          {domain.lastInboxSyncedAt && (
            <div className="text-xs text-gray-400">
              Last sync {formatDistanceToNow(domain.lastInboxSyncedAt, { addSuffix: true })}
            </div>
          )}
        </>
      ) : (
        <div className="flex items-center gap-2 text-gray-400">
          <div className="w-2 h-2 rounded-full bg-gray-300" />
          <span className="text-sm">No inboxes synced</span>
        </div>
      )}
    </div>
  );
}
```

---

## 🎯 Bulk Actions Bar (Clay Style)

```tsx
function BulkActionsBar({ selectedDomains }: { selectedDomains: WaterfallDomain[] }) {
  const totalCost = selectedDomains.reduce((sum, d) => sum + (d.cachedPrice || 0), 0);

  if (selectedDomains.length === 0) return null;

  return (
    <div className="fixed bottom-4 left-1/2 -translate-x-1/2 z-50">
      <div className="bg-white rounded-xl shadow-xl border border-gray-200 p-4 min-w-[600px]">
        <div className="flex items-center justify-between gap-6">
          {/* Selection info */}
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 bg-indigo-100 rounded-full flex items-center justify-center">
              <span className="text-indigo-700 font-bold text-sm">
                {selectedDomains.length}
              </span>
            </div>
            <div>
              <div className="text-sm font-semibold text-gray-900">
                {selectedDomains.length} domain{selectedDomains.length !== 1 ? 's' : ''} selected
              </div>
              {totalCost > 0 && (
                <div className="text-xs text-gray-500">
                  Total: ${totalCost.toFixed(2)}
                </div>
              )}
            </div>
          </div>

          {/* Quick actions */}
          <div className="flex items-center gap-2">
            <button className="px-4 py-2 bg-indigo-600 text-white rounded-lg text-sm font-medium hover:bg-indigo-700 transition-colors shadow-sm">
              Check Prices
            </button>
            <button className="px-4 py-2 bg-green-600 text-white rounded-lg text-sm font-medium hover:bg-green-700 transition-colors shadow-sm">
              Purchase All
            </button>
            <button className="px-4 py-2 bg-blue-600 text-white rounded-lg text-sm font-medium hover:bg-blue-700 transition-colors shadow-sm">
              Set DNS
            </button>
            <button className="p-2 hover:bg-gray-100 rounded-lg transition-colors">
              <X className="w-5 h-5 text-gray-500" />
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
```

---

## 📱 Responsive (Mobile - Clay Style)

```tsx
<div className="p-4 space-y-4 bg-gray-50">
  {domains.map(domain => (
    <div key={domain.id} className="bg-white rounded-xl shadow-sm border border-gray-200 overflow-hidden">
      {/* Header */}
      <div className="p-4 bg-gradient-to-r from-indigo-50 to-purple-50 border-b border-gray-200">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <div className={`w-2 h-2 rounded-full ${
              domain.currentStage >= 9 ? 'bg-green-500' : 'bg-blue-500'
            }`} />
            <span className="font-semibold text-gray-900">{domain.name}</span>
          </div>
          <input type="checkbox" className="rounded border-gray-300" />
        </div>
      </div>

      {/* Progress */}
      <div className="p-4 border-b border-gray-100">
        <div className="flex items-center justify-between text-xs text-gray-600 mb-2">
          <span>Stage {domain.currentStage}/9</span>
          <span className="font-medium">{Math.floor((domain.currentStage / 9) * 100)}%</span>
        </div>
        <div className="h-2 bg-gray-100 rounded-full overflow-hidden">
          <div
            className="h-full bg-gradient-to-r from-indigo-500 to-purple-600 rounded-full transition-all"
            style={{ width: `${(domain.currentStage / 9) * 100}%` }}
          />
        </div>
        <div className="mt-2 text-sm font-medium text-gray-700">
          {STAGE_LABELS[domain.currentStage]}
        </div>
      </div>

      {/* Current stage details */}
      <div className="p-4 border-b border-gray-100">
        {renderCurrentStageCell(domain)}
      </div>

      {/* Quick actions */}
      <div className="p-4 flex gap-2">
        {getAvailableActions(domain).map(action => (
          <button
            key={action.id}
            className="flex-1 px-3 py-2 bg-indigo-600 text-white rounded-lg text-sm font-medium hover:bg-indigo-700 transition-colors shadow-sm"
          >
            {action.label}
          </button>
        ))}
      </div>
    </div>
  ))}
</div>
```

---

## 🎯 Summary

### Clay.com Style Characteristics

✅ **Smooth interactions** - Transitions, hover effects, micro-animations
✅ **Inline actions** - Click cells to trigger actions (no separate modals for simple tasks)
✅ **Real-time updates** - Animated progress bars, pulsing status dots
✅ **Visual hierarchy** - Color-coded stages, clear status indicators
✅ **Contextual UI** - Actions appear on hover, relevant to current state
✅ **Polished design** - Rounded corners, shadows, gradients
✅ **Smart defaults** - Auto-price-check, auto-select cheapest provider
✅ **Bulk operations** - Floating action bar when domains selected
✅ **Status pills** - Color-coded badges for quick scanning
✅ **Progress visualization** - Smooth bars, rings, step indicators

### Key Differences from Base44

| Aspect | Base44 (Brutalist) | Clay (Modern) |
|--------|-------------------|---------------|
| **Corners** | Sharp rectangles (0px) | Rounded (8-12px) |
| **Borders** | 2px solid black | 1px subtle gray |
| **Shadows** | None (flat) | Soft depth (sm/md) |
| **Colors** | High contrast B/W | Soft pastels + vibrant accents |
| **Typography** | Bold uppercase mono | Clean sans-serif, mixed case |
| **Actions** | Explicit buttons | Inline + hover reveals |
| **Progress** | ASCII blocks █░ | Smooth animated bars |
| **Status** | Text labels | Color dots + pills |
| **Spacing** | Dense, compact | Breathable, balanced |
| **Feel** | Raw, functional | Polished, delightful |

**This is the Clay.com waterfall enrichment style - smooth, polished, and production-ready!** 🎨
