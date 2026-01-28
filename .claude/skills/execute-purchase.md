# Skill: Execute Hypertide Inbox Purchase

You are executing an inbox purchase order on Hypertide (app2.hypertide.io).
You have browser automation tools to navigate and interact with the Hypertide web UI.
You have database tools to read your job data and log progress.

## CRITICAL SAFETY RULES

1. **ONLY use data from the job record** - Never invent or guess values
2. **Take a screenshot and log EVERY step** via `log_step` - This creates the audit trail
3. **If workspace name not found in dropdown: FAIL IMMEDIATELY** - This prevents cross-contamination of inboxes between clients
4. **If any step shows unexpected content: FAIL with screenshot** - Do not try to recover from unknown states
5. **If payment fails: FAIL with "Payment failed" error** - Never retry payment automatically
6. **Never navigate away from Hypertide** - Only use app2.hypertide.io URLs

## EXECUTION STEPS

### Step 1: Load Job Data

```
Call: get_purchase_job(job_id)
```

Extract these fields from the response:
- `hypertide_email` - Login email for Hypertide
- `hypertide_password` - Login password for Hypertide
- `provider_type` - "entra" or "google"
- `domain_names` - Array of domain names to provision
- `forwarding_domain` - Client's main domain (e.g., "hirecharm.com")
- `company_name` - Client company name
- `bison_username` - EmailBison login email
- `bison_password` - EmailBison login password
- `bison_workspace_name` - EXACT workspace name to select (e.g., "Charm")
- `bison_url` - EmailBison URL (e.g., "https://send.hirecharm.com")
- `sender_names` - JSON array of {firstName, lastName} for inbox user configuration
- `use_saved_payment` - Whether to use saved payment method

Then update status:
```
Call: update_job_status(job_id, "processing", "Loading job data")
```

### Step 2: Login to Hypertide

```
Call: navigate("https://app2.hypertide.io/signin")
Call: log_step(job_id, "login_page", notes="Navigated to Hypertide signin page")
```

Fill the login form:
```
Call: fill("input[type='email']", hypertide_email)
Call: fill("input[type='password']", hypertide_password)
Call: click("button[type='submit']")
```

Wait for dashboard to load:
```
Call: wait_for_text("Place New Order", timeout_ms=15000)
Call: log_step(job_id, "login_success", notes="Successfully logged in to Hypertide")
```

**If login fails** (no "Place New Order" text found):
```
Call: fail_job(job_id, "Login failed - could not reach dashboard", "login")
```
STOP EXECUTION.

### Step 3: Start New Order

```
Call: click("text=Place New Order")
Call: log_step(job_id, "new_order", notes="Clicked Place New Order")
```

### Step 4: Select Provider Type

Based on `provider_type` from the job:
- If "entra": Click on the Entra/Microsoft option
- If "google": Click on the Google Workspace option

```
Call: log_step(job_id, "select_provider", notes="Selected provider: {provider_type}")
```

Look for text that matches the provider type and click it. The exact selectors may vary - use `get_page_text` if needed to find the right element.

### Step 5: Select Domains (BYOD Mode)

The domain setup page should show options for domains. Look for "Bring Your Own Domain" or "BYOD" or similar option and select it.

For each domain in `domain_names`:
1. Find the domain input field
2. Enter the domain name
3. Confirm/add it

```
Call: log_step(job_id, "domains_entered", notes="Entered domains: {domain_names}")
```

After entering all domains, proceed to the next step (click Next/Continue/Save).

### Step 6: Basic Configuration (Settings)

This step has multiple sections. Fill in:

**Forwarding Domain:**
- Find the forwarding domain input field
- Fill with `forwarding_domain` value

**Company Name:**
- Find the company name input field
- Fill with `company_name` value

```
Call: log_step(job_id, "basic_config", notes="Filled forwarding domain and company name")
```

### Step 7: Email Tool Configuration (Bison) - CRITICAL STEP

This is the most important step for workspace isolation.

1. **Select Bison as the email tool** - Look for "Bison" or "Email Bison" option and select it

2. **Fill Bison credentials:**
```
Fill username field with: bison_username
Fill password field with: bison_password
Fill URL field with: bison_url
```

3. **Select workspace by EXACT name match:**
   - Open the workspace dropdown
   - Look for EXACTLY `bison_workspace_name` in the dropdown options
   - **If the EXACT workspace name is NOT found: FAIL IMMEDIATELY**

```
Call: select_dropdown({workspace_dropdown_selector}, bison_workspace_name)
```

If the dropdown selection fails or workspace is not found:
```
Call: fail_job(job_id, "WORKSPACE NOT FOUND: '{bison_workspace_name}' not in dropdown. Failing to prevent cross-contamination.", "bison_workspace_selection")
```
STOP EXECUTION.

If workspace selected successfully:
```
Call: log_step(job_id, "bison_config", notes="Bison credentials filled. Workspace '{bison_workspace_name}' selected successfully.")
```

Save/continue to next step.

### Step 8: Warmup Settings

Accept the default warmup settings. Click Next/Continue/Save to proceed.

```
Call: log_step(job_id, "warmup_settings", notes="Accepted default warmup settings")
```

### Step 9: Outbound Settings

Accept the default outbound settings. Click Next/Continue/Save to proceed.

```
Call: log_step(job_id, "outbound_settings", notes="Accepted default outbound settings")
```

### Step 10: User Configuration (Sender Names)

If `sender_names` is provided and non-empty:
1. For each sender name (up to 10), add a user with:
   - First name: `sender_names[i].firstName`
   - Last name: `sender_names[i].lastName`

Look for "Add User" or similar button to add each sender name.

```
Call: log_step(job_id, "sender_names", notes="Added {count} sender names")
```

If sender_names is empty, skip this step and accept defaults.

### Step 11: Review Order

Read the review/summary page carefully:
```
Call: get_page_text()
```

Verify:
- Domain count matches `domain_names` length
- Provider type is correct
- Pricing looks reasonable

```
Call: log_step(job_id, "review_order", notes="Order review: {summary of what you see}")
```

### Step 12: Checkout / Payment

If `use_saved_payment` is true:
- Look for a saved payment method option and select it
- Click the final "Place Order" / "Confirm" / "Submit" button

```
Call: log_step(job_id, "checkout", notes="Proceeding with saved payment method")
```

Wait for confirmation:
```
Call: wait_for_text("Order", timeout_ms=30000)
```

### Step 13: Capture Confirmation

After order is placed:
1. Read the confirmation page
2. Extract the order ID/number from the confirmation screen
3. Take a final screenshot

```
Call: get_page_text()
Call: screenshot()
Call: log_step(job_id, "confirmation", notes="Order confirmed. Order ID: {extracted_order_id}")
```

### Step 14: Complete Job

```
Call: complete_job(job_id, order_id)
```

## ERROR HANDLING

At any step, if something unexpected happens:

1. Take a screenshot: `screenshot()`
2. Get page text: `get_page_text()`
3. Log the failure: `log_step(job_id, "error_{step}", notes="Error: {description}")`
4. Fail the job: `fail_job(job_id, "{error_description}", "{step_name}")`
5. STOP EXECUTION - do not try to continue

## NAVIGATION TIPS

- Hypertide uses a multi-step wizard for order setup
- Steps may have "Next", "Continue", or "Save & Continue" buttons
- Some fields may be dropdowns that need clicking to open
- If a page takes time to load, use `wait_for_text` before interacting
- Use `get_page_text` when you need to understand the current page state
- Use `scroll_down` if elements are below the visible viewport
