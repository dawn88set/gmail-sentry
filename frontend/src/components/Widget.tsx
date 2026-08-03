import { useEffect, useState } from 'react';
import { ArrowUpRight, ShieldCheck } from 'lucide-react';
import { WidgetContainer, WidgetButton } from '@clarittyai/widget-toolkit';
import {
  getWidgetData,
  clearCategoryAll,
  toApiError,
  type WidgetData,
  type WidgetAlert,
} from '@/lib/api';
import { runQuickAction, triggerDeepLink, notifyWidgetStateChanged } from '@/lib/widget-actions';
import { Avatar, parseSender } from '@/components/Avatar';
import { useToast } from '@/components/Toast';
import { cn } from '@/lib/utils';
import type { WidgetSize } from '@/lib/widget-sizes';

export type { WidgetSize };

interface WidgetProps {
  size?: WidgetSize;
  className?: string;
}

/**
 * The widget used to be a saturated blue card with white text, which made blue
 * the SURFACE — so the accent stopped meaning "this is the action", and the
 * widget read as a different product from the app beside it.
 *
 * Now it sits on the same neutral card the app uses, and the accent is spent
 * only on the one thing worth tapping. Type weight and spacing carry the
 * hierarchy instead of colour, which is also what stops the identity gate
 * flagging a multi-stop gradient here.
 */
function LiveDot({ calm }: { calm: boolean }) {
  return (
    <span className="relative flex h-1.5 w-1.5" aria-hidden>
      {!calm && (
        <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-accent opacity-70" />
      )}
      <span className={cn('relative inline-flex h-1.5 w-1.5 rounded-full', calm ? 'bg-success' : 'bg-accent')} />
    </span>
  );
}

/** Sender-first identity. People scan mail by WHO before WHAT, and an initial
 *  is legible at 360px where a name is not. */
function Who({ sender, className }: { sender: string; className?: string }) {
  const who = parseSender(sender);
  return <Avatar name={who.name} email={who.email} className={cn('h-7 w-7 text-[11px]', className)} />;
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

  // The glance is "open loops", not "unread-ish mail". Mail arriving isn't news
  // — a loop nobody has closed is. This is the SAME number the app's Today
  // screen shows, taken from the same backend field, because a widget that
  // disagrees with the app destroys trust in both.
  const alerts = (data.urgent_count ?? 0) + (data.needs_reply_count ?? 0);
  const loops = data.open_loops ?? 0;
  const attention = alerts + loops;
  const allClear = data.all_clear ?? attention === 0;
  const cold = data.cold_count ?? 0;
  const owed = data.owed_count ?? 0;
  const waiting = data.waiting_count ?? 0;

  // One qualifier line, showing the worst state present — at 170px there's room
  // for exactly one thing, so it should be the thing that costs most to miss.
  const qualifier =
    cold > 0
      ? `${cold} going cold`
      : alerts > 0
        ? `${alerts} to answer`
        : owed > 0
          ? `${owed} you owe`
          : waiting > 0
            ? `${waiting} awaiting reply`
            : '';

  // ---- Small ---------------------------------------------------------------
  if (size === 'small') {
    return (
      <WidgetContainer size="small" className={cn('bg-card', className)}>
        <div className="flex h-full flex-col justify-between">
          <div className="flex items-center gap-1.5 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
            <LiveDot calm={allClear} /> Watching
          </div>
          <div>
            <div className="text-[56px] font-semibold leading-none tracking-tight text-foreground">
              {attention}
            </div>
            <div className="mt-1 text-[12px] font-medium text-muted-foreground">
              open loop{attention === 1 ? '' : 's'}
            </div>
            {/* Weight, not colour, does the ranking — going cold is the costly one. */}
            {qualifier && (
              <div className={cn('mt-0.5 text-[11px]', cold > 0 ? 'font-semibold text-foreground' : 'text-muted-foreground')}>
                {qualifier}
              </div>
            )}
          </div>
          {allClear ? (
            <span className="flex items-center gap-1.5 text-[13px] font-medium text-muted-foreground">
              <ShieldCheck className="h-4 w-4 text-success" /> All clear
            </span>
          ) : (
            <button
              onClick={openApp}
              className="inline-flex w-full items-center justify-center gap-1.5 rounded-full bg-accent py-2 text-[13px] font-semibold text-accent-foreground transition-transform active:scale-95"
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
      <WidgetContainer size="medium" className={cn('bg-card', className)}>
        <div className="flex h-full flex-row items-center gap-3">
          <div className="flex w-[36%] flex-shrink-0 flex-col justify-center border-r border-border/60 pr-3">
            <div className="mb-1 flex items-center gap-1.5 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
              <LiveDot calm={allClear} /> Live
            </div>
            <div className="text-[42px] font-semibold leading-none tracking-tight text-foreground">
              {attention}
            </div>
            <div className="mt-1 text-[12px] font-medium text-muted-foreground">
              open loop{attention === 1 ? '' : 's'}
            </div>
            {qualifier && (
              <div className={cn('mt-0.5 text-[11px]', cold > 0 ? 'font-semibold text-foreground' : 'text-muted-foreground')}>
                {qualifier}
              </div>
            )}
          </div>
          <button onClick={() => (top ? openAlert(top) : openApp())} className="flex min-w-0 flex-1 flex-col justify-center gap-1.5 text-left" aria-label="Open Gmail Sentry">
            {top ? (
              <AlertPeek alert={top} />
            ) : (
              <span className="flex items-center gap-1.5 text-[13px] font-medium text-muted-foreground">
                <ShieldCheck className="h-4 w-4 text-success" /> Nothing open
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
    <WidgetContainer size="large" className={cn('bg-card', className)}>
      <div className="flex h-full flex-col">
        <div className="mb-2.5 flex items-center justify-between">
          <div className="flex items-baseline gap-2">
            <span className="text-[34px] font-semibold leading-none tracking-tight text-foreground">
              {attention}
            </span>
            <span className="text-[13px] text-muted-foreground">
              open loop{attention === 1 ? '' : 's'}
            </span>
          </div>
          <span className="inline-flex items-center gap-1.5 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
            <LiveDot calm={allClear} /> Watching
          </span>
        </div>

        <div className="flex flex-1 flex-col gap-2 overflow-hidden">
          {shown.length > 0 ? (
            shown.map((a) => <AlertRow key={a.id} alert={a} onClick={() => openAlert(a)} />)
          ) : (
            <div className="flex flex-1 items-center justify-center gap-1.5 text-[13px] font-medium text-muted-foreground">
              <ShieldCheck className="h-4 w-4 text-success" /> Inbox is calm
            </div>
          )}
        </div>

        <div className="mt-3 flex items-center justify-between gap-2">
          <JunkButton label="Promo" count={cleanup.promo} onClick={() => void clearJunk('promotions')} />
          <JunkButton label="Social" count={cleanup.social} onClick={() => void clearJunk('social')} />
          <JunkButton label="Spam" count={cleanup.spam} onClick={() => void clearJunk('spam')} />
          {/* The one accent on the surface: the single thing worth tapping. */}
          <button
            onClick={openApp}
            aria-label="Open Gmail Sentry"
            className="flex h-full flex-shrink-0 items-center rounded-2xl bg-accent px-3 py-2 text-accent-foreground transition-transform active:scale-95"
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
    <div className="flex min-w-0 items-center gap-2.5">
      <Who sender={alert.sender} />
      <div className="min-w-0 flex-1">
        {/* Sender first: people scan mail by WHO before WHAT. */}
        <span className="block truncate text-[13px] font-semibold text-foreground">
          {parseSender(alert.sender).name}
        </span>
        <span className="block truncate text-[12px] text-muted-foreground">{alert.subject}</span>
        {alert.reply_ready && (
          <span className="mt-0.5 block text-[11px] font-medium text-accent">Reply ready</span>
        )}
      </div>
    </div>
  );
}

function AlertRow({ alert, onClick }: { alert: WidgetAlert; onClick: () => void }) {
  return (
    <button
      onClick={onClick}
      className="flex w-full items-center gap-2.5 rounded-xl px-1.5 py-1.5 text-left transition-colors hover:bg-muted/50 active:bg-muted/70"
    >
      <Who sender={alert.sender} className="h-6 w-6 text-[10px]" />
      <div className="min-w-0 flex-1">
        <span
          className={cn(
            'block truncate text-[13px] text-foreground',
            alert.tier === 'urgent' ? 'font-bold' : 'font-medium',
          )}
        >
          {parseSender(alert.sender).name}
        </span>
        <span className="block truncate text-[12px] text-muted-foreground">{alert.subject}</span>
      </div>
      {alert.reply_ready && (
        <span className="flex-shrink-0 text-[11px] font-medium text-accent">Reply</span>
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
        'flex min-w-0 flex-1 flex-col items-center rounded-2xl bg-muted/60 px-2 py-2 text-foreground transition-colors hover:bg-muted active:scale-95',
        count === 0 && 'opacity-40',
      )}
    >
      <span className="text-[15px] font-semibold leading-none">{count}</span>
      <span className="mt-0.5 truncate text-[11px] text-muted-foreground">{label}</span>
    </button>
  );
}
