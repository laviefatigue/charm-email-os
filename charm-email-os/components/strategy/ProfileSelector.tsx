'use client';

import { useState, useEffect } from 'react';
import { Check, ChevronDown, FileText, Plus, Calendar, Building2 } from 'lucide-react';
import { cn } from '@/lib/utils';
import { Button } from '@/components/ui/button';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
  DropdownMenuSeparator,
} from '@/components/ui/dropdown-menu';
import { Badge } from '@/components/ui/badge';
import { onboardingApi, type OnboardingSubmission } from '@/lib/api';

interface ProfileSelectorProps {
  clientId: string;
  selectedSubmissionId: string | null;
  onSelect: (submissionId: string) => void;
  onCreateNew?: () => void;
}

function formatDate(dateString?: string) {
  if (!dateString) return '';
  return new Date(dateString).toLocaleDateString('en-US', {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
  });
}

function getStatusBadge(status?: string) {
  switch (status) {
    case 'submitted':
      return <Badge variant="default" className="text-xs">Submitted</Badge>;
    case 'draft':
      return <Badge variant="secondary" className="text-xs">Draft</Badge>;
    case 'approved':
      return <Badge variant="outline" className="text-xs bg-green-50 text-green-700 border-green-200">Approved</Badge>;
    default:
      return <Badge variant="secondary" className="text-xs">{status || 'Unknown'}</Badge>;
  }
}

export function ProfileSelector({
  clientId,
  selectedSubmissionId,
  onSelect,
  onCreateNew,
}: ProfileSelectorProps) {
  const [submissions, setSubmissions] = useState<OnboardingSubmission[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    async function fetchSubmissions() {
      try {
        setLoading(true);
        const response = await onboardingApi.getSubmissions(clientId);
        setSubmissions(response.submissions);

        // Auto-select the most recent if none selected
        if (!selectedSubmissionId && response.submissions.length > 0) {
          onSelect(response.submissions[0].id);
        }
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Failed to load profiles');
      } finally {
        setLoading(false);
      }
    }

    fetchSubmissions();
  }, [clientId, selectedSubmissionId, onSelect]);

  if (loading) {
    return (
      <div className="flex items-center gap-2 text-sm text-muted-foreground">
        <div className="h-4 w-4 animate-spin rounded-full border-2 border-primary border-t-transparent" />
        Loading profiles...
      </div>
    );
  }

  if (error) {
    return (
      <div className="text-sm text-destructive">
        {error}
      </div>
    );
  }

  if (submissions.length === 0) {
    return (
      <div className="flex items-center gap-3">
        <div className="flex items-center gap-2 text-sm text-muted-foreground">
          <FileText className="h-4 w-4" />
          No profiles found
        </div>
        {onCreateNew && (
          <Button variant="outline" size="sm" onClick={onCreateNew}>
            <Plus className="h-4 w-4 mr-1" />
            Create Profile
          </Button>
        )}
      </div>
    );
  }

  const selectedSubmission = submissions.find(s => s.id === selectedSubmissionId);

  return (
    <div className="flex items-center gap-3">
      <span className="text-sm font-medium text-muted-foreground">Profile:</span>

      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <Button variant="outline" className="min-w-[280px] justify-between">
            <div className="flex items-center gap-2 truncate">
              <Building2 className="h-4 w-4 text-muted-foreground shrink-0" />
              {selectedSubmission ? (
                <span className="truncate">
                  {selectedSubmission.companyName}
                  <span className="text-muted-foreground ml-2 text-xs">
                    {formatDate(selectedSubmission.submittedAt || selectedSubmission.createdAt)}
                  </span>
                </span>
              ) : (
                <span className="text-muted-foreground">Select a profile</span>
              )}
            </div>
            <ChevronDown className="h-4 w-4 ml-2 shrink-0" />
          </Button>
        </DropdownMenuTrigger>

        <DropdownMenuContent align="start" className="w-[320px]">
          {submissions.map((submission) => (
            <DropdownMenuItem
              key={submission.id}
              onClick={() => onSelect(submission.id)}
              className={cn(
                'flex items-center justify-between gap-2 cursor-pointer',
                selectedSubmissionId === submission.id && 'bg-accent'
              )}
            >
              <div className="flex flex-col gap-0.5 min-w-0">
                <div className="flex items-center gap-2">
                  <span className="font-medium truncate">{submission.companyName}</span>
                  {getStatusBadge(submission.submissionStatus)}
                </div>
                <div className="flex items-center gap-2 text-xs text-muted-foreground">
                  <Calendar className="h-3 w-3" />
                  {formatDate(submission.submittedAt || submission.createdAt)}
                  {(submission as { industry?: string }).industry && (
                    <>
                      <span className="text-muted-foreground/50">•</span>
                      {(submission as { industry?: string }).industry}
                    </>
                  )}
                </div>
              </div>
              {selectedSubmissionId === submission.id && (
                <Check className="h-4 w-4 text-primary shrink-0" />
              )}
            </DropdownMenuItem>
          ))}

          {onCreateNew && (
            <>
              <DropdownMenuSeparator />
              <DropdownMenuItem onClick={onCreateNew} className="cursor-pointer">
                <Plus className="h-4 w-4 mr-2" />
                Create New Profile
              </DropdownMenuItem>
            </>
          )}
        </DropdownMenuContent>
      </DropdownMenu>

      <span className="text-xs text-muted-foreground">
        {submissions.length} profile{submissions.length !== 1 ? 's' : ''} available
      </span>
    </div>
  );
}
