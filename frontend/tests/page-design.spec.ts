import { test, expect } from '@playwright/test';
import {
  collectAuditSnapshot,
  evaluateAudit,
  type AuditFinding,
} from './visual-audit';

/**
 * G5 — rendered visual verification for FULL APP PAGES (the widget surface is
 * covered separately by widget-constraints.spec.ts).
 *
 * Boots the real app (Playwright `webServer` → `npm run dev` at :3200), renders
 * the landing page in BOTH themes at desktop + mobile widths, snapshots the live
 * DOM + computed styles, and runs the deterministic audit:
 *   - HARD (fails the build): low-contrast/invisible text (WCAG AA), sub-44px
 *     tap targets, horizontal overflow on mobile.
 *   - SOFT (warns): >2 saturated accents, font-scale chaos, off-8pt spacing.
 *
 * Same audit module the engine runs (vendored mirror), so a dev on the seed is
 * held to the same rendered bar as a generated app. Add the routes your app
 * exposes to PAGES below as you build them.
 */

const BASE = process.env.AUDIT_BASE_URL || 'http://localhost:3200';

// Full-app routes to audit. Extend as the app grows.
// Scored with NO backend, so each route is graded on its empty/error rendering —
// which is exactly the state a new user sees first.
const PAGES = ['/', '/followups', '/people', '/attention', '/activity', '/mail'];
const THEMES = ['light', 'dark'] as const;
const VIEWPORTS = [
  { name: 'desktop', w: 1280, h: 900 },
  { name: 'mobile', w: 390, h: 844 },
] as const;

const fmt = (fs: AuditFinding[]) =>
  fs.map((f) => `  • [${f.severity}] ${f.key}: ${f.message}`).join('\n');

for (const route of PAGES) {
  for (const theme of THEMES) {
    for (const vp of VIEWPORTS) {
      test(`design audit — ${route} · ${theme} · ${vp.name}`, async ({
        page,
      }) => {
        await page.setViewportSize({ width: vp.w, height: vp.h });
        // The seed's pre-paint script reads ?theme= and toggles `dark` before
        // React mounts, so the snapshot reflects the right theme from frame 1.
        await page.goto(`${BASE}${route}?theme=${theme}`);
        await page.waitForLoadState('networkidle');
        // Let the app settle into a real state (data resolved or empty/error),
        // not a transient loading flash, before measuring.
        await page.waitForTimeout(600);

        const snapshot = await page.evaluate(collectAuditSnapshot);
        if (process.env.AUDIT_DEBUG) {
          const { parseColor, contrastRatio, isLargeText } = await import(
            './visual-audit'
          );
          for (const t of snapshot.textSamples) {
            const fg = parseColor(t.fg);
            const bg = parseColor(t.bg);
            if (!fg || !bg || bg[3] === 0) continue;
            const r = contrastRatio(fg, bg);
            const min = isLargeText(t.fontPx, t.fontWeight) ? 3 : 4.5;
            if (r < min)
              console.log(
                `  FAIL ${r.toFixed(2)}:1 fg=${t.fg} bg=${t.bg} "${t.text}"`,
              );
          }
        }
        const findings = evaluateAudit(snapshot);
        const hard = findings.filter((f) => f.severity === 'hard');
        const soft = findings.filter((f) => f.severity === 'soft');

        if (soft.length) {
          // Advisory — surfaced in the report, never fails the run.
          console.warn(
            `\n⚠ design audit (soft) — ${route} · ${theme} · ${vp.name}:\n${fmt(soft)}`,
          );
        }

        expect(
          hard,
          `Rendered design issues on ${route} (${theme}, ${vp.name}):\n${fmt(hard)}\n`,
        ).toEqual([]);
      });
    }
  }
}
