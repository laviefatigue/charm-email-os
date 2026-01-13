# Components

UI components organized by feature domain in `components/`.

## Component Categories

### Layout Components (`components/layout/`)

Core app shell components:

| Component | Purpose |
|-----------|---------|
| [[Sidebar]] | Main navigation sidebar |
| [[PageContainer]] | Page wrapper with consistent padding |
| [[ClientHeader]] | Client-specific header with tabs |
| [[TabNavigation]] | Tab switching for client views |
| [[Breadcrumb]] | Navigation breadcrumbs |

### Client Components (`components/clients/`)

[[clients]] management:

| Component | Purpose |
|-----------|---------|
| [[ClientCard]] | Client card in list view |
| [[ClientForm]] | New client creation form |
| [[OnboardingForm]] | Multi-step onboarding wizard |

### Infrastructure Components (`components/inboxes/`)

[[domains]] and [[inboxes]] management:

| Component | Purpose |
|-----------|---------|
| [[DomainCard]] | Domain status and actions |
| [[DomainForm]] | New domain creation |
| [[DomainEditModal]] | Edit domain details |
| [[InboxCard]] | Inbox status and health |
| [[InboxForm]] | New inbox creation |
| [[InboxEditModal]] | Edit inbox details |
| [[WarmupProgress]] | Warmup progress indicator |

### Health Components (`components/health/`)

[[health-monitoring]] UI:

| Component | Purpose |
|-----------|---------|
| [[HealthScoreRing]] | Circular health score visualization |
| [[DomainHealthGrid]] | Grid of domain health cards |
| [[DomainHealthCard]] | Individual domain health status |
| [[DomainPhaseBadge]] | Domain lifecycle phase indicator |
| [[KillTriggerMonitor]] | Active kill trigger alerts |
| [[KillTriggerCard]] | Individual trigger with actions |
| [[ESPHealthSummary]] | Gmail/Microsoft reputation summary |
| [[BackupCapacityGauge]] | Backup inbox capacity |
| [[ListContaminationTracker]] | List quality monitoring |
| [[CampaignAttributionPanel]] | Campaign impact on health |

### Strategy Components (`components/strategy/`)

[[campaign-ideas]] workflow:

| Component | Purpose |
|-----------|---------|
| [[IdeaCard]] | Campaign idea with approve/reject |
| [[IdeaEditModal]] | Edit idea details |
| [[ApprovedCampaignRow]] | Approved idea ready for campaign |
| [[CreateCampaignModal]] | Convert idea to campaign |

### Leads Components (`components/leads/`)

[[leads]] management:

| Component | Purpose |
|-----------|---------|
| [[CampaignSidebar]] | Campaign selection sidebar |
| [[CampaignHeader]] | Current campaign info |
| [[LeadsTable]] | Lead data table with filtering |
| [[StatsRow]] | Lead status statistics |
| [[UploadModal]] | CSV upload workflow |
| [[ColumnMappingStep]] | CSV column to field mapping |
| [[LeadSourceSelector]] | Lead source selection |
| [[ScriptPullModal]] | Script-based lead import |

### Shared Components (`components/shared/`)

Reusable across features:

| Component | Purpose |
|-----------|---------|
| [[StatusBadge]] | Status indicator with colors |
| [[ApprovalButtons]] | Approve/Reject button pair |
| [[ConfirmModal]] | Confirmation dialog |
| [[EmptyState]] | Empty list placeholder |
| [[LoadingSkeleton]] | Loading state placeholder |

### UI Primitives (`components/ui/`)

shadcn/ui components (Radix UI based):

- Avatar, Button, Card, Dialog
- Dropdown Menu, Input, Label
- Popover, Progress, Scroll Area
- Select, Separator, Tabs, Tooltip

## Component Patterns

### Store Integration
```tsx
function MyComponent() {
  const { data, action } = useSomeStore();
  return <UI data={data} onAction={action} />;
}
```

### Approval Pattern
```tsx
<ApprovalButtons
  onApprove={() => approveItem(id)}
  onReject={() => rejectItem(id)}
/>
```

### Status Display
```tsx
<StatusBadge status={item.status} />
```

## Related

- [[architecture]] - Component organization
- [[routing]] - Where components are used

---
Tags: #components #ui #react
