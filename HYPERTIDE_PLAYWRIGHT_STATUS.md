# Hypertide Playwright Automation - Test Status

**Last tested:** 2026-02-04 12:13 UTC

## Working Steps (Verified)

### Step 1: Load Job Data ✅
- Fetches job from database by ID
- Validates required fields (domains, provider, company)
- Test mode uses hardcoded test data

### Step 2: Login to Hypertide ✅
- Fills email and password fields
- Waits for "Place New Order" to confirm login success
- Screenshot: `step_2_login_success_*.png`

### Step 3: Start New Order ✅
- Clicks "Place New Order" button
- Screenshot: `step_3_new_order_*.png`

### Step 4: Select Provider Plan ✅
- **4a**: If `order_count > 1`, selects quantity from dropdown
  - Finds combobox within provider card via JavaScript
  - Opens dropdown, selects option matching "{N} orders"
  - Screenshot: `step_4a_order_selected_*.png`
- **4b**: Clicks "Select Plan" button for specified provider (Entra/Google)
- Waits for "Select Domains" text to confirm
- Screenshot: `step_4_provider_selected_*.png`

### Step 5: Enter Domains (BYOD) ✅
- 5a: Clicks "Use my own domains" option
- 5b: Waits for textarea to appear
- 5c: Enters domains (one per line) in textarea
- 5d: Clicks "Add Your Domain" button
- 5e: Clicks "I've configured my DNS" button (uses JS click)
- 5f: Clicks "Continue to Domain Settings" (uses JS click)
- Screenshots: `step_5a_*.png` through `step_5e_*.png`

### Step 6: Basic Configuration ✅
- Fills forwarding URL (hirecharm.com)
- Fills company name
- Clicks "Save Basic Configuration"
- Waits for "Connect Your Email Automation Tool" to confirm
- Screenshot: `step_6_basic_config_*.png`

### Step 7: Bison Email Tool Configuration ✅
- **7a**: Selects "Bison" radio button (uses JS click to avoid radio button issues)
- **7b**: Fills Bison credentials (username, password, URL)
- **7c**: Opens workspace selector ("Click to select workspace")
- **7d**: Fills API key and clicks "Fetch Workspaces"
- **7e**: Selects workspace from scrollable modal
  - **IMPORTANT**: Uses JavaScript-only clicks to avoid Playwright bug #9073
  - Bug #9073: scroll-click conflict in modals causes infinite loop
  - Solution: `element.click()` via `page.evaluate()` instead of Playwright click
- **7f**: Clicks "Move on without saving" to proceed
  - Scrolls to bottom first
  - Uses JS click with scrollIntoView
  - Verifies Step 3 (Warmup) becomes visible after
- Screenshots: `step_7a_*.png` through `step_7f_*.png`

### Step 8: Warmup Settings ✅
- Uses `_expand_and_save_section()` helper
- Expands "Step 3) Warmup & Tags Setup" accordion
- Clicks "Save Warmup & Tags Configuration"
- Toast notification confirms save
- Screenshot: `step_8_warmup_*.png`

### Step 9: Outbound Settings (Needs Testing)
- Should expand "Step 4) Outbound Settings" accordion
- Click "Save Outbound Settings"

### Step 10: Sender Names (Needs Testing)
- Should expand "Step 5) User Configuration" accordion
- Add sender names (first/last) from job data
- Click "Save User Configuration"

### Step 11: Review Order (Needs Testing)
- Navigate to review page
- Verify order summary

### Step 12: Checkout Handoff (Needs Testing)
- Click "Checkout with Stripe"
- Capture Stripe URL via response listener
- Call `handoff_checkout()` with URL

---

## Key Technical Solutions

### Playwright Bug #9073 Workaround
**Problem**: Clicking elements inside scrollable modals causes scroll position to change mid-click, creating an infinite loop.

**Solution**: Use JavaScript `element.click()` via `page.evaluate()` instead of Playwright's native `.click()`:
```python
self.page.evaluate("""
    (workspaceName) => {
        // Find element and click via JS
        const el = document.querySelector(`text=${workspaceName}`);
        el.scrollIntoView({ block: 'center' });
        el.click();
    }
""", workspace_name)
```

### Accordion Expansion Helper
**Problem**: Steps 8-10 use accordion sections that need to be expanded before interacting.

**Solution**: `_expand_and_save_section()` finds headers by "Step N)" pattern and clicks them:
```python
def _expand_and_save_section(self, section_text, save_button_text, section_num):
    # Find "Step N) Section Name" header
    # Click to expand
    # Find and click save button
```

### JavaScript Regex in Python Strings
**Problem**: Regex patterns like `/\s+/i` don't work in `page.evaluate()` - Python string escaping conflicts with JS regex.

**Solution**: Use `new RegExp()` constructor with escaped strings:
```python
# Instead of: /Workspace[\s]+/i
# Use: new RegExp('Workspace[\\\\s]+', 'i')
```

---

## Test Commands

```bash
# Full test to Step 8 (verified working)
py hypertide_playwright.py --test --dry-run --stop-after 8

# Interactive mode (pause between steps)
py hypertide_playwright.py --test --dry-run --interactive

# Keep browser open after completion
py hypertide_playwright.py --test --dry-run --stop-after 8 --pause

# Single step test
py hypertide_playwright.py --test --dry-run --step 7

# Test dropdown selection with 6 orders (generates 12 domains)
py hypertide_playwright.py --test --dry-run --stop-after 4 --order-count 6 --pause

# Test with real job from database
py hypertide_playwright.py --job-id <JOB_ID> --dry-run --stop-after 4 --pause
```

### Job Fields Used

| Field | Source | Default | Description |
|-------|--------|---------|-------------|
| `entra_orders` | Database | 0 | Number of Entra orders (used when provider_type="entra") |
| `google_orders` | Database | 0 | Number of Google orders (used when provider_type="google") |
| `provider_type` | Database | "entra" | "entra" or "google" |
| `domain_names` | Database | [] | Array of domain names (must match orders × domains_per_order) |

**Domain requirements:**
- Entra: 2 domains per order (6 orders = 12 domains)
- Google: 5 domains per order (5 orders = 25 domains)

---

## Files Modified

- `hypertide_playwright.py` - Main automation script
  - Fixed regex syntax in workspace verification (line ~1290)
  - Added `_expand_and_save_section()` helper
  - Added Step 7f "Move on without saving" click
  - Added `--pause` flag for browser inspection
