import { Send } from 'lucide-react';
import { WidgetContainer, WidgetButton, WidgetBadge } from '@clarittyai/widget-toolkit';
import { cn } from '@/lib/utils';
import type { WidgetSize } from '@/lib/widget-sizes';
import { type ItemWidgetData, type WidgetItem, priorityBadge } from './types';

/**
 * ApprovalCardWidget — the human-in-the-loop hero widget reused by every
 * "draft → approve → send" app (Sales, Support, HR, IT). Presentational: the
 * app's Widget.tsx fetches `data` and passes `onApprove` (calls /api/items/{id}/
 * approve) + `onReview` (deep-link to the queue). On a 409 the app sets `note`
 * to a "Connect <service>" prompt — never a fake send.
 *
 * Window-size invariant: appearance is driven only by `size`.
 */
export function ApprovalCardWidget({
  size, data, onApprove, onReview, note, className,
}: {
  size: WidgetSize;
  data: ItemWidgetData;
  onApprove?: (id: string) => void;
  onReview?: () => void;
  note?: string | null;
  className?: string;
}) {
  const pending = data.pending_count ?? 0;
  const all = data.items ?? [];
  const items: WidgetItem[] =
    all.filter((i) => i.status === 'pending_approval').length > 0
      ? all.filter((i) => i.status === 'pending_approval')
      : all;

  if (size === 'small') {
    return (
      <WidgetContainer size="small" className={cn('flex flex-col justify-between', className)}>
        <div>
          <div className={cn('text-5xl font-bold leading-none', pending > 0 ? 'text-foreground' : 'text-muted-foreground')}>
            {pending}
          </div>
          <div className="mt-1 text-xs font-medium text-muted-foreground">to approve</div>
        </div>
        {pending > 0 && onReview ? (
          <WidgetButton variant="primary" onClick={onReview} className="w-full">Review</WidgetButton>
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
          <div className={cn('text-4xl font-bold leading-none', pending > 0 ? 'text-foreground' : 'text-muted-foreground')}>
            {pending}
          </div>
          <div className="mt-1 text-xs font-medium text-muted-foreground">to approve</div>
        </div>
        <div className="flex min-w-0 flex-1 flex-col justify-center gap-2.5">
          {shown.length > 0 ? shown.map((it) => <ItemRow key={it.id} item={it} />)
            : <span className="text-sm text-muted-foreground">All clear ✓</span>}
        </div>
      </WidgetContainer>
    );
  }

  const shown = items.slice(0, 3);
  const hidden = Math.max(0, pending - shown.length);
  return (
    <WidgetContainer size="large" className={cn('flex flex-col', className)}>
      <div className="mb-3 flex items-center justify-between">
        <div className="flex items-baseline gap-2">
          <span className="text-3xl font-bold leading-none text-foreground">{pending}</span>
          <span className="text-sm text-muted-foreground">to approve</span>
        </div>
        {(data.published_today ?? 0) > 0 && (
          <WidgetBadge variant="success">{data.published_today} sent</WidgetBadge>
        )}
      </div>
      <div className="flex flex-1 flex-col gap-3 overflow-hidden">
        {shown.length > 0 ? shown.map((it, i) => (
          <ItemRow key={it.id} item={it} detail={i === 0} onApprove={onApprove} />
        )) : (
          <div className="flex flex-1 items-center justify-center text-sm text-muted-foreground">All caught up ✓</div>
        )}
      </div>
      <div className="mt-3 flex items-center justify-between gap-2">
        <span className="truncate text-xs text-muted-foreground">
          {note ? note : hidden > 0 ? `+${hidden} more · updated ${data.last_updated}` : `updated ${data.last_updated}`}
        </span>
        {shown.length > 0 && onReview && (
          <WidgetButton variant="secondary" onClick={onReview}>Review all</WidgetButton>
        )}
      </div>
    </WidgetContainer>
  );
}

function ItemRow({
  item, detail = false, onApprove,
}: {
  item: WidgetItem;
  detail?: boolean;
  onApprove?: (id: string) => void;
}) {
  const b = priorityBadge(item.priority);
  return (
    <div className="flex items-start gap-2.5">
      <div className="min-w-0 flex-1">
        <span className="block truncate text-sm font-medium text-foreground">{item.title}</span>
        {detail && item.body && (
          <span className="block truncate text-xs text-muted-foreground">{item.body}</span>
        )}
      </div>
      <WidgetBadge variant={b.variant}>{b.label}</WidgetBadge>
      {onApprove && (
        <WidgetButton variant="primary" onClick={() => onApprove(item.id)} icon={<Send className="h-3.5 w-3.5" />}>
          Approve
        </WidgetButton>
      )}
    </div>
  );
}
