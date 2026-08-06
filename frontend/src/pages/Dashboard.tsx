import { useEffect, useState, useCallback, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { AnimatePresence } from 'framer-motion';
import { ShieldCheck, RefreshCw, Megaphone, Users, Ban, Bell } from 'lucide-react';
import { useToast } from '@/components/Toast';
import { AnimatedNumber } from '@/components/AnimatedNumber';
import { SmartOnboarding } from '@/components/SmartOnboarding';
import { AlertSheet } from '@/components/AlertSheet';
import { ConnectButton } from '@/components/ConnectButtons';
import { Worklist } from '@/components/Worklist';
import { requestConnectIntegration } from '@/lib/integrations';
import { useIntegrationStatus } from '@/hooks/useIntegrationStatus';
import { Screen } from '@/components/ios/Screen';
import { ListSection, ListGroup, ListRow } from '@/components/ios/List';
import { IosButton } from '@/components/ios/IosButton';
import {
  getAlerts,
  getCleanup,
  getConfig,
  getRecentScans,
  getOnboardingStatus,
  getOnboardingProgress,
  getAccounts,
  getCommitments,
  getWorklist,
  runBackfill,
  runScan,
  toApiError,
  type Alert,
  type Worklist as WorklistData,
  type CleanupCounts,
  type SentryConfig,
  type ScanRunItem,
  type OnboardingProgress,
  type Commitment,
} from '@/lib/api';
import { cn } from '@/lib/utils';

const CATEGORIES = [
  { key: 'promotions' as const, label: 'Promotions', field: 'promotions' as const, Icon: Megaphone },
  { key: 'social' as const, label: 'Social', field: 'social' as const, Icon: Users },
  { key: 'spam' as const, label: 'Spam', field: 'spam' as const, Icon: Ban },
];

function LiveDot() {
  return (
    <span className="relative flex h-2 w-2">
      <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-accent opacity-75" />
      <span className="relative inline-flex h-2 w-2 rounded-full bg-accent" />
    </span>
  );
}

export default function Dashboard() {
  const { show } = useToast();
  const navigate = useNavigate();
  const [alerts, setAlerts] = useState<Alert[]>([]);
  const [cleanup, setCleanup] = useState<CleanupCounts | null>(null);
  const [config, setConfig] = useState<SentryConfig | null>(null);
  const [recentScans, setRecentScans] = useState<ScanRunItem[]>([]);
  // The hero number and the list below it come from ONE fetch. They used to be
  // different counts on the same screen ("2 need attention" above "12 things
  // need you"), which is exactly the inventory problem this replaced.
  const [work, setWork] = useState<WorklistData | null>(null);
  const [workLoading, setWorkLoading] = useState(true);
  const [workError, setWorkError] = useState<string | null>(null);
  const [scanning, setScanning] = useState(false);
  // First-run reading state. `null` = not started/needed.
  const [firstRun, setFirstRun] = useState<OnboardingProgress | null>(null);
  const [reading, setReading] = useState(false);
  const [promises, setPromises] = useState<Commitment[]>([]);
  // A ref, not the state: the connect edge and a manual tap can arrive in the
  // same tick, and `reading` wouldn't have re-rendered yet to stop the second.
  const readingRef = useRef(false);
  const [selectedAlert, setSelectedAlert] = useState<Alert | null>(null);
  // Start closed and let the SERVER decide. Opening it optimistically means a
  // fresh browser (or an unreachable API — the status call below is a soft
  // catch) shows the setup wizard over the dashboard, which is both a bad first
  // frame and why the rendered design audit was scoring the modal, not the page.
  const [onboarding, setOnboarding] = useState(false);
  const [obRole, setObRole] = useState('');
  const [obIntent, setObIntent] = useState('');

  const finishOnboarding = (applied: boolean) => {
    try {
      localStorage.setItem('gs_onboarded', '1');
    } catch {
      /* ignore */
    }
    setOnboarding(false);
    if (applied) void refresh();
  };

  const refresh = useCallback(async () => {
    try {
      const [a, c] = await Promise.all([getAlerts('active'), getCleanup()]);
      setAlerts(a);
      setCleanup(c);
    } catch (err) {
      show({ tone: 'error', text: `Couldn’t load inbox: ${toApiError(err).message}` });
    }
    // Where alerts go — used to nudge setup when no channel is configured yet.
    getConfig()
      .then(setConfig)
      .catch(() => undefined);
    // Recent scan runs — so the actual cadence (platform-owned) is visible.
    getRecentScans()
      .then((r) => setRecentScans(r.runs || []))
      .catch(() => undefined);
    // Thread-level open loops — the other half of "what needs you". Soft-fails:
    // a missing loop count shouldn't blank the whole dashboard.
    getWorklist(8)
      .then((w) => { setWork(w); setWorkError(null); })
      .catch((err) => setWorkError(toApiError(err).message))
      .finally(() => setWorkLoading(false));
    // What you said you'd do. Soft-fails: a missing list must never blank the
    // dashboard, and on a mailbox that hasn't been read yet it's simply empty.
    getCommitments(5)
      .then((c) => setPromises(c.commitments || []))
      .catch(() => undefined);
  }, [show]);

  /**
   * Read the mailbox now rather than over the next two hours.
   *
   * A scan indexes 20 messages and the ledger walks 48 hours per sweep, so a
   * freshly-connected mailbox stays empty for hours — which is exactly what
   * "I connected Gmail and nothing showed" was. The server sweeps under a time
   * budget and returns progress; we call it until it reports done, so each
   * request stays short and the user watches it fill.
   */
  const startFirstRun = useCallback(async () => {
    if (readingRef.current) return; // never two backfills at once
    readingRef.current = true;
    setReading(true);
    try {
      let p = await runBackfill();
      setFirstRun(p);
      // Runs until the list is READABLE, not merely indexed — `complete` also
      // requires every open loop to have a name and a subject. Bounded so a
      // server that never reports complete can't spin here forever.
      for (let i = 0; i < 60 && !p.complete; i++) {
        // Gmail's broker throttles per app, and a first read is the burstiest
        // thing this app does — so being asked to wait is ordinary, not a
        // failure. Waiting keeps the walk going; hammering through the pause is
        // what earns a longer one.
        if (p.paused_seconds) {
          await new Promise((r) => setTimeout(r, Math.min(p.paused_seconds!, 60) * 1000));
        }
        p = await runBackfill();
        setFirstRun(p);
      }
      await refresh();
      if (p.complete) {
        // Report the OUTCOME, not the mechanics. "Read 1,240 messages" is our
        // work; "12 accounts, 3 need you" is theirs — and it's the thing that
        // tells them the wait bought something.
        const acc = await getAccounts().catch(() => null);
        show({
          tone: 'success',
          text: acc
            ? `${acc.total} account${acc.total === 1 ? '' : 's'} · ${acc.needs_you} need you` +
              (acc.at_risk ? ` · ${acc.at_risk} going quiet` : '')
            : `Read ${p.threads.toLocaleString()} conversations.`,
        });
      }
    } catch (err) {
      const e = toApiError(err);
      show({
        tone: 'error',
        text:
          e.status === 409
            ? 'Connect Gmail first — that’s where your accounts come from.'
            : e.status === 429
              ? 'Gmail is rate-limiting us — the read will pick up again shortly.'
              : `Couldn’t read your mail: ${e.message}`,
      });
    } finally {
      readingRef.current = false;
      setReading(false);
    }
  }, [refresh, show]);

  // Connection status that notices OAuth finishing WITHOUT a reload, and kicks
  // off the first read on the rising edge. Before this, Today fetched status
  // once on mount and kept offering "Sign in with Google" until the user
  // refreshed the page by hand.
  const { integrations, appId, isConnected } = useIntegrationStatus({
    onConnect: (id) => {
      if (id !== 'gmail') return;
      void getOnboardingProgress()
        .then((p) => {
          setFirstRun(p);
          if (!p.backfill_done) void startFirstRun();
        })
        .catch(() => undefined);
    },
  });

  useEffect(() => {
    void refresh();
    // Where the first read got to, so a reload mid-backfill resumes the panel
    // instead of showing an empty dashboard with no explanation.
    getOnboardingProgress()
      .then(setFirstRun)
      .catch(() => undefined);
    getOnboardingStatus()
      .then((s) => {
        setObRole(s.role || '');
        setObIntent(s.intent || '');
        if (s.onboarded) {
          try {
            localStorage.setItem('gs_onboarded', '1');
          } catch {
            /* ignore */
          }
          return;
        }
        // Not onboarded server-side. localStorage is only a SUPPRESSOR — if the
        // user already dismissed the wizard on this device, don't re-open it.
        let dismissed = false;
        try {
          dismissed = localStorage.getItem('gs_onboarded') === '1';
        } catch {
          /* ignore */
        }
        if (!dismissed) setOnboarding(true);
      })
      .catch(() => undefined);
  }, [refresh]);

  const handleScan = async () => {
    setScanning(true);
    try {
      const s = await runScan();
      // `scanned` counts mail newly judged this run — settled mail is never
      // re-examined — so 0 means "up to date", not "the scan did nothing".
      // Reporting "Scanned 0 emails — flagged 0" would read as a failure.
      show({
        tone: 'success',
        text:
          s.scanned === 0
            ? 'Up to date — no new mail to review.'
            : `Reviewed ${s.scanned} new email${s.scanned === 1 ? '' : 's'} — flagged ${s.flagged}, filed ${s.labeled}, notified ${s.notified}.`,
      });
      await refresh();
    } catch (err) {
      const e = toApiError(err);
      show({
        tone: 'error',
        text: e.status === 409 ? 'Connect Gmail to start scanning.' : `Scan failed: ${e.message}`,
      });
    } finally {
      setScanning(false);
    }
  };

  const urgent = alerts.filter((a) => a.tier === 'urgent').length;
  const needsReply = alerts.filter((a) => a.tier === 'needs_reply').length;
  // Everything that needs the user, not just fresh mail — the same number the
  // list below shows. A hero that says 2 above a list of 12 teaches people not
  // to trust either.
  const attention = work ? work.total : urgent + needsReply;
  const calm = attention === 0;
  // Gmail is the only integration this app cannot run without — everything else
  // is a choice of where to be pinged. Fall back to a literal so the prompt
  // still appears if the status endpoint hasn't answered yet.
  const GMAIL = integrations.find((i) => i.id === 'gmail') ?? { id: 'gmail', name: 'Gmail', connected: false };
  const gmailMissing = !isConnected('gmail');
  // Connected, but the mailbox hasn't been read through yet. Without saying so,
  // a new user sees "All clear" over an empty list and concludes it's broken —
  // which is precisely what happened.
  const showFirstRun = !gmailMissing && firstRun !== null && !(firstRun.complete ?? firstRun.backfill_done);
  // No alert destination set on ANY channel → the app can flag mail but can't
  // reach the user. Surface a one-tap prompt to the Slack/notification setup.
  const hasAlertChannel = !!(
    config &&
    (config.slack_channel ||
      config.telegram_chat_id ||
      config.discord_channel_id ||
      config.whatsapp_to)
  );
  const showAlertSetup = config !== null && !hasAlertChannel;

  return (
    <>
      <AnimatePresence>
        {onboarding && (
          <SmartOnboarding onDone={finishOnboarding} initialRole={obRole} initialIntent={obIntent} />
        )}
      </AnimatePresence>

      <Screen
        title="Today"
        action={
          <IosButton
            variant="tinted"
            onClick={handleScan}
            disabled={scanning}
            icon={<RefreshCw className={cn('h-4 w-4', scanning && 'animate-spin')} />}
          >
            {scanning ? 'Scanning' : 'Scan'}
          </IosButton>
        }
      >
        {/* Status */}
        <ListGroup variant="plain-mobile">
          <div className="p-5">
            <div className="mb-2 flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
              <LiveDot /> Watching
            </div>
            {cleanup?.last_scan_error === 'gmail_not_connected' && (
              <div className="mb-3 rounded-lg bg-destructive/10 px-3 py-2 text-[12.5px] text-destructive">
                Last scan couldn’t run — Gmail isn’t connected. Reconnect it on the Integrations tab to resume scanning.
              </div>
            )}
            {calm ? (
              <div className="flex items-center gap-3">
                <ShieldCheck className="h-8 w-8 text-accent" />
                <div>
                  <div className="text-2xl font-bold text-foreground">All clear</div>
                  <div className="text-[13px] text-muted-foreground">Scanned {cleanup?.last_scan ?? 'recently'}</div>
                </div>
              </div>
            ) : (
              <>
                <div className="flex items-baseline gap-2.5">
                  <AnimatedNumber value={attention} className="text-6xl font-bold leading-none tracking-tighter text-foreground" />
                  <span className="text-[15px] font-medium text-muted-foreground">need attention</span>
                </div>
                <div className="mt-4 flex flex-wrap items-center gap-2">
                  {urgent > 0 && (
                    <span className="inline-flex items-center gap-1.5 rounded-full bg-accent/15 px-3 py-1 text-[13px] font-semibold text-accent">
                      <span className="h-1.5 w-1.5 rounded-full bg-accent" /> {urgent} urgent
                    </span>
                  )}
                  {needsReply > 0 && (
                    <span className="inline-flex items-center gap-1.5 rounded-full bg-muted px-3 py-1 text-[13px] font-semibold text-muted-foreground">
                      <span className="h-1.5 w-1.5 rounded-full bg-muted-foreground" /> {work ? `${work.ready_to_send} ready to send` : `${needsReply} to reply`}
                    </span>
                  )}
                  <span className="text-[13px] text-muted-foreground">· scanned {cleanup?.last_scan ?? '—'}</span>
                </div>
              </>
            )}
          </div>
        </ListGroup>

        {/* First read. The one moment the app has to earn trust: connecting and
            landing on an empty "All clear" is what made this look broken. */}
        {showFirstRun && (
          <ListGroup variant="plain-mobile">
            <div className="p-5">
              <div className="flex items-center gap-2 text-[15px] font-semibold text-foreground">
                {reading && <LiveDot />}
                {/* Says what the OWNER gets, not what the app does. "Read your
                    mail" describes our mechanics; "see where your accounts
                    stand" is the reason anyone would press it. */}
                {reading ? 'Working out your accounts' : 'See where your accounts stand'}
              </div>

              {reading ? (
                <>
                  {/* The counters ARE the progress. A percentage would be
                      invented — the sweep walks backwards through time and the
                      total isn't known until it lands — but a number climbing
                      in front of you is honest and reads as alive. */}
                  <div className="mt-3 flex items-end gap-6">
                    <div>
                      <AnimatedNumber
                        value={firstRun.messages_indexed}
                        className="text-3xl font-semibold leading-none tracking-tight text-foreground tabular-nums"
                      />
                      <div className="mt-1 text-[12px] text-muted-foreground">messages read</div>
                    </div>
                    <div>
                      <AnimatedNumber
                        value={firstRun.threads}
                        className="text-3xl font-semibold leading-none tracking-tight text-foreground tabular-nums"
                      />
                      <div className="mt-1 text-[12px] text-muted-foreground">conversations</div>
                    </div>
                  </div>

                  <div className="mt-3 h-1 overflow-hidden rounded-full bg-muted">
                    <div className="h-full w-1/3 animate-sweep rounded-full bg-accent" />
                  </div>

                  {/* "keeps going if you leave" is the line that matters. This
                      read used to be driven only by the loop in this component,
                      so navigating away abandoned it half-done; the server
                      advances it too now, and the copy should say so rather
                      than quietly implying you have to sit and watch. */}
                  <div className="mt-2 text-[12.5px] text-muted-foreground">
                    {firstRun.paused_seconds
                      ? 'Gmail asked us to slow down — picking up again in a moment.'
                      : firstRun.backfill_done && firstRun.anonymous_loops > 0
                        ? `Working out who ${firstRun.anonymous_loops} more conversation${firstRun.anonymous_loops === 1 ? ' is' : 's are'} with…`
                        : `Going back ${firstRun.horizon_days} days · keeps going if you leave this page`}
                  </div>
                </>
              ) : (
                <>
                  <div className="mt-1 text-[13px] text-muted-foreground">
                    I’ll go through the last {firstRun.horizon_days} days and work out who your
                    clients are, what you owe them, and which conversations have gone quiet.
                  </div>
                  <IosButton
                    variant="tinted"
                    className="mt-3"
                    onClick={() => void startFirstRun()}
                  >
                    Build my account picture
                  </IosButton>
                </>
              )}

              {firstRun.last_error && !reading && (
                <div className="mt-3 rounded-lg bg-destructive/10 px-3 py-2 text-[12.5px] text-destructive">
                  Last read stopped: {firstRun.last_error}
                </div>
              )}
            </div>
          </ListGroup>
        )}

        {/* What you SAID you'd do, above what arrived. A late reply is a
            delay; a broken promise is a reputation, and it's the one thing no
            mail client tracks. Every row carries the sentence you wrote, so
            it's checkable rather than something to take on trust. */}
        {promises.length > 0 && (
          <ListSection title="You promised">
            <ListGroup>
              {promises.map((p) => (
                <ListRow
                  key={p.thread_id}
                  onClick={() => navigate(`/mail/${encodeURIComponent(p.thread_id)}`)}
                  chevron
                  title={p.what}
                  subtitle={
                    <>
                      <span className="block truncate">
                        {p.to || 'someone'}
                        {p.overdue_days > 0 && (
                          <span className="font-semibold text-warning">
                            {' '}· {p.overdue_days}d past your date
                          </span>
                        )}
                      </span>
                      {p.quote && (
                        <span className="block truncate text-muted-foreground/80">
                          you wrote: “{p.quote}”
                        </span>
                      )}
                    </>
                  }
                />
              ))}
            </ListGroup>
          </ListSection>
        )}

        {/* One ranked plan, not four inventories — see components/Worklist.tsx */}
        <Worklist
          data={work}
          loading={workLoading}
          loadError={workError}
          onRetry={() => { setWorkLoading(true); void refresh(); }}
          onOpenAlert={(id) => {
            const a = alerts.find((x) => x.id === id);
            if (a) setSelectedAlert(a);
            else navigate('/attention');
          }}
        />
        {/* Get alerts — shown until a notification destination is set, so the
            user can find Slack/notification setup without hunting the Rules tab. */}
        {showAlertSetup && (
          <ListSection>
            <ListGroup variant="plain-mobile">
              <ListRow
                onClick={() => navigate('/rules?setup=alerts')}
                className="py-4"
                leading={
                  <span className="inline-flex h-10 w-10 items-center justify-center rounded-xl bg-accent/15 text-accent">
                    <Bell className="h-5 w-5" />
                  </span>
                }
                title={
                  <span className="block text-[15px] font-semibold text-foreground">Get alerts in Slack</span>
                }
                subtitle="Pick where urgent mail pings you — Slack, Telegram, Discord or WhatsApp."
                chevron
              />
            </ListGroup>
          </ListSection>
        )}

        {/* Connect Gmail — and ONLY Gmail.
            This used to render a button per unconnected integration: five of
            them stacked, Gmail sitting at the same weight as Discord. That's the
            "connect N services" banner the platform explicitly tells apps not to
            build, and it buries the one thing that actually matters — without
            Gmail there is no inbox to watch and every other choice is moot. The
            notification channels are a preference with a home of their own, one
            row above. */}
        {gmailMissing && (
          <ListSection footer="Connecting is handled by Claritty — your credentials stay on the platform.">
            <ListGroup variant="plain-mobile">
              <div className="space-y-3 p-4">
                {/* One weight, not two. The `/70` on the second sentence
                    measured 3.03:1 — below WCAG AA — and it only escaped the
                    design gate because this whole block used to be invisible
                    without a backend, which is exactly the state the gate runs
                    in. */}
                <p className="text-[13px] text-muted-foreground">
                  Connect Gmail to watch your real inbox. Showing sample data for now.
                </p>
                <ConnectButton
                  integrationId={GMAIL.id}
                  className="w-full justify-center sm:w-auto"
                  onClick={() => {
                    const posted = requestConnectIntegration(GMAIL.id, appId);
                    show({
                      tone: posted ? 'success' : 'error',
                      text: posted
                        ? `Opening ${GMAIL.name} connection…`
                        : `Connect ${GMAIL.name} on the Integrations tab.`,
                    });
                  }}
                />
              </div>
            </ListGroup>
          </ListSection>
        )}

        {/* Cleanup — tap a category to see exactly what's there before clearing */}

        <ListSection title="Clear the noise" footer="Tap a category to review what will be cleared. Clear all moves the whole category to Trash (recoverable 30 days), in batches.">
          <ListGroup variant="plain-mobile">
            {CATEGORIES.map(({ key, label, field, Icon }) => {
              const count = cleanup ? (cleanup[field] as number) : 0;
              return (
                <ListRow
                  key={key}
                  onClick={() => navigate(`/cleanup/${key}`)}
                  leading={
                    <span className="inline-flex h-8 w-8 items-center justify-center rounded-lg bg-muted text-muted-foreground">
                      <Icon className="h-[18px] w-[18px]" />
                    </span>
                  }
                  title={label}
                  trailing={<span className="text-[15px] tabular-nums text-muted-foreground">{count}</span>}
                  chevron
                />
              );
            })}
          </ListGroup>
        </ListSection>

        {/* Attention */}

        {/* Recent scans — the interval is owned by the platform; showing the real
            run times makes the actual cadence (and any gaps) visible. */}
        {recentScans.length > 0 && (
          <ListSection title="Recent scans" footer="Scans run on the schedule you set — the cadence is managed by the platform.">
            <ListGroup variant="plain-mobile">
              {recentScans.slice(0, 6).map((r, i) => (
                <div key={i} className="flex items-center justify-between px-4 py-2.5">
                  <span className="text-[13px] text-muted-foreground">{r.ago}</span>
                  {r.error ? (
                    <span className="text-[12px] font-medium text-destructive">
                      {r.error === 'gmail_not_connected' ? 'Gmail disconnected' : 'failed'}
                    </span>
                  ) : (
                    <span className="text-[12px] text-muted-foreground">
                      {r.scanned} scanned · {r.flagged} flagged · {r.labeled} filed ·{' '}
                      {r.notified} pinged
                    </span>
                  )}
                </div>
              ))}
            </ListGroup>
          </ListSection>
        )}
      </Screen>

      <AnimatePresence>
        {selectedAlert && (
          <AlertSheet alert={selectedAlert} onClose={() => setSelectedAlert(null)} onChanged={() => void refresh()} />
        )}
      </AnimatePresence>
    </>
  );
}
