import { useEffect, useState, useCallback } from 'react';
import { AnimatePresence } from 'framer-motion';
import { ShieldCheck } from 'lucide-react';
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
  const [filter, setFilter] = useState('all');
  const [alerts, setAlerts] = useState<Alert[]>([]);
  const [loading, setLoading] = useState(true);
  const [selected, setSelected] = useState<Alert | null>(null);

  const load = useCallback(async () => {
    const f = FILTERS.find((x) => x.key === filter);
    try {
      setAlerts(await getAlerts('active', f?.tier));
    } catch (err) {
      show({ tone: 'error', text: `Couldn’t load: ${toApiError(err).message}` });
    } finally {
      setLoading(false);
    }
  }, [filter, show]);

  useEffect(() => {
    void load();
  }, [load]);

  return (
    <>
      <AnimatePresence>
        {selected && (
          <AlertSheet
            alert={selected}
            onClose={() => setSelected(null)}
            onChanged={() => void load()}
          />
        )}
      </AnimatePresence>

      <Screen title="Attention">
        {/* Segmented filter */}
        <div className="flex gap-1 rounded-full border border-border/70 bg-muted/50 p-1">
          {FILTERS.map((f) => (
            <button
              key={f.key}
              onClick={() => setFilter(f.key)}
              className={cn(
                'flex-1 rounded-full px-3 py-1.5 text-sm font-medium transition-colors',
                filter === f.key ? 'bg-card text-foreground shadow-sm' : 'text-muted-foreground hover:text-foreground',
              )}
            >
              {f.label}
            </button>
          ))}
        </div>

        {loading ? (
          <ListGroup variant="plain-mobile">
            <SkeletonRows count={6} />
          </ListGroup>
        ) : alerts.length === 0 ? (
          <ListGroup variant="plain-mobile">
            <div className="flex flex-col items-center gap-2 p-10 text-center">
              <div className="inline-flex h-12 w-12 items-center justify-center rounded-2xl bg-accent/15">
                <ShieldCheck className="h-6 w-6 text-accent" />
              </div>
              <p className="text-[15px] font-semibold text-foreground">All clear</p>
              <p className="text-[13px] text-muted-foreground">Nothing needs your attention here.</p>
            </div>
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
