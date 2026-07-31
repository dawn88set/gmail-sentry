import { useCallback, useEffect, useState } from 'react';
import { Send, Loader2, Sparkles } from 'lucide-react';
import { Button } from '@clarittyai/app-ui';
import { useToast } from '@/components/Toast';
import {
  getNudge,
  draftNudge,
  sendNudge,
  toApiError,
  type FollowUp,
  type Nudge,
} from '@/lib/api';

const TONES: { value: 'gentle' | 'direct' | 'closing'; label: string }[] = [
  { value: 'gentle', label: 'Gentle' },
  { value: 'direct', label: 'Direct' },
  { value: 'closing', label: 'Close it out' },
];

/**
 * Approving a nudge.
 *
 * A reply answers a message that's on screen; a nudge answers silence. The user
 * never saw anything prompting it, so this composer does several things the
 * reply composer doesn't need to:
 *
 *  - shows the missing half — how long it's been, and what was last asked —
 *    because otherwise the user is approving a message into a void;
 *  - never pre-generates: the draft appears only when asked for;
 *  - names the recipient on the button, so a mis-tap is legible *before* it
 *    happens rather than after;
 *  - arms before sending, since this is the one irreversible action here;
 *  - shows the rate limit instead of silently disabling the button — a dead
 *    control reads as broken, an explained one reads as careful.
 *
 * Tone is three chips rather than free text: a nudge is a narrow genre, and an
 * open box invites over-writing something that works best short.
 */
export function NudgeComposer({
  followUp,
  onSent,
}: {
  followUp: FollowUp;
  onSent: () => void;
}) {
  const { show } = useToast();
  const [nudge, setNudge] = useState<Nudge | null>(null);
  const [body, setBody] = useState('');
  const [blocked, setBlocked] = useState('');
  const [drafting, setDrafting] = useState(false);
  const [sending, setSending] = useState(false);
  const [armed, setArmed] = useState(false);

  const load = useCallback(async () => {
    try {
      const d = await getNudge(followUp.id);
      setBlocked(d.blocked_reason || '');
      // An existing proposal is shown, but one is never CREATED on load — that
      // would be pre-generating, and a ready-to-send nudge nobody asked for is
      // a mis-tap away from an unrequested email to a client.
      if (d.nudge) {
        setNudge(d.nudge);
        setBody(d.nudge.draft);
      }
    } catch {
      /* the sheet still works without it */
    }
  }, [followUp.id]);

  useEffect(() => {
    void load();
  }, [load]);

  // Re-arm from scratch whenever the text changes — an armed button must always
  // refer to the words currently on screen.
  useEffect(() => setArmed(false), [body]);

  const draft = async (tone?: 'gentle' | 'direct' | 'closing') => {
    setDrafting(true);
    try {
      const d = await draftNudge(followUp.id, tone);
      setNudge(d.nudge);
      setBody(d.nudge.draft);
      setBlocked('');
    } catch (err) {
      const e = toApiError(err);
      // 409 here is a guard, not a fault — show its reason verbatim.
      if (e.status === 409) setBlocked(e.message);
      else show({ tone: 'error', text: `Couldn’t draft that: ${e.message}` });
    } finally {
      setDrafting(false);
    }
  };

  const send = async () => {
    if (!nudge) return;
    if (!armed) {
      setArmed(true);
      window.setTimeout(() => setArmed(false), 4000);
      return;
    }
    setSending(true);
    try {
      await sendNudge(nudge.id, body);
      show({ tone: 'success', text: `Sent to ${who}. I’ll watch for their reply.` });
      onSent();
    } catch (err) {
      const e = toApiError(err);
      show({
        tone: 'error',
        text:
          e.status === 409
            ? e.message
            : `Couldn’t send: ${e.message}`,
      });
    } finally {
      setSending(false);
      setArmed(false);
    }
  };

  const who = followUp.counterparty_name || followUp.counterparty_email || 'them';
  const silentDays = followUp.last_outbound_at
    ? Math.max(
        1,
        Math.floor(
          (Date.now() - new Date(`${followUp.last_outbound_at}Z`).getTime()) / 86400000,
        ),
      )
    : null;

  if (blocked && !nudge) {
    return (
      <div className="rounded-2xl bg-muted/60 p-3 text-[13px] leading-relaxed text-muted-foreground">
        {blocked}
      </div>
    );
  }

  return (
    <div className="space-y-3">
      {/* The half the user can't see: they never received a message here. */}
      <div className="rounded-2xl bg-muted/60 p-3 text-[13px] leading-relaxed text-muted-foreground">
        {silentDays
          ? `You wrote ${silentDays} day${silentDays === 1 ? '' : 's'} ago — no reply since.`
          : 'No reply since your last message.'}
        {followUp.nudge_count > 0 && (
          <>
            {' '}
            You’ve nudged {followUp.nudge_count}×.
          </>
        )}
      </div>

      {!nudge ? (
        <div className="space-y-2">
          <div className="grid grid-cols-3 gap-2">
            {TONES.map((t) => (
              <Button
                key={t.value}
                variant="secondary"
                size="sm"
                disabled={drafting}
                onClick={() => void draft(t.value)}
              >
                {t.label}
              </Button>
            ))}
          </div>
          <p className="text-[12px] text-muted-foreground">
            Writes a short follow-up in your voice. Nothing sends until you approve it.
          </p>
        </div>
      ) : (
        <>
          <div>
            <div className="mb-1 flex items-center gap-1.5 text-[12px] font-medium text-muted-foreground">
              <Sparkles className="h-3.5 w-3.5 text-accent" />
              {nudge.voice_matched ? 'Follow-up · in your voice' : 'Follow-up · basic draft'}
            </div>
            <textarea
              value={body}
              onChange={(e) => setBody(e.target.value)}
              rows={5}
              className="w-full resize-y rounded-xl border border-border bg-background px-3 py-2 text-[14px] leading-relaxed text-foreground outline-none focus:border-accent"
              aria-label="Follow-up message"
            />
          </div>

          {blocked && (
            <p className="text-[12px] text-destructive">{blocked}</p>
          )}

          <div>
            <Button
              variant={armed ? 'danger' : 'primary'}
              className="w-full justify-center"
              disabled={sending || !body.trim()}
              icon={sending ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}
              onClick={() => void send()}
            >
              {armed ? `Tap again to send to ${who}` : `Send follow-up to ${who}`}
            </Button>
            <p className="mt-1 text-center text-[11px] text-muted-foreground">
              Sends from your Gmail, in this thread.
            </p>
          </div>

          <Button
            variant="ghost"
            size="sm"
            className="w-full justify-center"
            disabled={drafting}
            onClick={() => void draft()}
          >
            {drafting ? 'Rewriting…' : 'Rewrite'}
          </Button>
        </>
      )}
    </div>
  );
}

export default NudgeComposer;
