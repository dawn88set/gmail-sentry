import { Inbox, SlidersHorizontal } from 'lucide-react';
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
  { name: 'Inbox', href: '/', icon: Inbox },
  { name: 'Rules', href: '/rules', icon: SlidersHorizontal },
];
