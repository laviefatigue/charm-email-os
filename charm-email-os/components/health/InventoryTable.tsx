'use client';

import { useState } from 'react';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { Label } from '@/components/ui/label';
import { cn } from '@/lib/utils';
import {
  MoreHorizontal,
  Skull,
  ArrowRightLeft,
  Clock,
  AlertTriangle,
  Search,
  Filter,
} from 'lucide-react';
import {
  InventoryInbox,
  InventoryPoolStatus,
  InventoryLifecycleStatus,
  POOL_STATUS_CONFIG,
  LIFECYCLE_STATUS_CONFIG,
  formatCooldownTime,
} from '@/lib/types/inventory';
import type { HealthRange } from '@/lib/types/health';
import { HEALTH_RANGE_THRESHOLDS } from '@/lib/types/health';

interface InventoryTableProps {
  inboxes: InventoryInbox[];
  isLoading?: boolean;
  poolStatusFilter?: InventoryPoolStatus | null;
  lifecycleStatusFilter?: InventoryLifecycleStatus | null;
  healthRangeFilter?: HealthRange | null;
  onKillAndReplace?: (inboxId: string, reason: string, autoReplace: boolean) => Promise<void>;
  onClearFilter?: () => void;
  className?: string;
}

export function InventoryTable({
  inboxes,
  isLoading = false,
  poolStatusFilter,
  lifecycleStatusFilter,
  healthRangeFilter,
  onKillAndReplace,
  onClearFilter,
  className,
}: InventoryTableProps) {
  const [searchQuery, setSearchQuery] = useState('');
  const [killDialogOpen, setKillDialogOpen] = useState(false);
  const [selectedInbox, setSelectedInbox] = useState<InventoryInbox | null>(null);
  const [killReason, setKillReason] = useState('');
  const [autoReplace, setAutoReplace] = useState(true);
  const [isKilling, setIsKilling] = useState(false);

  // Filter inboxes based on search and status filters
  const filteredInboxes = inboxes.filter((inbox) => {
    // Search filter
    if (searchQuery) {
      const query = searchQuery.toLowerCase();
      const matchesEmail = inbox.email.toLowerCase().includes(query);
      const matchesDomain = inbox.domainName.toLowerCase().includes(query);
      if (!matchesEmail && !matchesDomain) return false;
    }

    // Pool status filter
    if (poolStatusFilter && inbox.poolStatus !== poolStatusFilter) {
      return false;
    }

    // Lifecycle status filter
    if (lifecycleStatusFilter && inbox.lifecycleStatus !== lifecycleStatusFilter) {
      return false;
    }

    // Health range filter (based on health score)
    if (healthRangeFilter) {
      const healthScore = inbox.healthScore ?? 0;
      const { min, max } = HEALTH_RANGE_THRESHOLDS[healthRangeFilter];
      if (healthScore < min || healthScore >= max) {
        // Special case: critical includes 0-40, and healthy includes 100
        if (healthRangeFilter === 'healthy' && healthScore === 100) {
          // Allow exact 100
        } else if (healthRangeFilter === 'critical' && healthScore >= 0 && healthScore < 40) {
          // Already within range
        } else {
          return false;
        }
      }
    }

    return true;
  });

  const handleKillClick = (inbox: InventoryInbox) => {
    setSelectedInbox(inbox);
    setKillReason('');
    setAutoReplace(true);
    setKillDialogOpen(true);
  };

  const handleKillConfirm = async () => {
    if (!selectedInbox || !onKillAndReplace) return;

    setIsKilling(true);
    try {
      await onKillAndReplace(selectedInbox.inboxId, killReason, autoReplace);
      setKillDialogOpen(false);
    } finally {
      setIsKilling(false);
    }
  };

  const getRowClassName = (inbox: InventoryInbox) => {
    if (inbox.lifecycleStatus === 'dead') {
      return 'bg-muted/50 text-muted-foreground';
    }
    if (inbox.poolStatus === 'warning') {
      return 'bg-yellow-50 dark:bg-yellow-950/20';
    }
    return '';
  };

  return (
    <div className={cn('space-y-4', className)}>
      {/* Search and Filter Bar */}
      <div className="flex items-center gap-4">
        <div className="relative flex-1 max-w-sm">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
          <Input
            placeholder="Search by email or domain..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="pl-9"
          />
        </div>

        {/* Active Filters */}
        {(poolStatusFilter || lifecycleStatusFilter || healthRangeFilter) && (
          <div className="flex items-center gap-2">
            <Filter className="h-4 w-4 text-muted-foreground" />
            {poolStatusFilter && (
              <Badge variant="secondary" className="gap-1">
                Pool: {POOL_STATUS_CONFIG[poolStatusFilter].label}
              </Badge>
            )}
            {lifecycleStatusFilter && (
              <Badge variant="secondary" className="gap-1">
                Lifecycle: {LIFECYCLE_STATUS_CONFIG[lifecycleStatusFilter].label}
              </Badge>
            )}
            {healthRangeFilter && (
              <Badge variant="secondary" className="gap-1">
                Health: {HEALTH_RANGE_THRESHOLDS[healthRangeFilter].label}
              </Badge>
            )}
            <Button variant="ghost" size="sm" onClick={onClearFilter}>
              Clear
            </Button>
          </div>
        )}

        <div className="text-sm text-muted-foreground">
          Showing {filteredInboxes.length} of {inboxes.length}
        </div>
      </div>

      {/* Table */}
      <div className="rounded-md border">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead className="w-[300px]">Email</TableHead>
              <TableHead>Domain</TableHead>
              <TableHead>Pool Status</TableHead>
              <TableHead>Lifecycle</TableHead>
              <TableHead>Age</TableHead>
              <TableHead>Bounces (24h/7d)</TableHead>
              <TableHead>Campaigns</TableHead>
              <TableHead className="w-[50px]"></TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {isLoading ? (
              <TableRow>
                <TableCell colSpan={8} className="h-24 text-center">
                  Loading inventory...
                </TableCell>
              </TableRow>
            ) : filteredInboxes.length === 0 ? (
              <TableRow>
                <TableCell colSpan={8} className="h-24 text-center">
                  No inboxes found
                </TableCell>
              </TableRow>
            ) : (
              filteredInboxes.map((inbox) => (
                <TableRow key={inbox.inboxId} className={getRowClassName(inbox)}>
                  <TableCell className="font-medium">
                    <div className="flex flex-col">
                      <span>{inbox.email}</span>
                      {inbox.warningReason && (
                        <span className="text-xs text-yellow-600 flex items-center gap-1 mt-0.5">
                          <AlertTriangle className="h-3 w-3" />
                          {inbox.warningReason}
                        </span>
                      )}
                    </div>
                  </TableCell>
                  <TableCell className="text-muted-foreground">{inbox.domainName}</TableCell>
                  <TableCell>
                    {inbox.poolStatus ? (
                      <Badge
                        variant="outline"
                        className={cn(
                          POOL_STATUS_CONFIG[inbox.poolStatus].text,
                          POOL_STATUS_CONFIG[inbox.poolStatus].border,
                          'border'
                        )}
                      >
                        {POOL_STATUS_CONFIG[inbox.poolStatus].label}
                      </Badge>
                    ) : (
                      <span className="text-muted-foreground">-</span>
                    )}
                    {inbox.cooldownEndsAt && (
                      <div className="text-xs text-muted-foreground mt-1 flex items-center gap-1">
                        <Clock className="h-3 w-3" />
                        {formatCooldownTime(inbox.cooldownEndsAt)}
                      </div>
                    )}
                  </TableCell>
                  <TableCell>
                    <Badge
                      variant="secondary"
                      className={cn(
                        LIFECYCLE_STATUS_CONFIG[inbox.lifecycleStatus].bg,
                        LIFECYCLE_STATUS_CONFIG[inbox.lifecycleStatus].text
                      )}
                    >
                      {LIFECYCLE_STATUS_CONFIG[inbox.lifecycleStatus].label}
                    </Badge>
                  </TableCell>
                  <TableCell className="text-muted-foreground">
                    {inbox.ageDays}d
                  </TableCell>
                  <TableCell>
                    <div className="flex items-center gap-1">
                      <span
                        className={cn(
                          'font-medium',
                          inbox.hardBounces24h > 0 ? 'text-red-600' : ''
                        )}
                      >
                        {inbox.hardBounces24h}
                      </span>
                      <span className="text-muted-foreground">/</span>
                      <span
                        className={cn(
                          'font-medium',
                          inbox.hardBounces7d >= 3 ? 'text-red-600' : ''
                        )}
                      >
                        {inbox.hardBounces7d}
                      </span>
                    </div>
                  </TableCell>
                  <TableCell>
                    {inbox.associatedCampaigns.length > 0 ? (
                      <Badge variant="outline" className="font-normal">
                        {inbox.associatedCampaigns.length} campaign
                        {inbox.associatedCampaigns.length !== 1 ? 's' : ''}
                      </Badge>
                    ) : (
                      <span className="text-muted-foreground">-</span>
                    )}
                  </TableCell>
                  <TableCell>
                    <DropdownMenu>
                      <DropdownMenuTrigger asChild>
                        <Button
                          variant="ghost"
                          size="icon"
                          className="h-8 w-8"
                          disabled={inbox.lifecycleStatus === 'dead'}
                        >
                          <MoreHorizontal className="h-4 w-4" />
                        </Button>
                      </DropdownMenuTrigger>
                      <DropdownMenuContent align="end">
                        <DropdownMenuItem
                          onClick={() => handleKillClick(inbox)}
                          className="text-red-600"
                        >
                          <Skull className="mr-2 h-4 w-4" />
                          Kill & Replace
                        </DropdownMenuItem>
                        <DropdownMenuSeparator />
                        <DropdownMenuItem disabled>
                          <ArrowRightLeft className="mr-2 h-4 w-4" />
                          Move to Reserve
                        </DropdownMenuItem>
                      </DropdownMenuContent>
                    </DropdownMenu>
                  </TableCell>
                </TableRow>
              ))
            )}
          </TableBody>
        </Table>
      </div>

      {/* Kill Confirmation Dialog */}
      <AlertDialog open={killDialogOpen} onOpenChange={setKillDialogOpen}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle className="flex items-center gap-2 text-red-600">
              <Skull className="h-5 w-5" />
              Kill Inbox
            </AlertDialogTitle>
            <AlertDialogDescription>
              This will mark the inbox as dead and remove it from all campaigns.
            </AlertDialogDescription>
          </AlertDialogHeader>

          {selectedInbox && (
            <div className="space-y-4 py-4">
              <div className="p-3 bg-muted rounded-lg">
                <div className="font-medium">{selectedInbox.email}</div>
                <div className="text-sm text-muted-foreground">
                  {selectedInbox.associatedCampaigns.length} associated campaign
                  {selectedInbox.associatedCampaigns.length !== 1 ? 's' : ''}
                </div>
              </div>

              <div className="space-y-2">
                <Label htmlFor="kill-reason">Reason for killing</Label>
                <Textarea
                  id="kill-reason"
                  placeholder="e.g., High bounce rate, blacklisted, etc."
                  value={killReason}
                  onChange={(e) => setKillReason(e.target.value)}
                />
              </div>

              <div className="flex items-center gap-2">
                <input
                  type="checkbox"
                  id="auto-replace"
                  checked={autoReplace}
                  onChange={(e) => setAutoReplace(e.target.checked)}
                  className="rounded"
                />
                <Label htmlFor="auto-replace" className="font-normal">
                  Automatically replace with a reserve inbox in affected campaigns
                </Label>
              </div>
            </div>
          )}

          <AlertDialogFooter>
            <AlertDialogCancel disabled={isKilling}>Cancel</AlertDialogCancel>
            <AlertDialogAction
              onClick={handleKillConfirm}
              disabled={isKilling || !killReason.trim()}
              className="bg-red-600 hover:bg-red-700"
            >
              {isKilling ? 'Killing...' : 'Kill Inbox'}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
