import { useEffect, useRef, useState, useCallback } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { Loader2, Trash2, Inbox as InboxIcon } from 'lucide-react';
import { useToast } from '@/components/Toast';
import { Avatar, parseSender } from '@/components/Avatar';
import { Screen } from '@/components/ios/Screen';
import { ListGroup } from '@/components/ios/List';
import { IosButton } from '@/components/ios/IosButton';
import { SkeletonRows } from '@/components/ios/Skeleton';
import { ConnectButton } from '@/components/ConnectButtons';
import { requestConnectIntegration } from '@/lib/integrations';
import { getCategoryMessages, clearCategoryAll, toApiError, type CategoryMessage } from '@/lib/api';

const LABEL: Record<string, string> = { promotions: 'Promotions', social: 'Social', spam: 'Spam' };
const VALID = new Set(['promotions', 'social', 'spam']);

export default function CategoryList() {
  const { category = '' } = useParams();
  const navigate = useNavigate();
  const { show } = useToast();
  const cat = category as 'promotions' | 'social' | 'spam';

  const [messages, setMessages] = useState<CategoryMessage[]>([]);
  const [pageToken, setPageToken] = useState<string | null>('');
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [notConnected, setNotConnected] = useState(false);
  const [clearing, setClearing] = useState(false);
  const [progress, setProgress] = useState<{ done: number; total: number } | null>(null);
  const sentinel = useRef<HTMLDivElement | null>(null);
  const loadingRef = useRef(false);

  const loadPage = useCallback(
    async (token: string, initial: boolean) => {
      if (loadingRef.current) return;
      loadingRef.current = true;
      if (initial) setLoading(true);
      else setLoadingMore(true);
      try {
        const res = await getCategoryMessages(cat, token);
        setMessages((prev) => (initial ? res.messages : [...prev, ...res.messages]));
        setPageToken(res.next_page_token);
      } catch (err) {
        const e = toApiError(err);
        if (e.status === 409) setNotConnected(true);
        else show({ tone: 'error', text: `Couldn’t load: ${e.message}` });
        setPageToken(null);
      } finally {
        loadingRef.current = false;
        setLoading(false);
        setLoadingMore(false);
      }
    },
    [cat, show],
  );

  useEffect(() => {
    if (!VALID.has(cat)) {
      navigate('/');
      return;
    }
    setMessages([]);
    setPageToken('');
    setNotConnected(false);
    void loadPage('', true);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [cat]);

  // Infinite scroll: load the next page when the sentinel scrolls into view.
  // Paused while clearing — otherwise the observer keeps loading (ghost rows)
  // pages that are being trashed out from under it.
  useEffect(() => {
    const el = sentinel.current;
    if (!el || !pageToken || clearing) return;
    const io = new IntersectionObserver(
      (entries) => {
        if (entries[0].isIntersecting && pageToken && !loadingRef.current) {
          void loadPage(pageToken, false);
        }
      },
      { rootMargin: '400px' },
    );
    io.observe(el);
    return () => io.disconnect();
  }, [pageToken, loadPage, clearing]);

  const clearAll = async () => {
    setClearing(true);
    setProgress({ done: 0, total: 0 });
    // Freeze the total on the FIRST batch (done + still-remaining) so the "X / Y"
    // is stable — a fresh remaining count each pass would otherwise make Y wobble.
    let total = 0;
    try {
      const res = await clearCategoryAll(cat, 'trash', (done, remaining) => {
        if (total === 0) total = Math.max(done + remaining, done, 1);
        setProgress({ done: Math.min(done, total), total });
      });
      // Snap to 100% so the bar visibly completes before we leave.
      if (total > 0) setProgress({ done: total, total });
      show({
        tone: 'success',
        text: `Cleared ${res.cleared.toLocaleString()} ${cat} email${res.cleared === 1 ? '' : 's'} to Trash.`,
      });
      setClearing(false);
      setProgress(null);
      navigate('/');
    } catch (err) {
      const e = toApiError(err);
      show({ tone: 'error', text: e.status === 409 ? 'Connect Gmail, then try again.' : `Couldn’t clear: ${e.message}` });
      setClearing(false);
      setProgress(null);
    }
  };

  const title = LABEL[cat] || 'Cleanup';

  return (
    <Screen
      title={title}
      action={
        !notConnected && messages.length > 0 ? (
          <IosButton
            variant="filled"
            onClick={clearAll}
            disabled={clearing}
            icon={clearing ? <Loader2 className="h-4 w-4 animate-spin" /> : <Trash2 className="h-4 w-4" />}
          >
            {clearing ? 'Clearing…' : 'Clear all'}
          </IosButton>
        ) : undefined
      }
    >
      <p className="-mt-2 px-1 text-[13px] text-muted-foreground">
        Clear all moves every {cat} email to Trash (recoverable for 30 days) — the whole
        category, however large, in batches.
      </p>

      {/* Live batch progress: N / total moved to Trash. */}
      {clearing && progress && (
        <div className="rounded-2xl border border-border bg-card p-4">
          <div className="mb-2 flex items-center justify-between text-[13px]">
            <span className="font-medium text-foreground">Moving {cat} to Trash…</span>
            <span className="tabular-nums text-muted-foreground">
              {progress.total > 0
                ? `${progress.done.toLocaleString()} / ${progress.total.toLocaleString()}`
                : `${progress.done.toLocaleString()}…`}
            </span>
          </div>
          <div className="h-2 w-full overflow-hidden rounded-full bg-muted">
            <div
              className={`h-full rounded-full bg-accent transition-all duration-300 ${progress.total === 0 ? 'animate-pulse' : ''}`}
              style={{
                width:
                  progress.total > 0
                    ? `${Math.min(100, Math.round((progress.done / progress.total) * 100))}%`
                    : '20%',
              }}
            />
          </div>
        </div>
      )}

      {notConnected ? (
        <ListGroup variant="plain-mobile">
          <div className="flex flex-col items-center gap-3 p-8 text-center">
            <p className="text-[15px] font-semibold text-foreground">Reconnect Gmail</p>
            <p className="max-w-xs text-[13px] text-muted-foreground">
              Gmail shows connected, but the connection can’t be read right now (it may have expired
              or needs re-approving). Reconnect to refresh access.
            </p>
            <ConnectButton
              integrationId="gmail"
              onClick={() =>
                show({
                  tone: requestConnectIntegration('gmail') ? 'success' : 'error',
                  text: 'Opening Gmail reconnect… (or use Rules → Integrations)',
                })
              }
            />
          </div>
        </ListGroup>
      ) : loading ? (
        <ListGroup variant="plain-mobile">
          <SkeletonRows count={7} />
        </ListGroup>
      ) : messages.length === 0 ? (
        <ListGroup variant="plain-mobile">
          <div className="flex flex-col items-center gap-2 p-10 text-center">
            <div className="inline-flex h-12 w-12 items-center justify-center rounded-2xl bg-accent/15">
              <InboxIcon className="h-6 w-6 text-accent" />
            </div>
            <p className="text-[15px] font-semibold text-foreground">Nothing here</p>
            <p className="text-[13px] text-muted-foreground">No {title.toLowerCase()} to clear.</p>
          </div>
        </ListGroup>
      ) : (
        <>
          <ListGroup variant="plain-mobile">
            {messages.map((m) => {
              const who = parseSender(m.sender);
              return (
                <div key={m.id} className="flex items-start gap-3 px-4 py-3">
                  <Avatar name={who.name} email={who.email} className="mt-0.5 h-9 w-9 text-sm" />
                  <div className="min-w-0 flex-1">
                    <div className="truncate text-[15px] font-medium text-foreground">{m.subject}</div>
                    <div className="truncate text-[13px] text-muted-foreground">
                      <span className="text-foreground/70">{who.name || m.sender}</span>
                      {m.snippet ? ` — ${m.snippet}` : ''}
                    </div>
                  </div>
                </div>
              );
            })}
          </ListGroup>
          <div ref={sentinel} className="py-1">
            {loadingMore && (
              <ListGroup variant="plain-mobile">
                <SkeletonRows count={3} />
              </ListGroup>
            )}
            {!pageToken && (
              <p className="py-3 text-center text-[12px] text-muted-foreground">That’s everything loaded.</p>
            )}
          </div>
        </>
      )}
    </Screen>
  );
}
