"""
List Segment Tracker

V3 Section 12: List Management

Tracks bounce patterns by lead segment and enrichment provider.
Quarantines bad segments to prevent repeated inbox damage.

Thresholds (configurable via env):
- 2+ hard bounces from segment → quarantine segment
- 3+ hard bounces from segment → purge permanently
- Bounce rate > 3% on list → stop using
- 3+ bounces from enrichment provider → flag provider
"""
import os
from datetime import datetime, timezone
from typing import Dict, List, Optional
from uuid import UUID
import asyncpg

# V3 Section 12 thresholds
SEGMENT_QUARANTINE_BOUNCES = int(os.getenv('SEGMENT_QUARANTINE_BOUNCES', 2))
SEGMENT_PURGE_BOUNCES = int(os.getenv('SEGMENT_PURGE_BOUNCES', 3))
SEGMENT_BOUNCE_RATE_THRESHOLD = float(os.getenv('SEGMENT_BOUNCE_RATE_THRESHOLD', 0.03))  # 3%
PROVIDER_FLAG_BOUNCES = int(os.getenv('PROVIDER_FLAG_BOUNCES', 3))


class ListSegmentTracker:
    """
    Tracks bounce patterns by lead source for V3 compliance.

    When bounces occur, this module:
    1. Identifies the lead's source segment
    2. Increments segment bounce counters
    3. Quarantines/purges segments that exceed thresholds
    4. Flags enrichment providers with high bounce rates

    NOTE: Quarantine = local flag. Human operators decide actual action.
    """

    def __init__(self, db: asyncpg.Pool):
        self.db = db

    async def track_bounce_from_lead(
        self,
        workspace_id: UUID,
        lead_id: UUID,
        bounce_type: str = 'hard'
    ) -> Dict:
        """
        Track a bounce back to its source segment.

        Returns dict with any state changes (quarantine, purge, flag).
        """
        # Get lead's segment and provider
        lead = await self.db.fetchrow("""
            SELECT
                id,
                email,
                segment_id,
                enrichment_provider,
                source
            FROM leads
            WHERE id = $1
        """, lead_id)

        if not lead:
            return {'tracked': False, 'reason': 'Lead not found'}

        result = {
            'tracked': True,
            'segment_action': None,
            'provider_action': None
        }

        # Track bounce to segment if linked
        if lead['segment_id']:
            segment_result = await self._update_segment_bounces(
                segment_id=lead['segment_id'],
                workspace_id=workspace_id
            )
            result['segment_action'] = segment_result

        # Track bounce to enrichment provider if known
        if lead['enrichment_provider']:
            provider_result = await self._update_provider_bounces(
                provider_name=lead['enrichment_provider'],
                workspace_id=workspace_id
            )
            result['provider_action'] = provider_result

        return result

    async def _update_segment_bounces(
        self,
        segment_id: UUID,
        workspace_id: UUID
    ) -> Optional[str]:
        """
        Increment segment bounce counter and check thresholds.

        Returns action taken: 'quarantined', 'purged', or None.
        """
        # Increment bounce counter
        await self.db.execute("""
            UPDATE list_segments
            SET
                bounces_caused = COALESCE(bounces_caused, 0) + 1,
                bounces_7d = COALESCE(bounces_7d, 0) + 1,
                last_bounce_at = NOW(),
                bounce_rate = CASE
                    WHEN total_leads > 0
                    THEN ((COALESCE(bounces_caused, 0) + 1)::DECIMAL / total_leads)
                    ELSE 0
                END,
                updated_at = NOW()
            WHERE id = $1
        """, segment_id)

        # Get updated counts
        segment = await self.db.fetchrow("""
            SELECT
                segment_name,
                segment_state,
                bounces_caused,
                bounce_rate,
                total_leads
            FROM list_segments
            WHERE id = $1
        """, segment_id)

        if not segment:
            return None

        current_state = segment['segment_state']
        bounces = segment['bounces_caused'] or 0
        bounce_rate = float(segment['bounce_rate'] or 0)

        # V3 thresholds: 3+ bounces = purge, 2+ bounces = quarantine
        if bounces >= SEGMENT_PURGE_BOUNCES and current_state != 'purged':
            await self.db.execute("""
                UPDATE list_segments
                SET
                    segment_state = 'purged',
                    purged_at = NOW(),
                    updated_at = NOW()
                WHERE id = $1
            """, segment_id)
            print(f"    [SEGMENT PURGED] {segment['segment_name']}: {bounces} bounces")
            return 'purged'

        elif bounces >= SEGMENT_QUARANTINE_BOUNCES and current_state == 'active':
            await self.db.execute("""
                UPDATE list_segments
                SET
                    segment_state = 'quarantined',
                    quarantined_at = NOW(),
                    quarantine_reason = $2,
                    updated_at = NOW()
                WHERE id = $1
            """, segment_id, f'{bounces} hard bounces from segment')
            print(f"    [SEGMENT QUARANTINE] {segment['segment_name']}: {bounces} bounces")
            return 'quarantined'

        # Also check bounce rate threshold
        elif bounce_rate > SEGMENT_BOUNCE_RATE_THRESHOLD and current_state == 'active':
            await self.db.execute("""
                UPDATE list_segments
                SET
                    segment_state = 'quarantined',
                    quarantined_at = NOW(),
                    quarantine_reason = $2,
                    updated_at = NOW()
                WHERE id = $1
            """, segment_id, f'Bounce rate {bounce_rate*100:.1f}% exceeds {SEGMENT_BOUNCE_RATE_THRESHOLD*100}% threshold')
            print(f"    [SEGMENT QUARANTINE] {segment['segment_name']}: {bounce_rate*100:.1f}% bounce rate")
            return 'quarantined'

        return None

    async def _update_provider_bounces(
        self,
        provider_name: str,
        workspace_id: UUID
    ) -> Optional[str]:
        """
        Increment enrichment provider bounce counter and check flag threshold.

        Returns 'flagged' if threshold exceeded, else None.
        """
        # Upsert provider record
        await self.db.execute("""
            INSERT INTO enrichment_providers (workspace_id, provider_name)
            VALUES ($1, $2)
            ON CONFLICT (workspace_id, provider_name) DO NOTHING
        """, workspace_id, provider_name)

        # Increment bounce counter
        await self.db.execute("""
            UPDATE enrichment_providers
            SET
                bounces_caused = COALESCE(bounces_caused, 0) + 1,
                bounces_7d = COALESCE(bounces_7d, 0) + 1,
                last_bounce_at = NOW(),
                updated_at = NOW()
            WHERE workspace_id = $1 AND provider_name = $2
        """, workspace_id, provider_name)

        # Check flag threshold
        provider = await self.db.fetchrow("""
            SELECT
                provider_state,
                bounces_caused
            FROM enrichment_providers
            WHERE workspace_id = $1 AND provider_name = $2
        """, workspace_id, provider_name)

        if provider and (provider['bounces_caused'] or 0) >= PROVIDER_FLAG_BOUNCES:
            if provider['provider_state'] == 'active':
                await self.db.execute("""
                    UPDATE enrichment_providers
                    SET
                        provider_state = 'flagged',
                        flagged_at = NOW(),
                        flag_reason = $3,
                        updated_at = NOW()
                    WHERE workspace_id = $1 AND provider_name = $2
                """, workspace_id, provider_name, f'{provider["bounces_caused"]} bounces - audit all data from this provider')
                print(f"    [PROVIDER FLAGGED] {provider_name}: {provider['bounces_caused']} bounces")
                return 'flagged'

        return None

    async def create_segment_from_upload(
        self,
        workspace_id: UUID,
        segment_name: str,
        source_file: str,
        total_leads: int,
        segment_type: str = 'csv_upload',
        source_provider: str = None
    ) -> UUID:
        """
        Create a new segment record when leads are uploaded.

        Returns the segment_id to link to leads.
        """
        result = await self.db.fetchrow("""
            INSERT INTO list_segments (
                workspace_id,
                segment_name,
                segment_type,
                source_file,
                source_provider,
                total_leads
            ) VALUES ($1, $2, $3, $4, $5, $6)
            ON CONFLICT (workspace_id, segment_name)
            DO UPDATE SET
                total_leads = list_segments.total_leads + $6,
                updated_at = NOW()
            RETURNING id
        """, workspace_id, segment_name, segment_type, source_file, source_provider, total_leads)

        return result['id']

    async def get_segment_health(self, workspace_id: UUID) -> Dict:
        """Get segment health summary for a workspace."""
        stats = await self.db.fetchrow("""
            SELECT
                COUNT(*) as total_segments,
                COUNT(*) FILTER (WHERE segment_state = 'active') as active,
                COUNT(*) FILTER (WHERE segment_state = 'quarantined') as quarantined,
                COUNT(*) FILTER (WHERE segment_state = 'purged') as purged,
                SUM(bounces_caused) as total_bounces
            FROM list_segments
            WHERE workspace_id = $1
        """, workspace_id)

        providers = await self.db.fetchrow("""
            SELECT
                COUNT(*) as total_providers,
                COUNT(*) FILTER (WHERE provider_state = 'flagged') as flagged
            FROM enrichment_providers
            WHERE workspace_id = $1
        """, workspace_id)

        return {
            'segments': {
                'total': stats['total_segments'] or 0,
                'active': stats['active'] or 0,
                'quarantined': stats['quarantined'] or 0,
                'purged': stats['purged'] or 0,
                'total_bounces': stats['total_bounces'] or 0
            },
            'providers': {
                'total': providers['total_providers'] or 0,
                'flagged': providers['flagged'] or 0
            }
        }

    async def decay_7d_counters(self):
        """Decay 7-day bounce counters (run daily)."""
        # Segments
        await self.db.execute("""
            UPDATE list_segments
            SET
                bounces_7d = GREATEST(0, (COALESCE(bounces_7d, 0) * 0.86)::INTEGER),
                updated_at = NOW()
            WHERE bounces_7d > 0
        """)

        # Providers
        await self.db.execute("""
            UPDATE enrichment_providers
            SET
                bounces_7d = GREATEST(0, (COALESCE(bounces_7d, 0) * 0.86)::INTEGER),
                updated_at = NOW()
            WHERE bounces_7d > 0
        """)

        print("[ListSegmentTracker] Decayed 7d bounce counters")
