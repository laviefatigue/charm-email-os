'use client';

import { AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Legend } from 'recharts';
import type { VolumeHistory } from '@/lib/types';

interface VolumeHistoryChartProps {
  data: VolumeHistory;
}

export function VolumeHistoryChart({ data }: VolumeHistoryChartProps) {
  const chartData = data.snapshots.map((snapshot) => ({
    date: new Date(snapshot.date).toLocaleDateString('en-US', { month: 'short', day: 'numeric' }),
    'Emails Sent': snapshot.emails_sent,
    'Capacity': snapshot.daily_capacity_available,
    'Live Inboxes': snapshot.live_inboxes,
  }));

  return (
    <div className="h-80">
      <ResponsiveContainer width="100%" height="100%">
        <AreaChart data={chartData} margin={{ top: 10, right: 20, left: 0, bottom: 0 }}>
          <defs>
            <linearGradient id="colorSent" x1="0" y1="0" x2="0" y2="1">
              <stop offset="5%" stopColor="#3b82f6" stopOpacity={0.8}/>
              <stop offset="95%" stopColor="#3b82f6" stopOpacity={0}/>
            </linearGradient>
            <linearGradient id="colorCapacity" x1="0" y1="0" x2="0" y2="1">
              <stop offset="5%" stopColor="#10b981" stopOpacity={0.8}/>
              <stop offset="95%" stopColor="#10b981" stopOpacity={0}/>
            </linearGradient>
          </defs>
          <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
          <XAxis
            dataKey="date"
            tick={{ fontSize: 12 }}
            stroke="#6b7280"
          />
          <YAxis
            tick={{ fontSize: 12 }}
            stroke="#6b7280"
          />
          <Tooltip
            contentStyle={{
              backgroundColor: 'white',
              border: '1px solid #e5e7eb',
              borderRadius: '8px',
            }}
          />
          <Legend />
          <Area
            type="monotone"
            dataKey="Emails Sent"
            stroke="#3b82f6"
            fillOpacity={1}
            fill="url(#colorSent)"
          />
          <Area
            type="monotone"
            dataKey="Capacity"
            stroke="#10b981"
            fillOpacity={1}
            fill="url(#colorCapacity)"
          />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}
