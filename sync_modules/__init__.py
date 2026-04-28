"""
EmailBison Daily Sync Modules

Modular sync system for keeping local database fresh with EmailBison data.

Data-pull modules (EB → DB), concurrent-safe:
- workspace_sync_queue: Persistent DB job queue for concurrent per-workspace sync
- sync_accounts: Account & domain synchronization (no switch_workspace)
- sync_campaigns: Campaign & metrics synchronization (no switch_workspace)
- sync_events: Event & response message synchronization (no switch_workspace)
- sync_warmup: Warmup status and statistics synchronization (no switch_workspace)
- sync_engagement: Inbox engagement metrics with daily snapshots (no switch_workspace)

Tagging/write modules (DB → EB), driven by WorkspaceWriteOrchestrator:
- workspace_writes: Concurrent per-workspace driver for the three modules below
- lifecycle_tag_sync: Lifecycle tag management (incubating/live) in EmailBison
- set_tag_sync: A-Set/B-Set tag management and promotion in EmailBison
- kill_processor: Kill queue processing with 24hr tagging

Shared infrastructure:
- emailbison_client: Per-workspace EmailBison API client (workspace-scoped API key)
- audit_logger: Audit logging to sync_audit_log table
- slack_alerter: Slack webhook notifications
- health_checks: Inbox and domain health evaluation
- retention: Data retention/cleanup logic
- sync_oauth: OAuth config scraping from EmailBison UI
- daily_snapshot: Daily volume and capacity snapshots for dashboard charts
- onboarding_monitor: New workspace/client onboarding tracking
"""

from .emailbison_client import EmailBisonClient
from .audit_logger import AuditLogger, SyncResult
from .slack_alerter import SlackAlerter
from .workspace_sync_queue import WorkspaceSyncQueue
from .sync_accounts import AccountSyncModule
from .sync_campaigns import CampaignSyncModule
from .sync_events import EventSyncModule
from .sync_warmup import WarmupSyncModule
from .health_checks import HealthCheckModule
from .kill_processor import KillProcessor
from .retention import RetentionManager
from .sync_oauth import OAuthSyncModule
from .daily_snapshot import DailySnapshotModule
from .lifecycle_tag_sync import LifecycleTagSyncModule
from .set_tag_sync import SetTagSyncModule
from .sync_engagement import EngagementSyncModule
from .onboarding_monitor import OnboardingMonitorModule
from .workspace_writes import WorkspaceWriteOrchestrator
from .overhaul_audit import OverhaulAuditModule

__all__ = [
    'EmailBisonClient',
    'AuditLogger',
    'SyncResult',
    'SlackAlerter',
    'WorkspaceSyncQueue',
    'AccountSyncModule',
    'CampaignSyncModule',
    'EventSyncModule',
    'WarmupSyncModule',
    'HealthCheckModule',
    'KillProcessor',
    'RetentionManager',
    'OAuthSyncModule',
    'DailySnapshotModule',
    'LifecycleTagSyncModule',
    'SetTagSyncModule',
    'EngagementSyncModule',
    'OnboardingMonitorModule',
    'WorkspaceWriteOrchestrator',
    'OverhaulAuditModule',
]
