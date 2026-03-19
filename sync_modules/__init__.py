"""
EmailBison Daily Sync Modules

Modular sync system for keeping local database fresh with EmailBison data.

Modules:
- emailbison_client: Shared API client with workspace switching
- audit_logger: Audit logging to sync_audit_log table
- slack_alerter: Slack webhook notifications
- sync_accounts: Account & domain synchronization
- sync_campaigns: Campaign & metrics synchronization
- sync_events: Event & response message synchronization
- sync_warmup: Warmup status and statistics synchronization
- health_checks: Inbox and domain health evaluation
- kill_processor: Kill queue processing with 24hr tagging
- retention: Data retention/cleanup logic
- sync_oauth: OAuth config scraping from EmailBison UI
- daily_snapshot: Daily volume and capacity snapshots for dashboard charts
- lifecycle_tag_sync: Lifecycle tag management (incubating/live) in EmailBison
- set_tag_sync: A-Set/B-Set tag management and promotion in EmailBison
- sync_engagement: Inbox engagement metrics (opens, replies, interested) with daily snapshots
"""

from .emailbison_client import EmailBisonClient
from .audit_logger import AuditLogger, SyncResult
from .slack_alerter import SlackAlerter
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

__all__ = [
    'EmailBisonClient',
    'AuditLogger',
    'SyncResult',
    'SlackAlerter',
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
]
