'use client';

import { PieChart, Pie, Cell, ResponsiveContainer, Legend, Tooltip } from 'recharts';
import type { KillBreakdown } from '@/lib/types';

interface KillBreakdownPieProps {
  data: KillBreakdown;
}

const COLORS = ['#ef4444', '#f97316', '#f59e0b', '#eab308', '#84cc16'];

export function KillBreakdownPie({ data }: KillBreakdownPieProps) {
  const chartData = data.by_trigger.map((item) => ({
    name: item.trigger,
    value: item.count,
    percentage: item.percentage,
  }));

  return (
    <div className="h-64">
      <ResponsiveContainer width="100%" height="100%">
        <PieChart>
          <Pie
            data={chartData}
            cx="50%"
            cy="50%"
            labelLine={false}
            label={({ name, percentage }) => `${name}: ${percentage.toFixed(1)}%`}
            outerRadius={80}
            fill="#8884d8"
            dataKey="value"
          >
            {chartData.map((entry, index) => (
              <Cell key={`cell-${index}`} fill={COLORS[index % COLORS.length]} />
            ))}
          </Pie>
          <Tooltip
            contentStyle={{
              backgroundColor: 'white',
              border: '1px solid #e5e7eb',
              borderRadius: '8px',
            }}
          />
          <Legend />
        </PieChart>
      </ResponsiveContainer>
    </div>
  );
}
