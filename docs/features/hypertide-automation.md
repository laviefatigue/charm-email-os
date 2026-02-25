---
title: Hypertide Inbox Automation
created: 2026-02-13
updated: 2026-02-23
selector_mapping_date: 2026-02-13
tags: [feature, hypertide, automation, inboxes, playwright, selectors, capacity]
---

# Hypertide Inbox Automation

Browser automation for purchasing inbox infrastructure from Hypertide using Playwright.

## Overview

This automation handles the complete Hypertide order flow:
1. Choose Plan (Entra or Google)
2. Select Domains (Purchase or BYOD)
3. Setup Domain Settings
4. Review Order
5. Stripe Checkout

## Architecture

```
InboxProvisionModal (Frontend)
    ↓
POST /api/inbox-purchasing/smart-order
    ↓
inbox_purchase_jobs table (status='pending')
    ↓
hypertide_worker.py polls for jobs
    ↓
HypertideClient (Playwright browser)
    ↓
PurchaseAutomation (purchase.py)
```

## Plan Comparison

| Aspect | Hypertide Entra | Hypertide Google |
|--------|-----------------|------------------|
| Price | $50/month | $50/month |
| Domains per order | 2 | 5 |
| Inboxes per domain | 50 | 3 |
| Total inboxes | 100 | 15 |
| Emails/day/inbox | 2 | 15-20 |
| Monthly capacity | 5,000 emails | 5,000+ emails |
| Best for | B2B outreach at scale | Personal email deliverability |
| DNS warning | Disconnect Microsoft tenant | Disconnect Google Workspace |

## Capacity Tracking (2026-02-23)

Database views track HyperTide infrastructure capacity per domain and client.

### Expected Capacity per Domain

| Provider | Inboxes | Emails/Day/Inbox | Daily Capacity |
|----------|---------|------------------|----------------|
| **Entra** | 50 | 2 | 100 emails/day |
| **Google** | 3 | 20 | 60 emails/day |

### Views Available

| View | Purpose |
|------|---------|
| `v_domain_capacity` | Per-domain capacity vs expected |
| `v_client_capacity` | Client packages vs actual with gap analysis |
| `v_hypertide_order_queue` | Orders needed to fill capacity gaps |
| `v_workspace_volume` | Raw volume (no package required) |

### Client Packages

Stored in `client_subscriptions`:

```sql
entra_packages: 6          -- HyperTide Entra orders purchased
entra_domains_per_package: 2  -- Default
entra_inboxes_per_domain: 52  -- Default (50 + buffer)
google_packages: 5         -- HyperTide Google orders purchased
google_domains_per_package: 5 -- Default
google_inboxes_per_domain: 3  -- Default
spare_ratio: 0.15          -- 15% pipeline buffer target
```

### Order Queue Query

```sql
-- Find clients needing more HyperTide orders
SELECT client_name, provider_type, domain_gap, orders_needed
FROM v_hypertide_order_queue
WHERE orders_needed > 0;
```

See [[health-monitoring#HyperTide Capacity Tracking]] for full documentation.

## UI Selectors (Updated 2026-02-13)

These selectors were captured via Chrome DevTools inspection of `app2.hypertide.io`.

### Step 1: Choose Plan (`/choose-plan`)

```python
SELECTORS_CHOOSE_PLAN = {
    # Plan headings
    "entra_plan_heading": "heading:has-text('Hypertide Entra')",
    "google_plan_heading": "heading:has-text('Hypertide Google')",

    # Quantity dropdowns
    "entra_quantity_dropdown": "combobox:near(:text('Hypertide Entra'))",
    "google_quantity_dropdown": "combobox:near(:text('Hypertide Google'))",

    # Select buttons
    "entra_select_btn": "button:has-text('Select Plan'):near(:text('Hypertide Entra'))",
    "google_select_btn": "button:has-text('Select Plan'):near(:text('Hypertide Google'))",
}
```

### Step 2: Select Domains (`/select-domains`)

```python
SELECTORS_SELECT_DOMAINS = {
    # Domain source options
    "purchase_domains_option": "heading:has-text('Purchase domains')",
    "use_own_domains_option": "heading:has-text('Use my own domains')",

    # Domain input (multiline textarea)
    "domain_input": "textbox[placeholder*='example1.com']",
    "add_domain_btn": "button:has-text('Add Your Domain')",
    "max_domains_indicator": "button:has-text('Max Domains Added')",

    # DNS configuration (BYOD only)
    "dns_confirmed_btn": "button:has-text('I have configured DNS')",
    "dns_completed_indicator": "button:has-text('✓ Completed')",

    # Navigation
    "continue_to_settings": "button:has-text('Continue to Domain Settings')",
    "go_back_btn": "button:has-text('Go Back')",
}
```

### Step 3: Setup Domain Settings (`/setup-domain-settings`)

```python
SELECTORS_DOMAIN_SETTINGS = {
    # Step 1: Basic Configuration
    "forwarding_url_input": "textbox[placeholder*='example.com']",
    "company_client_input": "textbox[placeholder*='Acme Corp']",
    "save_basic_config_btn": "button:has-text('Save Basic Configuration')",

    # Step 2: Email Tool Connection
    "saved_credentials_btn": "button:has-text('Access your saved credentials')",
    "tool_instantly": "text=Instantly",
    "tool_smartlead": "text=Smartlead",
    "tool_bison": "text=Bison",
    "tool_other": "text=Other",

    # Bison-specific fields (common)
    "bison_username_input": "textbox[placeholder*='name@example.com']",
    "bison_password_input": "textbox[placeholder*='Enter your password']",
    "bison_url_input": "textbox[placeholder*='send.example.com']",

    # Bison-specific fields (Google only)
    "bison_app_id_input": "textbox[placeholder*='Enter your app ID']",  # Google OAuth Client ID
    "masterinbox_checkbox": "checkbox:near(:text('Add inboxes to masterinbox.com'))",

    # Credential save options
    "save_credentials_btn": "button:has-text('Save Your Credentials For Future Use')",
    "move_on_without_saving": "button:has-text('Move on without saving')",

    # Step 3: Warmup & Tags Setup
    "disable_warmup_checkbox": "checkbox:near(:text('Disable Warmup'))",
    "warmup_limit_input": "spinbutton:near(:text('Warmup Limit'))",
    "save_warmup_btn": "button:has-text('Save Warmup & Tags Configuration')",

    # Step 4: Outbound Settings
    "daily_limit_input": "spinbutton:near(:text('Daily Limit'))",
    "save_outbound_btn": "button:has-text('Save Outbound Settings')",

    # Step 5: User Configuration
    "first_name_input": "textbox[placeholder*='first name']",
    "last_name_input": "textbox[placeholder*='last name']",
    "add_user_btn": "button:has-text('+ Add User')",

    # Google-only: Profile Picture
    "profile_picture_input": "textbox[placeholder*='drive.google.com']",  # Google Drive link

    # Final navigation
    "save_continue_review": "button:has-text('Save & Continue to Review')",
    "continue_to_review": "button:has-text('Continue to Review')",
}
```

### Step 4: Review Order (`/review-order`)

```python
SELECTORS_REVIEW = {
    "go_back_btn": "button:has-text('Go Back')",
    "proceed_checkout": "button:has-text('Proceed to Checkout')",
    "checkout_btn": "button:has-text('Checkout with Stripe')",
}
```

### Step 5: Stripe Checkout

```python
SELECTORS_STRIPE = {
    "stripe_iframe": "iframe[src*='stripe']",
    "card_number": "[name='cardNumber']",
    "card_expiry": "[name='cardExpiry']",
    "card_cvc": "[name='cardCvc']",
    "billing_zip": "[name='billingPostalCode']",
    "pay_button": "button:has-text('Pay')",
}
```

## Flow Differences: Entra vs Google

### Select Domains Step

**Entra (2 domains required):**
```
Step 2) Enter Your Entra Domains (2 required for 1 order set)
...
at least 2 Entra domains to proceed
```

**Google (5 domains required):**
```
Step 2) Enter your Google Domains (5 required for 1 order set)
...
at least 5 Google domains to proceed
```

### DNS Warning

**Entra:**
> Disconnect any existing Microsoft tenant connections first.

**Google:**
> Disconnect any existing Google Workspace connections first.

### User Configuration Output

**Entra:**
```
50 inboxes per domain (100 total)
Inboxes are distributed evenly among users (50 Entra inboxes total per domain)
```

**Google:**
```
3 inboxes per domain (15 total)
Inboxes are distributed evenly among users (3 Google inboxes total per domain)
```

## Key Files

| File | Purpose |
|------|---------|
| `Hypertide/automation/src/hypertide_automation/purchase.py` | Main automation + selectors |
| `Hypertide/automation/src/hypertide_automation/client.py` | HypertideClient - Playwright wrapper |
| `Hypertide/automation/src/hypertide_automation/models.py` | Data models (OrderRequest, etc.) |
| `hypertide_worker.py` | Standalone worker (polls DB) |
| `api/routes/inbox_purchasing.py` | API endpoint + background task |

## Variable Mapping (Updated 2026-02-13)

> **Last Crawled**: 2026-02-13
> **Target URL**: `app2.hypertide.io`
> **Next Review**: Recrawl if Hypertide UI changes or selectors fail

### Variable Sources

Variables come from two sources:
1. **ENV** - Static credentials, same for all orders
2. **Database** - Dynamic per-client/order values from `inbox_purchase_jobs`

### Complete Field Mapping

#### Step 2: Select Domains

| Form Field | Source | Value |
|------------|--------|-------|
| Domain list | Database | `job.domain_names[]` (text array) |

#### Step 3: Setup Domain Settings

| Form Field | Source | Database Field / ENV Var |
|------------|--------|--------------------------|
| Forwarding URL | Database | `job.forwarding_domain` |
| Company/Client | Database | `job.company_name` |
| Bison URL (modal) | ENV | `EMAILBISON_API_URL` |
| API Key (modal) | ENV | `EMAILBISON_API_KEY` |
| Workspace (select) | Database | `job.bison_workspace_name` → click matching name |
| Username | ENV | `EMAILBISON_USERNAME` |
| Password | ENV | `EMAILBISON_PASSWORD` |
| Bison App ID (Google) | Database | `job.bison_app_id` |
| First Name | Database | `job.sender_names[0].firstName` |
| Last Name | Database | `job.sender_names[0].lastName` |

#### Step 5: Stripe Checkout

| Form Field | Source | ENV Var |
|------------|--------|---------|
| Card Number | ENV | `STRIPE_CARD_NUMBER` |
| Expiry | ENV | `STRIPE_CARD_EXP` |
| CVC | ENV | `STRIPE_CARD_CVC` |
| ZIP | ENV | `STRIPE_CARD_ZIP` |

### Database Schema Reference

```sql
-- inbox_purchase_jobs table (key fields)
company_name        TEXT      -- Client name for Basic Configuration
forwarding_domain   TEXT      -- Forwarding URL (e.g., "charmrecruiting.com")
bison_workspace_name TEXT     -- Workspace to select in modal (e.g., "Charm")
bison_url           TEXT      -- (Deprecated - use ENV instead)
bison_api_key       TEXT      -- (Deprecated - use ENV instead)
bison_app_id        TEXT      -- Google OAuth Client ID (Google orders only)
domain_names        TEXT[]    -- Array of domains for the order
sender_names        JSONB     -- User names: [{"firstName": "Chris", "lastName": "Booth"}]
provider_type       TEXT      -- "entra" or "google"
```

### Workspace Selection Flow

The Email Tool Connection step requires fetching workspaces from EmailBison:

```python
# 1. Click "Bison" tool option
await page.click("text=Bison")

# 2. Fill API credentials in the modal
await page.fill("[placeholder*='send.example.com']", os.getenv("EMAILBISON_API_URL"))
await page.fill("[placeholder*='API Key']", os.getenv("EMAILBISON_API_KEY"))

# 3. Click "Fetch Workspaces"
await page.click("button:has-text('Fetch Workspaces')")

# 4. Wait for workspace list and click matching workspace
workspace_name = job.bison_workspace_name  # e.g., "Charm"
await page.click(f"text={workspace_name}")

# 5. Fill login credentials
await page.fill("[placeholder*='name@example.com']", os.getenv("EMAILBISON_USERNAME"))
await page.fill("[placeholder*='Enter your password']", os.getenv("EMAILBISON_PASSWORD"))

# 6. ALWAYS skip saving credentials
await page.click("button:has-text('Move on without saving')")
```

### sender_names JSON Format

```json
[
  {
    "firstName": "Chris",
    "lastName": "Booth",
    "emailPrefix": "chris.booth",
    "source": "generated"
  },
  {
    "firstName": "Sarah",
    "lastName": "Miller",
    "emailPrefix": "sarah.miller",
    "source": "generated"
  }
]
```

For automation, use the first sender: `sender_names[0].firstName` and `sender_names[0].lastName`.

## Environment Variables

```bash
# Hypertide credentials (login to app2.hypertide.io)
HYPERTIDE_EMAIL=your-email@example.com
HYPERTIDE_PASSWORD=your-password

# EmailBison API credentials (for workspace fetch)
EMAILBISON_API_URL=https://spellcast.hirecharm.com
EMAILBISON_API_KEY=your-api-key

# EmailBison login credentials (for Bison tool connection)
EMAILBISON_USERNAME=your-bison-email
EMAILBISON_PASSWORD=your-bison-password

# Stripe payment (for checkout)
STRIPE_CARD_NUMBER=4242424242424242
STRIPE_CARD_EXP=12/30
STRIPE_CARD_CVC=123
STRIPE_CARD_ZIP=10001

# Worker config
HYPERTIDE_HEADLESS=true
```

## Testing

### Local Test Script

```bash
cd D:\Work\charm-email-os\Hypertide\automation

# Set credentials
set HYPERTIDE_EMAIL=your-email
set HYPERTIDE_PASSWORD=your-password

# Run tests (visible browser)
py test_reliability.py
```

### Test Coverage

1. **Config loading** - Verify env vars
2. **Health check** - Site accessibility
3. **Session validation** - Auth state
4. **Login detection** - Signin page detection
5. **Navigation with retry** - Robust navigation
6. **Retry mechanism** - Timeout handling
7. **Auto-login** - Credential-based login
8. **Full flow dry run** - End-to-end without purchase

## Automation Flow (BYOD Mode)

### Entra Order (2 domains)

```python
async def execute_entra_order(domains: list[str], config: OrderConfig):
    # Step 1: Choose Plan
    await page.click("button:has-text('Select Plan'):near(:text('Hypertide Entra'))")

    # Step 2: Select Domains (BYOD)
    await page.click("heading:has-text('Use my own domains')")
    await page.fill("textbox[placeholder*='example1.com']", "\n".join(domains))
    await page.click("button:has-text('Add Your Domain')")
    await page.click("button:has-text('I have configured DNS')")
    await page.click("button:has-text('Continue to Domain Settings')")

    # Step 3: Setup Settings
    await page.fill("textbox[placeholder*='example.com']", config.forwarding_url)
    await page.fill("textbox[placeholder*='Acme Corp']", config.client_name)
    await page.click("button:has-text('Save Basic Configuration')")
    await page.click("button:has-text('Move on without saving')")
    await page.click("button:has-text('Save Warmup & Tags Configuration')")
    await page.click("button:has-text('Save Outbound Settings')")
    await page.fill("textbox[placeholder*='first name']", config.user_first_name)
    await page.fill("textbox[placeholder*='last name']", config.user_last_name)
    await page.click("button:has-text('+ Add User')")
    await page.click("button:has-text('Save & Continue to Review')")

    # Step 4: Review & Checkout
    await page.click("button:has-text('Checkout with Stripe')")

    # Step 5: Stripe Payment
    await fill_stripe_form(config.stripe_credentials)
```

### Google Order (5 domains)

```python
async def execute_google_order(domains: list[str], config: OrderConfig):
    # Step 1: Choose Plan
    await page.click("button:has-text('Select Plan'):near(:text('Hypertide Google'))")

    # Step 2: Select Domains (BYOD) - 5 domains required
    await page.click("heading:has-text('Use my own domains')")
    await page.fill("textbox[placeholder*='example1.com']", "\n".join(domains))
    await page.click("button:has-text('Add Your Domain')")
    await page.click("button:has-text('I have configured DNS')")
    await page.click("button:has-text('Continue to Domain Settings')")

    # Step 3: Setup Settings
    await page.fill("textbox[placeholder*='example.com']", config.forwarding_url)
    await page.fill("textbox[placeholder*='Acme Corp']", config.client_name)
    await page.click("button:has-text('Save Basic Configuration')")

    # Google requires Bison App ID (OAuth Client ID format)
    await page.fill("textbox[placeholder*='Enter your app ID']", config.bison_app_id)
    await page.click("button:has-text('Move on without saving')")

    await page.click("button:has-text('Save Warmup & Tags Configuration')")
    await page.click("button:has-text('Save Outbound Settings')")  # Default: 2 emails/day

    await page.fill("textbox[placeholder*='first name']", config.user_first_name)
    await page.fill("textbox[placeholder*='last name']", config.user_last_name)
    await page.click("button:has-text('+ Add User')")

    # Optional: Profile picture (Google Drive link)
    if config.profile_picture_url:
        await page.fill("textbox[placeholder*='drive.google.com']", config.profile_picture_url)

    await page.click("button:has-text('Save & Continue to Review')")

    # Step 4: Review & Checkout
    await page.click("button:has-text('Checkout with Stripe')")

    # Step 5: Stripe Payment
    await fill_stripe_form(config.stripe_credentials)
```

**Key differences from Entra:**
- 5 domains required (vs 2)
- Bison App ID field required (Google OAuth Client ID format: `123456789-abc.apps.googleusercontent.com`)
- Profile Picture option (Google Drive link)
- 3 inboxes/domain (vs 50)
- Daily limit default: 2 (vs higher for Entra)

## Known Issues

1. **Password selector changed** - Login page password field uses label "Password*" not placeholder
2. **DNS button sometimes unclickable** - May need JavaScript click fallback
3. **Session expires mid-flow** - Automation detects and re-authenticates
4. **Corrupted saved credentials** - If "Save Your Credentials" was used with incorrect data, the saved values may be corrupted (e.g., password and URL concatenated). **Solution**: Always use "Move on without saving" and enter fresh credentials from ENV variables each time.

## Recrawl Checklist

If selectors start failing, recrawl the Hypertide UI:

1. Check `selector_mapping_date` in frontmatter
2. Navigate through each step with Chrome DevTools MCP
3. Update selectors in this doc and in `purchase.py`
4. Update `selector_mapping_date` and `updated` fields
5. Run `test_reliability.py` to validate

## Related

- [[domain-purchasing]] - Domain sourcing before inbox provisioning
- [[../architecture/api-endpoints]] - API documentation
- [[../infrastructure/coolify]] - Production deployment
