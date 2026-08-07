/**
 * The host embeds this app with a token that lives 30 minutes. Half an hour
 * after the pane is opened every request fails at once, and the app looks like
 * it signed itself out — the "it makes me log in again all the time" report.
 *
 * Reloading the iframe cannot fix it: the iframe's own URL still carries the
 * expired token. Only the host can mint a new one.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import {
  decodeToken,
  isTokenExpiring,
  requestFreshSession,
  resetSessionAsk,
  scheduleSessionRefresh,
} from '../session';

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

  it('asks once per token, not on every failed request', () => {
    const post = vi.fn();
    vi.stubGlobal('window', {
      parent: { postMessage: post },
      location: { pathname: '/', search: '' },
    } as unknown as Window & typeof globalThis);

    expect(requestFreshSession(undefined, 'tok-a')).toBe(true);
    expect(requestFreshSession(undefined, 'tok-a')).toBe(false); // a pane reopening repeatedly is worse
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


describe('renewing before anything breaks', () => {
  beforeEach(() => {
    resetSessionAsk();
    vi.useFakeTimers();
  });
  afterEach(() => {
    vi.useRealTimers();
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
  });

  it('asks the host shortly BEFORE the token lapses, not after it fails', () => {
    const post = vi.fn();
    vi.stubGlobal('window', {
      parent: { postMessage: post },
      location: { pathname: '/', search: '' },
    } as unknown as Window & typeof globalThis);

    const token = tokenWithExp(1800);          // 30 minutes, as production issues
    scheduleSessionRefresh(token);

    vi.advanceTimersByTime(28 * 60 * 1000);    // 28 min — still healthy
    expect(post).not.toHaveBeenCalled();

    vi.advanceTimersByTime(2 * 60 * 1000);     // past the 60s margin
    expect(post).toHaveBeenCalledTimes(1);
  });

  it('does not fire instantly for a token that is already dead', () => {
    // Otherwise loading a stale pane would reopen it the moment it appeared.
    const post = vi.fn();
    vi.stubGlobal('window', {
      parent: { postMessage: post },
      location: { pathname: '/', search: '' },
    } as unknown as Window & typeof globalThis);

    scheduleSessionRefresh(tokenWithExp(-60));
    vi.advanceTimersByTime(60 * 1000);
    expect(post).not.toHaveBeenCalled();
  });

  it('can be cancelled, so an unmount leaves no timer behind', () => {
    const post = vi.fn();
    vi.stubGlobal('window', {
      parent: { postMessage: post },
      location: { pathname: '/', search: '' },
    } as unknown as Window & typeof globalThis);

    scheduleSessionRefresh(tokenWithExp(1800))();
    vi.advanceTimersByTime(31 * 60 * 1000);
    expect(post).not.toHaveBeenCalled();
  });
});
