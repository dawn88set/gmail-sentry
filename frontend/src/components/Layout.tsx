import { Link, useLocation } from 'react-router-dom';
import { Home, ListTodo } from 'lucide-react';
import { cn } from '@/lib/utils';
import { appName } from '@/lib/app-meta';

interface LayoutProps {
  children: React.ReactNode;
}

export default function Layout({ children }: LayoutProps) {
  const location = useLocation();

  // Integration connection is owned by the Claritty platform (the app's
  // Intelligence / Settings → Integrations tabs). The app declares integrations
  // in intelligence.yaml and ships NO in-app connect surface — so no
  // Integrations nav item or setup banner here.
  const navigation = [
    { name: 'Home', href: '/', icon: Home },
    { name: 'Tasks', href: '/tasks', icon: ListTodo },
  ];

  // App glyph — the app's own initial in a themed tile. Derived from the
  // stamped appName so every generated app brands its OWN header (never the
  // platform mark). Theme-token driven so it follows the per-app palette.
  const appInitial = (appName.trim()[0] || 'A').toUpperCase();

  return (
    <div className="min-h-screen bg-background">
      {/* Header — glass morphism over the page (semantic tokens for dark mode) */}
      <header className="sticky top-0 z-50 w-full border-b border-border bg-background/80 backdrop-blur-lg">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex justify-between items-center h-16 lg:h-20">
            {/* Brand — the app's OWN initial glyph + name. Generation stamps
                appName per app; the glyph follows the per-app theme accent. */}
            <Link to="/" className="flex items-center gap-2.5 group">
              <span
                aria-hidden="true"
                className="flex h-7 w-7 flex-shrink-0 items-center justify-center rounded-lg bg-accent/15 text-sm font-bold text-foreground"
              >
                {appInitial}
              </span>
              <span className="inline-block text-lg lg:text-xl font-bold text-foreground transition-colors group-hover:text-accent">
                {appName}
              </span>
            </Link>

            {/* Navigation */}
            <nav className="flex items-center gap-1 lg:gap-2">
              {navigation.map((item) => {
                const isActive = location.pathname === item.href;
                const Icon = item.icon;
                return (
                  <Link
                    key={item.name}
                    to={item.href}
                    className="relative px-4 lg:px-5 py-2 rounded-lg group"
                  >
                    <div className="flex items-center gap-2">
                      <Icon className="h-4 w-4" />
                      <span
                        className={cn(
                          'text-sm lg:text-base font-medium transition-colors',
                          isActive
                            ? 'text-foreground'
                            : 'text-muted-foreground group-hover:text-foreground'
                        )}
                      >
                        {item.name}
                      </span>
                    </div>

                    {/* Active indicator */}
                    {isActive && (
                      <span className="absolute inset-0 bg-accent/10 rounded-lg -z-10" />
                    )}

                    {/* Hover effect — background tint (no scale, per brand) */}
                    <span className="absolute inset-0 bg-muted rounded-lg opacity-0 group-hover:opacity-100 transition-opacity -z-20" />
                  </Link>
                );
              })}
            </nav>
          </div>
        </div>
      </header>

      {/* Main Content */}
      <main className="min-h-[calc(100vh-16rem)]">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8 sm:py-12 space-y-6">
          {children}
        </div>
      </main>

      {/* Footer - Minimal Apple style */}
      <footer className="border-t border-border py-8 mt-16">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex flex-col sm:flex-row items-center justify-between gap-4 text-sm text-muted-foreground">
            <p className="text-center font-medium text-foreground sm:text-left">{appName}</p>
            <p className="text-center text-xs text-muted-foreground sm:text-right">
              © {new Date().getFullYear()} {appName}
            </p>
          </div>
        </div>
      </footer>
    </div>
  );
}
