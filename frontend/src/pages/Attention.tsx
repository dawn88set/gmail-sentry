import { useEffect, useState, useCallback } from 'react';
import { useSearchParams } from 'react-router-dom';
import { AnimatePresence } from 'framer-motion';
import { ShieldCheck } from 'lucide-react';
import { Button, EmptyState, ErrorState, Tabs } from '@clarittyai/app-ui';
import { useToast } from '@/components/Toast';
import { Avatar, parseSender } from '@/components/Avatar';
import { AlertSheet } from '@/components/AlertSheet';
import { Screen } from '@/components/ios/Screen';
import { ListGroup, ListRow } from '@/components/ios/List';
import { SkeletonRows } from '@/components/ios/Skeleton';
import { getAlerts, toApiError, type Alert, type Tier } from '@/lib/api';
import { cn } from '@/lib/utils';

const TIER_CHIP: Record<Tier, string> = {
  urgent: 'bg-accent/15 text-accent',
  needs_reply: 'bg-muted text-muted-foreground',
  fyi: 'bg-muted text-muted-foreground',
};
const TIER_LABEL: Record<Tier, string> = { urgent: 'Urgent', needs_reply: 'Reply', fyi: 'FYI' };

const FILTERS: { key: string; label: string; tier?: Tier }[] = [
  { key: 'all', label: 'All' },
  { key: 'urgent', label: 'Urgent', tier: 'urgent' },
  { key: 'needs_reply', label: 'To reply', tier: 'needs_reply' },
];

function relTime(iso?: string | null): string {
  if (!iso) return '';
  const t = new Date(iso.endsWith('Z') || iso.includes('+') ? iso : `${iso}Z`).getTime();
  if (Number.isNaN(t)) return '';
  const s = Math.max(0, Math.floor((Date.now() - t) / 1000));
  if (s < 60) return 'now';
  if (s < 3600) return `${Math.floor(s / 60)}m`;
  if (s < 86400) return `${Math.floor(s / 3600)}h`;
  return `${Math.floor(s / 86400)}d`;
}

export default function Attention() {
  const { show } = useToast();
  const [searchParams, setSearchParams] = useSearchParams();
  const [filter, setFilter] = useState('all');
  const [alerts, setAlerts] = useState<Alert[]>([]);
  const [loading, setLoading] = useState(true);
  // Distinct from "loaded and empty" — without it a failed load renders the
  // all-clear state, which claims nothing needs attention when we don't know.
  const [loadError, setLoadError] = useState<string | null>(null);
  const [selected, setSelected] = useState<Alert | null>(null);
  // The alert id whose reply should auto-open (arrived via a notification link).
  const [autoReplyId, setAutoReplyId] = useState<string | null>(null);

  const load = useCallback(async () => {
    const f = FILTERS.find((x) => x.key === filter);
    try {
      setAlerts(await getAlerts('active', f?.tier));
      setLoadError(null);
    } catch (err) {
      const e = toApiError(err);
      setLoadError(e.message);
      show({ tone: 'error', text: `Couldn’t load: ${e.message}` });
    } finally {
      setLoading(false);
    }
  }, [filter, show]);

  useEffect(() => {
    void load();
  }, [load]);

  // Deep link from a notification: ?focus=<alertId> → open that alert's reply.
  const focusId = searchParams.get('focus');
  useEffect(() => {
    if (!focusId || loading) return;
    const match = alerts.find((a) => a.id === focusId);
    if (match) {
      setSelected(match);
      setAutoReplyId(focusId);
    } else {
      show({ tone: 'error', text: 'That item is no longer waiting for a reply.' });
    }
    const next = new URLSearchParams(searchParams);
    next.delete('focus');
    setSearchParams(next, { replace: true });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [focusId, loading, alerts]);

  return (
    <>
      <AnimatePresence>
        {selected && (
          <AlertSheet
            alert={selected}
            autoReply={selected.id === autoReplyId}
            onClose={() => {
              setSelected(null);
              setAutoReplyId(null);
            }}
            onChanged={() => void load()}
          />
        )}
      </AnimatePresence>

      <Screen title="Attention">
        {/* Segmented filter */}
        <Tabs
          variant="pill"
          items={FILTERS.map((f) => ({ value: f.key, label: f.label }))}
          value={filter}
          onValueChange={setFilter}
        />

        {loading ? (
          <ListGroup variant="plain-mobile">
            <SkeletonRows count={6} />
          </ListGroup>
        ) : loadError ? (
          <ListGroup variant="plain-mobile">
            <ErrorState
              title="Couldn’t load your alerts"
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
        ) : alerts.length === 0 ? (
          <ListGroup variant="plain-mobile">
            <EmptyState
              icon={<ShieldCheck className="h-6 w-6 text-accent" />}
              title="All clear"
              description="Nothing needs your attention here."
            />
          </ListGroup>
        ) : (
          <ListGroup variant="plain-mobile">
            {alerts.map((a) => {
              const who = parseSender(a.sender || '');
              return (
                <ListRow
                  key={a.id}
                  onClick={() => setSelected(a)}
                  leading={<Avatar name={who.name} email={who.email} className="h-9 w-9 text-sm" />}
                  title={
                    <div className="flex items-baseline gap-2">
                      <span className="min-w-0 flex-1 truncate text-[15px] font-medium text-foreground">
                        {a.subject || '(no subject)'}
                      </span>
                      <span className="flex-shrink-0 text-[12px] text-muted-foreground">{relTime(a.created_at)}</span>
                    </div>
                  }
                  subtitle={
                    <div className="mt-0.5 flex items-center gap-1.5">
                      <span className={cn('flex-shrink-0 rounded-full px-1.5 py-0.5 text-[10px] font-semibold', TIER_CHIP[a.tier])}>
                        {TIER_LABEL[a.tier]}
                      </span>
                      <span className="min-w-0 flex-1 truncate">
                        <span className="text-foreground/70">{who.name || a.sender}</span>
                        {a.reason ? ` — ${a.reason}` : ''}
                      </span>
                    </div>
                  }
                  chevron
                />
              );
            })}
          </ListGroup>
        )}
      </Screen>
    </>
  );
}
