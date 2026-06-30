/**
 * GOLDEN REFERENCE — not built, not imported (lives outside src/, suffix
 * `.golden.tsx` so tsc/vite ignore it). It shows the BAR for a generated
 * `frontend/src/pages/Dashboard.tsx`: COMPOSE THE KIT (`@clarittyai/app-ui`),
 * don't hand-roll raw <div>s. Adapt the domain/content to the real app — do
 * NOT copy this content.
 *
 * Why it's good — the kit bakes the discipline in, so you can't get it wrong:
 *  - `AppShell` owns the background + one centered, constrained column.
 *  - `PageHeader` states the purpose with ONE primary action (single `action`
 *    slot — structurally one primary per view), no hero pitch.
 *  - `Section` gives consistent rhythm; `List`/`Row`, `Card`, `Stat` are the
 *    content primitives. Token-only color (no hex), dark-mode parity, ≥44px
 *    targets, 8pt spacing — all from the kit.
 *  - All three states are first-class: `SkeletonCards` (loading), `EmptyState`
 *    (short line + the primary action), `ErrorState` (high-contrast + retry).
 *
 * Domain here is a neutral fictional "reading queue" so it reads as reference.
 */
import { useEffect, useState } from 'react';
import { Plus, RefreshCw } from 'lucide-react';
import {
  AppShell,
  PageHeader,
  Section,
  Stat,
  Button,
  List,
  Row,
  Badge,
  EmptyState,
  ErrorState,
  SkeletonCards,
} from '@clarittyai/app-ui';
import { appName } from '@/lib/app-meta';
import { getQueue, getStats, addItem, type QueueItem, type Stats } from '@/lib/api';

export default function Dashboard() {
  const [items, setItems] = useState<QueueItem[] | null>(null);
  const [stats, setStats] = useState<Stats | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = async () => {
    try {
      const [q, s] = await Promise.all([getQueue(), getStats()]);
      setItems(q);
      setStats(s);
      setError(null);
    } catch {
      setError('Could not load your queue');
    }
  };

  useEffect(() => {
    void load();
  }, []);

  return (
    <AppShell>
      <PageHeader
        title={appName}
        description="Everything you saved to read, in one calm queue."
        action={
          <Button icon={<Plus className="h-4 w-4" />} onClick={() => void addItem().then(load)}>
            Add link
          </Button>
        }
      />

      {error ? (
        <ErrorState
          title={error}
          action={
            <Button variant="secondary" icon={<RefreshCw className="h-4 w-4" />} onClick={() => void load()}>
              Retry
            </Button>
          }
        />
      ) : items === null ? (
        <SkeletonCards count={4} />
      ) : (
        <>
          <Section title="This week">
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
              <Stat label="To read" value={stats?.unread ?? 0} />
              <Stat label="Read" value={stats?.read ?? 0} delta={`${stats?.readToday ?? 0} today`} deltaTone="success" />
              <Stat label="Added" value={stats?.addedToday ?? 0} delta="today" />
            </div>
          </Section>

          <Section title="Up next">
            {items.length === 0 ? (
              <EmptyState
                title="Nothing in your queue yet"
                description="Save a link and it'll show up here, ready to read."
                action={<Button onClick={() => void addItem().then(load)}>Add your first link</Button>}
              />
            ) : (
              <List>
                {items.map((it) => (
                  <Row
                    key={it.id}
                    title={it.title}
                    subtitle={it.source}
                    trailing={<Badge tone={it.read ? 'neutral' : 'accent'}>{it.read ? 'Read' : 'New'}</Badge>}
                  />
                ))}
              </List>
            )}
          </Section>
        </>
      )}
    </AppShell>
  );
}
