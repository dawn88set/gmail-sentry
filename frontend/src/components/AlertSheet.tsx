import { useEffect, useState, useRef } from 'react';
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
  Send,
  Wand2,
} from 'lucide-react';
import { Avatar, parseSender } from '@/components/Avatar';
import { ActionTile } from '@/components/ios/ActionTile';
import { useToast } from '@/components/Toast';
import { DraftRefiner } from '@/components/DraftRefiner';
import {
  doneAlert,
  snoozeAlert,
  muteAlert,
  dismissAlert,
  draftReplyAlert,
  sendReply,
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
  autoReply = false,
}: {
  alert: Alert;
  onClose: () => void;
  onChanged: () => void;
  /** Open straight into the reply (used by the notification approve deep link). */
  autoReply?: boolean;
}) {
  const { show } = useToast();
  const who = parseSender(alert.sender || '');
  const [busy, setBusy] = useState<string | null>(null);
  const [snoozeOpen, setSnoozeOpen] = useState(false);
  const [draft, setDraft] = useState<{ url: string; voice: boolean } | null>(null);
  const [replyText, setReplyText] = useState('');
  // The refiner reads the caret/selection to rewrite just the highlighted part.
  const replyRef = useRef<HTMLTextAreaElement>(null);
  const [intent, setIntent] = useState('');

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

  const composeUrl = () => {
    const to = who.email || '';
    const su = (alert.subject || '').toLowerCase().startsWith('re:')
      ? alert.subject || ''
      : `Re: ${alert.subject || ''}`.trim();
    return `https://mail.google.com/mail/?view=cm&fs=1&to=${encodeURIComponent(to)}&su=${encodeURIComponent(
      su,
    )}&body=${encodeURIComponent(replyText)}`;
  };

  const genReply = async (note?: string) => {
    setBusy('reply');
    try {
      const res = await draftReplyAlert(alert.id, note?.trim() || undefined);
      setReplyText(res.draft);
      setDraft({ url: res.compose_url, voice: res.voice_matched });
    } catch (err) {
      show({ tone: 'error', text: `Couldn’t draft a reply: ${toApiError(err).message}` });
    } finally {
      setBusy(null);
    }
  };

  const approveSend = async () => {
    if (!replyText.trim()) return;
    setBusy('send');
    try {
      await sendReply(alert.id, replyText);
      show({ tone: 'success', text: 'Reply sent ✓' });
      onChanged();
      onClose();
    } catch (err) {
      const e = toApiError(err);
      show({
        tone: 'error',
        text:
          e.status === 409
            ? 'Connect Gmail, then try again.'
            : `Couldn’t send the reply: ${e.message}`,
      });
      setBusy(null);
    }
  };

  // Preload a persisted draft (or auto-open the reply when arriving via the
  // notification approve deep link).
  useEffect(() => {
    if (alert.reply_draft) {
      setReplyText(alert.reply_draft);
      setDraft({ url: '', voice: false });
    } else if (autoReply) {
      void genReply();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const alreadySent = alert.reply_status === 'sent';

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

        {/* AI draft — editable, approve & send in-app */}
        {alreadySent ? (
          <div className="mt-4 flex items-center gap-2 rounded-2xl border border-border bg-background px-3 py-2.5 text-[13px] font-medium text-muted-foreground">
            <Check className="h-4 w-4 text-success" /> Reply sent
          </div>
        ) : (
          draft && (
            <div className="mt-4 rounded-2xl border border-border bg-background p-3">
              <div className="mb-1.5 text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
                Suggested reply{draft.voice ? ' · in your voice' : ''}
              </div>

              {/* Scrappy note → polished email in your voice */}
              <div className="mb-2 flex gap-2">
                <input
                  value={intent}
                  onChange={(e) => setIntent(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter') {
                      e.preventDefault();
                      void genReply(intent);
                    }
                  }}
                  placeholder="Tell me what to say — e.g. “Tuesday works, ask for the deck”"
                  className="min-w-0 flex-1 rounded-lg border border-border bg-card px-2.5 py-1.5 text-[13px] text-foreground outline-none placeholder:text-muted-foreground/70 focus:ring-2 focus:ring-accent/40"
                />
                <button
                  onClick={() => void genReply(intent)}
                  disabled={busy === 'reply'}
                  title="Write it in your voice"
                  className="inline-flex flex-shrink-0 items-center gap-1.5 rounded-lg border border-border px-2.5 py-1.5 text-[13px] font-semibold text-foreground transition-colors hover:bg-muted disabled:opacity-50"
                >
                  {busy === 'reply' ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Wand2 className="h-3.5 w-3.5" />}
                  Write it
                </button>
              </div>

              <textarea
                ref={replyRef}
                value={replyText}
                onChange={(e) => setReplyText(e.target.value)}
                rows={5}
                className="w-full resize-y rounded-xl border border-border bg-card px-3 py-2 text-[14px] leading-relaxed text-foreground outline-none focus:ring-2 focus:ring-accent/40"
                placeholder="Write your reply…"
              />
              <DraftRefiner
                value={replyText}
                onChange={setReplyText}
                textareaRef={replyRef}
                context={alert.subject || ''}
                disabled={busy !== null}
              />
              <div className="mt-3 flex gap-2">
                <button
                  onClick={() => void approveSend()}
                  disabled={busy === 'send' || !replyText.trim()}
                  className="inline-flex flex-1 items-center justify-center gap-2 rounded-xl bg-accent px-4 py-2.5 text-sm font-semibold text-accent-foreground disabled:opacity-50"
                >
                  {busy === 'send' ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}
                  Approve &amp; Send
                </button>
                <button
                  onClick={() => window.open(composeUrl(), '_blank', 'noopener')}
                  title="Open in Gmail instead"
                  className="inline-flex items-center justify-center rounded-xl border border-border px-3 py-2.5 text-sm font-medium text-foreground hover:bg-muted"
                >
                  <ExternalLink className="h-4 w-4" />
                </button>
                <button
                  onClick={() => {
                    navigator.clipboard?.writeText(replyText);
                    show({ tone: 'success', text: 'Reply copied.' });
                  }}
                  title="Copy"
                  className="inline-flex items-center justify-center rounded-xl border border-border px-3 py-2.5 text-sm font-medium text-foreground hover:bg-muted"
                >
                  <Copy className="h-4 w-4" />
                </button>
              </div>
            </div>
          )
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
          <ActionTile icon={<ExternalLink className="h-5 w-5" />} label="Open" onClick={() => alert.deep_link && window.open(alert.deep_link, '_blank', 'noopener')} />
          <ActionTile icon={busy === 'reply' ? <Loader2 className="h-5 w-5 animate-spin" /> : <CornerUpLeft className="h-5 w-5" />} label="Reply" onClick={() => void genReply()} />
          <ActionTile icon={<Clock className="h-5 w-5" />} label="Snooze" active={snoozeOpen} onClick={() => setSnoozeOpen((v) => !v)} />
          <ActionTile icon={busy === 'done' ? <Loader2 className="h-5 w-5 animate-spin" /> : <Check className="h-5 w-5" />} label="Done" onClick={() => void run('done', () => doneAlert(alert.id))} />
          <ActionTile icon={busy === 'mute' ? <Loader2 className="h-5 w-5 animate-spin" /> : <BellOff className="h-5 w-5" />} label="Mute sender" onClick={() => void run('mute', () => muteAlert(alert.id))} />
          <ActionTile icon={<Plus className="h-5 w-5" />} label="Make rule" onClick={() => void run('rule', () => createRuleFromAlert(alert.id, alert.tier === 'urgent' ? 'urgent' : 'needs_reply'), false).then(() => show({ tone: 'success', text: 'Rule created from this sender.' }))} />
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

export default AlertSheet;
