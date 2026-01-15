# Hypertide Screenshots Directory

This directory contains annotated screenshots of key Hypertide UI elements to help agents provide accurate visual guidance to users.

## Captured Screenshots

### Platform Overview
- [x] `hypertide-signin-page.png` - Login page showing invitation-only access model
- [x] `hypertide-dashboard-main.png` - Main dashboard with orders grouped by forwarding domain
- [x] `hypertide-billing-page.png` - Billing page with subscription records and domain status guide

### Order Management
- [x] `hypertide-choose-plan.png` - Plan selection page (Entra vs Google)
- [x] `hypertide-entra-bulk-options.png` - Entra bulk order dropdown (1-20 orders, up to 100k emails/mo)
- [x] `hypertide-google-bulk-options.png` - Google bulk order dropdown (1-20 orders, up to 100k emails/mo)
- [x] `hypertide-order-details-hirecharm.png` - Order details showing associated domains and statuses
- [x] `hypertide-configure-options.png` - Configure menu showing Update Forwarding/Usernames/Replace options

### Still Needed
- [ ] `hypertide-update-forwarding.png` - Update forwarding URL modal
- [ ] `hypertide-update-usernames.png` - Update usernames modal
- [ ] `hypertide-replace-domains.png` - Domain replacement interface
- [ ] `hypertide-download-inboxes.png` - Inbox credentials export
- [ ] `hypertide-view-subscription-details.png` - Subscription detail modal

## Screenshot Guidelines

1. **Annotate key elements** - Use red boxes/arrows to highlight important buttons/fields
2. **Include context** - Show enough of the surrounding UI for orientation
3. **Consistent naming** - Use lowercase-kebab-case.png format
4. **Update after UI changes** - Screenshots become stale when platforms update

## Usage in Skills

Reference screenshots in skill files like this:
```markdown
See screenshot: `screenshots/hypertide-dashboard-main.png`
Look for the "Place New Order" button in the top right.
```

## Key UI Elements Documented

### Dashboard
- Orders grouped by "Forwarding Domain" (client identifier)
- Stats: Time saved, Inboxes count, Money saved
- Filters: Sending Tools, Statuses, Order Types
- Order panel: Download, Configure, Order buttons

### Order Details
- Total/Active Domains count
- Monthly Capacity
- Associated domains with inbox type icons (Azure/Gmail)
- Order status: done, cancelled, pending

### Configure Menu
- Update Forwarding
- Update Usernames
- Replace Domains

### Billing
- Subscription records with domain lists
- Domain status color coding (Active/To Be Cancelled/Cancelled)
- View Details / View Invoices actions

## Last Updated
- Directory created: 2025-12-10
- Screenshots captured: 2025-12-10
