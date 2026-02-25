# Strategy Worker VPS Deployment Guide (DEPRECATED)

> **⚠️ DEPRECATED**: VPS deployments are no longer active. The strategy worker now runs locally via Docker. See [[../local-development/workers]] for the current localhost-first setup.

---

*Legacy documentation below - for reference only*

Deploy the AI-powered strategy generation worker on a remote VPS using Docker (ClaudeBox) and Prefect.

## Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│  VPS (31.97.142.123)                                                        │
│                                                                             │
│  ┌──────────────────────────────────────┐  ┌─────────────────────────────┐ │
│  │     Prefect Worker                   │  │   ClaudeBox Container       │ │
│  │                                      │  │                             │ │
│  │  Polls Prefect server for runs      │  │  - Claude Code CLI          │ │
│  │  Triggers strategy generation       │  │  - MCP Server               │ │
│  │  Monitors job status                ├──►  - Cold Email Skill         │ │
│  │                                      │  │  - Database connection      │ │
│  └──────────────────────────────────────┘  └─────────────────────────────┘ │
│                    │                                     │                  │
│                    │                                     │                  │
│  ┌─────────────────▼─────────────────────────────────────▼────────────────┐│
│  │                        Supabase PostgreSQL                              ││
│  │                   aws-0-us-east-1.pooler.supabase.com                  ││
│  └─────────────────────────────────────────────────────────────────────────┘│
│                                                                             │
│  Prefect Server: https://prefect.laviefatigue.com                          │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Prerequisites

1. VPS with Docker installed
2. Prefect server running at `https://prefect.laviefatigue.com`
3. Claude Pro/Max account for authentication
4. Database credentials

## Step 1: Clone Repository on VPS

```bash
ssh root@31.97.142.123

# Clone the repo
cd /opt
git clone <your-repo-url> charm-email-os
cd charm-email-os
```

## Step 2: Install ClaudeBox

ClaudeBox provides containerized Claude Code with persistent authentication.

```bash
# Install claudebox
curl -fsSL https://raw.githubusercontent.com/RchGrav/claudebox/main/install.sh | bash

# Or manual install
git clone https://github.com/RchGrav/claudebox.git ~/.claudebox-install
cd ~/.claudebox-install && ./install.sh
```

## Step 3: Initialize ClaudeBox for Charm Email OS

```bash
cd /opt/charm-email-os

# Initialize claudebox project
claudebox init

# Install required profiles
claudebox profile install python

# Build the container
claudebox build
```

## Step 4: Authenticate Claude Code

```bash
# Enter the container shell
claudebox shell

# Inside container: authenticate with Claude
claude /login

# Follow browser prompts to authenticate
# This stores credentials in ~/.claudebox/charm-email-os/claude/

# Exit container
exit
```

## Step 5: Configure Environment

Create `.env` file for the worker:

```bash
cat > /opt/charm-email-os/.env << 'EOF'
# Database (Supabase)
POSTGRES_HOST=aws-0-us-east-1.pooler.supabase.com
POSTGRES_PORT=6543
POSTGRES_DB=postgres
POSTGRES_USER=postgres.lhnzdotfevttijwyfcib
POSTGRES_PASSWORD=<your-password>

# Prefect
PREFECT_API_URL=https://prefect.laviefatigue.com/api

# Claude (used inside container)
CLAUDE_ACCOUNT=default
EOF

chmod 600 /opt/charm-email-os/.env
```

## Step 6: Update Worker for Docker Execution

The worker needs to run Claude commands inside the Docker container. Update `strategy_worker_prefect.py`:

```python
# Docker execution mode
USE_DOCKER = os.getenv("USE_DOCKER", "true").lower() == "true"

def run_claude_code(...):
    if USE_DOCKER:
        # Run inside claudebox container
        cmd = [
            "claudebox", "run",
            "claude", "-p", prompt,
            "--dangerously-skip-permissions",
            "--mcp-config", "/workspace/strategy_mcp_config.json",
        ]
    else:
        # Direct execution
        cmd = ["claude", "-p", prompt, ...]
```

## Step 7: Install Prefect Worker

```bash
# Install Python dependencies
cd /opt/charm-email-os
python3 -m venv venv
source venv/bin/activate
pip install -r requirements-worker.txt

# Configure Prefect
export PREFECT_API_URL=https://prefect.laviefatigue.com/api

# Deploy flows
prefect deploy --all
```

## Step 8: Start Prefect Worker

```bash
# Start worker (connects to work pool)
prefect worker start --pool default-agent-pool
```

Or run as a systemd service:

```bash
cat > /etc/systemd/system/prefect-worker.service << 'EOF'
[Unit]
Description=Prefect Worker for Charm Email OS
After=network.target docker.service

[Service]
Type=simple
User=root
WorkingDirectory=/opt/charm-email-os
Environment=PREFECT_API_URL=https://prefect.laviefatigue.com/api
ExecStart=/opt/charm-email-os/venv/bin/prefect worker start --pool default-agent-pool
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable prefect-worker
systemctl start prefect-worker
```

## Step 9: Test the Setup

### Test 1: Direct ClaudeBox Command

```bash
cd /opt/charm-email-os
claudebox run claude -p "Hello, world" --print
```

### Test 2: Create Test Job

```bash
# Insert a test job directly
psql "postgres://postgres.lhnzdotfevttijwyfcib:PASSWORD@aws-0-us-east-1.pooler.supabase.com:6543/postgres" << 'EOF'
INSERT INTO strategy_generation_jobs (client_id, status)
SELECT id, 'pending'
FROM clients
LIMIT 1;
EOF
```

### Test 3: Trigger via Prefect

```bash
# From your local machine
prefect deployment run 'process-pending-strategy-jobs/strategy-process-pending'
```

### Test 4: Check Prefect UI

Visit `https://prefect.laviefatigue.com` and verify:
- Flow runs appear
- Worker is connected
- Logs show Claude Code execution

## Troubleshooting

### Claude Not Authenticated

```bash
claudebox shell
claude /login
# Re-authenticate
```

### Docker Permission Issues

```bash
# Add user to docker group
usermod -aG docker $USER
newgrp docker
```

### Prefect Connection Issues

```bash
# Check API URL
export PREFECT_API_URL=https://prefect.laviefatigue.com/api
prefect config view

# Test connection
prefect work-pool ls
```

### Database Connection Issues

```bash
# Test database connection
psql "postgres://user:pass@host:port/db" -c "SELECT 1"
```

## Flow Deployments

| Deployment | Purpose | Trigger |
|------------|---------|---------|
| `strategy-single-job` | Process specific job | API/Webhook |
| `strategy-process-pending` | Batch process pending | Manual/Scheduled |
| `strategy-poll-scheduled` | Continuous polling | Cron (hourly) |
| `strategy-quick-check` | Quick check (3 jobs max) | Cron (every 5 min) |

## Monitoring

### View Worker Logs

```bash
journalctl -u prefect-worker -f
```

### View Container Logs

```bash
docker logs -f $(docker ps -q --filter "name=claudebox")
```

### View Prefect Flow Runs

Visit `https://prefect.laviefatigue.com` or:

```bash
prefect flow-run ls --limit 10
```

## Triggering from Anywhere

Once deployed, you can trigger strategy generation from:

1. **Prefect UI**: Click "Run" on any deployment
2. **Prefect CLI**: `prefect deployment run 'flow/deployment'`
3. **API**: `POST https://prefect.laviefatigue.com/api/deployments/{id}/create_flow_run`
4. **Charm Frontend**: Click "Trigger Generation" on Profile page

## Security Notes

- Claude credentials stored in `~/.claudebox/charm-email-os/`
- Database password in `.env` file (chmod 600)
- Prefect API behind Cloudflare Access if configured
- ClaudeBox uses network isolation/firewall rules
