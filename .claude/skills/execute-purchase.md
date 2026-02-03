# Skill: Execute Hypertide Inbox Purchase

You are executing an inbox purchase order on Hypertide (app2.hypertide.io).
You have browser automation tools to navigate and interact with the Hypertide web UI.
You have database tools to read your job data and log progress.

## CRITICAL SAFETY RULES

1. **ONLY use data from the job record** - Never invent or guess values
2. **Log EVERY step via `log_step` — but call it exactly ONCE per step** - Do not call log_step twice for the same step. One log_step call per step is the audit trail.
3. **If workspace name not found in dropdown: FAIL IMMEDIATELY** - This prevents cross-contamination of inboxes between clients
4. **If any step shows unexpected content: FAIL with screenshot** - Do not try to recover from unknown states
5. **If payment fails: FAIL with "Payment failed" error** - Never retry payment automatically
6. **Never navigate away from Hypertide** - Only use app2.hypertide.io URLs
7. **Never attempt to fill Stripe payment forms or solve captchas** — Always use `handoff_checkout()` at the Stripe checkout page

## TIMING AND RATE LIMITING RULES

8. **Login ONCE and only once** - After you see the dashboard ("Place New Order"), you are logged in. NEVER navigate back to the signin page or log in again.
9. **Never navigate to a page you are already on** - The navigate tool will tell you if it skipped a redundant navigation. If you are already on a page, interact with it directly.
10. **After every click that changes the page, call wait_for_text()** - Verify the expected content appeared before taking the next action. Do NOT assume the page loaded.
11. **Execute steps in strict sequential order** - Complete one step fully before starting the next. Never skip ahead or go back.
12. **If a TEST MODE stop instruction exists, obey it immediately** - After completing the specified step, call fail_job() and STOP. Do not execute any further steps.

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
- `bison_url` - EmailBison URL (always "https://spellcast.hirecharm.com")
- `bison_api_key` - EmailBison API key for fetching workspaces (starts with "17|...")
- `sender_names` - JSON array of {firstName, lastName} for inbox user configuration
- `use_saved_payment` - Whether to use saved payment method
- `stripe_card_number` - (optional) Card number for manual payment
- `stripe_card_exp` - (optional) Card expiration (MM/YY)
- `stripe_card_cvc` - (optional) Card CVC
- `stripe_card_zip` - (optional) Card billing ZIP code

Then update status:
```
Call: update_job_status(job_id, "processing", "Loading job data")
```

### Step 2: Login to Hypertide

**IMPORTANT: Login exactly ONCE. After seeing "Place New Order", you are on the dashboard. Do NOT navigate to the signin page again.**

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

Wait for dashboard to load — **do NOT proceed until this succeeds**:
```
Call: wait_for_text("Place New Order", timeout_ms=15000)
Call: log_step(job_id, "login_success", notes="Successfully logged in to Hypertide")
```

**If login fails** (no "Place New Order" text found):
```
Call: fail_job(job_id, "Login failed - could not reach dashboard", "login", "auth")
```
STOP EXECUTION.

**You are now logged in. Do NOT navigate to the signin page again for any reason.**

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

**Save the configuration:**
- Click the "Save Basic Configuration" button (orange button at bottom of Step 1 section)
- Wait for the form to indicate success (Step 2 should become enabled/expanded)

```
Call: wait_for_text("Connect Your Email Automation Tool", timeout_ms=10000)
Call: log_step(job_id, "basic_config", notes="Filled forwarding domain and company name, saved configuration")
```

### Step 7: Email Tool Configuration (Bison) - CRITICAL STEP

This is the most important step for workspace isolation.

The Hypertide form "Step 2) Connect Your Email Automation Tool" has:
- A row of email tool radio buttons: Instantly | Smartlead | **Bison** | Other
- Username field (email)
- Password field
- Workspace dropdown ("Click to select workspace") — opens a modal
- Bison URL field

**Sub-step 7a: Select Bison as the email tool**

Click the "Bison" radio button/option. Wait for the form fields to appear.

**Sub-step 7b: Fill Username, Password, and Bison URL**

```
Fill the Username field with: bison_username
Fill the Password field with: bison_password
Fill the Bison URL field with: bison_url  (always https://spellcast.hirecharm.com)
```

**Sub-step 7c: Open the Workspace selector**

Click the Workspace dropdown (labeled "Click to select workspace"). This opens a **modal dialog** titled "Select Bison Workspace" with:
- "Bison URL" field (pre-filled from the main form)
- "API Key (Global)" field (empty — you must fill this)
- "Fetch Workspaces" button
- "Available Workspaces" list (empty until fetched)

**Sub-step 7d: Fill the API Key and Fetch Workspaces**

```
Fill the "API Key (Global)" field with: bison_api_key
Click the "Fetch Workspaces" button
Call: wait_for_text(bison_workspace_name, timeout_ms=15000)
```

Wait for the "Available Workspaces" list to populate. If the fetch fails or times out:
```
Call: fail_job(job_id, "Failed to fetch workspaces from Bison API. Check API key and URL.", "bison_workspace_fetch", "config")
```
STOP EXECUTION.

**Sub-step 7e: Select the workspace by EXACT name match**

Scroll through the "Available Workspaces" list and click on EXACTLY `bison_workspace_name`.

**If the EXACT workspace name is NOT found in the list: FAIL IMMEDIATELY**

```
Call: fail_job(job_id, "WORKSPACE NOT FOUND: '{bison_workspace_name}' not in dropdown. Failing to prevent cross-contamination.", "bison_workspace_selection", "config")
```
STOP EXECUTION.

If workspace selected successfully, the modal should close and the workspace field on the main form should now show the selected workspace name.

```
Call: log_step(job_id, "bison_config", notes="Bison credentials filled. Workspace '{bison_workspace_name}' selected via API key fetch.")
```

**Sub-step 7f: Save credentials and continue**

Look for "Move on without saving" or "Save Your Credentials For Future Use" buttons at the bottom. Click "Move on without saving" to proceed without storing credentials in Hypertide.

Wait for the next page to load before proceeding.

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

### Step 12: Checkout / Payment Handoff

After confirming the order, the browser redirects to Stripe checkout.

**Do NOT attempt to fill payment details or solve captchas.**

1. Wait for the Stripe checkout page to load (URL contains `checkout.stripe.com` or page shows card entry fields)
2. Capture the current page URL from the browser:
```
Call: screenshot()
```
3. The URL visible in the browser or page info is the Stripe checkout URL. Call handoff:
```
Call: handoff_checkout(job_id, checkout_url)
```
4. **STOP EXECUTION immediately** after the handoff. Do not call any more tools. Output your summary report and exit.

## ERROR HANDLING

At any step, if something unexpected happens:

1. Take a screenshot: `screenshot()`
2. Get page text: `get_page_text()`
3. Log the failure: `log_step(job_id, "error_{step}", notes="Error: {description}")`
4. Classify the error and fail the job with the appropriate `error_type`:
   - **"payment"** — Card declined, insufficient funds, Stripe error, checkout failure
   - **"config"** — Wrong workspace, missing field, bad credentials, domain entry error
   - **"auth"** — Login failed, session expired, could not reach dashboard
   - **"timeout"** — Page didn't load, element not found after waiting, navigation timeout
   - **"system"** — Browser crashed, unexpected page state, unknown error
5. Fail the job: `fail_job(job_id, "{error_description}", "{step_name}", "{error_type}")`
6. STOP EXECUTION - do not try to continue

## NAVIGATION TIPS

- Hypertide uses a multi-step wizard for order setup
- Steps may have "Next", "Continue", or "Save & Continue" buttons
- Some fields may be dropdowns that need clicking to open
- **ALWAYS call `wait_for_text` after clicking a button that changes the page** — verify the expected content is visible before proceeding
- Use `get_page_text` when you need to understand the current page state
- Use `scroll_down` if elements are below the visible viewport
- **NEVER call `navigate()` to a URL you are already on** — interact with the current page directly
- **Login only ONCE** — once on the dashboard, proceed forward through the wizard, never back to signin
