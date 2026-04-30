"""Incubation Watcher — per-workspace incubation graduation daemon.

Extracted from sync_modules/lifecycle_tag_sync.py per the
docs/plans/emailbison-sync-decomposition.md plan. Owns:

  - 14-business-day graduation: incubating → reserve (Google) / live (Microsoft)
  - Tagging new warmup inboxes with 'incubating'
  - Untagging 'incubating' from inboxes already at lifecycle='active'

Per-workspace API key model (workspace_api_keys.key_token). No switch_workspace.
"""

__version__ = "0.1.0"
