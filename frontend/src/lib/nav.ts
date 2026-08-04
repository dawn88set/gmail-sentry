import { Home, Building2, Bell, Activity, SlidersHorizontal } from 'lucide-react';
import type { LucideIcon } from 'lucide-react';

export interface NavItem {
  name: string;
  href: string;
  icon: LucideIcon;
}

/**
 * The app's primary navigation — the single source of truth.
 *
 * Previously duplicated in Layout, TabBar and Sidebar, which meant adding a
 * destination in one place silently left the others behind.
 *
 * Five is the ceiling. The tab bar is a fixed 384px row, so every label has to
 * survive at roughly 67px — which is why "Attention" became "Alerts" when
 * Activity was added. A label that wraps or clips fails the mobile design gate,
 * and a sixth destination would need a different shell rather than a smaller
 * font.
 */
export const NAV_ITEMS: NavItem[] = [
  // "Today", not "Inbox": the composed view of everything that needs the user,
  // as distinct from Mail, which is the mailbox itself.
  { name: 'Today', href: '/', icon: Home },
  // The differentiator, and the reason Mail gave up this slot: against a
  // dedicated mail client we are a worse mail client, but no mail client can
  // say where an account stands. Reading a thread is still one tap away — from
  // the account it belongs to, which is a better route to it than a mailbox.
  { name: 'Accounts', href: '/accounts', icon: Building2 },
  { name: 'Alerts', href: '/attention', icon: Bell },
  // What the app did while nobody was looking — the answer to "is this thing
  // actually doing anything?", which nothing in the product could give before.
  { name: 'Activity', href: '/activity', icon: Activity },
  { name: 'Rules', href: '/rules', icon: SlidersHorizontal },
];
