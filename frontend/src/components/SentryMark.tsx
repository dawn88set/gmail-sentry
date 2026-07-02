import { cn } from '@/lib/utils';

/**
 * The Gmail Sentry mark: a warm amber "shield + envelope" glyph on a dark tile —
 * Firebase-inspired (one accent, no multicolor). Uses the theme accent so it
 * follows the palette.
 */
export function SentryMark({ className }: { className?: string }) {
  return (
    <span
      className={cn(
        'inline-flex items-center justify-center rounded-2xl bg-accent shadow-apple ring-1 ring-black/10',
        className,
      )}
    >
      <svg
        viewBox="0 0 48 48"
        className="h-[60%] w-[60%] text-accent-foreground"
        fill="none"
        stroke="currentColor"
        strokeWidth="3"
        strokeLinecap="round"
        strokeLinejoin="round"
        aria-hidden="true"
      >
        {/* shield */}
        <path d="M24 5 L40 11 V23 C40 33 33 40 24 43 C15 40 8 33 8 23 V11 Z" />
        {/* envelope inside */}
        <path d="M15 19 H33 V31 H15 Z" />
        <path d="M15 20 L24 27 L33 20" />
      </svg>
    </span>
  );
}

export default SentryMark;
