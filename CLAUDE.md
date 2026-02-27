# Charm Email OS - Project Context

## Database Access

The main Charm OS database is **PostgreSQL**, not SQLite. Use these environment variables:

```bash
# Connect to Charm OS PostgreSQL
PGPASSWORD=$POSTGRES_PASSWORD psql -h $POSTGRES_HOST -U $POSTGRES_USER -d $POSTGRES_DB

# Example queries:
PGPASSWORD=$POSTGRES_PASSWORD psql -h $POSTGRES_HOST -U $POSTGRES_USER -d $POSTGRES_DB -c "SELECT * FROM domains LIMIT 10;"
PGPASSWORD=$POSTGRES_PASSWORD psql -h $POSTGRES_HOST -U $POSTGRES_USER -d $POSTGRES_DB -c "SELECT COUNT(*) FROM domains;"
PGPASSWORD=$POSTGRES_PASSWORD psql -h $POSTGRES_HOST -U $POSTGRES_USER -d $POSTGRES_DB -c "\dt"  # List all tables
```

## Key Tables
- `domains` - All email domains (500+ records)
- `sender_accounts` - Email inboxes/senders
- `clients` - Client accounts
- `campaigns` - Email campaigns
- `campaign_cycles` - Campaign execution cycles

## File Access
- Code: `/home/claw/work/charm-email-os/` (Docker container)
- Local: `D:\Work\charm-email-os\` (Windows host)

## API Access
- Charm API: `http://charm-api:8000` (inside Docker network)
- Health check: `curl http://charm-api:8000/health`

## Important
- ALWAYS use PostgreSQL for Charm OS data, not SQLite files
- SQLite files (charm-notes.db, etc.) are just local note-taking, not the main database
- When running in Docker container (OpenClaw), use Linux paths
- When running on Windows host, use Windows paths
