# Infrastructure Provisioning SPA - Modular Component Design

**Date:** 2026-02-25
**Purpose:** Modular, maintainable component architecture following existing codebase patterns

---

## 🎯 Design Philosophy

### Principles:
1. **Single Responsibility** - Each component does ONE thing well
2. **Composable** - Small components combine into larger features
3. **Testable** - Easy to unit test in isolation
4. **Reusable** - Components work across different contexts
5. **Type-Safe** - Full TypeScript coverage

### Follows Existing Patterns:
- ✅ Zustand for global state (`infrastructureStore` pattern)
- ✅ React hooks for local state
- ✅ Shadcn/ui components for primitives
- ✅ API client pattern (`lib/api.ts`)
- ✅ Toast notifications for user feedback
- ✅ Lazy loading with tracking sets

---

## 📁 File Structure

```
app/clients/[clientId]/infrastructure/
└── page.tsx                                    ← Main page wrapper

components/infrastructure/
├── WaterfallTable/
│   ├── WaterfallTable.tsx                     ← Main table container
│   ├── WaterfallHeader.tsx                    ← Column headers with bulk actions
│   ├── WaterfallRow.tsx                       ← Single domain row
│   ├── WaterfallCell.tsx                      ← Base cell wrapper (handles loading, error states)
│   └── index.ts
│
├── cells/
│   ├── GeneratedCell/
│   │   ├── GeneratedCell.tsx                  ← Domain name, legitimacy score
│   │   ├── useGeneratedCell.ts                ← Cell-specific logic
│   │   └── index.ts
│   ├── PricedCell/
│   │   ├── PricedCell.tsx                     ← Dual-provider pricing display
│   │   ├── usePricedCell.ts                   ← Price fetching logic
│   │   └── index.ts
│   ├── PurchasedCell/
│   │   ├── PurchasedCell.tsx                  ← Purchase status, date, cost
│   │   ├── usePurchasedCell.ts
│   │   └── index.ts
│   ├── DNSMovedCell/
│   │   ├── DNSMovedCell.tsx                   ← Nameserver migration status
│   │   ├── useDNSMovedCell.ts                 ← Timer logic for propagation
│   │   └── index.ts
│   ├── DNSVerifiedCell/
│   │   ├── DNSVerifiedCell.tsx                ← DNS records checklist
│   │   ├── DNSRecordChecklist.tsx             ← Expandable SPF/DKIM/DMARC/MX list
│   │   ├── useDNSVerifiedCell.ts
│   │   └── index.ts
│   ├── ProviderAssignedCell/
│   │   ├── ProviderAssignedCell.tsx           ← Entra/Google badge
│   │   ├── ProviderBadge.tsx                  ← Reusable badge component
│   │   └── index.ts
│   ├── HyperTideOrderedCell/
│   │   ├── HyperTideOrderedCell.tsx           ← Order status, progress
│   │   ├── OrderProgressBar.tsx               ← Progress visualization
│   │   ├── useHyperTideOrderCell.ts           ← Polling logic
│   │   └── index.ts
│   ├── ProvisionedCell/
│   │   ├── ProvisionedCell.tsx                ← Provisioning status, ETA
│   │   ├── useProvisionedCell.ts
│   │   └── index.ts
│   ├── SyncedCell/
│   │   ├── SyncedCell.tsx                     ← Inbox count, sync status
│   │   ├── useSyncedCell.ts
│   │   └── index.ts
│   └── index.ts
│
├── modals/
│   ├── BulkGenerateModal/
│   │   ├── BulkGenerateModal.tsx              ← Generate N domains
│   │   ├── PackageProgressBar.tsx             ← Visual package fulfillment
│   │   └── index.ts
│   ├── BulkPriceCheckModal/
│   │   ├── BulkPriceCheckModal.tsx            ← Check prices for selected
│   │   ├── PriceCheckProgress.tsx             ← Per-domain progress
│   │   └── index.ts
│   ├── BulkPurchaseModal/
│   │   ├── BulkPurchaseModal.tsx              ← Purchase confirmation + progress
│   │   ├── CostSummary.tsx                    ← Total cost breakdown
│   │   ├── PurchaseProgress.tsx               ← Per-domain purchase status
│   │   └── index.ts
│   ├── BulkDNSSetModal/
│   │   ├── BulkDNSSetModal.tsx                ← Set nameservers to DNSimple
│   │   ├── DNSMigrationProgress.tsx           ← Per-domain NS update status
│   │   └── index.ts
│   ├── BulkDNSVerifyModal/
│   │   ├── BulkDNSVerifyModal.tsx             ← Verify DNS records
│   │   ├── DNSVerificationProgress.tsx        ← Per-domain verification results
│   │   └── index.ts
│   ├── ProviderAssignmentModal/
│   │   ├── ProviderAssignmentModal.tsx        ← Assign Entra/Google
│   │   ├── ProviderSelector.tsx               ← Radio buttons for provider
│   │   ├── OrderValidation.tsx                ← Show valid order groupings
│   │   └── index.ts
│   ├── HyperTideOrderModal/
│   │   ├── HyperTideOrderModal.tsx            ← Create HyperTide order
│   │   ├── OrderConfigForm.tsx                ← Forwarding domain, company name, etc.
│   │   ├── SenderNamesInput.tsx               ← Dynamic sender name list
│   │   ├── OrderSummary.tsx                   ← Expected output summary
│   │   └── index.ts
│   ├── OrderTrackingModal/
│   │   ├── OrderTrackingModal.tsx             ← Track HyperTide order progress
│   │   ├── OrderTimeline.tsx                  ← Step-by-step progress visualization
│   │   ├── useOrderPolling.ts                 ← Real-time polling
│   │   └── index.ts
│   └── InboxListModal/
│       ├── InboxListModal.tsx                 ← View synced inboxes
│       ├── InboxTable.tsx                     ← Filterable inbox list
│       └── index.ts
│
├── filters/
│   ├── ViewSelector.tsx                       ← Owned/Candidates/Pipeline/All tabs
│   ├── ProviderFilter.tsx                     ← Filter by Entra/Google
│   ├── StageFilter.tsx                        ← Filter by current stage
│   └── index.ts
│
├── bulk-actions/
│   ├── BulkActionButton.tsx                   ← Reusable bulk action button
│   ├── BulkActionDropdown.tsx                 ← Dropdown with multiple actions
│   └── index.ts
│
└── index.ts

hooks/infrastructure/
├── useWaterfallData.ts                        ← Fetch waterfall data
├── useSelection.ts                            ← Manage checkbox selection
├── useBulkActions.ts                          ← Coordinate bulk operations
├── usePolling.ts                              ← Generic polling with timeout
├── useLazyLoading.ts                          ← Lazy load with tracking
├── useDomainStage.ts                          ← Calculate current stage
└── index.ts

lib/api/infrastructure.ts                      ← API client for waterfall endpoints
lib/stores/waterfallStore.ts                   ← Zustand store for waterfall state
lib/types/infrastructure.ts                    ← TypeScript types
```

---

## 🧩 Component Breakdown

### 1. Core Components

#### **WaterfallTable.tsx** (Main Container)

**Responsibility:** Orchestrate table rendering, selection, filtering

```typescript
interface WaterfallTableProps {
  workspaceId: string;
  view: 'owned' | 'candidates' | 'pipeline' | 'all';
  filters: {
    provider?: 'entra' | 'google';
    stage?: number;
    search?: string;
  };
}

export function WaterfallTable({ workspaceId, view, filters }: WaterfallTableProps) {
  const { data, loading, error, refresh } = useWaterfallData(workspaceId, view, filters);
  const { selectedDomains, selectDomain, selectAll, clearSelection } = useSelection();

  return (
    <div className="relative">
      {/* Bulk action toolbar */}
      <BulkActionToolbar
        selectedCount={selectedDomains.size}
        onClearSelection={clearSelection}
      />

      {/* Waterfall table */}
      <Table>
        <WaterfallHeader
          columns={COLUMNS}
          selectedCount={selectedDomains.size}
          totalCount={data?.domains.length || 0}
          onSelectAll={selectAll}
        />
        <TableBody>
          {data?.domains.map((domain) => (
            <WaterfallRow
              key={domain.domain_id}
              domain={domain}
              selected={selectedDomains.has(domain.domain_id)}
              onSelect={() => selectDomain(domain.domain_id)}
              onRefresh={refresh}
            />
          ))}
        </TableBody>
      </Table>
    </div>
  );
}
```

**Dependencies:**
- `useWaterfallData` - Data fetching
- `useSelection` - Selection state
- `WaterfallHeader` - Column headers
- `WaterfallRow` - Domain rows

**Exports:** `WaterfallTable`

---

#### **WaterfallRow.tsx** (Single Domain Row)

**Responsibility:** Render one domain across all 9 stages

```typescript
interface WaterfallRowProps {
  domain: WaterfallDomain;
  selected: boolean;
  onSelect: () => void;
  onRefresh: () => void;
}

export function WaterfallRow({ domain, selected, onSelect, onRefresh }: WaterfallRowProps) {
  return (
    <TableRow className={selected ? 'bg-blue-50' : ''}>
      {/* Selection checkbox */}
      <TableCell>
        <Checkbox checked={selected} onCheckedChange={onSelect} />
      </TableCell>

      {/* Stage 1: Generated */}
      <TableCell>
        <GeneratedCell domain={domain} />
      </TableCell>

      {/* Stage 2: Priced */}
      <TableCell>
        <PricedCell domain={domain} onRefresh={onRefresh} />
      </TableCell>

      {/* Stage 3: Purchased */}
      <TableCell>
        <PurchasedCell domain={domain} />
      </TableCell>

      {/* Stage 4: DNS Moved */}
      <TableCell>
        <DNSMovedCell domain={domain} />
      </TableCell>

      {/* Stage 5: DNS Verified */}
      <TableCell>
        <DNSVerifiedCell domain={domain} onRefresh={onRefresh} />
      </TableCell>

      {/* Stage 6: Provider Assigned */}
      <TableCell>
        <ProviderAssignedCell domain={domain} />
      </TableCell>

      {/* Stage 7: HyperTide Ordered */}
      <TableCell>
        <HyperTideOrderedCell domain={domain} />
      </TableCell>

      {/* Stage 8: Provisioned */}
      <TableCell>
        <ProvisionedCell domain={domain} />
      </TableCell>

      {/* Stage 9: Synced */}
      <TableCell>
        <SyncedCell domain={domain} />
      </TableCell>
    </TableRow>
  );
}
```

**Dependencies:** All 9 cell components

**Exports:** `WaterfallRow`

---

#### **WaterfallCell.tsx** (Base Cell Wrapper)

**Responsibility:** Handle loading, error, empty states for any cell

```typescript
interface WaterfallCellProps {
  loading?: boolean;
  error?: string | null;
  empty?: boolean;
  emptyMessage?: string;
  children: React.ReactNode;
}

export function WaterfallCell({
  loading,
  error,
  empty,
  emptyMessage = '-',
  children,
}: WaterfallCellProps) {
  if (loading) {
    return (
      <div className="flex items-center justify-center py-2">
        <Loader2 className="h-4 w-4 animate-spin text-gray-400" />
      </div>
    );
  }

  if (error) {
    return (
      <div className="text-sm text-red-500 flex items-center gap-1">
        <AlertCircle className="h-4 w-4" />
        <span className="truncate" title={error}>Error</span>
      </div>
    );
  }

  if (empty) {
    return <span className="text-gray-400">{emptyMessage}</span>;
  }

  return <>{children}</>;
}
```

**Exports:** `WaterfallCell`

---

### 2. Cell Components (Modular Stages)

#### **GeneratedCell.tsx**

**Responsibility:** Display domain name, legitimacy score, badges

```typescript
interface GeneratedCellProps {
  domain: WaterfallDomain;
}

export function GeneratedCell({ domain }: GeneratedCellProps) {
  return (
    <div className="space-y-1">
      {/* Domain name */}
      <div className="font-medium text-sm">{domain.domain_name}</div>

      {/* Badges */}
      <div className="flex gap-1">
        {domain.owned && (
          <Badge variant="outline" className="text-xs">Owned ✓</Badge>
        )}
        {domain.deployed && (
          <Badge variant="outline" className="text-xs">Deployed ✓</Badge>
        )}
      </div>

      {/* Legitimacy score */}
      {domain.legitimacy_score && (
        <div className="text-xs text-gray-500">
          Score: {(domain.legitimacy_score * 100).toFixed(0)}%
        </div>
      )}
    </div>
  );
}
```

**No dependencies** (pure display)

**Exports:** `GeneratedCell`

---

#### **PricedCell.tsx**

**Responsibility:** Display pricing, handle single price check

```typescript
interface PricedCellProps {
  domain: WaterfallDomain;
  onRefresh: () => void;
}

export function PricedCell({ domain, onRefresh }: PricedCellProps) {
  const { checkPrice, checking } = usePricedCell(domain.domain_id, onRefresh);

  if (!domain.price_checked_at) {
    return (
      <Button size="sm" variant="ghost" onClick={checkPrice} disabled={checking}>
        {checking ? <Loader2 className="h-3 w-3 animate-spin" /> : 'Check'}
      </Button>
    );
  }

  if (domain.price_status === 'unavailable') {
    return <span className="text-xs text-gray-400">Unavailable</span>;
  }

  return (
    <div className="space-y-1">
      {/* Best price */}
      <div className="font-medium text-sm text-green-600">
        ${domain.cached_price}
      </div>

      {/* Provider */}
      <div className="text-xs text-gray-500 capitalize">
        {domain.selected_provider}
      </div>

      {/* Hover to see both prices */}
      <Button
        size="sm"
        variant="ghost"
        className="h-5 text-xs"
        onClick={checkPrice}
        disabled={checking}
      >
        {checking ? <Loader2 className="h-3 w-3 animate-spin" /> : <RefreshCw className="h-3 w-3" />}
      </Button>
    </div>
  );
}
```

**Dependencies:**
- `usePricedCell` hook for price checking logic

**Exports:** `PricedCell`

---

#### **usePricedCell.ts** (Cell-Specific Hook)

**Responsibility:** Handle single domain price check

```typescript
export function usePricedCell(domainId: string, onRefresh: () => void) {
  const [checking, setChecking] = useState(false);

  const checkPrice = async () => {
    setChecking(true);
    try {
      await infrastructureApi.checkPrice(domainId);
      toast.success('Price updated');
      onRefresh();
    } catch (error) {
      toast.error('Price check failed');
    } finally {
      setChecking(false);
    }
  };

  return { checkPrice, checking };
}
```

**Exports:** `usePricedCell`

---

#### **DNSVerifiedCell.tsx**

**Responsibility:** Display DNS verification status with expandable checklist

```typescript
interface DNSVerifiedCellProps {
  domain: WaterfallDomain;
  onRefresh: () => void;
}

export function DNSVerifiedCell({ domain, onRefresh }: DNSVerifiedCellProps) {
  const [expanded, setExpanded] = useState(false);

  if (domain.nameserver_status === 'pending') {
    return <span className="text-xs text-gray-400">Waiting for NS</span>;
  }

  if (domain.nameserver_status === 'failed') {
    return (
      <div className="text-xs text-red-500 flex items-center gap-1">
        <X className="h-3 w-3" />
        <span>Failed</span>
      </div>
    );
  }

  if (domain.nameserver_status === 'verified' && domain.dns_records_configured) {
    return (
      <div className="space-y-1">
        <div className="text-xs text-green-600 flex items-center gap-1">
          <Check className="h-3 w-3" />
          <span>Verified ✓</span>
        </div>

        {/* Expandable checklist */}
        <Button
          size="sm"
          variant="ghost"
          className="h-5 text-xs"
          onClick={() => setExpanded(!expanded)}
        >
          {expanded ? 'Hide' : 'Details'}
        </Button>

        {expanded && (
          <DNSRecordChecklist
            spf={domain.spf_configured}
            dkim={domain.dkim_configured}
            dmarc={domain.dmarc_configured}
            mx={domain.mx_configured}
          />
        )}
      </div>
    );
  }

  return <span className="text-xs text-yellow-600">⏱ Verifying...</span>;
}
```

**Dependencies:**
- `DNSRecordChecklist` component

**Exports:** `DNSVerifiedCell`

---

#### **DNSRecordChecklist.tsx** (Sub-Component)

**Responsibility:** Display DNS record status in expandable list

```typescript
interface DNSRecordChecklistProps {
  spf: boolean;
  dkim: boolean;
  dmarc: boolean;
  mx: boolean;
}

export function DNSRecordChecklist({ spf, dkim, dmarc, mx }: DNSRecordChecklistProps) {
  const records = [
    { name: 'SPF', configured: spf },
    { name: 'DKIM', configured: dkim },
    { name: 'DMARC', configured: dmarc },
    { name: 'MX', configured: mx },
  ];

  return (
    <div className="mt-1 space-y-0.5 text-xs">
      {records.map((record) => (
        <div key={record.name} className="flex items-center gap-1">
          {record.configured ? (
            <Check className="h-3 w-3 text-green-600" />
          ) : (
            <X className="h-3 w-3 text-gray-300" />
          )}
          <span className={record.configured ? 'text-green-600' : 'text-gray-400'}>
            {record.name}
          </span>
        </div>
      ))}
    </div>
  );
}
```

**No dependencies**

**Exports:** `DNSRecordChecklist`

---

#### **ProviderAssignedCell.tsx**

**Responsibility:** Display provider badge with color coding

```typescript
interface ProviderAssignedCellProps {
  domain: WaterfallDomain;
}

export function ProviderAssignedCell({ domain }: ProviderAssignedCellProps) {
  if (!domain.assigned_provider) {
    return <span className="text-xs text-gray-400">Unassigned</span>;
  }

  return <ProviderBadge provider={domain.assigned_provider} />;
}
```

**Dependencies:**
- `ProviderBadge` component

**Exports:** `ProviderAssignedCell`

---

#### **ProviderBadge.tsx** (Reusable Component)

**Responsibility:** Styled badge for Entra/Google

```typescript
interface ProviderBadgeProps {
  provider: 'entra' | 'google';
}

export function ProviderBadge({ provider }: ProviderBadgeProps) {
  if (provider === 'entra') {
    return (
      <Badge className="bg-blue-100 text-blue-700 border-blue-300">
        🟦 Entra
      </Badge>
    );
  }

  return (
    <Badge className="bg-red-100 text-red-700 border-red-300">
      🔴 Google
    </Badge>
  );
}
```

**No dependencies**

**Exports:** `ProviderBadge`

---

### 3. Shared Hooks (Reusable Logic)

#### **useSelection.ts**

**Responsibility:** Manage checkbox selection state

```typescript
export function useSelection() {
  const [selectedDomains, setSelectedDomains] = useState<Set<string>>(new Set());

  const selectDomain = useCallback((domainId: string) => {
    setSelectedDomains((prev) => {
      const next = new Set(prev);
      if (next.has(domainId)) {
        next.delete(domainId);
      } else {
        next.add(domainId);
      }
      return next;
    });
  }, []);

  const selectAll = useCallback((domainIds: string[]) => {
    setSelectedDomains((prev) => {
      if (prev.size === domainIds.length) {
        return new Set(); // Deselect all
      }
      return new Set(domainIds); // Select all
    });
  }, []);

  const clearSelection = useCallback(() => {
    setSelectedDomains(new Set());
  }, []);

  return {
    selectedDomains,
    selectDomain,
    selectAll,
    clearSelection,
  };
}
```

**Exports:** `useSelection`

---

#### **usePolling.ts**

**Responsibility:** Generic polling with timeout

```typescript
interface UsePollingOptions<T> {
  fetchFn: () => Promise<T>;
  interval: number;
  timeout: number;
  onSuccess?: (data: T) => void;
  onError?: (error: Error) => void;
  onTimeout?: () => void;
  shouldStop?: (data: T) => boolean;
}

export function usePolling<T>(options: UsePollingOptions<T>) {
  const [polling, setPolling] = useState(false);

  const startPolling = useCallback(() => {
    setPolling(true);

    const pollInterval = setInterval(async () => {
      try {
        const data = await options.fetchFn();

        if (options.shouldStop?.(data)) {
          clearInterval(pollInterval);
          options.onSuccess?.(data);
          setPolling(false);
        }
      } catch (error) {
        // Ignore polling errors (continue trying)
      }
    }, options.interval);

    // Timeout
    const timeoutId = setTimeout(() => {
      clearInterval(pollInterval);
      options.onTimeout?.();
      setPolling(false);
    }, options.timeout);

    return () => {
      clearInterval(pollInterval);
      clearTimeout(timeoutId);
    };
  }, [options]);

  const stopPolling = useCallback(() => {
    setPolling(false);
  }, []);

  return { polling, startPolling, stopPolling };
}
```

**Exports:** `usePolling`

---

#### **useBulkActions.ts**

**Responsibility:** Coordinate bulk operations with progress tracking

```typescript
interface BulkActionOptions {
  domainIds: string[];
  actionFn: (domainIds: string[]) => Promise<void>;
  onProgress?: (completed: number, total: number) => void;
  onComplete?: () => void;
  onError?: (error: Error) => void;
}

export function useBulkActions() {
  const [loading, setLoading] = useState(false);
  const [progress, setProgress] = useState({ completed: 0, total: 0 });

  const executeBulkAction = async (options: BulkActionOptions) => {
    setLoading(true);
    setProgress({ completed: 0, total: options.domainIds.length });

    try {
      await options.actionFn(options.domainIds);
      options.onComplete?.();
      toast.success(`Completed ${options.domainIds.length} domains`);
    } catch (error) {
      options.onError?.(error as Error);
      toast.error('Bulk action failed');
    } finally {
      setLoading(false);
      setProgress({ completed: 0, total: 0 });
    }
  };

  return {
    loading,
    progress,
    executeBulkAction,
  };
}
```

**Exports:** `useBulkActions`

---

## 🎨 Styling Convention

### Tailwind Classes:
```typescript
// Cell states
const cellClasses = {
  loading: 'text-gray-400',
  error: 'text-red-500',
  success: 'text-green-600',
  warning: 'text-yellow-600',
  empty: 'text-gray-400',
};

// Badge colors
const badgeColors = {
  entra: 'bg-blue-100 text-blue-700 border-blue-300',
  google: 'bg-red-100 text-red-700 border-red-300',
  owned: 'bg-green-100 text-green-700 border-green-300',
  deployed: 'bg-purple-100 text-purple-700 border-purple-300',
};

// Button sizes
const buttonSizes = {
  sm: 'h-7 px-2 text-xs',
  md: 'h-9 px-4 text-sm',
  lg: 'h-11 px-6 text-base',
};
```

---

## 🧪 Testing Strategy

### Unit Tests (Per Component):
```typescript
// GeneratedCell.test.tsx
describe('GeneratedCell', () => {
  it('displays domain name', () => {
    render(<GeneratedCell domain={mockDomain} />);
    expect(screen.getByText('example.com')).toBeInTheDocument();
  });

  it('shows owned badge when owned', () => {
    render(<GeneratedCell domain={{ ...mockDomain, owned: true }} />);
    expect(screen.getByText('Owned ✓')).toBeInTheDocument();
  });
});
```

### Integration Tests (Full Row):
```typescript
// WaterfallRow.test.tsx
describe('WaterfallRow', () => {
  it('renders all 9 cells', () => {
    render(<WaterfallRow domain={mockDomain} selected={false} onSelect={jest.fn()} />);
    expect(screen.getAllByRole('cell')).toHaveLength(10); // 9 stages + checkbox
  });
});
```

### Hook Tests:
```typescript
// useSelection.test.ts
describe('useSelection', () => {
  it('selects and deselects domains', () => {
    const { result } = renderHook(() => useSelection());
    act(() => result.current.selectDomain('domain-1'));
    expect(result.current.selectedDomains.has('domain-1')).toBe(true);
  });
});
```

---

## 📦 Export Pattern

### Each Module Exports:
```typescript
// components/infrastructure/cells/index.ts
export { GeneratedCell } from './GeneratedCell';
export { PricedCell } from './PricedCell';
export { PurchasedCell } from './PurchasedCell';
export { DNSMovedCell } from './DNSMovedCell';
export { DNSVerifiedCell } from './DNSVerifiedCell';
export { ProviderAssignedCell } from './ProviderAssignedCell';
export { HyperTideOrderedCell } from './HyperTideOrderedCell';
export { ProvisionedCell } from './ProvisionedCell';
export { SyncedCell } from './SyncedCell';

// hooks/infrastructure/index.ts
export { useWaterfallData } from './useWaterfallData';
export { useSelection } from './useSelection';
export { useBulkActions } from './useBulkActions';
export { usePolling } from './usePolling';
export { useLazyLoading } from './useLazyLoading';
```

---

## 🚀 Development Workflow

### Phase 1: Foundation (Week 1)
1. Create base components:
   - `WaterfallTable.tsx`
   - `WaterfallRow.tsx`
   - `WaterfallCell.tsx`
2. Create shared hooks:
   - `useSelection.ts`
   - `usePolling.ts`
   - `useBulkActions.ts`
3. Test with mock data

### Phase 2: Cells (Week 2)
1. Build simple cells first:
   - `GeneratedCell`
   - `PricedCell`
   - `PurchasedCell`
2. Build complex cells:
   - `DNSVerifiedCell` (with checklist)
   - `ProviderAssignedCell` (with badge)
   - `HyperTideOrderedCell` (with polling)

### Phase 3: Modals (Week 3)
1. Bulk action modals:
   - `BulkPriceCheckModal`
   - `BulkPurchaseModal`
   - `BulkDNSSetModal`
2. Order modals:
   - `HyperTideOrderModal`
   - `OrderTrackingModal`

### Phase 4: Integration (Week 4)
1. Connect to real API
2. Wire up all bulk actions
3. Add error handling
4. Polish UX

---

## 💡 Key Principles

1. **Each Cell is Self-Contained** - Can be developed and tested independently
2. **Hooks Extract Logic** - Components focus on UI, hooks handle business logic
3. **Composition Over Props** - Small components combine to create features
4. **Type Safety** - Full TypeScript coverage prevents runtime errors
5. **Testability** - Each component and hook can be unit tested

---

**Result:** Modular, maintainable, testable architecture that follows existing codebase patterns.
