import { cn } from '@/lib/utils';

/**
 * Compact iOS-style switch (46×28), tinted with the app accent when on.
 *
 * The inline `minWidth/minHeight` override the app's global mobile touch-target
 * floor (`@media (max-width:920px) button { min-height:44px }` in index.css),
 * which would otherwise stretch this fixed-size control on phones.
 */
export function Toggle({
  checked,
  onChange,
  disabled,
  className,
  'aria-label': ariaLabel,
}: {
  checked: boolean;
  onChange: (v: boolean) => void;
  disabled?: boolean;
  className?: string;
  'aria-label'?: string;
}) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      aria-label={ariaLabel}
      disabled={disabled}
      onClick={() => onChange(!checked)}
      style={{ minWidth: 46, minHeight: 28 }}
      className={cn(
        'relative inline-flex h-[28px] w-[46px] flex-shrink-0 items-center rounded-full p-0 transition-colors duration-200',
        checked ? 'bg-accent' : 'bg-muted',
        disabled && 'opacity-50',
        className,
      )}
    >
      <span
        className={cn(
          'block h-[24px] w-[24px] rounded-full bg-white shadow-[0_1px_2px_rgba(0,0,0,0.35)] transition-transform duration-200',
          checked ? 'translate-x-[20px]' : 'translate-x-[2px]',
        )}
      />
    </button>
  );
}

export default Toggle;
