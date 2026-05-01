"""Unit tests for the per-workspace inbox auditor (Plan: inbox-audit-overhaul.md).

Phase 2/3 of the overhaul. These are unit-only — testing the structured
report shape, severity classification, and serialization. Integration
tests against real Postgres + integrity-section SQL would require Docker
and live in test_overhaul.py / future test_inbox_auditor_integration.py.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from uuid import UUID, uuid4

from sync_modules.inbox_auditor import (
    AuditSection,
    InboxAuditor,
    WorkspaceAuditResult,
)


def _section(code, name, severity, count=0, sample_ids=None, details=None) -> AuditSection:
    return AuditSection(
        code=code, name=name, severity=severity, count=count,
        sample_ids=sample_ids or [], details=details or {},
    )


def _result(sections, total=0) -> WorkspaceAuditResult:
    return WorkspaceAuditResult(
        workspace_id=UUID('00000000-0000-0000-0000-000000000001'),
        workspace_name='TestWS',
        audit_date='2026-05-01',
        total_inboxes=total,
        inbox_id_set=[],
        sections=sections,
    )


class TestAuditSection:
    def test_default_fields(self):
        s = _section('I-1', 'Test', 'info')
        assert s.code == 'I-1'
        assert s.severity == 'info'
        assert s.count == 0
        assert s.sample_ids == []
        assert s.details == {}

    def test_with_samples(self):
        s = _section('I-2', 'Stuck', 'warn', count=5, sample_ids=['a', 'b'])
        assert s.count == 5
        assert s.sample_ids == ['a', 'b']


class TestWorkspaceAuditResult:
    def test_summary_format(self):
        sections = [
            _section('I-1', 'Critical thing', 'critical', count=3),
            _section('I-2', 'Warn thing', 'warn', count=1),
            _section('I-3', 'Info thing', 'info', count=0),
        ]
        result = _result(sections, total=100)
        s = result.summary()
        assert 'TestWS' in s
        assert '100 inboxes' in s
        assert 'critical' in s

    def test_summary_clean_workspace(self):
        sections = [
            _section('I-1', 'Critical thing', 'info', count=0),
            _section('I-2', 'Warn thing', 'info', count=0),
        ]
        result = _result(sections, total=50)
        # 0 critical, 0 warn — entirely clean
        assert '0 critical' in result.summary()

    def test_to_audit_data_shape(self):
        sections = [
            _section('I-1', 'Foo', 'critical', count=1),
            _section('I-2', 'Bar', 'warn', count=2),
            _section('I-3', 'Baz', 'info', count=0),
        ]
        result = _result(sections, total=10)
        data = result.to_audit_data()
        assert data['workspace_name'] == 'TestWS'
        assert data['audit_date'] == '2026-05-01'
        assert data['total_inboxes'] == 10
        assert len(data['sections']) == 3
        assert data['critical_count'] == 1
        assert data['warn_count'] == 1
        assert 'generated_at' in data

    def test_to_audit_data_is_jsonable(self):
        sections = [_section('I-1', 'Foo', 'info')]
        result = _result(sections)
        # Must be json-serializable for the JSONB INSERT to work
        s = json.dumps(result.to_audit_data())
        round_trip = json.loads(s)
        assert round_trip['workspace_name'] == 'TestWS'

    def test_critical_count_only_critical(self):
        sections = [
            _section('I-1', 'C1', 'critical', count=1),
            _section('I-2', 'C2', 'critical', count=2),
            _section('I-3', 'W',  'warn',     count=3),
            _section('I-4', 'I',  'info',     count=0),
        ]
        result = _result(sections)
        data = result.to_audit_data()
        assert data['critical_count'] == 2
        assert data['warn_count'] == 1


class TestInboxAuditorPrivateHelpers:
    """Test the static helpers that don't need a DB connection."""

    def test_count_critical_inboxes_picks_i1(self):
        sections = [
            _section('I-1', 'Cross-tenant', 'critical', count=5),
            _section('I-2', 'Stuck', 'warn', count=10),
        ]
        result = _result(sections)
        assert InboxAuditor._count_critical_inboxes(result) == 5

    def test_count_critical_inboxes_zero_when_i1_clean(self):
        sections = [
            _section('I-1', 'Cross-tenant', 'info', count=0),
            _section('I-2', 'Stuck', 'warn', count=10),
        ]
        result = _result(sections)
        assert InboxAuditor._count_critical_inboxes(result) == 0

    def test_count_disconnected_picks_i6(self):
        sections = [
            _section('I-1', 'X', 'info', count=0),
            _section('I-6', 'Reserve+disc', 'warn', count=7),
        ]
        result = _result(sections)
        assert InboxAuditor._count_disconnected_inboxes_in_scope(result) == 7


class TestSeverityClassification:
    """Pin the severity-rule semantics — these flow into operator alerts."""

    def test_i1_zero_is_info(self):
        # Pre-firewall: zero is good. Post-firewall: zero is expected.
        s = _section('I-1', 'Cross-tenant pollution', 'info', count=0)
        assert s.severity == 'info'

    def test_i1_nonzero_is_critical(self):
        # Any I-1 hit means the chk_quarantined_no_pool was bypassed.
        s = _section('I-1', 'Cross-tenant pollution', 'critical', count=1)
        assert s.severity == 'critical'

    def test_i5_quarantined_is_warn_not_critical(self):
        # Quarantined inboxes are EXPECTED behavior (firewall caught them).
        # They warrant operator review but aren't critical.
        s = _section('I-5', 'Quarantined inboxes', 'warn', count=3)
        assert s.severity == 'warn'
