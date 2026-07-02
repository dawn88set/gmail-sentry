import type { ButtonHTMLAttributes, ReactNode } from 'react';
import { cn } from '@/lib/utils';

type Variant = 'filled' | 'tinted' | 'plain' | 'destructive';

const VARIANT: Record<Variant, string> = {
  filled: 'bg-accent text-accent-foreground hover:bg-accent-600',
  tinted: 'bg-accent/12 text-accent hover:bg-accent/20',
  plain: 'text-accent hover:bg-accent/10',
  destructive: 'text-destructive hover:bg-destructive/10',
};

/** iOS-style button. `filled`/`tinted` are pill-ish; `plain`/`destructive` are text actions. */
export function IosButton({
  variant = 'filled',
  full,
  icon,
  children,
  className,
  ...props
}: {
  variant?: Variant;
  full?: boolean;
  icon?: ReactNode;
} & ButtonHTMLAttributes<HTMLButtonElement>) {
  const solid = variant === 'filled' || variant === 'tinted';
  return (
    <button
      className={cn(
        'inline-flex items-center justify-center gap-2 whitespace-nowrap rounded-xl text-[15px] font-semibold transition-colors active:scale-[0.98] disabled:opacity-50',
        solid ? 'h-11 px-5' : 'h-9 px-2',
        VARIANT[variant],
        full && 'w-full',
        className,
      )}
      {...props}
    >
      {icon}
      {children}
    </button>
  );
}

export default IosButton;
