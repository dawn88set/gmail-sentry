/**
 * Keeping the app usable for longer than the host's token lives.
 *
 * The platform embeds this app in an iframe and passes identity as a JWT in the
 * URL (`?claritty_token=…`). That token is valid for THIRTY MINUTES. The client
 * reads it once at startup and sends it on every request, so half an hour after
 * the pane is opened every call starts failing and the app looks like it has
 * signed itself out — which is exactly what "it asks me to log in again all the
 * time" is.
 *
 * Reloading the iframe does not help: its URL still carries the same expired
 * token, so a refresh re-sends it. Only the HOST can mint a new one, and the
 * documented way to ask is the deep-link message it already listens for — it
 * reopens the pane, and the new iframe URL carries a new token.
 *
 * So: notice expiry (from the token itself, before the failure, and from a 401
 * after it), ask the host once, and tell the user what is happening in the
 * meantime. What we must NOT do is show a login prompt of our own — this app
 * has no login, and pretending otherwise sends people looking for a password
 * that doesn't exist.
 */

/** Seconds of headroom — act before the token dies, not after. */
const EXPIRY_MARGIN_S = 60;

interface TokenClaims {
  exp?: number;
  iat?: number;
  userId?: string;
  email?: string;
}

export function decodeToken(token: string | null): TokenClaims | null {
  if (!token) return null;
  try {
    const payload = token.split('.')[1];
    if (!payload) return null;
    const json = atob(payload.replace(/-/g, '+').replace(/_/g, '/'));
    return JSON.parse(json) as TokenClaims;
  } catch {
    // A token we can't read is one we can't reason about; treat it as opaque
    // rather than as expired, so a format change doesn't lock people out.
    return null;
  }
}

/** True only when we can SEE that the token has expired (or is about to). */
export function isTokenExpiring(token: string | null): boolean {
  const claims = decodeToken(token);
  if (!claims?.exp) return false;
  return claims.exp * 1000 - Date.now() < EXPIRY_MARGIN_S * 1000;
}

//: One ask per token, not one per page. A token that is replaced gets its own
//: chance to be renewed; a token that is already being renewed does not get
//: asked about twice.
let askedForToken: string | null = null;

/**
 * Ask the host to reopen this app, which re-mints the token.
 *
 * Once per page life: the host reopening the pane is a visible thing to do to
 * someone, and doing it on every failed request would make an expired session
 * feel like the app was fighting them. Returns whether the ask was made — the
 * caller decides what to tell the user when it wasn't (standalone, no host).
 */
export function requestFreshSession(path?: string, token?: string | null): boolean {
  const key = token ?? 'unknown';
  if (askedForToken === key) return false;
  if (typeof window === 'undefined' || window.parent === window) return false;
  askedForToken = key;
  try {
    window.parent.postMessage(
      {
        type: 'WIDGET_ACTION',
        action: 'DEEP_LINK',
        path: path || window.location.pathname + window.location.search,
        source: 'session-expired',
      },
      '*',
    );
    return true;
  } catch {
    return false;
  }
}

/** For tests and for a manual retry after the user has been told. */
export function resetSessionAsk(): void {
  askedForToken = null;
}

/**
 * Renew BEFORE the token dies, so nothing ever fails.
 *
 * Reacting to a 401 means the user has already seen something break. The token
 * carries its own expiry, so the honest thing is to act on it: ask the host for
 * a fresh session shortly before the current one lapses, while everything still
 * works. One ask per token, so this cannot become a loop — if the host honours
 * it, a new pane loads with a new token and this schedules itself again from
 * scratch; if it doesn't, the reactive path still explains what happened.
 *
 * Nothing here can make a dead token work: the platform edge rejects an expired
 * token with 403 before the request reaches this app at all (verified against
 * production). Renewal in time is the only avenue an app has.
 */
export function scheduleSessionRefresh(token: string | null): () => void {
  const claims = decodeToken(token);
  if (!claims?.exp) return () => {};

  const msUntilRenewal = claims.exp * 1000 - Date.now() - EXPIRY_MARGIN_S * 1000;
  // setTimeout clamps anything over ~24.8 days and fires immediately on a
  // negative delay, which would ask the instant an already-dead token loads.
  if (msUntilRenewal <= 0 || msUntilRenewal > 24 * 60 * 60 * 1000) return () => {};

  const timer = setTimeout(() => requestFreshSession(undefined, token), msUntilRenewal);
  return () => clearTimeout(timer);
}
