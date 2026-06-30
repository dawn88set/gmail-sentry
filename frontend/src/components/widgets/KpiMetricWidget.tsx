import { WidgetContainer, WidgetBadge } from '@clarittyai/widget-toolkit';
import { cn } from '@/lib/utils';
import type { WidgetSize } from '@/lib/widget-sizes';
import { type KpiWidgetData, type KpiStat } from './types';

/**
 * KpiMetricWidget — a focal metric + optional secondary stats. Use for Finance/
 * Exec digests (runway, AR/AP, sent-today, revenue). Presentational: pass a
 * KpiWidgetData. Read-only — the safest widget for live demos.
 */
export function KpiMetricWidget({
  size, data, className,
}: {
  size: WidgetSize;
  data: KpiWidgetData;
  className?: string;
}) {
  const { primary, stats = [] } = data;

  if (size === 'small') {
    return (
      <WidgetContainer size="small" className={cn('flex flex-col justify-between', className)}>
        <div>
          <div className="text-4xl font-bold leading-none text-foreground">{primary.value}</div>
          <div className="mt-1 text-xs font-medium text-muted-foreground">{primary.label}</div>
        </div>
        {primary.delta && <DeltaBadge stat={primary} />}
      </WidgetContainer>
    );
  }

  if (size === 'medium') {
    return (
      <WidgetContainer size="medium" className={cn('flex flex-row items-center gap-4', className)}>
        <div className="flex w-[40%] flex-shrink-0 flex-col justify-center">
          <div className="text-4xl font-bold leading-none text-foreground">{primary.value}</div>
          <div className="mt-1 text-xs font-medium text-muted-foreground">{primary.label}</div>
          {primary.delta && <div className="mt-1"><DeltaBadge stat={primary} /></div>}
        </div>
        <div className="flex min-w-0 flex-1 flex-col justify-center gap-2">
          {stats.slice(0, 2).map((s) => <StatRow key={s.label} stat={s} />)}
        </div>
      </WidgetContainer>
    );
  }

  return (
    <WidgetContainer size="large" className={cn('flex flex-col', className)}>
      <div className="mb-3">
        <div className="text-5xl font-bold leading-none text-foreground">{primary.value}</div>
        <div className="mt-1.5 flex items-center gap-2">
          <span className="text-sm text-muted-foreground">{primary.label}</span>
          {primary.delta && <DeltaBadge stat={primary} />}
        </div>
      </div>
      <div className="flex flex-1 flex-col gap-2.5 overflow-hidden">
        {stats.slice(0, 4).map((s) => <StatRow key={s.label} stat={s} />)}
      </div>
      {data.last_updated && (
        <div className="mt-3 truncate text-xs text-muted-foreground">updated {data.last_updated}</div>
      )}
    </WidgetContainer>
  );
}

function DeltaBadge({ stat }: { stat: KpiStat }) {
  const variant = stat.deltaTone === 'success' ? 'success' : stat.deltaTone === 'error' ? 'error' : 'neutral';
  return <WidgetBadge variant={variant}>{stat.delta}</WidgetBadge>;
}

function StatRow({ stat }: { stat: KpiStat }) {
  return (
    <div className="flex items-center justify-between gap-2">
      <span className="min-w-0 flex-1 truncate text-sm text-muted-foreground">{stat.label}</span>
      <span className="text-sm font-semibold text-foreground">{stat.value}</span>
      {stat.delta && <DeltaBadge stat={stat} />}
    </div>
  );
}
