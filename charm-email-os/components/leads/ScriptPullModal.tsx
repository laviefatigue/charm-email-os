'use client';

import { useState } from 'react';
import {
  Zap,
  Database,
  Search,
  Target,
  AlertCircle,
  Building2,
  Users,
  Briefcase,
  Globe,
  Square,
} from 'lucide-react';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Label } from '@/components/ui/label';
import { Input } from '@/components/ui/input';
import { Card } from '@/components/ui/card';
import type { Campaign } from '@/lib/types';

interface ScriptPullModalProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  campaign?: Campaign;
}

// Placeholder data sources
const DATA_SOURCES = [
  { id: 'apollo', name: 'Apollo', description: 'B2B contact database', available: false },
  { id: 'zoominfo', name: 'ZoomInfo', description: 'Business intelligence', available: false },
  { id: 'linkedin', name: 'LinkedIn Sales Nav', description: 'Professional network', available: false },
  { id: 'clearbit', name: 'Clearbit', description: 'Enrichment & search', available: false },
];

export function ScriptPullModal({ open, onOpenChange, campaign }: ScriptPullModalProps) {
  const [leadCount, setLeadCount] = useState(100);

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-xl">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Zap className="h-5 w-5" />
            Script Pull Configuration
          </DialogTitle>
          <DialogDescription>
            Configure automated lead pulling based on campaign criteria
          </DialogDescription>
        </DialogHeader>

        {/* Coming Soon Banner */}
        <Card className="p-4 bg-amber-50 border-amber-200">
          <div className="flex items-center gap-3">
            <AlertCircle className="h-5 w-5 text-amber-600" />
            <div>
              <p className="font-medium text-amber-800">Feature Coming Soon</p>
              <p className="text-sm text-amber-700">
                Script pull requires backend API integration. This is a preview of the configuration UI.
              </p>
            </div>
          </div>
        </Card>

        {/* Target Criteria */}
        <div className="space-y-4">
          <Label className="text-sm font-semibold flex items-center gap-2">
            <Target className="h-4 w-4" />
            Target Criteria
          </Label>
          <p className="text-xs text-muted-foreground -mt-2">
            Based on campaign: &quot;{campaign?.name || 'Selected Campaign'}&quot;
          </p>

          <div className="grid grid-cols-2 gap-3">
            <Card className="p-3">
              <div className="flex items-center gap-2 text-sm">
                <Building2 className="h-4 w-4 text-muted-foreground" />
                <span className="text-muted-foreground">Industry</span>
              </div>
              <Badge variant="secondary" className="mt-2">
                {campaign?.industry || 'SaaS'}
              </Badge>
            </Card>
            <Card className="p-3">
              <div className="flex items-center gap-2 text-sm">
                <Users className="h-4 w-4 text-muted-foreground" />
                <span className="text-muted-foreground">Segment</span>
              </div>
              <Badge variant="secondary" className="mt-2">
                {campaign?.segment || 'Series A Startups'}
              </Badge>
            </Card>
            <Card className="p-3">
              <div className="flex items-center gap-2 text-sm">
                <Briefcase className="h-4 w-4 text-muted-foreground" />
                <span className="text-muted-foreground">Titles</span>
              </div>
              <div className="flex flex-wrap gap-1 mt-2">
                <Badge variant="outline" className="text-xs">CEO</Badge>
                <Badge variant="outline" className="text-xs">CTO</Badge>
                <Badge variant="outline" className="text-xs">VP Engineering</Badge>
              </div>
            </Card>
            <Card className="p-3">
              <div className="flex items-center gap-2 text-sm">
                <Globe className="h-4 w-4 text-muted-foreground" />
                <span className="text-muted-foreground">Location</span>
              </div>
              <Badge variant="secondary" className="mt-2">
                United States
              </Badge>
            </Card>
          </div>
        </div>

        {/* Lead Count */}
        <div className="space-y-4">
          <div className="flex items-center justify-between">
            <Label className="text-sm font-semibold">Lead Count Target</Label>
            <span className="text-sm font-medium">{leadCount} leads</span>
          </div>
          <input
            type="range"
            value={leadCount}
            onChange={(e) => setLeadCount(Number(e.target.value))}
            max={500}
            min={25}
            step={25}
            className="w-full h-2 bg-muted rounded-lg appearance-none cursor-not-allowed opacity-60"
            disabled
          />
          <div className="flex justify-between text-xs text-muted-foreground">
            <span>25</span>
            <span>500</span>
          </div>
        </div>

        {/* Data Sources */}
        <div className="space-y-3">
          <Label className="text-sm font-semibold flex items-center gap-2">
            <Database className="h-4 w-4" />
            Data Sources
          </Label>
          <div className="grid grid-cols-2 gap-2">
            {DATA_SOURCES.map((source) => (
              <Card
                key={source.id}
                className="p-3 cursor-not-allowed opacity-60"
              >
                <div className="flex items-start gap-2">
                  <Square className="h-4 w-4 text-muted-foreground mt-0.5" />
                  <div>
                    <p className="text-sm font-medium">{source.name}</p>
                    <p className="text-xs text-muted-foreground">{source.description}</p>
                    <Badge variant="outline" className="text-xs mt-1 text-amber-600">
                      API Not Connected
                    </Badge>
                  </div>
                </div>
              </Card>
            ))}
          </div>
        </div>

        {/* Additional Filters */}
        <div className="space-y-3">
          <Label className="text-sm font-semibold flex items-center gap-2">
            <Search className="h-4 w-4" />
            Additional Filters
          </Label>
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1.5">
              <Label className="text-xs text-muted-foreground">Company Size</Label>
              <Input placeholder="e.g., 50-200" disabled />
            </div>
            <div className="space-y-1.5">
              <Label className="text-xs text-muted-foreground">Keywords</Label>
              <Input placeholder="e.g., AI, automation" disabled />
            </div>
          </div>
        </div>

        <DialogFooter className="gap-2">
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button disabled>
            <Zap className="h-4 w-4 mr-2" />
            Run Script
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
