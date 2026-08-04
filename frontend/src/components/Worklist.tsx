import { useNavigate } from 'react-router-dom';
import { Check, CheckCircle2, Clock, MessageSquare, Send } from 'lucide-react';
import { Button, EmptyState, ErrorState } from '@clarittyai/app-ui';
import { Avatar, parseSender } from '@/components/Avatar';
import { ListGroup, ListSection } from '@/components/ios/List';
import { SkeletonRows } from '@/components/ios/Skeleton';
import { type WorkItem, type Worklist as WorklistData } from '@/lib/api';

const VERB: Record<WorkItem['kind'], { label: string; icon: JSX.Element }> = {
  reply: { label: 'Reply', icon: <Send className="h-3 w-3" /> },
  owe: { label: 'You owe', icon: <Clock className="h-3 w-3" /> },
  chase: { label: 'Chase', icon: <MessageSquare className="h-3 w-3" /> },
};

/**
 * What your email needs from you, in order.
 *
 * Today used to be four inventories — alerts here, open loops there, junk
 * counts, a scan log — and the user assembled the plan themselves. This is the
 * plan: one ranked list where every row is a thing to do, carrying the ask and
 * the deadline the app already parsed and never showed.
 *
 * Two deliberate choices:
 *
 * The headline is the ASK, not the subject. "Send the revised pricing before
 * Friday" is a task; "Re: Q3" is a filing label. The subject stays as the
 * second line so the row is still recognisable as an email.
 *
 * It counts DOWN, and says what's been cleared. An inbox is endless by
 * construction; a list you can finish is a different psychological object, and
 * "3 done today" is the only thing here that tells the user they're winning.
 */
export function Worklist({
  data,
  loading,
  loadError,
  onRetry,
  onOpenAlert,
}: {
  data: WorklistData | null;
  loading: boolean;
  loadError: string | null;
  onRetry: () => void;
  onOpenAlert?: (alertId: string) => void;
}) {
  const navigate = useNavigate();

  if (loading) {
    return (
      <ListGroup variant="plain-mobile">
        <SkeletonRows count={4} />
      </ListGroup>
    );
  }

  if (loadError || !data) {
    return (
      <ListGroup variant="plain-mobile">
        <ErrorState
          title="Couldn’t load your list"
          description={loadError || 'No data came back.'}
          action={
            <Button variant="secondary" size="sm" onClick={onRetry}>
              Try again
            </Button>
          }
        />
      </ListGroup>
    );
  }

  const { items, total, done_today, ready_to_send, overdue } = data;

  if (items.length === 0) {
    return (
      <ListSection title="Your list">
        <ListGroup variant="plain-mobile">
          <EmptyState
            icon={<CheckCircle2 className="h-6 w-6 text-success" />}
            title={done_today > 0 ? "That's everything" : 'Nothing needs you'}
            description={
              done_today > 0
                ? `You cleared ${done_today} thing${done_today === 1 ? '' : 's'} today. Nobody is waiting on you, and nothing has gone quiet.`
                : 'Nobody is waiting on a reply, and no thread has gone quiet.'
            }
          />
        </ListGroup>
      </ListSection>
    );
  }

  // One honest line about the shape of the work, not a wall of counters.
  const shape = [
    overdue > 0 ? `${overdue} overdue` : '',
    ready_to_send > 0 ? `${ready_to_send} ready to send` : '',
    done_today > 0 ? `${done_today} done today` : '',
  ].filter(Boolean).join(' · ');

  return (
    <ListSection
      title={`${total} thing${total === 1 ? '' : 's'} need you`}
      footer={
        total > items.length
          ? `Showing the ${items.length} that matter most — see all in Follow-ups.`
          : undefined
      }
    >
      {shape && <p className="-mt-1 px-4 text-[12px] text-muted-foreground">{shape}</p>}
      <ListGroup variant="plain-mobile">
        {items.map((i) => (
          <WorkRow
            key={i.id}
            item={i}
            onOpen={() => {
              // Act without leaving the list. Navigating away to find the same
              // row again is the opposite of a worklist.
              if (i.alert_id && onOpenAlert) onOpenAlert(i.alert_id);
              else navigate(i.alert_id ? '/attention' : '/followups');
            }}
          />
        ))}
      </ListGroup>
    </ListSection>
  );
}

function WorkRow({ item, onOpen }: { item: WorkItem; onOpen: () => void }) {
  const who = parseSender(item.email || item.who);
  const verb = VERB[item.kind];
  return (
    <button
      onClick={onOpen}
      className="flex w-full items-start gap-3 px-4 py-3 text-left transition-colors hover:bg-muted/40 active:bg-muted/60"
    >
      <Avatar name={item.who} email={who.email} className="mt-0.5 h-8 w-8 flex-shrink-0 text-[12px]" />
      <div className="min-w-0 flex-1">
        {/* The ask, in the user's task language — bold when it's late, because
            weight ranks faster than a badge. */}
        <div
          className={
            item.overdue
              ? 'truncate text-[15px] font-bold text-foreground'
              : 'truncate text-[15px] font-medium text-foreground'
          }
        >
          {item.headline}
        </div>
        <div className="mt-0.5 flex flex-wrap items-center gap-x-1.5 text-[12px] text-muted-foreground">
          <span className="inline-flex items-center gap-1 font-medium text-foreground/70">
            {verb.icon}
            {verb.label}
          </span>
          <span>·</span>
          {/* Person AND company. A name alone is unplaceable once you have more
              than a handful of contacts, and the company is what connects this
              row to the account it belongs to. */}
          <span className="truncate">
            {item.who}
            {item.company && item.company !== item.who && (
              <span className="text-foreground/70"> · {item.company}</span>
            )}
          </span>
          {item.due_label && (
            <>
              <span>·</span>
              <span className={item.overdue ? 'font-semibold text-destructive' : 'text-foreground/80'}>
                {item.due_label}
              </span>
            </>
          )}
          {!item.due_label && item.age_label && (
            <>
              <span>·</span>
              <span>{item.age_label}</span>
            </>
          )}
        </div>
        {/* Only shown when the subject isn't already the headline. */}
        {item.subject && item.subject !== item.headline && (
          <div className="mt-0.5 truncate text-[12px] text-muted-foreground/70">{item.subject}</div>
        )}
      </div>
      {item.reply_ready && (
        <span className="mt-1 inline-flex flex-shrink-0 items-center gap-1 text-[11px] font-medium text-accent">
          <Check className="h-3 w-3" />
          Draft
        </span>
      )}
    </button>
  );
}

export default Worklist;
