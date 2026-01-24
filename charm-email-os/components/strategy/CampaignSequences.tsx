'use client';

import { useState, useEffect, useCallback } from 'react';
import { RefreshCw, Sparkles, Filter, Loader2 } from 'lucide-react';
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
import { CampaignSequenceCard } from './CampaignSequenceCard';
import { StrategySelector } from './StrategySelector';
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
  const [sequences, setSequences] = useState<CampaignSequence[]>([]);
  const [loading, setLoading] = useState(true);
  const [generating, setGenerating] = useState(false);
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

  // Generate more sequences
  const handleGenerate = async () => {
    setGenerating(true);
    try {
      const job = await strategyApi.createJob(
        clientId,
        undefined,
        selectedStrategyId || undefined
      );
      toast.success(`Generation job started (Round ${job.generationRound})`);

      // Poll for completion
      let attempts = 0;
      const maxAttempts = 60; // 5 minutes with 5s intervals
      const pollInterval = setInterval(async () => {
        attempts++;
        try {
          const status = await strategyApi.getJobStatus(job.jobId);
          if (status.status === 'review' || status.status === 'completed') {
            clearInterval(pollInterval);
            toast.success('New sequences generated!');
            fetchSequences();
            setGenerating(false);
          } else if (status.status === 'failed') {
            clearInterval(pollInterval);
            toast.error(`Generation failed: ${status.errorMessage || 'Unknown error'}`);
            setGenerating(false);
          } else if (attempts >= maxAttempts) {
            clearInterval(pollInterval);
            toast.error('Generation timed out. Check job status manually.');
            setGenerating(false);
          }
        } catch {
          // Ignore polling errors
        }
      }, 5000);
    } catch (error) {
      console.error('Failed to start generation:', error);
      toast.error('Failed to start generation');
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

  // Filtered sequences for display
  const activeSequences = sequences.filter((s) => s.status !== 'denied');
  const deniedSequences = sequences.filter((s) => s.status === 'denied');

  return (
    <div className={cn('space-y-4', className)}>
      {/* Header Card */}
      <Card>
        <CardHeader className="pb-3">
          <div className="flex items-center justify-between">
            <div>
              <CardTitle className="text-lg">Campaign Sequences</CardTitle>
              <CardDescription>
                4-email campaign sequences generated by Strategy-AI
              </CardDescription>
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

          {/* Filters */}
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

          {/* Stats */}
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
        </CardHeader>
      </Card>

      {/* Loading state */}
      {loading && (
        <Card>
          <CardContent className="flex items-center justify-center py-12">
            <Loader2 className="w-6 h-6 animate-spin text-muted-foreground" />
            <span className="ml-2 text-muted-foreground">Loading sequences...</span>
          </CardContent>
        </Card>
      )}

      {/* Empty state */}
      {!loading && sequences.length === 0 && (
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

      {/* Active sequences */}
      {!loading && activeSequences.length > 0 && (
        <div className="space-y-3">
          {activeSequences.map((sequence) => (
            <CampaignSequenceCard
              key={sequence.id}
              sequence={sequence}
              onApprove={handleApprove}
              onDeny={handleDeny}
              onEditEmail={handleEditEmail}
              onRequestRevision={handleRequestRevision}
              onSpintax={handleSpintax}
              onPushToEmailBison={handlePushToEmailBison}
            />
          ))}
        </div>
      )}

      {/* Denied sequences (collapsible) */}
      {!loading && deniedSequences.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle className="text-sm font-medium text-muted-foreground">
              Denied Sequences ({deniedSequences.length})
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            {deniedSequences.map((sequence) => (
              <CampaignSequenceCard key={sequence.id} sequence={sequence} />
            ))}
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
    </div>
  );
}
