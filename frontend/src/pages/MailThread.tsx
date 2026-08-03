import { useCallback, useEffect, useState } from 'react';
import { useNavigate, useParams, useSearchParams } from 'react-router-dom';
import { ChevronLeft, CornerUpLeft, ExternalLink, Info } from 'lucide-react';
import { Button, ErrorState } from '@clarittyai/app-ui';
import { Avatar, parseSender } from '@/components/Avatar';
import { Screen } from '@/components/ios/Screen';
import { ListGroup } from '@/components/ios/List';
import { SkeletonRows } from '@/components/ios/Skeleton';
import { Compose } from '@/components/Compose';
import { useToast } from '@/components/Toast';
import { getMailThread, toApiError, type MailThread as Thread } from '@/lib/api';

/**
 * One conversation, oldest first.
 *
 * Thread membership comes from the ledger rather than from Gmail — the broker
 * has no `get_thread` verb, and the ledger already knows every message it has
 * observed in a thread and which direction it went. The consequence is honest
 * rather than hidden: a conversation older than the ledger's horizon comes back
 * flagged `partial`, and this screen SAYS it is showing one message instead of
 * quietly presenting a fragment as the whole exchange. Replying to half a
 * conversation you believed was complete is a real way to embarrass someone.
 */
export default function MailThread() {
  const { threadId = '' } = useParams();
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const { show } = useToast();
  const [thread, setThread] = useState<Thread | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [replying, setReplying] = useState(false);

  const load = useCallback(async () => {
    try {
      setThread(await getMailThread(threadId, params.get('seed') || ''));
      setLoadError(null);
    } catch (err) {
      setLoadError(toApiError(err).message);
    } finally {
      setLoading(false);
    }
  }, [threadId, params]);

  useEffect(() => {
    void load();
  }, [load]);

  const last = thread?.messages[thread.messages.length - 1];
  const other = thread?.messages.find((m) => !m.outbound) ?? last;
  const replyTo = other ? parseSender(other.sender).email : '';

  return (
    <>
      {replying && thread && (
        <Compose
          to={replyTo}
          subject={thread.subject.toLowerCase().startsWith('re:') ? thread.subject : `Re: ${thread.subject}`}
          threadId={thread.thread_id}
          inReplyTo={last?.rfc822_msgid || ''}
          onClose={() => setReplying(false)}
          onSent={() => {
            setReplying(false);
            show({ tone: 'success', text: 'Sent — I’ll watch for their reply.' });
            void load();
          }}
        />
      )}

      <Screen
        title={thread?.subject || 'Conversation'}
        action={
          <Button variant="secondary" size="sm" icon={<ChevronLeft className="h-4 w-4" />} onClick={() => navigate('/mail')}>
            Mail
          </Button>
        }
      >
        {loading ? (
          <ListGroup variant="plain-mobile">
            <SkeletonRows count={4} />
          </ListGroup>
        ) : loadError || !thread ? (
          <ListGroup variant="plain-mobile">
            <ErrorState
              title="Couldn’t open this conversation"
              description={loadError || 'Nothing came back.'}
              action={
                <Button variant="secondary" size="sm" onClick={() => { setLoading(true); void load(); }}>
                  Try again
                </Button>
              }
            />
          </ListGroup>
        ) : (
          <>
            {thread.partial && (
              <div className="flex items-start gap-2 rounded-2xl bg-muted/60 p-3 text-[12px] leading-relaxed text-muted-foreground">
                <Info className="mt-0.5 h-3.5 w-3.5 flex-shrink-0" />
                Showing one message — the rest of this conversation is older than what
                the app has indexed. Open it in Gmail for the full exchange.
              </div>
            )}

            <div className="space-y-3">
              {thread.messages.map((m) => {
                const who = parseSender(m.sender);
                return (
                  <div
                    key={m.id}
                    className={
                      m.outbound
                        ? 'rounded-2xl border border-accent/30 bg-accent/5 p-3'
                        : 'rounded-2xl bg-card p-3 ring-1 ring-border/60'
                    }
                  >
                    <div className="mb-2 flex items-center gap-2">
                      <Avatar name={who.name} email={who.email} className="h-7 w-7 text-[11px]" />
                      <span className="truncate text-[13px] font-semibold text-foreground">
                        {m.outbound ? 'You' : who.name || m.sender}
                      </span>
                    </div>
                    <div className="whitespace-pre-wrap break-words text-[14px] leading-relaxed text-foreground/90">
                      {m.body}
                    </div>
                  </div>
                );
              })}
            </div>

            <div className="flex gap-2">
              <Button
                variant="primary"
                className="flex-1 justify-center"
                icon={<CornerUpLeft className="h-4 w-4" />}
                onClick={() => setReplying(true)}
              >
                Reply
              </Button>
              <Button
                variant="secondary"
                icon={<ExternalLink className="h-4 w-4" />}
                onClick={() => window.open(thread.deep_link, '_blank', 'noopener')}
              >
                Gmail
              </Button>
            </div>
          </>
        )}
      </Screen>
    </>
  );
}
