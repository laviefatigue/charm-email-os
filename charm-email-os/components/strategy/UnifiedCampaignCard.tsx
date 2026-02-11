'use client';

import { useState } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from '@/components/ui/collapsible';
import {
  ChevronDown,
  Mail,
  CheckCircle2,
  Clock,
  AlertCircle,
  Copy,
  Variable,
  ThumbsUp,
  ThumbsDown,
  RotateCcw,
  Sparkles,
  Loader2,
  Send,
  Eye,
  History,
} from 'lucide-react';
import { cn } from '@/lib/utils';
import { toast } from 'sonner';
import { formatDistanceToNow } from 'date-fns';
import type { UnifiedCampaign, UnifiedEmail, CampaignAngle, CampaignStatus } from '@/lib/types';
import { RequestRevisionButton } from './RequestRevisionButton';

interface UnifiedCampaignCardProps {
  campaign: UnifiedCampaign;
  className?: string;
  onRequestRevisionCampaign?: () => void;
  onRequestRevisionEmail?: (position: 1 | 2 | 3 | 4) => void;
  isSubmitting?: {
    campaign?: boolean;
    emails?: Record<number, boolean>;
  };
  // Approval callbacks
  onApprove?: () => void;
  onDeny?: () => void;
  onRequestRevision?: (comment?: string) => void;
  isApproving?: boolean;
  // Spintax callbacks
  onTriggerSpintax?: () => void;
  isSpintaxing?: boolean;
  // Push to EmailBison callback
  onPushToEmailBison?: () => void;
  isPushing?: boolean;
}

const ANGLE_STYLES: Record<CampaignAngle, { bg: string; text: string; border: string; label: string }> = {
  custom_signal: { bg: 'bg-violet-50', text: 'text-violet-700', border: 'border-violet-200', label: 'Custom Signal' },
  persona_pain: { bg: 'bg-blue-50', text: 'text-blue-700', border: 'border-blue-200', label: 'Persona Pain' },
  case_study: { bg: 'bg-emerald-50', text: 'text-emerald-700', border: 'border-emerald-200', label: 'Case Study' },
  risk_efficiency: { bg: 'bg-amber-50', text: 'text-amber-700', border: 'border-amber-200', label: 'Risk/Efficiency' },
};

const STATUS_CONFIG: Record<CampaignStatus, { icon: React.ReactNode; label: string; color: string }> = {
  draft: {
    icon: <Clock className="h-4 w-4 text-yellow-600" />,
    label: 'Awaiting Review',
    color: 'bg-yellow-50 text-yellow-700 border-yellow-200'
  },
  approved: {
    icon: <CheckCircle2 className="h-4 w-4 text-green-600" />,
    label: 'Approved',
    color: 'bg-green-50 text-green-700 border-green-200'
  },
  denied: {
    icon: <AlertCircle className="h-4 w-4 text-red-600" />,
    label: 'Denied',
    color: 'bg-red-50 text-red-700 border-red-200'
  },
  revision_requested: {
    icon: <AlertCircle className="h-4 w-4 text-orange-600" />,
    label: 'Revision Requested',
    color: 'bg-orange-50 text-orange-700 border-orange-200'
  },
  spintax_pending: {
    icon: <Loader2 className="h-4 w-4 text-purple-600 animate-spin" />,
    label: 'Adding Spintax...',
    color: 'bg-purple-50 text-purple-700 border-purple-200'
  },
  spintaxed: {
    icon: <Sparkles className="h-4 w-4 text-purple-600" />,
    label: 'Spintaxed',
    color: 'bg-purple-50 text-purple-700 border-purple-200'
  },
  sent: {
    icon: <Send className="h-4 w-4 text-blue-600" />,
    label: 'Sent to EmailBison',
    color: 'bg-blue-50 text-blue-700 border-blue-200'
  },
};

interface EmailPreviewProps {
  email: UnifiedEmail;
  campaignAngle: CampaignAngle;
  onRequestRevision?: () => void;
  isSubmitting?: boolean;
}

function EmailPreview({ email, campaignAngle, onRequestRevision, isSubmitting }: EmailPreviewProps) {
  const [expanded, setExpanded] = useState(false);
  const angleStyle = ANGLE_STYLES[campaignAngle];

  const handleCopy = (e: React.MouseEvent) => {
    e.stopPropagation();
    const content = `Subject: ${email.subjectLine || '(threaded)'}\n\n${email.emailBody}`;
    navigator.clipboard.writeText(content);
    toast.success('Email copied to clipboard');
  };

  // Highlight variables in text
  const highlightVariables = (text: string) => {
    const parts = text.split(/(\{\{[^}]+\}\})/g);
    return parts.map((part, i) => {
      if (part.match(/^\{\{[^}]+\}\}$/)) {
        return (
          <span key={i} className="bg-green-100 text-green-800 px-1 rounded font-mono text-xs">
            {part}
          </span>
        );
      }
      return part;
    });
  };

  return (
    <div className={cn('border rounded-lg', expanded ? 'bg-muted/30' : '')}>
      <div
        className="flex items-center justify-between p-3 cursor-pointer hover:bg-muted/50 transition-colors"
        onClick={() => setExpanded(!expanded)}
      >
        <div className="flex items-center gap-3">
          <div className={cn(
            'flex items-center justify-center w-6 h-6 rounded-full text-xs font-medium',
            angleStyle.bg,
            angleStyle.text
          )}>
            {email.position}
          </div>
          <div>
            <p className="text-sm font-medium">{email.title}</p>
            <p className="text-xs text-muted-foreground">
              Day {email.waitDays} {email.threadReply && '• Threaded reply'}
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          {email.score && (
            <Badge variant="outline" className="text-xs">
              Score: {email.score}
            </Badge>
          )}
          <ChevronDown className={cn('h-4 w-4 transition-transform', expanded && 'rotate-180')} />
        </div>
      </div>

      {expanded && (
        <div className="px-3 pb-3 space-y-2">
          {email.subjectLine && (
            <div className="text-sm">
              <span className="text-muted-foreground">Subject: </span>
              <span className="font-medium">{highlightVariables(email.subjectLine)}</span>
            </div>
          )}
          <div className="text-sm whitespace-pre-wrap bg-background border rounded p-3">
            {highlightVariables(email.emailBody)}
          </div>
          <div className="flex items-center justify-between text-xs text-muted-foreground">
            <div className="flex items-center gap-4">
              <span>{email.wordCount || 'N/A'} words</span>
              {email.copyVariables.length > 0 && (
                <span className="flex items-center gap-1">
                  <Variable className="h-3 w-3" />
                  {email.copyVariables.length} variables
                </span>
              )}
            </div>
            <div className="flex items-center gap-2">
              {onRequestRevision && (
                <RequestRevisionButton
                  onClick={(e) => {
                    e?.stopPropagation();
                    onRequestRevision();
                  }}
                  isSubmitting={isSubmitting}
                  tooltip={`Request revision for Email ${email.position}`}
                  size="sm"
                  className="h-6"
                />
              )}
              <Button variant="ghost" size="sm" className="h-6 text-xs" onClick={handleCopy}>
                <Copy className="h-3 w-3 mr-1" />
                Copy
              </Button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export function UnifiedCampaignCard({
  campaign,
  className,
  onRequestRevisionCampaign,
  onRequestRevisionEmail,
  isSubmitting,
  onApprove,
  onDeny,
  onRequestRevision,
  isApproving,
  onTriggerSpintax,
  isSpintaxing,
  onPushToEmailBison,
  isPushing,
}: UnifiedCampaignCardProps) {
  const [emailsExpanded, setEmailsExpanded] = useState(false);
  const [showSpintaxed, setShowSpintaxed] = useState(false);
  const angleStyle = ANGLE_STYLES[campaign.angle];
  const statusConfig = STATUS_CONFIG[campaign.status];

  // Determine which emails to show (original vs spintaxed)
  const displayEmails = showSpintaxed && campaign.spintaxedEmails
    ? campaign.spintaxedEmails
    : campaign.emails;

  // Check if approval actions should be shown
  const showApprovalActions = campaign.status === 'draft' || campaign.status === 'revision_requested';
  const showSpintaxAction = campaign.status === 'approved';
  const showPushAction = campaign.status === 'spintaxed';
  const hasSpintaxedEmails = campaign.spintaxedEmails && campaign.spintaxedEmails.length > 0;

  return (
    <Card className={cn('overflow-hidden', className)}>
      <CardHeader className="pb-2">
        <div className="flex items-start justify-between">
          <div className="space-y-1">
            <div className="flex items-center gap-2">
              <Badge className={cn(angleStyle.bg, angleStyle.text, angleStyle.border, 'border')}>
                {angleStyle.label}
              </Badge>
              <Badge variant="outline" className={cn('text-xs border', statusConfig.color)}>
                <span className="flex items-center gap-1">
                  {statusConfig.icon}
                  {statusConfig.label}
                </span>
              </Badge>
            </div>
            <CardTitle className="text-base">{campaign.documentName}</CardTitle>
          </div>
          <div className="flex items-center gap-2">
            {onRequestRevisionCampaign && campaign.status !== 'sent' && (
              <RequestRevisionButton
                onClick={onRequestRevisionCampaign}
                isSubmitting={isSubmitting?.campaign}
                tooltip="Request revision for entire campaign"
                iconOnly
              />
            )}
            <Badge variant="outline" className="text-xs">
              Campaign {campaign.campaignNumber}
            </Badge>
          </div>
        </div>
      </CardHeader>

      <CardContent className="space-y-3">
        {/* Campaign Variables */}
        {campaign.campaignVariables.length > 0 && (
          <div className="space-y-1">
            <p className="text-xs font-medium text-muted-foreground">Campaign Variables</p>
            <div className="flex flex-wrap gap-1">
              {campaign.campaignVariables.map((v, i) => (
                <Badge
                  key={i}
                  variant="secondary"
                  className="font-mono text-[10px] bg-blue-50 text-blue-700"
                >
                  {v.name}
                </Badge>
              ))}
            </div>
          </div>
        )}

        {/* Email Sequence */}
        <Collapsible open={emailsExpanded} onOpenChange={setEmailsExpanded}>
          <CollapsibleTrigger asChild>
            <Button
              variant="ghost"
              className="w-full justify-between h-9 px-2"
            >
              <span className="flex items-center gap-2 text-sm">
                <Mail className="h-4 w-4" />
                Email Sequence ({displayEmails.length} emails)
                {hasSpintaxedEmails && showSpintaxed && (
                  <Badge variant="secondary" className="text-[10px] bg-purple-100 text-purple-700">
                    <Sparkles className="h-3 w-3 mr-1" />
                    Spintaxed
                  </Badge>
                )}
              </span>
              <ChevronDown className={cn('h-4 w-4 transition-transform', emailsExpanded && 'rotate-180')} />
            </Button>
          </CollapsibleTrigger>
          <CollapsibleContent className="space-y-2 mt-2">
            {/* Toggle between original and spintaxed emails */}
            {hasSpintaxedEmails && (
              <div className="flex items-center justify-end mb-2">
                <Button
                  variant="outline"
                  size="sm"
                  className="h-7 text-xs gap-1"
                  onClick={() => setShowSpintaxed(!showSpintaxed)}
                >
                  <Eye className="h-3 w-3" />
                  {showSpintaxed ? 'Show Original' : 'Show Spintaxed'}
                </Button>
              </div>
            )}
            {displayEmails.map((email) => (
              <EmailPreview
                key={email.position}
                email={email}
                campaignAngle={campaign.angle}
                onRequestRevision={
                  onRequestRevisionEmail && !showSpintaxed
                    ? () => onRequestRevisionEmail(email.position)
                    : undefined
                }
                isSubmitting={isSubmitting?.emails?.[email.position]}
              />
            ))}
          </CollapsibleContent>
        </Collapsible>

        {/* QA Score */}
        {campaign.qaScoring && (
          <div className="flex items-center justify-between pt-2 border-t">
            <div className="flex items-center gap-2">
              <span className="text-sm font-medium">QA Score:</span>
              <Badge
                className={cn(
                  campaign.qaScoring.overallScore >= 85
                    ? 'bg-green-100 text-green-800'
                    : campaign.qaScoring.overallScore >= 75
                    ? 'bg-yellow-100 text-yellow-800'
                    : 'bg-red-100 text-red-800'
                )}
              >
                {campaign.qaScoring.overallScore}
              </Badge>
            </div>
            <span className="text-xs text-muted-foreground">{campaign.qaScoring.verdict}</span>
          </div>
        )}

        {/* Approval Actions */}
        {showApprovalActions && (onApprove || onDeny || onRequestRevision) && (
          <div className="flex items-center justify-between pt-3 border-t">
            <p className="text-sm text-muted-foreground">
              {campaign.status === 'revision_requested'
                ? 'Ready for re-review'
                : 'Review this campaign'}
            </p>
            <div className="flex items-center gap-2">
              {onRequestRevision && (
                <Button
                  variant="outline"
                  size="sm"
                  className="h-8 text-xs gap-1 text-orange-600 hover:text-orange-700 hover:border-orange-300"
                  onClick={() => onRequestRevision()}
                  disabled={isApproving}
                >
                  <RotateCcw className="h-3 w-3" />
                  Request Revision
                </Button>
              )}
              {onDeny && (
                <Button
                  variant="outline"
                  size="sm"
                  className="h-8 text-xs gap-1 text-red-600 hover:text-red-700 hover:border-red-300"
                  onClick={onDeny}
                  disabled={isApproving}
                >
                  <ThumbsDown className="h-3 w-3" />
                  Deny
                </Button>
              )}
              {onApprove && (
                <Button
                  variant="default"
                  size="sm"
                  className="h-8 text-xs gap-1 bg-green-600 hover:bg-green-700"
                  onClick={onApprove}
                  disabled={isApproving}
                >
                  {isApproving ? (
                    <Loader2 className="h-3 w-3 animate-spin" />
                  ) : (
                    <ThumbsUp className="h-3 w-3" />
                  )}
                  Approve
                </Button>
              )}
            </div>
          </div>
        )}

        {/* Spintax Action */}
        {showSpintaxAction && onTriggerSpintax && (
          <div className="flex items-center justify-between pt-3 border-t">
            <div>
              <p className="text-sm font-medium text-green-700">Campaign Approved</p>
              <p className="text-xs text-muted-foreground">Add spintax variations to emails</p>
            </div>
            <Button
              variant="default"
              size="sm"
              className="h-8 text-xs gap-1 bg-purple-600 hover:bg-purple-700"
              onClick={onTriggerSpintax}
              disabled={isSpintaxing}
            >
              {isSpintaxing ? (
                <Loader2 className="h-3 w-3 animate-spin" />
              ) : (
                <Sparkles className="h-3 w-3" />
              )}
              {isSpintaxing ? 'Processing...' : 'Add Spintax'}
            </Button>
          </div>
        )}

        {/* Push to EmailBison Action */}
        {showPushAction && onPushToEmailBison && (
          <div className="flex items-center justify-between pt-3 border-t">
            <div>
              <p className="text-sm font-medium text-purple-700">Spintax Complete</p>
              <p className="text-xs text-muted-foreground">Ready to push to EmailBison</p>
            </div>
            <Button
              variant="default"
              size="sm"
              className="h-8 text-xs gap-1 bg-blue-600 hover:bg-blue-700"
              onClick={onPushToEmailBison}
              disabled={isPushing}
            >
              {isPushing ? (
                <Loader2 className="h-3 w-3 animate-spin" />
              ) : (
                <Send className="h-3 w-3" />
              )}
              {isPushing ? 'Pushing...' : 'Push to EmailBison'}
            </Button>
          </div>
        )}

        {/* Sent Status */}
        {campaign.status === 'sent' && (
          <div className="flex items-center justify-center pt-3 border-t">
            <Badge className="bg-blue-100 text-blue-700 text-xs gap-1">
              <Send className="h-3 w-3" />
              Successfully pushed to EmailBison
            </Badge>
          </div>
        )}

        {/* Revision History */}
        {campaign.revisionHistory && campaign.revisionHistory.length > 0 && (
          <Collapsible className="pt-3 border-t">
            <CollapsibleTrigger asChild>
              <Button variant="ghost" className="w-full justify-between h-8 px-2">
                <span className="flex items-center gap-2 text-sm text-muted-foreground">
                  <History className="h-4 w-4" />
                  Revision History ({campaign.revisionHistory.length})
                </span>
                <ChevronDown className="h-4 w-4" />
              </Button>
            </CollapsibleTrigger>
            <CollapsibleContent className="mt-2 space-y-2">
              {campaign.revisionHistory.map((rev) => (
                <div
                  key={rev.id}
                  className="p-2 border rounded text-sm bg-muted/30"
                >
                  <div className="flex items-center justify-between mb-1">
                    <span className="text-xs text-muted-foreground">
                      {formatDistanceToNow(new Date(rev.createdAt), { addSuffix: true })}
                    </span>
                    <Badge
                      variant={rev.status === 'processed' ? 'default' : 'secondary'}
                      className="text-[10px]"
                    >
                      {rev.status === 'processed' ? 'Processed' : 'Pending'}
                    </Badge>
                  </div>
                  <p className="text-sm">{rev.instruction}</p>
                  {rev.scope && (
                    <p className="text-xs text-muted-foreground mt-1">
                      Scope: {rev.scope}
                    </p>
                  )}
                </div>
              ))}
            </CollapsibleContent>
          </Collapsible>
        )}
      </CardContent>
    </Card>
  );
}
