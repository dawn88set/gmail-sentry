/**
 * Global toast — a single floating notice (success / error) that auto-dismisses.
 * Tokens only, matched to the app's card/badge language. No external lib.
 *
 * Mounted ONCE at the app root via <ToastProvider> (see App.tsx); any component
 * calls the `useToast()` hook to fire a toast. There is exactly one toast surface
 * for the whole app, so notices never stack or duplicate across pages/widgets.
 *
 * WHY THIS EXISTS: every app MUST surface errors to the user — never swallow a
 * failed API call. Catch the error, run it through `toApiError`, and `show()` it.
 * See "Surface every error" in CLAUDE.md.
 */
import {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from 'react';
import { CheckCircle2, AlertCircle, X, ExternalLink } from 'lucide-react';
import { cn } from '@/lib/utils';

export type ToastTone = 'success' | 'error';

export interface ToastMessage {
  tone: ToastTone;
  text: string;
  /** Optional trailing link action (e.g. "View result"). */
  href?: string;
  hrefLabel?: string;
}

interface ToastContextValue {
  show: (msg: ToastMessage) => void;
  dismiss: () => void;
}

const ToastContext = createContext<ToastContextValue | null>(null);

/** Mount once at the app root. Owns the single toast surface + provides `show`. */
export function ToastProvider({ children }: { children: ReactNode }) {
  const [toast, setToast] = useState<ToastMessage | null>(null);
  const timer = useRef<number | undefined>(undefined);

  const dismiss = useCallback(() => {
    setToast(null);
    window.clearTimeout(timer.current);
  }, []);

  const show = useCallback((msg: ToastMessage) => {
    setToast(msg);
    window.clearTimeout(timer.current);
    timer.current = window.setTimeout(() => setToast(null), 6000);
  }, []);

  const value = useMemo(() => ({ show, dismiss }), [show, dismiss]);

  return (
    <ToastContext.Provider value={value}>
      {children}
      <ToastView toast={toast} onDismiss={dismiss} />
    </ToastContext.Provider>
  );
}

const NOOP_TOAST: ToastContextValue = { show: () => {}, dismiss: () => {} };

/**
 * Access the global toast surface. Degrades to a NO-OP when no <ToastProvider> is
 * mounted (e.g. a widget rendered in a bare test or host context) so a missing
 * provider never crashes the widget. In the app, <ToastProvider> wraps everything
 * (incl. the /widget route), so toasts render normally.
 */
export function useToast(): ToastContextValue {
  return useContext(ToastContext) ?? NOOP_TOAST;
}

function ToastView({
  toast,
  onDismiss,
}: {
  toast: ToastMessage | null;
  onDismiss: () => void;
}) {
  if (!toast) return null;
  const success = toast.tone === 'success';
  const Icon = success ? CheckCircle2 : AlertCircle;
  return (
    <div className="pointer-events-none fixed inset-x-0 bottom-[calc(env(safe-area-inset-bottom)+1.5rem)] z-[60] flex justify-center px-4">
      <div
        role="status"
        className={cn(
          'pointer-events-auto flex max-w-md items-start gap-3 rounded-2xl border bg-card px-4 py-3 shadow-lg',
          success ? 'border-green-500/30' : 'border-red-500/30',
        )}
      >
        <span
          className={cn(
            'mt-0.5 flex h-7 w-7 flex-shrink-0 items-center justify-center rounded-lg',
            success ? 'bg-green-500/10 text-green-500' : 'bg-red-500/10 text-red-500',
          )}
        >
          <Icon className="h-4 w-4" />
        </span>
        <div className="min-w-0 flex-1">
          <p className="text-sm text-foreground">{toast.text}</p>
          {toast.href && (
            <a
              href={toast.href}
              target="_blank"
              rel="noreferrer"
              className="mt-1 inline-flex items-center gap-1 text-xs font-medium text-primary hover:underline"
            >
              {toast.hrefLabel ?? 'Open'} <ExternalLink className="h-3 w-3" />
            </a>
          )}
        </div>
        <button
          onClick={onDismiss}
          aria-label="Dismiss"
          className="flex h-6 w-6 flex-shrink-0 items-center justify-center rounded-lg text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
        >
          <X className="h-3.5 w-3.5" />
        </button>
      </div>
    </div>
  );
}
