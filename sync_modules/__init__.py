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
- health_checks: Inbox and domain health evaluation
- kill_processor: Kill queue processing with 24hr tagging
- retention: Data retention/cleanup logic
- sync_oauth: OAuth config scraping from EmailBison UI
"""

from .emailbison_client import EmailBisonClient
from .audit_logger import AuditLogger, SyncResult
from .slack_alerter import SlackAlerter
from .sync_accounts import AccountSyncModule
from .sync_campaigns import CampaignSyncModule
from .sync_events import EventSyncModule
from .health_checks import HealthCheckModule
from .kill_processor import KillProcessor
from .retention import RetentionManager
from .sync_oauth import OAuthSyncModule

__all__ = [
    'EmailBisonClient',
    'AuditLogger',
    'SyncResult',
    'SlackAlerter',
    'AccountSyncModule',
    'CampaignSyncModule',
    'EventSyncModule',
    'HealthCheckModule',
    'KillProcessor',
    'RetentionManager',
    'OAuthSyncModule',
]
