'use client';

import { useState } from 'react';
import { type StrategySuggestion } from '@/lib/api';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import {
  ChevronDown,
  ChevronRight,
  CheckCircle2,
  XCircle,
  MessageSquare,
  Edit,
  Copy,
  Check,
  Send,
  Loader2,
  History,
  GitBranch,
} from 'lucide-react';

interface RevisionTreeProps {
  /** The latest/current suggestion in the chain */
  latestSuggestion: StrategySuggestion;
  /** Previous revisions ordered from newest to oldest */
  revisions: StrategySuggestion[];
  /** Handlers from parent */
  onEdit: (suggestion: StrategySuggestion) => void;
  onApprove: (id: string) => void;
  onDeny: (id: string) => void;
  onRequestRevision: (suggestion: StrategySuggestion) => void;
  onPushToEmailBison: (id: string) => void;
  onCopy: (text: string, id: string) => void;
  /** Loading states */
  pushingId: string | null;
  copiedId: string | null;
}

export function RevisionTree({
  latestSuggestion,
  revisions,
  onEdit,
  onApprove,
  onDeny,
  onRequestRevision,
  onPushToEmailBison,
  onCopy,
  pushingId,
  copiedId,
}: RevisionTreeProps) {
  const [expanded, setExpanded] = useState(false);
  const hasRevisions = revisions.length > 0;

  // Display edited content if exists
  const displaySubject = latestSuggestion.editedSubjectLine || latestSuggestion.subjectLine;
  const displayBody = latestSuggestion.editedEmailBody || latestSuggestion.emailBody;
  const isEdited = latestSuggestion.editedSubjectLine || latestSuggestion.editedEmailBody;

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

  const renderHistoryItem = (suggestion: StrategySuggestion, index: number) => {
    const historySubject = suggestion.editedSubjectLine || suggestion.subjectLine;
    const historyBody = suggestion.editedEmailBody || suggestion.emailBody;

    return (
      <div
        key={suggestion.id}
        className="ml-6 pl-4 border-l-2 border-muted-foreground/30 py-2"
      >
        <div className="bg-muted/50 rounded-lg p-4">
          <div className="flex items-center gap-2 mb-2">
            <Badge variant="outline" className="text-xs">
              V{suggestion.variantNumber}
            </Badge>
            {getStatusBadge(suggestion.status)}
            {suggestion.score !== undefined && (
              <span className={`font-mono text-xs ${getScoreColor(suggestion.score)}`}>
                Score: {suggestion.score}
              </span>
            )}
            <span className="text-xs text-muted-foreground ml-auto">
              {new Date(suggestion.createdAt).toLocaleDateString()}
            </span>
          </div>

          <div className="text-sm mb-2">
            <span className="font-mono text-muted-foreground text-xs">Subject:</span>{' '}
            <span className="text-sm">{historySubject}</span>
          </div>

          {/* Show revision instruction if this was a revision request */}
          {suggestion.humanComment && (
            <div className="text-xs bg-yellow-50 dark:bg-yellow-900/20 p-2 rounded border border-yellow-200 dark:border-yellow-800 mb-2">
              <span className="font-medium">Revision feedback:</span> {suggestion.humanComment}
            </div>
          )}

          <details className="text-xs">
            <summary className="cursor-pointer text-muted-foreground hover:text-foreground">
              View email body
            </summary>
            <pre className="whitespace-pre-wrap mt-2 p-2 bg-background rounded text-xs max-h-40 overflow-y-auto">
              {historyBody}
            </pre>
          </details>

          <div className="flex gap-2 mt-2">
            <Button
              variant="ghost"
              size="sm"
              className="h-7 text-xs"
              onClick={() => onCopy(historyBody, `${suggestion.id}-history-body`)}
            >
              {copiedId === `${suggestion.id}-history-body` ? (
                <Check className="h-3 w-3 mr-1 text-green-500" />
              ) : (
                <Copy className="h-3 w-3 mr-1" />
              )}
              Copy
            </Button>
          </div>
        </div>
      </div>
    );
  };

  return (
    <Card className="overflow-hidden">
      <CardHeader className="pb-2">
        <div className="flex items-start justify-between">
          <div className="flex-1">
            <div className="flex items-center gap-2 mb-1 flex-wrap">
              <Badge variant="outline">V{latestSuggestion.variantNumber}</Badge>
              {getStatusBadge(latestSuggestion.status)}
              {latestSuggestion.campaignType && (
                <Badge variant="secondary">{latestSuggestion.campaignType}</Badge>
              )}
              {latestSuggestion.score !== undefined && (
                <span className={`font-mono text-sm ${getScoreColor(latestSuggestion.score)}`}>
                  Score: {latestSuggestion.score}
                </span>
              )}
              {isEdited && (
                <Badge variant="outline" className="text-blue-600 border-blue-200">
                  Edited
                </Badge>
              )}
              {latestSuggestion.pushedToEmailbison && (
                <Badge variant="outline" className="text-purple-600 border-purple-200">
                  Pushed
                </Badge>
              )}
              {hasRevisions && (
                <Badge
                  variant="outline"
                  className="text-orange-600 border-orange-200 cursor-pointer hover:bg-orange-50"
                  onClick={() => setExpanded(!expanded)}
                >
                  <GitBranch className="h-3 w-3 mr-1" />
                  {revisions.length} revision{revisions.length > 1 ? 's' : ''}
                </Badge>
              )}
            </div>
            <CardTitle className="text-base flex items-center gap-2">
              <span className="font-mono text-muted-foreground">Subject:</span>
              {displaySubject}
              <Button
                variant="ghost"
                size="sm"
                className="h-6 w-6 p-0"
                onClick={() => onCopy(displaySubject, `${latestSuggestion.id}-subject`)}
              >
                {copiedId === `${latestSuggestion.id}-subject` ? (
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
        {/* Email body */}
        <div className="relative">
          <pre className="whitespace-pre-wrap text-sm bg-muted p-4 rounded-lg font-sans">
            {displayBody}
          </pre>
          <Button
            variant="ghost"
            size="sm"
            className="absolute top-2 right-2 h-8 w-8 p-0"
            onClick={() => onCopy(displayBody, `${latestSuggestion.id}-body`)}
          >
            {copiedId === `${latestSuggestion.id}-body` ? (
              <Check className="h-4 w-4 text-green-500" />
            ) : (
              <Copy className="h-4 w-4" />
            )}
          </Button>
        </div>

        {/* Rationale */}
        {latestSuggestion.rationale && (
          <div className="text-sm text-muted-foreground border-l-2 border-blue-200 pl-3">
            <span className="font-medium">Rationale:</span> {latestSuggestion.rationale}
          </div>
        )}

        {/* Variables */}
        {latestSuggestion.usedVariables && latestSuggestion.usedVariables.length > 0 && (
          <div className="flex flex-wrap gap-1">
            <span className="text-xs text-muted-foreground mr-1">Variables:</span>
            {latestSuggestion.usedVariables.map((v, i) => (
              <Badge key={i} variant="outline" className="text-xs font-mono">
                {v}
              </Badge>
            ))}
          </div>
        )}

        {/* Human comment on latest */}
        {latestSuggestion.humanComment && (
          <div className="text-sm bg-yellow-50 dark:bg-yellow-900/20 p-3 rounded border border-yellow-200 dark:border-yellow-800">
            <span className="font-medium">Human Feedback:</span> {latestSuggestion.humanComment}
          </div>
        )}

        {/* Action buttons for latest */}
        <div className="flex gap-2 pt-2 border-t flex-wrap">
          {/* Edit button - always available */}
          <Button
            variant="outline"
            size="sm"
            onClick={() => onEdit(latestSuggestion)}
          >
            <Edit className="h-4 w-4 mr-1" />
            Edit
          </Button>

          {/* Pending-only actions */}
          {latestSuggestion.status === 'pending' && (
            <>
              <Button
                variant="outline"
                size="sm"
                className="text-green-600 border-green-200 hover:bg-green-50"
                onClick={() => onApprove(latestSuggestion.id)}
              >
                <CheckCircle2 className="h-4 w-4 mr-1" />
                Approve
              </Button>
              <Button
                variant="outline"
                size="sm"
                className="text-red-600 border-red-200 hover:bg-red-50"
                onClick={() => onDeny(latestSuggestion.id)}
              >
                <XCircle className="h-4 w-4 mr-1" />
                Deny
              </Button>
              <Button
                variant="outline"
                size="sm"
                onClick={() => onRequestRevision(latestSuggestion)}
              >
                <MessageSquare className="h-4 w-4 mr-1" />
                Request Revision
              </Button>
            </>
          )}

          {/* Approved-only: Push to EmailBison */}
          {latestSuggestion.status === 'approved' && !latestSuggestion.pushedToEmailbison && (
            <Button
              variant="outline"
              size="sm"
              className="text-purple-600 border-purple-200 hover:bg-purple-50"
              onClick={() => onPushToEmailBison(latestSuggestion.id)}
              disabled={pushingId === latestSuggestion.id}
            >
              {pushingId === latestSuggestion.id ? (
                <>
                  <Loader2 className="h-4 w-4 mr-1 animate-spin" />
                  Pushing...
                </>
              ) : (
                <>
                  <Send className="h-4 w-4 mr-1" />
                  Push to EmailBison
                </>
              )}
            </Button>
          )}

          {/* Toggle history button */}
          {hasRevisions && (
            <Button
              variant="ghost"
              size="sm"
              onClick={() => setExpanded(!expanded)}
              className="ml-auto"
            >
              {expanded ? (
                <>
                  <ChevronDown className="h-4 w-4 mr-1" />
                  Hide History
                </>
              ) : (
                <>
                  <History className="h-4 w-4 mr-1" />
                  Show History
                </>
              )}
            </Button>
          )}
        </div>

        {/* Revision History (collapsible) */}
        {expanded && hasRevisions && (
          <div className="border-t pt-4 mt-2">
            <div className="text-sm font-medium text-muted-foreground mb-2 flex items-center gap-2">
              <History className="h-4 w-4" />
              Revision History
            </div>
            {revisions.map((rev, idx) => renderHistoryItem(rev, idx))}
          </div>
        )}
      </CardContent>
    </Card>
  );
}

/**
 * Utility function to group suggestions by revision chains
 * Returns Map where key is the root suggestion ID and value is array of all versions
 */
export function groupByRevisionChain(suggestions: StrategySuggestion[]): Map<string, StrategySuggestion[]> {
  const chains = new Map<string, StrategySuggestion[]>();
  const processed = new Set<string>();

  // Build a map of original -> revisions
  const revisionMap = new Map<string, StrategySuggestion[]>();
  suggestions.forEach(s => {
    if (s.originalSuggestionId) {
      const existing = revisionMap.get(s.originalSuggestionId) || [];
      existing.push(s);
      revisionMap.set(s.originalSuggestionId, existing);
    }
  });

  // Find all revisions for a root suggestion (recursively)
  const findAllRevisions = (rootId: string): StrategySuggestion[] => {
    const revisions: StrategySuggestion[] = [];
    const directRevisions = revisionMap.get(rootId) || [];

    for (const rev of directRevisions) {
      revisions.push(rev);
      // Recursively find revisions of revisions
      revisions.push(...findAllRevisions(rev.id));
    }

    return revisions;
  };

  // Process each suggestion
  suggestions.forEach(suggestion => {
    if (processed.has(suggestion.id)) return;

    // If this is a revision, find its root
    if (suggestion.originalSuggestionId) {
      // Skip - will be processed with its root
      return;
    }

    // This is a root suggestion
    const allRevisions = findAllRevisions(suggestion.id);

    // Sort revisions by date (newest first for display)
    allRevisions.sort((a, b) =>
      new Date(b.createdAt).getTime() - new Date(a.createdAt).getTime()
    );

    // Mark all as processed
    processed.add(suggestion.id);
    allRevisions.forEach(r => processed.add(r.id));

    // If there are revisions, the latest one is the "current" version
    if (allRevisions.length > 0) {
      const latest = allRevisions[0];
      const history = [suggestion, ...allRevisions.slice(1)];
      chains.set(latest.id, [latest, ...history]);
    } else {
      // No revisions, just the original
      chains.set(suggestion.id, [suggestion]);
    }
  });

  return chains;
}
