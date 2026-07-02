/**
 * Connecting integrations is PLATFORM-OWNED. The sanctioned way to start a
 * connection from inside the app is to post `claritty:connect-integration` to
 * the host — the Claritty platform intercepts it and runs its integration gate
 * (OAuth / API-key flow) for that integration, scoped to this app.
 *
 * We never build our own OAuth UI; this just asks the platform to open its gate.
 * Returns false when not embedded (local/standalone) so callers can fall back to
 * a "connect on the Integrations tab" hint.
 */
export function requestConnectIntegration(integrationId: string, appId?: string | null): boolean {
  try {
    if (typeof window !== 'undefined' && window.parent && window.parent !== window) {
      // Send the documented message with redundant key spellings so whichever
      // shape the host expects (integrationId | integration | id | provider)
      // resolves. Extra keys are ignored by the platform.
      const payload = {
        type: 'claritty:connect-integration',
        integrationId,
        integration: integrationId,
        id: integrationId,
        provider: integrationId,
        appId: appId ?? undefined,
      };
      window.parent.postMessage(payload, '*');
      // Also emit the older/generic action envelope some hosts listen for.
      window.parent.postMessage(
        { type: 'CLARITTY_ACTION', action: 'connect-integration', integrationId, appId: appId ?? undefined },
        '*',
      );
      return true;
    }
  } catch {
    /* ignore */
  }
  return false;
}

/**
 * Ask the platform to DISCONNECT (revoke) this app's credential for an
 * integration — the counterpart to requestConnectIntegration. The platform
 * intercepts `claritty:disconnect-integration`, revokes the per-app credential,
 * and acks `claritty:disconnect-integration-done`. Use it to let the user
 * disconnect (then reconnect) from inside the app. Returns false when not
 * embedded (local/standalone).
 */
export function requestDisconnectIntegration(integrationId: string, appId?: string | null): boolean {
  try {
    if (typeof window !== 'undefined' && window.parent && window.parent !== window) {
      window.parent.postMessage(
        {
          type: 'claritty:disconnect-integration',
          integrationId,
          integration: integrationId,
          id: integrationId,
          provider: integrationId,
          appId: appId ?? undefined,
        },
        '*',
      );
      return true;
    }
  } catch {
    /* ignore */
  }
  return false;
}
