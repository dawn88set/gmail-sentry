import type { ReactNode } from 'react';
import { cn } from '@/lib/utils';

/**
 * A square icon-over-label tile for a sheet's secondary action grid
 * (Open / Snooze / Done / Mute…).
 *
 * Deliberately a raw <button> rather than the app-ui `Button`: this is a
 * fixed-size vertical tile, not a text button, so the kit's horizontal
 * padding/icon-gap rules fight it. It lives in the local `ios/` kit so the
 * exception is declared in one place instead of being re-hand-rolled in every
 * sheet that needs an action grid.
 */
export function ActionTile({
  icon,
  label,
  onClick,
  active,
  disabled,
}: {
  icon: ReactNode;
  label: string;
  onClick: () => void;
  active?: boolean;
  disabled?: boolean;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      aria-pressed={active}
      className={cn(
        'flex flex-col items-center justify-center gap-1.5 rounded-2xl border px-2 py-3 text-[12px] font-medium transition-colors disabled:opacity-50',
        active
          ? 'border-accent bg-accent/10 text-accent'
          : 'border-border bg-background text-foreground hover:bg-muted',
      )}
    >
      {icon}
      <span className="text-center leading-tight">{label}</span>
    </button>
  );
}

export default ActionTile;
