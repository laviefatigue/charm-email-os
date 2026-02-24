'use client';

import { useEffect, useState, useCallback } from 'react';
import {
  RefreshCw,
  Activity,
  TrendingUp,
  TrendingDown,
  AlertTriangle,
  CheckCircle,
  XCircle,
  Server,
  Mail,
  Shield,
} from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Progress } from '@/components/ui/progress';
import { HealthScoreGauge } from '@/components/charts/HealthScoreGauge';
import { KillVelocityChart } from '@/components/charts/KillVelocityChart';
import { KillBreakdownPie } from '@/components/charts/KillBreakdownPie';
import { VolumeHistoryChart } from '@/components/charts/VolumeHistoryChart';
import { formatNumber, formatPercent, formatRelativeTime, cn } from '@/lib/utils';
import type { DashboardData } from '@/lib/types';

export default function DashboardPage() {
  const [data, setData] = useState<DashboardData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [lastFetch, setLastFetch] = useState<Date | null>(null);

  const fetchData = useCallback(async () => {
    try {
      setLoading(true);
      const response = await fetch('/api/dashboard');
      if (!response.ok) {
        throw new Error(`API error: ${response.status}`);
      }
      const result = await response.json();
      setData(result);
      setLastFetch(new Date());
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to fetch data');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchData();

    // Auto-refresh every 5 minutes
    const interval = setInterval(fetchData, 300000);
    return () => clearInterval(interval);
  }, [fetchData]);

  if (loading && !data) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gradient-to-br from-blue-50 via-white to-purple-50">
        <div className="flex items-center gap-3">
          <RefreshCw className="h-8 w-8 animate-spin text-blue-600" />
          <span className="text-xl text-gray-700 font-medium">Loading Executive Dashboard...</span>
        </div>
      </div>
    );
  }

  if (error && !data) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gradient-to-br from-blue-50 via-white to-purple-50">
        <Card className="w-full max-w-md">
          <CardHeader>
            <CardTitle className="text-red-600">Connection Error</CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-gray-600">{error}</p>
            <button
              onClick={fetchData}
              className="mt-4 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors"
            >
              Retry Connection
            </button>
          </CardContent>
        </Card>
      </div>
    );
  }

  if (!data) return null;

  const { infrastructure, killVelocity, killBreakdown, volumeHistory, client } = data;

  // Calculate key metrics
  const totalInboxes = infrastructure.total_inboxes;
  const liveInboxes = infrastructure.live_inboxes;
  const deadInboxes = infrastructure.dead_inboxes;
  const healthScore = infrastructure.avg_health_score;
  const survivalRate = totalInboxes > 0 ? (liveInboxes / totalInboxes) * 100 : 0;
  const deployedInboxes = infrastructure.lifecycle_distribution.deployed;
  const reserveInboxes = infrastructure.lifecycle_distribution.reserve;
  const incubatingInboxes = infrastructure.lifecycle_distribution.incubating;
  const warningInboxes = infrastructure.lifecycle_distribution.warning;

  return (
    <div className="min-h-screen bg-gradient-to-br from-blue-50 via-white to-purple-50">
      {/* Header */}
      <div className="bg-white border-b border-gray-200 shadow-sm">
        <div className="max-w-7xl mx-auto px-6 py-6">
          <div className="flex items-center justify-between">
            <div>
              <h1 className="text-3xl font-bold text-gray-900">
                {client?.name || 'Charm'} Infrastructure
              </h1>
              <p className="text-gray-600 mt-1">Executive Health Dashboard</p>
            </div>
            <div className="flex items-center gap-4">
              {lastFetch && (
                <span className="text-sm text-gray-500">
                  Updated {formatRelativeTime(lastFetch.toISOString())}
                </span>
              )}
              <button
                onClick={fetchData}
                disabled={loading}
                className={cn(
                  "p-2 rounded-lg transition-colors",
                  loading
                    ? "bg-gray-100 text-gray-400 cursor-not-allowed"
                    : "bg-blue-600 text-white hover:bg-blue-700"
                )}
              >
                <RefreshCw className={cn("h-5 w-5", loading && "animate-spin")} />
              </button>
            </div>
          </div>
        </div>
      </div>

      <div className="max-w-7xl mx-auto px-6 py-8 space-y-8">
        {/* Key Metrics Row */}
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
          {/* Total Inboxes */}
          <Card className="bg-gradient-to-br from-blue-500 to-blue-600 text-white">
            <CardHeader className="pb-3">
              <CardTitle className="text-sm font-medium text-blue-100">
                Total Inboxes
              </CardTitle>
            </CardHeader>
            <CardContent>
              <div className="flex items-center justify-between">
                <div>
                  <div className="text-4xl font-bold">{formatNumber(totalInboxes)}</div>
                  <div className="text-sm text-blue-100 mt-1">
                    {formatNumber(liveInboxes)} live · {formatNumber(deadInboxes)} retired
                  </div>
                </div>
                <Server className="h-12 w-12 text-blue-200" />
              </div>
            </CardContent>
          </Card>

          {/* Health Score */}
          <Card className="bg-gradient-to-br from-green-500 to-green-600 text-white">
            <CardHeader className="pb-3">
              <CardTitle className="text-sm font-medium text-green-100">
                Health Score
              </CardTitle>
            </CardHeader>
            <CardContent>
              <div className="flex items-center justify-between">
                <div>
                  <div className="text-4xl font-bold">{Math.round(healthScore)}</div>
                  <div className="text-sm text-green-100 mt-1">
                    {healthScore >= 80 ? 'Excellent' : healthScore >= 60 ? 'Good' : 'Needs Attention'}
                  </div>
                </div>
                <Activity className="h-12 w-12 text-green-200" />
              </div>
            </CardContent>
          </Card>

          {/* Survival Rate */}
          <Card className="bg-gradient-to-br from-purple-500 to-purple-600 text-white">
            <CardHeader className="pb-3">
              <CardTitle className="text-sm font-medium text-purple-100">
                Survival Rate
              </CardTitle>
            </CardHeader>
            <CardContent>
              <div className="flex items-center justify-between">
                <div>
                  <div className="text-4xl font-bold">{formatPercent(survivalRate)}</div>
                  <div className="text-sm text-purple-100 mt-1">
                    {formatNumber(liveInboxes)} of {formatNumber(totalInboxes)} active
                  </div>
                </div>
                <CheckCircle className="h-12 w-12 text-purple-200" />
              </div>
            </CardContent>
          </Card>

          {/* Domain Health */}
          <Card className={cn(
            "text-white",
            infrastructure.flagged_domains > 0
              ? "bg-gradient-to-br from-red-500 to-red-600"
              : "bg-gradient-to-br from-teal-500 to-teal-600"
          )}>
            <CardHeader className="pb-3">
              <CardTitle className={cn(
                "text-sm font-medium",
                infrastructure.flagged_domains > 0 ? "text-red-100" : "text-teal-100"
              )}>
                Domain Status
              </CardTitle>
            </CardHeader>
            <CardContent>
              <div className="flex items-center justify-between">
                <div>
                  <div className="text-4xl font-bold">
                    {infrastructure.flagged_domains > 0
                      ? formatNumber(infrastructure.flagged_domains)
                      : formatNumber(infrastructure.clean_domains)
                    }
                  </div>
                  <div className={cn(
                    "text-sm mt-1",
                    infrastructure.flagged_domains > 0 ? "text-red-100" : "text-teal-100"
                  )}>
                    {infrastructure.flagged_domains > 0 ? 'Flagged' : 'Clean'} domains
                  </div>
                </div>
                {infrastructure.flagged_domains > 0 ? (
                  <AlertTriangle className="h-12 w-12 text-red-200" />
                ) : (
                  <Shield className="h-12 w-12 text-teal-200" />
                )}
              </div>
            </CardContent>
          </Card>
        </div>

        {/* Health Score & Distribution */}
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          {/* Health Score Gauge */}
          <Card>
            <CardHeader>
              <CardTitle>Infrastructure Health</CardTitle>
              <CardDescription>Overall system performance</CardDescription>
            </CardHeader>
            <CardContent>
              <HealthScoreGauge score={healthScore} label="Average Health Score" />
            </CardContent>
          </Card>

          {/* Health Distribution */}
          <Card>
            <CardHeader>
              <CardTitle>Health Distribution</CardTitle>
              <CardDescription>Inbox health breakdown</CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="space-y-3">
                <div>
                  <div className="flex justify-between text-sm mb-1">
                    <span className="font-medium text-green-700">Healthy</span>
                    <span className="text-gray-600">{formatNumber(infrastructure.health_distribution.healthy)}</span>
                  </div>
                  <Progress
                    value={(infrastructure.health_distribution.healthy / infrastructure.health_distribution.total) * 100}
                    className="h-2"
                  />
                </div>
                <div>
                  <div className="flex justify-between text-sm mb-1">
                    <span className="font-medium text-yellow-600">Good</span>
                    <span className="text-gray-600">{formatNumber(infrastructure.health_distribution.good)}</span>
                  </div>
                  <Progress
                    value={(infrastructure.health_distribution.good / infrastructure.health_distribution.total) * 100}
                    className="h-2"
                  />
                </div>
                <div>
                  <div className="flex justify-between text-sm mb-1">
                    <span className="font-medium text-orange-600">Warning</span>
                    <span className="text-gray-600">{formatNumber(infrastructure.health_distribution.warning)}</span>
                  </div>
                  <Progress
                    value={(infrastructure.health_distribution.warning / infrastructure.health_distribution.total) * 100}
                    className="h-2"
                  />
                </div>
                <div>
                  <div className="flex justify-between text-sm mb-1">
                    <span className="font-medium text-red-600">Critical</span>
                    <span className="text-gray-600">{formatNumber(infrastructure.health_distribution.critical)}</span>
                  </div>
                  <Progress
                    value={(infrastructure.health_distribution.critical / infrastructure.health_distribution.total) * 100}
                    className="h-2"
                  />
                </div>
              </div>
            </CardContent>
          </Card>

          {/* Lifecycle Distribution */}
          <Card>
            <CardHeader>
              <CardTitle>Lifecycle Status</CardTitle>
              <CardDescription>Inbox deployment stages</CardDescription>
            </CardHeader>
            <CardContent>
              <div className="space-y-4">
                <div className="flex items-center justify-between py-2 border-b">
                  <div className="flex items-center gap-2">
                    <div className="w-3 h-3 rounded-full bg-blue-500"></div>
                    <span className="text-sm font-medium">Deployed</span>
                  </div>
                  <Badge variant="default">{formatNumber(deployedInboxes)}</Badge>
                </div>
                <div className="flex items-center justify-between py-2 border-b">
                  <div className="flex items-center gap-2">
                    <div className="w-3 h-3 rounded-full bg-green-500"></div>
                    <span className="text-sm font-medium">Reserve</span>
                  </div>
                  <Badge variant="success">{formatNumber(reserveInboxes)}</Badge>
                </div>
                <div className="flex items-center justify-between py-2 border-b">
                  <div className="flex items-center gap-2">
                    <div className="w-3 h-3 rounded-full bg-yellow-500"></div>
                    <span className="text-sm font-medium">Incubating</span>
                  </div>
                  <Badge variant="warning">{formatNumber(incubatingInboxes)}</Badge>
                </div>
                <div className="flex items-center justify-between py-2">
                  <div className="flex items-center gap-2">
                    <div className="w-3 h-3 rounded-full bg-orange-500"></div>
                    <span className="text-sm font-medium">Warning</span>
                  </div>
                  <Badge variant="danger">{formatNumber(warningInboxes)}</Badge>
                </div>
              </div>
            </CardContent>
          </Card>
        </div>

        {/* Charts Row */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          {/* Kill Velocity */}
          {killVelocity && (
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center justify-between">
                  <span>Kill Velocity</span>
                  <div className="flex items-center gap-2">
                    {killVelocity.trend === 'up' && <TrendingUp className="h-5 w-5 text-red-500" />}
                    {killVelocity.trend === 'down' && <TrendingDown className="h-5 w-5 text-green-500" />}
                    <Badge variant={killVelocity.trend === 'up' ? 'danger' : 'success'}>
                      {killVelocity.totalDeaths7d} deaths (7d)
                    </Badge>
                  </div>
                </CardTitle>
                <CardDescription>Weekly inbox retirement trend</CardDescription>
              </CardHeader>
              <CardContent>
                <KillVelocityChart data={killVelocity} />
              </CardContent>
            </Card>
          )}

          {/* Kill Breakdown */}
          {killBreakdown && killBreakdown.total_kills > 0 && (
            <Card>
              <CardHeader>
                <CardTitle>Kill Trigger Analysis</CardTitle>
                <CardDescription>Why inboxes are retiring</CardDescription>
              </CardHeader>
              <CardContent>
                <KillBreakdownPie data={killBreakdown} />
              </CardContent>
            </Card>
          )}
        </div>

        {/* Volume History */}
        {volumeHistory && volumeHistory.snapshots.length > 0 && (
          <Card>
            <CardHeader>
              <CardTitle>Email Volume & Capacity</CardTitle>
              <CardDescription>30-day sending history</CardDescription>
            </CardHeader>
            <CardContent>
              <VolumeHistoryChart data={volumeHistory} />
            </CardContent>
          </Card>
        )}

        {/* Provider Breakdown */}
        <Card>
          <CardHeader>
            <CardTitle>Email Provider Distribution</CardTitle>
            <CardDescription>Inbox allocation by provider</CardDescription>
          </CardHeader>
          <CardContent>
            <div className="space-y-3">
              {infrastructure.providers.map((provider) => (
                <div key={provider.name} className="flex items-center justify-between py-3 border-b last:border-0">
                  <div className="flex-1">
                    <div className="flex items-center gap-3">
                      <Mail className="h-5 w-5 text-gray-400" />
                      <span className="font-medium text-gray-900">{provider.name}</span>
                    </div>
                  </div>
                  <div className="flex items-center gap-6">
                    <div className="text-right">
                      <div className="text-sm text-gray-500">Live</div>
                      <div className="text-lg font-semibold text-green-600">
                        {formatNumber(provider.live_count)}
                      </div>
                    </div>
                    <div className="text-right">
                      <div className="text-sm text-gray-500">Dead</div>
                      <div className="text-lg font-semibold text-red-600">
                        {formatNumber(provider.dead_count)}
                      </div>
                    </div>
                    <div className="text-right">
                      <div className="text-sm text-gray-500">Health</div>
                      <div className={cn(
                        "text-lg font-semibold",
                        provider.avg_health_score >= 80 ? "text-green-600" :
                        provider.avg_health_score >= 60 ? "text-yellow-600" :
                        provider.avg_health_score >= 40 ? "text-orange-600" :
                        "text-red-600"
                      )}>
                        {Math.round(provider.avg_health_score)}
                      </div>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>

        {/* Footer */}
        <div className="text-center text-sm text-gray-500 py-4">
          <p>Last synced: {infrastructure.last_sync ? formatRelativeTime(infrastructure.last_sync) : 'Unknown'}</p>
          <p className="mt-1">Data source: {infrastructure.sync_source}</p>
        </div>
      </div>
    </div>
  );
}
