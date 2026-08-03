import { useRef, useState } from 'react';
import { Loader2, Send, X } from 'lucide-react';
import { Button } from '@clarittyai/app-ui';
import { useToast } from '@/components/Toast';
import { DraftRefiner } from '@/components/DraftRefiner';
import { sendMail, toApiError } from '@/lib/api';

/**
 * Write an email.
 *
 * Shares the app's one discipline about outbound mail: it arms before sending,
 * and the button names the recipient, so a mis-tap is legible BEFORE it happens
 * rather than after. Every other send path in this app does the same, and this
 * one is the only place a message can go to someone the app never flagged —
 * which makes it the one most worth guarding.
 *
 * The refiner is here too: the point of drafting in the user's voice is lost if
 * the last edit has to be made by hand.
 */
export function Compose({
  onClose,
  onSent,
  to: initialTo = '',
  subject: initialSubject = '',
  threadId = '',
  inReplyTo = '',
}: {
  onClose: () => void;
  onSent: () => void;
  to?: string;
  subject?: string;
  threadId?: string;
  inReplyTo?: string;
}) {
  const { show } = useToast();
  const [to, setTo] = useState(initialTo);
  const [subject, setSubject] = useState(initialSubject);
  const [body, setBody] = useState('');
  const [sending, setSending] = useState(false);
  const [armed, setArmed] = useState(false);
  const bodyRef = useRef<HTMLTextAreaElement>(null);

  const send = async () => {
    if (!armed) {
      setArmed(true);
      window.setTimeout(() => setArmed(false), 4000);
      return;
    }
    setSending(true);
    try {
      await sendMail({ to, subject, body, thread_id: threadId, in_reply_to: inReplyTo });
      onSent();
    } catch (err) {
      const e = toApiError(err);
      show({
        tone: 'error',
        text: e.status === 409 ? 'Connect Gmail, then try again.' : `Couldn’t send: ${e.message}`,
      });
    } finally {
      setSending(false);
      setArmed(false);
    }
  };

  const ready = to.trim().length > 0 && body.trim().length > 0;

  return (
    <div className="fixed inset-0 z-50 flex items-end justify-center bg-black/40 sm:items-center" onClick={onClose}>
      <div
        className="max-h-[92vh] w-full overflow-y-auto rounded-t-3xl bg-card p-5 shadow-apple-lg sm:max-w-lg sm:rounded-3xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="mb-3 flex items-center justify-between">
          <span className="text-[17px] font-semibold text-foreground">
            {threadId ? 'Reply' : 'New email'}
          </span>
          <Button variant="ghost" size="sm" onClick={onClose} aria-label="Close">
            <X className="h-4 w-4" />
          </Button>
        </div>

        <label className="mb-2 block">
          <span className="mb-1 block text-[12px] font-medium text-muted-foreground">To</span>
          <input
            value={to}
            onChange={(e) => setTo(e.target.value)}
            disabled={!!threadId}
            placeholder="name@company.com"
            className="w-full rounded-xl border border-border bg-background px-3 py-2 text-[14px] text-foreground outline-none focus:border-accent disabled:opacity-60"
          />
        </label>

        <label className="mb-2 block">
          <span className="mb-1 block text-[12px] font-medium text-muted-foreground">Subject</span>
          <input
            value={subject}
            onChange={(e) => setSubject(e.target.value)}
            placeholder="Subject"
            className="w-full rounded-xl border border-border bg-background px-3 py-2 text-[14px] text-foreground outline-none focus:border-accent"
          />
        </label>

        <textarea
          ref={bodyRef}
          value={body}
          onChange={(e) => setBody(e.target.value)}
          rows={8}
          placeholder="Write your message…"
          aria-label="Message body"
          className="w-full resize-y rounded-xl border border-border bg-background px-3 py-2 text-[14px] leading-relaxed text-foreground outline-none focus:border-accent"
        />
        <DraftRefiner
          value={body}
          onChange={setBody}
          textareaRef={bodyRef}
          context={subject}
          disabled={sending}
        />

        <Button
          variant={armed ? 'danger' : 'primary'}
          className="mt-3 w-full justify-center"
          disabled={sending || !ready}
          icon={sending ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}
          onClick={() => void send()}
        >
          {armed ? `Tap again to send to ${to}` : `Send to ${to || '…'}`}
        </Button>
        <p className="mt-1 text-center text-[11px] text-muted-foreground">
          Sends from your Gmail.
        </p>
      </div>
    </div>
  );
}

export default Compose;
