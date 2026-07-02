import { Link, useLocation } from 'react-router-dom';
import { Inbox, SlidersHorizontal } from 'lucide-react';
import { cn } from '@/lib/utils';

const TABS = [
  { name: 'Inbox', href: '/', icon: Inbox },
  { name: 'Rules', href: '/rules', icon: SlidersHorizontal },
];

/** iOS bottom tab bar — blurred, hairline top, safe-area aware. */
export function TabBar() {
  const { pathname } = useLocation();
  return (
    <nav className="fixed inset-x-0 bottom-0 z-40 border-t border-border/60 bg-card/80 backdrop-blur-xl lg:hidden">
      <div className="mx-auto flex w-full max-w-sm items-stretch justify-around px-6 pt-2 pb-[calc(env(safe-area-inset-bottom)+0.5rem)]">
        {TABS.map((t) => {
          const active = pathname === t.href;
          const Icon = t.icon;
          return (
            <Link
              key={t.name}
              to={t.href}
              className={cn(
                'flex flex-1 flex-col items-center gap-1 rounded-lg py-1 text-[11px] font-medium transition-colors',
                active ? 'text-accent' : 'text-muted-foreground hover:text-foreground',
              )}
            >
              <Icon className="h-6 w-6" strokeWidth={active ? 2.4 : 2} />
              {t.name}
            </Link>
          );
        })}
      </div>
    </nav>
  );
}

export default TabBar;
