'use client';

import {
  Lightbulb,
  Target,
  Users,
  TrendingUp,
  Shield,
  FileText,
  ChevronDown,
  ChevronUp,
} from 'lucide-react';
import { useState } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';
import type { StrategyConsiderations, CampaignSequence, CampaignAngle } from '@/lib/api';

interface StrategyConsiderationPanelProps {
  considerations: StrategyConsiderations;
  sequence?: CampaignSequence;
  className?: string;
}

// Map onboarding input field names to display labels
const INPUT_LABELS: Record<string, string> = {
  target_customer: 'Target Customer',
  job_titles: 'Job Titles',
  segments: 'Segments',
  personas: 'Personas',
  roi_results: 'ROI Results',
  customer_voice: 'Customer Voice',
  case_study_company: 'Case Study',
  case_study_result: 'Case Study Result',
  pain_points: 'Pain Points',
  buying_triggers: 'Buying Triggers',
  success_metrics: 'Success Metrics',
  core_product: 'Core Product',
  industry: 'Industry',
  tone_style: 'Tone & Style',
  acv: 'ACV',
  sales_cycle_length: 'Sales Cycle',
};

// Map campaign angles to display info
const ANGLE_INFO: Record<CampaignAngle, { label: string; icon: typeof Lightbulb; color: string }> = {
  custom_signal: {
    label: 'Research Signal',
    icon: Target,
    color: 'text-blue-600 bg-blue-50',
  },
  persona_pain: {
    label: 'Persona Pain',
    icon: Users,
    color: 'text-purple-600 bg-purple-50',
  },
  case_study: {
    label: 'Case Study Proof',
    icon: TrendingUp,
    color: 'text-green-600 bg-green-50',
  },
  risk_efficiency: {
    label: 'Risk/Efficiency',
    icon: Shield,
    color: 'text-orange-600 bg-orange-50',
  },
};

function formatInputLabel(input: string): string {
  return INPUT_LABELS[input] || input.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
}

export function StrategyConsiderationPanel({
  considerations,
  sequence,
  className,
}: StrategyConsiderationPanelProps) {
  const [isExpanded, setIsExpanded] = useState(true);

  // Find the mapping for this specific sequence if provided
  const campaignMapping = sequence
    ? considerations.campaignMappings?.find(
        m => m.campaignId === sequence.id || m.campaignIndex === (sequence.generationRound - 1)
      )
    : null;

  // Get angle info for this campaign
  const angleInfo = sequence?.campaignAngle
    ? ANGLE_INFO[sequence.campaignAngle]
    : campaignMapping?.angle
      ? ANGLE_INFO[campaignMapping.angle]
      : null;

  return (
    <Card className={cn('border-amber-200 bg-amber-50/50', className)}>
      <CardHeader className="pb-2">
        <div className="flex items-center justify-between">
          <CardTitle className="text-sm flex items-center gap-2">
            <div className="flex h-6 w-6 items-center justify-center rounded bg-amber-100">
              <Lightbulb className="w-3.5 h-3.5 text-amber-600" />
            </div>
            Strategy Inputs Considered
          </CardTitle>
          <Button
            variant="ghost"
            size="sm"
            className="h-7 w-7 p-0"
            onClick={() => setIsExpanded(!isExpanded)}
          >
            {isExpanded ? (
              <ChevronUp className="h-4 w-4" />
            ) : (
              <ChevronDown className="h-4 w-4" />
            )}
          </Button>
        </div>
      </CardHeader>

      {isExpanded && (
        <CardContent className="space-y-4 pt-2">
          {/* Campaign Angle Badge */}
          {angleInfo && (
            <div className="flex items-center gap-2">
              <span className="text-xs font-medium text-amber-700">Campaign Angle:</span>
              <div className={cn('flex items-center gap-1.5 px-2 py-0.5 rounded', angleInfo.color)}>
                <angleInfo.icon className="w-3 h-3" />
                <span className="text-xs font-medium">{angleInfo.label}</span>
              </div>
            </div>
          )}

          {/* Target Persona/Segment */}
          {(sequence?.targetPersona || sequence?.targetSegment || campaignMapping?.targetPersona || campaignMapping?.targetSegment) && (
            <div>
              <h4 className="text-xs font-semibold text-amber-700 mb-1.5">Target</h4>
              <div className="flex flex-wrap gap-2">
                {(sequence?.targetPersona || campaignMapping?.targetPersona) && (
                  <Badge variant="outline" className="text-xs bg-white border-amber-300">
                    <Users className="w-3 h-3 mr-1" />
                    {sequence?.targetPersona || campaignMapping?.targetPersona}
                  </Badge>
                )}
                {(sequence?.targetSegment || campaignMapping?.targetSegment) && (
                  <Badge variant="outline" className="text-xs bg-white border-amber-300">
                    <Target className="w-3 h-3 mr-1" />
                    {sequence?.targetSegment || campaignMapping?.targetSegment}
                  </Badge>
                )}
              </div>
            </div>
          )}

          {/* Onboarding Inputs Used */}
          <div>
            <h4 className="text-xs font-semibold text-amber-700 mb-1.5">Onboarding Data Used</h4>
            <div className="flex flex-wrap gap-1.5">
              {considerations.inputsUsed.map((input) => (
                <Badge
                  key={input}
                  variant="outline"
                  className="text-xs bg-white border-amber-200 text-amber-800"
                >
                  {formatInputLabel(input)}
                </Badge>
              ))}
            </div>
          </div>

          {/* Campaign-Specific Reasoning */}
          {campaignMapping?.reasoning && (
            <div className="pt-2 border-t border-amber-200">
              <h4 className="text-xs font-semibold text-amber-700 mb-1.5 flex items-center gap-1">
                <FileText className="w-3 h-3" />
                Why This Angle
              </h4>
              <p className="text-sm text-amber-800 leading-relaxed">
                {campaignMapping.reasoning}
              </p>
              {campaignMapping.influencedBy && campaignMapping.influencedBy.length > 0 && (
                <div className="mt-2 text-xs text-amber-600">
                  <span className="font-medium">Based on: </span>
                  {campaignMapping.influencedBy.map(formatInputLabel).join(', ')}
                </div>
              )}
            </div>
          )}
        </CardContent>
      )}
    </Card>
  );
}
