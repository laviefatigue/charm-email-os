'use client';

import { cn } from '@/lib/utils';

interface HealthScoreRingProps {
  score: number;
  size?: 'sm' | 'md' | 'lg';
  showLabel?: boolean;
  className?: string;
}

export function HealthScoreRing({
  score,
  size = 'md',
  showLabel = true,
  className,
}: HealthScoreRingProps) {
  const sizeConfig = {
    sm: { dimension: 48, strokeWidth: 4, fontSize: 'text-xs' },
    md: { dimension: 64, strokeWidth: 5, fontSize: 'text-sm' },
    lg: { dimension: 80, strokeWidth: 6, fontSize: 'text-base' },
  };

  const config = sizeConfig[size];
  const radius = (config.dimension - config.strokeWidth) / 2;
  const circumference = 2 * Math.PI * radius;
  const offset = circumference - (score / 100) * circumference;

  // Color based on score
  const getColor = (score: number) => {
    if (score >= 80) return { stroke: '#22c55e', text: 'text-green-600' }; // green
    if (score >= 60) return { stroke: '#eab308', text: 'text-yellow-600' }; // yellow
    if (score >= 40) return { stroke: '#f97316', text: 'text-orange-600' }; // orange
    return { stroke: '#ef4444', text: 'text-red-600' }; // red
  };

  const color = getColor(score);

  return (
    <div className={cn('relative inline-flex items-center justify-center', className)}>
      <svg
        width={config.dimension}
        height={config.dimension}
        className="-rotate-90"
        aria-hidden="true"
      >
        {/* Background circle */}
        <circle
          cx={config.dimension / 2}
          cy={config.dimension / 2}
          r={radius}
          fill="none"
          stroke="#e5e7eb"
          strokeWidth={config.strokeWidth}
        />
        {/* Progress circle */}
        <circle
          cx={config.dimension / 2}
          cy={config.dimension / 2}
          r={radius}
          fill="none"
          stroke={color.stroke}
          strokeWidth={config.strokeWidth}
          strokeLinecap="round"
          strokeDasharray={circumference}
          strokeDashoffset={offset}
          className="transition-all duration-500 ease-out"
        />
      </svg>
      {showLabel && (
        <div className="absolute inset-0 flex items-center justify-center">
          <span className={cn('font-bold', config.fontSize, color.text)}>{score}</span>
        </div>
      )}
    </div>
  );
}
