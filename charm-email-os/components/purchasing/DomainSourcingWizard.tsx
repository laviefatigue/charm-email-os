'use client';

import { useState, useEffect, useCallback } from 'react';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { Checkbox } from '@/components/ui/checkbox';
import {
  Search,
  ShoppingCart,
  ArrowRight,
  Loader2,
  Check,
  X,
  DollarSign,
  Star,
  AlertTriangle,
  Globe,
  ThumbsUp,
  ThumbsDown,
  RefreshCw,
  Sparkles,
} from 'lucide-react';
import { toast } from 'sonner';
import { cn } from '@/lib/utils';
import {
  domainSourcingApi,
  type DomainCandidate,
  type PendingCandidatesResponse,
} from '@/lib/api';

// Types
interface RegistrarResult {
  registrar: string;
  isAvailable: boolean;
  registrationPrice: number;
  renewalPrice: number;
  isPromotional: boolean;
  regularPrice?: number;
  whoisPrivacyIncluded: boolean;
  error?: string;
}

interface SearchResult {
  domainName: string;
  baseName: string;
  tld: string;
  legitimacyScore: number;
  isAvailable: boolean;
  bestPrice?: number;
  bestRegistrar?: string;
  isDeal: boolean;
  valueScore: number;
  registrarResults: RegistrarResult[];
  selected?: boolean;
}

interface DomainSourcingWizardProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  clientId: string;
  clientName: string;
  onComplete?: (purchasedDomains: string[]) => void;
}

type WizardStep = 'review' | 'search' | 'purchase';

const WIZARD_STEPS: { key: WizardStep; label: string; description: string }[] = [
  { key: 'review', label: 'Review Candidates', description: 'Approve or deny domains' },
  { key: 'search', label: 'Search Prices', description: 'Find best registrar prices' },
  { key: 'purchase', label: 'Purchase', description: 'Complete purchase' },
];

const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://ccssgc4gowsog04wck400o0w.31.97.142.123.sslip.io';

export function DomainSourcingWizard({
  open,
  onOpenChange,
  clientId,
  clientName,
  onComplete,
}: DomainSourcingWizardProps) {
  // Wizard state
  const [currentStep, setCurrentStep] = useState<WizardStep>('review');
  const [isLoading, setIsLoading] = useState(false);

  // Candidate state
  const [pendingCandidates, setPendingCandidates] = useState<DomainCandidate[]>([]);
  const [approvedCandidates, setApprovedCandidates] = useState<DomainCandidate[]>([]);
  const [totalPending, setTotalPending] = useState(0);

  // Generation job state
  const [isGenerating, setIsGenerating] = useState(false);
  const [generationJobId, setGenerationJobId] = useState<string | null>(null);

  // Search results
  const [searchResults, setSearchResults] = useState<SearchResult[]>([]);
  const [targetPrice, setTargetPrice] = useState(8);
  const [maxPrice, setMaxPrice] = useState(15);

  // Get current step index
  const currentStepIndex = WIZARD_STEPS.findIndex((s) => s.key === currentStep);

  // Load pending candidates on open
  useEffect(() => {
    if (open && currentStep === 'review') {
      loadPendingCandidates();
    }
  }, [open]);

  // Load pending candidates
  const loadPendingCandidates = async () => {
    setIsLoading(true);
    try {
      const response = await domainSourcingApi.getPendingCandidates(clientId, 10);
      setPendingCandidates(response.candidates);
      setTotalPending(response.totalPending);
    } catch (error: any) {
      toast.error(error.message || 'Failed to load domain candidates');
    } finally {
      setIsLoading(false);
    }
  };

  // Load approved candidates
  const loadApprovedCandidates = async () => {
    try {
      const response = await domainSourcingApi.getApprovedDomains(clientId);
      setApprovedCandidates(response.approvedDomains);
    } catch (error: any) {
      console.error('Failed to load approved domains:', error);
    }
  };

  // Generate domains using Claude Code worker
  const handleGenerateDomains = async () => {
    setIsGenerating(true);
    try {
      // Create a generation job (fill_package=true by default)
      const job = await domainSourcingApi.createGenerationJob(clientId, 10, true);

      // Handle skipped status (package capacity already reached)
      if (job.status === 'skipped' || !job.jobId) {
        toast.info(job.message || 'Package capacity reached - no domains needed');
        setIsGenerating(false);
        return;
      }

      // At this point, jobId is guaranteed non-null
      const jobId = job.jobId;
      setGenerationJobId(jobId);
      toast.success(`Generating ${job.count} domains to fill package capacity...`);

      // Poll for job completion
      const pollInterval = setInterval(async () => {
        try {
          const status = await domainSourcingApi.getJobStatus(jobId);
          if (status.status === 'completed') {
            clearInterval(pollInterval);
            setIsGenerating(false);
            setGenerationJobId(null);
            toast.success('Domains generated successfully');
            loadPendingCandidates(); // Refresh the list
          } else if (status.status === 'failed') {
            clearInterval(pollInterval);
            setIsGenerating(false);
            setGenerationJobId(null);
            toast.error(status.errorMessage || 'Generation failed');
          }
        } catch (err) {
          console.error('Error polling job status:', err);
        }
      }, 3000); // Poll every 3 seconds

      // Timeout after 2 minutes
      setTimeout(() => {
        clearInterval(pollInterval);
        if (isGenerating) {
          setIsGenerating(false);
          setGenerationJobId(null);
          toast.error('Generation timed out. The job may still complete in the background.');
          loadPendingCandidates(); // Try to refresh anyway
        }
      }, 120000);
    } catch (error: any) {
      setIsGenerating(false);
      toast.error(error.message || 'Failed to start domain generation');
    }
  };

  // Approve a domain
  const handleApprove = async (domainId: string) => {
    try {
      const result = await domainSourcingApi.approveDomain(domainId);
      toast.success(`Approved: ${result.domainName}`);

      // Move from pending to approved
      const approved = pendingCandidates.find((c) => c.id === domainId);
      if (approved) {
        setApprovedCandidates((prev) => [...prev, { ...approved, approvalStatus: 'approved' }]);
        setPendingCandidates((prev) => prev.filter((c) => c.id !== domainId));
        setTotalPending((prev) => Math.max(0, prev - 1));
      }

      // Load a new pending candidate to replace
      loadPendingCandidates();
    } catch (error: any) {
      toast.error(error.message || 'Failed to approve domain');
    }
  };

  // Deny a domain
  const handleDeny = async (domainId: string) => {
    try {
      const result = await domainSourcingApi.denyDomain(domainId);
      toast.success(`Denied: ${result.domainName}`);

      // Remove from pending
      setPendingCandidates((prev) => prev.filter((c) => c.id !== domainId));
      setTotalPending((prev) => Math.max(0, prev - 1));

      // Load a new pending candidate to replace
      loadPendingCandidates();
    } catch (error: any) {
      toast.error(error.message || 'Failed to deny domain');
    }
  };

  // Navigation
  const goBack = () => {
    const prevIndex = currentStepIndex - 1;
    if (prevIndex >= 0) {
      setCurrentStep(WIZARD_STEPS[prevIndex].key);
    }
  };

  const goNext = () => {
    const nextIndex = currentStepIndex + 1;
    if (nextIndex < WIZARD_STEPS.length) {
      setCurrentStep(WIZARD_STEPS[nextIndex].key);
    }
  };

  // Proceed to search step
  const handleProceedToSearch = () => {
    if (approvedCandidates.length === 0) {
      toast.error('Approve at least one domain to search prices');
      return;
    }
    setCurrentStep('search');
  };

  // Search registrars
  const handleSearch = useCallback(async () => {
    if (approvedCandidates.length === 0) {
      toast.error('No approved domains to search');
      return;
    }

    setIsLoading(true);
    try {
      const response = await fetch(`${API_BASE}/api/domain-sourcing/search`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          candidates: approvedCandidates.map((c) => ({
            id: c.id,
            domain_name: c.domainName,
            base_name: c.baseName,
            tld: c.tld,
            rationale: c.rationale,
            legitimacy_score: c.legitimacyScore,
          })),
          target_price: targetPrice,
          max_price: maxPrice,
          include_variations: false,
        }),
      });

      if (!response.ok) {
        const error = await response.json();
        throw new Error(error.detail || 'Failed to search registrars');
      }

      const data = await response.json();
      setSearchResults(
        data.results.map((r: any) => ({
          domainName: r.domain_name,
          baseName: r.base_name,
          tld: r.tld,
          legitimacyScore: r.legitimacy_score,
          isAvailable: r.is_available,
          bestPrice: r.best_price,
          bestRegistrar: r.best_registrar,
          isDeal: r.is_deal,
          valueScore: r.value_score,
          registrarResults: r.registrar_results.map((rr: any) => ({
            registrar: rr.registrar,
            isAvailable: rr.is_available,
            registrationPrice: rr.registration_price,
            renewalPrice: rr.renewal_price,
            isPromotional: rr.is_promotional,
            regularPrice: rr.regular_price,
            whoisPrivacyIncluded: rr.whois_privacy_included,
            error: rr.error,
          })),
          selected: r.is_available && r.best_price && r.best_price <= maxPrice,
        }))
      );
      toast.success(`Found ${data.available_count} available domains`);
      goNext();
    } catch (error: any) {
      toast.error(error.message || 'Failed to search registrars');
    } finally {
      setIsLoading(false);
    }
  }, [approvedCandidates, targetPrice, maxPrice]);

  // Purchase domains
  const handlePurchase = useCallback(async () => {
    const selectedDomains = searchResults.filter((r) => r.selected && r.isAvailable);
    if (selectedDomains.length === 0) {
      toast.error('Select at least one domain to purchase');
      return;
    }

    setIsLoading(true);
    try {
      const response = await fetch(`${API_BASE}/api/domain-sourcing/purchase`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          client_id: clientId,
          approved_domains: selectedDomains.map((d) => ({
            domain_name: d.domainName,
            registrar: d.bestRegistrar,
            price: d.bestPrice,
          })),
          nameservers: [],
        }),
      });

      if (!response.ok) {
        const error = await response.json();
        throw new Error(error.detail || 'Failed to purchase domains');
      }

      const data = await response.json();

      if (data.successful_count > 0) {
        toast.success(`Successfully purchased ${data.successful_count} domain(s)`);
        const purchasedDomains = data.results
          .filter((r: any) => r.success)
          .map((r: any) => r.domain_name);
        onComplete?.(purchasedDomains);
        onOpenChange(false);
      } else {
        toast.error('No domains were purchased');
      }
    } catch (error: any) {
      toast.error(error.message || 'Failed to purchase domains');
    } finally {
      setIsLoading(false);
    }
  }, [clientId, searchResults, onComplete, onOpenChange]);

  // Toggle search result selection
  const toggleSearchResult = (domainName: string) => {
    setSearchResults((prev) =>
      prev.map((r) =>
        r.domainName === domainName ? { ...r, selected: !r.selected } : r
      )
    );
  };

  // Calculate totals
  const selectedSearchResultsCount = searchResults.filter((r) => r.selected && r.isAvailable).length;
  const totalPurchasePrice = searchResults
    .filter((r) => r.selected && r.isAvailable && r.bestPrice)
    .reduce((sum, r) => sum + (r.bestPrice || 0), 0);

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-4xl max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Globe className="h-5 w-5" />
            Purchase Domains for {clientName}
          </DialogTitle>
          <DialogDescription>
            Review AI-generated domain suggestions, then search prices and purchase
          </DialogDescription>
        </DialogHeader>

        {/* Step Indicator */}
        <div className="flex items-center justify-between mb-6">
          {WIZARD_STEPS.map((step, index) => (
            <div key={step.key} className="flex items-center">
              <div
                className={cn(
                  'flex items-center justify-center w-8 h-8 rounded-full text-sm font-medium',
                  index < currentStepIndex
                    ? 'bg-primary text-primary-foreground'
                    : index === currentStepIndex
                    ? 'bg-primary text-primary-foreground'
                    : 'bg-muted text-muted-foreground'
                )}
              >
                {index < currentStepIndex ? (
                  <Check className="h-4 w-4" />
                ) : (
                  index + 1
                )}
              </div>
              <div className="ml-2 hidden sm:block">
                <p className="text-sm font-medium">{step.label}</p>
                <p className="text-xs text-muted-foreground">{step.description}</p>
              </div>
              {index < WIZARD_STEPS.length - 1 && (
                <div
                  className={cn(
                    'w-12 h-0.5 mx-2',
                    index < currentStepIndex ? 'bg-primary' : 'bg-muted'
                  )}
                />
              )}
            </div>
          ))}
        </div>

        {/* Step Content */}
        <div className="min-h-[400px]">
          {/* Step 1: Review Candidates */}
          {currentStep === 'review' && (
            <div className="space-y-4">
              {/* Header with stats */}
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-sm text-muted-foreground">
                    Review domain suggestions for {clientName}
                  </p>
                  <div className="flex items-center gap-4 mt-1">
                    <Badge variant="outline">
                      {pendingCandidates.length} pending
                    </Badge>
                    <Badge variant="default" className="bg-green-600">
                      {approvedCandidates.length} approved
                    </Badge>
                    {isGenerating && (
                      <Badge variant="secondary" className="animate-pulse">
                        <Loader2 className="h-3 w-3 mr-1 animate-spin" />
                        Generating...
                      </Badge>
                    )}
                  </div>
                </div>
                <div className="flex items-center gap-2">
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={handleGenerateDomains}
                    disabled={isLoading || isGenerating}
                  >
                    {isGenerating ? (
                      <Loader2 className="h-4 w-4 animate-spin" />
                    ) : (
                      <>
                        <Sparkles className="h-4 w-4 mr-2" />
                        Generate More
                      </>
                    )}
                  </Button>
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={loadPendingCandidates}
                    disabled={isLoading || isGenerating}
                  >
                    {isLoading ? (
                      <Loader2 className="h-4 w-4 animate-spin" />
                    ) : (
                      <>
                        <RefreshCw className="h-4 w-4 mr-2" />
                        Refresh
                      </>
                    )}
                  </Button>
                </div>
              </div>

              {/* Loading state */}
              {isLoading && pendingCandidates.length === 0 && (
                <div className="flex flex-col items-center justify-center py-12">
                  <Loader2 className="h-12 w-12 text-muted-foreground mb-4 animate-spin" />
                  <p className="text-lg font-medium">Loading domain suggestions...</p>
                  <p className="text-sm text-muted-foreground">
                    Generating AI-powered domain candidates
                  </p>
                </div>
              )}

              {/* Pending candidates */}
              {!isLoading && pendingCandidates.length === 0 && approvedCandidates.length === 0 && (
                <div className="flex flex-col items-center justify-center py-12">
                  <Sparkles className="h-12 w-12 text-muted-foreground mb-4" />
                  <p className="text-lg font-medium">No pending candidates</p>
                  <p className="text-sm text-muted-foreground mb-4">
                    {isGenerating
                      ? 'Claude Code is generating domain suggestions...'
                      : 'Click below to generate new domain suggestions using AI'}
                  </p>
                  <Button onClick={handleGenerateDomains} disabled={isGenerating}>
                    {isGenerating ? (
                      <>
                        <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                        Generating...
                      </>
                    ) : (
                      <>
                        <Sparkles className="h-4 w-4 mr-2" />
                        Generate Domains
                      </>
                    )}
                  </Button>
                </div>
              )}

              {/* Candidate cards */}
              {pendingCandidates.length > 0 && (
                <div className="space-y-3">
                  <p className="text-sm font-medium">Pending Review ({pendingCandidates.length})</p>
                  <div className="grid grid-cols-1 gap-3">
                    {pendingCandidates.map((candidate) => (
                      <Card key={candidate.id} className="transition-all hover:shadow-md">
                        <CardContent className="p-4">
                          <div className="flex items-center justify-between">
                            <div className="flex-1">
                              <div className="flex items-center gap-3">
                                <span className="font-mono font-medium text-lg">
                                  {candidate.domainName}
                                </span>
                                <Badge variant="outline">
                                  <Star className="h-3 w-3 mr-1" />
                                  {Math.round(candidate.legitimacyScore * 100)}%
                                </Badge>
                              </div>
                              {candidate.rationale && (
                                <p className="text-sm text-muted-foreground mt-1">
                                  {candidate.rationale}
                                </p>
                              )}
                            </div>
                            <div className="flex items-center gap-2 ml-4">
                              <Button
                                size="sm"
                                variant="outline"
                                className="text-red-600 hover:text-red-700 hover:bg-red-50"
                                onClick={() => handleDeny(candidate.id)}
                              >
                                <ThumbsDown className="h-4 w-4 mr-1" />
                                Deny
                              </Button>
                              <Button
                                size="sm"
                                className="bg-green-600 hover:bg-green-700"
                                onClick={() => handleApprove(candidate.id)}
                              >
                                <ThumbsUp className="h-4 w-4 mr-1" />
                                Approve
                              </Button>
                            </div>
                          </div>
                        </CardContent>
                      </Card>
                    ))}
                  </div>
                </div>
              )}

              {/* Approved candidates */}
              {approvedCandidates.length > 0 && (
                <div className="space-y-3 mt-6">
                  <p className="text-sm font-medium text-green-700">
                    Approved ({approvedCandidates.length})
                  </p>
                  <div className="grid grid-cols-2 md:grid-cols-3 gap-2">
                    {approvedCandidates.map((candidate) => (
                      <Badge
                        key={candidate.id}
                        variant="secondary"
                        className="py-2 px-3 justify-between"
                      >
                        <span className="font-mono text-sm">{candidate.domainName}</span>
                        <Check className="h-3 w-3 text-green-600 ml-2" />
                      </Badge>
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}

          {/* Step 2: Search Prices */}
          {currentStep === 'search' && (
            <div className="space-y-4">
              {searchResults.length === 0 ? (
                <div className="space-y-4">
                  <Card>
                    <CardHeader className="pb-2">
                      <CardTitle className="text-base">Search Settings</CardTitle>
                      <CardDescription>
                        Searching prices for {approvedCandidates.length} approved domains
                      </CardDescription>
                    </CardHeader>
                    <CardContent>
                      <div className="grid grid-cols-2 gap-4">
                        <div className="space-y-2">
                          <Label>Target Price ($)</Label>
                          <Input
                            type="number"
                            value={targetPrice}
                            onChange={(e) => setTargetPrice(Number(e.target.value))}
                          />
                          <p className="text-xs text-muted-foreground">
                            Domains under this price are highlighted as deals
                          </p>
                        </div>
                        <div className="space-y-2">
                          <Label>Maximum Price ($)</Label>
                          <Input
                            type="number"
                            value={maxPrice}
                            onChange={(e) => setMaxPrice(Number(e.target.value))}
                          />
                          <p className="text-xs text-muted-foreground">
                            Auto-select domains under this price
                          </p>
                        </div>
                      </div>
                    </CardContent>
                  </Card>

                  <div className="flex flex-col items-center justify-center py-8">
                    <Search className="h-12 w-12 text-muted-foreground mb-4" />
                    <p className="text-lg font-medium">Ready to Search</p>
                    <p className="text-sm text-muted-foreground mb-4">
                      Search {approvedCandidates.length} domains across Porkbun & Dynadot
                    </p>
                    <Button onClick={handleSearch} disabled={isLoading}>
                      {isLoading ? (
                        <>
                          <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                          Searching...
                        </>
                      ) : (
                        <>
                          <Search className="h-4 w-4 mr-2" />
                          Search Registrars
                        </>
                      )}
                    </Button>
                  </div>
                </div>
              ) : (
                <>
                  <div className="flex items-center justify-between">
                    <div>
                      <p className="text-sm">
                        <span className="font-medium">{searchResults.filter((r) => r.isAvailable).length}</span> available
                        {' / '}
                        <span className="text-green-600 font-medium">{searchResults.filter((r) => r.isDeal).length}</span> deals
                      </p>
                      <p className="text-xs text-muted-foreground">
                        {selectedSearchResultsCount} selected - Total: ${totalPurchasePrice.toFixed(2)}
                      </p>
                    </div>
                    <Button variant="outline" size="sm" onClick={handleSearch} disabled={isLoading}>
                      {isLoading ? (
                        <Loader2 className="h-4 w-4 animate-spin" />
                      ) : (
                        <>
                          <RefreshCw className="h-4 w-4 mr-2" />
                          Refresh
                        </>
                      )}
                    </Button>
                  </div>

                  <div className="space-y-2">
                    {searchResults
                      .sort((a, b) => (b.valueScore || 0) - (a.valueScore || 0))
                      .map((result) => (
                        <Card
                          key={result.domainName}
                          className={cn(
                            'cursor-pointer transition-all',
                            !result.isAvailable && 'opacity-50',
                            result.selected && result.isAvailable && 'ring-2 ring-primary'
                          )}
                          onClick={() => result.isAvailable && toggleSearchResult(result.domainName)}
                        >
                          <CardContent className="p-4">
                            <div className="flex items-center justify-between">
                              <div className="flex items-center gap-3">
                                <Checkbox
                                  checked={result.selected && result.isAvailable}
                                  disabled={!result.isAvailable}
                                />
                                <div>
                                  <div className="flex items-center gap-2">
                                    <span className="font-mono font-medium">
                                      {result.domainName}
                                    </span>
                                    {result.isDeal && (
                                      <Badge variant="default" className="bg-green-600">
                                        Deal!
                                      </Badge>
                                    )}
                                    {!result.isAvailable && (
                                      <Badge variant="destructive">Unavailable</Badge>
                                    )}
                                  </div>
                                  {result.bestRegistrar && result.isAvailable && (
                                    <p className="text-xs text-muted-foreground">
                                      Best: {result.bestRegistrar}
                                    </p>
                                  )}
                                </div>
                              </div>
                              {result.isAvailable && result.bestPrice && (
                                <div className="text-right">
                                  <div className="flex items-center gap-1 text-lg font-bold">
                                    <DollarSign className="h-4 w-4" />
                                    {result.bestPrice.toFixed(2)}
                                  </div>
                                  <div className="flex items-center gap-1 text-xs text-muted-foreground">
                                    <Star className="h-3 w-3" />
                                    Score: {result.valueScore.toFixed(0)}
                                  </div>
                                </div>
                              )}
                            </div>
                          </CardContent>
                        </Card>
                      ))}
                  </div>
                </>
              )}
            </div>
          )}

          {/* Step 3: Purchase */}
          {currentStep === 'purchase' && (
            <div className="space-y-4">
              <Alert>
                <ShoppingCart className="h-4 w-4" />
                <AlertDescription>
                  Review your selection and complete the purchase. Domains will be registered
                  with the selected registrars and added to your inventory.
                </AlertDescription>
              </Alert>

              <Card>
                <CardHeader>
                  <CardTitle className="text-base">Purchase Summary</CardTitle>
                </CardHeader>
                <CardContent>
                  <div className="space-y-3">
                    {searchResults
                      .filter((r) => r.selected && r.isAvailable)
                      .map((domain) => (
                        <div
                          key={domain.domainName}
                          className="flex items-center justify-between py-2 border-b last:border-0"
                        >
                          <div>
                            <span className="font-mono">{domain.domainName}</span>
                            <p className="text-xs text-muted-foreground">
                              via {domain.bestRegistrar}
                            </p>
                          </div>
                          <span className="font-medium">${domain.bestPrice?.toFixed(2)}</span>
                        </div>
                      ))}

                    <div className="flex items-center justify-between pt-3 border-t">
                      <span className="font-medium">Total</span>
                      <span className="text-lg font-bold">${totalPurchasePrice.toFixed(2)}</span>
                    </div>
                  </div>
                </CardContent>
              </Card>

              {selectedSearchResultsCount === 0 && (
                <Alert variant="destructive">
                  <AlertTriangle className="h-4 w-4" />
                  <AlertDescription>
                    No domains selected for purchase. Go back and select domains.
                  </AlertDescription>
                </Alert>
              )}
            </div>
          )}
        </div>

        {/* Navigation */}
        <div className="flex items-center justify-between pt-4 border-t">
          <Button
            variant="outline"
            onClick={goBack}
            disabled={currentStepIndex === 0}
          >
            Back
          </Button>

          <div className="flex gap-2">
            <Button variant="ghost" onClick={() => onOpenChange(false)}>
              Cancel
            </Button>

            {currentStep === 'review' && (
              <Button
                onClick={handleProceedToSearch}
                disabled={approvedCandidates.length === 0}
              >
                Continue with {approvedCandidates.length} domains
                <ArrowRight className="h-4 w-4 ml-2" />
              </Button>
            )}

            {currentStep === 'search' && searchResults.length === 0 && (
              <Button onClick={handleSearch} disabled={isLoading}>
                {isLoading ? (
                  <>
                    <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                    Searching...
                  </>
                ) : (
                  <>
                    <Search className="h-4 w-4 mr-2" />
                    Search Registrars
                  </>
                )}
              </Button>
            )}

            {currentStep === 'search' && searchResults.length > 0 && (
              <Button onClick={goNext} disabled={selectedSearchResultsCount === 0}>
                Review Purchase
                <ArrowRight className="h-4 w-4 ml-2" />
              </Button>
            )}

            {currentStep === 'purchase' && (
              <Button
                onClick={handlePurchase}
                disabled={isLoading || selectedSearchResultsCount === 0}
              >
                {isLoading ? (
                  <>
                    <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                    Purchasing...
                  </>
                ) : (
                  <>
                    <ShoppingCart className="h-4 w-4 mr-2" />
                    Purchase ${totalPurchasePrice.toFixed(2)}
                  </>
                )}
              </Button>
            )}
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}

export default DomainSourcingWizard;
