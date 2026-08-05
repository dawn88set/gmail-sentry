import { useCallback, useEffect, useRef, useState } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { motion, AnimatePresence } from 'framer-motion';
import { Sparkles, ArrowRight, Loader2, X, Check } from 'lucide-react';
import { useToast } from '@/components/Toast';
import {
  ask,
  createRule,
  createLabelRule,
  toApiError,
  type AskAnswer,
} from '@/lib/api';
import { cn } from '@/lib/utils';

/**
 * Ask — the plain-language way into everything the app knows.
 *
 * Deliberately not a nav destination. The questions people have ("where are we
 * with Northwind?", "who's gone quiet?") occur WHILE they're looking at
 * something, and a tab you have to navigate to is a tab you forget exists. It
 * opens over whatever screen you're on, and it passes that screen as context so
 * "what's going on here?" on an account page means that account.
 *
 * Anything that would change something arrives as a proposal with a real count
 * of what it affects, and does nothing until it's approved — the same
 * draft→approve lifecycle the rest of the app runs on.
 */

const EXAMPLES = [
  'what needs me today?',
  'where are we with…',
  'who has gone quiet?',
  'file supplier mail into Ops',
];

export function AskBar() {
  const [open, setOpen] = useState(false);
  const [q, setQ] = useState('');
  const [busy, setBusy] = useState(false);
  const [answer, setAnswer] = useState<AskAnswer | null>(null);
  const [applied, setApplied] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);
  const { show } = useToast();
  const navigate = useNavigate();
  const location = useLocation();

  // ⌘K / Ctrl-K from anywhere, Escape to close. Registered once at the app root.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') {
        e.preventDefault();
        setOpen((v) => !v);
      } else if (e.key === 'Escape') {
        setOpen(false);
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, []);

  useEffect(() => {
    if (open) window.setTimeout(() => inputRef.current?.focus(), 60);
    else {
      setAnswer(null);
      setQ('');
      setApplied(false);
    }
  }, [open]);

  const submit = useCallback(
    async (text: string) => {
      const question = text.trim();
      if (!question || busy) return;
      setBusy(true);
      setApplied(false);
      try {
        setAnswer(await ask(question, location.pathname));
      } catch (err) {
        show({ tone: 'error', text: `Couldn’t answer that: ${toApiError(err).message}` });
      } finally {
        setBusy(false);
      }
    },
    [busy, location.pathname, show],
  );

  /** Apply a proposal. Only ever runs from an explicit tap. */
  const approve = useCallback(async () => {
    const p = answer?.proposal;
    if (!p) return;
    setBusy(true);
    try {
      if (p.kind === 'rule') await createRule(p.payload as never);
      else await createLabelRule(p.payload as never);
      setApplied(true);
      show({ tone: 'success', text: 'Done — it applies from the next scan.' });
    } catch (err) {
      show({ tone: 'error', text: `Couldn’t create that: ${toApiError(err).message}` });
    } finally {
      setBusy(false);
    }
  }, [answer, show]);

  return (
    <>
      {/* The trigger. Fixed, above the tab bar on mobile, out of the way of
          content — present on every screen without occupying a nav slot. */}
      <button
        onClick={() => setOpen(true)}
        aria-label="Ask Sentry"
        className="fixed bottom-20 right-4 z-40 inline-flex items-center gap-2 rounded-full bg-accent px-4 py-3 text-[14px] font-semibold text-accent-foreground shadow-lg transition-transform active:scale-95 lg:bottom-6"
      >
        <Sparkles className="h-4 w-4" />
        Ask
      </button>

      <AnimatePresence>
        {open && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="fixed inset-0 z-50 flex items-start justify-center bg-background/80 p-4 pt-[12vh] backdrop-blur-sm"
            onClick={() => setOpen(false)}
          >
            <motion.div
              initial={{ opacity: 0, y: -12, scale: 0.98 }}
              animate={{ opacity: 1, y: 0, scale: 1 }}
              exit={{ opacity: 0, y: -8, scale: 0.98 }}
              transition={{ duration: 0.16 }}
              onClick={(e) => e.stopPropagation()}
              className="w-full max-w-lg overflow-hidden rounded-2xl bg-card shadow-2xl ring-1 ring-border"
            >
              <form
                onSubmit={(e) => {
                  e.preventDefault();
                  void submit(q);
                }}
                className="flex items-center gap-3 border-b border-border px-4 py-3"
              >
                <Sparkles className="h-4 w-4 flex-shrink-0 text-accent" />
                <input
                  ref={inputRef}
                  value={q}
                  onChange={(e) => setQ(e.target.value)}
                  placeholder="Ask about your mail…"
                  className="min-w-0 flex-1 bg-transparent text-[15px] text-foreground outline-none placeholder:text-muted-foreground/60"
                />
                {busy ? (
                  <Loader2 className="h-4 w-4 flex-shrink-0 animate-spin text-muted-foreground" />
                ) : (
                  <button
                    type="button"
                    onClick={() => setOpen(false)}
                    aria-label="Close"
                    className="flex-shrink-0 text-muted-foreground transition-colors hover:text-foreground"
                  >
                    <X className="h-4 w-4" />
                  </button>
                )}
              </form>

              <div className="max-h-[52vh] overflow-y-auto px-4 py-3">
                {!answer && (
                  <div className="space-y-1.5">
                    {EXAMPLES.map((e) => (
                      <button
                        key={e}
                        onClick={() => {
                          setQ(e);
                          void submit(e);
                        }}
                        className="flex w-full items-center gap-2 rounded-lg px-2 py-1.5 text-left text-[13.5px] text-muted-foreground transition-colors hover:bg-muted/50 hover:text-foreground"
                      >
                        <ArrowRight className="h-3.5 w-3.5 flex-shrink-0 opacity-50" />
                        {e}
                      </button>
                    ))}
                  </div>
                )}

                {answer && (
                  <div>
                    <div className="text-[15px] font-semibold text-foreground">{answer.title}</div>
                    <div className="mt-1.5 space-y-1">
                      {answer.lines.map((l, i) => (
                        <div
                          key={i}
                          className={cn(
                            'text-[13.5px] leading-relaxed',
                            l.strong ? 'font-medium text-foreground' : 'text-foreground/85',
                            l.muted && 'text-[12.5px] text-muted-foreground',
                          )}
                        >
                          {l.text}
                        </div>
                      ))}
                    </div>

                    {/* A change is described, counted, and NOT made until tapped. */}
                    {answer.proposal && !applied && (
                      <div className="mt-3 flex items-center gap-2">
                        <button
                          onClick={() => void approve()}
                          disabled={busy}
                          className="inline-flex items-center gap-1.5 rounded-full bg-accent px-3.5 py-1.5 text-[13px] font-semibold text-accent-foreground transition-transform active:scale-95 disabled:opacity-60"
                        >
                          <Check className="h-3.5 w-3.5" />
                          {answer.proposal.label}
                        </button>
                        <button
                          onClick={() => setAnswer(null)}
                          className="rounded-full px-3 py-1.5 text-[13px] font-medium text-muted-foreground transition-colors hover:text-foreground"
                        >
                          Not that
                        </button>
                      </div>
                    )}
                    {applied && (
                      <div className="mt-3 inline-flex items-center gap-1.5 text-[13px] font-medium text-success">
                        <Check className="h-3.5 w-3.5" /> Created
                      </div>
                    )}

                    {answer.link && (
                      <button
                        onClick={() => {
                          navigate(answer.link!);
                          setOpen(false);
                        }}
                        className="mt-3 inline-flex items-center gap-1 text-[13px] font-medium text-accent"
                      >
                        Open <ArrowRight className="h-3.5 w-3.5" />
                      </button>
                    )}
                  </div>
                )}
              </div>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>
    </>
  );
}

export default AskBar;
