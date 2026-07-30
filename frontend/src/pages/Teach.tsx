import { useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Sparkles, Send, Loader2, RefreshCw, Check, Users, ChevronLeft } from 'lucide-react';
import { Screen } from '@/components/ios/Screen';
import { useToast } from '@/components/Toast';
import {
  suggestOnboarding,
  applyOnboarding,
  getProfile,
  learnProfile,
  toApiError,
  type OnboardingDraft,
  type CommProfile,
  type Tier,
} from '@/lib/api';
import { cn } from '@/lib/utils';

type Msg = { role: 'you' | 'sentry'; text: string };

const TIER_CHIP: Record<Tier, string> = {
  urgent: 'bg-accent/15 text-accent',
  needs_reply: 'bg-muted text-muted-foreground',
  fyi: 'bg-muted text-muted-foreground',
};
const TIER_LABEL: Record<Tier, string> = { urgent: 'Urgent', needs_reply: 'Reply', fyi: 'FYI' };

const QUICK = [
  'Ping me for anything from investors or my lawyer',
  'Always draft a warm, brief reply',
  'Mute newsletters and promotions',
  'Flag invoices and payments as urgent',
];

function relTime(iso: string | null): string {
  if (!iso) return 'never';
  const t = new Date(iso.endsWith('Z') || iso.includes('+') ? iso : `${iso}Z`).getTime();
  if (Number.isNaN(t)) return '';
  const s = Math.max(0, Math.floor((Date.now() - t) / 1000));
  if (s < 60) return 'just now';
  if (s < 3600) return `${Math.floor(s / 60)}m ago`;
  if (s < 86400) return `${Math.floor(s / 3600)}h ago`;
  return `${Math.floor(s / 86400)}d ago`;
}

export default function Teach() {
  const { show } = useToast();
  const navigate = useNavigate();
  const [messages, setMessages] = useState<Msg[]>([]);
  const [draft, setDraft] = useState<OnboardingDraft | null>(null);
  const [input, setInput] = useState('');
  const [sending, setSending] = useState(false);
  const [applying, setApplying] = useState(false);
  const [profile, setProfile] = useState<CommProfile | null>(null);
  const [learning, setLearning] = useState(false);
  const endRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    void getProfile()
      .then(setProfile)
      .catch(() => {});
  }, []);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' });
  }, [messages, draft]);

  const ask = async (text: string) => {
    const q = text.trim();
    if (!q || sending) return;
    setInput('');
    setMessages((m) => [...m, { role: 'you', text: q }]);
    setSending(true);
    try {
      const res = await suggestOnboarding({ description: q, current_draft: draft });
      setDraft(res.draft);
      const nRules = res.draft.triage_rules.length + res.draft.label_rules.length;
      setMessages((m) => [
        ...m,
        {
          role: 'sentry',
          text:
            res.draft.summary ||
            (nRules ? `I put together ${nRules} rule${nRules === 1 ? '' : 's'} — review and apply below.` : 'Got it.'),
        },
      ]);
    } catch (err) {
      show({ tone: 'error', text: `Couldn’t reach Sentry: ${toApiError(err).message}` });
    } finally {
      setSending(false);
    }
  };

  const apply = async () => {
    if (!draft) return;
    setApplying(true);
    try {
      const res = await applyOnboarding({
        triage_rules: draft.triage_rules,
        label_rules: draft.label_rules,
        notify_tier: draft.notify_tier,
        intent: messages.filter((m) => m.role === 'you').map((m) => m.text).join(' · '),
      });
      const total = res.created_rules + res.created_label_rules;
      show({ tone: 'success', text: `Saved ${total} rule${total === 1 ? '' : 's'} ✓` });
      setMessages((m) => [
        ...m,
        { role: 'sentry', text: `Done — ${total} rule${total === 1 ? '' : 's'} are now active. Tell me anything else to watch for.` },
      ]);
      setDraft(null);
    } catch (err) {
      show({ tone: 'error', text: `Couldn’t save: ${toApiError(err).message}` });
    } finally {
      setApplying(false);
    }
  };

  const relearn = async () => {
    setLearning(true);
    try {
      setProfile(await learnProfile());
      show({ tone: 'success', text: 'Re-learned your patterns ✓' });
    } catch (err) {
      const e = toApiError(err);
      show({
        tone: 'error',
        text: e.status === 409 ? 'Connect Gmail, then try again.' : `Couldn’t learn: ${e.message}`,
      });
    } finally {
      setLearning(false);
    }
  };

  const hasProposal = !!draft && (draft.triage_rules.length > 0 || draft.label_rules.length > 0);

  return (
    <Screen
      title="Teach Sentry"
      action={
        <button
          onClick={() => navigate('/rules')}
          className="inline-flex items-center gap-1 text-[15px] font-medium text-accent transition-opacity hover:opacity-80"
        >
          <ChevronLeft className="h-4 w-4" /> Rules
        </button>
      }
    >
      {/* Intro */}
      <div className="rounded-3xl bg-accent/10 p-5 ring-1 ring-accent/15">
        <div className="mb-2 inline-flex h-10 w-10 items-center justify-center rounded-2xl bg-accent/15">
          <Sparkles className="h-5 w-5 text-accent" />
        </div>
        <h2 className="text-[17px] font-semibold text-foreground">Tell Sentry what matters</h2>
        <p className="mt-1 text-[14px] leading-relaxed text-muted-foreground">
          Say it in plain language — who to always surface, what to mute, how you want replies to sound. Sentry turns
          it into rules, grounded in your real inbox. Come back anytime to refine.
        </p>
        <div className="mt-3 flex flex-wrap gap-2">
          {QUICK.map((q) => (
            <button
              key={q}
              onClick={() => void ask(q)}
              disabled={sending}
              className="rounded-full border border-border bg-card px-3 py-1.5 text-[12.5px] font-medium text-foreground transition-colors hover:bg-muted disabled:opacity-50"
            >
              {q}
            </button>
          ))}
        </div>
      </div>

      {/* Transcript */}
      {messages.length > 0 && (
        <div className="space-y-3">
          {messages.map((m, i) => (
            <div key={i} className={cn('flex', m.role === 'you' ? 'justify-end' : 'justify-start')}>
              <div
                className={cn(
                  'max-w-[85%] rounded-2xl px-4 py-2.5 text-[14px] leading-relaxed',
                  m.role === 'you'
                    ? 'bg-accent text-accent-foreground'
                    : 'bg-card text-foreground ring-1 ring-border',
                )}
              >
                {m.text}
              </div>
            </div>
          ))}

          {/* Proposed changes */}
          {hasProposal && draft && (
            <div className="rounded-2xl border border-accent/30 bg-card p-4">
              <div className="mb-2 text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
                Proposed
              </div>
              <div className="space-y-1.5">
                {draft.triage_rules.map((r, i) => (
                  <div key={`t${i}`} className="flex items-center gap-2 text-[13.5px]">
                    <span className={cn('flex-shrink-0 rounded-full px-1.5 py-0.5 text-[10px] font-semibold', TIER_CHIP[r.tier])}>
                      {TIER_LABEL[r.tier]}
                    </span>
                    <span className="min-w-0 flex-1 truncate text-foreground">{r.name}</span>
                  </div>
                ))}
                {draft.label_rules.map((r, i) => (
                  <div key={`l${i}`} className="flex items-center gap-2 text-[13.5px]">
                    <span className="flex-shrink-0 rounded-full bg-muted px-1.5 py-0.5 text-[10px] font-semibold text-muted-foreground">
                      File
                    </span>
                    <span className="min-w-0 flex-1 truncate text-foreground">
                      {r.name} → {r.target_label}
                    </span>
                  </div>
                ))}
              </div>
              <button
                onClick={() => void apply()}
                disabled={applying}
                className="mt-3 inline-flex w-full items-center justify-center gap-2 rounded-xl bg-accent px-4 py-2.5 text-sm font-semibold text-accent-foreground disabled:opacity-50"
              >
                {applying ? <Loader2 className="h-4 w-4 animate-spin" /> : <Check className="h-4 w-4" />}
                Apply these rules
              </button>
            </div>
          )}
          <div ref={endRef} />
        </div>
      )}

      {/* Composer */}
      <div className="rounded-2xl border border-border bg-card p-2">
        <textarea
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) {
              e.preventDefault();
              void ask(input);
            }
          }}
          rows={2}
          placeholder="e.g. anything from my lawyer is urgent, and mute receipts…"
          className="w-full resize-y rounded-xl bg-transparent px-3 py-2 text-[14px] leading-relaxed text-foreground outline-none placeholder:text-muted-foreground/70"
        />
        <div className="flex items-center justify-between px-1">
          <span className="text-[11px] text-muted-foreground">⌘↵ to send</span>
          <button
            onClick={() => void ask(input)}
            disabled={sending || !input.trim()}
            className="inline-flex items-center gap-2 rounded-xl bg-accent px-4 py-2 text-sm font-semibold text-accent-foreground disabled:opacity-50"
          >
            {sending ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}
            Send
          </button>
        </div>
      </div>

      {/* What I've learned about you */}
      <div className="rounded-2xl border border-border bg-card p-4">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Users className="h-4 w-4 text-muted-foreground" />
            <h3 className="text-[15px] font-semibold text-foreground">What I’ve learned about you</h3>
          </div>
          <button
            onClick={() => void relearn()}
            disabled={learning}
            className="inline-flex items-center gap-1.5 rounded-lg border border-border px-2.5 py-1.5 text-[12.5px] font-medium text-foreground transition-colors hover:bg-muted disabled:opacity-50"
          >
            {learning ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <RefreshCw className="h-3.5 w-3.5" />}
            Re-learn
          </button>
        </div>

        {profile && (profile.tone || profile.vip_senders.length > 0) ? (
          <div className="mt-3 space-y-3">
            {profile.tone && (
              <div>
                <div className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
                  Your reply voice
                </div>
                <p className="mt-0.5 text-[14px] text-foreground">{profile.tone}</p>
              </div>
            )}
            {profile.vip_senders.length > 0 && (
              <div>
                <div className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
                  People you actually correspond with
                </div>
                <div className="mt-1.5 flex flex-wrap gap-1.5">
                  {profile.vip_senders.slice(0, 8).map((v) => (
                    <span
                      key={v.email}
                      className="rounded-full bg-muted px-2.5 py-1 text-[12px] font-medium text-foreground"
                    >
                      {v.name || v.email}
                    </span>
                  ))}
                </div>
              </div>
            )}
            <p className="text-[11px] text-muted-foreground">Refreshed {relTime(profile.refreshed_at)}.</p>
          </div>
        ) : (
          <p className="mt-2 text-[13.5px] leading-relaxed text-muted-foreground">
            Nothing learned yet. Hit <span className="font-medium text-foreground">Re-learn</span> and I’ll study your
            sent mail to match your voice and spot the people you really talk to. (Needs Gmail connected.)
          </p>
        )}
      </div>
    </Screen>
  );
}
