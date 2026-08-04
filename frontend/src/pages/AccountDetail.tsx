import { useCallback, useEffect, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { Badge, Button, EmptyState, ErrorState, type BadgeTone } from '@clarittyai/app-ui';
import { ArrowLeft, Building2, Mail as MailIcon } from 'lucide-react';
import { Screen } from '@/components/ios/Screen';
import { ListGroup, ListRow, ListSection } from '@/components/ios/List';
import { SkeletonRows } from '@/components/ios/Skeleton';
import { getAccount, toApiError, type AccountDetail as Detail } from '@/lib/api';

/**
 * One account: the people, the open threads, and where it stands.
 *
 * The threads link into the existing mail reader, which is why /mail keeps its
 * routes after losing its tab — reading a conversation is one tap from the
 * company it belongs to, which is a better path to it than a mailbox was.
 */

const TONE: Record<string, BadgeTone> = {
  customer: 'success',
  client: 'success',
  prospect: 'accent',
  vendor: 'neutral',
  internal: 'neutral',
  unknown: 'neutral',
};

function hours(h: number | null): string {
  if (h === null || h === undefined) return '—';
  if (h < 1) return 'under an hour';
  if (h < 48) return `about ${Math.round(h)}h`;
  return `about ${Math.round(h / 24)}d`;
}

export default function AccountDetail() {
  const { accountKey = '' } = useParams();
  const navigate = useNavigate();
  const [data, setData] = useState<Detail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [missing, setMissing] = useState(false);

  const load = useCallback(async () => {
    try {
      setData(await getAccount(accountKey));
      setError(null);
    } catch (err) {
      const e = toApiError(err);
      // A key can disappear when a CRM lookup lands and a domain-keyed account
      // becomes CRM-keyed. Say that, rather than showing an empty company.
      if (e.status === 404) setMissing(true);
      else setError(e.message);
    } finally {
      setLoading(false);
    }
  }, [accountKey]);

  useEffect(() => {
    void load();
  }, [load]);

  const back = (
    <button
      onClick={() => navigate('/accounts')}
      className="mb-3 inline-flex items-center gap-1.5 text-[13px] text-muted-foreground transition-colors hover:text-foreground"
    >
      <ArrowLeft className="h-4 w-4" />
      Accounts
    </button>
  );

  if (loading) {
    return (
      <Screen title="Account">
        {back}
        <ListSection>
          <ListGroup>
            <SkeletonRows count={4} />
          </ListGroup>
        </ListSection>
      </Screen>
    );
  }

  if (missing) {
    return (
      <Screen title="Account">
        {back}
        <EmptyState
          icon={<Building2 className="h-6 w-6" />}
          title="That account is no longer listed"
          description="It may have been merged into another once its company details were resolved."
        />
      </Screen>
    );
  }

  if (error || !data) {
    return (
      <Screen title="Account">
        {back}
        <ErrorState
          title="Couldn’t load this account"
          description={error ?? 'Not found'}
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
      </Screen>
    );
  }

  const open = data.threads.filter((t) => !['done', 'ignored'].includes(t.state));

  return (
    <Screen title={data.name}>
      {back}

      <ListSection>
        <div className="flex flex-wrap items-center gap-2 px-1 pb-2">
          <Badge tone={TONE[data.relationship] ?? 'neutral'}>{data.relationship_label}</Badge>
          {data.at_risk && <Badge tone="warning">Going quiet</Badge>}
          <span className="text-[13px] text-muted-foreground">
            {data.people_count} {data.people_count === 1 ? 'person' : 'people'}
            {data.silent_days != null && ` · last contact ${data.silent_days === 0 ? 'today' : `${data.silent_days}d ago`}`}
            {data.your_median_reply_h != null && ` · you reply in ${hours(data.your_median_reply_h)}`}
          </span>
        </div>
      </ListSection>

      {data.needs_you > 0 && (
        <ListSection title="Needs you">
          <ListGroup>
            <ListRow
              title={`${data.you_owe} waiting on your reply`}
              subtitle={
                data.chasing > 0
                  ? `${data.chasing} where they've gone quiet`
                  : 'Nothing has gone quiet here'
              }
            />
          </ListGroup>
        </ListSection>
      )}

      <ListSection title={open.length ? 'Open conversations' : 'Conversations'}>
        <ListGroup>
          {open.length === 0 ? (
            <ListRow title="Nothing open" subtitle="No conversation here is waiting on either side." />
          ) : (
            open.map((t) => (
              <ListRow
                key={t.id}
                onClick={() => navigate(`/mail/${encodeURIComponent(t.thread_id)}`)}
                chevron
                leading={<MailIcon className="h-4 w-4 text-muted-foreground/60" />}
                title={t.subject}
                subtitle={`${t.who}${t.ball === 'you' ? ' · waiting on you' : ' · waiting on them'}`}
              />
            ))
          )}
        </ListGroup>
      </ListSection>

      <ListSection title="People">
        <ListGroup>
          {data.people.map((p) => (
            <ListRow
              key={p.email}
              title={p.display_name || p.email}
              subtitle={`${p.email} · ${p.thread_count} ${p.thread_count === 1 ? 'thread' : 'threads'}`}
              trailing={
                <span className="text-[13px] text-muted-foreground">
                  you answer {p.your_reply_rate}%
                </span>
              }
            />
          ))}
        </ListGroup>
      </ListSection>
    </Screen>
  );
}
