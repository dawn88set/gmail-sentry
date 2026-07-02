import { useState } from 'react';
import { motion } from 'framer-motion';
import {
  X,
  ExternalLink,
  CornerUpLeft,
  Clock,
  Check,
  BellOff,
  Plus,
  Loader2,
  Copy,
} from 'lucide-react';
import { Avatar, parseSender } from '@/components/Avatar';
import { useToast } from '@/components/Toast';
import {
  doneAlert,
  snoozeAlert,
  muteAlert,
  dismissAlert,
  draftReplyAlert,
  createRuleFromAlert,
  toApiError,
  type Alert,
  type Tier,
} from '@/lib/api';
import { cn } from '@/lib/utils';

const TIER_CHIP: Record<Tier, string> = {
  urgent: 'bg-accent/15 text-accent',
  needs_reply: 'bg-muted text-muted-foreground',
  fyi: 'bg-muted text-muted-foreground',
};
const TIER_LABEL: Record<Tier, string> = { urgent: 'Urgent', needs_reply: 'Needs reply', fyi: 'FYI' };
const SNOOZE = [
  { label: '3 hours', hours: 3 },
  { label: 'Tomorrow', hours: 18 },
  { label: 'Next week', hours: 168 },
];

export function AlertSheet({
  alert,
  onClose,
  onChanged,
}: {
  alert: Alert;
  onClose: () => void;
  onChanged: () => void;
}) {
  const { show } = useToast();
  const who = parseSender(alert.sender || '');
  const [busy, setBusy] = useState<string | null>(null);
  const [snoozeOpen, setSnoozeOpen] = useState(false);
  const [draft, setDraft] = useState<{ text: string; url: string; voice: boolean } | null>(null);

  const run = async (key: string, fn: () => Promise<unknown>, close = true) => {
    setBusy(key);
    try {
      await fn();
      onChanged();
      if (close) onClose();
    } catch (err) {
      const e = toApiError(err);
      show({
        tone: 'error',
        text: e.status === 409 ? 'Connect Gmail/Slack, then try again.' : `Couldn’t do that: ${e.message}`,
      });
      setBusy(null);
    }
  };

  const genReply = async () => {
    setBusy('reply');
    try {
      const res = await draftReplyAlert(alert.id);
      setDraft({ text: res.draft, url: res.compose_url, voice: res.voice_matched });
    } catch (err) {
      show({ tone: 'error', text: `Couldn’t draft a reply: ${toApiError(err).message}` });
    } finally {
      setBusy(null);
    }
  };

  return (
    <motion.div
      className="fixed inset-0 z-[90] flex items-end justify-center bg-black/50 backdrop-blur-sm sm:items-center sm:p-4"
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      onClick={onClose}
    >
      <motion.div
        onClick={(e) => e.stopPropagation()}
        initial={{ y: 60, opacity: 0.6 }}
        animate={{ y: 0, opacity: 1 }}
        exit={{ y: 60, opacity: 0 }}
        transition={{ duration: 0.32, ease: [0.16, 1, 0.3, 1] }}
        className="max-h-[88vh] w-full overflow-y-auto rounded-t-3xl bg-card p-5 shadow-apple-lg ring-1 ring-border/70 sm:max-w-md sm:rounded-3xl"
      >
        {/* Header */}
        <div className="flex items-start gap-3">
          <Avatar name={who.name} email={who.email} className="h-11 w-11 flex-shrink-0 text-base" />
          <div className="min-w-0 flex-1">
            <div className="flex items-center gap-2">
              <span className={cn('rounded-full px-2 py-0.5 text-[10px] font-semibold', TIER_CHIP[alert.tier])}>
                {TIER_LABEL[alert.tier]}
              </span>
            </div>
            <h2 className="mt-1 text-[17px] font-semibold leading-snug text-foreground">
              {alert.subject || '(no subject)'}
            </h2>
            <p className="truncate text-[13px] text-muted-foreground">{alert.sender}</p>
          </div>
          <button
            onClick={onClose}
            aria-label="Close"
            className="inline-flex h-8 w-8 flex-shrink-0 items-center justify-center rounded-full text-muted-foreground hover:bg-muted"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        {alert.reason && (
          <div className="mt-3 rounded-xl bg-accent/10 px-3 py-2 text-[13px] text-accent">
            Why flagged: {alert.reason}
          </div>
        )}
        {alert.snippet && (
          <p className="mt-3 line-clamp-4 text-[14px] leading-relaxed text-muted-foreground">{alert.snippet}</p>
        )}

        {/* AI draft */}
        {draft && (
          <div className="mt-4 rounded-2xl border border-border bg-background p-3">
            <div className="mb-1 text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
              Suggested reply{draft.voice ? ' · in your voice' : ''}
            </div>
            <p className="whitespace-pre-wrap text-[14px] leading-relaxed text-foreground">{draft.text}</p>
            <div className="mt-3 flex gap-2">
              <button
                onClick={() => window.open(draft.url, '_blank', 'noopener')}
                className="inline-flex flex-1 items-center justify-center gap-2 rounded-xl bg-accent px-4 py-2.5 text-sm font-semibold text-accent-foreground"
              >
                <ExternalLink className="h-4 w-4" /> Open in Gmail
              </button>
              <button
                onClick={() => {
                  navigator.clipboard?.writeText(draft.text);
                  show({ tone: 'success', text: 'Reply copied.' });
                }}
                className="inline-flex items-center justify-center rounded-xl border border-border px-3 py-2.5 text-sm font-medium text-foreground hover:bg-muted"
              >
                <Copy className="h-4 w-4" />
              </button>
            </div>
          </div>
        )}

        {/* Snooze options */}
        {snoozeOpen && (
          <div className="mt-4 flex gap-2">
            {SNOOZE.map((s) => (
              <button
                key={s.hours}
                onClick={() => void run('snooze', () => snoozeAlert(alert.id, s.hours))}
                className="flex-1 rounded-xl border border-border bg-background px-3 py-2.5 text-sm font-medium text-foreground hover:bg-muted"
              >
                {s.label}
              </button>
            ))}
          </div>
        )}

        {/* Actions */}
        <div className="mt-4 grid grid-cols-3 gap-2">
          <Action icon={<ExternalLink className="h-5 w-5" />} label="Open" onClick={() => alert.deep_link && window.open(alert.deep_link, '_blank', 'noopener')} />
          <Action icon={busy === 'reply' ? <Loader2 className="h-5 w-5 animate-spin" /> : <CornerUpLeft className="h-5 w-5" />} label="Reply" onClick={() => void genReply()} />
          <Action icon={<Clock className="h-5 w-5" />} label="Snooze" active={snoozeOpen} onClick={() => setSnoozeOpen((v) => !v)} />
          <Action icon={busy === 'done' ? <Loader2 className="h-5 w-5 animate-spin" /> : <Check className="h-5 w-5" />} label="Done" onClick={() => void run('done', () => doneAlert(alert.id))} />
          <Action icon={busy === 'mute' ? <Loader2 className="h-5 w-5 animate-spin" /> : <BellOff className="h-5 w-5" />} label="Mute sender" onClick={() => void run('mute', () => muteAlert(alert.id))} />
          <Action icon={<Plus className="h-5 w-5" />} label="Make rule" onClick={() => void run('rule', () => createRuleFromAlert(alert.id, alert.tier === 'urgent' ? 'urgent' : 'needs_reply'), false).then(() => show({ tone: 'success', text: 'Rule created from this sender.' }))} />
        </div>

        <button
          onClick={() => void run('dismiss', () => dismissAlert(alert.id))}
          className="mt-3 w-full rounded-xl px-4 py-2.5 text-sm font-medium text-muted-foreground hover:bg-muted"
        >
          Dismiss — not urgent
        </button>
      </motion.div>
    </motion.div>
  );
}

function Action({
  icon,
  label,
  onClick,
  active,
}: {
  icon: React.ReactNode;
  label: string;
  onClick: () => void;
  active?: boolean;
}) {
  return (
    <button
      onClick={onClick}
      className={cn(
        'flex flex-col items-center justify-center gap-1.5 rounded-2xl border px-2 py-3 text-[12px] font-medium transition-colors',
        active ? 'border-accent bg-accent/10 text-accent' : 'border-border bg-background text-foreground hover:bg-muted',
      )}
    >
      {icon}
      <span className="text-center leading-tight">{label}</span>
    </button>
  );
}

export default AlertSheet;
