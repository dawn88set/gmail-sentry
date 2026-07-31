import { useCallback, useEffect, useState } from 'react';
import { FolderTree, Check, X, Sparkles } from 'lucide-react';
import { Badge, Button } from '@clarittyai/app-ui';
import { useToast } from '@/components/Toast';
import { ListSection, ListGroup, ListRow } from '@/components/ios/List';
import { Toggle } from '@/components/ios/Toggle';
import {
  getFolders,
  approveFolder,
  rejectFolder,
  setFilingEnabled,
  toApiError,
  type MailFolder,
} from '@/lib/api';

/**
 * Smart filing settings + the folder approval queue.
 *
 * The approval queue is the whole safety story made visible: a proposed folder
 * is a question, not a decision, and nothing is written to the mailbox until
 * the user answers it. Renaming before approving is offered inline because the
 * user's wording for their own filing system should win over ours.
 */
export function FoldersSection() {
  const { show } = useToast();
  const [folders, setFolders] = useState<MailFolder[]>([]);
  const [enabled, setEnabled] = useState(false);
  const [loaded, setLoaded] = useState(false);
  const [busy, setBusy] = useState<string | null>(null);
  const [editing, setEditing] = useState<Record<string, string>>({});

  const load = useCallback(async () => {
    try {
      const d = await getFolders();
      setFolders(d.folders || []);
      setEnabled(!!d.filing_enabled);
    } catch {
      /* settings screen — a missing folder list shouldn't shout */
    } finally {
      setLoaded(true);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const toggle = async (next: boolean) => {
    setEnabled(next); // optimistic; the refetch below restores truth
    try {
      await setFilingEnabled(next);
      show({
        tone: 'success',
        text: next
          ? 'Filing on. New conversations will be proposed a folder — nothing is filed until you approve it.'
          : 'Filing off.',
      });
    } catch (err) {
      show({ tone: 'error', text: `Couldn’t change that: ${toApiError(err).message}` });
    } finally {
      void load();
    }
  };

  const decide = async (folder: MailFolder, approve: boolean) => {
    setBusy(folder.id);
    try {
      if (approve) {
        const renamed = (editing[folder.id] ?? '').trim();
        await approveFolder(folder.id, renamed && renamed !== folder.name ? renamed : undefined);
        show({ tone: 'success', text: `Filing into ${renamed || folder.name}.` });
      } else {
        await rejectFolder(folder.id);
        show({ tone: 'success', text: 'Won’t use that folder.' });
      }
    } catch (err) {
      show({ tone: 'error', text: `Couldn’t do that: ${toApiError(err).message}` });
    } finally {
      setBusy(null);
      void load();
    }
  };

  if (!loaded) return null;

  const proposed = folders.filter((f) => f.status === 'proposed');
  const active = folders.filter((f) => f.status === 'active');

  return (
    <>
      <ListSection
        title="Organize my mail"
        footer="Conversations are filed by who they're with — both your replies and theirs, so a thread lives in one place. Filing never hides anything: labelled mail stays in your inbox until you archive it."
      >
        <ListGroup variant="plain-mobile">
          <ListRow
            leading={
              <span className="inline-flex h-10 w-10 items-center justify-center rounded-xl bg-accent/15 text-accent">
                <FolderTree className="h-5 w-5" />
              </span>
            }
            title={<span className="block text-[15px] font-semibold text-foreground">Smart filing</span>}
            subtitle="Files new conversations into folders you approve"
            trailing={<Toggle checked={enabled} onChange={toggle} />}
          />
        </ListGroup>
      </ListSection>

      {proposed.length > 0 && (
        <ListSection
          title={`Folders waiting for you (${proposed.length})`}
          footer="Nothing is filed into a folder until you approve it. Rename it first if you'd word it differently."
        >
          <ListGroup variant="plain-mobile">
            {proposed.map((f) => (
              <div key={f.id} className="space-y-2 p-4">
                <div className="flex items-center gap-2">
                  <Sparkles className="h-4 w-4 flex-shrink-0 text-accent" />
                  <input
                    value={editing[f.id] ?? f.name}
                    onChange={(e) => setEditing((s) => ({ ...s, [f.id]: e.target.value }))}
                    className="min-w-0 flex-1 rounded-lg border border-border bg-background px-2.5 py-1.5 text-[14px] text-foreground outline-none focus:border-accent"
                    aria-label="Folder name"
                  />
                  <Badge tone="neutral">{f.kind === 'topical' ? 'Topic' : 'Person'}</Badge>
                </div>
                <div className="flex gap-2">
                  <Button
                    variant="primary"
                    size="sm"
                    className="flex-1 justify-center"
                    disabled={busy === f.id}
                    icon={<Check className="h-4 w-4" />}
                    onClick={() => decide(f, true)}
                  >
                    Use this folder
                  </Button>
                  <Button
                    variant="secondary"
                    size="sm"
                    disabled={busy === f.id}
                    icon={<X className="h-4 w-4" />}
                    onClick={() => decide(f, false)}
                  >
                    No thanks
                  </Button>
                </div>
              </div>
            ))}
          </ListGroup>
        </ListSection>
      )}

      {active.length > 0 && (
        <ListSection title="Folders in use">
          <ListGroup variant="plain-mobile">
            {active.map((f) => (
              <ListRow
                key={f.id}
                title={f.name}
                subtitle={
                  f.thread_count > 0
                    ? `${f.thread_count} conversation${f.thread_count === 1 ? '' : 's'}`
                    : 'No conversations filed yet'
                }
              />
            ))}
          </ListGroup>
        </ListSection>
      )}
    </>
  );
}

export default FoldersSection;
