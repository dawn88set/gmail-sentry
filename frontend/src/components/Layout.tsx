import { Link, useLocation } from 'react-router-dom';
import { TabBar } from '@/components/ios/TabBar';
import { SentryMark } from '@/components/SentryMark';
import { useEmbedded } from '@/lib/embedded';
import { AskBar } from '@/components/AskBar';
import { NAV_ITEMS } from '@/lib/nav';
import { cn } from '@/lib/utils';

interface LayoutProps {
  children: React.ReactNode;
}

/* Rail width and the matching content offset are written LITERALLY on purpose.
   Tailwind scans source for whole class strings, so a template like
   `lg:${RAIL_PAD}` is never generated and the page silently renders underneath
   the nav. Keep w-52 / pl-52 in step by hand. */

/**
 * The shell: navigation down the side, Ask across the top.
 *
 * Nav and Ask were competing for one horizontal strip, which capped both — five
 * destinations and a question box in the same row left the box too narrow to
 * show what it could do. Down the side, the nav gets full labels and room to
 * grow; across the top, Ask gets the width its rotating prompts need.
 *
 * Shells:
 *  - Desktop (lg+) and ALWAYS when embedded: sidebar + top Ask bar.
 *  - Mobile standalone (<lg): the iOS bottom tab bar, Ask still on top.
 *
 * The embedded case is forced deliberately. The Claritty panel is often
 * narrower than a desktop window, so a viewport-only breakpoint would render
 * the phone shell inside the platform and look nothing like this — see
 * CLAUDE.md, "App pages are embedded".
 */
export default function Layout({ children }: LayoutProps) {
  const { pathname } = useLocation();
  const embedded = useEmbedded();

  return (
    <div className="relative min-h-screen bg-background">
      {/* Navigation rail. */}
      <aside
        className={cn(
          'fixed inset-y-0 left-0 z-40 w-52 flex-col border-r border-border/60 bg-background/80 backdrop-blur-xl',
          embedded ? 'flex' : 'hidden lg:flex',
        )}
      >
        <Link to="/" className="flex h-16 flex-shrink-0 items-center gap-3 px-4">
          <SentryMark className="h-8 w-8 flex-shrink-0" />
          <span className="truncate text-[15px] font-semibold tracking-tight text-foreground">
            Gmail Sentry
          </span>
        </Link>

        <nav className="flex flex-1 flex-col gap-1 px-2 py-2">
          {NAV_ITEMS.map((it) => {
            const active = pathname === it.href;
            const Icon = it.icon;
            return (
              <Link
                key={it.name}
                to={it.href}
                aria-current={active ? 'page' : undefined}
                className={cn(
                  'flex items-center gap-3 rounded-xl px-3 py-2 text-[14px] font-medium transition-colors',
                  active
                    ? 'bg-muted text-foreground'
                    : 'text-muted-foreground hover:bg-muted/50 hover:text-foreground',
                )}
              >
                <Icon className="h-4 w-4 flex-shrink-0" />
                {it.name}
              </Link>
            );
          })}
        </nav>
      </aside>

      {/* Ask, across the top and nothing else in it — the width is the point. */}
      <header
        className={cn(
          'sticky top-0 z-30 border-b border-border/60 bg-background/70 backdrop-blur-xl',
          embedded ? 'pl-52' : 'lg:pl-52',
        )}
      >
        {/* Same column as the content — max-w-2xl / lg:max-w-3xl with the same
            padding as components/ios/Screen. A search box spanning the whole
            pane while everything beneath it sits in a narrower column reads as
            two different layouts stacked. */}
        <div className="mx-auto flex h-16 max-w-2xl items-center gap-3 px-4 lg:max-w-3xl lg:px-8">
          {/* The mark only appears where the rail doesn't, so the app is still
              identifiable on a phone without repeating itself on desktop. */}
          {!embedded && (
            <Link to="/" className="flex flex-shrink-0 items-center lg:hidden">
              <SentryMark className="h-8 w-8" />
            </Link>
          )}
          <AskBar variant="inline" />
        </div>
      </header>

      <main className={cn('min-h-screen', embedded ? 'pl-52' : 'lg:pl-52')}>{children}</main>

      {/* Mobile bottom tab bar — suppressed when embedded, where the rail is. */}
      {!embedded && <TabBar />}
    </div>
  );
}
