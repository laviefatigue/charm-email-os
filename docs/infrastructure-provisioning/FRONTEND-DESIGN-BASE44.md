# Infrastructure Provisioning SPA - Base44 Aesthetic Design

**Date:** 2026-02-25
**Design Language:** Base44-inspired brutalist, data-dense, high-contrast interface
**Purpose:** Production-grade infrastructure provisioning with maximum information density

---

## 🎨 Base44 Design Philosophy

### Core Principles

1. **Brutalist Typography** - Strong, monospaced fonts for data clarity
2. **High Contrast** - Black text on white, bold accent colors
3. **Data Density** - Maximum information in minimum space
4. **Grid System** - Strict alignment, no rounded corners
5. **Functional Color** - Color only for status/meaning, not decoration
6. **No Shadows** - Flat design with solid borders
7. **Monospace Numbers** - Perfect alignment for tables
8. **Direct Actions** - No confirmation modals unless destructive

---

## 🎨 Design System

### Color Palette

```css
/* Base colors */
--base-black: #000000;
--base-white: #FFFFFF;
--base-gray-50: #F9FAFB;
--base-gray-100: #F3F4F6;
--base-gray-200: #E5E7EB;
--base-gray-300: #D1D5DB;
--base-gray-900: #111827;

/* Functional colors - only for status */
--status-active: #3B82F6;      /* Blue - in progress */
--status-success: #10B981;     /* Green - complete */
--status-warning: #F59E0B;     /* Orange - attention needed */
--status-error: #EF4444;       /* Red - failed */
--status-neutral: #6B7280;     /* Gray - inactive */

/* Provider colors */
--provider-entra: #000000;     /* Black with blue accent */
--provider-google: #000000;    /* Black with red accent */
--accent-entra: #3B82F6;
--accent-google: #EF4444;

/* Action colors */
--action-primary: #000000;
--action-primary-hover: #1F2937;
--action-destructive: #DC2626;
```

### Typography

```css
/* Fonts */
--font-mono: 'JetBrains Mono', 'Courier New', monospace;
--font-sans: 'Inter', -apple-system, sans-serif;

/* Sizes */
--text-2xl: 24px / 32px;  /* Page title */
--text-xl: 20px / 28px;   /* Section headers */
--text-lg: 16px / 24px;   /* Column headers */
--text-base: 14px / 20px; /* Body text */
--text-sm: 12px / 16px;   /* Labels */
--text-xs: 11px / 14px;   /* Helper text */

/* Weights */
--font-regular: 400;
--font-medium: 500;
--font-bold: 700;
--font-black: 900;
```

### Spacing & Layout

```css
/* Grid */
--grid-unit: 8px;
--cell-padding: 16px;
--cell-min-width: 180px;
--cell-max-width: 240px;
--border-width: 1px;
--border-width-thick: 2px;

/* No border radius */
--border-radius: 0px;

/* Table layout */
--header-height: 64px;
--row-min-height: 56px;
--sticky-offset: 0px;
```

### Borders & Lines

```css
/* All borders are solid, no rounded corners */
border: 1px solid var(--base-gray-300);
border: 2px solid var(--base-black); /* For emphasis */

/* Grid lines */
.table-grid {
  border-collapse: collapse;
  border: 2px solid var(--base-black);
}

.table-grid th,
.table-grid td {
  border: 1px solid var(--base-gray-300);
  padding: 16px;
}

/* No box shadows */
box-shadow: none;
```

---

## 🖼️ Page Layout

### Full Page Structure

```
┌─────────────────────────────────────────────────────────────────┐
│ ███ INFRASTRUCTURE PROVISIONING ███              [CLIENT ▼]     │ ← Black header bar
│ [ALL] [OWNED] [NEW]                              Last sync: 2m  │
├─────────────────────────────────────────────────────────────────┤
│ ┏━━━━━━━━┳━━━━━━━┳━━━━━━━┳━━━━━━━┳━━━━━━━━┳━━━━━━━┳━━━━━━━━┓  │
│ ┃☐ SELECT┃ GEN   ┃ PRICE ┃ BUY   ┃ DNS-NS ┃ DNS-OK┃ PROV  ┃  │ ← Bold headers
│ ┃        ┃[CHECK]┃[CHECK]┃[BUY]  ┃[SET]   ┃[VRFY] ┃[ASGN] ┃  │ ← Action buttons
│ ┣━━━━━━━━╋━━━━━━━╋━━━━━━━╋━━━━━━━╋━━━━━━━━╋━━━━━━━╋━━━━━━━━┫  │
│ ┃ [ ]    ┃dom.io ┃$08.99 ┃✓ 02:00┃✓ NS-OK ┃✓✓✓✓  ┃█ENTRA ┃  │ ← Monospace data
│ ┃        ┃OWN 87%┃PB     ┃PB     ┃24:00:00┃ALL-OK┃       ┃  │
│ ┣━━━━━━━━╋━━━━━━━╋━━━━━━━╋━━━━━━━╋━━━━━━━━╋━━━━━━━╋━━━━━━━━┫  │
│ ┃ [✓]    ┃test.io┃$12.49 ┃       ┃        ┃      ┃       ┃  │
│ ┃        ┃NEW 92%┃DY     ┃       ┃        ┃      ┃       ┃  │
│ ┗━━━━━━━━┻━━━━━━━┻━━━━━━━┻━━━━━━━┻━━━━━━━━┻━━━━━━━┻━━━━━━━━┛  │
├─────────────────────────────────────────────────────────────────┤
│ █ 02 SELECTED  █ TOTAL: $021.48  █ 347 DOMAINS  █ SYNC: 00:02m │ ← Status bar
└─────────────────────────────────────────────────────────────────┘
```

### Header Design

```tsx
<header className="bg-black text-white border-b-2 border-black">
  {/* Top bar - Title & Client */}
  <div className="flex justify-between items-center px-6 py-4">
    <div>
      <h1 className="text-2xl font-black tracking-tight uppercase">
        ███ INFRASTRUCTURE PROVISIONING
      </h1>
    </div>
    <div className="flex items-center gap-6">
      <div className="text-sm font-mono">
        LAST SYNC: <span className="font-bold">00:02m AGO</span>
      </div>
      <select className="bg-white text-black border-2 border-black px-4 py-2 font-mono font-bold uppercase">
        <option>CLIENT: SPOUT</option>
        <option>CLIENT: ACME-CORP</option>
      </select>
    </div>
  </div>

  {/* View filters */}
  <div className="flex gap-0 border-t-2 border-white/20">
    <button className="px-6 py-3 bg-white text-black font-bold uppercase text-sm border-r-2 border-white/20">
      [ALL] 347
    </button>
    <button className="px-6 py-3 hover:bg-white/10 text-white font-bold uppercase text-sm border-r-2 border-white/20">
      [OWNED] 142
    </button>
    <button className="px-6 py-3 hover:bg-white/10 text-white font-bold uppercase text-sm">
      [NEW] 205
    </button>
  </div>
</header>
```

---

## 🧩 Waterfall Table Design

### Table Structure (Base44 Grid)

```tsx
<div className="overflow-x-auto bg-white">
  <table className="w-full border-collapse border-2 border-black">
    <thead>
      <tr className="bg-black text-white">
        {/* Checkbox column */}
        <th className="border border-gray-300 p-4 text-left">
          <div className="flex flex-col gap-2">
            <input type="checkbox" className="w-5 h-5 border-2 border-white" />
            <span className="text-xs font-mono uppercase">SELECT</span>
          </div>
        </th>

        {/* Stage columns */}
        {STAGES.map(stage => (
          <th key={stage.id} className="border border-gray-300 p-4 min-w-[180px]">
            <div className="flex flex-col gap-2">
              {/* Stage label - bold, uppercase */}
              <div className="font-bold text-sm uppercase tracking-wide">
                {stage.shortLabel}
              </div>

              {/* Count badge */}
              <div className="font-mono text-xs">
                [{stage.count.toString().padStart(3, '0')}]
              </div>

              {/* Bulk action button */}
              {stage.bulkAction && (
                <button className="bg-white text-black border-2 border-white px-3 py-1 font-bold text-xs uppercase hover:bg-gray-200 disabled:opacity-50 disabled:cursor-not-allowed">
                  [{stage.bulkAction}]
                </button>
              )}
            </div>
          </th>
        ))}
      </tr>
    </thead>

    <tbody>
      {domains.map((domain, idx) => (
        <tr
          key={domain.id}
          className={`
            border-b border-gray-300
            ${selectedIds.has(domain.id) ? 'bg-gray-100' : 'bg-white'}
            hover:bg-gray-50
          `}
        >
          {/* Checkbox */}
          <td className="border-r border-gray-300 p-4">
            <input
              type="checkbox"
              checked={selectedIds.has(domain.id)}
              className="w-5 h-5 border-2 border-black"
            />
          </td>

          {/* Stage cells */}
          <td className="border-r border-gray-300 p-4">
            <GeneratedCell domain={domain} />
          </td>
          {/* ... remaining cells ... */}
        </tr>
      ))}
    </tbody>
  </table>
</div>
```

---

## 🎯 Stage Cell Designs (Base44 Style)

### Cell 1: Generated Cell

**Visual Design:**
```
┌──────────────────────┐
│ EXAMPLE.IO           │ ← Bold, uppercase domain
│ [OWN] [DEP]          │ ← Solid badges
│ SCORE: 87%           │ ← Monospace
│ AGO: 02:15:30        │ ← Precise time
└──────────────────────┘
```

**Component:**
```tsx
<div className="space-y-2 font-mono text-sm">
  {/* Domain name - bold, uppercase */}
  <div className="font-bold text-base uppercase tracking-tight">
    {domain.name}
  </div>

  {/* Status badges - solid blocks */}
  <div className="flex gap-1">
    {domain.owned && (
      <span className="bg-black text-white px-2 py-0.5 text-xs font-bold uppercase">
        [OWN]
      </span>
    )}
    {domain.deployed && (
      <span className="bg-gray-800 text-white px-2 py-0.5 text-xs font-bold uppercase">
        [DEP]
      </span>
    )}
  </div>

  {/* Score - monospace, bold */}
  {domain.legitimacyScore && (
    <div className="text-xs">
      SCORE: <span className="font-bold">{(domain.legitimacyScore * 100).toFixed(0)}%</span>
    </div>
  )}

  {/* Time - precise format */}
  <div className="text-xs text-gray-600">
    AGO: {formatPreciseTime(domain.createdAt)}
  </div>
</div>

// Helper function
function formatPreciseTime(date: Date): string {
  const diff = Date.now() - date.getTime();
  const hours = Math.floor(diff / 3600000);
  const minutes = Math.floor((diff % 3600000) / 60000);
  const seconds = Math.floor((diff % 60000) / 1000);
  return `${hours.toString().padStart(2, '0')}:${minutes.toString().padStart(2, '0')}:${seconds.toString().padStart(2, '0')}`;
}
```

**Empty State:**
```tsx
<div className="text-gray-400 text-xs font-mono uppercase">
  [NOT-GENERATED]
</div>
```

---

### Cell 2: Priced Cell

**Visual Design:**
```
┌──────────────────────┐
│ $008.99              │ ← Monospace, padded
│ [PORKBUN]            │ ← Provider badge
│ STATUS: VALID        │ ← Status text
│ CHK: 02:15:30        │ ← Time since check
└──────────────────────┘
```

**Component:**
```tsx
<div className="space-y-2 font-mono text-sm">
  {/* Price - large, bold, padded */}
  {domain.cachedPrice && (
    <div className="font-bold text-base">
      ${domain.cachedPrice.toFixed(2).padStart(6, '0')}
    </div>
  )}

  {/* Provider badge - solid black */}
  {domain.selectedProvider && (
    <span className="bg-black text-white px-2 py-0.5 text-xs font-bold uppercase">
      [{domain.selectedProvider}]
    </span>
  )}

  {/* Status indicator */}
  <div className={`text-xs ${
    domain.priceStatus === 'valid' ? 'text-green-600' :
    domain.priceStatus === 'stale' ? 'text-orange-600' :
    'text-red-600'
  }`}>
    STATUS: <span className="font-bold uppercase">{domain.priceStatus}</span>
  </div>

  {/* Warning for stale */}
  {domain.priceStatus === 'stale' && (
    <div className="text-xs text-orange-600 font-bold">
      ! RECHECK REQUIRED
    </div>
  )}

  {/* Time since check */}
  {domain.priceCheckedAt && (
    <div className="text-xs text-gray-600">
      CHK: {formatPreciseTime(domain.priceCheckedAt)}
    </div>
  )}
</div>
```

**Empty State:**
```tsx
<div className="space-y-2">
  <div className="text-gray-400 text-xs font-mono uppercase">
    [NO-PRICE]
  </div>
  <button className="bg-black text-white px-2 py-1 text-xs font-bold uppercase hover:bg-gray-800">
    [CHECK]
  </button>
</div>
```

---

### Cell 3: Purchased Cell

**Visual Design:**
```
┌──────────────────────┐
│ ✓ PURCHASED          │ ← Bold status
│ [PORKBUN]            │ ← Provider
│ TIME: 02:15:30       │ ← Time since purchase
│ JOB: COMPLETE        │ ← Job status
└──────────────────────┘
```

**Component:**
```tsx
<div className="space-y-2 font-mono text-sm">
  {/* Status - bold with checkmark */}
  <div className="font-bold text-green-600 flex items-center gap-1">
    <span>✓</span>
    <span className="uppercase">PURCHASED</span>
  </div>

  {/* Provider badge */}
  {domain.selectedProvider && (
    <span className="bg-black text-white px-2 py-0.5 text-xs font-bold uppercase">
      [{domain.selectedProvider}]
    </span>
  )}

  {/* Job status if in progress */}
  {domain.purchaseJobStatus !== 'completed' && (
    <div className="text-xs text-blue-600 font-bold">
      JOB: {domain.purchaseJobStatus.toUpperCase()}...
    </div>
  )}

  {/* Time since purchase */}
  {domain.purchasedAt && (
    <div className="text-xs text-gray-600">
      TIME: {formatPreciseTime(domain.purchasedAt)}
    </div>
  )}
</div>
```

**Empty State:**
```tsx
<div className="space-y-2">
  <div className="text-gray-400 text-xs font-mono uppercase">
    [NOT-PURCHASED]
  </div>
  {domain.cachedPrice && (
    <button className="bg-black text-white px-2 py-1 text-xs font-bold uppercase hover:bg-gray-800">
      [BUY ${domain.cachedPrice.toFixed(2)}]
    </button>
  )}
</div>
```

---

### Cell 4: DNS Moved Cell

**Visual Design:**
```
┌──────────────────────┐
│ ✓ NS-UPDATED         │ ← Status
│ ns1.dnsimple.com     │ ← First NS (truncated)
│ ns2.dnsimple-e...    │ ← Second NS
│ PROP: 24:00:00       │ ← Propagation time
└──────────────────────┘
```

**Component:**
```tsx
<div className="space-y-2 font-mono text-sm">
  {/* Status */}
  <div className="font-bold text-blue-600 flex items-center gap-1">
    <span>✓</span>
    <span className="uppercase">NS-UPDATED</span>
  </div>

  {/* Nameservers - truncated, monospace */}
  {domain.currentNameservers && (
    <div className="text-xs text-gray-700 space-y-0.5">
      {domain.currentNameservers.slice(0, 2).map((ns, i) => (
        <div key={i} className="truncate">{ns}</div>
      ))}
      {domain.currentNameservers.length > 2 && (
        <div className="text-gray-500">+{domain.currentNameservers.length - 2} MORE</div>
      )}
    </div>
  )}

  {/* Propagation status */}
  <div className={`text-xs font-bold uppercase ${
    domain.dnsMigrationStatus === 'propagated' ? 'text-green-600' :
    domain.dnsMigrationStatus === 'propagating' ? 'text-blue-600' :
    'text-gray-500'
  }`}>
    {domain.dnsMigrationStatus === 'propagated' ? '✓ PROPAGATED' :
     domain.dnsMigrationStatus === 'propagating' ? '⧗ PROPAGATING' :
     '○ NOT-SET'}
  </div>

  {/* Time since update */}
  {domain.nameserversUpdatedAt && (
    <div className="text-xs text-gray-600">
      PROP: {formatPreciseTime(domain.nameserversUpdatedAt)}
    </div>
  )}
</div>
```

---

### Cell 5: DNS Verified Cell

**Visual Design:**
```
┌──────────────────────┐
│ ✓✓✓✓ ALL-OK          │ ← Compact checkmarks
│ SPF  : ✓             │ ← Record list
│ DKIM : ✓             │
│ DMARC: ✓             │
│ MX   : ✓             │
└──────────────────────┘
```

**Component:**
```tsx
<div className="space-y-2 font-mono text-sm">
  {/* Overall status - compact */}
  <div className={`font-bold text-xs uppercase ${
    domain.dnsRecordsConfigured ? 'text-green-600' : 'text-orange-600'
  }`}>
    {domain.dnsRecordsConfigured ? '✓✓✓✓ ALL-OK' : '✗ INCOMPLETE'}
  </div>

  {/* Record checklist - aligned */}
  <div className="space-y-0.5 text-xs">
    <DNSRecord label="SPF  " ok={domain.spfConfigured} />
    <DNSRecord label="DKIM " ok={domain.dkimConfigured} />
    <DNSRecord label="DMARC" ok={domain.dmarcConfigured} />
    <DNSRecord label="MX   " ok={domain.mxConfigured} />
  </div>

  {/* Verify button if incomplete */}
  {!domain.dnsRecordsConfigured && (
    <button className="bg-black text-white px-2 py-1 text-xs font-bold uppercase hover:bg-gray-800 w-full">
      [VERIFY]
    </button>
  )}
</div>

// Helper component
function DNSRecord({ label, ok }: { label: string; ok: boolean }) {
  return (
    <div className={ok ? 'text-green-600' : 'text-gray-400'}>
      {label}: {ok ? '✓' : '○'}
    </div>
  );
}
```

---

### Cell 6: Provider Assigned Cell

**Visual Design:**
```
┌──────────────────────┐
│ █ ENTRA              │ ← Solid bar indicator
│ MICROSOFT            │ ← Provider name
│ BATCH: 02            │ ← Domains per order
└──────────────────────┘
```

**Component:**
```tsx
<div className="space-y-2 font-mono text-sm">
  {domain.assignedProvider ? (
    <>
      {/* Provider indicator - solid bar */}
      <div className="flex items-center gap-2">
        <div className={`w-1 h-8 ${
          domain.assignedProvider === 'entra' ? 'bg-blue-600' : 'bg-red-600'
        }`} />
        <div className="font-bold uppercase">
          {domain.assignedProvider === 'entra' ? '█ ENTRA' : '█ GOOGLE'}
        </div>
      </div>

      {/* Provider full name */}
      <div className="text-xs text-gray-700">
        {domain.assignedProvider === 'entra' ? 'MICROSOFT' : 'WORKSPACE'}
      </div>

      {/* Batch size */}
      <div className="text-xs text-gray-600">
        BATCH: {domain.assignedProvider === 'entra' ? '02' : '05'}
      </div>
    </>
  ) : (
    <>
      <div className="text-gray-400 text-xs uppercase">
        [NO-PROVIDER]
      </div>
      <div className="flex gap-1">
        <button
          onClick={() => handleAssign('entra')}
          className="flex-1 bg-blue-600 text-white px-2 py-1 text-xs font-bold uppercase hover:bg-blue-700"
        >
          [E]
        </button>
        <button
          onClick={() => handleAssign('google')}
          className="flex-1 bg-red-600 text-white px-2 py-1 text-xs font-bold uppercase hover:bg-red-700"
        >
          [G]
        </button>
      </div>
    </>
  )}
</div>
```

---

### Cell 7: HyperTide Ordered Cell

**Visual Design:**
```
┌──────────────────────┐
│ ORDER: #A1B2C3       │ ← Order ID
│ [████████░░] 80%     │ ← ASCII progress
│ STEP: 04/05          │ ← Step counter
│ TIME: 01:23:45       │ ← Elapsed time
└──────────────────────┘
```

**Component:**
```tsx
<div className="space-y-2 font-mono text-sm">
  {domain.hyperTideOrderJobId ? (
    <>
      {/* Order ID */}
      <div className="font-bold text-xs">
        ORDER: #{domain.hyperTideOrderJobId.slice(0, 6).toUpperCase()}
      </div>

      {/* Progress bar - ASCII style */}
      {domain.hyperTideOrderStatus !== 'completed' && (
        <div className="space-y-1">
          <div className="text-xs text-blue-600">
            [{getASCIIProgress(domain.hyperTideProgress)}] {domain.hyperTideProgress}%
          </div>
          <div className="text-xs text-gray-600">
            STEP: {domain.hyperTideCurrentStep}
          </div>
        </div>
      )}

      {/* Completed */}
      {domain.hyperTideOrderStatus === 'completed' && (
        <div className="text-xs text-green-600 font-bold">
          ✓ COMPLETE
        </div>
      )}

      {/* Elapsed time */}
      <div className="text-xs text-gray-600">
        TIME: {formatPreciseTime(domain.hyperTideOrderedAt)}
      </div>
    </>
  ) : (
    <div className="text-gray-400 text-xs uppercase">
      [NOT-ORDERED]
    </div>
  )}
</div>

// ASCII progress bar
function getASCIIProgress(percent: number): string {
  const filled = Math.floor(percent / 10);
  const empty = 10 - filled;
  return '█'.repeat(filled) + '░'.repeat(empty);
}
```

---

### Cell 8: Provisioned Cell

**Visual Design:**
```
┌──────────────────────┐
│ ⧗ PROVISIONING       │ ← Status
│ HYPERTIDE            │ ← Vendor name
│ ETA: ~02:00:00       │ ← Estimated time
└──────────────────────┘
```

**Component:**
```tsx
<div className="space-y-2 font-mono text-sm">
  {/* Status */}
  {domain.provisioningStatus === 'synced' ? (
    <div className="font-bold text-green-600 uppercase">
      ✓ SYNCED
    </div>
  ) : domain.provisioningStatus === 'awaiting_sync' ? (
    <div className="font-bold text-blue-600 uppercase">
      ⧗ AWAIT-SYNC
    </div>
  ) : domain.provisioningStatus === 'provisioning' ? (
    <div className="font-bold text-orange-600 uppercase">
      ⧗ PROVISIONING
    </div>
  ) : (
    <div className="text-gray-400 text-xs uppercase">
      [NOT-STARTED]
    </div>
  )}

  {/* Vendor note */}
  {domain.provisioningStatus === 'provisioning' && (
    <>
      <div className="text-xs text-gray-700">
        HYPERTIDE
      </div>
      <div className="text-xs text-gray-600">
        ETA: ~02:00:00
      </div>
    </>
  )}
</div>
```

---

### Cell 9: Synced Cell

**Visual Design:**
```
┌──────────────────────┐
│ 100/100 ✓            │ ← Count
│ [██████████] 100%    │ ← ASCII progress
│ SYNC: 00:05:30       │ ← Last sync
└──────────────────────┘
```

**Component:**
```tsx
<div className="space-y-2 font-mono text-sm">
  {domain.syncedInboxCount > 0 ? (
    <>
      {/* Count - bold */}
      <div className="font-bold text-base">
        {domain.syncedInboxCount.toString().padStart(3, '0')}/
        {domain.expectedInboxCount.toString().padStart(3, '0')}
        {domain.syncedInboxCount === domain.expectedInboxCount ? ' ✓' : ''}
      </div>

      {/* ASCII progress bar */}
      <div className={`text-xs ${
        domain.syncedInboxCount === domain.expectedInboxCount
          ? 'text-green-600'
          : 'text-blue-600'
      }`}>
        [{getASCIIProgress((domain.syncedInboxCount / domain.expectedInboxCount) * 100)}]{' '}
        {Math.floor((domain.syncedInboxCount / domain.expectedInboxCount) * 100)}%
      </div>

      {/* Last sync time */}
      {domain.lastInboxSyncedAt && (
        <div className="text-xs text-gray-600">
          SYNC: {formatPreciseTime(domain.lastInboxSyncedAt)}
        </div>
      )}
    </>
  ) : (
    <div className="text-gray-400 text-xs uppercase">
      [NO-INBOXES]
    </div>
  )}
</div>
```

---

## 🎯 Action Buttons (Base44 Style)

### Primary Action Button

```tsx
<button className="
  bg-black text-white
  border-2 border-black
  px-4 py-2
  font-bold uppercase text-sm
  hover:bg-gray-800
  disabled:bg-gray-300 disabled:text-gray-500 disabled:cursor-not-allowed
  transition-colors
">
  [ACTION]
</button>
```

### Secondary Action Button

```tsx
<button className="
  bg-white text-black
  border-2 border-black
  px-4 py-2
  font-bold uppercase text-sm
  hover:bg-gray-100
">
  [CANCEL]
</button>
```

### Destructive Action Button

```tsx
<button className="
  bg-red-600 text-white
  border-2 border-red-800
  px-4 py-2
  font-bold uppercase text-sm
  hover:bg-red-700
">
  [DELETE]
</button>
```

### Inline Action (in cells)

```tsx
<button className="
  bg-black text-white
  px-2 py-1
  font-bold uppercase text-xs
  hover:bg-gray-800
  w-full
">
  [CHECK]
</button>
```

---

## 📊 Footer Bar (Base44 Style)

```tsx
<footer className="sticky bottom-0 bg-black text-white border-t-2 border-black">
  <div className="flex items-center h-12 px-6 font-mono text-sm divide-x-2 divide-white/20">
    {/* Selection count */}
    <div className="pr-6 font-bold">
      █ {selectedCount.toString().padStart(2, '0')} SELECTED
    </div>

    {/* Total cost */}
    {selectedCount > 0 && (
      <div className="px-6 font-bold">
        █ TOTAL: ${totalCost.toFixed(2).padStart(7, '0')}
      </div>
    )}

    {/* Total domains */}
    <div className="px-6">
      █ {totalDomains.toString().padStart(3, '0')} DOMAINS
    </div>

    {/* Sync status */}
    <div className="px-6">
      █ SYNC: {formatPreciseTime(lastSync)}
    </div>

    {/* Spacer */}
    <div className="flex-1" />

    {/* Clear button */}
    {selectedCount > 0 && (
      <div className="pl-6">
        <button
          onClick={clearSelection}
          className="bg-white text-black px-3 py-1 font-bold text-xs uppercase hover:bg-gray-200"
        >
          [CLEAR]
        </button>
      </div>
    )}
  </div>
</footer>
```

---

## 🔲 Modals (Base44 Style)

### Modal Container

```tsx
<div className="fixed inset-0 bg-black/80 flex items-center justify-center z-50">
  <div className="bg-white border-4 border-black w-full max-w-2xl max-h-[80vh] flex flex-col">
    {/* Header - black bar */}
    <div className="bg-black text-white px-6 py-4 flex justify-between items-center">
      <h2 className="font-black text-xl uppercase tracking-tight">
        ███ BULK PURCHASE
      </h2>
      <button onClick={onClose} className="text-white hover:text-gray-300 text-2xl font-bold">
        [×]
      </button>
    </div>

    {/* Content - white background, scrollable */}
    <div className="flex-1 overflow-y-auto p-6 font-mono">
      {/* Modal content here */}
    </div>

    {/* Footer - action buttons */}
    <div className="border-t-2 border-black p-6 flex gap-4 justify-end">
      <button className="bg-white text-black border-2 border-black px-6 py-2 font-bold uppercase">
        [CANCEL]
      </button>
      <button className="bg-black text-white border-2 border-black px-6 py-2 font-bold uppercase hover:bg-gray-800">
        [CONFIRM]
      </button>
    </div>
  </div>
</div>
```

### Bulk Purchase Modal (Base44)

```tsx
<Modal title="BULK PURCHASE" onClose={onClose}>
  {/* Cost summary - large, bold */}
  <div className="bg-gray-100 border-2 border-black p-6 mb-6">
    <div className="text-sm text-gray-600 uppercase mb-2">TOTAL COST</div>
    <div className="font-black text-4xl font-mono">
      ${totalCost.toFixed(2)}
    </div>
    <div className="text-sm text-gray-600 uppercase mt-2">
      {selectedDomains.length} DOMAINS
    </div>
  </div>

  {/* Provider selection */}
  <div className="mb-6">
    <div className="text-sm font-bold uppercase mb-2">PROVIDER SELECTION</div>
    <div className="space-y-2">
      <label className="flex items-center gap-2 cursor-pointer">
        <input type="radio" name="provider" value="auto" defaultChecked />
        <span className="font-mono text-sm">[AUTO] LOWEST PRICE (RECOMMENDED)</span>
      </label>
      <label className="flex items-center gap-2 cursor-pointer">
        <input type="radio" name="provider" value="porkbun" />
        <span className="font-mono text-sm">[PORKBUN] ONLY</span>
      </label>
      <label className="flex items-center gap-2 cursor-pointer">
        <input type="radio" name="provider" value="dynadot" />
        <span className="font-mono text-sm">[DYNADOT] ONLY</span>
      </label>
    </div>
  </div>

  {/* Domain list - data table */}
  <div className="border-2 border-black">
    <table className="w-full font-mono text-xs">
      <thead className="bg-black text-white">
        <tr>
          <th className="text-left p-2 font-bold uppercase">DOMAIN</th>
          <th className="text-right p-2 font-bold uppercase">PRICE</th>
          <th className="text-left p-2 font-bold uppercase">PROVIDER</th>
        </tr>
      </thead>
      <tbody className="divide-y divide-gray-300">
        {selectedDomains.map((domain, idx) => (
          <tr key={domain.id} className={idx % 2 === 0 ? 'bg-white' : 'bg-gray-50'}>
            <td className="p-2">{domain.name}</td>
            <td className="p-2 text-right font-bold">
              ${domain.price.toFixed(2).padStart(6, '0')}
            </td>
            <td className="p-2 uppercase">{domain.provider}</td>
          </tr>
        ))}
      </tbody>
    </table>
  </div>

  {/* Warning */}
  <div className="mt-6 bg-red-100 border-2 border-red-600 p-4">
    <div className="font-bold text-sm text-red-900 mb-1">! WARNING</div>
    <div className="text-xs text-red-800">
      THIS ACTION CANNOT BE UNDONE. CHARGES WILL BE APPLIED IMMEDIATELY.
    </div>
  </div>
</Modal>
```

---

## 🎨 Loading States (Base44)

### Page Loading

```tsx
<div className="flex items-center justify-center h-screen bg-white">
  <div className="text-center font-mono">
    <div className="text-4xl font-black mb-4 animate-pulse">
      ███ LOADING...
    </div>
    <div className="text-sm text-gray-600 uppercase">
      FETCHING WATERFALL DATA
    </div>
  </div>
</div>
```

### Cell Loading

```tsx
<div className="font-mono text-xs text-gray-500 uppercase animate-pulse">
  [LOADING...]
</div>
```

### Progress Indicator (ASCII)

```tsx
<div className="font-mono text-xs">
  <div className="text-blue-600">
    [{getASCIIProgress(progress)}] {progress}%
  </div>
  <div className="text-gray-600 mt-1">
    {currentItem}/{totalItems} COMPLETE
  </div>
</div>
```

---

## 🚨 Error States (Base44)

### Page Error

```tsx
<div className="flex items-center justify-center h-screen bg-white">
  <div className="text-center font-mono max-w-md">
    <div className="text-6xl font-black mb-4 text-red-600">
      ✗
    </div>
    <div className="text-2xl font-bold uppercase mb-2">
      ERROR
    </div>
    <div className="text-sm text-gray-700 mb-6 bg-red-50 border-2 border-red-600 p-4">
      {error.message}
    </div>
    <button className="bg-black text-white px-6 py-3 font-bold uppercase hover:bg-gray-800">
      [RETRY]
    </button>
  </div>
</div>
```

### Cell Error

```tsx
<div className="space-y-2">
  <div className="text-red-600 font-bold text-xs uppercase">
    ✗ ERROR
  </div>
  <div className="text-xs text-red-700 bg-red-50 border border-red-300 p-2">
    {error.message}
  </div>
  <button className="bg-black text-white px-2 py-1 text-xs font-bold uppercase hover:bg-gray-800 w-full">
    [RETRY]
  </button>
</div>
```

### Toast Notifications (Base44)

```tsx
// Success
<div className="bg-green-600 text-white border-2 border-green-800 px-4 py-3 font-mono font-bold">
  ✓ 15 DOMAINS PURCHASED SUCCESSFULLY
</div>

// Error
<div className="bg-red-600 text-white border-2 border-red-800 px-4 py-3 font-mono font-bold">
  ✗ PRICE CHECK FAILED FOR 3 DOMAINS
</div>

// Warning
<div className="bg-orange-500 text-white border-2 border-orange-700 px-4 py-3 font-mono font-bold">
  ! 2 DOMAINS HAVE STALE PRICES
</div>

// Info
<div className="bg-blue-600 text-white border-2 border-blue-800 px-4 py-3 font-mono font-bold">
  ⧗ DNS VERIFICATION IN PROGRESS...
</div>
```

---

## 📱 Responsive (Mobile - Base44)

### Mobile Card View

```tsx
<div className="p-4 space-y-4 bg-white">
  {domains.map(domain => (
    <div key={domain.id} className="border-2 border-black bg-white">
      {/* Header */}
      <div className="bg-black text-white p-4 flex justify-between items-center">
        <div className="font-bold uppercase font-mono">{domain.name}</div>
        <input type="checkbox" className="w-5 h-5 border-2 border-white" />
      </div>

      {/* Stage progress - ASCII */}
      <div className="p-4 bg-gray-50 border-b-2 border-black">
        <div className="font-mono text-xs mb-2">
          STAGE: {domain.currentStage}/09
        </div>
        <div className="font-mono text-sm text-blue-600">
          [{getASCIIProgress((domain.currentStage / 9) * 100)}]
          {Math.floor((domain.currentStage / 9) * 100)}%
        </div>
        <div className="font-mono text-xs text-gray-600 mt-1 uppercase">
          {STAGE_LABELS[domain.currentStage]}
        </div>
      </div>

      {/* Current stage details */}
      <div className="p-4 border-b border-gray-300">
        {renderCurrentStageCell(domain)}
      </div>

      {/* Actions */}
      <div className="p-4 flex gap-2">
        {getAvailableActions(domain).map(action => (
          <button
            key={action.id}
            className="flex-1 bg-black text-white px-3 py-2 font-bold text-xs uppercase hover:bg-gray-800"
          >
            [{action.label}]
          </button>
        ))}
      </div>
    </div>
  ))}
</div>
```

---

## 🎯 Summary

### Base44 Design Characteristics

✅ **Brutalist Typography** - JetBrains Mono for data, bold uppercase labels
✅ **High Contrast** - Black text on white, bold accent colors for status
✅ **Data Density** - Compact cells, monospace alignment, precise timestamps
✅ **Zero Border Radius** - All elements are rectangular, sharp corners
✅ **No Shadows** - Flat design with solid 2px borders
✅ **ASCII Progress Bars** - █░ characters instead of rounded progress bars
✅ **Monospace Numbers** - Perfect column alignment with padded values
✅ **Solid Color Blocks** - Black badges, colored status bars
✅ **Direct Actions** - No nested menus, immediate button access
✅ **Functional Color** - Color only indicates status/meaning, not decoration

### Component Hierarchy

```
InfrastructurePage (Base44)
├── Header (Black bar with white text)
│   ├── Title (███ INFRASTRUCTURE PROVISIONING)
│   ├── ViewTabs ([ALL] [OWNED] [NEW])
│   └── ClientSelector (Border-2 dropdown)
├── WaterfallTable (Border-2 grid)
│   ├── Header (Black background)
│   │   └── StageColumns (Bold uppercase, [ACTION] buttons)
│   └── Body (White/gray striped rows)
│       └── Cells (Monospace data, ASCII progress)
├── Footer (Black bar, monospace stats)
└── Modals (Border-4, black header)
```

### Design Tokens

- **Fonts:** JetBrains Mono (data), Inter (UI)
- **Colors:** Black/white base, functional status colors only
- **Borders:** 1px grid, 2px emphasis, 4px modals
- **Radius:** 0px everywhere
- **Spacing:** 8px grid system
- **Typography:** Bold uppercase labels, monospace data

---

**Base44 aesthetic complete. Ready for Phase 2 implementation with brutalist, data-dense design system.**
