# Infrastructure Provisioning SPA - Deployment Guide

## File Structure Overview

All files are organized in the `charm-email-os` repository:

```
charm-email-os/
├── api/
│   └── routes/
│       └── infrastructure.py          # Backend API endpoints
│
├── migrations/
│   └── 045_infrastructure_waterfall_FINAL.sql  # Database migration (USE THIS ONE)
│
├── charm-email-os/                    # Frontend Next.js app
│   ├── app/
│   │   └── infrastructure/
│   │       └── page.tsx               # Main SPA page (/infrastructure)
│   │
│   ├── components/
│   │   └── infrastructure/
│   │       ├── WaterfallTable.tsx     # Main table component
│   │       ├── StageColumn.tsx        # Column component
│   │       └── cells/
│   │           ├── StageCell.tsx      # Cell router
│   │           ├── GeneratedCell.tsx  # Stage 1
│   │           ├── PricedCell.tsx     # Stage 2
│   │           ├── PurchasedCell.tsx  # Stage 3
│   │           ├── DnsMovedCell.tsx   # Stage 4
│   │           ├── DnsVerifiedCell.tsx # Stage 5
│   │           ├── ProviderAssignedCell.tsx # Stage 6
│   │           ├── HyperTideOrderedCell.tsx # Stage 7
│   │           ├── ProvisionedCell.tsx # Stage 8
│   │           └── SyncedCell.tsx     # Stage 9
│   │
│   └── lib/
│       ├── stores/
│       │   └── waterfallStore.ts      # Zustand state management
│       ├── types/
│       │   └── infrastructure.ts      # TypeScript types
│       └── api.ts                     # API client (updated)
│
└── docs/
    └── infrastructure-provisioning/
        ├── DATABASE-ANALYSIS.md
        ├── DATA-HIERARCHY.md
        ├── API-CONSOLIDATION-AUDIT.md
        ├── SENDER-NAMES-FLOW.md
        ├── FINAL-AUDIT-SUMMARY.md
        └── DEPLOYMENT-GUIDE.md (this file)
```

---

## Quick Start - Docker Desktop Deployment

### Prerequisites
- Docker Desktop running
- PostgreSQL database accessible
- Backend API running
- Frontend Next.js dev server

### Step 1: Apply Database Migration

```bash
# Navigate to repo
cd /home/claw/charm-email-os

# Apply migration to your database
# Option A: Using psql directly
psql -U postgres -d ownrbl -f migrations/045_infrastructure_waterfall_FINAL.sql

# Option B: Using Docker if DB is containerized
docker exec -i <postgres-container> psql -U postgres -d ownrbl < migrations/045_infrastructure_waterfall_FINAL.sql

# Verify migration
psql -U postgres -d ownrbl -c "SELECT COUNT(*) FROM v_infrastructure_waterfall;"
```

**What this adds:**
- 8 DNS tracking fields on `domains` table
- 6 error tracking fields on `inbox_purchase_jobs` table
- `v_infrastructure_waterfall` view
- `domain_lifecycle_events` audit log table
- Performance indexes

**What it does NOT add:**
- ❌ `sender_names` table (names stored in `clients.onboarding_data`)

### Step 2: Register Backend Route

The backend route is already created at `/home/claw/charm-email-os/api/routes/infrastructure.py`

**Verify it's registered in main.py:**

```bash
# Check if infrastructure router is imported
grep -n "infrastructure" /home/claw/charm-email-os/api/main.py
```

**If not found, add to main.py:**

```python
# In api/main.py
from routes import infrastructure

# In the router includes section:
app.include_router(infrastructure.router, prefix="/api/infrastructure", tags=["infrastructure"])
```

### Step 3: Start Backend API

```bash
# Navigate to backend
cd /home/claw/charm-email-os/api

# Start with uvicorn
uvicorn main:app --reload --host 0.0.0.0 --port 8000

# Or if using Docker
docker-compose up backend
```

**Verify backend is running:**
```bash
curl http://localhost:8000/api/infrastructure/waterfall/workspace/test-id
# Should return 404 or empty array (not 500 error)
```

### Step 4: Start Frontend

```bash
# Navigate to frontend
cd /home/claw/charm-email-os/charm-email-os

# Install dependencies (if needed)
npm install

# Start dev server
npm run dev

# Should start on http://localhost:3000
```

### Step 5: Access the Infrastructure SPA

Open browser and navigate to:
```
http://localhost:3000/infrastructure
```

**You should see:**
- Client selector dropdown
- Filter controls (View, Stage, Provider)
- Empty state with "Select a Client" message

**Select a client to load waterfall:**
- Dropdown populates with all clients
- Select any client
- Waterfall table loads with 9 stage columns
- Domains appear in their current stage

---

## Docker Compose Setup (Optional)

If you want everything in Docker, create/update `docker-compose.yml`:

```yaml
version: '3.8'

services:
  postgres:
    image: postgres:15
    environment:
      POSTGRES_DB: ownrbl
      POSTGRES_USER: postgres
      POSTGRES_PASSWORD: password
    ports:
      - "5432:5432"
    volumes:
      - ./migrations:/docker-entrypoint-initdb.d
      - postgres_data:/var/lib/postgresql/data

  backend:
    build: ./api
    ports:
      - "8000:8000"
    environment:
      POSTGRES_HOST: postgres
      POSTGRES_PORT: 5432
      POSTGRES_DB: ownrbl
      POSTGRES_USER: postgres
      POSTGRES_PASSWORD: password
    depends_on:
      - postgres
    command: uvicorn main:app --host 0.0.0.0 --port 8000 --reload

  frontend:
    build: ./charm-email-os
    ports:
      - "3000:3000"
    environment:
      NEXT_PUBLIC_API_URL: http://localhost:8000
    depends_on:
      - backend
    command: npm run dev

volumes:
  postgres_data:
```

**Start everything:**
```bash
docker-compose up -d
```

**Access:**
- Frontend: http://localhost:3000/infrastructure
- Backend API: http://localhost:8000/docs (FastAPI Swagger UI)
- Database: localhost:5432

---

## Troubleshooting

### Issue: "Cannot find module '@/lib/stores/waterfallStore'"

**Solution:** Ensure TypeScript path alias is configured in `tsconfig.json`:

```json
{
  "compilerOptions": {
    "paths": {
      "@/*": ["./*"]
    }
  }
}
```

### Issue: "Failed to load waterfall data"

**Check:**
1. Backend API is running: `curl http://localhost:8000/api/infrastructure/waterfall/workspace/test-id`
2. Database migration applied: `psql -U postgres -d ownrbl -c "\d v_infrastructure_waterfall"`
3. CORS enabled in backend: Check `api/main.py` has CORS middleware

### Issue: "No clients found"

**Check:**
1. Clients exist in database: `psql -U postgres -d ownrbl -c "SELECT COUNT(*) FROM clients;"`
2. Backend `/api/clients/list` endpoint works
3. Client API integration in frontend

### Issue: Waterfall table is empty

**Check:**
1. Client has domains: `SELECT COUNT(*) FROM domains WHERE workspace_id = (SELECT workspace_id FROM clients WHERE id = 'client-id');`
2. View returns data: `SELECT * FROM v_infrastructure_waterfall WHERE workspace_id = 'workspace-id';`
3. Frontend API call succeeds (check browser console)

### Issue: lightningcss build error (from earlier)

**Solution:**
```bash
cd charm-email-os
rm -rf node_modules package-lock.json
npm install
npm run dev
```

---

## Environment Variables

### Backend (api/.env)
```bash
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_DB=ownrbl
POSTGRES_USER=postgres
POSTGRES_PASSWORD=password

# Optional
EMAILBISON_API_URL=https://spellcast.hirecharm.com
EMAILBISON_API_KEY=your-key-here
```

### Frontend (charm-email-os/.env.local)
```bash
NEXT_PUBLIC_API_URL=http://localhost:8000
```

---

## Testing the Deployment

### 1. Test Backend Endpoints

```bash
# Get waterfall for a client
curl http://localhost:8000/api/infrastructure/waterfall/client/{client-id}

# Get sender names
curl http://localhost:8000/api/infrastructure/sender-names/client/{client-id}

# Verify database view
psql -U postgres -d ownrbl -c "SELECT domain_name, current_stage FROM v_infrastructure_waterfall LIMIT 5;"
```

### 2. Test Frontend

1. Navigate to http://localhost:3000/infrastructure
2. Select a client from dropdown
3. Verify waterfall table loads
4. Check browser console for errors
5. Try filters (View, Stage, Provider)
6. Try domain selection (checkboxes)

### 3. Test Stage Cells

Each stage should display:
- **Stage 1:** Domain name, date, legitimacy score
- **Stage 2:** Price, provider badge, status
- **Stage 3:** Purchase date, provider
- **Stage 4:** DNS migration status, DNSimple badge
- **Stage 5:** SPF/DKIM/DMARC/MX checklist
- **Stage 6:** Entra/Google badge
- **Stage 7:** HyperTide job status
- **Stage 8:** Provisioning status
- **Stage 9:** Sync progress, inbox count

---

## Production Deployment Notes

### Database
- Migration `045_infrastructure_waterfall_FINAL.sql` is production-safe
- Uses `IF NOT EXISTS` for all objects
- Creates indexes for performance
- No data loss or breaking changes

### Backend
- All endpoints are read-only except HyperTide order creation
- No authentication added yet (add before production)
- Rate limiting recommended for bulk operations

### Frontend
- Built as standalone SPA at `/infrastructure`
- No dependencies on other pages
- Can be deployed independently
- Consider lazy loading for large domain counts (1000+)

### Performance
- Database view `v_infrastructure_waterfall` is indexed
- Frontend uses Zustand for efficient state management
- Horizontal scroll supports unlimited domains
- Consider pagination for 500+ domains

---

## What's Included vs. What's Missing

### ✅ Included & Working
- Complete 9-stage waterfall table
- Client selector and filters
- All stage cell components with data display
- Domain selection (checkboxes)
- Responsive horizontal scroll
- Loading and error states
- Database schema and backend API

### ⚠️ Not Yet Implemented (Planned)
- Bulk action modals (price check, purchase, DNS, etc.)
- HyperTide order modal
- Inline action buttons (currently display only)
- Job polling for async operations
- Real-time updates
- Notifications/toasts for actions

### ❌ Not Included (Out of Scope)
- Authentication/authorization
- User permissions
- Activity logging
- Analytics/metrics
- Export functionality

---

## Next Steps After Deployment

Once you've verified the basic deployment works:

1. **Add HyperTide Order Modal** - Configure workspace, sender names, submit orders
2. **Add Bulk Action Modals** - Price check, purchase, DNS operations
3. **Wire up inline actions** - Make cell buttons functional
4. **Add job polling** - Real-time status updates
5. **Add notifications** - Success/error toasts

The foundation is solid and ready for these enhancements!

---

## Support & Documentation

- **Database Schema:** See `DATABASE-ANALYSIS.md`
- **Data Hierarchy:** See `DATA-HIERARCHY.md`
- **API Endpoints:** See `API-CONSOLIDATION-AUDIT.md`
- **Sender Names:** See `SENDER-NAMES-FLOW.md`
- **Full Summary:** See `FINAL-AUDIT-SUMMARY.md`

---

## File Checklist

Before deploying, verify these files exist:

**Backend:**
- [x] `/api/routes/infrastructure.py` (8 endpoints)
- [x] `/migrations/045_infrastructure_waterfall_FINAL.sql`

**Frontend:**
- [x] `/charm-email-os/app/infrastructure/page.tsx`
- [x] `/charm-email-os/lib/stores/waterfallStore.ts`
- [x] `/charm-email-os/lib/types/infrastructure.ts`
- [x] `/charm-email-os/lib/api.ts` (updated with infrastructure endpoints)
- [x] `/charm-email-os/components/infrastructure/WaterfallTable.tsx`
- [x] `/charm-email-os/components/infrastructure/StageColumn.tsx`
- [x] `/charm-email-os/components/infrastructure/cells/` (10 files)

All files are ready in your local repository!
