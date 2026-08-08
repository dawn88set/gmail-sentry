import type { ReactNode } from 'react';
import { cn } from '@/lib/utils';

/**
 * A block of content that is a CARD on desktop and part of the page on a phone.
 *
 * The same reasoning as `ListGroup`'s default: on a 390px screen a card spends
 * a gutter down each side, a rounded edge and a ring on decoration, at exactly
 * the width where content is most starved of room — and several stacked read as
 * a pile of separate boxes instead of one page. Full-bleed with a hairline top
 * and bottom is what iOS does, and it is what every list in this app already
 * does; panels were the last thing still drawing boxes on a phone.
 *
 * `tone="accent"` keeps the emphasis (a proposal, a first-run prompt) without
 * reintroducing the card.
 */
export function Panel({
  children,
  className,
  tone = 'plain',
}: {
  children: ReactNode;
  className?: string;
  tone?: 'plain' | 'accent';
}) {
  return (
    <div
      className={cn(
        // Phone: edge-to-edge, hairline rules, no corner radius to eat width.
        '-mx-4 border-y bg-card px-4 py-4',
        // Desktop: the card it always was.
        'lg:mx-0 lg:rounded-2xl lg:border lg:px-4',
        tone === 'accent' ? 'border-accent/30' : 'border-border/60',
        className,
      )}
    >
      {children}
    </div>
  );
}

export default Panel;
