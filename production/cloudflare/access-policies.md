# Cloudflare Access Policies

## Identity Provider

| Provider | Type | Allowed Domain |
|----------|------|----------------|
| Google | OAuth | @hirecharm.com |

## Application Policies

### Charm Frontend (app.wizardgrimoire.cloud)

| Policy | Rules |
|--------|-------|
| Allow HireCharm | Emails ending in @hirecharm.com |
| Service Token | Charm API Automation token |

### Executive Dashboard (dashboard.wizardgrimoire.cloud)

| Policy | Rules |
|--------|-------|
| Allow HireCharm | Emails ending in @hirecharm.com |

### Coolify Panel (coolify.wizardgrimoire.cloud)

| Policy | Rules |
|--------|-------|
| Allow HireCharm | Emails ending in @hirecharm.com |

## API Endpoint (api.wizardgrimoire.cloud)

**No Access Policy** - Intentionally unprotected.

Rationale:
- Browser-based frontend cannot add service token headers to fetch() requests
- Adding Access to API would block all frontend functionality
- Security provided by:
  - Cloudflare Tunnel (VPS IP hidden)
  - UFW Firewall (only SSH allowed)
  - No direct port access possible

## Service Token Usage

For automated/programmatic access to protected endpoints:

```bash
# Headers required
CF-Access-Client-Id: 2d248ecd21fc2106dac566160e1d73b3.access
CF-Access-Client-Secret: {secret}

# Example curl
curl -H "CF-Access-Client-Id: 2d248ecd21fc2106dac566160e1d73b3.access" \
     -H "CF-Access-Client-Secret: {secret}" \
     https://app.wizardgrimoire.cloud/some-endpoint
```

## Adding New Applications

1. Go to Cloudflare Zero Trust Dashboard
2. Access > Applications > Add an application
3. Select "Self-hosted"
4. Configure:
   - Application name
   - Session duration (24h recommended)
   - Application domain (subdomain.wizardgrimoire.cloud)
5. Add policy:
   - Policy name: "Allow HireCharm"
   - Action: Allow
   - Include: Emails ending in @hirecharm.com

## Removing Access (if needed)

```bash
# List all Access apps
curl -X GET "https://api.cloudflare.com/client/v4/accounts/edc3f397f5bf38a27120797e8f1b361a/access/apps" \
     -H "Authorization: Bearer {api_token}" | jq '.result[] | {id, name, domain}'

# Delete specific app
curl -X DELETE "https://api.cloudflare.com/client/v4/accounts/edc3f397f5bf38a27120797e8f1b361a/access/apps/{app_id}" \
     -H "Authorization: Bearer {api_token}"
```
