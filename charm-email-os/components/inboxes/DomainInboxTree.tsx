'use client';

import { useState, useMemo } from 'react';
import { ChevronRight, ChevronDown, Globe, Mail, AlertCircle, CheckCircle, AlertTriangle, XCircle } from 'lucide-react';
import { cn } from '@/lib/utils';
import type { Domain, Inbox } from '@/lib/types';

interface DomainInboxTreeProps {
  domains: Domain[];
  inboxes: Inbox[];
  className?: string;
}

// Status badge colors
const STATUS_STYLES: Record<string, { bg: string; text: string; icon: typeof CheckCircle }> = {
  healthy: { bg: 'bg-green-100', text: 'text-green-700', icon: CheckCircle },
  live: { bg: 'bg-green-100', text: 'text-green-700', icon: CheckCircle },
  active: { bg: 'bg-green-100', text: 'text-green-700', icon: CheckCircle },
  warning: { bg: 'bg-yellow-100', text: 'text-yellow-700', icon: AlertTriangle },
  critical: { bg: 'bg-red-100', text: 'text-red-700', icon: AlertCircle },
  dead: { bg: 'bg-gray-100', text: 'text-gray-500', icon: XCircle },
  unknown: { bg: 'bg-gray-100', text: 'text-gray-500', icon: AlertCircle },
};

function StatusBadge({ status }: { status: string }) {
  const style = STATUS_STYLES[status] || STATUS_STYLES.unknown;
  const Icon = style.icon;

  return (
    <span className={cn(
      'inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium',
      style.bg,
      style.text
    )}>
      <Icon className="h-3 w-3" />
      {status}
    </span>
  );
}

interface DomainRowProps {
  domain: Domain;
  inboxes: Inbox[];
  isExpanded: boolean;
  onToggle: () => void;
}

function DomainRow({ domain, inboxes, isExpanded, onToggle }: DomainRowProps) {
  const healthState = domain.healthState || 'unknown';
  const liveInboxes = inboxes.filter(i => i.inboxState === 'live' || i.healthState === 'healthy').length;
  const deadInboxes = inboxes.filter(i => i.inboxState === 'dead' || i.healthState === 'dead').length;

  return (
    <div className="border rounded-lg overflow-hidden">
      {/* Domain Header */}
      <button
        onClick={onToggle}
        className="w-full flex items-center gap-3 px-4 py-3 bg-muted/50 hover:bg-muted transition-colors text-left"
      >
        {isExpanded ? (
          <ChevronDown className="h-4 w-4 text-muted-foreground flex-shrink-0" />
        ) : (
          <ChevronRight className="h-4 w-4 text-muted-foreground flex-shrink-0" />
        )}
        <Globe className="h-4 w-4 text-muted-foreground flex-shrink-0" />
        <span className="font-medium truncate flex-1">{domain.domain || domain.domainName}</span>
        <div className="flex items-center gap-3 flex-shrink-0">
          <span className="text-sm text-muted-foreground">
            {inboxes.length} inbox{inboxes.length !== 1 ? 'es' : ''}
            {deadInboxes > 0 && (
              <span className="text-red-600 ml-1">({deadInboxes} dead)</span>
            )}
          </span>
          <StatusBadge status={healthState} />
        </div>
      </button>

      {/* Inboxes List */}
      {isExpanded && inboxes.length > 0 && (
        <div className="border-t divide-y">
          {inboxes.map((inbox) => (
            <InboxRow key={inbox.id} inbox={inbox} />
          ))}
        </div>
      )}

      {isExpanded && inboxes.length === 0 && (
        <div className="px-4 py-3 text-sm text-muted-foreground border-t">
          No inboxes for this domain
        </div>
      )}
    </div>
  );
}

function InboxRow({ inbox }: { inbox: Inbox }) {
  const healthState = inbox.healthState || inbox.inboxState || 'unknown';
  const email = inbox.email || inbox.emailAddress || '';

  return (
    <div className="flex items-center gap-3 px-4 py-2 pl-12 hover:bg-muted/30 transition-colors">
      <Mail className="h-4 w-4 text-muted-foreground flex-shrink-0" />
      <span className="text-sm truncate flex-1 font-mono">{email}</span>
      <div className="flex items-center gap-3 flex-shrink-0">
        {inbox.hardBounces7d != null && inbox.hardBounces7d > 0 && (
          <span className="text-xs text-orange-600">
            {inbox.hardBounces7d} bounce{inbox.hardBounces7d !== 1 ? 's' : ''} (7d)
          </span>
        )}
        <StatusBadge status={healthState} />
      </div>
    </div>
  );
}

export function DomainInboxTree({ domains, inboxes, className }: DomainInboxTreeProps) {
  const [expandedDomains, setExpandedDomains] = useState<Set<string>>(new Set());

  // Group inboxes by domain
  const inboxesByDomain = useMemo(() => {
    const map = new Map<string, Inbox[]>();

    for (const inbox of inboxes) {
      // Try to match by domainId first, then by domain name
      let domainKey = inbox.domainId;

      if (!domainKey) {
        // Extract domain from email address
        const emailDomain = (inbox.email || inbox.emailAddress || '').split('@')[1];
        if (emailDomain) {
          const matchingDomain = domains.find(d =>
            (d.domain || d.domainName) === emailDomain
          );
          if (matchingDomain) {
            domainKey = matchingDomain.id;
          }
        }
      }

      if (domainKey) {
        const existing = map.get(domainKey) || [];
        existing.push(inbox);
        map.set(domainKey, existing);
      }
    }

    return map;
  }, [domains, inboxes]);

  const toggleDomain = (domainId: string) => {
    setExpandedDomains(prev => {
      const next = new Set(prev);
      if (next.has(domainId)) {
        next.delete(domainId);
      } else {
        next.add(domainId);
      }
      return next;
    });
  };

  const expandAll = () => {
    setExpandedDomains(new Set(domains.map(d => d.id)));
  };

  const collapseAll = () => {
    setExpandedDomains(new Set());
  };

  // Summary stats
  const totalInboxes = inboxes.length;
  const liveInboxes = inboxes.filter(i => i.inboxState === 'live' || i.healthState === 'healthy').length;
  const deadInboxes = inboxes.filter(i => i.inboxState === 'dead' || i.healthState === 'dead').length;
  const warningInboxes = inboxes.filter(i => i.healthState === 'warning' || i.healthState === 'critical').length;

  return (
    <div className={cn('space-y-4', className)}>
      {/* Summary Bar */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-4 text-sm">
          <span className="font-medium">{domains.length} domains</span>
          <span className="text-muted-foreground">|</span>
          <span>{totalInboxes} inboxes</span>
          {liveInboxes > 0 && (
            <span className="text-green-600">{liveInboxes} live</span>
          )}
          {warningInboxes > 0 && (
            <span className="text-yellow-600">{warningInboxes} warning</span>
          )}
          {deadInboxes > 0 && (
            <span className="text-red-600">{deadInboxes} dead</span>
          )}
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={expandAll}
            className="text-xs text-muted-foreground hover:text-foreground transition-colors"
          >
            Expand all
          </button>
          <span className="text-muted-foreground">|</span>
          <button
            onClick={collapseAll}
            className="text-xs text-muted-foreground hover:text-foreground transition-colors"
          >
            Collapse all
          </button>
        </div>
      </div>

      {/* Domain List */}
      <div className="space-y-2">
        {domains.length === 0 ? (
          <div className="text-center py-8 text-muted-foreground">
            No domains found
          </div>
        ) : (
          domains.map((domain) => (
            <DomainRow
              key={domain.id}
              domain={domain}
              inboxes={inboxesByDomain.get(domain.id) || []}
              isExpanded={expandedDomains.has(domain.id)}
              onToggle={() => toggleDomain(domain.id)}
            />
          ))
        )}
      </div>
    </div>
  );
}
