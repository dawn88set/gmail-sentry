import { useEffect, useState, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { AnimatePresence } from 'framer-motion';
import { ShieldCheck, RefreshCw, Megaphone, Users, Ban, Bell } from 'lucide-react';
import { EmptyState } from '@clarittyai/app-ui';
import { useToast } from '@/components/Toast';
import { AnimatedNumber } from '@/components/AnimatedNumber';
import { SmartOnboarding } from '@/components/SmartOnboarding';
import { AlertSheet } from '@/components/AlertSheet';
import { Avatar, parseSender } from '@/components/Avatar';
import { ConnectButton } from '@/components/ConnectButtons';
import { requestConnectIntegration } from '@/lib/integrations';
import { Screen } from '@/components/ios/Screen';
import { ListSection, ListGroup, ListRow } from '@/components/ios/List';
import { IosButton } from '@/components/ios/IosButton';
import { SkeletonRows } from '@/components/ios/Skeleton';
import {
  getAlerts,
  getCleanup,
  getConfig,
  getRecentScans,
  getRequiredIntegrations,
  getOnboardingStatus,
  runScan,
  toApiError,
  type Alert,
  type CleanupCounts,
  type SentryConfig,
  type ScanRunItem,
  type Tier,
  type RequiredIntegration,
} from '@/lib/api';
import { cn } from '@/lib/utils';

const TIER_CHIP: Record<Tier, string> = {
  urgent: 'bg-accent/15 text-accent',
  needs_reply: 'bg-muted text-muted-foreground',
  fyi: 'bg-muted text-muted-foreground',
};
const TIER_LABEL: Record<Tier, string> = { urgent: 'Urgent', needs_reply: 'Needs reply', fyi: 'FYI' };

const CATEGORIES = [
  { key: 'promotions' as const, label: 'Promotions', field: 'promotions' as const, Icon: Megaphone },
  { key: 'social' as const, label: 'Social', field: 'social' as const, Icon: Users },
  { key: 'spam' as const, label: 'Spam', field: 'spam' as const, Icon: Ban },
];

function relativeTime(iso?: string | null): string {
  if (!iso) return '';
  const then = new Date(iso.endsWith('Z') || iso.includes('+') ? iso : `${iso}Z`).getTime();
  if (Number.isNaN(then)) return '';
  const secs = Math.max(0, Math.floor((Date.now() - then) / 1000));
  if (secs < 60) return 'now';
  if (secs < 3600) return `${Math.floor(secs / 60)}m`;
  if (secs < 86400) return `${Math.floor(secs / 3600)}h`;
  return `${Math.floor(secs / 86400)}d`;
}

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
  const [integrations, setIntegrations] = useState<RequiredIntegration[]>([]);
  const [appId, setAppId] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [scanning, setScanning] = useState(false);
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
    } finally {
      setLoading(false);
    }
    // Where alerts go — used to nudge setup when no channel is configured yet.
    getConfig()
      .then(setConfig)
      .catch(() => undefined);
    // Recent scan runs — so the actual cadence (platform-owned) is visible.
    getRecentScans()
      .then((r) => setRecentScans(r.runs || []))
      .catch(() => undefined);
  }, [show]);

  useEffect(() => {
    void refresh();
    getRequiredIntegrations()
      .then((s) => {
        setIntegrations(s.integrations || []);
        setAppId(s.app_id ?? null);
      })
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
      show({
        tone: 'success',
        text: `Scanned ${s.scanned} email${s.scanned === 1 ? '' : 's'} — flagged ${s.flagged}, filed ${s.labeled}, notified ${s.notified}.`,
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
  const attention = urgent + needsReply;
  const calm = attention === 0;
  const notConnected = integrations.filter((i) => !i.connected);
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
        title="Inbox"
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
                      <span className="h-1.5 w-1.5 rounded-full bg-muted-foreground" /> {needsReply} to reply
                    </span>
                  )}
                  <span className="text-[13px] text-muted-foreground">· scanned {cleanup?.last_scan ?? '—'}</span>
                </div>
              </>
            )}
          </div>
        </ListGroup>

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

        {/* Connect */}
        {notConnected.length > 0 && (
          <ListSection footer="Connecting is handled by Claritty — your credentials stay on the platform.">
            <ListGroup variant="plain-mobile">
              <div className="space-y-3 p-4">
                <p className="text-[13px] text-muted-foreground">
                  Connect your accounts to scan your real inbox and send Slack pings.
                  <span className="text-muted-foreground/70"> Showing sample data for now.</span>
                </p>
                <div className="flex flex-col gap-2 sm:flex-row">
                  {notConnected.map((i) => (
                    <ConnectButton
                      key={i.id}
                      integrationId={i.id}
                      className="w-full justify-center sm:w-auto"
                      onClick={() => {
                        const posted = requestConnectIntegration(i.id, appId);
                        show({
                          tone: posted ? 'success' : 'error',
                          text: posted ? `Opening ${i.name} connection…` : `Connect ${i.name} on the Integrations tab.`,
                        });
                      }}
                    />
                  ))}
                </div>
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
        <ListSection title="Needs your attention">
          {loading ? (
            <ListGroup variant="plain-mobile">
              <SkeletonRows count={4} />
            </ListGroup>
          ) : alerts.length === 0 ? (
            <ListGroup variant="plain-mobile">
              <EmptyState
                icon={<ShieldCheck className="h-6 w-6 text-accent" />}
                title="Inbox is calm"
                description="Nothing needs your attention. Run a scan, or set up rules on the Rules tab."
              />
            </ListGroup>
          ) : (
            <ListGroup variant="plain-mobile">
              {alerts.slice(0, 5).map((a) => {
                const who = parseSender(a.sender || '');
                const chip = TIER_CHIP[a.tier] ?? TIER_CHIP.fyi;
                return (
                  <ListRow
                    key={a.id}
                    onClick={() => setSelectedAlert(a)}
                    leading={<Avatar name={who.name} email={who.email} className="h-9 w-9 text-sm" />}
                    title={
                      <div className="flex items-baseline gap-2">
                        <span className="min-w-0 flex-1 truncate text-[15px] font-medium text-foreground">
                          {a.subject || '(no subject)'}
                        </span>
                        <span className="flex-shrink-0 text-[12px] text-muted-foreground">{relativeTime(a.created_at)}</span>
                      </div>
                    }
                    subtitle={
                      <div className="mt-0.5 flex items-center gap-1.5">
                        <span className={cn('flex-shrink-0 rounded-full px-1.5 py-0.5 text-[10px] font-semibold', chip)}>
                          {TIER_LABEL[a.tier]}
                        </span>
                        <span className="min-w-0 flex-1 truncate">
                          <span className="text-foreground/70">{who.name || a.sender}</span>
                          {a.reason ? ` — ${a.reason}` : ''}
                        </span>
                      </div>
                    }
                    chevron
                  />
                );
              })}
              <ListRow
                onClick={() => navigate('/attention')}
                title={<span className="font-medium text-accent">See all &amp; take action</span>}
                chevron
              />
            </ListGroup>
          )}
        </ListSection>

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
                      {r.scanned} scanned · {r.flagged} flagged · {r.notified} pinged
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
