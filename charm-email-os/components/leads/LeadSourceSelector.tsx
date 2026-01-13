'use client';

import { Upload, Zap, Info } from 'lucide-react';
import { Card } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '@/components/ui/tooltip';
import { cn } from '@/lib/utils';

export type LeadSourceOption = 'upload' | 'script';

interface LeadSourceSelectorProps {
  selectedSource: LeadSourceOption;
  onSourceChange: (source: LeadSourceOption) => void;
  onProceed: () => void;
  campaignSegment?: string;
  campaignIndustry?: string;
}

export function LeadSourceSelector({
  selectedSource,
  onSourceChange,
  onProceed,
  campaignSegment,
  campaignIndustry,
}: LeadSourceSelectorProps) {
  return (
    <div className="space-y-6">
      <div className="space-y-3">
        {/* Manual Upload Option */}
        <Card
          className={cn(
            'p-4 cursor-pointer transition-all border-2',
            selectedSource === 'upload'
              ? 'border-primary bg-primary/5'
              : 'border-transparent hover:border-muted-foreground/30'
          )}
          onClick={() => onSourceChange('upload')}
        >
          <div className="flex items-start gap-4">
            <div
              className={cn(
                'flex h-10 w-10 items-center justify-center rounded-lg',
                selectedSource === 'upload' ? 'bg-primary text-primary-foreground' : 'bg-muted'
              )}
            >
              <Upload className="h-5 w-5" />
            </div>
            <div className="flex-1">
              <div className="flex items-center gap-2">
                <h3 className="font-semibold">Manual CSV Upload</h3>
              </div>
              <p className="text-sm text-muted-foreground mt-1">
                Upload a CSV file with lead data. You&apos;ll map columns to lead fields before importing.
              </p>
              <div className="flex flex-wrap gap-2 mt-3">
                <Badge variant="outline" className="text-xs">
                  Custom lists
                </Badge>
                <Badge variant="outline" className="text-xs">
                  Purchased leads
                </Badge>
                <Badge variant="outline" className="text-xs">
                  Event attendees
                </Badge>
              </div>
            </div>
            <div
              className={cn(
                'h-5 w-5 rounded-full border-2 flex items-center justify-center',
                selectedSource === 'upload' ? 'border-primary' : 'border-muted-foreground/30'
              )}
            >
              {selectedSource === 'upload' && <div className="h-2.5 w-2.5 rounded-full bg-primary" />}
            </div>
          </div>
        </Card>

        {/* Script Pull Option */}
        <Card
          className={cn(
            'p-4 cursor-pointer transition-all border-2',
            selectedSource === 'script'
              ? 'border-primary bg-primary/5'
              : 'border-transparent hover:border-muted-foreground/30'
          )}
          onClick={() => onSourceChange('script')}
        >
          <div className="flex items-start gap-4">
            <div
              className={cn(
                'flex h-10 w-10 items-center justify-center rounded-lg',
                selectedSource === 'script' ? 'bg-primary text-primary-foreground' : 'bg-muted'
              )}
            >
              <Zap className="h-5 w-5" />
            </div>
            <div className="flex-1">
              <div className="flex items-center gap-2">
                <h3 className="font-semibold">Automated Script Pull</h3>
                <Badge variant="secondary" className="text-xs">
                  Coming Soon
                </Badge>
              </div>
              <p className="text-sm text-muted-foreground mt-1">
                Automatically pull leads from external databases and APIs based on campaign targeting criteria.
              </p>
              {(campaignSegment || campaignIndustry) && (
                <div className="mt-3 p-2 bg-muted rounded text-xs">
                  <span className="text-muted-foreground">Will target: </span>
                  {campaignIndustry && <Badge variant="outline" className="text-xs mr-1">{campaignIndustry}</Badge>}
                  {campaignSegment && <Badge variant="outline" className="text-xs">{campaignSegment}</Badge>}
                </div>
              )}
              <div className="flex flex-wrap gap-2 mt-3">
                <Badge variant="outline" className="text-xs text-muted-foreground">
                  External Sources
                </Badge>
                <Badge variant="outline" className="text-xs text-muted-foreground">
                  Auto-enrichment
                </Badge>
                <TooltipProvider>
                  <Tooltip>
                    <TooltipTrigger asChild>
                      <Badge variant="outline" className="text-xs text-muted-foreground gap-1">
                        <Info className="h-3 w-3" />
                        API Required
                      </Badge>
                    </TooltipTrigger>
                    <TooltipContent>
                      <p>Script pull requires backend API integration</p>
                    </TooltipContent>
                  </Tooltip>
                </TooltipProvider>
              </div>
            </div>
            <div
              className={cn(
                'h-5 w-5 rounded-full border-2 flex items-center justify-center',
                selectedSource === 'script' ? 'border-primary' : 'border-muted-foreground/30'
              )}
            >
              {selectedSource === 'script' && <div className="h-2.5 w-2.5 rounded-full bg-primary" />}
            </div>
          </div>
        </Card>
      </div>

      <div className="flex justify-end">
        <Button onClick={onProceed} disabled={selectedSource === 'script'}>
          {selectedSource === 'upload' ? 'Upload CSV' : 'Configure Script'}
        </Button>
      </div>
    </div>
  );
}
