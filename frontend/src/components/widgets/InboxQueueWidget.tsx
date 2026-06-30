import { WidgetContainer, WidgetButton, WidgetBadge } from '@clarittyai/widget-toolkit';
import { cn } from '@/lib/utils';
import type { WidgetSize } from '@/lib/widget-sizes';
import { type ItemWidgetData, type WidgetItem, priorityBadge } from './types';

/**
 * InboxQueueWidget — a read-first queue/count (no in-place action). Use for apps
 * where the widget surfaces "what's waiting" and the user opens the app to act
 * (Ops, generic triage). Presentational: pass `data` + `onOpen` (deep-link).
 */
export function InboxQueueWidget({
  size, data, onOpen, unitLabel = 'open', className,
}: {
  size: WidgetSize;
  data: ItemWidgetData;
  onOpen?: () => void;
  unitLabel?: string;
  className?: string;
}) {
  const open = data.open_count ?? 0;
  const items = data.items ?? [];

  if (size === 'small') {
    return (
      <WidgetContainer size="small" className={cn('flex flex-col justify-between', className)}>
        <div>
          <div className={cn('text-5xl font-bold leading-none', open > 0 ? 'text-foreground' : 'text-muted-foreground')}>
            {open}
          </div>
          <div className="mt-1 text-xs font-medium text-muted-foreground">{unitLabel}</div>
        </div>
        {open > 0 && onOpen ? (
          <WidgetButton variant="primary" onClick={onOpen} className="w-full">Open</WidgetButton>
        ) : (
          <span className="text-sm font-medium text-muted-foreground">All clear ✓</span>
        )}
      </WidgetContainer>
    );
  }

  if (size === 'medium') {
    const shown = items.slice(0, 2);
    return (
      <WidgetContainer size="medium" className={cn('flex flex-row items-center gap-4', className)}>
        <div className="flex w-[34%] flex-shrink-0 flex-col justify-center">
          <div className={cn('text-4xl font-bold leading-none', open > 0 ? 'text-foreground' : 'text-muted-foreground')}>
            {open}
          </div>
          <div className="mt-1 text-xs font-medium text-muted-foreground">{unitLabel}</div>
        </div>
        <div className="flex min-w-0 flex-1 flex-col justify-center gap-2.5">
          {shown.length > 0 ? shown.map((it) => <Row key={it.id} item={it} />)
            : <span className="text-sm text-muted-foreground">All clear ✓</span>}
        </div>
      </WidgetContainer>
    );
  }

  const shown = items.slice(0, 4);
  const hidden = Math.max(0, open - shown.length);
  return (
    <WidgetContainer size="large" className={cn('flex flex-col', className)}>
      <div className="mb-3 flex items-baseline gap-2">
        <span className="text-3xl font-bold leading-none text-foreground">{open}</span>
        <span className="text-sm text-muted-foreground">{unitLabel}</span>
      </div>
      <div className="flex flex-1 flex-col gap-3 overflow-hidden">
        {shown.length > 0 ? shown.map((it) => <Row key={it.id} item={it} />)
          : <div className="flex flex-1 items-center justify-center text-sm text-muted-foreground">All caught up ✓</div>}
      </div>
      <div className="mt-3 flex items-center justify-between gap-2">
        <span className="truncate text-xs text-muted-foreground">
          {hidden > 0 ? `+${hidden} more · updated ${data.last_updated}` : `updated ${data.last_updated}`}
        </span>
        {shown.length > 0 && onOpen && <WidgetButton variant="secondary" onClick={onOpen}>Open</WidgetButton>}
      </div>
    </WidgetContainer>
  );
}

function Row({ item }: { item: WidgetItem }) {
  const b = priorityBadge(item.priority);
  return (
    <div className="flex items-center gap-2.5">
      <span className="block min-w-0 flex-1 truncate text-sm font-medium text-foreground">{item.title}</span>
      <WidgetBadge variant={b.variant}>{b.label}</WidgetBadge>
    </div>
  );
}
