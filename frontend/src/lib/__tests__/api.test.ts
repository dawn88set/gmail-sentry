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
