import { Component, type ErrorInfo, type ReactNode } from 'react';

/**
 * Turns a render crash into something a person can act on.
 *
 * Written after the deployed app showed a completely blank pane. The cause was
 * one undefined value — a list endpoint returned a body without its list, the
 * client handed `undefined` to state, and a `.filter` during render threw. React
 * unmounts the whole tree on an uncaught render error, so a single missing field
 * cost the entire product, and the only trace was a console message inside a
 * cross-origin iframe that nobody would ever look at.
 *
 * The specific bug is fixed at the source. This exists because the NEXT one
 * shouldn't cost the whole screen either: a blank page is the single worst
 * failure a user can be shown, because it is indistinguishable from the app
 * being broken, the network being down, or the user having done something
 * wrong — and it offers no way forward.
 *
 * Deliberately plain. It states what happened, gives one action that usually
 * works, and shows the message for anyone who can use it. No stack trace, no
 * apology paragraph, no error code that means nothing to the person reading it.
 */
interface Props {
  children: ReactNode;
}

interface State {
  error: Error | null;
}

export class ErrorBoundary extends Component<Props, State> {
  state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    // The one place this is visible from outside a browser devtools session.
    console.error('[gmail-sentry] render failed:', error, info.componentStack);
  }

  render() {
    const { error } = this.state;
    if (!error) return this.props.children;

    return (
      <div className="flex min-h-[60vh] flex-col items-center justify-center px-6 text-center">
        <p className="text-[17px] font-semibold text-foreground">This screen didn’t load</p>
        <p className="mt-2 max-w-sm text-[14px] leading-relaxed text-muted-foreground">
          Something went wrong drawing this page. Your mail is untouched — nothing
          was sent, filed or changed.
        </p>
        <button
          type="button"
          onClick={() => this.setState({ error: null })}
          className="mt-5 rounded-full bg-accent px-5 py-2.5 text-[15px] font-medium text-accent-foreground"
        >
          Try again
        </button>
        <p className="mt-4 max-w-sm break-words text-[12px] text-muted-foreground/80">
          {error.message}
        </p>
      </div>
    );
  }
}

export default ErrorBoundary;
