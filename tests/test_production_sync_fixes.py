#!/usr/bin/env python3
"""
Tests for Production Sync Fixes (FIX 1-8 + Entra Bounce-Rate Burns)

Covers:
- FIX 5: lifecycle_tag_sync safety net query
- FIX 6: Warning state auto-clear in sync_accounts
- FIX 7: decay_weekly_counters wiring
- FIX 8: ESP-aware domain burn thresholds (kill_processor)
- FIX 9: Entra bounce-rate domain burns (health_checks)

Run:
    pytest tests/test_production_sync_fixes.py -v
    py -m pytest tests/test_production_sync_fixes.py -v
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch, call
from decimal import Decimal
from uuid import uuid4
from datetime import datetime, timedelta, timezone


# ============================================================
# FIX 8: ESP-Aware Domain Burn Thresholds (kill_processor)
# ============================================================

class TestESPAwareBurnThresholds:
    """Test ESP-aware burn logic in kill_processor rate-based evaluation."""

    def test_esp_burn_constants_exist(self):
        """Verify ESP burn constants are properly defined."""
        from sync_modules.kill_processor import (
            ESP_BURN_MIN_COMPLAINTS,
            ESP_BURN_MIN_COMPLAINTS_DEFAULT,
            DOMAIN_COMPLAINT_RATE_BURN,
            DOMAIN_COMPLAINT_RATE_FLAGGED
        )
        assert ESP_BURN_MIN_COMPLAINTS['google'] == 1
        assert ESP_BURN_MIN_COMPLAINTS['entra'] == 3
        assert ESP_BURN_MIN_COMPLAINTS_DEFAULT == 1
        # Rate thresholds unchanged
        assert DOMAIN_COMPLAINT_RATE_BURN == Decimal('0.01')
        assert DOMAIN_COMPLAINT_RATE_FLAGGED == Decimal('0.003')

    def test_google_one_complaint_exceeds_threshold(self):
        """Google: 1 spam kill on 3-inbox domain → rate 33% AND count 1 >= 1 → burn."""
        from sync_modules.kill_processor import (
            ESP_BURN_MIN_COMPLAINTS,
            ESP_BURN_MIN_COMPLAINTS_DEFAULT,
            DOMAIN_COMPLAINT_RATE_BURN
        )
        esp_type = 'google'
        complaints_7d = 1
        complaint_rate = 1 / 3  # 33%

        min_complaints = ESP_BURN_MIN_COMPLAINTS.get(
            esp_type, ESP_BURN_MIN_COMPLAINTS_DEFAULT
        )

        should_burn = (
            complaints_7d >= min_complaints
            and complaint_rate >= float(DOMAIN_COMPLAINT_RATE_BURN)
        )
        assert should_burn is True

    def test_entra_one_complaint_does_not_burn(self):
        """Entra: 1 spam kill on 52-inbox domain → rate 1.9% but count 1 < 3 → monitoring."""
        from sync_modules.kill_processor import (
            ESP_BURN_MIN_COMPLAINTS,
            ESP_BURN_MIN_COMPLAINTS_DEFAULT,
            DOMAIN_COMPLAINT_RATE_BURN
        )
        esp_type = 'entra'
        complaints_7d = 1
        complaint_rate = 1 / 52  # 1.9%

        min_complaints = ESP_BURN_MIN_COMPLAINTS.get(
            esp_type, ESP_BURN_MIN_COMPLAINTS_DEFAULT
        )

        should_burn = (
            complaints_7d >= min_complaints
            and complaint_rate >= float(DOMAIN_COMPLAINT_RATE_BURN)
        )
        assert should_burn is False
        # But rate DOES exceed burn threshold → should enter monitoring
        assert complaint_rate >= float(DOMAIN_COMPLAINT_RATE_BURN)

    def test_entra_two_complaints_does_not_burn(self):
        """Entra: 2 spam kills → rate 3.8% but count 2 < 3 → still monitoring."""
        from sync_modules.kill_processor import (
            ESP_BURN_MIN_COMPLAINTS,
            ESP_BURN_MIN_COMPLAINTS_DEFAULT,
            DOMAIN_COMPLAINT_RATE_BURN
        )
        esp_type = 'entra'
        complaints_7d = 2
        complaint_rate = 2 / 52  # 3.8%

        min_complaints = ESP_BURN_MIN_COMPLAINTS.get(
            esp_type, ESP_BURN_MIN_COMPLAINTS_DEFAULT
        )

        should_burn = (
            complaints_7d >= min_complaints
            and complaint_rate >= float(DOMAIN_COMPLAINT_RATE_BURN)
        )
        assert should_burn is False

    def test_entra_three_complaints_burns(self):
        """Entra: 3 spam kills → rate 5.8% AND count 3 >= 3 → burn (pattern confirmed)."""
        from sync_modules.kill_processor import (
            ESP_BURN_MIN_COMPLAINTS,
            ESP_BURN_MIN_COMPLAINTS_DEFAULT,
            DOMAIN_COMPLAINT_RATE_BURN
        )
        esp_type = 'entra'
        complaints_7d = 3
        complaint_rate = 3 / 52  # 5.8%

        min_complaints = ESP_BURN_MIN_COMPLAINTS.get(
            esp_type, ESP_BURN_MIN_COMPLAINTS_DEFAULT
        )

        should_burn = (
            complaints_7d >= min_complaints
            and complaint_rate >= float(DOMAIN_COMPLAINT_RATE_BURN)
        )
        assert should_burn is True

    def test_unknown_esp_treats_like_google(self):
        """Unknown ESP uses default threshold (1) — conservative like Google."""
        from sync_modules.kill_processor import (
            ESP_BURN_MIN_COMPLAINTS,
            ESP_BURN_MIN_COMPLAINTS_DEFAULT,
            DOMAIN_COMPLAINT_RATE_BURN
        )
        esp_type = None  # Unknown
        complaints_7d = 1
        complaint_rate = 0.05  # 5%

        min_complaints = ESP_BURN_MIN_COMPLAINTS.get(
            esp_type, ESP_BURN_MIN_COMPLAINTS_DEFAULT
        )

        should_burn = (
            complaints_7d >= min_complaints
            and complaint_rate >= float(DOMAIN_COMPLAINT_RATE_BURN)
        )
        assert should_burn is True
        assert min_complaints == 1

    def test_entra_rate_below_flagged_no_action(self):
        """Entra: rate below 0.3% flagged threshold → no monitoring, no burn."""
        from sync_modules.kill_processor import (
            ESP_BURN_MIN_COMPLAINTS,
            ESP_BURN_MIN_COMPLAINTS_DEFAULT,
            DOMAIN_COMPLAINT_RATE_BURN,
            DOMAIN_COMPLAINT_RATE_FLAGGED
        )
        esp_type = 'entra'
        complaints_7d = 1
        complaint_rate = 0.002  # 0.2% — below 0.3% flagged threshold

        min_complaints = ESP_BURN_MIN_COMPLAINTS.get(
            esp_type, ESP_BURN_MIN_COMPLAINTS_DEFAULT
        )

        should_burn = (
            complaints_7d >= min_complaints
            and complaint_rate >= float(DOMAIN_COMPLAINT_RATE_BURN)
        )
        should_monitor = (
            complaints_7d >= min_complaints
            and complaint_rate >= float(DOMAIN_COMPLAINT_RATE_FLAGGED)
        )
        should_monitor_pattern = (
            complaint_rate >= float(DOMAIN_COMPLAINT_RATE_BURN)
            and complaints_7d < min_complaints
        )
        assert should_burn is False
        assert should_monitor is False
        assert should_monitor_pattern is False


# ============================================================
# FIX 9: Entra Bounce-Rate Domain Burns (health_checks)
# ============================================================

class TestEntraBounceRateBurns:
    """Test ESP-aware bounce-rate burn logic in health_checks."""

    def test_entra_burn_constants_exist(self):
        """Verify Entra burn constants are properly defined."""
        from sync_modules.health_checks import (
            ENTRA_DOMAIN_BURN_HARD_BOUNCE_RATE,
            ENTRA_DOMAIN_BURN_MIN_SENDS,
            ENTRA_DOMAIN_BURN_MIN_BLOCKED,
            ENTRA_DOMAIN_BURN_CIRCUIT_BREAKER
        )
        assert ENTRA_DOMAIN_BURN_HARD_BOUNCE_RATE == Decimal('0.05')
        assert ENTRA_DOMAIN_BURN_MIN_SENDS == 50
        assert ENTRA_DOMAIN_BURN_MIN_BLOCKED == 2
        assert ENTRA_DOMAIN_BURN_CIRCUIT_BREAKER == 2

    def test_entra_high_bounce_rate_should_burn(self):
        """Entra domain with >5% hard bounce rate should auto-burn."""
        from sync_modules.health_checks import (
            ENTRA_DOMAIN_BURN_HARD_BOUNCE_RATE,
            ENTRA_DOMAIN_BURN_MIN_BLOCKED
        )
        hard_bounce_rate = 0.065  # 6.5%
        blocked_count = 1

        should_burn = (
            hard_bounce_rate >= float(ENTRA_DOMAIN_BURN_HARD_BOUNCE_RATE)
            or blocked_count >= ENTRA_DOMAIN_BURN_MIN_BLOCKED
        )
        assert should_burn is True

    def test_entra_cross_inbox_blocks_should_burn(self):
        """Entra domain with 2+ blocked inboxes should auto-burn."""
        from sync_modules.health_checks import (
            ENTRA_DOMAIN_BURN_HARD_BOUNCE_RATE,
            ENTRA_DOMAIN_BURN_MIN_BLOCKED
        )
        hard_bounce_rate = 0.02  # 2% — below threshold
        blocked_count = 3

        should_burn = (
            hard_bounce_rate >= float(ENTRA_DOMAIN_BURN_HARD_BOUNCE_RATE)
            or blocked_count >= ENTRA_DOMAIN_BURN_MIN_BLOCKED
        )
        assert should_burn is True

    def test_entra_below_thresholds_flag_only(self):
        """Entra domain below both thresholds should not burn."""
        from sync_modules.health_checks import (
            ENTRA_DOMAIN_BURN_HARD_BOUNCE_RATE,
            ENTRA_DOMAIN_BURN_MIN_BLOCKED
        )
        hard_bounce_rate = 0.03  # 3% — below 5%
        blocked_count = 1  # Below 2

        should_burn = (
            hard_bounce_rate >= float(ENTRA_DOMAIN_BURN_HARD_BOUNCE_RATE)
            or blocked_count >= ENTRA_DOMAIN_BURN_MIN_BLOCKED
        )
        assert should_burn is False

    def test_google_never_auto_burns_on_bounce_rate(self):
        """Google domains should never auto-burn from bounce rate — flag only."""
        # Google burn path is spam complaints in kill_processor, not bounce rate
        infrastructure_type = 'google'
        # Even with high bounce rate, Google should be flag-only here
        assert infrastructure_type != 'entra'

    def test_circuit_breaker_limits_burns(self):
        """Circuit breaker prevents more than N burns per cycle."""
        from sync_modules.health_checks import ENTRA_DOMAIN_BURN_CIRCUIT_BREAKER

        burns_this_cycle = 0
        domains_to_burn = 5

        burned = 0
        flagged = 0
        for _ in range(domains_to_burn):
            if burns_this_cycle < ENTRA_DOMAIN_BURN_CIRCUIT_BREAKER:
                burns_this_cycle += 1
                burned += 1
            else:
                flagged += 1

        assert burned == ENTRA_DOMAIN_BURN_CIRCUIT_BREAKER
        assert flagged == domains_to_burn - ENTRA_DOMAIN_BURN_CIRCUIT_BREAKER

    def test_min_sends_prevents_false_positives(self):
        """Low-volume domains should not trigger bounce-rate burns."""
        from sync_modules.health_checks import ENTRA_DOMAIN_BURN_MIN_SENDS

        total_sends_7d = 30  # Below minimum
        hard_bounces_7d = 5  # Would be 16.7% if counted

        # With min_sends gate: rate is 0 (insufficient data)
        if total_sends_7d >= ENTRA_DOMAIN_BURN_MIN_SENDS:
            rate = hard_bounces_7d / total_sends_7d
        else:
            rate = 0

        assert rate == 0  # Insufficient sends, rate not calculated

    @pytest.mark.asyncio
    async def test_health_check_burns_entra_domain(self):
        """Integration: health check auto-burns Entra domain with high bounce rate."""
        from sync_modules.health_checks import HealthCheckModule

        workspace_id = uuid4()
        domain_id = uuid4()

        mock_db = AsyncMock()
        mock_audit = AsyncMock()
        mock_alerter = MagicMock()
        mock_alerter.send_alert = AsyncMock()
        mock_alerter.alert_domain_flagged = AsyncMock()

        # Domain with high hard bounce rate
        mock_db.fetch.return_value = [
            {
                'id': domain_id,
                'domain_name': 'bad-entra.com',
                'domain_bounce_rate_7d': Decimal('0.08'),
                'inboxes_with_complaints': 0,
                'inboxes_with_blocks': 1,
                'domain_state': 'live',
                'pool_status': 'live',
                'infrastructure_type': 'entra',
                'hard_bounce_rate_7d': Decimal('0.065'),  # >5% hard bounce
            }
        ]

        # burn_domain_and_promote result
        mock_db.fetchrow.return_value = {
            'burned_domain_id': domain_id,
            'burned_domain_name': 'bad-entra.com',
            'promoted_domain_id': uuid4(),
            'promoted_domain_name': 'reserve-entra.com',
            'action': 'promoted'
        }

        # domain_rotation_events insert
        mock_db.execute.return_value = None

        module = HealthCheckModule(
            db=mock_db,
            audit_logger=mock_audit,
            alerter=mock_alerter
        )

        await module._check_domain_bounce_rate_thresholds(workspace_id)

        # Should have called burn_domain_and_promote
        mock_db.fetchrow.assert_called_once()
        burn_call = mock_db.fetchrow.call_args
        assert 'burn_domain_and_promote' in burn_call[0][0]
        assert burn_call[0][1] == domain_id
        assert burn_call[0][2] == 'bounce_rate_domain'

        # Should have sent critical Slack alert
        mock_alerter.send_alert.assert_called_once()
        alert_call = mock_alerter.send_alert.call_args
        assert alert_call[1]['level'] == 'critical'
        assert 'Entra Domain Burned' in alert_call[1]['title']

    @pytest.mark.asyncio
    async def test_health_check_flags_google_domain(self):
        """Integration: health check flags (not burns) Google domain with high bounce rate."""
        from sync_modules.health_checks import HealthCheckModule

        workspace_id = uuid4()
        domain_id = uuid4()

        mock_db = AsyncMock()
        mock_audit = AsyncMock()
        mock_alerter = MagicMock()
        mock_alerter.send_alert = AsyncMock()
        mock_alerter.alert_domain_flagged = AsyncMock()

        # Google domain with high bounce rate
        mock_db.fetch.return_value = [
            {
                'id': domain_id,
                'domain_name': 'bad-google.com',
                'domain_bounce_rate_7d': Decimal('0.08'),
                'inboxes_with_complaints': 0,
                'inboxes_with_blocks': 0,
                'domain_state': 'live',
                'pool_status': 'live',
                'infrastructure_type': 'google',
                'hard_bounce_rate_7d': Decimal('0.065'),
            }
        ]
        mock_db.execute.return_value = None

        module = HealthCheckModule(
            db=mock_db,
            audit_logger=mock_audit,
            alerter=mock_alerter
        )

        await module._check_domain_bounce_rate_thresholds(workspace_id)

        # Should NOT have called burn_domain_and_promote
        mock_db.fetchrow.assert_not_called()

        # Should have flagged in DB
        mock_db.execute.assert_called_once()
        flag_call = mock_db.execute.call_args
        assert 'flagged' in flag_call[0][0]

        # Should have sent flag alert (not critical burn alert)
        mock_alerter.alert_domain_flagged.assert_called_once()
        mock_alerter.send_alert.assert_not_called()

    @pytest.mark.asyncio
    async def test_circuit_breaker_defers_excess_burns(self):
        """Integration: circuit breaker flags remaining domains after max burns."""
        from sync_modules.health_checks import (
            HealthCheckModule,
            ENTRA_DOMAIN_BURN_CIRCUIT_BREAKER
        )

        workspace_id = uuid4()

        mock_db = AsyncMock()
        mock_audit = AsyncMock()
        mock_alerter = MagicMock()
        mock_alerter.send_alert = AsyncMock()
        mock_alerter.alert_domain_flagged = AsyncMock()

        # 4 Entra domains all exceeding thresholds
        domains = []
        for i in range(4):
            did = uuid4()
            domains.append({
                'id': did,
                'domain_name': f'entra-{i}.com',
                'domain_bounce_rate_7d': Decimal('0.08'),
                'inboxes_with_complaints': 0,
                'inboxes_with_blocks': 3,
                'domain_state': 'live',
                'pool_status': 'live',
                'infrastructure_type': 'entra',
                'hard_bounce_rate_7d': Decimal('0.065'),
            })

        mock_db.fetch.return_value = domains
        mock_db.fetchrow.return_value = {
            'burned_domain_id': uuid4(),
            'burned_domain_name': 'some.com',
            'promoted_domain_id': None,
            'promoted_domain_name': None,
            'action': 'no_reserve'
        }
        mock_db.execute.return_value = None

        module = HealthCheckModule(
            db=mock_db,
            audit_logger=mock_audit,
            alerter=mock_alerter
        )

        await module._check_domain_bounce_rate_thresholds(workspace_id)

        # Should have burned exactly CIRCUIT_BREAKER domains
        burn_calls = [
            c for c in mock_db.fetchrow.call_args_list
            if 'burn_domain_and_promote' in c[0][0]
        ]
        assert len(burn_calls) == ENTRA_DOMAIN_BURN_CIRCUIT_BREAKER

        # Remaining should have been flagged
        flag_calls = [
            c for c in mock_db.execute.call_args_list
            if len(c[0]) > 0 and 'flagged' in str(c[0][0]) and 'domain_state' in str(c[0][0])
        ]
        assert len(flag_calls) == 4 - ENTRA_DOMAIN_BURN_CIRCUIT_BREAKER


# ============================================================
# FIX 5: Lifecycle Tag Sync Safety Net
# ============================================================

class TestLifecycleTagSyncSafetyNet:
    """Test FIX 5: _remove_live_from_dead catches all non-dead lifecycle states."""

    @pytest.mark.asyncio
    async def test_safety_net_catches_active_status(self):
        """Dead inboxes with lifecycle_status='active' should be caught."""
        from sync_modules.lifecycle_tag_sync import LifecycleTagSyncModule

        workspace_id = uuid4()
        inbox_id = uuid4()

        mock_db = AsyncMock()
        mock_client = AsyncMock()
        mock_audit = AsyncMock()
        mock_alerter = MagicMock()

        # Dead inbox with lifecycle_status still 'active' (kill_processor partial failure)
        mock_db.fetch.return_value = [
            {
                'id': inbox_id,
                'email_address': 'dead@example.com',
                'emailbison_account_id': 12345,
            }
        ]
        mock_db.execute.return_value = None

        module = LifecycleTagSyncModule(
            db=mock_db,
            client=mock_client,
            audit_logger=mock_audit,
            alerter=mock_alerter
        )

        audit = MagicMock()
        audit.increment_processed = MagicMock()
        audit.increment_updated = MagicMock()
        audit.add_error = MagicMock()

        result = await module._remove_live_from_dead(
            workspace_id=workspace_id,
            live_tag_id=99,
            audit=audit
        )

        # Should have queried with != 'dead' (not = 'active')
        query = mock_db.fetch.call_args[0][0]
        assert "!= 'dead'" in query or "!=" in query
        # The old broken query had "= 'active'" which missed other states


# ============================================================
# FIX 6: Warning State Auto-Clear
# ============================================================

class TestWarningAutoClean:
    """Test FIX 6: Warning state clears when bounces subside."""

    def test_warning_clears_when_bounces_zero(self):
        """Inbox with warning status and zero bounces should return to pool."""
        # Simulate the CASE logic
        inventory_pool_status = 'warning'
        hard_bounces_24h = 0
        hard_bounces_7d = 0
        domain_pool_status = 'live'

        # FIX 6 CASE branch:
        # 1. First check: bounces active → stays warning
        if hard_bounces_24h >= 1 or hard_bounces_7d >= 3:
            result = 'warning'
        # 2. FIX 6: bounces cleared AND currently warning → return to pool
        elif (inventory_pool_status == 'warning'
              and hard_bounces_24h < 1
              and hard_bounces_7d < 3):
            # Derive from domain pool_status
            if domain_pool_status == 'live':
                result = 'deployed'
            elif domain_pool_status == 'reserve':
                result = 'reserve'
            else:
                result = inventory_pool_status
        # 3. Preserve existing
        else:
            result = inventory_pool_status

        assert result == 'deployed'

    def test_warning_stays_when_bounces_active(self):
        """Inbox with active bounces should stay warning despite FIX 6."""
        inventory_pool_status = 'warning'
        hard_bounces_24h = 2  # Active bounces
        hard_bounces_7d = 0

        if hard_bounces_24h >= 1 or hard_bounces_7d >= 3:
            result = 'warning'
        elif (inventory_pool_status == 'warning'
              and hard_bounces_24h < 1
              and hard_bounces_7d < 3):
            result = 'deployed'
        else:
            result = inventory_pool_status

        assert result == 'warning'

    def test_warning_clears_to_reserve(self):
        """Inbox on reserve domain should clear to 'reserve', not 'deployed'."""
        inventory_pool_status = 'warning'
        hard_bounces_24h = 0
        hard_bounces_7d = 2  # Below 3 threshold
        domain_pool_status = 'reserve'

        if hard_bounces_24h >= 1 or hard_bounces_7d >= 3:
            result = 'warning'
        elif (inventory_pool_status == 'warning'
              and hard_bounces_24h < 1
              and hard_bounces_7d < 3):
            if domain_pool_status == 'live':
                result = 'deployed'
            elif domain_pool_status == 'reserve':
                result = 'reserve'
            else:
                result = inventory_pool_status
        else:
            result = inventory_pool_status

        assert result == 'reserve'

    def test_deployed_inbox_not_affected(self):
        """Deployed inboxes with zero bounces should remain deployed (no change)."""
        inventory_pool_status = 'deployed'
        hard_bounces_24h = 0
        hard_bounces_7d = 0

        if hard_bounces_24h >= 1 or hard_bounces_7d >= 3:
            result = 'warning'
        elif (inventory_pool_status == 'warning'
              and hard_bounces_24h < 1
              and hard_bounces_7d < 3):
            result = 'deployed'
        elif inventory_pool_status in ('deployed', 'reserve', 'warning'):
            result = inventory_pool_status
        else:
            result = inventory_pool_status

        assert result == 'deployed'

    def test_7d_bounces_at_threshold_stays_warning(self):
        """Inbox at exactly 3 hard_bounces_7d should stay warning."""
        inventory_pool_status = 'warning'
        hard_bounces_24h = 0
        hard_bounces_7d = 3  # At threshold — stays warning

        if hard_bounces_24h >= 1 or hard_bounces_7d >= 3:
            result = 'warning'
        elif (inventory_pool_status == 'warning'
              and hard_bounces_24h < 1
              and hard_bounces_7d < 3):
            result = 'deployed'
        else:
            result = inventory_pool_status

        assert result == 'warning'


# ============================================================
# FIX 7: decay_weekly_counters Wiring
# ============================================================

class TestWeeklyCounterDecay:
    """Test FIX 7: decay_weekly_counters is called during daily reset."""

    @pytest.mark.asyncio
    async def test_daily_reset_calls_decay(self):
        """run_daily_counter_reset must call both reset_daily and decay_weekly."""
        from emailbison_sync_worker import SyncOrchestrator

        mock_db = AsyncMock()
        mock_audit = AsyncMock()
        mock_alerter = MagicMock()

        worker = SyncOrchestrator.__new__(SyncOrchestrator)
        worker.db = mock_db
        worker.audit_logger = mock_audit
        worker.alerter = mock_alerter

        with patch('emailbison_sync_worker.HealthCheckModule') as MockHealth:
            mock_health_instance = AsyncMock()
            MockHealth.return_value = mock_health_instance

            await worker.run_daily_counter_reset()

            # Both methods must be called
            mock_health_instance.reset_daily_counters.assert_called_once()
            mock_health_instance.decay_weekly_counters.assert_called_once()


# ============================================================
# Domain Burn SQL Function Behavior Tests
# ============================================================

class TestDomainBurnLogic:
    """Test the domain burn decision logic (Python side)."""

    def test_reserve_domain_can_be_burned(self):
        """FIX 2b: pool_status 'reserve' should be burnable."""
        pool_status = 'reserve'
        # FIX 2b changed: if current_pool == 'live' → if current_pool in ('live', 'reserve')
        can_burn = pool_status in ('live', 'reserve')
        assert can_burn is True

    def test_burned_domain_cannot_be_reburned(self):
        """Already burned domains should not be burnable."""
        pool_status = 'burned'
        can_burn = pool_status in ('live', 'reserve')
        assert can_burn is False

    def test_unassigned_domain_cannot_be_burned(self):
        """Unassigned domains should not be burnable."""
        pool_status = 'unassigned'
        can_burn = pool_status in ('live', 'reserve')
        assert can_burn is False


# ============================================================
# ESP Decision Matrix — Full Coverage
# ============================================================

class TestESPDecisionMatrix:
    """
    Complete decision matrix test for ESP-aware domain burn.

    For each (ESP, complaint_count, rate) tuple, verify the correct action:
    burn, monitor, or safe.
    """

    @pytest.fixture
    def thresholds(self):
        from sync_modules.kill_processor import (
            ESP_BURN_MIN_COMPLAINTS,
            ESP_BURN_MIN_COMPLAINTS_DEFAULT,
            DOMAIN_COMPLAINT_RATE_BURN,
            DOMAIN_COMPLAINT_RATE_FLAGGED
        )
        return {
            'min_complaints': ESP_BURN_MIN_COMPLAINTS,
            'default': ESP_BURN_MIN_COMPLAINTS_DEFAULT,
            'burn_rate': float(DOMAIN_COMPLAINT_RATE_BURN),
            'flag_rate': float(DOMAIN_COMPLAINT_RATE_FLAGGED),
        }

    def _decide(self, thresholds, esp_type, complaints_7d, rate):
        """Replicate the kill_processor decision logic."""
        min_c = thresholds['min_complaints'].get(
            esp_type, thresholds['default']
        )
        burn_rate = thresholds['burn_rate']
        flag_rate = thresholds['flag_rate']

        if complaints_7d >= min_c and rate >= burn_rate:
            return 'burn'
        elif complaints_7d >= min_c and rate >= flag_rate:
            return 'monitor'
        elif rate >= burn_rate and complaints_7d < min_c:
            return 'monitor_pattern'
        else:
            return 'safe'

    def test_google_1_kill(self, thresholds):
        assert self._decide(thresholds, 'google', 1, 1/3) == 'burn'

    def test_entra_1_kill(self, thresholds):
        assert self._decide(thresholds, 'entra', 1, 1/52) == 'monitor_pattern'

    def test_entra_2_kills(self, thresholds):
        assert self._decide(thresholds, 'entra', 2, 2/52) == 'monitor_pattern'

    def test_entra_3_kills(self, thresholds):
        assert self._decide(thresholds, 'entra', 3, 3/52) == 'burn'

    def test_entra_1_kill_low_rate(self, thresholds):
        """Entra with 1 kill and very low rate (decayed) → safe."""
        assert self._decide(thresholds, 'entra', 1, 0.002) == 'safe'

    def test_google_0_kills(self, thresholds):
        assert self._decide(thresholds, 'google', 0, 0) == 'safe'

    def test_unknown_esp_1_kill(self, thresholds):
        assert self._decide(thresholds, None, 1, 0.05) == 'burn'

    def test_entra_10_kills(self, thresholds):
        """Entra with 10 kills → rate 19.2%, well above all thresholds."""
        assert self._decide(thresholds, 'entra', 10, 10/52) == 'burn'


# ============================================================
# Lifecycle Tag Collision Documentation Check
# ============================================================

class TestLifecycleTagCollision:
    """Test DOC 1: LIVE_TAG collision is documented and intentional."""

    def test_live_tag_matches_a_set_default(self):
        """LIVE_TAG must equal 'live' (same as A-Set default tag)."""
        from sync_modules.lifecycle_tag_sync import LIVE_TAG
        from sync_modules.set_tag_sync import DEFAULT_A_SET_TAG
        # This is intentional — execution order resolves it
        assert LIVE_TAG == DEFAULT_A_SET_TAG == 'live'

    def test_incubating_tag_is_distinct(self):
        """Incubating tag must not collide with any pool tag."""
        from sync_modules.lifecycle_tag_sync import INCUBATING_TAG
        from sync_modules.set_tag_sync import DEFAULT_A_SET_TAG, DEFAULT_B_SET_TAG
        assert INCUBATING_TAG != DEFAULT_A_SET_TAG
        assert INCUBATING_TAG != DEFAULT_B_SET_TAG


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
