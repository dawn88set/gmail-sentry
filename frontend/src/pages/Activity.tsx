import { useCallback, useEffect, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import {
  Activity as ActivityIcon,
  AlertTriangle,
  Check,
  FolderTree,
  Inbox,
  Mail,
  MessageSquare,
  PenLine,
  Send,
  Sparkles,
  Timer,
  UserCog,
  X,
} from 'lucide-react';
import { Button, EmptyState, ErrorState, Tabs } from '@clarittyai/app-ui';
import { Badge } from '@/components/ios/Badge';
import { useToast } from '@/components/Toast';
import { OrganizeBacklog } from '@/components/OrganizeBacklog';
import { Screen } from '@/components/ios/Screen';
import { ListGroup, ListRow, ListSection } from '@/components/ios/List';
import { SkeletonRows } from '@/components/ios/Skeleton';
import { Toggle } from '@/components/ios/Toggle';
import {
  approveFolder,
  getActivity,
  getFolders,
  getInsights,
  rejectFolder,
  setFilingEnabled,
  toApiError,
  type ActivityDay,
  type ActivityKind,
  type ActivitySummary,
  type Insights,
  type MailFolder,
} from '@/lib/api';

type Tab = 'activity' | 'folders' | 'insights';

const TABS: { value: Tab; label: string }[] = [
  { value: 'activity', label: 'Activity' },
  { value: 'folders', label: 'Folders' },
  { value: 'insights', label: 'Insights' },
];

/** An icon per event kind. Colour carries meaning and uses the app's own theme
 *  tokens: accent for work done, warning for something that needs the user,
 *  destructive only for a real failure. */
const ICON: Record<ActivityKind, { node: JSX.Element; tone: string }> = {
  thread_filed: { node: <FolderTree className="h-4 w-4" />, tone: 'text-accent' },
  filing_failed: { node: <AlertTriangle className="h-4 w-4" />, tone: 'text-destructive' },
  folder_proposed: { node: <Sparkles className="h-4 w-4" />, tone: 'text-warning' },
  folder_approved: { node: <Check className="h-4 w-4" />, tone: 'text-accent' },
  folder_rejected: { node: <X className="h-4 w-4" />, tone: 'text-muted-foreground' },
  mail_flagged: { node: <Mail className="h-4 w-4" />, tone: 'text-warning' },
  replies_drafted: { node: <PenLine className="h-4 w-4" />, tone: 'text-accent' },
  reply_sent: { node: <Send className="h-4 w-4" />, tone: 'text-accent' },
  nudge_sent: { node: <MessageSquare className="h-4 w-4" />, tone: 'text-accent' },
  went_quiet: { node: <Timer className="h-4 w-4" />, tone: 'text-warning' },
  loop_closed: { node: <Check className="h-4 w-4" />, tone: 'text-accent' },
  alert_auto_closed: { node: <Check className="h-4 w-4" />, tone: 'text-muted-foreground' },
  relationship_changed: { node: <UserCog className="h-4 w-4" />, tone: 'text-accent' },
  report_sent: { node: <Inbox className="h-4 w-4" />, tone: 'text-muted-foreground' },
};

function hours(h: number | null): string {
  if (h === null || h === undefined) return '';
  if (h < 1) return 'under an hour';
  if (h < 48) return `${Math.round(h)} hours`;
  return `${Math.round(h / 24)} days`;
}

/** What the row says when one side of the exchange has no measurable latency.
 *  A bare em-dash where a number should be reads as a broken component; saying
 *  we don't know yet is both truer and calmer. */
function responseLine(you: number | null, them: number | null): string {
  const yours = hours(you);
  const theirs = hours(them);
  if (!yours && !theirs) return 'Not enough back-and-forth yet to say';
  if (!yours) return `They answer in ${theirs} — you haven’t replied to enough of them yet`;
  if (!theirs) return `You answer in ${yours}`;
  return `You answer in ${yours} · they answer in ${theirs}`;
}

/**
 * What Gmail Sentry actually did.
 *
 * The app does most of its work while nobody is watching — it files a
 * conversation, retires an alert because the user answered from their phone,
 * notices a thread has gone quiet, reclassifies a prospect as a client. Until
 * this screen existed none of that was visible anywhere, and a folder showed a
 * name and a number with no way to check either. Software that works
 * unattended has to be able to say what it did, or it can't be trusted and
 * can't be corrected.
 *
 * Three tabs, because they answer three different questions: what happened,
 * where is my mail going, and what does all this say about how I work.
 */
export default function Activity() {
  const [searchParams, setSearchParams] = useSearchParams();
  const [tab, setTab] = useState<Tab>((searchParams.get('tab') as Tab) || 'activity');

  const pick = (value: string) => {
    const next = value as Tab;
    setTab(next);
    const params = new URLSearchParams(searchParams);
    if (next === 'activity') params.delete('tab');
    else params.set('tab', next);
    setSearchParams(params, { replace: true });
  };

  return (
    <Screen title="Activity">
      <Tabs variant="pill" items={TABS} value={tab} onValueChange={pick} />
      {tab === 'activity' && <Feed />}
      {tab === 'folders' && <Folders />}
      {tab === 'insights' && <InsightsTab />}
    </Screen>
  );
}

/* ── 1. The feed ─────────────────────────────────────────────────────────── */

function Feed() {
  const [days, setDays] = useState<ActivityDay[]>([]);
  const [summary, setSummary] = useState<ActivitySummary | null>(null);
  const [loading, setLoading] = useState(true);
  // Distinct from "loaded and empty": rendering "nothing has happened" after a
  // failed request would claim the app has been idle when we simply don't know.
  const [loadError, setLoadError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const d = await getActivity(14);
      setDays(d.days || []);
      setSummary(d.summary || null);
      setLoadError(null);
    } catch (err) {
      setLoadError(toApiError(err).message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  if (loading) {
    return (
      <ListGroup variant="plain-mobile">
        <SkeletonRows count={6} />
      </ListGroup>
    );
  }

  if (loadError) {
    return (
      <ListGroup variant="plain-mobile">
        <ErrorState
          title="Couldn’t load your activity"
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
    );
  }

  return (
    <>
      {summary && summary.total > 0 && <WeekStrip summary={summary} />}

      {days.length === 0 ? (
        <ListGroup variant="plain-mobile">
          <EmptyState
            icon={<ActivityIcon className="h-6 w-6 text-accent" />}
            title="Nothing to report yet"
            description="Once a scan flags something, files a conversation, or notices a thread going quiet, it shows up here. Routine scans that found nothing aren’t listed — only things that actually changed."
          />
        </ListGroup>
      ) : (
        days.map((d) => (
          <ListSection key={d.day} title={d.label}>
            <ListGroup variant="plain-mobile">
              {d.events.map((e) => {
                const icon = ICON[e.kind] ?? { node: <ActivityIcon className="h-4 w-4" />, tone: 'text-muted-foreground' };
                return (
                  <ListRow
                    key={e.id}
                    leading={
                      <span className={`inline-flex h-8 w-8 items-center justify-center rounded-xl bg-muted/60 ${icon.tone}`}>
                        {icon.node}
                      </span>
                    }
                    title={<div className="text-[15px] font-medium text-foreground">{e.title}</div>}
                    subtitle={e.detail || undefined}
                  />
                );
              })}
            </ListGroup>
          </ListSection>
        ))
      )}

      <p className="px-4 text-[12px] leading-snug text-muted-foreground">
        Only changes are listed — a scan that found nothing writes nothing here. The scan
        schedule itself is on Today.
      </p>
    </>
  );
}

function WeekStrip({ summary }: { summary: ActivitySummary }) {
  const cells = [
    { label: 'filed', value: summary.filed },
    { label: 'flagged', value: summary.flagged },
    { label: 'drafted', value: summary.drafted },
    { label: 'sent', value: summary.sent },
    { label: 'went quiet', value: summary.went_quiet },
  ].filter((c) => c.value > 0);

  if (cells.length === 0) return null;

  return (
    <ListSection title="Last 7 days">
      <div className="grid grid-cols-3 gap-2 sm:grid-cols-5">
        {cells.map((c) => (
          <div key={c.label} className="rounded-2xl bg-muted/60 px-3 py-2.5">
            <div className="text-[20px] font-semibold leading-none tabular-nums text-foreground">
              {c.value}
            </div>
            <div className="mt-1 text-[11px] leading-tight text-muted-foreground">{c.label}</div>
          </div>
        ))}
      </div>
    </ListSection>
  );
}

/* ── 2. Folders ──────────────────────────────────────────────────────────── */

/**
 * Everything about folders in one place.
 *
 * The approval queue used to live in Rules, beside notification settings — but
 * a proposed folder is a question about the user's mail, not a preference, and
 * it was easy to miss there. Rules keeps only the on/off switch.
 */
function Folders() {
  const navigate = useNavigate();
  const { show } = useToast();
  const [folders, setFolders] = useState<MailFolder[]>([]);
  const [enabled, setEnabled] = useState(false);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [editing, setEditing] = useState<Record<string, string>>({});

  const load = useCallback(async () => {
    try {
      const d = await getFolders();
      setFolders(d.folders || []);
      setEnabled(!!d.filing_enabled);
      setLoadError(null);
    } catch (err) {
      setLoadError(toApiError(err).message);
    } finally {
      setLoading(false);
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

  if (loading) {
    return (
      <ListGroup variant="plain-mobile">
        <SkeletonRows count={5} />
      </ListGroup>
    );
  }

  if (loadError) {
    return (
      <ListGroup variant="plain-mobile">
        <ErrorState
          title="Couldn’t load your folders"
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
    );
  }

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
          title={`Waiting for you (${proposed.length})`}
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

      {/* The backlog is the mail they installed this to organize, and the
          forward-only rule means nothing else will ever reach it. */}
      {enabled && <OrganizeBacklog onDone={load} />}

      {active.length > 0 ? (
        <ListSection title="Folders in use" footer="Tap a folder to see exactly what was filed there.">
          <ListGroup variant="plain-mobile">
            {active.map((f) => (
              <ListRow
                key={f.id}
                onClick={() => navigate(`/folders/${f.id}`)}
                chevron
                leading={
                  <span className="inline-flex h-9 w-9 items-center justify-center rounded-xl bg-muted/60 text-accent">
                    <FolderTree className="h-4 w-4" />
                  </span>
                }
                title={f.name}
                subtitle={
                  f.thread_count > 0
                    ? `${f.thread_count} conversation${f.thread_count === 1 ? '' : 's'}${
                        f.last_filed_ago ? ` · last ${f.last_filed_ago}` : ''
                      }`
                    : 'No conversations filed yet'
                }
              />
            ))}
          </ListGroup>
        </ListSection>
      ) : (
        proposed.length === 0 && (
          <ListGroup variant="plain-mobile">
            <EmptyState
              icon={<FolderTree className="h-6 w-6 text-accent" />}
              title={enabled ? 'No folders yet' : 'Filing is off'}
              description={
                enabled
                  ? 'As conversations come in, folders will be suggested here by who the thread is with. You approve each one before anything is labelled.'
                  : 'Turn on smart filing and conversations will be sorted by who they’re with — both your replies and theirs.'
              }
            />
          </ListGroup>
        )
      )}
    </>
  );
}

/* ── 3. Insights ─────────────────────────────────────────────────────────── */

function InsightsTab() {
  const [data, setData] = useState<Insights | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      setData(await getInsights());
      setLoadError(null);
    } catch (err) {
      setLoadError(toApiError(err).message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  if (loading) {
    return (
      <ListGroup variant="plain-mobile">
        <SkeletonRows count={5} />
      </ListGroup>
    );
  }

  if (loadError || !data) {
    return (
      <ListGroup variant="plain-mobile">
        <ErrorState
          title="Couldn’t work that out"
          description={loadError || 'No data came back.'}
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
    );
  }

  // Defaults so a partial payload costs this panel, not the whole screen.
  const { coverage, response, attention, at_risk, handled } = data ?? {};

  if (coverage.messages === 0) {
    return (
      <ListGroup variant="plain-mobile">
        <EmptyState
          icon={<ActivityIcon className="h-6 w-6 text-accent" />}
          title="Not enough mail yet"
          description="These are worked out from your real correspondence, so they appear once a few scans have run. Nothing here is estimated or modelled — if it can’t be counted, it isn’t shown."
        />
      </ListGroup>
    );
  }

  return (
    <>
      <ListSection
        title="How you respond"
        footer={response.caveat}
      >
        {response.groups.length === 0 ? (
          <ListGroup variant="plain-mobile">
            <div className="px-4 py-5 text-[13px] text-muted-foreground">
              Not enough two-way conversations yet to say anything true about your reply times.
            </div>
          </ListGroup>
        ) : (
          <ListGroup variant="plain-mobile">
            {response.groups.map((g) => (
              <ListRow
                key={g.relationship}
                title={
                  <div className="flex items-baseline gap-2">
                    <span className="text-[15px] font-medium text-foreground">{g.label}</span>
                    <span className="text-[12px] text-muted-foreground">
                      {g.people} {g.people === 1 ? 'person' : 'people'}
                    </span>
                    {g.thin && <Badge tone="neutral">few samples</Badge>}
                  </div>
                }
                subtitle={responseLine(g.you_answer_in_h, g.they_answer_in_h)}
              />
            ))}
          </ListGroup>
        )}
      </ListSection>

      {attention.people.length > 0 && (
        <ListSection
          title="Where your attention goes"
          footer="Ranked by whether you actually reply to them, not by how much they send."
        >
          <ListGroup variant="plain-mobile">
            {attention.people.map((p) => (
              <ListRow
                key={p.email}
                title={p.display_name || p.email}
                subtitle={
                  <span>
                    {p.relationship_label} · {p.thread_count} conversation
                    {p.thread_count === 1 ? '' : 's'} · you reply {p.your_reply_rate}%
                  </span>
                }
              />
            ))}
          </ListGroup>
        </ListSection>
      )}

      {at_risk.threads.length > 0 && (
        <ListSection
          title="Going quiet"
          footer="Silence sends no email, so these would otherwise be invisible until it’s too late."
        >
          <ListGroup variant="plain-mobile">
            {at_risk.threads.map((t) => (
              <ListRow
                key={t.id}
                leading={
                  <span className="inline-flex h-8 w-8 items-center justify-center rounded-xl bg-muted/60 text-warning">
                    <Timer className="h-4 w-4" />
                  </span>
                }
                title={t.who}
                subtitle={
                  <span>
                    {t.subject || '(no subject)'}
                    {t.silent_days > 0 && ` · silent ${t.silent_days} day${t.silent_days === 1 ? '' : 's'}`}
                  </span>
                }
              />
            ))}
          </ListGroup>
        </ListSection>
      )}

      <ListSection
        title="What Sentry handled"
        footer={`Counted over the last ${handled.days} days, from ${coverage.threads} conversation${
          coverage.threads === 1 ? '' : 's'
        } across ${coverage.days} day${coverage.days === 1 ? '' : 's'} of mail.`}
      >
        <ListGroup variant="plain-mobile">
          <ListRow title="Conversations filed" trailing={<Num n={handled.filed} />} />
          <ListRow title="Emails flagged for you" trailing={<Num n={handled.flagged} />} />
          <ListRow title="Replies drafted in your voice" trailing={<Num n={handled.drafted} />} />
          <ListRow title="Messages you sent from here" trailing={<Num n={handled.sent} />} />
          <ListRow title="Threads that went quiet" trailing={<Num n={handled.went_quiet} />} />
          <ListRow
            title="Folders in use"
            subtitle={handled.folders_pending > 0 ? `${handled.folders_pending} waiting for your OK` : undefined}
            trailing={<Num n={handled.folders_active} />}
          />
        </ListGroup>
      </ListSection>
    </>
  );
}

function Num({ n }: { n: number }) {
  return <span className="text-[17px] font-semibold tabular-nums text-foreground">{n}</span>;
}
