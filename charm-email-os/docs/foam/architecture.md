# Architecture

## Overview

Charm Email OS follows a modern React architecture with Next.js App Router, client-side state management via Zustand, and component-based UI.

## Directory Structure

```
charm-email-os/
├── app/                    # Next.js App Router pages
│   ├── layout.tsx          # Root layout with Sidebar
│   ├── page.tsx            # Redirects to /clients
│   └── clients/            # Client management routes
│       ├── page.tsx        # Client list
│       └── [clientId]/     # Dynamic client routes
│           ├── page.tsx    # Client overview
│           ├── health/     # Health monitoring
│           ├── inboxes/    # Infrastructure
│           ├── leads/      # Lead management
│           └── strategy/   # Campaign ideas
├── components/             # React components
│   ├── clients/            # Client-related components
│   ├── health/             # Health monitoring UI
│   ├── inboxes/            # Domain/inbox management
│   ├── layout/             # App shell components
│   ├── leads/              # Lead management UI
│   ├── providers/          # Context providers
│   ├── shared/             # Reusable components
│   ├── strategy/           # Campaign strategy UI
│   └── ui/                 # shadcn/ui primitives
├── lib/                    # Utilities and stores
│   ├── stores/             # Zustand state stores
│   ├── types/              # TypeScript types
│   ├── types.ts            # Core type definitions
│   ├── utils.ts            # Utility functions
│   └── mock-*.ts           # Mock data generators
└── public/                 # Static assets
```

## Architecture Layers

### Presentation Layer
- **Pages** (`app/`): Next.js App Router pages handle routing and layout
- **Components** (`components/`): Reusable UI components organized by feature

### State Layer
- **Zustand Stores** (`lib/stores/`): Client-side state management
  - [[clientStore]] - Client data
  - [[infrastructureStore]] - Domains and inboxes
  - [[strategyStore]] - Campaign ideas
  - [[campaignStore]] - Campaigns and leads
  - [[healthStore]] - Health metrics and alerts

### Data Layer
- **Types** (`lib/types/`): TypeScript interfaces and types
- **Mock Data** (`lib/mock-*.ts`): Sample data for development

## Data Flow

```
User Action → Component → Zustand Store → State Update → UI Re-render
```

1. User interacts with a component
2. Component calls store action
3. Store updates state
4. React re-renders affected components

## Component Organization

Components are organized by feature domain:

- `clients/` - [[ClientCard]], [[ClientForm]], [[OnboardingForm]]
- `health/` - [[DomainHealthGrid]], [[KillTriggerMonitor]], [[ESPHealthSummary]]
- `inboxes/` - [[DomainCard]], [[InboxCard]], [[WarmupProgress]]
- `leads/` - [[LeadsTable]], [[UploadModal]], [[CampaignSidebar]]
- `strategy/` - [[IdeaCard]], [[CreateCampaignModal]]
- `layout/` - [[Sidebar]], [[PageContainer]], [[TabNavigation]]
- `shared/` - [[StatusBadge]], [[ApprovalButtons]], [[EmptyState]]

## Related

- [[data-models]] - Type definitions
- [[state-management]] - Store details
- [[routing]] - Page structure

---
Tags: #architecture #structure
