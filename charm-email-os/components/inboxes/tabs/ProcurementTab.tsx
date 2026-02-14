'use client';

import { useState, useCallback } from 'react';
import { Globe, Mail, Sparkles, Loader2, Package } from 'lucide-react';
import { toast } from 'sonner';
import { Button } from '@/components/ui/button';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { Accordion, AccordionItem, AccordionTrigger, AccordionContent } from '@/components/ui/accordion';
import { EmptyState } from '@/components/shared';
import { DomainCandidatesTable, DomainsNeedingSetupTable, InboxProvisionModal } from '@/components/purchasing';
import { domainSourcingApi, type CanGenerateResponse } from '@/lib/api';
import type { Domain, SubscriptionWithUsage } from '@/lib/types';

interface ProcurementTabProps {
  clientId: string;
  clientName: string;
  subscription: SubscriptionWithUsage | null;
  canGenerateInfo: CanGenerateResponse | null;
  candidateDomains: Domain[];
  purchasedDomains: Domain[];
  pendingCount: number;
  approvedCount: number;
  onRefreshDomains: () => void;
  onRefreshInboxes: () => void;
}

export function ProcurementTab({
  clientId,
  clientName,
  subscription,
  canGenerateInfo,
  candidateDomains,
  purchasedDomains,
  pendingCount,
  approvedCount,
  onRefreshDomains,
  onRefreshInboxes,
}: ProcurementTabProps) {
  // Local state for this tab
  const [isGenerating, setIsGenerating] = useState(false);
  const [selectedDomainsForSetup, setSelectedDomainsForSetup] = useState<string[]>([]);
  const [hasAgeOverride, setHasAgeOverride] = useState(false);
  const [showProvisionModal, setShowProvisionModal] = useState(false);

  // Direct inline domain generation - queues job for containerized Claude Code worker
  const handleGenerateDomainsInline = useCallback(async () => {
    if (!canGenerateInfo?.canGenerate) {
      toast.error(canGenerateInfo?.message || 'Cannot generate domains');
      return;
    }
    setIsGenerating(true);
    try {
      // Create a job for the Claude Code domain worker (fill_package=true by default)
      const job = await domainSourcingApi.createGenerationJob(clientId, 10, true);

      // Handle skipped status (package capacity already reached)
      if (job.status === 'skipped' || !job.jobId) {
        toast.info(job.message || 'Package capacity reached - no domains needed');
        setIsGenerating(false);
        return;
      }

      toast.success(`Generating ${job.count} domains to fill package capacity...`);

      // At this point, jobId is guaranteed non-null (we returned early if skipped)
      const jobId = job.jobId!;

      // Poll for job completion and refresh domains
      const pollInterval = setInterval(async () => {
        try {
          const status = await domainSourcingApi.getJobStatus(jobId);
          if (status.status === 'completed') {
            clearInterval(pollInterval);
            await onRefreshDomains();
            // Auto-trigger bulk price check for newly generated domains
            try {
              toast.success('Domain generation complete! Checking prices...');
              await domainSourcingApi.checkPricesBulk({ clientId });
              await onRefreshDomains(); // Refresh with prices
              toast.success('Prices checked across registrars.');
            } catch {
              toast.success('Domain generation complete! Price check can be done manually.');
            }
            setIsGenerating(false);
          } else if (status.status === 'failed') {
            clearInterval(pollInterval);
            toast.error(status.errorMessage || 'Domain generation failed');
            setIsGenerating(false);
          }
        } catch {
          // Ignore polling errors
        }
      }, 3000); // Poll every 3 seconds

      // Timeout after 2 minutes
      setTimeout(() => {
        clearInterval(pollInterval);
        setIsGenerating(false);
        onRefreshDomains();
      }, 120000);
    } catch (error) {
      console.error('Failed to queue domain generation:', error);
      toast.error('Failed to queue domain generation');
      setIsGenerating(false);
    }
  }, [canGenerateInfo, clientId, onRefreshDomains]);

  // Handle setup click from DomainsNeedingSetupTable
  const handleSetupClick = useCallback((selectedIds: string[], override: boolean) => {
    setSelectedDomainsForSetup(selectedIds);
    setHasAgeOverride(override);
    setShowProvisionModal(true);
  }, []);

  // Handle provision modal close
  const handleProvisionModalClose = useCallback((open: boolean) => {
    setShowProvisionModal(open);
    if (!open) {
      setSelectedDomainsForSetup([]);
      setHasAgeOverride(false);
    }
  }, []);

  // Handle successful provisioning
  const handleProvisionSuccess = useCallback(() => {
    onRefreshDomains();
    onRefreshInboxes();
    setSelectedDomainsForSetup([]);
    setHasAgeOverride(false);
  }, [onRefreshDomains, onRefreshInboxes]);

  return (
    <div className="space-y-6">
      {/* Contextual header */}
      {subscription && subscription.domainsRemaining > 0 && (
        <Alert>
          <Package className="h-4 w-4" />
          <AlertDescription>
            Your <strong>{subscription.packageTemplateName || 'Custom'}</strong> package needs{' '}
            <strong>{subscription.domainsRemaining} more domains</strong> to reach full capacity.
          </AlertDescription>
        </Alert>
      )}

      <Accordion type="multiple" defaultValue={['domains', 'setup-inboxes']} className="space-y-4">
        {/* Domain Candidates — Generate + Review/Price/Purchase */}
        <AccordionItem value="domains" className="border rounded-lg px-4">
          <AccordionTrigger className="hover:no-underline py-4">
            <div className="flex items-center gap-3">
              <Globe className="h-4 w-4 text-muted-foreground" />
              <span className="text-base font-semibold">Domain Candidates</span>
              {candidateDomains.length > 0 && (
                <div className="flex items-center gap-2">
                  {pendingCount > 0 && (
                    <span className="px-2 py-0.5 bg-yellow-50 text-yellow-700 rounded-full text-xs">
                      {pendingCount} pending
                    </span>
                  )}
                  {approvedCount > 0 && (
                    <span className="px-2 py-0.5 bg-blue-50 text-blue-700 rounded-full text-xs">
                      {approvedCount} approved
                    </span>
                  )}
                </div>
              )}
            </div>
          </AccordionTrigger>
          <AccordionContent>
            <div className="flex items-center gap-3 mb-4">
              <Button
                size="sm"
                disabled={!canGenerateInfo?.canGenerate || isGenerating}
                onClick={handleGenerateDomainsInline}
              >
                {isGenerating ? (
                  <Loader2 className="h-4 w-4 mr-1 animate-spin" />
                ) : (
                  <Sparkles className="h-4 w-4 mr-1" />
                )}
                {isGenerating ? 'Generating...' : 'Generate Domains'}
              </Button>
              {!canGenerateInfo?.canGenerate && canGenerateInfo?.message && (
                <p className="text-xs text-muted-foreground">{canGenerateInfo.message}</p>
              )}
            </div>
            {candidateDomains.length > 0 ? (
              <DomainCandidatesTable
                domains={candidateDomains}
                clientId={clientId}
                onDomainUpdate={onRefreshDomains}
              />
            ) : (
              <EmptyState
                icon={Globe}
                title="No domain candidates yet"
                description="Click 'Generate Domains' above to create AI-powered domain suggestions."
              />
            )}
          </AccordionContent>
        </AccordionItem>

        {/* Setup Inboxes */}
        <AccordionItem value="setup-inboxes" className="border rounded-lg px-4">
          <AccordionTrigger className="hover:no-underline py-4">
            <div className="flex items-center justify-between w-full pr-2">
              <div className="flex items-center gap-3">
                <Mail className="h-4 w-4 text-muted-foreground" />
                <span className="text-base font-semibold">Setup Inboxes</span>
                {purchasedDomains.length > 0 && (
                  <span className="px-2 py-0.5 bg-orange-50 text-orange-700 rounded-full text-xs">
                    {purchasedDomains.length} ready
                  </span>
                )}
              </div>
            </div>
          </AccordionTrigger>
          <AccordionContent>
            {purchasedDomains.length > 0 ? (
              <DomainsNeedingSetupTable
                domains={purchasedDomains}
                onSetupClick={handleSetupClick}
                onDomainsChange={onRefreshDomains}
              />
            ) : (
              <EmptyState
                icon={Mail}
                title="No domains awaiting inbox setup"
                description="Domains will appear here once purchased above."
              />
            )}
          </AccordionContent>
        </AccordionItem>
      </Accordion>

      {/* Inbox Provision Modal */}
      <InboxProvisionModal
        open={showProvisionModal}
        onOpenChange={handleProvisionModalClose}
        clientId={clientId}
        clientName={clientName}
        selectedDomainIds={selectedDomainsForSetup}
        hasAgeOverride={hasAgeOverride}
        onSuccess={handleProvisionSuccess}
      />
    </div>
  );
}
