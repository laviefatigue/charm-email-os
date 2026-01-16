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

## Core Concepts

### [[clients]]
Organizations using the platform. Each client has their own infrastructure, campaigns, and leads.

### [[infrastructure]]
Email sending infrastructure including [[domains]] and [[inboxes]] with warmup and health tracking.

### [[campaigns]]
Outbound email campaigns created from [[campaign-ideas]] through the [[strategy]] workflow.

### [[leads]]
Contact records managed per campaign with status tracking and CSV upload support.

### [[health-monitoring]]
Comprehensive system for tracking inbox/domain health, kill triggers, and ESP reputation.

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

---
Tags: #overview #index
