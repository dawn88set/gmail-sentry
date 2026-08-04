import { useCallback, useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Badge, Button, EmptyState, ErrorState, type BadgeTone } from '@clarittyai/app-ui';
import { Building2, AlertTriangle } from 'lucide-react';
import { Screen } from '@/components/ios/Screen';
import { ListGroup, ListRow, ListSection } from '@/components/ios/List';
import { SkeletonRows } from '@/components/ios/Skeleton';
import { getAccounts, toApiError, type Account, type AccountsResponse } from '@/lib/api';

/**
 * Accounts — the mailbox grouped the way the business is actually run.
 *
 * Every other screen is organised the way mail arrives: a message, a thread, a
 * person. None of those answers the question an owner actually has, which is
 * "where does Northwind stand?" — an answer spread across four people, six
 * threads and two months of silence.
 *
 * Ranked worst-first, never alphabetically: a list sorted by name makes the user
 * redo the triage the app exists to have already done.
 */

const TONE: Record<string, BadgeTone> = {
  customer: 'success',
  client: 'success',
  prospect: 'accent',
  vendor: 'neutral',
  internal: 'neutral',
  unknown: 'neutral',
};

/** The one line that says where an account stands, in plain words.
 *
 * Only clauses backed by a real count are emitted — an account with nothing
 * outstanding says so rather than padding the row with zeroes. */
function state(a: Account): string {
  const bits: string[] = [];
  if (a.you_owe > 0) bits.push(`you owe ${a.you_owe}`);
  if (a.chasing > 0) {
    bits.push(
      a.silent_days != null && a.silent_days > 0
        ? `silent ${a.silent_days}d`
        : `${a.chasing} going quiet`,
    );
  }
  if (!bits.length) {
    if (a.open_threads > 0) bits.push(`${a.open_threads} open`);
    else bits.push('all clear');
  }
  if (a.last_contact_at && a.silent_days != null && !a.chasing) {
    bits.push(a.silent_days === 0 ? 'today' : `last contact ${a.silent_days}d ago`);
  }
  return bits.join(' · ');
}

/** Two lines, because "you owe 1" tells an owner an account needs work but not
 *  whether it needs work NOW. The ask — "PO 4471 needs your signature" — is the
 *  thing that decides, so it leads and the counts qualify it. */
function Subtitle({ a }: { a: Account }) {
  if (!a.headline) return <>{state(a)}</>;
  return (
    <>
      <span className="block truncate text-foreground/80">{a.headline}</span>
      <span className="block truncate">{state(a)}</span>
    </>
  );
}

export default function Accounts() {
  const navigate = useNavigate();
  const [data, setData] = useState<AccountsResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      setData(await getAccounts());
      setError(null);
    } catch (err) {
      setError(toApiError(err).message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const accounts = data?.accounts ?? [];

  return (
    <Screen title="Accounts">
      {loading ? (
        <ListSection>
          <ListGroup>
            <SkeletonRows count={5} />
          </ListGroup>
        </ListSection>
      ) : error ? (
        <ErrorState
          title="Couldn’t load your accounts"
          description={error}
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
      ) : accounts.length === 0 ? (
        <EmptyState
          icon={<Building2 className="h-6 w-6" />}
          title="No accounts yet"
          description="Once your mail has been read, the companies you work with appear here — who owes whom, and who has gone quiet."
        />
      ) : (
        <>
          {/* The summary is the headline a business owner wants first: not how
              many companies exist, but how many are slipping. */}
          <ListSection>
            <div className="flex items-baseline gap-4 px-1 pb-1">
              <div>
                <div className="text-3xl font-semibold text-foreground">{data?.total ?? 0}</div>
                <div className="text-[13px] text-muted-foreground">accounts</div>
              </div>
              {(data?.needs_you ?? 0) > 0 && (
                <div>
                  <div className="text-3xl font-semibold text-foreground">{data?.needs_you}</div>
                  <div className="text-[13px] text-muted-foreground">need you</div>
                </div>
              )}
              {(data?.at_risk ?? 0) > 0 && (
                <div>
                  <div className="text-3xl font-semibold text-warning">{data?.at_risk}</div>
                  <div className="text-[13px] text-muted-foreground">going quiet</div>
                </div>
              )}
            </div>
          </ListSection>

          <ListSection>
            <ListGroup>
              {accounts.map((a) => (
                <ListRow
                  key={a.key}
                  onClick={() => navigate(`/accounts/${encodeURIComponent(a.key)}`)}
                  chevron
                  leading={
                    a.at_risk ? (
                      <AlertTriangle className="h-4 w-4 text-warning" aria-label="Going quiet" />
                    ) : (
                      <Building2 className="h-4 w-4 text-muted-foreground/60" />
                    )
                  }
                  title={a.name}
                  subtitle={<Subtitle a={a} />}
                  trailing={
                    <Badge tone={TONE[a.relationship] ?? 'neutral'}>{a.relationship_label}</Badge>
                  }
                />
              ))}
            </ListGroup>
          </ListSection>
        </>
      )}
    </Screen>
  );
}
