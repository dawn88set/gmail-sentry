import { Link, useLocation } from 'react-router-dom';
import { Inbox, SlidersHorizontal } from 'lucide-react';
import { SentryMark } from '@/components/SentryMark';
import { cn } from '@/lib/utils';

const ITEMS = [
  { name: 'Inbox', href: '/', icon: Inbox },
  { name: 'Rules', href: '/rules', icon: SlidersHorizontal },
];

/**
 * macOS-style source-list sidebar (desktop only). Translucent "vibrancy" panel,
 * app identity on top, a selectable nav list below — like macOS System Settings.
 */
export function Sidebar() {
  const { pathname } = useLocation();
  return (
    <aside className="fixed inset-y-0 left-0 z-40 hidden w-64 flex-col border-r border-border/60 bg-card/70 backdrop-blur-xl lg:flex">
      <div className="flex items-center gap-2.5 px-4 py-5">
        <SentryMark className="h-8 w-8" />
        <span className="text-[15px] font-semibold tracking-tight text-foreground">Gmail Sentry</span>
      </div>

      <nav className="flex-1 space-y-1 px-3">
        {ITEMS.map((it) => {
          const active = pathname === it.href;
          const Icon = it.icon;
          return (
            <Link
              key={it.name}
              to={it.href}
              className={cn(
                'flex items-center gap-3 rounded-lg px-3 py-2 text-[14px] font-medium transition-colors',
                active ? 'bg-accent text-accent-foreground' : 'text-foreground hover:bg-muted',
              )}
            >
              <Icon className="h-[18px] w-[18px]" strokeWidth={2} />
              {it.name}
            </Link>
          );
        })}
      </nav>

      <div className="px-4 py-4 text-[11px] text-muted-foreground">Watching your inbox so you don’t have to.</div>
    </aside>
  );
}

export default Sidebar;
