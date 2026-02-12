"""
Audit Logger

Tracks every sync operation to the sync_audit_log table.
Provides structured logging and error tracking for debugging.
"""
import json
import traceback
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID
import asyncpg


@dataclass
class SyncResult:
    """Result of a sync operation."""
    audit_id: UUID
    sync_type: str
    status: str  # 'completed', 'failed', 'partial'
    records_processed: int = 0
    records_created: int = 0
    records_updated: int = 0
    records_failed: int = 0
    error_message: Optional[str] = None
    errors: List[Dict] = field(default_factory=list)
    duration_seconds: float = 0.0

    @property
    def success(self) -> bool:
        return self.status == 'completed'

    def to_dict(self) -> Dict:
        return {
            'audit_id': str(self.audit_id),
            'sync_type': self.sync_type,
            'status': self.status,
            'records_processed': self.records_processed,
            'records_created': self.records_created,
            'records_updated': self.records_updated,
            'records_failed': self.records_failed,
            'error_message': self.error_message,
            'duration_seconds': self.duration_seconds
        }


class AuditLogger:
    """Audit logging for sync operations."""

    def __init__(self, db: asyncpg.Pool):
        self.db = db

    async def start_audit(
        self,
        sync_type: str,
        workspace_id: UUID = None,
        metadata: Dict = None
    ) -> 'AuditContext':
        """Start a new audit record and return context manager."""
        audit_id = await self.db.fetchval("""
            INSERT INTO sync_audit_log (sync_type, workspace_id, metadata)
            VALUES ($1, $2, $3)
            RETURNING id
        """, sync_type, workspace_id, json.dumps(metadata) if metadata else None)

        return AuditContext(
            db=self.db,
            audit_id=audit_id,
            sync_type=sync_type,
            workspace_id=workspace_id,
            started_at=datetime.now()
        )

    async def get_last_successful_sync(
        self,
        sync_type: str,
        workspace_id: UUID = None
    ) -> Optional[datetime]:
        """Get timestamp of last successful sync for incremental syncing."""
        if workspace_id:
            return await self.db.fetchval("""
                SELECT last_successful_sync FROM sync_status
                WHERE sync_type = $1 AND workspace_id = $2
            """, sync_type, workspace_id)
        else:
            return await self.db.fetchval("""
                SELECT MAX(completed_at) FROM sync_audit_log
                WHERE sync_type = $1 AND status = 'completed'
            """, sync_type)

    async def update_sync_status(
        self,
        sync_type: str,
        workspace_id: UUID,
        record_count: int
    ):
        """Update sync status for incremental syncing."""
        await self.db.execute("""
            INSERT INTO sync_status (workspace_id, sync_type, last_successful_sync, last_sync_record_count, updated_at)
            VALUES ($1, $2, NOW(), $3, NOW())
            ON CONFLICT (workspace_id, sync_type) DO UPDATE SET
                last_successful_sync = NOW(),
                last_sync_record_count = $3,
                updated_at = NOW()
        """, workspace_id, sync_type, record_count)


class AuditContext:
    """Context manager for a single audit operation."""

    def __init__(
        self,
        db: asyncpg.Pool,
        audit_id: UUID,
        sync_type: str,
        workspace_id: UUID,
        started_at: datetime
    ):
        self.db = db
        self.audit_id = audit_id
        self.sync_type = sync_type
        self.workspace_id = workspace_id
        self.started_at = started_at
        self.records_processed = 0
        self.records_created = 0
        self.records_updated = 0
        self.records_failed = 0
        self.errors: List[Dict] = []

    def increment_processed(self):
        self.records_processed += 1

    def increment_created(self):
        self.records_created += 1

    def increment_updated(self):
        self.records_updated += 1

    def add_error(self, record_id: Any, error: str, details: Dict = None):
        """Log an error for a specific record."""
        self.records_failed += 1
        self.errors.append({
            'record_id': str(record_id) if record_id else None,
            'error': error,
            'details': details,
            'timestamp': datetime.now().isoformat()
        })

    async def complete(
        self,
        status: str = 'completed',
        error_message: str = None
    ) -> SyncResult:
        """
        Complete the audit and update the database.

        Args:
            status: 'completed', 'failed', or 'partial'
            error_message: Top-level error message if failed
        """
        completed_at = datetime.now()
        duration = (completed_at - self.started_at).total_seconds()

        # Determine status based on errors
        if status == 'completed' and self.records_failed > 0:
            status = 'partial'

        error_details = {'errors': self.errors} if self.errors else None

        await self.db.execute("""
            UPDATE sync_audit_log
            SET
                completed_at = $2,
                status = $3,
                records_processed = $4,
                records_created = $5,
                records_updated = $6,
                records_failed = $7,
                error_message = $8,
                error_details = $9
            WHERE id = $1
        """,
            self.audit_id,
            completed_at,
            status,
            self.records_processed,
            self.records_created,
            self.records_updated,
            self.records_failed,
            error_message,
            json.dumps(error_details) if error_details else None
        )

        return SyncResult(
            audit_id=self.audit_id,
            sync_type=self.sync_type,
            status=status,
            records_processed=self.records_processed,
            records_created=self.records_created,
            records_updated=self.records_updated,
            records_failed=self.records_failed,
            error_message=error_message,
            errors=self.errors,
            duration_seconds=duration
        )

    async def fail(self, error: Exception) -> SyncResult:
        """Mark audit as failed with exception details."""
        error_message = str(error)
        error_details = {
            'exception_type': type(error).__name__,
            'traceback': traceback.format_exc(),
            'partial_errors': self.errors
        }

        completed_at = datetime.now()
        duration = (completed_at - self.started_at).total_seconds()

        await self.db.execute("""
            UPDATE sync_audit_log
            SET
                completed_at = $2,
                status = 'failed',
                records_processed = $3,
                records_created = $4,
                records_updated = $5,
                records_failed = $6,
                error_message = $7,
                error_details = $8
            WHERE id = $1
        """,
            self.audit_id,
            completed_at,
            self.records_processed,
            self.records_created,
            self.records_updated,
            self.records_failed,
            error_message,
            json.dumps(error_details)
        )

        return SyncResult(
            audit_id=self.audit_id,
            sync_type=self.sync_type,
            status='failed',
            records_processed=self.records_processed,
            records_created=self.records_created,
            records_updated=self.records_updated,
            records_failed=self.records_failed,
            error_message=error_message,
            errors=self.errors,
            duration_seconds=duration
        )
