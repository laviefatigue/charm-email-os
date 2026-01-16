'use client';

import { useState, useCallback } from 'react';
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
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import {
  Sparkles,
  Search,
  ShoppingCart,
  ArrowLeft,
  ArrowRight,
  Loader2,
  Check,
  X,
  DollarSign,
  Star,
  AlertTriangle,
  Globe,
} from 'lucide-react';
import { toast } from 'sonner';
import { cn } from '@/lib/utils';

// Types
interface TLDPreference {
  tld: string;
  priority: number;
  maxPrice: number;
}

interface DomainCandidate {
  id: string;
  domainName: string;
  baseName: string;
  tld: string;
  rationale?: string;
  legitimacyScore: number;
  selected?: boolean;
}

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
  industry: string;
  brandKeywords: string[];
  targetAudience?: string;
  onComplete?: (purchasedDomains: string[]) => void;
}

type WizardStep = 'configure' | 'generate' | 'search' | 'purchase';

const WIZARD_STEPS: { key: WizardStep; label: string; description: string }[] = [
  { key: 'configure', label: 'Configure', description: 'Set generation preferences' },
  { key: 'generate', label: 'Generate', description: 'Review AI suggestions' },
  { key: 'search', label: 'Search', description: 'Compare registrar prices' },
  { key: 'purchase', label: 'Purchase', description: 'Complete purchase' },
];

const DEFAULT_TLDS: TLDPreference[] = [
  { tld: '.com', priority: 1, maxPrice: 15 },
  { tld: '.io', priority: 2, maxPrice: 40 },
  { tld: '.co', priority: 3, maxPrice: 25 },
  { tld: '.ai', priority: 4, maxPrice: 50 },
];

const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://ccssgc4gowsog04wck400o0w.31.97.142.123.sslip.io';

export function DomainSourcingWizard({
  open,
  onOpenChange,
  clientId,
  clientName,
  industry,
  brandKeywords,
  targetAudience = '',
  onComplete,
}: DomainSourcingWizardProps) {
  // Wizard state
  const [currentStep, setCurrentStep] = useState<WizardStep>('configure');
  const [isLoading, setIsLoading] = useState(false);

  // Configuration state
  const [domainsNeeded, setDomainsNeeded] = useState(6);
  const [tldPreferences, setTldPreferences] = useState<TLDPreference[]>(DEFAULT_TLDS);
  const [aiProvider, setAiProvider] = useState('openai');
  const [aiModel, setAiModel] = useState('gpt-4');
  const [avoidWords, setAvoidWords] = useState<string[]>([]);
  const [avoidWordInput, setAvoidWordInput] = useState('');

  // Generation results
  const [candidates, setCandidates] = useState<DomainCandidate[]>([]);
  const [filteredDuplicates, setFilteredDuplicates] = useState(0);

  // Search results
  const [searchResults, setSearchResults] = useState<SearchResult[]>([]);
  const [targetPrice, setTargetPrice] = useState(8);
  const [maxPrice, setMaxPrice] = useState(15);

  // Get current step index
  const currentStepIndex = WIZARD_STEPS.findIndex((s) => s.key === currentStep);

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

  // API calls
  const handleGenerate = useCallback(async () => {
    setIsLoading(true);
    try {
      // Use the new client-based endpoint that:
      // 1. Pulls onboarding data automatically
      // 2. Checks uniqueness against existing domains
      // 3. Saves unique candidates to DB
      const response = await fetch(`${API_BASE}/api/domain-sourcing/generate-for-client/${clientId}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          count: domainsNeeded,
          ai_provider: aiProvider,
          ai_model: aiModel,
          preferred_tlds: tldPreferences.map((t) => ({
            tld: t.tld.replace('.', ''),  // Remove dot prefix
            priority: t.priority,
            max_price: t.maxPrice,
          })),
        }),
      });

      if (!response.ok) {
        const error = await response.json();
        throw new Error(error.detail || 'Failed to generate domains');
      }

      const data = await response.json();

      // Map response to candidates (these are already saved to DB)
      setCandidates(
        data.generated_domains.map((c: any) => ({
          id: c.id,
          domainName: c.domain_name,
          baseName: c.base_name,
          tld: c.tld,
          rationale: c.rationale,
          legitimacyScore: c.legitimacy_score,
          selected: true,
        }))
      );

      // Track how many duplicates were filtered
      setFilteredDuplicates(data.filtered_count || 0);

      const message = data.filtered_count > 0
        ? `Generated ${data.generated_domains.length} unique domains (${data.filtered_count} duplicates filtered)`
        : `Generated ${data.generated_domains.length} domain suggestions`;
      toast.success(message);
      goNext();
    } catch (error: any) {
      toast.error(error.message || 'Failed to generate domains');
    } finally {
      setIsLoading(false);
    }
  }, [clientId, domainsNeeded, tldPreferences, aiProvider, aiModel]);

  const handleSearch = useCallback(async () => {
    const selectedCandidates = candidates.filter((c) => c.selected);
    if (selectedCandidates.length === 0) {
      toast.error('Select at least one domain to search');
      return;
    }

    setIsLoading(true);
    try {
      const response = await fetch(`${API_BASE}/api/domain-sourcing/search`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          candidates: selectedCandidates.map((c) => ({
            id: c.id,
            domain_name: c.domainName,
            base_name: c.baseName,
            tld: c.tld,
            rationale: c.rationale,
            legitimacy_score: c.legitimacyScore,
          })),
          target_price: targetPrice,
          max_price: maxPrice,
          include_variations: true,
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
  }, [candidates, targetPrice, maxPrice]);

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
          nameservers: [], // Will be set up after purchase
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

  // Toggle candidate selection
  const toggleCandidate = (id: string) => {
    setCandidates((prev) =>
      prev.map((c) => (c.id === id ? { ...c, selected: !c.selected } : c))
    );
  };

  // Toggle search result selection
  const toggleSearchResult = (domainName: string) => {
    setSearchResults((prev) =>
      prev.map((r) =>
        r.domainName === domainName ? { ...r, selected: !r.selected } : r
      )
    );
  };

  // Add avoid word
  const addAvoidWord = () => {
    if (avoidWordInput.trim() && !avoidWords.includes(avoidWordInput.trim().toLowerCase())) {
      setAvoidWords((prev) => [...prev, avoidWordInput.trim().toLowerCase()]);
      setAvoidWordInput('');
    }
  };

  // Remove avoid word
  const removeAvoidWord = (word: string) => {
    setAvoidWords((prev) => prev.filter((w) => w !== word));
  };

  // Calculate totals
  const selectedCandidatesCount = candidates.filter((c) => c.selected).length;
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
            Domain Sourcing Wizard
          </DialogTitle>
          <DialogDescription>
            Generate AI-powered domain suggestions and purchase from registrars
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
          {currentStep === 'configure' && (
            <div className="space-y-6">
              <Card>
                <CardHeader>
                  <CardTitle className="text-base">Generation Settings</CardTitle>
                  <CardDescription>
                    Configure how domains will be generated for {clientName}
                  </CardDescription>
                </CardHeader>
                <CardContent className="space-y-4">
                  {/* Domains needed */}
                  <div className="space-y-2">
                    <Label>Number of domains to generate</Label>
                    <Select
                      value={domainsNeeded.toString()}
                      onValueChange={(v) => setDomainsNeeded(parseInt(v))}
                    >
                      <SelectTrigger>
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        {[4, 6, 8, 10, 12].map((n) => (
                          <SelectItem key={n} value={n.toString()}>
                            {n} domains
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </div>

                  {/* AI Provider */}
                  <div className="grid grid-cols-2 gap-4">
                    <div className="space-y-2">
                      <Label>AI Provider</Label>
                      <Select value={aiProvider} onValueChange={setAiProvider}>
                        <SelectTrigger>
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          <SelectItem value="openai">OpenAI</SelectItem>
                          <SelectItem value="anthropic">Anthropic (Claude)</SelectItem>
                          <SelectItem value="ollama">Ollama (Local)</SelectItem>
                        </SelectContent>
                      </Select>
                    </div>
                    <div className="space-y-2">
                      <Label>Model</Label>
                      <Select value={aiModel} onValueChange={setAiModel}>
                        <SelectTrigger>
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          {aiProvider === 'openai' && (
                            <>
                              <SelectItem value="gpt-4">GPT-4</SelectItem>
                              <SelectItem value="gpt-4-turbo">GPT-4 Turbo</SelectItem>
                              <SelectItem value="gpt-3.5-turbo">GPT-3.5 Turbo</SelectItem>
                            </>
                          )}
                          {aiProvider === 'anthropic' && (
                            <>
                              <SelectItem value="claude-3-opus">Claude 3 Opus</SelectItem>
                              <SelectItem value="claude-3-sonnet">Claude 3 Sonnet</SelectItem>
                            </>
                          )}
                          {aiProvider === 'ollama' && (
                            <>
                              <SelectItem value="llama2">Llama 2</SelectItem>
                              <SelectItem value="mistral">Mistral</SelectItem>
                            </>
                          )}
                        </SelectContent>
                      </Select>
                    </div>
                  </div>

                  {/* TLD Preferences */}
                  <div className="space-y-2">
                    <Label>TLD Preferences (drag to reorder priority)</Label>
                    <div className="flex flex-wrap gap-2">
                      {tldPreferences.map((tld, index) => (
                        <Badge
                          key={tld.tld}
                          variant="outline"
                          className="px-3 py-1 cursor-pointer"
                        >
                          {index + 1}. {tld.tld} (max ${tld.maxPrice})
                        </Badge>
                      ))}
                    </div>
                  </div>

                  {/* Avoid Words */}
                  <div className="space-y-2">
                    <Label>Words to avoid</Label>
                    <div className="flex gap-2">
                      <Input
                        placeholder="Add word to avoid..."
                        value={avoidWordInput}
                        onChange={(e) => setAvoidWordInput(e.target.value)}
                        onKeyDown={(e) => e.key === 'Enter' && addAvoidWord()}
                      />
                      <Button variant="outline" onClick={addAvoidWord}>
                        Add
                      </Button>
                    </div>
                    {avoidWords.length > 0 && (
                      <div className="flex flex-wrap gap-2 mt-2">
                        {avoidWords.map((word) => (
                          <Badge
                            key={word}
                            variant="secondary"
                            className="cursor-pointer"
                            onClick={() => removeAvoidWord(word)}
                          >
                            {word}
                            <X className="h-3 w-3 ml-1" />
                          </Badge>
                        ))}
                      </div>
                    )}
                  </div>
                </CardContent>
              </Card>

              {/* Client Context */}
              <Card>
                <CardHeader className="pb-2">
                  <CardTitle className="text-base">Client Context</CardTitle>
                  <CardDescription>
                    Pulled automatically from {clientName}&apos;s onboarding data
                  </CardDescription>
                </CardHeader>
                <CardContent>
                  <div className="grid grid-cols-2 gap-4 text-sm">
                    <div>
                      <span className="text-muted-foreground">Industry:</span>
                      <p className="font-medium">{industry || 'From onboarding'}</p>
                    </div>
                    <div>
                      <span className="text-muted-foreground">Brand Keywords:</span>
                      <p className="font-medium">{brandKeywords.length > 0 ? brandKeywords.join(', ') : 'Extracted from product'}</p>
                    </div>
                    {targetAudience && (
                      <div className="col-span-2">
                        <span className="text-muted-foreground">Target Audience:</span>
                        <p className="font-medium">{targetAudience}</p>
                      </div>
                    )}
                  </div>
                  <Alert className="mt-3">
                    <AlertDescription className="text-xs">
                      Domains are automatically checked for uniqueness. Existing domains for this client will not be regenerated.
                    </AlertDescription>
                  </Alert>
                </CardContent>
              </Card>
            </div>
          )}

          {currentStep === 'generate' && (
            <div className="space-y-4">
              {candidates.length === 0 ? (
                <div className="flex flex-col items-center justify-center py-12">
                  <Sparkles className="h-12 w-12 text-muted-foreground mb-4" />
                  <p className="text-lg font-medium">Ready to Generate</p>
                  <p className="text-sm text-muted-foreground mb-4">
                    Click generate to create AI-powered domain suggestions
                  </p>
                  <Button onClick={handleGenerate} disabled={isLoading}>
                    {isLoading ? (
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
              ) : (
                <>
                  <div className="flex items-center justify-between">
                    <div>
                      <p className="text-sm text-muted-foreground">
                        {selectedCandidatesCount} of {candidates.length} selected
                      </p>
                      {filteredDuplicates > 0 && (
                        <p className="text-xs text-orange-600">
                          {filteredDuplicates} duplicate(s) filtered (already exist for this client)
                        </p>
                      )}
                    </div>
                    <Button variant="outline" size="sm" onClick={handleGenerate} disabled={isLoading}>
                      {isLoading ? (
                        <Loader2 className="h-4 w-4 animate-spin" />
                      ) : (
                        <>
                          <Sparkles className="h-4 w-4 mr-2" />
                          Regenerate
                        </>
                      )}
                    </Button>
                  </div>
                  <Alert className="mb-3">
                    <Check className="h-4 w-4" />
                    <AlertDescription className="text-xs">
                      These domains have been saved to your inventory. Select which ones to search for pricing.
                    </AlertDescription>
                  </Alert>
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                    {candidates.map((candidate) => (
                      <Card
                        key={candidate.id}
                        className={cn(
                          'cursor-pointer transition-all',
                          candidate.selected ? 'ring-2 ring-primary' : ''
                        )}
                        onClick={() => toggleCandidate(candidate.id)}
                      >
                        <CardContent className="p-4">
                          <div className="flex items-start justify-between">
                            <div className="flex-1">
                              <div className="flex items-center gap-2">
                                <Checkbox checked={candidate.selected} />
                                <span className="font-mono font-medium">
                                  {candidate.domainName}
                                </span>
                              </div>
                              {candidate.rationale && (
                                <p className="text-xs text-muted-foreground mt-1 ml-6">
                                  {candidate.rationale}
                                </p>
                              )}
                            </div>
                            <Badge variant="outline" className="ml-2">
                              <Star className="h-3 w-3 mr-1" />
                              {candidate.legitimacyScore}%
                            </Badge>
                          </div>
                        </CardContent>
                      </Card>
                    ))}
                  </div>
                </>
              )}
            </div>
          )}

          {currentStep === 'search' && (
            <div className="space-y-4">
              {searchResults.length === 0 ? (
                <div className="space-y-4">
                  <Card>
                    <CardHeader className="pb-2">
                      <CardTitle className="text-base">Search Settings</CardTitle>
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
                            Exclude domains above this price
                          </p>
                        </div>
                      </div>
                    </CardContent>
                  </Card>

                  <div className="flex flex-col items-center justify-center py-8">
                    <Search className="h-12 w-12 text-muted-foreground mb-4" />
                    <p className="text-lg font-medium">Ready to Search</p>
                    <p className="text-sm text-muted-foreground mb-4">
                      Search {selectedCandidatesCount} domains across registrars
                    </p>
                    <Button onClick={handleSearch} disabled={isLoading || selectedCandidatesCount === 0}>
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
                        {' · '}
                        <span className="text-green-600 font-medium">{searchResults.filter((r) => r.isDeal).length}</span> deals
                      </p>
                      <p className="text-xs text-muted-foreground">
                        {selectedSearchResultsCount} selected · Total: ${totalPurchasePrice.toFixed(2)}
                      </p>
                    </div>
                    <Button variant="outline" size="sm" onClick={handleSearch} disabled={isLoading}>
                      {isLoading ? (
                        <Loader2 className="h-4 w-4 animate-spin" />
                      ) : (
                        <>
                          <Search className="h-4 w-4 mr-2" />
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

          {currentStep === 'purchase' && (
            <div className="space-y-4">
              <Alert>
                <ShoppingCart className="h-4 w-4" />
                <AlertDescription>
                  Review your selection and complete the purchase. Domains will be registered
                  with the selected registrars and added to your inventory.
                </AlertDescription>
              </Alert>

              {/* Purchase Summary */}
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
            <ArrowLeft className="h-4 w-4 mr-2" />
            Back
          </Button>

          <div className="flex gap-2">
            <Button variant="ghost" onClick={() => onOpenChange(false)}>
              Cancel
            </Button>

            {currentStep === 'configure' && (
              <Button onClick={handleGenerate} disabled={isLoading}>
                {isLoading ? (
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
            )}

            {currentStep === 'generate' && candidates.length > 0 && (
              <Button onClick={goNext} disabled={selectedCandidatesCount === 0}>
                Search Prices
                <ArrowRight className="h-4 w-4 ml-2" />
              </Button>
            )}

            {currentStep === 'search' && searchResults.length === 0 && (
              <Button onClick={handleSearch} disabled={isLoading || selectedCandidatesCount === 0}>
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
