import { useCallback, useEffect, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { Repeat2, ExternalLink, Clock, Check, X } from 'lucide-react';
import { Button, EmptyState, ErrorState, Tabs } from '@clarittyai/app-ui';
import { useToast } from '@/components/Toast';
import { FollowUpRow } from '@/components/FollowUpRow';
import { NudgeComposer } from '@/components/NudgeComposer';
import { Screen } from '@/components/ios/Screen';
import { ListGroup } from '@/components/ios/List';
import { ActionTile } from '@/components/ios/ActionTile';
import { SkeletonRows } from '@/components/ios/Skeleton';
import {
  getFollowUps,
  snoozeFollowUp,
  doneFollowUp,
  ignoreFollowUp,
  syncFollowUps,
  toApiError,
  type FollowUp,
  type FollowUpCounts,
  type FollowUpFilter,
} from '@/lib/api';

const FILTERS: { value: FollowUpFilter; label: string }[] = [
  { value: 'open', label: 'All' },
  { value: 'owed', label: 'You owe' },
  { value: 'waiting', label: 'Waiting' },
  { value: 'cold', label: 'Cold' },
];

const EMPTY: Record<string, { title: string; description: string }> = {
  open: { title: 'No open loops', description: 'Nothing is waiting on you, and nobody has gone quiet.' },
  owed: { title: 'You owe nobody', description: 'Every thread where the ball was in your court is answered.' },
  waiting: { title: 'Nothing outstanding', description: "You're not waiting on a reply from anyone." },
  cold: { title: 'Nothing has gone cold', description: 'Every thread you’re waiting on is still within normal time for that person.' },
};

/**
 * Open loops — what you owe people, and what you're waiting on.
 *
 * "Cold" is a derived overlay rather than a separate bucket: it filters the
 * waiting set to threads past what's normal *for that person*, so nothing is
 * hidden by picking a tab.
 */
export default function FollowUps() {
  const { show } = useToast();
  const [searchParams, setSearchParams] = useSearchParams();
  const [filter, setFilter] = useState<FollowUpFilter>(
    (searchParams.get('state') as FollowUpFilter) || 'open',
  );
  const [rows, setRows] = useState<FollowUp[]>([]);
  const [counts, setCounts] = useState<FollowUpCounts | null>(null);
  const [loading, setLoading] = useState(true);
  // Distinct from "loaded and empty": rendering "no open loops" after a failed
  // request would claim nothing needs the user when we simply don't know.
  const [loadError, setLoadError] = useState<string | null>(null);
  const [selected, setSelected] = useState<FollowUp | null>(null);
  const [busy, setBusy] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const data = await getFollowUps(filter);
      setRows(data.followups || []);
      setCounts(data.counts || null);
      setLoadError(null);
    } catch (err) {
      const e = toApiError(err);
      setLoadError(e.message);
      show({ tone: 'error', text: `Couldn’t load follow-ups: ${e.message}` });
    } finally {
      setLoading(false);
    }
  }, [filter, show]);

  useEffect(() => {
    void load();
  }, [load]);

  const pick = (value: string) => {
    const next = value as FollowUpFilter;
    setFilter(next);
    const params = new URLSearchParams(searchParams);
    if (next === 'open') params.delete('state');
    else params.set('state', next);
    setSearchParams(params, { replace: true });
  };

  const act = async (label: string, id: string, run: () => Promise<unknown>) => {
    setBusy(id);
    try {
      await run();
      show({ tone: 'success', text: label });
      setSelected(null);
    } catch (err) {
      show({ tone: 'error', text: `Couldn’t do that: ${toApiError(err).message}` });
    } finally {
      setBusy(null);
      void load();
    }
  };

  const resync = async () => {
    setBusy('sync');
    try {
      const out = await syncFollowUps();
      setCounts(out.counts);
      show({ tone: 'success', text: 'Re-checked every thread.' });
    } catch (err) {
      show({ tone: 'error', text: `Couldn’t refresh: ${toApiError(err).message}` });
    } finally {
      setBusy(null);
      void load();
    }
  };

  const tabItems = FILTERS.map((f) => ({
    value: f.value,
    label: f.label,
    badge:
      counts && f.value !== 'open'
        ? String(
            f.value === 'owed' ? counts.owed : f.value === 'waiting' ? counts.waiting : counts.cold,
          )
        : counts
          ? String(counts.open_loops)
          : undefined,
  }));

  const empty = EMPTY[filter] ?? EMPTY.open;

  return (
    <>
      {selected && (
        <FollowUpActions
          followUp={selected}
          busy={busy === selected.id}
          onClose={() => setSelected(null)}
          onSent={() => {
            setSelected(null);
            void load();
          }}
          onSnooze={(h) => act('Snoozed.', selected.id, () => snoozeFollowUp(selected.id, h))}
          onDone={() => act('Loop closed.', selected.id, () => doneFollowUp(selected.id))}
          onIgnore={() => act('Won’t track this thread.', selected.id, () => ignoreFollowUp(selected.id))}
        />
      )}

      <Screen
        title="Follow-ups"
        action={
          <Button variant="secondary" size="sm" onClick={resync} disabled={busy === 'sync'}>
            {busy === 'sync' ? 'Checking' : 'Re-check'}
          </Button>
        }
      >
        <Tabs variant="pill" items={tabItems} value={filter} onValueChange={pick} />

        {loading ? (
          <ListGroup variant="plain-mobile">
            <SkeletonRows count={5} />
          </ListGroup>
        ) : loadError ? (
          <ListGroup variant="plain-mobile">
            <ErrorState
              title="Couldn’t load your follow-ups"
              description={loadError}
              action={
                <Button
                  variant="secondary"
                  size="sm"
                  onClick={() => {
                    setLoading(true);
                    void load();
                  }}
                >
                  Try again
                </Button>
              }
            />
          </ListGroup>
        ) : rows.length === 0 ? (
          <ListGroup variant="plain-mobile">
            <EmptyState
              icon={<Repeat2 className="h-6 w-6 text-accent" />}
              title={empty.title}
              description={empty.description}
            />
          </ListGroup>
        ) : (
          <ListGroup variant="plain-mobile">
            {rows.map((f) => (
              <FollowUpRow key={f.id} followUp={f} onClick={() => setSelected(f)} />
            ))}
          </ListGroup>
        )}
      </Screen>
    </>
  );
}

/**
 * Actions for one loop.
 *
 * The nudge composer appears only where the ball is genuinely theirs — on a
 * thread the user owes, chasing them for your own silence would be absurd. It's
 * the one irreversible action in the app, so it lives behind its own guards
 * (see NudgeComposer and backend/services/nudges.py) rather than sitting in
 * this action grid where a mis-tap could reach it.
 */
function FollowUpActions({
  followUp,
  busy,
  onClose,
  onSnooze,
  onDone,
  onIgnore,
  onSent,
}: {
  followUp: FollowUp;
  busy: boolean;
  onClose: () => void;
  onSnooze: (hours: number) => void;
  onDone: () => void;
  onIgnore: () => void;
  onSent: () => void;
}) {
  const [snoozeOpen, setSnoozeOpen] = useState(false);
  const gmail = `https://mail.google.com/mail/u/0/#all/${followUp.thread_id}`;

  return (
    <div className="fixed inset-0 z-50 flex items-end justify-center bg-black/40 sm:items-center" onClick={onClose}>
      <div
        className="w-full rounded-t-3xl bg-card p-5 shadow-apple-lg sm:max-w-md sm:rounded-3xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="mb-3 flex items-start gap-3">
          <div className="min-w-0 flex-1">
            <div className="truncate text-[17px] font-semibold text-foreground">
              {followUp.counterparty_name || followUp.counterparty_email}
            </div>
            <div className="truncate text-[13px] text-muted-foreground">{followUp.subject}</div>
          </div>
          <Button variant="ghost" size="sm" onClick={onClose} aria-label="Close">
            <X className="h-4 w-4" />
          </Button>
        </div>

        {followUp.ask_summary && (
          <div className="mb-4 rounded-2xl bg-muted/60 p-3 text-[14px] leading-relaxed text-foreground">
            {followUp.ask_summary}
          </div>
        )}

        {/* Only where the ball is genuinely theirs. On a thread the user owes,
            chasing them for your own silence would be absurd — so the composer
            simply isn't offered. */}
        {(followUp.state === 'going_cold' || followUp.state === 'awaiting_them') && (
          <div className="mb-4">
            <NudgeComposer followUp={followUp} onSent={onSent} />
          </div>
        )}

        {snoozeOpen ? (
          <div className="grid grid-cols-3 gap-2">
            {[
              { label: '3 hours', hours: 3 },
              { label: 'Tomorrow', hours: 18 },
              { label: 'Next week', hours: 168 },
            ].map((s) => (
              <Button key={s.hours} variant="secondary" size="sm" onClick={() => onSnooze(s.hours)}>
                {s.label}
              </Button>
            ))}
          </div>
        ) : (
          <div className="grid grid-cols-3 gap-2">
            <ActionTile
              icon={<ExternalLink className="h-5 w-5" />}
              label="Open"
              onClick={() => window.open(gmail, '_blank', 'noopener')}
            />
            <ActionTile
              icon={<Clock className="h-5 w-5" />}
              label="Snooze"
              active={snoozeOpen}
              onClick={() => setSnoozeOpen(true)}
            />
            <ActionTile
              icon={<Check className="h-5 w-5" />}
              label="Close loop"
              disabled={busy}
              onClick={onDone}
            />
          </div>
        )}

        <Button variant="ghost" size="sm" className="mt-3 w-full justify-center" onClick={onIgnore} disabled={busy}>
          Not a follow-up
        </Button>
      </div>
    </div>
  );
}
