---
title: Gemini SOP vs Charm - Quick Reference Card
created: 2026-02-23
---

# Gemini Kill Switch SOP - Quick Reference Card

## 📋 At-A-Glance Status

### ✅ IMPLEMENTED (Charm Already Has This)
- ✅ **Inbox auto-pause on 1 spam bounce (550)** - WORKING
- ✅ **SMTP error code tracking** - EXCEEDS SOP
- ✅ **Bounce type classification** - EXCEEDS SOP
- ✅ **Individual inbox Slack alerts** - WORKING

### ❌ MISSING (Must Build)
- ❌ **48-hour rolling window strike detection** - CRITICAL
- ❌ **Domain-level campaign pausing** - CRITICAL
- ❌ **Open rate <20% (3-day) monitoring** - HIGH PRIORITY
- ❌ **Daily morning kill summary report** - MEDIUM PRIORITY

---

## 🎯 Gemini SOP Rules → Charm Implementation

| # | Gemini Rule | Charm Today | Status |
|---|------------|-------------|---------|
| **1** | 1 spam bounce → pause inbox | ✅ Working | ✅ **DONE** |
| **2** | Bounce rate >2.5% (7d) → pause domain | ⚠️ Tracks at 5%, doesn't pause | ❌ **NEEDS FIX** |
| **3** | Spam complaint >0.1% → pause domain | ⚠️ Uses count not rate | ⚠️ **DIFFERENT** |
| **4** | Open rate <20% (3d) → pause domain | ❌ Not implemented | ❌ **MISSING** |
| **5** | Strike 1: Pause inbox | ✅ Working | ✅ **DONE** |
| **6** | Strike 2 (48h): Pause domain + rotate bench | ❌ No time window | ❌ **MISSING** |
| **7** | Strike 3 (48h): Kill domain + swap | ❌ No time window | ❌ **MISSING** |

---

## 🔧 Quick Fix SQL (Copy-Paste Ready)

### Fix #1: Create Rolling Window Table (5 minutes)
```sql
CREATE TABLE inbox_error_window (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    inbox_id UUID NOT NULL REFERENCES sender_accounts(id),
    domain_id UUID NOT NULL REFERENCES domains(id),
    error_code VARCHAR(20) NOT NULL,
    detected_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    window_expires_at TIMESTAMPTZ NOT NULL
);

CREATE INDEX idx_error_window_domain_time ON inbox_error_window(domain_id, detected_at DESC);

CREATE FUNCTION count_domain_strikes(p_domain_id UUID, p_window_hours INT DEFAULT 48)
RETURNS INTEGER AS $$
    SELECT COUNT(DISTINCT inbox_id)
    FROM inbox_error_window
    WHERE domain_id = p_domain_id
    AND detected_at >= NOW() - (p_window_hours || ' hours')::INTERVAL
$$ LANGUAGE SQL;
```

### Fix #2: Lower Bounce Rate Threshold (30 seconds)
```bash
# In .env file, change:
KILL_THRESHOLD_TOTAL_BOUNCE_RATE=0.025  # Was 0.05 (5%), now 2.5%
```

### Fix #3: Add Domain Health Functions (10 minutes)
```sql
CREATE FUNCTION get_domain_bounce_rate_7d(p_domain_id UUID) RETURNS NUMERIC AS $$
    SELECT COALESCE(
        COUNT(*) FILTER (WHERE ce.bounce_type IS NOT NULL)::NUMERIC /
        NULLIF(COUNT(*)::NUMERIC, 0), 0
    )
    FROM campaign_events ce
    JOIN sender_accounts sa ON sa.id = ce.sender_account_id
    WHERE sa.domain_id = p_domain_id
    AND ce.sent_at >= NOW() - INTERVAL '7 days'
$$ LANGUAGE SQL;

CREATE FUNCTION get_domain_open_rate_3d(p_domain_id UUID)
RETURNS TABLE(day_date DATE, open_rate NUMERIC) AS $$
    SELECT
        DATE(ce.sent_at) as day_date,
        COUNT(*) FILTER (WHERE ce.opened_at IS NOT NULL)::NUMERIC /
        NULLIF(COUNT(*)::NUMERIC, 0) as open_rate
    FROM campaign_events ce
    JOIN sender_accounts sa ON sa.id = ce.sender_account_id
    WHERE sa.domain_id = p_domain_id
    AND ce.sent_at >= NOW() - INTERVAL '3 days'
    GROUP BY DATE(ce.sent_at)
    ORDER BY day_date DESC
$$ LANGUAGE SQL;
```

---

## 📊 Implementation Checklist

### Week 1: Foundation
- [ ] Create `inbox_error_window` table
- [ ] Create `count_domain_strikes()` function
- [ ] Create domain health functions (bounce rate, spam rate, open rate)
- [ ] Modify `sync_events.py` to record errors in window
- [ ] Add cleanup job for expired window records

### Week 2: Domain Pausing
- [ ] Add `pause_domain_campaigns()` function to health_checks.py
- [ ] Implement Strike 2 detection logic
- [ ] Implement Strike 3 detection logic
- [ ] Add domain-level bounce rate checking
- [ ] Test domain pause workflow

### Week 3: Open Rate Monitoring
- [ ] Add 3-day open rate window detection
- [ ] Implement domain pause on low open rate
- [ ] Add daily morning kill summary report
- [ ] Test stealth spam filtering detection

### Week 4: Testing & Rollout
- [ ] Write comprehensive test suite
- [ ] Deploy in monitoring-only mode
- [ ] Review logs and tune thresholds
- [ ] Enable gradual rollout (one rule at a time)
- [ ] Document final implementation

---

## 🚨 Critical Thresholds (Gemini SOP)

| Metric | Threshold | Action | Charm Status |
|--------|-----------|--------|--------------|
| **Inbox spam bounce** | 1 bounce (550) | Pause inbox | ✅ **WORKING** |
| **Domain bounce rate** | >2.5% (7 days) | Pause domain | ⚠️ **5% today** |
| **Domain spam complaint** | >0.1% | Pause domain | ⚠️ **Uses count** |
| **Domain open rate** | <20% (3 days) | Pause domain | ❌ **MISSING** |
| **Strike 2** | 2 inboxes (48h) | Pause + rotate bench | ❌ **MISSING** |
| **Strike 3** | 3 inboxes (48h) | Kill + swap | ❌ **MISSING** |

---

## 💡 Key Differences: Gemini vs Charm

### Philosophy
- **Gemini:** Graduated strikes (1→2→3) with time windows
- **Charm:** Instant kill on threshold breach

### Approach
- **Gemini:** Domain-level rotation (swap entire domains)
- **Charm:** Inbox-level rotation (promote backup inboxes)

### Recommendation
**HYBRID:** Keep Charm's instant kill for catastrophic errors (550 5.7.705), add Gemini's graduated strikes for escalating issues (550 5.7.1)

---

## 📞 Who to Contact

| Question Type | Contact |
|--------------|---------|
| **Database schema changes** | DBA Team |
| **Sync worker modifications** | Backend Team |
| **Dashboard/UI updates** | Frontend Team |
| **DevOps/deployment** | Platform Team |
| **Gemini SOP questions** | [Campaign Ops Lead] |

---

## 🔗 Full Documentation Links

1. **EXECUTIVE-SUMMARY-gemini-sop.md** - For executives/managers (3 pages)
2. **gemini-sop-charm-exact-mapping.md** - For engineers (50+ pages, full SQL/Python)
3. **gemini-sop-action-items.md** - For project managers (action items + sprints)
4. **charm-vs-gemini-sop-comparison.md** - For architects (deep technical analysis)

---

## ⏱️ Time Estimates

| Task | Estimated Time |
|------|---------------|
| Create rolling window table | 2-3 days |
| Add domain pause logic | 1-2 days |
| Implement open rate monitoring | 2-3 days |
| Testing & QA | 3-5 days |
| **TOTAL** | **15-20 days** |

**Team Size:** 1-2 engineers
**Duration:** 3-4 weeks
**Cost:** $20K-$28K (internal) OR $40K-$60K (external)

---

**Last Updated:** 2026-02-23
**Status:** Ready for Implementation
**Next Action:** Get executive approval → Assign engineers → Start Week 1
