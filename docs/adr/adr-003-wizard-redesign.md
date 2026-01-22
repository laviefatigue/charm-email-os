---
title: "ADR-003: InboxPurchaseWizard Redesign"
created: 2026-01-22
updated: 2026-01-22
tags: [adr, status/accepted, infrastructure, wizard]
status: accepted
---

# ADR-003: InboxPurchaseWizard Redesign

## Status

Accepted (2026-01-22)

## Context

The original InboxPurchaseWizard had significant usability issues:

1. **Abstract Inputs** - User had to manually enter inbox counts (e.g., "100 Entra, 0 Google") without understanding what that meant in terms of domains and orders.

2. **No Domain Connection** - The wizard didn't know which purchased domains would be provisioned. User had no visibility into which domains would get inboxes.

3. **No Package Awareness** - Client package sizes (Starter: 699 inboxes, Growth: 1398 inboxes) weren't reflected. Users had to know the right numbers to enter.

4. **Confusing Flow** - The first step was "Configure" with manual number inputs, which didn't match the actual workflow of "select domains → configure → execute."

5. **Hidden Calculations** - Order breakdown required clicking "Calculate Order" button. Real-time feedback was missing.

## Decision

Redesign the wizard to be **domain-centric** rather than inbox-count-centric:

### New Step Flow

1. **Domains** (was: Configure)
   - Show all purchased domains available for setup
   - Pre-select domains passed from DomainsNeedingSetupTable
   - Add provider selection: Entra, Google, or Mixed (70/30)
   - Real-time order preview as domains are selected

2. **Names** (unchanged)
   - Load from onboarding personas
   - Generate random names
   - Manual entry

3. **Review** (unchanged)
   - Full configuration summary
   - Provider breakdown
   - Cost estimate

4. **Execute** (unchanged)
   - HyperTide automation
   - Progress tracking

### Key Changes

1. **Domain Selection First** - User selects which purchased domains to provision, not abstract inbox counts.

2. **Provider Selection** - Clear radio buttons with specifications:
   - Entra (recommended): 52 inboxes/domain, 2 domains/order
   - Google: 3 inboxes/domain, 5 domains/order
   - Mixed: 70% Entra, 30% Google

3. **Real-Time Preview** - Order breakdown updates immediately as domains are selected/deselected.

4. **Pre-Selection** - When opened from DomainsNeedingSetupTable, selected domains are pre-populated.

5. **Automatic Calculation** - No need to click "Calculate Order" - done via useMemo.

### New Props

```typescript
interface InboxPurchaseWizardProps {
  // ... existing props
  selectedDomainIds?: string[];  // NEW: Pre-selected domains
}
```

### Integration Changes

```typescript
// inboxes/page.tsx
<DomainsNeedingSetupTable
  onSetupClick={(selectedIds) => {
    setSelectedDomainsForSetup(selectedIds);  // NEW state
    setShowInboxPurchaseWizard(true);
  }}
/>

<InboxPurchaseWizard
  domains={purchasedNeedingSetup}
  selectedDomainIds={selectedDomainsForSetup}  // NEW prop
  // ...
/>
```

## Consequences

### Positive

- **Intuitive Flow** - Select domains → Choose provider → Configure names → Execute
- **Visible Calculations** - Real-time order preview eliminates guesswork
- **Domain Visibility** - Users see exactly which domains will be provisioned
- **Package Alignment** - Provider selection makes it easy to match package quotas
- **Reduced Errors** - Can't misconfigure because selections drive calculations

### Negative

- **Larger Component** - Wizard file grew from ~800 to ~1100 lines
- **New Dependency** - Added `@radix-ui/react-radio-group` for provider selection
- **Breaking Change** - New required prop `domains` expects different shape than before

### Neutral

- **Package Templates** - Still defined as constants, not from database. Phase 6B will add subscription table.
- **Mixed Provider** - Uses fixed 70/30 split. Could be made configurable later.

## Related

- [[inbox-provisioning]] - Wizard documentation
- [[package-templates]] - Package definitions
- [[domain-lifecycle]] - Status flow
- [[adr-002-legacy-status]] - Related infrastructure change
