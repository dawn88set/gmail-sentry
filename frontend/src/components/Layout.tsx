import { Link, useLocation } from 'react-router-dom';
import { Inbox, SlidersHorizontal } from 'lucide-react';
import { TabBar } from '@/components/ios/TabBar';
import { SentryMark } from '@/components/SentryMark';
import { cn } from '@/lib/utils';

const NAV = [
  { name: 'Inbox', href: '/', icon: Inbox },
  { name: 'Rules', href: '/rules', icon: SlidersHorizontal },
];

interface LayoutProps {
  children: React.ReactNode;
}

/**
 * Responsive shell:
 *  - Desktop (lg+): a top bar with the brand + a segmented tab control.
 *  - Mobile (<lg): the iOS bottom tab bar.
 */
export default function Layout({ children }: LayoutProps) {
  const { pathname } = useLocation();
  return (
    <div className="relative min-h-screen bg-background">
      {/* Desktop top tabs */}
      <header className="sticky top-0 z-40 hidden border-b border-border/60 bg-background/70 backdrop-blur-xl lg:block">
        <div className="mx-auto flex h-16 max-w-5xl items-center justify-between px-6">
          <Link to="/" className="flex items-center gap-2.5">
            <SentryMark className="h-8 w-8" />
            <span className="text-[15px] font-semibold tracking-tight text-foreground">Gmail Sentry</span>
          </Link>
          <nav className="flex items-center gap-1 rounded-full border border-border/60 bg-muted/50 p-1">
            {NAV.map((it) => {
              const active = pathname === it.href;
              const Icon = it.icon;
              return (
                <Link
                  key={it.name}
                  to={it.href}
                  className={cn(
                    'flex items-center gap-2 rounded-full px-4 py-1.5 text-sm font-medium transition-colors',
                    active ? 'bg-card text-foreground shadow-sm' : 'text-muted-foreground hover:text-foreground',
                  )}
                >
                  <Icon className="h-4 w-4" />
                  {it.name}
                </Link>
              );
            })}
          </nav>
        </div>
      </header>

      <main className="min-h-screen">{children}</main>

      {/* Mobile bottom tab bar */}
      <TabBar />
    </div>
  );
}
