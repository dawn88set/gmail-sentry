import { ChevronRight } from 'lucide-react';
import type { ReactNode } from 'react';
import { cn } from '@/lib/utils';

/** iOS grouped-list section: small-caps header + a rounded group + optional footer. */
export function ListSection({
  title,
  footer,
  children,
  className,
}: {
  title?: ReactNode;
  footer?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  return (
    <section className={cn('space-y-2', className)}>
      {title && (
        <h2 className="px-4 text-[13px] font-semibold uppercase tracking-wide text-muted-foreground">{title}</h2>
      )}
      {children}
      {footer && <p className="px-4 text-[12px] leading-snug text-muted-foreground">{footer}</p>}
    </section>
  );
}

/**
 * The grouped container. Children (ListRows) get hairline separators.
 * - `card` (default): rounded, elevated card on all sizes.
 * - `plain-mobile`: flat, edge-to-edge with dividers on mobile (iOS "plain" list),
 *   becoming a rounded card only at `lg` (desktop).
 */
export function ListGroup({
  children,
  className,
  variant = 'card',
}: {
  children: ReactNode;
  className?: string;
  variant?: 'card' | 'plain-mobile';
}) {
  return (
    <div
      className={cn(
        '[&>*+*]:border-t [&>*+*]:border-border/55',
        variant === 'card'
          ? 'overflow-hidden rounded-2xl bg-card ring-1 ring-border/60'
          : '-mx-4 border-y border-border/55 lg:mx-0 lg:overflow-hidden lg:rounded-2xl lg:border-y-0 lg:bg-card lg:ring-1 lg:ring-border/60',
        className,
      )}
    >
      {children}
    </div>
  );
}

/** A single grouped cell. Tappable when `onClick` is set (adds a chevron + press state). */
export function ListRow({
  leading,
  title,
  subtitle,
  trailing,
  onClick,
  chevron,
  className,
}: {
  leading?: ReactNode;
  title?: ReactNode;
  subtitle?: ReactNode;
  trailing?: ReactNode;
  onClick?: () => void;
  chevron?: boolean;
  className?: string;
}) {
  const interactive = !!onClick;
  const Comp: any = interactive ? 'button' : 'div';
  return (
    <Comp
      onClick={onClick}
      className={cn(
        'flex w-full items-center gap-3 px-4 py-3 text-left',
        interactive && 'transition-colors hover:bg-muted/40 active:bg-muted/60',
        className,
      )}
    >
      {leading != null && <span className="flex flex-shrink-0 items-center">{leading}</span>}
      <div className="min-w-0 flex-1">
        {typeof title === 'string' ? (
          <div className="truncate text-[15px] font-medium text-foreground">{title}</div>
        ) : (
          title
        )}
        {subtitle != null &&
          (typeof subtitle === 'string' ? (
            <div className="truncate text-[13px] text-muted-foreground">{subtitle}</div>
          ) : (
            <div className="text-[13px] text-muted-foreground">{subtitle}</div>
          ))}
      </div>
      {trailing != null && <span className="flex flex-shrink-0 items-center gap-2">{trailing}</span>}
      {chevron && <ChevronRight className="h-4 w-4 flex-shrink-0 text-muted-foreground/50" />}
    </Comp>
  );
}
