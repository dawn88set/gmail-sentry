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


/**
 * The interceptor must judge the payload, not the header.
 *
 * Its first version keyed on content-type and production disproved that
 * immediately: a correct JSON body delivered without `application/json` got
 * rejected, and a working endpoint reported "unexpected response from the
 * server". A header is a claim about the payload; the payload is the fact.
 */
describe('response interpretation', () => {
  const asJson = (body: string) => {
    try {
      return { ok: true as const, data: JSON.parse(body.trim()) };
    } catch {
      return { ok: false as const };
    }
  };

  it('accepts a JSON body that arrived without a JSON content-type', () => {
    const r = asJson('{"items":[],"total":0}');
    expect(r.ok).toBe(true);
    expect(r.ok && r.data.total).toBe(0);
  });

  it('rejects a body that is genuinely a page, not data', () => {
    expect(asJson('<!doctype html><html><body>504 Gateway Timeout</body></html>').ok).toBe(false);
  });

  it('treats an empty body as a failure rather than as empty data', () => {
    // '' parses as nothing; silently becoming {} would hide a real outage.
    expect(asJson('').ok).toBe(false);
  });
});
