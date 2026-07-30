import { Link, useLocation } from 'react-router-dom';
import { TabBar } from '@/components/ios/TabBar';
import { SentryMark } from '@/components/SentryMark';
import { useEmbedded } from '@/lib/embedded';
import { NAV_ITEMS } from '@/lib/nav';
import { cn } from '@/lib/utils';

interface LayoutProps {
  children: React.ReactNode;
}

/**
 * Responsive shell:
 *  - Desktop (lg+): a top bar with the brand + a segmented tab control.
 *  - Mobile (<lg): the iOS bottom tab bar.
 *  - Embedded in the Claritty panel: always the desktop shell, regardless of
 *    panel width — see `useEmbedded`.
 */
export default function Layout({ children }: LayoutProps) {
  const { pathname } = useLocation();
  const embedded = useEmbedded();

  return (
    <div className="relative min-h-screen bg-background">
      {/* Top tabs — desktop, and always when embedded. */}
      <header
        className={cn(
          'sticky top-0 z-40 border-b border-border/60 bg-background/70 backdrop-blur-xl',
          embedded ? 'block' : 'hidden lg:block',
        )}
      >
        <div className="mx-auto flex h-16 max-w-5xl items-center justify-between px-6">
          <Link to="/" className="flex items-center gap-2.5">
            <SentryMark className="h-8 w-8" />
            <span className="text-[15px] font-semibold tracking-tight text-foreground">Gmail Sentry</span>
          </Link>
          <nav className="flex items-center gap-1 rounded-full border border-border/60 bg-muted/50 p-1">
            {NAV_ITEMS.map((it) => {
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

      {/* Mobile bottom tab bar — suppressed when embedded (the header covers it). */}
      {!embedded && <TabBar />}
    </div>
  );
}
