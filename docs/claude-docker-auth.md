# Claude Code Docker Authentication Guide

This guide covers authentication setup for Claude Code running inside Docker containers. It applies to all Charm Email OS workers that use Claude Code:

- **Strategy Worker** (`charm-strategy-worker`)
- **Domain Worker** (`charm-domain-worker`)
- Any future Claude Code workers

## Authentication Methods

| Method | Expires | Best For | Setup Complexity |
|--------|---------|----------|------------------|
| **Long-lived Token** | Never* | Production, automation | Medium |
| **OAuth** | ~30 days | Development, testing | Easy |
| **API Key** | Never | Pay-per-use billing | Easy |

*Long-lived tokens are tied to your Claude subscription and remain valid as long as your subscription is active.

---

## Recommended: Long-lived Token Setup

This is the **recommended method** for production Docker containers because the token never expires.

### Step 1: Generate the Token

```bash
# Exec into the container
docker exec -it <container_name> bash

# Generate a long-lived token
claude setup-token

# You'll see output like:
# Your token: sk-ant-oat01-xxxxxxxxxxxxxxxxxxxxxxxxx
```

### Step 2: Configure the Token

Save the token to the credentials file:

```bash
# Still inside the container
cat > /home/claude/.claude/.credentials.json << 'EOF'
{
  "claudeAiOauth": {
    "accessToken": "sk-ant-oat01-YOUR_TOKEN_HERE",
    "refreshToken": "",
    "expiresAt": 4102444800000,
    "scopes": ["user:inference", "user:profile", "user:sessions:claude_code"],
    "subscriptionType": "max",
    "rateLimitTier": "default_claude_max_20x"
  }
}
EOF

# Set proper permissions
chmod 600 /home/claude/.claude/.credentials.json

# Verify it works
claude -p "Say OK" --max-turns 1
```

### Step 3: Verify Persistence

The credentials are stored in a Docker volume. Verify they persist:

```bash
# Exit the container
exit

# Restart the container
docker restart <container_name>

# Check auth still works
docker exec <container_name> sh -c "claude -p 'Say OK' --max-turns 1"
```

---

## Alternative: OAuth Setup

OAuth is simpler to set up but requires re-authentication every ~30 days.

```bash
# Exec into the container
docker exec -it <container_name> bash

# Run OAuth login
claude /login

# Follow the URL printed in the terminal
# Complete the OAuth flow in your browser
# Return to the terminal - it will confirm success

# Verify it works
claude -p "Say OK" --max-turns 1
```

### OAuth Health Monitoring

Both workers include OAuth health monitoring that:
- Checks token validity on startup
- Re-checks every hour (configurable via `OAUTH_CHECK_INTERVAL`)
- Sends webhook alerts when tokens expire (configure `ALERT_WEBHOOK_URL`)
- Pauses job processing until re-authenticated
- Auto-retries failed jobs after re-authentication

---

## Alternative: Anthropic API Key

Use an API key for pay-per-use billing (instead of Claude subscription).

### Step 1: Get an API Key

1. Go to [console.anthropic.com/settings/keys](https://console.anthropic.com/settings/keys)
2. Create a new API key
3. Copy the key (starts with `sk-ant-api03-`)

### Step 2: Configure the Container

Add the API key as an environment variable:

```yaml
# In docker-compose.yml
environment:
  - ANTHROPIC_API_KEY=sk-ant-api03-your-key-here
```

Or when running directly:

```bash
docker run -d \
  -e ANTHROPIC_API_KEY=sk-ant-api03-your-key-here \
  ...
  charm-strategy-worker:latest
```

---

## Container Configuration

### Docker Compose Environment Variables

```yaml
environment:
  # Database (required)
  - POSTGRES_HOST=${POSTGRES_HOST}
  - POSTGRES_PORT=${POSTGRES_PORT:-5432}
  - POSTGRES_DB=${POSTGRES_DB:-postgres}
  - POSTGRES_USER=${POSTGRES_USER}
  - POSTGRES_PASSWORD=${POSTGRES_PASSWORD}

  # Worker configuration
  - POLL_INTERVAL=${POLL_INTERVAL:-5}
  - CLAUDE_ACCOUNT=${CLAUDE_ACCOUNT:-}

  # OAuth health monitoring
  - OAUTH_CHECK_INTERVAL=${OAUTH_CHECK_INTERVAL:-3600}  # seconds
  - ALERT_WEBHOOK_URL=${ALERT_WEBHOOK_URL:-}            # Discord/Slack webhook

  # API Key auth (alternative to OAuth)
  - ANTHROPIC_API_KEY=${ANTHROPIC_API_KEY:-}
```

### Volume Mount for Credentials

```yaml
volumes:
  # Named volume (recommended for Docker Compose)
  - charm-claude-credentials:/home/claude/.claude

  # Or bind mount (for manual Docker runs)
  # - /var/claude-credentials:/home/claude/.claude
```

### Sharing Credentials Between Workers

Use the same named volume for all Claude workers:

```yaml
# docker-compose.strategy-worker.yml
volumes:
  - charm-claude-credentials:/home/claude/.claude

# docker-compose.domain-worker.yml
volumes:
  - charm-claude-credentials:/home/claude/.claude
```

This way, authenticating once works for all workers.

---

## Webhook Alerts

Configure Discord or Slack webhooks to receive alerts when OAuth expires.

### Discord Webhook Setup

1. Server Settings → Integrations → Webhooks → New Webhook
2. Copy the webhook URL
3. Set `ALERT_WEBHOOK_URL` environment variable

### Slack Webhook Setup

1. Create an Incoming Webhook in your Slack App
2. Copy the webhook URL
3. Set `ALERT_WEBHOOK_URL` environment variable

### Alert Messages

When OAuth expires:
```
🚨 Claude OAuth Token Expired
The OAuth token for Claude Code has expired.

To fix:
docker exec -it charm-strategy-worker bash
claude /login

Worker will pause until re-authenticated.
```

When OAuth is restored:
```
ℹ️ Claude OAuth Token Restored
OAuth has been successfully re-authenticated.
Worker resuming normal operation.
```

---

## Troubleshooting

### "Invalid API key" Error

```bash
# Check if credentials file exists
docker exec <container> ls -la /home/claude/.claude/

# Check credentials content
docker exec <container> cat /home/claude/.claude/.credentials.json

# Re-authenticate
docker exec -it <container> bash
claude /login
```

### Token Expires Immediately After Setup

The `setup-token` command generates a long-lived token, but it needs to be saved to the credentials file manually. If you just ran `setup-token` without saving, the token is lost.

Re-run `setup-token` and follow Step 2 above.

### Container Can't Find Claude CLI

```bash
# Check PATH
docker exec <container> which claude

# Should return: /home/claude/.local/bin/claude

# If not found, reinstall:
docker exec -it <container> bash
curl -fsSL https://claude.ai/install.sh | bash
```

### Permission Denied Errors

Claude Code cannot run as root with `--dangerously-skip-permissions`. The container must:
- Run as non-root user `claude`
- Have credentials in `/home/claude/.claude/` (not `/root/.claude/`)

---

## Security Considerations

| Risk | Mitigation |
|------|------------|
| Token in Docker volume | Volume is not network-accessible; restrict Docker host access |
| Container exec access | Limit who can `docker exec` into containers |
| Token scope | Tokens only allow inference, not account changes |
| Webhook URLs | Don't log webhook URLs; they can be used to send messages |

### Production Recommendations

1. **Use named Docker volumes** instead of bind mounts
2. **Restrict Docker host access** to trusted operators
3. **Configure webhook alerts** to be notified of expiry
4. **Use long-lived tokens** to avoid frequent re-auth
5. **Never commit credentials** to version control

---

## Quick Reference

### Authenticate New Container (Long-lived Token)

```bash
docker exec -it <container> bash
claude setup-token
# Copy the token, then:
cat > /home/claude/.claude/.credentials.json << 'EOF'
{"claudeAiOauth":{"accessToken":"YOUR_TOKEN","refreshToken":"","expiresAt":4102444800000,"scopes":["user:inference","user:profile","user:sessions:claude_code"],"subscriptionType":"max","rateLimitTier":"default_claude_max_20x"}}
EOF
chmod 600 /home/claude/.claude/.credentials.json
exit
```

### Re-authenticate Expired OAuth

```bash
docker exec -it <container> bash
claude /login
# Follow browser OAuth flow
exit
```

### Test Authentication

```bash
docker exec <container> sh -c "claude -p 'Say OK' --max-turns 1"
```

### Check Worker Logs

```bash
docker logs -f <container>
```
