'use client';

import { useState } from 'react';
import {
  Check,
  X,
  Edit,
  ChevronDown,
  ChevronUp,
  Target,
  FileText,
  Database,
  Lightbulb,
  Mail,
  Star,
} from 'lucide-react';
import { toast } from 'sonner';
import { Card, CardContent } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { StatusBadge } from '@/components/shared';
import type { CampaignIdea, CampaignType } from '@/lib/types';
import { useStrategyStore, useCampaignStore } from '@/lib/stores';
import { cn } from '@/lib/utils';

interface IdeaCardProps {
  idea: CampaignIdea;
  onEdit?: (idea: CampaignIdea) => void;
}

const CAMPAIGN_TYPE_LABELS: Record<CampaignType, { label: string; color: string }> = {
  custom_signal: { label: 'Custom Signal', color: 'bg-purple-100 text-purple-800' },
  creative_ideas: { label: 'Creative Ideas', color: 'bg-blue-100 text-blue-800' },
  whole_offer: { label: 'Whole Offer', color: 'bg-green-100 text-green-800' },
  fallback: { label: 'Fallback', color: 'bg-gray-100 text-gray-800' },
};

export function IdeaCard({ idea, onEdit }: IdeaCardProps) {
  const [expanded, setExpanded] = useState(false);
  const { approveIdea, rejectIdea } = useStrategyStore();
  const { createCampaignFromIdea } = useCampaignStore();

  const handleApprove = () => {
    approveIdea(idea.id);
    createCampaignFromIdea(idea);
    toast.success('Campaign approved! Head to Leads to start execution.');
  };

  const handleReject = () => {
    rejectIdea(idea.id);
    if (onEdit) {
      onEdit(idea);
    }
  };

  const isPending = idea.status === 'pending';
  const isEditing = idea.status === 'editing';
  const isApproved = idea.status === 'approved';

  const campaignTypeInfo = idea.campaignType
    ? CAMPAIGN_TYPE_LABELS[idea.campaignType]
    : CAMPAIGN_TYPE_LABELS.custom_signal;

  // Count available variables
  const variableCount = idea.variables
    ? Object.values(idea.variables.core || {}).filter(Boolean).length +
      Object.values(idea.variables.highSignal || {}).filter(Boolean).length +
      Object.values(idea.variables.aiGenerated || {}).filter(Boolean).length +
      Object.keys(idea.variables.custom || {}).length
    : 0;

  return (
    <Card className="transition-all hover:shadow-sm">
      <CardContent className="p-5">
        {/* Header: Hierarchy */}
        <div className="flex items-start justify-between gap-2 mb-3">
          <div className="flex-1 min-w-0">
            <h3 className="font-semibold text-lg truncate">{idea.title}</h3>
            <div className="flex flex-wrap items-center gap-1.5 mt-1.5">
              <Badge variant="outline" className="text-xs">
                {idea.industry}
              </Badge>
              <span className="text-muted-foreground text-xs">→</span>
              <Badge variant="secondary" className="text-xs">
                {idea.segment}
              </Badge>
              <span className="text-muted-foreground text-xs">→</span>
              <Badge className={cn('text-xs', campaignTypeInfo.color)}>
                {campaignTypeInfo.label}
              </Badge>
            </div>
          </div>
          <StatusBadge status={idea.status} />
        </div>

        {/* Angle / Description */}
        <p className="text-sm text-muted-foreground mb-4 line-clamp-2">{idea.angle}</p>

        {/* Quick Stats Row */}
        <div className="flex items-center gap-4 text-xs text-muted-foreground mb-4">
          {variableCount > 0 && (
            <span className="flex items-center gap-1">
              <Database className="h-3.5 w-3.5" />
              {variableCount} variables
            </span>
          )}
          {idea.creativeIdeas && idea.creativeIdeas.length > 0 && (
            <span className="flex items-center gap-1">
              <Lightbulb className="h-3.5 w-3.5" />
              {idea.creativeIdeas.length} ideas
            </span>
          )}
          {idea.followUps && idea.followUps.length > 0 && (
            <span className="flex items-center gap-1">
              <Mail className="h-3.5 w-3.5" />
              {idea.followUps.length + 1} emails
            </span>
          )}
          {idea.qaScore && (
            <span
              className={cn(
                'flex items-center gap-1 font-medium',
                idea.qaScore.total >= 85 && 'text-green-600',
                idea.qaScore.total >= 70 && idea.qaScore.total < 85 && 'text-yellow-600',
                idea.qaScore.total < 70 && 'text-red-600'
              )}
            >
              <Star className="h-3.5 w-3.5" />
              QA: {idea.qaScore.total}
            </span>
          )}
        </div>

        {/* Expandable Details */}
        <button
          onClick={() => setExpanded(!expanded)}
          className="flex items-center gap-1 text-xs text-primary hover:underline mb-3"
        >
          {expanded ? (
            <>
              <ChevronUp className="h-3.5 w-3.5" />
              Hide details
            </>
          ) : (
            <>
              <ChevronDown className="h-3.5 w-3.5" />
              Show details
            </>
          )}
        </button>

        {expanded && (
          <div className="space-y-4 pt-3 border-t">
            {/* Strategy Section */}
            {(idea.icpDescription || idea.valueProposition) && (
              <div>
                <div className="flex items-center gap-1.5 text-xs font-semibold text-muted-foreground mb-2">
                  <Target className="h-3.5 w-3.5" />
                  STRATEGY
                </div>
                {idea.icpDescription && (
                  <p className="text-sm mb-2">
                    <span className="font-medium">ICP:</span> {idea.icpDescription}
                  </p>
                )}
                {idea.valueProposition && (
                  <div className="text-sm space-y-1">
                    <p>
                      <span className="font-medium">Business Win:</span>{' '}
                      {idea.valueProposition.business}
                    </p>
                    <p>
                      <span className="font-medium">Personal Win:</span>{' '}
                      {idea.valueProposition.personal}
                    </p>
                  </div>
                )}
                {idea.objections && idea.objections.length > 0 && (
                  <div className="mt-2">
                    <span className="text-sm font-medium">Objections to handle:</span>
                    <div className="flex flex-wrap gap-1 mt-1">
                      {idea.objections.map((obj, i) => (
                        <Badge key={i} variant="outline" className="text-xs">
                          {obj}
                        </Badge>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            )}

            {/* Constraint Box (for creative_ideas) */}
            {idea.constraintBox && idea.constraintBox.length > 0 && (
              <div>
                <div className="flex items-center gap-1.5 text-xs font-semibold text-muted-foreground mb-2">
                  <Lightbulb className="h-3.5 w-3.5" />
                  CONSTRAINT BOX
                </div>
                <div className="flex flex-wrap gap-1">
                  {idea.constraintBox.map((feature, i) => (
                    <Badge key={i} variant="secondary" className="text-xs">
                      {feature}
                    </Badge>
                  ))}
                </div>
              </div>
            )}

            {/* Clay Variables */}
            {idea.variables && variableCount > 0 && (
              <div>
                <div className="flex items-center gap-1.5 text-xs font-semibold text-muted-foreground mb-2">
                  <Database className="h-3.5 w-3.5" />
                  CLAY VARIABLES
                </div>
                <div className="grid grid-cols-2 gap-2 text-xs">
                  {/* Core */}
                  {idea.variables.core?.firstName && (
                    <div className="flex justify-between">
                      <span className="text-muted-foreground">first_name</span>
                      <code className="bg-muted px-1 rounded">{`{{first_name}}`}</code>
                    </div>
                  )}
                  {idea.variables.core?.companyName && (
                    <div className="flex justify-between">
                      <span className="text-muted-foreground">company_name</span>
                      <code className="bg-muted px-1 rounded">{`{{company_name}}`}</code>
                    </div>
                  )}
                  {/* High Signal */}
                  {idea.variables.highSignal?.competitor && (
                    <div className="flex justify-between">
                      <span className="text-muted-foreground">competitor</span>
                      <code className="bg-muted px-1 rounded">{`{{competitor}}`}</code>
                    </div>
                  )}
                  {idea.variables.highSignal?.recentPostTopic && (
                    <div className="flex justify-between">
                      <span className="text-muted-foreground">recent_post</span>
                      <code className="bg-muted px-1 rounded">{`{{recent_post_topic}}`}</code>
                    </div>
                  )}
                  {/* AI Generated */}
                  {idea.variables.aiGenerated?.customerType && (
                    <div className="flex justify-between">
                      <span className="text-muted-foreground">customer_type</span>
                      <code className="bg-muted px-1 rounded">{`{{ai_customer_type}}`}</code>
                    </div>
                  )}
                  {/* Case Study */}
                  {idea.variables.caseStudy?.company && (
                    <div className="flex justify-between">
                      <span className="text-muted-foreground">case_study</span>
                      <code className="bg-muted px-1 rounded">{`{{case_study_company}}`}</code>
                    </div>
                  )}
                </div>
              </div>
            )}

            {/* Email Copy Preview */}
            {idea.email1 && (
              <div>
                <div className="flex items-center gap-1.5 text-xs font-semibold text-muted-foreground mb-2">
                  <FileText className="h-3.5 w-3.5" />
                  EMAIL 1 COPY
                </div>
                <div className="bg-muted/50 rounded-lg p-3 text-sm space-y-2">
                  <div>
                    <span className="text-xs font-medium text-muted-foreground">Subject:</span>
                    <p className="font-medium">{idea.email1.subject}</p>
                  </div>
                  <div>
                    <span className="text-xs font-medium text-muted-foreground">Body:</span>
                    <p className="whitespace-pre-wrap text-muted-foreground">{idea.email1.body}</p>
                  </div>
                  <div>
                    <span className="text-xs font-medium text-muted-foreground">CTA:</span>
                    <p className="text-primary">{idea.email1.cta}</p>
                  </div>
                </div>
              </div>
            )}

            {/* Creative Ideas (for creative_ideas campaign) */}
            {idea.creativeIdeas && idea.creativeIdeas.length > 0 && (
              <div>
                <div className="flex items-center gap-1.5 text-xs font-semibold text-muted-foreground mb-2">
                  <Lightbulb className="h-3.5 w-3.5" />
                  CREATIVE IDEAS
                </div>
                <ul className="space-y-2">
                  {idea.creativeIdeas.map((ci, i) => (
                    <li key={i} className="text-sm pl-3 border-l-2 border-primary/20">
                      <span className="font-medium">{ci.action}</span> using{' '}
                      <Badge variant="outline" className="text-xs mx-1">
                        {ci.feature}
                      </Badge>{' '}
                      targeting {ci.target}—
                      <span className="text-muted-foreground">{ci.benefit}</span>
                    </li>
                  ))}
                </ul>
              </div>
            )}

            {/* Follow-up Sequence */}
            {idea.followUps && idea.followUps.length > 0 && (
              <div>
                <div className="flex items-center gap-1.5 text-xs font-semibold text-muted-foreground mb-2">
                  <Mail className="h-3.5 w-3.5" />
                  FOLLOW-UP SEQUENCE
                </div>
                <div className="flex gap-2">
                  {idea.followUps.map((fu, i) => (
                    <div
                      key={i}
                      className="flex-1 bg-muted/50 rounded p-2 text-xs"
                    >
                      <div className="font-medium">Email {i + 2}</div>
                      <div className="text-muted-foreground">Day {fu.day}</div>
                      <div className="text-muted-foreground truncate">{fu.angle}</div>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* QA Score Breakdown */}
            {idea.qaScore && (
              <div>
                <div className="flex items-center gap-1.5 text-xs font-semibold text-muted-foreground mb-2">
                  <Star className="h-3.5 w-3.5" />
                  QA SCORE: {idea.qaScore.total}/100
                </div>
                <div className="grid grid-cols-3 gap-2 text-xs">
                  <div className="bg-muted/50 rounded p-2">
                    <div className="text-muted-foreground">Situation</div>
                    <div className="font-medium">{idea.qaScore.situationRecognition}/25</div>
                  </div>
                  <div className="bg-muted/50 rounded p-2">
                    <div className="text-muted-foreground">Value</div>
                    <div className="font-medium">{idea.qaScore.valueClarity}/25</div>
                  </div>
                  <div className="bg-muted/50 rounded p-2">
                    <div className="text-muted-foreground">Personal.</div>
                    <div className="font-medium">{idea.qaScore.personalizationQuality}/20</div>
                  </div>
                  <div className="bg-muted/50 rounded p-2">
                    <div className="text-muted-foreground">CTA</div>
                    <div className="font-medium">{idea.qaScore.ctaEffort}/15</div>
                  </div>
                  <div className="bg-muted/50 rounded p-2">
                    <div className="text-muted-foreground">Length</div>
                    <div className="font-medium">{idea.qaScore.length}/10</div>
                  </div>
                  <div className="bg-muted/50 rounded p-2">
                    <div className="text-muted-foreground">Subject</div>
                    <div className="font-medium">{idea.qaScore.subjectLine}/5</div>
                  </div>
                </div>
              </div>
            )}
          </div>
        )}

        {/* Action Buttons */}
        {(isPending || isEditing) && (
          <div className="flex items-center gap-2 pt-3 border-t">
            <Button
              size="sm"
              onClick={handleApprove}
              className="bg-green-600 hover:bg-green-700"
            >
              <Check className="h-4 w-4 mr-1" />
              Approve
            </Button>
            <Button
              size="sm"
              variant="outline"
              onClick={handleReject}
              className="text-red-600 hover:text-red-700 hover:bg-red-50"
            >
              {isEditing ? (
                <>
                  <Edit className="h-4 w-4 mr-1" />
                  Edit
                </>
              ) : (
                <>
                  <X className="h-4 w-4 mr-1" />
                  Reject
                </>
              )}
            </Button>
          </div>
        )}

        {isApproved && (
          <div className="pt-3 border-t">
            <p className="text-sm text-green-600 font-medium">
              Campaign created from this idea
            </p>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
