'use client';

import { useState, useEffect } from 'react';
import {
  FileText,
  Calendar,
  Eye,
  Pencil,
  Zap,
  Star,
  ExternalLink,
  Loader2,
} from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { onboardingApi, strategyApi, type OnboardingSubmission } from '@/lib/api';
import { toast } from 'sonner';
import { OnboardingEditModal } from '@/components/strategy/OnboardingEditModal';

interface SubmissionsListProps {
  clientId: string;
}

function formatDate(dateString?: string) {
  if (!dateString) return 'N/A';
  return new Date(dateString).toLocaleDateString('en-US', {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
  });
}

function SubmissionViewModal({
  submission,
  open,
  onOpenChange,
}: {
  submission: OnboardingSubmission | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  if (!submission) return null;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl max-h-[80vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <FileText className="h-5 w-5" />
            Onboarding Submission
          </DialogTitle>
        </DialogHeader>

        <div className="space-y-4">
          {/* Foundation */}
          <div className="space-y-2">
            <h4 className="font-medium text-sm">Foundation</h4>
            <div className="grid grid-cols-2 gap-2 text-sm">
              <div>
                <span className="text-muted-foreground">Company:</span>{' '}
                {submission.companyName}
              </div>
              {submission.website && (
                <div>
                  <span className="text-muted-foreground">Website:</span>{' '}
                  {submission.website}
                </div>
              )}
              {submission.contactName && (
                <div>
                  <span className="text-muted-foreground">Contact:</span>{' '}
                  {submission.contactName}
                </div>
              )}
              {submission.contactEmail && (
                <div>
                  <span className="text-muted-foreground">Email:</span>{' '}
                  {submission.contactEmail}
                </div>
              )}
            </div>
          </div>

          {/* Offering */}
          {submission.coreProduct && (
            <div className="space-y-2">
              <h4 className="font-medium text-sm">Offering</h4>
              <p className="text-sm">{submission.coreProduct}</p>
              {submission.targetCustomer && (
                <p className="text-sm text-muted-foreground">
                  Target: {submission.targetCustomer}
                </p>
              )}
            </div>
          )}

          {/* Signals */}
          {submission.signals && submission.signals.length > 0 && (
            <div className="space-y-2">
              <h4 className="font-medium text-sm">Buying Signals</h4>
              <div className="flex flex-wrap gap-1">
                {submission.signals.map((signal) => (
                  <Badge key={signal} variant="secondary" className="text-xs">
                    {signal}
                  </Badge>
                ))}
              </div>
            </div>
          )}

          {/* Job Titles */}
          {submission.jobTitles && submission.jobTitles.length > 0 && (
            <div className="space-y-2">
              <h4 className="font-medium text-sm">Target Job Titles</h4>
              <div className="flex flex-wrap gap-1">
                {submission.jobTitles.map((title) => (
                  <Badge key={title} variant="outline" className="text-xs">
                    {title}
                  </Badge>
                ))}
              </div>
            </div>
          )}

          {/* Segments */}
          {submission.segments && submission.segments.length > 0 && (
            <div className="space-y-2">
              <h4 className="font-medium text-sm">Customer Segments</h4>
              <div className="space-y-1">
                {submission.segments.map((segment, i) => (
                  <div key={segment.id || i} className="text-sm">
                    <span className="font-medium">{segment.segmentName}</span>
                    <span className="text-muted-foreground">
                      {' '}
                      ({segment.revenuePercentage}% revenue)
                    </span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Personas */}
          {submission.personas && submission.personas.length > 0 && (
            <div className="space-y-2">
              <h4 className="font-medium text-sm">Buyer Personas</h4>
              <div className="space-y-1">
                {submission.personas.map((persona, i) => (
                  <div key={persona.id || i} className="text-sm">
                    <span className="font-medium">{persona.jobTitle}</span>
                    {persona.seniorityLevel && (
                      <span className="text-muted-foreground">
                        {' '}
                        - {persona.seniorityLevel}
                      </span>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Messaging */}
          {(submission.customerVoice || submission.roiResults) && (
            <div className="space-y-2">
              <h4 className="font-medium text-sm">Messaging</h4>
              {submission.customerVoice && (
                <div className="text-sm">
                  <span className="text-muted-foreground">Voice:</span>{' '}
                  {submission.customerVoice}
                </div>
              )}
              {submission.roiResults && (
                <div className="text-sm">
                  <span className="text-muted-foreground">ROI/Results:</span>{' '}
                  {submission.roiResults}
                </div>
              )}
            </div>
          )}

          {/* Metadata */}
          <div className="pt-4 border-t text-xs text-muted-foreground">
            <div className="flex items-center gap-2">
              <Calendar className="h-3 w-3" />
              <span>
                Created: {formatDate(submission.createdAt)}
                {submission.updatedAt &&
                  submission.updatedAt !== submission.createdAt && (
                    <> | Updated: {formatDate(submission.updatedAt)}</>
                  )}
              </span>
            </div>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}

export function SubmissionsList({ clientId }: SubmissionsListProps) {
  const [submissions, setSubmissions] = useState<OnboardingSubmission[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [activeSubmissionId, setActiveSubmissionId] = useState<string | null>(null);
  const [viewingSubmission, setViewingSubmission] = useState<OnboardingSubmission | null>(null);
  const [editingSubmission, setEditingSubmission] = useState<OnboardingSubmission | null>(null);
  const [triggeringId, setTriggeringId] = useState<string | null>(null);

  useEffect(() => {
    async function fetchSubmissions() {
      try {
        setLoading(true);
        const response = await onboardingApi.getSubmissions(clientId);
        setSubmissions(response.submissions);
        // Set the first submission as active by default
        if (response.submissions.length > 0) {
          setActiveSubmissionId(response.submissions[0].id);
        }
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Failed to load submissions');
      } finally {
        setLoading(false);
      }
    }

    fetchSubmissions();
  }, [clientId]);

  const handleTriggerGeneration = async (submissionId: string) => {
    setTriggeringId(submissionId);
    try {
      const response = await strategyApi.createJob(clientId, submissionId);
      toast.success(`Strategy generation started (Round ${response.generationRound})`);
      // Note: The CampaignSuggestions component on the Strategy tab will poll for results
    } catch (err) {
      console.error('Failed to trigger generation:', err);
      toast.error(err instanceof Error ? err.message : 'Failed to start generation');
    } finally {
      setTriggeringId(null);
    }
  };

  const handleSetActive = (submissionId: string) => {
    setActiveSubmissionId(submissionId);
  };

  if (loading) {
    return (
      <Card>
        <CardHeader>
          <CardTitle className="text-base font-semibold flex items-center gap-2">
            <FileText className="h-4 w-4" />
            Onboarding Submissions
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="flex items-center justify-center py-8">
            <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
          </div>
        </CardContent>
      </Card>
    );
  }

  if (error) {
    return (
      <Card>
        <CardHeader>
          <CardTitle className="text-base font-semibold flex items-center gap-2">
            <FileText className="h-4 w-4" />
            Onboarding Submissions
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="text-center py-8 text-muted-foreground">{error}</div>
        </CardContent>
      </Card>
    );
  }

  if (submissions.length === 0) {
    return (
      <Card>
        <CardHeader>
          <CardTitle className="text-base font-semibold flex items-center gap-2">
            <FileText className="h-4 w-4" />
            Onboarding Submissions
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="text-center py-8">
            <FileText className="h-10 w-10 mx-auto mb-3 text-muted-foreground opacity-50" />
            <p className="font-medium text-muted-foreground mb-2">
              No onboarding forms submitted yet
            </p>
            <p className="text-sm text-muted-foreground mb-4">
              Send the client the onboarding form to collect detailed context for strategy generation.
            </p>
            <Button variant="outline" asChild>
              <a
                href={`https://onboard.laviefatigue.com?client_id=${clientId}`}
                target="_blank"
                rel="noopener noreferrer"
              >
                <ExternalLink className="h-4 w-4 mr-2" />
                Open Onboarding Form
              </a>
            </Button>
          </div>
        </CardContent>
      </Card>
    );
  }

  return (
    <>
      <Card>
        <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-4">
          <CardTitle className="text-base font-semibold flex items-center gap-2">
            <FileText className="h-4 w-4" />
            Onboarding Submissions
          </CardTitle>
          <Button variant="outline" size="sm" asChild>
            <a
              href={`https://onboard.laviefatigue.com?client_id=${clientId}`}
              target="_blank"
              rel="noopener noreferrer"
            >
              <ExternalLink className="h-4 w-4 mr-1" />
              New Form
            </a>
          </Button>
        </CardHeader>
        <CardContent>
          <div className="space-y-3">
            {submissions.map((submission) => (
              <div
                key={submission.id}
                className={`flex items-center justify-between p-3 rounded-lg border ${
                  activeSubmissionId === submission.id
                    ? 'border-primary bg-primary/5'
                    : 'border-border'
                }`}
              >
                <div className="flex items-center gap-3">
                  {activeSubmissionId === submission.id ? (
                    <Star className="h-4 w-4 text-primary fill-primary" />
                  ) : (
                    <button
                      onClick={() => handleSetActive(submission.id)}
                      className="text-muted-foreground hover:text-primary transition-colors"
                      title="Set as active submission"
                    >
                      <Star className="h-4 w-4" />
                    </button>
                  )}
                  <div>
                    <div className="flex items-center gap-2">
                      <span className="font-medium text-sm">
                        {formatDate(submission.submittedAt || submission.createdAt)}
                      </span>
                      <Badge
                        variant={
                          submission.submissionStatus === 'completed'
                            ? 'default'
                            : 'secondary'
                        }
                        className="text-xs"
                      >
                        {submission.submissionStatus}
                      </Badge>
                      {activeSubmissionId === submission.id && (
                        <Badge variant="outline" className="text-xs">
                          Active
                        </Badge>
                      )}
                    </div>
                    <p className="text-xs text-muted-foreground mt-0.5">
                      {submission.companyName}
                      {submission.coreProduct && ` - ${submission.coreProduct.substring(0, 50)}...`}
                    </p>
                  </div>
                </div>

                <div className="flex items-center gap-2">
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => setViewingSubmission(submission)}
                    title="View submission"
                  >
                    <Eye className="h-4 w-4" />
                  </Button>
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => setEditingSubmission(submission)}
                    title="Edit submission"
                  >
                    <Pencil className="h-4 w-4" />
                  </Button>
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => handleTriggerGeneration(submission.id)}
                    disabled={triggeringId === submission.id}
                    title="Trigger strategy generation"
                  >
                    {triggeringId === submission.id ? (
                      <Loader2 className="h-4 w-4 animate-spin" />
                    ) : (
                      <Zap className="h-4 w-4" />
                    )}
                    <span className="ml-1">Generate</span>
                  </Button>
                </div>
              </div>
            ))}
          </div>
        </CardContent>
      </Card>

      {/* View Modal */}
      <SubmissionViewModal
        submission={viewingSubmission}
        open={!!viewingSubmission}
        onOpenChange={(open) => !open && setViewingSubmission(null)}
      />

      {/* Edit Modal */}
      {editingSubmission && (
        <OnboardingEditModal
          submission={editingSubmission}
          open={!!editingSubmission}
          onOpenChange={(open) => !open && setEditingSubmission(null)}
          onSave={(updated) => {
            setSubmissions((prev) =>
              prev.map((s) => (s.id === updated.id ? updated : s))
            );
            setEditingSubmission(null);
          }}
        />
      )}
    </>
  );
}
