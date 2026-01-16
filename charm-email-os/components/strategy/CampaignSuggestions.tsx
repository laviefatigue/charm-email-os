'use client';

import { useState, useEffect } from 'react';
import { strategyApi, type StrategySuggestion, type StrategyJob } from '@/lib/api';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Textarea } from '@/components/ui/textarea';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter, DialogDescription } from '@/components/ui/dialog';
import {
  CheckCircle2,
  XCircle,
  MessageSquare,
  RefreshCw,
  Loader2,
  Sparkles,
  Copy,
  Check
} from 'lucide-react';

interface CampaignSuggestionsProps {
  clientId: string;
}

export function CampaignSuggestions({ clientId }: CampaignSuggestionsProps) {
  const [suggestions, setSuggestions] = useState<StrategySuggestion[]>([]);
  const [counts, setCounts] = useState({
    pending: 0,
    approved: 0,
    denied: 0,
    revision: 0,
    total: 0,
  });
  const [loading, setLoading] = useState(true);
  const [generating, setGenerating] = useState(false);
  const [currentJob, setCurrentJob] = useState<StrategyJob | null>(null);
  const [error, setError] = useState<string | null>(null);

  // Revision modal state
  const [revisionModal, setRevisionModal] = useState<{
    open: boolean;
    suggestionId: string | null;
    subjectLine: string;
  }>({ open: false, suggestionId: null, subjectLine: '' });
  const [revisionInstruction, setRevisionInstruction] = useState('');
  const [submittingRevision, setSubmittingRevision] = useState(false);

  // Copy state
  const [copiedId, setCopiedId] = useState<string | null>(null);

  const fetchSuggestions = async () => {
    try {
      setLoading(true);
      const response = await strategyApi.getSuggestions(clientId);
      setSuggestions(response.suggestions);
      setCounts({
        pending: response.pendingCount,
        approved: response.approvedCount,
        denied: response.deniedCount,
        revision: response.revisionCount,
        total: response.total,
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to fetch suggestions');
    } finally {
      setLoading(false);
    }
  };

  const pollForJobCompletion = async (jobId: string) => {
    const poll = async () => {
      try {
        const status = await strategyApi.getJobStatus(jobId);
        setCurrentJob(status);

        if (status.status === 'review' || status.status === 'completed') {
          setGenerating(false);
          setCurrentJob(null);
          await fetchSuggestions();
        } else if (status.status === 'failed') {
          setGenerating(false);
          setCurrentJob(null);
          setError(status.errorMessage || 'Generation failed');
        } else {
          // Still processing, poll again in 3 seconds
          setTimeout(poll, 3000);
        }
      } catch (err) {
        setGenerating(false);
        setCurrentJob(null);
        setError(err instanceof Error ? err.message : 'Failed to check job status');
      }
    };

    poll();
  };

  const handleGenerateMore = async () => {
    try {
      setGenerating(true);
      setError(null);
      const response = await strategyApi.createJob(clientId);
      pollForJobCompletion(response.jobId);
    } catch (err) {
      setGenerating(false);
      setError(err instanceof Error ? err.message : 'Failed to start generation');
    }
  };

  const handleReview = async (suggestionId: string, action: 'approve' | 'deny') => {
    try {
      await strategyApi.reviewSuggestion(suggestionId, { action });
      await fetchSuggestions();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to review suggestion');
    }
  };

  const handleRevisionSubmit = async () => {
    if (!revisionModal.suggestionId || !revisionInstruction.trim()) return;

    try {
      setSubmittingRevision(true);
      await strategyApi.requestRevision(revisionModal.suggestionId, revisionInstruction);
      setRevisionModal({ open: false, suggestionId: null, subjectLine: '' });
      setRevisionInstruction('');
      await fetchSuggestions();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to request revision');
    } finally {
      setSubmittingRevision(false);
    }
  };

  const handleCopy = async (text: string, id: string) => {
    try {
      await navigator.clipboard.writeText(text);
      setCopiedId(id);
      setTimeout(() => setCopiedId(null), 2000);
    } catch (err) {
      console.error('Failed to copy:', err);
    }
  };

  useEffect(() => {
    fetchSuggestions();
  }, [clientId]);

  const getStatusBadge = (status: string) => {
    switch (status) {
      case 'pending':
        return <Badge variant="outline">Pending Review</Badge>;
      case 'approved':
        return <Badge className="bg-green-500">Approved</Badge>;
      case 'denied':
        return <Badge variant="destructive">Denied</Badge>;
      case 'revision_requested':
        return <Badge className="bg-yellow-500">Revision Requested</Badge>;
      default:
        return <Badge variant="outline">{status}</Badge>;
    }
  };

  const getScoreColor = (score?: number) => {
    if (!score) return 'text-gray-400';
    if (score >= 85) return 'text-green-500';
    if (score >= 70) return 'text-yellow-500';
    return 'text-red-500';
  };

  if (loading) {
    return (
      <Card>
        <CardContent className="flex items-center justify-center py-8">
          <Loader2 className="h-6 w-6 animate-spin mr-2" />
          <span>Loading suggestions...</span>
        </CardContent>
      </Card>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header with stats and generate button */}
      <Card>
        <CardHeader className="pb-3">
          <div className="flex items-center justify-between">
            <div>
              <CardTitle className="flex items-center gap-2">
                <Sparkles className="h-5 w-5" />
                Campaign Suggestions
              </CardTitle>
              <CardDescription>
                AI-generated email variants for human review
              </CardDescription>
            </div>
            <Button
              onClick={handleGenerateMore}
              disabled={generating}
              className="gap-2"
            >
              {generating ? (
                <>
                  <Loader2 className="h-4 w-4 animate-spin" />
                  Generating...
                </>
              ) : (
                <>
                  <RefreshCw className="h-4 w-4" />
                  Generate More
                </>
              )}
            </Button>
          </div>
        </CardHeader>
        <CardContent>
          <div className="flex gap-4 text-sm">
            <div className="flex items-center gap-1">
              <span className="text-muted-foreground">Pending:</span>
              <span className="font-medium">{counts.pending}</span>
            </div>
            <div className="flex items-center gap-1">
              <span className="text-muted-foreground">Approved:</span>
              <span className="font-medium text-green-600">{counts.approved}</span>
            </div>
            <div className="flex items-center gap-1">
              <span className="text-muted-foreground">Denied:</span>
              <span className="font-medium text-red-600">{counts.denied}</span>
            </div>
            <div className="flex items-center gap-1">
              <span className="text-muted-foreground">Revisions:</span>
              <span className="font-medium text-yellow-600">{counts.revision}</span>
            </div>
          </div>

          {generating && currentJob && (
            <div className="mt-4 p-3 bg-blue-50 rounded-lg border border-blue-200">
              <div className="flex items-center gap-2 text-blue-700">
                <Loader2 className="h-4 w-4 animate-spin" />
                <span>
                  Generation round {currentJob.generationRound} in progress...
                  Status: {currentJob.status}
                </span>
              </div>
            </div>
          )}
        </CardContent>
      </Card>

      {error && (
        <div className="p-4 bg-red-50 border border-red-200 rounded-lg text-red-700">
          {error}
          <Button
            variant="link"
            className="text-red-700 underline ml-2 p-0 h-auto"
            onClick={() => setError(null)}
          >
            Dismiss
          </Button>
        </div>
      )}

      {/* Suggestions list */}
      {suggestions.length === 0 ? (
        <Card>
          <CardContent className="text-center py-12">
            <Sparkles className="h-12 w-12 mx-auto text-muted-foreground mb-4" />
            <h3 className="text-lg font-medium mb-2">No Suggestions Yet</h3>
            <p className="text-muted-foreground mb-4">
              Click &quot;Generate More&quot; to create AI-powered campaign variants
            </p>
            <Button onClick={handleGenerateMore} disabled={generating}>
              {generating ? (
                <>
                  <Loader2 className="h-4 w-4 animate-spin mr-2" />
                  Generating...
                </>
              ) : (
                'Generate Campaign Variants'
              )}
            </Button>
          </CardContent>
        </Card>
      ) : (
        <div className="space-y-4">
          {suggestions.map((suggestion) => (
            <Card key={suggestion.id} className="overflow-hidden">
              <CardHeader className="pb-2">
                <div className="flex items-start justify-between">
                  <div className="flex-1">
                    <div className="flex items-center gap-2 mb-1">
                      <Badge variant="outline">V{suggestion.variantNumber}</Badge>
                      {getStatusBadge(suggestion.status)}
                      {suggestion.campaignType && (
                        <Badge variant="secondary">{suggestion.campaignType}</Badge>
                      )}
                      {suggestion.score !== undefined && (
                        <span className={`font-mono text-sm ${getScoreColor(suggestion.score)}`}>
                          Score: {suggestion.score}
                        </span>
                      )}
                    </div>
                    <CardTitle className="text-base flex items-center gap-2">
                      <span className="font-mono text-muted-foreground">Subject:</span>
                      {suggestion.subjectLine}
                      <Button
                        variant="ghost"
                        size="sm"
                        className="h-6 w-6 p-0"
                        onClick={() => handleCopy(suggestion.subjectLine, `${suggestion.id}-subject`)}
                      >
                        {copiedId === `${suggestion.id}-subject` ? (
                          <Check className="h-3 w-3 text-green-500" />
                        ) : (
                          <Copy className="h-3 w-3" />
                        )}
                      </Button>
                    </CardTitle>
                  </div>
                </div>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="relative">
                  <pre className="whitespace-pre-wrap text-sm bg-muted p-4 rounded-lg font-sans">
                    {suggestion.emailBody}
                  </pre>
                  <Button
                    variant="ghost"
                    size="sm"
                    className="absolute top-2 right-2 h-8 w-8 p-0"
                    onClick={() => handleCopy(suggestion.emailBody, `${suggestion.id}-body`)}
                  >
                    {copiedId === `${suggestion.id}-body` ? (
                      <Check className="h-4 w-4 text-green-500" />
                    ) : (
                      <Copy className="h-4 w-4" />
                    )}
                  </Button>
                </div>

                {suggestion.rationale && (
                  <div className="text-sm text-muted-foreground border-l-2 border-blue-200 pl-3">
                    <span className="font-medium">Rationale:</span> {suggestion.rationale}
                  </div>
                )}

                {suggestion.usedVariables && suggestion.usedVariables.length > 0 && (
                  <div className="flex flex-wrap gap-1">
                    <span className="text-xs text-muted-foreground mr-1">Variables:</span>
                    {suggestion.usedVariables.map((v, i) => (
                      <Badge key={i} variant="outline" className="text-xs font-mono">
                        {v}
                      </Badge>
                    ))}
                  </div>
                )}

                {suggestion.humanComment && (
                  <div className="text-sm bg-yellow-50 p-3 rounded border border-yellow-200">
                    <span className="font-medium">Human Feedback:</span> {suggestion.humanComment}
                  </div>
                )}

                {suggestion.status === 'pending' && (
                  <div className="flex gap-2 pt-2 border-t">
                    <Button
                      variant="outline"
                      size="sm"
                      className="text-green-600 border-green-200 hover:bg-green-50"
                      onClick={() => handleReview(suggestion.id, 'approve')}
                    >
                      <CheckCircle2 className="h-4 w-4 mr-1" />
                      Approve
                    </Button>
                    <Button
                      variant="outline"
                      size="sm"
                      className="text-red-600 border-red-200 hover:bg-red-50"
                      onClick={() => handleReview(suggestion.id, 'deny')}
                    >
                      <XCircle className="h-4 w-4 mr-1" />
                      Deny
                    </Button>
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => setRevisionModal({
                        open: true,
                        suggestionId: suggestion.id,
                        subjectLine: suggestion.subjectLine,
                      })}
                    >
                      <MessageSquare className="h-4 w-4 mr-1" />
                      Request Revision
                    </Button>
                  </div>
                )}
              </CardContent>
            </Card>
          ))}
        </div>
      )}

      {/* Revision Request Modal */}
      <Dialog open={revisionModal.open} onOpenChange={(open) => {
        if (!open) {
          setRevisionModal({ open: false, suggestionId: null, subjectLine: '' });
          setRevisionInstruction('');
        }
      }}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Request Revision</DialogTitle>
            <DialogDescription>
              Provide instructions for improving this variant
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4">
            <div className="text-sm">
              <span className="font-medium">Subject:</span>{' '}
              <span className="text-muted-foreground">{revisionModal.subjectLine}</span>
            </div>
            <Textarea
              placeholder="e.g., Make it shorter, add more proof points, change the opening angle..."
              value={revisionInstruction}
              onChange={(e) => setRevisionInstruction(e.target.value)}
              rows={4}
            />
          </div>
          <DialogFooter>
            <Button
              variant="outline"
              onClick={() => {
                setRevisionModal({ open: false, suggestionId: null, subjectLine: '' });
                setRevisionInstruction('');
              }}
            >
              Cancel
            </Button>
            <Button
              onClick={handleRevisionSubmit}
              disabled={!revisionInstruction.trim() || submittingRevision}
            >
              {submittingRevision ? (
                <>
                  <Loader2 className="h-4 w-4 animate-spin mr-2" />
                  Submitting...
                </>
              ) : (
                'Submit Revision Request'
              )}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
