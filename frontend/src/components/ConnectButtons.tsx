import { cn } from '@/lib/utils';

/** Official 4-color Google "G" (colors via the gmail.* palette — no raw hex). */
/*
 * The hex colours in the service icons below are each provider's official brand
 * colour — Telegram #2AABEE, Discord #5865F2, WhatsApp #25D366. They identify
 * the service, so they are fixed by definition and must not be replaced with
 * theme tokens: a green WhatsApp glyph that turned indigo with the app theme
 * would stop being recognisable, which is the entire job of a service icon.
 * (The identity gate flags raw hex as possible drift; this is that exception.)
 */
export function GoogleLogo({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 48 48" className={className} aria-hidden="true">
      <path className="fill-gmail-red-500" d="M24 9.5c3.54 0 6.71 1.22 9.21 3.6l6.85-6.85C35.9 2.38 30.47 0 24 0 14.62 0 6.51 5.38 2.56 13.22l7.98 6.19C12.43 13.72 17.74 9.5 24 9.5z" />
      <path className="fill-gmail-blue-500" d="M46.98 24.55c0-1.57-.15-3.09-.38-4.55H24v9.02h12.94c-.58 2.96-2.26 5.48-4.78 7.18l7.73 6c4.51-4.18 7.09-10.36 7.09-17.65z" />
      <path className="fill-gmail-yellow-500" d="M10.53 28.59c-.48-1.45-.76-2.99-.76-4.59s.27-3.14.76-4.59l-7.98-6.19C.92 16.46 0 20.12 0 24c0 3.88.92 7.54 2.56 10.78l7.97-6.19z" />
      <path className="fill-gmail-green-500" d="M24 48c6.48 0 11.93-2.13 15.89-5.81l-7.73-6c-2.15 1.45-4.92 2.3-8.16 2.3-6.26 0-11.57-4.22-13.47-9.91l-7.98 6.19C6.51 42.62 14.62 48 24 48z" />
    </svg>
  );
}

/** Official 4-color Slack mark. */
export function SlackLogo({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 122.8 122.8" className={className} aria-hidden="true">
      <path className="fill-slack-red" d="M25.8 77.6c0 7.1-5.8 12.9-12.9 12.9S0 84.7 0 77.6s5.8-12.9 12.9-12.9h12.9v12.9zM32.3 77.6c0-7.1 5.8-12.9 12.9-12.9s12.9 5.8 12.9 12.9v32.3c0 7.1-5.8 12.9-12.9 12.9s-12.9-5.8-12.9-12.9V77.6z" />
      <path className="fill-slack-blue" d="M45.2 25.8c-7.1 0-12.9-5.8-12.9-12.9S38.1 0 45.2 0s12.9 5.8 12.9 12.9v12.9H45.2zM45.2 32.3c7.1 0 12.9 5.8 12.9 12.9s-5.8 12.9-12.9 12.9H12.9C5.8 58.1 0 52.3 0 45.2s5.8-12.9 12.9-12.9h32.3z" />
      <path className="fill-slack-green" d="M97 45.2c0-7.1 5.8-12.9 12.9-12.9s12.9 5.8 12.9 12.9-5.8 12.9-12.9 12.9H97V45.2zM90.5 45.2c0 7.1-5.8 12.9-12.9 12.9s-12.9-5.8-12.9-12.9V12.9C64.7 5.8 70.5 0 77.6 0s12.9 5.8 12.9 12.9v32.3z" />
      <path className="fill-slack-yellow" d="M77.6 97c7.1 0 12.9 5.8 12.9 12.9s-5.8 12.9-12.9 12.9-12.9-5.8-12.9-12.9V97h12.9zM77.6 90.5c-7.1 0-12.9-5.8-12.9-12.9s5.8-12.9 12.9-12.9h32.3c7.1 0 12.9 5.8 12.9 12.9s-5.8 12.9-12.9 12.9H77.6z" />
    </svg>
  );
}

/** Telegram mark (blue disc + paper plane). */
export function TelegramLogo({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" className={className} aria-hidden="true">
      <circle cx="12" cy="12" r="12" fill="#2AABEE" />
      <path fill="#fff" d="M5.49 11.86c3.79-1.65 6.32-2.74 7.59-3.27 3.61-1.5 4.36-1.76 4.85-1.77.11 0 .35.02.51.15.13.11.17.25.19.36.02.1.04.34.02.52-.2 2.08-1.05 7.12-1.48 9.45-.18.99-.54 1.32-.89 1.35-.75.07-1.32-.5-2.05-.97-1.14-.75-1.79-1.22-2.9-1.95-1.28-.84-.45-1.31.28-2.07.19-.2 3.51-3.22 3.58-3.49.01-.03.02-.16-.06-.23-.08-.07-.2-.05-.29-.03-.12.03-2.09 1.33-5.9 3.9-.56.38-1.06.57-1.52.56-.5-.01-1.46-.28-2.17-.52-.87-.28-1.57-.43-1.51-.91.03-.25.38-.5 1.05-.76z" />
    </svg>
  );
}

/** Discord mark (blurple). */
export function DiscordLogo({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" className={className} aria-hidden="true">
      <path fill="#5865F2" d="M20.32 4.37A19.8 19.8 0 0 0 15.4 2.9a.07.07 0 0 0-.08.04c-.21.38-.45.87-.62 1.25a18.3 18.3 0 0 0-5.4 0c-.17-.39-.42-.87-.63-1.25a.08.08 0 0 0-.08-.04c-1.7.3-3.35.8-4.92 1.47a.07.07 0 0 0-.03.03C.53 9.05-.32 13.58.1 18.06a.08.08 0 0 0 .03.05 19.9 19.9 0 0 0 6 3.03.08.08 0 0 0 .09-.03c.46-.63.87-1.3 1.23-2a.08.08 0 0 0-.04-.11c-.65-.25-1.27-.55-1.87-.9a.08.08 0 0 1-.01-.13l.37-.29a.07.07 0 0 1 .08-.01 14.2 14.2 0 0 0 12.06 0 .07.07 0 0 1 .08.01l.37.29a.08.08 0 0 1-.01.13c-.6.35-1.22.65-1.87.9a.08.08 0 0 0-.04.11c.36.7.78 1.36 1.23 2a.08.08 0 0 0 .09.03 19.8 19.8 0 0 0 6.01-3.03.08.08 0 0 0 .03-.05c.5-5.18-.84-9.67-3.54-13.66a.06.06 0 0 0-.03-.03zM8.02 15.33c-1.18 0-2.16-1.08-2.16-2.42s.96-2.42 2.16-2.42c1.21 0 2.18 1.09 2.16 2.42 0 1.34-.96 2.42-2.16 2.42zm7.97 0c-1.18 0-2.16-1.08-2.16-2.42s.96-2.42 2.16-2.42c1.21 0 2.18 1.09 2.16 2.42 0 1.34-.95 2.42-2.16 2.42z" />
    </svg>
  );
}

/** WhatsApp mark (green). Used for the Twilio → WhatsApp channel. */
export function WhatsAppLogo({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" className={className} aria-hidden="true">
      <path fill="#25D366" d="M.06 24l1.68-6.13A11.86 11.86 0 0 1 .16 11.9C.16 5.34 5.5 0 12.06 0a11.82 11.82 0 0 1 8.4 3.49 11.82 11.82 0 0 1 3.48 8.4c0 6.56-5.34 11.9-11.9 11.9a11.9 11.9 0 0 1-5.68-1.45L.06 24z" />
      <path fill="#fff" d="M8.9 6.9c-.2-.46-.42-.47-.62-.48h-.53c-.18 0-.48.07-.73.35-.25.28-.96.94-.96 2.3s.98 2.66 1.12 2.85c.14.18 1.9 3.05 4.7 4.15 2.33.92 2.8.74 3.3.69.5-.05 1.63-.66 1.86-1.3.23-.64.23-1.19.16-1.3-.07-.12-.25-.18-.53-.32-.28-.14-1.63-.8-1.89-.9-.25-.09-.44-.14-.62.14-.18.28-.71.9-.87 1.08-.16.18-.32.2-.6.07-.28-.14-1.17-.43-2.22-1.37-.82-.73-1.38-1.64-1.54-1.92-.16-.28-.02-.43.12-.57.12-.12.28-.32.42-.48.14-.16.18-.28.28-.46.09-.18.05-.35-.02-.48-.07-.14-.61-1.52-.86-2.06z" />
    </svg>
  );
}

type LogoC = (p: { className?: string }) => JSX.Element;
const BRAND: Record<string, { Logo: LogoC; label: string }> = {
  gmail: { Logo: GoogleLogo, label: 'Sign in with Google' },
  slack: { Logo: SlackLogo, label: 'Add to Slack' },
  telegram: { Logo: TelegramLogo, label: 'Connect Telegram' },
  discord: { Logo: DiscordLogo, label: 'Connect Discord' },
  twilio: { Logo: WhatsAppLogo, label: 'Connect WhatsApp' },
};

/** Neutral fallback mark for any integration without a branded logo. */
function GenericLogo({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" className={className} fill="none" aria-hidden="true">
      <path
        d="M10 13a5 5 0 0 0 7.07 0l3-3a5 5 0 1 0-7.07-7.07l-1.72 1.72M14 11a5 5 0 0 0-7.07 0l-3 3a5 5 0 1 0 7.07 7.07l1.71-1.71"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

/**
 * A branded connect button matching each provider's sign-in design. Clicking it
 * triggers the platform's integration gate (the caller wires onClick).
 */
export function ConnectButton({
  integrationId,
  onClick,
  className,
}: {
  integrationId: string;
  onClick: () => void;
  className?: string;
}) {
  const brand = BRAND[integrationId] ?? {
    Logo: GenericLogo,
    label: `Connect ${integrationId}`,
  };
  const Logo = brand.Logo;
  const label = brand.label;
  return (
    <button
      onClick={onClick}
      className={cn(
        // Theme-matching provider button — charcoal surface + hairline border in
        // dark, white in light — with the recognizable colored brand logo.
        'inline-flex items-center gap-2.5 rounded-full bg-card px-4 py-2 text-sm font-medium text-foreground shadow-sm ring-1 ring-border transition-colors hover:bg-muted active:scale-[0.98]',
        className,
      )}
    >
      <Logo className="h-[18px] w-[18px]" />
      {label}
    </button>
  );
}

export default ConnectButton;
