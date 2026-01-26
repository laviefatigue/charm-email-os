# Apply Spintax - Transform Approved Email Sequences

You are adding spintax variation and liquid personalization to an approved 4-email campaign sequence. The goal is to improve deliverability by adding variation while maintaining the core message.

## Execution Steps

1. **Call `get_sequence_for_spintax`** with the sequence_id to get:
   - The 4-email sequence content
   - Client context for personalization
   - Instructions on what to apply

2. **Transform each email** by applying:
   - Spintax patterns (variation)
   - Liquid syntax (personalization)

3. **Call `save_spintaxed_sequence`** with the transformed content

4. **Call `complete_spintax_job`** with the job_id to finalize

---

## Spintax Patterns to Apply

### Format
Wrap options in curly brackets `{}` and separate with pipes `|`:
```
{Hi|Hello|Hey}
{reaching out|writing|getting in touch}
```

### Where to Apply Spintax

**Greetings (Email 1 and 3 openings):**
```
{Hi|Hello|Hey|Good to connect}
```

**Opening hooks:**
```
{Quick question|Thought worth sharing|Brief note|Short one for you}
```

**CTAs (closing of each email):**
```
{Worth a quick call?|Open to chatting?|Make sense to connect?|Interested?}
```

**Time references:**
```
{this week|in the next few days|soon}
{15 minutes|a quick call|a brief chat}
```

**Softeners:**
```
{I think|I believe|From what I've seen}
{might|could|may}
{curious if|wondering if|wanted to see if}
```

---

## Liquid Syntax to Apply

### Time-of-Day Greeting (Email 1 only)
Replace static greeting with:
```liquid
{% assign hour = "now" | date: "%H" | plus: 0 %}
{% assign name = '{FIRST_NAME}' | strip | default: 'there' | downcase | capitalize %}
{% if hour < 12 %}Good morning{% elsif hour < 17 %}Good afternoon{% else %}Good evening{% endif %} {{ name }},
```

### Day-Based Availability (Email 4 CTA)
Replace static availability with:
```liquid
{% assign today = "now" | date: "%A" %}
{% if today == "Monday" %}tomorrow or Wednesday{% elsif today == "Tuesday" %}tomorrow or Thursday{% elsif today == "Wednesday" %}tomorrow or Friday{% elsif today == "Thursday" %}tomorrow or early next week{% else %}early next week{% endif %}
```

### Title/Role-Based Messaging (if job_titles available)
Add context-aware opener:
```liquid
{% assign title = '{TITLE}' | downcase | strip %}
{% if title contains "founder" or title contains "ceo" %}I'll keep this brief given your schedule.{% elsif title contains "sales" or title contains "revops" %}Happy to share a quick pipeline impact summary.{% elsif title contains "marketing" %}I can summarize pipeline impact in 2 minutes.{% else %}I can tailor this to your team's priorities.{% endif %}
```

### First Name with Fallback
Always use fallback for personalization:
```liquid
{% assign name = '{FIRST_NAME}' | strip | default: 'there' | downcase | capitalize %}
Hey {{ name }},
```

---

## Rules (CRITICAL)

1. **Do NOT change the core value proposition** - only add variation, not new content
2. **Max 2-3 spintax variations per element** - don't over-spin
3. **Keep word count within +/- 5 words** of original per email
4. **Preserve ALL existing {{variables}}** - these are merge fields
5. **All spintax options must read naturally** - no awkward phrasings
6. **Test liquid syntax validity** - ensure proper opening/closing tags
7. **Subject lines: minimal spintax** - keep recognizable, only vary greeting words

---

## Example Transformation

### Original Email 1:
```
Hey {{first_name}},

Quick question - saw that Acme Corp is scaling their outbound.

We help companies like yours automate follow-ups and save 10+ hours per week.

Worth a quick call this week?

Best,
[Sender]
```

### Spintaxed Email 1:
```liquid
{% assign hour = "now" | date: "%H" | plus: 0 %}
{% assign name = '{FIRST_NAME}' | strip | default: 'there' | downcase | capitalize %}
{% if hour < 12 %}Good morning{% elsif hour < 17 %}Good afternoon{% else %}Good evening{% endif %} {{ name }},

{Quick question|Brief one|Short note} - {saw|noticed} that Acme Corp is scaling their outbound.

{We help|I work with} companies like yours automate follow-ups and save {10+|over 10} hours per week.

{Worth a quick call|Open to chatting|Make sense to connect} {this week|in the next few days}?

{Best|Cheers|Talk soon},
[Sender]
```

---

## Quality Checklist

Before saving, verify:
- [ ] All 4 emails have spintax applied to greetings and CTAs
- [ ] Email 1 has time-of-day liquid greeting
- [ ] Email 4 CTA has day-based availability (if applicable)
- [ ] All {{variables}} preserved exactly as-is
- [ ] No core messaging changed
- [ ] Word count approximately matches original
- [ ] All liquid tags properly closed ({% endif %})
