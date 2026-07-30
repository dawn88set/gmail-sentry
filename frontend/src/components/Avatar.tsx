import { cn } from '@/lib/utils';

// Gmail-style colored initial avatars — a deterministic color per sender.
const AV = ['bg-av-blue', 'bg-av-teal', 'bg-av-indigo', 'bg-av-purple', 'bg-av-pink', 'bg-av-green', 'bg-av-red', 'bg-av-brown'];

function hash(s: string): number {
  let h = 0;
  for (let i = 0; i < s.length; i++) h = (h * 31 + s.charCodeAt(i)) | 0;
  return Math.abs(h);
}

/**
 * Parse "Dana Levi <dana@acme.com>" → { name, email }.
 *
 * Co-located with <Avatar> on purpose: every caller that renders an avatar first
 * parses a sender, so splitting them costs a second import for no runtime
 * benefit. The lint rule below is about dev-server hot reload, not correctness.
 */
// eslint-disable-next-line react-refresh/only-export-components
export function parseSender(raw: string): { name: string; email: string } {
  const m = /<([^>]+)>/.exec(raw || '');
  const email = (m ? m[1] : (/\S+@\S+/.exec(raw || '')?.[0] ?? '')).trim();
  const name = (raw || '').split('<')[0].trim().replace(/^"|"$/g, '');
  return { name: name || email, email };
}

export function Avatar({
  name,
  email,
  className,
}: {
  name?: string;
  email?: string;
  className?: string;
}) {
  const key = (email || name || '?').toLowerCase();
  const color = AV[hash(key) % AV.length];
  const initial = ((name || email || '?').trim()[0] || '?').toUpperCase();
  return (
    <span
      aria-hidden="true"
      className={cn('inline-flex flex-shrink-0 items-center justify-center rounded-full font-semibold text-white', color, className)}
    >
      {initial}
    </span>
  );
}

export default Avatar;
