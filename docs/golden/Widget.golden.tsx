/**
 * GOLDEN REFERENCE — not built, not imported (lives outside src/, suffix
 * `.golden.tsx` so tsc/vite ignore it). It shows the BAR for a generated
 * `frontend/src/components/Widget.tsx`: match this level of polish, hierarchy,
 * and state-handling — then ADAPT the domain/layout to the real app. Do NOT
 * copy this content.
 *
 * Why it's good:
 *  - Theme TOKENS only (text-foreground / text-muted-foreground / text-accent /
 *    bg-card via WidgetContainer) — zero hardcoded hex, so it inherits the app's
 *    palette and stays legible in light AND dark.
 *  - WidgetContainer owns the surface (size, glass, radius, padding, overflow);
 *    WidgetButton/WidgetBadge keep actions + chips on-brand and 44px-tappable.
 *  - ONE focal element per size; the three sizes are genuinely different layouts
 *    branched on the `size` prop only — no responsive prefixes, no @media.
 *  - All three states are handled and HIGH-CONTRAST: skeleton while loading,
 *    a calm empty state, and a legible error with a themed Retry (not a
 *    muted-on-glass whisper, not a hardcoded-blue button).
 *
 * Domain here is a neutral fictional "reading queue" so it reads as reference.
 */
import { useEffect, useState } from 'react';
import { BookOpen } from 'lucide-react';
import { WidgetContainer, WidgetButton, WidgetBadge } from '@clarittyai/widget-toolkit';
import { getWidgetData, openNext, type WidgetData } from '@/lib/api';
import { runQuickAction, notifyWidgetStateChanged } from '@/lib/widget-actions';
import { cn } from '@/lib/utils';
import type { WidgetSize } from '@/lib/widget-sizes';

export default function Widget({ size = 'medium' }: { size?: WidgetSize }) {
  const [data, setData] = useState<WidgetData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchData = async () => {
    try {
      setData(await getWidgetData(size));
      setError(null);
    } catch {
      setError('Could not load your queue');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void fetchData();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [size]);

  // Loading — token-based skeleton, never a bare spinner.
  if (loading) {
    return (
      <WidgetContainer size={size} className="animate-pulse">
        <div className="mb-4 h-4 w-2/3 rounded bg-muted" />
        <div className="h-8 w-1/3 rounded bg-muted" />
      </WidgetContainer>
    );
  }

  // Error — HIGH CONTRAST (text-foreground, not muted) + a themed Retry.
  if (error || !data) {
    return (
      <WidgetContainer size={size} className="flex flex-col items-center justify-center gap-2 text-center">
        <p className="text-sm font-medium text-foreground">{error ?? 'No data yet'}</p>
        <WidgetButton variant="secondary" onClick={() => void fetchData()}>
          Retry
        </WidgetButton>
      </WidgetContainer>
    );
  }

  const unread = data.unread ?? 0;
  const next = data.next_title;

  // Small — one focal metric + (at most) one action.
  if (size === 'small') {
    return (
      <WidgetContainer size="small" className="flex flex-col justify-between">
        <div>
          <div className={cn('text-5xl font-bold leading-none', unread > 0 ? 'text-foreground' : 'text-muted-foreground')}>
            {unread}
          </div>
          <div className="mt-1 text-xs font-medium text-muted-foreground">to read</div>
        </div>
        {unread > 0 ? (
          <WidgetButton variant="primary" icon={<BookOpen className="h-4 w-4" />} className="w-full" onClick={() => void runQuickAction({ actionId: 'open-next', run: openNext }).then(notifyWidgetStateChanged)}>
            Open next
          </WidgetButton>
        ) : (
          <span className="text-sm font-medium text-muted-foreground">All caught up</span>
        )}
      </WidgetContainer>
    );
  }

  // Medium — focal metric + a short peek.
  if (size === 'medium') {
    return (
      <WidgetContainer size="medium" className="flex flex-row items-center gap-4">
        <div className="flex w-[34%] flex-shrink-0 flex-col justify-center">
          <div className={cn('text-4xl font-bold leading-none', unread > 0 ? 'text-foreground' : 'text-muted-foreground')}>{unread}</div>
          <div className="mt-1 text-xs font-medium text-muted-foreground">to read</div>
        </div>
        <div className="min-w-0 flex-1">
          {next ? (
            <>
              <p className="text-xs text-muted-foreground">up next</p>
              <p className="truncate text-sm font-medium text-foreground">{next}</p>
            </>
          ) : (
            <span className="text-sm text-muted-foreground">All caught up</span>
          )}
        </div>
      </WidgetContainer>
    );
  }

  // Large — header + ranked list + footer.
  const items = data.items ?? [];
  return (
    <WidgetContainer size="large" className="flex flex-col">
      <div className="mb-3 flex items-center justify-between">
        <div className="flex items-baseline gap-2">
          <span className="text-3xl font-bold leading-none text-foreground">{unread}</span>
          <span className="text-sm text-muted-foreground">to read</span>
        </div>
        {(data.added_today ?? 0) > 0 && <WidgetBadge variant="info">{data.added_today} new</WidgetBadge>}
      </div>
      <div className="flex flex-1 flex-col gap-3 overflow-hidden">
        {items.length > 0 ? (
          items.slice(0, 3).map((it) => (
            <div key={it.id} className="min-w-0">
              <p className="truncate text-sm font-medium text-foreground">{it.title}</p>
              <p className="truncate text-xs text-muted-foreground">{it.source}</p>
            </div>
          ))
        ) : (
          <div className="flex flex-1 items-center justify-center text-sm text-muted-foreground">All caught up</div>
        )}
      </div>
    </WidgetContainer>
  );
}
