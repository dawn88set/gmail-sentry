import type { ComponentProps } from 'react';
import { Badge as KitBadge } from '@clarittyai/app-ui';
import { cn } from '@/lib/utils';

/**
 * The kit's Badge, with a legible label.
 *
 * The kit draws a tone's own colour as TEXT on a 10% tint of itself. That is a
 * pleasant look and it fails WCAG AA badly — measured on this app, "Client" in
 * `success` came out at 1.9:1 and several others sat near 2:1, which is not a
 * marginal miss but genuinely hard to read. The tint already carries the
 * meaning, so the label is drawn in the foreground colour and only the
 * background stays coloured.
 *
 * Wrapped once rather than fixed at each call site: there were six, a badge is
 * the kind of thing that gets added often, and "remember to pass a className"
 * is exactly the sort of rule that decays. `className` still wins if a caller
 * genuinely wants something else.
 */
export function Badge({ className, ...rest }: ComponentProps<typeof KitBadge>) {
  // `!` matters: the kit sets its own `text-<tone>` class, and two utilities of
  // equal specificity are decided by stylesheet order, not by which was passed
  // last — so a plain `text-foreground` lost silently and the badge stayed at
  // 1.9:1. Important is the honest tool for overriding a dependency's styling.
  return <KitBadge {...rest} className={cn('!text-foreground', className)} />;
}

export default Badge;
