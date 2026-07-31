import { Home, Repeat2, Bell, SlidersHorizontal } from 'lucide-react';
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
 */
export const NAV_ITEMS: NavItem[] = [
  // "Today", not "Inbox": next to Follow-ups, "Inbox" reads as a competing list
  // when it's actually the composed view of everything that needs the user.
  { name: 'Today', href: '/', icon: Home },
  { name: 'Follow-ups', href: '/followups', icon: Repeat2 },
  // Finally reachable — /attention was an orphan route with no way in.
  { name: 'Attention', href: '/attention', icon: Bell },
  { name: 'Rules', href: '/rules', icon: SlidersHorizontal },
];
