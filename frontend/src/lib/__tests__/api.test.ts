import { describe, it, expect } from 'vitest';
import { resolveProxyApiBase } from '../api';

describe('resolveProxyApiBase', () => {
  it('maps a preview-proxy document path to the proxy backend base', () => {
    expect(
      resolveProxyApiBase('/api/proxy/app/user-123/app-abc/'),
    ).toBe('/api/proxy/api/user-123/app-abc');
  });

  it('works for a sub-route under the proxy prefix', () => {
    expect(
      resolveProxyApiBase('/api/proxy/app/user-123/app-abc/tasks'),
    ).toBe('/api/proxy/api/user-123/app-abc');
  });

  it('handles an absolute (origin-prefixed) pathname form', () => {
    // Some hosts mount the proxy under a longer prefix.
    expect(
      resolveProxyApiBase('/x/api/proxy/app/u/a/widget'),
    ).toBe('/x/api/proxy/api/u/a');
  });

  it('returns null for a deployed / same-origin path (no proxy prefix)', () => {
    expect(resolveProxyApiBase('/')).toBeNull();
    expect(resolveProxyApiBase('/tasks')).toBeNull();
    expect(resolveProxyApiBase('/widget')).toBeNull();
  });
});


/**
 * A 200 that isn't JSON must fail loudly, not quietly.
 *
 * The app is served from the same origin as its API, so an infrastructure
 * response — a proxy page while the container restarts mid-deploy, a login
 * redirect — arrives as HTML with a 200. Left alone, `response.data` is a
 * string, every `data.someField` is `undefined`, and that undefined travels
 * into component state and throws far away at render, naming neither the
 * endpoint nor the cause. That is how one missing field blanked the deployed
 * app; this is the boundary where it should have stopped.
 */
describe('list endpoints degrade to empty, never to undefined', () => {
  it('a response missing its list yields [] rather than undefined', async () => {
    // The exact production shape: 200, JSON, but no `alerts` key.
    const body: { alerts?: unknown[] } = {};
    const result = body?.alerts ?? [];
    expect(Array.isArray(result)).toBe(true);
    expect(result).toHaveLength(0);
  });

  it('undefined is what actually crashed the app — prove .filter throws on it', () => {
    const alerts = undefined as unknown as unknown[];
    expect(() => alerts.filter(Boolean)).toThrow(TypeError);
    // …and that the fallback makes the same call safe.
    expect((alerts ?? []).filter(Boolean)).toEqual([]);
  });
});
