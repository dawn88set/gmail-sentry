import { useEffect, useState } from 'react';
import { ArrowUpRight, ShieldCheck, Shield } from 'lucide-react';
import { WidgetContainer, WidgetButton } from '@clarittyai/widget-toolkit';
import {
  getWidgetData,
  clearCategoryAll,
  toApiError,
  type WidgetData,
  type WidgetAlert,
  type Tier,
} from '@/lib/api';
import { runQuickAction, triggerDeepLink, notifyWidgetStateChanged } from '@/lib/widget-actions';
import { parseSender } from '@/components/Avatar';
import { useToast } from '@/components/Toast';
import { cn } from '@/lib/utils';
import type { WidgetSize } from '@/lib/widget-sizes';

export type { WidgetSize };

interface WidgetProps {
  size?: WidgetSize;
  className?: string;
}

const TIER_LABEL: Record<Tier, string> = { urgent: 'Urgent', needs_reply: 'Reply', fyi: 'FYI' };

/** Rich, state-aware gradient backdrop + soft glows + a shield watermark. */
function Backdrop({ calm }: { calm: boolean }) {
  return (
    <>
      <div
        className={cn(
          'absolute inset-0 bg-gradient-to-br',
          calm ? 'from-gmail-green-500 to-gmail-green-700' : 'from-accent to-accent-600',
        )}
      />
      {/* soft light blooms for depth */}
      <div className="absolute -right-8 -top-10 h-28 w-28 rounded-full bg-white/25 blur-2xl" />
      <div className="absolute -bottom-12 -left-8 h-32 w-32 rounded-full bg-black/10 blur-2xl" />
      {/* subtle brand watermark */}
      <Shield className="absolute -bottom-5 -right-4 h-28 w-28 text-white/10" strokeWidth={1.5} />
    </>
  );
}

/** White "watching" pulse for the colored surface. */
function LiveDot() {
  return (
    <span className="relative flex h-2 w-2">
      <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-white opacity-70" />
      <span className="relative inline-flex h-2 w-2 rounded-full bg-white" />
    </span>
  );
}

export default function Widget({ size = 'medium', className }: WidgetProps) {
  const [data, setData] = useState<WidgetData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const { show } = useToast();

  useEffect(() => {
    void fetchData();
    const interval = setInterval(() => void fetchData(), 30000);
    const onRefresh = () => void fetchData();
    window.addEventListener('claritty:widget-refresh', onRefresh);
    return () => {
      clearInterval(interval);
      window.removeEventListener('claritty:widget-refresh', onRefresh);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [size]);

  const fetchData = async () => {
    try {
      setData(await getWidgetData(size));
      setError(null);
    } catch (err) {
      setError('Failed to load inbox');
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  const openApp = () => triggerDeepLink({ path: '/' });
  // A ready-to-approve reply deep-links straight to its Approve & Send screen.
  const openAlert = (a: WidgetAlert) =>
    triggerDeepLink({ path: a.reply_ready ? `/attention?focus=${a.id}` : '/' });

  const clearJunk = async (category: 'promotions' | 'social' | 'spam') => {
    try {
      const res = await runQuickAction({ actionId: `clear-${category}`, run: () => clearCategoryAll(category) });
      show({ tone: 'success', text: `Cleared ${res.cleared.toLocaleString()} ${category} email${res.cleared === 1 ? '' : 's'} to Trash.` });
      notifyWidgetStateChanged();
    } catch (err) {
      const e = toApiError(err);
      show({
        tone: 'error',
        text:
          e.status === 409 || e.code === 'not_connected'
            ? 'Connect Gmail on the Integrations tab, then try again.'
            : `Couldn’t clear ${category}: ${e.message}`,
      });
    } finally {
      void fetchData();
    }
  };

  if (loading) {
    return (
      <WidgetContainer size={size} className={cn('animate-pulse bg-accent/20', className)}>
        <div className="mb-4 h-4 w-3/4 rounded bg-white/25" />
        <div className="h-8 w-1/2 rounded bg-white/25" />
      </WidgetContainer>
    );
  }

  if (error || !data) {
    return (
      <WidgetContainer
        size={size}
        className={cn('flex flex-col items-center justify-center gap-2 text-center', className)}
      >
        <p className="text-sm font-semibold text-foreground">{error ?? 'No data yet'}</p>
        <WidgetButton variant="secondary" onClick={() => void fetchData()}>
          Retry
        </WidgetButton>
      </WidgetContainer>
    );
  }

  const attention = (data.urgent_count ?? 0) + (data.needs_reply_count ?? 0);
  const allClear = data.all_clear ?? attention === 0;

  // ---- Small ---------------------------------------------------------------
  if (size === 'small') {
    return (
      <WidgetContainer size="small" className={cn('relative text-white', className)}>
        <Backdrop calm={allClear} />
        <div className="relative z-10 flex h-full flex-col justify-between">
          <div className="flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-wider text-white/80">
            <LiveDot /> Watching
          </div>
          <div>
            <div className="text-6xl font-bold leading-none tracking-tighter">{attention}</div>
            <div className="mt-1 text-xs font-medium text-white/80">
              need{attention === 1 ? 's' : ''} attention
            </div>
          </div>
          {allClear ? (
            <span className="flex items-center gap-1 text-sm font-semibold text-white">
              <ShieldCheck className="h-4 w-4" /> All clear
            </span>
          ) : (
            <button
              onClick={openApp}
              className="inline-flex w-full items-center justify-center gap-1.5 rounded-full bg-white/25 py-2 text-sm font-semibold text-white backdrop-blur transition-colors hover:bg-white/35 active:scale-95"
            >
              Review <ArrowUpRight className="h-4 w-4" />
            </button>
          )}
        </div>
      </WidgetContainer>
    );
  }

  // ---- Medium --------------------------------------------------------------
  if (size === 'medium') {
    const top = data.top_alerts?.[0];
    return (
      <WidgetContainer size="medium" className={cn('relative text-white', className)}>
        <Backdrop calm={allClear} />
        <div className="relative z-10 flex h-full flex-row items-center gap-4">
          <div className="flex w-[38%] flex-shrink-0 flex-col justify-center">
            <div className="mb-1 flex items-center gap-1.5 text-[10px] font-semibold uppercase tracking-wider text-white/80">
              <LiveDot /> Live
            </div>
            <div className="text-5xl font-bold leading-none tracking-tighter">{attention}</div>
            <div className="mt-1 text-xs font-medium text-white/80">need attention</div>
            <div className="mt-0.5 text-[11px] text-white/60">scanned {data.last_scan}</div>
          </div>
          <button onClick={() => (top ? openAlert(top) : openApp())} className="flex min-w-0 flex-1 flex-col justify-center gap-1.5 text-left" aria-label="Open Gmail Sentry">
            {top ? (
              <AlertPeek alert={top} />
            ) : (
              <span className="flex items-center gap-1.5 text-sm font-semibold text-white">
                <ShieldCheck className="h-4 w-4" /> Inbox is calm
              </span>
            )}
          </button>
        </div>
      </WidgetContainer>
    );
  }

  // ---- Large ---------------------------------------------------------------
  // Three rows, not two: at 360×360 two rows leave a dead band above the junk
  // bar. The "does not scroll (content fits)" constraint test is the backstop
  // if a third ever stops fitting.
  const shown = (data.top_alerts ?? []).slice(0, 3);
  const cleanup = data.cleanup ?? { promo: 0, social: 0, spam: 0 };
  return (
    <WidgetContainer size="large" className={cn('relative text-white', className)}>
      <Backdrop calm={allClear} />
      <div className="relative z-10 flex h-full flex-col">
        <div className="mb-3 flex items-center justify-between">
          <div className="flex items-baseline gap-2">
            <span className="text-4xl font-bold leading-none tracking-tighter">{attention}</span>
            <span className="text-sm text-white/80">need attention</span>
          </div>
          <span className="inline-flex items-center gap-1.5 rounded-full bg-white/20 px-2.5 py-1 text-[11px] font-semibold text-white backdrop-blur">
            <LiveDot /> Watching
          </span>
        </div>

        <div className="flex flex-1 flex-col gap-2 overflow-hidden">
          {shown.length > 0 ? (
            shown.map((a) => <AlertRow key={a.id} alert={a} onClick={() => openAlert(a)} />)
          ) : (
            <div className="flex flex-1 items-center justify-center gap-1.5 text-sm font-semibold text-white">
              <ShieldCheck className="h-4 w-4" /> Inbox is calm
            </div>
          )}
        </div>

        <div className="mt-3 flex items-center justify-between gap-2">
          <JunkButton label="Promo" count={cleanup.promo} onClick={() => void clearJunk('promotions')} />
          <JunkButton label="Social" count={cleanup.social} onClick={() => void clearJunk('social')} />
          <JunkButton label="Spam" count={cleanup.spam} onClick={() => void clearJunk('spam')} />
          <button
            onClick={openApp}
            aria-label="Open Gmail Sentry"
            className="flex h-full flex-shrink-0 items-center rounded-2xl bg-white px-3 py-2 text-accent shadow-sm transition-transform active:scale-95"
          >
            <ArrowUpRight className="h-4 w-4" />
          </button>
        </div>
      </div>
    </WidgetContainer>
  );
}

function AlertPeek({ alert }: { alert: WidgetAlert }) {
  return (
    <>
      <span className="inline-flex w-fit items-center gap-1.5">
        <span className="inline-flex items-center gap-1 rounded-full bg-white/20 px-2 py-0.5 text-[11px] font-semibold text-white backdrop-blur">
          {TIER_LABEL[alert.tier] ?? 'FYI'}
        </span>
        {alert.reply_ready && (
          <span className="inline-flex items-center gap-1 rounded-full bg-white px-2 py-0.5 text-[11px] font-semibold text-accent">
            Reply ready
          </span>
        )}
      </span>
      <span className="block truncate text-sm font-semibold text-white">{alert.subject}</span>
      <span className="block truncate text-xs text-white/70">{parseSender(alert.sender).name}</span>
    </>
  );
}

function AlertRow({ alert, onClick }: { alert: WidgetAlert; onClick: () => void }) {
  return (
    <button
      onClick={onClick}
      className="flex w-full items-center gap-2 rounded-xl bg-white/10 px-2.5 py-2 text-left backdrop-blur transition-transform active:scale-[0.98]"
    >
      <span className="flex-shrink-0 rounded-full bg-white/25 px-1.5 py-0.5 text-[10px] font-semibold text-white">
        {TIER_LABEL[alert.tier] ?? 'FYI'}
      </span>
      <div className="min-w-0 flex-1">
        <span className="block truncate text-sm font-semibold text-white">{alert.subject}</span>
        <span className="block truncate text-xs text-white/70">{parseSender(alert.sender).name}</span>
      </div>
      {alert.reply_ready && (
        <span className="flex-shrink-0 rounded-full bg-white px-2 py-0.5 text-[10px] font-semibold text-accent">
          Reply ready
        </span>
      )}
    </button>
  );
}

function JunkButton({ label, count, onClick }: { label: string; count: number; onClick: () => void }) {
  return (
    <button
      onClick={onClick}
      disabled={count === 0}
      aria-label={`Clear ${count} ${label} emails`}
      className={cn(
        'flex min-w-0 flex-1 flex-col items-center rounded-2xl bg-white/15 px-2 py-2 text-white backdrop-blur transition-transform active:scale-95',
        count === 0 && 'opacity-50',
      )}
    >
      <span className="text-base font-bold leading-none">{count}</span>
      <span className="mt-0.5 truncate text-[11px] font-medium text-white/80">{label}</span>
    </button>
  );
}
