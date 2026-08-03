import { useState, type RefObject } from 'react';
import { Loader2, Undo2 } from 'lucide-react';
import { useToast } from '@/components/Toast';
import { refineDraft, toApiError, type Refinement } from '@/lib/api';

const OPTIONS: { how: Refinement; label: string }[] = [
  { how: 'shorter', label: 'Shorter' },
  { how: 'warmer', label: 'Warmer' },
  { how: 'firmer', label: 'Firmer' },
  { how: 'formal', label: 'More formal' },
];

/**
 * Rewrite the draft you're looking at, without leaving it.
 *
 * A drafted reply is usually 80% right, and the last 20% is where people give
 * up and retype it themselves — which throws away the voice matching the draft
 * existed for. These are the four edits that actually get made.
 *
 * Selection-aware: rewrites what's highlighted, or the whole draft if nothing
 * is. That matters because the fix is usually one paragraph, not the email.
 *
 * Always undoable in one tap. This edits words the user is about to send in
 * their own name, so a rewrite they dislike must never cost them the original —
 * and the undo restores the selection too, so they can try a different chip on
 * the same passage.
 */
export function DraftRefiner({
  value,
  onChange,
  textareaRef,
  context = '',
  disabled = false,
}: {
  value: string;
  onChange: (next: string) => void;
  textareaRef: RefObject<HTMLTextAreaElement>;
  context?: string;
  disabled?: boolean;
}) {
  const { show } = useToast();
  const [busy, setBusy] = useState<Refinement | null>(null);
  const [undo, setUndo] = useState<{ text: string; start: number; end: number } | null>(null);

  const run = async (how: Refinement) => {
    const el = textareaRef.current;
    const start = el && el.selectionStart !== el.selectionEnd ? el.selectionStart : 0;
    const end = el && el.selectionStart !== el.selectionEnd ? el.selectionEnd : value.length;
    const passage = value.slice(start, end).trim();
    if (!passage) {
      show({ tone: 'error', text: 'Nothing to rewrite yet.' });
      return;
    }

    setBusy(how);
    try {
      const { text } = await refineDraft(passage, how, context);
      setUndo({ text: value, start, end });
      const next = value.slice(0, start) + text + value.slice(end);
      onChange(next);
      // Leave the rewritten passage selected so another chip can be tried on it.
      window.setTimeout(() => {
        el?.focus();
        el?.setSelectionRange(start, start + text.length);
      }, 0);
    } catch (err) {
      const e = toApiError(err);
      // 503 is an honest refusal with a sentence worth reading, not a fault.
      show({ tone: 'error', text: e.status === 503 ? e.message : `Couldn’t rewrite: ${e.message}` });
    } finally {
      setBusy(null);
    }
  };

  const revert = () => {
    if (!undo) return;
    onChange(undo.text);
    const { start, end } = undo;
    setUndo(null);
    window.setTimeout(() => {
      textareaRef.current?.focus();
      textareaRef.current?.setSelectionRange(start, end);
    }, 0);
  };

  return (
    <div className="mt-2 flex flex-wrap items-center gap-1.5">
      {OPTIONS.map((o) => (
        <button
          key={o.how}
          type="button"
          disabled={disabled || busy !== null || !value.trim()}
          onClick={() => void run(o.how)}
          className="inline-flex min-h-[32px] items-center gap-1.5 rounded-full border border-border bg-card px-3 text-[12px] font-medium text-muted-foreground transition-colors hover:border-accent/60 hover:text-foreground disabled:opacity-40"
        >
          {busy === o.how && <Loader2 className="h-3 w-3 animate-spin" />}
          {o.label}
        </button>
      ))}

      {undo && (
        <button
          type="button"
          onClick={revert}
          className="inline-flex min-h-[32px] items-center gap-1.5 rounded-full px-2.5 text-[12px] font-medium text-accent hover:underline"
        >
          <Undo2 className="h-3 w-3" />
          Undo
        </button>
      )}

      <span className="ml-auto text-[11px] text-muted-foreground/80">
        Select text to rewrite just that part
      </span>
    </div>
  );
}

export default DraftRefiner;
