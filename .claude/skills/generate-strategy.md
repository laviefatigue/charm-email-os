# Generate Strategy - Cold Email Campaign Variants

You are generating cold email campaign variants for a client using the Cold Email Personalization Skill v2.0. Your goal is to create punchy, research-backed emails that earn replies (not meetings).

## 5 Non-Negotiable Principles

1. **Shorter & Punchier** — Target 50-90 words. Can be read aloud in under 20 seconds.
2. **Research IS the personalization** — Custom signals > clever copy tricks
3. **Earn replies, not meetings** — Confirm their situation before asking for time
4. **Two valid paths** — Either use custom signal research OR lead with your whole offer
5. **Every word earns its place** — Delete anything that doesn't add value

## Instructions

### Step 1: Get Client Context

Call `get_client_context(client_id="{client_id}")` to retrieve:
- Company info (name, industry, product)
- Onboarding data (target customer, ICP, segments, personas)
- Messaging guidelines (tone_style, customer_voice, roi_results)
- Case studies available
- Previous suggestions and their status

### Step 2: Get Feedback Summary

Call `get_feedback_summary(client_id="{client_id}")` to learn:
- Which variants were approved (patterns that work)
- Which were denied (patterns to avoid)
- Any revision requests (specific guidance to incorporate)

### Step 3: Choose Campaign Strategy

Based on the context, choose one of these approaches:

| Type | When to Use | Example Opening |
|------|-------------|-----------------|
| **custom_signal** | Strong research data available | "Noticed you have Starter vs Pro tiers..." |
| **creative_ideas** | Feature-constrained format | "3 ideas for {{company_name}}:" |
| **whole_offer** | Subject line = full value prop | Subject: "4.7x upgrade increase" |
| **fallback** | Low research available | "Let me know if [person A] or [person B]..." |

### Step 4: Generate 3 Variants

Create 3 distinct variants with different angles:

- **Variant 1**: Opens with custom signal/insight about their business
- **Variant 2**: Opens with case study proof or social proof
- **Variant 3**: Opens with risk/efficiency angle or problem-aware approach

### Step 5: QA Score Each Variant

Score each variant using this rubric (0-100):

| Dimension | Points | What's Measured |
|-----------|--------|-----------------|
| Situation Recognition | 25 | Specific data about them? Uses research? |
| Value Clarity | 25 | Clear offer + proof? Reader knows what you do? |
| Personalization Quality | 20 | Custom signal OR AI insight? Not just {{name}}? |
| CTA Effort | 15 | 5 words or less to reply? Low friction? |
| Punchiness | 10 | 50-90 words? No fluff? |
| Subject Line | 5 | 2-4 words OR whole offer value prop? |

**Score Thresholds:**
- **85+** = Ship it
- **70-84** = One more pass
- **<70** = Start over

### Step 6: Save Each Variant

For each variant, call:
```
save_campaign_variant(
  job_id="{job_id}",
  variant_number=1,
  subject_line="Quick q about {{company_name}}",
  email_body="Hey {{first_name}},\n\nNoticed...",
  score=87,
  rationale="Strong custom signal opening, clear CTA, 72 words",
  used_variables=["{{first_name}}", "{{company_name}}"],
  campaign_type="custom_signal"
)
```

### Step 7: Complete Job

Call `complete_job(job_id="{job_id}")` when all 3 variants are saved.

---

## Variable Schema

Use these variables (will be replaced at send time):

### Core Variables (Always Available)
- `{{first_name}}` — Prospect's first name
- `{{company_name}}` — Their company
- `{{role_title}}` — Job title

### High-Signal Variables (From Onboarding)
- `{{industry}}` — Their industry
- `{{product}}` — What they sell
- `{{target_customer}}` — Who they sell to
- `{{case_study_company}}` — Reference customer name
- `{{case_study_result}}` — Key outcome achieved

### Custom Variables (From Research)
- `{{pricing_tier}}` — If you researched their pricing
- `{{competitor}}` — Known competitor
- `{{recent_news}}` — Recent company news

---

## Email Structure Template

### Subject Line (2-4 words or whole offer)
❌ "Quick question about your marketing strategy"
✅ "Quick q about {{company_name}}"
✅ "4.7x upgrade increase"

### Opening (Custom Signal or Case Study)
❌ "I hope this email finds you well"
✅ "Noticed you have Starter vs Pro tiers on your pricing page..."
✅ "We helped {{case_study_company}} increase conversions by {{case_study_result}}..."

### Value Proposition (1-2 sentences)
- What you do + what result you create
- Include proof if available

### CTA (5 words or less to reply)
❌ "Would you have 15 minutes next week to discuss?"
✅ "Worth exploring?"
✅ "Make sense to chat?"
✅ "Open to seeing how?"

---

## Banned Phrases (Delete & Rewrite)

- "I hope this email finds you well"
- "I wanted to reach out"
- "We help companies..." (unless followed by case study)
- "I came across your profile"
- "I'm reaching out because"
- "I noticed your company"
- Any request for "15 minutes" or "30 minutes"

---

## Example Output

### Variant 1 (Custom Signal, Score: 87)

**Subject:** Quick q about {{company_name}}

**Body:**
Hey {{first_name}},

Noticed you have Starter vs Pro tiers on your pricing page.

Most B2B SaaS teams we talk to are leaving 20-30% of their upgrade revenue on the table because pricing pages don't adapt to buyer intent.

We helped {{case_study_company}} increase their Starter-to-Pro conversions by 4.7x.

Worth exploring?

**Variables:** {{first_name}}, {{company_name}}, {{case_study_company}}
**Word Count:** 52
**Rationale:** Strong custom signal (pricing tiers), clear value prop with proof, low-effort CTA.

---

### Variant 2 (Case Study Lead, Score: 82)

**Subject:** {{case_study_result}} for {{case_study_company}}

**Body:**
{{first_name}},

{{case_study_company}} was losing trial-to-paid conversions to confusing checkout flows.

After implementing our checkout optimizer, they saw:
- 4.7x increase in upgrades
- 23% reduction in cart abandonment
- $340K additional ARR in 6 months

You're in {{industry}} with similar ACV ranges — the math would probably look similar.

Open to seeing how?

**Variables:** {{first_name}}, {{case_study_company}}, {{case_study_result}}, {{industry}}
**Word Count:** 61
**Rationale:** Proof-first approach, concrete numbers, industry relevance.

---

### Variant 3 (Risk/Efficiency Angle, Score: 79)

**Subject:** Quick {{company_name}} thought

**Body:**
{{first_name}},

Every month your pricing page stays static, you're probably leaving upgrade revenue on the table.

Most {{industry}} companies we audit have:
- Pricing pages that don't adapt to buyer signals
- Checkout flows with 15-25% drop-off rates
- No A/B testing on upgrade paths

Happy to run a free 5-minute audit if useful.

**Variables:** {{first_name}}, {{company_name}}, {{industry}}
**Word Count:** 58
**Rationale:** Problem-aware approach, specific pain points, low-commitment CTA.

---

## Parameters

- `client_id`: The UUID of the client to generate strategies for
- `job_id`: The generation job ID to associate variants with
- `submission_id`: (Optional) Specific onboarding submission to use

---

## Quick Reference: What Makes Good Cold Email Copy

1. **Opens with something about THEM** (not you)
2. **Proves you've done homework** (custom signal or AI insight)
3. **Clear value prop in 1 sentence**
4. **Social proof if available** (case study, numbers)
5. **CTA that takes 5 seconds to answer**
6. **Under 90 words total**
