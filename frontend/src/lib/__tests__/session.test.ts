/**
 * The host embeds this app with a token that lives 30 minutes. Half an hour
 * after the pane is opened every request fails at once, and the app looks like
 * it signed itself out — the "it makes me log in again all the time" report.
 *
 * Reloading the iframe cannot fix it: the iframe's own URL still carries the
 * expired token. Only the host can mint a new one.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { decodeToken, isTokenExpiring, requestFreshSession, resetSessionAsk } from '../session';

function tokenWithExp(secondsFromNow: number): string {
  const payload = { exp: Math.floor(Date.now() / 1000) + secondsFromNow, userId: 'u1' };
  const b64 = btoa(JSON.stringify(payload)).replace(/\+/g, '-').replace(/\//g, '_');
  return `header.${b64}.signature`;
}

describe('token expiry', () => {
  it('reads the expiry the host actually set', () => {
    expect(decodeToken(tokenWithExp(1800))?.exp).toBeGreaterThan(Date.now() / 1000);
  });

  it('a fresh token is not treated as expiring', () => {
    expect(isTokenExpiring(tokenWithExp(1800))).toBe(false);
  });

  it('an expired token is recognised', () => {
    expect(isTokenExpiring(tokenWithExp(-10))).toBe(true);
  });

  it('acts BEFORE expiry, not after — a request in flight must not fail first', () => {
    expect(isTokenExpiring(tokenWithExp(30))).toBe(true);
  });

  it('an unreadable token is treated as opaque, never as expired', () => {
    // A format change must not lock everyone out of the app.
    expect(isTokenExpiring('not-a-jwt')).toBe(false);
    expect(isTokenExpiring(null)).toBe(false);
  });
});

describe('asking the host for a fresh session', () => {
  beforeEach(() => resetSessionAsk());
  afterEach(() => vi.restoreAllMocks());

  it('asks once, not on every failed request', () => {
    const post = vi.fn();
    vi.stubGlobal('window', {
      parent: { postMessage: post },
      location: { pathname: '/', search: '' },
    } as unknown as Window & typeof globalThis);

    expect(requestFreshSession()).toBe(true);
    expect(requestFreshSession()).toBe(false);   // a pane reopening repeatedly is worse
    expect(post).toHaveBeenCalledTimes(1);
    vi.unstubAllGlobals();
  });

  it('does nothing when not embedded — there is no host to ask', () => {
    const w = { location: { pathname: '/', search: '' } } as unknown as Window & typeof globalThis;
    (w as unknown as { parent: unknown }).parent = w;
    vi.stubGlobal('window', w);
    expect(requestFreshSession()).toBe(false);
    vi.unstubAllGlobals();
  });
});
