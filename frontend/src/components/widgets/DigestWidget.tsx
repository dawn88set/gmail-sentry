import { WidgetContainer, WidgetButton } from '@clarittyai/widget-toolkit';
import { cn } from '@/lib/utils';
import type { WidgetSize } from '@/lib/widget-sizes';
import { type DigestWidgetData } from './types';

/**
 * DigestWidget — a short summarized list with an optional headline. Use for
 * Marketing/Ops/Legal/Exec read-only digests (today's highlights, campaign
 * recap, renewals due). Presentational: pass a DigestWidgetData + optional
 * `onOpen` deep-link.
 */
export function DigestWidget({
  size, data, onOpen, className,
}: {
  size: WidgetSize;
  data: DigestWidgetData;
  onOpen?: () => void;
  className?: string;
}) {
  const entries = data.entries ?? [];

  if (size === 'small') {
    return (
      <WidgetContainer size="small" className={cn('flex flex-col justify-between', className)}>
        <div className="min-w-0">
          <div className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
            {data.title ?? 'Digest'}
          </div>
          <p className="mt-1 line-clamp-4 text-sm font-medium text-foreground">
            {data.headline ?? (entries[0]?.title ?? 'Nothing new')}
          </p>
        </div>
        {onOpen && <WidgetButton variant="secondary" onClick={onOpen} className="w-full">Open</WidgetButton>}
      </WidgetContainer>
    );
  }

  const limit = size === 'medium' ? 2 : 5;
  const shown = entries.slice(0, limit);
  const hidden = Math.max(0, entries.length - shown.length);
  return (
    <WidgetContainer size={size} className={cn('flex flex-col', className)}>
      {data.headline && (
        <p className="mb-2 line-clamp-2 text-sm font-semibold text-foreground">{data.headline}</p>
      )}
      <div className="flex flex-1 flex-col gap-2.5 overflow-hidden">
        {shown.length > 0 ? shown.map((e) => (
          <div key={e.id} className="min-w-0">
            <span className="block truncate text-sm font-medium text-foreground">{e.title}</span>
            {e.subtitle && <span className="block truncate text-xs text-muted-foreground">{e.subtitle}</span>}
          </div>
        )) : (
          <div className="flex flex-1 items-center justify-center text-sm text-muted-foreground">Nothing new</div>
        )}
      </div>
      {(hidden > 0 || data.last_updated) && (
        <div className="mt-3 truncate text-xs text-muted-foreground">
          {hidden > 0 ? `+${hidden} more · ` : ''}{data.last_updated ? `updated ${data.last_updated}` : ''}
        </div>
      )}
    </WidgetContainer>
  );
}
