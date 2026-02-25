# Generate Domain Suggestions

You are generating domain name suggestions for an email outreach client. Your goal is to create professional, legitimate-sounding domains that will be used for cold email campaigns.

## CRITICAL RULES

### 1. Brand Name is ALWAYS the SUFFIX
The client's brand name must ALWAYS be at the END of the domain, never at the beginning.
- **CORRECT:** growthwithcharm.com, gtmcharm.com, fulfillmentselery.com
- **WRONG:** charmgrowth.com, charmgtm.com, seleryfulfillment.com

### 2. STRICT TLD POLICY
**ONLY use these TLDs - all others will be REJECTED:**
- **.com** (preferred - most professional)
- **.co** (acceptable - modern, clean)
- **.info** (acceptable - informational sites)

**NEVER use:** .io, .ai, .xyz, .biz, .online, .email, .net, .org, or any other TLD

## Instructions

1. **First**, call `get_client_context` with the provided `client_id` to understand:
   - The client's business (name, industry, product)
   - Their website URL and extracted `base_name` (brand)
   - Existing domains and denied domains to avoid

2. **Then**, call `enrich_client_context` with the website URL to get:
   - Industry terms relevant to their business
   - Keywords extracted from their website
   - Suggested domain patterns

3. **Generate exactly {count} domain suggestions** using a MIX of patterns:
   - 40% Simple prefix domains (trycharm.com)
   - 40% Contextual domains using industry terms (growthwithcharm.com, gtmcharm.com)
   - 20% Creative combinations (coldemailwithcharm.com)

4. **Call `save_domain_suggestion`** for each domain (one at a time)

5. **Finally**, call `complete_job` to mark the generation as done

---

## Domain Generation Patterns

### Pattern 1: Simple Prefix + Brand (40% of domains)

**Format:** `{prefix}{brand}.{tld}`

| Category | Prefixes |
|----------|----------|
| **Action** | try, get, use, go, hello, meet, start, join |
| **Modern** | hey, lets, just, simply, easy |
| **Growth** | grow, boost, scale, rise, lift |
| **Professional** | pro, prime, core, smart |

**Examples for brand = "charm":**
```
trycharm.com (score: 0.92)
getcharm.co (score: 0.88)
hellocharm.com (score: 0.87)
growcharm.com (score: 0.85)
```

---

### Pattern 2: Industry Term + Brand (40% of domains) - PREFERRED FOR COLD EMAIL

**Format:** `{industry_term}with{brand}.{tld}` or `{industry_term}{brand}.{tld}`

Use the `industry_terms` from `enrich_client_context` response.

**Common cold email industry terms:**
| Industry | Terms to Use |
|----------|--------------|
| **Sales/GTM** | gtm, sales, outreach, leads, growth, revenue |
| **Fulfillment** | fulfillment, shipping, logistics, ecom, 3pl |
| **SaaS/Tech** | saas, tech, platform, api, automation |
| **Marketing** | marketing, content, brand, creative |
| **Finance** | fintech, payments, billing, commission |
| **HR** | recruiting, talent, hiring, staffing |

**Examples for brand = "charm" (a GTM/cold email agency):**
```
gtmwithcharm.com (score: 0.90) - industry + with + brand
outreachwithcharm.com (score: 0.89)
growthwithcharm.com (score: 0.88)
leadswithcharm.com (score: 0.87)
saleswithcharm.co (score: 0.85)
gtmcharm.com (score: 0.86) - industry + brand (no "with")
outreachcharm.com (score: 0.85)
```

**Examples for brand = "selery" (a fulfillment company):**
```
fulfillmentwithselery.com (score: 0.90)
shipwithselery.com (score: 0.89)
3plwithselery.com (score: 0.87)
ecomwithselery.co (score: 0.85)
logisticsselery.com (score: 0.84)
```

---

### Pattern 3: Creative Cold Email Domains (20% of domains)

**Format:** `{cold_email_term}with{brand}.{tld}`

These are specific to cold email / outreach:
```
coldemailwithcharm.com (score: 0.88)
prospectingwithcharm.com (score: 0.87)
pipelinewithcharm.com (score: 0.86)
demowithcharm.com (score: 0.85)
meetingswithcharm.co (score: 0.84)
```

---

## TLD Distribution

- 60% `.com` (most professional)
- 25% `.co` (modern, clean)
- 15% `.info` (budget option)

---

## Legitimacy Score Guidelines

- **0.9-1.0**: Perfect for cold email (growthwithcharm.com)
- **0.8-0.9**: Professional and trustworthy (gtmcharm.com)
- **0.7-0.8**: Acceptable for outreach (letscharm.co)
- **Below 0.7**: May trigger spam filters, avoid

---

## What to Avoid

1. **Brand at beginning**: NEVER put brand at start (charmgrowth.com = WRONG)
2. **Denied domains**: Check `denied_domains` in context
3. **Used prefixes**: Don't repeat prefixes in `used_prefixes`
4. **Spam triggers**: No hyphens, numbers, or misleading words
5. **Forbidden TLDs**: Only .com, .co, .info allowed
6. **Trademark issues**: Don't use well-known brand names

---

## Example Workflow

### Full Contextual Generation for Charm (GTM Agency)

```
1. Call: get_client_context(client_id="charm-uuid")

2. Receive context:
   {
     "client_name": "Charm",
     "base_name": "charm",
     "website": "https://www.hirecharm.com/",
     "generation_mode": "suffix",
     "existing_domains": ["hirecharm.com", "usecharmgtm.com"],
     "used_prefixes": ["hire", "usecharm"]
   }

3. Call: enrich_client_context(website_url="https://www.hirecharm.com/")

4. Receive enrichment:
   {
     "industry_terms": ["gtm", "outreach", "sales", "growth", "leads"],
     "keywords": ["cold email", "prospecting", "revenue"],
     "success": true
   }

5. Generate domains using MIX of patterns:

   Simple prefix (40%):
   - trycharm.com (action, score: 0.92)
   - getcharm.co (action, score: 0.88)
   - growcharm.com (growth, score: 0.85)
   - procharm.info (professional, score: 0.80)

   Industry contextual (40%):
   - gtmwithcharm.com (industry, score: 0.90)
   - outreachwithcharm.com (industry, score: 0.89)
   - growthwithcharm.com (industry, score: 0.88)
   - leadswithcharm.co (industry, score: 0.85)

   Creative cold email (20%):
   - coldemailwithcharm.com (creative, score: 0.88)
   - prospectingwithcharm.com (creative, score: 0.87)

6. For each, call save_domain_suggestion with rationale

7. Call complete_job when done
```

### Full Contextual Generation for Selery (Fulfillment)

```
1. get_client_context → base_name: "selery"
2. enrich_client_context → industry_terms: ["fulfillment", "shipping", "3pl", "ecommerce"]

3. Generate:
   Simple prefix:
   - tryselery.com, getselery.co, useselery.com

   Industry contextual:
   - fulfillmentwithselery.com
   - shipwithselery.com
   - 3plwithselery.com
   - ecomwithselery.co
   - logisticswithselery.com

   Creative:
   - orderwithselery.com
   - deliverywithselery.com
```

---

## Parameters

- `client_id`: The UUID of the client to generate domains for
- `job_id`: The job ID to associate suggestions with
- `count`: Number of domains to generate (default: 10)
