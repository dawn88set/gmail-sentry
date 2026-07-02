import type { ReactNode } from 'react';
import { cn } from '@/lib/utils';

/**
 * A screen with a large-title header + a content column that clears the mobile
 * tab bar. Navigation lives in Layout (desktop top tabs / mobile bottom bar).
 */
export function Screen({
  title,
  action,
  children,
  className,
}: {
  title: ReactNode;
  action?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  return (
    <div className={cn('mx-auto max-w-2xl px-4 pb-28 pt-8 lg:max-w-3xl lg:px-8 lg:pb-16', className)}>
      <header className="mb-5 flex items-end justify-between gap-3">
        <h1 className="text-[30px] font-bold leading-tight tracking-tight text-foreground sm:text-[34px]">
          {title}
        </h1>
        {action && <div className="flex flex-shrink-0 items-center gap-2 pb-1">{action}</div>}
      </header>
      <div className="space-y-7">{children}</div>
    </div>
  );
}

export default Screen;
