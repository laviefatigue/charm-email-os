---
title: Lead Refinery Gates
created: 2026-01-27
updated: 2026-01-27
tags: [concept, lead-refinery, gates, verification]
---

# Lead Refinery Gates

The waterfall pipeline processes leads through cost-efficient gates with early-exit on failure.

## Gate 0: Free Pre-Validation (No API Cost)

**Purpose**: Eliminate bad emails and select best email BEFORE spending API credits.

- **Cost**: $0.00 (pure Python + DNS)
- **Module**: `gate0_prevalidation.py`
- **Dependency**: `dnspython` (for MX lookups)

### Checks Performed

| Check | What It Does | Impact |
|-------|-------------|--------|
| Syntax validation | Regex format check | Kills malformed emails |
| DNS MX lookup | Domain can receive email? | Kills dead domains |
| Email classification | Personal vs business vs ISP | Flags for priority |
| Smart email selection | Pick business over personal | Upgrades 8.4M leads |
| Role-based detection | info@, support@, etc. | Flags for B2B |
| Disposable detection | guerrillamail, tempmail, etc. | Kills throwaway |
| Typo correction | gmial.com -> gmail.com | Saves 3.2K leads |
| Legacy ISP detection | bellsouth, earthlink, juno | Flags low value |

### Verdicts

| Verdict | Meaning | Action |
|---------|---------|--------|
| `pass` | Business email, valid domain | Send to Gate 1 |
| `pass_risky` | Personal/ISP/role-based email | Send to Gate 1 (flagged) |
| `corrected` | Typo fixed | Send to Gate 1 (re-check) |
| `fail` | Disposable, no MX, bad syntax | Skip - don't spend credits |

### Enrichment Suggestions

For leads with only personal emails (15.8M in database):

- **Has LinkedIn URL** (7.87M): Use LeadMagic `find_email` to find business email
- **Has name + company**: Use LeadMagic `find_email` with name+company lookup
- **No enrichment path**: Still valid, just lower priority for B2B

### Database Impact

From 30.3M leads with email:

| Category | Count | % |
|----------|-------|---|
| Business emails | 14.4M | 48% |
| Personal emails | 15.8M | 52% |
| Multi-email leads | 8.4M | 28% |
| Personal + LinkedIn URL | 7.87M | 26% |
| Legacy ISP | 642K | 2% |
| Role-based | 56K | <1% |

## Gate 1: Email Verification (LeadMagic)

**Purpose**: Filter out invalid/bouncing emails before expensive enrichment.

- **Provider**: [LeadMagic](https://leadmagic.io/) (default)
- **Endpoint**: `POST https://api.leadmagic.io/email-validate`
- **Cost**: 1 credit = 20 validations (~$0.005/check)
- **Yield**: ~70%

| Status | Cost | Action |
|--------|------|--------|
| `valid` | 0.05 credits | Pass to Gate 2 |
| `valid_catch_all` | 0.05 credits | Pass (<5% bounce) |
| `catch_all` | **FREE** | Pass (risky) |
| `unknown` | **FREE** | Pass (risky) |
| `invalid` | 0.05 credits | Mark as `dead` |

### Provider Swapping

The system supports multiple providers via environment variables:

```bash
# Default: LeadMagic
export LEADMAGIC_API_KEY=xxx

# Alternative: Reoon ($0.0007/check)
export EMAIL_VERIFIER_PROVIDER=reoon
export REOON_API_KEY=xxx

# Alternative: ZeroBounce ($0.01/check)
export EMAIL_VERIFIER_PROVIDER=zerobounce
export ZEROBOUNCE_API_KEY=xxx
```

## Gate 2: AI-ARK Enrichment

**Purpose**: Verify person still works at company via LinkedIn data.

- **Provider**: [AI-ARK](https://ai-ark.com/)
- **Endpoint**: `api.ai-ark.com/api/developer-portal`
- **Cost**: 0.5 credits ($0.005)
- **Yield**: ~60%

| API Response | Status | Action |
|--------------|--------|--------|
| Company matches (fuzzy >80%) | `VERIFIED` | Save enriched data |
| Company mismatch | `CHANGED_JOB` | Save new company |
| No result / 404 | `UNVERIFIABLE` | Send to Gate 3 |

### Fuzzy Matching

Uses [rapidfuzz](https://github.com/maxbachmann/RapidFuzz) token_set_ratio:

```python
# Matches (score >= 80)
"Acme Inc" vs "Acme Incorporated" → 95%
"Google LLC" vs "Google" → 100%

# No match (score < 80)
"Acme Inc" vs "Totally Different Corp" → 20%
```

## Gate 3: Spider + Jina Rescue

**Purpose**: Rescue leads AI-ARK couldn't verify via public web search.

- **Cost**: ~$0.002 combined
- **Rescue Rate**: ~30%

### Process

1. **Spider.cloud**: Search Google for LinkedIn profile
   ```
   site:linkedin.com/in/ "John Doe" "Acme Inc"
   ```

2. **Jina.ai**: Extract employment info from HTML
   - Checks for "current", "present" indicators
   - Looks for company name near job title

3. **Decision**:
   - YES (still employed) → `verified` with `spider_verification_url`
   - NO → `dead`

### Cost Breakdown

| Service | Cost | Notes |
|---------|------|-------|
| Spider.cloud | $0.0001/credit | ~10 credits/search |
| Jina.ai | FREE | 10M tokens included |

## Waterfall Logic

```
for each lead:
    # Gate 0: Free Pre-Validation ($0.00)
    result = gate0.evaluate_lead(lead)
    if result.verdict == FAIL:
        skip (no credits spent)
        continue
    email = result.email  # Best email selected

    # Gate 1: LeadMagic Email Check ($0.005)
    if email is invalid:
        mark as DEAD
        continue

    # Gate 2: AI-ARK Employment Check ($0.005)
    if company matches:
        mark as VERIFIED
        continue
    if company mismatch:
        mark as CHANGED_JOB
        continue

    # Gate 3: Spider+Jina Rescue ($0.002)
    if rescue succeeds:
        mark as VERIFIED
    else:
        mark as DEAD
```

## Status Values

| Status | Meaning | Outcome |
|--------|---------|---------|
| `verified` | Person confirmed at company | Include in export |
| `changed_job` | Person at different company | Exclude (stale) |
| `dead` | Invalid email or not found | Exclude |
| `unverifiable` | Couldn't determine | Exclude |

## Related

- [[lead-refinery]] - Main hub
- [[lead-tam-map]] - Gate 2 enrichment data builds a living TAM map
- [[lead-refinery-config]] - Configuration options

---
Tags: #concept #lead-refinery #gates #verification
