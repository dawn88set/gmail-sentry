import { useEffect } from 'react';

/**
 * Inherit the Claritty platform's theme instead of owning a toggle.
 *
 * A Claritty app is embedded as an iframe inside the platform. The platform:
 *   1. appends `?theme=dark|light` to the iframe URL on load, and
 *   2. posts `{ type: 'CLARITTY_THEME', theme }` to the iframe whenever the
 *      user flips the platform theme (live, without reloading the frame).
 *
 * Resolution order (first match wins):
 *   1. `?theme=` URL param (platform-provided on load)
 *   2. live `CLARITTY_THEME` postMessage (platform toggle)
 *   3. the OS `prefers-color-scheme` (standalone / direct access fallback)
 *
 * No localStorage, no in-app toggle — the platform is the single source of
 * truth. Standalone (e.g. `docker compose up`) the OS preference drives it.
 */
function applyTheme(theme: 'dark' | 'light') {
  document.documentElement.classList.toggle('dark', theme === 'dark');
  document.documentElement.style.colorScheme = theme;
}

export function useClarittyTheme() {
  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const fromUrl = params.get('theme');

    const media = window.matchMedia('(prefers-color-scheme: dark)');

    // 1 + 3: URL param wins; otherwise follow the OS preference.
    if (fromUrl === 'dark' || fromUrl === 'light') {
      applyTheme(fromUrl);
    } else {
      applyTheme(media.matches ? 'dark' : 'light');
    }

    // Follow OS changes only when the platform hasn't pinned a theme.
    const onMedia = (e: MediaQueryListEvent) => {
      if (!new URLSearchParams(window.location.search).get('theme')) {
        applyTheme(e.matches ? 'dark' : 'light');
      }
    };
    media.addEventListener('change', onMedia);

    // 2: live updates from the platform on theme toggle.
    const onMessage = (event: MessageEvent) => {
      const data = event.data;
      if (data?.type === 'CLARITTY_THEME' && (data.theme === 'dark' || data.theme === 'light')) {
        // Pin it onto the URL so a later OS change doesn't override the
        // platform's explicit choice.
        const url = new URL(window.location.href);
        url.searchParams.set('theme', data.theme);
        window.history.replaceState(null, '', url.toString());
        applyTheme(data.theme);
      }
    };
    window.addEventListener('message', onMessage);

    return () => {
      media.removeEventListener('change', onMedia);
      window.removeEventListener('message', onMessage);
    };
  }, []);
}
