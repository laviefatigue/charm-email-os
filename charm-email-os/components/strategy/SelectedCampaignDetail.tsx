'use client';

import { useState } from 'react';
import {
  Mail,
  Star,
  Check,
  X,
  RotateCcw,
  Send,
  Loader2,
  Sparkles,
  ExternalLink,
  Copy,
  Clock,
  MessageSquare,
  Edit2,
  History,
} from 'lucide-react';
import { Card, CardHeader, CardContent } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { cn } from '@/lib/utils';
import type { CampaignSequence, SequenceEmail } from '@/lib/api';
import { StrategyConsiderationPanel } from './StrategyConsiderationPanel';
import { CampaignPerformanceCard } from './CampaignPerformanceCard';

interface SelectedCampaignDetailProps {
  sequence: CampaignSequence;
  onApprove?: () => Promise<void>;
  onDeny?: () => Promise<void>;
  onSpintax?: () => Promise<void>;
  onPushToEmailBison?: () => Promise<void>;
  onEditEmail?: (position: number) => void;
  onRequestRevision?: (position?: number) => void;
  className?: string;
}

const STATUS_STYLES: Record<string, { bg: string; text: string; label: string }> = {
  pending: { bg: 'bg-yellow-100', text: 'text-yellow-700', label: 'Pending Review' },
  approved: { bg: 'bg-green-100', text: 'text-green-700', label: 'Approved' },
  denied: { bg: 'bg-red-100', text: 'text-red-700', label: 'Denied' },
  revision_requested: { bg: 'bg-orange-100', text: 'text-orange-700', label: 'Revision Requested' },
  spintax_pending: { bg: 'bg-purple-100', text: 'text-purple-700', label: 'Spintax Processing' },
  spintaxed: { bg: 'bg-indigo-100', text: 'text-indigo-700', label: 'Spintaxed' },
  sent: { bg: 'bg-blue-100', text: 'text-blue-700', label: 'Sent' },
};

const CAMPAIGN_TYPE_LABELS: Record<string, string> = {
  custom_signal: 'Custom Signal',
  creative_ideas: 'Creative Ideas',
  whole_offer: 'Whole Offer',
  fallback: 'Fallback',
};

const VALUE_PROP_ICONS: Record<string, string> = {
  save_time: '\u23F1\uFE0F',
  save_money: '\uD83D\uDCB5',
  make_money: '\uD83D\uDCB0',
};

// Highlight spintax and liquid syntax in text
function renderWithSpintaxHighlight(text: string): React.ReactNode {
  if (!text) return text;

  const parts: React.ReactNode[] = [];
  let lastIndex = 0;

  // Combined regex for spintax {a|b|c}, liquid tags {% %}, and liquid vars {{ }}
  const regex = /(\{[^{}|]+(?:\|[^{}|]+)+\})|(\{%[^%]+%\})|(\{\{[^}]+\}\})/g;
  let match;

  while ((match = regex.exec(text)) !== null) {
    if (match.index > lastIndex) {
      parts.push(text.slice(lastIndex, match.index));
    }

    const matchedText = match[0];
    if (match[1]) {
      // Spintax {option1|option2}
      parts.push(
        <span key={match.index} className="bg-purple-100 text-purple-800 rounded px-0.5 font-mono text-xs">
          {matchedText}
        </span>
      );
    } else if (match[2]) {
      // Liquid tag {% if %}{% endif %}
      parts.push(
        <span key={match.index} className="bg-blue-100 text-blue-800 rounded px-0.5 font-mono text-xs">
          {matchedText}
        </span>
      );
    } else if (match[3]) {
      // Liquid variable {{var}}
      parts.push(
        <span key={match.index} className="bg-green-100 text-green-800 rounded px-0.5 font-mono text-xs">
          {matchedText}
        </span>
      );
    }

    lastIndex = regex.lastIndex;
  }

  if (lastIndex < text.length) {
    parts.push(text.slice(lastIndex));
  }

  return parts.length > 0 ? parts : text;
}

// Email detail card component
function EmailDetailCard({
  email,
  highlightSpintax,
  onEdit,
  onRequestRevision,
  onCopy,
}: {
  email: SequenceEmail;
  highlightSpintax: boolean;
  onEdit?: (position: number) => void;
  onRequestRevision?: (position: number) => void;
  onCopy: (text: string) => void;
}) {
  const displaySubject = email.editedSubjectLine || email.subjectLine;
  const displayBody = email.editedEmailBody || email.emailBody;
  const isEdited = !!(email.editedSubjectLine || email.editedEmailBody);

  return (
    <div className="border rounded-lg overflow-hidden bg-white">
      {/* Email header */}
      <div className="flex items-center justify-between p-3 bg-gray-50 border-b">
        <div className="flex items-center gap-3">
          <span className="font-semibold text-sm">Email {email.position}</span>
          <span className="text-xs text-muted-foreground flex items-center gap-1">
            <Clock className="w-3 h-3" />
            Day {email.waitDays}
          </span>
          {email.threadReply ? (
            <Badge variant="outline" className="text-xs bg-gray-100">
              <MessageSquare className="w-3 h-3 mr-1" />
              Thread Reply
            </Badge>
          ) : (
            <Badge variant="outline" className="text-xs bg-blue-50 text-blue-700 border-blue-200">
              New Thread
            </Badge>
          )}
          {isEdited && (
            <Badge variant="secondary" className="text-xs">
              Edited
            </Badge>
          )}
        </div>
        <div className="flex items-center gap-1">
          {email.wordCount && (
            <Badge variant="outline" className="text-xs">
              {email.wordCount} words
            </Badge>
          )}
        </div>
      </div>

      {/* Email content */}
      <div className="p-4 space-y-3">
        {/* Subject line (for Email 1 and 3) */}
        {displaySubject && (
          <div>
            <div className="flex items-center justify-between mb-1">
              <span className="text-xs font-medium text-muted-foreground">Subject Line</span>
              <Button
                variant="ghost"
                size="sm"
                className="h-6 px-2"
                onClick={() => onCopy(displaySubject)}
              >
                <Copy className="w-3 h-3" />
              </Button>
            </div>
            <div className="bg-gray-50 rounded p-2 font-mono text-sm">
              {highlightSpintax ? renderWithSpintaxHighlight(displaySubject) : displaySubject}
            </div>
          </div>
        )}

        {/* Email body */}
        <div>
          <div className="flex items-center justify-between mb-1">
            <span className="text-xs font-medium text-muted-foreground">Email Body</span>
            <Button
              variant="ghost"
              size="sm"
              className="h-6 px-2"
              onClick={() => onCopy(displayBody)}
            >
              <Copy className="w-3 h-3" />
            </Button>
          </div>
          <pre className="bg-gray-50 rounded p-3 text-sm whitespace-pre-wrap font-sans leading-relaxed max-h-[300px] overflow-y-auto">
            {highlightSpintax ? renderWithSpintaxHighlight(displayBody) : displayBody}
          </pre>
        </div>

        {/* Email actions */}
        <div className="flex items-center gap-2 pt-2 border-t">
          {onEdit && (
            <Button
              variant="outline"
              size="sm"
              onClick={() => onEdit(email.position)}
            >
              <Edit2 className="w-3 h-3 mr-1" />
              Edit
            </Button>
          )}
          {onRequestRevision && (
            <Button
              variant="outline"
              size="sm"
              onClick={() => onRequestRevision(email.position)}
            >
              <RotateCcw className="w-3 h-3 mr-1" />
              Request Revision
            </Button>
          )}
        </div>
      </div>
    </div>
  );
}

export function SelectedCampaignDetail({
  sequence,
  onApprove,
  onDeny,
  onSpintax,
  onPushToEmailBison,
  onEditEmail,
  onRequestRevision,
  className,
}: SelectedCampaignDetailProps) {
  const [viewMode, setViewMode] = useState<'original' | 'spintaxed'>('spintaxed');
  const [isApproving, setIsApproving] = useState(false);
  const [isDenying, setIsDenying] = useState(false);
  const [isSpintaxing, setIsSpintaxing] = useState(false);
  const [isPushing, setIsPushing] = useState(false);

  const statusStyle = STATUS_STYLES[sequence.status] || STATUS_STYLES.pending;
  const campaignTypeLabel = sequence.campaignType
    ? CAMPAIGN_TYPE_LABELS[sequence.campaignType] || sequence.campaignType
    : null;

  // Determine which emails to display
  const hasSpintaxedEmails = sequence.spintaxedEmails && sequence.spintaxedEmails.length > 0;
  const emailsToShow = viewMode === 'spintaxed' && hasSpintaxedEmails
    ? sequence.spintaxedEmails!
    : sequence.emails;
  const sortedEmails = [...emailsToShow].sort((a, b) => a.position - b.position);

  const handleApprove = async () => {
    if (!onApprove) return;
    setIsApproving(true);
    try {
      await onApprove();
    } finally {
      setIsApproving(false);
    }
  };

  const handleDeny = async () => {
    if (!onDeny) return;
    setIsDenying(true);
    try {
      await onDeny();
    } finally {
      setIsDenying(false);
    }
  };

  const handleSpintax = async () => {
    if (!onSpintax) return;
    setIsSpintaxing(true);
    try {
      await onSpintax();
    } finally {
      setIsSpintaxing(false);
    }
  };

  const handlePush = async () => {
    if (!onPushToEmailBison) return;
    setIsPushing(true);
    try {
      await onPushToEmailBison();
    } finally {
      setIsPushing(false);
    }
  };

  const handleCopy = (text: string) => {
    navigator.clipboard.writeText(text);
  };

  return (
    <Card className={cn('overflow-hidden', className)}>
      {/* Campaign header */}
      <CardHeader className="border-b bg-gray-50/50">
        <div className="flex items-start justify-between gap-4">
          <div className="flex items-start gap-3 flex-1 min-w-0">
            <div className="flex-shrink-0 w-10 h-10 bg-blue-100 rounded-lg flex items-center justify-center">
              <Mail className="w-5 h-5 text-blue-600" />
            </div>
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2 flex-wrap">
                <h3 className="font-semibold text-base truncate">
                  {sequence.campaignName}
                </h3>
                <Badge className={cn('text-xs', statusStyle.bg, statusStyle.text)}>
                  {statusStyle.label}
                </Badge>
              </div>
              <div className="flex items-center gap-3 mt-1 text-sm text-muted-foreground flex-wrap">
                {campaignTypeLabel && (
                  <span className="bg-gray-100 px-2 py-0.5 rounded text-xs">
                    {campaignTypeLabel}
                  </span>
                )}
                <span>4 emails</span>
                {sequence.totalWordCount && (
                  <span>{sequence.totalWordCount} words total</span>
                )}
                {sequence.score && (
                  <span className="flex items-center gap-1">
                    <Star className="w-4 h-4 text-yellow-500 fill-yellow-500" />
                    {sequence.score}/100
                  </span>
                )}
              </div>
              {sequence.valuePropRotation && sequence.valuePropRotation.length > 0 && (
                <div className="flex items-center gap-1 mt-1 text-xs">
                  <span className="text-muted-foreground">Value Props:</span>
                  {sequence.valuePropRotation.map((prop, i) => (
                    <span key={prop}>
                      {VALUE_PROP_ICONS[prop] || prop}
                      {i < sequence.valuePropRotation!.length - 1 && ' \u2192 '}
                    </span>
                  ))}
                </div>
              )}
              {/* Campaign angle and target info */}
              {(sequence.campaignAngle || sequence.targetPersona || sequence.targetSegment) && (
                <div className="flex items-center gap-2 mt-1 flex-wrap">
                  {sequence.campaignAngle && (
                    <Badge variant="outline" className="text-xs bg-amber-50 border-amber-200 text-amber-700">
                      {sequence.campaignAngle.replace(/_/g, ' ')}
                    </Badge>
                  )}
                  {sequence.targetPersona && (
                    <Badge variant="outline" className="text-xs bg-purple-50 border-purple-200 text-purple-700">
                      {sequence.targetPersona}
                    </Badge>
                  )}
                  {sequence.targetSegment && (
                    <Badge variant="outline" className="text-xs bg-blue-50 border-blue-200 text-blue-700">
                      {sequence.targetSegment}
                    </Badge>
                  )}
                </div>
              )}
              {/* Cycle and version badges */}
              {(sequence.cycleId || sequence.campaignVersion) && (
                <div className="flex items-center gap-2 mt-1 flex-wrap">
                  {sequence.cycleId && (
                    <Badge variant="outline" className="text-xs bg-gray-50 border-gray-200 text-gray-700">
                      Cycle
                    </Badge>
                  )}
                  {sequence.campaignVersion && (
                    <Badge variant="secondary" className="text-xs">
                      v{sequence.campaignVersion}
                    </Badge>
                  )}
                  {sequence.lineageId && (
                    <span className="text-xs text-muted-foreground">
                      Lineage: {sequence.lineageId.slice(0, 8)}...
                    </span>
                  )}
                </div>
              )}
            </div>
          </div>
        </div>
      </CardHeader>

      <CardContent className="pt-4 space-y-4">
        {/* Spintax view toggle */}
        {(sequence.status === 'spintaxed' || sequence.status === 'sent') && hasSpintaxedEmails && (
          <div className="flex items-center justify-between bg-gray-50 rounded-lg p-2">
            <span className="text-xs text-muted-foreground">View:</span>
            <div className="flex gap-1 bg-white rounded-md p-0.5 border">
              <Button
                variant={viewMode === 'original' ? 'default' : 'ghost'}
                size="sm"
                className={cn(
                  'h-7 px-3 text-xs',
                  viewMode === 'original' && 'bg-gray-900 text-white'
                )}
                onClick={() => setViewMode('original')}
              >
                Original
              </Button>
              <Button
                variant={viewMode === 'spintaxed' ? 'default' : 'ghost'}
                size="sm"
                className={cn(
                  'h-7 px-3 text-xs',
                  viewMode === 'spintaxed' && 'bg-purple-600 text-white hover:bg-purple-700'
                )}
                onClick={() => setViewMode('spintaxed')}
              >
                <Sparkles className="w-3 h-3 mr-1" />
                Spintaxed
              </Button>
            </div>
          </div>
        )}

        {/* Syntax highlighting legend */}
        {viewMode === 'spintaxed' && hasSpintaxedEmails && (
          <div className="flex items-center gap-4 text-xs text-muted-foreground bg-gray-50 rounded-lg p-2">
            <span className="font-medium">Legend:</span>
            <span className="flex items-center gap-1">
              <span className="bg-purple-100 text-purple-800 rounded px-1 font-mono">{'{a|b}'}</span>
              Spintax
            </span>
            <span className="flex items-center gap-1">
              <span className="bg-blue-100 text-blue-800 rounded px-1 font-mono">{'{% if %}'}</span>
              Liquid Tag
            </span>
            <span className="flex items-center gap-1">
              <span className="bg-green-100 text-green-800 rounded px-1 font-mono">{'{{var}}'}</span>
              Variable
            </span>
          </div>
        )}

        {/* All emails */}
        <div className="space-y-3">
          {sortedEmails.map((email) => (
            <EmailDetailCard
              key={email.position}
              email={email}
              highlightSpintax={viewMode === 'spintaxed' && !!hasSpintaxedEmails}
              onEdit={onEditEmail}
              onRequestRevision={onRequestRevision}
              onCopy={handleCopy}
            />
          ))}
        </div>

        {/* Strategy Consideration Panel */}
        {sequence.strategyConsiderations && (
          <StrategyConsiderationPanel
            considerations={sequence.strategyConsiderations}
            sequence={sequence}
          />
        )}

        {/* Version History - show if campaign has version tracking */}
        {sequence.campaignVersion && sequence.campaignVersion > 1 && (
          <div className="bg-gray-50 border border-gray-200 rounded-lg p-3">
            <h4 className="text-xs font-semibold text-gray-700 mb-2 flex items-center gap-1">
              <History className="w-3.5 h-3.5" />
              Version History
            </h4>
            <div className="space-y-2">
              {/* Current version */}
              <div className="flex items-center gap-2 text-sm">
                <Badge variant="secondary" className="text-xs">
                  v{sequence.campaignVersion}
                </Badge>
                <span className="text-muted-foreground">Current</span>
                {sequence.createdAt && (
                  <span className="text-xs text-muted-foreground">
                    {new Date(sequence.createdAt).toLocaleDateString()}
                  </span>
                )}
              </div>
              {/* Previous version link (if available) */}
              {sequence.previousVersionId && (
                <p className="text-xs text-muted-foreground">
                  Evolved from previous version
                </p>
              )}
            </div>
          </div>
        )}

        {/* Campaign Performance (for campaigns pushed to EmailBison) */}
        {sequence.performanceMetrics && (
          <CampaignPerformanceCard
            metrics={sequence.performanceMetrics}
            emailbisonCampaignId={sequence.emailbisonCampaignId}
            lastSync={sequence.lastPerformanceSync}
          />
        )}

        {/* Rationale */}
        {sequence.rationale && (
          <div className="bg-blue-50 border border-blue-200 rounded-lg p-3">
            <h4 className="text-xs font-semibold text-blue-700 mb-1">Rationale</h4>
            <p className="text-sm text-blue-800">{sequence.rationale}</p>
          </div>
        )}

        {/* Variables */}
        {sequence.usedVariables && sequence.usedVariables.length > 0 && (
          <div className="flex flex-wrap gap-1">
            <span className="text-xs text-muted-foreground mr-1">Variables:</span>
            {sequence.usedVariables.map((variable) => (
              <Badge key={variable} variant="outline" className="text-xs font-mono">
                {variable}
              </Badge>
            ))}
          </div>
        )}

        {/* Human feedback */}
        {sequence.humanComment && (
          <div className="bg-yellow-50 border border-yellow-200 rounded-lg p-3">
            <h4 className="text-xs font-semibold text-yellow-700 mb-1">Feedback</h4>
            <p className="text-sm text-yellow-800">{sequence.humanComment}</p>
            {sequence.reviewedBy && (
              <p className="text-xs text-yellow-600 mt-1">\u2014 {sequence.reviewedBy}</p>
            )}
          </div>
        )}

        {/* Action buttons */}
        <div className="flex items-center gap-2 pt-4 border-t flex-wrap">
          {/* Pending: Approve/Deny/Revision */}
          {sequence.status === 'pending' && (
            <>
              {onApprove && (
                <Button
                  variant="default"
                  size="sm"
                  className="bg-green-600 hover:bg-green-700"
                  onClick={handleApprove}
                  disabled={isApproving}
                >
                  {isApproving ? (
                    <Loader2 className="w-4 h-4 mr-1 animate-spin" />
                  ) : (
                    <Check className="w-4 h-4 mr-1" />
                  )}
                  Approve Sequence
                </Button>
              )}
              {onDeny && (
                <Button
                  variant="outline"
                  size="sm"
                  className="text-red-600 hover:bg-red-50"
                  onClick={handleDeny}
                  disabled={isDenying}
                >
                  {isDenying ? (
                    <Loader2 className="w-4 h-4 mr-1 animate-spin" />
                  ) : (
                    <X className="w-4 h-4 mr-1" />
                  )}
                  Deny
                </Button>
              )}
              {onRequestRevision && (
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => onRequestRevision()}
                >
                  <RotateCcw className="w-4 h-4 mr-1" />
                  Request Revision
                </Button>
              )}
            </>
          )}

          {/* Approved: Add Spintax */}
          {sequence.status === 'approved' && onSpintax && (
            <Button
              variant="default"
              size="sm"
              className="bg-purple-600 hover:bg-purple-700"
              onClick={handleSpintax}
              disabled={isSpintaxing}
            >
              {isSpintaxing ? (
                <Loader2 className="w-4 h-4 mr-1 animate-spin" />
              ) : (
                <Sparkles className="w-4 h-4 mr-1" />
              )}
              Add Spintax
            </Button>
          )}

          {/* Spintax pending */}
          {sequence.status === 'spintax_pending' && (
            <Badge className="bg-purple-100 text-purple-700">
              <Loader2 className="w-3 h-3 mr-1 animate-spin" />
              Processing Spintax...
            </Badge>
          )}

          {/* Spintaxed: Push to EmailBison */}
          {sequence.status === 'spintaxed' && !sequence.pushedToEmailbison && onPushToEmailBison && (
            <Button
              variant="default"
              size="sm"
              className="bg-blue-600 hover:bg-blue-700"
              onClick={handlePush}
              disabled={isPushing}
            >
              {isPushing ? (
                <Loader2 className="w-4 h-4 mr-1 animate-spin" />
              ) : (
                <Send className="w-4 h-4 mr-1" />
              )}
              Push to EmailBison
            </Button>
          )}

          {/* Already pushed */}
          {sequence.pushedToEmailbison && (
            <Badge className="bg-blue-100 text-blue-700">
              <ExternalLink className="w-3 h-3 mr-1" />
              Pushed to EmailBison
            </Badge>
          )}
        </div>
      </CardContent>
    </Card>
  );
}
