# Cloudflare Tunnel Setup Guide

This guide sets up a Cloudflare Tunnel to expose local services (like the Slack webhook endpoint) to the internet with a stable URL.

## Why Use Cloudflare Tunnel?

- **Stable URLs** - No more ngrok URL changes
- **Swap backends** - Point to local dev or production without changing Slack config
- **Built-in SSL** - Automatic HTTPS certificates
- **Zero Trust ready** - Can add authentication later

## Prerequisites

- Cloudflare account with `laviefatigue.com` (or your domain) added
- Domain DNS managed by Cloudflare

---

## Step 1: Install cloudflared

```powershell
# Windows (via winget)
winget install cloudflare.cloudflared

# Or download from: https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/downloads/
```

Verify installation:
```powershell
cloudflared --version
```

---

## Step 2: Authenticate with Cloudflare

```powershell
cloudflared tunnel login
```

This opens a browser to authenticate. Select your domain (`laviefatigue.com`).

A certificate is saved to: `C:\Users\ellio\.cloudflared\cert.pem`

---

## Step 3: Create the Tunnel

```powershell
cloudflared tunnel create charm-services
```

This outputs:
```
Tunnel credentials written to C:\Users\ellio\.cloudflared\<TUNNEL_ID>.json
Created tunnel charm-services with id <TUNNEL_ID>
```

**Save the TUNNEL_ID** - you'll need it for DNS routing.

---

## Step 4: Configure DNS Routes

Route your subdomain to the tunnel:

```powershell
# Replace <TUNNEL_ID> with your actual tunnel ID from Step 3
cloudflared tunnel route dns charm-services slack-hooks.laviefatigue.com
```

This creates a CNAME record in Cloudflare DNS pointing to your tunnel.

---

## Step 5: Update Config File

Edit `cloudflared/config.yml` and update the credentials file path if needed:

```yaml
tunnel: charm-services
credentials-file: C:\Users\ellio\.cloudflared\<TUNNEL_ID>.json  # Update with actual filename

ingress:
  - hostname: slack-hooks.laviefatigue.com
    service: http://localhost:8000
  - service: http_status:404
```

---

## Step 6: Test the Tunnel

Start the tunnel:
```powershell
cloudflared tunnel --config D:\Work\charm-email-os\cloudflared\config.yml run
```

Test it:
```powershell
curl https://slack-hooks.laviefatigue.com/health
```

Should return the API health status.

---

## Step 7: Run as Windows Service (Optional)

For persistent operation, install as a Windows service:

```powershell
# Run as Administrator
cloudflared service install --config D:\Work\charm-email-os\cloudflared\config.yml
```

Or add to docker-compose (see below).

---

## Docker Compose Integration

Add to `docker-compose.local.yml`:

```yaml
  cloudflared:
    image: cloudflare/cloudflared:latest
    container_name: charm-cloudflared
    restart: unless-stopped
    command: tunnel --config /etc/cloudflared/config.yml run
    volumes:
      - ./cloudflared/config.yml:/etc/cloudflared/config.yml:ro
      - C:/Users/ellio/.cloudflared:/etc/cloudflared/creds:ro
    environment:
      - TUNNEL_TOKEN=${CLOUDFLARE_TUNNEL_TOKEN}
    networks:
      - charm-network
```

---

## Configure Slack App

1. Go to [Slack API Dashboard](https://api.slack.com/apps)
2. Select your app (or create one)
3. Navigate to **Interactivity & Shortcuts**
4. Enable **Interactivity**
5. Set **Request URL** to:
   ```
   https://slack-hooks.laviefatigue.com/api/slack/interactions
   ```
6. Save Changes

**Current Configuration (2026-02-13):**
- Tunnel ID: `7a0e85d6-5c45-485e-889c-95d665aeca0b`
- Webhook URL: `https://slack-hooks.laviefatigue.com/api/slack/interactions`
- Handler: `api/routes/slack_webhooks.py`

---

## Adding More Services

To expose additional services, add entries to `cloudflared/config.yml`:

```yaml
ingress:
  # Slack webhooks
  - hostname: slack-hooks.laviefatigue.com
    service: http://localhost:8000

  # Full API access
  - hostname: api.laviefatigue.com
    service: http://localhost:8000

  # Frontend
  - hostname: charm.laviefatigue.com
    service: http://localhost:3000

  # Prefect UI
  - hostname: prefect.laviefatigue.com
    service: http://localhost:4200

  # Catch-all
  - service: http_status:404
```

Then add DNS routes:
```powershell
cloudflared tunnel route dns charm-services api.laviefatigue.com
cloudflared tunnel route dns charm-services charm.laviefatigue.com
```

---

## Troubleshooting

### Check tunnel status
```powershell
cloudflared tunnel info charm-services
```

### View logs
```powershell
cloudflared tunnel --config D:\Work\charm-email-os\cloudflared\config.yml run --loglevel debug
```

### DNS not resolving
- Check Cloudflare DNS dashboard for CNAME record
- Ensure tunnel is running
- May take 1-2 minutes for DNS propagation

### Connection refused
- Ensure local service is running on the configured port
- Check Docker network connectivity if using containers

---

## Quick Reference

| Service | Local URL | Public URL |
|---------|-----------|------------|
| Slack Webhooks | http://localhost:8000/api/slack/interactions | https://slack-hooks.laviefatigue.com/api/slack/interactions |
| API | http://localhost:8000 | https://api.laviefatigue.com |
| Frontend | http://localhost:3000 | https://charm.laviefatigue.com |

---

## Security Notes

- The tunnel only exposes what you configure in `ingress`
- Consider adding [Cloudflare Access](https://developers.cloudflare.com/cloudflare-one/policies/access/) for sensitive endpoints
- Slack webhooks should validate signatures (already implemented in `slack_webhooks.py`)
