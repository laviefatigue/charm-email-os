# Pages

Page / screen documentation for the operator UI overhaul. Each major surface gets its own `.md` here capturing intent, data sources, interactions, edge cases.

## Status

Pages not yet enumerated. Will be filled in during `/design-app` once the brand and design system are settled.

Likely surfaces (working list, to be refined):

- **Fleet overview** — workspaces with health/status roll-ups
- **Workspace detail** — per-workspace inboxes, domains, campaigns, drift
- **Operations / daemon control** — EOD reapply, Plan F, hypertide audit, tag op worker
- **Pipeline view** — incubating → reserve → live → dead/burned flow
- **Reports** — burn velocity, burned-domain attachments, hypertide drift, the existing 7 operator-queue reports
- **Settings (per-workspace)** — `eod_reapply_enabled`, `manages_via_hypertide`, `package_id`, target overrides

## See Also

- [[design-system/index]]
- [[design-system/brand-brief]]
