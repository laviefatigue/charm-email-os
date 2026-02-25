'use client';

import { useState } from 'react';
import {
  ChevronDown,
  ChevronUp,
  Mail,
  Check,
  X,
  RotateCcw,
  Send,
  Loader2,
  Star,
  ExternalLink,
  Sparkles,
} from 'lucide-react';
import { Card, CardHeader, CardContent } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { SequenceTimeline } from './SequenceTimeline';
import { EmailStepCard } from './EmailStepCard';
import { cn } from '@/lib/utils';
import type { CampaignSequence } from '@/lib/api';

interface CampaignSequenceCardProps {
  sequence: CampaignSequence;
  onApprove?: (sequenceId: string) => Promise<void>;
  onDeny?: (sequenceId: string) => Promise<void>;
  onEditEmail?: (sequenceId: string, position: number) => void;
  onRequestRevision?: (sequenceId: string, position?: number) => void;
  onSpintax?: (sequenceId: string) => Promise<void>;
  onPushToEmailBison?: (sequenceId: string) => Promise<void>;
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

export function CampaignSequenceCard({
  sequence,
  onApprove,
  onDeny,
  onEditEmail,
  onRequestRevision,
  onSpintax,
  onPushToEmailBison,
  className,
}: CampaignSequenceCardProps) {
  const [isExpanded, setIsExpanded] = useState(false);
  const [expandedEmails, setExpandedEmails] = useState<Set<number>>(new Set([1]));
  const [isApproving, setIsApproving] = useState(false);
  const [isDenying, setIsDenying] = useState(false);
  const [isSpintaxing, setIsSpintaxing] = useState(false);
  const [isPushing, setIsPushing] = useState(false);
  const [viewMode, setViewMode] = useState<'original' | 'spintaxed'>('spintaxed');

  const statusStyle = STATUS_STYLES[sequence.status] || STATUS_STYLES.pending;
  const campaignTypeLabel = sequence.campaignType
    ? CAMPAIGN_TYPE_LABELS[sequence.campaignType] || sequence.campaignType
    : null;

  // Determine which emails to display based on view mode
  const hasSpintaxedEmails = sequence.spintaxedEmails && sequence.spintaxedEmails.length > 0;
  const emailsToShow = viewMode === 'spintaxed' && hasSpintaxedEmails
    ? sequence.spintaxedEmails!
    : sequence.emails;

  // Sort emails by position
  const sortedEmails = [...emailsToShow].sort((a, b) => a.position - b.position);

  const toggleEmailExpanded = (position: number) => {
    setExpandedEmails((prev) => {
      const next = new Set(prev);
      if (next.has(position)) {
        next.delete(position);
      } else {
        next.add(position);
      }
      return next;
    });
  };

  const handleApprove = async () => {
    if (!onApprove) return;
    setIsApproving(true);
    try {
      await onApprove(sequence.id);
    } finally {
      setIsApproving(false);
    }
  };

  const handleDeny = async () => {
    if (!onDeny) return;
    setIsDenying(true);
    try {
      await onDeny(sequence.id);
    } finally {
      setIsDenying(false);
    }
  };

  const handleSpintax = async () => {
    if (!onSpintax) return;
    setIsSpintaxing(true);
    try {
      await onSpintax(sequence.id);
    } finally {
      setIsSpintaxing(false);
    }
  };

  const handlePush = async () => {
    if (!onPushToEmailBison) return;
    setIsPushing(true);
    try {
      await onPushToEmailBison(sequence.id);
    } finally {
      setIsPushing(false);
    }
  };

  return (
    <Card className={cn('overflow-hidden', className)}>
      {/* Collapsed Header */}
      <CardHeader
        className={cn(
          'cursor-pointer hover:bg-gray-50 transition-colors',
          isExpanded && 'border-b'
        )}
        onClick={() => setIsExpanded(!isExpanded)}
      >
        <div className="flex items-start justify-between gap-4">
          {/* Left side: Icon and info */}
          <div className="flex items-start gap-3 flex-1 min-w-0">
            <div className="flex-shrink-0 w-10 h-10 bg-blue-100 rounded-lg flex items-center justify-center">
              <Mail className="w-5 h-5 text-blue-600" />
            </div>

            <div className="flex-1 min-w-0">
              {/* Campaign name */}
              <div className="flex items-center gap-2 flex-wrap">
                <h3 className="font-semibold text-sm truncate">
                  {sequence.campaignName}
                </h3>
                <Badge className={cn('text-xs', statusStyle.bg, statusStyle.text)}>
                  {statusStyle.label}
                </Badge>
              </div>

              {/* Meta info row */}
              <div className="flex items-center gap-3 mt-1 text-xs text-muted-foreground flex-wrap">
                {campaignTypeLabel && (
                  <span className="bg-gray-100 px-2 py-0.5 rounded">
                    {campaignTypeLabel}
                  </span>
                )}
                <span>4 emails</span>
                {sequence.totalWordCount && (
                  <span>{sequence.totalWordCount} words total</span>
                )}
                {sequence.score && (
                  <span className="flex items-center gap-1">
                    <Star className="w-3 h-3 text-yellow-500 fill-yellow-500" />
                    {sequence.score}/100
                  </span>
                )}
              </div>

              {/* Value prop rotation */}
              {sequence.valuePropRotation && sequence.valuePropRotation.length > 0 && (
                <div className="flex items-center gap-1 mt-1 text-xs">
                  <span className="text-muted-foreground">Value Props:</span>
                  {sequence.valuePropRotation.map((prop, i) => (
                    <span key={prop}>
                      {VALUE_PROP_ICONS[prop] || prop}
                      {i < sequence.valuePropRotation!.length - 1 && ' → '}
                    </span>
                  ))}
                </div>
              )}
            </div>
          </div>

          {/* Right side: Expand button */}
          <button className="text-gray-400 hover:text-gray-600 p-1">
            {isExpanded ? (
              <ChevronUp className="w-5 h-5" />
            ) : (
              <ChevronDown className="w-5 h-5" />
            )}
          </button>
        </div>
      </CardHeader>

      {/* Expanded Content */}
      {isExpanded && (
        <CardContent className="pt-4 space-y-4">
          {/* Timeline visualization */}
          <SequenceTimeline />

          {/* Spintax view toggle - show when spintaxed */}
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
                  onClick={(e) => {
                    e.stopPropagation();
                    setViewMode('original');
                  }}
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
                  onClick={(e) => {
                    e.stopPropagation();
                    setViewMode('spintaxed');
                  }}
                >
                  <Sparkles className="w-3 h-3 mr-1" />
                  Spintaxed
                </Button>
              </div>
            </div>
          )}

          {/* Email list */}
          <div className="space-y-2">
            {sortedEmails.map((email) => (
              <EmailStepCard
                key={email.position}
                email={email}
                isExpanded={expandedEmails.has(email.position)}
                onToggleExpand={() => toggleEmailExpanded(email.position)}
                onEdit={onEditEmail ? (pos) => onEditEmail(sequence.id, pos) : undefined}
                onRequestRevision={
                  onRequestRevision ? (pos) => onRequestRevision(sequence.id, pos) : undefined
                }
                highlightSpintax={viewMode === 'spintaxed' && hasSpintaxedEmails}
              />
            ))}
          </div>

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
                <p className="text-xs text-yellow-600 mt-1">— {sequence.reviewedBy}</p>
              )}
            </div>
          )}

          {/* Action buttons */}
          <div className="flex items-center gap-2 pt-2 border-t flex-wrap">
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
                    onClick={() => onRequestRevision(sequence.id)}
                  >
                    <RotateCcw className="w-4 h-4 mr-1" />
                    Request Revision
                  </Button>
                )}
              </>
            )}

            {/* Approved: Show Spintax button */}
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

            {/* Spintax pending: Show processing indicator */}
            {sequence.status === 'spintax_pending' && (
              <Badge className="bg-purple-100 text-purple-700">
                <Loader2 className="w-3 h-3 mr-1 animate-spin" />
                Processing Spintax...
              </Badge>
            )}

            {/* Spintaxed: Show Push to EmailBison button */}
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

            {sequence.pushedToEmailbison && (
              <Badge className="bg-blue-100 text-blue-700">
                <ExternalLink className="w-3 h-3 mr-1" />
                Pushed to EmailBison
              </Badge>
            )}
          </div>
        </CardContent>
      )}
    </Card>
  );
}
