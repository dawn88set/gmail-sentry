import { useEffect, useState, useCallback, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { AnimatePresence } from 'framer-motion';
import { Plus, Trash2, Sparkles, Slack, Mail, Check, Send, MessageSquare, Phone, Loader2, MessageSquareText } from 'lucide-react';
import { Button } from '@clarittyai/app-ui';
import { useToast } from '@/components/Toast';
import { SmartOnboarding } from '@/components/SmartOnboarding';
import { FoldersSection } from '@/components/FoldersSection';
import { ConnectButton } from '@/components/ConnectButtons';
import { requestConnectIntegration, requestDisconnectIntegration } from '@/lib/integrations';
import { Screen } from '@/components/ios/Screen';
import { ListSection, ListGroup, ListRow } from '@/components/ios/List';
import { Toggle } from '@/components/ios/Toggle';
import { IosButton } from '@/components/ios/IosButton';
import { SkeletonRows } from '@/components/ios/Skeleton';
import {
  getConfig,
  updateConfig,
  testNotify,
  type NotifyResult,
  getSlackChannels,
  type SlackChannel,
  getRules,
  createRule,
  toggleRule,
  deleteRule,
  getLabelRules,
  createLabelRule,
  toggleLabelRule,
  deleteLabelRule,
  getOnboardingStatus,
  getRequiredIntegrations,
  toApiError,
  type SentryConfig,
  type NotifyChannel,
  type TriageRule,
  type LabelRule,
  type RuleKind,
  type Tier,
  type LabelMatchType,
  type RequiredIntegration,
} from '@/lib/api';
import { cn } from '@/lib/utils';

const INTEGRATION_META: Record<string, { Icon: typeof Mail; desc: string }> = {
  gmail: { Icon: Mail, desc: 'Read & organize your inbox' },
  slack: { Icon: Slack, desc: 'Alerts to a Slack channel' },
  telegram: { Icon: Send, desc: 'Alerts to a Telegram chat' },
  discord: { Icon: MessageSquare, desc: 'Alerts to a Discord channel' },
  twilio: { Icon: Phone, desc: 'Alerts via WhatsApp (Twilio)' },
};
const DEFAULT_INTEGRATIONS: RequiredIntegration[] = [
  { id: 'gmail', name: 'Gmail', connected: false },
  { id: 'slack', name: 'Slack', connected: false },
  { id: 'telegram', name: 'Telegram', connected: false },
  { id: 'discord', name: 'Discord', connected: false },
  { id: 'twilio', name: 'WhatsApp (Twilio)', connected: false },
];

/**
 * Where each channel's alerts go. Shown inline under a channel once it's
 * connected, so "connect Slack" and "which Slack channel" live together — Gmail
 * is the source and has no destination. The value is a non-secret routing id
 * stored on SentryConfig (the credential stays in the platform broker).
 */
const DEST_FIELD: Record<
  string,
  { field: keyof SentryConfig; label: string; placeholder: string; hint?: string }
> = {
  slack: {
    field: 'slack_channel',
    label: 'Send alerts to',
    placeholder: 'U0123… (your member ID, for a DM)  ·  or C0123… (channel ID)',
    hint: 'Use an ID, not a name (a name fails with channel_not_found). Easiest: your member ID for a DM — in Slack click your avatar → Profile → ⋮ → “Copy member ID” (U0…). For a channel: /invite @Claritty in it, then open the channel → its name → scroll to “Channel ID” (C0…).',
  },
  telegram: {
    field: 'telegram_chat_id',
    label: 'Send alerts to',
    placeholder: '123456789  ·  or @channel',
  },
  discord: {
    field: 'discord_channel_id',
    label: 'Send alerts to',
    placeholder: '123456789012345678',
  },
  twilio: {
    field: 'whatsapp_to',
    label: 'Send alerts to',
    placeholder: '+14155551234',
  },
};

/** Integration id → the notify channel label the backend uses (twilio→whatsapp). */
const NOTIFY_CHANNEL: Record<string, string> = {
  slack: 'slack',
  telegram: 'telegram',
  discord: 'discord',
  twilio: 'whatsapp',
};

const KIND_LABEL: Record<RuleKind, string> = {
  nl: 'Natural-language',
  vip_sender: 'VIP sender',
  keyword: 'Keyword',
};
const TIER_LABEL: Record<Tier, string> = { urgent: 'Urgent', needs_reply: 'Needs reply', fyi: 'FYI' };
const TIER_CHIP: Record<Tier, string> = {
  urgent: 'bg-accent/15 text-accent',
  needs_reply: 'bg-muted text-muted-foreground',
  fyi: 'bg-muted text-muted-foreground',
};
const MATCH_LABEL: Record<LabelMatchType, string> = {
  sender: 'Sender',
  domain: 'Domain',
  subject_keyword: 'Subject keyword',
};

const inputCls =
  'w-full rounded-lg bg-muted/60 px-3 py-2 text-[15px] text-foreground placeholder:text-muted-foreground/50 outline-none focus:ring-2 focus:ring-accent/40';

/**
 * Slack destinations must be an ID, never a name. Channel/DM/user ids are
 * uppercase and start with C/D/G/U/W (e.g. C0BGKR50VFS, U08UC99NS8P). A value
 * like `#gmail-sentry` or `@someone` fails with `channel_not_found` — catch it
 * before it's saved so alerts don't silently never send.
 */
const SLACK_ID_RE = /^[CDGUW][A-Z0-9]{6,}$/;
function slackDestError(value: string): string | null {
  const v = (value || '').trim();
  if (!v) return null;
  if (v.startsWith('#')) return 'Use the channel ID (starts with C), not the name #' + v.replace(/^#/, '') + '.';
  if (v.startsWith('@')) return 'Use the member ID (starts with U), not an @name.';
  if (!SLACK_ID_RE.test(v)) return 'That’s not a Slack ID. Use a channel ID (C…) or member ID (U…) — open the channel → About → Channel ID.';
  return null;
}

function FieldCell({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="px-4 py-2.5">
      <div className="mb-1 text-[12px] font-medium uppercase tracking-wide text-muted-foreground">{label}</div>
      {children}
    </div>
  );
}

function DeleteButton({ label, onClick }: { label: string; onClick: () => void }) {
  return (
    <Button
      variant="ghost"
      size="sm"
      onClick={onClick}
      aria-label={label}
      className="h-8 w-8 justify-center px-0 text-muted-foreground hover:bg-destructive/10 hover:text-destructive"
    >
      <Trash2 className="h-[18px] w-[18px]" />
    </Button>
  );
}

export default function Rules() {
  const { show } = useToast();
  const navigate = useNavigate();
  const [config, setConfig] = useState<SentryConfig>({
    slack_channel: '',
    notify_tier: 'urgent',
    channel_tiers: {},
    telegram_chat_id: '',
    discord_channel_id: '',
    teams_chat_id: '',
    whatsapp_to: '',
    auto_draft: true,
  });
  const [testResults, setTestResults] = useState<NotifyResult[] | null>(null);
  const [testing, setTesting] = useState(false);
  const [testingChannel, setTestingChannel] = useState<string | null>(null);

  /** Send a test to ONE channel, right where its destination is set. */
  const testOne = async (integrationId: string, label: string) => {
    const channel = NOTIFY_CHANNEL[integrationId];
    if (!channel) return;
    setTestingChannel(integrationId);
    try {
      const { results } = await testNotify(channel);
      const r = results.find((x) => x.channel === channel);
      if (r?.ok) show({ tone: 'success', text: `Test sent to ${label} ✓ — check ${label}.` });
      else show({ tone: 'error', text: `${label}: ${r?.error || 'not sent'}` });
    } catch (err) {
      show({ tone: 'error', text: `${label} test failed: ${toApiError(err).message}` });
    } finally {
      setTestingChannel(null);
    }
  };

  const runTest = async () => {
    setTesting(true);
    setTestResults(null);
    try {
      const { results } = await testNotify();
      setTestResults(results);
      if (results.length === 0) {
        show({ tone: 'error', text: 'No channels configured — connect one and set its destination.' });
      }
    } catch (err) {
      show({ tone: 'error', text: `Test failed: ${toApiError(err).message}` });
    } finally {
      setTesting(false);
    }
  };
  const [rules, setRules] = useState<TriageRule[]>([]);
  const [labelRules, setLabelRules] = useState<LabelRule[]>([]);
  const [wizard, setWizard] = useState(false);
  const [obRole, setObRole] = useState('');
  const [obIntent, setObIntent] = useState('');
  const [integrations, setIntegrations] = useState<RequiredIntegration[]>(DEFAULT_INTEGRATIONS);
  const [integrationsLoaded, setIntegrationsLoaded] = useState(false);
  const firstIntegrationsLoad = useRef(true);
  // When the Dashboard "Get alerts" prompt deep-links here (?setup=alerts),
  // scroll the Integrations section into view so Slack setup is front-and-center.
  const integrationsRef = useRef<HTMLDivElement>(null);
  const [appId, setAppId] = useState<string | null>(null);
  // Slack channel picker: real channels the bot can see, so the user can't
  // mistype and hit `channel_not_found`.
  const [slackChannels, setSlackChannels] = useState<SlackChannel[]>([]);
  const [slackChannelsError, setSlackChannelsError] = useState<string | null>(null);
  // The connected Slack workspace/team name — shown so the user can confirm a
  // channel id belongs to the SAME workspace (a mismatch → channel_not_found).
  const [slackWorkspace, setSlackWorkspace] = useState<string>('');
  // Transient "Saved ✓" acknowledgement so the user knows a blur/select persisted.
  const [savedField, setSavedField] = useState<string | null>(null);
  const savedTimer = useRef<number | null>(null);

  const [rName, setRName] = useState('');
  const [rKind, setRKind] = useState<RuleKind>('nl');
  const [rValue, setRValue] = useState('');
  const [rTier, setRTier] = useState<Tier>('urgent');

  const [lName, setLName] = useState('');
  const [lMatch, setLMatch] = useState<LabelMatchType>('sender');
  const [lValue, setLValue] = useState('');
  const [lLabel, setLLabel] = useState('');
  const [lArchive, setLArchive] = useState(false);

  const load = useCallback(async () => {
    try {
      const [c, r, lr] = await Promise.all([getConfig(), getRules(), getLabelRules()]);
      setConfig(c);
      setRules(r);
      setLabelRules(lr);
    } catch (err) {
      show({ tone: 'error', text: `Couldn’t load rules: ${toApiError(err).message}` });
    }
    getOnboardingStatus()
      .then((s) => {
        setObRole(s.role || '');
        setObIntent(s.intent || '');
      })
      .catch(() => undefined);
  }, [show]);

  const refreshIntegrations = useCallback(async () => {
    const started = Date.now();
    try {
      const s = await getRequiredIntegrations();
      if (s.integrations?.length) setIntegrations(s.integrations);
      setAppId(s.app_id ?? null);
    } catch {
      /* best-effort */
    } finally {
      // On the FIRST load, hold the ghost rows a beat so the loading state is
      // actually perceptible (status usually resolves in <150ms). Later polls
      // flip instantly — no skeleton flicker on every re-check.
      if (firstIntegrationsLoad.current) {
        firstIntegrationsLoad.current = false;
        const wait = Math.max(0, 600 - (Date.now() - started));
        window.setTimeout(() => setIntegrationsLoaded(true), wait);
      } else {
        setIntegrationsLoaded(true);
      }
    }
  }, []);

  useEffect(() => {
    void load();
    void refreshIntegrations();
  }, [load, refreshIntegrations]);

  // Deep-linked from the Dashboard "Get alerts" card → bring Integrations into
  // view once the rows have rendered.
  useEffect(() => {
    if (!integrationsLoaded) return;
    const params = new URLSearchParams(window.location.search);
    if (params.get('setup') !== 'alerts') return;
    const t = window.setTimeout(
      () => integrationsRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' }),
      100,
    );
    return () => window.clearTimeout(t);
  }, [integrationsLoaded]);

  // The platform acks connect/disconnect back into the iframe — refresh status
  // immediately so the row flips without waiting for the next poll tick.
  useEffect(() => {
    const onMsg = (e: MessageEvent) => {
      const t = e.data?.type;
      if (
        t === 'claritty:disconnect-integration-done' ||
        t === 'claritty:connect-integration-started' ||
        t === 'claritty:connect-integration-done'
      ) {
        void refreshIntegrations();
      }
    };
    window.addEventListener('message', onMsg);
    return () => window.removeEventListener('message', onMsg);
  }, [refreshIntegrations]);

  // Auto-detect a completed connection (after the OAuth popup) without a manual
  // refresh: re-check on focus/return + a light poll while any is unconnected.
  useEffect(() => {
    if (integrations.every((i) => i.connected)) return;
    const poll = () => void refreshIntegrations();
    const iv = window.setInterval(poll, 4000);
    const onVis = () => {
      if (!document.hidden) poll();
    };
    window.addEventListener('focus', poll);
    document.addEventListener('visibilitychange', onVis);
    return () => {
      window.clearInterval(iv);
      window.removeEventListener('focus', poll);
      document.removeEventListener('visibilitychange', onVis);
    };
  }, [integrations, refreshIntegrations]);

  // Load the Slack channel list + connected workspace so the destination becomes a
  // pick-list (no mistyped name → no `channel_not_found`) and the user can confirm
  // the workspace. Loaded INDEPENDENT of the connected badge (which is fail-open and
  // can false-negative): the endpoint itself reports the real connection state, so
  // gating on the badge would hide the picker when the badge is wrong. Re-runs when
  // the badge flips (after a connect) so it refreshes post-OAuth.
  const slackConnected = integrations.find((i) => i.id === 'slack')?.connected ?? false;
  useEffect(() => {
    if (!integrationsLoaded) return;
    let cancelled = false;
    getSlackChannels()
      .then((res) => {
        if (cancelled) return;
        setSlackChannels(res.channels ?? []);
        setSlackChannelsError(res.error ?? null);
        setSlackWorkspace(res.workspace ?? '');
      })
      .catch((err) => {
        if (!cancelled) setSlackChannelsError(toApiError(err).message);
      });
    return () => {
      cancelled = true;
    };
  }, [integrationsLoaded, slackConnected]);

  const saveConfig = async (patch: Partial<SentryConfig>) => {
    setConfig((c) => ({ ...c, ...patch }));
    try {
      setConfig(await updateConfig(patch));
      // Acknowledge the auto-save so the user knows it persisted.
      const key = Object.keys(patch)[0] ?? null;
      setSavedField(key);
      if (savedTimer.current) window.clearTimeout(savedTimer.current);
      savedTimer.current = window.setTimeout(() => setSavedField(null), 2200);
    } catch (err) {
      show({ tone: 'error', text: `Couldn’t save: ${toApiError(err).message}` });
      void load();
    }
  };

  const addRule = async () => {
    if (!rName.trim() || !rValue.trim()) {
      show({ tone: 'error', text: 'Give the rule a name and a value.' });
      return;
    }
    try {
      const created = await createRule({ name: rName.trim(), kind: rKind, value: rValue.trim(), tier: rTier });
      setRules((p) => [created, ...p]);
      setRName('');
      setRValue('');
    } catch (err) {
      show({ tone: 'error', text: `Couldn’t add rule: ${toApiError(err).message}` });
    }
  };

  const removeRule = async (id: string) => {
    setRules((p) => p.filter((r) => r.id !== id));
    try {
      await deleteRule(id);
    } catch (err) {
      show({ tone: 'error', text: `Couldn’t delete: ${toApiError(err).message}` });
      void load();
    }
  };

  const flipRule = async (id: string) => {
    try {
      const updated = await toggleRule(id);
      setRules((p) => p.map((r) => (r.id === id ? updated : r)));
    } catch (err) {
      show({ tone: 'error', text: `Couldn’t update: ${toApiError(err).message}` });
    }
  };

  const addLabelRule = async () => {
    if (!lName.trim() || !lValue.trim() || !lLabel.trim()) {
      show({ tone: 'error', text: 'Fill in name, match value, and label.' });
      return;
    }
    try {
      const created = await createLabelRule({
        name: lName.trim(),
        match_type: lMatch,
        match_value: lValue.trim(),
        target_label: lLabel.trim(),
        archive_after: lArchive,
      });
      setLabelRules((p) => [created, ...p]);
      setLName('');
      setLValue('');
      setLLabel('');
      setLArchive(false);
    } catch (err) {
      show({ tone: 'error', text: `Couldn’t add filing rule: ${toApiError(err).message}` });
    }
  };

  const removeLabelRule = async (id: string) => {
    setLabelRules((p) => p.filter((r) => r.id !== id));
    try {
      await deleteLabelRule(id);
    } catch (err) {
      show({ tone: 'error', text: `Couldn’t delete: ${toApiError(err).message}` });
      void load();
    }
  };

  const flipLabelRule = async (id: string) => {
    try {
      const updated = await toggleLabelRule(id);
      setLabelRules((p) => p.map((r) => (r.id === id ? updated : r)));
    } catch (err) {
      show({ tone: 'error', text: `Couldn’t update: ${toApiError(err).message}` });
    }
  };

  const valuePlaceholder =
    rKind === 'nl'
      ? 'e.g. Anything from my manager'
      : rKind === 'vip_sender'
        ? 'e.g. boss@acme.com'
        : 'e.g. invoice';

  return (
    <>
      <AnimatePresence>
        {wizard && (
          <SmartOnboarding
            initialRole={obRole}
            initialIntent={obIntent}
            onDone={(applied) => {
              setWizard(false);
              if (applied) void load();
            }}
          />
        )}
      </AnimatePresence>

      <Screen title="Rules">
        {/* Smart setup */}
        <ListGroup variant="plain-mobile">
          <ListRow
            onClick={() => setWizard(true)}
            leading={
              <span className="inline-flex h-8 w-8 items-center justify-center rounded-lg bg-accent/15 text-accent">
                <Sparkles className="h-[18px] w-[18px]" />
              </span>
            }
            title="Smart setup"
            subtitle="Let AI configure your rules from your inbox"
            chevron
          />
          <ListRow
            onClick={() => navigate('/teach')}
            leading={
              <span className="inline-flex h-8 w-8 items-center justify-center rounded-lg bg-accent/15 text-accent">
                <MessageSquareText className="h-[18px] w-[18px]" />
              </span>
            }
            title="Teach Sentry"
            subtitle="Describe what matters in plain language — Sentry turns it into rules"
            chevron
          />
        </ListGroup>

        {/* Integrations */}
        <div ref={integrationsRef} className="scroll-mt-4">
        <ListSection
          title="Integrations"
          footer="Connecting is handled by Claritty — your credentials stay on the platform."
        >
          <ListGroup variant="plain-mobile">
            {!integrationsLoaded && <SkeletonRows count={DEFAULT_INTEGRATIONS.length} />}
            {integrationsLoaded &&
              integrations.map((it) => {
              const meta = INTEGRATION_META[it.id] ?? { Icon: Mail, desc: '' };
              const Icon = meta.Icon;
              const dest = DEST_FIELD[it.id];
              return (
                <div key={it.id} className="px-4 py-3.5">
                  <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
                  <div className="flex min-w-0 flex-1 items-center gap-3">
                    <span className="inline-flex h-10 w-10 flex-shrink-0 items-center justify-center rounded-xl bg-muted text-foreground">
                      <Icon className="h-5 w-5" />
                    </span>
                    <div className="min-w-0 flex-1">
                      <div className="text-[15px] font-semibold text-foreground">{it.name}</div>
                      <div className="truncate text-[13px] text-muted-foreground">{meta.desc}</div>
                    </div>
                    {it.connected && (
                      <span className="inline-flex flex-shrink-0 items-center gap-1 rounded-full bg-accent/15 px-2.5 py-1 text-xs font-semibold text-accent">
                        <Check className="h-3.5 w-3.5" /> Connected
                      </span>
                    )}
                  </div>
                  {it.connected ? (
                    <Button
                      variant="secondary"
                      onClick={() => {
                        const posted = requestDisconnectIntegration(it.id, appId);
                        show({
                          tone: posted ? 'success' : 'error',
                          text: posted
                            ? `Disconnecting ${it.name}…`
                            : `Manage ${it.name} on the Integrations tab.`,
                        });
                        // Re-poll after the platform revokes the credential.
                        setTimeout(() => void refreshIntegrations(), 1500);
                        setTimeout(() => void refreshIntegrations(), 4000);
                      }}
                      className="w-full flex-shrink-0 justify-center sm:w-auto"
                    >
                      Disconnect
                    </Button>
                  ) : (
                    <ConnectButton
                      integrationId={it.id}
                      className="w-full justify-center sm:w-auto"
                      onClick={() => {
                        const posted = requestConnectIntegration(it.id, appId);
                        show({
                          tone: posted ? 'success' : 'error',
                          text: posted ? `Opening ${it.name} connection…` : `Connect ${it.name} on the Integrations tab.`,
                        });
                      }}
                    />
                  )}
                  </div>
                  {/* Where this channel's alerts go. Shown regardless of the
                      connection badge (which can false-negative) so configuring +
                      testing is never blocked — the Send-test result is the real
                      source of truth for whether it works. */}
                  {dest && (
                    <div className="mt-3 sm:pl-[52px]">
                      <div className="mb-1 flex items-center gap-2">
                        <label className="text-[13px] font-medium text-foreground">{dest.label}</label>
                        {savedField === dest.field && (
                          <span className="inline-flex items-center gap-1 text-[12px] font-medium text-accent">
                            <Check className="h-3.5 w-3.5" /> Saved
                          </span>
                        )}
                      </div>

                      {/* Which workspace the token is on — so the user can confirm a
                          channel id belongs to it (a mismatch → channel_not_found). */}
                      {it.id === 'slack' && slackWorkspace && (
                        <p className="mb-2 text-[12px] text-muted-foreground">
                          Connected workspace: <span className="font-medium text-foreground">{slackWorkspace}</span>
                          {' '}— the channel must be in this workspace.
                        </p>
                      )}

                      {/* Slack: pick a real channel the bot can see → no mistyped
                          name, no `channel_not_found`. */}
                      {it.id === 'slack' && slackChannels.length > 0 && (
                        <select
                          className={cn(inputCls, 'mb-2')}
                          value={slackChannels.some((c) => c.id === config.slack_channel) ? config.slack_channel : ''}
                          onChange={(e) => saveConfig({ slack_channel: e.target.value })}
                        >
                          <option value="">Choose a channel…</option>
                          {slackChannels.map((c) => (
                            <option key={c.id} value={c.id}>
                              #{c.name}
                            </option>
                          ))}
                        </select>
                      )}

                      {(() => {
                        const val = (config[dest.field] as string) ?? '';
                        const slackErr = it.id === 'slack' ? slackDestError(val) : null;
                        return (
                          <>
                            <input
                              className={cn(inputCls, slackErr && 'ring-2 ring-destructive/50')}
                              value={val}
                              placeholder={dest.placeholder}
                              onChange={(e) => setConfig({ ...config, [dest.field]: e.target.value })}
                              onBlur={() => {
                                // Never persist a Slack name — it would fail on every
                                // alert. Warn instead of saving garbage.
                                if (slackErr) {
                                  show({ tone: 'error', text: slackErr });
                                  return;
                                }
                                saveConfig({ [dest.field]: config[dest.field] });
                              }}
                            />
                            {slackErr && <p className="mt-1 text-[12px] text-destructive">{slackErr}</p>}
                          </>
                        );
                      })()}

                      {/* Per-channel urgency routing — e.g. urgent → WhatsApp,
                          replies → Slack. Defaults to the global tier below. */}
                      {(config[dest.field] as string)?.trim() && (
                        <div className="mt-2 flex items-center justify-between gap-2">
                          <span className="text-[13px] text-muted-foreground">Notify this channel for</span>
                          <select
                            className="rounded-lg bg-muted/60 px-2 py-1 text-[13px] text-foreground outline-none focus:ring-2 focus:ring-accent/40"
                            value={config.channel_tiers?.[NOTIFY_CHANNEL[it.id] as NotifyChannel] ?? ''}
                            onChange={(e) => {
                              const label = NOTIFY_CHANNEL[it.id] as NotifyChannel;
                              const next = { ...(config.channel_tiers ?? {}) };
                              if (e.target.value === '') delete next[label];
                              else next[label] = e.target.value as 'urgent' | 'needs_reply';
                              void saveConfig({ channel_tiers: next });
                            }}
                          >
                            <option value="">
                              Default ({config.notify_tier === 'urgent' ? 'urgent only' : 'urgent + replies'})
                            </option>
                            <option value="urgent">Urgent only</option>
                            <option value="needs_reply">Urgent + replies</option>
                          </select>
                        </div>
                      )}

                      {/* Step-by-step guide: Slack needs an ID (member or
                          channel) — never a name. Shown whether or not the
                          channel picker is available. */}
                      {it.id === 'slack' ? (
                        <div className="mt-2 rounded-lg bg-muted/40 p-3 text-[12px] leading-relaxed text-muted-foreground">
                          <p className="mb-2 font-semibold text-foreground">
                            Slack needs an ID (it starts with <span className="font-mono">U</span> or{' '}
                            <span className="font-mono">C</span>) — a channel or user <em>name</em> won’t work.
                          </p>

                          <p className="mb-1 font-medium text-foreground">Option 1 · DM yourself (fastest — no setup)</p>
                          <ol className="mb-2.5 ml-4 list-decimal space-y-0.5">
                            <li>In Slack, click your avatar (top-right) → <span className="font-medium text-foreground">Profile</span>.</li>
                            <li>
                              Click <span className="font-mono">⋯</span> / <span className="font-medium">More</span> →{' '}
                              <span className="font-medium text-foreground">Copy member ID</span>.
                            </li>
                            <li>Paste it in the box above — it looks like <span className="font-mono">U0A1B2C3D</span>.</li>
                          </ol>

                          <p className="mb-1 font-medium text-foreground">Option 2 · Post to a channel</p>
                          <ol className="ml-4 list-decimal space-y-0.5">
                            <li>
                              In that channel, send <span className="font-mono">/invite @Claritty</span>{' '}
                              (the bot must be a member to post).
                            </li>
                            <li>
                              Click the channel name → scroll to the bottom of <span className="font-medium">About</span> →
                              copy the <span className="font-medium text-foreground">Channel ID</span> (<span className="font-mono">C0…</span>).
                            </li>
                            <li>Paste it in the box above.</li>
                          </ol>

                          <p className="mt-2">
                            Then tap <span className="font-medium text-foreground">Send test message</span> below to confirm.
                          </p>
                          {slackChannelsError ? (
                            /succeeded|permission|scope/i.test(slackChannelsError) ? (
                              <span className="mt-1.5 block text-[12px] text-destructive">
                                Slack is missing a permission to list channels — disconnect &amp; reconnect
                                Slack above to re-grant it, then this picker will fill in.
                              </span>
                            ) : (
                              <span className="mt-1.5 block text-[11px] opacity-70">
                                Channel list unavailable ({slackChannelsError})
                              </span>
                            )
                          ) : null}
                        </div>
                      ) : dest.hint ? (
                        <p className="mt-1 text-[12px] text-muted-foreground">{dest.hint}</p>
                      ) : null}
                      {!(config[dest.field] as string)?.trim() ? (
                        <p className="mt-1 text-[12px] text-destructive">
                          Set a destination or {it.name} alerts won’t be sent.
                        </p>
                      ) : it.id === 'slack' && slackDestError(config[dest.field] as string) ? null : (
                        <Button
                          variant="ghost"
                          size="sm"
                          disabled={testingChannel === it.id}
                          onClick={() => testOne(it.id, it.name)}
                          className="mt-2 bg-accent/10 text-accent hover:bg-accent/20"
                          icon={
                            testingChannel === it.id ? (
                              <Loader2 className="h-3.5 w-3.5 animate-spin" />
                            ) : (
                              <Send className="h-3.5 w-3.5" />
                            )
                          }
                        >
                          Send test message
                        </Button>
                      )}
                    </div>
                  )}
                </div>
              );
            })}
          </ListGroup>
        </ListSection>
        </div>

        {/* Notifications */}
        <ListSection
          title="Notifications"
          footer="Each connected channel above has its own “Send alerts to” field. Set the tier here, then send a test to confirm delivery."
        >
          <ListGroup variant="plain-mobile">
            <ListRow
              title="Ping me about"
              trailing={
                <select
                  className="rounded-lg bg-transparent py-1 text-[15px] text-muted-foreground outline-none"
                  value={config.notify_tier}
                  onChange={(e) => saveConfig({ notify_tier: e.target.value as SentryConfig['notify_tier'] })}
                >
                  <option value="urgent">Urgent only</option>
                  <option value="needs_reply">Urgent + replies</option>
                </select>
              }
            />
            <ListRow
              title="Draft replies automatically"
              subtitle="Prepares a reply in your voice for “needs reply” mail — the ping carries it so you can approve in one tap. Never sends without your OK."
              trailing={
                <Toggle
                  checked={config.auto_draft}
                  onChange={(v) => void saveConfig({ auto_draft: v })}
                  aria-label="Draft replies automatically"
                />
              }
            />
          </ListGroup>

          {/* Always-visible Slack setup guide (Slack needs an ID, not a name —
              the #1 reason a test fails). */}
          <div className="mt-3 rounded-2xl bg-card p-4 text-[13px] leading-relaxed text-muted-foreground ring-1 ring-border">
            <p className="mb-2 flex items-center gap-2 text-[14px] font-semibold text-foreground">
              <Slack className="h-4 w-4" /> Setting a Slack destination
            </p>
            <p className="mb-2.5">
              Slack’s “Send alerts to” field needs an <span className="font-semibold text-foreground">ID</span>{' '}
              (it starts with <span className="font-mono">U</span> or <span className="font-mono">C</span>) — a channel or
              user <em>name</em> won’t work and fails with <span className="font-mono">channel_not_found</span>.
            </p>

            <p className="mb-1 font-medium text-foreground">Option 1 · DM yourself (fastest — no setup)</p>
            <ol className="mb-3 ml-4 list-decimal space-y-0.5">
              <li>In Slack, click your avatar (top-right) → <span className="font-medium text-foreground">Profile</span>.</li>
              <li>
                Click <span className="font-mono">⋯</span> / <span className="font-medium">More</span> →{' '}
                <span className="font-medium text-foreground">Copy member ID</span>.
              </li>
              <li>Paste it in Slack’s field above — it looks like <span className="font-mono">U0A1B2C3D</span>.</li>
            </ol>

            <p className="mb-1 font-medium text-foreground">Option 2 · Post to a channel</p>
            <ol className="ml-4 list-decimal space-y-0.5">
              <li>
                In that channel, send <span className="font-mono">/invite @Claritty</span>{' '}
                (the bot must be a member).
              </li>
              <li>
                Click the channel name → scroll to the bottom of <span className="font-medium">About</span> → copy the{' '}
                <span className="font-medium text-foreground">Channel ID</span> (<span className="font-mono">C0…</span>).
              </li>
              <li>Paste it in Slack’s field above.</li>
            </ol>

            <p className="mt-2.5">
              Then use <span className="font-medium text-foreground">Send test message</span> on the Slack row, or the
              button below, to confirm delivery.
            </p>
          </div>

          {/* Send a test alert to every configured channel + show each result. */}
          <div className="mt-3 px-1">
            <IosButton
              variant="tinted"
              onClick={runTest}
              disabled={testing}
              icon={testing ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}
            >
              {testing ? 'Sending test…' : 'Send test to all channels'}
            </IosButton>
          </div>
          {testResults && testResults.length > 0 && (
            <div className="mt-2 space-y-1.5 px-1">
              {testResults.map((r) => (
                <div
                  key={r.channel}
                  className="flex items-start gap-2 rounded-xl bg-card px-3 py-2 text-[13px] ring-1 ring-border"
                >
                  <span
                    className={cn(
                      'mt-0.5 flex h-4 w-4 flex-shrink-0 items-center justify-center rounded-full',
                      r.ok ? 'bg-accent/15 text-accent' : 'bg-destructive/15 text-destructive',
                    )}
                  >
                    {r.ok ? <Check className="h-3 w-3" /> : <span className="text-[10px] font-bold">!</span>}
                  </span>
                  <div className="min-w-0 flex-1">
                    <span className="font-medium capitalize text-foreground">{r.channel}</span>{' '}
                    <span className={r.ok ? 'text-muted-foreground' : 'text-destructive'}>
                      {r.ok ? 'delivered' : r.error || 'failed'}
                    </span>
                  </div>
                </div>
              ))}
            </div>
          )}
        </ListSection>

        {/* Urgency rules */}
        <ListSection title="Urgency rules" footer="Rules combine with built-in deadline detection.">
          {rules.length > 0 && (
            <ListGroup variant="plain-mobile" className="mb-3">
              {rules.map((r) => (
                <ListRow
                  key={r.id}
                  leading={
                    <span className={cn('rounded-full px-2 py-0.5 text-[10px] font-semibold', TIER_CHIP[r.tier])}>
                      {TIER_LABEL[r.tier]}
                    </span>
                  }
                  title={<span className={cn(!r.active && 'opacity-50')}>{r.name}</span>}
                  subtitle={<span className={cn(!r.active && 'opacity-50')}>{KIND_LABEL[r.kind]} · {r.value}</span>}
                  trailing={
                    <>
                      <Toggle checked={r.active} onChange={() => void flipRule(r.id)} aria-label="Rule active" />
                      <DeleteButton label="Delete rule" onClick={() => void removeRule(r.id)} />
                    </>
                  }
                />
              ))}
            </ListGroup>
          )}
          <ListGroup variant="plain-mobile">
            <FieldCell label="Name">
              <input className={inputCls} value={rName} placeholder="Boss emails" onChange={(e) => setRName(e.target.value)} />
            </FieldCell>
            <FieldCell label="Type">
              <select className={inputCls} value={rKind} onChange={(e) => setRKind(e.target.value as RuleKind)}>
                <option value="nl">Natural-language</option>
                <option value="vip_sender">VIP sender</option>
                <option value="keyword">Keyword</option>
              </select>
            </FieldCell>
            <FieldCell label="Match">
              <input className={inputCls} value={rValue} placeholder={valuePlaceholder} onChange={(e) => setRValue(e.target.value)} />
            </FieldCell>
            <FieldCell label="Tier">
              <select className={inputCls} value={rTier} onChange={(e) => setRTier(e.target.value as Tier)}>
                <option value="urgent">Urgent</option>
                <option value="needs_reply">Needs reply</option>
                <option value="fyi">FYI</option>
              </select>
            </FieldCell>
          </ListGroup>
          <IosButton variant="filled" full className="mt-3" icon={<Plus className="h-4 w-4" />} onClick={addRule}>
            Add rule
          </IosButton>
        </ListSection>

        {/* Smart filing — automatic, approval-gated, thread-level. Sits ABOVE the
            hand-written rules because it's what most people will actually use;
            the rules below stay for anyone who wants exact control. */}
        <FoldersSection />

        {/* Filing rules */}
        <ListSection title="Filing rules" footer="Auto-apply a Gmail label to matching mail — and optionally archive it.">
          {labelRules.length > 0 && (
            <ListGroup variant="plain-mobile" className="mb-3">
              {labelRules.map((r) => (
                <ListRow
                  key={r.id}
                  title={<span className={cn(!r.active && 'opacity-50')}>{r.name}</span>}
                  subtitle={
                    <span className={cn(!r.active && 'opacity-50')}>
                      {MATCH_LABEL[r.match_type]} {r.match_value} → {r.target_label}
                      {r.archive_after ? ' · archive' : ''}
                    </span>
                  }
                  trailing={
                    <>
                      <Toggle checked={r.active} onChange={() => void flipLabelRule(r.id)} aria-label="Rule active" />
                      <DeleteButton label="Delete filing rule" onClick={() => void removeLabelRule(r.id)} />
                    </>
                  }
                />
              ))}
            </ListGroup>
          )}
          <ListGroup variant="plain-mobile">
            <FieldCell label="Name">
              <input className={inputCls} value={lName} placeholder="Newsletters" onChange={(e) => setLName(e.target.value)} />
            </FieldCell>
            <FieldCell label="Match on">
              <select className={inputCls} value={lMatch} onChange={(e) => setLMatch(e.target.value as LabelMatchType)}>
                <option value="sender">Sender</option>
                <option value="domain">Domain</option>
                <option value="subject_keyword">Subject keyword</option>
              </select>
            </FieldCell>
            <FieldCell label="Value">
              <input className={inputCls} value={lValue} placeholder="news@substack.com" onChange={(e) => setLValue(e.target.value)} />
            </FieldCell>
            <FieldCell label="Apply label">
              <input className={inputCls} value={lLabel} placeholder="Reading" onChange={(e) => setLLabel(e.target.value)} />
            </FieldCell>
            <ListRow
              title="Archive after labeling"
              trailing={<Toggle checked={lArchive} onChange={setLArchive} aria-label="Archive after labeling" />}
            />
          </ListGroup>
          <IosButton variant="filled" full className="mt-3" icon={<Plus className="h-4 w-4" />} onClick={addLabelRule}>
            Add filing rule
          </IosButton>
        </ListSection>
      </Screen>
    </>
  );
}
