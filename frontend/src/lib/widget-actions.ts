/**
 * Widget Action Contract
 *
 * Standard way for a widget (rendered inside the Clarity marketplace iframe)
 * to declare interactive buttons. Two action types:
 *
 * 1. QUICK ACTION — calls the app's own backend API directly inside the
 *    widget iframe. No host involvement; widget updates itself in place.
 *
 * 2. DEEP LINK — posts a message to the parent host. The host catches it
 *    and opens its app modal (AppDialog) with the iframe pointed at the
 *    deep-link path, so the user sees the full app at that route without
 *    leaving the marketplace.
 *
 * Use the helpers below — do NOT call `window.parent.postMessage` directly.
 * See WIDGETS.md → "Widget Action Patterns" for the design rationale.
 */

export type WidgetActionMessage =
  | {
      type: 'WIDGET_ACTION';
      actionType: 'quick_action';
      actionId: string;
      source: string;
      timestamp: number;
    }
  | {
      type: 'WIDGET_ACTION';
      actionType: 'deep_link';
      path: string;
      source: string;
      timestamp: number;
    }
  | {
      type: 'WIDGET_ACTION';
      actionType: 'context_menu';
      x: number; // iframe-local viewport coordinate
      y: number;
      source: string;
      timestamp: number;
    }
  | {
      // Posted by the platform widget-bridge after a 500ms touch-and-hold
      // (cancelled if the finger moves >10px or lifts early). Apps never
      // post this themselves — the bridge owns the gesture so a widget can
      // remain fully interactive AND still let the user long-press to open
      // the host's context menu.
      type: 'WIDGET_ACTION';
      actionType: 'long_press';
      x: number; // iframe-local viewport coordinate
      y: number;
      source: string;
      timestamp: number;
    }
  | {
      type: 'WIDGET_ACTION';
      actionType: 'state_changed';
      source: string;
      timestamp: number;
    };

export interface QuickActionConfig<T> {
  actionId: string;
  run: () => Promise<T>;
  source?: string;
}

export interface DeepLinkConfig {
  path: string;
  source?: string;
}

/**
 * Resolve the widget's source slug. Apps can set `VITE_APP_SLUG` in their
 * env; if missing, fall back to the document title. Used as the `source`
 * field on every WIDGET_ACTION message for host-side analytics.
 */
export function getWidgetSource(): string {
  const fromEnv = import.meta.env?.VITE_APP_SLUG;
  if (typeof fromEnv === 'string' && fromEnv.length > 0) return fromEnv;
  if (typeof document !== 'undefined' && document.title) return document.title;
  return 'unknown';
}

/**
 * Post a WIDGET_ACTION message to the parent host. No-op when the widget
 * is NOT inside an iframe (running standalone — e.g. local dev at /widget).
 */
export function postWidgetAction(message: WidgetActionMessage): void {
  if (typeof window === 'undefined') return;
  if (window.parent === window) return; // not embedded — silently skip
  window.parent.postMessage(message, '*');
}

/**
 * Trigger a deep link. Posts a message to the host, which opens the app
 * modal at the given path. Path is a relative URL on the app's own router
 * (e.g. '/?view=chart&coin=BTC' or '/settings').
 */
export function triggerDeepLink({ path, source }: DeepLinkConfig): void {
  postWidgetAction({
    type: 'WIDGET_ACTION',
    actionType: 'deep_link',
    path,
    source: source ?? getWidgetSource(),
    timestamp: Date.now(),
  });
}

/**
 * Run a quick action: execute the app's API call, then post an
 * analytics-only message to the host so it knows the action fired.
 * Errors propagate to the caller; the analytics message fires either
 * way so success/failure rates can be measured.
 */
/**
 * Notify the host that data surfaced by this widget changed and the widget
 * should refresh. Call this from your full-app pages (rendered inside the
 * AppDialog modal) AFTER a successful mutation — e.g. user marked items as
 * read, edited a setting, deleted a watched item.
 *
 * The host bumps the widget's internal refresh counter, which triggers a
 * normal iframe reload + brief skeleton crossfade. Only THIS widget
 * refreshes; other widgets on the page are untouched.
 *
 * Don't call this for every user click — widgets already poll every 30s
 * on their own schedule. Use it when the user's action would otherwise
 * leave them looking at stale data on the widget for up to 30 seconds.
 *
 * No-op when not embedded (window.parent === window).
 */
export function notifyWidgetStateChanged(source?: string): void {
  postWidgetAction({
    type: 'WIDGET_ACTION',
    actionType: 'state_changed',
    source: source ?? getWidgetSource(),
    timestamp: Date.now(),
  });
}

/**
 * Forward right-clicks inside the widget iframe to the host so the user
 * sees the marketplace app menu (Edit Mode / Open App / Delete) instead
 * of the browser's default iframe menu. Returns a cleanup function; install
 * once on mount inside a `useEffect`.
 *
 * No-ops when the widget runs standalone (`window.parent === window`), so
 * local dev at `/widget` keeps the normal browser context menu — useful for
 * inspecting the page.
 */
export function installContextMenuBridge(): () => void {
  if (typeof window === 'undefined' || window.parent === window) {
    return () => {};
  }
  const handler = (e: MouseEvent) => {
    e.preventDefault();
    postWidgetAction({
      type: 'WIDGET_ACTION',
      actionType: 'context_menu',
      x: e.clientX,
      y: e.clientY,
      source: getWidgetSource(),
      timestamp: Date.now(),
    });
  };
  document.addEventListener('contextmenu', handler);
  return () => document.removeEventListener('contextmenu', handler);
}

export async function runQuickAction<T>({
  actionId,
  run,
  source,
}: QuickActionConfig<T>): Promise<T> {
  const resolvedSource = source ?? getWidgetSource();
  try {
    const result = await run();
    postWidgetAction({
      type: 'WIDGET_ACTION',
      actionType: 'quick_action',
      actionId,
      source: resolvedSource,
      timestamp: Date.now(),
    });
    return result;
  } catch (err) {
    postWidgetAction({
      type: 'WIDGET_ACTION',
      actionType: 'quick_action',
      actionId,
      source: resolvedSource,
      timestamp: Date.now(),
    });
    throw err;
  }
}
