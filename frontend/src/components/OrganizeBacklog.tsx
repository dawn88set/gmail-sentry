import { useCallback, useEffect, useState } from 'react';
import { Archive, Loader2, RotateCcw } from 'lucide-react';
import { Button } from '@clarittyai/app-ui';
import { Badge } from '@/components/ios/Badge';
import { useToast } from '@/components/Toast';
import { ListGroup, ListSection } from '@/components/ios/List';
import { Toggle } from '@/components/ios/Toggle';
import {
  getBacklogPreview,
  organizeBacklog,
  toApiError,
  type BacklogPreviewRow,
} from '@/lib/api';

/**
 * Organize the mail that was already there.
 *
 * Automatic filing is forward-only from the moment it's switched on, and that's
 * the right default — nobody wants an app relabelling four thousand old threads
 * because they flipped a toggle. But the consequence was that the backlog, the
 * mail someone installed this to get organized, was the one thing it would
 * never touch.
 *
 * The preview IS the approval surface. Each row says how many conversations
 * would move and where, and ticking it is the decision — a stronger, better
 * informed signal than the passive queue the automatic path uses, which is why
 * these folders are created active rather than proposed.
 *
 * Nothing is pre-selected. A screen that arrives with every folder ticked and a
 * button that says "Organize 412 conversations" is a trap, not a choice.
 */
export function OrganizeBacklog({ onDone }: { onDone?: () => void }) {
  const { show } = useToast();
  const [rows, setRows] = useState<BacklogPreviewRow[]>([]);
  const [picked, setPicked] = useState<Set<string>>(new Set());
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [remaining, setRemaining] = useState(0);

  const load = useCallback(async () => {
    try {
      const d = await getBacklogPreview(30);
      setRows(d.preview || []);
    } catch {
      /* the folders list above already surfaces connection problems */
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const toggle = (folder: string) =>
    setPicked((s) => {
      const next = new Set(s);
      next.has(folder) ? next.delete(folder) : next.add(folder);
      return next;
    });

  const run = async () => {
    setBusy(true);
    const chosen = [...picked];
    try {
      const out = await organizeBacklog(chosen, 30);
      setRemaining(out.remaining || 0);
      show({
        tone: 'success',
        text: out.threads
          ? `Organized ${out.threads} conversation${out.threads === 1 ? '' : 's'}.` +
            (out.remaining ? ` ${out.remaining} left — run it again to continue.` : '')
          : 'Nothing needed moving.',
      });
      setPicked(new Set());
    } catch (err) {
      const e = toApiError(err);
      show({
        tone: 'error',
        text:
          e.status === 409
            ? 'Connect Gmail, then try again.'
            : `Couldn’t organize: ${e.message}`,
      });
    } finally {
      setBusy(false);
      void load();
      onDone?.();
    }
  };

  if (loading || rows.length === 0) return null;

  const total = rows.filter((r) => picked.has(r.folder)).reduce((n, r) => n + r.threads, 0);
  const waiting = rows.reduce((n, r) => n + r.threads, 0);

  return (
    <ListSection
      title="Mail you already had"
      footer="Filing only handles new conversations from the day you switch it on, so anything older stays where it is until you say otherwise. Labelling never removes mail from your inbox."
    >
      <ListGroup variant="plain-mobile">
        <div className="flex items-start gap-3 px-4 py-3">
          <span className="mt-0.5 inline-flex h-9 w-9 flex-shrink-0 items-center justify-center rounded-xl bg-accent/15 text-accent">
            <Archive className="h-4 w-4" />
          </span>
          <div className="min-w-0 flex-1">
            <div className="text-[15px] font-semibold text-foreground">
              {waiting} conversation{waiting === 1 ? '' : 's'} could be organized
            </div>
            <div className="text-[13px] text-muted-foreground">
              From your last 30 days. Pick where they should go.
            </div>
          </div>
        </div>

        {rows.map((r) => (
          <div key={r.folder} className="flex items-center gap-3 px-4 py-3">
            <div className="min-w-0 flex-1">
              <div className="flex items-center gap-2">
                <span className="truncate text-[15px] font-medium text-foreground">
                  {r.folder}
                </span>
                {r.rejected && <Badge tone="warning">Declined before</Badge>}
                {!r.exists && !r.rejected && <Badge tone="neutral">New</Badge>}
              </div>
              <div className="text-[13px] text-muted-foreground">
                {r.threads} conversation{r.threads === 1 ? '' : 's'}
              </div>
            </div>
            <Toggle
              checked={picked.has(r.folder)}
              onChange={() => toggle(r.folder)}
              aria-label={`Organize ${r.threads} conversations into ${r.folder}`}
            />
          </div>
        ))}
      </ListGroup>

      <Button
        variant="primary"
        className="w-full justify-center"
        disabled={busy || picked.size === 0}
        icon={busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <Archive className="h-4 w-4" />}
        onClick={run}
      >
        {busy
          ? 'Organizing…'
          : picked.size === 0
            ? 'Pick a folder to continue'
            : `Organize ${total} conversation${total === 1 ? '' : 's'}`}
      </Button>

      {remaining > 0 && (
        <p className="flex items-center gap-1.5 px-4 text-[12px] text-muted-foreground">
          <RotateCcw className="h-3.5 w-3.5 flex-shrink-0" />
          {remaining} more to go — large mailboxes are done in batches so Gmail isn’t
          hammered. Run it again to continue.
        </p>
      )}
    </ListSection>
  );
}

export default OrganizeBacklog;
