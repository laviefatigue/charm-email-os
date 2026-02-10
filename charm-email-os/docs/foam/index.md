# Charm Email OS

**Client management platform for outbound email campaigns**

## Overview

Charm Email OS is a Next.js 16 application designed to manage email outreach operations at scale. It provides tools for managing clients, email infrastructure (domains/inboxes), campaign strategies, lead management, and health monitoring.

## Quick Links

- [[architecture]] - System architecture and tech stack
- [[data-models]] - Core types and interfaces
- [[state-management]] - Zustand stores overview
- [[components]] - UI component structure
- [[routing]] - Page routes and navigation
- [[onboarding-form]] - External client onboarding form
- [[strategy-ai-container]] - VPS Docker deployment for AI strategy generation
- [[strategy-cycles]] - Campaign cycles and Strategy page UI
- [[strategy-suggestions]] - Campaign sequence approval workflow and database schema
- [[strategy-upgrade]] - Planned strategy page improvements (spintax workflow)

## Core Concepts

### [[clients]]
Organizations using the platform. Each client has their own infrastructure, campaigns, and leads.

### [[infrastructure]]
Email sending infrastructure including [[domains]] and [[inboxes]] with warmup and health tracking. Real-time metrics via [[emailbison-integration]].

### [[campaigns]]
Outbound email campaigns organized by [[strategy-cycles]]. 4-email sequences with distinct angles (signal, pain, case study, risk).

### [[leads]]
Contact records managed per campaign with status tracking and CSV upload support.

### [[lead-dispositions]]
Lead state machine with cooldown logic, company-level suppression, TAM tracking, and pull logic for campaign fills.

### [[lead-refinery]]
JIT lead verification pipeline for manufacturing verified cold email lists. Processes 75.4M leads through cost-efficient waterfall validation.

### [[lead-tam-map]]
AI-ARK enrichment data flows back to the database, building a living TAM map. Every pipeline run makes future contracts cheaper and data fresher.

### [[health-monitoring]]
Comprehensive system for tracking inbox/domain health, kill triggers, and ESP reputation. Powered by [[emailbison-integration]] for real-time metrics.

### [[emailbison-integration]]
Real-time API integration with EmailBison for inbox connection status, health scores, bounce rates, and provider breakdown. Powers the [[inventory-health-dashboard]].

### [[strategy-ai-container]]
Purpose-built Docker container for autonomous email strategy generation using Claude Code on VPS.

### [[purchase-worker]]
Autonomous browser automation for purchasing email inboxes on Hypertide using Claude Code + Playwright. Navigates the Hypertide web UI, selects EmailBison workspaces, and completes orders without human intervention. Deployed on Coolify.

### [[system-integration]]
How Charm Email OS, the Lead Refinery pipeline, and EmailBison execution engine connect as a unified outbound platform. End-to-end data flows, system responsibilities, and integration points.

## Tech Stack

| Layer | Technology |
|-------|------------|
| Framework | Next.js 16.1.1 |
| UI | React 19, Tailwind CSS 4, Radix UI |
| State | Zustand 5 |
| Icons | Lucide React |
| Notifications | Sonner |
| IDs | nanoid |

## Getting Started

```bash
npm install
npm run dev
```

Open http://localhost:3000 to access the application.

## Related

- [[glossary]] - Term definitions
- [[workflows]] - Common user workflows
- [[system-integration]] - Platform integration map

---
Tags: #overview #index
