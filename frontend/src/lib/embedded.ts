import { useState } from 'react';

/**
 * True when the app is rendering inside the Claritty host (an iframe/panel)
 * rather than as the top-level window.
 *
 * Why this exists: our shell swaps wholesale at `lg` — a brand top bar on
 * desktop, an iOS bottom tab bar on mobile. Tailwind breakpoints react to the
 * *panel's* width, not the monitor's, and the platform panel is usually
 * narrower than `lg`. Without this the platform would render the phone layout,
 * which is the classic "looks right locally, looks like mobile on Claritty"
 * bug. When embedded we pin the desktop shell so the platform view matches the
 * full-window design. A real phone opening the app URL directly is the top
 * window, so it still gets the responsive mobile layout.
 */
export function useEmbedded(): boolean {
  const [embedded] = useState(() => {
    try {
      return window.self !== window.top;
    } catch {
      // Cross-origin access throws — which itself means we're framed.
      return true;
    }
  });
  return embedded;
}
