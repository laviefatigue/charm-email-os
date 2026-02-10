'use client';

import { useState, useEffect, useCallback } from 'react';
import { RefreshCw, Sparkles, Filter, Loader2, List, FileText } from 'lucide-react';
import { Card, CardHeader, CardContent, CardTitle, CardDescription } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
  DialogDescription,
} from '@/components/ui/dialog';
import { Textarea } from '@/components/ui/textarea';
import { Label } from '@/components/ui/label';
import { Input } from '@/components/ui/input';
import { StrategySelector } from './StrategySelector';
import { SequenceCampaignSelector } from './SequenceCampaignSelector';
import { SelectedCampaignDetail } from './SelectedCampaignDetail';
import { CampaignDocumentView } from './CampaignDocumentView';
import {
  strategyApi,
  type CampaignSequence,
  type ClientSequencesResponse,
  type SequenceEmailEditRequest,
} from '@/lib/api';
import { toast } from 'sonner';
import { cn } from '@/lib/utils';

interface CampaignSequencesProps {
  clientId: string;
  className?: string;
}

export function CampaignSequences({ clientId, className }: CampaignSequencesProps) {
  // View mode: 'sequences' (legacy) or 'documents' (new stablekernel format)
  const [viewMode, setViewMode] = useState<'sequences' | 'documents'>('documents');

  const [sequences, setSequences] = useState<CampaignSequence[]>([]);
  const [loading, setLoading] = useState(true);
  const [generating, setGenerating] = useState(false);
  const [generationStatus, setGenerationStatus] = useState<{
    jobId: string;
    round: number;
    status: string;
    startedAt: Date;
  } | null>(null);
  const [counts, setCounts] = useState({
    pending: 0,
    approved: 0,
    denied: 0,
    revision: 0,
    total: 0,
  });

  // Filters and sorting
  const [statusFilter, setStatusFilter] = useState<string>('all');
  const [selectedStrategyId, setSelectedStrategyId] = useState<string>('');
  const [sortBy, setSortBy] = useState<'created_at' | 'score'>('created_at');
  const [sortOrder, setSortOrder] = useState<'asc' | 'desc'>('desc');

  // Selected campaign for detail view
  const [selectedCampaignId, setSelectedCampaignId] = useState<string | null>(null);

  // Edit modal state
  const [editingEmail, setEditingEmail] = useState<{
    sequenceId: string;
    position: number;
    subjectLine: string;
    emailBody: string;
  } | null>(null);

  // Revision modal state
  const [revisionRequest, setRevisionRequest] = useState<{
    sequenceId: string;
    emailPosition?: number;
    instruction: string;
    scope: 'single' | 'subsequent' | 'all';
  } | null>(null);

  // Fetch sequences
  const fetchSequences = useCallback(async () => {
    setLoading(true);
    try {
      const params: Parameters<typeof strategyApi.getSequences>[1] = {
        sort: sortBy,
        order: sortOrder,
      };
      if (statusFilter !== 'all') {
        params.status = statusFilter;
      }
      if (selectedStrategyId) {
        params.strategyId = selectedStrategyId;
      }

      const response: ClientSequencesResponse = await strategyApi.getSequences(clientId, params);
      setSequences(response.sequences);
      setCounts({
        pending: response.pendingCount,
        approved: response.approvedCount,
        denied: response.deniedCount,
        revision: response.revisionCount,
        total: response.total,
      });
    } catch (error) {
      console.error('Failed to fetch sequences:', error);
      toast.error('Failed to load campaign sequences');
    } finally {
      setLoading(false);
    }
  }, [clientId, statusFilter, selectedStrategyId, sortBy, sortOrder]);

  useEffect(() => {
    fetchSequences();
  }, [fetchSequences]);

  // Auto-select first campaign when sequences load (if none selected)
  useEffect(() => {
    if (sequences.length > 0 && !selectedCampaignId) {
      // Select first non-denied sequence
      const firstActive = sequences.find(s => s.status !== 'denied');
      if (firstActive) {
        setSelectedCampaignId(firstActive.id);
      }
    }
    // Clear selection if selected campaign no longer exists
    if (selectedCampaignId && !sequences.find(s => s.id === selectedCampaignId)) {
      const firstActive = sequences.find(s => s.status !== 'denied');
      setSelectedCampaignId(firstActive?.id || null);
    }
  }, [sequences, selectedCampaignId]);

  // Get selected campaign details
  const selectedCampaign = selectedCampaignId
    ? sequences.find(s => s.id === selectedCampaignId)
    : null;

  // Generate more sequences
  const handleGenerate = async () => {
    setGenerating(true);
    setGenerationStatus(null);
    try {
      const job = await strategyApi.createJob(
        clientId,
        undefined,
        selectedStrategyId || undefined
      );

      // Set generation status for UI feedback
      setGenerationStatus({
        jobId: job.jobId,
        round: job.generationRound,
        status: 'processing',
        startedAt: new Date(),
      });

      toast.success(`Generation job started (Round ${job.generationRound})`);

      // Poll for completion
      let attempts = 0;
      const maxAttempts = 60; // 5 minutes with 5s intervals
      const pollInterval = setInterval(async () => {
        attempts++;
        try {
          const status = await strategyApi.getJobStatus(job.jobId);

          // Update status for UI
          setGenerationStatus(prev => prev ? { ...prev, status: status.status } : null);

          if (status.status === 'review' || status.status === 'completed') {
            clearInterval(pollInterval);
            toast.success('New sequences generated!');
            setGenerationStatus(null);
            fetchSequences();
            setGenerating(false);
          } else if (status.status === 'failed') {
            clearInterval(pollInterval);
            toast.error(`Generation failed: ${status.errorMessage || 'Unknown error'}`);
            setGenerationStatus(null);
            setGenerating(false);
          } else if (attempts >= maxAttempts) {
            clearInterval(pollInterval);
            toast.error('Generation timed out. Check job status manually.');
            setGenerationStatus(null);
            setGenerating(false);
          }
        } catch {
          // Ignore polling errors
        }
      }, 5000);
    } catch (error) {
      console.error('Failed to start generation:', error);
      toast.error('Failed to start generation');
      setGenerationStatus(null);
      setGenerating(false);
    }
  };

  // Handle approve
  const handleApprove = async (sequenceId: string) => {
    try {
      await strategyApi.reviewSequence(sequenceId, { action: 'approve' });
      toast.success('Sequence approved');
      fetchSequences();
    } catch (error) {
      console.error('Failed to approve:', error);
      toast.error('Failed to approve sequence');
    }
  };

  // Handle deny
  const handleDeny = async (sequenceId: string) => {
    try {
      await strategyApi.reviewSequence(sequenceId, { action: 'deny' });
      toast.success('Sequence denied');
      fetchSequences();
    } catch (error) {
      console.error('Failed to deny:', error);
      toast.error('Failed to deny sequence');
    }
  };

  // Handle edit email
  const handleEditEmail = (sequenceId: string, position: number) => {
    const sequence = sequences.find((s) => s.id === sequenceId);
    if (!sequence) return;

    const email = sequence.emails.find((e) => e.position === position);
    if (!email) return;

    setEditingEmail({
      sequenceId,
      position,
      subjectLine: email.editedSubjectLine || email.subjectLine || '',
      emailBody: email.editedEmailBody || email.emailBody,
    });
  };

  // Save email edit
  const handleSaveEdit = async () => {
    if (!editingEmail) return;

    try {
      const data: SequenceEmailEditRequest = {
        emailBody: editingEmail.emailBody,
      };
      // Only include subject line for positions 1 and 3
      if (editingEmail.position === 1 || editingEmail.position === 3) {
        data.subjectLine = editingEmail.subjectLine;
      }

      await strategyApi.editSequenceEmail(
        editingEmail.sequenceId,
        editingEmail.position,
        data
      );
      toast.success(`Email ${editingEmail.position} updated`);
      setEditingEmail(null);
      fetchSequences();
    } catch (error) {
      console.error('Failed to save edit:', error);
      toast.error('Failed to save changes');
    }
  };

  // Handle revision request
  const handleRequestRevision = (sequenceId: string, emailPosition?: number) => {
    setRevisionRequest({
      sequenceId,
      emailPosition,
      instruction: '',
      scope: emailPosition ? 'single' : 'all',
    });
  };

  // Submit revision request
  const handleSubmitRevision = async () => {
    if (!revisionRequest || !revisionRequest.instruction.trim()) {
      toast.error('Please provide revision instructions');
      return;
    }

    try {
      await strategyApi.requestSequenceRevision(revisionRequest.sequenceId, {
        emailPosition: revisionRequest.emailPosition || 0,
        instruction: revisionRequest.instruction,
        scope: revisionRequest.scope,
      });
      toast.success('Revision requested - new sequence will be generated');
      setRevisionRequest(null);
      fetchSequences();
    } catch (error) {
      console.error('Failed to request revision:', error);
      toast.error('Failed to request revision');
    }
  };

  // Handle spintax processing
  const handleSpintax = async (sequenceId: string) => {
    try {
      const result = await strategyApi.createSpintaxJob(sequenceId);
      toast.success('Spintax processing started');
      // Start polling for completion
      pollSpintaxStatus(result.jobId);
    } catch (error) {
      console.error('Failed to start spintax processing:', error);
      toast.error('Failed to start spintax processing');
    }
  };

  // Poll for spintax job completion
  const pollSpintaxStatus = async (jobId: string) => {
    const poll = async () => {
      try {
        const status = await strategyApi.getSpintaxJobStatus(jobId);
        if (status.status === 'completed') {
          toast.success('Spintax processing complete');
          fetchSequences();
        } else if (status.status === 'failed') {
          toast.error(`Spintax processing failed: ${status.errorMessage || 'Unknown error'}`);
          fetchSequences();
        } else {
          // Still processing, poll again in 2 seconds
          setTimeout(poll, 2000);
        }
      } catch (error) {
        console.error('Failed to check spintax status:', error);
      }
    };
    poll();
  };

  // Handle push to EmailBison
  const handlePushToEmailBison = async (sequenceId: string) => {
    try {
      const result = await strategyApi.pushSequenceToEmailBison(sequenceId);
      toast.success(`Campaign created in EmailBison (${result.emailsPushed} emails)`);
      fetchSequences();
    } catch (error) {
      console.error('Failed to push to EmailBison:', error);
      toast.error('Failed to push to EmailBison');
    }
  };

  // Filter sequences for selector (exclude denied by default unless filter is set)
  const selectableSequences = statusFilter === 'denied'
    ? sequences
    : sequences.filter((s) => s.status !== 'denied');

  return (
    <div className={cn('space-y-4', className)}>
      {/* Header Card with Filters */}
      <Card>
        <CardHeader className="pb-3">
          <div className="flex items-center justify-between">
            <div>
              <CardTitle className="text-lg">Campaign Sequences</CardTitle>
              <CardDescription>
                4-email campaign sequences generated by Strategy-AI
              </CardDescription>
            </div>
            <div className="flex items-center gap-2">
              {/* View Mode Toggle */}
              <div className="flex items-center border rounded-lg p-1">
                <Button
                  size="sm"
                  variant={viewMode === 'documents' ? 'default' : 'ghost'}
                  className="h-8"
                  onClick={() => setViewMode('documents')}
                >
                  <FileText className="w-4 h-4 mr-1" />
                  Document
                </Button>
                <Button
                  size="sm"
                  variant={viewMode === 'sequences' ? 'default' : 'ghost'}
                  className="h-8"
                  onClick={() => setViewMode('sequences')}
                >
                  <List className="w-4 h-4 mr-1" />
                  Sequences
                </Button>
              </div>

              <Button onClick={handleGenerate} disabled={generating}>
                {generating ? (
                  <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                ) : (
                  <Sparkles className="w-4 h-4 mr-2" />
                )}
                Generate More
              </Button>
            </div>
          </div>

          {/* Filters row - only show for sequences view */}
          {viewMode === 'sequences' && (
          <div className="flex items-center gap-3 mt-4 flex-wrap">
            <StrategySelector
              clientId={clientId}
              selectedStrategyId={selectedStrategyId || null}
              onStrategyChange={(id) => setSelectedStrategyId(id || '')}
            />

            <Select value={statusFilter} onValueChange={setStatusFilter}>
              <SelectTrigger className="w-[150px]">
                <Filter className="w-4 h-4 mr-2" />
                <SelectValue placeholder="Status" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">All Status</SelectItem>
                <SelectItem value="pending">Pending</SelectItem>
                <SelectItem value="approved">Approved</SelectItem>
                <SelectItem value="denied">Denied</SelectItem>
                <SelectItem value="revision_requested">Revisions</SelectItem>
              </SelectContent>
            </Select>

            <Select
              value={`${sortBy}-${sortOrder}`}
              onValueChange={(value) => {
                const [field, order] = value.split('-') as ['created_at' | 'score', 'asc' | 'desc'];
                setSortBy(field);
                setSortOrder(order);
              }}
            >
              <SelectTrigger className="w-[160px]">
                <SelectValue placeholder="Sort by" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="created_at-desc">Newest First</SelectItem>
                <SelectItem value="created_at-asc">Oldest First</SelectItem>
                <SelectItem value="score-desc">Highest Score</SelectItem>
                <SelectItem value="score-asc">Lowest Score</SelectItem>
              </SelectContent>
            </Select>

            <Button variant="outline" size="sm" onClick={fetchSequences}>
              <RefreshCw className="w-4 h-4" />
            </Button>
          </div>
          )}

          {/* Campaign selector - sequences view only */}
          {viewMode === 'sequences' && !loading && sequences.length > 0 && (
            <div className="mt-4 pt-4 border-t">
              <SequenceCampaignSelector
                sequences={selectableSequences}
                selectedId={selectedCampaignId}
                onSelect={setSelectedCampaignId}
              />
            </div>
          )}

          {/* Stats - sequences view only */}
          {viewMode === 'sequences' && (
            <div className="flex items-center gap-4 mt-4 text-sm">
              <Badge variant="outline" className="bg-yellow-50">
                {counts.pending} Pending
              </Badge>
              <Badge variant="outline" className="bg-green-50">
                {counts.approved} Approved
              </Badge>
              <Badge variant="outline" className="bg-red-50">
                {counts.denied} Denied
              </Badge>
              <Badge variant="outline" className="bg-orange-50">
                {counts.revision} Revisions
              </Badge>
            </div>
          )}
        </CardHeader>
      </Card>

      {/* Document View */}
      {viewMode === 'documents' && (
        <CampaignDocumentView clientId={clientId} />
      )}

      {/* Sequences View */}
      {viewMode === 'sequences' && (
        <>
          {/* Loading state */}
          {loading && (
        <Card>
          <CardContent className="flex items-center justify-center py-12">
            <Loader2 className="w-6 h-6 animate-spin text-muted-foreground" />
            <span className="ml-2 text-muted-foreground">Loading sequences...</span>
          </CardContent>
        </Card>
      )}

      {/* Generation in progress state */}
      {generating && generationStatus && (
        <Card className="border-blue-200 bg-blue-50/50">
          <CardContent className="py-8">
            <div className="flex flex-col items-center justify-center text-center">
              <div className="relative mb-4">
                <div className="w-16 h-16 rounded-full bg-blue-100 flex items-center justify-center">
                  <Sparkles className="w-8 h-8 text-blue-600 animate-pulse" />
                </div>
                <div className="absolute -bottom-1 -right-1 w-6 h-6 rounded-full bg-white flex items-center justify-center shadow-sm">
                  <Loader2 className="w-4 h-4 animate-spin text-blue-600" />
                </div>
              </div>
              <h3 className="font-semibold text-lg text-blue-900 mb-1">
                Generating 4 Campaign Sequences
              </h3>
              <p className="text-sm text-blue-700 mb-3">
                Round {generationStatus.round} • Strategy AI is crafting your campaigns
              </p>
              <div className="flex items-center gap-2 text-xs text-blue-600">
                <Badge variant="outline" className="bg-white border-blue-200">
                  Job: {generationStatus.jobId.slice(0, 8)}...
                </Badge>
                <Badge variant="outline" className="bg-white border-blue-200 capitalize">
                  Status: {generationStatus.status}
                </Badge>
              </div>
              <p className="text-xs text-blue-500 mt-4">
                This typically takes 1-3 minutes. You can leave this page and return later.
              </p>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Empty state */}
      {!loading && !generating && sequences.length === 0 && (
        <Card>
          <CardContent className="text-center py-12">
            <Sparkles className="w-12 h-12 mx-auto text-muted-foreground mb-4" />
            <h3 className="font-medium mb-2">No campaign sequences yet</h3>
            <p className="text-sm text-muted-foreground mb-4">
              Generate AI-powered 4-email campaign sequences
            </p>
            <Button onClick={handleGenerate} disabled={generating}>
              {generating ? (
                <Loader2 className="w-4 h-4 mr-2 animate-spin" />
              ) : (
                <Sparkles className="w-4 h-4 mr-2" />
              )}
              Generate Sequences
            </Button>
          </CardContent>
        </Card>
      )}

      {/* Selected campaign detail */}
      {!loading && !generating && selectedCampaign && (
        <SelectedCampaignDetail
          sequence={selectedCampaign}
          onApprove={async () => handleApprove(selectedCampaign.id)}
          onDeny={async () => handleDeny(selectedCampaign.id)}
          onSpintax={async () => handleSpintax(selectedCampaign.id)}
          onPushToEmailBison={async () => handlePushToEmailBison(selectedCampaign.id)}
          onEditEmail={(pos) => handleEditEmail(selectedCampaign.id, pos)}
          onRequestRevision={(pos) => handleRequestRevision(selectedCampaign.id, pos)}
        />
      )}

      {/* No campaign selected state */}
      {!loading && !generating && sequences.length > 0 && !selectedCampaign && (
        <Card>
          <CardContent className="text-center py-12">
            <Sparkles className="w-12 h-12 mx-auto text-muted-foreground mb-4" />
            <h3 className="font-medium mb-2">Select a campaign</h3>
            <p className="text-sm text-muted-foreground">
              Choose a campaign from the dropdown above to view and configure it
            </p>
          </CardContent>
        </Card>
      )}

      {/* Edit Email Modal */}
      <Dialog open={!!editingEmail} onOpenChange={() => setEditingEmail(null)}>
        <DialogContent className="max-w-2xl">
          <DialogHeader>
            <DialogTitle>
              Edit Email {editingEmail?.position}
              {editingEmail?.position === 2 || editingEmail?.position === 4
                ? ' (Threaded Reply)'
                : ''}
            </DialogTitle>
            <DialogDescription>
              Make changes to this email. Your edits will be saved separately from the original.
            </DialogDescription>
          </DialogHeader>

          <div className="space-y-4">
            {/* Subject line (only for Email 1 and 3) */}
            {editingEmail && (editingEmail.position === 1 || editingEmail.position === 3) && (
              <div>
                <Label htmlFor="subject">Subject Line</Label>
                <Input
                  id="subject"
                  value={editingEmail.subjectLine}
                  onChange={(e) =>
                    setEditingEmail({ ...editingEmail, subjectLine: e.target.value })
                  }
                  placeholder="Enter subject line..."
                />
              </div>
            )}

            {/* Email body */}
            <div>
              <Label htmlFor="body">Email Body</Label>
              <Textarea
                id="body"
                value={editingEmail?.emailBody || ''}
                onChange={(e) =>
                  editingEmail && setEditingEmail({ ...editingEmail, emailBody: e.target.value })
                }
                rows={10}
                className="font-mono text-sm"
              />
              <p className="text-xs text-muted-foreground mt-1">
                Word count:{' '}
                {editingEmail?.emailBody.split(/\s+/).filter(Boolean).length || 0}
              </p>
            </div>
          </div>

          <DialogFooter>
            <Button variant="outline" onClick={() => setEditingEmail(null)}>
              Cancel
            </Button>
            <Button onClick={handleSaveEdit}>Save Changes</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Revision Request Modal */}
      <Dialog open={!!revisionRequest} onOpenChange={() => setRevisionRequest(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>
              Request Revision
              {revisionRequest?.emailPosition
                ? ` - Email ${revisionRequest.emailPosition}`
                : ' - Entire Sequence'}
            </DialogTitle>
            <DialogDescription>
              Provide instructions for how you&apos;d like this to be revised.
            </DialogDescription>
          </DialogHeader>

          <div className="space-y-4">
            <div>
              <Label htmlFor="instruction">What would you like changed?</Label>
              <Textarea
                id="instruction"
                value={revisionRequest?.instruction || ''}
                onChange={(e) =>
                  revisionRequest &&
                  setRevisionRequest({ ...revisionRequest, instruction: e.target.value })
                }
                placeholder="E.g., Make the opening more direct, include a specific case study..."
                rows={4}
              />
            </div>

            {revisionRequest?.emailPosition && revisionRequest.emailPosition > 0 && (
              <div>
                <Label>Revision applies to:</Label>
                <div className="space-y-2 mt-2">
                  {(['single', 'subsequent', 'all'] as const).map((scope) => (
                    <label key={scope} className="flex items-center gap-2 text-sm">
                      <input
                        type="radio"
                        name="scope"
                        checked={revisionRequest.scope === scope}
                        onChange={() => setRevisionRequest({ ...revisionRequest, scope })}
                      />
                      {scope === 'single' && `Just Email ${revisionRequest.emailPosition}`}
                      {scope === 'subsequent' &&
                        `Email ${revisionRequest.emailPosition} and all subsequent`}
                      {scope === 'all' && 'Entire sequence (regenerate all 4)'}
                    </label>
                  ))}
                </div>
              </div>
            )}
          </div>

          <DialogFooter>
            <Button variant="outline" onClick={() => setRevisionRequest(null)}>
              Cancel
            </Button>
            <Button onClick={handleSubmitRevision}>Submit Revision Request</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
      </>
      )}
    </div>
  );
}
