import { useId } from 'react';
import { cn } from '@/lib/utils';

/**
 * The Gmail Sentry mark: a rainbow-gradient shield guarding an envelope, set on
 * a white square tile with a hairline border — the app icon. The square-with-
 * border framing (not a circle) is intentional so it reads as an app glyph.
 *
 * The hex colours here are deliberate and must NOT become theme tokens. This is
 * a fixed brand glyph, like a favicon: the tile is literally white in both
 * themes, so the slate envelope reads against it either way, and a mark whose
 * colours changed with the theme would stop being a recognisable mark. The
 * identity gate flags raw hex as possible theme drift — this is the exception it
 * asks you to confirm.
 */
export function SentryMark({ className }: { className?: string }) {
  // useId → unique gradient id per instance (the mark renders in both the top
  // bar and the sidebar; duplicate SVG ids would otherwise collide).
  const gid = useId().replace(/:/g, '');
  return (
    <span
      className={cn(
        'inline-flex items-center justify-center overflow-hidden rounded-lg bg-white shadow-apple ring-1 ring-black/15',
        className,
      )}
    >
      <svg viewBox="0 0 48 48" className="h-[70%] w-[70%]" fill="none" aria-hidden="true">
        <defs>
          <linearGradient id={gid} x1="6" y1="5" x2="42" y2="45" gradientUnits="userSpaceOnUse">
            <stop offset="0" stopColor="#D633FF" />
            <stop offset="0.18" stopColor="#7B4DFF" />
            <stop offset="0.38" stopColor="#2E7BFF" />
            <stop offset="0.56" stopColor="#22D3EE" />
            <stop offset="0.74" stopColor="#4ADE80" />
            <stop offset="0.88" stopColor="#FACC15" />
            <stop offset="1" stopColor="#FB923C" />
          </linearGradient>
        </defs>
        {/* shield outline — rainbow gradient stroke */}
        <path
          d="M24 4 L41 10 V23 C41 34 33.5 41.5 24 44.5 C14.5 41.5 7 34 7 23 V10 Z"
          stroke={`url(#${gid})`}
          strokeWidth="2.6"
          strokeLinejoin="round"
        />
        {/* envelope inside — dark slate so it reads on the white tile */}
        <g stroke="#334155" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <rect x="14" y="19" width="20" height="13" rx="1.5" />
          <path d="M14.6 20 L24 27.6 L33.4 20" />
        </g>
      </svg>
    </span>
  );
}

export default SentryMark;
