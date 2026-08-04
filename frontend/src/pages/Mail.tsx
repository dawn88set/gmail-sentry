import { useCallback, useEffect, useRef, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { Inbox, PenSquare } from 'lucide-react';
import { Button, EmptyState, ErrorState, Tabs } from '@clarittyai/app-ui';
import { useToast } from '@/components/Toast';
import { Avatar, parseSender } from '@/components/Avatar';
import { Screen } from '@/components/ios/Screen';
import { ListGroup } from '@/components/ios/List';
import { SkeletonRows } from '@/components/ios/Skeleton';
import { ConnectButton } from '@/components/ConnectButtons';
import { requestConnectIntegration } from '@/lib/integrations';
import { useIntegrationStatus } from '@/hooks/useIntegrationStatus';
import { Compose } from '@/components/Compose';
import { getMail, toApiError, type MailBox, type MailRow } from '@/lib/api';

const BOXES: { value: MailBox; label: string }[] = [
  { value: 'inbox', label: 'Inbox' },
  { value: 'unread', label: 'Unread' },
  { value: 'sent', label: 'Sent' },
  { value: 'archive', label: 'Archive' },
];

/**
 * The mailbox.
 *
 * The rest of the app is a watchdog: it decides what matters and hands over a
 * short list. This is the other half — when a row isn't enough and you need to
 * read the whole thread, or write to someone the app never flagged.
 *
 * It is deliberately NOT where the app points you first. Today is still the
 * plan; this is the drawer you open when the plan isn't the whole story.
 *
 * Every row costs one broker call for its metadata (the list endpoint returns
 * bare {id, threadId} stubs), so pages are small and scrolling is explicit
 * rather than infinite-by-default.
 */
export default function Mail() {
  const navigate = useNavigate();
  const { show } = useToast();
  const [params, setParams] = useSearchParams();
  const box = (params.get('box') as MailBox) || 'inbox';

  const [rows, setRows] = useState<MailRow[]>([]);
  const [pageToken, setPageToken] = useState<string>('');
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [notConnected, setNotConnected] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [composing, setComposing] = useState(false);
  const busy = useRef(false);

  const load = useCallback(
    async (token: string, initial: boolean) => {
      if (busy.current) return;
      busy.current = true;
      if (initial) setLoading(true);
      else setLoadingMore(true);
      try {
        const d = await getMail(box, token);
        setRows((prev) => (initial ? d.messages : [...prev, ...d.messages]));
        setPageToken(d.next_page_token);
        setNotConnected(false);
        setLoadError(null);
      } catch (err) {
        const e = toApiError(err);
        if (e.status === 409) setNotConnected(true);
        else setLoadError(e.message);
        setPageToken('');
      } finally {
        busy.current = false;
        setLoading(false);
        setLoadingMore(false);
      }
    },
    [box],
  );

  useEffect(() => {
    setRows([]);
    void load('', true);
  }, [load]);

  // Connecting happens in the host, so nothing here navigates when OAuth
  // finishes — without this the mailbox keeps showing its connect prompt until
  // the user reloads by hand.
  useIntegrationStatus({
    onConnect: (id) => {
      if (id === 'gmail') void load('', true);
    },
  });

  const pick = (v: string) => {
    const next = new URLSearchParams(params);
    if (v === 'inbox') next.delete('box');
    else next.set('box', v);
    setParams(next, { replace: true });
  };

  return (
    <>
      {composing && (
        <Compose
          onClose={() => setComposing(false)}
          onSent={() => {
            setComposing(false);
            show({ tone: 'success', text: 'Sent.' });
            void load('', true);
          }}
        />
      )}

      <Screen
        title="Mail"
        action={
          <Button variant="primary" size="sm" icon={<PenSquare className="h-4 w-4" />} onClick={() => setComposing(true)}>
            Write
          </Button>
        }
      >
        <Tabs variant="pill" items={BOXES} value={box} onValueChange={pick} />

        {notConnected ? (
          <ListGroup variant="plain-mobile">
            <div className="flex flex-col items-center gap-3 p-8 text-center">
              <p className="text-[15px] font-semibold text-foreground">Connect Gmail</p>
              <p className="max-w-xs text-[13px] text-muted-foreground">
                Your mail lives in Gmail — connect it and this becomes your mailbox.
              </p>
              <ConnectButton
                integrationId="gmail"
                onClick={() =>
                  show({
                    tone: requestConnectIntegration('gmail') ? 'success' : 'error',
                    text: 'Opening Gmail connect…',
                  })
                }
              />
            </div>
          </ListGroup>
        ) : loading ? (
          <ListGroup variant="plain-mobile">
            <SkeletonRows count={8} />
          </ListGroup>
        ) : loadError ? (
          <ListGroup variant="plain-mobile">
            <ErrorState
              title="Couldn’t load your mail"
              description={loadError}
              action={
                <Button variant="secondary" size="sm" onClick={() => void load('', true)}>
                  Try again
                </Button>
              }
            />
          </ListGroup>
        ) : rows.length === 0 ? (
          <ListGroup variant="plain-mobile">
            <EmptyState
              icon={<Inbox className="h-6 w-6 text-accent" />}
              title="Nothing here"
              description={box === 'unread' ? 'No unread mail.' : 'This mailbox is empty.'}
            />
          </ListGroup>
        ) : (
          <>
            <ListGroup variant="plain-mobile">
              {rows.map((m) => (
                <MailRowItem
                  key={m.id}
                  row={m}
                  onClick={() => navigate(`/mail/${m.thread_id || m.id}?seed=${m.id}`)}
                />
              ))}
            </ListGroup>
            {pageToken && (
              <Button
                variant="secondary"
                className="w-full justify-center"
                disabled={loadingMore}
                onClick={() => void load(pageToken, false)}
              >
                {loadingMore ? 'Loading…' : 'Load more'}
              </Button>
            )}
          </>
        )}
      </Screen>
    </>
  );
}

function MailRowItem({ row, onClick }: { row: MailRow; onClick: () => void }) {
  const who = parseSender(row.sender);
  return (
    <button
      onClick={onClick}
      className="flex w-full items-start gap-3 px-4 py-3 text-left transition-colors hover:bg-muted/40 active:bg-muted/60"
    >
      <Avatar name={who.name} email={who.email} className="mt-0.5 h-8 w-8 flex-shrink-0 text-[12px]" />
      <div className="min-w-0 flex-1">
        {/* Unread reads as weight, the way every mail client does it — it ranks
            faster than a dot and needs no legend. */}
        <div className={row.unread ? 'truncate text-[14px] font-bold text-foreground' : 'truncate text-[14px] font-medium text-foreground'}>
          {who.name || row.sender}
        </div>
        <div className={row.unread ? 'truncate text-[13px] font-semibold text-foreground' : 'truncate text-[13px] text-foreground/80'}>
          {row.subject}
        </div>
        <div className="truncate text-[12px] text-muted-foreground">{row.snippet}</div>
      </div>
    </button>
  );
}
