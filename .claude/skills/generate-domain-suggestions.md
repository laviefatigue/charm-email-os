# Generate Domain Suggestions

You are generating domain name suggestions for an email outreach client. Your goal is to create professional, legitimate-sounding domains that will be used for cold email campaigns.

## STRICT TLD POLICY

**ONLY use these TLDs - all others will be REJECTED:**
- **.com** (preferred - most professional)
- **.co** (acceptable - modern, clean)
- **.info** (acceptable - informational sites)

**NEVER use:** .io, .ai, .xyz, .biz, .online, .email, .net, .org, or any other TLD

The MCP server will reject any domain with a TLD not in the allowed list.

## Instructions

1. **First**, call `get_client_context` with the provided `client_id` to understand:
   - The client's business (name, industry, product)
   - Existing domains and their pattern
   - Any denied domains to avoid

2. **Analyze the context** to determine your generation strategy:
   - **If `has_onboarding: true`**: Use the onboarding data (industry, product, target audience) to generate creative, brand-aligned domains
   - **If `has_onboarding: false`**: Use the `domain_pattern` and `used_prefixes` to generate new variations

3. **Generate exactly {count} domain suggestions**, each with:
   - A unique, professional domain name
   - A rationale explaining why it works
   - A legitimacy score (0.7+ is good)

4. **Call `save_domain_suggestion`** for each domain (one at a time, don't batch)

5. **Finally**, call `complete_job` to mark the generation as done

## Generation Rules

### For Clients WITH Onboarding Data (Creative Mode)

Generate domains that:
- Combine action verbs with the product/service concept
- Use ONLY allowed TLDs (.com preferred, .co and .info acceptable)
- Sound like legitimate business domains
- Avoid spam triggers (no hyphens, no numbers, no misleading words)

**Good patterns:**
- `{action}{product}.com` (e.g., "growthcheckout.com")
- `{positive}{brand}.co` (e.g., "smartpayments.co")
- `{verb}{industry}.info` (e.g., "scaleecommerce.info")

### For Clients WITHOUT Onboarding (Pattern Fallback Mode)

When `generation_mode: pattern_fallback`:
1. Use the `domain_pattern` as your suffix (e.g., "checkoutcomponents.com")
2. Avoid all prefixes in `used_prefixes`
3. Generate new prefixes from these categories:

**Action Verbs:** launch, ignite, spark, fuel, drive, push, pull, click, tap, grab, catch, snap, hook, lock

**Growth Words:** rise, lift, climb, soar, leap, surge, spike, grow, bloom, peak, apex, top, max, ultra

**Positive Words:** ace, win, hit, yes, now, go, do, be, zen, flow, ease, breeze, smooth, swift, quick

**Professional:** pro, prime, core, key, main, lead, chief, smart, wise, keen, sharp, bright, clear, pure

**Tech/Modern:** neo, next, new, fresh, hot, cool, slick, flex, sync, link, mesh, grid, hub, node

**Format:** `{new_prefix}{domain_pattern}`

## Legitimacy Score Guidelines

- **0.9-1.0**: Looks like a real company domain (e.g., "growthmetrics.com")
- **0.8-0.9**: Professional and trustworthy (e.g., "boostanalytics.io")
- **0.7-0.8**: Acceptable for outreach (e.g., "clickwidgets.com")
- **Below 0.7**: May trigger spam filters, avoid

## What to Avoid

1. **Denied domains**: Check `denied_domains` in context - never suggest similar ones
2. **Used prefixes**: Don't repeat prefixes in `used_prefixes`
3. **Spam triggers**: No hyphens, numbers, or misleading words
4. **Forbidden TLDs**: NEVER use .io, .ai, .xyz, .biz, .online, .email, .net, .org (only .com, .co, .info allowed)
5. **Trademark issues**: Don't use well-known brand names

## Example Workflow

```
1. Call: get_client_context(client_id="abc123")

2. Receive context:
   {
     "client_name": "Checkout Components",
     "has_onboarding": false,
     "domain_pattern": "checkoutcomponents.com",
     "used_prefixes": ["boost", "get", "use", "try", "go"],
     "denied_domains": ["badcheckoutcomponents.com"]
   }

3. Generate using pattern fallback:
   - "launchecheckoutcomponents.com" (action verb, score: 0.85)
   - "primecheckoutcomponents.com" (professional, score: 0.88)
   - "flowcheckoutcomponents.com" (positive, score: 0.82)

4. For each, call:
   save_domain_suggestion(
     job_id="job123",
     domain_name="launchecheckoutcomponents.com",
     rationale="Action verb 'launch' implies starting/beginning, professional feel",
     legitimacy_score=0.85
   )

5. After all suggestions, call:
   complete_job(job_id="job123")
```

## Parameters

- `client_id`: The UUID of the client to generate domains for
- `job_id`: The job ID to associate suggestions with
- `count`: Number of domains to generate (default: 10)
