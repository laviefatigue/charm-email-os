'use client';

/**
 * Executive Dashboard V2 - Improved Design
 *
 * Key Improvements:
 * - Contextual descriptions for all metrics
 * - Data quality indicators throughout
 * - Empty states for all visualizations
 * - Skeleton loading states
 * - Always-visible Kill Analytics layout
 * - Tooltips explaining complex metrics
 * - Trend indicators and benchmarks
 */

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
  Info,
  Clock,
  Database,
  Calendar,
  BarChart3,
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

export default function DashboardPageV2() {
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
    const interval = setInterval(fetchData, 300000); // 5 min
    return () => clearInterval(interval);
  }, [fetchData]);

  // Skeleton Loading State
  if (loading && !data) {
    return (
      <div className="min-h-screen bg-gradient-to-br from-blue-50 via-white to-purple-50">
        <div className="bg-white border-b border-gray-200 shadow-sm">
          <div className="max-w-7xl mx-auto px-6 py-6">
            <div className="animate-pulse">
              <div className="h-8 bg-gray-200 rounded w-64 mb-2"></div>
              <div className="h-4 bg-gray-200 rounded w-48"></div>
            </div>
          </div>
        </div>

        <div className="max-w-7xl mx-auto px-6 py-8 space-y-8">
          {/* Metric Cards Skeleton */}
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
            {[1, 2, 3, 4].map((i) => (
              <Card key={i} className="animate-pulse">
                <CardHeader className="pb-3">
                  <div className="h-4 bg-gray-200 rounded w-24"></div>
                </CardHeader>
                <CardContent>
                  <div className="flex items-center justify-between">
                    <div className="flex-1">
                      <div className="h-10 bg-gray-200 rounded w-16 mb-2"></div>
                      <div className="h-3 bg-gray-200 rounded w-32"></div>
                    </div>
                    <div className="h-12 w-12 bg-gray-200 rounded-full"></div>
                  </div>
                </CardContent>
              </Card>
            ))}
          </div>

          {/* Charts Skeleton */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            {[1, 2].map((i) => (
              <Card key={i} className="animate-pulse">
                <CardHeader>
                  <div className="h-5 bg-gray-200 rounded w-32 mb-2"></div>
                  <div className="h-3 bg-gray-200 rounded w-48"></div>
                </CardHeader>
                <CardContent>
                  <div className="h-64 bg-gray-100 rounded"></div>
                </CardContent>
              </Card>
            ))}
          </div>
        </div>
      </div>
    );
  }

  if (error && !data) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gradient-to-br from-blue-50 via-white to-purple-50">
        <Card className="w-full max-w-md">
          <CardHeader>
            <CardTitle className="text-red-600 flex items-center gap-2">
              <AlertTriangle className="h-5 w-5" />
              Connection Error
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <p className="text-gray-600">{error}</p>
            <button
              onClick={fetchData}
              className="w-full px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors flex items-center justify-center gap-2"
            >
              <RefreshCw className="h-4 w-4" />
              Retry Connection
            </button>
          </CardContent>
        </Card>
      </div>
    );
  }

  if (!data) return null;

  const { infrastructure, killVelocity, killBreakdown, volumeHistory, client } = data;

  // Calculate metrics
  const totalInboxes = infrastructure.total_inboxes;
  const liveInboxes = infrastructure.live_inboxes;
  const deadInboxes = infrastructure.dead_inboxes;
  const healthScore = infrastructure.avg_health_score;
  const survivalRate = totalInboxes > 0 ? (liveInboxes / totalInboxes) * 100 : 0;
  const healthDist = infrastructure.health_distribution;
  const lifecycleDist = infrastructure.lifecycle_distribution;

  // Check if data is stale (>15 minutes old)
  const minutesSinceSync = infrastructure.last_sync
    ? Math.floor((Date.now() - new Date(infrastructure.last_sync).getTime()) / 60000)
    : null;
  const isDataStale = minutesSinceSync !== null && minutesSinceSync > 15;

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
                <div className="text-sm text-gray-500 flex items-center gap-1">
                  <Clock className="h-4 w-4" />
                  Updated {formatRelativeTime(lastFetch.toISOString())}
                </div>
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
                title="Refresh data"
              >
                <RefreshCw className={cn("h-5 w-5", loading && "animate-spin")} />
              </button>
            </div>
          </div>

          {/* Data Staleness Warning */}
          {isDataStale && (
            <div className="mt-4 p-3 bg-amber-50 border border-amber-200 rounded-lg flex items-center gap-2 text-sm text-amber-800">
              <AlertTriangle className="h-4 w-4" />
              <span>
                Data is {minutesSinceSync} minutes old. Click refresh for latest metrics.
              </span>
            </div>
          )}
        </div>
      </div>

      <div className="max-w-7xl mx-auto px-6 py-8 space-y-8">
        {/* Key Metrics Row */}
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
          {/* Total Inboxes */}
          <Card className="bg-gradient-to-br from-blue-500 to-blue-600 text-white hover:shadow-lg hover:scale-[1.01] transition-all duration-200">
            <CardHeader className="pb-3">
              <div className="flex items-center justify-between">
                <CardTitle className="text-sm font-medium text-blue-100">
                  Total Inboxes
                </CardTitle>
                <Info className="h-4 w-4 text-blue-200" />
              </div>
            </CardHeader>
            <CardContent>
              <div className="flex items-center justify-between">
                <div>
                  <div className="text-4xl font-bold">{formatNumber(totalInboxes)}</div>
                  <div className="text-sm text-blue-100 mt-1 flex items-center gap-2">
                    <CheckCircle className="h-3 w-3" />
                    {formatNumber(liveInboxes)} live
                    <span className="mx-1">·</span>
                    <XCircle className="h-3 w-3" />
                    {formatNumber(deadInboxes)} retired
                  </div>
                  <div className="text-xs text-blue-200 mt-2 flex items-center gap-1">
                    {survivalRate >= 85 ? (
                      <><TrendingUp className="h-3 w-3" /> Above target (85%)</>
                    ) : (
                      <><AlertTriangle className="h-3 w-3" /> Below target (85%)</>
                    )}
                  </div>
                </div>
                <Server className="h-12 w-12 text-blue-200" />
              </div>
            </CardContent>
          </Card>

          {/* Health Score */}
          <Card className="bg-gradient-to-br from-green-500 to-green-600 text-white hover:shadow-lg hover:scale-[1.01] transition-all duration-200">
            <CardHeader className="pb-3">
              <div className="flex items-center justify-between">
                <CardTitle className="text-sm font-medium text-green-100">
                  Health Score
                </CardTitle>
                <Info className="h-4 w-4 text-green-200" />
              </div>
            </CardHeader>
            <CardContent>
              <div className="flex items-center justify-between">
                <div>
                  <div className="text-4xl font-bold">{Math.round(healthScore)}</div>
                  <div className="text-sm text-green-100 mt-1">
                    {healthScore >= 80 ? 'Excellent' : healthScore >= 60 ? 'Good' : healthScore >= 40 ? 'Fair' : 'Needs Attention'}
                  </div>
                  <div className="text-xs text-green-200 mt-2">
                    {healthScore >= 80 ? '✓ Optimal performance' : '⚠ Review required'}
                  </div>
                </div>
                <Activity className="h-12 w-12 text-green-200" />
              </div>
            </CardContent>
          </Card>

          {/* Survival Rate */}
          <Card className="bg-gradient-to-br from-purple-500 to-purple-600 text-white hover:shadow-lg hover:scale-[1.01] transition-all duration-200">
            <CardHeader className="pb-3">
              <div className="flex items-center justify-between">
                <CardTitle className="text-sm font-medium text-purple-100">
                  Survival Rate
                </CardTitle>
                <Info className="h-4 w-4 text-purple-200" />
              </div>
            </CardHeader>
            <CardContent>
              <div className="flex items-center justify-between">
                <div>
                  <div className="text-4xl font-bold">{formatPercent(survivalRate)}</div>
                  <div className="text-sm text-purple-100 mt-1">
                    {formatNumber(liveInboxes)} of {formatNumber(totalInboxes)} active
                  </div>
                  <div className="text-xs text-purple-200 mt-2">
                    {survivalRate >= 85 ? '✓ Healthy ratio' : '⚠ Capacity concern'}
                  </div>
                </div>
                <CheckCircle className="h-12 w-12 text-purple-200" />
              </div>
            </CardContent>
          </Card>

          {/* Domain Health */}
          <Card className={cn(
            "text-white hover:shadow-lg hover:scale-[1.01] transition-all duration-200",
            infrastructure.flagged_domains > 0
              ? "bg-gradient-to-br from-red-500 to-red-600"
              : "bg-gradient-to-br from-teal-500 to-teal-600"
          )}>
            <CardHeader className="pb-3">
              <div className="flex items-center justify-between">
                <CardTitle className={cn(
                  "text-sm font-medium",
                  infrastructure.flagged_domains > 0 ? "text-red-100" : "text-teal-100"
                )}>
                  Domain Status
                </CardTitle>
                <Info className={cn(
                  "h-4 w-4",
                  infrastructure.flagged_domains > 0 ? "text-red-200" : "text-teal-200"
                )} />
              </div>
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
                  <div className={cn(
                    "text-xs mt-2",
                    infrastructure.flagged_domains > 0 ? "text-red-200" : "text-teal-200"
                  )}>
                    {infrastructure.flagged_domains > 0 ? '⚠ Review blacklists' : '✓ All clear'}
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
              <CardDescription>
                Overall system performance
                <span className="block text-xs text-gray-500 mt-1">
                  🎯 Based on connection, bounce rates, and sending behavior
                </span>
              </CardDescription>
            </CardHeader>
            <CardContent>
              <HealthScoreGauge score={healthScore} label="Average Health Score" />
            </CardContent>
          </Card>

          {/* Health Distribution */}
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                Health Distribution
                <Info className="h-4 w-4 text-gray-400" />
              </CardTitle>
              <CardDescription className="space-y-2">
                <p>Inbox health breakdown by score range</p>
                <div className="text-xs text-gray-600 bg-gray-50 p-2 rounded border border-gray-200">
                  <div className="font-medium mb-1">Score Ranges:</div>
                  <div className="grid grid-cols-2 gap-1">
                    <span>🟢 Healthy: 80-100</span>
                    <span>🟡 Good: 60-80</span>
                    <span>🟠 Warning: 40-60</span>
                    <span>🔴 Critical: 0-40</span>
                  </div>
                </div>
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="space-y-3">
                {[
                  { name: 'Healthy', count: healthDist.healthy, color: 'green', range: '80-100', icon: CheckCircle },
                  { name: 'Good', count: healthDist.good, color: 'yellow', range: '60-80', icon: Activity },
                  { name: 'Warning', count: healthDist.warning, color: 'orange', range: '40-60', icon: AlertTriangle },
                  { name: 'Critical', count: healthDist.critical, color: 'red', range: '0-40', icon: XCircle },
                ].map(({ name, count, color, range, icon: Icon }) => (
                  <div key={name} className="cursor-help" title={`${count} inboxes with health score ${range}`}>
                    <div className="flex justify-between text-sm mb-1">
                      <span className={`font-medium text-${color}-700 flex items-center gap-1`}>
                        <Icon className="h-3 w-3" />
                        {name}
                      </span>
                      <span className="text-gray-600 font-semibold">{formatNumber(count)}</span>
                    </div>
                    <Progress
                      value={(count / healthDist.total) * 100}
                      className="h-2"
                    />
                  </div>
                ))}
              </div>

              {/* Actionable Insight */}
              {healthDist.critical > 0 && (
                <div className="mt-4 p-3 bg-red-50 border border-red-200 rounded-lg">
                  <div className="flex items-start gap-2">
                    <AlertTriangle className="h-4 w-4 text-red-600 mt-0.5 flex-shrink-0" />
                    <div className="text-sm">
                      <div className="font-medium text-red-900">Action Required</div>
                      <div className="text-red-700 mt-1">
                        {healthDist.critical} inbox{healthDist.critical > 1 ? 'es' : ''} in critical state need immediate attention
                      </div>
                    </div>
                  </div>
                </div>
              )}
            </CardContent>
          </Card>

          {/* Lifecycle Distribution */}
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                Lifecycle Status
                <Info className="h-4 w-4 text-gray-400" />
              </CardTitle>
              <CardDescription>
                Inbox deployment stages
                <span className="block text-xs text-gray-500 mt-1">
                  📦 Tracking inbox pipeline from warmup to production
                </span>
              </CardDescription>
            </CardHeader>
            <CardContent>
              <div className="space-y-4">
                {[
                  { name: 'Deployed', count: lifecycleDist.deployed, color: 'blue', desc: 'Active in campaigns' },
                  { name: 'Reserve', count: lifecycleDist.reserve, color: 'green', desc: 'Ready for deployment' },
                  { name: 'Incubating', count: lifecycleDist.incubating, color: 'yellow', desc: 'Warming up' },
                  { name: 'Warning', count: lifecycleDist.warning, color: 'orange', desc: 'Has bounce issues' },
                ].map(({ name, count, color, desc }) => (
                  <div key={name} className="flex items-center justify-between py-2 border-b last:border-0">
                    <div className="flex items-center gap-2">
                      <div className={`w-3 h-3 rounded-full bg-${color}-500`}></div>
                      <div>
                        <span className="text-sm font-medium">{name}</span>
                        <div className="text-xs text-gray-500">{desc}</div>
                      </div>
                    </div>
                    <Badge>{formatNumber(count)}</Badge>
                  </div>
                ))}
              </div>
            </CardContent>
          </Card>
        </div>

        {/* Kill Analytics - ALWAYS SHOW BOTH */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          {/* Kill Velocity */}
          <Card>
            <CardHeader>
              <div className="flex items-center justify-between">
                <div className="flex-1">
                  <CardTitle className="flex items-center gap-2">
                    Kill Velocity
                    <Info className="h-4 w-4 text-gray-400" />
                  </CardTitle>
                  <CardDescription className="mt-1">
                    Weekly inbox deaths from send quality issues
                    <span className="block text-xs text-gray-500 mt-1">
                      📊 System kills only • Excludes manual deactivations
                    </span>
                  </CardDescription>
                </div>
                <div className="flex items-center gap-2">
                  {killVelocity?.trend === 'up' && <TrendingUp className="h-5 w-5 text-red-500" />}
                  {killVelocity?.trend === 'down' && <TrendingDown className="h-5 w-5 text-green-500" />}
                  {killVelocity && (
                    <Badge variant={killVelocity.trend === 'up' ? 'destructive' : 'default'}>
                      {killVelocity.totalDeaths7d} (7d)
                    </Badge>
                  )}
                </div>
              </div>
            </CardHeader>
            <CardContent>
              {killVelocity && killVelocity.weeklyData.length > 0 ? (
                <>
                  <KillVelocityChart data={killVelocity} />

                  {/* Trend Analysis */}
                  <div className="mt-4 grid grid-cols-2 gap-3 text-sm">
                    <div className="p-2 bg-gray-50 rounded">
                      <div className="text-gray-600">7-day total</div>
                      <div className="text-lg font-semibold text-gray-900">
                        {killVelocity.totalDeaths7d}
                      </div>
                    </div>
                    <div className="p-2 bg-gray-50 rounded">
                      <div className="text-gray-600">30-day total</div>
                      <div className="text-lg font-semibold text-gray-900">
                        {killVelocity.totalDeaths30d}
                      </div>
                    </div>
                  </div>
                </>
              ) : (
                // Empty State
                <div className="h-64 flex items-center justify-center">
                  <div className="text-center">
                    <CheckCircle className="h-16 w-16 text-green-500 mx-auto mb-4" />
                    <h3 className="text-lg font-semibold text-gray-700 mb-2">
                      No Deaths Recorded
                    </h3>
                    <p className="text-gray-500 max-w-sm">
                      All inboxes are performing well! No automated kills triggered by send quality issues.
                    </p>
                    <div className="mt-4 text-xs text-gray-400">
                      This chart tracks system-initiated deaths only
                    </div>
                  </div>
                </div>
              )}
            </CardContent>
          </Card>

          {/* Kill Breakdown - ALWAYS SHOW */}
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                Kill Trigger Analysis
                <Info className="h-4 w-4 text-gray-400" />
              </CardTitle>
              <CardDescription>
                Root cause analysis of inbox deaths
                <span className="block text-xs text-gray-500 mt-1">
                  🔍 Last 30 days • Helps identify systematic issues
                </span>
              </CardDescription>
            </CardHeader>
            <CardContent>
              {killBreakdown && killBreakdown.total_kills > 0 ? (
                <>
                  <KillBreakdownPie data={killBreakdown} />

                  {/* Trigger Legend */}
                  <div className="mt-4 space-y-2 text-xs">
                    <div className="font-medium text-gray-700">Common Triggers:</div>
                    <div className="space-y-1 text-gray-600">
                      <div>🚨 Spam Complaint - User reported spam</div>
                      <div>🛡️ Hard Blocked - ESP blocked sender</div>
                      <div>📧 Bad Address - Non-existent email</div>
                      <div>⏱️ Fresh Bounce - New inbox bounced</div>
                    </div>
                  </div>
                </>
              ) : (
                // Empty State
                <div className="h-64 flex items-center justify-center">
                  <div className="text-center">
                    <Shield className="h-16 w-16 text-green-500 mx-auto mb-4" />
                    <h3 className="text-lg font-semibold text-gray-700 mb-2">
                      No Kills in Last 30 Days
                    </h3>
                    <p className="text-gray-500 max-w-sm">
                      No inboxes have been automatically killed for send quality issues.
                    </p>
                    <div className="mt-4 p-3 bg-green-50 border border-green-200 rounded-lg inline-block">
                      <div className="text-sm text-green-800">
                        ✅ Clean sending behavior maintained
                      </div>
                    </div>
                  </div>
                </div>
              )}
            </CardContent>
          </Card>
        </div>

        {/* Volume History */}
        {volumeHistory && volumeHistory.snapshots.length > 0 ? (
          <Card>
            <CardHeader>
              <div className="flex items-center justify-between">
                <div className="flex-1">
                  <CardTitle className="flex items-center gap-2">
                    Email Volume & Capacity
                    <Info className="h-4 w-4 text-gray-400" />
                  </CardTitle>
                  <CardDescription>
                    30-day sending history with capacity utilization
                    <div className="flex items-center gap-3 mt-2 text-xs text-gray-500">
                      <div className="flex items-center gap-1">
                        <Database className="h-3 w-3" />
                        Source: EmailBison campaign stats
                      </div>
                      <div className="flex items-center gap-1">
                        <Clock className="h-3 w-3" />
                        Updated: {formatRelativeTime(infrastructure.last_sync)}
                      </div>
                      <div className="flex items-center gap-1">
                        <Calendar className="h-3 w-3" />
                        Nov 25, 2025 - Present
                      </div>
                    </div>
                  </CardDescription>
                </div>
                <Badge variant="outline" className="text-xs">
                  Backfilled 2026-02-23
                </Badge>
              </div>
            </CardHeader>
            <CardContent>
              <VolumeHistoryChart data={volumeHistory} />

              {/* Data Quality Note */}
              <div className="mt-3 p-2 bg-amber-50 border border-amber-200 rounded text-xs text-amber-800 flex items-start gap-2">
                <Info className="h-3 w-3 mt-0.5 flex-shrink-0" />
                <span>
                  <strong>Note:</strong> Kill annotations show system kills only (excludes manual deactivations)
                </span>
              </div>
            </CardContent>
          </Card>
        ) : (
          // Empty State
          <Card>
            <CardHeader>
              <CardTitle>Email Volume & Capacity</CardTitle>
              <CardDescription>30-day sending history</CardDescription>
            </CardHeader>
            <CardContent>
              <div className="h-80 flex items-center justify-center">
                <div className="text-center">
                  <BarChart3 className="h-16 w-16 text-gray-300 mx-auto mb-4" />
                  <h3 className="text-lg font-semibold text-gray-700 mb-2">
                    No Volume Data Available
                  </h3>
                  <p className="text-gray-500 max-w-md">
                    Volume history will appear here once your campaigns start sending emails.
                    Data is collected daily from EmailBison.
                  </p>
                  <div className="mt-4 text-xs text-gray-400">
                    Initial backfill scheduled for first sync
                  </div>
                </div>
              </div>
            </CardContent>
          </Card>
        )}

        {/* Provider Breakdown */}
        <Card>
          <CardHeader>
            <CardTitle>Email Provider Distribution</CardTitle>
            <CardDescription>
              Inbox allocation by provider
              <span className="block text-xs text-gray-500 mt-1">
                📬 Gmail, Microsoft, and other email service providers
              </span>
            </CardDescription>
          </CardHeader>
          <CardContent>
            <div className="space-y-3">
              {infrastructure.providers.map((provider) => (
                <div key={provider.name} className="flex items-center justify-between py-3 border-b last:border-0">
                  <div className="flex-1">
                    <div className="flex items-center gap-3">
                      <Mail className="h-5 w-5 text-gray-400" />
                      <div>
                        <span className="font-medium text-gray-900 capitalize">{provider.name}</span>
                        <div className="text-xs text-gray-500">
                          {((provider.live_count / totalInboxes) * 100).toFixed(1)}% of infrastructure
                        </div>
                      </div>
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
        <div className="text-center text-sm text-gray-500 py-4 space-y-1">
          <p className="flex items-center justify-center gap-2">
            <Clock className="h-4 w-4" />
            Last synced: {infrastructure.last_sync ? formatRelativeTime(infrastructure.last_sync) : 'Unknown'}
          </p>
          <p className="flex items-center justify-center gap-2">
            <Database className="h-4 w-4" />
            Data source: {infrastructure.sync_source}
          </p>
        </div>
      </div>
    </div>
  );
}
