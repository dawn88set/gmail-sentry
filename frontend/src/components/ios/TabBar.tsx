import { Link, useLocation } from 'react-router-dom';
import { NAV_ITEMS } from '@/lib/nav';
import { cn } from '@/lib/utils';

/** iOS bottom tab bar — blurred, hairline top, safe-area aware. */
export function TabBar() {
  const { pathname } = useLocation();
  return (
    <nav className="fixed inset-x-0 bottom-0 z-40 border-t border-border/60 bg-card/80 backdrop-blur-xl lg:hidden">
      {/* px-2, not px-6: with five destinations each tab gets ~72px at 390px,
          and the wider padding left "Follow-ups" without room to sit on one
          line. min-w-0 + truncate make a long label degrade gracefully instead
          of widening the row — the mobile design gate hard-fails on horizontal
          overflow. */}
      <div className="mx-auto flex w-full max-w-sm items-stretch justify-around px-2 pt-2 pb-[calc(env(safe-area-inset-bottom)+0.5rem)]">
        {NAV_ITEMS.map((t) => {
          const active = pathname === t.href;
          const Icon = t.icon;
          return (
            <Link
              key={t.name}
              to={t.href}
              className={cn(
                'flex min-w-0 flex-1 flex-col items-center gap-1 rounded-lg px-0.5 py-1 text-[11px] font-medium transition-colors',
                active ? 'text-accent' : 'text-muted-foreground hover:text-foreground',
              )}
            >
              <Icon className="h-6 w-6 flex-shrink-0" strokeWidth={active ? 2.4 : 2} />
              <span className="w-full truncate text-center leading-tight">{t.name}</span>
            </Link>
          );
        })}
      </div>
    </nav>
  );
}

export default TabBar;
