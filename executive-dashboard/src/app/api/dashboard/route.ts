import { NextResponse } from 'next/server';
import { config } from '@/lib/config';

// API Proxy - calls charm-api with hardcoded CLIENT_ID for Charm brand
// Aggregates all dashboard data in a single endpoint

export async function GET() {
  const { clientId, apiUrl } = config;

  try {
    // Fetch all data in parallel for optimal performance
    const [
      infraResponse,
      killVelocityResponse,
      killBreakdownResponse,
      volumeResponse,
      clientResponse
    ] = await Promise.all([
      fetch(`${apiUrl}/api/health/infrastructure/${clientId}`, {
        headers: { 'Content-Type': 'application/json' },
        cache: 'no-store',
      }),
      fetch(`${apiUrl}/api/health/kill-velocity/${clientId}`, {
        headers: { 'Content-Type': 'application/json' },
        cache: 'no-store',
      }),
      fetch(`${apiUrl}/api/health/kill-breakdown/${clientId}`, {
        headers: { 'Content-Type': 'application/json' },
        cache: 'no-store',
      }),
      fetch(`${apiUrl}/api/health/daily-volume/${clientId}?days=30`, {
        headers: { 'Content-Type': 'application/json' },
        cache: 'no-store',
      }),
      fetch(`${apiUrl}/api/clients/${clientId}`, {
        headers: { 'Content-Type': 'application/json' },
        cache: 'no-store',
      }),
    ]);

    // Infrastructure health is required
    if (!infraResponse.ok) {
      console.error('Infrastructure health API error:', infraResponse.status);
      return NextResponse.json(
        { error: 'Failed to fetch infrastructure health' },
        { status: infraResponse.status }
      );
    }

    const infrastructure = await infraResponse.json();

    // Other endpoints are optional - transform to match frontend types
    let killVelocity = null;
    if (killVelocityResponse.ok) {
      const raw = await killVelocityResponse.json();
      // Transform API response to match frontend types
      killVelocity = {
        weeklyData: raw.weekly || [],
        totalDeaths7d: raw.total_deaths_7d || 0,
        totalDeaths30d: raw.total_deaths_30d || 0,
        trend: raw.trend || 'stable',
      };
    }

    let killBreakdown = null;
    if (killBreakdownResponse.ok) {
      const raw = await killBreakdownResponse.json();
      // Transform API response to match frontend types
      killBreakdown = {
        total_kills: raw.total_killed || 0,
        by_trigger: (raw.raw || []).map((item: { trigger: string; count: number }) => ({
          trigger: item.trigger,
          count: item.count,
          percentage: raw.total_killed > 0 ? (item.count / raw.total_killed) * 100 : 0,
        })),
      };
    }

    let volumeHistory = null;
    if (volumeResponse.ok) {
      volumeHistory = await volumeResponse.json();
    }

    let client = null;
    if (clientResponse.ok) {
      client = await clientResponse.json();
    }

    // Combine and return
    return NextResponse.json({
      infrastructure,
      killVelocity,
      killBreakdown,
      volumeHistory,
      client,
      clientId,
      fetchedAt: new Date().toISOString(),
    });
  } catch (error) {
    console.error('API proxy error:', error);
    return NextResponse.json(
      { error: 'Failed to connect to backend API' },
      { status: 500 }
    );
  }
}
