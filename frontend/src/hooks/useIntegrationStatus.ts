import { useCallback, useEffect, useRef, useState } from 'react';
import {
  getRequiredIntegrations,
  type RequiredIntegration,
} from '@/lib/api';

/**
 * Connection status for this app's integrations, kept current WITHOUT a reload.
 *
 * Connecting is platform-owned: the app posts `claritty:connect-integration` and
 * the host runs OAuth in its own surface. Nothing navigates inside the iframe, so
 * a page that fetches status once on mount never learns the connection finished —
 * it keeps offering "Sign in with Google" until the user reloads by hand. That is
 * exactly the bug this fixes, and it was live on Today, Mail and the cleanup
 * lists; only Rules had the listener.
 *
 * Three signals, because no one of them is reliable on its own:
 *   - the host's ack message, when it sends one (instant, but not guaranteed)
 *   - focus / visibilitychange, for when the user comes back from the OAuth tab
 *   - a slow poll, which only runs while something is still unconnected, so a
 *     fully-connected app settles to zero background work
 *
 * `onConnect` fires on the rising edge for a given integration — not on every
 * refresh that reports it connected — so callers can kick off first-run work
 * exactly once. Without the edge, a 4s poll would restart it 15 times a minute.
 */
export interface IntegrationStatus {
  integrations: RequiredIntegration[];
  appId: string | null;
  /** False until the first response lands, so callers can hold a skeleton. */
  loaded: boolean;
  isConnected: (id: string) => boolean;
  refresh: () => Promise<void>;
}

export function useIntegrationStatus(options?: {
  /** Called once each time an integration transitions unconnected → connected. */
  onConnect?: (id: string) => void;
}): IntegrationStatus {
  const [integrations, setIntegrations] = useState<RequiredIntegration[]>([]);
  const [appId, setAppId] = useState<string | null>(null);
  const [loaded, setLoaded] = useState(false);

  // Kept in a ref so the poll/listener effects don't re-subscribe on every
  // status change, and so edge detection reads the previous value rather than a
  // stale closure.
  const connectedRef = useRef<Record<string, boolean>>({});
  const onConnectRef = useRef(options?.onConnect);
  onConnectRef.current = options?.onConnect;

  const refresh = useCallback(async () => {
    try {
      const s = await getRequiredIntegrations();
      const rows = s.integrations || [];
      // An empty list means "couldn't tell", not "nothing is connected" — keep
      // the last known good answer rather than flashing every row back to
      // disconnected and re-offering a connect button mid-session.
      if (rows.length) {
        const before = connectedRef.current;
        const after: Record<string, boolean> = {};
        for (const i of rows) after[i.id] = !!i.connected;
        connectedRef.current = after;
        setIntegrations(rows);
        // Rising edge only. `before[id]` is undefined on the very first load, so
        // an already-connected integration does not count as newly connected.
        for (const i of rows) {
          if (i.connected && before[i.id] === false) onConnectRef.current?.(i.id);
        }
      }
      setAppId(s.app_id ?? null);
    } catch {
      /* best-effort: a failed status check must never blank the page */
    } finally {
      setLoaded(true);
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  // The platform acks connect/disconnect back into the iframe — refresh at once
  // so the row flips without waiting for the next poll tick.
  useEffect(() => {
    const onMsg = (e: MessageEvent) => {
      const t = e.data?.type;
      if (
        t === 'claritty:connect-integration-done' ||
        t === 'claritty:connect-integration-started' ||
        t === 'claritty:disconnect-integration-done'
      ) {
        void refresh();
      }
    };
    window.addEventListener('message', onMsg);
    return () => window.removeEventListener('message', onMsg);
  }, [refresh]);

  // Catch a connection that completed without an ack (or with one we missed):
  // re-check when the user returns, and poll slowly meanwhile. Stops entirely
  // once everything is connected.
  useEffect(() => {
    if (loaded && integrations.length > 0 && integrations.every((i) => i.connected)) return;
    // Give up after ~2 minutes of polling. A status endpoint that never answers
    // (offline, or the audit harness running with no backend) would otherwise
    // be re-hit every 4s for as long as the tab is open. Focus and the host's
    // ack still refresh after that, so a real connection is never missed.
    let ticks = 0;
    const poll = () => {
      if (++ticks > 30) {
        window.clearInterval(iv);
        return;
      }
      void refresh();
    };
    const iv = window.setInterval(poll, 4000);
    const onVis = () => {
      if (!document.hidden) poll();
    };
    window.addEventListener('focus', poll);
    document.addEventListener('visibilitychange', onVis);
    return () => {
      window.clearInterval(iv);
      window.removeEventListener('focus', poll);
      document.removeEventListener('visibilitychange', onVis);
    };
  }, [loaded, integrations, refresh]);

  const isConnected = useCallback(
    (id: string) => integrations.find((i) => i.id === id)?.connected ?? false,
    [integrations],
  );

  return { integrations, appId, loaded, isConnected, refresh };
}

export default useIntegrationStatus;
