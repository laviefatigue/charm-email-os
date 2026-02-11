'use client';

import { useEffect, useState } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Progress } from '@/components/ui/progress';
import { Badge } from '@/components/ui/badge';
import { cn } from '@/lib/utils';
import { strategyApi, JobPhasesResponse, GenerationPhase } from '@/lib/api';
import {
  CheckCircle2,
  Circle,
  Loader2,
  XCircle,
  AlertCircle,
  FileText,
  Mail,
} from 'lucide-react';

interface GenerationProgressProps {
  jobId: string;
  onComplete?: () => void;
  onError?: (error: string) => void;
  className?: string;
}

const POLL_INTERVAL = 2000; // 2 seconds

function formatTime(seconds: number): string {
  if (seconds < 60) {
    return `${seconds}s`;
  }
  const minutes = Math.floor(seconds / 60);
  const remainingSeconds = seconds % 60;
  return remainingSeconds > 0 ? `${minutes}m ${remainingSeconds}s` : `${minutes}m`;
}

function getPhaseIcon(phase: GenerationPhase) {
  if (phase.status === 'completed') {
    return <CheckCircle2 className="w-5 h-5 text-green-500" />;
  }
  if (phase.status === 'failed') {
    return <XCircle className="w-5 h-5 text-red-500" />;
  }
  if (phase.status === 'processing') {
    return <Loader2 className="w-5 h-5 text-blue-500 animate-spin" />;
  }
  return <Circle className="w-5 h-5 text-muted-foreground" />;
}

function getPhaseLabel(phase: GenerationPhase): string {
  if (phase.type === 'scaffold') {
    return 'Strategy Scaffold';
  }
  return `Campaign ${phase.number}`;
}

function getPhaseDescription(phase: GenerationPhase): string {
  if (phase.type === 'scaffold') {
    return 'ICP mapping, variables, campaign angles';
  }
  const angleNames: Record<number, string> = {
    1: 'Custom Signal',
    2: 'Persona Pain',
    3: 'Case Study',
    4: 'Risk/Efficiency',
  };
  return angleNames[phase.number || 1] || 'Email generation';
}

export function GenerationProgress({
  jobId,
  onComplete,
  onError,
  className,
}: GenerationProgressProps) {
  const [data, setData] = useState<JobPhasesResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [polling, setPolling] = useState(true);

  useEffect(() => {
    if (!polling) return;

    const fetchStatus = async () => {
      try {
        const response = await strategyApi.getJobPhases(jobId);
        setData(response);

        // Check if job is complete or failed
        if (response.jobStatus === 'review' || response.jobStatus === 'completed') {
          setPolling(false);
          onComplete?.();
        } else if (response.jobStatus === 'failed') {
          setPolling(false);
          const errorMsg = response.errorMessage || 'Generation failed';
          setError(errorMsg);
          onError?.(errorMsg);
        }
      } catch (err) {
        const errorMsg = err instanceof Error ? err.message : 'Failed to fetch status';
        setError(errorMsg);
        setPolling(false);
        onError?.(errorMsg);
      }
    };

    // Initial fetch
    fetchStatus();

    // Set up polling
    const interval = setInterval(fetchStatus, POLL_INTERVAL);

    return () => clearInterval(interval);
  }, [jobId, polling, onComplete, onError]);

  if (error) {
    return (
      <Card className={cn('border-red-200 bg-red-50', className)}>
        <CardHeader className="pb-2">
          <CardTitle className="flex items-center gap-2 text-red-700">
            <AlertCircle className="w-5 h-5" />
            Generation Failed
          </CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-sm text-red-600">{error}</p>
        </CardContent>
      </Card>
    );
  }

  if (!data) {
    return (
      <Card className={className}>
        <CardContent className="flex items-center justify-center py-8">
          <Loader2 className="w-6 h-6 animate-spin text-muted-foreground" />
          <span className="ml-2 text-muted-foreground">Loading...</span>
        </CardContent>
      </Card>
    );
  }

  const { progress, phases } = data;
  const isComplete = data.jobStatus === 'review' || data.jobStatus === 'completed';

  return (
    <Card className={cn(isComplete ? 'border-green-200 bg-green-50/50' : '', className)}>
      <CardHeader className="pb-3">
        <CardTitle className="flex items-center justify-between">
          <span className="flex items-center gap-2">
            {isComplete ? (
              <CheckCircle2 className="w-5 h-5 text-green-500" />
            ) : (
              <Loader2 className="w-5 h-5 animate-spin text-blue-500" />
            )}
            {isComplete ? 'Generation Complete' : 'Strategy Generation In Progress'}
          </span>
          {!isComplete && progress.estimatedRemainingSeconds > 0 && (
            <Badge variant="outline" className="text-xs">
              ~{formatTime(progress.estimatedRemainingSeconds)} remaining
            </Badge>
          )}
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        {/* Overall Progress Bar */}
        <div className="space-y-2">
          <div className="flex justify-between text-sm">
            <span className="text-muted-foreground">Overall Progress</span>
            <span className="font-medium">{progress.percent}%</span>
          </div>
          <Progress value={progress.percent} className="h-2" />
        </div>

        {/* Phase List */}
        <div className="space-y-3 pt-2">
          {phases.map((phase) => (
            <div
              key={phase.id}
              className={cn(
                'flex items-start gap-3 p-3 rounded-lg border',
                phase.status === 'completed' && 'bg-green-50/50 border-green-200',
                phase.status === 'processing' && 'bg-blue-50/50 border-blue-200',
                phase.status === 'failed' && 'bg-red-50/50 border-red-200',
                phase.status === 'pending' && 'bg-muted/30 border-muted'
              )}
            >
              <div className="mt-0.5">{getPhaseIcon(phase)}</div>
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2">
                  {phase.type === 'scaffold' ? (
                    <FileText className="w-4 h-4 text-muted-foreground" />
                  ) : (
                    <Mail className="w-4 h-4 text-muted-foreground" />
                  )}
                  <span className="font-medium text-sm">{getPhaseLabel(phase)}</span>
                  <Badge
                    variant={
                      phase.status === 'completed'
                        ? 'default'
                        : phase.status === 'failed'
                        ? 'destructive'
                        : 'secondary'
                    }
                    className="text-xs capitalize"
                  >
                    {phase.status}
                  </Badge>
                </div>
                <p className="text-xs text-muted-foreground mt-1">
                  {getPhaseDescription(phase)}
                </p>
                {phase.errorMessage && (
                  <p className="text-xs text-red-600 mt-1">{phase.errorMessage}</p>
                )}
              </div>
            </div>
          ))}

          {/* Show placeholder if no phases yet */}
          {phases.length === 0 && (
            <div className="flex items-center gap-3 p-3 rounded-lg border bg-muted/30">
              <Loader2 className="w-5 h-5 animate-spin text-muted-foreground" />
              <div>
                <span className="font-medium text-sm">Initializing...</span>
                <p className="text-xs text-muted-foreground">Setting up generation phases</p>
              </div>
            </div>
          )}
        </div>

        {/* Status Summary */}
        {progress.totalPhases > 0 && (
          <div className="flex gap-4 text-xs text-muted-foreground pt-2 border-t">
            <span>
              {progress.completedPhases}/{progress.totalPhases} phases complete
            </span>
            {progress.failedPhases > 0 && (
              <span className="text-red-500">{progress.failedPhases} failed</span>
            )}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
