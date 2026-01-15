'use client';

import { useState, useMemo } from 'react';
import { ChevronRight, ChevronDown, Globe, Mail, AlertCircle, CheckCircle, AlertTriangle, XCircle, Filter, SortAsc, Loader2 } from 'lucide-react';
import { cn } from '@/lib/utils';
import type { Domain, Inbox } from '@/lib/types';

interface DomainInboxTreeProps {
  domains: Domain[];
  inboxes: Inbox[];
  className?: string;
  onExpandDomain?: (domainId: string) => void;  // Callback for lazy loading
  loadingDomainIds?: Set<string>;  // Domains currently loading
}

type FilterType = 'all' | 'healthy' | 'warning' | 'with-inboxes' | 'no-inboxes';
type SortType = 'name' | 'inboxes' | 'health';

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
  isLoading: boolean;
  onToggle: () => void;
}

function DomainRow({ domain, inboxes, isExpanded, isLoading, onToggle }: DomainRowProps) {
  const healthState = domain.healthState || 'unknown';
  // Use API's inboxCount if available, otherwise fall back to local count
  const inboxCount = domain.inboxCount ?? inboxes.length;
  const liveCount = domain.liveInboxCount ?? 0;
  const deadCount = domain.deadInboxCount ?? 0;

  return (
    <div className="border rounded-lg overflow-hidden">
      {/* Domain Header */}
      <button
        onClick={onToggle}
        className="w-full flex items-center gap-3 px-4 py-3 bg-muted/50 hover:bg-muted transition-colors text-left"
      >
        {isLoading ? (
          <Loader2 className="h-4 w-4 text-muted-foreground flex-shrink-0 animate-spin" />
        ) : isExpanded ? (
          <ChevronDown className="h-4 w-4 text-muted-foreground flex-shrink-0" />
        ) : (
          <ChevronRight className="h-4 w-4 text-muted-foreground flex-shrink-0" />
        )}
        <Globe className="h-4 w-4 text-muted-foreground flex-shrink-0" />
        <span className="font-medium truncate flex-1">{domain.domain || domain.domainName}</span>
        <div className="flex items-center gap-3 flex-shrink-0">
          <span className="text-sm text-muted-foreground">
            {inboxCount} inbox{inboxCount !== 1 ? 'es' : ''}
            {liveCount > 0 && (
              <span className="text-green-600 ml-1">({liveCount} live)</span>
            )}
            {deadCount > 0 && (
              <span className="text-red-600 ml-1">({deadCount} dead)</span>
            )}
          </span>
          <StatusBadge status={healthState} />
        </div>
      </button>

      {/* Inboxes List */}
      {isExpanded && isLoading && (
        <div className="px-4 py-3 text-sm text-muted-foreground border-t flex items-center gap-2">
          <Loader2 className="h-4 w-4 animate-spin" />
          Loading inboxes...
        </div>
      )}

      {isExpanded && !isLoading && inboxes.length > 0 && (
        <div className="border-t divide-y max-h-96 overflow-y-auto">
          {inboxes.map((inbox) => (
            <InboxRow key={inbox.id} inbox={inbox} />
          ))}
        </div>
      )}

      {isExpanded && !isLoading && inboxes.length === 0 && inboxCount > 0 && (
        <div className="px-4 py-3 text-sm text-muted-foreground border-t">
          Click to load {inboxCount} inboxes
        </div>
      )}

      {isExpanded && !isLoading && inboxCount === 0 && (
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

export function DomainInboxTree({ domains, inboxes, className, onExpandDomain, loadingDomainIds = new Set() }: DomainInboxTreeProps) {
  const [expandedDomains, setExpandedDomains] = useState<Set<string>>(new Set());
  const [filter, setFilter] = useState<FilterType>('all');
  const [sortBy, setSortBy] = useState<SortType>('name');

  // Group inboxes by domain
  const inboxesByDomain = useMemo(() => {
    const map = new Map<string, Inbox[]>();

    for (const inbox of inboxes) {
      let domainKey = inbox.domainId;

      if (!domainKey) {
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

  // Filter and sort domains
  const filteredDomains = useMemo(() => {
    let result = [...domains];

    // Apply filter
    switch (filter) {
      case 'healthy':
        result = result.filter(d => d.healthState === 'healthy' || d.healthState === 'live');
        break;
      case 'warning':
        result = result.filter(d => d.healthState === 'warning' || d.healthState === 'critical' || d.healthState === 'dead');
        break;
      case 'with-inboxes':
        result = result.filter(d => (d.inboxCount ?? 0) > 0);
        break;
      case 'no-inboxes':
        result = result.filter(d => (d.inboxCount ?? 0) === 0);
        break;
    }

    // Apply sort
    switch (sortBy) {
      case 'name':
        result.sort((a, b) => (a.domain || a.domainName || '').localeCompare(b.domain || b.domainName || ''));
        break;
      case 'inboxes':
        result.sort((a, b) => (b.inboxCount ?? 0) - (a.inboxCount ?? 0));
        break;
      case 'health':
        const healthOrder: Record<string, number> = { healthy: 0, live: 0, warning: 1, critical: 2, dead: 3, unknown: 4 };
        result.sort((a, b) => (healthOrder[a.healthState || 'unknown'] || 4) - (healthOrder[b.healthState || 'unknown'] || 4));
        break;
    }

    return result;
  }, [domains, filter, sortBy]);

  const toggleDomain = (domainId: string) => {
    setExpandedDomains(prev => {
      const next = new Set(prev);
      if (next.has(domainId)) {
        next.delete(domainId);
      } else {
        next.add(domainId);
        // Trigger lazy loading when expanding
        if (onExpandDomain) {
          onExpandDomain(domainId);
        }
      }
      return next;
    });
  };

  const expandAll = () => {
    const domainIds = filteredDomains.map(d => d.id);
    setExpandedDomains(new Set(domainIds));
    // Trigger lazy loading for all domains
    if (onExpandDomain) {
      domainIds.forEach(id => onExpandDomain(id));
    }
  };

  const collapseAll = () => {
    setExpandedDomains(new Set());
  };

  // Summary stats using API's inbox counts
  const totalInboxesFromApi = domains.reduce((sum, d) => sum + (d.inboxCount ?? 0), 0);
  const totalLiveInboxes = domains.reduce((sum, d) => sum + (d.liveInboxCount ?? 0), 0);
  const totalDeadInboxes = domains.reduce((sum, d) => sum + (d.deadInboxCount ?? 0), 0);
  const healthyDomains = domains.filter(d => d.healthState === 'healthy' || d.healthState === 'live').length;
  const warningDomains = domains.filter(d => d.healthState === 'warning' || d.healthState === 'critical').length;
  const deadDomains = domains.filter(d => d.healthState === 'dead').length;
  const domainsWithInboxes = domains.filter(d => (d.inboxCount ?? 0) > 0).length;

  return (
    <div className={cn('space-y-4', className)}>
      {/* Summary Bar */}
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex items-center gap-4 text-sm flex-wrap">
          <span className="font-medium">{domains.length} domains</span>
          <span className="text-muted-foreground">|</span>
          <span>
            {totalInboxesFromApi.toLocaleString()} inboxes
            {totalLiveInboxes > 0 && (
              <span className="text-green-600 ml-1">({totalLiveInboxes.toLocaleString()} live)</span>
            )}
            {totalDeadInboxes > 0 && (
              <span className="text-red-600 ml-1">({totalDeadInboxes.toLocaleString()} dead)</span>
            )}
          </span>
          <span className="text-muted-foreground">|</span>
          {healthyDomains > 0 && (
            <span className="text-green-600">{healthyDomains} healthy</span>
          )}
          {warningDomains > 0 && (
            <span className="text-yellow-600">{warningDomains} warning</span>
          )}
          {deadDomains > 0 && (
            <span className="text-red-600">{deadDomains} dead</span>
          )}
        </div>
      </div>

      {/* Filter & Sort Controls */}
      <div className="flex flex-wrap items-center gap-3 text-sm border-b pb-3">
        <div className="flex items-center gap-2">
          <Filter className="h-4 w-4 text-muted-foreground" />
          <span className="text-muted-foreground">Filter:</span>
          <select
            value={filter}
            onChange={(e) => setFilter(e.target.value as FilterType)}
            className="border rounded px-2 py-1 text-sm bg-background"
          >
            <option value="all">All domains ({domains.length})</option>
            <option value="healthy">Healthy only ({healthyDomains})</option>
            <option value="warning">Warning/Critical ({warningDomains + deadDomains})</option>
            <option value="with-inboxes">With inboxes ({domainsWithInboxes})</option>
            <option value="no-inboxes">No inboxes ({domains.length - domainsWithInboxes})</option>
          </select>
        </div>

        <div className="flex items-center gap-2">
          <SortAsc className="h-4 w-4 text-muted-foreground" />
          <span className="text-muted-foreground">Sort:</span>
          <select
            value={sortBy}
            onChange={(e) => setSortBy(e.target.value as SortType)}
            className="border rounded px-2 py-1 text-sm bg-background"
          >
            <option value="name">Name (A-Z)</option>
            <option value="inboxes">Inbox count</option>
            <option value="health">Health status</option>
          </select>
        </div>

        <div className="flex items-center gap-2 ml-auto">
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

      {/* Showing count */}
      {filter !== 'all' && (
        <div className="text-sm text-muted-foreground">
          Showing {filteredDomains.length} of {domains.length} domains
        </div>
      )}

      {/* Domain List */}
      <div className="space-y-2">
        {filteredDomains.length === 0 ? (
          <div className="text-center py-8 text-muted-foreground">
            No domains match the current filter
          </div>
        ) : (
          filteredDomains.map((domain) => (
            <DomainRow
              key={domain.id}
              domain={domain}
              inboxes={inboxesByDomain.get(domain.id) || []}
              isExpanded={expandedDomains.has(domain.id)}
              isLoading={loadingDomainIds.has(domain.id)}
              onToggle={() => toggleDomain(domain.id)}
            />
          ))
        )}
      </div>
    </div>
  );
}
