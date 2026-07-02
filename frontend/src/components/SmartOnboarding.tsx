import { useEffect, useMemo, useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import {
  Sparkles,
  Loader2,
  Bell,
  Tag,
  Check,
  ArrowRight,
  ArrowLeft,
  Wand2,
  Inbox as InboxIcon,
  Mail,
  MessageSquare,
  Plug,
  RefreshCw,
  Slack as SlackIcon,
} from 'lucide-react';
import { useToast } from '@/components/Toast';
import {
  suggestOnboarding,
  applyOnboarding,
  getRequiredIntegrations,
  getConfig,
  updateConfig,
  toApiError,
  type OnboardingDraft,
  type DraftTriageRule,
  type DraftLabelRule,
  type Tier,
  type RequiredIntegration,
} from '@/lib/api';
import { requestConnectIntegration } from '@/lib/integrations';
import { ConnectButton } from '@/components/ConnectButtons';
import { cn } from '@/lib/utils';

const ROLES = [
  { id: 'founder', label: 'Founder / Exec' },
  { id: 'manager', label: 'Manager' },
  { id: 'individual', label: 'Individual' },
  { id: 'sales', label: 'Sales' },
  { id: 'support', label: 'Support' },
];
const NOISE = [
  { id: 'urgent', label: 'Only urgent' },
  { id: 'balanced', label: 'Balanced' },
  { id: 'everything', label: 'Be generous' },
];

// Firebase-style: amber accent for urgent, neutral for the rest.
const TIER_CHIP: Record<Tier, string> = {
  urgent: 'bg-accent/15 text-accent',
  needs_reply: 'bg-muted text-muted-foreground',
  fyi: 'bg-muted text-muted-foreground',
};
const TIER_LABEL: Record<Tier, string> = { urgent: 'Urgent', needs_reply: 'Reply', fyi: 'FYI' };

const INTEGRATION_META: Record<string, { Icon: typeof Mail; desc: string }> = {
  gmail: { Icon: Mail, desc: 'Read & organize your inbox' },
  slack: { Icon: SlackIcon, desc: 'Send you attention alerts' },
};

type Step = 'context' | 'connect' | 'analyzing' | 'review' | 'settings';
const STEP_ORDER: Step[] = ['context', 'connect', 'review', 'settings'];

export function SmartOnboarding({
  onDone,
  initialRole = '',
  initialIntent = '',
}: {
  onDone: (applied: boolean) => void;
  initialRole?: string;
  initialIntent?: string;
}) {
  const { show } = useToast();
  const [step, setStep] = useState<Step>('context');
  const [role, setRole] = useState(initialRole);
  const [noise, setNoise] = useState('balanced');
  const [description, setDescription] = useState(initialIntent);

  // Integrations
  const [integrations, setIntegrations] = useState<RequiredIntegration[]>([]);
  const [appId, setAppId] = useState<string | null>(null);

  // Draft
  const [draft, setDraft] = useState<OnboardingDraft | null>(null);
  const [grounded, setGrounded] = useState(false);
  const [triOn, setTriOn] = useState<boolean[]>([]);
  const [labOn, setLabOn] = useState<boolean[]>([]);
  const [notify, setNotify] = useState<'urgent' | 'needs_reply'>('urgent');
  const [refineText, setRefineText] = useState('');
  const [refining, setRefining] = useState(false);

  // Settings
  const [slackChannel, setSlackChannel] = useState('');
  const [applying, setApplying] = useState(false);

  useEffect(() => {
    void refreshIntegrations();
    getConfig().then((c) => setSlackChannel(c.slack_channel || '')).catch(() => undefined);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const refreshIntegrations = async () => {
    try {
      const s = await getRequiredIntegrations();
      setIntegrations(s.integrations || []);
      setAppId(s.app_id ?? null);
    } catch {
      /* best-effort */
    }
  };

  // While the connect step is open, auto-detect a completed connection: poll,
  // and re-check whenever the user returns to the tab (after the OAuth popup)
  // or the platform posts an integration message — so the badge flips to
  // "Connected" without a manual "Recheck".
  useEffect(() => {
    if (step !== 'connect') return;
    const poll = () => void refreshIntegrations();
    const iv = window.setInterval(poll, 3000);
    const onVis = () => {
      if (!document.hidden) poll();
    };
    const onMsg = (e: MessageEvent) => {
      const t = (e?.data && (e.data.type || e.data.event)) as string | undefined;
      if (typeof t === 'string' && t.toLowerCase().includes('integration')) poll();
    };
    window.addEventListener('focus', poll);
    document.addEventListener('visibilitychange', onVis);
    window.addEventListener('message', onMsg);
    return () => {
      window.clearInterval(iv);
      window.removeEventListener('focus', poll);
      document.removeEventListener('visibilitychange', onVis);
      window.removeEventListener('message', onMsg);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [step]);

  const loadDraft = (d: OnboardingDraft) => {
    setDraft(d);
    setTriOn(d.triage_rules.map(() => true));
    setLabOn(d.label_rules.map(() => true));
    setNotify(d.notify_tier);
  };

  const analyze = async () => {
    setStep('analyzing');
    try {
      const res = await suggestOnboarding({ description, role, noise, current_draft: null });
      loadDraft(res.draft);
      setGrounded(res.grounded);
      setStep('review');
    } catch (err) {
      show({ tone: 'error', text: `Couldn’t build suggestions: ${toApiError(err).message}` });
      setStep('connect');
    }
  };

  const refine = async () => {
    if (!refineText.trim() || !draft) return;
    setRefining(true);
    const merged = (description ? `${description}\n` : '') + refineText;
    setDescription(merged);
    try {
      const res = await suggestOnboarding({ description: merged, role, noise, current_draft: draft });
      loadDraft(res.draft);
      setGrounded(res.grounded);
      setRefineText('');
    } catch (err) {
      show({ tone: 'error', text: `Couldn’t update: ${toApiError(err).message}` });
    } finally {
      setRefining(false);
    }
  };

  const apply = async () => {
    if (!draft) return;
    setApplying(true);
    const triage_rules = draft.triage_rules.filter((_, i) => triOn[i]);
    const label_rules = draft.label_rules.filter((_, i) => labOn[i]);
    try {
      const res = await applyOnboarding({ triage_rules, label_rules, notify_tier: notify, intent: description, role });
      await updateConfig({ slack_channel: slackChannel, notify_tier: notify }).catch(() => undefined);
      show({
        tone: 'success',
        text: `Sentry is set — ${res.created_rules} watch rule${res.created_rules === 1 ? '' : 's'} and ${res.created_label_rules} filing rule${res.created_label_rules === 1 ? '' : 's'} added.`,
      });
      onDone(true);
    } catch (err) {
      show({ tone: 'error', text: `Couldn’t apply: ${toApiError(err).message}` });
      setApplying(false);
    }
  };

  const skip = async () => {
    try {
      await applyOnboarding({ triage_rules: [], label_rules: [], intent: description, role });
    } catch {
      /* best-effort */
    }
    onDone(false);
  };

  const selectedCount = useMemo(
    () => triOn.filter(Boolean).length + labOn.filter(Boolean).length,
    [triOn, labOn],
  );

  const stepIndex = STEP_ORDER.indexOf(step === 'analyzing' ? 'connect' : step);
  const subtitle =
    step === 'connect'
      ? 'Connect your accounts'
      : step === 'review'
        ? 'Review what I’ll watch — toggle anything off'
        : step === 'settings'
          ? 'Where alerts go'
          : 'A minute to tune what reaches you';

  return (
    <motion.div
      className="fixed inset-0 z-[100] flex bg-background/85 backdrop-blur-2xl sm:items-center sm:justify-center sm:p-4"
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
    >
      <motion.div
        initial={{ opacity: 0, y: 16, scale: 0.98 }}
        animate={{ opacity: 1, y: 0, scale: 1 }}
        transition={{ duration: 0.4, ease: [0.16, 1, 0.3, 1] }}
        className="flex h-full w-full flex-col overflow-hidden bg-card sm:h-auto sm:max-h-[88vh] sm:max-w-lg sm:rounded-4xl sm:shadow-apple-lg sm:ring-1 sm:ring-border/70"
      >
        {/* Header */}
        <div className="flex items-center gap-3 border-b border-border/70 px-7 py-5">
          <div className="min-w-0 flex-1">
            <h1 className="text-[17px] font-semibold tracking-tight text-foreground">Set up your Sentry</h1>
            <p className="truncate text-xs text-muted-foreground">{subtitle}</p>
          </div>
          {/* progress dots */}
          <div className="flex items-center gap-1.5">
            {STEP_ORDER.map((s, i) => (
              <span
                key={s}
                className={cn('h-1.5 rounded-full transition-all', i <= stepIndex ? 'w-4 bg-accent' : 'w-1.5 bg-muted')}
              />
            ))}
          </div>
        </div>

        <div className="min-h-0 flex-1 overflow-y-auto px-7 py-6">
          <AnimatePresence mode="wait">
            {step === 'context' && (
              <motion.div key="context" initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -10 }}>
                <p className="text-[15px] leading-relaxed text-muted-foreground">
                  I’ll read your inbox and propose a setup — you just accept or toggle. Two quick taps make it sharper.
                </p>
                <ChipGroup label="What best describes you?" options={ROLES} value={role} onChange={setRole} />
                <ChipGroup label="How much should I ping you?" options={NOISE} value={noise} onChange={setNoise} />
                <label className="mt-6 block text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                  Anything specific? (optional)
                </label>
                <textarea
                  value={description}
                  onChange={(e) => setDescription(e.target.value)}
                  rows={2}
                  placeholder="e.g. anything from my lawyer, invoices, mute newsletters"
                  className="mt-2 w-full resize-none rounded-2xl border border-border bg-background px-4 py-3 text-sm text-foreground outline-none transition focus:border-accent focus:ring-2 focus:ring-accent/30"
                />
              </motion.div>
            )}

            {step === 'connect' && (
              <motion.div key="connect" initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -10 }}>
                <p className="text-[15px] leading-relaxed text-muted-foreground">
                  Gmail Sentry reads your inbox and pings you on Slack. Connect both to go live — you can also do this
                  later on the Integrations tab.
                </p>
                <div className="mt-5 space-y-3">
                  {(integrations.length ? integrations : [{ id: 'gmail', name: 'Gmail', connected: false }, { id: 'slack', name: 'Slack', connected: false }]).map((it) => {
                    const meta = INTEGRATION_META[it.id] ?? { Icon: Plug, desc: '' };
                    const Icon = meta.Icon;
                    return (
                      <div key={it.id} className="flex flex-col gap-3 rounded-2xl border border-border bg-background p-3.5 sm:flex-row sm:items-center">
                        <div className="flex min-w-0 flex-1 items-center gap-3">
                          <span className="inline-flex h-10 w-10 flex-shrink-0 items-center justify-center rounded-xl bg-muted text-foreground">
                            <Icon className="h-5 w-5" />
                          </span>
                          <div className="min-w-0 flex-1">
                            <div className="text-sm font-semibold text-foreground">{it.name}</div>
                            <div className="truncate text-xs text-muted-foreground">{meta.desc}</div>
                          </div>
                          {it.connected && (
                            <span className="inline-flex flex-shrink-0 items-center gap-1 rounded-full bg-accent/15 px-2.5 py-1 text-xs font-semibold text-accent">
                              <Check className="h-3.5 w-3.5" /> Connected
                            </span>
                          )}
                        </div>
                        {!it.connected && (
                          <ConnectButton
                            integrationId={it.id}
                            className="w-full justify-center sm:w-auto"
                            onClick={() => {
                              const posted = requestConnectIntegration(it.id, appId);
                              show({
                                tone: posted ? 'success' : 'error',
                                text: posted
                                  ? `Opening ${it.name} connection…`
                                  : `Connect ${it.name} on the app’s Integrations tab.`,
                              });
                            }}
                          />
                        )}
                      </div>
                    );
                  })}
                </div>
                <button
                  onClick={() => void refreshIntegrations()}
                  className="mt-3 inline-flex items-center gap-1.5 text-xs font-medium text-muted-foreground transition-colors hover:text-foreground"
                >
                  <RefreshCw className="h-3.5 w-3.5" /> Recheck connections
                </button>
              </motion.div>
            )}

            {step === 'analyzing' && (
              <motion.div key="analyzing" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} className="flex flex-col items-center gap-4 py-14 text-center">
                <span className="relative flex h-14 w-14 items-center justify-center">
                  <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-accent/30" />
                  <span className="relative inline-flex h-14 w-14 items-center justify-center rounded-2xl bg-accent/15 text-accent">
                    <Loader2 className="h-6 w-6 animate-spin" />
                  </span>
                </span>
                <p className="text-[15px] font-semibold text-foreground">Reading your inbox…</p>
                <p className="max-w-xs text-sm text-muted-foreground">Looking at who emails you, what’s noise, and what looks urgent.</p>
              </motion.div>
            )}

            {step === 'review' && draft && (
              <motion.div key="review" initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -10 }} className="space-y-6">
                <div className="flex items-center gap-2 rounded-2xl bg-muted px-3.5 py-2.5 text-xs text-muted-foreground">
                  {grounded ? (
                    <><InboxIcon className="h-3.5 w-3.5 text-accent" /> Grounded in your real inbox.</>
                  ) : (
                    <><Sparkles className="h-3.5 w-3.5 text-accent" /> Suggested from your role — connect Gmail for inbox-grounded rules.</>
                  )}
                </div>

                <Group icon={<Bell className="h-4 w-4" />} title="Watch closely">
                  {draft.triage_rules.map((r, i) => (
                    <ToggleCard
                      key={`t${i}`}
                      on={triOn[i]}
                      onToggle={() => setTriOn((s) => s.map((v, j) => (j === i ? !v : v)))}
                      title={r.name}
                      subtitle={triageSubtitle(r)}
                      reason={r.reason}
                      badge={<span className={cn('rounded-full px-2 py-0.5 text-[10px] font-semibold', TIER_CHIP[r.tier])}>{TIER_LABEL[r.tier]}</span>}
                    />
                  ))}
                  {draft.triage_rules.length === 0 && <Empty text="No watch rules suggested." />}
                </Group>

                <Group icon={<Tag className="h-4 w-4" />} title="Auto-file">
                  {draft.label_rules.map((r, i) => (
                    <ToggleCard
                      key={`l${i}`}
                      on={labOn[i]}
                      onToggle={() => setLabOn((s) => s.map((v, j) => (j === i ? !v : v)))}
                      title={r.name}
                      subtitle={labelSubtitle(r)}
                      reason={r.reason}
                    />
                  ))}
                  {draft.label_rules.length === 0 && <Empty text="No filing rules suggested." />}
                </Group>

                <div className="rounded-2xl border border-dashed border-border p-3">
                  <label className="flex items-center gap-1.5 text-xs font-semibold text-muted-foreground">
                    <Wand2 className="h-3.5 w-3.5 text-accent" /> Adjust in your words
                  </label>
                  <div className="mt-2 flex gap-2">
                    <input
                      value={refineText}
                      onChange={(e) => setRefineText(e.target.value)}
                      onKeyDown={(e) => e.key === 'Enter' && void refine()}
                      placeholder="e.g. also watch the Acme deal; ignore LinkedIn"
                      className="min-w-0 flex-1 rounded-xl border border-border bg-background px-3 py-2 text-sm outline-none focus:border-accent focus:ring-2 focus:ring-accent/30"
                    />
                    <button
                      onClick={() => void refine()}
                      disabled={refining || !refineText.trim()}
                      className="flex-shrink-0 rounded-xl bg-foreground px-3 py-2 text-sm font-semibold text-background transition-opacity disabled:opacity-40"
                    >
                      {refining ? '…' : 'Update'}
                    </button>
                  </div>
                </div>
              </motion.div>
            )}

            {step === 'settings' && (
              <motion.div key="settings" initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -10 }} className="space-y-6">
                <div>
                  <label className="flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                    <MessageSquare className="h-3.5 w-3.5" /> Slack channel
                  </label>
                  <input
                    value={slackChannel}
                    onChange={(e) => setSlackChannel(e.target.value)}
                    placeholder="#gmail-sentry  ·  or your member ID (U0123…)"
                    className="mt-2 w-full rounded-2xl border border-border bg-background px-4 py-3 text-sm text-foreground outline-none transition focus:border-accent focus:ring-2 focus:ring-accent/30"
                  />
                  <p className="mt-1.5 text-xs text-muted-foreground">Where pings land. Leave blank to pause Slack alerts.</p>
                </div>

                <div>
                  <div className="mb-2 text-xs font-semibold uppercase tracking-wider text-muted-foreground">Ping me about</div>
                  <div className="flex gap-2">
                    {(['urgent', 'needs_reply'] as const).map((t) => (
                      <button
                        key={t}
                        onClick={() => setNotify(t)}
                        className={cn(
                          'flex-1 rounded-2xl border px-3 py-2.5 text-sm font-semibold transition-colors',
                          notify === t ? 'border-accent bg-accent/10 text-foreground' : 'border-border text-muted-foreground hover:bg-muted',
                        )}
                      >
                        {t === 'urgent' ? 'Only urgent' : 'Urgent + replies'}
                      </button>
                    ))}
                  </div>
                </div>

                <div className="rounded-2xl bg-muted px-4 py-3 text-xs text-muted-foreground">
                  You’re turning on <span className="font-semibold text-foreground">{selectedCount}</span> rule
                  {selectedCount === 1 ? '' : 's'}. You can tweak everything later on the Rules page.
                </div>
              </motion.div>
            )}
          </AnimatePresence>
        </div>

        {/* Footer actions */}
        <div className="flex items-center justify-between gap-3 border-t border-border/70 px-7 py-4">
          {step === 'context' || step === 'analyzing' ? (
            <button onClick={() => void skip()} className="text-sm font-medium text-muted-foreground transition-colors hover:text-foreground">
              Skip
            </button>
          ) : (
            <button
              onClick={() => setStep(step === 'connect' ? 'context' : step === 'review' ? 'connect' : 'review')}
              className="inline-flex items-center gap-1.5 text-sm font-medium text-muted-foreground transition-colors hover:text-foreground"
            >
              <ArrowLeft className="h-4 w-4" /> Back
            </button>
          )}

          {step === 'context' && (
            <PrimaryBtn onClick={() => setStep('connect')}>Next <ArrowRight className="h-4 w-4" /></PrimaryBtn>
          )}
          {step === 'connect' && (
            <PrimaryBtn onClick={() => void analyze()}><Sparkles className="h-4 w-4" /> Analyze & suggest</PrimaryBtn>
          )}
          {step === 'analyzing' && <span className="text-sm text-muted-foreground">Working…</span>}
          {step === 'review' && (
            <PrimaryBtn onClick={() => setStep('settings')} disabled={selectedCount === 0}>
              Next <ArrowRight className="h-4 w-4" />
            </PrimaryBtn>
          )}
          {step === 'settings' && (
            <PrimaryBtn onClick={() => void apply()} disabled={applying || selectedCount === 0}>
              {applying ? <Loader2 className="h-4 w-4 animate-spin" /> : <Check className="h-4 w-4" />} Turn on Sentry
            </PrimaryBtn>
          )}
        </div>
      </motion.div>
    </motion.div>
  );
}

function PrimaryBtn({ children, onClick, disabled }: { children: React.ReactNode; onClick: () => void; disabled?: boolean }) {
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      className="inline-flex items-center gap-2 rounded-full bg-accent px-5 py-2.5 text-sm font-semibold text-accent-foreground shadow-apple transition-all hover:bg-accent-600 active:scale-[0.98] disabled:opacity-50"
    >
      {children}
    </button>
  );
}

function triageSubtitle(r: DraftTriageRule): string {
  if (r.kind === 'vip_sender') return `Sender · ${r.value}`;
  if (r.kind === 'keyword') return `Keyword · “${r.value}”`;
  return r.value;
}
function labelSubtitle(r: DraftLabelRule): string {
  const where = r.match_type === 'subject_keyword' ? 'Subject' : r.match_type === 'domain' ? 'Domain' : 'Sender';
  return `${where} ${r.match_value} → ${r.target_label}${r.archive_after ? ' · archive' : ''}`;
}

function ChipGroup({
  label,
  options,
  value,
  onChange,
}: {
  label: string;
  options: { id: string; label: string }[];
  value: string;
  onChange: (v: string) => void;
}) {
  return (
    <div className="mt-6">
      <div className="mb-2 text-xs font-semibold uppercase tracking-wider text-muted-foreground">{label}</div>
      <div className="flex flex-wrap gap-2">
        {options.map((o) => (
          <button
            key={o.id}
            onClick={() => onChange(o.id)}
            className={cn(
              'rounded-full border px-3.5 py-1.5 text-sm font-medium transition-all active:scale-95',
              value === o.id ? 'border-accent bg-accent/10 text-foreground' : 'border-border text-muted-foreground hover:bg-muted',
            )}
          >
            {o.label}
          </button>
        ))}
      </div>
    </div>
  );
}

function Group({ icon, title, children }: { icon: React.ReactNode; title: string; children: React.ReactNode }) {
  return (
    <div>
      <h3 className="mb-2 flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wider text-muted-foreground">
        {icon} {title}
      </h3>
      <div className="space-y-2">{children}</div>
    </div>
  );
}

function ToggleCard({
  on,
  onToggle,
  title,
  subtitle,
  reason,
  badge,
}: {
  on: boolean;
  onToggle: () => void;
  title: string;
  subtitle: string;
  reason?: string;
  badge?: React.ReactNode;
}) {
  return (
    <button
      onClick={onToggle}
      className={cn(
        'flex w-full items-start gap-3 rounded-2xl border p-3 text-left transition-all',
        on ? 'border-accent/40 bg-accent/[0.06]' : 'border-border bg-background opacity-60 hover:opacity-100',
      )}
    >
      <span
        className={cn(
          'mt-0.5 flex h-5 w-5 flex-shrink-0 items-center justify-center rounded-full border-2 transition-colors',
          on ? 'border-accent bg-accent text-accent-foreground' : 'border-border',
        )}
      >
        {on && <Check className="h-3 w-3" />}
      </span>
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2">
          <span className="truncate text-sm font-semibold text-foreground">{title}</span>
          {badge}
        </div>
        <div className="truncate text-xs text-muted-foreground">{subtitle}</div>
        {reason && <div className="mt-0.5 truncate text-[11px] italic text-muted-foreground/80">{reason}</div>}
      </div>
    </button>
  );
}

function Empty({ text }: { text: string }) {
  return <p className="rounded-2xl border border-dashed border-border px-3 py-3 text-xs text-muted-foreground">{text}</p>;
}

export default SmartOnboarding;
