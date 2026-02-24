'use client';

import { getHealthColor, getHealthStatus, formatNumber } from '@/lib/utils';

interface HealthScoreGaugeProps {
  score: number;
  label?: string;
}

export function HealthScoreGauge({ score, label = 'Overall Health' }: HealthScoreGaugeProps) {
  const radius = 80;
  const strokeWidth = 16;
  const normalizedRadius = radius - strokeWidth / 2;
  const circumference = normalizedRadius * 2 * Math.PI;
  const strokeDashoffset = circumference - (score / 100) * circumference;

  const status = getHealthStatus(score);
  const color = getHealthColor(score);

  return (
    <div className="flex flex-col items-center justify-center py-4">
      <div className="relative">
        <svg
          height={radius * 2}
          width={radius * 2}
          className="transform -rotate-90"
        >
          {/* Background circle */}
          <circle
            stroke="#e5e7eb"
            fill="transparent"
            strokeWidth={strokeWidth}
            r={normalizedRadius}
            cx={radius}
            cy={radius}
          />
          {/* Progress circle */}
          <circle
            stroke={score >= 80 ? '#10b981' : score >= 60 ? '#f59e0b' : score >= 40 ? '#f97316' : '#ef4444'}
            fill="transparent"
            strokeWidth={strokeWidth}
            strokeDasharray={circumference + ' ' + circumference}
            style={{ strokeDashoffset, transition: 'stroke-dashoffset 0.5s ease' }}
            strokeLinecap="round"
            r={normalizedRadius}
            cx={radius}
            cy={radius}
          />
        </svg>
        <div className="absolute inset-0 flex flex-col items-center justify-center">
          <span className={`text-4xl font-bold ${color}`}>{Math.round(score)}</span>
          <span className="text-sm text-gray-500 mt-1">{status}</span>
        </div>
      </div>
      <p className="text-sm text-gray-600 mt-4 font-medium">{label}</p>
    </div>
  );
}
