import { useCallback, useEffect, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { AlertTriangle, ChevronLeft, ExternalLink, FolderTree } from 'lucide-react';
import { Button, EmptyState, ErrorState } from '@clarittyai/app-ui';
import { Badge } from '@/components/ios/Badge';
import { Avatar } from '@/components/Avatar';
import { Screen } from '@/components/ios/Screen';
import { ListGroup, ListSection } from '@/components/ios/List';
import { SkeletonRows } from '@/components/ios/Skeleton';
import {
  getFolderThreads,
  toApiError,
  type FolderThread,
  type MailFolder,
} from '@/lib/api';

/**
 * What's actually in a folder.
 *
 * A folder that shows only a count is a claim the user can't check — and filing
 * writes labels into their real mailbox, so "trust me, 47 things went in there"
 * is not good enough. This is the audit: exactly what was put where, when, and
 * a way to open any of it in Gmail if the answer is "not that one".
 *
 * Costs no Gmail calls — subjects and senders come from the local ledger, which
 * already holds every message the app has observed.
 */
export default function FolderDetail() {
  const { folderId = '' } = useParams();
  const navigate = useNavigate();

  const [folder, setFolder] = useState<MailFolder | null>(null);
  const [threads, setThreads] = useState<FolderThread[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const d = await getFolderThreads(folderId);
      setFolder(d.folder);
      setThreads(d.threads || []);
      setLoadError(null);
    } catch (err) {
      setLoadError(toApiError(err).message);
    } finally {
      setLoading(false);
    }
  }, [folderId]);

  useEffect(() => {
    void load();
  }, [load]);

  const filed = threads.filter((t) => t.status === 'filed');
  const failed = threads.filter((t) => t.status === 'failed');
  const pending = threads.filter((t) => t.status === 'pending');

  return (
    <Screen
      title={folder?.name || 'Folder'}
      action={
        <Button
          variant="secondary"
          size="sm"
          icon={<ChevronLeft className="h-4 w-4" />}
          onClick={() => navigate('/activity?tab=folders')}
        >
          Folders
        </Button>
      }
    >
      {loading ? (
        <ListGroup variant="plain-mobile">
          <SkeletonRows count={6} />
        </ListGroup>
      ) : loadError ? (
        <ListGroup variant="plain-mobile">
          <ErrorState
            title="Couldn’t open that folder"
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
      ) : threads.length === 0 ? (
        <ListGroup variant="plain-mobile">
          <EmptyState
            icon={<FolderTree className="h-6 w-6 text-accent" />}
            title="Nothing filed here yet"
            description="Conversations land here as they come in. Filing never removes anything from your inbox — the label sits alongside it."
          />
        </ListGroup>
      ) : (
        <>
          {failed.length > 0 && (
            <ListSection
              title={`Couldn’t be filed (${failed.length})`}
              footer="Gmail refused the label on these. They’re still in your inbox — nothing was lost."
            >
              <ListGroup variant="plain-mobile">
                {failed.map((t) => (
                  <ThreadRow key={t.thread_id} thread={t} />
                ))}
              </ListGroup>
            </ListSection>
          )}

          {pending.length > 0 && (
            <ListSection
              title={`Waiting on approval (${pending.length})`}
              footer="These will be filed once you approve the folder."
            >
              <ListGroup variant="plain-mobile">
                {pending.map((t) => (
                  <ThreadRow key={t.thread_id} thread={t} />
                ))}
              </ListGroup>
            </ListSection>
          )}

          {filed.length > 0 && (
            <ListSection
              title={`${filed.length} conversation${filed.length === 1 ? '' : 's'}`}
              footer="Tap any of them to open the conversation in Gmail."
            >
              <ListGroup variant="plain-mobile">
                {filed.map((t) => (
                  <ThreadRow key={t.thread_id} thread={t} />
                ))}
              </ListGroup>
            </ListSection>
          )}
        </>
      )}
    </Screen>
  );
}

function ThreadRow({ thread: t }: { thread: FolderThread }) {
  const who = t.counterparty_name || t.counterparty_email;
  return (
    <button
      onClick={() => window.open(t.deep_link, '_blank', 'noopener')}
      className="flex w-full items-center gap-3 px-4 py-3 text-left transition-colors hover:bg-muted/40 active:bg-muted/60"
    >
      {t.status === 'failed' ? (
        <span className="inline-flex h-9 w-9 flex-shrink-0 items-center justify-center rounded-xl bg-muted/60 text-destructive">
          <AlertTriangle className="h-4 w-4" />
        </span>
      ) : (
        <Avatar name={t.counterparty_name} email={t.counterparty_email} className="h-9 w-9 flex-shrink-0 text-sm" />
      )}
      <div className="min-w-0 flex-1">
        <div className="truncate text-[15px] font-medium text-foreground">{t.subject}</div>
        <div className="truncate text-[13px] text-muted-foreground">
          {who || 'Unknown sender'}
          {t.status === 'filed' && t.filed_ago && ` · filed ${t.filed_ago}`}
          {t.status === 'filed' && t.filed_count > 0 && ` · ${t.filed_count} messages`}
        </div>
        {t.status === 'failed' && t.error && (
          <div className="mt-1 line-clamp-2 text-[12px] text-destructive">{t.error}</div>
        )}
      </div>
      {t.status === 'pending' ? (
        <Badge tone="neutral">Waiting</Badge>
      ) : (
        <ExternalLink className="h-4 w-4 flex-shrink-0 text-muted-foreground/50" />
      )}
    </button>
  );
}
