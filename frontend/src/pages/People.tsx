import { useCallback, useEffect, useState } from 'react';
import { Users, X, Pin, BellOff } from 'lucide-react';
import { Badge, Button, EmptyState, ErrorState, type BadgeTone } from '@clarittyai/app-ui';
import { useToast } from '@/components/Toast';
import { Avatar } from '@/components/Avatar';
import { Screen } from '@/components/ios/Screen';
import { ListGroup, ListRow, ListSection } from '@/components/ios/List';
import { SkeletonRows } from '@/components/ios/Skeleton';
import {
  getCounterparties,
  updateCounterparty,
  toApiError,
  type Counterparty,
  type Relationship,
} from '@/lib/api';

const REL_LABEL: Record<Relationship, string> = {
  customer: 'Client',
  prospect: 'Prospect',
  internal: 'Colleague',
  vendor: 'Supplier',
  bulk: 'Automated',
  unknown: 'Unclassified',
};

const REL_TONE: Record<Relationship, BadgeTone> = {
  customer: 'success',
  prospect: 'accent',
  internal: 'neutral',
  vendor: 'neutral',
  bulk: 'neutral',
  unknown: 'neutral',
};

/** The classes worth offering. `bulk` isn't here — that's a judgement about the
 *  address, not the relationship, and muting is the better tool for it. */
const CHOICES: Relationship[] = ['customer', 'prospect', 'internal', 'vendor', 'unknown'];

function hours(h: number | null): string {
  if (h === null || h === undefined) return '—';
  if (h < 1) return '<1h';
  if (h < 48) return `${Math.round(h)}h`;
  return `${Math.round(h / 24)}d`;
}

/**
 * Who it would cost you to ignore.
 *
 * Two jobs. The first is clarity: a business owner rarely has a list of the
 * people their business actually runs through, and this one is derived from
 * behaviour rather than from who sends the most mail.
 *
 * The second matters more. `relationship` is not a label — it picks the filing
 * folder (Clients/… vs Suppliers/…) and how long silence is normal before a
 * thread counts as cold. Inference gets it wrong sometimes, and until this
 * screen existed there was no way to say so. A correction here is marked as
 * stated by the user, so inference never overwrites it afterwards.
 */
export default function People() {
  const { show } = useToast();
  const [rows, setRows] = useState<Counterparty[]>([]);
  const [loading, setLoading] = useState(true);
  // Distinct from "loaded and empty" — claiming someone has no relationships
  // after a failed request would be a confident lie.
  const [loadError, setLoadError] = useState<string | null>(null);
  const [selected, setSelected] = useState<Counterparty | null>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    try {
      const d = await getCounterparties(100);
      setRows(d.counterparties || []);
      setLoadError(null);
    } catch (err) {
      const e = toApiError(err);
      setLoadError(e.message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const patch = async (
    cp: Counterparty,
    body: Parameters<typeof updateCounterparty>[1],
    label: string,
  ) => {
    setBusy(true);
    try {
      await updateCounterparty(cp.id, body);
      show({ tone: 'success', text: label });
      setSelected(null);
    } catch (err) {
      show({ tone: 'error', text: `Couldn’t save: ${toApiError(err).message}` });
    } finally {
      setBusy(false);
      void load();
    }
  };

  const known = rows.filter((c) => !c.muted && c.relationship !== 'bulk');
  const quiet = rows.filter((c) => c.muted);

  return (
    <>
      {selected && (
        <PersonSheet
          person={selected}
          busy={busy}
          onClose={() => setSelected(null)}
          onPatch={patch}
        />
      )}

      <Screen title="People">
        {loading ? (
          <ListGroup variant="plain-mobile">
            <SkeletonRows count={6} />
          </ListGroup>
        ) : loadError ? (
          <ListGroup variant="plain-mobile">
            <ErrorState
              title="Couldn’t load your contacts"
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
        ) : known.length === 0 ? (
          <ListGroup variant="plain-mobile">
            <EmptyState
              icon={<Users className="h-6 w-6 text-accent" />}
              title="Still learning"
              description="Once a few scans have run, the people your business actually runs through will show up here — ranked by whether you reply to them, not by how much they send."
            />
          </ListGroup>
        ) : (
          <ListSection
            title="Ranked by who you actually answer"
            footer="Setting someone as a Client or Supplier changes where their mail is filed and how long silence is normal before a thread counts as cold."
          >
            <ListGroup variant="plain-mobile">
              {known.map((c) => (
                <ListRow
                  key={c.id}
                  onClick={() => setSelected(c)}
                  leading={<Avatar name={c.display_name} email={c.email} className="h-9 w-9 text-sm" />}
                  title={
                    <div className="flex items-baseline gap-2">
                      <span className="min-w-0 flex-1 truncate text-[15px] font-semibold text-foreground">
                        {c.display_name || c.email}
                      </span>
                      {c.pinned && <Pin className="h-3.5 w-3.5 flex-shrink-0 text-accent" />}
                    </div>
                  }
                  subtitle={
                    <div className="mt-0.5 space-y-1">
                      <div className="truncate text-[12px] text-muted-foreground">{c.email}</div>
                      <div className="flex items-center gap-1.5">
                        <Badge tone={REL_TONE[c.relationship]}>{REL_LABEL[c.relationship]}</Badge>
                        <span className="truncate text-[12px] text-muted-foreground">
                          you reply {c.your_reply_rate}% · {c.thread_count} thread
                          {c.thread_count === 1 ? '' : 's'}
                        </span>
                      </div>
                    </div>
                  }
                  chevron
                />
              ))}
            </ListGroup>
          </ListSection>
        )}

        {quiet.length > 0 && (
          <ListSection title="Muted" footer="Muted people never raise alerts, open loops, or get filed.">
            <ListGroup variant="plain-mobile">
              {quiet.map((c) => (
                <ListRow
                  key={c.id}
                  onClick={() => setSelected(c)}
                  leading={<BellOff className="h-4 w-4 text-muted-foreground" />}
                  title={c.display_name || c.email}
                  subtitle={c.email}
                  chevron
                />
              ))}
            </ListGroup>
          </ListSection>
        )}
      </Screen>
    </>
  );
}

function PersonSheet({
  person,
  busy,
  onClose,
  onPatch,
}: {
  person: Counterparty;
  busy: boolean;
  onClose: () => void;
  onPatch: (
    cp: Counterparty,
    body: Parameters<typeof updateCounterparty>[1],
    label: string,
  ) => void;
}) {
  const c = person;
  return (
    <div
      className="fixed inset-0 z-50 flex items-end justify-center bg-black/40 sm:items-center"
      onClick={onClose}
    >
      <div
        className="max-h-[88vh] w-full overflow-y-auto rounded-t-3xl bg-card p-5 shadow-apple-lg sm:max-w-md sm:rounded-3xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="mb-4 flex items-start gap-3">
          <Avatar name={c.display_name} email={c.email} className="h-11 w-11" />
          <div className="min-w-0 flex-1">
            <div className="truncate text-[17px] font-semibold text-foreground">
              {c.display_name || c.email}
            </div>
            <div className="truncate text-[13px] text-muted-foreground">{c.email}</div>
          </div>
          <Button variant="ghost" size="sm" onClick={onClose} aria-label="Close">
            <X className="h-4 w-4" />
          </Button>
        </div>

        {/* The evidence behind the ranking, so it isn't a black box. */}
        <div className="mb-4 grid grid-cols-2 gap-2 text-[13px]">
          <Stat label="You reply to them" value={`${c.your_reply_rate}%`} />
          <Stat label="They reply to you" value={`${c.their_reply_rate}%`} />
          <Stat label="You answer in" value={hours(c.your_median_reply_h)} />
          <Stat label="They answer in" value={hours(c.their_median_reply_h)} />
          <Stat label="Conversations" value={String(c.thread_count)} />
          <Stat label="Importance" value={`${c.importance}/100`} />
        </div>

        <div className="mb-2 text-[12px] font-semibold uppercase tracking-wide text-muted-foreground">
          They are a…
        </div>
        <div className="mb-1 grid grid-cols-2 gap-2">
          {CHOICES.map((r) => (
            <Button
              key={r}
              variant={c.relationship === r ? 'primary' : 'secondary'}
              size="sm"
              disabled={busy}
              onClick={() => onPatch(c, { relationship: r }, `Saved — ${REL_LABEL[r]}.`)}
            >
              {REL_LABEL[r]}
            </Button>
          ))}
        </div>
        <p className="mb-4 text-[12px] text-muted-foreground">
          {c.relationship_source === 'user'
            ? 'You set this. It won’t be changed automatically.'
            : 'Worked out from how you two correspond — correct it if it’s wrong.'}
        </p>

        <div className="grid grid-cols-2 gap-2">
          <Button
            variant={c.pinned ? 'primary' : 'secondary'}
            size="sm"
            disabled={busy}
            icon={<Pin className="h-4 w-4" />}
            onClick={() =>
              onPatch(c, { pinned: !c.pinned }, c.pinned ? 'Unpinned.' : 'Always important now.')
            }
          >
            {c.pinned ? 'Pinned' : 'Always important'}
          </Button>
          <Button
            variant={c.muted ? 'primary' : 'secondary'}
            size="sm"
            disabled={busy}
            icon={<BellOff className="h-4 w-4" />}
            onClick={() => onPatch(c, { muted: !c.muted }, c.muted ? 'Unmuted.' : 'Muted.')}
          >
            {c.muted ? 'Muted' : 'Mute'}
          </Button>
        </div>
      </div>
    </div>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-xl bg-muted/60 px-3 py-2">
      <div className="text-[11px] text-muted-foreground">{label}</div>
      <div className="text-[15px] font-semibold text-foreground">{value}</div>
    </div>
  );
}
