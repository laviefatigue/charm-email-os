# Spintax & Liquid Syntax Skill

## Purpose
Generate variation in cold email copy using spintax and liquid syntax to improve deliverability, avoid spam filters, and personalize messages at scale.

---

## Spintax Basics

### Format
Wrap options in curly brackets `{}` and separate with pipes `|`.

```
{Hi|Hello|Hey}
{reaching out|writing|getting in touch}
{quick question|thought worth sharing|idea for you}
```

### Where It Works
- Email subject lines
- Email body copy
- One option selected randomly per send

### Common Spintax Patterns

**Greetings:**
```
{Hi|Hello|Hey|Good to connect}
```

**Opening hooks:**
```
{Quick question|Thought worth sharing|Brief note|Short one for you}
```

**CTAs:**
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

## Liquid Syntax

### Variable Handling
Bison replaces custom variables BEFORE parsing liquid templates. Variables in comparisons must be quoted.

**Correct:**
```liquid
{% if '{FIRST_NAME}' == 'Cody' %}
This is Cody
{% else %}
This is not Cody
{% endif %}
```

**Alternative (assign first):**
```liquid
{% assign first_name = {FIRST_NAME} %}
{% if first_name == 'Cody' %}
This is Cody
{% endif %}
```

---

## Template Library

### 1. Time-of-Day Greeting
```liquid
{% assign hour = "now" | date: "%H" | plus: 0 %}
{% assign name = '{FIRST_NAME}' | strip | default: 'there' | downcase | capitalize %}
{% if hour < 12 %}Good morning{% elsif hour < 17 %}Good afternoon{% else %}Good evening{% endif %} {{ name }} —
```

### 2. Day-Based Availability
```liquid
{% assign today = "now" | date: "%A" %}
{% if today == "Monday" %}tomorrow or Wednesday?{% elsif today == "Tuesday" %}tomorrow or Thursday?{% elsif today == "Wednesday" %}tomorrow or Friday?{% elsif today == "Thursday" %}tomorrow or early next week?{% elsif today == "Friday" or today == "Saturday" or today == "Sunday" %}early next week?{% endif %}
```

### 3. Title/Role-Based Messaging
```liquid
{% assign title = '{TITLE}' | downcase | strip %}
{% if title contains "founder" or title contains "ceo" %}I'll keep this brief given your schedule.{% elsif title contains "sales" or title contains "revops" %}Happy to share a quick pipeline impact summary.{% elsif title contains "marketing" or title contains "growth" %}I can summarize pipeline impact in 2 minutes.{% else %}I can tailor this to your team's priorities.{% endif %}
```

### 4. Location Fallback
```liquid
{% assign city = '{CITY}' %}
{% if city %}I'm helping several clients in {{ city }} who need guidance with insurance.{% else %}I'm helping several clients in {your area|the region} who need guidance with insurance.{% endif %}
```

### 5. Industry-Specific Hook
```liquid
{% assign industry = '{INDUSTRY}' | downcase | strip %}
{% if industry contains "saas" or industry contains "software" %}Saw you're scaling a SaaS play{% elsif industry contains "agency" or industry contains "marketing" %}Fellow agency operator here{% elsif industry contains "healthcare" or industry contains "health" %}Know healthcare has unique challenges{% else %}Came across your company{% endif %}
```

### 6. Company Size Messaging
```liquid
{% assign size = '{EMPLOYEE_COUNT}' | plus: 0 %}
{% if size < 50 %}At your stage, speed matters most.{% elsif size < 200 %}Growth-stage teams like yours often hit this wall.{% elsif size < 1000 %}Mid-market companies we work with face similar challenges.{% else %}Enterprise teams need a different approach.{% endif %}
```

### 7. First Name with Fallback
```liquid
{% assign name = '{FIRST_NAME}' | strip | default: 'there' | downcase | capitalize %}
Hey {{ name }},
```

### 8. Conditional P.S. Line
```liquid
{% assign linkedin = '{LINKEDIN_URL}' | strip %}
{% if linkedin %}P.S. Saw your recent post — good stuff.{% endif %}
```

---

## Useful Liquid Filters

| Filter | Purpose | Example |
|--------|---------|---------|
| `downcase` | Lowercase for matching | `'{TITLE}' \| downcase` |
| `upcase` | Uppercase | `'{COMPANY}' \| upcase` |
| `capitalize` | First letter cap | `'{FIRST_NAME}' \| capitalize` |
| `strip` | Remove whitespace | `'{CITY}' \| strip` |
| `default` | Fallback value | `'{FIRST_NAME}' \| default: 'there'` |
| `truncate` | Limit characters | `'{COMPANY}' \| truncate: 20` |
| `replace` | Find/replace | `'{TITLE}' \| replace: "Sr.", "Senior"` |
| `split` | Break into array | `'{TAGS}' \| split: ","` |
| `plus` | Add number | `'{COUNT}' \| plus: 0` (forces integer) |

---

## Date/Time Formats

| Code | Output | Example |
|------|--------|---------|
| `%A` | Full weekday | Monday |
| `%a` | Short weekday | Mon |
| `%B` | Full month | January |
| `%b` | Short month | Jan |
| `%d` | Day (01-31) | 15 |
| `%H` | Hour 24h (00-23) | 14 |
| `%I` | Hour 12h (01-12) | 02 |
| `%M` | Minutes | 30 |
| `%Y` | Year | 2025 |

**Usage:**
```liquid
{% assign today = "now" | date: "%A" %}
{% assign month = "now" | date: "%B" %}
{% assign hour = "now" | date: "%H" | plus: 0 %}
```

---

## Best Practices

1. **Always use `downcase` before string comparisons** — matching is case-sensitive
2. **Use `strip` to remove whitespace** from CSV imports
3. **Provide fallbacks with `default`** for missing data
4. **Test with edge cases** — empty fields, unusual titles, etc.
5. **Keep spintax natural** — all options should read smoothly
6. **Don't over-spin** — 2-3 variations per element is plenty
7. **Combine spintax + liquid** — spintax for variation, liquid for logic

---

## Common Mistakes

❌ **Unquoted variables in comparisons:**
```liquid
{% if {FIRST_NAME} == 'Cody' %}  <!-- WRONG -->
```

✅ **Quoted variables:**
```liquid
{% if '{FIRST_NAME}' == 'Cody' %}  <!-- CORRECT -->
```

❌ **Case-sensitive matching without downcase:**
```liquid
{% if '{TITLE}' contains "CEO" %}  <!-- Misses "ceo", "Ceo" -->
```

✅ **Downcase first:**
```liquid
{% assign title = '{TITLE}' | downcase %}
{% if title contains "ceo" %}  <!-- Catches all variations -->
```

---

## Full Example: Complete Email with Spintax + Liquid

```liquid
{% assign hour = "now" | date: "%H" | plus: 0 %}
{% assign name = '{FIRST_NAME}' | strip | default: 'there' | downcase | capitalize %}
{% assign title = '{TITLE}' | downcase | strip %}
{% assign today = "now" | date: "%A" %}

{% if hour < 12 %}Good morning{% elsif hour < 17 %}Good afternoon{% else %}Good evening{% endif %} {{ name }},

{Quick question|Brief one|Short note} — {% if title contains "founder" or title contains "ceo" %}know your time is tight{% elsif title contains "sales" or title contains "revenue" %}fellow revenue person here{% else %}came across your company{% endif %}.

{We help|I work with} {companies like yours|teams in your space} {solve X|handle Y|tackle Z}.

{% if today == "Friday" or today == "Saturday" or today == "Sunday" %}Open to connecting early next week?{% else %}Worth a {quick call|brief chat} {% if today == "Monday" %}tomorrow or Wednesday{% elsif today == "Tuesday" %}tomorrow or Thursday{% elsif today == "Wednesday" %}tomorrow or Friday{% else %}tomorrow or early next week{% endif %}?{% endif %}

{Best|Cheers|Talk soon},
[Your Name]
```

---

## Reference
Full Liquid documentation: https://shopify.github.io/liquid/
