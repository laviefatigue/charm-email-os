# Calculate Hypertide Order

## Purpose
Calculate optimal Hypertide order quantities from inbox targets or monthly sending volume requirements.

## When to Use
- Client needs a specific number of inboxes
- Planning infrastructure based on monthly email volume
- Estimating costs for proposals
- Mixed Entra + Google requirements

## Order Specifications

### Hypertide Entra (Recommended for B2B)
| Metric | Value |
|--------|-------|
| Domains per order | 2 |
| Inboxes per domain | 50 |
| **Inboxes per order** | **100** |
| Monthly capacity | 5,000 emails |
| Base cost | $50/month |

### Hypertide Google (Good for Consumer)
| Metric | Value |
|--------|-------|
| Domains per order | 5 |
| Inboxes per domain | 3 |
| **Inboxes per order** | **15** |
| Monthly capacity | 5,000+ emails |
| Base cost | $50/month |

## Calculation Formulas

### Inbox Target to Orders
```
Entra orders = ceil(target_inboxes / 100)
Google orders = ceil(target_inboxes / 15)
```

### Volume to Orders
```
Total orders = ceil(monthly_volume / 5000)
```

### Volume to Inboxes (Rule of Thumb)
```
Total inboxes = monthly_volume / 100
```
Each inbox safely sends ~100 emails/month.

## Quick Reference Tables

### Entra Orders
| Target Inboxes | Orders Needed | Actual Inboxes | Monthly Cost |
|----------------|---------------|----------------|--------------|
| 100 | 1 | 100 | $50 |
| 200 | 2 | 200 | $100 |
| 300 | 3 | 300 | $150 |
| 500 | 5 | 500 | $250 |
| 750 | 8 | 800 | $400 |
| 1000 | 10 | 1000 | $500 |

### Google Orders
| Target Inboxes | Orders Needed | Actual Inboxes | Monthly Cost |
|----------------|---------------|----------------|--------------|
| 15 | 1 | 15 | $50 |
| 30 | 2 | 30 | $100 |
| 45 | 3 | 45 | $150 |
| 75 | 5 | 75 | $250 |
| 105 | 7 | 105 | $350 |
| 150 | 10 | 150 | $500 |

## Mixed Order Calculations

**Key Constraint**: Hypertide allows only ONE order type per checkout.

For clients needing both Entra AND Google:
1. Calculate Entra orders separately
2. Calculate Google orders separately
3. Execute as TWO purchase flows
4. Automation handles this automatically via `BundlePurchaseAutomation`

### Example: 500 Entra + 100 Google
```
Entra: ceil(500 / 100) = 5 orders → 500 inboxes
Google: ceil(100 / 15) = 7 orders → 105 inboxes

Total: 12 orders, 605 inboxes, $600/month
```

## Recommended Inbox Splits

### B2B Focused (Business Emails)
- 80% Entra, 20% Google
- Entra excels at Outlook/corporate delivery

### Consumer Focused (Personal Emails)
- 40% Entra, 60% Google
- Gmail-to-Gmail has high deliverability

### Balanced (Mixed Targeting)
- 70% Entra, 30% Google
- Default recommendation

## Example Calculation Flow

**Scenario**: Client needs 50,000 emails/month, B2B focus

1. **Inbox estimate**: 50,000 / 100 = 500 inboxes
2. **Apply B2B split (80/20)**:
   - Entra: 400 inboxes
   - Google: 100 inboxes
3. **Calculate orders**:
   - Entra: ceil(400 / 100) = 4 orders
   - Google: ceil(100 / 15) = 7 orders
4. **Total**: 11 orders, ~$550/month, ~505 inboxes

## Automation Integration

The automation package at `D:\BrainOn\Hypertide\automation` provides:

```python
from hypertide_automation import calculate_optimal_orders, InboxTarget

# Preview calculation (no browser needed)
target = InboxTarget(entra_inboxes=500, google_inboxes=100)
breakdown = calculate_optimal_orders(target)

print(f"Entra: {breakdown.entra_orders} orders = {breakdown.entra_inboxes_actual} inboxes")
print(f"Google: {breakdown.google_orders} orders = {breakdown.google_inboxes_actual} inboxes")
print(f"Monthly cost: ${breakdown.estimated_monthly_cost}")
```

## Related Knowledge
- [order-calculations.yaml](../knowledge/order-calculations.yaml) - Detailed formulas
- [platform-architecture.yaml](../knowledge/platform-architecture.yaml) - UI flow documentation
