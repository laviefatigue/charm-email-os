# Infrastructure Provisioning - Quick Reference

**One-page cheat sheet for the Infrastructure Provisioning SPA.**

---

## Metrics at a Glance

```
┌─────────────────────────────────────────────────────────────────────────┐
│  DOMAINS        INBOXES         DAILY CAPACITY      ORDERS              │
│  ─────────      ───────         ──────────────      ──────              │
│  actual/        live/           inboxes ×           used/               │
│  expected       total           rate/day            required            │
│                                                                         │
│  12/12          607/618         1,518/day           6/6                 │
│  (from orders)  (live+dead)     (×30 = monthly)     (from package)      │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## Provider Configuration

| Provider | Domains/Order | Inboxes/Domain | Emails/Day/Inbox |
|----------|---------------|----------------|------------------|
| **Entra** | 2 | 50 | 2.5 |
| **Google** | 5 | 3 | 17.5 |

---

## Package Templates

| Package | Entra Orders | Google Orders | Total Domains | Total Inboxes |
|---------|--------------|---------------|---------------|---------------|
| **Starter** | 6 | 5 | 37 | 699 |
| **Growth** | 12 | 10 | 74 | 1,398 |

---

## Metric Calculations

### DOMAINS
```
orderCount = ceil(actualDomains / domainsPerOrder)
expected = orderCount × domainsPerOrder
Display: actualDomains / expected
```

### DAILY CAPACITY
```
Entra:  liveInboxes × 2.5 emails/day
Google: liveInboxes × 17.5 emails/day
```

### ORDERS
```
used = ceil(actualDomains / domainsPerOrder)
required = client_subscriptions.{provider}_packages
Display: used / required
```

---

## Domain Lifecycle Priority

| Priority | State | Action Needed |
|----------|-------|---------------|
| 1 | Live (Healthy) | Monitor |
| 2 | Live (Flagged) | Investigate |
| 3 | Ready for HyperTide | Create order |
| 4 | DNS Pending | Wait for propagation |
| 5 | Ready to Buy | Purchase domain |
| 6 | Not Priced | Check pricing |

---

## Status Colors

| Status | Color | Meaning |
|--------|-------|---------|
| Live | Green | Active, healthy |
| Flagged | Amber | At risk, needs attention |
| Dead | Red | All inboxes killed |

---

## Common Filters

| Filter | Use When |
|--------|----------|
| Purchased | View active infrastructure |
| Pending | Find domains to buy |
| Provider: Entra | Focus on Microsoft |
| Provider: Google | Focus on Google |
| >$15 toggle | See over-budget domains |
| Deactivated toggle | See dead domains |

---

## Key URLs

| Resource | URL |
|----------|-----|
| SPA | `http://localhost:3000/infrastructure` |
| API | `http://localhost:8000/api/infrastructure/...` |
| API Docs | `http://localhost:8000/docs` |

---

## Quick Commands

```bash
# Start all services
docker-compose -f docker-compose.local.yml up -d

# View frontend logs
docker logs charm-frontend

# Check API health
curl http://localhost:8000/health

# Query database
docker exec charm-postgres psql -U postgres -d postgres -c "..."
```

---

## Database Quick Queries

```sql
-- Check client package
SELECT c.name, cs.entra_packages, cs.google_packages, pt.name as package
FROM client_subscriptions cs
JOIN clients c ON c.id = cs.client_id
JOIN package_templates pt ON pt.id = cs.package_template_id;

-- Domain counts by provider
SELECT
  CASE WHEN esp LIKE '%microsoft%' THEN 'entra' ELSE 'google' END as provider,
  COUNT(DISTINCT domain_id) as domains
FROM sender_accounts
GROUP BY 1;

-- Live vs dead inboxes
SELECT
  COUNT(*) FILTER (WHERE killed_at IS NULL) as live,
  COUNT(*) FILTER (WHERE killed_at IS NOT NULL) as dead
FROM sender_accounts;
```
