'use client';

import { useState, useMemo } from 'react';
import { ChevronRight, ChevronDown, Globe, Mail, AlertCircle, CheckCircle, AlertTriangle, XCircle, Filter, SortAsc, Loader2, Cloud, Zap } from 'lucide-react';
import { formatDistanceToNow } from 'date-fns';
import { Progress } from '@/components/ui/progress';
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
  monitoring: { bg: 'bg-blue-100', text: 'text-blue-700', icon: AlertCircle },
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

  // Domain health details for explanation
  const healthScore = domain.latestHealthScore;
  const blacklistCount = domain.latestBlacklistCount ?? 0;

  // Count inboxes with issues (for display when expanded)
  const warningInboxes = inboxes.filter(i => (i.hardBounces7d ?? 0) > 0 || i.healthState === 'warning').length;
  const criticalInboxes = inboxes.filter(i => (i.hardBounces24h ?? 0) >= 3 || i.healthState === 'critical').length;
  const totalInboxIssues = warningInboxes + criticalInboxes;
  const hasInboxIssues = totalInboxIssues > 0;
  const hasDomainIssues = blacklistCount > 0 || (healthScore !== undefined && healthScore < 80);

  // Show health details panel when expanded and there are issues
  const showHealthDetails = isExpanded && (healthState === 'warning' || healthState === 'critical' || hasDomainIssues || hasInboxIssues);

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
        {/* Provider Icon */}
        {domain.infrastructureType === 'entra' ? (
          <span title="Microsoft Entra"><Cloud className="h-4 w-4 text-blue-500 shrink-0" /></span>
        ) : domain.infrastructureType === 'google' ? (
          <span title="Google Workspace"><Mail className="h-4 w-4 text-red-500 shrink-0" /></span>
        ) : (
          <Globe className="h-4 w-4 text-muted-foreground shrink-0" />
        )}
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
            {totalInboxIssues > 0 && (
              <span className="text-orange-600 ml-1">· {totalInboxIssues} flagged</span>
            )}
          </span>
          <StatusBadge status={healthState} />
        </div>
      </button>

      {/* Domain Health Explanation (when expanded and has issues) */}
      {showHealthDetails && (
        <div className="px-4 py-2 bg-yellow-50 border-t border-yellow-200 text-sm">
          {/* Domain Reputation Issues */}
          {hasDomainIssues && (
            <div className="mb-2">
              <div className="flex items-center gap-2 text-yellow-800">
                <Globe className="h-4 w-4 flex-shrink-0" />
                <span className="font-medium">Domain Reputation:</span>
              </div>
              <ul className="mt-1 ml-6 text-yellow-700 space-y-0.5">
                {blacklistCount > 0 && (
                  <li>
                    {domain.blacklistNames && domain.blacklistNames.length > 0
                      ? `Listed on: ${domain.blacklistNames.slice(0, 5).join(', ')}${domain.blacklistNames.length > 5 ? ` (+${domain.blacklistNames.length - 5} more)` : ''}`
                      : `Listed on ${blacklistCount} blacklist${blacklistCount !== 1 ? 's' : ''}`}
                  </li>
                )}
                {healthScore !== undefined && healthScore < 80 && (
                  <li>Health score: {healthScore}/100</li>
                )}
                {domain.lastCheckedAt && (
                  <li className="text-yellow-600 text-xs">
                    Last checked: {formatDistanceToNow(new Date(domain.lastCheckedAt), { addSuffix: true })}
                  </li>
                )}
              </ul>
            </div>
          )}
          {/* Inbox Delivery Issues */}
          {hasInboxIssues && (
            <div>
              <div className="flex items-center gap-2 text-orange-700">
                <Mail className="h-4 w-4 flex-shrink-0" />
                <span className="font-medium">Inbox Delivery Issues:</span>
              </div>
              <ul className="mt-1 ml-6 text-orange-600 space-y-0.5">
                {criticalInboxes > 0 && (
                  <li className="text-red-600 font-medium">
                    {criticalInboxes} critical (3+ bounces in 24h) — immediate action needed
                  </li>
                )}
                {warningInboxes > 0 && (
                  <li>
                    {warningInboxes} warning (bounces detected) — monitor closely
                  </li>
                )}
              </ul>
            </div>
          )}
          {!hasDomainIssues && !hasInboxIssues && (healthState === 'warning' || healthState === 'critical') && (
            <div className="flex items-center gap-2 text-yellow-700">
              <AlertTriangle className="h-4 w-4 flex-shrink-0" />
              <span>Domain flagged — check Health tab for details</span>
            </div>
          )}
        </div>
      )}

      {/* Inboxes List */}
      {isExpanded && isLoading && (
        <div className="px-4 py-3 text-sm text-muted-foreground border-t flex items-center gap-2">
          <Loader2 className="h-4 w-4 animate-spin" />
          Loading inboxes...
        </div>
      )}

      {isExpanded && !isLoading && inboxes.length > 0 && (
        <div className="border-t divide-y max-h-96 overflow-y-auto">
          {/* Sort inboxes: critical/warning first, then live, then dead */}
          {[...inboxes].sort((a, b) => {
            // Prioritize inboxes with issues
            const aHasIssue = (a.hardBounces7d ?? 0) > 0 || a.healthState === 'warning' || a.healthState === 'critical';
            const bHasIssue = (b.hardBounces7d ?? 0) > 0 || b.healthState === 'warning' || b.healthState === 'critical';
            if (aHasIssue && !bHasIssue) return -1;
            if (!aHasIssue && bHasIssue) return 1;

            const stateA = a.healthState || a.inboxState || 'unknown';
            const stateB = b.healthState || b.inboxState || 'unknown';
            const order: Record<string, number> = { critical: 0, warning: 1, live: 2, healthy: 2, unknown: 3, dead: 4 };
            return (order[stateA] ?? 3) - (order[stateB] ?? 3);
          }).map((inbox) => (
            <InboxRow key={inbox.id} inbox={inbox} />
          ))}
        </div>
      )}

      {isExpanded && !isLoading && inboxes.length === 0 && inboxCount > 0 && (
        <div className="px-4 py-3 text-sm text-muted-foreground border-t">
          Loading {inboxCount} inboxes...
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
  const baseHealthState = inbox.healthState || inbox.inboxState || 'unknown';
  const email = inbox.email || inbox.emailAddress || '';
  const hardBounces24h = inbox.hardBounces24h ?? 0;
  const hardBounces7d = inbox.hardBounces7d ?? 0;
  const hasBounces = hardBounces7d > 0 || hardBounces24h > 0;
  const warmupProgress = inbox.warmupProgress;
  const dailyLimit = inbox.dailySendLimit;
  const bounceRate = inbox.bounceRate7d;
  const isWarming = warmupProgress !== undefined && warmupProgress < 100;

  // Determine display status and severity based on bounce metrics
  let displayStatus = baseHealthState;
  let severity: 'none' | 'warning' | 'critical' = 'none';

  if (hardBounces24h >= 3) {
    displayStatus = 'critical';
    severity = 'critical';
  } else if (hardBounces24h >= 1 || hardBounces7d >= 5) {
    displayStatus = 'warning';
    severity = 'warning';
  } else if (hasBounces) {
    displayStatus = 'warning';
    severity = 'warning';
  }

  // Style based on severity
  const isCritical = severity === 'critical';
  const isWarning = severity === 'warning';
  const needsAttention = isCritical || isWarning;

  return (
    <div className={cn(
      "flex flex-col gap-1 px-4 py-2 pl-10 transition-colors relative",
      isCritical && "bg-red-50 hover:bg-red-100 border-l-4 border-l-red-500",
      isWarning && !isCritical && "bg-orange-50 hover:bg-orange-100 border-l-4 border-l-orange-400",
      !needsAttention && "hover:bg-muted/30 pl-12"
    )}>
      {/* Main row */}
      <div className="flex items-center gap-3">
        <Mail className={cn(
          "h-4 w-4 shrink-0",
          isCritical ? "text-red-600" : isWarning ? "text-orange-500" : "text-muted-foreground"
        )} />
        <span className={cn(
          "text-sm truncate flex-1 font-mono",
          isCritical && "text-red-900 font-medium",
          isWarning && !isCritical && "text-orange-900"
        )}>{email}</span>
        <div className="flex items-center gap-3 shrink-0">
          {hardBounces24h > 0 && (
            <span className={cn(
              "text-xs font-semibold px-2 py-0.5 rounded",
              isCritical ? "bg-red-200 text-red-800" : "bg-orange-200 text-orange-800"
            )}>
              {hardBounces24h} bounce{hardBounces24h !== 1 ? 's' : ''} (24h)
            </span>
          )}
          {hardBounces7d > 0 && hardBounces24h === 0 && (
            <span className="text-xs font-medium px-2 py-0.5 rounded bg-orange-100 text-orange-700">
              {hardBounces7d} bounce{hardBounces7d !== 1 ? 's' : ''} (7d)
            </span>
          )}
          <StatusBadge status={displayStatus} />
        </div>
      </div>
      {/* Metrics row - only show if we have data */}
      {(isWarming || dailyLimit || (bounceRate !== undefined && bounceRate > 0)) && (
        <div className="flex items-center gap-4 ml-7 text-xs text-muted-foreground">
          {/* Warmup progress */}
          {isWarming && (
            <div className="flex items-center gap-1.5">
              <Zap className="h-3 w-3 text-amber-500" />
              <span>Warmup:</span>
              <Progress value={warmupProgress} className="h-1.5 w-12" />
              <span className="text-amber-600">{warmupProgress}%</span>
            </div>
          )}
          {/* Daily limit */}
          {dailyLimit && (
            <span>
              Limit: <span className="font-medium text-foreground">{dailyLimit}/day</span>
            </span>
          )}
          {/* Bounce rate */}
          {bounceRate !== undefined && bounceRate > 0 && (
            <span className={cn(
              bounceRate >= 3 ? "text-red-600" : bounceRate >= 1 ? "text-orange-600" : ""
            )}>
              {bounceRate.toFixed(1)}% bounce rate
            </span>
          )}
        </div>
      )}
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
